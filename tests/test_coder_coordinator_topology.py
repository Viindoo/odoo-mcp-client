"""Topology guard for the node-primary / coder-coordinator model.

Protects the BEHAVIOR of the two-tier decomposition (not a wording snapshot).

Ground truth (reverse-engineered from the installed Claude Code binary, corrected here after a
prior pass pinned a FALSE premise): a subagent CAN launch a child and CAN receive its result via a
blocking launch (`run_in_background: false`), or - when the Agent tool exposes no such parameter -
launch async and END ITS TURN to be resumed by a wake router on completion; it is never simply
killed. The real hazards are the silent nesting cap (no Agent tool at all -> do the work inline or
return NEEDS_NEXT) and the non-interactive surface (where nothing resumes a parked turn, so never
end a turn with uncommitted work). This is `spawner-completion-contract.md` R0. A PRIOR pass
misread "a subagent may never be woken" out of an early, incomplete reading of the same evidence
and retargeted this whole file to an "odoo-coder authors everything inline, launches nothing"
topology. That premise is FALSE and has been retired in turn; the three-teammate topology below is
RESTORED (decided by the repo owner) and now runs on the CORRECT R0 physics (blocking launches via
`run_in_background: false`, never a passive/unbounded wait):

- The OUTER unit is the NODE (D1/D4 - the wave grouping layer is deleted and one-coder-per-module
  goes with it). `odoo-coding` dispatches ONE `odoo-coder` COORDINATOR per node (EVERY node -
  backend-only, frontend-only, or full-stack; a node may span one module, part of one, or several -
  the module is a PROPERTY of a node, never the dispatch unit). There is no single-stack
  direct-to-worker path.
- `odoo-coder` is the per-node COORDINATOR that OWNS the node's INTERNAL work-item (WI) split:
  it divides its ONE node into 1..N disjoint-file-set WIs, schedules INDEPENDENT WIs in PARALLEL
  and DEPENDENT WIs SEQUENTIALLY (backend before a frontend WI that binds it), and per WI launches
  THREE teammates - `odoo-test-writer` FIRST (authors the RED test, test-first), then
  `odoo-backend-coder` / `odoo-frontend-coder` (make it green; the coders no longer author tests) -
  blocking on each via R0 move 2 (`run_in_background: false`) when it needs the result. It tests
  the integrated node via `Skill(odoo-instance)` (inline in its own context, or by launching
  `odoo-instance-ops` - either way under the instance HARD RULES), then COMMITS its node by
  invoking `Skill(git-toolkit:git-ops)` (request-only; no raw git, no direct git leaf agent) and
  returns the SHA to `odoo-coding` (which collects it, no longer re-committing). It also reacts to a
  WI worker's own pre-integration BLOCKED within its bounded loop (excluding the
  manifest-dependency case, which still relays up unchanged) and monitors its
  WI workers on a live task list per `execution-tasklist-contract.md`.
- `odoo-test-writer`, `odoo-backend-coder`, and `odoo-frontend-coder` are HARD LEAVES - they launch
  nothing.
- The WI is `odoo-coder`'s PRIVATE unit: it MUST NOT appear as an outer-layer unit in
  odoo-planning / plan-mode-schema / phase-p / run-harness.
- `odoo-module-graph.md` states the two-tier axis (node outer, WI internal to odoo-coder; the
  module is a PROPERTY of a node, not a third tier).
- The agent is registered in plugin.json and reflected in the orchestration SSOT (`odoo-coding`'s
  spawns list names the coordinator + all three teammates).

Red-before-green: each assertion fails if its wiring is dropped or inverted. Several assertions
below were RESTORED (not merely reworded) after a prior pass wrongly retargeted them to the
inline-only premise - each restoration states the WRONG (false-premise) assertion it replaces, the
RESTORED one, and why the underlying business rule is the one that was true all along.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
LEAD = AGENTS / "odoo-coder.md"
TEST_WRITER = AGENTS / "odoo-test-writer.md"
BACKEND = AGENTS / "odoo-backend-coder.md"
FRONTEND = AGENTS / "odoo-frontend-coder.md"
CODING = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
MODULE_GRAPH = PLUGIN / "skills" / "_shared" / "odoo-module-graph.md"
CLAUDE_MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
DEPS = PLUGIN / "generator" / "skill_tool_deps.json"

# The OUTER-layer sites that must think in NODES only (never frame the outer unit as a WI, and
# never resurrect the module as the dispatch/grouping unit - D1/D4: the module is a property of a
# node, not the outer unit, and the wave layer these sites used to group nodes into is deleted).
OUTER_LAYER_FILES = {
    "odoo-planning": PLUGIN / "skills" / "odoo-planning" / "SKILL.md",
    "odoo-planner": AGENTS / "odoo-planner.md",
    "plan-mode-schema": PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md",
    "phase-p": PLUGIN / "skills" / "odoo-intake" / "references" / "phase-p-run-dag.md",
    "run-harness": PLUGIN / "skills" / "run-harness" / "SKILL.md",
}

# Regexes that would betray the OLD outer-WI framing (an outer layer decomposing into WIs).
# A bare mention of "work-item" is allowed ONLY as a disclaimer that it is odoo-coder-internal;
# these patterns are the ones that name a WI as the outer unit of planning/wave/run. Word-bounded
# so legitimate prose ("the module set", "each with") never false-positives.
OUTER_WI_ANTIPATTERNS = (
    r"per-wi\b",
    r"\bper wi\b",
    r"\bwi list\b",
    r"workitem list",
    r"wi-brief",
    r"wi->file",
    r"\beach wi\b",
    r"\bmodule set\b\s*:",  # the old "MODULE SET :" WI-brief field, not the phrase "the module set"
)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _norm(p: Path) -> str:
    return " ".join(_text(p).split())


def _dispatch_fences(p: Path) -> str:
    """The fenced ``` blocks of a body - the literal brief templates a dispatcher fills. Same
    scoping [brief-fields] (check_orchestration.py rule 12) applies, so both guards read the
    coordinator's brief from the same place."""
    return "\n".join(re.findall(r"```.*?```", _text(p), re.S))


def test_backend_coder_agent_exists_and_is_registered():
    """The backend writer agent exists and is declared in plugin.json.agents."""
    assert BACKEND.is_file(), "agents/odoo-backend-coder.md must exist (the backend hard-leaf writer)"
    declared = {Path(p).name for p in json.loads(_text(CLAUDE_MANIFEST)).get("agents", [])}
    assert "odoo-backend-coder.md" in declared, (
        "odoo-backend-coder.md must be declared in .claude-plugin/plugin.json agents"
    )


def test_coordinator_assigns_wis_to_the_three_teammates_backend_first():
    """RESTORE of the topology this file originally pinned.

    A prior pass replaced this with "test_coordinator_authors_every_wi_itself_backend_before_frontend",
    asserting the coordinator authors every WI inline and launches no agent - built on the false
    premise that a subagent has no barrier to release a launched child with (R0). The corrected R0
    (spawner-completion-contract.md) establishes the opposite: the Agent tool's own
    `run_in_background: false` parameter IS a blocking-launch lever, so a coordinator well inside
    the nesting cap can launch a teammate and block on its result. The repo owner has restored the
    three-teammate topology on this corrected physics.

    RESTORED assertion: the odoo-coder COORDINATOR launches THREE teammates - odoo-test-writer
    (test-first) + odoo-backend-coder + odoo-frontend-coder per WI - and sequences the backend WI
    before a frontend WI that binds it."""
    body = _norm(LEAD)
    assert "odoo-test-writer" in body, (
        "the coordinator must launch odoo-test-writer (the test-first teammate)"
    )
    assert "odoo-backend-coder" in body and "odoo-frontend-coder" in body, (
        "the coordinator must assign WIs to BOTH odoo-backend-coder and odoo-frontend-coder"
    )
    low = body.lower()
    # A bare `"backend" in low and "first" in low` is satisfied vacuously - both words appear
    # dozens of times elsewhere in the doc (e.g. "author the RED test FIRST") regardless of
    # whether backend-before-frontend sequencing is stated anywhere. Require the actual phrase.
    assert "backend before" in low, (
        "the coordinator must sequence a backend WI before a frontend WI that binds it"
    )


def test_coordinator_launches_test_writer_first_and_coders_do_not_author():
    """RESTORE of the topology this file originally pinned.

    A prior pass replaced this with "test_coordinator_authors_red_test_first_inline_and_leaves_do_not_author",
    asserting the coordinator authors the RED test itself via Skill(odoo-test-writing) inline. That
    was built on the same false premise as the sibling test above (R0: no barrier to block on a
    launched child) - now corrected: the coordinator DOES launch odoo-test-writer and blocks on it
    via R0 move 2.

    RESTORED assertion (test-first): the coordinator launches odoo-test-writer FIRST (the RED
    test), then the coder; the coders themselves still never author tests."""
    body = _norm(LEAD)
    low = body.lower()
    # A bare `"odoo-test-writer" in low and "first" in low` is satisfied vacuously - "first"
    # appears 15+ times elsewhere in the doc (e.g. the backend-before-frontend sequencing prose,
    # and the compound "test-first" methodology name that legitimately sits near almost every
    # odoo-test-writer mention). Require the LAUNCH VERB tightly bound to both odoo-test-writer
    # and "first" (e.g. "launch `odoo-test-writer` FIRST"), not incidental co-occurrence.
    assert re.search(
        r"(?i)launch(?:es|ing)?\s*`?odoo-test-writer`?\s+first\b", body
    ), (
        "the coordinator must launch odoo-test-writer FIRST per WI (test-first) - a launch verb "
        "must sit directly against 'odoo-test-writer ... first', not merely co-occur anywhere"
    )
    # The coder agents must explicitly disclaim test authoring (write code only).
    for path in (BACKEND, FRONTEND):
        cbody = _norm(path).lower()
        assert "do not author tests" in cbody or "does not author tests" in cbody or (
            "not author" in cbody and "test" in cbody
        ), f"{path.name} must state it does NOT author tests (the odoo-test-writer teammate does)"


def test_coordinator_owns_the_internal_wi_breakdown():
    """odoo-coder OWNS the internal WI split: 1..N disjoint WIs, parallel-vs-sequential schedule,
    per-WI worker assignment - and states the WI is its PRIVATE intra-module unit.

    RESTORE note: a prior pass required the NEGATION 'no parallel launch' (independent WIs cannot
    run in parallel because a subagent supposedly has no barrier to release a batch with). That
    premise is false - R0 move 2 (`run_in_background: false`) is exactly the mechanical barrier
    an independent batch releases on, per spawner-completion-contract.md R1. This restores the
    positive claim: independent WIs run in PARALLEL, dependent WIs run SEQUENTIALLY."""
    low = _norm(LEAD).lower()
    assert "work-item" in low or "wi" in low, "the coordinator must name the work-item unit"
    assert "disjoint" in low, "the WI split must be by DISJOINT file sets"
    assert "parallel" in low and "sequential" in low, (
        "independent WIs run in PARALLEL, dependent WIs run SEQUENTIALLY (R0 move 2 supplies the "
        "mechanical barrier for both - a blocking launch for the dependent chain, a held batch for "
        "the parallel one)"
    )
    assert "1..n" in low or "1..N".lower() in low or "one or more" in low, (
        "one module -> 1..N WIs"
    )
    assert "private" in low or "internal" in low, (
        "the WI must be declared the coordinator's PRIVATE / INTERNAL unit"
    )


def test_coordinator_tests_integrated_module_via_instance_skill():
    """The coordinator owns the integrated module test, provisioned via Skill(odoo-instance) - either
    inline in its own context or by launching odoo-instance-ops - either way under the HARD RULES."""
    body = _norm(LEAD)
    assert "Skill(odoo-instance)" in body, "the coordinator must run the integrated test via Skill(odoo-instance)"
    assert "integrated" in body.lower(), "the coordinator must own the INTEGRATED whole-module test"


def test_coordinator_is_bounded_fix_loop():
    """On failure the coordinator re-launches the relevant worker in a bounded loop (reusing the
    3-iteration bound from test-first-contract.md)."""
    body = _norm(LEAD)
    assert "test-first-contract.md" in body, "the coordinator must cite the test-first-contract bound"
    assert "3 iteration" in body.lower() or "3 iterations" in body.lower(), (
        "the coordinator's fix loop must reuse the 3-iteration bound"
    )


def test_coordinator_reacts_to_wi_level_blocked_excluding_manifest_dependency():
    """A WI worker (odoo-test-writer / odoo-backend-coder / odoo-frontend-coder) can BLOCK on its OWN
    before the integrated test ever runs (e.g. no RED test handed in, or the worker exhausted its own
    attempts on an ambiguous WI). The coordinator must react within its bounded loop - never idle and
    never silently drop the WI - EXCLUDING the manifest-dependency case, which still relays UP to
    odoo-coding unchanged (ledger-unaware), per module-coordination-ledger.md."""
    body = _norm(LEAD)
    low = body.lower()
    assert "blocked" in low, "the coordinator must address a WI worker's own BLOCKED result"
    assert "never idle on a wi-level blocked" in low or (
        "pre-integration blocked" in low and "never idle" in low
    ), "the coordinator must not idle on a WI-level BLOCKED - it must actively react"
    assert "manifest dependency" in low and "module-coordination-ledger" in body, (
        "the manifest-dependency BLOCKED case must still be named and pointed at the ledger snippet"
    )
    assert "ledger-unaware" in low, (
        "the coordinator must stay ledger-unaware even while reacting to a WI-level BLOCKED"
    )
    assert "relay" in low and "unchanged" in low, (
        "the manifest-dependency BLOCKED must still relay up to odoo-coding unchanged"
    )


def test_coordinator_monitors_wi_workers_on_a_live_task_list():
    """RESTORE of the topology this file originally pinned.

    A prior pass replaced this with "test_coordinator_keeps_own_live_task_list_not_a_teammate_board",
    asserting the coordinator explicitly disclaims Ask 2 (team-lead tracking) because it launches
    no teammates. That was the false-premise topology; the coordinator DOES launch three teammates
    and therefore IS a module lead that tracks them.

    RESTORED assertion: the coordinator tracks its own dispatched WI workers on a live task
    list, and reads each result from its own launch call's return value - it has no other channel
    to them and they have none to it."""
    body = _norm(LEAD)
    assert "spawner-completion-contract.md" in body, (
        "the coordinator launches agents, so R1/R2/R3 bind it - it must cite the SSOT"
    )
    assert "execution-tasklist-contract.md" in body, (
        "the coordinator must reference the live-task-list SSOT contract"
    )
    assert "task list" in body.lower(), "the coordinator must monitor WI workers on a live task list"
    low = body.lower()
    assert re.search(
        r"read (?:each|its|the|every)[\w' ]*result from (?:your|its) own launch call's return "
        r"value", low
    ), (
        "the coordinator must state the ONE channel it has to a teammate: its own launch call's "
        "return value"
    )
    assert re.search(r"no teammate (?:messages|can message|ever messages) you", low), (
        "the coordinator must state that no teammate can message it - otherwise it waits for a "
        "push that never arrives"
    )


def test_coordinator_commits_module_via_skill_git_ops_and_returns_sha():
    """New contract (worktree-graph refactor): the coordinator COMMITS its module by INVOKING the
    git-toolkit:git-ops skill (request-only), then returns the SHA to odoo-coding. It MUST NOT run
    raw git and MUST NOT dispatch a git leaf agent directly."""
    body = _norm(LEAD)
    low = body.lower()
    assert "git-toolkit:git-ops" in body, (
        "the coordinator must COMMIT its module by invoking the git-toolkit:git-ops skill"
    )
    assert "commit" in low, "the coordinator must state it COMMITS its module"
    # It returns the SHA up to odoo-coding (which no longer re-commits).
    assert "odoo-coding" in body and "sha" in low, (
        "the coordinator must return the commit SHA to odoo-coding"
    )
    # Request-only: it does not run raw git and does not cold-spawn a git leaf agent.
    assert "git-operator" not in body, (
        "odoo-coder.md must not name a git-toolkit leaf agent (git-toolkit owns internal naming; "
        "consumers route only through git-ops)"
    )
    assert (
        "not dispatch" in low or "must not dispatch" in low or "never dispatch" in low
    ) and "git leaf" in low, (
        "the coordinator must state it does NOT dispatch a git leaf agent directly (generic - no "
        "leaf-agent name required)"
    )
    assert "raw git" in low or "never raw git" in low or "not run raw git" in low, (
        "the coordinator must state it never runs raw git (only invokes git-ops)"
    )


def test_workers_are_hard_leaves():
    """All three teammates must declare themselves HARD LEAVES - the invariant that a leaf launches
    no sub-agent is independent of any depth-cap framing, so this checks the invariant under any of
    its equivalent phrasings rather than pinning one exact wording."""
    _LAUNCHES_NOTHING_PHRASES = (
        "never launch", "launch no sub-agent", "launches no sub-agent", "launch nothing",
    )
    for path in (TEST_WRITER, BACKEND, FRONTEND):
        body = _norm(path).lower()
        assert "hard leaf" in body or "hard leaves" in body, (
            f"{path.name} must declare it is a HARD LEAF"
        )
        assert any(phrase in body for phrase in _LAUNCHES_NOTHING_PHRASES), (
            f"{path.name} must state it launches no sub-agent (any equivalent phrasing)"
        )


# D1/D4: the dispatch unit is the NODE, never the module - a node may span one module, part of
# one, or several (the module is a PROPERTY of a node, not the outer/dispatch unit).
_ONE_CODER_PER_NODE_RE = re.compile(r"(?i)\bone\b.{0,30}?odoo-coder.{0,30}?per\s+(?:work\s+)?node")
# A bare `"one" in low and "per node" in low` is satisfied by policy-INVERTING text like
# "odoo-coding may dispatch MORE THAN one odoo-coder per node" (asserts multiple coders per
# node - the opposite rule) - "one" and "per node" both still appear as substrings. Explicitly
# reject the cardinality-inverting qualifier.
_MULTI_CODER_PER_NODE_INVERSION_RE = re.compile(
    r"(?i)(more\s+than\s+one|multiple|two\s+or\s+more)\b.{0,40}?odoo-coder.{0,40}?per\s+(?:work\s+)?node"
)
# The RETIRED per-module cardinality claim must not be resurrected anywhere in odoo-coding -
# regardless of "one" vs "more than one", a claim that odoo-coder is dispatched PER MODULE
# restores the exact constraint D4 abolished.
_CODER_PER_MODULE_CARDINALITY_RE = re.compile(r"(?i)\bodoo-coder\b.{0,40}?per\s+module")


def test_coding_dispatches_one_coder_per_node_for_every_node():
    """odoo-coding launches ONE odoo-coder COORDINATOR per NODE - for EVERY node, whatever module(s)
    it touches - with no single-stack direct-to-worker bypass and no resurrected per-module
    dispatch-cardinality claim (D1/D4: the wave layer is deleted and the module is a PROPERTY of a
    node, never the dispatch unit)."""
    body = _text(CODING)
    low = body.lower()
    assert "odoo-coder" in body, "odoo-coding must launch the odoo-coder coordinator"
    assert _ONE_CODER_PER_NODE_RE.search(low), (
        "odoo-coding must dispatch ONE odoo-coder per (work) node - not merely mention \"one\" and "
        "\"per node\" separately anywhere in the doc"
    )
    assert not _MULTI_CODER_PER_NODE_INVERSION_RE.search(low), (
        "odoo-coding text asserts MORE THAN ONE odoo-coder per node, which INVERTS the "
        "one-coordinator-per-node rule"
    )
    assert not _CODER_PER_MODULE_CARDINALITY_RE.search(low), (
        "odoo-coding must NOT resurrect a per-module odoo-coder dispatch-cardinality claim - the "
        "dispatch unit is the node; the module is only a property of it"
    )
    assert "every node" in low, (
        "odoo-coding must launch the coordinator for EVERY node (not just full-stack)"
    )
    # The old single-stack direct-dispatch topology must be gone.
    assert not re.search(r"single-stack module\s*->\s*launch", low), (
        "odoo-coding must NOT keep the old single-stack direct-to-worker dispatch - every node "
        "goes through the odoo-coder coordinator now."
    )
    # odoo-coding must NOT own the intra-node WI split (that is the coordinator's).
    assert "does not split" in low, (
        "odoo-coding must state it does NOT split a node into WIs - the coordinator owns that."
    )


def test_orchestration_ssot_reflects_node_primary_topology():
    """The orchestration SSOT (skill_tool_deps.json) odoo-coding spawns list names the coordinator +
    all three teammates, and states the dispatch cardinality as ONE odoo-coder per NODE - never per
    module (D1/D4: the dispatch unit is the node; the module is a property of it, not a tier).

    (Earlier note, still true: the agent-side dispatch axis is spelled `spawns_agents`, which
    declares the coordinator's edges rather than denying them - there is no `agents.odoo-coder.spawns
    == []` key to assert against.)"""
    orch = json.loads(_text(DEPS))["orchestration"]["odoo-coding"]
    spawns = " ".join(orch["spawns"])
    low = spawns.lower()
    assert (
        "odoo-coder" in spawns and "odoo-test-writer" in spawns
        and "odoo-backend-coder" in spawns and "odoo-frontend-coder" in spawns
    ), (
        "odoo-coding orchestration spawns must name the coordinator + all three teammates "
        "(odoo-test-writer + odoo-backend-coder + odoo-frontend-coder)"
    )
    assert "coordinator" in low, "the spawns entry must mark odoo-coder as the per-node coordinator"
    assert "per node" in low, "the dispatch note must say ONE odoo-coder per node"
    assert "per module" not in low, (
        "the spawns entry must NOT resurrect a per-module dispatch-cardinality claim - the "
        "dispatch unit is the node"
    )


def test_module_graph_states_two_tier_axis():
    """odoo-module-graph.md must state the two-tier axis: module is the OUTER unit; the WI is
    odoo-coder's INTERNAL intra-module unit (1 module -> 1..N WIs)."""
    text = _text(MODULE_GRAPH)
    low = " ".join(text.lower().split())
    assert "two-tier" in low, "odoo-module-graph.md must carry the two-tier decomposition axis section"
    assert "outer" in low and "node" in low, "the OUTER tier must be the NODE"
    assert re.search(r"outer tier\s*=\s*the node", low), (
        "the OUTER tier must be stated as the NODE, not the module - D1/D4 abolished the "
        "module-outer topology"
    )
    assert "internal" in low and ("work-item" in low or "wi" in low), (
        "the INNER tier (work-item) must be declared odoo-coder's INTERNAL unit"
    )
    assert "odoo-coder" in text, "the axis must name odoo-coder as the owner of the WI tier"
    # The module is a PROPERTY of a node, never a third tier of decomposition.
    assert "property" in low and "not a tier" in low, (
        "the file must state the module is a PROPERTY of a node, NOT a tier of decomposition"
    )
    assert "exactly two tiers" in low, (
        "the file must state the decomposition has EXACTLY TWO tiers (no third tier)"
    )
    assert not re.search(r"\bthird tier\b|\bthree[\s-]tiers?\b", low), (
        "odoo-module-graph.md must NOT introduce a third tier of decomposition"
    )
    # The conflict-freedom argument must name DISJOINT FILE SCOPES, not the module boundary (H3):
    # a node - and a WI within it - MAY span modules, so the module boundary can no longer be the
    # thing that keeps the outer DAG conflict-free.
    assert "disjoint file scope" in low, (
        "the conflict-freedom argument must name DISJOINT FILE SCOPES as what keeps the outer DAG "
        "conflict-free, not the module boundary"
    )
    assert not re.search(r"\bwi\b[^.]{0,150}\bnever\b[^.]{0,150}\bspan\b[^.]{0,30}\btwo modules\b", low), (
        "odoo-module-graph.md must NOT restate the retired module-boundary conflict-freedom claim "
        "('a WI can never span two modules') - a WI MAY span modules within a node"
    )


def test_survey_field_closes_the_whole_forwarding_chain():
    """RESTORE of the topology this file originally pinned.

    A prior pass required odoo-coder to state it "reads SURVEY itself before authoring" and "never
    a separate agent" - built on the false premise that odoo-coder authors the RED test inline
    instead of dispatching odoo-test-writer. Restored: SURVEY reaches odoo-coder AND every brief it
    hands a teammate AND odoo-test-writer's own brief-carries section - closing the whole chain to
    the teammate that actually authors the RED test and most needs the grounding.

    INVERTED (forward-list half): this previously matched one frozen contiguous literal -
    `forward `WORKTREE_PATH`, `INSTANCE_HANDLE`, `DESIGN_DOC`, `MASTER_DESIGN_DOC`, `SURVEY`,
    `WORKLOG`` - which pinned the forward list to exactly the fields it already named and made
    ADDING a dropped field (MODULE SCOPE / REQUEST, which a leaf cannot work without) fail here.
    A guard that forbids completing the very list it guards enforces the gap. It now checks
    MEMBERSHIP in the teammate briefs odoo-coder actually hands out, in any order or wording."""
    coder = _norm(LEAD)
    assert "SURVEY" in coder, "odoo-coder.md must name SURVEY in its inbound brief-carries prose"
    fences = _dispatch_fences(LEAD)
    assert fences, (
        "odoo-coder.md must carry its teammate briefs as literal dispatch fences - a prose list is "
        "not something a coordinator can fill field by field"
    )
    for field in ("SURVEY", "WORKTREE_PATH", "DESIGN_DOC", "MASTER_DESIGN_DOC", "WORKLOG",
                  "INSTANCE_HANDLE"):
        assert field in fences, (
            f"odoo-coder.md's teammate dispatch briefs must carry `{field}` - a field absent from "
            "every brief is a field no teammate ever receives"
        )
    test_writer = _text(TEST_WRITER)
    assert "SURVEY" in test_writer, (
        "odoo-test-writer.md must name SURVEY - the agent that authors the RED test and most "
        "needs the grounding"
    )


def test_wi_worker_dependency_gate_defines_green_against_status_enum():
    """D5 - the backend-before-frontend gate said the prerequisite must 'return green' with no
    definition against the actual status enum. Must now define green == status: DONE explicitly,
    and name that BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT are never green."""
    low = _norm(LEAD).lower()
    assert "defined precisely" in low or "the only value this schedule reads as green" in low, (
        "the dependency gate must explicitly DEFINE 'green' rather than leave it a bare adjective"
    )
    assert "status: done" in low, (
        "'green' must be defined as status: DONE against the Continuation Contract enum"
    )
    assert (
        "blocked`, `needs_context`, and `needs_next` are never green" in low
        or ("never green" in low and "blocked" in low)
    ), "the gate must state BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT are never green"


