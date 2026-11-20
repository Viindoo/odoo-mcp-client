#!/usr/bin/env python3
"""empty_state_dirs.py - remove the per-project and per-worktree state folders that hold nothing.

    empty_state_dirs.py sweep

Under <state root>/projects (paths.state_root(), $ODOO_AI_HOME) a folder is removed when its whole
tree holds only directories and nothing in it changed within the last day. The rule applies first
to each per-worktree folder (projects/<p>/worktrees/<w>), then to each project folder
(projects/<p>), judged on the tree as it was before the sweep so a project whose only content was
empty per-worktree folders goes in the same run. Any other kind of entry anywhere in a tree - a
file, a symlink (never followed), a socket - keeps that whole folder, as does a tree that cannot be
read in full. Directories are removed with rmdir only, deepest first, so a folder that gained
content meanwhile refuses and stays; an OS error on one folder is skipped.

Prints one summary line when something was removed, nothing otherwise. Exit 0, always. Only
<state root>/projects is swept, and the folder itself is never removed. Stdlib only.
Tests: tests/test_empty_state_dirs.py.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

MIN_AGE_S = 24 * 3600
WORKTREES = "worktrees"


def idle_empty_tree(path, cutoff):
    """The directories of the tree at `path`, deepest first, when it holds only real directories
    and none changed since `cutoff`; None otherwise (including a tree that cannot be read)."""
    found = []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            if os.lstat(current).st_mtime >= cutoff:
                return None
            with os.scandir(current) as it:
                for entry in it:
                    if not entry.is_dir(follow_symlinks=False):
                        return None
                    stack.append(entry.path)
        except OSError:
            return None
        found.append(current)
    return sorted(found, key=lambda p: p.count(os.sep), reverse=True)


def _children(path):
    try:
        with os.scandir(path) as it:
            return [e.path for e in it if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def _remove(dirs):
    """rmdir each directory in order; the number removed. A refusal keeps that directory, and so
    every directory above it, which rmdir refuses in turn."""
    removed = 0
    for directory in dirs:
        try:
            os.rmdir(directory)
        except OSError:
            continue
        removed += 1
    return removed


def sweep(root=None, now=None, min_age_s=MIN_AGE_S):
    """Remove the idle empty project and per-worktree folders; the number of directories removed."""
    projects = os.path.join(root or paths.state_root(), "projects")
    if os.path.islink(projects) or not os.path.isdir(projects):
        return 0
    cutoff = (time.time() if now is None else now) - min_age_s
    removed = 0
    for project in _children(projects):
        whole = idle_empty_tree(project, cutoff)
        if whole is not None:
            removed += _remove(whole)
            continue
        worktrees = os.path.join(project, WORKTREES)
        if os.path.islink(worktrees):
            continue
        for worktree in _children(worktrees):
            tree = idle_empty_tree(worktree, cutoff)
            if tree is not None:
                removed += _remove(tree)
    return removed


def main(argv):
    if argv == ["sweep"]:
        try:
            count = sweep()
            if count:
                print("empty-state-dirs: removed %d empty folder(s)" % count)
        except Exception:
            pass
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
