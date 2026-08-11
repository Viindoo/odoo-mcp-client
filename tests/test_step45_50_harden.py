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
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
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


# Every binary that can give this plugin a PostgreSQL client surface, plus the
# container runtime that can lend it one. A probe ladder rung is gated on
# `command -v <one of these>`, so their PRESENCE is what selects a rung.
_PG_CLIENT_BINS = (
    "pg_isready", "psql", "createdb", "dropdb", "pg_dump", "pg_restore", "docker",
)


def _client_free_path(tmp_path: Path, *stub_dirs: Path) -> str:
    """A PATH that provably carries NO PostgreSQL client and no container runtime.

    A test may NOT assert that a binary is absent from the host. `PATH =
    "<stubs>:/usr/bin:/bin"` reads as "no client here", but that is a claim about
    the RUNNER IMAGE, not about the test: a developer box without
    postgresql-client and a CI image that preinstalls it then run two different
    tests under one name, and the one that passes locally fails there - with the
    product behaving exactly as documented.

    So the absence is CONSTRUCTED rather than assumed: every ambient PATH entry
    is re-exposed through a single directory of symlinks with the client names
    left out (first occurrence wins, preserving PATH precedence). Everything the
    script legitimately needs - bash, python3, coreutils, `timeout`, `ps` - stays
    reachable and identical to a normal run; only the rung-selecting binaries are
    gone. Whitelisting instead would silently change WHICH code path runs
    whenever the script starts using one more tool.

    `stub_dirs` are prepended, so a test's own stubs still shadow the ambient
    ones. Returns the PATH string.
    """
    farm = tmp_path / "path-without-pg-clients"
    farm.mkdir(exist_ok=True)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            names = os.listdir(entry)
        except OSError:
            continue  # a PATH entry that does not exist or is unreadable
        for name in names:
            if name in _PG_CLIENT_BINS:
                continue
            link = farm / name
            if link.is_symlink() or link.exists():
                continue  # first hit wins - ambient PATH precedence is preserved
            src = Path(entry) / name
            if not os.access(src, os.X_OK) or src.is_dir():
                continue
            try:
                link.symlink_to(src)
            except OSError:
                continue
    path = os.pathsep.join([*(str(d) for d in stub_dirs), str(farm)])
    # Self-validating: if this construction ever stops working the test must fail
    # loudly here, not quietly go back to inheriting whatever the image ships.
    for name in _PG_CLIENT_BINS:
        found = shutil.which(name, path=path)
        assert found is None, (
            f"the constructed PATH must not reach a client surface, but "
            f"{name!r} resolved to {found!r} - the absence this test needs is "
            f"no longer guaranteed"
        )
    assert shutil.which("bash", path=path), (
        "the constructed PATH dropped bash - it must keep everything the script "
        "legitimately needs, or the test stops exercising the real code path"
    )
    return path


def _link_real_timeout(bindir: Path) -> bool:
    """Make the REAL coreutils `timeout` reachable THROUGH `bindir`, if it exists.

    `pg_bounded_run` has two arms - the `timeout` BINARY and a pure-bash fallback
    - and the docker rung exists precisely because handing a shell FUNCTION to
    the binary arm returns 127 unless that case is handled. Selecting the binary
    arm by hardcoding `/usr/bin:/bin` into PATH is a bet on the host's directory
    layout; link the binary in by RESOLVED location instead, so the arm is chosen
    by what exists rather than by where it happens to live.

    Returns whether the binary arm will be exercised. `timeout` is not POSIX and
    genuinely absent on BSD/macOS, so this must not be an assertion: on such a
    host the fallback arm runs, exactly as it does in production there.
    tests/test_pg_mode.py parametrizes BOTH arms directly - that is where the
    binary arm's absence is surfaced rather than passed over.
    """
    real = shutil.which("timeout")
    if not real:
        return False
    link = bindir / "timeout"
    if not link.is_symlink() and not link.exists():
        link.symlink_to(real)
    return True


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

    # Auto-derived venv dir: <SHARE dir>/venvs/17.0-minimal_17 (Tier-2 SHARE -
    # snippets/state-root-resolution.md; resolve_project_dir.sh share). Pin the
    # SHARE dir via the documented ODOO_AI_PROJECT_DIR override so this test is
    # hermetic (independent of the real git repo / HOME it happens to run in).
    # slug of "minimal_17" = "minimal_17" (already clean)
    share_dir = tmp_path / "odoo-ai" / "share"
    expected_venv = share_dir / "venvs" / "17.0-minimal_17"

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
    env["ODOO_AI_PROJECT_DIR"] = str(share_dir)
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
# step 50 <-> instances_io: a REAL 2-entry addons_path must resolve odoo-bin -
# _find_odoo_bin's split must match what instances_io.py's join_addons_path
# actually emits, not a value that only happens to be right for a
# single-entry addons_path.
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_finds_odoo_bin_across_a_real_two_entry_addons_path(tmp_path):
    """_find_odoo_bin must locate odoo-bin when INST_ADDONS_PATH carries 2+
    entries produced by the ACTUAL instances_io.py pipeline (a genuine TOML
    array -> join_addons_path -> INST_ADDONS_PATH), not a hand-joined string.

    No ODOO_BIN override here: the addons_path SCAN itself must resolve the
    odoo-bin location by finding it under the SECOND entry - the exact
    dimension (2+ real entries) that was absent from every other fixture and
    let a producer/consumer separator mismatch (IFS=',' against a
    colon-joined INST_ADDONS_PATH) ship silently.
    """
    # Entry 1: a plain custom-addons repo - no odoo-bin here.
    custom_dir = tmp_path / "custom-addons"
    custom_dir.mkdir(parents=True)

    # Entry 2: the real Odoo core dir (has odoo-bin under it).
    core = _make_core_dir(tmp_path)
    core_addons = str(core / "addons")

    # A python stub that FAILS the `<py> <odoo-bin> --version` preflight gate -
    # this lets the test stop cheaply and deterministically right after
    # odoo-bin resolution, without needing curl/pg_isready/poll machinery.
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=False)

    toml = tmp_path / "instances50-2entry.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            python = "{fake_py}"
            http_port = 18071
            db_name = "odoo_test_2entry"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = ["{custom_dir}", "{core_addons}"]
        """),
        encoding="utf-8",
    )

    bind = tmp_path / "bin50-2entry"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "000"\n')

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "3"
    env.pop("ODOO_PG_PASSWORD", None)
    env.pop("ODOO_BIN", None)  # the scan itself must find odoo-bin - no override

    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    out = res.stdout + res.stderr

    # Must NOT report "Could not locate odoo-bin" - that would mean the scan
    # failed to split the 2-entry INST_ADDONS_PATH correctly.
    assert "Could not locate odoo-bin" not in out, (
        f"_find_odoo_bin failed to resolve odoo-bin across a real 2-entry "
        f"addons_path (producer/consumer separator mismatch).\nOutput:\n{out}"
    )
    # Must have reached the (deliberately failing) PREFLIGHT gate - proof
    # odoo-bin WAS found and execution proceeded past the lookup.
    assert "PREFLIGHT FAILED" in out, (
        f"Expected to reach the PREFLIGHT gate (odoo-bin found, python stub "
        f"rejects --version).\nOutput:\n{out}"
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


def _run_step50_args(env, *extra_args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0", *extra_args],
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


# ---------------------------------------------------------------------------
# Root-cause fix: the readiness signal is a BOUNDED HTTP-port poll of
# /web/database/selector (primary, docs/reference/INSTANCE-LIFECYCLE.md item
# 14), fallback /web/login - never a log tail, never an unbounded wait.
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_ready_via_database_selector_primary_probe(tmp_path):
    """RED-first: the readiness probe's PRIMARY endpoint is
    /web/database/selector, not /web/login alone. A curl stub that answers 200
    ONLY for the selector path (000 for anything else, including /web/login)
    must still let apply succeed - proving the probe actually queries the
    selector endpoint. Under the OLD /web/login-only probe this stub would
    NEVER see a 200 (its only endpoint always sees 000) and apply would time
    out (BLOCKED, non-zero) instead."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    bind = tmp_path / "bin50"
    _write_stub(bind / "curl", textwrap.dedent("""\
        if [[ "$*" == *"/web/database/selector"* ]]; then
            echo "200"
        else
            echo "000"
        fi
    """))
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, (
        f"apply must succeed via the /web/database/selector probe alone.\n{out}"
    )
    assert "timed out" not in out


