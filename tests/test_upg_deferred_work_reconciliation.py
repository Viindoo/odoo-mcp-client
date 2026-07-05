"""Behavioral guard for odoo-modules-upgrade's version-anchored deferred-work reconciliation.

Business rule: during a module upgrade to a TARGET Odoo major series X, custom-module
TODO/FIXME/XXX/HACK debt markers that carry a version anchor <= X (including an already-passed
lower version) have come DUE and must be executed NOW, in THIS upgrade, instead of slipping past
again. A marker anchored to a HIGHER future version stays DEFERRED (untouched); a marker with no
parseable version anchor is never forced into scope - it is recorded and flagged for the human.
DUE items are not a side note: they become real upgrade work-items, folded into the SAME
implement (odoo-coding) -> P4b review -> P5 test path as the rest of the cluster.

The scan itself is context-heavy (it sweeps every in-scope file of a module) and MUST NOT be run
by the orchestrating/main context. odoo-modules-upgrade already dispatches `odoo-diff-comparator`
per module in P2 (dep order, parallel within a wave) to read that module's FULL source for the
core-absorption comparison - the reconciliation reuses that SAME delegated read instead of adding
a new phase/agent/dispatch, and returns a compact structured `deferred_work` block, never raw grep
output the orchestrator would have to sift through itself.

Each test below fails for exactly one reason: the corresponding piece of the rule was removed,
reworded past detection, or the delegation was lost (e.g. rewritten as an orchestrator-run grep).

Files under test (both under plugins/odoo-ai-agents/):
  - skills/odoo-modules-upgrade/SKILL.md
  - skills/odoo-modules-upgrade/references/upg-phase-detail.md

Run with: python3 -m pytest tests/test_upg_deferred_work_reconciliation.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILL_MD = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"
PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"


def _body(text: str) -> str:
    """Return the content after the closing --- of the frontmatter block."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _skill_body() -> str:
    assert SKILL_MD.exists(), f"skills/odoo-modules-upgrade/SKILL.md not found at {SKILL_MD}"
    return _body(SKILL_MD.read_text(encoding="utf-8"))


def _phase_detail_text() -> str:
    assert PHASE_DETAIL.exists(), f"upg-phase-detail.md not found at {PHASE_DETAIL}"
    return PHASE_DETAIL.read_text(encoding="utf-8")


def _paragraphs(text: str) -> list[str]:
    """Split markdown text on blank lines - the natural unit a rule + its qualifiers live in."""
    return re.split(r"\n\s*\n", text)


def _norm(text: str) -> str:
    """Collapse all whitespace (incl. line-wrap newlines) to single spaces.

    Markdown prose in these skill files hard-wraps at ~90-100 chars, so a literal multi-word
    phrase can legitimately split across a line break. Plain `in` checks on raw text are brittle
    against that reflow; normalize before any literal multi-word substring assertion.
    """
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------------
# Rule 1: the full case-insensitive marker family.
# If this is trimmed to just "TODO", FIXME/XXX/HACK technical debt keeps
# silently slipping past every upgrade unreconciled.
# ---------------------------------------------------------------------------

def test_marker_set_present_in_skill_and_phase_detail():
    """SKILL.md and phase-detail.md must both name the full marker family."""
    for label, text in (("SKILL.md", _skill_body()), ("upg-phase-detail.md", _phase_detail_text())):
        for token in ("`TODO`", "`FIXME`", "`XXX`", "`HACK`", "`@todo`"):
            assert token in text, (
                f"{label}: marker set is missing {token!r}. The version-anchored "
                "deferred-work scan must cover the full TODO/todo/Todo/ToDo/@todo/"
                "FIXME/XXX/HACK family, not just TODO."
            )


# ---------------------------------------------------------------------------
# Rule 2: DUE vs DEFERRED vs UNANCHORED classification.
# anchored version <= target (incl. already-passed/overdue) -> DUE;
# anchored version > target -> DEFERRED (left untouched);
# no parseable anchor -> UNANCHORED (recorded + flagged for human, never
# silently forced into DUE, never silently dropped).
# ---------------------------------------------------------------------------

def test_due_deferred_unanchored_classification_present():
    """A single paragraph must classify markers into DUE / DEFERRED / UNANCHORED together.

    Fails if: the three-way classification is deleted, or split apart so no single rule
    statement covers the due-vs-deferred-vs-unanchored decision, or the anti-silent-absorb/
    drop guarantee for unanchored markers is dropped.
    """
    body = _skill_body()
    paras = [p for p in _paragraphs(body) if "DUE" in p and "DEFERRED" in p and "UNANCHORED" in p]
    assert paras, (
        "skills/odoo-modules-upgrade/SKILL.md: no paragraph classifies markers into "
        "DUE / DEFERRED / UNANCHORED together - the version-anchored deferred-work "
        "classification rule is missing or was split apart (this assertion would pass "
        "vacuously if the rule were deleted piecemeal, so it requires all three labels "
        "co-occurring in one paragraph)."
    )
    para = _norm(paras[0])
    assert re.search(r"(?i)already-passed", para), (
        "DUE must explicitly include an already-passed (overdue) LOWER version, not only an "
        "exact match to the target series - otherwise debt anchored two upgrades ago never "
        "comes due."
    )
    assert re.search(r"(?i)higher", para), (
        "DEFERRED must be anchored to reading a HIGHER future version than target - without "
        "this qualifier, DEFERRED could be misread as covering everything not-yet-due."
    )
    assert "no parseable version anchor" in para, (
        "UNANCHORED must be triggered specifically by 'no parseable version anchor'."
    )
    assert re.search(r"(?i)flag.{0,60}human|human.{0,60}flag", para), (
        "An UNANCHORED marker must be flagged for the human, not silently resolved."
    )
    assert re.search(r"(?i)never silently", para), (
        "Must forbid silently absorbing an unanchored marker into DUE and forbid silently "
        "dropping it - both failure modes are distinct and both must be named."
    )


