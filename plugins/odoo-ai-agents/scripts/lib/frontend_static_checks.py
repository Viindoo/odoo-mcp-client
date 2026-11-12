#!/usr/bin/env python3
"""frontend_static_checks.py - static reference checks run by verify-frontend.sh (Tier 2).

Stdlib only; lxml is used for XPath evaluation when it is installed.

Subcommands (each prints one finding per line as `BLOCK|<file>:<line>|<msg>`,
`WARN|...` or `INFO|...`, and exits 0 - the caller decides what a BLOCK means):

  imports --addons-dir D [--addons-dir D ...] [--base REF] <js files...>
      A NEW `@<module>/<path>` import must resolve to
      `<D>/<module>/static/src/<path>.js` (or the path as written) in some addons dir.
      "New" means an untracked file in full, otherwise only the `+` lines of
      `git diff -U0 REF -- file`. A module found in an addons dir whose file is missing
      is a BLOCK; a module in no known addons dir is an INFO, never a BLOCK (the
      checkout simply may not be available). `@odoo/...` aliases are never checked.

  xpath-branch --addons-dir D [--addons-dir D ...] <xml files...>
      An `<xpath position="before|after">` of a template extension (client `t-inherit`,
      or server `inherit_id`) must not land between a `t-if`/`t-elif` node and the
      `t-elif`/`t-else` node that continues its chain: the inserted node would take the
      chain over. An inherited template that cannot be found, or an XPath that cannot
      be evaluated or matches nothing, is a WARN, never a BLOCK.

  scheme [--odoo-root R] [--base REF] <scss/css, xml and js files...>
      A change must not fix a colour scheme (snippets/odoo-ui-contract.md § 2). Only the
      lines the change adds are examined (an untracked file in full):
      WARN a literal colour in a stylesheet other than `*.dark.scss`, in a `style` attribute
      of an XML view or template, or in a JS string, and WARN a class that fixes a scheme
      (`bg-white`, `text-dark`, ...) in an XML class list.
      For every `*.dark.scss` given, the manifest of its module (read as a literal) must
      register it in a dark bundle (BLOCK when it does not) and must keep it out
      of every other bundle that includes it by path or glob (BLOCK otherwise). A manifest
      that cannot be read is a WARN. With `--odoo-root` on a checkout whose `web` declares
      no dark bundle, the registration part is skipped with one INFO line.
"""
import argparse
import copy
import glob
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from xml.parsers import expat

try:  # optional: full XPath + Odoo's hasclass
    from lxml import etree as LET
except Exception:  # pragma: no cover - exercised only where lxml is absent
    LET = None

IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(?\s*)(["'])@([A-Za-z0-9_]+)/([^"']+)\1"""
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

XPATH_GUIDE = "coding_guidelines/<series>/xml.md § Inheriting QWeb templates"
UI_CONTRACT = "snippets/odoo-ui-contract.md § 2"


def _emit(sev, file, line, msg):
    loc = f"{file}:{line}" if line else str(file)
    print(f"{sev}|{loc}|{msg}")


# ---------------------------------------------------------------------------
# imports
# ---------------------------------------------------------------------------
def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, *args], capture_output=True, text=True, check=False
    )


def _added_lines(path, base):
    """[(lineno, text)] of the lines this change adds to `path`, or None when the diff
    cannot be taken (the caller then reports it instead of guessing)."""
    abspath = os.path.abspath(path)
    cwd = os.path.dirname(abspath)
    try:
        with open(abspath, encoding="utf-8", errors="replace") as fh:
            content = fh.read().splitlines()
    except OSError:
        return []
    tracked = _git(cwd, "ls-files", "--error-unmatch", "--", abspath).returncode == 0
    if not tracked:
        return list(enumerate(content, 1))
    res = _git(cwd, "diff", "-U0", base, "--", abspath)
    if res.returncode != 0:
        return None
    out, lineno = [], 0
    for ln in res.stdout.splitlines():
        m = HUNK_RE.match(ln)
        if m:
            lineno = int(m.group(1))
            continue
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            out.append((lineno, ln[1:]))
            lineno += 1
    return out


