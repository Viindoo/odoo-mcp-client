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

# instances.toml is machine-global (resolvable from any cwd); the resolver is the SSOT.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
# repo-key resolver (Tier-2 state-root convention - snippets/state-root-resolution.md):
# sourced ONLY for its internal _project_dir_repo_key / _project_dir_hash12 /
# _project_dir_realpath_dir helpers (see _repo_key8 below). This step does not
# itself resolve a SHARE/ISOLATE dir, so the public resolve_project_dir_share/
# _isolate API is unused here.
# shellcheck source=../lib/resolve_project_dir.sh
source "$SCRIPT_DIR/../lib/resolve_project_dir.sh"
INSTANCES_TOML="$(_write_instances_target)"
GITIGNORE="$PWD/.gitignore"

# P2 db_name project-discriminator (49-solution-final.md §2.4.3): the first 8
# hex chars of sha256(realpath(git-common-dir)) - a stable, project-unique
# suffix so two same-series projects (now landing in ONE global catalog via
# the eager migration above) never default to the SAME db_name (the old
# default was series-derived only: "odoo_17_0" for every v17.0 project).
# CONVERGED (P3) onto resolve_project_dir.sh's repo-key resolver: the SAME
# source (sha256(realpath(git rev-parse --git-common-dir))) and the SAME
# non-git fallback (marker walk-up: a global `.odoo-ai-root` sentinel first,
# else the nearest `__manifest__.py`) - just an 8-hex slice of the resolver's
# 12-hex key instead of a fresh hash. When NEITHER git nor a marker is found
# anywhere in the chain (the resolver's own non-git fallback would REFUSE),
# falls back one step further to hashing THIS dir's own realpath - still
# deterministic per project dir, NEVER a bare constant.
_repo_key8() {
    local key12=""
    key12="$(_project_dir_repo_key 2>/dev/null)" || key12=""
    if [[ -z "$key12" ]]; then
        key12="$(_project_dir_hash12 "$(_project_dir_realpath_dir "$PWD")")" || return 1
    fi
    printf '%s\n' "${key12:0:8}"
}

