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


@pytest.fixture()
def machine(tmp_path):
    repo = tmp_path / "work" / "addons-repo"
    (repo / "addons").mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    for args in (("git", "init", "-q", "-b", "17.0"),
                 ("git", "commit", "-q", "--allow-empty", "-m", "init"),
                 ("git", "remote", "add", "origin", "git@example.org:acme/addons-repo.git")):
        subprocess.run(args, cwd=repo, check=True, capture_output=True, env=env)
    home = tmp_path / "odoo-ai"
    home.mkdir()
    catalog = home / "instances.toml"
    catalog.write_text('[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (repo / "addons"),
                       encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    return {"home": home, "catalog": catalog, "settings": settings}


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


def test_a_current_approved_setup_is_silent_and_untouched(machine):
    _approve(machine)
    before = machine["settings"].read_text()
    out = _hook(machine)
    assert out.returncode == 0
    assert out.stdout == "" and out.stderr == ""
    assert machine["settings"].read_text() == before


def test_drift_after_approval_is_converged_and_reported_without_touching_user_entries(machine):
    _approve(machine)
    data = _data(machine)
    data["autoMode"]["allow"] = [TAG + "wording of an older plugin version" if e.startswith(TAG) else e
                                 for e in data["autoMode"]["allow"]]
    data["autoMode"]["allow"].append("user wrote this")
    machine["settings"].write_text(json.dumps(data))
    out = _hook(machine)
    assert out.returncode == 0
    assert "updated" in out.stderr
    fixed = _data(machine)
    assert TAG + "wording of an older plugin version" not in fixed["autoMode"]["allow"]
    assert "user wrote this" in fixed["autoMode"]["allow"]
    assert _hook(machine).stderr == ""


def test_the_opt_out_stops_the_hook_from_writing_or_speaking(machine):
    _approve(machine)
    data = _data(machine)
    data["autoMode"]["allow"] = ["$defaults"]
    machine["settings"].write_text(json.dumps(data))
    before = machine["settings"].read_text()
    out = _hook(machine, {"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert out.returncode == 0 and out.stderr == "" and out.stdout == ""
    assert machine["settings"].read_text() == before


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
