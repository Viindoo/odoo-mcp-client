"""Behavioral tests for step-45 (venv) and step-50 (instance spinup) hardening.

Business rules protected:
  - step 45: python field is recorded in instances.toml ONLY when
    `<venv_py> <odoo-bin> --version` exits 0. An empty venv (or one whose
    deps are incomplete) must NOT silently poison step 50.
  - step 45: fails loud with an actionable message when no odoo-bin / core repo
    is present in the series' addons_path.
  - step 45: --requirements accepts multiple values (repeatable flag).
  - step 50: preflight validation runs BEFORE launching the server process. A
    python whose `<py> <odoo-bin> --version` fails must produce a LOUD
    actionable error and exit non-zero WITHOUT spawning an Odoo process and
    WITHOUT entering the poll-until-HTTP-200 loop.

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


def _make_core_dir(tmp_path: Path, series: str = "17.0") -> Path:
    """Create a minimal fake Odoo core dir with odoo-bin + requirements.txt.

    step 45's _core_root_for_series needs a dir in addons_path whose
    parent (or the dir itself) has both odoo-bin (executable) and
    requirements.txt so it can discover the core_bin path.
    """
    core = tmp_path / f"fake-core-{series.replace('.', '_')}"
    (core / "addons").mkdir(parents=True, exist_ok=True)
    # odoo-bin stub: prints a version string when called with --version
    odoo_bin = core / "odoo-bin"
    _write_stub(odoo_bin, 'echo "Odoo Server 17.0"\n')
    (core / "requirements.txt").write_text("# fake requirements\n", encoding="utf-8")
    return core


def _make_instances_toml(
    tmp_path: Path,
    series: str = "17.0",
    *,
    addons_path: str | None = None,
) -> Path:
    """Minimal instances.toml that step 45 can update.

    When addons_path is None a fake path is used (no odoo-bin present).
    Pass a real path string (e.g. from _make_core_dir) for tests that
    need the gate to find an odoo-bin.
    """
    if addons_path is None:
        addons_path = "/fake/core/addons:/fake/addons"
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
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )
    return toml


def _make_fake_venv(tmp_path: Path, *, odoo_runnable: bool) -> Path:
    """Return a fake venv dir whose bin/python stub succeeds or fails on
    `<python> <odoo-bin> --version` (the new gate).

    Strategy: the stub intercepts calls where $2 == "--version" (i.e. the
    `<venv_py> <odoo-bin> --version` gate call). All other invocations are
    passed to the REAL python3 so that inline Python snippets in the script
    (TOML update, instances_io.py, etc.) work correctly.
    """
    venv_dir = tmp_path / "fake-venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)

    real_py3 = shutil.which("python3") or "/usr/bin/python3"

    if odoo_runnable:
        # `<py> <odoo-bin> --version` -> exit 0; everything else -> real python3
        py_body = textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            exec {real_py3} "$@"
        """)
    else:
        # `<py> <odoo-bin> --version` -> exit 1; everything else -> real python3
        py_body = textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then exit 1; fi
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
def test_step45_verifies_odoo_bin_runs_before_recording_python(tmp_path):
    """When venv python can run `<py> <odoo-bin> --version`, the python field MUST be recorded."""
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")
    toml = _make_instances_toml(tmp_path, addons_path=addons_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")

    # The script must succeed and record the python path in instances.toml.
    assert res.returncode == 0, (
        f"Expected success.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    # python field must be set to the venv's bin/python path (not blank "")
    assert 'python = ""' not in content, (
        f"python field was NOT recorded despite odoo being runnable.\nTOML:\n{content}"
    )
    assert "bin/python" in content, (
        f"Expected venv python path recorded in TOML.\nTOML:\n{content}"
    )


@requires_bash
def test_step45_empty_venv_does_not_record_python(tmp_path):
    """When venv python cannot run `<py> <odoo-bin> --version`, step 45 must NOT record python."""
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")
    toml = _make_instances_toml(tmp_path, addons_path=addons_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=False)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")
    out = res.stdout + res.stderr

    # Must exit non-zero.
    assert res.returncode != 0, (
        f"Expected non-zero exit when odoo-bin --version fails.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # Must not record the python field.
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when odoo-bin --version fails.\nTOML:\n{content}"
    )
    # Must print an actionable error message mentioning the failure.
    assert "not recorded" in out.lower() or "failed" in out.lower() or "python" in out.lower(), (
        f"Expected actionable error about the failed gate.\nOutput:\n{out}"
    )


@requires_bash
def test_step45_multi_requirements_all_installed(tmp_path):
    """--requirements is repeatable; each file must be installed in order."""
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")
    toml = _make_instances_toml(tmp_path, addons_path=addons_path)
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
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


@requires_bash
def test_step45_gate_uses_odoo_bin_version_not_import(tmp_path):
    """Oracle test: stub python that PASSES `--version` but would FAIL `import odoo`.

    The gate must use `<py> <odoo-bin> --version`, NOT `<py> -c "import odoo"`.
    If python field IS recorded, gate correctly uses --version.
    If python field is NOT recorded, gate incorrectly still relies on import odoo.
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")
    toml = _make_instances_toml(tmp_path, addons_path=addons_path)

    venv_dir = tmp_path / "fake-venv-oracle"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    real_py3 = shutil.which("python3") or "/usr/bin/python3"

    # This stub: `--version` -> exit 0 (Odoo runnable); `-c "import odoo"` -> exit 1.
    # If gate still uses import odoo, it would fail -> python NOT recorded.
    # If gate uses --version, it succeeds -> python IS recorded.
    py_body = textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 1; fi
        exec {real_py3} "$@"
    """)
    _write_stub(bin_dir / "python", py_body)
    _write_stub(bin_dir / "pip", "exit 0\n")

    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)
    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")

    # Must succeed: gate uses --version which exits 0.
    assert res.returncode == 0, (
        f"Expected success (gate uses --version which passes).\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' not in content, (
        "python field must be recorded when `--version` passes, even if `import odoo` would fail "
        "(proves gate uses odoo-bin --version, not import odoo)"
    )


