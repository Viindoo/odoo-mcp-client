#!/usr/bin/env bash
# 45-venv.sh - Optional helper to provision a Python virtualenv for an Odoo
# instance (source mode). Each Odoo series supports only certain Python
# versions. That range is an Odoo SOURCE fact, read from the instance's own
# checkout (lib/odoo_source_facts.py python-suggest); lib/odoo-python-matrix.json
# is consulted only when no checkout is readable. The user reuses an existing
# venv or builds a new one with uv or pip.
#
# This step is OPT-IN: its `check` always reports satisfied so the `all` filter
# never auto-builds a venv (building lxml/psycopg2 can be heavy and needs system
# build deps). The setup command calls `create-venv` only when the user asks.
#
# CONFIG (env overrides):
#   ODOO_AI_HOME       machine-global dir    (default $HOME/.odoo-ai)
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#   ODOO_AI_PYTHON2    the Python 2.7 interpreter to build a Python 2 venv with
#                      (default: python2.7 / python2 on PATH, then pyenv's 2.7.x)
#
# Subcommands:
#   describe
#   suggest <series> [--profile P]   print the supported range + recommended Python
#                                    for a declared instance (source-derived)
#   apply                            advise-only: explain venv options
#   create-venv --series X.Y [--python VER] [--tool uv|pip]
#               [--path DIR] [--requirements FILE]
#                                    create a venv and record it on the instance.
#                                    A Python 2.7 venv (the series' checkout
#                                    declares Python 2, or --python 2.x) is built
#                                    with virtualenv, never uv/pip venv (neither
#                                    can target Python 2): see _create_python2_venv.
#                                    Exit 3 = NEEDS_CONTEXT (no usable Python 2.7
#                                    interpreter or no virtualenv able to target
#                                    it): nothing built, nothing recorded.
#                                    --tool pip: when the requested/recommended
#                                    python3.X is not on PATH, it looks for another
#                                    acceptable interpreter (PATH, pyenv, or an
#                                    already-installed uv-managed python - never
#                                    fetched), closest to the recommended version
#                                    first, going UP. When the source declares no
#                                    upper bound it never claims one: it says so,
#                                    and the fallback table's editorial max (if
#                                    any) is only a soft cap. Finding none, it refuses
#                                    with Exit 3 = NEEDS_CONTEXT rather than build
#                                    the venv with an out-of-range python3: see
#                                    _find_python3_in_range.
#   record-env --series X.Y [--profile P]
#                                    re-derive and re-record the environment facts
#                                    of an ALREADY-DECLARED instance WITHOUT
#                                    touching the venv: python, odoo_root (the
#                                    checkout root that makes `import odoo`
#                                    resolve), db_run_mode + db_container (the
#                                    Postgres client surface - see lib/pg_mode.sh).
#                                    Each fact is recorded only when its own gate
#                                    passes; a failed gate prints why and makes the
#                                    exit non-zero, and NEVER records a guess.
#                                    Run it once on a catalog written before these
#                                    keys existed, and after any change to your
#                                    Postgres container or venv.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
FACTS="$SCRIPT_DIR/../lib/odoo_source_facts.py"
# Postgres client-surface detector + db_run_mode vocabulary SSOT.
# shellcheck source=../lib/pg_mode.sh
source "$SCRIPT_DIR/../lib/pg_mode.sh"
# instances.toml is machine-global; resolve it (global-wins) via the shared helper.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
# venvs/ root (Tier-2 SHARE - snippets/state-root-resolution.md): sourced for
# resolve_project_dir_share, called lazily in cmd_create_venv (below) so a venv
# built in one linked worktree of a repo is reused by every other worktree of
# the SAME repo, instead of the old $ODOO_AI_DIR-relative (cwd/worktree-scoped)
# path. follow-up: reclassify venvs/ to host-global by requirements-hash (deferred).
# shellcheck source=../lib/resolve_project_dir.sh
source "$SCRIPT_DIR/../lib/resolve_project_dir.sh"
INSTANCES_TOML="$(_resolve_instances)"

cmd_describe() {
    echo "Optionally create a Python venv for an Odoo instance (reuse existing, or build with uv/pip)"
}

# _python_recommendation <series> [profile]
#   stdout: PY_RECOMMENDED / PY_MIN / PY_MAX / PY_SOURCE / PY_PYTHON2 lines, or
#   nothing. The range is read from the declared instance's checkout (its
#   odoo_root, else the core repo on its addons_path); the fallback table fills
#   in only when no checkout is readable (PY_SOURCE=matrix).
_python_recommendation() {
    local series="$1" profile="${2:-}" io="$SCRIPT_DIR/../lib/instances_io.py"
    local kv="" root="" line
    local -a args=()
    if [[ -f "$INSTANCES_TOML" && -f "$io" ]]; then
        # The row a later record lands on first; `suggest <series>` on a series with
        # only profiled rows still reads one of them (advice only, nothing recorded).
        kv="$(python3 "$io" read-row "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" \
            || kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || kv=""
    fi
    if [[ -n "$kv" ]]; then
        eval "$kv" 2>/dev/null || true
        [[ -n "${INST_ODOO_ROOT:-}" ]] && args+=(--odoo-root "$INST_ODOO_ROOT")
        _addons_path_to_array _rec_paths "${INST_ADDONS_PATH:-}"
        args+=("${_rec_paths[@]+"${_rec_paths[@]}"}")
        if [[ "${#args[@]}" -gt 0 ]]; then
            while IFS= read -r line; do
                [[ "$line" == ODOO_ROOT=* ]] && root="${line#ODOO_ROOT=}"
            done < <(python3 "$FACTS" locate-root "${args[@]}" 2>/dev/null || true)
        fi
    fi
    if [[ -n "$root" ]]; then
        python3 "$FACTS" python-suggest "$series" "$root" 2>/dev/null || true
    else
        python3 "$FACTS" python-suggest "$series" 2>/dev/null || true
    fi
}

