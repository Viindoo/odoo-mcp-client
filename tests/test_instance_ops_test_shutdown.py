"""A `test` run whose odoo-bin lingers after Odoo's shutdown line is ended and judged from the log."""

import os
import textwrap
import time
from pathlib import Path

import pytest

from test_instance_ops_script import (
    _base_env, _make_fake_odoo_bin, _make_fake_python, _run, requires_bash,
)

SHUTDOWN = "2026-01-01 00:00:01,000 1 INFO testdb odoo.service.server: Initiating shutdown"


def _summary(failed: int) -> str:
    return (
        "2026-01-01 00:00:00,000 1 INFO testdb odoo.tests.result: "
        f"{failed} failed, 0 error(s) of 3 tests when loading database 'testdb'"
    )


def _run_test_verb(tmp_path: Path, tail: str, failed: int, grace: str = "1"):
    pidfile = tmp_path / "odoo.pid"
    out = textwrap.dedent(f"""\
        echo $$ > "{pidfile}"
        echo "{_summary(failed)}"
        echo "{SHUTDOWN}"
        {tail}
    """)
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=out)
    # `exit 0` appended by the helper is unreachable after exec
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    addons = tmp_path / "addons"
    addons.mkdir()
    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    env["ODOO_AI_TEST_SHUTDOWN_GRACE"] = grace
    started = time.monotonic()
    res = _run("test", "--db", "testdb", "--python", str(fake_py), "--addons", str(addons),
               "--modules", "sale", env=env, timeout=25)
    return res, time.monotonic() - started, pidfile


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _log_text(res) -> str:
    path = next(l.split("=", 1)[1] for l in res.stdout.splitlines() if l.startswith("LOG_PATH="))
    return Path(path).read_text(encoding="utf-8")


@requires_bash
def test_a_hung_exit_after_the_shutdown_line_never_hides_a_failed_test(tmp_path):
    res, took, pidfile = _run_test_verb(tmp_path, "exec sleep 600", failed=1)
    assert took < 15
    assert "TEST_RESULT=failed" in res.stdout, res.stdout
    assert "allocator: FORCED_EXIT_AFTER_SHUTDOWN" in _log_text(res)
    assert not _alive(int(pidfile.read_text()))


@requires_bash
def test_the_shutdown_line_is_found_when_much_more_log_follows_it_and_a_passing_run_stays_passed(tmp_path):
    flood = 'yes "INFO testdb werkzeug: GET /websocket HTTP/1.1 101" | head -n 60000; exec sleep 600'
    res, took, pidfile = _run_test_verb(tmp_path, flood, failed=0)
    assert took < 15
    assert "TEST_RESULT=passed" in res.stdout, res.stdout
    assert "allocator: FORCED_EXIT_AFTER_SHUTDOWN grace=1s" in _log_text(res)
    assert not _alive(int(pidfile.read_text()))


@requires_bash
def test_a_process_that_exits_by_itself_after_the_shutdown_line_is_not_forced(tmp_path):
    res, took, _ = _run_test_verb(tmp_path, "exit 0", failed=0, grace="60")
    assert took < 10
    assert "TEST_RESULT=passed" in res.stdout, res.stdout
    assert "FORCED_EXIT_AFTER_SHUTDOWN" not in _log_text(res)
