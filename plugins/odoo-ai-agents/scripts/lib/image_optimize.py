#!/usr/bin/env python3
"""image_optimize.py - lossless size optimisation of PNG screenshots.

  image_optimize.py PATH...

Each PATH is a file or a directory (recursed). Only `*.png` (any case) is processed; every other
file is listed as skipped. A PNG is re-encoded with Pillow `optimize=True`, keeping mode, palette,
transparency, ICC profile, dpi and text chunks. The result is written beside the source, its decoded
pixels are compared with the source (as RGBA), and the source is replaced atomically only when the
pixels are identical AND the file is smaller. An animated PNG, and a PNG carrying a gamma or sRGB
chunk (Pillow cannot write those back), is left untouched.

Output, one KEY=VALUE per line:
  OPTIMIZED=<path> <bytes before> <bytes after>
  KEPT=<path> <reason>
  SKIPPED=<path> not a png
  SAVED_BYTES=<n>
Pillow missing: `PILLOW=missing` and `REMEDY=<text>`, every file untouched.
Exit: 0 always (a documentation run never fails on this step), 2 usage.
"""
from __future__ import annotations

import os
import sys

PILLOW_REMEDY = ("macOS (Homebrew): brew install pillow; Debian/Ubuntu: sudo apt install python3-pil; "
                 "Fedora: sudo dnf install python3-pillow")


def _walk(paths):
    for path in paths:
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(dirnames)
                for name in sorted(filenames):
                    yield os.path.join(dirpath, name)
        else:
            yield path


def _save_kwargs(img):
    kwargs = {"optimize": True}
    for key in ("icc_profile", "dpi", "transparency"):
        if key in img.info:
            kwargs[key] = img.info[key]
    text = getattr(img, "text", None)
    if text:
        from PIL.PngImagePlugin import PngInfo
        meta = PngInfo()
        for key, value in text.items():
            meta.add_text(key, value)
        kwargs["pnginfo"] = meta
    return kwargs


def optimize_one(Image, path):
    """Returns ("OPTIMIZED", before, after) or ("KEPT", reason)."""
    before = os.path.getsize(path)
    tmp = "%s.opt.%d.png" % (path[:-4], os.getpid())
    try:
        with Image.open(path) as src:
            if getattr(src, "n_frames", 1) > 1:
                return ("KEPT", "animated")
            if "gamma" in src.info or "srgb" in src.info:
                return ("KEPT", "gamma or sRGB chunk")
            src.load()
            source_rgba = src.convert("RGBA")
            src.save(tmp, "PNG", **_save_kwargs(src))
        with Image.open(tmp) as out:
            identical = out.size == source_rgba.size and out.convert("RGBA").tobytes() == source_rgba.tobytes()
        after = os.path.getsize(tmp)
        if not identical:
            return ("KEPT", "pixels differ")
        if after >= before:
            return ("KEPT", "already optimal")
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
        return ("OPTIMIZED", before, after)
    except Exception as exc:  # an unreadable image never fails the run
        return ("KEPT", "unreadable: %s" % exc.__class__.__name__)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        sys.stderr.write("usage: image_optimize.py PATH...\n")
        return 2
    try:
        from PIL import Image
    except ImportError:
        print("PILLOW=missing")
        print("REMEDY=" + PILLOW_REMEDY)
        return 0
    saved = 0
    for path in _walk(paths):
        if not path.lower().endswith(".png"):
            print("SKIPPED=%s not a png" % path)
            continue
        result = optimize_one(Image, path)
        if result[0] == "OPTIMIZED":
            saved += result[1] - result[2]
            print("OPTIMIZED=%s %d %d" % (path, result[1], result[2]))
        else:
            print("KEPT=%s %s" % (path, result[1]))
    print("SAVED_BYTES=%d" % saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
