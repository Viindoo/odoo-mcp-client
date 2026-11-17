#!/usr/bin/env python3
"""auto_mode_facts.py - derive the auto-mode entries of setup step 34 from this machine.

Every value is read at run time: the trusted roots from the instance catalog (the parent
directory of each addons_path entry, plus the state root's projects directory), the
organization, fork owner and protected branches from the git remotes and branches of the
repositories holding those addons. Git is only READ (remote URLs, the remote's HEAD symbolic
ref, branch names, local branch config, remote-tracking reflogs). No network, no `gh`. stdlib only.

A fork owner is the owner of a non-origin remote the user PUSHES to; the push-evidence rule
and the fork status of each repository live in fork_facts.py (one home, shared with setup steps
60 and the instance repo scan).

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
  newer <settings> <dotted.array.path>
                     Exit 0 when the array holds an entry tagged by a NEWER plugin version
                     than this one (that version owns the array: this version leaves it alone);
                     exit 1 otherwise.

Ownership across plugin versions. Sessions of several plugin versions share one settings file and
each converges it at start. An entry is tagged `odoo-ai-agents@<version>: ` with the version of the
plugin that wrote it, so the version that owns an array is the newest one that wrote to it: a
version writes (pruning every entry of an older or untagged tag) only into an array that holds no
entry of a newer version, and `check` calls such an array in sync. Releases from before the version
tag prune and write only entries tagged `odoo-ai-agents: ` (no `@`), so a versioned entry is
invisible to them and survives their start.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fork_facts  # noqa: E402  (git reader, owner parser, push evidence, fork status)

PLUGIN_ROOT = os.path.dirname(os.path.dirname(HERE))
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# Every tag this plugin ever wrote: `odoo-ai-agents: ` (before versions) and `odoo-ai-agents@<v>: `.
TAG_PATTERN = r"^odoo-ai-agents(@[0-9]+\.[0-9]+\.[0-9]+)?: "
_TAG_RE = re.compile(TAG_PATTERN)
_UNVERSIONED = (-1, -1, -1)


def plugin_version() -> str:
    """The version of this plugin (its plugin.json); "0.0.0" when it cannot be read."""
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version")
    except (OSError, ValueError, AttributeError):
        return "0.0.0"
    return version if isinstance(version, str) and _VERSION.match(version) else "0.0.0"


def _tuple(version: str) -> tuple:
    return tuple(int(p) for p in version.split("."))


TAG = f"odoo-ai-agents@{plugin_version()}: "
# The shape of every permissions.ask rule this step writes (and so the only shape it prunes).
ASK_PATTERN = r"^Bash\(git push (--force\* )?\* (--delete )?[A-Za-z0-9._/-]+\)$"
_BRANCH_OK = re.compile(r"^[A-Za-z0-9._/-]+$")
_SERIES_BRANCH = fork_facts.SERIES_BRANCH


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


_git = fork_facts.git
_owner = fork_facts.owner


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


def _catalog_entries(catalog: str) -> tuple[list[str], int]:
    """(addons_path entries, rows with an addons_path) of the catalog file."""
    import instances_io

    entries: list[str] = []
    rows = 0
    if os.path.isfile(catalog):
        for item in instances_io.load_instances(catalog):
            paths = instances_io.addons_path_list(item)
            if paths:
                rows += 1
            entries.extend(p.rstrip("/") for p in paths if p.strip())
    return _dedup(entries), rows


def catalog_repos(catalog: str = "") -> list[str]:
    """The git repositories holding the addons of the catalog (default: this machine's catalog)."""
    entries, _ = _catalog_entries(catalog or _catalog_path())
    return _dedup([_git_root(e) for e in entries if os.path.isdir(e)])


def derive() -> dict:
    """Facts of this machine. Keys: catalog, rows, roots, repos, orgs, forks, branches, fork_status,
    fork (the fork_facts summary of those repositories, grouped by origin)."""
    catalog = _catalog_path()
    entries, rows = _catalog_entries(catalog)
    roots = _dedup([os.path.dirname(e) for e in entries])
    roots = _dedup(roots + ([os.path.join(_home(), "projects")] if entries else []))

    repos = _dedup([_git_root(e) for e in entries if os.path.isdir(e)])
    orgs: list[str] = []
    branches: list[str] = []
    fork_status: list[dict] = []
    for repo in repos:
        found = fork_facts.fork_facts(repo)
        fork_status.append(found)
        default = fork_facts.default_branch(repo)
        if found["origin"]:
            orgs.append(found["origin"]["owner"])
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
    forks = fork_facts.known_owners(fork_status)
    branches = [b for b in _dedup(branches) if _BRANCH_OK.match(b)]
    return {"catalog": catalog, "rows": rows, "roots": roots, "repos": repos,
            "orgs": orgs, "forks": forks, "branches": branches, "fork_status": fork_status,
            "fork": fork_facts.summarize(fork_status)}


def _join(values) -> str:
    return ", ".join(values)


def build_entries(facts: dict) -> dict:
    roots, orgs, forks, branches = facts["roots"], facts["orgs"], facts["forks"], facts["branches"]
    org_globs = _join(f"{o}/*" for o in orgs) if orgs else "the upstream organization"
    fork_text = f" ({_join(forks)})" if forks else ""
    allow = [
        TAG + "Editing, creating, moving and deleting any file inside the trusted development roots "
        f"({_join(roots)}) and their git worktrees is routine Odoo development, including data, "
        "security and test files. A deliberate break-check is expected work, not a weakening of "
        "security: it temporarily alters an access rule, record rule, group, guard or data record "
        "in a file to prove that a test fails when the rule it guards is broken, stays "
        "uncommitted, and is restored or rebuilt afterwards.",
        TAG + "Routine git on the repositories inside the trusted roots is allowed: commit, merge, "
        "rebase, cherry-pick (including --continue, --skip and --abort after a conflict was "
        f"resolved on disk), worktree add and remove, tags, pushing branches to the fork{fork_text} "
        "including --force-with-lease, and creating, updating and reviewing pull requests and "
        f"issues. The exceptions are pushing to or deleting a protected branch of {org_globs} and "
        "merging a pull request without the user's confirmation.",
        TAG + "Building, running, testing, parking and dropping local Odoo instances and their "
        "localhost PostgreSQL databases (odoo-bin and the odoo-local MCP tools) is routine, and so "
        "is giving back a lease the agent's own run acquired: releasing or parking it stops its "
        "server and, for a throwaway database, drops it.",
        TAG + "Exposing a leased test instance through a temporary public https address (the "
        "instance_expose and instance_unexpose odoo-local tools, a Cloudflare Quick Tunnel to the "
        "instance's own localhost port) is routine: an instance built from code holds nothing to "
        "secure, a third party must reach it for an OAuth redirect or a webhook, and a person may "
        "follow the session from another device. The address ends with the instance's server.",
        TAG + f"Destructive steps of development inside the trusted roots ({_join(roots)}) are "
        "intended: deleting or rewriting code, tests and modules as part of the task, "
        "`git checkout <ref> -- <paths>`, `git restore`, `git reset --hard <sha recorded earlier "
        "in the same session>`, `git clean` and `git worktree remove --force` on worktrees the "
        "agent's own run created, and deleting the local backup branches, backup tags and "
        "temporary files that run created. Discarding uncommitted work the agent did not create "
        "stays blocked.",
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
    return {"tag": TAG, "tag_pattern": TAG_PATTERN,
            "autoMode": {"allow": allow, "soft_deny": soft_deny, "environment": environment},
            "ask": ask, "ask_pattern": ASK_PATTERN}


def propose_text(facts: dict, entries: dict) -> str:
    lines = [f"catalog: {facts['catalog']} ({facts['rows']} row(s) with an addons_path)"]
    lines += [f"trusted root: {r}" for r in facts["roots"]]
    lines += [f"git repository: {r}" for r in facts["repos"]]
    lines += [f"organization (origin owner): {o}" for o in facts["orgs"]]
    lines += [f"fork owner (remote the user pushes to): {o}" for o in facts["forks"]]
    lines += [f"protected branch: {b}" for b in facts["branches"]]
    if facts["fork"]["question"]:
        lines.append("FORK_QUESTION=" + shlex.quote(facts["fork"]["question"]))
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


def entry_version(entry) -> tuple | None:
    """The version tuple an entry's tag names (untagged-version tag: below every version), or None
    for an entry that is not this plugin's."""
    if not isinstance(entry, str):
        return None
    found = _TAG_RE.match(entry)
    if not found:
        return None
    return _tuple(found.group(1)[1:]) if found.group(1) else _UNVERSIONED


def owned_by_newer(data: dict, dotted: str) -> bool:
    """True when the array holds an entry written by a plugin version newer than this one."""
    mine = _tuple(plugin_version())
    return any((v := entry_version(e)) is not None and v > mine for e in _array(data, dotted))


def in_sync(data: dict, entries: dict) -> bool:
    ask_re = re.compile(ASK_PATTERN)
    for key, want in entries["autoMode"].items():
        if owned_by_newer(data, f"autoMode.{key}"):
            continue
        have = _array(data, f"autoMode.{key}")
        if "$defaults" not in have:
            return False
        if any(isinstance(e, str) and entry_version(e) is not None and e not in want for e in have):
            return False
        if any(w not in have for w in want):
            return False
    if owned_by_newer(data, "autoMode.soft_deny"):
        return True
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
        return 0 if any(entry_version(e) is not None for e in env) else 1
    if cmd == "newer":
        data = _load(argv[1]) if len(argv) > 2 else None
        return 0 if data is not None and owned_by_newer(data, argv[2]) else 1
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
