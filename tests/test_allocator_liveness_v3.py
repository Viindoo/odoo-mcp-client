"""Behavior tests for the allocator's session-anchored liveness (registry v3),
its non-destructive acquire, the scoped two-phase `gc`, and `--format json`.

The contract, stated as behavior:
  - a lease whose acquiring SESSION is alive is never reclaimed - not for a dead
    server pid, not for an expired TTL - and an ended session's lease is
    reclaimable (`owner-session-ended`), after a grace window on the automatic
    paths, immediately on an explicit `gc`;
  - a resumed session (same session id, new process) re-anchors its leases;
  - the automatic paths (`gc --scope dead-sessions`, acquire's capacity reclaim)
    never take the TTL arm;
  - acquire reclaims nothing but capacity, frees only ports, never drops a DB;
  - `gc` never holds the registry lock while it drops, `--dry-run` changes
    nothing, `--scope anchor` touches exactly one session's running leases;
  - `--format json` prints one object with a named error code on every failure.

The fake session anchor is a real `sleep` this module starts (its pid + its
fingerprint, exported as ODOO_AI_SESSION_ANCHOR); "the session ends" is that
sleep being killed. Every database interaction goes through a stub interpreter
that only LOGS what it was asked - no Postgres, no Odoo, no real drop.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
ALLOC = LIB / "allocator.py"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import session_anchor as sa  # noqa: E402
from test_allocator import INSTANCES_TOML, _import_allocator  # noqa: E402

TIMEOUT = 60
# A gated stub drop gives up after this long. It is well past TIMEOUT on purpose:
# a call that waits on the registry lock while a gated drop holds it then fails
# with a TimeoutExpired instead of quietly finishing once the gate gives up.
DROP_GATE_MAX_S = 2 * TIMEOUT
POOL = list(range(8170, 8180))  # INSTANCES_TOML: http_port_base 8170, pool 10


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #
class Session:
    """A fake agent session: a live `sleep` as the anchor process + a session id."""

    def __init__(self, session_id):
        self.session_id = session_id
        self.proc = subprocess.Popen(["sleep", "600"], start_new_session=True)
        self.pid = self.proc.pid
        self.started = sa.fingerprint(self.pid)
        assert self.started, "the stand-in anchor must be fingerprintable"

    @property
    def anchor(self):
        return sa.format_anchor(self.pid, self.started)

    def end(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=10)


class World:
    def __init__(self, tmp_path, drop_sleep_s=0, drop_gated=False):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.calls = tmp_path / "odoo_db_calls.log"
        self.drop_started = tmp_path / "drop-started"
        # With `drop_gated`, a stub drop blocks until the test opens this gate.
        self.drop_gate = tmp_path / "drop-gate" if drop_gated else None
        self.py = self._stub_python(drop_sleep_s)
        self.toml = tmp_path / "instances.toml"
        self.toml.write_text(INSTANCES_TOML.replace(
            'python = "/srv/venv/bin/python"', f'python = "{self.py}"'), encoding="utf-8")
        self.sessions = []

    def _stub_python(self, drop_sleep_s):
        """The instance's declared interpreter: answers every odoo_db.py question
        affirmatively, LOGS it, and - for `drop` - marks that a drop began and
        optionally takes `drop_sleep_s` to finish, or waits for `drop_gate` (a
        slow real drop)."""
        py = self.tmp / "fakebin" / "python"
        py.parent.mkdir()
        if self.drop_gate is not None:
            drop_sleep_s = (
                f'0; i=0; while [ ! -e "{self.drop_gate}" ] && '
                f'[ $i -lt {int(DROP_GATE_MAX_S * 20)} ]; do sleep 0.05; i=$((i+1)); done')
        py.write_text(
            "#!/bin/sh\n"
            'if [ "$(basename "$1")" = "odoo_db.py" ]; then\n'
            f'  echo "$2 $3" >> "{self.calls}"\n'
            '  case "$2" in\n'
            "    can-createdb) echo true; exit 0 ;;\n"
            '    preflight) echo "DB_AUTH_WHY=stub"; exit 0 ;;\n'
            f'    drop) : > "{self.drop_started}"; sleep {drop_sleep_s}; exit 0 ;;\n'
            "    exists) echo false; exit 0 ;;\n"
            "  esac\n"
            "  exit 0\n"
            "fi\n"
            f'exec {sys.executable} "$@"\n', encoding="utf-8")
        py.chmod(0o755)
        return py

    def session(self, session_id):
        s = Session(session_id)
        self.sessions.append(s)
        return s

    def env(self, session=None, *, session_id=None, **extra):
        e = dict(os.environ)
        e.pop(sa.CLAUDE_PID_ENV, None)
        e["ODOO_AI_HOME"] = str(self.home)
        e["ODOO_AI_INSTANCES"] = str(self.toml)
        e["HOME"] = str(self.home)
        e[sa.ANCHOR_ENV] = session.anchor if session else "none"
        sid = session_id if session_id is not None else (session.session_id if session else "")
        e[sa.SESSION_ID_ENV] = sid
        e.update(extra)
        return e

    def run(self, env, *args, timeout=TIMEOUT):
        return subprocess.run([sys.executable, str(ALLOC), *args], capture_output=True,
                              text=True, env=env, timeout=timeout)

    def acquire(self, env, *extra, run_id="run-A", mode="ephemeral"):
        p = self.run(env, "acquire", "--series", "17.0", "--mode", mode, "--run-id", run_id,
                     *extra)
        return p, _kv(p.stdout)

    def registry_path(self):
        return self.home / "runtime" / "leases.json"

    def leases(self):
        path = self.registry_path()
        return json.loads(path.read_text(encoding="utf-8"))["leases"] if path.exists() else []

    def lease(self, token):
        return next((lz for lz in self.leases() if lz["token"] == token), None)

    def edit(self, token, fn):
        path = self.registry_path()
        reg = json.loads(path.read_text(encoding="utf-8"))
        for lease in reg["leases"]:
            if lease["token"] == token:
                fn(lease)
        path.write_text(json.dumps(reg), encoding="utf-8")

    def age(self, token, seconds):
        """Push every "last touched" stamp of a lease `seconds` into the past."""
        def _age(lease):
            lease["heartbeat_at"] = int(time.time()) - seconds
            lease["owner"]["started_at"] = int(time.time()) - seconds
            if lease["owner"].get("session"):
                lease["owner"]["session"]["seen_at"] = int(time.time()) - seconds
        self.edit(token, _age)

    def records(self):
        log = self.home / "logs" / "allocator-reclaimed.jsonl"
        if not log.is_file():
            return []
        return [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()
                if ln.strip()]

    def drops(self):
        if not self.calls.is_file():
            return []
        return [ln for ln in self.calls.read_text(encoding="utf-8").splitlines()
                if ln.startswith("drop ")]

    def close(self):
        for s in self.sessions:
            s.end()


def _kv(stdout):
    import shlex
    out = {}
    for line in stdout.splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, raw = line.partition("=")
            vals = shlex.split(raw)
            out[key] = vals[0] if vals else ""
    return out


def _dead_pid():
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    try:
        yield w
    finally:
        w.close()


@pytest.fixture
def slow_world(tmp_path):
    w = World(tmp_path, drop_gated=True)
    try:
        yield w
    finally:
        w.drop_gate.touch()  # never leave a stub drop polling behind
        w.close()


# --------------------------------------------------------------------------- #
# 1 - the anchor protects; its death condemns
# --------------------------------------------------------------------------- #
def test_an_alive_session_protects_a_lease_whose_server_is_dead_and_ttl_expired(world):
    """The 90 `owner-pid-dead` + 44 TTL reclaims of live work, as one lease: its
    recorded server pid is dead (a restart that never re-bound) and its explicit
    TTL is long gone - but the session that acquired it is still running."""
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--no-create", "--pid", str(_dead_pid()),
                           "--ttl", "1")
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    world.age(token, 100_000)

    gc = world.run(world.env(b), "gc")
    assert gc.returncode == 0, gc.stderr
    assert world.lease(token) is not None, (
        f"a live session's lease must survive an explicit gc:\n{gc.stderr}"
    )
    listed = json.loads(world.run(world.env(b), "list", "--tokens", token,
                                  "--with-verdict").stdout)["leases"]
    assert listed[0]["verdict"]["protected_by"] == "session"
    assert listed[0]["verdict"]["anchor_alive"] is True
    assert listed[0]["verdict"]["condemn"] is None


def test_an_ended_session_is_condemned_as_owner_session_ended(world):
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    a.end()

    gc = world.run(world.env(b), "gc")
    assert gc.returncode == 0, gc.stderr
    assert world.lease(token) is None, "an explicit gc reclaims an ended session's lease"
    rec, = [r for r in world.records() if r["token"] == token]
    assert rec["reason"] == "owner-session-ended" and rec["owner_session_id"] == "sess-A"


def test_the_automatic_path_waits_out_the_grace_window_after_a_session_ends(world):
    """A session that just crashed may be resumed; `gc --scope dead-sessions`
    (the automatic reclaimer) spares it for ANCHOR_GRACE_S, then takes it."""
    alloc = _import_allocator()
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    a.end()

    world.run(world.env(b), "gc", "--scope", "dead-sessions")
    assert world.lease(token) is not None, "inside the grace window the lease must survive"

    world.age(token, alloc.ANCHOR_GRACE_S + 60)
    world.run(world.env(b), "gc", "--scope", "dead-sessions")
    assert world.lease(token) is None, "past the grace window the ended session's lease goes"


def test_a_resumed_session_with_the_same_session_id_re_anchors_its_lease(world):
    """`claude --resume` starts a NEW process under the SAME session id. Its first
    touch must adopt the old lease instead of letting it be condemned."""
    a = world.session("sess-A")
    _p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    a.end()
    resumed = world.session("sess-A")

    gc = world.run(world.env(resumed), "gc")
    assert gc.returncode == 0, gc.stderr
    lease = world.lease(token)
    assert lease is not None, "the resumed session's own lease must be protected"
    assert lease["owner"]["session"]["pid"] == resumed.pid, (
        "and re-anchored onto the resumed process, so later callers see it alive"
    )
    other = world.session("sess-B")
    verdict = json.loads(world.run(world.env(other), "list", "--tokens", token,
                                   "--with-verdict").stdout)["leases"][0]["verdict"]
    assert verdict["anchor_alive"] is True


def test_the_automatic_paths_never_take_the_ttl_arm(world):
    """An UNANCHORED, pid-less lease with an expired TTL: liveness is unprovable,
    which is an absence of evidence. Only an explicit gc may act on it."""
    alloc = _import_allocator()
    _p, out = world.acquire(world.env(None), "--no-create", "--ttl", "1")
    token = out["ALLOC_TOKEN"]
    world.age(token, 100_000)
    assert alloc._condemn_reason(world.lease(token), auto=True) is None

    world.run(world.env(None), "gc", "--scope", "dead-sessions")
    assert world.lease(token) is not None
    world.run(world.env(None), "gc")
    assert world.lease(token) is None, "an explicit gc (scope all) still honours the TTL arm"


# --------------------------------------------------------------------------- #
# 2 - acquire is non-destructive
# --------------------------------------------------------------------------- #
def test_another_sessions_acquire_leaves_a_condemnable_lease_untouched(world):
    alloc = _import_allocator()
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, out = world.acquire(world.env(a))
    token = out["ALLOC_TOKEN"]
    a.end()
    world.age(token, alloc.ANCHOR_GRACE_S + 60)
    assert alloc._condemn_reason(world.lease(token)) == alloc.CONDEMN_SESSION_ENDED

    for mode in ("ephemeral", "exclusive", "shared"):
        p, _ = world.acquire(world.env(b), "--no-create", run_id="run-B", mode=mode)
        assert p.returncode == 0, p.stderr
    assert world.lease(token) is not None
    assert world.drops() == [], "an acquire never drops a database"
    assert not [r for r in world.records() if r["by_verb"] == "acquire"]


def test_a_capacity_reclaim_frees_ports_only_and_keeps_the_row_and_database(world):
    """The whole pool is held by an ephemeral lease (a real throwaway DB,
    drop_on_release) of a session that ended long ago. A new acquire that needs a
    port may take the PORTS - and nothing else: the row stays (orphaned), the
    database is not dropped, and the record says dropped_db=false."""
    alloc = _import_allocator()
    a, b = world.session("sess-A"), world.session("sess-B")
    p, out = world.acquire(world.env(a), "--ports", str(len(POOL)))
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    assert world.lease(token)["drop_on_release"] is True
    a.end()
    world.age(token, alloc.ANCHOR_GRACE_S + 60)

    p, out_b = world.acquire(world.env(b), "--no-create", "--ports", "1", run_id="run-B")
    assert p.returncode == 0, p.stderr
    assert int(out_b["ALLOC_PORTS"]) in POOL
    victim = world.lease(token)
    assert victim is not None, "the capacity path must never delete an ephemeral row"
    assert victim["ports"] == [] and victim["orphaned"]["reason"] == "owner-session-ended"
    assert victim["db_name"] and victim["drop_on_release"] is True
    assert world.drops() == [], "the capacity path must never drop a database"
    rec, = [r for r in world.records() if r["token"] == token]
    assert rec["by_verb"] == "acquire-capacity" and rec["dropped_db"] is False

    # The orphaned row is still finished properly by an explicit gc.
    world.run(world.env(b), "gc")
    assert world.lease(token) is None and len(world.drops()) == 1


def test_a_full_pool_held_inside_the_grace_window_refuses_with_named_holders(world):
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, out = world.acquire(world.env(a), "--no-create", "--ports", str(len(POOL)))
    token = out["ALLOC_TOKEN"]
    a.end()  # ended, but only just: inside ANCHOR_GRACE_S

    p = world.run(world.env(b), "acquire", "--series", "17.0",
                  "--mode", "ephemeral", "--no-create", "--ports", "1", "--run-id", "run-B",
                  "--format", "json")
    doc = json.loads(p.stdout)
    assert p.returncode == 4 and doc["error"]["code"] == "PORT_POOL_EXHAUSTED"
    holders = doc["fields"]["holders"]
    assert [h["token8"] for h in holders] == [token[:8]]
    assert holders[0]["session_alive"] is False and holders[0]["mode"] == "ephemeral"
    assert isinstance(holders[0]["age_s"], int)
    assert world.lease(token)["ports"] == POOL, "inside the grace window nothing is taken"


# --------------------------------------------------------------------------- #
# 3 - gc: two-phase, dry-run, scoped
# --------------------------------------------------------------------------- #
def test_gc_does_not_hold_the_registry_lock_while_it_drops(slow_world):
    """A drop can take minutes; every acquire/release on the machine waits on the
    registry lock. With a drop in flight that does not finish until the test
    says so, an acquire (which takes the lock) and a list must both complete -
    and the row being reclaimed keeps its ports reserved until the drop has
    finished. No wall clock: had the gc held the lock, these calls could only
    return after the gate opened, which happens after they are checked."""
    w = slow_world
    a, b = w.session("sess-A"), w.session("sess-B")
    # Condemnable by EVERY arm a gc has ever had (ended session AND an expired
    # explicit TTL), so the lock property is what this test isolates.
    _p, out = w.acquire(w.env(a), "--ports", str(len(POOL)), "--ttl", "1")
    token = out["ALLOC_TOKEN"]
    w.age(token, 100_000)
    a.end()

    gc = subprocess.Popen([sys.executable, str(ALLOC), "gc"], env=w.env(b),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 20
        while not w.drop_started.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert w.drop_started.exists(), "test setup: the drop never started"

        p, got = w.acquire(w.env(b), "--no-create", run_id="run-B")
        listed = w.run(w.env(b), "list", "--with-verdict", "--show-tokens")
        assert not w.drop_gate.exists() and gc.poll() is None, (
            "acquire + list must complete while the gc's drop is still blocked")
        assert p.returncode == 0 and listed.returncode == 0, (p.stderr, listed.stderr)
        row = next(lz for lz in json.loads(listed.stdout)["leases"] if lz["token"] == token)
        assert row["verdict"]["state"] == "reclaiming"

        busy = w.run(w.env(b), "acquire", "--series", "17.0", "--mode", "ephemeral",
                     "--no-create", "--ports", "1", "--run-id", "run-B")
        assert busy.returncode == 4, (
            "the ports of a row still being reclaimed must not be handed out:\n" + busy.stderr
        )
    finally:
        w.drop_gate.touch()
        gc.wait(timeout=60)
    assert w.lease(token) is None and len(w.drops()) == 1


def test_gc_dry_run_destroys_nothing(world):
    alloc = _import_allocator()
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, out = world.acquire(world.env(a))
    token = out["ALLOC_TOKEN"]
    a.end()
    before = world.registry_path().read_bytes()

    p = world.run(world.env(b), "gc", "--dry-run")
    assert p.returncode == 0, p.stderr
    assert _kv(p.stdout).get("ALLOC_WOULD_RECLAIM") == token
    assert world.registry_path().read_bytes() == before, "a dry run must not write"
    assert world.drops() == [] and world.records() == []

    doc = json.loads(world.run(world.env(b), "gc", "--dry-run", "--format", "json").stdout)
    cand, = doc["fields"]["candidates"]
    assert cand["token"] == token and cand["reason"] == alloc.CONDEMN_SESSION_ENDED
    assert cand["drops_db"] is True
    assert world.registry_path().read_bytes() == before


def test_gc_scope_anchor_touches_only_that_sessions_running_leases(world):
    """What SessionEnd runs for the session that just ended: its running and
    reserved leases go; its PARKED lease (deliberately preserved), another ended
    session's lease and an unanchored stale lease all stay."""
    a, other = world.session("sess-A"), world.session("sess-C")
    _p, mine = world.acquire(world.env(a), "--no-create")
    _p, parked = world.acquire(world.env(a), "--no-create")
    world.edit(parked["ALLOC_TOKEN"], lambda lz: lz.update(parked_at=int(time.time()),
                                                            park_ttl_s=86400))
    _p, theirs = world.acquire(world.env(other), "--no-create", run_id="run-C")
    _p, loose = world.acquire(world.env(None), "--no-create", "--ttl", "1")
    world.age(loose["ALLOC_TOKEN"], 100_000)
    anchor = a.anchor
    a.end()
    other.end()

    p = world.run(world.env(None), "gc", "--scope", "anchor", "--anchor", anchor)
    assert p.returncode == 0, p.stderr
    left = {lz["token"] for lz in world.leases()}
    assert mine["ALLOC_TOKEN"] not in left
    assert {parked["ALLOC_TOKEN"], theirs["ALLOC_TOKEN"], loose["ALLOC_TOKEN"]} <= left


