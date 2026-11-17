#!/usr/bin/env python3
"""state_sweep.py - remove the old entries of one run-scoped state directory.

    state_sweep.py <directory> --older-than-minutes N [--files] [--name GLOB] [--exclude NAME ...]

Removes each direct child directory (default) or, with --files, each direct child file (only those
matching --name GLOB when given) whose NEWEST modification time is older than N minutes: the entry
itself and, for a directory, every file and directory under it. --exclude names children that are
never touched (repeatable).

Prints `SWEPT=<count>` and one `REMOVED=<name>` line per removed entry, sorted. A missing
directory is `SWEPT=0`. The directory itself is never removed. A symlink is never followed: a
symlinked child is unlinked, not descended into, and a symlink inside a directory is judged by its
own time. The directory must lie inside the plugin state root (paths.state_root(), $ODOO_AI_HOME).

Exit 0; 2 on a usage error or a directory outside the state root. Stdlib only.
Tests: tests/test_state_sweep.py.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402


def newest_mtime(path):
    """The latest modification time of `path` and, for a real directory, of everything under it."""
    newest = os.lstat(path).st_mtime
    if os.path.isdir(path) and not os.path.islink(path):
        for base, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                try:
                    newest = max(newest, os.lstat(os.path.join(base, name)).st_mtime)
                except OSError:
                    continue
    return newest


def _remove(path):
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def sweep(directory, minutes, files=False, name=None, exclude=(), now=None):
    """Remove the matching old children of `directory`; the sorted names removed."""
    if not os.path.isdir(directory):
        return []
    cutoff = (time.time() if now is None else now) - minutes * 60
    removed = []
    for child in sorted(os.listdir(directory)):
        if child in exclude:
            continue
        path = os.path.join(directory, child)
        is_dir = os.path.isdir(path) and not os.path.islink(path)
        if files:
            if is_dir or (name and not fnmatch.fnmatch(child, name)):
                continue
        elif not (is_dir or os.path.islink(path)):
            continue
        if newest_mtime(path) >= cutoff:
            continue
        try:
            _remove(path)
        except OSError:
            continue
        removed.append(child)
    return removed


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path != root and os.path.commonpath([path, root]) == root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory")
    parser.add_argument("--older-than-minutes", type=float, required=True, dest="minutes")
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--name", default=None)
    parser.add_argument("--exclude", nargs="+", action="extend", default=[])
    args = parser.parse_args(argv)
    if args.minutes < 0:
        print("x --older-than-minutes must not be negative", file=sys.stderr)
        return 2
    directory = os.path.abspath(os.path.expanduser(args.directory))
    if not _inside(directory, paths.state_root()):
        print("x %s is not inside the plugin state root" % directory, file=sys.stderr)
        return 2
    removed = sweep(directory, args.minutes, args.files, args.name, set(args.exclude))
    print("SWEPT=%d" % len(removed))
    for child in removed:
        print("REMOVED=%s" % child)
    return 0


if __name__ == "__main__":
    sys.exit(main())
