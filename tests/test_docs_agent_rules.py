"""The documentation agents' rules that a live run proved missing: presence of each mechanism by
its name, never the wording of a sentence."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"


def _read(rel):
    """The file with its line wraps folded, so a rule split over two lines still reads as one."""
    return re.sub(r"\s+", " ", (PLUGIN / rel).read_text(encoding="utf-8"))


def test_a_full_guide_is_gated_on_catalog_coverage():
    assert "doc_coverage_check.py" in _read("skills/odoo-doc-illustration/SKILL.md")
    assert "doc_coverage_check.py" in _read("skills/odoo-doc-illustration/references/doc-artifacts.md")
    assert "`coverage`" in _read("agents/odoo-doc-writer.md")
    assert (PLUGIN / "scripts/lib/doc_coverage_check.py").is_file()


def test_captures_hide_values_only_and_seed_empty_screens_through_the_ui():
    mech = _read("skills/_shared/doc-capture-mechanics.md")
    assert "What may be hidden" in mech and "cropped from the image file" in mech
    assert "THROUGH THE UI" in mech
    assert "`ui_user`" in mech and "`ui_user`" in _read("snippets/instance-handle-contract.md")


def test_menu_visibility_comes_from_the_menu_group_chain_with_a_live_check_per_role():
    assert "every parent up to the root" in _read("agents/odoo-doc-writer.md")
    assert "parent menu up to the root" in _read("skills/odoo-doc-illustration/references/doc-artifacts.md")
    assert "holding ONLY that role" in _read("agents/odoo-doc-writer.md")


def test_the_marketer_recaptures_on_this_build_and_writes_no_item_count():
    m = _read("agents/odoo-marketer.md")
    assert "EARLIER build" in m and "COUNT" in m


def test_every_docs_agent_states_the_no_git_rule_up_front():
    for rel in ("agents/odoo-doc-writer.md", "agents/odoo-marketer.md", "agents/odoo-doc-site-writer.md", "agents/odoo-planner.md"):
        text = _read(rel)
        body = text.split("---", 2)[2] if text.startswith("---") else text   # after the frontmatter
        head = " ".join(body.split(" ## ")[:4]).lower()                       # the intro + the first three sections
        assert "no git" in head or "not run git" in head or "do not run git" in head, rel


def test_the_writer_brief_states_where_guide_images_live_and_setup_checks_docutils():
    assert "static/description/assets/" in _read("skills/odoo-doc-illustration/references/writer-brief.md")
    assert "_have_docutils" in _read("scripts/setup-steps/05-prereq-check.sh")


def test_the_docs_site_check_shot_measures_a_page_of_the_same_kind_and_the_writer_checks_width_first():
    assert "SAME KIND" in _read("skills/odoo-doc-site/references/check-shot.md")
    assert "First page only" in _read("agents/odoo-doc-site-writer.md")
    acceptance = _read("skills/odoo-doc-site/references/acceptance.md")
    assert "LOCAL build" in acceptance and "UNVERIFIED" in acceptance.split("| 11 |", 1)[1].split("|", 3)[1]
