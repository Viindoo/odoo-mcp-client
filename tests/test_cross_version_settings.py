"""Behaviour tests: sessions of different plugin versions share the user's Claude Code configuration
(CLAUDE.md, settings.json) and must not undo each other's entries there.

Each session's SessionStart hooks converge three things in the shared files:
  - the ETHOS @import block of CLAUDE.md                (hooks/ensure-ethos-import.sh),
  - the Bash/Read/Edit/MCP allow rules                   (hooks/ensure-state-root-permissions.sh),
  - the autoMode entries and the push guard              (hooks/ensure-auto-mode.sh).

The contract, stated as behaviour:
  - among versions from this one on, a session of an OLDER version changes nothing a NEWER version
    wrote, and the newer version's start repairs what is missing;
  - against the releases that already shipped (their real scripts, taken from pinned commits and
    run unchanged), what a session needs at runtime does not depend on an entry those releases
    rewrite: the permission rules a command needs and the autoMode entries survive their start;
    the one entry they still rewrite - the ETHOS import path - is put back by the next start of
    this version;
  - a user's own entries and another plugin's are never touched.

The shipped releases are read with `git archive <pinned commit>` into a temp plugin cache (skipped on
a shallow clone, a failure in CI where the workflow fetches the full history). "This version" is the
working tree, installed under the plugin cache as version 99.x so that it orders after every release;
a second and third copy stand for a newer and an older version from this one on. Throwaway
CLAUDE_CONFIG_DIR, settings, state root and catalog: the real ones are never touched.
"""
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
PLUGIN_REL = "plugins/odoo-ai-agents"

# Release commits (`chore: release odoo-ai-agents <version>`). 8.12.2 and 8.13.0 differ in step 32 and
# in the auto-mode wording; the ETHOS hook and step 34 are the same in both.
RELEASES = {
    "8.12.2": "ee5180e8f2e2ef0519ffe4a7144f830e89bb432d",
    "8.13.0": "5ab72b3912a901e2274220c571a370a2077f8a4b",
}
OLDER_NEW, THIS, NEWER_NEW = "98.0.0", "99.0.0", "99.1.0"  # versions from this one on (copies of the tree)

SCRIPT_REL = "scripts/lib/resolve_project_dir.sh"
ETHOS_BEGIN = "<!-- BEGIN odoo-ai-agents ETHOS import (managed by ensure-ethos-import.sh - do not edit inside) -->"
LEGACY_TAG = "odoo-ai-agents: "


def _release_unavailable(reason):
    if os.environ.get("CI"):
        pytest.fail(reason + " - CI must check out the full history (fetch-depth: 0)")
    pytest.skip(reason)


