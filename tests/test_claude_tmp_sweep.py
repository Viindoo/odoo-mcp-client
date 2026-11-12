"""The SessionEnd sweep of Claude Code's temp directory (scripts/lib/claude_tmp.py sweep).

The rule protected: only the directory setup step 36 keeps in the state root is swept - never the
system temp directory, never a location the user pointed the variable at - and inside it only a
per-session folder that no file in has changed for 30 days, old files directly under
bash-edit-diff, and a project folder left empty. Anything else stays, links are never followed,
and a sweep never fails the hook. Ages are set with os.utime; everything lives under tmp_path.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
SESSION_END = PLUGIN / "hooks" / "session-end-gc.sh"
DAY = 24 * 3600

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX temp-dir layout")

spec = importlib.util.spec_from_file_location("claude_tmp_under_test", LIB / "claude_tmp.py")
claude_tmp = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(LIB))
spec.loader.exec_module(claude_tmp)


class Root:
    """A state root with the managed Claude Code temp directory in it."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.state = tmp_path / "state"
        self.managed = self.state / "tmp" / f"claude-{os.getuid()}"
        self.managed.mkdir(parents=True)

    def file(self, rel, age_days, base=None):
        path = (base or self.managed) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
        t = time.time() - age_days * DAY
        os.utime(path, (t, t))
        return path

    def sweep(self):
        return claude_tmp.sweep(root=str(self.state))

    def cli(self, **env):
        full = dict(os.environ, ODOO_AI_HOME=str(self.state), **env)
        return subprocess.run([sys.executable, str(LIB / "claude_tmp.py"), "sweep"], env=full,
                              capture_output=True, text=True, timeout=60)


@pytest.fixture
def root(tmp_path):
    return Root(tmp_path)


@posix_only
def test_a_session_idle_for_more_than_30_days_is_removed_whole(root):
    root.file("-proj-a/s1/scratchpad/a.txt", 31)
    root.file("-proj-a/s1/tasks/b.out", 90)
    root.file("-proj-a/s1/images/c.png", 45)
    root.sweep()
    assert not (root.managed / "-proj-a" / "s1").exists()


@posix_only
def test_one_fresh_file_keeps_the_whole_session(root):
    old = root.file("-proj-a/s1/scratchpad/a.txt", 90)
    fresh = root.file("-proj-a/s1/tasks/b.out", 29)
    root.sweep()
    assert old.exists() and fresh.exists()


@posix_only
def test_a_session_with_no_file_yet_is_not_idle(root):
    (root.managed / "-proj-a" / "s-new" / "scratchpad").mkdir(parents=True)
    root.sweep()
    assert (root.managed / "-proj-a" / "s-new" / "scratchpad").is_dir()


@posix_only
def test_only_the_idle_sessions_of_a_project_go(root):
    gone = root.file("-proj-a/idle/x.txt", 40)
    kept = root.file("-proj-a/busy/y.txt", 1)
    root.sweep()
    assert not gone.exists() and kept.exists()


@posix_only
def test_old_files_directly_under_bash_edit_diff_go_and_fresh_ones_stay(root):
    old = root.file("bash-edit-diff/old.diff", 31)
    fresh = root.file("bash-edit-diff/new.diff", 5)
    nested = root.file("bash-edit-diff/sub/very-old.diff", 400)
    os.utime(nested.parent, (1, 1))
    root.sweep()
    assert not old.exists() and fresh.exists()
    assert nested.exists(), "only files directly under bash-edit-diff are swept"
    assert (root.managed / "bash-edit-diff").is_dir(), "the directory itself stays"


@posix_only
def test_a_project_folder_left_empty_goes(root):
    root.file("-proj-a/s1/a.txt", 60)
    root.file("-proj-b/s2/b.txt", 60)
    root.file("-proj-b/s3/c.txt", 1)
    root.sweep()
    assert not (root.managed / "-proj-a").exists()
    assert (root.managed / "-proj-b" / "s3" / "c.txt").exists()


@posix_only
def test_anything_else_under_the_root_stays(root):
    stray_root = root.file("notes.txt", 400)
    stray_in_project = root.file("-proj-a/readme.txt", 400)
    root.file("-proj-a/s1/a.txt", 60)
    root.sweep()
    assert stray_root.exists() and stray_in_project.exists()
    assert (root.managed / "-proj-a").is_dir(), "a project folder with a file in it is not empty"


