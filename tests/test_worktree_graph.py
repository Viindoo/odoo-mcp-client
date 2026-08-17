"""Behavior guards for the worktree LINEAGE and the plan/runtime ownership split.

The plan is a FLAT DAG of work nodes with `depends_on`; nothing groups nodes. The worktree
lineage is therefore no longer a second projection authored INSIDE the plan (the retired
`Block 2W`) - it is a runtime invariant owned by the driver. What this file protects:

(a) `run-harness/SKILL.md` § Run start states ALL THREE lineage invariants, per NODE:
    ONE `run-integration` branch per repo forked ONCE; every source-writing node's worktree forks
    THAT branch; every returned commit cherry-picks back onto it as a saga, and that branch is
    what the terminal `integrate` node squashes.
(b) The PLAN carries no concrete ref STATE - no SHA, no branch tip, no resolved worktree
    filesystem path, no lease token - and no symbolic worktree-graph edge either. Those are
    runtime-only facts the driver owns (`agents/odoo-planner.md` states this from its own side).
(c) The odoo-coder coordinator COMMITS its node via Skill(git-toolkit:git-ops) - request-only, no
    direct git leaf agent, no raw git (see also test_coder_coordinator_topology.py).
(d) The `approach_kind` enum has ONE value set, declared identically at every declaration site,
    and every count word referring to it agrees with the actual enumerated value count.

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
RUN_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "run-integration.md"
PLAN_MODE_SCHEMA = SCHEMA
WORKFLOW_HARNESS = PLUGIN / "docs" / "reference" / "workflow-harness.md"
AUDIT_RUN = ROOT / "scripts" / "audit-run.py"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _run_start_section() -> str:
    """The body of run-harness/SKILL.md's `## Run start` section, whitespace-normalized.

    Scoping to the SECTION (not the whole file) is deliberate and is what makes this guard
    red-before-green: before the grouping layer was removed, these three invariants lived inside
    the retired between-groups integration section, as a step of a nested driver loop that ran for
    ONE node kind and phrased every invariant over the group rather than the node. `## Run start`
    as a top-level section of the driver, stated per NODE, is the post-change shape.
    """
    text = _text(RUN_HARNESS)
    m = re.search(r"^##\s+Run start\s*$", text, re.MULTILINE)
    assert m, (
        "run-harness/SKILL.md must carry a top-level `## Run start` section - the ONE place the "
        "run-integration branch is created and the three lineage invariants are stated."
    )
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return _normalize_ws(rest[: nxt.start()] if nxt else rest)


# ---------------------------------------------------------------------------
# (a) The three lineage invariants live in run-harness § Run start, per NODE
# ---------------------------------------------------------------------------

def test_run_start_states_invariant_1_one_integration_branch_per_repo():
    """Invariant 1: ONE run-integration branch per repo, forked ONCE, never re-forked, and NO
    per-node/per-stage integration branch.

    Fails if: the fork-once statement is dropped, or the text re-admits a second integration
    branch below the repo (a per-node/per-level/per-stage branch), which is what would let two
    nodes integrate against different parents and silently lose a commit.
    """
    sec = _run_start_section()
    assert re.search(r"(?i)ONE run-integration branch per repo, forked ONCE", sec), (
        "§ Run start must state ONE run-integration branch per repo, forked ONCE."
    )
    assert re.search(r"(?i)no per-node[^.]{0,80}integration branch", sec), (
        "§ Run start must REJECT a per-node (or per-level/per-stage) integration branch - the "
        "lineage is one branch per repo, not one per unit of work."
    )
    assert re.search(r"(?i)never re-forked", sec), (
        "§ Run start must state the branch is never re-forked mid-run."
    )


def test_run_start_states_invariant_2_every_node_worktree_forks_that_branch():
    """Invariant 2: every SOURCE-WRITING NODE's worktree forks that repo's run-integration branch -
    never `base`/principal, never another repo's.

    Fails if: the fork parent is dropped or inverted to base/principal (which would make a node
    blind to its dependencies' committed source), or if the unit reverts from the NODE to a
    grouping/module unit.
    """
    sec = _run_start_section()
    assert re.search(r"(?i)every source-writing node'?s worktree forks", sec), (
        "§ Run start must state EVERY SOURCE-WRITING NODE's worktree forks that branch - the "
        "unit is the node, not a module or any grouping of nodes."
    )
    assert re.search(r"(?i)never\s+`?base`?/principal", sec), (
        "§ Run start must state a node's worktree is NEVER forked from base/principal - forking "
        "from base is exactly the inversion that loses every prior node's commit."
    )
    assert re.search(r"(?i)never another repo'?s", sec), (
        "§ Run start must state a node's worktree is never forked from ANOTHER repo's branch."
    )


def test_run_start_states_invariant_3_every_commit_cherry_picks_back_as_a_saga():
    """Invariant 3: every commit a node returns cherry-picks back onto that same branch, as a
    saga with per-node verify + checkpoint, and THAT branch is what the terminal `integrate` node
    squashes and pushes.

    Fails if: the cherry-pick-back edge, the saga/checkpoint mechanism, or the
    'this branch is what ships' closure is dropped - each of which lets a commit exist without
    ever reaching the PR.
    """
    sec = _run_start_section()
    assert re.search(r"(?i)every commit a node returns cherry-picks back", sec), (
        "§ Run start must state every commit a node returns cherry-picks back onto that branch."
    )
    assert re.search(r"(?i)saga", sec) and re.search(r"(?i)checkpoint", sec), (
        "§ Run start must state the cherry-pick runs as a SAGA with a per-node verify + CHECKPOINT "
        "(rollback contract: skills/_shared/integration-loop.md)."
    )
    assert re.search(r"(?i)terminal\s+`?integrate`?\s+node\s+squashes", sec), (
        "§ Run start must close the lineage: the repo's terminal `integrate` node squashes and "
        "pushes THAT branch."
    )
    assert re.search(r"(?i)never reaches it never ships", sec), (
        "§ Run start must state the consequence - a commit that never reaches the integration "
        "branch never ships - so the invariant reads as a safety property, not bookkeeping."
    )


# ---------------------------------------------------------------------------
# (b) The plan carries no concrete ref STATE, and no worktree-graph edge
# ---------------------------------------------------------------------------

# A hex literal of commit-SHA shape. Requires at least one DIGIT so ordinary all-[a-f] English
# words ("defaced", "affected") are not mistaken for a SHA.
_SHA_LITERAL_RE = re.compile(r"(?<![\w/-])(?=[0-9a-f]{7,40}(?![\w-]))(?=[0-9a-f]*\d)[0-9a-f]{7,40}")
# A RESOLVED absolute filesystem path. `${CLAUDE_PLUGIN_ROOT}/...` and `<SHARE_DIR>/...` are
# SYMBOLIC and stay legal - only a machine-rooted path is ref state.
_ABS_PATH_RE = re.compile(r"(?<![\w$}>`])/(?:home|Users|var|opt|srv|etc|tmp|mnt)/")
# The retired Block-2W edge shape: a symbolic worktree node in the PLAN.
_WORKTREE_GRAPH_EDGE_RE = re.compile(r"worktree\s*\([^)]*\)|==>\s*run-integration")
_LEASE_TOKEN_RE = re.compile(r"(?i)lease\s*token")
_BRANCH_TIP_RE = re.compile(r"(?i)branch\s+tip|tip\s+SHA")


def test_plan_schema_carries_no_concrete_ref_state():
    """The plan is authored ONCE at approval time; a worktree path, a SHA, a branch tip and a
    lease token do not exist yet and are runtime-only facts the driver owns. The schema must
    therefore contain none of them - and no symbolic worktree-graph edge either (the retired
    `worktree(m)@... ==> run-integration` projection, whose only purpose was to let the plan
    describe a lineage the driver already owns).

    Fails if: any of those leak back into `plan-mode-schema.md` - the shape that made the plan
    an executor-shaped artifact instead of a decision record.
    """
    text = _text(PLAN_MODE_SCHEMA)
    norm = _normalize_ws(text)
    offenders = []
    for label, pattern in (
        ("SHA-shaped literal", _SHA_LITERAL_RE),
        ("resolved absolute filesystem path", _ABS_PATH_RE),
        ("worktree-graph node/edge", _WORKTREE_GRAPH_EDGE_RE),
        ("lease token", _LEASE_TOKEN_RE),
        ("branch tip", _BRANCH_TIP_RE),
    ):
        m = pattern.search(norm)
        if m:
            offenders.append(f"{label}: {m.group(0)!r}")
    assert not offenders, (
        "plan-mode-schema.md carries concrete ref STATE / an executor-shaped worktree graph - "
        "these are runtime-only facts owned by run-harness (§ Run start), never plan fields:\n"
        + "\n".join(offenders)
    )


def test_planner_states_the_plan_carries_no_ref_state():
    """The producer side of the same contract: `odoo-planner` must be told the plan carries NO
    worktree topology and NO concrete ref STATE, naming all four runtime-only classes.

    Fails if: the planner's plan-ref line is relaxed to let a worktree topology or any concrete
    ref back into the plan (the relaxation the retired Block 2W required).
    """
    norm = _normalize_ws(_text(PLANNER))
    assert re.search(r"(?i)NO worktree topology", norm), (
        "odoo-planner must state the plan carries NO worktree topology - not even a symbolic one."
    )
    assert re.search(r"(?i)NO concrete ref STATE", norm), (
        "odoo-planner must still forbid concrete ref STATE in the plan."
    )
    for cls in (r"no SHAs", r"no branch tips", r"no resolved worktree filesystem paths",
                r"no lease tokens"):
        assert re.search(rf"(?i){cls}", norm), (
            f"odoo-planner must name '{cls}' among the runtime-only facts the plan must not carry "
            "- an unenumerated ban is the one a future author reads as 'only SHAs'."
        )


# ---------------------------------------------------------------------------
# (c) coder commits via Skill(git-toolkit:git-ops) - request-only
# ---------------------------------------------------------------------------

def test_coder_commits_via_skill_git_ops_request_only():
    text = _text(CODER)
    low = text.lower()
    assert "git-toolkit:git-ops" in text and "commit" in low, (
        "odoo-coder must COMMIT its node by invoking git-toolkit:git-ops"
    )
    # Request-only: no raw git, no direct git leaf-agent dispatch.
    assert "raw git" in low, "odoo-coder must state it never runs raw git (invokes git-ops instead)"
    assert ("not dispatch" in low or "must not dispatch" in low) and "git leaf" in low, (
        "odoo-coder must state it does NOT dispatch a git leaf agent directly (generic wording - "
        "no leaf-agent name required, per the git-toolkit agent-name zero-mention policy)"
    )
    # It returns the SHA up to odoo-coding.
    assert "sha" in low and "odoo-coding" in text, (
        "odoo-coder must return the commit SHA to odoo-coding"
    )


# ---------------------------------------------------------------------------
# integration-loop.md: ONE owner of the integration loop
# ---------------------------------------------------------------------------

def test_integration_loop_names_run_harness_as_the_sole_owner():
    """`run-harness` is the canonical PER-NODE integration consumer and the SOLE owner - there is
    no separate git-executor skill running a second, nested integration loop.

    Fails if: the sole-ownership statement is dropped, or a second git-executor owner bullet
    reappears in the owner list (which is how a nested per-unit integration loop grows back).
    """
    text = _text(INTEGRATION_LOOP)
    norm = _normalize_ws(text)
    assert re.search(r"(?i)canonical per-node integration consumer", norm), (
        "integration-loop.md must name run-harness as the canonical PER-NODE integration consumer "
        "- the unit is the node, not a batch of them."
    )
    assert re.search(r"(?i)SOLE owner", norm), (
        "integration-loop.md must state run-harness is the SOLE owner of the integration loop "
        "(no separate git-executor skill)."
    )
    assert re.search(r"(?im)^-\s*`?[a-z0-9-]*git-executor", text) is None, (
        "integration-loop.md must not list a separate git-executor as an owner bullet - a second "
        "owner is a second, nested integration loop."
    )
    assert re.search(r"(?i)ordinary PLAN nodes", norm), (
        "integration-loop.md must state review and regression verification are ordinary PLAN "
        "nodes, not a driver-owned close step - the driver keeps no cadence of its own."
    )


# ---------------------------------------------------------------------------
# Ledger scope note: intra-run backstopped by a POLICY step (SELF_PROVISION:
# worktree-addons), NOT a structural guarantee of the git-fork lineage alone.
#
# Was: test_ledger_notes_intra_run_structurally_solved, which REQUIRED the
# literal phrase "structurally solved" - i.e. it enforced the presence of the
# very conflation this fix removes (a worktree CONTAINING a dependency's
# source is not the same as that source being on the addons-path). Inverted
# below: the ledger must state the corrected POLICY framing and must NOT
# regress to the structurally-solved/impossible claim.
# ---------------------------------------------------------------------------

def test_ledger_notes_intra_run_backstopped_by_policy_not_structure():
    text = _text(LEDGER)
    norm = _normalize_ws(text)
    low = norm.lower()
    assert re.search(
        r"(?i)forks? from the ONE `?run-integration`? branch[^.]{0,80}"
        r"run-harness/SKILL\.md.{0,20}Run start", norm
    ), (
        "the ledger must cite the lineage's ONE owner (run-harness/SKILL.md § Run start) for the "
        "fork-from-the-one-run-integration-branch fact, rather than restating it or pointing at a "
        "plan-side projection."
    )
    assert "contains" in low and "addons-path" in low, (
        "the ledger must distinguish the worktree CONTAINING the dependency's source from that "
        "source being on the addons-path"
    )
    assert re.search(r"(?i)POLICY step", norm), (
        "the ledger must frame reaching the addons-path as a POLICY step (SELF_PROVISION: "
        "worktree-addons, set by odoo-coding), never a structural guarantee of the fork itself"
    )
    assert "structurally solved" not in low and "structurally impossible" not in low, (
        "the ledger must NOT claim the addons-path guarantee is 'structurally solved/impossible' - "
        "see test_no_file_anywhere_claims_worktree_structurally_solves_addons_path for the "
        "whole-plugin version of this guard"
    )
    assert "cross-run" in low, (
        "the ledger must state it now backstops ONLY concurrent independent (cross-run) coordination"
    )


# ---------------------------------------------------------------------------
# The node invocation brief: state-root placeholders must be RESOLVED
#
# Every literal-absence assertion below normalizes whitespace first
# (the prose is hard-wrapped, so a literal spanning a line-wrap would
# otherwise false-negative).
# ---------------------------------------------------------------------------

def _node_invocation_brief_fence() -> str:
    """The fenced ``` ... ``` block under '## Node Invocation Brief Template'."""
    text = _text(RUN_INTEGRATION)
    marker = "## Node Invocation Brief Template"
    start = text.find(marker)
    assert start != -1, (
        "run-integration.md must carry '## Node Invocation Brief Template' - the brief the driver "
        "composes PER NODE (never per module)"
    )
    fence_start = text.find("```", start)
    assert fence_start != -1, "the brief template must be a fenced block"
    fence_end = text.find("```", fence_start + 3)
    assert fence_end != -1, "the brief template fence must close"
    return text[fence_start: fence_end + 3]


def test_node_brief_has_no_unresolved_state_root_placeholder():
    """A (absence): inside the brief fence, no line may contain the literal
    `<SHARE_DIR>` or `<ISOLATE_DIR>` UNLESS that line is the `SHARE_DIR:` /
    `ISOLATE_DIR:` field itself (a resolved-path placeholder is fine there;
    an unresolved one leaking into another field, e.g. design_index, is not)."""
    fence = _node_invocation_brief_fence()
    for line in fence.splitlines():
        stripped = line.strip()
        if stripped.startswith("SHARE_DIR") or stripped.startswith("ISOLATE_DIR"):
            continue
        norm = _normalize_ws(line)
        assert "<SHARE_DIR>" not in norm and "<ISOLATE_DIR>" not in norm, (
            f"unresolved state-root placeholder leaked into a non-field brief line: {line!r}"
        )


def test_node_brief_carries_share_and_isolate_fields():
    """A (presence-of-field): the node brief fence declares both
    SHARE_DIR and ISOLATE_DIR as captured-literal fields."""
    fence = _node_invocation_brief_fence()
    assert re.search(r"^SHARE_DIR\s*:", fence, re.MULTILINE), (
        "the node brief fence must carry a SHARE_DIR field"
    )
    assert re.search(r"^ISOLATE_DIR\s*:", fence, re.MULTILINE), (
        "the node brief fence must carry an ISOLATE_DIR field"
    )


_ADDONS_STRUCTURAL_CLAIM_PATTERNS = [
    re.compile(r"already\s+carr\w*\s+the\s+dependenc\w*\s+on\s+its\s+addons-path", re.IGNORECASE),
    re.compile(r"structurally\s+solved", re.IGNORECASE),
    re.compile(r"structurally\s+impossible", re.IGNORECASE),
    re.compile(r"structurally\s+remov\w*\s+the[^.]*blocked", re.IGNORECASE),
    re.compile(r"\b(?:is|are)\s+on\s+the\s+addons-path\s+by\s+construction", re.IGNORECASE),
]


def test_no_file_anywhere_claims_worktree_structurally_solves_addons_path():
    """CLASS guard (widened from a single literal phrase scoped to ONE file).

    BEFORE: `"already carries the dependency on its addons-path" not in
    <one file's text alone>` - one file, one exact phrase.

    AFTER: the same conflation - "a worktree CONTAINS the dependency's source
    (true, by git-fork lineage)" presented as "therefore that source is on the
    verification instance's addons-path" (false by default: the allocator
    emits the CATALOG list, rooted at the principal checkout, until
    `SELF_PROVISION: worktree-addons` re-roots it) - is a CLASS of claim with
    several phrasings ("structurally solved", "structurally impossible",
    "structurally removes the ... BLOCKED path", "on the addons-path BY
    CONSTRUCTION"). It survived, unfixed, in THREE files the single-file/
    single-phrase check could not see: snippets/module-coordination-ledger.md
    (x2), skills/run-harness/SKILL.md, and
    skills/odoo-intake/references/plan-mode-schema.md. Scan the WHOLE plugin
    tree (`_tree_texts()`, the same helper the enum-count guards below use)
    for the whole pattern family, not one file for one sentence.
    """
    offenders = []
    for path, text in _tree_texts():
        norm = _normalize_ws(text)
        for pattern in _ADDONS_STRUCTURAL_CLAIM_PATTERNS:
            if pattern.search(norm):
                offenders.append(f"{_rel(path)}: matched {pattern.pattern!r}")
    assert not offenders, (
        "the following files conflate 'worktree contains the dependency's source' with 'source is "
        "on the addons-path' - see snippets/instance-handle-contract.md § Worktree-addons "
        "carve-out:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# The `approach_kind` enum: ONE value set, declared identically everywhere.
#
# (Retargeted from the retired `topology` enum, which was a property of the
# grouping layer and died with it. The BEHAVIOUR the topology guards protected - "an enum has
# one value set and every restatement, including every count WORD, agrees with
# it" - is unchanged; only the enum it applies to moved. `approach_kind` is
# the surviving enum: five values, three declaration sites, one of them
# executable (scripts/audit-run.py), so a partial update is a real defect that
# makes the auditor disagree with the schema it audits against.)
# ---------------------------------------------------------------------------

def _tree_texts():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py), PLUS the repo-root
    `scripts/` executables, which carry an EXECUTABLE copy of the schema vocabulary.

    Same pattern as test_planning_ssot.py:34-39 - reused here rather than
    imported so this file stays independently runnable (repo convention: no
    cross-test-module imports).
    """
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for root in (PLUGIN, ROOT / "scripts"):
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in exts:
                yield p, p.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PLUGIN))
    except ValueError:
        return str(path.relative_to(ROOT))


