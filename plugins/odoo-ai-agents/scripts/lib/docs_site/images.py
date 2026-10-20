#!/usr/bin/env python3
"""images.py - put screenshots into a Sphinx docs repo and check every language has its image.

  images.py install --staging S --worktree W [--quality 85] [--allow-resize] [--json]
  images.py check   --worktree W --pages p1,p2 --langs en,vi [--source-lang en] [--json]

install: each staged `<rel/dir>/<stem>.<lang>.png|jpg|jpeg` becomes `W/<rel/dir>/<stem>.<lang>.jpg`
  (alpha flattened onto white, JPEG at --quality, optimized, NOT progressive, no metadata).
  A target whose directory does not exist is refused and reported (the directory is never made),
  so is a staged file without a `.<lang>` suffix, two staged files for one target, and - unless
  --allow-resize - an image whose pixel size differs from the target it would replace.
  The only command that writes inside the docs repo. Needs Pillow: exit 3 with a remedy line when
  it is missing (check does not need it).
check: every image a page references (image/figure/thumbnail directives, written WITHOUT the language
  suffix) must exist for every language under the repo's figure_language_filename (conf.py, else
  Sphinx's `{root}.{language}{ext}`). A language whose file is missing is reported with the path
  expected and whether the plain, suffix-less file exists. The SOURCE language (--source-lang, else
  the first of --langs) is the one Sphinx falls back to the plain file for, so a plain image with
  no source-language variant is fine; it is missing only when the plain file is absent too.
Exit: 0 clean, 1 a refusal or a missing image, 2 usage, 3 Pillow missing (install).
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docs_site import emit, image_refs, read_text, rst_lines  # noqa: E402
from docs_site import repo_facts  # noqa: E402

PILLOW_REMEDY = "Pillow is required for `images.py install`: python3 -m pip install --user Pillow"
IMAGE_EXT = (".png", ".jpg", ".jpeg")
_STAGED = re.compile(r"^(?P<stem>.+)\.(?P<lang>[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]{2,4})?)\.(?P<ext>png|jpe?g)$",
                     re.I)
_SUPPORTED_FIELDS = {"root", "ext", "path", "basename", "docpath", "language"}


# --------------------------------------------------------------------------- install

def plan_install(staging, worktree):
    """Map staged files to targets and decide which are refused. Pure: reads names only.

    Returns {"items": [{source, target, status, reason}], "skipped": [rel path, ...]}; status is
    "ok" or "refused".
    """
    items, skipped = [], []
    targets = {}
    for dirpath, dirnames, filenames in os.walk(staging):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, staging).replace(os.sep, "/")
            if not name.lower().endswith(IMAGE_EXT):
                skipped.append(rel)
                continue
            m = _STAGED.match(name)
            item = {"source": rel, "target": None, "status": "refused", "reason": None}
            items.append(item)
            if not m:
                item["reason"] = "NO_LANG_SUFFIX: expected <stem>.<lang>.png|jpg"
                continue
            rel_dir = os.path.dirname(rel)
            target_rel = (rel_dir + "/" if rel_dir else "") + "%s.%s.jpg" % (m.group("stem"), m.group("lang"))
            item["target"] = target_rel
            target_dir = os.path.join(worktree, rel_dir)
            if os.path.normpath(target_rel).startswith(".."):
                item["reason"] = "UNSAFE_PATH"
            elif not os.path.isdir(target_dir):
                item["reason"] = "TARGET_DIR_MISSING: %s" % (rel_dir or ".")
            else:
                item["status"] = "ok"
                targets.setdefault(target_rel, []).append(item)
    for target_rel, group in targets.items():
        if len(group) > 1:
            for item in group:
                item["status"] = "refused"
                item["reason"] = "TARGET_COLLISION: %d staged files map to %s" % (len(group), target_rel)
    return {"items": items, "skipped": skipped}


def _import_pillow():
    try:
        from PIL import Image  # noqa: WPS433
    except ImportError:
        return None
    return Image


def flatten_to_rgb(Image, img):
    """RGB image with any transparency composited onto white."""
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))
        base.paste(rgba, mask=rgba.split()[-1])
        return base
    return img.convert("RGB")


def install_one(Image, source_path, target_path, quality, allow_resize):
    """Write one JPEG. Returns (status, reason, (w, h))."""
    with Image.open(source_path) as src:
        rgb = flatten_to_rgb(Image, src)
    size = rgb.size
    if os.path.isfile(target_path) and not allow_resize:
        try:
            with Image.open(target_path) as old:
                old_size = old.size
        except Exception:  # an unreadable old file cannot be size-checked
            old_size = None
        if old_size is not None and old_size != size:
            return ("refused", "SIZE_CHANGED: target is %dx%d, new image is %dx%d (use --allow-resize)"
                    % (old_size[0], old_size[1], size[0], size[1]), size)
    # Same-directory temp name (never the ambient temp dir): the rename below is then atomic.
    tmp = "%s.tmp.%d" % (target_path, os.getpid())
    mode = stat.S_IMODE(os.stat(target_path).st_mode) if os.path.isfile(target_path) else 0o644
    try:
        rgb.save(tmp, "JPEG", quality=quality, optimize=True, progressive=False)
        os.chmod(tmp, mode)
        os.replace(tmp, target_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return ("installed", None, size)


def cmd_install(args):
    Image = _import_pillow()
    if Image is None:
        sys.stderr.write(PILLOW_REMEDY + "\n")
        if args.json:
            emit({"command": "install", "ok": False, "error": "PILLOW_MISSING", "remedy": PILLOW_REMEDY},
                 True, [PILLOW_REMEDY])
        return 3
    if not os.path.isdir(args.staging) or not os.path.isdir(args.worktree):
        sys.stderr.write("--staging and --worktree must be directories\n")
        return 2
    plan = plan_install(args.staging, args.worktree)
    results = []
    for item in plan["items"]:
        row = {"source": item["source"], "target": item["target"], "status": item["status"],
               "reason": item["reason"], "size": None}
        if item["status"] == "ok":
            status, reason, size = install_one(
                Image, os.path.join(args.staging, item["source"]),
                os.path.join(args.worktree, item["target"]), args.quality, args.allow_resize)
            row.update(status=status, reason=reason, size=list(size))
        results.append(row)
    refused = [r for r in results if r["status"] == "refused"]
    installed = [r for r in results if r["status"] == "installed"]
    report = {"command": "install", "ok": not refused, "installed": installed, "refused": refused,
              "skipped": plan["skipped"], "quality": args.quality}
    lines = ["installed %d image(s), refused %d, skipped %d non-image file(s)"
             % (len(installed), len(refused), len(plan["skipped"]))]
    lines += ["  installed %s" % r["target"] for r in installed]
    lines += ["  REFUSED %s: %s" % (r["source"], r["reason"]) for r in refused]
    emit(report, args.json, lines)
    return 1 if refused else 0


# --------------------------------------------------------------------------- check

def language_variant(ref, fmt, language, docname):
    """The path Sphinx looks for first: `figure_language_filename` applied to the reference."""
    root, ext = os.path.splitext(ref)
    dirname = os.path.dirname(root)
    if dirname and not dirname.endswith("/"):
        dirname += "/"
    docpath = os.path.dirname(docname)
    if docpath and not docpath.endswith("/"):
        docpath += "/"
    fields = {"root": root, "ext": ext, "path": dirname, "basename": os.path.basename(root),
              "docpath": docpath, "language": language}
    return fmt.format(**fields)


def _format_supported(fmt):
    try:
        names = {f for _lit, f, _spec, _conv in string.Formatter().parse(fmt) if f}
    except ValueError:
        return False
    return names <= _SUPPORTED_FIELDS


def _resolve(page, ref):
    if ref.startswith("/"):
        return os.path.normpath("content" + ref).replace(os.sep, "/")
    return os.path.normpath(os.path.join(os.path.dirname(page), ref)).replace(os.sep, "/")


def check_pages(worktree, pages, langs, fmt, source_lang=None):
    """Findings for `images.py check`: {missing, errors, checked}.

    `source_lang` (default: the first language) may rely on the plain file; every other
    language needs its own variant."""
    source_lang = source_lang or (langs[0] if langs else None)
    missing, errors, checked = [], [], 0
    usable = _format_supported(fmt)
    for page in pages:
        text = read_text(os.path.join(worktree, page))
        if text is None:
            errors.append({"page": page, "error": "PAGE_NOT_FOUND"})
            continue
        if not usable:
            errors.append({"page": page, "error": "UNSUPPORTED_FIGURE_LANGUAGE_FILENAME",
                           "detail": fmt})
            continue
        docname = page[len("content/"):] if page.startswith("content/") else page
        for no, ref in image_refs(rst_lines(text)):
            if re.match(r"^[a-zA-Z][\w+.-]*://", ref):
                continue
            checked += 1
            plain = _resolve(page, ref)
            plain_exists = os.path.isfile(os.path.join(worktree, plain))
            for lang in langs:
                variant = language_variant(ref, fmt, lang, docname)
                expected = _resolve(page, variant)
                if not os.path.isfile(os.path.join(worktree, expected)):
                    if lang == source_lang and plain_exists:
                        continue
                    missing.append({"page": page, "line": no, "ref": ref, "lang": lang,
                                    "expected": expected, "plain_exists": plain_exists})
    return {"missing": missing, "errors": errors, "checked": checked}


def cmd_check(args):
    if not os.path.isdir(args.worktree):
        sys.stderr.write("--worktree must be a directory\n")
        return 2
    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    if not pages or not langs:
        sys.stderr.write("--pages and --langs need at least one value\n")
        return 2
    conf_text = read_text(os.path.join(args.worktree, "conf.py"))
    values = repo_facts.conf_values(conf_text) if conf_text is not None else None
    fmt = repo_facts.DEFAULT_FIGURE_FILENAME
    source = "sphinx-default"
    if values and isinstance(values.get("figure_language_filename"), str):
        fmt, source = values["figure_language_filename"], "conf.py"
    source_lang = args.source_lang or langs[0]
    result = check_pages(args.worktree, pages, langs, fmt, source_lang)
    ok = not result["missing"] and not result["errors"]
    report = {"command": "check", "ok": ok, "figure_language_filename": {"value": fmt, "source": source},
              "languages": langs, "source_lang": source_lang, "pages": pages, "images_checked": result["checked"],
              "missing": result["missing"], "errors": result["errors"]}
    lines = ["checked %d image reference(s) in %d page(s) for %s: %d missing"
             % (result["checked"], len(pages), ",".join(langs), len(result["missing"]))]
    lines += ["  MISSING %s:%d [%s] %s (plain_exists: %s)"
              % (m["page"], m["line"], m["lang"], m["expected"], str(m["plain_exists"]).lower())
              for m in result["missing"]]
    lines += ["  ERROR %s %s" % (e["page"], e["error"]) for e in result["errors"]]
    emit(report, args.json, lines)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install screenshots / check per-language images.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("install")
    p.add_argument("--staging", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--quality", type=int, default=85)
    p.add_argument("--allow-resize", action="store_true")
    p.add_argument("--json", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--worktree", required=True)
    c.add_argument("--pages", required=True, help="comma-separated content/<path>.rst")
    c.add_argument("--langs", required=True, help="comma-separated language codes")
    c.add_argument("--source-lang", default=None,
                   help="the language Sphinx may serve from the plain image (default: the first of --langs)")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "install":
        return cmd_install(args)
    if args.cmd == "check":
        return cmd_check(args)
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
