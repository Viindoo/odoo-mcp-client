"""Behavior tests for the ONE gate every allocator process signal passes:
`allocator.py::_stop_owner_group_if_local` may SIGTERM a lease's recorded pid
GROUP only when that pid is PROVEN to belong to the lease.

Both directions are protected here, deliberately, because each one alone can be
satisfied by a broken implementation:

  Direction 1 - THE BYSTANDER MUST LIVE. A lease row naming a live, same-host
    pid with NO `pid_started` fingerprint, whose process corroborates nothing,
    must not be signalled. `leases.json` is at schema_version 2 with lenient
    readers, so that row shape is legal and expected - and the pid may by then
    belong to an unrelated shell, whose entire process group a GROUP SIGTERM
    takes down. Observed for real: a fixture that seeded `owner.pid` with the
    test runner's own pid killed the shell and the in-flight pytest run, with no
    failure message and no log line.

  Direction 2 - THE RUNAWAY MUST STILL DIE. A lease whose pid genuinely is the
    leased Odoo server must still be stopped, on the SAME fingerprint-less row
    shape - reclaiming a runaway server is why the allocator exists. Without
    this direction the fix is indistinguishable from breaking reclamation, and
    "just make it fail-closed" would pass.

Plus the properties that keep the two apart: a fingerprint MISMATCH beats
corroboration (the recorded owner provably exited), an UNMEASURABLE corroborating
signal is not corroboration, every refusal is REPORTED, the lease row is
reclaimed either way, and the `pid_started` backfill only ever stamps a pid whose
ownership was corroborated at that moment.

HARNESS SAFETY - read before editing. This module drives code that sends SIGTERM
to process GROUPS. Two independent interlocks make it incapable of signalling
anything it did not create:
  1. `_spawn` is the ONLY way to get a live pid here. It uses
     `start_new_session=True`, so the child is its own session/group leader
     (pgid == pid) and a group signal cannot reach outside its own descendants.
     Every pid is recorded and reaped in the fixture's teardown.
  2. `_seed_lease` REFUSES (AssertionError, before writing anything) any pid that
     this module did not spawn, unless the pid is proven dead AND the lease names
     a foreign host. `_FORBIDDEN_PIDS` (this process, its whole ancestor chain,
     this process group, 0 and 1) is asserted disjoint from every spawned pid.
Never replace `_spawn`/`_seed_lease` with a raw pid, and never seed
`os.getpid()`, `os.getppid()` or `os.getpgid(0)`.
"""

import contextlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
ALLOC = PLUGIN / "scripts" / "lib" / "allocator.py"

# A pid no process can hold, for the rows that must never be signalled at all.
DEAD_PID = 2 ** 30
FOREIGN_HOST = "seeded-not-this-host"


def _import_allocator():
    spec = importlib.util.spec_from_file_location("allocator_signal_ownership", ALLOC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ancestor_pids():
    """This process, its process group, and every ancestor up to init."""
    out = {0, 1, os.getpid()}
    with contextlib.suppress(OSError):
        out.add(os.getpgid(0))
    pid = os.getpid()
    for _ in range(64):
        try:
            ppid = os.getppid() if pid == os.getpid() else int(
                subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                               capture_output=True, text=True).stdout.strip() or 0
            )
        except ValueError:
            break
        if ppid <= 1:
            out.add(ppid)
            break
        out.add(ppid)
        pid = ppid
    return out


_FORBIDDEN_PIDS = _ancestor_pids()


