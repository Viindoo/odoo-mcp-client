"""Tests for `scripts/audit-run.py` - the run-topology auditor.

Business contract being protected (the four properties users complained were violated in real
run-harness runs; schema SSOT: `plugins/odoo-ai-agents/docs/reference/workflow-harness.md` 8.3):

  1. ONE PR per REPOSITORY. Each entry in the run file's `repos[]` gets exactly one DONE
     `approach_kind: integrate` node - never one per wave, and never one for a two-repo run. A run
     file that predates `repos[]` is audited in the legacy single-repo form, reported as such.
  2. Nothing substantive after the PR opens, SCOPED PER REPO. A PR-opening node that reached DONE
     while a node OF ITS OWN REPO outside the land tail {integrate, monitor, merge} is still
     unfinished must FAIL, naming that node - and must NOT name another repo's unfinished nodes or
     a `repo: null` node, which belong to no repository's readiness scope.
  3. No tier jargon emitted. An `L0`/`L1`/`L2` token recorded in any Continuation Contract must
     FAIL, naming the node - while the node's OWN `gate_tier` and the `gate_log[].tier` entries,
     which are the driver's internal control values, must NOT be flagged (every fixture here
     carries them, so a rule that over-reaches turns the clean fixture red).
  4. Gate count is REPORTED, never asserted - the right count depends on the run, so a run with
     zero human gates and a run with three are both legal.

Tests are behavior-first (ETHOS #8): each asserts on the script's observable contract - its exit
code and the node it names - not on its internals.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "audit-run.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2


def _run(fixture_name: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES / fixture_name), *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _audit_json(fixture_name: str) -> dict:
    result = _run(fixture_name, "--json")
    return json.loads(result.stdout)


def _check(audit: dict, check_id: str) -> dict:
    matches = [c for c in audit["checks"] if c["id"] == check_id]
    assert matches, f"audit emitted no check with id {check_id!r}: {audit['checks']}"
    return matches[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _nodes(raw: dict) -> list[dict]:
    return list(raw.get("nodes") or []) + list(raw.get("dynamic_nodes") or [])


# ---------------------------------------------------------------------------
# The passing fixture - a well-formed run must be clean on all three assertions
# ---------------------------------------------------------------------------


def test_well_formed_run_passes_every_assertion():
    """A run that opens exactly one PR after all substantive work settled must exit 0.

    The fixture deliberately carries `gate_tier` on every node and `tier` on every `gate_log`
    entry: those are the driver's internal control values and must never be mistaken for emitted
    tier jargon, so this test also proves check 3 does not over-reach.
    """
    result = _run("audit_run_clean.json")
    assert result.returncode == EXIT_OK, (
        f"a well-formed run must audit clean:\n{result.stdout}\n{result.stderr}"
    )
    audit = _audit_json("audit_run_clean.json")
    assert audit["ok"] is True
    assert all(c["ok"] for c in audit["checks"]), audit["checks"]


def test_read_only_run_with_no_pr_node_is_not_a_violation():
    """A chat-only run lands nothing, so declaring no PR-opening node is legal, not a violation."""
    result = _run("audit_run_chat_only.json")
    assert result.returncode == EXIT_OK, (
        f"a read-only run that declares no land-tail must audit clean:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Violation class 1 - more than one PR per run
# ---------------------------------------------------------------------------


def test_two_pr_opening_nodes_fail_and_both_are_named():
    """Two DONE `integrate` nodes = two PRs for one run - the per-wave-PR defect."""
    result = _run("audit_run_two_prs.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a run with two PR-opening nodes must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    audit = _audit_json("audit_run_two_prs.json")
    check = _check(audit, "one-pr")
    assert check["ok"] is False
    named = {v["node"] for v in check["violations"]}
    assert named == {"land-wave-1", "land-wave-2"}, (
        f"both offending PR-opening nodes must be named, got {named}"
    )


def test_declared_pr_node_that_never_reached_done_fails():
    """A run whose declared land tail never opened the PR is not 'exactly one PR' either."""
    result = _run("audit_run_pr_never_landed.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a declared-but-unlanded PR node must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    check = _check(_audit_json("audit_run_pr_never_landed.json"), "one-pr")
    assert [v["node"] for v in check["violations"]] == ["land"]


# ---------------------------------------------------------------------------
# Violation class 2 - substantive work still open behind an opened PR
# ---------------------------------------------------------------------------


def test_unfinished_substantive_node_behind_an_open_pr_fails_and_is_named():
    """The PR opened while the pre-PR tail's i18n reconcile was still READY."""
    result = _run("audit_run_work_after_pr.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"substantive work behind an opened PR must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    check = _check(_audit_json("audit_run_work_after_pr.json"), "pr-last")
    assert check["ok"] is False
    assert [v["node"] for v in check["violations"]] == ["i18n-reconcile"], check["violations"]


def test_land_tail_nodes_still_pending_are_not_a_violation():
    """A PENDING `odoo-pr-monitoring` node is the land tail doing its job, never a violation.

    The same fixture that fails on `i18n-reconcile` also carries a PENDING monitoring node; if the
    land-tail exemption ever broke, that node would show up here too.
    """
    check = _check(_audit_json("audit_run_work_after_pr.json"), "pr-last")
    named = {v["node"] for v in check["violations"]}
    assert "monitor-1" not in named, (
        f"a land-tail monitoring node must be exempt from the after-PR rule, got {named}"
    )


# ---------------------------------------------------------------------------
# The per-repo contract - `repos[]` + the per-node `repo` field
# ---------------------------------------------------------------------------


def _run_file(path: pathlib.Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *extra],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )


