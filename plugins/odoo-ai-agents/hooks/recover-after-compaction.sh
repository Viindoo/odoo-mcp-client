#!/usr/bin/env bash
# recover-after-compaction.sh - SessionStart hook for the `compact` source only.
#
# A compaction replaces the transcript with a summary: files read by path are gone unless the
# summary quotes them, and a skill invoked long ago may no longer be loaded. This notice says so
# and names what to reload: the skill in progress, the other plugin skills used earlier, and the
# run in progress. It names skills by invocable name only, never by file.
#
# WHERE THE FACTS COME FROM, in order: the state file steer-compaction.sh (PreCompact) wrote for
# this session; else the session transcript read here (hooks/compaction-state.sh); else the static
# sentences alone (no jq, an unreadable or empty payload, no usable transcript). A sentence whose
# fact is unknown is omitted.
#
# "Skill in progress" is the skill of the run's current node when a run is in progress and that
# node is a skill, else the most recently invoked plugin skill.
#
# Contract: context only, never blocks, always exits 0; silent on any other source (the matcher
# in hooks.json already limits it to `compact`; the check below keeps it true on a harness that
# ignores matchers). The notice stays well under the harness cut on any input: the skill list is
# capped and the run's approach is truncated.
set -uo pipefail

_input="$(cat 2>/dev/null || true)"
_source=""
if command -v jq >/dev/null 2>&1; then
  _source="$(printf '%s' "${_input}" | jq -r '.source // empty' 2>/dev/null || true)"
else
  case "${_input}" in *'"source"'*'"compact"'*) _source="compact" ;; esac
fi
[ "${_source}" = "compact" ] || exit 0

_head="[odoo-ai-agents] The context was just compacted. Files read by path before it are gone unless the summary quotes them, and a skill invoked long ago may no longer be loaded."
_tail="Re-read the exact text of any file a decision depends on before the next write. A lease, instance handle, worktree or open page the summary names is still held: release it through the owning skill when the run ends. A limit the human stated applies as the summary quotes it."

_state=""
if command -v jq >/dev/null 2>&1; then
  _hook_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
  export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${_hook_dir}/..}"
  if [ -r "${_hook_dir}/compaction-state.sh" ]; then
    # shellcheck source=/dev/null
    . "${_hook_dir}/compaction-state.sh"
    _sid="$(printf '%s' "${_input}" | jq -r '.session_id // empty' 2>/dev/null || true)"
    _state="$(_cs_read "$(_cs_file "${_sid}")")"
    if [ -z "${_state}" ]; then
      _transcript="$(printf '%s' "${_input}" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
      _cwd="$(printf '%s' "${_input}" | jq -r '.cwd // empty' 2>/dev/null || true)"
      _state="$(_cs_build_state "${_transcript}" "${_cwd}")"
    fi
  fi
fi

_ctx="${_head} ${_tail}"
if [ -n "${_state}" ]; then
  _built="$(printf '%s' "${_state}" | jq -r --arg head "${_head}" --arg tail "${_tail}" --argjson cap "${_CS_MAX_OTHER_SKILLS:-12}" '
    (.skills // [] | map(select(type == "string"))) as $sk
    | (.run | if type == "object" then . else null end) as $run
    | (if $run != null and (($run.skill // "") != "") then $run.skill else ($sk | last // "") end) as $cur
    | ($sk | map(select(. != $cur)) | .[-$cap:]) as $other
    | [ $head,
        (if $cur != "" then "Skill in progress: \($cur) - invoke it again before continuing its work." else empty end),
        (if ($other | length) > 0 then "Other plugin skills used earlier: \($other | join(", ")) - invoke one again when you return to its work." else empty end),
        (if $run != null and (($run.id // "") != "") and (($run.path // "") != "") then
           "Run in progress: \($run.id) at \($run.path)"
           + (if ($run.cursor // "") != "" then ", node \($run.cursor)" else "" end)
           + (if ($run.approach // "") != "" then " (\($run.approach))" else "" end)
           + " - read the run file before the next step."
         else empty end),
        $tail ] | join(" ")' 2>/dev/null || true)"
  [ -n "${_built}" ] && _ctx="${_built}"
fi

if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "${_ctx}" \
    '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
else
  printf '%s\n' "${_ctx}"
fi
exit 0