def test_coordinator_verifies_red_test_path_before_forwarding():
    """RESTORE of the topology this file originally pinned.

    A prior pass moved this gate to sit between the coordinator's OWN test-authoring and OWN
    code-writing steps - built on the false premise that there is no separate coder to forward the
    path TO. Restored: a RED_TEST_PATH present but pointing at a nonexistent file must be caught
    BEFORE FORWARDING it to a separate coder agent, treated exactly like "no test handed in" (the
    same bounded re-dispatch path), never forwarded unverified."""
    low = _norm(LEAD).lower()
    assert "verify it resolves to a real file" in low, (
        "odoo-coder.md must state the RED_TEST_PATH is verified to resolve to a real file before "
        "being forwarded to a coder"
    )
    assert "treat this exactly as" in low and "no test handed in" in low, (
        "an unresolved RED_TEST_PATH must be treated exactly like the 'no test handed in' case"
    )
    # Both coder leaves must also treat a present-but-invalid path the same as an absent one.
    for path in (BACKEND, FRONTEND):
        cbody = _norm(path).lower()
        assert "does not resolve to a real file" in cbody or "does not resolve to a real" in cbody, (
            f"{path.name} must treat a RED_TEST_PATH that does not resolve to a real file the "
            "same as a brief that carries no test at all"
        )


