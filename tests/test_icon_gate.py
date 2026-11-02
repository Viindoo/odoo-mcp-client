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
import functools
import http.server
import os
import stat
import struct
import subprocess
import sys
import threading
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "icon_gate.py"


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


def _facts_file(tmp_path, **over):
    """A hand-written facts file, for the cases that must not depend on measuring."""
    keys = {"NATIVE_SIZE": "140x140", "NATIVE_MODE": "RGBA", "NATIVE_STYLE": "tile",
            "NATIVE_FORMAT": "png", "CORNER_ALPHA": "transparent", "SAMPLE_COUNT": "1"}
    keys.update(over)
    path = tmp_path / "facts.txt"
    path.write_text("".join(f"{k}={v}\n" for k, v in keys.items()), encoding="utf-8")
    return path


def test_without_pillow_the_gate_is_cannot_verify_never_a_pass(tmp_path):
    png = _tiny_png(tmp_path / "icon.png")
    res, kv = _run("check", png, "--facts", _facts_file(tmp_path, NATIVE_SIZE="4x4"),
                   "--out-dir", tmp_path / "o", python_args=["-S"])
    assert res.returncode == 2
    assert kv["ICON_GATE"] == "CANNOT-VERIFY"
    assert any("Pillow" in r for r in kv["_reasons"])


def test_usage_errors_exit_three(tmp_path):
    res, _ = _run("check", tmp_path / "x.png", "--facts", tmp_path / "missing.txt",
                  "--out-dir", tmp_path)
    assert res.returncode == 3
    res, _ = _run("check", tmp_path / "x.png", "--facts", _facts_file(tmp_path),
                  "--plate-hex", "#00BBCE", "--out-dir", tmp_path)
    assert res.returncode == 3, "the fixed plate colour is gone: the family is measured"
    res, _ = _run("bogus")
    assert res.returncode == 3


def test_facts_without_pillow_reports_only_the_headers_and_is_cannot_verify(tmp_path):
    addons = tmp_path / "addons"
    (addons / "sale" / "static" / "description").mkdir(parents=True)
    _tiny_png(addons / "sale" / "static" / "description" / "icon.png", size=7)
    res, kv = _run("facts", "--core-addons", addons, python_args=["-S"])
    assert res.returncode == 2
    assert kv["NATIVE_SIZE"] == "7x7" and kv["NATIVE_MODE"] == "RGBA"
    assert kv["NATIVE_STYLE"] == "unknown"


def test_check_against_facts_that_state_no_family_is_cannot_verify(tmp_path):
    png = _tiny_png(tmp_path / "icon.png")
    facts = tmp_path / "facts.txt"
    facts.write_text("NATIVE_STYLE=unknown\nSAMPLE_COUNT=0\n", encoding="utf-8")
    res, kv = _run("check", png, "--facts", facts, "--out-dir", tmp_path / "o")
    assert res.returncode == 2 and kv["ICON_GATE"] == "CANNOT-VERIFY"


