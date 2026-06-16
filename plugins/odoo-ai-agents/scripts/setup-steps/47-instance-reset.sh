#!/usr/bin/env bash
# 47-instance-reset.sh - Reset instances.toml: backup then clear (--reset; --hard wipes all).
#
# This step is ROUTED EXPLICITLY (not via the `all` glob loop) through a
# --reset or --hard flag on the setup command. The `check` subcommand always
# exits 0 so the step is treated as satisfied by the automatic loop.
#
# Subcommands:
#   describe         One-line description.
#   check            Always exits 0 (treated as satisfied; real entry is via apply).
#   apply [--hard]   Back up instances.toml, then rewrite it:
#                      default  - keep instances whose every addons_path entry
#                                 exists on disk (drop dead/junk entries).
#                      --hard   - write a header-comment-only file with 0 instances.
#
# CONFIG:
#   ODOO_AI_INSTANCES  full-path override for instances.toml (tests / custom)
#   ODOO_AI_HOME       machine-global state dir    (default $HOME/.odoo-ai)
#   ODOO_AI_BACKUP_TS  fixed timestamp for deterministic test backups (optional)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTANCES_IO="$SCRIPT_DIR/../lib/instances_io.py"

# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Reset instances.toml: backup then clear (--reset; --hard wipes all)"
}

# ---------------------------------------------------------------------------
# check - always satisfied (routing is via apply / explicit flag)
# ---------------------------------------------------------------------------
cmd_check() {
    return 0
}

# ---------------------------------------------------------------------------
# _backup_toml - copy <path> to <path>.bak.<ts>; honour ODOO_AI_BACKUP_TS
# ---------------------------------------------------------------------------
_backup_toml() {
    local path="$1"
    local ts
    if [[ -n "${ODOO_AI_BACKUP_TS:-}" ]]; then
        ts="$ODOO_AI_BACKUP_TS"
    else
        ts="$(date +%s)"
    fi
    local dst="${path}.bak.${ts}"
    cp -- "$path" "$dst"
    echo "$dst"
}

# ---------------------------------------------------------------------------
# _all_paths_exist - return 0 if every addons_path entry exists on disk
# ---------------------------------------------------------------------------
_all_paths_exist() {
    local paths_colon="$1"
    local p
    IFS=':' read -ra _chk_paths <<< "$paths_colon"
    for p in "${_chk_paths[@]}"; do
        [[ -n "$p" ]] || continue
        [[ -d "$p" ]] || return 1
    done
    return 0
}

# ---------------------------------------------------------------------------
# apply [--hard]
# ---------------------------------------------------------------------------
cmd_apply() {
    local hard=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --hard) hard=1; shift ;;
            *) echo "Unknown argument: $1" >&2; return 2 ;;
        esac
    done

    # Resolve the target path (explicit override or machine-global).
    local toml
    toml="$(_write_instances_target)"

    # --- Step 1: backup if file exists ---
    if [[ -f "$toml" ]]; then
        local bak
        bak="$(_backup_toml "$toml")"
        echo "  backup -> $bak"
    else
        echo "  (no existing instances.toml - nothing to back up)"
    fi

    # --- Step 2: load and report existing instances ---
    local existing_count=0
    local kept_count=0
    local dropped_count=0

    if [[ -f "$toml" && -f "$INSTANCES_IO" ]]; then
        # Use instances_io.py to list all instances; tolerate parse errors.
        local series_list
        series_list="$(python3 - "$toml" "$INSTANCES_IO" <<'PY' 2>/dev/null || true
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[2])))
import instances_io

path = sys.argv[1]
try:
    instances = instances_io.load_instances(path)
except Exception as e:
    sys.stderr.write(f"parse error: {e}\n")
    sys.exit(0)

for it in instances:
    series = it.get("series", it.get("version", "?"))
    paths = it.get("addons_path", [])
    if isinstance(paths, str):
        paths = [paths]
    paths_str = ":".join(str(p) for p in paths)
    print(f"{series}\t{paths_str}")
