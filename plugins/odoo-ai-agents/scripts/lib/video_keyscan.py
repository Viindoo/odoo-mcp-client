#!/usr/bin/env python3
"""video_keyscan.py - scan a demo-video output directory for leaked API keys and tokens.

Subcommands (stdlib only; results are KEY=VALUE lines on stdout):
  scan --dir D [--key-env NAME ...]
            Every text file under D is checked for API keys, tokens, bearer headers, long opaque
            runs and the exact value of each named environment variable. Prints
            HIT=<relative path>:<line> per finding (never the key itself), FILES=<n>, HITS=<n>;
            exit 1 when HITS > 0.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".srt", ".vtt", ".csv", ".html", ".log"}
PATTERNS = [
    re.compile(r"sk-\w{20,}"),
    re.compile(r"AIza\w{35}"),
    re.compile(r"ya29\."),
    re.compile(r"(?:ghp_|gho_|github_pat_)\w{20,}"),
    re.compile(r"Bearer \S{20,}"),
    re.compile(r"(?<![\w+/=.:-])(?:[0-9a-fA-F]{40,}|[A-Za-z0-9+_-]{40,}={0,2})(?![\w+/=.:-])"),
]


def _is_text(path):
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return False
    with open(path, "rb") as fh:
        return b"\0" not in fh.read(4096)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--dir", required=True)
    p.add_argument("--key-env", action="append", default=[])
    args = parser.parse_args(argv)

    key_values = [os.environ[n] for n in args.key_env if os.environ.get(n)]
    files = hits = 0
    for root, _dirs, names in sorted(os.walk(args.dir)):
        for name in sorted(names):
            path = os.path.join(root, name)
            if not _is_text(path):
                continue
            files += 1
            rel = os.path.relpath(path, args.dir)
            with open(path, encoding="utf-8", errors="replace") as fh:
                for number, line in enumerate(fh, 1):
                    if any(rx.search(line) for rx in PATTERNS) or any(s in line for s in key_values):
                        hits += 1
                        print("HIT=%s:%d" % (rel, number))
    print("FILES=%d" % files)
    print("HITS=%d" % hits)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
