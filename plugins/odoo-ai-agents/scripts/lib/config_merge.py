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
# Entry point / dispatch
# ---------------------------------------------------------------------------

SUBCOMMANDS = {
    "json-merge": cmd_json_merge,
    "toml-ensure-table": cmd_toml_ensure_table,
    "toml-append-array-item": cmd_toml_append_array_item,
    "json-ensure-allow": cmd_json_ensure_allow,
    "json-prune-allow": cmd_json_prune_allow,
    "json-rule-covered": cmd_json_rule_covered,
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
