"""Both verdict paths of setup step 55 must read the same log the same way.

`55-instance-ops.sh` decides "did this build fail?" TWICE. `_parse_test_result`
produces the foreground `TEST_RESULT=` verdict once odoo-bin has exited, and
`_scan_build_markers` produces the background `BUILD_RESULT=` verdict that a
polling `wait-log` caller reads while the build is still in flight. Two
independent sensitivities over one log file is how the two came to answer
opposite things about the same run - and a caller that cannot trust the
blocking wait goes back to hand-rolling a poll loop, which is the exact
behavior the blocking wait exists to remove.

Contracts protected here. Every assertion is BEHAVIORAL - a log goes in, a
verdict comes out; none of them reads the script's text or names one of its
regexes, so a rewrite that keeps the behavior stays green and a rewrite that
loses it goes red no matter which phrasing it picks:

  1. An ERROR-LEVEL log line is not a verdict. Odoo logs at ERROR for many
     reasons unrelated to the build (a scheduled job raising, a mail send, a
     deprecated call), so neither path may promote one to a terminal failure -
     for a test build OR for an install/update build.
  2. A per-test failure is not a completion signal. The suite keeps running and
     the run appends its OWN `TEST_RESULT=` line when it finishes, so a mid-run
     `FAIL:`/`ERROR:` marker (plus the traceback that always accompanies it)
     must leave the wait un-decided, never preempt that verdict.
  3. A terminal FAILURE for a test build is the run's own `TEST_RESULT=failed`,
     or a hard abort proving odoo-bin died instead of continuing.
  4. The count fields and the findings file may never contradict the verdict.
     A run whose only failure signal is an AGGREGATE line still reports that
     line's numbers, and a figure the log cannot measure is reported EMPTY -
     never as a fabricated 0.

Marker wordings below are the VERBATIM Odoo strings, read from all 12 series in
a local checkout of each (v8.0-v19.0):
  * `Module %s: %d failures, %d errors`            v8.0-v13.0 modules/module.py
  * `Module %s: %d failures, %d errors of %d tests` v14.0-v19.0 modules/loading.py
  * `At least one test failed when loading the modules.` ALL 12, modules/loading.py
  * `<F> failed, <E> error(s) of <T> tests`        v14.0-v19.0 tests/result.py
    (`OdooTestResult.__str__`) rendered by service/server.py's
    `"%s when loading database %r"`
  * `Ran %d test%s in %.3fs`                       v8.0-v13.0 modules/module.py

Offline: no PostgreSQL, no real Odoo, no network.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEP55 = (
    ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "55-instance-ops.sh"
)

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


# ---------------------------------------------------------------------------
# Real Odoo log lines
# ---------------------------------------------------------------------------

# An ordinary ERROR-LEVEL line with nothing to do with the tests: ir_cron logs
# one every time a scheduled job raises. On a real 17.0 run of a large cluster
# the great majority of ERROR-level lines are of this kind, so keying a verdict
# on the level column turns each of them into a false terminal failure.
UNRELATED_ERROR_LINE = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.addons.base.models.ir_cron: "
    "Call of self.env['res.partner'].method() failed in Job"
)
PASSING_SUMMARY = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.service.server: "
    "0 failed, 0 error(s) of 41 tests when loading database 'testdb'"
)
LEGACY_RAN_MARKER = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.module: Ran 41 tests in 1.234s"
)
LOADED_MARKER = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.loading: Modules loaded."
)
PROGRESS_LINE = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.loading: loading 42 modules..."
)

# The ADVANCING progress markers, read from a local checkout of every one of the
# 12 supported series (8.0-19.0) - the literal format string AND its log level,
# because a DEBUG line is invisible at the shared `info` floor:
#   * `loading %s/%s`      INFO, once per data file, modules/loading.py, ALL 12
#   * `Starting %s ...`    INFO, once per test STARTED, 13.0-19.0
#                          (13.0 modules/module.py, 14.0-15.0 tests/runner.py,
#                           16.0-19.0 tests/result.py)
#   * `%s running tests.`  INFO, once per test MODULE, 8.0-13.0
#                          modules/module.py - the only test-phase progress
#                          wording 8.0-12.0 emit at all
# `loading %d modules...` (PROGRESS_LINE above) is logged ONCE per registry
# load, so it stays frozen for a whole test suite and cannot separate a working
# run from a dead one - which is why it is not a progress marker here.
def _datafile_progress(module: str, path: str) -> str:
    return (f"2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.loading: "
            f"loading {module}/{path}")


def _test_start_progress(cls: str, method: str) -> str:
    """`Starting <Class>.<method> ...` - 13.0-19.0, one per test."""
    return (f"2026-01-01 00:00:00,000 1 INFO testdb odoo.addons.sale.tests.test_order: "
            f"Starting {cls}.{method} ...")


def _test_module_progress(mod: str) -> str:
    """`<test module> running tests.` - 8.0-13.0, one per test module."""
    return (f"2026-01-01 00:00:00,000 1 INFO testdb odoo.modules.module: "
            f"odoo.addons.{mod}.tests.test_main running tests.")

# ONE failing test, exactly as odoo/tests/result.py `logError` writes it: an
# INFO rule line, then an ERROR line "<flavour>: <test description>" whose
# message body continues with `traceback.TracebackException.format()`. MEASURED
# on two real run logs: the traceback count equals the FAIL:/ERROR: marker
# count exactly (1 and 1; 98 and 98), which is what makes a traceback per-test
# evidence rather than proof the run died.
PER_TEST_FAILURE_LINES = [
    "======================================================================",
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.addons.sale.tests.test_order: "
    "ERROR: TestSaleOrder.test_discount_cap",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/addons/sale/tests/test_order.py", line 42, in test_discount_cap',
    "    self.assertEqual(order.discount, 20)",
    "AssertionError: 21 != 20",
]

# The three AGGREGATE failure wordings, plus the numberless blanket line.
AGG_PER_MODULE_V8_V13 = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.modules.module: "
    "Module sale: 2 failures, 1 errors"
)
AGG_PER_MODULE_V14_PLUS = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.modules.loading: "
    "Module sale: 2 failures, 1 errors of 41 tests"
)
AGG_PER_DATABASE_V14_PLUS = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.service.server: "
    "2 failed, 1 error(s) of 41 tests when loading database 'testdb'"
)
AGG_BLANKET_ALL_SERIES = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.modules.loading: "
    "At least one test failed when loading the modules."
)
# An aggregate whose figures DISAGREE with the per-test markers it sits beside,
# so a test combining the two can only be satisfied by one of the sources. An
# aggregate that happens to repeat the per-test count proves no precedence at
# all - it passes whichever source wins.
AGG_PER_DATABASE_DISAGREEING = (
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.service.server: "
    "7 failed, 9 error(s) of 41 tests when loading database 'testdb'"
)
SECOND_PER_TEST_FAILURE_LINES = [
    "======================================================================",
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.addons.sale.tests.test_order: "
    "FAIL: TestSaleOrder.test_margin_floor",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/addons/sale/tests/test_order.py", line 61, in test_margin_floor',
    "    self.assertEqual(order.margin, 5)",
    "AssertionError: 4 != 5",
]
THIRD_PER_TEST_FAILURE_LINES = [
    "======================================================================",
    "2026-01-01 00:00:00,000 1 ERROR testdb odoo.addons.sale.tests.test_order: "
    "FAIL: TestSaleOrder.test_tax_rounding",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/addons/sale/tests/test_order.py", line 80, in test_tax_rounding',
    "    self.assertEqual(order.tax, 3)",
    "AssertionError: 2 != 3",
]

# Hard aborts: the run cannot deliver a verdict of its own after any of these.
# None of them appeared even once across the 98 failing tests of the measured
# 19.0 run, which is what separates them from a per-test traceback.
HARD_ABORTS = {
    "critical": (
        "2026-01-01 00:00:00,000 1 CRITICAL testdb odoo.modules.registry: "
        "Failed to initialize database `testdb`."
    ),
    "registry": (
        "2026-01-01 00:00:00,000 1 ERROR testdb odoo.http: Failed to load registry"
    ),
    "psycopg2": "psycopg2.OperationalError: could not connect to server",
    "parse-error": (
        "odoo.tools.convert.ParseError: while parsing sale_views.xml:12"
    ),
    "unmet-dependency": (
        "2026-01-01 00:00:00,000 1 WARNING testdb odoo.modules.loading: "
        "Unmet dependencies: sale_extra"
    ),
}

# The two shapes a run leaves behind when it FINISHED and certified nothing -
# both taken from run logs this plugin produced, and both the reason the
# `inconclusive` verdict exists at all.
#   * a real skip line: the modern test-runner logger name, then
#     `skipped <Class>.<method> : <reason>`;
#   * the summary of a run whose tag filter matched NOTHING - the era-correct
#     wording carrying a total of zero;
#   * the summary of a run that matched tests and skipped every one of them - a
#     non-zero total, no failures, and a skip line above it.
SKIPPED_TEST_LINE = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.addons.website.tests.test_ui: "
    "skipped TestUi.test_32_website_background_colorpicker : "
    "websocket-client module is not installed"
)
ZERO_TESTS_SUMMARY = (
    "2026-01-01 00:00:00,000 1 WARNING testdb odoo.tests.result: "
    "0 failed, 0 error(s) of 0 tests when loading database 'testdb'"
)
SKIP_ONLY_SUMMARY = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.service.server: "
    "0 failed, 0 error(s) of 4 tests when loading database 'testdb'"
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env.pop("ODOO_AI_INSTANCES", None)
    return env


def _run(subcmd: str, *args, env: dict, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(STEP55), subcmd, *args],
        capture_output=True, text=True, env=env, timeout=timeout,
    )


def _run_verb(tmp_path: Path, verb: str, *, db: str, lines: list[str],
              version: str | None = None, exit_code: int = 0):
    """Run a real odoo-bin verb against a stub that prints `lines` verbatim.

    Returns (CompletedProcess, log path, env) so the SAME log the foreground
    verdict was computed from can then be handed to `wait-log`.
    """
    work = tmp_path / f"work-{db}"
    work.mkdir(parents=True, exist_ok=True)
    fake_bin = work / "odoo-bin"
    payload = "\n".join(lines)
    _write_stub(fake_bin, f'cat <<"ODOO_LOG_EOF"\n{payload}\nODOO_LOG_EOF\nexit {exit_code}\n')
    fake_py = work / "python"
    real = which("python3") or "/usr/bin/python3"
    _write_stub(fake_py, textwrap.dedent(f"""\
        if [[ "$2" == "--version" ]]; then echo "Odoo Server (preflight)"; exit 0; fi
        if [[ "$1" == "{fake_bin}" ]]; then shift; exec bash "{fake_bin}" "$@"; fi
        exec {real} "$@"
    """))
    addons = work / "addons"
    addons.mkdir(exist_ok=True)
    env = _env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    args = ["--db", db, "--python", str(fake_py), "--addons", str(addons),
            "--modules", "sale"]
    if version is not None:
        args += ["--version", version]
    res = _run(verb, *args, env=env)
    log = next((l.split("=", 1)[1] for l in res.stdout.splitlines()
                if l.startswith("LOG_PATH=")), "")
    assert log, f"{verb} emitted no LOG_PATH=\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    return res, Path(log), env


def _stamped_log(tmp_path: Path, name: str, *, verb: str, series: str,
                 lines: list[str]) -> Path:
    """A log shaped exactly as the script opens one: the run-verb stamp first."""
    log = tmp_path / name
    log.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines)
    log.write_text(f"ODOO_AI_RUN_VERB={verb} SERIES={series}\n{body}\n", encoding="utf-8")
    return log


def _field(res: subprocess.CompletedProcess, key: str) -> str:
    """The single value of an emitted `KEY=value` line (EMPTY is a real value)."""
    vals = [l.split("=", 1)[1] for l in res.stdout.splitlines()
            if l.startswith(key + "=")]
    assert len(vals) == 1, (
        f"expected exactly one {key}= line, got {vals!r}\nstdout:\n{res.stdout}"
    )
    return vals[0]


def _wait(log: Path, env: dict) -> subprocess.CompletedProcess:
    return _run("wait-log", "--log", str(log), "--timeout", "0", "--interval", "1", env=env)


def _findings(res: subprocess.CompletedProcess) -> str:
    path = Path(_field(res, "FINDINGS_PATH"))
    assert path.exists(), f"findings file {path} was never written"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CONTRACT 1 - an ERROR-level log line is not a verdict
# ---------------------------------------------------------------------------

@requires_bash
def test_a_passing_run_with_an_unrelated_error_level_line_is_not_a_failure(tmp_path):
    """Both paths must call the SAME log a pass.

    A run that ends `0 failed, 0 error(s) of 41 tests` passed. An ir_cron ERROR
    line elsewhere in the log says nothing about the suite, so the polling
    verdict may not call the run a failure while the run's own verdict calls it
    a pass - a caller handed two opposite answers stops trusting the wait.
    """
    res, log, env = _run_verb(
        tmp_path, "test", db="passwitherror", version="17.0",
        lines=[PROGRESS_LINE, LOADED_MARKER, UNRELATED_ERROR_LINE, PASSING_SUMMARY])
    assert _field(res, "TEST_RESULT") == "passed", (
        f"an unrelated ERROR-level line must not fail a passing suite\n{res.stdout}"
    )

    waited = _wait(log, env)
    assert _field(waited, "BUILD_RESULT") != "failure", (
        "the polling verdict contradicts the run's own verdict on the same log: "
        f"TEST_RESULT=passed but BUILD_RESULT=failure\nwait-log stdout:\n{waited.stdout}"
    )
    assert "TEST_RESULT=passed" in waited.stdout, (
        f"wait-log must surface the verdict the log carries\n{waited.stdout}"
    )


@requires_bash
def test_a_test_run_still_in_flight_is_not_failed_by_an_unrelated_error_line(tmp_path):
    """Before the run's verdict lands, an unrelated ERROR line is not terminal.

    This is the timing harm: on a real 17.0 run the first ERROR-level line sat
    at log line 1411 of 32764, so a level-keyed predicate declared failure
    seconds into a 23-minute build.
    """
    log = _stamped_log(tmp_path, "inflight-test.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, UNRELATED_ERROR_LINE])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "timeout", (
        "an in-flight test build whose only ERROR line is unrelated must stay "
        f"un-decided, not be declared failed\nstdout:\n{waited.stdout}"
    )
    assert waited.returncode == 2, f"rc={waited.returncode}\n{waited.stdout}"


@requires_bash
@pytest.mark.parametrize("verb", ["init", "update"])
def test_an_unrelated_error_level_line_never_fails_an_install_or_update_build(tmp_path, verb):
    """The same exposure exists for a build that runs no tests at all.

    An install that reaches "Modules loaded." succeeded; a cron ERROR line
    logged along the way does not change that, and the foreground verdict
    already agrees - so the polling verdict must too.
    """
    res, log, env = _run_verb(
        tmp_path, verb, db=f"{verb}witherror", version="17.0",
        lines=[PROGRESS_LINE, UNRELATED_ERROR_LINE, LOADED_MARKER])
    assert "STATUS=ok" in res.stdout.splitlines(), (
        f"{verb} must succeed: an unrelated ERROR line is not an install failure"
        f"\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )

    waited = _wait(log, env)
    assert _field(waited, "BUILD_RESULT") == "success", (
        f"the polling verdict contradicts {verb}'s own STATUS=ok on the same log"
        f"\nwait-log stdout:\n{waited.stdout}"
    )


# ---------------------------------------------------------------------------
# CONTRACT 2 - a per-test failure is not a completion signal
# ---------------------------------------------------------------------------

@requires_bash
def test_a_mid_run_per_test_failure_does_not_preempt_the_runs_own_verdict(tmp_path):
    """One failing test is not the end of the suite.

    The suite keeps running and the run appends its own `TEST_RESULT=` line when
    it finishes. Declaring the build failed at the first failing test stops the
    wait while odoo-bin is still working, and hands the caller a verdict the run
    never published.
    """
    log = _stamped_log(tmp_path, "midrun-failure.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, *PER_TEST_FAILURE_LINES])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "timeout", (
        "a per-test failure with no verdict line yet must leave the wait "
        f"un-decided, not terminate it as a failure\nstdout:\n{waited.stdout}"
    )
    assert waited.returncode == 2, f"rc={waited.returncode}\n{waited.stdout}"


@requires_bash
def test_a_mid_run_module_aggregate_does_not_preempt_the_runs_own_verdict(tmp_path):
    """The per-MODULE aggregate is logged inside the module loop, so the run
    continues after it - it is progress on a doomed run, not completion."""
    log = _stamped_log(tmp_path, "midrun-module-agg.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, AGG_PER_MODULE_V14_PLUS])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "timeout", (
        "a per-module failure aggregate is not a completion signal - the run has "
        f"more modules to load\nstdout:\n{waited.stdout}"
    )


@requires_bash
def test_a_failing_summary_is_never_certified_as_a_successful_build(tmp_path):
    """The run's summary line reports its own non-zero counts.

    It is the era-correct "the suite ran" wording, so a completion check that
    reads only the wording and never the numbers certifies a FAILING run as a
    successful build.
    """
    log = _stamped_log(tmp_path, "failing-summary.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, AGG_PER_DATABASE_V14_PLUS])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") != "success", (
        "a summary reporting 2 failed / 1 error must never read as a successful "
        f"build\nstdout:\n{waited.stdout}"
    )


# ---------------------------------------------------------------------------
# CONTRACT 3 - what a TERMINAL failure is for a test build
# ---------------------------------------------------------------------------

@requires_bash
def test_the_runs_own_failed_verdict_is_a_terminal_failure(tmp_path):
    """`TEST_RESULT=failed` on the log is the authoritative failure.

    The run computed it after odoo-bin exited and appended it precisely so a
    polling caller could reach it; reporting that log as a successful build is
    the same contradiction read from the other direction.
    """
    log = _stamped_log(tmp_path, "verdict-failed.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, PASSING_SUMMARY,
                              "TEST_RESULT=failed"])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "failure", (
        f"TEST_RESULT=failed must read as a failed build\nstdout:\n{waited.stdout}"
    )
    assert waited.returncode == 1, f"rc={waited.returncode}\n{waited.stdout}"


@requires_bash
def test_the_runs_own_passed_verdict_is_a_successful_build(tmp_path):
    """The mirror of the rule above: the verdict decides, in both directions."""
    log = _stamped_log(tmp_path, "verdict-passed.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, PASSING_SUMMARY,
                              "TEST_RESULT=passed"])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "success", (
        f"TEST_RESULT=passed must read as a finished build\nstdout:\n{waited.stdout}"
    )


@requires_bash
@pytest.mark.parametrize("label", sorted(HARD_ABORTS))
def test_a_hard_abort_with_no_verdict_line_is_a_terminal_failure(tmp_path, label):
    """A build that DIED will never publish a verdict, so waiting for one is a
    guaranteed stall - these markers must terminate the wait as a failure."""
    log = _stamped_log(tmp_path, f"abort-{label}.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, HARD_ABORTS[label]])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "failure", (
        f"{label!r} proves the run died and must end the wait as a failure"
        f"\nstdout:\n{waited.stdout}"
    )
    assert waited.returncode == 1, f"rc={waited.returncode}\n{waited.stdout}"


# ---------------------------------------------------------------------------
# CONTRACT 4 - counts and findings may never contradict the verdict
# ---------------------------------------------------------------------------

AGGREGATE_ONLY_CASES = [
    # label, series, the run's ONLY failure signal, expected failed/error counts
    ("per-module-v8-v13", "12.0", AGG_PER_MODULE_V8_V13, "2", "1"),
    ("per-module-v14-plus", "17.0", AGG_PER_MODULE_V14_PLUS, "2", "1"),
    ("per-database-v14-plus", "17.0", AGG_PER_DATABASE_V14_PLUS, "2", "1"),
]


@requires_bash
@pytest.mark.parametrize("label,series,agg_line,want_failed,want_error", AGGREGATE_ONLY_CASES)
def test_an_aggregate_only_failure_reports_the_aggregates_own_numbers(
        tmp_path, label, series, agg_line, want_failed, want_error):
    """A run whose only failure signal is an AGGREGATE line still published its
    numbers - so the count fields must carry them.

    `TEST_FAILED=0 TEST_ERROR=0` next to `TEST_RESULT=failed` tells the caller
    the run failed and that nothing failed, in the same breath.
    """
    res, _log, _env_ = _run_verb(tmp_path, "test", db=f"agg{label.replace('-', '')}",
                                 version=series, lines=[PROGRESS_LINE, agg_line])
    assert _field(res, "TEST_RESULT") == "failed", (
        f"[{label}] the aggregate wording must read as a failure\n{res.stdout}"
    )
    assert _field(res, "TEST_FAILED") == want_failed, (
        f"[{label}] TEST_FAILED must carry the aggregate's own failure count "
        f"({want_failed}), never 0 beside a failed verdict\n{res.stdout}"
    )
    assert _field(res, "TEST_ERROR") == want_error, (
        f"[{label}] TEST_ERROR must carry the aggregate's own error count "
        f"({want_error}), never 0 beside a failed verdict\n{res.stdout}"
    )


@requires_bash
@pytest.mark.parametrize(
    "label,series,agg_line",
    [(c[0], c[1], c[2]) for c in AGGREGATE_ONLY_CASES]
    + [("blanket-all-series", "17.0", AGG_BLANKET_ALL_SERIES)],
)
def test_the_findings_file_never_claims_nothing_failed_for_a_failed_verdict(
        tmp_path, label, series, agg_line):
    """The findings file is the artifact an agent reads to learn WHY a build
    failed. It may not answer "nothing failed" for a run whose verdict is
    `failed` - and it must show the line that states the failure."""
    res, _log, _env_ = _run_verb(tmp_path, "test", db=f"fnd{label.replace('-', '')}",
                                 version=series, lines=[PROGRESS_LINE, agg_line])
    assert _field(res, "TEST_RESULT") == "failed", res.stdout
    text = _findings(res)
    assert "No failing or errored tests detected" not in text, (
        f"[{label}] the findings file for a FAILED run says nothing failed:\n{text}"
    )
    evidence = agg_line.split(": ", 2)[-1]
    assert evidence in text, (
        f"[{label}] the findings file must show the line that states the "
        f"failure ({evidence!r}):\n{text}"
    )


# A traceback with NOTHING to do with any test. Taken from the shape a real run
# leaves behind: the HTTP server thread raises, Python's threading module prints
# its own header and traceback, and the suite carries on. Odoo also writes one
# for every logged exception a request recovers from, for routing errors, and for
# every HttpCase 500 a test deliberately asserts on.
INCIDENTAL_TRACEBACK_LINES = [
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.service.server: HTTP service running",
    "Exception in thread odoo.service.httpd:",
    "Traceback (most recent call last):",
    '  File "/usr/lib/python3.11/threading.py", line 1045, in _bootstrap_inner',
    "    self.run()",
    "OSError: [Errno 9] Bad file descriptor",
]


@requires_bash
def test_a_traceback_alone_never_rules_a_test_run_failed(tmp_path):
    """A traceback is not a test verdict, and the executed rule must say so too.

    The marker SSOT already argues that on a `--test-enable` run a traceback is
    per-test/incidental evidence and never a completion or failure signal - the
    same false-RED class as keying on the log-LEVEL column. Ruling on it anyway
    fails a run whose OWN summary reports that nothing failed.

    Measured against every real run log on disk: the traceback count matches the
    per-test FAIL:/ERROR: marker count in only three quarters of them, diverging
    by as much as 96 tracebacks against 4 markers - so a traceback cannot stand
    in for a failure marker even as an approximation.
    """
    res, _log, _env_ = _run_verb(
        tmp_path, "test", db="tbonly", version="17.0",
        lines=[PROGRESS_LINE, *INCIDENTAL_TRACEBACK_LINES, PASSING_SUMMARY])
    assert _field(res, "TEST_RESULT") == "passed", (
        "a run whose own summary reports 0 failed / 0 errors was ruled failed by an "
        f"incidental traceback\n{res.stdout}"
    )
    assert _field(res, "TEST_FAILED") == "0", res.stdout
    assert _field(res, "TEST_ERROR") == "0", res.stdout


@requires_bash
def test_a_failing_test_is_still_failed_when_it_carries_a_traceback(tmp_path):
    """The guard on the other side - and the more dangerous direction.

    Dropping the traceback from the test verdict must not lose a single genuinely
    failing run. It cannot: `odoo/tests/result.py` logs the `FAIL:`/`ERROR:`
    marker BEFORE the traceback body, so every failing test is still named by a
    marker the verdict does rule on.
    """
    res, _log, _env_ = _run_verb(
        tmp_path, "test", db="tbfail", version="17.0",
        lines=[PROGRESS_LINE, *PER_TEST_FAILURE_LINES, AGG_PER_DATABASE_V14_PLUS])
    assert _field(res, "TEST_RESULT") == "failed", (
        "a run with a named failing test must still be failed\n" + res.stdout
    )
    waited = _wait(_log, _env_)
    assert _field(waited, "BUILD_RESULT") == "failure", (
        "the polling path must reach the same failed verdict\n" + waited.stdout
    )


@requires_bash
def test_a_hard_abort_still_fails_a_test_run_with_no_test_marker_at_all(tmp_path):
    """The other thing the traceback used to carry, which must NOT be lost.

    An install failure inside a `--test-enable` build writes no fail-, skip- or
    ran-marker, so without a rule of its own it falls through to a bare
    `inconclusive`. It is a FAILED run - the suite could not run - and the abort
    marker set, which stays terminal for every verb, is what rules it.
    """
    res, _log, _env_ = _run_verb(
        tmp_path, "test", db="abortonly", version="17.0",
        lines=[PROGRESS_LINE, HARD_ABORTS["critical"]])
    assert _field(res, "TEST_RESULT") == "failed", (
        "a build that aborted before its suite could run is failed, not "
        "inconclusive\n" + res.stdout
    )


@requires_bash
def test_a_count_the_log_cannot_measure_is_empty_never_zero(tmp_path):
    """The blanket failure line carries NO number.

    That run's failure counts are UNMEASURABLE, which is a different fact from
    zero - the same rule the scope fields already follow. Reporting 0 here
    fabricates a figure and contradicts the verdict at the same time.
    """
    res, _log, _env_ = _run_verb(tmp_path, "test", db="unmeasurable", version="17.0",
                                 lines=[PROGRESS_LINE, AGG_BLANKET_ALL_SERIES])
    assert _field(res, "TEST_RESULT") == "failed", res.stdout
    assert _field(res, "TEST_FAILED") == "", (
        "an unmeasurable failure count must be reported EMPTY, not 0\n" + res.stdout
    )
    assert _field(res, "TEST_ERROR") == "", (
        "an unmeasurable error count must be reported EMPTY, not 0\n" + res.stdout
    )


@requires_bash
@pytest.mark.parametrize("series,ran_marker", [
    ("12.0", LEGACY_RAN_MARKER),
    ("17.0", PASSING_SUMMARY),
])
def test_a_measured_zero_is_still_reported_as_zero(tmp_path, series, ran_marker):
    """EMPTY is reserved for "the log carried no marker to measure it".

    A suite that ran and named no failing test measured zero failures, so zero
    is the honest answer there - the distinction is only worth having if both
    sides of it hold.
    """
    res, _log, _env_ = _run_verb(tmp_path, "test", db=f"measured{series.replace('.', '')}",
                                 version=series, lines=[PROGRESS_LINE, LOADED_MARKER,
                                                        ran_marker])
    assert _field(res, "TEST_RESULT") == "passed", res.stdout
    assert _field(res, "TEST_FAILED") == "0", (
        f"a suite that ran clean measured 0 failures\n{res.stdout}"
    )
    assert _field(res, "TEST_ERROR") == "0", (
        f"a suite that ran clean measured 0 errors\n{res.stdout}"
    )


@requires_bash
def test_the_findings_file_explains_a_failure_the_log_never_recorded(tmp_path):
    """The last route to a `failed` verdict: odoo-bin exited non-zero over a log
    that names nothing wrong. Zero failing tests is the honest count there, so
    the findings file has to carry the REASON instead - "no failing tests" on its
    own would read as "nothing to look at" for a build that failed."""
    res, _log, _env_ = _run_verb(tmp_path, "test", db="exitonly", version="17.0",
                                 lines=[PROGRESS_LINE, LOADED_MARKER, PASSING_SUMMARY],
                                 exit_code=3)
    assert _field(res, "TEST_RESULT") == "failed", res.stdout
    text = _findings(res)
    assert "No failing or errored tests detected" not in text, (
        f"the findings file for a FAILED run says nothing failed:\n{text}"
    )
    assert "TEST_RESULT=failed" in text, (
        f"the findings file must state the verdict it was written for:\n{text}"
    )
    assert "exit code" in text, (
        f"the findings file must name the non-zero exit as the reason:\n{text}"
    )


@requires_bash
def test_an_install_silent_skip_fails_both_paths_together(tmp_path):
    """Agreement has to hold in the failure direction too, for a build that runs
    no tests: a silent-skipped module leaves odoo-bin at exit 0 with "Modules
    loaded." on the log, and both verdicts must still call it failed."""
    res, log, env = _run_verb(
        tmp_path, "init", db="silentskip", version="17.0",
        lines=[PROGRESS_LINE, "invalid module names, ignored", LOADED_MARKER])
    assert "STATUS=error" in res.stdout.splitlines(), (
        f"a silently skipped module is not a successful install\n{res.stdout}"
    )
    waited = _wait(log, env)
    assert _field(waited, "BUILD_RESULT") == "failure", (
        f"the polling verdict must agree with STATUS=error\n{waited.stdout}"
    )


