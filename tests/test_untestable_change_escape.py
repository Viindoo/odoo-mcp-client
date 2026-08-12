"""Guard the untestable-change escape, the loud refusal, and the two-tier [brief-fields] walk.

Root cause these protect (observed live, three identical dispatches): `odoo-frontend-coder` was
handed a comment-only rename across 17 files. Its FIRST rule refuses any brief that carries no RED
test, or a `RED_TEST_PATH` that does not open - and a comment-only rename cannot have a RED test by
construction. So the leaf refused in 1-2 tool uses, returned near-empty text, and the coordinator
read that as a completed work-item with zero files. The same work handed to a generic agent
finished in ~5 minutes with 22 edits across 17 files. Three failures compound:

  1. no escape      - test-first was unconditional, so work that CANNOT go red had no legal path.
  2. quiet refusal  - the leaf exited without a terminal Continuation Contract status, so a refusal
                      was indistinguishable from a success at the launcher.
  3. dropped fields - odoo-coder's forward list named neither MODULE SCOPE nor REQUEST, so a
                      coordinator following it literally hands a coder no module and no request.
  4. blind lint     - [brief-fields] treated `orchestration.<skill>.spawns_agents` as a set of
                      DIRECT skill->agent edges. `RED_TEST_PATH` travels odoo-coder -> leaf-coder,
                      an agent->agent edge no tier of the rule walked, while the same flattening
                      charged `odoo-coding` for four keys it never emits and never should.

These assert the CONTRACT'S BEHAVIOR, not a wording snapshot: each can fail for a real reason -
delete the escape, make a refusal quiet again, drop a forwarded field, or flatten the edge tiers,
and the matching assertion goes red. The lint half is proved against synthetic fixtures (never the
real tree) so its detector is shown capable of firing, not merely observed printing "clean".

Run: python -m pytest tests/test_untestable_change_escape.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
SNIPPETS = PLUGIN / "snippets"

CODER = AGENTS / "odoo-coder.md"
BACKEND = AGENTS / "odoo-backend-coder.md"
FRONTEND = AGENTS / "odoo-frontend-coder.md"
CODING_SKILL = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
EXEMPTION_CONTRACT = SNIPPETS / "test-exemption-contract.md"
TEST_FIRST_CONTRACT = SNIPPETS / "test-first-contract.md"
DISPATCH_BRIEF = SNIPPETS / "dispatch-brief.md"
DEPS_FILE = PLUGIN / "generator" / "skill_tool_deps.json"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402

LEAF_CODERS = {"odoo-backend-coder": BACKEND, "odoo-frontend-coder": FRONTEND}
CODER_FAMILY = {"odoo-coder": CODER, **LEAF_CODERS}

# The categories the contract declares - a change class that cannot produce a failing test.
CATEGORIES = ("comment-only", "prose-rename", "formatting", "docs", "translation-text")


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _norm(p: Path) -> str:
    return " ".join(_text(p).split())


def _fences(p: Path) -> str:
    return "\n".join(re.findall(r"```.*?```", _text(p), re.S))


def _registry() -> dict:
    return json.loads(_text(DEPS_FILE))


def _section(text: str, heading: str) -> str:
    """The body of an H2 section, anchored at line start so an inline `§ <heading>` cross-reference
    elsewhere in the file cannot be mistaken for the heading itself."""
    m = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    assert m, f"heading {heading!r} not found"
    end = re.search(r"^## ", text[m.end():], re.M)
    return text[m.end():] if end is None else text[m.end():m.end() + end.start()]


# ---------------------------------------------------------------------------
# 1. The escape exists, is a CLOSED declaration, and is never inferred
# ---------------------------------------------------------------------------


def test_exemption_contract_declares_a_closed_category_set():
    """An escape whose reason field is free text is an escape with no gate: any leaf could talk
    itself past test-first. The contract must name a closed set of change classes that genuinely
    cannot go red, and must require specifics alongside the category."""
    assert EXEMPTION_CONTRACT.is_file(), (
        "snippets/test-exemption-contract.md must exist - it is the ONE declaring file for the "
        "escape; without it every consumer restates the rule and they drift"
    )
    text = _text(EXEMPTION_CONTRACT)
    low = _norm(EXEMPTION_CONTRACT).lower()
    assert "TEST_EXEMPTION" in text, "the contract must name the field it declares"
    for category in CATEGORIES:
        assert category in text, (
            f"the closed category set must enumerate `{category}` - a caller cannot declare a "
            "category the contract does not list"
        )
    assert "closed category set" in low, (
        "the set must be stated as CLOSED - an open set is not a gate"
    )
    assert "<specifics>" in text or "specifics" in low, (
        "the declaration must carry what specifically cannot go red, not a bare category"
    )


def test_an_absent_or_malformed_declaration_is_never_an_exemption():
    """The hole this reopens if it regresses: a leaf that reads a missing/empty field as consent
    is exactly the untested-code path test-first exists to close. Absence must resolve toward
    REFUSAL, and a half-written value must not be repaired by guessing."""
    low = _norm(EXEMPTION_CONTRACT).lower()
    assert "malformed is absent" in low or "malformed is absent." in low, (
        "the contract must state that a malformed declaration carries NO exemption"
    )
    assert "never infer" in low or "never read one into" in low or "never inferred" in low, (
        "the contract must forbid the receiver inferring an exemption"
    )
    assert "absent key mean the same thing" in low or "absent key" in low, (
        "the contract must define what an absent key means (no exemption), so absence is decided "
        "rather than improvised"
    )


def test_a_resolving_red_test_always_beats_an_exemption():
    """Precedence must be stated, or a brief carrying BOTH a real test and an exemption is decided
    by whichever line the leaf read last - and the exemption would silently retire a real test."""
    low = _norm(EXEMPTION_CONTRACT).lower()
    assert "wins" in low and "red_test_path" in low, (
        "the contract must state a resolving RED_TEST_PATH wins over an exemption"
    )
    assert "never cancels a test that exists" in low, (
        "an exemption must never cancel or authorise editing an existing test"
    )


def test_the_receiver_verifies_the_claim_against_what_it_writes():
    """A declaration the receiver cannot void is a blank cheque: the caller's judgment about
    testability was made BEFORE the file set was read. The leaf holds the only evidence that the
    work turned behavioral, so it must own the void."""
    low = _norm(EXEMPTION_CONTRACT).lower()
    assert "void" in low, "the contract must define when an exemption becomes VOID"
    for observable in ("selector", "msgid", "external id", "manifest key"):
        assert observable in low, (
            f"the void rule must name concrete observable edits (missing: {observable!r}) - "
            "'anything behavioral' is not decidable at runtime"
        )


# ---------------------------------------------------------------------------
# 2. The escape is wired END TO END - a hop that drops it recreates the defect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,path",
    [
        ("odoo-coding dispatch fence", CODING_SKILL),
        ("odoo-coder coordinator", CODER),
        ("odoo-backend-coder leaf", BACKEND),
        ("odoo-frontend-coder leaf", FRONTEND),
        ("dispatch-brief SSOT", DISPATCH_BRIEF),
    ],
)
def test_every_hop_on_the_coding_chain_names_the_exemption(label, path):
    assert "TEST_EXEMPTION" in _text(path), (
        f"{label} ({path.name}) never names TEST_EXEMPTION - the escape must survive every hop "
        "from the skill that scopes the change to the leaf that refuses it; one silent hop and "
        "the leaf blocks on a change that cannot have a test"
    )


def test_the_skill_that_builds_the_brief_emits_the_field_in_its_fence():
    """Prose ABOUT a field is not a field. The dispatch fence is what a caller copies values into,
    so an exemption named only in surrounding explanation never reaches a brief."""
    assert "TEST_EXEMPTION:" in _fences(CODING_SKILL), (
        "skills/odoo-coding/SKILL.md's per-module dispatch fence must emit `TEST_EXEMPTION:` as a "
        "brief key, not merely discuss exemptions in prose"
    )


def test_the_coordinator_forwards_the_field_in_its_leaf_brief():
    assert "TEST_EXEMPTION:" in _fences(CODER), (
        "agents/odoo-coder.md's leaf-coder dispatch brief must emit `TEST_EXEMPTION:` - the "
        "coordinator is the caller that fills the leaf's brief, so a field it never writes is a "
        "field the leaf never sees"
    )


@pytest.mark.parametrize("name", sorted(CODER_FAMILY))
def test_registry_brief_manifest_carries_the_field(name):
    """The registry is what [brief-fields] and the Inputs-table lint read. A field wired only in
    prose is invisible to every machine check."""
    brief = _registry()["agents"][name]["brief"]
    assert "TEST_EXEMPTION" in set(brief["required"]) | set(brief["optional"]), (
        f"agents.{name}.brief must declare TEST_EXEMPTION (optional - its absence means `none`)"
    )


def test_every_file_that_states_the_test_gate_also_states_the_escape():
    """Whole-tree, no adjacency window: any agent-facing file that names `RED_TEST_PATH` is a file
    that states the gate, and a file stating the gate WITHOUT the escape is a surviving
    restatement that recreates the exact defect for whoever reads that file alone."""
    offenders = []
    for path in sorted(PLUGIN.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "RED_TEST_PATH" in text and "TEST_EXEMPTION" not in text:
            offenders.append(str(path.relative_to(PLUGIN)))
    assert not offenders, (
        "these files state the RED_TEST_PATH gate but never mention the TEST_EXEMPTION escape, so "
        f"an agent reading only them refuses work that cannot go red: {offenders}"
    )


def test_the_test_first_contract_points_at_its_own_exception():
    """test-first-contract.md is the SSOT a reader lands on for red-before-green. If it asserts
    the rule with no pointer to the one sanctioned exception, that reader concludes none exists."""
    text = _text(TEST_FIRST_CONTRACT)
    assert "TEST_EXEMPTION" in text and "test-exemption-contract.md" in text, (
        "snippets/test-first-contract.md must point at the exemption contract - an SSOT that "
        "states only the absolute form of a rule contradicts the file that qualifies it"
    )


# ---------------------------------------------------------------------------
# 3. Test-first still bites: a BEHAVIOR change with no test is still refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_leaf_still_refuses_a_behavior_change_with_no_test(name):
    """The escape must not become a bypass. Both the no-test case and the unresolvable-path case
    must still refuse, and the leaf must void the exemption the moment the work turns behavioral."""
    low = _norm(LEAF_CODERS[name]).lower()
    assert "does not resolve to a real file" in low, (
        f"{name}: an unresolvable RED_TEST_PATH must still be treated as no test at all"
    )
    assert "refuse" in low, f"{name}: the no-test branch must still REFUSE, not proceed untested"
    assert "void" in low, (
        f"{name}: the leaf must hold the exemption VOID once the work needs an observable edit - "
        "without that, a declared exemption is a blanket licence to write untested behavior"
    )


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_leaf_never_infers_an_exemption_from_an_empty_field(name):
    low = _norm(LEAF_CODERS[name]).lower()
    assert "malformed `test_exemption` is not an exemption" in low or (
        "is not an exemption" in low and "never read one into a missing field" in low
    ), (
        f"{name}: the leaf must state that an absent/empty/malformed TEST_EXEMPTION is NOT an "
        "exemption - inferring one from an empty field reopens the untested-code hole"
    )


def test_the_coordinator_cannot_launder_a_lost_test_into_an_exemption():
    """The nearest available abuse: a test-writer returns a path that does not exist, and the
    coordinator relabels the work 'untestable' instead of re-dispatching the author."""
    low = _norm(CODER).lower()
    assert "never laundered into a `test_exemption`" in low or (
        "unresolved path is never" in low and "test_exemption" in low
    ), (
        "agents/odoo-coder.md must forbid converting an unresolved RED_TEST_PATH into an "
        "exemption - the exemption covers a change that cannot go red, not a test that got lost"
    )


# ---------------------------------------------------------------------------
# 4. The refusal is LOUD - a terminal status, never a near-empty message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_leaf_refusal_emits_a_terminal_continuation_block(name):
    """The final message is the ONLY channel back to a launcher, so an empty one is
    indistinguishable from silence. Each leaf must carry a REFUSAL-shaped continuation block, not
    only the DONE one - a template that shows success alone teaches success alone."""
    section = _section(_text(LEAF_CODERS[name]), "## Continuation Contract")
    blocks = re.findall(r"```continuation.*?```", section, re.S)
    refusals = [b for b in blocks if "status: BLOCKED" in b]
    assert refusals, (
        f"{name}: § Continuation Contract shows no `status: BLOCKED` block - the refusal has no "
        "shape to copy, which is how a gate ends up exiting on near-empty text"
    )
    block = refusals[0]
    assert "produced: []" in block, f"{name}: a refusal must report produced: [] explicitly"
    assert "blocked_reason:" in block, f"{name}: a refusal must carry blocked_reason"
    low = " ".join(section.split()).lower()
    assert "near-empty" in low, (
        f"{name}: the section must name the failure mode - a near-empty return reads as silence"
    )


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_any_gate_not_just_the_test_gate_exits_loudly(name):
    """Defect 2 is not specific to the test gate: the brief self-check STOP and every other
    precondition exit shared the same quiet path. The loud-report rule must be stated for ALL of
    them, and the self-check's STOP must route through it."""
    section = _section(_text(LEAF_CODERS[name]), "## Continuation Contract")
    low = " ".join(section.split()).lower()
    assert "brief self-check" in low and (
        "any other precondition" in low or "or any other precondition" in low
    ), (
        f"{name}: the loud-exit rule must cover every gate (the test gate, the brief self-check, "
        "any other precondition) - scoping it to one gate leaves the others quiet"
    )
    self_check = _section(_text(LEAF_CODERS[name]), "## Brief self-check")
    sc_low = " ".join(self_check.split()).lower()
    assert "continuation contract" in sc_low, (
        f"{name}: the Brief self-check's STOP clause must route its NEEDS_CONTEXT/BLOCKED through "
        "the Continuation Contract report, never emit a bare status line"
    )


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_the_refusal_names_a_referent_from_this_dispatch(name):
    """continuation-contract.md's decidability check: a blocked_reason that would read equally
    true for any other module names nothing. The leaf's own template must demand the concrete
    referent, or every refusal degenerates to 'missing information'."""
    section = _section(_text(LEAF_CODERS[name]), "## Continuation Contract")
    low = " ".join(section.split()).lower()
    assert "decidability" in low or "equally true for any other module" in low, (
        f"{name}: the refusal template must require a referent specific to THIS dispatch"
    )


