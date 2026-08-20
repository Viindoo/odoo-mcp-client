"""Guard the coordinate system every DIFF-SCOPED lint rule in
`generator/check_orchestration.py` depends on.

## The defect this test exists to prevent

`_added_lines_since(base)` answers "which line numbers did this change ADD?", and its callers
(today `[version-claim]`, rule 18) map each number back to a line of the WORKING-TREE file and
report the prose they find there. That only holds if the numbers index the working tree.

The pre-fix implementation unioned TWO diffs in two different coordinate systems:
`git diff base...HEAD` (numbers relative to HEAD) and `git diff HEAD` (numbers relative to the
working tree). While a tree is clean the two agree, so the bug is invisible. The moment an
uncommitted edit INSERTS lines above content an earlier branch commit added, every HEAD-relative
number keeps pointing at its old position - which now holds whatever content shifted down into
it - and the rule reports untouched prose as newly added.

Measured on the branch that found this: two `[version-claim]` STRICT findings against prose the
change never touched (a `v19+` load-language row and a `--no-http v11+` note), while both HEAD
lines with those numbers were boundary-SSOT pointers carrying no version token at all. A STRICT
finding that names innocent prose is worse than no rule: the only way to "fix" it is to reword
someone else's correct sentence.

## Chosen formulation

Behavioural, over a real throwaway git repo, and asserted as the INVARIANT rather than as one
reproduction: every line number reported must name genuinely-added content in the working-tree
file, and a line that is untouched-but-shifted must NOT be reported. Written this way the test
fails for ANY future implementation that mixes coordinate systems, not only for the two-diff
shape that caused it.

Run: python -m pytest tests/test_diff_scoped_line_attribution.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402

SENTINEL_UNTOUCHED = "orig-8"
BRANCH_ADDED = "branch-added-by-an-earlier-commit"
WORKTREE_ADDED = ("worktree-added-1", "worktree-added-2", "worktree-added-3")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, timeout=60,
    )


@pytest.fixture
def shifted_repo(tmp_path):
    """A repo in the exact shape that separates the two coordinate systems:

    base commit   -> 10 plain lines
    branch commit -> one line APPENDED (high line number in HEAD coordinates)
    working tree  -> three lines INSERTED near the top, shifting everything below

    The branch-added line therefore sits at a DIFFERENT number in HEAD than in the working tree,
    and HEAD's number lands on an untouched line.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "guard@example.invalid")
    _git(repo, "config", "user.name", "guard")
    target = repo / "doc.md"

    base_lines = [f"orig-{n}" for n in range(1, 11)]
    target.write_text("\n".join(base_lines) + "\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    target.write_text("\n".join(base_lines + [BRANCH_ADDED]) + "\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "branch commit appends a line")

    shifted = [base_lines[0], *WORKTREE_ADDED, *base_lines[1:], BRANCH_ADDED]
    target.write_text("\n".join(shifted) + "\n", encoding="utf-8")
    return repo, base_sha, target, shifted


def test_added_line_numbers_index_the_working_tree_not_head(shifted_repo, monkeypatch):
    """The invariant: every reported number must name content this change really added,
    read from the file the callers read - the working tree."""
    repo, base_sha, target, shifted = shifted_repo
    monkeypatch.setattr(co, "REPO_ROOT", repo)

    reported = co._added_lines_since(base_sha).get("doc.md", set())
    assert reported, "the change added lines; reporting none would make every diff-scoped rule blind"

    genuinely_added = {BRANCH_ADDED, *WORKTREE_ADDED}
    misattributed = {
        n: shifted[n - 1] for n in sorted(reported)
        if not (1 <= n <= len(shifted)) or shifted[n - 1] not in genuinely_added
    }
    assert not misattributed, (
        "every added-line number must name genuinely added content in the WORKING-TREE file; "
        f"these named untouched (or out-of-range) lines instead: {misattributed}"
    )

    # The specific shape the mix produced: HEAD's number for the branch-added line
    # (11, since HEAD has 10 original lines + 1) now holds untouched content.
    assert shifted[10] == SENTINEL_UNTOUCHED, "fixture drift: line 11 must be the untouched sentinel"
    assert 11 not in reported, (
        f"line 11 holds {SENTINEL_UNTOUCHED!r} in the working tree - untouched, merely shifted "
        "down. Reporting it is the coordinate-system mix, and it is what makes a STRICT rule "
        "accuse prose the change never edited"
    )

    # ... and the line that genuinely carries the branch commit's addition IS reported.
    assert len(shifted) in reported, (
        f"the branch-added line now sits at {len(shifted)} in the working tree and must still be "
        "attributed - the fix must not trade a false positive for a false negative"
    )
