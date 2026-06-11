#!/usr/bin/env bash
# 30-permissions.sh - Auto-allow the browser MCP tools in Claude Code.
#
# Plugin manifests cannot declare permissions themselves (Claude Code plugin
# settings.json only accepts `agent` + `subagentStatusLine`), so the only safe
# automated path is to append permission prefixes into the user-scope
# permissions file - exactly mirroring odoo-semantic-mcp/commands/connect.md
# step 5.
#
# Tool-name note: when an MCP server is provided by a plugin, Claude Code
# namespaces its tools as  mcp__plugin_<plugin>_<server>__<tool>  (see the
# chrome-devtools tool names exposed by this very repo). A bare-server prefix
# like `mcp__chrome-devtools` only matches when the server is registered
# stand-alone (e.g. via `claude mcp add`). To be safe across BOTH forms we
# allow the broad bare prefixes (which connect.md proved is the supported
# pattern) - a prefix entry matches any tool whose name starts with it.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if all browser prefixes already in permissions.allow[];
#              exit 1 if any is missing.
#   apply      Ask [Y/n], then idempotently append the prefixes via the lib.
#
# CONFIG PATH:
#   CLAUDE_SETTINGS  permissions file  ${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
#
# HARD RULES:
#   - Writes to ~/.claude/settings.json (permissions) - NOT ~/.claude.json
#     (the MCP registry, which step 10 owns). Do not cross the streams.
#   - Never echoes secrets (there are none here).
#   - Idempotent: re-running adds nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"

CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

# Broad bare-server prefixes. A permission prefix matches any tool whose name
# starts with it, so `mcp__chrome-devtools` covers the stand-alone form. We
# also list the plugin-namespaced forms for completeness/explicitness.
PREFIXES=(
    "mcp__chrome-devtools"
    "mcp__playwright"
    "mcp__pagecast"
    "mcp__plugin_chrome-devtools-mcp_chrome-devtools"
)

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Auto-allow browser MCP tools (chrome-devtools, playwright, pagecast) in Claude permissions"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
_allow_has() {
    # $1 = prefix. Exit 0 if present in permissions.allow[].
    [[ -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 - "$CLAUDE_SETTINGS" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
allow = (data.get("permissions") or {}).get("allow") or []
sys.exit(0 if sys.argv[2] in allow else 1)
PY
}

cmd_check() {
    local missing=0
    for p in "${PREFIXES[@]}"; do
        _allow_has "$p" || missing=1
    done
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    if [[ ! -f "$LIB" ]]; then
        echo "x lib not found at $LIB - cannot edit permissions. Install the plugin fully." >&2
        return 1
    fi

    # Confirmation gate (mirrors connect.md step 5). Honour non-interactive
    # mode: if stdin is not a TTY, proceed (the calling agent gates upstream).
    local reply="Y"
    if [[ -t 0 ]]; then
        printf 'Auto-allow browser MCP tools in %s? [Y/n] ' "$CLAUDE_SETTINGS"
        read -r reply || reply="Y"
        reply="${reply:-Y}"
    fi
    case "$reply" in
        n|N|no|No|NO|skip)
            echo "Skipped permission auto-allow. You can re-run: /odoo-ai-agents:odoo-setup permissions"
            return 0
            ;;
    esac

    local p rc had_io_error=0
    for p in "${PREFIXES[@]}"; do
        # json-ensure-allow is idempotent, backs up. Exit contract:
        #   0 = success / already present, 1 = general I/O error, 2 = invalid JSON.
        set +e
        python3 "$LIB" json-ensure-allow "$CLAUDE_SETTINGS" "$p"
        rc=$?
        set -e
        if [[ "$rc" -eq 2 ]]; then
            echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
            return 2
        elif [[ "$rc" -eq 1 ]]; then
            # I/O or unexpected error for this prefix. Do not silently treat as
            # success: warn, flag it, and keep going so the rest still apply.
            echo "x failed to add '$p' to $CLAUDE_SETTINGS (I/O error). Skipping this prefix." >&2
            had_io_error=1
        fi
    done
    if [[ "$had_io_error" -eq 1 ]]; then
        echo "! some browser MCP prefixes could not be written - re-run after fixing the cause." >&2
        return 1
    fi
    echo "ok browser MCP tools allow-listed in $CLAUDE_SETTINGS"
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