# _py_fact <name> <facts-text>: the value of one PY_* line, or empty.
_py_fact() {
    local want="$1" line
    while IFS= read -r line; do
        [[ "$line" == "$want="* ]] && { printf '%s\n' "${line#*=}"; return 0; }
    done <<<"$2"
    return 0
}

# _py_outside_range <ver> <min> <max>: exit 0 when <ver> is OUTSIDE [min, max]
# (an empty max is open), 1 when inside or undecidable.
_py_outside_range() {
    python3 - "$1" "$2" "$3" <<'PY' 2>/dev/null
import re, sys
def key(v):
    return tuple(int(p) for p in re.findall(r"\d+", v or ""))
ver, lo, hi = (key(a) for a in sys.argv[1:4])
if not ver or not lo:
    sys.exit(1)
sys.exit(0 if ver < lo or (hi and ver > hi) else 1)
PY
}

cmd_suggest() {
    local series="" profile=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile) profile="$2"; shift 2 ;;
            -*) echo "Unknown arg: $1" >&2; return 2 ;;
            *) series="$1"; shift ;;
        esac
    done
    [[ -n "$series" ]] || { echo "Usage: $(basename "$0") suggest <series> [--profile P]" >&2; return 2; }
    local facts rec lo hi src
    facts="$(_python_recommendation "$series" "$profile")"
    rec="$(_py_fact PY_RECOMMENDED "$facts")"
    if [[ -z "$rec" ]]; then
        echo "No Python facts for Odoo $series: no readable checkout and no fallback entry."
        return 0
    fi
    lo="$(_py_fact PY_MIN "$facts")"; hi="$(_py_fact PY_MAX "$facts")"; src="$(_py_fact PY_SOURCE "$facts")"
    case "$src" in debian) src="debian/control" ;; shebang) src="launcher shebang" ;; esac
    if [[ "$src" == "matrix" ]]; then
        echo "Supported Python for Odoo $series: $lo-${hi:-open} (fallback table - no readable Odoo checkout for this instance)"
    else
        echo "Supported Python for Odoo $series: $lo-${hi:-open} (read from the checkout's $src)"
    fi
    if [[ "$(_py_fact PY_PYTHON2 "$facts")" == "1" ]]; then
        echo "Recommended Python for Odoo $series: $rec (Python 2 - EOL, not recommended for new work)"
    else
        echo "Recommended Python for Odoo $series: $rec"
    fi
}

# check is always satisfied: venv provisioning is opt-in, not part of the
# automatic step run.
cmd_check() { return 0; }

cmd_apply() {
    echo "Python venv is optional and opt-in. For an Odoo source instance you can:"
    echo "  - Reuse an existing venv: set its python in .odoo-ai/instances.toml"
    echo "    (the 'python' field of the matching [[instance]]) or export ODOO_PYTHON."
    echo "  - Build a new one for a series (the supported Python range is read from the"
    echo "    instance's own Odoo checkout; '$(basename "$0") suggest <series>' prints it):"
    echo "      $(basename "$0") create-venv --series 17.0 --tool uv"
    echo "      $(basename "$0") create-venv --series 17.0 --tool pip --python 3.12"
    echo "Building installs the series' requirements.txt and needs system build deps"
    echo "(build-essential, python3-dev, libxml2-dev, libxslt1-dev, libpq-dev, ...)."
    echo "setup never installs those for you."
}

# Echo the absolute path of the Odoo server launcher for a series (and optional
# profile) - `odoo-bin`, or `openerp-server` on the oldest series - or nothing.
# Reads the (series, profile) row so the right profile's core is used, and asks
# the shared locator (resolve_instances.sh _odoo_find_launcher) with the row's
# odoo_root and addons_path.
_core_odoo_bin_for_series() {
    local series="$1" profile="${2:-}" io="$SCRIPT_DIR/../lib/instances_io.py"
    [[ -f "$INSTANCES_TOML" && -f "$io" ]] || return 0
    local kv
    kv="$(python3 "$io" read-row "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || return 0
    eval "$kv" 2>/dev/null || return 0
    _odoo_find_launcher "${INST_ADDONS_PATH:-}" "${INST_ODOO_ROOT:-}" || true
    return 0
}

# Echo the absolute path of the Odoo server launcher found on an addons_path
# string (SSOT separator - see resolve_instances.sh's _addons_path_to_array), or
# nothing. Used when INST_ADDONS_PATH is already resolved (e.g. a profiled read).
_core_odoo_bin_from_addons_path() {
    _odoo_find_launcher "$1" || true
    return 0
}

# ---------------------------------------------------------------------------
# _upsert_instance_keys <series> <profile> PAIR [PAIR ...]
#
# INSERT-OR-REPLACE every key on the ONE [[instance]] block matching
# (series, profile), in place. PAIR is KEY=VALUE (a TOML string) or KEY[]=A,B
# (a TOML array of strings). Replaces an existing assignment; when it is ABSENT
# it is INSERTED after the block's last assignment - a catalog written before a
# key existed therefore GAINS it, instead of silently keeping nothing. Refuses
# (non-zero, file untouched) when the series has only profiled blocks and no
# --profile was given, and when no block matches at all. Atomic write.
# The writer is config_merge.py's toml-upsert-instance-keys - one writer for
# every setup step that records a fact on a declared row.
# ---------------------------------------------------------------------------
_upsert_instance_keys() {
    local series="$1" profile="$2"; shift 2
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare the instance first (step 40)." >&2
        return 1
    }
    python3 "$LIB" toml-upsert-instance-keys "$INSTANCES_TOML" "$series" "$profile" "$@"
}

