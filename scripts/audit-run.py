#!/usr/bin/env python3
"""audit-run.py - audit a FINISHED run-state file for the four run-topology properties.

Reads a `run-<id>.json` blackboard - the RUN-DAG artifact the `run-harness` driver writes
(schema SSOT: `plugins/odoo-ai-agents/docs/reference/workflow-harness.md` section 8.3, operating
procedure: `plugins/odoo-ai-agents/skills/run-harness/SKILL.md`) - and asserts the properties that
users complained were violated in real runs:

  1. [one-pr]      One PR per REPO. A PR-opening node is detected by the ACT first and the
                   DECLARATION second: a node that recorded a pull-request URL in `produced`
                   OPENED a PR whatever its `approach_kind` says, and a node declaring
                   `approach_kind: "integrate"` is the land tail that is SUPPOSED to open one
                   (harness 8.3: "There is exactly ONE PR per REPO."). The two
                   signals must agree: a node that produced a PR URL without declaring `integrate`
                   is a finding (an undeclared land step), and a DONE `integrate` node that
                   produced no PR URL is a finding too (the land step's evidence is missing). The
                   run file declares its repositories in `repos[]` and tags every node with `repo`,
                   so the count is per-repo: exactly one PR-opening node must land for EACH entry in
                   `repos[]`, and every node that writes a repo's source or gates its delivery must
                   name a declared repo. A run file written before `repos[]` existed is audited in
                   the LEGACY SINGLE-REPO form (one PR for the whole run); the report names which
                   form it ran in.
  2. [pr-last]     Nothing substantive after the PR opens - SCOPED PER REPO. If repo R's PR-opening
                   node landed, every node whose `repo` is R and that is OUTSIDE the land tail must
                   be DONE or SKIPPED. Repo A's PR is NOT held hostage by repo B's unfinished
                   nodes. A node with `repo: null` is out of scope ONLY when it is genuinely
                   repo-less work (a chat-only synthesis / routing node): a `repo: null` node that
                   runs a delivery-gating lifecycle stage is IN scope and is a finding, because a
                   stage that gates a repository's PR belongs to that repository.
  3. [no-tier]     No tier jargon emitted. No `L0`/`L1`/`L2` token appears in any Continuation
                   Contract recorded in the run file (`nodes[].contract`). The node's own
                   `gate_tier` and the `gate_log[].tier` entries are the driver's INTERNAL control
                   values and are deliberately NOT scanned - only what a step EMITTED.
  4. [gates]       Gate count. Reports how many human gates the run hit, broken down by node, from
                   `gate_log[]`. Reported, never asserted: the right count depends on the run.

Three verdicts, never two - a run file the auditor cannot fully understand is NEVER reported as
clean:

  clean            every assertion passed
  violation        at least one assertion was violated, each finding naming its node
  could-not-check  the run file is missing, unparseable, or shaped outside the documented schema
                   (a `nodes` mapping instead of an array, an `approach_kind` outside the schema's
                   enum, a node with no id, ...). The auditor reports what it could not read and
                   refuses to issue a verdict on the parts it could.

Usage:
    scripts/audit-run.py <path-to-run-<id>.json> [--json]

Exit codes:
    0  clean - every assertion passed (check 4 is informational and never fails the run)
    1  violation - at least one assertion was violated
    2  could-not-check - usage error, or the run file is missing / unreadable / not JSON / not
       shaped like the documented run-state schema

Stdlib only; no hardcoded paths; runs from any cwd.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- Schema vocabulary (derived from workflow-harness.md 8.3, never invented) ------------------

# The documented `approach_kind` enum. A kind outside it is not audited as if it were harmless:
# the auditor cannot tell whether an unknown kind opens a PR, so it reports could-not-check.
APPROACH_KINDS = ("skill", "agent", "workflow", "inline", "integrate")

# The documented node `status` enum, same reasoning.
NODE_STATUSES = (
    "PENDING", "READY", "RUNNING", "DONE", "FAILED", "SKIPPED", "BLOCKED", "NEEDS_CONTEXT",
)

# The `approach_kind` of the terminal land node - the ONE node per repo that is SUPPOSED to open a
# PR. This is the DECLARATION half of PR detection; `opened_pr_urls()` is the ACT half, and the two
# are cross-checked against each other.
PR_OPENING_APPROACH_KINDS = ("integrate",)

# The only `approach_kind` that is ALWAYS repo-bound by its KIND alone: an `integrate` node opens
# that repo's PR. `repo: null` on it is a serialization bug - it puts real work outside every
# repo's readiness scope. Repo-boundness for CODING work no longer rests on the kind (there is no
# `wave` kind) - it rests on the node's `approach` name, via REPO_BOUND_APPROACHES below.
REPO_BOUND_APPROACH_KINDS = ("integrate",)

# Stage skills that CANNOT be repo-less either: each one writes into a repository's tree or gates
# that repository's delivery, so `repo: null` on one of them is a mis-stamped lifecycle node, not
# repo-less work. Sourced from the Terminal stage order constant (its ONE owner is
# `plugins/odoo-ai-agents/skills/run-harness/references/run-integration.md`, section "Terminal
# stage order") plus the code-changing front doors the coding nodes dispatch. `odoo-instance` is
# included even though it writes no source: a verification node writes no source but GATES that
# repo's delivery, so without this a `repo: null` verification node would pass the audit and sit
# outside every `integrate` scope.
REPO_BOUND_APPROACHES = (
    "odoo-coding",             # writes a repo's source
    "odoo-test-writing",       # writes a repo's tests
    "odoo-code-review",        # (1) review - the pre-PR review; it can force code changes
    "odoo-instance",           # writes no source but GATES that repo's delivery (test verdict)
    "odoo-i18n",               # (2) i18n reconcile - writes .po/.pot into a repo
    "odoo-acceptance",         # (3) live blast-radius oracle - gates that repo's PR
    "odoo-doc-illustration",   # (4) user guide + App-Store landing - writes into a repo
    "odoo-pr-monitoring",      # monitor + merge - watches ONE repo's PR
    "git-toolkit:git-ops",     # (6) the land step itself
)

# Artefact suffixes that only a repository source tree carries. A node that produced one of these
# wrote into some repository, so it must name which.
REPO_SOURCE_SUFFIXES = (".py", ".xml", ".js", ".po", ".pot", ".scss")

# Audit forms. The per-repo form is the real rule; the legacy form is the graceful fallback for a
# run file serialized before `repos[]`/`repo` existed.
FORM_PER_REPO = "per-repo"
FORM_LEGACY = "legacy-single-repo"

# The land tail: the nodes that legitimately run at or after the PR opens. Membership is EXACT,
# never a substring of a free-text node id - `i18n-merge-catalogs` and `integrated-review` contain
# a land-tail word and are ordinary pre-PR work. A node is land tail when its `approach_kind` is
# exactly `integrate` (the node that opens the PR) or its `approach` resolves exactly to
# `odoo-pr-monitoring`, the ONE skill the Terminal stage order assigns to both `monitor` and
# `merge`. The node's `id` is never consulted.
LAND_TAIL_APPROACH_KINDS = ("integrate",)
LAND_TAIL_APPROACHES = ("odoo-pr-monitoring",)

# A node that OBSERVES an already-open PR is handed its URL; it never opens one. Same skill as the
# land tail's monitor/merge stages.
POST_PR_OBSERVER_APPROACHES = LAND_TAIL_APPROACHES

# A node in one of these statuses is settled - it will not do any more work.
SETTLED_NODE_STATUSES = ("DONE", "SKIPPED")

DONE = "DONE"

# A gate_log decision that names an automatic pass. Anything else is a human sitting at the gate.
AUTO_GATE_DECISION_RE = re.compile(r"auto", re.I)

# The tier jargon a Continuation Contract must never carry.
TIER_TOKEN_RE = re.compile(r"\bL[012]\b")

# A recorded pull-request URL - the observable evidence that a node ACTUALLY opened a PR, across
# the forge flavours a run can land on (GitHub/Gitea `pull`/`pulls`, Bitbucket `pull-requests`,
# GitLab `merge_requests`). Matched inside a longer string, so "PR opened: <url>" counts.
PR_URL_RE = re.compile(
    r"https?://[^\s\"'<>()\[\]]+/(?:pull|pulls|pull-requests|merge_requests|merge-requests)/\d+",
    re.I,
)

VERDICT_CLEAN = "clean"
VERDICT_VIOLATION = "violation"
VERDICT_COULD_NOT_CHECK = "could-not-check"

EXIT_CLEAN = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_CHECK = 2


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
    """Every node the run knows about: the planned DAG plus the nodes materialized at runtime.

    Only reachable after `schema_problems()` came back empty, so every element really is an object
    and no node is silently dropped here.
    """
    nodes: list[dict] = []
    for key in ("nodes", "dynamic_nodes"):
        value = run.get(key) or []
        if isinstance(value, list):
            nodes += [n for n in value if isinstance(n, dict)]
    return nodes


def node_label(node: dict) -> str:
    """How a node is named in a finding - its id, falling back to its approach."""
    return str(node.get("id") or node.get("approach") or "<unnamed node>")


def approach_kind(node: dict) -> str:
    return str(node.get("approach_kind") or "").strip().lower()


def approach_is(node: dict, names: tuple[str, ...]) -> bool:
    """EXACT identity test for a node's `approach`, tolerating a `<plugin>:<skill>` qualifier.

    Exact by construction: `odoo-i18n` matches `odoo-i18n` and `odoo-ai-agents:odoo-i18n`, and
    never `i18n-merge-catalogs`. Substring matching is what let a free-text id exempt itself from
    the after-PR rule; nothing here looks at `id`.
    """
    approach = str(node.get("approach") or "").strip().lower()
    if not approach:
        return False
    return any(approach == name or approach.endswith(":" + name) for name in names)


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


# --- PR detection: the ACT (evidence) cross-checked against the DECLARATION --------------------


def _iter_strings(value):
    """Every string reachable inside a nested JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, sub in value.items():
            yield str(key)
            yield from _iter_strings(sub)
    elif isinstance(value, list):
        for sub in value:
            yield from _iter_strings(sub)


