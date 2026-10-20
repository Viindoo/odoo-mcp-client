"""Behavior tests for scripts/lib/docs_site/images.py - screenshots into a Sphinx docs repo.

Two promises are protected. `install` must never write somewhere the docs repo did not already
have a place for an image, never swap a screenshot for one of another size by accident, and
always produce a flat, non-progressive JPEG. `check` must say, per language, which referenced image
is missing - the build silently falls back to the other language's picture otherwise.

Pillow-backed cases skip when Pillow is absent; the mapping, refusal and check logic is pure.

Run with: python3 -m pytest tests/test_docs_site_images.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from docs_site import images  # noqa: E402

SCRIPT = LIB / "docs_site" / "images.py"

try:
    from PIL import Image
except ImportError:                      # pragma: no cover - depends on the host
    Image = None
needs_pillow = pytest.mark.skipif(Image is None, reason="Pillow is not installed")


def touch(root, rel, data=b"x"):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def run_cli(*args):
    res = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True,
                         text=True, timeout=120)
    return res


# ----------------------------------------------------------------------------- install: mapping

def test_a_staged_png_maps_to_a_jpg_with_the_same_stem_and_language(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    touch(staging, "content/a/img-p/01-form.vi.png")
    touch(staging, "content/a/img-p/02-list.en.jpg")
    (wt / "content/a/img-p").mkdir(parents=True)
    plan = images.plan_install(str(staging), str(wt))
    got = {i["source"]: (i["target"], i["status"]) for i in plan["items"]}
    assert got["content/a/img-p/01-form.vi.png"] == ("content/a/img-p/01-form.vi.jpg", "ok")
    assert got["content/a/img-p/02-list.en.jpg"] == ("content/a/img-p/02-list.en.jpg", "ok")


def test_a_target_whose_directory_does_not_exist_is_refused_and_reported(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    touch(staging, "content/new/img-p/01-form.vi.png")
    wt.mkdir()
    (item,) = images.plan_install(str(staging), str(wt))["items"]
    assert item["status"] == "refused"
    assert item["reason"].startswith("TARGET_DIR_MISSING")
    assert not (wt / "content").exists()          # the plan never creates the directory


def test_a_staged_image_without_a_language_suffix_is_refused(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    touch(staging, "content/a/01-form.png")
    (wt / "content/a").mkdir(parents=True)
    (item,) = images.plan_install(str(staging), str(wt))["items"]
    assert item["status"] == "refused"
    assert item["reason"].startswith("NO_LANG_SUFFIX")


def test_two_staged_files_for_one_target_are_both_refused(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    touch(staging, "content/a/01-form.vi.png")
    touch(staging, "content/a/01-form.vi.jpg")
    (wt / "content/a").mkdir(parents=True)
    items = images.plan_install(str(staging), str(wt))["items"]
    assert [i["status"] for i in items] == ["refused", "refused"]
    assert all(i["reason"].startswith("TARGET_COLLISION") for i in items)


def test_non_image_files_in_staging_are_skipped_not_installed(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    touch(staging, "content/a/notes.txt")
    (wt / "content/a").mkdir(parents=True)
    plan = images.plan_install(str(staging), str(wt))
    assert plan["items"] == []
    assert plan["skipped"] == ["content/a/notes.txt"]


# ----------------------------------------------------------------------------- install: pixels

def png(path, size, colour, mode="RGB"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, colour).save(path)


@needs_pillow
def test_transparency_is_flattened_onto_white(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (8, 8), (255, 0, 0, 0), "RGBA")      # fully transparent red
    (wt / "d").mkdir(parents=True)
    res = run_cli("install", "--staging", staging, "--worktree", wt, "--json")
    assert res.returncode == 0, res.stderr
    with Image.open(wt / "d/01-x.vi.jpg") as out:
        assert out.mode == "RGB"
        r, g, b = out.getpixel((4, 4))
        assert min(r, g, b) >= 250          # white, not the black or red a naive convert gives


@needs_pillow
def test_the_jpeg_is_quality_85_and_not_progressive_by_default(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (64, 64), (10, 120, 200))
    (wt / "d").mkdir(parents=True)
    assert run_cli("install", "--staging", staging, "--worktree", wt).returncode == 0
    with Image.open(wt / "d/01-x.vi.jpg") as out:
        assert out.format == "JPEG"
        assert "progressive" not in out.info and "progression" not in out.info
        assert out.quantization[0][0] == 5          # the luminance table scaled for quality 85


@needs_pillow
def test_the_quality_flag_changes_the_encoding(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (64, 64), (10, 120, 200))
    (wt / "d").mkdir(parents=True)
    assert run_cli("install", "--staging", staging, "--worktree", wt, "--quality", "50").returncode == 0
    with Image.open(wt / "d/01-x.vi.jpg") as out:
        assert out.quantization[0][0] == 16     # the unscaled standard table (quality 50)


@needs_pillow
def test_replacing_a_screenshot_with_one_of_another_pixel_size_is_refused(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (20, 20), (0, 0, 0))
    (wt / "d").mkdir(parents=True)
    wt_path = wt / "d/01-x.vi.jpg"
    Image.new("RGB", (10, 10), (255, 255, 255)).save(wt_path)
    before = wt_path.read_bytes()
    res = run_cli("install", "--staging", staging, "--worktree", wt, "--json")
    assert res.returncode == 1
    report = json.loads(res.stdout)
    assert report["refused"][0]["reason"].startswith("SIZE_CHANGED")
    assert wt_path.read_bytes() == before


@needs_pillow
def test_allow_resize_lets_a_different_pixel_size_replace_the_old_one(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (20, 20), (0, 0, 0))
    (wt / "d").mkdir(parents=True)
    Image.new("RGB", (10, 10), (255, 255, 255)).save(wt / "d/01-x.vi.jpg")
    assert run_cli("install", "--staging", staging, "--worktree", wt, "--allow-resize").returncode == 0
    with Image.open(wt / "d/01-x.vi.jpg") as out:
        assert out.size == (20, 20)


@needs_pillow
def test_an_image_of_the_same_size_replaces_the_old_one(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "d/01-x.vi.png", (10, 10), (0, 0, 0))
    (wt / "d").mkdir(parents=True)
    Image.new("RGB", (10, 10), (255, 255, 255)).save(wt / "d/01-x.vi.jpg")
    assert run_cli("install", "--staging", staging, "--worktree", wt).returncode == 0
    with Image.open(wt / "d/01-x.vi.jpg") as out:
        assert out.getpixel((5, 5))[0] < 20


@needs_pillow
def test_a_refused_target_leaves_no_file_and_the_others_still_install(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    png(staging / "ok/01-x.vi.png", (8, 8), (1, 2, 3))
    png(staging / "missing/01-y.vi.png", (8, 8), (1, 2, 3))
    (wt / "ok").mkdir(parents=True)
    res = run_cli("install", "--staging", staging, "--worktree", wt, "--json")
    assert res.returncode == 1
    report = json.loads(res.stdout)
    assert [r["target"] for r in report["installed"]] == ["ok/01-x.vi.jpg"]
    assert not (wt / "missing").exists()
    assert sorted(p.name for p in (wt / "ok").iterdir()) == ["01-x.vi.jpg"]      # no temp file left


def test_install_without_pillow_exits_3_with_a_remedy_line(tmp_path):
    staging, wt = tmp_path / "s", tmp_path / "w"
    staging.mkdir()
    wt.mkdir()
    code = ("import sys, runpy; sys.modules['PIL'] = None; sys.modules['PIL.Image'] = None; "
            "sys.argv = ['images.py', 'install', '--staging', %r, '--worktree', %r]; "
            "runpy.run_path(%r, run_name='__main__')" % (str(staging), str(wt), str(SCRIPT)))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert res.returncode == 3
    assert "pip install" in res.stderr and "Pillow" in res.stderr


def test_check_does_not_need_pillow(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "content/p.rst").write_text("text\n", encoding="utf-8")
    code = ("import sys, runpy; sys.modules['PIL'] = None; sys.modules['PIL.Image'] = None; "
            "sys.argv = ['images.py', 'check', '--worktree', %r, '--pages', 'content/p.rst', "
            "'--langs', 'en']; runpy.run_path(%r, run_name='__main__')" % (str(tmp_path), str(SCRIPT)))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr


# ----------------------------------------------------------------------------- check

PAGE = """\
Page
====