# ---------------------------------------------------------------------------
# _detect_pg_facts <series> <profile>
#   stdout: `db_run_mode=<v>` [+ `db_container=<name>`]; exit 3 undeterminable.
#   Uses the instance's DECLARED db_port to identify the container, so the human
#   never types a container name and a wrong one is never guessed.
# ---------------------------------------------------------------------------
_detect_pg_facts() {
    local series="$1" profile="${2:-}" io="$SCRIPT_DIR/../lib/instances_io.py"
    local db_port="" kv=""
    if [[ -f "$INSTANCES_TOML" && -f "$io" ]]; then
        kv="$(python3 "$io" read-row "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || kv=""
        if [[ -n "$kv" ]]; then
            eval "$kv" 2>/dev/null || true
            db_port="${INST_DB_PORT:-}"
        fi
    fi
    pg_detect_mode "$db_port"
}

# ---------------------------------------------------------------------------
# _report_db_preflight <series> <profile>
#   Advisory, never fatal. Asks the SSOT (allocator.py db-preflight - the SAME
#   ladder `acquire` gates on) and forwards its verdict verbatim. This function
#   must never restate, re-derive or re-word the answer: a second copy of the
#   question is how a setup step came to contradict the command that runs next.
#   BOUNDED: a setup-time advisory must never hang the setup it advises on.
# ---------------------------------------------------------------------------
_report_db_preflight() {
    local series="$1" profile="${2:-}" alloc="$SCRIPT_DIR/../lib/allocator.py"
    [[ -f "$alloc" ]] || return 0
    local -a args=("$alloc" db-preflight --series "$series" --instances "$INSTANCES_TOML")
    [[ -n "$profile" ]] && args+=(--profile "$profile")
    pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" python3 "${args[@]}" || true
    return 0
}

# ---------------------------------------------------------------------------
# _record_env_facts <series> <profile> <venv_py> <odoo_root>
#   Record every VERIFIED environment fact on the matched block. python and
#   odoo_root come from the caller's already-passed `<venv_py> <odoo-bin>
#   --version` gate; db_run_mode/db_container come from the detector. Returns
#   non-zero when a fact could not be determined - having recorded no guess for it.
# ---------------------------------------------------------------------------
_record_env_facts() {
    local series="$1" profile="${2:-}" venv_py="${3:-}" odoo_root="${4:-}"
    local -a facts=()
    local rc=0 line
    [[ -n "$venv_py" ]] && facts+=("python=$venv_py")
    [[ -n "$odoo_root" ]] && facts+=("odoo_root=$odoo_root")
    local detected="" drc=0
    detected="$(_detect_pg_facts "$series" "$profile")" || drc=$?
    if [[ "$drc" -eq 0 ]]; then
        while IFS= read -r line; do
            [[ -n "$line" ]] && facts+=("$line")
        done <<<"$detected"
    else
        rc=1
    fi
    if [[ "${#facts[@]}" -gt 0 ]]; then
        _upsert_instance_keys "$series" "$profile" "${facts[@]}" || return 1
    fi
    return "$rc"
}

# _warn_venv_outside_range <series> <venv_py> <odoo_root>
#   Advisory, never fatal: says so when the venv's interpreter lies outside the
#   Python range the checkout itself declares (odoo-bin --version passing does not
#   prove the whole addon set imports and runs under it).
_warn_venv_outside_range() {
    local series="$1" venv_py="$2" root="$3" ver facts lo hi
    ver="$("$venv_py" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || return 0
    facts="$(python3 "$FACTS" python-suggest "$series" "$root" 2>/dev/null)" || return 0
    lo="$(_py_fact PY_MIN "$facts")"; hi="$(_py_fact PY_MAX "$facts")"
    if _py_outside_range "$ver" "$lo" "$hi"; then
        echo "  Warning: the venv runs Python $ver, outside the range Odoo $series declares" >&2
        echo "  ($lo-${hi:-open}, source: $(_py_fact PY_SOURCE "$facts")). Rebuild it:" >&2
        echo "  $(basename "$0") create-venv --series $series" >&2
    fi
    return 0
}

