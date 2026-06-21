#!/usr/bin/env bash
# 45-venv.sh - Optional helper to provision a Python virtualenv for an Odoo
# instance (source mode). Each Odoo series supports only certain Python
# versions, so this reads the recommended version from odoo-python-matrix.json
# and lets the user reuse an existing venv or build a new one with uv or pip.
#
# This step is OPT-IN: its `check` always reports satisfied so the `all` filter
# never auto-builds a venv (building lxml/psycopg2 can be heavy and needs system
# build deps). The setup command calls `create-venv` only when the user asks.
#
# CONFIG (env overrides):
#   ODOO_AI_DIR        project state dir     (default $PWD/.odoo-ai)
#   ODOO_AI_HOME       machine-global dir    (default $HOME/.odoo-ai)
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#
# Subcommands:
#   describe
#   suggest <series>                 print the recommended Python for a series
#   apply                            advise-only: explain venv options
#   create-venv --series X.Y [--python VER] [--tool uv|pip]
#               [--path DIR] [--requirements FILE]
#                                    create a venv and record it on the instance

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
MATRIX_JSON="$SCRIPT_DIR/../lib/odoo-python-matrix.json"
ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"
# instances.toml is machine-global; resolve it (global-wins) via the shared helper.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
INSTANCES_TOML="$(_resolve_instances)"

cmd_describe() {
    echo "Optionally create a Python venv for an Odoo instance (reuse existing, or build with uv/pip)"
}

# Print recommended Python for a series, or nothing.
_suggested_python() {
    [[ -f "$MATRIX_JSON" ]] || return 0
    python3 - "$MATRIX_JSON" "$1" <<'PY' 2>/dev/null || true
import json, sys
try:
    m = json.load(open(sys.argv[1]))
    e = m.get("odoo_python_matrix", {}).get(sys.argv[2])
    if e and e.get("recommended"):
        out = e["recommended"]
        if e.get("python2"):
            out += " (Python 2 - EOL, not recommended for new work)"
        print(out)
except Exception:
    pass
PY
}

cmd_suggest() {
    local series="${1:-}"
    [[ -n "$series" ]] || { echo "Usage: $(basename "$0") suggest <series>" >&2; return 2; }
    local rec
    rec="$(_suggested_python "$series")"
    if [[ -n "$rec" ]]; then
        echo "Recommended Python for Odoo $series: $rec"
    else
        echo "No recommendation on file for Odoo $series."
    fi
}

# check is always satisfied: venv provisioning is opt-in, not part of the
# automatic step run.
cmd_check() { return 0; }

cmd_apply() {
    echo "Python venv is optional and opt-in. For an Odoo source instance you can:"
    echo "  - Reuse an existing venv: set its python in .odoo-ai/instances.toml"
    echo "    (the 'python' field of the matching [[instance]]) or export ODOO_PYTHON."
    echo "  - Build a new one for a series (recommended Python is suggested per series):"
    echo "      $(basename "$0") create-venv --series 17.0 --tool uv"
    echo "      $(basename "$0") create-venv --series 17.0 --tool pip --python 3.12"
    echo "Building installs the series' requirements.txt and needs system build deps"
    echo "(build-essential, python3-dev, libxml2-dev, libxslt1-dev, libpq-dev, ...)."
    echo "setup never installs those for you."
}

# Find odoo-bin's repo root for a series (and optional profile), to locate
# requirements.txt. Best effort: scans the instance's addons_path entries
# one level up. When profile is given, reads the (series, profile) instance
# so the right addons_path is used (avoids picking a different profile's core).
_core_root_for_series() {
    local series="$1" profile="${2:-}" io="$SCRIPT_DIR/../lib/instances_io.py"
    [[ -f "$INSTANCES_TOML" && -f "$io" ]] || return 0
    local kv
    kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || return 0
    eval "$kv" 2>/dev/null || return 0
    local p
    IFS=':' read -ra _paths <<<"${INST_ADDONS_PATH:-}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        [[ -f "$p/requirements.txt" && -x "$p/odoo-bin" ]] && { echo "$p"; return 0; }
        local up; up="$(dirname "$p")"
        [[ -f "$up/requirements.txt" && -x "$up/odoo-bin" ]] && { echo "$up"; return 0; }
    done
    return 0
}

# Echo absolute path to odoo-bin for a series (and optional profile), or nothing.
_core_odoo_bin_for_series() {
    local root; root="$(_core_root_for_series "$1" "${2:-}")" || return 0
    [[ -n "$root" && -x "$root/odoo-bin" ]] && echo "$root/odoo-bin"
    return 0
}

