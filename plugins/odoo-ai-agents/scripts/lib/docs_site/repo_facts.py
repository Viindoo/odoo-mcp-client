#!/usr/bin/env python3
"""repo_facts.py - what a Sphinx docs repo states about itself.

  repo_facts.py --worktree W [--page content/<path>.rst] [--json]

Reads (never imports or executes) conf.py, Makefile, extensions/, locale/, content/ and, read-only,
git. A fact the repo does not state is the string "UNKNOWN". Stdlib only, python3 >= 3.8.

Report keys:
  series, series_agree, series_sources   conf.py version/release, the Makefile build dir, the branch
  languages                              Makefile LANGUAGES, conf.py supported_languages, locale/ dirs
  figure_language_filename               conf.py value, else the Sphinx default
  translate_target_rewrites_all_po       conf.py/extensions/Makefile replace sphinx_intl's update or
                                         resave every .po (the hazard of a plain `make translate`)
  po                                     wrap width (patch argument, else sampled) + a sibling header
  extensions                             registered extensions, directives and roles
  page (with --page)                     toctree_parent, image_dir, next_image_index,
                                         nearest_sibling_page, menu_path_syntax, commit_subject_samples
Exit: 0 report written, 2 the worktree is not a directory.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docs_site import (ARROW, UNKNOWN, emit, git, image_refs, normalize_series, page_docname,  # noqa: E402
                       po_header_fields, read_text, rst_lines)

DEFAULT_FIGURE_FILENAME = "{root}.{language}{ext}"


# --------------------------------------------------------------------------- conf.py

def conf_values(text):
    """Module-level literal assignments of a conf.py, by name (None when it will not parse)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            targets = [node.target.id]
            value_node = node.value
        else:
            continue
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, SyntaxError):
            if isinstance(value_node, ast.Name) and value_node.id in out:
                value = out[value_node.id]
            else:
                continue
        for name in targets:
            out[name] = value
    return out


def _regex_assign(text, name):
    m = re.search(r"^%s\s*=\s*['\"]([^'\"]+)['\"]" % re.escape(name), text, re.M)
    return m.group(1) if m else None


def conf_series(text, values):
    result = {}
    for key in ("version", "release"):
        raw = values.get(key) if values is not None else _regex_assign(text, key)
        result[key] = normalize_series(raw) if isinstance(raw, str) else None
    return result


# --------------------------------------------------------------------------- Makefile

_MAKE_VAR = r"^\s*(?:export\s+)?%s\s*[:?+]?=\s*(.*)$"


def make_var(text, name):
    m = re.search(_MAKE_VAR % re.escape(name), text, re.M)
    return m.group(1).strip() if m else None


def makefile_series(text):
    for m in re.finditer(r"^\s*(?:export\s+)?(\w*BUILD_?DIR\w*|OUTPUT\w*|HTML\w*DIR)\s*[:?+]?=\s*(.*)$",
                         text, re.M):
        token = normalize_series(m.group(2))
        if token:
            return token
    return None


def split_langs(value):
    if not value:
        return []
    return [p for p in re.split(r"[\s,]+", value.strip()) if p and not p.startswith("$")]


# --------------------------------------------------------------------------- scanning helpers

def _py_files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, n) for n in os.listdir(directory) if n.endswith(".py"))


_REPLACES_UPDATE = (
    re.compile(r"\bbasic\.update\s*="),                       # sphinx_intl.basic.update = wrapper
    re.compile(r"sphinx_intl.*\bupdate\b.*="),                 # from sphinx_intl import update as ...
)
_SAVE = re.compile(r"\.save\s*\(")
_PO_WALK = re.compile(r"\.po['\"]|\*\.po|glob.*\bpo\b")


