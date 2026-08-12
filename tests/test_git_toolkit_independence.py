r"""Guard: git-toolkit is domain-agnostic and MUST NOT name odoo-ai-agents.

Business rule (dependency direction): git-toolkit is a domain-agnostic PROVIDER
library (Apache-2.0). As a provider it must not know, name, or point into its
CONSUMER plugin odoo-ai-agents. References in the OTHER direction
(odoo-ai-agents -> git-toolkit) are legal and are guarded by
``test_git_delegation_boundary.py``. This test is the exact inverse: it scans
ONLY ``plugins/git-toolkit/**`` so it structurally cannot touch odoo-ai-agents,
and together the two form a non-overlapping bidirectional guard.

A reference is forbidden when git-toolkit text names any odoo-ai-agents artifact
(the sibling plugin id, or any of its skills / agents / commands) or points into
the consumer-side delegation snippet (``git-delegation.md``). The denylist is
DATA-DRIVEN - derived from the actual basenames under
``plugins/odoo-ai-agents/{skills,agents,commands}`` (mirroring how
``test_naming_consistency.py`` discovers names) - so a newly added consumer skill
is covered automatically with no edit here.

FP-avoidance choices (do NOT loosen these without an accompanying test update):

1. NEVER the bare product noun ``odoo``. The Odoo product (``commit-convention-odoo.md``,
   ``__manifest__.py`` detection, "Odoo-the-product" prose) is legitimate domain
   knowledge for a git tool. Only FULL compound artifact names are forbidden
   (``odoo-git-rebase``, ``odoo-coding``, ...), matched with word boundaries.

2. WORD BOUNDARIES. Each token is matched as ``\bTOKEN\b`` (case-sensitive - artifact
   names are always written lowercase). The hyphen is a non-word char, so
   ``\bodoo-code-review\b`` does NOT match inside ``odoo-code-reviewer`` (which is
   itself a separate denylist token), and the dot-anchored ``git-delegation.md``
   token does NOT match the provider's own ``git-delegation-decision.md``.

3. GENERIC GIT TERMS stay legal. ``forward-port`` / ``backport`` are generic git ops
   git-toolkit performs; only the ``odoo-``-prefixed compound ``odoo-forward-port``
   is forbidden.

4. UNPREFIXED CONSUMER NAMES (``run-harness``, ``workflow-chaining``) are
   included from the skills glob (dirs starting with neither ``odoo-`` nor ``_``).

5. SELF + BINARY skipped. This test file lives outside the scan root by
   construction; non-UTF-8 (binary) files are skipped defensively.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"

# git-toolkit's OWN, provider-agnostic completion-reporting snippet: it tells a git-toolkit agent
# how to end its turn (emit the report as its final message, never send it), naming NO consumer.
# Guarded for existence + anchors here; the independence scan below additionally proves it names no
# odoo-ai-agents artifact.
COMPLETION_REPORTING = TOOLKIT / "snippets" / "completion-reporting.md"

# The consumer-side delegation snippet filename. Distinct from the provider's own
# ``git-delegation-decision.md`` - forbidding this token must NOT flag that file
# (see FP-guard #2: the token is dot-anchored).
DELEGATION_SNIPPET = "git-delegation.md"
SIBLING_PLUGIN = "odoo-ai-agents"


# ---------------------------------------------------------------------------
# Data-driven denylist
# Mirrors test_naming_consistency.py: names are directory/file basenames under
# plugins/odoo-ai-agents/{skills,agents,commands}. Globbing keeps the denylist
# in sync with the consumer automatically (ETHOS #11 data-driven).
# ---------------------------------------------------------------------------

def _consumer_names() -> set[str]:
    names: set[str] = set()
    for skill in AGENTS_PLUGIN.glob("skills/*/SKILL.md"):
        names.add(skill.parent.name)
    for md in AGENTS_PLUGIN.glob("agents/*.md"):
        names.add(md.stem)
    for md in AGENTS_PLUGIN.glob("commands/*.md"):
        names.add(md.stem)
    # Drop shared/private dirs (e.g. _shared) - not addressable artifacts.
    names = {n for n in names if not n.startswith("_")}
    # Plus the literals: the sibling plugin id and the consumer delegation snippet.
    names.add(SIBLING_PLUGIN)
    names.add(DELEGATION_SNIPPET)
    return names


def _forbidden_re(names: set[str]) -> re.Pattern[str]:
    """Compile an alternation of word-bounded, literal-escaped denylist tokens.

    Sorted longest-first so the regex engine reports the most specific token at a
    position. ``\\b`` on both ends + ``re.escape`` make each token a literal that
    only matches the full compound name (never the bare ``odoo`` product noun and
    never a longer superstring like ``odoo-code-reviewer`` for ``odoo-code-review``).
    """
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"\b(?:" + alt + r")\b")


# ---------------------------------------------------------------------------
# File discovery + scan (provider side only)
# ---------------------------------------------------------------------------

_SELF = Path(__file__).resolve()


def _text_files() -> list[Path]:
    files: list[Path] = []
    for p in sorted(TOOLKIT.rglob("*")):
        if not p.is_file():
            continue
        if p.resolve() == _SELF:  # never scan this test (defensive; it is outside TOOLKIT)
            continue
        files.append(p)
    return files


def _scan(path: Path, pattern: re.Pattern[str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # skip binary / unreadable
    rel = path.relative_to(REPO_ROOT)
    hits: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in pattern.finditer(line):
            hits.append(f"{rel}:{n}: {m.group()}  [{line.strip()[:90]!r}]")
    return hits


# ---------------------------------------------------------------------------
# In-test self-checks: the matcher must flag a real consumer name and spare
# the bare product noun / generic git terms / the provider's own snippet.
# These fail for the RIGHT reason if a future edit weakens the matcher.
# ---------------------------------------------------------------------------

def test_matcher_flags_consumer_name_and_spares_generics():
    pattern = _forbidden_re(_consumer_names())

    # FLAGS a real, full consumer artifact name embedded in prose.
    assert pattern.search("see the odoo-coding skill for details"), (
        "matcher must flag a full odoo-ai-agents artifact name"
    )
    assert pattern.search("delegated via odoo-ai-agents/snippets/git-delegation.md"), (
        "matcher must flag the consumer plugin id and the delegation snippet"
    )

    # Does NOT flag the bare product noun ``odoo`` (legitimate domain knowledge).
    assert not pattern.search("detect an Odoo repo via __manifest__.py"), (
        "matcher must NOT flag the bare Odoo product noun"
    )
    assert not pattern.search("odoo commit-convention support"), (
        "matcher must NOT flag the bare lowercase odoo product noun"
    )

    # Does NOT flag generic git ops that merely share a suffix with a consumer name.
    assert not pattern.search("a forward-port of 60 commits"), (
        "matcher must NOT flag the generic git op forward-port"
    )
    assert not pattern.search("backport the fix to v16"), (
        "matcher must NOT flag the generic git op backport"
    )

    # Does NOT flag the provider's OWN snippet (dot-anchored token boundary).
    assert not pattern.search("${ROOT}/snippets/git-delegation-decision.md"), (
        "matcher must NOT flag the provider's own git-delegation-decision.md"
    )


def test_denylist_is_populated():
    names = _consumer_names()
    # Sanity: the glob actually discovered the consumer's artifacts.
    assert "odoo-coding" in names, "expected odoo-coding skill in the data-driven denylist"
    assert SIBLING_PLUGIN in names and DELEGATION_SNIPPET in names
    assert "_shared" not in names, "private/shared dirs must be excluded"


def test_completion_reporting_snippet_exists():
    """git-toolkit's completion-reporting SSOT snippet must exist and carry its anchor tokens.

    The snippet's contract: a git-toolkit agent ends its turn by emitting its report as its FINAL
    MESSAGE and never sending it anywhere - it cannot address the context that dispatched it, and a
    messaging tool being in its toolset is not an instruction to try. The anchors guard exactly
    that. This complements the independence scan: that test proves the snippet names no consumer,
    this one proves the snippet still says what it must (the two together stop it from being
    silently emptied OR quietly re-coupled to a consumer).
    """
    assert COMPLETION_REPORTING.is_file(), f"missing SSOT snippet {COMPLETION_REPORTING}"
    body = COMPLETION_REPORTING.read_text(encoding="utf-8")
    low = " ".join(body.split()).lower()
    # The first entry is asserted verbatim ON PURPOSE: it is the identity marker
    # test_return_path_contract.py counts to prove the rule has exactly one home per plugin.
    # The rest are SHAPES, so a rewording that preserves the rule still passes.
    assert "your completion report is the final text of your turn" in low, (
        "completion-reporting.md must carry the declaring sentence verbatim - it is the marker "
        "the single-home guard counts"
    )
    for shape in (
        r"never send (?:the|your) report to anyone",
        r"cannot address the [\w-]+ that dispatched you|no agent can address",
        r"(?:is not|never) an instruction to (?:try|use one|use it)",
        r"never end a turn on a bare tool call",
    ):
        assert re.search(shape, low), (
            f"completion-reporting.md: no text matches the required rule shape {shape!r}"
        )
    for banned in ("SendMessage", "TaskUpdate", 'to: "main"'):
        assert banned not in body, (
            f"completion-reporting.md must not name {banned!r} - there is no upward channel, and "
            "naming the tool is what made an agent look for one"
        )


def test_git_toolkit_leaf_allowlists_grant_no_messaging_tool():
    """A hard leaf launches nothing, so it holds no legal send target. Listing a messaging tool in
    its `tools:` allowlist is worse than useless: the model calls it and errors instead of cleanly
    falling back to its final message. Data-driven over every git-toolkit agent that declares a
    `tools:` list."""
    offenders = []
    for agent in sorted((TOOLKIT / "agents").glob("*.md")):
        body = agent.read_text(encoding="utf-8")
        m = re.search(r"^tools:\s*\[(.*?)\]\s*$", body, re.MULTILINE | re.DOTALL)
        if not m:
            continue  # inherits the full surface - not an allowlist decision
        allowlist = m.group(1)
        for banned in ("SendMessage", "TaskUpdate"):
            if banned in allowlist:
                offenders.append(f"{agent.name}: tools: grants {banned}")
    assert not offenders, (
        "git-toolkit agents with a `tools:` allowlist must grant no messaging tool:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# github-operator.md: the PR-review inline-findings fan-out recipe (P3) is
# documented AND remains self-contained (no odoo-ai-agents artifact/path).
# ---------------------------------------------------------------------------

GITHUB_OPERATOR = TOOLKIT / "agents" / "github-operator.md"


def test_github_operator_documents_inline_findings_fanout_recipe():
    """github-operator.md must document the create -> loop -> submit_pending fan-out.

    Business rule: when an orchestrator hands github-operator a LIST of findings, it must
    post ONE inline comment per finding - never collapse to a single flat comment. The
    documented sequence is: open a pending review ONCE (`create`, no `event`), call
    `add_comment_to_pending_review` once per finding (subjectType LINE, a `suggestion`
    fence in the body when a fix exists), then finalize ONCE via `submit_pending`. This
    guards the sequence itself, not just the tool names in isolation.
    """
    text = GITHUB_OPERATOR.read_text(encoding="utf-8")
    assert "## PR review with inline findings" in text, (
        "github-operator.md is missing the '## PR review with inline findings (fan-out)' "
        "recipe section"
    )
    assert re.search(r'method:\s*"create"', text), (
        "github-operator.md does not document opening the pending review via "
        "pull_request_review_write method: \"create\""
    )
    assert "add_comment_to_pending_review" in text and "subjectType" in text, (
        "github-operator.md does not document the per-finding "
        "add_comment_to_pending_review call with a subjectType"
    )
    assert "submit_pending" in text, (
        "github-operator.md does not document finalizing the review via submit_pending"
    )
    assert "never `APPROVE`" in text or "never APPROVE" in text, (
        "github-operator.md does not forbid an automated review from ever submitting APPROVE"
    )
    assert "subjectType: \"FILE\"" in text, (
        "github-operator.md does not document the FILE-level fallback for a finding whose "
        "line cannot be anchored in the PR diff"
    )
    assert "DONE_WITH_CONCERNS" in text and re.search(
        r"never\s+silently collapse to one flat comment", text
    ), (
        "github-operator.md does not require DONE_WITH_CONCERNS (never a silent collapse to "
        "one flat comment) when the GitHub MCP is unavailable"
    )


def test_github_operator_fanout_recipe_names_no_odoo_ai_agents_artifact():
    """The fan-out recipe itself must stay self-contained (git-toolkit is dependency-free).

    Belt-and-suspenders companion to test_git_toolkit_names_no_odoo_ai_agents_artifact: that
    whole-provider scan already covers this file, but this test pins the guarantee directly
    to the P3 feature so a future refactor of the broader scan cannot silently drop coverage
    of this specific recipe.
    """
    pattern = _forbidden_re(_consumer_names())
    violations = _scan(GITHUB_OPERATOR, pattern)
    assert not violations, (
        "github-operator.md's inline-findings fan-out recipe names an odoo-ai-agents "
        f"artifact - git-toolkit must stay dependency-free:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# git-nesting-protocol.md: M1b - the same subagent-wake physics as odoo-ai-agents' R0
# (spawner-completion-contract.md), stated generically here so a git-toolkit agent never has to
# reach into the consumer plugin for it.
#
# NOTE ON PLACEMENT: the design (12-design-final.md M1b guard) names this test
# `tests/test_commit_convention_gate.py::test_nesting_protocol_states_subagent_wake_physics` -
# that file belongs to a LATER wave (M3/PR2, git-toolkit commit gate) and does not exist yet on
# this branch. This test is placed here instead, in the file that already owns
# git-nesting-protocol.md's other guards (test_completion_reporting_snippet_exists is the sibling
# "does the SSOT snippet still say what it must" pattern this follows) - the wave-2 implementer
# can move it verbatim into test_commit_convention_gate.py once that file exists, with no
# behavior change.
# ---------------------------------------------------------------------------

GIT_NESTING_PROTOCOL = TOOLKIT / "snippets" / "git-nesting-protocol.md"


def test_nesting_protocol_states_subagent_dispatch_physics():
    """M1b (corrected) - git-nesting-protocol.md must state the subagent DISPATCH PHYSICS
    generically (no consumer, no domain, no odoo artifact), matching the corrected ground truth in
    odoo-ai-agents' R0 (spawner-completion-contract.md): a subagent CAN launch a child and CAN
    receive its result - via a blocking launch when the launch tool exposes a background/foreground
    switch. What it CANNOT do is be woken by that child. A background child's completion is
    delivered to the root conversation, never back to a launcher that is itself dispatched, and
    every git-toolkit agent is dispatched - so "end the turn and be resumed" is not a slower
    alternative here, it is a permanent stall with no error and no output. Blocking is therefore
    mandatory, and the no-lever case falls back to doing the work inline or returning BLOCKED. The
    other hazards remain the silent nesting cap (no launch capability at all) and the
    non-interactive surface (never end a turn with uncommitted work).

    This test previously required the OPPOSITE of its (3) assertion - that the file offer the
    async-launch-and-park branch and NOT say a dispatched launcher may never be woken. That
    requirement described the root conversation's physics and applied it to agents that are never
    the root, which is the stall this contract exists to prevent, so it is inverted here.

    Business rule this protects: before this paragraph landed, git-toolkit's own leaf/lead agents
    had no LOCAL statement of the dispatch-physics invariant - the only place it lived was
    odoo-ai-agents' R0, and reaching into a CONSUMER'S snippet from a domain-agnostic PROVIDER
    inverts the dependency direction this whole file guards. The fix states the physics inline,
    generically, so it holds even if git-toolkit is ever consumed by a plugin other than
    odoo-ai-agents.
    """
    assert GIT_NESTING_PROTOCOL.is_file(), f"missing {GIT_NESTING_PROTOCOL}"
    text = GIT_NESTING_PROTOCOL.read_text(encoding="utf-8")
    low = " ".join(text.split()).lower()

    # A dispatched agent CAN block on a child (the blocking-mode branch below asserts it). What it
    # cannot do is be woken by one: a background child's completion is delivered to the root
    # conversation, never back to a launcher that is itself dispatched. So the file must not offer
    # the async park as an alternative shape - every git-toolkit agent is dispatched, so that
    # branch is a permanent stall, not a slower path.
    assert "do the work yourself" in low, (
        "git-nesting-protocol.md must keep the no-launch-capability fallback (do the work "
        "yourself), which is also where a caller lands when no blocking lever exists"
    )

    # RULE, not a string: the capability branch must be expressed -
    # (1) cap-absent handling: read your own toolset before launching, and never report a
    #     dispatch that could not be made.
    assert "read your own toolset" in low or "own toolset" in low, (
        "git-nesting-protocol.md must instruct checking launch capability before dispatching"
    )
    assert "never report a dispatch" in low or (
        "capability is absent" in low and ("blocked" in low or "do the work yourself" in low)
    ), (
        "git-nesting-protocol.md must state what to do when launch capability is absent (do the "
        "work yourself / return BLOCKED) and never claim a dispatch that could not be made"
    )
    # (2) the blocking-launch branch: a background/foreground switch, used in blocking mode when
    #     the caller needs the result inside its own turn. Naming the switch ALONE is not enough -
    #     a mutation that keeps "background/foreground switch" but drops the blocking-mode outcome
    #     (e.g. "pick whichever mode you like") must still be caught, so both must be present.
    assert "background/foreground switch" in low, (
        "git-nesting-protocol.md must name the background/foreground switch capability probe"
    )
    assert "blocking mode" in low and "returns inside your turn" in low, (
        "git-nesting-protocol.md must state the blocking-launch branch's OUTCOME: use blocking "
        "mode to get the result inside the caller's own turn - not merely name the switch"
    )
    # (3) the no-blocking-lever branch: there is NO async-park alternative for a dispatched agent.
    #     The file must say so in consequence terms (a launcher that ends its turn to wait may
    #     never be woken) and route that case to the same do-it-yourself / BLOCKED fallback.
    assert "may never be woken" in low, (
        "git-nesting-protocol.md must state the consequence that makes blocking mandatory: a "
        "dispatched agent that backgrounds a child and ends its turn to wait may never be woken"
    )
    assert "do not launch-and-park" in low, (
        "git-nesting-protocol.md must forbid the launch-and-park shape outright for a dispatched "
        "agent - offering it as an alternative is what strands a whole pipeline silently"
    )
    assert "never poll" in low and "never re-launch" in low, (
        "git-nesting-protocol.md must forbid polling and re-launching - a blocking launch already "
        "returns the result inside the turn, so there is never anything to poll for"
    )
    # (4) the uncommitted-work bound: the non-interactive-surface mitigation.
    assert "never end a turn with uncommitted work" in low, (
        "git-nesting-protocol.md must bound the non-interactive-surface risk: never end a turn "
        "with uncommitted work"
    )

    # Genericity: the paragraph must name no consumer, no domain, no odoo artifact - reuses the
    # SAME independence matcher the whole-provider scan below runs, scoped to this one file, so
    # this stays a true belt-and-suspenders companion (not a second, drifting detector).
    pattern = _forbidden_re(_consumer_names())
    violations = _scan(GIT_NESTING_PROTOCOL, pattern)
    assert not violations, (
        "git-nesting-protocol.md's dispatch-physics paragraph names an odoo-ai-agents artifact - "
        "it must stay domain-agnostic:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

def test_git_toolkit_names_no_odoo_ai_agents_artifact():
    """git-toolkit (domain-agnostic provider) must not name any odoo-ai-agents artifact.

    Business rule: a provider library must not know its consumers by name. Any
    git-toolkit text that names an odoo-ai-agents skill / agent / command, the
    sibling plugin id, or points into the consumer's git-delegation.md violates
    the dependency direction (odoo-ai-agents -> git-toolkit is fine; never the
    reverse). The denylist is derived from the consumer's actual artifact
    basenames, so adding a consumer skill extends the guard automatically.
    """
    pattern = _forbidden_re(_consumer_names())
    violations: list[str] = []
    for f in _text_files():
        violations.extend(_scan(f, pattern))

    n = len(violations)
    head = violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""
    assert not violations, (
        f"git-toolkit: {n} reference(s) to an odoo-ai-agents artifact. git-toolkit is a "
        f"domain-agnostic provider and MUST NOT name its consumers (skills/agents/commands), "
        f"the {SIBLING_PLUGIN!r} plugin, or point into the consumer's {DELEGATION_SNIPPET!r}. "
        f"Genericize the reference (name no consumer) and point only at git-toolkit's own "
        f"snippets.\n" + "\n".join(head) + tail
    )
