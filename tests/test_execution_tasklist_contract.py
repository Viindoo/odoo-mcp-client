"""Behavior gate for the always-on, live execution task-list contract.

Root cause this protects (see investigation notes for the fix): the native task board
(`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`) already had exactly the wiring an executor needs
to surface its own sequential progress (run-harness over RUN-DAG nodes, workflow-chaining over
phases, odoo-planning's downstream executor, odoo-coder over its work-items) - but it was gated on
the SAME experimental CHP capability probe built for a different problem (tracking OTHER named,
SendMessage-addressable teammates). Reusing that gate for an executor's OWN solo progress checklist
meant the one instruction that would give a human a live checklist never fired unless an unrelated
experimental env var happened to be set.

The fix: `snippets/execution-tasklist-contract.md` is a NEW, always-on SSOT - fires whenever a
task-list tool is available in the executor's own toolset, independent of Agent Team mode / the CHP
probe / SendMessage. It explicitly is NOT the same surface as the durable blackboard (`run-<id>.json`,
written only by run-harness), the worklog (the durable *why* journal), or the CHP-gated
teammate-status layer (agent-team-protocol.md Ask 2, which tracks OTHER named subagents).

These assertions protect the CONTRACT'S BEHAVIOR (always-on; distinguished from the three other
surfaces; cross-referenced by every consumer) - not a wording snapshot. Each can fail for a real
reason: gate the contract behind CHP again, blur it with the blackboard/worklog, or drop a
consumer's cross-reference, and the corresponding assertion goes red.

Run: python -m pytest tests/test_execution_tasklist_contract.py -v
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

CONTRACT_MD = PLUGIN / "snippets" / "execution-tasklist-contract.md"
RUN_HARNESS_MD = PLUGIN / "skills" / "run-harness" / "SKILL.md"
WORKFLOW_CHAINING_MD = PLUGIN / "skills" / "workflow-chaining" / "SKILL.md"
ODOO_PLANNING_MD = PLUGIN / "skills" / "odoo-planning" / "SKILL.md"
ODOO_CODER_MD = PLUGIN / "agents" / "odoo-coder.md"


def _norm(path: Path) -> str:
    """Whitespace-normalized file text so phrase checks survive line wrapping."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_contract_file_exists():
    """The always-on live task-list contract must exist as its own SSOT snippet."""
    assert CONTRACT_MD.is_file(), (
        "snippets/execution-tasklist-contract.md must exist as the SSOT for the live, "
        "in-session execution task-list contract"
    )


def test_contract_is_always_on_not_experimental_gated():
    """The contract must fire whenever a task-list tool is available - explicitly NOT gated on the
    experimental Agent Team mode / CHP capability probe / SendMessage, unlike teammate-status
    tracking."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "independent of" in low and (
        "experimental agent team mode" in low or "chp capability probe" in low
    ), "the contract must state it fires independent of the experimental CHP/Agent-Team gate"
    assert "do not gate this on any experimental flag" in low or "do not gate" in low, (
        "the contract must explicitly forbid gating this on an experimental flag"
    )


def test_contract_distinguishes_blackboard_worklog_and_teammate_tracking():
    """The contract must explicitly name and distinguish itself from the three other coordination
    surfaces so no consumer conflates them: the durable blackboard (run-<id>.json), the durable
    worklog, and the CHP-gated teammate-status task board (agent-team-protocol.md Ask 2)."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "blackboard" in low and "run-<id>.json" in text, (
        "the contract must distinguish itself from the durable blackboard"
    )
    assert "worklog" in low and "worklog-contract.md" in text, (
        "the contract must distinguish itself from the durable worklog"
    )
    assert "agent-team-protocol.md" in text and "ask 2" in low, (
        "the contract must distinguish itself from the CHP-gated teammate-status tracking "
        "(agent-team-protocol.md Ask 2)"
    )
    assert "mirror" in low, (
        "the live list must be stated to MIRROR the blackboard's state, never redefine it"
    )


def test_contract_degrades_silently_when_no_tool_available():
    """When no task-list tool exists in the toolset, the executor must degrade silently (proceed
    without one) rather than error or block."""
    text = _norm(CONTRACT_MD).lower()
    assert "degrade silently" in text or "silently" in text, (
        "the contract must state it degrades silently when no task-list tool is available"
    )


def test_run_harness_cites_the_always_on_contract_for_its_own_node_checklist():
    """run-harness's own sequential RUN-DAG-node checklist must fire independent of the CHP probe -
    separate from (and cross-referencing, not restating) its teammate-status tracking, which stays
    CHP-gated."""
    text = _norm(RUN_HARNESS_MD)
    assert "execution-tasklist-contract.md" in text, (
        "run-harness must cross-reference the execution-tasklist-contract SSOT"
    )
    low = text.lower()
    assert "independent of agent team mode" in low or (
        "independent of" in low and "chp capability probe" in low
    ), "run-harness must state its own node checklist is independent of the CHP gate"


def test_workflow_chaining_cites_the_always_on_contract_for_its_phase_checklist():
    """workflow-chaining must track its own phase-by-phase progress via the same always-on
    contract, independent of Agent Team mode."""
    text = _norm(WORKFLOW_CHAINING_MD)
    assert "execution-tasklist-contract.md" in text, (
        "workflow-chaining must cross-reference the execution-tasklist-contract SSOT"
    )
    assert "independent of agent team mode" in text.lower(), (
        "workflow-chaining must state its phase checklist is independent of Agent Team mode"
    )


def test_odoo_planning_cross_reference_matches_the_corrected_gate():
    """odoo-planning's note about the downstream execution task list must point at the corrected,
    always-on contract - not restate the old CHP-only condition as if it still solely gated it."""
    text = _norm(ODOO_PLANNING_MD)
    assert "execution-tasklist-contract.md" in text, (
        "odoo-planning must cross-reference the execution-tasklist-contract SSOT"
    )
    low = text.lower()
    assert "independent of the chp capability probe" in low or "independent of" in low, (
        "odoo-planning's cross-reference must reflect that the execution task list is "
        "independent of the CHP capability probe (that gate applies only to teammate-status "
        "tracking, a separate layer)"
    )


def test_odoo_coder_cites_the_contract_for_its_own_wi_checklist():
    """The odoo-coder per-module coordinator must track its own dispatched work-items on a live
    task list per the always-on contract, not only via the CHP-gated Ask-1 SendMessage push."""
    text = _norm(ODOO_CODER_MD)
    assert "execution-tasklist-contract.md" in text, (
        "odoo-coder must cross-reference the execution-tasklist-contract SSOT for its WI checklist"
    )
