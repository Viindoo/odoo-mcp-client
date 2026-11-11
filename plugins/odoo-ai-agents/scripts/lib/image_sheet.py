#!/usr/bin/env python3
"""image_sheet.py - review many screenshots at once, and read an image's pixel size.

  image_sheet.py sheet --out FILE --col-width PX --columns N --inputs FILE [FILE...]
  image_sheet.py size  --inputs FILE [FILE...]

`sheet` tiles the inputs, in the order given, into a grid of N columns, each column PX pixels wide
(white background, 8 px gaps), and writes it to FILE (.png, .jpg or .jpeg). An input wider than PX is
scaled DOWN to PX; an input that is not wider is kept at its own size - an image is never enlarged.
The canvas size is computed from the image headers first; a request whose canvas exceeds the limits
below is refused before any pixel buffer is allocated. The process also caps its own address space,
so a bug here cannot grow without bound.

`size` reports the pixel width and height each file declares in its header (nothing is decoded).
PNG, GIF and JPEG are read with the standard library alone, so `size` works without Pillow; any
other format uses Pillow when it is installed. `sheet` always needs Pillow.

Limits (the constants below): COL_WIDTH 64-2000 px, COLUMNS 1-12, INPUTS at most 200 for a sheet,
canvas at most 16,000,000 pixels and 8,000 px on a side, one input at most 100,000,000 pixels.

Output, one KEY=VALUE per line:
  SHEET=<path> <width> <height> <images>
  SIZE=<path> <width> <height>
  UNREADABLE=<path> <reason>            (size: not an image, or a format that needs Pillow; run goes on)
  REFUSED=<one line: what was asked, the limit>
  ERROR=<one line>
Pillow missing: `PILLOW=missing` and `REMEDY=<text>`, nothing written (for `size`: only when a file
needed it, after the other files are reported).
Exit: 0 done (also when Pillow is missing, as image_optimize.py), 1 refused or failed, 2 usage.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

PILLOW_REMEDY = ("macOS (Homebrew): brew install pillow; Debian/Ubuntu: sudo apt install python3-pil; "
                 "Fedora: sudo dnf install python3-pillow")

MIN_COL_WIDTH, MAX_COL_WIDTH = 64, 2000
MAX_COLUMNS = 12
MAX_INPUTS = 200
MAX_CANVAS_PIXELS = 16_000_000      # RGB: 48 MB of pixels
MAX_CANVAS_SIDE = 8000
MAX_INPUT_PIXELS = 100_000_000
GAP = 8
ADDRESS_SPACE_CAP = 2 * 1024 ** 3   # 2 GiB, headroom over Pillow + the largest allowed canvas


def _cap_memory():
    """Best effort (RLIMIT_AS is not enforced on every platform): never fatal."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = ADDRESS_SPACE_CAP if hard in (-1, resource.RLIM_INFINITY) else min(ADDRESS_SPACE_CAP, hard)
        if soft in (-1, resource.RLIM_INFINITY) or soft > limit:
            resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    except (ImportError, ValueError, OSError):
        pass


def _out(line):
    print(line)
    sys.stdout.flush()


def plan(sizes, col_width, columns):
    """Pure geometry from (w, h) header sizes. Returns (cells, canvas_w, canvas_h); cells are
    (x, y, w, h) with the scaled size. Never enlarges."""
    cells, y, row_h = [], GAP, 0
    used_cols = min(columns, len(sizes))
    for i, (w, h) in enumerate(sizes):
        col = i % columns
        if col == 0 and i:
            y += row_h + GAP
            row_h = 0
        cw = min(w, col_width)
        ch = max(1, round(h * cw / w))
        cells.append((GAP + col * (col_width + GAP), y, cw, ch))
        row_h = max(row_h, ch)
    return cells, GAP + used_cols * (col_width + GAP), y + row_h + GAP


def _refuse(text):
    _out("REFUSED=" + text)
    return 1


