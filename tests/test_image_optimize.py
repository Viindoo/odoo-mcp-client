"""Behaviour tests for scripts/lib/image_optimize.py - lossless PNG optimisation.

A PNG is replaced only when its decoded pixels are identical and the file is smaller; any other
file type is never touched; a missing Pillow leaves everything as it was and still exits 0.

Run with: python3 -m pytest tests/test_image_optimize.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:                      # pragma: no cover - depends on the host
    Image = None
needs_pillow = pytest.mark.skipif(Image is None, reason="Pillow is not installed")

SCRIPT = (Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
          / "image_optimize.py")


def run(*paths, block_pillow=False):
    if block_pillow:
        code = ("import sys, runpy; sys.modules['PIL'] = None; sys.argv = ['image_optimize.py'] + %r; "
                "runpy.run_path(%r, run_name='__main__')" % ([str(p) for p in paths], str(SCRIPT)))
        cmd = [sys.executable, "-c", code]
    else:
        cmd = [sys.executable, str(SCRIPT)] + [str(p) for p in paths]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def gradient(mode="RGB", size=(64, 48)):
    img = Image.new(mode, size)
    img.putdata([tuple((x * 4 + y * 3 + c * 50) % 256 for c in range(len(mode))) if len(mode) > 1
                 else (x * 4 + y) % 256 for y in range(size[1]) for x in range(size[0])])
    return img


def rgba(path):
    with Image.open(path) as img:
        return img.convert("RGBA").tobytes()


@needs_pillow
def test_an_unoptimised_png_gets_smaller_with_identical_pixels(tmp_path):
    path = tmp_path / "a.png"
    gradient().save(path, compress_level=0)
    before_bytes, before_pixels = path.stat().st_size, rgba(path)
    res = run(path)
    assert res.returncode == 0
    assert path.stat().st_size < before_bytes
    assert rgba(path) == before_pixels
    assert "OPTIMIZED=%s %d %d" % (path, before_bytes, path.stat().st_size) in res.stdout
    assert "SAVED_BYTES=%d" % (before_bytes - path.stat().st_size) in res.stdout


@needs_pillow
def test_an_already_optimised_png_is_kept_byte_identical(tmp_path):
    path = tmp_path / "a.png"
    gradient().save(path, optimize=True)
    run(path)                                  # first pass reaches the floor
    first = path.read_bytes()
    res = run(path)
    assert path.read_bytes() == first
    assert "KEPT=%s" % path in res.stdout and "SAVED_BYTES=0" in res.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.png"]      # no temp file left


@needs_pillow
def test_transparency_survives(tmp_path):
    path = tmp_path / "t.png"
    img = gradient("RGBA")
    img.putalpha(Image.linear_gradient("L").resize(img.size))
    img.save(path, compress_level=0)
    before = rgba(path)
    run(path)
    assert rgba(path) == before
    assert path.stat().st_size < len(before)


@needs_pillow
def test_a_palette_png_with_a_transparent_index_survives(tmp_path):
    path = tmp_path / "p.png"
    img = gradient().quantize(16)
    img.save(path, transparency=0, compress_level=0)
    before = rgba(path)
    run(path)
    assert rgba(path) == before
    with Image.open(path) as out:
        assert out.mode == "P" and "transparency" in out.info


@needs_pillow
def test_jpeg_and_gif_are_never_touched(tmp_path):
    jpg, gif = tmp_path / "a.jpg", tmp_path / "b.gif"
    gradient().save(jpg, quality=95)
    gradient("P" if False else "RGB").quantize(8).save(gif)
    sums = (jpg.read_bytes(), gif.read_bytes())
    res = run(jpg, gif)
    assert (jpg.read_bytes(), gif.read_bytes()) == sums
    assert "SKIPPED=%s not a png" % jpg in res.stdout and "SKIPPED=%s not a png" % gif in res.stdout


@needs_pillow
def test_a_directory_is_recursed_and_the_extension_is_case_insensitive(tmp_path):
    (tmp_path / "deep" / "er").mkdir(parents=True)
    paths = [tmp_path / "x.png", tmp_path / "deep" / "er" / "y.PNG"]
    for p in paths:
        gradient().save(p, format="PNG", compress_level=0)
    res = run(tmp_path)
    for p in paths:
        assert "OPTIMIZED=%s " % p in res.stdout


def test_without_pillow_every_file_is_untouched_and_the_exit_is_zero(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"not really a png")
    res = run(path, block_pillow=True)
    assert res.returncode == 0
    assert "PILLOW=missing" in res.stdout and "REMEDY=" in res.stdout
    assert "brew install pillow" in res.stdout and "python3-pil" in res.stdout
    assert path.read_bytes() == b"not really a png"


def test_no_path_is_a_usage_error():
    assert run().returncode == 2
