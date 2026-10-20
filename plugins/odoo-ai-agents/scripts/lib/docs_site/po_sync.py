#!/usr/bin/env python3
"""po_sync.py - keep the gettext catalogs of a Sphinx docs repo in step with its RST pages.

Runs under the DOCS REPO's own venv python (it needs Sphinx and Babel from the repo's
requirements.txt; both are imported lazily and a missing one exits 3 with a one-line remedy).
It never runs `make translate` or sphinx-intl: the repo's conf.py may patch sphinx-intl so that
every .po in the repo is re-saved and every fuzzy flag is stripped (a repo-wide diff in which
guesses become accepted translations). This tool touches ONLY the catalogs of the pages it is
given and never marks a guess as fuzzy.

Layout it assumes (one gettext domain per page; verify against the repo, do not trust this text):

    content/<p>.rst                      the English source page
    locale/sources/<p>.pot               its template
    locale/<lang>/LC_MESSAGES/<p>.po     one catalog per language

CLI (exit 0 ok, 1 findings or failure, 2 bad usage, 3 Sphinx/Babel missing):

    po_sync.py generate --worktree W --pages content/a.rst,content/b.rst --langs vi [--json]
    po_sync.py fill     --po locale/vi/LC_MESSAGES/a.po --spec spec.json [--json]
    po_sync.py verify   --worktree W --base-ref R --pages ... --langs vi [--json]
                        [--allow-untranslated]
    po_sync.py clean    --work-dir D | --worktree W     delete a work dir this tool created

Common flags: --content-dir (default content), --locale-dir (default locale), --width (default:
read from the repo's sphinx-intl invocation, else 76), --work-dir (default
<state root>/scratch/docs-site/<hash>/po-sync, the state root being $ODOO_AI_HOME or
~/.odoo-ai as scripts/lib/paths.py resolves it; never the system temp dir). The generate run
reports its work_dir; `clean` deletes it (the caller that ran generate cleans up after itself).

Syntax stays parseable by Python 3.8.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WIDTH = 76
HEADER_DATE_FIELD = "POT-Creation-Date"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_MISSING_DEP = 3


class SyncError(Exception):
    """A failure the caller should see as one line (exit 1)."""


# --------------------------------------------------------------------------- #
# lazy dependencies
# --------------------------------------------------------------------------- #
def require_module(name, why):
    """Exit 3 with a one-line remedy when `name` is not importable by this python."""
    if importlib.util.find_spec(name) is None:
        sys.stderr.write(
            "%s is not importable in %s (%s); run this with the docs repo's venv python "
            "(pip install -r requirements.txt there).\n" % (name, sys.executable, why))
        raise SystemExit(EXIT_MISSING_DEP)


def _babel():
    from babel.messages.catalog import Catalog
    from babel.messages.pofile import read_po, write_po
    return Catalog, read_po, write_po


# --------------------------------------------------------------------------- #
# pure helpers (page <-> catalog mapping, header shaping, accounting)
# --------------------------------------------------------------------------- #
def page_to_docname(page, content_dir="content"):
    """`content/a/b.rst` -> `a/b` (the Sphinx docname, hence the gettext domain)."""
    page = page.replace("\\", "/")
    while page.startswith("./"):
        page = page[2:]
    prefix = content_dir.strip("/") + "/"
    if not page.startswith(prefix) or not page.endswith(".rst"):
        raise SyncError("page %r is not a %s*.rst source page" % (page, prefix))
    docname = page[len(prefix):-len(".rst")]
    if not docname or ".." in docname.split("/"):
        raise SyncError("page %r does not name a page inside %s" % (page, prefix))
    return docname


def catalog_paths(page, lang, content_dir="content", locale_dir="locale"):
    """(pot, po) repo-relative paths of one page's template and of its `lang` catalog."""
    docname = page_to_docname(page, content_dir)
    loc = locale_dir.strip("/")
    return ("%s/sources/%s.pot" % (loc, docname),
            "%s/%s/LC_MESSAGES/%s.po" % (loc, lang, docname))