@requires_bash
def test_individual_markers_still_win_over_the_aggregate(tmp_path):
    """The aggregate is a FALLBACK. When the log names the individual failing
    tests, those markers stay the source of the counts.

    The two sources must report DIFFERENT numbers for this to prove anything: a
    log whose per-test markers and whose aggregate agree passes under EITHER
    precedence rule and discriminates nothing. Here the log names 2 failing and
    1 errored test individually while its aggregate claims 7 and 9, so only the
    per-test figures can satisfy the assertions and only the aggregate's can
    fail them.
    """
    res, _log, _env_ = _run_verb(
        tmp_path, "test", db="individualwins", version="17.0",
        lines=[PROGRESS_LINE, *PER_TEST_FAILURE_LINES, *SECOND_PER_TEST_FAILURE_LINES,
               *THIRD_PER_TEST_FAILURE_LINES, AGG_PER_DATABASE_DISAGREEING])
    assert _field(res, "TEST_RESULT") == "failed", res.stdout
    assert _field(res, "TEST_FAILED") == "2", (
        "the two individually named FAILING tests must be counted from their own "
        f"markers, not read off the aggregate's `7 failed`\n{res.stdout}"
    )
    assert _field(res, "TEST_ERROR") == "1", (
        "the one individually named ERRORED test must be counted from its own "
        f"marker, not read off the aggregate's `9 error(s)`\n{res.stdout}"
    )


