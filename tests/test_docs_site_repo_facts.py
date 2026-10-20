"""Behavior tests for scripts/lib/docs_site/repo_facts.py - what a Sphinx docs repo states about itself.

The helper is read by an agent that writes a docs page; a wrong fact (the wrong series, a guessed
image directory, a translate target that silently rewrites every catalog) becomes a wrong page. So
each test states a fact the repo makes, builds a minimal fake docs repo that makes it, and asserts
the report says exactly that - and says UNKNOWN when the repo does not state it.

Run with: python3 -m pytest tests/test_docs_site_repo_facts.py -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from docs_site import repo_facts  # noqa: E402

SCRIPT = LIB / "docs_site" / "repo_facts.py"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")

CONF = """\
project = 'Docs'
version = '17.0'
release = '17.0'
extensions = ['sphinx.ext.intersphinx', 'custom_ext']
supported_languages = {'en': 'English', 'vi': 'Vietnamese'}
"""
MAKEFILE = "LANGUAGES ?= vi\nBUILDDIR = _build/17.0\n"


def git(repo, *args, when=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=str(repo), env=env, check=True, capture_output=True, timeout=60)


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def commit(repo, message, when="2024-01-01T00:00:00"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message, when=when)


@pytest.fixture
def repo(tmp_path):
    """A minimal docs repo on branch 17.0 with a conf.py, a Makefile and no content."""
    root = tmp_path / "docs"
    root.mkdir()
    git(root, "init", "-q", "-b", "17.0")
    write(root, "conf.py", CONF)
    write(root, "Makefile", MAKEFILE)
    write(root, "content/index.rst", "Docs\n====\n")
    commit(root, "docs: scaffold")
    return root


def collect(root, page=None):
    return repo_facts.collect(str(root), page)


# ----------------------------------------------------------------------------- series

@needs_git
def test_a_series_stated_the_same_by_conf_makefile_and_branch_is_reported_agreed(repo):
    facts = collect(repo)
    assert facts["series"] == "17.0"
    assert facts["series_agree"] is True
    assert facts["series_sources"] == {"conf_version": "17.0", "conf_release": "17.0",
                                       "makefile_builddir": "17.0", "branch": "17.0"}


@needs_git
def test_a_branch_naming_another_series_than_conf_py_breaks_agreement(repo):
    git(repo, "checkout", "-q", "-b", "18.0")
    facts = collect(repo)
    assert facts["series_agree"] is False
    assert facts["series"] == "UNKNOWN"          # two sources disagree: no guess which is right
    assert facts["series_sources"]["branch"] == "18.0"
    assert facts["series_sources"]["conf_version"] == "17.0"


@needs_git
def test_a_series_the_repo_does_not_state_is_unknown_not_guessed(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    git(root, "init", "-q", "-b", "work")
    write(root, "conf.py", "project = 'x'\n")
    facts = collect(root)
    assert facts["series"] == "UNKNOWN"
    assert facts["series_agree"] is False
    assert "series" in facts["unknown"]


def test_a_release_with_a_patch_number_still_names_its_series(tmp_path):
    write(tmp_path, "conf.py", "version = '17.0'\nrelease = '17.0.3'\n")
    assert collect(tmp_path)["series_sources"]["conf_release"] == "17.0"


# ----------------------------------------------------------------------------- languages and figures

def test_languages_are_gathered_from_makefile_conf_and_locale_dirs_without_sources(tmp_path):
    write(tmp_path, "conf.py", "supported_languages = {'en': 'English', 'fr': 'French'}\n")
    write(tmp_path, "Makefile", "LANGUAGES ?= vi fr\n")
    write(tmp_path, "locale/vi/LC_MESSAGES/a.po", 'msgid ""\nmsgstr ""\n')
    write(tmp_path, "locale/sources/a.pot", 'msgid ""\nmsgstr ""\n')
    langs = collect(tmp_path)["languages"]
    assert langs["makefile"] == ["vi", "fr"]
    assert langs["conf_supported_languages"] == ["en", "fr"]
    assert langs["locale_dirs"] == ["vi"]          # `sources` holds templates, not a language
    assert langs["all"] == ["en", "fr", "vi"]


def test_figure_language_filename_defaults_to_sphinxs_when_conf_py_is_silent(tmp_path):
    write(tmp_path, "conf.py", "project = 'x'\n")
    fig = collect(tmp_path)["figure_language_filename"]
    assert fig == {"value": "{root}.{language}{ext}", "source": "sphinx-default"}


def test_figure_language_filename_set_in_conf_py_wins_over_the_default(tmp_path):
    write(tmp_path, "conf.py", "figure_language_filename = '{path}{basename}-{language}{ext}'\n")
    fig = collect(tmp_path)["figure_language_filename"]
    assert fig == {"value": "{path}{basename}-{language}{ext}", "source": "conf.py"}


# ----------------------------------------------------------------------------- gettext hazards

REWRITING_CONF = """\
from sphinx_intl import basic
_orig = basic.update

