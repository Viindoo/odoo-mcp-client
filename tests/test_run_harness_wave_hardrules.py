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


# The rule: the WHOLE RUN lands as exactly ONE PR, opened once after the final wave - never one PR
# per wave. A bare `"one pr" in low` substring check names this rule without protecting it: it is
# equally satisfied by policy-INVERTING text such as "one PR per wave" (asserts the OPPOSITE - a
# per-wave PR cadence), since "one pr" is a literal substring of "one PR per wave" too. Anchor on
# the actual CARDINALITY claim ("exactly one PR" / "single run(-level) PR") and explicitly reject
# the per-wave-PR inversion so the two phrasings can never both pass.
_SINGLE_RUN_PR_RE = re.compile(r"(?i)(exactly\s+one\s+pr\b|single[\s-]run(?:-level)?\s+pr\b)")
_PER_WAVE_PR_INVERSION_RE = re.compile(r"(?i)one\s+pr\s+per\s+wave")

# #199 hardening (R12 F1, PARTIAL): the four checks above test independent substring/regex
# presence ANYWHERE in the body, never that the SAME sentence asserts RUN-level (not WAVE-level)
# cardinality. A natural-sounding negation-of-negation rewrite defeats all four while asserting the
# EXACT policy #199 exists to rule out - verified against this constructed, policy-inverting text
# (executed against the actual compiled regexes, not a paraphrase):
#
#   "Each coding wave now opens exactly one PR of its own before advancing. There is no per-wave
#   PR restriction preventing this any longer - every wave independently opens exactly one PR,
#   reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run advances to the next
#   wave."
#
# This passes all four checks above: "no per-wave pr" occurs as a sub-phrase of an incidental
# negation ("no per-wave PR restriction preventing this"); "exactly one pr" occurs verbatim; the
# literal 4-gram "one pr per wave" never occurs contiguously; both required tokens are present.
# What makes it an inversion is that a WAVE - not the run - is the grammatical actor that "opens"
# the PR ("each/every wave ... opens ... one PR"), the opposite of every legitimate occurrence in
# this file (where "the run"/"the terminal integrate land-tail" opens the ONE PR, and any "wave"
# mention nearby is a temporal anchor like "after the final wave" or a negated compound like
# "NO per-wave PR" - never the subject of "opens"). Anchor on that actor relationship directly:
# reject a wave-referring phrase acting as the near subject of an "open(s)" verb bound to a PR
# cardinality claim, in the SAME clause (bounded by '.'/';' so it cannot cross into an unrelated
# sentence), unless it is itself a negation ("not ... per wave", "no per-wave ...").
_WAVE_ACTOR = r"\b(?:each|every|any|per)[\s-]+(?:coding[\s-]+)?waves?\b"
_OPEN_VERB = r"\bopen(?:s|ing|ed)?\b"
_PR_TOKEN = r"\bprs?\b"
_WAVE_AS_PR_OPENER_RE = re.compile(
    rf"(?i)(?<!not one )(?<!not )(?<!no ){_WAVE_ACTOR}[^.;]{{0,25}}"
    rf"(?:{_OPEN_VERB}[^.;]{{0,40}}{_PR_TOKEN}|{_PR_TOKEN}[^.;]{{0,40}}{_OPEN_VERB})"
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
    assert _SINGLE_RUN_PR_RE.search(low), (
        "run-harness must state the whole run lands as EXACTLY one PR (e.g. 'single run-level PR', "
        "'opens exactly ONE PR after the final wave') - not merely mention \"PR\" in passing."
    )
    assert not _PER_WAVE_PR_INVERSION_RE.search(low), (
        "run-harness text asserts a PER-WAVE PR policy (\"one PR per wave\"), which INVERTS the "
        "single-run-PR rule - each wave auto-advances with NO per-wave PR; only the whole run opens "
        "ONE PR, after the final wave."
    )
    assert "odoo-pr-monitoring" in low and "l2-merge-gate" in low, (
        "the outward merge must stay odoo-pr-monitoring's L2-merge-gate (run-harness's between-wave "
        "integration never merges) - a bare \"merge\" mention anywhere in the doc is not proof of this; "
        "the specific 'l2-merge-gate' token is."
    )
    assert not _WAVE_AS_PR_OPENER_RE.search(low), (
        "run-harness text reads as a WAVE (not the run) being the grammatical actor that 'opens' a "
        "PR - the #199 policy inversion (a per-wave PR cadence dressed as a cardinality claim). The "
        "single run-level PR is opened by the run / the terminal integrate land-tail, never by "
        "'each wave' or 'every wave'."
    )


def test_single_run_pr_claim_rejects_the_verified_wave_scoped_inversion():
    """#199 hardening (companion, meta-test): proves the new guard actually defeats the SPECIFIC
    policy-inverting sentence the review constructed and verified against the pre-fix regexes,
    while never firing on the real run-harness/SKILL.md text (which would be a false positive that
    blocks legitimate single-run-PR prose).

    Fails if the guard no longer catches the known-bad string (regression to the pre-fix
    blind spot), or if it now also rejects the real production text (over-tightened).
    """
    inverting_text = (
        "Each coding wave now opens exactly one PR of its own before advancing. "
        "There is no per-wave PR restriction preventing this any longer - every wave "
        "independently opens exactly one PR, reviewed and gated by odoo-pr-monitoring's "
        "l2-merge-gate before the run advances to the next wave."
    )
    low_candidate = inverting_text.lower()
    # The candidate must still satisfy every OTHER assertion (that is the whole point of the trap)...
    assert "no per-wave pr" in low_candidate
    assert _SINGLE_RUN_PR_RE.search(low_candidate)
    assert not _PER_WAVE_PR_INVERSION_RE.search(low_candidate)
    assert "odoo-pr-monitoring" in low_candidate and "l2-merge-gate" in low_candidate
    # ...but the new actor-relationship guard must catch it anyway.
    assert _WAVE_AS_PR_OPENER_RE.search(low_candidate), (
        "the wave-as-PR-opener guard must catch this constructed policy-inverting sentence - if "
        "this fails, the guard regressed to the pre-fix blind spot verified in #199."
    )

    real_body_low = _skill_body().lower()
    assert not _WAVE_AS_PR_OPENER_RE.search(real_body_low), (
        "the wave-as-PR-opener guard fired against the REAL run-harness/SKILL.md text - a false "
        "positive that would block legitimate single-run-PR prose."
    )