def scan_hazard(sources):
    """(rewrites_all_po, evidence). `sources` is {relative name: text}."""
    evidence = []
    rewrites = False
    for name, text in sorted(sources.items()):
        lines = text.splitlines()
        replaces = [i for i, ln in enumerate(lines, 1) if any(p.search(ln) for p in _REPLACES_UPDATE)]
        saves = [i for i, ln in enumerate(lines, 1) if _SAVE.search(ln)]
        walks = [i for i, ln in enumerate(lines, 1) if _PO_WALK.search(ln)]
        if replaces:
            rewrites = True
            for i in replaces:
                evidence.append({"file": name, "line": i, "text": lines[i - 1].strip()[:120]})
        if saves and walks and "sphinx_intl" in text:
            rewrites = True
            for i in saves[:3]:
                evidence.append({"file": name, "line": i, "text": lines[i - 1].strip()[:120]})
    return rewrites, evidence


def scan_registrations(sources):
    directives, roles = set(), set()
    for text in sources.values():
        for m in re.finditer(r"(?:add_directive(?:_to_domain)?|register_directive)\(\s*(?:['\"][^'\"]+['\"]\s*,\s*)?['\"]([^'\"]+)['\"]", text):
            directives.add(m.group(1))
        for m in re.finditer(r"(?:add_role(?:_to_domain)?|register_(?:local|canonical)_role)\(\s*(?:['\"][^'\"]+['\"]\s*,\s*)?['\"]([^'\"]+)['\"]", text):
            roles.add(m.group(1))
    return sorted(directives), sorted(roles)


def po_files(worktree, limit=None):
    out = []
    base = os.path.join(worktree, "locale")
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != "sources")
        for name in sorted(filenames):
            if name.endswith(".po"):
                out.append(os.path.join(dirpath, name))
                if limit and len(out) >= limit:
                    return out
    return out


def wrap_width(worktree, sources, sample_files):
    for name, text in sorted(sources.items()):
        m = re.search(r"\b(?:line_width|wrapwidth)\s*=\s*(\d+)", text)
        if m:
            return {"value": int(m.group(1)), "source": "patch:" + name}
    best = 0
    for path in sample_files:
        text = read_text(path) or ""
        for ln in text.splitlines():
            if ln and not ln.startswith("#"):
                best = max(best, len(ln))
    if best:
        return {"value": best, "source": "sample"}
    return {"value": UNKNOWN, "source": UNKNOWN}


# --------------------------------------------------------------------------- page facts

def _rel(worktree, path):
    return os.path.relpath(path, worktree).replace(os.sep, "/")


def _toctree_entries(text):
    lines = rst_lines(text)
    entries, glob = [], False
    for ln in lines:
        if ln.kind == "option" and ln.name == "toctree" and ln.opt == "glob":
            glob = True
        if ln.kind == "code" and ln.name == "toctree":
            entry = ln.text.strip()
            if not entry:
                continue
            m = re.match(r"^.*<([^>]+)>$", entry)
            entries.append((m.group(1) if m else entry).strip())
    return entries, glob


def toctree_parent(worktree, page):
    pdir = os.path.dirname(page)
    tried = []
    for cand in (pdir + ".rst", pdir + "/index.rst"):
        if cand == page:
            continue
        tried.append(cand)
        text = read_text(os.path.join(worktree, cand))
        if text is None:
            continue
        entries, glob = _toctree_entries(text)
        cand_dir = os.path.dirname(cand)
        content_root = "content"
        target = page_docname(page)
        listed = False
        for entry in entries:
            if entry.startswith("/"):
                resolved = os.path.normpath(content_root + entry)
            else:
                resolved = os.path.normpath(os.path.join(cand_dir, entry))
            resolved = resolved.replace(os.sep, "/")
            if resolved.endswith(".rst"):
                resolved = resolved[:-4]
            doc = resolved[len(content_root) + 1:] if resolved.startswith(content_root + "/") else resolved
            if doc == target:
                listed = True
            elif glob and re.fullmatch(re.escape(doc).replace(r"\*", "[^/]*"), target):
                listed = True
        return {"path": cand, "listed": listed, "entries": len(entries), "candidates_tried": tried}
    return {"path": UNKNOWN, "listed": UNKNOWN, "entries": 0, "candidates_tried": tried}


