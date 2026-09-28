"""Behavior tests: the lease facts other components consume, and the pool/park
edges a live exercise hit.

The contract, stated as behavior:
  - every lease row records the RESOLVED catalog `profile` ("" when unprofiled),
    and `list` returns it, so a consumer re-selects the same catalog row (python,
    addons) instead of the series' first one;
  - every successful acquire and adopt names the lease on STDERR
    (`allocator: acquired lease <token> run_id=<id>` /
    `allocator: adopted lease <token> run_id=<id>`), which survives an
    `eval "$(... acquire ...)"` that consumes stdout - and stdout stays the
    KEY=VALUE protocol;
  - a pool port in TIME_WAIT (it just served HTTP) is still handed out, because
    Odoo itself binds with SO_REUSEADDR;
  - after a capacity reclaim stopped the server holding the pool, acquire waits a
    short, bounded moment for the freed port instead of failing at once;
  - a pool that no lease holds but that cannot be bound fails with a DISTINCT
    reason and remedy (the ports are busy outside the registry);
  - a lease resumed out of another session's park goes BACK to the park when the
    resuming session ends - its database is not dropped;
  - a missing or unreadable instance catalog is a named refusal
    (NO_INSTANCE_CATALOG) on every verb that reads it, never a traceback.

Every database interaction goes through the stub interpreter of `World`, which
only LOGS what it was asked - no Postgres, no Odoo, no real drop.
"""

import errno
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_allocator import _import_allocator  # noqa: E402
from test_allocator_liveness_v3 import ALLOC, World, _kv  # noqa: E402

TIMEOUT = 60

TWO_PROFILES = """
[[instance]]
series = "17.0"
profile = "alpha"
addons_path = ["/srv/alpha/addons"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
python = "{py_alpha}"

[[instance]]
series = "17.0"
profile = "beta"
addons_path = ["/srv/beta/addons"]
run_mode = "source"
http_port = 8079
http_port_base = 8180
port_pool_size = 10
db_name = "odoo_17_0_beta"
db_name_prefix = "odoo_17_0_beta"
db_host = "localhost"
db_user = "odoo"
python = "{py_beta}"
"""

ONE_PORT_POOL = """
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
run_mode = "source"
http_port = {declared}
http_port_base = {base}
port_pool_size = 1
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
python = "{py}"
"""

# A stand-in Odoo server, launched the way 50-instance-spinup.sh launches one:
# DETACHED (its own session, reparented away from the test, so a stop really
# makes it disappear instead of leaving a zombie the test would have to reap).
# It listens on argv[1] the way Odoo does (SO_REUSEADDR), prints its pid, and -
# with argv[2] = linger seconds - forks a child in ANOTHER session that keeps the
# listening socket open that long after the server died (a worker outliving its
# master for a moment).
SERVER = r"""
import os, socket, sys, time
port = int(sys.argv[1]); linger = float(sys.argv[2]) if len(sys.argv) > 2 else 0
if os.fork():
    os._exit(0)
os.setsid()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("", port)); s.listen(5)
if linger and os.fork() == 0:
    os.setsid()
    parent = os.getppid()
    while os.getppid() == parent:
        time.sleep(0.05)
    time.sleep(linger)
    os._exit(0)
print("READY %d" % os.getpid(), flush=True)
sys.stdout.close()
time.sleep(600)
"""


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    try:
        yield w
    finally:
        w.close()


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _one_port_world(world):
    """Rewrite `world`'s catalog to a pool of exactly ONE free port; return it."""
    port = _free_port()
    world.toml.write_text(ONE_PORT_POOL.format(declared=port + 1000 if port < 60000 else 1,
                                               base=port, py=world.py), encoding="utf-8")
    return port


def _plain_bind_fails(port):
    s = socket.socket()
    try:
        s.bind(("", port))
    except OSError as exc:
        return exc.errno == errno.EADDRINUSE
    finally:
        s.close()
    return False


