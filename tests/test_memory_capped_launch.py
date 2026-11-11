"""The memory-capped launcher: a child that exceeds its cap dies ALONE.

Every process the plugin starts shares the terminal's systemd scope with `claude`; when the kernel
OOM-kills any one of them systemd stops the whole unit. `run_memory_capped` / `exec_memory_capped`
(scripts/lib/run_bounded.sh, also `bash run_bounded.sh capped <cmd>`) run a command so that the
memory cap - the value resource_limits.sh already resolves, ODOO_AI_LIMIT_MEMORY_HARD - kills that
command and nothing else: in a transient systemd user scope (MemoryMax, no swap) where the user
manager can enforce one, under an address-space limit elsewhere.

Real processes throughout. A test that needs a systemd user manager that enforces MemoryMax skips
with the reason where the host has none; the fallback tests hide systemd with PATH or a stub.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from conftest import farm_path, real_python3

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_local_mcp_harness import McpClient, hermetic_env, import_package  # noqa: E402

import_package()
from odoo_local import jobs  # noqa: E402

import test_odoo_local_mcp_i18n_export as i18n_tests  # noqa: E402
from test_odoo_local_mcp_i18n_export import i18n  # noqa: E402,F401  (fixture)
from test_odoo_local_mcp_instance import (SERIES, _build, _lease, _ok, _wait, client, world)  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "run_bounded.sh"

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX process groups and shell")

CAP = 256 * 1024 * 1024          # the small cap every test lowers the plugin's limit to
BIG_MB = 900                     # a child that allocates this much is far past CAP
PY = real_python3()

# Allocate BIG_MB of RESIDENT memory (every page touched), then report it.
ALLOCATE = ("import sys\n"
            "n = %d * 1024 * 1024\n"
            "b = bytearray(n)\n"
            "b[::4096] = b'\\x01' * len(range(0, n, 4096))\n"
            "print('allocated')\n" % BIG_MB)
# Report the memory.max / memory.swap.max of the cgroup this process runs in.
CGROUP_LIMITS = ("import re\n"
                 "cg = re.search(r'^0::(.*)$', open('/proc/self/cgroup').read(), re.M).group(1)\n"
                 "d = '/sys/fs/cgroup' + cg\n"
                 "print(open(d + '/memory.max').read().strip(), open(d + '/memory.swap.max').read().strip())\n")


def _scope_enforces_memory():
    """(usable, reason): can THIS host's systemd user manager start a scope whose MemoryMax holds?
    Asked directly, independent of the helper under test."""
    if not shutil.which("systemd-run"):
        return False, "no systemd-run on PATH"
    probe = ("import re; cg = re.search(r'^0::(.*)$', open('/proc/self/cgroup').read(), re.M).group(1);"
             " print(open('/sys/fs/cgroup' + cg + '/memory.max').read().strip())")
    try:
        done = subprocess.run(
            ["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=%d" % CAP, "-p", "MemorySwapMax=0",
             PY, "-c", probe], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "systemd-run failed to run: %s" % exc
    if done.returncode != 0 or done.stdout.strip() != str(CAP):
        return False, "no systemd user manager that enforces MemoryMax (rc=%s, memory.max=%r)" % (
            done.returncode, done.stdout.strip())
    return True, ""


_SCOPE_OK, _SCOPE_WHY = _scope_enforces_memory()
needs_scope = pytest.mark.skipif(not _SCOPE_OK, reason=_SCOPE_WHY or "systemd user scope available")


@pytest.fixture(scope="session")
def no_systemd_path(path_farm):
    """A PATH with the host's tools EXCEPT systemd-run - the macOS / container shape."""
    path = farm_path(path_farm(drop=("systemd-run",)))
    probe = subprocess.run(["bash", "-c", "command -v systemd-run"], env=dict(os.environ, PATH=path),
                           capture_output=True, text=True)
    assert probe.returncode != 0, "premise: systemd-run is not reachable"
    return path


def _env(cap=CAP, path=None, **extra):
    env = dict(os.environ)
    env.pop("_RUN_CAPPED_EXEC", None)
    if cap is None:
        env.pop("ODOO_AI_LIMIT_MEMORY_HARD", None)
    else:
        env["ODOO_AI_LIMIT_MEMORY_HARD"] = str(cap)
    if path is not None:
        env["PATH"] = path
    env.update(extra)
    return env


def _sourced(args, flags="", env=None, stdin=None, timeout=60):
    """Call `run_memory_capped` from a shell that has sourced the helper, as a script that keeps
    going afterwards does. Prints `launcher-alive rc=<status>` once the command returns."""
    script = f'. "{HELPER}"\nrun_memory_capped {flags} "$@"\nrc=$?\necho "launcher-alive rc=$rc"\n'
    return subprocess.run(["bash", "-c", script, "bash", *args], env=env or _env(), input=stdin,
                          capture_output=True, text=True, timeout=timeout)


