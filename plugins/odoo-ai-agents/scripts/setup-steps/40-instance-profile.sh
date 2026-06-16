#!/usr/bin/env bash
# 40-instance-profile.sh - Declare local Odoo instance(s) for visual setup.
#
# Runs discover_odoo.sh to find Odoo core + addon repos on the machine, prints
# the discovered TSV for the user to confirm the addons-path ordering, and
# persists the result to the machine-global `~/.odoo-ai/instances.toml` (so any
# agent on this host resolves it from any cwd; see lib/resolve_instances.sh).
# Also ensures the project `.odoo-ai/` is gitignored (same no-op grep pattern).
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
#   ODOO_AI_DIR        project context dir    ${ODOO_AI_DIR:-$PWD/.odoo-ai}
#   ODOO_AI_HOME       machine-global state   ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml (tests / custom)
#   ODOO_GIT_BASE      scan root for repos    (consumed by discover_odoo.sh)

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

ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"   # project artifacts (context.md, worklog, ...) - cwd-scoped
# instances.toml is machine-global (resolvable from any cwd); the resolver is the SSOT.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
INSTANCES_TOML="$(_write_instances_target)"
GITIGNORE="$PWD/.gitignore"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Discover local Odoo repos and declare instance profile(s) in ~/.odoo-ai/instances.toml (machine-global)"
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
# _write_instance_from_spec  (shared by apply)
#   $1 = series   $2 = addons_path TOML literal (already quoted, comma-sep)
#   $3 = http_port  $4 = db_name  $5 = db_host  $6 = db_user  $7 = python
# ---------------------------------------------------------------------------
_write_instance_from_spec() {
    local ver="$1" paths="$2" port="$3" db_name="$4" db_host="$5" db_user="$6" py="$7"
    local suggested_py pyline out

    suggested_py="$(_suggested_python "$ver")"
    if [[ -n "$py" ]]; then
        pyline=$(printf 'python = "%s"' "$py")
    elif [[ -n "$suggested_py" ]]; then
        pyline=$(printf 'python = ""                     # venv python for source mode; suggested Python for %s: %s' "$ver" "$suggested_py")
    else
        pyline='python = ""                     # venv python for source mode (empty = system python3)'
    fi

    out="$( {
        printf 'series = "%s"\n' "$ver"
        printf 'addons_path = [%s]\n' "$paths"
        printf 'run_mode = "source"            # source | docker\n'
        printf 'http_port = %s\n' "$port"
        printf 'db_name = "%s"\n' "$db_name"
        printf 'db_host = "%s"\n' "$db_host"
        printf 'db_user = "%s"\n' "$db_user"
        printf '%s\n' "$pyline"
        printf '# db_password: DO NOT store here. Use env ODOO_PG_PASSWORD or your keychain.\n'
    } | python3 "$LIB" toml-append-array-item "$INSTANCES_TOML" instance series "$ver" )"
    if printf '%s' "$out" | grep -q '^exists'; then
        echo "  [[instance]] series=$ver already present - skip"
        return 0
    else
        echo "  wrote [[instance]] series=$ver (http_port=$port) -> $INSTANCES_TOML"
        return 1   # signal: new item written (caller increments port_idx)
    fi
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    if [[ ! -f "$LIB" ]]; then
        echo "x lib/config_merge.py missing under $SCRIPT_DIR/../lib - install the plugin fully." >&2
        return 1
    fi

    # Guard: require a confirmed spec. Without it we MUST NOT auto-write anything.
    local spec_file="${ODOO_AI_PROFILE_SPEC:-}"
    if [[ -z "$spec_file" ]]; then
        echo "----------------------------------------------------------------------" >&2
        echo "  ODOO_AI_PROFILE_SPEC is not set." >&2
        echo >&2
        echo "  This step no longer auto-discovers and writes instances.toml without" >&2
        echo "  confirmation. To proceed:" >&2
        echo >&2
        echo "  1. Review the discovered Odoo repos on this machine:" >&2
        if [[ -f "$DISCOVER" ]]; then
            echo "       bash $DISCOVER" >&2
        fi
        echo >&2
        echo "  2. Build a confirmed JSON spec file, e.g. /tmp/profile.json:" >&2
        echo '       [{"series":"17.0","addons_path":["/abs/custom","/abs/core"]}]' >&2
        echo >&2
        echo "  3. Re-run with the spec exported:" >&2
        echo "       ODOO_AI_PROFILE_SPEC=/tmp/profile.json bash $0 apply" >&2
        echo "----------------------------------------------------------------------" >&2
        echo "x provide ODOO_AI_PROFILE_SPEC with the confirmed profile to write" >&2
        return 1
    fi

    if [[ ! -f "$spec_file" ]]; then
        echo "x ODOO_AI_PROFILE_SPEC=$spec_file: file not found" >&2
        return 1
    fi

    # instances.toml is machine-global. Seed it once from an existing project-local
    # file (idempotent copy, no clobber) and ensure the global dir + a defensive
    # .gitignore exist before we write.
    _migrate_local_instances_to_global

    mkdir -p "$(dirname "$INSTANCES_TOML")"

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

    # Parse each instance object from the JSON spec and write it.
    # Required: series, addons_path. Defaults for the rest.
    local n_items
    n_items="$(python3 - "$spec_file" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
if not isinstance(data, list):
    print("x ODOO_AI_PROFILE_SPEC JSON must be a list of instance objects", file=sys.stderr)
    sys.exit(1)
print(len(data))
PY
)" || return 1

    # Validate ENTIRE spec upfront before writing anything (no partial write).
    python3 - "$spec_file" <<'PY' || return 1
import json, sys
data = json.load(open(sys.argv[1]))
errors = []
for idx, item in enumerate(data):
    series = item.get("series")
    if not series or not str(series).strip():
        errors.append(f"item[{idx}]: missing or empty 'series'")
    addons = item.get("addons_path")
    if not isinstance(addons, list) or len(addons) == 0:
        errors.append(f"item[{idx}]: 'addons_path' must be a non-empty list")
if errors:
    for e in errors:
        print(f"x spec validation error: {e}", file=sys.stderr)
    sys.exit(1)
PY

    local i=0
    while [[ $i -lt $n_items ]]; do
        local ver addons_raw db_name_raw db_host_raw db_user_raw http_port_raw py_raw
        ver="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item["series"])
PY
)"
        addons_raw="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
paths = item.get("addons_path", [])
print(", ".join(f'"{p}"' for p in paths))
PY
)"
        http_port_raw="$(python3 - "$spec_file" "$i" "$base_port" "$port_idx" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
base = int(sys.argv[3])
idx  = int(sys.argv[4])
print(item.get("http_port") or (base + idx * 10))
PY
)"
        db_name_raw="$(python3 - "$spec_file" "$i" "$ver" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
default = "odoo_" + sys.argv[3].replace(".", "_")
print(item.get("db_name") or default)
PY
)"
        db_host_raw="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item.get("db_host") or "localhost")
PY
)"
        db_user_raw="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item.get("db_user") or "odoo")
PY
)"
        py_raw="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item.get("python") or "")
PY
)"

        if _write_instance_from_spec "$ver" "$addons_raw" "$http_port_raw" \
                "$db_name_raw" "$db_host_raw" "$db_user_raw" "$py_raw"; then
            : # already present - port_idx unchanged
        else
            port_idx=$((port_idx + 1))
        fi
        i=$((i + 1))
    done

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
