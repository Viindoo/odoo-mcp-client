"""Behavior tests: one Odoo job at a time per DATABASE.

Two jobs that write one database at once - two instance_build updates, or a build and an
instance_i18n_export, started by parallel agents on one lease or on two leases of the same
database - race each other inside Odoo (module state, registry, translations). The tools refuse to
start a build or export job while another LIVE job targets the same database (DATABASE_BUSY,
naming the blocking job_id), and a finished or dead job never blocks.

Driven over stdio against the real server, allocator and scripts in the stubbed world of
test_odoo_local_mcp_i18n_export.py (odoo-bin is a stub; a flag file makes a build or an export
slow, so a second start lands while the first job is live).
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_odoo_local_mcp_i18n_export import _export, _ready_lease, i18n  # noqa: E402,F401
from test_odoo_local_mcp_instance import (RUN, SERIES, _build, _declare_series, _err, _lease,  # noqa: E402,F401
                                          _ok, _wait, client, world)


def _slow_builds(world):
    """Every build sleeps before it finishes (exports stay governed by the i18n fixture)."""
    text = world["behavior"].read_text()
    world["behavior"].write_text(text.replace("for l in ${langs//,/ }; do",
                                              "sleep 30\nfor l in ${langs//,/ }; do", 1),
                                 encoding="utf-8")


def _busy(err, blocking_job):
    assert err["code"] == "DATABASE_BUSY", err
    assert err["diagnostics"]["job_id"] == blocking_job
    assert "job_wait" in err["remedy"]


def _release(c, token):
    _ok(c.call("lease_release", {"lease_token": token, "run_id": RUN}, timeout=120))


def test_a_second_build_on_the_same_lease_waits_for_the_first(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _slow_builds(i18n)
        first = _ok(_build(c, i18n, lease["token"], op="update"))["job_id"]
        err = _err(_build(c, i18n, lease["token"], op="update"))
        _busy(err, first)
        _release(c, lease["token"])


def test_a_build_on_another_lease_of_the_same_database_is_refused_while_one_runs(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        provider = _ready_lease(c, i18n)
        consumer = _lease(c, i18n, mode="exclusive", db_name=provider["db_name"])
        _slow_builds(i18n)
        first = _ok(_build(c, i18n, provider["token"], op="update"))["job_id"]
        _busy(_err(_build(c, i18n, consumer["token"], op="update")), first)
        _busy(_err(_export(c, i18n, consumer["token"])), first)
        _release(c, consumer["token"])
        _release(c, provider["token"])


def test_a_build_is_refused_while_an_export_runs_on_the_database(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        i18n["slow"].write_text("1", encoding="utf-8")
        export = _ok(_export(c, i18n, lease["token"]))["job_id"]
        _busy(_err(_build(c, i18n, lease["token"], op="update")), export)
        _release(c, lease["token"])


def test_an_export_during_a_build_is_busy_not_refused_for_what_the_build_has_not_loaded_yet(i18n):
    """While a build runs, the database holds a moment of that build - e.g. no demo data yet. The
    export must answer DATABASE_BUSY (wait, then retry) instead of reading that moment and
    refusing I18N_EXPORT_NEEDS_DEMO, which would send the agent to rebuild a database that is
    fine."""
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _slow_builds(i18n)
        build = _ok(_build(c, i18n, lease["token"], op="update"))["job_id"]
        i18n["db_facts"].write_text("DB_EXISTS=1\nDEMO=0\nLANGUAGES=en_US\n", encoding="utf-8")
        _busy(_err(_export(c, i18n, lease["token"])), build)
        _release(c, lease["token"])


def test_a_test_build_during_another_build_is_busy_not_refused_for_demo(i18n):
    """Where demo is opt-in a test build refuses a demo database (TEST_DB_HAS_DEMO) - but while
    another job runs on it, the database is not in its final state, and the answer is BUSY."""
    _declare_series(i18n, "19.0")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n, series="19.0", ports=1)
        _slow_builds(i18n)
        build = _ok(_build(c, i18n, lease["token"], demo="off"))["job_id"]
        i18n["db_facts"].write_text("DB_EXISTS=1\nDEMO=1\nLANGUAGES=en_US\n", encoding="utf-8")
        _busy(_err(_build(c, i18n, lease["token"], op="test", test_mode="reuse",
                          test_tags="/my_mod")), build)
        _release(c, lease["token"])


def test_another_database_is_never_blocked(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        a = _ready_lease(c, i18n)
        b = _lease(c, i18n)
        _slow_builds(i18n)
        _ok(_build(c, i18n, a["token"], op="update"))
        _ok(_build(c, i18n, b["token"], op="update"))
        _release(c, a["token"])
        _release(c, b["token"])


def test_a_finished_job_never_blocks(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])
        _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])


def test_a_dead_job_never_blocks(i18n):
    """A job whose process died without an exit record (its wrapper was killed) is not live."""
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _slow_builds(i18n)
        job = _ok(_build(c, i18n, lease["token"], op="update"))
        os.killpg(job["pid"], signal.SIGKILL)
        deadline = time.monotonic() + 20
        while _wait(c, job["job_id"], timeout_s=1)["state"] == "running":
            assert time.monotonic() < deadline, "the killed job never stopped"
        _ok(_build(c, i18n, lease["token"], op="update"))
        _release(c, lease["token"])


def test_two_servers_starting_at_once_on_one_database_start_exactly_one_job(i18n):
    """Two odoo-local servers (two sessions) start a build on two leases of one database at the
    same moment: the start is serialized machine-wide, so exactly one job starts and the other call
    is refused naming it - never two jobs because both looked before either started."""
    import threading
    with McpClient(i18n["env"](), i18n["work"]) as c1, McpClient(i18n["env"](), i18n["work"]) as c2:
        c1.initialize()
        c2.initialize()
        provider = _ready_lease(c1, i18n)
        consumer = _lease(c2, i18n, mode="exclusive", db_name=provider["db_name"])
        _slow_builds(i18n)
        results = {}
        barrier = threading.Barrier(2)

        def start(name, c, token):
            barrier.wait()
            results[name] = c.call("instance_build", {"lease_token": token, "op": "update",
                                                      "modules": ["my_mod"], "cwd": str(i18n["work"])},
                                   timeout=120)

        threads = [threading.Thread(target=start, args=("a", c1, provider["token"])),
                   threading.Thread(target=start, args=("b", c2, consumer["token"]))]
        for th in threads:
            th.start()
        for th in threads:
            th.join(150)
        ok = [r for r in results.values() if not r["isError"]]
        refused = [r for r in results.values() if r["isError"]]
        assert len(ok) == 1 and len(refused) == 1, results
        _busy(refused[0]["structuredContent"]["error"], ok[0]["structuredContent"]["job_id"])
        _release(c2, consumer["token"])
        _release(c1, provider["token"])
