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
  - skills/odoo-forward-port/references/fp-triage-table.md
  - skills/_shared/debug-method.md
  - agents/odoo-backend-debugger.md
"""

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
# Invariant 4 - P5 isolation flags: fp-phase-detail.md must contain both
# --skip-auto-install and --http-port flags in the P5 verify section.
# ---------------------------------------------------------------------------

class TestP5IsolationFlags:
    """fp-phase-detail.md P5 section must instruct use of --skip-auto-install
    and --http-port to isolate auto_install modules and avoid port collisions."""

    def setup_method(self):
        self.text = PHASE_DETAIL.read_text(encoding="utf-8")

    def test_skip_auto_install_present(self):
        """P5 must include --skip-auto-install flag."""
        assert "--skip-auto-install" in self.text, (
            "fp-phase-detail.md missing --skip-auto-install in P5 verify section"
        )

    def test_http_port_present(self):
        """P5 must include --http-port flag for port isolation."""
        assert "--http-port" in self.text, (
            "fp-phase-detail.md missing --http-port in P5 verify section"
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