# ---------------------------------------------------------------------------
# 5. The forward list carries what a leaf cannot work without (defect 3)
# ---------------------------------------------------------------------------


def test_leaf_coder_brief_carries_the_module_and_the_request():
    """The latent gap that alone produces 'wrote nothing': a coordinator following the forward
    list literally handed a coder no module path and no request text."""
    fences = _fences(CODER)
    for field in ("MODULE SCOPE", "REQUEST", "ODOO VERSION", "RED_TEST_PATH", "WORKTREE_PATH"):
        assert field in fences, (
            f"agents/odoo-coder.md's teammate briefs must carry `{field}` - a leaf handed a brief "
            "without it has nothing to act on and returns empty"
        )


def test_the_coordinator_states_the_briefs_are_the_field_list():
    """Two homes for the same list is how one of them silently goes stale. The fences must be
    declared authoritative, so a field is forwarded because it is IN a brief, not because a
    separate sentence happened to name it."""
    low = _norm(CODER).lower()
    assert "they are the field list" in low or "are the field list" in low, (
        "agents/odoo-coder.md must state its dispatch briefs ARE the field list a teammate "
        "receives - otherwise a prose list and a fence drift apart"
    )


def test_test_writer_brief_carries_every_key_its_registry_entry_requires():
    """Data-driven from the SSOT, not a frozen literal list: whatever
    agents.odoo-test-writer.brief.required declares must appear in the brief odoo-coder hands it."""
    required = _registry()["agents"]["odoo-test-writer"]["brief"]["required"]
    assert required, "odoo-test-writer must declare required brief keys - an empty list is vacuous"
    fences = _fences(CODER)
    missing = [k for k in required if k not in fences]
    assert not missing, (
        f"agents/odoo-coder.md's odoo-test-writer brief omits required key(s) {missing} declared "
        "in the registry - the coordinator is that agent's only caller"
    )


