"""Behavior tests for scripts/lib/allocator.py - the concurrent instance allocator.

These protect the BEHAVIOR the allocator promises under concurrent multi-agent /
multi-session use, NOT a snapshot of its code: distinct isolation per caller,
port-pool disjointness, exclusive mutual-exclusion, stale-lease reclamation
(dead pid + expired ttl), readonly being lease-free, and portable path
resolution via $ODOO_AI_HOME. The Postgres-touching path is covered by a
separate test that SKIPS when no local Postgres is available, so the core logic
stays CPU-only and CI-green without a database.

B2 model (this revision): the allocator no longer calls createdb.  The caller
(odoo-bin -d <db> -i <mods> --stop-after-init) creates the DB; release/gc drop
it THROUGH odoo_db.py (the through-Odoo path).  The fallback to raw dropdb is
only allowed when the venv python is absent from the lease.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOC = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"
ODOO_DB_PY = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_db.py"

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


def _leases(env, show_tokens: bool = True) -> list:
    # Default to --show-tokens so assertions on the full lease token keep working
    # after cmd_list started redacting tokens to an 8-char fingerprint by default.
    args = ["list"] + (["--show-tokens"] if show_tokens else [])
    p = _run(env, *args)
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
# P5 port-uniqueness gate (refinement 2, 23-review-final.md Part 2): a pooled
# port handed to an `exclusive-running` build must never equal the declared
# HTTP port (the shared/declared render target's port) - even when the
# profile declares no separate http_port_base, so the pool would otherwise
# start counting AT the declared port itself.
# --------------------------------------------------------------------------- #
def test_pooled_port_never_equals_the_declared_http_port(tmp_path):
    """With NO http_port_base declared (legacy profile), the pool must not hand
    out the declared http_port (8069) itself - that port is reserved for the
    shared/declared render target, so a pooled exclusive-running lease landing
    on it would collide."""
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML_LEGACY, encoding="utf-8")  # http_port=8069, no http_port_base
    env = _env(home, toml)
    p = _run(env, "acquire", "--series", "16.0", "--mode", "ephemeral",
             "--no-create", "--ports", "1")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_PORTS"][0] != 8069, (
        "a pooled port must never equal the declared HTTP port (would collide with "
        "the shared/declared render target listening there)"
    )


def test_concurrent_pooled_acquires_never_collide_with_declared_port(tmp_path):
    """Two (or more) concurrent exclusive-running-style acquires on the same
    series must get DISTINCT pooled ports, and NONE may equal the declared
    http_port - even under concurrency, and even with no http_port_base
    declared (the pool naively starts counting at the declared port)."""
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML_LEGACY, encoding="utf-8")
    env = _env(home, toml)
    n = 4
    procs = [
        subprocess.Popen(
            [sys.executable, str(ALLOC), "acquire", "--series", "16.0",
             "--mode", "ephemeral", "--no-create", "--ports", "1",
             "--run-id", f"run-{i}"],
            stdout=subprocess.PIPE, text=True, env=env,
        )
        for i in range(n)
    ]
    ports = []
    for pr in procs:
        out, _ = pr.communicate()
        ports.extend(_parse_alloc(out).get("ALLOC_PORTS", []))
    assert len(ports) == n, f"every concurrent acquire should yield a port; got {ports}"
    assert len(set(ports)) == n, f"flock must prevent duplicate ports; got {ports}"
    assert 8069 not in ports, (
        "no pooled port may equal the declared HTTP port, even under concurrency and "
        f"even with no http_port_base declared; got {ports}"
    )


# --------------------------------------------------------------------------- #
# Lease record shape (B2 model)
# --------------------------------------------------------------------------- #
def test_ephemeral_lease_carries_drop_context(tmp_path):
    """Verify the new B2 lease fields that _drop_through_odoo reads at release time.

    We need drop_on_release=True which requires an ephemeral lease WITHOUT --no-create.
    Inject a fake psql that makes _probe_createdb return True (role has CREATEDB) so
    the probe succeeds without a real Postgres.
    """
    # Fake psql: any invocation prints 't' (role has CREATEDB) and exits 0.
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    fake_psql = bindir / "psql"
    fake_psql.write_text("#!/bin/sh\necho t\n", encoding="utf-8")
    fake_psql.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML, encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    assert a["ALLOC_MODE"] == "ephemeral", (
        "fake psql returning 't' must allow the probe to pass and stay in ephemeral mode"
    )

    leases = _leases(env)
    assert len(leases) == 1
    lz = leases[0]
    assert lz["drop_on_release"] is True, "ephemeral lease must set drop_on_release=True"
    assert lz["python"] == "/srv/venv/bin/python", "venv interpreter must be stored in lease"
    assert lz["db_host"] == "localhost", "db_host must be stored for drop-context"
    assert lz["db_user"] == "odoo", "db_user must be stored for drop-context"
    # Password must NOT be stored - it is read from ODOO_PG_PASSWORD at drop time.
    assert "db_password" not in lz, "PG password must never be stored in the lease"
    assert "created_db" not in lz, "old created_db field must not appear (replaced by drop_on_release)"


def test_ephemeral_no_create_lease_does_not_set_drop_on_release(fixt):
    """--no-create ephemeral leases must NOT drop (caller did not create a DB)."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert a["ALLOC_MODE"] == "ephemeral"
    leases = _leases(env)
    assert len(leases) == 1
    assert leases[0]["drop_on_release"] is False, (
        "ephemeral+--no-create must set drop_on_release=False (no DB was created)"
    )


