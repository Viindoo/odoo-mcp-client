#!/usr/bin/env python3
"""audit-run.py - audit a FINISHED run-state file for the four run-topology properties.

Reads a `run-<id>.json` blackboard - the RUN-DAG artifact the `run-harness` driver writes
(schema SSOT: `plugins/odoo-ai-agents/docs/reference/workflow-harness.md` section 8.3, operating
procedure: `plugins/odoo-ai-agents/skills/run-harness/SKILL.md`) - and asserts the properties that
users complained were violated in real runs:

  1. [one-pr]      One PR per REPO. A PR-opening node is a node with
                   `approach_kind == "integrate"` - the terminal land-tail that squashes a repo's
                   run-integration branch, pushes it once, and opens THAT REPO's single PR (harness
                   8.3: "There is exactly ONE PR per REPO - never one per wave"). The run file
                   declares its repositories in `repos[]` and tags every node with `repo`, so the
                   check is per-repo: exactly one PR-opening node must reach DONE for EACH entry in
                   `repos[]`, and every `wave`/`integrate` node must name a declared repo. A run
                   file written before `repos[]` existed is audited in the LEGACY SINGLE-REPO form
                   (one PR for the whole run); the report names which form it ran in.
  2. [pr-last]     Nothing substantive after the PR opens - SCOPED PER REPO. If repo R's PR-opening
                   node is DONE, every node whose `repo` is R and that is OUTSIDE the land-tail set
                   {integrate, monitor, merge} must be DONE or SKIPPED. Repo A's PR is NOT held
                   hostage by repo B's unfinished nodes, and nodes with `repo: null` (chat-only
                   synthesis - belonging to no repository) are outside every repo's scope. A
                   coding/review/test node still unfinished behind ITS OWN repo's opened PR means
                   the run shipped a PR and then kept working - the topology complaint.
  3. [no-tier]     No tier jargon emitted. No `L0`/`L1`/`L2` token appears in any Continuation
                   Contract recorded in the run file (`nodes[].contract`). The node's own
                   `gate_tier` and the `gate_log[].tier` entries are the driver's INTERNAL control
                   values and are deliberately NOT scanned - only what a step EMITTED.
  4. [gates]       Gate count. Reports how many human gates the run hit, broken down by node, from
                   `gate_log[]`. Reported, never asserted: the right count depends on the run.

Usage:
    scripts/audit-run.py <path-to-run-<id>.json> [--json]

Exit codes:
    0  every assertion passed (check 4 is informational and never fails the run)
    1  at least one assertion was violated
    2  usage error, or the run file is missing / unreadable / not a JSON object

Stdlib only; no hardcoded paths; runs from any cwd.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- Schema vocabulary (derived from workflow-harness.md 8.3, never invented) ------------------

# The `approach_kind` of the terminal land node - the ONE node per repo that opens a PR.
# `odoo-coding` never pushes or opens a PR; `odoo-pr-monitoring` MERGES an already-open PR.
PR_OPENING_APPROACH_KINDS = ("integrate",)

# Node kinds that ALWAYS belong to a repository: a coding wave writes that repo's source tree, and
# an `integrate` node opens that repo's PR. `repo: null` on either is a serialization bug - it puts
# real work outside every repo's readiness scope. Every other kind may legitimately be repo-less.
REPO_BOUND_APPROACH_KINDS = ("wave", "integrate")

# Audit forms. The per-repo form is the real rule; the legacy form is the graceful fallback for a
# run file serialized before `repos[]`/`repo` existed.
FORM_PER_REPO = "per-repo"
FORM_LEGACY = "legacy-single-repo"

# The land tail: the nodes that legitimately run at or after the PR opens. `integrate` opens the
# PR, the monitoring node watches CI, the merge node lands it. Matched as tokens against a node's
# `approach_kind`, `approach`, and `id`, so `odoo-pr-monitoring` counts as `monitor`.
LAND_TAIL_TOKENS = ("integrate", "monitor", "merge")

# A node in one of these statuses is settled - it will not do any more work.
SETTLED_NODE_STATUSES = ("DONE", "SKIPPED")

DONE = "DONE"

# A gate_log decision that names an automatic pass. Anything else is a human sitting at the gate.
AUTO_GATE_DECISION_RE = re.compile(r"auto", re.I)

# The tier jargon a Continuation Contract must never carry.
TIER_TOKEN_RE = re.compile(r"\bL[012]\b")


# --- Run-file access --------------------------------------------------------------------------


def load_run(path: Path) -> dict:
    """Read the run-state file. Raises ValueError with a human-readable reason on any problem."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read run file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object, got {type(data).__name__}")
    return data


