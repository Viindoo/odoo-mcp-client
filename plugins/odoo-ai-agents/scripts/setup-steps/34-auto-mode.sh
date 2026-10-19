#!/usr/bin/env bash
# 34-auto-mode.sh - Teach Claude Code's auto-mode classifier what is routine on this machine,
# so development is not interrupted, while keeping a human gate on the protected branches.
#
# WHY a setup step: a plugin cannot ship `permissions` or `autoMode` (its manifest settings
# only accept `agent` and `subagentStatusLine`), and the classifier reads `autoMode.*` ONLY
# from the user's own settings file. The sanctioned path is a step that writes that file
# after the owner consents - the same path steps 30 and 32 take.
#
# What it writes (user settings, every entry tagged `odoo-ai-agents: ` so a later version
# prunes its own entries and never touches yours):
#   autoMode.allow        what is routine development inside the trusted roots
#   autoMode.soft_deny    pushing straight to / deleting a protected branch, merging a PR
#                         without the user's confirmation
#   autoMode.environment  organization, fork owner, trusted roots, purpose, protected branches
#   permissions.ask       `git push` rules naming each protected branch (always prompt)
# Each autoMode array keeps "$defaults" as its first element, so the built-in defaults stay.
# It NEVER writes hard_deny, permissions.allow or a bypass mode.
#
# Every value is derived from the machine (scripts/lib/auto_mode_facts.py): trusted roots
# from the instance catalog's addons_path rows, organization and fork owner from the git
# remotes of those repositories, protected branches from the remote's default branch plus
# every `<major>.0` branch. Git is only read.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 when every entry is present and no stale tagged entry remains (also
#              under the opt-out, or when nothing can be derived); exit 1 otherwise.
#   propose    Print the derived facts and every entry apply would write; exit 1 when
#              nothing can be derived (names what is missing).
#   apply      Ask [Y/n] per group (non-interactive stdin counts as yes), prune this
#              plugin's tagged entries, then union the current set. Idempotent, backs up.
#
# CONFIG:
#   CLAUDE_SETTINGS     ${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
#   ODOO_AI_HOME        state root, ODOO_AI_INSTANCES: catalog override
#   ODOO_AI_NO_AUTO_PERMS=1   opt-out: nothing is written
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
FACTS="$SCRIPT_DIR/../lib/auto_mode_facts.py"

CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
TAG="odoo-ai-agents: "

cmd_describe() {
    echo "Teach auto mode what is routine here (trusted roots, git, instances) and guard protected branches"
}

cmd_check() {
    [[ "${ODOO_AI_NO_AUTO_PERMS:-0}" == "1" ]] && return 0
    python3 "$FACTS" check "$CLAUDE_SETTINGS"
}

cmd_propose() {
    python3 "$FACTS" propose
}

_ask_group() {
    # $1 = question. Exit 0 = yes. Non-interactive stdin counts as yes.
    local reply="Y"
    if [[ -t 0 ]]; then
        printf '%s [Y/n] ' "$1"
        read -r reply || reply="Y"
        reply="${reply:-Y}"
    fi
    case "$reply" in
        n|N|no|No|NO|skip) return 1 ;;
    esac
    return 0
}

_lib() {
    # Run a config_merge subcommand; map its exit code (2 = invalid JSON) to a message.
    local rc
    set +e
    python3 "$LIB" "$@" >/dev/null
    rc=$?
    set -e
    if [[ "$rc" -eq 2 ]]; then
        echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
        exit 2
    elif [[ "$rc" -ne 0 ]]; then
        echo "x failed to update $CLAUDE_SETTINGS ($1, rc=$rc)." >&2
        exit 1
    fi
}

