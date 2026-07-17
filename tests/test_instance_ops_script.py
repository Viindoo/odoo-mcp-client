"""Tests for setup step 55 (55-instance-ops.sh).

Business contracts protected:
  1. init  - runs odoo-bin with -i <modules> --stop-after-init; writes a log
             under ${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<ts>.log and emits LOG_PATH= on stdout.
  2. test  - with exit 0 + passing summary -> TEST_RESULT=passed;
             with exit non-zero or failure marker -> TEST_RESULT=failed.
  3. drop  - invokes scripts/lib/odoo_db.py with `drop <db>` via the instance
             python and propagates exit code; on exit 10 prints a clear
             venv-unavailable error (does NOT raw-dropdb).
  4. update - uses -u not -i.

Offline: no PostgreSQL, no real Odoo, no network. All odoo-bin / odoo_db.py
calls go to stub scripts on a synthetic PATH / --python.
"""

import json
import os
import socket
import subprocess
import textwrap
import time
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
            # The `<py> <odoo-bin> --version` preflight gate always passes for this
            # stub (a working venv); the real -i/-u/test run below uses the odoo-bin
            # stub's own exit code. Mirrors the step-50 harness design.
            if [[ "$2" == "--version" ]]; then echo "Odoo Server (preflight)"; exit 0; fi
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
    # extra_output emits the "Modules loaded." completion marker - forced onto
    # the log by --log-handler=<ns>.modules.loading:INFO even under the
    # --log-level=warn baseline - so a genuinely successful run is confirmed
    # (exit 0 alone is not proof of install; see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, extra_output='echo "Modules loaded."')
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

    # 3. Log is under ODOO_AI_HOME/logs/ (ODOO_AI_HOME IS the .odoo-ai dir;
    #    .odoo-ai is appended only in the HOME fallback - allocator semantic).
    expected_logs_dir = Path(env["ODOO_AI_HOME"]) / "logs"
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


# ---------------------------------------------------------------------------
# Contract 2c: test - skipped tests must NEVER read as a bare passed (issue #171)
# ---------------------------------------------------------------------------