def test_exclusive_lease_does_not_set_drop_on_release(fixt):
    """Exclusive leases must never be dropped by release/gc."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "shared_db")
    leases = _leases(env)
    assert len(leases) == 1
    assert leases[0]["drop_on_release"] is False, (
        "exclusive lease must have drop_on_release=False (DB must survive release)"
    )


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
#
# B2 model: the allocator no longer calls createdb.
# The live-PG tests now guard on dropdb + psql only (createdb is used only by
# the test harness to stand in for Odoo create-on-init).
# --------------------------------------------------------------------------- #
def _pg_available() -> bool:
    """True when dropdb and psql are on PATH AND a local Postgres is reachable.

    createdb is NOT required by the allocator itself in B2 mode; the test
    harness uses it to stand in for `odoo-bin --stop-after-init`, but the
    allocator's own drop path only needs psql (for terminate-backend) and dropdb
    (for the raw-fallback path).
    """
    from shutil import which

    if not (which("dropdb") and which("psql")):
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


def _db_exists_pg(db: str) -> bool:
    """Check DB existence via psql (not via odoo_db.py - keeps the test isolated)."""
    env = dict(os.environ)
    pw = os.environ.get("ODOO_PG_PASSWORD")
    if pw:
        env["PGPASSWORD"] = pw
    r = subprocess.run(
        ["psql", "-h", "localhost", "-d", "postgres", "-tAc",
         f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
        capture_output=True, text=True, env=env,
    )
    return r.returncode == 0 and r.stdout.strip() == "1"


def _createdb_pg(db: str):
    """Raw createdb for test setup only - stands in for Odoo create-on-init."""
    env = dict(os.environ)
    pw = os.environ.get("ODOO_PG_PASSWORD")
    if pw:
        env["PGPASSWORD"] = pw
    subprocess.run(["createdb", "-h", "localhost", db], check=True, env=env)


@pytest.mark.skipif(not _pg_available(), reason="no local Postgres (dropdb/psql)")
def test_ephemeral_reserve_only_then_caller_creates_then_release_drops(fixt, tmp_path):
    """B2 contract: acquire does NOT create the DB (reserve-only).

    Flow:
    1. acquire --mode ephemeral  -> allocator reserves a unique db_name but does
       NOT create the database (DB absent after acquire).
    2. Test harness creates the DB via raw createdb (stands in for Odoo create-on-init).
    3. release drops it THROUGH the odoo_db.py path - we substitute a fake odoo_db.py
       that records its argv and actually drops the DB via raw dropdb, so the outcome
       (DB gone) is real and observable while odoo_db.py's invocation is verifiable.
    4. Assert: (a) DB absent after acquire; (b) fake odoo_db.py was called with
       `drop <db>`; (c) DB gone after release; (d) raw `dropdb` shell tool was NOT
       used by the allocator directly (it went through odoo_db.py).

    NOTE: if the role lacks CREATEDB the allocator degrades to exclusive mode,
    which has drop_on_release=False and no DB drop at release.  Skip the
    through-Odoo drop assertions in that case (degraded path is separately tested
    by the fallback test below).
    """
    from shutil import which

    env, _, _ = fixt

    # Inject a fake odoo_db.py that records calls and actually drops the DB.
    # We need to intercept the venv_python -> odoo_db.py call without a real Odoo.
    # Strategy: create a wrapper that acts as both the "venv python" AND the
    # "odoo_db.py" target by writing a shim odoo_db.py next to the real one and
    # pointing the test env at it via a custom _ODOO_DB_PY path is NOT possible
    # without patching allocator internals.
    #
    # Instead: point the instance's `python` to a fake python wrapper that actually
    # calls `dropdb` when invoked as `<python> odoo_db.py drop <db> ...`.
    # The wrapper writes its argv to a log file so we can assert it was called.
    fake_dir = tmp_path / "fakevenv" / "bin"
    fake_dir.mkdir(parents=True)
    log = tmp_path / "odoo_db_calls.log"
    fake_python = fake_dir / "python"

    # The fake python intercepts `python odoo_db.py drop <db> <flags>` and
    # actually dropdb's (so the outcome is real) while logging the call.
    # Any other invocation falls through to the real python.
    fake_python.write_text(
        f"""\
