#!/usr/bin/env bash
# 70-speech.sh - Configure narration for demo videos, vendor-neutral: an endpoint that
# speaks the OpenAI audio API (POST <base_url>/audio/speech, optional voice listing) for
# text-to-speech, a voice per narration language, and a speech-to-text endpoint
# (POST <base_url>/audio/transcriptions) that checks every narration clip against its
# script. Writes the machine-global, never-committed `speech.toml` in the state root.
#
# No credential value enters any file: the value the `bearer` mode sends is the plugin's
# configured option (Claude Code's own dialog), which only the odoo-media MCP server
# receives; `check` validates the configuration, and the odoo-media `media_info` and
# `speech_probe` tools say whether the value is present and whether the round trip works.
#
#   propose   prints the provider shapes this plugin knows (a gateway, hosted and
#             self-hosted), a gateway the operator exported as ODOO_AI_SPEECH_BASE_URL, and
#             whether ffmpeg has the filters the assembler needs. Writes nothing.
#   record    --from-json FILE  validates the operator-CONFIRMED configuration and writes it.
#             Refuses a value where a configuration key belongs, a voice recorded under two
#             languages, a non-locale language key.
#   show      prints the configuration as JSON.
#   probe     [--lang xx_YY]  the CLI round trip for a human with the value exported as
#             SPEECH_API_KEY; an agent calls the odoo-media speech_probe tool instead.
#
# Subcommands: describe | check | apply | propose | record | show | probe
#   check   exit 0 when speech.toml is valid; 1 otherwise.
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
    echo "Speech not configured. Run: $0 propose, confirm the endpoint, model, auth mode and a voice per language, then"
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
