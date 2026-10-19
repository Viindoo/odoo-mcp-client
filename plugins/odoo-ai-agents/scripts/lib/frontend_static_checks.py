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
    args = ap.parse_args(argv)
    dirs = [d for d in args.addons_dir if os.path.isdir(d)]
    if args.cmd == "imports":
        check_imports(args.files, dirs, args.base)
    else:
        check_xpath_branch(args.files, dirs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
