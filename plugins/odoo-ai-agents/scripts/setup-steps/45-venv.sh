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
MATRIX_JSON="$SCRIPT_DIR/../lib/odoo-python-matrix.json"
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
    _addons_path_to_array _paths "${INST_ADDONS_PATH:-}"
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

# Echo absolute path to odoo-bin scanning an addons_path string (SSOT
# separator - see resolve_instances.sh's _addons_path_to_array). Used when
# INST_ADDONS_PATH is already resolved (e.g. from a profiled read).
_core_odoo_bin_from_addons_path() {
    local addons_path="$1"
    local p up
    _addons_path_to_array _bp "${addons_path}"
    for p in "${_bp[@]}"; do
        [[ -n "$p" ]] || continue
        [[ -x "$p/odoo-bin" ]] && { echo "$p/odoo-bin"; return 0; }
        up="$(dirname "$p")"
        [[ -x "$up/odoo-bin" ]] && { echo "$up/odoo-bin"; return 0; }
    done
    return 0
}

# ---------------------------------------------------------------------------
# _upsert_instance_keys <series> <profile> KEY=VALUE [KEY=VALUE ...]
#
# INSERT-OR-REPLACE every KEY on the ONE [[instance]] block matching
# (series, profile), in place. Replaces an existing `KEY = ...` line; when the
# line is ABSENT it is INSERTED after the block's last assignment - a catalog
# written before a key existed therefore GAINS it, instead of silently keeping
# nothing. Refuses (non-zero, file untouched) when the series has only profiled
# blocks and no --profile was given, and when no block matches at all.
# ---------------------------------------------------------------------------
_upsert_instance_keys() {
    local series="$1" profile="$2"; shift 2
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare the instance first (step 40)." >&2
        return 1
    }
    python3 - "$INSTANCES_TOML" "$series" "$profile" "$@" <<'PY'
import os
import sys

path, series, profile = sys.argv[1], sys.argv[2], sys.argv[3]


def toml_escape(value):
    """Encode `value` for a TOML BASIC string (the `key = "..."` form below).

    Unescaped, a single `"` closes the string early and the whole catalog stops
    parsing - not one field: every instances_io.load_instances consumer (the
    allocator, every setup step, the teardown hook) then fails until a human
    repairs the file by hand. A backslash is the quieter variant: `\\t` decodes to
    a TAB, so the recorded value is silently WRONG instead of loudly broken.
    Backslash FIRST, or the escapes introduced for `"` get escaped again.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')
pairs = []
for raw in sys.argv[4:]:
    if "=" not in raw:
        print("x internal: expected KEY=VALUE, got %r" % raw, file=sys.stderr)
        sys.exit(2)
    key, _, value = raw.partition("=")
    pairs.append((key, value))
if not pairs:
    sys.exit(0)

try:
    lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
except OSError as exc:
    print("x cannot read %s: %s" % (path, exc), file=sys.stderr)
    sys.exit(1)


def scan_blocks(src_lines):
    """[(start, end, series, profile, last_assignment_index)] per [[instance]]."""
    blocks, cur = [], None
    for idx, raw in enumerate(src_lines):
        s = raw.strip()
        if s == "[[instance]]":
            if cur:
                blocks.append(cur)
            cur = {"start": idx, "end": idx, "series": "", "profile": "", "last_kv": idx}
            continue
        if s.startswith("["):
            if cur:
                blocks.append(cur)
                cur = None
            continue
        if cur is None:
            continue
        cur["end"] = idx
        if "=" in s and not s.startswith("#"):
            key = s.split("=", 1)[0].strip()
            val = s.split("=", 1)[1].strip().strip('"').strip("'")
            cur["last_kv"] = idx
            if key == "series":
                cur["series"] = val
            elif key == "profile":
                cur["profile"] = val
    if cur:
        blocks.append(cur)
    return blocks


blocks = scan_blocks(lines)
same_series = [b for b in blocks if b["series"] == series]
if profile == "":
    matches = [b for b in same_series if not b["profile"]]
    if same_series and not matches:
        print(
            "x series %r has only profile-specific [[instance]] blocks but no --profile "
            "was given. Pass --profile <name> to select the correct block. Nothing was "
            "recorded." % series,
            file=sys.stderr,
        )
        sys.exit(1)
else:
    matches = [b for b in same_series if b["profile"] == profile]
if not matches:
    label = "%s:%s" % (series, profile) if profile else series
    print(
        "x no [[instance]] block matches %s in %s - declare it first (step 40). "
        "Nothing was recorded." % (label, path),
        file=sys.stderr,
    )
    sys.exit(1)

block = matches[0]
indent = ""
probe = lines[block["last_kv"]]
indent = probe[: len(probe) - len(probe.lstrip())]

out = list(lines)
inserted = []
for key, value in pairs:
    replaced = False
    for idx in range(block["start"], block["end"] + 1):
        s = out[idx].strip()
        if s.startswith("#") or "=" not in s:
            continue
        if s.split("=", 1)[0].strip() != key:
            continue
        out[idx] = '%s%s = "%s"\n' % (indent, key, toml_escape(value))
        replaced = True
        break
    if not replaced:
        inserted.append('%s%s = "%s"\n' % (indent, key, toml_escape(value)))

if inserted:
    at = block["last_kv"] + 1
    out[at:at] = inserted

# ATOMIC publish: write a sibling temp file, then os.replace it over the target.
# An in-place truncate leaves a window in which the host's only instance catalog
# is empty or partial, and a crash there loses every declared instance. Same
# discipline as allocator.py's `_write_registry` - one pattern, not two.
tmp = "%s.tmp.%d" % (path, os.getpid())
try:
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    os.replace(tmp, path)
except OSError as exc:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    print("x cannot write %s: %s. Nothing was recorded." % (path, exc), file=sys.stderr)
    sys.exit(1)
label = "%s:%s" % (series, profile) if profile else series
print("  recorded %s for %s" % (", ".join("%s=%s" % kv for kv in pairs), label))
PY
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
        kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || kv=""
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

    local io="$SCRIPT_DIR/../lib/instances_io.py" kv=""
    kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "${profile:-}" 2>/dev/null)" || kv=""
    [[ -n "$kv" ]] || { echo "x no [[instance]] declared for series $series." >&2; return 1; }
    eval "$kv"

    local rc=0 venv_py="${INST_PYTHON:-}" odoo_root="" core_bin=""
    if [[ -n "$venv_py" && -x "$venv_py" ]]; then
        core_bin="$(_core_odoo_bin_from_addons_path "${INST_ADDONS_PATH:-}")" || core_bin=""
        if [[ -z "$core_bin" ]]; then
            core_bin="$(_core_odoo_bin_for_series "$series" "${profile:-}")" || core_bin=""
        fi
        if [[ -n "$core_bin" ]] && "$venv_py" "$core_bin" --version >/dev/null 2>&1; then
            odoo_root="$(dirname "$core_bin")"
        else
            echo "x '$venv_py <odoo-bin> --version' failed - python and odoo_root were NOT" >&2
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
            kv="$(python3 "$io" read "$INSTANCES_TOML" "$series" "${profile:-}" 2>/dev/null)" || kv=""
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

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    suggest)  shift; cmd_suggest "$@" ;;
    create-venv) shift; cmd_create_venv "$@" ;;
    record-env)  shift; cmd_record_env "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|suggest <series>|create-venv ...|record-env --series X.Y [--profile P]}" >&2; exit 2 ;;
esac