@posix_only
def test_nothing_outside_the_managed_directory_is_touched(root):
    around = [
        root.file(f"tmp/claude-{os.getuid() + 1}/-proj-a/s1/a.txt", 400, base=root.state),
        root.file("projects/old.png", 400, base=root.state),
        root.file("scratch/x.txt", 400, base=root.state),
    ]
    pointed = root.tmp / "pointed-elsewhere"
    system = root.tmp / "system-temp"
    around += [
        root.file(f"claude-{os.getuid()}/-proj-a/s1/a.txt", 400, base=pointed),
        root.file(f"claude-{os.getuid()}/bash-edit-diff/a.diff", 400, base=pointed),
        root.file(f"claude-{os.getuid()}/-proj-a/s1/a.txt", 400, base=system),
    ]
    root.file("-proj-a/s1/a.txt", 400)
    res = root.cli(CLAUDE_CODE_TMPDIR=str(pointed), TMPDIR=str(system))
    assert res.returncode == 0
    assert all(p.exists() for p in around)
    assert not (root.managed / "-proj-a").exists(), "the managed directory was swept"


@posix_only
def test_links_are_never_followed_out_of_the_root(root):
    outside = root.tmp / "outside"
    keep = [root.file("s/a.txt", 400, base=outside), root.file("fresh.txt", 400, base=outside),
            root.file("recent.txt", 0, base=outside)]
    root.file("-proj-a/idle/a.txt", 60)
    inner_link = root.managed / "-proj-a" / "idle" / "link-to-outside"
    inner_link.symlink_to(outside)
    os.utime(inner_link, (1, 1), follow_symlinks=False)
    (root.managed / "-proj-a" / "linked-session").symlink_to(outside)
    (root.managed / "linked-project").symlink_to(outside)
    (root.managed / "bash-edit-diff").mkdir()
    (root.managed / "bash-edit-diff" / "old-link").symlink_to(outside / "fresh.txt")
    os.utime(root.managed / "bash-edit-diff" / "old-link", (1, 1), follow_symlinks=False)
    root.sweep()
    assert all(p.exists() for p in keep)
    assert not (root.managed / "-proj-a" / "idle").exists(), "the idle session itself went"
    assert (root.managed / "-proj-a" / "linked-session").is_symlink()
    assert (root.managed / "linked-project").is_symlink()
    assert not os.path.lexists(root.managed / "bash-edit-diff" / "old-link"), "the link goes"


@posix_only
def test_a_managed_directory_that_is_itself_a_link_is_left_alone(root):
    outside = root.tmp / "outside"
    keep = root.file("-proj-a/s1/a.txt", 400, base=outside)
    shutil.rmtree(root.managed)
    root.managed.symlink_to(outside)
    root.sweep()
    assert keep.exists()


@posix_only
def test_no_managed_directory_means_nothing_to_do_and_nothing_is_created(tmp_path):
    state = tmp_path / "state"
    assert claude_tmp.sweep(root=str(state)) == (0, 0)
    assert not state.exists()
    res = subprocess.run([sys.executable, str(LIB / "claude_tmp.py"), "sweep"],
                         env=dict(os.environ, ODOO_AI_HOME=str(state)),
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and res.stdout == "" and not state.exists()


@posix_only
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads anything")
def test_a_session_that_cannot_be_read_is_not_judged_idle(root):
    readable = root.file("-proj-a/s1/readable.txt", 400)
    locked = root.file("-proj-a/s1/locked/a.txt", 400).parent
    locked.chmod(0)
    try:
        assert root.sweep() == (0, 0)
        assert readable.exists(), "nothing of a session that cannot be read in full is deleted"
    finally:
        locked.chmod(0o700)


@posix_only
def test_the_cli_prints_one_summary_line_only_when_it_removed_something(root):
    root.file("-proj-a/s1/a.txt", 60)
    root.file("bash-edit-diff/a.diff", 60)
    res = root.cli()
    assert res.returncode == 0 and len(res.stdout.splitlines()) == 1
    again = root.cli()
    assert again.returncode == 0 and again.stdout == ""


@posix_only
def test_the_session_end_worker_runs_the_sweep(tmp_path):
    plugin = tmp_path / "plugin"
    lib = plugin / "scripts" / "lib"
    lib.mkdir(parents=True)
    for name in ("run_bounded.sh", "claude_tmp.py", "claude_settings.py", "config_merge.py",
                 "paths.py"):
        shutil.copy2(LIB / name, lib / name)
    (lib / "allocator.py").write_text("import sys\n")
    world = Root(tmp_path)
    idle = world.file("-proj-a/s1/a.txt", 60)
    fresh = world.file("-proj-a/s2/b.txt", 1)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), ODOO_AI_HOME=str(world.state),
               HOME=str(tmp_path / "home"))
    res = subprocess.run(["bash", str(SESSION_END), "--detached-worker", "", ""], env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert not idle.exists() and fresh.exists()
