#!/usr/bin/env python3
"""doc_refs_check.py - deterministic gate for image paths and links in an Odoo module's docs.

A module's user guide (doc/*.rst), store page (static/description/*.html), README.rst and
manifest `images` are published by an app store that serves the module's own files and rewrites
relative image paths; anything that points at the author's machine, at a running instance, at a
sibling checkout directory or at one particular store host breaks once published.

Usage:
    python3 doc_refs_check.py --module-root <abs module dir> --series <X.Y> [file ...]

Files default to doc/**/*.rst, static/description/**/*.html, README.rst and the manifest.
Output: one `file:line: RULE: ref` per finding (file relative to the module root).
Exit: 0 clean, 1 findings, 2 usage error or an interpreter below 3.8.

Rules
  IMG_NOT_RELATIVE     image with a scheme, a leading "/", file:, or a localhost/127.0.0.1 host
  IMG_ESCAPES_MODULE   relative image resolving outside the module
  IMG_MISSING          relative image whose file does not exist
  IMG_NOT_SERVED       HTML image outside static/description/, RST image outside static/
  LINK_LOCAL           link to file:, localhost, 127.0.0.1, an absolute filesystem path, or a
                       root-relative path that is not a store module path
  LINK_SIBLING_PATH    relative link resolving outside the module (e.g. ../../<other>/...)
  LINK_STORE_ABSOLUTE  absolute URL (any host) whose path is (/<lang>)?/apps/modules/...
  LINK_STORE_SCHEME    store path not exactly /apps/modules/<series>/<technical_name>
  MANIFEST_IMAGE       manifest `images` entry not relative to the module root, or missing
Allowed: mailto:, tel:, #anchors, https links to non-store pages.

stdlib only; runs with the plugin interpreter (`python3`), never an Odoo venv. Old syntax (no
f-strings) so the version check below can report instead of a SyntaxError.
"""

import sys

if sys.version_info < (3, 8):
    sys.stderr.write("doc_refs_check.py: make python3 on PATH a Python >= 3.8 (deactivate the "
                     "Odoo venv); this one is %s\n" % sys.version.split()[0])
    sys.exit(2)

import argparse  # noqa: E402
import ast  # noqa: E402
import glob  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
from urllib.parse import unquote, urlsplit  # noqa: E402

_SERIES = re.compile(r"^[0-9]+\.[0-9]+$")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1")
_LANG = r"(?:/[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]{2,4})?)?"
_STORE_PATH = re.compile(r"^" + _LANG + r"/apps/modules(?:/|$)")
_STORE_EXACT = r"^/apps/modules/%s/[a-z0-9_]+$"

# RST
_RST_IMAGE = re.compile(r"^\s*\.\.\s+(?:\|[^|]+\|\s+)?(?:image|figure)::\s*(\S+)")
_RST_TARGET_OPT = re.compile(r"^\s*:target:\s*(\S+)")
# Hyperlink targets: named `.. _name: url`, anonymous `.. __: url` and the short `__ url`.
_RST_LINK_TARGET = re.compile(r"^\s*(?:\.\.\s+_[^:]*:|__)\s+(\S+)\s*$")
# Embedded URIs, named `text <url>`_ and anonymous `text <url>`__.
_RST_EMBEDDED = re.compile(r"`[^`<]*<([^>`]+)>`__?")
_RST_LITERAL_OPEN = re.compile(r"^\s*\.\.\s+(?:code-block|code|sourcecode|highlight)::")
_RST_INLINE_LITERAL = re.compile(r"``.+?``")
_BARE_URL = re.compile(r"(?<![<\w/])(?:https?|file)://[^\s<>`'\"]+")


class Finding(object):
    def __init__(self, path, line, rule, ref):
        self.path, self.line, self.rule, self.ref = path, line, rule, ref

    def render(self):
        return "%s:%d: %s: %s" % (self.path, self.line, self.rule, self.ref)


def _host(ref):
    try:
        return (urlsplit(ref).hostname or "").lower()
    except ValueError:
        return ""


def _is_local_host(ref):
    host = _host(ref)
    return host in _LOCAL_HOSTS or host.startswith("127.")


