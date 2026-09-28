"""Behavior tests for the odoo-local read-only tools (catalog_read, catalog_locate, series_detect,
project_dir) driven through the REAL server over stdio, plus the persisted background-job store.

Every case builds throwaway fixtures under tmp_path with ODOO_AI_HOME pinned there - never this
machine's real catalog or state dir (this repo is public and must pass on any host).

The expected values are stated from the documented contracts (resolve_instances.sh ladder,
instances_io locate rule, odoo_series ordered derivation, paths.py axes), and where a CLI already
answers the same question the tool is compared against that CLI - the parity is the contract.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from odoo_local_mcp_harness import LIB_DIR, MCP_DIR, McpClient, hermetic_env, import_package, structured

import_package()
from odoo_local import cli, jobs  # noqa: E402

CATALOG = textwrap.dedent("""\
    [[instance]]
    series = "16.0"
    addons_path = ["/src/odoo16/addons", "/src/custom16"]
    http_port = 8169
    db_name = "odoo_16"

    [[instance]]
    series = "17.0"
    profile = "minimal_17"
    addons_path = ["/src/odoo17/addons", "/src/custom17"]
    http_port = 8269
    python = "/venvs/17/bin/python"

    [[instance]]
    series = "17.0"
    addons_path = "/src/odoo17b/addons,/src/custom17/nested"
    """)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def work(tmp_path):
    w = tmp_path / "work"
    w.mkdir()
    return w


def _server(home, work, **env):
    client = McpClient(hermetic_env(home, **env), work)
    client.initialize()
    return client


def _ok(result):
    assert result["isError"] is False, result
    return structured(result)


def _err(result):
    assert result["isError"] is True, result
    return structured(result)["error"]


# --------------------------------------------------------------------------- #
# catalog_read
# --------------------------------------------------------------------------- #
def test_catalog_read_returns_every_row_from_the_global_catalog(home, work):
    path = _write(home / "instances.toml", CATALOG)
    with _server(home, work) as s:
        out = _ok(s.call("catalog_read", {}))
    assert out["catalog_path"] == str(path) and out["catalog_exists"] is True
    assert [r["instance_key"] for r in out["rows"]] == ["16.0", "17.0:minimal_17", "17.0"]
    first = out["rows"][0]
    assert first["addons_path"] == ["/src/odoo16/addons", "/src/custom16"]
    assert first["http_port"] == 8169 and first["db_name"] == "odoo_16"
    # An optional field the catalog does not declare is ABSENT, never defaulted.
    assert "python" not in first and "db_host" not in first and "db_port" not in first


def test_catalog_read_normalizes_a_flattened_addons_path_string(home, work):
    _write(home / "instances.toml", CATALOG)
    with _server(home, work) as s:
        rows = _ok(s.call("catalog_read", {"series": "17.0", "profile": ""}))["rows"]
    assert len(rows) == 1
    assert rows[0]["addons_path"] == ["/src/odoo17b/addons", "/src/custom17/nested"]


@pytest.mark.parametrize("args,keys", [
    ({"series": "17.0"}, ["17.0:minimal_17", "17.0"]),
    ({"series": "17.0", "profile": "minimal_17"}, ["17.0:minimal_17"]),
    ({"profile": "minimal_17"}, ["17.0:minimal_17"]),
    ({"series": "15.0"}, []),
])
def test_catalog_read_filters_are_exact_and_never_pick_for_you(home, work, args, keys):
    _write(home / "instances.toml", CATALOG)
    with _server(home, work) as s:
        rows = _ok(s.call("catalog_read", args))["rows"]
    assert [r["instance_key"] for r in rows] == keys


def test_explicit_instances_override_wins_over_global(home, work, tmp_path):
    _write(home / "instances.toml", CATALOG)
    override = _write(tmp_path / "elsewhere" / "cat.toml", '[[instance]]\nseries = "18.0"\naddons_path = ["/x"]\n')
    with _server(home, work, ODOO_AI_INSTANCES=override) as s:
        out = _ok(s.call("catalog_read", {}))
    assert out["catalog_path"] == str(override)
    assert [r["series"] for r in out["rows"]] == ["18.0"]


def test_project_catalog_is_the_fallback_only_when_global_declares_nothing(home, work):
    project = _write(work / ".odoo-ai" / "instances.toml", '[[instance]]\nseries = "15.0"\naddons_path = ["/p"]\n')
    with _server(home, work) as s:
        by_default_cwd = _ok(s.call("catalog_read", {}))
        by_explicit_cwd = _ok(s.call("catalog_read", {"cwd": str(work)}))
        _write(home / "instances.toml", CATALOG)
        after_global = _ok(s.call("catalog_read", {"cwd": str(work)}))
    assert by_default_cwd["catalog_path"] == str(project)
    assert by_explicit_cwd["catalog_path"] == str(project)
    assert after_global["catalog_path"] == str(home / "instances.toml")


def test_catalog_path_matches_resolve_instances_script(home, work):
    _write(work / ".odoo-ai" / "instances.toml", '[[instance]]\nseries = "15.0"\n')
    script = subprocess.run(["bash", str(LIB_DIR / "resolve_instances.sh"), "--path"], cwd=str(work),
                            env=hermetic_env(home, PWD=work), capture_output=True, text=True, check=True)
    with _server(home, work) as s:
        out = _ok(s.call("catalog_read", {"cwd": str(work)}))
    assert out["catalog_path"] == script.stdout.strip()


def test_missing_catalog_is_an_empty_result_not_an_error(home, work):
    with _server(home, work) as s:
        out = _ok(s.call("catalog_read", {}))
    assert out == {"catalog_path": str(home / "instances.toml"), "catalog_exists": False, "rows": []}


def test_malformed_catalog_is_a_named_error(home, work, tmp_path):
    bad = _write(tmp_path / "bad.toml", "[[instance]\nseries = \n")
    with _server(home, work, ODOO_AI_INSTANCES=bad) as s:
        err = _err(s.call("catalog_read", {}))
    assert err["code"] == "CATALOG_UNREADABLE" and str(bad) in err["message"]
    assert err["remedy"]


# --------------------------------------------------------------------------- #
# catalog_locate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("repo,key", [
    ("/src/custom17", "17.0:minimal_17"),            # equal to an entry
    ("/src/custom17/nested/mod", "17.0"),             # longest matching entry wins
    ("/src/custom16/sub/dir", "16.0"),                # descendant of an entry
])
def test_catalog_locate_maps_a_repo_to_its_covering_instance(home, work, repo, key):
    _write(home / "instances.toml", CATALOG)
    with _server(home, work) as s:
        out = _ok(s.call("catalog_locate", {"path": repo}))
    assert out["matched"] is True and out["row"]["instance_key"] == key


@pytest.mark.parametrize("repo", ["/src", "/elsewhere/repo", "/src/custom1"])
def test_catalog_locate_miss_is_a_normal_result(home, work, repo):
    # "/src" CONTAINS entries but is not covered BY one; "/src/custom1" is a string prefix only.
    _write(home / "instances.toml", CATALOG)
    with _server(home, work) as s:
        out = _ok(s.call("catalog_locate", {"path": repo}))
    assert out["matched"] is False and out["row"] is None


def test_catalog_locate_agrees_with_instances_io_cli(home, work):
    cat = _write(home / "instances.toml", CATALOG)
    cli_out = subprocess.run([sys.executable, str(LIB_DIR / "instances_io.py"), "locate", str(cat), "/src/custom17/nested/x"],
                             capture_output=True, text=True, check=True).stdout
    with _server(home, work) as s:
        row = _ok(s.call("catalog_locate", {"path": "/src/custom17/nested/x"}))["row"]
    assert "INST_SERIES=17.0" in cli_out and "INST_PROFILE=''" in cli_out
    assert row["series"] == "17.0" and row["profile"] == ""


# --------------------------------------------------------------------------- #
# series_detect
# --------------------------------------------------------------------------- #
def _odoo_root(tmp_path, pkg, release_text, manifest_name):
    root = tmp_path / "checkout"
    _write(root / pkg / "release.py", release_text)
    _write(root / "addons" / "base" / manifest_name, "{'name': 'Base', 'version': '1.3'}\n")
    return root


def test_series_detect_resolves_from_core_release_py(home, work, tmp_path):
    root = _odoo_root(tmp_path, "odoo", "version_info = (17, 0, 0, FINAL, 0, '')\n", "__manifest__.py")
    with _server(home, work) as s:
        out = _ok(s.call("series_detect", {"path": str(root)}))
    assert out["status"] == "OK" and out["series"] == "17.0" and out["step"] == "1"
    assert out["evidence"] == str(root / "odoo" / "release.py")


def test_series_detect_never_guesses_from_an_era_only_tree(home, work, tmp_path):
    root = tmp_path / "addons_only"
    _write(root / "my_mod" / "__openerp__.py", "{'name': 'M', 'version': '1.0'}\n")
    with _server(home, work) as s:
        out = _ok(s.call("series_detect", {"path": str(root)}))
    assert out["status"] == "NEEDS_CONTEXT" and out["series"] == ""
    assert out["step"] == "4" and out["era"] == "8.0-9.0"


def test_series_detect_matches_the_odoo_series_cli(home, work, tmp_path):
    root = _odoo_root(tmp_path, "openerp", "version_info = (9, 0, 0, 'final', 0)\n", "__openerp__.py")
    proc = subprocess.run([sys.executable, str(LIB_DIR / "odoo_series.py"), "detect", str(root)],
                          capture_output=True, text=True)
    lines = dict(line.split("=", 1) for line in proc.stdout.splitlines())
    with _server(home, work) as s:
        out = _ok(s.call("series_detect", {"path": str(root)}))
    assert out["series"] == lines["SERIES"].strip("'") == "9.0"
    assert out["status"] == lines["SERIES_STATUS"] == "OK"


def test_series_detect_on_a_missing_dir_is_a_named_error(home, work, tmp_path):
    with _server(home, work) as s:
        err = _err(s.call("series_detect", {"path": str(tmp_path / "nope")}))
    assert err["code"] == "PATH_NOT_DIRECTORY"


# --------------------------------------------------------------------------- #
# project_dir
# --------------------------------------------------------------------------- #
def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


@pytest.mark.parametrize("axis", ["share", "isolate"])
def test_project_dir_matches_paths_py_cli(home, work, tmp_path, axis):
    repo = _git_repo(tmp_path / "repo")
    expected = subprocess.run([sys.executable, str(LIB_DIR / "paths.py"), "--root", str(repo), axis],
                              env=hermetic_env(home), capture_output=True, text=True, check=True).stdout.strip()
    with _server(home, work) as s:
        out = _ok(s.call("project_dir", {"cwd": str(repo), "axis": axis}))
    assert out["path"] == expected and out["axis"] == axis
    assert out["path"].startswith(str(home / "projects") + os.sep)
    assert os.path.isdir(out["path"])


def test_isolate_nests_under_share_and_differs_from_it(home, work, tmp_path):
    repo = _git_repo(tmp_path / "repo")
    with _server(home, work) as s:
        share = _ok(s.call("project_dir", {"cwd": str(repo), "axis": "share"}))["path"]
        isolate = _ok(s.call("project_dir", {"cwd": str(repo), "axis": "isolate"}))["path"]
    assert isolate.startswith(share + os.sep + "worktrees" + os.sep)


def test_project_dir_honors_the_explicit_override(home, work, tmp_path):
    repo = _git_repo(tmp_path / "repo")
    forced = tmp_path / "forced"
    with _server(home, work, ODOO_AI_PROJECT_DIR=forced) as s:
        out = _ok(s.call("project_dir", {"cwd": str(repo), "axis": "share"}))
    assert out["path"] == str(forced)


def test_project_dir_without_git_or_marker_is_unresolved(home, work, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    env = {"GIT_CEILING_DIRECTORIES": str(tmp_path)}
    if any((p / ".odoo-ai-root").exists() or (p / "__manifest__.py").exists() or (p / "__openerp__.py").exists()
           for p in [bare, *bare.parents]):
        pytest.skip("an ancestor of tmp_path carries a project marker on this host")
    with _server(home, work, **env) as s:
        err = _err(s.call("project_dir", {"cwd": str(bare), "axis": "share"}))
    assert err["code"] == "PROJECT_DIR_UNRESOLVED"


# --------------------------------------------------------------------------- #
# jobs: persisted, restart-proof background processes
# --------------------------------------------------------------------------- #
def _in_fresh_process(home: Path, code: str) -> dict:
    """Run `code` in a NEW interpreter (a server restart, as far as the job store can tell) and
    return the JSON it prints."""
    prelude = "import json, sys; sys.path.insert(0, %r)\nfrom odoo_local import jobs\n" % str(MCP_DIR)
    proc = subprocess.run([sys.executable, "-c", prelude + code], env=hermetic_env(home),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_job_survives_a_server_restart_and_then_completes(home, work):
    rec = _in_fresh_process(home, "print(json.dumps(jobs.start(['sh', '-c', 'echo hello; sleep 2; exit 3'], %r)))" % str(work))
    assert rec["pid"] > 0 and rec["job_id"] and Path(rec["log_path"]).parent == home / "runtime" / "jobs"
    # The process that started it is gone; a new one reads the record and proves liveness.
    running = _in_fresh_process(home, "print(json.dumps(jobs.status(%r)))" % rec["job_id"])
    assert running["state"] == "running" and running["exit_code"] is None
    assert running["fingerprint_verified"] is bool(rec["pid_started"])
    done = _in_fresh_process(home, "print(json.dumps(jobs.wait(%r, 30)))" % rec["job_id"])
    assert done["state"] == "exited" and done["exit_code"] == 3 and done["timed_out"] is False
    assert "hello" in Path(rec["log_path"]).read_text()


def test_job_wait_times_out_while_still_running(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    rec = jobs.start(["sleep", "5"], work)
    try:
        st = jobs.wait(rec["job_id"], 0.5)
        assert st["state"] == "running" and st["timed_out"] is True
    finally:
        os.killpg(rec["pid"], signal.SIGKILL)


def test_killed_job_is_reported_lost_not_running(home, work):
    rec = _in_fresh_process(home, "print(json.dumps(jobs.start(['sleep', '30'], %r)))" % str(work))
    os.killpg(rec["pid"], signal.SIGKILL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        st = _in_fresh_process(home, "print(json.dumps(jobs.status(%r)))" % rec["job_id"])
        if st["state"] != "running":
            break
        time.sleep(0.2)
    assert st["state"] == "lost" and st["exit_code"] is None


def test_recycled_pid_is_reported_lost_not_running(home, monkeypatch):
    # A record whose pid is alive but held by a DIFFERENT process (same boot, other start time)
    # must never read as the job still running - that is the pid-recycling trap.
    import importlib.util
    spec = importlib.util.spec_from_file_location("sa_jobs", LIB_DIR / "session_anchor.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    live_fp = sa.fingerprint(os.getpid())
    if not (live_fp and live_fp.startswith(sa.SCHEME_PROC)):
        pytest.skip("needs the /proc fingerprint scheme to forge a same-boot mismatch")
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    forged = live_fp.rsplit(":", 1)[0] + ":1"
    record = {"job_id": "job-recycled", "pid": os.getpid(), "pid_started": forged, "log_path": "/dev/null",
              "started_at": "2000-01-01T00:00:00Z", "cmd": ["x"], "cwd": "/", "anchor": {}}
    Path(jobs.jobs_dir(), "job-recycled.json").write_text(json.dumps(record))
    st = jobs.status("job-recycled")
    assert st["state"] == "lost" and "different process" in st["detail"]


def test_job_records_the_session_anchor_and_env(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    monkeypatch.delenv("ODOO_AI_SESSION_ANCHOR", raising=False)
    rec = jobs.start([sys.executable, "-c", "import os; print('VIA=' + os.environ['ODOO_AI_VIA'] + ' X=' + os.environ['X'])"],
                     work, env={"X": "1"})
    st = jobs.wait(rec["job_id"], 30)
    assert st["exit_code"] == 0
    assert "VIA=mcp X=1" in Path(rec["log_path"]).read_text()
    assert rec["anchor"] == cli.anchor().as_dict()


def test_log_path_hint_is_honored(home, work, tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    hint = tmp_path / "logs" / "build.log"
    rec = jobs.start(["echo", "hinted"], work, log_path_hint=str(hint))
    jobs.wait(rec["job_id"], 30)
    assert rec["log_path"] == str(hint) and "hinted" in hint.read_text()


@pytest.mark.parametrize("job_id", ["job-nope", "../../etc/passwd", "", None])
def test_unknown_or_malformed_job_id_has_no_status(home, monkeypatch, job_id):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    assert jobs.status(job_id) is None and jobs.wait(job_id, 0) is None


@pytest.mark.parametrize("value", ["{home}", "{home}/", "{home}///"])
def test_jobs_dir_sits_under_the_allocator_runtime_root(home, monkeypatch, value):
    import importlib.util
    monkeypatch.setenv("ODOO_AI_HOME", value.format(home=home))
    spec = importlib.util.spec_from_file_location("allocator_home_parity", LIB_DIR / "allocator.py")
    allocator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(allocator)
    assert jobs.jobs_dir() == os.path.join(allocator._home(), "runtime", "jobs")


# --------------------------------------------------------------------------- #
# jobs: finished records are pruned on the SAME retention bound as build logs
# --------------------------------------------------------------------------- #
DAY_S = 86400


def _retention_days_from_bash() -> int:
    """The bound as the build-log sweeper itself sees it - read by SOURCING its lib in bash, an
    oracle independent of however jobs.py reads it."""
    out = subprocess.run(["bash", "-c", 'source "$1" && printf %s "$_LOG_RETENTION_DAYS"', "_",
                          str(LIB_DIR / "state_reclaim.sh")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout.strip().isdigit(), out.stderr
    return int(out.stdout.strip())


def _age(paths, days: float):
    t = time.time() - days * DAY_S
    for p in paths:
        if Path(p).exists():
            os.utime(p, (t, t))


def _job_files(job_id: str) -> list[Path]:
    d = Path(jobs.jobs_dir())
    return [d / (job_id + ext) for ext in (".json", ".rc", ".log")]


def _finished_job(work, days: float, **kw) -> dict:
    rec = jobs.start(["true"], work, **kw)
    st = jobs.wait(rec["job_id"], 30)
    assert st["state"] == "exited", st
    _age(_job_files(rec["job_id"]) + [rec["log_path"]], days)
    return rec


def _forged_record(job_id: str, pid: int, days: float) -> Path:
    path = Path(jobs.jobs_dir(), job_id + ".json")
    path.write_text(json.dumps({"job_id": job_id, "pid": pid, "pid_started": "", "log_path": "/dev/null",
                                "started_at": "2000-01-01T00:00:00Z", "cmd": ["x"], "cwd": "/", "anchor": {}}))
    _age([path], days)
    return path


def test_a_finished_job_older_than_the_log_retention_is_pruned_with_its_rc_and_log(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    rec = _finished_job(work, _retention_days_from_bash() + 2)
    pruned = jobs.prune_finished()
    assert rec["job_id"] in pruned
    assert [p for p in _job_files(rec["job_id"]) if p.exists()] == [], (
        "a pruned job must leave neither its record, its .rc nor its default log behind")
    assert jobs.status(rec["job_id"]) is None


def test_a_finished_job_inside_the_retention_window_is_kept(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    rec = _finished_job(work, max(_retention_days_from_bash() - 1, 0))
    assert jobs.prune_finished() == []
    assert jobs.status(rec["job_id"])["state"] == "exited", "a job inside the window stays queryable"


def test_a_lost_job_older_than_the_retention_is_pruned(home, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    dead = subprocess.Popen(["true"])
    dead.wait()
    _forged_record("job-lost-old", dead.pid, _retention_days_from_bash() + 2)
    assert jobs.status("job-lost-old")["state"] == "lost"
    assert jobs.prune_finished() == ["job-lost-old"]
    assert jobs.read_record("job-lost-old") is None


def test_a_running_job_is_never_pruned_however_old_its_files_are(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    rec = jobs.start(["sleep", "30"], work)
    try:
        _age(_job_files(rec["job_id"]), _retention_days_from_bash() + 30)
        assert jobs.prune_finished() == []
        assert jobs.status(rec["job_id"])["state"] == "running"
    finally:
        os.killpg(rec["pid"], signal.SIGKILL)


def test_a_hinted_log_outside_the_jobs_dir_is_left_to_the_log_sweeper(home, work, tmp_path, monkeypatch):
    """A build job's log lives in the logs dir, which the lease-guarded log sweeper owns; the job
    prune removes only what the job store itself created."""
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    hint = tmp_path / "logs" / "odoo_17_t_x-20000101T000000Z.ops.log"
    rec = _finished_job(work, _retention_days_from_bash() + 2, log_path_hint=str(hint))
    assert rec["job_id"] in jobs.prune_finished()
    assert hint.exists(), "the job prune must never unlink a log it did not place in its own dir"


def test_an_unreadable_retention_bound_prunes_nothing(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    rec = _finished_job(work, 10000)
    monkeypatch.setattr(jobs, "RETENTION_SOURCE", Path(home) / "no-such-state_reclaim.sh")
    assert jobs.prune_finished() == []
    assert jobs.read_record(rec["job_id"]) is not None, "no bound means nothing is provably old enough"


def test_starting_a_job_prunes_old_finished_ones(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    old = _finished_job(work, _retention_days_from_bash() + 2)
    new = jobs.start(["true"], work)
    jobs.wait(new["job_id"], 30)
    assert jobs.read_record(old["job_id"]) is None, "job start must prune the job store opportunistically"
    assert jobs.read_record(new["job_id"]) is not None


def test_server_start_prunes_old_finished_jobs(home, work, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    old = _finished_job(work, _retention_days_from_bash() + 2)
    with _server(home, work):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and jobs.read_record(old["job_id"]) is not None:
            time.sleep(0.1)
    assert jobs.read_record(old["job_id"]) is None, "server start must prune the job store"
