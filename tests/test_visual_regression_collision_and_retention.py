"""Behavioral guards for two runtime-review findings against odoo-visual-regression/SKILL.md
(PR #189 final-batch review, findings F1/F7 and F8 - both marked WRONG).

F7 (collision): the PR's own commit message claims two concurrent visual-regression runs no
longer collide on the comparison-set path, because it moved that path from a slug-less SHARE
location to a per-run ISOLATE `<slug>/` subdir. But `<ISOLATE_DIR>` is worktree-keyed, not
run-keyed (this skill is exempt from worktree provisioning), and the standalone `<slug>`
derivation had no anti-collision component - two concurrent standalone invocations sharing the
identical comparison intent (a retry, or two callers independently checking the same
before/after) derived the IDENTICAL slug and hence the identical path. The fix reuses the SAME
suffix mechanism `odoo-intake/references/phase-p-run-dag.md:43` already uses for its run id
(`<short-intent-slug>-<YYYYMMDD>-<4 random chars>`) rather than inventing a second one.

F8 (retention): the comparison-set cleanup fired only "after the Round-4 verdict is recorded" -
no failure-path clause, no TTL, no hook - so a run that fails, is abandoned, or is interrupted
left its comparison set on disk forever, reintroducing the unbounded-growth risk retention was
added to prevent. The fix gives retention (a) an unconditional trigger covering every terminal
status (DONE/BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT alike), enforced by the agent executing the skill
at its own terminal-status emission, and (b) a TTL-based orphan-sweep backstop (mtime > 24h)
for the crash/interrupted case no terminal-status prose can reach, enforced by whoever runs this
skill next, at Round 0.

Each test fails for exactly one reason, stated in its own docstring/message.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILL = PLUGIN / "skills" / "odoo-visual-regression" / "SKILL.md"


def _text() -> str:
    assert SKILL.exists(), f"odoo-visual-regression/SKILL.md not found at {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Collapse hard-wrapped markdown prose to single spaces for multi-word substring checks."""
    return re.sub(r"\s+", " ", text)


def _paragraphs(text: str) -> list[str]:
    return re.split(r"\n\s*\n", text)


# --------------------------------------------------------------------------- #
# F7 - the standalone slug derivation must carry an anti-collision component,
# reusing phase-p-run-dag.md's existing suffix mechanism (not a new one).
# --------------------------------------------------------------------------- #


def test_standalone_slug_derivation_carries_a_random_suffix():
    """The standalone-invocation slug rule must mint a random-chars suffix, not just a stable
    derivation from intent text.

    Fails if: the slug rule reverts to "derive ONE stable ... slug from the comparison intent"
    with no random/collision-breaking component - two concurrent runs on the identical intent
    would then derive the identical slug again (the exact defect this test guards).
    """
    norm = _norm(_text())
    assert re.search(r"4 random chars", norm), (
        "odoo-visual-regression/SKILL.md: the standalone slug derivation must mint a random-chars "
        "suffix (the anti-collision component) - without it, two concurrent standalone runs "
        "sharing the identical comparison intent derive the identical slug and collide."
    )


def test_standalone_slug_derivation_reuses_phase_p_run_dag_mechanism_not_a_new_one():
    """The anti-collision suffix must cite the EXISTING phase-p-run-dag.md:43 mechanism by path,
    proving it is reused rather than a freshly invented, divergent scheme.

    Fails if: the citation to the run-id mechanism this fix reuses is missing or the file path
    is wrong.
    """
    norm = _norm(_text())
    assert "phase-p-run-dag.md:43" in norm, (
        "odoo-visual-regression/SKILL.md: the slug-suffix fix must cite "
        "'phase-p-run-dag.md:43' - the file/line that already defines the "
        "'<short-intent-slug>-<YYYYMMDD>-<4 random chars>' mechanism for exactly this purpose - "
        "so the fix reuses it instead of inventing a second, divergent anti-collision scheme."
    )


def test_two_concurrent_same_intent_slugs_are_provably_different():
    """A worked example of two concurrent same-intent runs must show DIFFERENT derived slugs
    (not merely assert the rule exists in the abstract).

    Fails if: no two distinct example slugs sharing the same intent-slug/date prefix but a
    different random suffix appear in the file - i.e. the fix is asserted but never demonstrated.
    """
    norm = _norm(_text())
    m = re.search(
        r"`([a-z0-9-]+-20\d{6}-[a-z0-9]{4})`\s+and\s+`([a-z0-9-]+-20\d{6}-[a-z0-9]{4})`", norm
    )
    assert m, (
        "odoo-visual-regression/SKILL.md: expected a worked example pairing two concrete slugs "
        "of the shape '<intent>-<YYYYMMDD>-<4chars>' to demonstrate two concurrent same-intent "
        "runs mint different slugs."
    )
    slug_a, slug_b = m.group(1), m.group(2)
    assert slug_a != slug_b, "the two example slugs must differ"
    prefix_a = slug_a.rsplit("-", 1)[0]
    prefix_b = slug_b.rsplit("-", 1)[0]
    assert prefix_a == prefix_b, (
        f"the two example slugs must share the SAME intent-slug + date prefix (proving same "
        f"intent, same day) and differ ONLY in the random suffix; got {slug_a!r} vs {slug_b!r}"
    )


