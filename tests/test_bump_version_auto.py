"""Behavior tests for `scripts/bump-version.sh auto` (the version-bump classifier).

These protect the OPERATIONAL versioning policy, not the script's internals:

    new command / skill / agent or a `feat:` commit  -> MINOR
    bug fix / refactor / docs / chore / internal      -> PATCH (the default)
    breaking change (`type!:` or `BREAKING CHANGE:`)   -> MAJOR
    an explicit X.Y.Z (human names a version in NL)    -> honored verbatim

Each test stands up a throwaway git repo in `tmp_path`, seeds a `VERSION` file as
the classifier's anchor commit, then adds commits/files to drive ONE rule and runs
`bump-version.sh auto --dry-run` with cwd set to that repo. `--dry-run` writes
nothing, so the tests need no real repo layout (no plugin.json / CHANGELOG). We
assert only the SUGGESTED level parsed from stdout, so the tests stay decoupled
from how the script computes it. stdlib + subprocess only.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUMP = ROOT / "scripts" / "bump-version.sh"

# stdout line emitted by the script: "dry-run: would bump 1.2.3 -> 1.3.0 (level: minor)"
_DRYRUN = re.compile(
    r"would bump\s+(?P<cur>\d+\.\d+\.\d+)\s*->\s*(?P<new>\d+\.\d+\.\d+)\s*\(level:\s*(?P<level>[^)]+)\)"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _init_repo(tmp_path: Path, version: str = "1.2.3") -> Path:
    """Throwaway git repo whose anchor commit creates VERSION=version."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "VERSION").write_text(version + "\n", encoding="utf-8")
    _git(repo, "add", "VERSION")
    _git(repo, "commit", "-q", "-m", "chore: seed VERSION")
    return repo


def _commit(repo: Path, subject: str, body: str = "", *, touch: str = "noise.txt") -> None:
    """Make an empty-ish content change and commit it with the given message."""
    p = repo / touch
    p.parent.mkdir(parents=True, exist_ok=True)
    # append so repeated calls to the same path still produce a change
    with p.open("a", encoding="utf-8") as fh:
        fh.write(subject + "\n")
    _git(repo, "add", "-A")
    args = ["commit", "-q", "-m", subject]
    if body:
        args += ["-m", body]
    _git(repo, *args)


def _run_auto_dryrun(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(BUMP), *(extra or ("auto", "--dry-run"))],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _suggested_level(proc: subprocess.CompletedProcess) -> str:
    assert proc.returncode == 0, f"script failed: {proc.stderr or proc.stdout}"
    m = _DRYRUN.search(proc.stdout)
    assert m, f"no dry-run suggestion line in stdout:\n{proc.stdout}\n{proc.stderr}"
    return m.group("level").strip()


def test_feat_commit_suggests_minor(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: add a shiny new capability")
    assert _suggested_level(_run_auto_dryrun(repo)) == "minor"


def test_fix_only_suggests_patch(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "fix: correct an off-by-one")
    _commit(repo, "refactor: tidy internals", touch="other.txt")
    assert _suggested_level(_run_auto_dryrun(repo)) == "patch"


def test_new_skill_file_suggests_minor(tmp_path):
    repo = _init_repo(tmp_path)
    # A new skill added under skills/ must read as MINOR even when the commit type
    # is a non-feat (here `chore:`) - the added-path rule, not the subject, drives it.
    _commit(repo, "chore: add skill", touch="skills/foo/SKILL.md")
    assert _suggested_level(_run_auto_dryrun(repo)) == "minor"


def test_breaking_bang_commit_suggests_major(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat!: drop the legacy interface")
    assert _suggested_level(_run_auto_dryrun(repo)) == "major"


def test_breaking_change_footer_suggests_major(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "refactor: rework engine", body="BREAKING CHANGE: removed public method")
    assert _suggested_level(_run_auto_dryrun(repo)) == "major"


def test_breaking_change_hyphen_footer_suggests_major(tmp_path):
    # Conventional Commits treats `BREAKING-CHANGE:` as a synonym of `BREAKING CHANGE:`.
    repo = _init_repo(tmp_path)
    _commit(repo, "refactor: rework engine", body="BREAKING-CHANGE: dropped a public method")
    assert _suggested_level(_run_auto_dryrun(repo)) == "major"


def test_breaking_prose_without_colon_is_not_major(tmp_path):
    # A body line that merely STARTS with the words "BREAKING CHANGE" (no `: ` footer
    # delimiter) is prose, not a footer, and must NOT inflate the bump to major.
    repo = _init_repo(tmp_path)
    _commit(repo, "docs: note upcoming work", body="BREAKING CHANGE notes will follow later")
    assert _suggested_level(_run_auto_dryrun(repo)) == "patch"


def test_explicit_version_is_honored(tmp_path):
    """NL-override path: an explicit X.Y.Z is its OWN level argument (separate from
    `auto`) and the script honors it verbatim. Asserts the explicit arm only - it does
    not exercise auto-vs-explicit precedence (they are distinct invocations)."""
    repo = _init_repo(tmp_path, version="1.2.3")
    _commit(repo, "fix: something small")  # auto would say patch
    proc = _run_auto_dryrun(repo, "9.9.9", "--dry-run")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    m = _DRYRUN.search(proc.stdout)
    assert m, f"no dry-run line:\n{proc.stdout}\n{proc.stderr}"
    assert m.group("new") == "9.9.9", proc.stdout


def test_no_commits_since_anchor_defaults_to_patch(tmp_path):
    """Empty range (nothing since the VERSION anchor) is the safe default: patch."""
    repo = _init_repo(tmp_path)
    assert _suggested_level(_run_auto_dryrun(repo)) == "patch"
