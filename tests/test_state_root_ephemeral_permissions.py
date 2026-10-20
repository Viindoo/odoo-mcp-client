"""Behaviour tests: the SessionStart permission hook and throwaway state roots.

A session run with a throwaway ODOO_AI_HOME (a test or scratch run) used to append a
`Read(//<root>/**)` + `Edit(//<root>/projects/**)` pair to the user's settings file, for a
root that later vanished; the pairs piled up for good. The contract protected here:

  - an ephemeral root (under a system temp dir, or under the default root's scratch dir)
    is never granted rules;
  - the plugin's own earlier rule pairs for a root that is gone - or that lies under a
    system temp dir even while it exists - are removed, with a backup;
  - a user's own rules, the real default root's rules and the session's own (possibly
    not-yet-created) root are never removed;
  - ODOO_AI_NO_AUTO_PERMS=1 turns both the writing and the pruning off.

Every test drives the real hook against a throwaway HOME and settings file. The system temp
dirs are replaced through ODOO_AI_TEMP_DIRS (a test seam) so the outcome never depends on
where the runner's own temp directory happens to be.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "ensure-state-root-permissions.sh"
HELPER = PLUGIN / "scripts" / "lib" / "state_root_permissions.py"


def pair(root):
    """The two rules the plugin writes for a state root."""
    return [f"Read(/{root}/**)", f"Edit(/{root}/projects/**)"]


class World:
    def __init__(self, base):
        self.home = base / "home"
        self.systemp = base / "systemp"  # stands in for the system temp dir
        self.settings = self.home / ".claude" / "settings.json"
        self.home.mkdir()
        self.systemp.mkdir()
        self.settings.parent.mkdir()
        self.seed([])

    def seed(self, allow):
        self.settings.write_text(json.dumps({"permissions": {"allow": allow}}), encoding="utf-8")

    def allow(self):
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        return data["permissions"]["allow"]

    def run(self, odoo_ai_home=None, **env_extra):
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("ODOO_AI_HOME", None)
        env.pop("ODOO_AI_NO_AUTO_PERMS", None)
        env["HOME"] = str(self.home)
        env["CLAUDE_SETTINGS"] = str(self.settings)
        env["ODOO_AI_TEMP_DIRS"] = str(self.systemp)
        if odoo_ai_home is not None:
            env["ODOO_AI_HOME"] = str(odoo_ai_home)
        env.update(env_extra)
        r = subprocess.run(["bash", str(HOOK)], env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return r

    def lay_bash_rules(self):
        """One ephemeral session: lays the plugin's two Bash rules, no state-root rule."""
        self.run(self.systemp / "warm-up")
        assert state_rules(self.allow()) == []

    def backups(self):
        return list(self.settings.parent.glob("settings.json.bak.*"))


@pytest.fixture()
def world(tmp_path):
    return World(tmp_path)


def state_rules(allow):
    return [a for a in allow if a.startswith(("Read(//", "Edit(//"))]


def test_ephemeral_root_under_system_temp_gets_no_rules(world):
    world.run(world.systemp / "run1" / ".odoo-ai")
    assert state_rules(world.allow()) == []
    world.lay_bash_rules()
    assert world.run(world.systemp / "run2" / ".odoo-ai").stdout == "", (
        "an ephemeral root must not trigger the restart nudge"
    )


def test_scratch_dir_of_default_root_gets_no_rules(world):
    root = world.home / ".odoo-ai" / "scratch" / "live-run"
    world.run(root)
    assert state_rules(world.allow()) == []


def test_real_default_root_gets_its_rules(world):
    world.run()  # ODOO_AI_HOME unset: the default root under HOME
    assert pair(world.home / ".odoo-ai") == [
        a for a in world.allow() if a.startswith(("Read(//", "Edit(//"))
    ]


def test_real_root_rules_survive_a_scratch_session(world):
    real = world.home / ".odoo-ai"
    real.mkdir()
    world.seed(pair(real))
    world.run(real / "scratch" / "live-run")
    assert state_rules(world.allow()) == pair(real)


def test_vanished_plugin_rules_are_pruned_and_the_real_root_added(world):
    gone = world.home / "old-state-root"  # never created
    world.seed(pair(gone))
    world.run()
    assert state_rules(world.allow()) == pair(world.home / ".odoo-ai")
    assert world.backups(), "pruning must back the settings file up first"


def test_existing_root_under_system_temp_is_pruned_too(world):
    leftover = world.systemp / "kept-on-disk"
    leftover.mkdir()
    world.seed(pair(leftover))
    world.run()
    assert not any(str(leftover) in a for a in world.allow())


def test_user_written_rules_are_never_touched(world):
    gone = world.home / "vanished"
    user = [
        "Bash(git status)",
        f"Read(/{gone}/**)",  # no Edit(.../projects/**) beside it: not the plugin's pair
        f"Edit(/{gone}/notes/**)",  # a different shape
        f"Read(/{world.systemp}/user-data/**)",  # a user rule on a temp path
        f"Edit(/{world.systemp}/user-data/**)",
    ]
    world.seed(user)
    world.run()
    assert all(rule in world.allow() for rule in user)


def test_session_root_that_does_not_exist_yet_is_not_pruned(world):
    fresh = world.home / "brand-new-state-root"  # real root, directory not created yet
    world.run(fresh)
    settled = world.settings.read_text(encoding="utf-8")
    backups = len(world.backups())
    again = world.run(fresh)
    assert state_rules(world.allow()) == pair(fresh)
    # No prune-then-re-add churn: the second session rewrites nothing and says nothing.
    assert world.settings.read_text(encoding="utf-8") == settled
    assert len(world.backups()) == backups and again.stdout == ""


def test_opt_out_neither_writes_nor_prunes(world):
    stale = pair(world.home / "vanished")
    world.seed(stale)
    before = world.settings.read_text(encoding="utf-8")
    r = world.run(ODOO_AI_NO_AUTO_PERMS="1")
    assert world.settings.read_text(encoding="utf-8") == before
    assert r.stdout == "" and not world.backups()


def test_pruning_alone_is_silent_and_a_second_run_changes_nothing(world):
    real = world.home / ".odoo-ai"
    real.mkdir()
    world.lay_bash_rules()
    world.seed(world.allow() + pair(real) + pair(world.home / "vanished"))
    r = world.run()
    assert r.stdout == "" and r.stderr == "", "a prune-only run has nothing to announce"
    assert state_rules(world.allow()) == pair(real)
    first = world.settings.read_text(encoding="utf-8")
    world.run()
    assert world.settings.read_text(encoding="utf-8") == first


@pytest.mark.parametrize("root", ["/tmp/odoo-ai-never-created", "/var/tmp/odoo-ai-never-created"])
def test_builtin_system_temp_dirs_are_ephemeral(root):
    env = {k: v for k, v in os.environ.items() if k != "ODOO_AI_TEMP_DIRS"}
    r = subprocess.run(["python3", str(HELPER), "ephemeral", root], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0


def test_a_home_directory_root_is_not_ephemeral(tmp_path):
    env = dict(os.environ)
    env["ODOO_AI_TEMP_DIRS"] = str(tmp_path / "elsewhere")  # the runner's own tmp_path is not temp here
    env["HOME"] = str(tmp_path)
    r = subprocess.run(["python3", str(HELPER), "ephemeral", str(tmp_path / ".odoo-ai")],
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
