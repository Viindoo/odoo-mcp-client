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

  toml-upsert-instance-keys <instances.toml> <series> <profile> PAIR...
      Insert-or-replace keys on the ONE [[instance]] block matching
      (series, profile). PAIR is KEY=VALUE (a TOML string) or KEY[]=A,B (a TOML
      array of strings; KEY[]= is the empty array). Unknown keys, comments and
      other blocks are kept byte for byte; atomic write. See its docstring.

  json-ensure-allow <settings.json> <prefix>
      Idempotently append a permission prefix into permissions.allow[].
      Mirrors the exact logic from odoo-semantic-mcp/commands/connect.md
      step 5: setdefault, backup, refuse invalid JSON (exit 2), idempotent.

  json-prune-allow <settings.json> <stale_suffix> <stable_prefix> <keep_exact>
      Remove every permissions.allow[] entry that BOTH starts with
      <stable_prefix> AND ends with <stale_suffix>, EXCEPT an entry equal to
      <keep_exact> (never removed even though it also matches). Prune-only:
      never adds anything, including <keep_exact> itself if absent. Used to
      converge version-pinned rules across plugin upgrades - see
      json-rule-covered's docstring for why pruning must stay UNCONDITIONAL
      (independent of whether the current version's own rule gets added).
      Same safety contract as json-ensure-allow: backup before write, refuse
      invalid JSON (exit 2), idempotent no-op (no backup, no write) when
      nothing matches.

  json-rule-covered <settings.json> <rule>
      Read-only (never writes, never backs up). Exit 0 if <rule> is ALREADY
      GRANTED by an existing permissions.allow[] entry - an exact duplicate,
      or a small, explicitly enumerated set of provably-broader forms (see
      below); exit 1 otherwise. Used before writing a permission rule so a
      setup step adds NOTHING when the permission is already covered.
      DELIBERATELY CONSERVATIVE: coverage is recognized ONLY for forms whose
      semantics are unambiguous per Claude Code's own documentation
      (https://code.claude.com/docs/en/permissions). Anything not on this
      list - including a same-tool relative glob like "Read(**)", whose
      anchor is the SESSION's actual working directory and therefore cannot
      be proven to contain an absolute target path ahead of time - is NOT
      treated as coverage, so the caller still adds the rule. This bias is
      intentional: concluding "covered" when it is not means the permission
      is silently never granted (breaks function, a missed prompt with no
      error); concluding "not covered" when it actually is means one harmless
      redundant rule gets written (visible, self-correcting clutter). The
      two errors are NOT symmetric - do not "improve" this matcher to guess
      at forms outside the enumerated set. Recognized forms:
        1. Exact string duplicate of <rule>.
        2. A bare tool-name rule (e.g. "Bash", "Read", "Edit" with no
           parentheses) for the SAME tool - documented to match every use of
           that tool unconditionally.
        3. "<Tool>(*)" for the SAME tool - documented equivalent to the bare
           tool-name form (established explicitly for Bash in the docs;
           applied here to any tool since the underlying glob semantics -
           "*" matches any sequence of characters - are tool-agnostic for a
           lone, unanchored "*" specifier).
        4. An existing "<Tool>(//<ancestor>/**)" entry (filesystem-root
           anchored, via the "//" prefix) whose <ancestor> is <rule>'s own
           anchor path or a strict parent directory of it, when <rule> is
           itself of the SAME "<Tool>(//<path>/**)" shape. Both sides share
           the unambiguous filesystem-root anchor, so containment is a plain
           string-prefix check, independent of any session's working
           directory.
        5. For Bash rules only: an existing "Bash(<P> *)" or "Bash(<P>:*)"
           entry (a literal, wildcard-free <P> followed by the documented
           trailing-wildcard form) where <rule>'s own command text starts
           with "<P> " (P then a literal space) - the documented prefix-match
           semantics for Bash rules.

  mcp-server-matches <json|toml> <target> <name>
      Read-only. Read the DESIRED server spec ({"command", "args", "env"}) as JSON
      on stdin; exit 0 when <target> registers server <name> with exactly that
      command, args and env, 1 when it is missing or differs (drift), 2 when the
      target cannot be parsed. json: <target>.mcpServers.<name> (Gemini settings,
      Claude's ~/.claude.json user scope). toml: [mcp_servers.<name>] (Codex).

  mcp-server-set <json|toml> <target> <name>
      REPLACE server <name> with the spec on stdin (extra keys such as "trust"
      are written too). Never merges: a merged args list would keep a stale
      flag next to its replacement. Backup before write, refuse invalid JSON
      (exit 2), "unchanged" (no write, no backup) when already identical.

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

# Annotations stay strings: the builtin-generic / `X | None` forms below would
# otherwise be EVALUATED at import and crash every subcommand on Python < 3.10
# (3.8/3.9 hosts run the JSON-only setup steps through this file too).
from __future__ import annotations

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

    existing = ""
    if os.path.exists(target_path):
        if _toml_array_has_item(target_path, array_name, field, value):
            print("exists")
            return 0
        bak = _backup(target_path)
        print(f"backup -> {bak}")
        with open(target_path, encoding="utf-8") as fh:
            existing = fh.read()

    addition = "\n" + f"[[{array_name}]]\n"
    if body_raw.strip():
        addition += body_raw.rstrip("\n") + "\n"

    # ATOMIC publish: write a sibling temp file, then os.replace it over the
    # target - same discipline as 45-venv.sh's _upsert_instance_keys. An
    # in-place append (the prior "a" mode) leaves a window in which the
    # host's only instance catalog is truncated/partial if the process is
    # killed mid-write.
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    tmp = "%s.tmp.%d" % (target_path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(existing + addition)
        os.replace(tmp, target_path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        print(f"x cannot write {target_path}: {exc}. Nothing was recorded.", file=sys.stderr)
        return 1

    print(f"appended -> {target_path}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: toml-upsert-instance-keys
# ---------------------------------------------------------------------------

def _toml_basic_string(value: str) -> str:
    """`value` as a TOML BASIC string literal.

    Unescaped, a single `"` closes the string early and the whole catalog stops
    parsing - not one field: every instances_io.load_instances consumer (the
    allocator, every setup step, the teardown hook) then fails until a human
    repairs the file by hand. A backslash is the quieter variant: `\\t` decodes to
    a TAB, so the recorded value is silently WRONG instead of loudly broken.
    Backslash FIRST, or the escapes introduced for `"` get escaped again.
    """
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_value_span(src_lines: list, idx: int) -> int:
    """Index of the LAST line of the assignment starting at `idx`: the same line,
    unless its value opens an array that closes on a later line."""
    depth = 0
    quote = None
    j = idx
    text = src_lines[idx].split("=", 1)[1]
    while True:
        k = 0
        while k < len(text):
            ch = text[k]
            if quote:
                if ch == "\\" and quote == '"':
                    k += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                break
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            k += 1
        if depth <= 0 or j + 1 >= len(src_lines):
            return j
        j += 1
        text = src_lines[j]


def _inline_comment(text: str) -> str:
    """The trailing `# ...` comment of one TOML line (with the whitespace before
    it and without the newline), or "" - a `#` inside a quoted string is not one."""
    quote = None
    k = 0
    while k < len(text):
        ch = text[k]
        if quote:
            if ch == "\\" and quote == '"':
                k += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            start = k
            while start > 0 and text[start - 1] in " \t":
                start -= 1
            return text[start:].rstrip("\r\n")
        k += 1
    return ""


def _kept_comment(src_lines: list, first: int, last: int) -> str:
    """The inline comment a replaced assignment keeps: the one after its value
    (on its last line), else the one on its first line. Comments on the inner
    lines of a multi-line array annotate items that the new value replaces."""
    tail = _inline_comment(src_lines[last] if last != first
                           else src_lines[first].split("=", 1)[1])
    if tail or last == first:
        return tail
    return _inline_comment(src_lines[first].split("=", 1)[1])


def _atomic_replace(path: str, text: str) -> None:
    """Publish `text` as the new content of `path` atomically, KEEPING what the
    file already is: a symlink stays a symlink (its TARGET is replaced, in the
    target's directory), and the target's permission bits carry over (a 0600
    catalog must not come back world-readable). Raises OSError; the temp file is
    removed on failure."""
    real = os.path.realpath(path)
    try:
        mode = os.stat(real).st_mode & 0o7777
    except FileNotFoundError:
        mode = None
    tmp = "%s.tmp.%d" % (real, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            if mode is not None and hasattr(os, "fchmod"):
                os.fchmod(fh.fileno(), mode)
        os.replace(tmp, real)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _scan_instance_blocks(src_lines: list) -> list:
    """[{series, profile, last_kv, keys: {key: (first, last)}}] per [[instance]]
    block. A multi-line array value is ONE assignment spanning several lines, so
    a continuation line is never mistaken for a key or a table header."""
    blocks, cur = [], None
    idx = 0
    while idx < len(src_lines):
        s = src_lines[idx].strip()
        if s == "[[instance]]":
            if cur:
                blocks.append(cur)
            cur = {"series": "", "profile": "", "last_kv": idx, "keys": {}}
            idx += 1
            continue
        if s.startswith("["):
            if cur:
                blocks.append(cur)
                cur = None
            idx += 1
            continue
        if cur is not None and "=" in s and not s.startswith("#"):
            key = s.split("=", 1)[0].strip()
            last = _toml_value_span(src_lines, idx)
            val = s.split("=", 1)[1].split("#", 1)[0].strip().strip('"').strip("'")
            cur["keys"].setdefault(key, (idx, last))
            cur["last_kv"] = last
            if key == "series":
                cur["series"] = val
            elif key == "profile":
                cur["profile"] = val
            idx = last + 1
            continue
        idx += 1
    if cur:
        blocks.append(cur)
    return blocks


_TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def cmd_toml_upsert_instance_keys(args: list[str]) -> int:
    """toml-upsert-instance-keys <instances.toml> <series> <profile> PAIR [PAIR ...]

    INSERT-OR-REPLACE every key on the ONE [[instance]] block matching
    (series, profile), in place. A PAIR is either
      KEY=VALUE     -> KEY = "VALUE"              (a TOML string)
      KEY[]=A,B,C   -> KEY = ["A", "B", "C"]      (a TOML array of strings;
                       `KEY[]=` records the EMPTY array - a declared "none")
    An existing assignment of KEY is replaced whole, a multi-line array
    included; when KEY is ABSENT it is inserted after the block's last
    assignment, so a catalog written before a key existed GAINS it. Every other
    line - unknown keys, comments, other blocks - is kept byte for byte.
    An empty <profile> selects the unprofiled block. Refuses (exit 1, file
    untouched) when the series has only profiled blocks and no profile was
    given, and when no block matches. A replaced assignment keeps its own
    indentation and its inline comment. The new catalog is published atomically
    (sibling temp file + os.replace), never truncated in place: a crash in an
    in-place write loses every declared instance on the host. The file keeps
    its permission bits, and a symlinked catalog stays a symlink (its target is
    what is replaced) - see _atomic_replace.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_toml_upsert_instance_keys.__doc__)
        return 0
    if len(args) < 3:
        print("Usage: config_merge.py toml-upsert-instance-keys "
              "<instances.toml> <series> <profile> KEY=VALUE|KEY[]=A,B ...", file=sys.stderr)
        return 1
    path, series, profile = args[0], args[1], args[2]

    pairs = []
    for raw in args[3:]:
        if "=" not in raw:
            print("x internal: expected KEY=VALUE or KEY[]=A,B, got %r" % raw, file=sys.stderr)
            return 2
        key, _, value = raw.partition("=")
        if key.endswith("[]"):
            key = key[:-2]
            items = [v.strip() for v in value.split(",") if v.strip()]
            rendered = "[%s]" % ", ".join(_toml_basic_string(v) for v in items)
            shown = "[%s]" % ",".join(items)
        else:
            rendered = _toml_basic_string(value)
            shown = value
        if not _TOML_BARE_KEY.match(key):
            print("x internal: %r is not a bare TOML key" % key, file=sys.stderr)
            return 2
        pairs.append((key, rendered, shown))
    if not pairs:
        return 0

    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines(keepends=True)
    except OSError as exc:
        print("x cannot read %s: %s" % (path, exc), file=sys.stderr)
        return 1
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    blocks = _scan_instance_blocks(lines)
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
            return 1
    else:
        matches = [b for b in same_series if b["profile"] == profile]
    label = "%s:%s" % (series, profile) if profile else series
    if not matches:
        print(
            "x no [[instance]] block matches %s in %s - declare it first (step 40). "
            "Nothing was recorded." % (label, path),
            file=sys.stderr,
        )
        return 1

    block = matches[0]
    probe = lines[block["last_kv"]] if block["keys"] else ""
    indent = probe[: len(probe) - len(probe.lstrip())]

    out = list(lines)
    replacements, inserted = [], []
    for key, rendered, _shown in pairs:
        line = "%s%s = %s\n" % (indent, key, rendered)
        if key in block["keys"]:
            first, last = block["keys"][key]
            own = lines[first]
            own_indent = own[: len(own) - len(own.lstrip())]
            line = "%s%s = %s%s\n" % (own_indent, key, rendered,
                                     _kept_comment(lines, first, last))
            replacements.append((first, last, line))
        else:
            inserted.append(line)
    # Insert after the block's last assignment FIRST: every replaced span lies at
    # or before that line, so the insertion shifts none of them.
    at = block["last_kv"] + 1
    out[at:at] = inserted
    for first, last, line in sorted(replacements, reverse=True):
        out[first:last + 1] = [line]

    try:
        _atomic_replace(path, "".join(out))
    except OSError as exc:
        print("x cannot write %s: %s. Nothing was recorded." % (path, exc), file=sys.stderr)
        return 1
    print("  recorded %s for %s" % (", ".join("%s=%s" % (k, s) for k, _r, s in pairs), label))
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
# Subcommand: json-prune-allow
# ---------------------------------------------------------------------------

def _is_stale_entry(entry: str, keep_exact: str, stale_suffix: str, stable_prefix: str) -> bool:
    """Shared predicate: True iff `entry` is a version-pinned rule for the SAME
    plugin/script family as `keep_exact` but pinned to a DIFFERENT (stale) path.
    `entry == keep_exact` is never stale, even though it also matches the
    prefix/suffix - see json-prune-allow's docstring for the anchoring
    rationale (a suffix-only match is not enough; it must also share
    `stable_prefix`, which identifies ONE specific plugin's own directory)."""
    if entry == keep_exact:
        return False
    return entry.startswith(stable_prefix) and entry.endswith(stale_suffix)


def cmd_json_prune_allow(args: list[str]) -> int:
    """json-prune-allow <settings.json> <stale_suffix> <stable_prefix> <keep_exact>

    Remove every permissions.allow[] entry that BOTH starts with
    <stable_prefix> AND ends with <stale_suffix> - the SAME plugin's own
    script, pinned to a DIFFERENT (stale) absolute path (e.g. a prior version
    of that plugin's directory) - EXCEPT an entry equal to <keep_exact> (never
    removed even though it also matches). Prune-ONLY: does not add anything,
    including <keep_exact> itself if it is not already present.

    <stable_prefix> is REQUIRED. A suffix-only match is NOT anchored to any
    plugin's identity: two different plugins can each ship a same-named
    script (e.g. two plugins that both have scripts/lib/foo.sh), and a
    suffix-only prune would delete the OTHER plugin's unrelated rule. Passing
    a prefix specific enough to identify one plugin (its path up to and
    including the plugin-name directory) keeps the match scoped to that one
    plugin's own rule family.

    This is called UNCONDITIONALLY by the version-pinned-rule setup step,
    regardless of whether the current version's own rule ends up being added
    (see json-rule-covered) - stale debris from a prior plugin version is
    removed either way. Leaving it sitting there when the current rule is
    skipped as already-covered would NOT be defensible: it is exactly the
    accumulation this pruning exists to fix, and it grants nothing extra (if
    the current rule is redundant because of a broader existing permission,
    the stale prior-version rule is equally redundant under that same broader
    permission).

      - Backup before any write (same as json-ensure-allow).
      - Refuse to overwrite invalid JSON (exit 2).
      - Idempotent: if nothing matches (no stale entries), prints "unchanged"
        and exits 0 without writing or backing up.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_json_prune_allow.__doc__)
        return 0
    if len(args) != 4:
        print(
            "Usage: config_merge.py json-prune-allow "
            "<settings.json> <stale_suffix> <stable_prefix> <keep_exact>",
            file=sys.stderr,
        )
        return 1

    settings_path, stale_suffix, stable_prefix, keep_exact = args

    # Load existing settings (exits 2 on invalid JSON)
    data = _load_json_target(settings_path)

    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])

    kept = [a for a in allow if not _is_stale_entry(a, keep_exact, stale_suffix, stable_prefix)]

    if kept == allow:
        print("ok no stale entries - no change.")
        return 0

    removed = [a for a in allow if a not in kept]

    # Backup before modifying
    if os.path.exists(settings_path):
        bak = _backup(settings_path)
        print(f"backup -> {bak}")

    perms["allow"] = kept

    os.makedirs(os.path.dirname(os.path.abspath(settings_path)), exist_ok=True)
    _write_json(settings_path, data)
    print(f"ok removed stale entries from {settings_path}: {removed}.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: json-rule-covered
# ---------------------------------------------------------------------------

def _parse_rule(rule: str) -> tuple[str, str | None]:
    """Split "Tool(specifier)" into ("Tool", "specifier"), or a bare "Tool"
    rule into ("Tool", None)."""
    if "(" in rule and rule.endswith(")"):
        idx = rule.index("(")
        return rule[:idx], rule[idx + 1 : -1]
    return rule, None


def _rule_is_covered(allow: list[str], rule: str) -> tuple[bool, str]:
    """Core matcher for json-rule-covered. Returns (covered, reason). See the
    module docstring's json-rule-covered entry for the exact enumerated forms
    and the conservative bias driving this function: when in doubt, False."""
    if rule in allow:
        return True, "exact duplicate already in allow[]"

    tool, spec = _parse_rule(rule)

    # Form 2: a bare tool-name rule for the SAME tool matches every use of it.
    if tool in allow:
        return True, f"bare {tool!r} rule matches every use of this tool"

    # Form 3: "<Tool>(*)" - documented equivalent of the bare tool-name form
    # (explicitly stated for Bash; the underlying glob semantics of a lone,
    # unanchored "*" specifier are tool-agnostic).
    blanket = f"{tool}(*)"
    if blanket in allow:
        return True, f"{blanket!r} is equivalent to a bare {tool!r} rule"

    if spec is not None:
        # Form 4: filesystem-root-anchored ("//...") directory glob whose
        # anchor is an existing rule's anchor or a descendant of it. Only
        # meaningful when OUR OWN rule is also of this exact shape (our 4
        # rules' Read/Edit entries are; the Bash entries are not, so this
        # never fires for them).
        if spec.startswith("//") and spec.endswith("/**"):
            target_anchor = spec[2:-3]
            existing_prefix = f"{tool}(//"
            for entry in allow:
                if not (entry.startswith(existing_prefix) and entry.endswith("/**)")):
                    continue
                existing_spec = entry[len(tool) + 1 : -1]
                existing_anchor = existing_spec[2:-3]
                if target_anchor == existing_anchor or target_anchor.startswith(existing_anchor + "/"):
                    return True, f"{entry!r} already covers this path (ancestor directory)"

        # Form 5: Bash literal-prefix wildcard ("<P> *" / "<P>:*"), P
        # wildcard-free, where our command text starts with "<P> ".
        if tool == "Bash":
            for entry in allow:
                if not entry.startswith("Bash("):
                    continue
                inner = entry[len("Bash(") : -1]
                if inner.endswith(" *"):
                    p = inner[:-2]
                elif inner.endswith(":*"):
                    p = inner[:-2]
                else:
                    continue
                if "*" not in p and spec.startswith(p + " "):
                    return True, f"{entry!r} already covers this command (prefix wildcard)"

    return False, "not covered by any recognized form - adding"


def cmd_json_rule_covered(args: list[str]) -> int:
    """json-rule-covered <settings.json> <rule>

    Read-only (never writes). Exit 0 and print the reason if <rule> is
    already GRANTED by an existing permissions.allow[] entry (see the module
    docstring for the exact, deliberately small enumerated set of recognized
    forms); exit 1 otherwise. A missing or unreadable settings file, or any
    form not in the enumerated set, is treated as NOT covered (the caller
    should add the rule) - this function never widens the enumerated set to
    "look more broadly"; see the module docstring for why that asymmetry is
    intentional.
    """
    if not args or args[0] in ("-h", "--help"):
        print(cmd_json_rule_covered.__doc__)
        return 0
    if len(args) != 2:
        print(
            "Usage: config_merge.py json-rule-covered <settings.json> <rule>",
            file=sys.stderr,
        )
        return 1

    settings_path, rule = args

    try:
        with open(settings_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        print("not covered - settings file missing or unreadable")
        return 1

    allow = (data.get("permissions") or {}).get("allow") or []
    covered, reason = _rule_is_covered(allow, rule)
    print(reason)
    return 0 if covered else 1



# ---------------------------------------------------------------------------
# Subcommands: mcp-server-matches / mcp-server-set
# ---------------------------------------------------------------------------

def _read_spec_stdin() -> dict | None:
    try:
        spec = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"x stdin is not valid JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(spec, dict) or not isinstance(spec.get("command"), str) \
            or not isinstance(spec.get("args"), list):
        print('x the spec must be an object with "command" (string) and "args" (list)',
              file=sys.stderr)
        return None
    return spec


def _launch_equal(entry, spec: dict) -> bool:
    """Same command, same args (order included) and same env; a missing env equals {}."""
    if not isinstance(entry, dict):
        return False
    return (entry.get("command") == spec["command"]
            and list(entry.get("args") or []) == list(spec["args"])
            and dict(entry.get("env") or {}) == dict(spec.get("env") or {}))


def _toml_server_header(name: str) -> str:
    return f"[mcp_servers.{name}]"


def _toml_render_server(name: str, spec: dict) -> str:
    lines = [_toml_server_header(name),
             f"command = {_toml_basic_string(spec['command'])}",
             "args = [" + ", ".join(_toml_basic_string(str(a)) for a in spec["args"]) + "]"]
    env = spec.get("env") or {}
    if env:
        pairs = ", ".join(f"{_toml_basic_string(k)} = {_toml_basic_string(str(v))}"
                          for k, v in sorted(env.items()))
        lines.append("env = { " + pairs + " }")
    return "\n".join(lines) + "\n"


def _toml_server_spans(src_lines: list, name: str) -> list:
    """(start, end) line spans of [mcp_servers.<name>] and its sub-tables."""
    own = _toml_server_header(name)[:-1]  # "[mcp_servers.<name>"
    spans, start = [], None
    for i, line in enumerate(src_lines):
        head = line.strip()
        if head.startswith("["):
            if start is not None:
                spans.append((start, i))
                start = None
            compact = head.replace(" ", "")
            if compact == own + "]" or compact.startswith(own + "."):
                start = i
    if start is not None:
        spans.append((start, len(src_lines)))
    return spans


def _toml_server_entry(path: str, name: str):
    """The registered [mcp_servers.<name>] entry as a dict, or None (needs tomllib, 3.11+).
    Without tomllib, cmd_mcp_server_matches compares the table's text against what
    _toml_render_server writes instead."""
    import tomllib  # py3.11+
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return (data.get("mcp_servers") or {}).get(name)


def cmd_mcp_server_matches(args: list[str]) -> int:
    """mcp-server-matches <json|toml> <target> <name>  (desired spec JSON on stdin)"""
    if len(args) != 3 or args[0] not in ("json", "toml"):
        print("Usage: config_merge.py mcp-server-matches <json|toml> <target> <name>",
              file=sys.stderr)
        return 2
    fmt, target, name = args
    spec = _read_spec_stdin()
    if spec is None:
        return 2
    if not os.path.isfile(target):
        return 1
    if fmt == "json":
        try:
            with open(target, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return 2
        entry = ((data.get("mcpServers") or {}) if isinstance(data, dict) else {}).get(name)
        return 0 if _launch_equal(entry, spec) else 1
    try:
        import tomllib  # noqa: F401  py3.11+
        have_tomllib = True
    except ImportError:
        have_tomllib = False
    if have_tomllib:
        try:
            entry = _toml_server_entry(target, name)
        except Exception:
            return 2
        return 0 if _launch_equal(entry, spec) else 1
    with open(target, encoding="utf-8") as fh:
        src_lines = fh.read().splitlines()
    spans = _toml_server_spans(src_lines, name)
    if len(spans) != 1:
        return 1
    start, end = spans[0]
    have = [ln.strip() for ln in src_lines[start:end]
            if ln.strip() and not ln.strip().startswith("#")]
    want = [ln.strip() for ln in _toml_render_server(name, spec).splitlines()]
    return 0 if have == want else 1


def cmd_mcp_server_set(args: list[str]) -> int:
    """mcp-server-set <json|toml> <target> <name>  (spec JSON on stdin)"""
    if len(args) != 3 or args[0] not in ("json", "toml"):
        print("Usage: config_merge.py mcp-server-set <json|toml> <target> <name>",
              file=sys.stderr)
        return 1
    fmt, target, name = args
    spec = _read_spec_stdin()
    if spec is None:
        return 1
    if fmt == "json":
        existing = _load_json_target(target)  # exits 2 on invalid JSON
        if not isinstance(existing, dict):
            print(f"x {target} is not a JSON object. Refusing to overwrite.", file=sys.stderr)
            return 2
        servers = existing.get("mcpServers")
        if servers is not None and not isinstance(servers, dict):
            print(f"x {target}: mcpServers is not an object. Refusing to overwrite.",
                  file=sys.stderr)
            return 2
        if (servers or {}).get(name) == spec:
            print("unchanged")
            return 0
        updated = dict(existing)
        updated["mcpServers"] = dict(servers or {})
        updated["mcpServers"][name] = spec
        if os.path.exists(target):
            print(f"backup -> {_backup(target)}")
        _write_json(target, updated)
        print(f"ok -> {target}")
        return 0
    text = ""
    if os.path.exists(target):
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
    src_lines = text.splitlines()
    rendered = _toml_render_server(name, spec)
    keep = list(src_lines)
    for start, end in reversed(_toml_server_spans(src_lines, name)):
        del keep[start:end]
    while keep and not keep[-1].strip():
        keep.pop()
    new_text = ("\n".join(keep) + "\n\n" if keep else "") + rendered
    if new_text == text:
        print("unchanged")
        return 0
    if os.path.exists(target):
        print(f"backup -> {_backup(target)}")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    _atomic_replace(target, new_text)
    print(f"ok -> {target}")
    return 0


# ---------------------------------------------------------------------------
# Entry point / dispatch
# ---------------------------------------------------------------------------

SUBCOMMANDS = {
    "json-merge": cmd_json_merge,
    "toml-ensure-table": cmd_toml_ensure_table,
    "toml-append-array-item": cmd_toml_append_array_item,
    "toml-upsert-instance-keys": cmd_toml_upsert_instance_keys,
    "json-ensure-allow": cmd_json_ensure_allow,
    "json-prune-allow": cmd_json_prune_allow,
    "json-rule-covered": cmd_json_rule_covered,
    "mcp-server-matches": cmd_mcp_server_matches,
    "mcp-server-set": cmd_mcp_server_set,
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
