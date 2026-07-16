"""Guard P3 (odoo-code-review PR inline comments): the reviewer's Issues table
must carry `File` + `Line/Range` so a poster can anchor ONE inline comment per
finding, and the PR-posting hand-off must fan out EVERY severity (never a
single flat "review body").

Business rule under test (not implementation): a PR poster needs, for EVERY
Issues-table row, a diff-relative file path and a line/range to anchor a
GitHub inline comment (`add_comment_to_pending_review` requires `path` +
`line`/`startLine`) - a table with only `Location: line N` and no file cannot
drive that fan-out. A finding with a concrete fix must be replayable as a
```suggestion fence, so a `#### <File>:<Line/Range>` heading + fenced
replacement-lines convention is required. The skill hand-off must pass
structured findings (not a review body) and post ALL severities, never
filtering LOW out of the inline fan-out (decided option A, see
`22-solution-final.md` §3 B6).

These tests fail for the right reason if:
- the Issues table regresses to `Location` with no `File` column (old shape),
- the `#### <File>:<Line/Range>` suggested-replacement heading convention is
  dropped,
- the skill hand-off reverts to handing a single "review body" to git-ops,
- the skill stops requiring EVERY severity in the inline fan-out.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "agents"
SKILLS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills"

CODE_REVIEWER_AGENT = AGENTS_DIR / "odoo-code-reviewer.md"
CODE_REVIEW_SKILL = SKILLS_DIR / "odoo-code-review" / "SKILL.md"
AGENT_PROMPTS_REF = SKILLS_DIR / "odoo-code-review" / "references" / "agent-prompts.md"


def _read(path: Path) -> str:
    assert path.exists(), f"{path} not found"
    return path.read_text(encoding="utf-8")


def _fence_balance_state(text: str) -> tuple[bool, int]:
    """Walk the document CommonMark-fence-style and return (is_balanced, open_len).

    An opening fence is a line (after stripping up to 3 leading spaces) of 3+
    backticks, optionally followed by an info string (e.g. ```python). While a
    fence is open, ONLY a line that is backticks-and-trailing-whitespace ONLY
    (no info string) with count >= the opening count can close it - a line
    like ```python can never close a fence, opening or not, because it is not
    a pure backtick-and-whitespace line. This mirrors the CommonMark rule that
    trips up a 3-backtick wrapper containing a nested 3-backtick example: the
    nested block's own closer (a bare ```) satisfies "pure backticks, count >=
    opening count" and closes the OUTER fence early, silently dropping
    everything after it out of the code block until some later stray fence
    line closes (or never closes) the document. Returns whether the document
    ends back at the top level (no fence open) - the only way that holds is if
    every fence, including an outer wrapper around nested examples, is closed
    by something with at least as many backticks as it opened with.
    """
    open_len = 0
    for raw_line in text.splitlines():
        stripped = raw_line.lstrip(" ")
        indent = len(raw_line) - len(stripped)
        line = stripped if indent <= 3 else raw_line
        if open_len == 0:
            m = re.match(r"^(`{3,})", line)
            if m:
                open_len = len(m.group(1))
            continue
        m = re.match(r"^(`{3,})\s*$", line)
        if m and len(m.group(1)) >= open_len:
            open_len = 0
    return open_len == 0, open_len


# ---------------------------------------------------------------------------
# odoo-code-reviewer.md - Issues table shape (File + Line/Range columns)
# ---------------------------------------------------------------------------


def test_issues_table_header_has_file_and_line_range_columns():
    text = _read(CODE_REVIEWER_AGENT)
    issues_section = re.search(r"### Issues Found\n(.*?)\n\n", text, re.DOTALL)
    assert issues_section, "agents/odoo-code-reviewer.md has no `### Issues Found` section"
    header_match = re.search(r"^\|\s*Severity\s*\|.*\|$", issues_section.group(1), re.MULTILINE)
    assert header_match, (
        "agents/odoo-code-reviewer.md's `### Issues Found` section has no "
        "`| Severity | ... |` table header"
    )
    header = header_match.group(0)
    assert "File" in header, (
        "Issues table header is missing a `File` column - a PR poster cannot anchor an "
        f"inline comment without a diff-relative path. Header found: {header!r}"
    )
    assert "Line/Range" in header, (
        "Issues table header is missing a `Line/Range` column - a PR poster needs a line "
        f"or startLine-endLine to anchor an inline comment. Header found: {header!r}"
    )
    # Regression guard: the old header shape (`Location` standing in for a bare line number,
    # with no separate File column) must be gone from this table.
    assert "| Severity | Location |" not in text, (
        "agents/odoo-code-reviewer.md still has the old `Location`-only table header - "
        "File and Line/Range must be separate columns"
    )


def test_issues_table_file_column_is_repo_relative_not_worktree_absolute():
    text = _read(CODE_REVIEWER_AGENT)
    assert "repo-relative" in text or "repo root" in text, (
        "agents/odoo-code-reviewer.md does not state that `File` must be repo-relative - "
        "without this, a reviewer running in an isolated review_root worktree could emit a "
        "worktree-absolute path that add_comment_to_pending_review cannot anchor"
    )
    assert "worktree absolute path" in text.lower() or "worktree-absolute" in text.lower(), (
        "agents/odoo-code-reviewer.md does not explicitly forbid emitting the worktree "
        "absolute path for `File`"
    )


def test_suggested_replacement_heading_convention_documented():
    text = _read(CODE_REVIEWER_AGENT)
    assert "#### <File>:<Line/Range>" in text, (
        "agents/odoo-code-reviewer.md does not document the `#### <File>:<Line/Range>` "
        "per-finding suggested-replacement heading convention (mirrors odoo-security-audit / "
        "odoo-perf-audit) - without it, a poster has no per-finding anchor for a GitHub "
        "```suggestion fence"
    )
    assert "suggestion" in text.lower(), (
        "agents/odoo-code-reviewer.md does not mention the GitHub ```suggestion fence that "
        "a Suggested replacement block feeds"
    )


def test_output_format_fences_are_balanced():
    """Regression guard: the `## Output format` example template wraps nested
    3-backtick example fences (Suggested-replacement snippet, Fixed Code
    block). A nested fence's own closer must never prematurely close the
    template's OUTER wrapping fence - if it does, everything after it
    (TDD Conformance, Lint gate, Fixed Code, ...) silently drops out of the
    code block, and a later stray fence line can leave the REST OF THE FILE
    swallowed into a bogus open code block. Assert the whole document
    round-trips back to the top-level (no-fence-open) state.
    """
    text = _read(CODE_REVIEWER_AGENT)
    balanced, open_len = _fence_balance_state(text)
    assert balanced, (
        "agents/odoo-code-reviewer.md ends with an unclosed markdown fence "
        f"(opened with {open_len} backticks) - a nested ``` fence inside the "
        "`## Output format` example likely closed the outer wrapping fence "
        "early; widen the outer fence (e.g. ```` or ~~~~) so no inner ``` can "
        "close it, or restructure so no inner fence closes the outer"
    )


def test_suggested_replacement_worked_example_present():
    """The convention must be demonstrated, not just declared - a worked `#### file:line`
    heading followed by a fenced replacement block, matching the pattern in
    odoo-security-audit's vulnerability-taxonomy.md and odoo-perf-audit's output-format.md.
    """
    text = _read(CODE_REVIEWER_AGENT)
    assert re.search(r"^#### [\w./]+:\d+", text, re.MULTILINE), (
        "agents/odoo-code-reviewer.md has no worked `#### <file>:<line>` example heading "
        "demonstrating the suggested-replacement convention"
    )


# ---------------------------------------------------------------------------
# odoo-code-review/SKILL.md - structured hand-off, ALL severities, one summary comment
# ---------------------------------------------------------------------------


def test_skill_does_not_hand_git_ops_a_single_review_body():
    text = _read(CODE_REVIEW_SKILL)
    # The old, now-stale phrasing handed git-ops one blob ("the review body") with no
    # structure. It must be gone; the skill positively forbids it in the new text.
    assert not re.search(r"and the review body;\s*git-ops posts", text), (
        "skills/odoo-code-review/SKILL.md still hands git-ops a single flat review body - "
        "the hand-off must pass STRUCTURED findings (owner/repo/pullNumber + per-finding "
        "File/Line/Range), not a blob"
    )
    assert "Do NOT hand over a single review body" in text, (
        "skills/odoo-code-review/SKILL.md does not positively forbid handing git-ops a "
        "single review body"
    )


def test_skill_passes_structured_owner_repo_pull_number():
    text = _read(CODE_REVIEW_SKILL)
    for token in ("owner", "repo", "pullNumber"):
        assert token in text, (
            f"skills/odoo-code-review/SKILL.md's PR-posting hand-off is missing `{token}` - "
            "git-ops needs owner/repo/pullNumber to address the GitHub review API, not a "
            "bare PR number"
        )
    assert "fullName" in text and "/" in text, (
        "skills/odoo-code-review/SKILL.md does not derive owner/repo by splitting the "
        "scope's PR metadata `repo: <fullName>` on `/`"
    )


def test_skill_posts_every_severity_inline_option_a():
    """B6 = option A: every severity (CRITICAL..LOW) is its own inline comment - no
    severity filtering in the fan-out. This is the decided, non-negotiable contract.
    """
    text = _read(CODE_REVIEW_SKILL)
    assert "EVERY severity" in text, (
        "skills/odoo-code-review/SKILL.md does not require EVERY severity to be posted "
        "inline (option A) - dropping LOW findings from the inline fan-out was rejected"
    )
    assert re.search(r"CRITICAL\s+through\s+LOW", text) or "CRITICAL..LOW" in text, (
        "skills/odoo-code-review/SKILL.md does not spell out the full CRITICAL-to-LOW "
        "severity range for the inline fan-out"
    )
    assert "no finding is dropped" in text, (
        "skills/odoo-code-review/SKILL.md does not state that no finding is dropped from "
        "the inline fan-out"
    )


def test_skill_handoff_specifies_structured_finding_shape():
    """The hand-off must specify the exact per-finding shape the generic,
    dependency-free `github-operator` fan-out recipe consumes - built by THIS
    skill (owner of the Odoo-specific Issues-table shape) from the Issues
    table + Suggested-replacement blocks, never left for git-ops/
    github-operator to infer from Odoo vocabulary they do not know.
    """
    text = _read(CODE_REVIEW_SKILL)
    assert "findings[]" in text, (
        "skills/odoo-code-review/SKILL.md does not name a structured "
        "`findings[]` array as the hand-off payload"
    )
    for field in ("path", "startLine", "line", "severity", "body", "suggestion"):
        assert re.search(rf"`{field}`", text), (
            f"skills/odoo-code-review/SKILL.md does not document the finding "
            f"field `{field}` in the structured hand-off shape"
        )
    assert "Issues-table row" in text and "Line/Range" in text, (
        "skills/odoo-code-review/SKILL.md does not state that findings[] is "
        "built from the Issues-table rows' File/Line/Range columns"
    )
    assert "#### <File>:<Line/Range>" in text, (
        "skills/odoo-code-review/SKILL.md does not state that the optional "
        "`suggestion` field is sourced from the `#### <File>:<Line/Range>` "
        "Suggested-replacement blocks"
    )


def test_skill_verdict_is_one_separate_top_level_comment():
    text = _read(CODE_REVIEW_SKILL)
    assert "separate top-level PR comment" in text, (
        "skills/odoo-code-review/SKILL.md must post the verdict/score as ONE separate "
        "top-level comment - never folded into or substituting the per-finding inline "
        "comments"
    )
    assert "never a substitute for the per-finding inline comments" in text, (
        "skills/odoo-code-review/SKILL.md does not state the summary comment is never a "
        "substitute for the per-finding inline comments"
    )


def test_skill_submit_event_depends_on_critical_high():
    text = _read(CODE_REVIEW_SKILL)
    assert "REQUEST_CHANGES" in text and "COMMENT" in text, (
        "skills/odoo-code-review/SKILL.md does not wire the submit event "
        "(REQUEST_CHANGES when CRITICAL/HIGH remains, else COMMENT)"
    )


# ---------------------------------------------------------------------------
# references/agent-prompts.md - templates instruct the dispatched reviewer to
# populate File + Line/Range + the Suggested replacement block
# ---------------------------------------------------------------------------


def test_agent_prompts_templates_populate_file_and_line_range():
    text = _read(AGENT_PROMPTS_REF)
    occurrences = text.count(
        "Populate the Issues table `File` + `Line/Range` for EVERY finding"
    )
    assert occurrences >= 3, (
        "skills/odoo-code-review/references/agent-prompts.md must instruct the per-module, "
        "synthesis, AND domain templates to populate File + Line/Range for every finding "
        f"(found {occurrences} occurrence(s), need >= 3)"
    )
