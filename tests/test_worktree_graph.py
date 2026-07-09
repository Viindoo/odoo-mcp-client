"""Behavior guards for the planned-worktree-graph refactor (decision R, CORE step).

Protects the CONTRACT (not a wording snapshot) of the worktree dependency graph:

(a) Block 2W - the symbolic worktree dependency graph - lives in plan-mode-schema.md as a SECOND
    projection alongside the Block-2 module-DAG, carries SYMBOLIC topology/lifecycle only (never ref
    STATE: SHAs/tips/paths/leases), and encodes the fork-from-integrated-parent loop edge
    `integration@wave-(N+1) ==> integration@wave-N`. odoo-planner authors it and its plan-ref line is
    relaxed to allow symbolic topology while still forbidding concrete ref state.
(b) The odoo-coder coordinator COMMITS its module via Skill(git-toolkit:git-ops) - request-only, no
    direct git leaf agent, no raw git (see also test_coder_coordinator_topology.py).
(c) run-harness carries the between-wave integration (fork-from-prior-integration + cherry-pick in
    module-DAG order + saga + integrated review + cumulative close-gate + one squashed PR at the
    L2-squash-gate), consuming Block 2W.

Red-before-green: each assertion fails if its clause is dropped or inverted.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"
PLANNER = PLUGIN / "agents" / "odoo-planner.md"
CODER = PLUGIN / "agents" / "odoo-coder.md"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"
LEDGER = PLUGIN / "snippets" / "module-coordination-ledger.md"
INTEGRATION_LOOP = PLUGIN / "skills" / "_shared" / "integration-loop.md"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _block_2w_section() -> str:
    """The '**Block 2W ...**' spec, up to the next '**Block 3'."""
    text = _text(SCHEMA)
    start = text.find("**Block 2W")
    assert start != -1, (
        "plan-mode-schema.md must carry a '**Block 2W - Worktree dependency graph ...**' section "
        "(the second projection alongside the Block-2 module-DAG)."
    )
    end = text.find("**Block 3", start)
    return text[start: end if end != -1 else len(text)]


# ---------------------------------------------------------------------------
# (a) Block 2W in the plan schema
# ---------------------------------------------------------------------------

def test_schema_has_block_2w_with_symbolic_nodes():
    sec = _block_2w_section()
    for node in ("base", "integration@wave-N", "worktree(m)@wave-N"):
        assert node in sec, f"Block 2W must declare the symbolic node `{node}`"
    low = sec.lower()
    assert "parallel" in low, (
        "Block 2W must state it is authored IN PARALLEL with the Block-2 module-DAG"
    )
    assert "second projection" in low or "re-projected" in low or "projection" in low, (
        "Block 2W must be a SECOND projection of the wave grouping (not a second DAG source)"
    )


def test_block_2w_is_symbolic_topology_never_ref_state():
    """Block 2W carries topology/lifecycle but NEVER concrete ref state (SHAs/tips/paths/leases)."""
    sec = _block_2w_section()
    low = sec.lower()
    assert "symbolic" in low, "Block 2W must declare it is SYMBOLIC"
    assert "topology" in low and "lifecycle" in low, (
        "Block 2W must carry worktree TOPOLOGY + LIFECYCLE"
    )
    # The ref-state exclusions must be spelled out (never SHAs/tips/paths/leases).
    assert "sha" in low, "Block 2W must forbid concrete SHAs (ref state stays runtime)"
    assert "lease" in low, "Block 2W must forbid lease tokens (ref state stays runtime)"
    assert "path" in low, "Block 2W must forbid resolved worktree filesystem paths (ref state)"


def test_block_2w_fork_from_integrated_parent_loop_edge():
    """The wave-threading fix: integration@wave-(N+1) forks from integration@wave-N (NOT principal)."""
    sec = _block_2w_section()
    assert "integration@wave-(N+1) ==> integration@wave-N" in sec, (
        "Block 2W must carry the fork-from-integrated-parent edge "
        "`integration@wave-(N+1) ==> integration@wave-N` (the loop fix)."
    )
    low = sec.lower()
    assert "not `base`/principal" in low or "not base/principal" in low or (
        "not" in low and "principal" in low
    ), "Block 2W must state wave N+1 integration forks the PRIOR integration, NOT base/principal"
    assert "cherry-pick" in low and "-->" in sec, (
        "Block 2W must carry the cherry-pick-into edge (worktree -> integration, `-->`)"
    )
    assert "loop" in low, "Block 2W must describe the per-wave loop"


def test_block_2w_fenced_text_is_ascii_only():
    """The Block 2W ```text``` render must be ASCII-only (ETHOS rule 0)."""
    sec = _block_2w_section()
    m = re.search(r"```text\n(.*?)\n```", sec, re.DOTALL)
    assert m, "Block 2W must render the worktree graph as a fenced ```text``` block"
    for ch in m.group(1):
        assert ord(ch) < 128, f"Block 2W ASCII render found non-ASCII U+{ord(ch):04X} ({ch!r})"


def test_planner_authors_block_2w_and_ref_relaxation():
    """odoo-planner authors Block 2W AND its integration-loop bullet is relaxed: it carries the
    symbolic worktree topology/lifecycle but still NO concrete ref state."""
    text = _text(PLANNER)
    low = text.lower()
    assert "block 2w" in low, "odoo-planner must author Block 2W"
    # Relaxation: topology/lifecycle now allowed ...
    assert "topology/lifecycle" in low or ("topology" in low and "lifecycle" in low), (
        "odoo-planner's plan-ref line must now allow the symbolic worktree TOPOLOGY/LIFECYCLE"
    )
    # ... but concrete ref STATE still forbidden.
    assert "no concrete ref state" in low or "no concrete ref" in low, (
        "odoo-planner must still forbid concrete ref STATE (SHAs/tips/paths/leases stay runtime)"
    )
    assert "integration@wave-(n+1)" in low, (
        "odoo-planner must name the fork-from-integrated-parent loop edge it authors"
    )
    # The old absolute forbid ('never worktree/ref state') must be gone.
    assert "never worktree/ref state" not in low, (
        "odoo-planner must no longer say the plan carries 'never worktree/ref state' - the "
        "symbolic topology is now carried; only concrete ref STATE is forbidden."
    )


# ---------------------------------------------------------------------------
# (b) coder commits via Skill(git-toolkit:git-ops) - request-only
# ---------------------------------------------------------------------------

def test_coder_commits_via_skill_git_ops_request_only():
    text = _text(CODER)
    low = text.lower()
    assert "git-toolkit:git-ops" in text and "commit" in low, (
        "odoo-coder must COMMIT its module by invoking git-toolkit:git-ops"
    )
    # Request-only: no raw git, no direct git leaf-agent dispatch.
    assert "raw git" in low, "odoo-coder must state it never runs raw git (invokes git-ops instead)"
    assert ("not dispatch" in low or "must not dispatch" in low) and "git-operator" in low, (
        "odoo-coder must state it does NOT dispatch a git leaf agent (git-operator) directly"
    )
    # It returns the SHA up to odoo-coding.
    assert "sha" in low and "odoo-coding" in text, (
        "odoo-coder must return the commit SHA to odoo-coding"
    )


# ---------------------------------------------------------------------------
# (c) run-harness owns the between-wave integration (consumes Block 2W)
# ---------------------------------------------------------------------------

def test_run_harness_owns_between_wave_integration():
    text = _text(RUN_HARNESS)
    low = text.lower()
    assert "between-wave integration" in low, (
        "run-harness must carry a between-wave integration responsibility (consumes Block 2W)"
    )
    assert "block 2w" in low, "run-harness between-wave integration must CONSUME Block 2W"
    assert "fork-from-prior-integration" in low or (
        "forks `integration@wave-(n+1)` from `integration@wave-n`" in low
    ), "run-harness must fork wave N+1 integration from wave N integration (fork-from-prior-integration)"


def test_run_harness_cumulative_close_gate_and_squashed_pr():
    text = _text(RUN_HARNESS)
    low = text.lower()
    assert "cumulative regression close-gate" in low or "cumulative" in low and "close-gate" in low, (
        "run-harness between-wave integration must run the cumulative regression close-gate"
    )
    assert "module-dag" in low and ("topo order" in low or "topo-order" in low or "order" in low), (
        "run-harness must cherry-pick each module commit in module-DAG order"
    )
    assert "saga" in low, "run-harness cherry-pick must use saga rollback (integration-loop.md)"
    assert "squashed pr" in low, "run-harness must open ONE squashed PR per wave"
    assert "l2-squash-gate" in low, "run-harness must STOP at the L2-squash-gate (merge stays odoo-pr-monitoring)"


def test_integration_loop_names_run_harness_as_canonical_consumer():
    text = _text(INTEGRATION_LOOP)
    low = text.lower()
    assert "run-harness" in low and "canonical per-wave integration consumer" in low, (
        "integration-loop.md must name run-harness as the canonical per-wave integration consumer"
    )
    # After decision R, run-harness is the SOLE owner - there is no separate git-executor skill and
    # odoo-wave must NOT be listed as an owner anymore.
    assert "sole owner" in low, (
        "integration-loop.md must state run-harness is the SOLE owner of the per-wave integration "
        "(the separate git-executor skill was removed)."
    )
    assert re.search(r"^-\s*`?odoo-wave`?\b", text, re.MULTILINE) is None, (
        "integration-loop.md must no longer list `odoo-wave` as an owner bullet (it was removed)."
    )


# ---------------------------------------------------------------------------
# Ledger scope note: intra-run structurally solved; ledger backstops cross-run only
# ---------------------------------------------------------------------------

def test_ledger_notes_intra_run_structurally_solved():
    text = _text(LEDGER)
    low = text.lower()
    assert "block 2w" in low, "the ledger must reference Block 2W's fork-from-integrated-parent lineage"
    assert "structurally solved" in low, (
        "the ledger must state intra-run dependency-blindness is STRUCTURALLY SOLVED under Block 2W"
    )
    assert "cross-run" in low, (
        "the ledger must state it now backstops ONLY concurrent independent (cross-run) coordination"
    )