def test_gc_scope_anchor_refuses_a_session_that_is_still_alive(world):
    a = world.session("sess-A")
    _p, out = world.acquire(world.env(a), "--no-create")
    p = world.run(world.env(None), "gc", "--scope", "anchor", "--anchor", a.anchor,
                  "--format", "json")
    doc = json.loads(p.stdout)
    assert p.returncode == 3 and doc["error"]["code"] == "ANCHOR_ALIVE"
    assert world.lease(out["ALLOC_TOKEN"]) is not None


# --------------------------------------------------------------------------- #
# 4 - owner block, list filters, anchor/adopt/heartbeat
# --------------------------------------------------------------------------- #
def test_the_owner_block_records_session_via_and_acquired_by(world):
    a = world.session("sess-A")
    env = world.env(a, ODOO_AI_VIA="mcp", ODOO_AI_CALLER_AGENT_ID="agent-7",
                    ODOO_AI_CALLER_AGENT_TYPE="odoo-instance-ops")
    _p, out = world.acquire(env, "--no-create")
    owner = world.lease(out["ALLOC_TOKEN"])["owner"]
    assert owner["session"]["pid"] == a.pid and owner["session"]["started"] == a.started
    assert owner["session"]["session_id"] == "sess-A" and owner["session"]["source"] == "env"
    assert isinstance(owner["session"]["seen_at"], int)
    assert owner["via"] == "mcp"
    assert owner["acquired_by"] == {"agent_id": "agent-7", "agent_type": "odoo-instance-ops"}

    _p, plain = world.acquire(world.env(None), "--no-create")
    owner = world.lease(plain["ALLOC_TOKEN"])["owner"]
    assert owner["via"] == "cli" and "session" not in owner and "acquired_by" not in owner