def test_two_repos_with_one_pr_each_pass_and_are_audited_in_the_per_repo_form():
    """Two repos, two PRs is CORRECT - the rule is one PR per REPO, not one per run.

    Premise first (so this cannot pass vacuously): the fixture must really declare two repos, land
    two `integrate` nodes, and carry a `repo: null` node. Under a whole-run rule those two landed
    nodes are exactly the `one-pr` violation the two-PR fixture triggers, so a green verdict here
    is only reachable if the check buckets by repo.
    """
    raw = _fixture("audit_run_multi_repo_clean.json")
    assert [r["id"] for r in raw["repos"]] == ["fleet-addons", "core-addons"], (
        "fixture premise: two declared repos"
    )
    landed = [n for n in _nodes(raw)
              if n.get("approach_kind") == "integrate" and n.get("status") == "DONE"]
    assert {n["repo"] for n in landed} == {"fleet-addons", "core-addons"}, (
        f"fixture premise: one landed integrate per repo, got {landed}"
    )
    assert any(n.get("repo") is None for n in _nodes(raw)), (
        "fixture premise: a `repo: null` node must be present, or the null case is untested"
    )

    result = _run("audit_run_multi_repo_clean.json")
    assert result.returncode == EXIT_OK, (
        f"two repos with one PR each must audit clean:\n{result.stdout}\n{result.stderr}"
    )
    audit = _audit_json("audit_run_multi_repo_clean.json")
    assert audit["form"] == "per-repo"
    assert audit["repos"] == ["fleet-addons", "core-addons"]
    assert all(c["ok"] for c in audit["checks"]), audit["checks"]


