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

import contextlib
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
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


def _run(env, *args, timeout=None):
    """Invoke the allocator. `timeout` is a HARD test-side bound: every command
    promises to return a verdict, so a hang is a FAILURE (TimeoutExpired), never
    a test that waits until the harness kills it."""
    return subprocess.run(
        [sys.executable, str(ALLOC), *args],
        capture_output=True, text=True, env=env, timeout=timeout,
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


def _make_fake_venv_python(bindir, name="fake_python", log=None,
                           createdb="true", createdb_rc=0, drop_rc=0,
                           preflight_rc=0, exists=None):
    """Write a stand-in for the instance's DECLARED venv python and return its path.

    The allocator asks every Postgres question through this interpreter, so the
    stub answers `odoo_db.py <subcommand>` the way a real venv would and logs the
    full argv of each call. It deliberately does NOT stub any libpq client
    binary: the whole point of the contract under test is that a role's CREATEDB
    privilege is asked of the CLUSTER, never inferred from installed binaries.

    `preflight_rc` / `drop_rc` accept the CONNECTION codes (8 authentication
    refused, 9 cluster unreachable) as well as 0, 1 and the venv sentinel 10, so a
    test can distinguish "this route never reached the database" from "the
    operation was attempted and failed" - the pair the allocator must never
    conflate. `exists` answers the existence question; left None the stub says
    nothing, which is the "could not look" case.
    """
    bindir.mkdir(parents=True, exist_ok=True)
    py = bindir / name
    log_line = 'echo "$@" >> "%s"\n    ' % log if log is not None else ""
    py.write_text(
        '#!/bin/sh\n'
        'if [ "$(basename "$1")" = "odoo_db.py" ]; then\n'
        '    %s'
        'case "$2" in\n'
        '      can-createdb) %sexit %d ;;\n'
        '      drop) exit %d ;;\n'
        '      preflight) echo "DB_AUTH_WHY=stub"; exit %d ;;\n'
        '      exists) %sexit 0 ;;\n'
        '    esac\n'
        '    exit 0\n'
        'fi\n'
        'exec %s "$@"\n' % (
            log_line,
            ('echo %s; ' % createdb) if createdb is not None else "",
            createdb_rc, drop_rc, preflight_rc,
            ('echo %s; ' % exists) if exists is not None else "",
            sys.executable,
        ),
        encoding="utf-8",
    )
    py.chmod(0o755)
    return py


def _env_with_fake_venv(tmp_path, toml_text=None, **stub):
    """(env, log, py): a catalog whose `python` points at a stubbed venv
    interpreter, so an ephemeral acquire can be exercised with no real Postgres,
    no real Odoo, and no libpq client anywhere on PATH."""
    log = tmp_path / "odoo_db_argv.log"
    stub.setdefault("log", log)
    py = _make_fake_venv_python(tmp_path / "fakebin", **stub)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text((toml_text or INSTANCES_TOML).replace(
        'python = "/srv/venv/bin/python"', f'python = "{py}"'), encoding="utf-8")
    return _env(home, toml), log, py


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
# P2 boundary off-by-one fix (49-solution-final.md §2.3): a pooled port must
# never be handed out to instance-0 when it is instance-1's DECLARED boundary
# port, even though it falls inside instance-0's naive pool range. Declared
# ports step by 10 (40-instance-profile.sh) while DEFAULT_POOL_SIZE=10, so
# instance-0's pool [8070, 8080) naturally reaches 8079 == instance-1's
# declared port.
# --------------------------------------------------------------------------- #
INSTANCES_TOML_TWO_INSTANCES_BOUNDARY = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons-a"]
run_mode = "source"
http_port = 8069
db_name = "odoo_17_0_a"
db_name_prefix = "odoo_17_0_a"
db_host = "localhost"
db_user = "odoo"

[[instance]]
series = "18.0"
addons_path = ["/srv/odoo/addons-b"]
run_mode = "source"
http_port = 8079
db_name = "odoo_18_0_b"
db_name_prefix = "odoo_18_0_b"
db_host = "localhost"
db_user = "odoo"
"""


def test_maxed_out_pool_never_hands_out_a_sibling_instances_declared_port(tmp_path):
    """Two catalog instances declared 8069/8079 (10-apart; no http_port_base/
    port_pool_size overrides, so the pool derives from http_port+1..+10 = the
    naive [8070, 8080) range). Maxing out instance-0's pool must NEVER hand out
    8079 - instance-1's declared http_port - even though it falls inside
    instance-0's naive pool range.

    MUST FAIL on the pre-fix allocator (which only reserved the ACQUIRING
    instance's own declared port, `reserved={declared_port}`) and PASS once
    every catalog-declared http_port is reserved. Asserts on allocation
    RESULTS (the actual ports handed out), not on `_pick_ports` internals.
    """
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML_TWO_INSTANCES_BOUNDARY, encoding="utf-8")
    env = _env(home, toml)

    # Instance-0's naive pool is [8070, 8080) (DEFAULT_POOL_SIZE=10,
    # base=declared_port+1). Drain it one port at a time until exhausted,
    # recording every port actually handed out.
    handed_out = []
    for _ in range(20):  # generous upper bound; the pool holds at most 10
        p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
                 "--no-create", "--ports", "1")
        if p.returncode != 0:
            break
        handed_out.extend(_parse_alloc(p.stdout).get("ALLOC_PORTS", []))

    assert handed_out, "instance-0's pool must hand out at least one port"
    assert len(handed_out) == len(set(handed_out)), (
        f"a maxed-out pool must never hand out the same port twice; got {handed_out!r}"
    )
    assert 8079 not in handed_out, (
        "instance-0's pool must NEVER hand out 8079 - instance-1's declared "
        f"http_port - even though it falls inside the naive [8070,8080) pool "
        f"range; got {handed_out!r}"
    )


# --------------------------------------------------------------------------- #
# Lease record shape (B2 model)
# --------------------------------------------------------------------------- #
def test_ephemeral_lease_carries_drop_context(tmp_path):
    """Verify the new B2 lease fields that _drop_through_odoo reads at release time.

    We need drop_on_release=True which requires an ephemeral lease WITHOUT
    --no-create. The instance's declared python answers `can-createdb` with
    `true` (the role HAS CREATEDB), which is the only thing that may keep an
    ephemeral request in ephemeral mode.
    """
    env, _log, fake_py = _env_with_fake_venv(tmp_path)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_MODE"] == "ephemeral", (
        "a role that positively HAS CREATEDB must keep the acquire in ephemeral mode"
    )

    leases = _leases(env)
    assert len(leases) == 1
    lz = leases[0]
    assert lz["drop_on_release"] is True, "ephemeral lease must set drop_on_release=True"
    assert lz["python"] == str(fake_py), "venv interpreter must be stored in lease"
    assert lz["db_host"] == "localhost", "db_host must be stored for drop-context"
    assert lz["db_user"] == "odoo", "db_user must be stored for drop-context"
    # Password must NOT be stored - it is read from ODOO_PG_PASSWORD at drop time.
    assert "db_password" not in lz, "PG password must never be stored in the lease"
    assert "created_db" not in lz, "old created_db field must not appear (replaced by drop_on_release)"


def test_lease_addons_path_is_comma_separated_not_colon(fixt):
    """The lease's stored addons_path is forward-context for future tooling that
    launches odoo-bin directly from the lease (see the comment in allocator.py) -
    it must already be in Odoo's --addons-path/addons_path syntax (COMMA-separated
    directories), never colon (that is PATH/PYTHONPATH style, not an Odoo addons-path
    separator), and must match ALLOC_ADDONS_PATH's format so a future consumer can
    forward it to odoo-bin verbatim with no extra conversion step."""
    env, _, _ = fixt
    p, a = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert p.returncode == 0
    assert a["ALLOC_ADDONS_PATH"] == "/srv/odoo/addons,/srv/custom"

    leases = _leases(env)
    assert len(leases) == 1
    assert leases[0]["addons_path"] == a["ALLOC_ADDONS_PATH"] == "/srv/odoo/addons,/srv/custom", (
        "lease addons_path must be comma-separated, matching Odoo's --addons-path/"
        "addons_path syntax and ALLOC_ADDONS_PATH - not colon-delimited"
    )
    assert ":" not in leases[0]["addons_path"], (
        "lease addons_path must never use colon as the directory separator - "
        "Odoo's addons-path parser splits on comma only"
    )


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
# G4 regression: liveness must be AUTHORITATIVE for `_is_stale`, not merely a
# condemn-only signal. Before this fix, a LIVE owner pid could only ever
# CONDEMN a lease (never protect one) - control fell straight through to the
# ttl comparison regardless, so a still-running, in-use instance got reclaimed
# (process group killed + DB dropped) the moment nobody called `heartbeat`
# within `ttl_s` (2h default) - "work in progress gets cleaned up mid-run".
# These call `_is_stale` directly (fast, no subprocess) with a monkeypatched
# `_host`/`_pid_alive`/`_pid_fingerprint` so each scenario is deterministic and
# does not depend on real OS process timing.
# --------------------------------------------------------------------------- #
def test_is_stale_alive_verified_pid_survives_expired_ttl(monkeypatch):
    """THE defect: a same-host owner pid that is PROVABLY alive (its recorded
    `pid_started` fingerprint still matches) must NOT be reclaimed by an
    expired TTL - liveness is authoritative, not merely a condemn signal.
    MUST FAIL on the pre-fix allocator (measured: `_is_stale` returned True /
    stale here, which is exactly the reported "live instance reaped" bug)."""
    alloc = _import_allocator()
    monkeypatch.setattr(alloc, "_host", lambda: "thishost")
    monkeypatch.setattr(alloc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(alloc, "_pid_fingerprint", lambda pid: "FP-A")
    lease = {
        "owner": {"host": "thishost", "pid": 4242, "pid_started": "FP-A", "started_at": 0},
        "ttl_s": 1, "heartbeat_at": 0,  # heartbeat is ancient; ttl is long expired
    }
    assert alloc._is_stale(lease) is False, (
        "a provably-alive, same-host owner must NOT be condemned by an expired TTL"
    )


def test_is_stale_dead_pid_is_stale_regardless_of_fresh_ttl(monkeypatch):
    """A dead owner pid on this host is unambiguous - condemn immediately, even
    when the TTL has NOT expired (a fresh heartbeat does not resurrect a dead
    process). Already correct pre-fix (the dead-pid arm was unconditional
    before this change too); kept as an explicit lock-in guard."""
    alloc = _import_allocator()
    monkeypatch.setattr(alloc, "_host", lambda: "thishost")
    monkeypatch.setattr(alloc, "_pid_alive", lambda pid: False)
    now = alloc._now()
    lease = {
        "owner": {"host": "thishost", "pid": 4242, "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now,  # fresh - well within ttl
    }
    assert alloc._is_stale(lease) is True, (
        "a dead owner pid on this host must be stale regardless of a fresh TTL"
    )


def test_is_stale_unprovable_liveness_still_governed_by_ttl(monkeypatch):
    """When liveness cannot be proven at all (a different host - the pid
    integer is meaningless off-host), TTL remains the sole signal: expired ->
    stale, fresh -> not stale. Already correct pre-fix (the different-host
    lease never entered the pid branch either before or after); kept as an
    explicit lock-in guard for the ONE case TTL still governs post-fix."""
    alloc = _import_allocator()
    monkeypatch.setattr(alloc, "_host", lambda: "thishost")
    expired = {
        "owner": {"host": "otherhost", "pid": 4242, "started_at": 0},
        "ttl_s": 1, "heartbeat_at": 0,
    }
    assert alloc._is_stale(expired) is True, (
        "a different-host lease (liveness unprovable) must still expire on TTL"
    )
    now = alloc._now()
    fresh = {
        "owner": {"host": "otherhost", "pid": 4242, "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now,
    }
    assert alloc._is_stale(fresh) is False, (
        "a different-host lease still within TTL must not be stale"
    )


def test_is_stale_recycled_pid_is_condemned_not_protected(monkeypatch):
    """A pid can be reused by the OS: a bare `os.kill(pid, 0)` cannot tell the
    lease's original owner apart from an unrelated later process that inherited
    the same pid. When the re-measured fingerprint POSITIVELY mismatches the
    one recorded at bind/acquire time, the original owner is exactly as gone as
    a dead pid - condemn now, do not let the recycled pid protect the lease
    forever (the failure mode a bare pid check alone cannot avoid)."""
    alloc = _import_allocator()
    monkeypatch.setattr(alloc, "_host", lambda: "thishost")
    monkeypatch.setattr(alloc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(alloc, "_pid_fingerprint", lambda pid: "FP-IMPOSTOR")
    now = alloc._now()
    lease = {
        "owner": {"host": "thishost", "pid": 4242, "pid_started": "FP-ORIGINAL", "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now,
    }
    assert alloc._is_stale(lease) is True, (
        "a pid whose re-measured fingerprint no longer matches the recorded one "
        "must be condemned, not protected - the original owner is provably gone"
    )


def test_pid_owner_fields_records_a_fingerprint_for_acquire_and_bind(fixt):
    """Both places that learn a stable owner pid (`acquire --pid` and `bind`)
    must persist `owner.pid_started` alongside `owner.pid` - the fingerprint
    `_is_stale` needs to tell a genuinely-alive owner apart from a pid-recycled
    impostor. A lease with a pid but no fingerprint can only ever fall back to
    the ttl path, silently losing the G4 protection - so its presence here is
    itself a load-bearing regression guard."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "fp_db", "--pid", str(os.getpid()))
    leases = _leases(env)
    assert len(leases) == 1
    assert leases[0]["owner"]["pid"] == os.getpid()
    assert leases[0]["owner"]["pid_started"], (
        "acquire --pid must record a pid_started fingerprint, not leave it null"
    )

    _, b = _acquire(env, "--mode", "exclusive", "--db-name", "fp_db2")
    assert _leases(env)[1]["owner"]["pid"] is None
    r = _run(env, "bind", b["ALLOC_TOKEN"], "--pid", str(os.getpid()))
    assert r.returncode == 0, r.stderr
    bound = next(lz for lz in _leases(env) if lz["token"] == b["ALLOC_TOKEN"])
    assert bound["owner"]["pid"] == os.getpid()
    assert bound["owner"]["pid_started"], "bind must also record the pid_started fingerprint"


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


def test_a_persist_value_is_never_accepted_as_an_allocator_mode(fixt):
    """`--mode` takes the FOUR allocator modes only. `exclusive-running` is a
    `persist:` value (the skill/agent lifecycle vocabulary) that maps onto
    `--mode ephemeral`, and the lifetime difference is load-bearing: the mode
    decides `drop_on_release`, i.e. whether `release` destroys the database. A
    silently accepted persist value would hand a caller a lease whose fate is
    not the one it asked for, so this must be a loud refusal that writes
    nothing - and the two neighbouring real modes must keep working."""
    env, _, _ = fixt
    p, _ = _acquire(env, "--mode", "exclusive-running", "--ports", "1")
    assert p.returncode == 2, (
        f"a persist value must be REFUSED as a --mode, not accepted\n{p.stdout}{p.stderr}"
    )
    assert "exclusive-running" in p.stderr, "the refusal must name the value it rejected"
    assert _leases(env) == [], "a refused mode must write NO lease"

    # The real modes on either side of the confusion, and the fate each carries.
    p, a = _acquire(env, "--mode", "ephemeral", "--ports", "1", "--no-create")
    assert p.returncode == 0, p.stderr
    p, a = _acquire(env, "--mode", "exclusive", "--ports", "1")
    assert p.returncode == 0, p.stderr
    fates = {lz["mode"]: lz["drop_on_release"] for lz in _leases(env)}
    assert fates.get("exclusive") is False, (
        "an `exclusive` lease's database must SURVIVE release (drop_on_release false)"
    )


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
    allocator's own RAW-FALLBACK drop path needs psql (terminate-backend) and
    dropdb. These gates are harness-level: the tests below drive a REAL database,
    so they need real binaries. Nothing in the allocator's own contract needs
    them - the CREATEDB capability and every read-only query go through the
    instance's declared python, and those paths are covered by CPU-only stub
    tests here and in tests/test_pg_mode.py.
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

    # NOT a skip: an ephemeral request has exactly two outcomes (isolated, or a
    # non-zero refusal), so a non-ephemeral mode here is a contract violation to
    # report, never a reason to quietly stop exercising the B2 drop path.
    assert a["ALLOC_MODE"] == "ephemeral", (
        f"acquire exited 0 but did not return an ephemeral lease; got {a!r}"
    )

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

    assert a["ALLOC_MODE"] == "ephemeral", (
        f"acquire exited 0 but did not return an ephemeral lease; got {a!r}"
    )

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

    This is a pure-CPU test (no Postgres needed): the declared venv python answers
    `can-createdb` with true and exits rc=1 on `drop`, and a fake dropdb binary
    logs any invocation so we can assert it was NOT called.
    """
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    dropdb_log = tmp_path / "dropdb_calls.log"

    # Fake dropdb: logs any call (must NOT be invoked on genuine rc=1).
    fake_dropdb = bindir / "dropdb"
    fake_dropdb.write_text(
        '#!/bin/sh\necho "dropdb $*" >> "{log}"\n'.format(log=dropdb_log),
        encoding="utf-8",
    )
    fake_dropdb.chmod(0o755)

    # Declared venv python: answers can-createdb=true, exits rc=1 on `drop` to
    # simulate a genuine Odoo exp_drop failure (NOT the rc=10 venv sentinel).
    fake_python = _make_fake_venv_python(bindir, drop_rc=1)

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

    # Acquire an ephemeral lease (can-createdb answers true).
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_MODE"] == "ephemeral", "a role WITH CREATEDB must stay in ephemeral mode"

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
    """Return (env, log_path): a stubbed venv python that answers `can-createdb`
    with `true` and LOGS every odoo_db.py argv (so we can assert the drop command
    flags), exiting 0. CPU-only: no real Postgres, no real Odoo, and NO libpq
    client binary anywhere - the contract under test must not need one."""
    env, log, _py = _env_with_fake_venv(tmp_path, toml_text)
    return env, log


def _acquire_ephemeral_or_fail(env):
    """Acquire in ephemeral mode and REQUIRE it to have stayed ephemeral.

    A hard assertion on purpose: an ephemeral request has exactly two possible
    outcomes (isolated, or a non-zero refusal). Any pytest.skip here would let
    the through-Odoo drop coverage below evaporate silently the next time the
    mechanism changes - which is exactly how this defect stayed shippable.
    """
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, (
        f"ephemeral acquire must succeed with a stubbed can-createdb=true; "
        f"rc={p.returncode} stderr={p.stderr!r}"
    )
    assert a.get("ALLOC_MODE") == "ephemeral", (
        f"an ephemeral request must NEVER come back as anything else; got {a!r}"
    )
    return a


def test_drop_through_odoo_includes_db_port_when_set(tmp_path):
    """_drop_through_odoo must thread --db-port to odoo_db.py when the lease has one."""
    env, log = _make_drop_logger_env(tmp_path, INSTANCES_TOML_PORT)
    a = _acquire_ephemeral_or_fail(env)
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0, rel.stderr
    argv = log.read_text(encoding="utf-8")
    assert "drop" in argv, f"the drop must have gone through odoo_db.py; got {argv!r}"
    assert "--db-port" in argv and "5433" in argv, (
        f"drop command must include --db-port 5433 when the lease carries db_port; got {argv!r}"
    )


def test_drop_through_odoo_omits_db_port_when_empty(tmp_path):
    """No declared db_port -> the drop command must NOT carry --db-port (empty-omit)."""
    # INSTANCES_TOML has db_name_prefix but no db_port.
    env, log = _make_drop_logger_env(tmp_path, INSTANCES_TOML)
    a = _acquire_ephemeral_or_fail(env)
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0, rel.stderr
    argv = log.read_text(encoding="utf-8")
    assert "drop" in argv, f"the drop must have gone through odoo_db.py; got {argv!r}"
    assert "--db-port" not in argv, (
        f"drop command must OMIT --db-port when no db_port is declared; got {argv!r}"
    )


def test_drop_through_odoo_threads_the_declared_odoo_root(tmp_path):
    """A source checkout needs the repo root on sys.path for `import odoo` to
    resolve at all, so a declared odoo_root MUST reach odoo_db.py - otherwise
    every through-Odoo drop on a source instance takes the raw fallback it was
    written to avoid."""
    toml = INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"',
        'odoo_root = "/srv/odoo"\npython = "/srv/venv/bin/python"')
    env, log = _make_drop_logger_env(tmp_path, toml)
    a = _acquire_ephemeral_or_fail(env)
    assert _leases(env)[0]["odoo_root"] == "/srv/odoo", (
        "the lease must carry odoo_root - release/gc run after the caller is gone"
    )
    rel = _run(env, "release", a["ALLOC_TOKEN"])
    assert rel.returncode == 0, rel.stderr
    argv = log.read_text(encoding="utf-8")
    assert "--odoo-root /srv/odoo" in argv, (
        f"drop command must thread the declared odoo_root; got {argv!r}"
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
    assert p.returncode == 0, p.stderr
    assert a.get("ALLOC_MODE") == "ephemeral", (
        f"an ephemeral request must never come back as anything else; got {a!r}"
    )
    rel = _run(env, "release", a["ALLOC_TOKEN"], "--run-id", "run-B")
    assert rel.returncode != 0, "a foreign run must be refused"
    assert "run-A" in rel.stderr, f"refusal must name the owner run; stderr={rel.stderr!r}"
    assert len(_leases(env)) == 1, "a refused release must KEEP the lease"
    # The log also records the acquire's own can-createdb call, so assert on the
    # DROP specifically - the thing that must not have happened.
    argv = log.read_text(encoding="utf-8") if log.exists() else ""
    assert " drop " not in f" {argv} ", (
        f"a refused release must NOT invoke the drop (DB untouched); logged {argv!r}"
    )


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


# --------------------------------------------------------------------------- #
# L1.1/L1.2 - process-group teardown BEFORE the DB drop (the RAM-leak fix).
#
# Behavior contract protected here (NOT a code snapshot):
#   - `bind <token> --pid` upserts the live server pid onto the EXISTING lease
#     (the exclusive-lease path, so release/gc can find the process group), and
#     refuses an unknown token / a missing --pid.
#   - `release` stops the whole process GROUP (server master + its children)
#     BEFORE it drops the DB - active DB sessions block DROP DATABASE, so the
#     order is mandatory and must be observable.
#   - `gc` reaps the ttl-expired-but-process-still-alive ORPHAN: it stops the
#     group before reclaiming the lease (an upgrade from "wait for death").
#   - a legacy lease that carries NO pid releases cleanly - no crash, no signal.
# --------------------------------------------------------------------------- #
def _import_allocator():
    """Import allocator.py as a module so the ordering tests can monkeypatch the
    drop function in-process (the ledger tests still shell out, matching the rest
    of this file)."""
    spec = importlib.util.spec_from_file_location("allocator_under_test", ALLOC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _spawn_orphan_group(pidfile: Path, extra_argv=()):
    """Spawn a REAL process GROUP - a `setsid` session/group leader that forks a
    child, both alive - that is NOT a child of the test process. Because it is
    orphaned (reparented to init), killing the group makes the members disappear
    for real (no zombie held open by pytest), so `_pid_alive` flips to False and
    the ordering assertions are deterministic. Returns (leader_pid, child_pid);
    os.getpgid(leader) == leader, so os.killpg(leader, ...) reaps both.

    `extra_argv` is appended to the stand-in's command line verbatim. That is how
    a test makes the stand-in look like the server a lease actually names: the
    allocator will only signal a pid whose ownership it can PROVE, and a
    production launch is `setsid <py> <...>/odoo-bin -c <conf> -d <db>` (see
    allocator.py's `_ownership_proof`). A stand-in with no such command line and
    no `pid_started` fingerprint is - correctly - left alone.
    """
    launcher = textwrap.dedent(
        f"""\
        import os, time
        # Detach: fork + setsid so the leader is reparented to init, not to pytest.
        if os.fork() != 0:
            os._exit(0)                 # intermediary exits immediately
        os.setsid()                     # this process becomes session+group leader
        leader = os.getpid()
        child = os.fork()
        if child == 0:                  # grandchild: stays in the leader's group
            time.sleep(120)
            os._exit(0)
        with open({str(pidfile)!r}, "w") as fh:
            fh.write(f"{{leader}} {{child}}\\n")
        time.sleep(120)
        os._exit(0)
        """
    )
    # check=True waits for the intermediary (exits 0); the leader is now orphaned.
    subprocess.run([sys.executable, "-c", launcher, *[str(a) for a in extra_argv]],
                   check=True, timeout=30)
    deadline = time.time() + 5
    while time.time() < deadline:
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.02)
    leader, child = (int(x) for x in pidfile.read_text().split())
    return leader, child


def _reap(*pids):
    for pid in pids:
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, signal.SIGKILL)


# --- bind verb (ledger, shell-driven like the rest of the file) ------------- #
def test_bind_upserts_server_pid_onto_the_exclusive_lease(fixt):
    """An exclusive lease records no pid at acquire (only shared/--pid did before);
    `bind` upserts the live server pid onto that SAME lease slot so release/gc can
    stop its process group."""
    env, _, _ = fixt
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "excl_db")
    tok = a["ALLOC_TOKEN"]
    assert _leases(env)[0]["owner"]["pid"] is None, "exclusive acquire records no pid until bind"
    r = _run(env, "bind", tok, "--pid", str(os.getpid()))
    assert r.returncode == 0, f"bind must succeed on a known token; stderr={r.stderr!r}"
    leases = _leases(env)
    assert len(leases) == 1, "bind must NOT create a second lease row"
    assert leases[0]["owner"]["pid"] == os.getpid(), "bind must upsert the pid onto the exact lease"


def test_bind_refuses_unknown_token_and_missing_pid(fixt):
    env, _, _ = fixt
    _acquire(env, "--mode", "exclusive", "--db-name", "excl_db")
    bad = _run(env, "bind", "deadbeef" * 4, "--pid", str(os.getpid()))
    assert bad.returncode != 0, "bind must refuse an unknown token"
    _, a = _acquire(env, "--mode", "exclusive", "--db-name", "excl_db2")
    no_pid = _run(env, "bind", a["ALLOC_TOKEN"])  # --pid omitted
    assert no_pid.returncode != 0, "bind must refuse when --pid is missing"


# --- release stops the group BEFORE the drop (in-process, order observable) - #
def test_release_stops_process_group_before_dropping(tmp_path, monkeypatch):
    alloc = _import_allocator()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ODOO_AI_HOME", str(home))

    leader, child = _spawn_orphan_group(tmp_path / "grp.pids")
    try:
        assert alloc._pid_alive(leader) and alloc._pid_alive(child), "group must start alive"
        token = "ab" * 16
        now = int(time.time())
        # The fingerprint `bind`/`acquire --pid` record for real (_pid_owner_fields):
        # it is what PROVES this pid is still the process the lease named, which the
        # allocator requires before it will signal anything. This test is about the
        # teardown ORDER, so ownership is established the cheap way rather than by
        # dressing the stand-in up as an odoo-bin invocation.
        fingerprint = alloc._pid_fingerprint(leader)
        assert fingerprint, "test setup: must be able to fingerprint the spawned process"
        _seed_registry({"ODOO_AI_HOME": str(home)}, [{
            "token": token, "mode": "exclusive", "db_name": "leakdb",
            "drop_on_release": True, "python": "", "db_host": "localhost",
            "db_user": "odoo", "ports": [],
            "owner": {"host": socket.gethostname(), "pid": leader,
                      "pid_started": fingerprint,
                      "run_id": "run-A", "started_at": now},
            "ttl_s": 7200, "heartbeat_at": now,
        }])

        seen = {}

        def _recording_drop(lease, instances_path=None):
            # Snapshot liveness at the exact moment the drop fires: if the group
            # was stopped FIRST, both members are already gone here.
            seen["called"] = True
            seen["leader_alive"] = alloc._pid_alive(leader)
            seen["child_alive"] = alloc._pid_alive(child)
            return True

        monkeypatch.setattr(alloc, "_drop_through_odoo", _recording_drop)
        rc = alloc.cmd_release({"token": token, "run_id": "run-A"})

        assert rc == 0, "release must succeed"
        assert seen.get("called"), "the drop path must run (after the group stop)"
        assert seen["leader_alive"] is False, (
            "the server's process-group LEADER must be dead BEFORE the DB drop fires "
            "(a live session blocks DROP DATABASE)"
        )
        assert seen["child_alive"] is False, (
            "a child (worker/gevent/watchdog) must also be dead BEFORE the drop"
        )
    finally:
        _reap(child, leader)


# --- G4: gc must NOT touch a ttl-expired lease whose owner is PROVABLY alive - #
def test_gc_keeps_a_ttl_expired_but_provably_alive_orphan_group(tmp_path, monkeypatch):
    """This is the repurposed form of the pre-G4 test that asserted the OPPOSITE
    (gc stops + reclaims a ttl-expired-but-alive group) - that was the bug being
    fixed here, not protected behavior; see G4's fix-group report. With a REAL
    fingerprint recorded (mirroring what `acquire --pid`/`bind` now capture via
    `_pid_owner_fields`), gc must leave both the process group AND the lease
    alone, no matter how far past `ttl_s` the last heartbeat is."""
    alloc = _import_allocator()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ODOO_AI_HOME", str(home))

    leader, child = _spawn_orphan_group(tmp_path / "grp.pids")
    try:
        assert alloc._pid_alive(leader) and alloc._pid_alive(child)
        fingerprint = alloc._pid_fingerprint(leader)
        assert fingerprint, "test setup: must be able to fingerprint the real spawned process"
        token = "cd" * 16
        past = int(time.time()) - 100000
        _seed_registry({"ODOO_AI_HOME": str(home)}, [{
            "token": token, "mode": "exclusive", "db_name": "orphan_db",
            "drop_on_release": False, "python": "", "db_host": "localhost",
            "db_user": "odoo", "ports": [],
            "owner": {"host": socket.gethostname(), "pid": leader,
                      "pid_started": fingerprint,
                      "run_id": "run-A", "started_at": past},
            "ttl_s": 1, "heartbeat_at": past,  # long past ttl by time alone
        }])

        rc = alloc.cmd_gc({})
        assert rc == 0
        # Give gc a moment to have acted (or not); then assert nothing changed.
        time.sleep(0.3)
        assert alloc._pid_alive(leader), (
            "gc must NOT stop a ttl-expired orphan's group leader when it is "
            "provably still the same, alive process (G4)"
        )
        assert alloc._pid_alive(child), "gc must NOT stop the orphan's child either"
        reg = json.loads((home / "runtime" / "leases.json").read_text(encoding="utf-8"))
        assert len(reg["leases"]) == 1, (
            "gc must NOT reclaim a lease whose owner is provably alive, regardless of ttl"
        )
    finally:
        _reap(child, leader)


def test_gc_reclaims_a_ttl_expired_orphan_with_unverifiable_liveness(tmp_path, monkeypatch):
    """The residual case TTL still governs post-G4: a lease that never recorded
    a `pid_started` fingerprint (an older allocator, or one written before this
    fix) cannot be PROVEN alive even though its recorded pid happens to still be
    running - liveness is unprovable, so it falls back to ttl exactly like a
    different-host lease, and a long-expired ttl reclaims it (stopping the group
    first, per L1.2).

    The stand-in carries the command line a real spin-up launches
    (`<py> <...>/odoo-bin -c <db>-<port>.conf -d <db>`), which is what lets the
    allocator PROVE the pid is this lease's own server and stop it despite the
    missing fingerprint - see allocator.py `_ownership_proof`. Without that proof
    an alive pid is indistinguishable from a recycled bystander and is
    deliberately left running (guarded in test_allocator_signal_ownership.py);
    what this test protects is that a lease which HAS a provable runaway still
    gets both the process and the row reclaimed on ttl expiry."""
    alloc = _import_allocator()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ODOO_AI_HOME", str(home))

    odoo_bin = tmp_path / "src" / "odoo-bin"
    odoo_bin.parent.mkdir(parents=True, exist_ok=True)
    odoo_bin.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    leader, child = _spawn_orphan_group(
        tmp_path / "grp.pids",
        extra_argv=[odoo_bin, "-c", tmp_path / "orphan_db2-8069.conf", "-d", "orphan_db2"],
    )
    try:
        assert alloc._pid_alive(leader) and alloc._pid_alive(child)
        token = "ce" * 16
        past = int(time.time()) - 100000
        _seed_registry({"ODOO_AI_HOME": str(home)}, [{
            "token": token, "mode": "exclusive", "db_name": "orphan_db2",
            "drop_on_release": False, "python": "", "db_host": "localhost",
            "db_user": "odoo", "ports": [],
            # NO pid_started recorded - the unverifiable-liveness case.
            "owner": {"host": socket.gethostname(), "pid": leader,
                      "run_id": "run-A", "started_at": past},
            "ttl_s": 1, "heartbeat_at": past,
        }])

        rc = alloc.cmd_gc({})
        assert rc == 0
        deadline = time.time() + 5
        while time.time() < deadline and (alloc._pid_alive(leader) or alloc._pid_alive(child)):
            time.sleep(0.05)
        assert not alloc._pid_alive(leader), (
            "with no fingerprint to verify liveness, an expired ttl must still reclaim"
        )
        assert not alloc._pid_alive(child)
        reg = json.loads((home / "runtime" / "leases.json").read_text(encoding="utf-8"))
        assert reg["leases"] == [], "the unverifiable-liveness lease must be reclaimed on ttl expiry"
    finally:
        _reap(child, leader)


# --- legacy lease with NO pid releases cleanly (no crash, no signal) --------- #
def test_legacy_lease_without_pid_releases_without_signalling(tmp_path, monkeypatch):
    alloc = _import_allocator()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ODOO_AI_HOME", str(home))

    token = "ef" * 16
    now = int(time.time())
    _seed_registry({"ODOO_AI_HOME": str(home)}, [{
        "token": token, "mode": "exclusive", "db_name": "legacy",
        "drop_on_release": False, "python": "", "db_host": "localhost",
        "db_user": "odoo", "ports": [],
        # Pre-setsid legacy lease: no pid recorded at all.
        "owner": {"host": socket.gethostname(), "pid": None,
                  "run_id": "run-A", "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now,
    }])

    called = {"stop": False}
    monkeypatch.setattr(alloc, "_stop_group",
                        lambda *a, **k: called.__setitem__("stop", True))
    rc = alloc.cmd_release({"token": token, "run_id": "run-A"})
    assert rc == 0, "a legacy (no-pid) lease must release cleanly"
    assert called["stop"] is False, "no pid -> _stop_group must never be invoked (no signal sent)"
    reg = json.loads((home / "runtime" / "leases.json").read_text(encoding="utf-8"))
    assert reg["leases"] == [], "the legacy lease must be removed on release"


# --------------------------------------------------------------------------- #
# CS-C2 - worktree-correct addons path: --addons-path-override
#
# A per-module verification instance must load the worktree the code was
# written in, not the catalog's principal-checkout addons list. These tests
# protect the override CONTRACT (acquire --addons-path-override replaces the
# catalog value everywhere it is surfaced: ALLOC_ADDONS_PATH + the lease), the
# fail-loud behavior on a typo'd flag or a non-existent override directory, and
# the resolve_instances_path fallthrough diagnostics (Q2). All run the real
# script and assert on its actual stdout/stderr/exit code - not a re-
# implementation of the code under test.
# --------------------------------------------------------------------------- #
def test_addons_path_override_replaces_catalog_in_alloc_output(fixt, tmp_path):
    env, _, _ = fixt
    wt = tmp_path / "wt"
    wt.mkdir()
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    override = f"{wt},{catalog}"
    p, out = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", override,
    )
    assert p.returncode == 0, p.stderr
    assert out["ALLOC_ADDONS_PATH"] == override


def test_addons_path_override_persists_in_the_lease(fixt, tmp_path):
    env, _, _ = fixt
    wt = tmp_path / "wt"
    wt.mkdir()
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    override = f"{wt},{catalog}"
    p, _ = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", override,
    )
    assert p.returncode == 0, p.stderr
    leases = _leases(env)
    assert len(leases) == 1
    assert leases[0]["addons_path"] == override


def test_no_override_keeps_catalog_addons_byte_for_byte(fixt):
    """Regression fence - green before AND after the fix: with no override the
    catalog addons_path must pass through unchanged, byte for byte."""
    env, _, _ = fixt
    p, out = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert p.returncode == 0, p.stderr
    assert out["ALLOC_ADDONS_PATH"] == "/srv/odoo/addons,/srv/custom"
    leases = _leases(env)
    assert leases[0]["addons_path"] == "/srv/odoo/addons,/srv/custom"


def test_colon_delimited_override_is_normalized_to_commas(fixt, tmp_path):
    a_dir = tmp_path / "a"
    a_dir.mkdir()
    b_dir = tmp_path / "b"
    b_dir.mkdir()
    env, _, _ = fixt
    override = f"{a_dir}:{b_dir}"
    expected = f"{a_dir},{b_dir}"
    p, out = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", override,
    )
    assert p.returncode == 0, p.stderr
    # Asserting the exact expected value (not just "no colon present") matters:
    # an unrecognized flag falls through to the unrelated catalog value, which
    # also happens to contain no colon - a weaker assertion would pass
    # vacuously without the override ever being honored.
    assert out["ALLOC_ADDONS_PATH"] == expected
    leases = _leases(env)
    assert leases[0]["addons_path"] == expected


def test_unknown_flag_exits_non_zero(fixt):
    """The assertion that makes the whole fix falsifiable: a typo'd long flag
    must never silently fall into positionals and exit 0."""
    env, _, _ = fixt
    p = _run(env, "acquire", "--series", "17.0", "--addons-path-overide", "/tmp")
    assert p.returncode != 0
    assert "--addons-path-overide" in p.stderr


def test_alloc_output_and_lease_agree_under_override(fixt, tmp_path):
    """ALLOC_ADDONS_PATH (:527) and the lease's addons_path (:743) are separate
    literals - a one-sided patch must not pass this."""
    env, _, _ = fixt
    d = tmp_path / "wt"
    d.mkdir()
    p, out = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", str(d),
    )
    assert p.returncode == 0, p.stderr
    leases = _leases(env)
    assert out["ALLOC_ADDONS_PATH"] == leases[0]["addons_path"] == str(d)


def test_override_does_not_leak_across_leases(fixt, tmp_path):
    env, _, _ = fixt
    d = tmp_path / "wt"
    d.mkdir()
    p1, _ = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", str(d),
    )
    assert p1.returncode == 0, p1.stderr
    p2, out2 = _acquire(env, "--mode", "ephemeral", "--no-create", "--ports", "0")
    assert p2.returncode == 0, p2.stderr
    assert out2["ALLOC_ADDONS_PATH"] == "/srv/odoo/addons,/srv/custom"
    leases = _leases(env)
    assert len(leases) == 2
    assert sorted(lz["addons_path"] for lz in leases) == sorted(
        [str(d), "/srv/odoo/addons,/srv/custom"]
    )


def test_readonly_mode_honors_override(fixt, tmp_path):
    env, _, _ = fixt
    d = tmp_path / "wt"
    d.mkdir()
    p = _run(
        env, "acquire", "--series", "17.0", "--mode", "readonly",
        "--addons-path-override", str(d),
    )
    assert p.returncode == 0, p.stderr
    out = _parse_alloc(p.stdout)
    assert out["ALLOC_ADDONS_PATH"] == str(d)


def test_shared_mode_honors_override(fixt, tmp_path):
    env, _, _ = fixt
    d = tmp_path / "wt"
    d.mkdir()
    p = _run(
        env, "acquire", "--series", "17.0", "--mode", "shared",
        "--addons-path-override", str(d),
    )
    assert p.returncode == 0, p.stderr
    out = _parse_alloc(p.stdout)
    assert out["ALLOC_ADDONS_PATH"] == str(d)


def test_nonexistent_override_dir_is_refused_non_zero(fixt, tmp_path):
    env, _, _ = fixt
    missing = tmp_path / "does-not-exist"
    p = _run(
        env, "acquire", "--series", "17.0", "--mode", "ephemeral",
        "--no-create", "--ports", "0",
        "--addons-path-override", str(missing),
    )
    assert p.returncode != 0
    assert str(missing) in p.stderr


def test_first_addons_entry_wins_resolves_under_the_worktree(fixt, tmp_path):
    """The CONTRACT test: Odoo's addons-path is first-wins, so the fix means
    nothing unless the worktree's copy of the module is the FIRST entry."""
    env, _, _ = fixt
    wt = tmp_path / "wt"
    (wt / "mymod").mkdir(parents=True)
    (wt / "mymod" / "__manifest__.py").write_text("{}", encoding="utf-8")
    catalog = tmp_path / "catalog"
    (catalog / "mymod").mkdir(parents=True)
    (catalog / "mymod" / "__manifest__.py").write_text("{}", encoding="utf-8")
    override = f"{wt},{catalog}"
    p, out = _acquire(
        env, "--mode", "ephemeral", "--no-create", "--ports", "0",
        "--addons-path-override", override,
    )
    assert p.returncode == 0, p.stderr
    assert out["ALLOC_ADDONS_PATH"].split(",")[0] == str(wt)


def test_no_global_catalog_and_nonempty_project_catalog_emits_named_fallthrough(tmp_path):
    home = tmp_path / "home"
    home.mkdir()  # no instances.toml here -> the global catalog is absent
    project = tmp_path / "project"
    project_catalog_dir = project / ".odoo-ai"
    project_catalog_dir.mkdir(parents=True)
    (project_catalog_dir / "instances.toml").write_text(INSTANCES_TOML, encoding="utf-8")
    env = dict(os.environ)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)
    env.pop("ODOO_AI_INSTANCES", None)
    p = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "ephemeral", "--no-create", "--ports", "0"],
        capture_output=True, text=True, env=env, cwd=str(project),
    )
    assert p.returncode == 0, p.stderr
    assert "NO_GLOBAL_INSTANCE_CATALOG" in p.stderr
    assert "/odoo-setup" in p.stderr


