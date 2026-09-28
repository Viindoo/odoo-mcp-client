#!/usr/bin/env bash
# 46-server-wide.sh - Propose, then record, the server-wide modules of a declared
# Odoo instance: the catalog row's `server_wide_modules` array.
#
# Which addons a site must load server-wide (Odoo's `--load`) is a DEPLOYMENT
# fact: it depends on the addons the row serves, not on the Odoo series. Odoo's
# own core default (`base,web`, ...) is a SOURCE fact the tools read from the
# checkout and always apply - it is never recorded here. This step only keeps
# the deployment's ADDITIONS, and only after the operator confirms them:
#
#   propose  gathers the evidence it can read locally -
#              (a) modules on the row's addons_path whose own code checks their
#                  name against `server_wide_modules` (a self-declared need),
#              (b) the "should be loaded in server wide mode" warnings found in
#                  the build logs passed with --log (a probe build's log),
#              (c) what the row already declares (never dropped silently - an
#                  operator-added module leaves no trace in code or log);
#            and prints the union minus the core default as the proposal.
#            Candidates from Odoo Semantic and the operator's own additions are
#            merged by the caller (the /odoo-setup command) before `record`.
#   record   writes the CONFIRMED list onto the row (upsert: every other key,
#            comment and block is kept; atomic write). `--modules ""` records the
#            empty array - a confirmed "none", distinct from "never asked".
#
# Subcommands:
#   describe
#   check      exit 0 when every declared [[instance]] row carries
#              server_wide_modules (the empty array counts); 1 otherwise, naming
#              the rows still to confirm.
#   apply      advise-only: prints the proposal for every row still to confirm
#              and how to record it. Writes nothing (confirmation is the
#              operator's, never a shell step's). Exit status as `check`.
#   propose --series X.Y [--profile P] [--log FILE ...]
#   record  --series X.Y [--profile P] --modules a,b,c
#
# CONFIG:
#   ODOO_AI_HOME       machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml (tests / custom)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
IO="$SCRIPT_DIR/../lib/instances_io.py"
FACTS="$SCRIPT_DIR/../lib/odoo_source_facts.py"
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
INSTANCES_TOML="$(_resolve_instances)"

cmd_describe() {
    echo "Propose and record each declared instance's server-wide modules (--load additions), confirmed by you"
}

# _rows <mode> [args...]: the catalog questions, answered in ONE place.
#   _rows pending            -> one "series<TAB>profile" line per row lacking the key
#   _rows propose S P LOG... -> KEY=VALUE facts for row (S, P)
_rows() {
    python3 - "$IO" "$FACTS" "$INSTANCES_TOML" "$@" <<'PY'
import importlib.util
import os
import shlex
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


io = load("instances_io", sys.argv[1])
facts = load("odoo_source_facts", sys.argv[2])
catalog, mode, rest = sys.argv[3], sys.argv[4], sys.argv[5:]
KEY = "server_wide_modules"

try:
    items = io.load_instances(catalog)
except FileNotFoundError:
    items = []
except (OSError, ValueError) as exc:
    print("x %s could not be read as an instance catalog: %s" % (catalog, exc), file=sys.stderr)
    sys.exit(3)

if mode == "pending":
    for it in items:
        if KEY not in it:
            print("%s\t%s" % (io.series_of(it), io.profile_of(it)))
    sys.exit(0)

series, profile, logs = rest[0], rest[1], rest[2:]
label = "%s:%s" % (series, profile) if profile else series
row, reason = io.select_row(items, series, profile)
if row is None:
    print("x %s (catalog: %s)." % (reason, catalog), file=sys.stderr)
    sys.exit(1)

addons = io.addons_path_list(row)
root = facts.locate_odoo_root(row.get("odoo_root"), addons) or ""
core = facts.core_server_wide_modules(root) if root else None
current = io.server_wide_modules_of(row)
self_declared = facts.self_declared_server_wide(addons)
text = []
for path in logs:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text.append(fh.read())
    except OSError as exc:
        print("x cannot read log %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(2)
warned = facts.server_wide_warning_modules("\n".join(text))
core_set = set(core or [])
proposed = sorted((set(current) | set(self_declared) | set(warned)) - core_set)
undetected = sorted(set(current) - set(self_declared) - set(warned) - core_set)


def emit(key, value):
    if isinstance(value, (list, tuple)):
        value = ",".join(value)
    print("%s=%s" % (key, shlex.quote(str(value))))


emit("ROW", label)
emit("ODOO_ROOT", root)
emit("CORE_SERVER_WIDE_MODULES", core if core is not None else "")
emit("CORE_READABLE", "1" if core is not None else "0")
emit("DECLARED", "1" if KEY in row else "0")
emit("CURRENT_SERVER_WIDE_MODULES", current)
emit("SELF_DECLARED_SERVER_WIDE", self_declared)
emit("LOG_WARNINGS", warned)
emit("UNDETECTED_CURRENT", undetected)
emit("PROPOSED_SERVER_WIDE_MODULES", proposed)
PY
}

cmd_check() {
    [[ -f "$INSTANCES_TOML" ]] || return 1
    local pending
    pending="$(_rows pending)" || return 1
    [[ -z "$pending" ]] && return 0
    local series profile
    while IFS=$'\t' read -r series profile; do
        echo "  server_wide_modules not confirmed yet: ${series}${profile:+:$profile}"
    done <<<"$pending"
    return 1
}

cmd_propose() {
    local series="" profile=""
    local -a logs=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) series="${2:-}"; shift 2 ;;
            --profile) profile="${2:-}"; shift 2 ;;
            --log) logs+=("${2:-}"); shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$series" ]] || { echo "x --series is required (e.g. --series 17.0)" >&2; return 2; }
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare the instance first (step 40)." >&2
        return 1
    }
    _rows propose "$series" "$profile" "${logs[@]+"${logs[@]}"}"
}

