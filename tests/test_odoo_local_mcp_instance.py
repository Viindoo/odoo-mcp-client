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
import re
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
    # odoo_db.py answers nothing (the database cannot be read) unless a test writes db-facts.out:
    # then `db-facts` prints that file - what the database holds.
    db_facts = tmp_path / "db-facts.out"
    fake_py = _stub(fake_py_dir / "python", textwrap.dedent("""\
        if [[ "${2:-}" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        case "${1:-}" in
            *odoo_db.py)
                if [[ "${2:-}" == "db-facts" && -f "%(facts)s" ]]; then cat "%(facts)s"; fi
                exit 0 ;;
            %(bin)s) shift; exec bash "%(bin)s" "$@" ;;
        esac
        exec %(real)s "$@"
        """ % {"bin": odoo_bin, "real": sys.executable, "facts": db_facts}))

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
        values = dict(ODOO_AI_SESSION_ANCHOR=anchor, CLAUDE_CODE_SESSION_ID="sess-inst",
                      ODOO_BIN=str(odoo_bin), PATH="%s:%s" % (bindir, os.environ.get("PATH", "")),
                      SPINUP_TIMEOUT="10")
        values.update(extra)
        return hermetic_env(home, **values)

    w = {"home": home, "work": tmp_path, "addons": addons, "behavior": behavior, "calls": calls,
         "confs": confs, "rc_env": rc_env,
         "odoo_bin": odoo_bin, "python": fake_py, "curl_mode": curl_mode, "env": env,
         "port_base": port_base, "db_facts": db_facts}
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
    assert _odoo_bin_port_flags(world) == [], "a port-less install passes no port flag"


def test_a_builds_verdict_is_its_exit_code_and_the_markers_the_script_reads(client, world):
    """One lease, three builds: a module Odoo silently skipped is a failure; a failing test run is a
    failure that carries the test verdict; a running build answers a short wait with its state and
    the next wait with the verdict."""
    lease = _lease(client, world, ports=1)

    world["behavior"].write_text(
        'echo "odoo.modules.loading: invalid module names, ignored: my_mod"\n'
        'echo "odoo.modules.loading: Modules loaded."\nexit 0\n', encoding="utf-8")
    done = _wait(client, _ok(_build(client, world, lease["token"]))["job_id"])
    assert done["result"] == "failure" and done["exit_code"] != 0, ("a skipped module", done)

    world["behavior"].write_text(
        'echo "odoo.modules.loading: Modules loaded."\n'
        'echo "odoo.tests.result: 1 failed, 0 error(s) of 3 tests when loading database"\nexit 1\n',
        encoding="utf-8")
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test", test_tags="/my_mod"))["job_id"])
    assert done["result"] == "failure" and done["test_result"] == "failed", ("a failing test run", done)
    assert done["summary"].get("TEST_TAGS_USED") == "/my_mod"
    assert "--test-tags /my_mod" in world["calls"].read_text()

    gate = world["work"] / "build-gate"
    world["behavior"].write_text('while [[ ! -f "%s" ]]; do sleep 0.1; done\n'
                                 'echo "odoo.modules.loading: Modules loaded."\nexit 0\n' % gate,
                                 encoding="utf-8")
    job_id = _ok(_build(client, world, lease["token"]))["job_id"]
    first = _wait(client, job_id, timeout_s=1)
    assert first["result"] == "timeout" and first["state"] == "running", ("a running build", first)
    gate.write_text("go", encoding="utf-8")
    assert _wait(client, job_id)["result"] == "success"


