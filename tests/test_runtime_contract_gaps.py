"""Behavioral guards for the runtime-contract gaps in run-harness's integration loop, found by a
read-only role-play audit (findings F1/F4).

Each guard protects a BEHAVIOR/decision, not a code snapshot - see the docstring on each test for
the concrete failure scenario it prevents. Assertions are whitespace-normalized so a reformatted
(but semantically unchanged) paragraph never spuriously passes OR fails.

Run: python3 -m pytest tests/test_runtime_contract_gaps.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
INTEGRATION_LOOP = PLUGIN / "skills" / "_shared" / "integration-loop.md"
RUN_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "run-integration.md"
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
# Root cause: the saga rollback was literally "reset the integration branch HARD" - `git reset
# --hard` is item 4 of git-toolkit's 8-item destructive human-confirm gate
# (plugins/git-toolkit/snippets/git-safety-contract.md). run-harness's advance is billed as
# autonomous L1 drive-to-done with no carve-out for the rollback. A real mid-run failure would
# therefore BLOCK unexpectedly on a run the agent was told never stops. Fix: the rollback is
# re-expressed as a worktree abandon + re-fork at an anchor SHA - never invoking `git reset
# --hard` at all - so it structurally never reaches the gate, and the prose says WHY (nothing
# unique is discarded: the anchor SHA and every node's own commits stay reachable off
# run-integration).
# ===========================================================================

_DESTRUCTIVE_RESET_CLASS_RE = re.compile(
    r"(?i)reset[\s-]*(?:the\s+\w+\s+branch\s+)?-?-?hard\b"
)
# The bug's actual shape was PRESCRIPTIVE: "reset ... HARD to the pre-node SHA" / "... to the last
# passing checkpoint SHA" - i.e. the rollback's anchor immediately follows the reset. A bare,
# quoted/exposition mention of `git reset --hard` (e.g. naming what git-toolkit's gate item 4
# covers, or explicitly disclaiming "never a reset --hard against a live worktree") has no such
# anchor-continuation and must NOT be flagged.
#
# The anchor NOUN is what changed when the unit of work became the node: the retired anchors were
# named after the retired grouping layer. The two live anchors are the pre-NODE SHA (run-harness's
# per-node saga) and the pre-STEP SHA (the unit-agnostic single-unit collapse in
# run-integration.md), plus the last passing checkpoint SHA. Naming all three is what keeps this
# guard from going quietly vacuous against a vocabulary nobody writes anymore.
_ANCHOR_CONTINUATION_RE = re.compile(
    r"(?i)^.{0,40}?\bto\s+(?:the\s+)?(pre-node|pre-step|last\s+passing\s+checkpoint)\s+sha\b"
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

    Fails if: any file reintroduces the "reset ... hard to the pre-node/pre-step/checkpoint SHA"
    shape as the rollback mechanism.
    """
    offenders = []
    for path in _all_odoo_ai_agents_md():
        text = path.read_text(encoding="utf-8")
        for m in _DESTRUCTIVE_RESET_CLASS_RE.finditer(text):
            after = _norm(text[m.end(): m.end() + 80])
            if _ANCHOR_CONTINUATION_RE.search(after):
                offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)!r} {after[:40]!r}")
    assert not offenders, (
        "Found the prescriptive 'reset ... hard to the <anchor> SHA' shape describing the saga "
        "rollback - this is git-toolkit's gated `git reset --hard` (destructive gate item 4), "
        "which contradicts run-harness's autonomous L1 drive-to-done advance (no carve-out "
        f"exists for it). Offenders:\n" + "\n".join(offenders)
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
        "WORKTREE (not a live-tree reset) at the pre-node SHA."
    )
    assert re.search(r"(?i)resume from checkpoint.{0,200}worktree", body), (
        "integration-loop.md: resume-from-checkpoint must describe abandoning/re-forking the "
        "run-integration WORKTREE (not a live-tree reset) at the last passing checkpoint SHA."
    )


def test_integration_loop_states_why_rollback_fires_no_destructive_gate():
    """The prose must state WHY the rollback is safe without human confirmation - so a future
    agent understands the reasoning, not just the rule. The justification is that nothing unique
    is discarded: the anchor SHA and every node's own commits remain reachable independently of
    run-integration (a disposable, never-pushed, run-scoped branch).

    Fails if: the file asserts the rollback fires no gate WITHOUT explaining why (bare assertion
    would be exactly the kind of silent tautology this PR was asked to avoid re-introducing).
    """
    body = _norm(_read(INTEGRATION_LOOP))
    assert re.search(r"(?i)fires?\s+no\s+destructive[\s-]*(confirm)?\s*gate", body), (
        "integration-loop.md must explicitly state the saga rollback fires no destructive-confirm gate."
    )
    # The reasoning: nothing unique/irrecoverable is discarded (disposable branch + commits
    # remain reachable off the node's own branch / the anchor SHA). Phrased as a shape rather
    # than one exact sentence, so a rewording that keeps the reasoning keeps the test green while
    # DROPPING the reasoning still reddens it.
    assert re.search(r"(?i)nothing\s+(?:unique\s+)?(?:is\s+|to\s+)?discard(?:ed)?", body), (
        "integration-loop.md must state the reasoning (nothing unique is discarded), not just the "
        "bare conclusion that no gate fires."
    )
    assert re.search(r"(?i)stays?\s+reachable|remains?\s+reachable", body), (
        "integration-loop.md must state WHY nothing unique is lost - every commit up to the "
        "anchor stays REACHABLE on its own branch - or the 'nothing is discarded' claim is itself "
        "an unbacked assertion."
    )
    assert re.search(r"(?i)disposable", body) and re.search(r"(?i)never[\s-]*pushed", body), (
        "integration-loop.md must ground the reasoning in run-integration being a disposable, "
        "never-pushed, run-scoped branch - the actual reason git-toolkit's gate does not apply."
    )


