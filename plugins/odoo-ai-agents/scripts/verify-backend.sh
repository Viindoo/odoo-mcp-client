#!/usr/bin/env bash
# verify-backend.sh - pylint-odoo code-quality gate for Odoo backend Python.
#
# The backend sibling of verify-frontend.sh: a fast, no-DB, pre-push static gate
# that reproduces the `pylint-odoo` half of the Odoo code-quality CI gate
# LOCALLY, so backend lint failures are caught before push instead of in CI.
#
# WHAT IT DOES
#   Runs `pylint --load-plugins=pylint_odoo` over changed .py files, using a
#   version-matched pylint/astroid/pylint-odoo toolchain (pins resolved from
#   scripts/lib/odoo-python-matrix.json) in an ISOLATED tools venv that never
#   touches the instance venv. Enabled-codes come from the deployment's own
#   quality module when present (single source of truth), else a shipped fallback.
#
# THE VANILLA TRAP (why we never run bare pylint):
#   `# pylint: disable=consider-merging-classes-inherited` (R8180) is valid only
#   because pylint_odoo registers that message. Without the plugin loaded the same
#   pragma reads as unknown-option-value (W0012) - not suppressed by --disable=all
#   - looking like a failure to "fix" by deleting the pragma, which re-breaks real
#   CI. This gate ALWAYS loads pylint_odoo. See docs/reference/odoo-code-quality.md.
#
# USAGE:
#   verify-backend.sh [--series X.Y] [file ...]
#   verify-backend.sh                       (defaults to `git diff --name-only HEAD`, .py only)
#   verify-backend.sh --provision [--series X.Y] [--tool uv|pip]
#                                           (opt-in: build the pinned tools venv, then exit)
#
# ENV OVERRIDES:
#   CLAUDE_PLUGIN_ROOT    plugin root (required for matrix + fallback pylintrc)
#   ODOO_GIT_BASE         where Odoo/addons checkouts live (default: ~/git)
#   ODOO_AI_DIR           state dir for the tools venv (default: $PWD/.odoo-ai)
#   ODOO_SERIES           Odoo series (e.g. 17.0) when not resolvable from context
#   ODOO_PYLINTRC         explicit path to a pylintrc (highest-priority config)
#   VERIFY_BACKEND_BASE   git diff base ref (default: HEAD)
#   VERIFY_BACKEND_GIT_DIR  run git diff in this worktree (default: cwd) - set when reviewing a sibling worktree
#
# EXIT CODE:
#   0  passed, or degraded gracefully to warn-only (no toolchain / no series / no files)
#   1  at least one real pylint-odoo finding (BLOCK)

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve CLAUDE_PLUGIN_ROOT
# ---------------------------------------------------------------------------
if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CLAUDE_PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
fi

MATRIX_JSON="${CLAUDE_PLUGIN_ROOT}/scripts/lib/odoo-python-matrix.json"
FALLBACK_PYLINTRC="${CLAUDE_PLUGIN_ROOT}/scripts/odoo-pylintrc"
ODOO_GIT_BASE="${ODOO_GIT_BASE:-$HOME/git}"
ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"
VERIFY_BASE="${VERIFY_BACKEND_BASE:-HEAD}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_have() { command -v "$1" >/dev/null 2>&1; }

