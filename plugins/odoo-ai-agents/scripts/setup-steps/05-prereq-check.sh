#!/usr/bin/env bash
# 05-prereq-check.sh - Prerequisite gate. Detect (read-only, never sudo) the
# host tools setup CANNOT provision for you, and print a checklist the user
# must satisfy before the instance/browser steps can succeed.
#
# It splits requirements into:
#   AUTO-DETECTED   - probed here (Node, Python, PostgreSQL reachability and the
#                     db_user's CREATEDB capability, curl, docker, ffmpeg, Odoo
#                     repos under ODOO_GIT_BASE)
#   NEEDS CONFIRM   - cannot be detected (PostgreSQL password, system build deps,
#                     an Odoo venv with deps installed)
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"
ODOO_GIT_BASE="${ODOO_GIT_BASE:-$HOME/git}"
SETUP_FILTER="${SETUP_FILTER:-all}"
# addons_path separator SSOT mirror (_addons_path_to_array) - see
# scripts/lib/instances_io.py's join_addons_path/split_addons_path docstring.
# shellcheck source=../lib/resolve_instances.sh
source "$LIB_DIR/resolve_instances.sh"
# Postgres client dispatch (pg_run_client) + db_run_mode vocabulary SSOT.
# shellcheck source=../lib/pg_mode.sh
source "$LIB_DIR/pg_mode.sh"

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
# below odoo-coding; the platform enforces a depth cap of 5).
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

# Echo the resolved instances.toml path (read side), or return 1 if none exists.
_resolve_instances_path() {
    if [[ -n "${ODOO_AI_INSTANCES:-}" ]]; then printf '%s\n' "$ODOO_AI_INSTANCES"; return 0; fi
    if [[ -n "${ODOO_AI_HOME:-}" && -f "${ODOO_AI_HOME%/}/instances.toml" ]]; then
        printf '%s\n' "${ODOO_AI_HOME%/}/instances.toml"; return 0
    fi
    if [[ -n "${HOME:-}" && -f "${HOME%/}/.odoo-ai/instances.toml" ]]; then
        printf '%s\n' "${HOME%/}/.odoo-ai/instances.toml"; return 0
    fi
    if [[ -f "$PWD/.odoo-ai/instances.toml" ]]; then
        printf '%s\n' "$PWD/.odoo-ai/instances.toml"; return 0
    fi
    return 1
}

# Emit TAB-separated `series<TAB>python<TAB>addons_path` for each SOURCE-mode
# instance (missing run_mode defaults to source). Delegates to instances_io so
# the schema stays SSOT. Empty output when no toml / no source instances.
_enumerate_source_instances() {
    local toml="$1"
    [[ -f "$toml" ]] || return 0
    python3 - "$toml" "$LIB_DIR" <<'PY' 2>/dev/null || true
import os, sys
toml, libdir = sys.argv[1], sys.argv[2]
sys.path.insert(0, libdir)
import instances_io
for it in instances_io.load_instances(toml):
    if str(it.get("run_mode", "source")) != "source":
        continue
    series = instances_io.series_of(it)
    if not series:
        continue
    py = str(it.get("python", ""))
    ap = it.get("addons_path", [])
    if isinstance(ap, list):
        ap = instances_io.join_addons_path(ap)
    print("\t".join([series, py, str(ap)]))
PY
}

