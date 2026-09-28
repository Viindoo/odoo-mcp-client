"""Behavior tests for the odoo-local instance tools (instance_build / job_wait / instance_serve /
instance_status), driven over stdio against the REAL server, the REAL allocator and the REAL
setup-step scripts (55-instance-ops.sh, 50-instance-spinup.sh).

Nothing Odoo-shaped is real: odoo-bin, the venv python, curl and pg_isready are stubs, so the
tests need no Postgres, no Odoo and no network. What IS real is everything the tools are
responsible for: that connection facts come from the lease row, that a build runs detached and
is judged by its exit code plus the script's own marker reading, that a job outlives the server,
and that serving binds the launched server onto the lease.

ODOO_AI_OPS_SCRIPT (the test-only override of the 55 script path) is used only where a stand-in
is the point: recording the exact argv the tool hands the script.
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

from odoo_local_mcp_harness import LIB_DIR, PLUGIN, McpClient, hermetic_env, structured

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odoo_tree_fixtures as trees  # noqa: E402

SERIES = "17.0"
RUN = "run-instance-owner"
STEP50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"


def _load_lib(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location("inst_test_" + name, LIB_DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


session_anchor = _load_lib("session_anchor")


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(0); count it as gone.
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


# --------------------------------------------------------------------------- #
# the stubbed world
# --------------------------------------------------------------------------- #
@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    core = tmp_path / "core"
    addons = core / "addons"
    addons.mkdir(parents=True)
    # The Odoo checkout the tools read option facts from (demo default, port options, short
    # options): a fixture of SERIES where the stub odoo-bin lives, as in a real checkout.
    trees.write_checkout(core, SERIES, with_addons=False)
    # odoo-bin delegates to a behavior file each test writes, so one server serves many scenarios.
    behavior = tmp_path / "odoo-behavior.sh"
    behavior.write_text('echo "odoo.modules.loading: Modules loaded."\nexit 0\n', encoding="utf-8")
    calls = tmp_path / "odoo-bin-calls.log"
    # A `-c <conf>` launch WITHOUT --stop-after-init is the LISTENING server
    # 50-instance-spinup.sh starts: it stays up. Builds and exports carry -c too (a generated conf,
    # so the operator's ~/.odoorc is never read) but always stop after init; the conf each one was
    # handed is appended to run-confs.log.
    confs = tmp_path / "run-confs.log"
    rc_env = tmp_path / "run-rc-env.log"  # ODOO_RC|OPENERP_SERVER each such launch saw
    odoo_bin = _stub(core / "odoo-bin", textwrap.dedent("""\
        echo "odoo-bin $*" >> "%s"
        conf=""; prev=""; stop=""
        for a in "$@"; do
            [[ "$prev" == "-c" ]] && conf="$a"
            [[ "$a" == "--stop-after-init" ]] && stop=1
            prev="$a"
        done
        if [[ -n "$conf" && -z "$stop" ]]; then exec sleep 300; fi
        if [[ -n "$conf" ]]; then
            { echo "== $conf"; cat "$conf"; } >> "%s"
            echo "${ODOO_RC-<unset>}|${OPENERP_SERVER-<unset>}" >> "%s"
        fi
        exec bash "%s" "$@"
        """ % (calls, confs, rc_env, behavior)))

    fake_py_dir = tmp_path / "venv" / "bin"
    fake_py_dir.mkdir(parents=True)
    fake_py = _stub(fake_py_dir / "python", textwrap.dedent("""\
        if [[ "${2:-}" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        case "${1:-}" in
            *odoo_db.py) exit 0 ;;
            %(bin)s) shift; exec bash "%(bin)s" "$@" ;;
        esac
        exec %(real)s "$@"
        """ % {"bin": odoo_bin, "real": sys.executable}))

    port_base = 38300 + (os.getpid() % 50) * 10
    (home / "instances.toml").write_text(
        "[[instance]]\n"
        f'series = "{SERIES}"\n'
        f'python = "{fake_py}"\n'
        f"http_port = {port_base - 1}\n"
        f"http_port_base = {port_base}\n"
        'db_name = "insttest"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        'run_mode = "source"\n'
        f'addons_path = ["{addons}"]\n',
        encoding="utf-8",
    )

    bindir = tmp_path / "stub-bin"
    bindir.mkdir()
    curl_mode = tmp_path / "curl-mode"
    # curl-mode: "boot" = 000 on the first probe (nothing listening yet), 200 after; or a fixed code.
    curl_mode.write_text("boot", encoding="utf-8")
    curl_count = tmp_path / "curl-count"
    _stub(bindir / "curl", textwrap.dedent("""\
        mode="$(cat "%(mode)s")"
        if [[ "$mode" != "boot" ]]; then echo "$mode"; exit 0; fi
        n="$(cat "%(count)s" 2>/dev/null || echo 0)"; echo $((n + 1)) > "%(count)s"
        if [[ "$n" -ge 1 ]]; then echo 200; else echo 000; fi
        """ % {"mode": curl_mode, "count": curl_count}))
    _stub(bindir / "pg_isready", "exit 0\n")

    anchor_proc = subprocess.Popen(["sleep", "900"])
    anchor = session_anchor.format_anchor(anchor_proc.pid, session_anchor.fingerprint(anchor_proc.pid))

    def env(**extra):
        return hermetic_env(home, ODOO_AI_SESSION_ANCHOR=anchor, CLAUDE_CODE_SESSION_ID="sess-inst",
                            ODOO_BIN=str(odoo_bin), PATH="%s:%s" % (bindir, os.environ.get("PATH", "")),
                            SPINUP_TIMEOUT="10", **extra)

    w = {"home": home, "work": tmp_path, "addons": addons, "behavior": behavior, "calls": calls,
         "confs": confs, "rc_env": rc_env,
         "odoo_bin": odoo_bin, "python": fake_py, "curl_mode": curl_mode, "env": env,
         "port_base": port_base}
    yield w
    # Reap every server a test launched (recorded on its lease), then the anchor.
    reg = home / "runtime" / "leases.json"
    if reg.is_file():
        for lease in json.loads(reg.read_text()).get("leases", []):
            pid = (lease.get("owner") or {}).get("pid")
            if isinstance(pid, int) and pid > 1:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass
    anchor_proc.kill()
    anchor_proc.wait()


@pytest.fixture
def client(world):
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        yield c


def _ok(result):
    assert result["isError"] is False, result["structuredContent"]
    return structured(result)


def _err(result):
    assert result["isError"] is True, result["structuredContent"]
    return structured(result)["error"]


def _lease(c, world, **over):
    args = {"series": SERIES, "run_id": RUN, "cwd": str(world["work"]), "no_create": True}
    args.update(over)
    return _ok(c.call("lease_acquire", args))["lease"]


def _build(c, world, token, **over):
    """instance_build with demo off by default for op init, which requires it (op test takes no
    demo: the series default applies); pass demo=None to omit it."""
    args = {"lease_token": token, "op": "init", "modules": ["my_mod"], "cwd": str(world["work"])}
    args.update(over)
    if args["op"] == "init":
        args.setdefault("demo", "off")
    if args.get("demo") is None:
        args.pop("demo", None)
    return c.call("instance_build", args)


def _wait(c, job_id, timeout_s=60):
    return _ok(c.call("job_wait", {"job_id": job_id, "timeout_s": timeout_s}, timeout=timeout_s + 30))


def _registry(world):
    return json.loads((world["home"] / "runtime" / "leases.json").read_text())["leases"]


# --------------------------------------------------------------------------- #
# instance_build + job_wait
# --------------------------------------------------------------------------- #
def test_build_runs_against_the_leases_coordinates_and_succeeds(client, world):
    lease = _lease(client, world)
    started = time.monotonic()
    job = _ok(_build(client, world, lease["token"], extra_args=["--log-level=debug"]))
    assert time.monotonic() - started < 15, "instance_build must return before the build finishes"
    assert "instance_handle" not in job, (
        "a handle read at the start states the database BEFORE the build changed it")
    done = _wait(client, job["job_id"])
    assert done["result"] == "success", done
    assert done["instance_handle"]["log_path"] == job["log_path"]
    assert done["exit_code"] == 0 and done["state"] == "exited"
    assert "Modules loaded." in done["marker"]
    assert done["summary"].get("STATUS") == "ok"
    # The log the tool named is the log the script wrote (its run-verb stamp is the first line).
    assert Path(done["log_path"]).read_text().splitlines()[0].startswith("ODOO_AI_RUN_VERB=init SERIES=17.0")
    argv = world["calls"].read_text()
    assert "-d %s" % lease["db_name"] in argv and "-i my_mod" in argv
    assert "--addons-path %s" % world["addons"] in argv
    assert "--log-level=debug" in argv
    assert "--without-demo=True" in argv, "demo off on 17.0 is spelled --without-demo=True by the tool"


def test_build_that_silently_skips_a_module_is_a_failure(client, world):
    world["behavior"].write_text(
        'echo "odoo.modules.loading: invalid module names, ignored: my_mod"\n'
        'echo "odoo.modules.loading: Modules loaded."\nexit 0\n', encoding="utf-8")
    lease = _lease(client, world)
    done = _wait(client, _ok(_build(client, world, lease["token"]))["job_id"])
    assert done["result"] == "failure", done
    assert done["exit_code"] != 0


def test_failing_test_run_reports_failure_and_the_test_verdict(client, world):
    world["behavior"].write_text(
        'echo "odoo.modules.loading: Modules loaded."\n'
        'echo "odoo.tests.result: 1 failed, 0 error(s) of 3 tests when loading database"\nexit 1\n',
        encoding="utf-8")
    lease = _lease(client, world, ports=1)
    job = _ok(_build(client, world, lease["token"], op="test", test_tags="/my_mod"))
    done = _wait(client, job["job_id"])
    assert done["result"] == "failure"
    assert done["test_result"] == "failed"
    assert done["summary"].get("TEST_TAGS_USED") == "/my_mod"
    assert "--test-tags /my_mod" in world["calls"].read_text()


def test_wait_times_out_while_running_then_reports_the_verdict(client, world):
    world["behavior"].write_text('sleep 4\necho "odoo.modules.loading: Modules loaded."\nexit 0\n',
                                 encoding="utf-8")
    lease = _lease(client, world)
    job_id = _ok(_build(client, world, lease["token"]))["job_id"]
    first = _wait(client, job_id, timeout_s=1)
    assert first["result"] == "timeout" and first["state"] == "running"
    assert _wait(client, job_id)["result"] == "success"


def test_job_survives_a_server_restart(world):
    world["behavior"].write_text('sleep 3\necho "odoo.modules.loading: Modules loaded."\nexit 0\n',
                                 encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as first:
        first.initialize()
        lease = _lease(first, world)
        job_id = _ok(_build(first, world, lease["token"]))["job_id"]
    # The first server is gone; a fresh one knows the job from its record on disk.
    with McpClient(world["env"](), world["work"]) as second:
        second.initialize()
        done = _wait(second, job_id)
        assert done["result"] == "success" and done["exit_code"] == 0


def test_release_stops_a_build_still_running_on_the_lease(client, world):
    world["behavior"].write_text("sleep 120\nexit 0\n", encoding="utf-8")
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"]))
    time.sleep(1)
    out = _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    assert [j["job_id"] for j in out["stopped_jobs"] if j["stopped"]] == [job["job_id"]]
    done = _wait(client, job["job_id"], timeout_s=5)
    assert done["result"] in ("lost", "failure"), done
    assert not _alive(job["pid"])


def test_build_argument_contract(client, world):
    lease = _lease(client, world)
    token = lease["token"]
    cases = [
        ({"test_tags": "/x"}, "arguments.test_tags"),
        ({"extra_args": ["--log-level debug"]}, "arguments.extra_args"),
        ({"modules": ["bad name"]}, "arguments.modules"),
        ({"modules": []}, "arguments.modules"),
    ]
    for over, needle in cases:
        err = _err(_build(client, world, token, **over))
        assert err["code"] == "INVALID_ARGUMENTS" and needle in err["message"], (over, err)
    assert _err(_build(client, world, "f" * 32))["code"] == "LEASE_NOT_FOUND"
    assert _err(client.call("job_wait", {"job_id": "job-unknown"}))["code"] == "JOB_NOT_FOUND"
    assert _err(client.call("job_wait", {"job_id": "x", "timeout_s": 541}))["code"] == "INVALID_ARGUMENTS"


def _ops_recorder(tmp_path):
    """A stand-in for 55-instance-ops.sh (via the test-only ODOO_AI_OPS_SCRIPT) that records the
    argv the tool hands it; returns (stand_in, record)."""
    record = tmp_path / "ops-argv.json"
    stand_in = _stub(tmp_path / "ops-stand-in.sh", textwrap.dedent("""\
        if [[ "$1" == "wait-log" ]]; then
            echo "BUILD_PROGRESS=markers:1|bytes:1"; echo "BUILD_MARKER=stand-in"; echo "BUILD_RESULT=success"; exit 0
        fi
        %s -c 'import json, os, sys; json.dump({"argv": sys.argv[1:], "log": os.environ.get("ODOO_AI_OPS_LOG_PATH")}, open("%s", "w"))' "$@"
        printf 'ODOO_AI_RUN_VERB=init SERIES=17.0\\n' > "$ODOO_AI_OPS_LOG_PATH"
        echo "STATUS=ok"
        """ % (sys.executable, record)))
    return stand_in, record


def test_build_hands_the_script_every_lease_fact_via_the_ops_script_override(world, tmp_path):
    """ODOO_AI_OPS_SCRIPT (test-only) replaces the 55 script with a recorder, so the exact argv the
    tool builds from the lease row - not from the agent - is observable."""
    stand_in, record = _ops_recorder(tmp_path)
    with McpClient(world["env"](ODOO_AI_OPS_SCRIPT=str(stand_in)), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", modules=["a", "b"], test_mode="reuse",
                         log_mode="debug", extra_args=["--log-level=warn", "--workers=0"]))
        done = _wait(c, job["job_id"])
    seen = json.loads(record.read_text())
    argv = seen["argv"]
    assert argv[0] == "test"
    pairs = dict(zip(argv[1::2], argv[2::2]))
    assert pairs["--db"] == lease["db_name"]
    assert pairs["--python"] == str(world["python"])
    assert pairs["--addons"] == str(world["addons"])
    assert pairs["--modules"] == "a,b"
    assert pairs["--version"] == SERIES
    assert pairs["--db-host"] == "localhost" and pairs["--db-user"] == "odoo"
    assert pairs["--mode"] == "reuse" and pairs["--log-mode"] == "debug"
    assert pairs["--extra"] == "--log-level=warn --workers=0"
    # A test build takes no demo argument: the tool hands the script the series default it read
    # from the lease's checkout (SERIES loads demo by default).
    assert pairs["--demo"] == "on" and pairs["--languages"] == "en_US"
    assert "--load" not in argv, "nothing declared server-wide and no readable core: no --load"
    assert "--db-port" not in argv, "an undeclared db_port is omitted, never invented"
    assert pairs["--http-port"] == str(lease["ports"][0]), "the build binds the lease's own port"
    assert seen["log"] == job["log_path"]
    assert done["result"] == "success"


# --------------------------------------------------------------------------- #
# a build binds the lease's port, with the flag its series spells
# --------------------------------------------------------------------------- #
def _odoo_bin_port_flags(world):
    """The (flag, value) pairs for listening ports in the recorded odoo-bin calls."""
    words = world["calls"].read_text().split()
    return [(w, words[i + 1]) for i, w in enumerate(words[:-1])
            if w in ("--http-port", "--xmlrpc-port", "--gevent-port", "--longpolling-port")]


def _declare_series(world, series, checkout=None):
    """Re-declare the stubbed world's single catalog row under another series, and make its core
    dir a checkout of `checkout` (default: the same series)."""
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text().replace('series = "%s"' % SERIES, 'series = "%s"' % series),
                    encoding="utf-8")
    trees.write_checkout(world["addons"].parent, checkout or series, with_addons=False)


@pytest.mark.parametrize("series,flag", [("17.0", "--http-port"), ("11.0", "--http-port"),
                                         ("10.0", "--xmlrpc-port"), ("8.0", "--xmlrpc-port")])
def test_a_test_build_binds_the_leases_port_with_its_series_flag(world, series, flag):
    """Odoo starts its HTTP server whenever test mode is on, even with --stop-after-init. A test
    build that does not pass the leased port binds the default 8069 and collides with whatever
    already listens there - so odoo-bin must receive the lease's port, spelled for the series."""
    _declare_series(world, series)
    world["behavior"].write_text(
        'echo "odoo.modules.loading: Modules loaded."\n'
        'echo "odoo.tests.result: 0 failed, 0 error(s) of 2 tests when loading database"\nexit 0\n',
        encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", test_tags="/my_mod"))
        _wait(c, job["job_id"])
    assert _odoo_bin_port_flags(world) == [(flag, str(lease["ports"][0]))]


def test_a_two_port_lease_builds_with_both_ports_under_their_series_flags(client, world):
    lease = _lease(client, world, ports=2)
    job = _ok(_build(client, world, lease["token"], op="test", test_tags="/my_mod"))
    _wait(client, job["job_id"])
    assert _odoo_bin_port_flags(world) == [("--http-port", str(lease["ports"][0])),
                                           ("--gevent-port", str(lease["ports"][1]))]


def test_an_install_on_a_lease_with_a_port_binds_that_port_and_without_one_binds_none(client, world):
    with_port = _lease(client, world, ports=1)
    assert _wait(client, _ok(_build(client, world, with_port["token"]))["job_id"])["result"] == "success"
    assert _odoo_bin_port_flags(world) == [("--http-port", str(with_port["ports"][0]))]
    world["calls"].write_text("", encoding="utf-8")
    no_port = _lease(client, world)
    assert _wait(client, _ok(_build(client, world, no_port["token"]))["job_id"])["result"] == "success"
    assert _odoo_bin_port_flags(world) == [], "a port-less install passes no port flag"


def test_a_test_build_on_a_lease_without_a_port_is_refused_by_name_before_anything_starts(client, world):
    lease = _lease(client, world)
    err = _err(_build(client, world, lease["token"], op="test", test_tags="/my_mod"))
    assert err["code"] == "LEASE_HAS_NO_PORT" and "ports 1" in err["remedy"]
    assert "instance_build" in err["remedy"]
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json"))
    assert not world["calls"].exists() or "--test-enable" not in world["calls"].read_text()


# --------------------------------------------------------------------------- #
# instance_serve / instance_status
# --------------------------------------------------------------------------- #
def test_serve_launches_the_leased_database_and_binds_its_server(client, world):
    lease = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"],
                                             "cwd": str(world["work"])}, timeout=120))
    port = lease["ports"][0]
    assert out["state"] == "launched" and out["resumed"] is False
    assert out["http_port"] == port and out["url"] == "http://localhost:%d" % port
    assert out["served_addons_path"] == [str(world["addons"])]
    pid = out["server_pid"]
    assert isinstance(pid, int) and _alive(pid)
    row = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
    assert row["owner"]["pid"] == pid, "the launched server is bound onto the lease"
    handle = out["instance_handle"]
    assert handle["server_pid"] == pid and handle["http_port"] == port
    assert handle["lease_token"] == lease["token"] and handle["db_name"] == lease["db_name"]
    # Releasing the lease stops that server.
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    deadline = time.monotonic() + 15
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(pid)


