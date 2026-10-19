#!/usr/bin/env python3
"""icon_gate.py - rasterize and verify an Odoo module icon (static/description/icon.png).

Stdlib only; Pillow is needed for `check` and `sample` (without it the gate says
CANNOT-VERIFY, it never says PASS). Output is KEY=VALUE lines.

  probe
      RASTERIZERS=<csv, probe order, available ones only; chrome as chrome:<path>>
      PILLOW=1|0                                                       exit 0

  render <icon.svg> <out.png> [--size 256] [--rasterizer auto|<name>]
      RASTERIZER=<label>  PNG_PATH=<out.png>                           exit 0
      no rasterizer, or the chosen one failed                          exit 2
      Probe order: rsvg-convert, inkscape, chrome (headless), cairosvg, magick, convert.

  check <icon.png|icon.svg> --plate-hex '#RRGGBB' [--sample X,Y] [--size 256]
        [--delta-e 5.0] [--out-dir DIR] [--rasterizer auto|<name>]
      ICON_GATE=PASS|FAIL|CANNOT-VERIFY  PNG_PATH  PNG_SIZE  PNG_MODE  [RASTERIZER]
      PLATE_SAMPLE=#rrggbb@x,y  PLATE_ALPHA  PLATE_EXPECTED  PLATE_DELTA_E
      COLORFUL_PCT  NONBLANK=1|0  PREVIEW_32  PREVIEW_ZOOM  FAIL_REASON=<one per line>
      A greyscale mode, a plate colour off the expected one (CIEDE2000), a transparent plate
      pixel, a wrong size, or a blank image FAILs. A colourful icon needs >= 1% of its opaque
      pixels with chroma (max-min of RGB) above 8. Previews: icon-32.png (32 px, LANCZOS) and
      icon-32-x5.png (the 32 px icon enlarged 5x, nearest neighbour = what a 32 px render shows).
      --out-dir defaults to <ISOLATE dir>/icon-gate (scripts/lib/paths.py).
      Exit: 0 PASS, 1 FAIL, 2 CANNOT-VERIFY, 3 usage.

  sample <icon.png> [<icon.png> ...]
      For each sibling icon: PLATE=#rrggbb (dominant opaque colour of the border band),
      CORNER_RADIUS_PX=<n> (estimated from where the top edge turns opaque), SIZE=<WxH>.
      Lets a designer inherit the palette and corner radius of an existing icon family.
"""
import argparse
import base64
import importlib.util
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
GREY_MODES = {"L", "LA", "1", "I", "F"}
CHROMA_MIN = 8            # max-min of RGB above this counts as "has colour"
COLORFUL_MIN_PCT = 1.0    # of the opaque pixels
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


def cmd_render(args):
    label, reason = render(args.svg, args.png, args.size, args.rasterizer)
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
def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


def _default_out_dir():
    paths = _load("paths")
    return os.path.join(paths.isolate_dir(), "icon-gate")


def _cannot_verify(reason, **keys):
    out("ICON_GATE", "CANNOT-VERIFY")
    for k, v in keys.items():
        out(k, v)
    out("FAIL_REASON", reason)
    return 2


