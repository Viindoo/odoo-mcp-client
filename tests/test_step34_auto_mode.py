"""Behaviour tests for `scripts/setup-steps/34-auto-mode.sh`.

The step teaches Claude Code's auto-mode classifier what is routine on this machine and keeps a
human gate on protected branches. Every value is derived from the machine: the catalog's
addons_path rows and the git remotes/branches of the repositories holding them.

Drives throwaway settings (CLAUDE_SETTINGS), state root (ODOO_AI_HOME) and catalog
(ODOO_AI_INSTANCES); the real user settings are never touched.
"""
import json
import os
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


@pytest.fixture()
def machine(tmp_path):
    """A repo with origin (org acme), a fork remote, branches master/17.0/18.0, and a catalog
    declaring two addons entries inside it."""
    repo = tmp_path / "work" / "addons-repo"
    (repo / "addons").mkdir(parents=True)
    (repo / "extra").mkdir()
    _sh(repo, "git", "init", "-q", "-b", "17.0")
    _sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "init")
    _sh(repo, "git", "branch", "18.0")
    _sh(repo, "git", "remote", "add", "origin", "git@example.org:acme/addons-repo.git")
    _sh(repo, "git", "remote", "add", "fork", "https://example.org/alice/addons-repo.git")
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
    assert "fork owner (other remote): alice" in out.stdout
    for branch in ("master", "17.0", "18.0"):
        assert f"protected branch: {branch}" in out.stdout


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