# ---------------------------------------------------------------------------
# CONTRACT 5 - a DEAD run and a HEALTHY one must not look the same
#
# The only stall rule an executing agent is given is "a whole window elapsed
# with the progress evidence UNCHANGED - that, not the clock, is the evidence
# the build stopped". That rule is only true if the evidence ADVANCES while the
# build works. The evidence a poll used to report during a test suite was
# `loading <N> modules...`, logged ONCE per registry load, so a healthy 20-minute
# suite and an odoo-bin killed mid-suite produced byte-identical output and the
# healthy run was abandoned as BLOCKED after two windows.
# ---------------------------------------------------------------------------

def _poll(log: Path, env: dict) -> tuple[str, str, int]:
    """One in-flight poll: (BUILD_PROGRESS, BUILD_MARKER, returncode)."""
    waited = _wait(log, env)
    return (_field(waited, "BUILD_PROGRESS"),
            _field(waited, "BUILD_MARKER"),
            waited.returncode)


def _append(log: Path, lines: list[str]) -> None:
    with log.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# Each era's own ADVANCING wording, and the phase it covers. A series is only
# covered if at least one row applies to it.
ADVANCING_MARKERS = [
    ("test-phase-13.0-19.0", "17.0", "test",
     [_test_start_progress("TestSaleOrder", f"test_case_{i}") for i in range(1, 21)]),
    ("test-phase-8.0-13.0", "12.0", "test",
     [_test_module_progress(f"mod{i}") for i in range(1, 21)]),
    ("install-phase-all-series", "17.0", "test",
     [_datafile_progress("sale", f"views/view_{i}.xml") for i in range(1, 21)]),
    ("install-phase-init-verb", "8.0", "init",
     [_datafile_progress("base", f"data/data_{i}.xml") for i in range(1, 21)]),
]


