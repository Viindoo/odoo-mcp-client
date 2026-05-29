#!/usr/bin/env bash
# 10-browser-mcp.sh - Wire the 3 browser MCP servers cross-runtime.
#
# Registers three local stdio MCP servers - chrome-devtools, playwright and
# pagecast (all launched via `npx`) - into every AI CLI runtime found on the
# machine: Claude Code, Codex CLI and Gemini CLI.
#
# Subcommands (registry contract, shared by every setup step):
#   describe   Print a one-line human description of what this step does.
#   check      Exit 0 if ALL applicable runtimes already have ALL 3 servers
#              (nothing to do); exit 1 if any wiring is missing (apply needed).
#   apply      Perform the wiring. Idempotent, backs up before writing, never
#              sudo, never blind-overwrites. Re-running adds nothing.
#
# CONFIG PATHS (override via env for tests / non-default homes):
#   CLAUDE_CONFIG    MCP server registry          ${CLAUDE_CONFIG:-$HOME/.claude.json}
#   CODEX_CONFIG     Codex TOML config            ${CODEX_CONFIG:-$HOME/.codex/config.toml}
#   GEMINI_SETTINGS  Gemini settings JSON         ${GEMINI_SETTINGS:-$HOME/.gemini/settings.json}
#
# HARD RULES:
#   - Claude MCP registry is ~/.claude.json (NOT ~/.claude/settings.json, which
#     holds permissions - that is step 30's job). Do not cross the streams.
#   - Codex only accepts local stdio servers - npx command is correct here.
#   - No secrets are written (these servers need none).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"

CLAUDE_CONFIG="${CLAUDE_CONFIG:-$HOME/.claude.json}"
CODEX_CONFIG="${CODEX_CONFIG:-$HOME/.codex/config.toml}"
GEMINI_SETTINGS="${GEMINI_SETTINGS:-$HOME/.gemini/settings.json}"

# Server name -> npx args mapping. These args follow `npx -y` and MUST stay
# byte-for-byte in sync with the plugin's .mcp.json (the SSOT for the 3 browser
# servers' command + args). Each entry prints one arg per line so packages and
# flags (e.g. playwright's --caps=devtools) survive whitespace safely.
SERVERS=(chrome-devtools playwright pagecast)
_npx_args() {
    case "$1" in
        chrome-devtools) printf '%s\n' "chrome-devtools-mcp@latest" ;;
        playwright)      printf '%s\n' "@playwright/mcp@latest" "--caps=devtools" ;;
        pagecast)        printf '%s\n' "@mcpware/pagecast" ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Wire 3 browser MCP servers (chrome-devtools, playwright, pagecast) into Claude/Codex/Gemini"
}

# ---------------------------------------------------------------------------
# check helpers - return 0 if the named server is present in the given file
# ---------------------------------------------------------------------------
_claude_has() {
    # $1 = server name. Present if mcpServers.<name> exists in CLAUDE_CONFIG.
    [[ -f "$CLAUDE_CONFIG" ]] || return 1
    python3 - "$CLAUDE_CONFIG" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
sys.exit(0 if sys.argv[2] in (data.get("mcpServers") or {}) else 1)
PY
}

_codex_has() {
    # $1 = server name. Present if table [mcp_servers.<name>] exists.
    [[ -f "$CODEX_CONFIG" ]] || return 1
    grep -qE "^\[mcp_servers\.$1\]" "$CODEX_CONFIG"
}

_gemini_has() {
    # $1 = server name. Present if mcpServers.<name> exists in GEMINI_SETTINGS.
    [[ -f "$GEMINI_SETTINGS" ]] || return 1
    python3 - "$GEMINI_SETTINGS" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
sys.exit(0 if sys.argv[2] in (data.get("mcpServers") or {}) else 1)
PY
}