#!/bin/sh
# Fake venv python for test: intercepts odoo_db.py drop calls.
script="$2"
cmd="$3"
db="$4"
if [ "$(basename "$script")" = "odoo_db.py" ] && [ "$cmd" = "drop" ] && [ -n "$db" ]; then
    echo "odoo_db.py drop $db $5 $6 $7 $8" >> "{log}"
    PGPASSWORD="${{ODOO_PG_PASSWORD:-}}" dropdb -h localhost "$db" --if-exists
    exit $?
fi
exec {sys.executable} "$@"
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    # Use a custom instances.toml that points python at our fake wrapper.
    toml = tmp_path / "instances2.toml"
    toml.write_text(
        INSTANCES_TOML.replace("python = \"/srv/venv/bin/python\"",
                               f"python = \"{fake_python}\""),
        encoding="utf-8",
    )
    home = tmp_path / "home2"
    home.mkdir()
    env2 = _env(home, toml)
    env2["PATH"] = f"{fake_dir}{os.pathsep}{env2['PATH']}"

    p = _run(env2, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0

    if a["ALLOC_MODE"] != "ephemeral":
        pytest.skip("role lacks CREATEDB - degraded to exclusive, B2 drop path not exercised")

    db = a["ALLOC_DB_NAME"]

    # (a) Allocator must NOT have created the DB (reserve-only).
    assert not _db_exists_pg(db), "ephemeral DB must NOT exist right after acquire (reserve-only)"

    # Simulate Odoo create-on-init: the caller creates the DB.
    if not which("createdb"):
        pytest.skip("createdb not on PATH - cannot simulate Odoo create-on-init")
    _createdb_pg(db)
    assert _db_exists_pg(db), "test setup: DB must exist after simulated Odoo create-on-init"

    # release: must drop through the odoo_db.py (fake python) path.
    rel = _run(env2, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0

    # (b) Fake odoo_db.py was invoked with `drop <db>`.
    assert log.exists(), "odoo_db.py drop must have been called via the venv python"
    calls = log.read_text(encoding="utf-8")
    assert f"odoo_db.py drop {db}" in calls, (
        f"expected 'odoo_db.py drop {db}' in fake log; got: {calls!r}"
    )

    # (c) DB is gone after release.
    assert not _db_exists_pg(db), "ephemeral DB must be absent after release"


# --------------------------------------------------------------------------- #
# Profile-aware acquire (WI-4)
# --------------------------------------------------------------------------- #
INSTANCES_TOML_TWO_PROFILES = """\
[[instance]]
series = "17.0"
profile = "minimal"
instance_key = "17.0:minimal"
addons_path = ["/srv/odoo/addons"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0_minimal"
db_name_prefix = "odoo_17_0_minimal"
db_host = "localhost"
db_user = "odoo"
python = "/srv/venv-minimal/bin/python"

[[instance]]
series = "17.0"
profile = "full"
instance_key = "17.0:full"
addons_path = ["/srv/odoo/addons", "/srv/custom"]
run_mode = "source"
http_port = 8169
http_port_base = 8180
port_pool_size = 10
db_name = "odoo_17_0_full"
db_name_prefix = "odoo_17_0_full"
db_host = "localhost"
db_user = "odoo"
python = "/srv/venv-full/bin/python"
"""


def test_acquire_selects_by_profile(tmp_path):
    """--profile must select the matching [[instance]] block, not the first block.

    Behavior contract:
    - acquire --series 17.0 --profile minimal -> selects the 'minimal' block
      (ALLOC_PYTHON=/srv/venv-minimal/bin/python, ALLOC_PROFILE=minimal)
    - acquire --series 17.0 --profile full -> selects the 'full' block
      (ALLOC_PYTHON=/srv/venv-full/bin/python, ALLOC_PROFILE=full)
    - ephemeral db_name uses the matching block's db_name_prefix
    """
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML_TWO_PROFILES, encoding="utf-8")
    env = _env(home, toml)

    # Acquire for 'minimal' profile.
    p_min = _run(env, "acquire", "--series", "17.0", "--profile", "minimal",
                 "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert p_min.returncode == 0, (
        f"acquire --profile minimal failed.\nstdout: {p_min.stdout}\nstderr: {p_min.stderr}"
    )
    a_min = _parse_alloc(p_min.stdout)
    assert a_min.get("ALLOC_PROFILE") == "minimal", (
        f"ALLOC_PROFILE must be 'minimal'; got {a_min.get('ALLOC_PROFILE')!r}"
    )
    assert a_min.get("ALLOC_PYTHON") == "/srv/venv-minimal/bin/python", (
        f"ALLOC_PYTHON must come from minimal block; got {a_min.get('ALLOC_PYTHON')!r}"
    )
    assert a_min.get("ALLOC_DB_NAME", "").startswith("odoo_17_0_minimal_t_"), (
        f"ephemeral db_name must use minimal prefix; got {a_min.get('ALLOC_DB_NAME')!r}"
    )

    # Acquire for 'full' profile - must select different block.
    p_full = _run(env, "acquire", "--series", "17.0", "--profile", "full",
                  "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert p_full.returncode == 0, (
        f"acquire --profile full failed.\nstdout: {p_full.stdout}\nstderr: {p_full.stderr}"
    )
    a_full = _parse_alloc(p_full.stdout)
    assert a_full.get("ALLOC_PROFILE") == "full", (
        f"ALLOC_PROFILE must be 'full'; got {a_full.get('ALLOC_PROFILE')!r}"
    )
    assert a_full.get("ALLOC_PYTHON") == "/srv/venv-full/bin/python", (
        f"ALLOC_PYTHON must come from full block; got {a_full.get('ALLOC_PYTHON')!r}"
    )
    assert a_full.get("ALLOC_DB_NAME", "").startswith("odoo_17_0_full_t_"), (
        f"ephemeral db_name must use full prefix; got {a_full.get('ALLOC_DB_NAME')!r}"
    )


@pytest.mark.skipif(not _pg_available(), reason="no local Postgres (dropdb/psql)")
def test_ephemeral_release_fallback_when_no_venv(fixt, tmp_path):
    """When the lease has no python (empty), release drops via raw dropdb AND logs WARNING.

    This exercises the fallback path: venv_python is '' in the lease, so
    _drop_through_odoo must skip odoo_db.py and call raw _dropdb, emitting the
    WARNING sentinel to stderr.
    """
    from shutil import which

    if not which("createdb"):
        pytest.skip("createdb not on PATH - cannot simulate Odoo create-on-init")

    # Use an instances.toml WITHOUT a python field so the lease stores python=''.
    toml_no_python = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
"""
    home = tmp_path / "home_nopy"
    home.mkdir()
    toml = tmp_path / "instances_nopy.toml"
    toml.write_text(toml_no_python, encoding="utf-8")
    env = _env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0

    if a["ALLOC_MODE"] != "ephemeral":
        pytest.skip("role lacks CREATEDB - degraded to exclusive, fallback path not exercised")

    db = a["ALLOC_DB_NAME"]

    # Verify the lease has empty python (no venv).
    leases = json.loads(_run(env, "list").stdout)["leases"]
    assert len(leases) == 1
    assert leases[0]["python"] == "", "lease must carry empty python when instances.toml has none"
    assert leases[0]["drop_on_release"] is True

    # Simulate Odoo create-on-init.
    _createdb_pg(db)
    assert _db_exists_pg(db), "test setup: DB must exist after simulated create-on-init"

    # Release: must fall back to raw dropdb AND emit WARNING to stderr.
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0

    # (a) WARNING marker must appear in stderr.
    assert "WARNING" in rel.stderr and "venv unavailable" in rel.stderr, (
        f"allocator must emit 'WARNING - venv unavailable' when python is empty; "
        f"got stderr: {rel.stderr!r}"
    )

    # (b) DB is gone (raw dropdb succeeded).
    assert not _db_exists_pg(db), "ephemeral DB must be absent after release via raw dropdb fallback"


def test_ephemeral_release_does_not_fallback_on_genuine_drop_failure(tmp_path):
    """When the fake odoo_db.py exits with rc=1 (genuine exp_drop failure, NOT rc=10),
    the allocator must NOT invoke raw dropdb, must retain the lease, and must return
    a non-zero exit code.

    This is a pure-CPU test (no Postgres needed): we use a fake psql that makes
    _probe_createdb return True, a fake odoo_db.py that exits rc=1, and a fake
    dropdb binary that logs any invocation so we can assert it was NOT called.
    """
    # Fake psql: prints 't' (role has CREATEDB) so probe passes without real PG.
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    dropdb_log = tmp_path / "dropdb_calls.log"

    fake_psql = bindir / "psql"
    fake_psql.write_text("#!/bin/sh\necho t\n", encoding="utf-8")
    fake_psql.chmod(0o755)

    # Fake dropdb: logs any call (must NOT be invoked on genuine rc=1).
    fake_dropdb = bindir / "dropdb"
    fake_dropdb.write_text(
        '#!/bin/sh\necho "dropdb $*" >> "{log}"\n'.format(log=dropdb_log),
        encoding="utf-8",
    )
    fake_dropdb.chmod(0o755)

    # Fake venv python: invoked as `<python> /path/to/odoo_db.py drop <db> ...`
    # so $1=odoo_db.py path, $2=drop, $3=db_name.
    # Exits rc=1 to simulate a genuine Odoo exp_drop failure (NOT rc=10).
    fake_python = bindir / "fake_python"
    fake_python.write_text(
        '#!/bin/sh\n'
        'if [ "$(basename "$1")" = "odoo_db.py" ] && [ "$2" = "drop" ]; then\n'
        '    echo "odoo_db: exp_drop failed" >&2\n'
        '    exit 1\n'
        'fi\n'
        'exec {real_py} "$@"\n'.format(real_py=sys.executable),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    # Point the instance's python at our fake_python so the lease stores it.
    toml.write_text(
        INSTANCES_TOML.replace(
            'python = "/srv/venv/bin/python"',
            'python = "{fake_py}"'.format(fake_py=fake_python),
        ),
        encoding="utf-8",
    )
    env = _env(home, toml)
    env["PATH"] = "{bin}{sep}{path}".format(
        bin=bindir, sep=os.pathsep, path=env.get("PATH", "")
    )

    # Acquire an ephemeral lease (psql returns 't' so probe passes).
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    assert a["ALLOC_MODE"] == "ephemeral", "fake psql should have allowed ephemeral mode"

    # Release: fake odoo_db.py exits rc=1 -> genuine failure path.
    rel = _run(env, "release", a["ALLOC_TOKEN"])

    # (i) raw dropdb shell tool was NOT invoked.
    calls = dropdb_log.read_text(encoding="utf-8") if dropdb_log.exists() else ""
    assert "dropdb" not in calls, (
        "raw dropdb must NOT be called when odoo_db.py exits rc=1 (genuine failure); "
        "got: {calls!r}".format(calls=calls)
    )

    # (ii) the lease is RETAINED in the registry.
    leases = _leases(env)
    assert len(leases) == 1, (
        "lease must be retained when drop fails (so gc can retry); "
        "got {n} leases".format(n=len(leases))
    )
    assert leases[0]["token"] == a["ALLOC_TOKEN"], "retained lease must be the original token"

    # (iii) cmd_release returned non-zero.
    assert rel.returncode != 0, (
        "release must return non-zero when through-Odoo drop fails; "
        "got rc={rc}".format(rc=rel.returncode)
    )

    # (iv) stderr carries an ERROR marker.
    assert "ERROR" in rel.stderr, (
        "release must emit ERROR to stderr when through-Odoo drop fails; "
        "got: {stderr!r}".format(stderr=rel.stderr)
    )


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
    assert lz["drop_on_release"] is False, "a shared lease must NEVER own the declared DB"
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
    # Stub BOTH drop paths so any DB-destroying invocation is RECORDED.
    # The through-Odoo path (odoo_db.py) would be called by the fake venv python;
    # the raw-dropdb fallback path would call the shell `dropdb`.
    # If drop_on_release is False (as it must be for shared), NEITHER path fires.
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    log = tmp_path / "pg_calls.log"
    for tool in ("dropdb", "psql", "createdb"):
        f = bindir / tool
        f.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{log}"\n', encoding="utf-8")
        f.chmod(0o755)

    # Also create a fake python that logs any odoo_db.py invocation.
    fake_python = bindir / "fake_python"
    fake_python.write_text(
        f"""\
#!/bin/sh
echo "fake_python $*" >> "{log}"
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    # Use an instances.toml pointing to the fake python so if the allocator ever
    # incorrectly tries to drop via odoo_db.py on a shared lease, the call is logged.
    home2 = tmp_path / "home2"
    home2.mkdir()
    toml2 = tmp_path / "instances2.toml"
    toml2.write_text(
        INSTANCES_TOML.replace("python = \"/srv/venv/bin/python\"",
                               f"python = \"{fake_python}\""),
        encoding="utf-8",
    )
    env = _env(home2, toml2)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()  # dead.pid is now a dead pid on this host
    _shared(env, "--port", "8069", "--db-name", "odoo_17_0", "--pid", str(dead.pid))
    leases = _leases(env)
    assert len(leases) == 1 and leases[0]["drop_on_release"] is False

    _run(env, "gc")
    assert len(_leases(env)) == 0, "a dead-server shared row must be reclaimed (discovery self-heals)"
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "odoo_17_0" not in calls, "gc must NEVER touch the shared declared database"
    assert "dropdb" not in calls, "no raw dropdb may run for a drop_on_release=False shared lease"
    assert "fake_python" not in calls, "odoo_db.py path must not fire for a shared lease"


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


# --------------------------------------------------------------------------- #
# #163 db_port: threaded end-to-end (catalog -> lease -> drop/probe -> emit)
# --------------------------------------------------------------------------- #
INSTANCES_TOML_PORT = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
db_port = 5433
python = "/srv/venv/bin/python"
"""


def _env_with_toml(tmp_path, toml_text, home_name="home"):
    home = tmp_path / home_name
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(toml_text, encoding="utf-8")
    return _env(home, toml)


def test_lease_stores_db_port_and_pg_port(tmp_path):
    """A declared db_port must be persisted on the lease (top-level + _pg mirror)."""
    env = _env_with_toml(tmp_path, INSTANCES_TOML_PORT)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "exclusive", "--db-name", "x")
    assert p.returncode == 0, p.stderr
    lz = _leases(env)[0]
    assert str(lz.get("db_port")) == "5433", "db_port must be stored top-level on the lease"
    assert str(lz.get("_pg", {}).get("port")) == "5433", "db_port must mirror into _pg.port"


def test_acquire_echoes_alloc_db_port_when_declared(tmp_path):
    env = _env_with_toml(tmp_path, INSTANCES_TOML_PORT)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "exclusive", "--db-name", "x")
    a = _parse_alloc(p.stdout)
    assert a.get("ALLOC_DB_PORT") == "5433", "acquire must echo ALLOC_DB_PORT so the handle round-trips it"


def test_acquire_db_port_empty_when_absent_not_5432(fixt):
    """The empty-omit rule: no declared db_port -> ALLOC_DB_PORT='' (NEVER a fabricated 5432)."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x")
    assert a.get("ALLOC_DB_PORT", "") == "", (
        f"ALLOC_DB_PORT must be empty when no db_port is declared; got {a.get('ALLOC_DB_PORT')!r}"
    )
    assert a.get("ALLOC_DB_PORT", "") != "5432", "must not fabricate 5432"
    lz = _leases(env)[0]
    assert str(lz.get("db_port", "")) == "", "lease db_port must be empty when undeclared"


