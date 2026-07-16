"""Guard: master-child design contract - schema validity + downstream wiring.

Schema tests (test_index_yaml_*):
  PASS when an index.yaml fixture satisfies all contract requirements.
  FAIL when required fields are missing, child_path values collide, or
  dag_layer is inconsistent with depends_on (a module at layer k depends on
  a module at the same or higher layer -> invalid toposort).

  The invalid-fixture variant proves non-tautology: if the validator were
  removed or simplified to always return True, test_index_yaml_invalid_dag
  would PASS where it must FAIL, breaking CI.

Wiring tests:
  The master constraint has TWO valid representations of the same datum:
    - odoo-review-scoper is the SOURCE that RESOLVES the master design doc, and
      emits it through the scope-block field (`### Master design doc` heading +
      per-module `design_doc` column) - NOT the brief token. Guarded by
      test_scoper_emits_master_via_scope_block.
    - the brief CARRIERS (odoo-code-review sets the token; the reviewer/coder
      agents + the contract snippet read it) acknowledge master via the
      `MASTER_DESIGN_DOC` brief token. Guarded by test_master_design_doc_wired_*.
  FAIL when either representation regresses - the scoper losing master
  resolution, or a brief carrier dropping the token. Each carrier is a separate
  parametrized case so a regression in one file is immediately locatable.
"""

import re
from pathlib import Path

import pytest
import yaml  # PyYAML - in requirements.txt

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# Schema validator (self-contained, no production code required)
# ---------------------------------------------------------------------------

_REQUIRED_TOP = {"slug", "created", "master", "modules", "dag_layers"}
_REQUIRED_MODULE = {"name", "child_path", "depends_on", "dag_layer", "status"}
_VALID_STATUS = {"pending", "designed", "approved", "skipped"}


def _validate_index(data: dict) -> list[str]:
    """Return a list of violation strings; empty list = valid."""
    errors: list[str] = []

    # Top-level required fields
    missing_top = _REQUIRED_TOP - set(data.keys())
    if missing_top:
        errors.append(f"Missing top-level fields: {sorted(missing_top)}")

    modules = data.get("modules", [])
    if not isinstance(modules, list) or len(modules) == 0:
        errors.append("modules must be a non-empty list")
        return errors  # can't continue without modules

    # Per-module required fields
    for idx, mod in enumerate(modules):
        missing_mod = _REQUIRED_MODULE - set(mod.keys())
        if missing_mod:
            errors.append(
                f"modules[{idx}] ({mod.get('name', '?')}) missing fields: {sorted(missing_mod)}"
            )
        if "status" in mod and mod["status"] not in _VALID_STATUS:
            errors.append(
                f"modules[{idx}].status={mod['status']!r} not in {sorted(_VALID_STATUS)}"
            )

    # child_path must be distinct
    child_paths = [m["child_path"] for m in modules if "child_path" in m]
    if len(child_paths) != len(set(child_paths)):
        seen: set[str] = set()
        dupes = [p for p in child_paths if p in seen or seen.add(p)]  # type: ignore[func-returns-value]
        errors.append(f"Duplicate child_path values: {dupes}")

    # dag_layer consistency: every depends_on entry must be at a strictly lower layer
    layer_of: dict[str, int] = {
        m["name"]: m["dag_layer"]
        for m in modules
        if "name" in m and "dag_layer" in m
    }
    for mod in modules:
        if "depends_on" not in mod or "dag_layer" not in mod or "name" not in mod:
            continue
        mod_layer = mod["dag_layer"]
        for dep in mod["depends_on"]:
            dep_layer = layer_of.get(dep)
            if dep_layer is None:
                errors.append(
                    f"{mod['name']}.depends_on references unknown module {dep!r}"
                )
            elif dep_layer >= mod_layer:
                errors.append(
                    f"{mod['name']} (layer {mod_layer}) depends_on {dep!r} "
                    f"(layer {dep_layer}) - dependency must be at a strictly lower layer"
                )

    return errors


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_index_yaml_valid():
    """A correctly formed index.yaml must pass all contract checks."""
    data = yaml.safe_load((FIXTURES / "index_valid.yaml").read_text(encoding="utf-8"))
    errors = _validate_index(data)
    assert errors == [], (
        "Valid fixture failed schema check:\n" + "\n".join(f"  - {e}" for e in errors)
    )


