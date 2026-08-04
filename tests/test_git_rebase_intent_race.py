"""Invariant tests for the odoo-git-rebase shared-commit intent write race.

odoo-forward-port had this exact defect (a commit shared between two modules'
extractor bundles racing on the same `intents/<sha>.md` write path once
dispatch batches by MODULE) and it was fixed there first - see
`TestSharedCommitIntentWritePathPerModule` and `TestForwardPortSlugMandatoryNoFallback`
in `tests/test_forward_port_hardening.py`. That fix was deliberately left
forward-port-mode-scoped at the time: `agents/odoo-intent-extractor.md`'s
rebase-mode section still carried an identical "if SLUG absent, derive one"
bypass, reachable once `odoo-git-rebase`'s own module-batched dispatch
(SKILL.md P2, "Above ~30 non-(a) commits, batch intent extraction by MODULE")
shares a commit between two modules' bundles. Rebase only races ABOVE that
batching threshold, so it is rarer than the forward-port case, not milder.

This module pins the rebase-mode fix, mirrored from the forward-port
precedent: the caller (SKILL.md / rb-phase-detail.md P2) sets `SLUG` to
`<run-slug>/<module>` for the module-batched dispatch shape, and the callee
(`agents/odoo-intent-extractor.md` § Rebase mode) makes `SLUG` REQUIRED with
no derived fallback, refusing with `NEEDS_CONTEXT(SLUG)` instead.

Unlike forward-port, odoo-git-rebase's P3 (`odoo-diff-comparator`, rebase
mode) reads ALL intent records in ONE bulk pass via a flat `intents_dir`
field/directory - there is no per-module architecture at that phase the way
forward-port's P2 classify (which always walks module-by-module) has. Rather
than change that consumer's contract (out of scope for this fix - it is not
under `skills/odoo-git-rebase/**` or `agents/odoo-intent-extractor.md`), the
fix adds a deterministic, race-free consolidation fan-in step (P2, after all
module-batched dispatches return, before P3) that copies each commit's
canonical record back to the SAME bare-slug path every downstream phase
(P3/P5/P8/P9) already reads - so no consumer file needs to change at all.

The consolidation fan-in itself is a NEW moving part odoo-forward-port never needed (forward-port
has no bulk-directory reader the way rebase's P3 does). It sits between the writers and every
reader, so it can silently not happen: a crash between extraction and consolidation, or a resumed
run that believes P2 is already done, leaves the canonical path empty while P3 reads it as "no
intent to compare" instead of "the pipeline is broken". Two follow-up guards close that:

1. Consolidation is checkpointed SEPARATELY from extraction (`extracted-pending-consolidation`
   before the copy, `extracted` only after it is confirmed) and the copy is idempotent, so a
   resumed run re-attempts exactly the copies that did not complete.
2. P3 fails CLOSED: a completeness gate refuses (returns the pipeline's existing `BLOCKED`
   vocabulary - the SAME status odoo-intent-extractor/odoo-diff-comparator already use for their
   own absent-required-input guards) rather than proceeding when a non-(a) commit has no
   canonical record, instead of silently reading an absent record as "nothing to compare".

Files under test (all under plugins/odoo-ai-agents/):
  - agents/odoo-intent-extractor.md (§ Rebase mode only)
  - skills/odoo-git-rebase/SKILL.md (§ Checkpoint / resume, § P2, § P3)
  - skills/odoo-git-rebase/references/rb-phase-detail.md (§ P2, § P3)
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

INTENT_EXTRACTOR_AGENT = PLUGIN / "agents" / "odoo-intent-extractor.md"
DIFF_COMPARATOR_AGENT = PLUGIN / "agents" / "odoo-diff-comparator.md"
SKILL_MD = PLUGIN / "skills" / "odoo-git-rebase" / "SKILL.md"
PHASE_DETAIL = PLUGIN / "skills" / "odoo-git-rebase" / "references" / "rb-phase-detail.md"


def _ws_normalize(text):
    """Collapse ALL whitespace (including markdown hard-wraps) to single
    spaces so a literal-phrase search cannot be defeated by line wrapping."""
    return " ".join(text.split())


def _rebase_mode_section(text):
    """Slice the agent file down to just § Rebase mode (through the next
    top-level '## ' heading), so an assertion here can never accidentally
    pass because of unrelated forward-port-mode text elsewhere in the file."""
    start = text.index("## Rebase mode")
    rest = text[start + len("## Rebase mode"):]
    end = rest.index("\n## ")
    return text[start: start + len("## Rebase mode") + end]


# ---------------------------------------------------------------------------
# Invariant (write race) - the caller-side fix (SLUG: <slug>/<module> for the
# module-batched P2 dispatch) only closes the shared-commit write race if the
# brief actually carries it AND the callee actually honors whatever SLUG it
# is given instead of deriving its own.
#
# RED-before-green evidence (measured via `git show HEAD:<path>`):
#   - agents/odoo-intent-extractor.md 'Slug fallback:' heading: 1 -> 0 post-fix.
#   - agents/odoo-intent-extractor.md '`SLUG` is REQUIRED in rebase mode': 0 -> 1.
#   - rb-phase-detail.md 'SLUG: <slug>/<module>' (module-batched P2 brief): 0 -> 1.
#   - rb-phase-detail.md 'P2 consolidation' fan-in step: 0 -> 2 (heading + prose).
# ---------------------------------------------------------------------------


class TestRebaseModuleBatchedDispatchUsesPerModuleSlug:
    """rb-phase-detail.md must document a module-batched P2 dispatch shape (the one
    SKILL.md's 'Above ~30 non-(a) commits, batch intent extraction by MODULE' sentence
    promises exists) whose brief sets a PER-MODULE SLUG - never the bare run slug -
    exactly mirroring odoo-forward-port's own P1 fix for the identical hazard."""

    def setup_method(self):
        self.skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_skill_md_p2_states_per_module_slug_for_batched_dispatch(self):
        assert "SLUG` to `<slug>/<module>`" in self.skill_text, (
            "SKILL.md P2 must state that the module-batched dispatch sets SLUG to "
            "<slug>/<module> - a commit shared between two modules' bundles must never "
            "let both instances write the same intents/<sha>.md path"
        )

    def test_phase_detail_module_batched_brief_sets_per_module_slug(self):
        assert "SLUG: <slug>/<module>" in self.phase_text, (
            "rb-phase-detail.md's module-batched P2 dispatch brief must set "
            "SLUG: <slug>/<module>, not the bare run <slug>, for every module's dispatch"
        )

    def test_phase_detail_names_the_module_batched_dispatch_cap(self):
        """R2b-equivalent: once batching trips, at most one instance per module -
        never a fresh dispatch per individual commit - mirroring forward-port's own
        cardinality cap so the whole-tree cardinality guard
        (TestModuleFirstAgentCardinalityCap in test_forward_port_hardening.py) stays green."""
        assert "at most one" in self.phase_text.lower(), (
            "rb-phase-detail.md's module-batched P2 section must state the per-module "
            "dispatch cap ('at most one'), matching forward-port's R2b phrasing"
        )

    def test_phase_detail_module_batched_brief_carries_module_bundle_fields(self):
        section = self.phase_text[self.phase_text.index("module-batched, above ~30"):]
        section = section[: section.index("### P2 consolidation")]
        assert "MODULE: <module-name>" in section and "commit_dump_paths:" in section, (
            "the module-batched P2 brief must carry MODULE + the ordered commit_dump_paths "
            "bundle, not a single-SHA commit_dump_path field"
        )

    def test_default_per_commit_dispatch_keeps_the_bare_slug(self):
        """Below the batching threshold, exactly one dispatch ever owns a given commit -
        the bare run <slug> stays correct and must not be needlessly namespaced too."""
        default_brief = self.phase_text[
            self.phase_text.index("### P2 dispatch: odoo-intent-extractor"):
            self.phase_text.index("### P2 dispatch (module-batched")
        ]
        assert "SLUG: <slug>\n" in default_brief, (
            "the default (per-commit) P2 dispatch brief must keep SLUG: <slug> (bare) - "
            "only the module-batched shape needs the per-module namespace"
        )


