"""Behavioural guard for scripts/lib/icon_gate.py - the pixel gate for a module icon.

An icon that "looks fine" in the SVG can still ship as a grey PNG, a blank square, a plate
with a transparent hole, or a 128 px file; the gate reads the PIXELS and says so. The costly
failure is the gate reporting PASS when it could not look, so the cannot-verify cases are
pinned as hard as the failures.

Rasterizers are stubbed through PATH (no real rsvg/inkscape/chrome is needed); Pillow-backed
cases skip when Pillow is absent.

Run with: python3 -m pytest tests/test_icon_gate.py -v
"""
import base64
import os
import stat
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "icon_gate.py"

PLATE = (0, 187, 206)  # an arbitrary colourful plate
PLATE_HEX = "#00BBCE"


def _run(*args, env=None, python_args=(), cwd=None):
    full_env = dict(os.environ)
    full_env.pop("ODOO_AI_WORKTREE_DIR", None)
    full_env.update(env or {})
    res = subprocess.run(
        [sys.executable, *python_args, str(GATE), *map(str, args)],
        capture_output=True, text=True, env=full_env, cwd=cwd, timeout=120,
    )
    kv = {}
    multi = []
    for ln in res.stdout.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            kv[k] = v
            if k == "FAIL_REASON":
                multi.append(v)
    kv["_reasons"] = multi
    return res, kv


def _tiny_png(path: Path, size=4) -> Path:
    """A valid PNG without Pillow (for rasterizer stubs to copy into place)."""
    raw = b"".join(b"\x00" + b"\x00\xbb\xce\xff" * size for _ in range(size))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


STUB = """#!/bin/sh
out=""
for a in "$@"; do
  case "$a" in
    --export-filename=*|--screenshot=*) out="${a#*=}" ;;
  esac
  last="$a"
done
[ -n "$out" ] || out="$last"
printf '%s\\n' "$0" "$@" > "$STUB_LOG.${0##*/}"
if [ -n "$STUB_FAIL" ] && [ "${0##*/}" = "$STUB_FAIL" ]; then exit 1; fi
/bin/cp "$STUB_PNG" "$out"
"""