def _cli(args, flags=(), env=None, stdin=None, timeout=60):
    """The shell front door an agent calls: `bash run_bounded.sh capped <cmd>`."""
    return subprocess.run(["bash", str(HELPER), "capped", *flags, *args], env=env or _env(), input=stdin,
                          capture_output=True, text=True, timeout=timeout)


def _alive_rc(proc):
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("launcher-alive")]
    assert line, "the launcher did not survive its child: %r %r" % (proc.stdout, proc.stderr)
    return int(line[-1].split("rc=")[1])


# --------------------------------------------------------------------------- #
# systemd user scope: the child dies alone
# --------------------------------------------------------------------------- #
@posix_only
@needs_scope
def test_a_child_past_the_cap_is_killed_alone_and_the_launcher_sees_137():
    done = _sourced([PY, "-c", ALLOCATE])
    assert _alive_rc(done) == 137, done
    assert "allocated" not in done.stdout


@posix_only
@needs_scope
def test_the_shell_front_door_ends_with_the_kill_signal():
    """The front door REPLACES itself with the command, so its caller sees the command's own death:
    SIGKILL - status 137 to a shell, -9 to a program reading the wait status."""
    done = _cli([PY, "-c", ALLOCATE])
    assert done.returncode in (137, -signal.SIGKILL), done
    assert "allocated" not in done.stdout


@posix_only
@needs_scope
def test_a_child_within_the_cap_runs_normally_and_its_exit_code_passes_through():
    done = _sourced(["sh", "-c", "echo out; echo err >&2; cat; exit 7"], stdin="piped\n")
    assert _alive_rc(done) == 7, done
    assert done.stdout.startswith("out\npiped\n") and done.stderr == "err\n", done


@posix_only
@needs_scope
def test_the_child_runs_in_a_scope_of_its_own_with_the_cap_and_no_swap():
    """The cap is the one the plugin already resolves, held by the kernel for THIS child."""
    done = _cli([PY, "-c", CGROUP_LIMITS])
    assert done.returncode == 0, done
    assert done.stdout.split() == [str(CAP), "0"], done


@posix_only
def test_arguments_reach_the_command_exactly_as_given():
    """Recent systemd-run applies service-style `$` expansion to a scope's command line (`$$` -> `$`,
    `${NAME}` -> systemd-run's own value): a password, a regex or a path in odoo-bin's arguments
    would arrive rewritten."""
    args = ["a$$b", "p${HOME}q", "$HOME", "x$y", "%h", "100%", "two words", ""]
    script = "import sys; print(repr(sys.argv[1:]))"
    for run in (_cli, _sourced):
        done = run([PY, "-c", script, *args])
        assert done.stdout.splitlines()[0] == repr(args), (run.__name__, done)


@posix_only
@needs_scope
def test_the_cap_follows_the_plugins_existing_memory_limit_value():
    other = CAP * 2
    done = _cli([PY, "-c", CGROUP_LIMITS], env=_env(cap=other))
    assert done.stdout.split()[0] == str(other), done


@posix_only
@needs_scope
def test_the_commands_process_group_is_the_launchers_so_a_group_signal_still_reaches_it(tmp_path):
    """The scope changes the cgroup, never the session: the caller's killpg is how jobs, the
    allocator and the timeouts stop a server."""
    pidfile = tmp_path / "pid"
    proc = subprocess.Popen(
        ["bash", str(HELPER), "capped", "sh", "-c", f"echo $$ > {pidfile}; exec sleep 60"],
        env=_env(), start_new_session=True, stdin=subprocess.DEVNULL)
    try:
        _wait_for(pidfile)
        child = int(pidfile.read_text())
        assert child == proc.pid, "the capped command REPLACES the launcher: same pid"
        assert os.getpgid(child) == proc.pid
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
        assert proc.returncode == -signal.SIGTERM
    finally:
        _reap(proc)


# --------------------------------------------------------------------------- #
# without a usable systemd: an address-space limit, never a failed or slow launch
# --------------------------------------------------------------------------- #
@posix_only
def test_without_systemd_a_child_within_the_cap_runs_and_its_exit_code_passes_through(no_systemd_path):
    done = _sourced(["sh", "-c", "echo out; cat; exit 7"], env=_env(path=no_systemd_path), stdin="piped\n")
    assert _alive_rc(done) == 7, done
    assert done.stdout.startswith("out\npiped\n"), done