class TestRebaseConsolidationClosesTheLoopWithoutTouchingConsumers:
    """The module-batched dispatch writes per-module-namespaced intent files; every
    downstream consumer (P3's odoo-diff-comparator, P5's design route-out, P8/P9) still
    reads the bare-slug canonical path. A consolidation fan-in step must reconcile the
    two - closing the loop without requiring a change to any consumer file, since
    agents/odoo-diff-comparator.md is out of this fix's scope."""

    def setup_method(self):
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")
        self.comparator_text = DIFF_COMPARATOR_AGENT.read_text(encoding="utf-8")

    def test_consolidation_step_is_documented(self):
        assert "### P2 consolidation" in self.phase_text, (
            "rb-phase-detail.md must document a P2 consolidation fan-in step that runs "
            "after module-batched dispatch and before P3"
        )

    def test_consolidation_targets_the_canonical_bare_slug_path(self):
        section = self.phase_text[self.phase_text.index("### P2 consolidation"):]
        section = section[: section.index("\n## P3")]
        assert "<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md" in section, (
            "the consolidation step must write back to the SAME canonical bare-slug "
            "path every downstream phase already reads"
        )

    def test_consolidation_states_a_deterministic_owner_rule_for_shared_commits(self):
        """The original defect had 'no owner rule and no merge rule' for a commit shared
        between two modules' bundles - the fix must state ONE, not last-write-wins."""
        section = self.phase_text[self.phase_text.index("### P2 consolidation"):]
        section = section[: section.index("\n## P3")]
        assert "never last-write-wins" in section and "FIRST module" in section, (
            "the consolidation step must state a deterministic (never last-write-wins) "
            "owner rule for a commit shared between multiple modules' bundles"
        )

    def test_diff_comparator_agent_contract_is_unmodified_by_this_fix(self):
        """agents/odoo-diff-comparator.md is NOT under this fix's file scope - the
        consolidation design exists precisely so this file needs no change. Its
        intents_dir contract must still describe a single flat directory of per-commit
        files, unaware of any per-module namespacing upstream."""
        assert (
            "Path to `<ISOLATE_DIR>/git-rebase/<slug>/intents/` containing per-commit "
            "`<sha>.md` files" in self.comparator_text
        ), (
            "agents/odoo-diff-comparator.md's intents_dir contract must remain the "
            "single flat directory it always was - the rebase fix must not require "
            "this out-of-scope consumer file to change"
        )


