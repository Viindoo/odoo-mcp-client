"""Guard (NR2): the plan schema Block 2 REQUIRES a fenced ```text``` ASCII module-DAG
dependency-graph - not mermaid - with per-node wiring, and odoo-planner references it as REQUIRED.

Business rule: the plan odoo-planning emits (surfaced to the human in Plan Mode) must carry a
human-legible ASCII dependency-graph of the module-DAG so the human sees build order + per-node
execute-skill at a glance. Mermaid does not render in the plan file / terminal, so it is NOT used.
The graph is DERIVED from dag_layers / topological_order + Block 3 (never hand-drawn), and it is a
RENDERING of index.yaml dag_layers (extend, not fork).

These assert the CONTRACT (the schema requires the field + wiring), per ETHOS #8 - not a brittle
snapshot of the example graph.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"
PLANNER = PLUGIN / "agents" / "odoo-planner.md"


def _schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def _block2_spec() -> str:
    text = _schema()
    start = text.find("**REQUIRED - module-DAG ASCII dependency-graph block.**")
    assert start != -1, (
        "plan-mode-schema.md Block 2 must carry a '**REQUIRED - module-DAG ASCII dependency-graph "
        "block.**' spec."
    )
    end = text.find("**Block 3", start)
    return text[start: end if end != -1 else len(text)]


def _ascii_template() -> str:
    """The fenced ```text``` ASCII dep-graph example inside the schema."""
    m = re.search(r"```text\n(.*?)\n```", _schema(), re.DOTALL)
    assert m, "plan-mode-schema.md must contain a fenced ```text``` ASCII dependency-graph block."
    return m.group(1)


def test_block2_requires_fenced_text_ascii_graph_not_mermaid():
    spec = _block2_spec()
    assert "REQUIRED" in spec, "Block 2 dep-graph must be REQUIRED."
    assert "```text" in spec, "Block 2 must require a fenced ```text``` ASCII block."
    assert "NOT mermaid" in spec, (
        "Block 2 must state the graph is NOT mermaid (mermaid does not render in the plan file)."
    )
    # No lingering 'mermaid ... encouraged' in the schema.
    assert "mermaid diagram is encouraged" not in _schema().lower(), (
        "The old 'A mermaid diagram is encouraged' line must be gone from the schema."
    )


def test_block2_requires_per_node_wiring():
    spec = _block2_spec()
    assert "(NEW)" in spec and "(existing)" in spec, (
        "Each node must be marked (NEW)/(existing)."
    )
    assert "[skill:" in spec, "Each node must carry a [skill: <execute-skill>] tag."
    assert "Wave N" in spec or "Wave" in spec, "Nodes must be grouped under Wave N headers."
    assert "depends-on:" in spec and "-->" in spec, (
        "The depends direction must be shown per node (depends-on:) AND as a flat edge list (X --> Y)."
    )


def test_block2_states_data_source_derivation():
    spec = _block2_spec().lower()
    assert "derived" in spec, "Block 2 must state the graph is DERIVED (never hand-drawn)."
    assert "dag_layers" in spec, "Derivation must cite the design dag_layers."
    assert "topological_order" in spec, "Derivation must cite topological_order (few-WI path)."
    assert "block 3" in spec, "Derivation must cite the Block 3 assignment for the [skill:] tags."


def test_block2_master_child_reconciliation_clause_present():
    spec = _block2_spec()
    assert "master-child-design-contract.md" in spec or "index.yaml" in spec, (
        "Block 2 must carry the reconciliation clause: the dep-graph is a RENDERING of index.yaml "
        "dag_layers (extend, not fork - no second DAG schema)."
    )
    low = spec.lower()
    assert "not fork" in low or "second dag" in low or "no field" in low, (
        "The reconciliation clause must say it adds no field / does not fork the DAG."
    )


def test_ascii_template_has_no_box_drawing_unicode():
    template = _ascii_template()
    for ch in template:
        assert ord(ch) < 128, (
            f"The ASCII dep-graph template must be ASCII-only (ETHOS rule 0); found U+{ord(ch):04X} "
            f"({ch!r})."
        )


def test_planner_references_dep_graph_as_required_not_encouraged():
    text = PLANNER.read_text(encoding="utf-8")
    assert "encouraged" not in text.lower(), (
        "odoo-planner.md must no longer say the dep-graph/mermaid is 'encouraged' - it is REQUIRED."
    )
    assert "REQUIRED" in text and "ASCII dependency-graph" in text, (
        "odoo-planner.md Round 3 must reference the module-DAG ASCII dependency-graph as REQUIRED."
    )
    assert "plan-mode-schema.md" in text, (
        "odoo-planner.md must point at plan-mode-schema.md Block 2 for the dep-graph spec."
    )