def test_serve_a_lease_without_a_port_is_refused_by_name(client, world):
    lease = _lease(client, world)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"]}))
    assert err["code"] == "LEASE_HAS_NO_PORT" and "ports 1" in err["remedy"]


def test_serve_needs_exactly_one_of_token_or_series(client, world):
    assert _err(client.call("instance_serve", {}))["code"] == "INVALID_ARGUMENTS"
    lease = _lease(client, world, ports=1)
    both = client.call("instance_serve", {"lease_token": lease["token"], "series": SERIES})
    assert _err(both)["code"] == "INVALID_ARGUMENTS"


def test_serve_by_series_registers_the_shared_render_lease(client, world):
    out = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                          timeout=120))
    assert out["shared_lease_error"] is None
    token = out["lease_token"]
    assert token and out["state"] == "launched"
    shared = [lz for lz in _registry(world) if lz["mode"] == "shared"]
    assert [lz["token"] for lz in shared] == [token]
    assert shared[0]["owner"]["run_id"] == RUN
    status = _ok(client.call("instance_status", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])}))
    assert status["up"] is True and status["shared_lease"]["token"] == token
    declared = world["port_base"] - 1
    assert status["http_port"] == declared and status["url"] == "http://localhost:%d" % declared
    # A reader resolves the render server's base URL from lease_find(shared) without its token.
    reader = _ok(client.call("lease_find", {"series": SERIES, "cwd": str(world["work"])}))["lease"]
    assert reader["token"] is None and reader["served"] is True
    assert reader["http_port"] == out["http_port"] and reader["url"] == out["url"]
    assert status["shared_lease"]["url"] == out["url"]


