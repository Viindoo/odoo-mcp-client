"""Behavior tests: `acquire --mode ephemeral --db-name X` names the caller's own throwaway database.

An ephemeral lease DROPS its database at release and gc, so a name the caller chose is granted only
when the database provably does not exist yet, no catalog row declares it, no lease holds it and it
is a valid name; every other case is refused with DB_NAME_REFUSED and NO lease is written. An
exclusive acquire on a named database that does not exist yet is still granted and says, through
ALLOC_DB_ABSENT, that the build creates it and nothing drops it.

The allocator runs as a subprocess against a temp ODOO_AI_HOME, a fake catalog and a stub venv
python that answers `odoo_db.py exists|drop|preflight|can-createdb` (test_allocator.py).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_db_name_validation import wide_range_locale  # noqa: E402
from test_allocator import (  # noqa: E402
    INSTANCES_TOML, _env_with_fake_venv, _import_allocator, _leases, _parse_alloc, _run,
)

LIB = TESTS_DIR.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
RUN = "run-name-owner"
NAME = "my_throwaway"

TWO_ROW_TOML = INSTANCES_TOML + """
[[instance]]
series = "16.0"
http_port = 8079
http_port_base = 8190
port_pool_size = 10
db_name = "odoo_16_0_durable"
db_name_prefix = "odoo_16_0"
db_host = "localhost"
db_user = "odoo"
python = "/srv/venv/bin/python"
"""


def _acquire_json(env, *extra):
    p = _run(env, "acquire", "--series", "17.0", "--run-id", RUN, *extra, "--format", "json",
             timeout=60)
    return p, json.loads(p.stdout)


def _acquire(env, *extra):
    p = _run(env, "acquire", "--series", "17.0", "--run-id", RUN, *extra, timeout=60)
    return p, _parse_alloc(p.stdout)


def _assert_refused(p, doc, env, reason, rows_before=0):
    assert p.returncode == 12, p.stderr
    assert doc["error"]["code"] == "DB_NAME_REFUSED", doc
    assert doc["fields"]["reason"] == reason, doc
    assert len(_leases(env)) == rows_before, "a refused acquire must write no lease"


def _logged(log):
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_an_ephemeral_acquire_honours_the_database_name_the_caller_chose(tmp_path):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="false")
    p, a = _acquire(env, "--mode", "ephemeral", "--db-name", NAME)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_DB_NAME"] == NAME
    (row,) = _leases(env)
    assert row["db_name"] == NAME and row["mode"] == "ephemeral"


def test_a_named_ephemeral_lease_is_an_ordinary_throwaway_that_is_dropped_at_release(tmp_path):
    env, log, _py = _env_with_fake_venv(tmp_path, exists="false")
    _p, a = _acquire(env, "--mode", "ephemeral", "--db-name", NAME)
    (row,) = _leases(env)
    assert row["drop_on_release"] is True

    rel = _run(env, "release", a["ALLOC_TOKEN"], "--run-id", RUN, timeout=60)

    assert rel.returncode == 0, rel.stderr
    assert "drop " + NAME in _logged(log), "release must drop the chosen database through Odoo"
    assert _leases(env) == []


def test_gc_drops_the_database_of_a_named_ephemeral_lease_whose_owner_is_gone(tmp_path):
    env, log, _py = _env_with_fake_venv(tmp_path, exists="false")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _acquire(env, "--mode", "ephemeral", "--db-name", NAME, "--pid", str(dead.pid))
    assert len(_leases(env)) == 1

    _run(env, "gc", timeout=60)

    assert "drop " + NAME in _logged(log), "gc must drop the chosen database through Odoo"
    assert _leases(env) == []


def test_an_ephemeral_acquire_without_a_name_still_mints_one(tmp_path):
    env, log, _py = _env_with_fake_venv(tmp_path, exists="true")
    p, a = _acquire(env, "--mode", "ephemeral")
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_DB_NAME"].startswith("odoo_17_0_t_")
    assert "exists" not in _logged(log), "a minted name needs no existence probe"


def test_an_ephemeral_name_that_already_exists_on_the_cluster_is_never_adopted(tmp_path):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="true")
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", NAME)
    _assert_refused(p, doc, env, "database-exists")


def test_an_ephemeral_name_whose_existence_cannot_be_determined_is_refused(tmp_path):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists=None)
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", NAME)
    _assert_refused(p, doc, env, "existence-undeterminable")


@pytest.mark.parametrize("declared", ["odoo_17_0", "odoo_16_0_durable"],
                         ids=["the acquiring row", "another row of the catalog"])
def test_an_ephemeral_name_that_any_catalog_row_declares_is_refused(tmp_path, declared):
    env, _log, _py = _env_with_fake_venv(tmp_path, TWO_ROW_TOML, exists="false")
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", declared)
    _assert_refused(p, doc, env, "catalog-database")


@pytest.mark.parametrize("held_by", [
    ("--mode", "exclusive", "--db-name", NAME),
    ("--mode", "ephemeral", "--db-name", NAME),
    ("--mode", "shared", "--db-name", NAME),
], ids=["an exclusive lease", "an ephemeral lease", "a shared lease"])
def test_an_ephemeral_name_that_a_lease_of_any_mode_holds_is_refused(tmp_path, held_by):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="false")
    first, _a = _acquire(env, *held_by)
    assert first.returncode == 0, first.stderr
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", NAME)
    _assert_refused(p, doc, env, "name-held", rows_before=1)
    assert [h["db_name"] for h in doc["fields"]["holders"]] == [NAME]


@pytest.mark.parametrize("bad", ["a", "-leading", ".leading", "_leading", "has space",
                                 "has/slash", "has;semicolon", "trailing\n"])
def test_an_ephemeral_name_that_is_not_a_valid_database_name_is_refused(tmp_path, bad):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="false")
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", bad)
    _assert_refused(p, doc, env, "name-invalid")


def test_a_named_ephemeral_acquire_that_creates_nothing_is_refused(tmp_path):
    env, log, _py = _env_with_fake_venv(tmp_path, exists="false")
    p, doc = _acquire_json(env, "--mode", "ephemeral", "--db-name", NAME, "--no-create")
    _assert_refused(p, doc, env, "no-create")
    assert "exists" not in _logged(log), "the refusal is decided before any probe"


def test_the_allocator_accepts_exactly_the_database_names_the_spinup_gate_accepts(tmp_path):
    """The name rule is spelled once in lib/state_reclaim.sh (`_DB_NAME_RE`, gated by
    `validate_db_name`) and mirrored once in allocator.py: the two must never drift."""
    alloc = _import_allocator()
    shell_re = None
    for line in (LIB / "state_reclaim.sh").read_text(encoding="utf-8").splitlines():
        if line.startswith("_DB_NAME_RE="):
            shell_re = line.split("=", 1)[1].strip().strip("'")
    assert shell_re == "^" + alloc.DB_NAME_RE + "$", "the two spellings of the rule differ"
    # The two must agree under every locale: the C locale, and one whose bracket ranges reach past
    # ASCII when the host has one.
    names = ["ab", "a", "", "-x", ".x", "_x", "x y", "x/y", "x;y", "ok_1.2-3", "A9", "9A",
             "x\n", "é1", "a*", "ab\nc"]
    for locale in filter(None, ("C", wide_range_locale())):
        for name in names:
            gate = subprocess.run(["bash", "-c", 'source "$1"; validate_db_name "$2"', "_",
                                   str(LIB / "state_reclaim.sh"), name],
                                  capture_output=True, text=True,
                                  env={"PATH": "/usr/bin:/bin", "LC_ALL": locale}).returncode == 0
            assert alloc._is_valid_db_name(name) is gate, "disagreement on %r under %s" % (name, locale)


def test_an_exclusive_acquire_on_a_named_database_that_does_not_exist_yet_is_granted_and_flagged(
        tmp_path):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="false")
    p, a = _acquire(env, "--mode", "exclusive", "--db-name", NAME)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_DB_NAME"] == NAME and a["ALLOC_DB_ABSENT"] == "1"
    (row,) = _leases(env)
    assert row["drop_on_release"] is False, "nothing may drop a database an exclusive lease holds"


@pytest.mark.parametrize("exists", ["true", None], ids=["it exists", "existence unknown"])
def test_an_exclusive_acquire_on_a_named_database_carries_no_flag_unless_it_is_provably_new(
        tmp_path, exists):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists=exists)
    p, a = _acquire(env, "--mode", "exclusive", "--db-name", NAME)
    assert p.returncode == 0, "an exclusive acquire is never refused over existence: " + p.stderr
    assert "ALLOC_DB_ABSENT" not in a


def test_an_exclusive_acquire_that_creates_nothing_runs_no_existence_probe(tmp_path):
    env, log, _py = _env_with_fake_venv(tmp_path, exists="false")
    p, a = _acquire(env, "--mode", "exclusive", "--db-name", NAME, "--no-create")
    assert p.returncode == 0, p.stderr
    assert "ALLOC_DB_ABSENT" not in a
    assert "exists" not in _logged(log)


def test_an_exclusive_acquire_of_the_declared_database_is_never_flagged(tmp_path):
    env, _log, _py = _env_with_fake_venv(tmp_path, exists="false")
    for extra in ((), ("--db-name", "odoo_17_0")):
        _p, a = _acquire(env, "--mode", "exclusive", *extra)
        assert "ALLOC_DB_ABSENT" not in a
        _run(env, "release", a["ALLOC_TOKEN"], "--run-id", RUN, timeout=60)