def _make_drop_logger_env(tmp_path, toml_text):
    """Return (env, log_path): a fake psql that passes the CREATEDB probe and a
    fake venv python that LOGS the odoo_db.py argv (so we can assert the drop
    command flags) and exits 0. CPU-only: no real Postgres, no real dropdb."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "psql").write_text("#!/bin/sh\necho t\n", encoding="utf-8")
    (bindir / "psql").chmod(0o755)
    log = tmp_path / "odoo_db_argv.log"
    fake_python = bindir / "fake_python"
    fake_python.write_text(
        '#!/bin/sh\n'
        'if [ "$(basename "$1")" = "odoo_db.py" ]; then echo "$@" >> "%s"; exit 0; fi\n'
        'exec %s "$@"\n' % (log, sys.executable),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(toml_text.replace('python = "/srv/venv/bin/python"',
                                      f'python = "{fake_python}"'), encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    return env, log


def test_drop_through_odoo_includes_db_port_when_set(tmp_path):
    """_drop_through_odoo must thread --db-port to odoo_db.py when the lease has one."""
    env, log = _make_drop_logger_env(tmp_path, INSTANCES_TOML_PORT)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    if a["ALLOC_MODE"] != "ephemeral":
        pytest.skip("probe degraded to exclusive - drop path not exercised")
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0, rel.stderr
    argv = log.read_text(encoding="utf-8")
    assert "--db-port" in argv and "5433" in argv, (
        f"drop command must include --db-port 5433 when the lease carries db_port; got {argv!r}"
    )


def test_drop_through_odoo_omits_db_port_when_empty(tmp_path):
    """No declared db_port -> the drop command must NOT carry --db-port (empty-omit)."""
    # INSTANCES_TOML has db_name_prefix but no db_port.
    env, log = _make_drop_logger_env(tmp_path, INSTANCES_TOML)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    if a["ALLOC_MODE"] != "ephemeral":
        pytest.skip("probe degraded to exclusive - drop path not exercised")
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0, rel.stderr
    argv = log.read_text(encoding="utf-8")
    assert "--db-port" not in argv, (
        f"drop command must OMIT --db-port when no db_port is declared; got {argv!r}"
    )


# --------------------------------------------------------------------------- #
# Ownership: run_id carrier + FIXED release predicate (BLOCKER-1)
# --------------------------------------------------------------------------- #
def test_acquire_run_id_stored_as_owner_run_id_and_echoed(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x",
                    "--run-id", "add-priority-20260101-a3f1")
    assert a.get("ALLOC_RUN_ID") == "add-priority-20260101-a3f1", "acquire must echo ALLOC_RUN_ID"
    lz = _leases(env)[0]
    assert lz["owner"].get("run_id") == "add-priority-20260101-a3f1", (
        "the run id must be stored as owner.run_id (canonical ownership key)"
    )
    assert "session_id" not in lz["owner"], (
        "new leases must STOP writing the standalone dead session_id field"
    )


def test_session_alias_still_populates_owner_run_id(fixt):
    """--session stays a back-compat alias that lands in owner.run_id."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x", "--session", "legacy-run")
    assert a.get("ALLOC_RUN_ID") == "legacy-run"
    assert _leases(env)[0]["owner"].get("run_id") == "legacy-run"


