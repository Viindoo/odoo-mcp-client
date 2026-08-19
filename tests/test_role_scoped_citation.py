"""Guard [role-scope] (rule 11 in generator/check_orchestration.py, M6 in
12-design-final.md).

A `role: leaf` agent launches nothing, so the spawner-tier contracts
(spawner-completion-contract.md, concurrency-guard.md) do not bind it -
the file itself says so (spawner-completion-contract.md's own "vacuously compliant" sentence).
Between them the 25 leaf agents used to cite ~1MB of spawner-tier contract they could never
execute; M6 deletes those citations and replaces them with a one-line pointer to
worker-brief.md/continuation-contract.md/dispatch-brief.md instead.

The rule has three halves:
  (a) a `role: leaf` agent body may not cite any member of the spawner-tier set.
  (b) a `role: spawner|coordinator` agent body MUST cite spawner-completion-contract.md - it
      launches agents, so R3 (completion-report addressing) binds it directly.
  (c) the SAME body must state, in prose the running agent can read, that it does not author the
      source it dispatches. The frontmatter `description` is the launcher's routing listing and is
      never part of the running agent's system prompt, so a prohibition kept only there is one the
      agent was never given.

Half (b)'s subject set (agents with role in {spawner, coordinator}) must never be allowed to pass
vacuously when empty - an empty subject set would otherwise produce zero findings and look
identical to "every spawner complies". This file proves BOTH halves fire for the right reason
(red-before-green, on synthetic fixtures via monkeypatch - never touching the real tree), then
separately verifies the real tree: every leaf/spawner is data-driven from the registry `role`
field (never a hardcoded agent-name list), and exactly `odoo-coder` (the sole coordinator today)
remains as the citer of every spawner-tier file.

Run: python -m pytest tests/test_role_scoped_citation.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
AGENTS_DIR = PLUGIN / "agents"
DEPS_FILE = PLUGIN / "generator" / "skill_tool_deps.json"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402


def _registry() -> dict:
    return json.loads(DEPS_FILE.read_text(encoding="utf-8"))


def _agent_role_map() -> dict[str, str | None]:
    return {name: e.get("role") for name, e in _registry().get("agents", {}).items()}


ROLES = _agent_role_map()
LEAF_AGENTS = sorted(n for n, r in ROLES.items() if r == "leaf")
SPAWNER_AGENTS = sorted(n for n, r in ROLES.items() if r in ("spawner", "coordinator"))


# ---------------------------------------------------------------------------
# Discovery floor - a broken registry read would silently make every
# parametrized test below vacuous (0 params = 0 assertions = green for the
# wrong reason).
# ---------------------------------------------------------------------------


def test_leaf_and_spawner_subject_sets_discovered():
    assert len(LEAF_AGENTS) >= 20, f"expected >=20 role=leaf agents, found {len(LEAF_AGENTS)}: {LEAF_AGENTS}"
    assert len(SPAWNER_AGENTS) >= 1, (
        f"expected >=1 role=spawner|coordinator agent, found {len(SPAWNER_AGENTS)}"
    )


# ---------------------------------------------------------------------------
# Real-tree checks - data-driven from agents.<name>.role (never a hardcoded
# agent-name list), matching [role-scope]'s own data-driven design.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", LEAF_AGENTS)
def test_leaf_agent_body_cites_no_spawner_tier_file(name):
    body = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for banned in co.SPAWNER_TIER_FILES:
        assert banned not in body, (
            f"agents/{name}.md has role=leaf but cites '{banned}' (spawner-tier contract) - a "
            f"leaf launches nothing, so this does not bind it (M6, 12-design-final.md)"
        )


@pytest.mark.parametrize("name", SPAWNER_AGENTS)
def test_spawner_or_coordinator_cites_spawner_completion_contract(name):
    body = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    assert "spawner-completion-contract.md" in body, (
        f"agents/{name}.md has role={ROLES[name]!r} but never cites "
        f"spawner-completion-contract.md - R3's completion-report addressing rule binds it "
        f"directly (it launches agents)"
    )


def test_exactly_odoo_coder_cites_spawner_completion_contract():
    """After M6, spawner-completion-contract.md must be cited by exactly ONE agent body:
    odoo-coder (the sole role=spawner|coordinator agent today, which half (b) REQUIRES to cite
    it). Verified by grep, not assumed - the task's own verification command
    (`grep -rln spawner-completion-contract.md agents/`) made durable as a test."""
    citers = sorted(
        p.stem for p in AGENTS_DIR.glob("*.md")
        if "spawner-completion-contract.md" in p.read_text(encoding="utf-8")
    )
    assert citers == ["odoo-coder"], f"expected exactly ['odoo-coder'], found {citers}"


def test_retired_transport_snippet_is_cited_by_no_agent_body():
    """The retired upward-transport snippet is gone: the return path is the launch call's own
    return value, so there is no transport left to describe. A surviving citation points at a
    file that no longer exists."""
    citers = sorted(
        p.stem for p in AGENTS_DIR.glob("*.md")
        if "agent-team-protocol.md" in p.read_text(encoding="utf-8")
    )
    assert citers == [], f"expected no agent body to cite the retired snippet, found {citers}"


def test_concurrency_guard_is_cited_only_by_a_spawner_tier_body():
    """concurrency-guard.md is a SPAWNER-TIER file (co.SPAWNER_TIER_FILES): it binds a body that
    FANS OUT and does not bind one that launches nothing. The rule this protects is therefore
    half (a) - no `role: leaf` body may cite it - NOT "no body may cite it".

    A blanket zero-citer assertion is what left `odoo-coder`'s intra-node WI fan-out uncapped: it
    launches N same-worktree-writing workers, which is precisely the Mode B trigger the guard
    defines, yet no agent body was permitted to carry the cap. Assert the role boundary instead."""
    offenders = sorted(
        p.stem for p in AGENTS_DIR.glob("*.md")
        if "concurrency-guard.md" in p.read_text(encoding="utf-8")
        and ROLES.get(p.stem) not in ("spawner", "coordinator")
    )
    assert offenders == [], (
        f"only a role=spawner|coordinator body may cite concurrency-guard.md; these do not "
        f"launch anything yet cite it: {offenders}"
    )


def test_the_fanning_out_coordinator_actually_carries_the_concurrency_cap():
    """The positive half: a body that fans out MUST cite the cap, or its fan-out is unbounded.
    Without this, the boundary test above passes vacuously the moment the citation is deleted."""
    fanning_out = sorted(n for n, r in ROLES.items() if r in ("spawner", "coordinator"))
    assert fanning_out, "subject set is empty - the assertion below would pass vacuously"
    missing = [
        n for n in fanning_out
        if (AGENTS_DIR / f"{n}.md").exists()
        and "concurrency-guard.md" not in (AGENTS_DIR / f"{n}.md").read_text(encoding="utf-8")
    ]
    assert missing == [], (
        f"these bodies fan out but state no concurrency cap: {missing} - cite "
        "skills/_shared/concurrency-guard.md rather than launching an unbounded batch"
    )


def test_role_scope_is_strict_gating_and_clean_on_real_tree():
    """[role-scope] is folded into `findings` (gates --strict), unlike [brief-fields] (rule 12,
    permanently warn-only) and [wait-scope]/[wait-mechanism] (rules 9-10, warn-only for one
    release). On the real tree it must report ZERO findings and the process must still exit 0
    under --strict (other warn-only rules may still print)."""
    env = {**os.environ, "ORCH_STRICT": "1"}
    result = subprocess.run(
        [sys.executable, str(PLUGIN / "generator" / "check_orchestration.py"), "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "[role-scope]" not in result.stdout, (
        f"real tree must produce zero [role-scope] findings:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Detector-logic proof (red-before-green) - synthetic fixtures via
# monkeypatch, never touching the real tree. Mirrors the pattern in
# tests/test_wait_contract_scope.py for the sibling warn-only rules.
# ---------------------------------------------------------------------------


# What a compliant role=spawner|coordinator BODY must carry, both halves at once: the spawner-tier
# citation (b) and a prohibition on authoring what it dispatches (c).
_COMPLIANT_SPAWNER_BODY = (
    "I launch agents. See spawner-completion-contract.md R3. "
    "I never write the production source I dispatch."
)


def _write_registry(path: Path, agents: dict, extra: dict | None = None) -> None:
    data = {"agents": agents}
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_role_scope_flags_leaf_citing_spawner_tier_file(tmp_path, monkeypatch):
    """RED->GREEN for half (a): a synthetic role=leaf agent whose body cites a banned spawner-tier
    file is flagged; removing the citation clears the finding."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "fake-leaf.md").write_text(
        "You are a leaf. Full rule: spawner-completion-contract.md R3.", encoding="utf-8"
    )
    (agents_dir / "odoo-coder.md").write_text(_COMPLIANT_SPAWNER_BODY, encoding="utf-8")
    deps_file = tmp_path / "deps.json"
    _write_registry(deps_file, {
        "fake-leaf": {"role": "leaf"},
        "odoo-coder": {"role": "coordinator"},
    })
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "DEPS_FILE", deps_file)

    findings = []
    co.check_role_scope(findings)
    assert any("fake-leaf" in f and "spawner-completion-contract.md" in f for f in findings), (
        f"RED case did not fire: {findings}"
    )

    (agents_dir / "fake-leaf.md").write_text("You are a leaf. No spawner contract cited.", encoding="utf-8")
    findings2 = []
    co.check_role_scope(findings2)
    assert not any("fake-leaf" in f for f in findings2), f"GREEN case still fired: {findings2}"