@requires_bash
def test_step50_falls_back_to_web_login_when_selector_never_ready(tmp_path):
    """The BOUNDED poll falls back to /web/login exactly once the PRIMARY
    /web/database/selector has exhausted its whole timeout budget without ever
    answering 200 - covering a series/build where the selector route is
    unavailable. A curl stub that answers 200 ONLY for /web/login (000 for the
    selector path) must still let apply succeed, and it must actually launch
    odoo-bin (not just short-circuit an 'already up' pre-check, which probes
    the selector-only and sees 000 here)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    env["SPINUP_TIMEOUT"] = "3"
    bind = tmp_path / "bin50"
    _write_stub(bind / "curl", textwrap.dedent("""\
        if [[ "$*" == *"/web/database/selector"* ]]; then
            echo "000"
        else
            echo "200"
        fi
    """))
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"apply must succeed via the /web/login fallback.\n{out}"
    assert launch_log.exists(), (
        f"the selector-only 'already up' pre-check must see 000 and proceed to launch, "
        f"then the poll's fallback must confirm readiness on /web/login\n{out}"
    )


@requires_bash
def test_step50_readiness_poll_is_bounded_never_hangs(tmp_path):
    """The readiness poll (primary + fallback) is BOUNDED by SPINUP_TIMEOUT -
    a server that never becomes ready on EITHER endpoint must return within a
    small, deterministic wall-clock bound, never hang indefinitely and never
    fall back to tailing a (possibly empty) log."""
    env, _, _ = _make_step50_spinup_env(tmp_path, curl_mode="down")
    env["SPINUP_TIMEOUT"] = "2"
    started = time.monotonic()
    res = _run_step50(env)
    elapsed = time.monotonic() - started
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a never-ready spin-up must fail, not hang\n{out}"
    assert elapsed < 20, (
        f"the poll must be BOUNDED by SPINUP_TIMEOUT (=2s), not wait indefinitely; "
        f"took {elapsed:.1f}s\n{out}"
    )
    assert "timed out" in out.lower()


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
# P5.5-P5.9: persist: exclusive-running spin-up (--exclusive + allocator
# overrides) and the owner-stamped shared lease.
# ---------------------------------------------------------------------------
@requires_bash
def test_step50_exclusive_without_overrides_is_blocked_not_8069_fallback(tmp_path):
    """--exclusive with NO --db-name/--http-port must BLOCK (non-zero, no launch)
    rather than silently converge on the declared/8069 port (P5.9: the
    exclusive-running path must bypass the 8069 fallback, never use it)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(env, "--exclusive")
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"--exclusive with no overrides must be BLOCKED\n{out}"
    assert "BLOCKED" in out, f"expected an explicit BLOCKED message\n{out}"
    assert not launch_log.exists(), f"odoo-bin must NOT launch when --exclusive is under-specified\n{out}"
    assert _leases_at(home) == [], "a blocked exclusive spin-up must write no lease"


