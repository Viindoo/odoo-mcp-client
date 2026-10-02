"""Guard the loud refusal, the leaf forward list, and the two-tier [brief-fields] walk.

Root cause these protect (observed live, three identical dispatches): `odoo-frontend-coder` was
handed a comment-only rename across 17 files, refused it at a precondition gate in 1-2 tool uses,
returned near-empty text, and the coordinator read that as a completed work-item with zero files.
The same work handed to a generic agent finished in ~5 minutes with 22 edits across 17 files. The
precondition that refused it is gone (coders write code only; whether a node owes tests is decided
by the coordinator from the actual diff - snippets/test-sensitivity-contract.md § No test leg,
guarded in tests/test_test_sensitivity_contract.py). Three failures remain worth guarding:

  1. quiet refusal  - a leaf exited without a terminal Continuation Contract status, so a refusal
                      was indistinguishable from a success at the launcher.
  2. dropped fields - odoo-coder's forward list named neither MODULE SCOPE nor REQUEST, so a
                      coordinator following it literally hands a coder no module and no request.
  3. blind lint     - [brief-fields] treated `orchestration.<skill>.spawns_agents` as a set of
                      DIRECT skill->agent edges. A key that travels odoo-coder -> leaf is an
                      agent->agent edge no tier of the rule walked, while the same flattening
                      charged `odoo-coding` for keys it never emits and never should.

These assert the CONTRACT'S BEHAVIOR, not a wording snapshot: each can fail for a real reason -
make a refusal quiet again, drop a forwarded field, or flatten the edge tiers, and the matching
assertion goes red. The lint half is proved against synthetic fixtures (never the real tree) so its
detector is shown capable of firing, not merely observed printing "clean".

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
DEPS_FILE = PLUGIN / "generator" / "skill_tool_deps.json"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402

LEAF_CODERS = {"odoo-backend-coder": BACKEND, "odoo-frontend-coder": FRONTEND}


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
# 1. The refusal is LOUD - a terminal status, never a near-empty message
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
    # INVERTED. This used to require the literal `produced: []`, which made the empty list the
    # only legal refusal shape and contradicted the field's own definition
    # (`snippets/continuation-contract.md`: "files you actually wrote", no status qualifier) and
    # `skills/run-harness/SKILL.md` § reconcile ("BLOCKED when the effect is PARTIAL - record what
    # exists in `produced`"). A leaf writes into the shared WORKTREE_PATH and appends a worklog
    # entry before it refuses, so its partial work is exactly what a cold replacement inherits.
    # What the refusal owes is a `produced:` line that reports reality; `[]` stays correct when
    # nothing was written, and is guarded as such in `tests/test_blocked_round_trip.py`.
    assert re.search(r"^produced:", block, re.M), (
        f"{name}: a refusal must carry a `produced:` line"
    )
    assert "produced: []" not in block, (
        f"{name}: a refusal must not hardcode `produced: []` - it pre-empts the evidence field on "
        "the very status where partial work is most likely"
    )
    assert "blocked_reason:" in block, f"{name}: a refusal must carry blocked_reason"
    low = " ".join(section.split()).lower()
    assert "near-empty" in low, (
        f"{name}: the section must name the failure mode - a near-empty return reads as silence"
    )


@pytest.mark.parametrize("name", sorted(LEAF_CODERS))
def test_any_gate_not_just_the_test_gate_exits_loudly(name):
    """Defect 1 is not specific to one gate: the brief self-check STOP and every other
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
# 2. The forward list carries what a leaf cannot work without (defect 2)
# ---------------------------------------------------------------------------


def test_leaf_coder_brief_carries_the_module_and_the_request():
    """The latent gap that alone produces 'wrote nothing': a coordinator following the forward
    list literally handed a coder no module path and no request text."""
    fences = _fences(CODER)
    for field in ("MODULE SCOPE", "REQUEST", "ODOO VERSION", "WORKTREE_PATH"):
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
# 3. [brief-fields] walks BOTH edge tiers (defect 3)
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
        "a-leaf": {"role": "leaf", "brief": {"required": ["LEAF_ONLY_KEY"]}},
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
    assert any("a-coord" in f and "a-leaf" in f and "LEAF_ONLY_KEY" in f for f in findings), (
        f"the agent->agent tier did not fire on a coordinator brief missing its leaf's required "
        f"key: {findings}"
    )


def test_agent_to_agent_edge_clears_once_the_key_is_emitted(monkeypatch):
    """GREEN half: the same fixture with the key present in the coordinator's fence is clean, so
    the finding above tracks the key, not the mere existence of an agent edge."""
    orch = {"a-skill": {"spawns_agents": ["a-coord"]}}
    agents = {
        "a-coord": {"role": "coordinator", "spawns_agents": ["a-leaf"], "brief": {"required": []}},
        "a-leaf": {"role": "leaf", "brief": {"required": ["LEAF_ONLY_KEY"]}},
    }
    _fake_tree(
        monkeypatch,
        orch=orch,
        agents=agents,
        skill_bodies={"a-skill": "```\nNOTHING: x\n```"},
        agent_bodies={"a-coord": "```\nLEAF_ONLY_KEY: <value>\n```"},
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
        "a-leaf": {"role": "leaf", "brief": {"required": ["LEAF_ONLY_KEY"]}},
    }
    orch = {"a-skill": {"spawns_agents": ["a-coord", "a-leaf"]}}
    skill_bodies = {"a-skill": "```\nNOTHING: x\n```"}
    agent_bodies = {"a-coord": "```\nLEAF_ONLY_KEY: <value>\n```"}

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
    """On the REAL tree: odoo-coding is charged for no key its coordinator writes, AND the real
    odoo-coder -> leaf edges (both coders and the node's odoo-test-writer) are clean - so the noise
    did not simply move one tier down."""
    findings: list[str] = []
    co.check_brief_fields(findings)
    # Keyed on the DISPATCHER: the coding chain's briefs are written by odoo-coding (skill tier)
    # and odoo-coder (agent tier). Other callers of odoo-test-writer are outside this chain.
    coder_family = [
        f for f in findings
        if f.startswith("[brief-fields] 'odoo-coding'")
        or f.startswith("[brief-fields] agent 'odoo-coder'")
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