def test_no_catalog_anywhere_emits_named_diagnostic(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    env = dict(os.environ)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)
    env.pop("ODOO_AI_INSTANCES", None)
    p = subprocess.run(
        [sys.executable, str(ALLOC), "acquire", "--series", "17.0",
         "--mode", "ephemeral", "--no-create", "--ports", "0"],
        capture_output=True, text=True, env=env, cwd=str(project),
    )
    assert p.returncode != 0
    assert "NO_INSTANCE_CATALOG" in p.stderr
    assert "/odoo-setup" in p.stderr


def test_python_and_shell_agree_on_instances_nonempty(tmp_path):
    """Byte-parity with resolve_instances.sh's own _instances_nonempty (a
    column-anchored `grep -qE '^\\[\\[instance\\]\\]'`) - the Python and shell
    halves must never disagree about which catalog file is authoritative."""
    alloc = _import_allocator()

    empty_toml = tmp_path / "empty.toml"
    empty_toml.write_text("# no instance table here\n", encoding="utf-8")

    flush_toml = tmp_path / "flush.toml"
    flush_toml.write_text("[[instance]]\nseries = \"17.0\"\n", encoding="utf-8")

    indented_toml = tmp_path / "indented.toml"
    indented_toml.write_text("  [[instance]]\nseries = \"17.0\"\n", encoding="utf-8")

    resolve_sh = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "resolve_instances.sh"
    for path, expected in (
        (empty_toml, False),
        (flush_toml, True),
        (indented_toml, False),
    ):
        py_result = alloc._instances_nonempty(str(path))
        assert py_result is expected, f"python side for {path.name}"
        sh = subprocess.run(
            ["bash", "-c", f'source "{resolve_sh}" && _instances_nonempty "{path}"'],
            capture_output=True, text=True,
        )
        sh_result = sh.returncode == 0
        assert sh_result is expected, f"shell side for {path.name}: {sh.stderr}"
        assert py_result == sh_result, f"python/shell disagree for {path.name}"