@requires_bash
def test_step50_exclusive_uses_allocator_port_and_db_skips_shared_lease(tmp_path):
    """--exclusive --db-name --http-port --port-key spins up the CALLER's own
    pre-leased db/port (not the declared 18069/odoo_test) and registers NO
    shared lease at all - the DB is already owned by the caller's own acquire,
    not a second shared render-target row (P5.6/P5.7)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(
        env, "--exclusive",
        "--db-name", "odoo_17_0_t_deadbeef",
        "--http-port", "18271",
        "--port-key", "http_port",
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert launch_log.exists(), f"odoo-bin must launch for a well-specified --exclusive run\n{out}"
    launched = launch_log.read_text(encoding="utf-8")
    assert "odoo_17_0_t_deadbeef" in launched, (
        f"launch must target the ALLOCATOR-issued db, not the declared odoo_test\n{launched}"
    )
    assert _leases_at(home) == [], (
        "--exclusive must register NO shared lease - the DB is the caller's own "
        f"pre-leased instance, not the shared render target\nleases: {_leases_at(home)}"
    )
    # Conf must carry the overridden port under the agent-resolved key.
    conf_lines = [line for line in out.splitlines() if "Generated temp conf:" in line]
    assert conf_lines, f"no 'Generated temp conf' line\n{out}"
    conf_path = Path(conf_lines[0].split("Generated temp conf:")[-1].strip())
    conf = conf_path.read_text(encoding="utf-8")
    assert "http_port = 18271" in conf, f"conf must bind the allocator-issued port\n{conf}"


@requires_bash
def test_step50_exclusive_binds_launched_pid_onto_the_caller_lease(tmp_path):
    """L1.1 (RAM-leak fix): an --exclusive spin-up must BIND the launched server
    pid onto the caller's PRE-ACQUIRED lease (via --alloc-token), so a later
    `allocator.py release`/`gc` can stop the whole process group before dropping
    the DB. Before this fix only shared leases recorded a pid, so an exclusive
    lease leaked the listening server on release.
    """
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")

    # The caller (odoo-instance-ops) acquires the exclusive lease FIRST.
    db = "odoo_17_0_t_deadbeef"
    acq = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "exclusive", "--db-name", db, "--run-id", "run-excl"],
        capture_output=True, text=True, env=env,
    )
    assert acq.returncode == 0, acq.stderr
    token = next(
        line.split("=", 1)[1].strip().strip("'")
        for line in acq.stdout.splitlines() if line.startswith("ALLOC_TOKEN=")
    )
    assert token, f"acquire must mint a token\n{acq.stdout}"
    lease_before = [lz for lz in _leases_at(home) if lz.get("token") == token][0]
    assert lease_before["owner"]["pid"] is None, "exclusive acquire records no pid until the bind"

    res = _run_step50_args(
        env, "--exclusive",
        "--db-name", db,
        "--http-port", "18271",
        "--port-key", "http_port",
        "--alloc-token", token,
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert launch_log.exists(), f"odoo-bin must launch for a well-specified --exclusive run\n{out}"

    lease_after = [lz for lz in _leases_at(home) if lz.get("token") == token]
    assert lease_after, f"the exclusive lease must survive (never a shared row)\n{_leases_at(home)}"
    pid = lease_after[0]["owner"]["pid"]
    assert pid, "the launched server pid must be BOUND onto the exclusive lease"
    assert _alive(int(pid)), "the bound pid must be the live server (kill -0 confirmed)"
    # No shared lease is ever created on the exclusive branch.
    assert not [lz for lz in _leases_at(home) if lz.get("mode") == "shared"], (
        "the exclusive branch must NOT register a shared render lease"
    )
    os.kill(int(pid), signal.SIGTERM)  # reap the backgrounded sleep stand-in


def _make_step50_forking_env(tmp_path: Path, *, trap_term: bool):
    """A step-50 source-mode scenario whose 'odoo-bin' launch forks a CHILD
    (a stand-in worker) in the setsid process group and whose curl NEVER answers
    200 (the readiness poll TIMES OUT). Writes '<leader> <child>' to a pidfile.
    When trap_term is True, BOTH leader and child TRAP SIGTERM (append to a marker
    file and keep running) so only a SIGKILL escalation can reap them - proving
    the timeout cleanup escalates and targets the whole GROUP. Returns
    (env, home, pidfile, marker)."""
    pidfile = tmp_path / "grp.pids"
    marker = tmp_path / "term.marker"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    if trap_term:
        launch_body = textwrap.dedent(f"""\
            trap 'echo leader >> "{marker}"' TERM
            (
              trap 'echo child >> "{marker}"' TERM
              while :; do sleep 1; done
            ) &
            echo "$$ $!" > "{pidfile}"
            while :; do sleep 1; done
        """)
    else:
        launch_body = textwrap.dedent(f"""\
            sleep 300 &
            echo "$$ $!" > "{pidfile}"
            wait
        """)
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
    """) + launch_body)

    odoo_bin = tmp_path / "odoo-bin"
    _write_stub(odoo_bin, "exit 0\n")  # only needs to exist for _find_odoo_bin
    bind = tmp_path / "bin50"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "000"\n')       # never ready -> poll times out
    _write_stub(bind / "pg_isready", "exit 0\n")

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py))
    home = tmp_path / "odoo-ai-home"
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(home)
    env["SPINUP_TIMEOUT"] = "3"       # short poll bound
    env["SPINUP_STOP_GRACE"] = "2"    # short SIGTERM->SIGKILL escalation bound
    env.pop("ODOO_PG_PASSWORD", None)
    env["ODOO_BIN"] = str(odoo_bin)
    return env, home, pidfile, marker


