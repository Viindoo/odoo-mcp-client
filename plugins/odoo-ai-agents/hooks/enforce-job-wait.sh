#!/usr/bin/env bash
# enforce-job-wait.sh - Stop / SubagentStop gate on an odoo-local job the stopping agent started and
# never collected.
#
# WHY: `instance_build` and `instance_i18n_export` start a job that outlives the tool call and
# return its job_id; `job_wait` collects it. A job that finishes notifies NOBODY - not the main
# conversation, not a dispatched agent - unlike a background shell or an async subagent. An agent
# that ends its turn with such a job still running leaves the session idle until a human asks what
# it is waiting for (measured: a build finished sixteen minutes before the owner asked). Starting
# the job is a working pattern; the failure moment is the TURN END with the job still running, so
# the gate sits there. `job_wait`'s own description says never to end a turn waiting on a build
# without a tool call; this is the enforcement.
#
# WHAT IT DOES: stops the turn ONCE ({"decision":"block","reason":...}) and names each running job
# with its two honest exits. The main conversation (Stop) either waits with `job_wait` until the
# result is not `timeout`, or tells the human the job is still running and that nothing wakes the
# session when it ends. A dispatched agent (SubagentStop) either waits the same way or reports the
# job id and output path so its caller can collect it; the reason ends on the sentence that says
# what its caller receives.
#
# HOW A JOB IS ATTRIBUTED. The job record (scripts/mcp/odoo_local/jobs.py, $ODOO_AI_HOME/runtime/
# jobs/<job_id>.json) names the command, the pid and the server session's anchor; it does NOT name
# the agent that started the job - every agent of a session shares one odoo-local server. So
# "this agent started job J" is read from the agent's OWN transcript: an odoo-local job-starting
# tool call (JOB_STARTERS below) whose result carries `job_id` at its top level (a refusal nests its
# diagnostics under `error`, so another job named there is never taken for this agent's own). A job
# counts only while that transcript holds no `job_wait` result for it whose `state` is not
# `running`. The transcript
# only NOMINATES a job; whether it is still running is the job store's verdict (jobs.status: the
# exit file is absent, the recorded pid is alive and is the same process), so a job that finished,
# a record whose process is gone, a recycled pid and a job nobody started in this transcript never
# stop a turn.
#
# JOB_STARTERS is the set of odoo-local tools whose result carries a job_id and that are not
# `job_wait`; tests/test_job_wait_hook.py compares it with the server's own tool list.
#
# CONTRACT (Claude Code Stop / SubagentStop): stdin JSON has transcript_path, stop_hook_active,
# hook_event_name; SubagentStop also carries agent_transcript_path (the subagent's OWN transcript -
# the one read; the payload's transcript_path is the whole session's).
#   - Bounded: a stop a hook already continued (stop_hook_active=true) passes, so the reason is
#     given at most once per stop and can never loop.
#   - Reads the transcript through the job-start tool names only (hooks/transcript-lines.sh): a
#     transcript with none of them costs one fixed-string scan.
#   - Degrades to exit 0 on any uncertainty: no jq, no python3, no transcript, an unreadable job
#     record, a job store that cannot be imported.
#
# STATED RESIDUALS:
#   - A job a child agent started and handed to this agent by id (never through a starter call in
#     this agent's transcript) is not attributed to it.
#   - A job started in a transcript that was compacted away is not seen once the starting call has
#     left it.
#   - The hook reads the job store under its own $ODOO_AI_HOME; a server started with a different
#     one is not found, and the gate passes.

set -uo pipefail

_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
command -v python3 >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

