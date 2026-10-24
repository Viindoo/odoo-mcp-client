#!/usr/bin/env bash
# 75-youtube.sh - Configure the YouTube channels a run publishes videos to, by purpose (docs,
# marketing, ...), through the YouTube Data API v3. Writes the machine-global, never-committed
# `youtube.toml` in the state root; the OAuth values live in the plugin's configured options
# (Claude Code's own dialog), which only the odoo-media MCP server receives.
#
#   propose   prints what the operator prepares on the Google side, the slots, the declared channels
#   record    --channel P --from-json FILE  validates ONE channel table and merges it
#   remove    --channel P
#   consent   --channel P --client-json FILE  (OPERATOR-run, in a terminal: the loopback consent
#             flow that obtains the channel's refresh token and stores it with the client values in
#             the plugin configuration; prints nothing of them)
#   show      prints the configuration as JSON
#
# Subcommands: describe | check [--channel P] | apply | propose | record | remove | consent | show
#   check   exit 0 when youtube.toml is valid (and names P); 1 otherwise. Whether the configured
#           values are present, and whether they work, is the odoo-media youtube_check tool's job.
#   apply   advise-only; writes nothing.
#
# CONFIG:
#   ODOO_AI_HOME   machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/youtube_config.py"
OAUTH="$SCRIPT_DIR/../lib/youtube_oauth.py"

cmd_describe() {
    echo "Configure the YouTube channels videos are published to, by purpose (docs, marketing), in youtube.toml, confirmed by you; the consent for each channel runs in your own terminal"
}

cmd_check() {
    python3 "$LIB" check "$@"
}

cmd_apply() {
    if python3 "$LIB" check >/dev/null 2>&1; then
        echo "ok YouTube channels declared"
        return 0
    fi
    echo "YouTube not configured. Run: $0 propose, prepare the Google side, confirm one channel per purpose, then"
    echo "  $0 record --channel <purpose> --from-json <file>   (the setup command drives this; nothing is written here)"
    echo "  $0 consent --channel <purpose> --client-json <file>  (you run this one yourself, in a terminal)"
    return 1
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    shift; cmd_check "$@" ;;
    apply)    cmd_apply ;;
    propose)  shift; python3 "$LIB" propose "$@" ;;
    record)   shift; python3 "$LIB" record "$@" ;;
    remove)   shift; python3 "$LIB" remove "$@" ;;
    consent)  shift; python3 "$OAUTH" consent "$@" ;;
    show)     shift; python3 "$LIB" show "$@" ;;
    *) echo "usage: $0 {describe|check [--channel P]|apply|propose|record --channel P --from-json FILE|remove --channel P|consent --channel P --client-json FILE|show}" >&2; exit 2 ;;
esac