# --------------------------------------------------------------------------- #
# F8 - retention must cover every terminal status, not only the happy DONE
# path, plus a TTL backstop for a run that never reaches a terminal status.
# --------------------------------------------------------------------------- #


def test_retention_paragraph_covers_blocked_and_needs_context_not_only_done():
    """The Retention rule paragraph must explicitly trigger on BLOCKED/NEEDS_CONTEXT (or
    NEEDS_NEXT), not only after a successful Round-4 verdict.

    Fails if: the Retention paragraph reverts to gating cleanup strictly on "after the Round-4
    verdict is recorded" with no failure-path branch - a run that fails, is abandoned, or is
    interrupted would then leak its comparison set forever (the original F8 defect).
    """
    body = _text()
    paras = [p for p in _paragraphs(body) if "Retention" in p and "rm -rf" in p]
    assert paras, (
        "odoo-visual-regression/SKILL.md: no paragraph combines 'Retention' with the "
        "'rm -rf' cleanup command."
    )
    para = _norm(paras[0])
    assert "BLOCKED" in para, "Retention paragraph must explicitly name BLOCKED as a trigger."
    assert "NEEDS_CONTEXT" in para, (
        "Retention paragraph must explicitly name NEEDS_CONTEXT as a trigger."
    )
    assert re.search(r"(?i)ALL terminal paths|every terminal status", para), (
        "Retention paragraph must state it covers ALL terminal paths / every terminal status, "
        "not only the happy DONE path."
    )


def test_retention_names_an_enforcer():
    """The retention rule must name WHO enforces it (decidability requirement), not leave
    enforcement implicit.

    Fails if: no 'Enforcer:' statement is attached to the retention rule.
    """
    norm = _norm(_text())
    assert "Enforcer: the agent executing this skill" in norm, (
        "odoo-visual-regression/SKILL.md: the retention rule must name its enforcer explicitly "
        "('Enforcer: the agent executing this skill ...') so the obligation is decidable, not "
        "merely implied."
    )


def test_ttl_backstop_sweep_present_with_a_bounded_threshold():
    """A TTL-bounded orphan sweep must exist for the crash/interrupted-run case the
    terminal-status retention rule cannot reach (nothing runs teardown prose after a `-9`).

    Fails if: no `find` sweep over `visual/current/` with a numeric `-mmin` (or `-mtime`)
    threshold exists - i.e. there is no backstop for an abandoned run's directory at all.
    """
    norm = _norm(_text())
    assert re.search(r"find <ISOLATE_DIR>/visual/current/.*-mmin \+\d+", norm), (
        "odoo-visual-regression/SKILL.md: expected a bounded 'find ... visual/current/ ... "
        "-mmin +<N>' orphan-sweep command - the TTL backstop for a run that crashed or was "
        "abandoned before it could delete its own comparison set."
    )
    assert re.search(r"(?i)orphan sweep", norm), (
        "odoo-visual-regression/SKILL.md: the TTL backstop must be named/labelled (e.g. "
        "'Orphan sweep') so it reads as a distinct, deliberate rule rather than a stray command."
    )


def test_ttl_backstop_runs_before_minting_this_runs_own_slug():
    """The orphan sweep must run BEFORE this run mints its own slug, so it never races with or
    deletes the directory this same run is about to create.

    Fails if: the sweep instruction is not textually ordered before the slug-minting sentence
    in Round 0.
    """
    body = _text()
    round0_start = body.index("### Round 0")
    round1_start = body.index("### Round 1")
    round0 = body[round0_start:round1_start]
    sweep_pos = round0.find("find <ISOLATE_DIR>/visual/current/")
    slug_mint_pos = round0.find("derive `<intent-slug>-<YYYYMMDD>-<4 random chars>`")
    assert sweep_pos != -1, "Round 0 must contain the orphan-sweep find command."
    assert slug_mint_pos != -1, "Round 0 must contain the slug-minting instruction."
    assert sweep_pos < slug_mint_pos, (
        "The orphan sweep must be textually ordered BEFORE this run mints its own slug in "
        "Round 0 - otherwise the sweep could race with (or delete) the directory this run is "
        "about to create."
    )
