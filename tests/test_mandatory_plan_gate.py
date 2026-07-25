"""Guard: the mandatory-planning gate lives at the FRONT DOORS (admission), NOT inside executors.

Governance rule (SDLC stage-gate): quality/stage-gate belongs at ADMISSION - the front door that
admits a request into the pipeline checks ONCE that an approved plan exists before it dispatches an
executor for non-trivial code-writing work. Executors/stages TRUST that upstream governance
happened; they never self-block for "no plan". This keeps tools composable and removes the runtime
contradictions of a self-gate.

This test asserts two behaviors:
  (a) FRONT DOORS enforce the gate - odoo-intake, odoo-brl, and the odoo-implement-feature workflow
      route non-trivial code-writing work through odoo-planning BEFORE dispatching any executor, and
      never route straight to a coder.
  (b) EXECUTOR SILENCE - odoo-coding no longer carries a "mandatory-plan self-gate" / "HARD BLOCK
      (no plan)", and odoo-module-graph.md no longer HARD-BLOCKs a bare standalone self-derive; the
      standalone self-derive is a normal path.

Legit non-admission paths are acknowledged so the test does not over-assert: the autonomous-fix
loop sentinel stays in odoo-coding, and executors may still CITE the gate contract (for the
plan-provided fast-path) - citing the SSOT is not a self-gate.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

CODING = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
MODULE_GRAPH = PLUGIN / "skills" / "_shared" / "odoo-module-graph.md"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"
BRL = PLUGIN / "skills" / "odoo-brl" / "SKILL.md"
WORKFLOW = PLUGIN / "workflows" / "odoo-implement-feature.workflow.yaml"
GATE = PLUGIN / "snippets" / "planning-gate-contract.md"
PLANNING = PLUGIN / "skills" / "odoo-planning" / "SKILL.md"


# --------------------------------------------------------------------------- #
# (a) FRONT DOORS enforce the admission gate                                   #
# --------------------------------------------------------------------------- #

def test_gate_contract_names_the_front_door_as_the_actor():
    """The SSOT rule's SUBJECT is the front door establishing a plan before dispatch - not an
    executor self-checking."""
    text = GATE.read_text(encoding="utf-8")
    low = text.lower()
    assert "## mandatory-planning rule" in low
    # The front door is named as the actor that establishes the plan / admits work.
    assert "front door" in low, "The rule must name the FRONT DOOR as the actor of the gate."
    assert "admission" in low, "The rule must frame planning as enforced at ADMISSION."
    # The resulting invariant is still stated (guaranteed BY the front door, not self-checked).
    assert "no executor" in low and "approved plan artifact" in low, (
        "The invariant (no executor writes code without an approved plan artifact in scope) must "
        "survive as a consequence of the front-door admission decision."
    )
    # Executors TRUST upstream governance rather than re-checking.
    assert "trust" in low, "The rule must say executors TRUST upstream governance (no self-gate)."


def test_intake_is_the_admission_gate_and_routes_through_planning():
    text = INTAKE.read_text(encoding="utf-8")
    low = text.lower()
    # Intake routes non-trivial coding through the design->plan chain, planning mandatory for all.
    assert "planning is mandatory for all work" in low, (
        "intake must state planning is mandatory for all work (the :342 no-bypass rule)."
    )
    assert "odoo-solution-design → odoo-planning → odoo-coding" in text or (
        "odoo-solution-design" in text and "odoo-planning" in text
    ), "intake must route non-trivial work through solution-design -> odoo-planning before coding."
    # Intake owns the admission gate and dispatches an executor only after a plan is established.
    assert "admission gate" in low, (
        "intake must claim ownership of the admission gate (establishes plan before dispatch)."
    )
    # Intake ALWAYS delegates 3-block authoring to odoo-planning (never inline / never raw coder).
    assert "delegate 3-block authoring to `odoo-planning`" in text, (
        "intake must delegate plan authoring to odoo-planning, not dispatch a raw coder."
    )


def test_brl_never_routes_straight_to_coding():
    import re

    text = BRL.read_text(encoding="utf-8")
    low = text.lower()
    norm = re.sub(r"\s+", " ", low)  # tolerate prose line-wrapping
    assert "next: odoo-planning" in low, "brl must route its classified items to odoo-planning."
    assert "instead of `odoo-coding` directly" in norm, (
        "brl must route Standard/Config items to odoo-planning INSTEAD of odoo-coding directly."
    )
    assert "front-door admission gate" in norm, (
        "brl must claim it is a front-door admission gate that never hands work straight to an "
        "executor."
    )
    assert "never hands a requirement straight to an executor" in norm, (
        "brl must state it never hands a requirement straight to an executor."
    )


def test_workflow_both_branches_terminate_at_planning():
    text = WORKFLOW.read_text(encoding="utf-8")
    low = text.lower()
    # Trivial branch goes directly to odoo-planning; non-trivial goes via solution-design which
    # emits next: odoo-planning. The comment asserts BOTH branches route through odoo-planning.
    assert "next: odoo-planning" in low, "The trivial branch must terminate at odoo-planning."
    assert "next: odoo-solution-design" in low, (
        "The non-trivial branch must go through odoo-solution-design (which chains to odoo-planning)."
    )
    assert "both branches route through" in low, (
        "The workflow comment must state BOTH branches route through odoo-planning."
    )
    assert "no trivial direct-to-coding bypass" in low, (
        "The workflow must state there is no trivial direct-to-coding bypass."
    )
    # The workflow is the front-door admission gate.
    assert "front-door admission gate" in low, (
        "The workflow must claim it is a front-door admission gate (no executor before planning)."
    )


# --------------------------------------------------------------------------- #
# (b) EXECUTOR SILENCE - no self-gate inside the executors                     #
# --------------------------------------------------------------------------- #

def test_coding_has_no_mandatory_plan_self_gate():
    low = CODING.read_text(encoding="utf-8").lower()
    assert "mandatory-plan self-gate" not in low, (
        "odoo-coding must NOT carry a 'mandatory-plan self-gate' - the gate is at the front door."
    )
    assert "hard block" not in low, (
        "odoo-coding must NOT HARD BLOCK a no-plan invocation - it self-derives and proceeds."
    )
    # The standalone path is explicitly a self-derive, not a block.
    assert "self-derive" in low, (
        "odoo-coding must state that a bare standalone invocation self-derives and proceeds."
    )
    # It still identifies itself as a pipeline stage whose gate is upstream.
    assert "pipeline stage" in low and "front door" in low, (
        "odoo-coding must state it is a pipeline stage whose planning gate is enforced upstream at "
        "the front door."
    )


def test_coding_still_cites_the_gate_contract_for_the_fast_path():
    """Citing the SSOT (for the plan-provided fast-path) is allowed - it is a pointer, not a
    self-gate."""
    text = CODING.read_text(encoding="utf-8")
    assert "snippets/planning-gate-contract.md" in text, (
        "odoo-coding may still cite the gate contract SSOT (fast-path / upstream-gate pointer)."
    )


def test_coding_autonomous_fix_exception_preserved():
    """The bounded autonomous-fix loop is a legit non-admission path (human already triggered the
    front door) and must survive the self-gate removal."""
    text = CODING.read_text(encoding="utf-8")
    assert "AUTONOMOUS FIX (review-driven)" in text and "AUTONOMOUS FIX (debug-driven)" in text, (
        "The autonomous-fix sentinel handling must remain intact."
    )


def test_planning_owns_the_only_enter_exit_pair():
    """P3: odoo-planning is the SOLE enterer/exiter of Plan Mode for the lifecycle plan - front
    doors (odoo-intake) never call EnterPlanMode/ExitPlanMode themselves, they only dispatch
    odoo-planning, which owns both calls internally (after its planners return, before/at the
    approval gate)."""
    planning = PLANNING.read_text(encoding="utf-8")
    assert "EnterPlanMode" in planning and "ExitPlanMode" in planning, (
        "odoo-planning/SKILL.md must itself call both EnterPlanMode and ExitPlanMode - it is the "
        "sole enterer/exiter of the lifecycle plan's Plan Mode window."
    )

    intake = INTAKE.read_text(encoding="utf-8")
    ilow = " ".join(intake.lower().split())
    assert "intake never does" in ilow, (
        "odoo-intake/SKILL.md must state it enters Plan Mode on NO path - odoo-planning is the "
        "sole enterer."
    )
    assert "main agent calls **`enterplanmode`**" not in ilow, (
        "odoo-intake/SKILL.md must not instruct the main agent to call EnterPlanMode itself."
    )


def test_module_graph_standalone_self_derive_is_normal_not_blocked():
    low = MODULE_GRAPH.read_text(encoding="utf-8").lower()
    assert "hard block" not in low, (
        "odoo-module-graph.md must NOT HARD BLOCK a bare standalone self-derive - it is a normal "
        "path."
    )
    assert "normal path" in low, (
        "odoo-module-graph.md must frame the standalone self-derive as a NORMAL path."
    )
    # The new-module third case is preserved and its unresolved-edge case is a correctness
    # safeguard (graceful BLOCKED via the coder's dependency pre-flight), NOT an admission gate.
    assert "dependency pre-flight" in low and "correctness safeguard" in low, (
        "The unresolved-new-module edge must surface as a graceful BLOCKED via the coder's "
        "dependency pre-flight - a correctness safeguard, not a planning-admission gate."
    )
