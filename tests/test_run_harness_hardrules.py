"""Behavioral guard for run-harness's hard rules.

Tests protect the business contract, NOT the code structure:

- "never write/commit to the principal checkout"
- "never auto-merge - the outward merge is human-gated (L2)"
- "exactly ONE PR per REPO per run" (the cardinality kernel, inversion-guarded)
- "the driver dispatches ONE node per iteration and never has two dispatches in flight"

The last two are CONSOLIDATED kernels. The cardinality kernel previously had four separate
inversion detectors for a per-GROUP PR cadence; the grouping layer is gone, so the phrase they
hunted for cannot be written - but the property they protected (no PR cadence BELOW the repo)
still can be violated, by a per-node or per-module cadence, so ONE inversion-guarded assertion
keys on the actor relationship instead of on a retired noun. The dispatch kernel arrives from
the retired topology-value guards, whose only surviving fact was that the driver dispatches
sequentially.

Each assertion fails for exactly one reason: the corresponding rule was removed or inverted.

Run with: python3 -m pytest tests/test_run_harness_hardrules.py -v
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
RUN_HARNESS = PLUGIN / "skills" / "run-harness" / "SKILL.md"


def _skill_body() -> str:
    assert RUN_HARNESS.exists(), f"skills/run-harness/SKILL.md not found at {RUN_HARNESS}"
    text = RUN_HARNESS.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _norm(text: str) -> str:
    """Whitespace-normalize, first stripping line-leading `#` markers.

    The loop's contract is written inside a fenced pseudo-code block where each continuation line
    is a `#` comment, so a sentence that wraps carries a stray `#` mid-phrase. Dropping the
    line-leading marker (markdown heading or pseudo-code comment alike) is what lets a
    presence/absence assertion survive a re-wrap of the same sentence.
    """
    return re.sub(r"\s+", " ", re.sub(r"(?m)^[ \t]*#+[ \t]?", " ", text))


# ---------------------------------------------------------------------------
# Rule 1: Principal-branch-lock
# run-harness must explicitly prohibit dispatching a source-writing node against the principal
# checkout / writing-committing to the principal branch. If deleted, a coding node could mutate
# the branch other sessions depend on, breaking the worktree isolation guarantee.
# ---------------------------------------------------------------------------

_PRINCIPAL_LOCK_RE = re.compile(
    r"(?i)(never|must\s+not|do\s+not).{0,90}?principal\s+(checkout|branch)",
    re.DOTALL,
)


def test_principal_branch_lock_present():
    """Rule 1: run-harness must prohibit git write-ops / dispatch against the principal checkout.

    Fails if: the principal-branch-lock rule is removed or rephrased to drop the prohibition. This
    would let a node commit directly to master/main, defeating the worktree isolation model.
    """
    body = _skill_body()
    assert _PRINCIPAL_LOCK_RE.search(body), (
        "skills/run-harness/SKILL.md: principal-branch-lock rule missing. The body must prohibit "
        "dispatching a source-writing node against / writing to the principal checkout|branch "
        "(e.g. Hard rule 6: 'NEVER dispatch a source-writing node against the principal checkout')."
    )


# ---------------------------------------------------------------------------
# Rule 4: Human-confirm merge (no auto-merge)
# The run drives to done autonomously up to "PR opened"; the outward merge stays L2 (always a
# human gate). If deleted, a run could auto-land unreviewed changes on the principal branch.
# ---------------------------------------------------------------------------

_HUMAN_CONFIRM_RE = re.compile(
    r"(?i)(human.{0,20}confirm|human\s+approves|no.{0,20}auto.{0,20}merg|never.{0,20}auto.{0,20}merg"
    r"|l2\s+is\s+always\s+a\s+human\s+gate|l2\s+never\s+(lowers|auto-passes))",
    re.DOTALL,
)


def test_human_confirm_merge_present():
    """Rule 4: run-harness must require a human gate before the merge (no auto-merge).

    Fails if: the human-gated-merge rule is removed or softened to allow automatic merge. Without
    it, a run could silently merge a PR while the human is away.
    """
    body = _skill_body()
    assert _HUMAN_CONFIRM_RE.search(body), (
        "skills/run-harness/SKILL.md: human-confirm-merge rule missing. The body must state the "
        "merge/squash is human-gated (e.g. 'L2 is always a human gate', 'human-confirmed', "
        "'L2 never auto-passes, so the human approves the merge')."
    )


# ---------------------------------------------------------------------------
# Rule: exactly ONE PR per REPO per run - the cardinality kernel.
#
# A bare `"one pr" in low` substring check names this rule without protecting it: it is equally
# satisfied by policy-INVERTING text such as "one PR per node", since "one pr" is a literal
# substring of that too. So: anchor on the actual CARDINALITY claim, and reject the inversion two
# ways - as a literal sub-repo cadence, and as an ACTOR RELATIONSHIP (some unit smaller than the
# repo being the grammatical subject that "opens" a PR).
#
# The actor half is what survives from the four retired per-group detectors. Their history is the
# reason it is shaped this way: each earlier fix keyed the actor to a CLOSED word set (first four
# quantifiers, then a longer list), and each time a reviewer constructed ordinary English outside
# the set that asserted the identical inversion. The property that matters is not WHICH word
# introduces the unit - it is whether ANY sub-repo unit noun is the near grammatical subject of an
# "opens ... PR" clause. Two things genuinely ARE closed classes and are enumerated: English
# clause negation ("no"/"not"/"never"/...), and the ONE legitimate opener (`integrate`, the land
# tail). Both are excluded via a bounded same-clause window rather than a fixed-width lookbehind,
# so "no intermediate PR is ever opened" and "the terminal `integrate` node ... opens ONE PR"
# stay legal however many words sit in between.
# ---------------------------------------------------------------------------

_ONE_PR_PER_REPO_RE = re.compile(r"(?i)exactly\s+ONE\s+PR\s+per\s+REPO\s+per\s+run")
_SUB_REPO_CADENCE_RE = re.compile(
    r"(?i)\b(?:one|a|1)\s+pr\s+per\s+(node|module|step|stage|batch|group|cluster|commit)\b"
)

# Any unit SMALLER than the repo. Deliberately not quantifier-keyed (see the note above).
_SUB_REPO_ACTOR = r"\b(?:nodes?|modules?)\b"
_OPEN_VERB = r"\bopen(?:s|ing|ed)?\b"
_PR_TOKEN = r"\bprs?\b"
_SUB_REPO_OPENER_CORE_RE = re.compile(
    rf"(?i){_SUB_REPO_ACTOR}[^.;]{{0,25}}"
    rf"(?:{_OPEN_VERB}[^.;]{{0,40}}{_PR_TOKEN}|{_PR_TOKEN}[^.;]{{0,40}}{_OPEN_VERB})"
)
# English clause-negation is a genuinely closed, small function-word class - unlike "ways to refer
# to a node", this is safe to enumerate.
_NEGATION_RE = re.compile(r"(?i)\b(?:no|not|never|cannot|isn't|aren't|without)\b")
# The ONE legitimate PR opener: the terminal land-tail node, once per repo.
_LEGIT_OPENER_RE = re.compile(r"(?i)\b(?:integrate|land[\s-]?tail)\b")
_CLAUSE_WINDOW = 40  # chars scanned immediately before the actor match, same clause only


def _sub_repo_pr_opener_matches(text: str) -> list[re.Match]:
    """Every 'sub-repo unit opens a PR' candidate, excluding one whose actor sits under a
    same-clause negation, or whose same-clause context names the legitimate `integrate` land-tail
    opener. Both exclusions are Python-level bounded-WINDOW checks rather than fixed-width regex
    lookbehinds, so an arbitrary number of intervening words is still handled. Neither window ever
    crosses a preceding '.'/';' clause boundary, so an earlier, unrelated sentence can never
    suppress a real match."""
    matches = []
    for m in _SUB_REPO_OPENER_CORE_RE.finditer(text):
        start = m.start()
        clause_start = max(text.rfind(".", 0, start), text.rfind(";", 0, start)) + 1
        window = text[max(clause_start, start - _CLAUSE_WINDOW): start]
        if _NEGATION_RE.search(window):
            continue
        if _LEGIT_OPENER_RE.search(window + m.group(0)):
            continue
        matches.append(m)
    return matches


def _sub_repo_pr_opener_search(text: str):
    """`.search()`-shaped wrapper - first match or `None`."""
    matches = _sub_repo_pr_opener_matches(text)
    return matches[0] if matches else None


def test_exactly_one_pr_per_repo_per_run():
    """The cardinality kernel: the whole run lands as exactly ONE PR PER REPO, opened by that
    repo's terminal `integrate` node - never a PR per node, per module, or per any other unit
    smaller than the repo, and no intermediate PR at all.

    Fails if: the cardinality claim disappears, or the text acquires a PR cadence below the repo -
    either as a literal ("one PR per node") or as an actor relationship (a node/module being the
    thing that "opens" a PR), which is the inversion dressed up as a cardinality claim.
    """
    body = _skill_body()
    norm = _norm(body)
    assert _ONE_PR_PER_REPO_RE.search(norm), (
        "run-harness must state EXACTLY ONE PR per REPO per run - not merely mention \"PR\" in "
        "passing, and not a run-level claim that leaves the multi-repo case undefined."
    )
    assert re.search(r"(?i)N repos = N `?integrate`? nodes = N PRs", norm), (
        "run-harness must state the multi-repo arithmetic (N repos = N integrate nodes = N PRs) - "
        "the cardinality is per REPOSITORY, and a second repo is a second PR, not a second run."
    )
    assert re.search(r"(?i)no intermediate PR is ever opened", norm), (
        "run-harness must state no INTERMEDIATE PR is ever opened - the property a per-unit "
        "cadence would violate."
    )
    assert not _SUB_REPO_CADENCE_RE.search(norm), (
        "run-harness text asserts a PR cadence BELOW the repo (\"one PR per node/module/...\"), "
        "which inverts the one-PR-per-repo rule."
    )
    assert not _sub_repo_pr_opener_search(norm), (
        "run-harness text reads as a NODE or MODULE (not the repo's terminal `integrate` land "
        "tail) being the grammatical actor that 'opens' a PR - a per-unit PR cadence dressed as a "
        "cardinality claim."
    )
    assert re.search(r"(?i)odoo-pr-monitoring", norm), (
        "the outward merge of that ONE PR must stay odoo-pr-monitoring's - run-harness never merges."
    )


def test_one_pr_guard_rejects_a_constructed_sub_repo_inversion():
    """Companion meta-test: prove the guard actually defeats a policy-inverting sentence that
    satisfies every OTHER assertion, and never fires on the real run-harness/SKILL.md text (which
    would be a false positive blocking legitimate one-PR-per-repo prose).

    Fails if: the guard stops catching a sub-repo PR cadence (regression to a substring check), or
    it now also rejects the real production text (over-tightened).
    """
    inverting_text = _norm(
        "Each coding node now opens exactly one PR of its own before advancing. Exactly ONE PR "
        "per REPO per run still holds for the land tail - N repos = N integrate nodes = N PRs - "
        "and no intermediate PR is ever opened outside these, reviewed and gated by "
        "odoo-pr-monitoring before the run advances to the next node."
    )
    # The candidate satisfies every OTHER assertion - that is the whole point of the trap...
    assert _ONE_PR_PER_REPO_RE.search(inverting_text)
    assert re.search(r"(?i)N repos = N `?integrate`? nodes = N PRs", inverting_text)
    assert re.search(r"(?i)no intermediate PR is ever opened", inverting_text)
    assert not _SUB_REPO_CADENCE_RE.search(inverting_text)
    # ...but the actor-relationship guard catches it anyway.
    assert _sub_repo_pr_opener_search(inverting_text), (
        "the sub-repo-PR-opener guard must catch a constructed per-node PR cadence - if this "
        "fails, the guard regressed to a substring check."
    )

    assert not _sub_repo_pr_opener_search(_norm(_skill_body())), (
        "the sub-repo-PR-opener guard fired against the REAL run-harness/SKILL.md text - a false "
        "positive that would block legitimate one-PR-per-repo prose."
    )


def test_one_pr_guard_excludes_negated_and_legitimate_mentions():
    """False-positive regression guard for the two enumerated exclusions.

    (a) A NEGATED mention ("no intermediate PR is ever opened after a node lands") is legitimate
        prose asserting the rule, not violating it - and the negation may sit several words away
        from the unit noun, wider than a fixed-width lookbehind tolerates.
    (b) The terminal `integrate` node IS the one legitimate opener; naming it must never fire.

    Fails if: a future edit narrows either exclusion back to fixed-width adjacency and this real
    prose starts firing again.
    """
    negated = _norm(
        "this is the ONE land mechanism for the whole run - one PR per repo, never one per node "
        "(git-ops open-pr -> odoo-pr-monitoring merge); no local merge into the principal checkout"
    )
    assert not _sub_repo_pr_opener_search(negated), (
        "the guard must not fire on a negated, legitimate mention ('never one per node ... "
        "open-pr ...')."
    )
    legitimate = _norm(
        "the repo's terminal integrate node squashes run-integration and opens ONE PR against the "
        "principal branch"
    )
    assert not _sub_repo_pr_opener_search(legitimate), (
        "the guard must not fire on the terminal `integrate` node - it is the ONE legitimate "
        "per-repo PR opener, and flagging it would force the prose to stop naming its own actor."
    )


# ---------------------------------------------------------------------------
# Rule: ONE node per iteration - the driver never has two dispatches in flight.
#
# Consolidated kernel of the retired topology-value guards. Their whole subject (a value
# describing how several units inside one group relate) died with the grouping layer, but the one
# behavioural fact they carried - the driver dispatches SEQUENTIALLY, so "independent" never
# meant concurrent - is a property of the driver itself and survives unchanged. It is also the
# structural reason no grouping construct can be reintroduced through the back door: a field that
# batches nodes is inert unless the driver's prose says it advances them together.
# ---------------------------------------------------------------------------

_PARALLEL_MISCLAIM_RE = re.compile(
    r"(?i)(all\s+parallel|maximum\s+parallelism|built\s+in\s+parallel)"
)


def test_driver_dispatches_one_node_per_iteration_never_two_in_flight():
    """The driver's dispatch is strictly sequential: ONE node per iteration, never two dispatches
    in flight, and nothing batches or groups nodes to advance them together. Concurrency exists
    only INSIDE a dispatched spawner skill, below the driver.

    Fails if: the sequential-dispatch statement is dropped (which is what would let a batching
    field or a "advance these nodes together" instruction become operative), or if any file claims
    units are dispatched/built in parallel at the driver's level.
    """
    norm = _norm(_skill_body())
    assert re.search(r"(?i)ONE node per iteration", norm), (
        "run-harness must state it dispatches ONE node per iteration."
    )
    assert re.search(r"(?i)NEVER has two dispatches in flight", norm), (
        "run-harness must state the loop NEVER has two dispatches in flight - the fact that makes "
        "any grouping field inert."
    )
    assert re.search(
        r"(?i)nothing here batches, groups, or advances nodes together", norm), (
        "run-harness must explicitly reject batching/grouping nodes to advance them together - "
        "without this sentence a 'batch of READY nodes' instruction is not contradicted anywhere."
    )
    assert re.search(r"(?i)concurrency exists only INSIDE a dispatched spawner skill", norm), (
        "run-harness must locate concurrency BELOW the driver (inside a dispatched spawner), so "
        "'the coder runs work-items in parallel' is not read as licence to batch nodes."
    )
    offenders = []
    for path in sorted(PLUGIN.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for m in _PARALLEL_MISCLAIM_RE.finditer(text):
            offenders.append(f"{path.relative_to(PLUGIN)}: {m.group(0)!r}")
    assert not offenders, (
        "Found phrasing claiming units are dispatched/built 'in parallel' at the driver's level - "
        "the loop dispatches one node at a time (one blocking call), so this would be a false "
        f"claim about the mechanism, not a description of it. Offenders:\n" + "\n".join(offenders)
    )