BLOCK_COUNT=0
WARN_COUNT=0
_block() { echo "  [BLOCK] $*"; BLOCK_COUNT=$((BLOCK_COUNT + 1)); }
_warn()  { echo "  [WARN ] $*"; WARN_COUNT=$((WARN_COUNT + 1)); }
_ok()    { echo "  [  ok ] $*"; }
_info()  { echo "  [info ] $*"; }
_skip()  { echo "  [skip ] $*"; }

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
PROVISION=false
SERIES="${ODOO_SERIES:-}"
PROV_TOOL=""
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --provision) PROVISION=true; shift ;;
        --series)    SERIES="$2"; shift 2 ;;
        --tool)      PROV_TOOL="$2"; shift 2 ;;
        --) shift; while [[ $# -gt 0 ]]; do ARGS+=("$1"); shift; done ;;
        *)  ARGS+=("$1"); shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve Odoo series: --series / $ODOO_SERIES > .odoo-ai/context.md odoo_version
# ---------------------------------------------------------------------------
_resolve_series_from_context() {
    local ctx=".odoo-ai/context.md"
    [[ -f "$ctx" ]] || return 0
    # context.md uses Markdown bullets: "- **odoo_version**: 17.0"
    grep -iE '^[-*][[:space:]]*\**odoo_version' "$ctx" 2>/dev/null \
        | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1 || true
}

if [[ -z "$SERIES" ]]; then
    SERIES="$(_resolve_series_from_context)"
fi

# ---------------------------------------------------------------------------
# Resolve lint pins from the matrix for the series
# ---------------------------------------------------------------------------
# Sets PIN_PYLINT_ODOO / PIN_PYLINT / PIN_ASTROID / PIN_BEST_EFFORT
_load_pins() {
    [[ -n "$SERIES" && -f "$MATRIX_JSON" ]] || return 0
    local out
    # shlex.quote each value: pins use range specifiers (e.g. ">=2.15,<2.16") whose '>' '<'
    # would otherwise be parsed as shell redirections by `eval`, silently emptying the pin.
    out="$(python3 - "$MATRIX_JSON" "$SERIES" <<'PY' 2>/dev/null || true
import json, shlex, sys
try:
    m = json.load(open(sys.argv[1]))
    e = m.get("odoo_python_matrix", {}).get(sys.argv[2], {})
    lint = e.get("lint") or {}
    print("PIN_PYLINT_ODOO=%s" % shlex.quote(lint.get("pylint_odoo", "")))
    print("PIN_PYLINT=%s" % shlex.quote(lint.get("pylint", "")))
    print("PIN_ASTROID=%s" % shlex.quote(lint.get("astroid", "")))
    print("PIN_BEST_EFFORT=%s" % ("1" if lint.get("best_effort") else ""))
except Exception:
    pass
PY
)"
    [[ -n "$out" ]] && eval "$out"
}
PIN_PYLINT_ODOO=""; PIN_PYLINT=""; PIN_ASTROID=""; PIN_BEST_EFFORT=""
_load_pins

TOOLS_VENV="$ODOO_AI_DIR/tools/pylint-${SERIES:-default}"

# ---------------------------------------------------------------------------
# Provision (opt-in): build the pinned isolated tools venv
# ---------------------------------------------------------------------------
_provision() {
    echo "============================================================"
    echo " verify-backend --provision (series ${SERIES:-unknown})"
    echo "============================================================"
    if [[ -z "$SERIES" ]]; then
        _block "no Odoo series resolved - pass --series X.Y or set ODOO_SERIES / .odoo-ai/context.md"
        return 1
    fi
    if [[ -z "$PIN_PYLINT_ODOO" ]]; then
        _block "no lint pins for series $SERIES in $MATRIX_JSON"
        return 1
    fi
    local tool="${PROV_TOOL:-uv}"
    _have "$tool" || { [[ "$tool" == "uv" ]] && tool="pip" || true; }
    # Tools-venv Python must match the pinned linter (e.g. pylint 2.15 needs <=3.11),
    # NOT the instance 'recommended' Python - use lint_python when pinned.
    local pyver
    pyver="$(python3 - "$MATRIX_JSON" "$SERIES" <<'PY' 2>/dev/null || true
import json,sys
m=json.load(open(sys.argv[1])); e=m.get("odoo_python_matrix",{}).get(sys.argv[2],{})
lint=e.get("lint") or {}
print(lint.get("lint_python") or ("" if e.get("python2") else e.get("recommended","")))
PY
)"
    _info "installing pylint${PIN_PYLINT} astroid${PIN_ASTROID} pylint-odoo${PIN_PYLINT_ODOO} into $TOOLS_VENV"
    mkdir -p "$(dirname "$TOOLS_VENV")"
    if [[ "$tool" == "uv" ]] && _have uv; then
        if [[ -n "$pyver" ]]; then uv venv "$TOOLS_VENV" --python "$pyver" || uv venv "$TOOLS_VENV"; else uv venv "$TOOLS_VENV"; fi
        uv pip install --python "$TOOLS_VENV/bin/python" \
            "pylint${PIN_PYLINT}" "astroid${PIN_ASTROID}" "pylint-odoo${PIN_PYLINT_ODOO}" \
            || { _block "tools install failed"; return 1; }
    elif _have python3; then
        python3 -m venv "$TOOLS_VENV" || { _block "venv creation failed"; return 1; }
        "$TOOLS_VENV/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
        "$TOOLS_VENV/bin/pip" install \
            "pylint${PIN_PYLINT}" "astroid${PIN_ASTROID}" "pylint-odoo${PIN_PYLINT_ODOO}" \
            || { _block "tools install failed"; return 1; }
    else
        _block "neither uv nor python3 available to provision the tools venv"
        return 1
    fi
    _ok "tools venv ready: $TOOLS_VENV/bin/pylint"
}