class Harness:
    """Spawns and reaps the ONLY live processes these tests may name."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.spawned = set()

    # -- the one way to get a live pid ------------------------------------- #
    def spawn(self, argv_tail=(), listen_port=None, fork_child=True):
        """A detached process in its OWN session/group, optionally holding a
        listening socket, optionally with a child in the same group (so a group
        stop is observable as more than one death). `argv_tail` is appended
        verbatim, which is how a test gives the process a production-shaped
        command line.

        Double-fork on purpose (same reason as test_allocator.py's
        `_spawn_orphan_group`): the leader must NOT be a child of the test
        process, or a SIGKILL/SIGTERM leaves a zombie that pytest still holds
        open, `os.kill(pid, 0)` keeps succeeding, and "did it die?" becomes
        unobservable. Orphaned to init, death is real and the assertions mean
        what they say."""
        body = textwrap.dedent(
            """
            import os, socket, sys, time
            port = int(sys.argv[1]) if sys.argv[1] != "-" else 0
            fork_child = sys.argv[2] == "1"
            pidfile = sys.argv[3]
            if os.fork() != 0:
                os._exit(0)          # intermediary exits: the leader is orphaned
            os.setsid()              # own session + process group (pgid == pid)
            s = None
            if port:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                s.listen(5)
            child = os.fork() if fork_child else 0
            if fork_child and child == 0:
                time.sleep(300)
                os._exit(0)
            with open(pidfile, "w") as fh:
                fh.write("%d %d\\n" % (os.getpid(), child))
            time.sleep(300)
            """
        )
        pidfile = self.tmp_path / f"spawn-{len(self.spawned)}.pids"
        argv = [sys.executable, "-c", body, str(listen_port or "-"),
                "1" if fork_child else "0", str(pidfile), *[str(a) for a in argv_tail]]
        subprocess.run(argv, check=True, timeout=30, start_new_session=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            if pidfile.exists() and len(pidfile.read_text().split()) == 2:
                break
            time.sleep(0.02)
        parts = pidfile.read_text().split()
        assert len(parts) == 2, f"the spawned process never reported its pids: {parts!r}"
        leader, child = (int(x) for x in parts)
        self.spawned.add(leader)
        if child:
            self.spawned.add(child)
        # INTERLOCK 1: its own group, disjoint from anything we did not create.
        assert os.getpgid(leader) == leader, (
            "a spawned process must lead its OWN group, so a group signal cannot "
            "reach this test runner or its shell"
        )
        assert leader not in _FORBIDDEN_PIDS and child not in _FORBIDDEN_PIDS
        return leader, child

    def alive(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def reap(self):
        for pid in sorted(self.spawned):
            with contextlib.suppress(ProcessLookupError, OSError):
                os.kill(pid, signal.SIGKILL)
        for pid in sorted(self.spawned):
            with contextlib.suppress(ChildProcessError, OSError):
                os.waitpid(pid, os.WNOHANG)

    # -- the one way to write a lease row --------------------------------- #
    def seed_lease(self, home, pid, *, host=None, **fields):
        """INTERLOCK 2: refuses any pid this harness did not spawn (unless it is
        the proven-dead pid on a foreign host)."""
        if pid is not None and pid not in self.spawned:
            assert pid == DEAD_PID and host == FOREIGN_HOST, (
                f"harness safety: refusing to seed a lease with pid {pid} - this test "
                "module may only name pids it spawned itself (or the proven-dead pid "
                "on a foreign host). Seeding a pid you did not create is how the "
                "signal path kills your own shell."
            )
        assert pid not in _FORBIDDEN_PIDS, (
            "harness safety: that pid is this process, its group or an ancestor"
        )
        lease = {
            "token": fields.pop("token", "aa" * 16),
            "mode": "exclusive",
            "series": "17.0",
            "db_name": "odoo_17_t_deadbeef",
            "drop_on_release": False,
            "python": "",
            "db_host": "localhost",
            "db_user": "odoo",
            "ports": [],
            "ttl_s": 1,
            "heartbeat_at": int(time.time()) - 100000,
            "owner": {
                "host": host if host is not None else socket.gethostname(),
                "pid": pid,
                "run_id": "run-A",
                "started_at": int(time.time()) - 100000,
                **fields.pop("owner", {}),
            },
        }
        lease.update(fields)
        runtime = Path(home) / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "leases.json").write_text(
            json.dumps({"schema_version": 2, "leases": [lease]}), encoding="utf-8")
        return lease


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    try:
        yield h
    finally:
        h.reap()


@pytest.fixture
def alloc_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ODOO_AI_HOME", str(home))
    return home


def _leases(home):
    return json.loads((Path(home) / "runtime" / "leases.json").read_text(encoding="utf-8"))["leases"]


def _expire(home):
    """Push every lease's heartbeat far into the past - i.e. let TTL elapse -
    WITHOUT touching anything else the code under test wrote (so a fingerprint it
    did or did not record survives this)."""
    path = Path(home) / "runtime" / "leases.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    for lease in reg["leases"]:
        lease["heartbeat_at"] = int(time.time()) - 100000
        lease["ttl_s"] = 1
    path.write_text(json.dumps(reg), encoding="utf-8")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fake_odoo_bin(tmp_path):
    """A path token whose basename is `odoo-bin`, so a spawned stand-in carries
    the same command-line shape as 50-instance-spinup.sh's real launch:
    `setsid <py> <...>/odoo-bin -c <conf> -d <db>`."""
    d = tmp_path / "odoo_src"
    d.mkdir(exist_ok=True)
    bin_path = d / "odoo-bin"
    bin_path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    return bin_path


def _wait_dead(harness, *pids, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline and any(harness.alive(p) for p in pids):
        time.sleep(0.05)
    return [p for p in pids if harness.alive(p)]


# --------------------------------------------------------------------------- #
# 0 - the harness's own safety invariants, asserted before anything is signalled
# --------------------------------------------------------------------------- #
def test_harness_cannot_name_a_pid_it_did_not_spawn(harness, tmp_path):
    """The interlocks themselves, as a test: this module can only ever aim the
    signal path at a process it created in its own process group."""
    assert os.getpid() in _FORBIDDEN_PIDS and os.getppid() in _FORBIDDEN_PIDS
    assert os.getpgid(0) in _FORBIDDEN_PIDS

    leader, child = harness.spawn()
    assert harness.spawned >= {leader, child}
    assert not (harness.spawned & _FORBIDDEN_PIDS), (
        "no spawned pid may coincide with this process, its group or an ancestor"
    )
    assert os.getpgid(leader) != os.getpgid(0), (
        "the spawned group must be a DIFFERENT group from the test runner's"
    )

    for forbidden in (os.getpid(), os.getppid(), os.getpgid(0)):
        with pytest.raises(AssertionError):
            harness.seed_lease(tmp_path / "nope", forbidden)
    with pytest.raises(AssertionError):
        harness.seed_lease(tmp_path / "nope", 424242)  # never spawned here
    assert not (tmp_path / "nope").exists(), "a refused seed must write NOTHING"


def test_ss_queue_columns_are_never_read_as_listener_pids():
    """A parser detail that is load-bearing on a kill path: `ss` prints Recv-Q and
    Send-Q as bare integers beside the `pid=` field. Scanning its output for "any
    integer" would let a small unrelated number (a queue depth of 5, a pid of 0)
    corroborate a lease and authorise a signal. Only `pid=<n>` counts."""
    alloc = _import_allocator()
    line = ('LISTEN 0      5      127.0.0.1:8069 0.0.0.0:* '
            'users:(("odoo-bin",pid=41234,fd=7),("odoo-bin",pid=41240,fd=7))')
    assert alloc._pids_from_ss(line) == {41234, 41240}, (
        "only the pid= fields are pids; the queue columns must be ignored"
    )
    assert alloc._pids_from_ss("LISTEN 0 128 0.0.0.0:8069 0.0.0.0:*") == set(), (
        "an ss line with no pid= field names NO holder - it must not yield a pid"
    )


# --------------------------------------------------------------------------- #
# Direction 1 - the bystander must live (gc and release alike)
# --------------------------------------------------------------------------- #
def test_gc_does_not_signal_a_live_unprovable_pid_that_corroborates_nothing(
        harness, alloc_home, capfd):
    """THE INCIDENT, as a test. Live same-host pid, NO `pid_started`, a process
    that is not an Odoo server and holds none of the lease's ports: gc must
    reclaim the lease WITHOUT signalling that pid's group."""
    alloc = _import_allocator()
    leader, child = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    unheld_port = _free_port()
    harness.seed_lease(alloc_home, leader, ports=[unheld_port])
    assert _leases(alloc_home)[0]["owner"].get("pid_started") is None

    assert alloc.cmd_gc({}) == 0
    time.sleep(1.0)  # a SIGTERM'd group dies in well under this

    assert harness.alive(leader), (
        "an unproven pid must NOT be signalled: this lease row carries no "
        "pid_started, and nothing about the live process corroborates the lease, so "
        "the pid may belong to an unrelated session whose whole group would die"
    )
    assert harness.alive(child), "nor may its group members be signalled"
    err = capfd.readouterr().err
    assert f"REFUSING to signal pid {leader}" in err, (
        "the refusal must be REPORTED - an invisible non-decision is what made the "
        f"original incident undiagnosable; stderr was: {err!r}"
    )
    assert "pid_started" in err, "the refusal must say WHY ownership was unproven"
    assert _leases(alloc_home) == [], (
        "refusing to SIGNAL must not stop the lease row from being reclaimed - "
        "otherwise the fix trades a wrong kill for a permanent lease leak"
    )