def test_index_yaml_valid_dag_topo():
    """Layer-0 modules have no depends_on; layer-1 modules only depend on layer-0."""
    data = yaml.safe_load((FIXTURES / "index_valid.yaml").read_text(encoding="utf-8"))
    layer_of = {m["name"]: m["dag_layer"] for m in data["modules"]}
    for mod in data["modules"]:
        for dep in mod["depends_on"]:
            assert layer_of[dep] < mod["dag_layer"], (
                f"{mod['name']} (layer {mod['dag_layer']}) depends on {dep!r} "
                f"(layer {layer_of[dep]}) - not a valid DAG"
            )


def test_index_yaml_valid_child_paths_distinct():
    """child_path values in the valid fixture must all be unique."""
    data = yaml.safe_load((FIXTURES / "index_valid.yaml").read_text(encoding="utf-8"))
    paths = [m["child_path"] for m in data["modules"]]
    assert len(paths) == len(set(paths)), f"Duplicate child_path in valid fixture: {paths}"


def test_index_yaml_invalid_dag():
    """The invalid fixture (same-layer dependency) MUST be caught by the validator.

    This is the non-tautology proof: the validator must return at least one
    error for this fixture. If it returns empty, the validator is broken and
    this test fails.
    """
    data = yaml.safe_load(
        (FIXTURES / "index_invalid_dag.yaml").read_text(encoding="utf-8")
    )
    errors = _validate_index(data)
    assert errors, (
        "Validator silently accepted an invalid DAG (same-layer dependency). "
        "The schema check is broken - it must catch layer-k depends-on-layer-k."
    )
    # Confirm the specific violation is identified
    violation_text = " ".join(errors)
    assert "layer" in violation_text, (
        f"Validator did catch an error but did not mention 'layer': {errors}"
    )


# ---------------------------------------------------------------------------
# Wiring test A: odoo-review-scoper emits master via the scope-block field
# ---------------------------------------------------------------------------


def test_scoper_emits_master_via_scope_block():
    """odoo-review-scoper RESOLVES the master design doc and emits it through the
    scope-block field, not through the MASTER_DESIGN_DOC brief token.

    The scoper is the SOURCE of the master constraint: it resolves the master
    path (`master_design_doc` / `### Master design doc` heading) and the per-module
    child path (`design_doc` column). The brief token MASTER_DESIGN_DOC is what
    DOWNSTREAM consumers (set by odoo-code-review) carry - the scoper deliberately
    does not use it. Both are valid representations of the same datum.

    FAILS if the scoper loses master resolution (no master field) OR drops the
    per-module design_doc column - i.e. a regression where downstream consumers
    would no longer receive the master constraint.
    """
    scoper = PLUGIN / "agents" / "odoo-review-scoper.md"
    text = scoper.read_text(encoding="utf-8")
    assert "master_design_doc" in text or "Master design doc" in text, (
        f"{scoper.relative_to(ROOT)} must RESOLVE and emit the master design doc "
        "(the `master_design_doc` field / `### Master design doc` scope-block heading). "
        "Without it, no consumer can receive the master constraint."
    )
    # Bare `design_doc` (the per-module column) - `\b...\b` excludes the substring
    # inside `master_design_doc` and `design_doc_mode`/`design_doc_ambiguity`.
    assert re.search(r"\bdesign_doc\b", text), (
        f"{scoper.relative_to(ROOT)} must carry the per-module `design_doc` column "
        "so each changed module receives its child design path."
    )


# ---------------------------------------------------------------------------
# Wiring test B: MASTER_DESIGN_DOC brief token must appear in every carrier
# ---------------------------------------------------------------------------

# Brief CARRIERS that must reference the MASTER_DESIGN_DOC handoff token.
# The contract: any consumer that reads a design handoff brief from
# odoo-solution-architect must acknowledge both levels (DESIGN_DOC for the child
# spec, MASTER_DESIGN_DOC for the hard-constraint master TDD).
# NOTE: odoo-review-scoper is deliberately NOT here - it is the SOURCE that
# resolves master via the scope-block field (test_scoper_emits_master_via_scope_block),
# not a brief carrier.
_WIRED_FILES = [
    PLUGIN / "skills" / "odoo-code-review" / "references" / "agent-prompts.md",
    PLUGIN / "agents" / "odoo-code-reviewer.md",
    PLUGIN / "skills" / "odoo-coding" / "SKILL.md",
    PLUGIN / "agents" / "odoo-coder.md",
    PLUGIN / "agents" / "odoo-test-writer.md",
    PLUGIN / "agents" / "odoo-backend-coder.md",
    PLUGIN / "agents" / "odoo-frontend-coder.md",
    PLUGIN / "snippets" / "master-child-design-contract.md",
]