if [[ "$PROVISION" == "true" ]]; then
    _provision
    exit $?
fi

# ---------------------------------------------------------------------------
# Locate a pylint that can load pylint_odoo
#   1. isolated tools venv  2. PATH pylint (with pylint_odoo importable)
# ---------------------------------------------------------------------------
PYLINT_BIN=""
if [[ -x "$TOOLS_VENV/bin/pylint" ]] && "$TOOLS_VENV/bin/python" -c "import pylint_odoo" >/dev/null 2>&1; then
    PYLINT_BIN="$TOOLS_VENV/bin/pylint"
elif _have pylint && python3 -c "import pylint_odoo" >/dev/null 2>&1; then
    PYLINT_BIN="$(command -v pylint)"
fi

if [[ -z "$PYLINT_BIN" ]]; then
    echo "============================================================"
    echo " verify-backend - toolchain"
    echo "============================================================"
    _warn "pylint + pylint_odoo not available - skipping backend lint (graceful degrade)"
    _info "to enable the HARD gate, provision the pinned toolchain:"
    _info "    $(basename "$0") --provision --series ${SERIES:-<X.Y>}"
    _info "  (installs pylint${PIN_PYLINT:-} astroid${PIN_ASTROID:-} pylint-odoo${PIN_PYLINT_ODOO:-} into $TOOLS_VENV)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Resolve the pylintrc / enabled-codes
#   1. $ODOO_PYLINTRC (explicit)
#   2. deployment quality module (test_pylint / test_lint) on addons path - SSOT
#   3. repo-root pylintrc
#   4. shipped fallback
# ---------------------------------------------------------------------------
RCFILE=""
ENABLE_FROM_MODULE=""
_find_quality_module_rc() {
    # Look for a `test_pylint`/`test_lint` module dir in cwd or ODOO_GIT_BASE and
    # a pylintrc within it. Best-effort; returns a path on stdout or nothing.
    local d
    while IFS= read -r d; do
        for rc in "$d/.pylintrc" "$d/pylintrc" "$d/.pylintrc-mandatory"; do
            [[ -f "$rc" ]] && { echo "$rc"; return 0; }
        done
    done < <(find . "$ODOO_GIT_BASE" -maxdepth 4 -type d \( -name 'test_pylint' -o -name 'test_lint' \) 2>/dev/null | head -5)
}
_derive_enabled_codes() {
    # Best-effort: a deployment quality module may pin ENABLED_CODES in Python.
    # Extract the symbol list and turn it into a comma-joined --enable value.
    local d
    while IFS= read -r d; do
        python3 - "$d" <<'PY' 2>/dev/null && return 0
import os, re, sys
root = sys.argv[1]
codes = []
for dp, _, fns in os.walk(root):
    for fn in fns:
        if not fn.endswith(".py"):
            continue
        try:
            txt = open(os.path.join(dp, fn), encoding="utf-8").read()
        except OSError:
            continue
        # Strip '#'-comment tails (per line) BEFORE the regex so codes a
        # deployment intentionally commented out (license-allowed C8105,
        # manifest-version-format C8106, missing-readme C8112, ...) are NOT
        # silently re-enabled, and a ')' inside a comment can't truncate the list.
        txt = "\n".join(ln.split("#", 1)[0] for ln in txt.splitlines())
        m = re.search(r'ENABLED_CODES\s*=\s*[\[\(](.*?)[\]\)]', txt, re.S)
        if m:
            codes = re.findall(r'["\']([A-Za-z0-9_-]+)["\']', m.group(1))
            break
    if codes:
        break
if codes:
    print(",".join(codes))
    sys.exit(0)
sys.exit(1)
PY
    done < <(find . "$ODOO_GIT_BASE" -maxdepth 4 -type d \( -name 'test_pylint' -o -name 'test_lint' \) 2>/dev/null | head -5)
    return 1
}
_quality_module_present() {
    # True if a deployment quality module dir exists (even when we can't derive
    # its ENABLED_CODES) - lets us fail-closed instead of silently passing (B2).
    local d
    d="$(find . "$ODOO_GIT_BASE" -maxdepth 4 -type d \( -name 'test_pylint' -o -name 'test_lint' \) 2>/dev/null | head -1 || true)"
    [[ -n "$d" ]]
}

