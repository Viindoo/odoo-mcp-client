#!/usr/bin/env bash
# 40-instance-profile.sh - Declare local Odoo instance(s) for visual setup.
#
# Runs discover_odoo.sh to find Odoo core + addon repos on the machine, prints
# the discovered TSV for the user to confirm the addons-path ordering, and
# persists the result to `.odoo-ai/instances.toml` at the project root. Also
# ensures `.odoo-ai/` is gitignored (same no-op grep pattern as odoo-onboard).
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
# check - true when instances.toml exists with >=1 [instance.<version>] table
# ---------------------------------------------------------------------------
cmd_check() {
    [[ -f "$INSTANCES_TOML" ]] || return 1
    grep -qE '^\[instance\.' "$INSTANCES_TOML"
}

# ---------------------------------------------------------------------------
# gitignore - idempotent append of `.odoo-ai/` (mirrors odoo-onboard step 8)
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

    # If nothing discovered, write a single placeholder instance so `check`
    # has something and the AI agent/user can edit it.
    if [[ -z "$versions" ]]; then
        versions="0.0"
    fi

    # Build the addons_path per version: join paths whose version matches, in
    # the role-priority order discover_odoo.sh already emits.
    local ver
    while IFS= read -r ver; do
        [[ -n "$ver" ]] || continue
        if cmd_check && grep -qE "^\[instance\.${ver//./\\.}\]" "$INSTANCES_TOML" 2>/dev/null; then
            echo "  [instance.$ver] already present - skip"
            continue
        fi
        local paths
        paths="$(printf '%s\n' "$tsv" \
            | grep -vE '^#' \
            | awk -F'\t' -v v="$ver" 'NF>=3 && $2==v {printf "\"%s\", ", $3}' \
            | sed 's/, $//' || true)"
        [[ -z "$paths" ]] && paths=""

        # Body: no password. Host/user/db/port are sensible local defaults the
        # user/agent confirms; password stays in env (ODOO_PG_PASSWORD).
        {
            printf 'version = "%s"\n' "$ver"
            printf 'addons_path = [%s]\n' "$paths"
            printf 'run_mode = "source"            # source | docker\n'
            printf 'http_port = 8069\n'
            printf 'db_name = "odoo_%s"\n' "${ver//./_}"
            printf 'db_host = "localhost"\n'
            printf 'db_user = "odoo"\n'
            printf '# db_password: DO NOT store here. Use env ODOO_PG_PASSWORD or your keychain.\n'
        } | python3 "$LIB" toml-ensure-table "$INSTANCES_TOML" "[instance.$ver]" >/dev/null
        echo "  wrote [instance.$ver] -> $INSTANCES_TOML"
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