def check_imports(files, addons_dirs, base):
    for path in files:
        added = _added_lines(path, base)
        if added is None:
            _emit("INFO", path, 0, f"cannot diff against {base}; imports not checked")
            continue
        for lineno, text in added:
            stripped = text.lstrip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for m in IMPORT_RE.finditer(text):
                module, rel = m.group(2), m.group(3)
                if module == "odoo":
                    continue
                known = [d for d in addons_dirs if os.path.isdir(os.path.join(d, module))]
                if not known:
                    _emit("INFO", path, lineno,
                          f"import @{module}/{rel}: module {module} is in no known addons "
                          "dir, not checked")
                    continue
                resolved = False
                for d in known:
                    target = os.path.normpath(os.path.join(d, module, "static", "src", rel))
                    if os.path.isfile(target + ".js") or os.path.isfile(target):
                        resolved = True
                        break
                if not resolved:
                    d = known[0]
                    _emit("BLOCK", path, lineno,
                          f"import @{module}/{rel} does not resolve: "
                          f"{d}/{module}/static/src/{rel}(.js) missing")


# ---------------------------------------------------------------------------
# xpath-branch
# ---------------------------------------------------------------------------
class _El(ET.Element):
    """ElementTree element that remembers its source line (stdlib fallback)."""


def _parse_et(path):
    root, stack = None, []

    def start(name, attrs):
        nonlocal root
        el = _El(name, dict(attrs))
        el.line = parser.CurrentLineNumber
        if stack:
            stack[-1].append(el)
        else:
            root = el
        stack.append(el)

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    with open(path, "rb") as fh:
        parser.Parse(fh.read(), True)
    return root


def _parse(path):
    if LET is not None:
        p = LET.XMLParser(remove_comments=True, remove_pis=True, resolve_entities=False)
        return LET.parse(path, p).getroot()
    return _parse_et(path)


def _line(el):
    return getattr(el, "sourceline", None) or getattr(el, "line", 0) or 0


def _kids(el):
    return [c for c in el if isinstance(c.tag, str)]


def _parent_map(root):
    return {c: p for p in root.iter() for c in p}


def _hasclass(context, *classes):
    have = (context.context_node.get("class") or "").split()
    return all(c in have for c in classes)


if LET is not None:
    LET.FunctionNamespace(None)["hasclass"] = _hasclass


def _is_view_record(el):
    return el.tag == "record" and el.get("model") == "ir.ui.view"


def _is_base_view(el):
    """A server view definition that is itself not an extension of another view."""
    if el.tag == "template":
        return el.get("inherit_id") is None
    if _is_view_record(el):
        return not any(f.get("name") == "inherit_id" for f in _kids(el) if f.tag == "field")
    return False


def _extensions(root):
    """Yield (kind, ref, container) for each template extension in the tree."""
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.get("t-inherit"):
            yield "client", el.get("t-inherit"), el
        elif el.tag == "template" and el.get("inherit_id"):
            yield "server", el.get("inherit_id"), el
        elif _is_view_record(el):
            for f in _kids(el):
                if f.tag == "field" and f.get("name") == "inherit_id" and f.get("ref"):
                    yield "server", f.get("ref"), el


def _xpaths(container):
    for x in container.iter("xpath"):
        yield x


def _template_roots(root, kind, ref):
    """Elements in `root` that define the template `ref`."""
    module, _, bare = ref.rpartition(".")
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if kind == "client":
            if el.get("t-name") in (ref, bare) and el.get("t-inherit") is None:
                yield el
        elif el.get("id") in (ref, bare) and _is_base_view(el):
            yield el


