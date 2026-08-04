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

# #199 hardening (R12 F1, PARTIAL, then V3 R2 P6 - STILL PARTIAL). The four checks above test
# independent substring/regex presence ANYWHERE in the body, never that the SAME sentence asserts
# RUN-level (not WAVE-level) cardinality. A natural-sounding negation-of-negation rewrite defeats
# all four while asserting the EXACT policy #199 exists to rule out - verified against this
# constructed, policy-inverting text (executed against the actual compiled regexes, not a
# paraphrase):
#
#   "Each coding wave now opens exactly one PR of its own before advancing. There is no per-wave
#   PR restriction preventing this any longer - every wave independently opens exactly one PR,
#   reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run advances to the next
#   wave."
#
# What makes it an inversion is that a WAVE - not the run - is the grammatical actor that "opens"
# the PR ("each/every wave ... opens ... one PR"), the opposite of every legitimate occurrence in
# this file. The R12 fix anchored on THAT actor relationship correctly, but keyed the wave-actor
# itself to a closed 4-word quantifier set ("each|every|any|per"). A reviewer constructed and RAN
# 4 more sentences against the compiled regex using ordinary wave-referring phrasings outside that
# set - "this wave", "the current wave", bare plural "waves", "a wave" - and all 4 evaded it while
# asserting the identical policy inversion. Widening the quantifier list a second time repeats the
# same closed-class mistake with a longer list; the PROPERTY that actually matters is not WHICH
# quantifier introduces "wave" - it is whether ANY wave-referring noun (quantified, articled, bare,
# or plural - there is no closed set of ways to refer to "a wave" in English) is the near
# grammatical subject of an "opens ... PR" clause. Anchor on the noun itself (`\bwaves?\b`, no
# quantifier prefix required at all) and handle the one thing that actually needs enumerating -
# negation, a genuinely small, closed, non-domain-specific class of English function words
# ("no"/"not"/"never"/...) - via a bounded same-clause window check instead of a fixed-width
# lookbehind, so "not one per wave" and "NO per-wave PR" (real, legitimate text in THIS file) are
# excluded regardless of how many words sit between the negation and "wave".
_WAVE_ACTOR = r"\bwaves?\b"
_OPEN_VERB = r"\bopen(?:s|ing|ed)?\b"
_PR_TOKEN = r"\bprs?\b"
_WAVE_OPENER_CORE_RE = re.compile(
    rf"(?i){_WAVE_ACTOR}[^.;]{{0,25}}"
    rf"(?:{_OPEN_VERB}[^.;]{{0,40}}{_PR_TOKEN}|{_PR_TOKEN}[^.;]{{0,40}}{_OPEN_VERB})"
)
# English clause-negation is a genuinely closed, small function-word class - unlike "ways to refer
# to a wave", this is safe to enumerate.
_NEGATION_RE = re.compile(r"(?i)\b(?:no|not|never|cannot|isn't|aren't|without)\b")
_NEGATION_WINDOW = 20  # chars scanned immediately before the wave-actor match, same clause only


def _wave_as_pr_opener_matches(text: str) -> list[re.Match]:
    """Every 'wave opens PR' candidate (`_WAVE_OPENER_CORE_RE`), excluding one whose wave-actor is
    itself under a same-clause negation within `_NEGATION_WINDOW` chars before it - a Python-level
    bounded-window check rather than a fixed-width regex lookbehind, so an arbitrary number of
    intervening words ("not ONE per wave", not just "not per-wave") is still caught. The window
    never crosses a preceding '.'/';' clause boundary, so a negation in an EARLIER, unrelated
    sentence can never suppress a real match."""
    matches = []
    for m in _WAVE_OPENER_CORE_RE.finditer(text):
        start = m.start()
        clause_start = max(text.rfind(".", 0, start), text.rfind(";", 0, start)) + 1
        window_start = max(clause_start, start - _NEGATION_WINDOW)
        if _NEGATION_RE.search(text[window_start:start]):
            continue
        matches.append(m)
    return matches


