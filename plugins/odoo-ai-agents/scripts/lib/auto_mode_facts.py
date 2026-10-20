#!/usr/bin/env python3
"""auto_mode_facts.py - derive the auto-mode entries of setup step 34 from this machine.

Every value is read at run time: the trusted roots from the instance catalog (the parent
directory of each addons_path entry, plus the state root's projects directory), the
organization, fork owner and protected branches from the git remotes and branches of the
repositories holding those addons. Git is only READ (remote URLs, the remote's HEAD symbolic
ref, branch names, local branch config, remote-tracking reflogs). No network, no `gh`. stdlib only.

A fork owner is the owner of a non-origin remote the user PUSHES to. A remote that is only
fetched from (the upstream a fork was made from) is read-only to the user and is not a fork.
Local evidence of a push to remote R, any one of: a remote-tracking reflog entry of R written by
a push ("update by push"); `remote.pushDefault` or `branch.<b>.pushRemote` naming R; a local
branch whose upstream is a non-protected branch of R (`branch.<b>.remote` = R and
`branch.<b>.merge` not a series or default branch, which is what `git push -u` writes). A bare
`branch.<b>.remote` = R or the presence of other branches on R proves nothing: a branch started
from `R/<series>` tracks R, and a fetch of an upstream also brings its feature and PR refs.

Subcommands (settings/catalog paths come from the same environment as the setup steps:
CLAUDE_SETTINGS, ODOO_AI_HOME, ODOO_AI_INSTANCES):

  propose            Human-readable proposal; exit 0, or exit 1 naming what is missing.
  entries            JSON of exactly what `apply` writes:
                     {"tag", "autoMode": {allow, soft_deny, environment}, "ask": [...],
                      "ask_pattern"}. Exit 1 when nothing can be derived.
  check <settings>   Exit 0 when every entry is present and no stale entry of this plugin's
                     tag remains (also 0 when nothing can be derived); exit 1 otherwise.
  marker <settings>  Exit 0 when the settings carry at least one tagged autoMode.environment
                     entry (the user approved this step on this machine); exit 1 otherwise.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TAG = "odoo-ai-agents: "
# The shape of every permissions.ask rule this step writes (and so the only shape it prunes).
ASK_PATTERN = r"^Bash\(git push (--force\* )?\* (--delete )?[A-Za-z0-9._/-]+\)$"
_BRANCH_OK = re.compile(r"^[A-Za-z0-9._/-]+$")
_SERIES_BRANCH = re.compile(r"^[0-9]+\.0$")


def _home() -> str:
    home = os.environ.get("ODOO_AI_HOME") or os.path.join(os.environ.get("HOME", ""), ".odoo-ai")
    return home.rstrip("/") or "/"


def _catalog_path() -> str:
    explicit = os.environ.get("ODOO_AI_INSTANCES")
    if explicit:
        return explicit
    global_path = os.path.join(_home(), "instances.toml")

    def has_rows(p: str) -> bool:
        try:
            with open(p, encoding="utf-8") as fh:
                return any(line.startswith("[[instance]]") for line in fh)
        except OSError:
            return False

    project = os.path.join(os.getcwd(), ".odoo-ai", "instances.toml")
    if not has_rows(global_path) and has_rows(project):
        return project
    return global_path


def _git(repo: str, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _owner(url: str) -> str:
    """Owner segment of a remote URL (ssh scp-style, ssh:// or https://); '' when none."""
    url = url.strip()
    if not url:
        return ""
    if "://" in url:
        rest = url.split("://", 1)[1]
        path = rest.split("/", 1)[1] if "/" in rest else ""
    else:
        scp = re.match(r"^[^/:]+:(.+)$", url)
        path = scp.group(1) if scp else ""
    parts = [p for p in path.split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


def _git_root(path: str) -> str:
    cur = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
        cur = parent


def _dedup(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


_CONFIG_KEY = re.compile(r"^branch\.(.+)\.(remote|merge|pushremote)$")


def _pushed_remotes(repo: str, remotes: list[str], protected: set[str]) -> set[str]:
    """Names among `remotes` the user pushes to, from this clone's own records (git READ only)."""
    pushed: set[str] = set()
    # 1. A push rewrites the remote-tracking ref and logs "update by push"; a fetch logs "fetch".
    log = _git(repo, "log", "-g", "--glob=refs/remotes/*", "--format=%gD%x09%gs")
    for line in log.splitlines():
        ref, _, subject = line.partition("\t")
        if not subject.startswith("update by push"):
            continue
        for name in remotes:
            if ref.startswith(f"refs/remotes/{name}/"):
                pushed.add(name)
    # 2 and 3. Explicit push targets, and branches that `git push -u` bound to a feature branch.
    track: dict[str, dict[str, str]] = {}
    config = _git(repo, "config", "--get-regexp",
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
                and not _SERIES_BRANCH.match(short)):
            pushed.add(cfg["remote"])
    return pushed


def derive() -> dict:
    """Facts of this machine. Keys: catalog, rows, roots, repos, orgs, forks, branches."""
    import instances_io

    catalog = _catalog_path()
    entries: list[str] = []
    rows = 0
    if os.path.isfile(catalog):
        for item in instances_io.load_instances(catalog):
            paths = instances_io.addons_path_list(item)
            if paths:
                rows += 1
            entries.extend(p.rstrip("/") for p in paths if p.strip())
    entries = _dedup(entries)
    roots = _dedup([os.path.dirname(e) for e in entries])
    roots = _dedup(roots + ([os.path.join(_home(), "projects")] if entries else []))

    repos = _dedup([_git_root(e) for e in entries if os.path.isdir(e)])
    orgs: list[str] = []
    forks: list[str] = []
    branches: list[str] = []
    for repo in repos:
        remotes = _git(repo, "remote").split()
        head = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        default = head[len("origin/"):] if head.startswith("origin/") else ""
        pushed = _pushed_remotes(repo, [r for r in remotes if r != "origin"], {default} - {""})
        for name in remotes:
            owner = _owner(_git(repo, "remote", "get-url", name))
            if name == "origin":
                orgs.append(owner)
            elif name in pushed:
                forks.append(owner)
        if default:
            branches.append(default)
        refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").splitlines()
        for ref in refs:
            if ref.startswith("refs/heads/"):
                short = ref[len("refs/heads/"):]
            elif ref.startswith("refs/remotes/"):
                short = ref[len("refs/remotes/"):].split("/", 1)[-1]
            else:
                continue
            if _SERIES_BRANCH.match(short):
                branches.append(short)
    orgs = _dedup(orgs)
    forks = [f for f in _dedup(forks) if f not in orgs]
    branches = [b for b in _dedup(branches) if _BRANCH_OK.match(b)]
    return {"catalog": catalog, "rows": rows, "roots": roots, "repos": repos,
            "orgs": orgs, "forks": forks, "branches": branches}


def _join(values) -> str:
    return ", ".join(values)


def build_entries(facts: dict) -> dict:
    roots, orgs, forks, branches = facts["roots"], facts["orgs"], facts["forks"], facts["branches"]
    org_globs = _join(f"{o}/*" for o in orgs) if orgs else "the upstream organization"
    fork_text = f" ({_join(forks)})" if forks else ""
    allow = [
        TAG + f"Editing, creating, moving and deleting files inside the trusted development roots "
        f"({_join(roots)}) is routine Odoo development. This includes temporarily removing or "
        "altering an access check, record rule, guard or data record to prove that a test fails "
        "when the rule it guards is broken (a break-check), as long as the change stays "
        "uncommitted and is restored or rebuilt afterwards.",
        TAG + "Routine git on the repositories inside the trusted roots is allowed: commit, merge, "
        "rebase, cherry-pick (including --continue, --skip and --abort after a conflict was "
        f"resolved on disk), worktree add and remove, tags, pushing branches to the fork{fork_text} "
        "including --force-with-lease, and creating, updating and reviewing pull requests and "
        f"issues. The exceptions are pushing to or deleting a protected branch of {org_globs} and "
        "merging a pull request without the user's confirmation.",
        TAG + "Building, running, testing, parking and dropping local Odoo instances and their "
        "localhost PostgreSQL databases (odoo-bin and the odoo-local MCP tools) is routine.",
        TAG + f"Destructive steps of development inside the trusted roots ({_join(roots)}) are "
        "intended: deleting or rewriting code, tests and modules as part of the task, "
        "`git checkout <ref> -- <paths>`, `git restore`, `git reset --hard <sha recorded earlier "
        "in the same session>`, `git clean` and `git worktree remove --force` on worktrees the "
        "agent's own run created. Discarding uncommitted work the agent did not create stays blocked.",
    ]
    soft_deny = []
    if branches:
        soft_deny.append(
            TAG + f"Pushing (plain or force) directly to a protected branch ({_join(branches)}) of "
            f"{org_globs} without a pull request is not allowed.")
        soft_deny.append(
            TAG + f"Deleting a protected branch ({_join(branches)}) of {org_globs} is not allowed.")
    soft_deny.append(
        TAG + f"Merging a pull request of {org_globs} without the user's explicit confirmation "
        "is not allowed.")
    environment = [
        TAG + "Purpose of this machine: Odoo module development, forward-ports, upgrades and "
        "local test instances.",
        TAG + f"Trusted development roots: {_join(roots)}.",
    ]
    if orgs:
        environment.append(TAG + f"Organization that owns the upstream repositories: {_join(orgs)}.")
    if forks:
        environment.append(TAG + f"Fork owner the agent pushes feature branches to: {_join(forks)}.")
    if branches:
        environment.append(TAG + f"Protected branches: {_join(branches)}.")
    ask = []
    for b in branches:
        ask += [f"Bash(git push * {b})", f"Bash(git push --force* * {b})",
                f"Bash(git push * --delete {b})"]
    return {"tag": TAG, "autoMode": {"allow": allow, "soft_deny": soft_deny,
                                      "environment": environment},
            "ask": ask, "ask_pattern": ASK_PATTERN}


def propose_text(facts: dict, entries: dict) -> str:
    lines = [f"catalog: {facts['catalog']} ({facts['rows']} row(s) with an addons_path)"]
    lines += [f"trusted root: {r}" for r in facts["roots"]]
    lines += [f"git repository: {r}" for r in facts["repos"]]
    lines += [f"organization (origin owner): {o}" for o in facts["orgs"]]
    lines += [f"fork owner (remote the user pushes to): {o}" for o in facts["forks"]]
    lines += [f"protected branch: {b}" for b in facts["branches"]]
    if not facts["orgs"]:
        lines.append("note: no git remote named origin found - organization-scoped wording is generic")
    if not facts["branches"]:
        lines.append("note: no protected branch found - no push guard rules are written")
    lines.append("will write (settings, user scope), each entry starts with the tag "
                 f"'{TAG}' and the array starts with \"$defaults\":")
    for key, arr in entries["autoMode"].items():
        lines += [f"  autoMode.{key}: {e}" for e in arr]
    lines += [f"  permissions.ask: {e}" for e in entries["ask"]]
    return "\n".join(lines)


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _array(data: dict, dotted: str) -> list:
    node = data
    for key in dotted.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, list) else []


def in_sync(data: dict, entries: dict) -> bool:
    ask_re = re.compile(ASK_PATTERN)
    for key, want in entries["autoMode"].items():
        have = _array(data, f"autoMode.{key}")
        if "$defaults" not in have:
            return False
        if any(not isinstance(e, str) or e not in want for e in have if isinstance(e, str) and e.startswith(TAG)):
            return False
        if any(w not in have for w in want):
            return False
    have_ask = [e for e in _array(data, "permissions.ask") if isinstance(e, str)]
    if any(w not in have_ask for w in entries["ask"]):
        return False
    if any(ask_re.match(e) and e not in entries["ask"] for e in have_ask):
        return False
    return True


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "marker":
        data = _load(argv[1]) if len(argv) > 1 else None
        env = _array(data, "autoMode.environment") if data else []
        return 0 if any(isinstance(e, str) and e.startswith(TAG) for e in env) else 1
    facts = derive()
    if not facts["roots"]:
        if cmd == "check":
            return 0
        print("nothing to derive: the instance catalog "
              f"({facts['catalog']}) has no row with an addons_path. Declare an instance first "
              "(/odoo-ai-agents:odoo-setup instance), then re-run.")
        return 1
    entries = build_entries(facts)
    if cmd == "propose":
        print(propose_text(facts, entries))
        return 0
    if cmd == "entries":
        print(json.dumps(entries))
        return 0
    if cmd == "check":
        data = _load(argv[1]) if len(argv) > 1 else None
        if data is None:
            return 1
        return 0 if in_sync(data, entries) else 1
    print(f"unknown subcommand {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