# ---------------------------------------------------------------------------
# Invariant (B2-shaped bypass, rebase mode) - the caller-side fix above only
# closes the write race if the CALLEE (agents/odoo-intent-extractor.md)
# actually uses whatever SLUG it is given. § Rebase mode previously
# documented a fallback - "if SLUG absent, derive it as
# <feature-ref>-onto-<new-base>" - that reconstructs the bare,
# non-module-scoped run slug whenever a caller omits SLUG, silently
# reopening the exact write race the per-module SLUG closes. Fix: SLUG is
# now a REQUIRED, no-safe-default field in rebase mode too (mirroring both
# this agent's own forward-port-mode fix and its established Brief
# self-check pattern for OBJECTIVE/ACCEPTANCE/INPUTS) - the agent STOPs and
# returns NEEDS_CONTEXT(SLUG) instead of deriving anything.
# ---------------------------------------------------------------------------


class TestRebaseSlugMandatoryNoFallback:
    """agents/odoo-intent-extractor.md must never derive a fallback SLUG in rebase
    mode either - a derived slug cannot know whether the caller used the per-commit or
    module-batched dispatch shape, so it could silently reopen the shared-commit write
    race. A missing SLUG must STOP the agent, never be silently patched over."""

    def setup_method(self):
        self.text = INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8")
        self.rebase_section = _rebase_mode_section(self.text)

    def test_rebase_slug_derivation_bypass_removed(self):
        """The old 'Slug fallback: ... derive it as <feature-ref>-onto-<new-base>'
        heading must not survive anywhere in the file - that heading IS the bypass."""
        assert "Slug fallback:" not in self.text, (
            "agents/odoo-intent-extractor.md must not carry the old 'Slug fallback:' "
            "derivation heading - it silently reconstructs the bare, non-module-scoped "
            "run slug and reopens the shared-commit intents/<sha>.md write race"
        )
        assert "derive it as `<feature-ref>-onto-<new-base>`" not in self.text, (
            "the literal derivation formula must not survive as a fallback recipe"
        )

    def test_rebase_slug_stated_as_required_no_safe_default(self):
        assert "SLUG` is REQUIRED in rebase mode" in self.rebase_section, (
            "agents/odoo-intent-extractor.md § Rebase mode must state SLUG is REQUIRED - "
            "never a field with a silently-derivable safe default"
        )
        assert "NEVER derive a fallback here" in self.rebase_section, (
            "agents/odoo-intent-extractor.md § Rebase mode must explicitly forbid "
            "deriving a fallback SLUG"
        )

    def test_missing_slug_returns_needs_context_not_a_guess(self):
        """A missing SLUG must produce a structured NEEDS_CONTEXT status in rebase mode
        too, mirroring this agent's own established Brief self-check pattern - never a
        silent derived value."""
        assert "NEEDS_CONTEXT(SLUG)" in self.rebase_section, (
            "agents/odoo-intent-extractor.md § Rebase mode must return NEEDS_CONTEXT(SLUG) "
            "when SLUG is absent, per its own load-bearing-field-no-safe-default rule"
        )

    def test_rebase_section_covers_both_dispatch_shapes(self):
        assert "per-commit dispatch" in self.rebase_section and (
            "module-batched dispatch" in self.rebase_section
        ), (
            "§ Rebase mode's SLUG-required rule must explain both legal dispatch shapes "
            "(bare <slug> for per-commit, <slug>/<module> for module-batched) so a "
            "reader understands why there is no safe fallback to derive"
        )

    def test_brief_self_check_names_slug_as_required_in_both_modes(self):
        """The Brief self-check section (run BEFORE any Steps 1-2 work) must name SLUG
        as required in BOTH modes, so the gap is caught up front for a rebase-mode
        dispatch too, not only discovered at Step 3's write time."""
        self_check = self.text[self.text.index("## Brief self-check"):]
        assert "REQUIRED in BOTH forward-port mode and rebase mode" in self_check, (
            "agents/odoo-intent-extractor.md's Brief self-check must name SLUG as "
            "required in both modes, not forward-port-mode only"
        )

    def test_forward_port_mode_rule_is_unaffected(self):
        """This fix must not weaken forward-port mode's OWN, already-correct
        SLUG-required rule - only correct its cross-reference to rebase mode's rule,
        which is no longer a 'derivation rule' now that rebase mode is also required."""
        assert "`SLUG` is REQUIRED in forward-port mode - NEVER derive a fallback here." in self.text, (
            "forward-port mode's own SLUG-required statement must remain exactly as "
            "established - this fix only extends the same pattern to rebase mode"
        )
        assert "NEEDS_CONTEXT(SLUG) - forward-port mode requires a per-module SLUG" in self.text, (
            "forward-port mode's own NEEDS_CONTEXT(SLUG) refusal must remain unchanged"
        )
        # The forward-port paragraph's cross-reference to rebase mode must be corrected
        # (rebase mode no longer "has its own slug derivation rule" - it has its own
        # identical no-fallback requirement) rather than left stale.
        assert "which has its own slug derivation rule" not in self.text, (
            "the forward-port SLUG paragraph's cross-reference to rebase mode is stale - "
            "rebase mode no longer derives anything, it requires SLUG just like "
            "forward-port mode does"
        )