def _time_wait(port):
    """Leave `port` with a connection in TIME_WAIT, the way a server that just
    answered an HTTP request and closed does: the listener closes its side
    first, then the listener itself goes away."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    cli = socket.create_connection(("127.0.0.1", port), timeout=5)
    conn, _ = srv.accept()
    conn.sendall(b"HTTP/1.0 200 OK\r\n\r\n")
    conn.close()  # the server side closes FIRST -> TIME_WAIT on the server port
    cli.recv(64)
    cli.close()
    srv.close()


class _Server:
    def __init__(self, port, linger=0):
        launcher = subprocess.Popen([sys.executable, "-c", SERVER, str(port), str(linger)],
                                    stdout=subprocess.PIPE, text=True)
        line = launcher.stdout.readline().split()
        launcher.wait(timeout=10)
        assert line[:1] == ["READY"], "test setup: the stand-in server did not start"
        self.pid = int(line[1])

    def alive(self):
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        return True

    def wait_dead(self, timeout=15):
        deadline = time.time() + timeout
        while self.alive() and time.time() < deadline:
            time.sleep(0.05)
        return not self.alive()


def _server(port, linger=0):
    return _Server(port, linger)


def _kill(server):
    try:
        os.killpg(server.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    server.wait_dead()


# --------------------------------------------------------------------------- #
# 1 - the lease row records the resolved profile
# --------------------------------------------------------------------------- #
def test_every_lease_row_records_the_resolved_catalog_profile(world):
    """A series with two profiles: a consumer that reads the lease back (list,
    find, adopt, instance serve) must learn WHICH catalog row it was built from,
    or it launches the series' first row's interpreter against the other's DB."""
    beta_py = world.tmp / "fakebin" / "python-beta"
    beta_py.write_bytes(world.py.read_bytes())
    beta_py.chmod(0o755)
    world.toml.write_text(TWO_PROFILES.format(py_alpha=world.py, py_beta=beta_py),
                          encoding="utf-8")
    a = world.session("sess-A")
    env = world.env(a)

    p, beta = world.acquire(env, "--no-create", "--profile", "beta")
    assert p.returncode == 0, p.stderr
    assert beta["ALLOC_PROFILE"] == "beta" and beta["ALLOC_PYTHON"] == str(beta_py)
    p, default = world.acquire(env, "--no-create")
    assert p.returncode == 0, p.stderr
    p, shared = world.acquire(env, "--profile", "beta", mode="shared")
    assert p.returncode == 0, p.stderr

    assert world.lease(beta["ALLOC_TOKEN"])["profile"] == "beta"
    assert world.lease(default["ALLOC_TOKEN"])["profile"] == default["ALLOC_PROFILE"] == "alpha"
    assert world.lease(shared["ALLOC_TOKEN"])["profile"] == "beta"

    doc = json.loads(world.run(env, "list", "--show-tokens", "--format", "json").stdout)
    by_token = {lz["token"]: lz for lz in doc["fields"]["leases"]}
    assert by_token[beta["ALLOC_TOKEN"]]["profile"] == "beta"
    assert by_token[default["ALLOC_TOKEN"]]["profile"] == "alpha"


# --------------------------------------------------------------------------- #
# 2 - the acquired / adopted lease is named on stderr
# --------------------------------------------------------------------------- #
def test_acquire_names_the_lease_on_stderr_even_when_stdout_is_evald(world):
    a = world.session("sess-A")
    script = ('eval "$({py} {alloc} acquire --series 17.0 --mode ephemeral --no-create '
              '--run-id run-A)"; echo "TOKEN=$ALLOC_TOKEN"').format(
        py=shlex.quote(sys.executable), alloc=shlex.quote(str(ALLOC)))
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env=world.env(a), timeout=TIMEOUT)
    assert p.returncode == 0, p.stderr
    token = _kv(p.stdout)["TOKEN"]
    assert len(token) == 32
    assert f"allocator: acquired lease {token} run_id=run-A" in p.stderr.splitlines(), p.stderr


