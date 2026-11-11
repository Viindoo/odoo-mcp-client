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
  - step 50: the generated conf requests unaccent, so a database this launch
    CREATES is born with the extension. Odoo's creation path never runs again
    for that database, so a miss here is permanent and silent.

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
from types import SimpleNamespace

import pytest

import odoo_tree_fixtures as trees
from conftest import farm_path, real_python3, run_and_reap

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


def _launcher(path: Path, body: str, series: str = "17.0") -> None:
    """A stub Odoo launcher whose directory is a fixture checkout of `series`
    (tests/odoo_tree_fixtures.py), as a real launcher's is: the steps read the
    checkout's option facts (main-port key, --dev shape) from its config.py."""
    _write_stub(path, body)
    trees.write_checkout(path.parent, series, with_addons=False)


# Every binary that can give this plugin a PostgreSQL client surface, plus the
# container runtime that can lend it one. A probe ladder rung is gated on
# `command -v <one of these>`, so their PRESENCE is what selects a rung.
_PG_CLIENT_BINS = (
    "pg_isready", "psql", "createdb", "dropdb", "pg_dump", "pg_restore", "docker",
)


# `_client_free_path` used to build its own per-test symlink farm here. The farm
# is a pure function of (ambient PATH, drop-set) - a session-level constant - so
# it now comes from the shared, session-scoped `path_farm` fixture in
# conftest.py (one farm per distinct drop-set for the whole run, not one per
# test). The builder functions below are plain functions, not fixture
# consumers, so they receive the farm through `_bind_path_farm`'s bridge.
_PATH_FARM: dict = {}


@pytest.fixture(autouse=True)
def _bind_path_farm(path_farm):
    """Bridge the session-scoped `path_farm` factory into this file's builders."""
    _PATH_FARM["get"] = path_farm


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

    CALLERS MUST CONSUME THE RETURN VALUE (see _require_real_timeout): discarded,
    it let a case whose name claims the binary arm run the pure-bash FALLBACK arm
    instead - green, under a name describing an arm nothing exercised.
    """
    real = shutil.which("timeout")
    if not real:
        return False
    link = bindir / "timeout"
    if not link.is_symlink() and not link.exists():
        link.symlink_to(real)
    return True


def _require_real_timeout(bindir: Path) -> None:
    """Link the real `timeout` in, or SKIP - for a case that CLAIMS the binary arm.

    The docker rung exists precisely because handing a shell FUNCTION to the
    coreutils binary fails, so a case about that rung must actually reach the
    binary. On a host without it the honest outcome is a named skip: pretending the
    arm ran is how a test stops protecting the thing its name promises.
    """
    if not _link_real_timeout(bindir):
        pytest.skip("no coreutils `timeout` on this host, so the binary arm of "
                    "pg_bounded_run cannot be exercised here")


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
    _launcher(odoo_bin, 'echo "Odoo Server 17.0"\n')
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

    real_py3 = real_python3()

    if odoo_runnable:
        # `<py> <odoo-bin> --version` -> exit 0; everything else -> real python3
        # An `import odoo` probe FAILS, so recording the python proves the gate is
        # `<py> <odoo-bin> --version`, never an import check.
        py_body = textwrap.dedent(f"""\
            if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
            if [[ "$1" == "-c" && "$2" == "import odoo" ]]; then exit 1; fi
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
                    # No-op: fake venv already at the target path. The call is logged:
                    # a run that refuses before building must never reach it.
                    echo "uv $*" >> "{pip_log}"
                    exit 0 ;;
                pip)
                    echo "uv pip $*" >> "{pip_log}"
                    exit 0 ;;
                *) exit 0 ;;
            esac
        """),
    )
    return bind, pip_log


def _step45_path(bind: Path) -> str:
    """PATH for a step-45 run: the stub dir in front of the ambient PATH WITHOUT any
    Postgres client. `create-venv` ends by asking whether Postgres answers; a client
    installed on the host would question whatever cluster it finds there (and a password
    prompt on a pipe sits out the whole probe bound)."""
    return farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS), bind)


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
    env["PATH"] = _step45_path(bind)
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
def test_step45_records_python_once_odoo_bin_runs_and_installs_every_requirements_file(tmp_path):
    """The python field is recorded ONLY because `<py> <odoo-bin> --version` exits 0
    (the venv stub fails an `import odoo` probe, so an import gate would not record),
    and every repeatable --requirements file is installed, in order."""
    core = _make_core_dir(tmp_path)
    toml = _make_instances_toml(tmp_path, addons_path=str(core / "addons"))
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, pip_log = _make_step45_stub_bin(tmp_path, venv_dir)
    req1 = tmp_path / "req-core.txt"
    req2 = tmp_path / "req-addons.txt"
    req1.write_text("# core requirements\n", encoding="utf-8")
    req2.write_text("# addon requirements\n", encoding="utf-8")

    res = _run_step45(
        tmp_path, bind, toml, venv_dir, series="17.0",
        extra_args=["--requirements", str(req1), "--requirements", str(req2)],
    )
    out = res.stdout + res.stderr

    assert res.returncode == 0, f"Expected success.\n{out}"
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' not in content and "bin/python" in content, (
        f"the venv python must be recorded once odoo-bin runs.\nTOML:\n{content}"
    )
    assert pip_log.exists(), f"uv pip install was never called.\n{out}"
    logged = pip_log.read_text(encoding="utf-8")
    assert str(req1) in logged and str(req2) in logged, (
        f"each --requirements file must be installed.\nlogged:\n{logged}"
    )
    assert logged.index(str(req1)) < logged.index(str(req2)), "files install in the order given"


@requires_bash
def test_step45_empty_venv_does_not_record_python(tmp_path):
    """When venv python cannot run `<py> <odoo-bin> --version`, step 45 fails and records nothing."""
    core = _make_core_dir(tmp_path)
    toml = _make_instances_toml(tmp_path, addons_path=str(core / "addons"))
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=False)
    bind, _pip_log = _make_step45_stub_bin(tmp_path, venv_dir)

    res = _run_step45(tmp_path, bind, toml, venv_dir, series="17.0")

    assert res.returncode != 0, (
        f"Expected non-zero exit when odoo-bin --version fails.\n{res.stdout}{res.stderr}"
    )
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when odoo-bin --version fails.\nTOML:\n{content}"
    )


@requires_bash
def test_step45_fails_loud_when_core_repo_missing(tmp_path):
    """When addons_path has no dir with odoo-bin, step 45 must exit non-zero
    and must NOT record python."""
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
    content = toml.read_text(encoding="utf-8")
    assert 'python = ""' in content, (
        f"python field must remain blank when core repo is missing.\nTOML:\n{content}"
    )


# ---------------------------------------------------------------------------
# M1: no-profile create-venv must NOT clobber a profiled block
# ---------------------------------------------------------------------------

@requires_bash
def test_step45_no_profile_refuses_before_building_and_leaves_a_profiled_block_alone(tmp_path):
    """create-venv without --profile, when the toml holds ONLY profiled blocks for
    the series, must refuse (non-zero) BEFORE any venv is built, and must leave the
    catalog byte-identical: it never guesses which profiled block to record into."""
    core = _make_core_dir(tmp_path)
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
            addons_path = "{core / 'addons'}"
        """),
        encoding="utf-8",
    )
    original_content = toml.read_text(encoding="utf-8")
    venv_dir = _make_fake_venv(tmp_path, odoo_runnable=True)
    bind, uv_log = _make_step45_stub_bin(tmp_path, venv_dir)

    env = dict(os.environ)
    env["PATH"] = _step45_path(bind)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    # No --profile AND no --path: the guard fires before the venv path is computed.
    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0", "--tool", "uv"],
        capture_output=True, text=True, env=env,
    )

    assert res.returncode != 0, f"must refuse without --profile.\n{res.stdout}{res.stderr}"
    assert toml.read_text(encoding="utf-8") == original_content, "the catalog must be unchanged"
    assert not uv_log.exists(), (
        f"nothing may be built once the guard refuses:\n{uv_log.read_text(encoding='utf-8')}"
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
def test_step45_per_profile_venv_lands_at_the_profile_path_and_only_its_block_records_python(tmp_path):
    """With --profile minimal_17 and NO --path, the venv is auto-derived at
    $ODOO_AI_HOME/venvs/17.0-minimal_17 (series + profile slug), and python is
    recorded in the [[instance]] block of series=17.0 AND profile=minimal_17 -
    never in the sibling profile's block."""
    core = _make_core_dir(tmp_path)
    addons_path = str(core / "addons")
    block = textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        profile = "{profile}"
        instance_key = "17.0:{profile}"
        python = ""
        http_port = {port}
        db_name = "odoo_17_0_{profile}"
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = "%s"
    """) % addons_path
    toml = tmp_path / "instances.toml"
    toml.write_text(
        block.format(profile="minimal_17", port=8069) + "\n" + block.format(profile="full_17", port=8079),
        encoding="utf-8",
    )

    # Pre-create the venv at the auto-derived location with a python stub so the uv
    # stub no-ops and the gate finds the right python.
    expected_venv = tmp_path / "odoo-ai-home" / "venvs" / "17.0-minimal_17"
    venv_bin = expected_venv / "bin"
    venv_bin.mkdir(parents=True)
    real_py3 = real_python3()
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
    env["PATH"] = _step45_path(bind)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    res = subprocess.run(
        ["bash", str(STEP45), "create-venv", "--series", "17.0",
         "--profile", "minimal_17", "--tool", "uv"],
        capture_output=True, text=True, env=env,
    )

    assert res.returncode == 0, f"Expected success.\n{res.stdout}{res.stderr}"
    blocks = toml.read_text(encoding="utf-8").split("[[instance]]")
    minimal_block = next((b for b in blocks if 'profile = "minimal_17"' in b), "")
    full_block = next((b for b in blocks if 'profile = "full_17"' in b), "")
    assert minimal_block and full_block, f"both profile blocks must survive:\n{blocks}"
    assert str(expected_venv / "bin" / "python") in minimal_block, (
        f"the auto-derived venv python must be recorded in the minimal_17 block.\n{minimal_block}"
    )
    assert 'python = ""' in full_block, f"the sibling profile's block must stay untouched.\n{full_block}"


# ---------------------------------------------------------------------------
# step 50 tests
# ---------------------------------------------------------------------------

def _make_step50_toml(
    tmp_path: Path, *, series: str = "17.0", py_path: str, profile: str | None = None,
) -> Path:
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
        """) + (
            f'profile = "{profile}"\ninstance_key = "{series}:{profile}"\n' if profile else ""
        ),
        encoding="utf-8",
    )
    return toml


