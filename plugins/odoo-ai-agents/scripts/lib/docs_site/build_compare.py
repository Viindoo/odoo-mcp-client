#!/usr/bin/env python3
"""build_compare.py - build a docs repo at a base ref and as it stands, and compare the two.

Runs under the DOCS REPO's own venv python (it needs Sphinx; a missing one exits 3 with a one-line
remedy). The pass criterion is never a warning count: build warnings differ per environment, so the
base ref is built HERE, in the same environment as the candidate, and the criterion is "no new
warning or error versus that base, no failed candidate build".

    build_compare.py --worktree W --base-ref origin/<series> --langs en,vi
                     [--work-dir D] [--pages content/a.rst,...] [--source-lang en] [--json]
    build_compare.py serve --work-dir D [--port 0] [--langs en,vi]
    build_compare.py stop  --work-dir D
    build_compare.py clean --work-dir D | --worktree W

compare: exports the base ref (`git archive`) into D/base, copies the worktree's tracked and
untracked-not-ignored files into D/cand, and builds each tree per language with the repo's own
`make html` (the language and build-dir variables are read from its Makefile) or, when the Makefile
has no such variables, `sphinx-build -b html -D language=<lang>`. The touched pages are the .rst
files that differ between those two snapshots (or --pages), so a worktree edited while the builds
run changes nothing. For every non-source language it also checks that the built HTML of the touched
pages references the per-language image files the repo has beside the images those pages use (a
variant counts whether or not the plain file exists). Each build's doctrees are deleted once it is
done (they are several GB on a large site; the HTML is kept). D/compare.json is always written.
Exit 0 ok, 1 findings, 2 bad usage, 3 Sphinx missing.

serve: serves the candidate HTML of the last compare run on 127.0.0.1 only (stdlib http.server) so
it can be looked at in a real browser; prints `URL <lang> <url>` per language and `PID <pid>`, then
serves until SIGTERM/SIGINT. stop: stops the server recorded in D/serve.pid.

Work dirs default to <state root>/scratch/docs-site/<hash>/build-compare, the state root being
$ODOO_AI_HOME or ~/.odoo-ai as scripts/lib/paths.py resolves it (never the system temp dir: it may
be a small tmpfs, and builds die with "Disk quota exceeded"). The run reports its work_dir; the
caller that ran compare removes it with `clean` when done (it also stops a server it started).
The tools write only into the work dir; no temp-dir redirection is attempted.

Syntax stays parseable by Python 3.8.
"""

from __future__ import annotations

import argparse
import collections
import filecmp
import functools
import html.parser
import http.server
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
if __package__:
    from . import po_sync as _po
else:
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import po_sync as _po

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_MISSING_DEP = 0, 1, 2, 3

LANG_VARS = ("CURRENT_LANG", "DOC_LANG", "DOCS_LANG", "TARGET_LANG", "LANG_CODE")
OUT_VARS = ("BUILD_DIR", "BUILDDIR", "OUTPUT_DIR", "OUT_DIR")
MANIFEST = "compare.json"
PIDFILE = "serve.pid"
MIN_FREE_BYTES = 512 * 1024 * 1024


class CompareError(Exception):
    """A failure the caller should see as one line (exit 1)."""


# --------------------------------------------------------------------------- #
# pure helpers: Makefile variables, warning normalisation, set difference
# --------------------------------------------------------------------------- #
def _assigns(text, name):
    return re.search(r"^[ \t]*(?:export[ \t]+)?%s[ \t]*(?:\?|:|::|\+)?=" % re.escape(name),
                     text, re.M) is not None


def detect_make_vars(text):
    """(lang variable, build-dir variable) a Makefile declares, or (None, None) when it lacks
    either or has no way to build html (so the caller falls back to sphinx-build)."""
    lang_var = next((v for v in LANG_VARS if _assigns(text, v)), None)
    out_var = next((v for v in OUT_VARS if _assigns(text, v)), None)
    has_html = (re.search(r"^html[ \t]*:", text, re.M) is not None
                or re.search(r"^%[ \t]*:", text, re.M) is not None)
    if lang_var and out_var and has_html:
        return lang_var, out_var
    return None, None


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PROBLEM = re.compile(r"\b(?:WARNING|ERROR|CRITICAL|SEVERE)\b:")
_FAILURE = re.compile(r"^(?:Exception occurred|Extension error|Traceback \(most recent call last\)"
                      r"|make(?:\[\d+\])?: \*\*\*)")