def test_a_test_runs_summary_states_from_structured_fields_whether_a_browser_suite_ran(client, world):
    """job_wait's summary carries JS_RESULT beside the counts it was derived from: a run whose
    selection drives no Hoot/QUnit suite says `absent` (no failure line is not a pass), a suite
    that ran green says `passed`, and TESTS_RUN is the database total of Odoo's result line."""
    lease = _lease(client, world, ports=1)
    base = ('echo "odoo.modules.loading: Modules loaded."\n'
            'echo "odoo.service.server: 1366 post-tests in 977.14s, 380231 queries"\n'
            'echo "odoo.tests.stats: my_module: 2409 tests 907.85s 380231 queries"\n'
            'echo "odoo.tests.result: 0 failed, 0 error(s) of 1369 tests when loading database"\n')
    world["behavior"].write_text(base + "exit 0\n", encoding="utf-8")
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test", test_tags="/my_mod"))["job_id"])
    assert done["test_result"] == "passed" and done["summary"]["JS_RESULT"] == "absent", done["summary"]
    assert done["summary"]["TESTS_RUN"] == "1369", done["summary"]

    world["behavior"].write_text(
        base + 'echo "odoo.addons.web.tests.test_js.WebSuite.browser: QUnit test suite done."\nexit 0\n',
        encoding="utf-8")
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test", test_tags="/web:WebSuite"))["job_id"])
    assert done["summary"]["JS_RESULT"] == "passed" and done["summary"]["JS_RUNS"] == "1", done["summary"]


def test_job_survives_a_server_restart(world):
    gate = world["work"] / "build-gate"
    world["behavior"].write_text('while [[ ! -f "%s" ]]; do sleep 0.1; done\n'
                                 'echo "odoo.modules.loading: Modules loaded."\nexit 0\n' % gate,
                                 encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as first:
        first.initialize()
        lease = _lease(first, world)
        job_id = _ok(_build(first, world, lease["token"]))["job_id"]
    # The first server is gone and the build still runs; a fresh one knows the job from its record
    # on disk.
    gate.write_text("go", encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as second:
        second.initialize()
        done = _wait(second, job_id)
        assert done["result"] == "success" and done["exit_code"] == 0


def test_release_stops_a_build_still_running_on_the_lease(client, world):
    world["behavior"].write_text("sleep 120\nexit 0\n", encoding="utf-8")
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"]))
    deadline = time.monotonic() + 30
    while not world["calls"].exists() and time.monotonic() < deadline:
        time.sleep(0.1)  # the build is running once odoo-bin has been launched
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
    # An extra arg that sets what the tool controls is refused through the tool, naming the flag
    # (which tokens count is decided by refused_extra_flag, held to the full table below): a long
    # option, a short-option cluster and a build fact.
    for extra in ("--database=other", "-sdother_db", "--load=base,web"):
        err = _err(_build(client, world, token, extra_args=["--log-level=debug", extra]))
        assert err["code"] == "INVALID_ARGUMENTS" and "arguments.extra_args" in err["message"], extra
        assert err["diagnostics"]["token"] == extra and err["diagnostics"]["flag"] in err["message"], extra
    # A test build binds a port, so a lease without one is refused by name.
    err = _err(_build(client, world, token, op="test", test_tags="/my_mod"))
    assert err["code"] == "LEASE_HAS_NO_PORT" and "ports 1" in err["remedy"]
    assert "instance_build" in err["remedy"]
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json")), "no refused build started a job"
    assert not world["calls"].exists() or "--test-enable" not in world["calls"].read_text()
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


def test_the_tool_hands_the_script_the_leases_facts_not_the_agents(world, tmp_path):
    """ODOO_AI_OPS_SCRIPT (test-only) replaces the 55 script with a recorder, so the exact argv the
    tool builds from the lease row - not from the agent - is observable: every connection fact of
    the row, the declared odoo_root only when there is one, and the checkout's own second-port key."""
    stand_in, record = _ops_recorder(tmp_path)

    def last_pairs():
        argv = json.loads(record.read_text())["argv"]
        return argv, dict(zip(argv[1::2], argv[2::2]))

    with McpClient(world["env"](ODOO_AI_OPS_SCRIPT=str(stand_in)), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", modules=["a", "b"], test_mode="reuse",
                         log_mode="debug", extra_args=["--log-level=warn", "--workers=0"]))
        done = _wait(c, job["job_id"])
        seen = json.loads(record.read_text())
        argv, pairs = last_pairs()
        assert argv[0] == "test"
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
        assert "--odoo-root" not in argv, "an undeclared odoo_root is omitted"
        assert seen["log"] == job["log_path"]
        assert done["result"] == "success"
        _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))

        # The build script locates the Odoo launcher on the served addons_path and falls back to the
        # instance's declared odoo_root - but only when it is handed that root: a lease whose
        # addons_path names only a worktree of custom modules failed every build otherwise.
        core = world["addons"].parent
        toml = world["home"] / "instances.toml"
        toml.write_text(toml.read_text() + 'odoo_root = "%s"\n' % core, encoding="utf-8")
        lease = _lease(c, world)
        _wait(c, _ok(_build(c, world, lease["token"]))["job_id"])
        assert last_pairs()[1].get("--odoo-root") == str(core)
        _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))

        # With two ports the second one is spelled with the key the lease's checkout declares (its
        # config.py option dest), so a series number can never pick a key the checkout lacks.
        for checkout, key in (("8.0", "longpolling_port"), ("10.0", "longpolling_port"),
                              ("15.0", "longpolling_port"), ("16.0", "gevent_port"),
                              ("19.0", "gevent_port")):
            _declare_series(world, SERIES, checkout=checkout)
            lease = _lease(c, world, ports=2)
            _wait(c, _ok(_build(c, world, lease["token"], op="test", test_tags="/x"))["job_id"])
            pairs = last_pairs()[1]
            assert pairs["--gevent-port"] == str(lease["ports"][1]), checkout
            assert pairs["--gevent-port-key"] == key, checkout
            _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_what_the_checkout_cannot_state_refuses_the_build_before_anything_starts(client, world):
    """A second port the checkout cannot name, and a short extra arg with no readable checkout (what
    a short option sets depends on the checkout), are refused rather than guessed."""
    config = world["addons"].parent / "odoo" / "tools" / "config.py"
    original = config.read_text()
    config.write_text("\n".join(ln for ln in original.splitlines()
                                if "--gevent-port" not in ln and "--longpolling-port" not in ln),
                      encoding="utf-8")
    lease = _lease(client, world, ports=2)
    err = _err(_build(client, world, lease["token"], op="test", test_tags="/x"))
    assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN"
    assert "odoo_root" in err["remedy"]
    config.unlink()
    err = _err(_build(client, world, lease["token"], demo=None, op="update", extra_args=["-t/x"]))
    assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN"
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json"))