cmd_record() {
    local series="" profile="" modules="" have_modules=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) series="${2:-}"; shift 2 ;;
            --profile) profile="${2:-}"; shift 2 ;;
            --modules) modules="${2:-}"; have_modules=1; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$series" ]] || { echo "x --series is required (e.g. --series 17.0)" >&2; return 2; }
    [[ "$have_modules" -eq 1 ]] || {
        echo "x --modules is required: the operator-confirmed list (comma-separated;" >&2
        echo "  --modules \"\" records a confirmed none). Nothing was recorded." >&2
        return 2
    }
    local -a clean=()
    local m seen=","
    IFS=',' read -r -a _mods <<<"$modules"
    for m in "${_mods[@]+"${_mods[@]}"}"; do
        m="${m//[[:space:]]/}"
        [[ -n "$m" ]] || continue
        if [[ ! "$m" =~ ^[A-Za-z0-9_]+$ ]]; then
            echo "x '$m' is not an Odoo module name (letters, digits, underscore). Nothing was recorded." >&2
            return 2
        fi
        [[ "$seen" == *",$m,"* ]] && continue
        seen+="$m,"
        clean+=("$m")
    done
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare the instance first (step 40)." >&2
        return 1
    }
    local joined=""
    [[ "${#clean[@]}" -gt 0 ]] && joined="$(IFS=','; printf '%s' "${clean[*]}")"
    python3 "$LIB" toml-upsert-instance-keys "$INSTANCES_TOML" "$series" "$profile" \
        "server_wide_modules[]=$joined"
}

cmd_apply() {
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare an instance first (step 40)." >&2
        return 1
    }
    local pending series profile
    pending="$(_rows pending)" || return 1
    if [[ -z "$pending" ]]; then
        echo "  every declared instance already carries a confirmed server_wide_modules - no change"
        return 0
    fi
    while IFS=$'\t' read -r series profile; do
        echo "---- ${series}${profile:+:$profile}: proposal (NOT recorded - confirm first)"
        cmd_propose --series "$series" ${profile:+--profile "$profile"} || true
        echo "  record after confirmation:"
        echo "    $(basename "$0") record --series $series${profile:+ --profile $profile} --modules <a,b,...>"
    done <<<"$pending"
    return 1
}

# --- interpreter preflight (SSOT: scripts/lib/require_python.sh) ---------------------------
_REQ_PY="$SCRIPT_DIR/../lib/require_python.sh"
if [[ -r "$_REQ_PY" ]]; then
    # shellcheck source=/dev/null
    . "$_REQ_PY"
    case "${1:-}" in
        describe|-h|--help|"") ;;
        *) require_python3 "$(basename "$0") ${1:-}" || exit 2 ;;
    esac
fi

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    propose)  shift; cmd_propose "$@" ;;
    record)   shift; cmd_record "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|propose --series X.Y [--profile P] [--log FILE]...|record --series X.Y [--profile P] --modules a,b}" >&2; exit 2 ;;
esac
