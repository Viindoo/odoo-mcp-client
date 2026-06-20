"""Behavioral tests for step-45 (venv) and step-50 (instance spinup) hardening.

Business rules protected:
  - step 45: python field is recorded in instances.toml ONLY when
    `python -c "import odoo"` exits 0 inside the new venv. An empty venv must
    NOT silently poison step 50 with an un-importable interpreter.
  - step 45: --requirements accepts multiple values (repeatable flag).
  - step 50: preflight validation runs BEFORE launching the server process. A
    python that cannot `import odoo` must produce a LOUD actionable error and
    exit non-zero WITHOUT spawning an Odoo process and WITHOUT entering the
    poll-until-HTTP-200 loop.

All tests use stub binaries on a synthetic PATH - no network, no real postgres,
no real Python venv, no real Odoo install required. Offline and deterministic.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEP45 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "45-venv.sh"
)
STEP50 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "50-instance-spinup.sh"
)
ALLOC = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)


# ---------------------------------------------------------------------------
# helpers - stub builders
# ---------------------------------------------------------------------------

def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _make_instances_toml(tmp_path: Path, series: str = "17.0") -> Path:
    """Minimal instances.toml that step 45 can update."""
    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "{series}"
            python = ""
            http_port = 8069
            db_name = "odoo"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "/fake/core/addons:/fake/addons"
        """),
        encoding="utf-8",
    )
    return toml


def _make_fake_venv(tmp_path: Path, *, odoo_importable: bool) -> Path:
    """Return a fake venv dir whose bin/python stub succeeds or fails on `import odoo`.

    Strategy: the stub only intercepts `-c "import odoo"`; all other invocations
    are passed to the REAL python3 so that inline Python snippets in the script
    (TOML update, instances_io.py, etc.) work correctly.
    """
    venv_dir = tmp_path / "fake-venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)

    real_py3 = shutil.which("python3") or "/usr/bin/python3"

    if odoo_importable:
        # `-c "import odoo"` -> exit 0; everything else -> real python3
        py_body = textwrap.dedent(f"""\
            if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 0; fi
            exec {real_py3} "$@"
        """)
    else:
        # `-c "import odoo"` -> exit 1; everything else -> real python3
        py_body = textwrap.dedent(f"""\
            if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 1; fi
            exec {real_py3} "$@"
        """)
    _write_stub(bin_dir / "python", py_body)
    _write_stub(bin_dir / "pip", "exit 0\n")
    return venv_dir


def _make_step45_stub_bin(tmp_path: Path, fake_venv_dir: Path) -> Path:
    """Stub PATH bin dir with minimal tools step 45 needs (uv stub).

    The uv stub skips actual venv creation (fake-venv already exists)
    and logs pip install calls to a log file.
    """
    bind = tmp_path / "bin"
    bind.mkdir(exist_ok=True)
    pip_log = tmp_path / "pip.log"
    # uv stub: 'uv venv <path>' is a no-op (venv already in place);
    # 'uv pip install ...' logs the call and exits 0.
    _write_stub(
        bind / "uv",
        textwrap.dedent(f"""\
            case "$1" in
                venv)
                    # No-op: fake venv already at the target path.
                    exit 0 ;;
                pip)
                    echo "uv pip $*" >> "{pip_log}"
                    exit 0 ;;
                *) exit 0 ;;
            esac
        """),
    )
    return bind, pip_log


