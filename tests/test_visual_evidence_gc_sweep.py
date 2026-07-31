"""Issue class: run-scoped visual/*/<slug>/ evidence directories (qa/, debug/,
screenshots/) are RETAINED past their own run's terminal status (they are the cited
evidence behind a verdict/diagnosis) but nothing ever deletes them - an unbounded disk
leak, one directory per run, forever. visual/current/ already has a 24h crash-backstop
sweep (see test_visual_regression_collision_and_retention.py); this generalizes the
SAME orphan-sweep pattern to the three siblings with a longer, deliberate-retention
bound (they are meant to survive their own run, unlike the ephemeral current/ set).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILLS_DIR = PLUGIN / "skills"
CONTRACT_PATH = PLUGIN / "snippets" / "visual-evidence-lifecycle-contract.md"

BOUND_MINUTES = 43200  # 30 days

SWEEPS = {
    "odoo-acceptance": "visual/qa/",
    "odoo-debug": "visual/debug/",
    "odoo-ui-review": "visual/screenshots/",
}


def _text(skill_name: str) -> str:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    assert path.exists(), f"{skill_name}/SKILL.md not found at {path}"
    return path.read_text(encoding="utf-8")


def test_shared_contract_states_the_gc_bound_and_eligible_buckets():
    assert CONTRACT_PATH.exists(), f"Expected GC contract at {CONTRACT_PATH}"
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "30 days" in text and str(BOUND_MINUTES) in text, (
        "Shared contract must state the 30-day / 43200-minute retention bound"
    )
    assert re.search(r"(?i)SHARE reusable cache", text), (
        "Shared contract must explicitly exclude SHARE reusable caches from GC eligibility"
    )
    assert re.search(r"(?i)committed module deliverable", text), (
        "Shared contract must explicitly exclude committed module deliverables (bucket 3) "
        "from GC eligibility"
    )


def test_each_evidence_skill_sweeps_its_own_stale_siblings():
    for skill, subdir in SWEEPS.items():
        text = _text(skill)
        pattern = re.compile(
            rf"find <ISOLATE_DIR>/{re.escape(subdir)}.*-mmin \+{BOUND_MINUTES}.*-exec rm -rf"
        )
        assert pattern.search(text), (
            f"{skill}/SKILL.md must sweep stale {subdir}<slug>/ dirs with a bounded "
            f"'find ... -mmin +{BOUND_MINUTES} ... -exec rm -rf' orphan sweep"
        )


def test_each_evidence_skill_cites_the_shared_gc_contract():
    for skill in SWEEPS:
        text = _text(skill)
        assert "visual-evidence-lifecycle-contract.md" in text, (
            f"{skill}/SKILL.md must cite the shared GC contract for its orphan sweep"
        )


def test_sweep_runs_before_minting_the_skills_own_slug():
    """Concurrency protection: the sweep must be textually ordered before this run's
    OWN slug is minted, so it can never race with (or delete) the directory this same
    run is about to create."""
    for skill, subdir in SWEEPS.items():
        text = _text(skill)
        sweep_marker = f"find <ISOLATE_DIR>/{subdir}"
        mint_marker = "Generate one `slug`"
        sweep_pos = text.find(sweep_marker)
        mint_pos = text.find(mint_marker)
        assert sweep_pos != -1, f"{skill}/SKILL.md: sweep command not found"
        assert mint_pos != -1, f"{skill}/SKILL.md: slug-mint instruction not found"
        assert sweep_pos < mint_pos, (
            f"{skill}/SKILL.md: orphan sweep must be textually ordered BEFORE minting "
            "this run's own slug, so it can never race with the directory this run is "
            "about to create"
        )
