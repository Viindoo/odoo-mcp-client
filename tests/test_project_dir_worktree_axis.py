"""Behavior tests for the `worktree` axis of project_dir (paths.py +
resolve_project_dir.sh + the odoo-local MCP tool).

Contract under test:
- `worktree <name>` resolves to <SHARE>/worktrees/<name>/src, creating the
  parent and never `src` itself (git worktree add owns that).
- A worktree checked out at that path keys its ISOLATE dir on <name>, so its
  state lives in the parent of its src - identical from shell and Python.
- An invalid name is refused by both resolvers and by the tool.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from odoo_local_mcp_harness import LIB_DIR, hermetic_env

SH = LIB_DIR / "resolve_project_dir.sh"
PY = LIB_DIR / "paths.py"


def _git(args, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)


def _repo(tmp_path: Path, env: dict) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo, env)
    _git(["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], repo, env)
    return repo


def _py(args, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PY), *args], cwd=cwd, env=env, capture_output=True, text=True)


def _sh(args, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SH), *args], cwd=cwd, env=env, capture_output=True, text=True)


def _env(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    home.mkdir()
    env = hermetic_env(home)
    env["GIT_CONFIG_GLOBAL"] = str(tmp_path / "gitconfig")
    return env


def test_worktree_axis_resolves_under_share_and_creates_only_the_parent(tmp_path):
    env = _env(tmp_path)
    repo = _repo(tmp_path, env)
    share = _py(["share"], repo, env).stdout.strip()
    out = _py(["worktree", "feat-x"], repo, env)
    assert out.returncode == 0, out.stderr
    path = out.stdout.strip()
    assert path == os.path.join(share, "worktrees", "feat-x", "src")
    assert os.path.isdir(os.path.dirname(path))
    assert not os.path.exists(path)


def test_shell_and_python_agree_on_the_worktree_axis(tmp_path):
    env = _env(tmp_path)
    repo = _repo(tmp_path, env)
    py = _py(["worktree", "feat-x"], repo, env)
    sh = _sh(["worktree", "feat-x"], repo, env)
    assert py.returncode == 0 and sh.returncode == 0, (py.stderr, sh.stderr)
    assert py.stdout.strip() == sh.stdout.strip()


def test_a_worktree_checked_out_at_the_worktree_path_keys_its_isolate_dir_on_its_name(tmp_path):
    env = _env(tmp_path)
    repo = _repo(tmp_path, env)
    src = _py(["worktree", "feat-x"], repo, env).stdout.strip()
    _git(["worktree", "add", "-q", "-b", "feat-x", src, "HEAD"], repo, env)
    py = _py(["isolate"], Path(src), env)
    sh = _sh(["isolate"], Path(src), env)
    assert py.returncode == 0 and sh.returncode == 0, (py.stderr, sh.stderr)
    assert py.stdout.strip() == sh.stdout.strip() == os.path.dirname(src)
    # the principal checkout still keys on its hashed toplevel, not on a name
    principal = _py(["isolate"], repo, env).stdout.strip()
    assert principal != os.path.dirname(src)


@pytest.mark.parametrize("bad", ["", "../x", "a/b", ".hidden", "x" * 81, "sp ace"])
def test_an_invalid_worktree_name_is_refused_by_both_resolvers(tmp_path, bad):
    env = _env(tmp_path)
    repo = _repo(tmp_path, env)
    assert _py(["worktree", bad], repo, env).returncode != 0
    assert _sh(["worktree", bad], repo, env).returncode != 0


def test_the_tool_exposes_the_worktree_axis(tmp_path):
    from test_odoo_local_mcp_catalog import _err, _ok, _server  # noqa: WPS433 - reuse the real-server harness

    env = _env(tmp_path)
    repo = _repo(tmp_path, env)
    home = Path(env["ODOO_AI_HOME"])
    work = tmp_path / "work"
    work.mkdir()
    with _server(home, work) as s:
        out = _ok(s.call("project_dir", {"cwd": str(repo), "axis": "worktree", "name": "feat-x"}))
        missing = _err(s.call("project_dir", {"cwd": str(repo), "axis": "worktree"}))
    assert out["axis"] == "worktree" and out["name"] == "feat-x"
    assert out["path"] == _py(["worktree", "feat-x"], repo, env).stdout.strip()
    assert missing["code"] == "WORKTREE_NAME_REQUIRED"