def test_a_declared_repo_with_no_integrate_node_fails_and_is_named():
    """A repo the run coded in but never landed has no PR of its own - one PR per repo is broken."""
    raw = _fixture("audit_run_multi_repo_missing_integrate.json")
    assert [r["id"] for r in raw["repos"]] == ["fleet-addons", "core-addons"]
    integrates = [n for n in _nodes(raw) if n.get("approach_kind") == "integrate"]
    assert [n["repo"] for n in integrates] == ["fleet-addons"], (
        "fixture premise: exactly one integrate node, and it belongs to fleet-addons"
    )
    assert any(n.get("repo") == "core-addons" and n.get("status") == "DONE"
               for n in _nodes(raw)), (
        "fixture premise: core-addons must carry real, finished work - otherwise 'it never landed' "
        "would be vacuous"
    )

    result = _run("audit_run_multi_repo_missing_integrate.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a declared repo with no PR must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    check = _check(_audit_json("audit_run_multi_repo_missing_integrate.json"), "one-pr")
    assert check["ok"] is False
    assert any("core-addons" in v["node"] or "core-addons" in v["detail"]
               for v in check["violations"]), (
        f"the unlanded repo must be named in the finding, got {check['violations']}"
    )


def test_after_pr_check_names_only_the_landing_repos_own_unfinished_work():
    """The discriminator: per-repo scoping, not a whole-run check wearing a repo label.

    fleet-addons opened its PR while its own i18n node was still READY (a real violation), while
    core-addons is legitimately mid-flight (its PR is not open yet) and a `repo: null` synthesis
    node is still PENDING. Only fleet-addons' own node may be named; a global check would name
    core-addons' nodes and the repo-less node too.
    """
    raw = _fixture("audit_run_multi_repo_scoped.json")
    by_id = {n["id"]: n for n in _nodes(raw)}
    assert by_id["fleet-land"]["status"] == "DONE" and by_id["fleet-land"]["repo"] == "fleet-addons"
    assert by_id["fleet-i18n"]["status"] not in ("DONE", "SKIPPED")
    assert by_id["core-land"]["status"] != "DONE", (
        "fixture premise: core-addons must NOT have landed, else its nodes would be in scope"
    )
    for unfinished in ("core-wave-1", "core-review"):
        assert by_id[unfinished]["status"] not in ("DONE", "SKIPPED"), (
            f"fixture premise: {unfinished} must be unfinished, or the scoping proof is vacuous"
        )
        assert by_id[unfinished]["approach_kind"] not in ("integrate",), (
            f"fixture premise: {unfinished} must not be a land-tail node - otherwise it would be "
            "exempt for the WRONG reason and this test would prove nothing about repo scoping"
        )
    assert by_id["run-summary"]["repo"] is None
    assert by_id["run-summary"]["status"] not in ("DONE", "SKIPPED")

    result = _run("audit_run_multi_repo_scoped.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a PR opened over its own repo's unfinished work must exit {EXIT_VIOLATION}:\n"
        f"{result.stdout}"
    )
    check = _check(_audit_json("audit_run_multi_repo_scoped.json"), "pr-last")
    assert check["ok"] is False
    named = {v["node"] for v in check["violations"]}
    assert named == {"fleet-i18n"}, (
        "only the landing repo's own unfinished node may be named - another repo's unfinished "
        f"nodes and the repo-less node are out of scope, got {named}"
    )


def test_a_wave_node_with_no_repo_cannot_be_attributed_and_fails(tmp_path):
    """Mutation proof: strip the `repo` off a coding wave and the audit must refuse to pass it.

    A `wave`/`integrate` node with `repo: null` would silently escape every repo's readiness scope,
    so per-repo PR topology becomes unprovable. The unmutated fixture is green (asserted above), so
    this failure is caused by the mutation and nothing else.
    """
    raw = _fixture("audit_run_multi_repo_clean.json")
    target = next(n for n in raw["nodes"] if n["approach_kind"] == "wave")
    target["repo"] = None
    mutated = tmp_path / "run-mutated.json"
    mutated.write_text(json.dumps(raw), encoding="utf-8")

    result = _run_file(mutated)
    assert result.returncode == EXIT_VIOLATION, (
        f"an unattributable wave node must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    audit = json.loads(_run_file(mutated, "--json").stdout)
    violations = _check(audit, "one-pr")["violations"]
    assert any(v["node"] == target["id"] for v in violations), (
        f"the unattributed wave node must be named, got {violations}"
    )


def test_a_run_file_without_repos_is_reported_as_the_legacy_single_repo_form():
    """A run serialized before `repos[]` existed still audits - and says which form it ran in."""
    raw = _fixture("audit_run_clean.json")
    assert "repos" not in raw, "fixture premise: the legacy fixture declares no repos[]"

    audit = _audit_json("audit_run_clean.json")
    assert audit["form"] == "legacy-single-repo"
    assert audit["repos"] == []
    assert audit["ok"] is True
    text = _run("audit_run_clean.json").stdout
    assert "legacy-single-repo" in text, (
        f"the text report must name the form it ran in:\n{text}"
    )


# ---------------------------------------------------------------------------
# Violation class 3 - tier jargon in an emitted Continuation Contract
# ---------------------------------------------------------------------------


def test_tier_token_in_a_recorded_contract_fails_and_names_the_node():
    """`risk_level: L2` recorded in a step's Continuation Contract is emitted tier jargon."""
    result = _run("audit_run_tier_jargon.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a tier token in a recorded contract must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    check = _check(_audit_json("audit_run_tier_jargon.json"), "no-tier")
    assert check["ok"] is False
    assert [v["node"] for v in check["violations"]] == ["review-1"], check["violations"]
    assert "risk_level" in check["violations"][0]["detail"], (
        "the finding must point at the offending contract field, "
        f"got {check['violations'][0]['detail']!r}"
    )


def test_node_gate_tier_and_gate_log_tier_are_never_flagged():
    """The driver's internal tier control values are legitimate and must stay unflagged.

    Red-before-green proof that check 3 is scoped: the clean fixture's nodes all carry
    `gate_tier: L0/L1/L2` and its gate_log entries all carry `tier`, yet it audits clean. Widen the
    scan to the whole node and this test goes red for the right reason.
    """
    raw = json.loads((FIXTURES / "audit_run_clean.json").read_text(encoding="utf-8"))
    tiers = {n.get("gate_tier") for n in raw["nodes"]} | {e.get("tier") for e in raw["gate_log"]}
    assert {"L0", "L1", "L2"} <= tiers, (
        "fixture premise: the clean run must carry internal tier control values, otherwise this "
        f"test proves nothing - got {tiers}"
    )
    assert _check(_audit_json("audit_run_clean.json"), "no-tier")["ok"] is True


# ---------------------------------------------------------------------------
# Check 4 - the gate count is reported, never asserted
# ---------------------------------------------------------------------------


def test_human_gates_are_counted_per_node_and_auto_passes_excluded():
    """The clean run auto-passed two nodes and hit exactly one human gate, on `monitor-1`."""
    gates = _audit_json("audit_run_clean.json")["gates"]
    assert gates["total_gate_log_entries"] == 3
    assert gates["human_gate_count"] == 1
    assert gates["by_node"] == {"monitor-1": 1}


def test_zero_human_gates_is_reported_not_asserted():
    """A run with only auto-passes reports 0 human gates and must not fail on that account."""
    audit = _audit_json("audit_run_chat_only.json")
    assert audit["gates"]["human_gate_count"] == 0
    assert audit["ok"] is True, "the gate count must never flip the audit result"


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["a.json", "b.json"]])
def test_wrong_argument_count_is_a_usage_error(argv):
    """The script takes exactly one run-file path."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != EXIT_OK


def test_missing_or_unparseable_run_file_exits_two_not_one(tmp_path):
    """An unreadable run file is an operator error, distinct from a topology violation."""
    missing = _run("does-not-exist.json")
    assert missing.returncode == EXIT_USAGE, missing.stderr

    broken = tmp_path / "run-broken.json"
    broken.write_text("{not json", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(broken)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == EXIT_USAGE, result.stderr


def test_json_mode_emits_a_parseable_report_with_every_check():
    """`--json` must emit the same verdict as the text report, machine-readably."""
    audit = _audit_json("audit_run_two_prs.json")
    assert audit["ok"] is False
    assert {c["id"] for c in audit["checks"]} == {"one-pr", "pr-last", "no-tier"}
    assert audit["run_id"] == "two-prs-20260806-c3d4"
    assert set(audit["gates"]) == {"human_gate_count", "by_node", "total_gate_log_entries"}