def test_status_of_a_series_with_nothing_running(client, world):
    world["curl_mode"].write_text("000", encoding="utf-8")
    out = _ok(client.call("instance_status", {"series": SERIES, "cwd": str(world["work"])}))
    assert out == {"series": SERIES, "up": False, "http_port": None, "url": None, "shared_lease": None,
                   "parked_lease": None}


def test_serve_failure_is_named_and_carries_the_scripts_reason(client, world):
    world["curl_mode"].write_text("000", encoding="utf-8")  # never becomes ready
    lease = _lease(client, world, ports=1)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "SERVE_FAILED"
    assert "did not become ready" in err["diagnostics"]["stderr"]


# --------------------------------------------------------------------------- #
# 50-instance-spinup.sh: a refused shared-lease registration is loud, not swallowed
# --------------------------------------------------------------------------- #
def test_spinup_reports_a_refused_shared_registration(world, tmp_path):
    refusing = _stub(tmp_path / "refusing-allocator.py", "")
    refusing.write_text("import sys\nsys.stderr.write('allocator: refused\\n')\nsys.exit(2)\n", encoding="utf-8")
    env = world["env"](ODOO_AI_ALLOCATOR=str(refusing))
    env["ODOO_AI_INSTANCES"] = str(world["home"] / "instances.toml")
    proc = subprocess.run(["bash", str(STEP50), "apply", "--version", SERIES], capture_output=True,
                          text=True, env=env, cwd=str(world["work"]), timeout=90)
    try:
        assert proc.returncode == 0, proc.stderr  # the server IS up; the spin-up itself succeeded
        facts = dict(ln.split("=", 1) for ln in proc.stdout.splitlines() if "=" in ln and ln[:1].isupper())
        assert facts["SHARED_LEASE_TOKEN"] == ""
        assert facts["SHARED_LEASE_ERROR"] == "acquire-exit-2"
        assert "shared lease was NOT registered" in proc.stderr
        assert facts["SERVE_STATE"] == "launched" and facts["SERVER_PID"]
    finally:
        pid = next((ln.split("=", 1)[1] for ln in proc.stdout.splitlines()
                    if ln.startswith("SERVER_PID=")), "")
        if pid:
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# serving a lease: the lease's venv, derived port keys, a verified bound server
# --------------------------------------------------------------------------- #
def test_serve_on_a_multi_profile_series_runs_the_leases_own_venv(client, world, tmp_path):
    """The catalog's FIRST row for the series is profile alpha; the lease is profile beta, whose
    python is a logging wrapper. The server must launch with beta's interpreter - the one the build
    leg was handed - not the first row's."""
    used = tmp_path / "beta-python-calls.log"
    beta_py = _stub(tmp_path / "beta-python", 'echo "$*" >> "%s"\nexec "%s" "$@"\n' % (used, world["python"]))
    base = world["port_base"]
    rows = []
    for profile, python, port_base in (("alpha", world["python"], base), ("beta", beta_py, base + 5)):
        rows.append("[[instance]]\n"
                    f'series = "{SERIES}"\nprofile = "{profile}"\npython = "{python}"\n'
                    f"http_port = {port_base - 1}\nhttp_port_base = {port_base}\n"
                    f'db_name = "insttest_{profile}"\ndb_host = "localhost"\ndb_user = "odoo"\n'
                    f'run_mode = "source"\naddons_path = ["{world["addons"]}"]\n')
    (world["home"] / "instances.toml").write_text("\n".join(rows), encoding="utf-8")
    lease = _lease(client, world, ports=1, profile="beta")
    assert lease["venv_python"] == str(beta_py)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    assert out["state"] == "launched" and out["server_pid"]
    launches = [ln for ln in used.read_text().splitlines() if " -c " in " %s " % ln]
    assert launches, "the listening server must be launched by the lease's (beta) interpreter"
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "profile": "alpha"}))
    assert err["code"] == "PROFILE_MISMATCH"
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_a_two_port_lease_is_served_with_the_series_second_port_key(client, world):
    lease = _lease(client, world, ports=2)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    assert out["server_pid"]
    conf = "\n".join(p.read_text() for p in (world["home"] / "conf").glob("*.conf"))
    assert "gevent_port = %d" % lease["ports"][1] in conf, conf
    assert "http_port = %d" % lease["ports"][0] in conf, conf
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


