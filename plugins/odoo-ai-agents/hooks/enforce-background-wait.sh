#!/usr/bin/env bash
# enforce-background-wait.sh - SubagentStop gate on an unwakeable wait.
#
# WHY: a dispatched agent that ends its turn while it still waits on something it started loses
# that thing's result whenever nothing will wake it. Two shapes, both refused here:
#
#   (1) A BACKGROUND SHELL COMMAND OR MONITOR WATCH, on every surface. The Bash tool answers a
#       backgrounded command with "You will be notified when it completes."; the Monitor tool
#       answers with "You will be notified on each event". That promise is written for the ROOT
#       conversation and holds there. It does NOT hold for a dispatched agent: a SubagentStop IS
#       the end of that dispatch, nothing resumes it, and the command's result is delivered to
#       nobody. Measured shape - a subagent backgrounded a command, wrote one "WAITING, I have not
#       read its output" line, ended its turn, and its caller received that line as the
#       subagent's whole report while the command was still running.
#   (2) AN ASYNC TEAMMATE, on an UNATTENDED surface only. Measured on `claude -p` (hook env
#       CLAUDE_CODE_ENTRYPOINT=sdk-cli, CLAUDE_CODE_SESSION_ATTENDED=0): a subagent that launches a
#       child asynchronously and then ends its turn is NOT woken - the harness marks it completed
#       and the child's completion notification goes to the MAIN session. On the interactive
#       surface (ENTRYPOINT=cli, ATTENDED=1) the same subagent IS woken once per child, so ending
#       the turn there is the correct move and this arm stays silent. The rule an agent follows is
#       snippets/spawner-completion-contract.md R0 (move 2 on the surface whose agent-launch tool carries
#       run_in_background, move 3 on the one whose agent-launch tool does not).
#
# NOT a PreToolUse deny on the backgrounding or the launch itself. Both are WORKING patterns: a
# subagent may start a long command, or receive an async receipt, and then wait for it INSIDE THE
# SAME TURN with tool calls. (Long Odoo builds do not take the shell path at all: odoo-instance-ops
# runs them through the odoo-local `instance_build` tool, which returns a job_id, and blocks on
# `job_wait`.) The failure moment is not the start, it is the TURN END with the work still live, so
# the gate sits at the turn end.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON carries session_id, transcript_path (the
# SESSION transcript), cwd, permission_mode, hook_event_name, stop_hook_active,
# last_assistant_message, agent_id + agent_type + agent_transcript_path (SubagentStop only -
# a root `Stop` payload has none of the three), and `background_tasks`: an array of
# {id, type, status, description, command?, agent_type?} covering the whole session. A
# `"type": "shell"` entry is a Bash background command; a `"type": "subagent"` entry is an agent
# launched asynchronously (its id IS the agentId the async launch receipt names; a launch that
# returned its result in-turn is never listed) - the stopping subagent's OWN entry included. A task
# that has finished is REMOVED from the array, so "still listed as running" is the liveness test.
#   - Block form: {"decision":"block","reason":"..."} on stdout.
#   - Loop-safe: stop_hook_active=true -> never re-block.
#   - ROOT-SAFE: gated on hook_event_name == SubagentStop AND a non-empty agent_id. The root
#     IS notified of every completion on every surface, so blocking there would be wrong.
#   - OWNERSHIP: `background_tasks` is SESSION-wide, so a task the ROOT (or a sibling)
#     started appears here too. Blocking this subagent for someone else's work would demand a
#     fix it cannot make, so a live task counts only when the subagent's OWN transcript
#     (agent_transcript_path) shows it receiving that task id: for a shell task the Bash tool's
#     "running in background with ID: <id>" receipt, its "moved to the background (ID: <id>)"
#     receipt for a foreground command that outran its timeout, or the Monitor tool's "Monitor
#     started (task <id>," receipt - a Monitor watch is a `type: "shell"` entry in
#     `background_tasks` (measured: the harness labels its local-shell task kind "shell" whatever
#     started it) - and for a subagent task the agent-launch tool's "Async agent launched
#     successfully ... agentId: <id>" receipt for a subagent task. Its own entry never correlates
#     (its id is also skipped outright).
#   - SURFACE (subagent arm only): unattended iff CLAUDE_CODE_SESSION_ATTENDED=0, or that variable
#     is unset and CLAUDE_CODE_ENTRYPOINT=sdk-cli. ATTENDED=1 (interactive) or neither signal ->
#     the subagent arm stays silent; the shell arm is surface-independent.
#   - Degrades to exit 0 on ANY uncertainty: no jq, unreadable stdin, no `background_tasks`
#     key, an unexpected payload shape, no agent identity, no readable agent transcript, no
#     surface signal, or no correlated id. A false block halts real work; prefer the false
#     negative every time.
#
# STATED RESIDUAL FALSE NEGATIVES (see tests/test_background_wait_gate.py):
#   - A command backgrounded OUTSIDE the Bash tool's background flag - a bare `&`, `setsid`,
#     `nohup`, or a `disown` inside an ordinary foreground call - never becomes a task id and
#     never appears in `background_tasks`. It is invisible here, and it always will be.
#   - A live task started by the ROOT or a sibling and merely QUOTED in this subagent's
#     transcript would correlate; the block is still actionable, but the ownership claim would
#     be wrong.
#   - Only `"status": "running"` is treated as live. Any other live-but-differently-labelled
#     status passes.
#   - A teammate that finished after the subagent last made a tool call is no longer listed, so a
#     result that reached the main session instead of the subagent is not caught here.
#   - An unattended surface that exports neither surface signal is treated as interactive.

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
# reuse. A root `Stop` payload carries neither, and the root is notified of every completion -
# so on the root this hook must do nothing at all.
EVENT="$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)"
[[ "$EVENT" == "SubagentStop" ]] || _pass
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" ]] || _pass   # no caller identity -> fail open

