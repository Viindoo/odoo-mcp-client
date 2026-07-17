"""Behavior tests for scripts/lib/resolve_project_dir.sh + scripts/lib/paths.py -
the Tier-2 SHARE/ISOLATE state-root resolver pair (Problem 3 core; see
snippets/state-root-resolution.md for the full policy these protect).

Business rules protected, NOT the implementation:
  - Shell/Python PARITY is a stated invariant - both resolvers must print the
    IDENTICAL absolute path for the same repo/worktree/mode.
  - SHARE converges: every linked worktree of ONE repo resolves to the SAME
    SHARE dir; two SEPARATE repos never share one.
  - ISOLATE diverges: two worktrees of the same repo (including the principal
    checkout) each get a DISTINCT ISOLATE dir, nested under the shared SHARE
    dir's `worktrees/` subtree.
  - The non-git fallback walks UP to a project marker (`__manifest__.py` or
    `.odoo-ai-root`) rather than ever hashing the cwd directly - a directory
    with a marker resolves; a directory with NO marker anywhere above it
    REFUSES (non-zero exit / raises), instead of silently keying on $PWD.

Hermetic: every test runs against a throwaway $ODOO_AI_HOME under tmp_path and
throwaway git repos/worktrees under tmp_path - never the real $HOME, never
this repo's own git state.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
SH = LIB_DIR / "resolve_project_dir.sh"
PY = LIB_DIR / "paths.py"

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")

_GIT_ENV_EXTRA = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@test.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@test.invalid",
    # Never let a real global .gitconfig / hooks leak into a throwaway test repo.
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _env(home: Path, **extra) -> dict:
    """A clean subprocess env: throwaway $ODOO_AI_HOME/$HOME, no override vars
    leaking in from the invoking shell, so every path is fully hermetic."""
    e = dict(os.environ)
    for var in ("ODOO_AI_HOME", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR", "ODOO_AI_INSTANCES"):
        e.pop(var, None)
    e["ODOO_AI_HOME"] = str(home)
    e["HOME"] = str(home)  # never touch the real ~/.odoo-ai
    e.update(_GIT_ENV_EXTRA)
    e.update(extra)
    return e


def _git(args, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        env=env or {**os.environ, **_GIT_ENV_EXTRA},
    )


def _init_repo(path: Path) -> None:
    """A minimal git repo with one commit (worktree add needs a real HEAD)."""
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **_GIT_ENV_EXTRA}
    assert _git(["init", "-q"], path, env).returncode == 0
    (path / "README.md").write_text("x", encoding="utf-8")
    assert _git(["add", "README.md"], path, env).returncode == 0
    r = _git(["commit", "-q", "-m", "init"], path, env)
    assert r.returncode == 0, r.stderr


def _add_worktree(repo: Path, wt_path: Path) -> None:
    env = {**os.environ, **_GIT_ENV_EXTRA}
    r = _git(["worktree", "add", "-q", str(wt_path)], repo, env)
    assert r.returncode == 0, r.stderr


def _sh_resolve(mode: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SH), mode], cwd=cwd, capture_output=True, text=True, env=env)


def _py_resolve(mode: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PY), mode], cwd=cwd, capture_output=True, text=True, env=env
    )


# --------------------------------------------------------------------------- #
# static sanity: both files are syntactically valid and importable
# --------------------------------------------------------------------------- #
def test_shell_lib_parses():
    r = subprocess.run(["bash", "-n", str(SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_python_lib_imports_and_exposes_the_contract():
    spec = importlib.util.spec_from_file_location("paths_under_test", PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.share_dir)
    assert callable(mod.isolate_dir)
    assert issubclass(mod.ProjectDirError, RuntimeError)


# --------------------------------------------------------------------------- #
# shell/Python parity (INVARIANT)
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_shell_and_python_agree_on_share_and_isolate(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    env = _env(home)
    for mode in ("share", "isolate"):
        sh = _sh_resolve(mode, repo, env)
        py = _py_resolve(mode, repo, env)
        assert sh.returncode == 0, sh.stderr
        assert py.returncode == 0, py.stderr
        assert sh.stdout.strip() == py.stdout.strip(), (
            f"{mode}: shell={sh.stdout.strip()!r} python={py.stdout.strip()!r}"
        )


@requires_bash
@requires_git
def test_shell_and_python_agree_from_a_linked_worktree(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    env = _env(home)
    for mode in ("share", "isolate"):
        sh = _sh_resolve(mode, wt, env)
        py = _py_resolve(mode, wt, env)
        assert sh.returncode == 0, sh.stderr
        assert py.returncode == 0, py.stderr
        assert sh.stdout.strip() == py.stdout.strip()


# --------------------------------------------------------------------------- #
# C-3: resolving from a git-checkout SUBDIRECTORY (not just the root) - the
# most version-fragile behavior. `git rev-parse --git-common-dir` returns a
# CWD-RELATIVE `../.git` from a main-checkout subdir (vs plain `.git` at the
# root); `cd "$common" && pwd -P` / os.path.realpath must normalize both forms
# to the SAME absolute key. Every other git test in this file resolves from a
# repo/worktree ROOT only - these lock in the subdir case explicitly so a
# regression (or an old git emitting a different relative form) cannot stay
# green while a real subdir invocation (the common case - an agent's Bash
# tool cwd is often e.g. plugins/odoo-ai-agents/) silently breaks.
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_share_and_isolate_resolve_identically_from_a_repo_subdir(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    subdir = repo / "plugins" / "odoo-ai-agents"
    subdir.mkdir(parents=True)
    env = _env(home)

    for mode in ("share", "isolate"):
        from_root = _sh_resolve(mode, repo, env)
        from_sub = _sh_resolve(mode, subdir, env)
        assert from_root.returncode == 0, from_root.stderr
        assert from_sub.returncode == 0, from_sub.stderr
        assert from_root.stdout.strip() == from_sub.stdout.strip(), (
            f"{mode}: root={from_root.stdout.strip()!r} subdir={from_sub.stdout.strip()!r}"
        )


@requires_bash
@requires_git
def test_shell_and_python_agree_from_a_repo_subdir(tmp_path):
    """C-3 parity: shell's cwd-relative `../.git` handling and Python's
    `os.path.realpath` must agree from a repo SUBDIRECTORY, not just the root
    (test_shell_and_python_agree_on_share_and_isolate only covers the root)."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    subdir = repo / "plugins" / "odoo-ai-agents"
    subdir.mkdir(parents=True)
    env = _env(home)

    for mode in ("share", "isolate"):
        sh = _sh_resolve(mode, subdir, env)
        py = _py_resolve(mode, subdir, env)
        assert sh.returncode == 0, sh.stderr
        assert py.returncode == 0, py.stderr
        assert sh.stdout.strip() == py.stdout.strip(), (
            f"{mode}: shell={sh.stdout.strip()!r} python={py.stdout.strip()!r}"
        )