# Probe PostgreSQL reachability through the DECLARED client surface of the
# highest declared instance (db_run_mode - see lib/pg_mode.sh).
#   0 = proven reachable   1 = proven UNREACHABLE   2 = no surface to probe with
# "No client installed" and "cluster down" are DIFFERENT facts: only a probe that
# actually ran may report 1, and 2 is reported out loud rather than passed as ok.
_pg_probe_declared() {
    local toml py="" host="localhost" user="odoo" port="" mode="" container="" root=""
    if toml="$(_resolve_instances_path)" && [[ -f "$toml" ]]; then
        local kv=""
        kv="$(python3 "$LIB_DIR/instances_io.py" read "$toml" 2>/dev/null)" || kv=""
        if [[ -n "$kv" ]]; then
            eval "$kv" 2>/dev/null || true
            py="${INST_PYTHON:-}"; host="${INST_DB_HOST:-localhost}"
            user="${INST_DB_USER:-odoo}"; port="${INST_DB_PORT:-}"
            mode="${INST_DB_RUN_MODE:-}"; container="${INST_DB_CONTAINER:-}"
            root="${INST_ODOO_ROOT:-}"
        fi
    fi
    local -a port_args=()
    [[ -n "$port" ]] && port_args=(-p "$port")
    # Probe ladder, cheapest first, every rung BOUNDED. pg_isready is used for a
    # `native` surface AND for an UNDECLARED one (nothing recorded yet, so a
    # locally installed client is exactly the pre-declaration behavior) - but
    # never for `tcp-only`, which declares that this cluster has no client
    # surface at all. pg_isready is not part of PG_MODE_NATIVE_BINS, so a native
    # host may still lack it; falling through is then mandatory, because a
    # missing binary must never be reported as a down cluster.
    # 124 = the bound elapsed; 125 = the bound itself could not be applied
    # (pg_mode.sh's contract). Neither is a cluster fact, so both map to 2 ("no
    # verdict") on EVERY rung - the identical rule 50-instance-spinup.sh applies.
    local prc=0
    if [[ "$mode" == "native" || -z "$mode" ]] && _have pg_isready; then
        pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            pg_isready -h "$host" "${port_args[@]}" -U "$user" -q >/dev/null 2>&1 || prc=$?
        [[ "$prc" -eq 0 ]] && return 0
        [[ "$prc" -eq 124 || "$prc" -eq 125 ]] && return 2
        return 1
    fi
    if [[ "$mode" == "docker" && -n "$container" ]] && _have docker; then
        pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            pg_run_client docker "$container" "$host" "$user" "$port" pg_isready -q \
            >/dev/null 2>&1 || prc=$?
        [[ "$prc" -eq 0 ]] && return 0
        [[ "$prc" -eq 124 || "$prc" -eq 125 ]] && return 2
        return 1
    fi
    # tcp-only, an undeclared surface, or a client that is not installed after
    # all: opening a connection through the instance's own python IS the probe
    # (no client binary, no privilege needed).
    if [[ -n "$py" && -x "$py" && -f "$LIB_DIR/odoo_db.py" ]]; then
        local -a ex=("$LIB_DIR/odoo_db.py" exists postgres --db-host "$host" --db-user "$user")
        [[ -n "$root" ]] && ex+=(--odoo-root "$root")
        [[ -n "$port" ]] && ex+=(--db-port "$port")
        prc=0
        pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" "$py" "${ex[@]}" >/dev/null 2>&1 || prc=$?
        # 10 = this venv cannot import odoo; 124/125 = the probe did not answer.
        # Neither is a cluster fact - the venv gate below owns 10 - so neither may
        # be reported as a down cluster.
        [[ "$prc" -eq 10 || "$prc" -eq 124 || "$prc" -eq 125 ]] && return 2
        [[ "$prc" -eq 0 ]] && return 0
        return 1
    fi
    # No instance declared at all (a fresh setup): a bare local pg_isready is the
    # only thing left, and its absence means "cannot probe" - never "down".
    if _have pg_isready; then
        prc=0
        pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" pg_isready -q >/dev/null 2>&1 || prc=$?
        [[ "$prc" -eq 0 ]] && return 0
        [[ "$prc" -eq 124 || "$prc" -eq 125 ]] && return 2
        return 1
    fi
    return 2
}