def test_coordinator_reassigns_sibling_contradiction_not_just_the_complainer():
    """RESTORE of the topology this file originally pinned.

    A prior pass reframed the re-verification target as an "accused sibling WI" being re-looped
    (not re-dispatched) - built on the false premise that there is no separate worker to dispatch.
    Restored: on contradicting sibling reports, the re-DISPATCH loop must target the ACCUSED
    sibling's WORKER first, and forbid "loop[ing] the complaining WORKER alone" against unchanged
    ground truth."""
    low = _norm(LEAD).lower()
    assert "contradicts a sibling" in low or "contradicting sibling" in low, (
        "odoo-coder.md must name the sibling-contradiction case explicitly"
    )
    assert "accused sibling" in low, (
        "the re-dispatch target on a sibling contradiction must be named: the ACCUSED sibling, "
        "not merely the complaining worker"
    )
    assert "never loop the complaining worker alone against ground truth" in low or (
        "never loop the complaining worker alone" in low
    ), (
        "the rule must explicitly forbid re-dispatching only the complaining worker against "
        "unchanged ground truth"
    )


def test_wi_checkpoint_rule_present():
    """M1c (12-design-final.md) - uncommitted work must not survive a turn boundary.

    Root cause this protects: odoo-coder authors 1..N work-items per node inside ONE turn; if
    that turn ends early (context limit, an interrupt, a crash) with no commit yet, every WI
    written so far is lost - a stall costs the WHOLE NODE, not just the WI in flight (D4: the
    coordinator's unit is the node, which may span several modules). The fix: before ending its
    turn for ANY reason (DONE, NEEDS_NEXT, BLOCKED, or a budget cutoff), the coordinator must
    request a checkpoint commit of everything written so far via Skill(git-toolkit:git-ops), so a
    stall costs at most one work-item.

    What this proves: the rule is stated in the prose an executing agent reads. What it does NOT
    prove: that a commit actually happens at runtime - the only evidence for that is on disk
    (`git log <base>..HEAD` / `git status --short`), exactly as 12-design-final.md's own M1c guard
    note says."""
    low = _norm(LEAD).lower()
    assert "uncommitted work must not survive a turn boundary" in low, (
        "odoo-coder.md must state the M1c checkpoint rule: uncommitted work must not survive a "
        "turn boundary"
    )
    assert "done, needs_next, blocked" in low, (
        "the checkpoint rule must cover ALL terminal-status exits (DONE, NEEDS_NEXT, BLOCKED, or "
        "a budget cutoff), not only the happy-path DONE"
    )
    assert "skill(git-toolkit:git-ops)" in low, (
        "the checkpoint commit must be requested via Skill(git-toolkit:git-ops), same as the "
        "final integrated-green commit"
    )
    assert "a stall must cost one work-item, never the node" in low, (
        "the rule must state the bound explicitly: a stall costs at most one work-item, never "
        "the whole node"
    )


