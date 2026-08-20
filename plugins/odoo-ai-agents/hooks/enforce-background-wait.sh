#!/usr/bin/env bash
# enforce-background-wait.sh - SubagentStop gate on the unwakeable background-shell wait.
#
# WHY: the Bash tool answers a backgrounded command with "You will be notified when it
# completes." That promise is written for the ROOT conversation and holds there. It does
# NOT hold for a dispatched agent: a SubagentStop IS the end of that dispatch, nothing
# resumes it, and the command's result is delivered to nobody. Measured shape - a subagent
# backgrounded a command, wrote one "WAITING, I have not read its output" line, ended its
# turn, and its caller received that line as the subagent's whole report while the command
# was still running. This hook refuses that one stop.
#
# NOT a PreToolUse deny on the backgrounding itself. Backgrounding is a WORKING pattern
# here: a subagent may start a long command and then wait for it INSIDE THE SAME TURN with
# foreground calls (that is exactly how odoo-instance-ops drives every long Odoo build -
# background launch, then a blocking foreground `wait-log`). The failure moment is not the
# start, it is the TURN END with the command still live, so the gate sits at the turn end.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON carries session_id, transcript_path (the
# SESSION transcript), cwd, permission_mode, hook_event_name, stop_hook_active,
# last_assistant_message, agent_id + agent_type + agent_transcript_path (SubagentStop only -
# a root `Stop` payload has none of the three), and `background_tasks`: an array of
# {id, type, status, description, command?, agent_type?} covering the whole session. Entries
# with `"type": "subagent"` are agent children (INCLUDING the stopping subagent itself) and
# are NEVER gated: an agent child does wake the launcher that stopped for it. Only
# `"type": "shell"` entries are this hook's business. A shell task that has finished is
# REMOVED from the array, so "still listed as running" is the liveness test.
#   - Block form: {"decision":"block","reason":"..."} on stdout.
#   - Loop-safe: stop_hook_active=true -> never re-block.
#   - ROOT-SAFE: gated on hook_event_name == SubagentStop AND a non-empty agent_id. The root
#     IS woken when a background command finishes, so blocking there would be wrong.
#   - OWNERSHIP: `background_tasks` is SESSION-wide, so a task the ROOT (or a sibling)
#     started appears here too. Blocking this subagent for someone else's command would
#     demand a fix it cannot make, so a live task counts only when the subagent's OWN
#     transcript (agent_transcript_path) shows the Bash tool handing it that task id.
#   - Degrades to exit 0 on ANY uncertainty: no jq, unreadable stdin, no `background_tasks`
#     key, an unexpected payload shape, no agent identity, no readable agent transcript, or
#     no correlated id. A false block halts real work; prefer the false negative every time.
#
# STATED RESIDUAL FALSE NEGATIVES (see tests/test_background_wait_gate.py):
#   - A command backgrounded OUTSIDE the Bash tool's background flag - a bare `&`, `setsid`,
#     `nohup`, or a `disown` inside an ordinary foreground call - never becomes a task id and
#     never appears in `background_tasks`. It is invisible here, and it always will be.
#   - A live task started by the ROOT or a sibling and merely QUOTED in this subagent's
#     transcript would correlate; the block is still actionable (read the file, or say so),
#     but the ownership claim would be wrong.
#   - Only `"status": "running"` is treated as live. Any other live-but-differently-labelled
#     status passes.

set -uo pipefail

_pass() { exit 0; }   # approve / stay out of the way

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass   # already continuing from a prior block - no loop

# --- Root vs subagent -----------------------------------------------------------------------
# Two independent facts, both required. The event name alone would still fire if the hook were
# ever wired under `Stop` by mistake; agent_id alone would trust a field a future payload may
# reuse. A root `Stop` payload carries neither, and the root is genuinely woken by a finishing
# background command - so on the root this hook must do nothing at all.
EVENT="$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)"
[[ "$EVENT" == "SubagentStop" ]] || _pass
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" ]] || _pass   # no caller identity -> fail open

# --- Live background SHELL tasks (never a subagent entry) ------------------------------------
# An absent / non-array `background_tasks` is an unknown payload shape, not an empty one:
# pass. Fields are forced non-empty in the TSV (a bare `tostring` on the optional `command`)
# so a missing middle column cannot shift the row under a whitespace IFS read.
[[ "$(printf '%s' "$INPUT" | jq -r '(.background_tasks | type) // "missing"' 2>/dev/null || echo missing)" == "array" ]] || _pass