@pytest.mark.parametrize("checkout,key", [("8.0", "longpolling_port"), ("10.0", "longpolling_port"),
                                          ("15.0", "longpolling_port"), ("16.0", "gevent_port"),
                                          ("19.0", "gevent_port")])
def test_the_second_port_key_is_the_option_the_leases_checkout_declares(world, tmp_path, checkout, key):
    """The catalog says 17.0 throughout; the checkout the lease builds decides the key (its
    config.py option dest), so a series number can never pick a key the checkout lacks."""
    _declare_series(world, SERIES, checkout=checkout)
    stand_in, record = _ops_recorder(tmp_path)
    with McpClient(world["env"](ODOO_AI_OPS_SCRIPT=str(stand_in)), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=2)
        _wait(c, _ok(_build(c, world, lease["token"], op="test", test_tags="/x"))["job_id"])
    argv = json.loads(record.read_text())["argv"]
    pairs = dict(zip(argv[1::2], argv[2::2]))
    assert pairs["--gevent-port"] == str(lease["ports"][1]) and pairs["--gevent-port-key"] == key


def test_a_second_port_the_checkout_cannot_name_is_refused_before_anything_starts(world, tmp_path):
    config = world["addons"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines()
                                 if "--gevent-port" not in ln and "--longpolling-port" not in ln),
                      encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=2)
        err = _err(_build(c, world, lease["token"], op="test", test_tags="/x"))
    assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN" and "second port" in err["message"]
    assert "odoo_root" in err["remedy"]
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json"))


