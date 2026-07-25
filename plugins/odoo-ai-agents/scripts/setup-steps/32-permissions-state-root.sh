#!/usr/bin/env bash
# 32-permissions-state-root.sh - Auto-allow the narrow set of Bash/Read/Write/Edit
# rules the planning + intake pipeline needs to resolve and write under the
# machine-global state root ($ODOO_AI_HOME) without a per-call approval prompt.
#
# WHY this is a SIBLING of 30-permissions.sh, not folded into it: 30 owns the
# browser-MCP tool-permission surface (its docstring, cmd_describe, and the V-19
# three-way sync with browser_prefixes.py / browser-mcp-servers.sh are all
# browser-specific). This step owns a DIFFERENT, narrower surface - state-root
# Bash/Read/Write/Edit rules - so it gets its own numbered script per the repo's
# "one capability, one step script" convention (see commands/odoo-setup.md).
#
# Root cause this fixes: `odoo-planner` / `odoo-doc-planner` / intake Phase P all
# resolve and write under $ODOO_AI_HOME on every planning/run-DAG turn. Without
# this permission pre-grant, a fresh install prompts for the SAME handful of
# Bash/Read/Write/Edit calls on every session - not a Plan-Mode problem (see
# snippets/planning-gate-contract.md § Plan-Mode enter/exit for that fix), a
# permissions-onboarding problem. This step is the out-of-the-box experience for
# a fresh install; it does not (and cannot) change Plan Mode's own inheritance
# behavior.
#
# HARD SAFETY CONTRACT (enforced by tests/test_state_root_permissions.py -
# do NOT loosen without updating that test):
#   - Writes ONLY to permissions.allow[] - NEVER permissions.deny[]/ask[], and
#     NEVER additionalDirectories (that would widen READ scope across every
#     project's state tree for every session; Read(//$ODOO_AI_HOME/**) below
#     already achieves the needed effect with a narrower blast radius).
#   - The Write/Edit rules cover ONLY `projects/**` and `worklog/**` under the
#     state root - they EXCLUDE `bin/`, `venvs/`, `node_tools/`, `setup-scripts/`,
#     `runtime/`, and `instances.toml`. A sitecustomize.py under venvs/ or an
#     edited setup-scripts/*.sh is deferred code execution, not scratch data -
#     granting blanket Write(//$ODOO_AI_HOME/**) would auto-approve that too.
#   - Never writes `mcp__odoo-semantic` - that permission's owner is
#     plugins/odoo-semantic-mcp/commands/connect.md step 5; `check` below only
#     REPORTS its absence and points there.
#   - Bash rules are EXACT, wildcard-free command strings (the script this
#     grants takes exactly two argument values - `share` or `isolate` - so a
#     trailing `:*` wildcard would only widen the surface for no benefit).
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if all 7 rules already in permissions.allow[];
#              exit 1 if any is missing. Also reports (non-blocking) whether
#              mcp__odoo-semantic is present, pointing at its real owner.
#   apply      Ask [Y/n] (honors ODOO_AI_NO_AUTO_PERMS=1 opt-out), then
#              idempotently append the 7 rules via config_merge.py
#              json-ensure-allow, print them, instruct one restart, and
#              self-verify by re-running check.
#
# CONFIG PATH:
#   CLAUDE_SETTINGS  permissions file  ${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
#
# HARD RULES:
#   - Writes to ~/.claude/settings.json (permissions) - NOT ~/.claude.json
#     (the MCP registry).
#   - Never echoes secrets (there are none here).
#   - Idempotent: re-running adds nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"

CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

# Resolve the plugin root: prefer the harness-provided $CLAUDE_PLUGIN_ROOT (set
# when this step is dispatched from within the plugin's own command/hook
# context - mirrors commands/odoo-setup.md's own STEPS_DIR resolution); fall
# back to computing it from this script's own location so a direct/standalone
# invocation (tests, manual `bash 32-....sh apply`) still resolves correctly.
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT%/}"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

# Resolve the state root exactly like scripts/lib/resolve_project_dir.sh's own
# Tier-1 root convention: $ODOO_AI_HOME, defaulting to $HOME/.odoo-ai.
ODOO_AI_HOME="${ODOO_AI_HOME:-$HOME/.odoo-ai}"
ODOO_AI_HOME="${ODOO_AI_HOME%/}"

