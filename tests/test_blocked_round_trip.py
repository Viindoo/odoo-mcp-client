"""The BLOCKED round trip - what a refusing worker must leave behind for its replacement.

A nested coordinator (`agents/odoo-coder.md`) cannot resume a worker: a resume is fire-and-forget
and a nested parent that ends its turn to await one is never woken. Its only round trip is
worker-returns-BLOCKED -> coordinator reads it from the blocking launch's return value ->
coordinator COLD-SPAWNS a replacement. The replacement inherits exactly two things: whatever landed
in the shared `WORKTREE_PATH`, and whatever landed in the run's worklog. Four contracts keep that
inheritance real, and each has its own failure mode:

  1. **Resolved state dirs.** `<ISOLATE_DIR>` keys on the enclosing repository root, so a leaf that
     resolves it AFTER `cd`-ing into `WORKTREE_PATH` writes into that worktree's own tree. The
     coordinator then reads a DIFFERENT directory back and finds nothing - a silent empty read, not
     an error. The dispatcher must resolve once and pass `SHARE_DIR:`/`ISOLATE_DIR:` down; the leaf
     must consume them instead of re-resolving.
  2. **Write on every exit.** An append gated on reaching green writes nothing on the one path
     where the log is the only surviving artifact.
  3. **`PRIOR ATTEMPT`.** A replacement handed an unchanged brief re-derives what its predecessor
     already ruled out and reaches the same block.
  4. **`produced` on a refusal.** A hardcoded `produced: []` pre-empts the evidence field on the
     status where partial work is most likely, and a caller that never reads it cannot use it.

Prose guards, in the grep-the-Markdown idiom of `tests/test_dispatch_brief.py`. Assertions target
the CONTRACT (what a runtime agent must be told), not any one phrasing, and are whitespace-
normalized so a re-wrap does not turn a correct file red.
"""
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
SKILLS = PLUGIN / "skills"
SNIPPETS = PLUGIN / "snippets"

CODER = AGENTS / "odoo-coder.md"
BACKEND = AGENTS / "odoo-backend-coder.md"
FRONTEND = AGENTS / "odoo-frontend-coder.md"
TEST_WRITER = AGENTS / "odoo-test-writer.md"
DISPATCH_BRIEF = SNIPPETS / "dispatch-brief.md"
WORKLOG_CONTRACT = SNIPPETS / "worklog-contract.md"
TEST_EXEMPTION = SNIPPETS / "test-exemption-contract.md"
SKILL_TOOL_DEPS = PLUGIN / "generator" / "skill_tool_deps.json"

