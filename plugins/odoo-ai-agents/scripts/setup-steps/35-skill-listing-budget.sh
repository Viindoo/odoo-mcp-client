#!/usr/bin/env bash
# 35-skill-listing-budget.sh - Offer to raise Claude Code's skill-listing budget when it overflows.
#
# Every turn the model sees ONE listing of the session's skills and their descriptions, capped at a
# share of the context window. Over the cap, Claude Code keeps every name but drops descriptions,
# so the model rarely picks those skills on its own. This step measures the session's listing
# (scripts/lib/skill_listing.py holds the counting, the sources and the decision) and, only when
# it overflows, proposes a `skillListingBudgetFraction` for the USER settings file.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 when nothing is to do (fits, opted out, or decided elsewhere); 1 to propose.
#   propose    Print the measurement and the decision as KEY=VALUE lines plus one plain
#              sentence (QUESTION=...) for the agent to put to the user. Writes nothing.
#   apply      Re-measure; when the decision is still `propose`, write the fraction to the user
#              settings file ONLY with consent: `apply --yes` (the agent asked), or a `y` answer
#              at the [y/N] prompt on a terminal. Without either, nothing is written.
#
# Options (propose/apply): --window TOKENS  the model's context window (default: from the CLI's
#              debug log when it has a measurement, else the 200k window).
#
# CONFIG PATHS:
#   CLAUDE_CONFIG_DIR   Claude's config dir (default ~/.claude): plugins registry, user skills
#   CLAUDE_SETTINGS     the USER settings file written (default $CLAUDE_CONFIG_DIR/settings.json)
#
# HARD RULES:
#   - Writes only the USER settings file, never a project or local one, and never without consent.
#   - Never lowers a fraction: a value at or above the proposal is left untouched.
#   - Opt out entirely with ODOO_AI_NO_LISTING_BUDGET=1.
#   - Idempotent: once the listing fits, check exits 0 and apply writes nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/skill_listing.py"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
export CLAUDE_CONFIG_DIR="$CONFIG_DIR"
CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$CONFIG_DIR/settings.json}"
export CLAUDE_SETTINGS

_opted_out() { [[ "${ODOO_AI_NO_LISTING_BUDGET:-0}" == "1" ]]; }

_measure() {
    python3 "$LIB" measure "$@"
}

_get() {
    # $1 = KEY, stdin = measure output
    sed -n "s/^$1=//p" | head -n1
}

cmd_describe() {
    echo "Offer to raise Claude Code's skill-listing budget when the session's skill descriptions overflow it"
}

cmd_check() {
    _opted_out && return 0
    local action
    action="$(_measure "$@" | _get ACTION)"
    [[ "$action" == "propose" ]] && return 1
    return 0
}

_question() {
    # $1 = measure output
    local out="$1" fraction extra tokens share window
    fraction="$(_get FRACTION <<<"$out")"
    extra="$(_get EXTRA_TOKENS <<<"$out")"
    tokens="$(_get LISTING_TOKENS <<<"$out")"
    share="$(_get WINDOW_SHARE_PCT <<<"$out")"
    window="$(_get WINDOW_TOKENS <<<"$out")"
    echo "Your skill list is larger than Claude Code shows by default, so most skills are shown to the model without their descriptions and it rarely picks them on its own; set skillListingBudgetFraction to ${fraction} in your user settings so every description is shown, adding about ${extra} tokens of context per turn (the whole list then takes about ${tokens} tokens, ${share}% of a ${window}-token window)?"
}

cmd_propose() {
    if _opted_out; then
        echo "ACTION=opted-out"
        return 0
    fi
    local out action
    out="$(_measure "$@")"
    printf '%s\n' "$out"
    action="$(_get ACTION <<<"$out")"
    case "$action" in
        propose)        echo "QUESTION=$(_question "$out")" ;;
        fits)           echo "NOTE=The skill listing fits its budget - nothing to do." ;;
        env-override)   echo "NOTE=SLASH_COMMAND_TOOL_CHAR_BUDGET fixes the listing budget in this environment; a setting would be ignored. Raise that variable instead." ;;
        scope-override) echo "NOTE=A project or local settings file sets skillListingBudgetFraction and overrides the user file; raise it there if you want more descriptions shown." ;;
    esac
}

cmd_apply() {
    local yes=0 args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes) yes=1 ;;
            *) args+=("$1") ;;
        esac
        shift
    done
    if _opted_out; then
        echo "Skipped skill-listing budget (ODOO_AI_NO_LISTING_BUDGET=1)."
        return 0
    fi
    local out action fraction
    out="$(_measure "${args[@]+"${args[@]}"}")"
    action="$(_get ACTION <<<"$out")"
    if [[ "$action" != "propose" ]]; then
        echo "Nothing to write (decision: $action)."
        return 0
    fi
    fraction="$(_get FRACTION <<<"$out")"
    if [[ "$yes" -ne 1 ]]; then
        if [[ -t 0 ]]; then
            _question "$out"
            printf '[y/N] '
            local reply=""
            read -r reply || reply=""
            [[ "$reply" =~ ^[Yy] ]] || { echo "Not written."; return 0; }
        else
            echo "Not written: no consent (run 'apply --yes' after the user agreed)."
            return 0
        fi
    fi
    python3 "$LIB" set "$CLAUDE_SETTINGS" "$fraction"
    echo "Set skillListingBudgetFraction=$fraction in $CLAUDE_SETTINGS. Restart Claude Code for it to apply."
}

main() {
    local sub="${1:-describe}"
    shift || true
    case "$sub" in
        describe) cmd_describe ;;
        check)    cmd_check "$@" ;;
        propose)  cmd_propose "$@" ;;
        apply)    cmd_apply "$@" ;;
        *) echo "usage: $0 describe|check|propose|apply [--yes] [--window TOKENS]" >&2; return 2 ;;
    esac
}

main "$@"