def test_serve_that_attaches_to_a_port_no_server_of_the_lease_holds_is_a_failure(client, world):
    """Something answers the lease's port, so the spin-up 'attaches' - but no server is bound to the
    lease. Reporting success would hand out a URL served by nobody this lease owns."""
    world["curl_mode"].write_text("200", encoding="utf-8")
    lease = _lease(client, world, ports=1)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "SERVE_FAILED" and err["diagnostics"]["serve_state"] == "attached"
    assert err["diagnostics"]["bound_pid"] is None
    row = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
    assert (row.get("owner") or {}).get("pid") is None


def test_a_served_lease_reports_its_url_and_once_parked_is_found_with_a_token_by_its_owner_only(client, world):
    """(Resuming is 50-instance-spinup.sh + allocator `resume` territory, exercised with a real
    listening stub in tests/test_resume_never_strands_a_server.py; this stub world's server is a
    bare `sleep`, which `resume` rightly refuses to adopt.)"""
    lease = _lease(client, world, ports=1)
    first = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                            timeout=120))
    port = lease["ports"][0]
    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["served"] is True and listed["http_port"] == port and listed["url"] == first["url"]
    _ok(client.call("lease_park", {"lease_token": lease["token"], "run_id": RUN}))
    deadline = time.monotonic() + 15
    while _alive(first["server_pid"]) and time.monotonic() < deadline:
        time.sleep(0.2)
    stranger = _ok(client.call("lease_find", {"series": SERIES, "state": "parked", "cwd": str(world["work"])}))
    assert stranger["found"] is True and stranger["lease"]["token"] is None
    assert stranger["lease"]["run_id"] is None and stranger["lease"]["token_prefix"] == lease["token"][:8]
    assert stranger["lease"]["served"] is False and stranger["lease"]["url"] is None
    owner = _ok(client.call("lease_find", {"series": SERIES, "state": "parked", "run_id": RUN,
                                           "cwd": str(world["work"])}))["lease"]
    assert owner["token"] == lease["token"] and owner["yours"] is True and owner["run_id"] == RUN
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def _stale_fingerprint(pid):
    """A well-formed `proc:<boot>:<start>` fingerprint of the SAME scheme and boot as `pid`'s real
    one, but a start time that provably does not match it - so `fp_verdict` proves a MISMATCH,
    never merely "unknown" (which would prove nothing either way)."""
    real = session_anchor.fingerprint(pid)
    assert real and real.startswith("proc:"), "test needs the proc: scheme (Linux)"
    boot, _sep, start = real[len("proc:"):].rpartition(":")
    assert boot and start
    return "proc:%s:%s" % (boot, str(int(start) + 1))