def test_list_filters_by_tokens_and_by_the_callers_session(world):
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, ta = world.acquire(world.env(a), "--no-create")
    _p, tb = world.acquire(world.env(b), "--no-create", run_id="run-B")
    mine = json.loads(world.run(world.env(a), "list", "--session", "mine",
                                "--show-tokens").stdout)["leases"]
    assert [lz["token"] for lz in mine] == [ta["ALLOC_TOKEN"]]
    by_anchor = json.loads(world.run(world.env(None), "list", "--session", b.anchor,
                                     "--show-tokens").stdout)["leases"]
    assert [lz["token"] for lz in by_anchor] == [tb["ALLOC_TOKEN"]]
    picked = json.loads(world.run(world.env(None), "list", "--tokens",
                                  tb["ALLOC_TOKEN"][:8] + ",nomatch").stdout)["leases"]
    assert [lz["token"] for lz in picked] == [tb["ALLOC_TOKEN"][:8]]


def test_anchor_print_reports_the_callers_anchor(world):
    a = world.session("sess-A")
    p = world.run(world.env(a), "anchor", "--print")
    out = _kv(p.stdout)
    assert p.returncode == 0
    assert out["ODOO_AI_SESSION_ANCHOR"] == a.anchor and out["ODOO_AI_SESSION_ID"] == "sess-A"
    assert out["ODOO_AI_ANCHOR_STATE"] == "alive"
    none = world.run(world.env(None), "anchor", "--print", "--format", "json")
    assert none.returncode == 5 and json.loads(none.stdout)["error"]["code"] == "NO_ANCHOR"