def _make_step50_fake_py(
    tmp_path: Path, *, odoo_importable: bool, gate_log: Path | None = None,
) -> Path:
    """Standalone fake python binary (not inside a venv dir) for step 50 tests.

    Intercepts `<py> <odoo-bin> --version` (gate call) based on odoo_importable.
    Passes through all other calls to real python3 (e.g. instances_io.py calls).
    The parameter name retains `odoo_importable` for call-site readability, but
    the stub now controls `<py> <odoo-bin> --version` behavior.
    """
    real_py3 = real_python3()
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
    if gate_log is not None:  # record WHICH launcher the gate was asked about
        body = f'if [[ "$2" == "--version" ]]; then echo "$1" >> "{gate_log}"; fi\n' + body
    _write_stub(fake_py, body)
    return fake_py


# ---------------------------------------------------------------------------
# step 50 <-> instances_io: a REAL 2-entry addons_path must resolve odoo-bin -
# _find_odoo_bin's split must match what instances_io.py's join_addons_path
# actually emits, not a value that only happens to be right for a
# single-entry addons_path.
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_a_failing_version_gate_stops_the_spinup_at_the_launcher_found_in_a_real_two_entry_addons_path(tmp_path):
    """Two behaviours on one run. (1) The odoo-bin SCAN must locate the launcher
    when INST_ADDONS_PATH carries 2+ entries produced by the ACTUAL instances_io.py
    pipeline (a genuine TOML array -> join_addons_path -> INST_ADDONS_PATH), found
    under the SECOND entry with no ODOO_BIN override - the dimension a
    producer/consumer separator mismatch once slipped through. (2) When
    `<py> <odoo-bin> --version` fails, step 50 exits non-zero BEFORE launching
    anything or entering the readiness poll."""
    # Entry 1: a plain custom-addons repo - no odoo-bin here.
    custom_dir = tmp_path / "custom-addons"
    custom_dir.mkdir(parents=True)
    # Entry 2: the real Odoo core dir (has odoo-bin under it).
    core = _make_core_dir(tmp_path)
    core_addons = str(core / "addons")

    gate_log = tmp_path / "version-gate-calls.log"
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=False, gate_log=gate_log)

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

    assert gate_log.exists(), f"the gate was never asked: the scan did not resolve a launcher\n{out}"
    assert gate_log.read_text(encoding="utf-8").split() == [str(core / "odoo-bin")], (
        "the gate must be asked about the launcher found under the SECOND addons_path entry"
    )
    assert res.returncode != 0, f"a failing gate must stop the spin-up\n{out}"
    assert "Polling" not in out, f"the readiness poll was entered despite the failed gate\n{out}"


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


