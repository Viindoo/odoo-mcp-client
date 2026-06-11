#!/usr/bin/env bash
# 40-instance-profile.sh - Declare local Odoo instance(s) for visual setup.
#
# Runs discover_odoo.sh to find Odoo core + addon repos on the machine, prints
# the discovered TSV for the user to confirm the addons-path ordering, and
# persists the result to `.odoo-ai/instances.toml` at the project root. Also
# ensures `.odoo-ai/` is gitignored (same no-op grep pattern as odoo-onboarding).
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if .odoo-ai/instances.toml exists AND declares >=1 version
#              table; exit 1 otherwise (apply needed).
#   apply      Discover -> show TSV -> write instances.toml -> ensure gitignore.
#
# HARD RULES:
#   - NEVER write a password into instances.toml. Only host / user / db name /
#     port go in the file; the password belongs in an env var or keychain.
#   - Writes ONLY .odoo-ai/instances.toml and one .gitignore line. Touches no
#     Odoo source.
#   - Backs up before modifying (via the lib); idempotent on the gitignore line.
#
# CONFIG:
#   ODOO_AI_DIR    project context dir   ${ODOO_AI_DIR:-$PWD/.odoo-ai}
#   ODOO_GIT_BASE  scan root for repos   (consumed by discover_odoo.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"
MATRIX_JSON="$SCRIPT_DIR/../lib/odoo-python-matrix.json"

# Look up the recommended Python version for an Odoo series (e.g. "17.0").
# Prints the recommended version or nothing. Data-driven from MATRIX_JSON.
_suggested_python() {
    [[ -f "$MATRIX_JSON" ]] || return 0
    python3 - "$MATRIX_JSON" "$1" <<'PY' 2>/dev/null || true
import json, sys
try:
    m = json.load(open(sys.argv[1]))
    e = m.get("odoo_python_matrix", {}).get(sys.argv[2])
    if e and e.get("recommended"):
        print(e["recommended"])
except Exception:
    pass
PY
}
DISCOVER="$SCRIPT_DIR/../lib/discover_odoo.sh"

ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"
INSTANCES_TOML="$ODOO_AI_DIR/instances.toml"
GITIGNORE="$PWD/.gitignore"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Discover local Odoo repos and declare instance profile(s) in .odoo-ai/instances.toml"
}

# ---------------------------------------------------------------------------
# check - true when instances.toml exists with >=1 [[instance]] item
# ---------------------------------------------------------------------------
cmd_check() {
    [[ -f "$INSTANCES_TOML" ]] || return 1
    grep -qE '^\[\[instance\]\]' "$INSTANCES_TOML"
}