def header_size(path):
    """(width, height) of a PNG, GIF or JPEG read from its header with the standard library, or None
    when the file is not one of those (or its header is cut short)."""
    with open(path, "rb") as fh:
        head = fh.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR" and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a") and len(head) >= 10:
            return struct.unpack("<HH", head[6:10])
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                byte = fh.read(1)
                if not byte:
                    return None
                if byte != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":          # fill bytes
                    marker = fh.read(1)
                if not marker:
                    return None
                code = marker[0]
                if code == 0 or code == 1 or 0xD0 <= code <= 0xD9:
                    continue                      # no length field
                if code == 0xDA:
                    return None                   # scan data reached without a frame header
                seg = fh.read(2)
                if len(seg) < 2:
                    return None
                length = struct.unpack(">H", seg)[0]
                if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                    frame = fh.read(5)
                    if len(frame) < 5:
                        return None
                    height, width = struct.unpack(">HH", frame[1:5])
                    return (width, height)
                fh.seek(length - 2, 1)
    return None


def cmd_size(Image, args):
    needed_pillow = False
    for path in args.inputs:
        try:
            dims = header_size(path)
            if dims is None:
                if Image is None:
                    needed_pillow = True
                    _out("UNREADABLE=%s needs Pillow" % path)
                    continue
                with Image.open(path) as img:
                    dims = img.size
            _out("SIZE=%s %d %d" % (path, dims[0], dims[1]))
        except Exception as exc:
            _out("UNREADABLE=%s %s" % (path, exc.__class__.__name__))
    if needed_pillow:
        _out("PILLOW=missing")
        _out("REMEDY=" + PILLOW_REMEDY)
    return 0


def cmd_sheet(Image, args):
    n = len(args.inputs)
    asked = "asked %d images, col-width %d, columns %d" % (n, args.col_width, args.columns)
    if not MIN_COL_WIDTH <= args.col_width <= MAX_COL_WIDTH:
        return _refuse("%s; limit col-width %d-%d" % (asked, MIN_COL_WIDTH, MAX_COL_WIDTH))
    if not 1 <= args.columns <= MAX_COLUMNS:
        return _refuse("%s; limit columns 1-%d" % (asked, MAX_COLUMNS))
    if n > MAX_INPUTS:
        return _refuse("%s; limit %d images" % (asked, MAX_INPUTS))
    ext = os.path.splitext(args.out)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return _refuse("output %s; limit .png, .jpg or .jpeg" % args.out)
    sizes = []
    for path in args.inputs:                         # headers only, no pixels
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Exception as exc:
            _out("ERROR=cannot read %s (%s)" % (path, exc.__class__.__name__))
            return 1
        if w < 1 or h < 1 or w * h > MAX_INPUT_PIXELS:
            return _refuse("input %s is %dx%d; limit %d pixels" % (path, w, h, MAX_INPUT_PIXELS))
        sizes.append((w, h))
    cells, cw, ch = plan(sizes, args.col_width, args.columns)
    if cw * ch > MAX_CANVAS_PIXELS or max(cw, ch) > MAX_CANVAS_SIDE:
        return _refuse("%s makes a %dx%d canvas; limit %d pixels and %d on a side"
                       % (asked, cw, ch, MAX_CANVAS_PIXELS, MAX_CANVAS_SIDE))
    try:
        canvas = Image.new("RGB", (cw, ch), (255, 255, 255))
        for path, (x, y, w, h) in zip(args.inputs, cells):
            with Image.open(path) as img:
                if img.size[0] > w:
                    img.draft("RGB", (w, h))
                tile = img.convert("RGBA")
                if tile.size != (w, h):
                    tile = tile.resize((w, h), Image.LANCZOS)
                canvas.paste(tile, (x, y), tile)
        canvas.save(args.out)
    except MemoryError:
        _out("ERROR=out of memory building a %dx%d canvas" % (cw, ch))
        return 1
    except Exception as exc:
        _out("ERROR=%s: %s" % (exc.__class__.__name__, exc))
        return 1
    _out("SHEET=%s %d %d %d" % (args.out, cw, ch, n))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="image_sheet.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sheet = sub.add_parser("sheet", help="tile images into one contact sheet")
    sheet.add_argument("--out", required=True)
    sheet.add_argument("--col-width", type=int, required=True)
    sheet.add_argument("--columns", type=int, required=True)
    sheet.add_argument("--inputs", nargs="+", required=True)
    size = sub.add_parser("size", help="report pixel width and height")
    size.add_argument("--inputs", nargs="+", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is None and args.command == "sheet":
        _out("PILLOW=missing")
        _out("REMEDY=" + PILLOW_REMEDY)
        return 0
    _cap_memory()
    return (cmd_sheet if args.command == "sheet" else cmd_size)(Image, args)


if __name__ == "__main__":
    sys.exit(main())