def split_csv(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def split_header(text):
    """(header block, rest). The header is everything up to the first blank line."""
    head, sep, rest = text.partition("\n\n")
    return head, rest if sep else ""


def get_header_field(head, name):
    m = re.search(r'^"%s:[ \t]*(.*?)\\n"[ \t]*$' % re.escape(name), head, re.M)
    return m.group(1) if m else None


def set_header_field(head, name, value):
    """Set `name: value` in a PO header block, inserting it when absent."""
    line = '"%s: %s\\n"' % (name, value)
    pattern = re.compile(r'^"%s:.*\\n"[ \t]*$' % re.escape(name), re.M)
    if pattern.search(head):
        return pattern.sub(lambda _m: line, head, count=1)
    mime = re.search(r'^"MIME-Version:', head, re.M)
    if mime:
        return head[:mime.start()] + line + "\n" + head[mime.start():]
    return head + "\n" + line


def drop_fuzzy_header_flag(head):
    return re.sub(r"^#,[ \t]*fuzzy[ \t]*\n", "", head, flags=re.M)


def strip_volatile(text):
    """Text with the one field that changes on every run removed (for 'did it change?')."""
    return re.sub(r'^"%s:.*\\n"[ \t]*\n' % re.escape(HEADER_DATE_FIELD), "", text, flags=re.M)


def shape_new_header(model_head, lang, creation_date):
    """Header of a NEW catalog: the sibling's (or template's) header, adapted to `lang`."""
    head = drop_fuzzy_header_flag(model_head)
    head = set_header_field(head, "Language", lang)
    if creation_date is not None:
        head = set_header_field(head, HEADER_DATE_FIELD, creation_date)
    return head


def detect_width(texts):
    """Line width the repo wraps its catalogs at: read from its sphinx-intl / write_po call."""
    pats = (r"(?:--line-width|--width|\s-w)[ =]*(\d+)", r"\bwidth\s*=\s*(\d+)")
    for text in texts:
        for line in (text or "").splitlines():
            if "intl" not in line and "write_po" not in line:
                continue
            for pat in pats:
                m = re.search(pat, line)
                if m:
                    return int(m.group(1))
    return DEFAULT_WIDTH


def rewrite_locations(pot_text, built_in_dir, canonical_dir):
    """Re-express every `#: path:line` of a freshly built .pot relative to `canonical_dir`.

    Sphinx writes locations relative to the directory it built into, which here is a work
    directory outside the repo; left alone every page would differ from its committed template.
    """
    out = []
    for line in pot_text.split("\n"):
        if line.startswith("#: "):
            toks = []
            for tok in line[3:].split():
                path, sep, lineno = tok.rpartition(":")
                if not sep or not lineno.isdigit():
                    path, lineno = tok, None
                absolute = os.path.normpath(os.path.join(built_in_dir, path))
                rel = os.path.relpath(absolute, canonical_dir).replace(os.sep, "/")
                toks.append(rel if lineno is None else "%s:%s" % (rel, lineno))
            line = "#: " + " ".join(toks)
        out.append(line)
    return "\n".join(out)


def _is_empty(string):
    if isinstance(string, (tuple, list)):
        return (not string) or any(not s for s in string)
    return not string


def account(catalog):
    """Entry accounting of a parsed catalog.

    entries = every non-header message; fuzzy = flagged fuzzy (a guess, never counted as
    translated); untranslated = empty msgstr (Sphinx renders the English source for it);
    translated = non-empty and not fuzzy.
    """
    entries = fuzzy = translated = 0
    untranslated, fuzzy_ids = [], []
    for msg in catalog:
        if not msg.id:
            continue
        entries += 1
        mid = msg.id[0] if isinstance(msg.id, (tuple, list)) else msg.id
        if "fuzzy" in msg.flags:
            fuzzy += 1
            fuzzy_ids.append(mid)
        elif _is_empty(msg.string):
            untranslated.append(mid)
        else:
            translated += 1
    return {"entries": entries, "translated": translated, "untranslated": untranslated,
            "fuzzy": fuzzy, "fuzzy_msgids": fuzzy_ids,
            "header_fuzzy": bool(getattr(catalog, "fuzzy", False))}


def _locations(msg):
    """A message's source locations with "no line number" and line 0 the same thing: write_po
    prints neither as `:N`, so a catalog read back carries None where the template says 0."""
    return tuple((path, lineno or 0) for path, lineno in msg.locations)


def _snapshot(catalog):
    snap = {}
    for msg in catalog:
        if not msg.id:
            continue
        snap[(msg.id, msg.context)] = (
            msg.string, frozenset(msg.flags), _locations(msg),
            tuple(msg.auto_comments), tuple(msg.user_comments))
    return snap


# --------------------------------------------------------------------------- #
# repo access
# --------------------------------------------------------------------------- #
WORK_MARKER = ".docs-site-work"


def state_root():
    """The plugin's state root ($ODOO_AI_HOME, default ~/.odoo-ai), resolved by the plugin's own
    paths.py (scripts/lib), loaded by file path so no other `paths` module can shadow it."""
    lib = os.path.dirname(_HERE)
    spec = importlib.util.spec_from_file_location("odoo_ai_paths", os.path.join(lib, "paths.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.state_root()


def work_dir_for(worktree, tool, override=None):
    """--work-dir, else <state root>/scratch/docs-site/<hash of the worktree>/<tool>."""
    if override:
        return os.path.abspath(override)
    key = hashlib.sha256(os.path.realpath(worktree).encode("utf-8")).hexdigest()[:12]
    return os.path.join(state_root(), "scratch", "docs-site", key, tool)


def claim_work_dir(path, fresh=True):
    """Create `path` as a marked work dir (emptying a previous marked one). Refuses an existing
    non-empty directory this tool did not create, so a mistyped --work-dir cannot be wiped."""
    if os.path.isdir(path) and os.listdir(path):
        if not os.path.isfile(os.path.join(path, WORK_MARKER)):
            raise SyncError("%s exists, is not empty and is not a docs-site work dir "
                            "(no %s marker); pick another --work-dir" % (path, WORK_MARKER))
        if fresh:
            shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, WORK_MARKER), "w") as fh:
        fh.write("created by odoo-ai-agents docs_site; safe to delete\n")
    return path


def clean_work_dir(path):
    """Delete a marked work dir (and a server recorded in it). True when something was removed."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, WORK_MARKER)):
        raise SyncError("%s is not a docs-site work dir (no %s marker); refusing to delete it"
                        % (path, WORK_MARKER))
    shutil.rmtree(path)
    _remove_empty_hash_dir(path)
    return True


def _remove_empty_hash_dir(path):
    """After a default-layout work dir (<state root>/scratch/docs-site/<hash>/<tool>) is gone, drop
    its now-empty <hash> parent. Any other layout (an explicit --work-dir) leaves its parent alone."""
    parent = os.path.dirname(path)
    try:
        scratch = os.path.realpath(os.path.join(state_root(), "scratch", "docs-site"))
        if os.path.dirname(os.path.realpath(parent)) == scratch:
            os.rmdir(parent)
    except OSError:  # not empty (the other tool's work dir lives there too), or not ours
        pass


def read_text(path):
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-po-sync"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def repo_width(worktree, override):
    if override:
        return override
    texts = []
    for name in ("Makefile", "conf.py", "content/conf.py"):
        p = os.path.join(worktree, name)
        if os.path.isfile(p):
            texts.append(read_text(p))
    return detect_width(texts)


def find_repo_root(path):
    """Nearest ancestor of `path` that looks like the docs repo root (Makefile, conf.py or .git)."""
    cur = os.path.dirname(os.path.realpath(path))
    while True:
        if any(os.path.exists(os.path.join(cur, m)) for m in ("Makefile", "conf.py", ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.dirname(os.path.realpath(path))
        cur = parent


def conf_notes(worktree, content_dir):
    notes = []
    for rel in ("conf.py", content_dir + "/conf.py"):
        p = os.path.join(worktree, rel)
        if os.path.isfile(p) and "sphinx_intl" in read_text(p):
            notes.append("%s references sphinx_intl (it may re-save every .po and strip fuzzy "
                         "flags); this tool never runs sphinx-intl or `make translate`" % rel)
    return notes


def git_lines(worktree, args):
    proc = subprocess.run(["git", "-C", worktree] + args, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    if proc.returncode != 0:
        raise SyncError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return [ln for ln in proc.stdout.split("\n") if ln]


# --------------------------------------------------------------------------- #
# catalog read / merge / write
# --------------------------------------------------------------------------- #
def parse_catalog(text, lang=None, strict=False):
    _, read_po, _ = _babel()
    return read_po(io.BytesIO(text.encode("utf-8")), locale=lang, ignore_obsolete=True,
                   abort_invalid=strict)


def render_body(catalog, width):
    """The entries of `catalog` as PO text, without the header block."""
    _, _, write_po = _babel()
    buf = io.BytesIO()
    write_po(buf, catalog, width=width, ignore_obsolete=True, include_previous=False)
    return split_header(buf.getvalue().decode("utf-8"))[1]


def _strip_python_format(catalog):
    for msg in catalog:
        msg.flags.discard("python-format")


def _update(catalog, template):
    try:
        catalog.update(template, no_fuzzy_matching=True, update_header_comment=False)
    except TypeError:
        catalog.update(template, no_fuzzy_matching=True)


def find_model_header(po_path, locale_root):
    """Header of a sibling catalog: one in the same directory first, else any under the
    language root (first in sorted order)."""
    def first_po(walk_root, recursive):
        for dirpath, dirnames, filenames in os.walk(walk_root):
            dirnames.sort()
            for fn in sorted(filenames):
                cand = os.path.join(dirpath, fn)
                if fn.endswith(".po") and cand != po_path:
                    return cand
            if not recursive:
                break
        return None

    here = os.path.dirname(po_path)
    for walk_root, recursive in ((here, False), (locale_root, True)):
        found = first_po(walk_root, recursive) if os.path.isdir(walk_root) else None
        if found:
            return split_header(read_text(found))[0]
    return None


def merge_catalog(pot_text, po_path, lang, width, locale_root):
    """Create or refresh one .po from `pot_text`. Returns (report dict, written bool)."""
    Catalog, _, _ = _babel()
    template = parse_catalog(pot_text)
    creation_date = get_header_field(split_header(pot_text)[0], HEADER_DATE_FIELD)
    exists = os.path.isfile(po_path)
    keep_pyfmt = False
    if exists:
        old_text = read_text(po_path)
        old_head = split_header(old_text)[0]
        old_lang = get_header_field(old_head, "Language") or ""
        keep_pyfmt = "python-format" in old_text
        # patch an empty/wrong Language BEFORE parsing: an older Babel rejects the empty one
        cat = parse_catalog(set_header_field(old_head, "Language", lang) + "\n\n"
                            + split_header(old_text)[1], lang)
        model_head = old_head
    else:
        old_text, old_lang = None, None
        cat = Catalog(locale=lang)
        model_head = (find_model_header(po_path, locale_root)
                      or drop_fuzzy_header_flag(split_header(pot_text)[0]))
    if not keep_pyfmt:
        _strip_python_format(cat)
    before = _snapshot(cat)
    _update(cat, template)
    if not keep_pyfmt:
        _strip_python_format(cat)
    changed = (not exists) or before != _snapshot(cat) or old_lang != lang
    report = account(cat)
    report.update({"created": not exists, "written": False})
    if changed:
        head = (set_header_field(model_head, "Language", lang) if exists
                else shape_new_header(model_head, lang, creation_date))
        if exists and creation_date is not None:
            head = set_header_field(head, HEADER_DATE_FIELD, creation_date)
        write_text_atomic(po_path, head + "\n\n" + render_body(cat, width))
        report["written"] = True
    return report, report["written"]


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
def conf_args(root, content_dir):
    """`-c <root>` when conf.py sits at the repo root rather than beside the sources."""
    if os.path.isfile(os.path.join(root, content_dir, "conf.py")):
        return []
    if os.path.isfile(os.path.join(root, "conf.py")):
        return ["-c", root]
    raise SyncError("no conf.py in %s or at the repo root" % content_dir)


def run_sphinx_gettext(worktree, content_dir, out_dir, work):
    """sphinx-build -q -b gettext <W>/content <out>, run from W with the repo conf."""
    src = os.path.join(worktree, content_dir)
    cmd = [sys.executable, "-m", "sphinx", "-q", "-b", "gettext"]
    cmd += conf_args(worktree, content_dir)
    cmd += ["-d", os.path.join(work, "doctrees"), src, out_dir]
    log = os.path.join(work, "gettext.log")
    with open(log, "wb") as fh:
        rc = subprocess.call(cmd, cwd=worktree, stdout=fh, stderr=subprocess.STDOUT)
    if rc != 0:
        tail = "\n".join(read_text(log).splitlines()[-15:])
        raise SyncError("the gettext build failed (exit %d, log %s):\n%s" % (rc, log, tail))
    return log


def cmd_generate(args):
    worktree = os.path.realpath(args.worktree)
    pages, langs = split_csv(args.pages), split_csv(args.langs)
    if not pages or not langs:
        raise SyncError("--pages and --langs must each name at least one value")
    for page in pages:
        page_to_docname(page, args.content_dir)
        if not os.path.isfile(os.path.join(worktree, page)):
            raise SyncError("page %s does not exist in the worktree" % page)
    require_module("babel", "needed to merge catalogs")
    require_module("sphinx", "needed for the gettext builder")
    width = repo_width(worktree, args.width)
    work = claim_work_dir(work_dir_for(worktree, "po-sync", args.work_dir))
    pot_out = os.path.join(work, "pot")
    log = run_sphinx_gettext(worktree, args.content_dir, pot_out, work)
    canonical = os.path.join(worktree, args.locale_dir, "sources")
    result = {"worktree": worktree, "width": width, "log": log, "work_dir": work,
              "notes": conf_notes(worktree, args.content_dir), "pages": [], "ok": True}
    for page in pages:
        docname = page_to_docname(page, args.content_dir)
        built = os.path.join(pot_out, docname + ".pot")
        entry = {"page": page, "catalogs": {}}
        result["pages"].append(entry)
        if not os.path.isfile(built):
            entry["error"] = "the gettext builder wrote no %s.pot (is it a page of the toctree?)" % docname
            result["ok"] = False
            continue
        pot_text = rewrite_locations(read_text(built), pot_out, canonical)
        pot_rel, _ = catalog_paths(page, langs[0], args.content_dir, args.locale_dir)
        pot_dest = os.path.join(worktree, pot_rel)
        old_pot = read_text(pot_dest) if os.path.isfile(pot_dest) else None
        entry["pot"] = pot_rel
        entry["pot_written"] = old_pot is None or strip_volatile(old_pot) != strip_volatile(pot_text)
        if entry["pot_written"]:
            write_text_atomic(pot_dest, pot_text)
        pot_for_merge = read_text(pot_dest)
        for lang in langs:
            _, po_rel = catalog_paths(page, lang, args.content_dir, args.locale_dir)
            locale_root = os.path.join(worktree, args.locale_dir, lang, "LC_MESSAGES")
            report, _ = merge_catalog(pot_for_merge, os.path.join(worktree, po_rel), lang,
                                      width, locale_root)
            report["po"] = po_rel
            entry["catalogs"][lang] = report
    return result, (EXIT_OK if result["ok"] else EXIT_FINDINGS)


# --------------------------------------------------------------------------- #
# fill
# --------------------------------------------------------------------------- #
def cmd_fill(args):
    require_module("babel", "needed to edit catalogs")
    try:
        with io.open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SyncError("cannot read --spec %s: %s" % (args.spec, exc))
    if not isinstance(spec, list) or not all(
            isinstance(s, dict) and isinstance(s.get("msgid"), str)
            and isinstance(s.get("msgstr"), str) for s in spec):
        raise SyncError('--spec must be a JSON list of {"msgid": str, "msgstr": str}')
    if not os.path.isfile(args.po):
        raise SyncError("no such .po: %s" % args.po)
    text = read_text(args.po)
    head, rest = split_header(text)
    lang = get_header_field(head, "Language") or None
    cat = parse_catalog(set_header_field(head, "Language", lang) + "\n\n" + rest if lang else text, lang)
    missing, empty, seen = [], [], set()
    for item in spec:
        key = (item["msgid"], item.get("context"))
        msg = cat.get(item["msgid"], context=item.get("context"))
        if msg is None:
            missing.append(item["msgid"])
        elif key in seen:
            raise SyncError("msgid given twice in --spec: %r" % item["msgid"])
        elif not item["msgstr"]:
            empty.append(item["msgid"])
        seen.add(key)
    if missing or empty:
        out = {"ok": False, "po": args.po, "missing_msgids": missing, "empty_msgstr": empty}
        return out, EXIT_FINDINGS
    for item in spec:
        msg = cat.get(item["msgid"], context=item.get("context"))
        msg.string = item["msgstr"]
        msg.flags.discard("fuzzy")
    root = os.path.realpath(args.worktree) if args.worktree else find_repo_root(args.po)
    width = repo_width(root, args.width)
    keep_pyfmt = "python-format" in text
    if not keep_pyfmt:
        _strip_python_format(cat)
    write_text_atomic(args.po, head + "\n\n" + render_body(cat, width))
    out = account(cat)
    out.update({"ok": True, "po": args.po, "set": len(spec)})
    return out, EXIT_OK


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def expected_paths(pages, langs, content_dir, locale_dir):
    pots, pos = {}, {}
    for page in pages:
        for lang in langs:
            pot, po = catalog_paths(page, lang, content_dir, locale_dir)
            pots[pot] = page
            pos[po] = (page, lang)
    return pots, pos


def stray_locale_changes(changed, allowed):
    return sorted(p for p in changed if p not in allowed)


def check_catalog(path, lang):
    """Findings for one catalog file: parse, fuzzy, Language, untranslated."""
    findings = {"parse_error": None, "language": None, "language_ok": False,
                "fuzzy": 0, "header_fuzzy": False, "untranslated": [], "entries": 0}
    text = read_text(path)
    head = split_header(text)[0]
    language = get_header_field(head, "Language") or ""
    findings["language"] = language
    findings["language_ok"] = bool(language) and language.replace("-", "_") == lang.replace("-", "_")
    try:
        cat = parse_catalog(text, None, strict=True)
        from babel.messages.mofile import write_mo
        write_mo(io.BytesIO(), cat)
    except Exception as exc:  # any parse/compile failure is the finding
        findings["parse_error"] = "%s: %s" % (type(exc).__name__, exc)
        return findings
    acc = account(cat)
    findings.update({"fuzzy": acc["fuzzy"], "header_fuzzy": acc["header_fuzzy"],
                     "untranslated": acc["untranslated"], "entries": acc["entries"],
                     "fuzzy_msgids": acc["fuzzy_msgids"]})
    return findings


def cmd_verify(args):
    require_module("babel", "needed to parse catalogs")
    worktree = os.path.realpath(args.worktree)
    pages, langs = split_csv(args.pages), split_csv(args.langs)
    if not pages or not langs:
        raise SyncError("--pages and --langs must each name at least one value")
    pots, pos = expected_paths(pages, langs, args.content_dir, args.locale_dir)
    loc = args.locale_dir.strip("/") + "/"
    changed = set(git_lines(worktree, ["diff", "--name-only", "--no-renames", args.base_ref,
                                       "--", loc]))
    changed |= set(git_lines(worktree, ["ls-files", "-o", "--exclude-standard", "--", loc]))
    out = {"ok": True, "base_ref": args.base_ref, "outside_pages": [], "missing": [],
           "catalogs": {}, "failures": []}
    out["outside_pages"] = stray_locale_changes(changed, set(pots) | set(pos))
    if out["outside_pages"]:
        out["failures"].append("catalog files changed outside the given pages: %s"
                               % ", ".join(out["outside_pages"]))
    for po, (page, lang) in sorted(pos.items()):
        full = os.path.join(worktree, po)
        if not os.path.isfile(full):
            out["missing"].append(po)
            out["failures"].append("missing catalog %s" % po)
            continue
        res = check_catalog(full, lang)
        res["touched"] = po in changed
        out["catalogs"][po] = res
        if res["parse_error"]:
            out["failures"].append("%s does not parse: %s" % (po, res["parse_error"]))
            continue
        if res["fuzzy"]:  # an entry-level guess; the catalog HEADER's fuzzy flag is boilerplate
            out["failures"].append("%s has fuzzy entries (%d)" % (po, res["fuzzy"]))
        if not res["language_ok"]:
            out["failures"].append("%s Language header is %r, expected %r" % (
                po, res["language"], lang))
        if res["untranslated"] and not args.allow_untranslated:
            out["failures"].append("%s has %d untranslated entries" % (po, len(res["untranslated"])))
    for pot in sorted(pots):
        if not os.path.isfile(os.path.join(worktree, pot)):
            out["missing"].append(pot)
            out["failures"].append("missing template %s" % pot)
    out["ok"] = not out["failures"]
    return out, (EXIT_OK if out["ok"] else EXIT_FINDINGS)


# --------------------------------------------------------------------------- #
# clean
# --------------------------------------------------------------------------- #
def cmd_clean(args):
    if not args.work_dir and not args.worktree:
        raise SyncError("clean needs --work-dir D or --worktree W")
    path = work_dir_for(args.worktree or "", "po-sync", args.work_dir)
    removed = clean_work_dir(path)
    return {"ok": True, "work_dir": path, "removed": removed}, EXIT_OK


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def print_text(cmd, result):
    if cmd == "generate":
        for page in result["pages"]:
            if page.get("error"):
                print("%s: ERROR %s" % (page["page"], page["error"]))
                continue
            print("%s: template %s" % (page["page"], "updated" if page["pot_written"] else "unchanged"))
            for lang, rep in sorted(page["catalogs"].items()):
                print("  %s %s: %d entries, %d translated, %d untranslated, %d fuzzy%s" % (
                    lang, rep["po"], rep["entries"], rep["translated"], len(rep["untranslated"]),
                    rep["fuzzy"], " (created)" if rep["created"] else ""))
                for mid in rep["untranslated"]:
                    print("    - %s" % json.dumps(mid, ensure_ascii=False))
        for note in result["notes"]:
            print("note: " + note)
    elif cmd == "fill":
        if result["ok"]:
            print("%s: set %d, %d untranslated, %d fuzzy left" % (
                result["po"], result["set"], len(result["untranslated"]), result["fuzzy"]))
        else:
            for mid in result["missing_msgids"]:
                print("missing msgid: %s" % json.dumps(mid, ensure_ascii=False))
            for mid in result["empty_msgstr"]:
                print("empty msgstr for: %s" % json.dumps(mid, ensure_ascii=False))
    elif cmd == "clean":
        print("%s %s" % ("removed" if result["removed"] else "nothing to remove at",
                         result["work_dir"]))
    else:
        for po, res in sorted(result["catalogs"].items()):
            for mid in res["untranslated"]:
                print("untranslated in %s: %s" % (po, json.dumps(mid, ensure_ascii=False)))
        for failure in result["failures"]:
            print("FAIL: " + failure)
        if result["ok"]:
            print("verify ok")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    def common(p, worktree_required=True):
        p.add_argument("--worktree", required=worktree_required)
        p.add_argument("--content-dir", default="content")
        p.add_argument("--locale-dir", default="locale")
        p.add_argument("--width", type=int, default=None)
        p.add_argument("--json", action="store_true")

    g = sub.add_parser("generate", help="refresh the .pot and merge the .po of the given pages")
    common(g)
    g.add_argument("--pages", required=True)
    g.add_argument("--langs", required=True)
    g.add_argument("--work-dir", default=None)

    f = sub.add_parser("fill", help="apply {msgid, msgstr} translations to one .po")
    common(f, worktree_required=False)
    f.add_argument("--po", required=True)
    f.add_argument("--spec", required=True)

    v = sub.add_parser("verify", help="check the touched catalogs against a base ref")
    common(v)
    v.add_argument("--base-ref", required=True)
    v.add_argument("--pages", required=True)
    v.add_argument("--langs", required=True)
    v.add_argument("--allow-untranslated", action="store_true")

    c = sub.add_parser("clean", help="delete a work dir this tool created")
    c.add_argument("--work-dir", default=None)
    c.add_argument("--worktree", default=None)
    c.add_argument("--json", action="store_true")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    handler = {"generate": cmd_generate, "fill": cmd_fill, "verify": cmd_verify,
               "clean": cmd_clean}[args.cmd]
    try:
        result, code = handler(args)
    except SyncError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write("po_sync: %s\n" % exc)
        return EXIT_FINDINGS
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(args.cmd, result)
    return code


if __name__ == "__main__":
    sys.exit(main())
