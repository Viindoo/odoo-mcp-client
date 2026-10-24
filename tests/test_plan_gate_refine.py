"""A `refine` at the plan gate never re-dispatches a state-root-writing planner while Plan Mode is
open: a rejected ExitPlanMode leaves Plan Mode open, and every gate text says so in one voice."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
GATE_TEXTS = (
    PLUGIN / "skills/odoo-planning/SKILL.md",
    PLUGIN / "snippets/planning-gate-contract.md",
    PLUGIN / "skills/odoo-intake/references/plan-mode-schema.md",
)


def _squash(text):
    return re.sub(r"\s+", " ", text)


def test_every_gate_text_states_that_a_rejected_exit_leaves_plan_mode_open():
    for path in GATE_TEXTS:
        text = _squash(path.read_text(encoding="utf-8"))
        assert "leaves plan mode open" in text.lower() or "plan mode is still open" in text.lower(), path


def test_refine_never_relaunches_the_planner_before_approval():
    text = _squash((PLUGIN / "skills/odoo-planning/SKILL.md").read_text(encoding="utf-8"))
    refine = text[text.index("`refine: [feedback]` ->"):text.index("`approve` ->")]
    assert "re-dispatch" not in refine and "launch no writing agent" in refine
    assert "harness plan file" in refine
    # the planner rewrites the state-root plan once, after approval, before Phase P
    approve = text[text.index("`approve` ->"):text.index("`cancel` ->")]
    assert "resume the planner" in approve and "Phase P" in approve


def test_no_plugin_text_tells_the_owner_to_redispatch_the_planner_on_refine():
    for path in PLUGIN.rglob("*.md"):
        text = _squash(path.read_text(encoding="utf-8")).lower()
        assert "refine" not in text or "re-dispatch the planner" not in text, path
