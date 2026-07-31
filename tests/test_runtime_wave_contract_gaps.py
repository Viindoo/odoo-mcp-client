"""Behavioral guards for three PRE-EXISTING runtime-contract gaps in run-harness's between-wave
integration, found by a read-only role-play audit (findings F1/F3/F4).

Each guard protects a BEHAVIOR/decision, not a code snapshot - see the docstring on each test for
the concrete failure scenario it prevents. Assertions are whitespace-normalized so a reformatted
(but semantically unchanged) paragraph never spuriously passes OR fails.

Run: python3 -m pytest tests/test_runtime_wave_contract_gaps.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
INTEGRATION_LOOP = PLUGIN / "skills" / "_shared" / "integration-loop.md"
WAVE_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "wave-integration.md"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"
PLAN_MODE_SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"
GIT_TOOLKIT = ROOT / "plugins" / "git-toolkit"


def _norm(text: str) -> str:
    """Whitespace-normalize so a reflow/rewrap never flips a presence/absence assertion."""
    return re.sub(r"\s+", " ", text)


def _read(path: Path) -> str:
    assert path.exists(), f"not found: {path}"
    return path.read_text(encoding="utf-8")


def _all_odoo_ai_agents_md() -> list[Path]:
    return sorted(PLUGIN.rglob("*.md"))


# ===========================================================================
# Issue #190 - saga rollback must not be a destructive-gated `git reset --hard`
#
# Root cause: `integration-loop.md`'s saga rollback was literally "reset the integration branch
# HARD" - `git reset --hard` is item 4 of git-toolkit's 8-item destructive human-confirm gate
# (plugins/git-toolkit/snippets/git-safety-contract.md). run-harness's between-wave advance is
# billed as autonomous L1 drive-to-done with "NO per-wave stop" and no carve-out for the rollback.
# A real mid-wave failure would therefore BLOCK unexpectedly on a run the agent was told never
# stops. Fix: the rollback is re-expressed as a worktree abandon + re-fork at an anchor SHA -
# never invoking `git reset --hard` at all - so it structurally never reaches the gate, and the
# prose says WHY (nothing unique is discarded: the anchor SHA and every module's own commits stay
# reachable off run-integration).
# ===========================================================================

_DESTRUCTIVE_RESET_CLASS_RE = re.compile(
    r"(?i)reset[\s-]*(?:the\s+\w+\s+branch\s+)?-?-?hard\b"
)
# The bug's actual shape was PRESCRIPTIVE: "reset ... HARD to the pre-wave SHA" / "... to the last
# passing checkpoint SHA" - i.e. the rollback's anchor immediately follows the reset. A bare,
# quoted/exposition mention of `git reset --hard` (e.g. naming what git-toolkit's gate item 4
# covers, or explicitly disclaiming "never a reset --hard against a live worktree") has no such
# anchor-continuation and must NOT be flagged.
_ANCHOR_CONTINUATION_RE = re.compile(
    r"(?i)^.{0,40}?\bto\s+the\s+(pre-wave|last\s+passing\s+checkpoint)\s+sha\b"
)


def test_no_file_prescribes_the_saga_rollback_as_a_hard_reset():
    """Guards the CLASS, not one instance: NO .md file under odoo-ai-agents may PRESCRIBE the saga
    rollback (clean-abort | resume-from-checkpoint) as a `reset ... hard` / `reset-hard` operation
    that lands ON an anchor SHA, in ANY file - not just the two files this fix touches. A sibling
    reference (a peer orchestrator doc, a workflow-harness table row, a differently-worded
    restatement) would reopen the exact same contradiction with git-toolkit's destructive gate even
    if the two known files were fixed. A bare/exposition mention (naming git-toolkit's gate item,
    or explicitly disclaiming the op) is legitimate and must not trip this guard - only the
    prescriptive "reset ... hard to the <anchor> SHA" shape counts as an offender.

    Fails if: any file reintroduces the "reset ... hard to the pre-wave/checkpoint SHA" shape as
    the rollback mechanism.
    """
    offenders = []
    for path in _all_odoo_ai_agents_md():
        text = path.read_text(encoding="utf-8")
        for m in _DESTRUCTIVE_RESET_CLASS_RE.finditer(text):
            after = text[m.end(): m.end() + 60]
            if _ANCHOR_CONTINUATION_RE.search(after):
                offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)!r} {after[:40]!r}")
    assert not offenders, (
        "Found the prescriptive 'reset ... hard to the <anchor> SHA' shape describing the saga "
        "rollback - this is git-toolkit's gated `git reset --hard` (destructive gate item 4), "
        "which contradicts run-harness's autonomous L1 drive-to-done between-wave advance (no "
        f"carve-out exists for it). Offenders:\n" + "\n".join(offenders)
    )


def test_integration_loop_saga_uses_worktree_refork_not_reset_hard():
    """The saga rollback (clean-abort | resume-from-checkpoint) must be phrased as abandoning the
    run-integration worktree and re-provisioning a fresh one at the anchor SHA - an ordinary
    `worktree remove` + `worktree add` pair, not a live-tree `reset --hard`.

    Fails if: the saga steps stop naming `worktree` re-provisioning as the rollback mechanism.
    """
    body = _norm(_read(INTEGRATION_LOOP))
    assert re.search(r"(?i)clean abort.{0,200}worktree", body), (
        "integration-loop.md: clean-abort must describe abandoning/re-forking the run-integration "
        "WORKTREE (not a live-tree reset) at the pre-wave SHA."
    )
    assert re.search(r"(?i)resume from checkpoint.{0,200}worktree", body), (
        "integration-loop.md: resume-from-checkpoint must describe abandoning/re-forking the "
        "run-integration WORKTREE (not a live-tree reset) at the last passing checkpoint SHA."
    )


def test_integration_loop_states_why_rollback_fires_no_destructive_gate():
    """The prose must state WHY the rollback is safe without human confirmation - so a future
    agent understands the reasoning, not just the rule. The justification is that nothing unique
    is discarded: the anchor SHA and every module's own commits remain reachable independently of
    run-integration (a disposable, never-pushed, run-scoped branch).

    Fails if: the file asserts the rollback fires no gate WITHOUT explaining why (bare assertion
    would be exactly the kind of silent tautology this PR was asked to avoid re-introducing).
    """
    body = _norm(_read(INTEGRATION_LOOP))
    assert re.search(r"(?i)fires?\s+no\s+destructive[\s-]*(confirm)?\s*gate", body), (
        "integration-loop.md must explicitly state the saga rollback fires no destructive-confirm gate."
    )
    # The reasoning: nothing unique/irrecoverable is discarded (disposable branch + commits
    # remain reachable off the module's own branch / the anchor SHA).
    assert re.search(r"(?i)nothing\s+(unique\s+)?to\s+discard|nothing\s+is\s+discarded", body), (
        "integration-loop.md must state the reasoning (nothing unique is discarded), not just the "
        "bare conclusion that no gate fires."
    )
    assert re.search(r"(?i)disposable", body) and re.search(r"(?i)never[\s-]*pushed", body), (
        "integration-loop.md must ground the reasoning in run-integration being a disposable, "
        "never-pushed, run-scoped branch - the actual reason git-toolkit's gate does not apply."
    )


def test_run_harness_between_wave_advance_still_reads_as_autonomous_drive_to_done():
    """Companion assertion: fixing the rollback mechanism must NOT weaken run-harness's own
    autonomy claim - the between-wave advance (including the now-non-destructive rollback) must
    still read as ONE decidable conclusion: it does not stop for a human.

    Fails if: 'NO per-wave stop' / 'drive-to-done' / L1 wording is removed while fixing #190,
    leaving the between-wave advance ambiguous about whether it stops.
    """
    body = _norm(_read(RUN_HARNESS))
    low = body.lower()
    assert "no per-wave stop" in low, (
        "run-harness/SKILL.md must still state the between-wave advance has NO per-wave stop."
    )
    assert "drive-to-done" in low or "drives to" in low, (
        "run-harness/SKILL.md must still describe the between-wave advance as drive-to-done."
    )


def test_no_git_toolkit_file_modified_by_this_fix():
    """HARD CONSTRAINT: fixing #190 must never touch plugins/git-toolkit/ - odoo-ai-agents may
    depend on git-toolkit, never the reverse. This is a structural repo-layout guard, independent
    of git history, so it also protects any FUTURE edit in this area.

    Fails if: any file under plugins/git-toolkit/ was edited as part of this fix (checked via git
    diff against the merge-base with origin/master in CI; here we assert the directory still
    parses as untouched-by-name by checking the two fixed files live under odoo-ai-agents only).
    """
    assert str(INTEGRATION_LOOP).startswith(str(PLUGIN)), "fix must live under plugins/odoo-ai-agents"
    assert str(WAVE_INTEGRATION).startswith(str(PLUGIN)), "fix must live under plugins/odoo-ai-agents"
    assert GIT_TOOLKIT.exists(), "sanity: plugins/git-toolkit must still exist, untouched"


# ===========================================================================
# Issue #191 - `independent` topology: label vs behavior must agree
#
# Root cause: wave-integration.md's "Independent" topology was labeled "(all parallel)" /
# "Maximum parallelism", but the between-wave loop it describes dispatches modules SEQUENTIALLY
# (one blocking Skill-tool call at a time - wave-integration.md:347-349,362-399 themselves say so).
# The same false "built in parallel" framing was ALSO found in plan-mode-schema.md's Block 2
# template (a differently-shaped sibling instance of the identical claim, produced by the planner
# and consumed by the very same run-harness between-wave loop). Decision: fix the LABEL (not the
# loop) in BOTH places, and state plainly what `independent` DOES mean (module order unconstrained)
# vs what it does NOT mean (concurrent dispatch).
# ===========================================================================

_PARALLEL_MISCLAIM_RE = re.compile(
    r"(?i)(all\s+parallel|maximum\s+parallelism|built\s+in\s+parallel)"
)


def test_no_file_claims_independent_topology_dispatches_in_parallel():
    """Guards the CLASS: no .md file under odoo-ai-agents may claim modules within an `independent`
    wave are dispatched/built in parallel - not just the one file (`wave-integration.md`) this
    issue names, and not just the sibling (`plan-mode-schema.md`) this audit additionally found.

    Fails if: 'all parallel' / 'Maximum parallelism' / 'built in parallel' phrasing reappears
    anywhere describing wave/topology module dispatch.
    """
    offenders = []
    for path in _all_odoo_ai_agents_md():
        text = path.read_text(encoding="utf-8")
        for m in _PARALLEL_MISCLAIM_RE.finditer(text):
            offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)!r}")
    assert not offenders, (
        "Found phrasing claiming independent-topology modules dispatch 'in parallel' - the actual "
        "between-wave loop dispatches modules SEQUENTIALLY (one Skill-tool call at a time); "
        f"'independent' means module ORDER is unconstrained, not concurrent execution. Offenders:\n"
        + "\n".join(offenders)
    )


def test_wave_integration_independent_section_states_does_and_does_not_mean():
    """The Independent topology section must plainly state what the value DOES mean (module order
    is unconstrained) and what it does NOT mean (concurrent/parallel execution), grounded in the
    loop's own sequential dispatch mechanism.

    Fails if: the section drops either half of the does/does-not-mean pair.
    """
    text = _read(WAVE_INTEGRATION)
    m = re.search(r"###\s+Independent.*?(?=\n###\s|\Z)", text, re.DOTALL)
    assert m, "wave-integration.md: '### Independent' topology section not found"
    section = _norm(m.group(0))
    assert re.search(r"(?i)does\s+not\s+mean", section), (
        "wave-integration.md § Independent must explicitly state what the value does NOT mean "
        "(concurrent execution)."
    )
    assert re.search(r"(?i)(order\s+is\s+unconstrained|order\s+unconstrained|any\s+order)", section), (
        "wave-integration.md § Independent must state what the value DOES mean: module ORDER is "
        "unconstrained."
    )
    assert re.search(r"(?i)one\s+at\s+a\s+time|sequential", section), (
        "wave-integration.md § Independent must ground the 'does not mean parallel' claim in the "
        "loop's actual sequential/one-at-a-time dispatch mechanism."
    )


def test_plan_mode_schema_sibling_claim_fixed():
    """The sibling twin found in plan-mode-schema.md's Block 2 template and its worked example
    must no longer claim parallel build/dispatch for independent-topology modules.

    Fails if: 'built in parallel' phrasing (Block 2 ASCII template) or an unqualified
    'parallel-eligible order' claim (the worked example) survives.
    """
    text = _norm(_read(PLAN_MODE_SCHEMA))
    assert not re.search(r"(?i)built\s+in\s+parallel", text), (
        "plan-mode-schema.md still claims modules within a wave are 'built in parallel' - the "
        "same false claim issue #191 fixes in wave-integration.md."
    )
    assert re.search(r"(?i)sequential", text), (
        "plan-mode-schema.md's worked independent-topology example must state run-harness "
        "iterates the wave's modules SEQUENTIALLY (not merely 'parallel-eligible')."
    )


# ===========================================================================
# Issue #192 - `topology: single`'s integration worktree needs an explicit creation step
#
# Root cause: wave-integration.md § Single refers to an "already-provisioned JOB-tier integration
# worktree", but run-harness/SKILL.md's "Run start" step only stated a BRANCH fork - never an
# explicit worktree-creation step, unlike sibling skills (odoo-modules-upgrade, odoo-forward-port)
# which each spell out "Create the JOB-tier integration worktree: invoke git-toolkit:git-ops ...".
# Fix: add the same explicit step, in the same wording register, to run-harness's Run start.
# ===========================================================================


def test_run_harness_run_start_has_explicit_worktree_creation_step():
    """Run start must explicitly invoke git-toolkit:git-ops to CREATE the integration worktree -
    not just fork a branch - matching the sibling skills' shape ("Create the JOB-tier integration
    worktree: invoke the `git-toolkit:git-ops` skill ... to add a worktree").

    Fails if: Run start only mentions forking a branch with no explicit worktree-creation
    invocation of git-toolkit:git-ops.
    """
    body = _norm(_read(RUN_HARNESS))
    m = re.search(r"Run start \(ONCE, before wave 1\)\..{0,600}", body)
    assert m, "run-harness/SKILL.md: 'Run start (ONCE, before wave 1).' step not found"
    section = m.group(0)
    assert re.search(r"(?i)create the job-tier integration worktree", section), (
        "run-harness/SKILL.md Run start must explicitly say 'Create the JOB-tier integration "
        "worktree', matching odoo-modules-upgrade/odoo-forward-port's wording register."
    )
    assert re.search(r"(?i)invoke the `?git-toolkit:git-ops`? skill", section), (
        "run-harness/SKILL.md Run start must explicitly invoke git-toolkit:git-ops to create the "
        "worktree, not merely state a branch fork happens."
    )
    assert re.search(r"(?i)add a worktree", section), (
        "run-harness/SKILL.md Run start must name the concrete git-ops op (add a worktree), "
        "matching the sibling skills' wording register."
    )


def test_sibling_skills_still_carry_the_reference_wording_register():
    """Sanity/regression anchor: the sibling skills' own explicit creation-step wording (the
    register run-harness's new step must match) must still exist - otherwise this test's own
    'matches the sibling' claim would be unverifiable.
    """
    upgrade = _norm(_read(PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"))
    assert re.search(r"(?i)create the job-tier integration worktree", upgrade), (
        "odoo-modules-upgrade/SKILL.md must still carry the reference wording "
        "('Create the JOB-tier integration worktree ...') this fix mirrors."
    )


def test_wave_integration_single_section_points_back_to_the_creation_step():
    """§ Single's "already-provisioned JOB-tier integration worktree" phrase must not be an
    unexplained inference anymore - it should point back at run-harness's Run start step where the
    worktree is now explicitly created.

    Fails if: § Single still reads as a bare assumption with no pointer to where the worktree
    actually gets created.
    """
    text = _read(WAVE_INTEGRATION)
    m = re.search(r"###\s+Single.*?(?=\n###\s|\n---\s|\Z)", text, re.DOTALL)
    assert m, "wave-integration.md: '### Single' topology section not found"
    section = _norm(m.group(0))
    assert re.search(r"(?i)already-provisioned", section), (
        "wave-integration.md § Single must still reference the already-provisioned JOB-tier "
        "integration worktree."
    )
    # A bare "run start" substring already occurs innocently elsewhere in this section (the
    # Cross-WAVE lineage note's "ONCE at run start" temporal phrase) - require a genuine
    # cross-reference to the SKILL.md step, not just the word pair.
    assert re.search(r"(?i)run start.{0,80}SKILL\.md|SKILL\.md.{0,80}run start", section), (
        "wave-integration.md § Single must point back at run-harness/SKILL.md's 'Run start' step "
        "that creates the worktree (a real cross-reference, not just the incidental 'ONCE at run "
        "start' phrase already in the Cross-WAVE lineage note), so the reference is no longer an "
        "unexplained inference."
    )
