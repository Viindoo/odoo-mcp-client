"""Behavioral guards for run-harness's gate contract.

Two safety couplings, restated for the flat-DAG model:

- R1 (advance <-> regression-proof coupling): the driver may auto-advance and drive to done ONLY
  because a GREEN regression proof stands between the code and the PR. That proof is no longer a
  driver-owned "close gate" fired on a cadence - it is an ORDINARY PLAN NODE (`approach:
  odoo-instance`), and the coupling now lives in the driver's `integrate` READINESS PREDICATE:
  the PR does not open unless a DONE verification node on the dependency path covered every
  module the repo's coding nodes touched. `test_run_harness_never_opens_a_pr_on_red` below is
  that guard, and it explicitly REJECTS a re-added driver-owned close-gate: re-introducing one
  would restore the very cadence-bearing layer this model removed.

- R2 (SSOT <-> code drift): docs/reference/workflow-harness.md §8.4 is a HAND-AUTHORED SSOT. It
  states (a) the registry `_derive_gate_tier` derivation and (b) that the per-NODE tier is a
  TOTAL FUNCTION over every `approach_kind` with no node-kind carve-out, while the downstream
  outward MERGE stays human-gated (L2). These tests assert the doc and the code agree, so a
  future editor cannot re-introduce a node-kind spawn class or a node-kind tier exception
  without a red test.

Each assertion fails for exactly one reason. Run:
  python3 -m pytest tests/test_run_harness_gate.py -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"
RUN_HARNESS_DIR = PLUGIN / "skills" / "run-harness"
HARNESS_DOC = PLUGIN / "docs" / "reference" / "workflow-harness.md"
PLAN_MODE_SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import _derive_gate_tier, VALID_SPAWN_CLASS  # noqa: E402


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading: str) -> str:
    """The body of a `## <heading>` section, whitespace-normalized."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    assert m, f"run-harness/SKILL.md must carry a `## {heading}` section"
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return _norm(rest[: nxt.start()] if nxt else rest)


# ---------------------------------------------------------------------------
# R1 - never open a PR on red, enforced at the driver
# ---------------------------------------------------------------------------

# The retired shape: a driver-owned regression gate fired on the driver's own cadence.
_CLOSE_GATE_RE = re.compile(r"(?i)close[\s-]?gate")


def test_run_harness_owns_no_regression_close_gate_of_its_own():
    """The driver keeps NO verification cadence of its own. Regression verification is an
    ORDINARY PLAN NODE the planner positions; the driver only refuses to open the PR without a
    green one (see the readiness predicate below).

    Fails if: a driver-owned "close-gate" is re-added to run-harness - which would give the
    driver back a cadence, i.e. re-grow the grouping layer this model removed. Deliberately
    INVERTED relative to the guard it replaces (which REQUIRED that clause): the anchor for the
    autonomous advance moved from a driver cadence to the `integrate` readiness predicate, so
    requiring the old clause would now enforce the defect.
    """
    offenders = []
    for path in sorted(RUN_HARNESS_DIR.rglob("*.md")):
        for m in _CLOSE_GATE_RE.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(PLUGIN)}: {m.group(0)!r}")
    assert not offenders, (
        "run-harness must own no regression close-gate - verification is a PLAN node "
        "(`approach: odoo-instance`) the planner places, and the driver's only say is the "
        "`integrate` readiness predicate. Offenders:\n" + "\n".join(offenders)
    )