def test_adopt_re_anchors_only_for_the_owning_run(world):
    a, b = world.session("sess-A"), world.session("sess-B")
    _p, out = world.acquire(world.env(a), "--no-create")
    token = out["ALLOC_TOKEN"]
    refused = world.run(world.env(b), "adopt", token, "--run-id", "run-X", "--format", "json")
    assert refused.returncode == 1
    assert json.loads(refused.stdout)["error"]["code"] == "NOT_OWNER"
    assert world.lease(token)["owner"]["session"]["pid"] == a.pid

    ok = world.run(world.env(b), "adopt", token, "--run-id", "run-A")
    assert ok.returncode == 0, ok.stderr
    assert world.lease(token)["owner"]["session"]["pid"] == b.pid
    a.end()
    world.run(world.env(None), "gc")
    assert world.lease(token) is not None, "the adopting session now protects the lease"


def test_heartbeat_session_mine_refreshes_every_lease_of_the_session(world):
    a = world.session("sess-A")
    _p, one = world.acquire(world.env(a), "--no-create")
    _p, two = world.acquire(world.env(a), "--no-create")
    for token in (one["ALLOC_TOKEN"], two["ALLOC_TOKEN"]):
        world.age(token, 5000)
    p = world.run(world.env(a), "heartbeat", "--session", "mine")
    assert p.returncode == 0, p.stderr
    for token in (one["ALLOC_TOKEN"], two["ALLOC_TOKEN"]):
        seen = world.lease(token)["owner"]["session"]["seen_at"]
        assert time.time() - seen < 60