@pytest.mark.parametrize("mode", ["ephemeral", "exclusive", "shared"])
def test_every_lease_writing_acquire_names_its_lease_and_keeps_stdout_the_protocol(world, mode):
    a = world.session("sess-A")
    p, out = world.acquire(world.env(a), "--no-create", mode=mode)
    assert p.returncode == 0, p.stderr
    assert f"allocator: acquired lease {out['ALLOC_TOKEN']} run_id=run-A" in p.stderr
    assert all(ln.startswith("#") or "=" in ln for ln in p.stdout.splitlines() if ln), (
        "stdout must stay pure KEY=VALUE protocol:\n" + p.stdout)
    assert "allocator:" not in p.stdout
    # (an exclusive hold on the same database would refuse the second acquire)
    assert world.run(world.env(a), "release", out["ALLOC_TOKEN"], "--run-id",
                     "run-A").returncode == 0

    js = world.run(world.env(a), "acquire", "--series", "17.0", "--mode", mode,
                   "--no-create", "--run-id", "run-A", "--format", "json")
    doc = json.loads(js.stdout)  # exactly one JSON object on stdout
    token = doc["fields"]["ALLOC_TOKEN"]
    assert f"allocator: acquired lease {token} run_id=run-A" in js.stderr


def test_a_readonly_attach_writes_no_lease_and_names_none(world):
    p, out = world.acquire(world.env(None), mode="readonly")
    assert p.returncode == 0, p.stderr
    assert out["ALLOC_TOKEN"] == "" and "acquired lease" not in p.stderr


