"""Behavior tests: the `lease_acquire` tool and the database name the caller chooses.

Driven over stdio against the REAL server and the REAL allocator (tests/odoo_local_mcp_harness.py),
with a stub venv python answering the allocator's `odoo_db.py exists|drop|preflight|can-createdb`
questions (test_allocator.py `_make_fake_venv_python`), so no Postgres is needed.

Contracts protected:
  - ephemeral + db_name leases a throwaway database of that name, and releasing the lease drops it.
  - a refused name reaches the agent as DB_NAME_REFUSED with the remedy of its reason.
  - exclusive + db_name on a database that does not exist yet is granted with ONE warning saying the
    build creates it and nothing drops it; no warning when it exists, when that cannot be told, or
    when the lease creates nothing.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_allocator import _make_fake_venv_python  # noqa: E402
from test_odoo_local_mcp_lease import (  # noqa: E402,F401  (`world` is a fixture)
    RUN, SERIES, _acquire, _err, _ok, errors, world,
)

NAME = "my_throwaway"
WARNING_KEY = "database_will_be_created"


@pytest.fixture
def stubbed(world, tmp_path):
    """A factory: stubbed(exists) -> (client, drop log); the catalog's python is the stub."""
    stack = contextlib.ExitStack()

    def make(exists):
        log = tmp_path / "odoo_db_argv.log"
        py = _make_fake_venv_python(tmp_path / "fakebin", log=log, exists=exists)
        toml = world["home"] / "instances.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace(
            'python = "%s"' % sys.executable, 'python = "%s"' % py), encoding="utf-8")
        client = stack.enter_context(McpClient(world["session"]().env, world["work"]))
        client.initialize()
        return client, log

    with stack:
        yield make


def _logged(log):
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _warnings(out):
    return [w for w in out["warnings"] if w.startswith(WARNING_KEY)]


def test_a_named_ephemeral_lease_is_dropped_at_release_and_raises_no_warning(stubbed, world):
    client, log = stubbed("false")
    out = _ok(_acquire(client, world, db_name=NAME, no_create=False))
    assert out["lease"]["db_name"] == NAME and out["lease"]["mode"] == "ephemeral"
    assert out["instance_handle"]["db_name"] == NAME
    assert _warnings(out) == []

    released = _ok(client.call("lease_release", {"lease_token": out["lease"]["token"], "run_id": RUN}))

    assert released["status"] == "released"
    assert "drop " + NAME in _logged(log), "the chosen database must be dropped through Odoo"


def test_an_ephemeral_name_of_an_existing_database_reaches_the_agent_with_its_own_remedy(
        stubbed, world):
    client, _log = stubbed("true")
    err = _err(_acquire(client, world, db_name=NAME, no_create=False))
    assert err["code"] == "DB_NAME_REFUSED"
    assert err["diagnostics"]["fields"]["reason"] == "database-exists"
    assert err["remedy"] == errors.TOOL_REMEDIES["DB_NAME_REFUSED"]["reasons"]["database-exists"]
    assert client.call("lease_list", {})["structuredContent"]["leases"] == []


def test_an_exclusive_lease_on_a_database_that_does_not_exist_yet_warns_once(stubbed, world):
    client, _log = stubbed("false")
    out = _ok(_acquire(client, world, mode="exclusive", db_name=NAME, no_create=False))
    assert out["lease"]["db_name"] == NAME
    assert len(_warnings(out)) == 1, out["warnings"]


@pytest.mark.parametrize("exists,extra", [
    ("true", {}),
    (None, {}),
    ("false", {"no_create": True}),
], ids=["the database exists", "existence unknown", "the lease creates nothing"])
def test_an_exclusive_lease_raises_no_warning_unless_the_named_database_is_provably_new(
        stubbed, world, exists, extra):
    client, _log = stubbed(exists)
    args = {"mode": "exclusive", "db_name": NAME, "no_create": False}
    args.update(extra)
    out = _ok(_acquire(client, world, **args))
    assert _warnings(out) == []


def test_the_db_name_property_describes_its_meaning_for_every_mode(stubbed):
    client, _log = stubbed("false")
    tools = client.request("tools/list")["result"]["tools"]
    tool = next(t for t in tools if t["name"] == "lease_acquire")
    text = tool["inputSchema"]["properties"]["db_name"]["description"]
    assert "ephemeral" in text and "exclusive" in text, "db_name must be explained per mode"
