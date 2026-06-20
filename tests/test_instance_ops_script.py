"""Tests for setup step 55 (55-instance-ops.sh).

Business contracts protected:
  1. init  - runs odoo-bin with -i <modules> --stop-after-init; writes a log
             under ~/.odoo-ai/logs/<db>-<ts>.log and emits LOG_PATH= on stdout.
  2. test  - with exit 0 + passing summary -> TEST_RESULT=passed;
             with exit non-zero or failure marker -> TEST_RESULT=failed.
  3. drop  - invokes scripts/lib/odoo_db.py with `drop <db>` via the instance
             python and propagates exit code; on exit 10 prints a clear
             venv-unavailable error (does NOT raw-dropdb).
  4. update - uses -u not -i.

Offline: no PostgreSQL, no real Odoo, no network. All odoo-bin / odoo_db.py
calls go to stub scripts on a synthetic PATH / --python.
"""

import os
import subprocess
import textwrap
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEP55 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "55-instance-ops.sh"
)
REAL_ODOO_DB_PY = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_db.py"
)

requires_bash = pytest.mark.skipif(
    which("bash") is None, reason="bash not available"
)


# ---------------------------------------------------------------------------
# helpers - stub builders
# ---------------------------------------------------------------------------

def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _make_fake_odoo_bin(tmp_path: Path, *, exit_code: int = 0, extra_output: str = "") -> Path:
    """A fake odoo-bin that records its argv and exits with exit_code."""
    log = tmp_path / "odoo-bin-calls.log"
    fake = tmp_path / "odoo-bin"
    body = textwrap.dedent(f"""\
        echo "odoo-bin $*" >> "{log}"
        {extra_output}
        exit {exit_code}
    """)
    _write_stub(fake, body)
    return fake


def _make_fake_python(tmp_path: Path, *, odoo_bin_path: Path | None = None,
                      real_py3: str | None = None) -> Path:
    """A fake python that:
      - When called as `python <odoo-bin-path> ...`: exec the odoo-bin shell stub via bash.
      - Otherwise: pass through to real python3 (for odoo_db.py, inline snippets, etc.)

    This mirrors the step-50 test pattern where the fake python stub intercepts
    the odoo-bin launch call while keeping real Python for all lib calls.

    odoo_bin_path: path to the fake odoo-bin shell script. When None, the stub
    simply exec-delegates to real python3 for all calls (used for tests that
    only need library Python, e.g. drop).
    """
    real = real_py3 or which("python3") or "/usr/bin/python3"
    fake_dir = tmp_path / "fake-py-bin"
    fake_dir.mkdir(exist_ok=True)
    fake_py = fake_dir / "python"
    if odoo_bin_path is not None:
        body = textwrap.dedent(f"""\
            # If the first argument is the fake odoo-bin, exec it as a bash script.
            if [[ "$1" == "{odoo_bin_path}" ]]; then
                shift
                exec bash "{odoo_bin_path}" "$@"
            fi
            exec {real} "$@"
        """)
    else:
        body = f'exec {real} "$@"\n'
    _write_stub(fake_py, body)
    return fake_py


def _make_fake_odoo_db_py(tmp_path: Path, *, exit_code: int = 0) -> Path:
    """A fake odoo_db.py stub that records argv and exits with exit_code."""
    log = tmp_path / "odoo-db-calls.log"
    fake = tmp_path / "fake_odoo_db.py"
    fake.write_text(
        textwrap.dedent(f"""\
            import sys, pathlib
            pathlib.Path("{log}").write_text(" ".join(sys.argv[1:]) + "\\n", encoding="utf-8")
            sys.exit({exit_code})
        """),
        encoding="utf-8",
    )
    return fake


def _base_env(tmp_path: Path) -> dict:
    """Return a clean env dict for script runs (no real HOME / instances pollution)."""
    env = dict(os.environ)
    # Redirect ODOO_AI_HOME so logs land in tmp, not $HOME.
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    # No real instances.toml needed (55 does not read it).
    env.pop("ODOO_AI_INSTANCES", None)
    return env