def _resolve_ref(file_rel, ref):
    if ref.startswith("/"):
        return os.path.normpath("content" + ref).replace(os.sep, "/")
    return os.path.normpath(os.path.join(os.path.dirname(file_rel), ref)).replace(os.sep, "/")


def _classify_dir(image_dir, page_dir, stem):
    base = os.path.basename(image_dir)
    if image_dir == page_dir:
        return "same-dir"
    if base == "img-" + stem:
        return "img-<basename>"
    if base == "img":
        return "img"
    if base.startswith("img-"):
        return "img-<basename>"
    return "other:" + base


def image_dir_facts(worktree, page):
    pdir = os.path.dirname(page)
    stem = os.path.splitext(os.path.basename(page))[0]
    abs_dir = os.path.join(worktree, pdir)
    siblings = []
    if os.path.isdir(abs_dir):
        siblings = sorted(n for n in os.listdir(abs_dir) if n.endswith(".rst"))
    counts = {}
    own_dir = None
    for name in siblings:
        rel = pdir + "/" + name
        text = read_text(os.path.join(worktree, rel)) or ""
        refs = image_refs(rst_lines(text))
        for _no, ref in refs:
            if re.match(r"^[a-z]+://", ref):
                continue
            idir = os.path.dirname(_resolve_ref(rel, ref))
            sstem = os.path.splitext(name)[0]
            conv = _classify_dir(idir, pdir, sstem)
            counts[conv] = counts.get(conv, 0) + 1
            if rel == page and own_dir is None:
                own_dir = idir
    convention = UNKNOWN
    if counts:
        convention = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    if own_dir is not None:
        image_dir, source = own_dir, "page"
    elif convention == "img-<basename>":
        image_dir, source = pdir + "/img-" + stem, "convention"
    elif convention == "img":
        image_dir, source = pdir + "/img", "convention"
    elif convention == "same-dir":
        image_dir, source = pdir, "convention"
    else:
        image_dir, source = UNKNOWN, UNKNOWN
    exists = False
    next_index = UNKNOWN
    if image_dir != UNKNOWN:
        full = os.path.join(worktree, image_dir)
        exists = os.path.isdir(full)
        top = 0
        if exists:
            for n in os.listdir(full):
                m = re.match(r"^(\d+)-", n)
                if m:
                    top = max(top, int(m.group(1)))
        next_index = top + 1
    return {"convention": convention, "convention_counts": counts, "image_dir": image_dir,
            "image_dir_source": source, "image_dir_exists": exists, "next_image_index": next_index}


def nearest_sibling(worktree, page):
    pdir = os.path.dirname(page)
    out = git(worktree, "log", "--format=@%ct", "--name-only", "--", ":(glob)%s/*.rst" % pdir)
    if out is None:
        return {"path": UNKNOWN, "commit_time": UNKNOWN}
    seen, ts = {}, None
    for ln in out.splitlines():
        if ln.startswith("@"):
            ts = int(ln[1:])
        elif ln.strip() and ts is not None:
            seen.setdefault(ln.strip(), ts)
    best = None
    for path, when in seen.items():
        if path == page or not os.path.isfile(os.path.join(worktree, path)):
            continue
        if best is None or (when, path) > (best[1], best[0]):
            best = (path, when)
    if best is None:
        return {"path": UNKNOWN, "commit_time": UNKNOWN}
    return {"path": best[0], "commit_time": best[1]}


