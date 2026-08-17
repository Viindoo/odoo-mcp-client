"""Tests for `scripts/audit-run.py` - the run-topology auditor.

Business contract being protected (the four properties users complained were violated in real
run-harness runs; schema SSOT: `plugins/odoo-ai-agents/docs/reference/workflow-harness.md` 8.3):

  1. ONE PR per REPOSITORY, detected by the ACT and cross-checked against the DECLARATION. A node
     that recorded a pull-request URL in `produced` OPENED a PR whatever `approach_kind` it
     declares; a DONE `approach_kind: integrate` node that recorded no PR URL never proved it
     opened one. Each entry in `repos[]` gets exactly one landed PR-opening node, and never one for
     a two-repo run. A run file that predates `repos[]` is audited in the legacy single-repo form,
     reported as such.
  2. Nothing substantive after the PR opens, SCOPED PER REPO. A landed PR-opening node while a node
     OF ITS OWN REPO outside the land tail is still unfinished must FAIL, naming that node - and
     must NOT name another repo's unfinished nodes. Land-tail membership is EXACT (the node's
     `approach_kind`, or its `approach` resolving to `odoo-pr-monitoring`); a free-text id that
     merely CONTAINS `merge`/`integrate` buys no exemption. A `repo: null` node is out of scope
     only when it is genuinely repo-less work - a repo-less node running a delivery-gating stage is
     IN scope and is a finding.
  3. No tier jargon emitted. An `L0`/`L1`/`L2` token recorded in any Continuation Contract must
     FAIL, naming the node - while the node's OWN `gate_tier` and the `gate_log[].tier` entries,
     which are the driver's internal control values, must NOT be flagged (every fixture here
     carries them, so a rule that over-reaches turns the clean fixture red).
  4. Gate count is REPORTED, never asserted - the right count depends on the run, so a run with
     zero human gates and a run with three are both legal.

  5. THREE verdicts, never two. A run file the auditor cannot fully read - missing, unparseable, or
     shaped outside the documented schema - is `could-not-check` (exit 2), never `clean`. A shape
     that hides nodes from the audit (a `nodes` mapping, an `approach_kind` outside the enum) is
     the classic silent pass this state exists to stop.

Tests are behavior-first (ETHOS #8): each asserts on the script's observable contract - its exit
code and the node it names - not on its internals. Every test states its fixture's premise before
asserting the verdict, so none of them can pass vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "audit-run.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2


def _load_audit_module():
    """Load `scripts/audit-run.py` as a module - the only way to reach its vocabulary constants.

    Used exclusively to check SSOT membership (e.g. `REPO_BOUND_APPROACHES`), never to call the
    script's internals in place of running it: every behavioral assertion in this file still goes
    through the CLI via `_run`/`_run_file`.
    """
    spec = importlib.util.spec_from_file_location("audit_run_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


PR_URL_RE = re.compile(r"https?://\S+/(?:pull|pulls|pull-requests|merge_requests)/\d+", re.I)


def _pr_urls(value) -> set[str]:
    """Every pull-request URL reachable in a nested JSON value - used to state fixture premises."""
    if isinstance(value, str):
        return set(PR_URL_RE.findall(value))
    if isinstance(value, dict):
        return set().union(*(_pr_urls(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_pr_urls(v) for v in value)) if value else set()
    return set()


def _named(audit: dict, check_id: str) -> set[str]:
    return {v["node"] for v in _check(audit, check_id)["violations"]}


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
    """Two DONE `integrate` nodes = two PRs for one run - a duplicate-land defect."""
    result = _run("audit_run_two_prs.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a run with two PR-opening nodes must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    audit = _audit_json("audit_run_two_prs.json")
    check = _check(audit, "one-pr")
    assert check["ok"] is False
    named = {v["node"] for v in check["violations"]}
    assert named == {"land-mod-a", "land-mod-b"}, (
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
    for unfinished in ("core-hook", "core-review"):
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


def test_a_coding_node_with_no_repo_cannot_be_attributed_and_fails(tmp_path):
    """Mutation proof: strip the `repo` off a coding node and the audit must refuse to pass it.

    Repo-boundness for coding work no longer rests on a dedicated `approach_kind` (there is no
    `wave` value) - it rests on the node's `approach` name, via `REPO_BOUND_APPROACHES`. An
    `odoo-coding` node with `repo: null` would silently escape every repo's readiness scope, so
    per-repo PR topology becomes unprovable. The unmutated fixture is green (asserted above), so
    this failure is caused by the mutation and nothing else.
    """
    raw = _fixture("audit_run_multi_repo_clean.json")
    target = next(n for n in raw["nodes"] if n["approach"] == "odoo-coding")
    target["repo"] = None
    mutated = tmp_path / "run-mutated.json"
    mutated.write_text(json.dumps(raw), encoding="utf-8")

    result = _run_file(mutated)
    assert result.returncode == EXIT_VIOLATION, (
        f"an unattributable coding node must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    audit = json.loads(_run_file(mutated, "--json").stdout)
    violations = _check(audit, "one-pr")["violations"]
    assert any(v["node"] == target["id"] for v in violations), (
        f"the unattributed coding node must be named, got {violations}"
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


# ---------------------------------------------------------------------------
# PR detection by the ACT, not the declaration
#
# The auditor used to read `approach_kind` alone, so a node that really opened a
# PR while declaring some other kind was invisible. A run file recording THREE
# PR URLs on ONE repository audited clean.
# ---------------------------------------------------------------------------


def test_a_node_that_opened_a_pr_counts_even_when_it_declares_another_kind():
    """Three PRs on one repo, two of them opened by nodes declaring `approach_kind: skill`.

    Premise first (so this cannot pass vacuously): the fixture must declare exactly ONE repo and
    exactly ONE `integrate` node - a declaration-only audit therefore sees a textbook one-PR run -
    while two further DONE nodes each recorded a distinct pull-request URL in `produced`. Three
    distinct PR URLs land on that single repo. Only an audit that reads the ACT can see them.
    """
    raw = _fixture("audit_run_pr_by_evidence.json")
    assert [r["id"] for r in raw["repos"]] == ["fleet-addons"], "fixture premise: one declared repo"
    declared = [n for n in _nodes(raw) if n["approach_kind"] == "integrate"]
    assert [n["id"] for n in declared] == ["integrate"], (
        f"fixture premise: exactly ONE node declares the land-tail kind, got {declared}"
    )
    undeclared_openers = {
        n["id"] for n in _nodes(raw)
        if n["approach_kind"] != "integrate"
        and _pr_urls(n["produced"]) - _pr_urls(n.get("inputs"))
        and n["approach"] != "odoo-pr-monitoring"
    }
    assert undeclared_openers == {"land-billing", "land-billing-account"}, (
        f"fixture premise: two non-integrate nodes must carry PR evidence, got {undeclared_openers}"
    )
    assert all(n["status"] == "DONE" for n in _nodes(raw) if n["id"] in undeclared_openers)
    all_urls = set().union(*(_pr_urls(n["produced"]) for n in _nodes(raw)))
    assert len(all_urls) == 3, f"fixture premise: three distinct PRs on one repo, got {all_urls}"

    result = _run("audit_run_pr_by_evidence.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"three PRs on one repo must exit {EXIT_VIOLATION} however the openers declare "
        f"themselves:\n{result.stdout}"
    )
    named = _named(_audit_json("audit_run_pr_by_evidence.json"), "one-pr")
    assert {"land-billing", "land-billing-account"} <= named, (
        f"the nodes that actually opened the extra PRs must be named, got {named}"
    )


def test_a_monitoring_node_handed_a_pr_url_is_never_counted_as_opening_one():
    """The discriminator for evidence-based detection: producing a URL you were GIVEN is not opening.

    `monitor-13` echoes the PR URL it received into its own `produced`. If PR evidence were read
    naively, this node would read as a fourth PR opener and the auditor would invent a violation
    that no run can fix. The clean multi-repo fixture would go red for the same reason.
    """
    raw = _fixture("audit_run_pr_by_evidence.json")
    monitor = next(n for n in _nodes(raw) if n["id"] == "monitor-13")
    assert monitor["approach"] == "odoo-pr-monitoring"
    assert _pr_urls(monitor["produced"]), (
        "fixture premise: the monitoring node must echo a PR URL in `produced`, or this proves "
        "nothing"
    )
    assert _pr_urls(monitor["produced"]) <= _pr_urls(monitor["inputs"]), (
        "fixture premise: the URL it echoes must be one it was handed as input"
    )

    named = _named(_audit_json("audit_run_pr_by_evidence.json"), "one-pr")
    assert "monitor-13" not in named, (
        f"a node handed a PR URL must not be read as having opened it, got {named}"
    )


def test_a_done_land_node_that_recorded_no_pr_url_fails_and_is_named():
    """The other half: a declaration with no act behind it.

    A land tail that reports DONE while recording no pull-request URL anywhere never proved a PR
    exists. The whole run file is otherwise impeccable - one repo, one `integrate` node, every
    other node settled - which is exactly why a declaration-only audit called it clean.
    """
    raw = _fixture("audit_run_integrate_without_pr.json")
    land = next(n for n in _nodes(raw) if n["approach_kind"] == "integrate")
    assert land["status"] == "DONE", "fixture premise: the land tail must claim to have landed"
    assert not _pr_urls(raw), (
        "fixture premise: NO pull-request URL may appear anywhere in the run file, otherwise the "
        "missing evidence is not what is being measured"
    )
    assert all(n["status"] in ("DONE", "SKIPPED") for n in _nodes(raw)), (
        "fixture premise: every node settled, so `pr-last` cannot be what fails here"
    )

    result = _run("audit_run_integrate_without_pr.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a land node with no recorded PR must exit {EXIT_VIOLATION}:\n{result.stdout}"
    )
    check = _check(_audit_json("audit_run_integrate_without_pr.json"), "one-pr")
    assert check["ok"] is False
    assert [v["node"] for v in check["violations"]] == ["integrate"], check["violations"]


# ---------------------------------------------------------------------------
# Land-tail membership is EXACT, never a substring of a free-text node id
#
# `is_land_tail` used to match `integrate`/`monitor`/`merge` as substrings of the
# node's own id, so plausible planner ids exempted themselves from the after-PR
# rule and the PR could open over unfinished work.
# ---------------------------------------------------------------------------


def test_a_node_id_that_merely_contains_a_land_tail_word_is_not_exempt():
    """`i18n-merge-catalogs` and `integrated-review` are ordinary pre-PR work, not the land tail.

    Premise first: both ids CONTAIN a land-tail word, neither node declares a land-tail kind nor
    runs the land-tail skill, both are unfinished, and the repo's real `integrate` node landed with
    a recorded PR URL. Under substring matching both are exempt and the run audits clean.
    """
    raw = _fixture("audit_run_land_tail_substring.json")
    by_id = {n["id"]: n for n in _nodes(raw)}
    for node_id, word in (("i18n-merge-catalogs", "merge"), ("integrated-review", "integrate")):
        node = by_id[node_id]
        assert word in node_id, f"fixture premise: {node_id!r} must contain {word!r}"
        assert node["approach_kind"] == "skill", (
            f"fixture premise: {node_id} must not declare a land-tail kind"
        )
        assert node["approach"] != "odoo-pr-monitoring", (
            f"fixture premise: {node_id} must not run the land-tail skill either"
        )
        assert node["status"] not in ("DONE", "SKIPPED"), (
            f"fixture premise: {node_id} must be unfinished, or nothing is being measured"
        )
    assert by_id["integrate"]["status"] == "DONE" and _pr_urls(by_id["integrate"]["produced"]), (
        "fixture premise: the PR must really be open, otherwise `pr-last` has nothing to judge"
    )

    result = _run("audit_run_land_tail_substring.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"work left unfinished behind an opened PR must exit {EXIT_VIOLATION} whatever the node "
        f"ids spell:\n{result.stdout}"
    )
    named = _named(_audit_json("audit_run_land_tail_substring.json"), "pr-last")
    assert named == {"i18n-merge-catalogs", "integrated-review"}, (
        f"both substring-exempted nodes must be named, got {named}"
    )


def test_the_real_land_tail_keeps_its_exemption_when_the_substring_hole_closes():
    """Tightening the test must not delete the exemption it was guarding.

    The same fixture carries a PENDING `odoo-pr-monitoring` node - the land tail doing its job
    after the PR opens. A fix that simply dropped the exemption would name it too, and would
    deadlock every real run's monitor stage.
    """
    raw = _fixture("audit_run_land_tail_substring.json")
    monitor = next(n for n in _nodes(raw) if n["id"] == "pr-monitor")
    assert monitor["approach"] == "odoo-pr-monitoring"
    assert monitor["status"] not in ("DONE", "SKIPPED"), (
        "fixture premise: the monitoring node must be unfinished, or its exemption is untested"
    )

    named = _named(_audit_json("audit_run_land_tail_substring.json"), "pr-last")
    assert "pr-monitor" not in named, (
        f"the real land tail must stay exempt from the after-PR rule, got {named}"
    )


def test_renaming_a_flagged_node_to_a_land_tail_lookalike_does_not_silence_the_finding(tmp_path):
    """Mutation proof that the exemption is no longer reachable through the node id.

    `audit_run_work_after_pr.json` fails on `i18n-reconcile`. Rename that node - and nothing else -
    to `i18n-merge-catalogs` and the substring rule would exempt it, flipping the run to clean.
    The finding must survive the rename, still naming the node under its new id.
    """
    raw = _fixture("audit_run_work_after_pr.json")
    target = next(n for n in raw["nodes"] if n["id"] == "i18n-reconcile")
    assert target["status"] not in ("DONE", "SKIPPED"), "fixture premise: still unfinished"
    target["id"] = "i18n-merge-catalogs"
    mutated = tmp_path / "run-renamed.json"
    mutated.write_text(json.dumps(raw), encoding="utf-8")

    result = _run_file(mutated)
    assert result.returncode == EXIT_VIOLATION, (
        f"renaming a node must not change the verdict:\n{result.stdout}"
    )
    audit = json.loads(_run_file(mutated, "--json").stdout)
    assert {v["node"] for v in _check(audit, "pr-last")["violations"]} == {"i18n-merge-catalogs"}


# ---------------------------------------------------------------------------
# `repo: null` is a carve-out for repo-less work, not an escape hatch
#
# Every `repo: null` node used to sit outside every check, so a run whose
# acceptance and doc stages were stamped `repo: null` opened its PR with neither
# having run - and the auditor passed it while PRINTING that it was blind.
# ---------------------------------------------------------------------------


def test_a_delivery_gating_stage_stamped_repo_null_fails_and_is_named():
    """Acceptance and doc gate this repo's PR; `repo: null` does not put them outside its scope.

    Premise first: the run declares one repo whose `integrate` node landed with a real PR URL,
    while the acceptance and doc stages carry `repo: null` and never ran. Every node that could
    have failed the old checks is either settled or repo-less, which is why this audited clean.
    """
    raw = _fixture("audit_run_repo_null_lifecycle.json")
    assert [r["id"] for r in raw["repos"]] == ["fleet-addons"]
    by_id = {n["id"]: n for n in _nodes(raw)}
    for gating in ("cluster-acceptance", "cluster-doc"):
        assert by_id[gating]["repo"] is None, f"fixture premise: {gating} must be `repo: null`"
        assert by_id[gating]["status"] not in ("DONE", "SKIPPED"), (
            f"fixture premise: {gating} must never have run"
        )
    assert by_id["integrate"]["status"] == "DONE" and _pr_urls(by_id["integrate"]["produced"]), (
        "fixture premise: the PR must really be open"
    )
    assert all(n["status"] in ("DONE", "SKIPPED") for n in _nodes(raw) if n["repo"]), (
        "fixture premise: every repo-TAGGED node is settled, so only the repo-less ones can fail"
    )

    result = _run("audit_run_repo_null_lifecycle.json")
    assert result.returncode == EXIT_VIOLATION, (
        f"a PR opened over unfinished `repo: null` lifecycle stages must exit "
        f"{EXIT_VIOLATION}:\n{result.stdout}"
    )
    audit = _audit_json("audit_run_repo_null_lifecycle.json")
    assert {"cluster-acceptance", "cluster-doc"} <= _named(audit, "one-pr"), (
        f"a delivery-gating stage must be told to name its repo, got {_named(audit, 'one-pr')}"
    )
    assert _named(audit, "pr-last") == {"cluster-acceptance", "cluster-doc"}, (
        f"both unfinished gating stages must be named behind the opened PR, got "
        f"{_named(audit, 'pr-last')}"
    )


def test_genuinely_repo_less_work_stays_out_of_every_repo_scope():
    """The discriminator: the rule targets delivery-gating stages, not the `repo: null` field.

    The same fixture carries an unfinished `repo: null` inline synthesis node. It gates nothing and
    writes into no repository, so naming it would make every chat-only node a false positive and
    would re-break the multi-repo scoping the earlier fix established.
    """
    raw = _fixture("audit_run_repo_null_lifecycle.json")
    summary = next(n for n in _nodes(raw) if n["id"] == "run-summary")
    assert summary["repo"] is None and summary["status"] not in ("DONE", "SKIPPED"), (
        "fixture premise: an unfinished genuinely repo-less node must be present"
    )

    audit = _audit_json("audit_run_repo_null_lifecycle.json")
    assert "run-summary" not in _named(audit, "one-pr") | _named(audit, "pr-last"), (
        "a chat-only synthesis node belongs to no repository and must stay out of scope"
    )


def test_odoo_instance_is_repo_bound_and_a_repo_null_verification_node_is_flagged(tmp_path):
    """A verification node writes no source but GATES that repo's delivery (M4).

    `odoo-instance` must be in `REPO_BOUND_APPROACHES`: without it, a `repo: null` verification
    node would sit outside every `integrate` scope, and a run could open its PR having proven
    nothing about the repo it claims to deliver. First the vocabulary, then the behavior it must
    produce: build a minimal per-repo run whose ONLY problem is a verification node stamped
    `repo: null`, and confirm the auditor refuses to let it hide.
    """
    module = _load_audit_module()
    assert "odoo-instance" in module.REPO_BOUND_APPROACHES, (
        "odoo-instance must be repo-bound: it writes no source but gates that repo's delivery"
    )

    run = {
        "run_id": "instance-repo-null-20260817-a1b2",
        "schema_version": "run/1.0",
        "intent": "verify fleet-addons on a live instance without naming its repo",
        "autonomy": "auto",
        "status": "DONE",
        "cursor": None,
        "budget": {"max_nodes": 8, "nodes_run": 2},
        "repos": [
            {
                "id": "fleet-addons",
                "base": "18.0",
                "verify": "make test",
                "commit": "<resolved by git-toolkit:git-ops>",
                "confidential": "public",
                "worktree_root": "<worktree parent outside the repo tree>",
            }
        ],
        "nodes": [
            {
                "id": "fleet-billing",
                "approach": "odoo-coding",
                "approach_kind": "skill",
                "repo": "fleet-addons",
                "inputs": {},
                "depends_on": [],
                "gate_tier": "L1",
                "status": "DONE",
                "produced": ["viin_fleet_billing/models/fleet_vehicle.py"],
                "contract": {
                    "status": "DONE",
                    "produced": ["viin_fleet_billing/models/fleet_vehicle.py"],
                    "next": [],
                },
            },
            {
                "id": "fleet-verify",
                "approach": "odoo-instance",
                "approach_kind": "skill",
                "repo": None,
                "inputs": {},
                "depends_on": ["fleet-billing"],
                "gate_tier": "L1",
                "status": "DONE",
                "produced": ["test verdict: 42 passed"],
                "contract": {"status": "DONE", "produced": ["test verdict: 42 passed"], "next": []},
            },
            {
                "id": "integrate",
                "approach": "git-toolkit:git-ops",
                "approach_kind": "integrate",
                "repo": "fleet-addons",
                "inputs": {},
                "depends_on": ["fleet-verify"],
                "gate_tier": "L1",
                "status": "DONE",
                "produced": ["https://example.invalid/org/fleet-addons/pull/61"],
                "contract": {
                    "status": "DONE",
                    "produced": ["https://example.invalid/org/fleet-addons/pull/61"],
                    "next": [],
                },
            },
        ],
        "dynamic_nodes": [],
        "gate_log": [
            {"node": "fleet-billing", "tier": "L1", "decision": "auto-pass"},
            {"node": "fleet-verify", "tier": "L1", "decision": "auto-pass"},
        ],
        "completion": {
            "status": "DONE",
            "evidence": ["https://example.invalid/org/fleet-addons/pull/61"],
            "summary": "the verification node gates fleet-addons' delivery but was stamped repo: null",
        },
    }
    run_file = tmp_path / "run-instance-repo-null.json"
    run_file.write_text(json.dumps(run), encoding="utf-8")

    result = _run_file(run_file)
    assert result.returncode == EXIT_VIOLATION, (
        f"a repo: null verification node must fail the audit:\n{result.stdout}\n{result.stderr}"
    )
    audit = json.loads(_run_file(run_file, "--json").stdout)
    named = _named(audit, "one-pr")
    assert "fleet-verify" in named, (
        f"the repo: null odoo-instance node must be named as unattributable, got {named}"
    )


# ---------------------------------------------------------------------------
# Verdict 3 - could-not-check. A run file the auditor cannot fully read is
# never reported as clean.
# ---------------------------------------------------------------------------


def test_a_dag_serialized_as_a_mapping_is_could_not_check_not_clean():
    """Every node vanishes when `nodes` is an object - and an empty DAG passes every assertion.

    Premise first: the mapping really does hide a violating run - two DONE `integrate` nodes on one
    repo, each with its own PR URL, plus an acceptance node that never ran. Reported as clean, this
    file certifies the exact topology the auditor exists to catch.
    """
    raw = _fixture("audit_run_nodes_not_a_list.json")
    assert isinstance(raw["nodes"], dict), "fixture premise: `nodes` must be a mapping"
    hidden = list(raw["nodes"].values())
    landed = [n for n in hidden if n["approach_kind"] == "integrate" and n["status"] == "DONE"]
    assert len(landed) == 2 and len({u for n in landed for u in _pr_urls(n["produced"])}) == 2, (
        f"fixture premise: two landed PRs on one repo must be hidden inside the mapping, got "
        f"{landed}"
    )
    assert any(n["status"] not in ("DONE", "SKIPPED") for n in hidden), (
        "fixture premise: unfinished work must be hidden in there too"
    )

    result = _run("audit_run_nodes_not_a_list.json")
    assert result.returncode == EXIT_USAGE, (
        f"an unreadable DAG must exit {EXIT_USAGE} (could-not-check), never 0:\n{result.stdout}"
    )
    audit = _audit_json("audit_run_nodes_not_a_list.json")
    assert audit["verdict"] == "could-not-check"
    assert audit["ok"] is False
    assert any("nodes" in problem for problem in audit["schema_problems"]), audit["schema_problems"]
    assert "COULD-NOT-CHECK" in result.stdout, result.stdout


def test_an_approach_kind_outside_the_schema_enum_is_could_not_check():
    """A kind the schema does not define may be a land step the auditor cannot classify.

    Premise first: every other node conforms and the run looks like a textbook single-PR run, so
    the unknown kind is the only thing that can change the verdict.
    """
    raw = _fixture("audit_run_unknown_approach_kind.json")
    kinds = {n["approach_kind"] for n in _nodes(raw)}
    assert "bogus-kind" in kinds, "fixture premise: an out-of-enum kind must be present"
    assert kinds - {"bogus-kind"} <= {"skill", "agent", "workflow", "inline", "integrate"}, (
        f"fixture premise: every OTHER kind must be in the documented enum, got {kinds}"
    )

    result = _run("audit_run_unknown_approach_kind.json")
    assert result.returncode == EXIT_USAGE, (
        f"an out-of-enum approach_kind must exit {EXIT_USAGE} (could-not-check):\n{result.stdout}"
    )
    audit = _audit_json("audit_run_unknown_approach_kind.json")
    assert audit["verdict"] == "could-not-check"
    assert any("land-step" in problem for problem in audit["schema_problems"]), (
        f"the finding must name the node carrying the unknown kind, got {audit['schema_problems']}"
    )


def test_the_three_verdicts_are_distinct_and_map_to_distinct_exit_codes():
    """clean / violation / could-not-check are three states, never two.

    The failure this guards is a run file that cannot be read being folded into `clean` - the
    difference between "the audit found nothing wrong" and "the audit could not look".
    """
    expected = {
        "audit_run_clean.json": ("clean", EXIT_OK),
        "audit_run_two_prs.json": ("violation", EXIT_VIOLATION),
        "audit_run_nodes_not_a_list.json": ("could-not-check", EXIT_USAGE),
    }
    seen = {}
    for fixture, (verdict, exit_code) in expected.items():
        result = _run(fixture)
        assert result.returncode == exit_code, f"{fixture}:\n{result.stdout}\n{result.stderr}"
        seen[fixture] = _audit_json(fixture)["verdict"]
        assert seen[fixture] == verdict, f"{fixture} reported {seen[fixture]!r}"
    assert len(set(seen.values())) == 3, f"the three verdicts must be distinct, got {seen}"