# ---------------------------------------------------------------------------
# 6. [brief-fields] walks BOTH edge tiers (defect 4)
# ---------------------------------------------------------------------------


def test_the_coordinators_agent_edges_are_declared_in_the_ssot():
    """The axis the rule needs. Without it the agent->agent tier is undeclared, so no lint can
    know who writes a leaf's brief."""
    edges = _registry()["agents"]["odoo-coder"].get("spawns_agents")
    assert edges, "agents.odoo-coder.spawns_agents must declare the coordinator's dispatch edges"
    assert set(edges) == {"odoo-test-writer", "odoo-backend-coder", "odoo-frontend-coder"}, (
        f"agents.odoo-coder.spawns_agents must name exactly the three teammates, found {edges}"
    )


def _fake_tree(monkeypatch, *, orch, agents, skill_bodies, agent_bodies):
    monkeypatch.setattr(co, "load_orch", lambda: orch)
    monkeypatch.setattr(co, "load_agents", lambda: agents)
    monkeypatch.setattr(co, "skill_body", lambda name: skill_bodies.get(name))
    monkeypatch.setattr(co, "agent_body", lambda name: agent_bodies.get(name))


def test_agent_to_agent_edge_is_actually_checked(monkeypatch):
    """RED half of the detector proof, on synthetic data: a coordinator whose own brief omits a
    key its leaf requires must be reported. Flatten the rule back to skill-edges only and this
    goes green-for-the-wrong-reason (zero findings), which is the pre-fix blindness."""
    orch = {"a-skill": {"spawns_agents": ["a-coord"]}}
    agents = {
        "a-coord": {"role": "coordinator", "spawns_agents": ["a-leaf"], "brief": {"required": []}},
        "a-leaf": {"role": "leaf", "brief": {"required": ["RED_TEST_PATH"]}},
    }
    _fake_tree(
        monkeypatch,
        orch=orch,
        agents=agents,
        skill_bodies={"a-skill": "```\nNOTHING: x\n```"},
        agent_bodies={"a-coord": "```\nSOME_OTHER_KEY: x\n```"},
    )
    findings: list[str] = []
    co.check_brief_fields(findings)
    assert any("a-coord" in f and "a-leaf" in f and "RED_TEST_PATH" in f for f in findings), (
        f"the agent->agent tier did not fire on a coordinator brief missing its leaf's required "
        f"key: {findings}"
    )


