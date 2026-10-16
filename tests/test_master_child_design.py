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
  The brief CARRIERS (odoo-code-review sets the token; the reviewer/coder agents + the contract
  snippet read it) acknowledge the master constraint via the `MASTER_DESIGN_DOC` brief token.
  Guarded by test_master_design_doc_wired. Each carrier is a separate parametrized case so a
  regression in one file is immediately locatable.
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
# Wiring test B: MASTER_DESIGN_DOC brief token must appear in every carrier
# ---------------------------------------------------------------------------

# Brief CARRIERS that must reference the MASTER_DESIGN_DOC handoff token.
# The contract: any consumer that reads a design handoff brief from
# odoo-solution-architect must acknowledge both levels (DESIGN_DOC for the child
# spec, MASTER_DESIGN_DOC for the hard-constraint master TDD).
_WIRED_FILES = [
    PLUGIN / "skills" / "odoo-code-review" / "references" / "agent-prompts.md",
    PLUGIN / "agents" / "odoo-code-reviewer.md",
    PLUGIN / "skills" / "odoo-coding" / "SKILL.md",
    PLUGIN / "agents" / "odoo-coder.md",
    PLUGIN / "agents" / "odoo-test-writer.md",
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
# Contested-symbol reconciliation (same-layer siblings): no agent can address
# a sibling, so a child records the contested symbol and the LEAD decides
# after its R1 barrier clears - bounded to ONE reconciliation round per layer,
# with single-writer discipline preserved (a child NEVER writes §10/index.yaml).
#
# Business rule this protects: a same-layer disagreement must neither block a
# child nor be silently resolved by one side picking a winner. The earlier
# design had peers message each other directly - unimplementable twice over
# (no launcher can name a sibling, and a child's roster contains only agents it
# launched itself), so a child following it would stall on a send that cannot
# resolve.
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
