"""Behaviour tests for `scripts/setup-steps/34-auto-mode.sh`.

The step teaches Claude Code's auto-mode classifier what is routine on this machine and keeps a
human gate on protected branches. Every value is derived from the machine: the catalog's
addons_path rows and the git remotes/branches of the repositories holding them.

Drives throwaway settings (CLAUDE_SETTINGS), state root (ODOO_AI_HOME) and catalog
(ODOO_AI_INSTANCES); the real user settings are never touched.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "34-auto-mode.sh"
TAG = "odoo-ai-agents: "
GROUPS = ("allow", "soft_deny", "environment")


def _sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def _push_to_fork(repo, bare):
    """Make `repo` really push a feature branch to remote `fork` (a local bare repo stands in for
    the hosted fork; the remote's url keeps the public-looking owner the step reads)."""
    _sh(repo.parent, "git", "init", "-q", "--bare", str(bare))
    _sh(repo, "git", "config", "remote.fork.pushurl", str(bare))
    _sh(repo, "git", "push", "-q", "fork", "HEAD:refs/heads/feat-x")


def _fetch_upstream(repo, tmp_path, owner):
    """Add a remote `upstream` of `owner` the user only FETCHES from: a real fetch of a source
    repo that carries the series branch and a feature-looking branch, as an upstream's PR refs do."""
    src = tmp_path / "upstream-src"
    src.mkdir()
    _sh(src, "git", "init", "-q", "-b", "17.0")
    _sh(src, "git", "commit", "-q", "--allow-empty", "-m", "up")
    _sh(src, "git", "branch", "feat-pr-ref")
    _sh(repo, "git", "remote", "add", "upstream", f"https://example.org/{owner}/addons-repo.git")
    _sh(repo, "git", "fetch", "-q", str(src), "+refs/heads/*:refs/remotes/upstream/*")
    # A branch started from the upstream's series branch tracks the upstream.
    _sh(repo, "git", "branch", "--track", "from-upstream", "upstream/17.0")


@pytest.fixture()
def machine(tmp_path):
    """A repo with origin (org acme), a fork remote the user pushed to (alice), branches
    master/17.0/18.0, and a catalog declaring two addons entries inside it."""
    repo = tmp_path / "work" / "addons-repo"
    (repo / "addons").mkdir(parents=True)
    (repo / "extra").mkdir()
    _sh(repo, "git", "init", "-q", "-b", "17.0")
    _sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "init")
    _sh(repo, "git", "branch", "18.0")
    _sh(repo, "git", "remote", "add", "origin", "git@example.org:acme/addons-repo.git")
    _sh(repo, "git", "remote", "add", "fork", "https://example.org/alice/addons-repo.git")
    _push_to_fork(repo, tmp_path / "alice-bare.git")
    _sh(repo, "git", "update-ref", "refs/remotes/origin/master", "HEAD")
    _sh(repo, "git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
    home = tmp_path / "odoo-ai"
    home.mkdir()
    catalog = home / "instances.toml"
    catalog.write_text(
        '[[instance]]\nseries = "17.0"\naddons_path = ["%s", "%s"]\n' % (repo / "addons", repo / "extra"),
        encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    return {"repo": repo, "home": home, "catalog": catalog, "settings": settings}


def _run(machine, sub, env_extra=None):
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("ODOO_AI_NO_AUTO_PERMS", None)
    env.update(CLAUDE_SETTINGS=str(machine["settings"]), ODOO_AI_HOME=str(machine["home"]),
               ODOO_AI_INSTANCES=str(machine["catalog"]))
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(STEP), sub], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)


def _data(machine):
    return json.loads(Path(machine["settings"]).read_text(encoding="utf-8"))


def test_propose_derives_roots_org_fork_and_branches_from_catalog_and_remotes(machine):
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    assert f"trusted root: {machine['repo']}" in out.stdout
    assert f"trusted root: {machine['home']}/projects" in out.stdout
    assert "organization (origin owner): acme" in out.stdout
    assert "fork owner (remote the user pushes to): alice" in out.stdout
    for branch in ("master", "17.0", "18.0"):
        assert f"protected branch: {branch}" in out.stdout


def _fork_lines(out):
    return [ln for ln in out.stdout.splitlines() if ln.startswith("fork owner")]


def test_a_remote_the_user_pushes_feature_branches_to_is_a_fork_owner(machine):
    out = _run(machine, "propose")
    assert _fork_lines(out) == ["fork owner (remote the user pushes to): alice"]


def test_an_upstream_read_only_remote_is_not_a_fork_owner(machine, tmp_path):
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    assert _fork_lines(out) == ["fork owner (remote the user pushes to): alice"]
    assert _run(machine, "apply").returncode == 0
    assert "bigupstream" not in json.dumps(_data(machine))