cmd_record_env() {
    local series="" profile=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) series="$2"; shift 2 ;;
            --profile) profile="$2"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$series" ]] || { echo "x --series is required (e.g. --series 17.0)" >&2; return 2; }
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare the instance first (step 40)." >&2
        return 1
    }

    # Resolve the ONE row this records onto BEFORE anything else runs: a series with
    # only profiled rows and no --profile (or no row at all) is refused here, so no
    # probe below ever prints facts for a row nobody selected.
    local io="$SCRIPT_DIR/../lib/instances_io.py" kv="" _rr=0
    kv="$(python3 "$io" read-row "$INSTANCES_TOML" "$series" "${profile:-}")" || _rr=$?
    if [[ "$_rr" -ne 0 || -z "$kv" ]]; then
        echo "  Nothing was probed or recorded." >&2
        return 1
    fi
    eval "$kv"

    local rc=0 venv_py="${INST_PYTHON:-}" odoo_root="" core_bin=""
    if [[ -n "$venv_py" && -x "$venv_py" ]]; then
        core_bin="$(_core_odoo_bin_from_addons_path "${INST_ADDONS_PATH:-}")" || core_bin=""
        if [[ -z "$core_bin" ]]; then
            core_bin="$(_core_odoo_bin_for_series "$series" "${profile:-}")" || core_bin=""
        fi
        if [[ -n "$core_bin" ]] && "$venv_py" "$core_bin" --version >/dev/null 2>&1; then
            odoo_root="$(dirname "$core_bin")"
            _warn_venv_outside_range "$series" "$venv_py" "$odoo_root"
        else
            echo "x '$venv_py <odoo launcher> --version' failed - python and odoo_root were NOT" >&2
            echo "  recorded. Rebuild the venv: $(basename "$0") create-venv --series $series." >&2
            venv_py=""
            rc=1
        fi
    else
        echo "x this instance declares no runnable 'python' - python and odoo_root were NOT" >&2
        echo "  recorded. Build one: $(basename "$0") create-venv --series $series." >&2
        venv_py=""
        rc=1
    fi

    _record_env_facts "$series" "${profile:-}" "$venv_py" "$odoo_root" || rc=1
    _report_db_preflight "$series" "${profile:-}"
    return "$rc"
}

# ---------------------------------------------------------------------------
# Python 2.7 venvs (the series whose checkout declares Python 2).
#
# uv cannot create a Python 2 environment (it neither finds nor installs 2.x),
# and Python 2 has no `-m venv`. virtualenv can - but only up to 20.21.x:
# 20.22.0 dropped the Python 2.7 seed wheels (its seed/wheels/embed
# BUNDLE_SUPPORT lists 2.7 in 20.21.1 and no longer in 20.22.0). One spec, used
# everywhere below.
_PY2_VIRTUALENV_SPEC='virtualenv<20.22'

# _py_major_minor <python> - "X.Y" the interpreter reports, or nothing.
_py_major_minor() {
    "$1" -c 'import sys; sys.stdout.write("%d.%d\n" % sys.version_info[:2])' 2>/dev/null || true
}

# _find_python2 - print the Python 2.7 interpreter to build with; return 1
#   (reason on stderr) when there is none. $ODOO_AI_PYTHON2 wins and must BE a
#   2.7 (a named interpreter that is not is an error, never skipped); else the
#   first 2.7 among python2.7 / python2 on PATH, then pyenv's versions/2.7*.
_find_python2() {
    local cand ver
    if [[ -n "${ODOO_AI_PYTHON2:-}" ]]; then
        ver="$(_py_major_minor "$ODOO_AI_PYTHON2")"
        if [[ "$ver" == "2.7" ]]; then
            printf '%s\n' "$ODOO_AI_PYTHON2"
            return 0
        fi
        echo "  ODOO_AI_PYTHON2='$ODOO_AI_PYTHON2' is not a working Python 2.7 (it reports '${ver:-nothing}')." >&2
        return 1
    fi
    local -a cands=()
    for cand in python2.7 python2; do
        command -v "$cand" >/dev/null 2>&1 && cands+=("$(command -v "$cand")")
    done
    local pyenv_root="${PYENV_ROOT:-${HOME:-}/.pyenv}"
    if [[ -n "$pyenv_root" && -d "$pyenv_root/versions" ]]; then
        while IFS= read -r cand; do
            [[ -n "$cand" ]] && cands+=("$cand")
        done < <(ls -1d "$pyenv_root"/versions/2.7*/bin/python2.7 2>/dev/null | sort -r)
    fi
    for cand in "${cands[@]+"${cands[@]}"}"; do
        if [[ "$(_py_major_minor "$cand")" == "2.7" ]]; then
            printf '%s\n' "$cand"
            return 0
        fi
    done
    echo "  No Python 2.7 interpreter found (checked ODOO_AI_PYTHON2, python2.7 and python2 on PATH, pyenv versions under ${pyenv_root:-~/.pyenv})." >&2
    return 1
}

# _virtualenv_version_ok <virtualenv-executable> - 0 when it is older than 20.22
#   (still able to create a Python 2.7 environment).
_virtualenv_version_ok() {
    local ver
    ver="$("$1" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n 1)"
    [[ -n "$ver" ]] || return 1
    python3 - "$ver" <<'PY' 2>/dev/null
import re, sys
key = tuple(int(p) for p in re.findall(r"\d+", sys.argv[1]))
sys.exit(0 if key < (20, 22) else 1)
PY
}