_ABS_PATH = re.compile(r"(?<![^\s'\"(\[])/(?:[^\s:'\"()\[\]]+/)+")
_FILE_LINE = re.compile(r"(Makefile|\.\w{1,5}):\d+(?::\d+)?(?=[:\s,)'\"\]]|$)")


def normalize_problem(line, roots=()):
    """A warning/error line with everything environment- or position-specific removed."""
    line = _ANSI.sub("", line).strip()
    for root in sorted({r.rstrip("/") for r in roots if r}, key=len, reverse=True):
        line = line.replace(root + "/", "").replace(root, "<root>")
    line = _ABS_PATH.sub("", line)
    line = _FILE_LINE.sub(lambda m: m.group(1), line)
    line = re.sub(r"\bline \d+\b", "line N", line)
    return re.sub(r"\s+", " ", line).strip()


def extract_problems(log_text, roots=()):
    """Multiset (Counter) of the normalised WARNING/ERROR/failure lines of a build log."""
    found = collections.Counter()
    for raw in log_text.splitlines():
        line = _ANSI.sub("", raw).strip()
        if _PROBLEM.search(line) or _FAILURE.match(line):
            found[normalize_problem(line, roots)] += 1
    return found


def diff_problems(base, cand):
    """(new in cand, fixed in cand) as sorted lists; a repeated problem counts per occurrence."""
    new = cand - base
    fixed = base - cand
    expand = lambda c: sorted(k for k, n in c.items() for _ in range(n))  # noqa: E731
    return expand(new), expand(fixed)


class _Imgs(html.parser.HTMLParser):
    def __init__(self):
        html.parser.HTMLParser.__init__(self)
        self.srcs = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.srcs.append(src)


def img_basenames(html_text):
    parser = _Imgs()
    parser.feed(html_text)
    return {os.path.basename(urllib.parse.unquote(s.split("?")[0].split("#")[0]))
            for s in parser.srcs}


def rst_image_refs(rst_text):
    """The path each image/figure directive of an RST source names."""
    return [m.group(1) for m in re.finditer(
        r"^[ \t]*\.\.[ \t]+(?:image|figure)::[ \t]+(\S+)", rst_text, re.M)]


def rst_image_basenames(rst_text):
    return {os.path.basename(r) for r in rst_image_refs(rst_text)}


def ref_dirs_by_name(rst_text, page_dir, content_root):
    """basename -> {absolute directory the reference points into}, for the local references of a page.

    `page_dir` is the page's own directory, `content_root` the source root a leading "/" means."""
    out = collections.defaultdict(set)
    for ref in rst_image_refs(rst_text):
        if re.match(r"^[a-zA-Z][\w+.-]*://", ref):
            continue
        base = content_root if ref.startswith("/") else page_dir
        out[os.path.basename(ref)].add(os.path.normpath(os.path.join(base, os.path.dirname(ref).lstrip("/"))))
    return out


def language_variant(basename, lang, pattern="{root}.{language}{ext}"):
    """Name Sphinx looks for first when building `lang` (figure_language_filename)."""
    root, ext = os.path.splitext(basename)
    name = pattern.format(root=root, ext=ext, language=lang, basename=basename, path="",
                          docpath="", relative_path="", resolution="")
    return None if "/" in name else name


def figure_pattern(conf_text):
    m = re.search(r"""figure_language_filename\s*=\s*['"]([^'"]+)['"]""", conf_text or "")
    return m.group(1) if m else "{root}.{language}{ext}"


def image_expectations(plain_names, tree_dirs_by_name, lang, pattern, ref_dirs=None):
    """Variant names the built page must reference: those whose file the repo ships beside the
    image the page names. `tree_dirs_by_name` maps basename -> set of directories holding a file of
    that name; `ref_dirs` maps a plain basename -> the directories the page's references point into.

    Where the reference directory is known, the variant counts when a variant file sits in it -
    whether or not the plain file does. A name with no known reference directory (found only in
    built HTML) needs the plain and variant files in one directory."""
    expected = {}
    ref_dirs = ref_dirs or {}
    for plain in sorted(plain_names):
        variant = language_variant(plain, lang, pattern)
        if not variant:
            continue
        have = tree_dirs_by_name.get(variant, set())
        where = ref_dirs.get(plain) or tree_dirs_by_name.get(plain, set())
        if where & have:
            expected[plain] = variant
    return expected


def judge_images(expected, html_names):
    """(missing variants, plain images still used although a variant exists)."""
    missing = sorted(v for v in expected.values() if v not in html_names)
    plain_used = sorted(p for p in expected if p in html_names)
    return missing, plain_used