def _wait_dead(pid: int, timeout_s: float = 5.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


@requires_bash
def test_step50_exclusive_binds_pid_before_poll_and_group_reaped_on_timeout(tmp_path):
    """L1.1 failure-path gap: an --exclusive spin-up must bind the pid onto the
    lease BEFORE the readiness poll (so release/gc can always reap), and on a poll
    TIMEOUT the local cleanup must stop the whole process GROUP - not just the
    leader - so a forked worker child does not survive against a DB the caller may
    then drop."""
    env, home, pidfile, _ = _make_step50_forking_env(tmp_path, trap_term=False)
    db = "odoo_17_0_t_timeout1"
    acq = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "exclusive", "--db-name", db, "--run-id", "run-excl"],
        capture_output=True, text=True, env=env,
    )
    assert acq.returncode == 0, acq.stderr
    token = next(
        line.split("=", 1)[1].strip().strip("'")
        for line in acq.stdout.splitlines() if line.startswith("ALLOC_TOKEN=")
    )

    res = _run_step50_args(
        env, "--exclusive", "--db-name", db, "--http-port", "18271",
        "--port-key", "http_port", "--alloc-token", token,
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a never-ready spin-up must FAIL (timeout)\n{out}"
    assert pidfile.exists(), f"the fake server must have launched + forked a child\n{out}"
    leader, child = (int(x) for x in pidfile.read_text().split())

    # (1) pid bound onto the lease BEFORE the poll (even though the poll timed out).
    lease = [lz for lz in _leases_at(home) if lz.get("token") == token]
    assert lease, "the exclusive lease must survive the timeout"
    assert lease[0]["owner"]["pid"] == leader, (
        "the launched pid must be BOUND onto the lease before the readiness poll, "
        "so release/gc can reap the group regardless of poll outcome"
    )
    # (2) the WHOLE group is reaped by the local cleanup - child too, not just leader.
    try:
        assert _wait_dead(leader), "the timeout cleanup must stop the group leader"
        assert _wait_dead(child), (
            "the timeout cleanup must stop the forked CHILD too (group-targeted, "
            "not a bare `kill <leader>` that leaves workers running)"
        )
    finally:
        for p in (child, leader):
            try:
                os.kill(p, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass


@requires_bash
def test_step50_timeout_cleanup_escalates_to_group_sigkill(tmp_path):
    """The timeout cleanup must ESCALATE: SIGTERM the group, wait a bounded grace,
    then SIGKILL the group. Proven with a leader AND child that both TRAP SIGTERM
    (survive it) - they must still end up dead (only SIGKILL can do that), and both
    must have RECEIVED the group SIGTERM (marker written by each)."""
    env, home, pidfile, marker = _make_step50_forking_env(tmp_path, trap_term=True)
    db = "odoo_17_0_t_timeout2"
    acq = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "exclusive", "--db-name", db, "--run-id", "run-excl"],
        capture_output=True, text=True, env=env,
    )
    assert acq.returncode == 0, acq.stderr
    token = next(
        line.split("=", 1)[1].strip().strip("'")
        for line in acq.stdout.splitlines() if line.startswith("ALLOC_TOKEN=")
    )

    res = _run_step50_args(
        env, "--exclusive", "--db-name", db, "--http-port", "18271",
        "--port-key", "http_port", "--alloc-token", token,
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a never-ready spin-up must FAIL (timeout)\n{out}"
    assert pidfile.exists(), out
    leader, child = (int(x) for x in pidfile.read_text().split())

    try:
        # Both members RECEIVED the group SIGTERM (group targeting), yet survived it
        # (they trap it) - so being dead now proves the SIGKILL escalation fired.
        assert _wait_dead(leader), "SIGKILL escalation must reap the SIGTERM-trapping leader"
        assert _wait_dead(child), "SIGKILL escalation must reap the SIGTERM-trapping child"
        marker_text = marker.read_text(encoding="utf-8") if marker.exists() else ""
        assert "leader" in marker_text, "the leader must have received the group SIGTERM"
        assert "child" in marker_text, (
            "the child must have received the group SIGTERM too (group-targeted, not leader-only)"
        )
    finally:
        for p in (child, leader):
            try:
                os.kill(p, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass


@requires_bash
def test_step50_gevent_port_without_key_is_blocked(tmp_path):
    """--gevent-port with NO --gevent-port-key must BLOCK (non-zero, no launch)
    rather than silently omitting the second listening port from the generated
    conf (mirrors the --exclusive-without-overrides gate above)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(env, "--gevent-port", "9069")
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"--gevent-port with no --gevent-port-key must be BLOCKED\n{out}"
    assert "BLOCKED" in out, f"expected an explicit BLOCKED message\n{out}"
    assert "gevent-port" in out, f"expected the error to name the half-specified flag\n{out}"
    assert not launch_log.exists(), (
        f"odoo-bin must NOT launch when --gevent-port is under-specified\n{out}"
    )
    assert _leases_at(home) == [], "a blocked spin-up must write no lease"


@requires_bash
def test_step50_gevent_port_key_without_port_is_blocked(tmp_path):
    """--gevent-port-key with NO --gevent-port must BLOCK (non-zero, no launch) -
    the other half of the pairing gate (the previous test covers the reverse)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(env, "--gevent-port-key", "longpolling_port")
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"--gevent-port-key with no --gevent-port must be BLOCKED\n{out}"
    assert "BLOCKED" in out, f"expected an explicit BLOCKED message\n{out}"
    assert "gevent-port" in out, f"expected the error to name the half-specified flag\n{out}"
    assert not launch_log.exists(), (
        f"odoo-bin must NOT launch when --gevent-port-key is under-specified\n{out}"
    )
    assert _leases_at(home) == [], "a blocked spin-up must write no lease"


@requires_bash
def test_step50_gevent_port_and_key_together_writes_conf_line(tmp_path):
    """Regression guard for the happy path: --gevent-port + --gevent-port-key
    given TOGETHER must still succeed and the generated conf must carry the
    second listening-port line under the agent-resolved key - the new pairing
    gate must not block (or otherwise disturb) the well-specified case."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(
        env, "--gevent-port", "9069", "--gevent-port-key", "longpolling_port",
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert launch_log.exists(), f"odoo-bin must launch for a well-specified gevent pair\n{out}"
    conf_lines = [line for line in out.splitlines() if "Generated temp conf:" in line]
    assert conf_lines, f"no 'Generated temp conf' line\n{out}"
    conf_path = Path(conf_lines[0].split("Generated temp conf:")[-1].strip())
    conf = conf_path.read_text(encoding="utf-8")
    assert "longpolling_port = 9069" in conf, (
        f"conf must carry the second listening port under the resolved key\n{conf}"
    )


@requires_bash
def test_step50_shared_lease_owner_stamped_when_run_id_set(tmp_path):
    """P5.5: when the caller sets INST_RUN_ID before invoking apply (the
    declared/shared persist: shared-running path), _register_shared threads
    --run-id into its allocator acquire, so the shared lease is owner-stamped
    instead of unowned. Absent INST_RUN_ID, the lease stays unowned exactly as
    before (back-compat - already covered by test_step50_registers_shared_lease_after_server_up)."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    env["INST_RUN_ID"] = "run-owner-xyz"
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert launch_log.exists()
    shared = [lz for lz in _leases_at(home) if lz.get("mode") == "shared"]
    assert len(shared) == 1, f"expected exactly one shared lease\n{_leases_at(home)}"
    lz = shared[0]
    assert lz["owner"].get("run_id") == "run-owner-xyz", (
        f"the shared lease must be owner-stamped with INST_RUN_ID; got {lz['owner']!r}"
    )
    pid = lz["owner"]["pid"]
    if pid and _alive(pid):
        os.kill(int(pid), signal.SIGTERM)


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

    # A representative auto-derived venv path. The --profile guard fires BEFORE
    # the venv path is ever computed (resolve_project_dir_share included), so
    # its exact root is irrelevant to this assertion - what matters is that NO
    # venv directory materializes anywhere under tmp_path.
    auto_venv_path = tmp_path / "odoo-ai" / "venvs" / "17.0"

    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
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


# ---------------------------------------------------------------------------
# Problem 5: step 05 venv HARD gate for declared source-mode instances.
#   python="" (or a broken venv) -> `check` FAILS with a remediation line.
#   ODOO_AI_ALLOW_NO_VENV=1 downgrades the FAILED to a loud WARN (check passes).
# ---------------------------------------------------------------------------
STEP05 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "05-prereq-check.sh"
)


def _step05_env(tmp_path: Path, toml: Path, *, git_base: Path) -> dict:
    """A `check` env where every OTHER instance prerequisite (python3/curl/pg/repos)
    is satisfied via stubs, so the venv gate is the only differentiator."""
    bind = tmp_path / "bin05"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "200"\n')
    _write_stub(bind / "pg_isready", "exit 0\n")
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["SETUP_FILTER"] = "instance"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_GIT_BASE"] = str(git_base)
    env.pop("ODOO_AI_ALLOW_NO_VENV", None)
    return env


def _source_instance_toml(tmp_path: Path, *, python: str, addons_path: str) -> Path:
    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            python = "{python}"
            run_mode = "source"
            http_port = 8069
            db_name = "odoo"
            db_host = "localhost"
            db_user = "odoo"
            addons_path = "{addons_path}"
        """),
        encoding="utf-8",
    )
    return toml


@requires_bash
def test_step05_venv_gate_fails_when_source_instance_has_no_venv(tmp_path):
    """A declared source instance with python="" must make `check` FAIL with a
    remediation line pointing at 45-venv.sh (the hard gate)."""
    core = _make_core_dir(tmp_path)  # provides odoo-bin + counts as a repo under git_base
    toml = _source_instance_toml(tmp_path, python="", addons_path=str(core / "addons"))
    env = _step05_env(tmp_path, toml, git_base=tmp_path)

    res = subprocess.run(["bash", str(STEP05), "check"], capture_output=True, text=True, env=env)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"check must FAIL when a source instance has no venv.\n{out}"
    assert "FAILED" in out, f"expected an explicit FAILED gate line.\n{out}"
    assert "45-venv.sh" in out and "17.0" in out, (
        f"expected remediation naming 45-venv.sh and the series.\n{out}"
    )


@requires_bash
def test_step05_venv_gate_downgrades_to_warn_with_opt_out(tmp_path):
    """ODOO_AI_ALLOW_NO_VENV=1 downgrades the FAILED gate to a loud WARN and check passes."""
    core = _make_core_dir(tmp_path)
    toml = _source_instance_toml(tmp_path, python="", addons_path=str(core / "addons"))
    env = _step05_env(tmp_path, toml, git_base=tmp_path)
    env["ODOO_AI_ALLOW_NO_VENV"] = "1"

    res = subprocess.run(["bash", str(STEP05), "check"], capture_output=True, text=True, env=env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"opt-out must let check PASS.\n{out}"
    assert "WARN" in out, f"the opt-out must still be LOUD (WARN), never silent.\n{out}"


@requires_bash
def test_step05_venv_gate_passes_with_runnable_venv(tmp_path):
    """A source instance whose python runs `<py> <odoo-bin> --version` passes the gate."""
    core = _make_core_dir(tmp_path)
    venv = _make_fake_venv(tmp_path, odoo_runnable=True)
    toml = _source_instance_toml(
        tmp_path, python=str(venv / "bin" / "python"), addons_path=str(core / "addons"))
    env = _step05_env(tmp_path, toml, git_base=tmp_path)

    res = subprocess.run(["bash", str(STEP05), "check"], capture_output=True, text=True, env=env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"a working venv must PASS the gate.\n{out}"
    assert "FAILED" not in out, f"a working venv must not emit a FAILED line.\n{out}"


# ---------------------------------------------------------------------------
# P1 (Problem 1 hardening): the A2 long-running listener conf must carry
# limit_memory_hard/limit_memory_soft/limit_time_real (previously ZERO limit
# keys) and must NOT carry limit_time_cpu while workers=0 (a dead key there -
# it lives only in the prefork Worker.check_limits() path, which needs
# workers>0; this plugin never passes --workers). Unlike 55-instance-ops.sh's
# --stop-after-init build path, this IS a real listening ThreadedServer, so
# limit_memory_hard/soft AND limit_time_real all actually fire here. See
# snippets/odoo-bin-resource-limits.md.
# ---------------------------------------------------------------------------

def _generated_conf_text(out: str) -> str:
    conf_lines = [line for line in out.splitlines() if "Generated temp conf:" in line]
    assert conf_lines, f"no 'Generated temp conf:' line in output\n{out}"
    conf_path = Path(conf_lines[0].split("Generated temp conf:")[-1].strip())
    return conf_path.read_text(encoding="utf-8")


@requires_bash
def test_step50_conf_carries_limit_memory_hard_soft_and_time_real(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    conf = _generated_conf_text(out)
    assert re.search(r"^limit_memory_hard = \d+$", conf, re.MULTILINE), (
        f"conf must carry a numeric limit_memory_hard key.\nconf:\n{conf}"
    )
    assert re.search(r"^limit_memory_soft = \d+$", conf, re.MULTILINE), (
        f"conf must carry a numeric limit_memory_soft key.\nconf:\n{conf}"
    )
    assert re.search(r"^limit_time_real = \d+$", conf, re.MULTILINE), (
        f"conf must carry a numeric limit_time_real key.\nconf:\n{conf}"
    )


@requires_bash
def test_step50_conf_never_carries_limit_time_cpu_while_workers_zero(tmp_path):
    """limit_time_cpu must never appear at all while workers=0 - a dead key
    would give false confidence that a runaway request is bounded."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    conf = _generated_conf_text(out)
    assert "limit_time_cpu" not in conf, (
        f"conf must NOT carry limit_time_cpu while workers=0 (dead key).\nconf:\n{conf}"
    )


@requires_bash
def test_step50_conf_limit_memory_hard_is_env_overridable(tmp_path):
    """The A2 conf keys must be driven by the SAME resource_limits.sh env
    overrides as the build path (SSOT: one resolver, not two independent
    formulas) - ODOO_AI_LIMIT_MEMORY_HARD wins verbatim."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    env["ODOO_AI_LIMIT_MEMORY_HARD"] = "1234567890"
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    conf = _generated_conf_text(out)
    assert "limit_memory_hard = 1234567890" in conf, (
        f"conf must honor an explicit ODOO_AI_LIMIT_MEMORY_HARD override.\nconf:\n{conf}"
    )


@requires_bash
def test_step50_preflight_cannot_hang_when_the_declared_python_hangs(tmp_path):
    """The PostgreSQL reachability preflight is BOUNDED.

    When no client surface is declared and no pg_isready exists, reachability is
    probed through the instance's own declared interpreter. That interpreter is a
    third-party program: it can hang (an unreachable cluster with no connect
    timeout, a broken venv wrapper). An unbounded probe would stall the whole
    spin-up - and the spin-up's own timeout + process-group cleanup contract could
    never even be reached. The probe must therefore be cut off, reported as NOT
    PROBED, and never mistaken for 'the cluster is down'.
    """
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir()
    fake_py = py_bin_dir / "python"
    # --version answers (the venv gate passes); ANY other invocation - notably the
    # odoo_db.py reachability probe - hangs forever.
    _write_stub(fake_py, textwrap.dedent("""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        while :; do sleep 1; done
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _write_stub(odoo_bin, "exit 0\n")
    bind = tmp_path / "bin50"
    bind.mkdir()
    _write_stub(bind / "curl", 'echo "000"\n')  # never ready -> the poll times out

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py))
    env = dict(os.environ)
    # This instance declares NO db_run_mode, so rung 1 is selected by whether a
    # pg_isready EXISTS - a fact about the host, which no test may assume. The
    # absence is constructed here so the ladder provably falls to the interpreter
    # on every image, including one that ships postgresql-client.
    env["PATH"] = _client_free_path(tmp_path, bind)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "3"
    env["SPINUP_STOP_GRACE"] = "2"
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "2"
    env["ODOO_BIN"] = str(odoo_bin)
    env.pop("ODOO_PG_PASSWORD", None)

    res = _run_step50_args(env)  # a 30s subprocess bound: a hang FAILS this test
    out = res.stdout + res.stderr

    assert "PREFLIGHT FAILED: PostgreSQL is not reachable" not in out, (
        f"a probe that did not answer must NOT be reported as an unreachable "
        f"cluster - that conflation is the defect this dispatch replaced\n{out}"
    )
    assert "was NOT probed" in out, (
        f"an unanswered probe must be said out loud, never skipped silently\n{out}"
    )
    # "was NOT probed" is ALSO what the no-surface-and-no-python branch prints, so
    # on its own it cannot tell a cut-off interpreter probe from a ladder that
    # never reached one. Name the rung that had to run.
    assert "odoo_db.py exists" in out, (
        f"the interpreter rung is the one under test - a PATH that also lost the "
        f"declared python would pass the assertion above while testing nothing\n{out}"
    )


