#!/usr/bin/env python3
"""icon_gate.py - measure the icon family of an Odoo series, then rasterize and verify a module icon.

Stdlib only; Pillow is needed for `facts`, `check` and `sample` (without it the gate says
CANNOT-VERIFY, it never says PASS). Output is KEY=VALUE lines. Nothing here knows a series:
the spec an icon must meet is MEASURED from the series' own core icons
(`<addons dir>/*/static/description/icon.*`) by `facts`, and optionally OBSERVED in the browser
by `observe`.

  probe
      RASTERIZERS=<csv, probe order, available ones only; chrome as chrome:<path>>
      PILLOW=1|0                                                       exit 0

  facts --core-addons DIR [--core-addons DIR ...] [--out FACTS.txt]
      Measures every icon.png found under the given addons directories (an Odoo checkout has
      several: pass each). Prints, and with --out also writes, the family spec:
      NATIVE_SIZE=WxH (median)  NATIVE_MODE=RGBA|P|RGB  NATIVE_STYLE=tile|flat|unknown
      NATIVE_FORMAT=png|svg|both  CORNER_ALPHA=transparent|opaque  SAMPLE_COUNT=n
      FAMILY_OPAQUE_PCT (median share of opaque pixels, 0-100)  FAMILY_SATURATION and
      FAMILY_LIGHTNESS (median over icons of the mean chroma / luminance of the opaque pixels,
      0-255)  FAMILY_RADIUS_PX (median tile corner radius, tile style only)
      FAMILY_SAMPLE=<path> (one line per measured icon, read back by `check` for its contact sheet)
      A tile is a large uniform opaque plate along the border of the icon; a flat icon is a
      glyph on transparency. Mode, style and corner alpha are the majority of the icons.
      No icon found: NATIVE_STYLE=unknown, SAMPLE_COUNT=0, exit 4 (nothing is guessed).
      No Pillow: only size and mode from the PNG headers, NATIVE_STYLE=unknown, exit 2.
      Exit: 0 measured, 2 CANNOT-VERIFY, 3 usage, 4 no icon found.

  render <icon.svg> <out.png> [--size N | --facts FACTS.txt] [--rasterizer auto|<name>]
      RASTERIZER=<label>  PNG_PATH=<out.png>                           exit 0
      The size is --size, else the width of NATIVE_SIZE in the facts file, else 256.
      no rasterizer, or the chosen one failed                          exit 2
      Probe order: rsvg-convert, inkscape, chrome (headless), cairosvg, magick, convert.

  check <icon.png|icon.svg> --facts FACTS.txt [--out-dir DIR] [--rasterizer auto|<name>]
      ICON_GATE=PASS|FAIL|CANNOT-VERIFY  PNG_PATH  PNG_SIZE  PNG_MODE  [RASTERIZER]
      ICON_STYLE=tile|flat  ICON_OPAQUE_PCT  ICON_SATURATION  ICON_LIGHTNESS
      COLORFUL_PCT  NONBLANK=1|0  CONSISTENCY=ok|outlier  CONSISTENCY_REASON=<one per metric>
      CONTRAST_LIGHT=ok|low  CONTRAST_DARK=ok|low  PREVIEW_32  PREVIEW_ZOOM  CONTACT_SHEET
      FAIL_REASON=<one per line>
      FAIL (exit 1): size differs from NATIVE_SIZE; mode is not RGBA (a palette family still
      needs an RGBA icon); a corner pixel is not fully transparent when CORNER_ALPHA=transparent;
      the style differs from NATIVE_STYLE (a flat family refuses a large opaque plate, a tile
      family refuses an icon without one); blank image; fewer than 1% of the opaque pixels carry
      colour (chroma, max-min of RGB, above 8). A facts file with NATIVE_STYLE=unknown, or no
      Pillow, is CANNOT-VERIFY (exit 2).
      WARN only (exit stays 0): CONSISTENCY=outlier when the icon's opaque share is more than
      25 points, or its saturation or lightness more than 35 (0-255 scale), away from the
      family median; the agent decides. CONTRAST_LIGHT / CONTRAST_DARK are low when the mean
      luminance of the opaque pixels is within 60 (0-255) of white / of a dark background.
      Previews: icon-32.png (32 px, LANCZOS) and icon-32-x5.png (the 32 px icon enlarged 5x,
      nearest neighbour = what a 32 px render shows). icon-contact-sheet.png shows the icon
      first, then up to 8 family icons, each scaled into the same box, on a light row above a
      dark row, to judge whether the icon stands out.
      --out-dir defaults to <ISOLATE dir>/icon-gate (scripts/lib/paths.py).
      Exit: 0 PASS, 1 FAIL, 2 CANNOT-VERIFY, 3 usage.

  sample <icon.png> [<icon.png> ...]
      For each sibling icon: STYLE=tile|flat, PLATE=#rrggbb (tile only: dominant opaque colour
      of the border band), GLYPH=#rrggbb (dominant opaque colour off the plate),
      CORNER_RADIUS_PX=<n> (estimated from where the top edge turns opaque), SIZE=<WxH>.
      Lets a designer inherit the palette and corner radius of an existing icon family.

  observe --base-url URL --ui-user USER --module NAME [--out-dir DIR]
      Needs a live instance and the recorder library (scripts/lib/video_record.py). Signs in
      like the recorder, opens the apps screens, finds the square module icons and measures
      how the client draws them: BOX_PX=WxH (the module's icon, else the median)
      THEME_TILE=yes|no (a padded or rounded background box behind the image)
      TILE_BOX_PX, TILE_BG, TILE_RADIUS, TILE_PADDING (that box), ICON_COUNT,
      ICON_OVERRIDE=yes|no (the icon shown for --module differs from the module's own
      static/description/icon.png bytes), SCREENSHOT=<path> (the apps grid, full page),
      UNKNOWN=<what could not be measured>.
      Exit: 0 measured, 2 recorder library missing (REMEDY=), 4 nothing measured.
"""
import argparse
import base64
import collections
import glob
import importlib.util
import os
import shutil
import statistics
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
CHROMA_MIN = 8            # max-min of RGB above this counts as "has colour"
COLORFUL_MIN_PCT = 1.0    # of the opaque pixels
DARK_BG_LUM = 0.299 * 33 + 0.587 * 37 + 0.114 * 41
INSTALL_HINT = (
    "install one of: rsvg-convert (librsvg), inkscape, google-chrome/chromium, "
    "cairosvg (pip install cairosvg), ImageMagick (magick/convert)"
)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def out(key, value):
    print(f"{key}={value}")


