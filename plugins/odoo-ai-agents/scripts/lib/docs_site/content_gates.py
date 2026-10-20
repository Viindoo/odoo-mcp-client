#!/usr/bin/env python3
"""content_gates.py - mechanical content gates for the docs a change adds or modifies.

  content_gates.py --worktree W --base-ref REF --policy P [--pages p1,p2] [--built-css CSS]
                   [--capture-text FILE.jsonl] [--check-links] [--added-only] [--json]

Scope: files added or modified against REF (`git diff --name-only --diff-filter=AM REF`, plus
untracked files), or --pages (those pages, their per-language .po catalogs and the images they
reference; REF is then only used to tell added lines from old ones). Site policy comes from a JSON
object (`--policy`); a key that is absent switches its rule off. Stdlib only, python3 >= 3.8.

Rules (each finding carries rule, file, line, detail):
  BANNED_TERM         policy banned_terms as a whole word, case-insensitive, in RST prose, in the
                      reader-visible option text (:alt:, a meta :description:) and in the msgstr of the
                      touched .po files; code blocks, literals, link targets and path-like tokens
                      (/odoo?debug=1, https://...) are skipped; banned_terms_exempt_paths (globs) are
                      skipped.
  VERSION_PROSE       (forbid_version_prose) a series from series_list - or "Odoo N" for an N.0 series -
                      in prose; not in URLs, literals, code or paths.
  PRESENTATION        :width: :height: :scale: :figwidth: on image/figure/thumbnail (a youtube/vimeo
                      directive or iframe is exempt); style= or <style> in prose or raw html; hex/rgb/hsl
                      colours in prose; the classes lazy / img-fluid written by hand; a :class: /
                      rst-class / container class that is not in --built-css (when given) or not in
                      policy semantic_classes (when non-empty).
  HARDCODED_SITE_LINK a link starting with policy site_url_prefix in an added line (use :doc: / :ref:).
  MARKETPLACE_LINK    a link matching policy marketplace_url ({series}, {module}) whose series is not the
                      worktree's; with --check-links also one that does not answer HTTP 200 to HEAD
                      (10 s timeout). A network error is UNVERIFIED, not a finding.
  CAPTURE_BANNED_TERM banned terms in the text the caller read off a screenshot (--capture-text: one JSON
                      object per line, {"image": "<repo-relative path>", "lang": "vi", "text": "..."}),
                      matched the way prose is. This tool reads no pixels. Every image in scope (the plain
                      file and each per-language variant that exists) with no record is listed under
                      images_to_review - for the caller to look at; it is not a failure.
--added-only limits every text rule to added lines. Exit: 0 no finding (UNVERIFIED items and images to
review are listed but do not fail), 1 at least one finding, 2 usage / unreadable policy, ref or capture file.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docs_site import (UNKNOWN, PolicyError, catalogs_for_page, emit, git, glob_match,  # noqa: E402
                       image_refs, load_policy, normalize_series, parse_po, read_text, rst_lines)
from docs_site import repo_facts  # noqa: E402

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
HAND_WRITTEN_CLASSES = ("lazy", "img-fluid")
SIZE_OPTIONS = ("width", "height", "scale", "figwidth")
SIZED_DIRECTIVES = ("image", "figure", "thumbnail")
CLASS_DIRECTIVES = ("rst-class", "container", "cssclass")
LINK_KINDS = ("prose", "directive", "option", "raw")
READER_OPTIONS = ("alt", "description", "keywords", "subtitle")

# --------------------------------------------------------------------------- prose view

_LITERAL = re.compile(r"``.+?``", re.S)
_ROLE = re.compile(r":([\w:+.-]+):`([^`]*)`", re.S)
_LINK_ROLES = {"doc", "ref", "numref", "download", "any"}
_PROSE_ROLES = {"guilabel", "menuselection", "abbr", "term", "kbd"}
_HYPERLINK = re.compile(r"(`[^`<]*)(<[^<>`]+>)(`_{1,2})")
_URL = re.compile(r"(?:https?|ftp)://[^\s<>`\"')]+|www\.[^\s<>`\"')]+", re.I)
_PATHLIKE = re.compile(r"\S*/\S*")


def _blank(match_text):
    return " " * len(match_text)


def prose_view(text):
    """`text` with everything that is not running prose blanked out (same length).

    Blanked: inline literals, the target of :doc:/:ref:/... and of every literal-like role, the
    target of `text <url>`_ links and bare URLs. :guilabel:, :menuselection:, :abbr: and
    :term: are kept - their text is read by people.
    """
    text = _LITERAL.sub(lambda m: _blank(m.group(0)), text)

    def role(m):
        name = m.group(1)
        if name in _PROSE_ROLES:
            return m.group(0)
        whole = m.group(0)
        if name in _LINK_ROLES:
            inner = m.group(2)
            ang = re.search(r"<[^<>]*>\s*$", inner)
            if ang:
                start = m.start(2) - m.start(0) + ang.start()
                return whole[:start] + _blank(whole[start:-1]) + whole[-1]
        return _blank(whole)
    text = _ROLE.sub(role, text)
    text = _HYPERLINK.sub(lambda m: m.group(1) + _blank(m.group(2)) + m.group(3), text)
    text = _URL.sub(lambda m: _blank(m.group(0)), text)
    return text


def term_regex(term):
    words = term.split()
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?!\w)", re.I)


def version_regexes(series_list):
    out = []
    for series in series_list:
        s = str(series).strip()
        if not s:
            continue
        out.append(re.compile(r"(?<![\w./])" + re.escape(s) + r"(?!\w|\.\d)", re.I))
        m = re.fullmatch(r"(\d{1,2})\.0", s)
        if m:
            out.append(re.compile(r"(?<![\w.])(?:odoo|version|v)\s*" + m.group(1) + r"(?!\d|\.\d)", re.I))
    return out


_HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z])")
_FUNC_COLOUR = re.compile(r"\b(?:rgba?|hsla?)\s*\(", re.I)
_STYLE_ATTR = re.compile(r"\bstyle\s*=|<\s*style\b", re.I)


def colour_matches(view):
    """[(offset, text)] of hex / rgb() / hsl() colours; "#123" and "#100" are numbers, not colours."""
    out = []
    for m in _HEX_COLOUR.finditer(view):
        token = m.group(0)[1:]
        if len(token) == 6 or re.search(r"[a-fA-F]", token):
            out.append((m.start(), m.group(0)))
    out.extend((m.start(), m.group(0)) for m in _FUNC_COLOUR.finditer(view))
    return out


# --------------------------------------------------------------------------- text units

class Unit(object):
    """A run of text with the file lines it came from. spans: [(offset, line_no)]."""
    __slots__ = ("text", "spans", "first", "last", "kind")

    def __init__(self, text, spans, first, last, kind="prose"):
        self.text, self.spans, self.first, self.last, self.kind = text, spans, first, last, kind

    def line_at(self, offset):
        idx = bisect.bisect_right([s[0] for s in self.spans], offset) - 1
        return self.spans[max(idx, 0)][1]


def _join(lines):
    parts, spans, pos = [], [], 0
    for ln in lines:
        piece = ln.text.strip()
        spans.append((pos, ln.no))
        parts.append(piece)
        pos += len(piece) + 1
    return " ".join(parts), spans


def rst_prose_units(lines):
    units, cur = [], []
    for ln in lines + [None]:
        if ln is not None and ln.kind == "prose":
            cur.append(ln)
            continue
        if cur:
            text, spans = _join(cur)
            units.append(Unit(text, spans, cur[0].no, cur[-1].no))
            cur = []
    return units


def po_units(text):
    units = []
    for e in parse_po(text):
        if e["is_header"]:
            continue
        for item in e["msgstrs"]:
            if item["text"].strip():
                units.append(Unit(item["text"], [(0, item["line"])], item["line"], item["end_line"]))
    return units


# --------------------------------------------------------------------------- scope and added lines

def changed_files(worktree, base_ref):
    out = git(worktree, "diff", "--name-only", "--diff-filter=AM", base_ref)
    if out is None:
        return None
    files = set(l.strip() for l in out.splitlines() if l.strip())
    untracked = git(worktree, "ls-files", "--others", "--exclude-standard")
    if untracked:
        files.update(l.strip() for l in untracked.splitlines() if l.strip())
    return sorted(files)


class AddedLines(object):
    """Which lines of a file this change added (None = every line: the file is new)."""

    def __init__(self, worktree, base_ref):
        self.worktree, self.base_ref, self.cache = worktree, base_ref, {}

    def get(self, path):
        if path in self.cache:
            return self.cache[path]
        result = None
        if self.base_ref and git(self.worktree, "cat-file", "-e", "%s:%s" % (self.base_ref, path)) is not None:
            diff = git(self.worktree, "diff", "-U0", self.base_ref, "--", path)
            if diff is not None:
                result = set()
                for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.M):
                    start = int(m.group(1))
                    count = int(m.group(2)) if m.group(2) is not None else 1
                    result.update(range(start, start + count))
        self.cache[path] = result
        return result

    def touches(self, path, first, last):
        added = self.get(path)
        return added is None or any(n in added for n in range(first, last + 1))


def referenced_images(worktree, page):
    """Existing image files of a page: the plain file of every reference and each
    <root>.<lang><ext> variant next to it. A variant counts even when the plain file is absent."""
    text = read_text(os.path.join(worktree, page))
    found = []
    if text is None:
        return found
    for _no, ref in image_refs(rst_lines(text)):
        if re.match(r"^[a-zA-Z][\w+.-]*://", ref):
            continue
        rel = os.path.normpath(("content" + ref) if ref.startswith("/")
                               else os.path.join(os.path.dirname(page), ref)).replace(os.sep, "/")
        root, ext = os.path.splitext(rel)
        folder = os.path.dirname(rel)
        directory = os.path.join(worktree, folder)
        if not os.path.isdir(directory):
            continue
        stem = os.path.basename(root)
        for name in sorted(os.listdir(directory)):
            is_plain = name == stem + ext
            is_variant = name.startswith(stem + ".") and name.endswith(ext) and not is_plain
            if (is_plain or is_variant) and os.path.isfile(os.path.join(directory, name)):
                found.append(folder + "/" + name if folder else name)
    return found


# --------------------------------------------------------------------------- css

def css_classes(css_text):
    css = re.sub(r"/\*.*?\*/", " ", css_text, flags=re.S)
    css = re.sub(r"url\([^)]*\)|\"[^\"]*\"|'[^']*'", " ", css)
    found = set()
    for m in re.finditer(r"\.(-?(?:\\.|[_a-zA-Z])(?:\\.|[\w-])*)", css):
        found.add(re.sub(r"\\(.)", r"\1", m.group(1)))
    return found


# --------------------------------------------------------------------------- the text rules

class Gate(object):
    def __init__(self, worktree, policy, series, added, added_only, built_css_classes):
        self.worktree, self.policy, self.series = worktree, policy, series
        self.added, self.added_only = added, added_only
        self.css = built_css_classes
        self.findings = []
        self.unverified = []
        self.banned = [(t, term_regex(t)) for t in policy["banned_terms"] if str(t).strip()]
        self.version = version_regexes(policy["series_list"]) if policy["forbid_version_prose"] else []
        self.marketplace = self._marketplace_regex(policy["marketplace_url"])
        self.links = []   # (url, file, line) marketplace links for --check-links

    @staticmethod
    def _marketplace_regex(pattern):
        if not pattern:
            return None
        rx = re.escape(pattern)
        rx = rx.replace(re.escape("{series}"), r"(?P<series>[A-Za-z0-9.~-]+)")
        rx = rx.replace(re.escape("{module}"), r"(?P<module>[\w.-]+)")
        return re.compile(rx)

    def add(self, rule, path, line, detail, match=None):
        row = {"rule": rule, "file": path, "line": line, "detail": detail}
        if match is not None:
            row["match"] = match
        self.findings.append(row)

    def exempt(self, path):
        return any(glob_match(path, p) for p in self.policy["banned_terms_exempt_paths"])

    def _in_scope(self, path, first, last):
        return (not self.added_only) or self.added.touches(path, first, last)

    # -- prose rules shared by RST paragraphs and .po msgstr
    def prose_unit(self, path, unit):
        if not self._in_scope(path, unit.first, unit.last):
            return
        view = prose_view(unit.text)
        pview = _PATHLIKE.sub(lambda m: _blank(m.group(0)), view)
        self.banned_in(path, unit, pview)
        if self.version:
            vview = pview
            for rx in self.version:
                for m in rx.finditer(vview):
                    self.add("VERSION_PROSE", path, unit.line_at(m.start()),
                             "a series number in prose", m.group(0))
        for pos, token in colour_matches(view):
            self.add("PRESENTATION", path, unit.line_at(pos), "colour written in prose", token)

    def banned_in(self, path, unit, pview):
        """BANNED_TERM over `pview`, the unit's text with literals, targets and path-like tokens blanked."""
        if self.banned and not self.exempt(path):
            for term, rx in self.banned:
                for m in rx.finditer(pview):
                    self.add("BANNED_TERM", path, unit.line_at(m.start()),
                             "banned term %r" % term, m.group(0))

    def option_text(self, path, ln):
        """Reader-visible text kept in a directive option (alt text, a meta description)."""
        if ln.opt in READER_OPTIONS and ln.val and self._in_scope(path, ln.no, ln.no):
            unit = Unit(ln.val, [(0, ln.no)], ln.no, ln.no)
            self.banned_in(path, unit, _PATHLIKE.sub(lambda m: _blank(m.group(0)), prose_view(ln.val)))

    def link_text(self, path, no, text, last=None):
        """Link rules over one raw line (RST prose/directive/option/raw line or a msgstr)."""
        last = no if last is None else last
        prefix = self.policy["site_url_prefix"]
        if prefix and self._in_scope(path, no, last):
            for m in re.finditer(re.escape(prefix) + r"[^\s<>`\"')]*", text, re.I):
                self.add("HARDCODED_SITE_LINK", path, no,
                         "internal link spelled as a URL; use :doc: or :ref:", m.group(0))
        if self.marketplace and self._in_scope(path, no, last):
            for m in self.marketplace.finditer(text):
                url = m.group(0)
                self.links.append((url, path, no))
                if "series" in m.groupdict():
                    link_series = normalize_series(m.group("series"))
                    if self.series == UNKNOWN:
                        continue
                    if link_series != self.series:
                        self.add("MARKETPLACE_LINK", path, no,
                                 "link series %s differs from the worktree series %s"
                                 % (m.group("series"), self.series), url)

    # -- RST
    def rst_file(self, path, text):
        lines = rst_lines(text)
        for unit in rst_prose_units(lines):
            self.prose_unit(path, unit)
        for ln in lines:
            if ln.kind in LINK_KINDS:
                self.link_text(path, ln.no, ln.text)
            if ln.kind == "option":
                self.option_text(path, ln)
            self._presentation_line(path, ln)

    def _presentation_line(self, path, ln):
        if not self._in_scope(path, ln.no, ln.no):
            return
        if ln.kind == "option":
            if ln.name in SIZED_DIRECTIVES and ln.opt in SIZE_OPTIONS:
                self.add("PRESENTATION", path, ln.no,
                         ":%s: on a %s directive; size is the theme's job" % (ln.opt, ln.name), ln.val)
            if ln.opt in ("class", "figclass", "cssclass"):
                self.check_classes(path, ln.no, ln.val.split())
        elif ln.kind == "directive" and ln.name in CLASS_DIRECTIVES and ln.val:
            self.check_classes(path, ln.no, ln.val.split())
        if ln.kind in ("prose", "raw", "directive", "option"):
            if _STYLE_ATTR.search(ln.text) and not (ln.kind == "raw" and "<iframe" in ln.text.lower()):
                self.add("PRESENTATION", path, ln.no, "inline style in the page", ln.text.strip()[:100])
        if ln.kind == "raw":
            for cls in re.findall(r"\bclass\s*=\s*[\"']([^\"']*)[\"']", ln.text):
                self.check_classes(path, ln.no, cls.split(), hand_only=True)

    def check_classes(self, path, no, classes, hand_only=False):
        for cls in classes:
            if cls in HAND_WRITTEN_CLASSES:
                self.add("PRESENTATION", path, no, "class %r is added by the theme, never written by hand" % cls, cls)
            elif hand_only:
                continue
            elif self.css is not None and cls not in self.css:
                self.add("PRESENTATION", path, no, "class %r is not in the compiled CSS" % cls, cls)
            elif self.policy["semantic_classes"] and cls not in self.policy["semantic_classes"]:
                self.add("PRESENTATION", path, no, "class %r is not a semantic class of this site" % cls, cls)

    # -- .po
    def po_file(self, path, text):
        for unit in po_units(text):
            self.prose_unit(path, unit)
            if not self._in_scope(path, unit.first, unit.last):
                continue
            if _STYLE_ATTR.search(unit.text):
                self.add("PRESENTATION", path, unit.first, "inline style in a translation",
                         unit.text.strip()[:100])
            for part in unit.text.splitlines() or [unit.text]:
                self.link_text(path, unit.first, part, unit.last)