# The surface test and the teammate correlation are hooks/teammate-wait.sh, shared with
# enforce-teardown.sh (which reads the same stop as a WAIT on the surfaces this arm leaves alone).
# Unreadable -> fail open.
[[ -r "${BASH_SOURCE[0]%/*}/teammate-wait.sh" ]] || _pass
# shellcheck source=/dev/null
. "${BASH_SOURCE[0]%/*}/teammate-wait.sh"

# --- Surface: only an UNATTENDED one leaves a stopped subagent unwoken for an agent child -------
UNATTENDED=0
_tw_unattended && UNATTENDED=1

# --- Live background tasks --------------------------------------------------------------------
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

LIVE_AGENT_ROWS=""
[[ "$UNATTENDED" == "1" ]] && LIVE_AGENT_ROWS="$(_tw_live_agent_rows "$INPUT" "$AGENT_ID")"
[[ -n "$LIVE_ROWS" || -n "$LIVE_AGENT_ROWS" ]] || _pass

# --- Ownership: the subagent's OWN transcript must show it receiving that id -----------------
# `agent_transcript_path` is the SUBAGENT's transcript; the payload's plain `transcript_path`
# is the SESSION's and is deliberately NOT used - correlating against it would attribute the
# root's own background work to whichever subagent happened to stop next.
AGENT_TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.agent_transcript_path // empty' 2>/dev/null || true)"
[[ -n "$AGENT_TRANSCRIPT" && -f "$AGENT_TRANSCRIPT" ]] || _pass

# A 5s bound on every host (stock macOS has no `timeout`): run_bounded, loaded by teammate-wait.sh.
_tmo() { run_bounded 5 "$@"; }

# Every string anywhere in the subagent's transcript, one per line. Recursive descent (`..`)
# rather than a role/content walk on purpose: the evidence lives in a `tool_result`, which the
# harness authors, and its nesting is not ours to assume. A jq failure yields an empty scan ->
# no correlation -> pass.
OWN_STRINGS="$(_tmo jq -rR 'fromjson? | .. | strings' "$AGENT_TRANSCRIPT" 2>/dev/null || true)"
[[ -n "$OWN_STRINGS" ]] || _pass

# Shell task ids this subagent was handed: the Bash background receipt, the Bash receipt for a
# foreground command moved to the background on timeout, and the Monitor receipt. A Monitor id is
# also kept apart, only so the refusal can say which kind of task it names.
OWN_MONITOR_IDS="$(printf '%s\n' "$OWN_STRINGS" \
  | grep -oE 'Monitor started \(task [A-Za-z0-9_-]+' 2>/dev/null \
  | sed -E 's/.*\(task //' | grep -vE '^$' | sort -u || true)"
OWN_IDS="$( { printf '%s\n' "$OWN_STRINGS" \
  | grep -oE 'running in background with ID: [A-Za-z0-9_-]+|moved to the background \(ID: [A-Za-z0-9_-]+' 2>/dev/null \
  | sed -E 's/.*ID: //'; printf '%s\n' "$OWN_MONITOR_IDS"; } | grep -vE '^$' | sort -u || true)"

# Agent ids this subagent launched asynchronously (teammate-wait.sh _tw_async_launched_ids).
OWN_AGENT_IDS=""
[[ -n "$LIVE_AGENT_ROWS" ]] && OWN_AGENT_IDS="$(_tw_async_launched_ids "$AGENT_TRANSCRIPT")"

