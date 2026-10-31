#!/usr/bin/env python3
"""video_budget.py - AI spend estimate, ledger and key hygiene for narrated demo videos.

Subcommands (stdlib only; results are KEY=VALUE lines on stdout):
  estimate --storyboard SB.json
            ESTIMATE_REQUESTS, ESTIMATE_TOKENS from the storyboard `ai` block; `AI=none` and zeros
            when the block is absent.
  log       --ledger L.jsonl --kind trial|take --scene ID --lang LOCALE --requests N --tokens N
            Appends one ledger line; prints LOGGED=1, TOTAL_REQUESTS, TOTAL_TOKENS.
  check     --ledger L.jsonl --storyboard SB.json [--margin 0.25]
            SPENT_REQUESTS, SPENT_TOKENS, ESTIMATE_TOKENS, MARGIN; exit 4 with OVER=tokens|requests
            when a total exceeds the estimate by more than the margin.
  keys      --storyboard SB.json
            The demo key must be dedicated and its variable set; prints KEY_ENV=<NAME> only, never
            the value. Exit 1 with ERROR=... otherwise.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _estimate(sb):
    """Return ``(requests, tokens, has_ai)`` planned by a storyboard."""
    ai = sb.get("ai")
    if not isinstance(ai, dict):
        return 0, 0, False
    scenes = len(sb.get("scenes") or [])
    langs = len(sb.get("languages") or [])
    takes = int(ai.get("takes", 1))
    trials = int(ai.get("trials_k", 0))
    per_scene = int(ai.get("requests_per_scene", 0))
    requests = scenes * per_scene * takes * langs + scenes * trials * langs
    return requests, requests * int(ai.get("tokens_per_request", 0)), True


def _totals(ledger):
    requests = tokens = 0
    if os.path.isfile(ledger):
        with open(ledger, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    requests += int(row.get("requests", 0))
                    tokens += int(row.get("tokens", 0))
    return requests, tokens


def cmd_estimate(args):
    requests, tokens, has_ai = _estimate(_load(args.storyboard))
    if not has_ai:
        print("AI=none")
    print("ESTIMATE_REQUESTS=%d" % requests)
    print("ESTIMATE_TOKENS=%d" % tokens)
    return 0


def cmd_log(args):
    row = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "kind": args.kind, "scene": args.scene, "lang": args.lang,
           "requests": args.requests, "tokens": args.tokens}
    with open(args.ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    requests, tokens = _totals(args.ledger)
    print("LOGGED=1")
    print("TOTAL_REQUESTS=%d" % requests)
    print("TOTAL_TOKENS=%d" % tokens)
    return 0


def cmd_check(args):
    est_requests, est_tokens, _ = _estimate(_load(args.storyboard))
    requests, tokens = _totals(args.ledger)
    print("SPENT_REQUESTS=%d" % requests)
    print("SPENT_TOKENS=%d" % tokens)
    print("ESTIMATE_TOKENS=%d" % est_tokens)
    print("MARGIN=%s" % args.margin)
    factor = 1 + args.margin
    if tokens > est_tokens * factor:
        print("OVER=tokens")
        return 4
    if requests > est_requests * factor:
        print("OVER=requests")
        return 4
    return 0


def cmd_keys(args):
    ai = _load(args.storyboard).get("ai")
    if not isinstance(ai, dict):
        print("KEY=none")
        return 0
    if ai.get("key_scope") != "dedicated":
        print("ERROR=shared key")
        return 1
    name = ai.get("key_env") or ""
    if not name or not os.environ.get(name):
        print("ERROR=key_env %s unset" % name)
        return 1
    print("KEY_ENV=%s" % name)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("estimate")
    p.add_argument("--storyboard", required=True)
    p = sub.add_parser("log")
    p.add_argument("--ledger", required=True)
    p.add_argument("--kind", required=True, choices=["trial", "take"])
    p.add_argument("--scene", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--requests", required=True, type=int)
    p.add_argument("--tokens", required=True, type=int)
    p = sub.add_parser("check")
    p.add_argument("--ledger", required=True)
    p.add_argument("--storyboard", required=True)
    p.add_argument("--margin", type=float, default=0.25)
    p = sub.add_parser("keys")
    p.add_argument("--storyboard", required=True)
    args = parser.parse_args(argv)
    return {"estimate": cmd_estimate, "log": cmd_log, "check": cmd_check, "keys": cmd_keys}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