def _as_eval_root(el):
    """The element an inherited template's XPath is evaluated against (a detached copy,
    so a leading `//` is anchored at the template and not at the whole file)."""
    if _is_view_record(el):
        arch = next((f for f in _kids(el) if f.get("name") == "arch"), None)
        if arch is None:
            return None
        kids = _kids(arch)
        el = kids[0] if len(kids) == 1 else arch
    root = copy.deepcopy(el) if LET is not None else el
    if root.tag in ("template", "field"):
        root.tag = "t"
    return root


class _TemplateFinder:
    def __init__(self, addons_dirs, own_trees):
        self.dirs = addons_dirs
        self.own = own_trees
        self.cache = {}

    def _tree(self, path):
        if path not in self.cache:
            try:
                self.cache[path] = _parse(path)
            except Exception:
                self.cache[path] = None
        return self.cache[path]

    def _files(self, module):
        pats = []
        for d in self.dirs:
            base = os.path.join(d, module) if module else os.path.join(d, "*")
            for sub in ("static", "views", "templates"):
                pats.append(os.path.join(base, sub, "**", "*.xml"))
        seen = []
        for pat in pats:
            for f in sorted(glob.glob(pat, recursive=True)):
                if f not in seen:
                    seen.append(f)
        return seen

    def find(self, kind, ref):
        module, _, bare = ref.rpartition(".")
        for tree in self.own:
            for el in _template_roots(tree, kind, ref):
                return el
        scopes = ([module] if module else []) + [""]
        for scope in scopes:
            for f in self._files(scope):
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        if bare not in fh.read():
                            continue
                except OSError:
                    continue
                tree = self._tree(f)
                if tree is None:
                    continue
                for el in _template_roots(tree, kind, ref):
                    return el
        return None


def _first_match(root, expr):
    """(element|None, reason). Evaluate `expr` against the template copy `root`."""
    if LET is not None:
        try:
            hits = root.xpath(expr)
        except Exception as exc:
            return None, f"xpath cannot be evaluated ({type(exc).__name__})"
        hits = [h for h in hits if isinstance(getattr(h, "tag", None), str)]
    else:
        e = expr.strip()
        if e.startswith("//"):
            e = "." + e
        elif not e.startswith("."):
            return None, "xpath form needs lxml to be evaluated"
        try:
            hits = root.findall(e)
        except Exception as exc:
            return None, f"xpath cannot be evaluated without lxml ({type(exc).__name__})"
    if not hits:
        return None, "xpath matches nothing in the inherited template"
    return hits[0], ""


def _chain_continues_before(node):
    return node.get("t-if") is not None or node.get("t-elif") is not None


def _chain_continues_after(node):
    return node.get("t-elif") is not None or node.get("t-else") is not None


def check_xpath_branch(files, addons_dirs):
    trees = {}
    for path in files:
        try:
            trees[path] = _parse(path)
        except Exception as exc:
            _emit("WARN", path, 0, f"xml not parsed ({type(exc).__name__}); xpath-branch "
                  "not checked")
    finder = _TemplateFinder(addons_dirs, list(trees.values()))
    for path, root in trees.items():
        for kind, ref, container in _extensions(root):
            for xp in _xpaths(container):
                pos = xp.get("position")
                if pos not in ("before", "after"):
                    continue
                inserted = _kids(xp)
                if not inserted:
                    continue
                line = _line(xp)
                tmpl = finder.find(kind, ref)
                if tmpl is None:
                    _emit("WARN", path, line,
                          f"inherited template {ref} not found in the known addons dirs; "
                          "xpath position not checked")
                    continue
                eval_root = _as_eval_root(tmpl)
                if eval_root is None:
                    _emit("WARN", path, line, f"inherited template {ref} has no arch; "
                          "xpath position not checked")
                    continue
                target, reason = _first_match(eval_root, xp.get("expr", ""))
                if target is None:
                    _emit("WARN", path, line, f"{reason}; position not checked")
                    continue
                parents = _parent_map(eval_root)
                parent = parents.get(target)
                if parent is None:
                    continue
                sibs = _kids(parent)
                idx = sibs.index(target)
                if pos == "after":
                    a = target
                    b = sibs[idx + 1] if idx + 1 < len(sibs) else None
                else:
                    a = sibs[idx - 1] if idx > 0 else None
                    b = target
                if a is None or b is None:
                    continue
                if not (_chain_continues_before(a) and _chain_continues_after(b)):
                    continue
                if all(i.get("t-elif") is not None for i in inserted):
                    continue
                _emit("BLOCK", path, line,
                      "inserting between a t-if/t-elif and its t-elif/t-else breaks the "
                      f"conditional chain - see {XPATH_GUIDE}")


