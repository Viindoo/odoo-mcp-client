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
# how to end its turn (hand the report back once, last, never send it), naming NO consumer.
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

    The snippet's contract: a git-toolkit agent hands its report back once, last - as the
    `SubagentHandback` message when that tool is in its toolset, else as its FINAL TEXT - and never
    sends it anywhere - it cannot address the context that dispatched it, and a
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
    declaring = "your launcher receives your completion report once, as the last act of your dispatch"
    assert declaring in low, (
        "completion-reporting.md must carry the declaring sentence verbatim - it is the marker "
        "the single-home guard counts"
    )
    for shape in (
        r"never send (?:the|your) report to anyone",
        r"cannot address the [\w-]+ that dispatched you|no agent can address",
        r"(?:is not|never) an instruction to (?:try|use one|use it)",
        r"the only tool call a turn may end on is `subagenthandback`, alone in its own message",
        r"`subagenthandback` is in your toolset\*\* -> call it once with the full report",
        r"otherwise\*\* -> your report is the final text of your turn",
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
# git-nesting-protocol.md N0 - how a git-toolkit launcher collects a child's result, stated
# generically here so a git-toolkit agent never has to reach into the consumer plugin for it.
#
# Measured behavior the rule encodes: the launch tool either HAS a `run_in_background` parameter
# (passing `false` blocks and returns the child's result in-turn at any depth, several such launches
# in one message run concurrently, and a subagent that ends its turn while a child runs is NOT woken
# - the child's notice goes to the main conversation) or has NO such parameter (every launch is
# asynchronous and a launcher that ends its turn IS woken once per child, at any depth). The main
# conversation is notified of every completion in both cases. The rule therefore keys the move on
# the launch tool the agent itself holds - a fact it can read off its own tool surface.
# ---------------------------------------------------------------------------

GIT_NESTING_PROTOCOL = TOOLKIT / "snippets" / "git-nesting-protocol.md"
GIT_PIPELINE_LEAD = TOOLKIT / "agents" / "git-pipeline-lead.md"
GIT_OPS_SKILL = TOOLKIT / "skills" / "git-ops" / "SKILL.md"

_WITH_PARAM_HEAD = "has a `run_in_background` parameter"
_NO_PARAM_HEAD = "has no `run_in_background` parameter"


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


def _n0_section(text: str) -> str:
    """The raw `## N0` section of the nesting protocol ('' when the section is missing)."""
    m = re.search(r"^## N0\b.*?(?=^## )", text, re.M | re.S)
    return m.group(0) if m else ""


def _n0_branches(text: str) -> dict[str, str]:
    """The N0 decision bullets, flattened and lowercased, keyed by which launch-tool fact opens
    them: 'with' (the tool has the parameter), 'without' (it has none), 'none' (no capability)."""
    section = _n0_section(text)
    bullets = [
        _flat(chunk.split("\n\n")[0]) for chunk in re.split(r"\n(?=- \*\*)", section)[1:]
    ]
    branches: dict[str, str] = {}
    for bullet in bullets:
        head = bullet.split("->", 1)[0]
        if _NO_PARAM_HEAD in head:
            branches["without"] = bullet
        elif _WITH_PARAM_HEAD in head:
            branches["with"] = bullet
        elif "no agent-launch capability" in head:
            branches["none"] = bullet
    return branches


def test_nesting_protocol_keys_launch_move_on_launch_tool_parameter():
    """Business rule: a git-toolkit launcher decides how to collect a child's result from the
    launch tool it holds - whether that tool has a `run_in_background` parameter - never from a
    blanket claim. With the parameter it launches with `false` and must never stop while a child
    runs (stopping loses the result to the main conversation); without it, it launches and ends
    its turn to be woken. The old text asserted the second branch for everyone, which strands a
    subagent's child result whenever the tool does carry the parameter."""
    text = GIT_NESTING_PROTOCOL.read_text(encoding="utf-8")
    branches = _n0_branches(text)
    assert set(branches) == {"none", "with", "without"}, (
        "git-nesting-protocol.md N0 must branch on the launch tool the agent holds: no capability, "
        f"a tool that {_WITH_PARAM_HEAD}, a tool that {_NO_PARAM_HEAD} - found {sorted(branches)}"
    )
    with_param, without_param = branches["with"], branches["without"]
    assert "run_in_background: false" in with_param, (
        "the with-parameter branch must tell the launcher to pass `run_in_background: false`"
    )
    assert "never end your turn while a child" in with_param, (
        "the with-parameter branch must forbid ending the turn while a launched child still runs"
    )
    assert "end your turn" in without_param and "woken" in without_param, (
        "the no-parameter branch must state launch-then-end-your-turn and the wake"
    )
    # The unconditional claim may live ONLY inside the branch it is true for.
    whole = _flat(text)
    claim = "every launch is asynchronous"
    assert whole.count(claim) == without_param.count(claim) == 1, (
        f"{claim!r} must appear once, inside the no-parameter branch only - anywhere else it "
        "reads as true for every launcher"
    )


def test_nesting_protocol_states_subagent_dispatch_physics():
    """git-nesting-protocol.md must state, generically (no consumer, no domain), every rule a
    git-toolkit launcher needs to collect a child's result on any surface:

      - read your own toolset first; with no launch capability do the work yourself or return
        BLOCKED, and never report a dispatch you could not make;
      - with the parameter: concurrency by several launches in ONE message, the parameter always
        passed (its default is asynchronous), and the consequence of stopping early (nothing wakes
        the agent; the result goes to the main conversation);
      - without it: the wake is depth-independent, and a launcher that keeps working in the
        launching turn never stops, so it never receives anything;
      - an async receipt while holding the parameter is waited for IN the turn;
      - the main conversation resumes a nested launcher instead of acting on its child's result;
      - never re-launch a running child, never end a turn with uncommitted work.

    OLD INTENT -> NEW INTENT. This test used to require the opposite of the first measured branch:
    "every launch is asynchronous", "no foreground or blocking parameter exists", and "woken with
    that child's result ... whether you are the top-level context or a dispatched agent" - stated
    for every launcher. Measurement refuted that for a launch tool that carries
    `run_in_background` (a subagent that stops is not woken there). The intent kept is the same -
    a LOCAL, domain-agnostic statement of the dispatch physics, so a provider never reaches into a
    consumer's snippet - now pinned to the corrected, tool-keyed rule.
    """
    assert GIT_NESTING_PROTOCOL.is_file(), f"missing {GIT_NESTING_PROTOCOL}"
    text = GIT_NESTING_PROTOCOL.read_text(encoding="utf-8")
    low = _flat(text)
    n0 = _flat(_n0_section(text))
    branches = _n0_branches(text)
    assert n0, "git-nesting-protocol.md must carry the `## N0` launch-and-collect section"

    # (1) capability check first, and the no-capability fallback.
    assert "read your own toolset" in n0, "N0 must open with checking your own launch tool"
    none = branches.get("none", "")
    assert "do the work yourself" in none and "blocked" in none, (
        "the no-capability branch must say: do the work yourself or return BLOCKED"
    )
    assert "never report a dispatch you could not make" in none, (
        "the no-capability branch must forbid claiming a dispatch that could not be made"
    )

    # (2) with the parameter: in-turn collection, concurrency, the default, the consequence.
    with_param = branches.get("with", "")
    for needle, why in (
        ("inside your own turn", "the blocking launch returns the result inside the turn"),
        ("one message", "independent children go in ONE message to run concurrently"),
        ("always pass the parameter", "the parameter's default is asynchronous - always pass it"),
        ("main conversation", "stopping early sends the child's result to the main conversation"),
    ):
        assert needle in with_param, f"with-parameter branch: {why}"

    # (3) without it: the wake at any depth, once per child, and the never-stop failure mode.
    without_param = branches.get("without", "")
    for needle, why in (
        ("once per child", "the launcher is woken once per child"),
        ("dispatched agent yourself", "the wake must hold for a dispatched launcher too"),
        ("you never stop", "keep working after launching and nothing is handed back"),
    ):
        assert needle in without_param, f"no-parameter branch: {why}"

    # (4) the async-receipt rule and the main-conversation rule, both outside the branches.
    receipt = re.search(r"an async receipt while you hold the parameter\.(.*?)(?=\*\*the main)", n0)
    assert receipt and "do not end your turn" in receipt.group(1), (
        "N0 must say an async receipt received while holding the parameter is waited for in the "
        "turn - do NOT end your turn"
    )
    assert "resume that agent" in n0 and "by its id" in n0, (
        "N0 must tell the main conversation to resume the nested launcher (send it a message by "
        "its id) rather than act on that launcher's child result itself"
    )

    # (5) the standing prohibitions.
    assert "never re-launch a child that is still running" in n0
    assert "never end a turn with uncommitted work" in n0

    # (6) refuted wording stays deleted, anywhere in the file.
    for gone, why in (
        ("no foreground or blocking parameter exists", "refuted: the tool may carry one"),
        ("whether you are the top-level context", "refuted as a blanket wake guarantee"),
        ("can never be misdelivered", "refuted: an early stop sends the result to main"),
        ("background/foreground switch", "retired earlier wording must stay deleted"),
        ("may never be woken", "retired earlier wording must stay deleted"),
        ("do not launch-and-park", "retired earlier wording must stay deleted"),
    ):
        assert gone not in low, f"{gone!r}: {why}"

    # Genericity: reuse the SAME independence matcher the whole-provider scan below runs, scoped
    # to this one file, so this stays a true companion (not a second, drifting detector).
    pattern = _forbidden_re(_consumer_names())
    violations = _scan(GIT_NESTING_PROTOCOL, pattern)
    assert not violations, (
        "git-nesting-protocol.md's dispatch-physics section names an odoo-ai-agents artifact - "
        "it must stay domain-agnostic:\n" + "\n".join(violations)
    )


def test_git_toolkit_launchers_point_at_n0_without_restating_it():
    """The two places a git-toolkit launch happens - git-pipeline-lead (the only spawning agent)
    and the git-ops skill (which runs in the main conversation OR inside a dispatched agent) -
    must route the collect step to N0 and condition it on their own launch tool, never restate a
    blanket async claim of their own (a second copy is what rotted last time)."""
    for path in (GIT_PIPELINE_LEAD, GIT_OPS_SKILL):
        low = _flat(path.read_text(encoding="utf-8"))
        assert "git-nesting-protocol.md" in low and "n0" in low, (
            f"{path.name} must point the collect step at git-nesting-protocol.md N0"
        )
        assert "run_in_background" in low, (
            f"{path.name} must say the launch tool's own `run_in_background` parameter decides"
        )
        assert "every launch is asynchronous" not in low, (
            f"{path.name} restates the blanket async claim - point at N0 instead"
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
