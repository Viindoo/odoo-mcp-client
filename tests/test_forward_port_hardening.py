"""Invariant tests for forward-port hardening.

Each test pins a specific behavioral contract of the forward-port pipeline.
Tests are named after the RULE they enforce, not the implementation detail
they happen to read.  Every assertion is chosen so it would be RED if the
corresponding change were absent.

Files under test (all under plugins/odoo-ai-agents/):
  - skills/odoo-forward-port/SKILL.md
  - skills/odoo-forward-port/references/fp-phase-detail.md
  - snippets/fp-symbol-survival-check.md
  - snippets/fp-installable-false.md
  - snippets/fp-merge-absorption.md
  - skills/odoo-forward-port/references/fp-triage-table.md
  - skills/_shared/debug-method.md
  - agents/odoo-backend-debugger.md
  - agents/odoo-code-reviewer.md
  - agents/odoo-coder.md
  - skills/odoo-modules-upgrade/SKILL.md
  - skills/odoo-modules-upgrade/references/upg-phase-detail.md
  - skills/odoo-git-rebase/references/rb-phase-detail.md
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SKILL_MD = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
PHASE_DETAIL = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md"
SYMBOL_CHECK = PLUGIN / "snippets" / "fp-symbol-survival-check.md"
INSTALLABLE_FALSE = PLUGIN / "snippets" / "fp-installable-false.md"
TRIAGE_TABLE = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-triage-table.md"
DEBUG_METHOD = PLUGIN / "skills" / "_shared" / "debug-method.md"
BACKEND_DEBUGGER = PLUGIN / "agents" / "odoo-backend-debugger.md"
# CS-C10: odoo-installable-prober is the leaf that resolves the residual
# category-3 ambiguity; no test in this file opened it before CS-C10.
PROBER = PLUGIN / "agents" / "odoo-installable-prober.md"


# ---------------------------------------------------------------------------
# Invariant 1 - i18n non-destructive: no destructive re-export language in
# SKILL.md; instead a safe dispatch to odoo-i18n is present.
# ---------------------------------------------------------------------------

class TestI18nNonDestructive:
    """Forward-port must DELEGATE all .po/.pot work to the odoo-i18n skill and must
    NOT inline the recipe.  The non-destructive contract - including that re-export is
    valid AFTER loading the language - belongs to odoo-i18n, so this skill only
    dispatches and never restates a (potentially contradictory) inline warning."""

    def setup_method(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_destructive_recipe_removed(self):
        """SKILL.md must not instruct re-export per module on an isolated target DB."""
        assert "re-export per module on an isolated target DB" not in self.text, (
            "Destructive i18n re-export recipe still present in SKILL.md"
        )

    def test_i18n_dispatches_to_odoo_i18n_skill(self):
        """SKILL.md must direct i18n work to the odoo-i18n skill (not inline recipe)."""
        assert "odoo-i18n" in self.text, (
            "SKILL.md must reference the odoo-i18n skill for i18n forwarding"
        )

    def test_i18n_recipe_delegated_not_inlined(self):
        """SKILL.md must not inline the contradictory fresh-DB re-export prohibition.

        The flat 'NEVER re-export a .po from a fresh DB' wording reads as forbidding the
        legitimate load-language-then-export path that odoo-i18n owns; forward-port
        delegates the whole recipe to odoo-i18n instead of restating it.
        """
        assert "re-export a `.po` from a fresh DB" not in self.text, (
            "forward-port must not inline the 'NEVER re-export a .po from a fresh DB' "
            "warning - the non-destructive recipe (incl. valid re-export after loading "
            "the language) belongs to odoo-i18n"
        )


# ---------------------------------------------------------------------------
# Invariant 2 - P3.5 pointer-parity: both SKILL.md and fp-phase-detail.md
# reference fp-symbol-survival-check; the snippet itself contains the six
# symbol-class blind-spot markers.
# ---------------------------------------------------------------------------

class TestP35PointerParity:
    """Both prose files must reference [[fp-symbol-survival-check]]; the
    snippet must contain markers for each of the six symbol-class checks."""

    def test_skill_md_references_symbol_survival_check(self):
        """SKILL.md must contain the [[fp-symbol-survival-check]] wikilink."""
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "fp-symbol-survival-check" in text, (
            "SKILL.md missing reference to fp-symbol-survival-check"
        )

    def test_phase_detail_references_symbol_survival_check(self):
        """fp-phase-detail.md must contain the [[fp-symbol-survival-check]] wikilink."""
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "fp-symbol-survival-check" in text, (
            "fp-phase-detail.md missing reference to fp-symbol-survival-check"
        )

    def test_snippet_contains_test_base_class_check(self):
        """fp-symbol-survival-check.md must cover test base-class signature drift."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "test_base_classes" in text, (
            "Symbol-survival snippet missing test_base_classes check (section 2.5a)"
        )

    def test_snippet_contains_file_existence_check(self):
        """fp-symbol-survival-check.md must cover file-existence references."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "file_open" in text, (
            "Symbol-survival snippet missing file-existence check (section 2.5b)"
        )

    def test_snippet_contains_dynamic_ref_check(self):
        """fp-symbol-survival-check.md must cover dynamic ref / xml_id construction."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "dynamic" in text.lower() or "f-string" in text or "f'" in text, (
            "Symbol-survival snippet missing dynamic-ref check (section 2.5c)"
        )

    def test_snippet_contains_python_import_check(self):
        """fp-symbol-survival-check.md must cover python import-statement survival."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "pyflakes" in text, (
            "Symbol-survival snippet missing pyflakes import-survival check (section 2.5d/e)"
        )

    def test_snippet_contains_installable_flag_check(self):
        """fp-symbol-survival-check.md must cover installable-flag transition."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "installable" in text, (
            "Symbol-survival snippet missing installable-flag check (section 2.5f)"
        )

    def test_snippet_includes_tests_dir_in_scope(self):
        """fp-symbol-survival-check.md must explicitly include tests/ in the scope."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "tests/" in text or "`tests/`" in text, (
            "Symbol-survival snippet must include tests/ files in the check scope"
        )

    def test_p45_pyflakes_covers_production_not_only_tests(self):
        """fp-phase-detail.md P4.5 must define two lanes: Lane 1 (ALL .py) and Lane 2 (tests/ only)."""
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "Lane 1" in text, (
            "fp-phase-detail.md P4.5 must introduce Lane 1 (ALL merged-touched .py for compile+pyflakes)"
        )
        assert "Lane 2" in text, (
            "fp-phase-detail.md P4.5 must introduce Lane 2 (tests/ only for ACCEPTANCE GATE)"
        )

    def test_snippet_contains_orm_field_key_check(self):
        """fp-symbol-survival-check.md must contain the ORM create/write field-key class."""
        text = SYMBOL_CHECK.read_text(encoding="utf-8")
        assert "kind=orm-field-key" in text, (
            "Symbol-survival snippet missing orm-field-key kind discriminator (section g)"
        )
        # Pin the section-(g) grounding call by its unique `field='<key>'` placeholder:
        # a bare `entity_lookup(kind='field'` already exists in section (a) and would
        # pass even if section (g) were removed (tautology).
        assert "entity_lookup(kind='field', model='account.move', field='<key>'" in text, (
            "Symbol-survival snippet missing section-(g) entity_lookup field-type grounding "
            "call (field='<key>') for ORM create/write keys"
        )


# ---------------------------------------------------------------------------
# Invariant 3 - the error-count-is-not-a-pass rule: both debug-method.md and
# odoo-backend-debugger.md contain the '0 failed, N error(s)' rule markers.
# ---------------------------------------------------------------------------

class TestErrorCountNotAPassRule:
    """Both the shared debug method doc and the debugger agent must teach the
    rule: N error(s) from setUpClass means tests DID NOT RUN."""

    @pytest.mark.parametrize("path,label", [
        (DEBUG_METHOD, "debug-method.md"),
        (BACKEND_DEBUGGER, "odoo-backend-debugger.md"),
    ])
    def test_error_count_not_pass_rule_present(self, path, label):
        """'error(s)' + 'setUpClass' must both appear (the error-not-a-pass rule)."""
        text = path.read_text(encoding="utf-8")
        assert "error(s)" in text, (
            f"{label}: missing 'error(s)' marker for the error-not-a-pass rule"
        )
        assert "setUpClass" in text, (
            f"{label}: missing 'setUpClass' marker for the error-not-a-pass rule"
        )

    @pytest.mark.parametrize("path,label", [
        (DEBUG_METHOD, "debug-method.md"),
        (BACKEND_DEBUGGER, "odoo-backend-debugger.md"),
    ])
    def test_did_not_run_or_transient_warning_present(self, path, label):
        """The doc must warn that errors mean tests DID NOT RUN."""
        text = path.read_text(encoding="utf-8")
        assert ("DID NOT RUN" in text or "transient" in text), (
            f"{label}: missing 'DID NOT RUN' / 'transient' warning"
        )


# ---------------------------------------------------------------------------
# Invariant 4 - verify isolates auto_install modules and NEVER via a raw CLI
# flag: fp-phase-detail.md must set the delegated `skip_auto_install: true`
# field on the P9 odoo-instance dispatch and must NOT contain a raw
# --skip-auto-install / --http-port CLI flag anywhere.
#
# Superseded assertion (fixed here, not restated): the two tests this class
# replaced (`test_skip_auto_install_present`, `test_http_port_present`)
# asserted the LITERAL '--skip-auto-install' / '--http-port' CLI-flag strings
# were present ANYWHERE in the file. Those strings' only surviving source was
# the raw `odoo-bin -d $ALLOC_DB_NAME --test-enable ... --skip-auto-install
# --http-port=$ALLOC_HTTP_PORT` recipe at P7's collection-gate fallback - the
# exact P8 (PARTIAL, issue #197 sibling) defect this round fixes: a raw
# odoo-bin/allocator recipe bypassing the DELEGATE mandate this SAME file
# enforces at P9 ("DELEGATE - never a raw `allocator.py`/`odoo-bin` recipe").
# Removing that raw block (the correct fix) legitimately makes both old
# assertions RED - requiring the raw CLI flags to survive would require
# keeping the defect. The underlying business rule (auto_install modules
# isolated; port assignment never hand-built by this orchestrator) is
# untouched and re-asserted below against its delegate-consistent form.
# ---------------------------------------------------------------------------

class TestVerifyIsolatesAutoInstallViaDelegate:
    """P9's `odoo-instance` dispatch brief must isolate auto_install modules via the
    delegated `skip_auto_install: true` field: fp-phase-detail.md must never contain a raw
    `--skip-auto-install` / `--http-port` CLI flag - port assignment and auto-install isolation
    are the delegated `odoo-instance`/allocator's own job, never a raw recipe this orchestrator
    hand-builds (the same DELEGATE mandate P9 already states, now unbroken by P7's fallback)."""

    def setup_method(self):
        self.text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_skip_auto_install_field_present_on_p9_dispatch(self):
        """P9's odoo-instance dispatch brief must set skip_auto_install: true."""
        assert "skip_auto_install: true" in self.text, (
            "fp-phase-detail.md P9 dispatch brief missing 'skip_auto_install: true' - "
            "auto_install modules must be isolated via the delegated odoo-instance field, "
            "never a raw --skip-auto-install CLI flag"
        )

    def test_no_raw_skip_auto_install_cli_flag_anywhere(self):
        """No raw '--skip-auto-install' CLI flag may survive anywhere in the file.

        RED-before-green (git show HEAD): 1 occurrence, in the P7 collection-gate fallback's
        raw odoo-bin block (now removed and replaced with a DELEGATE-consistent instruction).
        """
        assert "--skip-auto-install" not in self.text, (
            "fp-phase-detail.md must not contain a raw '--skip-auto-install' CLI flag anywhere - "
            "use the delegated odoo-instance dispatch field 'skip_auto_install: true' instead "
            "(this orchestrator never hand-builds an odoo-bin recipe)"
        )

    def test_no_raw_http_port_cli_flag_anywhere(self):
        """No raw '--http-port' CLI flag may survive anywhere in the file.

        RED-before-green (git show HEAD): 1 occurrence, in the same P7 raw odoo-bin block.
        Port assignment is the delegated odoo-instance/allocator's own job - this orchestrator
        never issues a raw port flag.
        """
        assert "--http-port" not in self.text, (
            "fp-phase-detail.md must not contain a raw '--http-port' CLI flag anywhere - port "
            "assignment belongs to the delegated odoo-instance/allocator, never this orchestrator"
        )

    def test_p5_triages_coinstalled_dep_reds_against_baseline(self):
        """fp-phase-detail.md P5 must instruct triaging reds in co-installed deps against a clean-tip baseline."""
        assert "clean-tip baseline" in self.text, (
            "fp-phase-detail.md missing clean-tip baseline triage instruction in P5"
        )
        assert "co-installed" in self.text, (
            "fp-phase-detail.md P5 must address reds from co-installed dependencies"
        )


# ---------------------------------------------------------------------------
# Invariant 5 - lint-only lane: fp-installable-false.md contains the
# lint-only lane markers; fp-triage-table.md has the short-circuit gate for
# installable:False.
# ---------------------------------------------------------------------------

class TestLintOnlyLane:
    """installable:False modules must be routed to a lint-only lane.
    The snippet must declare it; the triage table must gate on it."""

    def test_installable_false_snippet_has_lint_only_lane(self):
        """fp-installable-false.md must declare the LINT-ONLY LANE explicitly."""
        text = INSTALLABLE_FALSE.read_text(encoding="utf-8")
        assert "lint-only" in text.lower() or "LINT-ONLY" in text, (
            "fp-installable-false.md missing lint-only lane declaration"
        )

    def test_installable_false_snippet_covers_installable_keyword(self):
        """fp-installable-false.md must contain the 'installable' flag rule."""
        text = INSTALLABLE_FALSE.read_text(encoding="utf-8")
        assert "installable" in text, (
            "fp-installable-false.md must reference the installable flag"
        )

    def test_triage_table_has_short_circuit_gate_for_installable_false(self):
        """fp-triage-table.md must have a SHORT-CIRCUIT GATE for installable:False
        before the tier rows so it is checked first."""
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "SHORT-CIRCUIT" in text or "short-circuit" in text.lower(), (
            "fp-triage-table.md missing SHORT-CIRCUIT GATE for installable:False"
        )
        assert "installable" in text, (
            "fp-triage-table.md must mention installable flag in its gate"
        )


# ---------------------------------------------------------------------------
# Invariant 6 - upgrade-scale gate: a large bucket-(c) cluster that is an
# upgrade-scale re-implement must hit an explicit defer-or-do gate, not be
# silently adapted as a mechanical port. Canonical in fp-triage-table.md;
# surfaced in SKILL.md.
# ---------------------------------------------------------------------------

class TestUpgradeScaleGate:
    """Bucket (c) covers a 3-line fix and a 500-line rewrite alike; the gate
    forces a defer-or-do choice when the cluster is an upgrade-scale re-implement."""

    def test_triage_table_defines_upgrade_scale_gate(self):
        """fp-triage-table.md must define the upgrade-scale defer-or-do gate."""
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "upgrade-scale" in text.lower(), (
            "fp-triage-table.md missing the upgrade-scale gate"
        )
        assert "200 LOC" in text, (
            "the gate must state the ~200 LOC new OWL/JS threshold"
        )
        assert "(a) defer" in text and "(b) do now" in text, (
            "the gate must present the explicit defer-or-do options"
        )

    def test_skill_md_surfaces_upgrade_scale_gate_in_flow(self):
        """SKILL.md must surface the upgrade-scale defer-or-do gate in the triage flow."""
        text = SKILL_MD.read_text(encoding="utf-8").lower()
        assert "upgrade-scale" in text, (
            "SKILL.md missing the bucket-(c) upgrade-scale gate"
        )
        assert "defer" in text, (
            "SKILL.md upgrade-scale gate must present the defer (vs do-now) option"
        )


# ---------------------------------------------------------------------------
# Invariant 7 - absorb-all worktree: absorb-all merges resolve conflicts in the
# integration worktree (a child worktree off the uncommitted HEAD cannot see
# them); child-worktree fan-out is the per-commit case only.
# ---------------------------------------------------------------------------

class TestAbsorbAllWorktree:
    """The per-commit child-worktree fan-out must be distinguished from the
    absorb-all case where conflicts live in the integration working tree."""

    def test_phase_detail_clarifies_absorb_all_worktree(self):
        """fp-phase-detail.md P4 must clarify absorb-all vs per-commit worktree handling."""
        low = PHASE_DETAIL.read_text(encoding="utf-8").lower()
        assert "absorb-all" in low, (
            "fp-phase-detail.md missing the absorb-all worktree clarification"
        )
        assert "per-commit" in low, (
            "the clarification must contrast absorb-all with the per-commit case"
        )
        assert "integration worktree" in low, (
            "absorb-all conflicts must resolve in the integration worktree"
        )

    def test_skill_md_surfaces_absorb_all_exception(self):
        """SKILL.md WORK-tier must surface the absorb-all child-worktree exception."""
        low = SKILL_MD.read_text(encoding="utf-8").lower()
        assert "absorb-all" in low, (
            "SKILL.md missing the absorb-all child-worktree exception"
        )
        assert "integration worktree" in low, (
            "SKILL.md must say absorb-all conflicts resolve in the integration worktree"
        )


# ---------------------------------------------------------------------------
# Invariant 8 - installable category-3 (first-enabled at source, not yet
# upgraded for target): fp-installable-false.md teaches the rule AND names
# the TARGET CLEAN-TIP discriminator.
# ---------------------------------------------------------------------------

SOLUTION_DESIGN_SKILL = PLUGIN / "skills" / "odoo-solution-design" / "SKILL.md"


class TestInstallableCategory3CleanTip:
    """fp-installable-false.md must document the third category - a module that
    became installable:True for the first time at source series X but has NOT
    yet been upgraded for the target series Y - AND must name the TARGET
    CLEAN-TIP discriminator (read target state BEFORE the merge)."""

    def setup_method(self):
        self.text = INSTALLABLE_FALSE.read_text(encoding="utf-8")

    def test_category3_rule_documented(self):
        """fp-installable-false.md must document the first-enabled-at-source category."""
        assert "First-enabled at source, not yet upgraded to target" in self.text, (
            "fp-installable-false.md missing the category-3 rule "
            "'First-enabled at source, not yet upgraded to target'"
        )

    def test_category3_first_enabled_label_present(self):
        """fp-installable-false.md must use the 'category-3 first-enabled' label."""
        assert "category-3 first-enabled" in self.text, (
            "fp-installable-false.md missing the 'category-3 first-enabled' label"
        )

    def test_target_clean_tip_discriminator_present(self):
        """fp-installable-false.md must name the TARGET CLEAN-TIP discriminator
        (read the target branch state BEFORE the merge is applied)."""
        assert "TARGET CLEAN-TIP" in self.text, (
            "fp-installable-false.md missing the TARGET CLEAN-TIP discriminator - "
            "agents must read installable status before the merge, not post-merge"
        )


# ---------------------------------------------------------------------------
# Invariant 9 - intent extraction BEFORE plan gate: P1 (intent extract)
# must appear before P4 (plan gate) in SKILL.md, and the P1 heading must
# explicitly state it runs BEFORE the plan gate.
# ---------------------------------------------------------------------------

class TestIntentBeforePlanGate:
    """The intent-extract phase (P1) must precede the plan gate (P4) in SKILL.md,
    both in document order and in explicit prose.  This pins the bug-fix that
    moved the plan gate to AFTER intent + classify + design so the plan carries
    REAL triaged tiers, not guesses."""

    def setup_method(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_intent_phrase_before_plan_gate_in_document_order(self):
        """P1 heading 'Runs BEFORE the plan gate' must appear before P4 heading
        'P4 - Plan gate [Plan Mode]' in SKILL.md (index order check)."""
        intent_marker = "Runs BEFORE the plan gate so the plan is built"
        plan_gate_marker = "P4 - Plan gate [Plan Mode]"
        assert intent_marker in self.text, (
            "SKILL.md P1 must state it 'Runs BEFORE the plan gate so the plan is built'"
        )
        assert plan_gate_marker in self.text, (
            "SKILL.md must have a P4 Plan gate section"
        )
        assert self.text.index(intent_marker) < self.text.index(plan_gate_marker), (
            "P1 intent-extract description must appear BEFORE P4 plan gate in SKILL.md "
            "(the intent+classify+design phases must precede the plan gate)"
        )


# ---------------------------------------------------------------------------
# Invariant 10 - plan gate uses harness Plan Mode, plan.md written as a
# resume RECORD after approval (not as the gate itself).
# ---------------------------------------------------------------------------

class TestPlanGateUsesHarnessPlanMode:
    """SKILL.md must reference EnterPlanMode and ExitPlanMode at the plan gate,
    and must clarify that plan.md is written AFTER approval as a resume RECORD,
    not as the gate itself.  This prevents the agent from using a text-based
    'approve' prompt as a Plan Mode substitute."""

    def setup_method(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_enter_plan_mode_referenced(self):
        """P4 must reference EnterPlanMode (harness Plan Mode tool)."""
        assert "EnterPlanMode" in self.text, (
            "SKILL.md P4 must call EnterPlanMode (the harness Plan Mode UI entry point)"
        )

    def test_exit_plan_mode_referenced(self):
        """P4 must reference ExitPlanMode (harness Plan Mode tool)."""
        assert "ExitPlanMode" in self.text, (
            "SKILL.md P4 must call ExitPlanMode (the harness Plan Mode UI exit point)"
        )

    def test_plan_md_is_written_as_resume_record(self):
        """SKILL.md must clarify plan.md is written after approval as a 'resume RECORD'."""
        assert "plan.md is now a RECORD" in self.text, (
            "SKILL.md P4 must state 'plan.md is now a RECORD' (written after Plan Mode "
            "approval as a resume artifact, not as the gate itself)"
        )


# ---------------------------------------------------------------------------
# Invariant 11 - design route-out carries return_to: odoo-forward-port, and
# odoo-solution-design honors return_to by NOT dispatching a coder.
# ---------------------------------------------------------------------------

class TestDesignRouteOutWithReturnTo:
    """P3 must emit return_to: odoo-forward-port when routing a commit to
    odoo-solution-design; odoo-solution-design must honor return_to by
    entering design-only mode (no code Plan Mode, no coder dispatch)."""

    def test_forward_port_emits_return_to_in_p3(self):
        """SKILL.md P3 must carry 'return_to: odoo-forward-port' in the route-out
        continuation contract payload."""
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "return_to: odoo-forward-port" in text, (
            "SKILL.md P3 must emit 'return_to: odoo-forward-port' so odoo-solution-design "
            "knows to return control to forward-port after design approval"
        )

    def test_solution_design_honors_return_to_no_coder(self):
        """odoo-solution-design SKILL.md must state that when return_to is SET it does
        NOT enter a code Plan Mode and does NOT dispatch a coder."""
        text = SOLUTION_DESIGN_SKILL.read_text(encoding="utf-8")
        assert "do NOT enter a code Plan Mode and do NOT" in text, (
            "odoo-solution-design SKILL.md must forbid code Plan Mode and coder dispatch "
            "when return_to is set (design-only mode for caller-return flow)"
        )

    def test_solution_design_return_to_set_emits_next_caller(self):
        """odoo-solution-design SKILL.md must emit next: <return_to> when return_to is SET."""
        text = SOLUTION_DESIGN_SKILL.read_text(encoding="utf-8")
        assert "`return_to` is SET" in text, (
            "odoo-solution-design SKILL.md must document the return_to-SET branch "
            "that emits next: <return_to> instead of next: odoo-coding"
        )


# ---------------------------------------------------------------------------
# Invariant 12 - odoo-installable-prober wired in classify (P2), and
# 'designed' is a valid checkpoint status.
# ---------------------------------------------------------------------------

class TestProberWiredAndDesignedCheckpoint:
    """SKILL.md P2 must dispatch odoo-installable-prober for ambiguous category-3
    modules; the checkpoint status set must include 'designed' so a crash between
    design-approval and re-entry resumes correctly."""

    def setup_method(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_installable_prober_dispatched_in_classify(self):
        """SKILL.md must wire odoo-installable-prober in the P2 classify phase."""
        assert "odoo-installable-prober" in self.text, (
            "SKILL.md P2 must reference odoo-installable-prober for category-3 ambiguity"
        )

    def test_designed_checkpoint_status_present(self):
        """SKILL.md must include 'status=designed' as a checkpoint status so a
        P3-routed commit can be resumed at the P4 plan gate with its design_doc."""
        assert "status=designed" in self.text, (
            "SKILL.md checkpoint section must include 'status=designed' - required for "
            "resuming a P3-routed commit after design approval"
        )


# ---------------------------------------------------------------------------
# Additional path constants used by tests 13-22 (issue #126 hardening).
# ---------------------------------------------------------------------------

FP_MERGE_ABSORPTION = PLUGIN / "snippets" / "fp-merge-absorption.md"
CODE_REVIEWER = PLUGIN / "agents" / "odoo-code-reviewer.md"
# The forward-port adapt block lives on the backend WRITER (odoo-backend-coder), not the
# odoo-coder per-module full-stack LEAD (which forwards the FP brief to its workers, does not write).
CODER = PLUGIN / "agents" / "odoo-backend-coder.md"
UPG_SKILL = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"
UPG_PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
RB_PHASE_DETAIL = PLUGIN / "skills" / "odoo-git-rebase" / "references" / "rb-phase-detail.md"
UPG_TRIAGE_TABLE = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-triage-table.md"


# ---------------------------------------------------------------------------
# Invariant 13 - C1/C2 in SSOT: fp-merge-absorption.md is the single home
# for the "keep TARGET version on conflict" (C1) and "migration dir retarget"
# (C2 / adapt_version) rules.
#
# RED-before-green evidence (git show 0c4fb1f):
#   - "keep the TARGET" -> ABSENT on base (empty grep)
#   - "Migration dir retarget (C2)" -> ABSENT on base
#   - "adapt_version" -> ABSENT on base
# ---------------------------------------------------------------------------

class TestC1C2InSSot:
    """fp-merge-absorption.md must encode both C1 (keep TARGET version on
    __manifest__.py conflict, never invent a bump) and C2 (migration-dir
    retarget to target series, driven by adapt_version mechanics)."""

    def setup_method(self):
        self.text = FP_MERGE_ABSORPTION.read_text(encoding="utf-8")

    def test_c1_keep_target_marker_present(self):
        """fp-merge-absorption.md must state 'keep the **TARGET**' in the C1 rule.

        Base commit 0c4fb1f: marker absent. RED if C1 edit is reverted.
        The Markdown bold form is **TARGET** (as authored in step 2a of the absorption window).
        """
        # Accepts both plain and bold-Markdown variants of the phrase.
        assert "keep the **TARGET**" in self.text or "keep the TARGET" in self.text, (
            "fp-merge-absorption.md missing C1 'keep the **TARGET**' marker - "
            "the no-bump-on-conflict rule must live here as the SSOT"
        )

    def test_c2_migration_dir_retarget_section_present(self):
        """fp-merge-absorption.md must contain the 'Migration dir retarget (C2)' heading.

        Base commit 0c4fb1f: heading absent. RED if C2 section is removed.
        """
        assert "Migration dir retarget (C2)" in self.text, (
            "fp-merge-absorption.md missing 'Migration dir retarget (C2)' section - "
            "the series-retarget rule must be declared here, not scattered elsewhere"
        )

    def test_c2_adapt_version_mechanics_documented(self):
        """fp-merge-absorption.md must document adapt_version() mechanics.

        Base commit 0c4fb1f: adapt_version absent. RED if the WHY block is removed.
        """
        assert "adapt_version" in self.text, (
            "fp-merge-absorption.md missing adapt_version() mechanics - "
            "the silent-skip explanation must be present so coders understand WHY retarget is required"
        )


# ---------------------------------------------------------------------------
# Invariant 14 - A2 removed (producer-side): fp-installable-false.md must no
# longer carry the old bump-trigger shell gate, and must point at
# fp-merge-absorption for both C1 and C2.
#
# RED-before-green evidence (git show 0c4fb1f:snippets/fp-installable-false.md):
#   - line 125: grep -qE '\.(js|scss|xml)$|/migrations/' -> PRESENT on base
#   - "[[fp-merge-absorption]]" -> ABSENT on base in A2 section
# ---------------------------------------------------------------------------

class TestA2Removed:
    """fp-installable-false.md must not contain the old bump-trigger grep gate
    ('.js/.scss/.xml/migrations/'), and must carry a no-bump pointer pointing
    at [[fp-merge-absorption]] (C1 + C2)."""

    def setup_method(self):
        self.text = INSTALLABLE_FALSE.read_text(encoding="utf-8")

    def test_old_bump_trigger_grep_absent(self):
        """fp-installable-false.md must not contain the old 'grep -qE' bump-trigger.

        Base commit 0c4fb1f line 125: grep -qE pattern present. RED if A2 revert reintroduces it.
        """
        # The old gate: grep -qE '\\.(js|scss|xml)$|/migrations/'
        assert r"grep -qE" not in self.text, (
            "fp-installable-false.md still contains the old 'grep -qE' bump-trigger - "
            "A2 must be replaced by a no-bump pointer; the '.js/.scss/.xml/migrations/' gate is removed"
        )

    def test_old_js_scss_xml_migrations_bump_gate_absent(self):
        """fp-installable-false.md must not reference the .js/.scss/.xml/migrations bump gate.

        Base commit 0c4fb1f line 121-126: '.js file ... .scss ... .xml ... migrations/' present.
        RED if A2 revert reintroduces this phrasing.

        The tombstone line ("that gate is removed") is the only acceptable context for
        /migrations/ - any other line containing it would indicate an active bump trigger.
        """
        # The old bump trigger had /migrations/ in an active instruction context.
        # The current file retains /migrations/ only in the tombstone that explicitly negates
        # it ("that gate is removed"). Guard: no line may contain /migrations/ outside
        # that tombstone context.
        active_trigger_lines = [
            line for line in self.text.splitlines()
            if "/migrations/" in line and "gate is removed" not in line
        ]
        assert not active_trigger_lines, (
            "fp-installable-false.md: /migrations/ found outside tombstone context - "
            "the old bump-trigger gate may have been reintroduced:\n"
            + "\n".join(f"  {line!r}" for line in active_trigger_lines)
        )

    def test_no_bump_pointer_to_fp_merge_absorption_in_a2_section(self):
        """fp-installable-false.md A2 section must carry the C1+C2 no-bump pointer text.

        Base commit 0c4fb1f: A2 section had a shell bump-trigger; the C1/C2 pointer text
        "Both rules: [[fp-merge-absorption]]" was absent from A2. RED if C1+C2 pointer removed.
        The Related-snippets cross-ref existed on base, so we assert the STRONGER inline text.
        """
        # Design §3b: "Both rules: `[[fp-merge-absorption]]` (C1 + C2)."
        assert "Both rules:" in self.text and "fp-merge-absorption" in self.text, (
            "fp-installable-false.md A2 section must carry the 'Both rules: [[fp-merge-absorption]] "
            "(C1 + C2)' no-bump pointer inline (not just in the Related section)"
        )


# ---------------------------------------------------------------------------
# Invariant 15 - Gate de-conflated: SKILL.md must no longer instruct a
# manifest bump when a migrations/ diff is present, AND must reference
# [[fp-merge-absorption]] for the combined C1+C2 rule.
#
# RED-before-green evidence (git show 0c4fb1f:skills/odoo-forward-port/SKILL.md):
#   - line 548-550: "Bump a module's manifest `version` only when the absorbed diff
#     touches a `.js` / `.scss` / `.xml` file or anything under `migrations/`" -> PRESENT on base
#   - "SSOT:\n  `[[fp-merge-absorption]]`" in the gate block -> ABSENT on base
# ---------------------------------------------------------------------------

class TestGateDeConflated:
    """SKILL.md must not carry the old 'bump on migrations/ diff' phrasing, and
    must reference [[fp-merge-absorption]] for the C1+C2 combined gate."""

    def setup_method(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_old_manifest_bump_gate_heading_absent(self):
        """SKILL.md must not retain the old 'Manifest version-bump gate' bullet.

        Base commit 0c4fb1f line 547: "- **Manifest version-bump gate.** Bump a module's manifest"
        present as the old gate. RED if reintroduced. This is distinct from the new C1/C2 gate.
        """
        assert "Manifest version-bump gate" not in self.text, (
            "SKILL.md still contains the old '**Manifest version-bump gate.**' bullet - "
            "the diff-file-type bump rule must be replaced by the de-conflated C1+C2 gate"
        )

    def test_skill_md_gate_references_fp_merge_absorption(self):
        """SKILL.md manifest/migration gate section must reference [[fp-merge-absorption]].

        Base commit 0c4fb1f: the gate section (lines 548-550) referenced [[fp-installable-false]]
        only. RED if fp-merge-absorption reference is removed from the gate.
        """
        # Check the gate sentence leads with the C1/C2 language and points at fp-merge-absorption.
        assert "C1 and C2 are distinct; apply both" in self.text, (
            "SKILL.md gate must de-conflate C1 and C2 as distinct rules with 'apply both'"
        )

    def test_never_auto_bumps_stated_in_gate(self):
        """SKILL.md gate must say forward-port NEVER auto-bumps version.

        Base commit: absent (old gate said the opposite - bump when diff touches js/xml/migrations).
        RED if the unconditional no-bump statement is removed.
        """
        assert "NEVER\n  auto-bumps" in self.text or "NEVER auto-bumps" in self.text, (
            "SKILL.md gate must state forward-port NEVER auto-bumps `version`"
        )


# ---------------------------------------------------------------------------
# Invariant 16 - Producer wiring (non-dead-code): the FP-ENRICHED brief in
# SKILL.md 8b AND the P8b template in fp-phase-detail.md must carry the
# MANIFEST/MIGRATION/PROVENANCE field pointing at [[fp-merge-absorption]], so
# the dispatched coder receives C1/C2/C3 without an extra lookup.
#
# RED-before-green evidence:
#   - SKILL.md line 396 (base): brief did not include MANIFEST/MIGRATION/PROVENANCE
#   - fp-phase-detail.md P8b (base): template did not include C1/C2/C3 field
# ---------------------------------------------------------------------------

class TestProducerWiring:
    """Both SKILL.md 8b and fp-phase-detail.md P8b must carry the
    MANIFEST/MIGRATION/PROVENANCE -> [[fp-merge-absorption]] brief field."""

    def test_skill_md_8b_brief_carries_c1c2c3_field(self):
        """SKILL.md 8b FP-ENRICHED brief must contain MANIFEST/MIGRATION/PROVENANCE field.

        Base commit: absent. RED if the brief field is removed.
        """
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "MANIFEST/MIGRATION/PROVENANCE" in text, (
            "SKILL.md 8b FP-ENRICHED brief must include the MANIFEST/MIGRATION/PROVENANCE "
            "field so the dispatched coder receives the C1/C2/C3 rules via the brief"
        )

    def test_phase_detail_p8b_template_carries_c1c2c3_field(self):
        """fp-phase-detail.md P8b coder brief template must reference [[fp-merge-absorption]].

        Base commit: absent. RED if the brief template field is removed.
        """
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "MANIFEST/MIGRATION/PROVENANCE" in text, (
            "fp-phase-detail.md P8b coder brief template must include the "
            "MANIFEST/MIGRATION/PROVENANCE -> [[fp-merge-absorption]] field"
        )


# ---------------------------------------------------------------------------
# Invariant 17 - C3 vocabulary reuse: fp-merge-absorption.md Triage section
# must contain a C3 source-issue marker; fp-phase-detail.md P11 must lead
# with "pre-existing source bug" (not the old "INHERITED" bare label) and must
# NOT contain the "carry the faithful forward" typo.
#
# RED-before-green evidence (git show 0c4fb1f):
#   - fp-merge-absorption.md: C3 section absent (only FP-delta/pre-existing triage existed)
#   - fp-phase-detail.md P11 line 666: "INHERITED" lead label present
#   - fp-phase-detail.md P11 line 669: "carry the faithful forward" typo present
# ---------------------------------------------------------------------------

class TestC3VocabularyReuse:
    """fp-merge-absorption.md Triage must encode C3 with a source-issue record;
    fp-phase-detail.md P11 must lead with 'pre-existing source bug' and contain
    no 'carry the faithful forward' typo."""

    def test_fp_merge_absorption_has_c3_section(self):
        """fp-merge-absorption.md Triage section must include the '### C3' heading.

        Base commit: C3 heading absent (only FP-delta/pre-existing existed). RED if removed.
        """
        text = FP_MERGE_ABSORPTION.read_text(encoding="utf-8")
        assert "### C3" in text or "C3 - fix old version first" in text, (
            "fp-merge-absorption.md Triage section missing the C3 sub-section "
            "('### C3' or 'C3 - fix old version first') - the fix-old-version-first rule must live here"
        )

    def test_fp_merge_absorption_c3_has_source_issue_marker(self):
        """fp-merge-absorption.md C3 section must contain the canonical source-issue record.

        Base commit: absent. RED if the canonical-row format is removed.
        """
        text = FP_MERGE_ABSORPTION.read_text(encoding="utf-8")
        # Canonical record: '<sha> | C3 | source issue <ref|DEFERRED> | <evidence one-liner>'
        assert "source issue" in text and "DEFERRED" in text, (
            "fp-merge-absorption.md C3 section must include the canonical merge-log record format "
            "with 'source issue' and 'DEFERRED' tokens"
        )

    def test_fp_phase_detail_p11_leads_with_pre_existing_source_bug(self):
        """fp-phase-detail.md P11 must use 'pre-existing source bug' as the primary label.

        Base commit P11 line 666: led with 'INHERITED' (bare label). Worktree leads with
        'pre-existing source bug'. RED if reverted to bare INHERITED.
        """
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "pre-existing source bug" in text, (
            "fp-phase-detail.md P11 must label an inherited defect as 'pre-existing source bug' "
            "(not just 'INHERITED') - the C3 vocabulary must be used consistently"
        )

    def test_fp_phase_detail_p11_no_carry_faithful_typo(self):
        """fp-phase-detail.md must not contain the 'carry the / faithful forward' typo.

        Base commit P11 ~line 669: "carry the\\nfaithful forward" present (split across lines,
        malformed phrase). Worktree: replaced with "forwarded faithfully". RED if reintroduced.
        The pattern spans a possible line-break so we check both variants.
        """
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        # The typo appears as "carry the\nfaithful forward" in the base commit (line-split form).
        # Both single-line and line-split variants must be absent.
        has_typo = (
            "carry the faithful forward" in text
            or "carry the\nfaithful forward" in text
        )
        assert not has_typo, (
            "fp-phase-detail.md P11 must not contain the 'carry the [\\n]faithful forward' typo - "
            "use 'forwarded faithfully' or equivalent correct phrasing"
        )


# ---------------------------------------------------------------------------
# Invariant 18 - Decision #8 installable sub-cases: fp-installable-false.md
# must cover the category-2/3 "reset after merge" case (upgraded-then-forwarded)
# as a DISTINCT section from the new-module landing; SKILL.md P8c must enumerate
# BOTH sub-cases explicitly.
#
# RED-before-green evidence (git show 0c4fb1f):
#   - fp-installable-false.md: "Category 2/3 - manifest reset after merge" heading absent
#   - SKILL.md line 400: "**8c new module** (exists at source, not yet at target)" - single sub-case only
# ---------------------------------------------------------------------------

class TestDecision8InstallableSubcases:
    """fp-installable-false.md must document the 'reset after merge' case; SKILL.md
    P8c must cover both new-module AND upgraded-then-forwarded sub-cases."""

    def test_installable_false_has_reset_after_merge_section(self):
        """fp-installable-false.md must contain 'Category 2/3 - manifest reset after merge'.

        Base commit: heading absent (only new-module landing described). RED if removed.
        """
        text = INSTALLABLE_FALSE.read_text(encoding="utf-8")
        assert "manifest reset after merge" in text, (
            "fp-installable-false.md must document the 'manifest reset after merge' case "
            "for category-2/3 modules (upgraded-then-forwarded, not just new-module landing)"
        )

    def test_skill_md_p8c_covers_two_sub_cases(self):
        """SKILL.md P8c must enumerate 'two sub-cases' for installable:False handling.

        Base commit line 400: only a single '8c new module' sub-case. RED if revert.
        """
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "two sub-cases" in text, (
            "SKILL.md P8c must say 'two sub-cases' to cover both new-module AND "
            "upgraded-then-forwarded scenarios"
        )

    def test_skill_md_p8c_covers_upgraded_then_forwarded(self):
        """SKILL.md P8c must name the 'Upgraded-then-forwarded' sub-case explicitly.

        Base commit: only 'new module' sub-case present. RED if Upgraded-then-forwarded removed.
        """
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "Upgraded-then-forwarded" in text, (
            "SKILL.md P8c must explicitly name the 'Upgraded-then-forwarded' sub-case "
            "so agents know to re-set installable:False when a merge carries installable:True "
            "on a pre-existing dormant module"
        )


# ---------------------------------------------------------------------------
# Invariant 19 - Consumers wired: both odoo-code-reviewer.md and odoo-coder.md
# must contain a forward-port C1/C2/C3 rule block pointing at [[fp-merge-absorption]],
# so the rules reach the executing agents via their brief.
#
# RED-before-green evidence (git show 0c4fb1f):
#   - odoo-code-reviewer.md: no fp-merge-absorption, no C1/C2/C3 FP block
#   - odoo-coder.md: no fp-merge-absorption, no Forward-port adapt block
# ---------------------------------------------------------------------------

class TestConsumersFpMergeAbsorption:
    """odoo-code-reviewer.md and odoo-coder.md must each contain a forward-port
    C1/C2/C3 rule block that references [[fp-merge-absorption]]."""

    @pytest.mark.parametrize("path,label", [
        (CODE_REVIEWER, "odoo-code-reviewer.md"),
        (CODER, "odoo-backend-coder.md"),
    ])
    def test_agent_references_fp_merge_absorption(self, path, label):
        """Agent file must reference [[fp-merge-absorption]] for the FP C1/C2/C3 rules.

        Base commit 0c4fb1f: fp-merge-absorption absent from both agent files. RED if removed.
        """
        text = path.read_text(encoding="utf-8")
        assert "fp-merge-absorption" in text, (
            f"{label} must reference [[fp-merge-absorption]] so the agent knows "
            f"the forward-port C1/C2/C3 rules when a FP brief arrives"
        )

    def test_code_reviewer_has_fp_c1_c2_c3_rule_block(self):
        """odoo-code-reviewer.md must contain the FP C1/C2/C3 review rule block.

        Base commit: no forward-port review block with C1/C2/C3. RED if removed.
        """
        text = CODE_REVIEWER.read_text(encoding="utf-8")
        # All three rule labels must appear in the FP review section.
        assert "C1:" in text and "C2:" in text and "C3:" in text, (
            "odoo-code-reviewer.md must contain a forward-port review block with C1, C2, and C3 "
            "rules so reviewers flag manifest-bump, migration-series, and pre-existing-bug violations"
        )

    def test_coder_has_fp_adapt_rule_block(self):
        """odoo-backend-coder.md must contain the 'Forward-port adapt' rule block.

        The backend WRITER (not the odoo-coder lead) applies C1/C2/C3. RED if removed.
        """
        text = CODER.read_text(encoding="utf-8")
        assert "Forward-port adapt" in text, (
            "odoo-backend-coder.md must contain the 'Forward-port adapt' rule block "
            "so the backend coder applies C1/C2/C3 when a FP brief references [[fp-merge-absorption]]"
        )


# ---------------------------------------------------------------------------
# Invariant 20 - Rule A unconditional: odoo-modules-upgrade SKILL.md and
# upg-phase-detail.md must contain NO migration-script EXCEPTION phrasing,
# NO "series-prefix bump" wording, and upg-phase-detail.md must contain the
# breadcrumb-scan marker '# TODO: Uncomment when upgrading'.
#
# RED-before-green evidence (git show 0c4fb1f):
#   - modules-upgrade SKILL.md line 212: "OCA/upstream -> series-prefix bump" -> PRESENT
#   - upg-phase-detail.md lines 552-554: "EXCEPTION... migration script... field type change" -> PRESENT
#   - upg-phase-detail.md: "# TODO: Uncomment when upgrading" -> ABSENT
# ---------------------------------------------------------------------------

class TestRuleAUnconditional:
    """odoo-modules-upgrade must never emit migration scripts (route to
    odoo-data-migration) and must never bump the manifest version
    (no OCA series-prefix branch); upg-phase-detail.md must encode the
    breadcrumb-scan instruction for the # TODO: Uncomment marker."""

    def test_modules_upgrade_skill_no_series_prefix_bump(self):
        """modules-upgrade SKILL.md must not contain 'series-prefix bump'.

        Base commit line 212: 'OCA/upstream -> series-prefix bump' present. RED if reintroduced.
        """
        text = UPG_SKILL.read_text(encoding="utf-8")
        assert "series-prefix bump" not in text, (
            "modules-upgrade SKILL.md must not contain 'series-prefix bump' - "
            "Rule A is unconditional: no manifest bump regardless of distribution"
        )

    def test_modules_upgrade_skill_never_writes_migration_scripts(self):
        """modules-upgrade SKILL.md must state it NEVER writes migration scripts.

        Base commit: had an EXCEPTION for field-type-change migration scripts. RED if removed.
        """
        text = UPG_SKILL.read_text(encoding="utf-8")
        assert "NEVER writes migration scripts" in text or "NO migration scripts are written" in text, (
            "modules-upgrade SKILL.md must unconditionally state it never writes migration scripts"
        )

    def test_upg_phase_detail_no_series_prefix_bump(self):
        """upg-phase-detail.md must not contain 'series-prefix' as a bump instruction.

        Base commit lines 546-548: 'OCA/upstream/non-Viindoo -> replace the source series prefix'
        present. RED if reintroduced.
        """
        text = UPG_PHASE_DETAIL.read_text(encoding="utf-8")
        # The key old phrase was 'replace the source series prefix with the target series prefix'
        assert "replace the source series prefix" not in text, (
            "upg-phase-detail.md must not instruct 'replace the source series prefix' - "
            "Rule A removes the OCA series-prefix bump branch entirely"
        )

    def test_upg_phase_detail_has_breadcrumb_scan_marker(self):
        """upg-phase-detail.md must contain the '# TODO: Uncomment when upgrading' instruction.

        Base commit: absent. RED if the breadcrumb-scan instruction is removed.
        """
        text = UPG_PHASE_DETAIL.read_text(encoding="utf-8")
        assert "# TODO: Uncomment when upgrading" in text, (
            "upg-phase-detail.md must instruct coders to scan for '# TODO: Uncomment when upgrading' "
            "breadcrumbs left by forward-port before setting auto_install/application"
        )


# ---------------------------------------------------------------------------
# Invariant 21 - OCA absence: the word 'OCA' (as a whole word) must be absent
# from the rewritten plugin files.  CHANGELOG.md is explicitly whitelisted
# (two historical CHANGELOG entries are intentionally preserved).
#
# Scope: plugins/odoo-ai-agents/ tree, excluding CHANGELOG.md.
# Regex: \bOCA\b to avoid false positives on substrings like 'allocation'.
#
# RED-before-green evidence (git show 0c4fb1f): multiple files contained \bOCA\b,
# including modules-upgrade SKILL.md line 212, upg-phase-detail.md lines 434-436,
# and others listed in Group C of solution-design-v2.md §4.
# ---------------------------------------------------------------------------

import re


class TestOcaAbsence:
    """The literal word OCA must not appear in any rewritten plugin file
    (excluding CHANGELOG.md, which intentionally preserves two historical entries)."""

    # Files that were rewritten in Group A/B/C/D of the solution design edit map.
    # Scoping to these files avoids false-positive risk from unrelated future files.
    REWRITTEN_FILES = [
        PLUGIN / "snippets" / "fp-merge-absorption.md",
        PLUGIN / "snippets" / "fp-installable-false.md",
        PLUGIN / "snippets" / "upg-conventions.md",
        PLUGIN / "snippets" / "new-module-manifest.md",
        PLUGIN / "snippets" / "odoo-version-pivots.md",
        PLUGIN / "snippets" / "python-naming-conventions.md",
        PLUGIN / "snippets" / "xml-view-conventions.md",
        PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md",
        PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md",
        PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md",
        PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md",
        PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-classification-table.md",
        PLUGIN / "agents" / "odoo-code-reviewer.md",
        PLUGIN / "agents" / "odoo-coder.md",
        PLUGIN / "docs" / "reference" / "odoo-code-quality.md",
        PLUGIN / "docs" / "reference" / "ODOO-TESTING.md",
        # Group C / Outside-Plugin files from the OCA removal map
        PLUGIN / "skills" / "odoo-support-triage" / "evals" / "evals.json",
        PLUGIN / "skills" / "odoo-feature-check" / "SKILL.md",
        PLUGIN / "skills" / "odoo-objection-handling" / "SKILL.md",
        PLUGIN / "scripts" / "lib" / "odoo-python-matrix.json",
    ]

    def test_oca_word_absent_from_rewritten_files(self):
        """Every rewritten plugin file must have zero occurrences of the word OCA.

        Base commit: multiple files contained \\bOCA\\b (confirmed by git show 0c4fb1f grep).
        RED if any OCA reference is reintroduced into a rewritten file.
        """
        _oca_re = re.compile(r"\bOCA\b")
        violations = []
        for path in self.REWRITTEN_FILES:
            if not path.exists():
                continue  # file may have been deleted (e.g. module-rename.md)
            text = path.read_text(encoding="utf-8")
            matches = _oca_re.findall(text)
            if matches:
                violations.append(f"{path.relative_to(PLUGIN)}: {len(matches)} occurrence(s)")
        assert not violations, (
            "\\bOCA\\b found in rewritten plugin files (CHANGELOG.md is whitelisted - "
            "all other files must be OCA-free after the removal pass):\n"
            + "\n".join(f"  {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Invariant 22 - Rebase analogue: rb-phase-detail.md P8 must contain the
# keep-base-version one-liner (same-series manifest conflict rule) AND must NOT
# import fp-merge-absorption (rebase is same-series only, no cross-series FP logic).
#
# RED-before-green evidence (git show 0c4fb1f:rb-phase-detail.md):
#   - "keep the new-base ref's `version` field unchanged" -> ABSENT on base
#   - "fp-merge-absorption" -> ABSENT on base (and must STAY absent)
# ---------------------------------------------------------------------------

class TestRebaseAnalogue:
    """rb-phase-detail.md P8 must encode the same-series manifest-conflict rule
    (keep base version) WITHOUT importing the cross-series FP C1/C2 mechanics."""

    def setup_method(self):
        self.text = RB_PHASE_DETAIL.read_text(encoding="utf-8")

    def test_rb_p8_keep_base_version_line_present(self):
        """rb-phase-detail.md P8 must say 'keep the new-base ref's version field unchanged'.

        Base commit: absent. RED if the same-series manifest-conflict rule is removed.
        """
        assert "keep the new-base ref" in self.text and "version" in self.text, (
            "rb-phase-detail.md P8 must contain the keep-base-version rule: "
            "'keep the new-base ref's `version` field unchanged - a same-series replay never bumps it'"
        )

    def test_rb_phase_detail_no_fp_merge_absorption_import(self):
        """rb-phase-detail.md must NOT reference fp-merge-absorption.

        The rebase analogue is same-series ONLY; importing cross-series FP C1/C2 migration
        logic would be incorrect. RED if fp-merge-absorption link is added to rb-phase-detail.
        """
        assert "fp-merge-absorption" not in self.text, (
            "rb-phase-detail.md must NOT reference fp-merge-absorption - "
            "the rebase same-series analogue is intentionally isolated from cross-series FP logic"
        )

    def test_rb_phase_detail_same_series_only_qualifier_present(self):
        """rb-phase-detail.md must qualify the version rule as same-series only.

        Base commit: absent. RED if the 'same-series analogue only' qualifier is removed.
        """
        assert "same-series" in self.text.lower() or "Same-series" in self.text, (
            "rb-phase-detail.md must qualify the keep-base-version rule as same-series only, "
            "distinguishing it from the cross-series FP C1/C2 mechanics"
        )


# ---------------------------------------------------------------------------
# Invariant 23 (CS-C7) - upg-triage-table.md must not permit a manifest version
# bump as an ADAPT scenario. Three other files (odoo-modules-upgrade SKILL.md,
# upg-conventions.md Convention 1, upg-classification-table.md) forbid any
# version bump unconditionally; test_modules_upgrade_skill_no_series_prefix_bump
# (above) only catches the "series-prefix bump" phrasing, so a differently
# worded manifest-version-bump permission slips past it - this test closes
# that specific hole.
#
# RED-before-green evidence: both literals verified present as raw substrings
# in upg-triage-table.md row 3 (:19) on the base commit.
# ---------------------------------------------------------------------------

class TestUpgTriageTableNoVersionBump:
    """upg-triage-table.md must not list a manifest version bump as an ADAPT scenario."""

    def test_upg_triage_table_does_not_list_a_manifest_version_bump_as_adapt(self):
        """upg-triage-table.md must contain neither 'manifest version bump' nor
        'version bump with no logic' (whitespace-normalized).

        Base commit row 3 permitted 'a single manifest version bump with no logic
        change' as a haiku-tier ADAPT scenario - contradicting the unconditional
        no-version-bump rule stated in odoo-modules-upgrade SKILL.md,
        upg-conventions.md Convention 1, and upg-classification-table.md.
        """
        text = UPG_TRIAGE_TABLE.read_text(encoding="utf-8")
        norm = " ".join(text.split())
        assert "manifest version bump" not in norm, (
            "upg-triage-table.md must not permit 'a manifest version bump' as an ADAPT "
            "scenario - it contradicts the unconditional no-version-bump rule in "
            "SKILL.md, upg-conventions.md Convention 1, and upg-classification-table.md"
        )
        assert "version bump with no logic" not in norm, (
            "upg-triage-table.md must not permit a 'version bump with no logic' change "
            "as an ADAPT scenario - same contradiction as above"
        )


# ---------------------------------------------------------------------------
# Invariant 24 (CS-C10) - `installable` grounding inverted: disk-read is the
# ONLY path, never OSM. OSM never carries the manifest `installable` flag
# (established empirically: describe_module / module_inspect(summary) /
# check_module_exists return identical field sets with no `installable` line,
# on both a definitely-installable module and a dormant hardware-driver
# module). The pre-CS-C10 prose framed OSM as PRIMARY and the manifest read
# as a fallback; since module_inspect always SUCCEEDS, the "OSM MISS" branch
# never fired and the failure was silent.
#
# Every absence assertion below is whitespace-normalized before searching.
# This is not cosmetic: 'OSM already grounds categories 1-2' is hard-wrapped
# across two source lines in both SKILL.md and fp-phase-detail.md, so a raw
# (non-normalized) `in` check on that literal returns False on the un-fixed
# base commit - a green test that asserts nothing. Verified directly:
#   "OSM already grounds categories 1-2" in raw text -> False (both files)
#   "OSM already grounds categories 1-2" in " ".join(text.split())  -> True
# ---------------------------------------------------------------------------

GENERATOR_DIR = PLUGIN / "generator"
SKILL_TOOL_DEPS = GENERATOR_DIR / "skill_tool_deps.json"
FEATURE_CATALOGER = PLUGIN / "agents" / "odoo-feature-cataloger.md"
FP_ALL_MD = sorted(
    (PLUGIN / "skills" / "odoo-forward-port").rglob("*.md")
) + sorted(PLUGIN.glob("snippets/fp-*.md"))


def _ws_normalize(text):
    """Collapse ALL whitespace (including markdown hard-wraps) to single
    spaces so a literal-phrase search cannot be defeated by line wrapping."""
    return " ".join(text.split())


class TestProberDoesNotGroundInstallableInOSM:
    """odoo-installable-prober.md must resolve `installable` from the target
    clean-tip manifest ONLY. Base commit: Step 1 opens with '**OSM primary.**
    Call `module_inspect`...' and records `target_grounding: osm` on success;
    the manifest read is framed as the OSM-MISS fallback (:53) and
    `target_grounding: ungrounded` is a live enum value (:36, :129).

    RED today (verified against the base commit) on:
      - ':43' contains 'OSM primary.'
      - ':51' contains 'target_grounding: osm'
      - ':36' contains 'ungrounded' (as a value the field can take)
      - the file contains a `module_inspect(` call at all (it is dropped
        from this agent's `mcp_tools` entirely by CS-C10 edit 10)
    """

    def setup_method(self):
        self.text = PROBER.read_text(encoding="utf-8")
        self.norm = _ws_normalize(self.text)

    def test_no_osm_primary_framing_or_osm_grounding_value(self):
        assert "OSM primary" not in self.norm, (
            "odoo-installable-prober.md must not frame OSM as the primary source for "
            "the installable flag - OSM never exposes the manifest installable flag; "
            "disk-read of the target clean-tip manifest is the ONLY path"
        )
        assert "target_grounding: osm" not in self.norm, (
            "odoo-installable-prober.md must never record target_grounding: osm - "
            "grounding is always manifest-file (the only path), never osm"
        )

    def test_ungrounded_grounding_value_is_gone(self):
        assert "ungrounded" not in self.norm, (
            "target_grounding must not offer 'ungrounded' as a value - manifest_path "
            "is now a REQUIRED input, so its absence is a BLOCK, never a degraded/"
            "ungrounded verdict a downstream consumer could misread as a fact"
        )

    def test_no_module_inspect_call_remains(self):
        """After CS-C10, `module_inspect` is dropped from this agent's `mcp_tools`
        (SSOT: skill_tool_deps.json) - the prose must not reference it either."""
        assert "module_inspect" not in self.text, (
            "odoo-installable-prober.md must not call module_inspect - OSM does not "
            "carry the manifest installable flag, so this agent has no remaining use "
            "for it (its mcp_tools list drops it entirely)"
        )

    def test_manifest_path_required_and_blocked_on_absence(self):
        """Presence half: the fix must install the REQUIRED/BLOCKED replacement,
        not just delete the OSM claim and leave nothing in its place."""
        assert "REQUIRED" in self.norm, (
            "manifest_path must be documented as REQUIRED input"
        )
        assert "manifest_path" in self.norm and "BLOCKED" in self.norm, (
            "absence of manifest_path must be documented as a BLOCK outcome"
        )

    def test_absent_key_default_is_stated_explicitly(self):
        """Finding #5: the rule must state Odoo's own default (absent key =
        installable) explicitly - an agent must not have to infer it."""
        assert "absent" in self.norm and "installable" in self.norm.lower(), (
            "the absent-key case must be covered at all"
        )
        # The specific default value must be spelled out next to "absent", not
        # left for the reader to infer from Odoo trivia.
        assert (
            "key is absent" in self.norm or "absent key" in self.norm
        ) and "True" in self.text, (
            "odoo-installable-prober.md must explicitly state that an absent "
            "'installable' key means installable (Odoo's own default is True) - "
            "never leave this to inference"
        )


class TestForwardPortFilesDoNotClaimOSMGroundsInstallable:
    """No forward-port prose file may claim OSM grounds/returns the manifest
    `installable` flag. Glob-derived (not hardcoded) so a future file in
    skills/odoo-forward-port/ or a new snippets/fp-*.md is covered automatically.

    RED today (verified against the base commit) on 3 files / 5 sites:
      - SKILL.md: 'OSM returned `installable:True`' + 'OSM already grounds
        categories 1-2' (P2 prose), and the Model-triage short-circuit's
        `module_inspect(...)` call on the same line as 'installable'
      - fp-phase-detail.md: same two P2 phrases, plus the 8c-bis
        `module_inspect(...)` call carrying a '# read installable' comment
        (two sites: P2 pre-merge probe, 8c-bis re-probe)
      - fp-triage-table.md: both SHORT-CIRCUIT GATE blockquotes read
        'installable' on the line immediately before a `module_inspect(...)` call
    """

    def test_files_glob_is_non_empty_and_matches_known_set(self):
        # Guards the glob itself: if the forward-port tree is ever restructured
        # so this glob silently returns nothing, the two assertions below would
        # vacuously pass. Pin the count, not the exact names, so a genuinely
        # new file still gets covered without editing this test.
        assert len(FP_ALL_MD) >= 3, (
            "expected the forward-port SKILL.md + references/*.md, at minimum "
            f"3 files - glob returned {[str(p) for p in FP_ALL_MD]}"
        )

    def test_no_file_claims_osm_already_grounds_or_osm_returned_installable(self):
        offenders = []
        for path in FP_ALL_MD:
            norm = _ws_normalize(path.read_text(encoding="utf-8"))
            if "OSM already grounds categories 1-2" in norm:
                offenders.append(f"{path.relative_to(PLUGIN)}: 'OSM already grounds categories 1-2'")
            idx = norm.find("OSM returned")
            if idx != -1 and "installable" in norm[idx:idx + 40]:
                offenders.append(f"{path.relative_to(PLUGIN)}: 'OSM returned ... installable'")
        assert not offenders, (
            "the following forward-port files still claim OSM grounds/returns the "
            "installable flag:\n" + "\n".join(offenders)
        )

    def test_no_module_inspect_call_adjacent_to_installable(self):
        """No line calling `module_inspect(` may have 'installable' on that same
        line or the line immediately before it - that adjacency is exactly the
        pattern that presents a non-existent OSM capability as real.

        A 3-line window was tried and rejected: it false-positives on
        snippets/fp-symbol-survival-check.md:320-321 (two unrelated adjacent
        SYMBOL-BROKEN record rows, one mentioning 'module_inspect' for an
        import-resolution check, the next for an installable-flag record) -
        that file needs no CS-C10 edit. The (previous line, this line) window
        flags exactly the 3 real files and nothing else.
        """
        offenders = []
        for path in FP_ALL_MD:
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if "module_inspect(" not in line:
                    continue
                window = " ".join(lines[max(0, i - 1): i + 1])
                if "installable" in window:
                    offenders.append(f"{path.relative_to(PLUGIN)}:{i + 1}: {line.strip()[:80]!r}")
        assert not offenders, (
            "the following lines call module_inspect( adjacent to 'installable' - "
            "OSM does not expose this flag, so the call must not be presented as a "
            "way to read it:\n" + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# Invariant 24 (widened) - the two checks above are scoped to `FP_ALL_MD`
# (forward-port SKILL.md + snippets/fp-*.md only) and their patterns require
# either one exact phrase or a literal `module_inspect(` CALL adjacent to
# 'installable'. `agents/odoo-doc-scoper.md:185` survived both: it is not a
# forward-port file, and it names the tools as bare backtick identifiers
# (`` `module_inspect` ``, no call syntax) in an "optional fallback" framing
# ("...are optional - use them only if disk reads cannot resolve an ambiguous
# `installable` state") rather than either previously-known bad phrase.
#
# Widened guard: scan EVERY .md file in the plugin (not just forward-port),
# for EITHER a call or a bare mention of `module_inspect` / `describe_module` /
# `check_module_exists`, co-occurring with 'installable' in the same logical
# unit - a markdown block-start (table row / list item / blockquote / heading)
# or fenced-block line is always its own unit; otherwise a run of hard-wrap
# continuation lines is one unit, split again on sentence punctuation. That
# co-occurrence is allowed ONLY when the SAME unit also states the tool does
# NOT carry/expose the flag (the correct, established framing) - otherwise it
# is presenting a non-existent OSM capability as usable for `installable`,
# the exact CS-C10 defect this whole Invariant protects.
#
# Line-level (or even 3-line-window) scanning was rejected for the same
# reason `test_no_module_inspect_call_adjacent_to_installable` above already
# rejected a 3-line window: `snippets/fp-symbol-survival-check.md` packs
# multiple unrelated SYMBOL-BROKEN template rows inside one fenced block with
# no separating blank lines, and `agents/odoo-doc-scoper.md`'s own correct
# `depends_in_scope` paragraph mentions 'installable' (a backward reference to
# an earlier, unrelated bullet) far from its own `module_inspect(...)` call on
# the SAME un-wrapped line. Chunking by markdown block-start + sentence
# boundary (never merging across a fence line) separates all of these
# correctly without either false-negativing the forward-port sites the two
# tests above already pin, or false-positiving on either of those two files.
#
# Pre-fix finding count (verified against `git show HEAD:...` for every .md
# file in the plugin, i.e. the tree before this session's fix): exactly 1 -
# `agents/odoo-doc-scoper.md:185`. Confirms this guard is scoped to the real
# defect, not zero (too narrow) and not a pile of unrelated false positives
# (too loose, would need an allowlist - which this deliberately avoids).
# ---------------------------------------------------------------------------

_OSM_INSTALLABLE_TOOL_RE = re.compile(
    r"\b(module_inspect|describe_module|check_module_exists)\b"
)
_OSM_INSTALLABLE_NEGATION_RE = re.compile(
    r"(does not|does n't|never|is not|isn't|n't|omit)\s*[\w\s'`]{0,50}?"
    r"(carr(?:y|ies)|expos(?:e|es|ed)|osm fact|it\b)",
    re.IGNORECASE,
)
_MD_BLOCK_START_RE = re.compile(r"^\s*(\||[-*+]\s|\d+\.\s|>|#{1,6}\s)")
_MD_FENCE_RE = re.compile(r"^\s*```")


def _osm_installable_chunks(text: str):
    """Logical units for the co-occurrence scan below: outside a fenced code
    block, hard-wrap continuation lines merge into one paragraph, split again
    on sentence-ending punctuation; a markdown block-start (table row, list
    item, blockquote, heading) always starts a new unit. Inside a fence,
    every line is its own unit (template/example rows are line-oriented, not
    prose - merging across them is exactly how the fp-symbol-survival-check.md
    false positive would happen)."""
    chunk_lines: list[str] = []
    prev_ended_sentence = True
    in_fence = False

    def flush():
        if not chunk_lines:
            return
        merged = " ".join(chunk_lines)
        chunk_lines.clear()
        for sentence in re.split(r"(?<=[.!?])\s+", merged):
            if sentence.strip():
                yield sentence

    for line in text.splitlines():
        stripped = line.strip()
        if _MD_FENCE_RE.match(line):
            yield from flush()
            in_fence = not in_fence
            prev_ended_sentence = True
            continue
        if in_fence:
            yield from flush()
            if stripped:
                yield stripped
            prev_ended_sentence = True
            continue
        starts_new = (not stripped) or _MD_BLOCK_START_RE.match(line) or prev_ended_sentence
        if starts_new:
            yield from flush()
        if stripped:
            chunk_lines.append(stripped)
        prev_ended_sentence = bool(stripped) and stripped[-1:] in ".!?:"
    yield from flush()


class TestNoFileAnywhereFramesAnOSMToolAsResolvingInstallable:
    """CLASS guard, widened to the WHOLE plugin tree and to a bare tool-name
    mention (not just call syntax) - see the module-level comment above for
    the before/after scope and the false-positive files this was tuned
    against."""

    def test_no_md_file_frames_module_inspect_or_describe_module_as_resolving_installable(self):
        offenders = []
        for path in sorted(PLUGIN.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            for chunk in _osm_installable_chunks(text):
                if not _OSM_INSTALLABLE_TOOL_RE.search(chunk):
                    continue
                if "installable" not in chunk.lower():
                    continue
                if _OSM_INSTALLABLE_NEGATION_RE.search(chunk):
                    continue
                offenders.append(f"{path.relative_to(PLUGIN)}: {chunk[:200]!r}")
        assert not offenders, (
            "the following files frame an OSM tool as usable to resolve `installable` without "
            "stating OSM does not carry/expose that flag - OSM never carries the manifest "
            "`installable` flag; disk-read of __manifest__.py is the ONLY path:\n"
            + "\n".join(offenders)
        )


class TestProberRegistryEntryNamesManifestNotModuleInspect:
    """skill_tool_deps.json's odoo-installable-prober entry (the SSOT `check_deps.py`
    validates) must not list module_inspect among its mcp_tools, and its notes must
    name the manifest read as the mechanism.

    RED today: agents["odoo-installable-prober"]["mcp_tools"] contains
    "module_inspect" (base commit :707).
    """

    def setup_method(self):
        self.deps = json.loads(SKILL_TOOL_DEPS.read_text(encoding="utf-8"))
        self.entry = self.deps["agents"]["odoo-installable-prober"]

    def test_mcp_tools_does_not_reference_module_inspect(self):
        assert "module_inspect" not in self.entry.get("mcp_tools", []), (
            "odoo-installable-prober's mcp_tools must not include module_inspect - "
            "OSM never carries the manifest installable flag, so this tool has no "
            "remaining purpose for this agent"
        )

    def test_notes_name_the_manifest_read(self):
        assert "manifest" in self.entry.get("notes", ""), (
            "odoo-installable-prober's notes must name the manifest read as the "
            "mechanism for resolving installable, not an OSM probe"
        )

    def test_set_active_version_still_present_and_justifies_the_floor(self):
        """set_active_version stays as the sanctioned OSM reachability probe
        (CS-C8) - its version_added is what keeps min_server_version 0.6.0
        justified by check_deps.py's invariant 3 (needed <= floor)."""
        assert self.entry.get("mcp_tools") == ["set_active_version"], (
            "odoo-installable-prober's mcp_tools should be exactly "
            "['set_active_version'] after dropping module_inspect"
        )
        assert self.entry.get("min_server_version") == "0.6.0", (
            "min_server_version must stay 0.6.0 - satisfied by set_active_version's "
            "own version_added floor"
        )


class TestInstallableFalseIsTheOnlyFieldConsumersRead:
    """Finding #3: no consumer parses `target_installable` (the prober's
    internal, per-manifest-read value); the value actually persisted to
    merge-log.md - and the only field name any other file references - is
    `installable_false=yes|no` (the merge_log_line format).

    This binds WRITER (odoo-installable-prober.md's merge_log_line contract)
    to READER (every other forward-port file that acts on the resolved
    installable state): the internal fields (`target_installable`,
    `target_grounding`) must never leak into orchestrator-facing prose, and
    the orchestrator's OWN direct resolution (categories 1-2, no prober
    dispatch) must record the SAME `installable_false=` field to merge-log.md
    that the prober uses - otherwise the majority of modules (which never go
    through the prober) would be invisible to any later reader keying off
    that field name.
    """

    ORCHESTRATOR_FACING = [SKILL_MD, PHASE_DETAIL, TRIAGE_TABLE, INSTALLABLE_FALSE,
                            PLUGIN / "snippets" / "fp-merge-absorption.md"]

    def test_prober_writes_installable_false_field(self):
        text = PROBER.read_text(encoding="utf-8")
        assert "installable_false=" in text, (
            "odoo-installable-prober.md's merge_log_line example must use the "
            "installable_false= field - the one durable, cross-agent-readable name"
        )
        assert "installable_false:" in text, (
            "odoo-installable-prober.md's structured verdict block must expose "
            "installable_false: as a field"
        )

    def test_internal_fields_never_leak_into_orchestrator_facing_prose(self):
        offenders = []
        for path in self.ORCHESTRATOR_FACING:
            text = path.read_text(encoding="utf-8")
            for internal_field in ("target_installable", "target_grounding"):
                if internal_field in text:
                    offenders.append(f"{path.relative_to(PLUGIN)} contains '{internal_field}'")
        assert not offenders, (
            "internal prober-only fields must not appear in orchestrator-facing "
            "prose - the only field crossing that boundary is installable_false:\n"
            + "\n".join(offenders)
        )

    def test_orchestrator_direct_resolution_writes_installable_false_too(self):
        """Categories 1-2 are resolved by the orchestrator directly (no prober
        dispatch) - SKILL.md and fp-phase-detail.md must instruct writing the
        SAME installable_false= field to merge-log.md for those modules, or a
        later reader keying off that field name would be blind to most modules."""
        for path in (SKILL_MD, PHASE_DETAIL):
            text = path.read_text(encoding="utf-8")
            assert "installable_false=" in text, (
                f"{path.relative_to(PLUGIN)} must instruct writing installable_false= "
                "to merge-log.md for the orchestrator's own direct-path modules "
                "(categories 1-2), the same field the prober's merge_log_line uses"
            )


class TestReadmeAndFeatureCatalogerDoNotClaimOSMGroundsInstallable:
    """README.md's forward-port P2 description and odoo-feature-cataloger.md's
    OSM step must not claim OSM supplies the installable flag either - these
    two files sit outside the glob above (README is prose-only docs, the
    cataloger is a different pipeline) but state the identical claim."""

    def test_readme_p2_mentions_manifest_not_just_osm(self):
        readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
        assert "clean-tip manifest" in readme, (
            "README.md's P2 description must mention the target clean-tip manifest "
            "as the installable source, not OSM alone"
        )
        assert "probes target clean-tip + source git-history" not in readme, (
            "README.md's odoo-installable-prober row must not claim it 'probes' "
            "target clean-tip via OSM - it reads the orchestrator-written manifest"
        )

    def test_feature_cataloger_does_not_claim_osm_has_installable_state(self):
        text = FEATURE_CATALOGER.read_text(encoding="utf-8")
        norm = _ws_normalize(text)
        assert "note edition (CE/EE) and installable state" not in norm, (
            "odoo-feature-cataloger.md must not claim check_module_exists/OSM "
            "supplies installable state - it must read the manifest on disk instead"
        )
        assert "__manifest__.py" in text and "installable" in text, (
            "odoo-feature-cataloger.md must still cover installable state, just "
            "grounded via the module's __manifest__.py on disk"
        )


# ---------------------------------------------------------------------------
# Invariant (CS-C11b) - the i18n mandate's compute/dispatch split: 8e COMPUTES
# both conditions from artifacts that already exist (no instance needed) and
# records them on the module's merge-log.md row; the DISPATCH of odoo-i18n
# moves to a new P9.5, which runs only after P9 provisions the instance
# (odoo-i18n hard-BLOCKs without one - dispatching at 8e/P8 would risk a
# redundant second provision).
# ---------------------------------------------------------------------------

class TestI18nMandateComputeDispatchSplit:
    def test_i18n_dispatch_comes_after_the_instance_phase(self):
        """SKILL.md must order P9 (instance provisioned) -> P9.5 (i18n dispatch) -> P10
        (gate). Asserting presence of all three anchors FIRST makes a missing P9.5 a clean
        assertion failure rather than a ValueError from .index() on a not-found substring."""
        text = SKILL_MD.read_text(encoding="utf-8")
        for anchor in ("**P9 - Verify by behavior", "**P9.5 - i18n", "**P10 - Gate merge"):
            assert anchor in text, f"SKILL.md must contain the phase anchor {anchor!r}"
        assert (
            text.index("**P9 - Verify by behavior")
            < text.index("**P9.5 - i18n")
            < text.index("**P10 - Gate merge")
        ), (
            "SKILL.md must order P9 (instance exists) before P9.5 (i18n dispatch) before P10 "
            "(gate) - odoo-i18n hard-BLOCKs without an instance (odoo-i18n/SKILL.md § "
            "Standalone-first fallback), so dispatching it before P9 risks a redundant second "
            "provision"
        )

    def test_8e_computes_and_does_not_dispatch(self):
        """fp-phase-detail.md's 8e block must record i18n_signals + i18n_due and must NOT
        dispatch odoo-i18n inline - the dispatch moved to P9.5, after the P9 instance exists."""
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.find("**8e - i18n")
        assert start != -1, "fp-phase-detail.md must still carry an 8e i18n block"
        end = text.find("\n\nNo convergence or worktree removal step here", start)
        assert end != -1, "8e block must be followed by the post-adapt closing paragraph"
        block = text[start:end]
        normalized_block = _ws_normalize(block)

        assert "i18n_signals" in normalized_block, (
            "8e must record i18n_signals on the module's merge-log.md row"
        )
        assert "i18n_due" in normalized_block, (
            "8e must record i18n_due on the module's merge-log.md row"
        )
        assert "DISPATCH: odoo-i18n" not in normalized_block, (
            "8e must NOT dispatch odoo-i18n inline anymore - the dispatch moved to P9.5, after "
            "the P9 instance exists (odoo-i18n hard-BLOCKs without one)"
        )


# ---------------------------------------------------------------------------
# PR #189 runtime-review fixes F1 (secondary BLOCKS) and F5:
#
# F1 - P9 (RED-then-GREEN verification) never named WORKTREE_PATH anywhere in the
# skill; only P9.5 (i18n) did, and P9.5's own text ASSUMED "the P9 INSTANCE_HANDLE
# whose addons path covers it" - a guarantee P9 never established. odoo-instance's
# WORKTREE_PATH field is optional and silently defaults to a catalog-tree instance
# (per odoo-instance/SKILL.md), so P9 could go GREEN against un-adapted code with
# no error raised. Fix: P9 now passes WORKTREE_PATH: <path>/fp-integration when it
# dispatches odoo-instance, and fp-phase-detail.md's P9 env-bootstrap re-roots the
# CATALOG addons baseline onto that worktree before any odoo-bin call - reusing the
# EXISTING odoo-instance WORKTREE_PATH substitution + allocator --addons-path-override
# mechanism (the same one 3d9928e already wired for odoo-git-rebase/odoo-coding/
# odoo-coder/worker-brief; forward-port was absent from that commit's file list).
#
# F5 - fp-triage-table.md Table 1's short-circuit gate (governs P0, which runs
# BEFORE P2) instructed reading a `manifest_path` described as "the value P2
# resolved" - unexecutable at P0 (`git show ca80dce` proves this forward reference
# replaced a self-contained, P0-executable check). Table 2 (governs P8, after P2)
# keeps the identical phrasing correctly - only Table 1 is wrong. Fix: Table 1's
# gate now cites the SAME disk-read Discriminator fp-installable-false.md already
# defines (mechanically executable at P0, no OSM claim), instead of forward-
# referencing manifest_path.
# ---------------------------------------------------------------------------

class TestP9WorktreeReroot:
    """FIX 4 (F1 secondary BLOCKS): P9 must name WORKTREE_PATH and re-root the
    verify instance's addons path onto the fp-integration worktree, so P9.5's
    'the P9 INSTANCE_HANDLE whose addons path covers it' claim is finally true."""

    def _p9_block(self, text: str, end_anchor: str) -> str:
        start = text.index("**P9 - Verify by behavior")
        end = text.index(end_anchor, start)
        return text[start:end]

    def test_skill_md_p9_passes_worktree_path_to_odoo_instance(self):
        """RED on base commit: SKILL.md's P9 paragraph never mentions WORKTREE_PATH at all -
        grepping the whole skill found it exactly once, inside P9.5, never in P9."""
        text = SKILL_MD.read_text(encoding="utf-8")
        block = _ws_normalize(self._p9_block(text, "**P9.5 - i18n reconcile"))
        assert "WORKTREE_PATH: <path>/fp-integration" in block, (
            "SKILL.md's P9 paragraph must pass WORKTREE_PATH: <path>/fp-integration when "
            "dispatching odoo-instance - without this, odoo-instance silently defaults to a "
            "catalog-tree instance (odoo-instance/SKILL.md: 'Omit for a catalog-tree instance') "
            "and P9 verifies un-adapted code with no error raised"
        )
        assert "--addons-path-override" in block, (
            "SKILL.md's P9 paragraph must name --addons-path-override as the mechanism "
            "WORKTREE_PATH triggers (odoo-instance/SKILL.md § WORKTREE_PATH substitution) - "
            "reusing the existing mechanism, not inventing a second one"
        )

    def test_fp_phase_detail_p9_reroots_before_any_odoo_bin_call(self):
        """RED on base commit: fp-phase-detail.md's P9 'Env-bootstrap' resolved addons_path only
        from the declared instance catalog entry (the principal-checkout catalog default) and
        never re-rooted it onto the fp-integration worktree - confirmed unchanged by this PR
        before this fix."""
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.index("## P9 - Verify by behavior")
        end = text.index("## P10 - Gate merge", start)
        block = text[start:end]
        norm = _ws_normalize(block)

        assert "Worktree re-root" in block, (
            "fp-phase-detail.md's P9 section must carry a named re-root step - the CATALOG "
            "baseline read from the declared instance entry is never the final addons_path "
            "used to verify"
        )
        assert "WORKTREE_PATH: <path>/fp-integration" in norm, (
            "the re-root step must name WORKTREE_PATH: <path>/fp-integration explicitly - the "
            "SAME P4 JOB-tier integration worktree the merge/adapt phases wrote to"
        )
        assert "Addons coverage assertion" in norm, (
            "the re-root step must point at instance-handle-contract.md's Addons coverage "
            "assertion so a miss BLOCKs instead of silently verifying the wrong tree"
        )
        # Ordering: the re-root instruction must appear BEFORE the odoo-instance dispatch that
        # actually consumes the addons path, not as an afterthought below it. P9 delegates to
        # odoo-instance (never a raw allocator.py/odoo-bin call - see the DELEGATE rule at the
        # top of this section); "operation: run-tests" is the dispatch brief field that performs
        # the addons-path-consuming acquire+install+test.
        assert block.index("Worktree re-root") < block.index("operation: run-tests"), (
            "the worktree re-root instruction must precede the odoo-instance dispatch brief in "
            "P9's text - a re-root documented after the dispatch that needs it is easy to miss"
        )

    def test_p95_addons_coverage_claim_is_backed_by_p9(self):
        """P9.5 says 'the P9 INSTANCE_HANDLE whose addons path covers it' - this assertion is
        only true once P9 itself re-roots via WORKTREE_PATH (this test pins the dependency both
        ways: P9.5 still makes the claim, and P9 now backs it)."""
        text = SKILL_MD.read_text(encoding="utf-8")
        p95_start = text.index("**P9.5 - i18n reconcile")
        p95_end = text.index("**P10 - Gate merge", p95_start)
        p95_block = _ws_normalize(text[p95_start:p95_end])
        assert "addons path" in p95_block, (
            "P9.5 must still assert the P9 INSTANCE_HANDLE's addons path covers the worktree"
        )
        p9_block = _ws_normalize(self._p9_block(text, "**P9.5 - i18n reconcile"))
        assert "WORKTREE_PATH: <path>/fp-integration" in p9_block, (
            "P9 must itself pass WORKTREE_PATH so P9.5's addons-path claim is actually true, not "
            "an unbacked assumption"
        )


class TestTable1GateIsP0Executable:
    """FIX 5: Table 1's short-circuit gate (governs P0) must be executable AT P0 - it must not
    forward-reference manifest_path, a P2 artifact that does not exist yet when P0 runs."""

    def _table(self, name_start: str, name_end: str) -> str:
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        start = text.index(name_start)
        end = text.index(name_end, start)
        return text[start:end]

    def test_table1_gate_does_not_forward_reference_p2_manifest_path(self):
        """RED on base commit: Table 1's blockquote reads '...the value P2 resolved into
        `manifest_path`...' - P2 runs strictly AFTER P0/P1 in the documented phase order, so this
        instruction is unexecutable at the point it governs (git show ca80dce proves this
        replaced a self-contained, P0-executable check)."""
        t1 = _ws_normalize(self._table("## Table 1", "## Table 2"))
        assert "the value p2 resolved into" not in t1.lower(), (
            "Table 1's SHORT-CIRCUIT GATE must not forward-reference 'the value P2 resolved into "
            "manifest_path' - P0 (which Table 1 governs) runs before P2; this instruction was "
            "unexecutable at the point it governs"
        )

    def test_table1_gate_is_p0_executable_and_cites_the_discriminator(self):
        t1 = _ws_normalize(self._table("## Table 1", "## Table 2"))
        assert "executable AT P0" in t1 or "P2 has not run yet" in t1, (
            "Table 1's gate must explicitly state it is executable at P0, not deferred to a "
            "later phase's artifact"
        )
        assert "[[fp-installable-false]]" in t1 and "Discriminator" in t1, (
            "Table 1's gate must cite fp-installable-false.md's own Discriminator section (the "
            "SAME disk-read mechanism, already self-contained and P0-executable) rather than "
            "restating or re-inventing a separate check"
        )
        assert "git-toolkit:git-ops" in t1, (
            "Table 1's gate must name the read-only git-toolkit:git-ops mechanism for the disk "
            "read (never OSM - OSM does not carry the installable flag)"
        )

    def test_table2_gate_is_unchanged_and_still_references_manifest_path(self):
        """Table 2 governs P8, which runs AFTER P2 - its identical 'value P2 resolved' phrasing
        is correct there and must NOT be touched by the Table 1 fix (regression guard: this test
        would catch an over-broad find/replace that also stripped Table 2's valid reference)."""
        t2 = _ws_normalize(self._table("## Table 2", "## How the two tables interact"))
        assert "the value p2 resolved into" in t2.lower(), (
            "Table 2's SHORT-CIRCUIT GATE must still reference 'the value P2 resolved into "
            "manifest_path' - Table 2 governs P8, which runs AFTER P2, so this phrasing is "
            "correct there and must not have been removed by the Table 1 fix"
        )


# ---------------------------------------------------------------------------
# Invariant (R2) - forward-port groups by MODULE first, then by commit within
# that module (R2a); at most ONE odoo-intent-extractor instance per module
# across the whole run (R2b); EXTRACT tier prefers sonnet/haiku and gates opus
# on explicit human confirmation (R2c/R2d).
#
# Scope note (GT1): scanned across the WHOLE `skills/` + `agents/` tree (rglob,
# no allowlist) PLUS `README.md`, because the same agent is also dispatched by
# odoo-git-rebase in rebase mode - a future per-commit dispatch regression
# could equally appear there, and the plugin's own hand-maintained README is
# just as capable of drifting stale as any skill/agent file.
#
# WIDENED (group C2): `README.md` was previously OUT of scope - it was
# hand-maintained architecture documentation outside the R2 fix's original
# ownership, found stale (still describing per-commit odoo-intent-extractor
# dispatch with no per-module cap) but reported separately rather than fixed
# or silently allowlisted. Group C2 corrected README.md's stale forward-port
# description (module-first P1/P8, the `at most one`/`ONE instance per
# module` cap) and it is now IN SCOPE below. This does NOT false-positive on
# odoo-git-rebase's own, still-legitimate, per-commit rebase-mode dispatch
# mention in the SAME file: README.md now also states the per-module cap (for
# forward-port), which satisfies this file-level pairing check exactly as it
# already does for any other file that legitimately mixes a qualified
# per-commit mention with an unrelated cap phrase.
#
# `docs/reference/ORCHESTRATION-MAP.md` stays OUT of this scan's scope: it is
# 100% generated from `generator/skill_tool_deps.json` (never hand-edited) and
# self-resolves on the next `make gen` pass, which this fix already made
# correct at the JSON SSOT.
#
# RED-before-green evidence (measured via `git show HEAD:<path>` against this
# same detection logic, before this fix landed):
#   - GT1 (per-commit odoo-intent-extractor dispatch with no per-module cap,
#     skills/+agents/ scope): 2 offenders - SKILL.md, fp-phase-detail.md.
#   - GT2 (agent frontmatter still claims 'one SHA per instance'): 1 offender -
#     agents/odoo-intent-extractor.md.
#   - GT3 (plan.md template has no Module heading before its SHA table): 1
#     offender - fp-phase-detail.md P4 template.
#   - GT4 (Table 1 section has no human-confirm gate phrase): 1 offender -
#     fp-triage-table.md Table 1.
#   - GT1 widened to README.md (group C2, measured via `git show HEAD:
#     plugins/odoo-ai-agents/README.md` against this same detection logic):
#     1 offender - HEAD's README.md states the P1 per-commit dispatch
#     (mermaid + phase table: "Dispatch odoo-intent-extractor per commit")
#     with zero per-module cap phrase ('at most one') anywhere in the file.
# ---------------------------------------------------------------------------

AGENTS_DIR = PLUGIN / "agents"
SKILLS_DIR = PLUGIN / "skills"
README_MD = PLUGIN / "README.md"
INTENT_EXTRACTOR_AGENT = AGENTS_DIR / "odoo-intent-extractor.md"


class TestModuleFirstAgentCardinalityCap:
    """R2b: nowhere in the skills/ or agents/ tree - OR the plugin README - may an
    unqualified per-commit odoo-intent-extractor dispatch instruction exist without the
    per-module cap sitting in the SAME file. A guard matching only the ONE known phrasing
    (SKILL.md's own wording) would leave every other phrasing unguarded while staying
    green - so this scans the whole subtree (+ README.md) instead of grepping one file
    for one string."""

    def _offenders(self):
        offenders = []
        for path in sorted(SKILLS_DIR.rglob("*.md")) + sorted(AGENTS_DIR.rglob("*.md")) + [README_MD]:
            raw = path.read_text(encoding="utf-8")
            text = _ws_normalize(raw)
            if "odoo-intent-extractor" not in text:
                continue
            has_percommit_dispatch = bool(
                re.search(r"odoo-intent-extractor[^.]{0,160}per[- ]commit", text, re.I)
            )
            has_module_cap = "at most one" in text.lower()
            if has_percommit_dispatch and not has_module_cap:
                offenders.append(str(path.relative_to(PLUGIN)))
        return offenders

    def test_no_unqualified_per_commit_dispatch_anywhere_in_skills_or_agents(self):
        """Any file describing an odoo-intent-extractor per-commit dispatch must also
        state the per-module cap ('at most one') in the SAME file - never a bare
        per-commit instruction with no module-cap qualifier anywhere nearby."""
        offenders = self._offenders()
        assert not offenders, (
            "Unqualified per-commit odoo-intent-extractor dispatch (no per-module cap "
            f"phrase in the same file) found in: {offenders}"
        )


class TestIntentExtractorAgentIsModuleScoped:
    """R2b: the agent's OWN frontmatter routing metadata must not regress back to a
    one-SHA-only contract - the caller-side cap (above) and the agent's own
    self-description must never drift apart."""

    def test_frontmatter_does_not_claim_one_sha_per_instance(self):
        text = _ws_normalize(INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8"))
        assert "one SHA per instance" not in text, (
            "agents/odoo-intent-extractor.md frontmatter must not claim 'one SHA per "
            "instance' - the P1 bulk sweep now dispatches one instance per MODULE "
            "(its ordered commit list), not one instance per commit"
        )

    def test_frontmatter_states_one_module_per_instance(self):
        text = _ws_normalize(INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8"))
        assert re.search(r"one module per instance", text, re.I), (
            "agents/odoo-intent-extractor.md frontmatter must state the module-scoped "
            "cardinality contract ('one MODULE per instance')"
        )

    def test_agent_accepts_ordered_commit_dump_paths(self):
        """The agent must accept an ORDERED per-module map (commit_dump_paths), not
        only the single-SHA commit_dump_path field, so one instance can read a whole
        module's commit bundle in one turn."""
        text = INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8")
        assert "commit_dump_paths" in text, (
            "agents/odoo-intent-extractor.md must document the commit_dump_paths "
            "(ordered module-bundle) brief field alongside the single-SHA commit_dump_path"
        )


class TestPlanRecordIsModuleFirst:
    """R2a: the P4 plan.md record - the one artifact the human sees before approving -
    must be grouped by MODULE first, with that module's commits nested inside it, not
    a flat SHA-keyed table with no module grouping at all."""

    def _p4_markdown_block(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        match = re.search(r"## P4 - Plan gate.*?```markdown(.*?)```", text, re.S)
        assert match, "fp-phase-detail.md must contain a P4 plan.md markdown template block"
        return match.group(1)

    def test_plan_template_has_a_module_heading(self):
        block = self._p4_markdown_block()
        assert "## Module:" in block, (
            "fp-phase-detail.md P4 plan.md template must contain a '## Module:' heading - "
            "the plan record must be grouped by module, not a flat commit-only table"
        )

    def test_module_heading_precedes_the_sha_table_in_the_template(self):
        block = self._p4_markdown_block()
        sha_idx = block.find("| SHA")
        module_idx = block.find("## Module:")
        assert sha_idx != -1 and module_idx != -1, (
            "fp-phase-detail.md P4 template must contain both a Module heading and a SHA table"
        )
        assert module_idx < sha_idx, (
            "fp-phase-detail.md P4 template must present the '## Module:' heading BEFORE "
            "the '| SHA' table header - each module's commits are nested under its own "
            "heading, never a flat SHA-keyed table with modules absent"
        )


class TestExtractTierOpusHumanConfirmGate:
    """R2d: opus is the only tier Table 1 (EXTRACT) can reach above sonnet/haiku, and it
    must never be a silent auto-assign - the P4 Plan Mode gate must call it out and get
    explicit human confirmation, the same mechanism Table 2 already uses for fable."""

    def _table1_section(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        start = text.index("## Table 1")
        end = text.index("## Table 2", start)
        return text[start:end]

    def test_table1_section_has_a_human_confirm_gate(self):
        section = self._table1_section()
        assert re.search(r"human confirm|human-confirm|explicit human", section, re.I), (
            "fp-triage-table.md Table 1 section must contain a human-confirm gate for "
            "opus - Table 1 has no fable band, so opus is the only tier this table can "
            "resolve above sonnet/haiku, and R2d requires explicit human approval for it"
        )

    def test_table1_gate_names_the_module_bundle_unit(self):
        section = self._table1_section()
        assert "module bundle" in section.lower() or "MODULE BUNDLE" in section, (
            "fp-triage-table.md Table 1 must resolve the tier per MODULE BUNDLE "
            "(every commit touching that module), not per individual commit"
        )

    def test_table1_gate_has_a_decidable_downgrade_and_suppressed_path(self):
        """The gate must not deadlock when no human is available (an active run-<id> /
        WORKTREE_PATH context) - it must auto-downgrade and record the reason, mirroring
        odoo-coding's own suppressed-gate pattern (reused by pointer, not re-derived)."""
        section = self._table1_section()
        assert "opus declined" in section, (
            "Table 1's gate must record a decline downgrade ('<module>: sonnet (opus "
            "declined)') when the human declines opus"
        )
        assert "gate suppressed" in section, (
            "Table 1's gate must record a suppressed-gate auto-downgrade ('opus "
            "auto-downgraded - gate suppressed') for the no-human-available case - "
            "it must never silently proceed at opus nor deadlock waiting on a human"
        )


# ---------------------------------------------------------------------------
# Invariant (R2b, 8b leg) - the P8 CODE-adapt leg is not an "N coders per module"
# exception. `agents/odoo-coder.md` states its per-round lifecycle is resumable
# (CHP Tier-A); SKILL.md and fp-phase-detail.md rest the per-module cap on the
# `WORKER_AGENT_ID` registry - ids the skill captured from its OWN launches,
# recorded one per module for the whole run. A launch call cannot assign a name,
# so a name-shaped resume identity is unimplementable and must never come back.
#
# Red-before-green: strike the id registry, or reintroduce a minted name, and the
# matching assertion below goes red.
# ---------------------------------------------------------------------------

CODER_COORDINATOR = AGENTS_DIR / "odoo-coder.md"
CODING_SKILL_MD = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"


class TestCoderCoordinatorIsResumableAcrossRounds:
    """agents/odoo-coder.md must state its one-commit-then-report lifecycle is ROUND-scoped, not
    single-shot-forever - a caller MAY resume the SAME named coordinator (CHP Tier-A) for a later
    round instead of cold-spawning a fresh one."""

    def test_coder_states_cross_round_resume_is_permitted(self):
        text = _ws_normalize(CODER_COORDINATOR.read_text(encoding="utf-8"))
        assert "Cross-round resume" in text, (
            "agents/odoo-coder.md must contain a 'Cross-round resume' section stating the "
            "coordinator is round-scoped and may be resumed by the id its launch returned"
        )

    def test_coder_states_done_does_not_preclude_a_later_resume(self):
        text = _ws_normalize(CODER_COORDINATOR.read_text(encoding="utf-8"))
        assert "does not itself terminate you or preclude a later resume" in text, (
            "agents/odoo-coder.md must state that a per-round 'status: DONE' report does not "
            "itself end the coordinator's addressability for a later Tier-A resume"
        )

    def test_coder_default_behavior_is_unchanged_absent_a_resume(self):
        text = _ws_normalize(CODER_COORDINATOR.read_text(encoding="utf-8")).lower()
        assert "this round's" in text and "was your last" in text, (
            "agents/odoo-coder.md must state that absent a resume, a round's DONE "
            "is terminal exactly as today - the resume path must be purely additive"
        )


class TestForwardPort8bLaunchesAndResumesTheCoderById:
    """SKILL.md and fp-phase-detail.md must launch the module's odoo-coder coordinator once and
    carry its captured `WORKER_AGENT_ID` into every later commit, replacing the old blanket
    'excluded from the R2b cap' framing that treated N-coders-per-module as unavoidable."""

    def test_skill_md_no_longer_claims_the_leg_is_unconditionally_excluded(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "EXCLUDED from the R2b cap" not in text, (
            "SKILL.md must not claim the 8b leg is unconditionally EXCLUDED from the R2b cap - "
            "the coordinator is resumable (agents/odoo-coder.md); the gap is narrower and named"
        )

    def test_skill_md_founds_the_per_module_cap_on_a_captured_id_registry(self):
        """R2b (at most one agent per module across the run) must rest on ids the skill CAPTURED
        from its own launches, recorded per module. A name cannot carry it: a launch call cannot
        name the agent it starts, so a name-based cap is unenforceable at runtime."""
        text = _ws_normalize(SKILL_MD.read_text(encoding="utf-8"))
        assert "fp-adapt-<slug>-<module>" not in text, (
            "SKILL.md must not mint an agent NAME for the per-module cap - no launch call can "
            "assign one, so the cap would rest on a primitive that does not exist"
        )
        assert "Per-module agent-id registry" in text, (
            "SKILL.md P8 must declare the per-module id registry the R2b cap rests on"
        )
        assert "one id per module for the WHOLE run" in text, (
            "the registry must be stated as one id per module for the whole run - that IS R2b"
        )

    def test_skill_md_carries_worker_agent_id_field(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "WORKER_AGENT_ID:" in text, (
            "SKILL.md P8 8b must document the WORKER_AGENT_ID brief field carried into "
            "odoo-coding - the SAME field shape the 8a leg uses, an id the caller captured from "
            "its own earlier launch"
        )
        assert "WORKER NAME" not in text, (
            "the retired name-shaped field must not survive alongside the id-shaped one"
        )

    def test_skill_md_states_r2b_is_closed_at_8b_not_a_lingering_gap(self):
        """`skills/odoo-coding/SKILL.md` recognizes `WORKER_AGENT_ID` (the receiving side
        landed), so the OLD interim 'named, bounded gap' / 'does NOT yet satisfy R2b' framing is
        stale and must be replaced by a plain closure statement - an accurate description must
        not overstate a gap that no longer exists."""
        text = _ws_normalize(SKILL_MD.read_text(encoding="utf-8"))
        assert "is CLOSED at the 8b leg" in text, (
            "SKILL.md must state plainly that R2b is now CLOSED at the 8b leg, now that "
            "skills/odoo-coding/SKILL.md's receiving side recognizes WORKER_AGENT_ID"
        )
        assert "a named, bounded gap" not in text and "does NOT yet satisfy R2b" not in text, (
            "SKILL.md must not still claim the old interim fallback framing ('a named, bounded "
            "gap' / 'does NOT yet satisfy R2b') now that the odoo-coding receiving side actually "
            "recognizes WORKER_AGENT_ID and resumes that id"
        )

    def test_phase_detail_p8b_carries_worker_agent_id_field(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "WORKER_AGENT_ID:" in text, (
            "fp-phase-detail.md P8b coder brief template must carry the WORKER_AGENT_ID field - "
            "the SAME field shape 8a's odoo-test-writer leg uses"
        )
        assert "WORKER NAME" not in text, (
            "the retired name-shaped field must not survive in the concrete brief template a "
            "caller copies from"
        )

    def test_phase_detail_mints_no_agent_name(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "fp-adapt-<slug>-<module>" not in text, (
            "fp-phase-detail.md must not mint an agent NAME - the resume identity is the id the "
            "caller's own launch returned"
        )

    def test_phase_detail_states_r2b_is_closed_at_8b_not_a_lingering_gap(self):
        """Same closure requirement as SKILL.md above, mirrored in fp-phase-detail.md."""
        text = _ws_normalize(PHASE_DETAIL.read_text(encoding="utf-8"))
        assert "is CLOSED" in text and "8b" in text, (
            "fp-phase-detail.md must state plainly that R2b is now closed at the 8b leg"
        )
        assert "a named, bounded gap" not in text and "does NOT yet satisfy R2b" not in text, (
            "fp-phase-detail.md must not still claim the old interim fallback framing now that "
            "the odoo-coding receiving side actually recognizes WORKER_AGENT_ID"
        )


# ---------------------------------------------------------------------------
# Invariant (drift guard) - the 8a (odoo-test-writer) and 8b (odoo-coder) cross-
# invocation resume legs MUST use the IDENTICAL field shape: `WORKER_AGENT_ID`,
# an id the caller captured from its OWN earlier launch. Two differently-labeled
# fields for one job is this repo's INST_ADDONS_PATH/ALLOC_ADDONS_PATH failure
# class. The guard is structural on BOTH sides - the sending side (SKILL.md,
# fp-phase-detail.md) and the receiving side (skills/odoo-coding/SKILL.md) - since
# a receiving side that accepts a different shape strands every send.
# ---------------------------------------------------------------------------

_AGENT_NAME_MINT_RE = re.compile(r"fp-adapt-<slug>-<module>")


class TestBothLegsUseTheSameResumeFieldShape:
    """The 8a odoo-test-writer leg and the 8b odoo-coder leg must carry their cross-invocation
    resume identity as the SAME thing: an id the caller captured from ITS OWN earlier launch.
    Neither leg may mint a name (no launch call can assign one), and the RECEIVING side
    (`skills/odoo-coding/SKILL.md`) must accept that IDENTICAL shape, not a second one."""

    @pytest.mark.parametrize("path,label", [
        (SKILL_MD, "SKILL.md"),
        (PHASE_DETAIL, "fp-phase-detail.md"),
    ])
    def test_neither_leg_mints_an_agent_name(self, path, label):
        text = _ws_normalize(path.read_text(encoding="utf-8"))
        assert not _AGENT_NAME_MINT_RE.search(text), (
            f"{label}: a minted agent name (fp-adapt-<slug>-<module>...) survives. A launch call "
            f"cannot assign a name, so a name-based resume identity is unimplementable - both "
            f"legs resume by the id their own launch returned."
        )
        assert "WORKER NAME" not in text, (
            f"{label}: the retired name-shaped resume field survives"
        )

    def test_receiving_side_declares_the_same_worker_agent_id_field(self):
        """The receiving side (skills/odoo-coding/SKILL.md Coder-brief schema) must declare the
        literal `WORKER_AGENT_ID:` field label - the SAME label the sending side (8a/8b, above)
        emits - not a differently-named or differently-shaped acceptance point."""
        text = CODING_SKILL_MD.read_text(encoding="utf-8")
        assert "WORKER_AGENT_ID:" in text, (
            "skills/odoo-coding/SKILL.md must declare a 'WORKER_AGENT_ID:' field in its Coder "
            "brief schema - the receiving side of what forward-port's sending side emits; a "
            "missing or differently-labeled field here would strand the sending side's resume"
        )

    def test_receiving_side_documents_the_field_as_a_captured_id_never_an_invented_string(self):
        """Structural pairing (not just 'mentioned somewhere'): the receiving side must document
        WORKER_AGENT_ID with the SAME provenance declaration the sending side uses, so a future
        reader cannot silently redefine it as a name on this side only."""
        text = _ws_normalize(CODING_SKILL_MD.read_text(encoding="utf-8"))
        assert "captured from ITS OWN earlier launch" in text, (
            "skills/odoo-coding/SKILL.md must document WORKER_AGENT_ID as an id the CALLER "
            "captured from ITS OWN earlier launch"
        )
        assert "never a string anyone invented" in text, (
            "skills/odoo-coding/SKILL.md must forbid an invented value for WORKER_AGENT_ID - "
            "that is exactly the unimplementable name-shaped field this replaced"
        )

    def test_resume_coder_agent_id_field_never_reintroduced(self):
        """Regression guard: the abandoned `RESUME_CODER` (agentId-shaped) field must never
        reappear anywhere in the plugin tree - it was deliberately dropped in favor of the
        `WORKER_AGENT_ID` shape both legs use. This scan already covers the receiving side
        (skills/odoo-coding/SKILL.md sits under PLUGIN too) - no separate receiving-side
        regression guard is needed for this specific check."""
        offenders = []
        for path in sorted(PLUGIN.rglob("*.md")) + sorted(PLUGIN.rglob("*.json")):
            if "RESUME_CODER" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(PLUGIN)))
        assert not offenders, (
            f"'RESUME_CODER' must not appear anywhere in the plugin tree (dropped in favor of "
            f"the WORKER_AGENT_ID shape); found in: {offenders}"
        )


# ---------------------------------------------------------------------------
# R12 runtime-review hardening round: 2 BREAKS (F1, F2), 2 DEGRADES (F3, F4),
# 1 escalated NIT (F6 - PR/acceptance/i18n ordering). Every guard below is
# RED-before-GREEN against `git show HEAD:<path>`, the committed pre-fix
# baseline this round started from; measured counts are recorded in each
# class docstring.
# ---------------------------------------------------------------------------


class TestP8NeverUsesChildWorktree:
    """F2 (BREAKS): P8's own opening framing ('spawn an adapt unit in its own child
    worktree off integration'), the mandatory 'Child worktree path' brief field on 8a/8b, and
    the unconditional 'op: create per-module child worktree' git-ops call all assumed a
    per-module child worktree is available for P8 fan-out. The SAME phase's own
    'CRITICAL - open merge window' rule says MERGE_HEAD (continuous) / CHERRY_PICK_HEAD
    (one-shot/absorb-all) is live for the ENTIRE P6-P9 span of every commit, in BOTH modes - so
    a child worktree can never converge back before P10, and the mandatory field has no value an
    agent can ever safely fill. Reconciled by removing the per-module child worktree entirely:
    P8 always adapts DIRECTLY in the integration worktree (P8 is SERIAL, so there is no
    concurrent writer to filesystem-isolate, and the open-merge window never clears before P8
    runs, in either mode) - a single run-long 'Worktree path' field replaces the unfillable
    'Child worktree path' field, and the 8a/8b 'converge child worktree back' step is dropped
    (there is nothing to converge - the adapt already happened in place).

    RED-before-green (measured via `git show HEAD:<path>`, the committed pre-fix baseline):
      SKILL.md 'spawn an adapt unit in its own child worktree off integration' count = 1
      SKILL.md 'Child worktree path' (any form) count = 4
      fp-phase-detail.md 'op: create per-module child worktree from fp/<slug>' count = 1
      fp-phase-detail.md 'converging back via merge works' (the flawed SUBSEQUENT-commit
        carve-out this fix retracts) count = 1
    All four are 0 in the current tree (GREEN, verified below)."""

    def test_skill_md_no_longer_frames_p8_as_always_child_worktree(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "spawn an adapt unit in its own child worktree off integration" not in text, (
            "SKILL.md P8 must not open by unconditionally framing a per-module child worktree "
            "as P8's normal mode - that framing directly contradicts the SAME phase's own "
            "'CRITICAL - open merge window' rule, which holds on every P8 call in both modes"
        )

    def test_skill_md_states_p8_always_adapts_directly_in_integration(self):
        text = _ws_normalize(SKILL_MD.read_text(encoding="utf-8"))
        assert "P8 8a/8b always adapt DIRECTLY in the integration" in text, (
            "SKILL.md Git topology must state, unconditionally and checkably, that P8 adapts "
            "directly in the integration worktree on every commit, in both modes"
        )
        assert "P8 NEVER uses a per-module child worktree" in text, (
            "SKILL.md P8 must restate the same unconditional rule at its own point of use, not "
            "only in the Git topology section"
        )

    def test_skill_md_drops_the_mandatory_child_worktree_path_field(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "**Child worktree path:" not in text, (
            "SKILL.md must not still declare a mandatory 'Child worktree path' brief field - "
            "F2's own finding is that no P8 invocation can ever validly fill it"
        )

    def test_skill_md_8a_and_8b_briefs_carry_a_stable_integration_worktree_path_field(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert text.count("Worktree path: `<path>/fp-integration`") >= 2, (
            "SKILL.md 8a and 8b briefs must both carry a 'Worktree path: <path>/fp-integration' "
            "field naming the SAME JOB-tier integration worktree for the whole run - never a "
            "per-commit child worktree path"
        )

    def test_phase_detail_drops_the_unconditional_create_child_worktree_op(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "op: create per-module child worktree from fp/<slug>" not in text, (
            "fp-phase-detail.md P8 must not unconditionally create a per-module child worktree "
            "before dispatching the adapt unit - the open-merge window makes it un-convergeable "
            "on every commit, in both modes"
        )

    def test_phase_detail_retracts_the_flawed_subsequent_commit_carveout(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "converging back via merge works" not in text, (
            "fp-phase-detail.md must not claim child-worktree fan-out becomes valid once "
            "'processing a SUBSEQUENT source commit after the previous P10 commit closed the "
            "prior merge' - that gap sits BETWEEN commits, never DURING one: by the time P8 for "
            "the next commit runs, that commit's own P5 has already reopened MERGE_HEAD"
        )

    def test_phase_detail_header_no_longer_claims_work_tier_worktree_per_module(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert (
            "## P8 - Adapt (test-first; serial per-module within a commit; "
            "WORK-tier worktree per module for filesystem isolation)"
        ) not in text, (
            "fp-phase-detail.md's P8 header must not claim a WORK-tier worktree per module - "
            "P8 never reaches the precondition (integration HEAD already committed) that would "
            "make one valid"
        )

    def test_git_topology_states_the_two_independent_reasons_p8_never_fans_out(self):
        text = _ws_normalize(SKILL_MD.read_text(encoding="utf-8"))
        assert "No parallelism to isolate" in text, (
            "SKILL.md Git topology must state P8 is SERIAL, so there is no concurrent writer "
            "for a child worktree to isolate - the first of the two independent reasons P8 "
            "never fans out"
        )
        assert "MERGE_HEAD exists" in text, (
            "SKILL.md Git topology must cite the concrete git error a second merge in the "
            "integration worktree raises, grounding the open-merge-window reason P8 never fans out"
        )


class TestP3DesignDocReachesTheP8bBrief:
    """F1 (BREAKS): P3 routes a non-trivial bucket-(c) commit OUT to odoo-solution-design and
    records the returned `design_doc` in plan.md 'so the run does not adapt blind' - but the 8b
    dispatch brief template that actually invokes `odoo-coding` for that SAME commit had NO
    `DESIGN_DOC` field, so the design never reached the coder. Fixed by adding `DESIGN_DOC` to
    the 8b brief, using the SAME sentinel shape `odoo-coding`'s own brief resolution already uses
    (`DESIGN_DOC: <child TDD path | none>`) rather than inventing a new one - an explicit `none`
    when P3 never routed this commit to design, never an omitted key.

    RED-before-green (measured via `git show HEAD:<path>`): the 8b fenced brief block in
    fp-phase-detail.md (from 'DISPATCH MODEL: <adapt-tier>' to 'USER LANGUAGE: ...') contained
    'DESIGN_DOC' 0 times at HEAD. It is present in the current tree (GREEN, verified below)."""

    _P8B_BLOCK_START = "DISPATCH MODEL: <adapt-tier>"
    _P8B_BLOCK_END = "USER LANGUAGE: <lang | omit when English>"

    def _phase_detail_8b_block(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.index(self._P8B_BLOCK_START)
        end = text.index(self._P8B_BLOCK_END, start)
        return text[start:end]

    def test_phase_detail_8b_brief_carries_design_doc_field(self):
        block = self._phase_detail_8b_block()
        assert "DESIGN_DOC:" in block, (
            "fp-phase-detail.md's 8b dispatch brief template (the ONLY adapt dispatch site for "
            "a P3-routed bucket-(c) commit) must carry a DESIGN_DOC field - omitting it means "
            "the coder adapts blind, exactly what P3's route-out exists to prevent"
        )

    def test_phase_detail_8b_design_doc_uses_the_odoo_coding_none_sentinel_shape(self):
        block = self._phase_detail_8b_block()
        assert "| none>" in block and "DESIGN_DOC:" in block, (
            "fp-phase-detail.md's 8b DESIGN_DOC field must state an explicit 'none' sentinel "
            "for the no-design case (mirroring skills/odoo-coding/SKILL.md's own "
            "'DESIGN_DOC: <child TDD path | none>' convention) rather than omitting the key"
        )

    def test_phase_detail_8b_cites_the_mirrored_odoo_coding_convention(self):
        block = self._phase_detail_8b_block()
        assert "child TDD path | none" in block, (
            "fp-phase-detail.md's 8b brief must cite the exact odoo-coding convention it "
            "mirrors ('DESIGN_DOC: <child TDD path | none>') per the reuse-don't-reinvent "
            "instruction - a previous round inventing a parallel field shape was rejected"
        )

    def test_skill_md_8b_bullet_also_documents_the_design_doc_field(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>" in text, (
            "SKILL.md's own 8b bullet (a second literal-field presentation of the same brief) "
            "must also document the DESIGN_DOC field, kept in lockstep with fp-phase-detail.md"
        )


class TestNoReplyAddressInAnyBriefTemplate:
    """A concrete brief template is what a caller actually copies, so a retired field surviving
    in one re-seeds it even after the schema drops it. None of this skill's three literal brief
    templates - P1, 8a, 8b - may carry a reply address: a launch call cannot name the agent it
    starts and no agent is shown its launcher, so the field can only ever hold a guess. The
    dispatched agent's report is its final message (spawner-completion-contract.md R3)."""

    def test_p1_brief_template_carries_no_reply_address(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.index("DISPATCH MODEL: <extract-tier>")
        end = text.index("USER LANGUAGE: <lang | omit when English>", start)
        block = text[start:end]
        for banned in ("CALLER_ID", "REPLY_TO"):
            assert banned not in block, (
                f"fp-phase-detail.md's P1 odoo-intent-extractor brief template still carries "
                f"{banned!r}"
            )

    def test_8a_brief_template_carries_no_reply_address(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.index("TEST ADAPT MODE: forward this source test to the target platform.")
        end = text.index("RULE: translate to target API", start)
        block = text[start:end]
        for banned in ("CALLER_ID", "REPLY_TO"):
            assert banned not in block, (
                f"fp-phase-detail.md's 8a odoo-test-writer brief template still carries {banned!r}"
            )

    def test_8b_brief_template_carries_no_reply_address(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        start = text.index("DISPATCH MODEL: <adapt-tier>")
        end = text.index("USER LANGUAGE: <lang | omit when English>", start)
        block = text[start:end]
        for banned in ("CALLER_ID", "REPLY_TO"):
            assert banned not in block, (
                f"fp-phase-detail.md's 8b odoo-coding brief template still carries {banned!r}"
            )

    def test_skill_md_8a_and_8b_bullets_carry_no_reply_address(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        for banned in ("CALLER_ID", "REPLY_TO"):
            assert banned not in text, (
                f"SKILL.md's own 8a/8b bullets (the second literal-field presentation of the "
                f"same briefs) still carry {banned!r}"
            )


class TestTable2FableGateSymmetricWithTable1Opus:
    """F4 (DEGRADES): Table 1 (EXTRACT, P4-resolved) states exactly what to record when the
    plan gate is suppressed and a module resolves to opus (Suppressed-gate auto-downgrade).
    Table 2 (ADAPT, fable) stated no equivalent for the IDENTICAL suppression condition - only
    the human-declines branch - so a suppressed-gate fable row had no value to record at this
    skill's own P4 plan gate, and the tier got decided at P8 runtime by odoo-coding's OWN gate
    instead, violating the stated invariant that a tier is part of the approved plan. Fixed by
    adding the symmetric Suppressed-gate auto-downgrade clause to Table 2's fable constraint.

    RED-before-green (measured via `git show HEAD:<path>`): 'gate suppressed' occurrences inside
    Table 2's fable constraint bullet (the text between 'fable is never a default' and the next
    '- A fullstack work-item' bullet) = 0 at HEAD. Non-zero in the current tree (GREEN, verified
    below)."""

    def _table2_fable_constraint_block(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        start = text.index("- **fable is never a default and ALWAYS needs explicit human confirmation**")
        end = text.index("- A fullstack work-item gets ONE tier applied to both legs by default", start)
        return text[start:end]

    def test_table2_fable_constraint_has_a_gate_suppressed_auto_downgrade_clause(self):
        block = self._table2_fable_constraint_block()
        assert "gate suppressed" in block.lower(), (
            "fp-triage-table.md Table 2's fable constraint must state a Suppressed-gate "
            "auto-downgrade clause - Table 1's opus row already has one for the IDENTICAL "
            "suppression condition (P4 Plan Mode suppressed, no human available)"
        )

    def test_table2_records_the_same_auto_downgrade_plan_md_format(self):
        block = self._table2_fable_constraint_block()
        assert "opus (fable auto-downgraded - gate suppressed)" in block, (
            "fp-triage-table.md Table 2 must record the auto-downgrade in the SAME plan.md "
            "format Table 1 and skills/odoo-coding/SKILL.md's own fable gate already use "
            "('<m>: opus (fable auto-downgraded - gate suppressed)')"
        )

    def test_table2_cites_the_mirrored_odoo_coding_pattern(self):
        block = self._table2_fable_constraint_block()
        assert "skills/odoo-coding/SKILL.md" in block, (
            "fp-triage-table.md Table 2's new clause must cite skills/odoo-coding/SKILL.md as "
            "the pattern it mirrors (the same pointer Table 1's own opus gate already uses) - "
            "per the reuse-don't-reinvent instruction, not a freshly invented mechanism"
        )


class TestAcceptanceAndReviewBothPrecedeThePrOpening:
    """F6 (escalated NIT -> real defect): SKILL.md opened the PR and ran the static review at
    P11, BEFORE the cluster-wide acceptance run at P12 - but the repo owner's requirement (already
    shipped this session in the sibling `run-harness` pipeline: i18n, then acceptance, then the
    lint-class gate, then the PR) is that acceptance AND the i18n reconcile both run BEFORE the PR
    opens and before the lint-class/review gate. No genuine data dependency forces the old order:
    acceptance (`odoo-acceptance`) reads only `merge-log.md` + `intents/<sha>.md` and never touches
    the PR; the ONLY sub-step in the old P11 that genuinely needs an open PR is the bot-comment
    cross-check (bot comments cannot predate the PR they are posted on) - every other review item
    is diff-based. Fixed by renumbering: P11 = acceptance (was P12), P12 = PR + review (was P11),
    with PR creation itself moved to the END of P12 (after the diff-based review clears) and the
    bot-comment cross-check kept as the one genuinely post-PR sub-step.

    RED-before-green (measured via `git show HEAD:<path>`): in SKILL.md, the '**P11 - PR + review'
    heading appeared at a LOWER text offset than the '**P12 - End-to-end acceptance' heading (PR
    review before acceptance) - i.e. P11-index < P12-index, backward per the owner's requirement.
    In fp-phase-detail.md, 'op: create PR' appeared at a LOWER offset than 'Attribute every
    finding to the FP diff' (the PR opened before its own review's attribution-diff check ran).
    Both orders are reversed in the current tree (GREEN, verified below)."""

    def test_skill_md_p11_is_now_acceptance_and_precedes_p12_pr_review(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        p11_idx = text.index("**P11 - End-to-end acceptance")
        p12_idx = text.index("**P12 - PR + review")
        assert p11_idx < p12_idx, (
            "SKILL.md must present P11 (end-to-end acceptance) BEFORE P12 (PR + review) - "
            "acceptance and the lint-class review gate must both clear before the PR opens"
        )

    def test_hard_rule_9_states_acceptance_runs_before_p12_pr_and_review(self):
        text = _ws_normalize(SKILL_MD.read_text(encoding="utf-8"))
        assert "P11 dispatches `odoo-acceptance` ONCE" in text, (
            "Hard rule 9 must attribute the mandatory acceptance dispatch to P11, not P12"
        )
        assert "BEFORE P12 pushes the branch, opens the PR, or runs its" in text, (
            "Hard rule 9 must state acceptance (P11) runs BEFORE P12 pushes, opens the PR, or "
            "runs its lint-class review gate - matching the sibling run-harness Pre-PR tail order"
        )

    def test_phase_detail_p12_heading_replaces_the_old_p11_pr_review_heading(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        assert "## P12 - PR + review" in text, (
            "fp-phase-detail.md must rename its PR + review section header to P12, matching "
            "SKILL.md's renumbered phase"
        )
        assert "## P11 - PR + review" not in text, (
            "fp-phase-detail.md must not still carry a stale '## P11 - PR + review' header once "
            "P11 has been reassigned to acceptance"
        )

    def test_phase_detail_pr_creation_happens_after_the_diff_based_review(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        create_pr_idx = text.index("op: create PR")
        attribution_idx = text.index("Attribute every finding to the FP diff before rating it")
        assert attribution_idx < create_pr_idx, (
            "fp-phase-detail.md must run the diff-based review (attribution diff, C3, "
            "installable-lint-only check) BEFORE creating the PR - only the post-PR bot-comment "
            "cross-check genuinely needs an open PR to exist"
        )

    def test_phase_detail_bot_comment_crosscheck_stays_the_one_post_pr_substep(self):
        text = PHASE_DETAIL.read_text(encoding="utf-8")
        create_pr_idx = text.index("op: create PR")
        bot_check_idx = text.index("Cross-check every static-review bot comment on the PR")
        assert create_pr_idx < bot_check_idx, (
            "the bot-comment cross-check must run AFTER PR creation (bot comments cannot "
            "predate the PR they are posted on) - it is the one sub-step this phase's own "
            "reordering must keep post-PR, never a reason to keep the whole review pre-PR-open"
        )


# ---------------------------------------------------------------------------
# Invariant (B2) - shared-commit intent write race: a commit touching modules
# A and B is dispatched to BOTH modules' single P1 extractor instances (by
# design - R2a/R2b), so both would write the identical `intents/<sha>.md` path
# with no owner or merge rule. Fix: the P1 dispatch brief's SLUG field is set
# per-module (`<slug>/<module>`), which the extractor's own write-path
# template (`<ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md`, substituted
# from that field) resolves into a per-module-namespaced path with no change
# needed to agents/odoo-intent-extractor.md.
#
# RED-before-green evidence (measured via `git show HEAD:<path>`):
#   - fp-phase-detail.md P1 brief template: bare 'SLUG: <slug>' (1 occurrence at the
#     line that causes the race) - 'SLUG: <slug>/<module>' -> 0 occurrences.
#   - SKILL.md / fp-phase-detail.md: 'PER-MODULE NAMESPACED' / per-module namespace
#     rationale -> 0 occurrences in either file.
# ---------------------------------------------------------------------------

class TestSharedCommitIntentWritePathPerModule:
    """A commit shared between modules A and B must never let both modules'
    P1 extractor instances write the SAME intents/<sha>.md path - the SLUG
    field driving the extractor's own write-path template must be per-module,
    not the bare run slug."""

    def setup_method(self):
        self.skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_phase_detail_p1_brief_sets_per_module_slug(self):
        """fp-phase-detail.md's P1 dispatch brief template must set
        SLUG: <slug>/<module> - never the bare run SLUG: <slug>."""
        assert "SLUG: <slug>/<module>" in self.phase_text, (
            "fp-phase-detail.md P1 brief template must set 'SLUG: <slug>/<module>' so each "
            "module's extractor writes to a per-module-namespaced intents/ path"
        )

    def test_no_bare_run_slug_survives_in_p1_brief_template(self):
        """The P1 brief template must not still carry a bare 'SLUG: <slug>' line - that
        is exactly the shape that lets two modules' extractors collide on one sha.

        RED-before-green (git show HEAD): 1 occurrence (line 96), the race-causing line
        this fix replaces.
        """
        # Match the exact brief-field line, not the broader "<slug>" token used
        # elsewhere (e.g. commit_dump_paths, which legitimately keeps the bare
        # run-level slug - those are already-resolved, single-writer paths).
        offenders = [
            line for line in self.phase_text.splitlines()
            if line.strip() == "SLUG: <slug>"
        ]
        assert not offenders, (
            "fp-phase-detail.md P1 brief template must not contain a bare 'SLUG: <slug>' "
            "line - it must be 'SLUG: <slug>/<module>' (per-module namespace) to avoid the "
            "shared-commit write race"
        )

    def test_skill_md_states_the_per_module_namespace_rationale(self):
        """SKILL.md's P1 section must explain WHY the namespace is per-module (the
        shared-commit write race), not just change the mechanic silently."""
        assert "PER-MODULE NAMESPACED" in self.skill_text, (
            "SKILL.md P1 must carry the 'PER-MODULE NAMESPACED' write-path rationale"
        )
        assert "write race" in self.skill_text.lower(), (
            "SKILL.md P1 must name the write race this namespace closes"
        )

    def test_extractor_agent_write_path_template_still_slug_parametrized(self):
        """The main B2 fix does not require editing agents/odoo-intent-extractor.md's write-path
        TEMPLATE - it is already parametrized by the brief's SLUG field, so a per-module SLUG
        value alone resolves the collision with no template change. (A SEPARATE hardening of
        this SAME agent's missing-SLUG BEHAVIOR - closing the bypass where an absent SLUG was
        silently derived back to the bare, non-module-scoped shape - is covered by
        TestForwardPortSlugMandatoryNoFallback below; that fix touches this file, just not this
        template line.)"""
        text = INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8")
        assert "<ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md" in text, (
            "agents/odoo-intent-extractor.md's write-path template must still read the "
            "SLUG field verbatim (unchanged) - the per-module namespace is achieved entirely "
            "by what value the caller passes into that field, not by editing this template"
        )

    def test_p3_route_out_carries_one_intent_record_per_module(self):
        """P3's design route-out payload must point at each touched module's OWN
        intent record, not a single flat path shared across modules."""
        assert "<ISOLATE_DIR>/forward-port/<slug>/<module>/intents/<sha>.md" in self.phase_text, (
            "fp-phase-detail.md P3's intent_records payload must use the per-module path "
            "shape, one entry per module in the `modules` list"
        )

    def test_skill_md_never_restates_the_write_path_backwards(self):
        """SKILL.md must never restate the per-module write path as
        `intents/<module>/<sha>.md` (module segment AFTER `intents/`) anywhere in the
        file - the shape is `<module>/intents/<sha>.md` (module segment BEFORE
        `intents/`), per this same section's own definition a few lines above (module
        A's instance writes `.../A/intents/<sha>.md`).

        The previous version of `test_p3_route_out_carries_one_intent_record_per_module`
        (above) only ever read `fp-phase-detail.md` for the correct-order claim - it
        never opened `SKILL.md` for the same claim, so SKILL.md silently restating the
        SAME artifact's path backwards in 5 places (P11 acceptance dispatch x2, the
        crash-recovery instruction, the Continuation Contract `produced` list, and the
        P3 route-out payload) was invisible to the suite. This test closes that hole
        directly; `TestPathShapeSegmentOrderConsistency` below closes it generally
        (whole-tree, not just these two files).

        RED-before-green (measured via `git show HEAD:plugins/odoo-ai-agents/skills/odoo-forward-port/SKILL.md`,
        i.e. the pre-fix state this test's own change corrects): 5 occurrences of the
        literal substring `intents/<module>` in SKILL.md (lines 699, 703, 830, 917, 924)
        -> 0 occurrences post-fix. Same check applied to fp-phase-detail.md catches its
        1 backward occurrence (line 502) -> 0 post-fix.
        """
        assert "intents/<module>" not in self.skill_text, (
            "SKILL.md restates the per-module intent write path backwards as "
            "'intents/<module>/...' somewhere in the file - the shape is "
            "'<module>/intents/...' (module segment BEFORE 'intents/'), matching this "
            "same file's own P1 definition (module A writes '.../A/intents/<sha>.md')"
        )
        assert "intents/<module>" not in self.phase_text, (
            "fp-phase-detail.md restates the per-module intent write path backwards as "
            "'intents/<module>/...' somewhere in the file - the shape is "
            "'<module>/intents/...' (module segment BEFORE 'intents/')"
        )


# ---------------------------------------------------------------------------
# Invariant (B2 bypass) - the caller-side fix above (SLUG: <slug>/<module> in the
# P1 dispatch brief) only closes the shared-commit write race if the CALLEE
# (agents/odoo-intent-extractor.md) actually uses whatever SLUG it is given. The
# agent's own Step 3 (forward-port mode) documented a fallback - "if absent,
# derive it from the source and target branch names" - that reconstructs the
# bare, non-module-scoped run slug whenever a caller omits SLUG, silently
# reopening the exact write race B2 closes. Fix: SLUG is now a REQUIRED,
# no-safe-default field in forward-port mode (mirrors this agent's own
# established Brief self-check pattern for OBJECTIVE/ACCEPTANCE/INPUTS) - the
# agent STOPs and returns NEEDS_CONTEXT(SLUG) instead of deriving anything.
# Rebase mode's OWN, separate slug-derivation rule (§ Rebase mode) was left
# untouched by THIS fix - it carried an identical bypass ("Slug fallback:
# ... derive it as <feature-ref>-onto-<new-base>") reachable once
# odoo-git-rebase's own module-batched dispatch (SKILL.md P2, "Above ~30
# non-(a) commits, batch intent extraction by MODULE") shares a commit
# between two modules' bundles. That gap was closed in a later round: § Rebase
# mode now also requires a concrete SLUG with no derived fallback, mirroring
# this same pattern - see `tests/test_git_rebase_intent_race.py` for that
# fix's own red-before-green evidence and guard suite.
# ---------------------------------------------------------------------------

class TestForwardPortSlugMandatoryNoFallback:
    """agents/odoo-intent-extractor.md must never derive a fallback SLUG in forward-port
    mode - a derived, non-module-scoped slug would silently reopen the B2 shared-commit
    write race. A missing SLUG must STOP the agent, never be silently patched over."""

    def setup_method(self):
        self.text = INTENT_EXTRACTOR_AGENT.read_text(encoding="utf-8")

    def test_forward_port_slug_derivation_bypass_removed(self):
        """The old 'if absent, derive it from the source and target branch names' fallback
        must not survive anywhere in the file - that phrase IS the bypass."""
        assert "if absent, derive it" not in self.text, (
            "agents/odoo-intent-extractor.md must not silently derive a fallback SLUG in "
            "forward-port mode - that reconstructs the bare, non-module-scoped run slug and "
            "reopens the B2 shared-commit intents/<sha>.md write race"
        )

    def test_slug_stated_as_required_no_safe_default(self):
        assert "SLUG` is REQUIRED in forward-port mode" in self.text, (
            "agents/odoo-intent-extractor.md Step 3 must state SLUG is REQUIRED in "
            "forward-port mode - never a field with a silently-derivable safe default"
        )
        assert "NEVER derive a fallback here" in self.text, (
            "agents/odoo-intent-extractor.md must explicitly forbid deriving a fallback SLUG"
        )

    def test_missing_slug_returns_needs_context_not_a_guess(self):
        """A missing SLUG must produce a structured NEEDS_CONTEXT status, mirroring this
        agent's own established Brief self-check pattern - never a silent derived value."""
        assert "NEEDS_CONTEXT(SLUG)" in self.text, (
            "agents/odoo-intent-extractor.md must return NEEDS_CONTEXT(SLUG) when SLUG is "
            "absent in forward-port mode, per its own load-bearing-field-no-safe-default rule"
        )

    def test_brief_self_check_names_slug_as_a_required_field(self):
        """The Brief self-check section (run BEFORE any Steps 1-2 work) must also name SLUG,
        so the gap is caught up front rather than only discovered at Step 3's write time."""
        self_check = self.text[self.text.index("## Brief self-check"):]
        assert "`SLUG`" in self_check and "forward-port mode" in self_check, (
            "agents/odoo-intent-extractor.md's Brief self-check must name SLUG as a "
            "forward-port-mode-required field, not leave the gap undiscoverable until Step 3"
        )

    def test_rebase_mode_no_longer_derives_a_fallback_slug(self):
        """Rebase mode's OWN slug-derivation rule carried an identical B2-shaped bypass -
        reachable once odoo-git-rebase's module-batched dispatch (SKILL.md P2, above the
        ~30-non-(a)-commit threshold) shares a commit between two modules' bundles. That gap
        was closed in a later round (see tests/test_git_rebase_intent_race.py for the full
        red-before-green guard suite); this test only confirms the old bypass phrase is gone
        and the two modes' requirements are still cross-referenced correctly, not conflated."""
        assert "Slug fallback:" not in self.text, (
            "agents/odoo-intent-extractor.md must not carry the old 'Slug fallback:' "
            "derivation heading in rebase mode - it was replaced with a required, "
            "no-fallback SLUG rule mirroring forward-port mode's own fix"
        )
        assert "SLUG` is REQUIRED in rebase mode" in self.text, (
            "agents/odoo-intent-extractor.md § Rebase mode must now state SLUG is REQUIRED "
            "with no fallback, mirroring forward-port mode's own established rule"
        )
        # Whitespace-normalized: this clause wraps across a Markdown line.
        assert "rebase mode's own identical no-fallback SLUG requirement is" in _ws_normalize(
            self.text
        ), (
            "the forward-port SLUG-required rule must still cross-reference rebase mode's "
            "(now also required, no-fallback) SLUG rule so a reader does not conflate the "
            "two modes' Brief self-check triggers"
        )


# ---------------------------------------------------------------------------
# Invariant (B3) - Tier-C has a legal retry for a failed/incomplete P1 module
# pass. The contract sanctions exactly one retry (a CHP Tier-A resume of the
# SAME instance) and calls a second instance "a pipeline defect, never a valid
# retry" - with no carve-out for when Tier-A itself is unavailable. Fix: an
# explicit Tier-C retry path - a
# SUPERSEDING fresh dispatch (never a second CONCURRENT one) once the failed
# instance's turn has fully ended.
#
# RED-before-green evidence (measured via `git show HEAD:<path>`): 0
# occurrences of 'Tier-C retry', 'SUPERSEDING dispatch', or 'PRIOR ATTEMPT' in
# either SKILL.md or fp-phase-detail.md.
# ---------------------------------------------------------------------------

class TestTierCRetryForFailedModulePass:
    """A failed or incomplete P1 module pass must have a legal retry path even when
    CHP Tier-A is unavailable - never an unsatisfiable instruction."""

    def setup_method(self):
        self.skill_text = SKILL_MD.read_text(encoding="utf-8")
        self.phase_text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_skill_md_states_a_tier_c_retry_path(self):
        assert "Tier-C retry" in self.skill_text, (
            "SKILL.md P1 must name an explicit Tier-C retry path for a failed/incomplete "
            "module pass - the contract cannot sanction only a Tier-A resume with no "
            "fallback when no resume is possible"
        )
        assert "SUPERSEDING" in self.skill_text, (
            "SKILL.md's Tier-C retry must be framed as a SUPERSEDING dispatch (replacing the "
            "dead instance), never a second concurrent one - otherwise it would re-violate R2b"
        )

    def test_phase_detail_mirrors_the_tier_c_retry_path(self):
        normalized = _ws_normalize(self.phase_text)
        assert "Tier-C" in normalized, (
            "fp-phase-detail.md's P1 section must mirror the Tier-C retry carve-out, not "
            "leave the stricter (unsatisfiable) resume-only retry rule unqualified"
        )
        assert "the id its own launch returned" in normalized, (
            "the sanctioned retry must be a resume of the SAME instance by the id the caller's "
            "own launch returned - the only address it can hold"
        )
        assert "no recorded id, or it no longer resolves" in normalized, (
            "the Tier-C branch must name the decidable condition that selects it, not a probe "
            "on state this runtime never exposes"
        )

    def test_retry_ban_still_requires_the_first_instance_to_have_ended(self):
        """The superseding dispatch must be gated on the failed instance's turn having
        fully ended - never a second instance dispatched while the first might still be
        running (that would reopen the R2b race, not close the retry gap)."""
        normalized = _ws_normalize(self.skill_text)
        assert "fully ended" in normalized or "turn has fully ended" in normalized, (
            "SKILL.md must require the failed instance's turn to have fully ended before "
            "a superseding dispatch - never a second CONCURRENT instance"
        )


# ---------------------------------------------------------------------------
# General guard (C1 follow-up) - path-shape self-consistency across the WHOLE
# plugin tree, not just this skill's two files.
#
# The R-d/C1 defect (see `TestSharedCommitIntentWritePathPerModule` above) was
# a special case of a broader failure mode: the SAME logical on-disk artifact
# - identified by a literal directory-name segment (e.g. `intents`) sitting
# next to a single templated placeholder segment (e.g. `<module>`) in a
# backtick/code-block path fragment - was described with the two segments in
# OPPOSITE relative order in different places, and no existing test compared
# those places against each other (each existing test only ever pinned ONE
# file's ONE claim, e.g. `test_p3_route_out_carries_one_intent_record_per_module`
# read `fp-phase-detail.md` only and never opened `SKILL.md` for the same
# claim - so SKILL.md contradicting itself, and contradicting that other
# file, stayed green).
#
# This guard is a general detector for that failure MODE, not a restatement
# of the specific fix: it extracts every `<literal>/<placeholder>` or
# `<placeholder>/<literal>` adjacent segment pair from every path-shaped
# token in every *.md file under the WHOLE `plugins/` tree (all three
# plugins, no filename allowlist), groups occurrences by the unordered
# (literal, placeholder) pair, and fails if the SAME pair is ever seen in
# both relative orders anywhere in the tree.
#
# Scope and reasoning (what this DOES and does NOT catch):
#   - DOES catch: two-segment reorderings of the same named artifact, where
#     one segment is a bare lowercase directory literal (`intents`, `commits`,
#     `survey`, ...) and the other is a single bracketed placeholder
#     (`<module>`, `<sha>`, `<slug>`, ...), anywhere a path-shaped token
#     appears - an inline code span OR a line inside a fenced code block /
#     brief template. Token extraction is deliberately NOT anchored to
#     backtick-pair parsing: several of the real R-d occurrences (SKILL.md
#     line 924, fp-phase-detail.md lines 233 and 557) span a multi-line
#     inline backtick pair or sit inside a ``` brief template, both of which
#     a `` `([^`\n]+)` `` single-line backtick regex misses entirely - a raw
#     path-shaped-token scan catches all of them.
#   - Verified empirically against the actual tree: scanning all of
#     `plugins/` finds exactly ONE contradictory pair pre-fix (`intents`,
#     `<module>`) and ZERO post-fix, with zero unrelated contradictions
#     anywhere else among the 100+ distinct (literal, placeholder) pairs the
#     same scan observes tree-wide - so the detector is not noisy at this
#     repo's current size.
#   - Does NOT catch: a shape restated with THREE OR MORE segments changing
#     relative order (only adjacent 2-segment swaps are modeled); a
#     contradiction where neither side uses a bracketed placeholder (pure
#     prose, or two fully concrete examples); or a contradiction between a
#     placeholder-pair order and a fully SUBSTITUTED worked example (e.g.
#     `.../A/intents/<sha>.md`, where `A` stands in for `<module>`) - a bare
#     single-letter segment is intentionally NOT treated as a placeholder, so
#     a file could in principle state the placeholder form one way and a
#     worked-example form the opposite way without this guard firing. That
#     specific residual case does not arise anywhere in the current tree
#     (checked by hand for this fix - SKILL.md's own worked example at lines
#     306-309 agrees with fp-phase-detail.md's), but a future author should
#     not rely on this guard alone for that variant. This is a documented
#     blind spot, not something the guard silently claims to verify.
#   - Does NOT judge which of the two orders is "correct" - it only proves
#     that BOTH orders coexist, which is sufficient to prove a
#     self-contradiction. Deciding which order is right (and fixing the
#     wrong occurrences) is necessarily a human/reviewer judgment call, the
#     same way it was for R-d - encoding "always trust the majority order" or
#     any similar auto-resolution rule would be UNSOUND here: in the R-d
#     pre-fix tree the WRONG order was numerically the majority (6 backward
#     vs 2 correct), so a majority-vote heuristic would have picked the
#     wrong side as "canonical" and flagged the two correct lines instead.
#
# RED-before-green evidence (measured via `git show HEAD:<path>` for the two
# touched files, whole-tree scan otherwise, reconstructed for this comment by
# scanning the tree with SKILL.md/fp-phase-detail.md swapped back to their
# pre-fix `git show HEAD` content): pre-fix, exactly ONE contradictory pair -
# (`intents`, `<module>`) - with 6 occurrences in the `intents/<module>`
# order (SKILL.md lines 699, 703, 830, 917, 924; fp-phase-detail.md line 502)
# and 2 occurrences in the `<module>/intents` order (fp-phase-detail.md lines
# 233, 557); 0 contradictory pairs anywhere else in the tree. Post-fix (this
# change): 0 contradictory pairs, period.
# ---------------------------------------------------------------------------

from collections import defaultdict

ALL_PLUGINS_ROOT = REPO_ROOT / "plugins"

_LITERAL_SEG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_PLACEHOLDER_SEG_RE = re.compile(r"^<[a-zA-Z][a-zA-Z0-9_-]*>$")
# A path-shaped run of characters: letters/digits/underscore/hyphen/dot,
# `<...>` placeholders, and `${...}` root markers. Deliberately NOT anchored
# to backtick spans - see "DOES catch" above.
_PATH_TOKEN_RE = re.compile(r"[$\{\}A-Za-z0-9_.<>/-]+")


def _find_segment_order_contradictions(root):
    """Scan every *.md file under `root` for `<literal>/<placeholder>` (or the
    reverse) adjacent path segments, grouped by the unordered (literal,
    placeholder) pair. Returns {pair: {order: [(file, lineno, token), ...]}}
    restricted to pairs where BOTH orders were observed anywhere under root.
    """
    records = defaultdict(lambda: defaultdict(list))
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in _PATH_TOKEN_RE.finditer(line):
                token = m.group(0)
                if token.count("/") < 2 or "<" not in token:
                    continue
                segs = [s for s in token.split("/") if s]
                for i in range(len(segs) - 1):
                    a, b = segs[i], segs[i + 1]
                    if _LITERAL_SEG_RE.match(a) and _PLACEHOLDER_SEG_RE.match(b):
                        pair, order = (a, b), "literal_before_placeholder"
                    elif _PLACEHOLDER_SEG_RE.match(a) and _LITERAL_SEG_RE.match(b):
                        pair, order = (b, a), "placeholder_before_literal"
                    else:
                        continue
                    records[pair][order].append(
                        (str(path.relative_to(REPO_ROOT)), lineno, token)
                    )
    return {pair: dict(orders) for pair, orders in records.items() if len(orders) > 1}


class TestPathShapeSegmentOrderConsistency:
    """General guard for the R-d/C1 failure class: the same named artifact
    (a literal directory segment next to a single templated placeholder
    segment) must never be described with the two segments in opposite
    relative order anywhere across the WHOLE `plugins/` tree (all three
    plugins - no filename allowlist). See the comment block above this class
    for full scope, false-positive verification, and documented blind spots.
    """

    def test_no_directory_placeholder_pair_has_conflicting_segment_order(self):
        contradictions = _find_segment_order_contradictions(ALL_PLUGINS_ROOT)
        if not contradictions:
            return
        lines = []
        for pair, orders in sorted(contradictions.items()):
            literal, placeholder = pair
            lines.append(f"pair ({literal!r}, {placeholder!r}) has both orders:")
            for order, hits in sorted(orders.items()):
                for file, lineno, token in hits:
                    lines.append(f"    {order}: {file}:{lineno}  `{token}`")
        pytest.fail(
            "the same (literal-directory, placeholder) segment pair is described "
            "with the two segments in opposite order somewhere in the plugin tree "
            "- one of the two orders is wrong for every artifact this pair names; "
            "resolve which order is correct and make every occurrence agree:\n"
            + "\n".join(lines)
        )
