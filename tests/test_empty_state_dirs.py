"""The SessionEnd sweep of empty per-project and per-worktree state folders
(scripts/lib/empty_state_dirs.py sweep).

The rule protected: a folder under <state root>/projects that holds only directories and that
nothing touched for a day is removed; anything holding any entry that is not a directory, or
touched within the day, stays; removal never deletes content. Ages are set with os.utime and every
path lives under tmp_path, with ODOO_AI_HOME pointing there.
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
OLD = 3 * DAY

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks and named pipes")

sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location("empty_state_dirs_under_test",
                                              LIB / "empty_state_dirs.py")
esd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(esd)


class World:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.state = tmp_path / "state"
        self.projects = self.state / "projects"
        self.projects.mkdir(parents=True)

    def dir(self, rel):
        path = self.projects / rel
        path.mkdir(parents=True, exist_ok=True)
        return path

    def settle(self, age=OLD):
        """Age every directory under projects/ so only what a test then touches is fresh."""
        t = time.time() - age
        for base, _dirs, _files in os.walk(self.projects, topdown=False):
            os.utime(base, (t, t), follow_symlinks=False)

    def sweep(self):
        return esd.sweep(root=str(self.state))

    def cli(self, **env):
        full = dict(os.environ, ODOO_AI_HOME=str(self.state), **env)
        return subprocess.run([sys.executable, str(LIB / "empty_state_dirs.py"), "sweep"],
                              env=full, capture_output=True, text=True, timeout=60)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_an_idle_worktree_folder_of_only_directories_is_removed(world):
    world.dir("p1/worktrees/w1/a/b")
    keep = world.dir("p1/worktrees/w2")
    (keep / "f.txt").write_text("x")
    world.settle()
    world.sweep()
    assert not (world.projects / "p1" / "worktrees" / "w1").exists()
    assert (keep / "f.txt").exists()


def test_a_project_whose_only_content_was_empty_worktree_folders_goes_in_the_same_run(world):
    world.dir("p1/worktrees/w1")
    world.dir("p1/worktrees/w2/x")
    world.settle()
    world.sweep()
    assert not (world.projects / "p1").exists()
    assert world.projects.is_dir(), "the projects folder itself stays"


def test_a_file_anywhere_in_a_tree_keeps_the_whole_folder(world):
    (world.dir("p1/worktrees/w1/deep/er") / "note.txt").write_text("x")
    world.dir("p1/worktrees/w1/empty-sibling")
    world.dir("p1/worktrees/w2")
    world.dir("p2")
    (world.dir("p3") / "state.json").write_text("{}")
    world.settle()
    world.sweep()
    assert (world.projects / "p1" / "worktrees" / "w1" / "deep" / "er" / "note.txt").exists()
    assert (world.projects / "p1" / "worktrees" / "w1" / "empty-sibling").is_dir()
    assert not (world.projects / "p1" / "worktrees" / "w2").exists(), "an empty sibling goes"
    assert (world.projects / "p3" / "state.json").exists()
    assert not (world.projects / "p2").exists()


@posix_only
def test_a_symlink_even_to_a_directory_keeps_the_folder_and_is_never_followed(world):
    outside = world.tmp / "outside"
    (outside / "inner").mkdir(parents=True)
    for d in (outside, outside / "inner"):
        os.utime(d, (1, 1))
    wt = world.dir("p1/worktrees/w1")
    (wt / "link").symlink_to(outside)
    os.utime(wt / "link", (1, 1), follow_symlinks=False)
    world.dir("p1/worktrees/w1/empty-sibling")
    world.dir("p2")
    (world.projects / "p2" / "dangling").symlink_to(world.tmp / "nowhere")
    world.settle()
    world.sweep()
    assert (wt / "link").is_symlink()
    assert (wt / "empty-sibling").is_dir(), "the folder is kept whole, not partly emptied"
    assert (world.projects / "p2" / "dangling").is_symlink()
    assert (outside / "inner").is_dir()


@posix_only
def test_an_entry_that_is_neither_file_nor_directory_keeps_the_folder(world):
    wt = world.dir("p1/worktrees/w1")
    os.mkfifo(wt / "pipe")
    world.dir("p1/worktrees/w1/empty-sibling")
    world.settle()
    world.sweep()
    assert (wt / "pipe").exists()
    assert (wt / "empty-sibling").is_dir()


def test_a_folder_modified_within_the_last_day_stays(world):
    world.dir("p1/worktrees/w-fresh/sub")
    world.dir("p1/worktrees/w-old")
    world.dir("p2/worktrees/w-old")
    deep = world.dir("p3/a/b")
    world.settle()
    t = time.time() - DAY // 2
    os.utime(world.projects / "p1" / "worktrees" / "w-fresh" / "sub", (t, t))
    os.utime(deep, (time.time() - 60, time.time() - 60))
    world.sweep()
    assert (world.projects / "p1" / "worktrees" / "w-fresh" / "sub").is_dir()
    assert not (world.projects / "p1" / "worktrees" / "w-old").exists()
    assert not (world.projects / "p2").exists()
    assert deep.is_dir(), "one fresh directory deep in a tree keeps the tree"


def test_removal_never_deletes_content_that_appears_during_the_sweep(world, monkeypatch):
    leaf = world.dir("p1/worktrees/w1/a")
    world.settle()
    real_judge = esd.idle_empty_tree

    def judge_then_race(path, cutoff):
        tree = real_judge(path, cutoff)
        (leaf / "late.txt").write_text("keep me")
        return tree

    monkeypatch.setattr(esd, "idle_empty_tree", judge_then_race)
    world.sweep()
    assert (leaf / "late.txt").read_text() == "keep me"


def test_an_os_error_on_one_folder_is_skipped_and_the_sweep_continues(world, monkeypatch):
    world.dir("p1")
    world.dir("p2")
    world.settle()
    real_rmdir = os.rmdir

    def failing_rmdir(path, *args, **kw):
        if os.path.basename(path) == "p1":
            raise PermissionError(13, "denied")
        return real_rmdir(path, *args, **kw)

    monkeypatch.setattr(os, "rmdir", failing_rmdir)
    world.sweep()
    assert (world.projects / "p1").is_dir()
    assert not (world.projects / "p2").exists()


@posix_only
def test_only_the_projects_folder_of_the_state_root_is_swept(world):
    around = [world.state / "logs" / "x", world.state / "tmp" / "claude-1" / "y",
              world.state / "runtime"]
    for d in around:
        d.mkdir(parents=True)
        os.utime(d, (1, 1))
    outside = world.tmp / "outside" / "p" / "worktrees" / "w"
    outside.mkdir(parents=True)
    os.utime(outside, (1, 1))
    world.dir("p1")
    (world.projects / "linked").symlink_to(world.tmp / "outside")
    world.settle()
    res = world.cli()
    assert res.returncode == 0
    assert not (world.projects / "p1").exists()
    assert all(d.is_dir() for d in around) and outside.is_dir()
    assert (world.projects / "linked").is_symlink()


@posix_only
def test_a_projects_folder_that_is_a_link_is_left_alone(world):
    outside = world.tmp / "outside"
    keep = outside / "p1"
    keep.mkdir(parents=True)
    os.utime(keep, (1, 1))
    shutil.rmtree(world.projects)
    world.projects.symlink_to(outside)
    world.sweep()
    assert keep.is_dir()


def test_resolving_a_swept_project_and_worktree_folder_again_recreates_it(world):
    repo = world.tmp / "repo"
    repo.mkdir()
    (repo / ".odoo-ai-root").write_text("")
    env = dict(os.environ, ODOO_AI_HOME=str(world.state))
    env.pop("ODOO_AI_PROJECT_DIR", None)
    code = ("import sys; sys.path.insert(0, %r); import paths; "
            "print(paths.share_dir()); print(paths.isolate_dir())" % str(LIB))

    def resolve():
        return subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=60)

    first = resolve()
    assert first.returncode == 0, first.stderr
    share, isolate = first.stdout.split()
    assert os.path.isdir(share) and os.path.isdir(isolate)
    world.settle()
    world.sweep()
    assert not os.path.exists(share)
    again = resolve()
    assert again.stdout.split() == [share, isolate]
    assert os.path.isdir(share) and os.path.isdir(isolate)


def test_the_cli_prints_one_summary_line_only_when_it_removed_something(world):
    world.dir("p1/worktrees/w1")
    world.settle()
    res = world.cli()
    assert res.returncode == 0 and len(res.stdout.splitlines()) == 1
    again = world.cli()
    assert again.returncode == 0 and again.stdout == ""


def test_no_projects_folder_means_nothing_to_do_and_nothing_is_created(tmp_path):
    state = tmp_path / "state"
    res = subprocess.run([sys.executable, str(LIB / "empty_state_dirs.py"), "sweep"],
                         env=dict(os.environ, ODOO_AI_HOME=str(state)),
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and res.stdout == "" and not state.exists()


def test_the_session_end_worker_runs_the_sweep(tmp_path):
    plugin = tmp_path / "plugin"
    lib = plugin / "scripts" / "lib"
    lib.mkdir(parents=True)
    for name in ("run_bounded.sh", "empty_state_dirs.py", "paths.py"):
        shutil.copy2(LIB / name, lib / name)
    (lib / "allocator.py").write_text("import sys\n")
    world = World(tmp_path)
    world.dir("p1/worktrees/w1")
    keep = world.dir("p2/worktrees/w1")
    (keep / "f.txt").write_text("x")
    world.settle()
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), ODOO_AI_HOME=str(world.state),
               HOME=str(tmp_path / "home"))
    res = subprocess.run(["bash", str(SESSION_END), "--detached-worker", "", ""], env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert res.stdout == ""
    assert not (world.projects / "p1").exists() and (keep / "f.txt").exists()