def cmd_check(args):
    cd = _load("color_delta")
    expected = cd.parse_color(args.plate_hex)
    if expected is None:
        print(f"icon_gate: --plate-hex {args.plate_hex!r} is not a colour", file=sys.stderr)
        return 3
    sample = None
    if args.sample:
        try:
            sx, sy = (int(v) for v in args.sample.split(","))
            sample = (sx, sy)
        except ValueError:
            print(f"icon_gate: --sample {args.sample!r} is not X,Y", file=sys.stderr)
            return 3
    try:
        out_dir = args.out_dir or _default_out_dir()
    except Exception as exc:
        print(f"icon_gate: no output dir ({exc}); pass --out-dir", file=sys.stderr)
        return 3
    os.makedirs(out_dir, exist_ok=True)

    src = args.icon
    extra = {}
    if src.lower().endswith(".svg"):
        png = os.path.join(out_dir, "icon.png")
        label, reason = render(src, png, args.size, args.rasterizer)
        if label is None:
            return _cannot_verify(reason)
        extra["RASTERIZER"] = label
        src = png
    if not _pillow():
        return _cannot_verify("Pillow is not installed, so the pixels cannot be read "
                              "(pip install pillow); this is not a pass")
    from PIL import Image

    reasons = []
    try:
        img = Image.open(src)
        img.load()
    except Exception as exc:
        out("ICON_GATE", "FAIL")
        out("PNG_PATH", src)
        out("FAIL_REASON", f"not a readable image ({type(exc).__name__})")
        return 1
    mode = img.mode
    out_keys = [("PNG_PATH", src), ("PNG_SIZE", f"{img.width}x{img.height}"), ("PNG_MODE", mode)]
    if img.format != "PNG":
        reasons.append(f"file is {img.format}, not PNG")
    if (img.width, img.height) != (args.size, args.size):
        reasons.append(f"size is {img.width}x{img.height}, expected {args.size}x{args.size}")
    if mode in GREY_MODES:
        reasons.append(f"mode {mode} is greyscale/indexed-grey; save as RGBA colour")
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    opaque = colourful = 0
    colours = set()
    covered = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            colours.add((r, g, b, a))
            if a > 0:
                covered = True
            if a == 255:
                opaque += 1
                if max(r, g, b) - min(r, g, b) > CHROMA_MIN:
                    colourful += 1
    pct = (100.0 * colourful / opaque) if opaque else 0.0
    nonblank = len(colours) > 1 and covered
    expected_has_chroma = max(expected) - min(expected) > CHROMA_MIN
    if expected_has_chroma and pct < COLORFUL_MIN_PCT:
        reasons.append(f"only {pct:.2f}% of the opaque pixels carry colour (need >= "
                       f"{COLORFUL_MIN_PCT:g}%): the icon is grey, not colourful")
    if not nonblank:
        reasons.append("the icon is blank (a single colour or fully transparent)")

    sx, sy = sample if sample else (args.size // 2, args.size // 8)
    plate_lines = []
    if 0 <= sx < w and 0 <= sy < h:
        r, g, b, a = px[sx, sy]
        de = cd.delta_e(_hex(expected), _hex((r, g, b)))
        plate_lines = [("PLATE_SAMPLE", f"{_hex((r, g, b))}@{sx},{sy}"), ("PLATE_ALPHA", a),
                       ("PLATE_EXPECTED", _hex(expected)), ("PLATE_DELTA_E", f"{de:.2f}")]
        if a != 255:
            reasons.append(f"plate pixel at {sx},{sy} has alpha {a}, expected 255 (opaque)")
        elif de > args.delta_e:
            reasons.append(f"plate colour {_hex((r, g, b))} at {sx},{sy} is dE {de:.2f} from "
                           f"{_hex(expected)} (limit {args.delta_e:g})")
    else:
        reasons.append(f"sample point {sx},{sy} is outside the {w}x{h} image")

    small = rgba.resize((32, 32), Image.LANCZOS)
    p32 = os.path.join(out_dir, "icon-32.png")
    pzoom = os.path.join(out_dir, "icon-32-x5.png")
    small.save(p32)
    small.resize((160, 160), Image.NEAREST).save(pzoom)

    out("ICON_GATE", "FAIL" if reasons else "PASS")
    for k, v in out_keys:
        out(k, v)
    for k, v in extra.items():
        out(k, v)
    for k, v in plate_lines:
        out(k, v)
    out("COLORFUL_PCT", f"{pct:.2f}")
    out("NONBLANK", 1 if nonblank else 0)
    out("PREVIEW_32", p32)
    out("PREVIEW_ZOOM", pzoom)
    for r in reasons:
        out("FAIL_REASON", r)
    return 1 if reasons else 0


# ---------------------------------------------------------------------------
# sample
# ---------------------------------------------------------------------------
def _corner_radius(px, w):
    """Radius of the rounded corner, from where the top row turns opaque.

    The top row's pixel centres sit half a pixel inside the arc's tangent line, so the first
    opaque x is r - sqrt(r) short of the radius; solve that back to r."""
    x0 = next((x for x in range(w) if px[x, 0][3] >= 128), None)
    if x0 is None:
        return 0
    if x0 == 0:
        return 0
    return round(((1 + (1 + 4 * x0) ** 0.5) / 2) ** 2)


def cmd_sample(args):
    if not _pillow():
        return _cannot_verify("Pillow is not installed, so the pixels cannot be read "
                              "(pip install pillow); this is not a pass")
    from PIL import Image
    status = 0
    for path in args.icons:
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            out("FILE", path)
            out("ERROR", f"not a readable image ({type(exc).__name__})")
            status = 1
            continue
        w, h = img.size
        px = img.load()
        band = max(2, w // 16)
        counts = {}
        for y in range(h):
            for x in range(w):
                if min(x, y, w - 1 - x, h - 1 - y) >= band:
                    continue
                r, g, b, a = px[x, y]
                if a == 255:
                    counts[(r, g, b)] = counts.get((r, g, b), 0) + 1
        out("FILE", path)
        if counts:
            out("PLATE", _hex(max(counts, key=counts.get)))
        else:
            out("PLATE", "NONE")
        out("CORNER_RADIUS_PX", _corner_radius(px, w))
        out("SIZE", f"{w}x{h}")
    return status


def main(argv=None):
    ap = argparse.ArgumentParser(prog="icon_gate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe").set_defaults(fn=cmd_probe)

    p = sub.add_parser("render")
    p.add_argument("svg")
    p.add_argument("png")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--rasterizer", default="auto")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("check")
    p.add_argument("icon")
    p.add_argument("--plate-hex", required=True)
    p.add_argument("--sample")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--delta-e", type=float, default=5.0)
    p.add_argument("--out-dir")
    p.add_argument("--rasterizer", default="auto")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("sample")
    p.add_argument("icons", nargs="+")
    p.set_defaults(fn=cmd_sample)

    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code not in (0, None) else 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
