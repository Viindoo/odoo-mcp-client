#!/usr/bin/env bash
# 00-osm-gate.sh - Gate: verify the Odoo Semantic MCP server is registered and
# reachable BEFORE the rest of setup runs.
#
# This is a REGISTRY + REACHABILITY check (is `odoo-semantic` declared in
# ~/.claude.json, and does its /health endpoint answer?). It is NOT a
# session-load check: Claude Code does not hot-reload MCP servers, so whether
# the mcp__odoo-semantic__* tools are actually callable in the CURRENT session
# can only be told by the AI agent trying to call one. The setup command's
# Gate #1 does that authoritative check; this script is the shell-level
# fallback (useful in non-interactive runs) and a clear, documented dependency.
#
# CONFIG (env overrides):
#   CLAUDE_CONFIG   path to the MCP registry (default ~/.claude.json)
#
# Subcommands: describe | check | apply
#   check  -> exit 0 if `odoo-semantic` is registered AND (if curl is present)
#            its server answers; exit 1 otherwise.
#   apply  -> no-op that prints how to connect. It never runs connect for you.

set -euo pipefail

CLAUDE_CONFIG="${CLAUDE_CONFIG:-$HOME/.claude.json}"

cmd_describe() {
    echo "Verify the Odoo Semantic MCP server is connected (run /odoo-semantic-mcp:connect first if not)"
}

# Print the server's base URL (without the trailing /mcp) from the registry,
# or nothing. Never prints the API key.
_registered_url() {
    [[ -f "$CLAUDE_CONFIG" ]] || return 0
    python3 - "$CLAUDE_CONFIG" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)
srv = (data.get("mcpServers") or {}).get("odoo-semantic")
if not isinstance(srv, dict):
    sys.exit(0)
url = str(srv.get("url") or srv.get("serverUrl") or "")
# str.removesuffix is Python 3.9+. This runs on the user's SYSTEM python3,
# which may be 3.8 (where removesuffix raises AttributeError, gets swallowed
# by `2>/dev/null || true`, and the gate falsely reports "not connected" and
# loops the user). Use version-agnostic slicing instead.
u = url.rstrip("/")
print(u[:-4] if u.endswith("/mcp") else u)
PY
}

cmd_check() {
    # 1. Registered in the MCP registry?
    local url
    url="$(_registered_url)"
    [[ -n "$url" ]] || return 1
    # 2. Reachable? Only probe when curl is available; otherwise trust the
    #    registry (the AI-level Gate #1 still does the real check).
    command -v curl >/dev/null 2>&1 || return 0
    curl -sf -o /dev/null --max-time 5 "${url}/health" 2>/dev/null
}

cmd_apply() {
    # Never connects for the user; just explains what to do.
    if cmd_check; then
        echo "ok Odoo Semantic MCP server is registered and reachable."
        echo "   If its tools are still not callable, restart your session"
        echo "   (Claude Code does not hot-reload MCP servers)."
        return 0
    fi
    echo "x Odoo Semantic MCP server is not connected." >&2
    echo "   1. Run /odoo-semantic-mcp:connect (about one minute)." >&2
    echo "   2. Restart Claude Code, then open a NEW session." >&2
    echo "   3. Re-run /odoo-semantic-skills:setup." >&2
    echo "   Setup needs the indexing backend connected before it can proceed." >&2
    return 1
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