def update_and_clean(locale_dir, pot_dir, languages, line_width=76, **kw):
    _orig(locale_dir, pot_dir, languages, line_width=line_width)
    for po in all_po(locale_dir):
        po.save()

basic.update = update_and_clean
"""


def test_a_conf_that_replaces_sphinx_intl_update_is_flagged_as_rewriting_every_po(tmp_path):
    write(tmp_path, "conf.py", REWRITING_CONF)
    facts = collect(tmp_path)
    assert facts["translate_target_rewrites_all_po"] is True
    assert any("basic.update" in e["text"] and e["file"] == "conf.py" for e in facts["rewrite_evidence"])


def test_a_plain_conf_is_not_flagged_as_rewriting_catalogs(tmp_path):
    write(tmp_path, "conf.py", CONF)
    facts = collect(tmp_path)
    assert facts["translate_target_rewrites_all_po"] is False
    assert facts["rewrite_evidence"] == []


def test_the_rewrite_hazard_in_an_extension_file_is_found_too(tmp_path):
    write(tmp_path, "conf.py", CONF)
    write(tmp_path, "extensions/po_tools.py", REWRITING_CONF)
    facts = collect(tmp_path)
    assert facts["translate_target_rewrites_all_po"] is True
    assert facts["rewrite_evidence"][0]["file"] == "extensions/po_tools.py"


def test_no_conf_py_means_the_hazard_is_unknown(tmp_path):
    assert collect(tmp_path)["translate_target_rewrites_all_po"] == "UNKNOWN"


def test_po_wrap_width_is_read_from_a_patch_argument_before_sampling(tmp_path):
    write(tmp_path, "conf.py", REWRITING_CONF.replace("line_width=76", "line_width=79"))
    write(tmp_path, "locale/vi/LC_MESSAGES/a.po", 'msgid ""\nmsgstr ""\n"Language: vi\\n"\n')
    assert collect(tmp_path)["po"]["wrap_width"] == {"value": 79, "source": "patch:conf.py"}


def test_po_wrap_width_is_sampled_from_a_sibling_catalog_when_no_patch_states_it(tmp_path):
    write(tmp_path, "conf.py", CONF)
    long_line = 'msgstr "' + "x" * 60 + '"'
    write(tmp_path, "locale/vi/LC_MESSAGES/a.po",
          '# a comment ' + "c" * 200 + '\nmsgid ""\n' + long_line + '\n')
    width = collect(tmp_path)["po"]["wrap_width"]
    assert width == {"value": len(long_line), "source": "sample"}   # comment lines do not count


def test_a_sibling_po_header_gives_language_and_generator(tmp_path):
    write(tmp_path, "conf.py", CONF)
    write(tmp_path, "locale/vi/LC_MESSAGES/a.po",
          'msgid ""\nmsgstr ""\n"Language: vi\\n"\n"Generated-By: Babel 2.14.0\\n"\n'
          '"Content-Type: text/plain; charset=UTF-8\\n"\n\nmsgid "Hi"\nmsgstr "Chao"\n')
    hdr = collect(tmp_path)["po"]["header_sample"]
    assert hdr["Language"] == "vi"
    assert hdr["Generated-By"] == "Babel 2.14.0"
    assert hdr["file"] == "locale/vi/LC_MESSAGES/a.po"


def test_a_repo_without_catalogs_reports_header_and_width_unknown(tmp_path):
    write(tmp_path, "conf.py", CONF)
    po = collect(tmp_path)["po"]
    assert po["wrap_width"]["value"] == "UNKNOWN"
    assert po["header_sample"]["Language"] == "UNKNOWN"


# ----------------------------------------------------------------------------- extensions

def test_directives_and_roles_registered_by_extension_files_are_listed(tmp_path):
    write(tmp_path, "conf.py", CONF)
    write(tmp_path, "extensions/custom_ext.py",
          "def setup(app):\n    app.add_directive('youtube', Youtube)\n"
          "    app.add_role('menu', menu_role)\n")
    ext = collect(tmp_path)["extensions"]
    assert ext["conf"] == ["sphinx.ext.intersphinx", "custom_ext"]
    assert ext["directives"] == ["youtube"]
    assert ext["roles"] == ["menu"]
    assert ext["files"] == ["extensions/custom_ext.py"]


# ----------------------------------------------------------------------------- page facts

CRM_PARENT = """\
CRM
===

