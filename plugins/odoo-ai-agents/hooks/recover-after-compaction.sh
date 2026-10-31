#!/usr/bin/env bash
# recover-after-compaction.sh - SessionStart hook for the `compact` source only.
#
# A compaction replaces the transcript with a summary; the harness re-reads only the five files
# read most recently. Every other contract, guideline, brief and design file the agent read is
# gone, and nothing in the new window says so. This notice says so, and names the reading map to
# re-read from before the next write.
#
# Contract: context only, never blocks, always exits 0; silent on any other source (the matcher
# in hooks.json already limits it to `compact`; the check below keeps it true on a harness that
# ignores matchers). No opt-out: the notice is a few hundred bytes, said once per compaction.
set -uo pipefail

_input="$(cat 2>/dev/null || true)"
_source=""
if command -v jq >/dev/null 2>&1; then
  _source="$(printf '%s' "${_input}" | jq -r '.source // empty' 2>/dev/null || true)"
else
  case "${_input}" in *'"source"'*'"compact"'*) _source="compact" ;; esac
fi
[ "${_source}" = "compact" ] || exit 0

_plugin_root="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd -P)"
_map="${_plugin_root}/snippets/read-before-act.md"
[ -f "${_map}" ] || exit 0

_ctx="[odoo-ai-agents] The context was just compacted. Of the files read before it, only the five read most recently are back, long ones cut short; every other contract, guideline, brief and design file is gone, and the summary above is the only record of what they said. Before the next write of a class of work, re-read its row of ${_map} § 1 (for code: the coding-guidelines INDEX of the series and the files its file-type rows name, plus the comment contract; for docs or marketing: their contracts; before a launch: the dispatch brief and the model-tier table). A lease, instance handle, worktree or open page the summary names is still held: release it through the owning skill when the run ends. A limit the human stated applies as the summary quotes it."

if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "${_ctx}" \
    '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
else
  printf '%s\n' "${_ctx}"
fi
exit 0
