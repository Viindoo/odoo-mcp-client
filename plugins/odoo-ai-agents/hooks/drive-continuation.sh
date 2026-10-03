#!/usr/bin/env bash
# drive-continuation.sh - Stop nudge for the drive-to-done loop.
#
# WHY: if the main agent ends its turn while the run THIS session drives is still NEEDS_NEXT, tell
# the MODEL so it advances the run on its own instead of waiting for the human to type "continue".
#
# CHANNEL: Stop `hookSpecificOutput.additionalContext`. It is the Stop output the model reads: the
# harness records it in the transcript as a `hook_additional_context` attachment and runs ONE more
# model turn with it. A Stop `systemMessage` never reaches the model (it is recorded as
# `hook_system_message` and the turn simply ends; both measured on Claude Code 2.1.288).
# `decision: "block"` is not used: a block is the harness refusing the stop, and the model must stay
# free to remain stopped for a legitimate pause - additionalContext informs the extra turn without
# ordering it. A model that does stay stopped ends that extra turn by restating, in one line, what
# it waits for: in a headless (`claude -p` / SDK) session the caller receives only the last message,
# so a turn ending on anything else would replace the pending question it stopped on.
#
# HARD CONTRACT: the reminder never traps the main agent. It costs one model turn per run state;
# the text names the legitimate reasons to stay stopped, and the model keeps the right to stop.
#   - Only THIS session's run counts (hooks/run-ownership.sh): the record this session wrote last. A
#     NEEDS_NEXT record that another session - live or long dead - left in the same state dir is not
#     this session's unfinished run; when this session drives several, the one it wrote last is named.
#   - Said ONCE per run state per context window (hooks/advice-once.sh): while the same run sits on
#     the same node, the reminder already in the transcript since the last compaction is not
#     repeated; a run that moves to another node is a new reminder. THAT is the loop guard: the
#     harness runs one more turn for EVERY Stop that emits additionalContext (measured: a hook
#     that emitted six times in a row got six extra turns), so a model that stays stopped is
#     reminded once and then left alone. `stop_hook_active`
#     is NOT the guard: it stays true on every stop of a hook-continued turn, so honouring it would
#     let the run advance one node per human prompt - the very stall this hook exists to end. It
#     is honoured only when there is no dedup - no readable transcript or helper - so a missing
#     guard never turns into an endless chain of reminders.
#   - Silent while the payload's `background_tasks` still lists a running task whose completion
#     wakes the session - a dispatched agent on every surface, a background shell or Monitor only on
#     an attended one: that turn end is a wait, not an abandoned run. In an unattended session a
#     background shell wakes nothing, so it does not silence the reminder.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# A turn end that WAITS for something whose completion wakes the session is not an abandoned run:
# a running dispatched agent (type subagent) on every surface, a running background shell or Monitor
# only on an attended one - in an unattended (`claude -p` / SDK) session nothing a background shell
# does wakes it, and a never-ending one (a dev server, a Monitor watch) would otherwise silence the
# reminder for the whole session. The surface test is hooks/teammate-wait.sh _tw_unattended;
# unreadable -> read as attended (the older, quieter behaviour).
_WAKE_TYPES='["subagent","shell"]'
if [[ -r "${BASH_SOURCE[0]%/*}/teammate-wait.sh" ]]; then
  # shellcheck source=/dev/null
  . "${BASH_SOURCE[0]%/*}/teammate-wait.sh"
  _tw_unattended && _WAKE_TYPES='["subagent"]'
fi
RUNNING_TASKS="$(printf '%s' "$INPUT" | jq -r --argjson t "$_WAKE_TYPES" '[.background_tasks[]? | objects | select((.status // "") == "running") | select(((.type // "") as $k | $t | index($k)) != null)] | length' 2>/dev/null || echo 0)"
[[ "$RUNNING_TASKS" =~ ^[0-9]+$ && "$RUNNING_TASKS" -gt 0 ]] && _pass

# The state dir and its NEEDS_NEXT records, and whose run each is: hooks/run-ownership.sh (the ONE
# copy remind-delegate.sh shares). The dir is resolved FROM this hook's own
# project cwd, so each worktree sees only its own records. Unreadable shared helper -> pass, the
# plugin-wide convention.
_HOOK_DIR="${BASH_SOURCE[0]%/*}"
[[ -r "$_HOOK_DIR/run-ownership.sh" ]] || _pass
# shellcheck source=/dev/null
. "$_HOOK_DIR/run-ownership.sh"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
RUN_DIR="$(_run_state_dir "$CWD")"
needs_next=()
while IFS= read -r rf; do [[ -n "$rf" ]] && needs_next+=("$rf"); done < <(_needs_next_runs "$RUN_DIR")
[[ ${#needs_next[@]} -gt 0 ]] || _pass

# Which one is THIS session's unfinished run: the one it wrote last. When ownership cannot be told
# (no readable transcript, a jq that cannot run the scan) the reminder keeps its older rule - exactly
# one NEEDS_NEXT record is the run; more is ambiguous and stays silent.
TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
owned="$(_session_owned_runs "$TRANSCRIPT" "${needs_next[@]}")"
if [[ $? -eq 2 ]]; then
  [[ ${#needs_next[@]} -eq 1 ]] || _pass
  active_run="${needs_next[0]}"
else
  [[ -n "$owned" ]] || _pass
  active_run="${owned%%$'\n'*}"
fi
# A run record without run_id is still named: by its file, run-<id>.json (the run-harness naming),
# never as '?' - a reminder that cannot say WHICH run is unfinished is noise.
_file_id="${active_run##*/run-}"; _file_id="${_file_id%.json}"
run_id="$(jq -r --arg f "$_file_id" '.run_id // $f' "$active_run" 2>/dev/null || printf '%s' "$_file_id")"
cursor="$(jq -r '.cursor // "?"' "$active_run" 2>/dev/null || echo '?')"

MSG="Run '$run_id' is still NEEDS_NEXT (next node: $cursor) and your turn just ended. Unless you stopped on purpose - an L2 gate is waiting for the user's decision, the run is BLOCKED or NEEDS_CONTEXT, or the user asked you to stop or pause - read $active_run and keep advancing the run via run-harness now, without asking the user to say continue. If you did stop on purpose, stay stopped and end with one line that restates what you are waiting for (the pending question or decision, or the blocker), because a caller that reads only your last message must still get it."

# Already in the context (the same run on the same node) -> stay quiet: the loop guard. Without a
# readable transcript or the helper there is no dedup (advice-once.sh fails open to "not seen"), so
# fall back to stop_hook_active and never remind twice in one hook-continued chain.
if [[ -r "$_HOOK_DIR/advice-once.sh" && -n "$TRANSCRIPT" && -r "$TRANSCRIPT" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/advice-once.sh"
  _advice_seen "$TRANSCRIPT" "$MSG" && _pass
else
  [[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo true)" == "false" ]] || _pass
fi

jq -cn --arg m "$MSG" '{hookSpecificOutput: {hookEventName: "Stop", additionalContext: $m}}'
exit 0
