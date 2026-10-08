#!/usr/bin/env python3
"""doc_refs_check.py - deterministic gate for image paths and links in an Odoo module's docs.

A module's user guide (doc/*.rst), store page (static/description/*.html), README.rst and
manifest `images` are published by an app store that serves the module's own files and rewrites
relative image paths; anything that points at the author's machine, at a running instance, at a
sibling checkout directory or at one particular store host breaks once published.

Usage:
    python3 doc_refs_check.py --module-root <abs module dir> --series <X.Y> [file ...]

Files default to doc/**/*.rst, static/description/**/*.html, README.rst and the manifest. No
file arguments = every doc file + the descriptor + IMG_ORPHAN over the whole module.
Output: one `file:line: RULE: ref` per finding (file relative to the module root).
Exit: 0 clean (and --help), 1 findings, 2 usage error or an interpreter below 3.8.

Every image a module ships lives flat in static/description/; a guide (doc/**/*.rst) names it
bare, the store page and README.rst by a path resolving to it. An image that is not a module file
(e.g. a vendor logo) is a public https:// URL: the stores display it as is, so it is not checked
further.

Rules
  IMG_NOT_RELATIVE     image that is neither a module path nor a public https:// URL: http://
                       (mixed content on an https store), data:, file: or any other scheme, a
                       leading "/" or "//" (protocol-relative), or a host that is not public
                       (localhost, a loopback, private or unspecified address, a name with no dot)
  IMG_NAME             module image (a reference or a manifest entry) whose file name has a
                       character outside A-Z a-z 0-9 . _ -
  IMG_NOT_BARE         doc/**/*.rst image that is not a bare file name (contains "/" or "\\")
  IMG_ESCAPES_MODULE   HTML / README.rst image resolving outside the module
  IMG_MISSING          doc/**/*.rst image with no static/description/<name>; HTML / README.rst
                       image whose resolved file does not exist
  IMG_NOT_FLAT         HTML / README.rst image not directly inside static/description/, or an
                       HTML image written with a directory part (e.g. `img/x.png`,
                       `../description/x.png`) - `./<file>` / `<file>` is the form Odoo and the
                       stores rewrite to the module's static/description/
  IMG_COVER_NOT_SHOWN  static/description/index.html references no image resolving to the file
                       manifest images[0] names (the manifest is read even when not passed);
                       reported as `static/description/index.html:0: IMG_COVER_NOT_SHOWN: <entry>`
  IMG_ORPHAN           whole-module mode only: an image under static/description/** or doc/**
                       (icon.png / icon.svg exempt) whose file name no other text file of the
                       module mentions; reported as `<path>:0: IMG_ORPHAN: <path>`. A mention is
                       the name standing alone: not preceded by a word character, "." or "-", not
                       followed by one of those or by "." + a word character (`see end.png.`
                       mentions end.png; `myend.png` and `end.png.bak` do not). Files under .git/
                       or __pycache__/ and binary files (a NUL byte in the first 8 KiB) are not read.
  LINK_LOCAL           link to file:, localhost, 127.0.0.1, an absolute filesystem path, or a
                       root-relative path that is not a store module path
  LINK_SIBLING_PATH    relative link resolving outside the module (e.g. ../../<other>/...)
  LINK_STORE_ABSOLUTE  absolute URL (any host) whose path is (/<lang>)?/apps/modules/...
  LINK_STORE_SCHEME    store path not exactly /apps/modules/<series>/<technical_name>
  MANIFEST_IMAGE       manifest `images` entry that is not an existing static/description/<file>
                       png / gif / jpg / jpeg
  MANIFEST_COVER       manifest images[0] whose name without its last extension does not end in
                       `_screenshot` (a locale variant is never the cover)
Allowed: mailto:, tel:, #anchors, https links to non-store pages, public https:// images.

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
import ipaddress  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
from urllib.parse import quote, unquote, urlsplit  # noqa: E402

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

_DESCRIPTION = ("static", "description")
_MANIFEST_IMAGE = re.compile(r"^static/description/[^/\\]+\.(?:png|gif|jpe?g)$", re.I)
_IMAGE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_ORPHAN_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
_ORPHAN_EXEMPT = ("static/description/icon.png", "static/description/icon.svg")
_SKIP_DIRS = (".git", "__pycache__")
_MANIFESTS = ("__manifest__.py", "__openerp__.py")
_ENGLISH_PAGE = "static/description/index.html"


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


def _is_public_host(ref):
    host = _host(ref)
    if not host or _is_local_host(ref):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host.strip(".")


def _image_kind(ref):
    """"local" for a module path, "external" for a public https:// URL, None for anything else."""
    if _DRIVE.match(ref) or ref.startswith(("/", "\\")):
        return None
    if _SCHEME.match(ref):
        return "external" if ref.lower().startswith("https://") and _is_public_host(ref) else None
    return "local"


def _file_name(ref):
    return unquote(urlsplit(ref).path).replace("\\", "/").rsplit("/", 1)[-1]


def _strip_dot_slash(path):
    return path[2:] if path.startswith("./") else path


