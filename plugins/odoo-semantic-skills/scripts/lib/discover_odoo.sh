#!/usr/bin/env bash
# discover_odoo.sh - Discover Odoo addon repos on this machine.
#
# Scans <base> (default: ${ODOO_GIT_BASE:-$HOME/git}) for Odoo addon repos and
# any Odoo core installation. Outputs a TSV to stdout that callers (setup
# scripts or AI agents) can use to suggest an addons-path configuration.
#
# OUTPUT FORMAT (TSV, one row per repo):
#   role<TAB>version<TAB>path<TAB>has_manifest
#
# Roles (guessed from directory name heuristics):
#   core       - The Odoo core repo (has odoo-bin + odoo/release.py)
#   enterprise - Odoo Enterprise addons (dir name contains "enterprise")
#   oca        - OCA community addons (dir name contains oca/server-tools etc.)
#   theme      - Theming / branding addons (dir name contains theme/branding)
#   custom     - Everything else (first in addons-path priority)
#
# A leading comment block explains the recommended addons-path order.
# Roles are heuristic ("guessed") - review before using.
#
# USAGE:
#   bash discover_odoo.sh [--base <dir>] [--project <dir>]
#
# OPTIONS:
#   --base <dir>     Root dir to scan for git repos. Default: ${ODOO_GIT_BASE:-$HOME/git}
#   --project <dir>  Project root (currently unused, reserved for future use). Default: $PWD
#
# EXIT CODES:
#   0  Always (warnings go to stderr; caller decides what to do with empty output)
#
# EXAMPLES:
#   bash discover_odoo.sh
#   bash discover_odoo.sh --base /opt/odoo
#   ODOO_GIT_BASE=/srv/odoo bash discover_odoo.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
BASE_DIR="${ODOO_GIT_BASE:-$HOME/git}"
PROJECT_DIR="${PWD}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --base)
            BASE_DIR="$2"
            shift 2
            ;;
        --project)
            PROJECT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Validate base directory
# ---------------------------------------------------------------------------
if [[ ! -d "$BASE_DIR" ]]; then
    echo "warning: base directory does not exist: $BASE_DIR" >&2
    # Exit 0 with empty output so callers can gracefully fall back to asking user
    exit 0
fi

# ---------------------------------------------------------------------------
# Helper: classify a directory into a role (heuristic)
# ---------------------------------------------------------------------------
_classify_role() {
    local dir_name
    dir_name="$(basename "$1" | tr '[:upper:]' '[:lower:]')"
    # Patterns checked in priority order; first match wins
    if [[ "$dir_name" == *enterprise* ]]; then
        echo "enterprise"
    elif [[ "$dir_name" == *oca* ]] \
      || [[ "$dir_name" == *server-tools* ]] \
      || [[ "$dir_name" == *server-ux* ]] \
      || [[ "$dir_name" == *web-* ]] \
      || [[ "$dir_name" == *addons-web* ]]; then
        echo "oca"
    elif [[ "$dir_name" == *theme* ]] || [[ "$dir_name" == *branding* ]]; then
        echo "theme"
    else
        echo "custom"
    fi
}

# ---------------------------------------------------------------------------
# Helper: extract Odoo version from release.py
# Returns empty string on failure (non-fatal).
# ---------------------------------------------------------------------------
_odoo_version_from_release() {
    local release_py="$1"
    # Try parsing version_info tuple: version_info = (17, 0, ...)
    python3 - "$release_py" <<'PY' 2>/dev/null || true
import ast, sys, re
try:
    src = open(sys.argv[1]).read()
    # Look for version_info = (major, minor, ...)
    m = re.search(r'version_info\s*=\s*\(([^)]+)\)', src)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        major = parts[0].strip("'\"")
        minor = parts[1].strip("'\"") if len(parts) > 1 else '0'
        print(f"{major}.{minor}")
        sys.exit(0)
    # Fallback: look for series = '17.0'
    m2 = re.search(r'series\s*=\s*[\'"]([^\'"]+)[\'"]', src)
    if m2:
        print(m2.group(1))
        sys.exit(0)
except Exception:
    pass
PY
}