def _collect_pr_urls(value) -> set[str]:
    return {m.group(0) for text in _iter_strings(value) for m in PR_URL_RE.finditer(text)}


def produced_pr_urls(node: dict) -> set[str]:
    """PR URLs the node recorded as ITS OWN output: `produced[]` and the contract's `produced[]`."""
    urls = _collect_pr_urls(node.get("produced"))
    contract = node.get("contract")
    if isinstance(contract, dict):
        urls |= _collect_pr_urls(contract.get("produced"))
    return urls


def opened_pr_urls(node: dict) -> set[str]:
    """The PR URLs this node OPENED - the observable act, independent of what it declares.

    Two subtractions keep an observer from being mistaken for an opener:
      - a URL the node also carries in `inputs` was HANDED to it, not created by it;
      - a `odoo-pr-monitoring` node watches a PR someone else opened, so its output never counts.
    """
    if approach_is(node, POST_PR_OBSERVER_APPROACHES):
        return set()
    return produced_pr_urls(node) - _collect_pr_urls(node.get("inputs"))


def opened_pr(node: dict) -> bool:
    return bool(opened_pr_urls(node))


def declares_pr_open(node: dict) -> bool:
    return approach_kind(node) in PR_OPENING_APPROACH_KINDS


def is_pr_opening(node: dict) -> bool:
    """A node that opens a PR - by the act it recorded, or by the role it declares."""
    return opened_pr(node) or declares_pr_open(node)