def test_coordinator_done_honesty_requires_scope_coverage_and_wi_accounting():
    """D7/D2 - a module covering only PART of the requested scope could pass all three
    DONE-honesty checks (file list / integrated-test verdict / SHA), and a premature 2-of-3 DONE
    was undetectable upstream (the WI list is odoo-coder's PRIVATE tracking). The DONE-honesty
    gate must now ALSO require (a) an explicit requirement-to-WI coverage mapping against
    REQUEST/frontendRequest, and (b) a stated WI-count + terminal-status accounting - both
    forwarded to odoo-coding so a partial-scope or partial-fan-out DONE is a failed contract, not
    silently trusted."""
    low = _norm(LEAD).lower()
    assert "check delivered scope against `request`" in low or (
        "delivered scope against" in low and "request" in low
    ), "odoo-coder.md must require checking delivered scope against REQUEST/frontendRequest"
    assert "wi count dispatched" in low or "wi count" in low, (
        "odoo-coder.md must require stating the WI count dispatched as part of its report"
    )
    assert "failed contract" in low, (
        "the extended honesty gate must still be framed as a failed-contract check"
    )
    # The exact V1b constructed passing message pattern must now be named as INSUFFICIENT.
    assert "implemented the requested change to" in low, (
        "odoo-coder.md must name the exact under-specified prose pattern (the V1b constructed "
        "message) as failing the honesty gate, not merely describe the rule abstractly"
    )
    # odoo-coding's own receiver-side gate must mirror the same two checks.
    coding_low = _norm(CODING).lower()
    assert "wi count" in coding_low and "terminal-status accounting" in coding_low, (
        "odoo-coding SKILL.md's own DONE-honesty gate must mirror the WI-count + terminal-status "
        "accounting requirement, not only the coordinator's own prose"
    )
    assert "requirement-coverage mapping" in coding_low or "request" in coding_low, (
        "odoo-coding SKILL.md's own DONE-honesty gate must require the requirement-coverage "
        "mapping, not just the file-list/SHA/test-verdict trio"
    )


def test_wi_is_not_an_outer_layer_unit():
    """The WI concept must NOT appear as an OUTER-layer decomposition unit in
    odoo-planning / plan-mode-schema / phase-p / run-harness. A bare 'work-item'
    mention is allowed ONLY as a disclaimer that it is odoo-coder-internal; the outer-WI
    ANTIPATTERNS (per-WI, WI list, MODULE SET, ...) must be absent."""
    offenders = []
    for label, path in OUTER_LAYER_FILES.items():
        low = _text(path).lower()
        for pat in OUTER_WI_ANTIPATTERNS:
            if re.search(pat, low):
                offenders.append(f"{label}: {pat!r}")
        # Any surviving 'work-item' / bare 'WI' mention must be framed as odoo-coder-internal.
        if re.search(r"\bwork-item\b|\bwi\b|\bwis\b", low):
            assert "odoo-coder" in low and ("internal" in low or "private" in low), (
                f"{label}: mentions the work-item but does not frame it as odoo-coder's "
                f"INTERNAL/PRIVATE unit - the outer layer must think in MODULES only."
            )
    assert not offenders, (
        "outer-layer files must not frame the unit as a work-item; offenders: " + ", ".join(offenders)
    )
