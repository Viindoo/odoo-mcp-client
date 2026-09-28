"""Behavior tests: rows the CURRENT allocator writes are safe under the RELEASED one.

The registry is machine-global and shared by every session on the host, and a
session keeps running the allocator of the plugin version it started with. So the
allocator a still-running older session executes reads - and, on every acquire,
SWEEPS - the rows this version writes. That older allocator (master) judges a row
by `owner.pid` + `owner.pid_started` compared with `==` against the ambient
`ps -o lstart=`, and by `ttl_s` against `heartbeat_at`; a row it condemns is
deleted and, with drop_on_release, its database is dropped.

The contract, stated as behavior - for rows written by THIS allocator:
  - a lease bound to a LIVE server pid is not condemned by master;
  - a pid-less, session-anchored lease whose session heartbeats is not condemned
    by master, even after master's own default TTL would have elapsed;
  - a parked lease is not condemned by master;
  - a lease whose bound server DIED while its session lives on is not condemned
    by master once any current-version write (the session heartbeat, another
    session's acquire) has run - and it can still be parked;
  - master's acquire (its machine-wide sweep) reclaims none of them and drops
    nothing;
  - the build facts this version records on a row (`server_wide_modules`,
    `built`) survive every verb master runs on it, and a row master wrote
    without them reads here as "nothing declared, nothing recorded" (the last
    section, which runs against master's CURRENT allocator whatever it is).

Master's allocator is taken from git (`git show master:<path>`) into a temp dir at
test time; the tests skip when git or the master branch is unavailable. Every
database interaction goes through the stub interpreter of `World`, which only
LOGS what it was asked - no Postgres, no Odoo, no real drop.
"""

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_allocator_liveness_v3 import World, _kv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LIB_REL = "plugins/odoo-ai-agents/scripts/lib"
# What master's allocator needs beside itself: its sibling import, and the
# through-Odoo drop script it hands to the lease's interpreter (a missing one
# would make a drop FAIL - and a failed drop keeps the row, which would let this
# test pass without proving anything).
MASTER_FILES = ("allocator.py", "instances_io.py", "odoo_db.py")


