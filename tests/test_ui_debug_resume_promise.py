"""ui-debug-session.workflow.yaml claims (top-of-file comment) that each phase writes
state so a multi-hour debug session can be interrupted and continued without losing
context. But the 'inspect' phase's nl_trigger referenced the symptom card and
reproduce-phase output as already-known conversation context, never instructing a
read-back from disk - a session resumed in a fresh context window would silently
diagnose from nothing, making the documented promise false.

Fix: name Phase 0's artifact explicitly and have Phase 2 ('inspect') explicitly read
both prior artifacts back from disk before diagnosing, instead of assuming they are
still in context.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "plugins" / "odoo-ai-agents" / "workflows" / "ui-debug-session.workflow.yaml"

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed")


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _phase(data, phase_id):
    for p in data["phases"]:
        if p["id"] == phase_id:
            return p
    raise KeyError(phase_id)


def test_collect_symptom_names_a_concrete_artifact_path():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"\.odoo-ai/debug/<slug>-symptom\.md", text), (
        "collect-symptom (Phase 0) must name a concrete on-disk artifact path - a later "
        "phase cannot read back state that was never given a filename"
    )


def test_inspect_phase_instructs_reading_back_prior_artifacts_from_disk():
    data = _load()
    inspect = _phase(data, "inspect")
    trigger = inspect.get("nl_trigger") or ""

    for artifact in ("<slug>-symptom.md", "<slug>-reproduce.md"):
        assert artifact in trigger, (
            f"'inspect' phase nl_trigger must name {artifact} as a concrete read-back target"
        )

    assert re.search(r"(?i)read\s*back", trigger), (
        "'inspect' phase nl_trigger must explicitly instruct reading back the prior-phase "
        "artifacts from disk - not merely reference them as already-known context, which "
        "silently breaks the moment a resumed session starts in a fresh context window"
    )


def test_workflow_schema_still_valid_after_the_fix():
    """Regression guard: the read-back wiring must not break the schema fields the
    runner depends on for the 'inspect' phase."""
    data = _load()
    inspect = _phase(data, "inspect")
    assert inspect.get("inline") is True
    assert inspect.get("model_tier") in {"haiku", "sonnet", "opus", "inherit"}
    assert inspect.get("gate")