def is_landed_pr(node: dict) -> bool:
    """A node whose PR is actually up: it recorded a PR URL, or it is the land tail and is DONE."""
    return opened_pr(node) or (declares_pr_open(node) and node_status(node) == DONE)


def is_land_tail(node: dict) -> bool:
    """True if the node belongs to the land tail (it may legitimately run at/after PR open).

    EXACT against the node's kind and its resolved skill identity - never a substring of the
    free-text `id`, which is how `i18n-merge-catalogs` and `integrated-review` used to exempt
    themselves from the after-PR rule.
    """
    return approach_kind(node) in LAND_TAIL_APPROACH_KINDS or approach_is(node, LAND_TAIL_APPROACHES)


def produced_repo_source(node: dict) -> list[str]:
    """Artefacts in `produced[]` that can only live inside a repository source tree."""
    found = []
    for text in _iter_strings(node.get("produced")):
        candidate = text.strip()
        if "://" in candidate:
            continue
        if candidate.lower().endswith(REPO_SOURCE_SUFFIXES):
            found.append(candidate)
    return found


def repo_binding_reasons(node: dict) -> list[str]:
    """Why this node MUST name a repository. Empty means it may legitimately be repo-less.

    A node is repo-bound when it writes a repository's source or gates a repository's delivery.
    Everything else - chat-only synthesis, routing, a report - may carry `repo: null`.
    """
    reasons: list[str] = []
    kind = approach_kind(node)
    if kind in REPO_BOUND_APPROACH_KINDS:
        reasons.append(
            f"approach_kind {kind!r} writes a repository's source or opens its PR"
        )
    if approach_is(node, REPO_BOUND_APPROACHES):
        reasons.append(
            f"approach {str(node.get('approach'))!r} is a lifecycle stage that writes into a "
            f"repository or gates its delivery"
        )
    if opened_pr(node):
        reasons.append(
            f"recorded pull-request URL(s) {sorted(opened_pr_urls(node))} in `produced`"
        )
    sources = produced_repo_source(node)
    if sources:
        reasons.append(f"produced repository source {sources}")
    return reasons