# The 7 exact rules (SSOT for this step). Read/Write/Edit use the `//<abs-path>`
# form (one extra leading slash over the already-absolute $ODOO_AI_HOME) so the
# rule matches an ABSOLUTE filesystem path, not a project-relative one.
RULES=(
    "Bash(bash ${PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share)"
    "Bash(bash ${PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh isolate)"
    "Read(/${ODOO_AI_HOME}/**)"
    "Write(/${ODOO_AI_HOME}/projects/**)"
    "Edit(/${ODOO_AI_HOME}/projects/**)"
    "Write(/${ODOO_AI_HOME}/worklog/**)"
    "Edit(/${ODOO_AI_HOME}/worklog/**)"
)

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Auto-allow the state-root Bash/Read/Write/Edit rules (planning + intake Phase P) in Claude permissions"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
_allow_has() {
    # $1 = rule string. Exit 0 if present in permissions.allow[].
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

_odoo_semantic_present() {
    [[ -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 - "$CLAUDE_SETTINGS" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
allow = (data.get("permissions") or {}).get("allow") or []
sys.exit(0 if any(a == "mcp__odoo-semantic" or a.startswith("mcp__odoo-semantic__") for a in allow) else 1)
PY
}

cmd_check() {
    local missing=0
    for r in "${RULES[@]}"; do
        _allow_has "$r" || missing=1
    done
    # Informational only - mcp__odoo-semantic is NOT this step's rule to write
    # or require; its owner is odoo-semantic-mcp's connect command.
    if ! _odoo_semantic_present; then
        echo "i  mcp__odoo-semantic is not in permissions.allow[] - that is NOT this step's job; run /odoo-semantic-mcp:connect (step 5) to add it." >&2
    fi
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    # Opt-out: respect a user who turned auto-permissioning off (same escape
    # hatch as hooks/ensure-browser-permissions.sh).
    if [[ "${ODOO_AI_NO_AUTO_PERMS:-0}" == "1" ]]; then
        echo "Skipped state-root permission auto-allow (ODOO_AI_NO_AUTO_PERMS=1). Re-run: /odoo-ai-agents:odoo-setup permissions"
        return 0
    fi

    if [[ ! -f "$LIB" ]]; then
        echo "x lib not found at $LIB - cannot edit permissions. Install the plugin fully." >&2
        return 1
    fi

    # Confirmation gate (mirrors 30-permissions.sh / connect.md step 5). Honour
    # non-interactive mode: if stdin is not a TTY, proceed (the calling agent
    # gates upstream).
    local reply="Y"
    if [[ -t 0 ]]; then
        printf 'Auto-allow state-root planning permissions in %s? [Y/n] ' "$CLAUDE_SETTINGS"
        read -r reply || reply="Y"
        reply="${reply:-Y}"
    fi
    case "$reply" in
        n|N|no|No|NO|skip)
            echo "Skipped state-root permission auto-allow. You can re-run: /odoo-ai-agents:odoo-setup permissions"
            return 0
            ;;
    esac

    local r rc had_io_error=0
    for r in "${RULES[@]}"; do
        # json-ensure-allow is idempotent, backs up. Exit contract:
        #   0 = success / already present, 1 = general I/O error, 2 = invalid JSON.
        set +e
        python3 "$LIB" json-ensure-allow "$CLAUDE_SETTINGS" "$r"
        rc=$?
        set -e
        if [[ "$rc" -eq 2 ]]; then
            echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
            return 2
        elif [[ "$rc" -eq 1 ]]; then
            echo "x failed to add '$r' to $CLAUDE_SETTINGS (I/O error). Skipping this rule." >&2
            had_io_error=1
        fi
    done
    if [[ "$had_io_error" -eq 1 ]]; then
        echo "! some state-root permission rules could not be written - re-run after fixing the cause." >&2
        return 1
    fi

    echo "ok state-root planning permissions allow-listed in $CLAUDE_SETTINGS:"
    for r in "${RULES[@]}"; do
        echo "   $r"
    done
    echo "i  because permissions are finalized BEFORE SessionStart hooks run, RESTART Claude Code once (or start a new session) for them to take effect this session."

    # Self-verify.
    if cmd_check >/dev/null; then
        echo "ok self-verify: all state-root permission rules confirmed present."
    else
        echo "x self-verify failed - re-run '$(basename "$0") check' to see what is still missing." >&2
        return 1
    fi
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
