#!/usr/bin/env python3
"""video_keyscan.py - scan a demo-video output directory for leaked API keys and tokens.

Subcommands (stdlib only; results are KEY=VALUE lines on stdout):
  scan --dir D [--key-env NAME ...]
            --key-env is optional and repeatable: without it only the built-in key and token shapes
            are checked; with it the exact value of each named variable is checked too.
            Every text file under D is checked for API keys, tokens, bearer headers, long opaque
            runs and the exact value of each named environment variable. Prints
            HIT=<relative path>:<line> per finding (never the key itself), each followed by
            HIT_CLASS=<class>[,<class>] naming the kind of token that matched (openai-key,
            google-key, oauth-token, github-token, bearer-header, hex-run, opaque-run, env-value),
            then FILES=<n>, HITS=<n>; exit 1 when HITS > 0.

A long run is not a hit when it is readable text: a lowercase word slug (lowercase words, each
letters with at most four trailing digits, joined by `-` or `_`, at least two thirds of the words
carrying no digit at all, such as a label derived from a title) or an MCP tool identifier (`mcp__` followed by letters, digits, `-` and `_`). A run of
letters and digits with no separator, a run of 40 or more hexadecimal digits, a bearer header and
an API-key shape stay hits.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".srt", ".vtt", ".csv", ".html", ".log"}
_RUN_EDGE = r"(?<![\w+/=.:-]){body}(?![\w+/=.:-])"
PATTERNS = [
    ("openai-key", re.compile(r"sk-\w{20,}")),
    ("google-key", re.compile(r"AIza\w{35}")),
    ("oauth-token", re.compile(r"ya29\.")),
    ("github-token", re.compile(r"(?:ghp_|gho_|github_pat_)\w{20,}")),
    ("bearer-header", re.compile(r"Bearer \S{20,}")),
    ("hex-run", re.compile(_RUN_EDGE.format(body=r"[0-9a-fA-F]{40,}"))),
]
OPAQUE_RUN = re.compile(_RUN_EDGE.format(body=r"[A-Za-z0-9+_-]{40,}={0,2}"))
_WORD = r"(?:[a-z]+[0-9]{0,4}|[0-9]{1,4})"
WORD_SLUG = re.compile(r"%s(?:[-_]+%s)+" % (_WORD, _WORD))
HEX_ONLY = re.compile(r"[0-9a-fA-F]+")
MCP_IDENTIFIER = re.compile(r"mcp__[A-Za-z0-9_-]+")


def _is_text(path):
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return False
    with open(path, "rb") as fh:
        return b"\0" not in fh.read(4096)


def _word_slug(token):
    """True for lowercase words joined by `-` or `_`, each word letters with at most four trailing
    digits, at least two thirds of the words carrying no digit at all."""
    if not WORD_SLUG.fullmatch(token):
        return False
    words = [w for w in re.split(r"[-_]+", token) if w]
    plain = sum(1 for w in words if not any(c.isdigit() for c in w))
    return 3 * plain >= 2 * len(words)


def _readable(token):
    """True for a run that is text, not a key: a word slug or an MCP tool identifier."""
    return _word_slug(token) or bool(MCP_IDENTIFIER.fullmatch(token))


def classes_of(line, key_values=()):
    """The classes of token found in `line`, in a fixed order; empty when the line is clean."""
    found = [name for name, rx in PATTERNS if rx.search(line)]
    if any(not (_readable(m.group(0)) or HEX_ONLY.fullmatch(m.group(0))) for m in OPAQUE_RUN.finditer(line)):
        found.append("opaque-run")
    if any(v in line for v in key_values):
        found.append("env-value")
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
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
                    found = classes_of(line, key_values)
                    if found:
                        hits += 1
                        print("HIT=%s:%d" % (rel, number))
                        print("HIT_CLASS=%s" % ",".join(found))
    print("FILES=%d" % files)
    print("HITS=%d" % hits)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