# --- Schema readability: the could-not-check state ---------------------------------------------


def _node_problems(node, where: str, index: int, per_repo: bool) -> list[str]:
    at = f"{where}[{index}]"
    if not isinstance(node, dict):
        return [f"{at} must be a JSON object, got {type(node).__name__} - a node the auditor "
                f"cannot read is a node it cannot audit"]
    problems: list[str] = []
    label = str(node.get("id") or "").strip()
    if not label:
        problems.append(f"{at} has no `id` - a finding could not name it")
    at = f"{at} ({label or '<unnamed>'})"

    kind = node.get("approach_kind")
    if kind is None:
        problems.append(f"{at} has no `approach_kind` - the auditor cannot tell whether it "
                        f"opens a PR")
    elif str(kind).strip().lower() not in APPROACH_KINDS:
        problems.append(f"{at} has approach_kind {kind!r}, outside the documented enum "
                        f"{list(APPROACH_KINDS)} - an unknown kind may be a land step the auditor "
                        f"cannot classify")

    status = node.get("status")
    if status is None:
        problems.append(f"{at} has no `status` - the auditor cannot tell whether it finished")
    elif str(status).strip().upper() not in NODE_STATUSES:
        problems.append(f"{at} has status {status!r}, outside the documented enum "
                        f"{list(NODE_STATUSES)}")

    if per_repo and "repo" not in node:
        problems.append(f"{at} has no `repo` key while the run declares `repos[]` - an absent "
                        f"field is not the same assertion as an explicit `repo: null`")
    elif not (node.get("repo") is None or isinstance(node.get("repo"), str)):
        problems.append(f"{at} has repo {node.get('repo')!r} - it must be a repos[].id string "
                        f"or null")

    for field, types, shape in (
        ("produced", (list,), "array"),
        ("depends_on", (list,), "array"),
        ("inputs", (dict,), "object"),
        ("contract", (dict,), "object"),
    ):
        value = node.get(field)
        if field in node and value is not None and not isinstance(value, types):
            problems.append(f"{at} has `{field}` of type {type(value).__name__}, expected a JSON "
                            f"{shape}")
    return problems