_write_array() {
    # $1 = dotted array path, $2 = JSON array of entries. Prune ours, keep "$defaults" first, union.
    local path="$1" entries="$2"
    _lib json-prune-tagged "$CLAUDE_SETTINGS" "$path" "$TAG"
    _lib json-ensure-first "$CLAUDE_SETTINGS" "$path" '$defaults'
    python3 - "$path" "$entries" <<'PY' | _merge_stdin
import json, sys
path, entries = sys.argv[1], json.loads(sys.argv[2])
node = entries
for key in reversed(path.split(".")):
    node = {key: node}
print(json.dumps(node))
PY
}

_merge_stdin() {
    local frag rc
    frag="$(cat)"
    set +e
    printf '%s' "$frag" | python3 "$LIB" json-merge "$CLAUDE_SETTINGS" >/dev/null
    rc=$?
    set -e
    if [[ "$rc" -eq 2 ]]; then
        echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
        exit 2
    elif [[ "$rc" -ne 0 ]]; then
        echo "x failed to update $CLAUDE_SETTINGS (json-merge, rc=$rc)." >&2
        exit 1
    fi
}

_entries_field() {
    # $1 = python expression over the entries dict `e`
    printf '%s' "$ENTRIES" | python3 -c "import json,sys; e=json.load(sys.stdin); print(json.dumps($1))"
}

cmd_apply() {
    if [[ "${ODOO_AI_NO_AUTO_PERMS:-0}" == "1" ]]; then
        echo "Skipped auto-mode setup (ODOO_AI_NO_AUTO_PERMS=1). Re-run: /odoo-ai-agents:odoo-setup auto-mode"
        return 0
    fi
    if [[ ! -f "$LIB" || ! -f "$FACTS" ]]; then
        echo "x helper library not found next to this step - install the plugin fully." >&2
        return 1
    fi
    # Refuse a non-JSON settings file before asking anything.
    if [[ -f "$CLAUDE_SETTINGS" ]] && ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$CLAUDE_SETTINGS" 2>/dev/null; then
        echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
        return 2
    fi

    local rc=0
    ENTRIES="$(python3 "$FACTS" entries)" || rc=$?
    if [[ "$rc" -ne 0 ]]; then
        python3 "$FACTS" propose >&2 || true
        return 1
    fi

    python3 "$FACTS" propose
    echo

    if _ask_group "Write the routine-development entries (autoMode.allow) to $CLAUDE_SETTINGS?"; then
        _write_array autoMode.allow "$(_entries_field 'e["autoMode"]["allow"]')"
        echo "ok autoMode.allow updated"
    else
        echo "Skipped autoMode.allow."
    fi
    if _ask_group "Write the protected-branch guard (autoMode.soft_deny and permissions.ask) to $CLAUDE_SETTINGS?"; then
        _write_array autoMode.soft_deny "$(_entries_field 'e["autoMode"]["soft_deny"]')"
        _lib json-prune-tagged "$CLAUDE_SETTINGS" permissions.ask "$(_entries_field 'e["ask_pattern"]' | python3 -c 'import json,sys; print(json.load(sys.stdin))')" --regex
        local ask
        ask="$(_entries_field 'e["ask"]')"
        if [[ "$ask" != "[]" ]]; then
            printf '%s' "$ask" | python3 -c 'import json,sys; print(json.dumps({"permissions": {"ask": json.load(sys.stdin)}}))' | _merge_stdin
        fi
        echo "ok autoMode.soft_deny and permissions.ask updated"
    else
        echo "Skipped the protected-branch guard."
    fi
    if _ask_group "Write the environment description (autoMode.environment) to $CLAUDE_SETTINGS?"; then
        _write_array autoMode.environment "$(_entries_field 'e["autoMode"]["environment"]')"
        echo "ok autoMode.environment updated"
    else
        echo "Skipped autoMode.environment."
    fi
    echo "i  auto mode reads these entries when a session starts - start a new session for them to take effect."
}

# --- interpreter preflight (same shape as 30/32) -------------------------------------------
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
    propose)  cmd_propose ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|propose|apply}" >&2; exit 2 ;;
esac