def _make_step50_spinup_env(
    tmp_path: Path, *, curl_mode: str, profile: str | None = None, lifetime: int = 15,
):
    """A source-mode step-50 scenario whose preflights PASS and whose 'odoo-bin'
    launch is faked by the python stub (logs the launch, then `exec sleep` to
    stay alive with a clean pid). curl_mode: 'up' (always 200), 'down' (always
    000), 'up_after_launch' (000 on the first probe, 200 thereafter). Every curl
    request is appended to `<tmp_path>/curl.log`.

    The stub ANSWERS a bounded `odoo_db.py` question and returns, as a real venv
    python does: only an odoo-bin invocation stays up. A stub that ran the launch
    body for the DB preflight too would hang it until its bound (10s) and make
    every spin-up test measure the fixture."""
    launch_log = tmp_path / "odoo-launch.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    # `<py> <odoo-bin> --version` -> exit 0 (preflight passes); an `import odoo` probe
    # fails (the retired gate); a real launch -> log + stay alive.
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        if [[ "$1" == *odoo_db.py ]]; then echo "DB_AUTH=ok"; exit 0; fi
        if [[ "$1" == "-c" ]]; then exit 1; fi
        echo "odoo-bin launched $*" >> "{launch_log}"
        echo $$ >> "{tmp_path}/server.pids"
        exec sleep {lifetime}
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _launcher(odoo_bin, "exit 0\n")  # only needs to be executable for _find_odoo_bin

    bind = tmp_path / "bin50"
    bind.mkdir(exist_ok=True)
    curl_log = tmp_path / "curl.log"
    record = f'echo "$*" >> "{curl_log}"\n'
    if curl_mode == "up":
        _write_stub(bind / "curl", record + 'echo "200"\n')
    elif curl_mode == "down":
        _write_stub(bind / "curl", record + 'echo "000"\n')
    else:  # up_after_launch: 000 on the first probe, 200 once the server "launched"
        cnt = tmp_path / "curl.count"
        _write_stub(bind / "curl", record + textwrap.dedent(f"""\
            n="$(cat "{cnt}" 2>/dev/null || echo 0)"
            echo $((n + 1)) > "{cnt}"
            if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi
        """))
    _write_stub(bind / "pg_isready", "exit 0\n")  # reachable -> skip the real-PG preflight

    toml = _make_step50_toml(tmp_path, series="17.0", py_path=str(fake_py), profile=profile)
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
    # run_and_reap, never subprocess.run: this step launches a background server it rightly
    # leaves running, and an unreaped stub outlives the whole session (conftest.run_and_reap).
    return run_and_reap(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        env=env, timeout=30,
    )


def _run_step50_args(env, *extra_args) -> subprocess.CompletedProcess:
    return run_and_reap(
        ["bash", str(STEP50), "apply", "--version", "17.0", *extra_args],
        env=env, timeout=30,
    )


def _wait_exists(path: Path, timeout_s: float = 10.0) -> bool:
    """The launch is backgrounded: `apply` can return before the stand-in server has
    written its first line, so a test reading its launch log waits for it."""
    deadline = time.monotonic() + timeout_s
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return path.exists()


def _stop_servers(home: Path) -> None:
    """Stop every server stand-in (`sleep`) a spin-up of `home` launched."""
    pidfile = home.parent / "server.pids"
    pids = pidfile.read_text(encoding="utf-8").split() if pidfile.exists() else []
    for pid in pids:
        if _alive(pid):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except OSError:
                pass


@pytest.fixture(scope="module")
def spinup_ok(tmp_path_factory):
    """ONE successful declared/shared spin-up (the allocator is on, the owner run
    id and a gevent port pair are given). Every test below that only reads what a
    good spin-up leaves behind - lease, log, conf, probe requests - reads this
    run instead of paying for its own."""
    tmp = tmp_path_factory.mktemp("spinup_ok")
    env, home, launch_log = _make_step50_spinup_env(
        tmp, curl_mode="up_after_launch", lifetime=300)
    env["INST_RUN_ID"] = "run-owner-xyz"
    res = _run_step50_args(
        env, "--gevent-port", "9069", "--gevent-port-key", "longpolling_port")
    out = res.stdout + res.stderr
    _wait_exists(launch_log)
    ns = SimpleNamespace(
        res=res, out=out, home=home, launch_log=launch_log, tmp=tmp,
        conf=_generated_conf_text(out) if res.returncode == 0 else "",
    )
    yield ns
    _stop_servers(home)


@requires_bash
def test_step50_registers_shared_lease_after_server_up(spinup_ok):
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    assert spinup_ok.launch_log.exists(), f"odoo-bin must have launched\n{spinup_ok.out}"
    leases = _leases_at(spinup_ok.home)
    shared = [lz for lz in leases if lz.get("mode") == "shared"]
    assert len(shared) == 1, f"step 50 must register exactly one shared lease\n{leases}"
    lz = shared[0]
    assert lz["series"] == "17.0"
    assert lz["ports"] == [18069], "the lease records the actual bound port"
    assert lz["drop_on_release"] is False, "the shared render lease must NEVER own the declared DB"
    pid = lz["owner"]["pid"]
    assert pid and _alive(pid), "the live server pid is recorded (for gc + cross-session discovery)"


@requires_bash
def test_step50_shared_lease_is_owner_stamped_with_the_callers_run_id(spinup_ok):
    """When the caller sets INST_RUN_ID before apply, the shared lease it registers
    is owner-stamped instead of unowned."""
    shared = [lz for lz in _leases_at(spinup_ok.home) if lz.get("mode") == "shared"]
    assert len(shared) == 1, f"expected exactly one shared lease\n{_leases_at(spinup_ok.home)}"
    assert shared[0]["owner"].get("run_id") == "run-owner-xyz", (
        f"the shared lease must be owner-stamped with INST_RUN_ID; got {shared[0]['owner']!r}"
    )


@requires_bash
def test_step50_readiness_probes_the_database_selector_first(spinup_ok):
    """The readiness probe's PRIMARY endpoint is /web/database/selector: the whole
    spin-up (the 'already up' pre-check and the poll that confirmed it) asked only
    that endpoint, never the /web/login fallback."""
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    requests = (spinup_ok.tmp / "curl.log").read_text(encoding="utf-8").splitlines()
    assert requests and all("/web/database/selector" in r for r in requests), requests


@requires_bash
def test_step50_gate_is_odoo_bin_version_never_an_import(spinup_ok):
    """The python stub PASSES `<py> <odoo-bin> --version` but FAILS an `import odoo`
    probe: the spin-up only gets through its preflight and launches if the gate is
    the former."""
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    assert spinup_ok.launch_log.exists(), f"the launch was blocked by the preflight\n{spinup_ok.out}"


@requires_bash
def test_step50_apply_writes_log_under_odoo_ai_home(spinup_ok):
    """apply writes the Odoo log to <ODOO_AI_HOME>/logs/<db>-<ts>.log and emits ONE
    parseable 'LOG_PATH=<path>' line on stdout, so a calling agent can capture the
    log location without screen-scraping."""
    res = spinup_ok.res
    assert res.returncode == 0, f"Expected success.\nstdout: {res.stdout}\nstderr: {res.stderr}"
    log_path_lines = [line for line in res.stdout.splitlines() if line.startswith("LOG_PATH=")]
    assert len(log_path_lines) == 1, f"Expected exactly one LOG_PATH= line.\n{res.stdout}"
    log_path = Path(log_path_lines[0].split("=", 1)[1])
    assert log_path.parent == spinup_ok.home / "logs"
    assert log_path.name.startswith("odoo_test-") and log_path.suffix == ".log", log_path.name
    assert log_path.exists(), f"LOG_PATH file {log_path} does not exist (redirect failed?)"