[[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)" == "true" ]] && _pass
EVENT="$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)"
[[ "$EVENT" == "Stop" || "$EVENT" == "SubagentStop" ]] || _pass

_HOOK_DIR="${BASH_SOURCE[0]%/*}"
[[ -r "$_HOOK_DIR/final-report.sh" ]] || _pass
# shellcheck source=/dev/null
. "$_HOOK_DIR/final-report.sh"
# shellcheck source=/dev/null
. "$_HOOK_DIR/../scripts/lib/run_bounded.sh" 2>/dev/null || true
declare -F run_bounded >/dev/null 2>&1 || _pass

# The odoo-local tools that start a job, and the one that collects it (tool-name suffixes).
JOB_STARTERS='instance_build|instance_i18n_export'
JOB_COLLECTOR='job_wait'

TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass
grep -qE "odoo-local__($JOB_STARTERS)" -- "$TRANSCRIPT" 2>/dev/null || _pass

# Job ids this transcript started and never read to a terminal state, oldest first.
CANDIDATES="$(jq -rRs "$_FR_JQ_RECORDS"'
  | def named($re): select(type == "object" and .type == "tool_use" and ((.name // "") | tostring | test($re)));
    ([ $R[] | select(.role == "assistant") | .content | (if type == "array" then .[] else empty end)
       | named("odoo-local__('"$JOB_STARTERS"')$") | .id ]) as $starters
  | ([ $R[] | select(.role == "assistant") | .content | (if type == "array" then .[] else empty end)
       | named("odoo-local__'"$JOB_COLLECTOR"'$") | {id: .id, job: ((.input.job_id // "") | tostring)} ]) as $waits
  | [ $R[] | .tur as $tur | .content | (if type == "array" then .[] else empty end)
      | select(type == "object" and .type == "tool_result")
      | {id: (.tool_use_id // ""),
         p: ((.content | blocktext | fromjson?)
             // ($tur | if type == "string" then (fromjson? // null)
                        elif type == "object" then (.structuredContent // null) else null end))} ] as $res
  | ([ $res[] | select(.id as $i | $starters | any(. == $i))
       | select((.p | type) == "object" and ((.p.job_id | type) == "string"))
       | .p.job_id ]) as $started
  | ([ $res[] | . as $r | select((.p | type) == "object" and ((.p.state | type) == "string") and .p.state != "running")
       | $waits[] | select(.id == $r.id) | .job ]) as $collected
  | ($started | unique) - $collected | .[]
' < <(_tool_call_lines "$TRANSCRIPT" "odoo-local__instance_build" "odoo-local__instance_i18n_export" \
        "odoo-local__job_wait") 2>/dev/null || true)"
[[ -n "$CANDIDATES" ]] || _pass

# The job store's verdict on each: job_id, op, output path of the ones still running.
MCP_DIR="${CLAUDE_PLUGIN_ROOT:-${_HOOK_DIR%/hooks}}/scripts/mcp"
[[ -r "$MCP_DIR/odoo_local/jobs.py" ]] || _pass
# shellcheck disable=SC2046
RUNNING="$(run_bounded 5 python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from odoo_local import jobs
for job_id in sys.argv[2:]:
    st = jobs.status(job_id)
    if st and st.get("state") == "running":
        meta = st.get("meta") or {}
        row = [job_id, meta.get("op") or "-", st.get("log_path") or "-"]
        print("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in row))
' "$MCP_DIR" $(printf '%s\n' "$CANDIDATES" | head -n 20) 2>/dev/null || true)"
[[ -n "$RUNNING" ]] || _pass

# Output bound: the harness cuts a hook output over 10,000 characters, so at most five jobs are
# listed and the rest counted.
N="$(printf '%s\n' "$RUNNING" | grep -c . || true)"
LINES=""; i=0
while IFS=$'\t' read -r job_id op out; do
  [[ -n "$job_id" ]] || continue
  i=$(( i + 1 ))
  (( i > 5 )) && continue
  LINES="$LINES"$'\n'"  job_id $job_id (op $op), output so far: ${out:0:300}"
done <<< "$RUNNING"
(( N > 5 )) && LINES="$LINES"$'\n'"  +$(( N - 5 )) more running job(s), same two moves apply"

if [[ "$EVENT" == "Stop" ]]; then
  EXITS="1) WAIT FOR IT NOW: call job_wait with the job_id (repeat while its result is timeout), then read the result and act on it. 2) If you must stop now, tell the user plainly that the job is still running and that nothing will wake this session when it ends - they have to ask you to collect it with job_wait."
else
  EXITS="1) WAIT FOR IT IN THIS TURN: call job_wait with the job_id (repeat while its result is timeout), then read the result and put it in your report. 2) If the result cannot be obtained inside this turn, report status BLOCKED naming the job_id and its output path, so your caller can collect it with job_wait - never a completion claim over a result you never read."
fi

REASON="Unwakeable-job gate: this turn is ending with ${N} odoo-local job(s) that you started and have not collected still running. A job that finishes notifies nobody, so its result stays unread until someone asks.${LINES}

${EXITS}"
if [[ "$EVENT" == "SubagentStop" ]]; then
  REASON="$REASON"$'\n\n'"$(_subagent_note_tail "$TRANSCRIPT" "$INPUT")"
fi

jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
exit 0