def schema_problems(run: dict) -> list[str]:
    """Everything about this run file the auditor cannot read as the documented schema.

    Non-empty means could-not-check: the auditor refuses to certify a file whose shape hides nodes
    from it. The classic silent pass is `nodes` serialized as a mapping - every node then vanishes
    and every assertion passes over an empty DAG.
    """
    problems: list[str] = []

    if "nodes" not in run:
        problems.append("no `nodes` array - a run-state file always serializes its DAG; auditing "
                        "an absent DAG would certify nothing as clean")
    for key in ("nodes", "dynamic_nodes"):
        value = run.get(key)
        if key in run and value is not None and not isinstance(value, list):
            problems.append(f"`{key}` must be a JSON array, got {type(value).__name__} - every "
                            f"node inside it would be invisible to the audit")

    repos_raw = run.get("repos")
    if "repos" in run and repos_raw is not None and not isinstance(repos_raw, list):
        problems.append(f"`repos` must be a JSON array, got {type(repos_raw).__name__} - the run "
                        f"would silently fall back to the legacy single-repo form")
    if isinstance(repos_raw, list):
        for i, entry in enumerate(repos_raw):
            if not isinstance(entry, dict):
                problems.append(f"repos[{i}] must be a JSON object, got {type(entry).__name__}")
            elif not str(entry.get("id") or "").strip():
                problems.append(f"repos[{i}] has no `id` - nodes cannot be attributed to it")

    gate_log = run.get("gate_log")
    if "gate_log" in run and gate_log is not None and not isinstance(gate_log, list):
        problems.append(f"`gate_log` must be a JSON array, got {type(gate_log).__name__}")
    if isinstance(gate_log, list):
        for i, entry in enumerate(gate_log):
            if not isinstance(entry, dict):
                problems.append(f"gate_log[{i}] must be a JSON object, got "
                                f"{type(entry).__name__}")

    per_repo = bool(declared_repos(run))
    for key in ("nodes", "dynamic_nodes"):
        value = run.get(key)
        if not isinstance(value, list):
            continue
        for i, node in enumerate(value):
            problems += _node_problems(node, key, i, per_repo)

    return problems


# --- Checks -----------------------------------------------------------------------------------


def _result(check_id: str, ok: bool, note: str, violations: list[dict]) -> dict:
    return {"id": check_id, "ok": ok, "note": note, "violations": violations}


def _declaration_evidence_violations(nodes: list[dict]) -> list[dict]:
    """Findings where what a node DID and what it DECLARED disagree about opening a PR."""
    violations: list[dict] = []
    for node in nodes:
        urls = sorted(opened_pr_urls(node))
        if urls and not declares_pr_open(node):
            violations.append({
                "node": node_label(node),
                "detail": f"recorded pull-request URL(s) {urls} in `produced` while declaring "
                          f"approach_kind {approach_kind(node) or '<unset>'!r} - a PR is opened "
                          f"ONLY by the terminal land node "
                          f"(approach_kind {PR_OPENING_APPROACH_KINDS[0]!r}), once per repo",
            })
        if len(urls) > 1:
            violations.append({
                "node": node_label(node),
                "detail": f"recorded {len(urls)} distinct pull-request URLs {urls} - one land step "
                          f"opens exactly one PR",
            })
        if declares_pr_open(node) and node_status(node) == DONE and not urls:
            violations.append({
                "node": node_label(node),
                "detail": f"declares approach_kind {approach_kind(node)!r} and reached {DONE} but "
                          f"recorded no pull-request URL in `produced` - the land step's own "
                          f"evidence is missing, so no PR can be confirmed",
            })
    return violations