# ---------------------------------------------------------------------------
# The DOCKER Postgres surface - the host class this dispatch was written for
# (Postgres in a container, no libpq client installed). Nothing here needs a
# real docker: a stub on PATH stands in for the daemon.
# ---------------------------------------------------------------------------
def _make_step50_toml_with_pg_surface(
    tmp_path: Path, *, py_path: str, series: str = "17.0", extra: str = "",
) -> Path:
    """instances.toml carrying the DECLARED Postgres client surface keys.

    `extra` is appended verbatim inside the one [[instance]] block, so a test can
    declare db_run_mode/db_container/db_port without a second fixture shape.
    """
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    toml = tmp_path / "instances50-pgsurface.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "{series}"
            python = "{py_path}"
            http_port = 18069
            db_name = "odoo_test"
            db_host = "db.example"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{fake_addons}"
        """) + extra,
        encoding="utf-8",
    )
    return toml


def _docker_pg_scenario(tmp_path: Path, *, docker_body: str, curl_body: str):
    """A source-mode step-50 scenario whose Postgres is declared as `docker`.

    Returns (env, out_paths). `docker_body` is the stub daemon's behavior, so one
    fixture covers a healthy daemon, a hanging one, or a refusing one.
    """
    launch_log = tmp_path / "odoo-launch.log"
    docker_log = tmp_path / "docker-calls.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        echo "odoo-bin launched $*" >> "{launch_log}"
        exec sleep 15
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _write_stub(odoo_bin, "exit 0\n")

    bind = tmp_path / "bin50-docker"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", curl_body)
    _write_stub(bind / "docker", f'echo "docker $*" >> "{docker_log}"\n' + docker_body)
    # A REAL `timeout` must be reachable - the arm on which handing a shell
    # function to that coreutils binary fails. Linked in explicitly rather than
    # inferred from a hardcoded /usr/bin:/bin, which is a guess about the host.
    _link_real_timeout(bind)

    toml = _make_step50_toml_with_pg_surface(
        tmp_path, py_path=str(fake_py),
        extra='db_port = 5544\ndb_run_mode = "docker"\ndb_container = "pg-for-tests"\n',
    )
    env = dict(os.environ)
    # The docker stub above SHADOWS any real docker the image ships, and the
    # declared mode keeps the ladder off rung 1 entirely, so this test's outcome
    # does not depend on what the host has installed.
    env["PATH"] = f"{bind}{os.pathsep}{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "3"
    env["SPINUP_STOP_GRACE"] = "2"
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "3"
    env["ODOO_BIN"] = str(odoo_bin)
    env.pop("ODOO_PG_PASSWORD", None)
    return env, launch_log, docker_log


@requires_bash
def test_step50_docker_pg_preflight_probes_inside_the_container_and_launches(tmp_path):
    """A `docker` Postgres surface must PASS its preflight and launch.

    The probe is `pg_bounded_run <secs> pg_run_client docker ...` - a bound
    applied to a shell FUNCTION. `timeout` is a coreutils BINARY that EXECs its
    argument, so that composition returns 127 unless the bound handles a function
    too, and 127 then reads as `PREFLIGHT FAILED: PostgreSQL is not reachable` on
    a perfectly healthy cluster: the instance never launches, on exactly the host
    class the docker arm exists for.
    """
    # 000 on the first probe (so the 'already up' short-circuit is not taken and
    # the preflight actually runs), 200 afterwards.
    cnt = tmp_path / "curl.count"
    env, launch_log, docker_log = _docker_pg_scenario(
        tmp_path, docker_body="exit 0\n", curl_body=textwrap.dedent(f"""\
            n="$(cat "{cnt}" 2>/dev/null || echo 0)"
            echo $((n + 1)) > "{cnt}"
            if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
        """))
    res = _run_step50_args(env)
    out = res.stdout + res.stderr

    assert "PREFLIGHT FAILED: PostgreSQL is not reachable" not in out, (
        f"a healthy containerised cluster must not be reported unreachable\n{out}"
    )
    assert res.returncode == 0, f"the spin-up must succeed\n{out}"
    assert "ok PostgreSQL reachable" in out, (
        f"the docker rung must report a POSITIVE reachability verdict\n{out}"
    )
    assert docker_log.exists(), f"the probe never invoked docker at all\n{out}"
    calls = docker_log.read_text(encoding="utf-8")
    assert "exec" in calls and "pg-for-tests" in calls and "pg_isready" in calls, (
        f"the probe must run pg_isready INSIDE the declared container; got:\n{calls}"
    )


@requires_bash
@pytest.mark.parametrize("surface", ["native", "docker"])
def test_step50_a_probe_that_times_out_is_never_a_reachability_verdict(tmp_path, surface):
    """124 means "the probe did not answer", on EVERY rung of the ladder.

    Only the interpreter rung was guarded, so a bound that elapsed on the native
    or docker rung fell straight through to `PREFLIGHT FAILED: PostgreSQL is not
    reachable ... (exit 124)` and refused to launch. Its sibling
    05-prereq-check.sh gets this right on both rungs, so the two ladders
    disagreed about the same rule.
    """
    hang = "while :; do :; done\n"
    if surface == "docker":
        env, launch_log, _ = _docker_pg_scenario(
            tmp_path, docker_body=hang, curl_body='echo "000"\n')
    else:
        launch_log = tmp_path / "odoo-launch.log"
        py_bin_dir = tmp_path / "fake-py-bin"
        py_bin_dir.mkdir(exist_ok=True)
        fake_py = py_bin_dir / "python"
        _write_stub(fake_py, textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            echo "odoo-bin launched $*" >> "{launch_log}"
            exec sleep 15
        """))
        odoo_bin = tmp_path / "odoo-bin"
        _write_stub(odoo_bin, "exit 0\n")
        bind = tmp_path / "bin50-native"
        bind.mkdir(exist_ok=True)
        _write_stub(bind / "curl", 'echo "000"\n')
        # The stub SHADOWS whatever client the image ships, so the rung under
        # test is this hanging one on every host - never the runner's real
        # pg_isready answering about a cluster this test knows nothing about.
        _write_stub(bind / "pg_isready", hang)
        _link_real_timeout(bind)
        toml = _make_step50_toml_with_pg_surface(
            tmp_path, py_path=str(fake_py), extra='db_run_mode = "native"\n')
        env = dict(os.environ)
        env["PATH"] = f"{bind}{os.pathsep}{env.get('PATH', '')}"
        env["ODOO_AI_INSTANCES"] = str(toml)
        env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
        env["SPINUP_TIMEOUT"] = "3"
        env["SPINUP_STOP_GRACE"] = "2"
        env["ODOO_AI_PG_PROBE_TIMEOUT"] = "3"
        env["ODOO_BIN"] = str(odoo_bin)
        env.pop("ODOO_PG_PASSWORD", None)

    res = _run_step50_args(env)
    out = res.stdout + res.stderr

    assert "PREFLIGHT FAILED: PostgreSQL is not reachable" not in out, (
        f"[{surface}] a bound that elapsed says NOTHING about the cluster\n{out}"
    )
    assert "was NOT probed" in out, (
        f"[{surface}] an unanswered probe must be said out loud\n{out}"
    )
    assert launch_log.exists(), (
        f"[{surface}] an unanswered probe must not block the launch\n{out}"
    )


