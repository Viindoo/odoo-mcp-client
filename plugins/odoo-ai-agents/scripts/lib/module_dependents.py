#!/usr/bin/env python3
"""module_dependents.py - the modules that extend one module: every addon whose manifest `depends`
names it, read from the addons directories of the instance (the trees as they are, never memory).

    module_dependents.py <module> --addons-path DIR[,DIR...] [--author NAME] [--json]

Prints one line per dependent, sorted by display name:
    DEPENDENT=<technical_name> name=<manifest name> author=<manifest author> installable=true|false
      application=true|false summary=<manifest summary> path=<dir>
or, with --json, a JSON list of objects with those keys plus `depends` and `website`.
`--author NAME` keeps only the modules whose manifest `author` equals NAME (case-insensitive,
surrounding spaces ignored) - the vendor's own extensions, the ones a store page may upsell.
A manifest that does not parse is reported on stderr (`x <path>: <reason>`) and skipped.
Exit 0 (an empty result is a valid answer), 2 on a usage error.

Who uses it: odoo-marketer (MODE landing, the EXTENSIONS section of the App Store page) and anyone
answering "what builds on this module". Stdlib only. Tests: tests/test_module_dependents.py.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

MANIFESTS = ("__manifest__.py", "__openerp__.py")


def read_manifest(path):
    """The manifest dict, or None (with the reason) when it cannot be read as a Python literal."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = ast.literal_eval(fh.read())
    except (OSError, ValueError, SyntaxError) as exc:
        return None, "%s" % exc
    if not isinstance(data, dict):
        return None, "not a dict"
    return data, ""


def iter_manifests(addons_dirs):
    """(module technical name, module dir, manifest path) for every addon under the directories."""
    seen = set()
    for base in addons_dirs:
        base = os.path.abspath(os.path.expanduser(base.strip()))
        if not base or base in seen or not os.path.isdir(base):
            continue
        seen.add(base)
        for name in sorted(os.listdir(base)):
            module_dir = os.path.join(base, name)
            if not os.path.isdir(module_dir):
                continue
            for manifest in MANIFESTS:
                path = os.path.join(module_dir, manifest)
                if os.path.isfile(path):
                    yield name, module_dir, path
                    break


def _flag(value, default):
    return bool(value) if value is not None else default


def dependents(module, addons_dirs, author=None, errors=None):
    """[{technical_name, name, author, installable, application, summary, website, depends, path}]
    for every addon whose `depends` names `module`, optionally only those of one author."""
    wanted = (author or "").strip().lower()
    out = []
    for name, module_dir, path in iter_manifests(addons_dirs):
        data, reason = read_manifest(path)
        if data is None:
            if errors is not None:
                errors.append("%s: %s" % (path, reason))
            continue
        depends = [str(d) for d in (data.get("depends") or [])]
        if module not in depends or name == module:
            continue
        mod_author = str(data.get("author") or "").strip()
        if wanted and mod_author.lower() != wanted:
            continue
        out.append({
            "technical_name": name,
            "name": str(data.get("name") or name).strip(),
            "author": mod_author,
            "installable": _flag(data.get("installable"), True),
            "application": _flag(data.get("application"), False),
            "summary": " ".join(str(data.get("summary") or "").split()),
            "website": str(data.get("website") or "").strip(),
            "depends": depends,
            "path": module_dir,
        })
    out.sort(key=lambda row: (row["name"].lower(), row["technical_name"]))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module")
    parser.add_argument("--addons-path", required=True, dest="addons_path",
                        help="comma-separated addons directories (Odoo's --addons-path form)")
    parser.add_argument("--author", default="")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    dirs = [d for d in args.addons_path.split(",") if d.strip()]
    if not dirs:
        print("x --addons-path names no directory", file=sys.stderr)
        return 2
    errors = []
    rows = dependents(args.module, dirs, args.author, errors)
    for err in errors:
        print("x %s" % err, file=sys.stderr)
    if args.as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        print("DEPENDENT=%s name=%s author=%s installable=%s application=%s summary=%s path=%s" % (
            row["technical_name"], row["name"], row["author"], str(row["installable"]).lower(),
            str(row["application"]).lower(), row["summary"], row["path"]))
    if not rows:
        print("DEPENDENTS=none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