_FENCE = re.compile(r"```.*?```", re.S)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Collapse every whitespace run to one space - a Markdown re-wrap must not flip a guard."""
    return " ".join(text.split())


def _fences(path: Path) -> list[str]:
    return _FENCE.findall(_text(path))


def _worktree_fences(path: Path) -> list[str]:
    """Every fenced dispatch brief in `path` that names a worktree root.

    `WORKTREE_PATH` is by definition a root other than the dispatcher's own cwd, so per
    `snippets/dispatch-brief.md` skeleton field 5 each such brief owes resolved state dirs.
    """
    return [f for f in _fences(path) if re.search(r"^\s*WORKTREE_PATH\s*:", f, re.M)]


# ---------------------------------------------------------------------------
# Discovery floors - a vacuous parametrize passes without testing anything.
# ---------------------------------------------------------------------------

# Every site a leaf/skill is dispatched against a worktree root distinct from the dispatcher's
# own cwd. Grow-only: a new cross-root dispatch belongs here, never an exemption from the rule.
WORKTREE_DISPATCH_SITES = [
    CODER,
    SKILLS / "odoo-coding" / "SKILL.md",
    SKILLS / "odoo-icon-design" / "SKILL.md",
    SKILLS / "odoo-git-rebase" / "references" / "rb-phase-detail.md",
    SKILLS / "odoo-forward-port" / "references" / "fp-phase-detail.md",
    SKILLS / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md",
    SKILLS / "run-harness" / "references" / "wave-integration.md",
]

# Leaves that `cd` into the dispatched worktree before they touch a Tier-2 path - exactly the
# agents for which "resolve from your own cwd" resolves to the WRONG tree.
WORKTREE_ROOTED_LEAVES = [BACKEND, FRONTEND, TEST_WRITER,
                          AGENTS / "odoo-translator.md",
                          AGENTS / "odoo-icon-designer.md",
                          AGENTS / "odoo-instance-ops.md"]

# The three workers `odoo-coder` launches, all of which can refuse.
CODER_FAMILY_WORKERS = [BACKEND, FRONTEND, TEST_WRITER]

LEAF_CODERS = [BACKEND, FRONTEND]


def test_every_referenced_file_exists():
    missing = [
        str(p.relative_to(REPO_ROOT))
        for p in (
            WORKTREE_DISPATCH_SITES
            + WORKTREE_ROOTED_LEAVES
            + [DISPATCH_BRIEF, WORKLOG_CONTRACT, TEST_EXEMPTION, SKILL_TOOL_DEPS]
        )
        if not p.exists()
    ]
    assert not missing, f"guarded files vanished: {missing}"


def test_dispatch_sites_actually_carry_worktree_fences():
    """Without this floor, a renamed heading would silently empty every parametrize below."""
    empty = [str(p.relative_to(REPO_ROOT)) for p in WORKTREE_DISPATCH_SITES
             if not _worktree_fences(p)]
    assert not empty, (
        f"these dispatch sites no longer expose a fenced brief carrying WORKTREE_PATH - the "
        f"guard below would pass vacuously: {empty}"
    )


# ---------------------------------------------------------------------------
# 1. Resolved state dirs - the dispatcher side.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", WORKTREE_DISPATCH_SITES, ids=lambda p: p.name)
def test_a_brief_naming_a_worktree_also_carries_the_resolved_state_dirs(path):
    """A dispatch that names a root other than the dispatcher's cwd must hand down BOTH state
    dirs as resolved absolute literals. Omitting them makes each leaf re-resolve `<ISOLATE_DIR>`
    from its own cwd, into a different tree - the caller's read-back then returns nothing, with no
    error anywhere. Rule: `snippets/state-root-resolution.md` § Cross-worktree dispatch."""
    offenders = []
    for fence in _worktree_fences(path):
        missing = [k for k in ("SHARE_DIR", "ISOLATE_DIR")
                   if not re.search(rf"^\s*{k}\s*:", fence, re.M)]
        if missing:
            head = _norm(fence)[:160]
            offenders.append(f"missing {missing} in fence starting: {head}")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: a fenced brief names WORKTREE_PATH but not the resolved "
        f"state dirs -> {offenders}"
    )


def test_no_dispatch_brief_uses_the_non_canonical_worktree_key():
    """`snippets/dispatch-brief.md` field 5 requires the literal `WORKTREE_PATH` token because it
    is grepped verbatim elsewhere. A brief spelling it `WORKTREE:` is invisible to every consumer
    that looks for the canonical name - including the guard above."""
    hits = []
    for md in PLUGIN.rglob("*.md"):
        for i, line in enumerate(_text(md).splitlines(), 1):
            if re.match(r"^\s*WORKTREE\s*:", line):
                hits.append(f"{md.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not hits, (
        "dispatch briefs must use the canonical `WORKTREE_PATH` key, never a bare `WORKTREE:` - "
        f"a new name silently misses consumers: {hits}"
    )


def test_dispatch_brief_field_5_binds_the_state_dirs_to_the_worktree():
    """The rule existed only as unnumbered prose, so every skill that filled the numbered skeleton
    faithfully reproduced the omission. Field 5 is where a dispatcher looks."""
    row = [ln for ln in _text(DISPATCH_BRIEF).splitlines() if ln.startswith("| 5 |")]
    assert row, "dispatch-brief.md lost skeleton row 5"
    field5 = _norm(row[0])
    for token in ("SHARE_DIR", "ISOLATE_DIR"):
        assert token in field5, (
            f"skeleton field 5 must name `{token}` as a companion of WORKTREE_PATH - otherwise a "
            "dispatcher filling the numbered table never learns the requirement exists"
        )


# ---------------------------------------------------------------------------
# 1b. Resolved state dirs - the leaf side.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", WORKTREE_ROOTED_LEAVES, ids=lambda p: p.name)
def test_a_worktree_rooted_leaf_consumes_the_handed_state_dirs_instead_of_re_resolving(path):
    """Passing the literals down is only half the fix: a leaf whose body says "resolve once" with
    no carve-out re-resolves anyway, from the worktree it just `cd`-ed into."""
    body = _norm(_text(path))
    assert re.search(r"`SHARE_DIR:`/`ISOLATE_DIR:` fields", body), (
        f"{path.name}: must say what to do when the brief HANDS IT `SHARE_DIR:`/`ISOLATE_DIR:`"
    )
    assert re.search(r"do NOT re-run the resolver", body), (
        f"{path.name}: must forbid re-running the resolver when handed the literals - "
        "re-resolving from a worktree cwd is exactly the divergence this fix removes"
    )
    assert re.search(r"[Oo]nly when both (fields )?are ABSENT", body), (
        f"{path.name}: must keep the standalone fallback (resolve yourself) explicit, so the "
        "carve-out does not read as 'never resolve'"
    )


# ---------------------------------------------------------------------------
# 2. The worklog is written before EVERY exit, not only a successful one.
# ---------------------------------------------------------------------------


def test_worklog_contract_obliges_an_entry_on_every_terminal_status():
    body = _norm(_text(WORKLOG_CONTRACT))
    assert "before EVERY exit" in body, (
        "worklog-contract.md must state the write timing as per-EXIT; 'at end of your step' reads "
        "as the successful end and leaves the refusal path unwritten"
    )
    for status in ("DONE", "BLOCKED", "NEEDS_CONTEXT", "NEEDS_NEXT"):
        assert f"`{status}`" in body, (
            f"worklog-contract.md must name `{status}` among the exits that owe an entry - "
            "listing only some of them is how the refusal path stayed uncovered"
        )
    assert "ruled out" in body, (
        "worklog-contract.md must say a refusal records what was RULED OUT, not just what was "
        "tried - the analysis is what the one-line blocked_reason cannot carry"
    )


def test_the_worklog_append_is_never_gated_on_reaching_green():
    """A worker that only appends 'once green' writes nothing on the exit where the log is the
    replacement's only inheritance."""
    offenders = []
    for md in list(AGENTS.glob("*.md")) + list(SKILLS.rglob("*.md")) + list(SNIPPETS.glob("*.md")):
        body = _norm(_text(md))
        for m in re.finditer(r"[Oo]nce green,?\s+APPEND", body):
            offenders.append(f"{md.relative_to(REPO_ROOT)}: ...{body[max(0, m.start()-60):m.end()+80]}...")
    assert not offenders, (
        f"the worklog append must not be conditioned on reaching green: {offenders}"
    )


