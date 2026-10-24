#!/usr/bin/env python3
"""registry_review.py - read the WHOLE instance registry and name what is wrong with it, so the
setup command shows the operator every anomaly as a plan line with its fix, instead of each step
stumbling on one of them later (or working around it in silence).

    registry_review.py review <instances.toml> [--json]
        One line per finding, then FINDINGS=<n>:
          FINDING=DUPLICATE_ROW   row=<key> detail=<n>th row with this key fix=<...>
          FINDING=SHARED_VENV     rows=<key key> detail=<venv dir> fix=<...>
          FINDING=DEAD_ADDONS_PATH row=<key> detail=<missing dir> fix=<...>
          FINDING=DEAD_PYTHON     row=<key> detail=<python> fix=<...>
          FINDING=NO_PYTHON       row=<key> detail=source row without a python fix=<...>
          FINDING=STALE_COMMENT   detail=<comment line> fix=<...>
        Exit 0 always (a review is an answer, not a gate); `--json` prints the list of objects.
    registry_review.py dedupe <instances.toml>
        Drops every later [[instance]] block whose key repeats an earlier one (the first row is
        the one every writer already selects), after a backup, atomically. Prints
        DROPPED=<key> per block removed and KEPT=<n>. The only write this script does.

A row's key is `instance_key`, else `series:profile`, else `series` (instances_io.instance_key_of).
Stdlib only. Tests: tests/test_registry_review.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402
import instances_io  # noqa: E402
import venv_facts  # noqa: E402

FIX = {
    "DUPLICATE_ROW": "registry_review.py dedupe keeps the first row and drops this one",
    "SHARED_VENV": "one venv per profile: /odoo-ai-agents:odoo-setup venv --version <X.Y> --profile <P> gives each row its own",
    "DEAD_ADDONS_PATH": "re-declare the instance (/odoo-ai-agents:odoo-setup instance updates the row) or clone the repository back",
    "DEAD_PYTHON": "/odoo-ai-agents:odoo-setup venv --version <X.Y> --profile <P> rebuilds it",
    "NO_PYTHON": "/odoo-ai-agents:odoo-setup instance builds the environment for the row",
    "STALE_COMMENT": "edit the comment or leave it; nothing reads it",
}


def review(path):
    """[{kind, row|rows, detail, fix}] for the registry at `path`; [] when it does not exist."""
    try:
        items = instances_io.load_instances(path)
    except FileNotFoundError:
        return []
    findings = []
    seen = {}
    for row in items:
        key = instances_io.instance_key_of(row)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            findings.append({"kind": "DUPLICATE_ROW", "row": key,
                             "detail": "%s rows carry this key; writers see only the first" % seen[key]})
    by_venv = {}
    for row in items:
        key = instances_io.instance_key_of(row)
        python = str(row.get("python") or "").strip()
        run_mode = str(row.get("run_mode") or "source").strip()
        if python:
            venv_dir = venv_facts.venv_dir_of(python)
            if venv_dir:
                by_venv.setdefault(venv_dir, []).append(key)
            if not os.access(python, os.X_OK):
                findings.append({"kind": "DEAD_PYTHON", "row": key, "detail": python})
        elif run_mode == "source":
            findings.append({"kind": "NO_PYTHON", "row": key, "detail": "source row without a python"})
        for entry in instances_io.addons_path_list(row):
            if entry and not os.path.isdir(entry):
                findings.append({"kind": "DEAD_ADDONS_PATH", "row": key, "detail": entry})
    for venv_dir, keys in sorted(by_venv.items()):
        if len(keys) > 1:
            findings.append({"kind": "SHARED_VENV", "rows": keys, "detail": venv_dir})
    for line in venv_facts.stale_comments(path):
        findings.append({"kind": "STALE_COMMENT", "detail": line})
    for f in findings:
        f["fix"] = FIX[f["kind"]]
    return findings


def _blocks(lines):
    """[(start, end, key)] of every [[instance]] block, by line index (end exclusive)."""
    starts = [i for i, line in enumerate(lines) if line.strip() == "[[instance]]"]
    out = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        keys = {}
        for line in lines[start + 1:end]:
            m = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*?)\s*(#.*)?$", line)
            if m and m.group(1) in ("series", "profile", "instance_key"):
                keys[m.group(1)] = m.group(2).strip().strip('"').strip("'")
        key = keys.get("instance_key") or (
            "%s:%s" % (keys.get("series", ""), keys["profile"]) if keys.get("profile") else keys.get("series", ""))
        out.append((start, end, key))
    return out


def dedupe(path):
    """Drop later blocks whose key repeats an earlier one. Returns ([dropped keys], kept count)."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    seen, drop = set(), []
    for start, end, key in _blocks(lines):
        if key in seen:
            drop.append((start, end, key))
        else:
            seen.add(key)
    if not drop:
        return [], len(seen)
    keep = []
    cut = [(s, e) for s, e, _ in drop]
    for i, line in enumerate(lines):
        if not any(s <= i < e for s, e in cut):
            keep.append(line)
    with config_merge.locked_target(path):
        config_merge._backup(path)
        config_merge._atomic_replace(path, "".join(keep))
    return [k for _, _, k in drop], len(seen)


def cmd_review(args):
    findings = review(args.path)
    if args.as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
        return 0
    for f in findings:
        who = ("rows=%s" % " ".join(f["rows"])) if "rows" in f else ("row=%s" % f["row"] if "row" in f else "")
        print("FINDING=%s %s detail=%s fix=%s" % (f["kind"], who, f["detail"], f["fix"]))
    print("FINDINGS=%d" % len(findings))
    return 0


def cmd_dedupe(args):
    if not os.path.exists(args.path):
        print("KEPT=0")
        return 0
    dropped, kept = dedupe(args.path)
    for key in dropped:
        print("DROPPED=%s" % key)
    print("KEPT=%d" % kept)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("review")
    p.add_argument("path")
    p.add_argument("--json", action="store_true", dest="as_json")
    p = sub.add_parser("dedupe")
    p.add_argument("path")
    args = parser.parse_args(argv)
    return {"review": cmd_review, "dedupe": cmd_dedupe}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
