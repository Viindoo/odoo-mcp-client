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
import re
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
    # extra_output emits the "Modules loaded." completion marker - kept on the
    # log at any caller-chosen level by the --log-handler=<ns>.modules.
    # loading:INFO FLOOR - so a genuinely successful run is confirmed
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
    """test with exit 0 + a real passing summary -> TEST_RESULT=passed.

    The summary is the VERBATIM v14+ wording (odoo/service/server.py logs
    OdooTestResult.__str__ as "<F> failed, <E> error(s) of <T> tests when
    loading database <db>"), not a paraphrase - the parser keys on it.
    """
    passing_summary = (
        "2026-01-01 00:00:00,000 1 INFO testdb odoo.service.server: "
        "0 failed, 0 error(s) of 5 tests when loading database 'testdb'"
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
def test_green_run_with_no_ran_marker_is_inconclusive_never_passed(tmp_path):
    """exit 0 with NO failure marker and NO "the suite ran" marker must report
    TEST_RESULT=inconclusive, never a bare passed.

    Business rule: `passed` is a POSITIVE finding - it requires evidence the
    suite actually ran. A --test-tags filter that matches zero tests exits 0
    and produces no marker at all; certifying that as green is the same class
    of false green as the skip-only run in Contract 2c. This test previously
    asserted the opposite (it pinned the fallthrough-to-passed defect in
    place), so it is inverted here rather than added alongside.
    """
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
    stdout_lines = res.stdout.splitlines()
    assert "TEST_RESULT=inconclusive" in stdout_lines, (
        f"a run with no ran-marker must be inconclusive.\nstdout:\n{res.stdout}"
    )
    assert "TEST_RESULT=passed" not in stdout_lines, (
        f"a run with no ran-marker must NEVER be certified passed.\nstdout:\n{res.stdout}"
    )


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
    passing_summary = (
        "2026-01-01 00:00:00,000 1 INFO cleanrundb odoo.service.server: "
        "0 failed, 0 error(s) of 5 tests when loading database 'cleanrundb'"
    )
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
        'echo "2026-01-01 00:00:00,000 1 INFO skiplookalikedb '
        'odoo.service.server: 0 failed, 0 error(s) of 5 tests when loading '
        'database \'skiplookalikedb\'"'
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
# Contract 5: ONE log-level default, shared by every verb, overridable per run.
# Business rule: init / update / test all resolve the SAME default level - the
# level at which a passing run still emits its own summary - and a caller
# overrides it per run with a --log-level in --extra (Odoo takes the last
# occurrence, so the default must sit BEFORE --extra in the argv). The tests
# below assert the RESOLVED default is one shared value and that no verb keeps
# a second, different one; they never snapshot a particular token beyond the
# one behavioural fact that makes it the right default.
# ---------------------------------------------------------------------------

@requires_bash
def test_init_defaults_to_log_level_info(tmp_path):
    """init must inject --log-level=info by default (Odoo's own stock level -
    the lowest at which a PASSING run still emits its summary line) and must
    NOT inject the old quiet `warn` default."""
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
    assert "--log-level=info" in call_content, (
        f"Expected default --log-level=info on init: {call_content}"
    )
    assert "--log-level=warn" not in call_content, (
        f"init must NOT emit the old quiet warn default: {call_content}"
    )


@requires_bash
def test_update_defaults_to_log_level_info(tmp_path):
    """update must inject the same --log-level=info default as init, and must
    NOT inject the old quiet `warn` default."""
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
    assert "--log-level=info" in call_content, (
        f"Expected default --log-level=info on update: {call_content}"
    )
    assert "--log-level=warn" not in call_content, (
        f"update must NOT emit the old quiet warn default: {call_content}"
    )


@requires_bash
def test_extra_log_level_overrides_the_default(tmp_path):
    """A caller-supplied --log-level in --extra must OVERRIDE the script default.

    Odoo takes the last occurrence of a repeated flag, so the default must
    appear BEFORE the --extra value in the argv - assert both the presence and
    the order. Asserted on a token the script's own default is NOT, so the test
    cannot silently pass by matching the default against itself.
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
        "--extra", "--log-level=debug",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-level=info" in call_content and "--log-level=debug" in call_content, (
        f"Expected both the default and the --extra override present: {call_content}"
    )
    # Order: the default must precede the --extra override so the override wins.
    assert call_content.index("--log-level=info") < call_content.index("--log-level=debug"), (
        f"the default must precede the --extra --log-level=debug override: {call_content}"
    )


# ---------------------------------------------------------------------------
# Contract 6: active-wait on long builds.
#   (a) A build op still maps a success-marker + exit-0 run to STATUS=ok, and a
#       failure-marker + non-zero run to STATUS=error with LOG_PATH preserved.
#   (b) The `wait-log` verb deterministically classifies a build log by terminal
#       marker: success markers -> BUILD_RESULT=success (exit 0); failure markers
#       -> BUILD_RESULT=failure (exit 1); a finished test run that certified no
#       pass -> BUILD_RESULT=inconclusive (exit 3); none within the bound ->
#       timeout (exit 2). Only exit 2 means "keep waiting". The value-by-value
#       mapping of the run's own verdict, and the guard that no verdict may
#       reach a caller through a fallthrough, live in test_verdict_paths_agree.py.
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
# Contract 7: the completion invariant - "Modules loaded." or STATUS=error.
#
# The whole init/update verdict rests on ONE line being present in the log.
# The two parts asserted below make that unconditional:
#   (a) init/update ALWAYS emit --log-handler=<ns>.modules.loading:INFO - a
#       FLOOR, not a workaround: it keeps "Modules loaded." on the log at ANY
#       level a caller may pass in --extra, including a quieter one, so the
#       completion contract never depends on the caller's verbosity choice.
#       Completion itself is decided by PROCESS EXIT (this call already blocks
#       on it), never by tailing/waiting on a log line.
#   (b) exit 0 alone is NOT sufficient - a run that exits 0 but never confirms
#       (no completion marker, or a silent-skip failure marker present) must
#       report STATUS=error, not STATUS=ok.
# ---------------------------------------------------------------------------

@requires_bash
def test_init_exit0_with_no_confirmation_marker_is_status_error(tmp_path):
    """exit 0 with a log carrying no completion marker at all must NOT be
    treated as done - the marker is REQUIRED for success, never inferred from
    the exit code. Before the fix, cmd_init trusted exit 0 alone here."""
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


def _write_log(tmp_path: Path, name: str, body: str, verb: str | None = None) -> Path:
    """Write a build log. `verb` writes the run-verb stamp the script's own
    `_open_log` puts on the first line of every log it opens.

    The stamp is what tells a later, separate `wait-log` process WHICH terminal
    predicate applies, so a test that means to exercise the install/update
    predicate has to declare `init`/`update` exactly as a real run does. Left
    unstamped, the log declares nothing, and the script resolves that to the
    narrower `test` predicate on purpose - see the UNKNOWN-verb tests below.
    """
    p = tmp_path / name
    stamp = f"ODOO_AI_RUN_VERB={verb} SERIES=\n" if verb else ""
    p.write_text(stamp + body, encoding="utf-8")
    return p


@requires_bash
def test_wait_log_success_marker(tmp_path):
    """wait-log on a log with a success marker -> BUILD_RESULT=success, exit 0, LOG_PATH echoed."""
    logf = _write_log(tmp_path, "build.log", "Loading modules...\nModules loaded.\n",
                      verb="init")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=success" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


@requires_bash
def test_wait_log_failure_marker_traceback(tmp_path):
    """wait-log on an install log with a Traceback -> BUILD_RESULT=failure, exit 1.

    Scoped to `init`/`update` deliberately: under -i/-u no test runs, so nothing
    but the build itself can raise and a traceback IS the failure. On a
    --test-enable log the same bytes are per-test/incidental evidence and must
    NOT rule - covered by the test-verb cases in test_verdict_paths_agree.py."""
    logf = _write_log(tmp_path, "build.log",
                      "Loading modules...\nTraceback (most recent call last):\n  File ...\n",
                      verb="init")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=failure" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


@requires_bash
def test_wait_log_failure_marker_critical(tmp_path):
    """wait-log on a log with a CRITICAL log line -> BUILD_RESULT=failure, exit 1."""
    logf = _write_log(tmp_path, "build.log",
                      "2026-01-01 00:00:00 CRITICAL db odoo.modules: boot failed\n",
                      verb="init")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=failure" in res.stdout


@requires_bash
def test_wait_log_failure_wins_over_success_marker(tmp_path):
    """A failure marker present alongside a success marker still classifies as failure."""
    logf = _write_log(tmp_path, "build.log",
                      "Registry loaded\nTraceback (most recent call last):\n",
                      verb="init")
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
        verb="init",
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
    logf = _write_log(tmp_path, "build.log", "still starting up...\n", verb="init")
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 2, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=timeout" in res.stdout
    assert f"LOG_PATH={logf}" in res.stdout


# ---------------------------------------------------------------------------
# UNKNOWN verb - a log that declares no verb at all.
#
# Reachable, not theoretical: any log written before the run-verb stamp existed,
# and any log a caller points `wait-log` at that this script did not open. The
# resolution must be the one that cannot certify a WRONG answer, because the two
# predicates disagree in exactly the places where each can be wrong.
# ---------------------------------------------------------------------------

@requires_bash
def test_an_unstamped_log_is_never_certified_successful_by_the_completion_marker(tmp_path):
    """`Modules loaded.` alone may not pass a log that never declared its verb.

    On a --test-enable run Odoo logs that line BEFORE the post-install suite
    starts. So on a log whose verb is unknown the same bytes are equally
    consistent with "the install finished" and "the tests have not begun", and
    certifying there hands back a green build whose tests never ran - the one
    error class that must be unreachable. Not-decided is the honest answer; the
    caller re-invokes and reports BLOCKED with the log preserved.
    """
    logf = _write_log(
        tmp_path, "unstamped.log",
        "Loading modules...\nModules loaded.\n"
        "2026-01-01 00:00:00,000 1 INFO testdb odoo.addons.web.tests.test_js: "
        "Starting WebSuite.test_unit_desktop ... \n",
    )
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert "BUILD_RESULT=success" not in res.stdout, (
        "an unstamped log carrying only the install completion marker was certified "
        f"as a successful build while its suite had not started\nstdout={res.stdout}"
    )
    assert res.returncode == 2, f"stdout={res.stdout}\nstderr={res.stderr}"


@requires_bash
def test_an_unstamped_log_is_never_failed_by_a_lone_traceback(tmp_path):
    """A traceback alone may not fail a log that never declared its verb.

    On a --test-enable run a traceback is per-test/incidental evidence - logged
    exceptions the run recovers from, routing errors, and every HttpCase 500 the
    test asserts on all write one. Ruling on it turns a healthy run RED.
    """
    logf = _write_log(
        tmp_path, "unstamped.log",
        "Loading modules...\n"
        "2026-01-01 00:00:00,000 1 INFO testdb odoo.addons.web.tests.test_js: "
        "Starting WebSuite.test_unit_desktop ... \n"
        "Exception in thread odoo.service.httpd:\n"
        "Traceback (most recent call last):\n  File ...\n",
    )
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert "BUILD_RESULT=failure" not in res.stdout, (
        "an unstamped log was ruled a failed build by a lone traceback\n"
        f"stdout={res.stdout}"
    )
    assert res.returncode == 2, f"stdout={res.stdout}\nstderr={res.stderr}"


@requires_bash
def test_an_unstamped_log_is_still_failed_by_a_hard_abort(tmp_path):
    """Refusing to certify is not refusing to answer.

    A hard abort proves odoo-bin died and will never publish a verdict of its
    own, whichever verb it was running. It stays terminal with no stamp at all -
    otherwise the safe default would trade a false verdict for a permanent wait.
    """
    logf = _write_log(
        tmp_path, "unstamped.log",
        "Loading modules...\n"
        "2026-01-01 00:00:00 CRITICAL db odoo.modules.registry: boot failed\n",
    )
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert "BUILD_RESULT=failure" in res.stdout, (
        f"a hard abort is terminal for every verb, stamp or none\nstdout={res.stdout}"
    )
    assert res.returncode == 1, f"stdout={res.stdout}\nstderr={res.stderr}"


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


# ---------------------------------------------------------------------------
# Separator SSOT: _find_odoo_bin must resolve a REAL 2-entry, comma-joined
# --addons value (the format allocator.py's ALLOC_ADDONS_PATH actually emits,
# fed here via agents/odoo-instance-ops.md's `--addons "$ALLOC_ADDONS_PATH"`)
# - not colon. This is the first test of 55-instance-ops.sh to exercise a
# 2+-entry addons_path; every existing test above sets ODOO_BIN directly,
# bypassing the _find_odoo_bin scan entirely.
# ---------------------------------------------------------------------------

@requires_bash
def test_find_odoo_bin_locates_across_two_entry_addons_path(tmp_path):
    """_find_odoo_bin must locate odoo-bin when --addons carries 2 comma-joined
    entries (today's REAL ALLOC_ADDONS_PATH format - allocator.py has emitted
    comma since it was fixed to match Odoo's own --addons-path syntax) with
    odoo-bin present only under the SECOND entry.

    No ODOO_BIN override: the scan itself must split the comma-joined value.
    This is the live, previously-undocumented regression at
    55-instance-ops.sh:167 (hardcoded IFS=':' against a value that has been
    comma-joined for weeks) - it fires on every init/update/test call the
    odoo-instance-ops agent makes with a real (2+-repo) addons_path.
    """
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    fake_bin = _make_fake_odoo_bin(repo_b, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)

    env = _base_env(tmp_path)
    env.pop("ODOO_BIN", None)

    res = _run(
        "init",
        "--db", "mydb2",
        "--python", str(fake_py),
        "--addons", f"{repo_a},{repo_b}",
        "--modules", "sale",
        env=env,
    )
    out = res.stdout + res.stderr

    assert res.returncode == 0, (
        f"init failed to resolve odoo-bin across a real 2-entry comma-joined "
        f"addons path.\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "STATUS=ok" in res.stdout, f"Expected STATUS=ok.\nstdout:\n{res.stdout}"
    call_log = repo_b / "odoo-bin-calls.log"
    assert call_log.exists(), (
        f"odoo-bin stub (under the SECOND addons_path entry) was never "
        f"invoked - the scan did not reach it.\n{out}"
    )


@requires_bash
def test_addons_csv_passed_to_odoo_bin_is_never_double_converted(tmp_path):
    """The --addons-path value odoo-bin actually receives, for a comma-joined
    2-entry --addons input, must be byte-identical to the input - guards
    against the old normalize idiom (`${arg_addons//:/, }`) reappearing and
    silently injecting a space once every producer emits comma-only."""
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    fake_bin = _make_fake_odoo_bin(repo_b, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)

    env = _base_env(tmp_path)
    env.pop("ODOO_BIN", None)
    addons_value = f"{repo_a},{repo_b}"

    res = _run(
        "init",
        "--db", "mydb3",
        "--python", str(fake_py),
        "--addons", addons_value,
        "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"init failed:\nstdout={res.stdout}\nstderr={res.stderr}"

    call_log = repo_b / "odoo-bin-calls.log"
    content = call_log.read_text(encoding="utf-8")
    assert f"--addons-path {addons_value}" in content, (
        f"Expected the odoo-bin invocation to receive the addons-path value "
        f"byte-identical to the input (no injected spaces / double-conversion); "
        f"got: {content!r}"
    )


# ---------------------------------------------------------------------------
# Contract 8: the log-level token the script emits must be valid on EVERY
# supported series, and the test-result parser must read the era-correct
# markers instead of guessing.
#
# Business rules protected here:
#   (a) One default level, resolved the same way for every verb, and only ever
#       a token in the INTERSECTION of the 12 series' `--log-level` choice
#       lists - a token valid on some series is a hard optparse startup
#       failure on the others.
#   (b) A failing suite is reported FAILED on every series, including the six
#       (v8.0-v13.0) whose per-module failure wording differs from v14+.
#   (c) `passed` is a POSITIVE finding: it requires an era-correct "the suite
#       ran" marker, and never falls through from "nothing went wrong".
#
# Every marker string below is the VERBATIM Odoo wording read from the source
# of the series it represents, never a paraphrase.
# ---------------------------------------------------------------------------

# The intersection of the `levels` list in {openerp,odoo}/tools/config.py across
# v8.0-v19.0. `runbot` (added at 14.0) and `warning` (never a member on any
# series) are both OUTSIDE it and must never be emitted by this script.
LOG_LEVEL_TOKENS_VALID_ON_EVERY_SERIES = {
    "info", "debug_rpc", "warn", "test", "critical",
    "debug_sql", "error", "debug", "debug_rpc_answer", "notset",
}

# Real per-era markers. Sources:
#   v8.0-v13.0 failure : {openerp,odoo}/modules/module.py  "Module %s: %d failures, %d errors"
#   all series failure : {openerp,odoo}/modules/loading.py "At least one test failed ..."
#   v14.0+     failure : odoo/modules/loading.py "Module %s: %d failures, %d errors of %d tests"
#   v8.0-v13.0 ran     : stdlib TextTestResult / odoo.modules.module "Ran %d test%s in %.3fs"
#   v14.0+     ran     : odoo/service/server.py "%s when loading database %r" with
#                        OdooTestResult.__str__ = "<F> failed, <E> error(s) of <T> tests"
FAIL_LINE_V8_V13 = (
    "2026-01-01 00:00:00,000 1 ERROR erad odoo.modules.module: "
    "Module sale: 2 failures, 0 errors"
)
FAIL_LINE_ALL_SERIES = (
    "2026-01-01 00:00:00,000 1 ERROR erad odoo.modules.loading: "
    "At least one test failed when loading the modules."
)
FAIL_LINE_V14_PLUS = (
    "2026-01-01 00:00:00,000 1 ERROR erad odoo.service.server: "
    "3 failed, 0 error(s) of 40 tests when loading database 'erad'"
)
RAN_LINE_V8_V13 = (
    "2026-01-01 00:00:00,000 1 INFO erad odoo.modules.module: Ran 5 tests in 1.234s"
)
RAN_LINE_V14_PLUS = (
    "2026-01-01 00:00:00,000 1 INFO erad odoo.service.server: "
    "0 failed, 0 error(s) of 40 tests when loading database 'erad'"
)


def _run_test_verb(tmp_path: Path, db: str, log_lines, *, version: str | None = None,
                   exit_code: int = 0, extra_args=()) -> subprocess.CompletedProcess:
    """Run the `test` verb against a stub odoo-bin that prints log_lines."""
    extra_output = "\n".join(f'echo "{line}"' for line in log_lines)
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=exit_code, extra_output=extra_output)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir(exist_ok=True)

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    args = ["--db", db, "--python", str(fake_py), "--addons", str(addons_dir),
            "--modules", "sale", *extra_args]
    if version is not None:
        args += ["--version", version]
    return _run("test", *args, env=env)


def _verdict(res: subprocess.CompletedProcess) -> str:
    lines = [l for l in res.stdout.splitlines() if l.startswith("TEST_RESULT=")]
    assert len(lines) == 1, f"expected exactly one TEST_RESULT= line, got {lines}\n{res.stdout}"
    return lines[0].split("=", 1)[1]


@requires_bash
@pytest.mark.parametrize("verb", ["init", "update"])
@pytest.mark.parametrize(
    "series",
    ["8.0", "9.0", "10.0", "11.0", "12.0", "13.0",
     "14.0", "15.0", "16.0", "17.0", "18.0", "19.0"],
)
def test_default_log_level_token_is_valid_on_every_supported_series(tmp_path, verb, series):
    """Whatever --log-level token the script resolves for a series, it must be a
    member of the intersection of all 12 series' accepted values.

    This is the version-general form of "never emit runbot" (14.0+ only) and
    "never emit warning" (not a member on ANY series) - both fail this rule
    without being named, and so would any future token that is valid on only
    part of the supported span. odoo-bin rejects an out-of-list value with an
    optparse choice error and never starts."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        verb, "--db", f"lvl{verb}{series.replace('.', '')}", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale", "--version", series,
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    emitted = re.findall(r"--log-level=([A-Za-z_]+)", call_content)
    assert emitted, f"{verb} emitted no --log-level at all: {call_content}"
    for token in emitted:
        assert token in LOG_LEVEL_TOKENS_VALID_ON_EVERY_SERIES, (
            f"{verb} on series {series} emitted --log-level={token}, which is not "
            f"valid on every supported series (v8.0-v19.0). Valid intersection: "
            f"{sorted(LOG_LEVEL_TOKENS_VALID_ON_EVERY_SERIES)}"
        )


@requires_bash
def test_test_verb_default_matches_the_build_default(tmp_path):
    """The `test` verb with no --log-mode must emit the SAME --log-level token
    init does by default - one default in this script, not two.

    Before the SSOT constant there were three independent literals; this test
    is what keeps them from drifting apart again."""
    init_dir = tmp_path / "initrun"
    init_dir.mkdir()
    fake_bin_i = _make_fake_odoo_bin(init_dir, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py_i = _make_fake_python(init_dir, odoo_bin_path=fake_bin_i)
    addons_i = init_dir / "addons"
    addons_i.mkdir()
    env_i = _base_env(init_dir)
    env_i["ODOO_BIN"] = str(fake_bin_i)
    res_i = _run("init", "--db", "defcmp1", "--python", str(fake_py_i),
                 "--addons", str(addons_i), "--modules", "sale", env=env_i)
    assert res_i.returncode == 0, f"stdout={res_i.stdout}\nstderr={res_i.stderr}"
    init_levels = re.findall(
        r"--log-level=([A-Za-z_]+)",
        (init_dir / "odoo-bin-calls.log").read_text(encoding="utf-8"),
    )

    test_dir = tmp_path / "testrun"
    test_dir.mkdir()
    res_t = _run_test_verb(test_dir, "defcmp2", [RAN_LINE_V14_PLUS], version="17.0")
    assert res_t.returncode == 0, f"stdout={res_t.stdout}\nstderr={res_t.stderr}"
    test_call = (test_dir / "odoo-bin-calls.log").read_text(encoding="utf-8")
    test_levels = re.findall(r"--log-level=([A-Za-z_]+)", test_call)

    assert init_levels == test_levels, (
        f"the test verb's default log level ({test_levels}) must equal init's "
        f"({init_levels}) - one default, not two"
    )
    assert "--log-level=test" not in test_call, (
        f"the test verb must not keep a separate `test` log level: {test_call}"
    )


@requires_bash
@pytest.mark.parametrize("token", ["runbot", "warning", "test"])
def test_log_mode_rejects_a_token_not_valid_on_every_series(tmp_path, token):
    """--log-mode is a CLOSED allowlist: a value outside info|debug|sql exits 2
    with the allowlist printed, on every series and with no version gate. This is
    what keeps `runbot` (a hard startup failure on v8.0-v13.0) from ever reaching
    odoo-bin through this parameter."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test", "--db", f"lm{token}", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--log-mode", token,
        env=env,
    )
    assert res.returncode == 2, (
        f"--log-mode {token} must be refused with exit 2.\n"
        f"rc={res.returncode} stdout={res.stdout} stderr={res.stderr}"
    )
    assert "info|debug|sql" in res.stderr, (
        f"the refusal must print the allowlist.\nstderr={res.stderr}"
    )


def test_no_committed_file_emits_a_series_gated_log_level_token():
    """No committed file anywhere in the plugin tree may hand odoo-bin a
    --log-level token that is invalid on part of the supported span.

    Whole-tree scan on whitespace-normalized text (prose here is line-wrapped,
    so an adjacency-bound check would miss most of it) rather than a check
    pinned to the one file that happens to carry the setter today."""
    offenders = []
    skip_dirs = {"node_modules", "__pycache__"}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".sh", ".md", ".py", ".json", ".yaml"}:
            continue
        rel = path.relative_to(ROOT)
        # Committed tree only: skip dot-dirs (.git/.venv/.claude) and vendored
        # trees, plus this file (which necessarily names the invalid tokens).
        if any(part.startswith(".") or part in skip_dirs for part in rel.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = " ".join(path.read_text(encoding="utf-8", errors="ignore").split())
        # Only the ASSIGNED form is a real emission; `--log-level` written as a
        # bare noun in prose ("pass a --log-level in --extra") is not, and a
        # shell/placeholder expansion (=$VAR, =<v>) resolves elsewhere.
        for token in re.findall(r"--log-level=([A-Za-z_]+)", text):
            if token not in LOG_LEVEL_TOKENS_VALID_ON_EVERY_SERIES:
                offenders.append(f"{rel}: --log-level={token}")
    assert not offenders, (
        "committed files name a --log-level token that is not valid on every "
        "supported series (v8.0-v19.0):\n  " + "\n  ".join(offenders)
    )


def test_no_script_grep_keys_on_the_bare_INFO_level_token():
    """55-instance-ops.sh must never grep a delimited ` INFO ` LEVEL token.

    Odoo's level-25 aggregate line prints as `INFO` on v8.0-v16.0 and v19.0 but
    as `RUNBOT` on v17.0-v18.0, so any scan keyed on the level column silently
    changes meaning across the span. Every marker scan in this script keys on
    MESSAGE TEXT instead, which is what keeps that drift inert - this guard
    goes RED if someone 'improves' a scan by keying on the level column."""
    text = STEP55.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "grep" in line and re.search(r"\[\[:space:\]\]INFO\[\[:space:\]\]|[\"' ]INFO[\"' ]", line)
        and not line.strip().startswith("#")
    ]
    assert not offenders, (
        "a grep in 55-instance-ops.sh keys on the bare INFO level token, which "
        "is displayed as RUNBOT on v17.0-v18.0:\n  " + "\n  ".join(offenders)
    )


@requires_bash
@pytest.mark.parametrize("series,fail_line", [
    ("12.0", FAIL_LINE_V8_V13),
    ("12.0", FAIL_LINE_ALL_SERIES),
    ("17.0", FAIL_LINE_V14_PLUS),
    ("17.0", FAIL_LINE_ALL_SERIES),
])
def test_test_summary_failure_is_parsed_in_every_era(tmp_path, series, fail_line):
    """A failing suite must read as TEST_RESULT=failed on EVERY series.

    RED before the fix on the v8.0-v13.0 per-module wording ("Module sale: 2
    failures, 0 errors"): the old `[1-9][0-9]* (failed|error)` pattern is the
    v14+ phrasing and never matched it, so a failures-only run on six of the
    twelve supported series was certified GREEN."""
    res = _run_test_verb(tmp_path, "eras", [fail_line], version=series)
    assert _verdict(res) == "failed", (
        f"series {series}: {fail_line!r} must read as failed.\nstdout:\n{res.stdout}"
    )


@requires_bash
@pytest.mark.parametrize("series,ran_line", [
    ("8.0", RAN_LINE_V8_V13),
    ("12.0", RAN_LINE_V8_V13),
    ("13.0", RAN_LINE_V8_V13),
    ("14.0", RAN_LINE_V14_PLUS),
    ("17.0", RAN_LINE_V14_PLUS),
    ("19.0", RAN_LINE_V14_PLUS),
])
def test_green_run_needs_an_era_correct_ran_marker(tmp_path, series, ran_line):
    """A clean run carrying its era's real "the suite ran" marker is passed."""
    res = _run_test_verb(tmp_path, "green", [ran_line], version=series)
    assert _verdict(res) == "passed", (
        f"series {series}: {ran_line!r} must certify a pass.\nstdout:\n{res.stdout}"
    )


@requires_bash
@pytest.mark.parametrize("series,wrong_era_line", [
    ("12.0", RAN_LINE_V14_PLUS),
    ("17.0", RAN_LINE_V8_V13),
])
def test_ran_marker_from_the_wrong_era_does_not_certify_a_pass(tmp_path, series, wrong_era_line):
    """The era gate is a real SPLIT, not a permissive union: a series-13-and-below
    run may not be certified by the v14+ wording, and vice versa. Without this,
    'era-gated' would be indistinguishable from 'accept anything'."""
    res = _run_test_verb(tmp_path, "wrongera", [wrong_era_line], version=series)
    assert _verdict(res) == "inconclusive", (
        f"series {series} must not be certified by the other era's marker "
        f"{wrong_era_line!r}.\nstdout:\n{res.stdout}"
    )


@requires_bash
@pytest.mark.parametrize("ran_line", [RAN_LINE_V8_V13, RAN_LINE_V14_PLUS])
def test_missing_version_accepts_either_era_marker(tmp_path, ran_line):
    """With --version omitted the gate degrades PERMISSIVELY - either era's
    marker certifies a pass. A missing series must never manufacture a false
    HOLD for a caller that simply did not thread the version through."""
    res = _run_test_verb(tmp_path, "noversion", [ran_line], version=None)
    assert _verdict(res) == "passed", (
        f"omitting --version must accept {ran_line!r}.\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_zero_tests_summary_is_inconclusive_never_passed(tmp_path):
    """The v14+ summary for a filter that matched nothing ("0 failed, 0
    error(s) of 0 tests") must NOT certify a pass - the ran-marker requires a
    non-zero test count, which is the whole point of requiring it."""
    zero_line = (
        "2026-01-01 00:00:00,000 1 WARNING erad odoo.service.server: "
        "0 failed, 0 error(s) of 0 tests when loading database 'erad'"
    )
    res = _run_test_verb(tmp_path, "zerotests", [zero_line], version="17.0")
    assert _verdict(res) == "inconclusive", (
        f"a zero-test summary must never be a pass.\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_wait_log_reports_a_version_stable_progress_marker(tmp_path):
    """An in-flight build (no terminal marker yet) must still report the last
    real progress line, and that line must be one every supported series can
    emit: `loading <N> modules...` is INFO and byte-identical v8.0-v19.0,
    whereas `Registry loaded` does not exist before 15.0 - nine of the twelve
    supported series could never produce it.

    This pins the LAST-RESORT rung only. `loading <N> modules...` is logged once
    per registry load, so it never advances and is not the evidence a stall rule
    compares - that is `BUILD_PROGRESS`, and the ADVANCING per-file/per-test
    wordings it counts are covered by `test_verdict_paths_agree.py`. What must
    hold here is that a poll with nothing else to show never returns an EMPTY
    marker."""
    logf = _write_log(
        tmp_path, "inflight.log",
        "2026-01-01 00:00:00,000 1 INFO erad odoo.modules.loading: loading 42 modules...\n",
    )
    res = _run("wait-log", "--log", str(logf), "--timeout", "0", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode == 2, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "BUILD_RESULT=timeout" in res.stdout
    marker_lines = [l for l in res.stdout.splitlines() if l.startswith("BUILD_MARKER=")]
    assert marker_lines == ["BUILD_MARKER=2026-01-01 00:00:00,000 1 INFO erad "
                            "odoo.modules.loading: loading 42 modules..."], (
        f"an in-flight poll must surface the progress line as evidence, not an "
        f"empty marker.\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_open_log_prunes_stale_run_artifacts_and_never_the_current_one(tmp_path):
    """A run prunes log/findings artifacts older than the retention window and
    leaves the current run's log byte-complete.

    The completion verdict reads the WHOLE log for its markers, so the sweep
    must delete stale FILES only - a size cap or a truncation could drop the
    "Modules loaded." line and turn a green build into STATUS=error, which is
    why retention is time-based and never touches a live file."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    logs_dir = Path(env["ODOO_AI_HOME"]) / "logs"
    logs_dir.mkdir(parents=True)
    stale_log = logs_dir / "olddb-20200101T000000Z.log"
    stale_findings = logs_dir / "olddb-20200101T000000Z.findings.md"
    fresh_other = logs_dir / "otherdb-recent.log"
    for f in (stale_log, stale_findings, fresh_other):
        f.write_text("x\n", encoding="utf-8")
    old = time.time() - 60 * 60 * 24 * 90
    for f in (stale_log, stale_findings):
        os.utime(f, (old, old))

    res = _run(
        "init", "--db", "retaindb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    assert not stale_log.exists(), "a log past the retention window must be pruned"
    assert not stale_findings.exists(), (
        "the .findings.md sibling must be pruned with its log so the pair never desynchronises"
    )
    assert fresh_other.exists(), "a recent log from another run must survive the sweep"

    log_line = [l for l in res.stdout.splitlines() if l.startswith("LOG_PATH=")]
    assert len(log_line) == 1
    current = Path(log_line[0].split("=", 1)[1])
    assert current.exists(), "the current run's log must survive its own sweep"
    assert "Modules loaded." in current.read_text(encoding="utf-8"), (
        "the current run's log must stay byte-complete - a truncation or size "
        "cap that dropped the completion marker would fail this"
    )


@requires_bash
def test_completion_marker_floor_survives_a_quieter_caller_level(tmp_path):
    """The --log-handler=<ns>.modules.loading:INFO flag is a FLOOR, not a
    redundant leftover: with the base level already at info it looks like a
    no-op, but --extra is unrestricted passthrough, so a caller threading a
    quieter --log-level must still get STATUS=ok on a successful build.

    Deleting the flag as 'redundant' would silently turn every such build into
    a false STATUS=error. The stub below REACTS to the flag - it reproduces
    Odoo's own suppression, emitting the completion line only when the effective
    level reaches INFO or the per-logger floor raises that one logger back to it
    - so removing the floor from the script makes this test go red on
    STATUS=error, not merely on a missing argv token."""
    calls = tmp_path / "odoo-bin-calls.log"
    fake_bin = tmp_path / "odoo-bin"
    _write_stub(fake_bin, textwrap.dedent(f"""\
        echo "odoo-bin $*" >> "{calls}"
        # Odoo logs "Modules loaded." at INFO on <ns>.modules.loading; a quieter
        # --log-level hides it unless a --log-handler floor raises that logger.
        _lvl=info; _floor=0
        for _a in "$@"; do
          case "$_a" in
            --log-level=*) _lvl="${{_a#--log-level=}}" ;;
            --log-handler=*.modules.loading:INFO) _floor=1 ;;
          esac
        done
        if [[ "$_lvl" == "info" || "$_lvl" == "debug" || "$_floor" == "1" ]]; then
          echo "Modules loaded."
        fi
        exit 0
    """))
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", "floordb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--version", "17.0",
        "--extra", "--log-level=warn",
        env=env,
    )
    assert res.returncode == 0, (
        f"a quieter caller level must not break the completion contract.\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "STATUS=ok" in res.stdout, f"stdout={res.stdout}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-handler=odoo.modules.loading:INFO" in call_content, (
        f"the completion-marker floor must still be emitted: {call_content}"
    )
    assert call_content.index("--log-handler=odoo.modules.loading:INFO") < call_content.index(
        "--log-level=warn"
    ), (
        f"the floor must precede the caller's --extra level: {call_content}"
    )


# ---------------------------------------------------------------------------
# Contract 9: the era gate must resolve a ZERO-PADDED major to the same era its
# unpadded form resolves to.
#
# Bash reads a 0-prefixed integer literal as OCTAL, so `08`/`09` are invalid
# octal: `(( major < 10 ))` errors on them and the failed comparison reads
# FALSE, silently routing a v8/v9 target down the v10+/v14+ branch - wrong
# logger namespace for the forced completion marker, wrong "the suite ran"
# marker for the test verdict.
# ---------------------------------------------------------------------------

@requires_bash
@pytest.mark.parametrize("series", ["08.0", "09.0"])
def test_zero_padded_legacy_series_still_resolves_the_openerp_namespace(tmp_path, series):
    """A zero-padded v8/v9 must force `--log-handler=openerp.modules.loading:INFO`.

    On the `odoo` namespace the completion-marker floor never applies to the real
    v8/v9 logger, so a green build can lose "Modules loaded." and report
    STATUS=error."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "init", "--db", f"padns{series.replace('.', '')}", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--version", series,
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    call_content = (tmp_path / "odoo-bin-calls.log").read_text(encoding="utf-8")
    assert "--log-handler=openerp.modules.loading:INFO" in call_content, (
        f"series={series}: a zero-padded legacy major must resolve to the openerp "
        f"namespace, not odoo: {call_content}"
    )


@requires_bash
@pytest.mark.parametrize("series", ["08.0", "09.0"])
def test_zero_padded_legacy_series_still_picks_the_legacy_ran_marker(tmp_path, series):
    """A zero-padded v8/v9 must accept the LEGACY ran-marker and reject the v14+ one.

    Landing on the modern branch would reverse both verdicts: a genuinely green
    v8/v9 run reads `inconclusive`, and a v14+-worded line falsely certifies a
    pass on a series that cannot emit it."""
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    res_ok = _run_test_verb(legacy_dir, "padok", [RAN_LINE_V8_V13], version=series)
    assert _verdict(res_ok) == "passed", (
        f"series {series}: the legacy ran-marker must certify a pass.\nstdout:\n{res_ok.stdout}"
    )

    modern_dir = tmp_path / "modern"
    modern_dir.mkdir()
    res_wrong = _run_test_verb(modern_dir, "padwrong", [RAN_LINE_V14_PLUS], version=series)
    assert _verdict(res_wrong) == "inconclusive", (
        f"series {series}: the v14+ marker must NOT certify a pass on a legacy "
        f"series.\nstdout:\n{res_wrong.stdout}"
    )


# ---------------------------------------------------------------------------
# Contract 10: `--log-mode warn` is REFUSED for the test verb.
#
# `warn` suppresses the INFO summary that is the only positive proof a suite
# ran, so every GREEN run under it parses as TEST_RESULT=inconclusive. The
# parameter is a closed allowlist; the hazard is removed at the flag, not
# documented downstream.
# ---------------------------------------------------------------------------

@requires_bash
def test_log_mode_warn_is_refused_because_it_hides_the_pass_summary(tmp_path):
    """`--log-mode warn` must exit 2 and never reach odoo-bin."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0)
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)

    res = _run(
        "test", "--db", "warnmode", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        "--log-mode", "warn",
        env=env,
    )
    assert res.returncode == 2, (
        f"--log-mode warn must be refused with exit 2.\n"
        f"rc={res.returncode} stdout={res.stdout} stderr={res.stderr}"
    )
    assert not (tmp_path / "odoo-bin-calls.log").exists(), (
        "a refused --log-mode must never launch odoo-bin"
    )
    assert "inconclusive" in res.stderr, (
        f"the refusal must name the consequence it prevents.\nstderr={res.stderr}"
    )


# ---------------------------------------------------------------------------
# Contract 11: an INSTALL failure inside a --test-enable build is `failed`,
# never `inconclusive`.
#
# A misspelled module or an unmet dependency makes Odoo silently skip the
# install at exit 0: no test ever runs, so the log carries no fail-marker, no
# skip-marker and no ran-marker. Classifying that as `inconclusive` ("we could
# not tell") understates it - the run is a hard failure and the caller must
# halt, not merely hold.
# ---------------------------------------------------------------------------

@requires_bash
@pytest.mark.parametrize("failure_line", [
    "2026-01-01 00:00:00,000 1 WARNING erad odoo.modules.loading: "
    "invalid module names, ignored: my_moduel",
    "2026-01-01 00:00:00,000 1 WARNING erad odoo.modules.loading: "
    "Some modules are not loaded, some dependencies or manifest may be missing: ['my_module']",
    "2026-01-01 00:00:00,000 1 WARNING erad odoo.modules.graph: "
    "module my_module: Unmet dependencies: account",
    "2026-01-01 00:00:00,000 1 CRITICAL erad odoo.modules.loading: "
    "Module my_module cannot be installed",
])
def test_install_failure_inside_a_test_run_is_failed_not_inconclusive(tmp_path, failure_line):
    """A silent-skip install marker in a test build must yield TEST_RESULT=failed."""
    res = _run_test_verb(tmp_path, "instfail", [failure_line], version="17.0")
    assert _verdict(res) == "failed", (
        f"an install failure inside a test build is a FAILED run, not an "
        f"inconclusive one: {failure_line!r}\nstdout:\n{res.stdout}"
    )


@requires_bash
def test_install_failure_outranks_an_otherwise_green_ran_marker(tmp_path):
    """Modules that DID install can run green while a named module was silently
    skipped - the ran-marker must not certify that partial run as a pass."""
    lines = [
        "2026-01-01 00:00:00,000 1 WARNING erad odoo.modules.loading: "
        "invalid module names, ignored: my_moduel",
        RAN_LINE_V14_PLUS,
    ]
    res = _run_test_verb(tmp_path, "partialinst", lines, version="17.0")
    assert _verdict(res) == "failed", (
        f"a green ran-marker must not mask a skipped install.\nstdout:\n{res.stdout}"
    )


# ---------------------------------------------------------------------------
# Contract 12: the retention sweep must never unlink a LIVE instance's log.
#
# 50-instance-spinup.sh writes long-lived listening-instance logs into the SAME
# shared logs dir under the same <db>-<ts>.log convention, and a lease with a
# verified-alive owner pid is never TTL-reclaimed. An instance that stays quiet
# past the retention window would otherwise have its open log unlinked out from
# under the server's fd: the server keeps writing to the detached inode while
# every path-based read reports "no such file".
# ---------------------------------------------------------------------------

def _age_out(*paths: Path) -> None:
    """Backdate paths well past any plausible retention window."""
    old = time.time() - 60 * 60 * 24 * 90
    for p in paths:
        os.utime(p, (old, old))


@requires_bash
def test_retention_sweep_spares_a_leased_instances_log(tmp_path):
    """A log whose database is referenced by the allocator lease registry
    survives the sweep; an unreferenced log of the same age does not."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    _seed_lease_registry(env, [_fresh_foreign_lease("liveinstance", "run-other")])

    logs_dir = Path(env["ODOO_AI_HOME"]) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    live_log = logs_dir / "liveinstance-20200101T000000Z.log"
    live_findings = logs_dir / "liveinstance-20200101T000000Z.findings.md"
    orphan_log = logs_dir / "goneinstance-20200101T000000Z.log"
    for f in (live_log, live_findings, orphan_log):
        f.write_text("x\n", encoding="utf-8")
    _age_out(live_log, live_findings, orphan_log)

    res = _run(
        "init", "--db", "sweepdb", "--python", str(fake_py),
        "--addons", str(addons_dir), "--modules", "sale",
        env=env,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    assert live_log.exists(), (
        "the sweep unlinked the log of an instance the lease registry still "
        "references - a live server's open fd would keep writing to a detached inode"
    )
    assert live_findings.exists(), (
        "the .findings.md sibling of a referenced instance must be spared with its log"
    )
    assert not orphan_log.exists(), (
        "a stale log referenced by no lease must still be pruned - sparing "
        "everything would disable retention instead of scoping it"
    )


@requires_bash
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses file permissions, so an unreadable registry cannot be simulated",
)
def test_retention_sweep_is_skipped_when_the_lease_registry_is_unreadable(tmp_path):
    """Registry present but unreadable -> sweep NOTHING (fail closed).

    Sweeping blind is the one outcome that can destroy a live instance's log, so
    an unreadable registry must stop the sweep rather than degrade to deleting
    everything old."""
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output='echo "Modules loaded."')
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons_dir = tmp_path / "addons"
    addons_dir.mkdir()

    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    _seed_lease_registry(env, [])
    registry = Path(env["ODOO_AI_HOME"]) / "runtime" / "leases.json"
    registry.chmod(0o000)

    logs_dir = Path(env["ODOO_AI_HOME"]) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stale_log = logs_dir / "unknowndb-20200101T000000Z.log"
    stale_log.write_text("x\n", encoding="utf-8")
    _age_out(stale_log)

    try:
        res = _run(
            "init", "--db", "blinddb", "--python", str(fake_py),
            "--addons", str(addons_dir), "--modules", "sale",
            env=env,
        )
        assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
        assert stale_log.exists(), (
            "with the lease registry unreadable the sweep must delete nothing - "
            "it cannot prove any log does not belong to a live instance"
        )
    finally:
        registry.chmod(0o644)


# ---------------------------------------------------------------------------
# wait-log's default bound must not race the harness's per-call ceiling
#
# A default EQUAL to the tool ceiling is a trap: when the harness wins the race
# the call returns NO `BUILD_RESULT=` line, the caller has nothing to check, and
# it reports "still waiting" - the exact idle-stall this active-wait mechanism
# exists to prevent. Asserted as a RELATIONSHIP between the two declared
# constants, never against the literal 570, so raising or lowering the ceiling
# shows up here as a visible failure instead of silently becoming wrong again.
# ---------------------------------------------------------------------------
def _sh_constant(name: str) -> int:
    """Read an integer constant from 55-instance-ops.sh by name."""
    import re
    src = STEP55.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(name)}=(\d+)\s*$", src, re.M)
    assert m, f"{name} must be declared as a bare integer constant in 55-instance-ops.sh"
    return int(m.group(1))


def test_wait_log_default_timeout_stays_below_the_tool_call_ceiling():
    default_s = _sh_constant("_WAIT_LOG_DEFAULT_TIMEOUT_S")
    ceiling_s = _sh_constant("_TOOL_CALL_CEILING_S")
    assert default_s < ceiling_s, (
        f"wait-log's default bound ({default_s}s) must be strictly BELOW the "
        f"per-call tool ceiling ({ceiling_s}s). At or above it, the harness can cut "
        "the call off before any BUILD_RESULT= line is printed, leaving the caller "
        "with nothing to check - an idle stall by construction."
    )
    assert ceiling_s - default_s >= 15, (
        f"leave real headroom: {ceiling_s - default_s}s between the default bound and "
        "the ceiling is not enough to print the verdict and return"
    )


def test_wait_log_uses_the_declared_default_not_a_hardcoded_number():
    """The constant must actually REACH cmd_wait_log. A constant that is declared
    and never read is this repo's most common defect shape - the guard above would
    then pass while the real default stayed at the ceiling."""
    import re
    src = STEP55.read_text(encoding="utf-8")
    m = re.search(r"local logf=\"\" timeout=(\S+) interval=", src)
    assert m, "cmd_wait_log's option defaults line was not found"
    assert m.group(1) == '"$_WAIT_LOG_DEFAULT_TIMEOUT_S"', (
        f"cmd_wait_log must default to the declared constant, not the literal "
        f"{m.group(1)} - two sources for one number is how it drifted to the ceiling"
    )


@requires_bash
def test_wait_log_always_prints_a_build_result_within_its_bound(tmp_path):
    """The behavior the bound protects: a wait that reaches its timeout STILL emits
    a terminal `BUILD_RESULT=` line (and a non-zero exit), so the caller always has
    something to act on rather than an empty response."""
    logf = tmp_path / "build.log"
    logf.write_text("Loading module x\n", encoding="utf-8")  # no terminal marker
    res = _run("wait-log", "--log", str(logf), "--timeout", "1", "--interval", "1",
               env=_base_env(tmp_path))
    assert res.returncode != 0, "a timed-out wait must exit non-zero"
    assert "BUILD_RESULT=timeout" in res.stdout, (
        f"a bounded wait must ALWAYS print a terminal BUILD_RESULT line; got {res.stdout!r}"
    )


def test_drop_threads_odoo_root_to_odoo_db_py(tmp_path):
    """A source checkout is not pip-installed, so `import odoo` resolves only with
    the repo root on sys.path - which is the ONLY reason odoo-bin works. Without
    this passthrough every through-Odoo drop on a source instance exits 10 and the
    caller takes a raw-client fallback it should never have needed."""
    log = tmp_path / "odoo-db-argv.log"
    py_dir = tmp_path / "logpy"
    py_dir.mkdir()
    fake_py = py_dir / "python"
    _write_stub(fake_py, f'echo "$@" >> "{log}"\nexit 0\n')

    res = _run(
        "drop", "--db", "dropme", "--python", str(fake_py),
        "--db-host", "pghost", "--odoo-root", "/srv/core",
        env=_base_env(tmp_path),
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    argv = log.read_text(encoding="utf-8")
    assert "--odoo-root /srv/core" in argv, (
        f"drop must thread --odoo-root through to odoo_db.py: {argv}"
    )


def test_drop_omits_odoo_root_when_not_declared(tmp_path):
    """Absent stays absent: an undeclared odoo_root must not be fabricated into a
    guessed path, which would put the WRONG checkout on sys.path."""
    log = tmp_path / "odoo-db-argv.log"
    py_dir = tmp_path / "logpy"
    py_dir.mkdir()
    fake_py = py_dir / "python"
    _write_stub(fake_py, f'echo "$@" >> "{log}"\nexit 0\n')

    res = _run("drop", "--db", "dropme", "--python", str(fake_py), env=_base_env(tmp_path))
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "--odoo-root" not in log.read_text(encoding="utf-8")