def test_a_clone_with_only_an_upstream_remote_has_no_fork_owner(machine, tmp_path):
    _sh(machine["repo"], "git", "remote", "remove", "fork")
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    out = _run(machine, "propose")
    assert _fork_lines(out) == []
    assert _run(machine, "apply").returncode == 0
    assert not any("Fork owner" in e for e in _data(machine)["autoMode"]["environment"])


def _questions(out):
    return [ln for ln in out.stdout.splitlines() if ln.startswith("FORK_QUESTION=")]


def test_propose_asks_which_account_holds_the_fork_when_nothing_was_pushed(machine, tmp_path):
    _sh(machine["repo"], "git", "remote", "remove", "fork")
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    [question] = _questions(out)
    assert "acme/addons-repo" in question


def test_propose_asks_the_fork_question_for_a_clone_with_no_other_remote(machine):
    _sh(machine["repo"], "git", "remote", "remove", "fork")
    [question] = _questions(_run(machine, "propose"))
    assert "acme/addons-repo" in question


def test_propose_asks_nothing_when_a_remote_was_pushed_to(machine):
    assert _questions(_run(machine, "propose")) == []


def _second_machine_clone(machine, tmp_path, name, origin):
    """Another clone beside the first one, with origin `origin` and no fork remote; its addons
    directory joins the catalog."""
    repo = tmp_path / "work" / name
    (repo / "addons").mkdir(parents=True)
    _sh(repo, "git", "init", "-q", "-b", "17.0")
    _sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "init")
    _sh(repo, "git", "remote", "add", "origin", origin)
    with machine["catalog"].open("a", encoding="utf-8") as fh:
        fh.write('\n[[instance]]\nseries = "18.0"\naddons_path = ["%s"]\n' % (repo / "addons"))
    return repo


def test_a_fork_owner_known_from_one_clone_silences_the_question_for_every_other_clone(
        machine, tmp_path):
    """Two origins, three clones; only one clone has a pushed fork."""
    _second_machine_clone(machine, tmp_path, "addons-repo-copy", "git@example.org:acme/addons-repo.git")
    _second_machine_clone(machine, tmp_path, "themes", "git@example.org:acme/themes.git")
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    assert _fork_lines(out) == ["fork owner (remote the user pushes to): alice"]
    assert _questions(out) == []


def test_without_any_pushed_fork_the_operator_is_asked_exactly_once_for_many_clones(
        machine, tmp_path):
    _sh(machine["repo"], "git", "remote", "remove", "fork")
    _second_machine_clone(machine, tmp_path, "addons-repo-copy", "git@example.org:acme/addons-repo.git")
    _second_machine_clone(machine, tmp_path, "themes", "git@example.org:acme/themes.git")
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    assert len(_questions(out)) == 1


def test_propose_never_prints_a_credential_from_a_remote_url(machine):
    repo = machine["repo"]
    _sh(repo, "git", "remote", "set-url", "origin", "https://token123@example.org/acme/addons-repo.git")
    _sh(repo, "git", "remote", "set-url", "fork", "https://alice:secret456@example.org/alice/addons-repo.git")
    out = _run(machine, "propose")
    assert out.returncode == 0, out.stderr
    assert "token123" not in out.stdout and "secret456" not in out.stdout


def test_an_unconfirmed_fork_candidate_is_never_written(machine, tmp_path):
    _sh(machine["repo"], "git", "remote", "remove", "fork")
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    assert _run(machine, "apply").returncode == 0
    written = json.dumps(_data(machine))
    assert "bigupstream" not in written
    assert not any("Fork owner" in e for e in _data(machine)["autoMode"]["environment"])


def test_a_remote_named_as_the_push_target_by_config_is_a_fork_owner(machine, tmp_path):
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    _sh(machine["repo"], "git", "config", "remote.pushDefault", "upstream")
    out = _run(machine, "propose")
    assert "bigupstream" in " ".join(_fork_lines(out))


def test_a_branch_pushed_with_upstream_tracking_to_a_feature_branch_marks_its_remote_a_fork(
        machine, tmp_path):
    _fetch_upstream(machine["repo"], tmp_path, "bigupstream")
    repo = machine["repo"]
    _sh(repo, "git", "config", "branch.from-upstream.merge", "refs/heads/my-feature")
    out = _run(machine, "propose")
    assert "bigupstream" in " ".join(_fork_lines(out))


def test_propose_without_a_catalog_row_names_what_is_missing_and_exits_1(machine):
    machine["catalog"].write_text("", encoding="utf-8")
    out = _run(machine, "propose")
    assert out.returncode == 1
    assert "addons_path" in out.stdout