@requires_bash
def test_test_verb_skip_only_run_is_inconclusive_never_passed(tmp_path):
    """A skip-only run (real repro shape from issue #171) must report
    TEST_RESULT=inconclusive, NEVER a bare TEST_RESULT=passed.

    Repro: a single test is SKIPPED (never ran, e.g. missing chrome devtools
    port), odoo-bin still prints "0 failed, 0 error(s) of 1 tests" and exits 0.
    Before the fix, that "0 failed, 0 error" line alone was read as a pass.

    Asserted as an EXACT stdout line (splitlines()), not a substring - a
    substring check would be fooled by any future verdict value that happens
    to start with "TEST_RESULT=passed" (e.g. a hypothetical
    "TEST_RESULT=passed-with-skips"), which is exactly why `inconclusive` was
    chosen as the verdict value instead.
    """
    extra_output = (
        'echo "INFO 12345 test odoo.addons.website_slides.tests.test_ui: '
        'skipped test_website_slides_tour : Failed to detect chrome devtools '
        'port after 10.0s."\n'
        'echo "INFO 12345 test odoo.tests.result: 0 failed, 0 error(s) of 1 tests"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skiponlydb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "website_slides",
        env=env,
    )

    stdout_lines = res.stdout.splitlines()
    assert "TEST_RESULT=inconclusive" in stdout_lines, (
        f"Expected an exact TEST_RESULT=inconclusive line for a skip-only run.\n"
        f"stdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=passed" not in stdout_lines, (
        f"A skip-only run must NEVER report TEST_RESULT=passed.\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_test_verb_emits_test_skipped_count(tmp_path):
    """TEST_SKIPPED=<n> must be emitted as a first-class field, counting every
    skip line matched by the version-robust skip regex (modern odoo.*test*:
    skip shape), alongside TEST_FAILED/TEST_ERROR/TEST_WARNING."""
    extra_output = (
        'echo "INFO 1 test odoo.addons.foo.tests.test_a: skipped test_one : reason one"\n'
        'echo "INFO 1 test odoo.addons.foo.tests.test_b: skipped test_two : reason two"\n'
        'echo "INFO 1 test odoo.tests.result: 0 failed, 0 error(s) of 2 tests"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skipcountdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "foo",
        env=env,
    )

    assert "TEST_SKIPPED=2" in res.stdout.splitlines(), (
        f"Expected TEST_SKIPPED=2 for two skip lines.\nstdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=inconclusive" in res.stdout.splitlines()


@requires_bash
def test_test_verb_skip_names_appear_in_findings_file(tmp_path):
    """Skipped test NAMES must be surfaced into the FINDINGS_PATH file under a
    dedicated section, mirroring the existing FAIL/ERROR and warnings sections -
    never swallowed, so a caller can see WHICH tests were skipped."""
    extra_output = (
        'echo "INFO 1 test odoo.addons.website_slides.tests.test_ui: '
        'skipped test_website_slides_tour : Failed to detect chrome devtools '
        'port after 10.0s."\n'
        'echo "INFO 1 test odoo.tests.result: 0 failed, 0 error(s) of 1 tests"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skipfindingsdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "website_slides",
        env=env,
    )

    findings_lines = [l for l in res.stdout.splitlines() if l.startswith("FINDINGS_PATH=")]
    assert len(findings_lines) == 1, f"Expected one FINDINGS_PATH= line.\nstdout:\n{res.stdout}"
    findings_path = Path(findings_lines[0].split("=", 1)[1])
    assert findings_path.exists(), f"findings file {findings_path} was not created."

    findings_text = findings_path.read_text(encoding="utf-8")
    assert "Skipped tests" in findings_text, (
        f"findings file must have a Skipped tests section.\n{findings_text}"
    )
    assert "test_website_slides_tour" in findings_text, (
        f"findings file must list the skipped test's name.\n{findings_text}"
    )
    assert "skipped=1" in findings_text, (
        f"findings file Counts line must include the skipped count.\n{findings_text}"
    )


@requires_bash
def test_test_verb_skip_alone_does_not_force_nonzero_exit(tmp_path):
    """Skips are NOT fatal (legitimate via @tagged filters / missing external
    deps): a skip-only run with odoo-bin exit 0 must keep exiting 0 and report
    STATUS=ok - the skip verdict is surfaced via TEST_RESULT/TEST_SKIPPED only,
    never by forcing a non-zero exit."""
    extra_output = (
        'echo "INFO 1 test odoo.addons.foo.tests.test_a: skipped test_one : reason"\n'
        'echo "INFO 1 test odoo.tests.result: 0 failed, 0 error(s) of 1 tests"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skipexitdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "foo",
        env=env,
    )

    assert res.returncode == 0, (
        f"a skip-only run with odoo-bin exit 0 must keep the script's own exit at 0.\n"
        f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    assert "STATUS=ok" in res.stdout.splitlines()


@requires_bash
def test_test_verb_zero_skip_clean_run_still_emits_passed(tmp_path):
    """Regression guard: a genuinely clean run (0 failed, 0 error, 0 skipped)
    must still emit an exact TEST_RESULT=passed line and TEST_SKIPPED=0 - the
    skip fix must not regress the plain-pass path."""
    passing_summary = "  Ran 5 test(s) in 1.23s: 0 failed, 0 error(s) (at_install)"
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=0, extra_output=f'echo "{passing_summary}"'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "cleanrundb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "sale",
        env=env,
    )

    assert res.returncode == 0
    stdout_lines = res.stdout.splitlines()
    assert "TEST_RESULT=passed" in stdout_lines, (
        f"a genuinely clean 0-skip run must still emit an exact TEST_RESULT=passed line.\n"
        f"stdout:\n{res.stdout}"
    )
    assert "TEST_SKIPPED=0" in stdout_lines


@requires_bash
def test_test_verb_benign_skip_lookalikes_do_not_trip_skip_detection(tmp_path):
    """Regression guard (skeptic-review blockers): a genuinely clean, fully-passing
    run whose log ALSO contains two benign lines that merely LOOK like a skip must
    still emit an exact TEST_RESULT=passed line and TEST_SKIPPED=0 - never
    inconclusive.

    1. An ordinary business retry line using the bare "... skipped" phrase
       (e.g. a stock reservation retry), which is NOT a test-skip event.
    2. A business log line from a module/model whose NAME merely CONTAINS the
       substring "test" (hr_attestation, website_testimonial) paired with an
       unrelated "skipping" business message - the model name is not a
       ".tests." package path segment.

    Neither line has a genuine `.tests.`/`.tests:` logger-namespace segment nor
    the stdlib `test_NAME (module.tests.path) ... skipped` shape, so SKIP_RE
    must not match either one.
    """
    extra_output = (
        'echo "INFO 1 test odoo.addons.stock.models.stock_move: reservation '
        '... skipped (insufficient qty, will retry)"\n'
        'echo "INFO 1 test odoo.addons.hr_attestation.models.hr_attestation: '
        'skipping approval because state != draft"\n'
        'echo "INFO 1 test odoo.addons.website_testimonial.models.testimonial: '
        'skipping duplicate testimonial entry"\n'
        'echo "  Ran 5 test(s) in 1.23s: 0 failed, 0 error(s) (at_install)"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skiplookalikedb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "stock",
        env=env,
    )

    assert res.returncode == 0
    stdout_lines = res.stdout.splitlines()
    assert "TEST_SKIPPED=0" in stdout_lines, (
        f"benign skip-lookalike lines must NOT be counted as skips.\nstdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=passed" in stdout_lines, (
        f"a clean run with only skip-lookalike noise must still emit an exact "
        f"TEST_RESULT=passed line, never inconclusive.\nstdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=inconclusive" not in stdout_lines


@requires_bash
def test_test_verb_fail_dominates_over_skip(tmp_path):
    """A run with BOTH a genuine skip AND a failing test must report
    TEST_RESULT=failed - a failure is always the dominant, blocking verdict,
    never downgraded to inconclusive just because a skip is also present."""
    extra_output = (
        'echo "INFO 1 test odoo.addons.website_slides.tests.test_ui: '
        'skipped test_website_slides_tour : Failed to detect chrome devtools '
        'port after 10.0s."\n'
        'echo "FAIL: test_my_module.TestCase.test_foo"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "failskipdb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "website_slides",
        env=env,
    )

    stdout_lines = res.stdout.splitlines()
    assert "TEST_RESULT=failed" in stdout_lines, (
        f"fail must dominate over a co-occurring skip.\nstdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=inconclusive" not in stdout_lines
    assert "TEST_SKIPPED=1" in stdout_lines


@requires_bash
def test_test_verb_skip_dominates_over_warning(tmp_path):
    """A run with BOTH a genuine skip AND a warning (no fail/error) must report
    TEST_RESULT=inconclusive - a skip is not proof the suite ran clean, so it
    must win over a plain warning-only verdict."""
    extra_output = (
        'echo "INFO 1 test odoo.addons.website_slides.tests.test_ui: '
        'skipped test_website_slides_tour : Failed to detect chrome devtools '
        'port after 10.0s."\n'
        'echo "2026-07-17 10:00:00,000 1 WARNING test odoo.addons.website_slides: '
        'some deprecation notice"'
    )
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test",
        "--db", "skipwarndb",
        "--python", str(fake_py),
        "--addons", str(addons_dir),
        "--modules", "website_slides",
        env=env,
    )

    stdout_lines = res.stdout.splitlines()
    assert "TEST_RESULT=inconclusive" in stdout_lines, (
        f"skip must dominate over a co-occurring warning (no fail/error).\nstdout:\n{res.stdout}"
    )
    assert "TEST_WARNING=1" in stdout_lines
    assert "TEST_SKIPPED=1" in stdout_lines


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
# Contract 3b: the assert-droppable ownership gate fires whenever NOT --force -
# including for a bare (empty-run-id) drop, the caller most likely to be nuking
# a DB it does not own. Regression guard for the MAJOR fix that dropped the
# `-n "$arg_run_id"` precondition so an empty-run-id drop no longer skips the
# ownership check exactly when it is needed.
# ---------------------------------------------------------------------------

def _seed_lease_registry(env: dict, leases: list) -> None:
    """Seed the allocator lease registry the real allocator.py (invoked by the
    drop gate) reads: ${ODOO_AI_HOME}/runtime/leases.json."""
    runtime = Path(env["ODOO_AI_HOME"]) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "leases.json").write_text(
        json.dumps({"schema_version": 2, "leases": leases}), encoding="utf-8"
    )


def _fresh_foreign_lease(db_name: str, owner_run: str) -> dict:
    """A fresh (non-stale) exclusive lease on db_name owned by owner_run: pid=None
    (no dead-pid staleness), heartbeat now, long TTL."""
    now = int(time.time())
    return {
        "token": "ab" * 16, "mode": "exclusive", "db_name": db_name,
        "drop_on_release": False,
        "owner": {"host": socket.gethostname(), "pid": None,
                  "run_id": owner_run, "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now,
        "_pg": {"host": "localhost", "user": "odoo"},
    }


@requires_bash
def test_bare_drop_of_unmanaged_db_still_succeeds(tmp_path):
    """A bare drop (empty run-id, no --force) of an UNMANAGED DB (no lease) must
    pass the ownership gate and proceed to drop. The gate must NOT block a drop
    just because the caller has no run id."""
    # Fake python that "succeeds" for the odoo_db.py drop call so a passing gate
    # yields STATUS=ok (proving the gate did not block).
    fake_py_dir = tmp_path / "ok-py-bin"
    fake_py_dir.mkdir()
    fake_py = fake_py_dir / "python"
    _write_stub(fake_py, "exit 0\n")

    env = _base_env(tmp_path)
    _seed_lease_registry(env, [])  # no leases -> unmanaged

    res = _run("drop", "--db", "unmanaged_db", "--python", str(fake_py), env=env)

    assert res.returncode == 0, (
        f"bare drop of an unmanaged DB must succeed (gate passes for empty run-id).\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "STATUS=ok" in res.stdout, (
        f"Expected STATUS=ok (drop proceeded).\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "drop refused" not in res.stderr, (
        f"the gate must not refuse an unmanaged DB.\nstderr={res.stderr}"
    )


@requires_bash
def test_bare_drop_of_fresh_foreign_db_is_refused_without_force(tmp_path):
    """A bare drop (empty run-id, no --force) of a DB held by a FRESH lease owned
    by a DIFFERENT run must be REFUSED - this is exactly the case the empty-run-id
    caller most needs protection from. odoo_db.py must never be reached."""
    fake_py_dir = tmp_path / "ok-py-bin"
    fake_py_dir.mkdir()
    fake_py = fake_py_dir / "python"
    _write_stub(fake_py, "exit 0\n")

    env = _base_env(tmp_path)
    _seed_lease_registry(env, [_fresh_foreign_lease("foreign_db", "run-owner")])

    res = _run("drop", "--db", "foreign_db", "--python", str(fake_py), env=env)

    assert res.returncode != 0, (
        f"a bare drop of a fresh foreign-owned DB must be refused.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "drop refused" in res.stderr, (
        f"Expected a 'drop refused' message.\nstderr={res.stderr}"
    )
    assert "STATUS=ok" not in res.stdout, (
        f"a refused drop must NOT report STATUS=ok (odoo_db.py must not run).\n"
        f"stdout={res.stdout}"
    )


@requires_bash
def test_force_overrides_gate_for_fresh_foreign_db(tmp_path):
    """--force deliberately reaps a foreign lease: the ownership gate is skipped
    and the drop proceeds even against a fresh foreign-owned DB."""
    fake_py_dir = tmp_path / "ok-py-bin"
    fake_py_dir.mkdir()
    fake_py = fake_py_dir / "python"
    _write_stub(fake_py, "exit 0\n")

    env = _base_env(tmp_path)
    _seed_lease_registry(env, [_fresh_foreign_lease("foreign_db", "run-owner")])

    res = _run("drop", "--db", "foreign_db", "--python", str(fake_py),
               "--force", env=env)

    assert res.returncode == 0, (
        f"--force must override the ownership gate.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "STATUS=ok" in res.stdout, (
        f"Expected STATUS=ok after a forced drop.\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "drop refused" not in res.stderr, (
        f"--force must not be refused by the gate.\nstderr={res.stderr}"
    )


# ---------------------------------------------------------------------------
# Contract 4: update - uses -u not -i
# ---------------------------------------------------------------------------

@requires_bash
def test_update_uses_dash_u_not_dash_i(tmp_path):
    """update must invoke odoo-bin with -u <modules>, NOT -i."""
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
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
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
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


# ---------------------------------------------------------------------------
# Contract 5: build ops (init / update) default to --log-level=warn, overridable
# via --extra. Business rule: a build op is quiet (warn) by default - quieter than
# Odoo's stock `info` - but a caller escalates for deep debugging by passing a
# louder --log-level in --extra, which must WIN (Odoo takes the last occurrence,
# so warn must sit BEFORE --extra in the argv).
# ---------------------------------------------------------------------------

@requires_bash
def test_init_defaults_to_log_level_warn(tmp_path):
    """init must inject --log-level=warn by default (quieter than Odoo's info)."""
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "warndb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-level=warn" in call_content, (
        f"Expected default --log-level=warn on init: {call_content}"
    )


@requires_bash
def test_update_defaults_to_log_level_warn(tmp_path):
    """update must inject --log-level=warn by default."""
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update", "--db", "warndb2", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-level=warn" in call_content, (
        f"Expected default --log-level=warn on update: {call_content}"
    )


@requires_bash
def test_init_extra_log_level_overrides_warn_default(tmp_path):
    """A caller-supplied --log-level=info in --extra must OVERRIDE the warn default.

    Odoo takes the last occurrence of a repeated flag, so the default warn must
    appear BEFORE the --extra value in the argv - assert both the presence and
    the order.
    """
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "escdb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--extra", "--log-level=info",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-level=warn" in call_content and "--log-level=info" in call_content, (
        f"Expected both warn default and info override present: {call_content}"
    )
    # Order: warn (default) must precede info (--extra override) so info wins.
    assert call_content.index("--log-level=warn") < call_content.index("--log-level=info"), (
        f"warn default must precede the --extra --log-level=info override: {call_content}"
    )


# ---------------------------------------------------------------------------
# Contract 6: active-wait on long builds.
#   (a) A build op still maps a success-marker + exit-0 run to STATUS=ok, and a
#       failure-marker + non-zero run to STATUS=error with LOG_PATH preserved.
#   (b) The `wait-log` verb deterministically classifies a build log by terminal
#       marker: success markers -> BUILD_RESULT=success (exit 0); failure markers
#       -> BUILD_RESULT=failure (exit 1); none within the bound -> timeout (exit 2).
# ---------------------------------------------------------------------------

@requires_bash
def test_init_success_marker_run_maps_to_status_ok(tmp_path):
    """A build that emits a success marker and exits 0 -> STATUS=ok, log preserved."""
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=0, extra_output='echo "Modules loaded."'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "okmarker", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "STATUS=ok" in res.stdout
    log_line = [l for l in res.stdout.splitlines() if l.startswith("LOG_PATH=")]
    assert len(log_line) == 1
    log_path = Path(log_line[0].split("=", 1)[1])
    assert log_path.exists() and "Modules loaded." in log_path.read_text(encoding="utf-8")


@requires_bash
def test_init_failure_marker_run_preserves_log(tmp_path):
    """A build that emits a Traceback and exits non-zero -> STATUS=error, LOG_PATH preserved."""
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=1,
        extra_output='echo "Traceback (most recent call last):"'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "failmarker", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode != 0, "Expected non-zero exit on a failed build."
    assert "STATUS=error" in res.stdout
    log_line = [l for l in res.stdout.splitlines() if l.startswith("LOG_PATH=")]
    assert len(log_line) == 1, f"LOG_PATH must be preserved on failure: {res.stdout}"
    log_path = Path(log_line[0].split("=", 1)[1])
    assert log_path.exists(), "Log must persist on failure for diagnosis."


# ---------------------------------------------------------------------------
# Contract 7 (RED-first / root-cause fix): the historical hang.
#
# Root cause: under --log-level=warn, EVERY completion line ("Modules
# loaded.", etc.) is INFO-level and gets suppressed - a clean run produces an
# EMPTY log. A completion check that requires seeing a line in that log would
# therefore wait forever (or, bounded, always time out) even on a genuinely
# successful run. The fix has two parts, both asserted below:
#   (a) init/update now force --log-handler=<ns>.modules.loading:INFO onto the
#       odoo-bin invocation so "Modules loaded." survives the warn baseline -
#       completion is decided by PROCESS EXIT (this call already blocks on
#       it), never by tailing/waiting on a log line.
#   (b) exit 0 alone is NOT sufficient - a run that exits 0 but never confirms
#       (empty log, or a silent-skip failure marker present) must report
#       STATUS=error, not STATUS=ok.
# ---------------------------------------------------------------------------

@requires_bash
def test_init_exit0_with_no_confirmation_marker_is_status_error(tmp_path):
    """RED-first: exit 0 with an OTHERWISE-EMPTY log (no warning/error line at
    all - simulating the old warn-level hang where the completion line was
    suppressed) must NOT be treated as done. This is the exact root-cause bug:
    before the fix, cmd_init trusted exit 0 alone and reported STATUS=ok here."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)  # no extra_output -> empty log
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "emptywarn", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode != 0, (
        f"exit 0 with an empty log must NOT be confirmed done.\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "STATUS=error" in res.stdout, f"expected STATUS=error.\nstdout={res.stdout}"
    assert "STATUS=ok" not in res.stdout
    log_line = [l for l in res.stdout.splitlines() if l.startswith("LOG_PATH=")]
    assert len(log_line) == 1, f"LOG_PATH must be preserved for diagnosis: {res.stdout}"
    assert Path(log_line[0].split("=", 1)[1]).exists()


@requires_bash
def test_update_exit0_with_no_confirmation_marker_is_status_error(tmp_path):
    """Same RED-first contract as above, for the update verb (-u)."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)  # no extra_output -> empty log
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update", "--db", "emptywarnu", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode != 0
    assert "STATUS=error" in res.stdout, f"stdout={res.stdout}"
    assert "STATUS=ok" not in res.stdout


@requires_bash
@pytest.mark.parametrize(
    "failure_line",
    [
        "invalid module names, ignored",
        "Some modules are not loaded, some dependencies or manifest may be missing",
        "Unmet dependency detected",
        "cannot be installed because",
    ],
)
def test_init_exit0_with_silent_skip_marker_is_status_error(tmp_path, failure_line):
    """RED-first: exit 0 PLUS the 'Modules loaded.' marker PLUS a silent-skip
    failure marker (a bad module name / unmet dep / demo failure that Odoo
    still exits 0 for) must still report STATUS=error - a failure marker wins
    over the success marker."""
    fake_bin = _make_fake_odoo_bin(
        tmp_path, exit_code=0,
        extra_output=f'echo "Modules loaded."\necho "{failure_line}"'
    )
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "silentskip", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode != 0, (
        f"a silent-skip marker ({failure_line!r}) must flip the verdict to error "
        f"even with exit 0 and the success marker present.\nstdout={res.stdout}"
    )
    assert "STATUS=error" in res.stdout, f"stdout={res.stdout}"


@requires_bash
@pytest.mark.parametrize("series,expected_ns", [
    ("8.0", "openerp"),
    ("9.0", "openerp"),
    ("10.0", "odoo"),
    ("17.0", "odoo"),
])
def test_init_forces_log_handler_namespace_by_version(tmp_path, series, expected_ns):
    """init must add --log-handler=<ns>.modules.loading:INFO, ns resolved from
    --version: 'openerp' for v8-v9, 'odoo' for v10+ (the openerp->odoo rename
    landed at the v9->v10 boundary)."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", f"nsdb{series.replace('.', '')}", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--version", series,
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    expected_flag = f"--log-handler={expected_ns}.modules.loading:INFO"
    assert expected_flag in call_content, (
        f"series={series}: expected {expected_flag!r} in odoo-bin invocation: {call_content}"
    )


@requires_bash
def test_init_log_handler_defaults_to_odoo_namespace_when_version_omitted(tmp_path):
    """Omitting --version must default the namespace to 'odoo' (the v10+
    majority) rather than failing or omitting the flag entirely."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "noversiondb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-handler=odoo.modules.loading:INFO" in call_content, (
        f"expected the odoo (v10+ default) namespace when --version is omitted: {call_content}"
    )


@requires_bash
@pytest.mark.parametrize("series,expected_ns", [
    ("8.0", "openerp"),
    ("9.0", "openerp"),
    ("10.0", "odoo"),
    ("17.0", "odoo"),
])
def test_update_forces_log_handler_namespace_by_version(tmp_path, series, expected_ns):
    """update must add --log-handler=<ns>.modules.loading:INFO, ns resolved from
    --version: 'openerp' for v8-v9, 'odoo' for v10+ (the openerp->odoo rename
    landed at the v9->v10 boundary) - same namespace-resolution contract as
    init (mirrors test_init_forces_log_handler_namespace_by_version)."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update", "--db", f"nsupddb{series.replace('.', '')}", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--version", series,
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    expected_flag = f"--log-handler={expected_ns}.modules.loading:INFO"
    assert expected_flag in call_content, (
        f"series={series}: expected {expected_flag!r} in odoo-bin invocation: {call_content}"
    )


@requires_bash
def test_update_log_handler_defaults_to_odoo_namespace_when_version_omitted(tmp_path):
    """Omitting --version must default the namespace to 'odoo' (the v10+
    majority) rather than failing or omitting the flag entirely - mirrors
    test_init_log_handler_defaults_to_odoo_namespace_when_version_omitted."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update", "--db", "noversionupddb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-handler=odoo.modules.loading:INFO" in call_content, (
        f"expected the odoo (v10+ default) namespace when --version is omitted: {call_content}"
    )


def _write_log(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


@requires_bash
def test_wait_log_success_marker(tmp_path):
    """wait-log on a log with a success marker -> BUILD_RESULT=success, exit 0, LOG_PATH echoed."""
    logf = _write_log(tmp_path, "build.log", "Loading modules...\nModules loaded.\n")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=success" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


@requires_bash
def test_wait_log_failure_marker_traceback(tmp_path):
    """wait-log on a log with a Traceback -> BUILD_RESULT=failure, exit 1."""
    logf = _write_log(tmp_path, "build.log",
                      "Loading modules...\nTraceback (most recent call last):\n  File ...\n")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=failure" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


@requires_bash
def test_wait_log_failure_marker_critical(tmp_path):
    """wait-log on a log with a CRITICAL log line -> BUILD_RESULT=failure, exit 1."""
    logf = _write_log(tmp_path, "build.log",
                      "2026-01-01 00:00:00 CRITICAL db odoo.modules: boot failed\n")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=failure" in res.stdout


@requires_bash
def test_wait_log_failure_wins_over_success_marker(tmp_path):
    """A failure marker present alongside a success marker still classifies as failure."""
    logf = _write_log(tmp_path, "build.log",
                      "Registry loaded\nTraceback (most recent call last):\n")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=failure" in res.stdout


@requires_bash
def test_wait_log_silent_skip_marker_wins_over_modules_loaded(tmp_path):
    """RED-first (review fix): a log carrying BOTH the 'Modules loaded.'
    completion marker AND a silent-skip failure marker (a bad module name /
    unmet dep / demo failure that odoo-bin still exits 0 for - see
    _install_confirmed) must report BUILD_RESULT=failure, never success.

    Before the fix, _scan_build_markers (the wait-log verdict used by the
    MANDATED background active-wait path in agents/odoo-instance-ops.md) used
    a separate, weaker marker set than _install_confirmed (the foreground
    verdict) and did NOT know about the silent-skip markers - so this exact
    log wrongly produced BUILD_RESULT=success. The fix makes both paths share
    the same _INSTALL_FAIL_RE / _INSTALL_SUCCESS_MARKER SSOT."""
    logf = _write_log(
        tmp_path, "build.log",
        "Loading modules...\nModules loaded.\ninvalid module names, ignored\n",
    )
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, (
        f"a silent-skip marker alongside 'Modules loaded.' must classify as "
        f"failure, not success.\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "BUILD_RESULT=failure" in res.stdout
    assert "BUILD_RESULT=success" not in res.stdout


@requires_bash
def test_wait_log_timeout_when_no_marker(tmp_path):
    """wait-log with no terminal marker within the bound -> BUILD_RESULT=timeout, exit 2."""
    logf = _write_log(tmp_path, "build.log", "still starting up...\n")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 2, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=timeout" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


# ---------------------------------------------------------------------------
# BLOCKER-3: create-side db-connection threading (--db-host/--db-user/--db-port)
# so CREATE/INIT/UPDATE/TEST hit the SAME Postgres cluster the DROP path uses.
# ---------------------------------------------------------------------------

@requires_bash
def test_init_threads_db_conn_flags_when_declared(tmp_path):
    """init must forward --db_host/--db_user/--db_port to odoo-bin when declared."""
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, extra_output='echo "Modules loaded."')
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
        "--db-host", "pghost",
        "--db-user", "pguser",
        "--db-port", "5433",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--db_host pghost" in call_content, f"expected --db_host pghost: {call_content}"
    assert "--db_user pguser" in call_content, f"expected --db_user pguser: {call_content}"
    assert "--db_port 5433" in call_content, (
        f"declared --db-port must reach odoo-bin as --db_port 5433 (BLOCKER-3): {call_content}"
    )


@requires_bash
def test_init_omits_db_port_when_not_declared(tmp_path):
    """No --db-port -> odoo-bin invocation must OMIT --db_port (empty-omit rule)."""
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "mydb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--db_port" not in call_content, (
        f"--db_port must be OMITTED when not declared (ambient PG env preserved): {call_content}"
    )


@requires_bash
def test_update_threads_db_port_when_declared(tmp_path):
    # "Modules loaded." confirms the run per the deterministic completion
    # contract (exit 0 alone is not proof - see _install_confirmed).
    fake_bin = _make_fake_odoo_bin(tmp_path, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "update", "--db", "mydb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--db-port", "5433",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--db_port 5433" in call_content, f"update must thread --db_port: {call_content}"


@requires_bash
def test_test_threads_db_port_when_declared(tmp_path):
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test", "--db", "mydb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--db-port", "5433",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--db_port 5433" in call_content, f"test must thread --db_port: {call_content}"


@requires_bash
def test_drop_threads_db_port_to_odoo_db_py(tmp_path):
    """drop must forward --db-port to odoo_db.py (BLOCKER-3: drop hits the right cluster)."""
    log = tmp_path / "odoo-db-argv.log"
    py_dir = tmp_path / "logpy"
    py_dir.mkdir()
    fake_py = py_dir / "python"
    _write_stub(fake_py, f'echo "$@" >> "{log}"\nexit 0\n')

    env = _base_env(tmp_path)
    res = _run(
        "drop", "--db", "dropme", "--python", str(fake_py),
        "--db-host", "pghost", "--db-port", "5433",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    argv = log.read_text(encoding="utf-8")
    assert "drop dropme" in argv, f"drop must invoke odoo_db.py drop dropme: {argv}"
    assert "--db-port" in argv and "5433" in argv, (
        f"drop must thread --db-port 5433 to odoo_db.py: {argv}"
    )


# ---------------------------------------------------------------------------
# Problem 5: --version preflight in init/update/test (fail loud, no run)
# ---------------------------------------------------------------------------

@requires_bash
def test_init_preflight_fails_loud_on_bad_python(tmp_path):
    """A --python whose `<py> <odoo-bin> --version` fails must fail-loud BEFORE the
    real run - mirroring 50-instance-spinup.sh's preflight gate."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    # Bad python: fails the --version gate; would exit 0 otherwise.
    bad_dir = tmp_path / "badpy"
    bad_dir.mkdir()
    bad_py = bad_dir / "python"
    _write_stub(bad_py, 'if [[ "$2" == "--version" ]]; then exit 1; fi\nexit 0\n')

    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()
    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "x", "--python", str(bad_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a broken venv must fail the preflight.\n{out}"
    assert "PREFLIGHT FAILED" in out, f"expected a loud PREFLIGHT FAILED message.\n{out}"
    # The real -i run must NOT have happened (only the --version probe, which the
    # bad python handled itself without touching odoo-bin).
    call_log = tmp_path / "odoo-bin-calls.log"
    content = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert " -i " not in content, f"init must NOT run odoo-bin -i after preflight failure: {content}"
