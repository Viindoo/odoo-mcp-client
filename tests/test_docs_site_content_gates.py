"""Behavior tests for scripts/lib/docs_site/content_gates.py - mechanical gates for a docs change.

Each rule is a promise about what may not reach a published page: a banned term, a version number in
prose, hand-set presentation, a link spelled so it breaks on the next branch, text baked into a
screenshot. A gate that cries wolf gets ignored, so the tests pin both sides of every rule: what it
must flag and the look-alike it must leave alone. A check that could not run (no network) is
UNVERIFIED and never a pass and never a failure.

Fixtures are tiny fake docs repos in a temp dir with a throw-away git history; the "image" files
are placeholder bytes and the text read off a screenshot comes in as a JSONL capture file.

Run with: python3 -m pytest tests/test_docs_site_content_gates.py -q
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from docs_site import PolicyError, content_gates as cg, load_policy  # noqa: E402

SCRIPT = LIB / "docs_site" / "content_gates.py"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")

CONF = "version = '17.0'\nrelease = '17.0'\nsupported_languages = {'en': 'English', 'vi': 'Vietnamese'}\n"


def git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=str(repo), env=env, check=True, capture_output=True, timeout=60)


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path):
    """A docs repo on branch 17.0 whose history ends at tag `base`; work is added after that."""
    root = tmp_path / "docs"
    root.mkdir()
    git(root, "init", "-q", "-b", "17.0")
    write(root, "conf.py", CONF)
    write(root, "Makefile", "LANGUAGES ?= vi\nBUILDDIR = _build/17.0\n")
    write(root, "content/old.rst", "Old\n===\n\nThis legacy page mentions Acme once.\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs: base")
    git(root, "tag", "base")
    return root


def policy(**kw):
    base = {"banned_terms": [], "banned_terms_exempt_paths": [], "forbid_version_prose": False,
            "series_list": [], "marketplace_url": "", "site_url_prefix": "", "semantic_classes": []}
    base.update(kw)
    return base


def gate(repo, pol, **kw):
    return cg.run_gates(str(repo), "base", pol, **kw)


def found(report, rule=None):
    return [(f["rule"], f["file"], f["line"]) for f in report["findings"] if rule is None or f["rule"] == rule]


# ----------------------------------------------------------------------------- scope

@needs_git
def test_only_files_added_or_modified_since_the_base_are_in_scope(repo):
    write(repo, "content/new.rst", "New\n===\n\nAcme again.\n")           # untracked new page
    write(repo, "content/old.rst", "Old\n===\n\nNothing now.\nAcme\n")       # modified
    report = gate(repo, policy(banned_terms=["Acme"]))
    assert sorted(report["scope"]["files"]) == ["content/new.rst", "content/old.rst"]
    untouched = gate(repo, policy(banned_terms=["Acme"]), added_only=False)
    assert "conf.py" not in untouched["scope"]["files"]


@needs_git
def test_a_page_committed_after_the_base_is_in_scope_like_an_uncommitted_one(repo):
    write(repo, "content/committed.rst", "C\n=\n\nAcme.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs: add")
    assert found(gate(repo, policy(banned_terms=["Acme"]))) == [("BANNED_TERM", "content/committed.rst", 4)]


@needs_git
def test_a_legacy_line_in_a_modified_page_passes_added_only_but_a_new_line_does_not(repo):
    write(repo, "content/old.rst", "Old\n===\n\nThis legacy page mentions Acme once.\n\nNew Acme line.\n")
    full = gate(repo, policy(banned_terms=["Acme"]))
    added = gate(repo, policy(banned_terms=["Acme"]), added_only=True)
    assert [l for _r, _f, l in found(full)] == [4, 6]
    assert [l for _r, _f, l in found(added)] == [6]


# ----------------------------------------------------------------------------- BANNED_TERM

@needs_git
def test_a_banned_word_in_prose_is_a_finding_with_its_line_regardless_of_case(repo):
    write(repo, "content/p.rst", "P\n=\n\nWe sell it with ACME support.\n")
    assert found(gate(repo, policy(banned_terms=["acme"]))) == [("BANNED_TERM", "content/p.rst", 4)]


@needs_git
def test_a_banned_word_inside_a_longer_word_is_not_a_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\nAcmeville and Pacme are places.\n")
    assert found(gate(repo, policy(banned_terms=["Acme"]))) == []


@needs_git
def test_a_banned_term_in_code_literals_and_link_targets_is_not_prose(repo):
    write(repo, "content/p.rst", "P\n=\n\n"
          "Run ``acme-cli`` now.\n\n"
          ".. code-block:: bash\n\n   acme --help\n\n"
          "Example::\n\n   acme again\n\n"
          "See :doc:`/acme/page` and https://acme.example.invalid/x and "
          "`the site <https://acme.example.invalid>`_ and `the guide <acme/guide>`_.\n")
    assert found(gate(repo, policy(banned_terms=["acme"]))) == []


@needs_git
def test_a_banned_term_in_a_guilabel_is_prose_and_is_found(repo):
    write(repo, "content/p.rst", "P\n=\n\nClick :guilabel:`Acme Sync`.\n")
    assert found(gate(repo, policy(banned_terms=["acme"]))) == [("BANNED_TERM", "content/p.rst", 4)]


@needs_git
def test_a_multi_word_term_wrapped_over_two_lines_is_found_on_its_first_line(repo):
    write(repo, "content/p.rst", "P\n=\n\nThis is made by Acme\nCorp for you.\n")
    assert found(gate(repo, policy(banned_terms=["Acme Corp"]))) == [("BANNED_TERM", "content/p.rst", 4)]


@needs_git
def test_exempt_paths_are_not_scanned_for_banned_terms(repo):
    write(repo, "content/legal/terms.rst", "T\n=\n\nAcme is the licensor.\n")
    write(repo, "content/p.rst", "P\n=\n\nAcme.\n")
    report = gate(repo, policy(banned_terms=["Acme"], banned_terms_exempt_paths=["content/legal/**"]))
    assert found(report) == [("BANNED_TERM", "content/p.rst", 4)]


PO = """\
msgid ""
msgstr ""
"Language: vi\\n"