def _same_file(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _manifest_images(manifest_file):
    """(lineno, value) of each string in the descriptor's `images` list."""
    with open(manifest_file, encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "images"):
                continue
            if not isinstance(value, (ast.List, ast.Tuple)):
                continue
            return [(elt.lineno, elt.value) for elt in value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
        return []
    return []


class Checker(object):
    def __init__(self, module_root, series):
        self.root = os.path.abspath(module_root)
        self.series = series
        self.description = os.path.join(self.root, *_DESCRIPTION)
        self.findings = []

    def _rel(self, path):
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    def _add(self, doc_file, line, rule, ref):
        self.findings.append(Finding(self._rel(doc_file), line, rule, ref))

    def _manifest_file(self):
        for name in _MANIFESTS:
            path = os.path.join(self.root, name)
            if os.path.isfile(path):
                return path
        return None

    # ---------------------------------------------------------------- images
    def image(self, doc_file, line, ref, kind):
        """kind "bare": a guide image, named by its file name in static/description/;
        kind "page": an HTML image, written `./<file>` or `<file>`;
        kind "path": a README.rst image, a path resolving into static/description/."""
        ref = ref.strip()
        if not ref:
            return
        image_kind = _image_kind(ref)
        if image_kind == "external":
            return
        if image_kind is None:
            self._add(doc_file, line, "IMG_NOT_RELATIVE", ref)
            return
        if not _IMAGE_NAME.match(_file_name(ref)):
            self._add(doc_file, line, "IMG_NAME", ref)
        if kind == "bare":
            if "/" in ref or "\\" in ref:
                self._add(doc_file, line, "IMG_NOT_BARE", ref)
            elif not os.path.isfile(os.path.join(self.description, unquote(urlsplit(ref).path))):
                self._add(doc_file, line, "IMG_MISSING", ref)
            return
        target = _resolve(ref, doc_file)
        if not _inside(target, self.root):
            self._add(doc_file, line, "IMG_ESCAPES_MODULE", ref)
            return
        if not os.path.isfile(target):
            self._add(doc_file, line, "IMG_MISSING", ref)
            return
        if not _same_file(os.path.dirname(target), self.description) or (
                kind == "page" and re.search(r"[/\\]", _strip_dot_slash(urlsplit(ref).path))):
            self._add(doc_file, line, "IMG_NOT_FLAT", ref)

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
        kind = "bare" if self._rel(doc_file).startswith("doc/") else "path"
        literal_indent = None
        for no, raw in enumerate(lines, 1):
            indent = len(raw) - len(raw.lstrip())
            if literal_indent is not None:
                if not raw.strip() or indent > literal_indent:
                    continue
                literal_indent = None
            m = _RST_IMAGE.match(raw)
            if m:
                self.image(doc_file, no, m.group(1), kind)
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
        images = []

        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                line = self.getpos()[0]
                values = dict(attrs)
                if tag in ("img", "source"):
                    if values.get("src"):
                        images.append((line, values["src"]))
                    for part in (values.get("srcset") or "").split(","):
                        if part.strip():
                            images.append((line, part.strip().split()[0]))
                if tag == "a" and values.get("href") is not None:
                    checker.link(doc_file, line, values["href"])
                for u in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)",
                                     values.get("style") or ""):
                    images.append((line, u.group(1)))

            handle_startendtag = handle_starttag

        Parser(convert_charrefs=True).feed(text)
        for line, ref in images:
            self.image(doc_file, line, ref, "page")
        if self._rel(doc_file) == _ENGLISH_PAGE:
            self.cover_shown(doc_file, [ref.strip() for _line, ref in images])

    def cover_shown(self, page, refs):
        manifest = self._manifest_file()
        cover = _manifest_images(manifest) if manifest else []
        if not cover:
            return
        target = os.path.join(self.root, cover[0][1])
        if not any(_image_kind(ref) == "local" and _same_file(_resolve(ref, page), target)
                   for ref in refs if ref):
            self._add(page, 0, "IMG_COVER_NOT_SHOWN", cover[0][1])

    # -------------------------------------------------------------- manifest
    def manifest(self, manifest_file):
        for index, (line, ref) in enumerate(_manifest_images(manifest_file)):
            if not _IMAGE_NAME.match(_file_name(ref)):
                self._add(manifest_file, line, "IMG_NAME", ref)
            if not (_MANIFEST_IMAGE.match(ref) and os.path.isfile(os.path.join(self.root, ref))):
                self._add(manifest_file, line, "MANIFEST_IMAGE", ref)
            if index == 0 and not os.path.splitext(os.path.basename(ref))[0].endswith(
                    "_screenshot"):
                self._add(manifest_file, line, "MANIFEST_COVER", ref)

    # --------------------------------------------------------------- orphans
    def orphans(self):
        candidates, texts = [], []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                rel = self._rel(path)
                if (rel.startswith(("static/description/", "doc/"))
                        and name.lower().endswith(_ORPHAN_EXTS) and rel not in _ORPHAN_EXEMPT):
                    candidates.append(path)
                try:
                    with open(path, "rb") as fh:
                        head = fh.read(8192)
                        if b"\0" in head:
                            continue
                        data = head + fh.read()
                except OSError:
                    continue
                texts.append((path, data.decode("utf-8", errors="replace")))
        for path in sorted(candidates, key=self._rel):
            name = os.path.basename(path)
            spellings = sorted({re.escape(name), re.escape(quote(name))})
            pattern = re.compile(r"(?<![\w.-])(?:%s)(?![\w-]|\.\w)" % "|".join(spellings))
            if not any(pattern.search(text) for other, text in texts if other != path):
                rel = self._rel(path)
                self.findings.append(Finding(rel, 0, "IMG_ORPHAN", rel))

    def check_file(self, path):
        low = path.lower()
        name = os.path.basename(path)
        if name in _MANIFESTS:
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
    for name in ("README.rst",) + _MANIFESTS:
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
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
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
    if not args.files:
        checker.orphans()
    for finding in checker.findings:
        sys.stdout.write(finding.render() + "\n")
    return 1 if checker.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