def all_nodes(run: dict) -> list[dict]:
    """Every node the run knows about: the planned DAG plus the nodes materialized at runtime."""
    nodes: list[dict] = []
    for key in ("nodes", "dynamic_nodes"):
        value = run.get(key) or []
        if isinstance(value, list):
            nodes += [n for n in value if isinstance(n, dict)]
    return nodes


def node_label(node: dict) -> str:
    """How a node is named in a finding - its id, falling back to its approach."""
    return str(node.get("id") or node.get("approach") or "<unnamed node>")


def is_pr_opening(node: dict) -> bool:
    return str(node.get("approach_kind") or "").strip().lower() in PR_OPENING_APPROACH_KINDS


def is_land_tail(node: dict) -> bool:
    """True if the node belongs to the land tail (it may legitimately run at/after PR open)."""
    haystack = " ".join(
        str(node.get(field) or "") for field in ("approach_kind", "approach", "id")
    ).lower()
    return any(token in haystack for token in LAND_TAIL_TOKENS)


def node_status(node: dict) -> str:
    return str(node.get("status") or "").strip().upper()


def declared_repos(run: dict) -> list[str]:
    """The repository ids the run declares in `repos[]`, in declaration order.

    Empty means the run file predates the field (or declares no usable id) - the caller then falls
    back to the legacy single-repo form rather than inventing a repository.
    """
    entries = run.get("repos")
    if not isinstance(entries, list):
        return []
    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        repo_id = str(entry.get("id") or "").strip()
        if repo_id and repo_id not in ids:
            ids.append(repo_id)
    return ids


def node_repo(node: dict) -> str | None:
    """The repository a node belongs to, or None when it belongs to none (chat-only synthesis)."""
    raw = node.get("repo")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def audit_form(run: dict) -> str:
    return FORM_PER_REPO if declared_repos(run) else FORM_LEGACY


# --- Checks -----------------------------------------------------------------------------------


def _result(check_id: str, ok: bool, note: str, violations: list[dict]) -> dict:
    return {"id": check_id, "ok": ok, "note": note, "violations": violations}


def check_one_pr_per_repo(run: dict) -> dict:
    """1. Exactly one PR-opening node reached DONE per declared repository.

    Per-repo form (`repos[]` declared): every `wave`/`integrate` node must name a declared repo,
    and each `repos[]` entry must have exactly one PR-opening node at DONE. A run that opened NO
    PR at all lands nothing (chat-only / review-only) and is legal.

    Legacy form (no `repos[]`): the whole run is one repository bucket - exactly one PR-opening
    node at DONE, zero declared being legal. No `repo` is invented to pretend otherwise.
    """
    nodes = all_nodes(run)
    repos = declared_repos(run)
    declared = [n for n in nodes if is_pr_opening(n)]
    landed = [n for n in declared if node_status(n) == DONE]

    if not repos:
        note = (
            f"{len(landed)} PR-opening node(s) reached DONE out of {len(declared)} declared "
            f"(approach_kind in {list(PR_OPENING_APPROACH_KINDS)}); this run file declares no "
            f"`repos[]`, so it was audited in the {FORM_LEGACY} form - one PR for the whole run"
        )
        if len(landed) > 1:
            return _result("one-pr", False, note, [
                {"node": node_label(n),
                 "detail": f"PR-opening node reached {DONE} - a run opens exactly one PR per repo"}
                for n in landed
            ])
        if declared and not landed:
            return _result("one-pr", False, note, [
                {"node": node_label(n),
                 "detail": f"PR-opening node declared but its status is "
                           f"{node_status(n) or '<unset>'}, not {DONE} - the run never landed"}
                for n in declared
            ])
        return _result("one-pr", True, note, [])

    violations: list[dict] = []

    # (a) Attribution. A coding wave or a land tail with no declared repo cannot be attributed to
    #     any PR, which makes "one PR per repo" unprovable for the whole run.
    for node in nodes:
        kind = str(node.get("approach_kind") or "").strip().lower()
        if kind not in REPO_BOUND_APPROACH_KINDS:
            continue
        repo = node_repo(node)
        if repo is None:
            violations.append({
                "node": node_label(node),
                "detail": f"approach_kind {kind!r} carries no `repo` - a node that writes a repo's "
                          f"source or opens its PR must name one of {repos}",
            })
        elif repo not in repos:
            violations.append({
                "node": node_label(node),
                "detail": f"names repo {repo!r}, which is absent from repos[] {repos}",
            })

    # (b) One PR per declared repo - unless the run landed nothing at all.
    if declared:
        for repo in repos:
            landed_here = [n for n in landed if node_repo(n) == repo]
            declared_here = [n for n in declared if node_repo(n) == repo]
            if len(landed_here) > 1:
                violations += [
                    {"node": node_label(n),
                     "detail": f"second PR-opening node at {DONE} for repo {repo!r} - each repo "
                               f"opens exactly one PR"}
                    for n in landed_here
                ]
            elif not landed_here and declared_here:
                violations += [
                    {"node": node_label(n),
                     "detail": f"PR-opening node for repo {repo!r} declared but its status is "
                               f"{node_status(n) or '<unset>'}, not {DONE} - that repo never landed"}
                    for n in declared_here
                ]
            elif not declared_here:
                violations.append({
                    "node": f"<repo {repo}>",
                    "detail": f"repo {repo!r} is declared in repos[] but the run has no PR-opening "
                              f"node for it, while {len(landed)} other PR(s) opened - every repo "
                              f"the run touches gets its own PR",
                })

    repoless = sum(1 for n in nodes if node_repo(n) is None)
    note = (
        f"{FORM_PER_REPO} form over repos[] {repos}: {len(landed)} PR-opening node(s) at {DONE} "
        f"out of {len(declared)} declared; {repoless} node(s) belong to no repository (`repo: null`)"
    )
    return _result("one-pr", not violations, note, violations)