@pytest.mark.parametrize("path", CODER_FAMILY_WORKERS, ids=lambda p: p.name)
def test_each_coder_family_worker_appends_the_worklog_on_a_refusal(path):
    """The read side already works - the replacement is required to read the worklog first. What
    was missing is any rule making the refusing worker WRITE one."""
    body = _norm(_text(path))
    assert re.search(r"(refusal|BLOCKED|EVERY exit).{0,400}?worklog", body, re.I), (
        f"{path.name}: nothing ties a refusal/every-exit to a worklog append"
    )
    assert "ruled out" in body, (
        f"{path.name}: a refusal entry must record what was RULED OUT and why - the reasoning "
        "behind the refusal is precisely what `blocked_reason` cannot hold"
    )
    assert re.search(r"never a transcript|not a transcript", body), (
        f"{path.name}: must bound the entry to decisions, per worklog-contract.md's "
        "'decisions that change the outcome, not routine narration'"
    )


# ---------------------------------------------------------------------------
# 3. `PRIOR ATTEMPT` - a re-dispatch that supersedes a failed pass carries it.
# ---------------------------------------------------------------------------


def test_prior_attempt_is_registered_as_a_coder_family_brief_field():
    text = _text(DISPATCH_BRIEF)
    start = text.index("### Coder")
    end = text.index("### Reviewer", start)
    coder_delta = _norm(text[start:end])
    assert "`PRIOR ATTEMPT`" in coder_delta, (
        "dispatch-brief.md's Coder family delta must register `PRIOR ATTEMPT` - the field existed "
        "at exactly one use site and was unknown to the family that needs it most"
    )
    assert "re-dispatch" in coder_delta and "first dispatch" in coder_delta, (
        "the registration must scope the field to a superseding re-dispatch and say it is omitted "
        "on a first dispatch - otherwise it reads as a universally required key"
    )


def test_prior_attempt_is_not_promoted_into_the_universal_skeleton():
    """It is a Coder-family delta. An 11th skeleton row is guarded elsewhere as the retired
    reply-address field returning; this test states the positive intent."""
    text = _text(DISPATCH_BRIEF)
    skeleton_rows = [ln for ln in text.splitlines() if re.match(r"^\|\s*\d+\s*\|", ln)]
    assert not any("PRIOR ATTEMPT" in ln for ln in skeleton_rows), (
        "`PRIOR ATTEMPT` must stay a family delta, never a universal skeleton row"
    )