def check_one_pr_per_repo(run: dict) -> dict:
    """1. Exactly one PR-opening node landed per declared repository, act and declaration agreeing.

    Per-repo form (`repos[]` declared): every node that writes a repo's source or gates its
    delivery must name a declared repo, and each `repos[]` entry must have exactly one PR-opening
    node landed. A run that opened NO PR at all lands nothing (chat-only / review-only) and is
    legal.

    Legacy form (no `repos[]`): the whole run is one repository bucket - exactly one PR-opening
    node landed, zero declared being legal. No `repo` is invented to pretend otherwise.
    """
    nodes = all_nodes(run)
    repos = declared_repos(run)
    declared = [n for n in nodes if is_pr_opening(n)]
    landed = [n for n in nodes if is_landed_pr(n)]
    pr_urls = sorted({url for n in nodes for url in opened_pr_urls(n)})

    disagreements = _declaration_evidence_violations(nodes)

    if not repos:
        note = (
            f"{len(landed)} PR-opening node(s) landed out of {len(declared)} detected "
            f"(declared approach_kind {list(PR_OPENING_APPROACH_KINDS)} or evidenced by a "
            f"pull-request URL in `produced`); {len(pr_urls)} distinct PR URL(s) recorded; this "
            f"run file declares no `repos[]`, so it was audited in the {FORM_LEGACY} form - one PR "
            f"for the whole run"
        )
        violations = list(disagreements)
        if len(landed) > 1:
            violations += [
                {"node": node_label(n),
                 "detail": f"PR-opening node landed - a run opens exactly one PR per repo"}
                for n in landed
            ]
        elif declared and not landed:
            violations += [
                {"node": node_label(n),
                 "detail": f"PR-opening node declared but its status is "
                           f"{node_status(n) or '<unset>'}, not {DONE} - the run never landed"}
                for n in declared
            ]
        return _result("one-pr", not violations, note, violations)

    violations: list[dict] = list(disagreements)

    # (a) Attribution. A node that writes a repo's source or gates its delivery and names no repo
    #     cannot be attributed to any PR, which makes "one PR per repo" unprovable for the run.
    for node in nodes:
        repo = node_repo(node)
        reasons = repo_binding_reasons(node)
        if repo is None:
            if reasons:
                violations.append({
                    "node": node_label(node),
                    "detail": f"carries `repo: null` but is repo-bound work ({'; '.join(reasons)})"
                              f" - it must name one of {repos}",
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
            urls_here = sorted({url for n in landed_here for url in opened_pr_urls(n)})
            if len(landed_here) > 1:
                violations += [
                    {"node": node_label(n),
                     "detail": f"PR-opening node landed for repo {repo!r} alongside "
                               f"{len(landed_here) - 1} other(s) (PR URLs {urls_here}) - each repo "
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
        f"{FORM_PER_REPO} form over repos[] {repos}: {len(landed)} PR-opening node(s) landed out "
        f"of {len(declared)} detected (declared approach_kind "
        f"{list(PR_OPENING_APPROACH_KINDS)} or evidenced by a pull-request URL in `produced`); "
        f"{len(pr_urls)} distinct PR URL(s) recorded; {repoless} node(s) carry `repo: null`"
    )
    return _result("one-pr", not violations, note, violations)


def check_nothing_substantive_after_pr(run: dict) -> dict:
    """2. No repo's PR-opening node landed while THAT repo's substantive work is unfinished.

    Scoped per repo: repo A's opened PR is judged against repo A's nodes only, so a legitimately
    unfinished repo B never shows up as a violation of A. A `repo: null` node is out of scope only
    when it is genuinely repo-less work - a repo-less node running a delivery-gating lifecycle
    stage is IN scope, because a stage that gates a repository's PR belongs to that repository.
    Without `repos[]` this falls back to the legacy whole-run scope.
    """
    nodes = all_nodes(run)
    repos = declared_repos(run)
    landed = [n for n in nodes if is_landed_pr(n)]
    tail = (f"approach_kind {list(LAND_TAIL_APPROACH_KINDS)} or approach "
            f"{list(LAND_TAIL_APPROACHES)}, matched exactly")

    def _unfinished(bucket: list[dict]) -> list[dict]:
        return [
            n for n in bucket
            if not is_land_tail(n) and node_status(n) not in SETTLED_NODE_STATUSES
        ]

    if not repos:
        unfinished = _unfinished(nodes)
        note = (
            f"{FORM_LEGACY} form (no repos[] declared): {len(landed)} PR-opening node(s) landed; "
            f"{len(unfinished)} substantive node(s) outside the land tail ({tail}) "
            f"not in {list(SETTLED_NODE_STATUSES)}"
        )
        if not landed or not unfinished:
            return _result("pr-last", True, note, [])
        opened_by = ", ".join(node_label(n) for n in landed)
        return _result("pr-last", False, note, [
            {"node": node_label(n),
             "detail": f"status {node_status(n) or '<unset>'} while PR-opening node(s) "
                       f"[{opened_by}] already landed"}
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
                       f"PR-opening node(s) [{opened_by}] already landed"}
            for n in _unfinished([n for n in nodes if node_repo(n) == repo])
        ]

    # `repo: null` is a carve-out for repo-less work, NOT a way for a delivery-gating stage to sit
    # outside every repo's readiness scope. Once ANY repo has landed, an unfinished repo-bound
    # node that named no repo is exactly the escape hatch this check exists to close.
    repoless_open = _unfinished([n for n in nodes if node_repo(n) is None])
    orphan_gating = [n for n in repoless_open if repo_binding_reasons(n)]
    if landed_repos:
        violations += [
            {"node": node_label(n),
             "detail": f"status {node_status(n) or '<unset>'} with `repo: null` while repo(s) "
                       f"{landed_repos} already landed their PR - this node is repo-bound work "
                       f"({'; '.join(repo_binding_reasons(n))}), so `repo: null` does not put it "
                       f"outside the readiness scope it gates"}
            for n in orphan_gating
        ]

    note = (
        f"{FORM_PER_REPO} form: repo(s) {landed_repos or []} have an opened PR; scope is that "
        f"repo's OWN nodes outside the land tail ({tail}), plus any unfinished repo-bound "
        f"`repo: null` node - other repos' nodes and the "
        f"{len(repoless_open) - len(orphan_gating)} unfinished genuinely repo-less node(s) are "
        f"out of scope"
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
    """Audit a run file whose shape is already known-readable (`schema_problems()` came back empty)."""
    results = [check(run) for _cid, _title, check in CHECKS]
    ok = all(r["ok"] for r in results)
    return {
        "run_file": str(run_file),
        "run_id": run.get("run_id"),
        "run_status": run.get("status"),
        "form": audit_form(run),
        "repos": declared_repos(run),
        "verdict": VERDICT_CLEAN if ok else VERDICT_VIOLATION,
        "ok": ok,
        "schema_problems": [],
        "checks": results,
        "gates": report_gates(run),
    }


def could_not_check(run: dict | None, run_file: Path, problems: list[str]) -> dict:
    return {
        "run_file": str(run_file),
        "run_id": (run or {}).get("run_id"),
        "run_status": (run or {}).get("status"),
        "form": None,
        "repos": [],
        "verdict": VERDICT_COULD_NOT_CHECK,
        "ok": False,
        "schema_problems": problems,
        "checks": [],
        "gates": None,
    }


def print_text_report(audit_result: dict) -> None:
    titles = {cid: title for cid, title, _check in CHECKS}
    print(f"audit-run: {audit_result['run_file']}")
    print(f"  run_id: {audit_result.get('run_id')}   status: {audit_result.get('run_status')}")

    if audit_result["verdict"] == VERDICT_COULD_NOT_CHECK:
        print("  [COULD-NOT-CHECK] this run file is not shaped like the documented run-state "
              "schema")
        for problem in audit_result["schema_problems"]:
            print(f"         -> {problem}")
        print("         no verdict is issued: an unreadable run file is never reported as clean")
        print(f"  RESULT: {VERDICT_COULD_NOT_CHECK.upper()}")
        return

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
        result = could_not_check(None, run_file, [str(exc)])
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print_text_report(result)
        print(f"audit-run: could-not-check: {exc}", file=sys.stderr)
        return EXIT_COULD_NOT_CHECK

    problems = schema_problems(run)
    if problems:
        result = could_not_check(run, run_file, problems)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print_text_report(result)
        print(f"audit-run: could-not-check: {len(problems)} schema problem(s) in {run_file}",
              file=sys.stderr)
        return EXIT_COULD_NOT_CHECK

    audit_result = audit(run, run_file)
    if args.json:
        print(json.dumps(audit_result, indent=2, sort_keys=True))
    else:
        print_text_report(audit_result)
    return EXIT_CLEAN if audit_result["ok"] else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
