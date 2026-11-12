#!/usr/bin/env bash
# 36-claude-tmpdir.sh - Offer to move Claude Code's temp directory into the plugin's state root.
#
# Claude Code keeps per-session working files (scratchpads, task output, images) and its
# bash-edit-diff files under one temp root and never deletes them. By default that root is the
# system temp directory, often memory-backed, so a long-lived machine slowly fills RAM. This step
# proposes CLAUDE_CODE_TMPDIR=<the tmp folder of the state root> in the USER settings file
# (scripts/lib/claude_tmp.py holds the measurement, the write and the SessionEnd sweep that keeps
# the directory small).
# Only that one variable is set: moving the generic temp variable would move every child process.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 when nothing is to do (already set, opted out, settings unusable);
#              1 to propose.
#   propose    Print the measurement and the decision as KEY=VALUE lines plus one plain
#              sentence (QUESTION=...) for the agent to put to the user. Writes nothing.
#   apply      Re-measure; when the decision is still `propose`, create the directory (mode 0700)
#              and merge env.CLAUDE_CODE_TMPDIR into the user settings file ONLY with consent:
#              `apply --yes` (the agent asked), or a `y` answer at the [y/N] prompt on a terminal.
#              Prints RESULT=written|unchanged|declined|opted-out. Exit 2 when the settings file
#              cannot be edited safely (not a JSON object, or its `env` is not one).
#
# CONFIG PATHS:
#   CLAUDE_CONFIG_DIR   Claude's config dir (default ~/.claude)
#   CLAUDE_SETTINGS     the USER settings file written (default $CLAUDE_CONFIG_DIR/settings.json)
#   ODOO_AI_HOME        the state root (default ~/.odoo-ai); the directory is its subfolder tmp
#
# HARD RULES:
#   - Writes only the USER settings file (the variable is ignored in project and local settings),
#     never without consent. The change applies to Claude Code sessions started afterwards.
#   - Never changes a value the user already set, in the environment or in the settings file.
#   - Opt out entirely with ODOO_AI_NO_CLAUDE_TMP=1.
#   - Idempotent: once set, check exits 0 and apply writes nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/claude_tmp.py"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
export CLAUDE_CONFIG_DIR="$CONFIG_DIR"
CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$CONFIG_DIR/settings.json}"
export CLAUDE_SETTINGS

_opted_out() { [[ "${ODOO_AI_NO_CLAUDE_TMP:-0}" == "1" ]]; }

_measure() {
    python3 "$LIB" measure
}

_get() {
    # $1 = KEY, stdin = measure output
    sed -n "s/^$1=//p" | head -n1
}

cmd_describe() {
    echo "Offer to move Claude Code's temp directory into the state root and sweep it"
}

cmd_check() {
    _opted_out && return 0
    local action
    action="$(_measure | _get ACTION)" || action=""
    [[ "$action" == "propose" ]] && return 1
    return 0
}

_question() {
    # $1 = measure output
    local out="$1" root backed target days where
    root="$(_get CURRENT_TEMP_ROOT <<<"$out")"
    backed="$(_get CURRENT_TEMP_MEMORY_BACKED <<<"$out")"
    target="$(_get TARGET <<<"$out")"
    days="$(_get SWEEP_MAX_AGE_DAYS <<<"$out")"
    where="the system temp directory${root:+ ($root)}"
    case "$backed" in
        yes) where="$where, which is memory-backed" ;;
        no)  where="$where, which is on disk" ;;
    esac
    echo "Claude Code keeps its scratchpads, task output and images in ${where}, and never" \
        "deletes them; set CLAUDE_CODE_TMPDIR to ${target} in your user settings so they live" \
        "there instead, and let this plugin delete session folders there that nothing touched" \
        "for ${days} days when a session ends? It applies to Claude Code sessions started" \
        "after the change."
}

cmd_propose() {
    if _opted_out; then
        echo "ACTION=opted-out"
        return 0
    fi
    local out action
    out="$(_measure)"
    printf '%s\n' "$out"
    action="$(_get ACTION <<<"$out")"
    case "$action" in
        propose)
            echo "QUESTION=$(_question "$out")"
            if [[ "$(_get SANDBOX_TMP_FALLBACK <<<"$out")" == "yes" ]]; then
                echo "NOTE=The per-user path under that directory is" \
                    "$(_get PER_UID_PATH_BYTES <<<"$out") bytes, over the" \
                    "$(_get SOCKET_PATH_LIMIT <<<"$out") Claude Code allows for sandboxed shell" \
                    "commands: it keeps its own files there and gives those commands a short" \
                    "fallback temp directory under the system temp directory. Nothing breaks."
            fi
            ;;
        set-in-environment|set-in-settings)
            echo "NOTE=Claude Code's temp directory is already set by you - nothing to do." ;;
        settings-invalid)
            echo "NOTE=The user settings file is not a JSON object (or its env is not one);" \
                "fix it first, setup will not edit it." ;;
    esac
}

cmd_apply() {
    local yes=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes) yes=1 ;;
        esac
        shift
    done
    if _opted_out; then
        echo "RESULT=opted-out"
        echo "Skipped Claude Code temp directory (ODOO_AI_NO_CLAUDE_TMP=1)."
        return 0
    fi
    local out action target
    out="$(_measure)"
    action="$(_get ACTION <<<"$out")"
    if [[ "$action" == "settings-invalid" ]]; then
        echo "RESULT=refused"
        echo "Refusing to edit $CLAUDE_SETTINGS: not a JSON object (or its env is not one)." >&2
        return 2
    fi
    if [[ "$action" != "propose" ]]; then
        echo "RESULT=unchanged"
        echo "Nothing to write (decision: $action)."
        return 0
    fi
    target="$(_get TARGET <<<"$out")"
    if [[ "$yes" -ne 1 ]]; then
        if [[ -t 0 ]]; then
            _question "$out"
            printf '[y/N] '
            local reply=""
            read -r reply || reply=""
            [[ "$reply" =~ ^[Yy] ]] || { echo "RESULT=declined"; echo "Not written."; return 0; }
        else
            echo "RESULT=declined"
            echo "Not written: no consent (run 'apply --yes' after the user agreed)."
            return 0
        fi
    fi
    local result
    result="$(python3 "$LIB" set "$CLAUDE_SETTINGS" "$target")"
    printf '%s\n' "$result"
    if [[ "$result" == *RESULT=written* ]]; then
        echo "Set CLAUDE_CODE_TMPDIR=$target in $CLAUDE_SETTINGS." \
            "It applies to Claude Code sessions started from now on."
    fi
}

main() {
    local sub="${1:-describe}"
    shift || true
    case "$sub" in
        describe) cmd_describe ;;
        check)    cmd_check "$@" ;;
        propose)  cmd_propose "$@" ;;
        apply)    cmd_apply "$@" ;;
        *) echo "usage: $0 describe|check|propose|apply [--yes]" >&2; return 2 ;;
    esac
}

main "$@"
