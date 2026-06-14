"""Protect the concurrency-guard SSOT and odoo-coding's model-weighted dispatch (issue #59).

Business contract under protection (behavior-first, ETHOS #11):
1. The OOM fan-out rule lives in EXACTLY ONE place
   (skills/_shared/concurrency-guard.md) with two modes: Mode A (legacy cap-3
   Agent-tool batching) and Mode B (model-weighted budget, incl. the weight
   table haiku/sonnet/opus/fable).
2. Every fan-out skill references that SSOT instead of restating the numbers.
3. odoo-coding dispatches the coders via Agent-tool model-weighted batches (the
   JS Workflow dispatch engine was removed to kill the args-undefined crash
   class): it must NOT regress to the legacy fixed "fire 3, wait" barrier, and
   its gate table carries an explicit model column with all four tiers.

These tests fail when the rule is duplicated again, when a skill drops its
pointer, or when the fixed fire-3 barrier regresses back into odoo-coding.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "plugins" / "odoo-ai-agents" / "skills"
GUARD = SKILLS_DIR / "_shared" / "concurrency-guard.md"

FANOUT_SKILLS = [
    "odoo-coding",
    "odoo-debug",
    "odoo-code-review",
    "wave",
    "workflow-chaining",
    "odoo-brl",
]


def _skill_text(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def test_concurrency_guard_ssot_exists_with_both_modes():
    assert GUARD.is_file(), "SSOT file skills/_shared/concurrency-guard.md is missing"
    text = GUARD.read_text(encoding="utf-8")
    assert "Mode A" in text, "SSOT must define Mode A (legacy cap-3 batching)"
    assert "Mode B" in text, "SSOT must define Mode B (model-weighted budget)"
    # The weight table is the load-bearing data of Mode B.
    for model, weight in (("haiku", "1"), ("sonnet", "2"), ("opus", "4"), ("fable", "8")):
        assert re.search(rf"\|\s*{model}\s*\|\s*{weight}\s*\|", text), (
            f"SSOT weight table must pin {model}={weight}"
        )


def test_every_fanout_skill_references_the_ssot():
    for name in FANOUT_SKILLS:
        assert "concurrency-guard.md" in _skill_text(name), (
            f"{name}/SKILL.md must point at the concurrency-guard SSOT "
            "instead of restating the OOM rule"
        )


def test_failure_log_name_not_restated_by_pointerized_skills():
    # The failure-log citation lives ONLY in the SSOT - executing agents need
    # the rule, not the tracker name; every fan-out skill carries a pointer.
    for name in FANOUT_SKILLS:
        assert "unbounded-opus-fanout-oom" not in _skill_text(name), (
            f"{name}/SKILL.md restates the failure log name - reference "
            "concurrency-guard.md instead"
        )
    assert "unbounded-opus-fanout-oom" in GUARD.read_text(encoding="utf-8")


def test_odoo_coding_has_no_fire3_batch_barrier():
    # The legacy fixed "fire 3, wait" barrier must not regress. odoo-coding now
    # dispatches via Agent-tool model-weighted batches (Mode B budget <=8); that
    # weighted batch is the sanctioned model after the JS dispatch engine was
    # dropped - the only thing forbidden here is the old fixed-3 barrier.
    assert "fire 3, wait" not in _skill_text("odoo-coding"), (
        "odoo-coding regressed to the fixed fire-3-wait batch barrier"
    )


def test_odoo_coding_gate_table_has_model_column_with_all_tiers():
    text = _skill_text("odoo-coding")
    assert re.search(r"\|\s*module\s*\|\s*stack\s*\|\s*wave\s*\|\s*model\s*\|", text), (
        "odoo-coding gate table must carry a model column"
    )
    # Anchor each tier to a row of the deterministic tier table (| # | ... | **tier** |),
    # not to incidental mentions elsewhere in the file.
    for tier in ("haiku", "opus", "fable"):
        assert re.search(rf"\|\s*\d\s*\|.*\|\s*\*\*{tier}\*\*\s*\|", text), (
            f"odoo-coding tier table must have a row resolving to the {tier} tier"
        )
    assert re.search(r"\|\s*\d\s*\|.*\|\s*\*\*sonnet\*\*\s*\(default\)\s*\|", text), (
        "odoo-coding tier table must keep sonnet as the explicit default row"
    )


def test_odoo_coding_passes_model_explicitly():
    text = _skill_text("odoo-coding")
    # Single dispatch path (Agent tool): the brief pins the tier in its first
    # line AND every Agent-tool call sets the `model` parameter (belt and braces,
    # mirroring odoo-debug). Drop the DISPATCH MODEL line and this goes red.
    assert "DISPATCH MODEL:" in text, (
        "odoo-coding Agent-tool dispatch must set the DISPATCH MODEL prompt line "
        "(mirroring odoo-debug)"
    )
