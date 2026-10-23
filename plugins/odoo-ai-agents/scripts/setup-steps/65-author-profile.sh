#!/usr/bin/env bash
# 65-author-profile.sh - Propose, then record, the vendor's public contact profile:
# the machine-global, never-committed `author-profile.toml` in the state root that
# the documentation writers read for every published contact detail.
#
# Published docs and App Store pages carry no email address (they are public and
# indexed; an address there is harvested). Contact goes through two web pages the
# vendor states - a pre-sales page and a support/ticket page - and the store shows
# the manifest `support` address to purchasers only. This step records those values
# once, confirmed by the operator; the writers never invent them.
#
#   propose --addons DIR   reads the module descriptors under DIR (author, website,
#                          support) and prints KEY=VALUE candidates; writes nothing.
#   record  --from-json F  validates the operator-CONFIRMED profile and writes it
#                          (backup, atomic). Refuses an address in a URL field, a
#                          non-https or non-public URL, an unknown key.
#   show                   prints the profile as JSON for a skill to read.
#
# Subcommands: describe | check | apply | propose | record | show
#   check   exit 0 when a valid profile exists; 1 otherwise (remedy on stderr); 2 unreadable.
#   apply   advise-only: says what to run; writes nothing (confirmation is the operator's).
#
# CONFIG:
#   ODOO_AI_HOME   machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/author_profile_config.py"

cmd_describe() {
    echo "Record the vendor's public contact profile (pre-sales and support pages, manifest support address) in author-profile.toml, confirmed by you"
}

cmd_check() {
    python3 "$LIB" check
}

cmd_apply() {
    if python3 "$LIB" check >/dev/null 2>&1; then
        echo "ok author profile declared"
        return 0
    fi
    echo "Author profile not declared. Run: $0 propose --addons <addons dir>, confirm the values, then"
    echo "  $0 record --from-json <file>   (the setup command drives this; nothing is written here)"
    return 1
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    propose)  shift; python3 "$LIB" propose "$@" ;;
    record)   shift; python3 "$LIB" record "$@" ;;
    show)     shift; python3 "$LIB" show "$@" ;;
    *) echo "usage: $0 {describe|check|apply|propose --addons DIR|record --from-json FILE|show}" >&2; exit 2 ;;
esac