# --------------------------------------------------------------------------- #
# a build binds the lease's port, with the flag its series spells
# --------------------------------------------------------------------------- #
def _odoo_bin_port_flags(world):
    """The (flag, value) pairs for listening ports in the recorded odoo-bin calls."""
    words = world["calls"].read_text().split()
    return [(w, words[i + 1]) for i, w in enumerate(words[:-1])
            if w in ("--http-port", "--xmlrpc-port", "--gevent-port", "--longpolling-port")]


def _interface_flags(world):
    """The (flag, value) pairs for the listen address in the recorded odoo-bin calls."""
    words = world["calls"].read_text().split()
    return [(w, words[i + 1]) for i, w in enumerate(words[:-1])
            if w in ("--http-interface", "--xmlrpc-interface")]


def _declare_series(world, series, checkout=None):
    """Re-declare the stubbed world's single catalog row under another series, and make its core
    dir a checkout of `checkout` (default: the same series)."""
    toml = world["home"] / "instances.toml"
    toml.write_text(re.sub(r'(?m)^series = ".*"$', 'series = "%s"' % series, toml.read_text(), count=1),
                    encoding="utf-8")
    trees.write_checkout(world["addons"].parent, checkout or series, with_addons=False)


@pytest.mark.parametrize("series,flag", [("17.0", "--http-port"), ("11.0", "--http-port"),
                                         ("10.0", "--xmlrpc-port"), ("8.0", "--xmlrpc-port"),
                                         ("19.0", "--http-port"), ("20.0", "--http-port")])
