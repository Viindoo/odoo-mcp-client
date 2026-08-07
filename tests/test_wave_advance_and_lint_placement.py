"""Behavioral guards for R6 (wave-boundary auto-advance) and R7 (lint-class gate placement).

R6 - the owner observed the main agent stopping to ask at every wave in a multi-wave run. The
root cause (Phase 2 arbitration) is a SELF-CONTRADICTION inside `skills/run-harness/SKILL.md`
itself: the Gate-tier-resolution / Circuit-breakers sections state an enumerated, decidable
auto-advance contract ("AUTO-ADVANCE ... NO per-wave stop"), while Hard rule 2 stated an UNBOUNDED
escape hatch ("the human + main agent may stop at any time") with no enumeration - and
`docs/reference/workflow-harness.md` restated (rather than pointed at) that same unbounded framing
("the accepted trade-off: occasionally the main agent needs a human continue"). The fix tightens
BOTH sides to state the SAME enumerated stop-condition list, with `skills/run-harness/SKILL.md` as
the ONE owner of the runtime rule and `docs/reference/workflow-harness.md` pointing at it.

R7a/R7b - lint-class gates (`test_lint`, `test_pylint`, eslint, and siblings) move OUT of the
per-wave/per-module gate set into ONE pre-PR step, and `odoo-acceptance` + `odoo-i18n` (when they
apply) run BEFORE that lint-class step AND before the PR - never after. This module's guards cover
the files Group E owns (`skills/run-harness/**`, `docs/reference/workflow-harness.md`,
`skills/odoo-coding/**`); the companion deletions in the 4 per-module agent files
(`agents/odoo-backend-coder.md`, `agents/odoo-frontend-coder.md`, `agents/odoo-coder.md`,
`agents/odoo-code-reviewer.md`) are handed off in
`/tmp/odoo-mcp-client-research/phase2/44-handoff-E.md` (Group E does not own `agents/*.md`) -
the whole-tree scan below is intentionally NOT scoped to only "safe" files, so it also measures
that pending, known-and-tracked gap rather than hiding it.

These are CONTRACT / BEHAVIOR checks (a rule is present, decidable, and in the right place), not
line-count snapshots.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

RUN_HARNESS_SKILL = PLUGIN / "skills" / "run-harness" / "SKILL.md"
WAVE_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "wave-integration.md"
WORKFLOW_HARNESS_DOC = PLUGIN / "docs" / "reference" / "workflow-harness.md"
ODOO_CODING_SKILL = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"


def _read(p: Path) -> str:
    assert p.exists(), f"expected file missing: {p}"
    return p.read_text(encoding="utf-8")


def _norm_ws(s: str) -> str:
    """Collapse all whitespace runs to a single space, lowercase - so a guard is not defeated by
    a line-wrap, a double-space, or a case change (the 'guard-test trap' this repo has been bitten
    by before: a pattern tied to one exact rendering walks right past a re-wrapped paragraph)."""
    return re.sub(r"\s+", " ", s).lower()


# ---------------------------------------------------------------------------
# R6 - no unbounded stop-permission clause anywhere in the plugin tree
# ---------------------------------------------------------------------------

# The two exact phrasings the Phase-2 survey found as the root cause (both were repo-unique
# before the fix - confirmed by direct grep on the pre-fix tree). Matched on NORMALIZED text so a
# rewrap can't hide a reintroduction.
UNBOUNDED_STOP_PATTERNS = [
    re.compile(r"may stop at any time"),
    re.compile(r"accepted trade-off"),
    re.compile(r"occasionally the main agent needs a human"),
]


def _all_plugin_md_files():
    return sorted(PLUGIN.rglob("*.md"))


def test_no_unbounded_stop_permission_phrase_anywhere_in_plugin():
    """Behavior protected: the main agent is never told, anywhere, that it may pause simply
    because it feels like it. Scans the WHOLE plugin tree (every .md file), not just the two
    files the fix touched - a reintroduction anywhere is the same bug recurring.

    Fails if any of the two retired unbounded phrasings resurfaces, in ANY file, in ANY casing or
    line-wrap (text is whitespace-normalized before matching).
    """
    offenders = []
    for f in _all_plugin_md_files():
        norm = _norm_ws(_read(f))
        for pat in UNBOUNDED_STOP_PATTERNS:
            if pat.search(norm):
                offenders.append(f"{f.relative_to(REPO_ROOT)}: matched {pat.pattern!r}")
    assert not offenders, (
        "Unbounded stop-permission phrasing found (R6 regression) - a run may stop for no "
        "enumerated reason:\n" + "\n".join(offenders)
    )


def test_run_harness_states_the_enumerated_auto_advance_contract():
    """Behavior protected: `skills/run-harness/SKILL.md` is the ONE owner of the runtime
    auto-advance rule, and it is DECIDABLE in both directions - the agent can read the text and
    know (a) that it auto-advances by default and (b) the closed list of the only legitimate
    reasons to stop.

    Fails if either half of the contract goes missing: the auto-advance default, or the
    enumerated stop-condition list (L2 gate / BLOCKED / NEEDS_CONTEXT / user-abort).
    """
    text = _norm_ws(_read(RUN_HARNESS_SKILL))
    assert "auto-advances the run without asking a human" in text, (
        "run-harness/SKILL.md Hard rule 2 must state the auto-advance default in a decidable "
        "sentence."
    )
    assert "enumerated" in text, (
        "run-harness/SKILL.md must frame the stop conditions as an ENUMERATED (closed) list, not "
        "open-ended judgement calls."
    )
    for must_have in ("l2", "blocked", "needs_context", "abort"):
        assert must_have in text, (
            f"run-harness/SKILL.md Hard rule 2 must name {must_have!r} as one of the enumerated "
            "legitimate stop conditions."
        )
    # Decidable in BOTH directions: plowing past a genuine block must also be named as wrong.
    assert "plows past" in text or "ignored" in text, (
        "run-harness/SKILL.md must also state that ignoring a genuine BLOCKED condition is itself "
        "wrong - the rule must not be readable as license to never stop."
    )


def test_workflow_harness_points_at_run_harness_instead_of_restating():
    """Behavior protected: SSOT direction is `skills/run-harness/SKILL.md` (the runtime skill an
    agent actually loads) OWNS the stop-condition rule; `docs/reference/workflow-harness.md` (a
    reference doc) POINTS at it instead of restating a competing, unbounded version - mirroring
    the existing precedent where `skills/_shared/concurrency-guard.md` owns the tier numbers and
    every doc cites it rather than re-declaring them.

    Fails if the doc stops naming Hard rule 2 as the owner, or independently restates its own
    enumerated list (a second copy that could drift from the first).
    """
    low = _norm_ws(_read(WORKFLOW_HARNESS_DOC))
    assert "hard rule 2" in low, (
        "workflow-harness.md must point at run-harness/SKILL.md Hard rule 2 as the rule's owner."
    )
    assert "skills/run-harness/skill.md" in low, (
        "workflow-harness.md must name the file path it points at, not just say 'the skill'."
    )


# ---------------------------------------------------------------------------
# R7b - the pre-PR tail is ordered: i18n -> acceptance -> lint-class gate -> integrate
# ---------------------------------------------------------------------------


def test_pre_pr_tail_section_exists_exactly_once():
    """Behavior protected: there is exactly ONE place that owns the pre-PR tail ordering (SSOT) -
    not one copy in wave-integration.md and a second, possibly-drifted copy elsewhere."""
    text = _read(WAVE_INTEGRATION)
    heading = "## Pre-PR tail (mandatory sequence, after the final wave closes green)"
    assert text.count(heading) == 1, (
        f"wave-integration.md must carry the '{heading}' section exactly once (found "
        f"{text.count(heading)})."
    )


def test_pre_pr_tail_orders_i18n_before_acceptance_before_lint_before_integrate():
    """Behavior protected: the pre-PR tail's four stages appear in the mandated order. This is a
    real data dependency (i18n mutates rendered UI text; acceptance's evidence must reflect the
    FINAL translated state) matching the precedent already shipping in odoo-modules-upgrade
    (i18n before its Acceptance stage) and odoo-forward-port (i18n before its later Acceptance
    stage) - composing with both, not a third diverging order.

    Fails if any stage is missing, or if the stages appear out of order.
    """
    text = _read(WAVE_INTEGRATION)
    start = text.find("## Pre-PR tail (mandatory sequence, after the final wave closes green)")
    assert start != -1, "Pre-PR tail section not found (see the previous test for detail)."
    section = text[start:]

    markers = [
        ("i18n reconcile", "**1 - i18n reconcile"),
        ("acceptance", "**2 - Acceptance"),
        ("lint-class gate", "**3 - Pre-PR lint-class gate"),
        ("terminal integrate", "**4 - Terminal land-tail PR"),
    ]
    positions = []
    for label, marker in markers:
        idx = section.find(marker)
        assert idx != -1, f"Pre-PR tail section missing the {label!r} stage marker {marker!r}."
        positions.append((label, idx))

    ordered = [label for label, _ in sorted(positions, key=lambda t: t[1])]
    expected = [label for label, _ in markers]
    assert ordered == expected, (
        f"Pre-PR tail stages are out of order - expected {expected}, found {ordered}. R7b requires "
        "i18n before acceptance before the lint-class gate before the terminal PR."
    )


def test_acceptance_depends_on_final_wave_not_on_the_pr():
    """Behavior protected: R7b's literal requirement - acceptance runs BEFORE the PR opens, never
    depending on it. This was a REAL bug the Phase-2 survey found: the pre-fix text materialized
    the acceptance node 'depending on the run's PR', which is the exact inversion R7b forbids.

    Fails if the acceptance stage is ever wired to depend on the run's PR again.
    """
    text = _norm_ws(_read(WAVE_INTEGRATION))
    assert "depending on the run's pr" not in text, (
        "the acceptance hand-off must not depend on the run's PR (R7b: acceptance runs BEFORE "
        "the PR, not after it opens) - this exact phrase was the pre-fix bug."
    )
    assert "before the pr opens" in text or "before the pr, not after" in text, (
        "the acceptance stage must explicitly state it fires before the PR opens."
    )


def test_i18n_mandate_is_wired_once_per_run_not_per_module():
    """Behavior protected: i18n reconcile is a MANDATORY, ONCE-per-run tail step (mirroring
    odoo-modules-upgrade / odoo-forward-port's existing i18n-mandate-contract.md callers) - not a
    per-module, low-confidence advisory suggestion that a --auto run would never actually
    materialize (confidence < 0.5 is never auto-materialized per run-harness's own driver rule).

    Fails if wave-integration.md does not reference the shared i18n-mandate-contract.md, or if
    odoo-coding/SKILL.md still tries to also suggest a per-module odoo-i18n hop (which would fire
    once per module per wave for the same run-level obligation).
    """
    wave_text = _read(WAVE_INTEGRATION)
    assert "i18n-mandate-contract.md" in wave_text, (
        "wave-integration.md's Pre-PR tail must reuse snippets/i18n-mandate-contract.md as the "
        "i18n mandate SSOT (not restate it)."
    )
    coding_text = _norm_ws(_read(ODOO_CODING_SKILL))
    assert "do not also emit a per-module" in coding_text or "do not also emit" in coding_text, (
        "odoo-coding/SKILL.md must explicitly stop suggesting a per-module odoo-i18n hop now that "
        "the tail owns the mandatory, once-per-run i18n step."
    )


def test_lint_class_gate_containment_prose_is_present():
    """Behavior protected: moving lint to the tail must not become a worse failure than what it
    replaces. The prose MUST state (not just imply) the fix-loop containment, the bounded
    iteration cap, and the teardown answer - required by the Phase-2 round-2 brief, not optional.

    Fails if the containment paragraph, the bounded-iteration cap, or the teardown statement is
    missing from the Pre-PR tail section.
    """
    text = _norm_ws(_read(WAVE_INTEGRATION))
    assert "containment for tail-only lint" in text, (
        "wave-integration.md must carry an explicit containment section for the tail-only lint "
        "gate, not leave the trade-off unaddressed."
    )
    assert "bound the fix-loop to 3 iterations" in text, (
        "the lint-gate fix-loop must be bounded (3 iterations, matching every other bounded chain "
        "in this file) so a persistent failure reaches BLOCKED instead of looping forever."
    )
    assert "resource-teardown-contract.md" in text and "t0-t4" in text, (
        "the pre-PR lint-class gate must state its own teardown obligation (self-provision + "
        "release before the integrate node's terminal signal) per the T0-T4 contract."
    )
    assert "does not orphan anything" in text, (
        "wave-integration.md must explicitly answer the teardown question - confirm that removing "
        "the per-work-item lint self-checks does not leave any instance lease dangling."
    )


def _section(text: str, start_marker: str, end_marker: str) -> str:
    """Slice `text` from `start_marker` up to (not including) `end_marker`. Asserts both markers
    are actually found, so a rename of either heading fails loudly instead of silently scoping to
    an empty/whole-file range."""
    start = text.find(start_marker)
    assert start != -1, f"start marker not found: {start_marker!r}"
    end = text.find(end_marker, start)
    assert end != -1, f"end marker not found after start: {end_marker!r}"
    return text[start:end]


def test_pre_pr_lint_gate_threads_worktree_path_never_relies_on_cwd():
    """Behavior protected (R12 F1, BREAKS): the pre-PR lint-class gate self-provisions an
    instance over 'the run-integration branch's aggregate diff' - but `run-integration` is a
    SEPARATE git worktree from the principal checkout. Without an explicit `WORKTREE_PATH`, this
    either silently lints the wrong (catalog/principal) tree - a false-green regardless of what
    run-integration actually contains - or trips the allocator's `_addons_path_worktree_mismatch`
    guard and hard-blocks every run, depending on the dispatching agent's cwd. Neither outcome is
    acceptable, and cwd-dependence is itself the defect class this test guards against.

    Fails if stage 3 ("Pre-PR lint-class gate") does not explicitly state WORKTREE_PATH (rooted on
    run-integration), the SELF_PROVISION: worktree-addons carve-out, and the addons-path-override
    mechanism that satisfies the allocator's mismatch guard - mirroring the SAME shape this file's
    own Example 3 and § Per-module Invocation Brief Template already use.
    """
    text = _read(WAVE_INTEGRATION)
    section = _section(
        text,
        "**3 - Pre-PR lint-class gate",
        "**4 - Terminal land-tail PR",
    )
    norm = _norm_ws(section)

    assert "worktree_path: <path>/run-integration" in norm, (
        "the pre-PR lint-class gate must state WORKTREE_PATH: <path>/run-integration explicitly - "
        "never inferred from the dispatching agent's cwd."
    )
    assert "self_provision: worktree-addons" in norm, (
        "the pre-PR lint-class gate must carry SELF_PROVISION: worktree-addons for a dispatched "
        "bounded subagent, the SAME field § Per-module Invocation Brief Template / Example 3 use."
    )
    assert "addons-path-override" in norm, (
        "the fix must explain that WORKTREE_PATH is what makes the acquire call carry "
        "--addons-path-override."
    )
    assert "_addons_path_worktree_mismatch" in norm, (
        "the fix must name the allocator guard (scripts/lib/allocator.py) that a missing "
        "--addons-path-override either fails to engage (false-green) or refuses against (hard "
        "block)."
    )
    assert "instance-handle-contract.md" in section, (
        "the fix must point at snippets/instance-handle-contract.md's Worktree-addons carve-out "
        "as the SSOT for this mechanism, not restate it inline."
    )
    assert "never inferred from cwd" in norm or "never relies on cwd" in norm or (
        "dispatching agent's cwd" in norm
    ), (
        "the fix must explicitly disclaim cwd-dependence - the defect class this gate must not "
        "reproduce."
    )


def test_pre_pr_lint_fix_reaches_run_integration_and_is_reverified_there():
    """Behavior protected (R12 waves finding #1, BREAKS): a lint fix authored at the pre-PR tail
    must actually reach the shipped PR. The pre-fix text said to re-invoke odoo-coding at 'the
    failing module's worktree slice' (an undefined term reading naturally as the STALE, already
    cherry-picked per-module worktree from that module's wave) with no step bringing the resulting
    commit back onto `run-integration` - the ONLY branch the terminal land-tail squashes and
    pushes. Without that step the fix either never reaches the PR (if the loop trusts a bare DONE)
    or the loop re-lints unchanged run-integration content and falsely exhausts to BLOCKED.

    Fails if the containment section does not (a) disambiguate the fix's target worktree, (b)
    mandate a cherry-pick of the fix back onto run-integration via git-toolkit:git-ops (never a raw
    git command), and (c) mandate re-running the lint-class suite against run-integration's OWN new
    tip rather than trusting the coder's self-reported DONE.
    """
    text = _read(WAVE_INTEGRATION)
    section = _section(
        text,
        "**Containment for tail-only lint",
        "**4 - Terminal land-tail PR",
    )
    norm = _norm_ws(section)

    assert "worktree slice" not in norm, (
        "the undefined 'worktree slice' phrasing must be replaced with a decidable target "
        "(the module's own per-wave worktree, named consistently with § Per-module Integration "
        "Loop's `mod.worktree`)."
    )
    assert "cherry-pick the fix back onto" in norm and "run-integration" in norm, (
        "the containment section must mandate cherry-picking the fix commit back onto "
        "run-integration - a fix left on the module's own worktree branch never reaches the PR."
    )
    assert "git-toolkit:git-ops" in section, (
        "the cherry-pick-back step must route through the git-toolkit:git-ops skill, never a raw "
        "git command run inline (this repo's git-delegation rule binds this fix loop too)."
    )
    assert "re-run the lint-class suite against" in norm and "run-integration" in norm, (
        "the fix-loop must explicitly re-run the lint-class suite against run-integration's own "
        "new tip after the cherry-pick - not just once, upfront."
    )
    assert "never trust the coder's own" in norm or "does not prove" in norm, (
        "the fix-loop must explicitly refuse to trust the coder's bare DONE self-report as proof "
        "that run-integration (the tree that actually ships) is clean."
    )


def test_review_escalation_fix_reaches_run_integration_and_is_reverified_there():
    """Behavior protected: the SAME defect as the pre-PR lint-gate fix loop (see the previous
    test), one section up. Review Escalation ("close-the-wave cross-cutting review") runs over
    the whole `run-integration` worktree, but its fix-dispatch paragraph could re-invoke
    `odoo-coding` against 'that module's worktree path' (the module's OWN per-wave worktree, a
    SEPARATE tree from run-integration) with no stated cherry-pick-back step and no stated
    re-verification target - the fix could land on the module's own branch and never reach
    run-integration, or the loop could trust a bare DONE without re-checking run-integration
    itself.

    Fails if the paragraph does not (a) disambiguate the fix's target tree (run-integration
    directly for the inline/subagent paths, the module's own worktree - named, not an undefined
    "slice" - for the odoo-coding path), (b) mandate cherry-picking that third path's result back
    onto run-integration via git-toolkit:git-ops (never a raw git command), and (c) mandate
    re-verifying against run-integration's own tip specifically.
    """
    text = _read(WAVE_INTEGRATION)
    section = _section(
        text,
        "## Review Escalation",
        "## Pre-PR tail",
    )
    norm = _norm_ws(section)

    assert "run-integration" in norm, (
        "the Review Escalation fix-dispatch paragraph must name run-integration explicitly - "
        "'the whole integration worktree' alone does not pin the SAME tree a re-invoked "
        "odoo-coding dispatch (scoped to the module's own worktree) must return to."
    )
    assert "cherry-picked back onto" in norm or "cherry-pick" in norm, (
        "the paragraph must mandate cherry-picking a fix authored on the module's own worktree "
        "back onto run-integration - the SAME step § Per-module Integration Loop already performs "
        "for every module SHA."
    )
    assert "git-toolkit:git-ops" in section, (
        "the cherry-pick-back step must route through git-toolkit:git-ops, never a raw git command "
        "run inline."
    )
    assert "re-run verify against" in norm and "run-integration" in norm, (
        "the paragraph must mandate re-running verify against run-integration's current tip "
        "specifically, not the module's own worktree and not a bare worker DONE."
    )


def test_conflict_resolver_names_the_worktree_it_edits_and_continues_against():
    """Behavior protected: the SAME shape one more time. The Conflict Resolver's worker brief told
    a freshly-dispatched (context-isolated) subagent to edit 'the conflicting files in the
    worktree' with no path, and the follow-up 're-invoke git-toolkit:git-ops ... op=cherry-pick-
    continue' named no worktree/branch either - both instructions are actionable only if the tree
    is stated, since a fresh subagent context does not inherit cwd (the SAME reasoning
    instance-handle-contract.md already applies to every other worktree-scoped dispatch in this
    plugin).

    Fails if the worker-brief sentence or the cherry-pick-continue sentence does not name
    run-integration (or its `<path>/run-integration` form) explicitly.
    """
    text = _read(WAVE_INTEGRATION)
    section = _section(
        text,
        "## Conflict Resolver",
        "## Review Escalation",
    )
    norm = _norm_ws(section)

    assert "editing the conflicting files in the" in norm and "run-integration" in norm, (
        "the worker brief must name run-integration as the worktree the resolver edits in - a "
        "fresh subagent context has no cwd to infer it from."
    )
    assert norm.count("run-integration") >= 2, (
        "both the worker-brief sentence AND the re-invoke git-toolkit:git-ops "
        "(op=cherry-pick-continue) sentence must each name run-integration - one mention covering "
        "only the first half leaves the second half's target undefined again."
    )


def test_run_harness_has_no_untargeted_reverify_reinvoke_instruction_whole_class_scan():
    """Whole-CLASS structural guard (R12 F1 + waves-finding-#1 pattern): ANY instruction anywhere
    in `skills/run-harness/**` that says re-run / re-verify / re-invoke MUST name its target tree
    (`run-integration`, `run_integration`, or `WORKTREE_PATH`) in the SAME block - not merely
    somewhere else in the same document section. This is the class the three sites fixed above
    (the pre-PR lint gate, Review Escalation, Conflict Resolver) all belong to; this test exists so
    a FOURTH site is caught structurally instead of needing a human to notice the same shape again.

    Granularity is deliberately FINE (each bullet / each blank-line paragraph is its own block, not
    the whole enclosing `##` section) - a coarse whole-section check would have MISSED the original
    pre-PR lint-gate bug, because a SIBLING bullet three lines away already mentions
    `run-integration` for an unrelated reason while the violating bullet itself names nothing
    (verified while building this guard: the section-level version of this check gave a false
    'OK' on the pre-fix tree for exactly that reason).

    Structural exclusion (not a per-file/per-site allowlist): the `## Examples` section is dropped
    entirely - it is a compressed, deliberately terse restatement of mechanics already defined
    earlier in the SAME file (see its own preamble: "these examples start from run-harness picking
    a coding wave node..."), the same way Example 1 does not re-restate WORKTREE_PATH/
    SELF_PROVISION either. Any OTHER file added under run-harness/** in the future is included
    automatically (whole-tree glob, not a name list).
    """
    verb_re = re.compile(r"\b(re-run|re-verify|re-invoke)\b", re.IGNORECASE)
    tree_re = re.compile(r"run-integration|run_integration|worktree_path", re.IGNORECASE)

    def blocks(text: str):
        examples_at = text.find("\n## Examples")
        if examples_at != -1:
            text = text[:examples_at]
        return [p for p in re.split(r"\n\s*\n|\n(?=- )", text) if p.strip()]

    run_harness_dir = PLUGIN / "skills" / "run-harness"
    offenders = []
    for f in sorted(run_harness_dir.rglob("*.md")):
        text = _read(f)
        for block in blocks(text):
            verbs = verb_re.findall(block)
            if verbs and not tree_re.search(block):
                snippet = re.sub(r"\s+", " ", block.strip())[:100]
                offenders.append(f"{f.relative_to(REPO_ROOT)}: {verbs} in {snippet!r}...")

    assert not offenders, (
        "found a re-run/re-verify/re-invoke instruction with no target tree named in its own "
        "block (the false-green / lost-fix defect class) - name run-integration, run_integration, "
        "or WORKTREE_PATH in the SAME bullet/paragraph as the instruction:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# R7a - lint-class names are gone from per-module/per-wave gate sites, present ONLY at the
# designated pre-PR tail location. Whole-tree scan (structural exclusions only, never a
# known-offender allowlist) so the guard catches every sibling name, not just `test_lint`.
# ---------------------------------------------------------------------------

# Every lint-class tool name the Phase-2 survey enumerated for R7a ("test_lint, test_pylint,
# eslint, and siblings"). Word-bounded so e.g. `ruff` does not match inside an unrelated word.
LINT_CLASS_NAMES = re.compile(
    r"(test_lint|test_pylint|pylint-odoo|\beslint\b|\bflake8\b|\bruff\b|\bprettier\b)",
    re.IGNORECASE,
)

# Structural exclusions ONLY - entire directories/files that are a DIFFERENT, legitimate thing
# (a reference doc describing the gate's mechanics, a peer orchestrator's own separate pipeline,
# or a different lifecycle stage), never a per-offender allowlist. Group E's own new pre-PR gate
# lives under skills/run-harness/, which is deliberately where these names are now ALLOWED to
# live.
STRUCTURALLY_EXCLUDED_DIRS = (
    "docs/reference",  # SSOT description of the gates' mechanics, not an execution site
    "skills/run-harness",  # the new, single, designated pre-PR tail location
    "skills/odoo-modules-upgrade",  # peer orchestrator, already correct (lint at its own P7 pre-PR step)
    "skills/odoo-forward-port",  # peer orchestrator (Group C), its own separate lane
    "skills/odoo-deploy-checklist",  # a different lifecycle stage (post-deploy smoke test)
    "skills/_shared",  # shared reference material (coding_guidelines, frontend-fidelity pitfall
                        # catalogue) consumed by many skills - same category as snippets/, not a
                        # per-module execution body
    "skills/odoo-debug/SKILL.md",  # diagnostic routing-table entry (which debugger owns a
                                   # `test_lint` FAILURE symptom) - mirrors
                                   # agents/odoo-backend-debugger.md, not an execution site
    "skills/odoo-deep-survey/SKILL.md",  # read-only analytical/recon lens listing framework-
                                         # validation test classes - not a gating decision
    "skills/odoo-test-writing/SKILL.md",  # generic, multi-caller test-AUTHORING skill (not
                                          # specific to the wave/coding pipeline); its one mention
                                          # is advisory tagging info for a LATER executor. Flagged
                                          # in the Phase-2 round-2 report as worth a follow-up
                                          # look, not silently resolved as clean.
    "snippets",  # cross-cutting SSOT snippets describing WHO/WHAT, not per-module execution bodies
    "agents/odoo-backend-debugger.md",  # diagnostic reference for interpreting a lint FAILURE message
    "agents/odoo-ui-debugger.md",  # grounding-doc pointer (read before diagnosing), not an execution site
    "agents/odoo-ui-reviewer.md",  # grounding-doc pointer, not an execution site
    "README.md",  # top-level repo overview / persona table - descriptive, not prescriptive
)

# The 4 sites the Phase-2 survey identified as the actual per-module/per-WI GATING execution
# sites - handed off to Group A in 44-handoff-E.md (Group E does not own agents/*.md).
PENDING_HANDOFF_FILES = (
    "agents/odoo-backend-coder.md",
    "agents/odoo-frontend-coder.md",
    "agents/odoo-coder.md",
    "agents/odoo-code-reviewer.md",
)

# `agents/odoo-instance-ops.md` and `skills/odoo-instance/SKILL.md` are DELIBERATELY NOT
# structurally excluded (R7a/R12 F1 fix): both were previously blindly excluded here with a
# "describes mechanics, not a gating decision" rationale that each file's OWN Verdict/Dispatch
# contract for `run-tests` contradicted - installing + tagging a lint module IS the gating
# decision, because a tagged/installed lint test that fails is indistinguishable, in the returned
# status, from any other failing test, and both fed the SAME BLOCKING `tests-failed` /
# bounded-fix-loop machinery for EVERY per-module, per-wave dispatch. A blind name-presence scan
# cannot see that class of bug either way - the strings `test_lint`/`test_pylint` legitimately
# belong in BOTH files (the agent is the ONE place that probes for and unions them; the skill is
# the front door that resolves and threads the deciding field before dispatch), now CONDITIONALLY
# on an explicit `GATE_ROLE` field in both - see `agents/odoo-instance-ops.md` "Lint modules -
# installed ONLY for the designated pre-PR lint gate (HARD RULE)" and
# `skills/odoo-instance/SKILL.md` "Agent-side unions this skill does not compute itself" +
# "GATE_ROLE resolution". So both files are measured here (a capped, visible bucket, never
# silently re-hidden) AND separately covered by dedicated behavioral tests
# (`test_odoo_instance_ops_lint_union_is_gated_by_gate_role`,
# `test_odoo_instance_skill_resolves_and_forwards_gate_role` below) that check the actual
# reachability/consequence fix, not just string presence. There is NO remaining out-of-lane gap:
# `skills/odoo-instance/**` was assigned to this same fix owner in a scope-extension round, so the
# sibling file that used to sit in a separate "out of lane, tracked" bucket is now fixed and folded
# into this ONE bucket - a cap that existed only to tolerate an unfixed sibling does not survive
# the sibling being fixed.
GATED_MECHANISM_FILES = (
    "agents/odoo-instance-ops.md",
    "skills/odoo-instance/SKILL.md",
)


def _is_structurally_excluded(rel_posix: str) -> bool:
    return any(rel_posix.startswith(d) for d in STRUCTURALLY_EXCLUDED_DIRS)


def test_lint_class_names_absent_outside_the_designated_sites_whole_tree_scan():
    """Whole-tree regression guard for R7a: catches EVERY lint-class name enumerated by the
    survey (test_lint, test_pylint, pylint-odoo, eslint, flake8, ruff, prettier) - not only
    `test_lint` (the trap this repo has been bitten by before: a guard pinned to one name goes
    green while a sibling walks past).

    Reports THREE buckets separately (never a per-offender allowlist - each bucket is a small,
    named, capped set with a stated reason, and every cap is measured against the CURRENT count,
    not an arbitrarily wide ceiling):
      - TRUE offenders: any file outside every other bucket. This must be EMPTY - a true
        regression here is a real bug.
      - PENDING (known, tracked): the 4 named per-module agent files. Their lint-class content is
        REQUIRED to disappear too (see 44-handoff-E.md), but Group E does not own agents/*.md this
        round (arbitration A-06) - measured and reported, not silently hidden.
      - GATED MECHANISM (both fixed, both behaviorally covered): `agents/odoo-instance-ops.md` +
        `skills/odoo-instance/SKILL.md` - see `GATED_MECHANISM_FILES` above and the two dedicated
        `test_odoo_instance_*_gate_role*` tests below for the real coverage this blind scan cannot
        provide.
    """
    true_offenders = []
    pending = []
    gated_mechanism = []
    for f in _all_plugin_md_files():
        rel_posix = f.relative_to(PLUGIN).as_posix()
        if _is_structurally_excluded(rel_posix):
            continue
        text = _read(f)
        hits = LINT_CLASS_NAMES.findall(text)
        if not hits:
            continue
        if rel_posix in PENDING_HANDOFF_FILES:
            pending.append((rel_posix, len(hits)))
        elif rel_posix in GATED_MECHANISM_FILES:
            gated_mechanism.append((rel_posix, len(hits)))
        else:
            true_offenders.append((rel_posix, len(hits)))

    assert not true_offenders, (
        "Lint-class names found in a file that is NEITHER a structurally-excluded reference/peer "
        "location NOR one of the tracked buckets above - this is a genuine R7a regression:\n"
        + "\n".join(f"{p}: {n} hit(s)" for p, n in true_offenders)
    )

    # The pending bucket is EXPECTED to be non-empty until 44-handoff-E.md is applied. Assert
    # against the survey's own measured baseline (25 lines across the 4 files) so a change in
    # either direction is visible: fewer hits means the hand-off is landing; MORE hits means new
    # lint-class content leaked into one of these files on top of the known, tracked debt.
    total_pending_hits = sum(n for _, n in pending)
    assert total_pending_hits <= 40, (
        "Lint-class references in the 4 pending hand-off files grew well beyond the Phase-2 "
        f"survey's measured baseline (~25-34 regex hits): {pending}. New lint-class content was "
        "added on top of the known pending debt - that is a NEW regression, not the tracked one."
    )

    # Both gated-mechanism files legitimately mention test_lint/test_pylint - the agent is the ONE
    # place that probes for and unions them at execution time, the skill is the front door that
    # resolves and forwards the deciding GATE_ROLE field before dispatch. Capped PER FILE against
    # the CURRENT measured count so unrelated NEW lint-class content cannot hide inside this
    # bucket, and so a regression in either file is attributable rather than lost in a combined sum.
    # The agents/odoo-instance-ops.md cap was bumped from 20 to 28 (measured: 25) for the
    # checker-load coverage confirmation fix - a legitimate, reviewed addition that discusses
    # test_lint/test_pylint's own one-method checker-sweep shape (grounding) and the decidable
    # coverage rule (§ Verdict contract), not a reintroduction of the unconditional union it composes
    # with (still gated by GATE_ROLE, see the dedicated test below).
    gated_by_file = dict(gated_mechanism)
    assert gated_by_file.get("agents/odoo-instance-ops.md", 0) <= 28, (
        "Lint-class references in agents/odoo-instance-ops.md grew beyond the measured baseline "
        f"(25 hits after the checker-load coverage confirmation fix): {gated_mechanism}. Confirm "
        "any new mention is still gated by GATE_ROLE (see "
        "test_odoo_instance_ops_lint_union_is_gated_by_gate_role below), not a reintroduction of "
        "the unconditional union."
    )
    assert gated_by_file.get("skills/odoo-instance/SKILL.md", 0) <= 12, (
        "Lint-class references in skills/odoo-instance/SKILL.md grew beyond the measured baseline "
        f"(8 hits after the GATE_ROLE fix): {gated_mechanism}. Confirm any new mention is still "
        "gated by GATE_ROLE (see test_odoo_instance_skill_resolves_and_forwards_gate_role below), "
        "not a reintroduction of the unconditional union."
    )


# ---------------------------------------------------------------------------
# R7a / R12 F1 BREAK - the lint-module union is CONDITIONAL on an explicit GATE_ROLE field, never
# unconditional for "ANY run-tests op". This is the real fix the blind name-presence scan above
# cannot express: the defect was in the REACHABILITY/CONSEQUENCE of the HARD RULE from a per-wave
# call site, not in the mere presence of the strings `test_lint`/`test_pylint`.
# ---------------------------------------------------------------------------

INSTANCE_OPS_AGENT = PLUGIN / "agents" / "odoo-instance-ops.md"
ODOO_CODER_AGENT = PLUGIN / "agents" / "odoo-coder.md"
INSTANCE_SKILL_MD = PLUGIN / "skills" / "odoo-instance" / "SKILL.md"


def test_odoo_instance_ops_lint_union_is_gated_by_gate_role():
    """Behavior protected (R12 F1, BREAK): the lint-module install+tag union in
    `agents/odoo-instance-ops.md` must be CONDITIONAL on an explicit `GATE_ROLE` field the
    dispatching caller states - never unconditional for "ANY run-tests op". Unconditional wiring is
    exactly what let a `test_lint`/`test_pylint` violation surface as a BLOCKING `tests-failed`
    verdict inside `odoo-coder`'s own per-module, per-wave integrated verification (never the pre-PR
    tail R7a intended).

    Fails if the two decidable branches (`pre-pr-lint-gate` unions, `per-module-verify` does not),
    the NEEDS_CONTEXT refusal for an absent GATE_ROLE, or the still-unconditional old phrasing is
    missing/reintroduced.
    """
    text = _norm_ws(_read(INSTANCE_OPS_AGENT))

    assert "gate_role" in text, (
        "agents/odoo-instance-ops.md must name GATE_ROLE as the field that decides the lint-module "
        "union - the union cannot be unconditional for every run-tests dispatch."
    )
    assert "pre-pr-lint-gate" in text and "per-module-verify" in text, (
        "agents/odoo-instance-ops.md must state BOTH GATE_ROLE values - pre-pr-lint-gate (unions "
        "test_lint/test_pylint) and per-module-verify (does not) - so a per-module dispatch can "
        "opt out by name, not by omission."
    )
    assert "needs_context" in text, (
        "agents/odoo-instance-ops.md must refuse (NEEDS_CONTEXT) a run-tests/test-enable dispatch "
        "whose GATE_ROLE is unresolved - never silently default to installing (reinstates the "
        "per-wave gate) or skipping (risks a false-green pre-PR gate)."
    )
    assert "do not probe for, install, or tag" in text or "do not install" in text, (
        "agents/odoo-instance-ops.md must explicitly state that a per-module-verify dispatch skips "
        "the lint probe/install/tag entirely, not merely 'also' union it."
    )


def test_odoo_instance_skill_resolves_and_forwards_gate_role():
    """Behavior protected (R12 F1 scope extension, BREAK sibling): the `odoo-instance` SKILL - the
    front door every caller routes through before `odoo-instance-ops` ever sees a brief - must
    resolve and forward the SAME `GATE_ROLE` field, not a second spelling or a parallel mechanism.
    This is the reachability half of the fix: an agent-side gate is worthless if the front door that
    composes its brief never threads the deciding field through.

    Fails if the skill does not name GATE_ROLE, does not state both values, does not give a
    decidable resolution rule for a caller that stated no role (never a silent default toward the
    dangerous "install" side), or still claims the lint union applies with "callers pass nothing
    extra" (the old, unconditional framing this fix replaces).
    """
    text = _norm_ws(_read(INSTANCE_SKILL_MD))

    assert "gate_role" in text, (
        "skills/odoo-instance/SKILL.md must name GATE_ROLE as a dispatch parameter - the SAME field "
        "agents/odoo-instance-ops.md reads, not a differently-spelled parallel mechanism."
    )
    assert "pre-pr-lint-gate" in text and "per-module-verify" in text, (
        "skills/odoo-instance/SKILL.md must state BOTH GATE_ROLE values, matching "
        "agents/odoo-instance-ops.md's vocabulary exactly."
    )
    assert "default to `gate_role: per-module-verify`" in text, (
        "the skill must state a decidable default for an unstated role (per-module-verify - the "
        "never-escalates-to-lint choice) rather than silently guessing toward installing lint "
        "modules for an ad-hoc request."
    )
    assert "gated, never unconditional" in text or "not automatic like" in text, (
        "the skill must explicitly disclaim the OLD unconditional framing for the lint union - it "
        "is no longer true that 'callers pass nothing extra' for the lint-module union the way they "
        "do for to_base."
    )


def test_odoo_coder_opts_out_of_the_lint_gate_on_its_per_module_dispatch():
    """Behavior protected (R12 F1, BREAK, caller side): `odoo-coder`'s own integrated-module
    verification - the exact per-wave call site the review found colliding with the lint gate -
    must explicitly declare `GATE_ROLE: per-module-verify` on every run-tests dispatch it makes, and
    must no longer claim the lint-module union applies to it.

    Fails if `odoo-coder.md` still claims the `/test_lint`+`/test_pylint` install union is one of
    the instance HARD RULES applied to its own integrated test, or drops the explicit GATE_ROLE
    opt-out.
    """
    raw = _read(ODOO_CODER_AGENT)
    text = _norm_ws(raw)

    assert "gate_role: per-module-verify" in text, (
        "odoo-coder.md must state GATE_ROLE: per-module-verify on its own integrated-module "
        "verification dispatch(es) - the caller-side half of the GATE_ROLE contract."
    )
    assert "the `/test_lint`+`/test_pylint` install union" not in raw, (
        "odoo-coder.md must no longer claim the lint-module install union is one of the "
        "unconditional instance HARD RULES applied to its own per-module integrated test - that "
        "claim is what let the per-wave lint collision survive."
    )


def test_pre_pr_lint_gate_declares_its_own_gate_role():
    """Behavior protected (R12 F1, BREAK, the ONE authorized caller): the pre-PR lint-class gate in
    `wave-integration.md` - the ONE dispatch authorized to trigger the lint-module union - must
    explicitly state `GATE_ROLE: pre-pr-lint-gate` on its provisioning dispatch, the SAME way it
    already mandates `WORKTREE_PATH`/`SELF_PROVISION` explicitly rather than leaving them inferred.

    Fails if the Pre-PR lint-class gate section does not name GATE_ROLE explicitly.
    """
    text = _read(WAVE_INTEGRATION)
    section = _section(
        text,
        "**3 - Pre-PR lint-class gate",
        "**4 - Terminal land-tail PR",
    )
    norm = _norm_ws(section)
    assert "gate_role: pre-pr-lint-gate" in norm, (
        "the pre-PR lint-class gate must explicitly state GATE_ROLE: pre-pr-lint-gate on its "
        "run-tests dispatch - never inferred from being 'the last stage'."
    )