# --------------------------------------------------------------------------- #
# THE LOAD-BEARING INVARIANT: `--mode ephemeral` NEVER degrades
#
# An ephemeral request has exactly TWO outcomes:
#   (a) exit 0 with ALLOC_MODE=ephemeral and a fresh <prefix>_t_<hex8> db name, or
#   (b) a non-zero exit that writes NO lease and names the remedies.
# There is no third outcome. ALLOC_MODE=exclusive can only ever be produced by a
# caller that literally passed --mode exclusive. Before this contract existed the
# allocator answered "is this role allowed to create databases?" by shelling out
# to psql - so a host with no libpq client installed (Postgres in a container)
# was told its role lacks the privilege, and silently handed back an `exclusive`
# lease on the DECLARED, long-lived database: two concurrent callers wrote the
# same durable DB and neither was told.
# --------------------------------------------------------------------------- #

# Every way the capability question can fail, mapped to the exit it must produce.
# 6 = the role positively LACKS CREATEDB (a human fixes it with a grant).
# 7 = the capability is UNDETERMINABLE (a human fixes it with a declaration or by
#     starting the cluster). Never collapsed into 6: the remedies differ.
_EPHEMERAL_REFUSAL_SHAPES = {
    "role positively lacks CREATEDB": (dict(createdb="false"), None, 6),
    "cluster unreachable": (dict(createdb=None, createdb_rc=1), None, 7),
    "venv cannot import odoo": (dict(createdb=None, createdb_rc=10), None, 7),
    "capability answer is garbage": (dict(createdb="maybe"), None, 7),
    "no python declared": (None, None, 7),
    "tcp-only declared and role lacks CREATEDB": (
        dict(createdb="false"), 'db_run_mode = "tcp-only"', 6),
    "docker declared and capability undeterminable": (
        dict(createdb=None, createdb_rc=1),
        'db_run_mode = "docker"\ndb_container = "declared-elsewhere"', 7),
    # The CONNECTION shapes belong in this list, not in tests of their own: they are
    # two more ways the question can fail, and the invariant under test - an
    # ephemeral request is never answered with an exclusive lease - is the same one.
    # 8 and 9 stay distinct from 6 and 7 because the remedy differs again.
    "odoo cannot authenticate": (dict(preflight_rc=8), None, 8),
    "cluster did not answer": (dict(preflight_rc=9), None, 9),
}


