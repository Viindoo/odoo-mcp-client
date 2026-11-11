"""Behaviour tests for scripts/lib/image_sheet.py - the one contact-sheet and image-size command.

A sheet tiles screenshots without ever enlarging one; a request whose canvas is too big is refused
before a pixel buffer exists; `size` reads the dimensions from the file; a missing Pillow is reported.

Run with: python3 -m pytest tests/test_image_sheet.py -q
"""
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:                      # pragma: no cover - depends on the host
    Image = None
needs_pillow = pytest.mark.skipif(Image is None, reason="Pillow is not installed")

SCRIPT = (Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
          / "image_sheet.py")

# Runs the script in-process and reports the peak resident memory (KiB) of that process on stderr.
_PEAK_WRAPPER = (
    "import sys, runpy, resource\n"
    "sys.argv = ['image_sheet.py'] + sys.argv[1:]\n"
    "try:\n"
    "    runpy.run_path(%r, run_name='__main__')\n"
    "except SystemExit as exc:\n"
    "    code = exc.code or 0\n"
    "else:\n"
    "    code = 0\n"
    # ru_maxrss survives fork+exec, so a child of a large test process would report the parent's
    # peak; VmHWM is this process image's own high-water mark.
    "peak = None\n"
    "try:\n"
    "    with open('/proc/self/status') as fh:\n"
    "        for line in fh:\n"
    "            if line.startswith('VmHWM:'):\n"
    "                peak = int(line.split()[1])\n"
    "except OSError:\n"
    "    pass\n"
    "if peak is None:\n"
    "    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
    "    peak = peak // 1024 if sys.platform == 'darwin' else peak\n"
    "sys.stderr.write('PEAK_KIB=%%d\\n' %% peak)\n"
    "sys.exit(code)\n" % str(SCRIPT))


def run(*args, block_pillow=False):
    if block_pillow:
        code = ("import sys, runpy; sys.modules['PIL'] = None; sys.argv = ['image_sheet.py'] + %r; "
                "runpy.run_path(%r, run_name='__main__')" % ([str(a) for a in args], str(SCRIPT)))
        cmd = [sys.executable, "-c", code]
    else:
        cmd = [sys.executable, str(SCRIPT)] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def run_measured(*args):
    res = subprocess.run([sys.executable, "-c", _PEAK_WRAPPER] + [str(a) for a in args],
                         capture_output=True, text=True, timeout=120)
    peak = int([ln for ln in res.stderr.splitlines() if ln.startswith("PEAK_KIB=")][-1].split("=")[1])
    return res, peak


def shot(tmp_path, name, size, color):
    path = tmp_path / name
    Image.new("RGB", size, color).save(path)
    return path


def keyed(res, key):
    return [ln.split("=", 1)[1] for ln in res.stdout.splitlines() if ln.startswith(key + "=")]


