"""Boundary eval for the FRONT-DOOR DISPATCH CONTRACT: a front door must dispatch specialist work,
not perform it in its own context.

WHY these tests exist. Eight front doors were corrected in one pass for telling the orchestrator to
do a specialist's job inline - `odoo-forward-port` P6/P7 ran a conflict scan, raw OSM
`model_inspect`/`entity_lookup` grounding and a `python -m pytest --collect-only` collection gate in
the main context; `odoo-solution-design` decided contested symbols itself instead of dispatching the
reconcile pass. Nothing prevented those from coming back. A static wording-freeze guard can prove
the corrected sentences are present; it cannot prove an orchestrator READING them actually
dispatches. That needs the TRANSCRIPT graded, which is what
`evals/frontdoor-boundary/lib/grading.py` does and what this file proves the grading logic of.

WHICH HALF COVERS WHICH GAP (both are needed; neither subsumes the other):
  - `plugins/odoo-ai-agents/hooks/block-coordinator-code-write.sh` is the PREVENTIVE half. It hard-
    denies a production-source write by a DISPATCHED AGENT whose declared role forbids authoring -
    and it can only ever act there, because it resolves the role from a populated `agent_type`.
  - This grader is the DETECTIVE half covering the gap that hook cannot reach: a FRONT-DOOR SKILL
    running in the MAIN context, where no `agent_type` exists to key on at all, plus a dispatched
    COORDINATOR's own inline breach (a sidechain turn, so a sidechain filter would miss it).

WHAT IS ASSERTED HERE, per this repo's transcript-fixture convention
(tests/test_resource_teardown_evals.py, tests/test_enforce_teardown.py): the graders themselves are
deterministic and run in CI with no live model, against HAND-AUTHORED transcripts - `execution.
max_turns` defaults to 10 and `timeout_seconds` to 300, so a real front-door dispatch does not fit a
default live case. Every RED/GREEN pair below is red-before-green by construction: the
PRE-CORRECTION transcript shape must be FLAGGED and the corrected shape must PASS, with the same
forbidden classes loaded from the eval definition's own `forbidden_tool_classes` SSOT rather than
restated here (so the definition and this test cannot drift).

RESIDUAL FALSE NEGATIVES of the guard these tests protect - the full list is R1-R6 in
`evals/frontdoor-boundary/lib/grading.py`'s module docstring. The one that bounds this guard most:
an orchestrator that REASONS FROM MEMORY and calls no tool leaves no transcript evidence at all, so
a decision it never writes down is invisible here. Next: an actor with no `agents.<name>.role` entry
(`general-purpose`, `Explore`) is never accused, matching from tool SHAPE cannot see a step spelled
through a wrapper it does not name, and a `satisfied_by_prior_dispatch` exoneration proves only that
the dispatch happened - not that what was written is what came back.

Run with: python3 -m pytest tests/test_frontdoor_boundary_evals.py -v
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GRADING_PY = ROOT / "evals" / "frontdoor-boundary" / "lib" / "grading.py"
EVAL_DIR = ROOT / "evals" / "frontdoor-boundary"
FP_EVAL = EVAL_DIR / "odoo-forward-port.evals.json"
SD_EVAL = EVAL_DIR / "odoo-solution-design.evals.json"


def _load_grading_module():
    spec = importlib.util.spec_from_file_location("frontdoor_grading", GRADING_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


grading = _load_grading_module()


def _classes(eval_path) -> list:
    return json.loads(Path(eval_path).read_text(encoding="utf-8"))["forbidden_tool_classes"]


FP_CLASSES = _classes(FP_EVAL)
SD_CLASSES = _classes(SD_EVAL)


# --------------------------------------------------------------------------------------------- #
# Transcript builders - the _line/_tu/_text convention of tests/test_resource_teardown_evals.py,
# extended with the ENVELOPE keys real Claude Code transcripts carry (OBSERVED: a main-context line
# carries `attributionSkill` and never `attributionAgent`; a subagent line carries
# `attributionAgent` + `agentId` + `isSidechain: true`).
# --------------------------------------------------------------------------------------------- #
def _line(role="assistant", content=None, **envelope):
    return json.dumps({"role": role, "content": content or [], **envelope})


def _tu(name, id_=None, **input_kwargs):
    block = {"type": "tool_use", "name": name, "input": input_kwargs}
    if id_:
        block["id"] = id_
    return block


def _text(s):
    return {"type": "text", "text": s}


def _orchestrator(content, skill="odoo-forward-port"):
    """A MAIN-context turn: the front-door skill acting as the orchestrator. No agent identity."""
    return _line(content=content, attributionSkill=f"odoo-ai-agents:{skill}", isSidechain=False)


def _subagent(content, agent):
    """A DISPATCHED subagent turn - always a sidechain, identity carried by attributionAgent."""
    return _line(content=content, attributionAgent=agent, agentId="fixtureagent01", isSidechain=True)


def _write_transcript(tmp_path, lines) -> Path:
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tpath


def _violated_classes(out) -> set:
    return {v["class_id"] for v in out["violations"]}


# --------------------------------------------------------------------------------------------- #
# The eval definitions must exist, parse, and declare usable classes
# --------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", [FP_EVAL, SD_EVAL])
def test_eval_definition_exists_and_has_required_fields(path):
    assert path.is_file(), f"eval definition missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("skill_name") or data.get("agent_name"), "must name its target"
    assert data["evals"], "evals[] must not be empty"
    for item in data["evals"]:
        assert item["prompt"], "each eval needs a self-contained prompt/brief"
        assert item["expectations"], "each eval needs at least one verifiable expectation"
    assert data["forbidden_tool_classes"], "the boundary eval's whole subject is its forbidden classes"
    for cls in data["forbidden_tool_classes"]:
        assert cls.get("id"), "every class needs an id the verdict can name"
        assert cls.get("rule"), "every class must state the dispatch rule it protects, for the reader"
        assert (
            cls.get("tool_name_suffixes") or cls.get("tool_name_pattern") or cls.get("input_pattern")
        ), f"class {cls.get('id')!r} declares no selector - it would match every tool call"


def test_the_front_doors_under_test_actually_exist():
    """A guard aimed at a skill that is not there would pass forever."""
    for path in (FP_EVAL, SD_EVAL):
        skill = json.loads(path.read_text(encoding="utf-8"))["skill_name"]
        assert (
            ROOT / "plugins" / "odoo-ai-agents" / "skills" / skill / "SKILL.md"
        ).is_file(), f"eval targets a skill that does not exist: {skill}"


def test_a_class_with_no_selector_is_refused_rather_than_matching_everything():
    with pytest.raises(ValueError, match="no selector"):
        grading.grade_frontdoor_boundary(__file__, [{"id": "catch-all"}])


def test_grading_with_no_classes_at_all_is_refused():
    with pytest.raises(ValueError, match="at least one forbidden class"):
        grading.grade_frontdoor_boundary(__file__, [])


# --------------------------------------------------------------------------------------------- #
# Actor resolution - the whole design rests on this, so it is asserted directly against the
# LIVE agent-role SSOT (generator/skill_tool_deps.json), never a stub.
# --------------------------------------------------------------------------------------------- #
def test_the_agent_role_ssot_still_declares_both_role_kinds():
    """If the SSOT stopped declaring a coordinator, the coordinator test below would go vacuous."""
    roles = grading.load_agent_roles()
    assert roles, "the agent-role SSOT must be readable - the grader's identity lookup depends on it"
    assert any(r in grading.ORCHESTRATING_ROLES for r in roles.values()), "no coordinator/spawner declared"
    assert any(r == "leaf" for r in roles.values()), "no leaf declared"


def test_main_context_turn_with_no_agent_identity_is_the_orchestrator():
    roles = grading.load_agent_roles()
    actor = grading.resolve_turn_actor(
        {"attributionSkill": "odoo-ai-agents:odoo-forward-port", "isSidechain": False}, roles
    )
    assert actor["kind"] == "main-context"
    assert actor["orchestrating"] is True
    assert actor["skill"] == "odoo-forward-port"


def test_declared_coordinator_is_orchestrating_even_on_a_sidechain_turn():
    roles = grading.load_agent_roles()
    coordinator = next(n for n, r in roles.items() if r in grading.ORCHESTRATING_ROLES)
    actor = grading.resolve_turn_actor(
        {"attributionAgent": f"odoo-ai-agents:{coordinator}", "isSidechain": True}, roles
    )
    assert actor["kind"] == "coordinator"
    assert actor["orchestrating"] is True


def test_declared_leaf_is_never_treated_as_the_orchestrator():
    roles = grading.load_agent_roles()
    leaf = next(n for n, r in roles.items() if r == "leaf")
    actor = grading.resolve_turn_actor({"attributionAgent": f"odoo-ai-agents:{leaf}"}, roles)
    assert actor["kind"] == "leaf"
    assert actor["orchestrating"] is False


def test_an_actor_with_no_declared_role_is_not_accused():
    """Positive-role-claim only - the same posture block-coordinator-code-write.sh takes."""
    roles = grading.load_agent_roles()
    actor = grading.resolve_turn_actor({"attributionAgent": "Explore", "agentId": "x1"}, roles)
    assert actor["kind"] == "unknown-actor"
    assert actor["orchestrating"] is False


def test_hook_shaped_identity_spellings_resolve_identically():
    """A transcript captured from a hook payload carries agent_type, not attributionAgent."""
    roles = grading.load_agent_roles()
    coordinator = next(n for n, r in roles.items() if r in grading.ORCHESTRATING_ROLES)
    for key in ("agent_type", "agentType", "subagent_type"):
        actor = grading.resolve_turn_actor({key: f"odoo-ai-agents:{coordinator}"}, roles)
        assert actor["kind"] == "coordinator", key


# --------------------------------------------------------------------------------------------- #
# odoo-forward-port P6/P7 - RED: the PRE-CORRECTION shape must be flagged
# --------------------------------------------------------------------------------------------- #
def _pre_correction_p6_p7_lines() -> list[str]:
    """The literal shape the phase text carried BEFORE the correction: the orchestrator runs the
    conflict scan, the OSM grounding and the collection gate itself."""
    return [
        _orchestrator([_text("P6 - symbol-survival check. Scanning for conflict markers.")]),
        _orchestrator([_tu("Bash", command="git diff --check ; grep -rn '^<<<<<<<' .")]),
        _orchestrator([_tu(
            "mcp__odoo-semantic__model_inspect",
            model="account.account", method="fields", odoo_version="18.0",
        )]),
        _orchestrator([_tu(
            "mcp__odoo-semantic__entity_lookup",
            kind="field", model="account.account", field="company_ids", odoo_version="18.0",
        )]),
        _orchestrator([_tu(
            "mcp__odoo-semantic__api_version_diff",
            symbol="account.account.company_id", from_version="17.0", to_version="18.0",
        )]),
        _orchestrator([_tu(
            "Bash",
            command="python -m pytest addons/mod/tests/test_x.py --collect-only -q 2>&1 | tail -20",
        )]),
        _orchestrator([_tu("Bash", command="pyflakes addons/mod/models/account_move.py")]),
        _orchestrator([_text("SYMBOL-SURVIVAL: clean. Proceeding to P8.")]),
    ]


def test_pre_correction_forward_port_orchestrator_running_p6_p7_inline_is_flagged(tmp_path):
    """RED PROOF. Every inline recipe the correction removed is caught, by its own class."""
    out = grading.grade_frontdoor_boundary(
        _write_transcript(tmp_path, _pre_correction_p6_p7_lines()), FP_CLASSES,
        skill_name="odoo-forward-port",
    )
    assert out["pass"] is False, out
    assert _violated_classes(out) == {
        "fp-p6-inline-conflict-scan",
        "fp-p6-inline-osm-grounding",
        "fp-p7-inline-collection-gate",
    }, out["violations"]
    # 1 conflict scan + 3 OSM calls + 2 static-gate commands.
    assert len(out["violations"]) == 6, out["violations"]
    assert out["exonerated"] == []
    failed = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("fp-p6-inline-conflict-scan" in t for t in failed)
    assert any("fp-p6-inline-osm-grounding" in t for t in failed)
    assert any("fp-p7-inline-collection-gate" in t for t in failed)


@pytest.mark.parametrize(
    "command,expected_class",
    [
        # Alternate SHAPES of the same defect - a guard that recognises exactly one phrasing goes
        # green while every other phrasing walks past it.
        ("git diff --check", "fp-p6-inline-conflict-scan"),
        ("git   diff  --stat --check", "fp-p6-inline-conflict-scan"),
        ("grep -rln '<<<<<<<' addons/", "fp-p6-inline-conflict-scan"),
        ("rg --no-heading '^<<<<<<< HEAD' .", "fp-p6-inline-conflict-scan"),
        ("python -m pytest --collect-only -q addons/mod/tests", "fp-p7-inline-collection-gate"),
        ("pytest -q --collect-only", "fp-p7-inline-collection-gate"),
        (".venv/bin/pyflakes addons/mod/models/x.py", "fp-p7-inline-collection-gate"),
        ("python -m py_compile addons/mod/models/x.py", "fp-p7-inline-collection-gate"),
    ],
)
def test_each_inline_gate_phrasing_is_caught_not_just_the_one_the_old_text_used(
    tmp_path, command, expected_class
):
    lines = [_orchestrator([_tu("Bash", command=command)])]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is False, command
    assert expected_class in _violated_classes(out), (command, out["violations"])


def test_a_command_split_across_lines_is_still_caught(tmp_path):
    """Whitespace is normalized before matching - never line adjacency."""
    lines = [_orchestrator([_tu("Bash", command="python -m pytest \\\n    addons/mod/tests \\\n    --collect-only")])]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert "fp-p7-inline-collection-gate" in _violated_classes(out), out


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__odoo-semantic__entity_lookup",
        "mcp__plugin_odoo-ai-agents_odoo-semantic__entity_lookup",
        "mcp__odoo-semantic-headed__tests_covering",
        "mcp__odoo-semantic__test_coverage_audit",
    ],
)
def test_the_osm_class_is_mcp_prefix_agnostic(tmp_path, tool_name):
    """Suffix-keyed, so a new MCP namespace (headed, plugin_*) is covered without an edit here."""
    lines = [_orchestrator([_tu(tool_name, model="account.move", odoo_version="18.0")])]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is False, tool_name
    assert _violated_classes(out) == {"fp-p6-inline-osm-grounding"}, out


# --------------------------------------------------------------------------------------------- #
# odoo-forward-port P6/P7 - GREEN: the corrected shape passes
# --------------------------------------------------------------------------------------------- #
def _corrected_p6_p7_lines(delegate_turns_as_orchestrator: bool = False) -> list[str]:
    """The corrected shape: the orchestrator dispatches both phases and records only the verdict.
    The delegate then issues exactly the calls that would be violations from the orchestrator.

    `delegate_turns_as_orchestrator` reattributes ONLY the delegate's turns to the main context,
    leaving every tool call byte-identical - the control that proves the green verdict is produced
    by the identity resolution and not by a grader that never matches anything.
    """
    def _delegate(content, agent):
        return _orchestrator(content) if delegate_turns_as_orchestrator else _subagent(content, agent)

    return [
        _orchestrator([_text("P6 - dispatching the conflict scan and the merge-base file list.")]),
        _orchestrator([_tu(
            "Skill",
            skill="git-toolkit:git-ops",
            args="conflict-marker scan + git diff --name-only <merge-base>..<src-SHA>, "
                 "write both to a findings file and return the path",
        )]),
        _orchestrator([_tu(
            "Agent",
            subagent_type="Explore",
            description="P6 symbol grounding",
            prompt="Ground every Odoo symbol in the returned file list against the TARGET version "
                   "per fp-symbol-survival-check sections 1-2.5. Return SYMBOL-BROKEN lines only.",
        )]),
        # The dispatched delegate does the work - these calls are its job, not a breach.
        _delegate([_tu(
            "mcp__odoo-semantic__model_inspect",
            model="account.account", method="fields", odoo_version="18.0",
        )], agent="Explore"),
        _delegate([_tu(
            "mcp__odoo-semantic__entity_lookup",
            kind="field", model="account.account", field="company_ids", odoo_version="18.0",
        )], agent="Explore"),
        _delegate([_tu(
            "Bash", command="python -m pytest addons/mod/tests --collect-only -q",
        )], agent="Explore"),
        _delegate([_text("SYMBOL-SURVIVAL: clean")], agent="Explore"),
        _orchestrator([_tu(
            "Write",
            file_path="<SHARE_DIR>/forward-port/<slug>/merge-log.md",
            content="SYMBOL-SURVIVAL: clean | collection gate: PASS | bucket: (a) no adapt needed",
        )]),
        _orchestrator([_text("P6/P7 verdict recorded. Proceeding to P8.")]),
    ]


def test_corrected_forward_port_dispatches_both_phases_and_passes(tmp_path):
    """GREEN PROOF on the current tree's shape - and the delegate's identical calls stay clean."""
    out = grading.grade_frontdoor_boundary(
        _write_transcript(tmp_path, _corrected_p6_p7_lines()), FP_CLASSES,
        skill_name="odoo-forward-port",
    )
    assert out["pass"] is True, out
    assert out["violations"] == []
    assert out["orchestrating_turns"] > 0, "the verdict must not be vacuously PASS"
    assert out["delegated_turns"] > 0, "the fixture must contain the delegate's own calls to be a real test"


def test_the_delegate_calls_in_the_corrected_fixture_would_be_violations_from_the_orchestrator(tmp_path):
    """Discriminating control: the SAME calls, reattributed to the orchestrator, DO fail. Without
    this, the green result above could be explained by a grader that never matches anything."""
    lines = _corrected_p6_p7_lines(delegate_turns_as_orchestrator=True)
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is False, out
    assert _violated_classes(out) == {"fp-p6-inline-osm-grounding", "fp-p7-inline-collection-gate"}, out


def test_recording_the_verdict_is_not_a_violation(tmp_path):
    """The orchestrator's OWN job - writing merge-log.md - must never trip a class."""
    lines = [_orchestrator([_tu(
        "Write",
        file_path="<SHARE_DIR>/forward-port/<slug>/merge-log.md",
        content="SYMBOL-BROKEN | account.account.company_id | models/x.py:42 | bucket: b | "
                "evidence: entity_lookup NOT FOUND at 18.0",
    )])]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is True, out


