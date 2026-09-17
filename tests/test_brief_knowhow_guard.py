"""Self-check for the [brief-knowhow] detector (rule 19 in generator/check_orchestration.py).

The boundary it protects, SSOT `snippets/dispatch-brief.md` § "A brief carries WHAT and WHY,
never HOW": a skill that DISPATCHES a named agent owns the outcome, the scope, the resolved
inputs and the boundaries; the agent owns its own method. When the caller re-teaches the method,
the agent holds two copies of one rule - its own, and the caller's already-lossy paraphrase - and
has to decide at runtime which governs. The copies then drift independently.

Rule 19 is the NEGATIVE counterpart of rule 12 [brief-fields], over the SAME two edge tiers rule 12
walks: skill->agent (minus leaves a coordinator re-briefs) and agent->agent. Both read the declared
edges out of `generator/skill_tool_deps.json`.

Two strictness levels, tested separately below because they make different promises:

  STRICT - the DETERMINISTIC shapes, which gate. (a) a dispatch-fence field whose value sends the
  worker to a document instead of handing it a resolved value; (b) a heading family whose whole
  purpose is to pre-digest the agent's domain.

  WARN-ONLY, permanently - cross-edge prose duplication, which catches the DOMINANT form (a rule
  restated as ordinary prose, no fence, no telltale heading) but cannot gate: the same wording
  appears innocently on both sides when a contract requires both to carry a sentence verbatim, and
  when a caller states a routing fact about its callee.

The tests that matter most here are the NEGATIVE ones. A guard tuned only until it fires is a
guard that will be switched off the first time it blocks a correct change - so this file pins the
shapes that must STAY legal: an objective-shaped imperative (`TASK: Resolve the conflict`), and the
correct negative form of the very verb the rule hunts (`substitute it, never re-resolve`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

import generator.check_orchestration as co  # noqa: E402
from generator.check_orchestration import check_brief_knowhow  # noqa: E402


def _run(monkeypatch, orch, bodies, agents=None, edges=None, refs=None):
    """Drive rule 19 over synthetic dispatchers instead of the real tree.

    Returns (strict, warn) so a test can assert WHICH list a shape lands in - the split is the
    contract, not an implementation detail."""
    monkeypatch.setattr(co, "load_orch", lambda: orch)
    monkeypatch.setattr(co, "skill_body", lambda name: bodies.get(name))
    monkeypatch.setattr(co, "agent_body", lambda name: (agents or {}).get(name))
    monkeypatch.setattr(co, "agent_spawn_edges", lambda: edges or {})
    monkeypatch.setattr(co, "_skill_dispatch_surface",
                        lambda name: [(f"skills/{name}/SKILL.md", bodies.get(name) or "")]
                        + list((refs or {}).get(name, [])))
    strict: list[str] = []
    warn: list[str] = []
    check_brief_knowhow(strict, warn)
    return strict, warn


NAMED = {"demo-skill": {"spawn_class": "spawner-agent", "spawns_agents": ["demo-agent"]}}
ANON = {"demo-skill": {"spawn_class": "spawner-agent", "spawns": ["(anonymous workers)"]}}

PROCEDURAL_BRIEF = """## Agent invocation

```
MODULE: sale_order
INSTANCE_RESOLUTION: follow instance-resolution.md
```
"""

RESOLVED_BRIEF = """## Agent invocation

