#!/usr/bin/env bash
# odoo_port_keys.sh - Source-only helper: the era rule for Odoo's main listening port.
#
# SSOT for the main HTTP port's option name per series, shared by
# 50-instance-spinup.sh (the odoo.conf key it writes) and 55-instance-ops.sh
# (the odoo-bin flag it passes). Read from each series' odoo/tools/config.py
# option dest and confirmed with Odoo Semantic `cli_help server`: the option is
# `xmlrpc_port` (`--xmlrpc-port`) before 11.0 and `http_port` (`--http-port`)
# from 11.0 on.
#
# Usage (source-only):
#   odoo_http_port_key <series>    # prints xmlrpc_port | http_port
#   odoo_http_port_flag <series>   # prints --xmlrpc-port | --http-port
# A series whose major is not an integer (empty, "saas~17.2") gets the 11.0+
# name - the only one every series from 11.0 on accepts.
#
# Portable to bash 3.2 (macOS).

odoo_http_port_key() {
    local _ohpk_major="${1%%.*}"
    if [[ "$_ohpk_major" =~ ^[0-9]+$ ]] && (( _ohpk_major < 11 )); then
        echo "xmlrpc_port"
    else
        echo "http_port"
    fi
}

odoo_http_port_flag() {
    local _ohpf_key
    _ohpf_key="$(odoo_http_port_key "${1:-}")"
    echo "--${_ohpf_key//_/-}"
}