# Echo absolute path to odoo-bin scanning a colon-separated addons_path string.
# Used when INST_ADDONS_PATH is already resolved (e.g. from a profiled read).
_core_odoo_bin_from_addons_path() {
    local addons_path="$1"
    local p up
    IFS=':' read -ra _bp <<<"${addons_path}"
    for p in "${_bp[@]}"; do
        [[ -n "$p" ]] || continue
        [[ -x "$p/odoo-bin" ]] && { echo "$p/odoo-bin"; return 0; }
        up="$(dirname "$p")"
        [[ -x "$up/odoo-bin" ]] && { echo "$up/odoo-bin"; return 0; }
    done
    return 0
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
    [[ -n "$pyver" ]] || pyver="$(_suggested_python "$series" | sed -E 's/ .*//')"
    [[ -n "$tool" ]]  || tool="uv"

    # Early guard: when --profile is omitted but the toml has ONLY profiled blocks
    # for this series, fail-loud BEFORE building anything. This avoids building an
    # expensive venv only to discover we have nowhere clean to record the python path.
    if [[ -z "$profile" && -f "$INSTANCES_TOML" ]]; then
        local _ep_rc=0
        python3 - "$INSTANCES_TOML" "$series" <<'PY' 2>&1 || _ep_rc=$?
import sys, re

path, series = sys.argv[1], sys.argv[2]
try:
    src = open(path, encoding="utf-8").read()
except OSError:
    sys.exit(0)

in_block = False
block_series = ""
block_profile = ""
profiled_series = set()
unprofiled_series = set()

def flush():
    global in_block, block_series, block_profile
    if in_block and block_series:
        if block_profile:
            profiled_series.add(block_series)
        else:
            unprofiled_series.add(block_series)
    in_block = False
    block_series = ""
    block_profile = ""

for raw_line in src.splitlines():
    s = raw_line.strip()
    if s == "[[instance]]":
        flush()
        in_block = True
    elif s.startswith("["):
        flush()
    if in_block and s.startswith("series") and "=" in s:
        block_series = s.split("=", 1)[1].strip().strip('"').strip("'")
    if in_block and s.startswith("profile") and "=" in s:
        block_profile = s.split("=", 1)[1].strip().strip('"').strip("'")
flush()

if series in profiled_series and series not in unprofiled_series:
    print(
        f"x series {series!r} has only profile-specific [[instance]] blocks but "
        f"create-venv was called without --profile. Pass --profile <name> to "
        f"select the correct block. python was NOT recorded.",
        file=sys.stderr,
    )
    sys.exit(1)
PY
        [[ "$_ep_rc" -eq 0 ]] || return "$_ep_rc"
    fi

    # Venv path: when --profile is given and --path is absent, use a per-profile path.
    if [[ -z "$path" ]]; then
        if [[ -n "$profile" ]]; then
            local prof_slug
            prof_slug="$(printf '%s' "$profile" | tr -c '[:alnum:]._-' '_')"
            path="$ODOO_AI_DIR/venvs/${series}-${prof_slug}"
        else
            path="$ODOO_AI_DIR/venvs/$series"
        fi
    fi

    # Auto-collect requirements from profile's addons_path when not explicit.
    # When profile is given, read the specific (series, profile) instance so we
    # get the right addons_path; fall back to series-only for the unprofiled case.
    if [[ "$explicit_reqs" -eq 0 ]]; then
        local io="$SCRIPT_DIR/../lib/instances_io.py"
        local kv
        if [[ -f "$INSTANCES_TOML" && -f "$io" ]]; then
            kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "${profile:-}" 2>/dev/null)" || kv=""
            if [[ -n "$kv" ]]; then
                eval "$kv" 2>/dev/null || true
                local p
                IFS=':' read -ra _ap <<<"${INST_ADDONS_PATH:-}"
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
        IFS=':' read -ra _rcheck <<<"${INST_ADDONS_PATH}"
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

    echo "  Creating venv for Odoo $series at $path (python ${pyver:-default}, tool $tool)"
    case "$tool" in
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
                else
                    echo "  Note: python$pyver not found on PATH; falling back to python3" >&2
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
        echo "x No Odoo core repo (with odoo-bin) found for series $series." >&2
        echo "  A source instance REQUIRES the core repo present locally. Add the" >&2
        echo "  core repo (dir containing odoo-bin) to this series' addons_path and" >&2
        echo "  re-run. The 'python' field was NOT recorded." >&2
        return 1
    fi
    if ! "$venv_py" "$core_bin" --version >/dev/null 2>&1; then
        echo "x '$venv_py $core_bin --version' failed - the venv cannot run Odoo." >&2
        echo "  The venv is missing Odoo's deps (lxml/psycopg2/...). Pass --requirements" >&2
        echo "  <repo>/requirements.txt for every repo. 'python' was NOT recorded." >&2
        return 1
    fi

    # Record the interpreter on the instance so step 50 uses it.
    # Matches on (series, profile): when profile is set, only update the [[instance]]
    # block whose series AND profile both match. When profile is empty, match by
    # series only (first matching block, preserving backward compat).
    # NOTE: this only REPLACES an existing `python = ...` line in the matched
    # [[instance]] block; it assumes step 40 already wrote a `python = ""`
    # placeholder line into that block. If the line is absent, nothing is written.
    if [[ -f "$INSTANCES_TOML" ]]; then
        local _rec_rc=0
        python3 - "$INSTANCES_TOML" "$series" "$venv_py" "$profile" <<'PY' || _rec_rc=$?
