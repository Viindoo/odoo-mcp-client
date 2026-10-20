"""po_sync.py: keeping the gettext catalogs of a Sphinx docs repo in step with its pages.

Pure-function tests always run. The CLI tests need a python that has Sphinx and Babel (the docs
repo's own venv): this suite's venv is used when it has both, else $DOCS_SITE_TEST_PYTHON, else
those tests skip.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "plugins/odoo-ai-agents/scripts/lib/docs_site/po_sync.py"


def _load():
    spec = importlib.util.spec_from_file_location("po_sync_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


po_sync = _load()


def _has(python, *mods):
    code = "import importlib.util,sys;sys.exit(any(importlib.util.find_spec(m) is None for m in %r))" % (mods,)
    return subprocess.call([python, "-c", code]) == 0


def _docs_python():
    for cand in (sys.executable, os.environ.get("DOCS_SITE_TEST_PYTHON")):
        if cand and _has(cand, "sphinx", "babel"):
            return cand
    return None


DOCS_PYTHON = _docs_python()
needs_docs_python = pytest.mark.skipif(
    DOCS_PYTHON is None,
    reason="no python with Sphinx and Babel (the docs repo venv): set DOCS_SITE_TEST_PYTHON")


# --------------------------------------------------------------------------- pure functions
def test_a_page_maps_to_one_template_and_one_catalog_per_language():
    pot, po = po_sync.catalog_paths("content/guide/b.rst", "vi")
    assert pot == "locale/sources/guide/b.pot"
    assert po == "locale/vi/LC_MESSAGES/guide/b.po"
    assert po_sync.catalog_paths("./content/a.rst", "fr")[1] == "locale/fr/LC_MESSAGES/a.po"


@pytest.mark.parametrize("page", ["other/a.rst", "content/a.md", "content/../x.rst", "content/.rst"])
def test_a_page_outside_the_content_tree_is_refused(page):
    with pytest.raises(po_sync.SyncError):
        po_sync.page_to_docname(page)


def test_a_new_catalog_header_takes_the_language_and_drops_the_template_fuzzy_flag():
    model = ('# T\n#\n#, fuzzy\nmsgid ""\nmsgstr ""\n"Project-Id-Version: x\\n"\n'
             '"POT-Creation-Date: 2020-01-01 00:00+0000\\n"\n"Language-Team: LANGUAGE\\n"\n'
             '"MIME-Version: 1.0\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"')
    head = po_sync.shape_new_header(model, "vi", "2026-10-20 09:00+0700")
    assert "fuzzy" not in head
    assert po_sync.get_header_field(head, "Language") == "vi"
    assert po_sync.get_header_field(head, "POT-Creation-Date") == "2026-10-20 09:00+0700"
    assert po_sync.get_header_field(head, "Project-Id-Version") == "x"
    assert head.index('"Language: vi') < head.index('"MIME-Version')


def test_an_empty_language_header_is_replaced_not_duplicated():
    head = 'msgid ""\nmsgstr ""\n"Language: \\n"\n"MIME-Version: 1.0\\n"'
    fixed = po_sync.set_header_field(head, "Language", "vi")
    assert fixed.count('"Language:') == 1
    assert po_sync.get_header_field(fixed, "Language") == "vi"


def test_line_width_is_read_from_the_repos_catalog_tooling_else_76():
    assert po_sync.detect_width(["translate:\n\tsphinx-intl update -p x -l vi -w 120\n"]) == 120
    assert po_sync.detect_width(["write_po(f, cat, width=100)\n"]) == 100
    assert po_sync.detect_width(["html:\n\tsphinx-build -w warnings.txt\n"]) == 76
    assert po_sync.detect_width([]) == 76


def test_template_locations_do_not_depend_on_the_directory_it_was_built_in(tmp_path):
    repo = tmp_path / "repo"
    built_a = tmp_path / "cache" / "a" / "pot"
    built_b = tmp_path / "other" / "deeper" / "pot"
    for built in (built_a, built_b):
        built.mkdir(parents=True)
    canonical = str(repo / "locale" / "sources")

    def pot_for(built):
        rel = os.path.relpath(str(repo / "content" / "a.rst"), str(built))
        return "msgid \"\"\n\n#: %s:2 %s:9\nmsgid \"x\"\nmsgstr \"\"\n" % (rel, rel)

    one = po_sync.rewrite_locations(pot_for(built_a), str(built_a), canonical)
    two = po_sync.rewrite_locations(pot_for(built_b), str(built_b), canonical)
    assert one == two
    assert "#: ../../content/a.rst:2 ../../content/a.rst:9" in one


def test_catalog_files_of_other_pages_are_reported_as_strays():
    allowed = {"locale/sources/a.pot", "locale/vi/LC_MESSAGES/a.po"}
    changed = {"locale/vi/LC_MESSAGES/a.po", "locale/vi/LC_MESSAGES/zzz.po", "locale/sources/b.pot"}
    assert po_sync.stray_locale_changes(changed, allowed) == [
        "locale/sources/b.pot", "locale/vi/LC_MESSAGES/zzz.po"]


def _msg(mid, string="", flags=()):
    return types.SimpleNamespace(id=mid, string=string, flags=set(flags))


def test_a_fuzzy_guess_is_never_counted_as_translated_and_an_empty_msgstr_is_untranslated():
    cat = [_msg("", "header"), _msg("Done", "Xong"), _msg("Guess", "Doan", {"fuzzy"}),
           _msg("Todo", ""), _msg("Todo2", "")]
    acc = po_sync.account(cat)
    assert (acc["entries"], acc["translated"], acc["fuzzy"]) == (4, 1, 1)
    assert acc["untranslated"] == ["Todo", "Todo2"]
    assert acc["fuzzy_msgids"] == ["Guess"]


def test_the_default_work_dir_is_scratch_under_the_plugin_state_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(tmp_path / "state"))
    path = po_sync.work_dir_for(str(tmp_path / "repo"), "po-sync")
    assert path.startswith(str(tmp_path / "state" / "scratch" / "docs-site") + os.sep)
    assert path.endswith(os.sep + "po-sync")
    assert po_sync.work_dir_for(str(tmp_path / "repo"), "po-sync", str(tmp_path / "w")) == str(tmp_path / "w")


def test_a_work_dir_holding_someone_elses_files_is_neither_wiped_nor_deleted(tmp_path):
    mine = tmp_path / "keep"
    mine.mkdir()
    (mine / "precious.txt").write_text("x")
    with pytest.raises(po_sync.SyncError):
        po_sync.claim_work_dir(str(mine))
    with pytest.raises(po_sync.SyncError):
        po_sync.clean_work_dir(str(mine))
    assert (mine / "precious.txt").is_file()


def test_a_claimed_work_dir_is_emptied_on_reuse_and_removed_by_clean(tmp_path):
    work = tmp_path / "w"
    po_sync.claim_work_dir(str(work))
    (work / "stale.log").write_text("old")
    po_sync.claim_work_dir(str(work))
    assert not (work / "stale.log").exists()
    assert po_sync.clean_work_dir(str(work)) is True
    assert not work.exists()
    assert po_sync.clean_work_dir(str(work)) is False


def test_cleaning_a_default_work_dir_also_removes_its_empty_hash_parent_but_never_another_tools_dir(
        tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(tmp_path / "state"))
    repo = str(tmp_path / "repo")
    mine = po_sync.claim_work_dir(po_sync.work_dir_for(repo, "po-sync"))
    other = po_sync.claim_work_dir(po_sync.work_dir_for(repo, "build-compare"))
    hash_dir = os.path.dirname(mine)
    assert po_sync.clean_work_dir(mine) is True
    assert os.path.isdir(other)                       # the sibling tool's work dir keeps the parent alive
    assert po_sync.clean_work_dir(other) is True
    assert not os.path.exists(hash_dir)
    assert os.path.isdir(str(tmp_path / "state" / "scratch" / "docs-site"))


def test_cleaning_an_explicit_work_dir_never_removes_the_directory_around_it(tmp_path):
    outer = tmp_path / "outer"
    work = po_sync.claim_work_dir(str(outer / "w"))
    assert po_sync.clean_work_dir(work) is True
    assert outer.is_dir()


def test_a_missing_babel_exits_3_with_a_one_line_remedy():
    code = ("import sys; sys.modules['babel'] = None; sys.path.insert(0, %r); import po_sync; "
            "sys.exit(po_sync.main(['verify','--worktree','.','--base-ref','HEAD',"
            "'--pages','content/a.rst','--langs','vi']))" % str(MODULE.parent))
    proc = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    assert proc.returncode == 3
    assert len(proc.stderr.strip().splitlines()) == 1
    assert "requirements.txt" in proc.stderr


# --------------------------------------------------------------------------- CLI behaviour
def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@example.test", "-c", "user.name=t", "-C", str(cwd)]
                   + list(args), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def docs(tmp_path):
    repo = tmp_path / "docs"
    (repo / "content" / "guide").mkdir(parents=True)
    (repo / "content" / "conf.py").write_text(
        "project = 'x'\nlanguage = 'en'\nlocale_dirs = ['../locale/']\ngettext_compact = False\n")
    (repo / "content" / "index.rst").write_text(
        "Index\n=====\n\n.. toctree::\n\n   a\n   guide/b\n")
    (repo / "content" / "a.rst").write_text("Page A\n======\n\nSome text here.\n\nSecond para.\n")
    (repo / "content" / "guide" / "b.rst").write_text("Page B\n======\n\nOther page text.\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def run(docs, *args, expect=None):
    env = dict(os.environ, ODOO_AI_HOME=str(docs.parent / "home"))
    proc = subprocess.run([DOCS_PYTHON, str(MODULE)] + list(args), cwd=str(docs), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if expect is not None:
        assert proc.returncode == expect, proc.stdout + proc.stderr
    return proc


def generate(docs, pages="content/a.rst", langs="vi", expect=0):
    proc = run(docs, "generate", "--worktree", str(docs), "--pages", pages, "--langs", langs,
               "--json", expect=expect)
    return json.loads(proc.stdout)


def po_of(docs, name="a"):
    return docs / "locale" / "vi" / "LC_MESSAGES" / (name + ".po")


@needs_docs_python
def test_generate_touches_only_the_catalogs_of_the_given_pages(docs):
    report = generate(docs)
    assert po_of(docs).is_file() and (docs / "locale/sources/a.pot").is_file()
    assert not po_of(docs, "guide/b").exists()
    assert not (docs / "locale/sources/guide/b.pot").exists()
    assert not (docs / "locale/sources/index.pot").exists()
    rep = report["pages"][0]["catalogs"]["vi"]
    assert rep["untranslated"] == ["Page A", "Some text here.", "Second para."]
    assert rep["fuzzy"] == 0 and rep["translated"] == 0


@needs_docs_python
def test_a_new_catalog_carries_the_language_and_the_templates_locations_relative_to_the_repo(docs):
    generate(docs)
    text = po_of(docs).read_text()
    assert '"Language: vi\\n"' in text
    assert "#: ../../content/a.rst:2" in text
    assert str(docs.parent) not in text


@needs_docs_python
def test_a_new_catalog_copies_the_header_shape_of_its_sibling(docs):
    generate(docs, pages="content/guide/b.rst")
    sib = po_of(docs, "guide/b")
    sib.write_text(sib.read_text().replace("Last-Translator: FULL NAME <EMAIL@ADDRESS>",
                                           "Last-Translator: Docs Team"))
    generate(docs, pages="content/guide/b.rst")  # untouched sibling stays as is
    generate(docs, pages="content/a.rst")
    head = po_of(docs).read_text().split("\n\n")[0]
    # the sibling here is in a sub dir: it is found through the language root
    assert "Last-Translator: Docs Team" in head
    assert "Language: vi" in head


@needs_docs_python
def test_existing_translations_survive_a_refresh_and_a_changed_source_line_is_not_guessed_fuzzy(docs):
    generate(docs)
    spec = docs / "spec.json"
    spec.write_text(json.dumps([{"msgid": "Page A", "msgstr": "Trang A"},
                                {"msgid": "Some text here.", "msgstr": "Mot doan van."}]))
    run(docs, "fill", "--po", str(po_of(docs)), "--spec", str(spec), expect=0)
    (docs / "content" / "a.rst").write_text(
        "Page A\n======\n\nSome text here!\n\nSecond para.\n")  # near-identical msgid
    report = generate(docs)
    text = po_of(docs).read_text()
    rep = report["pages"][0]["catalogs"]["vi"]
    assert 'msgstr "Trang A"' in text
    assert rep["fuzzy"] == 0 and "fuzzy" not in text
    assert "Some text here!" in rep["untranslated"]
    assert "Mot doan van." not in text  # the old entry is gone, not carried over by similarity


@needs_docs_python
def test_a_refresh_without_source_changes_rewrites_nothing(docs):
    generate(docs)
    run(docs, "fill", "--po", str(po_of(docs)), "--spec", _spec(docs, {"Page A": "Trang A"}), expect=0)
    before = (po_of(docs).read_bytes(), (docs / "locale/sources/a.pot").read_bytes())
    report = generate(docs)
    assert (po_of(docs).read_bytes(), (docs / "locale/sources/a.pot").read_bytes()) == before
    assert report["pages"][0]["pot_written"] is False
    assert report["pages"][0]["catalogs"]["vi"]["written"] is False


@needs_docs_python
def test_an_empty_language_header_is_repaired_when_the_page_is_refreshed(docs):
    generate(docs)
    po_of(docs).write_text(po_of(docs).read_text().replace('"Language: vi\\n"', '"Language: \\n"'))
    generate(docs)
    assert '"Language: vi\\n"' in po_of(docs).read_text()


def _spec(docs, mapping):
    path = docs / "spec.json"
    path.write_text(json.dumps([{"msgid": k, "msgstr": v} for k, v in mapping.items()]))
    return str(path)


@needs_docs_python
def test_fill_clears_the_fuzzy_flag_of_the_entries_it_sets_and_no_other(docs):
    generate(docs)
    po = po_of(docs)
    text = po.read_text()
    text = text.replace('msgid "Page A"\nmsgstr ""', '#, fuzzy\nmsgid "Page A"\nmsgstr "Tran A"')
    text = text.replace('msgid "Second para."\nmsgstr ""', '#, fuzzy\nmsgid "Second para."\nmsgstr "Doan 2"')
    po.write_text(text)
    run(docs, "fill", "--po", str(po), "--spec", _spec(docs, {"Page A": "Trang A"}), expect=0)
    out = po.read_text()
    assert 'msgstr "Trang A"' in out
    assert out.count("#, fuzzy") == 1 and '"Doan 2"' in out


@needs_docs_python
def test_fill_with_an_unknown_msgid_changes_nothing_and_fails(docs):
    generate(docs)
    before = po_of(docs).read_bytes()
    proc = run(docs, "fill", "--po", str(po_of(docs)),
               "--spec", _spec(docs, {"Page A": "Trang A", "No such text": "x"}), expect=1)
    assert "No such text" in proc.stdout
    assert po_of(docs).read_bytes() == before


def _translate_all(docs, name="a", mapping=None):
    po = po_of(docs, name)
    mapping = mapping or {}
    rep = json.loads(run(docs, "verify", "--worktree", str(docs), "--base-ref", "HEAD",
                         "--pages", "content/%s.rst" % name, "--langs", "vi", "--allow-untranslated",
                         "--json").stdout)
    todo = rep["catalogs"]["locale/vi/LC_MESSAGES/%s.po" % name]["untranslated"]
    run(docs, "fill", "--po", str(po), "--spec",
        _spec(docs, {m: mapping.get(m, "VI " + m) for m in todo}), expect=0)


def verify(docs, *extra, expect=None):
    return run(docs, "verify", "--worktree", str(docs), "--base-ref", "HEAD", "--pages",
               "content/a.rst", "--langs", "vi", "--json", *extra, expect=expect)


@needs_docs_python
def test_verify_passes_a_fully_translated_page_and_fails_while_entries_are_untranslated(docs):
    generate(docs)
    proc = verify(docs, expect=1)
    res = json.loads(proc.stdout)
    assert res["catalogs"]["locale/vi/LC_MESSAGES/a.po"]["untranslated"]
    verify(docs, "--allow-untranslated", expect=0)
    _translate_all(docs)
    assert json.loads(verify(docs, expect=0).stdout)["ok"] is True


@needs_docs_python
def test_verify_fails_on_a_fuzzy_entry_even_when_it_has_a_translation(docs):
    generate(docs)
    _translate_all(docs)
    po = po_of(docs)
    po.write_text(po.read_text().replace('msgid "Page A"', '#, fuzzy\nmsgid "Page A"'))
    res = json.loads(verify(docs, expect=1).stdout)
    assert any("fuzzy" in f for f in res["failures"])


@needs_docs_python
def test_verify_fails_when_the_language_header_is_empty_or_wrong(docs):
    generate(docs)
    _translate_all(docs)
    po = po_of(docs)
    for bad in ('"Language: \\n"', '"Language: fr\\n"'):
        po.write_text(po.read_text().replace('"Language: vi\\n"', bad))
        res = json.loads(verify(docs, expect=1).stdout)
        assert any("Language" in f for f in res["failures"])
        po.write_text(po.read_text().replace(bad, '"Language: vi\\n"'))


@needs_docs_python
def test_verify_fails_when_another_pages_catalog_changed_even_if_untracked(docs):
    generate(docs)
    _translate_all(docs)
    generate(docs, pages="content/guide/b.rst")
    res = json.loads(verify(docs, expect=1).stdout)
    assert "locale/vi/LC_MESSAGES/guide/b.po" in res["outside_pages"]
    assert "locale/sources/guide/b.pot" in res["outside_pages"]


@needs_docs_python
def test_verify_reports_an_unparsable_catalog(docs):
    generate(docs)
    po_of(docs).write_text(po_of(docs).read_text().replace(
        "charset=UTF-8", "charset=bogus"))
    res = json.loads(verify(docs, "--allow-untranslated", expect=1).stdout)
    assert res["catalogs"]["locale/vi/LC_MESSAGES/a.po"]["parse_error"]


@needs_docs_python
def test_generate_reports_its_work_dir_under_the_state_root_and_clean_removes_it(docs):
    report = generate(docs)
    work = Path(report["work_dir"])
    assert str(work).startswith(str(docs.parent / "home" / "scratch" / "docs-site"))
    assert work.is_dir()
    run(docs, "clean", "--work-dir", str(work), expect=0)
    assert not work.exists()


@needs_docs_python
def test_clean_by_worktree_finds_the_default_work_dir_and_leaves_the_repo_alone(docs):
    work = Path(generate(docs)["work_dir"])
    run(docs, "clean", "--worktree", str(docs), expect=0)
    assert not work.exists()
    assert po_of(docs).is_file()


POT_WITH_ZERO_LINE = (
    'msgid ""\nmsgstr ""\n"Project-Id-Version: x\\n"\n"POT-Creation-Date: 2020-01-01 00:00+0000\\n"\n'
    '"Language: \\n"\n"MIME-Version: 1.0\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
    '#: ../../content/a.rst:0\nmsgid "Hello"\nmsgstr ""\n\n#: ../../content/a.rst:3\nmsgid "World"\nmsgstr ""\n')


@needs_docs_python
def test_a_template_location_with_line_zero_does_not_make_an_unchanged_catalog_rewrite_itself(tmp_path):
    code = (
        "import sys, json; sys.path.insert(0, %r); import po_sync; "
        "pot = open(sys.argv[1], encoding='utf-8').read(); out = []\n"
        "for _ in range(3):\n"
        "    rep, written = po_sync.merge_catalog(pot, sys.argv[2], 'vi', 76, sys.argv[3])\n"
        "    out.append(written)\n"
        "print(json.dumps(out))" % str(MODULE.parent))
    pot = tmp_path / "a.pot"
    pot.write_text(POT_WITH_ZERO_LINE, encoding="utf-8")
    po = tmp_path / "vi" / "a.po"
    po.parent.mkdir()
    proc = subprocess.run([DOCS_PYTHON, "-c", code, str(pot), str(po), str(po.parent)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [True, False, False]       # created once, then left alone


@needs_docs_python
def test_verify_ignores_the_fuzzy_flag_of_the_catalog_header_but_not_of_an_entry(docs):
    generate(docs)
    _translate_all(docs)
    po = po_of(docs)
    original = po.read_text()
    po.write_text(original.replace('msgid ""\nmsgstr ""', '#, fuzzy\nmsgid ""\nmsgstr ""', 1))
    res = json.loads(verify(docs, expect=0).stdout)
    assert res["ok"] is True and res["catalogs"]["locale/vi/LC_MESSAGES/a.po"]["header_fuzzy"] is True
    po.write_text(original.replace('msgid "Page A"', '#, fuzzy\nmsgid "Page A"'))
    assert json.loads(verify(docs, expect=1).stdout)["catalogs"]["locale/vi/LC_MESSAGES/a.po"]["fuzzy"] == 1


@needs_docs_python
def test_clean_by_worktree_also_removes_the_hash_directory_it_leaves_empty(docs):
    work = Path(generate(docs)["work_dir"])
    run(docs, "clean", "--worktree", str(docs), expect=0)
    assert not work.parent.exists()
