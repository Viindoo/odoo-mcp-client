"""Guard: the mandatory-planning SSOT is stated ONCE and every other site is a pointer.

Business rule this protects (Q1, FINAL): planning is MANDATORY for ALL work that writes
code - no executor writes code without an approved plan artifact in scope, and there is NO
trivial/size/module-count bypass and no `inline-plan-eligible` fast-path predicate. The rule,
the `plan_mode_active` definition, and the 3-block plan schema each live in exactly ONE
authoritative place (their SSOT); consumer files point at them rather than restating them.

These are CONTRACT checks (does the SSOT exist + do consumers point at it), not string-count
snapshots - prose may drift as long as the single-source-of-truth invariant holds.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

GATE = PLUGIN / "snippets" / "planning-gate-contract.md"
SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"
CODING = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
PLANNING = PLUGIN / "skills" / "odoo-planning" / "SKILL.md"

# The three self-driving front-door orchestrators (Option B GATE-ONLY): they REUSE the shared
# Plan-Mode mechanics rather than defining their own.
FORWARD_PORT = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
GIT_REBASE = PLUGIN / "skills" / "odoo-git-rebase" / "SKILL.md"
MODULES_UPGRADE = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"

POINTER = "snippets/planning-gate-contract.md"


def _tree_texts():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py)."""
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


def test_gate_contract_exists_and_declares_the_rule_once():
    assert GATE.exists(), "snippets/planning-gate-contract.md (the mandatory-planning SSOT) is missing."
    text = GATE.read_text(encoding="utf-8")
    assert "## Mandatory-planning rule" in text, (
        "planning-gate-contract.md must own a '## Mandatory-planning rule' section (the Q1 SSOT)."
    )
    low = text.lower()
    assert "no executor" in low and "approved plan artifact" in low, (
        "The Mandatory-planning rule must state that no executor writes code without an approved "
        "plan artifact in scope."
    )
    assert "hard block" in low, "The rule must HARD BLOCK a bare standalone invocation."
    # The three approved-plan-artifact signals are named ONCE in the detection section.
    assert "## Approved-plan-artifact detection" in text
    for signal in ("run-<id>", "WORKTREE_PATH", "inputs"):
        assert signal in text, f"The detection section must name the {signal!r} signal."


def test_no_inline_plan_eligible_or_trivial_bypass_survives_anywhere():
    """Q1 deleted the `inline-plan-eligible` predicate - it must appear NOWHERE, and the intake
    trivial-bypass 'skips design and routes straight to odoo-coding' sentence must be gone."""
    offenders = [str(p.relative_to(PLUGIN)) for p, t in _tree_texts() if "inline-plan-eligible" in t]
    assert not offenders, (
        f"`inline-plan-eligible` predicate must be deleted everywhere (Q1); still present in: {offenders}"
    )
    intake = INTAKE.read_text(encoding="utf-8")
    assert "skips design and routes straight to `odoo-coding`" not in intake, (
        "intake's trivial-bypass sentence ('skips design and routes straight to odoo-coding') must "
        "be excised - planning is mandatory for all work."
    )


def test_plan_mode_active_defined_once_in_gate_contract():
    """The `plan_mode_active` boolean definition is SSOT in planning-gate-contract.md; every other
    site (odoo-planning, workflow-harness, intake) is a pointer/usage, not a 2nd definition."""
    gate = GATE.read_text(encoding="utf-8")
    assert "boolean dispatch-brief flag" in gate, (
        "planning-gate-contract.md must carry the authoritative `plan_mode_active` definition."
    )
    definers = [
        str(p.relative_to(PLUGIN)) for p, t in _tree_texts() if "boolean dispatch-brief flag" in t
    ]
    assert definers == ["snippets/planning-gate-contract.md"], (
        f"The `plan_mode_active` definition must exist in exactly ONE place; found in: {definers}"
    )
    # odoo-planning must POINT at the SSOT, not re-define it.
    assert POINTER in PLANNING.read_text(encoding="utf-8"), (
        "odoo-planning/SKILL.md must reference planning-gate-contract.md for the plan_mode_active "
        "definition instead of restating it."
    )