def test_role_scope_flags_spawner_missing_the_citation(tmp_path, monkeypatch):
    """RED->GREEN for half (b): a role=spawner agent whose body never cites
    spawner-completion-contract.md is flagged; adding the citation clears it."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "fake-spawner.md").write_text(
        "I launch agents but cite nothing. I never write the production source I dispatch.",
        encoding="utf-8",
    )
    deps_file = tmp_path / "deps.json"
    _write_registry(deps_file, {"fake-spawner": {"role": "spawner"}})
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "DEPS_FILE", deps_file)

    findings = []
    co.check_role_scope(findings)
    assert any("fake-spawner" in f and "spawner-completion-contract.md" in f for f in findings), (
        f"RED case did not fire: {findings}"
    )

    (agents_dir / "fake-spawner.md").write_text(_COMPLIANT_SPAWNER_BODY, encoding="utf-8")
    findings2 = []
    co.check_role_scope(findings2)
    assert not any("fake-spawner" in f for f in findings2), f"GREEN case still fired: {findings2}"


def test_role_scope_flags_a_spawner_whose_body_never_forbids_authoring(tmp_path, monkeypatch):
    """RED->GREEN for half (c)(i) - THE guard that would have caught the observed breach.

    `odoo-coder` carried "NOT a code writer and NOT a leaf" in its frontmatter `description`
    ONLY. That string is the launcher's routing listing; it is never part of the running agent's
    system prompt, so the agent had no prohibition to disobey. When its teammate dispatch was
    refused, it edited a module's `__manifest__.py` itself.

    Remaining false negative, stated: this is a LEXICAL claim check over the whitespace-normalized
    body. A body that states the prohibition in a phrasing the regex cannot see fails here even
    though it is correct prose; a body that states it and then contradicts it elsewhere passes.
    It proves the claim is PRESENT for the agent to read, never that the agent obeys it -
    `hooks/block-coordinator-code-write.sh` is the enforcing half."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    deps_file = tmp_path / "deps.json"
    _write_registry(deps_file, {"fake-spawner": {"role": "coordinator"}})
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "DEPS_FILE", deps_file)

    # RED: cites the contract, but never forbids authoring.
    (agents_dir / "fake-spawner.md").write_text(
        "I launch agents. See spawner-completion-contract.md R3. "
        "I dispatch my teammates and end my turn.",
        encoding="utf-8",
    )
    findings = []
    co.check_role_scope(findings)
    assert any("does not author the source it dispatches" in f for f in findings), (
        f"RED case did not fire - a spawner with no authoring prohibition must be flagged: {findings}"
    )

    # GREEN: the same body, plus the prohibition, in a DIFFERENT phrasing from the fixture above -
    # the rule protects the claim, not one sentence.
    (agents_dir / "fake-spawner.md").write_text(
        "I launch agents. See spawner-completion-contract.md R3. "
        "I do not author production code myself.",
        encoding="utf-8",
    )
    findings2 = []
    co.check_role_scope(findings2)
    assert not any("fake-spawner" in f for f in findings2), f"GREEN case still fired: {findings2}"