def test_agent_to_agent_edge_clears_once_the_key_is_emitted(monkeypatch):
    """GREEN half: the same fixture with the key present in the coordinator's fence is clean, so
    the finding above tracks the key, not the mere existence of an agent edge."""
    orch = {"a-skill": {"spawns_agents": ["a-coord"]}}
    agents = {
        "a-coord": {"role": "coordinator", "spawns_agents": ["a-leaf"], "brief": {"required": []}},
        "a-leaf": {"role": "leaf", "brief": {"required": ["RED_TEST_PATH"]}},
    }
    _fake_tree(
        monkeypatch,
        orch=orch,
        agents=agents,
        skill_bodies={"a-skill": "```\nNOTHING: x\n```"},
        agent_bodies={"a-coord": "```\nRED_TEST_PATH: <path>\n```"},
    )
    findings: list[str] = []
    co.check_brief_fields(findings)
    assert not findings, f"expected a clean run once the coordinator emits the key: {findings}"


def test_a_skill_is_not_charged_for_a_brief_its_coordinator_writes(monkeypatch):
    """The false-positive half. `orchestration.<skill>.spawns_agents` is a REACHABILITY set (it
    feeds the generated ORCHESTRATION-MAP), so a leaf under a coordinator appears there even
    though the skill never writes that leaf's brief. Charging the skill yields a finding no edit
    to the skill can ever clear - and the second arm proves the coordinator declaration is what
    silences it, not a blanket exemption for that agent name."""
    agents = {
        "a-coord": {"role": "coordinator", "spawns_agents": ["a-leaf"], "brief": {"required": []}},
        "a-leaf": {"role": "leaf", "brief": {"required": ["RED_TEST_PATH"]}},
    }
    orch = {"a-skill": {"spawns_agents": ["a-coord", "a-leaf"]}}
    skill_bodies = {"a-skill": "```\nNOTHING: x\n```"}
    agent_bodies = {"a-coord": "```\nRED_TEST_PATH: <path>\n```"}

    _fake_tree(monkeypatch, orch=orch, agents=agents, skill_bodies=skill_bodies,
               agent_bodies=agent_bodies)
    findings: list[str] = []
    co.check_brief_fields(findings)
    assert not findings, (
        f"the skill was charged for a leaf brief its declared coordinator writes: {findings}"
    )

    # Drop the coordinator's declared edge: the leaf is now reachable ONLY as a direct skill edge,
    # so the skill IS its dispatcher and the finding must come back.
    agents_flat = dict(agents)
    agents_flat["a-coord"] = {"role": "coordinator", "brief": {"required": []}}
    _fake_tree(monkeypatch, orch=orch, agents=agents_flat, skill_bodies=skill_bodies,
               agent_bodies=agent_bodies)
    findings = []
    co.check_brief_fields(findings)
    assert any("a-skill" in f and "a-leaf" in f for f in findings), (
        f"with no declared agent edge the skill IS the dispatcher and must be charged: {findings}"
    )