@requires_bash
def test_step50_a_tcp_only_declaration_never_consults_a_local_client(tmp_path):
    """`tcp-only` positively declares NO client surface, so rung 1 is skipped.

    This is the DECLARED twin of the undeclared case above, and it needs no
    assumption about the host at all: an installed pg_isready belongs to some
    OTHER cluster, so consulting it is the wrong-cluster hazard - it would answer
    confidently, and about a database this instance never uses. The ladder must
    walk straight past it to the instance's own interpreter, and when THAT cannot
    answer, report a non-answer rather than convert one into a verdict.
    """
    probe_log = tmp_path / "pg_isready-calls.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir()
    fake_py = py_bin_dir / "python"
    # --version answers (the venv gate passes); the reachability probe hangs.
    _write_stub(fake_py, textwrap.dedent("""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        while :; do sleep 1; done
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _write_stub(odoo_bin, "exit 0\n")
    bind = tmp_path / "bin50-tcponly"
    bind.mkdir()
    _write_stub(bind / "curl", 'echo "000"\n')  # never ready -> the poll times out
    # A local client that would report a HEALTHY cluster - the false green the
    # declaration exists to refuse. It records every call, so "never consulted"
    # is proved rather than inferred from the absence of a message.
    _write_stub(bind / "pg_isready", f'echo "called $*" >> "{probe_log}"\nexit 0\n')

    toml = _make_step50_toml_with_pg_surface(
        tmp_path, py_path=str(fake_py), extra='db_run_mode = "tcp-only"\n')
    env = dict(os.environ)
    # Ambient PATH is fine here: the stub above SHADOWS any client the image
    # ships, so this test's outcome is the same whether or not one exists.
    env["PATH"] = f"{bind}{os.pathsep}{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "3"
    env["SPINUP_STOP_GRACE"] = "2"
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "2"
    env["ODOO_BIN"] = str(odoo_bin)
    env.pop("ODOO_PG_PASSWORD", None)

    res = _run_step50_args(env)  # a 30s subprocess bound: a hang FAILS this test
    out = res.stdout + res.stderr

    assert not probe_log.exists(), (
        f"a tcp-only declaration must never reach a local client - it answers for "
        f"a DIFFERENT cluster; calls:\n{probe_log.read_text(encoding='utf-8')}\n{out}"
    )
    assert "ok PostgreSQL reachable" not in out, (
        f"the wrong cluster's client answered 0 and that became a positive "
        f"reachability verdict for this one\n{out}"
    )
    assert "PREFLIGHT FAILED: PostgreSQL is not reachable" not in out, (
        f"a probe that did not answer must NOT be reported as an unreachable "
        f"cluster\n{out}"
    )
    assert "was NOT probed" in out and "odoo_db.py exists" in out, (
        f"tcp-only must fall to the interpreter rung, and its non-answer must be "
        f"said out loud\n{out}"
    )


# ---------------------------------------------------------------------------
# The upsert writes into the HOST'S instance catalog - the SSOT every consumer
# reads (the allocator, all five setup steps, the teardown hook). A value it
# cannot represent does not corrupt one field: it makes the whole file
# unparseable, and every one of those consumers then fails until a human
# repairs it by hand.
# ---------------------------------------------------------------------------
def _tomllib_load(path: Path) -> dict:
    import tomllib

    with open(path, "rb") as fh:
        return tomllib.load(fh)


@requires_bash
@pytest.mark.parametrize("hostile", ['pa"th', "pa\\th", "pa\\tb"])
def test_step45_upsert_keeps_the_catalog_parseable_for_any_recorded_value(tmp_path, hostile):
    """A recorded value must round-trip, whatever characters it contains.

    `create-venv --path DIR` takes this value from user input. Unescaped, a `"`
    closes the TOML string early and the catalog stops parsing altogether; a
    backslash is the quieter variant - `\\t` decodes to a TAB, so the recorded
    value is silently WRONG rather than loudly broken.
    """
    core = _make_core_dir(tmp_path)
    toml = _make_instances_toml(tmp_path, addons_path=str(core / "addons"))
    env = dict(os.environ)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")

    # Drive the upsert directly: it is the unit that owns value encoding, and
    # calling it here needs no venv, no uv and no Odoo.
    # `source <script> check` loads the functions without tripping the argv
    # dispatcher at the bottom of the file (which would `exit 2`).
    res = subprocess.run(
        ["bash", "-c",
         f'source "{STEP45}" check >/dev/null; '
         f'_upsert_instance_keys "17.0" "" "python=$1"', "_", hostile],
        capture_output=True, text=True, env=env,
    )
    out = res.stdout + res.stderr

    parsed = _tomllib_load(toml)  # raises TOMLDecodeError when the catalog is broken
    got = parsed["instance"][0]["python"]
    assert got == hostile, (
        f"the recorded value must round-trip exactly; wrote {hostile!r}, read back "
        f"{got!r}\noutput:\n{out}"
    )


@requires_bash
def test_step45_upsert_never_leaves_a_half_written_catalog(tmp_path):
    """The catalog is replaced ATOMICALLY, never truncated in place.

    An in-place truncate has a window in which the host's only instance catalog
    is empty or partial; a crash there loses every declared instance. The
    allocator's own registry write already uses tmp + os.replace - the same
    discipline applies to the file the allocator READS.
    """
    core = _make_core_dir(tmp_path)
    toml = _make_instances_toml(tmp_path, addons_path=str(core / "addons"))
    src = STEP45.read_text(encoding="utf-8")
    upsert = src[src.index("_upsert_instance_keys() {"):src.index("# _detect_pg_facts")]
    assert "os.replace" in upsert, (
        "the upsert must publish the new catalog with an atomic os.replace, not an "
        "in-place truncate of the host's SSOT"
    )
    assert 'open(path, "w"' not in upsert, (
        "the upsert must not open the catalog itself for writing (that truncates it)"
    )
    # And the mechanism must actually work end to end.
    env = dict(os.environ)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    res = subprocess.run(
        ["bash", "-c",
         f'source "{STEP45}" check >/dev/null; '
         f'_upsert_instance_keys "17.0" "" "odoo_root=/srv/odoo"'],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert _tomllib_load(toml)["instance"][0]["odoo_root"] == "/srv/odoo"
    leftovers = [p.name for p in toml.parent.glob("instances.toml.tmp*")]
    assert leftovers == [], f"the temp file must not survive a successful write: {leftovers}"


# ---------------------------------------------------------------------------
# step 55 (instance ops): the ACTIVE-WAIT terminal predicate.
#
# These live in this file because it is this change's owned home for setup-step
# behavior; the rule they protect belongs to 55-instance-ops.sh.
#
# `wait-log` runs in a different process - often a different agent turn - from the
# build it is waiting on, so the only thing it can read is the log. The terminal
# predicate DIFFERS by verb: "Modules loaded." IS completion for an
# install/update build, but on a test run Odoo logs it BEFORE the post-install
# suite starts (verified against a local checkout: modules/loading.py logs it
# ahead of the post_install test step). Certifying a test run there stops the wait
# while the suite has not begun.
# ---------------------------------------------------------------------------
STEP55 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "55-instance-ops.sh"
)

_MODERN_SUMMARY = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.service.server: "
    "0 failed, 0 error(s) of 5 tests when loading database 'testdb'"
)
_LOADED_MARKER = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.loading: Modules loaded."
)
_PROGRESS_LINE = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.loading: loading 3 modules..."
)


def _run55(subcmd: str, *args, env: dict, timeout: int = 60):
    return subprocess.run(
        ["bash", str(STEP55), subcmd, *args],
        capture_output=True, text=True, env=env, timeout=timeout,
    )


def _step55_env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env.pop("ODOO_AI_INSTANCES", None)
    return env


def _run55_test_verb(tmp_path: Path, *, odoo_output: str, exit_code: int = 0):
    """Run the `test` verb against a fake odoo-bin that emits `odoo_output`."""
    fake_bin = tmp_path / "odoo-bin"
    _write_stub(fake_bin, f'cat <<"EOF"\n{odoo_output}\nEOF\nexit {exit_code}\n')
    fake_py = tmp_path / "fake-py-bin" / "python"
    fake_py.parent.mkdir(exist_ok=True)
    real = shutil.which("python3") or "/usr/bin/python3"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server (preflight)"; exit 0; fi
        if [[ "$1" == "{fake_bin}" ]]; then shift; exec bash "{fake_bin}" "$@"; fi
        exec {real} "$@"
    """))
    addons = tmp_path / "addons"
    addons.mkdir(exist_ok=True)
    env = _step55_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    res = _run55("test", "--db", "testdb", "--python", str(fake_py),
                 "--addons", str(addons), "--modules", "sale",
                 "--version", "17.0", env=env)
    log = next(
        (line.split("=", 1)[1] for line in res.stdout.splitlines()
         if line.startswith("LOG_PATH=")), "")
    return res, Path(log), env