# The canonical declaration sentence: `approach_kind` is one of `a | b | c` - <count> values.
_ENUM_SENTENCE_RE = re.compile(
    r"`approach_kind`\s+is\s+one\s+of\s+`([^`]+)`"
)
# The executable declaration in scripts/audit-run.py.
_AUDIT_ENUM_RE = re.compile(r"APPROACH_KINDS\s*=\s*\(([^)]*)\)")

_EXPECTED_APPROACH_KINDS = {"skill", "agent", "workflow", "inline", "integrate"}


def _declared_kinds_in(text: str) -> set[str] | None:
    """The `approach_kind` value SET a file declares, or None when it declares none."""
    m = _ENUM_SENTENCE_RE.search(text)
    if m:
        return {v.strip().strip("`") for v in m.group(1).split("|") if v.strip()}
    m = _AUDIT_ENUM_RE.search(text)
    if m:
        return {v.strip().strip("\"'") for v in m.group(1).split(",") if v.strip()}
    return None


def test_approach_kind_enum_declaration_sites_agree():
    """A (one value set): every file that DECLARES the `approach_kind` value set must declare the
    SAME set, and that set must be the five documented kinds. A sixth value added at one site
    only - or a retired value left behind at one site - reddens here.

    This is the assertion with teeth: the auditor (`scripts/audit-run.py`) refuses to audit a kind
    outside its own tuple, so a schema that grew a kind the auditor never learned about silently
    stops being audited.
    """
    declarations = {}
    for path, text in _tree_texts():
        kinds = _declared_kinds_in(text)
        if kinds:
            declarations[_rel(path)] = kinds
    assert declarations, (
        "no file declares the `approach_kind` value set - the enum must have a declaration site"
    )
    disagreeing = {k: sorted(v) for k, v in declarations.items()
                   if v != _EXPECTED_APPROACH_KINDS}
    assert not disagreeing, (
        f"every `approach_kind` declaration must be exactly {sorted(_EXPECTED_APPROACH_KINDS)}; "
        f"these disagree: {disagreeing}"
    )
    # The executable half must be one of them - a prose-only enum cannot keep the auditor honest.
    assert str(AUDIT_RUN.relative_to(ROOT)) in declarations, (
        "scripts/audit-run.py must declare the `approach_kind` enum (APPROACH_KINDS) so the "
        "auditor and the schema cannot drift apart"
    )