@requires_bash
@pytest.mark.parametrize("label,series,verb,advancing", ADVANCING_MARKERS)
def test_a_progressing_run_and_a_stalled_one_yield_different_evidence(
        tmp_path, label, series, verb, advancing):
    """THE discriminating test: poll twice, and the two answers must differ for a
    run that did work and match for a run that did not.

    Same log, same code path, the ONLY difference being whether odoo-bin wrote
    anything between the two polls. If both halves cannot be true at once the
    stall rule is worthless: matching answers on a working run abandon it, and
    differing answers on a dead one wait for it forever.
    """
    env = _env(tmp_path)
    log = _stamped_log(tmp_path, f"advancing-{label}.log", verb=verb, series=series,
                       lines=[PROGRESS_LINE, *advancing[:5]])

    first_progress, first_marker, first_rc = _poll(log, env)
    assert first_rc == 2, f"[{label}] the run is still in flight\nrc={first_rc}"
    assert first_progress, (
        f"[{label}] a poll must report a progress reading a caller can compare; "
        "an absent field gives the stall rule nothing to work with"
    )

    # HEALTHY: odoo-bin wrote more of the same real output between the polls.
    _append(log, advancing[5:])
    grown_progress, grown_marker, grown_rc = _poll(log, env)
    assert grown_rc == 2, f"[{label}] still in flight\nrc={grown_rc}"
    assert grown_progress != first_progress, (
        f"[{label}] the build did {len(advancing) - 5} more units of work between "
        f"the two polls and the progress reading did not move ({first_progress!r} "
        "-> unchanged): the stall rule would abandon a healthy long run as BLOCKED"
    )
    assert grown_marker != first_marker, (
        f"[{label}] BUILD_MARKER is byte-identical across a poll that saw real new "
        f"output ({first_marker!r}) - the field the contract names as the progress "
        "evidence must move when the build moves"
    )

    # DEAD: nothing was written. Same code path, no append.
    stalled_progress, stalled_marker, stalled_rc = _poll(log, env)
    assert stalled_rc == 2, f"[{label}] a dead run publishes no verdict\nrc={stalled_rc}"
    assert stalled_progress == grown_progress, (
        f"[{label}] nothing was written between these two polls, so the progress "
        f"reading must be IDENTICAL ({grown_progress!r} -> {stalled_progress!r}); "
        "a reading that drifts on its own can never prove a build stopped"
    )
    assert stalled_marker == grown_marker, (
        f"[{label}] BUILD_MARKER must also be identical when nothing was written "
        f"({grown_marker!r} -> {stalled_marker!r})"
    )