@requires_bash
def test_step45_fails_loud_when_core_repo_missing(tmp_path):
    """When addons_path has no dir with odoo-bin, step 45 must exit non-zero
    with a message mentioning 'core repo' or 'odoo-bin', and must NOT record python."""
    # addons_path points to a dir that exists but has NO odoo-bin.
    fake_addons = tmp_path / "addons-no-bin"
    fake_addons.mkdir(parents=True, exist_ok=True)
    toml = _make_instances_toml(tmp_path, addons_path=str(fake_addons))

    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")
    out = res.stdout + res.stderr

    assert res.returncode != 0, (
        f"Expected non-zero when core repo/odoo-bin is missing.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    assert "core repo" in out.lower() or "odoo-bin" in out.lower(), (
        f"Expected mention of 'core repo' or 'odoo-bin' in error output.\nOutput:\n{out}"
    )
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when core repo is missing.\nTOML:\n{content}"
    )


@requires_bash
def test_step45_per_profile_venv_path_and_profile_field(tmp_path):
    """With --profile minimal_17, step 45 must:
    - Place the venv at venvs/17.0-minimal_17 (not venvs/17.0).
    - Record the python field in the [[instance]] block that matches
      series=17.0 AND profile=minimal_17 (not the other profile's block).
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")

    # Two [[instance]] blocks in the same toml: minimal_17 and full_17.
    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "minimal_17"
            instance_key = "17.0:minimal_17"
            python = ""
            http_port = 8069
            db_name = "odoo_17_0_minimal_17"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"

            [[instance]]
            series = "17.0"
            profile = "full_17"
            instance_key = "17.0:full_17"
            python = ""
            http_port = 8079
            db_name = "odoo_17_0_full_17"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )

    venv_dir = tmp_path / "odoo-ai" / "venvs" / "17.0-minimal_17"
    venv_dir.mkdir(parents=True, exist_ok=True)

    venv_dir_bin = venv_dir / "bin"
    venv_dir_bin.mkdir(exist_ok=True)
    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    _write_stub(
        venv_dir_bin / "python",
        textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            exec {real_py3} "$@"
        """),
    )
    _write_stub(venv_dir_bin / "pip", "exit 0\n")

    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_DIR"] = str(tmp_path / "odoo-ai")
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    # Run with --profile minimal_17: no --path so venv path is auto-derived.
    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0",
         "--profile", "minimal_17", "--tool", "uv",
         "--path", str(venv_dir)],
        capture_output=True, text=True, env=env,
    )

    assert res.returncode == 0, (
        f"Expected success with --profile minimal_17.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )

    content = toml.read_text(encoding="utf-8")
    # The minimal_17 block must now have the python path recorded.
    # The full_17 block must still have python = "".
    blocks = content.split("[[instance]]")
    minimal_block = next((b for b in blocks if "minimal_17" in b and "full_17" not in b), "")
    full_block = next((b for b in blocks if "full_17" in b and "minimal_17" not in b), "")

    assert minimal_block, f"Could not find minimal_17 block in TOML:\n{content}"
    assert full_block, f"Could not find full_17 block in TOML:\n{content}"

    assert 'python = ""' not in minimal_block, (
        f"minimal_17 block must have python path recorded, not empty.\nBlock:\n{minimal_block}"
    )
    assert "bin/python" in minimal_block, (
        f"Expected venv python path in minimal_17 block.\nBlock:\n{minimal_block}"
    )
    assert 'python = ""' in full_block, (
        f"full_17 block must still have python='' (unmodified).\nBlock:\n{full_block}"
    )


# ---------------------------------------------------------------------------
# M1: no-profile create-venv must NOT clobber a profiled block
# ---------------------------------------------------------------------------

@requires_bash
def test_step45_no_profile_does_not_clobber_profiled_block(tmp_path):
    """create-venv without --profile must NOT write into a profiled [[instance]] block.

    Business rule (M1): when the toml has ONLY profiled blocks for series 17.0,
    running `create-venv --series 17.0` (no --profile) must fail-loud with a
    message asking for --profile. It must NOT silently record the venv path into
    the profiled block.

    This test is RED on code where `profile == "" or block_profile == profile`
    matches any block (poisoning the profiled block).
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")

    # Only ONE [[instance]] block, and it IS profiled.
    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "minimal_17"
            instance_key = "17.0:minimal_17"
            python = ""
            http_port = 8069
            db_name = "odoo_17_0_minimal_17"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )
    original_content = toml.read_text(encoding="utf-8")

    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    # Run create-venv WITHOUT --profile.
    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")
    out = res.stdout + res.stderr

    # Must exit non-zero (refuses to guess which profiled block to update).
    assert res.returncode != 0, (
        f"Expected non-zero when only profiled blocks exist and --profile not given.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # Must mention --profile in the error message.
    assert "--profile" in out or "profile" in out.lower(), (
        f"Expected message mentioning --profile in output.\nOutput:\n{out}"
    )
    # The profiled block must be UNCHANGED (python field must remain blank).
    content_after = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content_after, (
        f"profiled block must NOT have python recorded (no --profile given).\nTOML:\n{content_after}"
    )
    # Verify TOML is byte-identical to what we started with.
    assert content_after == original_content, (
        f"TOML must be unchanged when create-venv fails-loud.\nOriginal:\n{original_content}\nAfter:\n{content_after}"
    )


@requires_bash
def test_step45_no_profile_writes_unprofiled_block_when_present(tmp_path):
    """create-venv without --profile MUST record python in the unprofiled block.

    When the toml has both an unprofiled block AND a profiled block for the same
    series, create-venv --series X (no --profile) must:
    - Record python in the UNPROFILED block (block_profile == "").
    - Leave the profiled block UNCHANGED.
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")

    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            python = ""
            http_port = 8069
            db_name = "odoo_17_0"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"

            [[instance]]
            series = "17.0"
            profile = "minimal_17"
            instance_key = "17.0:minimal_17"
            python = ""
            http_port = 8079
            db_name = "odoo_17_0_minimal_17"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )

    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")

    assert res.returncode == 0, (
        f"Expected success when unprofiled block exists.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    blocks = content.split("[[instance]]")
    # Identify blocks by presence/absence of a `profile = ` line (not path strings).
    unprofiled = next(
        (b for b in blocks if "series" in b and 'profile = ' not in b), ""
    )
    profiled = next(
        (b for b in blocks if "minimal_17" in b and 'profile = "minimal_17"' in b), ""
    )

    assert unprofiled, f"Could not find unprofiled block:\n{content}"
    assert profiled, f"Could not find profiled block:\n{content}"
    assert 'python = ""' not in unprofiled, (
        f"Unprofiled block must have python recorded.\nBlock:\n{unprofiled}"
    )
    assert "bin/python" in unprofiled, (
        f"Expected venv python in unprofiled block.\nBlock:\n{unprofiled}"
    )
    assert 'python = ""' in profiled, (
        f"Profiled block must remain unchanged (python still blank).\nBlock:\n{profiled}"
    )


@requires_bash
def test_step45_per_profile_venv_path_auto_derived(tmp_path):
    """With --profile minimal_17 and NO --path, venv must be placed at
    venvs/17.0-minimal_17 (auto-derived from series + profile slug).

    L5 coverage: test_step45_per_profile_venv_path_and_profile_field passes
    --path explicitly so the auto-derive branch is never exercised there.
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")

    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "minimal_17"
            instance_key = "17.0:minimal_17"
            python = ""
            http_port = 8069
            db_name = "odoo_17_0_minimal_17"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )

    # Auto-derived venv dir: ODOO_AI_DIR/venvs/17.0-minimal_17
    # slug of "minimal_17" = "minimal_17" (already clean)
    odoo_ai_dir = tmp_path / "odoo-ai"
    expected_venv = odoo_ai_dir / "venvs" / "17.0-minimal_17"

    # Pre-create the venv dir with a python stub so uv stub no-ops and
    # the gate check finds the right python.
    expected_venv.mkdir(parents=True, exist_ok=True)
    venv_bin = expected_venv / "bin"
    venv_bin.mkdir(exist_ok=True)
    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    _write_stub(
        venv_bin / "python",
        textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            exec {real_py3} "$@"
        """),
    )
    _write_stub(venv_bin / "pip", "exit 0\n")

    bind, _pip_log = _make_step45_stub_bin(tmp_path, expected_venv)

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_DIR"] = str(odoo_ai_dir)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")

    # Run WITHOUT --path so the auto-derive branch is exercised.
    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0",
         "--profile", "minimal_17", "--tool", "uv"],
        capture_output=True, text=True, env=env,
    )

    assert res.returncode == 0, (
        f"Expected success with --profile and no --path.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # The auto-derived venv path must appear in the output.
    assert "17.0-minimal_17" in res.stdout + res.stderr, (
        f"Expected auto-derived venv path '17.0-minimal_17' in output.\nOutput:\n{res.stdout + res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' not in content, (
        f"python field must be recorded with auto-derived path.\nTOML:\n{content}"
    )
    assert "bin/python" in content, (
        f"Expected venv python path in TOML.\nTOML:\n{content}"
    )


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

    Intercepts `<py> <odoo-bin> --version` (gate call) based on odoo_importable.
    Passes through all other calls to real python3 (e.g. instances_io.py calls).
    The parameter name retains `odoo_importable` for call-site readability, but
    the stub now controls `<py> <odoo-bin> --version` behavior.
    """
    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    bin_dir = tmp_path / "fake-py-bin"
    bin_dir.mkdir(exist_ok=True)
    fake_py = bin_dir / "python"
    if odoo_importable:
        # `<py> <odoo-bin> --version` -> exit 0 (Odoo runnable)
        body = textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            exec {real_py3} "$@"
        """)
    else:
        # `<py> <odoo-bin> --version` -> exit 1 (Odoo not runnable)
        body = textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then exit 1; fi
            exec {real_py3} "$@"
        """)
    _write_stub(fake_py, body)
    return fake_py


@requires_bash
def test_step50_validates_odoo_bin_runs_before_launch(tmp_path):
    """When `<py> <odoo-bin> --version` fails, step 50 must exit non-zero BEFORE launching odoo-bin.

    The test uses a fake `python` interpreter (pointed to by the instance's `python`
    field in instances.toml) that fails `--version`. The system python3 on PATH is
    left real so that instances_io.py (called by _read_instance) works correctly.
    """
    # Fake python that FAILS `<py> <odoo-bin> --version` but passes instances_io calls
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=False)

    # Fake odoo-bin (records launch attempts - must NOT be reached)
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
        f"Expected non-zero exit when odoo-bin --version fails.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )

    # Must print a LOUD, actionable error mentioning PREFLIGHT failure
    assert "PREFLIGHT" in out or "failed" in out.lower(), (
        f"Expected PREFLIGHT error message.\nOutput:\n{out}"
    )

    # Must NOT have launched odoo-bin (no poll stage reached)
    assert not odoo_launch_log.exists(), (
        f"odoo-bin was launched despite --version preflight failure.\n"
        f"launch log: {odoo_launch_log.read_text()}\nOutput:\n{out}"
    )
    # Confirm the poll loop was not entered (no "Polling" in output)
    assert "Polling" not in out, (
        f"Step 50 entered the poll loop despite preflight failure.\nOutput:\n{out}"
    )


@requires_bash
def test_step50_gate_uses_odoo_bin_version_not_import(tmp_path):
    """Oracle test: stub python that PASSES `<py> <odoo-bin> --version` but would
    FAIL `<py> -c "import odoo"`. The preflight in step 50 must use --version, NOT
    import odoo.

    If the gate correctly uses `--version` -> preflight PASSES -> launch PROCEEDS
    (odoo-bin launch log created, poll loop entered).

    If the gate incorrectly uses `import odoo` -> preflight FAILS -> launch BLOCKED
    (odoo-bin launch log NOT created, no poll loop).

    This test is RED on any code path that still uses `import odoo` as the gate.
    """
    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    # Oracle stub: `$2 == "--version"` passes (gate check);
    # When called as `<py> <odoo-bin> -c <conf> ...` (real launch), log and exit 0
    # so odoo-bin is "launched" and the log file is created.
    # When called as `<py> -c "import odoo"` (old gate), exits 1 (odoo not importable).
    # Anything else (instances_io.py Python calls) delegates to real python3.
    py_bin_dir = tmp_path / "fake-py-oracle"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    odoo_launch_log = tmp_path / "odoo-launch.log"
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "fake-core" / "odoo-bin"
    # fake_bin is also a bash stub (needed for ODOO_BIN path).
    _write_stub(fake_bin, f'echo "odoo-bin-direct $*" >> "{odoo_launch_log}"\nexit 0\n')

    _write_stub(
        fake_py,
        textwrap.dedent(f"""\
            # Gate check: `<py> <odoo-bin> --version`
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            # Old import gate (must NOT be used by step 50): `<py> -c "import odoo"`
            if [[ "$1" == "-c" ]]; then exit 1; fi
            # Real odoo-bin launch: `<py> <odoo-bin> -c <conf> -d <db> ...`
            # Detected by: $1 is a path and $2 == "-c" (config flag).
            if [[ -f "$1" && "$2" == "-c" ]]; then
                echo "odoo-bin launched via py: $*" >> "{odoo_launch_log}"
                exit 0
            fi
            exec {real_py3} "$@"
        """),
    )

    bind = tmp_path / "bin50-oracle"
    bind.mkdir(exist_ok=True)
    # curl returns 000 on first call (server not yet up) then 200 (up).
    # This forces step 50 to launch odoo-bin before the poll loop can short-circuit.
    curl_counter = tmp_path / "curl-count.txt"
    curl_counter.write_text("0", encoding="utf-8")
    _write_stub(
        bind / "curl",
        textwrap.dedent(f"""\
            n=$(cat "{curl_counter}" 2>/dev/null || echo 0)
            n=$((n + 1))
            echo "$n" > "{curl_counter}"
            if [[ "$n" -le 1 ]]; then echo "000"; else echo "200"; fi
        """),
    )
    # pg_isready stub: simulate PG reachable so the preflight check does not
    # block the test on CI runners that have pg_isready installed but no live
    # PostgreSQL service.  This test is specifically about the --version oracle
    # gate; PG reachability is orthogonal.
    _write_stub(bind / "pg_isready", "exit 0\n")

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py))

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "10"
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(fake_bin)

    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    out = res.stdout + res.stderr

    # Gate must PASS (--version exits 0) -> launch must PROCEED.
    assert res.returncode == 0, (
        f"Expected success: gate uses --version (passes), but got non-zero.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # odoo-bin must have been launched (proves preflight did not block).
    assert odoo_launch_log.exists(), (
        f"odoo-bin was NOT launched despite --version gate passing.\nOutput:\n{out}"
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
    # `<py> <odoo-bin> --version` -> exit 0 (preflight passes); real launch -> log + stay alive.
    # The preflight call is `$2 == "--version"`; the actual launch call is not --version.
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
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
    _write_stub(fake_bin, f'echo "Odoo Server {series}"\n')

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


# ---------------------------------------------------------------------------
# F1: step 45 must verify ALL profile repos are present (not just core)
# ---------------------------------------------------------------------------

@requires_bash
def test_step45_verifies_all_profile_repos_present(tmp_path):
    """A profile's addons_path has 2 repos: core (with odoo-bin) + one addon repo.
    If the addon repo dir does NOT exist, step 45 create-venv must fail-loud
    with a message naming the missing repo, and must NOT record python.

    Business rule (B1): verifies all the profile's repos are present before
    build - 'core only' check is insufficient.

    RED on current code (which only checks that odoo-bin exists in addons_path,
    does not separately verify each repo dir in the path is present).
    """
    # Core repo (with odoo-bin) - exists
    core = _make_core_dir(tmp_path)
    core_addons = str(core / "addons")

    # Addon repo dir - does NOT exist
    missing_repo = str(tmp_path / "missing-addon-repo" / "addons")

    addons_path = f"{core_addons}:{missing_repo}"

    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "full_17"
            python = ""
            http_port = 8069
            db_name = "odoo_17_full"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )
    original_content = toml.read_text(encoding="utf-8")

    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_DIR"] = str(tmp_path / "odoo-ai")
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")

    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0",
         "--profile", "full_17", "--tool", "uv", "--path", str(venv_dir)],
        capture_output=True, text=True, env=env,
    )
    out = res.stdout + res.stderr

    # Must fail because a repo dir is missing
    assert res.returncode != 0, (
        f"Expected non-zero exit when a profile repo dir is missing.\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # Error message must name the missing repo path
    assert "missing" in out.lower() or "missing-addon-repo" in out or "not found" in out.lower(), (
        f"Expected error message mentioning the missing repo path.\nOutput:\n{out}"
    )
    # python must NOT be recorded
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when a profile repo is missing.\nTOML:\n{content}"
    )
    # TOML unchanged
    assert content == original_content, (
        f"TOML must be unchanged when repo-presence check fails.\nTOML:\n{content}"
    )


# ---------------------------------------------------------------------------
# F2: no-profile + only-profiled-blocks fails EARLY (before gate/build)
# ---------------------------------------------------------------------------

@requires_bash
def test_step45_no_profile_multiprofile_fails_early(tmp_path):
    """When the toml has only profiled blocks for the given series, create-venv
    without --profile must fail BEFORE any venv is built (no venv dir created).

    Business rule (B2): fail-loud guard triggers before gate/build so the error
    message is clean rather than appearing after expensive dependency install.

    The existing test_step45_no_profile_does_not_clobber_profiled_block verifies
    exit non-zero + TOML unchanged; this test additionally verifies the guard
    fires BEFORE any venv directory is created.
    """
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")

    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "minimal_17"
            instance_key = "17.0:minimal_17"
            python = ""
            http_port = 8069
            db_name = "odoo_17_minimal"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )

    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    # Auto-derived venv path (what the script would create if --path were absent)
    odoo_ai_dir = tmp_path / "odoo-ai"
    auto_venv_path = odoo_ai_dir / "venvs" / "17.0"

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_DIR"] = str(odoo_ai_dir)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")

    # Run WITHOUT --profile AND WITHOUT --path so auto-derived path is used
    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0", "--tool", "uv"],
        capture_output=True, text=True, env=env,
    )
    out = res.stdout + res.stderr

    # Must fail
    assert res.returncode != 0, (
        f"Expected non-zero exit.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )
    # Guard message must mention --profile
    assert "--profile" in out or "profile" in out.lower(), (
        f"Expected message mentioning --profile.\nOutput:\n{out}"
    )
    # No venv must have been created (guard fired BEFORE build)
    assert not auto_venv_path.exists(), (
        f"Venv dir {auto_venv_path} must NOT be created when guard fires early.\n"
        f"Output:\n{out}"
    )


# ---------------------------------------------------------------------------
# F3: step 50 shared lease must pass --profile to allocator acquire
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_shared_lease_passes_profile_to_allocator(tmp_path):
    """When spinning up a profiled instance, step 50's _register_shared must
    pass --profile <name> to allocator acquire so the lease targets the correct
    (series, profile) slot rather than the first series match.

    Strategy: write a profiled [[instance]] in instances.toml, run step 50 apply,
    then inspect the written lease to confirm profile is recorded. The allocator
    already supports --profile (cmd_acquire reads opts['profile']); this test
    confirms step 50 actually passes it.

    RED on current code where _register_shared calls acquire without --profile.
    """
    # instances.toml with a PROFILED block
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "fake-core" / "odoo-bin"
    _write_stub(fake_bin, 'echo "Odoo Server 17.0"\n')

    real_py3 = shutil.which("python3") or "/usr/bin/python3"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    launch_log = tmp_path / "odoo-launch.log"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        echo "launched $*" >> "{launch_log}"
        exec sleep 15
    """))

    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            profile = "test_profile"
            instance_key = "17.0:test_profile"
            python = "{fake_py}"
            http_port = 18169
            db_name = "odoo_17_tp"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{fake_addons}"
        """),
        encoding="utf-8",
    )

    bind = tmp_path / "bin50p"
    bind.mkdir(exist_ok=True)
    # curl: 000 first (trigger launch), 200 second (server up)
    cnt = tmp_path / "curl.count"
    _write_stub(bind / "curl", textwrap.dedent(f"""\
        n="$(cat "{cnt}" 2>/dev/null || echo 0)"
        echo $((n + 1)) > "{cnt}"
        if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
    """))
    _write_stub(bind / "pg_isready", "exit 0\n")

    home = tmp_path / "odoo-ai-home"
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(home)
    env["SPINUP_TIMEOUT"] = "10"
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(fake_bin)

    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0", "--profile", "test_profile"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, (
        f"Expected success for profiled instance.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    )

    # Inspect the lease: profile field must be recorded
    leases = _leases_at(home)
    shared = [lz for lz in leases if lz.get("mode") == "shared"]
    assert len(shared) == 1, (
        f"Expected exactly one shared lease.\nLeases:\n{leases}\nOutput:\n{out}"
    )
    lz = shared[0]
    assert lz.get("profile") == "test_profile", (
        f"Shared lease must record profile='test_profile' (got {lz.get('profile')!r}).\n"
        f"Lease: {lz}\nOutput:\n{out}"
    )

    # Reap the background sleep
    pid = lz.get("owner", {}).get("pid")
    if pid and _alive(pid):
        os.kill(int(pid), signal.SIGTERM)