def test_adopt_names_the_adopted_lease_on_stderr(world):
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    p = world.run(world.env(b), "adopt", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    assert f"allocator: adopted lease {token} run_id=run-A" in p.stderr.splitlines()
    assert "allocator:" not in p.stdout


# --------------------------------------------------------------------------- #
# 3 - the port pool: TIME_WAIT, the post-reclaim wait, busy-outside-registry
# --------------------------------------------------------------------------- #
def test_a_pool_port_in_time_wait_is_still_handed_out(world):
    """A port that just served HTTP sits in TIME_WAIT for ~60s. Odoo binds it
    fine (SO_REUSEADDR), so the allocator must not call the pool exhausted."""
    port = _one_port_world(world)
    _time_wait(port)
    if not _plain_bind_fails(port):
        pytest.skip("test setup: this host did not leave the port in TIME_WAIT")
    p, out = world.acquire(world.env(None), "--no-create", "--ports", "1")
    assert p.returncode == 0, p.stderr
    assert out["ALLOC_PORTS"] == str(port)


def test_a_port_still_listened_on_is_never_handed_out(world):
    """The SO_REUSEADDR probe must still refuse a port a live server LISTENS on
    - with a distinct reason, because no lease holds it."""
    alloc = _import_allocator()
    port = _one_port_world(world)
    server = _server(port)
    try:
        p = world.run(world.env(None), "acquire", "--series", "17.0", "--mode", "ephemeral",
                      "--no-create", "--ports", "1", "--run-id", "run-A", "--format", "json")
        doc = json.loads(p.stdout)
        assert p.returncode == 4 and doc["error"]["code"] == "PORT_POOL_EXHAUSTED"
        fields = doc["fields"]
        assert fields["holders"] == []
        assert fields["reason"] == alloc.PORTS_BUSY_OUTSIDE_REGISTRY
        spec = alloc.ERROR_CODES["PORT_POOL_EXHAUSTED"]["reasons"][fields["reason"]]
        assert fields["remedy"] == spec["remedy"]
        assert doc["error"]["message"] == spec["summary"]
        assert fields["reason"] in p.stderr, "the shell path must name the reason too"
        assert world.leases() == []
    finally:
        _kill(server)


def test_a_pool_held_by_a_lease_keeps_the_ordinary_exhausted_remedy(world):
    port = _one_port_world(world)
    a = world.session("sess-A")
    p, _ = world.acquire(world.env(a), "--no-create", "--ports", "1")
    assert p.returncode == 0, p.stderr
    p = world.run(world.env(a), "acquire", "--series", "17.0", "--mode", "ephemeral",
                  "--no-create", "--ports", "1", "--run-id", "run-B", "--format", "json")
    doc = json.loads(p.stdout)
    assert p.returncode == 4 and doc["error"]["code"] == "PORT_POOL_EXHAUSTED"
    assert [h["ports"] for h in doc["fields"]["holders"]] == [[port]]
    assert "reason" not in doc["fields"]


def test_after_a_capacity_reclaim_acquire_waits_briefly_for_the_freed_port(world):
    """The pool's only port is held by an ended session's server whose worker
    keeps the listening socket open ~1.5s after the master is stopped. The
    reclaiming acquire must get that port, not PORT_POOL_EXHAUSTED with no
    holders."""
    alloc = _import_allocator()
    port = _one_port_world(world)
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--no-create", "--ports", "1")
    assert p.returncode == 0 and out["ALLOC_PORTS"] == str(port), p.stderr
    token = out["ALLOC_TOKEN"]
    server = _server(port, linger=1.5)
    try:
        p = world.run(world.env(a), "bind", token, "--pid", str(server.pid))
        assert p.returncode == 0, p.stderr
        a.end()
        world.age(token, alloc.ANCHOR_GRACE_S + 60)

        p, got = world.acquire(world.env(b), "--no-create", "--ports", "1", run_id="run-B")
        assert p.returncode == 0, p.stderr
        assert got["ALLOC_PORTS"] == str(port)
        assert world.lease(token)["orphaned"]["reason"] == "owner-session-ended"
    finally:
        _kill(server)


# --------------------------------------------------------------------------- #
# 4 - a resumed park goes back to the park when the resuming session ends
# --------------------------------------------------------------------------- #
def test_a_lease_resumed_from_a_park_is_parked_again_when_the_resuming_session_ends(world):
    # `resume` refuses a database that is provably gone; this stub's database exists.
    world.py.write_text(world.py.read_text(encoding="utf-8").replace(
        "exists) echo false", "exists) echo true"), encoding="utf-8")
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--ports", "1")  # drop_on_release: a real throwaway
    assert p.returncode == 0, p.stderr
    token, port = out["ALLOC_TOKEN"], int(out["ALLOC_PORTS"])
    first = _server(port)
    try:
        assert world.run(world.env(a), "bind", token, "--pid", str(first.pid)).returncode == 0
        p = world.run(world.env(a), "park", token, "--run-id", "run-A", "--park-ttl", "7777")
        assert p.returncode == 0, p.stderr
    finally:
        _kill(first)

    second = _server(port)
    try:
        p = world.run(world.env(b), "resume", token, "--pid", str(second.pid))
        assert p.returncode == 0, p.stderr
        assert world.lease(token).get("parked_at") is None
        anchor = b.anchor
        b.end()

        p = world.run(world.env(None), "gc", "--scope", "anchor", "--anchor", anchor)
        assert p.returncode == 0, p.stderr
        row = world.lease(token)
        assert row is not None, "the park its owner chose must survive the resumer's end"
        assert row.get("parked_at") is not None and row["park_ttl_s"] == 7777
        assert row["owner"].get("pid") is None and row["ports"] == [port]
        assert row["drop_on_release"] is True and world.drops() == []
        assert _kv(p.stdout).get("ALLOC_PARKED") == token
        assert "ALLOC_RECLAIMED" not in p.stdout
        assert second.wait_dead(), "a parked lease holds disk, never a server"
    finally:
        _kill(second)


def test_a_lease_the_ending_session_acquired_itself_is_still_reclaimed(world):
    """Control: only a lease taken OUT OF A PARK goes back to one."""
    a = world.session("sess-A")
    _p, out = world.acquire(world.env(a))
    anchor = a.anchor
    a.end()
    p = world.run(world.env(None), "gc", "--scope", "anchor", "--anchor", anchor)
    assert p.returncode == 0, p.stderr
    assert world.lease(out["ALLOC_TOKEN"]) is None and len(world.drops()) == 1


# --------------------------------------------------------------------------- #
# 5 - no catalog is a named refusal, never a traceback
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("argv", [
    ["acquire", "--series", "99.0", "--run-id", "x"],
    ["acquire", "--series", "99.0", "--run-id", "x", "--mode", "shared"],
    ["db-preflight", "--series", "99.0"],
    ["can-createdb", "--series", "99.0"],
    ["reap-orphans"],
])
def test_a_missing_instance_catalog_is_a_named_refusal(tmp_path, argv):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    for key in ("ODOO_AI_INSTANCES", "CLAUDE_PID"):
        env.pop(key, None)
    env.update(ODOO_AI_HOME=str(home), HOME=str(home), ODOO_AI_SESSION_ANCHOR="none")
    p = subprocess.run([sys.executable, str(ALLOC), *argv, "--format", "json"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path),
                       timeout=TIMEOUT)
    assert "Traceback" not in p.stderr, p.stderr
    doc = json.loads(p.stdout)
    assert p.returncode == 1 and doc["ok"] is False, p.stderr
    assert doc["error"]["code"] == "NO_INSTANCE_CATALOG", doc
    shell = subprocess.run([sys.executable, str(ALLOC), *argv], capture_output=True, text=True,
                           env=env, cwd=str(tmp_path), timeout=TIMEOUT)
    assert shell.returncode == 1 and "Traceback" not in shell.stderr, shell.stderr
    assert not (home / "runtime" / "leases.json").exists(), "a refusal writes no lease"


def test_an_unparseable_instance_catalog_is_a_named_refusal(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bad = tmp_path / "instances.toml"
    bad.write_text("[[instance]]\nseries = \n", encoding="utf-8")
    env = dict(os.environ, ODOO_AI_HOME=str(home), HOME=str(home),
               ODOO_AI_SESSION_ANCHOR="none")
    p = subprocess.run([sys.executable, str(ALLOC), "acquire", "--series", "17.0", "--run-id",
                        "x", "--instances", str(bad), "--format", "json"],
                       capture_output=True, text=True, env=env, timeout=TIMEOUT)
    assert "Traceback" not in p.stderr, p.stderr
    assert json.loads(p.stdout)["error"]["code"] == "NO_INSTANCE_CATALOG"


# --------------------------------------------------------------------------- #
# 6 - release says whether THIS call removed the row
# --------------------------------------------------------------------------- #
def test_release_reports_that_it_deleted_the_row_and_a_second_release_that_it_was_absent(world):
    a = world.session("sess-A")
    _p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]

    p = world.run(world.env(a), "release", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    kv = _kv(p.stdout)
    assert kv.get("ALLOC_RELEASED") == token and "ALLOC_ALREADY_ABSENT" not in kv
    assert world.lease(token) is None

    p = world.run(world.env(a), "release", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    kv = _kv(p.stdout)
    assert kv.get("ALLOC_ALREADY_ABSENT") == "1" and "ALLOC_RELEASED" not in kv

    js = json.loads(world.run(world.env(a), "release", token, "--run-id", "run-A",
                              "--format", "json").stdout)
    assert js["ok"] is True and js["fields"]["ALLOC_ALREADY_ABSENT"] == 1
    assert "ALLOC_RELEASED" not in js["fields"]


def test_a_refused_or_kept_release_claims_no_release(world):
    a = world.session("sess-A")
    _p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    p = world.run(world.env(a), "release", token, "--run-id", "run-X", "--format", "json")
    doc = json.loads(p.stdout)
    assert p.returncode == 1 and doc["error"]["code"] == "NOT_OWNER"
    assert "ALLOC_RELEASED" not in doc["fields"] and "ALLOC_ALREADY_ABSENT" not in doc["fields"]

    js = json.loads(world.run(world.env(a), "release", token, "--run-id", "run-A",
                              "--format", "json").stdout)
    assert js["ok"] is True and js["fields"]["ALLOC_RELEASED"] == token
