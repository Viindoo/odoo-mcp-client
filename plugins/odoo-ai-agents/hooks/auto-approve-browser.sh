#!/usr/bin/env bash
# auto-approve-browser.sh - PermissionRequest hook that auto-approves the
# plugin's browser MCP tools IN-SESSION.
#
# WHY: settings.json written by the SessionStart permission hook only takes
# effect NEXT session - Claude Code finalizes permissions before SessionStart
# fires. So on the very first session after install/update the browser tools
# would still prompt. This PermissionRequest hook closes that window: for a
# tool namespaced to one of THIS plugin's browser MCP servers (derived from
# .mcp.json via browser_prefixes.py, the SSOT) it emits an `allow` decision;
# for anything else it stays silent so the normal prompt flow is untouched.
#
# Contract: read stdin (the PermissionRequest payload as JSON), extract
# tool_name with python3 (NOT jq), and:
#   - ODOO_AI_NO_AUTO_PERMS=1 -> pass-through (exit 0, no output);
#   - tool matches a plugin browser server -> print the allow decision, exit 0;
#   - otherwise -> pass-through (exit 0, no output).
# Never exits non-zero (a hook failure must not break the permission flow).
set -uo pipefail

# Opt-out: respect a user who turned auto-permissioning off.
if [ "${ODOO_AI_NO_AUTO_PERMS:-0}" = "1" ]; then
  exit 0
fi

_input="$(cat)"

# Extract tool_name with python3 (stdlib json, no jq). Empty on any error.
_tool="$(printf '%s' "${_input}" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    name = data.get("tool_name") or ""
    sys.stdout.write(name if isinstance(name, str) else "")
except Exception:
    pass
' 2>/dev/null)"

# No tool name -> nothing to decide, pass through.
[ -n "${_tool}" ] || exit 0

_lib="$(dirname "$0")/../scripts/lib/browser_prefixes.py"

# match exits 0 iff the tool belongs to one of this plugin's browser servers.
if python3 "${_lib}" match "${_tool}" >/dev/null 2>&1; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}'
fi

exit 0