# --------------------------------------------------------------------------- links

def default_head(url, timeout=10):
    """(status, error): HTTP status after redirects, or (None, reason) on a network failure."""
    def attempt(method):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": "docs-site-gates/1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, None
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return None, str(getattr(exc, "reason", exc))
    status, err = attempt("HEAD")
    if status in (405, 501):
        status, err = attempt("GET")
    return status, err


def check_links(gate, head):
    seen = {}
    for url, path, no in gate.links:
        if url not in seen:
            seen[url] = head(url)
        status, err = seen[url]
        if status is None:
            gate.unverified.append({"rule": "MARKETPLACE_LINK", "file": path, "line": no,
                                    "match": url, "reason": "network error: %s" % err})
        elif status != 200:
            gate.add("MARKETPLACE_LINK", path, no, "HTTP %s" % status, url)


# --------------------------------------------------------------------------- captured text

def load_capture_text(path):
    """Records of a --capture-text JSONL file: [{image, lang, text}]. A bad line is a PolicyError."""
    raw = read_text(path)
    if raw is None:
        raise PolicyError("capture text file not readable: %s" % path)
    records = []
    for no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise PolicyError("capture text line %d is not valid JSON: %s" % (no, exc))
        if (not isinstance(row, dict) or not isinstance(row.get("image"), str) or not row["image"].strip()
                or not isinstance(row.get("text"), str)
                or not isinstance(row.get("lang", ""), str)):
            raise PolicyError('capture text line %d must be {"image": str, "lang": str, "text": str}' % no)
        image = os.path.normpath(row["image"].strip()).replace(os.sep, "/")
        records.append({"image": image, "lang": row.get("lang", ""), "text": row["text"]})
    return records