# ---------------------------------------------------------------------------
# Rule 3: DUE items become REAL work-items, wired into the SAME
# implement -> P4b review -> P5 test path - not a side note.
# ---------------------------------------------------------------------------

def test_due_items_wired_into_implement_review_test_path():
    """DUE items must flow through the upgrade's real work-item pipeline (P4 -> P4b -> P5).

    Fails if: DUE items are only recorded/logged somewhere but never actually dispatched to
    odoo-coding, or the review (P4b) / test (P5) legs of that path are dropped, turning
    "reconciliation" into an inert side-note nobody implements.
    """
    body = _skill_body()
    due_work_item_paras = [
        _norm(p) for p in _paragraphs(body)
        if "DUE" in p and re.search(r"(?i)work-items?", p)
    ]
    assert due_work_item_paras, (
        "skills/odoo-modules-upgrade/SKILL.md: no paragraph wires DUE deferred-work items "
        "into the upgrade's work-item set."
    )
    full_path_paras = [p for p in due_work_item_paras if "P4b" in p and "P5" in p]
    assert full_path_paras, (
        "skills/odoo-modules-upgrade/SKILL.md: found a DUE/work-item paragraph but none "
        "references the full implement -> P4b review -> P5 test path:\n"
        + "\n---\n".join(due_work_item_paras)
    )
    assert any("not a side note" in p for p in full_path_paras), (
        "SKILL.md must explicitly state DUE items are 'not a side note' - the phrase that "
        "distinguishes 'executed now' from merely recording/logging the marker."
    )


# ---------------------------------------------------------------------------
# Rule 4: delegation. The scan reuses the ALREADY-dispatched per-module reader
# (odoo-diff-comparator, P2) - it is never a fresh grep the orchestrating/main
# context runs itself, and no new phase/agent was invented for it.
# ---------------------------------------------------------------------------

def test_scan_delegated_to_existing_per_module_reader_not_main_context():
    """The marker scan must be delegated to the existing per-module dispatch, not main context.

    Fails if: the SKILL is rewritten to describe the scan as something the orchestrator itself
    greps (main-context pollution with a cluster-wide sweep), or as a brand-new stand-alone
    phase/agent instead of reusing the odoo-diff-comparator read P2 already performs.
    """
    body = _skill_body()
    norm_body = _norm(body)
    assert "same delegated per-module read" in norm_body, (
        "skills/odoo-modules-upgrade/SKILL.md: the reconciliation must be framed as reusing "
        "the SAME delegated per-module read already used for P2 core-absorption comparison, "
        "not introduced as a new phase or a new agent dispatch."
    )
    assert re.search(r"(?i)odoo-diff-comparator.{0,300}(full source|same read)", norm_body), (
        "SKILL.md must attribute the scan to the odoo-diff-comparator dispatch already "
        "running per module in P2."
    )
    assert "never greps module source itself" in norm_body, (
        "SKILL.md must state the orchestrator never greps module source itself for this "
        "reconciliation - without this the scan could be re-described as an orchestrator/main "
        "context grep, defeating the point of delegating it to a sub-agent's own context."
    )
    assert "no separate scan or dispatch" in norm_body, (
        "SKILL.md must make explicit that no new agent/dispatch/phase was invented for this "
        "scan - it rides the existing P2 per-module dispatch."
    )


# ---------------------------------------------------------------------------
# Rule 5: the per-module dispatch-brief mechanics (marker regex source, file
# types, classification, structured output) live in the reference file the
# SKILL body points to, and the delegated agent actually returns a compact
# `deferred_work` block (not raw grep output) that P4 consumes.
# ---------------------------------------------------------------------------

def test_phase_detail_carries_scan_mechanics_and_structured_output():
    """upg-phase-detail.md must carry the per-module scan brief + deferred_work output schema."""
    detail = _norm(_phase_detail_text())
    assert "deferred_work" in detail, (
        "upg-phase-detail.md: the odoo-diff-comparator dispatch brief and the "
        "absorption/<module>.md output schema must carry a deferred_work block that P4 "
        "consumes as its work-item source."
    )
    assert re.search(r"(?i)version anchor", detail), (
        "upg-phase-detail.md must describe parsing a VERSION ANCHOR from the marker text."
    )
    assert re.search(r"(?i)same read as step 2|no separate dispatch", detail), (
        "upg-phase-detail.md must state the scan happens in the SAME read as the existing "
        "per-module comparator step, not a separate dispatch."
    )
    assert "0b." in detail and re.search(r"(?i)DUE VERSION-ANCHORED DEFERRED WORK", detail), (
        "upg-phase-detail.md P4 dispatch brief must carry an explicit instruction step that "
        "implements DUE deferred-work items now (the wiring point into odoo-coding)."
    )