def _write_stamped_log(tmp_path: Path, name: str, *, verb: str, series: str, body: str) -> Path:
    """A log shaped exactly as 55-instance-ops.sh opens one: the run-verb stamp
    first, then odoo's own output."""
    log = tmp_path / name
    log.write_text(f"ODOO_AI_RUN_VERB={verb} SERIES={series}\n{body}\n", encoding="utf-8")
    return log


@requires_bash
def test_step55_test_verb_reports_the_scope_it_actually_covered(tmp_path):
    """How many modules loaded and how many tests ran are MACHINE output.

    Left as prose instructions, both figures depend on an agent hand-running two
    greps and hand-writing the numbers into free text - the same discretion that
    produced the original silent cover-up. The caller must RECEIVE them.
    """
    res, log, _env = _run55_test_verb(
        tmp_path, odoo_output=f"{_PROGRESS_LINE}\n{_LOADED_MARKER}\n{_MODERN_SUMMARY}")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "MODULES_LOADED=3" in res.stdout, (
        f"the number of modules loaded must be emitted\nstdout:\n{res.stdout}"
    )
    assert "TESTS_RUN=5" in res.stdout, (
        f"the number of tests that ran must be emitted\nstdout:\n{res.stdout}"
    )
    # The pre-existing lines other consumers parse must be untouched.
    for kept in ("TEST_RESULT=passed", "TEST_FAILED=0", "TEST_SKIPPED=0", "FINDINGS_PATH="):
        assert kept in res.stdout, f"{kept} must still be emitted\nstdout:\n{res.stdout}"


