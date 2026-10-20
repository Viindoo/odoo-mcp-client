#!/usr/bin/env python3
"""fork_facts.py - where a clone's fork lives, from its own git records. READ-ONLY, no network.

One mechanism shared by setup step 34 (auto-mode), step 60 (docs-site) and the instance repo
scan. For a clone it reports the owner and name of `origin`, every other remote with its owner
and whether the user PUSHED to it, and one status:

  fork-remote-pushed     a non-origin remote the user pushed to (the fork)
  fork-remote-unpushed   non-origin remotes exist, none pushed (candidates only, never a fork)
  no-fork-remote         origin is the only remote

A remote that is only fetched from (the upstream a fork was made from) is read-only to the user and
is never a fork. Local evidence of a push to remote R, any one of: a remote-tracking reflog entry of
R written by a push ("update by push"); `remote.pushDefault` or `branch.<b>.pushRemote` naming R; a
local branch whose upstream is a non-protected branch of R (`branch.<b>.remote` = R and
`branch.<b>.merge` not a series or default branch, which is what `git push -u` writes). A bare
`branch.<b>.remote` = R or the presence of other branches on R proves nothing: a branch started
from `R/<series>` tracks R, and a fetch of an upstream also brings its feature and PR refs.

When the status is not `fork-remote-pushed`, `question` is a fact only the operator can answer
(which GitHub account holds their fork); nothing here guesses it. Remote URLs are never printed.

  fork_facts.py --repo PATH [--json]     KEY=VALUE lines (default) or one JSON object
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys

PUSHED = "fork-remote-pushed"
UNPUSHED = "fork-remote-unpushed"
NONE = "no-fork-remote"

SERIES_BRANCH = re.compile(r"^[0-9]+\.0$")
_CONFIG_KEY = re.compile(r"^branch\.(.+)\.(remote|merge|pushremote)$")


def git(repo: str, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _path(url: str) -> list[str]:
    url = url.strip()
    if not url:
        return []
    if "://" in url:
        rest = url.split("://", 1)[1]
        path = rest.split("/", 1)[1] if "/" in rest else ""
    else:
        scp = re.match(r"^[^/:]+:(.+)$", url)
        path = scp.group(1) if scp else ""
    return [p for p in path.split("/") if p]


def owner(url: str) -> str:
    """Owner segment of a remote URL (ssh scp-style, ssh:// or https://); '' when none."""
    parts = _path(url)
    return parts[-2] if len(parts) >= 2 else ""


def repo_name(url: str) -> str:
    """Repository segment of a remote URL, without a `.git` suffix; '' when none."""
    parts = _path(url)
    name = parts[-1] if parts else ""
    return name[:-4] if name.endswith(".git") else name


def pushed_remotes(repo: str, remotes: list[str], protected: set[str]) -> set[str]:
    """Names among `remotes` the user pushes to, from this clone's own records (git READ only)."""
    pushed: set[str] = set()
    # 1. A push rewrites the remote-tracking ref and logs "update by push"; a fetch logs "fetch".
    log = git(repo, "log", "-g", "--glob=refs/remotes/*", "--format=%gD%x09%gs")
    for line in log.splitlines():
        ref, _, subject = line.partition("\t")
        if not subject.startswith("update by push"):
            continue
        for name in remotes:
            if ref.startswith(f"refs/remotes/{name}/"):
                pushed.add(name)
    # 2 and 3. Explicit push targets, and branches that `git push -u` bound to a feature branch.
    track: dict[str, dict[str, str]] = {}
    config = git(repo, "config", "--get-regexp",
                 r"^(remote\.pushdefault|branch\..*\.(remote|merge|pushremote))$")
    for line in config.splitlines():
        key, _, value = line.partition(" ")
        if key == "remote.pushdefault" and value in remotes:
            pushed.add(value)
            continue
        m = _CONFIG_KEY.match(key)
        if m:
            track.setdefault(m.group(1), {})[m.group(2)] = value.strip()
    for cfg in track.values():
        if cfg.get("pushremote") in remotes:
            pushed.add(cfg["pushremote"])
        merge = cfg.get("merge", "")
        short = merge[len("refs/heads/"):] if merge.startswith("refs/heads/") else ""
        if (cfg.get("remote") in remotes and short and short not in protected
                and not SERIES_BRANCH.match(short)):
            pushed.add(cfg["remote"])
    return pushed


def default_branch(repo: str) -> str:
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head[len("origin/"):] if head.startswith("origin/") else ""


def fork_facts(repo: str) -> dict:
    """{repo, origin: {owner, repo} | None, remotes: [{name, owner, repo, pushed}], status, question}.

    `repo` is the root of a clone. `remotes` lists every remote except origin."""
    origin_url = git(repo, "remote", "get-url", "origin")
    origin = ({"owner": owner(origin_url), "repo": repo_name(origin_url)}
              if origin_url else None)
    names = [r for r in git(repo, "remote").split() if r != "origin"]
    default = default_branch(repo)
    pushed = pushed_remotes(repo, names, {default} - {""})
    remotes = []
    for name in names:
        url = git(repo, "remote", "get-url", name)
        remotes.append({"name": name, "owner": owner(url), "repo": repo_name(url),
                        "pushed": name in pushed})
    if any(r["pushed"] for r in remotes):
        status = PUSHED
    elif remotes:
        status = UNPUSHED
    else:
        status = NONE
    question = ""
    if status != PUSHED and origin and origin["owner"] and origin["repo"]:
        question = ("Which GitHub account holds your fork of %s/%s? Answer an account name, "
                    "or none when you use no GitHub fork workflow."
                    % (origin["owner"], origin["repo"]))
    return {"repo": repo, "origin": origin, "remotes": remotes, "status": status,
            "question": question}


def pairs(facts: dict) -> list[tuple[str, str]]:
    """The facts as (NAME, value) pairs, in print order. Empty facts are left out."""
    origin = facts["origin"]
    out = [("FORK_STATUS", facts["status"])]
    if origin and origin["owner"] and origin["repo"]:
        out.append(("FORK_ORIGIN", "%s/%s" % (origin["owner"], origin["repo"])))
    pushed = [r for r in facts["remotes"] if r["pushed"]]
    other = [r for r in facts["remotes"] if not r["pushed"]]
    if pushed:
        out.append(("FORK_PUSHED_REMOTES", ",".join("%s=%s" % (r["name"], r["owner"]) for r in pushed)))
    if other:
        out.append(("FORK_UNPUSHED_REMOTES", ",".join("%s=%s" % (r["name"], r["owner"]) for r in other)))
    if facts["question"]:
        out.append(("FORK_QUESTION", facts["question"]))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Report where a clone's fork lives (read-only).")
    ap.add_argument("--repo", required=True, help="path inside a git clone")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    args = ap.parse_args(argv)
    root = git(args.repo, "rev-parse", "--show-toplevel")
    if not root:
        print("x %s is not inside a git clone" % args.repo, file=sys.stderr)
        return 1
    facts = fork_facts(root)
    if args.json:
        print(json.dumps(facts))
    else:
        for name, value in pairs(facts):
            print("%s=%s" % (name, shlex.quote(value)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
