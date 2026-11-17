#!/usr/bin/env python3
"""plugin_version_rules.py - the permission rules that name one installed plugin version (stdlib only).

Several sessions of different plugin versions share the user's settings file. A rule whose
text carries a version directory (`Bash(bash <plugins>/<plugin>/<version>/scripts/... share *)`)
covers the command of the session that runs from that directory and no other, so each rule
belongs to its directory and never to "the current version": every version writes the rules of
every installed version directory (its own and its siblings'), and a rule goes only when its
directory no longer holds the script. A version therefore never replaces a rule another version
wrote, and a rule survives every other version's start.

The rule shape ends in ` *` after the argument (documented: a trailing `*` with a space before it
also matches the bare command, so `... share *` covers `... share`). That shape is also the one
earlier releases do not recognise: their pruning removes only entries that end exactly with
`<script> share)` or `<script> isolate)`, so these rules survive an older session's start.

Subcommands:

  roots <plugin-root> <script-rel>
      Print the directories to grant, one per line: <plugin-root> first (always), then, when its
      last path segment is a MAJOR.MINOR.PATCH version, every sibling version directory that
      holds <script-rel>, in version order. A checkout loaded with --plugin-dir has no version
      segment: only <plugin-root> is printed.

  prune <settings.json> <plugin-root> <script-rel> [--check]
      Remove the Bash allow rules of this plugin's other version directories (same parent
      directory, version-named last segment) whose directory no longer holds <script-rel>:
        Bash(bash <parent>/<version>/<script-rel> <args>)   with <args> empty or `... *`
      <plugin-root> itself and every other rule shape - another plugin's, another script's, the
      user's own - stay. A <plugin-root> without a version segment prunes nothing. With --check
      nothing is written: exit 0 when something would be pruned, 1 when not. Without it: backup,
      lock and atomic write exactly like config_merge.py; nothing to prune writes nothing;
      invalid JSON exits 2.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_merge  # noqa: E402  (shared backup / lock / atomic write)

_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_BASH_HEAD = "Bash(bash "


def _version_key(name: str) -> tuple:
    return tuple(int(p) for p in name.split("."))


def _parent_of_versions(plugin_root: str) -> str:
    """The directory holding the version directories, or "" when <plugin-root> is not one."""
    root = plugin_root.rstrip("/")
    parent, name = os.path.split(root)
    return parent if _VERSION.match(name) and parent else ""


def roots(plugin_root: str, script_rel: str) -> list[str]:
    own = plugin_root.rstrip("/")
    out = [own]
    parent = _parent_of_versions(own)
    if not parent:
        return out
    try:
        names = [n for n in os.listdir(parent) if _VERSION.match(n)]
    except OSError:
        return out
    for name in sorted(names, key=_version_key):
        sibling = f"{parent}/{name}"
        if sibling != own and os.path.isfile(os.path.join(sibling, script_rel)):
            out.append(sibling)
    return out


def _entry_root(entry, parent: str, script_rel: str) -> str:
    """The version directory a Bash rule of this plugin's script names, or "" for any other entry."""
    if not isinstance(entry, str) or not entry.startswith(_BASH_HEAD + parent + "/") or not entry.endswith(")"):
        return ""
    inner = entry[len(_BASH_HEAD):-1]
    marker = "/" + script_rel
    cut = inner.find(marker)
    if cut < 0:
        return ""
    root, rest = inner[:cut], inner[cut + len(marker):]
    if " " in root or not _VERSION.match(os.path.basename(root)) or os.path.dirname(root) != parent:
        return ""
    return root if rest == "" or rest.startswith(" ") else ""


def vanished_rules(allow: list, plugin_root: str, script_rel: str) -> list[str]:
    own = plugin_root.rstrip("/")
    parent = _parent_of_versions(own)
    if not parent:
        return []
    doomed = []
    for entry in allow:
        root = _entry_root(entry, parent, script_rel)
        if root and root != own and not os.path.isfile(os.path.join(root, script_rel)):
            doomed.append(entry)
    return doomed


def cmd_prune(args: list[str]) -> int:
    check_only = "--check" in args
    rest = [a for a in args if a != "--check"]
    if len(rest) != 3:
        print("Usage: plugin_version_rules.py prune <settings.json> <plugin-root> <script-rel> [--check]",
              file=sys.stderr)
        return 1
    settings_path, plugin_root, script_rel = rest
    with config_merge.locked_target(settings_path):
        data = config_merge._load_json_target(settings_path)
        allow = (data.get("permissions") or {}).get("allow") if isinstance(data, dict) else None
        if not isinstance(allow, list):
            return 1 if check_only else 0
        doomed = vanished_rules(allow, plugin_root, script_rel)
        if check_only:
            return 0 if doomed else 1
        if not doomed:
            print("ok no rule of a removed plugin version - no change.")
            return 0
        print(f"backup -> {config_merge._backup(settings_path)}")
        data["permissions"]["allow"] = [e for e in allow if e not in doomed]
        config_merge._write_json(settings_path, data)
        print(f"ok removed rules of removed plugin versions from {settings_path}: {doomed}.")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) == 3 and argv[0] == "roots":
        print("\n".join(roots(argv[1], argv[2])))
        return 0
    if argv and argv[0] == "prune":
        return cmd_prune(argv[1:])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