# ---------------------------------------------------------------------------
# scheme
# ---------------------------------------------------------------------------
# A colour function counts only when its first argument is a number: `rgba($var, .5)` and
# `rgb(var(--x))` derive from a variable and are not literals.
HEX_RE = re.compile(
    r"(?<![\w&#$-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
COLOR_FN_RE = re.compile(r"(?<![\w-])(?P<fn>rgba?|hsla?)\(\s*[-+]?(?:\d|\.\d)")
BARE_NAME_RE = re.compile(r"(?<![\w$#.@-])(?:white|black)(?![\w(-])")
DECL_RE = re.compile(
    r"""(?:^|[;{(,])\s*(?P<prop>[$@]?[\w-]+|["'][^"']*["'])\s*:(?!:)\s*(?P<val>[^;{}]*)""")
SCHEME_CLASSES = ("bg-white", "bg-light", "bg-dark", "bg-black", "text-dark", "text-white",
                  "text-black", "text-light", "border-light", "border-dark", "border-white")
SCHEME_CLASS_RE = re.compile(
    r"(?<![\w-])(%s)(?![\w-])" % "|".join(re.escape(c) for c in SCHEME_CLASSES))
XML_ATTR_RE = re.compile(
    r"""(?<![\w:.-])(?P<name>t-attf-class|t-att-class|t-attf-style|t-att-style|class|style)"""
    r"""\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""", re.S)
STYLE_COLOR_DECL_RE = re.compile(
    r"(?<![\w-])(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?"
    r"|outline(?:-color)?|fill|stroke|box-shadow|text-shadow|caret-color|accent-color)"
    r"\s*:\s*(?P<val>[^;]*)")


def _blank(text):
    return re.sub(r"[^\n]", " ", text)


def _blank_css(text, line_comments):
    """Lines of `text` with comments, string contents and `url(...)` contents replaced by
    spaces, so a pattern run on a line never reads prose or a data URI."""
    out, i, n = [], 0, len(text)
    while i < n:
        c, two = text[i], text[i:i + 2]
        if two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(_blank(text[i:j]))
        elif line_comments and two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
        elif c in "\"'":
            k = i + 1
            while k < n and text[k] != c and text[k] != "\n":
                k += 2 if text[k] == "\\" else 1
            k = min(k, n)
            closed = k < n and text[k] == c
            out.append(c + _blank(text[i + 1:k]) + (c if closed else ""))
            j = k + 1 if closed else k
        elif (c in "uU" and text[i:i + 4].lower() == "url("
              and not re.match(r"[\w-]", text[i - 1:i])):
            j = text.find(")", i)
            j = n if j < 0 else j
            out.append(text[i:i + 4] + _blank(text[i + 4:j]))
        else:
            out.append(c)
            j = i + 1
        i = j
    return "".join(out).split("\n")


def _literal_colour(text, names=False):
    """The first literal colour in `text` as it should be quoted, or None."""
    for rx in (HEX_RE, COLOR_FN_RE) + ((BARE_NAME_RE,) if names else ()):
        hit = rx.search(text)
        if hit:
            return hit.group("fn") + "(...)" if rx is COLOR_FN_RE else hit.group(0)
    return None


def _css_literal(code):
    """The first literal colour on one comment-free stylesheet line, or None. A hex or a
    colour name is read only as a declaration value, never in a selector (`#fade {`)."""
    fn = COLOR_FN_RE.search(code)
    if fn:
        return fn.group("fn") + "(...)"
    decls = list(DECL_RE.finditer(code))
    for d in decls:
        lit = _literal_colour(d.group("val"), names=True)
        if lit:
            return lit
    if not decls and "{" not in code and code.rstrip().endswith(";"):
        return _literal_colour(code)
    return None


def _read_full(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _scheme_stylesheet(path, added):
    text = _read_full(path)
    if text is None:
        return
    code = _blank_css(text, line_comments=not path.endswith(".css"))
    for lineno, _ in added:
        lit = _css_literal(code[lineno - 1]) if 0 < lineno <= len(code) else None
        if lit:
            _emit("WARN", path, lineno,
                  f"literal colour {lit}: use a core SCSS variable, or a component custom "
                  f"property with a core variable as fallback - see {UI_CONTRACT}")


def _scheme_xml(path, added):
    text = _read_full(path)
    if text is None:
        return
    text = re.sub(r"<!--.*?-->", lambda m: _blank(m.group(0)), text, flags=re.S)
    changed = {n for n, _ in added}
    for m in XML_ATTR_RE.finditer(text):
        first = text.count("\n", 0, m.start()) + 1
        last = first + text.count("\n", m.start(), m.end())
        lines = [n for n in range(first, last + 1) if n in changed]
        if not lines:
            continue
        name, val = m.group("name"), m.group("val")
        if name.endswith("class"):
            hit = SCHEME_CLASS_RE.search(val)
            if hit:
                _emit("WARN", path, lines[0],
                      f"class {hit.group(1)} fixes a colour scheme: use a core class that "
                      f"follows the theme (bg-view, text-body, text-muted, text-bg-<status>) - "
                      f"see {UI_CONTRACT}")
            continue
        for decl in STYLE_COLOR_DECL_RE.finditer(val):
            lit = _literal_colour(decl.group("val"), names=True)
            if lit:
                _emit("WARN", path, lines[0],
                      f"style attribute fixes the colour {lit}: use a core class or a "
                      f"component custom property instead - see {UI_CONTRACT}")
                break


def _js_strings(text):
    """(first line, last line, content) of every string literal outside comments."""
    out, i, n, line = [], 0, len(text), 1
    while i < n:
        c, two = text[i], text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            i = j
        elif c in "\"'`":
            j = i + 1
            while j < n and text[j] != c and (c == "`" or text[j] != "\n"):
                j += 2 if text[j] == "\\" else 1
            j = min(j, n)
            out.append((line, line + text.count("\n", i, j), text[i + 1:j]))
            line += text.count("\n", i, j)
            i = j + 1
        else:
            line += c == "\n"
            i += 1
    return out


def _scheme_js(path, added):
    text = _read_full(path)
    if text is None:
        return
    changed = {n for n, _ in added}
    for first, last, content in _js_strings(text):
        lines = [n for n in range(first, last + 1) if n in changed]
        lit = _literal_colour(content) if lines else None
        if lit:
            _emit("WARN", path, lines[0],
                  f"literal colour {lit} in a string: take it from a core CSS variable or "
                  f"class, or the web client's colour helpers - see {UI_CONTRACT}")


def _glob_re(pattern):
    """Regex of a bundle path or glob: `**` crosses directories, `*` and `?` stay in one."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _bundle_holds(entries, rel):
    """Whether a bundle's entries end up holding `rel`: later entries win, as in Odoo."""
    held = False
    for entry in entries:
        if isinstance(entry, str):
            op, args = "append", [entry]
        elif isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], str):
            op, args = entry[0], [a for a in entry[1:] if isinstance(a, str)]
        else:
            continue
        if op in ("append", "prepend") and len(args) == 1:
            held = held or bool(_glob_re(args[0]).match(rel))
        elif op == "remove" and len(args) == 1 and _glob_re(args[0]).match(rel):
            held = False
        elif op in ("before", "after") and len(args) == 2:
            held = held or bool(_glob_re(args[1]).match(rel))
        elif op == "replace" and len(args) == 2:
            held = (held and not _glob_re(args[0]).match(rel)) or bool(_glob_re(args[1]).match(rel))
    return held


