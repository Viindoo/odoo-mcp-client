#!/usr/bin/env bash
# odoo_cli_facts.sh - Source-only helper: the command-line facts of the Odoo checkout a launcher
# runs from, READ from that checkout (odoo_source_facts.py cli-facts), never keyed on a series
# number. Shared by 50-instance-spinup.sh (odoo.conf port key, --dev shape) and
# 55-instance-ops.sh (port flag, demo flag, logger namespace, the i18n export command line).
#
# Usage (source-only):
#   odoo_cli_facts <odoo_root>
#       Sets, for the checkout at <odoo_root> (the directory holding odoo-bin / openerp-server):
#         ODOO_CLI_CORE_PACKAGE     odoo | openerp   (also the root of Odoo's logger namespace)
#         ODOO_CLI_DEMO_OPT_IN      1 (config.py declares --with-demo: no demo unless asked)
#                                   0 (only --without-demo: demo loads by default)
#                                   empty (neither declared)
#         ODOO_CLI_WITHOUT_DEMO     1 when config.py declares --without-demo (a build can
#                                   spell "no demo" explicitly), else 0
#         ODOO_CLI_HTTP_PORT_KEY    main port odoo.conf key: http_port | xmlrpc_port
#         ODOO_CLI_SECOND_PORT_KEY  second port odoo.conf key: gevent_port | longpolling_port
#         ODOO_CLI_DEV_TAKES_VALUE  1 when `--dev=all` is valid, else 0
#       Returns 1 with the reason on stderr (every variable empty) when the checkout's
#       tools/config.py is unreadable - a caller that needs a fact refuses then, it never guesses.
#   odoo_i18n_facts <odoo_root>
#       Sets the command line that exports one module's translation file on that checkout
#       (odoo_source_facts.py i18n-facts): ODOO_I18N_FORM = server | subcommand, and
#         server:     ODOO_I18N_EXPORT_FLAG, ODOO_I18N_MODULES_FLAG, ODOO_I18N_LANGUAGE_FLAG
#         subcommand: ODOO_I18N_COMMAND, ODOO_I18N_SUBCOMMAND, ODOO_I18N_CONFIG_FLAG,
#                     ODOO_I18N_DATABASE_FLAG, ODOO_I18N_OUTPUT_FLAG, ODOO_I18N_LANGUAGES_FLAG
#       Returns 1 with the reason on stderr (every variable empty) when the checkout declares
#       neither form - the caller refuses then, it never guesses.
#   odoo_cli_flag <key>
#       The odoo-bin flag of an odoo.conf key: `--` + key with `_` spelled `-`.
#   odoo_isolated_rc_env <conf>
#       Export, in the calling (sub)shell, the environment under which an Odoo launched from it
#       reads <conf> - and no other config file. `-c <conf>` alone is not enough before 19.0:
#       config.py builds its singleton at IMPORT time by parsing an empty command line, which
#       loads the default rc file (~/.odoorc / ~/.openerp_serverrc) into the options, and the
#       later `-c <conf>` load only overrides the keys <conf> states - every other key of the
#       operator's rc (without_demo, data_dir, db_*, ...) survives. That import-time load reads
#       $ODOO_RC (checked first from 10.0) or, on the `openerp` core package, $OPENERP_SERVER
#       before the default file, so both name <conf>. On the `odoo` package OPENERP_SERVER is
#       exported EMPTY: never read there (19.0+ only warns when it is non-empty). Needs
#       odoo_cli_facts run first (ODOO_CLI_CORE_PACKAGE).
#
# Portable to bash 3.2 (macOS).

_ODOO_CLI_FACTS_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odoo_source_facts.py"