def _refusal_env(tmp_path, shape):
    """Build a catalog+stub for one refusal shape. Returns (env, declared_db_name)."""
    stub, toml_extra, _exit = _EPHEMERAL_REFUSAL_SHAPES[shape]
    toml_text = INSTANCES_TOML
    if toml_extra:
        toml_text = toml_text.replace(
            'python = "/srv/venv/bin/python"', toml_extra + '\npython = "/srv/venv/bin/python"')
    if stub is None:
        # No `python` at all: the capability cannot be asked, so it is
        # UNDETERMINABLE - which must never be read as a factual "no".
        toml_text = toml_text.replace('python = "/srv/venv/bin/python"\n', "")
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        toml = tmp_path / "instances.toml"
        toml.write_text(toml_text, encoding="utf-8")
        env = _env(home, toml)
    else:
        env, _log, _py = _env_with_fake_venv(tmp_path, toml_text, **stub)
    return env, "odoo_17_0"


@pytest.mark.parametrize("shape", sorted(_EPHEMERAL_REFUSAL_SHAPES))
def test_ephemeral_request_never_yields_exclusive_lease(tmp_path, shape):
    """For EVERY way the CREATEDB question can fail, the acquire refuses loudly -
    it never answers an ephemeral request with an exclusive lease."""
    env, declared_db = _refusal_env(tmp_path, shape)
    expected_exit = _EPHEMERAL_REFUSAL_SHAPES[shape][2]

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")

    assert p.returncode == expected_exit, (
        f"[{shape}] must exit {expected_exit}; got {p.returncode}, stderr={p.stderr!r}"
    )
    assert "ALLOC_MODE=exclusive" not in p.stdout, (
        f"[{shape}] an ephemeral request must NEVER be answered with an exclusive "
        f"lease; stdout={p.stdout!r}"
    )
    assert declared_db not in p.stdout, (
        f"[{shape}] the DECLARED long-lived database must never be handed to an "
        f"ephemeral request; stdout={p.stdout!r}"
    )
    assert p.stderr.strip(), f"[{shape}] a refusal must say why"


@pytest.mark.parametrize("shape", sorted(_EPHEMERAL_REFUSAL_SHAPES))
def test_ephemeral_declared_db_name_never_leased_by_an_ephemeral_request(tmp_path, shape):
    """The registry - not stdout - is the authority: after EVERY refusal shape no
    lease exists at all, and in particular none on the declared db_name. Asserted
    on leases.json so a future change to the emit format cannot make this pass
    vacuously."""
    env, declared_db = _refusal_env(tmp_path, shape)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    assert p.returncode != 0, f"[{shape}] expected a refusal; stdout={p.stdout!r}"

    leases = _leases(env)
    assert leases == [], f"[{shape}] a refused acquire must write NO lease; got {leases!r}"
    assert declared_db not in {lz.get("db_name") for lz in leases}, (
        f"[{shape}] the declared database must never appear in a lease minted by an "
        "ephemeral request"
    )