@pytest.fixture
def stubs(tmp_path):
    """A PATH holding only the stub rasterizers a test installs."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    png = _tiny_png(tmp_path / "stub.png")
    svg = tmp_path / "icon.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"/>\n',
                   encoding="utf-8")

    class S:
        env = {"PATH": str(bindir), "STUB_PNG": str(png), "STUB_LOG": str(tmp_path / "log")}
        dir = bindir
        svg_path = svg
        out = tmp_path / "out" / "icon.png"

        @staticmethod
        def add(*names):
            for n in names:
                f = bindir / n
                f.write_text(STUB, encoding="utf-8")
                f.chmod(f.stat().st_mode | stat.S_IEXEC)

        @staticmethod
        def argv(name):
            return (tmp_path / f"log.{name}").read_text(encoding="utf-8").splitlines()

        @staticmethod
        def called(name):
            return (tmp_path / f"log.{name}").exists()

    return S


# ---------------------------------------------------------------------------
# rasterizers (stdlib only)
# ---------------------------------------------------------------------------
def test_probe_lists_the_available_rasterizers_in_probe_order(stubs):
    stubs.add("convert", "rsvg-convert", "google-chrome-stable", "inkscape")
    res, kv = _run("probe", env=stubs.env, python_args=["-S"])
    assert res.returncode == 0
    assert kv["RASTERIZERS"].split(",") == [
        "rsvg-convert", "inkscape", f"chrome:{stubs.dir}/google-chrome-stable", "convert"
    ]
    assert kv["PILLOW"] == "0"  # -S hides every site package


def test_render_uses_the_first_available_rasterizer_in_probe_order(stubs):
    stubs.add("magick", "inkscape")
    res, kv = _run("render", stubs.svg_path, stubs.out, env=stubs.env, python_args=["-S"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["RASTERIZER"] == "inkscape" and kv["PNG_PATH"] == str(stubs.out)
    assert stubs.out.is_file()
    assert not stubs.called("magick")
    assert "--export-width=256" in stubs.argv("inkscape")


def test_render_falls_through_to_the_next_rasterizer_when_one_fails(stubs):
    stubs.add("rsvg-convert", "convert")
    env = dict(stubs.env, STUB_FAIL="rsvg-convert")
    res, kv = _run("render", stubs.svg_path, stubs.out, "--size", "128", env=env,
                   python_args=["-S"])
    assert res.returncode == 0 and kv["RASTERIZER"] == "convert"
    assert "128x128" in stubs.argv("convert")


def test_chrome_is_driven_headless_with_a_transparent_background_and_no_temp_file(stubs):
    stubs.add("chromium")
    res, kv = _run("render", stubs.svg_path, stubs.out, env=stubs.env, python_args=["-S"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["RASTERIZER"].startswith("chrome:")
    argv = stubs.argv("chromium")
    for flag in ("--headless=new", "--default-background-color=00000000",
                 "--window-size=256,256", "--force-device-scale-factor=1",
                 f"--screenshot={stubs.out}"):
        assert flag in argv, f"{flag} missing from {argv}"
    url = argv[-1]
    assert url.startswith("data:text/html;base64,"), "the page must travel as a data: URL"
    html = base64.b64decode(url.split(",", 1)[1]).decode()
    assert "data:image/svg+xml;base64," in html and 'width=256' in html
    assert sorted(p.name for p in stubs.out.parent.iterdir()) == ["icon.png"], (
        "no temp file may be left beside the output"
    )


def test_no_rasterizer_is_cannot_verify_naming_the_install_options(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    svg = tmp_path / "i.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    res, kv = _run("render", svg, tmp_path / "o.png", env={"PATH": str(empty)},
                   python_args=["-S"])
    assert res.returncode == 2
    assert kv["RENDER"] == "CANNOT-VERIFY"
    for hint in ("rsvg-convert", "inkscape", "chrome", "cairosvg", "ImageMagick"):
        assert hint in kv["REASON"]
    assert not (tmp_path / "o.png").exists()


def test_without_pillow_the_gate_is_cannot_verify_never_a_pass(tmp_path):
    png = _tiny_png(tmp_path / "icon.png")
    res, kv = _run("check", png, "--plate-hex", PLATE_HEX, "--size", "4",
                   "--out-dir", tmp_path / "o", python_args=["-S"])
    assert res.returncode == 2
    assert kv["ICON_GATE"] == "CANNOT-VERIFY"
    assert any("Pillow" in r for r in kv["_reasons"])


def test_usage_errors_exit_three(tmp_path):
    res, _ = _run("check", tmp_path / "x.png", "--plate-hex", "not-a-colour",
                  "--out-dir", tmp_path)
    assert res.returncode == 3
    res, _ = _run("bogus")
    assert res.returncode == 3


# ---------------------------------------------------------------------------
# pixel checks (Pillow)
# ---------------------------------------------------------------------------
@pytest.fixture
def pil():
    return pytest.importorskip("PIL.Image")


def _icon(Image, path, *, size=256, plate=PLATE, mode="RGBA", glyph=(255, 255, 255)):
    """A plate-coloured square with a glyph rectangle so the icon is not a flat fill."""
    img = Image.new("RGBA", (size, size), plate + (255,))
    for y in range(size // 3, 2 * size // 3):
        for x in range(size // 3, 2 * size // 3):
            img.putpixel((x, y), glyph + (255,))
    img.convert(mode).save(path, "PNG")
    return path


def _check(png, tmp_path, *extra, plate=PLATE_HEX):
    return _run("check", png, "--plate-hex", plate, "--out-dir", tmp_path / "gate", *extra)


def test_a_good_icon_passes_with_previews(pil, tmp_path):
    res, kv = _check(_icon(pil, tmp_path / "i.png"), tmp_path)
    assert res.returncode == 0, res.stdout
    assert kv["ICON_GATE"] == "PASS" and kv["_reasons"] == []
    assert kv["PNG_SIZE"] == "256x256" and kv["PNG_MODE"] == "RGBA" and kv["NONBLANK"] == "1"
    assert kv["PLATE_SAMPLE"] == "#00bbce@128,32" and kv["PLATE_ALPHA"] == "255"


def test_a_greyscale_png_fails_even_at_the_right_size(pil, tmp_path):
    img = pil.new("L", (256, 256), 120)
    img.putpixel((10, 10), 30)
    p = tmp_path / "g.png"
    img.save(p)
    res, kv = _check(p, tmp_path)
    assert res.returncode == 1 and kv["ICON_GATE"] == "FAIL"
    assert kv["PNG_MODE"] == "L"
    assert any("greyscale" in r for r in kv["_reasons"])


def test_an_rgb_png_whose_pixels_are_all_grey_fails(pil, tmp_path):
    p = _icon(pil, tmp_path / "grey.png", plate=(120, 120, 120), glyph=(200, 200, 200))
    res, kv = _check(p, tmp_path)
    assert res.returncode == 1
    assert kv["PNG_MODE"] == "RGBA" and float(kv["COLORFUL_PCT"]) < 1
    assert any("not colourful" in r for r in kv["_reasons"])


def test_a_plate_colour_outside_the_threshold_fails_and_inside_passes(pil, tmp_path):
    p = _icon(pil, tmp_path / "i.png", plate=(127, 66, 130))     # a purple plate
    res, kv = _check(p, tmp_path)
    assert res.returncode == 1 and float(kv["PLATE_DELTA_E"]) > 5
    assert any("is dE" in r for r in kv["_reasons"])

    near = _icon(pil, tmp_path / "near.png", plate=(0, 187, 210))
    res, kv = _check(near, tmp_path)
    assert res.returncode == 0 and float(kv["PLATE_DELTA_E"]) <= 5
    res, _ = _check(near, tmp_path, "--delta-e", "0.01")
    assert res.returncode == 1, "the threshold is the caller's to tighten"


def test_a_transparent_plate_at_the_sample_point_fails(pil, tmp_path):
    img = pil.open(_icon(pil, tmp_path / "i.png"))
    img.putpixel((128, 32), PLATE + (0,))
    img.save(tmp_path / "hole.png")
    res, kv = _check(tmp_path / "hole.png", tmp_path)
    assert res.returncode == 1 and kv["PLATE_ALPHA"] == "0"
    assert any("alpha 0" in r for r in kv["_reasons"])


def test_a_blank_png_fails(pil, tmp_path):
    pil.new("RGBA", (256, 256), PLATE + (255,)).save(tmp_path / "flat.png")
    res, kv = _check(tmp_path / "flat.png", tmp_path)
    assert res.returncode == 1 and kv["NONBLANK"] == "0"
    assert any("blank" in r for r in kv["_reasons"])
    pil.new("RGBA", (256, 256), (0, 0, 0, 0)).save(tmp_path / "void.png")
    assert _check(tmp_path / "void.png", tmp_path)[1]["NONBLANK"] == "0"


def test_a_wrong_size_fails(pil, tmp_path):
    p = _icon(pil, tmp_path / "small.png", size=128)
    res, kv = _check(p, tmp_path)
    assert res.returncode == 1 and kv["PNG_SIZE"] == "128x128"
    assert any("expected 256x256" in r for r in kv["_reasons"])
    res, kv = _check(p, tmp_path, "--size", "128")
    assert res.returncode == 0, "the expected size is the caller's to declare"


def test_a_custom_sample_point_is_the_pixel_that_is_judged(pil, tmp_path):
    img = pil.open(_icon(pil, tmp_path / "i.png"))
    img.putpixel((5, 5), (255, 0, 0, 255))
    img.save(tmp_path / "red.png")
    res, kv = _check(tmp_path / "red.png", tmp_path, "--sample", "5,5")
    assert res.returncode == 1 and kv["PLATE_SAMPLE"] == "#ff0000@5,5"


def test_previews_are_32px_and_a_nearest_neighbour_x5_zoom(pil, tmp_path):
    res, kv = _check(_icon(pil, tmp_path / "i.png"), tmp_path)
    small = pil.open(kv["PREVIEW_32"])
    zoom = pil.open(kv["PREVIEW_ZOOM"]).convert("RGBA")
    assert small.size == (32, 32) and zoom.size == (160, 160)
    assert kv["PREVIEW_32"].endswith("icon-32.png") and kv["PREVIEW_ZOOM"].endswith("icon-32-x5.png")
    zp, sp = zoom.load(), small.convert("RGBA").load()
    for by in range(32):
        for bx in range(32):
            block = {zp[bx * 5 + dx, by * 5 + dy] for dx in range(5) for dy in range(5)}
            assert block == {sp[bx, by]}, f"block {bx},{by} is not a uniform 5x5 enlargement"


def test_default_previews_land_under_the_state_root(pil, tmp_path):
    iso = tmp_path / "isolate"
    res, kv = _run("check", _icon(pil, tmp_path / "i.png"), "--plate-hex", PLATE_HEX,
                   env={"ODOO_AI_WORKTREE_DIR": str(iso)})
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["PREVIEW_32"] == str(iso / "icon-gate" / "icon-32.png")
    assert Path(kv["PREVIEW_ZOOM"]).is_file()


def test_an_svg_is_rasterized_then_judged(pil, stubs, tmp_path):
    big = _icon(pil, tmp_path / "rendered.png")
    stubs.add("rsvg-convert")
    env = dict(stubs.env, STUB_PNG=str(big))
    res, kv = _run("check", stubs.svg_path, "--plate-hex", PLATE_HEX, "--out-dir",
                   tmp_path / "gate", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["RASTERIZER"] == "rsvg-convert"
    assert kv["PNG_PATH"] == str(tmp_path / "gate" / "icon.png")


def test_sample_reports_the_plate_colour_and_corner_radius_of_a_synthetic_icon(pil, tmp_path):
    from PIL import ImageDraw

    img = pil.new("RGBA", (256, 256), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, 255, 255], radius=40, fill=PLATE + (255,))
    for y in range(100, 160):
        for x in range(100, 160):
            img.putpixel((x, y), (255, 255, 255, 255))
    p = tmp_path / "family.png"
    img.save(p)
    res, kv = _run("sample", p)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["PLATE"] == PLATE_HEX.lower()
    assert abs(int(kv["CORNER_RADIUS_PX"]) - 40) <= 2
    assert kv["SIZE"] == "256x256"