@posix_only
def test_without_systemd_a_child_past_the_cap_fails_inside_itself_and_the_launcher_survives(no_systemd_path):
    done = _sourced([PY, "-c", ALLOCATE], env=_env(path=no_systemd_path))
    assert _alive_rc(done) != 0, done
    assert "allocated" not in done.stdout


@posix_only
def test_a_systemd_that_cannot_start_a_scope_falls_back_instead_of_failing_the_launch(tmp_path, no_systemd_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "systemd-run").write_text("#!/bin/sh\necho 'Failed to connect to bus' >&2\nexit 1\n")
    (stub / "systemd-run").chmod(0o755)
    path = os.pathsep.join([str(stub), no_systemd_path])
    ok = _sourced(["sh", "-c", "exit 5"], env=_env(path=path))
    assert _alive_rc(ok) == 5, ok
    over = _sourced([PY, "-c", ALLOCATE], env=_env(path=path))
    assert _alive_rc(over) != 0 and "allocated" not in over.stdout, over


@posix_only
def test_a_systemd_that_accepts_the_scope_but_cannot_enforce_the_cap_is_not_trusted(tmp_path, no_systemd_path):
    """A user manager without the memory controller starts the scope and ignores MemoryMax: the
    child would run uncapped. It must get the address-space limit instead."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "systemd-run").write_text(textwrap.dedent("""\
        #!/bin/bash
        while [[ "${1:-}" == -* ]]; do
            case "$1" in -p) shift 2 ;; --) shift; break ;; *) shift ;; esac
        done
        exec "$@"
        """))
    (stub / "systemd-run").chmod(0o755)
    env = _env(path=os.pathsep.join([str(stub), no_systemd_path]))
    over = _sourced([PY, "-c", ALLOCATE], env=env)
    assert _alive_rc(over) != 0 and "allocated" not in over.stdout, over


# --------------------------------------------------------------------------- #
# the cap is the plugin's existing limit, including its escape hatch
# --------------------------------------------------------------------------- #
@posix_only
@pytest.mark.parametrize("value", ["0", ""])
def test_zero_or_empty_limit_means_uncapped_on_every_path(value, no_systemd_path):
    for path in (None, no_systemd_path):
        done = _sourced([PY, "-c", ALLOCATE], env=_env(cap=value, path=path))
        assert _alive_rc(done) == 0 and "allocated" in done.stdout, (path, done)


@posix_only
def test_scope_only_runs_uncapped_where_no_scope_is_usable(no_systemd_path):
    """The v12+ listener has Odoo's own limit; an address-space limit there is the wrong tool."""
    done = _sourced([PY, "-c", ALLOCATE], flags="--scope-only", env=_env(path=no_systemd_path))
    assert _alive_rc(done) == 0 and "allocated" in done.stdout, done


@posix_only
@needs_scope
def test_scope_only_still_caps_where_a_scope_is_usable():
    done = _sourced([PY, "-c", ALLOCATE], flags="--scope-only")
    assert _alive_rc(done) == 137, done


@posix_only
def test_a_command_that_cannot_be_found_reports_127():
    assert _cli(["no-such-command-here"]).returncode == 127
    assert _alive_rc(_sourced(["no-such-command-here"])) == 127


@posix_only
def test_the_shell_front_door_keeps_the_wall_clock_bound():
    started = time.monotonic()
    done = subprocess.run(["bash", str(HELPER), "bounded", "1", "sleep", "30"], capture_output=True, timeout=30)
    assert done.returncode == 124 and time.monotonic() - started < 10


# --------------------------------------------------------------------------- #
# jobs: a job started through the capped launcher can still be stopped
# --------------------------------------------------------------------------- #
def _wait_for(path, timeout=20):
    deadline = time.monotonic() + timeout
    while not Path(path).exists() or not Path(path).read_text().strip():
        assert time.monotonic() < deadline, "%s never appeared" % path
        time.sleep(0.05)