cmd_check() {
    # Exit 0 only if all 3 servers present in every runtime that is actually
    # installed. Codex and Gemini are OPTIONAL: a machine with only Claude must
    # not be reported as "needs wiring" just because ~/.codex / ~/.gemini are
    # absent. Their config file existing is the signal that the runtime is set up.
    local missing=0
    for s in "${SERVERS[@]}"; do
        _claude_has "$s" || missing=1
        if [[ -f "$CODEX_CONFIG" ]]; then
            _codex_has "$s" || missing=1
        fi
        if [[ -f "$GEMINI_SETTINGS" ]]; then
            _gemini_has "$s" || missing=1
        fi
    done
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply helpers - per runtime
# ---------------------------------------------------------------------------
_apply_claude() {
    local name
    local -a pkg_args
    for name in "${SERVERS[@]}"; do
        mapfile -t pkg_args < <(_npx_args "$name")
        if _claude_has "$name"; then
            echo "  claude: $name already registered - skip"
            continue
        fi
        # Prefer the official CLI when available (matches connect.md pattern).
        if command -v claude >/dev/null 2>&1; then
            if claude mcp add --scope user "$name" -- npx -y "${pkg_args[@]}" >/dev/null 2>&1; then
                echo "  claude: added $name via 'claude mcp add'"
                continue
            fi
            echo "  claude: 'claude mcp add' failed for $name, falling back to json-merge" >&2
        fi
        # Fallback: deep-merge into the MCP registry file.
        python3 - "$name" "${pkg_args[@]}" <<'PY' | python3 "$LIB" json-merge "$CLAUDE_CONFIG"
import json, sys
name, pkg_args = sys.argv[1], sys.argv[2:]
print(json.dumps({"mcpServers": {name: {
    "command": "npx", "args": ["-y", *pkg_args]
}}}))
PY
        echo "  claude: merged $name into $CLAUDE_CONFIG"
    done
}

_apply_codex() {
    local name args_toml
    local -a pkg_args
    for name in "${SERVERS[@]}"; do
        mapfile -t pkg_args < <(_npx_args "$name")
        if _codex_has "$name"; then
            echo "  codex: $name already registered - skip"
            continue
        fi
        # Render the args array as a TOML list: ["-y", "<pkg>", "<flag>", ...].
        args_toml='"-y"'
        local a
        for a in "${pkg_args[@]}"; do
            args_toml="$args_toml, \"$a\""
        done
        printf 'command = "npx"\nargs = [%s]\n' "$args_toml" \
            | python3 "$LIB" toml-ensure-table "$CODEX_CONFIG" "[mcp_servers.$name]" >/dev/null
        echo "  codex: ensured [mcp_servers.$name] in $CODEX_CONFIG"
    done
}

_apply_gemini() {
    local name
    local -a pkg_args
    for name in "${SERVERS[@]}"; do
        mapfile -t pkg_args < <(_npx_args "$name")
        if _gemini_has "$name"; then
            echo "  gemini: $name already registered - skip"
            continue
        fi
        python3 - "$name" "${pkg_args[@]}" <<'PY' | python3 "$LIB" json-merge "$GEMINI_SETTINGS"
import json, sys
name, pkg_args = sys.argv[1], sys.argv[2:]
print(json.dumps({"mcpServers": {name: {
    "command": "npx", "args": ["-y", *pkg_args], "trust": True
}}}))
PY
        echo "  gemini: merged $name (trust=true) into $GEMINI_SETTINGS"
    done
}

cmd_apply() {
    if [[ ! -f "$LIB" ]]; then
        echo "x lib not found at $LIB - cannot merge config. Install the plugin fully." >&2
        return 1
    fi
    echo "Wiring browser MCP servers..."
    # Claude is always handled. Codex and Gemini are OPTIONAL — only wire them
    # when their config file already exists, so a Claude-only machine never gets
    # an uninvited ~/.codex/config.toml or ~/.gemini/settings.json created.
    _apply_claude
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
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