def test_render_takes_its_size_from_the_facts_unless_one_is_given(stubs, tmp_path):
    stubs.add("rsvg-convert")
    facts = _facts_file(tmp_path, NATIVE_SIZE="100x100")
    res, kv = _run("render", stubs.svg_path, stubs.out, "--facts", facts, env=stubs.env,
                   python_args=["-S"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert stubs.argv("rsvg-convert")[:5] == [stubs.argv("rsvg-convert")[0], "-w", "100", "-h", "100"]
    res, kv = _run("render", stubs.svg_path, stubs.out, "--facts", facts, "--size", "64",
                   env=stubs.env, python_args=["-S"])
    assert "64" in stubs.argv("rsvg-convert") and "100" not in stubs.argv("rsvg-convert")


# ---------------------------------------------------------------------------
# pixel checks (Pillow)
# ---------------------------------------------------------------------------
@pytest.fixture
def pil():
    return pytest.importorskip("PIL.Image")


TILE_HUES = [(0, 187, 206), (127, 66, 130), (220, 90, 40), (60, 160, 80), (200, 60, 120),
             (240, 180, 20), (70, 90, 200), (30, 150, 140), (180, 80, 200), (230, 120, 60)]
GLYPH_HUES = [(230, 60, 60), (40, 120, 230), (250, 170, 0), (60, 190, 90), (150, 60, 200),
              (0, 190, 200), (240, 100, 160), (90, 90, 230), (200, 120, 20), (20, 160, 120)]


def _tile(Image, path, *, size=140, plate=(0, 187, 206), mode="RGBA", radius=28):
    """A coloured rounded plate with transparent corners and a white glyph."""
    from PIL import ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=plate + (255,))
    d.rectangle([size // 3, size // 3, 2 * size // 3, 2 * size // 3], fill=(255, 255, 255, 255))
    img.convert(mode).save(path, "PNG")
    return path


def _flat(Image, path, *, size=100, glyph=(230, 60, 60), mode="RGBA"):
    """A glyph on a transparent surround, no plate."""
    from PIL import ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([size // 4, size // 4, 3 * size // 4, 3 * size // 4], fill=glyph + (255,))
    d.rectangle([size // 2 - 4, size // 2 - 4, size // 2 + 4, size // 2 + 4], fill=(40, 40, 40, 255))
    img.convert(mode).save(path, "PNG")
    return path


def _addons(root, Image, make, hues, *, folder="addons", **kw):
    for i, hue in enumerate(hues):
        d = root / folder / f"mod{folder.replace('/', '_')}{i}" / "static" / "description"
        d.mkdir(parents=True)
        make(Image, d / "icon.png", **({"plate": hue} if make is _tile else {"glyph": hue}), **kw)
    return root / folder


@pytest.fixture
def tile_facts(pil, tmp_path):
    addons = _addons(tmp_path / "tiles", pil, _tile, TILE_HUES)
    facts = tmp_path / "tile-facts.txt"
    res, kv = _run("facts", "--core-addons", addons, "--out", facts)
    assert res.returncode == 0, res.stdout + res.stderr
    return facts


@pytest.fixture
def flat_facts(pil, tmp_path):
    addons = _addons(tmp_path / "flats", pil, _flat, GLYPH_HUES)
    facts = tmp_path / "flat-facts.txt"
    res, kv = _run("facts", "--core-addons", addons, "--out", facts)
    assert res.returncode == 0, res.stdout + res.stderr
    return facts


def _check(png, facts, tmp_path):
    return _run("check", png, "--facts", facts, "--out-dir", tmp_path / "gate")


def test_facts_measures_a_tile_family(pil, tmp_path):
    addons = _addons(tmp_path / "t", pil, _tile, TILE_HUES)
    out_file = tmp_path / "facts.txt"
    res, kv = _run("facts", "--core-addons", addons, "--out", out_file)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["NATIVE_SIZE"] == "140x140" and kv["NATIVE_MODE"] == "RGBA"
    assert kv["NATIVE_STYLE"] == "tile" and kv["NATIVE_FORMAT"] == "png"
    assert kv["CORNER_ALPHA"] == "transparent" and kv["SAMPLE_COUNT"] == "10"
    assert abs(float(kv["FAMILY_RADIUS_PX"]) - 28) <= 2
    assert 0 < float(kv["FAMILY_OPAQUE_PCT"]) <= 100
    assert float(kv["FAMILY_SATURATION"]) > 8 and 0 < float(kv["FAMILY_LIGHTNESS"]) < 255
    assert res.stdout.count("FAMILY_SAMPLE=") == 10
    assert out_file.read_text(encoding="utf-8") == res.stdout, "--out holds the same lines"


def test_facts_measures_a_flat_family_and_reads_several_directories(pil, tmp_path):
    a = _addons(tmp_path / "x", pil, _flat, GLYPH_HUES[:4], folder="addons")
    b = _addons(tmp_path / "x", pil, _flat, GLYPH_HUES[4:7], folder="odoo/addons")
    svg = a / next(a.iterdir()).name / "static" / "description" / "icon.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    res, kv = _run("facts", "--core-addons", a, "--core-addons", b)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["NATIVE_SIZE"] == "100x100" and kv["NATIVE_STYLE"] == "flat"
    assert kv["CORNER_ALPHA"] == "transparent" and kv["SAMPLE_COUNT"] == "7"
    assert kv["NATIVE_FORMAT"] == "both"
    assert "FAMILY_RADIUS_PX" not in kv, "the radius is a tile statistic"


def test_facts_reports_a_palette_family_as_palette(pil, tmp_path):
    root = tmp_path / "pal"
    for i, hue in enumerate(TILE_HUES[:4]):
        d = root / f"m{i}" / "static" / "description"
        d.mkdir(parents=True)
        pil.new("RGBA", (80, 80), hue + (255,)).convert("P").save(d / "icon.png")
    res, kv = _run("facts", "--core-addons", root)
    assert kv["NATIVE_MODE"] == "P" and kv["NATIVE_SIZE"] == "80x80"
    assert kv["CORNER_ALPHA"] == "opaque"


def test_facts_with_no_icon_says_unknown_and_exits_four(tmp_path):
    (tmp_path / "empty" / "m" / "static" / "description").mkdir(parents=True)
    out_file = tmp_path / "facts.txt"
    res, kv = _run("facts", "--core-addons", tmp_path / "empty", "--out", out_file)
    assert res.returncode == 4
    assert kv["NATIVE_STYLE"] == "unknown" and kv["SAMPLE_COUNT"] == "0"
    assert "NATIVE_SIZE" not in kv, "nothing is guessed"
    assert "NATIVE_STYLE=unknown" in out_file.read_text(encoding="utf-8")


def test_a_matching_tile_icon_passes_with_previews(pil, tile_facts, tmp_path):
    res, kv = _check(_tile(pil, tmp_path / "i.png"), tile_facts, tmp_path)
    assert res.returncode == 0, res.stdout
    assert kv["ICON_GATE"] == "PASS" and kv["_reasons"] == []
    assert kv["PNG_SIZE"] == "140x140" and kv["PNG_MODE"] == "RGBA"
    assert kv["ICON_STYLE"] == "tile" and kv["NONBLANK"] == "1"
    assert Path(kv["PREVIEW_32"]).is_file() and Path(kv["PREVIEW_ZOOM"]).is_file()


def test_a_matching_flat_icon_passes(pil, flat_facts, tmp_path):
    res, kv = _check(_flat(pil, tmp_path / "i.png", glyph=(60, 190, 90)), flat_facts, tmp_path)
    assert res.returncode == 0, res.stdout
    assert kv["ICON_GATE"] == "PASS" and kv["ICON_STYLE"] == "flat"


def test_a_wrong_size_fails_naming_the_native_size(pil, tile_facts, tmp_path):
    res, kv = _check(_tile(pil, tmp_path / "s.png", size=128), tile_facts, tmp_path)
    assert res.returncode == 1 and kv["PNG_SIZE"] == "128x128"
    assert any("expected 140x140" in r for r in kv["_reasons"])


def test_a_non_rgba_mode_fails_even_for_a_palette_family(pil, tmp_path):
    root = tmp_path / "pal"
    for i, hue in enumerate(GLYPH_HUES[:4]):
        d = root / f"m{i}" / "static" / "description"
        d.mkdir(parents=True)
        _flat(pil, d / "icon.png", glyph=hue, mode="P")
    facts = tmp_path / "pal-facts.txt"
    res, kv = _run("facts", "--core-addons", root, "--out", facts)
    assert kv["NATIVE_MODE"] == "P"
    res, kv = _check(_flat(pil, tmp_path / "p.png", mode="P"), facts, tmp_path)
    assert res.returncode == 1 and kv["PNG_MODE"] == "P"
    assert any("expected RGBA" in r for r in kv["_reasons"])
    res, kv = _check(_flat(pil, tmp_path / "ok.png"), facts, tmp_path)
    assert res.returncode == 0, res.stdout


def test_an_opaque_corner_fails_when_the_family_corners_are_transparent(pil, tile_facts, tmp_path):
    img = pil.open(_tile(pil, tmp_path / "i.png"))
    img.putpixel((0, 0), (0, 187, 206, 255))
    img.save(tmp_path / "corner.png")
    res, kv = _check(tmp_path / "corner.png", tile_facts, tmp_path)
    assert res.returncode == 1
    assert any("corner" in r for r in kv["_reasons"])


def test_a_flat_family_refuses_a_plate_and_a_tile_family_refuses_a_bare_glyph(
        pil, tile_facts, flat_facts, tmp_path):
    res, kv = _check(_tile(pil, tmp_path / "t.png", size=100), flat_facts, tmp_path)
    assert res.returncode == 1 and kv["ICON_STYLE"] == "tile"
    assert any("style mismatch" in r and "plate" in r for r in kv["_reasons"])
    res, kv = _check(_flat(pil, tmp_path / "f.png", size=140), tile_facts, tmp_path)
    assert res.returncode == 1 and kv["ICON_STYLE"] == "flat"
    assert any("style mismatch" in r and "no large opaque plate" in r for r in kv["_reasons"])


def test_a_grey_png_fails_the_colour_rule(pil, flat_facts, tmp_path):
    p = _flat(pil, tmp_path / "grey.png", glyph=(120, 120, 120))
    img = pil.open(p)
    for x in range(40, 60):
        img.putpixel((x, 50), (118, 120, 122, 255))
    img.save(p)
    res, kv = _check(p, flat_facts, tmp_path)
    assert res.returncode == 1 and float(kv["COLORFUL_PCT"]) < 1
    assert any("not colourful" in r for r in kv["_reasons"])


def test_a_blank_png_fails(pil, flat_facts, tmp_path):
    pil.new("RGBA", (100, 100), (0, 0, 0, 0)).save(tmp_path / "void.png")
    res, kv = _check(tmp_path / "void.png", flat_facts, tmp_path)
    assert res.returncode == 1 and kv["NONBLANK"] == "0"
    assert any("blank" in r for r in kv["_reasons"])


def test_a_dull_icon_in_a_saturated_family_is_an_outlier_warning_not_a_failure(
        pil, flat_facts, tmp_path):
    res, kv = _check(_flat(pil, tmp_path / "ok.png", glyph=(60, 190, 90)), flat_facts, tmp_path)
    assert kv["CONSISTENCY"] == "ok" and "CONSISTENCY_REASON" not in kv
    dull = _flat(pil, tmp_path / "dull.png", glyph=(150, 158, 162))
    res, kv = _check(dull, flat_facts, tmp_path)
    assert res.returncode == 0, "an outlier is the agent's call, not a failure: " + res.stdout
    assert kv["ICON_GATE"] == "PASS" and kv["CONSISTENCY"] == "outlier"
    assert "CONSISTENCY_REASON=saturation" in res.stdout


def test_a_pale_glyph_has_low_contrast_on_light_and_a_black_one_on_dark(pil, flat_facts, tmp_path):
    res, kv = _check(_flat(pil, tmp_path / "w.png", glyph=(255, 247, 242)), flat_facts, tmp_path)
    assert res.returncode == 0 and kv["CONTRAST_LIGHT"] == "low" and kv["CONTRAST_DARK"] == "ok"
    res, kv = _check(_flat(pil, tmp_path / "b.png", glyph=(20, 14, 10)), flat_facts, tmp_path)
    assert res.returncode == 0 and kv["CONTRAST_DARK"] == "low" and kv["CONTRAST_LIGHT"] == "ok"
    res, kv = _check(_flat(pil, tmp_path / "m.png", glyph=(230, 60, 60)), flat_facts, tmp_path)
    assert kv["CONTRAST_LIGHT"] == "ok" and kv["CONTRAST_DARK"] == "ok"


def test_the_contact_sheet_shows_the_icon_and_eight_family_icons_on_light_and_dark(
        pil, flat_facts, tmp_path):
    res, kv = _check(_flat(pil, tmp_path / "i.png"), flat_facts, tmp_path)
    sheet = pil.open(kv["CONTACT_SHEET"]).convert("RGB")
    assert kv["CONTACT_SHEET"].endswith("icon-contact-sheet.png")
    assert sheet.size == (12 + 9 * (96 + 12), 2 * (96 + 24)), "9 cells (icon + 8), two rows"
    assert sheet.getpixel((2, 2)) == (255, 255, 255), "the top row is the light half"
    assert sheet.getpixel((2, sheet.height - 3)) == (33, 37, 41), "the bottom row is the dark half"
    cell_x = 12 + 48
    assert sheet.getpixel((cell_x, 12 + 48)) != (255, 255, 255), "the new icon is drawn first"


def test_the_contact_sheet_skips_family_icons_that_are_gone(pil, flat_facts, tmp_path):
    for line in flat_facts.read_text(encoding="utf-8").splitlines():
        if line.startswith("FAMILY_SAMPLE="):
            os.remove(line.split("=", 1)[1])
    res, kv = _check(_flat(pil, tmp_path / "i.png"), flat_facts, tmp_path)
    assert res.returncode == 0 and pil.open(kv["CONTACT_SHEET"]).size == (12 + 108, 2 * 120)


def test_previews_are_32px_and_a_nearest_neighbour_x5_zoom(pil, tile_facts, tmp_path):
    res, kv = _check(_tile(pil, tmp_path / "i.png"), tile_facts, tmp_path)
    small = pil.open(kv["PREVIEW_32"])
    zoom = pil.open(kv["PREVIEW_ZOOM"]).convert("RGBA")
    assert small.size == (32, 32) and zoom.size == (160, 160)
    assert kv["PREVIEW_32"].endswith("icon-32.png") and kv["PREVIEW_ZOOM"].endswith("icon-32-x5.png")
    zp, sp = zoom.load(), small.convert("RGBA").load()
    for by in range(32):
        for bx in range(32):
            block = {zp[bx * 5 + dx, by * 5 + dy] for dx in range(5) for dy in range(5)}
            assert block == {sp[bx, by]}, f"block {bx},{by} is not a uniform 5x5 enlargement"


def test_default_previews_land_under_the_state_root(pil, tile_facts, tmp_path):
    iso = tmp_path / "isolate"
    res, kv = _run("check", _tile(pil, tmp_path / "i.png"), "--facts", tile_facts,
                   env={"ODOO_AI_WORKTREE_DIR": str(iso)})
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["PREVIEW_32"] == str(iso / "icon-gate" / "icon-32.png")
    assert Path(kv["CONTACT_SHEET"]).is_file()


def test_an_svg_is_rasterized_at_the_native_size_then_judged(pil, stubs, flat_facts, tmp_path):
    big = _flat(pil, tmp_path / "rendered.png")
    stubs.add("rsvg-convert")
    env = dict(stubs.env, STUB_PNG=str(big))
    res, kv = _run("check", stubs.svg_path, "--facts", flat_facts, "--out-dir",
                   tmp_path / "gate", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["RASTERIZER"] == "rsvg-convert"
    assert kv["PNG_PATH"] == str(tmp_path / "gate" / "icon.png")
    assert stubs.argv("rsvg-convert")[1:5] == ["-w", "100", "-h", "100"]


def test_sample_reports_style_plate_glyph_radius_and_size_of_a_tile(pil, tmp_path):
    p = _tile(pil, tmp_path / "family.png", size=256, radius=40)
    res, kv = _run("sample", p)
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["STYLE"] == "tile" and kv["PLATE"] == "#00bbce" and kv["GLYPH"] == "#ffffff"
    assert abs(int(kv["CORNER_RADIUS_PX"]) - 40) <= 2
    assert kv["SIZE"] == "256x256"


def test_sample_reports_a_flat_icon_without_a_plate(pil, tmp_path):
    res, kv = _run("sample", _flat(pil, tmp_path / "f.png"))
    assert kv["STYLE"] == "flat" and "PLATE" not in kv
    assert kv["GLYPH"] == "#e63c3c" and kv["SIZE"] == "100x100"


# ---------------------------------------------------------------------------
# observe (a real Chromium against a fixture site)
# ---------------------------------------------------------------------------
RECORDER_TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "video_record.py"


def _recorder_ready():
    res = subprocess.run([sys.executable, str(RECORDER_TOOL), "install-check"],
                         capture_output=True, text=True, timeout=120)
    return res.returncode == 0


MASKED = "pass" + "word"
LOGIN_PAGE = f'''<!doctype html><title>sign in</title>
<form id=f><input name=login><input type="{MASKED}" name="{MASKED}">
<button type=submit>Go</button></form>
<script>document.getElementById('f').onsubmit = (e) => {{ e.preventDefault(); location = '/'; }};</script>'''
APPS_PAGE = '''<!doctype html><title>apps</title>
<body style="margin:0;background:#fff">
<div style="display:flex;gap:40px;padding:30px">
  <div class=app><div style="background:#f8f9fa;border-radius:12px;padding:10px;width:70px;height:70px;box-sizing:border-box">
    <img src="/sale/static/description/icon.png" alt="Sales" width=50 height=50></div><span>Sales</span></div>
  <div class=app><img src="/brand/crm.png" alt="CRM" width=64 height=64><span>CRM</span></div>
  <div class=app><img src="/brand/wide.png" alt="Logo" width=96 height=24></div>
</div></body>'''


def _serve(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _site(root, index):
    Image = pytest.importorskip("PIL.Image")
    if not _recorder_ready():
        pytest.skip("node >= 20 and the pinned playwright library are not installed")
    (root / "web" / "login").mkdir(parents=True)
    (root / "web" / "login" / "index.html").write_text(LOGIN_PAGE, encoding="utf-8")
    (root / "index.html").write_text(index, encoding="utf-8")
    (root / "sale" / "static" / "description").mkdir(parents=True)
    (root / "brand").mkdir()
    Image.new("RGBA", (64, 64), (0, 187, 206, 255)).save(root / "sale" / "static" / "description" / "icon.png")
    Image.new("RGBA", (64, 64), (127, 66, 130, 255)).save(root / "brand" / "crm.png")
    Image.new("RGBA", (96, 24), (10, 10, 10, 255)).save(root / "brand" / "wide.png")
    (root / "crm" / "static" / "description").mkdir(parents=True)
    Image.new("RGBA", (64, 64), (220, 90, 40, 255)).save(root / "crm" / "static" / "description" / "icon.png")
    return _serve(root)


@pytest.fixture(scope="module")
def apps_site(tmp_path_factory):
    server = _site(tmp_path_factory.mktemp("apps"), APPS_PAGE)
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="module")
def bare_site(tmp_path_factory):
    server = _site(tmp_path_factory.mktemp("bare"), "<!doctype html><title>home</title><p>no apps here</p>")
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_observe_measures_the_box_and_tells_a_themed_tile_from_a_bare_image(apps_site, tmp_path):
    res, kv = _run("observe", "--base-url", apps_site, "--ui-user", "demo", "--module", "sale",
                   "--out-dir", tmp_path / "obs")
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["BOX_PX"] == "50x50" and kv["THEME_TILE"] == "yes"
    assert kv["TILE_BOX_PX"] == "70x70" and kv["ICON_COUNT"] == "2"
    assert kv["ICON_OVERRIDE"] == "no", "the shown bytes are the module's own"
    assert Path(kv["SCREENSHOT"]).stat().st_size > 0

    res, kv = _run("observe", "--base-url", apps_site, "--ui-user", "demo", "--module", "crm",
                   "--out-dir", tmp_path / "obs")
    assert res.returncode == 0, res.stdout + res.stderr
    assert kv["BOX_PX"] == "64x64" and kv["THEME_TILE"] == "no" and "TILE_BOX_PX" not in kv
    assert kv["ICON_OVERRIDE"] == "yes", "the shown icon differs from the module's own file"


def test_observe_with_nothing_to_measure_exits_four(bare_site, tmp_path):
    res, kv = _run("observe", "--base-url", bare_site, "--ui-user", "demo",
                   "--module", "sale", "--out-dir", tmp_path / "obs")
    assert res.returncode == 4, res.stdout + res.stderr
    assert "UNKNOWN" in kv and "BOX_PX" not in kv


def test_observe_without_the_recorder_library_exits_two_with_the_remedy(tmp_path):
    env = {"ODOO_AI_RECORDER_NODE_PATH": str(tmp_path / "nowhere")}
    res, kv = _run("observe", "--base-url", "http://127.0.0.1:1", "--ui-user", "u",
                   "--module", "m", env=env)
    assert res.returncode == 2
    assert kv["REMEDY"] == "run /odoo-ai-agents:odoo-setup browser"