# _create_python2_venv <python2.7> <dir> - build a Python 2.7 venv at <dir>
#   with a virtualenv that can still target it, first that is available:
#     1. uv present:  uvx --from 'virtualenv<20.22' virtualenv -p <py2> <dir>
#                     (uv fetches that virtualenv and runs it on a Python 3;
#                     the environment it creates runs <py2>)
#     2. a `virtualenv` on PATH older than 20.22: virtualenv -p <py2> <dir>
#     3. virtualenv installed into <py2> itself: <py2> -m virtualenv <dir>
#   Return 3 (NEEDS_CONTEXT, nothing built) when none is.
_create_python2_venv() {
    local py2="$1" dir="$2" venv_bin
    if command -v uvx >/dev/null 2>&1; then
        uvx --from "$_PY2_VIRTUALENV_SPEC" virtualenv -p "$py2" "$dir"
        return $?
    fi
    if command -v uv >/dev/null 2>&1; then
        uv tool run --from "$_PY2_VIRTUALENV_SPEC" virtualenv -p "$py2" "$dir"
        return $?
    fi
    venv_bin="$(command -v virtualenv 2>/dev/null || true)"
    if [[ -n "$venv_bin" ]] && _virtualenv_version_ok "$venv_bin"; then
        "$venv_bin" -p "$py2" "$dir"
        return $?
    fi
    if "$py2" -m virtualenv --version >/dev/null 2>&1; then
        "$py2" -m virtualenv "$dir"
        return $?
    fi
    echo "x NEEDS_CONTEXT: no virtualenv able to create a Python 2.7 environment is available." >&2
    echo "  Provide one, then re-run: install uv (it runs '$_PY2_VIRTUALENV_SPEC' on demand)," >&2
    echo "  or install '$_PY2_VIRTUALENV_SPEC' on PATH, or virtualenv into $py2 itself" >&2
    echo "  ($py2 -m pip install 'virtualenv<20.22'). Nothing was built; 'python' was NOT recorded." >&2
    return 3
}

# _python_soft_cap <series> - the fallback table's editorial "max" for <series>,
#   or nothing. Used ONLY when the checkout declares no upper bound: it is a soft
#   cap (interpreters at or below it are preferred; one above it is still usable,
#   with a warning), never a substitute for the source range.
_python_soft_cap() {
    python3 - "$1" "$SCRIPT_DIR/../lib/odoo-python-matrix.json" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[2], encoding="utf-8") as fh:
        entry = (json.load(fh).get("odoo_python_matrix") or {}).get(sys.argv[1]) or {}
except (OSError, ValueError, AttributeError):
    entry = {}
print(entry.get("max") or "")
PY
}

# _candidate_versions <lo> <hi> <requested> <soft-cap>
#   stdout: "X.Y<TAB>tier" lines, in the order to try them. Closest to <requested>
#   first, oldest-acceptable first going UP: <requested>, <requested>+1, ... up to
#   the upper bound, then the versions below <requested> down to <lo> (newest
#   first). The upper bound is <hi> when the source declares one; otherwise the
#   soft cap when the fallback table has one, else <lo>'s minor+20 so the search
#   stays bounded. With a soft cap and no <hi>, the versions above the cap (up to
#   minor+20) come last. tier:
#     in    inside the range the source declares ([lo, hi])
#     open  the source declares no upper bound; >= lo and not above any soft cap
#     over  above the fallback table's soft cap (no source upper bound)
#   A <requested> outside [lo, bound] is ignored (the walk starts at <lo>).
_candidate_versions() {
    python3 - "$1" "${2:-}" "${3:-}" "${4:-}" <<'PY' 2>/dev/null
import re, sys

def parts(v):
    m = re.match(r"(\d+)\.(\d+)", v or "")
    return (int(m.group(1)), int(m.group(2))) if m else None

lo, hi, req, cap = (parts(a) for a in sys.argv[1:5])
if not lo:
    sys.exit(0)
major = lo[0]
limit = lo[1] + 20
if hi and hi[0] == major:
    top, tier, cap = hi[1], "in", None
elif cap and cap[0] == major and cap[1] >= lo[1]:
    top, tier = cap[1], "open"
else:
    top, tier, cap = limit, "open", None
start = req[1] if req and req[0] == major and lo[1] <= req[1] <= top else lo[1]
order = list(range(start, top + 1)) + list(range(start - 1, lo[1] - 1, -1))
for minor in order:
    print("%d.%d\t%s" % (major, minor, tier))
if cap:
    for minor in range(top + 1, max(limit, top) + 1):
        print("%d.%d\tover" % (major, minor))
PY
}

# _explain_python_pick <requested> <picked-desc> <ver> <tier> <lo> <hi> <cap> <series>
#   stderr: why <picked-desc> was chosen, worded by the tier - it never claims a
#   range the source did not declare.
_explain_python_pick() {
    local requested="$1" desc="$2" ver="$3" tier="$4" lo="$5" hi="$6" cap="$7" series="$8"
    echo "  Note: python$requested not found; using $desc (Python $ver)." >&2
    case "$tier" in
        in)
            echo "  It is inside the range Odoo $series's source declares ($lo-$hi)." >&2 ;;
        open)
            echo "  Odoo $series's source declares no upper Python bound (min $lo); chose the" >&2
            echo "  installed interpreter closest to $requested, oldest first going up." >&2
            [[ -n "$cap" ]] && echo "  It is within the fallback table's editorial cap ($cap)." >&2
            echo "  Verify your addons run under it." >&2 ;;
        over)
            echo "  Warning: Odoo $series's source declares no upper Python bound (min $lo), and" >&2
            echo "  no installed interpreter at or below the fallback table's editorial cap" >&2
            echo "  ($cap) was found; Python $ver is above it. Verify your addons run under it." >&2 ;;
    esac
}