#: ../../content/p.rst:4
msgid "Acme is mentioned in the source text."
msgstr "Ban dich nay khong nhac ten."

msgid "Clean source"
msgstr "Cau dich co Acme trong do"
"""


@needs_git
def test_a_banned_term_in_a_msgstr_is_found_but_one_in_a_msgid_is_not(repo):
    write(repo, "locale/vi/LC_MESSAGES/p.po", PO)
    report = gate(repo, policy(banned_terms=["Acme"]))
    assert found(report) == [("BANNED_TERM", "locale/vi/LC_MESSAGES/p.po", 10)]


@needs_git
def test_the_po_header_and_obsolete_entries_are_not_translations_and_are_not_scanned(repo):
    write(repo, "locale/vi/LC_MESSAGES/p.po",
          'msgid ""\nmsgstr ""\n"Project-Id-Version: Acme Docs\\n"\n"Language: vi\\n"\n\n'
          '#~ msgid "old"\n#~ msgstr "Acme cu"\n')
    assert found(gate(repo, policy(banned_terms=["Acme"]))) == []


def test_an_obsolete_po_entry_is_not_an_entry():
    from docs_site import parse_po
    entries = parse_po('msgid "a"\nmsgstr "b"\n\n#~ msgid "old"\n#~ msgstr "cu"\n')
    assert [e["msgid"] for e in entries] == ["a"]


# ----------------------------------------------------------------------------- VERSION_PROSE

@needs_git
def test_a_series_number_in_prose_is_a_finding_when_version_prose_is_forbidden(repo):
    write(repo, "content/p.rst", "P\n=\n\nThis works since 16.0 and in Odoo 17 too.\n")
    report = gate(repo, policy(forbid_version_prose=True, series_list=["16.0", "17.0"]))
    assert [(r, l) for r, _f, l in found(report)] == [("VERSION_PROSE", 4), ("VERSION_PROSE", 4)]
    assert sorted(f["match"] for f in report["findings"]) == ["16.0", "Odoo 17"]


@needs_git
def test_version_prose_is_not_checked_unless_the_policy_forbids_it(repo):
    write(repo, "content/p.rst", "P\n=\n\nThis works since 16.0.\n")
    assert found(gate(repo, policy(series_list=["16.0"]))) == []


@needs_git
def test_a_series_number_in_a_url_a_path_or_a_literal_is_not_version_prose(repo):
    write(repo, "content/p.rst", "P\n=\n\n"
          "See https://example.invalid/17.0/page and /opt/odoo/17.0/addons and ``--branch 17.0``.\n"
          "Open the 17.0/addons folder. A price of 117.05 and 17.05 is not a series.\n")
    assert found(gate(repo, policy(forbid_version_prose=True, series_list=["17.0"]))) == []


# ----------------------------------------------------------------------------- PRESENTATION

@needs_git
def test_a_pixel_width_on_a_screenshot_is_a_presentation_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. image:: img/01-a.jpg\n   :width: 600px\n\n"
          ".. figure:: img/02-b.jpg\n   :height: 40\n   :scale: 50 %\n")
    report = gate(repo, policy())
    assert [(r, l) for r, _f, l in found(report)] == [("PRESENTATION", 5), ("PRESENTATION", 8), ("PRESENTATION", 9)]


@needs_git
def test_a_youtube_iframe_size_is_not_a_presentation_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. youtube:: abc123\n   :width: 640\n   :height: 360\n\n"
          ".. raw:: html\n\n   <iframe width=\"560\" style=\"border:0\" src=\"https://video.invalid/embed/x\"></iframe>\n")
    assert found(gate(repo, policy())) == []


@needs_git
def test_a_style_attribute_in_raw_html_is_a_presentation_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. raw:: html\n\n   <p style=\"color: red\">Hi</p>\n")
    assert found(gate(repo, policy())) == [("PRESENTATION", "content/p.rst", 6)]


@needs_git
def test_a_colour_written_in_prose_is_a_finding_but_an_issue_number_is_not(repo):
    write(repo, "content/p.rst", "P\n=\n\nUse the colour #FF8800 or rgb(10, 20, 30).\n"
          "Fixes ticket #123 and ``#ff0000`` in code.\n")
    report = gate(repo, policy())
    assert sorted(f["match"] for f in report["findings"]) == ["#FF8800", "rgb("]


@needs_git
def test_theme_classes_written_by_hand_are_findings(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. image:: img/01-a.jpg\n   :class: img-fluid lazy\n")
    report = gate(repo, policy())
    assert sorted(f["match"] for f in report["findings"]) == ["img-fluid", "lazy"]


CSS = ".note-box{color:red}.btn-primary:hover{} .sm\\:flex{} a.link, /* .commented {} */ .x{background:url(a.png)}"


@needs_git
def test_a_class_missing_from_the_compiled_css_is_a_finding(repo, tmp_path):
    css = write(tmp_path, "built/theme.css", CSS)
    write(repo, "content/p.rst", "P\n=\n\n.. container:: note-box\n\n   text\n\n"
          ".. rst-class:: ghost-class\n\nPara.\n")
    report = gate(repo, policy(), built_css=str(css))
    assert [(r, l) for r, _f, l in found(report)] == [("PRESENTATION", 8)]
    assert report["findings"][0]["match"] == "ghost-class"


@needs_git
def test_a_class_outside_the_semantic_classes_is_a_finding_only_when_the_policy_lists_them(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. container:: note-box\n\n   text\n\n.. container:: other\n\n   text\n")
    assert found(gate(repo, policy())) == []
    report = gate(repo, policy(semantic_classes=["note-box"]))
    assert [(r, l) for r, _f, l in found(report)] == [("PRESENTATION", 8)]


def test_css_classes_are_read_from_selectors_not_from_values_or_comments():
    got = cg.css_classes(CSS)
    assert {"note-box", "btn-primary", "sm:flex", "link", "x"} <= got
    assert "commented" not in got and "png" not in got


# ----------------------------------------------------------------------------- HARDCODED_SITE_LINK

@needs_git
def test_a_link_spelled_with_the_site_prefix_in_an_added_line_is_a_finding(repo):
    write(repo, "content/old.rst", "Old\n===\n\nThis legacy page mentions Acme once.\n\n"
          "See `the guide <https://docs.example.invalid/17.0/guide.html>`_ or :doc:`/guide`.\n")
    report = gate(repo, policy(site_url_prefix="https://docs.example.invalid"))
    assert found(report) == [("HARDCODED_SITE_LINK", "content/old.rst", 6)]
    assert report["findings"][0]["match"] == "https://docs.example.invalid/17.0/guide.html"


@needs_git
def test_an_old_hardcoded_link_that_this_change_did_not_add_is_left_alone(repo):
    write(repo, "content/legacy.rst", "L\n=\n\nSee https://docs.example.invalid/old.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs: legacy")
    git(repo, "tag", "-f", "base")
    write(repo, "content/legacy.rst", "L\n=\n\nSee https://docs.example.invalid/old.\n\nMore text.\n")
    assert found(gate(repo, policy(site_url_prefix="https://docs.example.invalid"), added_only=True)) == []


# ----------------------------------------------------------------------------- MARKETPLACE_LINK

MARKET = "https://market.example.invalid/apps/{series}/{module}"


@needs_git
def test_a_marketplace_link_for_another_series_than_the_worktrees_is_a_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\nGet `Sales <https://market.example.invalid/apps/16.0/sale_x>`_ "
          "or `Stock <https://market.example.invalid/apps/17.0/stock_x>`_.\n")
    report = gate(repo, policy(marketplace_url=MARKET))
    assert found(report) == [("MARKETPLACE_LINK", "content/p.rst", 4)]
    assert report["findings"][0]["match"].endswith("16.0/sale_x")


@needs_git
def test_when_the_worktree_series_is_unknown_marketplace_series_is_unverified_not_guessed(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    git(root, "init", "-q", "-b", "work")
    write(root, "conf.py", "project = 'x'\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs: base")
    git(root, "tag", "base")
    write(root, "content/p.rst", "P\n=\n\nSee https://market.example.invalid/apps/16.0/sale_x.\n")
    report = gate(root, policy(marketplace_url=MARKET))
    assert report["findings"] == []
    assert report["unverified"][0]["rule"] == "MARKETPLACE_LINK"


class _Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(405 if self.path.endswith("nohead") else 404 if self.path.endswith("gone") else 200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def local_market():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_port
    server.shutdown()
    server.server_close()


@needs_git
def test_check_links_accepts_a_200_and_flags_a_404(repo, local_market):
    write(repo, "content/p.rst", "P\n=\n\nOk %s/apps/17.0/here\n\nGone %s/apps/17.0/gone\n"
          % (local_market, local_market))
    pol = policy(marketplace_url=local_market + "/apps/{series}/{module}")
    report = gate(repo, pol, check_links_flag=True)
    assert [(f["line"], f["detail"]) for f in report["findings"]] == [(6, "HTTP 404")]
    assert report["unverified"] == []
    assert gate(repo, pol)["findings"] == []          # no HEAD request without --check-links


@needs_git
def test_a_server_that_refuses_head_is_asked_with_get_before_the_link_is_called_broken(repo, local_market):
    write(repo, "content/p.rst", "P\n=\n\nSee %s/apps/17.0/nohead\n" % local_market)
    report = gate(repo, policy(marketplace_url=local_market + "/apps/{series}/{module}"), check_links_flag=True)
    assert report["findings"] == [] and report["unverified"] == []


@needs_git
def test_a_network_error_while_checking_a_link_is_unverified_not_a_failure(repo):
    write(repo, "content/p.rst", "P\n=\n\nDown http://127.0.0.1:1/apps/17.0/x\n")   # nothing listens
    pol = policy(marketplace_url="http://127.0.0.1:1/apps/{series}/{module}")
    report = gate(repo, pol, check_links_flag=True)
    assert report["findings"] == [] and report["ok"] is True
    assert report["unverified"][0]["reason"].startswith("network error")


# ----------------------------------------------------------------------------- reader-visible option text, URL tokens

@needs_git
def test_a_banned_term_in_a_path_or_url_token_is_not_a_prose_finding(repo):
    write(repo, "content/p.rst", "P\n=\n\nOpen /odoo?debug=1 or https://example.invalid/odoo/web "
          "or the web/odoo/login path to see it.\n")
    assert found(gate(repo, policy(banned_terms=["odoo"]))) == []


@needs_git
def test_the_same_term_written_as_a_word_beside_a_path_is_still_found(repo):
    write(repo, "content/p.rst", "P\n=\n\nOdoo opens /odoo?debug=1 for you.\n")
    report = gate(repo, policy(banned_terms=["odoo"]))
    assert [f["match"] for f in report["findings"]] == ["Odoo"]


@needs_git
def test_a_banned_term_in_alt_text_and_a_meta_description_is_found(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. meta::\n   :description: Learn Acme basics\n\n"
          ".. image:: img/a.png\n   :alt: The Acme dashboard\n   :class: o-img\n")
    assert found(gate(repo, policy(banned_terms=["Acme"]))) == [
        ("BANNED_TERM", "content/p.rst", 5), ("BANNED_TERM", "content/p.rst", 8)]


@needs_git
def test_a_figure_caption_legend_and_admonition_title_are_scanned(repo):
    write(repo, "content/p.rst", "P\n=\n\n.. figure:: img/a.png\n   :alt: plain\n\n   The Acme caption.\n\n"
          "   Legend: Acme again.\n\n.. admonition:: Acme warning\n\n   Body.\n")
    assert [l for _r, _f, l in found(gate(repo, policy(banned_terms=["Acme"])))] == [7, 9, 11]


@needs_git
def test_alt_text_on_a_line_the_change_did_not_add_is_skipped_with_added_only(repo):
    write(repo, "content/old.rst", "Old\n===\n\n.. image:: img/a.png\n   :alt: Acme legacy\n\n"
          "New line.\n\n.. image:: img/b.png\n   :alt: Acme new\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs: more")
    git(repo, "tag", "base2")
    write(repo, "content/old.rst", "Old\n===\n\n.. image:: img/a.png\n   :alt: Acme legacy\n\n"
          "New line.\n\n.. image:: img/b.png\n   :alt: Acme new\n\n.. image:: img/c.png\n   :alt: Acme c\n")
    report = cg.run_gates(str(repo), "base2", policy(banned_terms=["Acme"]), added_only=True)
    assert [l for _r, _f, l in found(report)] == [13]


# ----------------------------------------------------------------------------- captured screenshot text

def capture_file(tmp_path, *rows):
    path = tmp_path / "capture.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


@needs_git
def test_a_banned_term_in_text_captured_off_a_screenshot_is_a_finding_for_that_image(repo, tmp_path):
    write(repo, "content/img/01-a.vi.png", "x")
    write(repo, "content/img/02-b.vi.png", "x")
    cap = capture_file(tmp_path,
                       {"image": "content/img/01-a.vi.png", "lang": "vi", "text": "Dashboard\nPowered by Acme Corp\nSave"},
                       {"image": "content/img/02-b.vi.png", "lang": "vi", "text": "Nothing to see"})
    report = gate(repo, policy(banned_terms=["Acme Corp"]), capture_text=cap)
    assert found(report) == [("CAPTURE_BANNED_TERM", "content/img/01-a.vi.png", None)]
    assert report["findings"][0]["match"] == "Powered by Acme Corp"
    assert report["ok"] is False


@needs_git
def test_an_image_without_a_capture_record_is_listed_for_review_and_is_not_a_failure(repo, tmp_path):
    write(repo, "content/img/01-a.vi.png", "x")
    write(repo, "content/img/02-b.vi.png", "x")
    cap = capture_file(tmp_path, {"image": "content/img/01-a.vi.png", "lang": "vi", "text": "fine"})
    report = gate(repo, policy(banned_terms=["Acme"]), capture_text=cap)
    assert report["images_to_review"] == ["content/img/02-b.vi.png"]
    assert report["findings"] == [] and report["ok"] is True


@needs_git
def test_without_a_capture_file_every_image_in_scope_is_listed_for_review(repo):
    write(repo, "content/img/01-a.png", "x")
    report = gate(repo, policy(banned_terms=["Acme"]))
    assert report["images_to_review"] == ["content/img/01-a.png"] and report["ok"] is True
    assert any("IMAGES_TO_REVIEW content/img/01-a.png" in l for l in cg.summary(report))


@needs_git
def test_an_exempt_image_needs_neither_a_scan_nor_a_review(repo, tmp_path):
    write(repo, "content/legal/01-a.png", "x")
    cap = capture_file(tmp_path, {"image": "content/legal/01-a.png", "lang": "en", "text": "Acme"})
    report = gate(repo, policy(banned_terms=["Acme"], banned_terms_exempt_paths=["content/legal/**"]),
                  capture_text=cap)
    assert report["findings"] == [] and report["images_to_review"] == []
    bare = gate(repo, policy(banned_terms=["Acme"], banned_terms_exempt_paths=["content/legal/**"]))
    assert bare["images_to_review"] == []


@needs_git
def test_a_banned_word_inside_a_longer_captured_word_is_not_a_finding(repo, tmp_path):
    write(repo, "content/img/01-a.png", "x")
    cap = capture_file(tmp_path, {"image": "content/img/01-a.png", "lang": "en", "text": "Acmeville"})
    assert found(gate(repo, policy(banned_terms=["Acme"]), capture_text=cap)) == []


@needs_git
@pytest.mark.parametrize("body", ["not json", '{"image": "a.png"}', '{"image": "", "text": "x"}', '[1]'])
def test_a_malformed_capture_line_is_refused_not_ignored(repo, tmp_path, body):
    path = tmp_path / "capture.jsonl"
    path.write_text(body + "\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        gate(repo, policy(banned_terms=["Acme"]), capture_text=str(path))


@needs_git
def test_the_cli_takes_capture_text_and_prints_images_to_review(repo, tmp_path):
    write(repo, "content/img/01-a.png", "x")
    write(repo, "content/img/02-b.png", "x")
    cap = capture_file(tmp_path, {"image": "content/img/01-a.png", "lang": "en", "text": "Acme"})
    res = cli(repo, policy(banned_terms=["Acme"]), "--capture-text", cap)
    report = json.loads(res.stdout)
    assert res.returncode == 1 and report["counts"] == {"CAPTURE_BANNED_TERM": 1}
    assert report["images_to_review"] == ["content/img/02-b.png"]
    assert "IMAGES_TO_REVIEW content/img/02-b.png" in res.stderr


# ----------------------------------------------------------------------------- scope by pages, policy, CLI

@needs_git
def test_pages_scope_covers_the_page_its_catalogs_and_its_language_images(repo):
    write(repo, "content/a/p.rst", "P\n=\n\n.. image:: img/01-x.jpg\n")
    write(repo, "content/a/img/01-x.vi.jpg", "x")
    write(repo, "content/a/img/01-x.en.jpg", "x")
    write(repo, "locale/vi/LC_MESSAGES/a/p.po", PO)
    report = cg.run_gates(str(repo), None, policy(), pages=["content/a/p.rst"])
    assert report["scope"]["files"] == [
        "content/a/img/01-x.en.jpg", "content/a/img/01-x.vi.jpg", "content/a/p.rst",
        "locale/vi/LC_MESSAGES/a/p.po"]


@needs_git
def test_pages_scope_holds_the_plain_image_and_a_variant_whose_plain_file_is_absent(repo):
    write(repo, "content/a/p.rst", "P\n=\n\n.. image:: img/01-x.jpg\n\n.. image:: img/02-y.jpg\n")
    write(repo, "content/a/img/01-x.jpg", "x")           # plain only
    write(repo, "content/a/img/02-y.vi.jpg", "x")        # variant only
    report = cg.run_gates(str(repo), None, policy(), pages=["content/a/p.rst"])
    assert report["scope"]["images"] == ["content/a/img/01-x.jpg", "content/a/img/02-y.vi.jpg"]


def test_a_policy_value_of_the_wrong_type_is_refused(tmp_path):
    bad = write(tmp_path, "policy.json", json.dumps({"banned_terms": "acme"}))
    with pytest.raises(PolicyError):
        load_policy(str(bad))


def test_an_absent_policy_key_takes_the_rule_off(tmp_path):
    p = write(tmp_path, "policy.json", json.dumps({"banned_terms": ["x"]}))
    pol = load_policy(str(p))
    assert pol["forbid_version_prose"] is False and pol["site_url_prefix"] == ""


def cli(repo, pol, *args):
    p = write(repo.parent, "policy.json", json.dumps(pol))
    return subprocess.run([sys.executable, str(SCRIPT), "--worktree", str(repo), "--base-ref", "base",
                           "--policy", str(p), "--json", *args],
                          capture_output=True, text=True, timeout=120)


@needs_git
def test_the_cli_exits_1_with_a_json_report_when_a_gate_finds_something(repo):
    write(repo, "content/p.rst", "P\n=\n\nAcme.\n")
    res = cli(repo, policy(banned_terms=["Acme"]))
    assert res.returncode == 1
    report = json.loads(res.stdout)
    assert report["counts"] == {"BANNED_TERM": 1} and report["ok"] is False


@needs_git
def test_the_cli_exits_0_on_a_clean_change(repo):
    write(repo, "content/p.rst", "P\n=\n\nFine.\n")
    res = cli(repo, policy(banned_terms=["Acme"]))
    assert res.returncode == 0
    assert json.loads(res.stdout)["findings"] == []


@needs_git
def test_the_cli_exits_2_on_an_unreadable_base_ref(repo):
    p = write(repo.parent, "policy.json", "{}")
    res = subprocess.run([sys.executable, str(SCRIPT), "--worktree", str(repo), "--base-ref", "no-such-ref",
                          "--policy", str(p)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 2
