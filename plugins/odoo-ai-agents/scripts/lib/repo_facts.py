#!/usr/bin/env python3
"""repo_facts.py - the cheap git facts about a working tree, read by script so an agent runs no git.

READ-ONLY, no network, no hooks, no index lock (GIT_OPTIONAL_LOCKS=0). One call answers what
agent prose used to read with inline git:

  repo_root            top of the working tree containing `path` (what `rev-parse --show-toplevel` says)
  principal_root       the main checkout's root (the first entry of `git worktree list`); differs from
                       repo_root inside a linked worktree; "" when the repository is bare or its main
                       checkout is not recorded anywhere git can read (a separate git dir)
  is_linked_worktree   repo_root is a linked worktree, not the main checkout
  branch / detached    the checked-out branch ("" when HEAD is detached)
  ref                  the branch, else the short SHA when detached (in an unborn repo, the branch
                       the first commit will land on)
  head_sha / head_sha_full   short and full SHA of HEAD (empty before the first commit)
  origin_url / remotes remote URLs, credentials stripped
  operation_in_progress   merge | rebase | cherry-pick | revert | bisect | none (a paused multi-commit
                       cherry-pick or revert is told from its sequencer todo list)
  dirty                uncommitted changes under `status_paths` (the whole tree when none are given)

A path outside any repository is a normal result (is_repo false, every other field empty), not an
error. Anything else git cannot answer raises RepoFactsError with a named code.

  repo_facts.py PATH [--status-path P ...] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

TIMEOUT_S = 20
MAX_DIRTY_ENTRIES = 50

_GIT_PREFIX = ["git", "--literal-pathspecs", "-c", "core.fsmonitor=false"]
_NOT_A_REPO = "not a git repository"
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_HOST_PORT = re.compile(r"^(\[[^\]]*\]|[^:@\[\]]*)(:\d*)?$")

# marker (relative to the worktree's own git dir) -> operation name; first match wins, so a rebase
# that is also stopped on a cherry-pick reports the outer operation.
_OPERATION_MARKERS = (
    ("rebase-merge", "rebase"),
    ("rebase-apply", "rebase"),
    ("MERGE_HEAD", "merge"),
    ("CHERRY_PICK_HEAD", "cherry-pick"),
    ("REVERT_HEAD", "revert"),
    ("BISECT_LOG", "bisect"),
)


class RepoFactsError(Exception):
    def __init__(self, code, message, diagnostics=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or {}


_LOCAL_ENV = None


def _local_env_vars():
    """The variables git itself says are repository-local (`git rev-parse --local-env-vars`):
    GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE and the rest. Asked of git, never listed here, so a
    git that grows one is covered. Read once; an answer git cannot give removes nothing."""
    global _LOCAL_ENV
    if _LOCAL_ENV is None:
        try:
            proc = subprocess.run(["git", "rev-parse", "--local-env-vars"], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  universal_newlines=True, timeout=TIMEOUT_S)
            _LOCAL_ENV = proc.stdout.split() if proc.returncode == 0 else []
        except (OSError, subprocess.SubprocessError):
            _LOCAL_ENV = []
    return _LOCAL_ENV


def _git(args, cwd):
    """(rc, stdout, stderr) of `git <args>` run in cwd. Raises RepoFactsError on a missing git
    binary or a timeout. The server's own repository-local git variables are dropped, so the
    facts are those of `cwd` and never of whatever repository the server was started from."""
    env = dict(os.environ)
    for name in _local_env_vars():
        env.pop(name, None)
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    try:
        proc = subprocess.run(_GIT_PREFIX + list(args), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                              timeout=TIMEOUT_S)
    except FileNotFoundError:
        raise RepoFactsError("GIT_UNAVAILABLE", "the git executable is not on PATH")
    except subprocess.TimeoutExpired:
        raise RepoFactsError("SUBPROCESS_TIMEOUT", "git %s exceeded %ss" % (args[0], TIMEOUT_S),
                             {"command": args[0]})
    return proc.returncode, proc.stdout, proc.stderr


def _must(args, cwd):
    rc, out, err = _git(args, cwd)
    if rc != 0:
        raise RepoFactsError("GIT_FAILED", "git %s failed (rc=%d): %s" % (args[0], rc, err.strip()),
                             {"command": args[0], "rc": rc, "stderr": err.strip()[-2000:]})
    return out.strip()


def strip_credentials(url):
    """`https://user:token@host/x` -> `https://host/x`. scp-like (`user@host:path`) and file
    forms pass unchanged: their user part names an account, not a secret.

    The userinfo ends at the LAST `@` of the authority (a password may hold a raw `@`). An
    authority that is not a valid host[:port] means the userinfo itself held a `/` or `:`-shaped
    text git would cut at: everything up to the last `@` before the query is then credentials."""
    scheme = _SCHEME.match(url)
    if not scheme:
        return url
    head, rest = scheme.group(0), url[scheme.end():]
    try:
        netloc = urlsplit(url).netloc
    except ValueError:  # an unbalanced [ in the authority
        netloc = re.split(r"[/?#]", rest, 1)[0]
    if "@" in netloc:
        return head + rest[len(netloc.rsplit("@", 1)[0]) + 1:]
    if not _HOST_PORT.match(netloc):
        before_query = re.split(r"[?#]", rest, 1)[0]
        if "@" in before_query:
            return head + rest[before_query.rindex("@") + 1:]
    return url


def _absolute(path, cwd):
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))


def _empty(path):
    return {
        "path": path, "is_repo": False, "repo_root": "", "principal_root": "", "is_linked_worktree": False,
        "branch": "", "detached": False, "ref": "", "head_sha": "", "head_sha_full": "",
        "origin_url": "", "remotes": {}, "operation_in_progress": "none",
        "dirty": {"checked_paths": [], "is_dirty": False, "entries": [], "truncated": False},
    }


def _remotes(cwd):
    out = {}
    names = _must(["remote"], cwd).split()
    for name in names:
        rc, url, _ = _git(["remote", "get-url", name], cwd)
        if rc == 0 and url.strip():
            out[name] = strip_credentials(url.strip())
    return out


def _operation(git_dir):
    for marker, name in _OPERATION_MARKERS:
        if os.path.exists(os.path.join(git_dir, marker)):
            return name
    # A multi-commit cherry-pick or revert paused between commits (the conflict resolved and
    # committed by hand) leaves only the sequencer's todo list; its first verb names the operation.
    try:
        with open(os.path.join(git_dir, "sequencer", "todo")) as fh:
            for line in fh:
                if line.strip() and not line.startswith("#"):
                    return "revert" if line.split()[0] == "revert" else "cherry-pick"
    except (OSError, UnicodeDecodeError):
        pass
    if os.path.isdir(os.path.join(git_dir, "sequencer")):
        return "cherry-pick"
    return "none"


def _first_worktree(path):
    """The fields of the first `git worktree list --porcelain` entry (`worktree <path>`, then
    `HEAD ...`, `branch ...` or `bare`). NUL-separated where git can (2.36+), else by line."""
    rc, out, err = _git(["worktree", "list", "--porcelain", "-z"], path)
    sep = "\0"
    if rc != 0:
        rc, out, err = _git(["worktree", "list", "--porcelain"], path)
        sep = "\n"
    if rc != 0:
        raise RepoFactsError("GIT_FAILED", "git worktree failed (rc=%d): %s" % (rc, err.strip()),
                             {"command": "worktree", "rc": rc, "stderr": err.strip()[-2000:]})
    first = []
    for field in out.split(sep):
        if not field:
            break
        first.append(field)
    return first


def _principal_root(path, repo_root, common_dir, linked):
    """The main checkout: the first entry of `git worktree list`. A bare repository has none (""),
    and neither does a repository whose git dir is separate from its checkout: git then lists the
    git dir itself, a place nobody can check anything out of."""
    if not linked:
        return repo_root
    first = _first_worktree(path)
    if not first or not first[0].startswith("worktree ") or "bare" in first[1:]:
        return ""
    root = os.path.normpath(first[0][len("worktree "):])
    if os.path.realpath(root) == os.path.realpath(common_dir):
        return ""
    return root


def _dirty(cwd, status_paths):
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]
    if status_paths:
        args += ["--"] + [_absolute(p, cwd) for p in status_paths]
    rc, out, err = _git(args, cwd)  # not _must: strip() would eat the leading space of " M path"
    if rc != 0:
        raise RepoFactsError("GIT_FAILED", "git status failed (rc=%d): %s" % (rc, err.strip()),
                             {"command": "status", "rc": rc, "stderr": err.strip()[-2000:]})
    entries = []
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if not item:
            continue
        entries.append(item)
        if item[:1] in ("R", "C") or item[1:2] in ("R", "C"):
            i += 1  # a rename/copy carries its origin path as the next NUL field
    return {
        "checked_paths": [_absolute(p, cwd) for p in (status_paths or [])],
        "is_dirty": bool(entries),
        "entries": entries[:MAX_DIRTY_ENTRIES],
        "truncated": len(entries) > MAX_DIRTY_ENTRIES,
    }


def facts(path, status_paths=None):
    """The facts dict for the directory `path` (absolute)."""
    if not os.path.isdir(path):
        raise RepoFactsError("PATH_NOT_DIRECTORY", "path is not a directory: %s" % path, {"path": path})
    result = _empty(path)
    rc, top, err = _git(["rev-parse", "--show-toplevel"], path)
    if rc != 0:
        if _NOT_A_REPO in err:
            return result
        raise RepoFactsError("GIT_FAILED", "git rev-parse failed (rc=%d): %s" % (rc, err.strip()),
                             {"command": "rev-parse", "rc": rc, "stderr": err.strip()[-2000:]})
    repo_root = os.path.normpath(top.strip())
    git_dir = _absolute(_must(["rev-parse", "--absolute-git-dir"], path), path)
    common_dir = _absolute(_must(["rev-parse", "--git-common-dir"], path), path)
    linked = os.path.realpath(git_dir) != os.path.realpath(common_dir)
    result.update({
        "is_repo": True,
        "repo_root": repo_root,
        "is_linked_worktree": linked,
        "principal_root": _principal_root(path, repo_root, common_dir, linked),
        "operation_in_progress": _operation(git_dir),
    })

    rc, branch, _ = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], path)
    branch = branch.strip() if rc == 0 else ""
    rc, full, _ = _git(["rev-parse", "--verify", "--quiet", "HEAD"], path)
    full = full.strip() if rc == 0 else ""
    short = _must(["rev-parse", "--short", "HEAD"], path) if full else ""
    result.update({
        "branch": branch,
        "detached": not branch and bool(full),
        "ref": branch or short,
        "head_sha": short,
        "head_sha_full": full,
    })

    remotes = _remotes(path)
    result["remotes"] = remotes
    result["origin_url"] = remotes.get("origin", "")
    result["dirty"] = _dirty(path, status_paths)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("path")
    parser.add_argument("--status-path", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args(argv)
    try:
        out = facts(os.path.abspath(ns.path), ns.status_path or None)
    except RepoFactsError as exc:
        print("x %s: %s" % (exc.code, exc.message), file=sys.stderr)
        return 1
    if ns.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        for key in ("repo_root", "principal_root", "branch", "ref", "head_sha", "origin_url",
                    "operation_in_progress"):
            print("%s=%s" % (key.upper(), out[key]))
        print("DIRTY=%s" % ("yes" if out["dirty"]["is_dirty"] else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