def test_release_does_not_signal_a_live_unprovable_pid(harness, alloc_home, capfd):
    """The same gate on the release path, not just gc: release still succeeds and
    still removes the lease, it just never signals an unproven pid."""
    alloc = _import_allocator()
    leader, child = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    harness.seed_lease(alloc_home, leader, token="bb" * 16)

    assert alloc.cmd_release({"token": "bb" * 16, "run_id": "run-A"}) == 0
    time.sleep(1.0)

    assert harness.alive(leader) and harness.alive(child), (
        "release must not signal an unproven pid either"
    )
    assert f"REFUSING to signal pid {leader}" in capfd.readouterr().err
    assert _leases(alloc_home) == [], "the lease must still be released"


def test_an_unmeasurable_corroborating_signal_is_not_corroboration(
        harness, alloc_home, capfd, monkeypatch):
    """A port-holder question that could not be ASKED (no lsof/ss/fuser on this
    host) is "could not look", never "it is ours". The process survives and the
    refusal says so."""
    alloc = _import_allocator()
    port = _free_port()
    leader, child = harness.spawn(listen_port=port, argv_tail=["bystander"])
    monkeypatch.setattr(alloc, "_which", lambda binary: None)
    assert alloc._port_listener_pids(port) is None, (
        "with no tool available the answer must be None (unknown), not an empty set"
    )
    harness.seed_lease(alloc_home, leader, ports=[port])

    assert alloc.cmd_gc({}) == 0
    time.sleep(1.0)
    assert harness.alive(leader) and harness.alive(child)
    assert f"REFUSING to signal pid {leader}" in capfd.readouterr().err