```
MODULE: sale_order
INSTANCE_HANDLE: db=odoo_run_17, http_port=8069
```
"""


# ---------------------------------------------------------------------------
# STRICT (a) - a field value that points at a document instead of carrying one
# ---------------------------------------------------------------------------


def test_flags_a_brief_field_whose_value_sends_the_worker_to_a_document(monkeypatch):
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": PROCEDURAL_BRIEF})
    assert any("INSTANCE_RESOLUTION" in f for f in strict), (
        f"'follow <doc>.md' is a hidden sub-task the worker pays before starting: {strict}"
    )


def test_clears_the_same_field_once_the_caller_passes_a_resolved_value(monkeypatch):
    assert _run(monkeypatch, NAMED, {"demo-skill": RESOLVED_BRIEF}) == ([], [])


@pytest.mark.parametrize(
    "value",
    [
        "follow instance-resolution.md",
        "consult the venv-resolution.md ladder",
        "apply snippets/state-root-resolution.md",
        "per the instance-handle contract",
        "see snippets/worker-brief.md for the shape",
        "resolve it yourself from the catalog",
    ],
)
def test_every_pointer_shaped_value_is_detected(monkeypatch, value):
    body = f"## Agent invocation\n\n```\nSOME_FIELD: {value}\n```\n"
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict, (
        f"'{value}' must be detected - a guard that catches one phrasing goes green on every "
        "other wording of the same defect"
    )


def test_a_key_containing_a_slash_is_still_scanned(monkeypatch):
    body = "## Agent invocation\n\n```\nMODEL/EFFORT: per concurrency-guard.md\n```\n"
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict, "a key like MODEL/EFFORT must not slip past the key pattern"


def test_the_procedure_is_caught_anywhere_in_the_value_not_only_at_its_start(monkeypatch):
    body = "## Agent invocation\n\n```\nMODULES: the node's list, per the module-graph contract\n```\n"
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict, (
        "a procedure buried mid-value is the same defect as one at the start; anchoring the "
        "pattern to the first word is how the shape grows back"
    )


# ---------------------------------------------------------------------------
# STRICT (a) - NEGATIVE cases. These must STAY legal.
# ---------------------------------------------------------------------------


def test_an_objective_shaped_imperative_is_not_a_procedure(monkeypatch):
    """`TASK: Resolve the conflict in place` is the OUTCOME the dispatch asks for. Flagging it
    would make the rule fire on correctly-written briefs, and a guard that blocks correct changes
    gets switched off."""
    body = "## Agent invocation\n\n```\nTASK: Resolve the conflict in place and return the files\n```\n"
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict == [], f"an objective must not read as a procedure: {strict}"


def test_the_correct_negative_form_of_the_hunted_verb_is_not_flagged(monkeypatch):
    """`substitute it, never re-resolve` is the caller doing exactly the right thing. An earlier
    revision of this rule flagged it - the guard fired on the FIX rather than the defect."""
    body = (
        "## Agent invocation\n\n```\n"
        "SHARE_DIR: <absolute path> - substitute this literal, never re-resolve it\n```\n"
    )
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict == [], f"a 'never re-resolve' instruction is correct, not a finding: {strict}"


# ---------------------------------------------------------------------------
# STRICT (b) - the know-how heading family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "## Brief context",
        "## Brief context - Odoo review pitfalls",
        "## Brief Context",           # capital C - the regex must be case-insensitive
        "# Brief context (reference)",  # H1
        "#### Odoo UI review pitfalls",
        "### Key failure modes the design prevents",
        "## Things the agent watches for",
    ],
)
def test_flags_the_knowhow_heading_family(monkeypatch, heading):
    body = f"{heading}\n\nThings to watch: pin the version before navigating.\n"
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": body})
    assert strict, f"'{heading}' must be flagged at any level and any case: {strict}"


def test_a_skill_with_no_knowhow_section_and_resolved_fields_is_clean(monkeypatch):
    body = "## Role\n\nDispatcher.\n\n" + RESOLVED_BRIEF
    assert _run(monkeypatch, NAMED, {"demo-skill": body}) == ([], [])


# ---------------------------------------------------------------------------
# Scan surface: reference files, and the agent->agent tier
# ---------------------------------------------------------------------------


def test_a_reference_file_the_skill_dispatches_from_is_scanned(monkeypatch):
    """A brief template parked in `references/` is still a brief this skill sends. Scoping the
    scan to SKILL.md alone left a live re-teaching in
    `skills/odoo-code-review/references/agent-prompts.md` invisible."""
    refs = {"demo-skill": [("skills/demo-skill/references/agent-prompts.md",
                            PROCEDURAL_BRIEF)]}
    strict, _ = _run(monkeypatch, NAMED, {"demo-skill": "## Role\n\nDispatcher.\n"}, refs=refs)
    assert any("references/agent-prompts.md" in f for f in strict), (
        f"a dispatch template in references/ must be scanned: {strict}"
    )


def test_the_agent_to_agent_tier_is_scanned(monkeypatch):
    """A coordinator writes its leaves' briefs; the skill above it never does. Rule 12 walks that
    tier, so rule 19 must too - otherwise the coordinator that writes three leaf briefs is wholly
    exempt from the boundary being enforced one level up."""
    strict, _ = _run(
        monkeypatch,
        {},
        {},
        agents={"coordinator": PROCEDURAL_BRIEF, "leaf": "leaf body"},
        edges={"coordinator": ["leaf"]},
    )
    assert any("agents/coordinator.md" in f for f in strict), (
        f"an agent that re-briefs named leaves is a dispatcher too: {strict}"
    )


# ---------------------------------------------------------------------------
# WARN-ONLY - cross-edge prose duplication
# ---------------------------------------------------------------------------


def test_prose_restatement_is_reported_but_does_not_gate(monkeypatch):
    """The dominant form: a rule restated as ordinary prose, with no fence and no heading. It must
    be REPORTED (a structural check cannot see it) and must NOT gate (the same wording appears
    innocently when a contract requires both sides to carry it)."""
    rule = (
        "Every finding must cite a screenshot a console message or a computed style readout "
        "rather than an unverified impression of the rendered screen"
    )
    strict, warn = _run(
        monkeypatch,
        NAMED,
        {"demo-skill": f"## Agent invocation\n\n{rule}\n"},
        agents={"demo-agent": f"## Review workflow\n\n{rule}\n"},
    )
    assert strict == [], "prose similarity is too noisy to gate; it must stay warn-only"
    assert any("shares wording with" in w for w in warn), (
        f"a near-verbatim restatement must at least be reported: {warn}"
    )


def test_a_pointer_line_is_not_counted_as_a_restatement(monkeypatch):
    """A caller SHOULD cite the agent's contract, and a citation shares wording with what it
    cites. Counting that as duplication would punish the correct behaviour."""
    line = (
        "Full contract with every rule and its rationale lives in "
        "${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md and is not restated here at all"
    )
    _, warn = _run(
        monkeypatch,
        NAMED,
        {"demo-skill": f"## Agent invocation\n\n{line}\n"},
        agents={"demo-agent": f"## Method\n\n{line}\n"},
    )
    assert warn == [], f"a pointer line must not read as a restatement: {warn}"


# ---------------------------------------------------------------------------
# The anonymous-worker exemption - load-bearing, not a nicety
# ---------------------------------------------------------------------------


def test_anonymous_worker_fanout_is_exempt(monkeypatch):
    """No agents/<name>.md exists to hold the method and the worker cannot resolve
    CLAUDE_PLUGIN_ROOT to read one, so the skill MUST paste the procedure in. Flagging this
    would break odoo-deep-survey and odoo-brl, which are correct as they stand."""
    body = PROCEDURAL_BRIEF + "\n## Brief context\n\nPasted procedure for the worker.\n"
    assert _run(monkeypatch, ANON, {"demo-skill": body}) == ([], [])


# ---------------------------------------------------------------------------
# Wiring + the real tree
# ---------------------------------------------------------------------------


def test_rule_19_strict_half_gates_rather_than_warns():
    source = (PLUGIN / "generator" / "check_orchestration.py").read_text(encoding="utf-8")
    assert "check_brief_knowhow(findings, knowhow_warn_only_findings)" in source, (
        "the deterministic half must be invoked with the gating `findings` list; passing it a "
        "warn-only list would let the boundary rot back in while the build stays green. The "
        "prose half takes its OWN warn list rather than rule 12's, so the printed header cannot "
        "report [brief-knowhow] findings under a [brief-fields] label"
    )


def test_real_tree_has_no_knowhow_in_a_named_agent_dispatch_brief():
    strict: list[str] = []
    warn: list[str] = []
    check_brief_knowhow(strict, warn)
    assert not strict, (
        "a dispatcher is teaching its agent the agent's own trade again:\n  "
        + "\n  ".join(strict)
    )