def test_a_test_build_binds_the_leases_port_and_states_loopback_as_its_series_spells_them(
        world, series, flag):
    """Odoo starts its HTTP server whenever test mode is on, even with --stop-after-init. A test
    build that does not pass the leased port binds the default 8069 and collides with whatever
    already listens there - so odoo-bin must receive the lease's port, spelled for the series. A
    series that logs "missing --http-interface, using 0.0.0.0" on every start turns every clean run
    into tests-passed-with-warnings; the build states the loopback address itself (19.0 only: the
    others default to all interfaces without a warning or to loopback already)."""
    _declare_series(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", test_tags="/my_mod"))
        _wait(c, job["job_id"])
    assert _odoo_bin_port_flags(world) == [(flag, str(lease["ports"][0]))]
    assert _interface_flags(world) == ([("--http-interface", "127.0.0.1")] if series == "19.0" else [])


def test_a_two_port_lease_builds_with_both_ports_and_a_caller_chosen_listen_address_wins(client, world):
    """Odoo's option parser keeps the last value, so an explicit --http-interface in extra_args (a
    caller who wants another address) comes after the loopback the build states and wins."""
    _declare_series(world, "19.0")
    lease = _lease(client, world, series="19.0", ports=2)
    job = _ok(_build(client, world, lease["token"], op="test", test_tags="/my_mod",
                     extra_args=["--http-interface=0.0.0.0"]))
    _wait(client, job["job_id"])
    assert _odoo_bin_port_flags(world) == [("--http-port", str(lease["ports"][0])),
                                           ("--gevent-port", str(lease["ports"][1]))]
    words = world["calls"].read_text().split()
    assert words.index("127.0.0.1") < words.index("--http-interface=0.0.0.0")


# --------------------------------------------------------------------------- #
# instance_serve / instance_status
# --------------------------------------------------------------------------- #
def _conf_text(world):
    return "\n".join(p.read_text() for p in (world["home"] / "conf").glob("*.conf"))


def test_a_leases_server_is_launched_bound_reported_and_stopped_by_the_release(client, world):
    port_base = world["port_base"]
    world["curl_mode"].write_text("000", encoding="utf-8")  # nothing answers the declared port
    lease = _lease(client, world, ports=1)
    port = lease["ports"][0]
    # Before the serve: the series (its declared instance, not running) and the lease agree on "down".
    by_series = _ok(client.call("instance_status", {"series": SERIES, "cwd": str(world["work"])}))
    assert by_series["up"] is False and by_series["lease"] is None
    before = _ok(client.call("instance_status", {"lease_token": lease["token"], "cwd": str(world["work"])}))
    assert before["up"] is False and before["lease"]["served"] is False and before["series"] == SERIES

    world["curl_mode"].write_text("boot", encoding="utf-8")  # nothing listens yet, then the server does
    (world["curl_mode"].parent / "curl-count").unlink(missing_ok=True)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"],
                                             "cwd": str(world["work"])}, timeout=120))
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
    # A first launch is not a resume: no refusal to resume lands in the allocator log.
    log_text = "".join(p.read_text(errors="replace") for p in world["home"].rglob("allocator-stderr.log"))
    assert "REFUSING to resume" not in log_text, log_text

    # Status of the served lease reports that lease's own port, not the declared instance's.
    after = _ok(client.call("instance_status", {"lease_token": lease["token"], "cwd": str(world["work"])}))
    assert after["up"] is True and after["http_port"] == port
    assert after["url"] == "http://localhost:%d" % port and after["lease"]["served"] is True
    assert after["http_port"] != port_base - 1, "the lease's port, not the declared one"
    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["served"] is True and listed["http_port"] == port and listed["url"] == out["url"]

    # scripts/lib/allocator.py PID_OWNER_KEYS: an OLDER allocator's `bind`/`resume` rewrites
    # owner.pid + owner.pid_started but knows nothing of owner.pid_fp, so a pid_fp recorded for a
    # PREVIOUS pid is left behind - trustworthy only while owner.pid_fp_pid still equals owner.pid.
    # Reading pid_fp by hand would prove a MISMATCH against a server that is genuinely running and
    # `served` would wrongly read False.
    reg_path = world["home"] / "runtime" / "leases.json"
    doc = json.loads(reg_path.read_text())
    owner = next(lz for lz in doc["leases"] if lz["token"] == lease["token"])["owner"]
    assert owner.get("pid_fp") and owner.get("pid_started")
    owner["pid_fp"] = _stale_fingerprint(pid)
    owner["pid_fp_pid"] = pid + 424242
    reg_path.write_text(json.dumps(doc), encoding="utf-8")
    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["served"] is True, "a stale pid_fp (pid_fp_pid != pid) must fall back to pid_started"
    assert listed["http_port"] == port and listed["url"] == out["url"]

    # Releasing the lease stops that server.
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    deadline = time.monotonic() + 15
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(pid)