@requires_bash
def test_step50_gevent_port_and_key_together_writes_conf_line(spinup_ok):
    """--gevent-port + --gevent-port-key given TOGETHER succeed and the generated
    conf carries the second listening-port line under the agent-resolved key."""
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    assert "longpolling_port = 9069" in spinup_ok.conf, spinup_ok.conf


@requires_bash
def test_step50_conf_carries_limit_memory_hard_soft_and_time_real(spinup_ok):
    conf = spinup_ok.conf
    for key in ("limit_memory_hard", "limit_memory_soft", "limit_time_real"):
        assert re.search(rf"^{key} = \d+$", conf, re.MULTILINE), (
            f"conf must carry a numeric {key} key.\nconf:\n{conf}"
        )


@requires_bash
def test_step50_conf_never_carries_limit_time_cpu_while_workers_zero(spinup_ok):
    """limit_time_cpu must never appear at all while workers=0 - a dead key
    would give false confidence that a runaway request is bounded."""
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    assert "limit_time_cpu" not in spinup_ok.conf, spinup_ok.conf


@requires_bash
def test_step50_conf_requests_unaccent_for_a_database_it_may_create(spinup_ok):
    """The spin-up conf must carry `unaccent = True`: this launch CREATES the
    database whenever it is the first to name a missing one, and creation is the
    only moment unaccent can still be installed."""
    assert spinup_ok.res.returncode == 0, spinup_ok.out
    assert re.search(r"^unaccent = True$", spinup_ok.conf, re.MULTILINE), spinup_ok.conf


@pytest.fixture(scope="module")
def spinup_never_ready(tmp_path_factory):
    """ONE spin-up whose server never answers on either endpoint (the poll times out)."""
    tmp = tmp_path_factory.mktemp("spinup_never_ready")
    env, home, _ = _make_step50_spinup_env(tmp, curl_mode="down")
    env["SPINUP_TIMEOUT"] = "2"
    started = time.monotonic()
    res = _run_step50(env)
    return SimpleNamespace(
        res=res, out=res.stdout + res.stderr, home=home, elapsed=time.monotonic() - started)


@requires_bash
def test_step50_leaves_no_shared_lease_when_server_never_comes_up(spinup_never_ready):
    assert spinup_never_ready.res.returncode != 0, (
        f"a never-ready spin-up must fail\n{spinup_never_ready.out}"
    )
    assert _leases_at(spinup_never_ready.home) == [], (
        "a failed spin-up must leave NO shared lease (registration happens only after the server is up)"
    )


@requires_bash
def test_step50_readiness_poll_is_bounded_never_hangs(spinup_never_ready):
    """The readiness poll (primary + fallback) is BOUNDED by SPINUP_TIMEOUT - a
    server that never becomes ready on EITHER endpoint returns within a small,
    deterministic wall-clock bound, never hangs indefinitely."""
    assert spinup_never_ready.res.returncode != 0, spinup_never_ready.out
    assert spinup_never_ready.elapsed < 20, (
        f"the poll must be BOUNDED by SPINUP_TIMEOUT (=2s); took {spinup_never_ready.elapsed:.1f}s"
    )


@requires_bash
def test_step50_attaches_to_existing_shared_lease_without_relaunch(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up")
    # Pre-seed a LIVE shared lease (pid = this pytest process, which is alive).
    pre = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0", "--mode", "shared",
         "--port", "18069", "--db-name", "odoo_test", "--pid", str(os.getpid()), "--allow-unowned"],
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


# ---------------------------------------------------------------------------
# Root-cause fix: the readiness signal is a BOUNDED HTTP-port poll of
# /web/database/selector (primary, docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md item
# 14), fallback /web/login - never a log tail, never an unbounded wait.
# ---------------------------------------------------------------------------

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
    env["SPINUP_TIMEOUT"] = "1"
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
    assert _wait_exists(launch_log), (
        f"the selector-only 'already up' pre-check must see 000 and proceed to launch, "
        f"then the poll's fallback must confirm readiness on /web/login\n{out}"
    )


@requires_bash
def test_step50_degrades_to_plain_spinup_without_allocator(tmp_path):
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    env["ODOO_AI_ALLOCATOR"] = ""  # disable allocator coordination
    res = _run_step50(env)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "is up:" in out, f"the server must still spin up and print its URL\n{out}"
    assert _wait_exists(launch_log), "the server must still launch when the allocator is disabled"
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


@pytest.fixture(scope="module")
def exclusive_runs(tmp_path_factory):
    """The --exclusive spin-ups against ONE reserved lease: a launch naming a
    database the lease does not hold (refused), the launch naming its own database
    (the lease's pid is bound onto it), and a token-less launch on the caller's own
    db and port. Each run is paid once; the tests below read what it left."""
    tmp = tmp_path_factory.mktemp("exclusive_runs")
    env, home, launch_log = _make_step50_spinup_env(
        tmp, curl_mode="up_after_launch", lifetime=300)
    built_db = "odoo_17_0_t_builtleg"
    # --no-create keeps this a pure RESERVATION: it skips the allocator's own
    # cluster preflight, so the launch log only ever records the spin-ups below.
    acq = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "exclusive", "--db-name", built_db, "--run-id", "run-excl",
         "--no-create"],
        capture_output=True, text=True, env=env,
    )
    assert acq.returncode == 0, acq.stderr
    token = next(
        line.split("=", 1)[1].strip().strip("'")
        for line in acq.stdout.splitlines() if line.startswith("ALLOC_TOKEN=")
    )
    ns = SimpleNamespace(home=home, token=token, built_db=built_db,
                         lease_before=[lz for lz in _leases_at(home) if lz.get("token") == token][0],
                         launched_by_acquire=launch_log.exists())

    def spin(*args):
        launch_log.unlink(missing_ok=True)
        (tmp / "curl.count").unlink(missing_ok=True)  # the first probe says 'down' again
        res = _run_step50_args(env, "--exclusive", "--http-port", "18271",
                               "--port-key", "http_port", *args)
        if res.returncode == 0:
            _wait_exists(launch_log)
            # The log already holds the stand-in's answer to the DB preflight; the server's own
            # line (`-c <conf> -d <db>`) follows once the memory-capped launcher has exec'd it.
            deadline = time.monotonic() + 10
            while (not launch_log.exists() or " -d " not in launch_log.read_text(encoding="utf-8")) \
                    and time.monotonic() < deadline:
                time.sleep(0.05)
        launched = launch_log.read_text(encoding="utf-8") if launch_log.exists() else None
        return SimpleNamespace(res=res, out=res.stdout + res.stderr, launched=launched,
                               leases=_leases_at(home))

    ns.wrong_db = spin("--db-name", "odoo_17_0_t_someotherdb", "--alloc-token", token)
    ns.own_db = spin("--db-name", built_db, "--alloc-token", token)
    ns.tokenless = spin("--db-name", "odoo_17_0_t_deadbeef")
    yield ns
    _stop_servers(home)


