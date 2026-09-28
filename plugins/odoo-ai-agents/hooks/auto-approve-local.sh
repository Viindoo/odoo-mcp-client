#!/usr/bin/env bash
# auto-approve-local.sh - PermissionRequest hook that auto-approves this
# plugin's LOCAL (non-browser) MCP tools IN-SESSION - the odoo-local server's
# lease/instance/catalog tools (scripts/mcp/odoo_local_server.py).
#
# WHY A SEPARATE HOOK FROM auto-approve-browser.sh: odoo-local's tools are NOT a
# browser-automation family - browser_prefixes.py / plugin_mcp_servers.py
# deliberately keep LOCAL_SERVERS out of the browser permission surface, because
# some of these tools are destructive (`lease_release`, an applied `lease_gc`
# can stop a process group and drop a database) - nothing like clicking through
# a page. Blanket-approving them as "browser" tools would be a category error,
# so this is a purpose-built policy for this one server family.
#
# POLICY: auto-allow every `mcp__plugin_<plugin>_odoo-local__*` tool call EXCEPT
# `lease_gc` invoked with `tool_input.dry_run` explicitly `false` (an APPLY gc -
# the one call in this surface that can actually reclaim/destroy something). A
# dry-run gc (the documented default) is a read-only listing and is auto-allowed
# like every other local tool; only an explicit `dry_run:false` falls through to
# the normal human-approval prompt.
#
# Contract: read stdin (the PermissionRequest payload as JSON), and:
#   - ODOO_AI_NO_AUTO_PERMS=1 -> pass-through (exit 0, no output);
#   - tool_name is not namespaced to a LOCAL server (scripts/lib/plugin_mcp_servers.py
#     LOCAL_SERVERS, the SSOT) -> pass-through (exit 0, no output);
#   - tool is `lease_gc` AND tool_input.dry_run is exactly `false` -> pass-through
#     (fall through to the human prompt);
#   - otherwise -> print the allow decision, exit 0.
# Never exits non-zero (a hook failure must not break the permission flow).
set -uo pipefail

# Opt-out: respect a user who turned auto-permissioning off.
if [ "${ODOO_AI_NO_AUTO_PERMS:-0}" = "1" ]; then
  exit 0
fi

_input="$(cat)"
_lib_dir="$(cd "$(dirname "$0")/../scripts/lib" 2>/dev/null && pwd)"

# All parsing + the policy decision live in one python3 invocation (stdlib json,
# no jq): load plugin_mcp_servers.py by path (the SSOT for LOCAL_SERVERS + the
# plugin-namespaced tool-prefix logic - the same sibling-import pattern
# browser_prefixes.py and gen_mcp_manifests.py use), split the tool name against
# it, and apply the lease_gc/dry_run exception. Prints the allow decision only
# when the call should be auto-approved; prints nothing (pass-through) for
# every other case, including any parse error.
_decision="$(printf '%s' "${_input}" | python3 -c '
import importlib.util
import json
import sys

lib_dir = sys.argv[1]

try:
    spec = importlib.util.spec_from_file_location(
        "plugin_mcp_servers", f"{lib_dir}/plugin_mcp_servers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
except Exception:
    sys.exit(0)

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name")
if not isinstance(tool, str) or not tool:
    sys.exit(0)

server, short = mod.split_local_tool(tool)
if server is None:
    sys.exit(0)

if short == "lease_gc":
    tool_input = data.get("tool_input")
    if isinstance(tool_input, dict) and tool_input.get("dry_run") is False:
        sys.exit(0)  # apply-mode gc: fall through to the normal human prompt

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "allow"},
    }
}))
' "${_lib_dir}" 2>/dev/null)"

if [ -n "${_decision}" ]; then
  printf '%s\n' "${_decision}"
fi

exit 0
