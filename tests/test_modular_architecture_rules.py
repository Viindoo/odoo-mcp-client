"""The modular-architecture rules the plugin prose must keep: each rule is pinned by one short
distinctive phrase in the file that carries it."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
CONTRACT = "snippets/modularity-contract.md"
PRINCIPLES = "snippets/odoo-platform-design-principles.md"


def _read(rel):
    """The file with its line wraps folded, so a rule split over two lines still reads as one."""
    return re.sub(r"\s+", " ", (PLUGIN / rel).read_text(encoding="utf-8"))


def _between(rel, start, end):
    text = _read(rel)
    assert start in text, f"{rel}: no {start!r}"
    tail = text.split(start, 1)[1]
    assert end in tail, f"{rel}: no {end!r} after {start!r}"
    return tail.split(end, 1)[0]


def test_cross_module_behaviour_lives_in_an_auto_install_bridge_module():
    section = _between(CONTRACT, "## Where cross-module behaviour lives", "## The check")
    assert "bridge module" in section and "auto_install" in section
    assert "§ Where cross-module behaviour lives" in _read(CONTRACT).split("## Design", 1)[1]


def test_the_install_set_is_read_from_the_build_log_not_inferred_from_a_manifest():
    tests = _between(CONTRACT, "## Tests", "## Acceptance")
    assert "read from the build log" in tests and "auto_install" in tests
    assert "read from the build log" in _read("snippets/test-scope-contract.md")


def test_a_test_never_depends_on_the_absence_of_a_module_outside_its_closure():
    tests = _between(CONTRACT, "## Tests", "## Acceptance")
    assert "absence of a module outside its closure" in tests.lower()
    assert "overrides of that method" in tests
    assert "absence of a module outside its closure" in _read("snippets/test-sensitivity-contract.md")


def test_auto_install_fires_on_install_only_so_update_never_adds_the_bridge():
    assert "fires on install only" in _read("docs/reference/INSTANCE-LIFECYCLE.md")
    assert "| Bridge module absent after `-u` |" in (
        PLUGIN / "skills/_shared/odoo-failure-modes.md"
    ).read_text(encoding="utf-8")


def test_a_value_set_by_law_is_a_data_record_never_a_formula_string():
    section = _between(PRINCIPLES, "## 2.", "## 3.")
    assert "set by law or regulation" in section and "data record" in section
    assert "formula string" in _between("agents/odoo-code-reviewer.md", "## MODE R1", "## MODE R2")


def test_a_generic_accounting_module_runs_on_the_generic_chart_of_account():
    assert "generic chart of `account`" in _between(PRINCIPLES, "## 2.", "## 3.")


def test_a_business_module_paints_only_with_core_levers():
    section = _between("skills/_shared/odoo-frontend-fidelity.md", "### A.", "### B.")
    rule6 = section.split("6. ", 1)[1]
    assert "core levers" in rule6 and "bg-white" in rule6
    step = _between("agents/odoo-ui-reviewer.md", "### Step 4b", "### Step 5")
    assert "theme-fixed Bootstrap class" in step


def test_dependents_are_computed_to_a_fixed_point_and_retirement_is_marked_under_the_name_key():
    graph = _read("skills/_shared/odoo-module-graph.md")
    assert "## Reverse closure" in graph
    assert "fixed point" in _between("skills/_shared/odoo-module-graph.md", "## Reverse closure", "## How `odoo-coding`")
    assert "under the `name` key" in _read(PRINCIPLES).split("## 5.", 1)[1]


def test_the_closure_only_install_set_claim_is_gone():
    assert "contains ONLY the module and its upstream closure" not in _read(CONTRACT)