PY
)"
        if [[ -n "$series_list" ]]; then
            while IFS=$'\t' read -r series paths_colon; do
                existing_count=$((existing_count + 1))
                if _all_paths_exist "$paths_colon"; then
                    kept_count=$((kept_count + 1))
                    echo "  keep   [[instance]] series=$series (paths ok)"
                else
                    dropped_count=$((dropped_count + 1))
                    echo "  drop   [[instance]] series=$series (dead path)"
                fi
            done <<< "$series_list"
        fi
    fi

    # --- Step 3: write clean file ---
    mkdir -p "$(dirname "$toml")"

    if [[ "$hard" -eq 1 ]]; then
        # --hard: wipe everything
        printf '# instances.toml - reset (--hard); re-run setup step 40 to re-populate.\n' > "$toml"
        echo "ok instances.toml wiped (--hard); 0 instances remain -> $toml"
    else
        # default: keep only instances whose every addons_path dir exists
        if [[ -f "$toml" && -f "$INSTANCES_IO" && -n "${series_list:-}" ]]; then
            # Write a fresh file by re-reading the backup and filtering.
            local bak_content bak_path
            # Find the most recent backup (created just above).
            bak_path="$(ls -t "${toml}".bak.* 2>/dev/null | head -1 || true)"

            if [[ -n "$bak_path" && -f "$bak_path" ]]; then
                python3 - "$bak_path" "$toml" <<'PY'
import sys, re, os

def _parse_value(raw):
    raw = raw.split("#", 1)[0].strip()
    if raw.startswith("[") and raw.endswith("]"):
        items = []
        for part in raw[1:-1].split(","):
            part = part.strip().strip('"').strip("'")
            if part:
                items.append(part)
        return items
    if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw

def load_raw_blocks(path):
    """Return list of (header_line, body_lines, series, addons_path_list)."""
    blocks = []
    cur_body = []
    cur_series = None
    cur_paths = []
    in_block = False
    _LEGACY = re.compile(r"^\[\s*instance\.(?P<key>.+?)\s*\]$")
    preamble = []

    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    i = 0
    # Collect any leading comment/blank preamble before first [[instance]].
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "[[instance]]" or _LEGACY.match(stripped):
            break
        preamble.append(lines[i])
        i += 1

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "[[instance]]":
            if in_block:
                blocks.append(("[[instance]]", list(cur_body), cur_series, cur_paths))
            cur_body = []
            cur_series = None
            cur_paths = []
            in_block = True
            i += 1
            continue
        m = _LEGACY.match(stripped)
        if m:
            if in_block:
                blocks.append(("[[instance]]", list(cur_body), cur_series, cur_paths))
            k = m.group("key").strip().strip('"').strip("'")
            cur_body = []
            cur_series = k
            cur_paths = []
            in_block = True
            i += 1
            continue
        if in_block:
            cur_body.append(lines[i])
            val = _parse_value(lines[i].partition("=")[2]) if "=" in lines[i] else None
            key_raw = lines[i].partition("=")[0].strip()
            if key_raw == "series" and val:
                cur_series = val
            elif key_raw == "addons_path" and val:
                cur_paths = val if isinstance(val, list) else [val]
        i += 1

    if in_block:
        blocks.append(("[[instance]]", list(cur_body), cur_series, cur_paths))

    return preamble, blocks

def all_paths_exist(paths):
    return all(os.path.isdir(p) for p in paths if p)

src_path, dst_path = sys.argv[1], sys.argv[2]
preamble, blocks = load_raw_blocks(src_path)

kept = [b for b in blocks if all_paths_exist(b[3])]

out = []
# Write preamble only if it's non-trivial (not just our own reset comment).
for line in preamble:
    if not line.strip().startswith("#"):
        out.append(line)

for hdr, body, series, paths in kept:
    out.append("\n[[instance]]\n")
    out.extend(body)

with open(dst_path, "w", encoding="utf-8") as fh:
    if not out or all(not l.strip() for l in out):
        fh.write("# instances.toml - cleaned; re-run setup step 40 to re-populate.\n")
    else:
        content = "".join(out)
        # Strip leading blank lines.
        fh.write(content.lstrip("\n"))
PY
            else
                printf '# instances.toml - reset; re-run setup step 40 to re-populate.\n' > "$toml"
            fi
        else
            # No instances or no backup; write minimal clean file.
            printf '# instances.toml - reset; re-run setup step 40 to re-populate.\n' > "$toml"
        fi

        # Re-count kept after write.
        local kept_after=0
        kept_after="$(grep -cE '^\[\[instance\]\]' "$toml" 2>/dev/null || true)"
        kept_after="${kept_after:-0}"
        echo "ok instances.toml cleaned: $kept_after instance(s) kept, $dropped_count dropped -> $toml"
    fi
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    shift; cmd_apply "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply [--hard]}" >&2; exit 2 ;;
esac
