#!/usr/bin/env bash
# 75-youtube.sh - Configure where documentation videos are published: the YouTube channel
# an organisation or a person owns, through the YouTube Data API v3. Writes the
# machine-global, never-committed `youtube.toml` in the state root.
#
# No secret enters any file: the configuration names the ENVIRONMENT VARIABLES holding the
# OAuth client id, client secret and refresh token; `check` verifies they are set.
#
#   propose   prints what the operator prepares (Cloud project, Desktop OAuth client, a refresh
#             token with the upload scope, a published consent screen) and which variables are
#             already set (names only). Writes nothing.
#   record    --from-json FILE  validates the operator-CONFIRMED configuration and writes it.
#   show      prints it as JSON.
#
# Subcommands: describe | check | apply | propose | record | show
#   check   exit 0 when youtube.toml is valid and every variable is set; 1 otherwise.
#   apply   advise-only; writes nothing.
#
# CONFIG:
#   ODOO_AI_HOME   machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/youtube_config.py"

cmd_describe() {
    echo "Configure the YouTube channel documentation videos are published to (OAuth variable names, default privacy, playlist) in youtube.toml, confirmed by you"
}

cmd_check() {
    python3 "$LIB" check
}

cmd_apply() {
    if python3 "$LIB" check >/dev/null 2>&1; then
        echo "ok YouTube configuration declared"
        return 0
    fi
    echo "YouTube not configured. Run: $0 propose, prepare the OAuth client and refresh token, confirm the values, then"
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
    *) echo "usage: $0 {describe|check|apply|propose|record --from-json FILE|show}" >&2; exit 2 ;;
esac