# --------------------------------------------------------------------------- #
# trees
# --------------------------------------------------------------------------- #
def git(worktree, args):
    proc = subprocess.run(["git", "-C", worktree] + args, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise CompareError("git %s failed: %s" % (" ".join(args),
                                                 proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout


def export_base(worktree, ref, dest):
    git(worktree, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    os.makedirs(dest)
    proc = subprocess.Popen(["git", "-C", worktree, "archive", "--format=tar", ref],
                            stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                name = member.name
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                if hasattr(tarfile, "data_filter"):
                    tar.extract(member, dest, filter="data")
                else:
                    tar.extract(member, dest)
    finally:
        proc.stdout.close()
        rc = proc.wait()
    if rc != 0:
        raise CompareError("git archive %s failed" % ref)


def copy_candidate(worktree, dest):
    """Tracked + untracked-not-ignored files of the worktree (deleted ones skipped)."""
    names = git(worktree, ["ls-files", "-z", "-c", "-o", "--exclude-standard"]).split(b"\0")
    skipped = []
    for raw in sorted({n for n in names if n}):
        rel = raw.decode("utf-8", "surrogateescape")
        src = os.path.join(worktree, rel)
        if not os.path.lexists(src):
            continue
        if os.path.isdir(src) and not os.path.islink(src):
            skipped.append(rel)  # a submodule checkout
            continue
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.islink(src):
            os.symlink(os.readlink(src), target)
        else:
            shutil.copy2(src, target)
    return skipped


def touched_pages(base_dir, cand_dir, content_dir):
    """Pages (repo-relative .rst paths) whose text in the candidate snapshot differs from the base
    snapshot or that the base does not have. Reads only the two snapshots, never the live worktree."""
    top = os.path.join(cand_dir, content_dir)
    found = []
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".rst"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), cand_dir).replace(os.sep, "/")
            old = os.path.join(base_dir, rel)
            if not os.path.isfile(old) or not filecmp.cmp(old, os.path.join(cand_dir, rel), shallow=False):
                found.append(rel)
    return sorted(found)


def find_html_root(out_dir):
    """Directory holding the built index.html (BUILD_DIR itself, BUILD_DIR/html, or deeper)."""
    for sub in ("", "html"):
        if os.path.isfile(os.path.join(out_dir, sub, "index.html")):
            return os.path.join(out_dir, sub) if sub else out_dir
    best = None
    for dirpath, dirnames, filenames in os.walk(out_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("_static", "_images")]
        if "index.html" in filenames:
            depth = dirpath[len(out_dir):].count(os.sep)
            if best is None or depth < best[0]:
                best = (depth, dirpath)
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# building
# --------------------------------------------------------------------------- #
def build_env():
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    env = dict(os.environ)
    env["PATH"] = exe_dir + os.pathsep + env.get("PATH", "")
    if os.path.isfile(os.path.join(os.path.dirname(exe_dir), "pyvenv.cfg")):
        env["VIRTUAL_ENV"] = os.path.dirname(exe_dir)
    return env


def build_one(tree_dir, tree, lang, work, content_dir, make_vars, env, timeout, log_path):
    """Build one tree for one language. Returns a dict (mode, returncode, log, out)."""
    out = os.path.join(work, "%s-%s-out" % (tree, lang))
    shutil.rmtree(out, ignore_errors=True)
    lang_var, out_var = make_vars
    if lang_var and shutil.which("make", path=env["PATH"]):
        cmd = ["make", "-C", tree_dir, "html", "%s=%s" % (lang_var, lang), "%s=%s" % (out_var, out)]
        mode = "make"
    else:
        cmd = ([sys.executable, "-m", "sphinx", "-b", "html", "-D", "language=%s" % lang]
               + _po.conf_args(tree_dir, content_dir)
               + ["-d", os.path.join(out, ".doctrees"), os.path.join(tree_dir, content_dir), out])
        mode = "sphinx-build"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        with open(log_path, "wb") as fh:
            rc = subprocess.call(cmd, cwd=tree_dir, env=env, stdout=fh,
                                 stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        rc = -1
    html_root = find_html_root(out) if rc == 0 else None
    remove_doctrees(out)
    return {"tree": tree, "lang": lang, "mode": mode, "returncode": rc,
            "build_succeeded": rc == 0, "log": log_path, "out": out, "html_root": html_root}


def remove_doctrees(out):
    """Delete the doctrees a build left under `out` (at most two levels down); the HTML stays."""
    removed = 0
    base_depth = out.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _files in os.walk(out):
        if dirpath.rstrip(os.sep).count(os.sep) - base_depth >= 2:
            dirnames[:] = []
        for name in list(dirnames):
            if name in ("doctrees", ".doctrees"):
                shutil.rmtree(os.path.join(dirpath, name), ignore_errors=True)
                dirnames.remove(name)
                removed += 1
    return removed


def tree_dirs_by_name(tree_dir, content_dir):
    index = collections.defaultdict(set)
    for dirpath, dirnames, filenames in os.walk(os.path.join(tree_dir, content_dir)):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            index[fn].add(dirpath)
    return index


def page_html(html_root, docname):
    for cand in (os.path.join(html_root, docname + ".html"),
                 os.path.join(html_root, docname, "index.html")):
        if os.path.isfile(cand):
            return cand
    return None


def check_images(cand_dir, content_dir, pages, lang, built, source_built, pattern):
    """Per touched page: the built `lang` HTML must reference the repo's per-language images."""
    results = []
    index = {name: set(os.path.normpath(d) for d in dirs)
             for name, dirs in tree_dirs_by_name(cand_dir, content_dir).items()}
    content_root = os.path.normpath(os.path.join(cand_dir, content_dir))
    for page in pages:
        docname = _po.page_to_docname(page, content_dir)
        rst_text = _po.read_text(os.path.join(cand_dir, page))
        ref_dirs = ref_dirs_by_name(rst_text, os.path.dirname(os.path.join(cand_dir, page)), content_root)
        plain = rst_image_basenames(rst_text)
        if source_built and source_built.get("html_root"):
            src_html = page_html(source_built["html_root"], docname)
            if src_html:
                plain |= img_basenames(_po.read_text(src_html))
        expected = image_expectations(plain, index, lang, pattern, ref_dirs)
        rec = {"page": page, "lang": lang, "expected": sorted(expected.values()),
               "missing": [], "plain_used": [], "html_found": True}
        html_path = page_html(built["html_root"], docname) if built.get("html_root") else None
        if html_path is None:
            rec["html_found"] = False
        elif expected:
            rec["missing"], rec["plain_used"] = judge_images(expected, img_basenames(_po.read_text(html_path)))
        results.append(rec)
    return results


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #
def cmd_compare(args):
    _po.require_module("sphinx", "needed to build the docs")
    worktree = os.path.realpath(args.worktree)
    langs = _po.split_csv(args.langs)
    if not langs:
        raise CompareError("--langs must name at least one language")
    work = _po.claim_work_dir(_po.work_dir_for(worktree, "build-compare", args.work_dir))
    result = {"ok": False, "base_ref": args.base_ref, "work_dir": work, "notes": [], "builds": [],
              "languages": {}, "images": [], "failures": [], "pages": [], "cand_html": {}}
    try:
        _compare(args, worktree, langs, work, result)
    except CompareError as exc:
        result["failures"].append(str(exc))
        result["error"] = str(exc)
        raise
    finally:
        # always written, so `serve` and a later `clean` find what was built even after a failure
        with open(os.path.join(work, MANIFEST), "w") as fh:
            json.dump({"cand_html": result["cand_html"], "ok": result["ok"],
                       "error": result.get("error")}, fh, indent=2, sort_keys=True)
    return result, (EXIT_OK if result["ok"] else EXIT_FINDINGS)


def _compare(args, worktree, langs, work, result):
    free = shutil.disk_usage(work).free
    if free < MIN_FREE_BYTES:
        result["notes"].append("less than 512 MiB free under the work dir; a build may fail with "
                               "'Disk quota exceeded' (use --work-dir on a larger disk)")
    export_base(worktree, args.base_ref, os.path.join(work, "base"))
    skipped = copy_candidate(worktree, os.path.join(work, "cand"))
    if skipped:
        result["notes"].append("submodule paths are not built: " + ", ".join(skipped))
    trees = {"base": os.path.join(work, "base"), "cand": os.path.join(work, "cand")}
    # the touched pages come from the two snapshots just taken: the worktree may change while the
    # builds run, and a page the candidate snapshot lacks must not be looked for afterwards
    pages = (_po.split_csv(args.pages) if args.pages
             else touched_pages(trees["base"], trees["cand"], args.content_dir))
    result["pages"] = pages
    makefile = os.path.join(trees["cand"], "Makefile")
    make_vars = (None, None)
    if os.path.isfile(makefile):
        make_vars = detect_make_vars(_po.read_text(makefile))
    if args.lang_var and args.out_var:
        make_vars = (args.lang_var, args.out_var)
    env = build_env()
    roots = [work, worktree, os.path.expanduser("~"), os.path.realpath(work)]
    builds = {}
    for lang in langs:
        problems = {}
        for tree in ("base", "cand"):
            log = os.path.join(work, "logs", "%s-%s.log" % (tree, lang))
            rec = build_one(trees[tree], tree, lang, work, args.content_dir, make_vars, env,
                            args.timeout, log)
            builds[(tree, lang)] = rec
            problems[tree] = extract_problems(_po.read_text(log), roots + [trees[tree], rec["out"]])
            result["builds"].append({k: rec[k] for k in
                                     ("tree", "lang", "mode", "returncode", "build_succeeded", "log")})
        new, fixed = diff_problems(problems["base"], problems["cand"])
        entry = {"base_succeeded": builds[("base", lang)]["build_succeeded"],
                 "cand_succeeded": builds[("cand", lang)]["build_succeeded"],
                 "new": new, "fixed": fixed}
        result["languages"][lang] = entry
        if not entry["cand_succeeded"]:
            result["failures"].append("[%s] the candidate build failed (log %s)"
                                      % (lang, builds[("cand", lang)]["log"]))
        if not entry["base_succeeded"]:
            result["notes"].append("[%s] the base build failed too: its warnings are not a "
                                   "trustworthy reference" % lang)
        for item in new:
            result["failures"].append("[%s] new versus base: %s" % (lang, item))
    result["cand_html"] = {lang: builds[("cand", lang)]["html_root"] for lang in langs
                           if builds[("cand", lang)].get("html_root")}
    conf_path = next((p for p in (os.path.join(trees["cand"], args.content_dir, "conf.py"),
                                  os.path.join(trees["cand"], "conf.py")) if os.path.isfile(p)), None)
    pattern = figure_pattern(_po.read_text(conf_path)) if conf_path else figure_pattern("")
    present = [p for p in pages if os.path.isfile(os.path.join(trees["cand"], p))]
    for page in pages:
        if page not in present:
            result["failures"].append("page %s is not in the candidate snapshot" % page)
    for lang in langs:
        if lang == args.source_lang or not builds[("cand", lang)]["build_succeeded"]:
            continue
        rows = check_images(trees["cand"], args.content_dir, present, lang, builds[("cand", lang)],
                            builds.get(("cand", args.source_lang)), pattern)
        result["images"].extend(rows)
        for row in rows:
            if not row["html_found"]:
                result["failures"].append("[%s] no built HTML for %s" % (lang, row["page"]))
            for name in row["missing"]:
                result["failures"].append("[%s] %s does not reference the per-language image %s"
                                          % (lang, row["page"], name))
    result["ok"] = not result["failures"]


def print_compare(result):
    for lang, entry in sorted(result["languages"].items()):
        print("[%s] base build %s, candidate build %s" % (
            lang, "ok" if entry["base_succeeded"] else "FAILED",
            "ok" if entry["cand_succeeded"] else "FAILED"))
        for item in entry["fixed"]:
            print("  fixed: " + item)
    for row in result["images"]:
        if row["expected"]:
            print("[%s] %s: per-language images %s" % (
                row["lang"], row["page"], "ok" if not row["missing"] else "MISSING"))
    for note in result["notes"]:
        print("note: " + note)
    for failure in result["failures"]:
        print("FAIL: " + failure)
    print("compare ok: no new warning versus base" if result["ok"] else "compare FAILED")


# --------------------------------------------------------------------------- #
# serve / stop
# --------------------------------------------------------------------------- #
def serve_roots(work, langs):
    """{lang: absolute html root} of the candidate build, from the manifest or by scanning."""
    roots = {}
    manifest = os.path.join(work, MANIFEST)
    if os.path.isfile(manifest):
        with open(manifest) as fh:
            roots = dict(json.load(fh).get("cand_html", {}))
    else:
        for name in sorted(os.listdir(work)) if os.path.isdir(work) else []:
            m = re.match(r"^cand-(.+)-out$", name)
            if m:
                root = find_html_root(os.path.join(work, name))
                if root:
                    roots[m.group(1)] = root
    if langs:
        unknown = [l for l in langs if l not in roots]
        if unknown:
            raise CompareError("no candidate HTML for: " + ", ".join(unknown))
        roots = {l: roots[l] for l in langs}
    if not roots:
        raise CompareError("no candidate HTML under %s (run a compare first)" % work)
    return roots


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):  # keep stdout for the URL/PID lines only
        pass


def cmd_serve(args):
    work = os.path.abspath(args.work_dir)
    roots = serve_roots(work, _po.split_csv(args.langs))
    handler = functools.partial(_QuietHandler, directory=work)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    port = server.server_address[1]
    pidfile = os.path.join(work, PIDFILE)
    with open(pidfile, "w") as fh:
        json.dump({"pid": os.getpid(), "port": port}, fh)

    def _stop(_signum=None, _frame=None):
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    for lang, root in sorted(roots.items()):
        rel = os.path.relpath(os.path.join(root, "index.html"), work).replace(os.sep, "/")
        print("URL %s http://127.0.0.1:%d/%s" % (lang, port, urllib.parse.quote(rel)))
    print("PID %d" % os.getpid())
    sys.stdout.flush()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            os.remove(pidfile)
        except OSError:
            pass
    return None, EXIT_OK


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie is not a server
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def cmd_stop(args):
    work = os.path.abspath(args.work_dir)
    pidfile = os.path.join(work, PIDFILE)
    if not os.path.isfile(pidfile):
        raise CompareError("no server recorded in %s" % pidfile)
    with open(pidfile) as fh:
        pid = int(json.load(fh)["pid"])
    if _alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 10
        while _alive(pid) and time.time() < deadline:
            time.sleep(0.05)
        if _alive(pid):
            raise CompareError("server %d did not stop after SIGTERM" % pid)
    try:
        os.remove(pidfile)
    except OSError:
        pass
    print("STOPPED %d" % pid)
    return None, EXIT_OK


def cmd_clean(args):
    if not args.work_dir and not args.worktree:
        raise CompareError("clean needs --work-dir D or --worktree W")
    path = _po.work_dir_for(args.worktree or "", "build-compare", args.work_dir)
    pidfile = os.path.join(path, PIDFILE)
    if os.path.isfile(pidfile):
        try:
            cmd_stop(argparse.Namespace(work_dir=path))
        except CompareError:
            pass
    removed = _po.clean_work_dir(path)
    print("%s %s" % ("removed" if removed else "nothing to remove at", path))
    return None, EXIT_OK


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parsers():
    cmp_ = argparse.ArgumentParser(prog="build_compare.py", description=__doc__.split("\n")[0])
    cmp_.add_argument("--worktree", required=True)
    cmp_.add_argument("--base-ref", required=True)
    cmp_.add_argument("--langs", required=True)
    cmp_.add_argument("--work-dir", default=None)
    cmp_.add_argument("--pages", default=None, help="default: the pages touched versus base-ref")
    cmp_.add_argument("--source-lang", default="en")
    cmp_.add_argument("--content-dir", default="content")
    cmp_.add_argument("--lang-var", default=None)
    cmp_.add_argument("--out-var", default=None)
    cmp_.add_argument("--timeout", type=int, default=3600)
    cmp_.add_argument("--json", action="store_true")

    srv = argparse.ArgumentParser(prog="build_compare.py serve")
    srv.add_argument("--work-dir", required=True)
    srv.add_argument("--port", type=int, default=0)
    srv.add_argument("--langs", default=None)

    stp = argparse.ArgumentParser(prog="build_compare.py stop")
    stp.add_argument("--work-dir", required=True)
    cln = argparse.ArgumentParser(prog="build_compare.py clean")
    cln.add_argument("--work-dir", default=None)
    cln.add_argument("--worktree", default=None)
    return cmp_, srv, stp, cln


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmp_, srv, stp, cln = build_parsers()
    if argv and argv[0] == "serve":
        args, handler, as_json = srv.parse_args(argv[1:]), cmd_serve, False
    elif argv and argv[0] == "stop":
        args, handler, as_json = stp.parse_args(argv[1:]), cmd_stop, False
    elif argv and argv[0] == "clean":
        args, handler, as_json = cln.parse_args(argv[1:]), cmd_clean, False
    else:
        args = cmp_.parse_args(argv[1:] if argv and argv[0] == "compare" else argv)
        handler, as_json = cmd_compare, args.json
    try:
        result, code = handler(args)
    except (CompareError, _po.SyncError) as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            sys.stderr.write("build_compare: %s\n" % exc)
        return EXIT_FINDINGS
    if result is not None:
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print_compare(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
