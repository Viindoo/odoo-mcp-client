"""Behavioral gates for the odoo-instance subsystem hardening (v4.9.0).

Three coherent contracts are locked in by these read-only prose assertions:

  ITEM 4 - active-wait on long builds. A long -i/-u/--test-enable build can exceed
           the foreground Bash tool timeout; the odoo-instance-ops agent MUST launch
           it in the background and poll LOG_PATH to a TERMINAL marker (never
           idle-stall). The skill relays a short form of the same contract.

  ITEM 2 - subagent self-provision via odoo-instance inline leaf-mode. A dispatched
           leaf that lacks an INSTANCE_HANDLE self-provisions by invoking
           Skill(odoo-instance) inline-mode (which carries the HARD RULES), NOT by a
           bare allocator.py call and NOT by cold-spawning odoo-instance-ops. HARD
           RULES stay single-sourced in the agent (cross-referenced, not duplicated).

  ITEM 5 (gap fix) - the odoo-coder / odoo-frontend-coder CODER agents were missed by
           ITEM 2: their own no-handle self-provisioning fallback (the backend lint
           gate's isolated instance, the frontend quick-smoke server) still called
           `scripts/lib/allocator.py acquire` directly, bypassing the same HARD RULES
           the coders' own lint/smoke gate depends on (crucially the lint-module
           install union). Fixed to route through Skill(odoo-instance) inline-mode,
           like every other self-provisioning leaf.

Prose is line-wrapped in the source, so every phrase assertion runs against a
whitespace-normalized copy of the file.

Run: python -m pytest tests/test_instance_ops_hardening.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SKILL_MD = PLUGIN / "skills" / "odoo-instance" / "SKILL.md"
AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"
QA_TESTER_MD = PLUGIN / "agents" / "odoo-qa-tester.md"
CODING_MD = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
CODER_MD = PLUGIN / "agents" / "odoo-coder.md"           # the per-module full-stack LEAD
BACKEND_CODER_MD = PLUGIN / "agents" / "odoo-backend-coder.md"  # the backend hard-leaf writer
FRONTEND_CODER_MD = PLUGIN / "agents" / "odoo-frontend-coder.md"
INSTANCE_RESOLUTION_MD = PLUGIN / "snippets" / "instance-resolution.md"
HANDLE_CONTRACT = PLUGIN / "snippets" / "instance-handle-contract.md"
WORKER_BRIEF = PLUGIN / "snippets" / "worker-brief.md"
EVALS = PLUGIN / "skills" / "odoo-instance" / "evals" / "evals.json"


def _norm(path: Path) -> str:
    """Whitespace-normalized file text so phrase checks survive line wrapping."""
    return " ".join(path.read_text(encoding="utf-8").split())


# ---------------------------------------------------------------------------
# ITEM 4 - active-wait contract
# ---------------------------------------------------------------------------

def test_agent_carries_active_wait_section():
    """odoo-instance-ops.md must own the active-wait-on-long-builds contract."""
    text = _norm(AGENT_MD)
    assert "Active-wait on long builds" in text, "agent must have the active-wait section"
    assert "run_in_background" in text, "agent must instruct a background launch"
    assert "never idle-stall" in text.lower(), "agent must forbid idle-stalling"
    assert "heartbeat" in text, "agent must emit a heartbeat between polls"


def test_agent_active_wait_names_terminal_markers():
    """The contract must name both success and failure terminal markers."""
    text = _norm(AGENT_MD)
    for success in ("Modules loaded.", "Registry loaded", "Initiating shutdown"):
        assert success in text, f"agent must name success marker {success!r}"
    for failure in ("Traceback (most recent call last):", "Failed to load registry"):
        assert failure in text, f"agent must name failure marker {failure!r}"


def test_agent_active_wait_exit_code_authoritative():
    """The build's exit code stays authoritative over a possibly-drifting marker."""
    text = _norm(AGENT_MD).lower()
    assert "exit code" in text and "authoritative" in text, (
        "agent must state the process exit code is authoritative over log markers"
    )


def test_agent_build_ops_cross_reference_active_wait():
    """create/init/update/run-tests each cross-reference the active-wait contract."""
    text = _norm(AGENT_MD)
    assert text.count('"Active-wait on long builds"') >= 4, (
        "each of create/init/update/run-tests must cross-reference the active-wait section"
    )