def _module_dir(path):
    d = os.path.dirname(os.path.abspath(path))
    while d != os.path.dirname(d):
        if any(os.path.isfile(os.path.join(d, n)) for n in ("__manifest__.py", "__openerp__.py")):
            return d
        d = os.path.dirname(d)
    return None


def _source_facts():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import odoo_source_facts
    return odoo_source_facts


def _is_dark_bundle(bundle):
    # Core and themes name dark bundles both ways: `web.assets_web_dark`,
    # `web.dark_mode_assets_backend`.
    return "dark" in str(bundle).rsplit(".", 1)[-1]


def _check_dark_registration(path, facts):
    module = _module_dir(path)
    manifest = facts.module_manifest(module) if module else None
    if manifest is None:
        _emit("WARN", path, 1, "manifest not readable, dark registration not checked")
        return
    assets = manifest.get("assets")
    assets = assets if isinstance(assets, dict) else {}
    rel = os.path.relpath(os.path.abspath(path), os.path.dirname(module)).replace(os.sep, "/")
    if not any(_is_dark_bundle(b) and _bundle_holds(e, rel) for b, e in assets.items()):
        _emit("BLOCK", path, 1,
              f"{rel} is in no dark bundle of the module manifest: add it to the dark "
              f"bundle, as core does with web.assets_web_dark - see {UI_CONTRACT}")
    for bundle, entries in assets.items():
        # A private sub-bundle (`web._assets_core`) is only reached through an `include`, and
        # the bundle that includes it owns the removal.
        private = str(bundle).rsplit(".", 1)[-1].startswith("_")
        if not private and not _is_dark_bundle(bundle) and _bundle_holds(entries, rel):
            _emit("BLOCK", path, 1,
                  f"{rel} stays in the light bundle {bundle}: add ('remove', '{rel}') or a "
                  f"glob covering it to that bundle - see {UI_CONTRACT}")


