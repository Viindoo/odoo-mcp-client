"""Behavior tests for setup step 36 and its SessionStart hint: move Claude Code's temp directory.

The rule protected: setup proposes CLAUDE_CODE_TMPDIR=<state root>/tmp only when the user has set
nothing, writes it only to the USER settings file and only with consent (lock, backup, atomic
replace, every other key kept), never changes a value the user already chose, and the SessionStart
hint speaks up only when there is something to propose AND the current temp directory is
memory-backed. Everything runs as real processes against a temporary HOME / config dir / state
root; the mount table is a fixture file, so no test depends on how the host is mounted.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "36-claude-tmpdir.sh"
HOOK = PLUGIN / "hooks" / "check-setup-deps.sh"
ENV_NAME = "CLAUDE_CODE_TMPDIR"
HINT_TOKEN = "odoo-setup tmp"

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

_CLEARED = (ENV_NAME, "CLAUDE_SETTINGS", "ODOO_AI_NO_CLAUDE_TMP", "ODOO_AI_PROJECT_DIR",
            "ODOO_AI_WORKTREE_DIR")


class World:
    """A throwaway machine: home, Claude config dir, state root, a system temp dir and a mount
    table that says where the memory filesystems are."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.cfg = tmp_path / "cfg"
        self.state = tmp_path / "state"
        self.systemp = tmp_path / "systemp"
        self.proj = tmp_path / "proj"
        self.mountinfo = tmp_path / "mountinfo"
        for d in (self.home, self.cfg, self.systemp, self.proj):
            d.mkdir()
        self.settings = self.cfg / "settings.json"
        self.set_mount("tmpfs")

    def set_mount(self, fstype):
        """The system temp dir sits on `fstype`; None writes no mount table at all."""
        if fstype is None:
            self.mountinfo.unlink(missing_ok=True)
            return
        root = os.path.realpath(self.systemp)
        self.mountinfo.write_text(
            f"1 0 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
            f"36 1 0:30 / {root} rw,nosuid - {fstype} {fstype} rw\n")

    def write_settings(self, data):
        self.settings.write_text(data if isinstance(data, str) else json.dumps(data))

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in _CLEARED}
        env.update(HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.cfg),
                   ODOO_AI_HOME=str(self.state), ODOO_AI_MOUNTINFO=str(self.mountinfo),
                   TMPDIR=str(self.systemp))
        env.update(extra)
        return env

    def step(self, *args, umask=None, **extra):
        return subprocess.run(
            ["bash", str(STEP), *args], cwd=self.proj, env=self.env(**extra),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
            preexec_fn=(lambda: os.umask(umask)) if umask is not None else None)

    def hint(self, **extra):
        res = subprocess.run(["bash", str(HOOK)], input="{}", cwd=self.proj,
                             env=self.env(**extra), capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr
        return res.stderr

    def saved(self):
        return json.loads(self.settings.read_text())

    @property
    def target(self):
        return self.state / "tmp"

    def backups(self):
        return sorted(self.cfg.glob("settings.json.bak.*"))


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def _kv(out, key):
    for line in out.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


# --------------------------------------------------------------------------- #
# what is proposed
# --------------------------------------------------------------------------- #
@requires_bash
def test_nothing_set_proposes_the_tmp_folder_of_the_state_root_and_writes_nothing(world):
    assert world.step("check").returncode == 1
    out = world.step("propose").stdout
    assert _kv(out, "ACTION") == "propose"
    assert _kv(out, "TARGET") == str(world.target)
    assert os.path.isabs(_kv(out, "TARGET"))
    assert _kv(out, "QUESTION"), "the agent needs a question to put to the user"
    assert _kv(out, "CURRENT_TEMP_ROOT") == str(world.systemp)
    assert not world.settings.exists() and not world.state.exists()


@requires_bash
@pytest.mark.parametrize("fstype, expected", [
    ("tmpfs", "yes"), ("ramfs", "yes"), ("ext4", "no"), (None, "unknown")])
def test_proposal_says_whether_the_current_temp_dir_is_memory_backed(world, fstype, expected):
    world.set_mount(fstype)
    assert _kv(world.step("propose").stdout, "CURRENT_TEMP_MEMORY_BACKED") == expected


@requires_bash
def test_a_long_per_user_path_is_reported_as_information_not_refused(world):
    out = world.step("propose").stdout
    assert int(_kv(out, "PER_UID_PATH_BYTES")) > int(_kv(out, "SOCKET_PATH_LIMIT"))
    assert _kv(out, "SANDBOX_TMP_FALLBACK") == "yes"
    assert _kv(out, "ACTION") == "propose", "a long path still gets a proposal"
    assert _kv(out, "NOTE")
    assert world.step("apply", "--yes").returncode == 0


@requires_bash
def test_a_short_per_user_path_needs_no_fallback_note(world):
    out = world.step("propose", ODOO_AI_HOME="/s").stdout
    assert _kv(out, "SANDBOX_TMP_FALLBACK") == "no"
    assert _kv(out, "NOTE") is None


# --------------------------------------------------------------------------- #
# a value the user set is never changed
# --------------------------------------------------------------------------- #
@requires_bash
def test_a_value_in_the_environment_means_nothing_to_do(world):
    world.write_settings({"model": "x"})
    before = world.settings.read_bytes()
    env = {ENV_NAME: str(world.tmp / "mine")}
    assert world.step("check", **env).returncode == 0
    assert _kv(world.step("propose", **env).stdout, "ACTION") == "set-in-environment"
    assert _kv(world.step("propose", **env).stdout, "QUESTION") is None
    assert world.step("apply", "--yes", **env).returncode == 0
    assert world.settings.read_bytes() == before
    assert not world.state.exists()


@requires_bash
@pytest.mark.parametrize("value", [None, "", "/somewhere/else", "$HOME/tmp"])
def test_a_value_the_user_set_in_settings_is_never_changed(world, value):
    world.write_settings({"env": {ENV_NAME: value}, "model": "x"})
    before = world.settings.read_bytes()
    assert world.step("check").returncode == 0
    assert _kv(world.step("propose").stdout, "ACTION") == "set-in-settings"
    res = world.step("apply", "--yes")
    assert res.returncode == 0 and _kv(res.stdout, "RESULT") == "unchanged"
    assert world.settings.read_bytes() == before
    assert not world.backups() and not world.state.exists()


@requires_bash
def test_project_and_local_settings_do_not_count_because_claude_code_ignores_them_there(world):
    (world.proj / ".claude").mkdir()
    for name in ("settings.json", "settings.local.json"):
        (world.proj / ".claude" / name).write_text(json.dumps({"env": {ENV_NAME: "/x"}}))
    before = {p.name: p.read_bytes() for p in (world.proj / ".claude").iterdir()}
    assert world.step("check").returncode == 1
    assert world.step("apply", "--yes").returncode == 0
    assert {p.name: p.read_bytes() for p in (world.proj / ".claude").iterdir()} == before
    assert world.saved()["env"][ENV_NAME] == str(world.target)


# --------------------------------------------------------------------------- #
# apply: consent, exactly one key, safety
# --------------------------------------------------------------------------- #
@requires_bash
def test_apply_without_consent_writes_nothing(world):
    world.write_settings({"model": "x"})
    before = world.settings.read_bytes()
    res = world.step("apply")
    assert res.returncode == 0 and _kv(res.stdout, "RESULT") == "declined"
    assert world.settings.read_bytes() == before
    assert not world.state.exists() and not world.backups()


@requires_bash
def test_apply_with_consent_adds_exactly_one_key_and_keeps_everything_else(world):
    original = {"model": "x", "permissions": {"allow": ["Bash(ls)"]},
                "env": {"KEEP_ME": "1", "OTHER": "two"}}
    world.write_settings(original)
    before = world.settings.read_bytes()
    res = world.step("apply", "--yes")
    assert res.returncode == 0 and _kv(res.stdout, "RESULT") == "written"
    expected = json.loads(json.dumps(original))
    expected["env"][ENV_NAME] = str(world.target)
    assert world.saved() == expected
    assert os.path.isabs(world.saved()["env"][ENV_NAME]) and "~" not in str(world.target)
    backups = world.backups()
    assert len(backups) == 1 and backups[0].read_bytes() == before


@requires_bash
def test_apply_creates_the_directory_private_to_the_user_whatever_the_umask(world):
    res = world.step("apply", "--yes", umask=0)
    assert res.returncode == 0
    assert world.target.is_dir()
    assert stat.S_IMODE(world.target.stat().st_mode) == 0o700
    assert world.target.stat().st_uid == os.getuid()


@requires_bash
def test_apply_tightens_a_directory_that_already_exists_with_looser_rights(world):
    world.target.mkdir(parents=True)
    world.target.chmod(0o755)
    assert world.step("apply", "--yes").returncode == 0
    assert stat.S_IMODE(world.target.stat().st_mode) == 0o700


@requires_bash
def test_apply_creates_the_settings_file_when_there_is_none(world):
    assert not world.settings.exists()
    assert world.step("apply", "--yes").returncode == 0
    assert world.saved() == {"env": {ENV_NAME: str(world.target)}}
    assert not world.backups(), "nothing existed to back up"


@requires_bash
def test_second_apply_changes_nothing_and_says_so(world):
    world.write_settings({"model": "x"})
    assert world.step("apply", "--yes").returncode == 0
    after_first = world.settings.read_bytes()
    backups = world.backups()
    assert world.step("check").returncode == 0
    second = world.step("apply", "--yes")
    assert second.returncode == 0 and _kv(second.stdout, "RESULT") == "unchanged"
    assert world.settings.read_bytes() == after_first
    assert world.backups() == backups


@requires_bash
def test_opt_out_makes_check_pass_and_apply_do_nothing(world):
    world.write_settings({"model": "x"})
    before = world.settings.read_bytes()
    opt = {"ODOO_AI_NO_CLAUDE_TMP": "1"}
    assert world.step("check", **opt).returncode == 0
    assert _kv(world.step("propose", **opt).stdout, "ACTION") == "opted-out"
    res = world.step("apply", "--yes", **opt)
    assert res.returncode == 0 and _kv(res.stdout, "RESULT") == "opted-out"
    assert world.settings.read_bytes() == before
    assert not world.state.exists()


@requires_bash
@pytest.mark.parametrize("content", ["{not json", "[]", '"text"', '{"env": []}', '{"env": "x"}'])
def test_a_settings_file_that_cannot_be_edited_safely_is_refused_and_left_alone(world, content):
    world.write_settings(content)
    before = world.settings.read_bytes()
    res = world.step("apply", "--yes")
    assert res.returncode == 2
    assert world.settings.read_bytes() == before
    assert not world.state.exists(), "no directory is made for a write that was refused"
    assert not world.backups()


@requires_bash
def test_claude_config_dir_decides_which_settings_file_is_written(world):
    other = world.tmp / "elsewhere"
    other.mkdir()
    (other / "settings.json").write_text(json.dumps({"model": "y"}))
    res = world.step("apply", "--yes", CLAUDE_CONFIG_DIR=str(other))
    assert res.returncode == 0
    assert json.loads((other / "settings.json").read_text())["env"][ENV_NAME] == str(world.target)
    assert not world.settings.exists()
    assert not (world.home / ".claude").exists(), "the default config dir is not touched"


# --------------------------------------------------------------------------- #
# the SessionStart hint
# --------------------------------------------------------------------------- #
@requires_bash
def test_hint_is_shown_once_when_there_is_something_to_propose_and_the_temp_dir_is_memory(world):
    stderr = world.hint()
    assert stderr.count(HINT_TOKEN) == 1


@requires_bash
@pytest.mark.parametrize("why, setup", [
    ("the temp dir is on disk", lambda w: (w.set_mount("ext4"), {})[1]),
    ("the filesystem cannot be told", lambda w: (w.set_mount(None), {})[1]),
    ("the user set it in the environment", lambda w: {ENV_NAME: "/mine"}),
    ("the user set it in settings",
     lambda w: (w.write_settings({"env": {ENV_NAME: "/mine"}}), {})[1]),
    ("the user opted out", lambda w: {"ODOO_AI_NO_CLAUDE_TMP": "1"}),
])
def test_hint_stays_silent_when_there_is_nothing_to_do_or_nothing_wrong(world, why, setup):
    assert HINT_TOKEN not in world.hint(**setup(world)), why


@requires_bash
def test_hint_is_read_only(world):
    world.write_settings({"model": "x"})
    before = {p: p.read_bytes() for p in world.cfg.iterdir()}
    state_before = sorted(world.state.rglob("*")) if world.state.exists() else []
    assert HINT_TOKEN in world.hint()
    assert {p: p.read_bytes() for p in world.cfg.iterdir()} == before
    assert not world.target.exists()
    assert (sorted(world.state.rglob("*")) if world.state.exists() else []) == state_before


# --------------------------------------------------------------------------- #
# the writer on its own: it re-checks under its lock, whatever its caller measured
# --------------------------------------------------------------------------- #
def _set(world, settings, target):
    return subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "lib" / "claude_tmp.py"), "set",
         str(settings), str(target)],
        env=world.env(), capture_output=True, text=True, timeout=60)


def test_the_writer_never_replaces_a_value_that_appeared_after_the_measurement(world):
    world.write_settings({"env": {ENV_NAME: "/chosen/by/the/user"}})
    before = world.settings.read_bytes()
    res = _set(world, world.settings, world.target)
    assert res.returncode == 0 and _kv(res.stdout, "RESULT") == "unchanged"
    assert world.settings.read_bytes() == before
    assert not world.target.exists() and not world.backups()


@pytest.mark.parametrize("content", ["{not json", "[]", '{"env": []}'])
def test_the_writer_refuses_a_file_it_cannot_edit_safely_before_making_anything(world, content):
    world.write_settings(content)
    before = world.settings.read_bytes()
    res = _set(world, world.settings, world.target)
    assert res.returncode == 2
    assert world.settings.read_bytes() == before
    assert not world.target.exists() and not world.backups()
