"""Guard: D11 (V3 R2 P5) - the analyst-family Continuation Contract format must match its
siblings'. Business rule protected: every leaf agent that emits a dual `BLOCKED`/`NEEDS_CONTEXT`
early-return fallback in its Continuation Contract section must also carry the explicit "'waiting'
is never a bare statement" restatement its siblings carry - a genuine pause must be reported as
`BLOCKED`/`NEEDS_CONTEXT` with a `blocked_reason` naming what/who/next, never a bare "waiting"/
"in progress" sentence that leaves the caller unable to tell finished-without-reporting from
still-working (the SSOT rule: `snippets/continuation-contract.md`, "Waiting is never a bare
statement").

History: a prior round added the `## Continuation Contract` section (with this explicit clause) to
4 of "5 read-only analyst-family agents" that had none, but left the 5th
(`odoo-doc-scoper.md`, which already had a Continuation Contract section from an earlier diff)
without the clause - a differently-phrased sibling left behind in the identically-named class.

FAMILY IDENTIFICATION (scanning, not a hardcoded file list - see `_dual_status_family()`): the
5 agents V3 R2 named by hand ("matching diff-stat line counts") share one concrete, greppable
textual shape - their Continuation Contract section's early-return fallback is phrased as
"Use `status: BLOCKED`/`NEEDS_CONTEXT`" or the reverse-ordered "Use `status: NEEDS_CONTEXT` /
`BLOCKED`" (never a single bare `BLOCKED` or `NEEDS_CONTEXT` alone - that is a different,
already-compliant completion shape used by other agent families in this tree, e.g.
`odoo-code-reviewer.md`/`odoo-qa-tester.md`, out of scope here). Scanning for that shape - rather
than trusting V3's hand-picked list - finds 7 members, not 5: the same 5, PLUS `odoo-doc-planner.md`
(also missing the clause; not one of V3's named 5, but the identical defect under the identical
contract shape) and `odoo-intent-extractor.md` (already compliant). This is the whole point of a
scan over a list: a member the manual audit missed is still caught.

Run: python3 -m pytest tests/test_analyst_family_completion_format.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "plugins" / "odoo-ai-agents" / "agents"

CC_HEADING_RE = re.compile(r"##\s*Continuation Contract", re.IGNORECASE)
# The shape that ties the family together: a DUAL early-return fallback naming BOTH BLOCKED and
# NEEDS_CONTEXT together (either order) as backtick-quoted `status:` values - not a bare mention of
# either status alone, which other, differently-shaped agent families also use.
DUAL_STATUS_RE = re.compile(
    r"Use `status:\s*(?:BLOCKED`\s*/\s*`NEEDS_CONTEXT`|NEEDS_CONTEXT`\s*/\s*`BLOCKED`)",
    re.IGNORECASE,
)
WAITING_CLAUSE_RE = re.compile(r"never a bare statement", re.IGNORECASE)
SECTION_WINDOW = 2000


def _dual_status_family() -> dict[str, str]:
    """Scan agents/*.md (not a hardcoded list) for every file whose Continuation Contract section
    uses the dual BLOCKED/NEEDS_CONTEXT early-return shape. Returns {filename: section_text}."""
    family = {}
    for path in sorted(AGENTS.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        norm = re.sub(r"\s+", " ", raw)
        heading = CC_HEADING_RE.search(norm)
        if not heading:
            continue
        section = norm[heading.start():heading.start() + SECTION_WINDOW]
        if DUAL_STATUS_RE.search(section):
            family[path.name] = section
    return family


def test_family_scan_finds_the_known_members_plus_the_one_v3_missed():
    """Genre A (structural, whole-tree scan). Locks in that the scan-based family identification
    is not narrower than V3's own hand-picked 5, and documents that it is WIDER by exactly one real
    member (`odoo-doc-planner.md`) the manual "diff-stat line count" audit method did not name -
    proving the scan is doing real work, not just reproducing a list by another route.

    Fails if: the scan stops finding any of V3's 5 named members, or `odoo-doc-planner.md`/
    `odoo-intent-extractor.md` drop out of the dual-status shape (a rewrite that changes their
    Continuation Contract phrasing away from this shape - in which case this test's OWN premise
    needs re-checking, not a silent pass).
    """
    family = _dual_status_family()
    v3_named = {
        "odoo-diff-comparator.md",
        "odoo-doc-scoper.md",
        "odoo-gap-analyzer.md",
        "odoo-installable-prober.md",
        "odoo-review-scoper.md",
    }
    missing = v3_named - set(family)
    assert not missing, f"scan lost V3-named family member(s): {missing}"
    assert "odoo-doc-planner.md" in family, (
        "the scan must find odoo-doc-planner.md - a real 6th/7th member sharing the identical "
        "dual-status Continuation Contract shape, missed by V3's manual hand-picked list."
    )


def test_every_dual_status_agent_states_the_waiting_ban():
    """Genre A (whole-tree, no allowlist). Every agent file the structural scan finds - not just
    V3's named 5 - must carry the explicit "'waiting' is never a bare statement" restatement in its
    Continuation Contract section, matching the sibling wording already established by 4/5 of the
    named family.

    Pre-fix (measured against `git show HEAD`): 2 offenders - `odoo-doc-scoper.md` (had a
    Continuation Contract section with no waiting-ban restatement; V3's exact finding) and
    `odoo-doc-planner.md` (same gap, found only by widening the scan past V3's named list).

    Fails if: any current or future dual-status agent lacks the restatement - including a
    brand-new one nobody has written yet, which is the entire point of scoping this to the
    scan-derived family rather than the one historically-named class.
    """
    family = _dual_status_family()
    assert len(family) >= 5, (
        f"the structural scan should find at least the 5 V3-named members; found {len(family)}: "
        f"{sorted(family)}"
    )
    offenders = [name for name, section in family.items() if not WAITING_CLAUSE_RE.search(section)]
    assert not offenders, (
        "Agent(s) with a dual BLOCKED/NEEDS_CONTEXT Continuation Contract but no explicit "
        f"'waiting is never a bare statement' restatement: {sorted(offenders)}"
    )