# P2 bootstrap-race PRIMARY fix (49-solution-final.md §2.4.1): migrate THIS
# project's local .odoo-ai/instances.toml into the machine-global catalog
# EAGERLY, at session start (every subcommand dispatch below), rather than
# LAZILY only inside `apply` (which is additionally gated behind
# ODOO_AI_PROFILE_SPEC and so may never run at all in a given session). Two
# never-migrated same-series projects that BOTH migrate early land in ONE
# global catalog whose port_idx stepper (below) then sees every already-
# declared instance and assigns distinct ports before either ever spins up -
# shrinking the race window to near-zero by construction. Idempotent + a
# no-op copy (never clobbers an existing global) - see resolve_instances.sh.
_migrate_local_instances_to_global || true

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
#   $8 = profile (optional; empty string = no profile)
# ---------------------------------------------------------------------------
_write_instance_from_spec() {
    local ver="$1" paths="$2" port="$3" db_name="$4" db_host="$5" db_user="$6" py="$7"
    local profile="${8:-}"
    local suggested_py pyline profileline instance_key_val match_field match_value out

    suggested_py="$(_suggested_python "$ver")"
    if [[ -n "$py" ]]; then
        pyline=$(printf 'python = "%s"' "$py")
    elif [[ -n "$suggested_py" ]]; then
        pyline=$(printf 'python = ""                     # venv python for source mode; suggested Python for %s: %s' "$ver" "$suggested_py")
    else
        pyline='python = ""                     # venv python for source mode (empty = system python3)'
    fi

    # Compute instance_key and idempotency match-key.
    # Q1 backward-compat: when profile is empty, match by series (legacy behavior);
    # when profile is set, match by instance_key so two profiles of the same series
    # don't conflict and don't dedupe each other.
    if [[ -n "$profile" ]]; then
        instance_key_val="${ver}:${profile}"
        profileline=$(printf 'profile = "%s"\n' "$profile")
        match_field="instance_key"
        match_value="$instance_key_val"
    else
        instance_key_val="$ver"
        profileline=""
        match_field="series"
        match_value="$ver"
    fi

    out="$( {
        printf 'series = "%s"\n' "$ver"
        [[ -n "$profileline" ]] && printf '%s\n' "$profileline"
        printf 'instance_key = "%s"\n' "$instance_key_val"
        printf 'addons_path = [%s]\n' "$paths"
        printf 'run_mode = "source"            # source | docker\n'
        printf 'http_port = %s\n' "$port"
        printf 'db_name = "%s"\n' "$db_name"
        printf 'db_host = "%s"\n' "$db_host"
        printf 'db_user = "%s"\n' "$db_user"
        printf '%s\n' "$pyline"
        printf '# db_password: DO NOT store here. Use env ODOO_PG_PASSWORD or your keychain.\n'
    } | python3 "$LIB" toml-append-array-item "$INSTANCES_TOML" instance "$match_field" "$match_value" )"
    if printf '%s' "$out" | grep -q '^exists'; then
        local label="${ver}${profile:+:$profile}"
        echo "  [[instance]] $label already present - skip"
        return 0
    else
        local label="${ver}${profile:+:$profile}"
        echo "  wrote [[instance]] $label (http_port=$port) -> $INSTANCES_TOML"
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

    # instances.toml is machine-global; the migration itself now runs EAGERLY at
    # session start (top of this script, before subcommand dispatch - see the
    # P2 bootstrap-race comment there), not here. This mkdir remains as a
    # defensive no-op in case apply somehow runs before the eager call above.
    mkdir -p "$(dirname "$INSTANCES_TOML")"

    # Port allocation: assign a distinct http_port per NEW instance, stepping by
    # 11 so each instance leaves room for a longpolling/gevent port later
    # without landing exactly on the next declared boundary port (COSMETIC
    # ONLY - 49-solution-final.md §2.3: this does NOT fix an existing 8069/8079
    # catalog and does not itself close the allocator boundary off-by-one; the
    # real fix is allocator.py reserving every catalog-declared http_port, see
    # scripts/lib/allocator.py cmd_acquire). Seed the counter from the number
    # of instances already declared so re-running never changes an existing
    # instance's port (idempotent).
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

    # P2 db_name project-discriminator (49-solution-final.md §2.4.3): resolved
    # ONCE per apply() invocation (constant across every item in this spec, not
    # per-loop-iteration work) and threaded into the db_name default below.
    local repo_key8
    repo_key8="$(_repo_key8)"

    local i=0
    while [[ $i -lt $n_items ]]; do
        local ver addons_raw db_name_raw db_host_raw db_user_raw http_port_raw py_raw profile_raw
        ver="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item["series"])
PY
)"
        profile_raw="$(python3 - "$spec_file" "$i" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
print(item.get("profile") or "")
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
# Step by 11 (COSMETIC ONLY - see the comment above base_port): does not fix
# an existing catalog and is not itself the boundary off-by-one fix.
print(item.get("http_port") or (base + idx * 11))
PY
)"
        db_name_raw="$(python3 - "$spec_file" "$i" "$ver" "$profile_raw" "$repo_key8" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
item = data[int(sys.argv[2])]
prof = sys.argv[4]
repo_key8 = sys.argv[5]
# P2 db_name project-discriminator: default is now series- AND project-scoped
# (odoo_<series>_<repo-key8>) so two same-series projects sharing one global
# catalog never default to the SAME db_name (the old default was series-only).
default = "odoo_" + sys.argv[3].replace(".", "_") + "_" + repo_key8
if prof and not item.get("db_name"):
    # When profile is set and db_name not explicit, suffix the slug to avoid
    # two profiles of the same series sharing a database.
    import re
    slug = re.sub(r'[^a-zA-Z0-9._-]', '_', prof)
    default = default + "_" + slug
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
                "$db_name_raw" "$db_host_raw" "$db_user_raw" "$py_raw" "$profile_raw"; then
            : # already present - port_idx unchanged
        else
            port_idx=$((port_idx + 1))
        fi
        i=$((i + 1))
    done

    _ensure_gitignore

    # Seed machine-global i18n language registry (idempotent - no clobber)
    _I18N_JSON="$(dirname "$INSTANCES_TOML")/i18n.json"
    if [[ ! -f "$_I18N_JSON" ]]; then
        printf '{"default_languages":["vi_VN"]}\n' >"$_I18N_JSON"
        echo "  seeded $_I18N_JSON (default_languages=[\"vi_VN\"])"
    else
        echo "  $_I18N_JSON already exists - no change"
    fi

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