.. toctree::
   :titlesonly:

   crm/lead
   Pipeline <crm/pipeline>
"""


@needs_git
def test_the_toctree_parent_is_the_rst_named_like_the_page_directory_and_says_if_it_lists_the_page(repo):
    write(repo, "content/applications/crm.rst", CRM_PARENT)
    write(repo, "content/applications/crm/lead.rst", "Lead\n====\n")
    write(repo, "content/applications/crm/forecast.rst", "Forecast\n========\n")
    commit(repo, "docs: crm")
    listed = collect(repo, "content/applications/crm/lead.rst")["page"]["toctree_parent"]
    assert listed["path"] == "content/applications/crm.rst"
    assert listed["listed"] is True
    titled = collect(repo, "content/applications/crm/pipeline.rst")["page"]["toctree_parent"]
    assert titled["listed"] is True                      # `Title <path>` entries count
    unlisted = collect(repo, "content/applications/crm/forecast.rst")["page"]["toctree_parent"]
    assert unlisted["path"] == "content/applications/crm.rst"
    assert unlisted["listed"] is False


@needs_git
def test_a_page_with_no_parent_toctree_file_reports_it_unknown(repo):
    write(repo, "content/loose/page.rst", "Page\n====\n")
    commit(repo, "docs: loose")
    parent = collect(repo, "content/loose/page.rst")["page"]["toctree_parent"]
    assert parent["path"] == "UNKNOWN"
    assert parent["listed"] == "UNKNOWN"


@needs_git
def test_the_image_dir_convention_of_siblings_is_applied_to_a_new_page_with_the_next_index(repo):
    write(repo, "content/applications/crm/lead.rst", ".. image:: img-lead/01-form.jpg\n")
    write(repo, "content/applications/crm/won.rst",
          ".. figure:: img-won/01-list.jpg\n\n.. image:: img-won/02-chart.jpg\n")
    write(repo, "content/applications/crm/img-lead/01-form.vi.jpg", "x")
    write(repo, "content/applications/crm/img-lead/03-old.vi.jpg", "x")
    commit(repo, "docs: crm")
    facts = collect(repo, "content/applications/crm/lost.rst")["page"]
    assert facts["convention"] == "img-<basename>"
    assert facts["image_dir"] == "content/applications/crm/img-lost"
    assert facts["image_dir_exists"] is False
    assert facts["next_image_index"] == 1


@needs_git
def test_next_image_index_continues_after_the_highest_number_in_the_pages_own_dir(repo):
    write(repo, "content/a/page.rst", ".. image:: img-page/01-one.jpg\n")
    write(repo, "content/a/img-page/01-one.en.jpg", "x")
    write(repo, "content/a/img-page/01-one.vi.jpg", "x")
    write(repo, "content/a/img-page/07-seven.vi.jpg", "x")
    commit(repo, "docs: a")
    facts = collect(repo, "content/a/page.rst")["page"]
    assert facts["image_dir"] == "content/a/img-page"
    assert facts["image_dir_source"] == "page"
    assert facts["next_image_index"] == 8


@needs_git
def test_a_shared_img_dir_convention_is_recognised(repo):
    write(repo, "content/a/one.rst", ".. image:: img/01-x.jpg\n")
    write(repo, "content/a/two.rst", ".. image:: img/02-y.jpg\n")
    write(repo, "content/a/img/02-y.vi.jpg", "x")
    commit(repo, "docs: a")
    facts = collect(repo, "content/a/three.rst")["page"]
    assert facts["convention"] == "img"
    assert facts["image_dir"] == "content/a/img"
    assert facts["next_image_index"] == 3


@needs_git
def test_with_no_images_in_the_area_the_image_dir_is_unknown(repo):
    write(repo, "content/a/one.rst", "Just text.\n")
    commit(repo, "docs: a")
    facts = collect(repo, "content/a/new.rst")["page"]
    assert facts["image_dir"] == "UNKNOWN"
    assert facts["next_image_index"] == "UNKNOWN"


@needs_git
def test_the_nearest_sibling_is_the_most_recently_changed_rst_in_the_same_directory(repo):
    write(repo, "content/a/old.rst", "Old\n===\n")
    commit(repo, "docs: old", when="2023-01-01T00:00:00")
    write(repo, "content/a/fresh.rst", "Fresh\n=====\n")
    commit(repo, "docs: fresh", when="2024-06-01T00:00:00")
    write(repo, "content/b/other.rst", "Other\n=====\n")   # another directory: never a sibling
    commit(repo, "docs: other", when="2025-01-01T00:00:00")
    near = collect(repo, "content/a/new.rst")["page"]["nearest_sibling_page"]
    assert near["path"] == "content/a/fresh.rst"


@needs_git
def test_menu_path_syntax_counts_decide_the_preferred_style(repo):
    arrow = "‣"
    write(repo, "content/a/one.rst", "Go to **Sales %s Orders** then **CRM %s Leads**.\n" % (arrow, arrow))
    write(repo, "content/a/two.rst", "Use :menuselection:`Sales --> Orders`.\n")
    commit(repo, "docs: a")
    syntax = collect(repo, "content/a/new.rst")["page"]["menu_path_syntax"]
    assert syntax["bold_arrow"] == 2
    assert syntax["menuselection"] == 1
    assert syntax["preferred"] == "bold_arrow"


@needs_git
def test_no_menu_paths_at_all_or_an_even_split_leaves_the_style_undecided(repo):
    write(repo, "content/a/one.rst", "Nothing to select here.\n")
    commit(repo, "docs: a")
    assert collect(repo, "content/a/new.rst")["page"]["menu_path_syntax"]["preferred"] == "UNKNOWN"
    write(repo, "content/a/two.rst", "Go to **Sales %s Orders**.\n\nOr :menuselection:`Sales --> Orders`.\n" % "\u2023")
    commit(repo, "docs: b")
    assert collect(repo, "content/a/new.rst")["page"]["menu_path_syntax"]["preferred"] == "UNKNOWN"


@needs_git
def test_the_last_ten_commit_subjects_are_sampled(repo):
    for i in range(12):
        write(repo, "content/n%d.rst" % i, "n\n=\n")
        commit(repo, "docs: page %d" % i, when="2024-02-%02dT00:00:00" % (i + 1))
    subjects = collect(repo, "content/n0.rst")["page"]["commit_subject_samples"]
    assert len(subjects) == 10
    assert subjects[0] == "docs: page 11"


# ----------------------------------------------------------------------------- CLI

def test_the_cli_prints_a_parseable_json_report_and_a_summary(tmp_path):
    write(tmp_path, "conf.py", CONF)
    res = subprocess.run([sys.executable, str(SCRIPT), "--worktree", str(tmp_path), "--json"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["series_sources"]["conf_version"] == "17.0"
    assert "series:" in res.stderr


def test_the_cli_refuses_a_worktree_that_is_not_a_directory(tmp_path):
    res = subprocess.run([sys.executable, str(SCRIPT), "--worktree", str(tmp_path / "nope")],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 2