def _extract_release(version, dest):
    if shutil.which("git") is None:
        _release_unavailable("git is not available")
    proc = subprocess.run(["git", "-C", str(ROOT), "archive", RELEASES[version], PLUGIN_REL],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        _release_unavailable(f"release {version} is not in this clone (shallow checkout?)")
    tmp_tar = dest.parent / f"release-{version}.tar"
    tmp_tar.write_bytes(proc.stdout)
    with tarfile.open(tmp_tar) as tar:
        tar.extractall(dest.parent / f"release-{version}", filter="data")
    tmp_tar.unlink()
    shutil.move(str(dest.parent / f"release-{version}" / PLUGIN_REL), str(dest))
    shutil.rmtree(dest.parent / f"release-{version}")
    shipped = json.loads((dest / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert shipped == version, f"pinned commit for {version} holds plugin version {shipped}"


def _install_working_tree(version, dest):
    shutil.copytree(PLUGIN, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    manifest = dest / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = version
    manifest.write_text(json.dumps(data), encoding="utf-8")


def _git(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, env={
        **os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


class World:
    """One machine: a Claude config dir holding a plugin cache with every version installed, the
    user's settings and CLAUDE.md, a state root and an instance catalog with one git repository."""

    def __init__(self, base):
        self.base = base
        self.cfg = base / "claude"
        self.cache = self.cfg / "plugins" / "cache" / "viindoo-plugins" / "odoo-ai-agents"
        self.cache.mkdir(parents=True)
        self.settings = self.cfg / "settings.json"
        self.claude_md = self.cfg / "CLAUDE.md"
        self.home = base / "odoo-ai"
        self.home.mkdir()
        repo = base / "work" / "addons-repo"
        (repo / "addons").mkdir(parents=True)
        for args in (("git", "init", "-q", "-b", "17.0"),
                     ("git", "commit", "-q", "--allow-empty", "-m", "init"),
                     ("git", "remote", "add", "origin", "git@example.org:acme/addons-repo.git")):
            _git(repo, *args)
        self.catalog = self.home / "instances.toml"
        self.catalog.write_text('[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (repo / "addons"),
                                encoding="utf-8")
        self.versions = {}

    def install(self, version):
        dest = self.cache / version
        if version in RELEASES:
            _extract_release(version, dest)
        else:
            _install_working_tree(version, dest)
        (dest / "ODOO-AI-ETHOS.md").write_text(f"# ETHOS of {version}\n", encoding="utf-8")
        self.versions[version] = dest
        return dest

    def root(self, version):
        return self.cache / version

    def run(self, version, script, *args):
        """A script of one installed version, exactly as that version's session runs it."""
        env = dict(os.environ)
        for name in ("CLAUDE_PLUGIN_ROOT", "ODOO_AI_NO_AUTO_PERMS", "ODOO_AI_NO_ETHOS_IMPORT"):
            env.pop(name, None)
        env.update(CLAUDE_CONFIG_DIR=str(self.cfg), CLAUDE_SETTINGS=str(self.settings),
                   ODOO_AI_HOME=str(self.home), ODOO_AI_INSTANCES=str(self.catalog),
                   HOME=str(self.base / "home"),
                   ODOO_AI_TEMP_DIRS=str(self.base / "system-temp-elsewhere"))
        return subprocess.run(["bash", str(self.root(version) / script), *args], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)

    def start(self, version, hook):
        proc = self.run(version, f"hooks/{hook}")
        assert proc.returncode == 0, f"{hook} of {version}: rc={proc.returncode} {proc.stderr}"
        return proc

    def data(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def allow(self):
        return list((self.data().get("permissions") or {}).get("allow") or [])

    def import_line(self):
        lines = self.claude_md.read_text(encoding="utf-8").splitlines()
        return lines[lines.index(ETHOS_BEGIN) + 1]

    def snapshot(self):
        return (self.settings.read_text(encoding="utf-8") if self.settings.exists() else None,
                self.claude_md.read_text(encoding="utf-8") if self.claude_md.exists() else None)


@pytest.fixture()
def machine(tmp_path_factory):
    """A factory: `machine(*versions)` is a machine with those plugin versions installed."""
    def build(*names):
        w = World(tmp_path_factory.mktemp("world"))
        w.settings.write_text("{}", encoding="utf-8")
        for version in names:
            w.install(version)
        return w
    return build


def import_of(w, version):
    return f"@{w.root(version)}/ODOO-AI-ETHOS.md"


# --------------------------------------------------------------------------- #
# a) the ETHOS @import of CLAUDE.md
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("release", ["8.12.2", "8.13.0"])
def test_a_shipped_release_still_rewrites_the_import_and_the_next_start_of_this_version_restores_it(machine, release):
    world = machine(THIS, "8.12.2", "8.13.0")
    world.start(THIS, "ensure-ethos-import.sh")
    assert world.import_line() == import_of(world, THIS)
    world.start(release, "ensure-ethos-import.sh")
    assert world.import_line() == import_of(world, release), "the shipped hook heals any path to its own"
    world.start(THIS, "ensure-ethos-import.sh")
    assert world.import_line() == import_of(world, THIS)


def test_an_older_version_from_this_one_on_never_replaces_a_newer_versions_import(machine):
    world = machine(OLDER_NEW, THIS, NEWER_NEW)
    world.start(NEWER_NEW, "ensure-ethos-import.sh")
    written = world.snapshot()
    world.start(THIS, "ensure-ethos-import.sh")
    world.start(OLDER_NEW, "ensure-ethos-import.sh")
    assert world.snapshot() == written, "an older version's start must leave CLAUDE.md byte-identical"
    assert world.import_line() == import_of(world, NEWER_NEW)


def test_a_newer_versions_start_puts_its_import_over_an_older_versions(machine):
    world = machine(OLDER_NEW, THIS)
    world.start(OLDER_NEW, "ensure-ethos-import.sh")
    world.start(THIS, "ensure-ethos-import.sh")
    assert world.import_line() == import_of(world, THIS)


def test_an_import_of_a_newer_version_whose_file_is_gone_is_healed(machine):
    world = machine(THIS, NEWER_NEW)
    world.start(NEWER_NEW, "ensure-ethos-import.sh")
    (world.root(NEWER_NEW) / "ODOO-AI-ETHOS.md").unlink()
    world.start(THIS, "ensure-ethos-import.sh")
    assert world.import_line() == import_of(world, THIS)


def test_a_users_own_claude_md_content_survives_every_version(machine):
    world = machine(THIS, NEWER_NEW)
    mine = "# my notes\n\nuse tabs\n"
    world.claude_md.write_text(mine, encoding="utf-8")
    world.start(NEWER_NEW, "ensure-ethos-import.sh")
    world.start(THIS, "ensure-ethos-import.sh")
    text = world.claude_md.read_text(encoding="utf-8")
    assert text.startswith(mine)
    assert text.count(ETHOS_BEGIN) == 1


# --------------------------------------------------------------------------- #
# b) the allow rules of the state-root step
# --------------------------------------------------------------------------- #
def _granted(allow, command):
    """Whether an allow list grants `command`, by the documented Bash rule semantics: a rule with no
    `*` matches one exact command; a trailing ` *` also matches the bare command."""
    for rule in allow:
        if not (rule.startswith("Bash(") and rule.endswith(")")):
            continue
        body = rule[len("Bash("):-1]
        if body == command:
            return True
        if body.endswith(" *") and body.count("*") == 1:
            head = body[:-2]
            if command == head or command.startswith(head + " "):
                return True
    return False


def _commands(w, version):
    return [f"bash {w.root(version)}/{SCRIPT_REL} {axis}" for axis in ("share", "isolate")]


@pytest.mark.parametrize("release", ["8.12.2", "8.13.0"])
def test_the_command_of_every_installed_version_stays_granted_across_a_shipped_releases_start(machine, release):
    world = machine(THIS, "8.12.2", "8.13.0")
    world.start(THIS, "ensure-state-root-permissions.sh")
    for version in (THIS, "8.12.2", "8.13.0"):
        for command in _commands(world, version):
            assert _granted(world.allow(), command), f"after this version's start: {command}"
    world.start(release, "ensure-state-root-permissions.sh")
    for version in (THIS, "8.12.2", "8.13.0"):
        for command in _commands(world, version):
            assert _granted(world.allow(), command), f"after {release}'s start: {command}"


def test_the_rules_this_version_wrote_survive_both_shipped_releases_and_nothing_else_is_touched(machine):
    world = machine(THIS, "8.12.2", "8.13.0")
    world.settings.write_text(json.dumps({"permissions": {"allow": ["Bash(sudo *)", "mcp__other__tool"]},
                                          "model": "x"}), encoding="utf-8")
    world.start(THIS, "ensure-state-root-permissions.sh")
    mine = [a for a in world.allow() if a.startswith("Bash(bash ") and a.endswith(" *)")]
    assert len(mine) == 6, f"two rules for each of the three installed versions; got {mine}"
    world.start("8.12.2", "ensure-state-root-permissions.sh")
    world.start("8.13.0", "ensure-state-root-permissions.sh")
    allow = world.allow()
    assert set(mine) <= set(allow)
    assert "Bash(sudo *)" in allow and "mcp__other__tool" in allow
    assert world.data()["model"] == "x"


def test_this_versions_start_after_a_shipped_release_writes_nothing_more_to_converge(machine):
    world = machine(THIS, "8.12.2", "8.13.0")
    world.start(THIS, "ensure-state-root-permissions.sh")
    world.start("8.13.0", "ensure-state-root-permissions.sh")
    world.start(THIS, "ensure-state-root-permissions.sh")
    again = world.snapshot()
    world.start(THIS, "ensure-state-root-permissions.sh")
    assert world.snapshot() == again
    check = world.run(THIS, "scripts/setup-steps/32-permissions-state-root.sh", "check")
    assert check.returncode == 0, check.stderr


def test_versions_from_this_one_on_never_undo_each_others_rules(machine):
    world = machine(OLDER_NEW, THIS, NEWER_NEW)
    world.start(NEWER_NEW, "ensure-state-root-permissions.sh")
    written = world.snapshot()
    world.start(THIS, "ensure-state-root-permissions.sh")
    world.start(OLDER_NEW, "ensure-state-root-permissions.sh")
    assert world.snapshot() == written


# --------------------------------------------------------------------------- #
# c) and d) autoMode.allow / autoMode.environment (and soft_deny, permissions.ask)
# --------------------------------------------------------------------------- #
AUTO_GROUPS = ("allow", "soft_deny", "environment")


def _approve_with(w, version):
    """The owner's one-time approval, run by the step of `version`."""
    out = w.run(version, "scripts/setup-steps/34-auto-mode.sh", "apply")
    assert out.returncode == 0, out.stderr


def _plugin_entries(w, tag_start):
    data = w.data()
    return {g: [e for e in data["autoMode"][g] if e.startswith(tag_start)] for g in AUTO_GROUPS}


def _versioned(w, version):
    return _plugin_entries(w, f"odoo-ai-agents@{version}: ")


@pytest.mark.parametrize("release", ["8.12.2", "8.13.0"])
def test_entries_this_version_wrote_survive_a_shipped_releases_start_untouched(machine, release):
    """An approval given on a shipped release is migrated by this version to its own tag; the
    shipped release then finds no entry it recognises, so it neither prunes nor rewrites."""
    world = machine(THIS, "8.12.2", "8.13.0")
    _approve_with(world, release)
    assert any(_plugin_entries(world, LEGACY_TAG).values()), "the shipped release writes the plain tag"
    world.start(THIS, "ensure-auto-mode.sh")
    assert not any(_plugin_entries(world, LEGACY_TAG).values()), "the earlier tag is migrated away"
    mine = _versioned(world, THIS)
    assert all(mine[g] for g in AUTO_GROUPS)
    written = world.snapshot()
    world.start(release, "ensure-auto-mode.sh")
    assert world.snapshot() == written, "the shipped hook finds no approval marker and writes nothing"


@pytest.mark.parametrize("release", ["8.12.2", "8.13.0"])
def test_a_shipped_release_that_rewrites_its_own_entries_leaves_this_versions_entries_alone(machine, release):
    """The owner runs the setup step again inside a session of a shipped release: its plain-tag
    entries return beside this version's, which stay exactly as written; this version's next start
    removes the plain-tag ones."""
    world = machine(THIS, "8.12.2", "8.13.0")
    world.start(THIS, "ensure-auto-mode.sh")  # no approval yet: nothing is written
    assert not world.data().get("autoMode")
    _approve_with(world, THIS)
    mine = _versioned(world, THIS)
    _approve_with(world, release)
    assert _versioned(world, THIS) == mine, "this version's entries must survive the shipped step"
    assert any(_plugin_entries(world, LEGACY_TAG).values())
    world.start(release, "ensure-auto-mode.sh")
    assert _versioned(world, THIS) == mine
    world.start(THIS, "ensure-auto-mode.sh")
    assert not any(_plugin_entries(world, LEGACY_TAG).values())
    assert _versioned(world, THIS) == mine


def test_users_own_auto_mode_entries_and_asks_survive_migration_and_the_shipped_release(machine):
    world = machine(THIS, "8.13.0")
    world.settings.write_text(json.dumps({
        "autoMode": {"allow": ["$defaults", "my own allow"], "environment": ["my own environment"]},
        "permissions": {"ask": ["Bash(rm -rf *)"]}}), encoding="utf-8")
    _approve_with(world, "8.13.0")
    world.start(THIS, "ensure-auto-mode.sh")
    world.start("8.13.0", "ensure-auto-mode.sh")
    data = world.data()
    assert "my own allow" in data["autoMode"]["allow"]
    assert "my own environment" in data["autoMode"]["environment"]
    assert "Bash(rm -rf *)" in data["permissions"]["ask"]
    assert all(data["autoMode"][g][0] == "$defaults" for g in ("allow", "soft_deny", "environment"))


def test_an_older_version_from_this_one_on_never_replaces_entries_a_newer_version_wrote(machine):
    world = machine(OLDER_NEW, THIS, NEWER_NEW)
    _approve_with(world, NEWER_NEW)
    written = world.snapshot()
    for version in (THIS, OLDER_NEW):
        check = world.run(version, "scripts/setup-steps/34-auto-mode.sh", "check")
        assert check.returncode == 0, f"{version}: an array of a newer version is in sync; {check.stderr}"
        world.start(version, "ensure-auto-mode.sh")
        _approve_with(world, version)
    assert world.snapshot() == written
    assert not any(_versioned(world, THIS).values()) and not any(_versioned(world, OLDER_NEW).values())


def test_a_newer_versions_start_replaces_the_entries_of_an_older_version(machine):
    world = machine(THIS, NEWER_NEW)
    _approve_with(world, THIS)
    old_entries = _versioned(world, THIS)
    assert all(old_entries[g] for g in AUTO_GROUPS)
    world.start(NEWER_NEW, "ensure-auto-mode.sh")
    assert not any(_versioned(world, THIS).values())
    assert all(_versioned(world, NEWER_NEW)[g] for g in AUTO_GROUPS)
    check = world.run(NEWER_NEW, "scripts/setup-steps/34-auto-mode.sh", "check")
    assert check.returncode == 0, check.stderr
