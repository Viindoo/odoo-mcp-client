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
#   ODOO_AI_DIR     state dir (default $PWD/.odoo-ai)
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
INSTANCES_TOML="$ODOO_AI_DIR/instances.toml"

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

# Find odoo-bin's repo root for a series, to locate requirements.txt. Best
# effort: scans the instance's addons_path entries one level up.
_core_root_for_series() {
    local series="$1" io="$SCRIPT_DIR/../lib/instances_io.py"
    [[ -f "$INSTANCES_TOML" && -f "$io" ]] || return 0
    local kv
    kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" 2>/dev/null)" || return 0
    eval "$kv" 2>/dev/null || return 0
    local p
    IFS=':' read -ra _paths <<<"${INST_ADDONS_PATH:-}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        [[ -f "$p/requirements.txt" && -x "$p/odoo-bin" ]] && { echo "$p"; return 0; }
        local up; up="$(dirname "$p")"
        [[ -f "$up/requirements.txt" && -x "$up/odoo-bin" ]] && { echo "$up"; return 0; }
    done
}

cmd_create_venv() {
    local series="" pyver="" tool="" path="" reqs=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) series="$2"; shift 2 ;;
            --python) pyver="$2"; shift 2 ;;
            --tool)   tool="$2"; shift 2 ;;
            --path)   path="$2"; shift 2 ;;
            --requirements) reqs="$2"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; return 2 ;;
        esac
    done
    [[ -n "$series" ]] || { echo "x --series is required (e.g. --series 17.0)" >&2; return 2; }
    [[ -n "$pyver" ]] || pyver="$(_suggested_python "$series" | sed -E 's/ .*//')"
    [[ -n "$tool" ]]  || tool="uv"
    [[ -n "$path" ]]  || path="$ODOO_AI_DIR/venvs/$series"

    # Resolve requirements.txt if not given.
    if [[ -z "$reqs" ]]; then
        local core; core="$(_core_root_for_series "$series")"
        [[ -n "$core" ]] && reqs="$core/requirements.txt"
    fi

    echo "  Creating venv for Odoo $series at $path (python ${pyver:-default}, tool $tool)"
    case "$tool" in
        uv)
            command -v uv >/dev/null 2>&1 || { echo "x 'uv' not found. Install uv or use --tool pip." >&2; return 1; }
            if [[ -n "$pyver" ]]; then uv venv "$path" --python "$pyver"; else uv venv "$path"; fi
            if [[ -n "$reqs" && -f "$reqs" ]]; then
                uv pip install --python "$path/bin/python" -r "$reqs" \
                    || { echo "x dependency install failed (check system build deps)." >&2; return 1; }
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
            if [[ -n "$reqs" && -f "$reqs" ]]; then
                "$path/bin/pip" install -r "$reqs" \
                    || { echo "x dependency install failed (check system build deps)." >&2; return 1; }
            else
                echo "  (no requirements.txt found - venv created empty; install deps manually)"
            fi
            ;;
        *) echo "x Unknown --tool '$tool'. Use uv or pip." >&2; return 2 ;;
    esac

    # Record the interpreter on the instance so step 50 uses it.
    # NOTE: this only REPLACES an existing `python = ...` line in the matched
    # [[instance]] block; it assumes step 40 already wrote a `python = ""`
    # placeholder line into that block. If the line is absent, nothing is written.
    if [[ -f "$INSTANCES_TOML" && -x "$path/bin/python" ]]; then
        python3 - "$INSTANCES_TOML" "$series" "$path/bin/python" <<'PY' || true
import sys
path, series, py = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    src = open(path, encoding="utf-8").read()
except OSError:
    sys.exit(0)
lines = src.splitlines(keepends=True)
out, in_block, matched, updated = [], False, False, False
for line in lines:
    s = line.strip()
    if s == "[[instance]]":
        in_block, matched = True, False
    elif s.startswith("["):
        in_block, matched = False, False
    if in_block and s.startswith("series") and "=" in s:
        val = s.split("=", 1)[1].strip().strip('"').strip("'")
        matched = (val == series)
    if in_block and matched and s.startswith("python") and "=" in s:
        indent = line[:len(line) - len(line.lstrip())]
        out.append(f'{indent}python = "{py}"\n')
        updated = True
        continue
    out.append(line)
if updated:
    open(path, "w", encoding="utf-8").write("".join(out))
    print(f"  recorded python for {series} -> {py}")
PY
    fi
    echo "ok venv ready: $path/bin/python"
}

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    suggest)  shift; cmd_suggest "$@" ;;
    create-venv) shift; cmd_create_venv "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|suggest <series>|create-venv ...}" >&2; exit 2 ;;
esac
