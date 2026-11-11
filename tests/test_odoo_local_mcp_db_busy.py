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
    """Every build sleeps while the flag file exists (exports stay governed by the i18n fixture).
    Returns the flag: unlink it and builds are fast again."""
    flag = world["work"] / "builds-are-slow"
    text = world["behavior"].read_text()
    if "builds-are-slow" not in text:
        world["behavior"].write_text(text.replace(
            "for l in ${langs//,/ }; do",
            'if [[ -f "%s" ]]; then sleep 30; fi\nfor l in ${langs//,/ }; do' % flag, 1), encoding="utf-8")
    flag.write_text("1", encoding="utf-8")
    return flag


def _busy(err, blocking_job):
    assert err["code"] == "DATABASE_BUSY", err
    assert err["diagnostics"]["job_id"] == blocking_job
    assert "job_wait" in err["remedy"]


def _release(c, token):
    _ok(c.call("lease_release", {"lease_token": token, "run_id": RUN}, timeout=120))


def test_a_build_blocks_every_other_job_on_its_database_and_never_another_database(i18n):
    """On 19.0, where a test build refuses a demo database: the state of a database while a job
    runs on it is a moment of that job - e.g. no demo data yet - so a second build or an export
    must answer DATABASE_BUSY (wait, then retry) instead of reading that moment and refusing for
    what the first job has not loaded yet, which would send the agent to rebuild a database that
    is fine."""
    _declare_series(i18n, "19.0")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        provider = _ready_lease(c, i18n, series="19.0", ports=1)
        consumer = _lease(c, i18n, series="19.0", mode="exclusive", db_name=provider["db_name"], ports=1)
        other = _lease(c, i18n, series="19.0")
        _slow_builds(i18n)
        first = _ok(_build(c, i18n, provider["token"], op="update"))["job_id"]
        # the same lease, and another lease of the same database
        _busy(_err(_build(c, i18n, provider["token"], op="update")), first)
        _busy(_err(_build(c, i18n, consumer["token"], op="update")), first)
        _busy(_err(_export(c, i18n, consumer["token"])), first)
        # an export while the database holds no demo yet, a test build while it holds some
        i18n["db_facts"].write_text("DB_EXISTS=1\nDEMO=0\nLANGUAGES=en_US\n", encoding="utf-8")
        _busy(_err(_export(c, i18n, provider["token"])), first)
        i18n["db_facts"].write_text("DB_EXISTS=1\nDEMO=1\nLANGUAGES=en_US\n", encoding="utf-8")
        _busy(_err(_build(c, i18n, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod")),
              first)
        # another database is never blocked
        _ok(_build(c, i18n, other["token"], op="update"))
        for token in (other["token"], consumer["token"], provider["token"]):
            _release(c, token)


def test_an_export_blocks_a_build_and_neither_a_finished_nor_a_dead_job_blocks(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        i18n["slow"].write_text("1", encoding="utf-8")
        export = _ok(_export(c, i18n, lease["token"]))["job_id"]
        _busy(_err(_build(c, i18n, lease["token"], op="update")), export)
        _release(c, lease["token"])
        i18n["slow"].unlink()

        # A finished job never blocks.
        lease = _ready_lease(c, i18n)
        _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])
        _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])

        # A job whose process died without an exit record (its wrapper was killed) is not live.
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