@requires_bash
@requires_git
def test_share_and_isolate_resolve_identically_from_a_worktree_subdir(tmp_path):
    """C-3, extended to a linked worktree per the review's required fix: a
    worktree's `--git-common-dir` is already absolute (`/repo/.git`), but the
    subdir-vs-root convergence must still hold for the worktree checkout
    itself, not just the principal checkout."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    subdir = wt / "plugins" / "odoo-ai-agents"
    subdir.mkdir(parents=True)
    env = _env(home)

    for mode in ("share", "isolate"):
        from_root = _sh_resolve(mode, wt, env)
        from_sub = _sh_resolve(mode, subdir, env)
        assert from_root.returncode == 0, from_root.stderr
        assert from_sub.returncode == 0, from_sub.stderr
        assert from_root.stdout.strip() == from_sub.stdout.strip(), (
            f"{mode}: root={from_root.stdout.strip()!r} subdir={from_sub.stdout.strip()!r}"
        )


@requires_bash
@requires_git
def test_shell_and_python_agree_from_a_worktree_subdir(tmp_path):
    """C-3 parity, worktree-subdir variant."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    subdir = wt / "plugins" / "odoo-ai-agents"
    subdir.mkdir(parents=True)
    env = _env(home)

    for mode in ("share", "isolate"):
        sh = _sh_resolve(mode, subdir, env)
        py = _py_resolve(mode, subdir, env)
        assert sh.returncode == 0, sh.stderr
        assert py.returncode == 0, py.stderr
        assert sh.stdout.strip() == py.stdout.strip(), (
            f"{mode}: shell={sh.stdout.strip()!r} python={py.stdout.strip()!r}"
        )