def check_nothing_substantive_after_pr(run: dict) -> dict:
    """2. No repo's PR-opening node is DONE while THAT repo's substantive work is unfinished.

    Scoped per repo: repo A's opened PR is judged against repo A's nodes only, so a legitimately
    unfinished repo B never shows up as a violation of A, and `repo: null` nodes (belonging to no
    repository) are outside every repo's scope. Without `repos[]` this falls back to the legacy
    whole-run scope.
    """
    nodes = all_nodes(run)
    repos = declared_repos(run)
    landed = [n for n in nodes if is_pr_opening(n) and node_status(n) == DONE]

    def _unfinished(bucket: list[dict]) -> list[dict]:
        return [
            n for n in bucket
            if not is_land_tail(n) and node_status(n) not in SETTLED_NODE_STATUSES
        ]

    if not repos:
        unfinished = _unfinished(nodes)
        note = (
            f"{FORM_LEGACY} form (no repos[] declared): {len(landed)} PR-opening node(s) DONE; "
            f"{len(unfinished)} substantive node(s) outside the land tail "
            f"{list(LAND_TAIL_TOKENS)} not in {list(SETTLED_NODE_STATUSES)}"
        )
        if not landed or not unfinished:
            return _result("pr-last", True, note, [])
        opened_by = ", ".join(node_label(n) for n in landed)
        return _result("pr-last", False, note, [
            {"node": node_label(n),
             "detail": f"status {node_status(n) or '<unset>'} while PR-opening node(s) "
                       f"[{opened_by}] already reached {DONE}"}
            for n in unfinished
        ])

    violations: list[dict] = []
    landed_repos: list[str] = []
    for repo in repos:
        landed_here = [n for n in landed if node_repo(n) == repo]
        if not landed_here:
            continue
        landed_repos.append(repo)
        opened_by = ", ".join(node_label(n) for n in landed_here)
        violations += [
            {"node": node_label(n),
             "detail": f"status {node_status(n) or '<unset>'} in repo {repo!r} while THAT repo's "
                       f"PR-opening node(s) [{opened_by}] already reached {DONE}"}
            for n in _unfinished([n for n in nodes if node_repo(n) == repo])
        ]

    repoless_open = len(_unfinished([n for n in nodes if node_repo(n) is None]))
    note = (
        f"{FORM_PER_REPO} form: repo(s) {landed_repos or []} have an opened PR; scope is that "
        f"repo's OWN nodes outside the land tail {list(LAND_TAIL_TOKENS)} - other repos' nodes and "
        f"the {repoless_open} unfinished `repo: null` node(s) are deliberately out of scope"
    )
    return _result("pr-last", not violations, note, violations)