def test_skill_relays_active_wait_contract():
    """odoo-instance SKILL.md must relay a short form of the active-wait contract."""
    text = _norm(SKILL_MD)
    assert "Active-wait on long builds (relay)" in text, "skill must relay the wait contract"
    assert "background" in text and "LOG_PATH" in text, (
        "skill relay must mention background launch + LOG_PATH poll"
    )
    assert "Modules loaded." in text, "skill relay must name a success marker"


def test_skill_documents_log_level_warn_default():
    """The skill must document the warn default + escalation for build ops."""
    text = _norm(SKILL_MD)
    assert "--log-level=warn" in text, "skill must state the warn default for builds"
    assert "ESCALATE" in text, "skill must document escalation to info/debug"


def test_agent_self_review_covers_active_wait_and_log_level():
    """The agent self-review checklist must cover the wait + log-level rules."""
    text = _norm(AGENT_MD)
    assert "actively waited to a TERMINAL marker" in text, (
        "self-review must include the active-wait item"
    )
    assert "--log-level=warn" in text and "test` verb kept `--log-level=test`" in text, (
        "self-review must assert the warn default and that the test verb keeps --log-level=test"
    )


# ---------------------------------------------------------------------------
# ITEM 2 - inline leaf-mode self-provision
# ---------------------------------------------------------------------------

def test_skill_has_two_modes_dispatch_and_inline():
    """The skill relaxes sole-dispatcher into single-owner with dispatch + inline modes."""
    text = _norm(SKILL_MD)
    assert "Single owner of instance fan-out" in text, "skill must own instance fan-out (single owner)"
    assert "Dispatch mode" in text and "Inline leaf-mode" in text, (
        "skill must define both dispatch mode and inline leaf-mode"
    )
    assert "ONLY component that launches the `odoo-instance-ops` agent" in text, (
        "dispatch mode must remain the sole launcher of odoo-instance-ops"
    )


def test_skill_inline_mode_does_not_spawn_and_honors_hard_rules():
    """Inline leaf-mode runs inline (no agent spawn) and honors the SAME HARD RULES."""
    text = _norm(SKILL_MD)
    assert "does NOT dispatch `odoo-instance-ops`" in text or \
           "do NOT launch the `odoo-instance-ops` agent" in text, (
        "inline leaf-mode must NOT dispatch the ops agent"
    )
    assert "SAME HARD RULES" in text, "inline leaf-mode must state it honors the same HARD RULES"


def test_skill_inline_mode_cross_references_hard_rules_not_duplicated():
    """HARD RULES stay single-sourced in the agent - the skill cross-references, not restates."""
    text = _norm(SKILL_MD)
    assert "agents/odoo-instance-ops.md" in text
    assert "en_US - always loaded on every build" in text, (
        "inline-mode must point at the agent's en_US HARD-RULE section (SSOT)"
    )
    assert "to_base" in text and "Lint modules" in text, (
        "inline-mode must point at the to_base + lint-module HARD-RULE sections"
    )
    assert "do NOT restate them here" in text, (
        "inline-mode must explicitly avoid duplicating the HARD RULES"
    )


def test_qa_tester_no_handle_fallback_routes_to_inline_skill():
    """odoo-qa-tester's no-handle fallback = invoke Skill(odoo-instance) inline-mode, not raw allocator."""
    text = _norm(QA_TESTER_MD)
    assert "Skill(odoo-instance)" in text and "inline-mode" in text, (
        "qa-tester must self-provision via Skill(odoo-instance) inline-mode"
    )
    assert "SOLE EXCEPTION" in text, "qa-tester must carve out the odoo-instance Skill exception"
    assert "never spawn subagents" in text, (
        "qa-tester must still forbid spawning subagents (no raw odoo-instance-ops cold-spawn)"
    )


def test_coding_skill_no_handle_fallback_routes_to_inline_skill():
    """odoo-coding's no-handle fallback = Skill(odoo-instance) inline-mode, never a bare allocator call."""
    text = _norm(CODING_MD)
    assert text.count("Skill(odoo-instance)") >= 2, (
        "both coding self-provision spots must route via Skill(odoo-instance) inline-mode"
    )
    assert "never a bare" in text, "coding must forbid a bare allocator.py call as the fallback"