def _git_show(ref_path):
    try:
        proc = subprocess.run(["git", "-C", str(ROOT), "show", ref_path],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


@pytest.fixture(scope="module")
def master_lib(tmp_path_factory):
    """A directory holding master's allocator.py and its siblings."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    dest = tmp_path_factory.mktemp("master_lib")
    for name in MASTER_FILES:
        text = _git_show("master:{lib}/{name}".format(lib=LIB_REL, name=name))
        if text is None:
            pytest.skip("master:{lib}/{name} is not available".format(lib=LIB_REL, name=name))
        (dest / name).write_text(text, encoding="utf-8")
    if "session_anchor" in (dest / "allocator.py").read_text(encoding="utf-8"):
        pytest.skip("master already carries the session-anchored allocator; "
                    "this test guards the pre-anchor release")
    return dest


@pytest.fixture
def old_alloc(master_lib, monkeypatch):
    """master's allocator imported in-process, bound to master's instances_io."""
    saved = sys.modules.pop("instances_io", None)
    monkeypatch.syspath_prepend(str(master_lib))
    try:
        spec = importlib.util.spec_from_file_location("allocator_master",
                                                      master_lib / "allocator.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("instances_io", None)
        if saved is not None:
            sys.modules["instances_io"] = saved
    return mod


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    try:
        yield w
    finally:
        w.close()


def _server():
    """A stand-in long-lived server process (its own process group)."""
    return subprocess.Popen(["sleep", "600"], start_new_session=True)


def _stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)


def _new_rows(world, server):
    """The three row shapes, each written by the CURRENT allocator in a live
    session: (bound, anchored, parked) tokens."""
    a = world.session("sess-A")
    env = world.env(a)
    # 1. a throwaway DB (drop_on_release) bound to a live server pid.
    p, out = world.acquire(env, "--pid", str(server.pid))
    assert p.returncode == 0, p.stderr
    bound = out["ALLOC_TOKEN"]
    # 2. a pid-less build lease protected only by its session anchor.
    p, out = world.acquire(env)
    assert p.returncode == 0, p.stderr
    anchored = out["ALLOC_TOKEN"]
    # 3. a lease whose server was parked (park stops it and keeps the database).
    parked_server = _server()
    try:
        p, out = world.acquire(env, "--pid", str(parked_server.pid))
        assert p.returncode == 0, p.stderr
        parked = out["ALLOC_TOKEN"]
        p = world.run(env, "park", parked, "--run-id", "run-A")
        assert p.returncode == 0, p.stderr
    finally:
        _stop(parked_server)
    return a, bound, anchored, parked


def test_master_does_not_condemn_a_lease_bound_to_a_live_server(world, old_alloc, monkeypatch):
    """THE BLOCKER: master compares owner.pid_started with `==` against the
    ambient `ps -o lstart=`. A TZ-free fingerprint written there never matches,
    so master read every live bound server as `owner-pid-recycled`."""
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    server = _server()
    try:
        _a, bound, _anchored, _parked = _new_rows(world, server)
        row = world.lease(bound)
        assert row["owner"]["pid"] == server.pid
        assert old_alloc._condemn_reason(row) is None, (
            "master condemns a live, bound server's lease written by the current "
            "allocator (reason {r!r}); owner.pid_started = {v!r}".format(
                r=old_alloc._condemn_reason(row), v=row["owner"].get("pid_started")))
        assert old_alloc._is_stale(row) is False
    finally:
        _stop(server)


def test_master_does_not_condemn_a_heartbeating_pid_less_anchored_lease(
        world, old_alloc, monkeypatch):
    """A pid-less lease is judged by master's TTL arm alone: ttl_s against
    heartbeat_at. The session's periodic `heartbeat --session mine` must keep
    heartbeat_at fresh - refreshing only the anchor's seen_at would leave master
    to reap it once its TTL lapsed."""
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    server = _server()
    try:
        a, _bound, anchored, _parked = _new_rows(world, server)
        world.age(anchored, 30 * 3600)  # beyond master's 2h default and the 24h floor
        assert old_alloc._condemn_reason(world.lease(anchored)) is not None, (
            "test setup: an unrefreshed row this old must be condemned by master")
        p = world.run(world.env(a), "heartbeat", "--session", "mine")
        assert p.returncode == 0, p.stderr
        row = world.lease(anchored)
        assert row["owner"].get("pid") is None
        assert old_alloc._condemn_reason(row) is None, (
            "after the session heartbeat master must see a fresh heartbeat_at, got "
            "reason {r!r}".format(r=old_alloc._condemn_reason(row)))
    finally:
        _stop(server)


def test_master_does_not_condemn_a_parked_lease(world, old_alloc, monkeypatch):
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    server = _server()
    try:
        _a, _bound, _anchored, parked = _new_rows(world, server)
        row = world.lease(parked)
        assert row.get("parked_at") is not None and row["owner"].get("pid") is None
        assert old_alloc._condemn_reason(row) is None
    finally:
        _stop(server)


def test_masters_acquire_sweep_reclaims_none_of_the_new_rows(world, master_lib):
    """End to end, the way the incident happens: another session still on the
    released plugin acquires. Its acquire sweeps the machine-wide registry and
    drops what it condemns. Nothing written by the current allocator for a live
    session may be reclaimed, and no database may be dropped."""
    server = _server()
    try:
        a, bound, anchored, parked = _new_rows(world, server)
        env = world.env(None)
        p = subprocess.run(
            [sys.executable, str(master_lib / "allocator.py"), "acquire", "--series", "17.0",
             "--mode", "ephemeral", "--no-create", "--run-id", "run-old"],
            capture_output=True, text=True, env=env, timeout=60)
        assert p.returncode == 0, p.stderr
        assert _kv(p.stdout).get("ALLOC_TOKEN"), p.stdout
        left = {lz["token"] for lz in world.leases()}
        assert {bound, anchored, parked} <= left, (
            "master's acquire reclaimed a lease the current allocator wrote for a live "
            "session:\n" + p.stderr)
        assert world.drops() == [], "master's acquire dropped a database: " + p.stderr
        assert "RECLAIMED" not in p.stderr, p.stderr
        assert server.poll() is None, "master's sweep stopped a live server"
        # And the registry is still one the current allocator reads unchanged.
        listed = json.loads(world.run(world.env(a), "list", "--show-tokens").stdout)
        assert {bound, anchored, parked} <= {lz["token"] for lz in listed["leases"]}
    finally:
        _stop(server)


def test_a_pid_fingerprint_rewritten_by_master_is_not_trusted_for_the_new_pid(
        world, master_lib, old_alloc, monkeypatch):
    """Master's `bind` rewrites owner.pid + owner.pid_started and knows nothing of
    owner.pid_fp. The stale pid_fp (measured on the OLD pid) must not make the
    current allocator read the NEW, live server as recycled."""
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    first, second = _server(), _server()
    try:
        a = world.session("sess-A")
        p, out = world.acquire(world.env(a), "--no-create", "--pid", str(first.pid))
        assert p.returncode == 0, p.stderr
        token = out["ALLOC_TOKEN"]
        p = subprocess.run([sys.executable, str(master_lib / "allocator.py"), "bind", token,
                            "--pid", str(second.pid)],
                           capture_output=True, text=True, env=world.env(None), timeout=60)
        assert p.returncode == 0, p.stderr
        row = world.lease(token)
        assert row["owner"]["pid"] == second.pid and row["owner"].get("pid_fp_pid") == first.pid
        # Judged unanchored (the session is not what this test is about).
        row["owner"].pop("session", None)
        from test_allocator import _import_allocator
        alloc = _import_allocator()
        assert alloc._condemn_reason(row) is None, alloc._judge(row)
        assert alloc._verdict(row)["protected_by"] == "server-pid"
    finally:
        _stop(first)
        _stop(second)


# --------------------------------------------------------------------------- #
# A live session's lease whose BOUND server died
# --------------------------------------------------------------------------- #
def _bound_then_server_dies(world, a=None):
    """Session A acquires a throwaway DB (drop_on_release) bound to a server
    pid; the server then dies while session A lives on. Returns (a, token, pid)."""
    a = a or world.session("sess-A")
    server = _server()
    p, out = world.acquire(world.env(a), "--pid", str(server.pid))
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    assert world.lease(token)["drop_on_release"] is True
    _stop(server)
    return a, token, server.pid


def _verdict(world, env, token):
    listed = json.loads(world.run(env, "list", "--tokens", token, "--with-verdict").stdout)
    return listed["leases"][0]["verdict"]


def test_master_protects_a_live_sessions_lease_after_its_server_died_and_the_session_heartbeat(
        world, old_alloc, monkeypatch):
    """The current allocator protects this row by its live anchor; master knows
    no anchor and reads the dead bound pid as `owner-pid-dead`. The session's
    periodic heartbeat must leave the row in a shape master protects too."""
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    a, token, _pid = _bound_then_server_dies(world)
    assert _verdict(world, world.env(a), token)["protected_by"] == "session"
    assert old_alloc._condemn_reason(world.lease(token)) == old_alloc.CONDEMN_PID_DEAD, (
        "test setup: before the heartbeat master must condemn the dead bound pid")

    p = world.run(world.env(a), "heartbeat", "--session", "mine")
    assert p.returncode == 0, p.stderr
    row = world.lease(token)
    assert old_alloc._condemn_reason(row) is None, (
        "after the session heartbeat master still condemns a live session's lease "
        "({r!r}); owner = {o!r}".format(r=old_alloc._condemn_reason(row), o=row["owner"]))
    # The current allocator's own judgment is unchanged: still the session.
    verdict = _verdict(world, world.env(a), token)
    assert verdict["protected_by"] == "session" and verdict["condemn"] is None
    assert verdict["state"] == "reserved"


def test_masters_acquire_sweep_keeps_a_live_sessions_lease_whose_server_died(world, master_lib):
    """End to end, the incident: the bound server died, session A heartbeats,
    then a session still on the released plugin acquires. Its sweep must not
    reclaim A's lease nor drop A's database."""
    a, token, _pid = _bound_then_server_dies(world)
    p = world.run(world.env(a), "heartbeat", "--session", "mine")
    assert p.returncode == 0, p.stderr
    old = subprocess.run(
        [sys.executable, str(master_lib / "allocator.py"), "acquire", "--series", "17.0",
         "--mode", "ephemeral", "--no-create", "--run-id", "run-old"],
        capture_output=True, text=True, env=world.env(None), timeout=60)
    assert old.returncode == 0, old.stderr
    assert world.lease(token) is not None, (
        "master's acquire reclaimed a live session's lease:\n" + old.stderr)
    assert world.drops() == [], "master's acquire dropped a database: " + old.stderr
    assert "RECLAIMED" not in old.stderr, old.stderr


def test_another_sessions_acquire_also_sheds_the_dead_server_pid(world, old_alloc, monkeypatch):
    """The shed is not only the owner's heartbeat: any current-version write
    under the lock (here another session's acquire) leaves the row safe for
    master, without waiting for session A's next heartbeat."""
    monkeypatch.setenv("ODOO_AI_HOME", str(world.home))
    _a, token, _pid = _bound_then_server_dies(world)
    b = world.session("sess-B")
    p, _out = world.acquire(world.env(b), "--no-create", run_id="run-B")
    assert p.returncode == 0, p.stderr
    assert old_alloc._condemn_reason(world.lease(token)) is None, world.lease(token)["owner"]


def test_a_lease_whose_server_died_can_still_be_parked(world):
    """Shedding the pid must not turn a lease that was RUNNING into one park
    refuses as never-run: parking is how the owner keeps the database past its
    session."""
    a, token, _pid = _bound_then_server_dies(world)
    assert world.run(world.env(a), "heartbeat", "--session", "mine").returncode == 0
    assert world.lease(token)["owner"].get("pid") is None
    p = world.run(world.env(a), "park", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    row = world.lease(token)
    assert row.get("parked_at") is not None
    assert world.drops() == []


def test_an_ended_sessions_lease_and_a_live_server_are_left_as_they_are(world):
    """Nothing is shed without BOTH a provably live anchor and a provably gone
    server: an ended session's row keeps its dead pid (it is condemnable in
    every version anyway) and a live server's pid stays bound."""
    a = world.session("sess-A")
    live = _server()
    try:
        p, out = world.acquire(world.env(a), "--no-create", "--pid", str(live.pid))
        assert p.returncode == 0, p.stderr
        live_token = out["ALLOC_TOKEN"]
        # The server dies after the last write session A makes, then A ends.
        _a, dead_token, dead_pid = _bound_then_server_dies(world, a)
        a.end()
        b = world.session("sess-B")
        assert world.run(world.env(b), "heartbeat", "--session", "mine").returncode == 0
        assert world.lease(dead_token)["owner"].get("pid") == dead_pid
        assert world.lease(live_token)["owner"].get("pid") == live.pid
    finally:
        _stop(live)


# --------------------------------------------------------------------------- #
# Build facts on the lease row (server_wide_modules, built) under the RELEASED
# allocator - the session-anchored one on master, whatever it is. Every verb it
# runs against a row this version wrote must keep both keys intact and must not
# choke on them: its sessions share the registry with this one.
# --------------------------------------------------------------------------- #
RELEASED_FILES = MASTER_FILES + ("session_anchor.py",)
BUILD_FACTS = {"server_wide_modules": ["to_base", "viin_brand"],
               "built": {"demo": True, "languages": ["en_US", "vi_VN"]}}


@pytest.fixture(scope="module")
def released_lib(tmp_path_factory):
    """master's allocator and siblings, taken as they are (no pre-anchor skip)."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    dest = tmp_path_factory.mktemp("released_lib")
    for name in RELEASED_FILES:
        text = _git_show("master:{lib}/{name}".format(lib=LIB_REL, name=name))
        if text is None:
            pytest.skip("master:{lib}/{name} is not available".format(lib=LIB_REL, name=name))
        (dest / name).write_text(text, encoding="utf-8")
    return dest


def _released(world, lib, env, *args):
    return subprocess.run([sys.executable, str(lib / "allocator.py"), *args], capture_output=True,
                          text=True, env=env, timeout=60)


def _row_with_build_facts(world, env, *extra):
    """A lease written by THIS allocator carrying both new keys (server_wide_modules from the
    catalog at acquire, built from record-build)."""
    world.toml.write_text(world.toml.read_text(encoding="utf-8")
                          + 'server_wide_modules = ["to_base", "viin_brand"]\n', encoding="utf-8")
    p, out = world.acquire(env, "--no-create", *extra)
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    for args in (("--demo", "on"), ("--languages", "en_US,vi_VN")):
        p = world.run(env, "record-build", token, *args)
        assert p.returncode == 0, p.stderr
    row = world.lease(token)
    assert {k: row[k] for k in BUILD_FACTS} == BUILD_FACTS
    return token


def test_the_released_allocator_keeps_the_build_facts_through_its_own_writes(world, released_lib):
    a = world.session("sess-A")
    env = world.env(a)
    server = _server()
    try:
        token = _row_with_build_facts(world, env)
        for args in (("heartbeat", token), ("heartbeat", "--session", "mine"),
                     ("bind", token, "--pid", str(server.pid)),
                     ("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create",
                      "--run-id", "run-old"),
                     ("park", token, "--run-id", "run-A")):
            p = _released(world, released_lib, env, *args)
            assert p.returncode == 0, (args, p.stderr)
            row = world.lease(token)
            assert row is not None, "the released allocator removed the row on %r" % (args,)
            assert {k: row.get(k) for k in BUILD_FACTS} == BUILD_FACTS, args
        assert world.drops() == []
    finally:
        _stop(server)


def test_the_released_allocator_lists_and_releases_a_row_with_the_build_facts(world, released_lib):
    a = world.session("sess-A")
    env = world.env(a)
    token = _row_with_build_facts(world, env)
    listed = json.loads(_released(world, released_lib, env, "list", "--show-tokens").stdout)
    row = next(lz for lz in listed["leases"] if lz["token"] == token)
    assert {k: row.get(k) for k in BUILD_FACTS} == BUILD_FACTS
    p = _released(world, released_lib, env, "release", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    assert world.lease(token) is None
    assert world.drops() == [], "a --no-create lease created no database to drop"


def test_a_row_the_released_allocator_wrote_reads_as_no_build_facts_here(world, released_lib):
    """The other direction: a row without the keys (acquired by the released allocator) is read
    by this version as `nothing declared, nothing recorded`, and record-build fills it."""
    a = world.session("sess-A")
    env = world.env(a)
    p = _released(world, released_lib, env, "acquire", "--series", "17.0", "--mode", "ephemeral",
                  "--no-create", "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    token = _kv(p.stdout)["ALLOC_TOKEN"]
    assert "server_wide_modules" not in world.lease(token) and "built" not in world.lease(token)
    p = world.run(env, "record-build", token, "--demo", "off")
    assert p.returncode == 0, p.stderr
    assert world.lease(token)["built"] == {"demo": False, "languages": []}


def _declare_server_wide_once(world):
    text = world.toml.read_text(encoding="utf-8")
    if "server_wide_modules" not in text:
        world.toml.write_text(text + 'server_wide_modules = ["to_base", "viin_brand"]\n',
                              encoding="utf-8")


def _row_with_build_facts_again(world, env, *extra):
    """Another row carrying both keys (the catalog key is declared once)."""
    _declare_server_wide_once(world)
    p, out = world.acquire(env, "--no-create", *extra)
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    assert world.run(env, "record-build", token, "--demo", "on", "--languages",
                     "en_US,vi_VN").returncode == 0
    row = world.lease(token)
    assert {k: row[k] for k in BUILD_FACTS} == BUILD_FACTS
    return token


def _databases_exist(world):
    """The stub cluster answers `exists` with true: these rows' databases were built."""
    text = world.py.read_text(encoding="utf-8")
    assert "exists) echo false" in text, "test setup: the World stub changed shape"
    world.py.write_text(text.replace("exists) echo false", "exists) echo true"), encoding="utf-8")


def _assert_clean(args, p, codes=(0,)):
    assert "Traceback" not in p.stderr, (args, p.stderr)
    assert p.returncode in codes, (args, p.returncode, p.stderr)


def test_the_released_allocators_gc_query_and_reap_run_cleanly_on_rows_with_build_facts(
        world, released_lib):
    """The released allocator's read-and-judge verbs (gc in each scope, query in each form,
    reap-orphans listing and dropping) meet rows carrying `built` / `server_wide_modules` on
    every host that runs two plugin versions: none may crash on them, reclaim a live session's
    row because of them, or strip them."""
    _databases_exist(world)
    a = world.session("sess-A")
    env = world.env(a)
    server = _server()
    try:
        _declare_server_wide_once(world)
        bound = _row_with_build_facts_again(world, env, "--pid", str(server.pid))
        reserved = _row_with_build_facts_again(world, env)
        parked = _row_with_build_facts_again(world, env)
        assert world.run(env, "park", parked, "--run-id", "run-A").returncode == 0
        # The cluster lists every lease's database plus one old, unreferenced orphan: reap must
        # see the build-fact rows as lease references and name the orphan alone. LIST mode only:
        # the released reap's `--yes` drops through the host's raw psql/dropdb, not the stub,
        # so it would reach a real cluster (and blocks on one that prompts).
        orphan = "odoo_17_0_t_0badf00d"
        names = [world.lease(t)["db_name"] for t in (bound, reserved, parked)] + [orphan]
        text = world.py.read_text(encoding="utf-8")
        world.py.write_text(text.replace(
            "    exists) echo true; exit 0 ;;\n",
            "    exists) echo true; exit 0 ;;\n"
            "    list-databases) printf '%s\\n' " + " ".join(names) + "; exit 0 ;;\n"
            "    db-age-s) echo 999999; exit 0 ;;\n"), encoding="utf-8")
        other = world.env(world.session("sess-B"))
        runs = [
            (("gc", "--dry-run"), (0,)),
            (("gc",), (0,)),
            (("gc", "--scope", "dead-sessions"), (0,)),
            (("query", "--series", "17.0"), (0, 1)),  # no shared server: NOT_FOUND
            (("query", "--series", "17.0", "--state", "parked", "--run-id", "run-A"), (0,)),
            (("reap-orphans", "--min-age-s", "0"), (0,)),
        ]
        for args, codes in runs:
            p = _released(world, released_lib, other, *args)
            _assert_clean(args, p, codes)
            if args[:3] == ("query", "--series", "17.0") and "--state" in args:
                assert _kv(p.stdout).get("ALLOC_TOKEN") == parked, p.stdout
            if args[0] == "reap-orphans":
                cands = [ln.split("=", 1)[1].strip("'").split()[0]
                         for ln in p.stdout.splitlines() if ln.startswith("REAP_CANDIDATE=")]
                assert cands == [orphan], "reap named %r, not the orphan alone" % cands
            for token in (bound, reserved, parked):
                row = world.lease(token)
                assert row is not None, "the released %r removed a live session's row" % (args,)
                assert {k: row.get(k) for k in BUILD_FACTS} == BUILD_FACTS, args
        assert world.drops() == [], "the released allocator dropped a database"
        assert server.poll() is None, "the released allocator stopped a live server"
    finally:
        _stop(server)


def test_a_lease_parked_before_it_was_ever_served_is_safe_under_the_released_allocator(
        world, released_lib):
    """`park` now accepts a RESERVED lease (built, never served). The row it writes must read as
    an ordinary parked lease to the released allocator: not condemned by its gc or its acquire
    sweep, found by its `query --state parked`, and its database never dropped."""
    _databases_exist(world)
    a = world.session("sess-A")
    env = world.env(a)
    token = _row_with_build_facts_again(world, env)
    p = world.run(env, "park", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    a.end()  # the owning session is gone: only the park budget protects the row now
    other = world.env(world.session("sess-B"))
    for args in (("gc",), ("gc", "--scope", "dead-sessions"),
                 ("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create",
                  "--run-id", "run-old")):
        p = _released(world, released_lib, other, *args)
        _assert_clean(args, p)
        row = world.lease(token)
        assert row is not None and row.get("parked_at") is not None, (
            "the released %r reclaimed a parked lease:\n%s" % (args, p.stderr))
    p = _released(world, released_lib, other, "query", "--series", "17.0", "--state", "parked",
                  "--run-id", "run-A")
    _assert_clean("query parked", p)
    assert _kv(p.stdout).get("ALLOC_TOKEN") == token
    assert world.drops() == []
