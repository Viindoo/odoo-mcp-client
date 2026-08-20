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
import re
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
LIFECYCLE_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-LIFECYCLE-BUILD-CONTRACT.md"
INSTANCE_OPS_SH = PLUGIN / "scripts" / "setup-steps" / "55-instance-ops.sh"
RESOURCE_LIMITS_SNIPPET = PLUGIN / "snippets" / "odoo-bin-resource-limits.md"


def _norm(path: Path) -> str:
    """Whitespace-normalized file text so phrase checks survive line wrapping."""
    return " ".join(path.read_text(encoding="utf-8").split())


# ---------------------------------------------------------------------------
# Stale-claim scan universe
#
# The whole-tree scans below used to walk `plugins/**/*.md` only. `hooks/*.json` (the machine-
# readable registration a debugging agent reads FIRST, and therefore trusts most), `hooks/*.sh`
# (the headers that justify each hook) and the repo's own `tests/*.py` (whose section banners are
# read as the contract) were all unscanned - and that blind spot is exactly where superseded
# claims survived a rule change. Every negative/stale-claim scan takes this corpus.
# ---------------------------------------------------------------------------
_HOOKS_DIR = PLUGIN / "hooks"


def _rel(path: Path) -> str:
    """Repo-relative label for an offender, falling back to the absolute path. The fallback keeps
    these scans callable over a synthetic corpus (how their red-before-green proof drives them)
    instead of raising ValueError before the finding is ever reported."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _stale_claim_corpus(include_tests: bool = True) -> list[Path]:
    """Every agent-facing or maintainer-facing file a stale claim can hide in.

    `include_tests=False` is for a rule whose own prohibition guards live under `tests/` and must
    quote the banned shape to ban it - scanning those sources yields structural false positives,
    not findings."""
    self_path = Path(__file__).resolve()
    files = set((REPO_ROOT / "plugins").rglob("*.md"))
    files |= set(_HOOKS_DIR.glob("*.json")) | set(_HOOKS_DIR.glob("*.sh"))
    if include_tests:
        files |= set((REPO_ROOT / "tests").glob("*.py"))
    return sorted(p for p in files if p.resolve() != self_path)


def test_stale_claim_corpus_covers_the_historical_blind_spots():
    """Discovery floor for the scans below: silently dropping hooks/ or tests/ would make every
    stale-claim guard in this file vacuous - which is how the blind spot went unnoticed."""
    corpus = _stale_claim_corpus()
    assert _HOOKS_DIR / "hooks.json" in corpus, "hooks/hooks.json must be scanned"
    assert _HOOKS_DIR / "enforce-teardown.sh" in corpus, "hooks/*.sh must be scanned"
    assert any(p.suffix == ".py" and p.parent.name == "tests" for p in corpus), (
        "the repo's own tests/*.py must be scanned"
    )
    assert AGENT_MD in corpus and SKILL_MD in corpus, "plugin markdown must still be scanned"
    assert Path(__file__).resolve() not in corpus, (
        "the scanning file itself must be excluded - it has to be able to NAME the claims it bans"
    )
    no_tests = _stale_claim_corpus(include_tests=False)
    assert not any(p.suffix == ".py" for p in no_tests), (
        "include_tests=False must drop the tests corpus"
    )
    assert _HOOKS_DIR / "hooks.json" in no_tests and AGENT_MD in no_tests, (
        "include_tests=False must drop the tests corpus and NOTHING else"
    )


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
    """The contract must name success/progress and failure markers, and every
    marker it names must be one EVERY supported series can actually emit.

    `Registry loaded` is banned here on a source fact, not a style preference:
    that line was introduced at 15.0, so nine of the twelve supported series
    can never produce it - naming it as a progress signal tells the agent to
    wait for something that will never appear. The version-stable progress
    line is `loading <N> modules...` (INFO, byte-identical v8.0-v19.0)."""
    text = _norm(AGENT_MD)
    for success in ("Modules loaded.", "loading <N> modules...", "Initiating shutdown"):
        assert success in text, f"agent must name marker {success!r}"
    for failure in ("Traceback (most recent call last):", "Failed to load registry"):
        assert failure in text, f"agent must name failure marker {failure!r}"
    assert "Registry loaded" not in text, (
        "agent must NOT name `Registry loaded` as a marker - it does not exist "
        "before Odoo 15.0, so it can never appear on nine supported series"
    )


def test_agent_active_wait_distinguishes_test_verb_failure_markers_from_install_update():
    """The `test` verb's terminal-marker set is DIFFERENT and NARROWER than
    init/update's - naming both under one undifferentiated list is the exact
    prose/mechanism gap `55-instance-ops.sh`'s `_scan_build_markers` closed:
    for `test`, a per-test `FAIL:`/`ERROR:` marker (and the traceback that
    always follows it) is MID-RUN evidence, not completion - the suite keeps
    running past each one and the harness appends its own authoritative
    `TEST_RESULT=` line only once it finishes. An agent reading only an
    undifferentiated failure-marker list can end the wait at the first failing
    test - the exact stall the script now refuses to produce.

    Pre-fix RED: the contract listed `Traceback (most recent call last):` (and
    a bare ` ERROR ` token) as unconditional failure markers with no per-verb
    split, so a reader had no way to learn that the `test` verb treats them
    differently."""
    text = _norm(AGENT_MD)
    assert "NARROWER set" in text, (
        "agent must state that the `test` verb's failure-marker set is a "
        "narrower, different set from init/update's - not one shared list"
    )
    windows = _windows(text, re.compile(r"MID-RUN"), 400, 600)
    assert windows, "agent must name the MID-RUN (non-terminal) status of a per-test failure"
    assert any(
        "FAIL:" in w and "ERROR:" in w and "TEST_RESULT=" in w for w in windows
    ), (
        "the MID-RUN explanation must name the per-test FAIL:/ERROR: markers and point "
        "at the run's own TEST_RESULT= line as the real terminal signal"
    )
    assert "log-LEVEL column" in text and "NEVER key" in text, (
        "agent must forbid keying a marker scan on the ` ERROR ` log-LEVEL column for "
        "EITHER verb - Odoo logs at ERROR for reasons unrelated to the build, so a "
        "level-keyed match turns an unrelated line into a false terminal failure"
    )


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


def test_skill_documents_the_single_build_log_level_default():
    """The skill must state ONE build log-level default plus how to override it,
    and must not still claim the old quiet `warn` baseline anywhere.

    Scanned over the whole normalized file rather than one line: a stale claim
    that survives elsewhere in the document is exactly as misleading to a
    dispatching agent as the original."""
    text = _norm(SKILL_MD)
    assert "--log-level=info" in text, "skill must state the build default level"
    assert "log_mode" in text and "extra flags" in text, (
        "skill must name both override paths (log_mode for run-tests, extra flags otherwise)"
    )
    for stale in (
        "--log-level=warn` by DEFAULT",
        "runs at `--log-level=warn`",
        "quieter than Odoo's stock",
        "keeps `--log-level=test`",
    ):
        assert stale not in text, (
            f"skill still carries the superseded default claim {stale!r}"
        )


def test_agent_self_review_covers_active_wait_and_log_level():
    """The agent self-review checklist must cover the wait + log-level rules."""
    text = _norm(AGENT_MD)
    assert "actively waited to a TERMINAL marker" in text, (
        "self-review must include the active-wait item"
    )
    assert "--log-level=info" in text, (
        "self-review must assert the single build log-level default"
    )
    assert "--log-level=test" not in text, (
        "self-review must not assert a separate `test`-verb default - there is one default now"
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

def test_backend_coder_is_instance_free_no_self_provision():
    """RETARGETED (R7a - lint-class gates moved to run-harness's pre-PR tail): odoo-backend-coder is
    now INSTANCE-FREE, symmetric with odoo-frontend-coder - it must NOT self-provision an Odoo
    instance at all. Its own bounded checks (ORM-validation gate, inline review) need no instance;
    the CI-parity lint-class gate (/test_lint + /test_pylint) it used to self-provision for now runs
    ONCE, over the aggregate diff, at run-harness's pre-PR tail. Any live/instance-backed check is
    owned by the odoo-coder lead's integrated module test."""
    text = _norm(BACKEND_CODER_MD)
    assert "Skill(odoo-instance)" not in text, (
        "backend-coder must be INSTANCE-FREE - it must NOT invoke Skill(odoo-instance) to self-provision"
    )
    assert "allocator.py acquire" not in text, (
        "backend-coder must not carry a raw-allocator acquire recipe (instance-free)"
    )
    assert "instance-free" in text.lower(), (
        "backend-coder must state it is INSTANCE-FREE"
    )
    assert "ORM validation gate" in text or "ORM-validation gate" in text, (
        "the ORM-validation gate must survive - it needs no instance and is unrelated to lint"
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
    assert "forwards it (`db_name` / `http_port` / `db_port`" in text, (
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
# INSTANCE-ALLOCATION-MODES.md §5 and agents/odoo-instance-ops.md operation 1.
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


def _spinup_invocations(path: Path) -> list[str]:
    """Every SHELL INVOCATION of 50-instance-spinup.sh in one file, as one
    whitespace-collapsed string per invocation.

    Line-continuation aware on purpose: these commands are written one flag per
    line, so a check that only ever read the line naming the script would miss
    every flag on it. Prose that merely MENTIONS the script (including a sentence
    saying which flag it refuses) never lands here, because only the line that
    carries the script path - plus its backslash continuations - is collected."""
    lines = path.read_text(encoding="utf-8").splitlines()
    calls, i = [], 0
    while i < len(lines):
        if "50-instance-spinup.sh" in lines[i]:
            buf = [lines[i]]
            while buf[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                buf.append(lines[i])
            calls.append(" ".join(" ".join(buf).split()))
        i += 1
    return calls


def test_persist_ssot_names_the_acquire_mode_and_the_release_time_fate():
    """`persist:` is SKILL/AGENT vocabulary that MAPS onto the four allocator
    modes, and this file is the SSOT for that mapping. Both halves of the
    `exclusive-running` row are load-bearing:

    - the MODE the acquire must request, because the name suggests a fifth mode
      that does not exist (`--mode exclusive-running` exits 2), and
    - the RELEASE-TIME FATE, because the name promises persistence while the mode
      it maps to carries `drop_on_release: true`. A reader who takes the name at
      face value releases the lease and destroys a database it just built.

    Naming the mapping without naming the fate is the gap that costs the database,
    so this asserts both."""
    modes_doc = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-MODES.md"
    text = _norm(modes_doc)
    s = text.find("`persist: exclusive-running`")
    assert s != -1, "the persist SSOT must declare the exclusive-running value"
    e = text.find("`persist: exclusive-parked`", s + 1)
    row = text[s: e if e != -1 else len(text)]

    assert "allocator `ephemeral`" in row, (
        "the row must name the allocator mode the acquire requests"
    )
    assert "exclusive-running` is not a mode" in row or "not a mode at all" in row, (
        "the row must say that `--mode exclusive-running` is not a mode - the name is "
        "the whole reason a caller reaches for it"
    )
    assert "drop_on_release" in row and "DROPS" in row.upper(), (
        "the row must state that `release` DROPS this lease's database - the promise the "
        "value's NAME makes is the opposite, and only this sentence corrects it"
    )


def test_no_documented_spinup_invocation_passes_run_id():
    """50-instance-spinup.sh records ownership on NO path - the --exclusive
    lease was owner-stamped by the caller's acquire, and the shared/declared path
    reads INST_RUN_ID from the environment - so it REFUSES --run-id (exit 2).

    A documented invocation carrying that flag therefore does not merely mislead:
    it exits 2 before anything launches, which reads to an executing agent as a
    broken provisioning step. Scanned tree-wide rather than at the two known
    sites, because the same copy-paste lands anywhere a listening instance is
    documented. tests/ is excluded: the executable guard for the refusal has to
    PASS the banned flag in order to observe the exit code."""
    offenders, seen = [], 0
    for path in _stale_claim_corpus(include_tests=False):
        for call in _spinup_invocations(path):
            seen += 1
            if "--run-id" in call:
                offenders.append(f"{_rel(path)}: {call[:160]}")
    # Discovery floor: a scan that finds no invocation at all proves nothing, and a
    # reflowed command or a renamed script would silently make this vacuous.
    assert seen >= 3, (
        f"only {seen} spin-up invocation(s) found - the extractor stopped matching, so "
        "this guard is asserting over an empty set"
    )
    assert not offenders, (
        "50-instance-spinup.sh exits 2 on --run-id; these documented invocations would "
        "fail before launch:\n  " + "\n  ".join(offenders)
    )


def test_agent_exclusive_running_is_two_legs_with_the_three_handoff_invariants():
    """Nothing in this plugin installs modules AND leaves the server listening in
    one call: 55-instance-ops.sh init builds and exits, 50-instance-spinup.sh
    launches and installs nothing. So the isolated listening instance is TWO
    LEGS, and the agent that owns operation 1 must say so and issue both.

    It must also carry the three invariants of the handoff, because each fails
    while the port still answers HTTP 200 - so no probe, log or exit code catches
    any of them: WHICH allocator mode the acquire requests (and therefore whether
    `release` destroys the database), that both legs name the SAME database, and
    that the lease survives between the legs."""
    text = _norm(AGENT_MD)
    s = text.find("**`persist: exclusive-running`**")
    assert s != -1, "the exclusive-running branch must exist"
    e = text.find("**`persist: shared-running`**", s + 1)
    section = text[s: e if e != -1 else len(text)]

    assert "55-instance-ops.sh" in section and "50-instance-spinup.sh" in section, (
        "the exclusive-running branch must issue BOTH legs - the build verb and the "
        "listening verb - not the spin-up alone (which installs nothing)"
    )
    # Invariant 1: the mode, and the release-time consequence it decides.
    assert "mode `ephemeral`" in section or "--mode ephemeral" in section, (
        "the branch must NAME the allocator mode the acquire requests"
    )
    assert "drop_on_release" in section and "release" in section, (
        "the branch must state that this lease's database is DROPPED at release - the "
        "belief that `exclusive-running` means durable is what destroys a built database"
    )
    # Invariant 2: one database across both legs.
    assert "$ALLOC_DB_NAME" in section, (
        "both legs must be told to name the SAME acquired database"
    )
    # Invariant 3: the lease outlives the handoff.
    assert "between the legs" in section or "between leg 1 and leg 2" in section, (
        "the branch must forbid releasing/parking the lease between the two legs"
    )
    # The superseded instruction must be GONE, not left standing beside the new one.
    assert "Do NOT ALSO run `55-instance-ops.sh init`" not in text, (
        "the old single-leg instruction contradicts the two-leg contract and must be "
        "deleted, not merely supplemented"
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
# Instance readiness/completion detection. Completion is decided by
# deterministic signals, never by tailing a log: install/update job -> process
# exit + a REQUIRED completion marker + failure-marker scan; listening instance
# -> bounded HTTP port poll. The --log-handler=<ns>.modules.loading:INFO flag is
# the FLOOR that keeps the completion marker present at any level a caller may
# pass in --extra. SSOT: docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md item 14.
# ---------------------------------------------------------------------------

def test_agent_documents_log_handler_namespace_forcing():
    """odoo-instance-ops.md must document the --log-handler=<ns>.modules.
    loading:INFO floor on init/update that keeps 'Modules loaded.' on the log
    at any caller-chosen level, and the openerp/odoo namespace split by
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


def test_delegation_recipes_pass_version_flag():
    """Every delegation recipe whose script-side behavior is series-gated must
    pass --version - the gate is INERT if the recipe never threads it through.

    init/update need it to resolve the --log-handler namespace (openerp v8-v9
    vs odoo v10+); run-tests needs it so _parse_test_result picks the
    era-correct "the suite ran" marker instead of accepting either wording."""
    text = _norm(AGENT_MD)

    def _section(header_start: str, header_end: str) -> str:
        s = text.find(header_start)
        assert s != -1, f"section {header_start!r} not found"
        e = text.find(header_end, s + 1)
        return text[s: e if e != -1 else len(text)]

    init = _section("### 3. init-modules", "### 4. update-modules")
    update = _section("### 4. update-modules", "### 5. run-tests")
    run_tests = _section("### 5. run-tests", "### 6. ")
    for name, sec in (("init-modules", init), ("update-modules", update),
                      ("run-tests", run_tests)):
        assert '--version "<series>"' in sec, (
            f"{name} must pass --version \"<series>\" to 55-instance-ops.sh"
        )


def test_no_agent_or_doc_claims_a_quiet_or_empty_build_log():
    """No agent-facing file may still claim a successful build produces an
    EMPTY/near-empty log, or that completion lines get SUPPRESSED.

    Whole-tree, whitespace-normalized scan matched on the CLAIM shape rather
    than on one file or one sentence: the recurring failure mode here is a rule
    changing in its definition site while restatements elsewhere survive and
    then contradict it. Every phrase below described the old quiet baseline and
    is false under the current one - an agent that believes it would skip
    reading a log that now has real content. The corpus includes `hooks/*.json`,
    `hooks/*.sh` and `tests/*.py` - the three artifact classes this scan used to
    skip entirely."""
    stale_claims = (
        "produces an EMPTY log",
        "produces an empty log",
        "gets SUPPRESSED",
        "gets suppressed",
        "quieter than Odoo",
        "log-level=warn` build baseline",
        "log-level=warn baseline",
        "survives the `warn` baseline",
    )
    offenders = []
    for path in _stale_claim_corpus():
        text = _norm(path)
        for claim in stale_claims:
            if claim in text:
                offenders.append(f"{_rel(path)}: {claim!r}")
    assert not offenders, (
        "agent-facing prose still describes the superseded quiet-log baseline:\n  "
        + "\n  ".join(offenders)
    )


def test_lifecycle_doc_item14_documents_ready_detect_contract():
    """docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md must carry item 14 - the
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


# ---------------------------------------------------------------------------
# P1 - odoo-bin memory/time resource-limit hardening (Problem 1). Protects:
# "a big install fails cleanly / is capped, on EVERY version, and the caller
# can override or uncap it." Value RESOLUTION is tested separately in
# test_resource_limits.py; these tests protect the COMMAND-CONSTRUCTION
# contract - that each of the 3 build verbs actually WIRES the resolved
# values into the odoo-bin launch, with override precedence intact. Assert on
# PRESENCE + ORDERING, never the numeric default, so the default formula can
# change without a false failure here.
# ---------------------------------------------------------------------------

def _raw_section(text: str, header_start: str, header_end: str) -> str:
    """Like the per-test `_section` helpers above, but over RAW (non-whitespace-
    normalized) text - needed here because ordering/indentation of the actual
    shell command matters for the ulimit/--limit-memory-hard/${arg_extra}
    assertions below."""
    s = text.find(header_start)
    assert s != -1, f"section {header_start!r} not found"
    e = text.find(header_end, s + 1)
    return text[s: e if e != -1 else len(text)]


def test_instance_ops_sources_resource_limits_lib():
    """55-instance-ops.sh must source the resource-limit SSOT lib (never
    re-derive the hard-cap formula inline)."""
    text = INSTANCE_OPS_SH.read_text(encoding="utf-8")
    assert 'source "$LIB_DIR/resource_limits.sh"' in text, (
        "55-instance-ops.sh must source scripts/lib/resource_limits.sh"
    )


def test_instance_ops_verbs_wrap_odoo_bin_in_ulimit_and_hard_cap():
    """cmd_init/cmd_update/cmd_test must each wrap the odoo-bin launch in
    `ulimit -Sv` AND emit `--limit-memory-hard=` BEFORE `${arg_extra}` (override
    precedence: Odoo's arg parser takes the LAST occurrence of a repeated flag,
    so a caller-supplied override in --extra must still win).

    Ordering is checked against the ACTUAL CODE lines only (a literal,
    unquoted `${arg_extra}` standing alone on its own line, and the literal
    `--limit-memory-hard="$_lim_bytes"` flag construction) - prose comments
    in this file legitimately mention both tokens in either order while
    explaining the rule, so a bare substring search would false-positive on
    a comment sentence instead of the real command line."""
    text = INSTANCE_OPS_SH.read_text(encoding="utf-8")

    init = _raw_section(text, "cmd_init() {", "cmd_update() {")
    update = _raw_section(text, "cmd_update() {", "cmd_test() {")
    test_verb = _raw_section(text, "cmd_test() {", "cmd_drop() {")

    hard_flag_re = re.compile(r'^[ \t]+--limit-memory-hard="\$_lim_bytes"', re.MULTILINE)
    arg_extra_line_re = re.compile(r'^[ \t]+\$\{arg_extra\}[ \t]*\\?[ \t]*$', re.MULTILINE)

    for name, section in (("cmd_init", init), ("cmd_update", update), ("cmd_test", test_verb)):
        assert "ulimit -Sv" in section, f"{name} must wrap the odoo-bin launch in ulimit -Sv"
        assert "resource_limit_is_uncapped" in section, (
            f"{name} must honor the uncapped escape hatch (skip ulimit when the resolved "
            "cap is 0/empty)"
        )
        hard_match = hard_flag_re.search(section)
        extra_match = arg_extra_line_re.search(section)
        assert hard_match, f"{name} must emit the code line --limit-memory-hard=\"$_lim_bytes\""
        assert extra_match, f"{name} must still pass ${{arg_extra}} through as its own code line"
        assert hard_match.start() < extra_match.start(), (
            f"{name}: --limit-memory-hard= must appear BEFORE ${{arg_extra}} so a caller "
            "override supplied via --extra still wins"
        )


def test_instance_ops_verbs_scope_ulimit_to_a_subshell():
    """The `ulimit -Sv` call must be scoped to a subshell wrapping ONLY the
    odoo-bin invocation, never applied to the calling shell at large (which
    would silently tighten every later command in the same script run).

    Matched against the ACTUAL CODE line (not the prose comment above it,
    which also legitimately says "ulimit -Sv" while explaining the rule)."""
    text = INSTANCE_OPS_SH.read_text(encoding="utf-8")
    init = _raw_section(text, "cmd_init() {", "cmd_update() {")
    update = _raw_section(text, "cmd_update() {", "cmd_test() {")
    test_verb = _raw_section(text, "cmd_test() {", "cmd_drop() {")
    ulimit_code_re = re.compile(
        r'^[ \t]+resource_limit_is_uncapped \|\| ulimit -Sv', re.MULTILINE
    )
    for name, section in (("cmd_init", init), ("cmd_update", update), ("cmd_test", test_verb)):
        ulimit_match = ulimit_code_re.search(section)
        assert ulimit_match, f"{name}: expected the code line `resource_limit_is_uncapped || ulimit -Sv ...`"
        open_paren_idx = section.rfind("(\n", 0, ulimit_match.start())
        assert open_paren_idx != -1, (
            f"{name}: ulimit -Sv must be inside a scoped `(` subshell, not the bare script body"
        )


def test_resource_limits_snippet_documents_the_policy():
    """snippets/odoo-bin-resource-limits.md must exist and document the
    canonical default, the v12 enforcement boundary, the uncapped escape
    hatch, and the override-precedence rule - other files point at it rather
    than restating command text."""
    assert RESOURCE_LIMITS_SNIPPET.exists(), (
        "snippets/odoo-bin-resource-limits.md must exist as the P1 SSOT policy doc"
    )
    text = _norm(RESOURCE_LIMITS_SNIPPET)
    assert "ODOO_AI_LIMIT_MEMORY_HARD" in text, "snippet must name the override env var"
    assert "4 GiB" in text or "4294967296" in text, "snippet must state the 4 GiB floor"
    assert "v12" in text, "snippet must document the v12.0 enforcement boundary"
    assert "uncapped" in text.lower(), "snippet must document the uncapped escape hatch"
    assert "limit_time_cpu" in text and "dead" in text.lower(), (
        "snippet must state limit_time_cpu is a dead key while workers=0"
    )


def test_spinup_conf_sources_resource_limits_lib_and_references_snippet():
    """50-instance-spinup.sh must source the same resource-limit SSOT lib
    (never a second, independent formula for the A2 conf keys)."""
    step50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
    text = step50.read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/../lib/resource_limits.sh"' in text, (
        "50-instance-spinup.sh must source scripts/lib/resource_limits.sh"
    )


# ---------------------------------------------------------------------------
# LIVE-RUN DEFECT 1 - the agent idle-stalled instead of driving the blocking
# mechanism that already existed.
#
# Observed twice in one run: odoo-instance-ops launched a build with
# `run_in_background: true`, then ENDED ITS TURN on a text-only "waiting for
# the background test run to complete" reply while odoo-bin had already exited
# and the log already held its terminal marker. A third case lost the launching
# shell (reaped before it printed its own STATUS=/TEST_RESULT= line) while the
# orphaned odoo-bin ran to completion.
#
# The mechanism was never missing: `55-instance-ops.sh wait-log` genuinely
# BLOCKS in one foreground Bash call and returns BUILD_RESULT=success|failure|
# timeout. What was missing was the INSTRUCTION SHAPE around it:
#   (a) it was named as "prefer the deterministic helper" - advisory, so an
#       agent could legally not use it;
#   (b) it was never told apart from the `run_in_background: true` pattern one
#       line above, so backgrounding the WAIT (which returns instantly with no
#       BUILD_RESULT) read as compliant;
#   (c) the harness's own generic Bash guidance ("if waiting for a background
#       task you will be notified - do not poll") was never overridden, and an
#       agent following that generic default correctly ends its turn - and
#       stalls, because no notification resumes a dispatched agent's ended turn;
#   (d) skills/odoo-instance/SKILL.md's relay dropped the mechanism NAME
#       entirely, so the two statements of one contract disagreed.
#
# The pre-fix guards above assert only that phrases EXIST. These assert the
# instruction SHAPE, over whitespace-normalized text, so a reworded regression
# still fails: a concrete invocation (not a bare mention), a mandate rather
# than a preference, a foreground requirement, an explicit override of the
# harness default, a ban on the text-only turn end, and agreement between the
# two files.
# ---------------------------------------------------------------------------

# A real INVOCATION of the blocking helper - `wait-log` followed by its
# required --log argument (a bare "the wait-log helper" mention does not
# satisfy this, which is exactly how the skill relay passed pre-fix).
_WAIT_CALL_RE = re.compile(r"wait-log\s+(?:\\\s*)?--log", re.IGNORECASE)

# Any wording that turns a required next action into an option. Matched near
# the call only, so ordinary uses elsewhere in the file are not swept in.
_HEDGE_RE = re.compile(
    r"\b(prefer|prefers|preferably|preferred|ideally|optional|optionally|"
    r"recommended|if possible|may want|consider using)\b",
    re.IGNORECASE,
)
_NEGATED_HEDGE_RE = re.compile(r"\b(never|not|no longer|instead of)\b\s*$", re.IGNORECASE)

# The mandate family: any of these makes the next action non-negotiable.
_MANDATE_RE = re.compile(
    r"\b(MANDATORY|MUST|VERY NEXT|never optional|non-negotiable|required)\b",
    re.IGNORECASE,
)

# A prohibition on backgrounding THIS call. The prohibition must attach to the
# tool parameter or to the wait itself ("WITHOUT run_in_background", "never
# backgrounding that call") - a nearby sentence that merely happens to negate
# some other "background" noun ("not a poll of a background task") must NOT
# satisfy it, or removing the real ban would go unnoticed.
_BACKGROUND_BAN_RE = re.compile(
    r"\b(never|not|without|no|do NOT)\b[^.]{0,60}?"
    r"(run_in_background|background(?:ing)?\s+(?:this|that|it|the\s+wait|the\s+call))",
    re.IGNORECASE,
)

# The harness's own generic default, and an explicit override of it.
_HARNESS_DEFAULT_RE = re.compile(
    r"(do not poll|don't poll|never poll|will be notified|you will be notified|notification)",
    re.IGNORECASE,
)
_OVERRIDE_RE = re.compile(
    r"(overrid|override|does not apply|do not apply|supersede|takes precedence)",
    re.IGNORECASE,
)

# The forbidden OUTPUT SHAPE - the thing the agent actually did. "never
# idle-stall" (pre-fix) is an abstraction an agent can believe it is obeying
# while emitting exactly this; the contract must name the shape.
_TURN_END_SHAPE_RE = re.compile(
    r"(text-only|tool-call-free|no tool call|end(?:ing|s)? (?:your|its|the) turn|"
    r"turn end|\"waiting\"|waiting for the (?:background|build))",
    re.IGNORECASE,
)
_PROHIBITION_RE = re.compile(
    r"\b(never|not|must not|forbid|forbids|forbidden|is the idle-stall|disallow)\b",
    re.IGNORECASE,
)

_ACTIVE_WAIT_FILES = (
    ("agents/odoo-instance-ops.md", AGENT_MD),
    ("skills/odoo-instance/SKILL.md", SKILL_MD),
)


def _windows(text: str, pattern: re.Pattern, before: int, after: int) -> list[str]:
    """Every window of `text` around a match of `pattern`, for proximity checks."""
    return [
        text[max(0, m.start() - before): m.end() + after]
        for m in pattern.finditer(text)
    ]


def _active_wait_contract(path: Path) -> str:
    """The active-wait contract SECTION of a file, whitespace-normalized.

    Scoped to the section rather than to a byte window around the call: the
    call and the sentence that governs it drift apart whenever the paragraph is
    reflowed, while an unrelated `(optional)` in a nearby Inputs list must never
    be mistaken for hedging. Both files label the contract identically, which
    the agreement test below also relies on."""
    raw = path.read_text(encoding="utf-8")
    start = raw.find("Active-wait on long builds")
    assert start != -1, f"{path.name}: the active-wait contract label is missing"
    nxt = raw.find("\n## ", start + 1)
    end = min(nxt if nxt != -1 else len(raw), start + 6000)
    return " ".join(raw[start:end].split())


def _unnegated_hedges(window: str) -> list[str]:
    """Hedge words in `window` that are NOT themselves negated ("not a
    preference" / "never optional" are mandates, not hedges)."""
    out = []
    for m in _HEDGE_RE.finditer(window):
        lead = window[max(0, m.start() - 24): m.start()]
        if not _NEGATED_HEDGE_RE.search(lead):
            out.append(m.group())
    return out


def test_active_wait_names_a_concrete_blocking_call_not_a_bare_mention():
    """Both statements of the contract must name the blocking call as a CALL -
    `wait-log --log <path>` - so an executing agent has something to run.

    Pre-fix RED: the skill relay mentioned `wait-log` only while describing
    which marker set it shares with the script, never as an invocation, so an
    agent reading the relay had no named mechanism for the wait at all."""
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        assert _WAIT_CALL_RE.search(text), (
            f"{rel}: must name the blocking helper as an invocation with its --log "
            "argument (a bare 'the wait-log helper' mention is not an instruction)"
        )


def test_active_wait_is_mandatory_and_never_hedged_into_an_option():
    """The blocking call must be stated as required, and no un-negated hedge
    may govern it.

    Two halves on purpose: the presence half fails if the mandate is deleted,
    the absence half fails if hedging vocabulary comes back in ANY of its
    forms. Pre-fix RED on both: the call was introduced with "prefer the
    deterministic helper" and carried no mandate token in its vicinity."""
    for rel, path in _ACTIVE_WAIT_FILES:
        assert _windows(_norm(path), _WAIT_CALL_RE, 400, 400), (
            f"{rel}: no blocking call found to check (see previous test)"
        )
        contract = _active_wait_contract(path)
        assert _MANDATE_RE.search(contract), (
            f"{rel}: the foreground wait must be stated as MANDATORY/MUST/your VERY "
            "NEXT call - an advisory mechanism is what let the agent skip it"
        )
        hedged = _unnegated_hedges(contract)
        assert not hedged, (
            f"{rel}: hedging vocabulary governs the blocking call again ({hedged}) - "
            "it must read as a required next action, not a preference"
        )


def test_active_wait_requires_the_foreground_and_bans_backgrounding_the_wait():
    """The wait must be told apart from the background LAUNCH one step above
    it: stated as foreground, and with backgrounding it explicitly forbidden.

    Pre-fix RED: the only `run_in_background` instruction was the positive one
    for the launch, and nothing said the wait itself must not be backgrounded -
    so carrying the launch pattern forward into the wait (which returns
    instantly with no BUILD_RESULT) read as compliant."""
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        near = _windows(text, _WAIT_CALL_RE, 500, 700)
        assert any("foreground" in w.lower() for w in near), (
            f"{rel}: the wait must be stated as a FOREGROUND call"
        )
        assert any(_BACKGROUND_BAN_RE.search(w) for w in near), (
            f"{rel}: backgrounding the wait itself must be explicitly forbidden "
            "(a backgrounded wait returns instantly with no BUILD_RESULT)"
        )


def test_active_wait_explicitly_overrides_the_harness_do_not_poll_default():
    """Both files must name the harness's own generic Bash guidance ("you will
    be notified - do not poll") AND override it for this call.

    This is the collision that produced the observed transcript: given a
    prominent generic default and a merely advisory plugin rule, the agent
    picked the generic one and ended its turn. Pre-fix RED: neither file
    referenced that default at all, so there was nothing to override."""
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        near = _windows(text, _WAIT_CALL_RE, 900, 1400)
        assert any(_HARNESS_DEFAULT_RE.search(w) for w in near), (
            f"{rel}: must name the harness's generic do-not-poll / you-will-be-notified "
            "default at the point of the wait"
        )
        assert any(
            _HARNESS_DEFAULT_RE.search(w) and _OVERRIDE_RE.search(w) for w in near
        ), (
            f"{rel}: must state that the harness default is OVERRIDDEN / does not apply "
            "for this call - naming it without overriding it leaves the collision intact"
        )


def test_a_text_only_turn_end_before_a_terminal_verdict_is_forbidden():
    """The contract must forbid the OUTPUT SHAPE the agent actually produced -
    a tool-call-free "waiting for the build" reply that ends the turn - not
    only the abstraction "never idle-stall".

    Pre-fix RED: both files forbade "idle-stalling" and "returning before a
    terminal marker" without ever naming a text-only turn end, which is what
    the agent emitted while believing it was compliant."""
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        shapes = _windows(text, _TURN_END_SHAPE_RE, 220, 220)
        assert shapes, (
            f"{rel}: must name the forbidden response shape (a text-only / tool-call-free "
            "reply that ends the turn while the build verdict is unknown)"
        )
        assert any(_PROHIBITION_RE.search(w) for w in shapes), (
            f"{rel}: the text-only turn end must be FORBIDDEN, not merely described"
        )


def test_the_two_statements_of_the_wait_contract_agree():
    """The agent file and the skill relay must state the SAME mechanism.

    The original divergence was exactly this: the agent named `wait-log`, the
    relay did not, so a reader of the front door learned there was a poll to
    perform but never what to call. Any future edit that upgrades one file and
    forgets the other fails here, naming both sides."""
    carried = {}
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        near = _windows(text, _WAIT_CALL_RE, 900, 1400)
        carried[rel] = {
            "invocation": bool(near),
            "foreground": any("foreground" in w.lower() for w in near),
            "mandate": any(_MANDATE_RE.search(w) for w in near),
            "override": any(
                _HARNESS_DEFAULT_RE.search(w) and _OVERRIDE_RE.search(w) for w in near
            ),
        }
    for aspect in ("invocation", "foreground", "mandate", "override"):
        holders = [rel for rel, got in carried.items() if got[aspect]]
        assert len(holders) == len(carried), (
            f"the two statements of the active-wait contract disagree on {aspect!r}: "
            f"carried by {holders}, missing from "
            f"{[r for r in carried if r not in holders]} - one file stating the "
            "mechanism while the other omits it is the original divergence"
        )


def test_a_reaped_launcher_is_never_read_as_a_pass():
    """The third observed case: the backgrounded launching shell was reaped
    before printing its own STATUS=/TEST_RESULT= line while odoo-bin ran to
    completion. The agent must never synthesize the missing verdict line.

    Pre-fix RED: no file mentioned the possibility, so the only guidance
    ("never stop at BUILD_RESULT=success without confirming the script's own
    STATUS= line") was unsatisfiable and left the outcome to improvisation."""
    text = _norm(AGENT_MD)
    assert re.search(r"reap(?:ed|s)?\b", text, re.IGNORECASE), (
        "the agent must handle the launcher shell being reaped before it printed "
        "STATUS=/TEST_RESULT="
    )
    window = _windows(text, re.compile(r"reap(?:ed|s)?\b", re.IGNORECASE), 320, 520)
    assert any(
        re.search(r"\b(never|not|must not)\b[^.]{0,120}?(synthes|invent|assume|pass)",
                  w, re.IGNORECASE)
        for w in window
    ), (
        "a reaped launcher must be stated as NEVER a pass and the missing verdict "
        "line must never be synthesized"
    )
    assert any(
        ("inconclusive" in w.lower() or "BLOCKED" in w) and "LOG_PATH" in w
        for w in window
    ), (
        "the reaped-launcher branch must name the terminal status to report and "
        "require LOG_PATH be forwarded"
    )


def test_build_timeout_is_re_invoked_not_turned_into_a_turn_end():
    """`BUILD_RESULT=timeout` must drive another foreground wait, with a stated,
    evidence-based stop condition - not a turn end and not an unbounded loop.

    Pre-fix RED: the contract's only timeout branch was "report BLOCKED", so
    every build longer than one wait window BLOCKED instead of completing, and
    nothing told the agent it could wait again."""
    text = _norm(AGENT_MD)
    windows = _windows(text, re.compile(r"BUILD_RESULT=timeout|timeout", re.IGNORECASE), 260, 900)
    assert any(
        re.search(r"re-?invoke|re-?run|again|repeat", w, re.IGNORECASE)
        and "BUILD_PROGRESS" in w
        for w in windows
    ), (
        "a timeout verdict must instruct re-invoking the same foreground wait, with "
        "the BUILD_PROGRESS reading as the evidence for whether to continue"
    )
    assert any(
        re.search(r"BLOCKED", w)
        and "BUILD_PROGRESS" in w
        and re.search(r"identical|unchanged|stopped progress|no longer",
                      w, re.IGNORECASE)
        for w in windows
    ), (
        "the stop condition must be evidence-based (a non-empty BUILD_PROGRESS "
        "repeated across a whole window), not a bare clock, and must resolve to BLOCKED"
    )


def test_the_stall_rule_names_the_field_that_actually_advances():
    """The stall rule is only true if the evidence it compares MOVES while the
    build works.

    `BUILD_MARKER` alone does not qualify as the rule's subject: on a test build
    the newest deciding line can repeat for a long time, and the field the script
    guarantees on EVERY poll - and guarantees to count real units of work - is
    `BUILD_PROGRESS`. Naming the wrong field is not a wording nit: with frozen
    evidence, two windows of a HEALTHY long suite read as "stopped progressing"
    and the run is abandoned as BLOCKED.

    Pre-fix RED: the contract's only stall rule was "`BUILD_MARKER` UNCHANGED
    from the previous one - that, not the clock, is the evidence the build
    stopped progressing", which is exactly the frozen-evidence rule.
    """
    for rel, path in _ACTIVE_WAIT_FILES:
        text = _norm(path)
        assert "BUILD_PROGRESS" in text, (
            f"{rel}: the wait contract must name BUILD_PROGRESS - the field a poll "
            "emits on every path and the only one that advances while a suite runs"
        )
        # The superseded rule must be DELETED, not left standing beside the new
        # one: a runtime agent that reads the old sentence first obeys it.
        #
        # Scanned SENTENCE by SENTENCE over the WHOLE file, not through a fixed
        # byte window forward from `BUILD_MARKER`. A bounded-adjacency window
        # goes green the moment the paragraph is reflowed or the stale sentence
        # is re-worded a few words longer, which is how a superseded rule
        # survives a sweep; and the stale claim can sit anywhere in the file,
        # not only after the token. The predicate is phrasing-independent: ANY
        # sentence that makes the stall decision (stop / BLOCKED / stopped
        # progressing) turn on BUILD_MARKER holding still is stale, whatever
        # words it uses for "holding still", unless that same sentence is about
        # BUILD_PROGRESS.
        stale_sentence = re.compile(
            r"BUILD_MARKER(?![_A-Z])"
            r"(?=[^.!?]*(?:unchanged|identical|same|repeat|not moved|no longer moves|"
            r"stopped progress|frozen|still))"
            r"(?=[^.!?]*(?:BLOCKED|stopped progress|stop waiting|give up|abandon))",
            re.IGNORECASE,
        )
        offenders = [
            s.strip() for s in re.split(r"(?<=[.!?]) ", text)
            if stale_sentence.search(s) and "BUILD_PROGRESS" not in s
        ]
        assert not offenders, (
            f"{rel}: a stall rule keyed on BUILD_MARKER holding still is still "
            "present - it must be replaced, not annotated. Offending sentence(s):\n"
            + "\n".join(offenders)
        )

    text = _norm(AGENT_MD)
    assert re.search(r"EMPTY[^.]{0,200}(NEVER|never)[^.]{0,120}BLOCKED", text), (
        "the contract must state that an EMPTY progress reading is the absence of "
        "evidence and never on its own grounds for BLOCKED"
    )
    assert re.search(r"(not a guarantee|could not separate|cannot separate)", text), (
        "the contract must say plainly where the stall rule stays unreliable - a "
        "single long-running test freezes a healthy run's reading - instead of "
        "implying a guarantee"
    )


def test_no_file_restates_the_completion_marker_as_the_success_rule_for_every_verb():
    """`Modules loaded.` certifies an install/update build and NOTHING else.

    Odoo logs that line BEFORE a `--test-enable` build's post-install suite
    starts, so on a test run it is PROGRESS - it cannot certify a tested build.
    A restatement that requires it for SUCCESS without saying which verb it
    governs is therefore wrong for run-tests, and a runtime agent that reads the
    unscoped sentence applies it to the verb in front of it.

    Scanned SENTENCE by SENTENCE across the WHOLE plugin corpus, not through an
    adjacency window: this exact claim already survived three sweeps precisely
    because it carried no distinctive keyword and sat far from the rule it
    contradicted. A sentence is only acceptable if it names the verb scope it
    applies to.

    Pre-fix RED: `skills/odoo-instance/SKILL.md` carried "The exit code stays
    authoritative for FAILURE while the `Modules loaded.` completion marker is
    still required for SUCCESS; run-tests reuses `TEST_RESULT=`" - one unscoped
    SUCCESS rule with the test verb tacked on as a footnote.
    """
    scoping = re.compile(
        r"init|update|create|install|-i\b|-u\b|not a test|test run|--test-enable",
        re.IGNORECASE,
    )
    offenders = []
    for path in sorted(PLUGIN.rglob("*.md")):
        text = _norm(path)
        if "Modules loaded." not in text:
            continue
        for sentence in re.split(r"(?<=[.!?]) ", text):
            if "Modules loaded." not in sentence:
                continue
            if not re.search(r"SUCCESS|required for|certif|proof of|confirms",
                             sentence, re.IGNORECASE):
                continue
            if scoping.search(sentence):
                continue
            offenders.append(f"{path.relative_to(PLUGIN)}: {sentence}")
    assert not offenders, (
        "a SUCCESS rule built on the `Modules loaded.` completion marker must name "
        "the verb it governs - unscoped, it certifies a --test-enable build whose "
        "suite never ran. Offending sentence(s):\n" + "\n".join(offenders)
    )


def test_the_lifecycle_reference_covers_a_test_enable_build_on_its_own_terms():
    """The completion-detection reference must have a row for a test build.

    A `--test-enable` build is `--stop-after-init`, so a reader splitting the
    world into "install/update job" and "listening instance" files it under the
    first - where BOTH halves of the rule are wrong for it: `Modules loaded.` is
    only progress there, and a lone traceback is per-test/incidental evidence
    rather than a failure marker.

    Pre-fix RED: item 14 named exactly two job shapes and listed `Traceback
    (most recent call last)` as an unconditional failure marker.
    """
    text = _norm(LIFECYCLE_DOC)
    anchor = re.search(r"Readiness/completion detection is DETERMINISTIC", text)
    assert anchor, "the completion-detection item is gone from the lifecycle reference"
    section = text[anchor.start(): anchor.start() + 4000]
    assert "--test-enable" in section, (
        "the completion-detection item names no test-build shape at all, so a "
        "--test-enable run (which IS --stop-after-init) reads as an install job, "
        "where both halves of the rule are wrong for it"
    )
    row = section[section.find("--test-enable"):]
    assert re.search(r"TEST_RESULT=", row), (
        "the test-build row must name the run's OWN TEST_RESULT= line as its "
        "completion signal"
    )
    assert re.search(r"Modules loaded\.[^.]{0,240}(only PROGRESS|progress|never certif|"
                     r"cannot certif|not certif)", row, re.IGNORECASE), (
        "the test-build row must say that `Modules loaded.` is only progress on a "
        "test run and cannot certify it"
    )
    assert re.search(r"[Tt]raceback[^.]{0,320}(NOT a failure|not a failure|MID-RUN|"
                     r"mid-run|per-test)", row), (
        "the test-build row must say a lone traceback is not a failure marker there - "
        "otherwise the install row's marker list is read as applying to it"
    )


def test_the_agent_is_told_an_empty_count_is_not_a_zero():
    """`TEST_FAILED=`/`TEST_ERROR=` can arrive EMPTY, and the agent must know.

    The script's own header documents "unmeasured, never 0" - but the agent never
    reads the script. Told only `TEST_FAILED=<n>`, it reports an absent
    measurement as a measured zero, which beside a `failed` verdict says the run
    failed and that nothing failed.

    Pre-fix RED: the agent described the fields as `TEST_FAILED=<n>` /
    `TEST_ERROR=<n>` with no empty case anywhere, and its checklist said
    "warnings>0 with no fail/error", which does not separate empty from zero.
    """
    text = _norm(AGENT_MD)
    assert re.search(r"TEST_FAILED[^.]{0,300}EMPTY", text) or re.search(
        r"EMPTY[^.]{0,300}TEST_FAILED", text), (
        "the agent is never told TEST_FAILED= can arrive EMPTY"
    )
    assert re.search(r"EMPTY[^.]{0,200}(never|NEVER|not)[^.]{0,80}(0|zero)", text), (
        "the agent must be told an EMPTY count is UNMEASURED and never a zero"
    )
    assert re.search(r"(EMPTY|unmeasured)[^.]{0,200}null", text, re.IGNORECASE), (
        "the agent must be told how to carry an EMPTY count into its output block "
        "(null, not 0)"
    )
    # The pass-with-warnings rung must not be reachable on an EMPTY count.
    checklist = [s for s in re.split(r"(?<=[.!?]) ", text)
                 if "tests-passed-with-warnings" in s]
    assert checklist, "the checklist must still gate tests-passed-with-warnings"
    assert any(re.search(r"EMPTY|measured", s) for s in checklist), (
        "the tests-passed-with-warnings rung must say an EMPTY fail/error count is "
        "not the evidence that nothing failed - as written, empty reads as zero"
    )


# ---------------------------------------------------------------------------
# LIVE-RUN DEFECT 2 - a per-module verdict silently covered other modules.
#
# Observed: a run-tests dispatch with GATE_ROLE: per-module-verify for one
# module ran UNSCOPED. Odoo's auto_install fan-out pulled in 63 modules and
# 1626 tests from the declared profile, including PRE-EXISTING failures in
# unrelated addon repos, and those failures decided the verdict of a run that
# was nominally verifying ONE module (whose real depends closure is two
# modules).
#
# The fix deliberately does NOT change scoping: auto-adding --test-tags or a
# skip-auto-install flag would suppress tests, manufacturing a false green -
# the exact defect class this release cycle removed. Instead the SCOPE becomes
# part of the verdict: the figures actually observed, plus an explicit
# statement when the verdict was decided outside the module under
# verification. These guards protect that contract, and protect against the
# suppression "fix" being introduced later.
# ---------------------------------------------------------------------------

# The grounded markers the figures come from - the script's own ran-marker SSOT
# (era-split at v14) and the version-stable module-loading progress line.
_MODULES_LOADED_MARKER_RE = re.compile(r"loading\s*<?N?\d*>?\s*modules", re.IGNORECASE)
_TESTS_RAN_MARKER_RE = re.compile(
    r"Ran\s*<?[TN]?\d*>?\s*tests?\s*in|of\s*<?[TN]?\d*>?\s*tests", re.IGNORECASE
)
_OUT_OF_SCOPE_RE = re.compile(r"out of scope|out-of-scope|outside the module|outside", re.IGNORECASE)
_SUPPRESSION_FLAG_RE = re.compile(r"--test-tags|test_tags|skip-auto-install|skip_auto_install")


def _run_tests_section(text: str) -> str:
    """The run-tests operation only, so a figure named elsewhere in the file
    (the active-wait marker list) cannot satisfy these assertions."""
    start = text.find("### 5. run-tests")
    assert start != -1, "run-tests section not found in the agent file"
    end = text.find("### 6. ", start + 1)
    return text[start: end if end != -1 else len(text)]


def test_run_tests_verdict_reports_the_scope_it_was_decided_on():
    """The run-tests contract must require the two figures actually observed -
    modules loaded and tests run - each read from THIS run's log via its
    grounded marker, so a caller can see the fan-out that decided the verdict.

    Pre-fix RED: the run-tests section reported TEST_RESULT= plus four counters
    and nothing about how many modules were installed or how many tests ran, so
    63 modules / 1626 tests looked identical to the one module requested."""
    section = _run_tests_section(_norm(AGENT_MD))
    assert _MODULES_LOADED_MARKER_RE.search(section), (
        "the run-tests verdict must require the count of modules ACTUALLY loaded, read "
        "from the log's own module-loading marker"
    )
    assert _TESTS_RAN_MARKER_RE.search(section), (
        "the run-tests verdict must require the count of tests ACTUALLY run, read from "
        "the era-correct ran-marker the script's own parser uses"
    )
    assert re.search(r"\bnotes\b", section, re.IGNORECASE), (
        "both figures must be wired into the existing output contract (the notes field), "
        "not left as a side remark"
    )
    assert re.search(r"unknown", section, re.IGNORECASE), (
        "a figure the log does not carry must be reported unknown - never estimated, "
        "never omitted"
    )


def test_run_tests_verdict_names_a_verdict_decided_outside_the_module():
    """When failures lie outside the module under verification, the report must
    say so explicitly, and the verdict must NOT soften.

    Pre-fix RED: nothing in the section distinguished an in-scope regression
    from a pre-existing failure in an unrelated addon, so a per-module gate
    reported another repo's failures as its own module's verdict."""
    section = _run_tests_section(_norm(AGENT_MD))
    assert _OUT_OF_SCOPE_RE.search(section), (
        "the verdict contract must name the out-of-scope case (a failing test whose "
        "module is not in this dispatch's --modules list)"
    )
    assert re.search(r"findings_path", section), (
        "the out-of-scope decision must be adjudicated from findings_path (the failing "
        "test names), not guessed"
    )
    assert re.search(
        r"(still\s+`?tests-failed`?|still BLOCKING|never softens|verdict itself never)",
        section, re.IGNORECASE,
    ), (
        "an out-of-scope failure must stay tests-failed and stay blocking - reporting it "
        "as out-of-scope must never become a downgrade"
    )


def test_run_tests_never_narrows_the_run_to_hide_the_fan_out():
    """The scope must be made VISIBLE, never suppressed: the contract must
    forbid auto-adding a tag filter or a skip-auto-install flag the caller did
    not ask for.

    This guards the tempting wrong fix. Suppressing tests to make a per-module
    gate quiet manufactures a false green, which is worse than a noisy one -
    paired with the presence assertions above so neither half can be dropped
    alone."""
    section = _run_tests_section(_norm(AGENT_MD))
    hits = [
        section[max(0, m.start() - 200): m.end() + 120]
        for m in _SUPPRESSION_FLAG_RE.finditer(section)
    ]
    assert hits, "the run-tests section must reference the scoping flags it must not auto-add"
    assert re.search(
        r"\b(never|not|do NOT|must not)\b[^.]{0,200}?"
        r"(--test-tags|test_tags|skip-auto-install|skip_auto_install)",
        section, re.IGNORECASE,
    ), (
        "the contract must FORBID auto-adding --test-tags / skip-auto-install the caller "
        "did not request - suppressing tests manufactures a false green"
    )
    assert re.search(r"false green|false-green", section, re.IGNORECASE), (
        "the reason the run is not narrowed must stay stated, so a later edit does not "
        "'optimize' the noise away"
    )


def test_canonical_output_block_notes_field_carries_the_scope_figures():
    """The reporting channel must be wired, not just described: the canonical
    output block's own notes field must say it always carries the scope figures
    on a run-tests dispatch.

    Pre-fix RED: notes was 'one-line summary of any non-obvious decision or
    error', which no agent would read as an obligation to report scope."""
    raw = AGENT_MD.read_text(encoding="utf-8")
    notes_lines = [ln for ln in raw.splitlines() if ln.startswith("notes:")]
    assert notes_lines, "canonical output block notes: field not found"
    assert any(
        re.search(r"scope", ln, re.IGNORECASE) for ln in notes_lines
    ), (
        "the canonical output block's notes field must state that a run-tests report "
        "always carries the scope figures"
    )


def test_skill_relays_the_scope_transparency_requirement():
    """The front door must relay the figures and the out-of-scope statement
    verbatim, must not narrow the run itself, and must point at the agent as
    the rule's SSOT rather than restating the decidable rule.

    Pre-fix RED: the skill had no scope concept at all, so a relayed verdict
    lost the fan-out even when the agent had measured it."""
    text = _norm(SKILL_MD)
    assert re.search(r"scope transparency", text, re.IGNORECASE), (
        "the skill must carry the scope-transparency relay"
    )
    assert re.search(r"auto_install", text), (
        "the relay must name the auto_install fan-out as the cause"
    )
    assert _OUT_OF_SCOPE_RE.search(text), (
        "the relay must require the out-of-scope statement to be passed through"
    )
    assert re.search(
        r"\b(never|not|do NOT|must not)\b[^.]{0,200}?"
        r"(test_tags|--test-tags|skip_auto_install|skip-auto-install)",
        text, re.IGNORECASE,
    ), (
        "the skill must forbid narrowing the run to hide the fan-out"
    )
    assert "odoo-instance-ops.md" in SKILL_MD.read_text(encoding="utf-8"), (
        "the decidable rule stays single-sourced in the agent - the skill points at it"
    )


# ---------------------------------------------------------------------------
# Allocator acquire: the two new exit codes, and the retired silent degradation.
#
# `allocator.py acquire` gained exit 6 (the database role positively LACKS
# CREATEDB) and exit 7 (the CREATEDB capability is UNDETERMINABLE), and
# `--mode ephemeral` can no longer silently degrade to `exclusive` - it either
# succeeds as ephemeral or fails writing no lease. An exit code an agent cannot
# ACT on is a stall waiting to happen, so each code must carry its remedy.
# ---------------------------------------------------------------------------


def _exit_code_window(text: str, code: str, before: int = 120, after: int = 700) -> list[str]:
    pattern = re.compile(r"(?:exit|code)\s*`?" + re.escape(code) + r"`?\b", re.IGNORECASE)
    return _windows(text, pattern, before, after)


def test_acquire_exit_6_carries_actions_not_just_a_meaning():
    """Exit 6 (role positively lacks CREATEDB) must name what to DO: get
    CREATEDB granted, or re-acquire exclusive while STATING that isolation was
    not provided, or pass --no-create.

    Pre-fix RED: the code did not exist in the prose, and the mode list instead
    promised a silent auto-degrade the allocator no longer performs."""
    text = _norm(AGENT_MD)
    windows = _exit_code_window(text, "6")
    assert windows, "the agent must document acquire exit 6"
    assert any("CREATEDB" in w for w in windows), (
        "exit 6 must be identified as the role positively lacking CREATEDB"
    )
    assert any(
        sum(
            bool(re.search(p, w, re.IGNORECASE))
            for p in (r"grant", r"--mode exclusive|exclusive", r"--no-create")
        ) >= 2
        for w in windows
    ), "exit 6 must name at least two of its three remedies (grant / exclusive / --no-create)"
    assert any(re.search(r"isolation", w, re.IGNORECASE) for w in windows), (
        "falling back to exclusive must require STATING that isolation was not provided - "
        "a silent fallback is how an unisolated run passes for an isolated one"
    )


def test_acquire_exit_7_carries_actions_and_names_its_three_causes():
    """Exit 7 (capability UNDETERMINABLE) must name its three causes - no
    declared python, the venv cannot import odoo, the cluster is unreachable -
    and resolve to a retry or NEEDS_CONTEXT, never a guess."""
    text = _norm(AGENT_MD)
    windows = _exit_code_window(text, "7")
    assert windows, "the agent must document acquire exit 7"
    assert any(
        re.search(r"undetermin", w, re.IGNORECASE) for w in windows
    ), "exit 7 must be identified as the capability being undeterminable"
    for cause in (r"python", r"import odoo", r"cluster"):
        assert any(re.search(cause, w, re.IGNORECASE) for w in windows), (
            f"exit 7 must name its cause {cause!r} so the agent knows what to resolve"
        )
    assert any(
        re.search(r"NEEDS_CONTEXT", w) and re.search(r"re-?acquire", w, re.IGNORECASE)
        for w in windows
    ), "exit 7 must resolve to a bounded retry then NEEDS_CONTEXT, never a guessed mode"


def test_no_prose_claims_ephemeral_silently_degrades_to_exclusive():
    """The retired behavior must be DELETED, and the replacement rule stated.

    An agent that believes `ephemeral` auto-degrades will read a shared
    declared DB as its own throwaway. Both halves asserted: the stale claim
    must be absent in any wording, AND the current rule (ephemeral never
    degrades; it succeeds or fails writing no lease) must be present, so
    deleting the rule cannot pass as 'no stale claim found'.

    Scope: the whole `plugins/**` tree PLUS `hooks/*.json` and `hooks/*.sh`,
    which this scan used to skip (it read exactly two hand-listed files).
    `tests/*.py` is deliberately NOT scanned for THIS claim: the repo's own
    prohibition guards for it live there and must quote the banned shape to ban
    it, so a tests scan reports its own guards. Consequence to close
    separately: `tests/test_allocator.py` still carries a stale
    'the allocator degrades to exclusive mode' note that no guard covers."""
    degrade = re.compile(
        r"(auto-?degrad\w*|degrad\w*|falls? back|fall back|downgrad\w*)", re.IGNORECASE
    )
    offenders = []
    for path in _stale_claim_corpus(include_tests=False):
        rel = _rel(path)
        text = _norm(path)
        for m in degrade.finditer(text):
            lead = text[max(0, m.start() - 30): m.start()]
            if re.search(r"\b(never|not|no longer|cannot|can no longer)\b", lead, re.IGNORECASE):
                continue  # a prohibition, not a claim
            tail = text[m.end(): m.end() + 90]
            if re.search(r"exclusive", tail, re.IGNORECASE):
                offenders.append(f"{rel}: {text[max(0, m.start() - 60): m.end() + 90]!r}")
    assert not offenders, (
        "prose still describes the retired silent ephemeral -> exclusive degradation:\n  "
        + "\n  ".join(offenders)
    )
    agent = _norm(AGENT_MD)
    assert re.search(
        r"ephemeral[^.]{0,40}$|NEVER degrades|never degrades", agent
    ) or re.search(r"never degrades to another mode", agent, re.IGNORECASE), (
        "the agent must state the current rule: ephemeral NEVER degrades to another mode"
    )
    assert re.search(r"fails? writing no lease|no lease is written", agent, re.IGNORECASE), (
        "the agent must state the failure shape: it either succeeds as ephemeral or fails "
        "writing no lease"
    )


# ---------------------------------------------------------------------------
# The DB-AUTH refusal wave: acquire gained exits 8 (Odoo cannot AUTHENTICATE to
# the cluster) and 9 (the cluster did not answer at all), both checked BEFORE
# 6/7 and for `--mode exclusive` as well as `ephemeral`.
#
# Every defect this section guards shipped at once, and every one of them
# survived review because no guard reached it: five files stated the refusal set
# as 6-and-7 only, one sentence handed a stopped cluster an authentication fix,
# `DB_AUTH=unknown` (the ONE state that must never block) was never stated to
# the agent, and the agent was told to report a Continuation-only status value
# into an output block whose enum has no such value.
# ---------------------------------------------------------------------------
SETUP_CMD_MD = PLUGIN / "commands" / "odoo-setup.md"
ALLOCATION_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-API.md"

# An exit-code ENUMERATION: a refusal/exit lead-in followed by two or more codes
# joined by any separator this repo's prose actually uses. Shape, not phrasing -
# "exit 6 or 7", "exits 6/7/8/9", "Exit **6, 7, 8 or 9**", "Acquire refusals -
# `6`, `7`, `8` and `9`" all match the same way.
_CODE = r"[`*\s:\-]{0,4}(\d)[`*]{0,2}"
_JOIN = r"\s*(?:,|/|\bor\b|\band\b|-|\bto\b|\bthrough\b)\s*"
_EXIT_ENUM = re.compile(
    r"\b(?:exit|exits|code|codes|refusal|refusals)\b" + _CODE
    + r"(?:" + _JOIN + _CODE + r")+", re.IGNORECASE)


# The RULE itself, not the two cross-references that point at it by name.
_REFUSAL_RULE = re.compile(r"Refused before launch \(exits", re.IGNORECASE)


def _contract_text(path: Path) -> str:
    """Whitespace-normalized CONTRACT text of a file.

    For markdown / shell / json that is the whole file. For the repo's own
    `tests/*.py` it is the COMMENT banners plus the docstrings - the text a
    maintainer reads as the rule - and never the fixture string literals a guard
    must quote verbatim in order to ban them.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".py":
        return " ".join(raw.split())
    parts: list[str] = []
    try:
        import io
        import tokenize
        for tok in tokenize.generate_tokens(io.StringIO(raw).readline):
            if tok.type == tokenize.COMMENT:
                parts.append(tok.string)
    except Exception:  # pragma: no cover - an unparsable file falls back to raw
        parts.append(raw)
    try:
        import ast
        tree = ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    parts.append(doc)
    except Exception:  # pragma: no cover
        parts.append(raw)
    return " ".join(" ".join(parts).split())


_ONE_CODE = re.compile(r"\b(?:exit|exits|code|codes)\b[`*\s:\-]{0,4}(\d)\b", re.IGNORECASE)


def _contract_paragraphs(path: Path) -> list[str]:
    """The file's contract text split into PASSAGES - the unit a remedy is offered in.

    A blank-line-separated block for markdown/shell/json; one contiguous comment
    run or one docstring for the repo's own tests. Passage granularity beats a
    sliding character window here: it is what makes "this passage offers a remedy"
    decidable instead of "some remedy token happens to sit N characters away".
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".py":
        return [" ".join(b.split()) for b in re.split(r"\n\s*\n", raw) if b.strip()]
    import ast
    import io
    import tokenize
    blocks: list[str] = []
    run: list[str] = []
    last_line = -2
    try:
        for tok in tokenize.generate_tokens(io.StringIO(raw).readline):
            if tok.type != tokenize.COMMENT:
                continue
            if tok.start[0] == last_line + 1:
                run.append(tok.string)
            else:
                if run:
                    blocks.append(" ".join(run))
                run = [tok.string]
            last_line = tok.start[0]
    except Exception:  # pragma: no cover
        return [" ".join(raw.split())]
    if run:
        blocks.append(" ".join(run))
    try:
        tree = ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    blocks.append(doc)
    except Exception:  # pragma: no cover
        pass
    return [" ".join(b.split()) for b in blocks if b.strip()]


def _refusal_enumerations(corpus=None) -> list[tuple[Path, str, str]]:
    """Every (file, matched enumeration, +/-260-char window) naming BOTH 6 and 7.

    Naming 6 and 7 together is what makes a passage the ACQUIRE refusal set - no
    other exit-code family in this plugin pairs them. TWO shapes are detected, so
    a rephrasing does not silence the scan: one joined list ("exit 6 or 7",
    "exits 6/7/8/9", "refusals - `6`, `7`, `8` and `9`") and two separate mentions
    close enough to be one passage ("exit 6 (...) or exit 7 (...)").
    """
    found = []
    for path in (corpus if corpus is not None else _stale_claim_corpus()):
        text = _contract_text(path)
        for m in _EXIT_ENUM.finditer(text):
            digits = set(re.findall(r"\d", m.group(0)))
            if {"6", "7"} <= digits:
                lo, hi = max(0, m.start() - 260), min(len(text), m.end() + 260)
                found.append((path, m.group(0), text[lo:hi]))
        singles = [(m.start(), m.end(), m.group(1)) for m in _ONE_CODE.finditer(text)]
        for (s1, e1, d1), (s2, e2, d2) in zip(singles, singles[1:]):
            if {d1, d2} != {"6", "7"}:
                continue
            gap = text[e1:s2]
            # One PASSAGE offering the set, not two codes being contrasted: the
            # codes are joined across at most a parenthetical, inside one clause
            # (no sentence break) and with no negation between them - "exit 6
            # (...) or exit 7" states the set; "must exit 6 ... never exit 7" and
            # "no exit 6, no exit 7" contrast them and state nothing.
            if len(gap) > 120 or re.search(r"[.;]", gap):
                continue
            if re.search(r"\b(no|not|never|rather|instead)\b", gap, re.IGNORECASE):
                continue
            lo, hi = max(0, s1 - 260), min(len(text), e2 + 260)
            found.append((path, text[s1:e2], text[lo:hi]))
    return found


def test_the_refusal_set_scan_reaches_every_restating_file():
    """Discovery floor. This scan is only worth anything if it actually reaches
    the files that restate the contract - a broken glob, a renamed separator or a
    changed lead-in word would make it vacuous instead of failing."""
    found = _refusal_enumerations()
    seen = {_rel(p) for p, _, _ in found}
    for expected in (
        "plugins/odoo-ai-agents/agents/odoo-instance-ops.md",
        "plugins/odoo-ai-agents/docs/reference/INSTANCE-ALLOCATION-API.md",
        "plugins/odoo-ai-agents/snippets/instance-resolution.md",
        "plugins/odoo-ai-agents/snippets/fp-merge-absorption.md",
        "plugins/odoo-ai-agents/skills/_shared/concurrency-guard.md",
        "plugins/odoo-ai-agents/skills/odoo-forward-port/references/fp-phase-detail.md",
    ):
        assert expected in seen, (
            f"{expected} restates the acquire refusal set but the enumeration scan "
            f"no longer reaches it - the scan is broken, not the file. Reached: {sorted(seen)}"
        )
    assert len(found) >= 6, f"only {len(found)} refusal enumerations found - scan is broken"


def test_no_file_states_the_acquire_refusal_set_without_8_and_9():
    """A passage that enumerates the acquire refusals MUST cover 8 and 9 too.

    Pre-fix RED: `snippets/instance-resolution.md`, `skills/_shared/concurrency-guard.md`,
    `snippets/fp-merge-absorption.md` and `skills/odoo-forward-port/references/fp-phase-detail.md`
    each said "exit 6 or 7" - a set that has been incomplete since acquire started
    refusing on authentication. An agent that hits 8 finds nothing matching in the
    paragraph written for exactly that purpose and either retries blind or falls
    into a generic error path."""
    offenders = []
    for path, enum, window in _refusal_enumerations():
        if not ("8" in window and "9" in window):
            offenders.append(f"{_rel(path)}: {enum!r} in ...{window[:200]}...")
    assert not offenders, (
        "these passages state the acquire refusal set without exits 8 and 9 - the "
        "agent cannot act on a code the contract never names:\n  " + "\n  ".join(offenders)
    )


def _instance_ops_status_lines(corpus=None) -> list[tuple[Path, str]]:
    """Every `status:` line inside an ```instance-ops fenced block, tree-wide."""
    lines = []
    for path in (corpus if corpus is not None else _stale_claim_corpus()):
        if path.suffix != ".md":
            continue
        inside = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not inside:
                if re.match(r"^`{3,}instance-ops\s*$", stripped):
                    inside = True
                continue
            if re.match(r"^`{3,}\s*$", stripped):
                inside = False
                continue
            if stripped.startswith("status:"):
                lines.append((path, stripped))
    return lines


def test_instance_ops_status_never_takes_a_continuation_only_value():
    """The two status vocabularies must stay separable.

    The `instance-ops` output block carries OPERATIONAL outcomes (up/created/
    dropped/tests-*/error); `DONE`/`NEEDS_NEXT`/`BLOCKED`/`NEEDS_CONTEXT` belong
    to the Continuation Contract and to nothing else. A file that offers a
    Continuation value as an `instance-ops` `status:` forces the agent either to
    emit an out-of-enum value (breaking every caller that parses the block) or to
    drop the actionable distinction.

    Pre-fix RED: `skills/odoo-instance/SKILL.md` listed `BLOCKED|NEEDS_CONTEXT`
    inside the block it tells the skill to relay verbatim, while the agent's own
    enum for the same block had neither."""
    lines = _instance_ops_status_lines()
    files = {_rel(p) for p, _ in lines}
    assert _rel(AGENT_MD) in files and _rel(SKILL_MD) in files, (
        f"the instance-ops block scan must reach both the agent and the skill; reached {files}"
    )
    offenders = [
        f"{_rel(p)}: {line!r}" for p, line in lines
        if re.search(r"\b(DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT)\b", line)
    ]
    assert not offenders, (
        "a Continuation Contract status value is offered as an `instance-ops` block "
        "status - the two vocabularies must never cross:\n  " + "\n  ".join(offenders)
    )


def test_the_refusal_before_launch_rule_maps_both_status_fields_explicitly():
    """The agent must say WHICH value goes in WHICH block on a refusal - naming
    one vocabulary's value with no block named is what made the two collide."""
    text = _norm(AGENT_MD)
    rule = _windows(text, _REFUSAL_RULE, 0, 1800)
    assert rule, "the agent must carry a named 'Refused before launch' rule for exits 8/9"
    body = rule[0]
    assert re.search(r"`instance-ops` block[^.]{0,80}`?status: error", body), (
        "the rule must name the value that goes in the `instance-ops` block (`error` - "
        "the only refusal value its enum has)"
    )
    assert re.search(r"Continuation Contract[^.]{0,90}NEEDS_CONTEXT", body), (
        "the rule must name the value that goes in the Continuation Contract"
    )
    assert re.search(r"NEEDS_CONTEXT", _norm(AGENT_MD)[
        _norm(AGENT_MD).find("Continuation Contract block per"):][:900]), (
        "the Continuation Contract section must keep ONE rule for a refusal, not a "
        "second, contradicting mapping"
    )


def test_exit_8_and_exit_9_never_share_one_remedy():
    """Exit 9's remedy differs IN KIND from exit 8's: start the cluster / correct
    db_host-db_port, not an authentication fix. A passage that names both codes and
    offers only an auth remedy sends a stopped cluster to `48-db-local-auth.sh`,
    which does nothing for a cluster that is not running.

    Pre-fix RED: the agent's Through-Odoo paragraph named both exits and then one
    remedy - `/odoo-ai-agents:odoo-setup`, with the parenthetical attached to 8.
    A passage that states NO remedy (a pure cross-reference to the SSOT) is not a
    finding - only one that states an auth remedy without the reachability one."""
    auth = re.compile(r"odoo-setup|ODOO_PG_PASSWORD|48-db-local-auth", re.IGNORECASE)
    reach = re.compile(r"start(?:ing|s)?\s+(?:the\s+)?cluster|db_host|db_port", re.IGNORECASE)
    code8 = re.compile(r"(?:\b(?:exit|exits|code|codes)\b[`*\s:\-]{0,4}|[`*])8\b")
    code9 = re.compile(r"(?:\b(?:exit|exits|code|codes)\b[`*\s:\-]{0,4}|[`*])9\b")
    offenders = []
    checked = 0
    for path in _stale_claim_corpus():
        for passage in _contract_paragraphs(path):
            if not (code8.search(passage) and code9.search(passage)):
                continue
            # A passage that offers NO remedy is a cross-reference to the SSOT,
            # not a fifth copy of it - nothing to check.
            if not auth.search(passage):
                continue
            checked += 1
            if not reach.search(passage):
                offenders.append(f"{_rel(path)}: ...{passage[:260]}...")
    assert checked >= 2, (
        f"only {checked} passage(s) offer a remedy for exits 8/9 - the scan is broken, "
        "not the prose"
    )
    assert not offenders, (
        "exit 8 and exit 9 are given ONE remedy - a stopped cluster is being sent to "
        "an authentication fix:\n  " + "\n  ".join(offenders)
    )
    agent = _norm(AGENT_MD)
    assert re.search(r"ODOO_PG_PASSWORD", agent), (
        "the agent must name `ODOO_PG_PASSWORD` as the managed/remote alternative - "
        "step 48 REFUSES exactly that class of cluster, so setup alone is a dead end there"
    )


def test_db_auth_unknown_is_stated_as_never_blocking():
    """`unknown` is the ONE DB_AUTH state that must never block, and the primitive
    prints a `BLOCKED - DB_AUTH=<state>` stderr block for EVERY non-ok state -
    `unknown` included - so a fully successful acquire can print a scary refusal
    line moments before succeeding. Wherever the states are enumerated for an
    agent, the never-block rule and the exit-code-over-stderr rule travel with
    them.

    Pre-fix RED: "unknown" appeared nowhere near DB_AUTH in the agent file, so an
    agent had no textual basis for treating exit 0 with that stderr as a pass."""
    corpus = [p for p in _stale_claim_corpus() if "DB_AUTH" in _contract_text(p)]
    reached = {_rel(p) for p in corpus}
    assert _rel(AGENT_MD) in reached and _rel(ALLOCATION_DOC) in reached, (
        f"the DB_AUTH scan must reach the agent and the allocation reference; got {reached}"
    )
    never_blocks = re.compile(
        r"(unknown|undetermin\w*)[^.]{0,200}?\b(?:never|does not|do not|cannot)\b[^.]{0,120}?block"
        r"|\b(?:never|does not|do not|cannot)\b[^.]{0,140}?block[^.]{0,200}?(unknown|undetermin\w*)",
        re.IGNORECASE)
    offenders = []
    for path in corpus:
        text = _contract_text(path)
        states = [s for s in ("denied", "unreachable", "unknown") if s in text]
        if len(states) >= 2 and not never_blocks.search(text):
            offenders.append(f"{_rel(path)} enumerates {states} without the never-block rule")
    assert not offenders, (
        "a DB_AUTH state enumeration omits the rule that an UNDETERMINABLE state never "
        "blocks - only a PROVEN 8 or 9 does:\n  " + "\n  ".join(offenders)
    )
    agent = _norm(AGENT_MD)
    assert re.search(
        r"DB_AUTH=unknown[^.]{0,400}?(exit code is authoritative|EXIT CODE is authoritative)",
        agent, re.IGNORECASE), (
        "the agent must be told the EXIT CODE is authoritative for `unknown`, not the "
        "`BLOCKED - DB_AUTH=` stderr string every non-ok state prints"
    )


def test_the_agent_never_self_applies_the_pg_hba_setup_step():
    """Step 48 edits a live cluster's `pg_hba.conf` the moment it is invoked and
    carries no confirm gate of its own - the gate lives in `/odoo-setup`
    (CONFIRM #5). This agent self-invokes numbered setup scripts routinely
    (`45-venv.sh`, `50-instance-spinup.sh`), so silence here reads as permission.

    Pre-fix RED: nothing forbade it, and the file's own idiom said yes."""
    agent = _norm(AGENT_MD)
    window = _windows(agent, re.compile(r"48-db-local-auth\.sh"), 400, 700)
    assert window, "the agent must name the step 48 remedy for exit 8"
    assert any(
        re.search(r"NEVER run `?48-db-local-auth\.sh", w, re.IGNORECASE)
        or re.search(r"never (?:run|invoke)[^.]{0,60}48-db-local-auth", w, re.IGNORECASE)
        for w in window
    ), "the agent must be forbidden from running step 48 itself"
    assert any(re.search(r"route[^.]{0,80}(human|odoo-setup)", w, re.IGNORECASE) for w in window), (
        "the prohibition must name the route that replaces it - through the human via "
        "`/odoo-ai-agents:odoo-setup`"
    )


def test_the_mandatory_wait_log_step_has_an_arm_for_a_build_that_opens_no_log():
    """A refusal before launch emits no `LOG_PATH=` at all, so the HARD RULE's
    mandatory `wait-log` call has no argument to take. Without a named arm the
    agent has no valid next tool call and the rule reads as a stall.

    Pre-fix RED: the rule covered a reaped launcher with no `STATUS=` line but not
    a build that never opened a log."""
    text = _norm(AGENT_MD)
    arm = _windows(text, re.compile(r"No `LOG_PATH=` line at all", re.IGNORECASE), 0, 420)
    assert arm, "the active-wait HARD RULE must carry an arm for a build that opens no log"
    body = arm[0]
    assert re.search(r"terminal|report", body, re.IGNORECASE), (
        "the arm must resolve to a report, not to a wait"
    )
    assert re.search(r"skip|nothing to wait on", body, re.IGNORECASE), (
        "the arm must say the mandatory wait-log call is skipped in this ONE case"
    )


def test_the_forwarded_refusal_has_a_documented_home_outside_the_one_line_notes():
    """`notes:` is documented as a one-line summary; the primitive's refusal is
    4-6 lines and must be forwarded AS-IS. Without a named home the agent either
    violates the block convention or truncates the primitive's own text."""
    text = _norm(AGENT_MD)
    rule = _windows(text, _REFUSAL_RULE, 0, 1800)
    assert rule, "the refusal rule must exist"
    body = rule[0]
    assert re.search(r"(fenced block|prose summary)", body, re.IGNORECASE), (
        "the multi-line refusal needs a named home - a fenced block in the prose summary"
    )
    assert re.search(r"never[^.]{0,80}(truncat|fold)[^.]{0,60}`?notes", body, re.IGNORECASE), (
        "the rule must forbid truncating the refusal into the one-line `notes:` field"
    )


def test_force_forget_is_named_and_its_outcomes_are_flag_gated():
    """`--force-forget` gates two of the three release outcome keys, and a plain
    release on a present-or-unverifiable DB emits NONE of them (exit 1, lease
    kept). The flag PERMANENTLY accepts a leaked database, so the file must say
    who decides.

    Pre-fix RED: `--force-forget` appeared 0 times in the agent, while the prose
    told the agent to distinguish three outcomes as if all three were reachable
    from the plain release the code block above it shows."""
    text = _norm(AGENT_MD)
    assert "--force-forget" in text, (
        "the flag that gates two of the three release outcome keys must be named"
    )
    win = _windows(text, re.compile(r"ALLOC_FORGOTTEN_DB"), 400, 900)
    assert win, "the release outcomes must be documented"
    body = " ".join(win)
    assert re.search(r"WITHOUT the flag|without `--force-forget`|plain release", body, re.IGNORECASE), (
        "the outcomes reachable WITHOUT the flag must be separated from those needing it"
    )
    assert re.search(r"(NO key|no key at all)[^.]{0,120}(exit 1|KEEPS the lease|lease)", body,
                     re.IGNORECASE) or re.search(
        r"(KEEPS the lease|lease is KEPT)[^.]{0,140}(exit 1)", body, re.IGNORECASE), (
        "the fourth case - present or unverifiable without the flag: no key, lease kept, "
        "exit 1 - must be covered"
    )
    assert re.search(r"PERMANENTLY|permanent", body, re.IGNORECASE) and re.search(
        r"(caller|human)[^.]{0,120}(asked|owns|decide)", body, re.IGNORECASE), (
        "escalating to --force-forget permanently accepts a leak, so the file must say "
        "who decides"
    )


def test_the_setup_command_carries_one_step_inventory():
    """`commands/odoo-setup.md` is EXECUTED by a router: an executable header that
    bounds the instance cluster at AI-4 while AI-5 lives inside it, or a
    `skip instance` list that omits the one step which edits a live cluster's
    `pg_hba.conf`, is a routing bug, not a documentation nit.

    Pre-fix RED: the cluster header said AI-1 through AI-4, the skip list named
    only 40/45/50, and the "what it sets up" list stopped at 5 = spin-up."""
    text = _norm(SETUP_CMD_MD)
    assert "AI-5" in text, "AI-5 must exist in the command"
    assert not re.search(r"AI-1 through AI-4|AI-1\.\.AI-4", text), (
        "no header may bound the instance cluster at AI-4 while AI-5 runs inside it"
    )
    skip = _windows(text, re.compile(r"skip instance"), 60, 400)
    assert skip, "the Gate #2 skip-instance branch must exist"
    assert any(re.search(r"`48`|`48-db-local-auth", w) for w in skip), (
        "an explicit `skip instance` must skip step 48 - it edits a live cluster's "
        "pg_hba.conf"
    )
    inventory = _windows(text, re.compile(r"5\.\s+\*\*DB local auth"), 0, 200)
    assert inventory, (
        "the 'what it sets up' inventory must include DB local auth, renumbering "
        "spin-up to 6 as `docs/setup.md` already does"
    )
    assert re.search(r"6\.\s+\*\*Instance spin-up", text), (
        "instance spin-up must be item 6 once DB local auth is item 5"
    )
    assert not re.search(r"probe PostgreSQL through the declared `db_run_mode`", text), (
        "step 50's gate is Odoo's OWN connection; a green pg_isready can never make the "
        "launch green, and the numbered flow must not describe it as the preflight"
    )


# ---------------------------------------------------------------------------
# The `instance-ops` OPERATIONAL status enum is declared in exactly ONE place.
#
# The two-vocabulary collision this section's earlier guards fix arose from a
# COPY: `skills/odoo-instance/SKILL.md` restated the enum it is told to relay
# verbatim, and the copy then drifted - it grew `started`, lost `ready-for-doc`,
# and gained two Continuation-only values the agent's own enum never had. A
# second copy is therefore not a style problem, it is the defect's origin.
# ---------------------------------------------------------------------------
# Operational values only. `started` is the RETIRED value the drifted copy grew;
# it stays in the pattern so a copy carrying it is caught rather than missed.
_OPERATIONAL_STATUS_VALUES = (
    "tests-passed-with-warnings", "tests-inconclusive", "tests-failed",
    "tests-passed", "ready-for-doc", "created", "dropped", "started",
    "up", "down", "error",
)
_STATUS_ENUM_RUN = re.compile(
    r"\b(?:" + "|".join(_OPERATIONAL_STATUS_VALUES) + r")\b"
    r"(?:\s*[|,/]\s*\b(?:" + "|".join(_OPERATIONAL_STATUS_VALUES) + r")\b){2,}"
)


def _status_enum_copies(corpus=None) -> list[tuple[Path, str]]:
    """Every place an operational-status ENUM is spelled out, tree-wide.

    The shape is >=3 of the operational values joined by `|`, `,` or `/` - a
    declaration, not a prose mention of one value. That is what separates "this
    file declares the enum" from "this file talks about tests-inconclusive".
    """
    found = []
    for path in (corpus if corpus is not None else _stale_claim_corpus()):
        text = _contract_text(path)
        for m in _STATUS_ENUM_RUN.finditer(text):
            found.append((path, m.group(0)))
    return found


def test_the_operational_status_enum_is_declared_in_exactly_one_place():
    """ONE declaration, everywhere else a cross-reference.

    Pre-fix RED: `skills/odoo-instance/SKILL.md` carried a second copy of the enum
    inside the ```instance-ops block it relays verbatim. Two copies is how the
    vocabularies drifted apart in the first place - the copy grew `started`, lost
    `ready-for-doc`, and admitted `BLOCKED`/`NEEDS_CONTEXT`."""
    copies = _status_enum_copies()
    # Discovery floor: the ONE declaration must still be found, in the agent, inside
    # its own instance-ops block, and still complete - a renamed value or a reflowed
    # block would otherwise make this guard vacuous instead of failing.
    mine = [run for path, run in copies if path == AGENT_MD]
    assert len(mine) == 1, (
        f"the agent must carry exactly ONE operational status enum; found {len(mine)}"
    )
    declaration = mine[0]
    assert sum(v in declaration for v in _OPERATIONAL_STATUS_VALUES) >= 8, (
        f"the declaration lost values - the scan is matching something else: {declaration!r}"
    )
    assert "error" in declaration and "ready-for-doc" in declaration, (
        "the declaration must still carry the refusal value `error` and `ready-for-doc`"
    )
    assert "started" not in declaration, (
        "`started` is the retired value the drifted copy grew - it must not enter the "
        "declaration"
    )
    assert any(
        line.startswith("status:") and _STATUS_ENUM_RUN.search(line)
        for path, line in _instance_ops_status_lines() if path == AGENT_MD
    ), "the declaration must live on the `status:` line of the agent's instance-ops block"
    offenders = [f"{_rel(p)}: {run[:160]!r}" for p, run in copies if p != AGENT_MD]
    assert not offenders, (
        "the operational status enum is declared in more than one place - every other "
        "file must cross-reference the agent instead of copying it:\n  "
        + "\n  ".join(offenders)
    )


def test_the_password_escape_hatch_states_its_ordering_and_its_scope():
    """`$ODOO_PG_PASSWORD` is read from the ENVIRONMENT of the process that runs
    each step (the scripts export it to libpq as PGPASSWORD for that launch only,
    and the generated conf carries no db_password line). Offered without that
    ordering, the human exports it in their own terminal, the orchestrator's next
    `50 apply` never sees it, and the build refuses again.

    Pre-fix RED: AI-5 said only "on a refusal offer the alternative it names and
    continue" - no ordering, no process scope, and no route for the case that
    actually bites (the orchestrator does not control the human's shell)."""
    text = _norm(SETUP_CMD_MD)
    win = _windows(text, re.compile(r"ODOO_PG_PASSWORD"), 200, 900)
    assert win, "the setup command must name the escape hatch"
    body = " ".join(win)
    assert re.search(r"\bSAME shell\b|same shell", body), (
        "the export must be scoped to the SAME shell/process that runs the consuming step"
    )
    assert re.search(r"(before|precede)[^.]{0,60}`?50 apply", body, re.IGNORECASE), (
        "the ordering must be explicit: the export precedes the step that consumes it"
    )
    assert re.search(r"never reaches yours|own terminal", body, re.IGNORECASE), (
        "the failure mode must be named - a value exported in the human's own terminal "
        "never reaches the orchestrator's process"
    )
    assert re.search(r"PGPASSFILE|pgpass", body), (
        "the case that bites - no control over the consuming shell - needs the durable "
        "route libpq resolves by itself, not an export that will never arrive"
    )
    assert re.search(r"NEVER ask for it|never (?:ask|echo)", body, re.IGNORECASE), (
        "a secret must never be requested, echoed, or placed on a command line"
    )


# ---------------------------------------------------------------------------
# Step 48's arm is chosen by WHERE THE SERVER RUNS, never by `db_run_mode`.
#
# `db_run_mode` records only whether libpq binaries are on THIS host's PATH
# (`pg_mode.sh`: "native = libpq client binaries on PATH reach this cluster"), and
# it prefers `native` whenever they are. The modal developer host - client
# installed, PostgreSQL in a container publishing a loopback port - therefore
# records `native` while its SERVER is a container. Routing the FIX on that value
# sent exactly that host to the advise-only arm, which prints loopback trust rules
# that can never match a connection arriving from the bridge gateway. Step 48 now
# asks `_container_publishing` where the SERVER is; the prose must not reinstate
# the retired premise that `native` means advice-only.
# ---------------------------------------------------------------------------
# A backticked bare `native` is the db_run_mode LITERAL. "native SERVER" (no
# backticks) is the server-location fact, which IS a legitimate advisory trigger -
# so the shape distinguishes them instead of banning the word.
_DB_RUN_MODE_LITERAL = re.compile(r"`native`")
_ADVISORY_OUTCOME = re.compile(
    r"advis\w*|printed instructions|instructions only|prints? (?:the )?instructions",
    re.IGNORECASE)


def test_no_prose_ties_the_advise_only_arm_to_the_db_run_mode_value():
    """The advise-only arm belongs to a native SERVER, not to `db_run_mode=native`.

    Pre-fix RED: `commands/odoo-setup.md` said "A `native` cluster gets printed
    instructions only" and "a `native` cluster's `pg_hba.conf` are only *advised*" -
    both keying the outcome on the CLIENT-surface value, which is what sent a
    container-served host to an arm that could not fix it."""
    offenders = []
    checked = 0
    for path in _stale_claim_corpus():
        for passage in _contract_paragraphs(path):
            if not re.search(r"48-db-local-auth|step 48|`48`", passage, re.IGNORECASE):
                continue
            checked += 1
            for m in _DB_RUN_MODE_LITERAL.finditer(passage):
                tail = passage[m.end(): m.end() + 80]
                if _ADVISORY_OUTCOME.search(tail):
                    offenders.append(f"{_rel(path)}: ...{passage[m.start() - 60:m.end() + 90]}...")
    assert checked >= 2, (
        f"only {checked} passage(s) about step 48 were scanned - the scan is broken, "
        "not the prose"
    )
    assert not offenders, (
        "the advise-only arm is keyed on the `db_run_mode` value instead of on where "
        "the SERVER runs - the retired premise:\n  " + "\n  ".join(offenders)
    )


def test_the_setup_command_states_the_real_step_48_routing_key():
    """The router must be able to predict which arm runs: the server's location,
    a single publisher of the declared port, and the two-publisher refusal."""
    bullet = [
        p for p in _contract_paragraphs(SETUP_CMD_MD)
        if "48-db-local-auth" in p and "pg_hba.conf" in p
    ]
    assert bullet, "the step-48 bullet must exist in the setup command"
    body = " ".join(bullet)
    assert re.search(r"where the SERVER is|SERVER runs|the SERVER", body), (
        "the bullet must name the routing key - where the SERVER runs"
    )
    assert re.search(r"NOT by\s+`db_run_mode`|not by\s+`db_run_mode`", body), (
        "the bullet must say the arm is NOT chosen by `db_run_mode`"
    )
    assert re.search(r"publish\w*[^.]{0,80}`db_port`|`db_port`[^.]{0,80}publish\w*", body), (
        "the bullet must name the actual test - a container publishing the declared "
        "`db_port`"
    )
    assert re.search(r"(TWO|two)\s+publishers?[^.]{0,120}(refus|declare `db_container`)", body), (
        "two publishers is refused and named - a router that expects a guess would "
        "misreport the refusal"
    )
    assert re.search(r"native SERVER", body), (
        "printed instructions belong to a genuinely native SERVER, and the prose must "
        "say so in those terms"
    )


def test_the_never_sudo_rule_survives_and_still_covers_pg_hba():
    """Correcting the PREMISE of the advisory arm must never weaken the rule it
    guards: this plugin runs no sudo, and a privileged `pg_hba.conf` change stays
    the user's to make."""
    text = _norm(SETUP_CMD_MD)
    rule = _windows(text, re.compile(r"Never sudo silently", re.IGNORECASE), 0, 320)
    assert rule, "the never-sudo-silently HARD RULE must still exist"
    body = rule[0]
    assert "pg_hba.conf" in body, (
        "the rule must still cover a privileged pg_hba.conf change - that is the case "
        "step 48 refuses to perform"
    )
    assert re.search(r"advis", body, re.IGNORECASE) and re.search(
        r"user runs any privileged change", body, re.IGNORECASE), (
        "the rule must keep both halves: advise only, and the user performs the "
        "privileged change"
    )


# ---------------------------------------------------------------------------
# The operation SET, not just the operation COUNT.
#
# `tests/test_counted_section_reference_agreement.py` proves the NUMBER in
# `## Seven operations` agrees with every cross-file citation of that heading.
# That is the single-syntax half, and on its own it is satisfied by a rename, a
# swap, or two errors that cancel: seven headings and seven dispatch values can
# disagree on every member and still both be seven. This is the other half - the
# MEMBERSHIP check - and the two are deliberately kept as separate guards so a
# failure names which kind of drift happened.
#
# The two sides are genuinely different vocabularies and the mapping between them
# is stated here rather than assumed: the agent names its operations by their full
# `<verb>-<object>` heading (`create-instance`, `init-modules`), while the skill's
# dispatch table names the VERB a caller passes (`create`, `init`). One agent
# heading legitimately covers two dispatch values (`ensure-up / status`).
# ---------------------------------------------------------------------------
_OPERATION_HEADING_RE = re.compile(r"^###\s+\d+\.\s+(.+?)\s*$", re.M)
_OPERATION_OBJECT_SUFFIXES = ("-instance", "-modules")
# The catalog heading is found by SHAPE, never by its current count word: the count is data
# (`test_counted_section_reference_agreement.py` owns keeping it honest), so adding a ninth
# operation must not also require editing this extractor to see it.
_OPERATION_SECTION_RE = re.compile(r"^##\s+\w+\s+operations\s*$", re.M)


def _agent_operation_verbs() -> set[str]:
    """The dispatch verbs the agent's numbered operation headings cover."""
    text = AGENT_MD.read_text(encoding="utf-8")
    heading = _OPERATION_SECTION_RE.search(text)
    assert heading, "agents/odoo-instance-ops.md no longer has a `## <count> operations` catalog"
    start = heading.start()
    end = text.find("\n## ", start)
    section = text[start:] if end == -1 else text[start:end]
    verbs = set()
    for m in _OPERATION_HEADING_RE.finditer(section):
        for part in m.group(1).split("/"):
            name = part.strip()
            for suffix in _OPERATION_OBJECT_SUFFIXES:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            verbs.add(name)
    return verbs


def _skill_dispatch_verbs() -> set[str]:
    """The `operation` row of the skill's dispatch table, as a set."""
    for line in SKILL_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("| `operation`"):
            cells = [c.strip() for c in line.split("|")]
            return {v.strip(" `") for v in cells[2].split("/") if v.strip()}
    raise AssertionError("the skill's dispatch table has no `operation` row any more")


def test_the_operation_discovery_floors_hold():
    """Both extractors must actually find something. A guard that compares two
    empty sets is the failure mode this whole pair exists to avoid."""
    assert len(_agent_operation_verbs()) >= 7, (
        f"the agent's operation headings did not parse: {sorted(_agent_operation_verbs())}"
    )
    assert len(_skill_dispatch_verbs()) >= 7, (
        f"the skill's dispatch row did not parse: {sorted(_skill_dispatch_verbs())}"
    )


def test_operation_set_matches_the_dispatch_table():
    """Every operation the agent implements is dispatchable, and every value the
    skill accepts is implemented.

    A value in the skill that the agent never implements is a dispatch the agent
    answers by improvising; an operation in the agent no skill value reaches is
    this repo's signature defect - a correct mechanism nothing calls."""
    agent, skill = _agent_operation_verbs(), _skill_dispatch_verbs()
    assert agent == skill, (
        "the agent's operations and the skill's dispatch values have drifted apart.\n"
        f"  only in agents/odoo-instance-ops.md: {sorted(agent - skill)}\n"
        f"  only in skills/odoo-instance/SKILL.md: {sorted(skill - agent)}"
    )
