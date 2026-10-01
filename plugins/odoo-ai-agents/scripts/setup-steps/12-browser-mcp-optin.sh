#!/usr/bin/env bash
# 12-browser-mcp-optin.sh - Wire the FIVE opt-in browser MCP families into Claude Code at USER
# scope, on demand, with this machine's state-root flags.
#
# Only ONE browser family is EAGER: the plugin's bundled .mcp.json starts the headless
# `chrome-devtools` through scripts/mcp/browser_mcp_launch.py, which resolves the state root at
# every launch. The other five - `chrome-devtools-headed`, `playwright`, `playwright-headed`,
# `pagecast`, `pagecast-headed` - are OPT-IN so a plain session never launches five browser npx
# processes it does not need. This step is that opt-in for the plugin-installed Claude path.
#
# Each family is registered as
#   claude mcp add --scope user <server> [-e KEY=VALUE] -- npx -y <pin> <flags> <state-root flags>
# with the spec scripts/lib/browser_mcp_servers.py resolves ON THIS MACHINE NOW (the state root
# from scripts/lib/paths.py): a user-scope entry carries resolved values only, never a plugin
# cache path. A family registered with any other command, args or env (an older pin, no
# state-root flag, a moved $ODOO_AI_HOME) is DRIFT: `check` reports it and `apply` removes and
# re-adds that entry (never merges - a merged args list keeps the stale flag); when the add fails,
# the removed entry is restored and the step fails. Restart Claude Code
# afterwards: MCP does not hot-reload. Tool PERMISSIONS need no change here - browser_prefixes.py
# allow-lists all six families from a static SSOT.
#
# OPT-OUT for a browser-free host: to also stop the eager chrome-devtools from loading, add it
# to `disabledMcpjsonServers` in Claude settings, e.g.
#   { "disabledMcpjsonServers": ["chrome-devtools"] }
# Do NOT run this step on such a host (it is opt-in and does nothing unless run).
#
# Subcommands (registry contract, shared by every setup step):
#   describe   Print a one-line human description of what this step does.
#   check      Exit 0 if there is nothing to do (Claude CLI absent, or all five opt-in families
#              registered at user scope exactly as specified); exit 1 if any is missing or
#              drifted.
#   apply      Register the missing families and re-register the drifted ones. Idempotent,
#              never sudo. Exit 1 when any family could not be wired.
#
# CONFIG / OVERRIDES (for tests / non-default installs):
#   CLAUDE_BIN          Claude CLI binary            ${CLAUDE_BIN:-claude}
#   CLAUDE_CONFIG_DIR   Claude's config dir; the user-scope registry is its .claude.json
#                       (default: ~/.claude.json)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
# shellcheck source=../lib/browser-mcp-servers.sh
. "$SCRIPT_DIR/../lib/browser-mcp-servers.sh"

CLAUDE_BIN="${CLAUDE_BIN:-claude}"

_have_claude() { command -v "$CLAUDE_BIN" >/dev/null 2>&1; }

# The file Claude Code keeps user-scope MCP servers in (top-level "mcpServers").
_claude_user_config() { _browser_mcp_py claude-config; }

# 0 when <server> is registered at user scope exactly as the SSOT specifies.
_claude_matches() {
    local spec
    spec="$(browser_mcp_spec "$1")" || return 1
    printf '%s' "$spec" | python3 "$LIB" mcp-server-matches json "$(_claude_user_config)" "$1" >/dev/null 2>&1
}

# The user-scope entry of <server> as compact JSON on stdout (exit 0), or nothing (exit 1) when it
# has none. Captured BEFORE apply removes a drifted entry, so a failed add can put it back.
_claude_user_entry() {
    python3 - "$(_claude_user_config)" "$1" <<'PY' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    sys.exit(1)
servers = (data.get("mcpServers") or {}) if isinstance(data, dict) else {}
entry = servers.get(sys.argv[2]) if isinstance(servers, dict) else None
if entry is None:
    sys.exit(1)
sys.stdout.write(json.dumps(entry, separators=(",", ":")))
PY
}

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Wire the 5 opt-in browser MCP families (chrome-devtools-headed, playwright[-headed], pagecast[-headed]) into Claude at user scope with this machine's state-root flags; re-register drifted entries (chrome-devtools is eager via bundled .mcp.json)"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
cmd_check() {
    # No Claude CLI -> cannot (and need not) wire; nothing to do.
    _have_claude || return 0
    local s missing=0
    for s in "${BROWSER_MCP_OPTIN_SERVERS[@]}"; do
        _claude_matches "$s" || missing=1
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
    local s spec line previous failed=0
    local -a add_args
    for s in "${BROWSER_MCP_OPTIN_SERVERS[@]}"; do
        if _claude_matches "$s"; then
            echo "  claude: $s already registered as specified - skip"
            continue
        fi
        spec="$(browser_mcp_spec "$s")" || { echo "  x cannot resolve the launch spec for $s" >&2; return 1; }
        add_args=()
        while IFS= read -r line; do
            add_args+=("$line")
        done < <(printf '%s' "$spec" | python3 -c '
import json, sys
spec = json.load(sys.stdin)
for key, value in sorted(spec.get("env", {}).items()):
    print("-e")
    print("%s=%s" % (key, value))
print("--")
print(spec["command"])
for arg in spec["args"]:
    print(arg)
')
        # Claude refuses to add a name that exists, so a drifted entry is removed first; its JSON is
        # kept so a failed add restores it instead of leaving the family unregistered.
        previous=""
        if previous="$(_claude_user_entry "$s")"; then
            if ! "$CLAUDE_BIN" mcp remove --scope user "$s" >/dev/null; then
                echo "  x claude: could not remove drifted $s (user scope) - left as it was" >&2
                failed=1
                continue
            fi
            echo "  claude: removed drifted $s (user scope)"
        fi
        # The server name goes BEFORE -e: --env takes several KEY=VALUE pairs and would read a
        # name that follows it as one more.
        if "$CLAUDE_BIN" mcp add --scope user "$s" "${add_args[@]}"; then
            echo "  claude: added $s (user scope) -> ${add_args[*]}"
            continue
        fi
        failed=1
        echo "  x claude: could not add $s (user scope)" >&2
        if [[ -n "$previous" ]]; then
            if "$CLAUDE_BIN" mcp add-json --scope user "$s" "$previous" >/dev/null; then
                echo "  claude: restored the previous $s registration (still drifted)" >&2
            else
                echo "  x claude: could not restore the previous $s registration: $previous" >&2
            fi
        fi
    done
    if [[ "$failed" -ne 0 ]]; then
        echo "x some opt-in browser MCP families were not wired (see above); re-run this step." >&2
        return 1
    fi
    echo "ok opt-in browser MCP families wired. Restart Claude Code - MCP does not hot-reload."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
# --- interpreter preflight ------------------------------------------------------------------
# The launch spec and the drift comparison are computed in python. SSOT:
# scripts/lib/require_python.sh. `describe` and the usage arm are pure text.
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
