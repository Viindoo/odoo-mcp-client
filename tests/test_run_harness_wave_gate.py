"""Behavioral guards for run-harness's between-wave integration drive-to-done gate (ETHOS#11).

(Retargeted from the folded-in per-wave git-executor. The behavior each assertion
protects is unchanged; only the OWNER moved to run-harness.)

These protect the two safety couplings the between-wave advance depends on - not the
code structure:

- R1 (advance<->close-gate coupling): run-harness may auto-advance between waves ONLY because
  each wave now proves a green CUMULATIVE close-gate before it auto-advances (and, ultimately,
  before the run's ONE terminal PR). If that anchor is ever removed while the L1 between-wave
  autonomy stays, the run would drive to done with no regression proof. This test fails the moment
  the "cumulative ... close-gate" clause disappears from run-harness, so the autonomy cannot ship
  without its justification.

- R2 (SSOT<->code drift): docs/reference/workflow-harness.md §8.4 is a HAND-AUTHORED SSOT. It
  states (a) the registry `_derive_gate_tier` derivation (which has NO spawner-wave branch anymore)
  and (b) that the between-wave integration (`approach_kind: wave`) node advances at L1 while the
  downstream outward MERGE stays human-gated (L2). This test asserts the doc and the code agree, so
  a future editor cannot re-introduce a `spawner-wave` class or flip the between-wave tier without a
  red test.

Each assertion fails for exactly one reason. Run:
  python3 -m pytest tests/test_run_harness_wave_gate.py -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"
HARNESS_DOC = PLUGIN / "docs" / "reference" / "workflow-harness.md"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import _derive_gate_tier, VALID_SPAWN_CLASS  # noqa: E402


# ---------------------------------------------------------------------------
# R1 - the cumulative close-gate anchor must be present in run-harness
# ---------------------------------------------------------------------------

_CUMULATIVE_GATE_RE = re.compile(r"(?i)cumulative\b.{0,40}?\bclose-gate", re.DOTALL)


def test_run_harness_has_cumulative_close_gate():
    """R1: run-harness must carry the cumulative close-gate clause (the between-wave regression anchor).

    Fails if: the cumulative close-gate wording is removed from run-harness/SKILL.md. The
    between-wave advance is L1 (auto-pass / drive-to-done); that is only safe because each wave
    proves a green cumulative regression suite before it auto-advances (and before the run's ONE PR).
    """
    assert RUN_HARNESS.exists(), f"skills/run-harness/SKILL.md not found at {RUN_HARNESS}"
    body = RUN_HARNESS.read_text(encoding="utf-8")
    assert _CUMULATIVE_GATE_RE.search(body), (
        "skills/run-harness/SKILL.md: cumulative close-gate clause missing. "
        "The body must contain a 'cumulative ... close-gate' clause. The between-wave L1 autonomy "
        "MUST NOT ship without this regression gate."
    )


# ---------------------------------------------------------------------------
# R2 - the spawner-wave class is gone; §8.4 states the wave-node L1 without it
# ---------------------------------------------------------------------------


def _section_84(text: str) -> str:
    """Return the body of the '### 8.4 Gate-tier policy' section (up to the next '### ')."""
    start = re.search(r"^###\s+8\.4\b.*$", text, re.MULTILINE)
    assert start, "workflow-harness.md: '### 8.4' Gate-tier policy section not found"
    rest = text[start.end():]
    nxt = re.search(r"^###\s+", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_spawner_wave_class_is_gone():
    """R2: the `spawner-wave` spawn_class was removed when the per-wave git-executor was folded into run-harness.

    Fails if: `spawner-wave` re-appears as a valid spawn class, or `_derive_gate_tier` regains a
    class-based branch that would need it.
    """
    assert "spawner-wave" not in VALID_SPAWN_CLASS, (
        "spawner-wave must no longer be a valid spawn_class - it is no longer a registered spawn class."
    )


def test_derive_gate_tier_has_no_wave_branch():
    """R2: _derive_gate_tier derives from (instance_touching, output_mode, outward) ONLY.

    A writes-files, non-instance, non-outward skill is L1; add instance_touching and it becomes L2.
    There is no wave/spawner-wave short-circuit that would keep an instance-touching skill at L1.
    """
    assert _derive_gate_tier("spawner-agent", False, "writes-files", False) == "L1"
    assert _derive_gate_tier("spawner-agent", True, "writes-files", False) == "L2"
    assert _derive_gate_tier("orchestrator-nl", False, "chat-only", False) == "L0"
    assert _derive_gate_tier("spawner-agent", False, "writes-files", True) == "L2"


def test_harness_doc_states_between_wave_node_is_l1():
    """R2: workflow-harness.md §8.4 must state the between-wave (`approach_kind: wave`) node advances
    at L1, and must NOT contain a `spawner-wave` derivation branch.

    Fails if: the SSOT doc re-introduces `spawner-wave`, or drops/flips the between-wave L1 statement.
    """
    text = HARNESS_DOC.read_text(encoding="utf-8")
    sec = _section_84(text)
    assert "spawner-wave" not in sec or "removed" in sec.lower(), (
        "workflow-harness.md §8.4 must not re-introduce a `spawner-wave` derivation branch "
        "(only a note that it was removed is allowed)."
    )
    m = re.search(r"between-wave integration.{0,80}?L1", sec, re.DOTALL)
    assert m, (
        "workflow-harness.md §8.4 must state the between-wave integration (`approach_kind: wave`) "
        "node tier is L1 (the drive-to-done advance)."
    )
    # The downstream outward merge stays human-gated (L2) - the doc must keep that coupling.
    assert "downstream" in sec.lower() and "merge" in sec.lower(), (
        "workflow-harness.md §8.4 must keep the human-gated downstream merge coupling for the wave node."
    )


def test_run_harness_body_states_wave_advance_l1_merge_l2():
    """R2 (companion): run-harness SKILL.md itself must state the between-wave advance is L1
    (auto-advance, NO per-wave PR) and the ONLY coding-run L2 is the downstream outward MERGE
    (odoo-pr-monitoring's L2-merge-gate). The single-run-PR model has no per-wave L2-squash-gate."""
    body = RUN_HARNESS.read_text(encoding="utf-8")
    low = body.lower()
    assert "between-wave integration" in low, "run-harness must own a between-wave integration section"
    assert "l1" in low, "run-harness must state the between-wave advance is L1 (drive-to-done)."
    assert "no per-wave pr" in low, (
        "run-harness must state the wave auto-advances with NO per-wave PR (single-run-PR model)."
    )
    assert "l2-merge-gate" in low and "odoo-pr-monitoring" in low, (
        "run-harness must state the ONLY coding-run L2 is the downstream outward MERGE "
        "(odoo-pr-monitoring's L2-merge-gate)."
    )
    assert "approach_kind" in low and "wave" in low, (
        "run-harness must describe the coding wave node as `approach_kind: wave`."
    )


def test_i18n_registry_tier_stays_l2():
    """R2 (companion): a genuine instance-touching non-wave skill (odoo-i18n) must stay L2 - the
    removal of the spawner-wave short-circuit must not lower any real instance-touching skill."""
    reg = json.loads(
        (PLUGIN / "generator" / "skill_tool_deps.json").read_text(encoding="utf-8")
    )["orchestration"]

    i18n = reg["odoo-i18n"]
    i18n_expected = _derive_gate_tier(
        i18n["spawn_class"], bool(i18n.get("instance_touching")),
        i18n["output_mode"], bool(i18n.get("outward")),
    )
    assert i18n_expected == "L2", f"odoo-i18n must stay L2 via instance_touching, got {i18n_expected!r}"
    assert i18n["default_gate_tier"] == i18n_expected == "L2"

    # And there is no lingering spawner-wave entry in the registry (skip the `_doc` string key).
    assert all(
        v.get("spawn_class") != "spawner-wave"
        for k, v in reg.items()
        if not k.startswith("_") and isinstance(v, dict)
    ), "no orchestration entry may still declare spawn_class=spawner-wave"
