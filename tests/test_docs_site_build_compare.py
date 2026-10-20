"""build_compare.py: build a docs repo at a base ref and as it stands, compare, and serve.

Pure-function tests and the serve/stop tests always run. The build tests need a python that has
Sphinx (the docs repo's own venv): this suite's venv is used when it has it, else
$DOCS_SITE_TEST_PYTHON, else those tests skip.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "plugins/odoo-ai-agents/scripts/lib/docs_site/build_compare.py"


def _load():
    sys.path.insert(0, str(MODULE.parent))
    try:
        spec = importlib.util.spec_from_file_location("build_compare_under_test", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(MODULE.parent))
    return mod


bc = _load()


def _has_sphinx(python):
    return bool(python) and subprocess.call(
        [python, "-c", "import importlib.util,sys;sys.exit(importlib.util.find_spec('sphinx') is None)"]
    ) == 0


DOCS_PYTHON = next((p for p in (sys.executable, os.environ.get("DOCS_SITE_TEST_PYTHON"))
                    if _has_sphinx(p)), None)
needs_sphinx = pytest.mark.skipif(
    DOCS_PYTHON is None,
    reason="no python with Sphinx (the docs repo venv): set DOCS_SITE_TEST_PYTHON")


# --------------------------------------------------------------------------- pure functions
def test_the_makefiles_own_language_and_build_dir_variables_are_detected():
    text = ("CURRENT_LANG ?= en\nBUILD_DIR = _build\nhtml:\n\tsphinx-build -b html . $(BUILD_DIR)\n")
    assert bc.detect_make_vars(text) == ("CURRENT_LANG", "BUILD_DIR")


def test_a_makefile_without_the_variables_falls_back_to_plain_sphinx_build():
    quickstart = "SPHINXOPTS ?=\nBUILDDIR = _build\n%: Makefile\n\t@sphinx-build -M $@ . $(BUILDDIR)\n"
    assert bc.detect_make_vars(quickstart) == (None, None)  # BUILDDIR but no language variable
    assert bc.detect_make_vars("LANG = C\nBUILD_DIR = x\nhtml:\n\ttrue\n") == (None, None)  # env LANG is not it
    assert bc.detect_make_vars("CURRENT_LANG = en\nBUILD_DIR = x\n") == (None, None)  # nothing builds html


def test_the_same_warning_in_two_checkouts_normalises_to_one_string():
    a = "/cache/x/base/content/a.rst:12: WARNING: undefined label: 'nolabel' [ref.ref]"
    b = "/cache/x/cand/content/a.rst:47: WARNING: undefined label: 'nolabel' [ref.ref]"
    na = bc.normalize_problem(a, ["/cache/x/base"])
    nb = bc.normalize_problem(b, ["/cache/x/cand"])
    assert na == nb == "content/a.rst: WARNING: undefined label: 'nolabel' [ref.ref]"


def test_normalisation_drops_colour_codes_absolute_dirs_outside_the_tree_and_line_words():
    line = "\x1b[91m/usr/lib/python3/site-packages/sphinx/x.py:88: WARNING: odd at line 9\x1b[39m"
    assert bc.normalize_problem(line) == "x.py: WARNING: odd at line N"


def test_a_different_warning_message_is_not_normalised_away():
    assert (bc.normalize_problem("a.rst:3: WARNING: unknown document: 'x'")
            != bc.normalize_problem("a.rst:3: WARNING: unknown document: 'y'"))


def test_only_warning_error_and_failure_lines_of_a_log_are_problems():
    log = ("reading sources... [100%] a\n/r/a.rst:3: WARNING: broken\nbuild succeeded, 1 warning.\n"
           "/r/b.rst:9: ERROR: worse\nmake: *** [Makefile:4: html] Error 2\nnotice about warnings\n")
    got = bc.extract_problems(log, ["/r"])
    assert sorted(got) == ["a.rst: WARNING: broken", "b.rst: ERROR: worse",
                           "make: *** [Makefile: html] Error 2"]


def test_a_warning_repeated_one_more_time_than_in_base_is_new():
    base = bc.extract_problems("/b/a.rst:1: WARNING: dup\n", ["/b"])
    cand = bc.extract_problems("/c/a.rst:1: WARNING: dup\n/c/a.rst:8: WARNING: dup\n", ["/c"])
    new, fixed = bc.diff_problems(base, cand)
    assert new == ["a.rst: WARNING: dup"] and fixed == []


def test_a_warning_gone_from_the_candidate_is_reported_fixed_not_new():
    base = bc.extract_problems("/b/a.rst:1: WARNING: old\n/b/a.rst:2: WARNING: keep\n", ["/b"])
    cand = bc.extract_problems("/c/a.rst:5: WARNING: keep\n", ["/c"])
    assert bc.diff_problems(base, cand) == ([], ["a.rst: WARNING: old"])


def test_a_language_image_is_expected_only_when_the_repo_ships_it_beside_the_plain_one():
    index = {"pic.png": {"/c/img"}, "pic.vi.png": {"/c/img"},
             "other.png": {"/c/img"}, "lone.png": {"/c/x"}, "lone.vi.png": {"/c/y"}}
    exp = bc.image_expectations({"pic.png", "other.png", "lone.png"}, index, "vi",
                                "{root}.{language}{ext}")
    assert exp == {"pic.png": "pic.vi.png"}


def test_a_language_image_is_expected_when_the_variant_exists_even_though_the_plain_file_does_not():
    ref_dirs = {"pic.png": {"/c/img"}, "far.png": {"/c/img"}}
    index = {"pic.vi.png": {"/c/img"}, "far.vi.png": {"/c/elsewhere"}}
    exp = bc.image_expectations({"pic.png", "far.png"}, index, "vi", "{root}.{language}{ext}", ref_dirs)
    assert exp == {"pic.png": "pic.vi.png"}      # far.vi.png sits beside no reference of far.png


def test_image_references_resolve_against_the_page_directory_or_the_source_root():
    refs = bc.ref_dirs_by_name(".. image:: img/a.png\n.. figure:: /shared/b.png\n"
                               ".. image:: https://example.invalid/c.png\n", "/c/content/guide", "/c/content")
    assert refs == {"a.png": {"/c/content/guide/img"}, "b.png": {"/c/content/shared"}}


def test_the_built_page_is_judged_against_a_variant_that_has_no_plain_file(tmp_path):
    cand = tmp_path / "cand"
    (cand / "content" / "img").mkdir(parents=True)
    (cand / "content" / "a.rst").write_text("A\n=\n\n.. image:: img/only.png\n")
    (cand / "content" / "img" / "only.vi.png").write_bytes(b"x")          # no only.png at all
    built = tmp_path / "html"
    built.mkdir()
    (built / "a.html").write_text('<img src="_images/only.png">')           # the build ignored the variant
    rows = bc.check_images(str(cand), "content", ["content/a.rst"], "vi",
                           {"html_root": str(built)}, None, "{root}.{language}{ext}")
    assert rows[0]["expected"] == ["only.vi.png"] and rows[0]["missing"] == ["only.vi.png"]


def test_the_touched_pages_are_read_from_the_two_snapshots_not_from_the_worktree(tmp_path):
    base, cand = tmp_path / "base", tmp_path / "cand"
    for tree in (base, cand):
        (tree / "content" / "sub").mkdir(parents=True)
    (base / "content" / "same.rst").write_text("same")
    (cand / "content" / "same.rst").write_text("same")
    (base / "content" / "sub" / "edited.rst").write_text("old")
    (cand / "content" / "sub" / "edited.rst").write_text("new")
    (cand / "content" / "added.rst").write_text("added")
    (cand / "content" / "notes.txt").write_text("not a page")
    assert bc.touched_pages(str(base), str(cand), "content") == [
        "content/added.rst", "content/sub/edited.rst"]


def test_doctrees_are_removed_from_a_build_output_and_the_html_is_kept(tmp_path):
    out = tmp_path / "cand-en-out"
    for rel in ("doctrees", ".doctrees", "html/.doctrees", "html/sub"):
        (out / rel).mkdir(parents=True)
        (out / rel / "x.pickle").write_bytes(b"x" * 10)
    (out / "html" / "index.html").write_text("<p>hi</p>")
    bc.remove_doctrees(str(out))
    assert not (out / "doctrees").exists() and not (out / ".doctrees").exists()
    assert not (out / "html" / ".doctrees").exists()
    assert (out / "html" / "index.html").is_file() and (out / "html" / "sub" / "x.pickle").is_file()


def test_a_page_still_pointing_at_the_plain_image_is_missing_the_language_one():
    exp = {"pic.png": "pic.vi.png"}
    assert bc.judge_images(exp, {"pic.png"}) == (["pic.vi.png"], ["pic.png"])
    assert bc.judge_images(exp, {"pic.vi.png"}) == ([], [])


def test_the_language_filename_pattern_comes_from_the_repo_conf():
    assert bc.figure_pattern("figure_language_filename = '{root}-{language}{ext}'") == "{root}-{language}{ext}"
    assert bc.figure_pattern("project = 'x'") == "{root}.{language}{ext}"
    assert bc.language_variant("a.png", "vi", "{root}-{language}{ext}") == "a-vi.png"
    assert bc.language_variant("a.png", "vi", "{path}/{language}/{basename}") is None


def test_built_html_images_are_read_by_basename():
    html = '<p><img src="_images/pic.vi.png" alt=""><img src="../_images/a%20b.png?x=1"></p>'
    assert bc.img_basenames(html) == {"pic.vi.png", "a b.png"}


def test_a_missing_sphinx_exits_3_with_a_one_line_remedy():
    code = ("import sys; sys.modules['sphinx'] = None; sys.path.insert(0, %r); import build_compare; "
            "sys.exit(build_compare.main(['--worktree','.','--base-ref','HEAD','--langs','en']))"
            % str(MODULE.parent))
    proc = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    assert proc.returncode == 3
    assert len(proc.stderr.strip().splitlines()) == 1 and "requirements.txt" in proc.stderr


# --------------------------------------------------------------------------- serve / stop
def _port_open(port, host="127.0.0.1"):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _non_loopback_ip():
    """This machine's outward address, or None (no packet is sent by a UDP connect)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def _start_server(work, *extra):
    proc = subprocess.Popen([sys.executable, str(MODULE), "serve", "--work-dir", str(work), *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.strip())
        if line.startswith("PID "):
            break
    return proc, lines


def test_serve_exposes_every_language_on_loopback_and_stop_closes_the_port(tmp_path):
    for lang in ("en", "vi"):
        out = tmp_path / ("cand-%s-out" % lang) / "html"
        out.mkdir(parents=True)
        (out / "index.html").write_text("<h1>home %s</h1>" % lang)
    proc, lines = _start_server(tmp_path, "--port", "0")
    try:
        urls = {l.split()[1]: l.split()[2] for l in lines if l.startswith("URL ")}
        assert set(urls) == {"en", "vi"}
        assert lines[-1] == "PID %d" % proc.pid
        port = int(urls["en"].split(":")[2].split("/")[0])
        assert port > 0 and urls["vi"].startswith("http://127.0.0.1:%d/" % port)
        other = _non_loopback_ip()
        if other:  # bound to loopback only: the machine's other address must refuse
            assert not _port_open(port, other)
        for lang, url in urls.items():
            assert ("home %s" % lang) in urllib.request.urlopen(url, timeout=5).read().decode()
        stop = subprocess.run([sys.executable, str(MODULE), "stop", "--work-dir", str(tmp_path)],
                              stdout=subprocess.PIPE, universal_newlines=True)
        assert stop.returncode == 0 and stop.stdout.strip() == "STOPPED %d" % proc.pid
        proc.wait(timeout=10)
        assert not _port_open(port)
        assert not (tmp_path / "serve.pid").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()


def test_serve_refuses_a_language_that_was_not_built(tmp_path):
    out = tmp_path / "cand-en-out"
    out.mkdir()
    (out / "index.html").write_text("x")
    proc = subprocess.run([sys.executable, str(MODULE), "serve", "--work-dir", str(tmp_path),
                           "--langs", "en,fr"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=20)
    assert proc.returncode == 1 and "fr" in proc.stderr


def test_clean_stops_a_running_server_before_deleting_the_work_dir(tmp_path):
    work = tmp_path / "w"
    out = work / "cand-en-out"
    out.mkdir(parents=True)
    (out / "index.html").write_text("x")
    (work / bc._po.WORK_MARKER).write_text("")
    proc, lines = _start_server(work)
    try:
        port = int(lines[0].split(":")[2].split("/")[0])
        done = subprocess.run([sys.executable, str(MODULE), "clean", "--work-dir", str(work)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        assert done.returncode == 0 and not work.exists()
        proc.wait(timeout=10)
        assert not _port_open(port)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()


def test_clean_refuses_a_directory_that_is_not_a_work_dir(tmp_path):
    (tmp_path / "x.txt").write_text("keep")
    done = subprocess.run([sys.executable, str(MODULE), "clean", "--work-dir", str(tmp_path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert done.returncode == 1 and (tmp_path / "x.txt").is_file()


def test_stop_without_a_recorded_server_fails(tmp_path):
    proc = subprocess.run([sys.executable, str(MODULE), "stop", "--work-dir", str(tmp_path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert proc.returncode == 1


# --------------------------------------------------------------------------- builds
def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@example.test", "-c", "user.name=t", "-C", str(cwd)]
                   + list(args), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63"
    "6460f8cf5000000503010174e1c1b60000000049454e44ae426082")

CONF = "project = 'x'\nlanguage = 'en'\nlocale_dirs = ['../locale/']\n"
A_RST = "Page A\n======\n\n.. image:: img/pic.png\n\nSome text.\n"


@pytest.fixture
def site(tmp_path):
    repo = tmp_path / "docs"
    (repo / "content" / "img").mkdir(parents=True)
    (repo / "content" / "conf.py").write_text(CONF)
    (repo / "content" / "index.rst").write_text("Index\n=====\n\n.. toctree::\n\n   a\n")
    (repo / "content" / "a.rst").write_text(A_RST)
    (repo / "content" / "img" / "pic.png").write_bytes(PNG)
    (repo / "content" / "img" / "pic.vi.png").write_bytes(PNG)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def compare(site, *extra, langs="en,vi", expect=None):
    env = dict(os.environ, ODOO_AI_HOME=str(site.parent / "home"))
    proc = subprocess.run(
        [DOCS_PYTHON, str(MODULE), "--worktree", str(site), "--base-ref", "HEAD", "--langs", langs,
         "--json", *extra], cwd=str(site), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True)
    if expect is not None:
        assert proc.returncode == expect, proc.stdout + proc.stderr
    return json.loads(proc.stdout), proc


@needs_sphinx
def test_an_unchanged_tree_passes_even_though_both_sides_carry_the_same_old_warning(site):
    broken = A_RST + "\nSee :ref:`nolabel`.\n"
    (site / "content" / "a.rst").write_text(broken)
    _git(site, "commit", "-qam", "base with an old warning")
    (site / "content" / "a.rst").write_text("\n\n" + broken)  # same warning, moved lines
    res, _ = compare(site, expect=0)
    assert res["ok"] and all(not v["new"] for v in res["languages"].values())


@needs_sphinx
def test_a_warning_the_candidate_adds_fails_the_comparison_and_is_named(site):
    (site / "content" / "a.rst").write_text(A_RST + "\nSee :ref:`nolabel`.\n")
    res, _ = compare(site, expect=1)
    assert any("nolabel" in n for n in res["languages"]["en"]["new"])
    assert any("nolabel" in f for f in res["failures"])


@needs_sphinx
def test_a_warning_the_candidate_removes_is_reported_fixed_and_passes(site):
    (site / "content" / "a.rst").write_text(A_RST + "\nSee :ref:`nolabel`.\n")
    _git(site, "commit", "-qam", "warn")
    (site / "content" / "a.rst").write_text(A_RST)
    res, _ = compare(site, expect=0)
    assert any("nolabel" in f for f in res["languages"]["en"]["fixed"])


@needs_sphinx
def test_a_candidate_that_no_longer_builds_fails_even_with_no_warning_lines(site):
    (site / "content" / "conf.py").write_text(CONF + "raise RuntimeError('boom')\n")
    res, _ = compare(site, langs="en", expect=1)
    assert res["languages"]["en"]["cand_succeeded"] is False
    assert res["languages"]["en"]["base_succeeded"] is True


@needs_sphinx
def test_without_make_variables_the_build_runs_sphinx_build_with_the_language(site):
    res, _ = compare(site, expect=0)
    assert {b["mode"] for b in res["builds"]} == {"sphinx-build"}
    assert Path(res["cand_html"]["vi"], "index.html").is_file()


@needs_sphinx
def test_the_repos_make_variables_are_used_and_the_build_lands_in_the_work_dir(site):
    (site / "Makefile").write_text(
        "CURRENT_LANG ?= en\nBUILD_DIR ?= _build\nhtml:\n"
        "\tpython -m sphinx -q -b html -D language=$(CURRENT_LANG) content $(BUILD_DIR)/html\n")
    res, _ = compare(site, expect=0)
    assert {b["mode"] for b in res["builds"]} == {"make"}
    assert res["cand_html"]["vi"].startswith(res["work_dir"])
    assert not (site / "_build").exists()


@needs_sphinx
def test_the_default_work_dir_is_scratch_under_the_state_root_and_clean_removes_it(site):
    res, _ = compare(site, langs="en", expect=0)
    work = Path(res["work_dir"])
    assert str(work).startswith(str(site.parent / "home" / "scratch" / "docs-site"))
    assert work.is_dir()
    done = subprocess.run([DOCS_PYTHON, str(MODULE), "clean", "--work-dir", str(work)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert done.returncode == 0 and not work.exists()


@needs_sphinx
def test_the_translated_build_is_proven_to_pick_the_language_image(site):
    (site / "content" / "a.rst").write_text(A_RST + "\nMore text.\n")
    res, _ = compare(site, expect=0)
    rows = [r for r in res["images"] if r["lang"] == "vi"]
    assert rows and rows[0]["expected"] == ["pic.vi.png"] and rows[0]["missing"] == []


@needs_sphinx
def test_a_translated_build_that_ignores_the_language_variable_is_caught_by_the_image_check(site):
    (site / "Makefile").write_text(
        "CURRENT_LANG ?= en\nBUILD_DIR ?= _build\nhtml:\n"
        "\tpython -m sphinx -q -b html -D language=en content $(BUILD_DIR)/html\n")  # ignores it
    (site / "content" / "a.rst").write_text(A_RST + "\nMore text.\n")
    res, _ = compare(site, expect=1)
    assert any("pic.vi.png" in f for f in res["failures"])


@needs_sphinx
def test_untracked_new_pages_are_part_of_the_candidate_and_ignored_files_are_not(site):
    (site / ".gitignore").write_text("secret.rst\n")
    (site / "content" / "secret.rst").write_text("Secret\n======\n")  # ignored: not copied
    (site / "content" / "new.rst").write_text("New\n===\n\nText.\n")
    (site / "content" / "index.rst").write_text("Index\n=====\n\n.. toctree::\n\n   a\n   new\n")
    res, _ = compare(site, langs="en", expect=0)
    cand = Path(res["work_dir"], "cand", "content")
    assert (cand / "new.rst").is_file() and not (cand / "secret.rst").exists()
    assert "content/new.rst" in res["pages"]


@needs_sphinx
def test_no_doctrees_are_left_behind_but_the_html_is(site):
    res, _ = compare(site, expect=0)
    work = Path(res["work_dir"])
    left = [str(p) for p in work.rglob("*") if p.is_dir() and p.name in ("doctrees", ".doctrees")]
    assert left == []
    assert Path(res["cand_html"]["vi"], "index.html").is_file()


@needs_sphinx
def test_a_page_added_to_the_worktree_while_the_builds_run_is_not_looked_for_in_the_snapshot(site):
    late = site / "content" / "late.rst"
    (site / "Makefile").write_text(
        "CURRENT_LANG ?= en\nBUILD_DIR ?= _build\nhtml:\n"
        "\tprintf 'Late\\n====\\n' > %s\n"
        "\tpython -m sphinx -q -b html -D language=$(CURRENT_LANG) content $(BUILD_DIR)/html\n" % late)
    (site / "content" / "a.rst").write_text(A_RST + "\nMore text.\n")
    res, proc = compare(site, expect=0)
    assert "Traceback" not in proc.stderr
    assert res["pages"] == ["content/a.rst"] and late.is_file()


@needs_sphinx
def test_a_named_page_the_snapshot_lacks_is_one_failure_line_not_a_traceback(site):
    res, proc = compare(site, "--pages", "content/a.rst,content/ghost.rst", expect=1)
    assert "Traceback" not in proc.stderr
    assert res["failures"] == ["page content/ghost.rst is not in the candidate snapshot"]
    assert (Path(res["work_dir"]) / "compare.json").is_file()


@needs_sphinx
def test_compare_json_is_written_even_when_the_base_ref_cannot_be_exported(site):
    work = site.parent / "w"
    env = dict(os.environ, ODOO_AI_HOME=str(site.parent / "home"))
    proc = subprocess.run(
        [DOCS_PYTHON, str(MODULE), "--worktree", str(site), "--base-ref", "no-such-ref", "--langs", "en",
         "--work-dir", str(work), "--json"], cwd=str(site), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True)
    assert proc.returncode == 1 and "Traceback" not in proc.stderr
    assert json.loads((work / "compare.json").read_text())["cand_html"] == {}