def test_plan_schema_is_ssot_owned_by_planning_and_not_relocated():
    assert SCHEMA.exists(), "plan-mode-schema.md must remain at skills/odoo-intake/references/ (no relocate)."
    head = SCHEMA.read_text(encoding="utf-8")[:600]
    assert "SSOT owned by `odoo-planning`" in head, (
        "plan-mode-schema.md header must state it is the SSOT owned by odoo-planning."
    )


def test_intake_decision_tree_exemption_names_design_and_planning():
    """intake:134 'Does NOT apply' exemption list must include odoo-solution-design AND
    odoo-planning (they write only under the $ODOO_AI_HOME state root; odoo-planning owns its
    own Plan Mode)."""
    text = INTAKE.read_text(encoding="utf-8")
    idx = text.find("**Does NOT apply**")
    assert idx != -1, "intake must have a '**Does NOT apply**' Plan-Mode exemption clause."
    clause = text[idx: idx + 700]
    assert "odoo-solution-design" in clause and "odoo-planning" in clause, (
        "The Plan-Mode exemption list must name both odoo-solution-design and odoo-planning."
    )


def test_coding_points_at_gate_contract_not_its_own_rule():
    assert POINTER in CODING.read_text(encoding="utf-8"), (
        "odoo-coding/SKILL.md must cite planning-gate-contract.md (the mandatory-plan SSOT), "
        "not re-author its own mandatory-planning rule."
    )


def test_specialist_orchestrators_point_at_gate_contract_not_restate_plan_mode_active():
    """Option B (GATE-ONLY): the three self-driving front doors - odoo-forward-port,
    odoo-git-rebase, odoo-modules-upgrade - must REUSE the shared Plan-Mode gate by POINTING at
    planning-gate-contract.md for the enter/exit + plan_mode_active mechanics, and must NOT restate
    the `plan_mode_active` definition (its SSOT is the gate contract). Their specialized plan
    CONTENT stays authored in-skill. Parity with test_coding_points_at_gate_contract_not_its_own_rule
    - would go RED if any of the three re-authored the bespoke plan-mode mechanics instead of
    pointing at the SSOT.
    """
    for skill in (FORWARD_PORT, GIT_REBASE, MODULES_UPGRADE):
        text = skill.read_text(encoding="utf-8")
        rel = str(skill.relative_to(PLUGIN))
        assert POINTER in text, (
            f"{rel} must reference planning-gate-contract.md (reuse the shared Plan-Mode gate) "
            "instead of defining its own plan-mode mechanics."
        )
        assert "boolean dispatch-brief flag" not in text, (
            f"{rel} must NOT restate the plan_mode_active definition - that SSOT lives only in "
            "planning-gate-contract.md; point at it."
        )


