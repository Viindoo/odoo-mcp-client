"""docs_site - deterministic helpers for the product-docs-site workflow.

A product docs site is a separate Sphinx repo (one branch per series, English RST source,
a second language through gettext catalogs, screenshots stored per language). The scripts in
this package read that repo's TEXT (never import or execute its conf.py), report JSON, and
exit non-zero on a failing gate. Each is a CLI:

  repo_facts.py     facts the docs repo states about itself (series, languages, hazards, conventions)
  images.py         install staged screenshots as JPEG / check every language has its image
  content_gates.py  banned terms, version prose, presentation, links, text captured off screenshots
  ui_terms.py       check the UI terms a translation uses against a live instance in that language

Rules shared by all of them: stdlib only (python3 >= 3.8; images.py install alone needs
Pillow), no clock or randomness in a report, a fact the repo does not state is the string
"UNKNOWN" and never a guess, and nothing writes inside the docs repo except `images.py install`.

This module holds the readers they share: git, the site policy, a gettext (.po) reader and a
line classifier for RST that tells prose from literal blocks, directive options and comments.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys

UNKNOWN = "UNKNOWN"

# The bold menu-path separator of an Odoo doc (Settings, arrow, Users), written as an escape so the
# source stays ASCII. Defined once; repo_facts and ui_terms import it.
ARROW = "\u2023"

# A series token: "17.0", "saas-17.2", or the word "master". Never the middle of a longer number.
_SERIES_NUM = re.compile(r"(?<![\d.])(?:saas[-~])?\d{1,2}\.\d{1,2}(?!\d)")


def normalize_series(value):
    """Return the series token inside `value` ("17.0", "saas-17.2", "master") or None."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "master":
        return "master"
    m = _SERIES_NUM.search(text)
    return m.group(0) if m else None


# --------------------------------------------------------------------------- files / git

def read_text(path):
    """File text (utf-8, undecodable bytes replaced) or None when it cannot be read."""
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return None


