"""Guard (NR1 - TRIM, not just point): each moved planning fact ends up stated ONCE.

Business rule: the mandatory-planning refactor MOVED several facts to their SSOT and left the old
sites as short pointers. This test asserts the TRIM actually landed - the now-duplicated prose was
physically EXCISED, so each excised phrase appears AT MOST ONCE across the plugin tree (only at its
SSOT), never beside a fresh pointer.

Matching normalizes whitespace so a line-wrapped occurrence still counts (prose may re-wrap).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text)


def _count(phrase: str):
    """Return {relpath: count} for files where the whitespace-normalized phrase occurs."""
    needle = _norm(phrase)
    hits = {}
    exts = {".md", ".yaml", ".yml", ".txt"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            n = _norm(p.read_text(encoding="utf-8")).count(needle)
            if n:
                hits[str(p.relative_to(PLUGIN))] = n
    return hits


def test_trivial_inline_authoring_phrase_excised():
    """'writes it inline' / 'writes the inline micro-plan' authoring split must be gone."""
    for phrase in ("writes it inline", "writes the inline micro-plan", "write the inline light micro-plan"):
        hits = _count(phrase)
        total = sum(hits.values())
        assert total == 0, (
            f"Trivial-inline authoring phrase {phrase!r} must be excised everywhere; found: {hits}"
        )


def test_trivial_bypass_to_coding_sentence_excised():
    hits = _count("skips design and routes straight to `odoo-coding`")
    assert sum(hits.values()) == 0, (
        f"The intake trivial-bypass sentence must be excised; found: {hits}"
    )


def test_plan_mode_active_definition_stated_once():
    hits = _count("boolean dispatch-brief flag")
    assert sum(hits.values()) <= 1, (
        f"The plan_mode_active definition must be declared at most ONCE (its SSOT); found: {hits}"
    )
    assert list(hits) in ([], ["snippets/planning-gate-contract.md"]), (
        f"The plan_mode_active definition must live in planning-gate-contract.md; found: {hits}"
    )


def test_why_next_intake_rationale_stated_once():
    """The 'why next: odoo-intake, not run-harness' rationale (marker: 'strand every execution
    node') must survive at most once, at its SSOT (odoo-planning); planner + phase-p become
    pointers."""
    hits = _count("strand every execution node")
    assert sum(hits.values()) <= 1, (
        f"The why-next rationale must be stated at most ONCE (its SSOT); found: {hits}"
    )
    assert list(hits) in ([], ["skills/odoo-planning/SKILL.md"]), (
        f"The why-next rationale SSOT must be odoo-planning/SKILL.md; found: {hits}"
    )


def test_pointers_replaced_the_old_sites():
    """The former duplicate sites now POINT at their SSOT (measurably shorter = a pointer)."""
    planner = (PLUGIN / "agents" / "odoo-planner.md").read_text(encoding="utf-8")
    phase_p = (PLUGIN / "skills" / "odoo-intake" / "references" / "phase-p-run-dag.md").read_text(encoding="utf-8")
    for text, name in ((planner, "odoo-planner.md"), (phase_p, "phase-p-run-dag.md")):
        assert "odoo-planning/SKILL.md" in text and "Continuation Contract" in text, (
            f"{name} must point at odoo-planning/SKILL.md § Continuation Contract for the why-next "
            "rationale instead of restating it."
        )