def test_run_harness_never_opens_a_pr_on_red():
    """R1: the `integrate` readiness predicate is what keeps a PR off a red tree.

    All four clauses must be stated: (a) clause (i) evaluated over the LIVE node set including
    dynamic nodes; (b) clause (ii) requiring a DONE `approach: odoo-instance` node on the
    transitive dependency path whose modules cover every module R's coding nodes named;
    (c) SKIPPED never satisfies clause (ii); (d) a narrower plan `depends_on` is an ADVISORY
    finding, never a BLOCK.

    Fails if: any clause is dropped, if clause (ii) is softened to "DONE or SKIPPED" (a skipped
    verification is an ABSENT verification), or if readiness is re-phrased as an EQUALITY against
    the plan's `depends_on` (which either blocks the run on a dynamic node the driver itself
    created, or excludes it and lets unverified source land).
    """
    sec = _section(RUN_HARNESS.read_text(encoding="utf-8"), "integrate readiness")

    # (a) clause (i) over the LIVE node set, dynamic nodes included.
    assert re.search(r"(?i)\(i\)[^.]{0,200}NOT in the land-tail set", sec), (
        "clause (i) must scope over every node of repo R that is NOT in the land-tail set."
    )
    assert re.search(r"(?i)Dynamic nodes materialized at runtime COUNT", sec), (
        "clause (i) must be evaluated over the LIVE node set - dynamic nodes COUNT, never only "
        "what the plan happened to name."
    )

    # (b) clause (ii): a DONE odoo-instance node covering every module R's coding nodes touched.
    clause_ii = re.search(
        r"(?i)\*\*\(ii\)\*\*(.{0,600}?)(?:\*\*`?SKIPPED|\Z)", sec, re.DOTALL
    )
    assert clause_ii, "the readiness predicate must carry an explicit clause (ii)"
    body_ii = clause_ii.group(1)
    assert re.search(r"(?i)approach:\s*odoo-instance", body_ii), (
        "clause (ii) must require a node whose `approach` is `odoo-instance` - the node kind that "
        "actually runs the suites."
    )
    assert re.search(r"(?i)transitive dependency path", body_ii), (
        "clause (ii) must require that node to sit on `integrate@R`'s TRANSITIVE dependency path "
        "- a green run somewhere else in the DAG proves nothing about this PR's tree."
    )
    assert re.search(r"(?i)\bDONE\b", body_ii), "clause (ii) must require that node to be DONE."
    # Emphasis-blind: the offending phrasing is written `**DONE** or SKIPPED` in real markdown, so
    # a literal `DONE or SKIPPED` search silently passes over it. Strip emphasis first, and accept
    # either operand order.
    plain_ii = re.sub(r"[*`_]", "", body_ii)
    assert not re.search(
        r"(?i)\b(DONE\b[^.]{0,20}\bor\b[^.]{0,20}\bSKIPPED|SKIPPED\b[^.]{0,20}\bor\b[^.]{0,20}\bDONE)\b",
        plain_ii), (
        "clause (ii) must NOT accept 'DONE or SKIPPED' - a skipped verification is an ABSENT "
        "verification, and accepting it opens the PR on an unverified tree. (Clause (i) may say "
        "'DONE or SKIPPED'; clause (ii) may not.)"
    )
    assert re.search(r"(?i)covers every module named", body_ii), (
        "clause (ii) must require the union of modules that node RAN to cover every module named "
        "by R's coding nodes, dynamic coding nodes included."
    )

    # (c) SKIPPED never satisfies clause (ii), and the failure is a BLOCK, not a shrug.
    assert re.search(r"(?i)`?SKIPPED`?\s+never satisfies clause \(ii\)", sec), (
        "the section must state in its own sentence that SKIPPED never satisfies clause (ii)."
    )
    assert re.search(r"(?i)STOP BLOCKED[^.]{0,200}unverified tree", sec), (
        "an unsatisfied clause (ii) must STOP the run BLOCKED naming the unverified tree - never "
        "proceed with an advisory."
    )

    # (d) a narrower plan depends_on is ADVISORY, never a BLOCK, and never an equality.
    assert re.search(r"(?i)`?integrate\.depends_on`?\s+is a FLOOR, not the rule", sec), (
        "the plan's `integrate.depends_on` must be declared a FLOOR, not the rule."
    )
    assert re.search(r"(?i)ADVISORY finding", sec) and re.search(
        r"(?i)Never STOP BLOCKED on a narrower `?depends_on`?", sec), (
        "a narrower plan `depends_on` must be an ADVISORY finding, never a BLOCK."
    )
    assert not re.search(r"(?i)depends_on`?\s*==", sec), (
        "readiness must be a PREDICATE, never an EQUALITY against the plan's `depends_on` - an "
        "equality either blocks on a driver-created dynamic node or excludes it."
    )


