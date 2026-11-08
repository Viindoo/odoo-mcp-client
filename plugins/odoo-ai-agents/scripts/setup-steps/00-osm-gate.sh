#!/usr/bin/env bash
# 00-osm-gate.sh - Gate: verify the Odoo Semantic MCP server is registered and
# reachable BEFORE the rest of setup runs.
#
# This is a REGISTRY + REACHABILITY check: is the server registered - by the
# odoo-semantic-mcp plugin (enabled, with its mcp_url option set) or by hand
# (an `odoo-semantic` entry in ~/.claude.json) - and does its /health endpoint
# answer? Which of the two is decided by scripts/lib/osm_registration.py. It is
# NOT a session-load check: whether the mcp__plugin_odoo-semantic-mcp_odoo-semantic__* tools
# are actually callable in the CURRENT session can only be told by the AI agent
# trying to call one. The setup command's Gate #1 does that authoritative check;
# this script is the shell-level fallback (useful in non-interactive runs).
#
# CONFIG (env overrides):
#   CLAUDE_CONFIG   path to the hand-registration file (default $CLAUDE_CONFIG_DIR/.claude.json, else ~/.claude.json)
#
# Subcommands: describe | check | apply
#   check  -> exit 0 if a server is registered AND (if curl is present)
#            its server answers; exit 1 otherwise.
#   apply  -> no-op that prints how to connect. It never runs connect for you.

set -euo pipefail

cmd_describe() {
    echo "Verify the Odoo Semantic MCP server is connected (run /odoo-semantic-mcp:connect first if not)"
}

# Print the server's base URL (without the trailing /mcp), or nothing. Never prints the API key.
_registered_url() {
    local lib
    lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib"
    python3 "$lib/osm_registration.py" 2>/dev/null |
        sed -n 's/^OSM_URL=//p' || true
}

cmd_check() {
    # 1. Registered by the plugin or by hand?
    local url
    url="$(_registered_url)"
    [[ -n "$url" ]] || return 1
    # 2. Reachable? Only probe when curl is available; otherwise trust the
    #    registration (the AI-level Gate #1 still does the real check).
    command -v curl >/dev/null 2>&1 || return 0
    curl -sf -o /dev/null --max-time 5 "${url}/health" 2>/dev/null || return 1
}

cmd_apply() {
    # Never connects for the user; just explains what to do.
    if cmd_check; then
        echo "ok Odoo Semantic MCP server is registered and reachable."
        echo "   If its tools are still not callable, run /reload-plugins"
        echo "   (it restarts the plugin's server)."
        return 0
    fi
    echo "x Odoo Semantic MCP server is not connected." >&2
    echo "   1. Run /odoo-semantic-mcp:connect (about one minute)." >&2
    echo "   2. Run /reload-plugins (it restarts the plugin's server)." >&2
    echo "   3. Re-run /odoo-ai-agents:odoo-setup." >&2
    echo "   Setup needs the indexing backend connected before it can proceed." >&2
    return 1
}

# --- interpreter preflight ------------------------------------------------------------------
# This gate reads the Claude settings through python with stderr suppressed, so a broken
# interpreter would read as "no MCP server configured" - a confident wrong answer. It needs only
# `json`, NOT tomllib: refusing a host this step would have served is the same defect inverted.
# SSOT: scripts/lib/require_python.sh.
_GATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REQ_PY="$_GATE_DIR/../lib/require_python.sh"
if [[ -r "$_REQ_PY" ]]; then
    # shellcheck source=/dev/null
    . "$_REQ_PY"
    case "${1:-}" in
        describe|-h|--help|"") ;;
        *) require_python3 "$(basename "$0") ${1:-}" json || exit 2 ;;
    esac
fi

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
