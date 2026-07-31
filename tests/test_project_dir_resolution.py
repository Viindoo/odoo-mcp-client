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
# override trailing-slash normalisation parity (table-driven: add a suffix to
# _TRAILING_SLASH_SUFFIXES to cover a new input class for free)
#
# A doubled/tripled trailing slash on an override denotes the SAME directory
# as the bare path (POSIX: "/a/b//" == "/a/b/" == "/a/b"), so it must resolve
# to the IDENTICAL state-dir key as the bare path in BOTH resolvers - never a
# stray, only-sometimes-present slash that would splinter one directory into
# two different keys. Regression fence for the divergence where the shell used
# `${VAR%/}` (strips exactly ONE trailing slash) while paths.py used
# `.rstrip("/")` (strips ALL) - an override ending in a doubled slash resolved
# to two DIFFERENT state dirs depending on which half of the pair answered.
# --------------------------------------------------------------------------- #
_TRAILING_SLASH_SUFFIXES = ["", "/", "//", "///"]
_TRAILING_SLASH_IDS = ["none", "single", "double", "triple"]


@requires_bash
@requires_git
@pytest.mark.parametrize("suffix", _TRAILING_SLASH_SUFFIXES, ids=_TRAILING_SLASH_IDS)
def test_project_dir_override_trailing_slashes_normalise_identically(tmp_path, suffix):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    override_dir = tmp_path / "explicit-share"
    expected = str(override_dir)  # canonical form: no trailing slash
    env = _env(home, ODOO_AI_PROJECT_DIR=expected + suffix)

    sh = _sh_resolve("share", repo, env)
    assert sh.returncode == 0, sh.stderr
    py = _py_resolve("share", repo, env)
    assert py.returncode == 0, py.stderr

    assert sh.stdout.strip() == expected
    assert py.stdout.strip() == expected
    assert sh.stdout.strip() == py.stdout.strip()


@requires_bash
@requires_git
@pytest.mark.parametrize("suffix", _TRAILING_SLASH_SUFFIXES, ids=_TRAILING_SLASH_IDS)
def test_worktree_dir_override_trailing_slashes_normalise_identically(tmp_path, suffix):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    override_dir = tmp_path / "explicit-isolate"
    expected = str(override_dir)  # canonical form: no trailing slash
    env = _env(home, ODOO_AI_WORKTREE_DIR=expected + suffix)

    sh = _sh_resolve("isolate", repo, env)
    assert sh.returncode == 0, sh.stderr
    py = _py_resolve("isolate", repo, env)
    assert py.returncode == 0, py.stderr

    assert sh.stdout.strip() == expected
    assert py.stdout.strip() == expected
    assert sh.stdout.strip() == py.stdout.strip()


@requires_bash
@pytest.mark.parametrize(
    "raw,var,mode",
    [
        ("/", "ODOO_AI_PROJECT_DIR", "share"),
        ("///", "ODOO_AI_PROJECT_DIR", "share"),
        ("/", "ODOO_AI_WORKTREE_DIR", "isolate"),
        ("///", "ODOO_AI_WORKTREE_DIR", "isolate"),
    ],
    ids=["share-single-slash", "share-all-slashes", "isolate-single-slash", "isolate-all-slashes"],
)
def test_all_slashes_override_collapses_to_root_both_langs(tmp_path, raw, var, mode):
    """An override that is ONLY slashes (e.g. "/", "///") names the filesystem
    root - both resolvers MUST canonicalize it to "/", never to an empty
    string (which would break `mkdir -p ""` / `os.makedirs("")`)."""
    home = tmp_path / "home"
    env = _env(home, **{var: raw})

    sh = _sh_resolve(mode, tmp_path, env)
    assert sh.returncode == 0, sh.stderr
    py = _py_resolve(mode, tmp_path, env)
    assert py.returncode == 0, py.stderr

    assert sh.stdout.strip() == "/"
    assert py.stdout.strip() == "/"


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