def test_served_survives_a_stale_pid_fp_left_by_an_older_allocators_bind(client, world):
    """scripts/lib/allocator.py PID_OWNER_KEYS: an OLDER allocator's `bind`/`resume` rewrites
    owner.pid + owner.pid_started but knows nothing of owner.pid_fp, so a pid_fp recorded for a
    PREVIOUS pid is left behind - trustworthy only while owner.pid_fp_pid still equals owner.pid
    (`_recorded_fingerprint`). Reading `pid_fp or pid_started` by hand (ignoring pid_fp_pid) treats
    that stale fingerprint as though it named the CURRENT pid: fp_verdict proves a MISMATCH against
    a server that is genuinely running, and `served` would wrongly read False."""
    lease = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    pid = out["server_pid"]
    reg_path = world["home"] / "runtime" / "leases.json"
    doc = json.loads(reg_path.read_text())
    row = next(lz for lz in doc["leases"] if lz["token"] == lease["token"])
    owner = row["owner"]
    assert owner["pid"] == pid and owner.get("pid_fp") and owner.get("pid_started")
    # Simulate the older allocator's partial rewrite: pid_fp_pid still names a PID OTHER than the
    # one pid/pid_started now record, and pid_fp is a fingerprint that does not match THIS pid.
    owner["pid_fp"] = _stale_fingerprint(pid)
    owner["pid_fp_pid"] = pid + 424242
    reg_path.write_text(json.dumps(doc), encoding="utf-8")

    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["served"] is True, "a stale pid_fp (pid_fp_pid != pid) must fall back to pid_started"
    assert listed["http_port"] == lease["ports"][0] and listed["url"] == out["url"]

    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


# --------------------------------------------------------------------------- #
# extra_args may not retarget what the tool controls
# --------------------------------------------------------------------------- #
REFUSED_EXTRA = ["--database=other", "--datab=other", "-d", "-dother", "--db-filter=.*", "--db_host=x",
                 "--db-host=x", "--db_port=1", "--db_user=x", "--db_password=x", "--addons-path=/x",
                 "-c", "--config=/x", "--data-dir=/x", "-D/x", "-i", "--init=base", "-u", "--update=all",
                 "--stop-after-init", "--test-enable", "--test-tags=/x", "-p8070", "--http-port=1",
                 "--xmlrpc-port=1", "--gevent-port=1", "--longpolling-port=1",
                 # optparse short-option CLUSTERS: every char is an option until one that takes a
                 # value consumes the rest - -s (--save) takes none, so -sd... still sets -d.
                 "-sdother_db", "-sd", "-sc/x.conf", "-sp8069", "-s",
                 # the connection, the rc file, the test switches, the log destination
                 "-rpostgres", "-r", "-wsecret", "-t/x", "--save", "--sa", "--logfile=/x", "--syslog",
                 "--pidfile=/x", "--db-template=tpl", "--db_template=tpl", "--db_replica_host=x",
                 "--db_replica_port=1", "--test-file=/x",
                 # "end of options": what follows (the tool's own flags) would become positional
                 "--",
                 # the build facts the tool applies itself (server-wide modules, languages, demo) -
                 # full names, accepted prefixes, and the short -l in a cluster
                 "--load=base,web", "--load", "--loa=base", "--load-language=fr_FR",
                 "--load-lang=fr_FR", "--language=fr_FR", "--lang=fr_FR", "-lfr_FR", "-ldother",
                 "-l", "-slfr_FR", "--with-demo", "--with", "--without-demo=all",
                 "--without-demo=True", "--without-demo", "--witho"]