def scan_capture_text(gate, records):
    """Banned terms in the text a caller read off each screenshot; same matcher as prose."""
    for rec in records:
        if gate.exempt(rec["image"]):
            continue
        text = rec["text"]
        for term, rx in gate.banned:
            for m in rx.finditer(text):
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.end())
                line = text[start:end if end >= 0 else len(text)].strip()
                gate.add("CAPTURE_BANNED_TERM", rec["image"], None,
                         "banned term %r in the text captured from the image%s"
                         % (term, (" (%s)" % rec["lang"]) if rec["lang"] else ""), line)


# --------------------------------------------------------------------------- run

def run_gates(worktree, base_ref, policy, pages=None, built_css=None, capture_text=None,
              check_links_flag=False, added_only=False, head=None):
    """Run every rule and return the report dict. `head` is a test seam for the link check.
    `capture_text` is the path of a JSONL file of text read off screenshots (see the module doc)."""
    facts = repo_facts.collect(worktree)
    series = facts["series"]
    css = None
    if built_css:
        css_text = read_text(built_css)
        if css_text is None:
            raise PolicyError("built css not readable: %s" % built_css)
        css = css_classes(css_text)
    records = load_capture_text(capture_text) if capture_text else []

    if pages:
        files = []
        for page in pages:
            files.append(page)
            files.extend(catalogs_for_page(worktree, page))
            files.extend(referenced_images(worktree, page))
        files = sorted(set(files))
    else:
        files = changed_files(worktree, base_ref)
        if files is None:
            raise PolicyError("git could not diff against %r in %s" % (base_ref, worktree))
    added = AddedLines(worktree, base_ref)
    gate = Gate(worktree, policy, series, added, added_only, css)
    if gate.marketplace is not None and series == UNKNOWN:
        gate.unverified.append({"rule": "MARKETPLACE_LINK", "file": None, "line": None,
                                "reason": "worktree series is UNKNOWN; link series not compared"})
    images = []
    for path in files:
        full = os.path.join(worktree, path)
        if not os.path.isfile(full):
            continue
        low = path.lower()
        if low.endswith(".rst"):
            gate.rst_file(path, read_text(full) or "")
        elif low.endswith(".po"):
            gate.po_file(path, read_text(full) or "")
        elif low.endswith(IMAGE_EXT):
            images.append(path)
    if check_links_flag:
        check_links(gate, head or default_head)
    scan_capture_text(gate, records)
    captured = set(r["image"] for r in records)
    to_review = [p for p in images if p not in captured and not gate.exempt(p)]
    counts = {}
    for f in gate.findings:
        counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    order = lambda f: (f["file"], f["line"] if f["line"] is not None else -1, f["rule"], str(f.get("match")))
    return {
        "ok": not gate.findings,
        "worktree_series": series,
        "base_ref": base_ref,
        "scope": {"files": files, "images": images},
        "findings": sorted(gate.findings, key=order),
        "unverified": gate.unverified,
        "counts": counts,
        "capture_records": len(records),
        "images_to_review": to_review,
    }


