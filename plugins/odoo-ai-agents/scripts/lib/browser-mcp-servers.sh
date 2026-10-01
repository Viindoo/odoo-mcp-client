#!/usr/bin/env bash
# browser-mcp-servers.sh - shell API over scripts/lib/browser_mcp_servers.py, the SSOT for the
# six browser MCP families' pins, flags and state-root flags. SOURCED (not executed) by the setup
# steps 10-browser-mcp.sh (Codex/Gemini), 12-browser-mcp-optin.sh (Claude user scope) and
# 20-browser-deps.sh (package + Chromium pre-install). Every value comes from the python SSOT;
# nothing is pinned here.
#
# Sourcing needs no interpreter: when python3 cannot run, the values below are empty and the
# caller's own require_python3 preflight reports it before any of them is used.
#
#   BROWSER_MCP_{CHROME,PLAYWRIGHT,PAGECAST}_PIN   exact package pins (env-overridable)
#   BROWSER_MCP_PLAYWRIGHT_CORE_VERSION            playwright-core the pinned @playwright/mcp uses
#   BROWSER_MCP_EAGER_SERVER                       the family bundled in .mcp.json
#   BROWSER_MCP_ALL_SERVERS / BROWSER_MCP_OPTIN_SERVERS   family arrays
#   browser_mcp_npx_args <server>   pin + base flags, one per line (no state-root flags)
#   browser_mcp_spec <server>       JSON {"command","args","env"} with resolved state-root flags

_BROWSER_MCP_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/browser_mcp_servers.py"

# The pin overrides are passed through explicitly so an unexported shell assignment still wins.
_browser_mcp_py() {
    BROWSER_MCP_CHROME_PIN="${BROWSER_MCP_CHROME_PIN:-}" \
    BROWSER_MCP_PLAYWRIGHT_PIN="${BROWSER_MCP_PLAYWRIGHT_PIN:-}" \
    BROWSER_MCP_PAGECAST_PIN="${BROWSER_MCP_PAGECAST_PIN:-}" \
        python3 "$_BROWSER_MCP_PY" "$@"
}

_browser_mcp_lines_into() {
    # $1 = array name, rest = SSOT CLI args. Portable to bash 3.2 (no mapfile).
    local __name="$1" __line __out
    shift
    __out="$(_browser_mcp_py "$@" 2>/dev/null || true)"
    eval "$__name=()"
    while IFS= read -r __line; do
        if [[ -n "$__line" ]]; then eval "$__name+=(\"\$__line\")"; fi
    done <<<"$__out"
    return 0
}

browser_mcp_npx_args() { _browser_mcp_py npx-args "$1"; }
browser_mcp_spec() { _browser_mcp_py spec "$1"; }

BROWSER_MCP_CHROME_PIN="$(_browser_mcp_py pin chrome-devtools 2>/dev/null || true)"
BROWSER_MCP_PLAYWRIGHT_PIN="$(_browser_mcp_py pin playwright 2>/dev/null || true)"
BROWSER_MCP_PAGECAST_PIN="$(_browser_mcp_py pin pagecast 2>/dev/null || true)"
BROWSER_MCP_PLAYWRIGHT_CORE_VERSION="$(_browser_mcp_py playwright-core-version 2>/dev/null || true)"
BROWSER_MCP_EAGER_SERVER="$(_browser_mcp_py servers eager 2>/dev/null || true)"
_browser_mcp_lines_into BROWSER_MCP_ALL_SERVERS servers all
_browser_mcp_lines_into BROWSER_MCP_OPTIN_SERVERS servers optin
