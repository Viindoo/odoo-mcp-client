"""README/SKILL.md phase-parity guard for the forward-port and modules-upgrade pipelines.

No test previously enforced that the plugin README's per-pipeline mermaid diagram and phase
table stay in lockstep with the phase set the governing SKILL.md actually declares. That gap
is exactly how a SKILL.md-only phase addition (a new mandatory P9.5) shipped without its
README row/node - the drift compiled clean because nothing read the two files together.

This test extracts the phase anchors (P0, P9.5, P1d, ...) straight from each SKILL.md's own
bold phase headers - the SSOT for "what phases this pipeline has" - and asserts the README's
matching '### <pipeline> pipeline' section (both the mermaid diagram node labels and the
phase table's leading column) documents exactly that same set: no phase missing, none
stale/renamed/phantom.

Regex note: anchors are extracted from the START of a bold span / table cell / diagram node
label (`\\*\\*P9.5 - ...`, `| P9.5 ...`, `["P9.5 - ...`) rather than via a literal substring
search, so a phase mention that merely appears somewhere in running prose (e.g. "P9
provisions the instance the P9.5 dispatch reuses") is never mistaken for that phase's own
declaration, and incidental line-wrapping cannot produce a tautological pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
README = PLUGIN / "README.md"

FORWARD_PORT_SKILL = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
MODULES_UPGRADE_SKILL = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"

# A phase anchor at the START of a bold span in SKILL.md: **P9.5 - ...**, **P1d Transitive...**.
# Deliberately anchored to "starts the bold span" (not "appears anywhere after **") so that a
# bold span like "**P2 also reconciles...**" still yields the (already-legitimate) anchor P2,
# never a phantom "P2also".
_SKILL_ANCHOR_RE = re.compile(r"\*\*(P\d+(?:\.\d+)?[a-z]?)\b")

# A phase anchor at the START of a markdown table row: "| P9.5 i18n reconcile | ...".
_TABLE_ANCHOR_RE = re.compile(r"^\|\s*(P\d+(?:\.\d+)?[a-z]?)\b", re.MULTILINE)

# A phase anchor at the START of a mermaid node/subgraph label: 'P9["P9.5 - i18n ...' or
# 'subgraph P1_grp["P1 - Intent extract ..."]'.
_DIAGRAM_ANCHOR_RE = re.compile(r'\[\s*"(P\d+(?:\.\d+)?[a-z]?)\b')


def _skill_phase_anchors(skill_md: Path) -> set[str]:
    text = skill_md.read_text(encoding="utf-8")
    return set(_SKILL_ANCHOR_RE.findall(text))


def _readme_pipeline_section(heading_prefix: str) -> str:
    """Return the README.md slice from '### <heading_prefix>' up to the next '### ' heading."""
    text = README.read_text(encoding="utf-8")
    start_match = re.search(r"^### " + re.escape(heading_prefix), text, re.MULTILINE)
    assert start_match, f"README.md has no '### {heading_prefix}' heading"
    tail = text[start_match.end():]
    next_heading = re.search(r"^### ", tail, re.MULTILINE)
    end = start_match.end() + (next_heading.start() if next_heading else len(tail))
    return text[start_match.start():end]


def _readme_table_anchors(section_text: str) -> set[str]:
    return set(_TABLE_ANCHOR_RE.findall(section_text))


def _readme_diagram_anchors(section_text: str) -> set[str]:
    mermaid_match = re.search(r"```mermaid\n(.*?)```", section_text, re.DOTALL)
    assert mermaid_match, "pipeline section is missing its ```mermaid fenced diagram"
    return set(_DIAGRAM_ANCHOR_RE.findall(mermaid_match.group(1)))


PIPELINE_CASES = [
    pytest.param(FORWARD_PORT_SKILL, "Forward-port pipeline", id="forward-port"),
    pytest.param(MODULES_UPGRADE_SKILL, "Modules-upgrade pipeline", id="modules-upgrade"),
]


class TestReadmePipelinePhaseParity:
    """The README's per-pipeline section must document exactly the phase set its SKILL.md
    declares - neither fewer (a missing/stale phase) nor more (a phantom phase SKILL.md
    dropped), in BOTH the mermaid diagram and the phase table."""

    @pytest.mark.parametrize("skill_md, heading", PIPELINE_CASES)
    def test_readme_table_matches_skill_md_phase_set(self, skill_md: Path, heading: str) -> None:
        skill_anchors = _skill_phase_anchors(skill_md)
        section_text = _readme_pipeline_section(heading)
        readme_anchors = _readme_table_anchors(section_text)
        missing = skill_anchors - readme_anchors
        stale = readme_anchors - skill_anchors
        assert not missing and not stale, (
            f"README.md '### {heading}' phase TABLE drifted from {skill_md.relative_to(REPO_ROOT)}: "
            f"missing from README table: {sorted(missing)}; "
            f"stale/phantom in README table (absent from SKILL.md): {sorted(stale)}"
        )

    @pytest.mark.parametrize("skill_md, heading", PIPELINE_CASES)
    def test_readme_diagram_matches_skill_md_phase_set(self, skill_md: Path, heading: str) -> None:
        skill_anchors = _skill_phase_anchors(skill_md)
        section_text = _readme_pipeline_section(heading)
        readme_anchors = _readme_diagram_anchors(section_text)
        missing = skill_anchors - readme_anchors
        stale = readme_anchors - skill_anchors
        assert not missing and not stale, (
            f"README.md '### {heading}' mermaid DIAGRAM drifted from {skill_md.relative_to(REPO_ROOT)}: "
            f"missing from README diagram: {sorted(missing)}; "
            f"stale/phantom in README diagram (absent from SKILL.md): {sorted(stale)}"
        )