def _inside(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def _resolve(ref, doc_file):
    path = unquote(urlsplit(ref).path) if not _DRIVE.match(ref) else ref
    return os.path.normpath(os.path.join(os.path.dirname(doc_file), path))


class Checker(object):
    def __init__(self, module_root, series):
        self.root = os.path.abspath(module_root)
        self.series = series
        self.findings = []

    def _add(self, doc_file, line, rule, ref):
        rel = os.path.relpath(doc_file, self.root)
        self.findings.append(Finding(rel.replace(os.sep, "/"), line, rule, ref))

    # ---------------------------------------------------------------- images
    def image(self, doc_file, line, ref, kind):
        ref = ref.strip()
        if not ref:
            return
        if (_SCHEME.match(ref) and not _DRIVE.match(ref)) or ref.startswith(("/", "\\")) \
                or _DRIVE.match(ref) or ref.startswith("//") or _is_local_host(ref):
            self._add(doc_file, line, "IMG_NOT_RELATIVE", ref)
            return
        target = _resolve(ref, doc_file)
        if not _inside(target, self.root):
            self._add(doc_file, line, "IMG_ESCAPES_MODULE", ref)
            return
        if not os.path.isfile(target):
            self._add(doc_file, line, "IMG_MISSING", ref)
            return
        served = (os.path.join(self.root, "static", "description") if kind == "html"
                  else os.path.join(self.root, "static"))
        if not _inside(target, served):
            self._add(doc_file, line, "IMG_NOT_SERVED", ref)

    # ----------------------------------------------------------------- links
    def link(self, doc_file, line, ref):
        ref = ref.strip()
        if not ref or ref.startswith("#"):
            return
        low = ref.lower()
        if low.startswith(("mailto:", "tel:")):
            return
        if low.startswith("file:") or _DRIVE.match(ref):
            self._add(doc_file, line, "LINK_LOCAL", ref)
            return
        if low.startswith(("http://", "https://", "//")):
            if _is_local_host(ref):
                self._add(doc_file, line, "LINK_LOCAL", ref)
            elif _STORE_PATH.match(urlsplit(ref).path or ""):
                self._add(doc_file, line, "LINK_STORE_ABSOLUTE", ref)
            return
        if _SCHEME.match(ref):
            return
        if ref.startswith("/"):
            if _STORE_PATH.match(ref):
                if not re.match(_STORE_EXACT % re.escape(self.series), ref):
                    self._add(doc_file, line, "LINK_STORE_SCHEME", ref)
            else:
                self._add(doc_file, line, "LINK_LOCAL", ref)
            return
        if not _inside(_resolve(ref, doc_file), self.root):
            self._add(doc_file, line, "LINK_SIBLING_PATH", ref)

    # ------------------------------------------------------------------- RST
    def rst(self, doc_file):
        with open(doc_file, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        literal_indent = None
        for no, raw in enumerate(lines, 1):
            indent = len(raw) - len(raw.lstrip())
            if literal_indent is not None:
                if not raw.strip() or indent > literal_indent:
                    continue
                literal_indent = None
            m = _RST_IMAGE.match(raw)
            if m:
                self.image(doc_file, no, m.group(1), "rst")
            else:
                m = _RST_TARGET_OPT.match(raw) or _RST_LINK_TARGET.match(raw)
                if m:
                    self.link(doc_file, no, m.group(1))
                else:
                    text = _RST_INLINE_LITERAL.sub("", raw)
                    for e in _RST_EMBEDDED.finditer(text):
                        self.link(doc_file, no, e.group(1))
                    for u in _BARE_URL.finditer(_RST_EMBEDDED.sub("", text)):
                        self.link(doc_file, no, u.group(0).rstrip(".,;:)"))
            if _RST_LITERAL_OPEN.match(raw) or (raw.rstrip().endswith("::")
                                                and not raw.lstrip().startswith("..")):
                literal_indent = indent

    # ------------------------------------------------------------------ HTML
    def html(self, doc_file):
        with open(doc_file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        checker = self

        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                line = self.getpos()[0]
                values = dict(attrs)
                if tag in ("img", "source"):
                    if values.get("src"):
                        checker.image(doc_file, line, values["src"], "html")
                    for part in (values.get("srcset") or "").split(","):
                        if part.strip():
                            checker.image(doc_file, line, part.strip().split()[0], "html")
                if tag == "a" and values.get("href") is not None:
                    checker.link(doc_file, line, values["href"])
                for u in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)",
                                     values.get("style") or ""):
                    checker.image(doc_file, line, u.group(1), "html")

            handle_startendtag = handle_starttag

        Parser(convert_charrefs=True).feed(text)

    # -------------------------------------------------------------- manifest
    def manifest(self, manifest_file):
        with open(manifest_file, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "images"):
                    continue
                if not isinstance(value, (ast.List, ast.Tuple)):
                    continue
                for elt in value.elts:
                    if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                        continue
                    ref = elt.value
                    target = os.path.normpath(os.path.join(self.root, ref))
                    if (_SCHEME.match(ref) or ref.startswith(("/", "\\")) or _DRIVE.match(ref)
                            or not _inside(target, self.root) or not os.path.isfile(target)):
                        self._add(manifest_file, elt.lineno, "MANIFEST_IMAGE", ref)
            return

    def check_file(self, path):
        low = path.lower()
        name = os.path.basename(path)
        if name in ("__manifest__.py", "__openerp__.py"):
            self.manifest(path)
        elif low.endswith(".rst"):
            self.rst(path)
        elif low.endswith((".html", ".htm")):
            self.html(path)


def default_files(root):
    found = []
    found += sorted(glob.glob(os.path.join(root, "doc", "**", "*.rst"), recursive=True))
    found += sorted(glob.glob(os.path.join(root, "static", "description", "**", "*.html"),
                              recursive=True))
    for name in ("README.rst", "__manifest__.py", "__openerp__.py"):
        if os.path.isfile(os.path.join(root, name)):
            found.append(os.path.join(root, name))
    return found


def main(argv):
    parser = argparse.ArgumentParser(prog="doc_refs_check.py", description=__doc__.split("\n")[0])
    parser.add_argument("--module-root", required=True)
    parser.add_argument("--series", required=True)
    parser.add_argument("files", nargs="*")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    root = os.path.abspath(args.module_root)
    if not os.path.isdir(root):
        sys.stderr.write("doc_refs_check.py: --module-root %s is not a directory\n" % root)
        return 2
    if not _SERIES.match(args.series):
        sys.stderr.write("doc_refs_check.py: --series must look like 17.0, got %r\n" % args.series)
        return 2
    files = [f if os.path.isabs(f) else os.path.join(root, f) for f in args.files] \
        or default_files(root)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.stderr.write("doc_refs_check.py: no such file: %s\n" % ", ".join(missing))
        return 2
    checker = Checker(root, args.series)
    for path in files:
        checker.check_file(path)
    for finding in checker.findings:
        sys.stdout.write(finding.render() + "\n")
    return 1 if checker.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
