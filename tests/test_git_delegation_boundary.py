"""Guard: odoo-ai-agents must route all git/GitHub work through the git-toolkit ``git-ops`` skill.

Business rule (the seam this file protects): git-toolkit is the ONLY plugin allowed to
execute git mutations, call the ``gh`` CLI, or invoke GitHub MCP tools. A consumer skill
that needs a git/GitHub operation MUST INVOKE the ``git-toolkit:git-ops`` skill via the Skill
tool (git-ops then classifies the op and runs it on the right git agent under the safety
contract). Consumers NO LONGER name or cold-spawn the git leaf agents (git-operator,
git-surveyor, github-operator, git-pipeline-lead) directly via the Agent tool.

Two complementary boundaries are enforced here:

A. NO INLINE EXECUTION (``test_no_git_delegation_bypass``) - a consumer must not run a git
   mutation, a ``gh`` call, or a GitHub MCP tool inline in a code span (only bounded reads
   and own-worktree ``add``/``commit``/``stash`` may appear inline). Scanned in code spans.

B. NO DIRECT AGENT DISPATCH (``test_no_direct_git_agent_dispatch``) - a consumer must not
   cold-spawn one of the git leaf agents as a ``subagent_type`` dispatch; it must invoke the
   git-ops skill instead. Scanned in prose + code spans of the CONSUMER skills.

FP-avoidance choices (do NOT loosen these without an accompanying test update):

1. CODE SPANS ONLY (boundary A) - inline backtick spans AND fenced ````` blocks are scanned;
   plain prose is NOT. Prevents flagging English words like "commit", "push", "merge",
   "branch" in descriptive sentences ("each commit is replayed ...", "the feature branch").

2. GENERATED REGIONS SKIPPED - content between
   ``<!-- BEGIN GENERATED ... -->`` / ``<!-- END GENERATED ... -->`` markers is excluded
   (both boundaries). Generated regions are MCP tool descriptions emitted by ``make gen``.

3. HYPHEN BOUNDARY - ``\\bgit\\s+`` (space, not zero-width) never matches ``git-operator``,
   ``git-surveyor``, ``git-toolkit`` (hyphen, no space after "git"). ``git -C <path>`` form
   is explicitly handled.

4. GH CLI CHECK - ``gh `` (trailing space) is required, so ``github``, ``ghci``, and path
   segments like ``.github/`` never match.

5. git-toolkit EXCLUDED - the plugin that legitimately wraps raw git (and whose OWN ``git-ops``
   skill legitimately dispatches the git leaf agents) is not in the scan scope; its agents are
   the target delegates, not the source of violations.

6. AGENT-DISPATCH PROHIBITION SCOPED TO CONSUMER SKILLS (boundary B) - the prose scan covers
   ``skills/``, ``snippets/`` and ``commands/`` but NOT ``agents/``. The git leaf-worker agents
   live in git-toolkit (already out of scope); the odoo-ai-agents leaf-worker agents are
   git-free (they declare "NEVER run git commands") and only DESCRIBE the orchestrator's
   pre-step. The dispatch DECISION - the thing the new seam governs - is made by the consumer
   SKILL, so that is where the prohibition is enforced. Boundary A still covers ``agents/``.

7. DISPATCH != MENTION (boundary B) - a git leaf agent may still be NAMED informationally
   (e.g. the "what git-ops resolves the op to" reference table in snippets/git-delegation.md,
   or "git-operator owns the worktree lifecycle"). Only an ACTIVE dispatch of a leaf agent is a
   violation, in ANY of three forms: (i) a ``dispatch``/``spawn`` verb taking a leaf agent as
   its direct object; (ii) a delegation verb (``delegate`` / ``route`` / ``hand off`` /
   ``defer``) handing an op off TO a leaf agent (e.g. "delegate the cherry-pick to
   git-operator", "route the push to github-operator"); OR (iii) a leaf-agent name co-occurring
   on one line with an explicit cold-spawn mechanism token (``subagent_type`` / ``Agent tool`` /
   ``cold-spawn``). An informational mention that carries NO dispatch/delegation verb and NO
   mechanism token - a resolution-table cell ``| Local mutation ... | git-operator |``, the
   gloss "git-operator owns the worktree lifecycle" - is NOT flagged. (The delegation-verb form
   (ii) was previously the soft form left unflagged; it is now caught so a future regression
   cannot reintroduce direct leaf coupling by phrasing it as "delegate ... to <agent>".)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"


# ---------------------------------------------------------------------------
# File discovery
# skills/** is recursive (includes references/, evals/, etc. subdirectories).
# agents/commands/snippets are also scanned recursively to catch any nested
# files, though in practice they are currently flat.
# docs/ is intentionally OUT of scan scope (human-reference material; see F8
# in the review - violations there do not constitute a runnable bypass since
# the scanner guards author-facing prose, not documentation).
# ---------------------------------------------------------------------------

def _md_files() -> list[Path]:
    """All odoo-ai-agents authored markdown (boundary A: inline-execution scan)."""
    files: list[Path] = []
    for subdir in ("skills", "agents", "commands", "snippets"):
        d = AGENTS_PLUGIN / subdir
        if d.exists():
            files.extend(d.rglob("*.md"))
    return sorted(set(files))


def _consumer_skill_files() -> list[Path]:
    """Consumer-skill markdown (boundary B: agent-dispatch scan).

    Excludes agents/ - see FP-avoidance #6: the dispatch DECISION belongs to the consumer
    SKILL, and the leaf-worker agent docs are git-free / informational.
    """
    files: list[Path] = []
    for subdir in ("skills", "snippets", "commands"):
        d = AGENTS_PLUGIN / subdir
        if d.exists():
            files.extend(d.rglob("*.md"))
    return sorted(set(files))


# ---------------------------------------------------------------------------
# Generated-region detection
# Lines inside <!-- BEGIN GENERATED ... --> / <!-- END GENERATED ... --> are
# excluded from scanning; they are never authored prose.
# ---------------------------------------------------------------------------

_GENERATED_RE = re.compile(
    r"<!--\s*BEGIN GENERATED\b.*?-->(.*?)<!--\s*END GENERATED\b.*?-->",
    re.DOTALL | re.IGNORECASE,
)


def _generated_line_ranges(text: str) -> list[tuple[int, int]]:
    """Return inclusive (start_line, end_line) 1-based ranges covering each generated region."""
    ranges: list[tuple[int, int]] = []
    for m in _GENERATED_RE.finditer(text):
        s = text.count("\n", 0, m.start()) + 1
        e = text.count("\n", 0, m.end()) + 1
        ranges.append((s, e))
    return ranges


def _in_generated(line_no: int, regions: list[tuple[int, int]]) -> bool:
    return any(s <= line_no <= e for s, e in regions)


# ---------------------------------------------------------------------------
# Code-span extraction
# Fenced blocks (``` / ~~~) take precedence; inline spans are found only in
# regions that are NOT already inside a fenced extent.
# ---------------------------------------------------------------------------

# Fenced code block: optional leading whitespace, opening fence (3+ backticks
# or tildes), optional lang tag, content, closing fence (same indent + same
# fence chars). Group 1 = leading whitespace; group 2 = fence marker; group 3
# = content. The leading-whitespace capture ensures INDENTED fenced blocks are
# scanned - previously anchoring at column 0 allowed a future regression to
# silently bypass the guard by placing a forbidden command in an indented fence.
_FENCED_RE = re.compile(
    r"^([ \t]*)(`{3,}|~{3,})[^\n]*\n(.*?)^\1\2[ \t]*\n?",
    re.MULTILINE | re.DOTALL,
)

# Inline code span: single backtick (not preceded/followed by another backtick),
# content that does not cross a newline.
# (?<!`) / (?!`) prevent matching into triple-backtick fence markers.
_INLINE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")


def _code_spans(text: str) -> list[tuple[int, str]]:
    """Return (char_offset_of_first_content_char, span_content) for all code spans.

    char_offset is used to compute 1-based line numbers via text.count("\\n", 0, offset)+1.
    Fenced blocks are enumerated first and their byte extents recorded so that
    inline-backtick matching never re-processes content already inside a fence.
    """
    spans: list[tuple[int, str]] = []
    fenced_extents: list[tuple[int, int]] = []

    for m in _FENCED_RE.finditer(text):
        fenced_extents.append((m.start(), m.end()))
        spans.append((m.start(3), m.group(3)))  # group 3 = content (groups 1+2 are indent+fence)

    for m in _INLINE_RE.finditer(text):
        if not any(s <= m.start() < e for s, e in fenced_extents):
            spans.append((m.start(1), m.group(1)))

    return spans


# ---------------------------------------------------------------------------
# Boundary A: inline-execution detection
# ---------------------------------------------------------------------------

# Git verbs that are ALWAYS safe regardless of additional arguments.
_ALWAYS_ALLOWED: frozenset[str] = frozenset({"status", "rev-parse", "merge-base"})

# gh CLI: trailing space required to distinguish from "github", "ghci", ".github/", etc.
_GH_RE = re.compile(r"\bgh\s")

# GitHub MCP tools: the full qualified tool-call prefix.
_GITHUB_MCP_RE = re.compile(r"\bmcp__plugin_github_github__\w+")

# git command token: handles both plain `git <verb>` and `git -C <path> <verb>`.
# [a-z][a-z-]* captures hyphenated verbs like "merge-base", "rev-parse"
# so that `merge` and `merge-base` are distinct verbs and "git-operator" (no
# space) is never matched.
_GIT_RE = re.compile(r"\bgit(?:\s+-C\s+\S+)?\s+([a-z][a-z-]*)")


def _git_allowed(verb: str, line: str) -> bool:
    """Return True iff this `git <verb>` invocation is in the bounded-read allowlist.

    Bounded-read allowlist (may appear inline in code spans):
      status                            - always safe
      rev-parse [...]                   - always safe (read SHA/ref)
      merge-base [...]                  - always safe (read common ancestor)
      branch --show-current             - read current branch name
      remote get-url [...]              - read remote URL
      worktree list                     - list only (not add/remove)
      diff (--stat|--name-only|--shortstat|--quiet|--check)  - bounded output
      log (--oneline | -n<digits>)      - bounded output
      show --stat                       - header+stat only (not full patch)

    Benign own-worktree writes (may appear inline - see "Benign local writes" in
    snippets/git-delegation.md; only valid in a dedicated worker worktree):
      add, commit, stash

    Everything else is a violation requiring routing through git-toolkit:git-ops.
    """
    if verb in _ALWAYS_ALLOWED:
        return True
    if verb == "branch":
        # Only the current-branch read is safe; listing, creating, or deleting are not.
        return "--show-current" in line
    if verb == "remote":
        # Only the URL read is safe; `remote add/remove/set-url` are mutations.
        return "get-url" in line
    if verb == "worktree":
        # `git worktree list` is safe; `add` / `remove` / `prune` are mutations.
        # Use a word boundary so "list" != "listall" etc.
        return bool(re.search(r"\bgit\s+worktree\s+list\b", line))
    if verb == "diff":
        # Bounding flags that limit output to a summary or boolean exit code.
        # A bare `git diff <ref>` (no bounding flag) is unbounded -> violation.
        return any(f in line for f in ("--stat", "--name-only", "--shortstat", "--quiet", "--check"))
    if verb == "log":
        # Accept -n<digits>, -n <digits>, -n<placeholder> (e.g. -n<N>), or --oneline.
        # A bare `git log <range>` or `git log --no-merges` without a count/format
        # bound is unbounded -> violation.
        return bool(re.search(r"-n\s*(?:\d+|<\w+>)|--oneline\b", line))
    if verb == "show":
        # `git show --stat` is bounded (header + stat only).
        # `git show <sha>` (full patch) is unbounded -> violation.
        return "--stat" in line
    if verb in ("add", "commit", "stash"):
        # Benign own-worktree writes - allowed per "Benign local writes" in
        # git-delegation.md. Valid only when the agent is in its own dedicated
        # worktree (S9-satisfied by construction); static analysis cannot enforce
        # the worktree scoping so the policy is documented in prose.
        return True
    # All other verbs (push, fetch, pull, rebase, merge, cherry-pick, checkout,
    # switch, reset, tag, apply, format-patch, range-diff,
    # worktree-add, branch-delete, ...) are mutations or unbounded reads.
    return False


def _scan_file(f: Path) -> list[str]:
    """Return formatted boundary-A (inline-execution) violation strings for one file."""
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(REPO_ROOT))
    gen_regions = _generated_line_ranges(text)
    violations: list[str] = []

    for span_start, span_content in _code_spans(text):
        base_line = text.count("\n", 0, span_start) + 1
        for offset, raw_line in enumerate(span_content.splitlines()):
            line_no = base_line + offset
            if _in_generated(line_no, gen_regions):
                continue

            # --- gh CLI (always forbidden) ---
            if _GH_RE.search(raw_line):
                ctx = raw_line.strip()[:90]
                violations.append(f"{rel}:{line_no}: gh CLI  [{ctx!r}]")

            # --- GitHub MCP tool (always forbidden) ---
            for m in _GITHUB_MCP_RE.finditer(raw_line):
                violations.append(f"{rel}:{line_no}: GitHub MCP  [{m.group()!r}]")

            # --- git command (allowlist filter) ---
            # Dedup per line per verb to avoid double-reporting the same verb
            # appearing twice on one line (e.g. `git push && git push`).
            seen_verbs: set[str] = set()
            for m in _GIT_RE.finditer(raw_line):
                verb = m.group(1)
                if verb in seen_verbs:
                    continue
                seen_verbs.add(verb)
                if not _git_allowed(verb, raw_line):
                    ctx = raw_line.strip()[:80]
                    violations.append(f"{rel}:{line_no}: git {verb}  [{ctx!r}]")

    return violations


# ---------------------------------------------------------------------------
# Boundary B: direct git-agent dispatch detection
#
# The new seam: a consumer skill must INVOKE git-toolkit:git-ops via the Skill tool, NOT
# cold-spawn a git leaf agent via the Agent tool. A leaf agent may be NAMED informationally
# (FP-avoidance #7); only an ACTIVE cold-spawn is a violation.
# ---------------------------------------------------------------------------

# The four git-toolkit leaf agents. The `\b` boundaries + explicit alternation keep
# "git-operator" from matching inside "github-operator" (after "git" comes "h", not "-").
_LEAF_AGENT_RE = re.compile(
    r"\b(?:git-operator|git-surveyor|github-operator|git-pipeline-lead)\b"
)

# Explicit cold-spawn MECHANISM tokens. Presence of one of these on the SAME line as a leaf
# agent name is an active cold-spawn (e.g. "... github-operator (cold-spawn via the Agent
# tool ...)", '... subagent_type: "git-operator" ...'). NOTE: "dispatch" is deliberately NOT
# a token here - on its own it is too common; it only counts when it directly governs a leaf
# agent (see _DIRECT_DISPATCH_RE), so that "delegates ... to git-operator before dispatching
# the worker" does NOT trip on the unrelated "dispatching".
_COLDSPAWN_TOKEN_RE = re.compile(r"subagent_type|Agent\s+tool|cold-?spawn", re.IGNORECASE)

# A dispatch/spawn verb taking a leaf agent as its DIRECT OBJECT. Allows optional
# "git-toolkit's", determiners ("a/the/one/fresh/new"), and markdown/quote wrappers
# (``**name**``, `` `name` ``) between the verb and the agent name. Does NOT allow arbitrary
# nouns, so "dispatch the worker via git-surveyor" (git-surveyor is object of "via", not the
# dispatch) does not match.
_DIRECT_DISPATCH_RE = re.compile(
    r"\b(?:re-?)?(?:dispatch|spawn)(?:es|ing|ed|s)?\s+"
    # ReDoS-safe: a single decoration char per outer `*` iteration (no inner `+`
    # nested inside the outer `*`), so no exponential backtracking. Matches the
    # same strings - a run of N decoration chars is consumed as N outer iterations.
    r"(?:(?:a|an|the|one|fresh|new|git-toolkit'?s?)\s+|[*`\"'(])*"
    r"(?:git-operator|git-surveyor|github-operator|git-pipeline-lead)\b",
    re.IGNORECASE,
)

# A delegation verb handing an op off TO a leaf agent as the named delegate target:
# "delegate the cherry-pick to git-operator", "route the push to github-operator". The git op
# governed by delegate/route/hand-off/defer is what gets dispatched, and the leaf agent is the
# explicit delegate - exactly the direct coupling the git-ops front door removes. This is the
# soft prose form a future regression could reintroduce, so it is now caught alongside the hard
# ``dispatch``/``spawn`` form. FP-avoidance: the gap between the verb and ``to <agent>`` is
# bounded to a SINGLE clause (``[^.;\n]``) so a delegation verb in one clause cannot reach an
# unrelated informational agent mention in another; and an informational table cell or "owns the
# worktree lifecycle" gloss carries NO delegation verb, so it never matches. Determiner/markdown
# wrappers between ``to`` and the agent name are tolerated (mirrors _DIRECT_DISPATCH_RE).
_DELEGATION_DISPATCH_RE = re.compile(
    r"\b(?:re-?)?(?:delegat(?:e|es|ed|ing)|rout(?:e|es|ed|ing)|defer(?:s|red|ring)?"
    r"|hand(?:s|ed|ing)?\s+off)\b"
    r"[^.;\n]*?\bto\s+"
    # ReDoS-safe: a single decoration char per outer `*` iteration (no inner `+`
    # nested inside the outer `*`), so no exponential backtracking. Matches the
    # same strings - a run of N decoration chars is consumed as N outer iterations.
    r"(?:(?:a|an|the|one|fresh|new|git-toolkit'?s?)\s+|[*`\"'(])*"
    r"(?:git-operator|git-surveyor|github-operator|git-pipeline-lead)\b",
    re.IGNORECASE,
)


def _is_agent_dispatch(line: str) -> bool:
    """True if this single line actively dispatches a git leaf agent (boundary B).

    A line is a violation when ANY of:
      - a dispatch/spawn verb takes a leaf agent as its direct object, OR
      - a delegation verb (delegate / route / hand off / defer) hands an op off TO a leaf agent
        as the named delegate (e.g. "delegate the cherry-pick to git-operator"), OR
      - an explicit cold-spawn mechanism token (subagent_type / Agent tool / cold-spawn)
        co-occurs on the line with a leaf-agent name.
    A bare informational mention of a leaf agent (no verb, no token) is NOT a violation.
    """
    if _DIRECT_DISPATCH_RE.search(line):
        return True
    if _DELEGATION_DISPATCH_RE.search(line):
        return True
    if _COLDSPAWN_TOKEN_RE.search(line) and _LEAF_AGENT_RE.search(line):
        return True
    return False


def _scan_file_for_agent_dispatch(f: Path) -> list[str]:
    """Return formatted boundary-B (direct-dispatch) violation strings for one file.

    Scans prose AND code spans (the dispatch instructions live in prose), skipping only
    generated regions.
    """
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(REPO_ROOT))
    gen_regions = _generated_line_ranges(text)
    violations: list[str] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        if _in_generated(i, gen_regions):
            continue
        if _is_agent_dispatch(raw_line):
            ctx = raw_line.strip()[:90]
            violations.append(f"{rel}:{i}: cold-spawns a git leaf agent  [{ctx!r}]")
    return violations


# ---------------------------------------------------------------------------
# The guard tests
# ---------------------------------------------------------------------------

def test_no_git_delegation_bypass():
    """Boundary A: odoo-ai-agents must not EXECUTE git mutations / GitHub-API / unbounded
    reads inline; only bounded reads + own-worktree add/commit/stash may appear in code spans.

    Business rule: git-toolkit holds exclusive authority over git mutations and GitHub API
    ops. odoo-ai-agents skills/agents/commands/snippets must NEVER contain inline git mutations
    or unbounded reads; every such op is routed through the git-toolkit:git-ops skill.

    Allowed inline in code spans (bounded, read-only):
      git status / rev-parse / branch --show-current / remote get-url / merge-base /
      worktree list / diff --stat|--name-only|--shortstat|--quiet|--check /
      log --oneline|-n<digits> / show --stat

    Allowed inline (own-worktree benign writes):
      git add, git commit, git stash  (in a dedicated worker worktree only)

    Forbidden inline (must route through git-ops):
      push, fetch, pull, rebase, merge, cherry-pick, checkout, switch, reset, tag, apply,
      format-patch, range-diff, worktree add/remove, bare git diff <ref>, bare git log
      <range>, git show <sha> (full patch), gh CLI calls, mcp__plugin_github_github__* tools.
    """
    all_violations: list[str] = []
    for f in _md_files():
        all_violations.extend(_scan_file(f))

    n = len(all_violations)
    head = all_violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""

    assert not all_violations, (
        f"odoo-ai-agents: {n} inline git/GitHub reference(s) bypass the git-toolkit "
        f"delegation boundary. Route each through the git-toolkit:git-ops skill (invoke it "
        f"via the Skill tool); git-ops resolves the op to the right git agent and runs it "
        f"under the safety contract. See snippets/git-delegation.md for the allowlist.\n"
        + "\n".join(head)
        + tail
    )


def test_no_direct_git_agent_dispatch():
    """Boundary B (the NEW seam): a consumer skill must INVOKE the git-toolkit:git-ops skill
    via the Skill tool - it must NOT cold-spawn one of the git leaf agents (git-operator,
    git-surveyor, github-operator, git-pipeline-lead) directly as a subagent_type dispatch.

    git-ops itself (in git-toolkit, out of scan scope) is the ONLY place those agents are
    legitimately dispatched. A consumer that writes "dispatch git-operator ..." or
    "github-operator (cold-spawn via the Agent tool)" bypasses the front door and re-couples
    the consumer to git-toolkit's internals.

    Informational mentions remain allowed (FP-avoidance #7): the "what git-ops resolves the op
    to" reference table, "git-operator owns the worktree lifecycle", etc. Only an ACTIVE
    dispatch is a violation: a dispatch/spawn verb governing a leaf agent, a delegation verb
    (delegate/route/hand off/defer) handing an op off TO a leaf agent, OR a leaf-agent name
    co-occurring with a subagent_type / Agent tool / cold-spawn token.
    """
    violations: list[str] = []
    for f in _consumer_skill_files():
        violations.extend(_scan_file_for_agent_dispatch(f))

    n = len(violations)
    head = violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""

    assert not violations, (
        f"odoo-ai-agents: {n} consumer-skill line(s) cold-spawn a git leaf agent directly "
        f"instead of invoking the git-toolkit:git-ops skill. Replace each direct dispatch "
        f"(e.g. 'dispatch git-operator ...') with an INVOCATION of the git-toolkit:git-ops "
        f"skill via the Skill tool, describing the op + scope + worktree + confirmation; "
        f"git-ops resolves and runs it on the right git agent. A leaf agent may still be "
        f"NAMED informationally, just not cold-spawned. See snippets/git-delegation.md.\n"
        + "\n".join(head)
        + tail
    )


def test_agent_dispatch_detection_red_before_green():
    """Self-check that boundary B can FAIL for the right reason (red-before-green).

    Asserts the detector FLAGS genuine cold-spawn constructs and PASSES the new git-ops
    invocation + informational mentions. If this regresses, boundary B has been loosened to
    the point of vacuity and would no longer protect the seam.
    """
    forbidden = [
        # the canonical OLD construct the migration removes
        "Dispatch git-operator via subagent_type to create the integration worktree.",
        "1. Dispatch **github-operator** to fetch PR metadata and the changed file list.",
        "Pre-step: dispatch git-surveyor (read-only, no worktree) to write the commit dump.",
        "delegate to **github-operator** (via Agent tool) with the review body.",
        "Each poll tick, dispatch git-toolkit's `github-operator` (cold-spawn via the Agent tool).",
        'Fan out with `subagent_type: "git-operator"` per work-item.',
        # MED-1: the soft delegation-verb form - a git op handed off TO a leaf agent as the named
        # delegate. Previously left unflagged; now caught so a regression cannot reintroduce direct
        # leaf coupling by phrasing the dispatch as "delegate/route/hand off/defer ... to <agent>".
        "delegate the cherry-pick to git-operator.",
        "route the push to github-operator",
        "hand off the range-diff verification to git-surveyor",
        "Each poll tick, defer the PR read to github-operator.",
        # the same soft form that used to be in `allowed` - now a violation.
        "delegate a bisect run to git-operator in a dedicated worktree.",
    ]
    for line in forbidden:
        assert _is_agent_dispatch(line), f"boundary B should FLAG but did not: {line!r}"

    allowed = [
        # the NEW seam - invoking the skill, never naming a leaf agent as a dispatch target
        "Invoke the `git-toolkit:git-ops` skill via the Skill tool to create a worktree.",
        "Each poll tick, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to READ the PR.",
        # informational mentions of leaf agents (FP-avoidance #7) - allowed: NO dispatch/delegation
        # verb governs the agent, NO cold-spawn token co-occurs.
        "git-ops resolves the op to git-operator for the local mutation and runs it.",
        "| Local mutation - rebase, cherry-pick, merge, commit, push | git-operator |",
        "git-operator owns the worktree lifecycle (S9 invariant).",
        # a delegation verb that hands off to git-OPS (the front door), not to a leaf agent - fine.
        "Route the cherry-pick to git-ops, which resolves it to the right git agent.",
        # dispatching a NON-git agent (e.g. a semantic conflict resolver) is fine
        "Dispatch the odoo-coder agent to edit the conflicted files.",
        # delegating a NON-git op to a non-leaf agent is fine
        "delegate the conflict resolution to odoo-coder in the worktree.",
        # the fork handoff tier is not a git-agent cold-spawn
        'launch one Opus subagent per cluster using `subagent_type: "fork"`.',
    ]
    for line in allowed:
        assert not _is_agent_dispatch(line), f"boundary B should NOT flag but did: {line!r}"


def test_inline_git_detection_red_before_green(tmp_path, monkeypatch):
    """Self-check that boundary A can FAIL for the right reason (red-before-green).

    Boundary A (``test_no_git_delegation_bypass``) previously had NO self-check, so a future edit
    that loosened the allowlist or the scanner could pass silently. This exercises the REAL module
    functions (``_git_allowed`` + ``_scan_file``) on synthetic inputs so any such loosening trips
    here:

      - inline git MUTATIONS (push / cherry-pick / merge / rebase) are NEVER allowed;
      - own-worktree benign writes (add / commit / stash) ARE allowed inline (S9 carve-out);
      - the scanner FLAGS a fenced ``git push origin HEAD`` span and PASSES a bounded
        ``git diff --stat`` read.

    If the allowlist were widened to admit a mutation, or the scanner stopped flagging it, this
    test goes red.
    """
    # --- allowlist: mutations rejected ---
    for verb in ("push", "cherry-pick", "merge", "rebase"):
        assert _git_allowed(verb, f"git {verb} origin HEAD") is False, (
            f"boundary A allowlist must REJECT inline `git {verb}` (it is a mutation)"
        )

    # --- allowlist: own-worktree benign writes accepted ---
    for verb in ("add", "commit", "stash"):
        assert _git_allowed(verb, f"git {verb} .") is True, (
            f"boundary A allowlist must ACCEPT own-worktree `git {verb}` (S9 carve-out)"
        )

    # --- scanner: flag a known-bad fenced span, pass a bounded read ---
    # _scan_file formats violations relative to REPO_ROOT, so point REPO_ROOT at the tmp dir
    # the synthetic fixtures live under (reverted automatically by monkeypatch).
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    bad = tmp_path / "bad-inline-git.md"
    bad.write_text("Example:\n\n```bash\ngit push origin HEAD\n```\n", encoding="utf-8")
    bad_hits = _scan_file(bad)
    assert any("git push" in h for h in bad_hits), (
        f"scanner must FLAG a fenced `git push origin HEAD` span; got {bad_hits!r}"
    )

    good = tmp_path / "good-inline-git.md"
    good.write_text("Bounded read:\n\n```bash\ngit diff --stat\n```\n", encoding="utf-8")
    good_hits = _scan_file(good)
    assert good_hits == [], (
        f"scanner must PASS a bounded `git diff --stat` read; got {good_hits!r}"
    )