odoo_cli_facts() {
    ODOO_CLI_CORE_PACKAGE=""
    ODOO_CLI_DEMO_OPT_IN=""
    ODOO_CLI_WITHOUT_DEMO=""
    ODOO_CLI_HTTP_PORT_KEY=""
    ODOO_CLI_SECOND_PORT_KEY=""
    ODOO_CLI_DEV_TAKES_VALUE=""
    local _ocf_out _ocf_line
    _ocf_out="$("${PY3:-python3}" "$_ODOO_CLI_FACTS_PY" cli-facts "${1:-}")" || return 1
    while IFS= read -r _ocf_line; do
        case "$_ocf_line" in
            CORE_PACKAGE=*)    ODOO_CLI_CORE_PACKAGE="${_ocf_line#*=}" ;;
            DEMO_OPT_IN=*)     ODOO_CLI_DEMO_OPT_IN="${_ocf_line#*=}" ;;
            WITHOUT_DEMO=*)    ODOO_CLI_WITHOUT_DEMO="${_ocf_line#*=}" ;;
            HTTP_PORT_KEY=*)   ODOO_CLI_HTTP_PORT_KEY="${_ocf_line#*=}" ;;
            SECOND_PORT_KEY=*) ODOO_CLI_SECOND_PORT_KEY="${_ocf_line#*=}" ;;
            DEV_TAKES_VALUE=*) ODOO_CLI_DEV_TAKES_VALUE="${_ocf_line#*=}" ;;
        esac
    done <<<"$_ocf_out"
    return 0
}

odoo_i18n_facts() {
    ODOO_I18N_FORM=""
    ODOO_I18N_EXPORT_FLAG=""
    ODOO_I18N_MODULES_FLAG=""
    ODOO_I18N_LANGUAGE_FLAG=""
    ODOO_I18N_COMMAND=""
    ODOO_I18N_SUBCOMMAND=""
    ODOO_I18N_CONFIG_FLAG=""
    ODOO_I18N_DATABASE_FLAG=""
    ODOO_I18N_OUTPUT_FLAG=""
    ODOO_I18N_LANGUAGES_FLAG=""
    local _oif_out _oif_line
    _oif_out="$("${PY3:-python3}" "$_ODOO_CLI_FACTS_PY" i18n-facts "${1:-}")" || return 1
    while IFS= read -r _oif_line; do
        case "$_oif_line" in
            I18N_FORM=*)            ODOO_I18N_FORM="${_oif_line#*=}" ;;
            I18N_EXPORT_FLAG=*)     ODOO_I18N_EXPORT_FLAG="${_oif_line#*=}" ;;
            I18N_MODULES_FLAG=*)    ODOO_I18N_MODULES_FLAG="${_oif_line#*=}" ;;
            I18N_LANGUAGE_FLAG=*)   ODOO_I18N_LANGUAGE_FLAG="${_oif_line#*=}" ;;
            I18N_COMMAND=*)         ODOO_I18N_COMMAND="${_oif_line#*=}" ;;
            I18N_SUBCOMMAND=*)      ODOO_I18N_SUBCOMMAND="${_oif_line#*=}" ;;
            I18N_CONFIG_FLAG=*)     ODOO_I18N_CONFIG_FLAG="${_oif_line#*=}" ;;
            I18N_DATABASE_FLAG=*)   ODOO_I18N_DATABASE_FLAG="${_oif_line#*=}" ;;
            I18N_OUTPUT_FLAG=*)     ODOO_I18N_OUTPUT_FLAG="${_oif_line#*=}" ;;
            I18N_LANGUAGES_FLAG=*)  ODOO_I18N_LANGUAGES_FLAG="${_oif_line#*=}" ;;
        esac
    done <<<"$_oif_out"
    return 0
}

odoo_cli_flag() {
    local _ocfl_key="${1:-}"
    echo "--${_ocfl_key//_/-}"
}

odoo_isolated_rc_env() {
    export ODOO_RC="${1:-}"
    if [[ "${ODOO_CLI_CORE_PACKAGE:-}" == "openerp" ]]; then
        export OPENERP_SERVER="${1:-}"
    else
        export OPENERP_SERVER=""
    fi
}