@needs_pillow
def test_a_sheet_has_one_cell_per_image_laid_out_in_the_requested_columns(tmp_path):
    reds = [shot(tmp_path, "r%d.png" % i, (300, 200), (255, 0, 0)) for i in range(3)]
    out = tmp_path / "sheet.png"
    res = run("sheet", "--out", out, "--col-width", 300, "--columns", 2, "--inputs", *reds)
    assert res.returncode == 0
    w, h, count = map(int, keyed(res, "SHEET")[0].split(" ")[-3:])
    assert count == 3
    with Image.open(out) as sheet:
        assert sheet.size == (w, h)
        assert w > 2 * 300 and w < 3 * 300 + 40        # two columns, not three
        assert h > 2 * 200 and h < 3 * 200 + 40        # two rows
        assert sheet.getpixel((w // 2 - 150, 8 + 100)) == (255, 0, 0)    # first tile painted


@needs_pillow
def test_an_image_wider_than_the_column_is_scaled_down_keeping_its_proportions(tmp_path):
    big = shot(tmp_path, "big.png", (1200, 600), (0, 0, 255))
    out = tmp_path / "sheet.png"
    res = run("sheet", "--out", out, "--col-width", 400, "--columns", 1, "--inputs", big)
    assert res.returncode == 0
    with Image.open(out) as sheet:
        assert sheet.width < 1200 / 2                   # nothing close to native width
        assert 400 <= sheet.width <= 440
        assert 200 <= sheet.height <= 240               # 600 * 400/1200 = 200 plus margins


@needs_pillow
def test_an_image_narrower_than_the_column_is_never_enlarged(tmp_path):
    small = shot(tmp_path, "small.png", (100, 80), (0, 255, 0))
    out = tmp_path / "sheet.png"
    res = run("sheet", "--out", out, "--col-width", 800, "--columns", 1, "--inputs", small)
    assert res.returncode == 0
    with Image.open(out) as sheet:
        assert sheet.height < 80 + 40                   # tile kept at 80 rows, not 640
        assert dict((c, n) for n, c in sheet.getcolors(maxcolors=10))[(0, 255, 0)] == 100 * 80


@needs_pillow
@pytest.mark.parametrize("flags", [
    ["--col-width", "300", "--columns", "330"],                    # the incident: 330 columns
    ["--col-width", "100000", "--columns", "2"],                   # absurd column width
    ["--col-width", "2000", "--columns", "1"],                     # tall stack: canvas over the pixel cap
])
def test_an_oversized_request_is_refused_quickly_and_small_without_writing_a_file(tmp_path, flags):
    images = [shot(tmp_path, "i%d.png" % i, (2000, 2000), (9, 9, 9)) for i in range(5)]
    out = tmp_path / "sheet.png"
    res, peak_kib = run_measured("sheet", "--out", out, *flags, "--inputs", *images)
    assert res.returncode == 1
    assert len(keyed(res, "REFUSED")) == 1
    assert not out.exists()
    assert peak_kib < 150 * 1024                        # a 16 MPx+ canvas alone would be far above


@needs_pillow
def test_the_most_a_sheet_may_ask_for_still_builds_within_bounded_memory(tmp_path):
    images = [shot(tmp_path, "i%d.png" % i, (1500, 1000), (5, 5, 5)) for i in range(12)]
    out = tmp_path / "sheet.png"
    res, peak_kib = run_measured("sheet", "--out", out, "--col-width", 600, "--columns", 3,
                                 "--inputs", *images)
    assert res.returncode == 0
    assert peak_kib < 600 * 1024


@needs_pillow
def test_size_reports_the_pixel_width_and_height_read_from_each_file(tmp_path):
    a = shot(tmp_path, "a.png", (321, 123), (1, 2, 3))
    b = shot(tmp_path, "b.png", (7, 9), (1, 2, 3))
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    res = run("size", "--inputs", a, b, bad)
    assert res.returncode == 0
    assert keyed(res, "SIZE") == ["%s 321 123" % a, "%s 7 9" % b]
    assert keyed(res, "UNREADABLE")[0].startswith(str(bad))


def test_a_missing_pillow_is_reported_with_its_remedy_and_nothing_is_written(tmp_path):
    out = tmp_path / "sheet.png"
    res = run("sheet", "--out", out, "--col-width", 300, "--columns", 2, "--inputs", tmp_path / "x.png",
              block_pillow=True)
    assert res.returncode == 0
    assert keyed(res, "PILLOW") == ["missing"]
    assert keyed(res, "REMEDY")
    assert not out.exists()


def test_a_call_without_its_named_flags_is_a_usage_error():
    assert run("sheet", "x.png").returncode == 2


def _png(path, width, height):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _gif(path, width, height):
    # header, logical screen descriptor, one global colour, one image descriptor with LZW data, trailer
    path.write_bytes(b"GIF89a" + struct.pack("<HHBBB", width, height, 0x80, 0, 0) + b"\x00\x00\x00\xff\xff\xff"
                     + b"\x2c" + struct.pack("<HHHHB", 0, 0, width, height, 0) + b"\x02\x02\x44\x01\x00" + b"\x3b")


def _jpeg(path, width, height):
    # a comment and an app segment come before the frame header, so the walk over segments is real
    path.write_bytes(b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                     + b"\xff\xfe" + struct.pack(">H", 6) + b"abcd"
                     + b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
                     + b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x00\xff\xd9")


@pytest.mark.parametrize("writer, name", [(_png, "a.png"), (_gif, "a.gif"), (_jpeg, "a.jpg")])
def test_size_of_a_png_gif_or_jpeg_is_read_from_the_header_without_pillow(tmp_path, writer, name):
    path = tmp_path / name
    writer(path, 321, 123)
    res = run("size", "--inputs", path, block_pillow=True)
    assert res.returncode == 0
    assert keyed(res, "SIZE") == ["%s 321 123" % path]
    assert not keyed(res, "PILLOW")


def test_size_of_a_format_that_needs_pillow_says_so_when_pillow_is_missing(tmp_path):
    path = tmp_path / "x.bmp"
    path.write_bytes(b"BM" + b"\x00" * 60)
    ok = tmp_path / "ok.png"
    _png(ok, 5, 6)
    res = run("size", "--inputs", path, ok, block_pillow=True)
    assert res.returncode == 0
    assert keyed(res, "SIZE") == ["%s 5 6" % ok]
    assert keyed(res, "UNREADABLE")[0].startswith(str(path))
    assert keyed(res, "PILLOW") == ["missing"]
