"""Guard: the code -> review+test -> code loop must be unambiguous about who drives
`odoo-code-review`.

Root cause this protects against: `odoo-coding/SKILL.md`'s loop-driving prose must never leave an
invocation in which NEITHER side drives the review - `odoo-coding` emitting `next:
odoo-code-review` on the assumption that a driver above it will schedule that node, while no such
node exists. The review then silently never runs, and the only symptom is unreviewed code in a PR.

The gate that decides between the two branches is now a property of the PLAN, not of the caller:
emit-next is legal ONLY when the approved plan ALREADY wires a review node after this coding node
(so `run-harness` has a real node to dispatch); every other invocation - explicitly including a
plan-fed standalone invocation whose plan carries no such node - must DRIVE `odoo-code-review`
inline and fix before returning. That is strictly stronger than the caller-identity gate it
replaces ("was I dispatched directly by the driver?"), because a driver-dispatched node whose plan
has no review node now drives inline instead of emitting into the void - and it is what makes the
old "something that merely looks like an active run" trick structurally impossible rather than
disclaimed.

Run: python3 -m pytest tests/test_run_harness_loop_disambiguation.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CODING_SKILL = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"

_LOOP_HEADING_RE = re.compile(
    r"^##\s+The code -> review\+test -> code loop.*?(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _loop_section() -> str:
    assert CODING_SKILL.exists(), f"not found: {CODING_SKILL}"
    text = CODING_SKILL.read_text(encoding="utf-8")
    m = _LOOP_HEADING_RE.search(text)
    assert m, (
        "skills/odoo-coding/SKILL.md: '## The code -> review+test -> code loop' "
        "section not found - has the heading moved or been renamed?"
    )
    return _normalize(m.group(0))


def test_loop_section_default_is_drive_inline_and_enumerates_its_invocations():
    """The DEFAULT branch must be drive-inline, and must ENUMERATE the invocations it covers -
    including the one that looks most like a driver-dispatched call (a plan-fed standalone
    invocation).

    An unenumerated "every other invocation" is what let a caller argue its own case into the
    emit-next branch. Naming the plan-fed standalone case explicitly is the clause that closes it:
    carrying a plan (or anything that resembles run state) is NOT what earns emit-next.

    Fails if: the prose reverts to a generic "no driver above me" exception that never says what
    happens for an invocation that has run-shaped context but no review node - the gap that lets
    the review be skipped.
    """
    section = _loop_section()
    assert re.search(r"(?i)Drive it yourself in the default case \(mandatory\)", section), (
        "the loop section must declare drive-inline the MANDATORY default, before the branches - "
        "a rule stated only as one of two symmetric branches has no default at all."
    )
    assert re.search(r"(?i)Every other invocation \(default - drive inline\)", section), (
        "the default branch must be labelled as such and be the catch-all ('every other "
        "invocation'), so the two branches are exhaustive by construction."
    )
    for case in (r"direct invocation", r"intake fast-path", r"autonomous fix"):
        assert re.search(rf"(?i){case}", section), (
            f"the drive-inline branch must explicitly INCLUDE '{case}' - an unenumerated default "
            "is one a caller can argue itself out of."
        )
    assert re.search(
        r"(?i)plan-fed standalone invocation whose plan carries no separate review node", section), (
        "the drive-inline branch must explicitly INCLUDE a plan-fed standalone invocation whose "
        "plan carries NO separate review node - carrying a plan, a run slug, or any other "
        "run-shaped context is not what earns emit-next, and this is the exact case that "
        "otherwise emits into the void."
    )


def test_loop_section_gates_emit_next_on_a_plan_wired_review_node():
    """emit-next must be gated on the APPROVED PLAN already wiring a review node after this coding
    node - a checkable property of the plan - and not on who invoked this skill.

    Fails if: the gate is weakened back to a caller-identity test ('dispatched by run-harness',
    'under an active run'), which cannot distinguish a driver-dispatched node that HAS a review
    node downstream from one that does not.
    """
    section = _loop_section()
    assert re.search(
        r"(?i)when the approved plan already\s+wires a review node \(`?odoo-code-review`?\) after "
        r"this coding node, emit `?next: odoo-code-review`?", section), (
        "the emit-next branch must be gated on the APPROVED PLAN already wiring a review node "
        "after this coding node - the only condition under which something downstream will "
        "actually run the review."
    )
    assert re.search(r"(?i)`?run-harness`? drives every node through its ONE dispatch loop", section), (
        "the section must state the driver runs every node through its ONE dispatch loop - the "
        "reason a plan-wired review node is guaranteed to be dispatched, and the reason there is "
        "no second, nested loop that could dispatch it instead."
    )
    assert re.search(r"(?i)do not double-dispatch", section), (
        "the emit-next branch must state its own reason (avoiding a double dispatch); without it "
        "the branch reads as an opt-out from reviewing rather than a de-duplication."
    )


def test_loop_section_reason_is_stated_from_the_default_branch_too():
    """The default branch must carry the UNLESS clause inline - drive inline unless the plan
    already places a separate review node on this node's dependency path - so a reader who lands
    on the mandate alone reaches the same decision as a reader who reads both branches.

    Fails if: the exception is stated only in the branch list, leaving the headline mandate
    unqualified (the two then disagree for anyone who stops reading early).
    """
    section = _loop_section()
    assert re.search(
        r"(?i)UNLESS the plan already places a separate review node on this node's dependency path",
        section), (
        "the drive-inline mandate must carry its exception inline, phrased over the plan's "
        "dependency path."
    )
    assert re.search(r"(?i)driving review here would double-dispatch", section), (
        "the mandate's exception must state WHY it exists (double dispatch), not merely that it "
        "exists."
    )
    assert re.search(r"(?i)Emit the Continuation Contract either way", section), (
        "both branches must still emit the Continuation Contract - the driver's only evidence "
        "that the node ran at all."
    )


def test_loop_section_mandates_drive_and_fix_before_returning():
    """The default branch must mandate driving + fixing inline before returning."""
    section = _loop_section()
    assert re.search(r"(?i)drive\b", section), (
        "skills/odoo-coding/SKILL.md loop section must use 'drive' language for the default branch."
    )
    assert re.search(r"(?i)fix\b.{0,80}before returning|before returning.{0,80}fix", section), (
        "skills/odoo-coding/SKILL.md loop section must require fixing within the bounded loop BEFORE "
        "returning in the default branch, not merely reviewing."
    )
    assert re.search(r"(?i)Bound the loop to \*\*3 iterations\*\*|bounded loop", section), (
        "the inline drive must be BOUNDED - an unbounded fix loop is how 'drive it yourself' "
        "turns into a run that never returns."
    )
