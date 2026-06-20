"""Invariant tests for forward-port hardening (#90).

Each test pins a specific behavioral contract introduced or fixed in the
#90 / #76 wave.  Tests are named after the RULE they enforce, not the
implementation detail they happen to read.  Every assertion is chosen so
it would be RED if the corresponding WI change were absent.

Files under test (all under plugins/odoo-ai-agents/):
  - skills/odoo-forward-port/SKILL.md                (WI-3)
  - skills/odoo-forward-port/references/fp-phase-detail.md  (WI-4)
  - snippets/fp-symbol-survival-check.md              (WI-1)
  - snippets/fp-installable-false.md                  (WI-5)
  - skills/odoo-forward-port/references/fp-triage-table.md  (WI-5)
  - skills/_shared/debug-method.md                    (WI-6)
  - agents/odoo-backend-debugger.md                   (WI-6)
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
    """SKILL.md must not instruct a destructive fresh-DB .po re-export and
    must route i18n work to the odoo-i18n skill."""

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

    def test_destructive_overwrite_warning_present(self):
        """SKILL.md must warn that overwriting .po from a fresh DB destroys translations."""
        # The plan mandates: 'NEVER re-export a .po from a fresh DB and overwrite'
        assert "fresh DB" in self.text, (
            "SKILL.md must warn about fresh-DB export data loss"
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


# ---------------------------------------------------------------------------
# Invariant 3 - MED-6: both debug-method.md and odoo-backend-debugger.md
# contain the '0 failed, N error(s)' rule markers.
# ---------------------------------------------------------------------------

class TestMED6DebuggerRule:
    """Both the shared debug method doc and the debugger agent must teach the
    MED-6 rule: N error(s) from setUpClass means tests DID NOT RUN."""

    @pytest.mark.parametrize("path,label", [
        (DEBUG_METHOD, "debug-method.md"),
        (BACKEND_DEBUGGER, "odoo-backend-debugger.md"),
    ])
    def test_error_count_not_pass_rule_present(self, path, label):
        """'error(s)' + 'setUpClass' must both appear (the MED-6 rule)."""
        text = path.read_text(encoding="utf-8")
        assert "error(s)" in text, (
            f"{label}: missing 'error(s)' marker for MED-6 rule"
        )
        assert "setUpClass" in text, (
            f"{label}: missing 'setUpClass' marker for MED-6 rule"
        )

    @pytest.mark.parametrize("path,label", [
        (DEBUG_METHOD, "debug-method.md"),
        (BACKEND_DEBUGGER, "odoo-backend-debugger.md"),
    ])
    def test_did_not_run_or_transient_warning_present(self, path, label):
        """The doc must warn that errors mean tests DID NOT RUN."""
        text = path.read_text(encoding="utf-8")
        assert ("DID NOT RUN" in text or "transient" in text), (
            f"{label}: missing 'DID NOT RUN' / 'transient' warning for MED-6"
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


# ---------------------------------------------------------------------------
# Invariant 5 - NEW-1 lint-only lane: fp-installable-false.md contains the
# lint-only lane markers; fp-triage-table.md has the short-circuit gate for
# installable:False.
# ---------------------------------------------------------------------------

class TestNew1LintOnlyLane:
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
