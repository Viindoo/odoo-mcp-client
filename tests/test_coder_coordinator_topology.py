"""Topology guard for the module-primary / coder-coordinator model (v4.9.0).

Protects the BEHAVIOR of the reconciled two-tier decomposition (not a wording snapshot):

- The OUTER unit is the MODULE. `odoo-coding` dispatches ONE `odoo-coder` COORDINATOR per module
  (EVERY module - backend-only, frontend-only, or full-stack). There is no single-stack
  direct-to-worker path anymore.
- `odoo-coder` is the per-module COORDINATOR that OWNS the module's INTERNAL work-item (WI) split:
  it divides its ONE module into 1..N disjoint-file-set WIs, schedules INDEPENDENT WIs in PARALLEL
  and DEPENDENT WIs SEQUENTIALLY (backend before a frontend WI that binds it), and per WI launches
  THREE teammates - `odoo-test-writer` FIRST (authors the RED test, test-first), then
  `odoo-backend-coder` / `odoo-frontend-coder` (make it green; the coders no longer author tests) -
  tests the integrated module via `odoo-instance` INLINE, then COMMITS its module by invoking
  `Skill(git-toolkit:git-ops)` (request-only; no raw git, no direct git leaf agent) and returns the
  SHA to `odoo-coding` (which collects it, no longer re-committing).
- `odoo-test-writer`, `odoo-backend-coder`, and `odoo-frontend-coder` are HARD LEAVES - they launch nothing.
- The WI is `odoo-coder`'s PRIVATE unit: it MUST NOT appear as an outer-layer unit in
  odoo-planning / plan-mode-schema / phase-p / run-harness.
- `odoo-module-graph.md` states the two-tier axis (module outer, WI internal to odoo-coder).
- The new agent is registered in plugin.json and reflected in the orchestration SSOT.

Red-before-green: each assertion fails if its wiring is dropped or inverted.
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

# The OUTER-layer sites that must think in MODULES only (never frame the outer unit as a WI).
# (odoo-wave was removed - decision R; run-harness now owns the between-wave integration.)
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


def test_backend_coder_agent_exists_and_is_registered():
    """The backend writer agent exists and is declared in plugin.json.agents."""
    assert BACKEND.is_file(), "agents/odoo-backend-coder.md must exist (the backend hard-leaf writer)"
    declared = {Path(p).name for p in json.loads(_text(CLAUDE_MANIFEST)).get("agents", [])}
    assert "odoo-backend-coder.md" in declared, (
        "odoo-backend-coder.md must be declared in .claude-plugin/plugin.json agents"
    )


def test_coordinator_assigns_wis_to_the_three_teammates_backend_first():
    """The odoo-coder COORDINATOR launches THREE teammates - odoo-test-writer (test-first) +
    odoo-backend-coder + odoo-frontend-coder per WI - and sequences the backend WI before a frontend
    WI that binds it."""
    body = _norm(LEAD)
    assert "odoo-test-writer" in body, (
        "the coordinator must launch odoo-test-writer (the test-first teammate)"
    )
    assert "odoo-backend-coder" in body and "odoo-frontend-coder" in body, (
        "the coordinator must assign WIs to BOTH odoo-backend-coder and odoo-frontend-coder"
    )
    low = body.lower()
    assert "backend" in low and "first" in low or "backend before" in low, (
        "the coordinator must sequence a backend WI before a frontend WI that binds it"
    )


def test_coordinator_launches_test_writer_first_and_coders_do_not_author():
    """Test-first: the coordinator launches odoo-test-writer FIRST (the RED test), then the coder;
    the coders no longer author tests."""
    low = _norm(LEAD).lower()
    assert "odoo-test-writer" in low and "first" in low, (
        "the coordinator must launch odoo-test-writer FIRST per WI (test-first)"
    )
    # The coder agents must explicitly disclaim test authoring (write code only).
    for path in (BACKEND, FRONTEND):
        cbody = _norm(path).lower()
        assert "do not author tests" in cbody or "does not author tests" in cbody or (
            "not author" in cbody and "test" in cbody
        ), f"{path.name} must state it does NOT author tests (the odoo-test-writer teammate does)"


def test_coordinator_owns_the_internal_wi_breakdown():
    """odoo-coder OWNS the internal WI split: 1..N disjoint WIs, parallel-vs-sequential schedule,
    per-WI worker assignment - and states the WI is its PRIVATE intra-module unit."""
    low = _norm(LEAD).lower()
    assert "work-item" in low or "wi" in low, "the coordinator must name the work-item unit"
    assert "disjoint" in low, "the WI split must be by DISJOINT file sets"
    assert "parallel" in low and "sequential" in low, (
        "independent WIs run in PARALLEL, dependent WIs run SEQUENTIALLY"
    )
    assert "1..n" in low or "1..N".lower() in low or "one or more" in low, (
        "one module -> 1..N WIs"
    )
    assert "private" in low or "internal" in low, (
        "the WI must be declared the coordinator's PRIVATE / INTERNAL unit"
    )


def test_coordinator_tests_integrated_module_via_instance_inline():
    """The coordinator owns the integrated module test via Skill(odoo-instance) INLINE (never dispatch)."""
    body = _norm(LEAD)
    assert "Skill(odoo-instance)" in body, "the coordinator must run the integrated test via Skill(odoo-instance)"
    assert "INLINE" in body.upper(), "the integrated test must be INLINE leaf-mode (+0 depth)"
    assert "integrated" in body.lower(), "the coordinator must own the INTEGRATED whole-module test"
    assert "adding no subagent depth" in body, (
        "the coordinator must justify the inline Skill(odoo-instance) call as adding no subagent depth"
    )


def test_coordinator_is_bounded_fix_loop():
    """On failure the coordinator re-launches the relevant worker in a bounded loop (reusing the
    3-iteration bound from test-first-contract.md)."""
    body = _norm(LEAD)
    assert "test-first-contract.md" in body, "the coordinator must cite the test-first-contract bound"
    assert "3 iteration" in body.lower() or "3 iterations" in body.lower(), (
        "the coordinator's fix loop must reuse the 3-iteration bound"
    )


def test_coordinator_commits_module_via_skill_git_ops_and_returns_sha():
    """New contract (worktree-graph refactor): the coordinator COMMITS its module by INVOKING the
    git-toolkit:git-ops skill (request-only), then returns the SHA to odoo-coding. It MUST NOT run
    raw git and MUST NOT dispatch a git leaf agent (git-operator) directly."""
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
    assert "git-operator" not in body or (
        "not dispatch" in low or "must not dispatch" in low or "never dispatch" in low
    ), "the coordinator must NOT dispatch a git leaf agent (git-operator) directly"
    assert "raw git" in low or "never raw git" in low or "not run raw git" in low, (
        "the coordinator must state it never runs raw git (only invokes git-ops)"
    )


def test_workers_are_hard_leaves():
    """All three teammates must declare themselves HARD LEAVES that launch nothing."""
    for path in (TEST_WRITER, BACKEND, FRONTEND):
        body = _norm(path).lower()
        assert "hard leaf" in body or "hard leaves" in body, (
            f"{path.name} must declare it is a HARD LEAF"
        )
        assert "never launch" in body or "launch no sub-agent" in body or "launch nothing" in body, (
            f"{path.name} must state it launches no sub-agent"
        )


def test_coding_dispatches_one_coder_per_module_for_every_module():
    """odoo-coding launches ONE odoo-coder COORDINATOR per module - for EVERY module, with no
    single-stack direct-to-worker bypass."""
    body = _text(CODING)
    low = body.lower()
    assert "odoo-coder" in body, "odoo-coding must launch the odoo-coder coordinator"
    assert "one" in low and "per module" in low, (
        "odoo-coding must dispatch ONE odoo-coder per module"
    )
    assert "every module" in low, (
        "odoo-coding must launch the coordinator for EVERY module (not just full-stack)"
    )
    # The old single-stack direct-dispatch topology must be gone.
    assert not re.search(r"single-stack module\s*->\s*launch", low), (
        "odoo-coding must NOT keep the old single-stack direct-to-worker dispatch - every module "
        "goes through the odoo-coder coordinator now."
    )
    # odoo-coding must NOT own the intra-module WI split (that is the coordinator's).
    assert "does not split" in low or "does NOT split".lower() in low or "not split a module into wis" in low, (
        "odoo-coding must state it does NOT split a module into WIs - the coordinator owns that."
    )


def test_orchestration_ssot_reflects_module_primary_topology():
    """The orchestration SSOT (skill_tool_deps.json) odoo-coding spawns list names the coordinator +
    both workers so the generated ORCHESTRATION-MAP reflects the module-primary topology."""
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
    assert "coordinator" in low, "the spawns entry must mark odoo-coder as the per-module coordinator"
    assert "per module" in low, "the dispatch note must say ONE odoo-coder per module"


def test_module_graph_states_two_tier_axis():
    """odoo-module-graph.md must state the two-tier axis: module is the OUTER unit; the WI is
    odoo-coder's INTERNAL intra-module unit (1 module -> 1..N WIs)."""
    text = _text(MODULE_GRAPH)
    low = text.lower()
    assert "two-tier" in low, "odoo-module-graph.md must carry the two-tier decomposition axis section"
    assert "outer" in low and "module" in low, "the OUTER tier must be the module"
    assert "internal" in low and ("work-item" in low or "wi" in low), (
        "the INNER tier (work-item) must be declared odoo-coder's INTERNAL unit"
    )
    assert "odoo-coder" in text, "the axis must name odoo-coder as the owner of the WI tier"


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