def test_plan_schema_requires_a_verification_node_per_repo():
    """The producer side of the same safety property: a plan that never runs the suites must be
    impossible to write, not merely caught at the land tail.

    Fails if: the schema stops requiring at least one `odoo-instance` node per repo on
    `integrate`'s dependency path covering every module that repo's coding nodes touch.
    """
    norm = _norm(PLAN_MODE_SCHEMA.read_text(encoding="utf-8"))
    assert re.search(r"(?i)Never open a PR on a red suite", norm), (
        "plan-mode-schema.md must state the rule the verification node exists to serve."
    )
    assert re.search(
        r"(?i)at least ONE node whose `?approach`? is `?odoo-instance`?", norm), (
        "plan-mode-schema.md must require EVERY repo to carry at least one `odoo-instance` node."
    )
    assert re.search(r"(?i)on `?integrate@R`?'?s? dependency path", norm), (
        "that node must be required to sit on `integrate@R`'s dependency path."
    )
    assert re.search(r"(?i)cover every module named by any coding node in that repo", norm), (
        "its `modules` must be required to cover every module named by that repo's coding nodes."
    )


# ---------------------------------------------------------------------------
# R2 - no node-kind spawn class, no node-kind tier carve-out
# ---------------------------------------------------------------------------


def _section_84(text: str) -> str:
    """Return the body of the '### 8.4 Gate-tier policy' section (up to the next '### ')."""
    start = re.search(r"^###\s+8\.4\b.*$", text, re.MULTILINE)
    assert start, "workflow-harness.md: '### 8.4' Gate-tier policy section not found"
    rest = text[start.end():]
    nxt = re.search(r"^###\s+", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_spawner_wave_class_is_gone():
    """R2: the `spawner-wave` spawn_class was removed when the per-wave git-executor was folded into run-harness.

    Fails if: `spawner-wave` re-appears as a valid spawn class, or `_derive_gate_tier` regains a
    class-based branch that would need it.
    """
    assert "spawner-wave" not in VALID_SPAWN_CLASS, (
        "spawner-wave must no longer be a valid spawn_class - it is no longer a registered spawn class."
    )


def test_derive_gate_tier_has_no_wave_branch():
    """R2: _derive_gate_tier derives from (instance_touching, output_mode, outward) ONLY.

    A writes-files, non-instance, non-outward skill is L1; add instance_touching and it becomes L2.
    There is no wave/spawner-wave short-circuit that would keep an instance-touching skill at L1.
    """
    assert _derive_gate_tier("spawner-agent", False, "writes-files", False) == "L1"
    assert _derive_gate_tier("spawner-agent", True, "writes-files", False) == "L2"
    assert _derive_gate_tier("orchestrator-nl", False, "chat-only", False) == "L0"
    assert _derive_gate_tier("spawner-agent", False, "writes-files", True) == "L2"


def test_harness_doc_states_the_node_tier_is_a_total_function_with_no_carve_out():
    """R2: workflow-harness.md §8.4 must state the per-NODE tier is a TOTAL FUNCTION over every
    `approach_kind`, resolved once at dispatch, with NO per-node-kind carve-out and NO
    hand-authorable field - and must keep the human-gated outward MERGE coupling.

    The guard this replaces required §8.4 to state that one particular node kind advances at L1.
    That node-kind carve-out is exactly what the total function removed, so requiring it would now
    enforce the defect; the surviving behaviour - "no node kind gets its own tier rule, and the
    outward merge is still L2" - is asserted instead.

    Fails if: the SSOT doc re-introduces a node-kind derivation branch (spawn class or tier
    exception), drops the total-function statement, or lets a tier be hand-authored in the run file.
    """
    text = HARNESS_DOC.read_text(encoding="utf-8")
    sec = _norm(_section_84(text))
    assert "spawner-wave" not in sec, (
        "workflow-harness.md §8.4 must not re-introduce a `spawner-wave` derivation branch."
    )
    assert re.search(r"(?i)no\s+node-kind-specific case and no per-node-kind carve-out", sec), (
        "§8.4 must state `_derive_gate_tier` has NO node-kind-specific case and no per-node-kind "
        "carve-out - a node kind must never buy itself a tier."
    )
    assert re.search(r"(?i)per-NODE tier[^.]{0,120}TOTAL FUNCTION over every `?approach_kind`?", sec), (
        "§8.4 must state the per-NODE tier is a TOTAL FUNCTION over every `approach_kind`."
    )
    assert re.search(r"(?i)not a field a node or a human can hand-author", sec), (
        "§8.4 must state the tier is not a hand-authorable field in `run-<id>.json` - the "
        "hand-edit is the threat model, never a feature."
    )
    # The downstream outward merge stays human-gated (L2) - the doc must keep that coupling.
    assert re.search(r"(?i)MERGE to the[\s\S]{0,40}principal branch", sec) and "L2" in sec, (
        "workflow-harness.md §8.4 must keep the human-gated outward MERGE coupling (L2)."
    )
    assert re.search(r"(?i)autonomy\s+dial\s+can\s+never\s+lower\s+L2", sec), (
        "§8.4 must state the autonomy dial can NEVER lower L2."
    )


def test_run_harness_body_states_the_only_l2_is_the_outward_merge():
    """R2 (companion): run-harness/SKILL.md itself must state that it drives to done and that the
    ONLY coding-run L2 is the downstream outward MERGE, owned by `odoo-pr-monitoring`, with EVERY
    node's tier - `integrate` included - coming from the ONE total function rather than a prose
    exception. Hard rule 5 sharpened the merge clause to "the ONLY OUTWARD L2" and added a
    companion clause: the merge is not the only L2 a run hits at all - the REGISTRY also returns
    L2 for an instance-touching skill (`odoo-i18n`, `odoo-acceptance`). Both clauses are asserted
    together so neither can regress alone.

    The guard this replaces asserted the same coupling for one node kind ("the between-X advance
    is L1, the merge is L2"). The node kind is gone; the coupling is not, and is now stated as a
    general rule - which is strictly stronger, because a prose tier exception ANYWHERE is now a
    failure rather than an accepted special case.

    Fails if: a second OUTWARD L2 appears in a coding run, the merge stops being human-gated, the
    registry-L2 companion clause for an instance-touching skill goes missing, or a prose tier
    exception is re-added next to the function.
    """
    body = RUN_HARNESS.read_text(encoding="utf-8")
    norm = _norm(body)
    low = norm.lower()
    assert re.search(r"(?i)The merge is the ONLY OUTWARD L2", norm), (
        "run-harness must state the merge is the ONLY OUTWARD L2."
    )
    assert re.search(
        r"(?i)the REGISTRY also returns L2 for an? instance-touching skill", norm), (
        "run-harness must state the REGISTRY also returns L2 for an instance-touching skill - "
        "the outward merge is not the only L2 a run hits."
    )
    assert "odoo-pr-monitoring" in low, (
        "run-harness must name `odoo-pr-monitoring` as the owner of that outward merge gate."
    )
    assert re.search(
        r"(?i)EVERY node'?s tier, `?integrate`? included, comes from the ONE total function", norm), (
        "run-harness must state EVERY node's tier, `integrate` included, comes from the ONE total "
        "function - never from a prose exception, and never from a node-kind carve-out."
    )
    assert re.search(r"(?i)never from a prose exception", norm), (
        "run-harness must explicitly reject a prose tier exception, which is how a node-kind "
        "carve-out grows back."
    )
    assert re.search(r"(?i)no local merge into the principal", norm) and re.search(
        r"(?i)no auto-merge", norm), (
        "run-harness must state there is no local merge into the principal and no auto-merge."
    )
    assert re.search(r"(?i)Drive-to-done STOPS at \"PR opened\"", norm), (
        "run-harness must state drive-to-done STOPS at 'PR opened' - the autonomy has an end, and "
        "that end is the human merge gate."
    )


def test_i18n_registry_tier_stays_l2():
    """R2 (companion): a genuine instance-touching skill (odoo-i18n) must stay L2 - the removal of
    the node-kind short-circuit must not lower any real instance-touching skill."""
    reg = json.loads(
        (PLUGIN / "generator" / "skill_tool_deps.json").read_text(encoding="utf-8")
    )["orchestration"]

    i18n = reg["odoo-i18n"]
    i18n_expected = _derive_gate_tier(
        i18n["spawn_class"], bool(i18n.get("instance_touching")),
        i18n["output_mode"], bool(i18n.get("outward")),
    )
    assert i18n_expected == "L2", f"odoo-i18n must stay L2 via instance_touching, got {i18n_expected!r}"
    assert i18n["default_gate_tier"] == i18n_expected == "L2"

    # And there is no lingering spawner-wave entry in the registry (skip the `_doc` string key).
    assert all(
        v.get("spawn_class") != "spawner-wave"
        for k, v in reg.items()
        if not k.startswith("_") and isinstance(v, dict)
    ), "no orchestration entry may still declare spawn_class=spawner-wave"
