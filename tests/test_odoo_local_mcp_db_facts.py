"""Behavior tests: the odoo-local tools read demo and the active languages from the DATABASE
itself (`odoo_db.py db-facts`: ir_module_module.demo, res_lang.active) wherever they decide on
them - the TEST_DB_HAS_DEMO refusal, the instance_i18n_export gate, and every INSTANCE_HANDLE's
demo / languages_loaded - and fall back to the lease records (what builds recorded, from every
lease on that database) only when the database cannot be read. Each answer names its source
(facts_source: database | leases).

Driven over stdio against the real server, allocator and scripts in the stubbed world of
test_odoo_local_mcp_i18n_export.py, whose stub venv python answers `db-facts` from a file the test
writes (no file = the database cannot be read) and logs each read.

Contracts protected:
  - the database wins over the lease records in both directions (demo loaded that no lease
    recorded; a lease record the database contradicts);
  - a database that does not exist holds nothing;
  - an unreadable database falls back to the lease records, and says so;
  - the read is asked of the lease's own database and cluster, once per tool call;
  - instance_build hands back no handle at its start (the database is what it is about to
    change): job_wait's handle states the facts after the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_odoo_local_mcp_i18n_export import _export, _export_calls, _ready_lease, _record_build, i18n  # noqa: E402,F401
from test_odoo_local_mcp_instance import (RUN, SERIES, _build, _declare_series, _err, _lease,  # noqa: E402,F401
                                          _ok, _wait, client, world)


def _db(world, demo=None, languages=None, exists=True):
    """Make the stub database answer db-facts; demo=None removes the answer (unreadable)."""
    if demo is None and exists:
        world["db_facts"].unlink(missing_ok=True)
        return
    text = "DB_EXISTS=0\n" if not exists else "DB_EXISTS=1\nDEMO=%d\nLANGUAGES=%s\n" % (
        1 if demo else 0, ",".join(languages or []))
    world["db_facts"].write_text(text, encoding="utf-8")


def _reads(world):
    return world["db_calls"].read_text().splitlines() if world["db_calls"].exists() else []


def _acquire(c, world, **over):
    args = {"series": SERIES, "run_id": RUN, "cwd": str(world["work"]), "no_create": True}
    args.update(over)
    return _ok(c.call("lease_acquire", args))


def test_the_handle_states_what_the_database_holds_over_what_leases_recorded(i18n):
    # The database states what no build recorded, and the lease's own database is the one asked.
    _db(i18n, demo=True, languages=["en_US", "fr_BE"])
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        out = _acquire(c, i18n)
        handle = out["instance_handle"]
        assert (handle["demo"], handle["languages_loaded"], handle["facts_source"]) == (
            True, ["en_US", "fr_BE"], "database")
        (read,) = _reads(i18n)
        words = read.split()
        assert words[1:3] == ["db-facts", out["lease"]["db_name"]], "the lease's own database is asked"
        assert words[words.index("--db-host") + 1] == "localhost"
        assert words[words.index("--db-user") + 1] == "odoo"
        assert words[words.index("--odoo-root") + 1] == str(i18n["odoo_bin"].parent)

        # job_wait hands back the database facts after the build (the database is what the build
        # changed); the lease records (demo on, en_US + vi_VN) lose to the database in both
        # directions; an unreadable database falls back to the lease records and says so; a
        # database that does not exist holds nothing.
        lease = _ready_lease(c, i18n, languages=("vi_VN",))
        for facts, expected in (
                (dict(demo=False, languages=["en_US"]), (False, ["en_US"], "database")),
                (dict(), (True, ["en_US", "vi_VN"], "leases")),
                (dict(exists=False), (False, None, "database"))):
            _db(i18n, **facts)
            handle = _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])["instance_handle"]
            assert (handle["demo"], handle["languages_loaded"], handle["facts_source"]) == expected, facts

        fresh = _lease(c, i18n)
        job = _ok(_build(c, i18n, fresh["token"], demo="off"))
        _db(i18n, demo=True, languages=["en_US"])
        done = _wait(c, job["job_id"])
        assert done["instance_handle"]["demo"] is True and done["instance_handle"]["facts_source"] == "database"


def test_a_test_build_follows_the_database_over_the_lease_records(i18n):
    _declare_series(i18n, "19.0")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        # The database holds demo no lease recorded: refused, one database read per tool call.
        _db(i18n, demo=True, languages=["en_US"])
        lease = _lease(c, i18n, series="19.0", ports=1)
        before = len(_reads(i18n))
        err = _err(_build(c, i18n, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
        assert len(_reads(i18n)) == before + 1, "one database read per tool call"
        assert err["code"] == "TEST_DB_HAS_DEMO"
        assert err["diagnostics"]["facts_source"] == "database"

        # The database holds no demo whatever a lease recorded: it runs.
        _record_build(i18n, lease["token"], "--demo", "on")
        _db(i18n, demo=False, languages=["en_US"])
        _ok(_build(c, i18n, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod"))

        # An unreadable database still refuses on the lease records.
        other = _lease(c, i18n, series="19.0", ports=1)
        _record_build(i18n, other["token"], "--demo", "on")
        _db(i18n)
        err = _err(_build(c, i18n, other["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
        assert err["code"] == "TEST_DB_HAS_DEMO" and err["diagnostics"]["facts_source"] == "leases"


def test_the_export_gate_follows_the_database_over_the_lease_records(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)  # the lease records say: fit for the export
        for demo, languages, code, missing in (
                (False, ["en_US", "vi_VN", "fr_BE"], "I18N_EXPORT_NEEDS_DEMO", None),
                (True, ["en_US", "vi_VN"], "I18N_LANGUAGE_NOT_LOADED", ["fr_BE"])):
            _db(i18n, demo=demo, languages=languages)
            err = _err(_export(c, i18n, lease["token"]))
            assert err["code"] == code and err["diagnostics"]["facts_source"] == "database"
            if missing:
                assert err["diagnostics"]["missing"] == missing
        assert _export_calls(i18n) == []

        # A database fit for the export exports though no build recorded it.
        fresh = _lease(c, i18n)
        _db(i18n, demo=True, languages=["en_US", "vi_VN", "fr_BE"])
        done = _wait(c, _ok(_export(c, i18n, fresh["token"]))["job_id"])
        assert done["result"] == "success", done
        assert [e["kind"] for e in done["exports"]] == ["pot", "po", "po"]
