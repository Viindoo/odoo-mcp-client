"""
config_merge.py - Safe, idempotent config merge utility (stdlib only, no pip).

Subcommands:
  json-merge <target.json>
      Read a JSON fragment from stdin and deep-merge it into target.
      Dict keys are merged recursively. Lists are unioned (no duplicates).
      Creates target if it does not exist.
      Refuses to overwrite a target that is not valid JSON (exit 2).
      Creates a timestamped backup before any write.
      Idempotent: if merged result equals current content, prints "unchanged"
      and does NOT create a backup.

  toml-ensure-table <target.toml> <table_header>
      Read key=value lines from stdin. Ensure the named TOML table exists.
      If the table is already present, print "exists" and exit 0.
      Otherwise APPEND the header + body to the end of the file (preserving
      comments and formatting) and create a backup first.
      Requires py3.11+ for tomllib; falls back to text scan on older Python.

  json-ensure-allow <settings.json> <prefix>
      Idempotently append a permission prefix into permissions.allow[].
      Mirrors the exact logic from odoo-semantic-mcp/commands/connect.md
      step 5: setdefault, backup, refuse invalid JSON (exit 2), idempotent.

Exit codes:
  0  success / no change needed
  1  general error (I/O, parse failure for input, etc.)
  2  target file exists but is not valid JSON/TOML (refuse to overwrite)

Usage examples:
  # Merge a fragment into a JSON settings file
  echo '{"mcpServers": {"my-server": {"url": "http://localhost:8000"}}}' \\
    | python3 config_merge.py json-merge ~/.claude/settings.json

  # Ensure a TOML table exists in pyproject.toml
  echo 'url = "http://localhost:8000"' \\
    | python3 config_merge.py toml-ensure-table pyproject.toml '[tool.my-server]'

  # Idempotently add a permission prefix
  python3 config_merge.py json-ensure-allow ~/.claude/settings.json mcp__odoo-semantic
"""

import json
import os
import re
import shutil
import sys
import time


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _backup_ts() -> int:
    """Return a unix timestamp for backup suffixes.
    Honours TEST_BACKUP_TS env var so tests can pin a deterministic value."""
    raw = os.environ.get("TEST_BACKUP_TS")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return int(time.time())


def _backup(path: str) -> str:
    """Copy path to <path>.bak.<ts> and return the backup path."""
    ts = _backup_ts()
    dst = f"{path}.bak.{ts}"
    shutil.copy2(path, dst)
    return dst


def _deep_merge(base: dict, fragment: dict) -> dict:
    """Recursively merge fragment into base.
    - dict values are merged recursively.
    - list values are unioned (preserving order, no duplicates by value).
    - scalar values from fragment overwrite base.
    Returns a NEW dict (base is not mutated).
    """
    result = dict(base)
    for key, fval in fragment.items():
        bval = result.get(key)
        if isinstance(bval, dict) and isinstance(fval, dict):
            result[key] = _deep_merge(bval, fval)
        elif isinstance(bval, list) and isinstance(fval, list):
            # Union: keep existing order, append new items only
            seen = set()
            merged = []
            for item in bval:
                # Use json-serialised form as a hashable key
                k = json.dumps(item, sort_keys=True)
                if k not in seen:
                    seen.add(k)
                    merged.append(item)
            for item in fval:
                k = json.dumps(item, sort_keys=True)
                if k not in seen:
                    seen.add(k)
                    merged.append(item)
            result[key] = merged
        else:
            result[key] = fval
    return result


def _load_json_target(path: str) -> dict:
    """Load JSON from path; return {} if file does not exist.
    Exits with code 2 if the file exists but is not valid JSON.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(
            f"x {path} is not valid JSON ({exc}). Refusing to overwrite.",
            file=sys.stderr,
        )
        sys.exit(2)


def _write_json(path: str, data: dict) -> None:
    """Write data as indented JSON, ensuring a trailing newline."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Subcommand: json-merge
# ---------------------------------------------------------------------------

