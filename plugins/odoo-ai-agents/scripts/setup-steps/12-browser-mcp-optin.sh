#!/usr/bin/env bash
# 12-browser-mcp-optin.sh - Wire the FIVE opt-in browser MCP families into
# Claude Code at USER scope, on demand.
#
# Only ONE browser family is EAGER: the plugin's bundled .mcp.json ships the
# headless `chrome-devtools`, which Claude auto-loads on install. The other five
# families - `chrome-devtools-headed`, `playwright`, `playwright-headed`,
# `pagecast`, `pagecast-headed` - are OPT-IN so a plain session never launches
# five browser npx processes it does not need. They exist as tools only after
# the user opts into the visual/doc workflow; this step is that opt-in for the
# plugin-installed Claude path.
#
# It registers each opt-in family with `claude mcp add --scope user <server> --
# npx -y <pinned-pkg> <flags>` (pins + flags come from the browser-mcp-servers.sh
# SSOT). It is idempotent (a family already registered is skipped) and never
# touches the eager chrome-devtools (the bundled .mcp.json owns that). Their
# tool PERMISSIONS are already covered - browser_prefixes.py allow-lists all six
# families from a static SSOT, decoupled from the eager set - so wiring one here
# needs no permission change.
#
# OPT-OUT for a browser-free host: to also stop the eager chrome-devtools from
# loading, add it to `disabledMcpjsonServers` in Claude settings, e.g.
#   { "disabledMcpjsonServers": ["chrome-devtools"] }
# Do NOT run this step on such a host (it is opt-in and does nothing unless run).
#
# Subcommands (registry contract, shared by every setup step):
#   describe   Print a one-line human description of what this step does.
#   check      Exit 0 if there is nothing to do (Claude CLI absent, or all five
#              opt-in families already registered at user scope); exit 1 if the
#              Claude CLI is present and any opt-in family is missing.
#   apply      Register the missing opt-in families. Idempotent, never sudo.
#
# CONFIG / OVERRIDES (for tests / non-default installs):
#   CLAUDE_BIN   Claude CLI binary   ${CLAUDE_BIN:-claude}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/browser-mcp-servers.sh
. "$SCRIPT_DIR/../lib/browser-mcp-servers.sh"

CLAUDE_BIN="${CLAUDE_BIN:-claude}"

_have_claude() { command -v "$CLAUDE_BIN" >/dev/null 2>&1; }

# Present if `claude mcp get <name>` succeeds (registered in some scope).
_claude_has() {
    "$CLAUDE_BIN" mcp get "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Wire the 5 opt-in browser MCP families (chrome-devtools-headed, playwright[-headed], pagecast[-headed]) into Claude at user scope, on demand (chrome-devtools is eager via bundled .mcp.json)"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
cmd_check() {
    # No Claude CLI -> cannot (and need not) wire; nothing to do.
    _have_claude || return 0
    local s missing=0
    for s in "${BROWSER_MCP_OPTIN_SERVERS[@]}"; do
        _claude_has "$s" || missing=1
    done
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    if ! _have_claude; then
        echo "  claude CLI not found on PATH - skipping Claude opt-in wiring."
        echo "  Install/expose the 'claude' CLI, then re-run this step to enable the visual/doc browser families."
        return 0
    fi
    echo "Wiring opt-in browser MCP families into Claude (user scope)..."
    local s
    local -a pkg_args
    for s in "${BROWSER_MCP_OPTIN_SERVERS[@]}"; do
        if _claude_has "$s"; then
            echo "  claude: $s already registered - skip"
            continue
        fi
        mapfile -t pkg_args < <(browser_mcp_npx_args "$s")
        # claude mcp add --scope user <name> -- npx -y <pkg> <flags...>
        "$CLAUDE_BIN" mcp add --scope user "$s" -- npx -y "${pkg_args[@]}"
        echo "  claude: added $s (user scope) -> npx -y ${pkg_args[*]}"
    done
    echo "ok opt-in browser MCP families wired. Restart Claude Code - MCP does not hot-reload."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