def test_broken_native_client_does_not_change_the_ephemeral_outcome(tmp_path):
    """The false negative that caused the defect, replayed: every native client
    is present and BROKEN. The capability answer comes from the CLUSTER through
    the declared python, so a broken client binary is IRRELEVANT and the acquire
    must succeed as a fully isolated ephemeral lease.

    `dropdb` is stubbed broken rather than left off PATH on purpose. "dropdb is
    absent" would be a claim about the HOST - true on a developer box, false on a
    CI image that ships postgresql-client - so the same test would mean two
    different things depending on where it ran. Present-but-broken is the
    stricter case anyway: an absent binary cannot be consulted at all, while this
    one can be, and still must not change the verdict.
    """
    import re

    env, _log, _py = _env_with_fake_venv(tmp_path)
    bindir = tmp_path / "brokenbin"
    bindir.mkdir()
    for name, body in (("psql", "#!/bin/sh\nexit 127\n"),
                       ("dropdb", "#!/bin/sh\nexit 127\n"),
                       ("createuser", "#!/bin/sh\nexit 1\n")):
        (bindir / name).write_text(body, encoding="utf-8")
        (bindir / name).chmod(0o755)
    # Prepended, so these SHADOW any working client the image ships: whatever the
    # host has, the clients this acquire can reach are the broken ones above.
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, f"a broken psql must not affect the outcome; stderr={p.stderr!r}"
    assert a["ALLOC_MODE"] == "ephemeral"
    assert re.match(r"^odoo_17_0_t_[0-9a-f]{8}$", a["ALLOC_DB_NAME"]), (
        f"an ephemeral acquire must hand back a fresh throwaway db name; got "
        f"{a['ALLOC_DB_NAME']!r}"
    )
    assert a["ALLOC_DB_NAME"] != "odoo_17_0", "never the declared database"


def test_role_positively_without_createdb_exits_6_and_writes_no_lease(tmp_path):
    """Exit 6 is the role-lacks-the-privilege verdict, and its message must name
    every explicit option a caller has - it must not leave the caller to guess."""
    env, _log, _py = _env_with_fake_venv(tmp_path, createdb="false")
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    assert p.returncode == 6, f"got {p.returncode}, stderr={p.stderr!r}"
    assert _leases(env) == []
    low = p.stderr.lower()
    assert "createdb" in low, "the message must name the missing privilege"
    assert "--mode exclusive" in p.stderr, "it must name the explicit serialise alternative"
    assert "--no-create" in p.stderr, "it must name the probe-free alternative"


def test_undeterminable_createdb_capability_exits_7_and_writes_no_lease(tmp_path):
    """Exit 7 is UNDETERMINABLE, distinct from 6 so the remedy is unambiguous. It
    must name the series and the cause; 'I could not tell' is never read as 'no'."""
    env, _log, _py = _env_with_fake_venv(tmp_path, createdb=None, createdb_rc=1)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0")
    assert p.returncode == 7, f"got {p.returncode}, stderr={p.stderr!r}"
    assert _leases(env) == []
    assert "17.0" in p.stderr, f"the refusal must name the series; got {p.stderr!r}"
    assert "can-createdb" in p.stderr, "it must name the cause it could not resolve"


def test_no_create_keeps_ephemeral_and_asks_nothing(tmp_path):
    """--no-create means the caller creates no database, so CREATEDB is irrelevant
    to it: the capability must not even be asked, and the mode must stay ephemeral."""
    probe_log = tmp_path / "odoo_db_argv.log"
    env, log, _py = _env_with_fake_venv(tmp_path, createdb="false")
    assert log == probe_log

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
             "--ports", "0", "--no-create")
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, p.stderr
    assert a["ALLOC_MODE"] == "ephemeral", "--no-create must stay a probe-free path"
    assert not probe_log.exists(), (
        "with --no-create the capability must not be asked at all; the stub logged "
        f"{probe_log.read_text(encoding='utf-8') if probe_log.exists() else ''!r}"
    )
    assert _leases(env)[0]["drop_on_release"] is False


def test_acquire_has_no_mode_reassignment(tmp_path):
    """Source-level backstop for the exact SHAPE that produced the defect: inside
    cmd_acquire, `mode` is bound ONCE from the caller's request and never
    reassigned. An AST walk, not a string match, so no comment or message wording
    can make it pass."""
    import ast

    tree = ast.parse(ALLOC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "cmd_acquire")
    writes = []
    for node in ast.walk(fn):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "mode":
                writes.append(node.lineno)
    assert len(writes) == 1, (
        "cmd_acquire must bind `mode` exactly once (the caller's request) and never "
        f"rewrite it - a rewrite is how an ephemeral request silently became an "
        f"exclusive lease. Assignments found at lines {writes}"
    )


# --------------------------------------------------------------------------- #
# Drop safety: a drop that did not happen is NEVER reported as success
# --------------------------------------------------------------------------- #
def test_failed_raw_fallback_drop_keeps_the_lease(tmp_path):
    """The raw fallback's return value must be HONOURED. When the declared client
    surface cannot drop (tcp-only), release must fail, the lease must survive, and
    the filestore must be left alone. Discarding that return value deletes the
    lease while the database survives - an orphan nothing can find, since the only
    thing that could find it (reap-orphans) needs a lease to know it existed."""
    toml = INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"',
        'db_run_mode = "tcp-only"\npython = "/srv/venv/bin/python"')
    # can-createdb answers true (so we get a real ephemeral lease); the drop then
    # exits 10 = "venv unavailable", which is what sends it to the raw fallback.
    env, _log, _py = _env_with_fake_venv(tmp_path, toml, drop_rc=10)
    xdg = tmp_path / "xdg"
    env["XDG_DATA_HOME"] = str(xdg)

    a = _acquire_ephemeral_or_fail(env)
    filestore = xdg / "Odoo" / "filestore" / a["ALLOC_DB_NAME"]
    filestore.mkdir(parents=True)

    rel = _run(env, "release", a["ALLOC_TOKEN"])

    assert rel.returncode != 0, (
        f"a drop that did not happen must NOT be reported as a successful release; "
        f"stderr={rel.stderr!r}"
    )
    assert len(_leases(env)) == 1, (
        "the lease must be KEPT so gc can retry and the DB stays findable"
    )
    assert filestore.is_dir(), "the filestore must not be removed when nothing was dropped"
    assert "tcp-only" in rel.stderr, f"the error must name the declared mode; got {rel.stderr!r}"


def test_tcp_only_mode_never_invokes_a_client_binary(tmp_path):
    """db_run_mode=tcp-only is a declaration that this host has NO client surface.
    The allocator must honour it rather than trying a binary that happens to be on
    PATH - a client that works for a DIFFERENT cluster is the wrong-cluster shape."""
    toml = INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"',
        'db_run_mode = "tcp-only"\npython = "/srv/venv/bin/python"')
    env, _log, _py = _env_with_fake_venv(tmp_path, toml, drop_rc=10)
    calls = tmp_path / "client_calls.log"
    bindir = tmp_path / "clientbin"
    bindir.mkdir()
    for name in ("psql", "dropdb"):
        (bindir / name).write_text(
            '#!/bin/sh\necho "%s $*" >> "%s"\nexit 0\n' % (name, calls), encoding="utf-8")
        (bindir / name).chmod(0o755)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    a = _acquire_ephemeral_or_fail(env)
    _run(env, "release", a["ALLOC_TOKEN"])

    assert not calls.exists(), (
        "a tcp-only declaration must never reach a libpq client binary; got "
        f"{calls.read_text(encoding='utf-8') if calls.exists() else ''!r}"
    )