@pytest.mark.parametrize(
    "consumer",
    _WIRED_FILES,
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_master_design_doc_wired(consumer):
    """MASTER_DESIGN_DOC must appear in every consumer file.

    FAILS when the wiring is absent - either the file was never wired or the
    token was removed as part of a regression. Each file is a separate
    parametrized case so CI pinpoints exactly which consumer is broken.
    """
    assert consumer.exists(), (
        f"Consumer file not found: {consumer.relative_to(ROOT)}. "
        "Update _WIRED_FILES if the file was intentionally moved or renamed."
    )
    text = consumer.read_text(encoding="utf-8")
    assert "MASTER_DESIGN_DOC" in text, (
        f"{consumer.relative_to(ROOT)} must reference MASTER_DESIGN_DOC. "
        "Wire the master-child handoff field or revert the removal."
    )


# ---------------------------------------------------------------------------
# Peer reconciliation (P2 wave 5): bounded same-layer debate + deadlock
# escalation exactly one level up + single-writer discipline (a child NEVER
# writes §10/index.yaml itself - B2 correction).
#
# Business rule this protects: same-layer child architects may negotiate a
# shared-symbol contract directly with each other (the sanctioned LATERAL
# case of spawner-completion-contract.md R3), but that negotiation MUST be
# bounded (never an open-ended back-and-forth) and a deadlock MUST escalate
# to the lead - never get silently resolved by one side picking a winner,
# and never skip past the lead to some other ancestor.
# ---------------------------------------------------------------------------

ARCHITECT_AGENT = PLUGIN / "agents" / "odoo-solution-architect.md"
DISPATCH_BRIEF_SNIPPET = PLUGIN / "snippets" / "dispatch-brief.md"
MASTER_CHILD_CONTRACT = PLUGIN / "snippets" / "master-child-design-contract.md"
SOLUTION_DESIGN_SKILL = PLUGIN / "skills" / "odoo-solution-design" / "SKILL.md"

_WS = re.compile(r"\s+")


def _normalized(text: str) -> str:
    """Collapse Markdown line-wrap whitespace so a phrase split across two
    source lines still matches a single-line assertion (mirrors the idiom in
    test_dispatch_brief.py's spawner-framing check)."""
    return _WS.sub(" ", text)


def test_peer_reconciliation_bounded_and_escalates():
    """Peer debate between same-layer child architects must be BOUNDED (a
    fixed round-trip cap, not an open-ended negotiation) and a deadlock must
    ESCALATE - never get silently resolved - exactly ONE level up (to the
    lead/main), never past it and never laterally to a third peer.

    FAILS if the round cap disappears (reopening the unbounded-debate risk
    the survey flagged) or if the escalation path stops naming "one level"
    (reopening the level-skipping risk R3 exists to prevent).
    """
    contract = _normalized(MASTER_CHILD_CONTRACT.read_text(encoding="utf-8"))
    idx = contract.find("## Peer reconciliation")
    assert idx != -1, (
        "master-child-design-contract.md must define a "
        "'## Peer reconciliation' section (the P2 peer-debate SSOT)."
    )
    section = contract[idx : idx + 3000]

    # Bounded: a concrete round-trip cap, not an open-ended loop.
    assert "TWO round-trips" in section, (
        "Peer reconciliation must state a concrete bounded round-trip cap (N=2) - "
        "an unbounded loop is the failure mode this rule exists to prevent."
    )

    # Deadlock -> escalate, never silently pick a winner (stated in the §10
    # block just above the section heading, not inside the section itself -
    # check the whole file, not the sliced section).
    assert "never silently pick a winner" in contract, (
        "A deadlock (cap exhausted or a §10 HARD-rule conflict) must escalate - "
        "the contract must forbid silently picking a winner."
    )

    # Escalation goes UP exactly one level - to the lead - never past it.
    assert "goes UP exactly one level" in section or "UP exactly one level" in section, (
        "Escalation must be scoped to exactly one level up (the lead), mirroring "
        "spawner-completion-contract.md R3 - never a level-skip."
    )
    assert "spawner-completion-contract.md" in section, (
        "Peer reconciliation must cross-reference spawner-completion-contract.md "
        "R3 as the SSOT for the report-up-one-level rule it lateralizes."
    )

    # The child-agent-facing summary in the architect must mirror both invariants
    # - a runtime-dispatched child reads the agent body, not the snippet, first.
    architect = _normalized(ARCHITECT_AGENT.read_text(encoding="utf-8"))
    idx2 = architect.find("## Peer reconciliation (child mode)")
    assert idx2 != -1, (
        "odoo-solution-architect.md must carry a "
        "'## Peer reconciliation (child mode)' subsection."
    )
    child_section = architect[idx2 : idx2 + 3000]
    assert "Two round-trips" in child_section, (
        "Child-mode section must restate the bounded round-trip cap."
    )
    assert "Escalate UP one level only" in child_section, (
        "Child-mode section must restate escalate-up-exactly-one-level-only."
    )
    assert "never past the lead" in child_section or "never to the peer, never past" in child_section, (
        "Child-mode section must forbid escalating past the lead or laterally to a peer."
    )


def test_peer_reconciliation_child_never_writes_section10_or_index():
    """Single-writer correction (B2): once peers agree, EACH records the
    contract in its OWN child TDD/worklog - NEITHER peer edits index.yaml or
    §10 directly. The MODE: consistency pass (dispatched by the orchestrating
    skill) remains the SOLE §10/index.yaml applier.

    FAILS if any of the three touched files stop stating this invariant -
    regressing to the pre-fix design where the debate mechanism could write
    §10 directly and recreate the concurrent-write race B2 flagged.
    """
    contract = _normalized(MASTER_CHILD_CONTRACT.read_text(encoding="utf-8"))
    assert "NEITHER peer edits `index.yaml`/§10 directly" in contract, (
        "master-child-design-contract.md must forbid peers from writing "
        "§10/index.yaml directly - only the consistency pass may."
    )
    assert "records the agreed contract in its OWN child TDD" in contract, (
        "master-child-design-contract.md must require each peer to record the "
        "agreed contract in its OWN child TDD, never in the shared §10/index.yaml."
    )
    assert "is the SOLE §10" in contract and "`index.yaml` applier" in contract, (
        "master-child-design-contract.md's Conflict list section must name the "
        "consistency pass as the SOLE §10/index.yaml applier."
    )

    architect = _normalized(ARCHITECT_AGENT.read_text(encoding="utf-8"))
    assert "Never edit `index.yaml` or §10 yourself" in architect, (
        "odoo-solution-architect.md child mode must forbid the child from "
        "editing §10/index.yaml itself even after a peer agreement."
    )
    assert "never edit `index.yaml`/§10" in architect, (
        "odoo-solution-architect.md's child-row grounding cell must forbid "
        "editing index.yaml/§10 as part of the peer-reconcile note."
    )

    skill = _normalized(SOLUTION_DESIGN_SKILL.read_text(encoding="utf-8"))
    assert "children never write §10 themselves" in skill or "children never write §10" in skill, (
        "odoo-solution-design/SKILL.md's consistency-pass step must state "
        "children never write §10 themselves - it is the sole applier."
    )


def test_peers_field_is_the_lead_brokered_address_authority():
    """The lead (odoo-solution-design, main context) is the address authority
    for PEERS - it injects the field at fan-out; a child never guesses an
    address. A lone-child layer must get the field explicitly set to `none`
    (never an implicit gap a child could misread as "no PEERS field at all
    means I may guess"). Also confirms the caller-side schema (dispatch-brief.md)
    documents the field for any spawner composing a same-layer batch brief.
    """
    brief = _normalized(DISPATCH_BRIEF_SNIPPET.read_text(encoding="utf-8"))
    assert "`PEERS`" in brief, (
        "dispatch-brief.md's designer/planner delta must name the PEERS field."
    )

    skill = _normalized(SOLUTION_DESIGN_SKILL.read_text(encoding="utf-8"))
    assert "PEERS: <other child names in this" in skill, (
        "odoo-solution-design/SKILL.md step c must inject PEERS: <...> at "
        "same-layer fan-out."
    )
    assert "PEERS: none" in skill, (
        "odoo-solution-design/SKILL.md must explicitly set PEERS: none for a "
        "lone-child layer - never leave the field silently absent."
    )
    assert "address authority" in skill, (
        "odoo-solution-design/SKILL.md must state the orchestrating skill is "
        "the address authority for the PEERS list it brokers."
    )