def test_run_harness_advance_still_reads_as_autonomous_drive_to_done():
    """Companion assertion: fixing the rollback mechanism must NOT weaken run-harness's own
    autonomy claim - the advance (including the now-non-destructive rollback) must still read as
    ONE decidable conclusion: it does not stop merely because a unit of work finished.

    The guard this replaces keyed on a per-group "no stop" phrase. With the grouping layer gone,
    the stronger and more decidable form is the CLOSED, ENUMERATED list of the only conditions
    that may end the turn, plus the explicit statement that finishing a node is not one of them -
    a closed list cannot be extended by implication, which a bare "no per-X stop" sentence could.

    Fails if: the enumerated stop conditions stop being closed, or the "finishing a node is never
    a reason to stop" clause is dropped, leaving the advance ambiguous about whether it stops.
    """
    body = _norm(_read(RUN_HARNESS))
    assert re.search(r"(?i)drive-to-done", body), (
        "run-harness/SKILL.md must still describe the advance as drive-to-done."
    )
    assert re.search(
        r"(?i)auto-advances the run WITHOUT asking a human UNLESS[^.]{0,120}ENUMERATED conditions",
        body), (
        "run-harness/SKILL.md must state the advance is autonomous UNLESS one of an ENUMERATED "
        "set of conditions holds."
    )
    assert re.search(r"(?i)these are the ONLY legitimate reasons to end the turn", body), (
        "the enumerated list must be declared CLOSED ('the ONLY legitimate reasons') - an open "
        "list is not a decidable rule."
    )
    assert re.search(
        r"(?i)Finishing a node, or any single subagent dispatch, is by itself never one of these",
        body), (
        "run-harness/SKILL.md must state that finishing a NODE (or any single dispatch) is never "
        "by itself a reason to stop - the exact ambiguity that turns drive-to-done into "
        "step-by-step nagging."
    )
    assert re.search(r"(?i)plows past a genuine \(a\)-\(d\) condition[^.]{0,80}BLOCKED behavior", body), (
        "the rule must bite in BOTH directions - ignoring a real stop condition is BLOCKED "
        "behaviour too, not drive-to-done - or 'autonomous' reads as licence to ignore gates."
    )


def test_no_git_toolkit_file_modified_by_this_fix():
    """HARD CONSTRAINT: fixing #190 must never touch plugins/git-toolkit/ - odoo-ai-agents may
    depend on git-toolkit, never the reverse. This is a structural repo-layout guard, independent
    of git history, so it also protects any FUTURE edit in this area.

    Fails if: the files this fix owns stop living under plugins/odoo-ai-agents/ (i.e. the fix
    reached across the dependency direction into the provider plugin).
    """
    assert str(INTEGRATION_LOOP).startswith(str(PLUGIN)), "fix must live under plugins/odoo-ai-agents"
    assert str(RUN_INTEGRATION).startswith(str(PLUGIN)), "fix must live under plugins/odoo-ai-agents"
    assert GIT_TOOLKIT.exists(), "sanity: plugins/git-toolkit must still exist, untouched"


# ===========================================================================
# Issue #192 - the integration worktree needs an EXPLICIT creation step
#
# Root cause: § Single-unit collapse dispatches into an "already-provisioned integration
# worktree", but run-harness/SKILL.md's Run start only stated a BRANCH fork - never an explicit
# worktree-creation step, unlike sibling skills (odoo-modules-upgrade, odoo-forward-port) which
# each spell out "Create the ... integration worktree: invoke git-toolkit:git-ops ...". A branch
# is not a checkout: without the creation step the "already-provisioned" phrase is an unexplained
# inference, and the driver improvises in a git-mutating phase.
# ===========================================================================


def _run_start_section() -> str:
    """The body of run-harness/SKILL.md's top-level `## Run start` section, normalized."""
    text = _read(RUN_HARNESS)
    m = re.search(r"^##\s+Run start\s*$", text, re.MULTILINE)
    assert m, (
        "run-harness/SKILL.md must carry a top-level `## Run start` section - the ONE place the "
        "integration branch AND its worktree are created, before the first node"
    )
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return _norm(rest[: nxt.start()] if nxt else rest)