# Report the CREATEDB capability per declared instance, auto-detected by asking the
# cluster (never inferred from which binaries are installed). An instance whose role
# lacks it cannot use `ephemeral` isolation: the allocator REFUSES with exit 6
# rather than silently sharing the declared database.
#
# The question is asked through `allocator.py can-createdb`, which is the SAME
# two-route ladder the `acquire` gate uses and returns the SAME exit codes. Asking
# odoo_db.py directly from here would re-implement route 1 in shell and could not
# reach route 2 at all - so a `run_mode = "docker"` instance, which declares no
# `python` because compose launches it, got no answer from the very command whose
# job is to say whether isolation is available.
_createdb_report() {
    local toml series profile
    toml="$(_resolve_instances_path)" || return 0
    [[ -f "$toml" ]] || return 0
    [[ -f "$LIB_DIR/allocator.py" ]] || return 0
    while IFS=$'\t' read -r series profile; do
        [[ -n "$series" ]] || continue
        local label="$series"
        [[ -n "$profile" ]] && label="$series:$profile"
        local -a args=("$LIB_DIR/allocator.py" can-createdb --series "$series" --instances "$toml")
        [[ -n "$profile" ]] && args+=(--profile "$profile")
        local out="" rc=0
        out="$(python3 "${args[@]}" 2>/dev/null)" || rc=$?
        case "$rc" in
            0) echo "  [ok ] the declared role may CREATE DATABASE for $label (ephemeral isolation available)" ;;
            6) echo "  [ -- ] the declared role may NOT CREATE DATABASE for $label - 'ephemeral'"
               echo "         acquires refuse (exit 6). fix: grant that role CREATEDB." ;;
            *) echo "  [ ?? ] CREATEDB for $label undeterminable - 'ephemeral' acquires refuse (exit 7)."
               echo "         fix: start PostgreSQL, then 45-venv.sh record-env --series $series"
               echo "         (a compose-run instance declares no python: declare db_run_mode +"
               echo "         db_container so the capability can be asked inside the container)" ;;
        esac
    done < <(_enumerate_instance_keys "$toml")
}

# Emit TAB-separated `series<TAB>profile` for EVERY declared instance, whatever its
# run_mode. Kept separate from _enumerate_source_instances (which is deliberately
# source-only: it gates the VENV, a source-mode-only concern) so adding a column
# here can never shift that reader's fields.
_enumerate_instance_keys() {
    local toml="$1"
    [[ -f "$toml" ]] || return 0
    python3 - "$toml" "$LIB_DIR" <<'PY' 2>/dev/null || true
import sys
toml, libdir = sys.argv[1], sys.argv[2]
sys.path.insert(0, libdir)
import instances_io
for it in instances_io.load_instances(toml):
    series = instances_io.series_of(it)
    if not series:
        continue
    print("\t".join([series, str(instances_io.profile_of(it) or "")]))
PY
}

