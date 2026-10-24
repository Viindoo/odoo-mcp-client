#!/usr/bin/env python3
"""doc_coverage_check.py - does the module guide account for every capability of its catalog?

A `full-guide` documents every row of `feature-catalog.jsonl` (skills/odoo-doc-illustration/
references/doc-artifacts.md), or says per row why it does not: the writer stamps each row with
`coverage`: `guide` (a chapter or task covers it), `setup` (the administrator's setup chapter),
or `excluded: <reason the reader would accept>` (an internal technical view, a capability another
module's guide owns). A row with no stamp, or an `excluded` with no reason, is a gap: the guide
returned DONE without deciding about it.

    python3 doc_coverage_check.py <feature-catalog.jsonl> [--scope full-guide|screenshot-doc]
Prints one `GAP=<feature_id> <name>: <why>` line per gap and `COVERED=<n> EXCLUDED=<n> GAPS=<n>`;
exit 0 when no gap, 1 when gaps (full-guide) - a screenshot-doc only reports (exit 0).
"""
from __future__ import annotations

import argparse
import json
import sys

VALID = ("guide", "setup")


def rows(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def gaps(catalog_rows):
    out, covered, excluded = [], 0, 0
    for row in catalog_rows:
        fid, name = row.get("feature_id", "?"), row.get("name", "")
        cov = row.get("coverage")
        if cov in VALID:
            covered += 1
        elif isinstance(cov, str) and cov.startswith("excluded:") and cov.split(":", 1)[1].strip():
            excluded += 1
        elif cov is None:
            out.append((fid, name, "no coverage stamp - the guide never decided about it"))
        else:
            out.append((fid, name, "coverage %r is neither guide, setup nor excluded: <reason>" % (cov,)))
    return out, covered, excluded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog")
    parser.add_argument("--scope", default="full-guide", choices=("full-guide", "screenshot-doc"))
    args = parser.parse_args(argv)
    found, covered, excluded = gaps(list(rows(args.catalog)))
    for fid, name, why in found:
        print("GAP=%s %s: %s" % (fid, name, why))
    print("COVERED=%d EXCLUDED=%d GAPS=%d" % (covered, excluded, len(found)))
    return 1 if (found and args.scope == "full-guide") else 0


if __name__ == "__main__":
    sys.exit(main())