LIVE_ROWS="$(printf '%s' "$INPUT" | jq -r '
  .background_tasks[]?
  | select((.type // "") == "shell")
  | select((.status // "") == "running")
  | [((.id // "") | tostring),
     (((.command // .description // "") | tostring) | gsub("[\n\t]"; " "))]
  | @tsv' 2>/dev/null || true)"
[[ -n "$LIVE_ROWS" ]] || _pass

# --- Ownership: the subagent's OWN transcript must show the Bash tool handing it that id -----
# `agent_transcript_path` is the SUBAGENT's transcript; the payload's plain `transcript_path`
# is the SESSION's and is deliberately NOT used - correlating against it would attribute the
# root's own background commands to whichever subagent happened to stop next.
AGENT_TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.agent_transcript_path // empty' 2>/dev/null || true)"
[[ -n "$AGENT_TRANSCRIPT" && -f "$AGENT_TRANSCRIPT" ]] || _pass

_tmo() { if command -v timeout >/dev/null 2>&1; then timeout 5 "$@"; else "$@"; fi; }

# Every string anywhere in the subagent's transcript, one per line. Recursive descent (`..`)
# rather than a role/content walk on purpose: the evidence lives in a `tool_result`, which the
# harness authors, and its nesting is not ours to assume. A jq failure yields an empty scan ->
# no correlation -> pass.
OWN_STRINGS="$(_tmo jq -rR 'fromjson? | .. | strings' "$AGENT_TRANSCRIPT" 2>/dev/null || true)"
[[ -n "$OWN_STRINGS" ]] || _pass

OWN_IDS="$(printf '%s\n' "$OWN_STRINGS" \
  | grep -oE 'running in background with ID: [A-Za-z0-9_-]+' 2>/dev/null \
  | sed -E 's/.*ID: //' | grep -vE '^$' | sort -u || true)"
[[ -n "$OWN_IDS" ]] || _pass

# --- Build the finding -----------------------------------------------------------------------
LINES=""
N=0
while IFS=$'\t' read -r task_id task_cmd; do
    [[ -n "$task_id" ]] || continue
    printf '%s\n' "$OWN_IDS" | grep -qxF "$task_id" 2>/dev/null || continue
    # The output file the Bash tool named back to this subagent, read from its own transcript -
    # never reconstructed from a guessed temp-dir layout.
    out_path="$(printf '%s\n' "$OWN_STRINGS" | grep -oE "/[^ \"']*${task_id}\.output" 2>/dev/null | head -1 || true)"
    [[ -n "$out_path" ]] || out_path="(output path not recorded in your transcript - re-read the Bash result that started task ${task_id})"
    N=$(( N + 1 ))
    LINES="$LINES"$'\n'"  [$task_id] $task_cmd"$'\n'"      output so far: $out_path"
done <<< "$LIVE_ROWS"

[[ "$N" -gt 0 ]] || _pass   # every live shell task belongs to someone else

REASON="Unwakeable-wait gate: you are a DISPATCHED agent and this turn is ending with ${N} background shell command(s) you started still running. Ending your turn ENDS your dispatch - the Bash tool's \"You will be notified when it completes\" line is written for the root conversation and does NOT hold for you. Nothing resumes a dispatched agent for a background shell command, so its result is reachable only inside THIS turn, and stopping now discards it.${LINES}

Do ONE of these for EACH command above, before you stop:
1) READ IT NOW - the output file above already holds everything the command has printed so far. Read it, use what is there, and say in your report that the command had not finished.
2) WAIT FOR IT IN THIS TURN - make your VERY NEXT action a FOREGROUND tool call that blocks until the command is finished (never a text-only reply), then read that output file. Repeat the foreground wait as many times as it takes; every response you emit before you hold the result MUST carry a tool call.
3) STOP IT - if you no longer need the result, kill the command (\`KillShell\` on task id <id> when your toolset has it, otherwise terminate the process from a foreground Bash call), and say so in your report.

Then emit your \`continuation\` block. If the result cannot be obtained inside this turn, report \`status: BLOCKED\`, naming the command and its output path so your caller can pick it up - never a completion claim over a background command you never read."

jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
exit 0
