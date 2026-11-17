"""`state_sweep.py` removes run-scoped state by the NEWEST time inside each entry, reports what it
removed, and never leaves the plugin state root."""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "state_sweep.py"
HOUR = 3600


def _age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t), follow_symlinks=False)


def _run(home, *args):
    env = dict(os.environ, ODOO_AI_HOME=str(home))
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True,
                          text=True, env=env)


def _run_dir(base, name, age, inner_age=None):
    d = base / name
    d.mkdir(parents=True)
    f = d / "f.txt"
    f.write_text("x")
    _age(f, age if inner_age is None else inner_age)
    _age(d, age)
    return d


def test_old_directories_are_removed_and_reported_sorted(tmp_path):
    base = tmp_path / "state" / "runs"
    _run_dir(base, "b-old", 5 * HOUR)
    _run_dir(base, "a-old", 5 * HOUR)
    _run_dir(base, "fresh", 60)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120)
    assert res.returncode == 0
    assert res.stdout.splitlines() == ["SWEPT=2", "REMOVED=a-old", "REMOVED=b-old"]
    assert sorted(p.name for p in base.iterdir()) == ["fresh"]


def test_a_directory_with_a_fresh_file_inside_is_kept_though_its_own_time_is_old(tmp_path):
    base = tmp_path / "state" / "runs"
    _run_dir(base, "busy", 5 * HOUR, inner_age=60)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120)
    assert res.stdout.splitlines() == ["SWEPT=0"]
    assert (base / "busy" / "f.txt").exists()


def test_a_fresh_file_deep_below_keeps_the_whole_directory(tmp_path):
    base = tmp_path / "state" / "runs"
    d = _run_dir(base, "deep", 5 * HOUR)
    sub = d / "a" / "b"
    sub.mkdir(parents=True)
    (sub / "g").write_text("y")
    _age(d / "a", 5 * HOUR)
    _age(sub, 5 * HOUR)
    assert _run(tmp_path / "state", base, "--older-than-minutes", 120).stdout.startswith("SWEPT=0")


def test_files_mode_removes_only_old_matching_files(tmp_path):
    base = tmp_path / "state" / "notes"
    base.mkdir(parents=True)
    for name, age in (("old.md", 5 * HOUR), ("new.md", 60), ("old.txt", 5 * HOUR)):
        (base / name).write_text("x")
        _age(base / name, age)
    _run_dir(base, "adir", 5 * HOUR)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120, "--files", "--name", "*.md")
    assert res.stdout.splitlines() == ["SWEPT=1", "REMOVED=old.md"]
    assert sorted(p.name for p in base.iterdir()) == ["adir", "new.md", "old.txt"]


def test_excluded_children_are_never_touched(tmp_path):
    base = tmp_path / "state" / "runs"
    _run_dir(base, "keep", 5 * HOUR)
    _run_dir(base, "go", 5 * HOUR)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120, "--exclude", "keep")
    assert res.stdout.splitlines() == ["SWEPT=1", "REMOVED=go"]
    assert (base / "keep").is_dir()


def test_a_missing_directory_is_zero_swept(tmp_path):
    res = _run(tmp_path / "state", tmp_path / "state" / "nope", "--older-than-minutes", 1)
    assert res.returncode == 0 and res.stdout.splitlines() == ["SWEPT=0"]


def test_the_directory_itself_is_never_removed(tmp_path):
    base = tmp_path / "state" / "runs"
    base.mkdir(parents=True)
    _age(base, 9 * HOUR)
    _run(tmp_path / "state", base, "--older-than-minutes", 1)
    assert base.is_dir()


def test_a_symlinked_child_is_unlinked_and_its_target_survives(tmp_path):
    base = tmp_path / "state" / "runs"
    base.mkdir(parents=True)
    outside = tmp_path / "outside"
    _run_dir(outside, "precious", 9 * HOUR)
    link = base / "link"
    link.symlink_to(outside / "precious", target_is_directory=True)
    _age(link, 9 * HOUR)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120)
    assert res.stdout.splitlines() == ["SWEPT=1", "REMOVED=link"]
    assert not link.is_symlink() and (outside / "precious" / "f.txt").exists()


def test_a_symlink_inside_a_directory_is_not_followed_for_its_age(tmp_path):
    base = tmp_path / "state" / "runs"
    d = _run_dir(base, "run", 9 * HOUR)
    fresh = tmp_path / "fresh-target"
    fresh.mkdir()
    (d / "ln").symlink_to(fresh, target_is_directory=True)
    _age(d / "ln", 9 * HOUR)
    _age(d, 9 * HOUR)
    res = _run(tmp_path / "state", base, "--older-than-minutes", 120)
    assert res.stdout.splitlines() == ["SWEPT=1", "REMOVED=run"]
    assert fresh.is_dir()


def test_a_directory_outside_the_state_root_is_a_usage_error(tmp_path):
    other = tmp_path / "elsewhere"
    _run_dir(other, "old", 9 * HOUR)
    res = _run(tmp_path / "state", other, "--older-than-minutes", 1)
    assert res.returncode == 2
    assert (other / "old").is_dir()


def test_the_state_root_itself_is_refused(tmp_path):
    (tmp_path / "state").mkdir()
    assert _run(tmp_path / "state", tmp_path / "state", "--older-than-minutes", 1).returncode == 2
