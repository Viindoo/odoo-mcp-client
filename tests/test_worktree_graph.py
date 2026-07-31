"""Behavior guards for the planned-worktree-graph refactor (decision R, CORE step).

Protects the CONTRACT (not a wording snapshot) of the worktree dependency graph:

(a) Block 2W - the symbolic worktree dependency graph - lives in plan-mode-schema.md as a SECOND
    projection alongside the Block-2 module-DAG, carries SYMBOLIC topology/lifecycle only (never ref
    STATE: SHAs/tips/paths/leases), and encodes the fork-from-integrated-parent edge
    `worktree(m)@wave-N ==> run-integration` - every wave's worktrees fork from the ONE
    run-integration branch, which already carries all prior waves. odoo-planner authors it and its
    plan-ref line is relaxed to allow symbolic topology while still forbidding concrete ref state.
(b) The odoo-coder coordinator COMMITS its module via Skill(git-toolkit:git-ops) - request-only, no
    direct git leaf agent, no raw git (see also test_coder_coordinator_topology.py).
(c) run-harness carries the between-wave integration (fork-worktrees-from-run-integration + cherry-pick
    in module-DAG order + saga + integrated review + cumulative close-gate + AUTO-ADVANCE with NO
    per-wave PR, then ONE run-level PR via the terminal `integrate` land-tail), consuming Block 2W.

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
WAVE_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "wave-integration.md"
PLAN_MODE_SCHEMA = SCHEMA
WORKFLOW_HARNESS = PLUGIN / "docs" / "reference" / "workflow-harness.md"
PHASE_P_RUN_DAG = PLUGIN / "skills" / "odoo-intake" / "references" / "phase-p-run-dag.md"
UPG_PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
FORWARD_PORT_SKILL = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"


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
    for node in ("base", "run-integration", "worktree(m)@wave-N"):
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


def test_block_2w_fork_from_integrated_parent_edge():
    """The wave-threading property on ONE branch: every wave's worktrees fork from the single
    run-integration branch (which already carries all prior waves), NOT from a per-wave branch."""
    sec = _block_2w_section()
    assert "worktree(m)@wave-N ==> run-integration" in sec, (
        "Block 2W must carry the fork-from-integrated-parent edge "
        "`worktree(m)@wave-N ==> run-integration` (every wave forks from the ONE run-integration branch)."
    )
    low = sec.lower()
    assert "run-integration" in low, "Block 2W must name the single run-integration branch"
    assert "no per-wave pr" in low, (
        "Block 2W must state each wave auto-advances with NO per-wave PR (single-run-PR model)"
    )
    assert "cherry-pick" in low and "-->" in sec, (
        "Block 2W must carry the cherry-pick-into edge (worktree -> run-integration, `-->`)"
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
    assert "run-integration" in low, (
        "odoo-planner must name the single run-integration branch lineage it authors"
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
    assert ("not dispatch" in low or "must not dispatch" in low) and "git leaf" in low, (
        "odoo-coder must state it does NOT dispatch a git leaf agent directly (generic wording - "
        "no leaf-agent name required, per the git-toolkit agent-name zero-mention policy)"
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
    assert "run-integration" in low and "fork" in low, (
        "run-harness must fork each wave's module worktrees from the ONE run-integration branch "
        "(fork-from-integrated-parent, now on a single branch)"
    )


def test_run_harness_cumulative_close_gate_and_single_pr():
    text = _text(RUN_HARNESS)
    low = text.lower()
    assert "cumulative regression close-gate" in low or "cumulative" in low and "close-gate" in low, (
        "run-harness between-wave integration must run the cumulative regression close-gate"
    )
    assert "module-dag" in low and ("topo order" in low or "topo-order" in low or "order" in low), (
        "run-harness must cherry-pick each module commit in module-DAG order"
    )
    assert "saga" in low, "run-harness cherry-pick must use saga rollback (integration-loop.md)"
    # Single-run-PR model: NO per-wave PR; exactly ONE run-level PR via the terminal integrate land-tail.
    assert "no per-wave pr" in low, "run-harness must state there is NO per-wave PR (waves auto-advance)"
    assert "one pr" in low and "integrate" in low, (
        "run-harness must open exactly ONE run-level PR via the terminal `integrate` land-tail"
    )
    assert "l2-merge-gate" in low, (
        "the outward MERGE of the single run PR stays odoo-pr-monitoring's (L2-merge-gate)"
    )


def test_integration_loop_names_run_harness_as_canonical_consumer():
    text = _text(INTEGRATION_LOOP)
    low = text.lower()
    assert "run-harness" in low and "canonical between-wave integration consumer" in low, (
        "integration-loop.md must name run-harness as the canonical between-wave integration consumer"
    )
    # After decision R, run-harness is the SOLE owner - there is no separate git-executor skill.
    # The dead per-wave git-executor must NOT be listed as an owner anymore.
    assert "sole owner" in low, (
        "integration-loop.md must state run-harness is the SOLE owner of the per-wave integration "
        "(the separate git-executor skill was removed)."
    )
    assert re.search(r"^-\s*`?odoo-wave`?\b", text, re.MULTILINE) is None, (
        "integration-loop.md must no longer list the retired per-wave git-executor as an owner bullet."
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
    low = text.lower()
    assert "block 2w" in low, "the ledger must reference Block 2W's fork-from-integrated-parent lineage"
    assert "contains" in low and "addons-path" in low, (
        "the ledger must distinguish the worktree CONTAINING the dependency's source from that "
        "source being on the addons-path"
    )
    assert "policy" in low, (
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
# CS-C2 - worktree-correct addons path: wave-integration.md fixes
#
# Every literal-absence assertion below normalizes whitespace first
# (the prose is hard-wrapped, so a literal spanning a line-wrap would
# otherwise false-negative).
# ---------------------------------------------------------------------------

def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _module_invocation_brief_fence() -> str:
    """The fenced ``` ... ``` block under '## Per-module Invocation Brief Template'."""
    text = _text(WAVE_INTEGRATION)
    marker = "## Per-module Invocation Brief Template"
    start = text.find(marker)
    assert start != -1, (
        "wave-integration.md must carry '## Per-module Invocation Brief Template'"
    )
    fence_start = text.find("```", start)
    assert fence_start != -1, "the brief template must be a fenced block"
    fence_end = text.find("```", fence_start + 3)
    assert fence_end != -1, "the brief template fence must close"
    return text[fence_start: fence_end + 3]


def test_per_module_brief_has_no_unresolved_state_root_placeholder():
    """A (absence): inside the brief fence, no line may contain the literal
    `<SHARE_DIR>` or `<ISOLATE_DIR>` UNLESS that line is the `SHARE_DIR:` /
    `ISOLATE_DIR:` field itself (a resolved-path placeholder is fine there;
    an unresolved one leaking into another field, e.g. design_index, is not)."""
    fence = _module_invocation_brief_fence()
    for line in fence.splitlines():
        stripped = line.strip()
        if stripped.startswith("SHARE_DIR") or stripped.startswith("ISOLATE_DIR"):
            continue
        norm = _normalize_ws(line)
        assert "<SHARE_DIR>" not in norm and "<ISOLATE_DIR>" not in norm, (
            f"unresolved state-root placeholder leaked into a non-field brief line: {line!r}"
        )


def test_per_module_brief_carries_share_and_isolate_fields():
    """A (presence-of-field): the per-module brief fence declares both
    SHARE_DIR and ISOLATE_DIR as captured-literal fields."""
    fence = _module_invocation_brief_fence()
    assert re.search(r"^SHARE_DIR\s*:", fence, re.MULTILINE), (
        "the per-module brief fence must carry a SHARE_DIR field"
    )
    assert re.search(r"^ISOLATE_DIR\s*:", fence, re.MULTILINE), (
        "the per-module brief fence must carry an ISOLATE_DIR field"
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
    <wave-integration.md's text alone>` - one file, one exact phrase.

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
    tree (`_tree_texts()`, the same helper the topology-count guards below
    use) for the whole pattern family, not one file for one sentence.
    """
    offenders = []
    for path, text in _tree_texts():
        norm = _normalize_ws(text)
        for pattern in _ADDONS_STRUCTURAL_CLAIM_PATTERNS:
            if pattern.search(norm):
                offenders.append(f"{path.relative_to(PLUGIN)}: matched {pattern.pattern!r}")
    assert not offenders, (
        "the following files conflate 'worktree contains the dependency's source' with 'source is "
        "on the addons-path' - see snippets/instance-handle-contract.md § Worktree-addons "
        "carve-out:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# CS-C6 - topology: single. The enum owner is wave-integration.md; every other
# site restating the topology value list must become a pointer.
# ---------------------------------------------------------------------------

def _tree_texts():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py).

    Same pattern as test_planning_ssot.py:34-39 - reused here rather than
    imported so this file stays independently runnable (repo convention: no
    cross-test-module imports).
    """
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


_TOPOLOGY_ENUM_LINE = re.compile(r"independent\s*[/|]")


def _is_topology_enum_line(line: str) -> bool:
    """True when `line` restates the topology value list as a DELIMITED enumeration
    (`independent / ...` or `independent | ...`) AND names `diamond`.

    Requiring the pipe/slash delimiter (not just co-occurrence of the two words)
    is deliberate: a bare `"independent" in line and "diamond" in line` check
    false-positives on `skills/_shared/doc-cluster-plan.md:73` ("Deeper trees /
    diamonds recurse: one instance per independent leaf-path...") - unrelated
    doc-instance-topology prose that happens to share two common English words
    with the wave-topology enum, not a restatement of its value list. Requiring
    the enumeration-style delimiter keeps the loose 2-word intent (still catches
    a surviving partial-value fork, not just an exact five-value match) while
    excluding that homonym.
    """
    return bool(_TOPOLOGY_ENUM_LINE.search(line)) and "diamond" in line


def test_topology_value_set_has_exactly_one_definer():
    """A (count == 1): the topology enum's value LIST (independent/linear/mixed/diamond/single)
    must be textually restated in exactly one file - wave-integration.md, the enum's SSOT owner.
    Scans for any DELIMITED enumeration line carrying 'independent' and 'diamond' (not all five
    values together), so it also catches a surviving FOUR-value fork - a scan for all five values
    on one line would be blind to that fork, which is the exact defect this guards against."""
    definer_files = set()
    for path, text in _tree_texts():
        for line in text.splitlines():
            if _is_topology_enum_line(line):
                definer_files.add(str(path.relative_to(PLUGIN)))
    owner = "skills/run-harness/references/wave-integration.md"
    assert definer_files == {owner}, (
        f"the topology value list must be restated in exactly {{'{owner}'}}; "
        f"found it also in: {sorted(definer_files - {owner})}"
    )


def test_owner_file_lists_single_in_every_value_enumeration():
    """A (completeness): every line inside wave-integration.md (the owner) that restates the
    topology value list (a delimited 'independent /|' enumeration naming 'diamond') must also
    carry 'single' - guards against updating the heading/intro sentence but forgetting the
    log-template (:145) or the per-module-brief (:294) copies of the same list."""
    text = _text(WAVE_INTEGRATION)
    offending = [
        line for line in text.splitlines()
        if _is_topology_enum_line(line) and "single" not in line
    ]
    assert not offending, (
        f"wave-integration.md value-enumeration line(s) missing 'single': {offending}"
    )


_TOPOLOGY_CONSUMERS = {
    "plan-mode-schema.md": PLAN_MODE_SCHEMA,
    "integration-loop.md": INTEGRATION_LOOP,
    "phase-p-run-dag.md": PHASE_P_RUN_DAG,
    "run-harness/SKILL.md": RUN_HARNESS,
    "upg-phase-detail.md": UPG_PHASE_DETAIL,
    "odoo-forward-port/SKILL.md": FORWARD_PORT_SKILL,
    "odoo-planner.md": PLANNER,
    "workflow-harness.md": WORKFLOW_HARNESS,
}


def test_consumers_point_at_the_topology_owner():
    """A (glob) - a WEAK pointer-presence guard: it only proves each consumer NAMES the owner, not
    that it stopped restating values (test_topology_value_set_has_exactly_one_definer above is the
    test with real teeth - it reddens if the enum forks). Each of the eight consumer files must
    contain the literal pointer 'wave-integration.md' somewhere in a context naming the owner's
    '§ Topology values' section."""
    for label, path in _TOPOLOGY_CONSUMERS.items():
        text = _text(path)
        assert "wave-integration.md" in text, (
            f"{label} must point at wave-integration.md (the topology enum's ONE owner)"
        )
        assert "Topology values" in text, (
            f"{label} must name the owner's '§ Topology values' section, not just the bare filename"
        )


# ---------------------------------------------------------------------------
# CS-C6 follow-up: a stale "N topologies" count word is a SEPARATE defect from
# the value-list restatement above - it can drift even in a file that has NO
# copy of the value list at all (a bare prose reference to "the four
# topologies"). Guard it by COMPUTING N from the owner's canonical enumeration
# and asserting every count-word reference to it agrees, rather than
# hardcoding "five" as a snapshot (ETHOS #8: protect the behavior/invariant -
# "the count word must track the actual enumeration" - not today's number).
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUMBER_WORD_ALTERNATION = "|".join(_NUMBER_WORDS)


def _topology_value_count() -> int:
    """N = the number of values in the owner's canonical enumeration (the intro sentence's
    parenthetical list right under the '## Topology values' heading), computed from the text
    itself - never hardcoded - so this stays correct when a sixth value is added."""
    text = _text(WAVE_INTEGRATION)
    m = re.search(r"Choose from the plan's Block-2 module-DAG \(([^)]+)\)", text)
    assert m, (
        "wave-integration.md must carry the canonical topology-values intro sentence "
        "this count is computed from"
    )
    values = [v.strip() for v in m.group(1).split("/")]
    assert values, "the canonical enumeration must not be empty"
    return len(values)


def _count_word_violations(text: str, n: int) -> list[str]:
    """Every count-word reference to 'topolog(y|ies)' in `text` must numerically agree with `n`
    (the ACTUAL enumerated value count) - UNLESS the reference is explicitly scoped to
    'multi-module' (excluding the `single` collapse case, which has no internal module ordering
    to describe), in which case it must agree with `n - 1`. Two directions are checked: the count
    word BEFORE 'topolog' ("four multi-module topologies", "five topology values",
    "the 4 wave-batch topologies") and the count word inside a "Topology values (<word>)"
    heading-style parenthetical (topolog BEFORE the word).

    Widened (was word-only: `\\b(one|two|...)\\b(\\s+multi-module)?\\s+topolog`, so it was blind to
    a DIGIT count and to any filler word other than the literal "multi-module" between the count
    and "topolog"): the count token now also accepts a bare digit (`4`, not just `four`), and up to
    3 filler words of any kind may sit between the count and "topolog" (`wave-batch`,
    `multi-module`, or a future adjective) - only "multi-module" (anywhere in that filler span)
    still switches the expectation to `n - 1`. This is what makes
    `skills/odoo-intake/references/maintainers.md`'s "the **4** wave-batch topologies" (a digit,
    with the filler word "wave-batch" the old regex could not skip past) visible to this guard at
    all. Returns violation messages (empty = no violations)."""
    violations = []
    for m in re.finditer(
        rf"\b(\d{{1,2}}|{_NUMBER_WORD_ALTERNATION})\b((?:\s+[A-Za-z][A-Za-z-]*){{0,3}})\s+topolog",
        text, re.IGNORECASE,
    ):
        word = m.group(1).lower()
        filler = (m.group(2) or "").lower()
        scoped_to_multi_module = "multi-module" in filler
        expected = (n - 1) if scoped_to_multi_module else n
        value = int(word) if word.isdigit() else _NUMBER_WORDS[word]
        if value != expected:
            violations.append(
                f"count token {word!r} ({'multi-module-scoped, ' if scoped_to_multi_module else ''}"
                f"expected {expected}) disagrees with the enumerated value count N={n}: "
                f"matched {m.group(0)!r}"
            )
    for m in re.finditer(r"[Tt]opology values\s*\((\w+)\)", text):
        word = m.group(1).lower()
        if word not in _NUMBER_WORDS or _NUMBER_WORDS[word] != n:
            violations.append(
                f"heading count word {word!r} disagrees with the enumerated value count N={n}"
            )
    return violations


def test_owner_file_count_words_agree_with_the_enumerated_value_count():
    """A stale 'the four topologies' sentence sitting right after a five-value enumeration is a
    defect this PR exists to remove: a reader cannot tell whether it is stale prose or a
    deliberate exclusion, and if excluded, which value. This computes N from the owner's own
    enumeration and asserts every count-word reference to 'topolog...' in the owner file agrees
    with N (or N - 1 when explicitly scoped to 'multi-module', i.e. excluding the `single`
    collapse case, which has no internal ordering). Adding a sixth value and forgetting to update
    one of these count words reddens this test instead of leaving a silent ambiguity for the next
    reader to puzzle out."""
    n = _topology_value_count()
    violations = _count_word_violations(_text(WAVE_INTEGRATION), n)
    assert not violations, "\n".join(violations)


def test_run_harness_skill_count_word_agrees_with_the_enumerated_value_count():
    """Same guard as above, applied to run-harness/SKILL.md's own 'Full templates (... topology
    values ...)' cross-reference into the owner - a second site this same follow-up fixed, so it
    gets the same protection against drifting stale again."""
    n = _topology_value_count()
    violations = _count_word_violations(_text(RUN_HARNESS), n)
    assert not violations, "\n".join(violations)


def test_every_file_stating_a_topology_count_agrees_with_the_owner():
    """CLASS guard (widened from 2 hardcoded files to the WHOLE plugin tree).

    BEFORE: the two tests above only ever read `WAVE_INTEGRATION` and
    `RUN_HARNESS` - any THIRD file stating a topology count was invisible to
    both, no matter how stale. `skills/odoo-intake/references/maintainers.md`
    said "the 4 wave-batch topologies" (a DIGIT, with the filler word
    "wave-batch") after the enum grew to 5 values, and neither test could see
    it: it isn't one of the two files, and even if it were, the old regex
    only matched a spelled-out number word immediately followed by
    "multi-module" or "topolog" - not a digit, and not with an arbitrary
    filler word in between.

    AFTER: scan every text file in the plugin (`_tree_texts()`, the same
    whole-tree helper `test_topology_value_set_has_exactly_one_definer` uses)
    with the widened `_count_word_violations` (digit-or-word count token, up
    to 3 filler words before "topolog").

    Pre-fix finding count on this exact check (verified against
    `git show HEAD:...maintainers.md`): exactly 1 -
    `skills/odoo-intake/references/maintainers.md` ("the 4 wave-batch
    topologies"). WAVE_INTEGRATION and RUN_HARNESS themselves are already
    covered (and green) by the two dedicated tests above; this one exists to
    catch every OTHER file, present or future.
    """
    n = _topology_value_count()
    offenders = []
    for path, text in _tree_texts():
        violations = _count_word_violations(text, n)
        if violations:
            offenders.append(f"{path.relative_to(PLUGIN)}: " + "; ".join(violations))
    assert not offenders, (
        "the following files state a topology count that disagrees with the enumerated value "
        f"count N={n} (owner: skills/run-harness/references/wave-integration.md):\n"
        + "\n".join(offenders)
    )