# _find_python3_in_range <requested> <lo> <hi> [series]
#   stdout: an ALREADY-INSTALLED python3.Y interpreter acceptable for the series -
#   never one fetched on demand. Versions are tried in _candidate_versions order;
#   for each version: PATH (python3.Y), then pyenv (versions/3.Y*/bin/python3.Y),
#   then a uv-managed python already on disk (UV_PYTHON_DOWNLOADS=never so
#   `uv python find` cannot trigger a download). Prints which one it picked (and
#   why) to stderr. Empty <lo>, or nothing found -> return 1, nothing on stdout.
_find_python3_in_range() {
    local requested="$1" lo="$2" hi="$3" series="${4:-}" ver tier cand pyenv_root cap=""
    [[ -n "$lo" ]] || return 1
    [[ -z "$hi" && -n "$series" ]] && cap="$(_python_soft_cap "$series")"
    pyenv_root="${PYENV_ROOT:-${HOME:-}/.pyenv}"
    local have_uv=0
    command -v uv >/dev/null 2>&1 && have_uv=1
    while IFS=$'\t' read -r ver tier; do
        [[ -n "$ver" ]] || continue
        if command -v "python$ver" >/dev/null 2>&1; then
            _explain_python_pick "$requested" "python$ver on PATH" "$ver" "$tier" "$lo" "$hi" "$cap" "$series"
            command -v "python$ver"
            return 0
        fi
        if [[ -n "$pyenv_root" && -d "$pyenv_root/versions" ]]; then
            while IFS= read -r cand; do
                [[ -x "$cand" ]] || continue
                _explain_python_pick "$requested" "pyenv's $cand" "$ver" "$tier" "$lo" "$hi" "$cap" "$series"
                printf '%s\n' "$cand"
                return 0
            done < <(ls -1d "$pyenv_root"/versions/"$ver"*/bin/python"$ver" 2>/dev/null | sort -r)
        fi
        if [[ "$have_uv" -eq 1 ]]; then
            cand="$(UV_PYTHON_DOWNLOADS=never uv python find "$ver" 2>/dev/null)" || cand=""
            if [[ -n "$cand" && -x "$cand" ]]; then
                _explain_python_pick "$requested" "uv-managed $cand" "$ver" "$tier" "$lo" "$hi" "$cap" "$series"
                printf '%s\n' "$cand"
                return 0
            fi
        fi
    done < <(_candidate_versions "$lo" "$hi" "$requested" "$cap")
    return 1
}