# --------------------------------------------------------------------------- #
# 5 - --format json and named failures; usage errors never trace back
# --------------------------------------------------------------------------- #
def _json(world, env, *args):
    p = world.run(env, *args, "--format", "json")
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"--format json must print exactly ONE object:\n{p.stdout}"
    doc = json.loads(lines[0])
    assert set(doc) == {"ok", "rc", "error", "fields"}
    assert doc["rc"] == p.returncode and doc["ok"] is (p.returncode == 0)
    return doc


def test_json_success_carries_typed_fields_and_no_error(world):
    doc = _json(world, world.env(None), "acquire", "--series", "17.0", "--mode", "ephemeral",
                "--no-create", "--ports", "2", "--run-id", "run-J")
    assert doc["ok"] is True and doc["error"] is None
    fields = doc["fields"]
    assert len(fields["ALLOC_TOKEN"]) == 32 and fields["ALLOC_RUN_ID"] == "run-J"
    assert isinstance(fields["ALLOC_PORTS"], list) and len(fields["ALLOC_PORTS"]) == 2


@pytest.mark.parametrize("args, rc, code", [
    (("acquire", "--mode", "ephemeral", "--no-create", "--run-id", "r"), 2, "SERIES_REQUIRED"),
    (("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create"), 10,
     "RUN_ID_REQUIRED"),
    (("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create", "--run-id", "r",
      "--ports", "two"), 2, "USAGE"),
    (("acquire", "--series", "99.0", "--mode", "ephemeral", "--run-id", "r"), 1,
     "NO_INSTANCE"),
    (("bind", "tok", "--pid", "abc"), 2, "USAGE"),
    (("park", "no-such-token"), 1, "LEASE_NOT_FOUND"),
    (("gc", "--scope", "everything"), 2, "USAGE"),
    (("frobnicate",), 2, "USAGE"),
])
def test_every_failure_names_its_code_and_its_exit(world, args, rc, code):
    alloc = _import_allocator()
    doc = _json(world, world.env(None), *args)
    assert doc["rc"] == rc and doc["error"]["code"] == code, doc
    assert alloc.ERROR_CODES[code]["rc"] == rc, "each code always pairs with one exit code"
    assert doc["error"]["message"]