@requires_bash
def test_a_run_killed_mid_suite_is_distinguishable_from_one_still_working(tmp_path):
    """The measured failure, end to end.

    A log that stops mid-suite because odoo-bin was killed (no verdict line, no
    hard-abort marker - the process was simply reaped) and a log still being
    appended to are the two cases the poll has to tell apart. Both are
    `BUILD_RESULT=timeout` by design - "not decided yet" is the honest verdict
    for both, and neither may be read as passed - so the ONLY thing that can
    separate them is whether the progress reading moved.
    """
    env = _env(tmp_path)
    body = [PROGRESS_LINE, LOADED_MARKER,
            *[_test_start_progress("TestSaleOrder", f"test_{i}") for i in range(1, 51)]]
    killed = _stamped_log(tmp_path, "killed-mid-suite.log", verb="test", series="17.0",
                          lines=body)
    working = _stamped_log(tmp_path, "still-working.log", verb="test", series="17.0",
                           lines=body)

    killed_first = _poll(killed, env)
    working_first = _poll(working, env)
    assert killed_first[0] == working_first[0], (
        "the two logs are byte-identical right now, so the readings must match: "
        f"{killed_first[0]!r} vs {working_first[0]!r}"
    )

    # Only one of them keeps running.
    _append(working, [_test_start_progress("TestSaleOrder", f"test_{i}")
                      for i in range(51, 551)])

    killed_second = _poll(killed, env)
    working_second = _poll(working, env)

    assert killed_second[0] == killed_first[0], (
        "the killed run wrote nothing, so its reading must be unchanged: "
        f"{killed_first[0]!r} -> {killed_second[0]!r}"
    )
    assert working_second[0] != working_first[0], (
        "500 lines of genuine new passing-test output landed between the polls and "
        f"the reading did not move: {working_first[0]!r} -> {working_second[0]!r}"
    )
    assert killed_second[0] != working_second[0], (
        "after one window the dead run and the healthy run still report the same "
        f"evidence ({killed_second[0]!r}) - indistinguishable, which is what made "
        "the stall rule false"
    )


