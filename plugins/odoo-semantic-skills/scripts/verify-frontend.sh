#!/usr/bin/env bash
# verify-frontend.sh — 3-tier OWL/JS/SCSS quality gate for Odoo frontend files.
#
# TIERS (each independently degrades; only BLOCK-tier failures cause non-zero exit):
#
#   Tier 1 — FORMAT/LINT (toolchain-dependent, graceful degradation)
#     Python (.py):  run `ruff check <files>` if ruff is available.
#                    Line-length read from target repo's pyproject.toml / ruff.toml (never hardcoded).
#                    Never runs `ruff format` (version-sensitive, mutating).
#                    If ruff absent: soft-warn, continue.
#     JavaScript (.js): config resolution order:
#       (1) repo-committed root .eslintrc* / .prettierrc* + local bin  → run HARD
#       (2) <odoo_checkout>/addons/web/tooling/_eslintrc.json present  → use it HARD if prettier avail
#       (3) shipped fallback ${CLAUDE_PLUGIN_ROOT}/scripts/odoo-prettierrc.json → HARD if prettier avail
#       (4) no config anywhere → SOFT warn, do NOT block
#
#   Tier 2 — STATIC OWL/SCSS (grep/ERE, always runs, zero toolchain needed)
#     Applies ${CLAUDE_PLUGIN_ROOT}/scripts/rules/owl-pitfalls.txt over .js/.xml/.scss files.
#     BLOCK on classes 1/3/6.  WARN on 2/4/5.
#
#   Tier 3 — RUNTIME SMOKE (only when a live Odoo instance is configured)
#     Skipped silently when not configured. Never blocks when absent.
#
# USAGE:
#   verify-frontend.sh [file ...]
#   verify-frontend.sh             (defaults to `git diff --name-only HEAD`)
#
# ENV OVERRIDES:
#   CLAUDE_PLUGIN_ROOT    plugin root (required for rules/ and fallback config)
#   ODOO_GIT_BASE         where Odoo core checkouts live (default: ~/git)
#   ODOO_INSTANCE_URL     live instance base URL for Tier-3 smoke (e.g. http://localhost:8069)
#   VERIFY_FRONTEND_BASE  git diff base ref (default: HEAD)
#
# EXIT CODE:
#   0  all tiers passed (or degraded gracefully to warn-only)
#   1  at least one BLOCK-tier failure

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve CLAUDE_PLUGIN_ROOT
# ---------------------------------------------------------------------------
if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    # Best-effort: derive from script location when env var is absent.
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CLAUDE_PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
fi

RULES_FILE="${CLAUDE_PLUGIN_ROOT}/scripts/rules/owl-pitfalls.txt"
FALLBACK_PRETTIERRC="${CLAUDE_PLUGIN_ROOT}/scripts/odoo-prettierrc.json"
ODOO_GIT_BASE="${ODOO_GIT_BASE:-$HOME/git}"
VERIFY_BASE="${VERIFY_FRONTEND_BASE:-HEAD}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_have() { command -v "$1" >/dev/null 2>&1; }

# Counters
BLOCK_COUNT=0
WARN_COUNT=0

_block() { echo "  [BLOCK] $*"; BLOCK_COUNT=$((BLOCK_COUNT + 1)); }
_warn()  { echo "  [WARN ] $*"; WARN_COUNT=$((WARN_COUNT + 1)); }
_ok()    { echo "  [  ok ] $*"; }
_info()  { echo "  [info ] $*"; }
_skip()  { echo "  [skip ] $*"; }