def summary(report):
    lines = ["%d finding(s), %d unverified, %d file(s) in scope"
             % (len(report["findings"]), len(report["unverified"]), len(report["scope"]["files"]))]
    for f in report["findings"]:
        lines.append("  %s %s:%s %s%s" % (f["rule"], f["file"], f["line"] if f["line"] is not None else "-",
                                          f["detail"], (" [%s]" % f["match"]) if "match" in f else ""))
    for u in report["unverified"]:
        lines.append("  UNVERIFIED %s %s: %s" % (u["rule"], u.get("file") or "-", u["reason"]))
    for path in report["images_to_review"]:
        lines.append("  IMAGES_TO_REVIEW %s" % path)
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mechanical content gates for a docs change.")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--base-ref")
    ap.add_argument("--policy", required=True)
    ap.add_argument("--pages", help="comma-separated content/<path>.rst; replaces the git diff scope")
    ap.add_argument("--built-css")
    ap.add_argument("--capture-text", help="JSONL: one {image, lang, text} per line, the text read off "
                                           "a screenshot; scanned for banned terms like prose")
    ap.add_argument("--check-links", action="store_true")
    ap.add_argument("--added-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.worktree):
        sys.stderr.write("worktree is not a directory: %s\n" % args.worktree)
        return 2
    pages = [p.strip() for p in args.pages.split(",") if p.strip()] if args.pages else None
    if not pages and not args.base_ref:
        sys.stderr.write("--base-ref is required unless --pages is given\n")
        return 2
    try:
        policy = load_policy(args.policy)
        report = run_gates(args.worktree, args.base_ref, policy, pages=pages, built_css=args.built_css,
                           capture_text=args.capture_text, check_links_flag=args.check_links, added_only=args.added_only)
    except PolicyError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    emit(report, args.json, summary(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