def test_a_release_by_another_run_is_not_owner_in_json(world):
    _p, out = world.acquire(world.env(None), "--no-create")
    doc = _json(world, world.env(None), "release", out["ALLOC_TOKEN"], "--run-id", "run-Z")
    assert doc["rc"] == 1 and doc["error"]["code"] == "NOT_OWNER"


@pytest.mark.parametrize("caller", [("--run-id", "run-Z"), ()], ids=["other-run", "no-run-id"])
def test_a_park_by_another_run_is_not_owner_in_json(world, caller):
    """The CLI (Bash fallback) path enforces park ownership itself - no wrapper is
    needed to keep a stranger from stopping a peer's server - and names it with
    the same code release uses, ahead of the lease-state refusals (this lease has
    no server, so a later check would have said NOT_RUNNING instead)."""
    _p, out = world.acquire(world.env(None), "--no-create")
    doc = _json(world, world.env(None), "park", out["ALLOC_TOKEN"], *caller)
    assert doc["rc"] == 1 and doc["error"]["code"] == "NOT_OWNER", doc


@pytest.mark.parametrize("args", [
    ("acquire", "--mode", "ephemeral", "--no-create", "--run-id", "r"),
    ("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create", "--run-id", "r",
     "--ports", "x"),
    ("acquire", "--series", "17.0", "--mode", "shared", "--run-id", "r", "--port", "http"),
    ("acquire", "--series", "17.0", "--mode", "ephemeral", "--no-create", "--run-id", "r",
     "--ttl", "soon"),
])
def test_shell_mode_usage_errors_exit_2_without_a_traceback_or_a_lease(world, args):
    """Without --format json the protocol is unchanged, except that the two
    silent/crashing shapes are now usage errors: a missing --series no longer
    picks the highest declared series, and a non-integer --ports no longer
    crashes half-way through an allocation."""
    p = world.run(world.env(None), *args)
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert "Traceback" not in p.stderr, p.stderr
    assert p.stdout == "", "a refusal writes nothing to the eval protocol"
    assert world.leases() == []


def test_list_json_nests_the_leases(world):
    _p, out = world.acquire(world.env(None), "--no-create")
    doc = _json(world, world.env(None), "list", "--with-verdict")
    lease, = doc["fields"]["leases"]
    assert lease["token"] == out["ALLOC_TOKEN"][:8]
    assert set(lease["verdict"]) >= {"state", "protected_by", "condemn", "condemn_auto",
                                     "anchor_alive"}
    assert doc["fields"]["schema_version"] == 3