@requires_bash
@pytest.mark.parametrize("label,series,verb,lines,want_result", [
    ("timeout", "17.0", "test", [PROGRESS_LINE], "timeout"),
    ("test-failed", "17.0", "test", [PROGRESS_LINE, "TEST_RESULT=failed"], "failure"),
    ("test-passed", "17.0", "test", [PROGRESS_LINE, "TEST_RESULT=passed"], "success"),
    ("init-ok", "17.0", "init", [PROGRESS_LINE, LOADED_MARKER], "success"),
    ("hard-abort", "17.0", "test", [PROGRESS_LINE, HARD_ABORTS["critical"]], "failure"),
])
def test_the_progress_reading_is_emitted_on_every_path(
        tmp_path, label, series, verb, lines, want_result):
    """A field a caller must diff across polls has to be there on EVERY poll.

    Emitted only on the un-decided path, it is absent exactly when the caller is
    mid-comparison, and "the field vanished" is indistinguishable from "the field
    did not move".
    """
    log = _stamped_log(tmp_path, f"everypath-{label}.log", verb=verb, series=series,
                       lines=lines)
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == want_result, waited.stdout
    assert _field(waited, "BUILD_PROGRESS"), (
        f"[{label}] no progress reading on a {want_result} poll\n{waited.stdout}"
    )


@requires_bash
def test_progress_evidence_is_never_a_verdict(tmp_path):
    """Progress may not decide an outcome in EITHER direction.

    A log made of nothing but hundreds of real progress lines is a build that is
    working, not one that finished - certifying there would re-create the bug
    where the wait returned before the suite ended, and failing there would
    abandon a healthy run.
    """
    log = _stamped_log(
        tmp_path, "progress-only.log", verb="test", series="17.0",
        lines=[PROGRESS_LINE,
               *[_datafile_progress("sale", f"views/v{i}.xml") for i in range(1, 31)],
               *[_test_start_progress("TestSaleOrder", f"test_{i}") for i in range(1, 31)]])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "timeout", (
        "60 progress lines are not a completed build\n" + waited.stdout
    )
    assert waited.returncode == 2, f"rc={waited.returncode}\n{waited.stdout}"
    assert "TEST_RESULT=" not in waited.stdout, (
        "a progress-only log publishes no verdict, so none may be echoed\n"
        + waited.stdout
    )


@requires_bash
def test_a_run_with_no_progress_marker_at_all_still_advances_while_it_writes(tmp_path):
    """A log with no progress marker at all must still be comparable AND advance.

    A caller-chosen log level above INFO suppresses every progress wording, and a
    log that has just been opened has not reached its first one. Neither may
    resolve to success or failure, and neither may look like a stall while the
    file is still growing.

    The assertions below name only what a CALLER can act on - the reading is
    present, it moves when the run writes, it holds still when the run does not,
    and it decides nothing. They deliberately do NOT name the reading's internal
    shape: which components it is built from is the script's business, and
    pinning that pins one arrangement rather than the contract.
    """
    env = _env(tmp_path)
    quiet = [
        "2026-01-01 00:00:00,000 1 WARNING testdb odoo.modules.loading: "
        "deprecated attribute in view sale.view_order_form",
    ]
    log = _stamped_log(tmp_path, "no-progress-markers.log", verb="test", series="17.0",
                       lines=quiet)
    first_progress, _first_marker, rc = _poll(log, env)
    assert rc == 2, f"an in-flight build with no progress marker is not decided\nrc={rc}"
    assert first_progress, (
        "a build whose level suppresses every progress wording still has to give the "
        "caller something to compare - an absent reading gives the stall rule nothing"
    )

    _append(log, quiet * 20)
    grown_progress, _grown_marker, rc = _poll(log, env)
    assert rc == 2, f"rc={rc}"
    assert grown_progress != first_progress, (
        "the log grew, so the reading must move - otherwise a build "
        f"running at a quiet log level is read as stalled: {first_progress!r}"
    )

    # Nothing written -> the reading must hold still, or it can never prove a stop.
    stalled_progress, _m, rc = _poll(log, env)
    assert rc == 2, f"rc={rc}"
    assert stalled_progress == grown_progress, (
        "nothing was appended between these two polls, so the reading must be "
        f"identical: {grown_progress!r} -> {stalled_progress!r}"
    )

    # A progress marker landing is more evidence, never less: the reading must
    # still move, and must still not decide the build.
    _append(log, [_test_start_progress("TestSaleOrder", "test_first")])
    marker_progress, _m, rc = _poll(log, env)
    assert rc == 2, (
        "a progress marker is not a verdict; the build is still un-decided\n"
        f"rc={rc}"
    )
    assert marker_progress != stalled_progress, (
        "the run published its first progress marker and the reading did not move: "
        f"{stalled_progress!r} -> {marker_progress!r}"
    )


@requires_bash
def test_the_reading_keeps_moving_after_the_runs_last_progress_marker(tmp_path):
    """THE case a real long build spends most of its wall clock in.

    A `--test-enable` build publishes hundreds of progress lines while it installs
    modules, then enters the browser/JS suite: ONE test that streams thousands of
    console lines under a logger no progress wording matches. From that point the
    marker count is frozen for the rest of the run - measured on real run logs,
    for over 1,700 seconds of a 1,838-second build, three full wait windows.

    So the marker count alone cannot carry the stall rule. Whatever the reading is
    built from, it MUST move while the run writes, or an agent obeying "a non-empty
    reading repeated across a whole window is the evidence the build stopped"
    abandons a healthy run as BLOCKED. Both halves are asserted here: it moves
    while output lands, and it holds still when output stops.
    """
    env = _env(tmp_path)
    # Install phase: real progress markers, exactly as every build emits them.
    installed = [PROGRESS_LINE,
                 *[_datafile_progress("web", f"views/v{i}.xml") for i in range(1, 121)]]
    log = _stamped_log(tmp_path, "browser-suite.log", verb="test", series="17.0",
                       lines=[*installed, LOADED_MARKER,
                              _test_start_progress("WebSuite", "test_unit_desktop")])
    before, _m, rc = _poll(log, env)
    assert rc == 2, f"the suite has only just started\nrc={rc}"
    assert before, "the reading must be present once the suite starts"

    # The browser suite now streams console output under its own logger. Not one
    # of these lines is a progress marker, and no further marker will ever land.
    console = [
        "2026-01-01 00:00:00,000 1 INFO testdb "
        "odoo.addons.web.tests.test_js.WebSuite.test_unit_desktop.browser: "
        f'[HOOT] Running test "@web/views/case_{i}"'
        for i in range(1, 401)
    ]
    _append(log, console[:200])
    during, _m, rc = _poll(log, env)
    assert rc == 2, f"one long test is not a finished build\nrc={rc}"
    assert during != before, (
        "200 lines of genuine browser-suite output landed and the progress reading "
        f"did not move ({before!r}): a healthy run inside one long test is read as "
        "stalled and reported BLOCKED"
    )

    _append(log, console[200:])
    later, _m, rc = _poll(log, env)
    assert rc == 2, f"rc={rc}"
    assert later != during, (
        "a second window of genuine browser-suite output landed and the reading "
        f"still did not move ({during!r} -> {later!r})"
    )

    # And the converse, on the very same log: output stops, reading holds still.
    stopped, _m, rc = _poll(log, env)
    assert rc == 2, f"rc={rc}"
    assert stopped == later, (
        "nothing was appended, so the reading must be byte-identical: "
        f"{later!r} -> {stopped!r} - a reading that drifts on its own can never "
        "prove a build stopped"
    )


