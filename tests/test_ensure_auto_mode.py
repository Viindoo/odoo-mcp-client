"""Behaviour tests for the SessionStart hook `hooks/ensure-auto-mode.sh`.

The hook keeps the auto-mode entries written by setup step 34 current across plugin versions,
but only after the owner approved the step once on this machine (a tagged autoMode.environment
entry is the marker). Before that it writes nothing and gives one line of advice.

Drives throwaway settings (CLAUDE_SETTINGS), state root and catalog; real settings are never
touched.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "ensure-auto-mode.sh"
STEP = PLUGIN / "scripts" / "setup-steps" / "34-auto-mode.sh"
TAG = "odoo-ai-agents: "


def _build_machine(base):
    repo = base / "work" / "addons-repo"
    (repo / "addons").mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    for args in (("git", "init", "-q", "-b", "17.0"),
                 ("git", "commit", "-q", "--allow-empty", "-m", "init"),
                 ("git", "remote", "add", "origin", "git@example.org:acme/addons-repo.git")):
        subprocess.run(args, cwd=repo, check=True, capture_output=True, env=env)
    home = base / "odoo-ai"
    home.mkdir()
    catalog = home / "instances.toml"
    catalog.write_text('[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (repo / "addons"),
                       encoding="utf-8")
    settings = base / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    return {"home": home, "catalog": catalog, "settings": settings}


@pytest.fixture(scope="module")
def approved_machine(tmp_path_factory):
    """One machine (a repo, its catalog) and the settings the owner's one-time approval leaves
    behind - built once; every test starts from a copy of that settings file."""
    m = _build_machine(tmp_path_factory.mktemp("machine"))
    _approve(m)
    m["approved_text"] = m["settings"].read_text(encoding="utf-8")
    return m


@pytest.fixture()
def machine(approved_machine, tmp_path):
    """The approved machine with its own settings file, set back to `{}` (before approval)."""
    m = dict(approved_machine, settings=tmp_path / "settings.json")
    m["settings"].write_text("{}", encoding="utf-8")
    return m


@pytest.fixture()
def approved(machine, approved_machine):
    machine["settings"].write_text(approved_machine["approved_text"], encoding="utf-8")
    return machine


def _env(machine, extra=None):
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("ODOO_AI_NO_AUTO_PERMS", None)
    env.update(CLAUDE_SETTINGS=str(machine["settings"]), ODOO_AI_HOME=str(machine["home"]),
               ODOO_AI_INSTANCES=str(machine["catalog"]))
    if extra:
        env.update(extra)
    return env


def _hook(machine, extra=None):
    return subprocess.run(["bash", str(HOOK)], env=_env(machine, extra), stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)


def _approve(machine):
    """What the owner's one-time approval leaves behind: run the step."""
    subprocess.run(["bash", str(STEP), "apply"], env=_env(machine), stdin=subprocess.DEVNULL,
                   check=True, capture_output=True, text=True, timeout=120)


def _data(machine):
    return json.loads(Path(machine["settings"]).read_text(encoding="utf-8"))


def test_before_the_owner_approved_nothing_is_written_and_one_advice_line_is_given(machine):
    out = _hook(machine)
    assert out.returncode == 0
    assert machine["settings"].read_text() == "{}"
    assert "/odoo-ai-agents:odoo-setup auto-mode" in out.stderr
    assert len([line for line in out.stderr.splitlines() if line.strip()]) == 1


def test_a_current_approved_setup_is_silent_and_untouched(approved):
    before = approved["settings"].read_text()
    out = _hook(approved)
    assert out.returncode == 0
    assert out.stdout == "" and out.stderr == ""
    assert approved["settings"].read_text() == before


def test_drift_after_approval_is_converged_and_reported_without_touching_user_entries(approved):
    data = _data(approved)
    data["autoMode"]["allow"] = [TAG + "wording of an older plugin version" if e.startswith(TAG) else e
                                 for e in data["autoMode"]["allow"]]
    data["autoMode"]["allow"].append("user wrote this")
    approved["settings"].write_text(json.dumps(data))
    out = _hook(approved)
    assert out.returncode == 0
    assert "updated" in out.stderr
    fixed = _data(approved)
    assert TAG + "wording of an older plugin version" not in fixed["autoMode"]["allow"]
    assert "user wrote this" in fixed["autoMode"]["allow"]
    assert _hook(approved).stderr == ""


def test_the_opt_out_stops_the_hook_from_writing_or_speaking(approved):
    data = _data(approved)
    data["autoMode"]["allow"] = ["$defaults"]
    approved["settings"].write_text(json.dumps(data))
    before = approved["settings"].read_text()
    out = _hook(approved, {"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert out.returncode == 0 and out.stderr == "" and out.stdout == ""
    assert approved["settings"].read_text() == before


def test_a_settings_file_that_is_not_json_is_never_written(machine):
    machine["settings"].write_text("{not json")
    out = _hook(machine)
    assert out.returncode == 0
    assert machine["settings"].read_text() == "{not json"
    assert not list(machine["settings"].parent.glob("settings.json.bak.*"))


def test_the_hook_is_registered_for_session_start_after_the_state_root_hook():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    commands = [h["command"] for entry in hooks["hooks"]["SessionStart"] for h in entry["hooks"]]
    names = [c.split("/hooks/")[1].rstrip('"') for c in commands]
    assert names.index("ensure-auto-mode.sh") == names.index("ensure-state-root-permissions.sh") + 1