def cmd_json_merge(args: list[str]) -> int:
    """json-merge <target.json>

    Read a JSON fragment from stdin and deep-merge it into target.json.
    Creates the file if it does not exist. Idempotent.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_json_merge.__doc__)
        return 0
    if len(args) != 1:
        print("Usage: config_merge.py json-merge <target.json>", file=sys.stderr)
        return 1

    target_path = args[0]

    # Read fragment from stdin
    try:
        fragment_raw = sys.stdin.read()
        fragment = json.loads(fragment_raw)
    except json.JSONDecodeError as exc:
        print(f"x stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(fragment, dict):
        print("x Fragment must be a JSON object (dict), not a list or scalar.", file=sys.stderr)
        return 1

    # Load existing target (exits 2 on invalid JSON)
    existing = _load_json_target(target_path)
    merged = _deep_merge(existing, fragment)

    # Idempotency check: compare serialized forms
    existing_serial = json.dumps(existing, sort_keys=True)
    merged_serial = json.dumps(merged, sort_keys=True)
    if existing_serial == merged_serial:
        print("unchanged")
        return 0

    # Backup existing file before write
    if os.path.exists(target_path):
        bak = _backup(target_path)
        print(f"backup -> {bak}")

    _write_json(target_path, merged)
    print(f"ok -> {target_path}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: toml-ensure-table
# ---------------------------------------------------------------------------

def _split_toml_key(key_str: str) -> list[str]:
    """Split a dotted TOML key path on '.' that lies OUTSIDE quotes, stripping
    the surrounding quotes from each segment.

    Plain ``str.split(".")`` is wrong for quoted keys: a header like
    ``instance."17.0"`` must split to ``['instance', '17.0']``, not
    ``['instance', '"17', '0"']``.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    quote_char = ""
    for ch in key_str:
        if in_quote:
            if ch == quote_char:
                in_quote = False
            else:
                buf.append(ch)
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
        elif ch == ".":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _toml_table_exists_tomllib(path: str, header: str) -> bool:
    """Use tomllib to detect if a TOML table header is already present.
    header is the raw bracket form, e.g. '[tool.my-server]' or
    '[mcp_servers.playwright]'.
    """
    try:
        import tomllib  # py3.11+
    except ImportError:
        return _toml_table_exists_text(path, header)

    # Normalise header to dot-path key sequence
    # Strip leading/trailing brackets and whitespace
    raw = header.strip()
    if raw.startswith("[["):
        # Array-of-tables: strip [[ ]]
        key_str = raw[2:-2].strip() if raw.endswith("]]") else raw[2:].strip("]").strip()
    elif raw.startswith("["):
        key_str = raw[1:-1].strip() if raw.endswith("]") else raw[1:].strip("]").strip()
    else:
        key_str = raw

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        # Cannot parse; fall back to text scan
        return _toml_table_exists_text(path, header)

    # Walk the parsed tree along the key path (quote-aware split)
    parts = _split_toml_key(key_str)
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _toml_array_has_item(path: str, array_name: str, field: str, value: str) -> bool:
    """True if the array-of-tables ``[[array_name]]`` already contains an item
    whose ``field`` equals ``value``. Uses tomllib (py3.11+) when available,
    else a minimal text scan over ``[[array_name]]`` blocks.
    """
    if not os.path.exists(path):
        return False
    try:
        import tomllib  # py3.11+
    except ImportError:
        return _toml_array_has_item_text(path, array_name, field, value)
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return _toml_array_has_item_text(path, array_name, field, value)
    items = data.get(array_name)
    if not isinstance(items, list):
        return False
    return any(
        isinstance(it, dict) and str(it.get(field)) == str(value) for it in items
    )


def _toml_array_has_item_text(path: str, array_name: str, field: str, value: str) -> bool:
    """Fallback for Python < 3.11: scan ``[[array_name]]`` blocks for a line
    ``field = "value"`` (string/bare scalar)."""
    if not os.path.exists(path):
        return False
    header = f"[[{array_name}]]"
    in_block = False
    pat = re.compile(
        r"^\s*" + re.escape(field) + r'\s*=\s*["\']?' + re.escape(str(value)) + r'["\']?\s*(#.*)?$'
    )
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped == header:
                    in_block = True
                    continue
                if stripped.startswith("["):  # any other table/array ends the block
                    in_block = False
                    continue
                if in_block and pat.match(stripped):
                    return True
    except OSError:
        pass
    return False


def _toml_table_exists_text(path: str, header: str) -> bool:
    """Fallback: scan file text for the exact header line (stripped)."""
    if not os.path.exists(path):
        return False
    normalised = header.strip()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip() == normalised:
                    return True
    except OSError:
        pass
    return False