# --------------------------------------------------------------------------------------------- #
# Identity, not isSidechain - the measured reason the discriminator had to change
# --------------------------------------------------------------------------------------------- #
def test_a_declared_leaf_running_the_gate_itself_is_never_flagged(tmp_path):
    roles = grading.load_agent_roles()
    leaf = next(n for n, r in roles.items() if r == "leaf")
    lines = [
        _subagent([_tu("Bash", command="python -m pytest addons/mod/tests --collect-only")],
                  agent=f"odoo-ai-agents:{leaf}"),
        _orchestrator([_text("delegate returned")]),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is True, out
    assert any(k.startswith("leaf:") for k in out["actors"]), out["actors"]


def test_a_dispatched_coordinator_breaching_inline_is_flagged_although_its_turn_is_a_sidechain(tmp_path):
    """THE case an `isSidechain` filter structurally misses. Measured: main-context turns are all
    `isSidechain:false` and a dispatched subagent's are all `true`, so filtering on
    `isSidechain == false` would silently exonerate a COORDINATOR - which is why this grader keys on
    the role the agent-role SSOT declares for the turn's agent identity instead."""
    roles = grading.load_agent_roles()
    coordinator = next(n for n, r in roles.items() if r in grading.ORCHESTRATING_ROLES)
    lines = [
        _subagent([_tu("Bash", command="python -m pytest addons/mod/tests --collect-only")],
                  agent=f"odoo-ai-agents:{coordinator}"),
    ]
    transcript = _write_transcript(tmp_path, lines)
    # The turn really is a sidechain - so a sidechain filter would have dropped it.
    assert json.loads(transcript.read_text(encoding="utf-8").splitlines()[0])["isSidechain"] is True
    out = grading.grade_frontdoor_boundary(transcript, FP_CLASSES)
    assert out["pass"] is False, out
    assert _violated_classes(out) == {"fp-p7-inline-collection-gate"}
    assert out["violations"][0]["actor"] == f"coordinator:{coordinator}"


def test_an_unknown_actor_is_not_accused(tmp_path):
    """`Explore` / `general-purpose` resolve to no role - and the corrected P6 dispatches Explore to
    do exactly these calls, so accusing an unknown actor would break the fix it is guarding."""
    lines = [
        _subagent([_tu("mcp__odoo-semantic__model_inspect", model="account.move", odoo_version="18.0")],
                  agent="general-purpose"),
        _orchestrator([_text("delegate returned")]),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is True, out


# --------------------------------------------------------------------------------------------- #
# Vacuity and scoping
# --------------------------------------------------------------------------------------------- #
def test_a_transcript_with_no_orchestrating_turn_cannot_be_graded_pass(tmp_path):
    """A guard that returns PASS on a transcript it could never fail is not a guard."""
    roles = grading.load_agent_roles()
    leaf = next(n for n, r in roles.items() if r == "leaf")
    lines = [_subagent([_text("done")], agent=f"odoo-ai-agents:{leaf}")]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is False, out
    assert out["orchestrating_turns"] == 0
    failed = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("at least one turn issued by the orchestrator" in t for t in failed)


def test_skill_scoping_drops_a_turn_positively_attributed_to_another_front_door(tmp_path):
    lines = [
        _orchestrator([_tu("Bash", command="python -m pytest tests --collect-only")],
                      skill="odoo-code-review"),
        _orchestrator([_text("P6 verdict recorded")]),
    ]
    transcript = _write_transcript(tmp_path, lines)
    scoped = grading.grade_frontdoor_boundary(transcript, FP_CLASSES, skill_name="odoo-forward-port")
    assert scoped["pass"] is True, scoped
    unscoped = grading.grade_frontdoor_boundary(transcript, FP_CLASSES)
    assert unscoped["pass"] is False, "without scoping the same call IS graded - proving the filter acted"


def test_a_tool_result_echoing_a_forbidden_command_is_not_the_orchestrators_action(tmp_path):
    """Only the orchestrator's OWN tool_use counts - the same assistant-only posture
    hooks/enforce-teardown.sh and grade_eval_a take."""
    lines = [
        _line(role="user", content=[{
            "type": "tool_result", "tool_use_id": "t1",
            "content": [{"type": "text", "text": "the delegate ran: python -m pytest --collect-only"}],
        }], attributionSkill="odoo-ai-agents:odoo-forward-port"),
        _orchestrator([_text("recorded")]),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), FP_CLASSES)
    assert out["pass"] is True, out


# --------------------------------------------------------------------------------------------- #
# odoo-solution-design - contested-symbol reconciliation (the missing-dispatch shape)
# --------------------------------------------------------------------------------------------- #
_CONTESTED = "<SHARE_DIR>/designs/<master-slug>/contested-symbols.md"
_MASTER = "<SHARE_DIR>/designs/<master-slug>/master.md"
_VERDICT = (
    "### 10.4 Contested symbol: sale.order.x_window_id\n"
    "winner: module_a (owns the field definition)\n"
    "loser: module_b (consumes it via related)\n"
)
_RECONCILE_PROMPT = (
    "MODE: reconcile\n"
    "CONTESTED: <SHARE_DIR>/designs/<master-slug>/contested-symbols.md\n"
    "MASTER_DESIGN_DOC: <SHARE_DIR>/designs/<master-slug>/master.md\n"
    "Return one verdict row per contested symbol (winner, loser, evidence, or UNRESOLVED)."
)


def test_pre_correction_solution_design_orchestrator_deciding_the_symbol_itself_is_flagged(tmp_path):
    """RED PROOF: read the contested file, then rule on it - no reconcile dispatch anywhere."""
    lines = [
        _orchestrator([_tu("Read", file_path=_CONTESTED)], skill="odoo-solution-design"),
        _orchestrator([_text("module_a's proposal is the stronger one against master section 10.")],
                      skill="odoo-solution-design"),
        _orchestrator([_tu("Edit", file_path=_MASTER, old_string="### 10.4", new_string=_VERDICT)],
                      skill="odoo-solution-design"),
    ]
    out = grading.grade_frontdoor_boundary(
        _write_transcript(tmp_path, lines), SD_CLASSES, skill_name="odoo-solution-design",
    )
    assert out["pass"] is False, out
    assert _violated_classes(out) == {"sd-contested-symbol-self-decision"}
    assert out["exonerated"] == []


def test_corrected_solution_design_dispatches_reconcile_then_records_the_verdict(tmp_path):
    """GREEN PROOF: the identical verdict write is exonerated by the preceding reconcile dispatch -
    and the exoneration is REPORTED, so a reviewer can see which dispatch cleared it."""
    lines = [
        _orchestrator([_tu("Read", file_path=_CONTESTED)], skill="odoo-solution-design"),
        _orchestrator([_tu(
            "Agent",
            subagent_type="odoo-ai-agents:odoo-solution-architect",
            description="reconcile layer 1",
            prompt=_RECONCILE_PROMPT,
        )], skill="odoo-solution-design"),
        _subagent([_text("verdict: winner module_a; loser module_b; evidence master section 10.2")],
                  agent="odoo-ai-agents:odoo-solution-architect"),
        _orchestrator([_tu("Edit", file_path=_MASTER, old_string="### 10.4", new_string=_VERDICT)],
                      skill="odoo-solution-design"),
    ]
    out = grading.grade_frontdoor_boundary(
        _write_transcript(tmp_path, lines), SD_CLASSES, skill_name="odoo-solution-design",
    )
    assert out["pass"] is True, out
    assert len(out["exonerated"]) == 1, out
    assert out["exonerated"][0]["exonerated_by"] == "odoo-solution-architect MODE: reconcile dispatch"


def test_the_reconcile_dispatch_is_recognised_across_line_breaks(tmp_path):
    """The exoneration pattern requires BOTH the agent name and `MODE: reconcile`, which land on
    different lines of a real brief - so it only works because the haystack is whitespace-normalized
    before matching. Line adjacency must never be what decides a verdict."""
    assert "\n" in _RECONCILE_PROMPT and "odoo-solution-architect" not in _RECONCILE_PROMPT
    lines = [
        _orchestrator([_tu("Agent", subagent_type="odoo-ai-agents:odoo-solution-architect",
                           prompt=_RECONCILE_PROMPT)], skill="odoo-solution-design"),
        _orchestrator([_tu("Write", file_path=_MASTER, content=_VERDICT)], skill="odoo-solution-design"),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), SD_CLASSES)
    assert out["pass"] is True, out


