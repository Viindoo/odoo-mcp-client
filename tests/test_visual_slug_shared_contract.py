"""Issue class: run-scoped visual/*/<slug>/ sibling subpaths mint their own slug with no
shared, collision-proof derivation rule -- odoo-visual-regression got one (see
test_visual_regression_collision_and_retention.py); odoo-acceptance, odoo-debug, and
odoo-ui-review did not, and odoo-ui-review had no slug instruction at all.

Fix: ONE shared home (snippets/visual-evidence-lifecycle-contract.md) states the
`<intent-slug>-<YYYYMMDD>-<4 random chars>` derivation once; every skill that mints a
run-scoped visual/*/<slug>/ evidence path cites it instead of restating (or, in
odoo-ui-review's case, omitting) the rule.

Guard-the-class: any current or FUTURE skill that mints such a path without citing the
shared home reddens test_every_visual_slug_minting_skill_cites_the_shared_contract.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILLS_DIR = PLUGIN / "skills"

CONTRACT_REF = "visual-evidence-lifecycle-contract.md"
CONTRACT_PATH = PLUGIN / "snippets" / CONTRACT_REF

SLUG_PATH_RE = re.compile(r"visual/[a-zA-Z_-]+/<slug>")
DELEGATION_MARKER = "slug comes from"

SITES = {
    "odoo-visual-regression": "visual/current/<slug>/",
    "odoo-acceptance": "visual/qa/<slug>/",
    "odoo-debug": "visual/debug/<slug>/",
    "odoo-ui-review": "visual/screenshots/<slug>/",
}


def _skill_text(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    assert path.exists(), f"{name}/SKILL.md not found at {path}"
    return path.read_text(encoding="utf-8")


def test_shared_contract_file_exists():
    assert CONTRACT_PATH.exists(), (
        f"Expected the shared collision-proof slug-derivation home at {CONTRACT_PATH}"
    )


def test_shared_contract_states_the_derivation_formula():
    assert CONTRACT_PATH.exists(), f"Expected shared contract at {CONTRACT_PATH}"
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "<intent-slug>-<YYYYMMDD>-<4 random chars>" in text, (
        "Shared contract must state the exact derivation formula"
    )
    assert "phase-p-run-dag.md:43" in text, (
        "Shared contract must cite phase-p-run-dag.md:43 as the reused mechanism origin"
    )


def test_shared_contract_worked_example_shows_two_differing_derivations():
    assert CONTRACT_PATH.exists(), f"Expected shared contract at {CONTRACT_PATH}"
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    norm = re.sub(r"\s+", " ", text)
    m = re.search(
        r"`([a-z0-9-]+-20\d{6}-[a-z0-9]{4})`\s+and\s+`([a-z0-9-]+-20\d{6}-[a-z0-9]{4})`", norm
    )
    assert m, (
        "Expected a worked example pairing two concrete same-intent, same-day slugs of the "
        "shape '<intent>-<YYYYMMDD>-<4chars>' to prove two concurrent runs differ."
    )
    slug_a, slug_b = m.group(1), m.group(2)
    assert slug_a != slug_b, "the two example slugs must differ"
    assert slug_a.rsplit("-", 1)[0] == slug_b.rsplit("-", 1)[0], (
        "the two example slugs must share the SAME intent-slug + date prefix and differ "
        "ONLY in the random suffix"
    )


def test_four_sites_cite_the_shared_contract():
    missing = [name for name in SITES if CONTRACT_REF not in _skill_text(name)]
    assert not missing, (
        f"These skills must cite {CONTRACT_REF} for their run-scoped visual/*/<slug>/ "
        f"subpath's collision-proof slug derivation: {missing}"
    )


def test_every_visual_slug_minting_skill_cites_the_shared_contract():
    """Guard the CLASS: scan every skills/*/SKILL.md; any file that references a
    visual/<x>/<slug> evidence path and does not explicitly delegate slug sourcing
    elsewhere ("slug comes from ...") must cite the shared derivation contract. A NEW
    skill introducing a fresh visual/<new>/<slug>/ path with no citation reddens here."""
    failures = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        if SLUG_PATH_RE.search(text) and DELEGATION_MARKER not in text.lower():
            if CONTRACT_REF not in text:
                failures.append(str(skill_md.relative_to(PLUGIN)))
    assert not failures, (
        f"These skills mint a run-scoped visual/*/<slug>/ evidence path without citing "
        f"{CONTRACT_REF} (the shared collision-proof derivation home): {failures}"
    )
