"""Guard: `instance_touching` is checked against the skill, never against its own derivation.

`generator/check_orchestration.py::_derive_gate_tier` maps `instance_touching: true` straight to
`default_gate_tier: L2` - an ALWAYS-human gate the autonomy dial can never lower - and rule 1d then
asserts the stored tier equals that derivation. Read together, those two are a closed loop: the
registry states a fact, the lint computes a tier from that fact, and then checks the tier against
the computation. A wrong input yields a self-consistent wrong output and a green suite.

That is not hypothetical. `odoo-qa-suite` shipped `instance_touching: true` while its own
frontmatter called it "non-executing", its Out-of-Scope table routed every live run to
`odoo-acceptance`, and its instance need was handed off as `NEEDS_NEXT -> odoo-instance`. The
result was a human gate on a static test plan, and `make validate` agreed with it.

This file protects the CONTRADICTION, not the current registry contents:

  * `test_no_skill_declares_a_live_instance_it_never_drives` - the live invariant (rule 16a).
  * `test_generated_tools_region_is_not_evidence` - the exact hole. The generated `## MCP tools`
    block prints an `odoo-bin` sentence in its `cli_help` blurb for skills that never touch an
    instance, so a body that contains NOTHING BUT that block must read as zero evidence. Without
    this, the naive scan certifies precisely the declarations the rule exists to catch.
  * `test_detector_*` - synthetic mutation proofs that each half can fire, and that hand-off
    prose (the shape that fooled the registry) is not mistaken for a drive.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "odoo-ai-agents"
CHECKER = PLUGIN_ROOT / "generator" / "check_orchestration.py"
DEPS_FILE = PLUGIN_ROOT / "generator" / "skill_tool_deps.json"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_orchestration_under_test", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _orchestration() -> dict:
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data["orchestration"].items() if not k.startswith("_")}


def test_no_skill_declares_a_live_instance_it_never_drives() -> None:
    """Rule 16a as an invariant: a `true` with no evidence anywhere in the skill's own body.

    Such a declaration does not merely mislabel - it derives L2 and stops an otherwise-automatic
    run to authorize an irreversible act the skill never performs."""
    findings: list[str] = []
    warn_only: list[str] = []
    checker.check_instance_truth(findings, warn_only)
    offences = [f for f in findings if "[instance-truth]" in f]
    assert not offences, "\n".join(offences)


def test_the_declared_true_set_is_not_empty() -> None:
    """Anchors the check above: if every skill declared false, 16a would pass measuring nothing."""
    declared = [n for n, e in _orchestration().items() if e.get("instance_touching")]
    assert declared, (
        "no skill declares instance_touching=true - rule 16a's subject set is empty and the "
        "invariant above passes vacuously"
    )


def test_generated_tools_region_is_not_evidence() -> None:
    """The exact mechanism that let a false declaration look corroborated.

    The generated block names `odoo-bin` inside the `cli_help` tool blurb for every skill that
    lists that tool, instance-touching or not. A body made of nothing else must score zero."""
    generated_only = (
        "## MCP tools\n\n"
        "<!-- BEGIN GENERATED TOOLS -->\n"
        "- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for "
        "deprecated flags.\n"
        "- `model_inspect` - Inspect a model.\n"
        "<!-- END GENERATED TOOLS -->\n"
    )
    stripped = checker.GENERATED_TOOLS_RE.sub("", generated_only)
    strong, weak = checker._instance_evidence(stripped)
    assert not strong and not weak, (
        f"the generated tools block counted as instance evidence: strong={strong} weak={weak}"
    )


@pytest.mark.parametrize(
    "body",
    [
        "Between advances, call `allocator.py heartbeat <token>` on the cluster's handle.",
        "1. **Provision once at the leaf.** Dispatch `odoo-instance` (`odoo-instance-ops`, ...).",
        "the coder self-provisions by invoking\n`Skill(odoo-instance)` (a unique ephemeral DB).",
        "CONDITIONAL the `odoo-instance` skill (via the Skill tool): run ONLY when the range "
        "touches Python.",
    ],
)
def test_detector_sees_a_skill_that_drives_an_instance(body: str) -> None:
    strong, _weak = checker._instance_evidence(body)
    assert strong, f"detector missed a real instance drive: {body!r}"


@pytest.mark.parametrize(
    "body",
    [
        # the shape that fooled the registry: the need is handed off, not performed
        "When no live Odoo instance is reachable, emit `status: NEEDS_NEXT` with skill: "
        "odoo-instance, reason: provision the instance needed for runtime bug reproduction.",
        # an Out-of-Scope row
        "| Running tests on a live instance or cluster | route to `odoo-acceptance` |",
        # a routing-table row naming the front door
        "| 63 | \"spin up v17\" | `odoo-instance` | Front door for ALL live-instance lifecycle |",
        # an explicit abstention
        "This skill does not dispatch the `odoo-instance` skill and never launches "
        "`odoo-instance-ops`.",
        # module not installed yet -> install first elsewhere
        "- **Module not yet installed on a live instance** -> install first via `odoo-instance`.",
    ],
)
def test_detector_does_not_mistake_a_hand_off_for_a_drive(body: str) -> None:
    strong, _weak = checker._instance_evidence(body)
    assert not strong, f"detector read a hand-off as a drive: {body!r} -> {strong}"


def test_half_a_fires_on_a_declaration_with_no_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation proof for the strict half: a registry that claims a live instance a body never
    mentions must be a finding, not a shrug."""
    monkeypatch.setattr(
        checker, "load_orch", lambda: {"fake-skill": {"instance_touching": True}}
    )
    monkeypatch.setattr(
        checker,
        "skill_body",
        lambda name: "## Role\n\nProduce a static, non-executing test plan. Nothing is run.\n",
    )
    findings: list[str] = []
    warn_only: list[str] = []
    checker.check_instance_truth(findings, warn_only)
    assert any("[instance-truth]" in f and "fake-skill" in f for f in findings), findings
    assert not warn_only


def test_half_b_fires_on_a_denial_the_body_contradicts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation proof for the warn-only half: the lint must be able to contradict a `false` too -
    it just may not gate on it while the tier derivation still keys L2 off the bare fact."""
    monkeypatch.setattr(
        checker, "load_orch", lambda: {"fake-skill": {"instance_touching": False}}
    )
    monkeypatch.setattr(
        checker,
        "skill_body",
        lambda name: "Dispatch `odoo-instance` for the capture DB, then "
                     "`allocator.py release <token>` when the last module is done.\n",
    )
    findings: list[str] = []
    warn_only: list[str] = []
    checker.check_instance_truth(findings, warn_only)
    assert any("[instance-truth]" in f and "fake-skill" in f for f in warn_only), warn_only
    assert not findings


def test_gate_tier_still_matches_the_derivation_for_every_skill() -> None:
    """The stored tier must agree with `_derive_gate_tier` - the pre-existing consistency check,
    asserted here so a corrected `instance_touching` cannot be landed without its tier."""
    mismatches = []
    for name, e in sorted(_orchestration().items()):
        output_mode = e.get("output_mode")
        if output_mode not in checker.VALID_OUTPUT_MODE:
            continue
        expected = checker._derive_gate_tier(
            e.get("spawn_class", ""),
            bool(e.get("instance_touching")),
            output_mode,
            bool(e.get("outward")),
        )
        if e.get("default_gate_tier") != expected:
            mismatches.append(f"{name}: stored={e.get('default_gate_tier')} derived={expected}")
    assert not mismatches, "\n".join(mismatches)