def _listener_argv(world):
    """The argv of every LISTENING launch (a `-c <conf>` launch without --stop-after-init)."""
    return [line for line in world["calls"].read_text().splitlines()
            if " -c " in line and "--stop-after-init" not in line]


def _set_dev_shape(world, shape):
    """Rewrite the checkout's --dev declaration: "value" keeps the fixture's, "flag" makes it a
    boolean switch, "none" removes it."""
    config = next((world["odoo_bin"].parent).glob("*/tools/config.py"))
    text = config.read_text(encoding="utf-8")
    declared = "group.add_option('--dev', dest='dev_mode', type=\"string\")"
    assert declared in text, "the fixture declares a value-taking --dev"
    replacement = {"value": declared, "flag": "group.add_option('--dev', dest='dev_mode', action='store_true')",
                   "none": ""}[shape]
    config.write_text(text.replace(declared, replacement), encoding="utf-8")


def test_a_leases_server_runs_without_developer_features_unless_asked(client, world):
    """A served instance is what captures, acceptance and UI review are judged on, usually from a
    worktree whose files are still being saved: by default it states no --dev (no restart on a saved
    file, views from the database); only developer_server asks for Odoo's developer features, in
    the spelling the checkout declares. The result says which kind runs, on an attach too."""
    plain = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": plain["token"], "cwd": str(world["work"])},
                          timeout=120))
    assert out["state"] == "launched" and out["developer_server"] is False
    (launch,) = _listener_argv(world)
    assert "--dev" not in launch, launch

    dev = _lease(client, world, ports=1)
    (world["curl_mode"].parent / "curl-count").unlink(missing_ok=True)  # nothing listens yet again
    out = _ok(client.call("instance_serve", {"lease_token": dev["token"], "developer_server": True,
                                             "cwd": str(world["work"])}, timeout=120))
    assert out["state"] == "launched" and out["developer_server"] is True
    assert "--dev=reload,qweb,xml" in _listener_argv(world)[-1]

    # An attach launches nothing: the result reports what the running server was started with.
    again = _ok(client.call("instance_serve", {"lease_token": dev["token"], "cwd": str(world["work"])},
                            timeout=120))
    assert again["state"] == "attached" and again["developer_server"] is True
    plain_again = _ok(client.call("instance_serve", {"lease_token": plain["token"],
                                                     "cwd": str(world["work"])}, timeout=120))
    assert plain_again["state"] == "attached" and plain_again["developer_server"] is False
    assert len(_listener_argv(world)) == 2, "an attach starts no server"

    # A running server keeps what it was launched with: the developer server is not silently absent.
    err = _err(client.call("instance_serve", {"lease_token": plain["token"], "developer_server": True,
                                              "cwd": str(world["work"])}, timeout=120))
    assert err["code"] == "DEV_SERVER_NOT_APPLIED" and err["diagnostics"]["running"] is False
    assert len(_listener_argv(world)) == 2


@pytest.mark.parametrize("shape,expected", [("flag", " --dev"), ("value", " --dev=reload,qweb,xml")])
def test_the_developer_server_flag_follows_the_shape_the_checkout_declares(client, world, shape, expected):
    _set_dev_shape(world, shape)
    lease = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "developer_server": True,
                                             "cwd": str(world["work"])}, timeout=120))
    assert out["developer_server"] is True
    launch = _listener_argv(world)[-1]
    assert launch.endswith(expected), launch


def test_a_developer_server_is_refused_where_the_checkout_has_no_dev_option(client, world):
    _set_dev_shape(world, "none")
    lease = _lease(client, world, ports=1)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "developer_server": True,
                                              "cwd": str(world["work"])}, timeout=120))
    assert err["code"] == "DEV_SERVER_UNSUPPORTED", err
    assert not world["calls"].exists() or not _listener_argv(world), "nothing may be launched"
    (world["curl_mode"].parent / "curl-count").unlink(missing_ok=True)  # nothing listens yet
    ok = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                         timeout=120))
    assert ok["developer_server"] is False and "--dev" not in _listener_argv(world)[-1]


