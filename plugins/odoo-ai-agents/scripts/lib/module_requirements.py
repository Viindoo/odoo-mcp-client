#!/usr/bin/env python3
"""module_requirements.py - what one module needs beyond Odoo's own installation, read from its
descriptor's `external_dependencies` and the Python requirements of the Odoo checkout.

    module_requirements.py <module directory> [--odoo-root DIR] [--addons-path DIR ...]

The descriptor (`__manifest__.py`, else `__openerp__.py`) is read as a literal, never imported.
The checkout is located with odoo_source_facts.locate_odoo_root from --odoo-root, the
--addons-path entries and the module's own parent directory; its `requirements.txt` lists the
Python packages Odoo installs itself.

Prints:
    PYTHON_EXTRA=<comma list of the declared python dependencies the checkout's requirements do
                  not cover>
    BIN=<comma list of every declared bin dependency>
    TECH_SECTION=yes|no          yes when either list is non-empty
A declared name is covered when it equals a requirement after normalisation (case, `-`/`_`/`.`),
also across the import-name / distribution-name difference (`ldap` and `python-ldap`, `dateutil`
and `python-dateutil`, `PIL` and `pillow`).

Exit 0; 2 when the descriptor is unreadable or the arguments are wrong; 3 when python dependencies
are declared but the checkout's requirements cannot be read (nothing is guessed).
No `external_dependencies`: TECH_SECTION=no, exit 0. Stdlib only.
Tests: tests/test_module_requirements.py.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odoo_source_facts as facts  # noqa: E402

# Import names whose distribution carries another name (beyond the `python-` prefix rule).
_DISTRIBUTION_OF = {
    "pil": "pillow",
    "yaml": "pyyaml",
    "openssl": "pyopenssl",
    "crypto": "pycryptodome",
    "serial": "pyserial",
    "usb": "pyusb",
    "bs4": "beautifulsoup4",
    "cups": "pycups",
    "mysqldb": "mysqlclient",
    "jwt": "pyjwt",
    "magic": "python-magic",
    "dateutil": "python-dateutil",
    "ldap": "python-ldap",
    "pypdf2": "pypdf2",
    "zxingcpp": "zxing-cpp",
}


def read_descriptor(module_dir):
    """The descriptor dict of the module, or None when none is present or it is no literal dict."""
    for name in ("__manifest__.py", "__openerp__.py"):
        path = os.path.join(module_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = ast.literal_eval(fh.read().strip())
        except (OSError, ValueError, SyntaxError, MemoryError, RecursionError):
            return None
        return data if isinstance(data, dict) else None
    return None


def _names(value):
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _spellings(name):
    """Every normalised distribution name a declared dependency may be listed under."""
    norm = facts.normalise_requirement(name) or ""
    out = {norm}
    if norm in _DISTRIBUTION_OF:
        out.add(facts.normalise_requirement(_DISTRIBUTION_OF[norm]))
    if norm.startswith("python-"):
        out.add(norm[len("python-"):])
    else:
        out.add("python-" + norm)
    return out


def uncovered(declared, requirements):
    """The declared names no requirement covers, in declaration order."""
    have = set(requirements)
    return [name for name in declared if not (_spellings(name) & have)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module_dir")
    parser.add_argument("--odoo-root", default=None)
    parser.add_argument("--addons-path", action="append", default=[], dest="addons_path")
    args = parser.parse_args(argv)
    module_dir = os.path.abspath(os.path.expanduser(args.module_dir))
    data = read_descriptor(module_dir)
    if data is None:
        print("x no readable module descriptor in %s" % module_dir, file=sys.stderr)
        return 2
    ext = data.get("external_dependencies")
    ext = ext if isinstance(ext, dict) else {}
    declared_python = _names(ext.get("python"))
    bins = _names(ext.get("bin"))
    extra = []
    if declared_python:
        addons = [p for d in args.addons_path for p in d.split(",") if p.strip()]
        addons.append(os.path.dirname(module_dir))
        root = facts.locate_odoo_root(args.odoo_root, addons)
        reqs = facts.python_requirements(root) if root else None
        if reqs is None:
            print("x the Python requirements of the Odoo checkout are unreadable "
                  "(no requirements.txt at its root)", file=sys.stderr)
            return 3
        extra = uncovered(declared_python, reqs)
    print("PYTHON_EXTRA=%s" % ",".join(extra))
    print("BIN=%s" % ",".join(bins))
    print("TECH_SECTION=%s" % ("yes" if extra or bins else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