# ---------------------------------------------------------------------------
# Collect file list
# ---------------------------------------------------------------------------
if [[ $# -gt 0 ]]; then
    FILES=("$@")
else
    # Default: files changed relative to base.
    # `mapfile` is bash 4+; read in a loop instead so this runs on macOS bash 3.2.
    FILES=()
    while IFS= read -r _line; do
        FILES+=("$_line")
    done < <(git diff --name-only "${VERIFY_BASE}" 2>/dev/null || true)
fi

# Filter to existing files only (ignore deletions)
EXISTING_FILES=()
for f in "${FILES[@]:-}"; do
    [[ -n "$f" && -f "$f" ]] && EXISTING_FILES+=("$f")
done

if [[ ${#EXISTING_FILES[@]} -eq 0 ]]; then
    echo "verify-frontend: no files to check."
    exit 0
fi

echo "============================================================"
echo " verify-frontend — ${#EXISTING_FILES[@]} file(s)"
echo "============================================================"

# ---------------------------------------------------------------------------
# Split by extension
# ---------------------------------------------------------------------------
PY_FILES=()
JS_FILES=()
SCSS_FILES=()
TEMPLATE_FILES=()   # .xml / .html (OWL templates)

for f in "${EXISTING_FILES[@]}"; do
    case "$f" in
        *.py)                PY_FILES+=("$f") ;;
        *.js)                JS_FILES+=("$f") ;;
        *.scss|*.css)        SCSS_FILES+=("$f") ;;
        *.xml|*.html)        TEMPLATE_FILES+=("$f") ;;
    esac
done

# ===========================================================================
# TIER 1 — FORMAT / LINT
# ===========================================================================
echo
echo "--- Tier 1: Format / Lint ---"

# ---------------------------------------------------------------------------
# T1-A: Python — ruff check (never ruff format)
# ---------------------------------------------------------------------------
if [[ ${#PY_FILES[@]} -gt 0 ]]; then
    echo
    echo "  Python files (${#PY_FILES[@]}):"
    if _have ruff; then
        # Detect line-length from the nearest pyproject.toml or ruff.toml
        RUFF_EXTRA_ARGS=()
        _PYPROJECT=""
        # Walk up from the first Python file's location to find pyproject.toml
        _SEARCH_DIR="$(dirname "${PY_FILES[0]}")"
        while [[ "$_SEARCH_DIR" != "/" && "$_SEARCH_DIR" != "." ]]; do
            if [[ -f "$_SEARCH_DIR/pyproject.toml" ]]; then
                _PYPROJECT="$_SEARCH_DIR/pyproject.toml"
                break
            elif [[ -f "$_SEARCH_DIR/ruff.toml" ]]; then
                _PYPROJECT="$_SEARCH_DIR/ruff.toml"
                break
            fi
            _SEARCH_DIR="$(dirname "$_SEARCH_DIR")"
        done
        # Also check repo root (pwd) as fallback
        if [[ -z "$_PYPROJECT" ]]; then
            if [[ -f "pyproject.toml" ]]; then
                _PYPROJECT="pyproject.toml"
            elif [[ -f "ruff.toml" ]]; then
                _PYPROJECT="ruff.toml"
            fi
        fi

        if [[ -n "$_PYPROJECT" ]]; then
            _LINE_LEN="$(python3 - "$_PYPROJECT" <<'PY' 2>/dev/null || true
import sys
try:
    content = open(sys.argv[1]).read()
    # Try TOML parsing via stdlib (Python 3.11+) first, then regex fallback
    try:
        import tomllib
        with open(sys.argv[1], "rb") as fh:
            data = tomllib.load(fh)
        ll = (data.get("tool", {}).get("ruff", {}).get("line-length")
              or data.get("tool", {}).get("ruff", {}).get("format", {}).get("line-length")
              or data.get("line-length"))
        if ll:
            print(str(ll))
    except (ImportError, AttributeError):
        import re
        m = re.search(r'line-length\s*=\s*(\d+)', content)
        if m:
            print(m.group(1))
except Exception:
    pass
PY
)"
            if [[ -n "$_LINE_LEN" ]]; then
                _info "ruff: reading line-length=$_LINE_LEN from $_PYPROJECT"
                RUFF_EXTRA_ARGS=("--line-length" "$_LINE_LEN")
            else
                _info "ruff: no line-length in $_PYPROJECT — using ruff default"
            fi
        else
            _info "ruff: no pyproject.toml/ruff.toml found — using ruff default"
        fi

        # Run ruff check (read-only; never ruff format).
        # Guard the array expansion: an empty array under `set -u` aborts on bash 3.2.
        if ruff check ${RUFF_EXTRA_ARGS[@]+"${RUFF_EXTRA_ARGS[@]}"} "${PY_FILES[@]}" 2>&1; then
            _ok "ruff check passed"
        else
            _block "ruff check failed (see output above)"
        fi
    else
        _warn "ruff not found — skipping Python lint (install ruff to enable HARD check)"
    fi
fi

# ---------------------------------------------------------------------------
# T1-B: JavaScript — config-resolution-ordered prettier --check
# ---------------------------------------------------------------------------
if [[ ${#JS_FILES[@]} -gt 0 ]]; then
    echo
    echo "  JavaScript files (${#JS_FILES[@]}):"

    JS_CONFIG=""
    JS_CONFIG_SRC=""
    JS_HARD=false

    # (1) Repo-committed root .prettierrc* / .eslintrc*
    for _rc in .prettierrc .prettierrc.json .prettierrc.js .prettierrc.yaml .prettierrc.yml prettier.config.js; do
        if [[ -f "$_rc" ]]; then
            JS_CONFIG="$_rc"
            JS_CONFIG_SRC="repo-committed root $_rc"
            JS_HARD=true
            break
        fi
    done

    # (2) Odoo checkout web/tooling/_eslintrc.json (has embedded prettier config since v17)
    #     or _prettierrc.json (v15-v16)
    if [[ -z "$JS_CONFIG" ]]; then
        while IFS= read -r _odoo_dir; do
            for _tooling_cfg in \
                "$_odoo_dir/addons/web/tooling/_prettierrc.json" \
                "$_odoo_dir/addons/web/tooling/_eslintrc.json"; do
                if [[ -f "$_tooling_cfg" ]]; then
                    JS_CONFIG="$_tooling_cfg"
                    JS_CONFIG_SRC="odoo checkout tooling: $_tooling_cfg"
                    JS_HARD=true
                    break 2
                fi
            done
        done < <(find "$ODOO_GIT_BASE" -maxdepth 2 -name "odoo-bin" 2>/dev/null \
                 | xargs -I{} dirname {} 2>/dev/null | head -5)
    fi

    # (3) Shipped fallback
    if [[ -z "$JS_CONFIG" && -f "$FALLBACK_PRETTIERRC" ]]; then
        JS_CONFIG="$FALLBACK_PRETTIERRC"
        JS_CONFIG_SRC="shipped fallback odoo-prettierrc.json (tier-3 fallback)"
        JS_HARD=true
    fi

    if [[ -n "$JS_CONFIG" ]]; then
        _info "JS config: $JS_CONFIG_SRC"
        if _have prettier; then
            # prettier --config only works with its own config format (not .eslintrc)
            # If the config is an eslintrc, extract the prettier/prettier rule values
            # and write a temp config, then clean up.
            _PRETTIER_CONFIG_ARG="$JS_CONFIG"
            _TEMP_PRETTIER=""
            if [[ "$JS_CONFIG" == *"_eslintrc"* ]] || [[ "$JS_CONFIG" == *".eslintrc"* ]]; then
                # Extract prettier options from eslintrc prettier/prettier rule
                _TEMP_PRETTIER="$(mktemp /tmp/odoo-prettierrc-XXXXXX.json)"
                python3 - "$JS_CONFIG" "$_TEMP_PRETTIER" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    rules = data.get("rules", {})
    pp = rules.get("prettier/prettier", [])
    opts = {}
    if isinstance(pp, list) and len(pp) >= 2 and isinstance(pp[1], dict):
        opts = pp[1]
    if not opts:
        # fallback canonical values
        opts = {"tabWidth": 4, "semi": True, "singleQuote": False, "printWidth": 100, "endOfLine": "auto"}
    with open(sys.argv[2], "w") as fh:
        json.dump(opts, fh, indent=2)
except Exception as e:
    # write fallback
    with open(sys.argv[2], "w") as fh:
        json.dump({"tabWidth": 4, "semi": True, "singleQuote": False, "printWidth": 100, "endOfLine": "auto"}, fh)
PY
                _PRETTIER_CONFIG_ARG="$_TEMP_PRETTIER"
            fi

            if prettier --config "$_PRETTIER_CONFIG_ARG" --check "${JS_FILES[@]}" 2>&1; then
                _ok "prettier --check passed"
            else
                if [[ "$JS_HARD" == "true" ]]; then
                    _block "prettier --check failed (HARD: config $JS_CONFIG_SRC)"
                else
                    _warn "prettier --check failed (SOFT: config $JS_CONFIG_SRC)"
                fi
            fi

            [[ -n "$_TEMP_PRETTIER" && -f "$_TEMP_PRETTIER" ]] && rm -f "$_TEMP_PRETTIER"
        else
            if [[ "$JS_HARD" == "true" ]]; then
                _warn "prettier not found — skipping JS format check (install prettier to enable HARD check with $JS_CONFIG_SRC)"
            else
                _warn "prettier not found — skipping JS format check"
            fi
        fi
    else
        # (4) No config available — soft warn only
        _warn "no JS prettier config found (repo root / Odoo tooling / fallback) — skipping JS format check"
    fi
fi

# ===========================================================================
# TIER 2 — STATIC OWL/SCSS (grep/ERE, always runs)
# ===========================================================================
echo
echo "--- Tier 2: Static OWL/SCSS (always runs) ---"

if [[ ! -f "$RULES_FILE" ]]; then
    _warn "rules file not found: $RULES_FILE — skipping Tier 2"
else
    # Combine files by applicability
    OWL_FILES=("${JS_FILES[@]:-}" "${TEMPLATE_FILES[@]:-}")
    # .scss scanned for classes 4 and 5 only (filter in rule-apply loop below)

    _apply_rule_to_file() {
        local pattern="$1"
        local severity="$2"
        local message="$3"
        local file="$4"
        local scss_only="${5:-false}"

        # scss_only rules only apply to .scss/.css files
        if [[ "$scss_only" == "true" ]]; then
            case "$file" in *.scss|*.css) ;; *) return 0 ;; esac
        fi

        local matched_lines

        if [[ "$message" == "class-1:"* ]]; then
            # Class-1: two-stage check for bare arrow free-identifier.
            # Stage 1: match the arrow pattern.
            # Stage 2: exclude lines where this./props. immediately precedes the call
            #          (the grep -v filter keeps only truly bare-ident cases).
            # Also skip XML comment lines (<!-- ... -->).
            matched_lines=$(grep -nE "$pattern" "$file" 2>/dev/null \
                | grep -vE 't-on[-a-zA-Z.]*=["\'"'"'][(][^)]*[)] =>[[:space:]]*(this|props)\.' \
                | grep -vE '^[0-9]+:[[:space:]]*<!--' \
                || true)

        elif [[ "$message" == "class-2:"* ]]; then
            # Class-2: useService("ui") warn ONLY when NOT wrapped in useState() on same line.
            # If the line also contains useState(, it is the correct pattern — skip it.
            matched_lines=$(grep -nE "$pattern" "$file" 2>/dev/null \
                | grep -vE 'useState[(]' \
                | grep -vE '^[0-9]+:[[:space:]]*//' \
                || true)

        elif [[ "$message" == "class-3:"* ]]; then
            # Class-3: raw contenteditable in an OWL *template*.
            # Only applies to template files (.xml/.html) — a bare `contenteditable=`
            # in .js is almost always a CSS/attribute SELECTOR string
            # (e.g. querySelector("[contenteditable=true]")), which is legitimate and
            # must NOT block. Restricting to templates removes that false positive.
            case "$file" in
                *.xml|*.html) ;;
                *) return 0 ;;
            esac
            # Anchor on the template-attribute form: contenteditable= followed by a
            # quote (contenteditable="true" / ='true'), not an unquoted selector token.
            # Skip XML/HTML comment lines.
            matched_lines=$(grep -nE "$pattern" "$file" 2>/dev/null \
                | grep -vE '^[0-9]+:[[:space:]]*<!--' \
                || true)

        elif [[ "$message" == "class-6:"* ]]; then
            # Class-6: t-set-slot="body" — skip XML comment lines.
            matched_lines=$(grep -nE "$pattern" "$file" 2>/dev/null \
                | grep -vE '^[0-9]+:[[:space:]]*<!--' \
                || true)

        else
            matched_lines=$(grep -nE "$pattern" "$file" 2>/dev/null || true)
        fi

        [[ -z "$matched_lines" ]] && return 0

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            local lineno="${line%%:*}"
            local content="${line#*:}"
            if [[ "$severity" == "BLOCK" ]]; then
                _block "$file:$lineno — $message"
                echo "         matched: $content"
            else
                _warn "$file:$lineno — $message"
                echo "         matched: $content"
            fi
        done <<< "$matched_lines"
    }

    # Parse rules file and apply each rule
    ALL_SCAN_FILES=("${OWL_FILES[@]:-}" "${SCSS_FILES[@]:-}")
    if [[ ${#ALL_SCAN_FILES[@]} -eq 0 ]]; then
        _skip "no .js/.xml/.html/.scss files — Tier 2 skipped"
    else
        while IFS='|' read -r pattern severity message || [[ -n "$pattern" ]]; do
            # Skip comments and blank lines
            [[ -z "${pattern// }" || "${pattern:0:1}" == "#" ]] && continue

            # Determine if this is a SCSS-only rule (classes 4 and 5)
            local_scss_only=false
            if [[ "$message" == "class-4:"* || "$message" == "class-5:"* ]]; then
                local_scss_only=true
            fi

            # Apply to each file
            for scan_file in "${ALL_SCAN_FILES[@]:-}"; do
                [[ -z "$scan_file" || ! -f "$scan_file" ]] && continue
                # SCSS-only rules: skip non-scss files
                if [[ "$local_scss_only" == "true" ]]; then
                    case "$scan_file" in *.scss|*.css) ;; *) continue ;; esac
                fi
                # Non-SCSS rules: skip scss files (Tier-2 classes 1/2/3/6 are JS/XML only)
                if [[ "$local_scss_only" == "false" ]]; then
                    case "$scan_file" in *.scss|*.css) continue ;; esac
                fi
                _apply_rule_to_file "$pattern" "$severity" "$message" "$scan_file" "$local_scss_only"
            done
        done < "$RULES_FILE"

        # Report clean if no issues from Tier 2
        if [[ $BLOCK_COUNT -eq 0 && $WARN_COUNT -eq 0 ]]; then
            _ok "Tier 2 static scan: no issues"
        fi
    fi
fi

# ===========================================================================
# TIER 3 — RUNTIME SMOKE (optional)
# ===========================================================================
echo
echo "--- Tier 3: Runtime Smoke ---"
if [[ -z "${ODOO_INSTANCE_URL:-}" ]]; then
    _skip "ODOO_INSTANCE_URL not set — runtime smoke skipped (not a blocking condition)"
else
    _info "ODOO_INSTANCE_URL=$ODOO_INSTANCE_URL — checking /web/login reachability"
    if _have curl; then
        if curl -sf -o /dev/null --max-time 10 "${ODOO_INSTANCE_URL}/web/login" 2>/dev/null; then
            _ok "Instance reachable at ${ODOO_INSTANCE_URL}/web/login"
        else
            _warn "Instance not responding at ${ODOO_INSTANCE_URL}/web/login (non-blocking)"
        fi
    else
        _skip "curl not available — skipping runtime smoke"
    fi
fi

# ===========================================================================
# TIER 4 — BRAND FIDELITY (optional, brand-agnostic, static)
# ===========================================================================
# Runs ONLY when the consumer declares `brand_tokens_source` in .odoo-ai/context.md
# (a JSON map of token -> color, e.g. {"--primary": "#1E88E5", ...}). The plugin
# ships NO brand of its own — the map is discovered from the consumer environment,
# mirroring how verify-backend.sh derives ENABLED_CODES from the deployment's
# quality module. No browser here: this is the STATIC half (hardcoded-hex vs brand
# palette). The RUNTIME half (getComputedStyle :root ΔE-diff) is the ui-reviewer's
# Step 4b. Both share scripts/lib/color_delta.py. WARN-only (never blocks).
echo
echo "--- Tier 4: Brand fidelity (optional) ---"
_BRAND_SRC=""
if [[ -f ".odoo-ai/context.md" ]]; then
    _BRAND_SRC="$(grep -iE '^[-*][[:space:]]*\**brand_tokens_source' .odoo-ai/context.md 2>/dev/null \
        | head -1 | sed -E 's/.*brand_tokens_source\**[[:space:]]*:?[[:space:]]*//' | tr -d '`' | xargs 2>/dev/null || true)"
fi
COLOR_DELTA="${CLAUDE_PLUGIN_ROOT}/scripts/lib/color_delta.py"
_BRAND_NEAR="${BRAND_NEAR_DELTA:-3.0}"   # hardcoded hex this close to a brand token => should use the var
if [[ -z "$_BRAND_SRC" ]]; then
    _skip "no brand_tokens_source in .odoo-ai/context.md — brand fidelity skipped (not a blocking condition)"
elif [[ ! -f "$_BRAND_SRC" ]]; then
    _warn "brand_tokens_source declared but file not found: $_BRAND_SRC"
elif ! _have python3 || [[ ! -f "$COLOR_DELTA" ]]; then
    _skip "python3 / color_delta.py unavailable — brand fidelity skipped"
elif [[ ${#SCSS_FILES[@]} -eq 0 ]]; then
    _skip "no .scss/.css files changed — brand fidelity skipped"
else
    _info "brand map: $_BRAND_SRC (near-token ΔE threshold $_BRAND_NEAR)"
    _BRAND_WARN_BEFORE=$WARN_COUNT
    # Iterate changed SCSS lines with a hardcoded hex; ΔE-compare to each brand color.
    for sf in "${SCSS_FILES[@]:-}"; do
        [[ -f "$sf" ]] || continue
        while IFS= read -r hit; do
            [[ -z "$hit" ]] && continue
            lineno="${hit%%:*}"
            hex="$(printf '%s' "$hit" | grep -oiE '#[0-9a-f]{6}|#[0-9a-f]{3}' | head -1)"
            [[ -z "$hex" ]] && continue
            # Find the nearest brand token to this hardcoded hex.
            near="$(python3 - "$COLOR_DELTA" "$_BRAND_SRC" "$hex" "$_BRAND_NEAR" <<'PY' 2>/dev/null || true
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("cd", sys.argv[1])
cd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cd)
src, hexv, thr = sys.argv[2], sys.argv[3], float(sys.argv[4])
try:
    tokens = json.load(open(src))
except Exception:
    sys.exit(0)
best = None
for name, val in tokens.items():
    if cd.parse_color(str(val)) is None:
        continue
    de = cd.delta_e(str(val), hexv)
    if de is None:
        continue
    if best is None or de < best[1]:
        best = (name, de)
if best and best[1] <= thr:
    print(f"{best[0]}|{best[1]:.2f}")
PY
)"
            if [[ -n "$near" ]]; then
                tok="${near%%|*}"; de="${near#*|}"
                _warn "$sf:$lineno — hardcoded hex $hex ≈ brand token $tok (ΔE $de); reference the token var instead of inlining the brand color"
            fi
        done < <(grep -niE '#[0-9a-f]{6}|#[0-9a-f]{3}' "$sf" 2>/dev/null || true)
    done
    [[ $WARN_COUNT -eq $_BRAND_WARN_BEFORE ]] && _ok "Tier 4 brand: no near-token hardcoded brand colors"
fi

# ===========================================================================
# Summary
# ===========================================================================
echo
echo "============================================================"
echo " Summary"
echo "============================================================"
echo "  BLOCK issues : $BLOCK_COUNT"
echo "  WARN  issues : $WARN_COUNT"

if [[ $BLOCK_COUNT -gt 0 ]]; then
    echo
    echo "  RESULT: FAILED ($BLOCK_COUNT blocking issue(s) — fix before proceeding)"
    exit 1
else
    if [[ $WARN_COUNT -gt 0 ]]; then
        echo
        echo "  RESULT: PASS (with $WARN_COUNT warning(s) — review recommended)"
    else
        echo
        echo "  RESULT: PASS (clean)"
    fi
    exit 0
fi
