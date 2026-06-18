"""Behavior tests for scripts/lib/allocator.py - the concurrent instance allocator.

These protect the BEHAVIOR the allocator promises under concurrent multi-agent /
multi-session use, NOT a snapshot of its code: distinct isolation per caller,
port-pool disjointness, exclusive mutual-exclusion, stale-lease reclamation
(dead pid + expired ttl), readonly being lease-free, and portable path
resolution via $ODOO_AI_HOME. The Postgres-touching createdb/dropdb path is
covered by a separate test that SKIPS when no local Postgres is available, so
the core logic stays CPU-only and CI-green without a database.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOC = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"

INSTANCES_TOML = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons", "/srv/custom"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
python = "/srv/venv/bin/python"
"""

# An old profile with NONE of the new pool fields - must still allocate.
INSTANCES_TOML_LEGACY = """\
[[instance]]
series = "16.0"
http_port = 8069
db_name = "odoo_16_0"
db_host = "localhost"
db_user = "odoo"
"""


def _env(home: Path, toml: Path) -> dict:
    e = dict(os.environ)
    e["ODOO_AI_HOME"] = str(home)
    e["ODOO_AI_INSTANCES"] = str(toml)
    e["HOME"] = str(home)  # isolate any ~/.odoo-ai fallback
    return e


def _run(env, *args):
    return subprocess.run(
        [sys.executable, str(ALLOC), *args],
        capture_output=True, text=True, env=env,
    )


def _parse_alloc(stdout: str) -> dict:
    """Parse ALLOC_KEY=<shlex-quoted> lines into a dict; ALLOC_PORTS -> list[int]."""
    import shlex

    out = {}
    for line in stdout.splitlines():
        if "=" not in line or not line.startswith("ALLOC_"):
            continue
        key, _, raw = line.partition("=")
        vals = shlex.split(raw)
        val = vals[0] if vals else ""
        if key == "ALLOC_PORTS":
            out[key] = [int(p) for p in val.split()] if val else []
        else:
            out[key] = val
    return out


def _leases(env) -> list:
    p = _run(env, "list")
    return json.loads(p.stdout)["leases"]


@pytest.fixture
def fixt(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML, encoding="utf-8")
    return _env(home, toml), home, toml


def _acquire(env, *extra):
    p = _run(env, "acquire", "--series", "17.0", *extra)
    return p, _parse_alloc(p.stdout)


# --------------------------------------------------------------------------- #
# Isolation + ports
# --------------------------------------------------------------------------- #
def test_two_ephemeral_acquires_get_distinct_db_and_disjoint_ports(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "2")
    _, b = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "2")
    assert a["ALLOC_DB_NAME"] != b["ALLOC_DB_NAME"], "ephemeral DBs must be unique"
    assert a["ALLOC_DB_NAME"].startswith("odoo_17_0_t_")
    assert set(a["ALLOC_PORTS"]).isdisjoint(b["ALLOC_PORTS"]), "ports must not overlap"
    assert len(a["ALLOC_PORTS"]) == 2 and len(b["ALLOC_PORTS"]) == 2


def test_ports_come_from_the_declared_pool(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "1")
    assert 8170 <= a["ALLOC_PORTS"][0] < 8180, "port must be within http_port_base..+pool_size"


