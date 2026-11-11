#!/usr/bin/env bash
# steer-compaction.sh - PreCompact hook.
#
# Two jobs, both before the context is replaced by a summary:
#   1. STEER. Its stdout is the instruction the harness gives the summarizer: which facts of the
#      working context the summary must keep and which it may drop.
#   2. HAND OVER. It records, for recover-after-compaction.sh, the plugin skills invoked in this
#      session and the run this session owns (hooks/compaction-state.sh), in a small state file
#      under the plugin state root. The post-compaction hook cannot rely on the transcript alone: it
#      is the same session's file but may not yet hold the records of the compaction in progress.
#
# Contract: never blocks a compaction, always exits 0, prints the instruction even when the state
# cannot be recorded (no jq, no state root, unreadable payload or transcript). The text is a fixed
# few hundred bytes, plain stdout (PreCompact stdout is the summarizer's instruction).
set -uo pipefail

_input="$(cat 2>/dev/null || true)"

_text="[odoo-ai-agents] Keep in the summary: (1) every limit, decision or correction the user stated, quoted; (2) the skill, workflow or plan node in progress, its phase and its next step; (3) each file read whose rules still bind the work (contract, guideline, design, brief): its path and the rule it set; (4) every lease token, instance handle, worktree path, branch and open browser page still held; (5) each subagent still running or awaiting a resume: its id and what it owes. Leave out how decisions were reached."

_record_state() {
  command -v jq >/dev/null 2>&1 || return 0
  local sid transcript cwd file
  sid="$(printf '%s' "${_input}" | jq -r '.session_id // empty' 2>/dev/null || true)"
  transcript="$(printf '%s' "${_input}" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
  cwd="$(printf '%s' "${_input}" | jq -r '.cwd // empty' 2>/dev/null || true)"
  [[ -n "${sid}" ]] || return 0
  _hook_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || return 0
  export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${_hook_dir}/..}"
  [[ -r "${_hook_dir}/compaction-state.sh" ]] || return 0
  # shellcheck source=/dev/null
  . "${_hook_dir}/compaction-state.sh"
  file="$(_cs_file "${sid}")"
  [[ -n "${file}" ]] || return 0
  _cs_write "${file}" "$(_cs_build_state "${transcript}" "${cwd}")"
}
_record_state >/dev/null 2>&1 || true

printf '%s\n' "${_text}"
exit 0