# ---------------------------------------------------------------------------
# Collect all data first, then print header + sorted rows
# ---------------------------------------------------------------------------
declare -A SEEN_REPOS   # track repo roots to avoid duplicates
declare -A REPO_ROLE
declare -A REPO_VERSION
declare -A REPO_HAS_MANIFEST

# ---------------------------------------------------------------------------
# Phase 1: Detect Odoo core repos (has odoo-bin + odoo/release.py)
# ---------------------------------------------------------------------------
while IFS= read -r odoobin; do
    repo_root="$(dirname "$odoobin")"
    release_py="$repo_root/odoo/release.py"
    [[ -f "$release_py" ]] || continue

    if [[ -z "${SEEN_REPOS[$repo_root]+set}" ]]; then
        SEEN_REPOS[$repo_root]=1
        version="$(_odoo_version_from_release "$release_py")"
        REPO_ROLE[$repo_root]="core"
        REPO_VERSION[$repo_root]="${version:-unknown}"
        REPO_HAS_MANIFEST[$repo_root]="yes"
    fi
done < <(find "$BASE_DIR" -maxdepth 3 -name "odoo-bin" 2>/dev/null)

# ---------------------------------------------------------------------------
# Phase 2: Discover addon repos via __manifest__.py
# ---------------------------------------------------------------------------
while IFS= read -r manifest; do
    # module dir is the parent of __manifest__.py
    module_dir="$(dirname "$manifest")"
    # repo root is one level above the module dir
    repo_root="$(dirname "$module_dir")"

    # Skip Odoo core repos already classified in Phase 1
    [[ -n "${SEEN_REPOS[$repo_root]+set}" ]] && continue

    SEEN_REPOS[$repo_root]=1
    role="$(_classify_role "$repo_root")"
    REPO_ROLE[$repo_root]="$role"
    REPO_HAS_MANIFEST[$repo_root]="yes"

    # Try to infer version from __manifest__.py (best-effort, first module wins)
    if [[ -z "${REPO_VERSION[$repo_root]+set}" ]]; then
        ver="$(python3 - "$manifest" <<'PY' 2>/dev/null || true
import ast, sys
try:
    data = ast.literal_eval(open(sys.argv[1]).read())
    v = data.get('version', '')
    # version field is often "17.0.x.y.z"; extract series
    parts = str(v).split('.')
    if len(parts) >= 2 and parts[0].isdigit():
        print(f"{parts[0]}.{parts[1]}")
except Exception:
    pass
PY
)"
        REPO_VERSION[$repo_root]="${ver:-unknown}"
    fi
done < <(find "$BASE_DIR" -maxdepth 4 -name "__manifest__.py" 2>/dev/null)

# ---------------------------------------------------------------------------
# Output: print comment header, then TSV rows (sorted by role priority)
# ---------------------------------------------------------------------------
# Recommended addons-path order: custom first (highest priority), core last
echo "# Discovered Odoo repos (heuristic role; verify before using)"
echo "# Recommended addons-path order: custom -> theme -> oca -> enterprise -> core"
echo "# Columns: role<TAB>version<TAB>path<TAB>has_manifest"
echo "# role is 'guessed' from directory name - review before committing to config"

# Emit in role-priority order so caller sees them already sorted for addons-path
for priority_role in custom theme oca enterprise core; do
    for repo_root in "${!REPO_ROLE[@]}"; do
        [[ "${REPO_ROLE[$repo_root]}" == "$priority_role" ]] || continue
        ver="${REPO_VERSION[$repo_root]:-unknown}"
        # printf (not echo -e) so a path containing backslashes is not mangled by
        # escape interpretation, keeping the TSV columns intact.
        printf '%s\t%s\t%s\t%s\n' "$priority_role" "$ver" "$repo_root" "${REPO_HAS_MANIFEST[$repo_root]:-no}"
    done
done