def test_a_developer_server_is_never_the_shared_declared_instance(client, world):
    err = _err(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "developer_server": True,
                                              "cwd": str(world["work"])}))
    assert err["code"] == "INVALID_ARGUMENTS" and "developer_server" in err["message"]
    shared = _lease(client, world, mode="shared")
    err = _err(client.call("instance_serve", {"lease_token": shared["token"], "developer_server": True,
                                              "cwd": str(world["work"])}))
    assert err["code"] == "INVALID_ARGUMENTS" and "developer_server" in err["message"]
    assert not world["calls"].exists() or not _listener_argv(world), "nothing may be launched"


def test_serve_with_an_addons_path_that_drops_the_core_addons_is_refused_before_anything_starts(
        client, world):
    """lease_acquire refuses an addons_path naming only a worktree (the launcher is found through
    odoo_root, but no core module is on the path); instance_serve's addons_path override must not
    be a way around that rule. Refused with the same code and reason, nothing is launched; the
    same override keeping the core addons directory serves."""
    lease = _lease(client, world, ports=1)
    worktree = world["work"] / "wt-only"
    worktree.mkdir()
    err = _err(client.call("instance_serve", {"lease_token": lease["token"],
                                              "addons_path": [str(worktree)],
                                              "cwd": str(world["work"])}, timeout=120))
    assert err["code"] == "ADDONS_PATH_OVERRIDE_INVALID"
    assert err["diagnostics"]["fields"]["reason"] == "core-addons-missing"
    assert not world["calls"].exists() or "-c " not in world["calls"].read_text(), "nothing launched"
    row = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
    assert not (row.get("owner") or {}).get("pid"), "no server was bound onto the lease"

    out = _ok(client.call("instance_serve", {"lease_token": lease["token"],
                                             "addons_path": [str(world["addons"]), str(worktree)],
                                             "cwd": str(world["work"])}, timeout=120))
    assert out["state"] == "launched" and out["served_addons_path"] == [str(world["addons"]), str(worktree)]
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_serve_and_status_refuse_what_cannot_be_served_or_asked_by_name(client, world):
    lease = _lease(client, world)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"]}))
    assert err["code"] == "LEASE_HAS_NO_PORT" and "ports 1" in err["remedy"], "serve, no port"
    assert _err(client.call("instance_serve", {}))["code"] == "INVALID_ARGUMENTS", "serve, neither"
    both = client.call("instance_serve", {"lease_token": lease["token"], "series": SERIES})
    assert _err(both)["code"] == "INVALID_ARGUMENTS", "serve, both"
    err = _err(client.call("instance_serve", {"series": "99.0", "run_id": RUN, "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "NO_INSTANCE" and "catalog_read" in err["remedy"], "serve, undeclared series"

    assert _err(client.call("instance_status", {"cwd": str(world["work"])}))["code"] == "INVALID_ARGUMENTS"
    ported = _lease(client, world, ports=1)
    err = _err(client.call("instance_status", {"lease_token": ported["token"], "series": "16.0",
                                               "cwd": str(world["work"])}))
    assert err["code"] == "INVALID_ARGUMENTS"
    world["curl_mode"].write_text("000", encoding="utf-8")
    out = _ok(client.call("instance_status", {"series": SERIES, "cwd": str(world["work"])}))
    assert out == {"series": SERIES, "up": False, "http_port": None, "url": None, "lease": None,
                   "shared_lease": None, "parked_lease": None}, "status, nothing running"

    # The allocator matches `--series ""` against rows that record no series, so asking it for the
    # shared / parked lease of an empty series answers with whichever such row exists - here the
    # very lease being asked about, reported as the shared render lease of no series at all.
    path = world["home"] / "runtime" / "leases.json"
    data = json.loads(path.read_text())
    for row in data["leases"]:
        if row["token"] == ported["token"]:
            row["series"], row["mode"] = "", "shared"
    path.write_text(json.dumps(data))
    out = _ok(client.call("instance_status", {"lease_token": ported["token"], "cwd": str(world["work"])}))
    assert out["series"] == "" and out["lease"]["token"] == ported["token"]
    assert out["shared_lease"] is None and out["parked_lease"] is None, "no series: no borrowed answer"

    (world["home"] / "instances.toml").unlink()
    err = _err(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "NO_INSTANCE_CATALOG" and "odoo-setup" in err["remedy"], "serve, no catalog"


def test_serve_by_series_registers_the_shared_render_lease_and_a_foreign_attach_never_obtains_it(
        client, world):
    """instance_serve(series) that ATTACHES to a server another run launched hands back the URL - a
    reader needs nothing else - but never the owner's token or run id: with both, the reader
    could lease_release the render server out from under every other reader."""
    out = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                          timeout=120))
    assert out["shared_lease_error"] is None
    token = out["lease_token"]
    assert token and out["state"] == "launched" and out["instance_handle"]["lease_token"] == token
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

    env, proc = _other_session(world)
    try:
        with McpClient(env, world["work"]) as foreign:
            foreign.initialize()
            for run_id in ("run-reader", RUN):  # naming the owner's run from a live foreign session
                att = _ok(foreign.call("instance_serve", {"series": SERIES, "run_id": run_id,
                                                          "cwd": str(world["work"])}, timeout=120))
                assert att["state"] == "attached" and att["url"] == out["url"], run_id
                assert att["http_port"] == out["http_port"]
                assert att["lease_token"] is None and att["instance_handle"]["lease_token"] is None, run_id
                assert att["instance_handle"]["run_id"] == "", run_id
                assert token not in json.dumps(att) and RUN not in json.dumps(att["instance_handle"]), run_id
    finally:
        proc.kill()
        proc.wait()
    # The owner's own session re-attaching is still handed its lease.
    again = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                            timeout=120))
    assert again["state"] == "attached" and again["lease_token"] == token
    assert [lz["token"] for lz in _registry(world) if lz["mode"] == "shared"] == [token]