@requires_bash
def test_step50_refuses_a_db_name_that_disagrees_with_its_lease(exclusive_runs):
    """ONE DATABASE, BOTH LEGS. `55-instance-ops.sh init` installs the module set
    into the database the lease reserved, then this script launches that SAME
    database listening. Launching a DIFFERENT name makes Odoo create that other
    database EMPTY on the spot: the port answers HTTP 200 and every later check
    reports green against code nobody installed - so the disagreement is refused
    before anything is launched or written."""
    ex = exclusive_runs
    assert not ex.launched_by_acquire, "test setup: the reservation must launch nothing"
    run = ex.wrong_db
    assert run.res.returncode != 0, f"a db-name that disagrees with the lease must BLOCK\n{run.out}"
    assert ex.built_db in run.out, f"the refusal must name the database the lease reserved\n{run.out}"
    assert run.launched is None, f"NOTHING may launch\n{run.out}"
    assert "Generated conf:" not in run.out, f"no conf may be written either\n{run.out}"


@requires_bash
def test_step50_exclusive_binds_launched_pid_onto_the_caller_lease(exclusive_runs):
    """An --exclusive spin-up BINDS the launched server pid onto the caller's
    PRE-ACQUIRED lease (via --alloc-token), so a later release or gc can stop the
    whole process group before dropping the DB."""
    ex = exclusive_runs
    assert ex.lease_before["owner"]["pid"] is None, "exclusive acquire records no pid until the bind"
    run = ex.own_db
    assert run.res.returncode == 0, f"the matching db name must spin up\n{run.out}"
    assert run.launched is not None, f"odoo-bin must launch when both legs agree\n{run.out}"
    lease_after = [lz for lz in run.leases if lz.get("token") == ex.token]
    assert lease_after, f"the exclusive lease must survive (never a shared row)\n{run.leases}"
    pid = lease_after[0]["owner"]["pid"]
    assert pid and _alive(int(pid)), "the bound pid must be the live server"
    assert not [lz for lz in run.leases if lz.get("mode") == "shared"], (
        "the exclusive branch must NOT register a shared render lease"
    )


@requires_bash
def test_step50_exclusive_uses_allocator_port_and_db_skips_shared_lease(exclusive_runs):
    """--exclusive --db-name --http-port --port-key spins up the CALLER's own
    pre-leased db/port (not the declared 18069/odoo_test), with or without a token,
    and registers NO shared lease - the DB is already owned by the caller's own
    acquire, not a second shared render-target row."""
    for label, run, db in (("with a token", exclusive_runs.own_db, exclusive_runs.built_db),
                           ("without a token", exclusive_runs.tokenless, "odoo_17_0_t_deadbeef")):
        assert run.res.returncode == 0, f"[{label}] {run.out}"
        assert db in run.launched, (
            f"[{label}] launch must target the ALLOCATOR-issued db, not the declared odoo_test\n{run.launched}"
        )
        assert not [lz for lz in run.leases if lz.get("mode") == "shared"], (
            f"[{label}] --exclusive must register NO shared lease\n{run.leases}"
        )
        assert "http_port = 18271" in _generated_conf_text(run.out), (
            f"[{label}] conf must bind the allocator-issued port"
        )