import sys
path, series, py, profile = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    src = open(path, encoding="utf-8").read()
except OSError:
    sys.exit(0)
lines = src.splitlines(keepends=True)
out = []
in_block = False
block_series = ""
block_profile = ""
matched = False
updated = False

# When profile is empty: only match unprofiled blocks (block_profile == "").
# Detect whether the series has ONLY profiled blocks (no unprofiled block to
# write to) so we can fail-loud instead of silently poisoning the wrong block.
if profile == "":
    # Mini scan: collect (series, has_profile) pairs for each [[instance]] block.
    _in = False
    _bs = ""
    _bp = ""
    _profiled_series = set()    # series that have at least one profiled block
    _unprofiled_series = set()  # series that have at least one unprofiled block
    def _flush():
        if _in and _bs:
            if _bp:
                _profiled_series.add(_bs)
            else:
                _unprofiled_series.add(_bs)
    for raw_line in lines:
        s = raw_line.strip()
        if s == "[[instance]]":
            _flush()
            _in = True; _bs = ""; _bp = ""
        elif s.startswith("["):
            _flush()
            _in = False; _bs = ""; _bp = ""
        if _in and s.startswith("series") and "=" in s:
            _bs = s.split("=", 1)[1].strip().strip('"').strip("'")
        if _in and s.startswith("profile") and "=" in s:
            _bp = s.split("=", 1)[1].strip().strip('"').strip("'")
    _flush()  # flush last block
    # Fail-loud only when ALL blocks for this series are profiled (none unprofiled).
    if series in _profiled_series and series not in _unprofiled_series:
        print(
            f"x series {series!r} has only profile-specific [[instance]] blocks but "
            f"create-venv was called without --profile. Pass --profile <name> to "
            f"select the correct block. python was NOT recorded.",
            file=sys.stderr,
        )
        sys.exit(1)

for line in lines:
    s = line.strip()
    if s == "[[instance]]":
        in_block = True
        block_series = ""
        block_profile = ""
        matched = False
    elif s.startswith("["):
        in_block = False
        matched = False
    if in_block and s.startswith("series") and "=" in s:
        block_series = s.split("=", 1)[1].strip().strip('"').strip("'")
    if in_block and s.startswith("profile") and "=" in s:
        block_profile = s.split("=", 1)[1].strip().strip('"').strip("'")
    # Re-evaluate match: stricter than select_instance (refuses to guess a profiled block when no --profile is given).
    # profile=="" -> only match blocks where block_profile=="" (unprofiled).
    # profile set  -> match blocks where block_series==series AND block_profile==profile.
    if in_block and block_series:
        if block_series == series:
            if profile == "" and block_profile == "":
                matched = True
            elif profile != "" and block_profile == profile:
                matched = True
            else:
                matched = False
        else:
            matched = False
    if in_block and matched and s.startswith("python") and "=" in s and not updated:
        indent = line[:len(line) - len(line.lstrip())]
        out.append(f'{indent}python = "{py}"\n')
        updated = True
        continue
    out.append(line)
if updated:
    open(path, "w", encoding="utf-8").write("".join(out))
    label = f"{series}:{profile}" if profile else series
    print(f"  recorded python for {label} -> {py}")
PY
        # Propagate non-zero exit from the recorder (e.g. fail-loud on profile
        # ambiguity: sys.exit(1) in the Python block above).
        [[ "$_rec_rc" -eq 0 ]] || return "$_rec_rc"
    fi
    echo "ok venv ready: $venv_py"
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    suggest)  shift; cmd_suggest "$@" ;;
    create-venv) shift; cmd_create_venv "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|suggest <series>|create-venv ...}" >&2; exit 2 ;;
esac
