"""Behavioral gates for the odoo-instance subsystem hardening (v4.9.0).

Three coherent contracts are locked in by these read-only prose assertions:

  ITEM 4 - active-wait on long builds. A long -i/-u/--test-enable build can exceed
           the foreground Bash tool timeout; the odoo-instance-ops agent MUST launch
           it in the background and poll LOG_PATH to a TERMINAL marker (never
           idle-stall). The skill relays a short form of the same contract.

  ITEM 2 - subagent self-provision via Skill(odoo-instance). A dispatched leaf that
           lacks an INSTANCE_HANDLE self-provisions by invoking Skill(odoo-instance)
           (which carries the HARD RULES), NEVER by a bare allocator.py call - the
           bypass that would skip those rules. (The depth-cap-motivated "never
           launch odoo-instance-ops directly" coercion was removed in a later wave -
           whichever path the caller's context uses to provision, the HARD RULES
           apply either way.) HARD RULES stay single-sourced in the agent
           (cross-referenced, not duplicated).

  ITEM 5 (gap fix) - the odoo-coder / odoo-frontend-coder CODER agents were missed by
           ITEM 2: their own no-handle self-provisioning fallback (the backend lint
           gate's isolated instance, the frontend quick-smoke server) still called
           `scripts/lib/allocator.py acquire` directly, bypassing the same HARD RULES
           the coders' own lint/smoke gate depends on (crucially the lint-module
           install union). Fixed to route through Skill(odoo-instance), like every
           other self-provisioning leaf.

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

def test_skill_is_single_owner_with_inline_and_launch_paths():
    """The skill is the single owner of instance provisioning and offers the caller EITHER path -
    run the ops steps inline in its own context, or launch the odoo-instance-ops agent - with no
    coercion toward one over the other (the old "sole launcher" / depth-cap framing was removed;
    the skill still owns launching the agent when that path is chosen)."""
    text = _norm(SKILL_MD)
    assert "Single owner of instance provisioning" in text, (
        "skill must state it is the single owner of instance provisioning"
    )
    assert "Inline leaf-mode" in text, "skill must define an inline leaf-mode provisioning path"
    assert "launch the `odoo-instance-ops` agent" in text or "launching that agent" in text, (
        "skill must still document launching odoo-instance-ops as a provisioning path"
    )
    assert "component that owns launching that agent" in text, (
        "skill must own launching odoo-instance-ops when that path is chosen"
    )


def test_skill_inline_mode_honors_hard_rules():
    """Inline leaf-mode is not a bypass - however the operation is carried out, it honors the SAME
    HARD RULES as launching the agent."""
    text = _norm(SKILL_MD)
    assert "SAME HARD RULES" in text, "inline leaf-mode must state it honors the same HARD RULES"
    assert "not a bypass" in text.lower(), "the inline path must be stated as not a bypass"


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


def test_qa_tester_no_handle_fallback_routes_via_odoo_instance_skill():
    """odoo-qa-tester's no-handle fallback provisions via Skill(odoo-instance) - carrying the HARD
    RULES - never a raw allocator.py call."""
    text = _norm(QA_TESTER_MD)
    assert "Skill(odoo-instance)" in text, "qa-tester must self-provision via Skill(odoo-instance)"
    assert "HARD RULES" in text, "qa-tester's provisioning must be stated as carrying the HARD RULES"
    assert "raw" in text.lower() and "allocator.py" in text, (
        "qa-tester must forbid a raw allocator.py call as the self-provisioning fallback"
    )


def test_coding_skill_no_handle_fallback_routes_to_inline_skill():
    """odoo-coding's no-handle fallback = Skill(odoo-instance) inline-mode, never a bare allocator call."""
    text = _norm(CODING_MD)
    assert text.count("Skill(odoo-instance)") >= 2, (
        "both coding self-provision spots must route via Skill(odoo-instance) inline-mode"
    )
    assert "never a bare" in text, "coding must forbid a bare allocator.py call as the fallback"