def check_scheme(files, base, odoo_root):
    facts = _source_facts()
    registration = True
    if odoo_root and facts.locate_odoo_root(odoo_root) and not facts.dark_asset_bundle(odoo_root):
        registration = False
        if any(f.endswith(".dark.scss") for f in files):
            _emit("INFO", odoo_root, 0,
                  "web declares no dark asset bundle on this series; dark registration "
                  "not checked")
    scanners = {".scss": _scheme_stylesheet, ".css": _scheme_stylesheet,
                ".xml": _scheme_xml, ".js": _scheme_js}
    for path in files:
        if path.endswith(".dark.scss"):
            if registration:
                _check_dark_registration(path, facts)
            continue
        scan = scanners.get(os.path.splitext(path)[1])
        if scan is None:
            continue
        added = _added_lines(path, base)
        if added is None:
            _emit("INFO", path, 0, f"cannot diff against {base}; colour scheme not checked")
            continue
        scan(path, added)


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="frontend_static_checks.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("imports", "xpath-branch"):
        p = sub.add_parser(name)
        p.add_argument("--addons-dir", action="append", default=[])
        if name == "imports":
            p.add_argument("--base", default="HEAD")
        p.add_argument("files", nargs="*")
    scheme = sub.add_parser("scheme")
    scheme.add_argument("--base", default="HEAD")
    scheme.add_argument("--odoo-root", default=None)
    scheme.add_argument("files", nargs="*")
    args = ap.parse_args(argv)
    if args.cmd == "scheme":
        check_scheme(args.files, args.base, args.odoo_root)
        return 0
    dirs = [d for d in args.addons_dir if os.path.isdir(d)]
    if args.cmd == "imports":
        check_imports(args.files, dirs, args.base)
    else:
        check_xpath_branch(args.files, dirs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
