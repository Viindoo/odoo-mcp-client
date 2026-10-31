"""Forward-port manifest version rule C1: max(M + 1, S) for a module installable on both series,
the source version for a module dormant (installable False) at the target - and every restatement
of the rule says the same. Files are read fresh; only the rule's key phrases are asserted."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
STALE = ("installable modules only", "keeps the target's M")


def _read(rel):
    """The file with its line wraps folded, so a rule split over two lines still reads as one."""
    return re.sub(r"\s+", " ", (PLUGIN / rel).read_text(encoding="utf-8"))


def _between(text, start, end):
    """The text from `start` up to the next `end`, failing loudly when the anchor is gone."""
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_step_2a_gives_installable_modules_a_bump_and_dormant_modules_the_source_version():
    step = _between(_read("snippets/fp-merge-absorption.md"), "2a.", " 3. Adapt")
    assert "installable on both" in step and "max(M + 1, S)" in step
    assert "installable: False" in step or "installable_false=yes" in step
    assert "source version" in step.lower()
    assert "keeps the target's" not in step


def test_the_dormant_source_version_rule_reaches_every_restatement():
    lane_file = _read("snippets/fp-installable-false.md") + " ## "
    assert "source version" in _between(lane_file, "## LINT-ONLY LANE", " ## ")
    assert "source version" in _between(lane_file, "## A2", " ## ")
    pivots = _read("snippets/odoo-version-pivots.md")
    assert "dormant" in _between(pivots, "| Forward-port version", " | CORE")
    manifest = _read("snippets/new-module-manifest.md")
    assert "dormant" in manifest[manifest.index("| Forward-port, source bumped"):][:400]
    for rel in ("snippets/fp-installable-false.md", "snippets/odoo-version-pivots.md",
                "snippets/new-module-manifest.md", "snippets/fp-merge-absorption.md"):
        for stale in STALE:
            assert stale not in _read(rel), f"{rel} still says {stale!r}"


def test_the_readme_and_the_orchestration_entry_no_longer_limit_c1_to_installable_modules():
    for rel in ("README.md", "generator/skill_tool_deps.json"):
        assert "installable modules only)" not in _read(rel), rel