def _wave_as_pr_opener_search(text: str):
    """`.search()`-shaped wrapper over `_wave_as_pr_opener_matches` - first match or `None`."""
    matches = _wave_as_pr_opener_matches(text)
    return matches[0] if matches else None


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
    assert not _wave_as_pr_opener_search(low), (
        "run-harness text reads as a WAVE (not the run) being the grammatical actor that 'opens' a "
        "PR - the #199 policy inversion (a per-wave PR cadence dressed as a cardinality claim). The "
        "single run-level PR is opened by the run / the terminal integrate land-tail, never by any "
        "wave-referring noun (quantified, articled, or bare)."
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
    assert _wave_as_pr_opener_search(low_candidate), (
        "the wave-as-PR-opener guard must catch this constructed policy-inverting sentence - if "
        "this fails, the guard regressed to the pre-fix blind spot verified in #199."
    )

    real_body_low = _skill_body().lower()
    assert not _wave_as_pr_opener_search(real_body_low), (
        "the wave-as-PR-opener guard fired against the REAL run-harness/SKILL.md text - a false "
        "positive that would block legitimate single-run-PR prose."
    )


def test_wave_actor_guard_catches_the_v3_quantifier_evasions():
    """V3 R2 P6 hardening. The R12 fix above anchored `_WAVE_ACTOR` on a closed 4-word quantifier
    set ("each|every|any|per"). A reviewer constructed and RAN 4 sentences against the compiled
    production regex using ordinary wave-referring phrasings outside that set - "this wave", "the
    current wave", bare plural "waves", "a wave" - each asserting the identical wave-opens-PR
    policy inversion; all 4 evaded the guard. `_wave_as_pr_opener_matches` no longer keys on a
    quantifier at all (see the axis-error note above `_WAVE_ACTOR`), so all 4 must now be caught.

    Fails if: the guard regresses to requiring an enumerated quantifier before "wave" again.
    """
    verified_evasions = [
        "This wave now opens exactly one PR of its own before advancing. There is no per-wave PR "
        "restriction preventing this any longer - this wave independently opens exactly one PR, "
        "reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run advances to the "
        "next wave.",
        "The current wave now opens exactly one PR of its own before advancing. There is no "
        "per-wave PR restriction preventing this any longer - the current wave independently opens "
        "exactly one PR, reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run "
        "advances to the next wave.",
        "Waves now open exactly one PR of their own before advancing. There is no per-wave PR "
        "restriction preventing this any longer - waves independently open exactly one PR, "
        "reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run advances to the "
        "next wave.",
        "A wave now opens exactly one PR of its own before advancing. There is no per-wave PR "
        "restriction preventing this any longer - a wave independently opens exactly one PR, "
        "reviewed and gated by odoo-pr-monitoring's l2-merge-gate before the run advances to the "
        "next wave.",
    ]
    for sentence in verified_evasions:
        low = sentence.lower()
        # each candidate still satisfies every OTHER assertion, same trap shape as the meta-test above.
        assert "no per-wave pr" in low
        assert _SINGLE_RUN_PR_RE.search(low)
        assert not _PER_WAVE_PR_INVERSION_RE.search(low)
        assert "odoo-pr-monitoring" in low and "l2-merge-gate" in low
        assert _wave_as_pr_opener_search(low), (
            f"the wave-as-PR-opener guard must catch the verified V3 evasion: {sentence!r}"
        )


def test_wave_negation_guard_survives_variable_word_gaps():
    """False-positive regression guard. `_wave_as_pr_opener_matches` excludes a wave-actor under a
    same-clause negation, via a bounded WINDOW check rather than a fixed-width lookbehind, so an
    arbitrary number of words between the negation and 'wave' is still excluded correctly - not
    just the exact 'no per-wave'/'not per-wave' adjacency. Measured real text this must never flag:
    'one PR, not one per wave (git-ops open-PR -> odoo-pr-monitoring merge)' - here 'wave' precedes
    'open-pr' within the proximity window, but 'not one per ' (3 words) sits between the negation
    and 'wave', wider than a simple '(?<!not )' lookbehind would tolerate.

    This is not a pin of the guard's own blind spot - it pins the opposite: this is legitimate,
    already-correct prose (the negation of a per-wave PR policy), and must stay excluded.

    Fails if: a future edit narrows the negation check back to fixed-width adjacency and this real
    sentence starts firing again.
    """
    real_negated_text = (
        "this is the ONE land mechanism for the whole run - one pr, not one per wave "
        "(git-ops open-pr -> odoo-pr-monitoring merge); no local merge into the principal checkout"
    )
    assert not _wave_as_pr_opener_search(real_negated_text), (
        "the wave-as-PR-opener guard must not fire on 'not one per wave (... open-pr ...)' - a "
        "negated, legitimate mention, not a policy-inverting claim."
    )