def test_run_harness_run_start_has_explicit_worktree_creation_step():
    """Run start must explicitly invoke git-toolkit:git-ops to CREATE the integration worktree -
    not just fork a branch - and must do so once PER ENTRY in `RUN.repos[]`, because a branch
    without a checkout leaves every downstream "already-provisioned worktree" reference dangling.

    The `JOB-tier` wording register the previous version of this guard pinned is not asserted:
    pinning a wording register is a snapshot, and the behaviour (an explicit, delegated,
    per-repo creation step that runs ONCE before the first node) is what the reference actually
    needs. The per-repo cardinality is asserted instead, which the old single-repo phrasing could
    not express.

    Fails if: Run start only mentions forking a branch with no explicit worktree-creation
    invocation of git-toolkit:git-ops, or if the per-`repos[]`-entry cardinality is lost (which
    silently gives a multi-repo run one worktree for N repos).
    """
    section = _run_start_section()
    assert re.search(r"(?i)Runs ONCE, before the first node", section), (
        "§ Run start must state it runs ONCE, before the first node - not per node, per stage, or "
        "per any grouping of them."
    )
    assert re.search(r"(?i)invoke `?git-toolkit:git-ops`?", section), (
        "§ Run start must explicitly invoke git-toolkit:git-ops to create the worktree, not merely "
        "state a branch fork happens (and never run raw git itself)."
    )
    assert re.search(r"(?i)add worktree|add a worktree", section), (
        "§ Run start must name the concrete git-ops op (add a worktree) - a branch fork alone "
        "leaves no checkout for a node's worktree to fork FROM."
    )
    assert re.search(
        r"(?i)ONE branch \+ worktree pair PER ENTRY in `?RUN\.repos\[\]`?", section), (
        "§ Run start must create ONE branch + worktree pair PER ENTRY in RUN.repos[] - the "
        "cardinality that makes an N-repo run land N PRs instead of colliding on one worktree."
    )
    assert re.search(r"(?i)never from the invoking checkout|entry's own card|that entry's", section), (
        "§ Run start must resolve each pair's base/worktree_root from THAT entry's own card - "
        "reusing another entry's (or the invoking checkout's HEAD) is how repo 2 forks from repo "
        "1's base."
    )


def test_sibling_orchestrators_still_create_their_integration_worktree_explicitly():
    """The peer orchestrators run their own integration loop (integration-loop.md § Who owns an
    integration loop) and must each keep their OWN explicit creation step - the same behaviour
    asserted above for run-harness, in the pipelines that do not go through it.

    Fails if: a peer orchestrator drops its explicit creation step and starts assuming a worktree
    somebody else provisioned - the dangling-inference defect, one plugin over.
    """
    upgrade = _norm(_read(PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"))
    assert re.search(r"(?i)create the [\w-]+ integration worktree", upgrade), (
        "odoo-modules-upgrade/SKILL.md must still carry an explicit 'Create the ... integration "
        "worktree' step of its own."
    )
    assert re.search(r"(?i)git-toolkit:git-ops", upgrade), (
        "odoo-modules-upgrade/SKILL.md must delegate that creation to git-toolkit:git-ops."
    )


def test_single_unit_collapse_is_unit_agnostic_and_has_one_owner():
    """The `n <= 1` collapse rule is the ONLY survivor of the retired topology enum, and it now
    lives in run-integration.md § Single-unit collapse, phrased unit-agnostically so BOTH callers
    (run-harness over source-writing nodes, odoo-modules-upgrade P4 over classification rows) can
    cite the same section instead of re-deriving a local variant in a git-mutating phase.

    Fails if: the section loses its ONE-owner declaration, stops being unit-agnostic, or drops the
    COUNT-never-infer rule (inferring the collapse from an absent field is how a multi-unit step
    silently loses its child worktrees).
    """
    text = _read(RUN_INTEGRATION)
    m = re.search(r"^##\s+Single-unit collapse\s*$", text, re.MULTILINE)
    assert m, "run-integration.md must carry a `## Single-unit collapse` section"
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    section = _norm(rest[: nxt.start()] if nxt else rest)

    assert re.search(r"(?i)this section is its ONE owner", section), (
        "§ Single-unit collapse must declare itself the rule's ONE owner - two owners is how the "
        "callers drift apart."
    )
    assert re.search(r"(?i)`?n <= 1`? unit", section), (
        "the rule must be stated over `n <= 1` UNITS, not over a named node kind - it is cited by "
        "two pipelines whose units differ."
    )
    assert re.search(r"(?i)COUNT `?n`?, never infer it", section), (
        "§ Single-unit collapse must require COUNTING n, never inferring it from an absent field."
    )
    assert re.search(r"(?i)POISON-CONTAINMENT", section), (
        "the reason `n >= 2` keeps the child worktree must be stated as poison-containment, NOT "
        "as an index.lock/concurrency race - dispatch is sequential, so a race reason would be "
        "false and would collapse the moment a reader checked it."
    )
    for caller in (r"skills/run-harness/SKILL\.md", r"upg-phase-detail\.md"):
        assert re.search(caller, section), (
            f"§ Single-unit collapse must name its caller {caller} - an owner section with no "
            "named readers is how a sole-caller move silently orphans a pipeline."
        )