def test_a_dispatch_to_the_architect_in_another_mode_does_not_exonerate(tmp_path):
    """`MODE: review` is a different pass - only the reconcile dispatch clears a verdict write."""
    lines = [
        _orchestrator([_tu("Agent", subagent_type="odoo-ai-agents:odoo-solution-architect",
                           prompt="MODE: review\nReview the child designs on this dependency chain.")],
                      skill="odoo-solution-design"),
        _orchestrator([_tu("Write", file_path=_MASTER, content=_VERDICT)], skill="odoo-solution-design"),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), SD_CLASSES)
    assert out["pass"] is False, out
    assert _violated_classes(out) == {"sd-contested-symbol-self-decision"}


def test_a_verdict_write_before_the_dispatch_is_still_a_violation(tmp_path):
    """Order matters: a dispatch issued AFTER the ruling did not inform it."""
    lines = [
        _orchestrator([_tu("Write", file_path=_MASTER, content=_VERDICT)], skill="odoo-solution-design"),
        _orchestrator([_tu("Agent", subagent_type="odoo-ai-agents:odoo-solution-architect",
                           prompt=_RECONCILE_PROMPT)], skill="odoo-solution-design"),
    ]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), SD_CLASSES)
    assert out["pass"] is False, out


@pytest.mark.parametrize(
    "content",
    [
        "contested symbol sale.order.x_window_id resolved in favour of module_a",
        "Contested-Symbol table updated: module_b's proposal lost",
        "winner: module_a\nloser: module_b",
        "module_b's proposal loses; module_a owns the field",
    ],
)
def test_each_verdict_phrasing_is_caught_not_just_the_one_the_old_text_used(tmp_path, content):
    lines = [_orchestrator([_tu("Write", file_path=_MASTER, content=content)],
                           skill="odoo-solution-design")]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), SD_CLASSES)
    assert out["pass"] is False, content