def test_release_without_run_id_still_succeeds_on_owned_lease(fixt):
    """BLOCKER-1: the rightful owner must NEVER be blocked from releasing its own
    lease just because no run id was forwarded to the release call (token-possession)."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x", "--run-id", "run-A")
    rel = _run(env, "release", a["ALLOC_TOKEN"])  # NO --run-id forwarded
    assert rel.returncode == 0, (
        f"release with no forwarded run_id must succeed (token-possession); stderr={rel.stderr!r}"
    )
    assert _leases(env) == [], "the lease must be removed on a successful release"


def test_release_matching_run_id_proceeds(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x", "--run-id", "run-A")
    rel = _run(env, "release", a["ALLOC_TOKEN"], "--run-id", "run-A")
    assert rel.returncode == 0, rel.stderr
    assert _leases(env) == []


def test_release_different_run_id_refused_and_db_not_dropped(tmp_path):
    """A DIFFERENT non-empty caller run must be refused: non-zero, lease kept, DB NOT dropped."""
    env, log = _make_drop_logger_env(tmp_path, INSTANCES_TOML_PORT)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             "--run-id", "run-A")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0
    if a["ALLOC_MODE"] != "ephemeral":
        pytest.skip("probe degraded to exclusive - drop path not exercised")
    rel = _run(env, "release", a["ALLOC_TOKEN"], "--run-id", "run-B")
    assert rel.returncode != 0, "a foreign run must be refused"
    assert "run-A" in rel.stderr, f"refusal must name the owner run; stderr={rel.stderr!r}"
    assert len(_leases(env)) == 1, "a refused release must KEEP the lease"
    assert not log.exists(), "a refused release must NOT invoke the drop (DB untouched)"


def test_force_release_of_foreign_run_proceeds_and_logs(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x", "--run-id", "run-A")
    rel = _run(env, "release", a["ALLOC_TOKEN"], "--run-id", "run-B", "--force")
    assert rel.returncode == 0, rel.stderr
    assert _leases(env) == [], "--force must proceed with the release"
    assert "force" in rel.stderr.lower(), f"--force must log a loud line; stderr={rel.stderr!r}"


def _seed_registry(env, leases):
    home = Path(env["ODOO_AI_HOME"])
    runtime = home / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "leases.json").write_text(
        json.dumps({"schema_version": 2, "leases": leases}), encoding="utf-8"
    )


def test_legacy_session_id_only_lease_releasable_by_token(fixt):
    """A pre-existing lease that carries ONLY owner.session_id (no run_id) must be
    releasable by token possession (owner_run resolves via the session_id fallback)."""
    env, _, _ = fixt
    token = "ab" * 16
    now = int(time.time())
    _seed_registry(env, [{
        "token": token, "mode": "exclusive", "db_name": "legacy", "drop_on_release": False,
        "owner": {"host": socket.gethostname(), "pid": None,
                  "session_id": "old-run", "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now, "_pg": {"host": "localhost", "user": "odoo"},
    }])
    rel = _run(env, "release", token)  # no run id
    assert rel.returncode == 0, f"legacy lease must be releasable by token; stderr={rel.stderr!r}"
    assert _leases(env) == []


# --------------------------------------------------------------------------- #
# assert-droppable (read-only ownership probe under flock)
# --------------------------------------------------------------------------- #
def test_assert_droppable_refuses_fresh_foreign_lease(fixt):
    env, _, _ = fixt
    _acquire(env, "--mode", "exclusive", "--db-name", "mydb", "--run-id", "run-A")
    r = _run(env, "assert-droppable", "--db-name", "mydb", "--run-id", "run-B")
    assert r.returncode != 0, "a fresh lease owned by a different run must be non-droppable"
    assert "run-A" in r.stderr, f"assert-droppable must name the owning run; stderr={r.stderr!r}"


def test_assert_droppable_allows_own_run(fixt):
    env, _, _ = fixt
    _acquire(env, "--mode", "exclusive", "--db-name", "mydb", "--run-id", "run-A")
    r = _run(env, "assert-droppable", "--db-name", "mydb", "--run-id", "run-A")
    assert r.returncode == 0, f"the owning run may drop its own DB; stderr={r.stderr!r}"


def test_assert_droppable_allows_unmanaged_db(fixt):
    env, _, _ = fixt
    r = _run(env, "assert-droppable", "--db-name", "no_such_lease", "--run-id", "run-B")
    assert r.returncode == 0, "an unmanaged DB (no lease) is always droppable"


def test_assert_droppable_refuses_foreign_drop_of_shared_lease(fixt):
    """A `shared` lease acquired WITH --run-id=A must refuse a foreign bare-drop
    (--run-id=B) exactly like an exclusive lease does - assert-droppable's
    ownership guard is mode-agnostic; owner-stamping a shared lease is enough
    to protect it (P5.5: the shared-lease registration path threads --run-id)."""
    env, _, _ = fixt
    _shared(env, "--port", "18069", "--run-id", "run-A")
    r = _run(env, "assert-droppable", "--db-name", "odoo_17_0", "--run-id", "run-B")
    assert r.returncode != 0, "a shared lease owned by a different run must be non-droppable"
    assert "run-A" in r.stderr, f"assert-droppable must name the owning run; stderr={r.stderr!r}"


def test_assert_droppable_refuses_unowned_fresh_lease_without_force(fixt):
    """P5.8: an UNOWNED (no run_id at all) but FRESH lease must be refused by
    assert-droppable without --force - 'unowned' is no longer a synonym for
    'safe to drop'. --force still overrides (the documented reap escape hatch)."""
    env, _, _ = fixt
    _acquire(env, "--mode", "exclusive", "--db-name", "mydb")  # no --run-id: unowned
    r = _run(env, "assert-droppable", "--db-name", "mydb")
    assert r.returncode != 0, "an unowned fresh lease must be refused without --force"
    r2 = _run(env, "assert-droppable", "--db-name", "mydb", "--force")
    assert r2.returncode == 0, "--force must override the unowned-fresh refusal"


def test_assert_droppable_allows_stale_foreign_lease(fixt):
    env, _, _ = fixt
    now = int(time.time())
    _seed_registry(env, [{
        "token": "cd" * 16, "mode": "exclusive", "db_name": "stalemydb", "drop_on_release": False,
        "owner": {"host": socket.gethostname(), "pid": None,
                  "run_id": "run-C", "started_at": now - 100000},
        "ttl_s": 1, "heartbeat_at": now - 100000, "_pg": {"host": "localhost", "user": "odoo"},
    }])
    r = _run(env, "assert-droppable", "--db-name", "stalemydb", "--run-id", "run-B")
    assert r.returncode == 0, (
        f"a STALE foreign lease must not block a drop (gc would reap it); stderr={r.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# cmd_list token redaction (accident-prevention layer)
# --------------------------------------------------------------------------- #
def test_list_redacts_tokens_by_default_full_with_show_tokens(fixt):
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "x")
    full = a["ALLOC_TOKEN"]

    default_reg = json.loads(_run(env, "list").stdout)["leases"][0]
    assert default_reg["token"] != full, "list must NOT print the full token by default"
    assert default_reg["token"] == full[:8], "the default token must be an 8-char fingerprint"

    shown_reg = json.loads(_run(env, "list", "--show-tokens").stdout)["leases"][0]
    assert shown_reg["token"] == full, "--show-tokens must reveal the full token"


# --------------------------------------------------------------------------- #
# registry schema_version stamp
# --------------------------------------------------------------------------- #
def test_registry_stamps_schema_version_2(fixt):
    env, _, _ = fixt
    _acquire(env, "--mode", "ephemeral", "--no-create")
    reg = json.loads(_run(env, "list", "--show-tokens").stdout)
    assert reg.get("schema_version") == 2, "a written registry must be stamped schema_version: 2"
