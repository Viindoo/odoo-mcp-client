"""Behaviour tests for `scripts/lib/fork_facts.py`, the fork mechanism shared by setup steps 34 and
60 and the instance repo scan.

A clone is classified from its own git records (read only, no network): `fork-remote-pushed` when
the user pushed to a non-origin remote, `fork-remote-unpushed` when non-origin remotes exist but
none was pushed to, `no-fork-remote` otherwise. A local bare repository stands in for the hosted
fork.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import fork_facts  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, **GIT_ENV})


@pytest.fixture()
def clone(tmp_path):
    """A clone whose origin is acme/addons-repo, with credentials in the URL."""
    repo = tmp_path / "addons-repo"
    repo.mkdir()
    _sh(repo, "git", "init", "-q", "-b", "17.0")
    _sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "init")
    _sh(repo, "git", "remote", "add", "origin", "https://token123@example.org/acme/addons-repo.git")
    return repo


def _add_fork(repo, name="fork", account="alice", push=True):
    """Add remote `name` owned by `account`; push a feature branch to it when `push`."""
    bare = repo.parent / ("%s-bare.git" % account)
    _sh(repo.parent, "git", "init", "-q", "--bare", str(bare))
    _sh(repo, "git", "remote", "add", name, "https://%s:secret456@example.org/%s/addons-repo.git"
        % (account, account))
    _sh(repo, "git", "config", "remote.%s.pushurl" % name, str(bare))
    if push:
        _sh(repo, "git", "push", "-q", name, "HEAD:refs/heads/feat-x")


def _add_fetch_only_upstream(repo, owner="bigupstream"):
    """Add remote `upstream` that is only FETCHED from (it carries a series and a feature branch)."""
    src = repo.parent / "upstream-src"
    src.mkdir()
    _sh(src, "git", "init", "-q", "-b", "17.0")
    _sh(src, "git", "commit", "-q", "--allow-empty", "-m", "up")
    _sh(src, "git", "branch", "feat-pr-ref")
    _sh(repo, "git", "remote", "add", "upstream", "https://example.org/%s/addons-repo.git" % owner)
    _sh(repo, "git", "fetch", "-q", str(src), "+refs/heads/*:refs/remotes/upstream/*")


def _cli(repo, *flags):
    return subprocess.run([sys.executable, str(LIB / "fork_facts.py"), "--repo", str(repo), *flags],
                          capture_output=True, text=True, timeout=60)


def test_a_clone_with_only_origin_has_no_fork_remote(clone):
    facts = fork_facts.fork_facts(str(clone))
    assert facts["status"] == "no-fork-remote"
    assert facts["origin"] == {"owner": "acme", "repo": "addons-repo"}
    assert facts["remotes"] == []


def test_a_fetch_only_remote_is_a_candidate_never_a_fork(clone):
    _add_fetch_only_upstream(clone)
    facts = fork_facts.fork_facts(str(clone))
    assert facts["status"] == "fork-remote-unpushed"
    assert [(r["name"], r["owner"], r["pushed"]) for r in facts["remotes"]] == [
        ("upstream", "bigupstream", False)]


def test_a_remote_the_user_pushed_to_is_the_fork(clone):
    _add_fork(clone)
    facts = fork_facts.fork_facts(str(clone))
    assert facts["status"] == "fork-remote-pushed"
    assert [(r["name"], r["owner"], r["pushed"]) for r in facts["remotes"]] == [("fork", "alice", True)]


def test_a_pushed_fork_stays_the_only_fork_next_to_a_fetch_only_upstream(clone):
    _add_fetch_only_upstream(clone)
    _add_fork(clone)
    facts = fork_facts.fork_facts(str(clone))
    assert facts["status"] == "fork-remote-pushed"
    assert {r["name"]: r["pushed"] for r in facts["remotes"]} == {"upstream": False, "fork": True}


def test_a_remote_added_but_never_pushed_to_is_unpushed(clone):
    _add_fork(clone, push=False)
    assert fork_facts.fork_facts(str(clone))["status"] == "fork-remote-unpushed"


def test_a_push_target_set_by_config_counts_as_pushed(clone):
    _add_fetch_only_upstream(clone)
    _sh(clone, "git", "config", "remote.pushDefault", "upstream")
    assert fork_facts.fork_facts(str(clone))["status"] == "fork-remote-pushed"


def test_an_unconfirmed_fork_raises_a_question_naming_the_origin_repository(clone):
    for setup in (lambda: None, lambda: _add_fetch_only_upstream(clone)):
        setup()
        facts = fork_facts.fork_facts(str(clone))
        assert "acme/addons-repo" in facts["question"]
        assert dict(fork_facts.pairs(facts))["FORK_QUESTION"] == facts["question"]


def test_a_pushed_fork_raises_no_question(clone):
    _add_fork(clone)
    facts = fork_facts.fork_facts(str(clone))
    assert facts["question"] == ""
    assert "FORK_QUESTION" not in dict(fork_facts.pairs(facts))


def test_no_question_is_asked_about_a_repository_without_an_origin(tmp_path):
    repo = tmp_path / "bare-clone"
    repo.mkdir()
    _sh(repo, "git", "init", "-q")
    facts = fork_facts.fork_facts(str(repo))
    assert facts["origin"] is None
    assert facts["question"] == ""


def test_cli_prints_key_value_lines_and_never_a_credential(clone):
    _add_fork(clone)
    out = _cli(clone)
    assert out.returncode == 0, out.stderr
    lines = dict(line.partition("=")[::2] for line in out.stdout.splitlines())
    assert shlex.split(lines["FORK_STATUS"]) == ["fork-remote-pushed"]
    assert shlex.split(lines["FORK_ORIGIN"]) == ["acme/addons-repo"]
    assert shlex.split(lines["FORK_PUSHED_REMOTES"]) == ["fork=alice"]
    for secret in ("token123", "secret456", "https://"):
        assert secret not in out.stdout + out.stderr


def test_cli_json_carries_the_facts_and_never_a_credential(clone):
    _add_fork(clone)
    _add_fetch_only_upstream(clone)
    out = _cli(clone, "--json")
    assert out.returncode == 0, out.stderr
    facts = json.loads(out.stdout)
    assert facts["status"] == "fork-remote-pushed"
    assert {r["name"]: r["pushed"] for r in facts["remotes"]} == {"fork": True, "upstream": False}
    for secret in ("token123", "secret456", "https://"):
        assert secret not in out.stdout


def test_cli_reads_a_repository_from_a_subdirectory(clone):
    _add_fork(clone)
    sub = clone / "addons"
    sub.mkdir()
    assert json.loads(_cli(sub, "--json").stdout)["repo"] == str(clone.resolve())


def test_cli_refuses_a_directory_that_is_not_a_clone(tmp_path):
    out = _cli(tmp_path / "nowhere")
    assert out.returncode == 1
    assert out.stdout == ""


def test_reading_the_fork_changes_nothing_in_the_clone(clone):
    _add_fork(clone)
    before = subprocess.run(["git", "-C", str(clone), "config", "--list"], capture_output=True,
                            text=True).stdout
    _cli(clone)
    after = subprocess.run(["git", "-C", str(clone), "config", "--list"], capture_output=True,
                           text=True).stdout
    assert before == after
