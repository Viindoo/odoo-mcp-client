"""Guard: per-module acceptance criteria (TDD §9) and test scenarios (TDD §7) are cleanly
owned at DESIGN time, and the planner no longer overclaims the independent QA oracle as a
planning-time input.

Business rules this protects:

1. TDD §9 Acceptance Criteria is MANDATORY at module granularity - one AC block per row of
   §1's per-module table - so a design covering N modules cannot ship with fewer than N
   module-level AC blocks (the prior wording only REQUIRED "two levels" with no per-module
   floor, so a multi-module design could satisfy the letter of the rule with a single
   module-level block and a solution-level summary).
2. Every §9 `expected` value MUST be requirement-derived (hand-computed), NEVER phrased from
   an OSM/code finding - the INDEPENDENCE GUARD - so the downstream independent QA oracle
   (odoo-qa-planner) that may consume §9 stays bias-free, mirroring odoo-qa-planner's own
   code-read ban.
3. TDD §7's scenario table must be PARTITIONED PER MODULE even in single-mode multi-module
   TDDs (master-child mode already gets this for free because each child TDD is scoped to
   one module) - so a single-mode multi-module design cannot pool all modules' behaviors into
   one flat, module-ambiguous table.
4. odoo-planner (agent) and odoo-planning (skill) must NOT claim the independent QA oracle
   (`odoo-qa-planner`'s `scenarios.md`) as a standard/assumed planning-time input - it is
   authored LATER at odoo-acceptance Phase 1, after coding. At planning time the plan only
   RESERVES the acceptance stage against the design's §9 Acceptance Criteria (which DO exist
   at planning) and wires in the real oracle only when/if one is already present.
5. Consuming `DESIGN_DOC` §9 as a source of `expected` does NOT violate oracle independence
   (the ban is on reading the IMPLEMENTATION/code, not a requirement-derived design doc) - this
   must be stated explicitly in both the acceptance-oracle-contract SSOT and odoo-qa-planner,
   cross-referencing the §9 INDEPENDENCE GUARD.

Red-before-green: each assertion fails if the corresponding wording/rule regresses (e.g. the
old "Required at TWO levels" phrasing returns, or QA_ORACLE is re-treated as a standard input).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

ARCHITECT = PLUGIN / "agents" / "odoo-solution-architect.md"
SOLUTION_DESIGN_SKILL = PLUGIN / "skills" / "odoo-solution-design" / "SKILL.md"
PLANNER = PLUGIN / "agents" / "odoo-planner.md"
PLANNING_SKILL = PLUGIN / "skills" / "odoo-planning" / "SKILL.md"
ORACLE_CONTRACT = PLUGIN / "snippets" / "acceptance-oracle-contract.md"
QA_PLANNER = PLUGIN / "agents" / "odoo-qa-planner.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading_prefix: str = "## ") -> str:
    """Slice `text` from `heading` up to (not including) the next heading at the same level."""
    idx = text.find(heading)
    assert idx != -1, f"heading {heading!r} not found"
    rest = text[idx + len(heading):]
    end = rest.find(f"\n{next_heading_prefix}")
    return rest if end == -1 else rest[:end]


# ---------------------------------------------------------------------------
# Rule 1 + 2: TDD Section 9 - mandatory per-module AC block + independence guard
# ---------------------------------------------------------------------------


def test_section9_requires_a_module_level_block_per_affected_module():
    body = _read(ARCHITECT)
    sec9 = _section(body, "## 9. Acceptance Criteria")
    assert "MANDATORY" in sec9, (
        "§9 must state the module-level AC block is MANDATORY, not merely one of two optional "
        "levels."
    )
    assert "PER AFFECTED MODULE" in sec9 or "per affected module" in sec9.lower(), (
        "§9 must require one AC block per affected module."
    )
    assert "§1 per-module table" in sec9, (
        "§9 must anchor the per-module AC requirement to §1's per-module table (one block per row)."
    )
    assert "INCOMPLETE" in sec9, (
        "§9 must state the design is INCOMPLETE until every module in §1 has its own §9 block."
    )
    # Red-before-green: the old two-optional-levels wording must be gone.
    assert "Required at TWO levels" not in sec9, (
        "§9 still carries the old 'two levels' wording - the per-module floor was not tightened."
    )


def test_section9_independence_guard_present_and_bans_osm_code_grounding():
    body = _read(ARCHITECT)
    sec9 = _section(body, "## 9. Acceptance Criteria")
    assert "INDEPENDENCE GUARD" in sec9, "§9 must carry a named INDEPENDENCE GUARD subsection."
    assert "requirement" in sec9.lower() and "business rule" in sec9.lower(), (
        "§9's independence guard must ground `expected` in the requirement/business rule."
    )
    assert "NEVER" in sec9 and "OSM" in sec9, (
        "§9's independence guard must explicitly ban phrasing `expected` from an OSM finding."
    )
    assert "odoo-qa-planner" in sec9, (
        "§9's independence guard must state it mirrors the odoo-qa-planner code-read ban."
    )
    assert "acceptance-oracle-contract.md" in sec9, (
        "§9 must point at the acceptance-oracle-contract SSOT."
    )
    # §7 is explicitly carved out - it may cite OSM for structural/test-scaffolding grounding.
    assert "§7" in sec9, (
        "§9 must distinguish itself from §7 (which may cite OSM for base-class/coverage grounding)."
    )


def test_section7_scenario_table_partitioned_per_module():
    body = _read(ARCHITECT)
    sec7 = _section(body, "## 7. Test strategy outline")
    lower = sec7.lower()
    assert "per-module partition" in lower or "partitioned per module" in lower, (
        "§7 must require the scenario table be partitioned per module."
    )
    assert "single-mode multi-module" in sec7 or "single-mode" in sec7, (
        "§7 must call out that the per-module partition applies even in single-mode "
        "multi-module TDDs, not only master-child mode."
    )
    assert "### <module>" in sec7 or "<module>" in sec7, (
        "§7 must specify a concrete per-module grouping mechanism (a subheading per module)."
    )


# ---------------------------------------------------------------------------
# Mirrored wording in odoo-solution-design SKILL.md
# ---------------------------------------------------------------------------


def test_solution_design_consistency_pass_confirms_module_level_ac():
    """The master-child consistency pass (Decompose branch step d) reads each child's §9 - it
    must confirm the MANDATORY per-module block + INDEPENDENCE GUARD are honored, not just note
    that §9 exists."""
    body = _read(SOLUTION_DESIGN_SKILL)
    idx = body.find("**d. Consistency pass")
    assert idx != -1, "Decompose branch step d (Consistency pass) not found."
    step_d = body[idx: idx + 700]
    assert "MANDATORY" in step_d, (
        "Consistency pass must confirm each child's §9 carries its MANDATORY module-level block."
    )
    assert "INDEPENDENCE GUARD" in step_d, (
        "Consistency pass must confirm each child's §9 honors the INDEPENDENCE GUARD."
    )


def test_solution_design_section7_invariant_requires_per_module_partition():
    body = _read(SOLUTION_DESIGN_SKILL)
    idx = body.find("**Invariant:**")
    assert idx != -1, "§7 tool-usage Invariant paragraph not found."
    invariant = body[idx: idx + 500]
    assert "PARTITIONED PER MODULE" in invariant, (
        "The §7 Invariant in odoo-solution-design must require the per-module partition, "
        "mirroring the tightened agent wording."
    )


# ---------------------------------------------------------------------------
# Rule 4: odoo-planner / odoo-planning demote QA_ORACLE to optional/usually-absent
# ---------------------------------------------------------------------------


def test_planner_agent_marks_qa_oracle_optional_and_usually_absent():
    body = _read(PLANNER)
    # Red-before-green: the old headline implying the oracle is a standard planning input.
    assert "the gap matrix, and the independent QA oracle into" not in body, (
        "odoo-planner description still implies the independent QA oracle pre-exists at "
        "planning time - it must be demoted to optional/usually-absent."
    )
    assert "OPTIONAL" in body, "odoo-planner must mark QA_ORACLE as OPTIONAL."
    assert "usually" in body.lower() and "absent" in body.lower(), (
        "odoo-planner must state the QA oracle is usually ABSENT at planning time."
    )
    assert "odoo-acceptance" in body and "Phase 1" in body, (
        "odoo-planner must state the oracle is authored later, at odoo-acceptance Phase 1."
    )
    assert "§9" in body, (
        "odoo-planner must state the plan reserves the acceptance stage against the design's "
        "§9 Acceptance Criteria when the oracle is absent."
    )
    assert "RESERVES" in body, (
        "odoo-planner must use RESERVES language for the acceptance stage when no oracle exists."
    )


def test_planner_round0_qa_oracle_step_reflects_optionality():
    body = _read(PLANNER)
    idx = body.find("QA_ORACLE")
    assert idx != -1
    step = body[idx: idx + 600]
    assert "OPTIONAL" in step and "ABSENT" in step, (
        "Round 0 step 3 (QA_ORACLE) must be labeled OPTIONAL / usually ABSENT."
    )
    assert "§9" in step, "Round 0 step 3 must name §9 as the fallback source when the oracle is absent."


def test_planning_skill_input_port_marks_qa_oracle_optional():
    body = _read(PLANNING_SKILL)
    idx = body.find("QA oracle")
    assert idx != -1, "Input port section must still name the QA oracle input."
    bullet = body[idx: idx + 500]
    assert "OPTIONAL" in bullet and "ABSENT" in bullet, (
        "odoo-planning's Input port QA-oracle bullet must be marked OPTIONAL / usually ABSENT."
    )
    assert "odoo-acceptance" in bullet, (
        "odoo-planning must state the oracle is authored later at odoo-acceptance."
    )


# ---------------------------------------------------------------------------
# Rule 5: acceptance-oracle-contract.md + odoo-qa-planner cross-reference the §9 guard
# ---------------------------------------------------------------------------


def test_oracle_contract_allows_design_doc_section9_as_source():
    body = _read(ORACLE_CONTRACT)
    assert "DESIGN_DOC" in body and "§9" in body, (
        "acceptance-oracle-contract.md must name DESIGN_DOC §9 as a legitimate source of expected."
    )
    assert "ALLOWED" in body, (
        "acceptance-oracle-contract.md must explicitly ALLOW §9 as a source, distinct from the "
        "banned implementation/code source."
    )
    assert "INDEPENDENCE GUARD" in body, (
        "acceptance-oracle-contract.md must cross-reference the design's own §9 INDEPENDENCE GUARD."
    )
    assert "odoo-solution-architect.md" in body, (
        "acceptance-oracle-contract.md must point at agents/odoo-solution-architect.md for the "
        "§9 INDEPENDENCE GUARD definition."
    )


def test_qa_planner_cross_references_section9_independence_guard():
    body = _read(QA_PLANNER)
    assert "INDEPENDENCE GUARD" in body, (
        "odoo-qa-planner must cross-reference the §9 INDEPENDENCE GUARD when naming DESIGN_DOC §9 "
        "as an allowed input."
    )
    assert "odoo-solution-architect.md" in body, (
        "odoo-qa-planner must point at agents/odoo-solution-architect.md §9 for the guard."
    )
    # The pre-existing REQUIREMENT input row must still name DESIGN_DOC §9 (Fix 3 finding).
    assert "DESIGN_DOC" in body and "§9" in body, (
        "odoo-qa-planner must still name DESIGN_DOC §9 as a source of the requirement/intent."
    )


# ---------------------------------------------------------------------------
# ASCII-hyphen output convention (repo-wide rule) for all files this fix touches
# ---------------------------------------------------------------------------

_TOUCHED_FILES = [
    ARCHITECT,
    SOLUTION_DESIGN_SKILL,
    PLANNER,
    PLANNING_SKILL,
    ORACLE_CONTRACT,
    QA_PLANNER,
]


def test_touched_files_use_ascii_hyphen_only():
    banned = {0x2013: "en-dash", 0x2014: "em-dash", 0x2012: "figure-dash", 0x2015: "horizontal-bar"}
    offenders = []
    for f in _TOUCHED_FILES:
        text = _read(f)
        for cp, label in banned.items():
            if chr(cp) in text:
                offenders.append(f"{f.name}: contains {label}")
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)
