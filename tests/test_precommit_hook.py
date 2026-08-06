"""Behavior tests for `.githooks/pre-commit` (the confidentiality guard).

These protect what the guard must DO, not how it is written:

    a confidential term is rejected from a LINKED WORKTREE   (not just the primary checkout)
    a confidential term is rejected from the PRIMARY checkout
    no patterns.local anywhere -> warn on stderr, structural checks only, exit 0
    the structural rules fire with or without patterns.local
    a term far from EOF is still rejected                    (no size-dependent blind spot)

Two silent-disable defects motivated this file, and both are invisible to a
"does the commit succeed?" eyeball:

  1. `patterns.local` is gitignored, so it exists only in the PRIMARY checkout.
     Resolving it from `git rev-parse --show-toplevel` found nothing from a
     linked worktree - where branch work actually happens - and the hook then
     dropped its project-confidential rules and exited 0, reading exactly like a
     full-strength pass.
  2. Every rule was `printf ... | grep -q ...` under `set -o pipefail`. `grep -q`
     exits at the first match, the writer dies of SIGPIPE, pipefail marks the
     pipeline failed, and the enclosing `if` sees FALSE - so above the ~64KB pipe
     buffer a MATCH became indistinguishable from a NON-MATCH.

Each test stands up a throwaway primary checkout (plus, where relevant, a real
linked worktree) in `tmp_path`, writes a SYNTHETIC patterns file, stages a blob
into an ISOLATED index, and runs the hook. Nothing here reads, copies, or
depends on the real `.githooks/patterns.local`; the terms below are invented.

`HOOK_UNDER_TEST` allows pointing the suite at a candidate hook, which is how a
test is proven capable of failing (run it against the pre-fix hook and cases 1
and 5 must go RED). stdlib + subprocess only.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = Path(os.environ.get("HOOK_UNDER_TEST", ROOT / ".githooks" / "pre-commit"))

# Invented, secret-shaped terms. NEVER copy anything out of the real patterns.local.
SYNTH_TERM = "ACME-QUARTERBRIDGE-XK92"
SYNTH_HOST = "vault-77.internal.example.invalid"

# The piped-grep defect only bites once the writer cannot fit the remainder into
# the pipe buffer (64KiB on Linux), so the far-from-EOF case must clear it well.
PIPE_BUFFER_BYTES = 64 * 1024

# Both structural probes are assembled at runtime on purpose: spelled out as one
# literal, each would trip this hook's own rules when THIS file is staged, and no
# allowlisted placeholder can stand in (the rules exist precisely to let those
# through, so a stand-in would stop the test from testing anything).
_ABS_PATH_PROBE = "see /" + "home/somedev/notes/thing.md for details"
_GMAIL_PROBE = "maintainer: somebody@" + "gmail.com"


def _filler(line: str, min_bytes: int = 4 * PIPE_BUFFER_BYTES) -> str:
    """Repeat `line` until it is comfortably past the pipe buffer.

    Sized in BYTES, not lines: a line-count that happens to fall short of the
    buffer makes the size-dependent tests pass against a buggy hook.
    """
    unit = line + "\n"
    reps = -(-min_bytes // len(unit.encode()))  # ceil division
    out = unit * reps
    assert len(out.encode()) >= min_bytes, "filler must clear the pipe buffer"
    return out


def _env(home: Path) -> dict:
    """Git env isolated from the developer's own config, hooks, and identity."""
    env = dict(os.environ)
    for var in (
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_DIR",
        "GIT_WORK_TREE",
    ):
        env.pop(var, None)
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
    )
    return env


def _git(repo: Path, *args: str, env: dict) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env
    ).stdout.strip()


class Lab:
    """A primary checkout, optionally with a real linked worktree attached."""

    def __init__(self, primary: Path, worktree: Path | None, env: dict, home: Path):
        self.primary = primary
        self.worktree = worktree
        self.env = env
        self.home = home

    @property
    def patterns(self) -> Path:
        return self.primary / ".githooks" / "patterns.local"


