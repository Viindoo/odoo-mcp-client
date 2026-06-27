"""Guard: odoo-ai-agents must delegate all git/GitHub operations to git-toolkit.

Business rule: git-toolkit is the ONLY plugin allowed to execute git mutations,
call the ``gh`` CLI, or invoke GitHub MCP tools. Any odoo-ai-agents authored prose
that instructs these operations inline bypasses the delegation boundary and the
safety contract enforced by git-toolkit (backup, tree-identity verify, human-confirm
gate). Every such op MUST be delegated via Agent tool ``subagent_type`` to one of:
git-surveyor, git-operator, github-operator, or git-pipeline-lead.

FP-avoidance choices (do NOT loosen these without an accompanying test update):

1. CODE SPANS ONLY - inline backtick spans AND fenced ````` blocks are scanned;
   plain prose is NOT. Prevents flagging English words like "commit", "push",
   "merge", "branch" in descriptive sentences ("each commit is replayed ...",
   "the feature branch", "merge strategy").

2. GENERATED REGIONS SKIPPED - content between
   ``<!-- BEGIN GENERATED ... -->`` / ``<!-- END GENERATED ... -->`` markers is
   excluded. Generated regions contain MCP tool descriptions auto-emitted by
   ``make gen`` and are not authored agent instructions.

3. HYPHEN BOUNDARY - ``\\bgit\\s+`` (space, not zero-width) never matches
   ``git-operator``, ``git-surveyor``, ``git-toolkit`` (hyphen, no space after
   "git"). ``git -C <path>`` form is explicitly handled.

4. GH CLI CHECK - ``gh `` (trailing space) is required, so ``github``, ``ghci``,
   and path segments like ``.github/`` never match.

5. git-toolkit EXCLUDED - the plugin that legitimately wraps raw git is not in
   the scan scope; its agents are the target delegates, not the source of violations.
"""

from __future__ import annotations

import re
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
    files: list[Path] = []
    for subdir in ("skills", "agents", "commands", "snippets"):
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
# Violation detection
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

    Everything else is a violation requiring delegation to git-toolkit.
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
        # Benign own-worktree writes - allowed per canonical #3 in git-delegation.md
        # ("Benign local writes" section). Valid only when the agent is in its own
        # dedicated worktree (S9-satisfied by construction); static analysis cannot
        # enforce the worktree scoping so the policy is documented in prose.
        return True
    # All other verbs (push, fetch, pull, rebase, merge, cherry-pick, checkout,
    # switch, reset, tag, apply, format-patch, range-diff,
    # worktree-add, branch-delete, ...) are mutations or unbounded reads.
    return False


def _scan_file(f: Path) -> list[str]:
    """Return formatted violation strings for a single file."""
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
# The guard test
# ---------------------------------------------------------------------------

def test_no_git_delegation_bypass():
    """odoo-ai-agents must delegate all git mutations + GitHub-API + unbounded reads
    to git-toolkit; only bounded reads may appear inline in code spans.

    Business rule: git-toolkit agents (git-surveyor, git-operator, github-operator,
    git-pipeline-lead) hold exclusive authority over git mutations and GitHub API ops.
    odoo-ai-agents skills/agents/commands/snippets must NEVER contain inline git
    mutations or unbounded reads; they must delegate via Agent tool subagent_type.

    Allowed inline in code spans (bounded, read-only):
      git status
      git rev-parse [...]
      git branch --show-current
      git remote get-url [...]
      git merge-base [...]
      git worktree list
      git diff --stat | --name-only | --shortstat | --quiet | --check
      git log --oneline | -n<digits>
      git show --stat

    Allowed inline (own-worktree benign writes - canonical #3):
      git add, git commit, git stash  (in a dedicated worker worktree only)

    Forbidden inline (must delegate to git-toolkit):
      push, fetch, pull, rebase, merge, cherry-pick, checkout, switch,
      reset, tag, apply, format-patch, range-diff, worktree add/remove,
      bare git diff <ref>, bare git log <range>, git show <sha> (full patch),
      gh CLI calls, mcp__plugin_github_github__* tool invocations.
    """
    all_violations: list[str] = []
    for f in _md_files():
        all_violations.extend(_scan_file(f))

    n = len(all_violations)
    head = all_violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""

    assert not all_violations, (
        f"odoo-ai-agents: {n} forbidden git/GitHub reference(s) bypass the git-toolkit "
        f"delegation boundary. Delegate each to git-surveyor / git-operator / "
        f"github-operator / git-pipeline-lead via Agent tool subagent_type. "
        f"See snippets/git-delegation.md for the dispatch contract and allowlist.\n"
        + "\n".join(head)
        + tail
    )