def _run_step45(
    tmp_path: Path,
    bind: Path,
    instances_toml: Path,
    venv_path: Path,
    *,
    series: str = "17.0",
    extra_args: list | None = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(instances_toml)
    env["ODOO_AI_DIR"] = str(tmp_path / "odoo-ai")
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    cmd = ["bash", str(STEP45), "create-venv", "--series", series,
           "--tool", "uv", "--path", str(venv_path)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------
# step 45 tests
# ---------------------------------------------------------------------------

@requires_bash
def test_step45_verifies_import_odoo_before_recording_python(tmp_path):
    """When venv python can `import odoo`, the python field MUST be recorded."""
    toml = _make_instances_toml(tmp_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_importable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")

    # The script must succeed and record the python path in instances.toml.
    assert res.returncode == 0, (
        f"Expected success.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    # python field must be set to the venv's bin/python path (not blank "")
    assert 'python = ""' not in content, (
        f"python field was NOT recorded despite odoo being importable.\nTOML:\n{content}"
    )
    assert "bin/python" in content, (
        f"Expected venv python path recorded in TOML.\nTOML:\n{content}"
    )


@requires_bash
def test_step45_empty_venv_does_not_record_python(tmp_path):
    """When venv python cannot `import odoo`, step 45 must NOT record python and must exit non-zero."""
    toml = _make_instances_toml(tmp_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_importable=False)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")
    out = res.stdout + res.stderr

    # Must exit non-zero.
    assert res.returncode != 0, (
        f"Expected non-zero exit when import odoo fails.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # Must not record the python field.
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when import odoo fails.\nTOML:\n{content}"
    )
    # Must print an actionable error message mentioning the failure.
    assert "import odoo" in out.lower() or "not recorded" in out.lower(), (
        f"Expected actionable error mentioning 'import odoo'.\nOutput:\n{out}"
    )


@requires_bash
def test_step45_multi_requirements_all_installed(tmp_path):
    """--requirements is repeatable; each file must be installed in order."""
    toml = _make_instances_toml(tmp_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_importable=True)
    bind, pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    # Create two distinct requirements files.
    req1 = tmp_path / "req-core.txt"
    req2 = tmp_path / "req-addons.txt"
    req1.write_text("# core requirements\n", encoding="utf-8")
    req2.write_text("# addon requirements\n", encoding="utf-8")

    res = _run_step45(
        tmp_path, bind, toml, venv_dir, series="17.0",
        extra_args=["--requirements", str(req1), "--requirements", str(req2)],
    )
    out = res.stdout + res.stderr

    assert res.returncode == 0, (
        f"Expected success with multiple --requirements.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    assert pip_log.exists(), f"uv pip install was never called.\nOutput:\n{out}"
    logged = pip_log.read_text(encoding="utf-8")
    assert str(req1) in logged, f"req1 not installed.\nlogged:\n{logged}\nout:\n{out}"
    assert str(req2) in logged, f"req2 not installed.\nlogged:\n{logged}\nout:\n{out}"


# ---------------------------------------------------------------------------
# step 50 tests
# ---------------------------------------------------------------------------

def _make_step50_toml(tmp_path: Path, *, series: str = "17.0", py_path: str) -> Path:
    """instances.toml for step 50 (source mode).

    py_path points to the fake venv python stub that controls import odoo behavior.
    The addons_path is a real directory (we create it) so instances_io can be loaded.
    """
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    toml = tmp_path / "instances50.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "{series}"
            python = "{py_path}"
            http_port = 18069
            db_name = "odoo_test"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{fake_addons}"
        """),
        encoding="utf-8",
    )
    return toml


def _make_step50_fake_py(tmp_path: Path, *, odoo_importable: bool) -> Path:
    """Standalone fake python binary (not inside a venv dir) for step 50 tests.

    Passes through all calls to real python3 EXCEPT `-c "import odoo"` which
    exits 0 or 1 based on odoo_importable.
    """
    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    bin_dir = tmp_path / "fake-py-bin"
    bin_dir.mkdir(exist_ok=True)
    fake_py = bin_dir / "python"
    if odoo_importable:
        body = textwrap.dedent(f"""\
            if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 0; fi
            exec {real_py3} "$@"
        """)
    else:
        body = textwrap.dedent(f"""\
            if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 1; fi
            exec {real_py3} "$@"
        """)
    _write_stub(fake_py, body)
    return fake_py


@requires_bash
def test_step50_validates_python_imports_odoo_before_launch(tmp_path):
    """When python cannot `import odoo`, step 50 must exit non-zero BEFORE launching odoo-bin.

    The test uses a fake `python` interpreter (pointed to by the instance's `python`
    field in instances.toml) that fails `import odoo`. The system python3 on PATH is
    left real so that instances_io.py (called by _read_instance) works correctly.
    """
    # Fake python that FAILS import odoo (but passes through instances_io calls to real py3)
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=False)

    # Fake odoo-bin (records launch attempts)
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "fake-core" / "odoo-bin"
    odoo_launch_log = tmp_path / "odoo-launch.log"
    _write_stub(
        fake_bin,
        f'echo "odoo-bin launched $*" >> "{odoo_launch_log}"\nsleep 999\n',
    )

    # Build stub bin dir: only curl is stubbed; python3 stays real (for instances_io)
    bind = tmp_path / "bin50"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "000"\n')

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py))

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "3"
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(fake_bin)

    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    out = res.stdout + res.stderr

    # Must exit non-zero
    assert res.returncode != 0, (
        f"Expected non-zero exit when python cannot import odoo.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )

    # Must print a LOUD, actionable error
    assert "PREFLIGHT" in out or "import odoo" in out.lower(), (
        f"Expected preflight/import-odoo error message.\nOutput:\n{out}"
    )

    # Must NOT have launched odoo-bin (no poll stage reached)
    assert not odoo_launch_log.exists(), (
        f"odoo-bin was launched despite import odoo preflight failure.\n"
        f"launch log: {odoo_launch_log.read_text()}\nOutput:\n{out}"
    )
    # Confirm the poll loop was not entered (no "Polling" in output)
    assert "Polling" not in out, (
        f"Step 50 entered the poll loop despite preflight failure.\nOutput:\n{out}"
    )


# ---------------------------------------------------------------------------
# step 50 <-> allocator: shared-lease registration of the live render target
# (no Postgres / no network; the 'odoo-bin' launch is faked by the py stub).
# ---------------------------------------------------------------------------
def _alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def _leases_at(home: Path) -> list:
    reg = home / "runtime" / "leases.json"
    if not reg.exists():
        return []
    return json.loads(reg.read_text(encoding="utf-8")).get("leases", [])


def _make_step50_spinup_env(tmp_path: Path, *, curl_mode: str):
    """A source-mode step-50 scenario whose preflights PASS and whose 'odoo-bin'
    launch is faked by the python stub (logs the launch, then `exec sleep` to
    stay alive with a clean pid). curl_mode: 'up' (always 200), 'down' (always
    000), 'up_after_launch' (000 on the first probe, 200 thereafter)."""
    launch_log = tmp_path / "odoo-launch.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    # `-c "import odoo"` -> ok; any other call (the launch) -> log + stay alive.
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 0; fi
        echo "odoo-bin launched $*" >> "{launch_log}"
        exec sleep 15
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _write_stub(odoo_bin, "exit 0\n")  # only needs to be executable for _find_odoo_bin

    bind = tmp_path / "bin50"
    bind.mkdir(exist_ok=True)
    if curl_mode == "up":
        _write_stub(bind / "curl", 'echo "200"\n')
    elif curl_mode == "down":
        _write_stub(bind / "curl", 'echo "000"\n')
    else:  # up_after_launch: 000 on the first probe, 200 once the server "launched"
        cnt = tmp_path / "curl.count"
        _write_stub(bind / "curl", textwrap.dedent(f"""\
            n="$(cat "{cnt}" 2>/dev/null || echo 0)"
            echo $((n + 1)) > "{cnt}"
            if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
        """))
    _write_stub(bind / "pg_isready", "exit 0\n")  # reachable -> skip the real-PG preflight

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py))
    home = tmp_path / "odoo-ai-home"
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(home)
    env["SPINUP_TIMEOUT"] = "3"
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(odoo_bin)
    return env, home, launch_log


def _run_step50(env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        capture_output=True, text=True, env=env, timeout=30,
    )


@requires_bash
def test_step50_registers_shared_lease_after_server_up(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert launch_log.exists(), f"odoo-bin must have launched\n{out}"
    shared = [lz for lz in _leases_at(home) if lz.get("mode") == "shared"]
    assert len(shared) == 1, f"step 50 must register exactly one shared lease\n{_leases_at(home)}"
    lz = shared[0]
    assert lz["series"] == "17.0"
    assert lz["ports"] == [18069], "the lease records the actual bound port"
    assert lz["drop_on_release"] is False, "the shared render lease must NEVER own the declared DB"
    pid = lz["owner"]["pid"]
    assert pid and _alive(pid), "the live server pid is recorded (for gc + cross-session discovery)"
    os.kill(int(pid), signal.SIGTERM)  # reap the backgrounded sleep


@requires_bash
def test_step50_attaches_to_existing_shared_lease_without_relaunch(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up")
    # Pre-seed a LIVE shared lease (pid = this pytest process, which is alive).
    pre = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0", "--mode", "shared",
         "--port", "18069", "--db-name", "odoo_test", "--pid", str(os.getpid())],
        capture_output=True, text=True, env=env,
    )
    assert pre.returncode == 0, pre.stderr
    assert len(_leases_at(home)) == 1

    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "already up" in out, f"step 50 must take the already-up path\n{out}"
    assert not launch_log.exists(), f"step 50 must NOT launch a second odoo-bin\n{out}"
    shared = [lz for lz in _leases_at(home) if lz.get("mode") == "shared"]
    assert len(shared) == 1, "attach must not duplicate the shared lease row"
    assert shared[0]["owner"]["pid"] == os.getpid(), "attach must not overwrite the live server pid"


@requires_bash
def test_step50_leaves_no_shared_lease_when_server_never_comes_up(tmp_path):
    env, home, _ = _make_step50_spinup_env(tmp_path, curl_mode="down")
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a never-ready spin-up must fail\n{out}"
    assert _leases_at(home) == [], (
        "a failed spin-up must leave NO shared lease (registration happens only after the server is up)"
    )


@requires_bash
def test_step50_degrades_to_plain_spinup_without_allocator(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    env["ODOO_AI_ALLOCATOR"] = ""  # disable allocator coordination
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "is up:" in out, f"the server must still spin up and print its URL\n{out}"
    assert launch_log.exists(), "the server must still launch when the allocator is disabled"
    assert _leases_at(home) == [], "with the allocator disabled, NO lease is written"
    # The degraded path leaves a short backgrounded `sleep` (no lease records its
    # pid); it is detached and self-reaps, so it does not block the suite.


# ---------------------------------------------------------------------------
# WI-4 (a): persistent log path under ~/.odoo-ai/logs/ + parseable LOG_PATH=
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_apply_writes_log_under_odoo_ai_home(tmp_path):
    """apply must write the Odoo log to <ODOO_AI_HOME>/.odoo-ai/logs/<db>-<ts>.log
    and emit a parseable 'LOG_PATH=<path>' line on stdout so a calling agent
    can capture the log location without screen-scraping.
    """
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50(env)
    out = res.stdout + res.stderr

    assert res.returncode == 0, f"Expected success.\nstdout: {res.stdout}\nstderr: {res.stderr}"

    # 1. A parseable LOG_PATH= line must appear on stdout.
    log_path_lines = [line for line in res.stdout.splitlines() if line.startswith("LOG_PATH=")]
    assert len(log_path_lines) == 1, (
        f"Expected exactly one LOG_PATH= line on stdout.\nstdout:\n{res.stdout}"
    )

    log_path = Path(log_path_lines[0].split("=", 1)[1])

    # 2. The path must be inside ODOO_AI_HOME/logs/ (ODOO_AI_HOME IS the .odoo-ai
    #    dir; .odoo-ai is appended only in the HOME fallback).
    expected_dir = home / "logs"
    assert log_path.parent == expected_dir, (
        f"LOG_PATH must be under {expected_dir}, got {log_path.parent}"
    )

    # 3. The filename encodes the db name and a UTC timestamp.
    assert log_path.name.startswith("odoo_test-"), (
        f"Log filename must start with the db name 'odoo_test-', got: {log_path.name}"
    )
    assert log_path.suffix == ".log", (
        f"Log file must have .log suffix, got: {log_path.suffix}"
    )

    # 4. The log file must actually exist (Odoo output was redirected there).
    assert log_path.exists(), (
        f"LOG_PATH file {log_path} does not exist (redirect failed?)"
    )


# ---------------------------------------------------------------------------
# WI-4 (b): port config key - xmlrpc_port for v8/9/10, http_port for v11+
# ---------------------------------------------------------------------------

def _make_step50_toml_for_series(tmp_path: Path, series: str) -> tuple:
    """Return (toml_path, fake_py_path, env) for a source-mode step-50 scenario
    where preflights pass and odoo-bin is a stub that logs launch args.
    The scenario does NOT reach the poll step (curl always 000) - we only care
    about the generated conf, not whether the server comes up.
    """
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=True)

    fake_core = tmp_path / "fake-core"
    fake_addons = fake_core / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = fake_core / "odoo-bin"
    _write_stub(fake_bin, "exit 0\n")

    toml = tmp_path / f"instances-{series.replace('.', '_')}.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "{series}"
            python = "{fake_py}"
            http_port = 18069
            db_name = "odoo_test"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{fake_addons}"
        """),
        encoding="utf-8",
    )

    bind = tmp_path / f"bin-{series.replace('.', '_')}"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "000"\n')
    _write_stub(bind / "pg_isready", "exit 0\n")

    home = tmp_path / f"home-{series.replace('.', '_')}"
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(home)
    env["SPINUP_TIMEOUT"] = "3"
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(fake_bin)
    env["ODOO_AI_ALLOCATOR"] = ""  # skip lease registration

    return toml, fake_py, env



@requires_bash
def test_step50_conf_uses_xmlrpc_port_for_legacy_series(tmp_path):
    """For series 8.0, 9.0, 10.0 the generated odoo.conf must use xmlrpc_port;
    for 17.0 it must use http_port.

    Strategy: use an 'up_after_launch' curl stub (first probe 000, second+ 200)
    so the script enters the 'source' branch, generates a conf, and launches
    odoo-bin. Apply succeeds (HTTP 200 on the 2nd poll) and the conf is NOT
    cleaned up (cleanup only on poll-timeout). We then read the conf from the
    path printed on stdout.
    """
    results = {}
    for series in ("8.0", "9.0", "10.0", "17.0"):
        series_tmp = tmp_path / series.replace(".", "_")
        series_tmp.mkdir()
        _, _, env = _make_step50_toml_for_series(series_tmp, series)
        # Replace the curl stub with an up_after_launch variant:
        # first probe -> 000 (triggers launch), second probe -> 200 (poll succeeds).
        bind = series_tmp / f"bin-{series.replace('.', '_')}"
        cnt = series_tmp / "curl.count"
        _write_stub(bind / "curl", textwrap.dedent(f"""\
            n="$(cat "{cnt}" 2>/dev/null || echo 0)"
            echo $((n + 1)) > "{cnt}"
            if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
        """))

        res = subprocess.run(
            ["bash", str(STEP50), "apply", "--version", series],
            capture_output=True, text=True, env=env, timeout=30,
        )
        out = res.stdout + res.stderr
        assert res.returncode == 0, (
            f"Expected success for series={series}.\nout:\n{out}"
        )
        # Extract the conf path from output.
        conf_lines = [
            line for line in out.splitlines()
            if "Generated temp conf:" in line
        ]
        assert conf_lines, (
            f"No 'Generated temp conf' line for series={series}.\nout:\n{out}"
        )
        conf_path = conf_lines[0].split("Generated temp conf:")[-1].strip()
        assert Path(conf_path).exists(), (
            f"Conf file {conf_path} does not exist for series={series} "
            f"(should NOT be cleaned up when apply succeeds)"
        )
        results[series] = Path(conf_path).read_text(encoding="utf-8")

    for series in ("8.0", "9.0", "10.0"):
        conf = results[series]
        assert "xmlrpc_port" in conf, (
            f"series {series}: expected 'xmlrpc_port' in conf, got:\n{conf}"
        )
        assert "http_port" not in conf, (
            f"series {series}: 'http_port' must NOT appear in conf (it's xmlrpc_port for <v11), got:\n{conf}"
        )

    conf17 = results["17.0"]
    assert "http_port" in conf17, (
        f"series 17.0: expected 'http_port' in conf, got:\n{conf17}"
    )
    assert "xmlrpc_port" not in conf17, (
        f"series 17.0: 'xmlrpc_port' must NOT appear in conf, got:\n{conf17}"
    )


# ---------------------------------------------------------------------------
# Fix 5: --dev=all version gate (v8/v9 must NOT get --dev=all; v10+ must)
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_dev_flag_gated_by_version(tmp_path):
    """series 8.0 and 9.0 must NOT include '--dev=all' in the launch command;
    series 17.0 MUST include '--dev=all'.

    --dev=all is a string-valued flag introduced in v10; v9 has only a boolean
    --dev and v8 has no --dev at all. Passing --dev=all to either would raise an
    optparse error and prevent Odoo from starting.

    Strategy: identical to test_step50_conf_uses_xmlrpc_port_for_legacy_series -
    use an up_after_launch curl stub so the script generates the launch command and
    succeeds. Capture the 'Launching:' line from stdout and check --dev=all presence.
    """
    results = {}
    for series in ("8.0", "9.0", "17.0"):
        series_tmp = tmp_path / series.replace(".", "_")
        series_tmp.mkdir()
        _, _, env = _make_step50_toml_for_series(series_tmp, series)
        # up_after_launch: first probe 000 (trigger launch), second+ 200 (success).
        bind = series_tmp / f"bin-{series.replace('.', '_')}"
        cnt = series_tmp / "curl.count"
        _write_stub(bind / "curl", textwrap.dedent(f"""\
            n="$(cat "{cnt}" 2>/dev/null || echo 0)"
            echo $((n + 1)) > "{cnt}"
            if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
        """))

        res = subprocess.run(
            ["bash", str(STEP50), "apply", "--version", series],
            capture_output=True, text=True, env=env, timeout=30,
        )
        out = res.stdout + res.stderr
        assert res.returncode == 0, (
            f"Expected success for series={series}.\nout:\n{out}"
        )
        # Capture the 'Launching:' diagnostic line.
        launch_lines = [line for line in out.splitlines() if "Launching:" in line]
        assert launch_lines, (
            f"No 'Launching:' line for series={series}.\nout:\n{out}"
        )
        results[series] = launch_lines[0]

    # v8 and v9: --dev=all must NOT appear.
    for series in ("8.0", "9.0"):
        assert "--dev=all" not in results[series], (
            f"series {series}: '--dev=all' must NOT appear in launch command "
            f"(--dev=all requires v10+); got: {results[series]!r}"
        )

    # v17: --dev=all must appear.
    assert "--dev=all" in results["17.0"], (
        f"series 17.0: '--dev=all' must appear in launch command; "
        f"got: {results['17.0']!r}"
    )
