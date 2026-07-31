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
