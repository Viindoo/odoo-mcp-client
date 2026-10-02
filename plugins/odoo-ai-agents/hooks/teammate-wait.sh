# teammate-wait.sh - SOURCED helper (not a hook): the ONE implementation of "which teammates did THIS
# subagent launch asynchronously that are still running, and will a stop wake it for them". Two
# SubagentStop gates read it and must never disagree:
#   - enforce-background-wait.sh: on an UNATTENDED surface a stop with such a teammate is refused -
#     nothing wakes the stopped subagent there, so the teammate's result goes to the main session.
#   - enforce-teardown.sh: on any OTHER surface the same stop is a WAIT, not the end of the dispatch
#     (snippets/spawner-completion-contract.md R0 move 3 - the subagent is woken once per teammate),
#     so a lease the subagent still holds for the work it resumes is not ordered released there.
# If the two drifted, a stop could be refused as unwakeable and also let through as a wait, or a
# coordinator waiting for its teammate could be ordered to destroy the instance it is waiting to use.
#
# Every function prints to stdout and prints nothing on any failure (no jq, unreadable transcript,
# parse error); both callers treat "nothing" as "no teammate" and fall back to their own default.

# A 5s bound on every host (stock macOS has no `timeout`): scripts/lib/run_bounded.sh.
# shellcheck source=../scripts/lib/run_bounded.sh
. "${BASH_SOURCE[0]%/*}/../scripts/lib/run_bounded.sh" 2>/dev/null || true
declare -F run_bounded >/dev/null 2>&1 || run_bounded() { shift; "$@"; }

# Returns 0 on an UNATTENDED surface - the one that leaves a stopped subagent unwoken for an agent
# child: CLAUDE_CODE_SESSION_ATTENDED=0, or that variable unset with CLAUDE_CODE_ENTRYPOINT=sdk-cli
# (measured on `claude -p`). ATTENDED=1 (interactive) or neither signal -> returns 1.
_tw_unattended() {
  [[ "${CLAUDE_CODE_SESSION_ATTENDED-}" == "0" ]] && return 0
  [[ -z "${CLAUDE_CODE_SESSION_ATTENDED-}" && "${CLAUDE_CODE_ENTRYPOINT-}" == "sdk-cli" ]] && return 0
  return 1
}

# $1 = the SubagentStop payload, $2 = the stopping subagent's own agent_id. Prints one
# "<id>\t<agent_type>: <description>" row per `background_tasks` entry of `type: "subagent"` with
# `status: "running"`, the stopping subagent's own entry excluded. `background_tasks` is
# SESSION-wide: these rows are not yet this subagent's - _tw_own_live_teammates decides that.
_tw_live_agent_rows() {
  printf '%s' "$1" | jq -r --arg self "$2" '
    .background_tasks[]?
    | select((.type // "") == "subagent")
    | select((.status // "") == "running")
    | select(((.id // "") | tostring) != $self)
    | [((.id // "") | tostring),
       ((((.agent_type // "agent") | tostring) + ": " + ((.description // "") | tostring)) | gsub("[\n\t]"; " "))]
    | @tsv' 2>/dev/null || true
}

# $1 = the subagent's OWN transcript (agent_transcript_path - never the session transcript). Prints
# the agent ids it launched asynchronously, read only from strings that ARE an async launch receipt
# ("Async agent launched successfully ... agentId: <id>"), so an agentId merely mentioned elsewhere
# never counts. Recursive descent on purpose: the receipt lives in a harness-authored tool_result
# whose nesting is not ours to assume.
_tw_async_launched_ids() {
  [[ -n "${1:-}" && -f "$1" ]] || return 0
  run_bounded 5 jq -rR '
    fromjson? | .. | strings
    | select(test("Async agent launched successfully"))
    | scan("agentId: ([A-Za-z0-9_-]+)")[]' "$1" 2>/dev/null \
    | grep -vE '^$' | sort -u || true
}

# $1 = payload, $2 = own agent_id, $3 = own transcript. Prints the _tw_live_agent_rows rows whose id
# this subagent's own async launch receipt names: the teammates IT launched that are still running.
_tw_own_live_teammates() {
  local rows ids task_id task_desc
  rows="$(_tw_live_agent_rows "$1" "$2")"
  [[ -n "$rows" ]] || return 0
  ids="$(_tw_async_launched_ids "$3")"
  [[ -n "$ids" ]] || return 0
  while IFS=$'\t' read -r task_id task_desc; do
    [[ -n "$task_id" ]] || continue
    printf '%s\n' "$ids" | grep -qxF "$task_id" 2>/dev/null || continue
    printf '%s\t%s\n' "$task_id" "$task_desc"
  done <<< "$rows"
}
