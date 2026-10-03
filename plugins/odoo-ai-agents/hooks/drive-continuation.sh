#!/usr/bin/env bash
# drive-continuation.sh - Stop ADVISORY nudge for the drive-to-done loop.
#
# WHY: if the main agent ends its turn while a run is still NEEDS_NEXT, remind it (and the
# human) that the run is unfinished and can be advanced. This keeps drive-to-done resilient
# WITHOUT coercion.
#
# HARD CONTRACT: this hook NEVER blocks the main agent's turn-end. It emits
#   {continue:true, systemMessage:...} only - an advisory line. (Using {decision:"block"} here
#   would trap the main agent, which is forbidden.) The human + main agent keep the right to
#   stop at any time. Self-gates to silence when no run is active; loop-safe via stop_hook_active.
#   Only THIS session's run counts (hooks/run-ownership.sh): the record this session wrote last. A
#   NEEDS_NEXT record that another session - live or long dead - left in the same state dir is not
#   this session's unfinished run; when this session drives several, the one it wrote last is named.
#   Said ONCE per run state per context window: while the same run sits on the same node, the
#   reminder already in the transcript since the last compaction is not repeated on every later
#   turn end (hooks/advice-once.sh); a run that moves to another node is a new reminder.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# Loop-safe: if we already nudged on this stop cycle, stay quiet.
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass

# The state dir and its NEEDS_NEXT records, and whose run each is: hooks/run-ownership.sh (the ONE
# copy remind-delegate.sh and parse-continuation.sh share). The dir is resolved FROM this hook's own
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

MSG="Run '$run_id' is still NEEDS_NEXT (next node: $cursor). If you intend to keep going, advance it via run-harness (read $active_run). To stop, say so - this is only a reminder, not a block."

# Already in the context (the same run on the same node) -> stay quiet. Helper unreadable -> emit.
if [[ -r "$_HOOK_DIR/advice-once.sh" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/advice-once.sh"
  _advice_seen "$TRANSCRIPT" "$MSG" && _pass
fi

jq -cn --arg m "$MSG" '{continue:true, systemMessage:$m}'
exit 0