def git(worktree, *args):
    """stdout of `git -C worktree <args>` or None when git is missing or the command fails."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", worktree] + list(args),
            capture_output=True, env=env, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", "replace")


def glob_match(path, pattern):
    """Glob on a '/'-separated relative path: `**` crosses directories, `*` and `?` do not."""
    regex = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            regex += "(?:.*/)?"
            i += 3
            continue
        if c == "*":
            if pattern.startswith("**", i):
                regex += ".*"
                i += 2
                continue
            regex += "[^/]*"
        elif c == "?":
            regex += "[^/]"
        else:
            regex += re.escape(c)
        i += 1
    return re.fullmatch(regex, path) is not None or fnmatch.fnmatchcase(path, pattern)


# --------------------------------------------------------------------------- policy / output

POLICY_DEFAULTS = {
    "banned_terms": [],
    "banned_terms_exempt_paths": [],
    "forbid_version_prose": False,
    "series_list": [],
    "marketplace_url": "",
    "site_url_prefix": "",
    "semantic_classes": [],
}


class PolicyError(Exception):
    pass


def load_policy(path):
    """Site policy from a JSON object file; absent keys take the defaults (rule off)."""
    policy = {k: (list(v) if isinstance(v, list) else v) for k, v in POLICY_DEFAULTS.items()}
    if not path:
        return policy
    text = read_text(path)
    if text is None:
        raise PolicyError("policy file not readable: %s" % path)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise PolicyError("policy file is not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise PolicyError("policy file must hold a JSON object")
    for key, default in POLICY_DEFAULTS.items():
        if key in data and data[key] is not None:
            if type(data[key]) is not type(default):
                raise PolicyError("policy key %s must be a %s" % (key, type(default).__name__))
            policy[key] = data[key]
    return policy


def emit(report, as_json, summary_lines):
    """JSON on stdout with --json (summary on stderr), else the summary on stdout."""
    if as_json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        sys.stderr.write("\n".join(summary_lines) + "\n")
    else:
        sys.stdout.write("\n".join(summary_lines) + "\n")


# --------------------------------------------------------------------------- gettext reader

_PO_KEY = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s*(".*")\s*$')
_PO_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}


def _po_unquote(quoted):
    inner = quoted[1:-1]
    return re.sub(r"\\(.)", lambda m: _PO_ESC.get(m.group(1), m.group(1)), inner)


def parse_po(text):
    """Entries of a .po file: dicts with msgctxt, msgid, flags, line and msgstrs.

    `msgstrs` is a list of {text, line, end_line}; a plural entry has one per form. The header
    is the entry whose msgid is "" and `is_header` is True. Obsolete (#~) entries are skipped.
    """
    entries = []
    cur = None
    field = None  # (key, target dict) the next continuation line extends
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            cur = None
            field = None
            continue
        if line.startswith("#~"):
            continue
        if line.startswith("#"):
            if cur is None:
                cur = {"msgctxt": None, "msgid": "", "msgstrs": [], "flags": [], "line": no,
                       "is_header": False, "_has_id": False}
                entries.append(cur)
            if line.startswith("#,"):
                cur["flags"].extend(f.strip() for f in line[2:].split(",") if f.strip())
            continue
        m = _PO_KEY.match(line)
        if m:
            key, value = m.group(1), _po_unquote(m.group(3))
            starts_new = key in ("msgctxt", "msgid") and (
                cur is None or bool(cur["msgstrs"]) or cur["_has_id"])
            if starts_new:
                cur = {"msgctxt": None, "msgid": "", "msgstrs": [], "flags": [], "line": no,
                       "is_header": False, "_has_id": False}
                entries.append(cur)
            if cur is None:
                continue
            if key == "msgctxt":
                cur["msgctxt"] = value
                field = ("msgctxt", cur)
            elif key == "msgid":
                cur["msgid"] = value
                cur["_has_id"] = True
                field = ("msgid", cur)
            elif key == "msgid_plural":
                field = ("ignore", cur)
            else:
                item = {"text": value, "line": no, "end_line": no}
                cur["msgstrs"].append(item)
                field = ("msgstr", item)
        elif line.startswith('"') and field is not None:
            value = _po_unquote(line)
            kind, target = field
            if kind in ("msgctxt", "msgid"):
                target[kind] = (target[kind] or "") + value
            elif kind == "msgstr":
                target["text"] += value
                target["end_line"] = no
    for e in entries:
        e["is_header"] = e["_has_id"] and e["msgid"] == "" and e["msgctxt"] is None
        del e["_has_id"]
    return entries


def po_header_fields(text):
    """The header entry's `Key: value` fields of a .po file as a dict."""
    for e in parse_po(text):
        if e["is_header"] and e["msgstrs"]:
            out = {}
            for ln in e["msgstrs"][0]["text"].splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    out[k.strip()] = v.strip()
            return out
    return {}


# --------------------------------------------------------------------------- RST line classifier

class Line(object):
    """One RST line. kind: prose | directive | option | code | raw | comment | blank.

    name is the directive a directive/option/code/raw line belongs to; opt and val are the
    option name and value of an option line, or the argument of a directive line (val).
    """
    __slots__ = ("no", "text", "kind", "name", "opt", "val", "indent")

    def __init__(self, no, text, kind, name=None, opt=None, val=None, indent=0):
        self.no = no
        self.text = text
        self.kind = kind
        self.name = name
        self.opt = opt
        self.val = val
        self.indent = indent

    def __repr__(self):
        return "Line(%d,%s,%s)" % (self.no, self.kind, self.name)


_DIRECTIVE = re.compile(
    r"^(?P<ind>\s*)\.\.\s+(?:\|[^|]+\|\s+)?(?P<name>[A-Za-z][\w:+.-]*)::(?:\s+(?P<arg>.*))?$")
_TARGET = re.compile(r"^\s*\.\.\s+(?:_[^:]+:|__:)")
_OPTION = re.compile(r"^(?P<ind>\s+):(?P<opt>[\w-]+):(?:\s+(?P<val>.*))?$")

# Directives whose body is not prose.
_LITERAL_BODY = {"code-block", "code", "sourcecode", "parsed-literal", "math", "productionlist",
                 "toctree", "literalinclude", "include", "index", "highlight", "default-role",
                 "doctest", "testcode", "testoutput", "graphviz", "mermaid", "uml"}
# Directives whose argument line is running text.
_PROSE_ARG = {"note", "warning", "tip", "important", "caution", "danger", "hint", "attention",
              "error", "seealso", "admonition", "topic", "sidebar", "versionadded",
              "versionchanged", "deprecated", "replace", "rubric", "title"}


def rst_lines(text):
    """Classify every line of an RST source; see `Line`."""
    out = []
    in_block = None      # (kind, name, base_indent) while inside an indented literal/raw/comment body
    pending = None       # (kind, name, base_indent): the next indented text starts such a body
    opt_ctx = None       # (name, indent): option lines may follow a directive marker
    for no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        if not stripped:
            out.append(Line(no, raw, "blank", indent=indent))
            opt_ctx = None
            continue
        if in_block is not None:
            kind, name, base = in_block
            if indent > base:
                out.append(Line(no, raw, kind, name=name, indent=indent))
                continue
            in_block = None
        if opt_ctx is not None:
            m = _OPTION.match(raw)
            if m and len(m.group("ind")) > opt_ctx[1]:
                out.append(Line(no, raw, "option", name=opt_ctx[0], opt=m.group("opt"),
                                val=(m.group("val") or "").strip(), indent=indent))
                continue
            opt_ctx = None
        if pending is not None:
            kind, name, base = pending
            pending = None
            if indent > base:
                in_block = (kind, name, base)
                out.append(Line(no, raw, kind, name=name, indent=indent))
                continue
        d = _DIRECTIVE.match(raw)
        if d:
            name = d.group("name")
            arg = (d.group("arg") or "").strip()
            ind = len(d.group("ind"))
            opt_ctx = (name, ind)
            if name == "raw":
                pending = ("raw", name, ind)
            elif name in _LITERAL_BODY:
                pending = ("code", name, ind)
            if name in _PROSE_ARG and arg:
                out.append(Line(no, arg, "prose", name=name, indent=indent))
            else:
                out.append(Line(no, raw, "directive", name=name, val=arg, indent=indent))
            continue
        if _TARGET.match(raw):
            out.append(Line(no, raw, "directive", name="target", indent=indent))
            continue
        if stripped.startswith("..") and (len(stripped) == 2 or stripped[2] in " \t"):
            pending = ("comment", None, indent)
            out.append(Line(no, raw, "comment", indent=indent))
            continue
        out.append(Line(no, raw, "prose", indent=indent))
        if stripped.endswith("::"):
            pending = ("code", None, indent)
    return out


_IMG_DIRECTIVES = ("image", "figure", "thumbnail")


def image_refs(lines):
    """(line_no, reference) of every image/figure/thumbnail directive argument."""
    refs = []
    for ln in lines:
        if ln.kind == "directive" and ln.name in _IMG_DIRECTIVES and ln.val:
            refs.append((ln.no, ln.val.split()[0]))
    return refs


# --------------------------------------------------------------------------- pages and catalogs

def page_docname(page):
    """'content/a/b.rst' -> 'a/b' (the Sphinx docname, relative to content/)."""
    p = page.replace(os.sep, "/")
    if p.startswith("content/"):
        p = p[len("content/"):]
    return p[:-4] if p.endswith(".rst") else p


def catalogs_for_page(worktree, page, langs=None):
    """Existing per-language .po catalogs of a page: locale/<lang>/LC_MESSAGES/<docname>.po."""
    docname = page_docname(page)
    root = os.path.join(worktree, "locale")
    found = []
    if not os.path.isdir(root):
        return found
    for lang in sorted(os.listdir(root)):
        if lang == "sources" or (langs and lang not in langs):
            continue
        cand = os.path.join(root, lang, "LC_MESSAGES", docname + ".po")
        if os.path.isfile(cand):
            found.append(os.path.relpath(cand, worktree).replace(os.sep, "/"))
    return found