# ---------------------------------------------------------------------------
# Invariant (consolidation can silently not happen) - the P2 consolidation
# fan-in is a NEW moving part that sits between the module-batched writers
# and every reader. Marking a commit `extracted` the instant its extractor
# returns - before its canonical-path copy is confirmed - means a crash
# between the two, or a resumed run that reads that premature `extracted`,
# leaves P3/P5/P8/P9 reading a path that was never written. Fix: checkpoint
# the two facts SEPARATELY (`extracted-pending-consolidation` -> `extracted`,
# promoted only after the copy is confirmed) and make the copy idempotent so
# a resumed run can safely re-attempt every sha still pending.
#
# RED-before-green evidence (measured by restoring the prior round's fixed
# content - the write-race fix ALONE, without this round's additions - via
# `cp` and re-running this class; see the report for full command output):
#   - 'extracted-pending-consolidation' in SKILL.md / rb-phase-detail.md: 0 -> present.
#   - the old unconditional 'Mark each `status=extracted` ... (both dispatch
#     shapes)' sentence (conflates the two facts): present -> removed.
# ---------------------------------------------------------------------------


class TestConsolidationIsSeparatelyCheckpointedAndResumable:
    """P2 consolidation must never let 'the extractor returned' pass as 'the canonical
    record exists'. The two facts get two checkpoint states, the copy is idempotent, and a
    resumed run re-attempts exactly the shas that never reached the canonical state."""

    def setup_method(self):
        self.skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_checkpoint_schema_declares_the_pending_state(self):
        schema_block = self.skill_text[
            self.skill_text.index("```json", self.skill_text.index("## Checkpoint / resume")):
            self.skill_text.index("```", self.skill_text.index("```json", self.skill_text.index("## Checkpoint / resume")) + 1)
        ]
        assert "extracted-pending-consolidation" in schema_block, (
            "SKILL.md's checkpoint.json schema must declare the "
            "extracted-pending-consolidation intermediate state, not only "
            "extracted|designed|resolved|reviewed|done"
        )

    def test_old_conflated_marking_sentence_is_gone(self):
        assert "for crash-resume (both dispatch shapes)" not in self.phase_text, (
            "the old unconditional 'Mark each status=extracted ... (both dispatch shapes)' "
            "sentence conflated extractor-returned with canonical-record-exists - it must be "
            "replaced by the two-state marking rule"
        )

    def _consolidation_section(self):
        start = self.phase_text.index("### P2 consolidation")
        end = self.phase_text.index("## P3 - Cluster behavior comparison")
        return self.phase_text[start:end]

    def test_module_batched_marks_pending_before_copying(self):
        section = self._consolidation_section()
        assert "extracted-pending-consolidation" in section and "NEVER" in section, (
            "the P2 consolidation section must mark a module-batched commit "
            "extracted-pending-consolidation BEFORE the copy, explicitly never extracted yet"
        )

    def test_promotion_to_extracted_happens_only_after_confirmation(self):
        # Whitespace-normalized: this clause wraps across a Markdown line.
        section = _ws_normalize(self._consolidation_section())
        assert "confirms the destination file exists and is non-empty" in section, (
            "promotion to <sha>: extracted must be gated on git-ops confirming the "
            "canonical file exists and is non-empty - never assumed from the copy call alone"
        )

    def test_copy_is_stated_idempotent(self):
        section = self._consolidation_section().lower()
        assert "idempotent" in section and "no-op" in section, (
            "the consolidation copy must be explicitly documented as idempotent - "
            "re-copying an already-correct file must be a no-op, not an error"
        )

    def test_resume_reattempts_pending_shas_without_redispatching_extractor(self):
        resume_bullets = self.skill_text[self.skill_text.index("**P0 reads checkpoint.json first"):]
        resume_bullets = resume_bullets[: resume_bullets.index("## The pipeline")]
        assert "extracted-pending-consolidation" in resume_bullets and (
            "never re-dispatch the extractor" in resume_bullets
        ), (
            "SKILL.md's P0 resume bullets must state that a extracted-pending-consolidation "
            "commit resumes by re-running ONLY the consolidation copy, never by "
            "re-dispatching the extractor"
        )

    def test_default_per_commit_shape_still_marks_extracted_directly(self):
        """The fix must not force the default (non-batched) dispatch shape through the new
        intermediate state too - it never needed one and still does not."""
        section = self.phase_text[self.phase_text.index("### P2 consolidation"):]
        assert "Default per-commit checkpoint marking" in section, (
            "the default per-commit dispatch shape must keep marking <sha>: extracted "
            "directly in one step - it has no intermediate state to track"
        )