@requires_bash
def test_step55_test_verb_log_is_self_describing_and_carries_its_verdict(tmp_path):
    """The log must say WHICH verb produced it, and end up holding the verdict.

    `wait-log` reads nothing but the log, so a verdict that only ever reaches the
    script's stdout is unreachable by construction - the caller then waits for a
    `TEST_RESULT=` that no polling call can ever show it.
    """
    res, log, env = _run55_test_verb(
        tmp_path, odoo_output=f"{_PROGRESS_LINE}\n{_LOADED_MARKER}\n{_MODERN_SUMMARY}")
    assert res.returncode == 0, res.stdout + res.stderr
    contents = log.read_text(encoding="utf-8")
    assert contents.startswith("ODOO_AI_RUN_VERB=test"), (
        f"the log must be stamped with its run verb\nlog head:\n{contents[:200]}"
    )
    assert "SERIES=17.0" in contents.splitlines()[0], (
        f"the stamp must carry the series so the era gate can be resolved\n{contents[:200]}"
    )
    assert "TEST_RESULT=passed" in contents, (
        f"the verdict must be IN the log, where wait-log can reach it\n{contents[-400:]}"
    )

    waited = _run55("wait-log", "--log", str(log), "--timeout", "0", env=env)
    assert "TEST_RESULT=passed" in waited.stdout, (
        f"wait-log must surface the verdict the log carries\nstdout:\n{waited.stdout}"
    )
    assert "BUILD_RESULT=success" in waited.stdout, waited.stdout


@requires_bash
def test_step55_wait_log_does_not_certify_a_test_run_at_modules_loaded(tmp_path):
    """"Modules loaded." is NOT completion for a test run.

    Odoo logs it before the post-install suite starts, so certifying there tells
    the agent to stop waiting while the tests have not begun - and the dispatch
    then reports `tests-inconclusive` for a run that would have passed or failed
    cleanly.
    """
    log = _write_stamped_log(tmp_path, "test-run.log", verb="test", series="17.0",
                             body=f"{_PROGRESS_LINE}\n{_LOADED_MARKER}")
    env = _step55_env(tmp_path)
    res = _run55("wait-log", "--log", str(log), "--timeout", "0", env=env)
    assert "BUILD_RESULT=success" not in res.stdout, (
        f"a test run with no ran-marker must not be certified complete\nstdout:\n{res.stdout}"
    )
    assert "BUILD_RESULT=timeout" in res.stdout, (
        f"the wait must report that no terminal marker was seen yet\nstdout:\n{res.stdout}"
    )


@requires_bash
@pytest.mark.parametrize("series,summary", [
    ("17.0", _MODERN_SUMMARY),
    ("12.0", "2026-01-01 00:00:00,000 1 INFO testdb odoo.tests: Ran 5 tests in 1.234s"),
])
def test_step55_wait_log_certifies_a_test_run_on_its_own_ran_marker(tmp_path, series, summary):
    """A test run's terminal predicate is the era-correct "the suite ran" marker -
    the regexes this script already holds, era-gated exactly as the verdict parser
    gates them (v8-v13 runner trailer, v14+ per-database summary)."""
    # Deliberately WITHOUT "Modules loaded.": the ran-marker must be what
    # certifies, so the assertion cannot be satisfied by the install predicate.
    log = _write_stamped_log(tmp_path, "test-ran.log", verb="test", series=series,
                             body=f"{_PROGRESS_LINE}\n{summary}")
    env = _step55_env(tmp_path)
    res = _run55("wait-log", "--log", str(log), "--timeout", "0", env=env)
    assert res.returncode == 0, f"[{series}] {res.stdout}\n{res.stderr}"
    assert "BUILD_RESULT=success" in res.stdout, (
        f"[{series}] a completed suite must be certified complete\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_step55_wait_log_still_certifies_an_install_build_at_modules_loaded(tmp_path):
    """For an install/update build "Modules loaded." IS completion - the verdict
    _install_confirmed reaches on the same log. Splitting the test predicate must
    not move this one."""
    log = _write_stamped_log(tmp_path, "init-run.log", verb="init", series="17.0",
                             body=f"{_PROGRESS_LINE}\n{_LOADED_MARKER}")
    env = _step55_env(tmp_path)
    res = _run55("wait-log", "--log", str(log), "--timeout", "0", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "BUILD_RESULT=success" in res.stdout, res.stdout
