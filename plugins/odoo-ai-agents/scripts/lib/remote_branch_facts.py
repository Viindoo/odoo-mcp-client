#!/usr/bin/env python3
"""remote_branch_facts.py - does a remote repository have a branch for a series? Asked BEFORE a
clone is proposed (odoo-setup AI-3): the index can list a profile whose repositories never got a
branch for the series, and a clone of a missing branch fails late and loudly.

The one place beside scripts/lib/repo_facts.py that runs git for an agent: a single read of the
remote's refs (`ls-remote --heads`), no checkout, credentials removed from every printed URL.

    python3 remote_branch_facts.py <url> <branch> [<branch> ...] [--timeout 20] [--json]
Prints BRANCH_<name>=present|absent per branch and REMOTE=<url without credentials>;
exit 0 all present, 1 one absent, 2 the remote could not be asked (unreachable, no access).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit


def strip_credentials(url):
    """The URL without user:password@ (an https remote) - an scp-like `git@host:org/repo` keeps its
    user, which is not a credential."""
    parts = urlsplit(url)
    if parts.scheme and parts.netloc and "@" in parts.netloc:
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return url


def remote_heads(url, timeout=20):
    """{branch: sha} of the remote, or None when the remote could not be asked."""
    # the url comes from an index or a manifest: never let it be read as a git option, and never let
    # it name a transport that runs a command (ext::)
    if not url or url.startswith("-") or url.startswith("ext::"):
        return None
    try:
        proc = subprocess.run(["git", "-c", "protocol.ext.allow=never", "ls-remote", "--heads", "--", url],
                              capture_output=True, text=True, timeout=timeout, check=False,
                              env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    heads = {}
    for line in proc.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/"):]] = sha
    return heads


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    heads = remote_heads(args.url, args.timeout)
    shown = strip_credentials(args.url)
    if heads is None:
        if args.json:
            print(json.dumps({"remote": shown, "reachable": False, "branches": {}}))
        else:
            print("REMOTE=%s" % shown)
            print("REACHABLE=0")
        return 2
    result = {b: ("present" if b in heads else "absent") for b in args.branches}
    if args.json:
        print(json.dumps({"remote": shown, "reachable": True, "branches": result}))
    else:
        print("REMOTE=%s" % shown)
        print("REACHABLE=1")
        for b in args.branches:
            print("BRANCH_%s=%s" % (b, result[b]))
    return 0 if all(v == "present" for v in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
