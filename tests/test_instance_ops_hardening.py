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
LIFECYCLE_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-LIFECYCLE.md"


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


# ---------------------------------------------------------------------------
# P5 - instance port isolation (persist: field + owned lease + runtime cli_help
# port-flag resolution, never a hardcoded flag). See docs/reference/
# INSTANCE-ALLOCATION.md §5 and agents/odoo-instance-ops.md operation 1.
# ---------------------------------------------------------------------------

def test_skill_carries_persist_and_run_id_dispatch_fields():
    """skills/odoo-instance/SKILL.md must declare the persist:/run_id: dispatch
    fields (P5.1) - the caller-facing lifecycle/isolation choice and the
    lease-ownership identity, both threaded into the odoo-instance-ops brief."""
    text = _norm(SKILL_MD)
    assert "`persist`" in text and "ephemeral" in text and "exclusive-running" in text \
        and "shared-running" in text, (
        "SKILL.md dispatch table must declare persist: ephemeral|exclusive-running|shared-running"
    )
    assert "`run_id`" in text, "SKILL.md dispatch table must declare a run_id field"
    assert "PERSIST:" in text and "RUN_ID:" in text, (
        "SKILL.md's brief shape must thread PERSIST:/RUN_ID: into the odoo-instance-ops brief"
    )
    assert "never converges on `8069`" in text or "never converging on 8069" in text, (
        "SKILL.md must state exclusive-running never converges on the declared/8069 port"
    )


def test_agent_resolves_port_flag_at_runtime_never_hardcoded():
    """agents/odoo-instance-ops.md must instruct RUNTIME cli_help resolution of
    the port flag name - never a hardcoded flag - and must state the tie-break
    rule for when cli_help lists more than one candidate (P5.2 + refinement 1
    from 23-review-final.md Part 2)."""
    text = _norm(AGENT_MD)
    assert "FAST-PATH PRIOR only" in text, (
        "agent must state the per-version CLI table is a fast-path prior, not the SSOT"
    )
    assert "resolved at runtime via" in text and "cli_help" in text, (
        "agent must instruct runtime cli_help resolution of the port flag, not a hardcoded one"
    )
    assert "Port-flag tie-break" in text, "agent must carry the port-flag tie-break rule"
    assert "PREFER `--http-port` whenever `cli_help` lists it" in text, (
        "tie-break must prefer --http-port whenever cli_help lists it (xmlrpc-port only for v8-v10)"
    )
    assert "PREFER `--gevent-port` whenever `cli_help` lists it" in text, (
        "tie-break must prefer --gevent-port whenever cli_help lists it (longpolling-port only "
        "where gevent-port is absent)"
    )
    assert "NEVER pass a flag the target series' `cli_help` does not list" in text, (
        "tie-break must forbid passing a flag the target series' cli_help does not list at all"
    )


def test_agent_create_instance_is_one_persist_keyed_flow():
    """The old odoo-instance-ops.md contradiction - Step D's 'acquire a pooled
    port, --ports 1 to listen' (formerly :48/:71) vs create-instance's 'delegate
    to spinup; do NOT also acquire' (formerly :241-247) - must be reconciled
    into ONE persist:-keyed flow, not left as two divergent paths."""
    text = _norm(AGENT_MD)

    def _section(header_start: str, header_end: str) -> str:
        s = text.find(header_start)
        assert s != -1, f"section {header_start!r} not found"
        e = text.find(header_end, s + 1)
        return text[s: e if e != -1 else len(text)]

    create = _section("### 1. create-instance", "### 2. drop-instance")
    for mode in ("`persist: ephemeral`", "`persist: exclusive-running`", "`persist: shared-running`"):
        assert mode in create, f"create-instance must branch explicitly on {mode}"
    assert "--exclusive" in create, "the exclusive-running branch must pass --exclusive to spinup"
    assert "INST_RUN_ID" in create, "the shared-running branch must export INST_RUN_ID for spinup"
    assert "is ONE flow keyed on one field, not two independent" in text, (
        "the agent must state the reconciliation explicitly, not just perform it silently"
    )


