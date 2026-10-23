#!/usr/bin/env bash
# 70-speech.sh - Configure narration for demo videos, vendor-neutral: an endpoint that
# speaks the OpenAI audio API (POST <base_url>/audio/speech, optional voice listing) for
# text-to-speech, a voice per narration language, and a speech-to-text endpoint
# (POST <base_url>/audio/transcriptions) that checks every narration clip against its
# script. Writes the machine-global, never-committed `speech.toml` in the state root.
#
# The key itself never enters any file: the configuration names the ENVIRONMENT VARIABLE
# that holds it, and `check` verifies the variable is set in the current shell.
#
#   propose   prints the provider shapes this plugin knows (hosted and self-hosted), which
#             known key variables are set on this machine (names only), and whether ffmpeg
#             has the filters the assembler needs. Writes nothing.
#   record    --from-json FILE  validates the operator-CONFIRMED configuration and writes it.
#             Refuses a key where a variable name belongs, a voice recorded under two
#             languages, a non-locale language key.
#   show      prints the configuration as JSON.
#   probe     [--lang xx_YY]  synthesises one short sentence per configured language (one
#             call each - run it only when the operator agrees) and prints each clip's path
#             and duration; exit 1 when a language fails.
#
# Subcommands: describe | check | apply | propose | record | show | probe
#   check   exit 0 when speech.toml is valid and every key variable is set; 1 otherwise.
#   apply   advise-only: says what to run; writes nothing.
#
# CONFIG:
#   ODOO_AI_HOME   machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/speech_config.py"
CLIENT="$SCRIPT_DIR/../lib/speech_client.py"

cmd_describe() {
    echo "Configure narration voices for demo videos: an OpenAI-compatible speech endpoint, a voice per language, the speech-to-text check (speech.toml), confirmed by you"
}

cmd_check() {
    python3 "$LIB" check
}

cmd_apply() {
    if python3 "$LIB" check >/dev/null 2>&1; then
        echo "ok speech configuration declared"
        return 0
    fi
    echo "Speech not configured. Run: $0 propose, confirm the endpoint, model, key variable NAME and a voice per language, then"
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
    probe)    shift; python3 "$CLIENT" probe "$@" ;;
    *) echo "usage: $0 {describe|check|apply|propose|record --from-json FILE|show|probe [--lang xx_YY]}" >&2; exit 2 ;;
esac