def test_apply_writes_only_the_four_keys_and_keeps_defaults_first(machine):
    machine["settings"].write_text(json.dumps({"autoMode": {"allow": ["my own rule"]}, "model": "x"}))
    assert _run(machine, "apply").returncode == 0
    data = _data(machine)
    assert set(data) == {"autoMode", "model", "permissions"}
    assert set(data["autoMode"]) == set(GROUPS)
    assert set(data["permissions"]) == {"ask"}
    for key in GROUPS:
        assert data["autoMode"][key][0] == "$defaults"
    assert "my own rule" in data["autoMode"]["allow"]
    assert any(e.startswith(TAG) for e in data["autoMode"]["allow"])
    assert all(e.startswith(TAG) for e in data["autoMode"]["soft_deny"][1:])


def test_apply_never_writes_hard_deny_or_broad_allow_or_bypass(machine):
    _run(machine, "apply")
    data = _data(machine)
    assert "hard_deny" not in data["autoMode"]
    assert "allow" not in data["permissions"]
    assert "bypassPermissions" not in json.dumps(data)


def test_apply_is_idempotent_and_check_agrees(machine):
    assert _run(machine, "check").returncode == 1
    assert _run(machine, "apply").returncode == 0
    first = machine["settings"].read_text()
    assert _run(machine, "check").returncode == 0
    assert _run(machine, "apply").returncode == 0
    assert machine["settings"].read_text() == first


def test_entries_name_only_the_machine_owners_never_a_hardcoded_vendor(machine):
    _run(machine, "apply")
    text = json.dumps(_data(machine))
    assert "acme" in text and "alice" in text
    for vendor in ("viindoo", "davidtranhp", "tvtmaaddons"):
        assert vendor not in text.lower()


def test_the_edit_allowance_covers_a_break_check_of_data_security_and_test_files(machine):
    """A break-check temporarily alters a security or data file and restores it: the classifier
    must be told that is expected work, or it blocks the proof every test relies on."""
    _run(machine, "apply")
    entries = _data(machine)["autoMode"]["allow"]
    texts = [" ".join(e.lower().split()) for e in entries if e.startswith(TAG)]
    covering = [t for t in texts
                if "break-check" in t
                and re.search(r"\b(data|security|test)(?:,| and| or)[^.;]{0,30}files?\b"
                              r"|\b(data|security|test) files?\b", t)
                and ("restored" in t or "rebuilt" in t)]
    assert covering, "no allow entry covers a break-check of a data, security or test file"


def test_ask_rules_name_every_protected_branch_in_all_three_push_forms(machine):
    _run(machine, "apply")
    ask = _data(machine)["permissions"]["ask"]
    for branch in ("master", "17.0", "18.0"):
        assert f"Bash(git push * {branch})" in ask
        assert f"Bash(git push --force* * {branch})" in ask
        assert f"Bash(git push * --delete {branch})" in ask


def test_a_changed_entry_text_prunes_the_stale_tagged_entry_and_keeps_user_entries(machine):
    machine["settings"].write_text(json.dumps({
        "autoMode": {"allow": ["$defaults", TAG + "an older wording of a rule", "user wrote this"],
                     "environment": [TAG + "old environment"]},
        "permissions": {"ask": ["Bash(git push * 99.0)", "Bash(rm -rf *)"]},
    }))
    assert _run(machine, "check").returncode == 1
    assert _run(machine, "apply").returncode == 0
    data = _data(machine)
    assert TAG + "an older wording of a rule" not in data["autoMode"]["allow"]
    assert TAG + "old environment" not in data["autoMode"]["environment"]
    assert "user wrote this" in data["autoMode"]["allow"]
    assert "Bash(git push * 99.0)" not in data["permissions"]["ask"]
    assert "Bash(rm -rf *)" in data["permissions"]["ask"]
    assert _run(machine, "check").returncode == 0


def test_opt_out_writes_nothing_and_check_passes(machine):
    before = machine["settings"].read_text()
    out = _run(machine, "apply", {"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert out.returncode == 0
    assert machine["settings"].read_text() == before
    assert _run(machine, "check", {"ODOO_AI_NO_AUTO_PERMS": "1"}).returncode == 0


def test_invalid_json_settings_exit_2_and_stay_unchanged(machine):
    machine["settings"].write_text("{not json")
    out = _run(machine, "apply")
    assert out.returncode == 2
    assert machine["settings"].read_text() == "{not json"
    assert not list(machine["settings"].parent.glob("settings.json.bak.*"))


def test_apply_backs_up_existing_settings_before_writing(machine):
    machine["settings"].write_text(json.dumps({"model": "x"}))
    _run(machine, "apply")
    assert list(machine["settings"].parent.glob("settings.json.bak.*"))