# ---------------------------------------------------------------------------
# rasterizers
# ---------------------------------------------------------------------------
def probe_rasterizers():
    """[(name, label, path_or_None)] for the rasterizers available now, in probe order."""
    found = []
    for name in ("rsvg-convert", "inkscape"):
        p = shutil.which(name)
        if p:
            found.append((name, name, p))
    for name in CHROME_NAMES:
        p = shutil.which(name)
        if p:
            found.append(("chrome", f"chrome:{p}", p))
            break
    if importlib.util.find_spec("cairosvg") is not None:
        found.append(("cairosvg", "cairosvg", None))
    for name in ("magick", "convert"):
        p = shutil.which(name)
        if p:
            found.append((name, name, p))
    return found


def _chrome_page(svg_path, size):
    with open(svg_path, "rb") as fh:
        svg_b64 = base64.b64encode(fh.read()).decode("ascii")
    html = (
        '<html><body style="margin:0"><img src="data:image/svg+xml;base64,'
        f'{svg_b64}" width={size} height={size}></body></html>'
    )
    return "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("ascii")


def _run_rasterizer(name, path, svg, png, size):
    n = str(size)
    if name == "rsvg-convert":
        cmd = [path, "-w", n, "-h", n, svg, "-o", png]
    elif name == "inkscape":
        cmd = [path, "--export-type=png", f"--export-width={n}", f"--export-height={n}",
               f"--export-filename={png}", svg]
    elif name == "chrome":
        cmd = [path, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--force-device-scale-factor=1", "--default-background-color=00000000",
               f"--window-size={n},{n}", f"--screenshot={png}", _chrome_page(svg, size)]
    elif name == "cairosvg":
        try:
            import cairosvg
            cairosvg.svg2png(url=svg, write_to=png, output_width=size, output_height=size)
            return True
        except Exception:
            return False
    else:  # magick / convert
        cmd = [path, "-background", "none", svg, "-resize", f"{n}x{n}", png]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and os.path.isfile(png) and os.path.getsize(png) > 0