def cmd_toml_ensure_table(args: list[str]) -> int:
    """toml-ensure-table <target.toml> <table_header>

    Read key=value body lines from stdin.
    Ensure [table_header] exists in target.toml.
    If already present: print "exists" and exit 0 (no change).
    If absent: append header + body to the end of the file, backup first.
    Creates file if it does not exist.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_toml_ensure_table.__doc__)
        return 0
    if len(args) != 2:
        print(
            "Usage: config_merge.py toml-ensure-table <target.toml> <table_header>",
            file=sys.stderr,
        )
        return 1

    target_path = args[0]
    header = args[1]

    # Normalise header: ensure it's wrapped in [ ]
    header_stripped = header.strip()
    if not (header_stripped.startswith("[") and header_stripped.endswith("]")):
        header_stripped = f"[{header_stripped}]"

    body_raw = sys.stdin.read()

    # Check existence
    if os.path.exists(target_path):
        if _toml_table_exists_tomllib(target_path, header_stripped):
            print("exists")
            return 0
        # Backup before modifying
        bak = _backup(target_path)
        print(f"backup -> {bak}")

    # Append block to file (preserves all existing content + comments)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with open(target_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(header_stripped + "\n")
        if body_raw.strip():
            # Ensure body ends with a newline
            fh.write(body_raw.rstrip("\n") + "\n")

    print(f"appended -> {target_path}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: toml-append-array-item
# ---------------------------------------------------------------------------

def cmd_toml_append_array_item(args: list[str]) -> int:
    """toml-append-array-item <target.toml> <array_name> <match_field> <match_value>

    Read key=value body lines from stdin. Ensure the array-of-tables
    [[array_name]] contains an item whose <match_field> == <match_value>.
    If such an item already exists: print "exists" and exit 0 (no change).
    Otherwise append a new [[array_name]] block with the body, backing up first.
    Creates the file if it does not exist. Idempotent.

    Unlike toml-ensure-table this keys uniqueness off a FIELD value rather than
    the table header, so it is safe for repeated [[array_name]] items.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_toml_append_array_item.__doc__)
        return 0
    if len(args) != 4:
        print(
            "Usage: config_merge.py toml-append-array-item "
            "<target.toml> <array_name> <match_field> <match_value>",
            file=sys.stderr,
        )
        return 1

    target_path, array_name, field, value = args
    body_raw = sys.stdin.read()

    if os.path.exists(target_path):
        if _toml_array_has_item(target_path, array_name, field, value):
            print("exists")
            return 0
        bak = _backup(target_path)
        print(f"backup -> {bak}")

    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with open(target_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"[[{array_name}]]\n")
        if body_raw.strip():
            fh.write(body_raw.rstrip("\n") + "\n")

    print(f"appended -> {target_path}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: json-ensure-allow
# ---------------------------------------------------------------------------

def cmd_json_ensure_allow(args: list[str]) -> int:
    """json-ensure-allow <settings.json> <prefix>

    Idempotently append <prefix> into permissions.allow[] in settings.json.
    Mirrors the logic from odoo-semantic-mcp/commands/connect.md step 5:
      - setdefault permissions / allow
      - backup before any write
      - refuse to overwrite invalid JSON (exit 2)
      - idempotent: if prefix already present, print message and exit 0
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_json_ensure_allow.__doc__)
        return 0
    if len(args) != 2:
        print(
            "Usage: config_merge.py json-ensure-allow <settings.json> <prefix>",
            file=sys.stderr,
        )
        return 1

    settings_path = args[0]
    prefix = args[1]

    # Load existing settings (exits 2 on invalid JSON)
    data = _load_json_target(settings_path)

    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])

    if prefix in allow:
        print(f"ok {prefix} already in allow-list - no change.")
        return 0

    # Backup before modifying
    if os.path.exists(settings_path):
        bak = _backup(settings_path)
        print(f"backup -> {bak}")

    allow.append(prefix)

    os.makedirs(os.path.dirname(os.path.abspath(settings_path)), exist_ok=True)
    _write_json(settings_path, data)
    print(f"ok Added {prefix} to permissions.allow in {settings_path}.")
    return 0


# ---------------------------------------------------------------------------
# Entry point / dispatch
# ---------------------------------------------------------------------------

SUBCOMMANDS = {
    "json-merge": cmd_json_merge,
    "toml-ensure-table": cmd_toml_ensure_table,
    "toml-append-array-item": cmd_toml_append_array_item,
    "json-ensure-allow": cmd_json_ensure_allow,
}


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("Subcommands:", ", ".join(SUBCOMMANDS))
        return 0

    sub = argv[0]
    if sub not in SUBCOMMANDS:
        print(f"Unknown subcommand: {sub!r}. Choose from: {', '.join(SUBCOMMANDS)}", file=sys.stderr)
        return 1

    return SUBCOMMANDS[sub](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
