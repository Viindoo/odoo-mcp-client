"""Guard: the Q2 migration carve-out states all THREE predicate conditions ONCE, and
odoo-solution-design points at it (it does not restate a silent migration bypass).

Business rule (Q2, GATED): a lone design_doc satisfies the mandatory-plan gate ONLY when the
design is (1) a data/schema migration script, AND (2) touches exactly ONE module, AND (3) has no
multi-layer dag_layers. Any richer (multi-module OR multi-layer) design fails the carve-out and
HARD BLOCKS to odoo-planning. The carve-out is declared once in planning-gate-contract.md.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
GATE = PLUGIN / "snippets" / "planning-gate-contract.md"
DESIGN = PLUGIN / "skills" / "odoo-solution-design" / "SKILL.md"


def _carveout_section() -> str:
    text = GATE.read_text(encoding="utf-8")
    start = text.find("## Migration carve-out")
    assert start != -1, "planning-gate-contract.md must own a '## Migration carve-out' section."
    end = text.find("\n## ", start + 1)
    return text[start: end if end != -1 else len(text)]


def test_carveout_states_all_three_conditions():
    sec = _carveout_section().lower()
    assert "migration script" in sec, "Condition 1: the design must be a migration script."
    assert "exactly one" in sec and "module" in sec, "Condition 2: exactly ONE module."
    assert "dag_layers" in sec and ("single layer" in sec or "no multi-layer" in sec), (
        "Condition 3: no multi-layer dag_layers (single layer)."
    )


def test_carveout_richer_designs_route_to_planning_at_the_door():
    """Reframed: the carve-out is a FRONT-DOOR routing decision by odoo-solution-design. A richer
    design FAILS the carve-out and odoo-solution-design routes it to odoo-planning INSTEAD (no
    executor self-gate / re-validation on arrival)."""
    sec = _carveout_section().lower()
    assert "fails the carve-out" in sec, (
        "The carve-out must state that a richer (multi-module/multi-layer) design FAILS it."
    )
    assert "multi-module" in sec or "richer" in sec, (
        "The carve-out must name the failing case (multi-module / multi-layer / richer design)."
    )
    assert "odoo-planning" in sec, (
        "A richer design must be ROUTED to odoo-planning at the door (the bypass is denied)."
    )
    # The routing is decided by the front door; no executor re-validates on arrival.
    assert "odoo-solution-design" in sec and "re-validate" in sec, (
        "The carve-out must be owned by odoo-solution-design (front-door routing), with no executor "
        "re-validating the carve-out on arrival."
    )
    # The old executor self-gate framing must be gone.
    assert "executor self-gate" not in sec, (
        "The 'Executor self-gate' sentence (naming odoo-coding/odoo-data-migration as co-owners of "
        "the gate) must be excised - it was drift."
    )


def test_solution_design_points_at_carveout_not_a_silent_bypass():
    text = DESIGN.read_text(encoding="utf-8")
    assert "planning-gate-contract.md" in text and "Migration carve-out" in text, (
        "odoo-solution-design must point at planning-gate-contract.md § Migration carve-out."
    )
    # The old silent bypass phrasing must be gone.
    assert "routes straight to `odoo-data-migration` / `odoo-coding`" not in text, (
        "The old silent 'migration routes straight to odoo-data-migration/odoo-coding' bypass "
        "must be replaced by the carve-out pointer."
    )


def test_carveout_is_declared_once():
    """Exactly one file owns a '## Migration carve-out' section - the SSOT."""
    owners = []
    for p in PLUGIN.rglob("*.md"):
        if "## Migration carve-out" in p.read_text(encoding="utf-8"):
            owners.append(str(p.relative_to(PLUGIN)))
    assert owners == ["snippets/planning-gate-contract.md"], (
        f"The Migration carve-out section must be owned by exactly one file; found: {owners}"
    )