@requires_bash
def test_step50_refuses_run_id_and_teaches_where_ownership_is_recorded(tmp_path):
    """This script records ownership on NO path: the --exclusive lease was
    already owner-stamped by the caller's acquire, and the shared/declared path
    reads INST_RUN_ID from the environment. A caller that passes --run-id here
    therefore set nothing.

    The refusal must stay a refusal - accept-and-ignore would turn a loud
    immediate failure into a silent no-op and leave the caller believing it
    stamped an owner - and it must NAME the call that does record ownership,
    because a bare "Unknown arg" leaves the caller guessing at a flag that looks
    exactly right. A wholly unknown flag must still get the generic message, so
    this teaches about one real confusion rather than blanket-explaining typos.
    """
    env, _home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up")
    res = _run_step50_args(
        env, "--exclusive", "--db-name", "odoo_17_0_t_deadbeef",
        "--http-port", "18271", "--port-key", "http_port", "--run-id", "run-excl",
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, f"--run-id must be REFUSED, never accepted-and-ignored\n{out}"
    assert "allocator.py acquire --run-id" in out, (
        f"the refusal must name where ownership IS recorded, not just reject the flag\n{out}"
    )
    assert "INST_RUN_ID" in out, (
        f"the refusal must also name the env door the shared/declared path uses\n{out}"
    )
    assert not launch_log.exists(), f"a refused arg parse must launch nothing\n{out}"

    generic = _run_step50_args(env, "--not-a-real-flag")
    gout = generic.stdout + generic.stderr
    assert generic.returncode == 2 and "Unknown arg: --not-a-real-flag" in gout, (
        f"an unrelated unknown flag must keep the generic refusal\n{gout}"
    )
    assert "allocator.py acquire --run-id" not in gout, (
        "the self-teaching text belongs to --run-id only; blanket-attaching it to every "
        f"typo makes it noise\n{gout}"
    )


def _make_step50_forking_env(tmp_path: Path):
    """A step-50 source-mode scenario whose 'odoo-bin' launch forks a CHILD (a
    stand-in worker) in the setsid process group and whose curl NEVER answers 200
    (the readiness poll TIMES OUT). BOTH leader and child TRAP SIGTERM (append to a
    marker file and keep running) so only a SIGKILL escalation can reap them.
    Writes '<leader> <child>' to a pidfile. Returns (env, home, pidfile, marker)."""
    pidfile = tmp_path / "grp.pids"
    marker = tmp_path / "term.marker"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    launch_body = textwrap.dedent(f"""\
        trap 'echo leader >> "{marker}"' TERM
        (
          trap 'echo child >> "{marker}"' TERM
          while :; do sleep 1; done
        ) &
        echo "$$ $!" > "{pidfile}"
        while :; do sleep 1; done
    """)
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        # A real venv python ANSWERS a bounded odoo_db.py question and returns;
        # only an odoo-bin invocation launches a server.
        if [[ "$1" == *odoo_db.py ]]; then echo "DB_AUTH=ok"; exit 0; fi
    """) + launch_body)

    odoo_bin = tmp_path / "odoo-bin"
    _launcher(odoo_bin, "exit 0\n")  # only needs to exist for _find_odoo_bin
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
    env["SPINUP_TIMEOUT"] = "1"       # one poll round
    env["SPINUP_STOP_GRACE"] = "1"    # short SIGTERM->SIGKILL escalation bound
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
def test_step50_a_timed_out_exclusive_spinup_binds_its_pid_and_reaps_the_whole_group(tmp_path):
    """On a readiness TIMEOUT the local cleanup stops the whole process GROUP, and
    ESCALATES: SIGTERM the group, wait a bounded grace, then SIGKILL it. Proven with
    a leader AND child that both TRAP SIGTERM - they still end up dead (only SIGKILL
    can do that) and both RECEIVED the group SIGTERM (a bare `kill <leader>` would
    leave the forked worker running against a DB the caller may then drop). The
    launched pid was bound onto the exclusive lease BEFORE the poll, so release or
    gc can always reap regardless of the poll outcome."""
    env, home, pidfile, marker = _make_step50_forking_env(tmp_path)
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
    assert pidfile.exists(), f"the fake server must have launched + forked a child\n{out}"
    leader, child = (int(x) for x in pidfile.read_text().split())

    try:
        lease = [lz for lz in _leases_at(home) if lz.get("token") == token]
        assert lease, "the exclusive lease must survive the timeout"
        assert lease[0]["owner"]["pid"] == leader, (
            "the launched pid must be BOUND onto the lease before the readiness poll"
        )
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
@pytest.mark.parametrize("half", [
    pytest.param(("--gevent-port", "9069"), id="port-without-key"),
    pytest.param(("--gevent-port-key", "longpolling_port"), id="key-without-port"),
])
def test_step50_a_half_specified_gevent_pair_is_blocked(tmp_path, half):
    """--gevent-port and --gevent-port-key come as a PAIR: either alone must BLOCK
    (non-zero, no launch, no lease) rather than silently omitting the second
    listening port from the generated conf."""
    env, home, launch_log = _make_step50_spinup_env(tmp_path, curl_mode="up_after_launch")
    res = _run_step50_args(env, *half)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"{half} alone must be BLOCKED\n{out}"
    assert not launch_log.exists(), f"odoo-bin must NOT launch when the pair is under-specified\n{out}"
    assert _leases_at(home) == [], "a blocked spin-up must write no lease"


# ---------------------------------------------------------------------------
# WI-4 (a): persistent log path under ~/.odoo-ai/logs/ + parseable LOG_PATH=
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WI-4 (b): port config key - xmlrpc_port for v8/9/10, http_port for v11+
# ---------------------------------------------------------------------------

def _make_step50_toml_for_series(tmp_path: Path, series: str, checkout: str | None = None) -> tuple:
    """Return (toml_path, fake_py_path, env) for a source-mode step-50 scenario
    where preflights pass and odoo-bin is a stub that logs launch args. The
    launcher's directory is a fixture checkout of `checkout` (default `series`).
    The scenario does NOT reach the poll step (curl always 000) - we only care
    about the generated conf, not whether the server comes up.
    """
    fake_py = _make_step50_fake_py(tmp_path, odoo_importable=True)

    fake_core = tmp_path / "fake-core"
    fake_addons = fake_core / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = fake_core / "odoo-bin"
    _launcher(fake_bin, f'echo "Odoo Server {series}"\n', series=checkout or series)

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



@pytest.fixture(scope="module")
def series_runs(tmp_path_factory):
    """One `apply` per checkout shape, each paid once: label -> (conf text, the
    'Launching:' line). A checkout declared under another series label
    ('10.0-as-17.0') proves the answers come from the checkout's own option
    facts, never from the series label."""
    runs = {}
    for label, series, checkout in (
        ("8.0", "8.0", None), ("9.0", "9.0", None), ("10.0", "10.0", None),
        ("17.0", "17.0", None), ("10.0-as-17.0", "17.0", "10.0"),
        ("9.0-as-17.0", "17.0", "9.0"),
    ):
        series_tmp = tmp_path_factory.mktemp("series_" + label.replace(".", "_"))
        _, _, env = _make_step50_toml_for_series(series_tmp, series, checkout=checkout)
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
        assert res.returncode == 0, f"Expected success for {label}.\nout:\n{out}"
        launching = [line for line in out.splitlines() if "Launching:" in line]
        assert launching, f"No 'Launching:' line for {label}.\nout:\n{out}"
        # The conf is NOT cleaned up when apply succeeds.
        runs[label] = (_generated_conf_text(out), launching[0])
    return runs


@requires_bash
def test_step50_conf_main_port_key_comes_from_the_checkout(series_runs):
    """The main-port key is the checkout's option dest, never the series label:
    xmlrpc_port for a v8/9/10 checkout (even one declared under 17.0), http_port
    from v11."""
    for label in ("8.0", "9.0", "10.0", "10.0-as-17.0"):
        conf = series_runs[label][0]
        assert "xmlrpc_port" in conf and "http_port" not in conf, f"{label}:\n{conf}"
    conf17 = series_runs["17.0"][0]
    assert "http_port" in conf17 and "xmlrpc_port" not in conf17, conf17


@requires_bash
def test_step50_dev_all_is_gated_by_the_checkouts_own_dev_option(series_runs):
    """--dev=all needs a value-taking --dev (v10+); v9 has only a boolean --dev and
    v8 none, so passing it there would stop Odoo from starting. The gate is the
    checkout's own option, not the series label."""
    for label in ("8.0", "9.0", "9.0-as-17.0"):
        assert "--dev=all" not in series_runs[label][1], f"{label}: {series_runs[label][1]!r}"
    for label in ("10.0", "17.0"):
        assert "--dev=all" in series_runs[label][1], f"{label}: {series_runs[label][1]!r}"


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
    env["PATH"] = _step45_path(bind)
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
# F3: step 50 shared lease must pass --profile to allocator acquire
# ---------------------------------------------------------------------------

@requires_bash
def test_step50_shared_lease_passes_profile_to_allocator(tmp_path):
    """When spinning up a profiled instance, step 50's shared registration passes
    the profile to the allocator, so the lease targets the correct (series, profile)
    slot rather than the first series match."""
    env, home, _launch_log = _make_step50_spinup_env(
        tmp_path, curl_mode="up_after_launch", profile="test_profile", lifetime=60)
    # A sibling profile of the same series, declared FIRST: a registration that forgot
    # the profile would land on "the first series match" - this one.
    toml = Path(env["ODOO_AI_INSTANCES"])
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('[[instance]]', textwrap.dedent("""\
            [[instance]]
            series = "17.0"
            profile = "decoy"
            instance_key = "17.0:decoy"
            python = "/nonexistent/python"
            http_port = 18169
            db_name = "odoo_decoy"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "/nonexistent/addons"

            [[instance]]"""), 1), encoding="utf-8")
    try:
        res = _run_step50_args(env, "--profile", "test_profile")
        out = res.stdout + res.stderr
        assert res.returncode == 0, f"Expected success for profiled instance.\n{out}"
        shared = [lz for lz in _leases_at(home) if lz.get("mode") == "shared"]
        assert len(shared) == 1, f"Expected exactly one shared lease.\n{_leases_at(home)}\n{out}"
        assert shared[0].get("profile") == "test_profile", shared[0]
    finally:
        _wait_exists(tmp_path / "server.pids")
        _stop_servers(home)


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
    conf_lines = [line for line in out.splitlines() if "Generated conf:" in line]
    assert conf_lines, f"no 'Generated conf:' line in output\n{out}"
    conf_path = Path(conf_lines[0].split("Generated conf:")[-1].strip())
    return conf_path.read_text(encoding="utf-8")


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