ALLOWED_EXTRA = ["--log-level=debug", "--dev=xml", "--log-handler=odoo.sql_db:DEBUG",
                 "--http-interface=127.0.0.1", "--workers=0", "--i18n-overwrite",
                 "--db_maxconn=4", "--limit-time-real=600", "--limit-memory-soft=1",
                 "--skip-auto-install", "debug"]


@pytest.mark.parametrize("token", REFUSED_EXTRA)
def test_an_extra_arg_setting_a_tool_controlled_flag_is_refused_before_anything_starts(client, world, token):
    lease = _lease(client, world)
    err = _err(_build(client, world, lease["token"], extra_args=["--log-level=debug", token]))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.extra_args" in err["message"]
    assert err["diagnostics"]["token"] == token and err["diagnostics"]["flag"] in err["message"]
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json"))


def _shorts(tmp_path, series):
    """The short-option map a checkout of `series` declares (fixture tree, see odoo_tree_fixtures)."""
    from odoo_local_mcp_harness import import_package
    import_package()
    from odoo_local import cli
    return cli.load_lib("odoo_source_facts").short_options(trees.write_checkout(tmp_path / series, series))


def test_ordinary_extra_args_are_not_refused(tmp_path):
    shorts = _shorts(tmp_path, SERIES)
    from odoo_local import tools_instance
    assert [t for t in ALLOWED_EXTRA if tools_instance.refused_extra_flag(t, shorts)] == []


@pytest.mark.parametrize("token,series,flag", [
    ("-t/x", "17.0", "-t"), ("-t/x", "19.0", "-t"),  # the checkout declares -t as --test-tags
    ("-tEurope/Paris", "8.0", None),   # 8.0: -t is --timezone, a free option taking a value
    ("-tdfoo", "8.0", None),           # ... so "dfoo" is its value, not -d
    ("-t/x", "16.0", None),            # no -t declared: nothing it could set
    ("-sdfoo", "8.0", "-s"), ("-rodoo", "10.0", "-r"), ("-wx", "20.0", "-w"),
    ("-sdfoo", "20.0", "-d"),          # 20.0 declares no -s: the -d after it is still read
])
def test_short_option_meaning_follows_the_checkout(tmp_path, token, series, flag):
    shorts = _shorts(tmp_path, series)
    from odoo_local import tools_instance
    assert tools_instance.refused_extra_flag(token, shorts) == flag
    assert tools_instance.refused_extra_flag("--database=x", None) == "--database", (
        "a long option needs no checkout")
    with pytest.raises(ValueError):
        tools_instance.refused_extra_flag(token, None)


def test_a_short_extra_arg_with_no_readable_checkout_is_refused_before_anything_starts(world):
    """What a short option sets depends on the checkout (-t is --timezone or --test-tags or
    nothing); with no checkout to read, it is refused rather than guessed."""
    config = world["addons"].parent / "odoo" / "tools" / "config.py"
    config.unlink()
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world)
        err = _err(_build(c, world, lease["token"], demo=None, op="update", extra_args=["-t/x"]))
    assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN" and "short options" in err["message"]


# --------------------------------------------------------------------------- #
# token + owner run disclosure across sessions
# --------------------------------------------------------------------------- #
def _other_session(world, session_id="sess-other"):
    """(env, anchor process) of a second, LIVE Claude Code session on the same machine."""
    proc = subprocess.Popen(["sleep", "900"])
    env = world["env"]()
    env["ODOO_AI_SESSION_ANCHOR"] = session_anchor.format_anchor(proc.pid, session_anchor.fingerprint(proc.pid))
    env["CLAUDE_CODE_SESSION_ID"] = session_id
    return env, proc


def test_attaching_to_another_runs_render_server_is_not_obtaining_it(client, world):
    """instance_serve(series) that ATTACHES to a server another run launched hands back the URL - a
    reader needs nothing else - but never the owner's token or run id: with both, the reader
    could lease_release the render server out from under every other reader."""
    owner = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                            timeout=120))
    token = owner["lease_token"]
    assert owner["state"] == "launched" and token and owner["instance_handle"]["lease_token"] == token
    env, proc = _other_session(world)
    try:
        with McpClient(env, world["work"]) as reader:
            reader.initialize()
            for run_id in ("run-reader", RUN):  # naming the owner's run from a live foreign session
                out = _ok(reader.call("instance_serve", {"series": SERIES, "run_id": run_id,
                                                         "cwd": str(world["work"])}, timeout=120))
                assert out["state"] == "attached" and out["url"] == owner["url"], run_id
                assert out["http_port"] == owner["http_port"]
                assert out["lease_token"] is None and out["instance_handle"]["lease_token"] is None, run_id
                assert out["instance_handle"]["run_id"] == "", run_id
                assert token not in json.dumps(out) and RUN not in json.dumps(out["instance_handle"]), run_id
    finally:
        proc.kill()
        proc.wait()
    # The owner's own session re-attaching is still handed its lease.
    again = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                            timeout=120))
    assert again["state"] == "attached" and again["lease_token"] == token
    assert [lz["token"] for lz in _registry(world) if lz["mode"] == "shared"] == [token]


def _serve_and_park(client, world):
    lease = _lease(client, world, ports=1)
    first = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                            timeout=120))
    _ok(client.call("lease_park", {"lease_token": lease["token"], "run_id": RUN}))
    deadline = time.monotonic() + 15
    while _alive(first["server_pid"]) and time.monotonic() < deadline:
        time.sleep(0.2)
    return lease