def _approach_kind_value_count() -> int:
    """N = the number of values in the canonical enumeration, computed from the text itself -
    never hardcoded - so this stays correct when a sixth value is added."""
    kinds = _declared_kinds_in(_text(WORKFLOW_HARNESS))
    assert kinds, (
        "workflow-harness.md § 8.3 must carry the canonical `approach_kind` declaration sentence "
        "this count is computed from"
    )
    return len(kinds)


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUMBER_WORD_ALTERNATION = "|".join(_NUMBER_WORDS)
_COUNT_RE = re.compile(
    rf"\b(\d{{1,2}}|{_NUMBER_WORD_ALTERNATION})\b((?:\s+[A-Za-z][A-Za-z-]*){{0,3}})\s+"
    r"(?:values?|kinds?)\b",
    re.IGNORECASE,
)
_ENUM_MENTION_RE = re.compile(r"(?i)approach[_ -]kind")
_MENTION_WINDOW = 160  # chars either side of the count word that must mention the enum


def _count_word_violations(text: str, n: int) -> list[str]:
    """Every count-word reference to the `approach_kind` value set must numerically agree with
    `n` (the ACTUAL enumerated value count).

    A count word is attributed to this enum only when `approach_kind` is mentioned within
    `_MENTION_WINDOW` chars of it - otherwise "three coordination surfaces" and every other
    unrelated count in the tree would be swept in. The count token accepts a bare digit (`5`) as
    well as a spelled-out word, and tolerates up to 3 filler words between the count and
    `values`/`kinds` ("five serialized values"), because a stale count survives a rewording.
    Returns violation messages (empty = no violations)."""
    norm = _normalize_ws(text)
    violations = []
    for m in _COUNT_RE.finditer(norm):
        window = norm[max(0, m.start() - _MENTION_WINDOW): m.end() + _MENTION_WINDOW]
        if not _ENUM_MENTION_RE.search(window):
            continue
        word = m.group(1).lower()
        value = int(word) if word.isdigit() else _NUMBER_WORDS[word]
        if value != n:
            violations.append(
                f"count token {word!r} disagrees with the enumerated value count N={n}: "
                f"matched {m.group(0)!r}"
            )
    return violations


def test_every_file_stating_an_approach_kind_count_agrees_with_the_declaration():
    """CLASS guard, whole tree: a stale "the four approach kinds" sentence sitting next to a
    five-value enumeration is a defect - a reader cannot tell whether it is stale prose or a
    deliberate exclusion, and if excluded, which value. This computes N from the canonical
    declaration and asserts every count-word reference to the enum, in EVERY file of the plugin
    plus the repo-root scripts, agrees with N.

    Adding a sixth value and forgetting to update one of these count words reddens this test
    instead of leaving a silent ambiguity for the next reader to puzzle out.
    """
    n = _approach_kind_value_count()
    offenders = []
    for path, text in _tree_texts():
        violations = _count_word_violations(text, n)
        if violations:
            offenders.append(f"{_rel(path)}: " + "; ".join(violations))
    assert not offenders, (
        "the following files state an `approach_kind` count that disagrees with the enumerated "
        f"value count N={n} (canonical declaration: docs/reference/workflow-harness.md § 8.3):\n"
        + "\n".join(offenders)
    )