@requires_bash
def test_no_log_at_all_reports_absent_evidence_not_a_stall(tmp_path):
    """A log that does not exist is the absence of evidence.

    EMPTY is the honest answer - the same rule the count and scope fields follow.
    It must not be reported as a number a caller could compare and mistake for
    "unchanged, therefore stopped", and it must not resolve the build either way.
    """
    missing = tmp_path / "never-written.log"
    waited = _wait(missing, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") == "timeout", waited.stdout
    assert _field(waited, "BUILD_PROGRESS") == "", (
        "a log that does not exist has no progress to measure, so the field must be "
        f"EMPTY rather than a comparable figure\n{waited.stdout}"
    )
    assert _field(waited, "BUILD_MARKER") == "", waited.stdout


# ---------------------------------------------------------------------------
# The whole point, asserted directly: on the log the run actually produced, the
# two paths must never disagree.
# ---------------------------------------------------------------------------

DISAGREEMENT_MATRIX = [
    ("clean-pass", "17.0", [PROGRESS_LINE, LOADED_MARKER, PASSING_SUMMARY], 0),
    ("pass-with-unrelated-error", "17.0",
     [PROGRESS_LINE, LOADED_MARKER, UNRELATED_ERROR_LINE, PASSING_SUMMARY], 0),
    ("legacy-clean-pass", "12.0", [PROGRESS_LINE, LOADED_MARKER, LEGACY_RAN_MARKER], 0),
    ("per-test-failure", "17.0",
     [PROGRESS_LINE, LOADED_MARKER, *PER_TEST_FAILURE_LINES, AGG_PER_DATABASE_V14_PLUS], 1),
    ("aggregate-only-failure", "17.0", [PROGRESS_LINE, AGG_PER_DATABASE_V14_PLUS], 0),
    ("legacy-aggregate-only-failure", "12.0", [PROGRESS_LINE, AGG_PER_MODULE_V8_V13], 0),
    ("blanket-failure", "17.0", [PROGRESS_LINE, AGG_BLANKET_ALL_SERIES], 0),
    ("nonzero-exit-clean-log", "17.0", [PROGRESS_LINE, LOADED_MARKER, PASSING_SUMMARY], 1),
    ("hard-abort", "17.0", [PROGRESS_LINE, HARD_ABORTS["critical"]], 1),
    # Neither of these proves a pass, and neither is a failure - the two shapes
    # the real corpus holds for a run that finished having certified nothing.
    ("tag-filter-matched-nothing", "17.0",
     [PROGRESS_LINE, LOADED_MARKER, ZERO_TESTS_SUMMARY], 0),
    ("every-matched-test-skipped", "17.0",
     [PROGRESS_LINE, LOADED_MARKER, SKIPPED_TEST_LINE, SKIP_ONLY_SUMMARY], 0),
]


@requires_bash
@pytest.mark.parametrize("label,series,lines,exit_code", DISAGREEMENT_MATRIX)
def test_the_two_paths_never_disagree_on_the_log_the_run_produced(
        tmp_path, label, series, lines, exit_code):
    """One log, one outcome.

    `wait-log` reads the very log the `test` verb just finished writing - the
    verdict line included. `BUILD_RESULT=failure` and `TEST_RESULT=failed` must
    therefore hold together or not at all, for every shape of log a real run
    can produce.
    """
    res, log, env = _run_verb(tmp_path, "test", db=f"agree{label.replace('-', '')}",
                              version=series, lines=lines, exit_code=exit_code)
    verdict = _field(res, "TEST_RESULT")
    waited = _wait(log, env)
    build = _field(waited, "BUILD_RESULT")
    if verdict == "failed":
        assert build == "failure", (
            f"[{label}] the run reported TEST_RESULT=failed but the polling "
            f"verdict reported BUILD_RESULT={build}\nverb stdout:\n{res.stdout}"
            f"\nwait-log stdout:\n{waited.stdout}"
        )
    elif verdict == "passed":
        assert build == "success", (
            f"[{label}] the run reported TEST_RESULT=passed but the polling "
            f"verdict reported BUILD_RESULT={build}\nverb stdout:\n{res.stdout}"
            f"\nwait-log stdout:\n{waited.stdout}"
        )
    else:
        # Every remaining verdict is the run declining to certify a pass. The
        # polling verdict may neither overturn that into a failure nor - the
        # direction that actually shipped - launder it into a success.
        assert build not in ("failure", "success"), (
            f"[{label}] the run reported TEST_RESULT={verdict}, which certifies "
            f"neither a pass nor a failure, but the polling verdict reported "
            f"BUILD_RESULT={build}\nverb stdout:\n{res.stdout}"
            f"\nwait-log stdout:\n{waited.stdout}"
        )


# ---------------------------------------------------------------------------
# CONTRACT 5 - EVERY verdict the run can publish is mapped, deliberately
#
# `_parse_test_result` publishes the run's verdict on the log; `_scan_build_markers`
# reads it back and turns it into the `BUILD_RESULT=` a polling caller acts on.
# That hand-off has been rebuilt three times, and each rebuild handled the value
# that had just been caught and left the rest to a fallthrough:
#
#   * a bare unconditional success, so the run's own `failed` read as success;
#   * a branch for `failed` with success still the fallthrough, so the run's own
#     `inconclusive` read as success - measured on the real log corpus, where
#     four genuine test-verb runs (two whose tag filter matched zero tests, two
#     whose every matched test was skipped) were each relayed as a passing build.
#
# `inconclusive` is the value the run emits precisely BECAUSE it refuses to
# claim a pass without positive proof the suite ran. Relaying it as success is
# therefore the worst direction available: the refusal is overturned by the very
# mechanism meant to carry it.
#
# The guard below is STRUCTURAL, not another single-value patch. It reads the
# set of verdict values `_parse_test_result` can assign straight out of the
# script, reads the set `_scan_build_markers` explicitly enumerates, and demands
# they be equal - so a FOURTH value added to the emitter without an arm in the
# reader is a RED CI, not a silent fallthrough, no matter which value it is.
# ---------------------------------------------------------------------------

STEP55_TEXT = STEP55.read_text(encoding="utf-8")

# The floor the two extractors are checked against. It is not the source of the
# contract - the script is - but without it a regex that silently matches
# nothing would make every assertion below vacuously true, and this guard would
# join the class of defect it exists to catch. Kept here so a genuine change to
# the verdict vocabulary must touch this list AND the script, in one change.
KNOWN_VERDICT_VALUES = {"passed", "failed", "inconclusive"}


def _shell_function_body(name: str) -> str:
    """The body of a top-level shell function, by its `name() {` ... `}` frame."""
    lines = STEP55_TEXT.splitlines()
    opener = f"{name}() {{"
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == opener)
    except StopIteration:  # pragma: no cover - the floor assertions report it
        return ""
    try:
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    except StopIteration:  # pragma: no cover
        return ""
    return "\n".join(lines[start + 1:end])


def _verdict_values_emitted() -> set[str]:
    """Every value `_parse_test_result` can assign to the verdict it publishes."""
    body = _shell_function_body("_parse_test_result")
    return {
        m.group(1)
        for m in re.finditer(r"""verdict=["']([a-z][a-z0-9_-]*)["']""", body)
    }


def _verdict_values_mapped() -> set[str]:
    """Every value `_scan_build_markers` gives an explicit arm of its own.

    The wildcard arm is deliberately NOT collected: a fail-safe default is a
    backstop for a value nobody wired, never a substitute for wiring it.
    """
    body = _shell_function_body("_scan_build_markers")
    block = re.search(
        r'case\s+"\$\{verdict#TEST_RESULT=\}"\s+in(.*?)\besac\b', body, re.DOTALL
    )
    if not block:
        return set()
    return {
        arm
        for m in re.finditer(r"^\s*([A-Za-z0-9_|-]+)\)", block.group(1), re.MULTILINE)
        for arm in m.group(1).split("|")
    }