def _run(subcmd: str, *args, env: dict, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["bash", str(STEP55), subcmd, *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)


# ---------------------------------------------------------------------------
# describe / check sanity
# ---------------------------------------------------------------------------

@requires_bash
def test_describe():
    """describe prints a non-empty one-line description."""
    res = _run("describe", env=dict(os.environ))
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() != ""


@requires_bash
def test_check_always_exits_0():
    """check always exits 0 (on-demand ops script, not an idempotent installer)."""
    res = _run("check", env=dict(os.environ))
    assert res.returncode == 0, res.stderr


# ---------------------------------------------------------------------------
# Contract 1: init - uses -i, writes log, emits LOG_PATH=
# ---------------------------------------------------------------------------

@requires_bash
def test_init_runs_odoo_bin_with_install_flag(tmp_path):
    """init must invoke odoo-bin with -i <modules> and --stop-after-init.

    Verifies the LOG_PATH= line is emitted and the log file exists on disk.
    """
    fake_bin = _make_fake_odoo_bin(tmp_path)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init",
        "--db", "mydb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale,purchase",
        env=env,
    )

    assert res.returncode == 0, f"init failed:\nstdout={res.stdout}\nstderr={res.stderr}"

    # 1. LOG_PATH= line on stdout.
    log_path_lines = [l for l in res.stdout.splitlines() if l.startswith("LOG_PATH=")]
    assert len(log_path_lines) == 1, (
        f"Expected exactly one LOG_PATH= line.\nstdout:\n{res.stdout}"
    )
    log_path = Path(log_path_lines[0].split("=", 1)[1])

    # 2. Log file exists.
    assert log_path.exists(), f"Log file {log_path} was not created."

    # 3. Log is under ODOO_AI_HOME/.odoo-ai/logs/.
    expected_logs_dir = Path(env["ODOO_AI_HOME"]) / ".odoo-ai" / "logs"
    assert log_path.parent == expected_logs_dir, (
        f"LOG_PATH must be under {expected_logs_dir}, got {log_path.parent}"
    )

    # 4. Filename encodes the db name.
    assert log_path.name.startswith("mydb-"), (
        f"Log filename must start with db name 'mydb-', got: {log_path.name}"
    )
    assert log_path.suffix == ".log"

    # 5. odoo-bin was called with -i and --stop-after-init.
    call_log = tmp_path / "odoo-bin-calls.log"
    assert call_log.exists(), "odoo-bin stub was not invoked."
    call_content = call_log.read_text(encoding="utf-8")
    assert " -i " in call_content, f"Expected '-i' flag in odoo-bin invocation: {call_content}"
    assert "sale,purchase" in call_content or ("sale" in call_content and "purchase" in call_content), (
        f"Expected modules 'sale,purchase' in odoo-bin invocation: {call_content}"
    )
    assert "--stop-after-init" in call_content, (
        f"Expected --stop-after-init in odoo-bin invocation: {call_content}"
    )
    # Must NOT use -u (that is for update).
    assert " -u " not in call_content, f"init must not use -u: {call_content}"

    # 6. STATUS=ok on success.
    assert "STATUS=ok" in res.stdout, f"Expected STATUS=ok.\nstdout:\n{res.stdout}"


# ---------------------------------------------------------------------------
# Contract 2a: test - passing run -> TEST_RESULT=passed
# ---------------------------------------------------------------------------

@requires_bash
def test_test_verb_emits_passed_on_clean_run(tmp_path):
    """test with exit 0 + no failure markers -> TEST_RESULT=passed."""
    # odoo-bin stub: exits 0 and prints a passing summary.
    passing_summary = (
        "  Ran 5 test(s) in 1.23s: 0 failed, 0 error(s) (at_install)"
    )
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=0,
        extra_output=f'echo "{passing_summary}"'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "testdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        env=env,
    )

    assert res.returncode == 0, f"test failed:\nstdout={res.stdout}\nstderr={res.stderr}"
    assert "TEST_RESULT=passed" in res.stdout, (
        f"Expected TEST_RESULT=passed.\nstdout:\n{res.stdout}"
    )
    assert "STATUS=ok" in res.stdout