# ---------------------------------------------------------------------------
# Invariant (a missing canonical record must fail closed) - P3 previously had
# no rule refusing to proceed when a non-(a) commit's canonical intents/<sha>.md
# record was absent or empty; it would read as "nothing to compare" instead
# of "the pipeline is broken". Fix: a completeness gate that BLOCKs (reusing
# the pipeline's own existing terminal-status vocabulary, never inventing a
# new one) before any P3 dispatch.
#
# RED-before-green evidence (measured by restoring the prior round's fixed
# content and re-running this class): 'canonical intent record completeness'
# / 'BLOCKED' inside the P3 section: 0 occurrences pre-fix -> present post-fix.
# ---------------------------------------------------------------------------


class TestP3FailsClosedOnMissingCanonicalRecord:
    """P3 must refuse - never silently proceed - when a non-(a) commit has no readable
    canonical intent record, reusing the pipeline's existing BLOCKED vocabulary."""

    def setup_method(self):
        self.skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")
        self.p3_section = self.phase_text[
            self.phase_text.index("## P3 - Cluster behavior comparison"):
            self.phase_text.index("## P4")
        ]

    def test_completeness_gate_section_exists(self):
        assert "### P3 gate: canonical intent record completeness" in self.p3_section, (
            "rb-phase-detail.md must document a P3 completeness gate that runs before any "
            "odoo-diff-comparator dispatch"
        )

    def test_gate_runs_before_the_dispatch_sections(self):
        gate_pos = self.p3_section.index("### P3 gate: canonical intent record completeness")
        prestep_pos = self.p3_section.index("### P3 pre-step: git-ops three-dot diff")
        dispatch_pos = self.p3_section.index("### P3 dispatch: odoo-diff-comparator")
        assert gate_pos < prestep_pos < dispatch_pos, (
            "the completeness gate must appear BEFORE the three-dot-diff pre-step and the "
            "odoo-diff-comparator dispatch - a gate documented after the dispatch it is "
            "meant to guard would not actually block anything"
        )

    def test_gate_returns_blocked_reusing_existing_vocabulary(self):
        gate_section = self.p3_section[
            self.p3_section.index("### P3 gate"):
            self.p3_section.index("### P3 pre-step")
        ]
        assert "status: BLOCKED" in gate_section, (
            "the completeness gate must return the pipeline's existing BLOCKED status, not "
            "silently proceed or invent a new status name"
        )
        assert "SAME `BLOCKED` vocabulary" in gate_section, (
            "the gate must explicitly state it reuses the SAME BLOCKED vocabulary the "
            "agents already use, never a new one"
        )

    def test_gate_cites_the_existing_blocked_precedents_by_name(self):
        gate_section = self.p3_section[
            self.p3_section.index("### P3 gate"):
            self.p3_section.index("### P3 pre-step")
        ]
        assert "commit_dump_path nor commit_dump_paths provided" in gate_section, (
            "the gate must cite odoo-intent-extractor.md's own BLOCKED guard by its exact "
            "phrase, proving this is a reuse of established vocabulary, not a new invention"
        )
        assert "diff_path not provided" in gate_section, (
            "the gate must cite odoo-diff-comparator.md's own BLOCKED guard by its exact "
            "phrase for the same reason"
        )

    def test_gate_delegates_the_check_never_reads_inline(self):
        gate_section = self.p3_section[
            self.p3_section.index("### P3 gate"):
            self.p3_section.index("### P3 pre-step")
        ]
        # Whitespace-normalized: this clause wraps across a Markdown line.
        assert "never read inline" in _ws_normalize(gate_section), (
            "the completeness check must be delegated (git-ops or Explore), matching this "
            "pipeline's established never-read-inline convention for heavy/verification checks"
        )

    def test_skill_md_p3_header_reflects_the_gate(self):
        # Whitespace-normalized: this clause wraps across a Markdown line.
        assert "completeness gate MUST pass before dispatch" in _ws_normalize(self.skill_text), (
            "SKILL.md's P3 phase header must state the completeness gate MUST pass before "
            "any odoo-diff-comparator dispatch, not read as an unconditional 'no gate' phase"
        )
