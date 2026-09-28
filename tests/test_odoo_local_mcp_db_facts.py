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

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_odoo_local_mcp_i18n_export import _export, _export_calls, _ready_lease, i18n  # noqa: E402,F401
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


# --------------------------------------------------------------------------- #
# the handle
# --------------------------------------------------------------------------- #
def test_the_handle_states_what_the_database_holds_though_no_build_recorded_it(i18n):
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


def test_the_database_overrules_what_a_lease_recorded(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)  # lease records: demo on, en_US + vi_VN + fr_BE
        _db(i18n, demo=False, languages=["en_US"])
        done = _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])
    handle = done["instance_handle"]
    assert (handle["demo"], handle["languages_loaded"], handle["facts_source"]) == (
        False, ["en_US"], "database")


def test_an_unreadable_database_falls_back_to_the_lease_records_and_says_so(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, languages=("vi_VN",))
        done = _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])
    handle = done["instance_handle"]
    assert (handle["demo"], handle["languages_loaded"], handle["facts_source"]) == (
        True, ["en_US", "vi_VN"], "leases")


def test_a_database_that_does_not_exist_holds_nothing(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _db(i18n, exists=False)
        done = _wait(c, _ok(_build(c, i18n, lease["token"], op="update"))["job_id"])
    handle = done["instance_handle"]
    assert (handle["demo"], handle["languages_loaded"], handle["facts_source"]) == (
        False, None, "database")


def test_job_wait_hands_back_the_database_facts_after_the_build(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n)
        job = _ok(_build(c, i18n, lease["token"], demo="off"))
        _db(i18n, demo=True, languages=["en_US"])
        done = _wait(c, job["job_id"])
    assert done["instance_handle"]["demo"] is True and done["instance_handle"]["facts_source"] == "database"


# --------------------------------------------------------------------------- #
# the test-build refusal
# --------------------------------------------------------------------------- #
def test_a_test_build_is_refused_on_a_database_holding_demo_no_lease_recorded(i18n):
    _declare_series(i18n, "19.0")
    _db(i18n, demo=True, languages=["en_US"])
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n, series="19.0", ports=1)
        before = len(_reads(i18n))
        err = _err(_build(c, i18n, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
        assert len(_reads(i18n)) == before + 1, "one database read per tool call"
    assert err["code"] == "TEST_DB_HAS_DEMO"
    assert err["diagnostics"]["facts_source"] == "database"


def test_a_test_build_runs_where_the_database_holds_no_demo_whatever_a_lease_recorded(i18n):
    _declare_series(i18n, "19.0")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n, series="19.0", ports=1)
        _wait(c, _ok(_build(c, i18n, lease["token"], demo="on"))["job_id"])
        _db(i18n, demo=False, languages=["en_US"])
        _ok(_build(c, i18n, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod"))


def test_an_unreadable_database_still_refuses_on_the_lease_records(i18n):
    _declare_series(i18n, "19.0")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n, series="19.0", ports=1)
        _wait(c, _ok(_build(c, i18n, lease["token"], demo="on"))["job_id"])
        err = _err(_build(c, i18n, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
    assert err["code"] == "TEST_DB_HAS_DEMO" and err["diagnostics"]["facts_source"] == "leases"


# --------------------------------------------------------------------------- #
# the export gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("demo,languages,code,missing", [
    (False, ["en_US", "vi_VN", "fr_BE"], "I18N_EXPORT_NEEDS_DEMO", None),
    (True, ["en_US", "vi_VN"], "I18N_LANGUAGE_NOT_LOADED", ["fr_BE"]),
])
def test_the_export_gate_follows_the_database_over_the_lease_records(i18n, demo, languages, code,
                                                                     missing):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)  # the lease records say: fit for the export
        _db(i18n, demo=demo, languages=languages)
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == code and err["diagnostics"]["facts_source"] == "database"
    if missing:
        assert err["diagnostics"]["missing"] == missing
    assert _export_calls(i18n) == []


def test_a_database_fit_for_the_export_exports_though_no_build_recorded_it(i18n):
    _db(i18n, demo=True, languages=["en_US", "vi_VN", "fr_BE"])
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    assert done["result"] == "success", done
    assert [e["kind"] for e in done["exports"]] == ["pot", "po", "po"]
