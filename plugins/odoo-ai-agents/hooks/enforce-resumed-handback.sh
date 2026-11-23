#!/usr/bin/env bash
# enforce-resumed-handback.sh - SubagentStop gate for an agent RESUMED by its launcher.
#
# WHY: a subagent that reports through SubagentHandback delivers ONE report per dispatch, and its
# launcher can resume it afterwards with a new request (a message sent to the stopped agent). The
# answer to that request reaches the launcher only through a SubagentHandback call: plain text
# written at the end of the turn reaches nobody, and the launcher waits for a message that never
# arrives. An agent that finished its first dispatch with a hand-back has no reason to expect the
# second turn to differ, so it ends the resumed turn in text - and the answer is lost.
#
# WHAT IT DOES: blocks the stop ONCE per request with a reason that says what reaches the launcher:
# call SubagentHandback with the answer; if the call is refused as already delivered, send the
# answer with SendMessage as the refusal says, then stop. A request the agent already answered is
# never asked for again: the reason says not to send a second time.
#
# WHEN (hooks/final-report.sh _resumed_without_report - the SSOT, with the definition of a launcher
# request): the agent delivered a report through SubagentHandback, its launcher then sent a new
# request (origin kind `coordinator`, or a `peer` message that is neither a hand-back nor from an
# agent this agent launched), and at the stop of the turn that request started no report has been
# delivered since - unless a handback refused as already delivered was followed by a SendMessage,
# or a peer request was followed by a SendMessage addressed to its sender.
#
# WHEN NOT: the stop of a later turn - a message (task notification, human message, hand-back,
# request) that reached the agent after it had stopped starts a new turn, and that turn is judged
# for its own request only; a request this gate already blocked once (its block reason, led by
# _RESUMED_GATE_MARK, is in the transcript); an agent whose report travels as its final text (it
# never delivered a SubagentHandback, so there is nothing to resume); a first dispatch. A message
# that reaches the agent while it still works the request (a queued background-task notification
# or child hand-back) does not end that turn, so the stop is still judged.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON has agent_transcript_path (the subagent's own
# transcript - the one read here), transcript_path (the whole session's) + stop_hook_active.
#   - Block form: {"decision":"block","reason":"..."} on stdout; no other output.
#   - Bounded: a stop that a hook already continued (stop_hook_active=true) passes, and the record
#     this gate's block leaves in the transcript (a "Stop hook feedback:" user record, or a
#     hook_blocking_error attachment with hookEvent SubagentStop) marks the request as blocked, so
#     the block is given at most once per request, across stops, and can never loop.
#   - Degrades to exit 0 on any uncertainty (no jq, no transcript, parse error).

set -uo pipefail

_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

[[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)" == "true" ]] && _pass

_FR_LIB="${BASH_SOURCE[0]%/*}/final-report.sh"
[[ -r "$_FR_LIB" ]] || _pass
# shellcheck source=/dev/null
. "$_FR_LIB"

TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass

ASKER="$(_resumed_without_report "$TRANSCRIPT")"
[[ -n "$ASKER" ]] || _pass

if [[ "$ASKER" == peer\ * && -n "${ASKER#peer }" ]]; then
  FALLBACK="send your answer with SendMessage to ${ASKER#peer } (the agent that sent you the request)"
else
  FALLBACK="send your answer with SendMessage to main"
fi

REASON="${_RESUMED_GATE_MARK} Your launcher sent you a new request after your earlier report was delivered, and this turn is ending without a SubagentHandback delivered for it. Plain text you end a turn with is not delivered to your launcher: it receives your answer to this request only through a SubagentHandback call. If you have not answered this request yet, call SubagentHandback now with your answer - your complete report, its continuation block included. If that call is refused because your report was already delivered, ${FALLBACK}, as the refusal says, then stop. If you already answered this request with a message, do not send it again: stop."

jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
exit 0