def test_zero_ports_leases_no_port(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert a["ALLOC_PORTS"] == [], "a --stop-after-init test needs a DB but no port"


# --------------------------------------------------------------------------- #
# Exclusive mutual exclusion
# --------------------------------------------------------------------------- #
def test_exclusive_lease_blocks_a_second_holder(fixt):
    env, _, _ = fixt
    p1, _ = _acquire(env, "--mode", "exclusive", "--db-name", "shared_db")
    assert p1.returncode == 0
    p2, _ = _acquire(env, "--mode", "exclusive", "--db-name", "shared_db")
    assert p2.returncode == 3, "second exclusive holder of the same DB must be rejected"


def test_release_frees_an_exclusive_lease(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "shared_db")
    assert _run(env, "release", a["ALLOC_TOKEN"]).returncode == 0
    p, _ = _acquire(env, "--mode", "exclusive", "--db-name", "shared_db")
    assert p.returncode == 0, "after release the DB can be re-acquired"


# --------------------------------------------------------------------------- #
# Stale reclamation
# --------------------------------------------------------------------------- #
def test_gc_reclaims_a_dead_pid_lease(fixt):
    env, _, _ = fixt
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()  # now dead.pid is a dead pid on this host
    _acquire(env, "--mode", "ephemeral", "--no-create", "--pid", str(dead.pid))
    assert len(_leases(env)) == 1
    _run(env, "gc")
    assert len(_leases(env)) == 0, "a lease owned by a dead pid (same host) must be reclaimed"


def test_gc_reclaims_an_expired_ttl_lease(fixt):
    env, _, _ = fixt
    _acquire(env, "--mode", "ephemeral", "--no-create", "--ttl", "-1")
    _run(env, "gc")
    assert len(_leases(env)) == 0, "a lease past its ttl must be reclaimed"


def test_gc_keeps_a_live_default_lease(fixt):
    env, _, _ = fixt
    # No --pid (so no premature pid-reclaim) and default ttl -> must survive gc.
    _acquire(env, "--mode", "ephemeral", "--no-create")
    _run(env, "gc")
    assert len(_leases(env)) == 1, "a fresh lease with no pid + default ttl must NOT be reclaimed"


# --------------------------------------------------------------------------- #
# readonly + portability + back-compat
# --------------------------------------------------------------------------- #
def test_readonly_is_lease_free(fixt):
    env, _, _ = fixt
    p, a = _acquire(env, "--mode", "readonly")
    assert p.returncode == 0
    assert a["ALLOC_TOKEN"] == "", "readonly must not mint a token"
    assert a["ALLOC_DB_NAME"] == "odoo_17_0", "readonly returns the declared DB"
    assert _leases(env) == [], "readonly must write NO lease"


def test_registry_lives_under_odoo_ai_home(fixt):
    env, home, _ = fixt
    _acquire(env, "--mode", "ephemeral", "--no-create")
    assert (home / "runtime" / "leases.json").is_file(), (
        "the lease registry must live under $ODOO_AI_HOME/runtime/"
    )


def test_legacy_instances_toml_without_pool_fields_still_allocates(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML_LEGACY, encoding="utf-8")
    env = _env(home, toml)
    p = _run(env, "acquire", "--series", "16.0", "--mode", "ephemeral", "--no-create", "--ports", "1")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    assert a["ALLOC_PORTS"] and a["ALLOC_PORTS"][0] >= 8069, (
        "with no http_port_base/port_pool_size, the pool derives from http_port"
    )


# --------------------------------------------------------------------------- #
# Concurrency: flock serialises the read-modify-write
# --------------------------------------------------------------------------- #
def test_parallel_acquires_never_duplicate_a_port(fixt):
    env, _, _ = fixt
    n = 8
    procs = [
        subprocess.Popen(
            [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
             "--mode", "ephemeral", "--no-create", "--ports", "1"],
            stdout=subprocess.PIPE, text=True, env=env,
        )
        for _ in range(n)
    ]
    ports = []
    for pr in procs:
        out, _ = pr.communicate()
        ports.extend(_parse_alloc(out).get("ALLOC_PORTS", []))
    assert len(ports) == n, f"every parallel acquire should yield a port; got {ports}"
    assert len(set(ports)) == n, f"flock must prevent duplicate ports; got {ports}"
    reg_ports = [p for lease in _leases(env) for p in lease["ports"]]
    assert len(reg_ports) == len(set(reg_ports)) == n, "registry must hold n unique ports"


# --------------------------------------------------------------------------- #
# Postgres lifecycle (skips without a local Postgres)
# --------------------------------------------------------------------------- #
def _pg_available() -> bool:
    from shutil import which

    if not (which("createdb") and which("dropdb") and which("psql")):
        return False
    env = dict(os.environ)
    pw = os.environ.get("ODOO_PG_PASSWORD")
    if pw:
        env["PGPASSWORD"] = pw
    r = subprocess.run(
        ["psql", "-h", "localhost", "-d", "postgres", "-tAc", "SELECT 1"],
        capture_output=True, text=True, env=env,
    )
    return r.returncode == 0


@pytest.mark.skipif(not _pg_available(), reason="no local Postgres (createdb/psql)")
def test_ephemeral_createdb_then_release_dropdb(fixt):
    env, _, _ = fixt
    p, a = _acquire(env, "--mode", "ephemeral", "--ports", "0")
    # Either it created an ephemeral DB, or it degraded to exclusive (no CREATEDB).
    assert p.returncode == 0
    if a["ALLOC_MODE"] == "ephemeral":
        db = a["ALLOC_DB_NAME"]
        chk = subprocess.run(
            ["psql", "-h", "localhost", "-d", "postgres", "-tAc",
             f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
            capture_output=True, text=True, env=env,
        )
        assert chk.stdout.strip() == "1", "ephemeral DB must exist after acquire"
        assert _run(env, "release", a["ALLOC_TOKEN"]).returncode == 0
        chk2 = subprocess.run(
            ["psql", "-h", "localhost", "-d", "postgres", "-tAc",
             f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
            capture_output=True, text=True, env=env,
        )
        assert chk2.stdout.strip() == "", "ephemeral DB must be dropped after release"


# --------------------------------------------------------------------------- #
# shared mode: the visual stack's live render target - non-exclusive, never
# drops the declared DB, cross-session discoverable, dead-server reclaimed.
# --------------------------------------------------------------------------- #
def _shared(env, *extra):
    p = _run(env, "acquire", "--series", "17.0", "--mode", "shared", *extra)
    return p, _parse_alloc(p.stdout)


def test_shared_acquire_records_actual_port_and_pid(fixt):
    env, _, _ = fixt
    p, a = _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    assert p.returncode == 0
    assert a["ALLOC_MODE"] == "shared"
    assert a["ALLOC_PORTS"] == [8069], "shared records the KNOWN port verbatim (not pooled)"
    assert a["ALLOC_ATTACHED"] == "0", "the first acquire mints, it does not attach"
    leases = _leases(env)
    assert len(leases) == 1
    lz = leases[0]
    assert lz["created_db"] is False, "a shared lease must NEVER own the declared DB"
    assert lz["ports"] == [8069]
    assert lz["owner"]["pid"] == os.getpid(), "the long-lived server pid is recorded"


def test_second_shared_acquire_attaches_not_duplicates(fixt):
    env, _, _ = fixt
    _, a = _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    p2, b = _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    assert p2.returncode == 0
    assert b["ALLOC_ATTACHED"] == "1", "a 2nd shared acquire ATTACHES to the live lease"
    assert b["ALLOC_TOKEN"] == a["ALLOC_TOKEN"], "attach returns the SAME lease token"
    assert b["ALLOC_PORTS"] == [8069]
    assert len(_leases(env)) == 1, "attach must NOT duplicate the lease row"


def test_shared_acquire_never_blocks_a_second_holder(fixt):
    env, _, _ = fixt
    p1, _ = _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    p2, _ = _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    assert p1.returncode == 0 and p2.returncode == 0, (
        "shared is non-exclusive: a 2nd holder is never rejected (unlike exclusive rc=3)"
    )


def test_gc_reclaims_dead_shared_server_but_never_drops_declared_db(fixt, tmp_path):
    env, _, _ = fixt
    # Stub the PG CLI so any DB-destroying call is RECORDED; then assert none fired.
    # If `shared` ever set created_db=True (or the gc guard regressed), gc would
    # dropdb the SHARED declared database here and this test would go red.
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    log = tmp_path / "pg_calls.log"
    for tool in ("dropdb", "psql", "createdb"):
        f = bindir / tool
        f.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{log}"\n', encoding="utf-8")
        f.chmod(0o755)
    env = dict(env)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()  # dead.pid is now a dead pid on this host
    _shared(env, "--port", "8069", "--db-name", "odoo_17_0", "--pid", str(dead.pid))
    leases = _leases(env)
    assert len(leases) == 1 and leases[0]["created_db"] is False

    _run(env, "gc")
    assert len(_leases(env)) == 0, "a dead-server shared row must be reclaimed (discovery self-heals)"
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "odoo_17_0" not in calls, "gc must NEVER dropdb the shared declared database"
    assert "dropdb" not in calls, "no dropdb may run for a created_db=False shared lease"


def test_query_returns_live_shared_lease_else_rc1(fixt):
    env, _, _ = fixt
    miss = _run(env, "query", "--series", "17.0")
    assert miss.returncode == 1, "query with no live shared server exits 1"
    assert _parse_alloc(miss.stdout) == {}, "query miss emits no ALLOC_* lines"

    _shared(env, "--port", "8069", "--pid", str(os.getpid()))
    hit = _run(env, "query", "--series", "17.0")
    a = _parse_alloc(hit.stdout)
    assert hit.returncode == 0
    assert a["ALLOC_PORTS"] == [8069], "query surfaces the actual bound port"
    assert a["ALLOC_DB_NAME"] == "odoo_17_0"


def test_shared_acquire_with_newer_pid_upserts_in_place(fixt):
    env, _, _ = fixt
    _, a = _shared(env, "--port", "8069")  # pre-launch: mint without the pid yet
    assert a["ALLOC_ATTACHED"] == "0"
    assert _leases(env)[0]["owner"]["pid"] is None, "a pre-launch lease carries no pid"
    _, b = _shared(env, "--port", "8069", "--pid", str(os.getpid()))  # post-up upsert
    assert b["ALLOC_ATTACHED"] == "1"
    assert b["ALLOC_TOKEN"] == a["ALLOC_TOKEN"]
    leases = _leases(env)
    assert len(leases) == 1, "the upsert must not create a second row"
    assert leases[0]["owner"]["pid"] == os.getpid(), "the real server pid is recorded in place"