def menu_path_syntax(worktree, page):
    pdir = os.path.join(worktree, os.path.dirname(page))
    bold = re.compile(r"\*\*[^*\n]*%s[^*\n]*\*\*" % ARROW)
    bold_gt = re.compile(r"\*\*[^*\n]* > [^*\n]*\*\*")
    counts = {"bold_arrow": 0, "bold_gt": 0, "menuselection": 0, "files": 0}
    for dirpath, dirnames, filenames in os.walk(pdir):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            if not name.endswith(".rst"):
                continue
            text = read_text(os.path.join(dirpath, name)) or ""
            counts["files"] += 1
            counts["bold_arrow"] += len(bold.findall(text))
            counts["bold_gt"] += len(bold_gt.findall(text))
            counts["menuselection"] += text.count(":menuselection:")
    ranked = sorted((counts[k], k) for k in ("bold_arrow", "bold_gt", "menuselection"))
    preferred = UNKNOWN
    if ranked[-1][0] > 0 and ranked[-1][0] > ranked[-2][0]:
        preferred = ranked[-1][1]
    counts["preferred"] = preferred
    return counts


def page_facts(worktree, page):
    subjects = git(worktree, "log", "-10", "--format=%s")
    facts = {
        "page": page,
        "page_exists": os.path.isfile(os.path.join(worktree, page)),
        "toctree_parent": toctree_parent(worktree, page),
        "nearest_sibling_page": nearest_sibling(worktree, page),
        "menu_path_syntax": menu_path_syntax(worktree, page),
        "commit_subject_samples": subjects.splitlines() if subjects is not None else UNKNOWN,
    }
    facts.update(image_dir_facts(worktree, page))
    return facts


# --------------------------------------------------------------------------- the report

def collect(worktree, page=None):
    conf_text = read_text(os.path.join(worktree, "conf.py"))
    make_text = read_text(os.path.join(worktree, "Makefile"))
    values = conf_values(conf_text) if conf_text is not None else None

    branch_out = git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_out.strip() if branch_out else None
    if branch == "HEAD":
        branch = None
    conf_s = conf_series(conf_text or "", values) if conf_text is not None else {"version": None, "release": None}
    sources = {
        "conf_version": conf_s["version"],
        "conf_release": conf_s["release"],
        "makefile_builddir": makefile_series(make_text) if make_text else None,
        "branch": normalize_series(branch) if branch else None,
    }
    stated = sorted(set(v for v in sources.values() if v))
    series = stated[0] if len(stated) == 1 else UNKNOWN
    report = {
        "worktree": worktree,
        "branch": branch if branch else UNKNOWN,
        "series": series,
        "series_agree": len(stated) == 1,
        "series_sources": sources,
    }

    conf_langs = []
    if values is not None and "supported_languages" in values:
        sl = values["supported_languages"]
        if isinstance(sl, dict):
            conf_langs = [str(k) for k in sl]
        elif isinstance(sl, (list, tuple, set)):
            conf_langs = [str(k) for k in sl]
    elif conf_text:
        m = re.search(r"supported_languages\s*=\s*[\[{(]([^\]})]*)[\]})]", conf_text)
        if m:
            conf_langs = re.findall(r"['\"]([\w-]+)['\"]\s*(?::|,|$)", m.group(1))
    make_langs = split_langs(make_var(make_text, "LANGUAGES")) if make_text else []
    locale_dirs = []
    locale_root = os.path.join(worktree, "locale")
    if os.path.isdir(locale_root):
        locale_dirs = sorted(d for d in os.listdir(locale_root)
                             if d != "sources" and os.path.isdir(os.path.join(locale_root, d)))
    union = sorted(set(make_langs) | set(conf_langs) | set(locale_dirs))
    report["languages"] = {"makefile": make_langs, "conf_supported_languages": conf_langs,
                           "locale_dirs": locale_dirs, "all": union if union else UNKNOWN}

    if values is not None and isinstance(values.get("figure_language_filename"), str):
        report["figure_language_filename"] = {"value": values["figure_language_filename"], "source": "conf.py"}
    else:
        m = re.search(r"^figure_language_filename\s*=\s*['\"]([^'\"]+)['\"]", conf_text or "", re.M)
        if m:
            report["figure_language_filename"] = {"value": m.group(1), "source": "conf.py"}
        else:
            report["figure_language_filename"] = {"value": DEFAULT_FIGURE_FILENAME, "source": "sphinx-default"}

    ext_files = _py_files(os.path.join(worktree, "extensions"))
    scan_sources = {}
    if conf_text is not None:
        scan_sources["conf.py"] = conf_text
    if make_text is not None:
        scan_sources["Makefile"] = make_text
    ext_sources = {}
    for path in ext_files:
        text = read_text(path)
        if text is not None:
            scan_sources[_rel(worktree, path)] = text
            ext_sources[_rel(worktree, path)] = text
    if conf_text is None:
        report["translate_target_rewrites_all_po"] = UNKNOWN
        report["rewrite_evidence"] = []
    else:
        rewrites, evidence = scan_hazard(scan_sources)
        report["translate_target_rewrites_all_po"] = rewrites
        report["rewrite_evidence"] = evidence

    sample = po_files(worktree, limit=5)
    header = {}
    header_file = None
    for path in sample:
        header = po_header_fields(read_text(path) or "")
        if header:
            header_file = _rel(worktree, path)
            break
    report["po"] = {
        "wrap_width": wrap_width(worktree, scan_sources, sample),
        "header_sample": {
            "file": header_file or UNKNOWN,
            "Language": header.get("Language", UNKNOWN),
            "Generated-By": header.get("Generated-By", UNKNOWN),
            "Content-Type": header.get("Content-Type", UNKNOWN),
            "Plural-Forms": header.get("Plural-Forms", UNKNOWN),
        },
    }

    ext_list = []
    if values is not None and isinstance(values.get("extensions"), (list, tuple)):
        ext_list = [e for e in values["extensions"] if isinstance(e, str)]
    directives, roles = scan_registrations(ext_sources if ext_sources else scan_sources)
    if conf_text is not None and not ext_sources:
        directives, roles = scan_registrations({"conf.py": conf_text})
    elif conf_text is not None:
        d2, r2 = scan_registrations({"conf.py": conf_text})
        directives = sorted(set(directives) | set(d2))
        roles = sorted(set(roles) | set(r2))
    report["extensions"] = {"conf": ext_list, "files": [_rel(worktree, p) for p in ext_files],
                            "directives": directives, "roles": roles}

    if page:
        report["page"] = page_facts(worktree, page.replace(os.sep, "/"))
    report["unknown"] = sorted(_unknown_keys(report))
    return report