def _make_lab(tmp_path: Path, *, with_patterns: bool = True, worktree: bool = True) -> Lab:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True, exist_ok=True)
    env = _env(home)

    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "-q", "-b", "main", env=env)
    _git(primary, "config", "commit.gpgsign", "false", env=env)

    hooks = primary / ".githooks"
    hooks.mkdir()
    shutil.copy2(HOOK, hooks / "pre-commit")
    # patterns.local is gitignored in the real repo; mirror that exactly, since
    # "it is untracked" is the whole reason a worktree cannot see it.
    (primary / ".gitignore").write_text(".githooks/patterns.local\n", encoding="utf-8")
    (primary / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(primary, "add", "-A", env=env)
    _git(primary, "commit", "-q", "-m", "seed", env=env)

    if with_patterns:
        (hooks / "patterns.local").write_text(
            f"# synthetic rules - not real terms\n{SYNTH_TERM}\n{SYNTH_HOST}\n",
            encoding="utf-8",
        )

    wt = None
    if worktree:
        wt = tmp_path / "wt"
        _git(primary, "worktree", "add", "-q", str(wt), "-b", "feature", env=env)

    return Lab(primary, wt, env, home)


def _fresh_index(lab: Lab) -> dict:
    """Env pointing at an empty, isolated index.

    The index lives outside both checkouts so a test can never disturb a real
    staging area, and each call starts from an empty one.
    """
    env = dict(lab.env)
    idx = lab.home / "test-index"
    if idx.exists():
        idx.unlink()
    env["GIT_INDEX_FILE"] = str(idx)
    return env


def _stage_blob(cwd: Path, env: dict, content: str, name: str) -> str:
    """Write a blob and stage it as a regular file. Returns the blob sha."""
    sha = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=cwd,
        input=content,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()
    _git(cwd, "update-index", "--add", "--cacheinfo", f"100644,{sha},{name}", env=env)
    return sha


def _stage_gitlink(cwd: Path, env: dict, name: str, commit_sha: str) -> None:
    """Stage a submodule pointer: mode 160000, pointing at a commit, no blob."""
    _git(cwd, "update-index", "--add", "--cacheinfo", f"160000,{commit_sha},{name}", env=env)


def _exec_hook(cwd: Path, env: dict):
    return subprocess.run(
        ["bash", str(cwd / ".githooks" / "pre-commit")],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_hook(lab: Lab, cwd: Path, content: str, name: str = "candidate.md"):
    """Stage `content` into a fresh isolated index under `cwd`, then run the hook."""
    env = _fresh_index(lab)
    _stage_blob(cwd, env, content, name)
    return _exec_hook(cwd, env)


# --------------------------------------------------------------------------- 1
def test_confidential_term_is_rejected_from_a_linked_worktree(tmp_path):
    """patterns.local lives only in the primary checkout; a worktree commit must
    still be blocked by it. This is the defect that shipped: the hook resolved
    the file relative to the worktree root, found nothing, and exited 0."""
    lab = _make_lab(tmp_path)
    assert not (lab.worktree / ".githooks" / "patterns.local").exists(), (
        "precondition: the worktree must NOT have its own patterns.local, "
        "otherwise this test cannot see the bug"
    )

    proc = _run_hook(lab, lab.worktree, f"intro line\nhost: {SYNTH_TERM}\ntail\n")

    assert proc.returncode == 1, (
        "a confidential term staged from a linked worktree must block the commit; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "confidential term" in proc.stderr
    assert "not found" not in proc.stderr, (
        "the hook fell back to structural-checks-only from the worktree: " + proc.stderr
    )


def test_clean_blob_from_a_linked_worktree_is_accepted(tmp_path):
    """Control for case 1: with the same lab, a clean blob must pass. Without
    this, a hook that rejected everything would satisfy the test above."""
    lab = _make_lab(tmp_path)
    proc = _run_hook(lab, lab.worktree, "a perfectly ordinary line of prose\n")
    assert proc.returncode == 0, f"clean blob must commit: {proc.stderr}"


# --------------------------------------------------------------------------- 2
def test_confidential_term_is_rejected_from_the_primary_checkout(tmp_path):
    lab = _make_lab(tmp_path, worktree=False)
    proc = _run_hook(lab, lab.primary, f"host: {SYNTH_HOST}\n")
    assert proc.returncode == 1, f"expected a block, got {proc.returncode}: {proc.stderr}"
    assert "confidential term" in proc.stderr


# --------------------------------------------------------------------------- 3
def test_missing_patterns_file_warns_and_runs_structural_checks_only(tmp_path):
    """An external contributor has only patterns.local.example. That must warn
    and degrade to the structural rules - never hard-fail their commit - and the
    note must name every path searched so the cause is one read away."""
    lab = _make_lab(tmp_path, with_patterns=False)
    proc = _run_hook(lab, lab.worktree, f"host: {SYNTH_TERM}\n")

    assert proc.returncode == 0, (
        "a missing patterns.local must not block a commit; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "not found" in proc.stderr
    assert "looked in:" in proc.stderr, "the note must say WHERE it looked: " + proc.stderr
    for expected in (str(lab.primary), str(lab.worktree)):
        assert expected in proc.stderr, (
            f"the note must name the {expected} candidate: {proc.stderr}"
        )


# --------------------------------------------------------------------------- 4
def test_structural_rules_fire_without_patterns_local(tmp_path):
    """The generic structural rules carry no project terms, so they must hold
    even when the confidential rule set is unavailable."""
    lab = _make_lab(tmp_path, with_patterns=False)
    proc = _run_hook(lab, lab.worktree, _GMAIL_PROBE + "\n")
    assert proc.returncode == 1, f"the gmail rule must fire: {proc.stderr}"
    assert "gmail" in proc.stderr


# --------------------------------------------------------------------------- 5
def test_term_far_from_eof_is_still_rejected(tmp_path):
    """A match must be detectable at any blob size.

    With the old piped `grep -q`, `grep` exited at the match on line 1 while the
    writer still had megabytes to push; SIGPIPE + pipefail then reported the
    pipeline as failed and the rule silently never fired. The term here sits far
    more than one pipe buffer from EOF, which is the condition that triggered it.
    """
    lab = _make_lab(tmp_path)
    filler = _filler("filler line of perfectly ordinary prose")
    content = f"host: {SYNTH_TERM}\n{filler}"

    proc = _run_hook(lab, lab.worktree, content)

    assert proc.returncode == 1, (
        f"a term {len(filler.encode())} bytes from EOF must still block the commit; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "confidential term" in proc.stderr



@pytest.mark.parametrize(
    "rule_line, filler_line, needle",
    [
        (_GMAIL_PROBE, "filler line of ordinary prose", "gmail"),
        # The absolute-path rule is two greps in series, so its filler has to
        # reach the SECOND one to reproduce the defect: these lines match the
        # first-stage regex and are then excused by the placeholder allowlist.
        # Ordinary prose filler is dropped by the first grep, nothing backs up,
        # and the test would pass against a hook that still has the bug.
        (_ABS_PATH_PROBE, "/home/user/docs/example/", "non-portable"),
    ],
)
def test_structural_rules_also_survive_a_large_blob(tmp_path, rule_line, filler_line, needle):
    """Case 5's sibling: the size-dependent blind spot hit EVERY rule, not just
    the confidential-term loop, so the structural ones are pinned down too."""
    lab = _make_lab(tmp_path)
    filler = _filler(filler_line)
    proc = _run_hook(lab, lab.worktree, f"{rule_line}\n{filler}")
    assert proc.returncode == 1, f"{needle} rule must fire on a large blob: {proc.stderr}"
    assert needle in proc.stderr


def test_large_clean_blob_is_still_accepted(tmp_path):
    """Control for case 5: the size fix must not turn big files into false
    positives."""
    lab = _make_lab(tmp_path)
    proc = _run_hook(lab, lab.worktree, _filler("ordinary prose line"))
    assert proc.returncode == 0, f"a large clean blob must commit: {proc.stderr}"


# ------------------------------------------------------- unreadable vs no-blob
# The hook must tell THREE states apart, not two: an entry that legitimately has
# no blob, a blob that reads fine, and a read that failed. Collapsing the last
# two is the same silent-pass shape as the pipefail defect - the guard reports
# nothing and the commit sails through.
def test_unreadable_staged_entry_blocks_the_commit(tmp_path):
    """A staged regular file whose blob cannot be read must BLOCK.

    Built by staging a normal file and then removing its object from the store,
    so the index entry points at nothing - the shape a corrupted or pruned object
    takes. The old `content=... || continue` skipped it silently, which made an
    unscannable file indistinguishable from a clean one.
    """
    lab = _make_lab(tmp_path)
    env = _fresh_index(lab)
    sha = _stage_blob(lab.worktree, env, "ordinary content\n", "vanished.md")

    # A linked worktree shares the primary checkout's object store.
    obj = lab.primary / ".git" / "objects" / sha[:2] / sha[2:]
    assert obj.exists(), "precondition: the blob must be a loose object we can remove"
    obj.unlink()

    proc = _exec_hook(lab.worktree, env)

    assert proc.returncode == 1, (
        "an unreadable staged entry must block the commit, not be skipped; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "vanished.md" in proc.stderr, "the blocking message must name the file"
    assert "read" in proc.stderr.lower(), (
        "the message must say the READ failed, so it is not mistaken for a content "
        f"match: {proc.stderr}"
    )


def test_submodule_gitlink_entry_does_not_block(tmp_path):
    """Control: an entry with no blob BY DESIGN must pass without blocking.

    The gitlink points at a commit whose AUTHOR address would trip the gmail
    rule. `git show` on a gitlink succeeds and prints that commit's metadata
    rather than file content, so a hook that scans gitlinks blocks the commit
    over an address that appears in no file in this repo. Passing here means the
    entry was skipped, not merely that it happened to look clean.
    """
    lab = _make_lab(tmp_path)
    env_with_gmail_author = dict(lab.env)
    env_with_gmail_author["GIT_AUTHOR_EMAIL"] = _GMAIL_PROBE.split()[-1]
    _git(
        lab.primary,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "pointee commit",
        env=env_with_gmail_author,
    )
    pointee = _git(lab.primary, "rev-parse", "HEAD", env=lab.env)

    env = _fresh_index(lab)
    _stage_gitlink(lab.worktree, env, "vendor-sub", pointee)
    proc = _exec_hook(lab.worktree, env)

    assert proc.returncode == 0, (
        "a submodule gitlink has no blob to scan and must not block; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "vendor-sub" not in proc.stderr, (
        "the gitlink must not be scanned at all: " + proc.stderr
    )


def test_a_renamed_and_edited_file_is_still_scanned(tmp_path):
    """A staged rename must not carry unscanned content into the repo.

    Git pairs a staged delete+add into ONE `R` record, which `--diff-filter=AM`
    excludes - so `git mv` plus an edit produced a staged blob the hook listed
    nowhere and never scanned, while exiting 0. This stages exactly that shape
    through the real porcelain rather than by hand, so it stays honest about what
    git actually reports.
    """
    lab = _make_lab(tmp_path)
    wt = lab.worktree
    body = "".join(f"line {i} of ordinary content\n" for i in range(40))
    (wt / "doc.md").write_text(body, encoding="utf-8")
    _git(wt, "add", "doc.md", env=lab.env)
    _git(wt, "commit", "-q", "-m", "add doc", env=lab.env)

    env = _fresh_index(lab)
    _git(wt, "read-tree", "HEAD", env=env)
    _git(wt, "mv", "doc.md", "moved.md", env=env)
    (wt / "moved.md").write_text(body + f"token: {SYNTH_TERM}\n", encoding="utf-8")
    _git(wt, "add", "-A", env=env)

    proc = _exec_hook(wt, env)

    assert proc.returncode == 1, (
        "a renamed-and-edited file carries staged content and must be scanned; "
        f"got exit {proc.returncode}\nstderr: {proc.stderr}"
    )
    assert "confidential term" in proc.stderr


def test_a_readable_blob_is_still_scanned_after_the_skip_logic(tmp_path):
    """Control for both of the above: normal files must still be scanned.

    A hook that skipped too eagerly would satisfy the gitlink test and quietly
    stop guarding everything else.
    """
    lab = _make_lab(tmp_path)
    proc = _run_hook(lab, lab.worktree, f"token: {SYNTH_TERM}\n")
    assert proc.returncode == 1, f"a normal blob must still be scanned: {proc.stderr}"
    assert "confidential term" in proc.stderr