def _reap(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.wait(timeout=10)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _stop_a_capped_job(tmp_path, monkeypatch, extra_env):
    monkeypatch.setenv("ODOO_AI_HOME", str(tmp_path / "home"))
    pidfile = tmp_path / "child.pid"
    rec = jobs.start(["bash", str(HELPER), "capped", "sh", "-c", f"echo $$ > {pidfile}; exec sleep 120"],
                     str(tmp_path), env=dict({"ODOO_AI_LIMIT_MEMORY_HARD": str(CAP)}, **extra_env))
    try:
        _wait_for(pidfile)
        child = int(pidfile.read_text())
        assert _alive(child) and jobs.status(rec["job_id"])["state"] == "running"
        stopped, detail = jobs.stop(rec["job_id"], grace_s=5)
        assert stopped, detail
        deadline = time.monotonic() + 10
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _alive(child), "stop() did not reach the real child"
        assert jobs.wait(rec["job_id"], 10)["state"] != "running"
    finally:
        try:
            os.killpg(rec["pid"], signal.SIGKILL)
        except OSError:
            pass


@posix_only
@needs_scope
def test_a_job_whose_command_runs_in_a_capped_scope_stops_with_its_process_group(tmp_path, monkeypatch):
    _stop_a_capped_job(tmp_path, monkeypatch, {})


@posix_only
def test_a_job_under_the_address_space_fallback_stops_with_its_process_group(tmp_path, monkeypatch, no_systemd_path):
    _stop_a_capped_job(tmp_path, monkeypatch, {"PATH": no_systemd_path})


# --------------------------------------------------------------------------- #
# wiring: the real scripts launch odoo-bin through it (builds, exports, the server)
# --------------------------------------------------------------------------- #
def _allocate_when_marked(world, mark):
    """odoo-bin allocates past the cap and is killed/fails when `mark` exists; else behaves as before."""
    body = world["behavior"].read_text(encoding="utf-8")
    world["behavior"].write_text(
        f'if [[ -f "{mark}" ]]; then exec "{PY}" -c "{ALLOCATE}"; fi\n' + body, encoding="utf-8")


def _world_env(world, path=None):
    env = world["env"](ODOO_AI_LIMIT_MEMORY_HARD=str(CAP))
    if path is not None:
        env["PATH"] = os.pathsep.join([env["PATH"].split(os.pathsep)[0], path])
    return env


@posix_only
@needs_scope
def test_a_build_past_the_cap_ends_with_odoo_bin_killed_alone_and_the_session_alive(world, tmp_path):
    mark = tmp_path / "allocate"
    _allocate_when_marked(world, mark)
    with McpClient(_world_env(world), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world)
        ok = _wait(c, _ok(_build(c, world, lease["token"]))["job_id"])
        assert ok["result"] == "success", ok
        mark.write_text("1")
        killed = _wait(c, _ok(_build(c, world, lease["token"], op="update"))["job_id"])
        assert killed["result"] != "success" and killed["exit_code"] == 137, killed
        assert _ok(c.call("lease_list", {})), "the server answers after the kill"


@posix_only
def test_a_build_past_the_cap_fails_without_systemd_too(world, tmp_path, no_systemd_path):
    mark = tmp_path / "allocate"
    _allocate_when_marked(world, mark)
    with McpClient(_world_env(world, no_systemd_path), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world)
        ok = _wait(c, _ok(_build(c, world, lease["token"]))["job_id"])
        assert ok["result"] == "success", ok
        mark.write_text("1")
        failed = _wait(c, _ok(_build(c, world, lease["token"], op="update"))["job_id"])
        assert failed["result"] != "success" and failed["exit_code"] != 0, failed


@posix_only
@needs_scope
def test_a_translation_export_is_capped_like_a_build(i18n, tmp_path):
    mark = tmp_path / "allocate-export"
    body = i18n["behavior"].read_text(encoding="utf-8")
    survived = tmp_path / "exporter-survived"
    code = ALLOCATE + f"open('{survived}', 'w').close()\n"
    marked = body.replace('if [[ -n "$out" ]]; then', 'if [[ -n "$out" ]]; then\n'
                          f'    if [[ -f "{mark}" ]]; then exec "{PY}" -c "{code}"; fi', 1)
    assert marked != body, "premise: the export branch of the stub behavior was found"
    i18n["behavior"].write_text(marked, encoding="utf-8")
    with McpClient(_world_env(i18n), i18n["work"]) as c:
        c.initialize()
        lease = i18n_tests._ready_lease(c, i18n)
        mark.write_text("1")
        done = _wait(c, _ok(i18n_tests._export(c, i18n, lease["token"]))["job_id"])
    assert done["result"] != "success", done
    assert not survived.exists(), "the exporter outlived its cap"
    assert i18n_tests._leftovers(i18n["module"] / "i18n") == []
    assert not (i18n["module"] / "i18n" / "my_mod.pot").exists()


@posix_only
@needs_scope
def test_the_served_instance_runs_in_a_scope_with_the_cap(world):
    with McpClient(_world_env(world), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)
        out = _ok(c.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                         timeout=120))
        cgroup = Path("/proc/%d/cgroup" % out["server_pid"]).read_text().strip().split("::", 1)[1]
        assert (Path("/sys/fs/cgroup" + cgroup) / "memory.max").read_text().strip() == str(CAP)
        _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": "run-instance-owner"}))