def _docker_pg_scenario(
    tmp_path: Path, *, docker_body: str, curl_body: str, probe_timeout: int = 5,
):
    """A source-mode step-50 scenario whose Postgres is declared as `docker`.

    Returns (env, out_paths). `docker_body` is the stub daemon's behavior, so one
    fixture covers a healthy daemon, a hanging one, or a refusing one.
    """
    launch_log = tmp_path / "odoo-launch.log"
    docker_log = tmp_path / "docker-calls.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    # The declared interpreter ANSWERS odoo_db.py (so the only probe that can hang is
    # the rung under test); only an odoo-bin invocation launches a server.
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        if [[ "$1" == *odoo_db.py ]]; then echo "DB_AUTH=ok"; exit 0; fi
        echo "odoo-bin launched $*" >> "{launch_log}"
        exec sleep 15
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _launcher(odoo_bin, "exit 0\n")

    bind = tmp_path / "bin50-docker"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", curl_body)
    _write_stub(bind / "docker", f'echo "docker $*" >> "{docker_log}"\n' + docker_body)
    # A REAL `timeout` must be reachable - the arm on which handing a shell
    # function to that coreutils binary fails. Linked in explicitly rather than
    # inferred from a hardcoded /usr/bin:/bin, which is a guess about the host.
    _require_real_timeout(bind)

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
    env["SPINUP_TIMEOUT"] = "1"
    env["SPINUP_STOP_GRACE"] = "1"
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = str(probe_timeout)
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
    assert _wait_exists(launch_log), f"the healthy cluster must not block the launch\n{out}"
    assert docker_log.exists(), f"the probe never invoked docker at all\n{out}"
    calls = docker_log.read_text(encoding="utf-8")
    assert "exec" in calls and "pg-for-tests" in calls and "pg_isready" in calls, (
        f"the probe must run pg_isready INSIDE the declared container; got:\n{calls}"
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


def _unanswered_probe_scenario(tmp_path: Path, rung: str):
    """A source-mode step-50 scenario in which ONE rung of the Postgres preflight
    ladder never answers, every other rung answers fine, and curl never says the
    server is up. Returns (env, launch_log, asked, local_client_calls):
    `asked` is a file the hanging rung writes before it hangs (proof the rung under
    test really ran), `local_client_calls` a file a healthy local pg_isready writes
    when consulted.

    rung: `undeclared-interpreter` (no db_run_mode and NO client installed, so the
    ladder falls to the instance's own interpreter), `tcp-only` (declared: NO client
    surface, a healthy local pg_isready must never be consulted), `native` (a
    hanging pg_isready), `docker` (a hanging container client)."""
    if rung == "docker":
        env, launch_log, docker_log = _docker_pg_scenario(
            tmp_path, docker_body="while :; do :; done\n", curl_body='echo "000"\n',
            probe_timeout=1)
        return env, launch_log, docker_log, tmp_path / "never-written"

    launch_log = tmp_path / "odoo-launch.log"
    asked = tmp_path / "probe-asked.log"
    local_client_calls = tmp_path / "pg_isready-calls.log"
    py_hangs = rung in ("undeclared-interpreter", "tcp-only")
    answer = "while :; do sleep 1; done" if py_hangs else 'echo "DB_AUTH=ok"; exit 0'
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        if [[ "$1" == *odoo_db.py ]]; then echo asked >> "{asked}"; {answer}; fi
        echo "odoo-bin launched $*" >> "{launch_log}"
        exec sleep 15
    """))
    odoo_bin = tmp_path / "odoo-bin"
    _launcher(odoo_bin, "exit 0\n")
    bind = tmp_path / "bin50-probe"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "curl", 'echo "000"\n')  # never ready -> the poll times out
    env = dict(os.environ)
    if rung == "native":
        # The stub SHADOWS whatever client the image ships, so the rung under test is
        # this hanging one on every host.
        _write_stub(bind / "pg_isready", f'echo asked >> "{asked}"\nwhile :; do :; done\n')
        _require_real_timeout(bind)
        extra = 'db_run_mode = "native"\n'
        env["PATH"] = f"{bind}{os.pathsep}{env.get('PATH', '')}"
    elif rung == "tcp-only":
        # A local client that would report a HEALTHY cluster - the false green the
        # declaration exists to refuse; it records every call.
        _write_stub(bind / "pg_isready", f'echo "called $*" >> "{local_client_calls}"\nexit 0\n')
        extra = 'db_run_mode = "tcp-only"\n'
        env["PATH"] = f"{bind}{os.pathsep}{env.get('PATH', '')}"
    else:  # undeclared-interpreter: no client may be reachable, whatever the host ships
        extra = ""
        env["PATH"] = farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS), bind)
    toml = _make_step50_toml_with_pg_surface(tmp_path, py_path=str(fake_py), extra=extra)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "1"
    env["SPINUP_STOP_GRACE"] = "1"
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "1"
    env["ODOO_BIN"] = str(odoo_bin)
    env.pop("ODOO_PG_PASSWORD", None)
    return env, launch_log, asked, local_client_calls


@requires_bash
@pytest.mark.parametrize("rung", ["undeclared-interpreter", "tcp-only", "native", "docker"])
def test_step50_a_probe_that_does_not_answer_is_never_a_reachability_verdict(tmp_path, rung):
    """A bound that elapsed means "the probe did not answer", on EVERY rung of the
    ladder (native client, container client, the instance's own interpreter): it
    says nothing about the cluster, so it must never become `PostgreSQL is not
    reachable` and must not block the launch. A declared `tcp-only` also never
    consults a local client - an installed pg_isready belongs to some OTHER cluster
    and would answer confidently about a database this instance never uses.
    """
    env, launch_log, asked, local_client_calls = _unanswered_probe_scenario(tmp_path, rung)
    res = _run_step50_args(env)  # a 30s subprocess bound: a hang FAILS this test
    out = res.stdout + res.stderr

    assert asked.exists(), f"[{rung}] test setup: the rung under test was never asked\n{out}"
    assert "PREFLIGHT FAILED: PostgreSQL is not reachable" not in out, (
        f"[{rung}] a bound that elapsed says NOTHING about the cluster\n{out}"
    )
    assert _wait_exists(launch_log), f"[{rung}] an unanswered probe must not block the launch\n{out}"
    assert not local_client_calls.exists(), (
        f"[{rung}] a tcp-only declaration must never reach a local client\n"
        f"{local_client_calls.read_text(encoding='utf-8') if local_client_calls.exists() else ''}"
    )


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
    _launcher(fake_bin, f'cat <<"EOF"\n{odoo_output}\nEOF\nexit {exit_code}\n')
    fake_py = tmp_path / "fake-py-bin" / "python"
    fake_py.parent.mkdir(exist_ok=True)
    real = real_python3()
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


@pytest.fixture(scope="module")
def step55_test_run(tmp_path_factory):
    """ONE `test` verb run against a fake odoo-bin that prints a clean modern run,
    plus the `wait-log` read of the log it left."""
    tmp = tmp_path_factory.mktemp("step55_test_run")
    res, log, env = _run55_test_verb(
        tmp, odoo_output=f"{_PROGRESS_LINE}\n{_LOADED_MARKER}\n{_MODERN_SUMMARY}")
    waited = _run55("wait-log", "--log", str(log), "--timeout", "0", env=env)
    return SimpleNamespace(res=res, log=log, waited=waited)


@requires_bash
def test_step55_test_verb_reports_the_scope_it_actually_covered(step55_test_run):
    """How many modules loaded and how many tests ran are MACHINE output: left as
    prose instructions, both figures depend on an agent hand-running two greps and
    hand-writing the numbers into free text. The caller must RECEIVE them."""
    res = step55_test_run.res
    assert res.returncode == 0, res.stdout + res.stderr
    for kept in ("MODULES_LOADED=3", "TESTS_RUN=5",
                 # lines other consumers parse must be untouched
                 "TEST_RESULT=passed", "TEST_FAILED=0", "TEST_SKIPPED=0", "FINDINGS_PATH="):
        assert kept in res.stdout, f"{kept} must be emitted\nstdout:\n{res.stdout}"


@requires_bash
def test_step55_test_verb_log_is_self_describing_and_carries_its_verdict(step55_test_run):
    """The log says WHICH verb produced it and ends up holding the verdict:
    `wait-log` reads nothing but the log, so a verdict that only reached the
    script's stdout would be unreachable by construction."""
    contents = step55_test_run.log.read_text(encoding="utf-8")
    assert contents.startswith("ODOO_AI_RUN_VERB=test"), contents[:200]
    assert "SERIES=17.0" in contents.splitlines()[0], "the stamp must carry the series"
    assert "TEST_RESULT=passed" in contents, "the verdict must be IN the log"
    waited = step55_test_run.waited
    assert "TEST_RESULT=passed" in waited.stdout, waited.stdout
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


# ---------------------------------------------------------------------------
# One question, one answer.
#
# `05-prereq-check.sh` already delegates the DB question to the allocator, which
# owns the ladder `acquire` gates on. `45-venv.sh` re-implemented one route of it
# in shell instead - so on a host whose Postgres is containerised (the instance
# declares no interpreter of its own) the setup step printed "could not determine"
# while the command that runs next answered it perfectly well. Two copies of a
# question is how a setup step came to contradict the command after it.
# ---------------------------------------------------------------------------
def _step45_db_question_env(tmp_path, *, preflight_rc, createdb="true", docker_answer="t"):
    """(env, toml): a record-env scenario carrying BOTH DB routes.

    The declared interpreter answers `odoo_db.py preflight` with `preflight_rc`
    (8 = Odoo was refused authentication), and a stub `docker` stands in for the
    container-local client that would answer the capability question `t`. That is
    the observed host class, and the one where the two routes disagree.
    """
    core = _make_core_dir(tmp_path)
    py_dir = tmp_path / "fake-py-bin"
    py_dir.mkdir(exist_ok=True)
    fake_py = py_dir / "python"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
        if [[ "$1" == *odoo_db.py ]]; then
            case "$2" in
                preflight) echo "DB_AUTH_WHY=stub"; exit {preflight_rc} ;;
                can-createdb) echo "{createdb}"; exit 0 ;;
            esac
            exit 0
        fi
        exit 0
    """))

    bind = tmp_path / "bin45"
    bind.mkdir(exist_ok=True)
    _write_stub(bind / "docker", f'echo "{docker_answer}"\nexit 0\n')
    _require_real_timeout(bind)

    toml = tmp_path / "instances45-db.toml"
    toml.write_text(textwrap.dedent(f"""\
        [[instance]]
        series = "17.0"
        python = "{fake_py}"
        odoo_root = "{core}"
        http_port = 18069
        db_name = "odoo_test"
        db_host = "db.example"
        db_port = 5544
        db_user = "odoo"
        db_run_mode = "docker"
        db_container = "pg-for-tests"
        run_mode = "source"
        addons_path = "{core / 'addons'}"
    """), encoding="utf-8")

    env = dict(os.environ)
    # Every client name is constructed absent, THEN the stub dir is prepended: the
    # only `docker` reachable is this fixture's, and no native client is reachable
    # at all. `path_farm` validates the farm on its own (it may not be handed a
    # stub dir that re-adds a client), so the prepend happens here.
    env["PATH"] = os.pathsep.join(
        [str(bind), farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS))])
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "10"
    env.pop("ODOO_PG_PASSWORD", None)
    return env, toml


def _run_step45_record_env(env, series="17.0"):
    return subprocess.run(
        ["bash", str(STEP45), "record-env", "--series", series],
        capture_output=True, text=True, env=env, timeout=120,
    )


@requires_bash
def test_record_env_does_not_contradict_the_allocator_on_the_same_fixture(tmp_path):
    """The setup step and the command that runs next must AGREE.

    On this fixture the container-local client would answer the capability question
    `t` while the connection Odoo itself opens is refused - so a step with its own
    copy of the question reports success where the allocator refuses. Asserted on
    the emitted verdict token, so it cannot go green on a reworded message.
    """
    env, toml = _step45_db_question_env(tmp_path, preflight_rc=8)

    step = _run_step45_record_env(env)
    direct = subprocess.run(
        [sys.executable, str(ALLOC), "db-preflight", "--series", "17.0",
         "--instances", str(toml)],
        capture_output=True, text=True, env=env, timeout=120,
    )

    def _auth(text):
        for line in text.splitlines():
            if line.startswith("DB_AUTH="):
                return line.partition("=")[2].strip().strip("'\"")
        return None

    assert _auth(direct.stdout) == "denied", (
        f"test setup: the allocator must refuse on this fixture; got {direct.stdout!r} "
        f"{direct.stderr!r}"
    )
    assert _auth(step.stdout) == _auth(direct.stdout), (
        "the setup step and the allocator must produce the SAME verdict token; step "
        f"said {_auth(step.stdout)!r}, the allocator said {_auth(direct.stdout)!r}\n"
        f"step stdout={step.stdout!r}\nstep stderr={step.stderr!r}"
    )


# ---------------------------------------------------------------------------
# unaccent: the listening conf must REQUEST it, because this launch is the
# database CREATOR whenever it is the first thing to name a declared-but-not-
# yet-built DB (cli/server.py runs Odoo's _create_empty_database for every -d
# that does not exist yet). A database created without unaccent can never be
# repaired by a later launch - nothing re-runs the creation path - and Odoo then
# silently drops accent-insensitive search and the trigram indexes it would have
# built over unaccent().
#
# The key has NO runtime effect by design: from v8 to v19 Odoo decides whether
# to USE unaccent by probing the database (modules/db.py has_unaccent), never by
# reading this key. That is precisely why it must be present at CREATION time or
# not at all - which is what makes this a conf-CONTENT contract rather than a
# runtime one.
# ---------------------------------------------------------------------------