def test_a_foreign_session_cannot_list_find_and_take_a_parked_lease(client, world):
    """The live repro: another session lists every lease, then asks lease_find for the parked one -
    guessing the owner's run - and would adopt + release it with what came back. Neither listing
    nor finding may hand it the token or the owner run while the owning session lives."""
    lease = _serve_and_park(client, world)
    env, proc = _other_session(world)
    try:
        with McpClient(env, world["work"]) as foreign:
            foreign.initialize()
            rows = _ok(foreign.call("lease_list", {"scope": "all"}))["leases"]
            row = next(r for r in rows if r["token_prefix"] == lease["token"][:8])
            assert row["token"] is None and row["run_id"] is None
            for args in ({}, {"run_id": "run-guess"}, {"run_id": RUN}):
                found = _ok(foreign.call("lease_find", dict({"series": SERIES, "state": "parked",
                                                              "cwd": str(world["work"])}, **args)))
                assert found["found"] is True and found["lease"]["token"] is None, args
                assert found["lease"]["session_alive"] is True, "the owning session is measured, parked or not"
                assert found["lease"]["run_id"] is None and found["lease"]["yours"] is False, args
                assert lease["token"] not in json.dumps(found), args
    finally:
        proc.kill()
        proc.wait()
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_an_owner_resuming_from_a_new_session_sees_the_ended_session_and_gets_the_token(client, world):
    """The legitimate resume: the session that parked the lease has ended, and the owner run
    continues in a new session. lease_find(parked, run_id) reports session_alive=false (measured,
    not null - the adopt-or-not decision reads it) and hands the token back for lease_adopt."""
    env, proc = _other_session(world, "sess-earlier")
    with McpClient(env, world["work"]) as earlier:
        earlier.initialize()
        lease = _serve_and_park(earlier, world)
    proc.kill()
    proc.wait()
    listed = next(r for r in _ok(client.call("lease_list", {"scope": "all"}))["leases"]
                  if r["token_prefix"] == lease["token"][:8])
    assert listed["session_alive"] is False and listed["token"] is None
    found = _ok(client.call("lease_find", {"series": SERIES, "state": "parked", "run_id": RUN,
                                           "cwd": str(world["work"])}))["lease"]
    assert found["session_alive"] is False
    assert found["token"] == lease["token"] and found["run_id"] == RUN and found["yours"] is True
    err = _err(client.call("instance_serve", {"lease_token": found["token"], "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "LEASE_NOT_ADOPTED", "an earlier session's park is adopted before it is served"
    adopted = _ok(client.call("lease_adopt", {"lease_token": found["token"], "run_id": RUN}))
    assert adopted["lease"]["session_alive"] is True
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_serving_a_parked_lease_of_another_session_needs_lease_adopt_first(client, world):
    """Serving re-anchors a parked lease onto the server that serves it, and instance_serve takes no
    run id - so a parked lease recorded by another session is refused by name until the owner run
    lease_adopt-s it (which checks the run). The lease is left exactly as it was."""
    lease = _serve_and_park(client, world)
    before = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
    env, proc = _other_session(world)
    try:
        with McpClient(env, world["work"]) as other:
            other.initialize()
            err = _err(other.call("instance_serve", {"lease_token": lease["token"],
                                                     "cwd": str(world["work"])}, timeout=120))
            assert err["code"] == "LEASE_NOT_ADOPTED"
            assert "lease_adopt" in err["remedy"] and "instance_serve" in err["remedy"]
            after = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
            assert after == before, "a refused serve must not touch the lease"
            _ok(other.call("lease_adopt", {"lease_token": lease["token"], "run_id": RUN}))
            # Past the gate now: whatever the (stub) resume says, it is no longer LEASE_NOT_ADOPTED.
            res = other.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                             timeout=120)
            assert res["isError"] is False or structured(res)["error"]["code"] != "LEASE_NOT_ADOPTED"
            _ok(other.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    finally:
        proc.kill()
        proc.wait()


def test_the_owning_session_serves_its_own_parked_lease_without_adopting(client, world):
    lease = _serve_and_park(client, world)
    res = client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])}, timeout=120)
    assert res["isError"] is False or structured(res)["error"]["code"] != "LEASE_NOT_ADOPTED"
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


# --------------------------------------------------------------------------- #
# a first launch leaves no resume refusal in the allocator log
# --------------------------------------------------------------------------- #
def test_a_first_launch_logs_no_resume_refusal(client, world):
    """A never-served lease is not parked: `resume` could only refuse it (and log that it refused)
    before the spin-up falls back to `bind`. Every ordinary serve used to write that refusal into
    the allocator stderr log, burying the refusals that matter."""
    lease = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    row = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
    assert row["owner"]["pid"] == out["server_pid"], "the launched server is still bound"
    logs = list(world["home"].rglob("allocator-stderr.log"))
    text = "".join(p.read_text(errors="replace") for p in logs)
    assert "REFUSING to resume" not in text, text
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


# --------------------------------------------------------------------------- #
# instance_serve(series) against a catalog that declares nothing for it
# --------------------------------------------------------------------------- #
def test_serving_an_undeclared_series_is_no_instance(client, world):
    err = _err(client.call("instance_serve", {"series": "99.0", "run_id": RUN, "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "NO_INSTANCE" and "catalog_read" in err["remedy"]


def test_serving_with_no_catalog_at_all_is_no_instance_catalog(client, world):
    (world["home"] / "instances.toml").unlink()
    err = _err(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "NO_INSTANCE_CATALOG" and "odoo-setup" in err["remedy"]
