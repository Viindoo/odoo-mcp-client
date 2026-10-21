"""Guard: odoo-ai-agents must route all git/GitHub work through the git-toolkit ``git-ops`` skill.

Business rule (the seam this file protects): git-toolkit is the ONLY plugin that knows how to operate
git - which commands, which flags. A consumer skill/agent that needs a git/GitHub operation INVOKES
the ``git-toolkit:git-ops`` skill via the Skill tool and states the REQUEST and the expected RESULT,
never a git command or flag (git-ops then classifies the op and runs it on the right git agent under
the safety contract). Repo facts an agent used to read with inline git (root, branch, short SHA,
origin URL, dirty paths, merge/rebase in progress) come from the odoo-local ``repo_facts`` tool, whose
script calls git. Consumers also never name or cold-spawn the git leaf agents (git-operator,
git-surveyor, github-operator, git-pipeline-lead) directly.

Two complementary boundaries are enforced here:

A. NO GIT COMMAND IN PROSE (``test_no_git_command_in_agent_prose``) - NO ``git <verb>`` (any
   subcommand, with or without ``-C <dir>`` / ``-c k=v`` / other global flags, wrapped across lines or
   not) in ANY odoo-ai-agents agent-facing text: code spans, fenced blocks, plain prose, workflow YAML
   comments. No git-only flag (``--no-ff``, ``--name-only``, ...) either, and no ``op:`` request line
   carrying flags (``--skip``, ``--continue``, ``-s``). A bounded read is not an exception: there is no
   allowlist. ``gh`` CLI calls and GitHub MCP tools stay forbidden in code spans. Allowlisted SHAPES
   only (``_allowed_shape``): the ``git clone`` line ``/odoo-ai-agents:odoo-setup`` prints for the
   HUMAN, an external quote naming ``core.hooksPath``. Out of scope by construction: ``scripts/``
   (code, not prose) and the plugin's human-only ``docs/`` and ``README.md``.

B. NO GIT-TOOLKIT AGENT MENTION (``test_no_git_toolkit_agent_mention``) - a consumer must not
   NAME one of the git-toolkit leaf agents (git-operator, git-surveyor, github-operator,
   git-pipeline-lead) in ANY phrasing - dispatch instruction OR informational aside alike. Only
   ``git-toolkit:git-ops`` may be named. Scanned across the odoo-ai-agents executor-facing prose set.

The developer session of THIS repo is governed by CLAUDE.md, which may keep bounded reads inline;
``test_agent_facing_docs_route_git_through_git_ops`` scans CLAUDE.md and docs/authoring-skills-and-agents.md
with that dev-session allowance (``_DEV_SESSION_READS``) and nothing more.

FP-avoidance choices (do NOT loosen these without an accompanying test update):

1. GENERATED REGIONS SKIPPED - content between
   ``<!-- BEGIN GENERATED ... -->`` / ``<!-- END GENERATED ... -->`` markers is excluded
   (both boundaries). Generated regions are MCP tool descriptions emitted by ``make gen``.

2. HYPHEN BOUNDARY - ``git`` followed by a space and a subcommand is the only shape matched, so
   ``git-ops``, ``git-toolkit``, ``odoo-git-rebase`` (hyphen, no space) never match.

3. GH CLI CHECK - ``gh `` (trailing space) is required, so ``github``, ``ghci``, and path
   segments like ``.github/`` never match.

4. git-toolkit EXCLUDED - the plugin that legitimately wraps raw git (and whose OWN ``git-ops``
   skill legitimately dispatches the git leaf agents) is not in the scan scope; its agents are
   the target delegates, not the source of violations.

5. MENTION == VIOLATION (boundary B) - the rule is strict: a git-toolkit leaf-agent name must
   NEVER appear in odoo-ai-agents executor-facing prose, because even an informational mention
   gives a runtime executor a specialist name to imitate and dispatch directly. The scan scope
   covers ``skills/``, ``snippets/``, ``commands/``, ``agents/`` and ``docs/`` markdown PLUS the
   plugin's own ``README.md`` and the ``generator/skill_tool_deps.json`` orchestration SSOT text -
   everything an executing agent may read. ``plugins/git-toolkit/**`` stays out of scope; the scan
   never reaches repo-root ``CHANGELOG.md``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"


# ---------------------------------------------------------------------------
# File discovery
# Boundary A scans every odoo-ai-agents file an executing agent may read as INSTRUCTIONS: skills/,
# agents/, commands/, snippets/ (markdown, recursive) and workflows/ (YAML). Out of scope by
# construction: scripts/ (code - a script may call git), docs/ and README.md (human reference;
# boundary B still scans them), repo-root CONTRIBUTING.md (the human guide keeps `git commit -s`).
# Two repo-root agent-facing docs that CLAUDE.md mandates agents read - CLAUDE.md itself and
# docs/authoring-skills-and-agents.md - are scanned by test_agent_facing_docs_route_git_through_git_ops
# with the developer-session allowance.
# ---------------------------------------------------------------------------

def _agent_prose_files() -> list[Path]:
    """All odoo-ai-agents agent-facing instruction text (boundary A)."""
    files: list[Path] = []
    for subdir in ("skills", "agents", "commands", "snippets"):
        d = AGENTS_PLUGIN / subdir
        if d.exists():
            files.extend(d.rglob("*.md"))
    d = AGENTS_PLUGIN / "workflows"
    if d.exists():
        files.extend(d.glob("*.yaml"))
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
# Boundary A: no git command in agent-facing prose
# ---------------------------------------------------------------------------

# gh CLI: trailing space required to distinguish from "github", "ghci", ".github/", etc.
_GH_RE = re.compile(r"\bgh\s")

# GitHub MCP tools: the full qualified tool-call prefix.
_GITHUB_MCP_RE = re.compile(r"\bmcp__plugin_github_github__\w+")

# Every git subcommand an agent could spell. A verb here after the word `git` is a command, whatever
# the surrounding markup: the rule is "no `git <verb>` in prose", so English use of the same words
# ("the git branch", "a git merge step") is reworded rather than exempted.
_GIT_VERBS = (
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout",
    "cherry-pick", "clean", "clone", "commit", "commit-tree", "config", "describe", "diff", "diff-tree",
    "fetch", "filter-repo", "for-each-ref", "format-patch", "gc", "grep", "hash-object", "init", "log",
    "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mktree", "mv", "name-rev", "notes",
    "patch-id", "pull", "push", "range-diff", "read-tree", "rebase", "reflog", "remote", "reset",
    "restore", "rev-list", "rev-parse", "revert", "rm", "shortlog", "show", "show-ref", "stash",
    "status", "submodule", "switch", "symbolic-ref", "tag", "update-index", "update-ref", "worktree",
    "write-tree",
)

# Between `git` and its subcommand: whitespace (a span may wrap lines, with a markdown quote `>`, a
# comment `#` or a bullet `*` at the start of the continuation) and global options (`-C <dir>`,
# `-c k=v`, `--no-pager`, `--git-dir=...`).
_SEP = r"[\s>#*]+"
_GLOBAL_OPT = r"(?:-[Cc]%s\S+|--?[A-Za-z][\w-]*(?:=\S+)?)" % _SEP
_GIT_RE = re.compile(
    r"(?<![\w./-])git(?:%s%s)*%s(%s)(?![\w-])" % (
        _SEP, _GLOBAL_OPT, _SEP, "|".join(sorted(_GIT_VERBS, key=len, reverse=True))
    )
)

# Flags only git understands: naming one is spelling a git command even without the word `git`.
_GIT_FLAG_RE = re.compile(
    r"(?<![\w-])--(?:no-ff|ff-only|no-commit|force-with-lease|name-only|name-status|porcelain|"
    r"rebase-merges|show-current|abbrev-ref|show-toplevel|git-common-dir|is-ancestor|first-parent|"
    r"no-merges|no-verify|amend|left-right|diff-filter|cherry-pick)(?![\w-])"
)

# A git-ops request line (`op: ...`) states the request, so it carries no command flag at all.
_OP_FLAG_RE = re.compile(r"(?:^|[\s`#])op:.*?(?<![\w-])(--[a-z][a-z-]*|-[A-Za-z])(?![\w-])")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _allowed_shape(rel: str, verb: str, line: str) -> bool:
    """The ONLY shapes of `git <verb>` that may stay in agent-facing prose.

    - an external quote that names `core.hooksPath` (the coding guideline's own sentence);
    - the `git clone` line `/odoo-ai-agents:odoo-setup` prints for the HUMAN to run (the agent never
      runs it; that file names the commands it prints).
    Everything else - every read included - is a request to `git-toolkit:git-ops` or a `repo_facts` call.
    """
    if "core.hooksPath" in line:
        return True
    if rel.endswith("commands/odoo-setup.md") and verb == "clone":
        return True
    return False


def _scan_file(f: Path) -> list[str]:
    """Return formatted boundary-A violation strings for one file (whole text: code spans, fenced
    blocks, prose, spans wrapped across lines, YAML comments alike)."""
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(REPO_ROOT))
    lines = text.splitlines()
    gen_regions = _generated_line_ranges(text)
    violations: list[str] = []

    def src(n: int) -> str:
        return lines[n - 1].strip()[:90] if 0 < n <= len(lines) else ""

    seen: set[tuple[int, str]] = set()
    for m in _GIT_RE.finditer(text):
        n = _line_of(text, m.start())
        verb = m.group(1)
        if _in_generated(n, gen_regions) or (n, verb) in seen:
            continue
        seen.add((n, verb))
        window = " ".join(lines[max(n - 2, 0):n + 1])
        if _allowed_shape(rel, verb, window):
            continue
        violations.append(f"{rel}:{n}: git {verb}  [{src(n)!r}]")

    for m in _GIT_FLAG_RE.finditer(text):
        n = _line_of(text, m.start())
        if _in_generated(n, gen_regions) or "core.hooksPath" in src(n):
            continue
        violations.append(f"{rel}:{n}: git flag {m.group()}  [{src(n)!r}]")

    for i, raw in enumerate(lines, start=1):
        if _in_generated(i, gen_regions):
            continue
        m = _OP_FLAG_RE.search(raw)
        if m:
            violations.append(f"{rel}:{i}: op request carries flag {m.group(1)}  [{raw.strip()[:90]!r}]")

    # gh CLI / GitHub MCP tools stay forbidden in code spans.
    for span_start, span_content in _code_spans(text):
        base_line = _line_of(text, span_start)
        for offset, raw_line in enumerate(span_content.splitlines()):
            line_no = base_line + offset
            if _in_generated(line_no, gen_regions):
                continue
            if _GH_RE.search(raw_line):
                violations.append(f"{rel}:{line_no}: gh CLI  [{raw_line.strip()[:90]!r}]")
            for mm in _GITHUB_MCP_RE.finditer(raw_line):
                violations.append(f"{rel}:{line_no}: GitHub MCP  [{mm.group()!r}]")

    return sorted(set(violations), key=lambda v: (v.split(":")[0], int(v.split(":")[1]), v))


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

def test_no_git_command_in_agent_prose():
    """Boundary A: no ``git <verb>``, git-only flag or flag-carrying ``op:`` line anywhere in
    odoo-ai-agents agent-facing text - reads included.

    Business rule: how to operate git (which commands, which flags) is git-toolkit's know-how, and
    only there. A skill/agent that needs a git fact reads it from the odoo-local ``repo_facts`` tool;
    one that needs anything else asks ``git-toolkit:git-ops`` for a RESULT. An inline command - even a
    harmless-looking read - lets a runtime agent copy it and run git itself.
    """
    all_violations: list[str] = []
    for f in _agent_prose_files():
        all_violations.extend(_scan_file(f))

    n = len(all_violations)
    head = all_violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""

    assert not all_violations, (
        f"odoo-ai-agents: {n} git command(s)/flag(s) in agent-facing prose. State the REQUEST and the "
        f"expected RESULT to git-toolkit:git-ops (invoke it via the Skill tool), or read a repo fact "
        f"with the odoo-local repo_facts tool; never write the command. See snippets/git-delegation.md.\n"
        + "\n".join(head)
        + tail
    )


# A GRANT is prose that PERMITS an inline git read ("bounded reads may stay inline", "the bounded-read
# allowlist"). There is no such permission for plugin prose, so no file may hand one out - a grant
# is the sentence that re-opens the door the command scan closes.
_GRANT_RE = re.compile(
    r"bounded[- ]reads?\b[^.\n]{0,80}\b(?:inline|allowlist)|"
    r"\b(?:inline|read-only)[- ]git\b[^.\n]{0,40}\b(?:ok|allowed|legal)|"
    r"may (?:stay|run) inline|inline-legal|inline[- ]OK|bounded[- ]read allowlist",
    re.IGNORECASE,
)


def _scan_file_for_grant(f: Path) -> list[str]:
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(REPO_ROOT))
    gen_regions = _generated_line_ranges(text)
    flat = re.sub(r"[ \t]*\n[ \t>#*]*", " ", text)  # a grant wrapped over two lines still counts
    out = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        if _in_generated(i, gen_regions):
            continue
        if _GRANT_RE.search(raw_line):
            out.append(f"{rel}:{i}: grants an inline git read  [{raw_line.strip()[:90]!r}]")
    if not out and _GRANT_RE.search(flat):
        out.append(f"{rel}: grants an inline git read (wrapped over lines)")
    return out


def test_no_prose_grants_an_inline_git_read():
    """Boundary A, GRANT half: odoo-ai-agents agent-facing text never PERMITS an inline git read
    ("bounded reads may stay inline", "the bounded-read allowlist"). Every actor reads a repo fact
    with `repo_facts` and asks git-ops for anything else; a permission sentence anywhere re-opens
    the door the command scan closes."""
    violations: list[str] = []
    for f in _agent_prose_files():
        violations.extend(_scan_file_for_grant(f))
    assert not violations, "prose grants an inline git read:\n" + "\n".join(violations[:60])


def test_grant_detection_red_before_green(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    for label, text in {
        "may stay inline": "Bounded reads (status) may stay inline.\n",
        "allowlist": "See the bounded-read allowlist in git-delegation.md.\n",
        "inline-legal": "the same class the snippet keeps inline-legal\n",
        "wrapped": "bounded reads\nmay stay inline\n",
    }.items():
        f = tmp_path / "x.md"
        f.write_text(text, encoding="utf-8")
        assert _scan_file_for_grant(f), f"grant detector must FLAG: {label}"
    ok = tmp_path / "ok.md"
    ok.write_text("Run no git. A bounded grep of the log is fine; ask git-ops for history.\n", encoding="utf-8")
    assert _scan_file_for_grant(ok) == []


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


def test_git_command_detection_red_before_green(tmp_path, monkeypatch):
    """Self-check that boundary A FAILS for the right reason, and passes what it must.

    Exercises the REAL scanner on synthetic files. Every spelling of "the agent runs git" must be
    flagged - mutation or read, code span, fence, plain prose, a span wrapped over two lines, the
    ``-C <dir>`` / ``-c k=v`` / ``--no-pager`` forms, a YAML comment, an ``op:`` line with flags - and
    nothing else may be: ``git-ops``, ``odoo-git-rebase``, ``github``, the human ``git clone`` line,
    the external ``core.hooksPath`` quote.
    """
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    def hits(text, name="x.md"):
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return _scan_file(f)

    flagged = {
        "inline mutation": "Run `git push origin HEAD` now.\n",
        "inline bounded read": "Check with `git status --porcelain`.\n",
        "inline read, was allowlisted": "Use `git rev-parse --short HEAD`.\n",
        "fenced block": "```bash\ngit diff --stat\n```\n",
        "plain prose": "Then you git rebase the branch onto main.\n",
        "-C form": "Run `git -C <dir> rm file`.\n",
        "-c form": "Run `git -c core.quotepath=off log`.\n",
        "global flag": "Run `git --no-pager log`.\n",
        "wrapped span": "Run `git\n  rebase --onto a b`.\n",
        "wrapped under a quote": "> run git\n> merge-base a b\n",
        "yaml comment": "    # `git -C <root> status --porcelain`\n",
        "git-only flag": "Merge it with --no-ff and look at --name-only.\n",
        "op line with a flag": "op: continue the rebase --skip\n",
        "op line with a short flag": "- op: rm -r module dir + commit -s\n",
        "gh cli": "Run `gh pr list`.\n",
        "github mcp": "Call `mcp__plugin_github_github__get_me`.\n",
    }
    for label, text in flagged.items():
        assert hits(text), f"boundary A must FLAG: {label}"

    clean = {
        "git-ops name": "Invoke `git-toolkit:git-ops` and ask it for the merge base.\n",
        "hyphenated skill": "Hand over to odoo-git-rebase, then odoo-forward-port.\n",
        "github word": "Open the github page; see .github/workflows.\n",
        "request without command": "op: create an integration worktree at the feature tip\n",
        "repo_facts": "Read the branch with `repo_facts`.\n",
        "git as a noun": "The git index is shared.\n",
        "core.hooksPath quote": "* Changes your git config's `core.hooksPath` to the tooling hooks.\n",
    }
    for label, text in clean.items():
        assert hits(text) == [], f"boundary A must PASS: {label}; got {hits(text)!r}"

    assert hits("Print `git clone -b BRANCH <ssh-url> odoo17` for the user.\n", "commands/odoo-setup.md") == []
    assert hits("Print `git clone -b BRANCH <ssh-url> odoo17` for the user.\n", "skills/other/SKILL.md")


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


# The developer session of THIS repo (CLAUDE.md governs it) may keep these BOUNDED reads inline:
# status, rev-parse, branch --show-current, remote get-url, merge-base, worktree list, and
# diff / log / show only with a bounding flag. Every mutation still goes through git-toolkit:git-ops.
# This allowance is for CLAUDE.md and docs/authoring-skills-and-agents.md ONLY; plugin prose has none.
_DEV_SESSION_ALWAYS = frozenset({"status", "rev-parse", "merge-base"})
_DEV_GIT_RE = re.compile(r"\bgit(?:\s+-C\s+\S+)?\s+([a-z][a-z-]*)")


def _dev_session_read(verb: str, line: str) -> bool:
    if verb in _DEV_SESSION_ALWAYS:
        return True
    if verb == "branch":
        return "--show-current" in line
    if verb == "remote":
        return "get-url" in line
    if verb == "worktree":
        return bool(re.search(r"\bgit\s+worktree\s+list\b", line))
    if verb == "diff":
        return any(f in line for f in ("--stat", "--name-only", "--shortstat", "--quiet", "--check"))
    if verb == "log":
        return bool(re.search(r"-n\s*(?:\d+|<\w+>)|--oneline\b", line))
    if verb == "show":
        return "--stat" in line
    return False


def _scan_agent_doc(f: Path) -> list[str]:
    """Scan an agent-facing repo doc: code spans may hold a dev-session bounded read; a mutation,
    an unbounded read, a gh call or a GitHub MCP tool is flagged. ONE carve-out: the one-time
    confidentiality-hook install `git config --local core.hooksPath .githooks/` is a HUMAN setup
    command, not an agent op."""
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
            for m in _DEV_GIT_RE.finditer(line):
                v = m.group(1)
                if not _dev_session_read(v, line):  out.append(f"{rel}:{ln}: git {v}  [{line.strip()[:80]!r}]")
    return out


def test_agent_facing_docs_route_git_through_git_ops():
    """CLAUDE.md + docs/authoring govern the DEVELOPER session of this repo: a bounded read may stay
    inline there, but any mutation, unbounded read, gh call or GitHub MCP tool in a code span must
    route through git-toolkit:git-ops. The confidentiality-hook `git config core.hooksPath` install
    is carved out."""
    v = []
    for f in AGENT_FACING_DOCS:
        if f.exists(): v.extend(_scan_agent_doc(f))
    assert not v, ("agent-facing repo docs contain a raw git mutation or unbounded read in a code span; "
                   "route through the git-toolkit:git-ops skill.\n" + "\n".join(v))


def test_dev_session_allowance_flags_what_it_must(tmp_path, monkeypatch):
    """The dev-session scan accepts bounded reads and flags every mutation / unbounded read, so the
    allowance cannot widen silently."""
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    ok = tmp_path / "ok.md"
    ok.write_text("Reads: `git status`, `git diff --stat`, `git log -n5`, `git rev-parse HEAD`.\n", encoding="utf-8")
    assert _scan_agent_doc(ok) == []
    for cmd in ("git commit -s", "git push origin x", "git rebase main", "git diff main", "git log main..x",
                "git -C d add f", "git show abc", "git rm f"):
        bad = tmp_path / "bad.md"
        bad.write_text(f"Run `{cmd}`.\n", encoding="utf-8")
        assert _scan_agent_doc(bad), f"dev-session scan must flag `{cmd}`"


# ---------------------------------------------------------------------------
# Boundary C: the ADVISORY reminder hook must never auto-approve the git
# mutation it exists to discourage
#
# `hooks/remind-delegate.sh` (PreToolUse) reminds a role=leaf or role=node-owner subagent that it
# runs no git itself - a repo fact comes from repo_facts, anything else is a git-ops request
# (boundary A/B above are the build-time/static guarantee; this hook is only a same-turn, runtime
# nudge, and its fire/no-fire cases are tested in tests/test_advisory_hooks_context_cost.py). Being
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

    The reminder carries NO permissionDecision at all: every value decides something. "allow"
    skips the user's own rules, "ask"/"deny" impose a prompt or a refusal, and "defer" stops a
    `claude -p` / SDK run at that tool call (Claude Code honors it only non-interactively, as a
    pause for the calling process). Asserting the key is absent - not merely `!= "allow"` - is
    what catches any of those coming back.
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -am 'do the thing'"},
        # role=leaf per generator/skill_tool_deps.json "agents"."odoo-frontend-coder".role
        "agent_id": "agent-under-test",
        "agent_type": "odoo-frontend-coder",
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
    hso = output.get("hookSpecificOutput", {})
    assert hso.get("additionalContext"), f"the reminder text is missing: {output!r}"
    assert "permissionDecision" not in hso and "decision" not in output, (
        f"remind-delegate.sh made a permission decision for a git-mutating Bash command from a "
        f"role=leaf subagent - an ADVISORY hook must leave the call to normal permission "
        f"evaluation (no decision field at all; 'defer' stops a -p/SDK run). Output: {output!r}"
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

    Same contract as the sibling test - no permission decision at all - exercised through a
    structurally independent code path (no leaf-role resolution involved at all).
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    # Seed an active run (status NEEDS_NEXT) under an explicit ISOLATE override so this test
    # never touches the real state root and never depends on git/marker resolution.
    isolate_dir = tmp_path / "isolate"
    isolate_dir.mkdir(parents=True, exist_ok=True)
    (isolate_dir / "run-test123.json").write_text(
        json.dumps({"status": "NEEDS_NEXT"}), encoding="utf-8"
    )

    # The nudge is for a run THIS session drives (hooks/run-ownership.sh): its transcript shows the
    # call that wrote the run record.
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "assistant", "timestamp": now, "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_run", "name": "Read",
                                 "input": {"file_path": str(isolate_dir / "run-test123.json")}}]}}),
        json.dumps({"type": "user", "timestamp": now, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_run", "content": "{}"}]}}),
    ]) + "\n", encoding="utf-8")

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/whatever.py"},
        # No agent_id/agent_type: this is the MAIN agent (not a subagent) - the branch the
        # test_remind_delegate_never_allows_risky_git_mutation test above cannot reach.
        "cwd": str(REPO_ROOT),
        "transcript_path": str(transcript),
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
    hso = output.get("hookSpecificOutput", {})
    assert hso.get("additionalContext"), f"the reminder text is missing: {output!r}"
    assert "permissionDecision" not in hso and "decision" not in output, (
        f"remind-delegate.sh made a permission decision for a mid-run Write from the main "
        f"agent - an ADVISORY hook must leave the call to normal permission evaluation (no "
        f"decision field at all; 'defer' stops a -p/SDK run). Output: {output!r}"
    )
