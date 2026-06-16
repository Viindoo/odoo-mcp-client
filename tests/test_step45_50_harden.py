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
import os
import shutil
import subprocess
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