def test_agent_exclusive_running_never_falls_back_to_8069():
    """The exclusive-running mechanism must state it never falls back to the
    declared/8069 port and BLOCKs instead when the allocator port is missing
    (P5.9 - the six 8069 fallbacks must not apply to this path)."""
    text = _norm(AGENT_MD)
    assert "NEVER converges on `8069`" in text or "NEVER converges on 8069" in text, (
        "agent must state exclusive-running never converges on the declared/8069 port"
    )
    assert "BLOCK rather than fall back to the declared/`8069` port" in text, (
        "agent must state the spinup delegation BLOCKs rather than silently falling back to 8069"
    )


# ---------------------------------------------------------------------------
# Instance readiness/completion detection fix - the historical hang under
# --log-level=warn (empty log -> a marker-only wait never terminates). The
# fix replaces log-tailing with deterministic signals: install/update job ->
# process exit + a forced completion marker + failure-marker scan; listening
# instance -> bounded HTTP port poll. SSOT: docs/reference/
# INSTANCE-LIFECYCLE.md item 14.
# ---------------------------------------------------------------------------

def test_agent_documents_log_handler_namespace_forcing():
    """odoo-instance-ops.md must document forcing --log-handler=<ns>.modules.
    loading:INFO onto init/update so 'Modules loaded.' survives the
    --log-level=warn baseline, and the openerp/odoo namespace split by
    version (v8-v9 vs v10+)."""
    text = _norm(AGENT_MD)
    assert "--log-handler=<ns>.modules.loading:INFO" in text, (
        "agent must document the --log-handler=<ns>.modules.loading:INFO forcing"
    )
    assert "openerp" in text and "v8-v9" in text, (
        "agent must name the openerp namespace for series < 10 (v8-v9)"
    )
    assert "odoo` for v10+" in text or "'odoo' for v10+" in text or "odoo` for v10+" in text.replace("'", "`"), (
        "agent must name the odoo namespace for v10+"
    )
    assert "v9->v10" in text or "v9 -> v10" in text, (
        "agent must name the v9->v10 boundary where the openerp->odoo namespace rename landed"
    )


def test_agent_documents_process_exit_completion_contract():
    """odoo-instance-ops.md must state that an install/update job's completion
    signal is PROCESS EXIT (never a log-tail wait), and that exit 0 alone is
    NOT proof of install (the silent-skip holes)."""
    text = _norm(AGENT_MD)
    assert "Deterministic completion contract" in text, (
        "agent must carry a named 'Deterministic completion contract' section"
    )
    assert "never a log-tail wait" in text.lower() or "never a log tail" in text.lower(), (
        "agent must explicitly forbid a log-tail wait for completion"
    )
    assert "exit 0" in text.lower() and (
        "not proof of install" in text.lower() or "is not proof" in text.lower()
    ), "agent must state exit 0 alone is NOT proof of install"
    for marker in (
        "invalid module names, ignored",
        "Some modules are not loaded",
        "Unmet dependenc",
        "cannot be installed",
    ):
        assert marker in text, f"agent must name the silent-skip failure marker {marker!r}"


def test_agent_documents_bounded_port_poll_for_listening_readiness():
    """odoo-instance-ops.md must state the LISTENING-instance readiness signal
    is a bounded HTTP port poll of /web/database/selector (fallback
    /web/login), never a log tail - distinct from the job-completion signal."""
    text = _norm(AGENT_MD)
    assert "/web/database/selector" in text, (
        "agent must name /web/database/selector as the primary readiness probe"
    )
    assert "/web/login" in text, "agent must name /web/login as the fallback probe"
    assert "BOUNDED" in text or "bounded" in text, (
        "agent must state the port poll is bounded (has a timeout)"
    )


def test_init_and_update_delegation_recipes_pass_version_flag():
    """The init-modules and update-modules delegation recipes must pass
    --version so the script can resolve the --log-handler namespace - the
    contract is inert without it being threaded through."""
    text = _norm(AGENT_MD)

    def _section(header_start: str, header_end: str) -> str:
        s = text.find(header_start)
        assert s != -1, f"section {header_start!r} not found"
        e = text.find(header_end, s + 1)
        return text[s: e if e != -1 else len(text)]

    init = _section("### 3. init-modules", "### 4. update-modules")
    update = _section("### 4. update-modules", "### 5. run-tests")
    for name, sec in (("init-modules", init), ("update-modules", update)):
        assert '--version "<series>"' in sec, (
            f"{name} must pass --version \"<series>\" to 55-instance-ops.sh"
        )


