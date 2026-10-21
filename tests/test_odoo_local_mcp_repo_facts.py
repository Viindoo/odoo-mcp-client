"""Behavior tests for the odoo-local `repo_facts` tool: the git facts an agent needs (root, branch,
HEAD, remote, dirty paths, merge/rebase in progress) come from the tool, so the agent runs no git.

Every case builds a throwaway repository under tmp_path and states the expected value from how the
repository was built (a branch name it was created with, a remote URL it was given, a file it left
uncommitted) - not from the tool's own code. The tool is driven through the REAL server over stdio.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from odoo_local_mcp_harness import McpClient, hermetic_env, structured

_GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(cwd, *args, check=True):
    env = dict(os.environ)
    env.update(_GIT_ENV)
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=check)


def commit_file(repo, name, text, message="c"):
    (Path(repo) / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "17.0")
    commit_file(r, "a.txt", "one\n")
    return r


@pytest.fixture
def server(home, tmp_path):
    client = McpClient(hermetic_env(home, **_GIT_ENV), tmp_path)
    client.initialize()
    with client as s:
        yield s


def facts(server, path, **args):
    result = server.call("repo_facts", {"path": str(path), **args})
    assert result["isError"] is False, result
    return structured(result)


def test_reports_where_the_repository_is_and_what_it_has_checked_out(server, repo):
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    sub = repo / "pkg" / "deep"
    sub.mkdir(parents=True)
    out = facts(server, sub)
    assert out["is_repo"] is True
    assert out["repo_root"] == str(repo.resolve())
    assert out["branch"] == "17.0" and out["detached"] is False and out["ref"] == "17.0"
    assert out["head_sha_full"] == sha and sha.startswith(out["head_sha"]) and len(out["head_sha"]) < len(sha)
    assert out["operation_in_progress"] == "none"
    assert out["is_linked_worktree"] is False and out["principal_root"] == out["repo_root"]


def test_a_detached_head_is_reported_by_its_short_sha(server, repo):
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "--detach")
    out = facts(server, repo)
    assert out["branch"] == "" and out["detached"] is True
    assert out["ref"] == out["head_sha"] and sha.startswith(out["head_sha"])


def test_a_repository_without_commits_has_a_branch_but_no_sha(server, tmp_path):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git(fresh, "init", "-q", "-b", "main")
    out = facts(server, fresh)
    assert out["is_repo"] is True and out["branch"] == "main"
    assert out["head_sha"] == "" and out["head_sha_full"] == "" and out["detached"] is False


def test_a_linked_worktree_points_back_to_the_main_checkout(server, repo, tmp_path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(wt))
    out = facts(server, wt)
    assert out["is_linked_worktree"] is True
    assert out["repo_root"] == str(wt.resolve())
    assert out["principal_root"] == str(repo.resolve())
    assert out["branch"] == "feature"


def test_origin_url_is_reported_without_embedded_credentials(server, repo):
    git(repo, "remote", "add", "origin", "https://user:s3cret@git.example.invalid/acme/addons.git")
    git(repo, "remote", "add", "upstream", "git@git.example.invalid:acme/upstream.git")
    out = facts(server, repo)
    assert out["origin_url"] == "https://git.example.invalid/acme/addons.git"
    assert out["remotes"] == {"origin": "https://git.example.invalid/acme/addons.git",
                              "upstream": "git@git.example.invalid:acme/upstream.git"}
    assert "s3cret" not in str(out)


def test_no_origin_is_an_empty_url_not_an_error(server, repo):
    out = facts(server, repo)
    assert out["origin_url"] == "" and out["remotes"] == {}


def test_dirty_is_limited_to_the_paths_asked_about(server, repo):
    (repo / "mod_a").mkdir()
    (repo / "mod_b").mkdir()
    (repo / "mod_a" / "new.py").write_text("x = 1\n")  # untracked, inside mod_a
    asked_a = facts(server, repo, status_paths=[str(repo / "mod_a")])["dirty"]
    asked_b = facts(server, repo, status_paths=["mod_b"])["dirty"]  # relative to `path`
    assert asked_a["is_dirty"] is True and asked_a["entries"] == ["?? mod_a/"]
    assert asked_b["is_dirty"] is False and asked_b["entries"] == []


def test_dirty_without_paths_covers_the_whole_tree_and_sees_tracked_edits(server, repo):
    assert facts(server, repo)["dirty"]["is_dirty"] is False
    (repo / "a.txt").write_text("changed\n")
    out = facts(server, repo)["dirty"]
    assert out["is_dirty"] is True and out["entries"] == [" M a.txt"]


def test_status_paths_are_literal_never_globs(server, repo):
    (repo / "a.txt").write_text("changed\n")
    out = facts(server, repo, status_paths=["*.txt"])["dirty"]
    assert out["is_dirty"] is False


def test_a_long_dirty_list_is_capped_and_says_so(server, repo):
    for i in range(60):
        (repo / ("f%02d.txt" % i)).write_text("x\n")
    out = facts(server, repo)["dirty"]
    assert out["is_dirty"] is True and len(out["entries"]) == 50 and out["truncated"] is True


def _conflicting_branches(repo):
    git(repo, "checkout", "-q", "-b", "other")
    commit_file(repo, "a.txt", "other\n", "other")
    git(repo, "checkout", "-q", "17.0")
    commit_file(repo, "a.txt", "main\n", "main")


def test_a_merge_stopped_on_a_conflict_is_reported(server, repo):
    _conflicting_branches(repo)
    git(repo, "merge", "other", check=False)
    assert facts(server, repo)["operation_in_progress"] == "merge"


def test_a_rebase_stopped_on_a_conflict_is_reported(server, repo):
    _conflicting_branches(repo)
    git(repo, "checkout", "-q", "other")
    git(repo, "rebase", "17.0", check=False)
    assert facts(server, repo)["operation_in_progress"] == "rebase"


def test_a_cherry_pick_stopped_on_a_conflict_is_reported(server, repo):
    _conflicting_branches(repo)
    git(repo, "cherry-pick", "other", check=False)
    assert facts(server, repo)["operation_in_progress"] == "cherry-pick"


def test_the_operation_is_per_worktree(server, repo, tmp_path):
    _conflicting_branches(repo)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
    git(repo, "merge", "other", check=False)
    assert facts(server, repo)["operation_in_progress"] == "merge"
    assert facts(server, wt)["operation_in_progress"] == "none"


def test_a_directory_outside_any_repository_is_a_normal_result(server, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    out = facts(server, plain)
    assert out["is_repo"] is False and out["repo_root"] == "" and out["ref"] == ""
    assert out["dirty"]["is_dirty"] is False


def test_the_read_leaves_the_repository_exactly_as_it_was(server, repo):
    (repo / "a.txt").write_text("changed\n")
    (repo / "new.txt").write_text("x\n")
    git(repo, "add", "a.txt")
    commit_file(repo, "b.txt", "b\n")
    # Touch without changing content: the index is now stat-dirty, which a plain `git status`
    # opportunistically rewrites. A read-only tool must leave it alone.
    os.utime(repo / "b.txt", (1_000_000_000, 1_000_000_000))

    def snapshot():
        return sorted((str(p.relative_to(repo)), p.read_bytes()) for p in (repo / ".git").rglob("*")
                      if p.is_file() and p.name != "index.lock")

    before = snapshot()
    facts(server, repo)
    assert snapshot() == before and not (repo / ".git" / "index.lock").exists()


def test_a_missing_directory_is_a_named_error(server, tmp_path):
    result = server.call("repo_facts", {"path": str(tmp_path / "nope")})
    assert result["isError"] is True and structured(result)["error"]["code"] == "PATH_NOT_DIRECTORY"


def test_a_relative_path_is_refused(server):
    result = server.call("repo_facts", {"path": "relative/dir"})
    assert result["isError"] is True and structured(result)["error"]["code"] == "INVALID_ARGUMENTS"


def test_a_missing_git_binary_is_a_named_error(home, tmp_path, repo):
    env = hermetic_env(home, **_GIT_ENV)
    env["PATH"] = str(tmp_path / "empty-bin")  # no git on PATH
    (tmp_path / "empty-bin").mkdir()
    client = McpClient(env, tmp_path)
    client.initialize()
    with client as s:
        result = s.call("repo_facts", {"path": str(repo)})
    assert result["isError"] is True and structured(result)["error"]["code"] == "GIT_UNAVAILABLE"
    assert structured(result)["error"]["remedy"]
    assert os.path.isdir(str(repo))
