#!/usr/bin/env bash
# 60-docs-site.sh - Propose, then record, a product documentation site: the
# machine-global, never-committed `docs-sites.toml` in the state root (next to
# instances.toml) that the odoo-doc-site skill reads.
#
# One `[[site]]` row per docs repository: its upstream remote, the remote feature
# branches are pushed to, the languages (source first), the audience, per series the
# local clone and the capture instance, optionally the code repositories the site
# documents (`repos`, operator-stated, never guessed), and the site policy (banned
# terms, marketplace link pattern, demo company, commit style and when the check shot runs). Which of
# that is a FACT of the repository is derived; the rest is the operator's and is never
# guessed:
#
#   propose  reads the clone (git READ only) and prints KEY=VALUE facts - origin URL,
#            fork candidates (the remotes the user pushes to), series branches, the
#            languages the repo states, sibling clones per series, the catalog instances
#            per series - plus POLICY_FIELDS_TO_CONFIRM. Writes nothing.
#   record   validates the operator-CONFIRMED row (JSON) and upserts that one row. Every
#            other row and every comment outside it is kept; backup, then atomic write.
#            Refuses unknown keys, an instance the catalog does not declare and a
#            marketplace_url lacking {series} and {module}.
#   show     prints the declared row(s) as JSON for a skill to read.
#
# Subcommands:
#   describe
#   check      exit 0 when a site is declared and every row is complete and valid;
#              1 otherwise (no file: one line naming the remedy); 2 on an unreadable file.
#   apply      advise-only: says what to run; writes nothing (confirmation is the
#              operator's, never a shell step's). Exit status as `check`.
#   propose --repo PATH [--key K]
#   record  --key K --from-json FILE
#   show    [--key K]
#
# CONFIG:
#   ODOO_AI_HOME       machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml (tests / custom)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/docs_site_config.py"
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
INSTANCES_TOML="$(_resolve_instances)"

cmd_describe() {
    echo "Declare a product docs site (repo, series, capture instance, site policy) in docs-sites.toml, confirmed by you"
}

cmd_check() {
    python3 "$LIB" check --instances "$INSTANCES_TOML"
}

cmd_propose() {
    local repo="$PWD" key=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) repo="${2:-}"; shift 2 ;;
            --key) key="${2:-}"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$repo" ]] || { echo "x --repo needs the path of a local clone of the docs repo" >&2; return 2; }
    python3 "$LIB" propose --repo "$repo" ${key:+--key "$key"} --instances "$INSTANCES_TOML"
}

cmd_record() {
    local key="" file=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --key) key="${2:-}"; shift 2 ;;
            --from-json) file="${2:-}"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$key" && -n "$file" ]] || {
        echo "x record needs --key <id> and --from-json <file> (the operator-confirmed row). Nothing was recorded." >&2
        return 2
    }
    python3 "$LIB" record --key "$key" --from-json "$file" --instances "$INSTANCES_TOML"
}

cmd_show() {
    local key=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --key) key="${2:-}"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    python3 "$LIB" show ${key:+--key "$key"}
}

cmd_apply() {
    if cmd_check; then
        echo "  every declared docs site is complete - no change"
        return 0
    fi
    echo "  declare or complete a site, then record it after the operator confirms:"
    echo "    $(basename "$0") propose --repo <path of a local clone of the docs repo> [--key <id>]"
    echo "    $(basename "$0") record --key <id> --from-json <file>"
    return 1
}

# --- interpreter preflight (SSOT: scripts/lib/require_python.sh) ---------------------------
# docs_site_config.py reads docs-sites.toml with tomllib when present and with its own reader of
# the subset it writes otherwise, so this step asks for a working python3 only.
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
    propose)  shift; cmd_propose "$@" ;;
    record)   shift; cmd_record "$@" ;;
    show)     shift; cmd_show "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|propose --repo PATH [--key K]|record --key K --from-json FILE|show [--key K]}" >&2; exit 2 ;;
esac