def test_lifecycle_doc_item14_documents_ready_detect_contract():
    """docs/reference/INSTANCE-LIFECYCLE.md must carry item 14 - the
    readiness/completion detection contract - naming both signal shapes."""
    text = _norm(LIFECYCLE_DOC)
    assert "Readiness/completion detection is DETERMINISTIC" in text, (
        "lifecycle doc must carry the readiness/completion detection item"
    )
    assert "PROCESS EXIT" in text, "lifecycle doc must name process exit as the job signal"
    assert "/web/database/selector" in text and "/web/login" in text, (
        "lifecycle doc must name the primary + fallback readiness endpoints"
    )


def test_skill_states_deterministic_signal_never_log_tail():
    """skills/odoo-instance/SKILL.md must state at dispatch level that the
    instance-up/job-done signal is deterministic, never a log tail."""
    text = _norm(SKILL_MD)
    assert "DETERMINISTIC" in text, (
        "skill must state the readiness/completion signal is deterministic"
    )
    assert "never a log tail" in text.lower() or "never a log-tail" in text.lower(), (
        "skill must state the signal is never a log tail"
    )
    assert "/web/database/selector" in text, (
        "skill must name /web/database/selector as the listening-readiness probe"
    )


# ---------------------------------------------------------------------------
# L1.5 - server_pid in the canonical instance handle, and --alloc-token
# threaded through the exclusive-running provisioning path so the spinup
# script's exclusive-branch pid-bind (allocator.py bind) actually fires.
# ---------------------------------------------------------------------------

def test_agent_canonical_output_block_carries_server_pid():
    """odoo-instance-ops.md's canonical instance-ops output block must add a
    server_pid field - the server's process-group id under setsid, null for
    --stop-after-init builds (which self-terminate)."""
    text = _norm(AGENT_MD)
    assert "server_pid: <pid or null>" in text, (
        "canonical output block must add a server_pid field"
    )
    assert "process-group id under setsid" in text.lower(), (
        "agent must document server_pid as the process-group id under setsid"
    )
    assert "--stop-after-init" in text and "self-terminate" in text, (
        "agent must state server_pid is null for --stop-after-init builds, which self-terminate"
    )


def test_handle_contract_declares_server_pid_optional_field():
    """instance-handle-contract.md must add server_pid as an OPTIONAL forwarded
    field, matching the agent's canonical block (SSOT: field names must not drift)."""
    text = _norm(HANDLE_CONTRACT)
    assert "`server_pid`" in text, "handle contract must declare server_pid"
    assert "optional" in text.lower(), "server_pid must be documented as optional"


def test_agent_exclusive_running_spinup_forwards_alloc_token():
    """The persist: exclusive-running provisioning path's 50-instance-spinup.sh
    invocation must forward the lease token Step D's acquire returned via
    --alloc-token, or the script's exclusive-branch pid-bind (allocator.py
    bind) silently never fires in production (_bind_exclusive no-ops when
    ARG_ALLOC_TOKEN is unset)."""
    text = _norm(AGENT_MD)

    def _section(header_start: str, header_end: str) -> str:
        s = text.find(header_start)
        assert s != -1, f"section {header_start!r} not found"
        e = text.find(header_end, s + 1)
        return text[s: e if e != -1 else len(text)]

    exclusive = _section(
        "**`persist: exclusive-running`**", "**`persist: shared-running`**"
    )
    assert "--alloc-token" in exclusive, (
        "the exclusive-running spinup invocation must pass --alloc-token"
    )
    assert '--alloc-token "$ALLOC_TOKEN"' in exclusive, (
        "the exclusive-running spinup invocation must forward the acquired lease "
        "token ($ALLOC_TOKEN, returned by Step D's allocator.py acquire) as --alloc-token"
    )