def test_handle_contract_no_handle_fallback_is_inline_skill():
    """The instance-handle contract's no-handle fallback is the inline skill route."""
    text = _norm(HANDLE_CONTRACT)
    assert "Skill(odoo-instance)" in text and "inline-mode" in text
    assert "provided handle always wins" in text, "a provided handle must still always win"


def test_worker_brief_permits_odoo_instance_skill_carveout():
    """worker-brief must add a carve-out that a leaf MAY invoke Skill(odoo-instance)."""
    text = _norm(WORKER_BRIEF)
    assert "Skill(odoo-instance)" in text, "worker-brief must permit the odoo-instance Skill"
    assert "a leaf never" in text and "invokes git-ops even via the Skill tool" in text, (
        "the git-ops-via-Skill prohibition must remain intact"
    )
    assert "no subagent" in text.lower() or "adds no nesting depth" in text, (
        "carve-out must justify itself as adding no subagent depth"
    )


def test_evals_retargeted_to_single_owner_and_inline_leaf():
    """Evals assert the new rule: leaf self-provisions via the skill, never raw-spawns the agent."""
    data = json.loads(EVALS.read_text(encoding="utf-8"))
    evals = {e["id"]: e for e in data["evals"]}

    # id 6 - orchestrator dispatch mode still routes through the skill, never a raw agent spawn.
    assert evals[6]["expected_routed_to"] == "odoo-instance"
    assert "raw agent" in evals[6]["must_not"] or "bypassing odoo-instance" in evals[6]["must_not"]

    # id 11 - leaf self-provision via inline-mode; must NOT cold-spawn the agent or call allocator.py.
    assert 11 in evals, "a leaf inline-mode self-provision eval (id 11) must exist"
    e11 = evals[11]
    assert e11["expected_routed_to"] == "odoo-instance"
    assert "inline" in e11["expected_behavior"].lower()
    assert "odoo-instance-ops" in e11["must_not"] and "allocator.py" in e11["must_not"], (
        "id 11 must forbid both raw agent cold-spawn AND a direct allocator.py call"
    )


# ---------------------------------------------------------------------------
# ITEM 5 (gap fix) - the CODER agents were missed by ITEM 2's inline-leaf sweep
# ---------------------------------------------------------------------------

def test_backend_coder_no_handle_fallback_routes_to_inline_skill():
    """odoo-backend-coder's no-handle self-provisioning (its bounded /test_lint gate) routes via
    Skill(odoo-instance) inline-mode, never a bare allocator.py acquire - the raw path used to skip
    the HARD RULES the lint gate (/test_lint + /test_pylint) depends on (lint modules must be
    INSTALLED). The backend WRITER (not the odoo-coder lead) owns this bounded lint gate."""
    text = _norm(BACKEND_CODER_MD)
    assert "Skill(odoo-instance)" in text and "Inline leaf-mode" in text, (
        "backend coder must self-provision via Skill(odoo-instance) inline-mode"
    )
    assert "Do NOT call `scripts/lib/allocator.py acquire` directly" in text, (
        "backend coder must forbid calling the raw allocator directly for its own provisioning"
    )
    assert "allocator.py acquire --series" not in text, (
        "backend coder must not carry a literal raw-allocator acquire recipe for self-provisioning"
    )
    assert "lint-module install union" in text, (
        "backend coder must explain why the raw allocator path was wrong: it skips the lint-module "
        "install union its own /test_lint+/test_pylint gate depends on"
    )
    # Preserved invariants from the fix brief.
    assert "INSTANCE_HANDLE precedence" in text, "INSTANCE_HANDLE precedence rule must survive"
    assert "Lint-only inline; a full suite delegates" in text, (
        "the lint-only-inline / full-suite-delegates split must survive"
    )
    assert "No instance reachable and none handed in" in text and "NEEDS_NEXT: odoo-instance" in text, (
        "the never-fake-a-pass / NEEDS_NEXT escalation rule must survive"
    )