def test_a_serve_that_cannot_become_ready_or_attaches_to_a_stranger_is_a_failure(world):
    with McpClient(world["env"](SPINUP_TIMEOUT="3"), world["work"]) as client:
        client.initialize()
        # Something answers the lease's port, so the spin-up 'attaches' - but no server is bound to
        # the lease. Reporting success would hand out a URL served by nobody this lease owns.
        world["curl_mode"].write_text("200", encoding="utf-8")
        lease = _lease(client, world, ports=1)
        err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                               timeout=120))
        assert err["code"] == "SERVE_FAILED" and err["diagnostics"]["serve_state"] == "attached"
        assert err["diagnostics"]["bound_pid"] is None
        row = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
        assert (row.get("owner") or {}).get("pid") is None

        world["curl_mode"].write_text("000", encoding="utf-8")  # never becomes ready
        err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                               timeout=120))
        assert err["code"] == "SERVE_FAILED"
        assert err["diagnostics"]["stderr"].strip(), "the script's own reason is carried"


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
# serving a lease: the lease's venv, derived port keys, the loopback its series needs
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


@pytest.mark.parametrize("series,line", [("19.0", "http_interface = 127.0.0.1"), ("17.0", None)])
def test_a_two_port_lease_is_served_with_the_series_second_port_key_and_the_loopback_it_needs(
        world, series, line):
    """The second port is written under the key the series spells (gevent_port here); a series
    that warns about the wildcard listen-address default is served with the loopback address stated,
    one that does not is served with no interface key at all."""
    _declare_series(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=2)
        out = _ok(c.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                         timeout=120))
        assert out["server_pid"]
        conf = _conf_text(world)
        assert "gevent_port = %d" % lease["ports"][1] in conf, conf
        assert "http_port = %d" % lease["ports"][0] in conf, conf
        if line:
            assert line in conf.splitlines(), conf
        else:
            assert "interface" not in conf, conf
        _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def _stale_fingerprint(pid):
    """A well-formed `proc:<boot>:<start>` fingerprint of the SAME scheme and boot as `pid`'s real
    one, but a start time that provably does not match it - so `fp_verdict` proves a MISMATCH,
    never merely "unknown" (which would prove nothing either way)."""
    real = session_anchor.fingerprint(pid)
    assert real and real.startswith("proc:"), "test needs the proc: scheme (Linux)"
    boot, _sep, start = real[len("proc:"):].rpartition(":")
    assert boot and start
    return "proc:%s:%s" % (boot, str(int(start) + 1))


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