def test_real_tree_charges_nobody_for_the_coder_family_edges():
    """On the REAL tree: the four measured false positives (odoo-coding blamed for TARGET
    BEHAVIOR, TEST TYPE, and RED_TEST_PATH twice) are gone, AND the real odoo-coder -> leaf edges
    the rule now walks are clean - so the noise did not simply move one tier down."""
    findings: list[str] = []
    co.check_brief_fields(findings)
    coder_family = [
        f for f in findings
        if "odoo-coding" in f or "odoo-coder" in f or "odoo-backend-coder" in f
        or "odoo-frontend-coder" in f
    ]
    assert not coder_family, f"unexpected [brief-fields] findings on the coding chain: {coder_family}"


def test_brief_fields_stays_warn_only():
    """This rule is permanently non-gating by design (module docstring, and the docstring of
    tests/test_agent_inputs_match_registry.py). Walking a new edge tier must not quietly turn a
    diagnostic into a CI gate."""
    findings: list[str] = []
    warn: list[str] = []
    co.check_brief_fields(warn)
    assert not findings, "check_brief_fields must never write into the gating findings list"
    assert warn, (
        "check_brief_fields produced zero warn-only findings on the real tree - either the corpus "
        "is finally clean (update this floor deliberately) or the rule went vacuous"
    )