def test_the_coordinator_carries_prior_attempt_on_a_re_dispatch():
    body = _norm(_text(CODER))
    assert "PRIOR ATTEMPT" in body, "odoo-coder.md must wire `PRIOR ATTEMPT` into its retry path"
    fences = " ".join(_norm(f) for f in _worktree_fences(CODER))
    assert fences.count("PRIOR ATTEMPT:") >= 2, (
        "both of odoo-coder's leaf briefs must expose `PRIOR ATTEMPT:` - the bounded fix loop "
        "re-dispatches the test-writer as well as the coders"
    )


def test_prior_attempt_is_declared_in_the_brief_manifest():
    registry = json.loads(_text(SKILL_TOOL_DEPS))["agents"]
    for agent in ("odoo-coder", "odoo-backend-coder", "odoo-frontend-coder", "odoo-test-writer"):
        brief = registry[agent]["brief"]
        declared = set(brief.get("required", [])) | set(brief.get("optional", []))
        assert "PRIOR ATTEMPT" in declared, (
            f"{agent}: `PRIOR ATTEMPT` must be declared in its brief manifest, so the field is "
            "discoverable from the SSOT rather than from one skill's prose"
        )


def test_the_coder_family_manifest_declares_the_state_dirs():
    registry = json.loads(_text(SKILL_TOOL_DEPS))["agents"]
    for agent in ("odoo-coder", "odoo-backend-coder", "odoo-frontend-coder"):
        required = registry[agent]["brief"].get("required", [])
        for key in ("SHARE_DIR", "ISOLATE_DIR"):
            assert key in required, (
                f"{agent}: `{key}` must be a REQUIRED brief key - this family always works in a "
                "worktree that is not its dispatcher's cwd, and always writes a worklog"
            )


# ---------------------------------------------------------------------------
# 4. `produced` on a refusal - the worker lists it, the caller reads it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", LEAF_CODERS, ids=lambda p: p.name)
def test_a_refusal_template_does_not_pre_empt_produced_with_an_empty_list(path):
    """`snippets/continuation-contract.md` defines `produced` with no status qualifier, and
    run-harness already treats BLOCKED-with-partial-effect as legitimate. A template hardcoding
    `produced: []` throws away the one record of what actually landed in the shared worktree."""
    text = _text(path)
    start = text.index("## Continuation Contract")
    section = text[start:]
    refusals = [b for b in _FENCE.findall(section) if "status: BLOCKED" in b]
    assert refusals, f"{path.name}: no BLOCKED refusal template found under ## Continuation Contract"
    block = refusals[0]
    assert "produced: []" not in block, (
        f"{path.name}: the refusal template must not hardcode `produced: []` - a worker that "
        "wrote partial files and its worklog entry must report them"
    )
    assert re.search(r"^produced:", block, re.M), (
        f"{path.name}: the refusal template must still carry a `produced:` line"
    )
    assert "worklog" in block.lower(), (
        f"{path.name}: the refusal's `produced` must name the worklog entry - it is the artifact "
        "the cold replacement actually reads"
    )


@pytest.mark.parametrize("path", CODER_FAMILY_WORKERS, ids=lambda p: p.name)
def test_an_empty_produced_stays_legal_when_nothing_was_written(path):
    """The fix is to stop making `produced: []` unconditional, not to force a non-empty list."""
    body = _norm(_text(path))
    # Tolerant of the backticks and of the surrounding wording - what must survive is the CLAUSE
    # that keeps an empty list a legal, meaningful answer.
    assert re.search(r"`?\[\]`? only when you truly wrote nothing", body), (
        f"{path.name}: must keep `[]` correct for a worker that genuinely wrote nothing"
    )


def test_the_coordinator_reads_a_blocked_childs_produced():
    """Both halves or neither: a worker that reports its partial work to a caller which never
    reads the field has changed nothing."""
    body = _norm(_text(CODER))
    assert re.search(r"READ what the refusing worker already produced", body), (
        "odoo-coder.md must instruct reading a refusing worker's `produced` before composing the "
        "replacement's brief - nothing told it to read that list at all"
    )
    assert re.search(r"`produced` list", body), (
        "odoo-coder.md must name the `produced` list literally, not gesture at 'the result'"
    )


def test_the_exemption_contract_no_longer_prescribes_an_empty_produced():
    """A single surviving restatement recreates the defect."""
    body = _norm(_text(TEST_EXEMPTION))
    assert "`produced: []`" not in body, (
        "test-exemption-contract.md must not prescribe `produced: []` for a refusal - it is the "
        "same pre-emption the coder templates carried"
    )
