#!/usr/bin/env bash
# 05-prereq-check.sh - Prerequisite gate. Detect (read-only, never sudo) the
# host tools setup CANNOT provision for you, and print a checklist the user
# must satisfy before the instance/browser steps can succeed.
#
# It splits requirements into:
#   AUTO-DETECTED   - probed here (Node, Python, PostgreSQL running, curl,
#                     docker, ffmpeg, Odoo repos under ODOO_GIT_BASE)
#   NEEDS CONFIRM   - cannot be detected (PostgreSQL role/password, system
#                     build deps, an Odoo venv with deps installed)
#
# This script NEVER installs anything and NEVER runs sudo. The setup command
# turns the checklist into an explicit "ready / skip instance / cancel" prompt.
#
# CONFIG (env overrides):
#   ODOO_GIT_BASE   where Odoo repos are cloned (default ~/git)
#   SETUP_FILTER    all | browser | instance (tailors which items are required)
#
# Subcommands: describe | check | apply
#   check  -> exit 0 only if every REQUIRED auto-detected item is present.
#   apply  -> print the full checklist (auto-detected + needs-confirm).

set -euo pipefail

ODOO_GIT_BASE="${ODOO_GIT_BASE:-$HOME/git}"
SETUP_FILTER="${SETUP_FILTER:-all}"

cmd_describe() {
    echo "Check host prerequisites setup cannot install for you (Node, PostgreSQL, Odoo repos, Python)"
}

_have() { command -v "$1" >/dev/null 2>&1; }

# True when the instance steps (40/50) are in scope for the active filter.
_needs_instance() { [[ "$SETUP_FILTER" == "all" || "$SETUP_FILTER" == "instance" ]]; }
# True when the browser steps (10/20) are in scope.
_needs_browser() { [[ "$SETUP_FILTER" == "all" || "$SETUP_FILTER" == "browser" || "$SETUP_FILTER" == "runtime" ]]; }

# Node major version, or empty.
_node_major() {
    _have node || return 0
    node --version 2>/dev/null | sed -E 's/^v?([0-9]+).*/\1/'
}

# Minimum Claude Code version for nested subagent dispatch (the odoo-coder per-module coordinator,
# launched for EVERY module, launches odoo-backend-coder and/or odoo-frontend-coder one agent level
# below odoo-coding; the platform enforces a depth cap of 5). This is NOT the experimental
# agent-teams flag - SendMessage coordinator<->worker works without it.
CC_MIN_VERSION="2.1.172"

# Claude Code version (e.g. "2.1.172"), or empty if the CLI is absent.
_cc_version() {
    _have claude || return 0
    claude --version 2>/dev/null | sed -E 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/\1/' | head -1
}

# 0 = detected version >= CC_MIN_VERSION (dotted numeric compare via sort -V); non-zero otherwise.
_cc_version_ok() {
    local v; v="$(_cc_version)"
    [[ -n "$v" ]] || return 1
    [[ "$(printf '%s\n%s\n' "$CC_MIN_VERSION" "$v" | sort -V | head -1)" == "$CC_MIN_VERSION" ]]
}

# 0 = at least one Odoo repo (odoo-bin or __manifest__.py) under ODOO_GIT_BASE.
_repos_present() {
    [[ -d "$ODOO_GIT_BASE" ]] || return 1
    find "$ODOO_GIT_BASE" -maxdepth 4 \( -name odoo-bin -o -name __manifest__.py \) \
        -print -quit 2>/dev/null | grep -q .
}

cmd_check() {
    # Exit 0 only if every REQUIRED auto-detected item for the active filter is
    # present. Needs-confirm items never block `check` (only the AI prompt does).
    local nm
    if _needs_browser; then
        nm="$(_node_major)"
        [[ -n "$nm" && "$nm" -ge 20 ]] || return 1
        _have npx || return 1
    fi
    if _needs_instance; then
        _have python3 || return 1
        _have curl || return 1
        if _have pg_isready; then
            pg_isready -q 2>/dev/null || return 1
        fi
        _repos_present || return 1
    fi
    return 0
}

_mark() { if "$@" >/dev/null 2>&1; then printf '[ok ]'; else printf '[ -- ]'; fi; }

cmd_apply() {
    local nm ccv
    nm="$(_node_major)"
    ccv="$(_cc_version)"
    echo "============================================================"
    echo " Prerequisites for Odoo setup (filter: $SETUP_FILTER)"
    echo " setup never runs sudo and never installs system packages."
    echo "============================================================"
    echo
    echo "AUTO-DETECTED:"
    # Claude Code version gate - required for the coder coordinator's nested subagent dispatch.
    # Informational (never blocks `check`); an older CLI still runs everything else.
    if _cc_version_ok; then printf '  [ok ]'; else printf '  [ -- ]'; fi
    echo " Claude Code >= $CC_MIN_VERSION (nested subagent dispatch for the coder coordinator)  found: ${ccv:-none}"
    echo "         fix: update Claude Code to >= $CC_MIN_VERSION (do NOT set any experimental agent-teams flag)"
    if _needs_browser; then
        if [[ -n "$nm" && "$nm" -ge 20 ]]; then printf '  [ok ]'; else printf '  [ -- ]'; fi
        echo " Node.js >= 20 (browser MCP servers)  found: ${nm:-none}"
        echo "         fix: nvm install 20   or   https://nodejs.org"
        printf '  %s' "$(_mark _have npx)";  echo " npx (launches MCP servers)"
    fi
    if _needs_instance; then
        printf '  %s' "$(_mark _have python3)"; echo " python3 (runs odoo-bin in source mode)"
        echo "         fix: install python3, or 'uv python install <version>'"
        printf '  %s' "$(_mark _have curl)";    echo " curl (polls /web/login during spin-up)"
        if _have pg_isready; then
            printf '  %s' "$(_mark pg_isready -q)"; echo " PostgreSQL running (pg_isready)"
        else
            echo "  [ ?? ] PostgreSQL running (pg_isready not installed - cannot probe)"
        fi
        echo "         fix: start PostgreSQL, e.g. 'sudo systemctl start postgresql'"
        echo "              or 'docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass postgres:16'"
        printf '  %s' "$(_mark _repos_present)"; echo " Odoo repos under \${ODOO_GIT_BASE:-\$HOME/git} ($ODOO_GIT_BASE)"
        echo "         fix: git clone https://github.com/odoo/odoo -b 17.0 ~/git/odoo17"
        echo "              (or set ODOO_GIT_BASE to where your repos live)"
        printf '  %s' "$(_mark _have docker)";   echo " docker (optional - only for run_mode=docker)"
        printf '  %s' "$(_mark _have ffmpeg)";   echo " ffmpeg (optional - pagecast video/GIF recording)"
    fi
    echo
    echo "NEEDS YOUR CONFIRMATION (cannot be auto-detected):"
    if _needs_instance; then
        echo "  [ ] PostgreSQL role with CREATEDB exists for your db_user (default: odoo)"
        echo "        e.g. createuser --createdb --login odoo"
        echo "  [ ] DB password exported as ODOO_PG_PASSWORD (skip if using trust auth)"
        echo "  [ ] System build deps installed (only if you build a fresh venv):"
        echo "        build-essential python3-dev libxml2-dev libxslt1-dev libpq-dev"
        echo "        libldap2-dev libsasl2-dev libssl-dev libjpeg-dev zlib1g-dev"
        echo "  [ ] An Odoo venv with requirements installed (or let step 45 build one)"
    fi
    echo
    echo "Required AUTO-DETECTED items marked [ -- ] must be fixed before continuing."
    echo "Items marked [ ] only affect the instance spin-up step."
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