def render(svg, png, size, wanted="auto"):
    """(label, None) on success, (None, reason) otherwise."""
    available = probe_rasterizers()
    if wanted != "auto":
        available = [a for a in available if a[0] == wanted or a[1] == wanted]
    if not available:
        what = "no rasterizer available" if wanted == "auto" else f"rasterizer {wanted} not available"
        return None, f"{what}; {INSTALL_HINT}"
    os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
    for name, label, path in available:
        if os.path.exists(png):
            os.remove(png)
        if _run_rasterizer(name, path, svg, png, size):
            return label, None
    return None, "every available rasterizer failed on " + svg


def cmd_probe(_args):
    out("RASTERIZERS", ",".join(label for _n, label, _p in probe_rasterizers()))
    out("PILLOW", 1 if _pillow() else 0)
    return 0


# ---------------------------------------------------------------------------
# measuring one icon
# ---------------------------------------------------------------------------
PLATE_SHARE_MIN = 0.4     # of the border band: one uniform opaque colour this wide is a plate
OPAQUE_ALPHA = 128
OUTLIER_OPAQUE_PTS = 25.0
OUTLIER_COLOUR = 35.0
CONTRAST_MIN = 60.0       # |mean luminance - background| on 0-255
DARK_BG = (33, 37, 41)
LIGHT_BG = (255, 255, 255)
SHEET_BOX = 96
SHEET_PAD = 12
SHEET_FAMILY_MAX = 8
PNG_MODES = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