# ---------------------------------------------------------------------------
# gitignore - idempotent append of `.odoo-ai/` (mirrors odoo-onboarding step 8)
# ---------------------------------------------------------------------------
_ensure_gitignore() {
    if [[ -f "$GITIGNORE" ]]; then
        if grep -qxF '.odoo-ai/' "$GITIGNORE"; then
            echo "  .gitignore already excludes .odoo-ai/ - no change"
            return 0
        fi
        # Append with a guaranteed leading newline if the file lacks a trailing one.
        [[ -n "$(tail -c1 "$GITIGNORE" 2>/dev/null)" ]] && printf '\n' >>"$GITIGNORE"
        printf '.odoo-ai/\n' >>"$GITIGNORE"
        echo "  appended .odoo-ai/ to .gitignore"
    else
        printf '.odoo-ai/\n' >"$GITIGNORE"
        echo "  created .gitignore with .odoo-ai/"
    fi
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    if [[ ! -f "$LIB" || ! -f "$DISCOVER" ]]; then
        echo "x lib/discover script missing under $SCRIPT_DIR/../lib - install the plugin fully." >&2
        return 1
    fi

    echo "Discovering Odoo repos on this machine..."
    local tsv
    tsv="$(bash "$DISCOVER" 2>/dev/null || true)"

    echo "----------------------------------------------------------------------"
    if [[ -z "$tsv" ]] || ! printf '%s' "$tsv" | grep -qvE '^#'; then
        echo "  (no Odoo repos auto-discovered under \${ODOO_GIT_BASE:-\$HOME/git})"
        echo "  The instance profile will be written with placeholders for you/the"
        echo "  AI agent to fill in (addons_path, version)."
    else
        printf '%s\n' "$tsv"
    fi
    echo "----------------------------------------------------------------------"
    echo "Review the role -> addons-path ordering above (custom first, core last)."

    mkdir -p "$ODOO_AI_DIR"

    # Derive distinct versions from the discovered TSV (skip 'unknown'/comments).
    local versions
    versions="$(printf '%s\n' "$tsv" \
        | grep -vE '^#' \
        | awk -F'\t' 'NF>=2 && $2!="unknown" && $2!="" {print $2}' \
        | sort -u || true)"

    # If nothing was discovered, do NOT write a junk placeholder instance.
    # Guide the user to clone a repo / point ODOO_GIT_BASE and re-run instead.
    if [[ -z "$versions" ]]; then
        echo "  No Odoo series discovered under \${ODOO_GIT_BASE:-\$HOME/git}."
        echo "  Clone an Odoo repo (e.g. 'git clone https://github.com/odoo/odoo -b 17.0 ~/git/odoo17')"
        echo "  or set ODOO_GIT_BASE to where your repos live, then re-run this step."
        echo "  (No instance profile written - nothing to declare yet.)"
        _ensure_gitignore
        return 0
    fi

    # Port allocation: assign a distinct http_port per NEW instance, stepping by
    # 10 so each instance leaves room for a longpolling/gevent port later. Seed
    # the counter from the number of instances already declared so re-running
    # never changes an existing instance's port (idempotent).
    local base_port=8069 port_idx
    # NOTE: `grep -c` prints "0" on stdout AND exits 1 when the file exists but
    # has zero matches. A `|| echo 0` fallback would ALSO fire in that case,
    # yielding the two-line string "0\n0", which crashes the `port=$((...))`
    # arithmetic below under `set -euo pipefail` ("arithmetic syntax error").
    # Use `|| true` plus a default expansion so we always get a single integer
    # whether the file is absent, present-with-0-matches, or present-with-N.
    port_idx="$(grep -cE '^\[\[instance\]\]' "$INSTANCES_TOML" 2>/dev/null || true)"
    port_idx="${port_idx:-0}"

    # Build the addons_path per series: join paths whose series matches, in the
    # role-priority order discover_odoo.sh already emits. Each series becomes an
    # [[instance]] array-of-tables item keyed by the `series` field (no dotted
    # table headers, so every Python TOML parser reads it back correctly).
    local ver
    while IFS= read -r ver; do
        [[ -n "$ver" ]] || continue
        local paths port suggested_py out pyline
        paths="$(printf '%s\n' "$tsv" \
            | grep -vE '^#' \
            | awk -F'\t' -v v="$ver" 'NF>=3 && $2==v {printf "\"%s\", ", $3}' \
            | sed 's/, $//' || true)"
        [[ -z "$paths" ]] && paths=""
        port=$((base_port + port_idx * 10))
        suggested_py="$(_suggested_python "$ver")"
        if [[ -n "$suggested_py" ]]; then
            pyline=$(printf 'python = ""                     # venv python for source mode; suggested Python for %s: %s' "$ver" "$suggested_py")
        else
            pyline='python = ""                     # venv python for source mode (empty = system python3)'
        fi

        # Body: no password. Host/user/db/port are sensible local defaults the
        # user/agent confirms; password stays in env (ODOO_PG_PASSWORD).
        out="$( {
            printf 'series = "%s"\n' "$ver"
            printf 'addons_path = [%s]\n' "$paths"
            printf 'run_mode = "source"            # source | docker\n'
            printf 'http_port = %s\n' "$port"
            printf 'db_name = "odoo_%s"\n' "${ver//./_}"
            printf 'db_host = "localhost"\n'
            printf 'db_user = "odoo"\n'
            printf '%s\n' "$pyline"
            printf '# db_password: DO NOT store here. Use env ODOO_PG_PASSWORD or your keychain.\n'
        } | python3 "$LIB" toml-append-array-item "$INSTANCES_TOML" instance series "$ver" )"
        if printf '%s' "$out" | grep -q '^exists'; then
            echo "  [[instance]] series=$ver already present - skip"
        else
            echo "  wrote [[instance]] series=$ver (http_port=$port) -> $INSTANCES_TOML"
            port_idx=$((port_idx + 1))
        fi
    done <<<"$versions"

    _ensure_gitignore

    echo "ok instance profile(s) declared in $INSTANCES_TOML"
    echo "   (Edit addons_path / ports / db_name as needed. No password is stored.)"
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