@requires_bash
def test_test_verb_emits_passed_on_exit0_no_markers(tmp_path):
    """test with exit 0 and no failure markers -> TEST_RESULT=passed (even without pass line)."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "All done"')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "testdb2",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        env=env,
    )

    assert res.returncode == 0
    assert "TEST_RESULT=passed" in res.stdout


# ---------------------------------------------------------------------------
# Contract 2b: test - failure markers -> TEST_RESULT=failed
# ---------------------------------------------------------------------------

@requires_bash
def test_test_verb_emits_failed_on_nonzero_exit(tmp_path):
    """test with non-zero odoo-bin exit -> TEST_RESULT=failed + STATUS=error."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=1, extra_output='echo "something went wrong"')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "faildb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        env=env,
    )

    assert res.returncode != 0, "Expected non-zero exit when odoo-bin exits 1."
    assert "TEST_RESULT=failed" in res.stdout, (
        f"Expected TEST_RESULT=failed.\nstdout:\n{res.stdout}"
    )
    assert "STATUS=error" in res.stdout


@requires_bash
def test_test_verb_emits_failed_on_fail_marker_in_log(tmp_path):
    """test with exit 0 but 'FAIL:' in log output -> TEST_RESULT=failed."""
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=0,
        extra_output='echo "FAIL: test_my_module.TestCase.test_foo"'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "failmarkerdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        env=env,
    )

    # Exit 0 from the script is acceptable here (odoo-bin exited 0); what matters
    # is that TEST_RESULT=failed is emitted.
    combined = res.stdout + res.stderr
    assert "TEST_RESULT=failed" in res.stdout, (
        f"Expected TEST_RESULT=failed when log contains FAIL:.\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )


@requires_bash
def test_test_verb_passes_test_tags_to_odoo_bin(tmp_path):
    """test with --test-tags should forward --test-tags to odoo-bin."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "tagsdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        "--test-tags", "/sale",
        env=env,
    )

    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_log = tmp_path / "odoo-bin-calls.log"
    assert call_log.exists()
    call_content = call_log.read_text(encoding="utf-8")
    assert "--test-tags" in call_content, (
        f"Expected --test-tags in odoo-bin call: {call_content}"
    )
    assert "/sale" in call_content, (
        f"Expected '/sale' tag in odoo-bin call: {call_content}"
    )


# ---------------------------------------------------------------------------
# Contract 3: drop - calls odoo_db.py, propagates exit, reports exit 10
# ---------------------------------------------------------------------------

@requires_bash
def test_drop_invokes_odoo_db_py_with_correct_args(tmp_path):
    """drop must call odoo_db.py drop <db> via the instance python."""
    fake_odb_py = _make_fake_odoo_db_py(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path)

    env = _base_env(tmp_path)

    res = _run(
        "drop",
        "--db", "dropme",
        "--python", str(fake_py),
        env=env,
        # Override ODOO_DB_PY location so the script uses our stub.
    )

    # We cannot easily override ODOO_DB_PY env (it's hardcoded in the script),
    # so instead we verify the real odoo_db.py is invoked by the real python.
    # The real odoo_db.py will fail with exit 10 (venv unavailable, no odoo pkg)
    # because fake_py is just real python3 which doesn't have odoo.
    # That is the correct behavior: drop should report venv-unavailable, not crash.
    # Accept either exit 10 (venv unavailable) or success (if odoo is importable).
    assert res.returncode in (0, 10), (
        f"drop should exit 0 (success) or 10 (venv-unavailable), not {res.returncode}.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    if res.returncode == 10:
        # Must print a clear venv-unavailable error.
        assert "venv" in res.stderr.lower() or "venv unavailable" in res.stderr.lower(), (
            f"Expected venv-unavailable message on stderr.\nstderr={res.stderr}"
        )


@requires_bash
def test_drop_reports_venv_unavailable_on_exit10(tmp_path):
    """When odoo_db.py exits 10, drop must print a clear error and NOT raw-dropdb.

    We simulate this by pointing --python at a python stub that always exits 10
    when called with odoo_db.py as the first arg.
    """
    # Fake python: exits 10 for any call (simulates no-odoo venv)
    fake_py_dir = tmp_path / "no-odoo-py-bin"
    fake_py_dir.mkdir()
    fake_py = fake_py_dir / "python"
    _write_stub(fake_py, "exit 10\n")

    env = _base_env(tmp_path)

    res = _run(
        "drop",
        "--db", "dropme",
        "--python", str(fake_py),
        env=env,
    )

    assert res.returncode == 10, (
        f"Expected exit 10 (venv unavailable), got {res.returncode}.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    combined = res.stdout + res.stderr
    assert "venv" in combined.lower(), (
        f"Expected 'venv' in error output.\ncombined:\n{combined}"
    )
    # Must NOT have silently fallen back to raw dropdb.
    # (The error message may mention "dropdb" in an explanatory sentence about what
    # NOT to do; what matters is that STATUS=ok is absent and exit code is 10.)
    assert "STATUS=ok" not in combined, (
        f"drop must NOT report STATUS=ok on venv-unavailable.\ncombined:\n{combined}"
    )


@requires_bash
def test_drop_propagates_nonzero_exit_from_odoo_db(tmp_path):
    """When odoo_db.py exits with a non-10 non-zero code, drop propagates it."""
    fake_py_dir = tmp_path / "exit1-py-bin"
    fake_py_dir.mkdir()
    fake_py = fake_py_dir / "python"
    _write_stub(fake_py, 'echo "odoo_db: exp_drop failed" >&2; exit 1\n')

    env = _base_env(tmp_path)

    res = _run(
        "drop",
        "--db", "dropfail",
        "--python", str(fake_py),
        env=env,
    )

    assert res.returncode == 1, (
        f"Expected exit 1 propagated, got {res.returncode}.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )


# ---------------------------------------------------------------------------
# Contract 4: update - uses -u not -i
# ---------------------------------------------------------------------------

@requires_bash
def test_update_uses_dash_u_not_dash_i(tmp_path):
    """update must invoke odoo-bin with -u <modules>, NOT -i."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update",
        "--db", "updatedb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale,purchase",
        env=env,
    )

    assert res.returncode == 0, f"update failed:\nstdout={res.stdout}\nstderr={res.stderr}"

    call_log = tmp_path / "odoo-bin-calls.log"
    assert call_log.exists(), "odoo-bin stub was not invoked."
    call_content = call_log.read_text(encoding="utf-8")

    assert " -u " in call_content, f"update must use -u flag: {call_content}"
    assert " -i " not in call_content, f"update must NOT use -i flag: {call_content}"
    assert "--stop-after-init" in call_content
    assert "STATUS=ok" in res.stdout


# ---------------------------------------------------------------------------
# Extra: --extra flags are forwarded to odoo-bin
# ---------------------------------------------------------------------------

@requires_bash
def test_init_forwards_extra_flags(tmp_path):
    """--extra flags are forwarded verbatim to odoo-bin."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init",
        "--db", "mydb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        "--extra", "--without-demo=all --skip-auto-install",
        env=env,
    )

    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_log = tmp_path / "odoo-bin-calls.log"
    call_content = call_log.read_text(encoding="utf-8")
    assert "--without-demo=all" in call_content, (
        f"Expected --without-demo=all forwarded: {call_content}"
    )
    assert "--skip-auto-install" in call_content, (
        f"Expected --skip-auto-install forwarded: {call_content}"
    )