def test_role_scope_second_half_does_not_pass_vacuously_when_subject_set_empty(tmp_path, monkeypatch):
    """RED->GREEN proof that an EMPTY spawner/coordinator subject set is ITSELF a finding, never a
    silent pass - the exact vacuous-pass failure mode half (b) exists to prevent. GREEN is reached
    only via the explicit opt-out flag, never by the empty set alone."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "only-leaf.md").write_text("no spawner-tier citation here.", encoding="utf-8")
    deps_file = tmp_path / "deps.json"

    # RED: no role=spawner|coordinator agent anywhere, and no opt-out flag.
    _write_registry(deps_file, {"only-leaf": {"role": "leaf"}})
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "DEPS_FILE", deps_file)

    findings = []
    co.check_role_scope(findings)
    assert any("EMPTY" in f for f in findings), (
        f"RED case did not fire - an empty spawner/coordinator subject set must be flagged, "
        f"never silently pass: {findings}"
    )

    # GREEN: the explicit opt-out flag makes the empty set a deliberate, reviewed choice.
    _write_registry(
        deps_file, {"only-leaf": {"role": "leaf"}},
        extra={"_role_scope_no_spawners_expected": True},
    )
    findings2 = []
    co.check_role_scope(findings2)
    assert not findings2, f"GREEN case (opt-out flag set) still produced findings: {findings2}"


def test_role_scope_real_registry_does_not_need_the_opt_out_flag():
    """Sanity: the real registry has a genuine spawner/coordinator (odoo-coder) and must NOT be
    carrying the opt-out flag - if it ever needed to, that would itself be a signal worth a human
    seeing, not something to silently set."""
    data = _registry()
    assert not data.get("_role_scope_no_spawners_expected"), (
        "the real registry has role=spawner|coordinator agents and must not carry "
        "_role_scope_no_spawners_expected"
    )
    assert SPAWNER_AGENTS, "the real registry lost its only spawner/coordinator agent"
