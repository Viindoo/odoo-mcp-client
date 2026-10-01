#!/usr/bin/env bash
# 10-browser-mcp.sh - Wire the 6 browser MCP servers into Codex and Gemini.
#
# Registers six local stdio MCP servers - chrome-devtools, playwright and pagecast, each with a
# headless default and a `-headed` variant (all launched via `npx`) - into Codex CLI and Gemini
# CLI when those runtimes are installed, each with the state-root flags
# scripts/lib/browser_mcp_servers.py resolves ON THIS MACHINE NOW (state root from
# scripts/lib/paths.py). Neither runtime expands ${CLAUDE_PLUGIN_ROOT}, and their session hooks do
# not run this plugin's SessionStart probe, so re-run this step after every plugin update.
#
# Claude Code does NOT need to be wired here: this plugin bundles its own .mcp.json which Claude
# reads automatically, and step 12 wires Claude's opt-in families at user scope. This script NEVER
# writes to ~/.claude.json.
#
# Subcommands (registry contract, shared by every setup step):
#   describe   Print a one-line human description of what this step does.
#   check      Exit 0 if every installed runtime registers all six servers exactly as specified;
#              exit 1 if any is missing or drifted (other command/args/env).
#   apply      Register missing servers and REPLACE drifted ones (never merge: a merged args list
#              keeps the stale flag next to its replacement). Backs up before writing, never sudo.
#
# CONFIG PATHS (override via env for tests / non-default homes):
#   CODEX_CONFIG     Codex TOML config            ${CODEX_CONFIG:-$HOME/.codex/config.toml}
#   GEMINI_SETTINGS  Gemini settings JSON         ${GEMINI_SETTINGS:-$HOME/.gemini/settings.json}
#
# A Gemini settings.json server wins over the extension's server of the same name, so the
# resolved entry written here is the one Gemini runs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"

CODEX_CONFIG="${CODEX_CONFIG:-$HOME/.codex/config.toml}"
GEMINI_SETTINGS="${GEMINI_SETTINGS:-$HOME/.gemini/settings.json}"

# shellcheck source=../lib/browser-mcp-servers.sh
. "$SCRIPT_DIR/../lib/browser-mcp-servers.sh"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Wire 6 browser MCP servers (chrome-devtools/playwright/pagecast, each headless + -headed) into Codex/Gemini with this machine's state-root flags; replace drifted entries (Claude uses bundled .mcp.json)"
}

# The desired spec per runtime: Gemini entries also carry trust=true.
_codex_spec() { browser_mcp_spec "$1"; }
_gemini_spec() {
    browser_mcp_spec "$1" | python3 -c 'import json, sys; d = json.load(sys.stdin); d["trust"] = True; print(json.dumps(d))'
}

_codex_matches() {
    [[ -f "$CODEX_CONFIG" ]] || return 1
    _codex_spec "$1" | python3 "$LIB" mcp-server-matches toml "$CODEX_CONFIG" "$1" >/dev/null 2>&1
}

_gemini_matches() {
    [[ -f "$GEMINI_SETTINGS" ]] || return 1
    _gemini_spec "$1" | python3 "$LIB" mcp-server-matches json "$GEMINI_SETTINGS" "$1" >/dev/null 2>&1
}

cmd_check() {
    # Codex and Gemini are OPTIONAL: a machine with only Claude must not be reported as "needs
    # wiring" because ~/.codex / ~/.gemini are absent. Their config file existing is the signal
    # that the runtime is set up.
    local s missing=0
    for s in "${BROWSER_MCP_ALL_SERVERS[@]}"; do
        if [[ -f "$CODEX_CONFIG" ]]; then
            _codex_matches "$s" || missing=1
        fi
        if [[ -f "$GEMINI_SETTINGS" ]]; then
            _gemini_matches "$s" || missing=1
        fi
    done
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply helpers - per runtime
# ---------------------------------------------------------------------------
_apply_codex() {
    local name
    for name in "${BROWSER_MCP_ALL_SERVERS[@]}"; do
        if _codex_matches "$name"; then
            echo "  codex: $name already registered as specified - skip"
            continue
        fi
        _codex_spec "$name" | python3 "$LIB" mcp-server-set toml "$CODEX_CONFIG" "$name" >/dev/null
        echo "  codex: set [mcp_servers.$name] in $CODEX_CONFIG"
    done
}

_apply_gemini() {
    local name
    for name in "${BROWSER_MCP_ALL_SERVERS[@]}"; do
        if _gemini_matches "$name"; then
            echo "  gemini: $name already registered as specified - skip"
            continue
        fi
        _gemini_spec "$name" | python3 "$LIB" mcp-server-set json "$GEMINI_SETTINGS" "$name" >/dev/null
        echo "  gemini: set $name (trust=true) in $GEMINI_SETTINGS"
    done
}

cmd_apply() {
    if [[ ! -f "$LIB" ]]; then
        echo "x lib not found at $LIB - cannot merge config. Install the plugin fully." >&2
        return 1
    fi
    echo "Wiring browser MCP servers into Codex/Gemini..."
    # Codex and Gemini are OPTIONAL - only wire them when their config file already exists, so a
    # Claude-only machine never gets an uninvited ~/.codex/config.toml or ~/.gemini/settings.json.
    if [[ -f "$CODEX_CONFIG" ]]; then
        _apply_codex
    else
        echo "  codex: $CODEX_CONFIG not found - skipping (Codex not installed)"
    fi
    if [[ -f "$GEMINI_SETTINGS" ]]; then
        _apply_gemini
    else
        echo "  gemini: $GEMINI_SETTINGS not found - skipping (Gemini not installed)"
    fi
    echo "ok browser MCP servers wired. Restart each CLI session - MCP does not hot-reload."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
# --- interpreter preflight ------------------------------------------------------------------
# This step rewrites JSON settings files through python. A broken interpreter would leave
# them unwritten while the step reported success, so it stops here instead.
# SSOT: scripts/lib/require_python.sh. `describe` and the usage arm are pure text and stay
# runnable on a host with no python at all.
_REQ_PY="$SCRIPT_DIR/../lib/require_python.sh"
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