DERIVE_FAILED=""
if [[ -n "${ODOO_PYLINTRC:-}" && -f "${ODOO_PYLINTRC}" ]]; then
    RCFILE="$ODOO_PYLINTRC"
    RC_SRC="env ODOO_PYLINTRC"
else
    _mod_rc="$(_find_quality_module_rc || true)"
    if [[ -n "$_mod_rc" ]]; then
        RCFILE="$_mod_rc"
        RC_SRC="deployment quality module ($_mod_rc)"
    else
        _enable="$(_derive_enabled_codes || true)"
        if [[ -n "$_enable" ]]; then
            ENABLE_FROM_MODULE="$_enable"
            RCFILE="$FALLBACK_PYLINTRC"
            RC_SRC="shipped fallback + ENABLED_CODES derived from deployment quality module"
        elif [[ -f "pylintrc" || -f ".pylintrc" ]]; then
            RCFILE="$([[ -f .pylintrc ]] && echo .pylintrc || echo pylintrc)"
            RC_SRC="repo-root $RCFILE"
        elif _quality_module_present; then
            # B2 fail-closed: a quality module exists but its whitelist could NOT be
            # derived and there is no pylintrc to fall back on. NEVER run an empty
            # whitelist (that would --disable=all and pass with zero checks = false
            # GREEN). Run the full shipped fallback config and flag the gap LOUDLY below.
            DERIVE_FAILED=1
            RCFILE="$FALLBACK_PYLINTRC"
            RC_SRC="shipped fallback (could NOT derive whitelist from quality module)"
        else
            RCFILE="$FALLBACK_PYLINTRC"
            RC_SRC="shipped fallback odoo-pylintrc"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Collect .py files