# Locate odoo-bin for a comma-delimited addons_path (ODOO_BIN wins, else scan).
_find_odoo_bin_in() {
    local addons_path="$1" p
    if [[ -n "${ODOO_BIN:-}" && -x "${ODOO_BIN}" ]]; then echo "$ODOO_BIN"; return 0; fi
    _addons_path_to_array _paths "${addons_path}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

# HARD GATE: every DECLARED source-mode instance must have a WORKING venv -
# `python` populated AND `<python> <odoo-bin> --version` runs. On failure emit a
# FAILED line + remediation and return non-zero. ODOO_AI_ALLOW_NO_VENV=1
# downgrades FAILED -> a loud WARN (deferring a build stays legit, never silent).
# No declared instances (fresh setup) -> nothing to gate -> pass.
_venv_gate() {
    local toml
    toml="$(_resolve_instances_path)" || return 0
    [[ -f "$toml" ]] || return 0
    local failed=0 series py addons bin
    while IFS=$'\t' read -r series py addons; do
        [[ -n "$series" ]] || continue
        local ok=1
        if [[ -z "$py" ]]; then
            ok=0
        else
            bin="$(_find_odoo_bin_in "$addons")" || bin=""
            if [[ -z "$bin" ]] || ! "$py" "$bin" --version >/dev/null 2>&1; then
                ok=0
            fi
        fi
        if [[ "$ok" -eq 0 ]]; then
            if [[ "${ODOO_AI_ALLOW_NO_VENV:-}" == "1" ]]; then
                echo "  [WARN] no working Odoo venv for series $series" \
                     "(ODOO_AI_ALLOW_NO_VENV=1) - build later: 45-venv.sh --series $series" >&2
            else
                echo "  [FAILED] no working Odoo venv for series $series -" \
                     "run 45-venv.sh --series $series (create-venv), then re-run setup." >&2
                failed=1
            fi
        fi
    done < <(_enumerate_source_instances "$toml")
    return "$failed"
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
        # A cluster PROVEN unreachable blocks; "could not probe at all" does not
        # (that is reported by apply, never silently converted into a verdict).
        local _pgrc=0
        _pg_probe_declared || _pgrc=$?
        if [[ "$_pgrc" -eq 1 ]]; then return 1; fi
        _repos_present || return 1
        # HARD venv gate for declared source instances (opt-out via ODOO_AI_ALLOW_NO_VENV=1).
        _venv_gate || return 1
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
        printf '  %s' "$(_mark _have curl)";    echo " curl (polls /web/database/selector during spin-up, falling back to /web/login)"
        local _pgrc=0
        _pg_probe_declared || _pgrc=$?
        case "$_pgrc" in
            0) echo "  [ok ] PostgreSQL reachable (probed through the declared db_run_mode)" ;;
            1) echo "  [ -- ] PostgreSQL NOT reachable (probed through the declared db_run_mode)" ;;
            *) echo "  [ ?? ] PostgreSQL: no way to probe yet - declare an instance, then run" ;
               echo "         45-venv.sh create-venv + record-env for it" ;;
        esac
        echo "         fix: start PostgreSQL, e.g. 'sudo systemctl start postgresql'"
        echo "              or run it in a container publishing a host port of YOUR choosing,"
        echo "              then declare that port as db_port on the [[instance]]"
        _createdb_report
        printf '  %s' "$(_mark _repos_present)"; echo " Odoo repos under \${ODOO_GIT_BASE:-\$HOME/git} ($ODOO_GIT_BASE)"
        echo "         fix: git clone https://github.com/odoo/odoo -b 17.0 ~/git/odoo17"
        echo "              (or set ODOO_GIT_BASE to where your repos live)"
        printf '  %s' "$(_mark _have docker)";   echo " docker (REQUIRED when your PostgreSQL runs in a container - db_run_mode=docker)"
        printf '  %s' "$(_mark _have ffmpeg)";   echo " ffmpeg (optional - pagecast video/GIF recording)"
    fi
    echo
    echo "NEEDS YOUR CONFIRMATION (cannot be auto-detected):"
    if _needs_instance; then
        echo "  [ ] DB password exported as ODOO_PG_PASSWORD (skip if using trust auth)"
        echo "  [ ] System build deps installed (only if you build a fresh venv):"
        echo "        build-essential python3-dev libxml2-dev libxslt1-dev libpq-dev"
        echo "        libldap2-dev libsasl2-dev libssl-dev libjpeg-dev zlib1g-dev"
        echo "  [ ] An Odoo venv with requirements installed (built by step 45)"
    fi
    if _needs_instance; then
        echo
        echo "VENV GATE (HARD - blocks 'check' for each declared source-mode instance):"
        if _venv_gate; then
            echo "  [ok ] Every declared source instance has a working venv (or none declared yet)."
        else
            echo "         fix: run 45-venv.sh --series <X> for each series flagged FAILED above." >&2
            echo "         (Set ODOO_AI_ALLOW_NO_VENV=1 to defer a build - downgrades FAILED to WARN.)" >&2
        fi
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