cmd_create_venv() {
    local series="" pyver="" tool="" path="" profile=""
    local -a reqs_list=()
    local explicit_reqs=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) series="$2"; shift 2 ;;
            --python) pyver="$2"; shift 2 ;;
            --tool)   tool="$2"; shift 2 ;;
            --path)   path="$2"; shift 2 ;;
            --profile) profile="$2"; shift 2 ;;
            --requirements) reqs_list+=("$2"); explicit_reqs=1; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$series" ]] || { echo "x --series is required (e.g. --series 17.0)" >&2; return 2; }
    local _py_facts _py_lo _py_hi
    _py_facts="$(_python_recommendation "$series" "$profile")"
    _py_lo="$(_py_fact PY_MIN "$_py_facts")"; _py_hi="$(_py_fact PY_MAX "$_py_facts")"
    if [[ -z "$pyver" ]]; then
        pyver="$(_py_fact PY_RECOMMENDED "$_py_facts")"
    elif _py_outside_range "$pyver" "$_py_lo" "$_py_hi"; then
        echo "  Warning: Python $pyver is outside the range Odoo $series supports" >&2
        echo "  ($_py_lo-${_py_hi:-open}, source: $(_py_fact PY_SOURCE "$_py_facts"))." >&2
    fi
    [[ -n "$tool" ]]  || tool="uv"

    # A Python 2.7 target (the checkout declares Python 2, or --python 2.x):
    # uv and `python -m venv` cannot build it, and a Python 3 venv would be the
    # wrong interpreter - so find the 2.7 interpreter NOW, before anything is
    # built, and refuse (NEEDS_CONTEXT) rather than build something else.
    local py2=""
    if [[ "$pyver" == 2 || "$pyver" == 2.* ]]; then
        if ! py2="$(_find_python2)"; then
            echo "x NEEDS_CONTEXT: Odoo $series needs a Python 2.7 venv ($_py_lo-${_py_hi:-open}," >&2
            echo "  source: $(_py_fact PY_SOURCE "$_py_facts")) and no Python 2.7 interpreter is available." >&2
            echo "  Provide one, then re-run: install python2.7 (e.g. 'pyenv install 2.7.18'; uv" >&2
            echo "  cannot install Python 2), or set ODOO_AI_PYTHON2=/path/to/python2.7." >&2
            echo "  Nothing was built; 'python' was NOT recorded." >&2
            return 3
        fi
    fi

    # Early guard: resolve the ONE row the venv will be recorded on BEFORE building
    # anything - a series with only profiled rows and no --profile, or no declared
    # row at all, has nowhere clean to record the python path, so an expensive
    # build would be wasted. Same rule as the writer (instances_io.py read-row).
    if [[ -f "$INSTANCES_TOML" ]]; then
        python3 "$SCRIPT_DIR/../lib/instances_io.py" read-row "$INSTANCES_TOML" "$series" \
            "${profile:-}" >/dev/null || {
            echo "  python was NOT recorded; nothing was built." >&2
            return 1
        }
    fi

    # Venv path: when --profile is given and --path is absent, use a per-profile
    # path rooted at the resolver's Tier-2 SHARE dir (resolve_project_dir.sh
    # share) - converges across a repo's linked worktrees instead of the old
    # $ODOO_AI_DIR-relative (cwd/worktree-scoped) path.
    # follow-up: reclassify venvs/ to host-global by requirements-hash (deferred).
    if [[ -z "$path" ]]; then
        local share_dir
        share_dir="$(resolve_project_dir_share)" || {
            echo "x could not resolve the project SHARE dir for venvs/ (see resolve_project_dir.sh)." >&2
            return 1
        }
        if [[ -n "$profile" ]]; then
            local prof_slug
            prof_slug="$(printf '%s' "$profile" | tr -c '[:alnum:]._-' '_')"
            path="$share_dir/venvs/${series}-${prof_slug}"
        else
            path="$share_dir/venvs/$series"
        fi
    fi

    # Auto-collect requirements from profile's addons_path when not explicit.
    # When profile is given, read the specific (series, profile) instance so we
    # get the right addons_path; fall back to series-only for the unprofiled case.
    if [[ "$explicit_reqs" -eq 0 ]]; then
        local io="$SCRIPT_DIR/../lib/instances_io.py"
        local kv
        if [[ -f "$INSTANCES_TOML" && -f "$io" ]]; then
            kv="$(python3 "$io" read-row "$INSTANCES_TOML" "$series" "${profile:-}" 2>/dev/null)" || kv=""
            if [[ -n "$kv" ]]; then
                eval "$kv" 2>/dev/null || true
                local p
                _addons_path_to_array _ap "${INST_ADDONS_PATH:-}"
                for p in "${_ap[@]}"; do
                    [[ -n "$p" ]] || continue
                    [[ -f "$p/requirements.txt" ]] && reqs_list+=("$p/requirements.txt")
                    local up; up="$(dirname "$p")"
                    [[ -f "$up/requirements.txt" && "$up" != "$p" ]] && reqs_list+=("$up/requirements.txt")
                done
            fi
        fi
        # Deduplicate (preserve order, first occurrence wins).
        # Both expansions guard against set -u on empty arrays (bash 3.2+ portable).
        local -a uniq_reqs=()
        local seen_r=""
        for r in "${reqs_list[@]+"${reqs_list[@]}"}"; do
            if [[ ":${seen_r}:" != *":${r}:"* ]]; then
                uniq_reqs+=("$r")
                seen_r="${seen_r}:${r}"
            fi
        done
        reqs_list=("${uniq_reqs[@]+"${uniq_reqs[@]}"}")
    fi

    # Verify all repo dirs in the profile's addons_path exist BEFORE building the
    # venv. A missing repo means the profile is incomplete and the venv would be
    # built against an inconsistent source set. Fail-loud with actionable message
    # listing each missing path so the user knows exactly what to clone first.
    if [[ -n "${INST_ADDONS_PATH:-}" ]]; then
        local _missing_repos=()
        local _rp _rp_up
        _addons_path_to_array _rcheck "${INST_ADDONS_PATH}"
        for _rp in "${_rcheck[@]}"; do
            [[ -n "$_rp" ]] || continue
            # Accept either the dir itself or its parent (addons subdir pattern)
            _rp_up="$(dirname "$_rp")"
            if [[ ! -d "$_rp" && ! -d "$_rp_up" ]]; then
                _missing_repos+=("$_rp")
            elif [[ ! -d "$_rp" ]]; then
                # parent exists but addons subdir is missing
                _missing_repos+=("$_rp")
            fi
        done
        if [[ "${#_missing_repos[@]}" -gt 0 ]]; then
            echo "x Repo dirs missing from the profile's addons_path - clone them first:" >&2
            for _rp in "${_missing_repos[@]}"; do
                echo "  missing: $_rp" >&2
            done
            echo "  The 'python' field was NOT recorded." >&2
            return 1
        fi
    fi

    if [[ -n "$py2" ]]; then
        tool="virtualenv"
        echo "  Creating venv for Odoo $series at $path (python $py2, tool virtualenv: uv and pip venv cannot target Python 2)"
    else
        echo "  Creating venv for Odoo $series at $path (python ${pyver:-default}, tool $tool)"
    fi
    case "$tool" in
        virtualenv)
            local _p2rc=0
            _create_python2_venv "$py2" "$path" || _p2rc=$?
            if [[ "$_p2rc" -ne 0 ]]; then
                [[ "$_p2rc" -eq 3 ]] && return 3
                echo "x Python 2.7 venv creation failed." >&2
                return 1
            fi
            if [[ ${#reqs_list[@]} -gt 0 ]]; then
                local r
                for r in "${reqs_list[@]}"; do
                    if [[ -f "$r" ]]; then
                        echo "  Installing requirements: $r"
                        "$path/bin/pip" install -r "$r" \
                            || { echo "x dependency install failed for $r (check system build deps)." >&2; return 1; }
                    else
                        echo "  Warning: requirements file not found, skipping: $r" >&2
                    fi
                done
            else
                echo "  (no requirements.txt found - venv created empty; install deps manually)"
            fi
            ;;
        uv)
            command -v uv >/dev/null 2>&1 || { echo "x 'uv' not found. Install uv or use --tool pip." >&2; return 1; }
            if [[ -n "$pyver" ]]; then uv venv "$path" --python "$pyver"; else uv venv "$path"; fi
            if [[ ${#reqs_list[@]} -gt 0 ]]; then
                local r
                for r in "${reqs_list[@]}"; do
                    if [[ -f "$r" ]]; then
                        echo "  Installing requirements: $r"
                        uv pip install --python "$path/bin/python" -r "$r" \
                            || { echo "x dependency install failed for $r (check system build deps)." >&2; return 1; }
                    else
                        echo "  Warning: requirements file not found, skipping: $r" >&2
                    fi
                done
            else
                echo "  (no requirements.txt found - venv created empty; install deps manually)"
            fi
            ;;
        pip)
            local py="python3"
            if [[ -n "$pyver" ]]; then
                if command -v "python$pyver" >/dev/null 2>&1; then
                    py="python$pyver"
                elif py="$(_find_python3_in_range "$pyver" "$_py_lo" "$_py_hi" "$series")" && [[ -n "$py" ]]; then
                    :  # _find_python3_in_range already explained the pick on stderr
                else
                    echo "x NEEDS_CONTEXT: python$pyver is not on PATH and no other interpreter" >&2
                    echo "  inside Odoo $series's supported range ($_py_lo-${_py_hi:-open}, source:" >&2
                    echo "  $(_py_fact PY_SOURCE "$_py_facts")) was found (checked PATH, pyenv, and" >&2
                    echo "  already-installed uv-managed pythons - none is fetched for you)." >&2
                    echo "  Provide one, then re-run: install python$pyver (e.g. via pyenv or your" >&2
                    echo "  OS package manager), or use --tool uv (uv can fetch it automatically)." >&2
                    echo "  Nothing was built; 'python' was NOT recorded." >&2
                    return 3
                fi
            fi
            "$py" -m venv "$path" || { echo "x venv creation failed." >&2; return 1; }
            if [[ ${#reqs_list[@]} -gt 0 ]]; then
                local r
                for r in "${reqs_list[@]}"; do
                    if [[ -f "$r" ]]; then
                        echo "  Installing requirements: $r"
                        "$path/bin/pip" install -r "$r" \
                            || { echo "x dependency install failed for $r (check system build deps)." >&2; return 1; }
                    else
                        echo "  Warning: requirements file not found, skipping: $r" >&2
                    fi
                done
            else
                echo "  (no requirements.txt found - venv created empty; install deps manually)"
            fi
            ;;
        *) echo "x Unknown --tool '$tool'. Use uv or pip." >&2; return 2 ;;
    esac

    # Verify the venv can actually run Odoo before recording it as the instance
    # python. We do this by running `<venv_py> <odoo-bin> --version` which:
    #   - Uses the venv's own interpreter (correct even for python2 venvs on v8-v10)
    #   - Exercises odoo-bin's actual import path (sys.path[0] = repo root)
    #   - Works with namespace packages (Odoo v19 has no odoo/__init__.py so bare
    #     `import odoo` is a false-negative against a source-only checkout)
    # An empty venv or one with missing deps would silently poison step 50.
    local venv_py="$path/bin/python"
    if [[ ! -x "$venv_py" ]]; then
        echo "x venv python not found at $venv_py - creation failed." >&2
        return 1
    fi
    # Resolve core_bin: use the profile-specific INST_ADDONS_PATH when available
    # (set during the auto-collect requirements block above), else fall back to the
    # series-level scan.
    local core_bin=""
    if [[ -n "${INST_ADDONS_PATH:-}" ]]; then
        core_bin="$(_core_odoo_bin_from_addons_path "${INST_ADDONS_PATH}")" || core_bin=""
    fi
    if [[ -z "$core_bin" ]]; then
        core_bin="$(_core_odoo_bin_for_series "$series" "${profile:-}")" || core_bin=""
    fi
    if [[ -z "$core_bin" ]]; then
        echo "x No Odoo core repo (with odoo-bin, or openerp-server on the oldest series)" >&2
        echo "  found for series $series. A source instance REQUIRES the core repo present" >&2
        echo "  locally. Add the core repo (the dir containing that launcher) to this" >&2
        echo "  series' addons_path and" >&2
        echo "  re-run. The 'python' field was NOT recorded." >&2
        return 1
    fi
    if ! "$venv_py" "$core_bin" --version >/dev/null 2>&1; then
        echo "x '$venv_py $core_bin --version' failed - the venv cannot run Odoo." >&2
        echo "  The venv is missing Odoo's deps (lxml/psycopg2/...). Pass --requirements" >&2
        echo "  <repo>/requirements.txt for every repo. 'python' was NOT recorded." >&2
        return 1
    fi

    # Record the VERIFIED environment facts on the instance so step 50 and the
    # allocator use them: `python` (the interpreter just proven able to run
    # odoo-bin), `odoo_root` (that same repo's root - what makes `import odoo`
    # resolve for a source checkout), and the Postgres client surface
    # (`db_run_mode`/`db_container`). Matches on (series, profile) and INSERTS a
    # key whose line is absent, so a catalog written before a key existed gains it.
    local _rec_rc=0
    _record_env_facts "$series" "$profile" "$venv_py" "$(dirname "$core_bin")" || _rec_rc=$?
    _report_db_preflight "$series" "$profile"
    # A detector that could not decide is reported, not fatal: the venv IS ready
    # and every non-ephemeral mode works without the client-surface fact.
    if [[ "$_rec_rc" -ne 0 ]]; then
        echo "  Warning: db_run_mode was NOT recorded (see the message above);" >&2
        echo "  re-run '$(basename "$0") record-env --series $series' once resolved." >&2
    fi
    echo "ok venv ready: $venv_py"
}

# --- interpreter preflight ------------------------------------------------------------------
# A step that cannot run python must report THAT, not an empty catalog. Every catalog read below
# goes through `python3` with its stderr suppressed, which is right for an absent optional fact
# and wrong for a broken interpreter - the two become indistinguishable, and the operator is shown
# a downstream symptom instead of the cause. SSOT: scripts/lib/require_python.sh.
# `describe` and the usage arm are pure text, so they stay runnable on a host with no python.
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
    suggest)  shift; cmd_suggest "$@" ;;
    create-venv) shift; cmd_create_venv "$@" ;;
    record-env)  shift; cmd_record_env "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|suggest <series> [--profile P]|create-venv ...|record-env --series X.Y [--profile P]}" >&2; exit 2 ;;
esac