# ---------------------------------------------------------------------------
if [[ ${#ARGS[@]} -gt 0 ]]; then
    FILES=("${ARGS[@]}")
else
    FILES=()
    while IFS= read -r _line; do FILES+=("$_line"); done \
        < <(git ${VERIFY_BACKEND_GIT_DIR:+-C "$VERIFY_BACKEND_GIT_DIR"} diff --name-only "${VERIFY_BASE}" 2>/dev/null || true)
fi
PY_FILES=()
for f in "${FILES[@]:-}"; do
    [[ -n "$f" && -f "$f" && "$f" == *.py ]] && PY_FILES+=("$f")
done

echo "============================================================"
echo " verify-backend - pylint-odoo gate"
echo "============================================================"
_info "series   : ${SERIES:-<unknown>}${PIN_BEST_EFFORT:+ (best-effort: pre-16 series)}"
_info "pylint   : $PYLINT_BIN"
_info "config   : $RC_SRC"
[[ -n "$ENABLE_FROM_MODULE" ]] && _info "enable   : ${ENABLE_FROM_MODULE}"
if [[ -n "$DERIVE_FAILED" ]]; then
    _warn "could not derive the deployment whitelist from its quality module - running the FULL shipped fallback config instead (fail-closed); this gate is NOT a silent pass. Fix the quality module's ENABLED_CODES or set ODOO_PYLINTRC."
fi

if [[ ${#PY_FILES[@]} -eq 0 ]]; then
    _skip "no changed .py files to check"
    echo "  RESULT: PASS (clean)"
    exit 0
fi
_info "files    : ${#PY_FILES[@]}"

# ---------------------------------------------------------------------------
# Run pylint with pylint_odoo ALWAYS loaded (the trap guard)
# ---------------------------------------------------------------------------
PYLINT_ARGS=(--rcfile="$RCFILE" --load-plugins=pylint_odoo
             --score=no --reports=no
             --msg-template='{path}:{line}: [{msg_id}({symbol})] {msg}')
# When the enabled codes come from the deployment's own whitelist, --disable=all
# FIRST so ONLY that whitelist runs - otherwise the rcfile's broad defaults
# stack on top and the gate reports findings the deployment's CI never enforces.
# Order matters: --disable=all THEN --enable=<whitelist>.
[[ -n "$ENABLE_FROM_MODULE" ]] && PYLINT_ARGS+=(--disable=all --enable="$ENABLE_FROM_MODULE")

set +e
OUTPUT="$("$PYLINT_BIN" "${PYLINT_ARGS[@]}" "${PY_FILES[@]}" 2>&1)"
PYLINT_RC=$?
set -e

echo
echo "--- pylint-odoo findings ---"
# pylint exit code is a bitmask: 1 fatal, 2 error, 4 warning, 8 refactor,
# 16 convention, 32 usage error. 0 = clean.
if [[ $PYLINT_RC -eq 0 ]]; then
    _ok "no pylint-odoo findings"
elif (( PYLINT_RC & 32 )) || (( PYLINT_RC & 1 )); then
    # Tool/config problem (e.g. unknown enabled symbol on this version) - surface,
    # do NOT hard-fail the developer's change on our own misconfiguration.
    echo "$OUTPUT"
    _warn "pylint usage/fatal error (rc=$PYLINT_RC) - config/toolchain issue, not your code (graceful)"
else
    # Findings from the enabled set. Split off unknown-option-value (W0012, or the
    # legacy bad-option-value): it fires when our derived whitelist names a message
    # THIS pylint-odoo build doesn't know - version drift between the deployment's
    # pinned linter and ours, i.e. OUR config, not the developer's code. WARN, never
    # BLOCK (match on the stable symbol, not the version-drifting numeric id).
    # Everything else is a real finding and BLOCKs (matches CI).
    _ALL_FIND=$(printf '%s\n' "$OUTPUT" | grep -E '^[^ ].*: \[[A-Z][0-9]+\(' || true)
    _DRIFT=$(printf '%s\n' "$_ALL_FIND" | grep -E '\((unknown-option-value|bad-option-value)\)' || true)
    _REAL=$(printf '%s\n' "$_ALL_FIND" | grep -vE '\((unknown-option-value|bad-option-value)\)' || true)
    if [[ -n "$_DRIFT" ]]; then
        printf '%s\n' "$_DRIFT" | while IFS= read -r line; do
            [[ -n "$line" ]] && echo "  [WARN ] $line"
        done
        _DRIFT_N=$(printf '%s\n' "$_DRIFT" | grep -c . || true)
        WARN_COUNT=$(( WARN_COUNT + ${_DRIFT_N:-0} ))
    fi
    if [[ -n "$_REAL" ]]; then
        printf '%s\n' "$_REAL" | while IFS= read -r line; do
            [[ -n "$line" ]] && echo "  [BLOCK] $line"
        done
        _REAL_N=$(printf '%s\n' "$_REAL" | grep -c . || true)
        BLOCK_COUNT=$(( BLOCK_COUNT + ${_REAL_N:-0} ))
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo " Summary"
echo "============================================================"
echo "  BLOCK issues : $BLOCK_COUNT"
echo "  WARN  issues : $WARN_COUNT"
if [[ $BLOCK_COUNT -gt 0 ]]; then
    echo
    echo "  RESULT: FAILED ($BLOCK_COUNT pylint-odoo finding(s) - fix before push; matches CI)"
    exit 1
fi
echo
if [[ $WARN_COUNT -gt 0 ]]; then
    echo "  RESULT: PASS (with $WARN_COUNT warning(s) - review recommended)"
else
    echo "  RESULT: PASS (clean)"
fi
exit 0
