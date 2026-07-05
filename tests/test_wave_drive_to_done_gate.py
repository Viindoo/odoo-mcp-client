"""Behavioral guards for the P1 drive-to-done wave reclassification (ETHOS#11).

These protect the two safety couplings the reclassification depends on - not the
code structure:

- R1 (P1<->P2 coupling): odoo-wave may auto-advance between waves ONLY because each
  wave now proves a green CUMULATIVE close-gate before it opens a PR. If P2's
  Phase-4.4 anchor is ever removed while P1's L1 autonomy stays, the wave would
  drive to done with no regression proof - exactly the hole P2 fills. This test
  fails the moment the "cumulative ... close-gate" clause disappears from
  odoo-wave, so the autonomy change cannot ship without its justification.

- R2 (SSOT<->code drift): docs/reference/workflow-harness.md §8.4 is a HAND-AUTHORED
  SSOT with no other test guarding it. It states the gate-tier derivation that
  `check_orchestration._derive_gate_tier` implements. This test asserts the doc's
  spawner-wave clause derives the SAME tier the code does, so a future editor cannot
  silently re-introduce "spawner-wave => L2" in prose and contradict the code (or
  vice-versa) without a red test.

Each assertion fails for exactly one reason. Run:
  python3 -m pytest tests/test_wave_drive_to_done_gate.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
WAVE_SKILL = PLUGIN / "skills" / "odoo-wave" / "SKILL.md"
HARNESS_DOC = PLUGIN / "docs" / "reference" / "workflow-harness.md"

# Make `generator` importable (same pattern as tests/test_gen_surface.py): the
# generator package lives under the skills plugin, so the plugin root is on sys.path.
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import _derive_gate_tier  # noqa: E402


# ---------------------------------------------------------------------------
# R1 - the cumulative close-gate anchor must be present in odoo-wave
# ---------------------------------------------------------------------------

_CUMULATIVE_GATE_RE = re.compile(r"(?i)cumulative\b.{0,40}?\bclose-gate", re.DOTALL)


def test_wave_body_has_cumulative_close_gate():
    """R1: odoo-wave must carry the cumulative close-gate clause (P2 anchor).

    Fails if: the Phase-4.4 cumulative close-gate wording is removed from
    skills/odoo-wave/SKILL.md. P1 reclassified the between-wave advance to L1
    (auto-pass / drive-to-done); that is only safe because each wave proves a
    green cumulative regression suite before opening a PR. Without this anchor
    the wave would drive to done with no cumulative proof.
    """
    assert WAVE_SKILL.exists(), f"skills/odoo-wave/SKILL.md not found at {WAVE_SKILL}"
    body = WAVE_SKILL.read_text(encoding="utf-8")
    assert _CUMULATIVE_GATE_RE.search(body), (
        "skills/odoo-wave/SKILL.md: cumulative close-gate clause missing. "
        "The body must contain a 'cumulative ... close-gate' clause (Phase 4.4). "
        "P1's between-wave L1 autonomy MUST NOT ship without this P2 regression gate."
    )


# ---------------------------------------------------------------------------
# R2 - §8.4 spawner-wave derivation must agree with _derive_gate_tier
# ---------------------------------------------------------------------------


def _section_84(text: str) -> str:
    """Return the body of the '### 8.4 Gate-tier policy' section (up to the next '### ')."""
    start = re.search(r"^###\s+8\.4\b.*$", text, re.MULTILINE)
    assert start, "workflow-harness.md: '### 8.4' Gate-tier policy section not found"
    rest = text[start.end():]
    nxt = re.search(r"^###\s+", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_harness_doc_spawner_wave_tier_matches_code():
    """R2: workflow-harness.md §8.4 must derive the SAME tier for a spawner-wave
    that check_orchestration._derive_gate_tier does.

    Fails if: the SSOT doc and the code disagree on the spawner-wave gate tier -
    e.g. someone re-introduces 'spawn_class == spawner-wave => L2' in the doc
    while the code short-circuits it to L1 (or vice-versa). This turns an
    otherwise-untested hand-authored SSOT into a guarded one.
    """
    # Behavior of the code for a STATIC spawner-wave (worktree fan-out, ephemeral
    # instance, not outward). odoo-wave is instance_touching=writes-files in the
    # registry; the spawner-wave branch must short-circuit that to L1.
    derived = _derive_gate_tier(
        spawn_class="spawner-wave",
        instance_touching=True,
        output_mode="writes-files",
        outward=False,
    )
    assert derived == "L1", (
        "_derive_gate_tier regressed: a static spawner-wave must derive L1 "
        f"(got {derived!r}). P1 relies on the between-wave advance being L1."
    )

    text = HARNESS_DOC.read_text(encoding="utf-8")
    sec = _section_84(text)
    # The derivation bullet pairs a tier with the literal `spawn_class == spawner-wave`.
    m = re.search(r"\*\*(L[012])\*\*[^\n]*spawn_class == spawner-wave", sec)
    assert m, (
        "workflow-harness.md §8.4: no '**L?** ... spawn_class == spawner-wave' derivation "
        "line found. The SSOT must state the spawner-wave gate tier explicitly."
    )
    assert m.group(1) == derived, (
        f"workflow-harness.md §8.4 says spawner-wave => {m.group(1)} but "
        f"_derive_gate_tier says {derived}. The SSOT and the code must agree."
    )


def test_wave_registry_tier_matches_derivation_and_i18n_unchanged():
    """R2 (companion): the registry default_gate_tier must equal the derivation for
    odoo-wave (now L1), while an instance-touching non-wave skill (odoo-i18n) stays L2.

    Fails if: the registry <-> derivation lockstep breaks for odoo-wave, or the
    reordering accidentally lowered a genuine instance-touching skill from L2.
    """
    import json

    reg = json.loads(
        (PLUGIN / "generator" / "skill_tool_deps.json").read_text(encoding="utf-8")
    )["orchestration"]

    wave = reg["odoo-wave"]
    wave_expected = _derive_gate_tier(
        wave["spawn_class"], bool(wave.get("instance_touching")),
        wave["output_mode"], bool(wave.get("outward")),
    )
    assert wave_expected == "L1", f"odoo-wave should derive L1, got {wave_expected!r}"
    assert wave["default_gate_tier"] == wave_expected, (
        f"odoo-wave registry default_gate_tier={wave['default_gate_tier']!r} "
        f"but derivation says {wave_expected!r} - they must move in lockstep."
    )

    i18n = reg["odoo-i18n"]
    i18n_expected = _derive_gate_tier(
        i18n["spawn_class"], bool(i18n.get("instance_touching")),
        i18n["output_mode"], bool(i18n.get("outward")),
    )
    assert i18n_expected == "L2", (
        f"odoo-i18n must stay L2 via instance_touching, got {i18n_expected!r} - "
        "the spawner-wave reordering must NOT lower a genuine instance-touching skill."
    )
    assert i18n["default_gate_tier"] == i18n_expected == "L2"