def _png_header(path):
    """:returns: (width, height, mode) from a PNG header, or None when it is not a PNG."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(26)
    except OSError:
        return None
    if len(head) < 26 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h, PNG_MODES.get(head[25], "?")


def _corner_radius(px, w):
    """Radius of the rounded corner, from where the top row turns opaque.

    The top row's pixel centres sit half a pixel inside the arc's tangent line, so the first
    opaque x is r - sqrt(r) short of the radius; solve that back to r."""
    x0 = next((x for x in range(w) if px[x, 0][3] >= 128), None)
    if x0 is None or x0 == 0:
        return 0
    return round(((1 + (1 + 4 * x0) ** 0.5) / 2) ** 2)


def _bucket(c):
    return (c[0] >> 3, c[1] >> 3, c[2] >> 3)


def _analyse(img):
    """Measures an RGBA image.

    :returns: dict with w, h, opaque_pct, saturation, lightness, colourful_pct, nonblank,
        corners_transparent, style (tile|flat), plate, glyph, radius
    """
    w, h = img.size
    px = img.load()
    data = img.tobytes()
    opaque = colourful = 0
    sat = lum = 0.0
    colours = set()
    covered = False
    for r, g, b, a in zip(data[0::4], data[1::4], data[2::4], data[3::4]):
        colours.add((r, g, b, a))
        if a:
            covered = True
        if a >= OPAQUE_ALPHA:
            opaque += 1
            chroma = max(r, g, b) - min(r, g, b)
            sat += chroma
            lum += 0.299 * r + 0.587 * g + 0.114 * b
            if chroma > CHROMA_MIN:
                colourful += 1
    band = max(2, w // 16)
    ring = 0
    buckets = {}
    exact = {}
    allcols = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 255:
                allcols[(r, g, b)] = allcols.get((r, g, b), 0) + 1
            if min(x, y, w - 1 - x, h - 1 - y) >= band:
                continue
            ring += 1
            if a == 255:
                key = _bucket((r, g, b))
                buckets[key] = buckets.get(key, 0) + 1
                exact[(r, g, b)] = exact.get((r, g, b), 0) + 1
    plate = None
    if buckets:
        best = max(buckets, key=buckets.get)
        if ring and buckets[best] / ring >= PLATE_SHARE_MIN:
            inside = {c: n for c, n in exact.items() if _bucket(c) == best}
            plate = max(inside, key=inside.get)
    pool = allcols
    if plate is not None:
        pool = {c: n for c, n in allcols.items() if _bucket(c) != _bucket(plate)} or allcols
    glyph = max(pool, key=pool.get) if pool else None
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    return {
        "w": w, "h": h,
        "opaque_pct": 100.0 * opaque / (w * h),
        "saturation": sat / opaque if opaque else 0.0,
        "lightness": lum / opaque if opaque else 0.0,
        "colourful_pct": 100.0 * colourful / opaque if opaque else 0.0,
        "nonblank": len(colours) > 1 and covered,
        "corners_transparent": all(c[3] == 0 for c in corners),
        "style": "tile" if plate is not None else "flat",
        "plate": _hex(plate) if plate else None,
        "glyph": _hex(glyph) if glyph else None,
        "radius": _corner_radius(px, w) if plate is not None else 0,
    }


def _open_rgba(path):
    from PIL import Image
    img = Image.open(path)
    img.load()
    return img, img.convert("RGBA")


def _cannot_verify(reason, **keys):
    out("ICON_GATE", "CANNOT-VERIFY")
    for k, v in keys.items():
        out(k, v)
    out("FAIL_REASON", reason)
    return 2


NO_PILLOW = "Pillow is not installed, so the pixels cannot be read (pip install pillow); this is not a pass"


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------
def _num(v):
    return str(int(v)) if v == int(v) else ("%.2f" % v).rstrip("0").rstrip(".")


def cmd_facts(args):
    seen = set()
    pngs, svgs = [], 0
    for d in args.core_addons:
        for path in sorted(glob.glob(os.path.join(d, "*", "static", "description", "icon.*"))):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            ext = path.rsplit(".", 1)[-1].lower()
            if ext == "svg":
                svgs += 1
            elif ext == "png":
                pngs.append(path)
    measured = []
    have_pillow = _pillow()
    for path in pngs:
        head = _png_header(path)
        if head is None:
            continue
        rec = {"path": path, "w": head[0], "h": head[1], "mode": head[2]}
        if have_pillow:
            try:
                img, rgba = _open_rgba(path)
            except Exception:
                continue
            rec["mode"] = img.mode
            rec.update(_analyse(rgba))
        measured.append(rec)
    if not measured:
        return _emit_facts([("NATIVE_STYLE", "unknown"), ("SAMPLE_COUNT", 0)], args, 4)
    fmt = "both" if svgs else "png"
    wmed = int(statistics.median(r["w"] for r in measured))
    hmed = int(statistics.median(r["h"] for r in measured))
    mode = collections.Counter(r["mode"] for r in measured).most_common(1)[0][0]
    lines = [("NATIVE_SIZE", f"{wmed}x{hmed}"), ("NATIVE_MODE", mode)]
    status = 0
    if have_pillow:
        top = collections.Counter(r["style"] for r in measured).most_common()
        style = top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else "unknown"
        clear = sum(r["corners_transparent"] for r in measured) * 2 > len(measured)
        lines += [("NATIVE_STYLE", style), ("NATIVE_FORMAT", fmt),
                  ("CORNER_ALPHA", "transparent" if clear else "opaque"),
                  ("SAMPLE_COUNT", len(measured)),
                  ("FAMILY_OPAQUE_PCT", _num(statistics.median(r["opaque_pct"] for r in measured))),
                  ("FAMILY_SATURATION", _num(statistics.median(r["saturation"] for r in measured))),
                  ("FAMILY_LIGHTNESS", _num(statistics.median(r["lightness"] for r in measured)))]
        radii = [r["radius"] for r in measured if r["style"] == "tile"]
        if radii:
            lines.append(("FAMILY_RADIUS_PX", _num(statistics.median(radii))))
    else:
        lines += [("NATIVE_STYLE", "unknown"), ("NATIVE_FORMAT", fmt),
                  ("SAMPLE_COUNT", len(measured)), ("REASON", NO_PILLOW)]
        status = 2
    lines += [("FAMILY_SAMPLE", r["path"]) for r in measured]
    return _emit_facts(lines, args, status)


def _emit_facts(lines, args, status):
    for k, v in lines:
        out(k, v)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("".join(f"{k}={v}\n" for k, v in lines))
    return status


def read_facts(path):
    """:returns: dict of the facts file; FAMILY_SAMPLE is a list. Raises ValueError/OSError."""
    facts = {"FAMILY_SAMPLE": []}
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if "=" not in ln:
                continue
            k, v = ln.rstrip("\n").split("=", 1)
            if k == "FAMILY_SAMPLE":
                facts[k].append(v)
            else:
                facts[k] = v
    if "NATIVE_STYLE" not in facts:
        raise ValueError("no NATIVE_STYLE line: not a facts file")
    return facts


def _size_of(facts):
    try:
        w, h = facts["NATIVE_SIZE"].split("x")
        return int(w), int(h)
    except (KeyError, ValueError):
        return None


def cmd_render(args):
    size = args.size
    if size is None and args.facts:
        try:
            native = _size_of(read_facts(args.facts))
        except (OSError, ValueError) as exc:
            print(f"icon_gate: --facts {args.facts!r}: {exc}", file=sys.stderr)
            return 3
        size = native[0] if native else None
    label, reason = render(args.svg, args.png, size or 256, args.rasterizer)
    if label is None:
        out("RENDER", "CANNOT-VERIFY")
        out("REASON", reason)
        return 2
    out("RASTERIZER", label)
    out("PNG_PATH", args.png)
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def _default_out_dir():
    paths = _load("paths")
    return os.path.join(paths.isolate_dir(), "icon-gate")


def _contact_sheet(Image, rgba, family_paths, dest):
    """A strip of the new icon then up to 8 family icons on a light row above a dark row."""
    pick = [p for p in family_paths if os.path.isfile(p)]
    if len(pick) > SHEET_FAMILY_MAX:
        step = len(pick) / SHEET_FAMILY_MAX
        pick = [pick[int(i * step)] for i in range(SHEET_FAMILY_MAX)]
    icons = [rgba]
    for p in pick:
        try:
            icons.append(Image.open(p).convert("RGBA"))
        except Exception:
            continue
    cell = SHEET_BOX + 2 * SHEET_PAD
    sheet = Image.new("RGB", (SHEET_PAD + len(icons) * (SHEET_BOX + SHEET_PAD), 2 * cell), LIGHT_BG)
    for row, bg in enumerate((LIGHT_BG, DARK_BG)):
        sheet.paste(bg, (0, row * cell, sheet.width, (row + 1) * cell))
        for i, ic in enumerate(icons):
            scale = SHEET_BOX / max(ic.size)
            small = ic.resize((max(1, round(ic.width * scale)), max(1, round(ic.height * scale))),
                              Image.LANCZOS)
            x = SHEET_PAD + i * (SHEET_BOX + SHEET_PAD) + (SHEET_BOX - small.width) // 2
            y = row * cell + SHEET_PAD + (SHEET_BOX - small.height) // 2
            sheet.paste(small, (x, y), small)
    sheet.save(dest)
    return dest


def cmd_check(args):
    try:
        facts = read_facts(args.facts)
    except (OSError, ValueError) as exc:
        print(f"icon_gate: --facts {args.facts!r} is not readable ({exc})", file=sys.stderr)
        return 3
    try:
        out_dir = args.out_dir or _default_out_dir()
    except Exception as exc:
        print(f"icon_gate: no output dir ({exc}); pass --out-dir", file=sys.stderr)
        return 3
    os.makedirs(out_dir, exist_ok=True)
    native = _size_of(facts)
    if facts["NATIVE_STYLE"] not in ("tile", "flat") or native is None:
        return _cannot_verify("the facts file does not state the family (NATIVE_STYLE="
                              f"{facts['NATIVE_STYLE']}); run facts on a checkout with icons")

    src = args.icon
    extra = {}
    if src.lower().endswith(".svg"):
        png = os.path.join(out_dir, "icon.png")
        label, reason = render(src, png, native[0], args.rasterizer)
        if label is None:
            return _cannot_verify(reason)
        extra["RASTERIZER"] = label
        src = png
    if not _pillow():
        return _cannot_verify(NO_PILLOW)
    from PIL import Image

    reasons = []
    try:
        img, rgba = _open_rgba(src)
    except Exception as exc:
        out("ICON_GATE", "FAIL")
        out("PNG_PATH", src)
        out("FAIL_REASON", f"not a readable image ({type(exc).__name__})")
        return 1
    m = _analyse(rgba)
    if img.format != "PNG":
        reasons.append(f"file is {img.format}, not PNG")
    if (img.width, img.height) != native:
        reasons.append(f"size is {img.width}x{img.height}, expected {native[0]}x{native[1]}")
    if img.mode != "RGBA":
        reasons.append(f"mode is {img.mode}, expected RGBA (save as RGBA colour)")
    if facts.get("CORNER_ALPHA") == "transparent" and not m["corners_transparent"]:
        reasons.append("a corner pixel is not fully transparent, the family has transparent corners")
    if m["style"] != facts["NATIVE_STYLE"]:
        if facts["NATIVE_STYLE"] == "flat":
            reasons.append(f"style mismatch: the icon draws a large opaque plate ({m['plate']}) "
                           "but the family is flat glyphs on transparency")
        else:
            reasons.append("style mismatch: the icon has no large opaque plate but the family "
                           "is tiles")
    if m["colourful_pct"] < COLORFUL_MIN_PCT:
        reasons.append(f"only {m['colourful_pct']:.2f}% of the opaque pixels carry colour (need >= "
                       f"{COLORFUL_MIN_PCT:g}%): the icon is grey, not colourful")
    if not m["nonblank"]:
        reasons.append("the icon is blank (a single colour or fully transparent)")

    outliers = []
    for name, key, fkey, limit in (
            ("opaque share", "opaque_pct", "FAMILY_OPAQUE_PCT", OUTLIER_OPAQUE_PTS),
            ("saturation", "saturation", "FAMILY_SATURATION", OUTLIER_COLOUR),
            ("lightness", "lightness", "FAMILY_LIGHTNESS", OUTLIER_COLOUR)):
        try:
            med = float(facts[fkey])
        except (KeyError, ValueError):
            continue
        if abs(m[key] - med) > limit:
            outliers.append(f"{name} {m[key]:.1f} is {abs(m[key] - med):.1f} away from the "
                            f"family median {med:g} (band {limit:g})")

    lum = m["lightness"]
    contrast = {"CONTRAST_LIGHT": "low" if abs(lum - 255) < CONTRAST_MIN else "ok",
                "CONTRAST_DARK": "low" if abs(lum - DARK_BG_LUM) < CONTRAST_MIN else "ok"}

    small = rgba.resize((32, 32), Image.LANCZOS)
    p32 = os.path.join(out_dir, "icon-32.png")
    pzoom = os.path.join(out_dir, "icon-32-x5.png")
    small.save(p32)
    small.resize((160, 160), Image.NEAREST).save(pzoom)
    sheet = _contact_sheet(Image, rgba, facts["FAMILY_SAMPLE"],
                           os.path.join(out_dir, "icon-contact-sheet.png"))

    out("ICON_GATE", "FAIL" if reasons else "PASS")
    out("PNG_PATH", src)
    out("PNG_SIZE", f"{img.width}x{img.height}")
    out("PNG_MODE", img.mode)
    for k, v in extra.items():
        out(k, v)
    out("ICON_STYLE", m["style"])
    out("ICON_OPAQUE_PCT", f"{m['opaque_pct']:.1f}")
    out("ICON_SATURATION", f"{m['saturation']:.1f}")
    out("ICON_LIGHTNESS", f"{m['lightness']:.1f}")
    out("COLORFUL_PCT", f"{m['colourful_pct']:.2f}")
    out("NONBLANK", 1 if m["nonblank"] else 0)
    out("CONSISTENCY", "outlier" if outliers else "ok")
    for r in outliers:
        out("CONSISTENCY_REASON", r)
    for k, v in contrast.items():
        out(k, v)
    out("PREVIEW_32", p32)
    out("PREVIEW_ZOOM", pzoom)
    out("CONTACT_SHEET", sheet)
    for r in reasons:
        out("FAIL_REASON", r)
    return 1 if reasons else 0


# ---------------------------------------------------------------------------
# sample
# ---------------------------------------------------------------------------
def cmd_sample(args):
    if not _pillow():
        return _cannot_verify(NO_PILLOW)
    status = 0
    for path in args.icons:
        try:
            _img, rgba = _open_rgba(path)
        except Exception as exc:
            out("FILE", path)
            out("ERROR", f"not a readable image ({type(exc).__name__})")
            status = 1
            continue
        m = _analyse(rgba)
        out("FILE", path)
        out("STYLE", m["style"])
        if m["plate"]:
            out("PLATE", m["plate"])
        out("GLYPH", m["glyph"] or "NONE")
        out("CORNER_RADIUS_PX", _corner_radius(rgba.load(), m["w"]))
        out("SIZE", f"{m['w']}x{m['h']}")
    return status


# ---------------------------------------------------------------------------
# observe
# ---------------------------------------------------------------------------
OBSERVER = os.path.join(os.path.dirname(HERE), "recorder", "icon_observe.mjs")


def cmd_observe(args):
    vr = _load("video_record")
    found = vr.problems()
    if not os.path.isfile(OBSERVER):
        found.append(("OBSERVER", "the icon observer script is missing"))
    if found:
        for key, text in found:
            print("ERROR=%s: %s" % (key, text))
        print("REMEDY=" + vr.REMEDY)
        return 2
    try:
        out_dir = args.out_dir or _default_out_dir()
    except Exception as exc:
        print(f"icon_gate: no output dir ({exc}); pass --out-dir", file=sys.stderr)
        return 3
    os.makedirs(out_dir, exist_ok=True)
    env = dict(os.environ)
    env["NODE_PATH"] = vr.node_modules()
    proc = subprocess.Popen(
        [vr.node_ok(), OBSERVER, "--base-url", args.base_url, "--ui-user", args.ui_user,
         "--module", args.module, "--out-dir", out_dir],
        env=env, stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="icon_gate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe").set_defaults(fn=cmd_probe)

    p = sub.add_parser("facts")
    p.add_argument("--core-addons", action="append", required=True)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_facts)

    p = sub.add_parser("render")
    p.add_argument("svg")
    p.add_argument("png")
    p.add_argument("--size", type=int)
    p.add_argument("--facts")
    p.add_argument("--rasterizer", default="auto")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("check")
    p.add_argument("icon")
    p.add_argument("--facts", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--rasterizer", default="auto")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("sample")
    p.add_argument("icons", nargs="+")
    p.set_defaults(fn=cmd_sample)

    p = sub.add_parser("observe")
    p.add_argument("--base-url", required=True)
    p.add_argument("--ui-user", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_observe)

    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code not in (0, None) else 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