def test_handle_contract_no_handle_fallback_routes_via_odoo_instance_skill():
    """The instance-handle contract's no-handle fallback self-provisions via Skill(odoo-instance)
    under the HARD RULES; whichever provisioning path is used, a provided handle always wins."""
    text = _norm(HANDLE_CONTRACT)
    assert "Skill(odoo-instance)" in text, (
        "the no-handle fallback must self-provision via Skill(odoo-instance)"
    )
    assert "provided handle always wins" in text, "a provided handle must still always win"


def test_worker_brief_permits_odoo_instance_skill_carveout():
    """worker-brief permits a leaf to invoke Skill(odoo-instance) to self-provision (carrying the
    instance HARD RULES), while the INDEPENDENT git-ops-via-Skill prohibition for leaves remains
    intact - a leaf never owns git, regardless of the instance carve-out."""
    text = _norm(WORKER_BRIEF)
    low = text.lower()
    assert "Skill(odoo-instance)" in text, "worker-brief must permit the odoo-instance Skill"
    assert "HARD RULES" in text, (
        "the carve-out must justify itself via the instance HARD RULES, not a depth argument"
    )
    assert "leaf never" in low and "invokes git-ops even via the skill tool" in low, (
        "the git-ops-via-Skill prohibition must remain intact"
    )