# --------------------------------------------------------------------------- #
# explicit-root parameter: resolve AS IF cwd were a named target root,
# regardless of the caller's ACTUAL cwd (`--root` on the CLI, a positional arg
# when sourced, `root=` in Python). Omitting it must stay byte-identical to
# the pre-`--root` behavior - see the regression fence below.
# --------------------------------------------------------------------------- #
@requires_bash
@requires_git
def test_root_flag_equals_cwd_invocation_for_share_and_isolate(tmp_path):
    """--root <path> must resolve IDENTICALLY to invoking with cwd=<path> and
    no flag at all: there is exactly ONE resolution algorithm, and --root only
    changes which directory it treats as the starting point. Red today:
    --root is unparsed, so the shell `case` falls to `*)` and exits 2 with the
    usage string before any comparison is possible; `paths.py` similarly has
    no `--root` handling and rejects the extra argv."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = _env(home)

    for mode in ("share", "isolate"):
        baseline_sh = _sh_resolve(mode, repo, env)
        baseline_py = _py_resolve(mode, repo, env)
        assert baseline_sh.returncode == 0, baseline_sh.stderr
        assert baseline_py.returncode == 0, baseline_py.stderr

        rooted_sh = subprocess.run(
            ["bash", str(SH), "--root", str(repo), mode],
            cwd=elsewhere, capture_output=True, text=True, env=env,
        )
        rooted_py = subprocess.run(
            [sys.executable, str(PY), "--root", str(repo), mode],
            cwd=elsewhere, capture_output=True, text=True, env=env,
        )
        assert rooted_sh.returncode == 0, rooted_sh.stderr
        assert rooted_py.returncode == 0, rooted_py.stderr
        assert rooted_sh.stdout.strip() == baseline_sh.stdout.strip(), (
            f"{mode}: --root shell={rooted_sh.stdout.strip()!r} "
            f"cwd-baseline shell={baseline_sh.stdout.strip()!r}"
        )
        assert rooted_py.stdout.strip() == baseline_py.stdout.strip(), (
            f"{mode}: --root python={rooted_py.stdout.strip()!r} "
            f"cwd-baseline python={baseline_py.stdout.strip()!r}"
        )


@requires_bash
@requires_git
def test_root_flag_from_linked_worktree_share_converges_isolate_diverges(tmp_path):
    """--root <worktree> must preserve the SHARE/ISOLATE split that makes this
    resolver useful: SHARE converges to the principal's SHARE dir (same
    `--git-common-dir`), ISOLATE stays distinct (different `--show-toplevel`).
    Guards the `--git-common-dir` / `--show-toplevel` split surviving the new
    parameter - the exact property `state-root-resolution.md` rests on.
    Red today for the same reason as the sibling test above."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "repo-wt"
    _add_worktree(repo, wt)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = _env(home)

    share_main = _sh_resolve("share", repo, env)
    iso_main = _sh_resolve("isolate", repo, env)
    assert share_main.returncode == 0, share_main.stderr
    assert iso_main.returncode == 0, iso_main.stderr

    rooted_share = subprocess.run(
        ["bash", str(SH), "--root", str(wt), "share"],
        cwd=elsewhere, capture_output=True, text=True, env=env,
    )
    rooted_isolate = subprocess.run(
        ["bash", str(SH), "--root", str(wt), "isolate"],
        cwd=elsewhere, capture_output=True, text=True, env=env,
    )
    assert rooted_share.returncode == 0, rooted_share.stderr
    assert rooted_isolate.returncode == 0, rooted_isolate.stderr
    assert rooted_share.stdout.strip() == share_main.stdout.strip(), (
        "SHARE must converge: --root <worktree> should resolve the SAME "
        "SHARE dir as the principal checkout"
    )
    assert rooted_isolate.stdout.strip() != iso_main.stdout.strip(), (
        "ISOLATE must diverge: --root <worktree> should NOT resolve the "
        "same ISOLATE dir as the principal checkout"
    )


@requires_bash
def test_root_flag_on_nonexistent_dir_exits_nonzero_with_named_diagnostic(tmp_path):
    """--root <path> where <path> is not a directory must fail loudly and
    NAME the flag in the diagnostic (not fall through to a generic usage
    string) - the escape hatch a caller relies on to return
    BLOCKED(state root unresolvable for the named target root). Red today:
    the shell exits 2 with the usage text (no mention of `--root`), and
    `paths.py` similarly has no such check."""
    home = tmp_path / "home"
    bogus = tmp_path / "does-not-exist"
    env = _env(home)

    sh = subprocess.run(
        ["bash", str(SH), "--root", str(bogus), "share"],
        capture_output=True, text=True, env=env,
    )
    py = subprocess.run(
        [sys.executable, str(PY), "--root", str(bogus), "share"],
        capture_output=True, text=True, env=env,
    )

    assert sh.returncode != 0
    assert sh.stdout.strip() == ""
    assert "--root" in sh.stderr, sh.stderr

    assert py.returncode != 0
    assert py.stdout.strip() == ""
    assert "--root" in py.stderr, py.stderr


@requires_bash
@requires_git
def test_no_root_flag_is_byte_identical_regression_fence(tmp_path):
    """Fence, not a new-behavior test: omitting --root must remain
    byte-identical to what share/isolate returned before this parameter
    existed. Green before and after this change - it is the proof that
    --root is purely additive, never a change to the no-flag path."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _init_repo(repo)
    env = _env(home)

    for mode in ("share", "isolate"):
        sh = _sh_resolve(mode, repo, env)
        py = _py_resolve(mode, repo, env)
        assert sh.returncode == 0, sh.stderr
        assert py.returncode == 0, py.stderr
        assert sh.stdout.strip() == py.stdout.strip()
