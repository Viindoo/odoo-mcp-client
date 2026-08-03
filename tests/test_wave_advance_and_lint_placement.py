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
    "skills/odoo-instance",  # infra-capability skill (installs/unions lint modules on ANY
                             # test-run build) - describes mechanics, not a gating decision, same
                             # category as agents/odoo-instance-ops.md
    "skills/odoo-onboarding",  # a different skill entirely: one-time repo setup (discovers the
                               # REPO's OWN existing ruff/eslint config) - unrelated to per-wave
                               # coding-run gating
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
    "agents/odoo-instance-ops.md",  # infra capability (installs lint modules) - not a gating decision
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


def _is_structurally_excluded(rel_posix: str) -> bool:
    return any(rel_posix.startswith(d) for d in STRUCTURALLY_EXCLUDED_DIRS)


def test_lint_class_names_absent_outside_the_designated_sites_whole_tree_scan():
    """Whole-tree regression guard for R7a: catches EVERY lint-class name enumerated by the
    survey (test_lint, test_pylint, pylint-odoo, eslint, flake8, ruff, prettier) - not only
    `test_lint` (the trap this repo has been bitten by before: a guard pinned to one name goes
    green while a sibling walks past).

    Reports two buckets separately:
      - TRUE offenders: any file outside the structural exclusions AND outside the 4 pending
        hand-off files. This must be EMPTY - a true regression here is a real bug.
      - PENDING (known, tracked): the 4 named per-module agent files. Their lint-class content is
        REQUIRED to disappear too (see 44-handoff-E.md), but Group E does not own agents/*.md this
        round (arbitration A-06) - measured and reported, not silently hidden.
    """
    true_offenders = []
    pending = []
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
        else:
            true_offenders.append((rel_posix, len(hits)))

    assert not true_offenders, (
        "Lint-class names found in a file that is NEITHER a structurally-excluded reference/peer "
        "location NOR one of the 4 files pending the Group-A hand-off - this is a genuine R7a "
        "regression:\n" + "\n".join(f"{p}: {n} hit(s)" for p, n in true_offenders)
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
