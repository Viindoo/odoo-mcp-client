"""Guard: the per-WI code -> review+test -> code loop must be unambiguous about
who drives `odoo-code-review`.

Root cause this protects against: `odoo-coding/SKILL.md`'s loop-driving prose used
to state only ONE exception to "drive the review yourself" - "dispatched by an
active run-harness (a `run-<id>` is named)". `odoo-wave` invokes `odoo-coding` via
the Skill tool per work-item, passing `WORKTREE_PATH` + `WORKLOG: <runSlug>` but
NEVER a `run-<id>` RUN-DAG node for that per-WI call (`odoo-wave/SKILL.md` Phase 2
- odoo-wave has no per-WI `next` driver; it just cherry-picks and moves on after
`odoo-coding` returns a SHA). A loose reading of the old prose ("I'm transitively
under a run, `runSlug` looks like a run-id") let `odoo-coding` emit
`next: odoo-code-review` and NOT drive it - nobody ever advances that `next`, so
the module reached the wave-level Phase 4 review with NO independent per-WI
review+fix loop. No backstop, no test.

The fix disambiguates the rule to two explicit branches: emit-next is legal ONLY
when `odoo-coding` is itself a RUN-DAG node dispatched DIRECTLY by run-harness;
every other invocation - explicitly INCLUDING an `odoo-wave` dispatch - must DRIVE
`odoo-code-review` inline and fix before returning. `odoo-wave/SKILL.md` carries a
mirroring one-line assertion so the contract is stated from both sides.

These tests fail on the pre-fix prose (verified by reasoning about the removed
text, which never mentioned `odoo-wave` or `RUN-DAG node` in the loop section at
all) and pass once the disambiguated wording is in place. They are substring /
proximity checks on prose (not exact-line diffs), so a future rewording that
preserves the same guarantees will not spuriously fail.

Run: python3 -m pytest tests/test_wave_loop_drive_to_done_disambiguation.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CODING_SKILL = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
WAVE_SKILL = PLUGIN / "skills" / "odoo-wave" / "SKILL.md"

_LOOP_HEADING_RE = re.compile(
    r"^##\s+The code -> review\+test -> code loop.*?(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _normalize(text: str) -> str:
    """Collapse whitespace runs (incl. line-wraps) to a single space.

    SKILL.md prose hard-wraps at ~100 cols, so a proximity check that spans a
    wrap boundary must not be sensitive to the newline in between.
    """
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


def test_loop_section_names_odoo_wave_in_the_drive_inline_default():
    """The default (drive-inline) branch must name `odoo-wave` explicitly.

    Fails if: the prose reverts to a generic "no run-harness" exception that
    never says what happens for an `odoo-wave` per-WI dispatch. The old wording
    never mentioned odoo-wave in this section at all, which is exactly the gap
    that let a loose reading skip the per-WI review.
    """
    section = _loop_section()
    assert "odoo-wave" in section, (
        "skills/odoo-coding/SKILL.md loop section must explicitly name "
        "`odoo-wave` as an invocation that drives the review inline (default "
        "branch), not just 'no run-harness'."
    )


def test_loop_section_gates_emit_next_to_direct_rundag_dispatch():
    """emit-next must be gated to a RUN-DAG node dispatched DIRECTLY by run-harness.

    Fails if: the emit-next exception is stated as merely "an active run-harness"
    (a run-id visible anywhere upstream) rather than "odoo-coding is itself a
    RUN-DAG node run-harness dispatched directly" - the ambiguity that caused the
    bug (odoo-wave's WORKLOG:<runSlug> looking like a qualifying run-id).
    """
    section = _loop_section()
    assert re.search(r"RUN-DAG node", section), (
        "skills/odoo-coding/SKILL.md loop section must use the precise "
        "'RUN-DAG node' vocabulary to scope the emit-next branch."
    )
    assert re.search(r"dispatched\s+DIRECTLY\s+by\s+`?run-harness`?", section), (
        "skills/odoo-coding/SKILL.md loop section must state the emit-next "
        "branch applies only when odoo-coding is dispatched DIRECTLY by "
        "run-harness (not merely 'under an active run-harness')."
    )


def test_loop_section_excludes_transitive_run_and_runslug_from_emit_next():
    """A transitively-active run / bare runSlug|WORKLOG must NOT trigger emit-next.

    Fails if: the prose no longer explicitly disclaims a bare `runSlug` /
    `WORKLOG` value (odoo-wave's per-WI brief field) as a qualifying run-id for
    the emit-next branch.
    """
    section = _loop_section()
    assert re.search(r"runSlug", section) and re.search(r"WORKLOG", section), (
        "skills/odoo-coding/SKILL.md loop section must reference odoo-wave's "
        "`runSlug` / `WORKLOG` brief fields to disclaim them as a run-harness "
        "RUN-DAG node."
    )
    assert re.search(r"is\s+NOT\s+a\s+run-harness\s+RUN-DAG\s+node", section), (
        "skills/odoo-coding/SKILL.md loop section must explicitly state that a "
        "transitively-active run / bare runSlug is NOT a run-harness RUN-DAG "
        "node and does not trigger the emit-next branch."
    )


def test_loop_section_mandates_drive_and_fix_before_returning():
    """The default branch must mandate driving + fixing inline before returning."""
    section = _loop_section()
    assert re.search(r"(?i)drive\b", section), (
        "skills/odoo-coding/SKILL.md loop section must use 'drive' language for "
        "the default (non-run-harness-RUN-DAG) branch."
    )
    assert re.search(r"(?i)fix\b.{0,80}before returning|before returning.{0,80}fix", section), (
        "skills/odoo-coding/SKILL.md loop section must require fixing within the "
        "bounded loop BEFORE returning in the default branch, not merely "
        "reviewing."
    )


def test_wave_skill_mirrors_the_per_wi_inline_review_guarantee():
    """odoo-wave/SKILL.md Phase 2 must state, from its own side, that the
    invoked odoo-coding drives its per-WI review inline and that odoo-wave
    itself never advances a per-WI `next`.

    Fails if: this mirroring assertion is missing, leaving the guarantee stated
    only from odoo-coding's side with nothing in odoo-wave to cross-check against
    (an SSOT / drift risk - CLAUDE.md ETHOS #9 "SSOT").
    """
    assert WAVE_SKILL.exists(), f"not found: {WAVE_SKILL}"
    text = _normalize(WAVE_SKILL.read_text(encoding="utf-8"))
    assert re.search(r"(?i)odoo-coding.{0,120}DRIVES.{0,80}inline", text), (
        "skills/odoo-wave/SKILL.md Phase 2 must state that the invoked "
        "odoo-coding DRIVES its per-WI odoo-code-review inline."
    )
    assert re.search(r"(?i)odoo-wave\s+does\s+NOT\s+advance\s+a\s+per-WI\s+`?next`?", text), (
        "skills/odoo-wave/SKILL.md Phase 2 must explicitly disclaim advancing a "
        "per-WI `next` itself - the exact gap that let the review skip silently."
    )