def _walk_strings(value, path: str):
    """Yield (json-path, string) for every string in a nested contract - keys included, since a
    tier token can hide in a field NAME as easily as in its value."""
    if isinstance(value, dict):
        for key, sub in value.items():
            yield f"{path}.{key}", str(key)
            yield from _walk_strings(sub, f"{path}.{key}")
    elif isinstance(value, list):
        for i, sub in enumerate(value):
            yield from _walk_strings(sub, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


def check_no_tier_jargon(run: dict) -> dict:
    """3. No L0/L1/L2 token in any recorded Continuation Contract.

    Scanned: `nodes[].contract` / `dynamic_nodes[].contract` only. The node's own `gate_tier` and
    `gate_log[].tier` are the driver's internal control values - legitimate, never scanned.
    """
    violations: list[dict] = []
    scanned = 0
    for node in all_nodes(run):
        contract = node.get("contract")
        if contract in (None, {}, [], ""):
            continue
        scanned += 1
        for json_path, text in _walk_strings(contract, "contract"):
            for m in TIER_TOKEN_RE.finditer(text):
                violations.append({
                    "node": node_label(node),
                    "detail": f"tier token {m.group()!r} at {json_path}: {text.strip()[:120]!r}",
                })
    note = f"{scanned} recorded Continuation Contract(s) scanned"
    return _result("no-tier", not violations, note, violations)


def report_gates(run: dict) -> dict:
    """4. Human-gate count, broken down by node. Reported, never asserted."""
    entries = run.get("gate_log") or []
    entries = [e for e in entries if isinstance(e, dict)]
    by_node: dict[str, int] = {}
    human = 0
    for entry in entries:
        decision = str(entry.get("decision") or "")
        if AUTO_GATE_DECISION_RE.search(decision):
            continue
        human += 1
        name = str(entry.get("node") or "<unnamed node>")
        by_node[name] = by_node.get(name, 0) + 1
    return {
        "human_gate_count": human,
        "by_node": dict(sorted(by_node.items())),
        "total_gate_log_entries": len(entries),
    }


CHECKS = (
    ("one-pr", "One PR per repo", check_one_pr_per_repo),
    ("pr-last", "Nothing substantive after the PR opens (per repo)",
     check_nothing_substantive_after_pr),
    ("no-tier", "No tier jargon in any emitted contract", check_no_tier_jargon),
)


# --- Reporting ---------------------------------------------------------------------------------


def audit(run: dict, run_file: Path) -> dict:
    results = [check(run) for _cid, _title, check in CHECKS]
    return {
        "run_file": str(run_file),
        "run_id": run.get("run_id"),
        "run_status": run.get("status"),
        "form": audit_form(run),
        "repos": declared_repos(run),
        "ok": all(r["ok"] for r in results),
        "checks": results,
        "gates": report_gates(run),
    }


def print_text_report(audit_result: dict) -> None:
    titles = {cid: title for cid, title, _check in CHECKS}
    print(f"audit-run: {audit_result['run_file']}")
    print(f"  run_id: {audit_result.get('run_id')}   status: {audit_result.get('run_status')}")
    repos = audit_result.get("repos") or []
    scope = ", ".join(repos) if repos else "none declared - run file predates `repos[]`"
    print(f"  form: {audit_result.get('form')}   repos[]: {scope}")
    for result in audit_result["checks"]:
        mark = "PASS" if result["ok"] else "FAIL"
        print(f"  [{mark}] {result['id']} - {titles.get(result['id'], result['id'])}")
        print(f"         {result['note']}")
        for violation in result["violations"]:
            print(f"         -> node {violation['node']}: {violation['detail']}")
    gates = audit_result["gates"]
    print(f"  [INFO] gates - {gates['human_gate_count']} human gate(s) hit "
          f"across {gates['total_gate_log_entries']} gate_log entr(ies)")
    if gates["by_node"]:
        for name, count in gates["by_node"].items():
            print(f"         -> node {name}: {count}")
    else:
        print("         -> no human gate recorded")
    print(f"  RESULT: {'OK' if audit_result['ok'] else 'VIOLATIONS FOUND'}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="audit-run.py",
        description="Audit a finished run-<id>.json for the four run-topology properties.",
    )
    parser.add_argument("run_file", help="path to the finished run-<id>.json run-state file")
    parser.add_argument("--json", action="store_true",
                        help="emit the audit as JSON instead of a text report")
    args = parser.parse_args(argv)

    run_file = Path(args.run_file)
    try:
        run = load_run(run_file)
    except ValueError as exc:
        print(f"audit-run: {exc}", file=sys.stderr)
        return 2

    audit_result = audit(run, run_file)
    if args.json:
        print(json.dumps(audit_result, indent=2, sort_keys=True))
    else:
        print_text_report(audit_result)
    return 0 if audit_result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