def test_lead_coder_owns_integrated_instance_test_inline():
    """The odoo-coder per-module full-stack LEAD owns the INTEGRATED whole-module instance test, run
    via Skill(odoo-instance) INLINE leaf-mode (never dispatch-mode, which would spawn odoo-instance-ops
    one level deeper and overflow the depth cap). No-handle -> the lead self-provisions inline."""
    text = _norm(CODER_MD)
    assert "Skill(odoo-instance)" in text and "INLINE" in text.upper(), (
        "the lead must run the integrated module test via Skill(odoo-instance) inline-mode"
    )
    assert "integrated" in text.lower(), (
        "the lead must own the INTEGRATED whole-module test"
    )
    assert "NEVER dispatch-mode" in text or "never dispatch-mode" in text.lower(), (
        "the lead must forbid dispatch-mode (spawning odoo-instance-ops would overflow the depth cap)"
    )


def test_frontend_coder_is_instance_free_no_self_provision():
    """RETARGETED (coder-coordinator restructure): odoo-frontend-coder is now INSTANCE-FREE - it must
    NOT self-provision an Odoo instance at all. Its only gate is the static verify-frontend.sh; any
    live/instance-backed check is owned by the odoo-coder lead's integrated test (full-stack) or a
    delegated NEEDS_NEXT: odoo-instance run (frontend-only). It still consumes a handed-in
    INSTANCE_HANDLE and delegates full suites, but never acquires its own lease/server."""
    text = _norm(FRONTEND_CODER_MD)
    # Instance-free: no self-provision route via the odoo-instance skill, no bare allocator acquire.
    assert "Skill(odoo-instance)" not in text, (
        "frontend-coder must be INSTANCE-FREE - it must NOT invoke Skill(odoo-instance) to self-provision"
    )
    assert "allocator.py acquire" not in text, (
        "frontend-coder must not carry a raw-allocator acquire recipe (instance-free)"
    )
    assert "instance-free" in text.lower(), (
        "frontend-coder must state it is INSTANCE-FREE"
    )
    # Preserved: consume a handed-in handle, delegate full suites, and the static gate is the only gate.
    assert "INSTANCE_HANDLE precedence" in text, "INSTANCE_HANDLE precedence rule must survive"
    assert "A full JS suite delegates" in text and "NEEDS_NEXT: odoo-instance" in text, (
        "the full-JS-suite-delegates-via-NEEDS_NEXT rule must survive"
    )
    assert "verify-frontend.sh" in text, "the static verify-frontend.sh gate must remain the mandatory gate"


def test_instance_touching_coder_agents_do_not_spawn_a_subagent_for_instance_skill():
    """Invoking Skill(odoo-instance) is a Skill-tool call, not an Agent-tool spawn - the
    instance-touching coding agents (the odoo-backend-coder writer's lint gate and the odoo-coder
    lead's integrated test) stay INLINE (no subagent depth added), matching the worker-brief
    carve-out. (odoo-frontend-coder is instance-free and is covered by its own test above.)"""
    for path in (BACKEND_CODER_MD, CODER_MD):
        text = _norm(path)
        assert "adding no subagent depth" in text, (
            f"{path.name} must justify the Skill(odoo-instance) carve-out as adding no subagent depth"
        )


def test_instance_resolution_notes_skill_is_the_agent_entry_point():
    """instance-resolution.md's raw § Allocate recipe stays the mechanism odoo-instance's
    inline-mode uses internally; agents are pointed at the skill, not the recipe, up front."""
    text = _norm(INSTANCE_RESOLUTION_MD)
    assert "Skill(odoo-instance)" in text, (
        "instance-resolution.md must point agents at Skill(odoo-instance) rather than the raw recipe"
    )
    assert "INTERNALLY" in text, (
        "instance-resolution.md must state the recipe is used INTERNALLY by the skill's inline-mode"
    )
    assert "self-provision via" in text.lower() or "self-provision via" in text, (
        "instance-resolution.md must instruct agents to self-provision via the skill"
    )
    # The recipe itself must still be present (not deleted) - other callers still need it.
    assert "allocator.py acquire --series" in text, (
        "the low-level allocate recipe must remain intact for the skill's inline-mode to use"
    )
