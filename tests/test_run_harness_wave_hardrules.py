"""Behavioral guard for run-harness's between-wave integration hard rules.

(Retargeted from the folded-in per-wave git-executor. The two business contracts protected are
unchanged; only the OWNER moved to run-harness, which now owns the per-wave integration directly.)

- Each assertion fails for exactly one reason: the corresponding rule was removed.
- Tests protect the business contract ("never auto-merge - each wave auto-advances with NO per-wave
  PR; the single run-level PR's outward merge is human-gated (L2)", "never write to the principal
  checkout"), NOT the code structure.

Run with: python3 -m pytest tests/test_run_harness_wave_hardrules.py -v
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_HARNESS = ROOT / "plugins" / "odoo-ai-agents" / "skills" / "run-harness" / "SKILL.md"


def _skill_body() -> str:
    assert RUN_HARNESS.exists(), f"skills/run-harness/SKILL.md not found at {RUN_HARNESS}"
    text = RUN_HARNESS.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


# ---------------------------------------------------------------------------
# Rule 1: Principal-branch-lock
# run-harness must explicitly prohibit dispatching a source-writing node against the principal
# checkout / writing-committing to the principal branch. If deleted, a coding wave could mutate the
# branch other sessions depend on, breaking the wave isolation guarantee.
# ---------------------------------------------------------------------------

_PRINCIPAL_LOCK_RE = re.compile(
    r"(?i)(never|must\s+not|do\s+not).{0,90}?principal\s+(checkout|branch)",
    re.DOTALL,
)


def test_principal_branch_lock_present():
    """Rule 1: run-harness must prohibit git write-ops / dispatch against the principal checkout.

    Fails if: the principal-branch-lock rule is removed or rephrased to drop the prohibition. This
    would let a wave commit directly to master/main, defeating the wave isolation model.
    """
    body = _skill_body()
    assert _PRINCIPAL_LOCK_RE.search(body), (
        "skills/run-harness/SKILL.md: principal-branch-lock rule missing. The body must prohibit "
        "dispatching a source-writing node against / writing to the principal checkout|branch "
        "(e.g. Hard rule 6: 'NEVER dispatch a source-writing node against the principal checkout')."
    )


# ---------------------------------------------------------------------------
# Rule 4: Human-confirm merge (no auto-merge)
# Each wave AUTO-ADVANCES on a green cumulative close-gate with NO per-wave PR; the single run-level
# PR's outward merge stays L2 (always a human gate). If deleted, a run could auto-land unreviewed
# changes on the principal branch.
# ---------------------------------------------------------------------------

_HUMAN_CONFIRM_RE = re.compile(
    r"(?i)(human.{0,20}confirm|human\s+approves|no.{0,20}auto.{0,20}merg|never.{0,20}auto.{0,20}merg"
    r"|l2\s+is\s+always\s+a\s+human\s+gate|l2\s+never\s+(lowers|auto-passes))",
    re.DOTALL,
)


def test_human_confirm_merge_present():
    """Rule 4: run-harness must require a human gate before the merge (no auto-merge).

    Fails if: the human-gated-merge rule is removed or softened to allow automatic merge. Without
    it, a wave could silently merge a PR while the human is away.
    """
    body = _skill_body()
    assert _HUMAN_CONFIRM_RE.search(body), (
        "skills/run-harness/SKILL.md: human-confirm-merge rule missing. The body must state the "
        "merge/squash is human-gated (e.g. 'L2 is always a human gate', 'human-confirmed', "
        "'L2 never auto-passes, so the human approves the merge')."
    )


def test_between_wave_auto_advances_and_never_merges():
    """Rule 4 (companion): each wave AUTO-ADVANCES on a green cumulative close-gate with NO per-wave
    PR; the whole run lands as exactly ONE PR whose outward MERGE stays odoo-pr-monitoring's -
    run-harness's between-wave integration never merges to principal."""
    body = _skill_body()
    low = body.lower()
    assert "no per-wave pr" in low, (
        "run-harness between-wave integration must AUTO-ADVANCE with NO per-wave PR (single-run-PR model)."
    )
    assert "one pr" in low, (
        "run-harness must land the whole run as exactly ONE PR (opened once after the final wave)."
    )
    assert "odoo-pr-monitoring" in low and "merge" in low, (
        "the outward merge must stay odoo-pr-monitoring's (run-harness's between-wave integration never merges)."
    )
