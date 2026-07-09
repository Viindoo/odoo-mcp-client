"""Pinned prose tripwire for the Problem-2 commit-ownership contract (NOT a behavior test).

This file guards the *wording* of Edits A/C/C-land: it snapshots prose tokens, not behavior
(ETHOS #8). It exists as a low-value early-warning that a future edit silently reintroduced a
"no commit" escape hatch into odoo-coding, dropped the always-commit-via-git-ops statement,
removed run-harness's source-write worktree provisioning, or deleted the ``integrate`` land node
from intake's micro-plan schema. It asserts substrings, so it will (correctly) go red if the
final wording is reworded - re-pin the substrings when the SSOT prose changes intentionally.

Plugin-root idiom reused from the sibling ``tests/test_git_delegation_boundary.py`` so this file
stands alone.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"


def test_coding_path_owns_a_commit():
    """Low-value prose tripwire (NOT behavior): odoo-coding must not retain a 'no commit' escape,
    must state it always commits via git-ops, run-harness must document source-write worktree
    provisioning, and the inline micro-plan must carry an 'integrate' land node. Pin substrings to
    the final wording of Edits A/C/C-land; this snapshots prose tokens, not behavior."""
    coding = (AGENTS_PLUGIN / "skills/odoo-coding/SKILL.md").read_text(encoding="utf-8").lower()
    harness = (AGENTS_PLUGIN / "skills/run-harness/SKILL.md").read_text(encoding="utf-8")
    intake = (AGENTS_PLUGIN / "skills/odoo-intake/SKILL.md").read_text(encoding="utf-8")
    for anti in ("make no commit", "no commit is made"):
        assert anti not in coding
    assert "always" in coding and "git-toolkit:git-ops" in coding
    assert "writes the source tree" in harness.lower() and "git-toolkit:git-ops" in harness
    assert "review, integrate]" in intake  # the [code, review, integrate] land node exists in the micro-plan schema


def test_coder_coordinator_commits_module_and_coding_collects_sha():
    """Worktree-graph refactor: the odoo-coder per-module COORDINATOR now COMMITS its module by
    invoking git-toolkit:git-ops (its worktree is dependency-correct - forked from the integrated
    state per Block 2W), then returns the SHA. odoo-coding no longer re-commits: it COLLECTS the
    returned SHA and passes it up. This snapshots prose tokens, not behavior; re-pin if the wording
    changes intentionally."""
    coder = (AGENTS_PLUGIN / "agents/odoo-coder.md").read_text(encoding="utf-8")
    low = coder.lower()
    # The coordinator commits its module via git-ops and returns the SHA.
    assert "git-toolkit:git-ops" in coder and "commit" in low, (
        "odoo-coder coordinator must COMMIT its module via git-toolkit:git-ops"
    )
    assert "odoo-coding" in coder and "sha" in low, (
        "odoo-coder coordinator must return the commit SHA to odoo-coding"
    )
    # odoo-coding collects the SHA and no longer re-commits the coordinator's output.
    coding = (AGENTS_PLUGIN / "skills/odoo-coding/SKILL.md").read_text(encoding="utf-8")
    clow = coding.lower()
    assert "git-toolkit:git-ops" in coding and "coordinator" in clow, (
        "odoo-coding must describe the coordinator's git-ops commit"
    )
    assert "collect" in clow and "sha" in clow, (
        "odoo-coding must COLLECT the coordinator's returned SHA (it no longer re-commits)"
    )
