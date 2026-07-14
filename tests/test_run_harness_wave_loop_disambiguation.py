"""Guard: the per-module code -> review+test -> code loop must be unambiguous about who drives
`odoo-code-review`.

(Retargeted from the folded-in per-wave git-executor. run-harness now owns the between-wave
integration that invokes `odoo-coding` per module; the contract it protects is unchanged.)

Root cause this protects against: `odoo-coding/SKILL.md`'s loop-driving prose must not let a
transitively-active run (a `runSlug`/`WORKLOG` that merely looks like a run-id) trick `odoo-coding`
into emitting `next: odoo-code-review` and NOT driving it. During between-wave integration
`run-harness` invokes `odoo-coding` via the Skill tool per MODULE, passing `WORKTREE_PATH` +
`WORKLOG: <runSlug>` but NEVER a `run-<id>` RUN-DAG node for that per-module call - so `odoo-coding`
MUST DRIVE the review inline in that case.

The rule has two explicit branches: emit-next is legal ONLY when `odoo-coding` is itself a RUN-DAG
node dispatched DIRECTLY by run-harness; every other invocation - explicitly INCLUDING a
run-harness between-wave integration invocation - must DRIVE `odoo-code-review` inline and fix
before returning. run-harness carries a mirroring one-line assertion so the contract is stated from
both sides.

Run: python3 -m pytest tests/test_run_harness_wave_loop_disambiguation.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CODING_SKILL = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"

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


def test_loop_section_names_run_harness_between_wave_in_the_drive_inline_default():
    """The default (drive-inline) branch must explicitly name the run-harness between-wave
    integration invocation.

    Fails if: the prose reverts to a generic "no run-harness" exception that never says what
    happens for a run-harness between-wave per-module dispatch (the gap that lets the per-module
    review be skipped).
    """
    section = _loop_section()
    assert "run-harness" in section and "between-wave" in section, (
        "skills/odoo-coding/SKILL.md loop section must explicitly name a `run-harness` between-wave "
        "integration invocation as an invocation that drives the review inline (default branch)."
    )


def test_loop_section_gates_emit_next_to_direct_rundag_dispatch():
    """emit-next must be gated to a RUN-DAG node dispatched DIRECTLY by run-harness."""
    section = _loop_section()
    assert re.search(r"RUN-DAG node", section), (
        "skills/odoo-coding/SKILL.md loop section must use the precise 'RUN-DAG node' vocabulary."
    )
    assert re.search(r"dispatched\s+DIRECTLY\s+by\s+`?run-harness`?", section), (
        "skills/odoo-coding/SKILL.md loop section must state the emit-next branch applies only when "
        "odoo-coding is dispatched DIRECTLY by run-harness (not merely 'under an active run-harness')."
    )


def test_loop_section_excludes_transitive_run_and_runslug_from_emit_next():
    """A transitively-active run / bare runSlug|WORKLOG must NOT trigger emit-next."""
    section = _loop_section()
    assert re.search(r"runSlug", section) and re.search(r"WORKLOG", section), (
        "skills/odoo-coding/SKILL.md loop section must reference the `runSlug` / `WORKLOG` brief "
        "fields to disclaim them as a run-harness RUN-DAG node."
    )
    assert re.search(r"is\s+NOT\s+a\s+run-harness\s+RUN-DAG\s+node", section), (
        "skills/odoo-coding/SKILL.md loop section must explicitly state that a transitively-active "
        "run / bare runSlug is NOT a run-harness RUN-DAG node and does not trigger emit-next."
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


def test_run_harness_mirrors_the_per_module_inline_review_guarantee():
    """run-harness/SKILL.md § Between-wave integration must state, from its own side, that the
    invoked odoo-coding drives its per-module review inline and that run-harness itself never
    advances a per-module `next`.

    Fails if: this mirroring assertion is missing, leaving the guarantee stated only from
    odoo-coding's side with nothing in run-harness to cross-check against (SSOT / drift risk).
    """
    assert RUN_HARNESS.exists(), f"not found: {RUN_HARNESS}"
    text = _normalize(RUN_HARNESS.read_text(encoding="utf-8"))
    assert re.search(r"(?i)odoo-coding.{0,120}DRIVES.{0,80}inline", text), (
        "skills/run-harness/SKILL.md between-wave integration must state that the invoked "
        "odoo-coding DRIVES its per-module odoo-code-review inline."
    )
    assert re.search(r"(?i)run-harness\s+does\s+NOT\s+advance\s+a\s+per-module\s+`?next`?", text), (
        "skills/run-harness/SKILL.md must explicitly disclaim advancing a per-module `next` itself "
        "for the in-wave odoo-coding invocation - the exact gap that let the review skip silently."
    )
