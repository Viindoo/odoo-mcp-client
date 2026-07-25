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
   may appear inline; even own-worktree add/commit/stash are forbidden - workers never run git,
   the orchestrator commits via git-ops). Scanned in code spans.

B. NO GIT-TOOLKIT AGENT MENTION (``test_no_git_toolkit_agent_mention``) - a consumer must not
   NAME one of the git-toolkit leaf agents (git-operator, git-surveyor, github-operator,
   git-pipeline-lead) in ANY phrasing - dispatch instruction OR informational aside alike. Only
   ``git-toolkit:git-ops`` may be named. Scanned across the odoo-ai-agents executor-facing prose set.

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

6. MENTION == VIOLATION (boundary B) - the rule is strict: a git-toolkit leaf-agent name must
   NEVER appear in odoo-ai-agents executor-facing prose, because even an informational mention
   gives a runtime executor a specialist name to imitate and dispatch directly. This is a strict
   SUPERSET of the old "no active dispatch" rule (a name that never appears categorically cannot
   be dispatched), so it is implemented as a single presence check - simpler than, and strictly
   stronger than, the retired dispatch/delegation-verb heuristics it replaces. The scan scope now
   covers ``skills/``, ``snippets/``, ``commands/``, ``agents/`` and ``docs/`` markdown PLUS the
   plugin's own ``README.md`` and the ``generator/skill_tool_deps.json`` orchestration SSOT text -
   everything an executing agent may read. ``plugins/git-toolkit/**`` stays out of scope (it
   legitimately owns and names its own 4 agents); the scan never reaches repo-root ``CHANGELOG.md``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"


# ---------------------------------------------------------------------------
# File discovery
# skills/** is recursive (includes references/, evals/, etc. subdirectories).
# agents/commands/snippets are also scanned recursively to catch any nested
# files, though in practice they are currently flat.
# docs/ broadly and CONTRIBUTING.md are OUT of the boundary-A/B scan scope (human-reference
# material; see F8 in the review - CONTRIBUTING.md keeps the manual `git commit -s` human path).
# EXCEPTION: two root-level agent-facing docs that CLAUDE.md mandates agents read/obey - CLAUDE.md
# itself and docs/authoring-skills-and-agents.md - ARE now scanned by
# test_agent_facing_docs_route_git_through_git_ops (via _scan_agent_doc), which flags a raw
# commit/push/gh/GitHub-MCP in a code span but carves out the confidentiality core.hooksPath install.
# ---------------------------------------------------------------------------

def _md_files() -> list[Path]:
    """All odoo-ai-agents authored markdown (boundary A: inline-execution scan)."""
    files: list[Path] = []
    for subdir in ("skills", "agents", "commands", "snippets"):
        d = AGENTS_PLUGIN / subdir
        if d.exists():
            files.extend(d.rglob("*.md"))
    return sorted(set(files))


def _consumer_prose_files() -> list[Path]:
    """odoo-ai-agents executor-facing prose (boundary B: git-toolkit agent-name mention scan).

    Scan scope is everything an executing agent may read: skills/, snippets/, commands/, agents/
    and docs/ markdown, PLUS the plugin's own README.md and the generator/skill_tool_deps.json
    orchestration SSOT text. plugins/git-toolkit/** is deliberately NOT here (it owns its own
    agent names). The two non-*.md paths are appended AFTER the glob loop - the per-subdir
    rglob only picks up *.md - each guarded by .exists().
    """
    files: list[Path] = []
    for subdir in ("skills", "snippets", "commands", "agents", "docs"):
        d = AGENTS_PLUGIN / subdir
        if d.exists():
            files.extend(d.rglob("*.md"))
    for extra in (AGENTS_PLUGIN / "README.md", AGENTS_PLUGIN / "generator" / "skill_tool_deps.json"):
        if extra.exists():
            files.append(extra)
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

    Everything else - including add / commit / stash (workers never run git; the orchestrator
    commits via git-toolkit:git-ops) - is a violation requiring routing through git-toolkit:git-ops.
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
    # add / commit / stash are NO LONGER allowed inline: workers never run git (they write
    # files and return; the orchestrator commits via git-toolkit:git-ops). See the "No worker
    # git" section in snippets/git-delegation.md.
    # All other verbs (add, commit, stash, push, fetch, pull, rebase, merge, cherry-pick,
    # checkout, switch, reset, tag, apply, format-patch, range-diff, worktree-add,
    # branch-delete, ...) are mutations or unbounded reads -> route through git-ops.
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
# Boundary B: git-toolkit leaf-agent NAME MENTION detection
#
# The seam: odoo-ai-agents executor-facing prose must route git work through the
# git-toolkit:git-ops front door and must NEVER NAME a git-toolkit leaf agent - not even as an
# informational aside, because a bare name gives a runtime executor a specialist to imitate.
# A single presence check over _LEAF_AGENT_RE implements this (a strict superset of the old
# active-dispatch-only detector, which is why the verb/mechanism heuristics were retired).
# ---------------------------------------------------------------------------

# The four git-toolkit leaf agents. The `\b` boundaries + explicit alternation keep
# "git-operator" from matching inside "github-operator" (after "git" comes "h", not "-").
_LEAF_AGENT_RE = re.compile(
    r"\b(?:git-operator|git-surveyor|github-operator|git-pipeline-lead)\b"
)


def _scan_file_for_agent_mention(f: Path) -> list[str]:
    """Return formatted boundary-B (leaf-agent-name mention) violation strings for one file.

    Flags ANY line naming a git-toolkit leaf agent - dispatch instruction, table cell, gloss,
    chain diagram, provenance note, all alike - skipping only generated regions. Reads the file
    as raw text so a non-*.md path (the orchestration SSOT JSON) scans identically to markdown.
    """
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(REPO_ROOT))
    gen_regions = _generated_line_ranges(text)
    violations: list[str] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        if _in_generated(i, gen_regions):
            continue
        for m in _LEAF_AGENT_RE.finditer(raw_line):
            ctx = raw_line.strip()[:90]
            violations.append(f"{rel}:{i}: names git-toolkit leaf agent {m.group()!r}  [{ctx!r}]")
    return violations


# ---------------------------------------------------------------------------
# The guard tests
# ---------------------------------------------------------------------------

def test_no_git_delegation_bypass():
    """Boundary A: odoo-ai-agents must not EXECUTE git mutations / GitHub-API / unbounded
    reads inline; only bounded reads may appear in code spans (workers never run git - not even
    add/commit/stash; the orchestrator commits via git-ops).

    Business rule: git-toolkit holds exclusive authority over git mutations and GitHub API
    ops. odoo-ai-agents skills/agents/commands/snippets must NEVER contain inline git mutations
    or unbounded reads; every such op is routed through the git-toolkit:git-ops skill.

    Allowed inline in code spans (bounded, read-only):
      git status / rev-parse / branch --show-current / remote get-url / merge-base /
      worktree list / diff --stat|--name-only|--shortstat|--quiet|--check /
      log --oneline|-n<digits> / show --stat

    Forbidden inline (must route through git-ops):
      add, commit, stash, push, fetch, pull, rebase, merge, cherry-pick, checkout, switch,
      reset, tag, apply, format-patch, range-diff, worktree add/remove, bare git diff <ref>, bare git log
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


def test_no_git_toolkit_agent_mention():
    """Boundary B (the seam): odoo-ai-agents executor-facing prose must route git work through
    the git-toolkit:git-ops front door and must contain ZERO occurrences of a git-toolkit leaf
    agent name (git-operator, git-surveyor, github-operator, git-pipeline-lead), in ANY phrasing -
    dispatch instruction or informational aside alike. Only ``git-toolkit:git-ops`` may be named.

    This is a strict superset of the retired "no active dispatch" rule: a name that never appears
    categorically cannot be dispatched, so the observable contract - an executing agent never sees
    a git-toolkit leaf-agent name in odoo-ai-agents prose, so it has nothing to imitate - is now
    asserted directly. git-toolkit itself (out of scan scope) legitimately owns those names.

    Scan scope: skills/, snippets/, commands/, agents/, docs/ markdown + the plugin's README.md +
    the generator/skill_tool_deps.json orchestration SSOT text. It does NOT reach repo-root
    CHANGELOG.md, so a git-toolkit-internal dev-log line there never conflicts with this guard.
    """
    violations: list[str] = []
    for f in _consumer_prose_files():
        violations.extend(_scan_file_for_agent_mention(f))

    n = len(violations)
    head = violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""

    assert not violations, (
        f"odoo-ai-agents: {n} line(s) name a git-toolkit leaf agent in executor-facing prose. "
        f"A bare mention nudges a runtime executor toward direct dispatch - name ONLY the "
        f"`git-toolkit:git-ops` front door and describe the op class generically (read-only "
        f"cognition / local mutation / GitHub API / large-scale) if needed. See "
        f"snippets/git-delegation.md.\n"
        + "\n".join(head)
        + tail
    )


def test_agent_mention_detection_red_before_green(tmp_path, monkeypatch):
    """Self-check that boundary B can FAIL for the right reason (red-before-green).

    Exercises the REAL scanner (_scan_file_for_agent_mention) on synthetic files so any loosening
    trips here: the detector must FLAG a leaf-agent name UNIFORMLY regardless of phrasing - a
    resolution-table cell, an informational gloss, and an active-dispatch sentence all count - and
    must PASS a file that names only the git-ops front door.
    """
    # _scan_file_for_agent_mention formats violations relative to REPO_ROOT; point it at tmp_path.
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    bad = tmp_path / "names-leaf-agents.md"
    bad.write_text(
        "| Local mutation - rebase, cherry-pick, merge | git-operator |\n"
        "git-operator owns the worktree lifecycle (S9 invariant).\n"
        "Dispatch github-operator via subagent_type to open the PR.\n",
        encoding="utf-8",
    )
    bad_hits = _scan_file_for_agent_mention(bad)
    assert len(bad_hits) == 3, (
        f"scanner must FLAG all three leaf-agent mentions (table cell, gloss, dispatch) "
        f"uniformly; got {bad_hits!r}"
    )

    good = tmp_path / "names-only-git-ops.md"
    good.write_text(
        "Invoke the `git-toolkit:git-ops` skill via the Skill tool to create a worktree.\n"
        "git-ops classifies the op internally and routes it to the specialist that owns it.\n",
        encoding="utf-8",
    )
    good_hits = _scan_file_for_agent_mention(good)
    assert good_hits == [], (
        f"scanner must PASS a file that names only the git-ops front door; got {good_hits!r}"
    )


def test_inline_git_detection_red_before_green(tmp_path, monkeypatch):
    """Self-check that boundary A can FAIL for the right reason (red-before-green).

    Boundary A (``test_no_git_delegation_bypass``) previously had NO self-check, so a future edit
    that loosened the allowlist or the scanner could pass silently. This exercises the REAL module
    functions (``_git_allowed`` + ``_scan_file``) on synthetic inputs so any such loosening trips
    here:

      - inline git MUTATIONS (push / cherry-pick / merge / rebase) are NEVER allowed;
      - own-worktree writes (add / commit / stash) are NO LONGER allowed inline (workers never run git);
      - the scanner FLAGS a fenced ``git push origin HEAD`` span and PASSES a bounded
        ``git diff --stat`` read.

    If the allowlist were widened to admit a mutation, or the scanner stopped flagging it, this
    test goes red.
    """
    # --- allowlist: mutations rejected (incl. add/commit/stash - workers never run git) ---
    for verb in ("push", "cherry-pick", "merge", "rebase", "add", "commit", "stash"):
        assert _git_allowed(verb, f"git {verb} origin HEAD") is False, (
            f"boundary A allowlist must REJECT inline `git {verb}` (workers never run git)"
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


# ---------------------------------------------------------------------------
# Boundary A extension: agent-facing repo docs (CLAUDE.md + docs/authoring)
#
# These root-level docs are NOT under plugins/odoo-ai-agents (so _md_files does
# not reach them), but CLAUDE.md mandates agents read/obey them, so a raw commit
# in one of their code spans is a real agent-facing bypass. Scan them with the
# same boundary-A machinery plus a carve-out for the confidentiality-hook install.
# ---------------------------------------------------------------------------

# Agent-facing repo docs that CLAUDE.md mandates agents read/obey. (CONTRIBUTING.md is the HUMAN
# guide and is intentionally OUT of scope - it keeps the manual `git commit -s` path.)
AGENT_FACING_DOCS = [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "docs" / "authoring-skills-and-agents.md"]


def _scan_agent_doc(f: Path) -> list[str]:
    """Boundary-A-style scan for an agent-facing doc, with ONE carve-out: the one-time
    confidentiality-hook install `git config --local core.hooksPath .githooks/` is a legitimate
    HUMAN setup command, not an agent commit op, and is not flagged."""
    text = f.read_text(encoding="utf-8"); rel = str(f.relative_to(REPO_ROOT))
    gen = _generated_line_ranges(text); out = []
    for span_start, span in _code_spans(text):
        base = text.count("\n", 0, span_start) + 1
        for off, line in enumerate(span.splitlines()):
            ln = base + off
            if _in_generated(ln, gen):        continue
            if "core.hooksPath" in line:      continue   # confidentiality-hook install carve-out
            if _GH_RE.search(line):           out.append(f"{rel}:{ln}: gh CLI")
            for m in _GITHUB_MCP_RE.finditer(line): out.append(f"{rel}:{ln}: GitHub MCP")
            for m in _GIT_RE.finditer(line):
                v = m.group(1)
                if not _git_allowed(v, line):  out.append(f"{rel}:{ln}: git {v}  [{line.strip()[:80]!r}]")
    return out


def test_agent_facing_docs_route_git_through_git_ops():
    """CLAUDE.md + docs/authoring are agent instructions; they must route git through
    git-toolkit:git-ops, never a raw commit/push in a code span. The confidentiality-hook
    `git config core.hooksPath` install is carved out. Guards the Problem-3 docs/root leak."""
    v = []
    for f in AGENT_FACING_DOCS:
        if f.exists(): v.extend(_scan_agent_doc(f))
    assert not v, ("agent-facing repo docs contain a raw git command in a code span; route through "
                   "the git-toolkit:git-ops skill.\n" + "\n".join(v))


# ---------------------------------------------------------------------------
# Boundary C: the ADVISORY reminder hook must never auto-approve the git
# mutation it exists to discourage
#
# `hooks/remind-delegate.sh` (PreToolUse) reminds a role=leaf subagent that it must route git
# mutations through git-toolkit:git-ops instead of running them itself (boundary A/B above are
# the build-time/static guarantee; this hook is only a same-turn, runtime nudge). Being
# advisory means it must NEVER hand back a `permissionDecision` that DECIDES the call for the
# permission system - "allow" silently auto-approves the exact git mutation this whole file's
# boundary exists to stop, defeating the delegation contract at the one layer (PreToolUse) that
# runs before the user ever sees a prompt. This is a runtime-behavior test (invokes the actual
# hook script as the harness would), not a source-text scan like boundaries A/B.
# ---------------------------------------------------------------------------

REMIND_DELEGATE_HOOK = AGENTS_PLUGIN / "hooks" / "remind-delegate.sh"


def test_remind_delegate_never_allows_risky_git_mutation():
    """remind-delegate.sh must NOT emit permissionDecision:"allow" for a git-mutating Bash
    command dispatched from a role=leaf subagent (the RISKY branch, ~line 66-84).

    Business rule: this hook is documented as ADVISORY-ONLY (HARD CONTRACT header) - it may
    attach `additionalContext` as a reminder, but it must never itself decide the tool call,
    because "allow" bypasses normal permission-rule evaluation (including the user's own
    deny/ask rules) for the exact git mutation the delegation boundary (this file, boundary A/B)
    exists to stop. An advisory hook that auto-approves what it exists to discourage is a
    machine-level bypass of the repo's own git-delegation contract.

    Red-before-green: prior to this fix, both PreToolUse emit sites in remind-delegate.sh hard-
    coded `permissionDecision:"allow"` (unconditionally, regardless of TOOL/RISKY), so this
    exact assertion (decision must equal "defer") would have FAILED against the pre-fix
    script - it asserts the opposite of what the script used to always emit, so it is not a
    snapshot of current behavior; it protects the advisory-never-decides contract this whole
    module guards. Asserting `== "defer"` (not merely `!= "allow"`) pins the exact documented
    no-opinion value (HARD CONTRACT header: "permissionDecision is ALWAYS 'defer' ... NEVER
    'allow', 'deny', or 'ask'") so a future regression to "ask" or "deny" - a lesser but still
    real bug, silently swallowed by a looser `!= "allow"` check - is caught here too.
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -am 'do the thing'"},
        # role=leaf per generator/skill_tool_deps.json "agents"."odoo-backend-coder".role
        "agent_id": "agent-under-test",
        "agent_type": "odoo-backend-coder",
        "cwd": str(REPO_ROOT),
    }

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(AGENTS_PLUGIN)

    result = subprocess.run(
        ["bash", str(REMIND_DELEGATE_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, (
        f"remind-delegate.sh must never hard-fail (exit 0 always); "
        f"got rc={result.returncode}, stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), (
        "remind-delegate.sh produced no output for a RISKY git-mutating Bash command from a "
        "role=leaf subagent - expected a hookSpecificOutput reminder JSON on stdout"
    )
    output = json.loads(result.stdout)
    decision = output.get("hookSpecificOutput", {}).get("permissionDecision")
    assert decision == "defer", (
        f"remind-delegate.sh emitted permissionDecision={decision!r} for a git-mutating Bash "
        f"command dispatched from a role=leaf subagent - an ADVISORY hook must never itself "
        f"decide the tool call; it must always emit the documented no-opinion value 'defer'. "
        f"Full output: {output!r}"
    )


def test_remind_delegate_never_allows_mid_run_delegate_nudge(tmp_path):
    """remind-delegate.sh must NOT emit permissionDecision:"allow" for the OTHER PreToolUse emit
    site - the main-agent mid-run drive-to-done delegate nudge (~line 119), independent of the
    leaf/spawner RISKY-git-mutation site (~line 84) covered by the test above.

    Business rule: same advisory-only contract as the sibling test, exercised via the OTHER
    branch of the same file - no agent_id/agent_type (this is the MAIN agent, not a subagent),
    a heavy/mutating tool (Write/Edit/MultiEdit/Bash), and an active drive-to-done run (a
    `run-*.json` with `status: "NEEDS_NEXT"`) seeded under the resolved ISOLATE dir. This branch
    has its own independent self-gates (active-run glob, not the leaf-role SSOT lookup the other
    branch uses), so a regression that fixed only the RISKY branch and left this one at
    `"allow"` would NOT be caught by `test_remind_delegate_never_allows_risky_git_mutation`
    above - that test never populates agent_id/agent_type, so it can never reach this code path.

    Red-before-green: prior to this fix, this emit site (like the sibling one) hard-coded
    `permissionDecision:"allow"` unconditionally for any Write/Edit/MultiEdit/Bash call from the
    main agent during an active run - so this exact assertion (decision must equal "defer")
    would have FAILED against the pre-fix script for the same reason as the sibling test, but by
    exercising a structurally independent code path (no leaf-role resolution involved at all).
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    # Seed an active run (status NEEDS_NEXT) under an explicit ISOLATE override so this test
    # never touches the real state root and never depends on git/marker resolution.
    isolate_dir = tmp_path / "isolate"
    isolate_dir.mkdir(parents=True, exist_ok=True)
    (isolate_dir / "run-test123.json").write_text(
        json.dumps({"status": "NEEDS_NEXT"}), encoding="utf-8"
    )

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/whatever.py"},
        # No agent_id/agent_type: this is the MAIN agent (not a subagent) - the branch the
        # test_remind_delegate_never_allows_risky_git_mutation test above cannot reach.
        "cwd": str(REPO_ROOT),
    }

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(AGENTS_PLUGIN)
    env["ODOO_AI_WORKTREE_DIR"] = str(isolate_dir)

    result = subprocess.run(
        ["bash", str(REMIND_DELEGATE_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, (
        f"remind-delegate.sh must never hard-fail (exit 0 always); "
        f"got rc={result.returncode}, stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), (
        "remind-delegate.sh produced no output for a mid-run Write from the main agent with an "
        "active NEEDS_NEXT run - expected a hookSpecificOutput reminder JSON on stdout"
    )
    output = json.loads(result.stdout)
    decision = output.get("hookSpecificOutput", {}).get("permissionDecision")
    assert decision == "defer", (
        f"remind-delegate.sh emitted permissionDecision={decision!r} for a mid-run Write from "
        f"the main agent (active drive-to-done run) - an ADVISORY hook must never itself decide "
        f"the tool call; it must always emit the documented no-opinion value 'defer'. "
        f"Full output: {output!r}"
    )