# --------------------------------------------------------------------------- #
# SHARE: converges across worktrees of one repo, isolates across repos
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_share_dir_converges_across_linked_worktrees(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    env = _env(home)

    share_main = _sh_resolve("share", repo, env)
    share_wt = _sh_resolve("share", wt, env)
    assert share_main.returncode == 0, share_main.stderr
    assert share_wt.returncode == 0, share_wt.stderr
    assert share_main.stdout.strip() == share_wt.stdout.strip()


@requires_bash
@requires_git
def test_share_dir_differs_across_separate_repos(tmp_path):
    home = tmp_path / "home"
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _init_repo(repo1)
    _init_repo(repo2)
    env = _env(home)

    s1 = _sh_resolve("share", repo1, env)
    s2 = _sh_resolve("share", repo2, env)
    assert s1.returncode == 0, s1.stderr
    assert s2.returncode == 0, s2.stderr
    assert s1.stdout.strip() != s2.stdout.strip()


# --------------------------------------------------------------------------- #
# ISOLATE: distinct per worktree, nested under the shared SHARE dir
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_isolate_dir_differs_per_worktree(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    env = _env(home)

    iso_main = _sh_resolve("isolate", repo, env)
    iso_wt = _sh_resolve("isolate", wt, env)
    assert iso_main.returncode == 0, iso_main.stderr
    assert iso_wt.returncode == 0, iso_wt.stderr
    assert iso_main.stdout.strip() != iso_wt.stdout.strip()

    share = _sh_resolve("share", repo, env).stdout.strip()
    assert iso_main.stdout.strip().startswith(share + "/worktrees/")
    assert iso_wt.stdout.strip().startswith(share + "/worktrees/")


@requires_bash
@requires_git
def test_isolate_dir_stable_for_the_same_worktree_across_calls(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    env = _env(home)
    a = _sh_resolve("isolate", repo, env).stdout.strip()
    b = _sh_resolve("isolate", repo, env).stdout.strip()
    assert a and a == b


# --------------------------------------------------------------------------- #
# override env vars win verbatim
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_explicit_project_dir_override_wins(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    override = tmp_path / "explicit-share"
    env = _env(home, ODOO_AI_PROJECT_DIR=str(override))
    sh = _sh_resolve("share", repo, env)
    assert sh.returncode == 0, sh.stderr
    assert sh.stdout.strip() == str(override)
    assert override.is_dir()


@requires_bash
@requires_git
def test_explicit_worktree_dir_override_wins(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    override = tmp_path / "explicit-isolate"
    env = _env(home, ODOO_AI_WORKTREE_DIR=str(override))
    sh = _sh_resolve("isolate", repo, env)
    assert sh.returncode == 0, sh.stderr
    assert sh.stdout.strip() == str(override)
    assert override.is_dir()


# --------------------------------------------------------------------------- #
# non-git fallback: walk-up marker resolves; no marker REFUSES (never $PWD)
# --------------------------------------------------------------------------- #
@requires_bash
def test_nongit_dir_with_manifest_marker_resolves_via_walkup(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "standalone_module"
    deep = proj / "sub" / "deeper"
    deep.mkdir(parents=True)
    (proj / "__manifest__.py").write_text("{}", encoding="utf-8")
    env = _env(home)

    sh = _sh_resolve("share", deep, env)
    assert sh.returncode == 0, sh.stderr
    py = _py_resolve("share", deep, env)
    assert py.returncode == 0, py.stderr
    assert sh.stdout.strip() == py.stdout.strip()

    # Resolving from a DIFFERENT subdirectory of the SAME marker root must
    # yield the SAME key - proves it hashes the marker root, not raw cwd.
    other_sub = proj / "other"
    other_sub.mkdir()
    sh2 = _sh_resolve("share", other_sub, env)
    assert sh2.returncode == 0, sh2.stderr
    assert sh2.stdout.strip() == sh.stdout.strip()


@requires_bash
def test_nongit_dir_with_sentinel_marker_resolves(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "sentinel_project"
    sub = proj / "sub"
    sub.mkdir(parents=True)
    (proj / ".odoo-ai-root").write_text("", encoding="utf-8")
    env = _env(home)

    sh = _sh_resolve("share", sub, env)
    assert sh.returncode == 0, sh.stderr
    py = _py_resolve("share", sub, env)
    assert py.returncode == 0, py.stderr
    assert sh.stdout.strip() == py.stdout.strip()


@requires_bash
def test_nongit_sentinel_root_wins_over_nearer_manifests(tmp_path):
    """C-2: a `.odoo-ai-root` sentinel at the project root must WIN over ANY
    nearer `__manifest__.py` - real Odoo addons layouts put a manifest in
    EVERY module dir, so "nearest marker of either kind wins" would mis-root:
    two modules of the SAME project would resolve to two DIFFERENT keys
    instead of converging on the project root. Two module manifests nested
    below one root sentinel must BOTH resolve to the ROOT's key, proving the
    sentinel has global walk-up priority, not just nearest-wins."""
    home = tmp_path / "home"
    proj = tmp_path / "multi_module_project"
    module_a = proj / "addons" / "sale_extra"
    module_b = proj / "addons" / "purchase_extra"
    module_a.mkdir(parents=True)
    module_b.mkdir(parents=True)
    (proj / ".odoo-ai-root").write_text("", encoding="utf-8")
    (module_a / "__manifest__.py").write_text("{}", encoding="utf-8")
    (module_b / "__manifest__.py").write_text("{}", encoding="utf-8")
    env = _env(home)

    from_root = _sh_resolve("share", proj, env)
    from_a = _sh_resolve("share", module_a, env)
    from_b = _sh_resolve("share", module_b, env)
    assert from_root.returncode == 0, from_root.stderr
    assert from_a.returncode == 0, from_a.stderr
    assert from_b.returncode == 0, from_b.stderr
    assert from_root.stdout.strip() == from_a.stdout.strip() == from_b.stdout.strip(), (
        "the .odoo-ai-root sentinel must win over every nearer module manifest"
    )

    py_from_a = _py_resolve("share", module_a, env)
    assert py_from_a.returncode == 0, py_from_a.stderr
    assert py_from_a.stdout.strip() == from_a.stdout.strip()


@requires_bash
def test_nongit_dir_with_no_marker_refuses_not_pwd(tmp_path):
    """No git repo AND no marker anywhere up to `/`: both resolvers must REFUSE
    (non-zero exit / raise) rather than ever hashing the bare cwd."""
    home = tmp_path / "home"
    empty = tmp_path / "empty_dir_with_no_marker"
    empty.mkdir()
    env = _env(home)

    sh = _sh_resolve("share", empty, env)
    assert sh.returncode != 0
    assert sh.stdout.strip() == ""
    assert "ODOO_AI_PROJECT_DIR" in sh.stderr

    py = _py_resolve("share", empty, env)
    assert py.returncode != 0
    assert py.stdout.strip() == ""


def test_nongit_dir_with_no_marker_raises_project_dir_error(tmp_path):
    """Same refusal, exercised via the importable Python API (not the CLI), so
    callers that `import paths` get a catchable exception, not a bare exit."""
    home = tmp_path / "home"
    empty = tmp_path / "empty_dir_with_no_marker"
    empty.mkdir()
    env = _env(home)

    old_cwd = os.getcwd()
    old_env = {k: os.environ.get(k) for k in env}
    try:
        os.chdir(empty)
        os.environ.update(env)
        spec = importlib.util.spec_from_file_location("paths_under_test_2", PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with pytest.raises(mod.ProjectDirError):
            mod.share_dir()
        with pytest.raises(mod.ProjectDirError):
            mod.isolate_dir()
    finally:
        os.chdir(old_cwd)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@requires_bash
def test_pwd_instability_never_changes_the_key(tmp_path):
    """A stronger cwd-stability guard than the walk-up test above: resolving
    from `<proj>` and from `<proj>/sub` (two DIFFERENT $PWD values under the
    same marker root) must yield the IDENTICAL key - the classic
    cwd-hash bug this design explicitly rejects (C-9)."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    sub = proj / "sub"
    sub.mkdir(parents=True)
    (proj / "__manifest__.py").write_text("{}", encoding="utf-8")
    env = _env(home)

    from_root = _sh_resolve("share", proj, env)
    from_sub = _sh_resolve("share", sub, env)
    assert from_root.returncode == 0, from_root.stderr
    assert from_sub.returncode == 0, from_sub.stderr
    assert from_root.stdout.strip() == from_sub.stdout.strip()
