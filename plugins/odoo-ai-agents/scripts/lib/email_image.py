#!/usr/bin/env python3
"""email_image.py - render an email address as a PNG so a public page can show it without
publishing crawlable text.

Usage:
    python3 email_image.py --address <addr> --out <file.png> [--font <ttf>] [--size 22]
                           [--color 333333] [--background ffffff]

The image is drawn by Pillow when it is importable, else by ffmpeg's drawtext filter (an ffmpeg
built with libfreetype); a machine with neither prints the remedy and exits 2. The font comes from
--font, else the author profile's `font_file`, else `fc-match` on this machine. The address is passed to ffmpeg as a text file,
never on the command line, so it reaches no process list or log. Output: the PNG path, its pixel
width and height, and the alt text to use ("contact address" - never the address itself).
Exit: 0 written, 1 refused (not an address), 2 missing tool or font.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _font_from_profile():
    try:
        import author_profile_config as apc
        profile = apc.read_profile(apc.profile_path())
        font = profile.get("font_file")
        return font if font and os.path.isfile(font) else None
    except Exception:  # noqa: BLE001 - a missing or invalid profile is simply "no font given"
        return None


def _font_from_fc_match():
    if not shutil.which("fc-match"):
        return None
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans-serif"], capture_output=True,
                             text=True, timeout=10, check=False).stdout.strip()
    except OSError:
        return None
    return out if out and os.path.isfile(out) else None


def _escape_drawtext(value):
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(address, out, font=None, size=22, color="333333", background="ffffff"):
    if not _EMAIL.match(address):
        print("x not an email address: %r" % address, file=sys.stderr)
        return 1
    font = font or _font_from_profile() or _font_from_fc_match()
    if not font:
        print("x no font found - pass --font <ttf with Latin Extended coverage> or record "
              "font_file in the author profile", file=sys.stderr)
        return 2
    width = int(len(address) * size * 0.62) + 2 * size
    height = int(size * 2)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    code = _render_pillow(address, out, font, size, color, background, width, height)
    if code is None:
        code = _render_ffmpeg(address, out, font, size, color, background, width, height)
    if code is None:
        print("x no renderer: install Pillow for the plugin python3 (pip install pillow) or an "
              "ffmpeg built with the drawtext filter (libfreetype)", file=sys.stderr)
        return 2
    if code:
        return code
    print("PNG=%s" % out)
    print("WIDTH=%d" % width)
    print("HEIGHT=%d" % height)
    print("ALT=contact address")
    return 0


def _render_pillow(address, out, font, size, color, background, width, height):
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: WPS433 - optional dependency
    except ImportError:
        return None
    try:
        face = ImageFont.truetype(font, size)
    except OSError:
        print("x the font %s cannot be opened by Pillow" % font, file=sys.stderr)
        return 2
    image = Image.new("RGB", (width, height), "#" + background)
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), address, font=face)
    draw.text((size, (height - (box[3] - box[1])) / 2 - box[1]), address, font=face,
              fill="#" + color)
    image.save(out, "PNG")
    return 0


def _render_ffmpeg(address, out, font, size, color, background, width, height):
    if not shutil.which("ffmpeg"):
        return None
    try:
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                                 text=True, timeout=20, check=False).stdout
    except OSError:
        return None
    if " drawtext " not in filters:
        return None
    textfile = out + ".txt"  # beside the output, never in a shared temp dir
    with open(textfile, "w", encoding="utf-8") as fh:
        fh.write(address)
    try:
        vf = ("drawtext=fontfile=%s:textfile=%s:fontsize=%d:fontcolor=0x%s:x=%d:y=(h-text_h)/2"
              % (_escape_drawtext(font), _escape_drawtext(textfile), size, color, size))
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
               "-i", "color=c=0x%s:s=%dx%d:d=1" % (background, width, height),
               "-vf", vf, "-frames:v", "1", out]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    finally:
        os.unlink(textfile)
    if proc.returncode != 0 or not os.path.isfile(out):
        print("x ffmpeg could not render the image (see its stderr)", file=sys.stderr)
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--address", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--font")
    parser.add_argument("--size", type=int, default=22)
    parser.add_argument("--color", default="333333")
    parser.add_argument("--background", default="ffffff")
    args = parser.parse_args(argv)
    return render(args.address, args.out, args.font, args.size, args.color, args.background)


if __name__ == "__main__":
    sys.exit(main())
