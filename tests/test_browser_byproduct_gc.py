"""prune_browser_byproducts: stale files the browser servers write ON THEIR OWN are deleted, and
nothing an agent or another skill owns is ever touched.

With the state-root flags, playwright names its own files (console-*.log, page-*.png, traces/,
session-*/...) at the top level of <root>/projects - the parent of every per-repo state dir - and
pagecast records into <root>/scratch/pagecast. Both are pruned after 24h by the launcher at every
start and by the SessionEnd hook. Captures no skill owns go to <ISOLATE_DIR>/visual/adhoc/<slug>/
and are pruned after 30 days. Anything else in a per-repo dir (12-hex keys) is out of bounds,
whatever its age.
"""
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SSOT_PY = PLUGIN / "scripts" / "lib" / "browser_mcp_servers.py"
SESSION_END = PLUGIN / "hooks" / "session-end-gc.sh"
LAUNCHER = PLUGIN / "scripts" / "mcp" / "browser_mcp_launch.py"

spec = importlib.util.spec_from_file_location("browser_mcp_servers_gc", SSOT_PY)
ssot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ssot)

DAY = 24 * 3600


def _touch(path: Path, age_s: float, text="x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    t = time.time() - age_s
    os.utime(path, (t, t))
    return path


def _age_dir(path: Path, age_s: float):
    t = time.time() - age_s
    os.utime(path, (t, t))


def test_old_playwright_files_at_the_projects_top_level_are_deleted(tmp_path):
    projects = tmp_path / "projects"
    old = [_touch(projects / n, 2 * DAY) for n in (
        "console-2026-01-01T00-00-00.log", "page-2026-01-01T00-00-00-000Z.png",
        "element-2026.png", "network-1.log", "download-report.pdf", "storage-state-1.json")]
    removed = ssot.prune_browser_byproducts(str(tmp_path))
    assert removed >= len(old)
    assert not any(p.exists() for p in old)


def test_fresh_playwright_files_are_kept(tmp_path):
    fresh = _touch(tmp_path / "projects" / "page-now.png", 60)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert fresh.exists()


def test_per_repo_state_dirs_are_never_touched_whatever_their_age(tmp_path):
    repo = tmp_path / "projects" / "0123456789ab"
    kept = [_touch(repo / "worktrees" / "ba9876543210" / "visual" / "page-1.png", 90 * DAY),
            _touch(repo / "console-x.log", 90 * DAY)]
    _age_dir(repo, 90 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert all(p.exists() for p in kept)


def test_unrecognised_names_at_the_projects_top_level_are_kept(tmp_path):
    other = _touch(tmp_path / "projects" / "notes.md", 90 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert other.exists()


def test_old_trace_and_session_trees_are_emptied_and_removed(tmp_path):
    projects = tmp_path / "projects"
    trace = _touch(projects / "traces" / "trace-1.zip", 3 * DAY)
    sess = _touch(projects / "session-1700000000" / "a" / "b.log", 3 * DAY)
    for d in (projects / "session-1700000000" / "a", projects / "session-1700000000",
              projects / "traces"):
        _age_dir(d, 3 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert not trace.exists() and not sess.exists()
    assert not (projects / "session-1700000000").exists()


def test_pagecast_scratch_recordings_are_pruned_by_age(tmp_path):
    scratch = tmp_path / "scratch" / "pagecast"
    old = _touch(scratch / "recording-abc.webm", 2 * DAY)
    fresh = _touch(scratch / "recording-def.webm", 60)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert not old.exists() and fresh.exists()


def test_a_symlink_is_removed_itself_never_followed(tmp_path):
    target = _touch(tmp_path / "keep" / "precious.png", 90 * DAY)
    link = tmp_path / "projects" / "page-link.png"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    t = time.time() - 2 * DAY
    os.utime(link, (t, t), follow_symlinks=False)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert target.exists()
    assert not os.path.lexists(link)


def test_a_missing_state_root_is_not_an_error(tmp_path):
    assert ssot.prune_browser_byproducts(str(tmp_path / "absent")) == 0


def test_the_cli_prunes_the_resolved_state_root(tmp_path):
    old = _touch(tmp_path / "projects" / "console-1.log", 2 * DAY)
    env = dict(os.environ, ODOO_AI_HOME=str(tmp_path))
    proc = subprocess.run([sys.executable, str(SSOT_PY), "prune"], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0 and proc.stdout == ""
    assert not old.exists()


def test_both_runtime_callers_invoke_the_prune():
    """A correct mechanism nothing calls is this plugin's dominant defect."""
    assert "prune_browser_byproducts(" in LAUNCHER.read_text(encoding="utf-8")
    assert "browser_mcp_servers.py\" prune" in SESSION_END.read_text(encoding="utf-8")


ISOLATE = Path("projects") / "0123456789ab" / "worktrees" / "ba9876543210"


def test_adhoc_captures_older_than_30_days_are_pruned_and_younger_ones_kept(tmp_path):
    adhoc = tmp_path / ISOLATE / "visual" / "adhoc"
    old = _touch(adhoc / "login-glitch" / "a.png", 31 * DAY)
    _age_dir(adhoc / "login-glitch", 31 * DAY)
    young = _touch(adhoc / "kanban" / "b.png", 20 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert not old.exists() and not (adhoc / "login-glitch").exists()
    assert young.exists()
    assert adhoc.is_dir(), "the adhoc dir itself stays"


def test_other_visual_owners_are_never_pruned(tmp_path):
    owned = _touch(tmp_path / ISOLATE / "visual" / "odoo-doc-illustration" / "run" / "a.png",
                   400 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path))
    assert owned.exists()


def test_the_worktree_override_adhoc_dir_is_pruned_too(tmp_path):
    override = tmp_path / "custom-isolate"
    old = _touch(override / "visual" / "adhoc" / "x" / "a.png", 31 * DAY)
    ssot.prune_browser_byproducts(str(tmp_path / "state"),
                                  environ={"ODOO_AI_WORKTREE_DIR": str(override) + "/"})
    assert not old.exists()