def test_the_extractors_still_see_the_verdict_vocabulary_they_are_checking():
    """Non-vacuity floor for the structural guard below.

    Both extractors read shell source with a regex. A refactor that computes the
    verdict indirectly, renames a function, or reshapes the `case` would leave
    them matching nothing - and an emptied set makes a set-equality assertion
    pass while checking nothing at all. Failing HERE says "the guard can no
    longer see the code", which is a different and more useful message than a
    guard that quietly stops guarding.
    """
    emitted = _verdict_values_emitted()
    assert emitted == KNOWN_VERDICT_VALUES, (
        "the set of verdict values the run can publish has changed - the guard's "
        "own floor must be updated in the SAME change that changes the script, so "
        "the hardcoded list can never drift away from what the script emits.\n"
        f"  script emits: {sorted(emitted)}\n"
        f"  floor:        {sorted(KNOWN_VERDICT_VALUES)}"
    )


def test_every_verdict_the_run_can_publish_is_explicitly_mapped_by_the_polling_scan():
    """No verdict value may reach the polling caller through a fallthrough.

    This is the defect, stated once and structurally: a value the run can
    publish, with no arm of its own in the scan that reads it back, inherits
    whatever the default arm happens to be. Three times that default was
    success. Adding a fourth verdict to the emitter must therefore fail CI until
    it is given a deliberate `BUILD_RESULT`, rather than silently inheriting one.
    """
    emitted = _verdict_values_emitted()
    mapped = _verdict_values_mapped()
    assert emitted <= mapped, (
        "a verdict the run publishes has NO explicit arm in the polling scan, so "
        "it falls through to the default instead of being given a deliberate "
        f"BUILD_RESULT: {sorted(emitted - mapped)}"
    )
    assert mapped <= emitted, (
        "the polling scan maps a verdict value the run can never publish - dead "
        f"code that hides which values are really covered: {sorted(mapped - emitted)}"
    )


@requires_bash
@pytest.mark.parametrize("value", sorted(KNOWN_VERDICT_VALUES))
def test_each_published_verdict_ends_the_wait_with_a_decided_result(tmp_path, value):
    """Every verdict is TERMINAL: the run computed it after odoo-bin exited.

    A verdict relayed as `timeout` tells the caller to wait again for a run that
    is already over - the idle-stall the blocking wait exists to remove, reached
    from the other side.
    """
    log = _stamped_log(tmp_path, f"verdict-{value}.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, f"TEST_RESULT={value}"])
    waited = _wait(log, _env(tmp_path))
    assert waited.returncode != 2, (
        f"TEST_RESULT={value} is the run's own FINAL verdict, so the wait must be "
        f"over\nstdout:\n{waited.stdout}"
    )
    assert _field(waited, "BUILD_RESULT") != "timeout", (
        f"TEST_RESULT={value} must not be reported as an unfinished build"
        f"\nstdout:\n{waited.stdout}"
    )
    assert f"TEST_RESULT={value}" in waited.stdout, (
        f"the wait must surface the verdict the log carries\n{waited.stdout}"
    )


@requires_bash
def test_an_inconclusive_run_is_reported_as_neither_a_pass_nor_an_unfinished_build(tmp_path):
    """`inconclusive` needs an outcome of its OWN - both neighbours are wrong.

    Reported as success, a caller concludes the module's tests passed when zero
    tests ran, which is the false green the verdict exists to prevent. Reported
    as `timeout`, the caller waits again on a run that has already ended and
    waits forever. So it is neither, and it carries its own exit status so a
    non-parsing caller can tell it apart from a pass as well.
    """
    log = _stamped_log(tmp_path, "verdict-inconclusive.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, "TEST_RESULT=inconclusive"])
    waited = _wait(log, _env(tmp_path))
    build = _field(waited, "BUILD_RESULT")
    assert build != "success", (
        "the run REFUSED to claim a pass without proof the suite ran, and the "
        "polling verdict claimed it on the run's behalf\nstdout:\n" + waited.stdout
    )
    assert build != "timeout", (
        "an inconclusive run has FINISHED - reporting it as unfinished makes a "
        "poller wait forever\nstdout:\n" + waited.stdout
    )
    assert waited.returncode not in (0, 2), (
        f"the exit status must separate an inconclusive run from a pass (0) and "
        f"from an unfinished one (2); got {waited.returncode}\n{waited.stdout}"
    )


@requires_bash
def test_an_unrecognized_future_verdict_fails_safe_rather_than_certifying_a_pass(tmp_path):
    """The runtime backstop behind the structural guard.

    If a verdict value ever reaches this scan unmapped - a partial deployment, a
    log written by a newer emitter - the answer must not be a green build. A
    loud wrong RED is recoverable; a silent GREEN on an unknown verdict is the
    exact failure this whole hand-off keeps reproducing.
    """
    log = _stamped_log(tmp_path, "verdict-unknown.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, "TEST_RESULT=some-future-value"])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") != "success", (
        "an unrecognized verdict was certified as a successful build\nstdout:\n"
        + waited.stdout
    )
    assert waited.returncode != 0, (
        f"an unrecognized verdict must not exit 0\nrc={waited.returncode}\n{waited.stdout}"
    )


@requires_bash
def test_a_skip_bearing_ran_marker_is_not_certified_green_before_the_verdict_lands(tmp_path):
    """The same hole, one branch upstream.

    Before the run appends its verdict line, the scan may certify success from
    the era-correct "the suite ran" marker. A skip-only run publishes exactly
    that marker with a non-zero total and no failure anywhere - so a wait landing
    in the window before the verdict line certifies a build the run is about to
    call `inconclusive`. Withholding certification costs nothing: the verdict
    line lands moments later and decides it.
    """
    log = _stamped_log(tmp_path, "skip-only-preverdict.log", verb="test", series="17.0",
                       lines=[PROGRESS_LINE, LOADED_MARKER, SKIPPED_TEST_LINE,
                              SKIP_ONLY_SUMMARY])
    waited = _wait(log, _env(tmp_path))
    assert _field(waited, "BUILD_RESULT") != "success", (
        "a run whose only tests were SKIPPED was certified a successful build "
        "before it published its own verdict\nstdout:\n" + waited.stdout
    )


@requires_bash
@pytest.mark.parametrize("label,series,lines", [
    # Measured on the real corpus: two runs whose tag filter matched zero tests,
    # two whose every matched test was skipped. Both shapes are genuine test-verb
    # runs that finished, and neither proves a pass.
    ("tag-filter-matched-nothing", "17.0", [ZERO_TESTS_SUMMARY]),
    ("every-matched-test-skipped", "17.0", [SKIPPED_TEST_LINE, SKIP_ONLY_SUMMARY]),
])
def test_a_run_that_proved_no_pass_reads_inconclusive_on_both_paths(
        tmp_path, label, series, lines):
    """End to end, on the log shapes the corpus actually holds.

    The `test` verb rules the run `inconclusive`, appends that to the log, and
    `wait-log` reads the same log back. The two answers must be the SAME fact in
    the two vocabularies - not one refusing to claim a pass while the other
    claims it.
    """
    res, log, env = _run_verb(tmp_path, "test", db=f"honest{label.replace('-', '')}",
                              version=series,
                              lines=[PROGRESS_LINE, LOADED_MARKER, *lines])
    assert _field(res, "TEST_RESULT") == "inconclusive", (
        f"[{label}] the run must refuse to claim a pass\nstdout:\n{res.stdout}"
    )
    waited = _wait(log, env)
    build = _field(waited, "BUILD_RESULT")
    assert build not in ("success", "timeout"), (
        f"[{label}] the run reported TEST_RESULT=inconclusive but the polling "
        f"verdict reported BUILD_RESULT={build}\nverb stdout:\n{res.stdout}"
        f"\nwait-log stdout:\n{waited.stdout}"
    )
    assert _field(waited, "BUILD_PROGRESS"), (
        f"[{label}] no progress reading on an inconclusive poll\n{waited.stdout}"
    )
