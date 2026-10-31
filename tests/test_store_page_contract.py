"""The App Store page contract pinned by structure: the section map, the skeleton, the gate rule
names and the model tier of the landing work - never by what a model writes."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"

TEMPLATE = "skills/odoo-doc-illustration/references/app-store-template.md"
MARKETER = "agents/odoo-marketer.md"
GUARD = "skills/_shared/concurrency-guard.md"
WRITER_BRIEF = "skills/odoo-doc-illustration/references/writer-brief.md"

SECTION_KEYS = ["HERO", "WHAT-CHANGES", "VIDEO", "DAY-ONE", "INCLUDED", "FAQ", "TRY-AND-SUPPORT", "TECH"]


def _read(rel):
    return (PLUGIN / rel).read_text(encoding="utf-8")


def _between(text, start, end=None):
    """The text from the line starting with ``start`` up to the next line starting with ``end``."""
    head = text.index(start)
    tail = text.index(end, head + len(start)) if end else len(text)
    return text[head:tail]


def _section_two():
    return _between(_read(TEMPLATE), "## 2.", "\n## 3.")


def _skeleton():
    return _between(_read(TEMPLATE), "## 3.", "\n## 4.")


def test_the_section_map_is_the_eight_buyer_decision_steps_in_order():
    rows = re.findall(r"^\| (\d+) \| ([A-Z-]+) \|", _section_two(), re.M)
    assert [key for _, key in rows] == SECTION_KEYS
    assert [int(n) for n, _ in rows] == list(range(1, 9))


def test_the_skeleton_is_one_column_without_tabs():
    skeleton = _skeleton()
    assert "nav nav-tabs" not in skeleton
    assert "tab-content" not in skeleton


def test_the_video_section_uses_the_odoo_video_container():
    video = _between(_skeleton(), "<!-- VIDEO", "<!-- DAY-ONE")
    assert "media_iframe_video" in video
    assert "data-oe-expression" in video


def test_the_sanitizer_table_says_a_bare_iframe_is_stripped():
    rules = _between(_read(TEMPLATE), "## 1.", "\n## 2.")
    assert [line for line in rules.splitlines() if line.startswith("| No bare `<iframe>`") and "strips" in line]


def test_the_template_names_the_two_page_size_gate_rules():
    template = _read(TEMPLATE)
    assert "PAGE_TOO_LONG" in template
    assert "PAGE_TOO_MANY_IMAGES" in template


def test_the_marketer_landing_mode_names_the_two_page_size_gate_rules():
    landing = _between(_read(MARKETER), "## MODE landing", "\n## ")
    assert "PAGE_TOO_LONG" in landing
    assert "PAGE_TOO_MANY_IMAGES" in landing


def test_the_marketer_runs_on_opus():
    frontmatter = _between(_read(MARKETER), "---", "\n---")
    assert re.search(r"^model: opus$", frontmatter, re.M)


def test_the_marketer_never_writes_a_price_figure():
    never = _between(_read(MARKETER), "## Never")
    assert "price" in never


def _tier_row(name):
    return next(line for line in _read(GUARD).splitlines() if line.startswith(f"| **{name}**"))


def test_the_opus_tier_owns_the_landing_page():
    assert "landing page" in _tier_row("opus")


def test_the_sonnet_tier_does_not_own_the_landing_page():
    assert "landing page" not in _tier_row("sonnet")


def test_the_landing_launch_block_offers_opus_as_the_dispatch_model():
    block = _between(_read(WRITER_BRIEF), "## The landing launch", "\n## ")
    lines = [line for line in block.splitlines() if line.startswith("DISPATCH MODEL:")]
    assert lines and "opus" in lines[0]