def test_evals_retarget_to_single_owner_never_bare_allocator():
    """Evals assert the new rule: whichever path a caller provisions through (inline or by launching
    odoo-instance-ops), it must never bypass the HARD RULES via a bare allocator.py call. A direct
    launch of odoo-instance-ops is no longer, by itself, a failure - only bypassing the HARD RULES
    (e.g. a bare allocator.py call) is."""
    data = json.loads(EVALS.read_text(encoding="utf-8"))
    evals = {e["id"]: e for e in data["evals"]}

    # id 6 - orchestrator dispatch still routes through the skill; the failure is bypassing the
    # HARD RULES or calling allocator.py directly, not "launching the agent directly" per se.
    assert evals[6]["expected_routed_to"] == "odoo-instance"
    assert "allocator.py" in evals[6]["must_not"] or "hard rules" in evals[6]["must_not"].lower(), (
        "id 6 must forbid bypassing the HARD RULES / calling allocator.py directly"
    )

    # id 11 - leaf self-provision under the HARD RULES; must NOT call allocator.py directly.
    # (Cold-spawning odoo-instance-ops from a leaf is a separate, tool-capability concern - a hard
    # leaf structurally lacks the launch mechanism - not something this eval's must_not encodes.)
    assert 11 in evals, "a leaf self-provisioning eval (id 11) must exist"
    e11 = evals[11]
    assert e11["expected_routed_to"] == "odoo-instance"
    assert "hard rules" in e11["expected_behavior"].lower(), (
        "id 11's expected behavior must invoke the instance HARD RULES"
    )
    assert "allocator.py" in e11["must_not"], (
        "id 11 must forbid a direct allocator.py call that bypasses the HARD RULES"
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


def test_lead_coder_owns_integrated_instance_test_via_odoo_instance_skill():
    """The odoo-coder per-module LEAD owns the INTEGRATED whole-module instance test. No-handle -> it
    self-provisions via Skill(odoo-instance), which the lead may run either inline in its own context
    or by launching odoo-instance-ops - either way under the instance HARD RULES."""
    text = _norm(CODER_MD)
    low = text.lower()
    assert "Skill(odoo-instance)" in text, (
        "the lead must run/provision the integrated module test via Skill(odoo-instance)"
    )
    assert "integrated" in low, "the lead must own the INTEGRATED whole-module test"
    assert "HARD RULES" in text, (
        "provisioning must be stated as carrying the instance HARD RULES"
    )
    assert "inline in your own context" in low or "inline in" in low, (
        "the lead may provision inline in its own context"
    )
    assert "odoo-instance-ops" in text, (
        "the lead may alternatively provision by launching the odoo-instance-ops agent"
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


# ---------------------------------------------------------------------------
# BLOCKER fix - dispatch-path run/session-ownership + db_port carrier
#
# INSTANCE_HANDLE grew db_port + run_id (instance-handle-contract.md) so a multi-turn
# orchestrator can drop/release the right instance on the right Postgres port under the
# right owner. The INLINE path already carried them via $ALLOC_DB_PORT/$ALLOC_RUN_ID, but
# the DISPATCH path (odoo-instance-ops's canonical output block + the odoo-instance skill's
# relay/forward list) had no channel for either field - the orchestrator could not read them
# back off a dispatched agent. Fixed by adding both fields to the agent's canonical block and
# the skill's relayed schema + enumerated forwarding list.
# ---------------------------------------------------------------------------

def test_agent_canonical_output_block_carries_db_port_and_run_id():
    """odoo-instance-ops's canonical output block must add db_port + run_id fields, and the
    surrounding prose must instruct populating them from the acquire result ($ALLOC_DB_PORT /
    $ALLOC_RUN_ID) - the dispatch path was previously missing this carrier entirely."""
    text = _norm(AGENT_MD)
    assert "db_port: <resolved port or empty>" in text, (
        "canonical output block must add a db_port field"
    )
    assert "run_id: <owning run id or empty>" in text, (
        "canonical output block must add a run_id field"
    )
    assert "populate them from Step D's acquire result" in text, (
        "agent must instruct populating db_port/run_id from the acquire result"
    )
    assert "`db_port` from `$ALLOC_DB_PORT`" in text and "`run_id` from `$ALLOC_RUN_ID`" in text, (
        "agent must map db_port from $ALLOC_DB_PORT and run_id from $ALLOC_RUN_ID explicitly"
    )


def test_skill_relay_forwards_db_port_and_run_id():
    """odoo-instance SKILL.md's relay/forward section must carry db_port + run_id in BOTH the
    relayed fenced schema and the enumerated forwarding list - matching the inline path's
    $ALLOC_DB_PORT/$ALLOC_RUN_ID and instance-handle-contract.md's field names, so the
    orchestrator has a channel to read them off the dispatch path too."""
    text = _norm(SKILL_MD)
    assert "db_port: <resolved port or empty>" in text, (
        "relayed instance-ops schema must add a db_port field"
    )
    assert "run_id: <owning run id or empty>" in text, (
        "relayed instance-ops schema must add a run_id field"
    )
    assert "forwards it (`dbname` / `http_port` / `db_port`" in text, (
        "the enumerated forwarding list must include db_port"
    )
    assert "`lease_token` / `run_id`" in text, (
        "the enumerated forwarding list must include run_id"
    )


def test_handle_contract_field_names_match_agent_and_skill():
    """Cross-file consistency: db_port and run_id field names in the agent's canonical block and
    the skill's relay must match instance-handle-contract.md's SSOT field names (no drift)."""
    contract_text = _norm(HANDLE_CONTRACT)
    assert "`db_port`" in contract_text and "`run_id`" in contract_text, (
        "instance-handle-contract.md must be the SSOT declaring db_port + run_id"
    )
    agent_text = _norm(AGENT_MD)
    skill_text = _norm(SKILL_MD)
    for field in ("db_port", "run_id"):
        assert field in agent_text, f"agent canonical block must use contract field name {field!r}"
        assert field in skill_text, f"skill relay must use contract field name {field!r}"


def test_evals_case_11_uses_neutral_self_provision_framing():
    """Eval id 11 previously said 'Skill(odoo-instance) inline-mode' in expected_behavior while its
    tags said 'inline-leaf-mode' - a two-mode framing the SSOT skill collapsed (inline-mode and
    launching the agent are just two implementation options, not a leaf-forced special mode).
    Reworded to the neutral 'self-provision via Skill(odoo-instance) (runs in the caller's own
    context)', with tags matching."""
    data = json.loads(EVALS.read_text(encoding="utf-8"))
    e11 = {e["id"]: e for e in data["evals"]}[11]
    assert "via `Skill(odoo-instance)` (runs in the caller's own context)" in e11["expected_behavior"], (
        "eval 11's expected_behavior must use the neutral self-provision framing"
    )
    assert "inline-mode" not in e11["expected_behavior"], (
        "eval 11 must not name inline-mode as a leaf-specific forced mode"
    )
    assert "inline-leaf-mode" not in e11["tags"], (
        "eval 11's tags must not retain the stale inline-leaf-mode tag"
    )
    assert "self-provision" in e11["tags"], (
        "eval 11's tags must be reworded consistently with the neutral expected_behavior"
    )
