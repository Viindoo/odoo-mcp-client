#!/usr/bin/env python3
"""state_root_permissions.py - which state roots may hold permission rules (stdlib only).

The SessionStart permission step (setup-steps/32-permissions-state-root.sh) appends
`Read(//<root>/**)` and `Edit(//<root>/projects/**)` for the session's state root to
permissions.allow[] of the user's settings file. A session that runs with a throwaway
state root (a test or a scratch run) must not leave such rules behind. This helper owns
the two decisions the step delegates:

  ephemeral <root>
      Exit 0 when <root> is an ephemeral state root, 1 when it is not. Ephemeral means
      the root is, or lies under, one of:
        - a system temp directory (the built-in list below, or the directories named by
          ODOO_AI_TEMP_DIRS - an os.pathsep list that REPLACES the built-in list; a
          test seam, never needed in normal use);
        - the scratch directory of the default state root ($HOME/.odoo-ai/scratch).
      Symlinks are resolved on both sides before comparing.

  prune <settings.json> <current-root> [--check]
      Remove the plugin's OWN state-root rule pairs whose root is gone or ephemeral:
        Edit(//<root>/projects/**)   - the plugin's signature; a pair is recognised by it
        Read(//<root>/**)            - removed together with its Edit rule
      A root is pruned when its directory no longer exists, or when it is ephemeral
      (even if it still exists - the plugin never writes such rules). <current-root> (the
      session's own root, which may not exist yet on a first run) is never pruned as
      "vanished". A Read rule with no Edit rule beside it, and every other rule shape,
      is a user's rule and stays. With --check nothing is written: exit 0 when
      something would be pruned, 1 when not. Without it: backup, lock and atomic write
      exactly like config_merge.py; nothing to prune writes nothing; invalid JSON exits 2.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_merge  # noqa: E402  (shared backup / lock / atomic write)

# Directories the system uses for throwaway files. /var/folders is the per-user temp area
# on macOS; the real path of each entry is compared too, so a symlinked temp dir is covered.
_SYSTEM_TEMP_DIRS = ("/tmp", "/var/tmp", "/var/folders", "/private/var/folders")

_EDIT_PREFIX = "Edit(//"
_EDIT_SUFFIX = "/projects/**)"
_READ_PREFIX = "Read(//"
_READ_SUFFIX = "/**)"
_GLOB_CHARS = "*?[]{}"


def _temp_dirs() -> list[str]:
    raw = os.environ.get("ODOO_AI_TEMP_DIRS")
    if raw is not None:
        return [d for d in raw.split(os.pathsep) if d]
    return list(_SYSTEM_TEMP_DIRS)


def _forms(path: str) -> set[str]:
    return {os.path.normpath(path), os.path.realpath(path)}


def _is_under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def is_ephemeral(root: str) -> bool:
    bases = set()
    for d in _temp_dirs():
        bases |= _forms(d)
    home = os.environ.get("HOME") or os.path.expanduser("~")
    bases |= _forms(os.path.join(home, ".odoo-ai", "scratch"))
    return any(_is_under(r, b) for r in _forms(root) for b in bases)


def _edit_root(entry) -> str | None:
    """The absolute root an `Edit(//<root>/projects/**)` rule names, else None."""
    if not (isinstance(entry, str) and entry.startswith(_EDIT_PREFIX) and entry.endswith(_EDIT_SUFFIX)):
        return None
    root = "/" + entry[len(_EDIT_PREFIX):-len(_EDIT_SUFFIX)]
    if root == "/" or any(c in root for c in _GLOB_CHARS):
        return None
    return root


def stale_rules(allow: list, current_root: str) -> list[str]:
    """The allow[] entries to remove: both rules of every plugin-written root that is
    ephemeral, or gone from disk and not the session's own root."""
    current = _forms(current_root)
    stale_roots = set()
    for entry in allow:
        root = _edit_root(entry)
        if root is None:
            continue
        gone = not os.path.isdir(root) and not (_forms(root) & current)
        if gone or is_ephemeral(root):
            stale_roots.add(root)
    doomed = set()
    for root in stale_roots:
        doomed.add(f"{_EDIT_PREFIX}{root[1:]}{_EDIT_SUFFIX}")
        doomed.add(f"{_READ_PREFIX}{root[1:]}{_READ_SUFFIX}")
    return [e for e in allow if isinstance(e, str) and e in doomed]


def cmd_prune(args: list[str]) -> int:
    check_only = "--check" in args
    rest = [a for a in args if a != "--check"]
    if len(rest) != 2:
        print("Usage: state_root_permissions.py prune <settings.json> <current-root> [--check]",
              file=sys.stderr)
        return 1
    settings_path, current_root = rest
    with config_merge.locked_target(settings_path):
        data = config_merge._load_json_target(settings_path)
        allow = (data.get("permissions") or {}).get("allow") if isinstance(data, dict) else None
        if not isinstance(allow, list):
            return 1 if check_only else 0
        doomed = stale_rules(allow, current_root)
        if check_only:
            return 0 if doomed else 1
        if not doomed:
            print("ok no stale state-root rules - no change.")
            return 0
        print(f"backup -> {config_merge._backup(settings_path)}")
        data["permissions"]["allow"] = [e for e in allow if e not in doomed]
        config_merge._write_json(settings_path, data)
        print(f"ok removed stale state-root rules from {settings_path}: {doomed}.")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) == 2 and argv[0] == "ephemeral":
        return 0 if is_ephemeral(argv[1]) else 1
    if argv and argv[0] == "prune":
        return cmd_prune(argv[1:])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