def test_legacy_lease_without_db_run_mode_still_drops_on_a_native_host(tmp_path):
    """Backward compatibility, scoped as narrowly as it can be: a lease minted
    before db_run_mode existed carries none, and on a host where BOTH client
    binaries are genuinely present the raw fallback must still work exactly as it
    did. Absent is not silently equated with tcp-only."""
    calls = tmp_path / "client_calls.log"
    bindir = tmp_path / "clientbin"
    bindir.mkdir()
    for name in ("psql", "dropdb"):
        (bindir / name).write_text(
            '#!/bin/sh\necho "%s $*" >> "%s"\nexit 0\n' % (name, calls), encoding="utf-8")
        (bindir / name).chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML, encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    token = "cd" * 16
    now = int(time.time())
    _seed_registry(env, [{
        "token": token, "mode": "ephemeral", "db_name": "odoo_17_0_t_0badcafe",
        "drop_on_release": True, "python": "",  # no venv -> raw fallback
        "db_host": "localhost", "db_user": "odoo", "db_port": "",
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "", "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }])

    rel = _run(env, "release", token)
    assert rel.returncode == 0, f"a pre-change lease must still release; stderr={rel.stderr!r}"
    assert _leases(env) == [], "a successful drop must remove the lease"
    logged = calls.read_text(encoding="utf-8")
    assert "odoo_17_0_t_0badcafe" in logged, (
        f"the raw fallback must have dropped the DB on a native host; got {logged!r}"
    )


def test_release_keeps_the_lease_when_the_raw_drop_command_fails(tmp_path):
    """Isolates the discarded-return-value defect, with no dependence on the
    acquire path: a seeded lease with no venv takes the raw fallback, and the
    `dropdb` command FAILS. The database therefore still exists, so the lease must
    still exist too. Deleting the lease here strands a database that nothing can
    ever find again - reap-orphans only knows a db was ephemeral by its NAME, and
    a caller that was told "released" never retries."""
    calls = tmp_path / "client_calls.log"
    bindir = tmp_path / "clientbin"
    bindir.mkdir()
    # psql (terminate-backend) succeeds; dropdb FAILS every attempt.
    (bindir / "psql").write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
    (bindir / "dropdb").write_text(
        '#!/bin/sh\necho "dropdb $*" >> "%s"\necho "dropdb: could not drop" >&2\nexit 1\n' % calls,
        encoding="utf-8")
    for name in ("psql", "dropdb"):
        (bindir / name).chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML, encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    xdg = tmp_path / "xdg"
    env["XDG_DATA_HOME"] = str(xdg)
    filestore = xdg / "Odoo" / "filestore" / "odoo_17_0_t_feedface"
    filestore.mkdir(parents=True)

    token = "ef" * 16
    now = int(time.time())
    _seed_registry(env, [{
        "token": token, "mode": "ephemeral", "db_name": "odoo_17_0_t_feedface",
        "drop_on_release": True, "python": "",  # no venv -> raw fallback
        "db_host": "localhost", "db_user": "odoo", "db_port": "",
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "", "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }])

    rel = _run(env, "release", token)

    assert calls.exists(), "test setup: the raw fallback must have been attempted"
    assert rel.returncode != 0, (
        "a failed drop must NOT be reported as a successful release; "
        f"stderr={rel.stderr!r}"
    )
    assert len(_leases(env)) == 1, (
        "the lease must be KEPT when the drop failed - the database is still there"
    )
    assert filestore.is_dir(), "the filestore must survive a drop that did not happen"


# --------------------------------------------------------------------------- #
# Probes are BOUNDED - an acquire that cannot answer must still RETURN.
#
# psycopg2 opens the connection with no libpq connect timeout (`connect_timeout`
# appears nowhere in Odoo's sql_db across the supported series), so a paused or
# firewalled cluster blocks INSIDE db_connect. An unbounded probe therefore never
# returns: no lease, no exit 6, no exit 7, no verdict at all - strictly worse
# than the wrong answer the probe replaced, because the caller learns nothing.
# --------------------------------------------------------------------------- #
def _hanging_venv_python(bindir, name="hang_python", subcommand="can-createdb"):
    """A stand-in venv interpreter that HANGS on one odoo_db.py subcommand.

    Spins rather than sleeping: `sleep` may be absent from a restricted PATH, and
    the process must genuinely outlive the bound for the bound to be what is
    measured.
    """
    bindir.mkdir(parents=True, exist_ok=True)
    py = bindir / name
    py.write_text(
        '#!/bin/sh\n'
        'if [ "$(basename "$1")" = "odoo_db.py" ] && [ "$2" = "%s" ]; then\n'
        '    while : ; do : ; done\n'
        'fi\n'
        'exec %s "$@"\n' % (subcommand, sys.executable),
        encoding="utf-8",
    )
    py.chmod(0o755)
    return py


def test_ephemeral_acquire_returns_a_verdict_when_the_createdb_probe_hangs(tmp_path):
    """An unresponsive CREATEDB probe must end in exit 7, not in a hang.

    The refusal is what makes `ephemeral` honest, so the refusal itself must be
    reachable: a probe with no bound means `acquire` never returns, the caller's
    tool call dies at the harness ceiling, and NOTHING is reported - not even
    "undeterminable".
    """
    py = _hanging_venv_python(tmp_path / "hangbin")
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"', f'python = "{py}"'), encoding="utf-8")
    env = _env(home, toml)
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "2"

    started = time.monotonic()
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    elapsed = time.monotonic() - started

    assert p.returncode == 7, (
        f"an unanswerable capability probe must REFUSE with exit 7; got {p.returncode}, "
        f"stderr={p.stderr!r}"
    )
    assert elapsed < 45, f"the probe must be bounded; acquire took {elapsed:.1f}s"
    assert "timed out" in p.stderr.lower(), (
        f"the reason must say the probe did not answer - never a factual 'no'; got {p.stderr!r}"
    )
    assert _leases(env) == [], "a refused acquire writes NO lease"


def test_the_probe_bound_is_the_same_knob_the_shell_half_uses(tmp_path):
    """ONE timeout policy, not two.

    pg_mode.sh bounds every shell-side probe with $ODOO_AI_PG_PROBE_TIMEOUT; the
    python half must read the SAME variable, or a host that tunes the bound gets
    it applied to half of its probes.
    """
    py = _hanging_venv_python(tmp_path / "hangbin")
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"', f'python = "{py}"'), encoding="utf-8")

    def _elapsed(secs):
        env = _env(home, toml)
        env["ODOO_AI_PG_PROBE_TIMEOUT"] = str(secs)
        started = time.monotonic()
        p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
                 timeout=90)
        assert p.returncode == 7, p.stderr
        return time.monotonic() - started

    short = _elapsed(2)
    long = _elapsed(9)
    assert long - short >= 3.0, (
        f"$ODOO_AI_PG_PROBE_TIMEOUT must govern the python-side probe too; 2s took "
        f"{short:.1f}s and 9s took {long:.1f}s"
    )


# --------------------------------------------------------------------------- #
# The UNDETERMINABLE message must diagnose correctly AND name the remedy.
# --------------------------------------------------------------------------- #
def test_undeterminable_createdb_names_the_record_env_remedy(tmp_path):
    """`import odoo` failing is an UNDECLARED `odoo_root`, not a broken venv.

    A source checkout is never pip-installed, so a catalog written before
    `odoo_root` existed makes odoo_db.py exit 10 - and its own message says "no
    venv?", which is FALSE: the venv is fine. Repeating that diagnosis and then
    offering only "re-dispatch with an explicit --mode" hides the one cheap fix,
    which is the very thing that records the missing key.
    """
    bindir = tmp_path / "sentinelbin"
    bindir.mkdir()
    py = bindir / "py10"
    py.write_text(
        '#!/bin/sh\n'
        'if [ "$(basename "$1")" = "odoo_db.py" ]; then\n'
        '    echo "odoo_db: cannot import odoo (no venv?) - no module named odoo" >&2\n'
        '    exit 10\n'
        'fi\n'
        'exec %s "$@"\n' % sys.executable,
        encoding="utf-8",
    )
    py.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"', f'python = "{py}"'), encoding="utf-8")
    env = _env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)

    assert p.returncode == 7, f"got {p.returncode}: {p.stderr!r}"
    assert "record-env" in p.stderr, (
        f"the ONE cheap fix must be named on this path too; got {p.stderr!r}"
    )
    assert "odoo_root" in p.stderr, (
        f"the message must name the fact that is actually missing, not blame the "
        f"venv; got {p.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# A compose-run instance declares no `python` at all - but it is a FIRST-CLASS
# supported run mode, so `--mode ephemeral` must not be permanently unreachable
# for it. When the catalog declares a libpq client surface, the SAME capability
# question is asked over that surface.
# --------------------------------------------------------------------------- #
INSTANCES_TOML_DOCKER_RUN = """\
[[instance]]
series = "18.0"
run_mode = "docker"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_18_0"
db_name_prefix = "odoo_18_0"
db_host = "db.example"
db_port = 5544
db_user = "odoo"
db_run_mode = "docker"
db_container = "pg-for-tests"
"""

INSTANCES_TOML_DOCKER_RUN_TCP_ONLY = INSTANCES_TOML_DOCKER_RUN.replace(
    'db_run_mode = "docker"\ndb_container = "pg-for-tests"\n', 'db_run_mode = "tcp-only"\n')


def _docker_client_env(tmp_path, toml_text, *, answer="t", rc=0, log=None):
    """A catalog with NO `python` and a stubbed `docker` on PATH, so the declared
    container is the only surface that can answer anything."""
    bindir = tmp_path / "clientbin"
    bindir.mkdir(parents=True, exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(
        '#!/bin/sh\n'
        + ('echo "$@" >> "%s"\n' % log if log is not None else "")
        + ('echo "%s"\n' % answer if answer is not None else "")
        + 'exit %d\n' % rc,
        encoding="utf-8",
    )
    docker.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(toml_text, encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    return env


def test_compose_run_instance_can_still_acquire_an_ephemeral_lease(tmp_path):
    """A `run_mode = "docker"` instance declares no `python` (compose launches
    it), so the interpreter probe can never answer for it. With a declared docker
    client surface the SAME live privilege query is asked inside the container -
    otherwise `--mode ephemeral` is permanently exit 7 for a first-class supported
    run mode, and isolation is unavailable by construction rather than by fact."""
    log = tmp_path / "docker_calls.log"
    env = _docker_client_env(tmp_path, INSTANCES_TOML_DOCKER_RUN, answer="t", log=log)

    p = _run(env, "acquire", "--series", "18.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    a = _parse_alloc(p.stdout)

    assert p.returncode == 0, (
        f"a compose-run instance with a declared client surface must be able to "
        f"acquire an isolated lease; got {p.returncode}, stderr={p.stderr!r}"
    )
    assert a["ALLOC_MODE"] == "ephemeral"
    assert a["ALLOC_DB_NAME"].startswith("odoo_18_0_t_")
    calls = log.read_text(encoding="utf-8")
    assert "pg-for-tests" in calls and "rolcreatedb" in calls, (
        f"the capability must be asked of the CLUSTER inside the declared "
        f"container; got:\n{calls}"
    )


def test_compose_run_instance_refuses_with_6_when_the_role_lacks_createdb(tmp_path):
    """The client-surface answer keeps False and undeterminable DISTINCT: a role
    that positively lacks CREATEDB is exit 6 (grant it), never exit 7."""
    env = _docker_client_env(tmp_path, INSTANCES_TOML_DOCKER_RUN, answer="f")
    p = _run(env, "acquire", "--series", "18.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    assert p.returncode == 6, f"got {p.returncode}: {p.stderr!r}"
    assert _leases(env) == [], "a refused acquire writes NO lease"


def test_no_interpreter_and_no_client_surface_says_why_and_what_to_do(tmp_path):
    """The residual dead end must be a STATED answer, not a silent one.

    No `python` and `db_run_mode = "tcp-only"` means nothing on this host can ask
    Postgres anything, so exit 7 is correct - but the message must name BOTH
    exhausted routes and the declaration that would open one, or the user has no
    way out.
    """
    env = _docker_client_env(tmp_path, INSTANCES_TOML_DOCKER_RUN_TCP_ONLY, answer=None)
    p = _run(env, "acquire", "--series", "18.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    assert p.returncode == 7, f"got {p.returncode}: {p.stderr!r}"
    err = p.stderr
    assert "python" in err and "db_run_mode" in err, (
        f"both exhausted routes must be named; got {err!r}"
    )
    assert "record-env" in err, f"the remedy must be named; got {err!r}"


# --------------------------------------------------------------------------- #
# A pre-change lease must not become PERMANENTLY un-droppable.
# --------------------------------------------------------------------------- #
def test_release_re_resolves_the_drop_surface_from_the_current_catalog(tmp_path):
    """A lease minted before `odoo_root`/`db_run_mode` existed must still drop.

    On a host whose Postgres is containerised (no libpq client at all), such a
    lease has: no odoo_root -> odoo_db.py exits 10 -> raw fallback -> no mode ->
    no client argv -> drop refused -> release exits 1 and re-appends the lease.
    `gc` repeats it, and reap-orphans excludes any DB a lease references: stuck
    forever, with `record-env` able to fix the catalog but never the lease. The
    CURRENT catalog is the live fact, so release must re-read it.
    """
    calls = tmp_path / "odoo_db_argv.log"
    py = _make_fake_venv_python(tmp_path / "fakebin", log=calls, drop_rc=0)
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    # The catalog HAS been repaired (this is what `45-venv.sh record-env` writes).
    toml.write_text(
        INSTANCES_TOML.replace('python = "/srv/venv/bin/python"',
                               f'python = "{py}"\nodoo_root = "/srv/odoo"\n'
                               'db_run_mode = "tcp-only"'),
        encoding="utf-8")
    env = _env(home, toml)

    token = "cd" * 16
    now = int(time.time())
    _seed_registry(env, [{
        # A PRE-CHANGE lease: none of python / odoo_root / db_run_mode exist on it.
        "token": token, "mode": "ephemeral", "series": "17.0",
        "db_name": "odoo_17_0_t_deadbeef", "drop_on_release": True,
        "db_host": "localhost", "db_user": "odoo", "db_port": "",
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "", "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }])

    rel = _run(env, "release", token, timeout=60)

    assert rel.returncode == 0, (
        f"a pre-change lease must be droppable once the catalog declares the facts; "
        f"stderr={rel.stderr!r}"
    )
    assert _leases(env) == [], "a successful drop removes the lease"
    logged = calls.read_text(encoding="utf-8")
    assert "drop odoo_17_0_t_deadbeef" in logged, (
        f"the drop must have gone THROUGH Odoo using the catalog's interpreter; got {logged!r}"
    )


def test_release_force_forget_never_loses_a_database_silently(tmp_path):
    """When nothing can drop the DB, the operator needs an explicit way out that
    LEAKS LOUDLY rather than one that pretends success.

    `--force-forget` removes the lease only after naming the database, the
    cluster it lives on, and what still has to be cleaned up by hand - so the
    escape can never be mistaken for a completed teardown.
    """
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    # Nothing on this host can reach Postgres: no python, no client surface.
    toml.write_text(INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"', 'db_run_mode = "tcp-only"'), encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = str(tmp_path / "empty-bin")  # no psql / dropdb anywhere

    token = "9a" * 16
    now = int(time.time())
    lease = {
        "token": token, "mode": "ephemeral", "series": "17.0",
        "db_name": "odoo_17_0_t_0badf00d", "drop_on_release": True, "python": "",
        "db_host": "localhost", "db_user": "odoo", "db_port": "",
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "", "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }
    _seed_registry(env, [lease])

    stuck = _run(env, "release", token, timeout=60)
    assert stuck.returncode != 0, "test setup: this lease must be undroppable here"
    assert len(_leases(env)) == 1, "test setup: the lease must be retained"

    forget = _run(env, "release", token, "--force-forget", timeout=60)
    assert forget.returncode == 0, f"the escape must succeed; stderr={forget.stderr!r}"
    assert _leases(env) == [], "--force-forget must remove the lease"
    assert "odoo_17_0_t_0badf00d" in forget.stderr, (
        f"the abandoned database must be NAMED so it can be cleaned up by hand; "
        f"got {forget.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# gc runs INSIDE acquire, and acquire has early returns after it.
# --------------------------------------------------------------------------- #
def test_gc_result_survives_an_exclusive_conflict_exit(tmp_path):
    """A lease whose DB gc already DROPPED must not still be listed.

    `acquire` gc's under the lock and then may return 3 (exclusive conflict) or 4
    (port pool exhausted) - both BEFORE the single registry write. The drop has
    already happened by then, so the registry keeps advertising a lease whose
    database is gone: `release` on it then fails, and every reader sees a
    resource that does not exist.
    """
    calls = tmp_path / "odoo_db_argv.log"
    py = _make_fake_venv_python(tmp_path / "fakebin", log=calls, drop_rc=0)
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"', f'python = "{py}"'), encoding="utf-8")
    env = _env(home, toml)

    now = int(time.time())
    host = socket.gethostname()
    _seed_registry(env, [
        {  # STALE ephemeral lease: gc will drop its DB and reclaim it.
            "token": "11" * 16, "mode": "ephemeral", "series": "17.0",
            "db_name": "odoo_17_0_t_abcdef01", "drop_on_release": True,
            "python": str(py), "db_host": "localhost", "db_user": "odoo", "db_port": "",
            "owner": {"host": host, "pid": None, "run_id": "", "started_at": 0},
            "ttl_s": 1, "heartbeat_at": 0,
        },
        {  # FRESH exclusive lease on the declared DB: forces the exit-3 path.
            "token": "22" * 16, "mode": "exclusive", "series": "17.0",
            "db_name": "odoo_17_0", "drop_on_release": False,
            "owner": {"host": host, "pid": None, "run_id": "other", "started_at": now},
            "ttl_s": 3600, "heartbeat_at": now,
        },
    ])

    p = _run(env, "acquire", "--series", "17.0", "--mode", "exclusive", "--ports", "0",
             timeout=60)
    assert p.returncode == 3, f"test setup: expected an exclusive conflict; got {p.returncode}"
    assert calls.exists() and "drop odoo_17_0_t_abcdef01" in calls.read_text(encoding="utf-8"), (
        "test setup: gc must have dropped the stale lease's database"
    )

    remaining = {lz["db_name"] for lz in _leases(env)}
    assert "odoo_17_0_t_abcdef01" not in remaining, (
        "a lease whose database gc already dropped must not survive the early "
        f"return; registry still lists {sorted(remaining)}"
    )


# --------------------------------------------------------------------------- #
# Secrets never travel on argv.
# --------------------------------------------------------------------------- #
def test_no_postgres_question_puts_the_password_on_the_command_line(tmp_path):
    """A password on argv is world-readable in `ps`.

    The docker client arm already avoids this deliberately (`docker exec -e
    PGPASSWORD` forwards it by NAME), so the interpreter arm applying the opposite
    standard is an inconsistency, not a trade-off - and it is free to fix:
    odoo_db.py already reads ODOO_PG_PASSWORD from its environment, which a child
    process inherits.
    """
    log = tmp_path / "odoo_db_argv.log"
    env, _log, _py = _env_with_fake_venv(tmp_path, log=log, createdb="true")
    env["ODOO_PG_PASSWORD"] = "s3cret-on-argv"

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    assert p.returncode == 0, p.stderr
    logged = log.read_text(encoding="utf-8")
    assert "can-createdb" in logged, f"test setup: the probe must have run; got {logged!r}"
    assert "--db-password" not in logged, (
        f"the password flag must not be on argv; got {logged!r}"
    )
    assert "s3cret-on-argv" not in logged, (
        f"the password value must never appear on argv; got {logged!r}"
    )


# --------------------------------------------------------------------------- #
# `can-createdb` - ONE ladder, asked from anywhere.
#
# The setup-time report used to invoke odoo_db.py directly, which duplicated route
# 1 of the ladder in shell and could not reach route 2 at all - so a compose-run
# instance (no `python`) got no answer, from the very command whose job is to tell
# the user whether isolation is available.
# --------------------------------------------------------------------------- #
def test_can_createdb_reports_the_same_verdict_acquire_would_refuse_on(tmp_path):
    """The read-only query and the acquire gate must share ONE ladder.

    Two implementations of "may this role create a database" drift the moment only
    one is exercised, and the drifted one is what a human reads before deciding
    whether their setup works.
    """
    env = _docker_client_env(tmp_path, INSTANCES_TOML_DOCKER_RUN, answer="t")
    ok = _run(env, "can-createdb", "--series", "18.0", timeout=60)
    assert ok.returncode == 0, f"a positive answer must exit 0; {ok.stderr!r}"
    assert "CREATEDB=true" in ok.stdout, ok.stdout

    env_no = _docker_client_env(tmp_path / "no", INSTANCES_TOML_DOCKER_RUN, answer="f")
    no = _run(env_no, "can-createdb", "--series", "18.0", timeout=60)
    assert no.returncode == 6, (
        f"a positive NO must exit 6 - the same code acquire refuses with; got {no.returncode}"
    )
    assert "CREATEDB=false" in no.stdout, no.stdout

    env_un = _docker_client_env(
        tmp_path / "un", INSTANCES_TOML_DOCKER_RUN_TCP_ONLY, answer=None)
    un = _run(env_un, "can-createdb", "--series", "18.0", timeout=60)
    assert un.returncode == 7, (
        f"undeterminable must exit 7 and stay DISTINCT from a factual no; got {un.returncode}"
    )
    assert "CREATEDB=undeterminable" in un.stdout, un.stdout
    assert "CREATEDB_WHY=" in un.stdout, (
        f"the reason must be machine-readable, not only prose on stderr; {un.stdout!r}"
    )


def test_can_createdb_writes_no_lease(tmp_path):
    """It is a QUESTION, not an allocation: nothing may be reserved by asking."""
    env = _docker_client_env(tmp_path, INSTANCES_TOML_DOCKER_RUN, answer="t")
    _run(env, "can-createdb", "--series", "18.0", timeout=60)
    assert _leases(env) == [], "a read-only query must never write a lease"


# --------------------------------------------------------------------------- #
# The drop ladder must tell "never attempted" from "attempted and failed".
#
# Those two used to arrive as the SAME exit code, so the allocator could not tell
# a connection that never reached the database from a DROP DATABASE that genuinely
# failed - and they demand OPPOSITE handling. The pair below asserts the
# DISTINCTION, which neither test can assert alone: this one proves the connection
# case now reaches the declared surface, and its sibling
# `test_ephemeral_release_does_not_fallback_on_genuine_drop_failure` proves a
# genuine failure still never does.
# --------------------------------------------------------------------------- #
INSTANCES_TOML_DOCKER_SURFACE = INSTANCES_TOML.replace(
    'python = "/srv/venv/bin/python"',
    'db_run_mode = "docker"\ndb_container = "pg-for-tests"\npython = "/srv/venv/bin/python"')


def _venv_plus_docker_env(tmp_path, toml_text, *, docker_log=None, docker_rc=0,
                          docker_out="1", **stub):
    """(env, docker_log, py): a catalog declaring BOTH an interpreter and a docker
    client surface, with both constructed as stubs.

    This is the observed host class: Postgres in a container, no libpq client on
    the host, and a venv that can talk to it over TCP. Both routes therefore exist,
    which is what makes "which route answered" observable at all.
    """
    log = docker_log or (tmp_path / "docker_calls.log")
    bindir = tmp_path / "clientbin"
    bindir.mkdir(parents=True, exist_ok=True)
    docker = bindir / "docker"
    # `docker_out` is what the container-local client PRINTS: for the existence
    # query a row means the database is there, and empty output means it is not.
    docker.write_text(
        '#!/bin/sh\necho "$@" >> "%s"\n%sexit %d\n' % (
            log, ('echo "%s"\n' % docker_out) if docker_out else "", docker_rc),
        encoding="utf-8")
    docker.chmod(0o755)
    py = _make_fake_venv_python(tmp_path / "fakebin", **stub)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(toml_text.replace(
        'python = "/srv/venv/bin/python"', 'python = "%s"' % py), encoding="utf-8")
    env = _env(home, toml)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    return env, log, py


@pytest.mark.parametrize("drop_rc,label", [(8, "authentication refused"),
                                           (9, "cluster unreachable")])
def test_drop_falls_back_to_the_declared_surface_when_the_through_odoo_drop_cannot_connect(
        tmp_path, drop_rc, label):
    """A connection failure means DROP DATABASE was never issued.

    On the observed host class the container-local client CAN drop the database
    while the host-side TCP connection cannot authenticate at all. Reading that
    refusal as a genuine exp_drop failure keeps the lease forever, and
    reap-orphans excludes any database a lease references - so the lease and its
    database become permanently unreclaimable from both ends.
    """
    env, docker_log, _py = _venv_plus_docker_env(
        tmp_path, INSTANCES_TOML_DOCKER_SURFACE, drop_rc=drop_rc, exists="false")

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    a = _parse_alloc(p.stdout)
    assert p.returncode == 0, f"[{label}] test setup: acquire must succeed; {p.stderr!r}"

    rel = _run(env, "release", a["ALLOC_TOKEN"], timeout=60)
    assert rel.returncode == 0, (
        f"[{label}] the declared surface dropped it, so the release must succeed; "
        f"stderr={rel.stderr!r}"
    )
    assert _leases(env) == [], f"[{label}] a successful drop must remove the lease"
    calls = docker_log.read_text(encoding="utf-8")
    assert "dropdb" in calls and a["ALLOC_DB_NAME"] in calls, (
        f"[{label}] the declared client surface must have been consulted; got:\n{calls}"
    )


@pytest.mark.parametrize("arm,stub,lease_python", [
    ("connection refused", dict(drop_rc=8), True),
    ("venv unavailable", dict(drop_rc=10), True),
    ("no interpreter at all", dict(drop_rc=0), False),
])  # ids name the fallback ARM, so a fourth arm has to be added here to be covered
def test_client_drop_fallback_refuses_a_lease_that_does_not_name_a_throwaway_db(
        tmp_path, arm, stub, lease_python):
    """The client route is equivalent to the through-Odoo one for a THROWAWAY
    database only, so the gate is a precondition rather than a hope.

    A hand-edited or corrupted lease naming the declared, long-lived database must
    never reach a client-side drop. Parametrised over EVERY fallback arm, so a
    fourth arm added later cannot silently bypass the gate.
    """
    toml_text = INSTANCES_TOML_DOCKER_SURFACE
    if not lease_python:
        # The drop surface is re-resolved from the CURRENT catalog on every attempt,
        # so the interpreter has to be absent THERE too for this arm to be reached.
        toml_text = toml_text.replace('python = "/srv/venv/bin/python"\n', "")
    env, docker_log, py = _venv_plus_docker_env(tmp_path, toml_text, **stub)

    token = "ab" * 16
    now = int(time.time())
    _seed_registry(env, [{
        "token": token, "mode": "ephemeral", "series": "17.0",
        # The DECLARED database, not a throwaway - the shape the gate refuses.
        "db_name": "odoo_17_0", "drop_on_release": True,
        "python": str(py) if lease_python else "",
        "odoo_root": "", "db_run_mode": "docker", "db_container": "pg-for-tests",
        "db_host": "localhost", "db_user": "odoo", "db_port": "",
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "",
                  "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }])

    rel = _run(env, "release", token, timeout=60)

    calls = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert "dropdb" not in calls, (
        f"[{arm}] a lease naming the declared database must never reach a "
        f"client-side drop; got:\n{calls}"
    )
    assert rel.returncode != 0, f"[{arm}] a refused drop must not report success"
    assert len(_leases(env)) == 1, f"[{arm}] the lease must be kept"


def test_createdb_ladder_stops_on_a_proven_auth_denial_instead_of_asking_another_surface(
        tmp_path):
    """A capability answer from a DIFFERENT connection is not extra information.

    The container-local surface answers `true` on a host whose builds cannot
    authenticate over TCP at all, because a stock Postgres image trusts its own
    loopback. Letting that overrule the route the build actually takes is
    answering the wrong question confidently - so once route 1 PROVES the refusal,
    route 2 must not even be invoked.
    """
    env, docker_log, _py = _venv_plus_docker_env(
        tmp_path, INSTANCES_TOML_DOCKER_SURFACE, createdb=None, createdb_rc=8)

    p = _run(env, "can-createdb", "--series", "17.0", timeout=60)

    assert p.returncode == 8, (
        f"a proven authentication refusal must propagate, not become a capability "
        f"answer; got {p.returncode}, stderr={p.stderr!r}"
    )
    assert "CREATEDB=true" not in p.stdout, (
        f"a capability verdict must never be emitted here; got {p.stdout!r}"
    )
    calls = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert calls.strip() == "", (
        f"the second surface must not be consulted at all; got:\n{calls}"
    )


def test_db_preflight_never_emits_createdb_true_alongside_db_auth_denied(tmp_path):
    """The contradiction itself, asserted on the emitted keys rather than wording.

    A report that says "authentication refused" and "may create databases" in the
    same breath tells the reader both that the build cannot start and that it can.
    """
    env, docker_log, _py = _venv_plus_docker_env(
        tmp_path, INSTANCES_TOML_DOCKER_SURFACE, preflight_rc=8)

    p = _run(env, "db-preflight", "--series", "17.0", timeout=60)
    keys = dict(
        line.partition("=")[::2] for line in p.stdout.splitlines() if "=" in line)

    assert p.returncode == 8, f"got {p.returncode}, stderr={p.stderr!r}"
    assert keys.get("DB_AUTH") == "denied", p.stdout
    assert "CREATEDB" not in keys, (
        f"no capability verdict may accompany a proven refusal; got {p.stdout!r}"
    )
    calls = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert calls.strip() == "", f"the capability ladder must not run at all:\n{calls}"


def test_db_preflight_reports_both_facts_when_the_connection_works(tmp_path):
    """Both facts, one call: the report must stay USEFUL, not just safe."""
    env, _log, _py = _venv_plus_docker_env(
        tmp_path, INSTANCES_TOML_DOCKER_SURFACE, preflight_rc=0, createdb="true")
    p = _run(env, "db-preflight", "--series", "17.0", timeout=60)
    assert p.returncode == 0, f"got {p.returncode}, stderr={p.stderr!r}"
    assert "DB_AUTH=ok" in p.stdout and "CREATEDB=true" in p.stdout, p.stdout
    assert _leases(env) == [], "a read-only query must never write a lease"


# --------------------------------------------------------------------------- #
# `ABANDONED` is a claim about the cluster, so it must be EARNED.
#
# A build that crashed before creating anything leaves a lease whose drop can only
# ever "fail" - un-releasable from one end, while reap-orphans cannot see the
# database from the other. Classifying existence before naming anything closes it.
# --------------------------------------------------------------------------- #
_FORGET_STATES = {
    # existence answer -> (stub kwargs, toml, expected emitted key, forbidden keys)
    "database is there": (dict(drop_rc=1, exists="true"), INSTANCES_TOML,
                          "ALLOC_ABANDONED_DB",
                          ("ALLOC_FORGOTTEN_DB", "ALLOC_UNVERIFIED_DB")),
    "database never existed": (dict(drop_rc=1, exists="false"), INSTANCES_TOML,
                               "ALLOC_FORGOTTEN_DB",
                               ("ALLOC_ABANDONED_DB", "ALLOC_UNVERIFIED_DB")),
    "existence cannot be determined": (
        dict(drop_rc=1), INSTANCES_TOML.replace(
            'python = "/srv/venv/bin/python"',
            'db_run_mode = "tcp-only"\npython = "/srv/venv/bin/python"'),
        "ALLOC_UNVERIFIED_DB",
        ("ALLOC_ABANDONED_DB", "ALLOC_FORGOTTEN_DB")),
}


@pytest.mark.parametrize("state", sorted(_FORGET_STATES))
def test_force_forget_names_exactly_what_it_left_behind(tmp_path, state):
    """--force-forget must never claim a cluster fact nothing observed.

    Three outcomes, one per existence answer, asserted on the emitted KEY so a
    reworded message cannot make this pass and a renamed key cannot make it pass
    silently either.
    """
    stub, toml_text, expected, forbidden = _FORGET_STATES[state]
    env, _log, _py = _env_with_fake_venv(tmp_path, toml_text, **stub)

    a = _acquire_ephemeral_or_fail(env)
    forget = _run(env, "release", a["ALLOC_TOKEN"], "--force-forget", timeout=60)

    assert forget.returncode == 0, (
        f"[{state}] the escape must succeed; stderr={forget.stderr!r}")
    assert _leases(env) == [], f"[{state}] --force-forget must remove the lease"
    assert expected in forget.stdout, (
        f"[{state}] expected {expected}; got stdout={forget.stdout!r} "
        f"stderr={forget.stderr!r}"
    )
    for key in forbidden:
        assert key not in forget.stdout, (
            f"[{state}] {key} must NOT be emitted; got {forget.stdout!r}")
    assert a["ALLOC_DB_NAME"] in forget.stderr, (
        f"[{state}] whatever the outcome, the database must be NAMED for a human")


def test_release_succeeds_when_the_database_is_provably_absent(tmp_path):
    """The other half of the un-releasable-lease leak.

    A build that crashed before creating its database leaves a lease whose drop
    always "fails", so the plain release path kept it forever and gc retried it
    forever. Once absence is PROVEN there was nothing to tear down, and the release
    is clean - no --force-forget, no leaked lease.
    """
    env, _log, _py = _env_with_fake_venv(tmp_path, drop_rc=1, exists="false")
    a = _acquire_ephemeral_or_fail(env)

    rel = _run(env, "release", a["ALLOC_TOKEN"], timeout=60)

    assert rel.returncode == 0, (
        f"a database that does not exist leaves nothing to drop; stderr={rel.stderr!r}"
    )
    assert _leases(env) == [], "the lease must not survive a teardown with nothing to do"
    assert "ALLOC_FORGOTTEN_DB" in rel.stdout, (
        f"the outcome must be machine-readable; got {rel.stdout!r}")


def test_a_provably_absent_database_takes_its_filestore_with_it(tmp_path):
    """The filestore is a SEPARATE object with its own lifetime, and this path is
    reached exactly when the database vanished without Odoo dropping it - deleting
    a container's volume takes every ephemeral database and leaves every filestore
    directory behind.

    Releasing the lease here puts that directory beyond BOTH reapers at once: `gc`
    finds work through leases and the lease is gone, `reap-orphans` finds work
    through pg_database and there is no row. So one directory per run would leak
    forever, with nothing left that references it - while the message says NOTHING
    was left behind.
    """
    env, _log, _py = _env_with_fake_venv(tmp_path, drop_rc=1, exists="false")
    xdg = tmp_path / "xdg"
    env["XDG_DATA_HOME"] = str(xdg)

    a = _acquire_ephemeral_or_fail(env)
    filestore = xdg / "Odoo" / "filestore" / a["ALLOC_DB_NAME"]
    filestore.mkdir(parents=True)
    (filestore / "checksum").mkdir()
    (filestore / "checksum" / "blob").write_bytes(b"attachment bytes")

    rel = _run(env, "release", a["ALLOC_TOKEN"], timeout=60)

    assert rel.returncode == 0, f"stderr={rel.stderr!r}"
    assert _leases(env) == [], "the lease must be released on a proven absence"
    assert not filestore.exists(), (
        "the filestore outlived the only two things that could ever have found it; "
        f"{filestore} still holds {sorted(p.name for p in filestore.iterdir())}")
    assert "ALLOC_FORGOTTEN_DB" in rel.stdout


def test_release_keeps_the_lease_when_existence_cannot_be_determined(tmp_path):
    """"We could not look" is never "it is not there".

    Collapsing the two would release a lease whose database is still on disk, and
    nothing could then find it: reap-orphans knows a database was a throwaway only
    by its NAME, and the caller was told the teardown succeeded.
    """
    toml = INSTANCES_TOML.replace(
        'python = "/srv/venv/bin/python"',
        'db_run_mode = "tcp-only"\npython = "/srv/venv/bin/python"')
    env, _log, _py = _env_with_fake_venv(tmp_path, toml, drop_rc=1)
    a = _acquire_ephemeral_or_fail(env)

    rel = _run(env, "release", a["ALLOC_TOKEN"], timeout=60)

    assert rel.returncode != 0, (
        f"an unverifiable teardown must not be reported as done; stderr={rel.stderr!r}")
    assert len(_leases(env)) == 1, "the lease must be kept so gc can retry"


# --------------------------------------------------------------------------- #
# Authentication is a precondition of every BUILD verb, so the gate covers every
# mode that will build - and refuses only on a PROVEN negative.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", ["ephemeral", "exclusive"])
@pytest.mark.parametrize("preflight_rc,expected", [(8, 8), (9, 9)])
def test_acquire_refuses_when_odoo_cannot_authenticate_and_writes_no_lease(
        tmp_path, mode, preflight_rc, expected):
    """Odoo opens its maintenance-database connection for EVERY `-d <name>` run.

    So a refused connection kills an `exclusive` build exactly as it kills an
    ephemeral one, and handing out a lease first only moves the failure to a raw
    traceback mid-build with a database half-created. Parametrised over both
    building modes and both proven negatives.
    """
    env, _log, _py = _env_with_fake_venv(tmp_path, preflight_rc=preflight_rc)
    token = "cc" * 16
    now = int(time.time())
    _seed_registry(env, [{
        "token": token, "mode": "shared", "series": "17.0", "db_name": "other_db",
        "drop_on_release": False, "ports": [],
        "owner": {"host": socket.gethostname(), "pid": None, "run_id": "",
                  "started_at": now},
        "ttl_s": 3600, "heartbeat_at": now,
    }])
    registry = Path(env["ODOO_AI_HOME"]) / "runtime" / "leases.json"
    before = registry.read_bytes()

    p = _run(env, "acquire", "--series", "17.0", "--mode", mode, "--ports", "0",
             timeout=60)

    assert p.returncode == expected, (
        f"[{mode}] got {p.returncode}, stderr={p.stderr!r}")
    assert registry.read_bytes() == before, (
        f"[{mode}] a refused acquire must leave the registry byte-unchanged")
    assert p.stderr.strip(), f"[{mode}] a refusal must say why"


@pytest.mark.parametrize("mode", ["ephemeral", "exclusive"])
def test_acquire_never_blocks_on_an_undeterminable_authentication_state(tmp_path, mode):
    """UNDETERMINABLE never blocks - only a PROVEN negative does.

    Refusing here would refuse on every host that has not finished declaring its
    environment, which turns a safety gate into an outage. The three states stay
    distinct precisely so this one can be non-blocking.
    """
    env, _log, _py = _env_with_fake_venv(tmp_path, preflight_rc=1)
    p = _run(env, "acquire", "--series", "17.0", "--mode", mode, "--ports", "0",
             timeout=60)
    assert p.returncode == 0, (
        f"[{mode}] an unanswerable question must not refuse the acquire; got "
        f"{p.returncode}, stderr={p.stderr!r}"
    )
    assert len(_leases(env)) == 1, f"[{mode}] the lease must be written"


@pytest.mark.parametrize("mode", ["readonly", "shared"])
def test_the_auth_gate_is_skipped_for_a_mode_that_builds_nothing(tmp_path, mode):
    """A lease that opens no database must not be gated on one.

    `readonly` attaches to something already running and `shared` never creates,
    so asking the question there would refuse an attach for a reason that cannot
    affect it. The stub records every call, so the skip is proved rather than
    inferred.
    """
    log = tmp_path / "odoo_db_argv.log"
    env, _log, _py = _env_with_fake_venv(tmp_path, log=log, preflight_rc=8)
    p = _run(env, "acquire", "--series", "17.0", "--mode", mode, "--ports", "0",
             timeout=60)
    assert p.returncode == 0, f"[{mode}] got {p.returncode}, stderr={p.stderr!r}"
    logged = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "preflight" not in logged, (
        f"[{mode}] the question must not even be asked; the stub logged {logged!r}")
    _assert_the_gate_could_have_been_asked(env, log, mode)


def test_no_create_skips_the_auth_gate_too(tmp_path):
    """--no-create declares that this caller opens no database at all."""
    log = tmp_path / "odoo_db_argv.log"
    env, _log, _py = _env_with_fake_venv(tmp_path, log=log, preflight_rc=8)
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             "--no-create", timeout=60)
    assert p.returncode == 0, f"got {p.returncode}, stderr={p.stderr!r}"
    logged = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "preflight" not in logged, (
        f"with --no-create nothing may be asked; the stub logged {logged!r}")
    _assert_the_gate_could_have_been_asked(env, log, "--no-create")


def _assert_the_gate_could_have_been_asked(env, log, case):
    """POSITIVE CONTROL for the three "must not even be asked" assertions.

    Each of those reads the argv log only `if log.exists()`, and for a skipped gate
    the file is never created - so the assertion holds TRIVIALLY. A fixture
    regression that stopped the allocator resolving the declared interpreter at all
    would then report "the gate is correctly skipped" on a host where it could never
    have been asked in the first place. So: run a mode that MUST ask, against the
    same env and the same stub, and prove the recording works.
    """
    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--ports", "0",
             timeout=60)
    assert p.returncode == 8, (
        "[{c}] control: a building mode must reach the gate this fixture pins to "
        "denied; got {rc}, stderr={err!r}".format(c=case, rc=p.returncode, err=p.stderr))
    assert log.exists() and "preflight" in log.read_text(encoding="utf-8"), (
        "[{c}] control: the stub never recorded a preflight even for a mode that "
        "must ask, so the skip assertion above proved nothing".format(c=case))