def _shorts(tmp_path, series):
    """The short-option map a checkout of `series` declares (fixture tree, see odoo_tree_fixtures)."""
    from odoo_local_mcp_harness import import_package
    import_package()
    from odoo_local import cli
    return cli.load_lib("odoo_source_facts").short_options(trees.write_checkout(tmp_path / series, series))


def test_extra_args_setting_a_tool_controlled_flag_are_refused_and_ordinary_ones_are_not(tmp_path):
    shorts = _shorts(tmp_path, SERIES)
    from odoo_local import tools_instance
    assert [t for t in REFUSED_EXTRA if not tools_instance.refused_extra_flag(t, shorts)] == []
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


# --------------------------------------------------------------------------- #
# a parked lease: who may see its token, who may serve it
# --------------------------------------------------------------------------- #
def _other_session(world, session_id="sess-other"):
    """(env, anchor process) of a second, LIVE Claude Code session on the same machine."""
    proc = subprocess.Popen(["sleep", "900"])
    env = world["env"]()
    env["ODOO_AI_SESSION_ANCHOR"] = session_anchor.format_anchor(proc.pid, session_anchor.fingerprint(proc.pid))
    env["CLAUDE_CODE_SESSION_ID"] = session_id
    return env, proc


def _serve_and_park(client, world):
    lease = _lease(client, world, ports=1)
    first = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                            timeout=120))
    _ok(client.call("lease_park", {"lease_token": lease["token"], "run_id": RUN}))
    deadline = time.monotonic() + 15
    while _alive(first["server_pid"]) and time.monotonic() < deadline:
        time.sleep(0.2)
    return lease


def test_a_parked_lease_is_found_with_its_token_by_its_owner_only_and_served_by_its_owner_only(
        client, world):
    """(Resuming is 50-instance-spinup.sh + allocator `resume` territory, exercised with a real
    listening stub in tests/test_resume_never_strands_a_server.py; this stub world's server is a
    bare `sleep`, which `resume` rightly refuses to adopt.)

    The live repro: another session lists every lease, then asks lease_find for the parked one -
    guessing the owner's run - and would adopt + release it with what came back. Neither listing
    nor finding may hand it the token or the owner run while the owning session lives, and serving
    re-anchors a parked lease onto the server that serves it, so a parked lease recorded by another
    session is refused by name until the owner run lease_adopt-s it (which checks the run)."""
    lease = _serve_and_park(client, world)
    # No run named: the token is not handed out; the owner's run gets it.
    stranger = _ok(client.call("lease_find", {"series": SERIES, "state": "parked", "cwd": str(world["work"])}))
    assert stranger["found"] is True and stranger["lease"]["token"] is None
    assert stranger["lease"]["run_id"] is None and stranger["lease"]["token_prefix"] == lease["token"][:8]
    assert stranger["lease"]["served"] is False and stranger["lease"]["url"] is None
    owner = _ok(client.call("lease_find", {"series": SERIES, "state": "parked", "run_id": RUN,
                                           "cwd": str(world["work"])}))["lease"]
    assert owner["token"] == lease["token"] and owner["yours"] is True and owner["run_id"] == RUN

    before = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
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
            err = _err(foreign.call("instance_serve", {"lease_token": lease["token"],
                                                       "cwd": str(world["work"])}, timeout=120))
            assert err["code"] == "LEASE_NOT_ADOPTED"
            assert "lease_adopt" in err["remedy"] and "instance_serve" in err["remedy"]
            after = next(lz for lz in _registry(world) if lz["token"] == lease["token"])
            assert after == before, "a refused serve must not touch the lease"

            # The owning session serves its own parked lease without adopting.
            res = client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                              timeout=120)
            assert res["isError"] is False or structured(res)["error"]["code"] != "LEASE_NOT_ADOPTED"

            # Once the owner run adopts it, serving is past the gate: whatever the (stub) resume
            # says, it is no longer LEASE_NOT_ADOPTED.
            _ok(foreign.call("lease_adopt", {"lease_token": lease["token"], "run_id": RUN}))
            res = foreign.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                               timeout=120)
            assert res["isError"] is False or structured(res)["error"]["code"] != "LEASE_NOT_ADOPTED"
            _ok(foreign.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    finally:
        proc.kill()
        proc.wait()


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