def test_an_ordinary_design_write_is_not_a_contested_symbol_verdict(tmp_path):
    """The orchestrator writes `status: designed` per module on every layer - never a violation."""
    lines = [_orchestrator([_tu("Write", file_path="<SHARE_DIR>/designs/<master-slug>/index.yaml",
                                content="module_a:\n  status: designed\n")],
                           skill="odoo-solution-design")]
    out = grading.grade_frontdoor_boundary(_write_transcript(tmp_path, lines), SD_CLASSES)
    assert out["pass"] is True, out


# --------------------------------------------------------------------------------------------- #
# CLI smoke: the live-run entry point each evals.json documents in how_to_run_live
# --------------------------------------------------------------------------------------------- #
def test_cli_exits_nonzero_on_a_flagged_transcript_and_zero_on_a_clean_one(tmp_path):
    import subprocess
    import sys

    fail_dir = tmp_path / "fail"
    fail_dir.mkdir()
    fail_path = _write_transcript(fail_dir, _pre_correction_p6_p7_lines())
    proc = subprocess.run(
        [sys.executable, str(GRADING_PY), str(FP_EVAL), str(fail_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 1, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["pass"] is False
    assert payload["violations"], "the CLI must print the offending calls, not just a verdict"

    pass_dir = tmp_path / "pass"
    pass_dir.mkdir()
    pass_path = _write_transcript(pass_dir, _corrected_p6_p7_lines())
    proc = subprocess.run(
        [sys.executable, str(GRADING_PY), str(FP_EVAL), str(pass_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["pass"] is True