# --- Build the findings ----------------------------------------------------------------------
LINES=""
N=0
if [[ -n "$LIVE_ROWS" && -n "$OWN_IDS" ]]; then
    while IFS=$'\t' read -r task_id task_cmd; do
        [[ -n "$task_id" ]] || continue
        printf '%s\n' "$OWN_IDS" | grep -qxF "$task_id" 2>/dev/null || continue
        # The output file the Bash tool named back to this subagent, read from its own transcript -
        # never reconstructed from a guessed temp-dir layout.
        if printf '%s\n' "$OWN_MONITOR_IDS" | grep -qxF "$task_id" 2>/dev/null; then
            N=$(( N + 1 ))
            LINES="$LINES"$'\n'"  [$task_id] (Monitor watch) $task_cmd"$'\n'"      its events reach you only while this turn lasts - wait for them now, or stop the watch"
            continue
        fi
        out_path="$(printf '%s\n' "$OWN_STRINGS" | grep -oE "/[^ \"']*${task_id}\.output" 2>/dev/null | head -1 || true)"
        [[ -n "$out_path" ]] || out_path="(output path not recorded in your transcript - re-read the Bash result that started task ${task_id})"
        N=$(( N + 1 ))
        LINES="$LINES"$'\n'"  [$task_id] $task_cmd"$'\n'"      output so far: $out_path"
    done <<< "$LIVE_ROWS"
fi

AGENT_LINES=""
NA=0
if [[ -n "$LIVE_AGENT_ROWS" && -n "$OWN_AGENT_IDS" ]]; then
    while IFS=$'\t' read -r task_id task_desc; do
        [[ -n "$task_id" ]] || continue
        printf '%s\n' "$OWN_AGENT_IDS" | grep -qxF "$task_id" 2>/dev/null || continue
        NA=$(( NA + 1 ))
        AGENT_LINES="$AGENT_LINES"$'\n'"  [$task_id] $task_desc"
    done <<< "$LIVE_AGENT_ROWS"
fi

[[ "$N" -gt 0 || "$NA" -gt 0 ]] || _pass   # every live task belongs to someone else

REASON=""
if [[ "$N" -gt 0 ]]; then
REASON="Unwakeable-wait gate: you are a DISPATCHED agent and this turn is ending with ${N} background shell command(s) or Monitor watch(es) you started still running. Ending your turn ENDS your dispatch - the Bash tool's \"You will be notified when it completes\" and the Monitor tool's \"You will be notified on each event\" lines are written for the root conversation and do NOT hold for you. Nothing resumes a dispatched agent for a background task, so its result is reachable only inside THIS turn, and stopping now discards it.${LINES}

Do ONE of these for EACH command above, before you stop:
1) READ IT NOW - the output file above already holds everything the command has printed so far. Read it, use what is there, and say in your report that the command had not finished.
2) WAIT FOR IT IN THIS TURN - make your VERY NEXT action a FOREGROUND tool call that blocks until the command is finished (never a text-only reply), then read that output file. Repeat the foreground wait as many times as it takes; every response you emit before you hold the result MUST carry a tool call.
3) STOP IT - if you no longer need the result, stop the task (\`TaskStop\` or \`KillShell\` on task id <id> when your toolset has one, otherwise terminate the process from a foreground Bash call), and say so in your report. A Monitor watch has no output file to read: wait for its events in this turn (2) or stop it (3).

Then emit your \`continuation\` block. If the result cannot be obtained inside this turn, report \`status: BLOCKED\`, naming the command and its output path so your caller can pick it up - never a completion claim over a background command you never read."
fi

if [[ "$NA" -gt 0 ]]; then
    [[ -n "$REASON" ]] && REASON="$REASON"$'\n\n'
    REASON="${REASON}Unwakeable-teammate gate: you are a DISPATCHED agent on an unattended surface and this turn is ending with ${NA} teammate(s) you launched asynchronously still running. On this surface nothing wakes a subagent that stopped: the harness marks you complete and each teammate's result goes to the main conversation, never to you.${AGENT_LINES}

Do NOT end your turn. Wait for them IN THIS TURN (snippets/spawner-completion-contract.md R0 move 2, § An async receipt under move 2): keep making tool calls - a bounded sleep in a Bash call, then a look at what has arrived - until each teammate's completion notification reaches you at a tool round, then read its result and clear your R1 barrier. Every response you emit before you hold every result MUST carry a tool call. Your agent-launch tool carries run_in_background here, so launch every later teammate with run_in_background: false (R0 move 2) and its result returns inside your turn. If a teammate cannot finish inside this turn, report \`status: BLOCKED\` naming it - never a completion claim over a result you never read."
fi

jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
exit 0