def test_a_fingerprint_mismatch_beats_every_corroborating_signal(
        harness, alloc_home, tmp_path, capfd):
    """Ladder order, pinned: a POSITIVE fingerprint mismatch proves the recorded
    owner already exited, so the pid is a recycled stranger no matter how much
    the live process looks like the leased server."""
    alloc = _import_allocator()
    db = "odoo_17_t_mismatch"
    port = _free_port()
    leader, child = harness.spawn(
        listen_port=port,
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", f"/conf/{db}-8069.conf", "-d", db])
    harness.seed_lease(alloc_home, leader, db_name=db, ports=[port],
                       owner={"pid_started": "Thu Jan  1 00:00:00 1970"})

    assert alloc.cmd_gc({}) == 0
    time.sleep(1.0)
    assert harness.alive(leader) and harness.alive(child), (
        "a proven-recycled pid must never be signalled, corroboration or not"
    )
    assert "recycled" in capfd.readouterr().err


# --------------------------------------------------------------------------- #
# Direction 2 - the genuine runaway must still die
# --------------------------------------------------------------------------- #
def test_gc_still_stops_a_runaway_server_proven_by_its_command_line(
        harness, alloc_home, tmp_path, capfd):
    """The reclaim half. Same fingerprint-less row shape as Direction 1, but the
    live process IS the leased server: it runs an odoo-bin command line naming
    this lease's own database (the shape 50-instance-spinup.sh launches). Its
    whole GROUP must be stopped and the lease reclaimed."""
    alloc = _import_allocator()
    db = "odoo_17_t_runaway1"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    leader, child = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    harness.seed_lease(alloc_home, leader, db_name=db)
    assert _leases(alloc_home)[0]["owner"].get("pid_started") is None

    assert alloc.cmd_gc({}) == 0
    survivors = _wait_dead(harness, leader, child)
    assert survivors == [], (
        f"a runaway leased server must STILL be reclaimed; {survivors} survived. "
        "Requiring a fingerprint that old lease rows never recorded would leak "
        "every pre-fingerprint server forever"
    )
    assert "ownership PROVEN by cmdline" in capfd.readouterr().err
    assert _leases(alloc_home) == []


def test_gc_still_stops_a_runaway_server_proven_by_the_leases_own_port(
        harness, alloc_home, capfd):
    """The second corroborating observation, load-bearing on its own: no
    fingerprint and a command line that names nothing, but the process leads the
    group LISTENING on a port this lease reserved."""
    alloc = _import_allocator()
    port = _free_port()
    leader, child = harness.spawn(listen_port=port, argv_tail=["opaque-server-name"])
    if alloc._port_listener_pids(port) is None:
        pytest.skip("no lsof/ss/fuser on this host: port ownership is unobservable")
    harness.seed_lease(alloc_home, leader, ports=[port])

    assert alloc.cmd_gc({}) == 0
    survivors = _wait_dead(harness, leader, child)
    assert survivors == [], (
        f"holding the lease's own reserved port proves ownership; {survivors} survived"
    )
    assert "ownership PROVEN by port" in capfd.readouterr().err


def test_gc_still_stops_a_matching_fingerprint_owner_when_condemned(
        harness, alloc_home, capfd):
    """The pre-existing proof must keep working unchanged: a row WITH a matching
    `pid_started` is signalled on the strength of the fingerprint alone - no
    corroboration required, so the fix cannot have become "corroborate always"."""
    alloc = _import_allocator()
    leader, child = harness.spawn(argv_tail=["bystander-shaped-but-fingerprinted"])
    fingerprint = alloc._pid_fingerprint(leader)
    assert fingerprint, "test setup: the spawned process must be fingerprintable"
    # A lease that is stale by TTL and whose owner pid is the recorded one: gc
    # condemns it (heartbeat far in the past) and the stop is proven.
    harness.seed_lease(alloc_home, leader, owner={"pid_started": fingerprint})
    monkey = _leases(alloc_home)[0]["owner"]
    assert monkey["pid_started"] == fingerprint

    # _is_stale PROTECTS a verified-alive owner, so drive the gate directly here:
    # this test is about the signal decision, not about who condemns the lease.
    assert alloc._stop_owner_group_if_local(_leases(alloc_home)[0]) is True
    survivors = _wait_dead(harness, leader, child)
    assert survivors == [], f"a fingerprint match must still authorise the stop; {survivors} survived"
    assert "ownership PROVEN by fingerprint" in capfd.readouterr().err


# --------------------------------------------------------------------------- #
# Backfill - shrink the unprovable population without manufacturing proof
# --------------------------------------------------------------------------- #
def test_heartbeat_backfills_the_fingerprint_only_when_ownership_is_corroborated(
        harness, alloc_home, tmp_path, capfd):
    alloc = _import_allocator()
    db = "odoo_17_t_backfill"
    leader, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", f"/c/{db}-8069.conf", "-d", db])
    harness.seed_lease(alloc_home, leader, db_name=db, token="cc" * 16,
                       heartbeat_at=int(time.time()))

    assert alloc.cmd_heartbeat({"token": "cc" * 16}) == 0
    recorded = _leases(alloc_home)[0]["owner"]["pid_started"]
    assert recorded == alloc._pid_fingerprint(leader), (
        "a corroborated row must gain the fingerprint it never recorded, so later "
        "checks stop having to judge it by the pid number alone"
    )
    assert "recorded the missing owner.pid_started" in capfd.readouterr().err


def test_heartbeat_never_backfills_a_fingerprint_it_cannot_corroborate(
        harness, alloc_home, capfd):
    """The dangerous half of a backfill: stamping whatever process holds the pid
    would convert an honestly-unprovable row into a wrongly-PROVEN one, and every
    later signal would trust it. It must stay absent - and the next gc must still
    refuse to signal."""
    alloc = _import_allocator()
    leader, child = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    harness.seed_lease(alloc_home, leader, token="dd" * 16,
                       heartbeat_at=int(time.time()))

    assert alloc.cmd_heartbeat({"token": "dd" * 16}) == 0
    assert _leases(alloc_home)[0]["owner"].get("pid_started") is None, (
        "an uncorroborated pid must NOT be fingerprinted - that would manufacture "
        "the very proof the gate exists to demand"
    )
    capfd.readouterr()
    _expire(alloc_home)  # let the TTL elapse so gc actually judges this row
    assert alloc.cmd_gc({}) == 0
    time.sleep(1.0)
    assert harness.alive(leader) and harness.alive(child)
    assert f"REFUSING to signal pid {leader}" in capfd.readouterr().err


# --------------------------------------------------------------------------- #
# The two cheap gates before any of the above (no process is ever touched)
# --------------------------------------------------------------------------- #
def test_a_foreign_host_lease_is_never_probed_or_signalled(harness, alloc_home):
    alloc = _import_allocator()
    harness.seed_lease(alloc_home, DEAD_PID, host=FOREIGN_HOST)
    lease = _leases(alloc_home)[0]

    def _explode(*a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("a foreign-host lease must not be inspected at all")

    for name in ("_pid_alive", "_pid_cmdline", "_port_listener_pids", "_stop_group"):
        setattr(alloc, name, _explode)
    assert alloc._stop_owner_group_if_local(lease) is False


def test_a_dead_pid_is_a_silent_no_op(harness, alloc_home, capfd):
    alloc = _import_allocator()
    harness.seed_lease(alloc_home, DEAD_PID, host=FOREIGN_HOST)
    lease = _leases(alloc_home)[0]
    lease["owner"]["host"] = socket.gethostname()  # same host, provably dead pid
    signalled = {"hit": False}
    alloc._stop_group = lambda *a, **k: signalled.__setitem__("hit", True)
    assert alloc._stop_owner_group_if_local(lease) is False
    assert signalled["hit"] is False, "a dead pid must never reach _stop_group"
    assert "REFUSING" not in capfd.readouterr().err, (
        "a dead pid is not a refusal to report - there is nothing to signal"
    )


# --------------------------------------------------------------------------- #
# DOC DIRECTION - no agent-facing prose may license the blind kill
#
# This guard exists because of how the defect survived: no test ever compared
# what the docs CLAIM about the signal decision against what the code DOES.
# `INSTANCE-LIFECYCLE.md` stated that a recycled-pid condemn means "the
# fingerprint no longer matches, so the process is stopped ... even though the pid
# itself is alive" - the exact inverse of the rule. A reader following that
# sentence would have reintroduced the blind kill believing they were conforming,
# which is worse than an undocumented rule: it is a document deputising the bug.
#
# The asserted invariant is a DIRECTION, not a wording: no doc may say that an
# unproven, unprovable or PROVEN-RECYCLED pid gets stopped/killed/terminated/
# signalled. Legitimate prose is untouched - stopping a PROVEN owner, the
# SIGTERM -> wait -> SIGKILL escalation itself, `_is_stale` CONDEMNING a lease on
# a mismatch (a lease-level verdict, not a signal), and the `os.kill(pid, 0)`
# liveness PROBE, which sends no signal at all.
# --------------------------------------------------------------------------- #

# A no-proof condition: the fingerprint is missing, unmeasurable, or mismatched.
_DOC_NO_PROOF = re.compile(r"""(
    fingerprint[^.|]{0,80}?(no\ longer\ match|does\ not\ match|mismatch|cannot\ be|could\ not\ be)
  | (pid_started|fingerprint)[^.|]{0,60}?(absent|missing|never\ recorded|unverifiable)
  | positive\ (\S+\ )?mismatch
  | recycled(-pid)?
  | unproven | unprovable | not\ proven | cannot\ be\ proven | ownership\ is\ not\ proven
  | without\ a\ fingerprint | no\ `?pid_started`?
)""", re.I | re.X)

# Actually sending a signal (or claiming a process ends up stopped by one).
_DOC_SIGNAL = re.compile(r"""(
    is\ stopped | are\ stopped | be\ stopped | stops?\ (that|the|its)\ (pid|process|server|group)
  | stopping\ (that|the|its) | kill(s|ed|ing)? | terminat(e|es|ed|ing)
  | signall?(s|ed|ing)? | SIGTERM | SIGKILL | killpg
)""", re.I | re.X)

# An explicit statement that NO signal is sent - the shape correct prose takes.
_DOC_NEGATED = re.compile(r"""(
    never\ signall?ed | not\ signall?ed | never\ stopped | not\ stopped | never\ kill | not\ kill
  | must\ not\ be\ signall?ed | refus | left\ alone | no\ signal\ is\ sent | nothing\ was\ signall?ed
  | never\ reached\ by\ this\ path | never\ condemns
)""", re.I | re.X)

# `os.kill(pid, 0)` / `kill -0` send NO signal - they are liveness PROBES. Excised
# before the scan so documenting the probe never reads as documenting a kill.
_DOC_PROBE = re.compile(r"(os\.)?kill\s*\(?\s*(pid)?\s*,?\s*0\s*\)?|kill\s+-0", re.I)

# The claim has to be about signalling a PROCESS. "a killed/OOM'd session" is a
# session dying of its own accord, not the allocator signalling anything.
_DOC_PID_NOUN = re.compile(r"\b(pid|process(es)?|group|server|owner)\b", re.I)


def _doc_sentences(text):
    flat = re.sub(r"\s+", " ", text)
    # Split on sentence enders AND table-cell pipes: a markdown API table packs
    # several independent claims onto one physical line.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\s*\|\s*", flat) if s.strip()]


def _licenses_a_blind_kill(sentence):
    """True when `sentence` claims an unproven/recycled pid ends up signalled."""
    text = _DOC_PROBE.sub(" ", sentence)
    if _DOC_NEGATED.search(text):
        return False
    no_proof = list(_DOC_NO_PROOF.finditer(text))
    signals = [m for m in _DOC_SIGNAL.finditer(text)
               if _DOC_PID_NOUN.search(text[max(0, m.start() - 60):m.end() + 60])]
    if not (no_proof and signals):
        return False
    # A causal claim keeps its halves close; 200 chars apart inside a period-less
    # blob is coincidence, not an assertion.
    return min(abs(a.start() - b.start()) for a in no_proof for b in signals) <= 200


# Each of these is a real phrasing of the inverted rule. The first is the exact
# wording that shipped in INSTANCE-LIFECYCLE.md and licensed the incident.
_MUST_CATCH = {
    "the_original_shipped_sentence":
        "The same order applies inside `gc` whenever it reclaims a lease with a still-live "
        "local pid - a recycled-pid condemn (the fingerprint no longer matches, so the "
        "process is stopped before the drop even though the pid itself is alive), or the "
        "liveness-unprovable-past-TTL fallback case.",
    "kill_verb":
        "When the fingerprint no longer matches, gc kills the recorded pid's process group "
        "before dropping the database.",
    "terminate_verb":
        "A lease with no `pid_started` still has its owner process terminated on reclaim.",
    "signal_verb_unprovable":
        "If the fingerprint cannot be re-measured, the allocator signals the process group "
        "anyway, best effort.",
    "recycled_pid_stopped":
        "A recycled pid is stopped along with its group so the drop is not blocked.",
    "sigterm_on_absent_fingerprint":
        "For a legacy row whose `pid_started` is absent, release sends SIGTERM to the pid's "
        "group and escalates to SIGKILL.",
}

_MUST_NOT_CATCH = {
    # The corrected prose in INSTANCE-LIFECYCLE.md.
    "corrected_mismatch_rule":
        "A positive `pid_started` mismatch proves the OPPOSITE of ownership - the recorded "
        "owner already exited, which is exactly how its pid became free to be reused - so "
        "the live process now holding that number is an unrelated bystander and is NEVER "
        "signalled: the lease is still condemned and reclaimed, the process is left alone, "
        "and the refusal is reported.",
    # Stopping a PROVEN owner is the whole point of the mechanism.
    "proven_owner_is_stopped":
        "If the lease carries an `owner.pid` on THIS host that is alive AND PROVEN to be "
        "this lease's own server, STOP the server's process GROUP first (SIGTERM -> bounded "
        "wait -> group SIGKILL).",
    # The escalation ladder, described with no proof claim at all.
    "escalation_ladder":
        "The allocator stops the server's process group FIRST (SIGTERM, bounded wait, group "
        "SIGKILL), THEN drops the DB for `drop_on_release` leases.",
    # `_is_stale` CONDEMNS a lease on a mismatch - a lease verdict, not a signal.
    "mismatch_condemns_the_lease":
        "A POSITIVE fingerprint mismatch (the pid was recycled onto a different process) "
        "condemns immediately, same as a dead pid - the recorded owner is exactly as gone.",
    # The liveness probe sends no signal.
    "liveness_probe":
        "The `pid_started` fingerprint rules out a pid-recycled impostor, which a bare "
        "`os.kill(pid,0)` cannot tell apart from the original process.",
    # Something else dying, not the allocator signalling.
    "session_died_on_its_own":
        "A killed/OOM'd session gets its ephemeral DB dropped when `_is_stale` says the "
        "lease may be reclaimed (dead pid; or unprovable liveness past TTL).",
    # The reaping-direction rationale, which legitimately uses "kills".
    "reaping_direction_rationale":
        "For reaping, the safe default is to NOT reap when unsure - an un-reaped orphan only "
        "costs RAM, but a wrongly-reaped lease kills a live server and destroys the owner's "
        "in-progress work.",
}


@pytest.mark.parametrize("name", sorted(_MUST_CATCH))
def test_the_doc_guard_catches_every_phrasing_of_the_inverted_rule(name):
    assert _licenses_a_blind_kill(_MUST_CATCH[name]), (
        f"MUST-CATCH {name!r}: this sentence tells a reader that an unproven or "
        "proven-recycled pid gets signalled, which is the defect. The guard failed to "
        "flag it, so the doc could ship it again"
    )


@pytest.mark.parametrize("name", sorted(_MUST_NOT_CATCH))
def test_the_doc_guard_leaves_correct_prose_alone(name):
    assert not _licenses_a_blind_kill(_MUST_NOT_CATCH[name]), (
        f"MUST-NOT-CATCH {name!r}: this sentence is CORRECT (it either negates the signal, "
        "describes stopping a PROVEN owner, condemns a lease rather than a process, or "
        "describes a liveness probe). A guard that flags it would push authors into "
        "vaguer prose, not truer prose"
    )


def test_no_plugin_doc_claims_an_unproven_pid_is_signalled():
    """The live scan: every `*.md` under the plugin, in the direction the code
    actually implements. `_ownership_proof` signals ONLY on proof, so no doc may
    promise otherwise - a paraphrase that outruns the code is how the blind kill
    got authorised in the first place."""
    findings = []
    for md in sorted(PLUGIN.rglob("*.md")):
        for sentence in _doc_sentences(md.read_text(encoding="utf-8")):
            if _licenses_a_blind_kill(sentence):
                findings.append(f"{md.relative_to(PLUGIN)}: {sentence[:300]}")
    assert not findings, (
        "these sentences claim an unproven / unprovable / proven-recycled pid gets "
        "stopped, killed or signalled, which inverts `_stop_owner_group_if_local`. State "
        "the rule the code implements (an unproven pid is NEVER signalled; the lease is "
        "still reclaimed) and point at `_ownership_proof` instead of paraphrasing its "
        "rungs:\n  - " + "\n  - ".join(findings)
    )