.. figure:: img-page/01-form.jpg

   A caption.

.. image:: /shared/02-chart.jpg
   :alt: chart

.. image:: https://example.invalid/remote.jpg
"""


def make_page(tmp_path, conf=None):
    touch(tmp_path, "content/a/page.rst", PAGE.encode())
    if conf is not None:
        touch(tmp_path, "conf.py", conf.encode())


def test_check_reports_each_language_whose_image_is_missing(tmp_path):
    make_page(tmp_path)
    touch(tmp_path, "content/a/img-page/01-form.en.jpg")
    touch(tmp_path, "content/shared/02-chart.en.jpg")
    touch(tmp_path, "content/shared/02-chart.vi.jpg")
    result = images.check_pages(str(tmp_path), ["content/a/page.rst"], ["en", "vi"],
                                "{root}.{language}{ext}")
    assert [(m["lang"], m["expected"]) for m in result["missing"]] == [
        ("vi", "content/a/img-page/01-form.vi.jpg")]
    assert result["checked"] == 2           # the remote URL is not a repo image


def test_check_is_clean_when_every_language_has_every_image(tmp_path):
    make_page(tmp_path)
    for lang in ("en", "vi"):
        touch(tmp_path, "content/a/img-page/01-form.%s.jpg" % lang)
        touch(tmp_path, "content/shared/02-chart.%s.jpg" % lang)
    result = images.check_pages(str(tmp_path), ["content/a/page.rst"], ["en", "vi"],
                                "{root}.{language}{ext}")
    assert result["missing"] == [] and result["errors"] == []


def test_a_plain_suffixless_file_does_not_stand_in_for_a_language_image(tmp_path):
    make_page(tmp_path)
    touch(tmp_path, "content/a/img-page/01-form.jpg")        # only the plain file exists
    result = images.check_pages(str(tmp_path), ["content/a/page.rst"], ["vi"], "{root}.{language}{ext}",
                                source_lang="en")
    first = result["missing"][0]
    assert first["ref"] == "img-page/01-form.jpg" and first["plain_exists"] is True


def test_the_source_language_may_rely_on_the_plain_image_but_a_target_language_may_not(tmp_path):
    make_page(tmp_path)
    touch(tmp_path, "content/a/img-page/01-form.jpg")        # plain only: Sphinx falls back for the source
    touch(tmp_path, "content/shared/02-chart.jpg")
    result = images.check_pages(str(tmp_path), ["content/a/page.rst"], ["en", "vi"],
                                "{root}.{language}{ext}")
    assert sorted((m["lang"], m["plain_exists"]) for m in result["missing"]) == [("vi", True), ("vi", True)]


def test_the_source_language_is_missing_an_image_when_even_the_plain_file_is_absent(tmp_path):
    make_page(tmp_path)
    result = images.check_pages(str(tmp_path), ["content/a/page.rst"], ["en"], "{root}.{language}{ext}")
    assert [(m["lang"], m["plain_exists"]) for m in result["missing"]] == [("en", False), ("en", False)]


def test_source_lang_flag_names_the_fallback_language_and_text_output_prints_plain_exists(tmp_path):
    make_page(tmp_path)
    touch(tmp_path, "content/a/img-page/01-form.jpg")
    touch(tmp_path, "content/shared/02-chart.jpg")
    first_is_source = run_cli("check", "--worktree", tmp_path, "--pages", "content/a/page.rst",
                              "--langs", "vi,en")
    assert "[en] content/a/img-page/01-form.en.jpg (plain_exists: true)" in first_is_source.stdout
    assert "[vi]" not in first_is_source.stdout
    flagged = run_cli("check", "--worktree", tmp_path, "--pages", "content/a/page.rst",
                      "--langs", "vi,en", "--source-lang", "en", "--json")
    assert json.loads(flagged.stdout)["source_lang"] == "en"
    assert {m["lang"] for m in json.loads(flagged.stdout)["missing"]} == {"vi"}


def test_check_follows_the_repos_figure_language_filename(tmp_path):
    make_page(tmp_path, conf="figure_language_filename = '{path}{language}/{basename}{ext}'\n")
    touch(tmp_path, "content/a/img-page/vi/01-form.jpg")
    touch(tmp_path, "content/shared/vi/02-chart.jpg")
    res = run_cli("check", "--worktree", tmp_path, "--pages", "content/a/page.rst", "--langs", "vi", "--json")
    assert res.returncode == 0, res.stdout
    assert json.loads(res.stdout)["figure_language_filename"]["source"] == "conf.py"


def test_a_filename_format_the_check_cannot_evaluate_is_an_error_not_a_pass(tmp_path):
    make_page(tmp_path, conf="figure_language_filename = '{resolved_path}.{language}'\n")
    res = run_cli("check", "--worktree", tmp_path, "--pages", "content/a/page.rst", "--langs", "vi", "--json")
    assert res.returncode == 1
    assert json.loads(res.stdout)["errors"][0]["error"] == "UNSUPPORTED_FIGURE_LANGUAGE_FILENAME"


def test_check_fails_the_cli_when_an_image_is_missing(tmp_path):
    make_page(tmp_path)
    res = run_cli("check", "--worktree", tmp_path, "--pages", "content/a/page.rst", "--langs", "en,vi")
    assert res.returncode == 1
    assert "MISSING" in res.stdout


def test_a_page_that_does_not_exist_fails_the_check(tmp_path):
    res = run_cli("check", "--worktree", tmp_path, "--pages", "content/none.rst", "--langs", "en", "--json")
    assert res.returncode == 1
    assert json.loads(res.stdout)["errors"][0]["error"] == "PAGE_NOT_FOUND"
