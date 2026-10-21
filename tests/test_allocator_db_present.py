"""Behavior tests: `_db_present` never reads "could not look" as "the database is absent".

`_db_present` is the probe release, resume and the parked-lease query use to decide a
database is PROVABLY gone: a False removes the filestore and frees the lease. Its first
route runs `odoo_db.py exists` under the lease's own interpreter, and Odoo's own existence
APIs answer False for any failed connection - so an unreachable cluster or a refused login
used to come back as "absent". The allocator must see an unknown answer as None.

The route is driven for real: the REAL odoo_db.py, run by the current interpreter against
a fake Odoo package whose connection layer fails (the builders live in test_odoo_db_lib.py).
No PostgreSQL, no real Odoo, no psql on PATH.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_odoo_db_lib import _build_fake_odoo  # noqa: E402

LIB = TESTS_DIR.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib"


@pytest.fixture
def alloc():
    sys.path.insert(0, str(LIB))
    try:
        spec = importlib.util.spec_from_file_location("allocator_db_present_under_test",
                                                      LIB / "allocator.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path.remove(str(LIB))


def _lease(pkg):
    """A lease whose drop surface is complete, so no catalog is consulted. `db_run_mode`
    names no client surface, so the psql fallback offers no route either."""
    return {"db_name": "odoo_t_deadbeef", "db_host": "h", "db_user": "nosuchrole",
            "python": sys.executable, "odoo_root": str(pkg), "db_run_mode": "none",
            "db_container": "x"}


@pytest.mark.parametrize("layout", ["legacy", "modern"])
@pytest.mark.parametrize("message", [
    "could not connect to server: Connection refused",
    "FATAL: password authentication failed for user",
])
def test_an_unreachable_or_refusing_cluster_is_unknown_not_absent(
        alloc, tmp_path, layout, message):
    pkg = _build_fake_odoo(tmp_path, layout=layout, exp_db_exist_returns=False,
                           exist_returns=False, connect_error=message)
    assert alloc._db_present(_lease(pkg)) is None


@pytest.mark.parametrize("layout", ["legacy", "modern"])
def test_a_database_absent_from_the_catalog_is_provably_absent(alloc, tmp_path, layout):
    pkg = _build_fake_odoo(tmp_path, layout=layout, exp_db_exist_returns=False,
                           exist_returns=False, in_catalog=False)
    assert alloc._db_present(_lease(pkg)) is False


@pytest.mark.parametrize("layout", ["legacy", "modern"])
def test_a_database_that_refuses_connections_is_still_present(alloc, tmp_path, layout):
    pkg = _build_fake_odoo(tmp_path, layout=layout, exp_db_exist_returns=False,
                           exist_returns=False, in_catalog=True)
    assert alloc._db_present(_lease(pkg)) is True