def _unknown_keys(node, prefix=""):
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            found.extend(_unknown_keys(v, prefix + str(k) + "."))
    elif node == UNKNOWN:
        found.append(prefix.rstrip("."))
    return found


def summary(report):
    lines = ["series: %s (agree: %s) sources: %s" % (
        report["series"], report["series_agree"],
        ", ".join("%s=%s" % (k, v) for k, v in sorted(report["series_sources"].items()) if v) or "none")]
    lines.append("languages: %s" % (report["languages"]["all"],))
    lines.append("figure_language_filename: %s (%s)" % (
        report["figure_language_filename"]["value"], report["figure_language_filename"]["source"]))
    lines.append("translate_target_rewrites_all_po: %s" % report["translate_target_rewrites_all_po"])
    lines.append("po wrap width: %s (%s)" % (report["po"]["wrap_width"]["value"], report["po"]["wrap_width"]["source"]))
    if "page" in report:
        p = report["page"]
        lines.append("toctree parent: %s (listed: %s)" % (p["toctree_parent"]["path"], p["toctree_parent"]["listed"]))
        lines.append("image dir: %s, next index: %s" % (p["image_dir"], p["next_image_index"]))
        lines.append("nearest sibling: %s" % p["nearest_sibling_page"]["path"])
        lines.append("menu path syntax: %s" % p["menu_path_syntax"]["preferred"])
    if report["unknown"]:
        lines.append("UNKNOWN: %s" % ", ".join(report["unknown"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description="Facts a Sphinx docs repo states about itself.")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--page", help="content/<path>.rst, relative to the worktree")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.worktree):
        sys.stderr.write("worktree is not a directory: %s\n" % args.worktree)
        return 2
    report = collect(args.worktree, args.page)
    emit(report, args.json, summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