def test_enter_precedes_authoring_invariant():
    """P4 (plan mode ownership + timing), AMENDED by P3: `EnterPlanMode` is called before the
    first GIT-TRACKED or otherwise irreversible effect, and ALWAYS before presenting the plan -
    NOT necessarily before the planners' own state-root-only authoring. odoo-planning's guard now
    sits AFTER both planner dispatches (P1a/P1b) and BEFORE the approval gate: the planners write
    ONLY under the `$ODOO_AI_HOME` state root, which Plan Mode does not gate, so entering earlier
    bought nothing but extra prompting (the over-prompting bug P3 fixes). odoo-intake (which
    enters Plan Mode on NO path) still complies in its own prose. Root cause this guards:
    odoo-planning used to enter BEFORE dispatching its planners while they wrote only
    state-root plan files - triggering Plan Mode for a non-git-tracked write - and odoo-intake
    pre-opened Plan Mode on the author's behalf; both stay excised."""
    gate = GATE.read_text(encoding="utf-8")
    low = " ".join(gate.lower().split())  # normalize whitespace - prose line-wraps
    assert "enter before the first git-tracked" in low, (
        "planning-gate-contract.md must state the amended WHEN invariant: EnterPlanMode is "
        "called before the first GIT-TRACKED or otherwise irreversible effect."
    )
    assert "always before presenting" in low, (
        "planning-gate-contract.md must state EnterPlanMode is ALWAYS called before presenting "
        "the plan for approval."
    )
    assert "does not require an open plan mode window" in low, (
        "planning-gate-contract.md must state that state-root-only plan authoring does NOT "
        "require an open Plan Mode window."
    )
    assert "exactly one actor calls it" in low, (
        "planning-gate-contract.md must pin exactly ONE actor as the enterer for a given plan."
    )
    assert "pre-open plan mode on behalf of the plan author" in low, (
        "planning-gate-contract.md must forbid a caller from pre-opening Plan Mode on the "
        "author's behalf and then dispatching it."
    )

    planning = PLANNING.read_text(encoding="utf-8")
    guard_idx = planning.find("Plan Mode guard")
    p1a_idx = planning.find("### P1a - Code plan")
    p1b_idx = planning.find("### P1b - Doc plan")
    gate_idx = planning.find("## Plan-approval gate")
    assert -1 not in (guard_idx, p1a_idx, p1b_idx, gate_idx), (
        "odoo-planning/SKILL.md must carry a 'Plan Mode guard' section, both P1a/P1b planner "
        "dispatch sections, and the 'Plan-approval gate' section."
    )
    assert guard_idx > p1a_idx and guard_idx > p1b_idx, (
        "odoo-planning's Plan Mode guard must sit AFTER BOTH planner dispatches (P1a and P1b) - "
        "state-root plan authoring does not require an open Plan Mode window, so the enter no "
        "longer precedes it."
    )
    assert guard_idx < gate_idx, (
        "odoo-planning's Plan Mode guard must sit BEFORE the approval gate - ExitPlanMode stays "
        "there, and the guard's ENTER must still precede presenting the plan for approval."
    )

    intake = INTAKE.read_text(encoding="utf-8")
    ilow = " ".join(intake.lower().split())
    assert "intake never does" in ilow, (
        "odoo-intake/SKILL.md must state that it enters Plan Mode on NO path - the plan-authoring "
        "skill (odoo-planning) is the sole enterer, never intake."
    )
    assert "main agent calls **`enterplanmode`**" not in ilow, (
        "odoo-intake/SKILL.md must NOT instruct the main agent to call EnterPlanMode directly - "
        "that call belongs solely to the plan-authoring skill it dispatches."
    )


PHASE_P_RUN_DAG = PLUGIN / "skills" / "odoo-intake" / "references" / "phase-p-run-dag.md"


def test_no_caller_pre_opens_plan_mode():
    """P3 item 28: NO intake-side REFERENCE/procedure file may pass `plan_mode_active: true` to
    odoo-planning on a dispatch - that would pre-open Plan Mode on the author's behalf and
    silently defeat its own guard (odoo-planning reads the flag and skips its own EnterPlanMode).
    Verified bug this guards: phase-p-run-dag.md's trivial single-module path used to pass
    `plan_mode_active: true` on its Skill-tool dispatch. `odoo-intake/SKILL.md` itself is exempt
    from the blanket scan below - it legitimately DOCUMENTS the ban in negated prose ('never
    passes `plan_mode_active: true`'), which is not a dispatch; every OTHER file under
    skills/odoo-intake/ (its references/) must not contain the literal token at all."""
    offenders = [
        str(p.relative_to(PLUGIN))
        for p, t in _tree_texts()
        if str(p.relative_to(PLUGIN)).startswith("skills/odoo-intake/")
        and str(p.relative_to(PLUGIN)) != "skills/odoo-intake/SKILL.md"
        and "plan_mode_active: true" in t
    ]
    assert not offenders, (
        f"No file under skills/odoo-intake/ (other than SKILL.md's own rule-documenting prose) "
        f"may pass `plan_mode_active: true` to odoo-planning - found in: {offenders}"
    )
    assert "plan_mode_active: true" not in PHASE_P_RUN_DAG.read_text(encoding="utf-8"), (
        "phase-p-run-dag.md must not pre-open Plan Mode on odoo-planning's behalf via "
        "`plan_mode_active: true` - it is the sole enterer of its own Plan Mode window."
    )
