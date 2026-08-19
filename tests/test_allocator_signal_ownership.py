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

`park`/`resume` (the G4 section near the end) live here for the same reason:
`park` is the THIRD call site that sends a process signal through this gate, and
its whole promise - "park holds disk, never memory" - IS that stop. `resume` is
the write path that hands the gate a pid for the future, so it is bound by the
same corroboration rule.

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

        Returns `(leader, child)`. `fork_child=False` stages the OTHER real
        shape - a process group with exactly one member, which is what a
        `workers = 0` source-mode instance runs as - and reports `child` as 0:
        the sentinel for "no second member", never a pid (see the interlock
        below, and `_dead_same_host_pid` in the sibling module, which already
        reads it that way).

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
        assert leader not in _FORBIDDEN_PIDS, (
            f"harness safety: the spawned leader {leader} is this process, its group "
            "or an ancestor"
        )
        # `child` is 0 under `fork_child=False`: the spawned script writes that as
        # the SENTINEL for "no second member in this group", never as a pid. It
        # must be vetted as a sentinel, because 0 IS in _FORBIDDEN_PIDS and
        # belongs there - `os.kill(0, ...)` signals THIS process's whole group
        # (the runner and its shell), which is the accident this module's
        # interlocks exist to make impossible. Asserting the sentinel against that
        # set instead made the branch unreachable: `fork_child=False` could only
        # ever be entered by a caller who then tripped this very line, so a
        # single-member process group - the shape a `workers = 0` dev instance
        # actually runs (see test_gc_still_stops_a_runaway_whose_group_has_exactly
        # _one_member) - could not be staged at all. The sentinel is a legal
        # RESULT and never a legal TARGET: it is not added to `self.spawned`
        # above, so `reap` never signals it, and `seed_lease` below refuses it
        # like any other pid this module did not spawn.
        assert not child or child not in _FORBIDDEN_PIDS, (
            f"harness safety: the spawned child {child} is this process, its group "
            "or an ancestor"
        )
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
        # INTERLOCK 1, re-asserted at TEARDOWN. Every pid in `self.spawned` is
        # about to be SIGKILLed, and `os.kill(0, ...)` does not mean "pid 0" - it
        # signals THIS process's entire group, i.e. the runner and its shell. The
        # set is vetted when a pid enters it, but vetting the producer is not the
        # same as vetting the syscall: a set that somehow holds a forbidden pid is
        # a bug to REPORT, never one to execute. Measured while mutation-testing
        # this module: letting the no-child sentinel 0 into the set killed the
        # in-flight pytest run outright (exit 137) with no failure report at all -
        # exactly the "no trace" failure this whole module exists to prevent. So
        # drop them BEFORE the kill loop, reap the genuine children anyway (a
        # teardown that bails early leaks the very processes it exists to remove),
        # and fail loudly afterwards.
        unsafe = sorted(self.spawned & _FORBIDDEN_PIDS)
        self.spawned -= _FORBIDDEN_PIDS
        for pid in sorted(self.spawned):
            with contextlib.suppress(ProcessLookupError, OSError):
                os.kill(pid, signal.SIGKILL)
        for pid in sorted(self.spawned):
            with contextlib.suppress(ChildProcessError, OSError):
                os.waitpid(pid, os.WNOHANG)
        assert not unsafe, (
            f"harness safety: the reap set held {unsafe}, which name this process, "
            "its group or an ancestor (0 signals the WHOLE group). They were NOT "
            "signalled - fix whatever put them there"
        )

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

    # The no-child SENTINEL is vetted as a sentinel, not as a pid. Both interlocks
    # must survive that distinction, or `fork_child=False` becomes a hole in them
    # rather than the branch it is meant to be.
    solo_leader, solo_child = harness.spawn(fork_child=False)
    assert solo_child == 0, (
        "fork_child=False must report the no-child sentinel, not a pid"
    )
    assert 0 not in harness.spawned, (
        "INTERLOCK 1: pid 0 must never enter the reap set - `os.kill(0, SIGKILL)` "
        "signals THIS process's entire group, i.e. the test runner and its shell"
    )
    assert solo_leader not in _FORBIDDEN_PIDS and os.getpgid(solo_leader) == solo_leader, (
        "a single-member group must still be a group of its OWN, disjoint from ours"
    )
    with pytest.raises(AssertionError):
        harness.seed_lease(tmp_path / "nope-zero", 0)  # INTERLOCK 2 refuses the sentinel
    assert not (tmp_path / "nope-zero").exists(), "a refused seed must write NOTHING"


def test_the_command_line_rung_survives_an_80_column_ps(harness, alloc_home, tmp_path, capfd):
    """REGRESSION - this is the CI failure, as a test.

    `ps -o args=` prints `args` as a DISPLAY column and procps truncates it to the
    screen width, defaulting to 80 characters wherever it cannot determine one -
    which is what a GitHub runner and a plain container both do, while a developer
    workstation does not. The tokens that corroborate a lease (`odoo-bin`,
    `-d <db>`, the `<db>-<port>.conf` basename) sit at the END of a long command
    line, so they were precisely the bytes cut off: the rung silently reported
    "not proven", the allocator refused to signal, and a genuine runaway server
    was never reclaimed - on CI only.

    `COLUMNS=80` reproduces that environment deterministically. The rung must
    still read the FULL argv (via `/proc/<pid>/cmdline`, or `ps -ww` off-Linux)
    and still prove ownership."""
    alloc = _import_allocator()
    db = "odoo_17_t_widthproof"
    leader, child = harness.spawn(argv_tail=[
        str(_fake_odoo_bin(tmp_path)), "-c", f"{tmp_path}/conf/{db}-8069.conf", "-d", db])
    os.environ["COLUMNS"] = "80"  # restored in the finally below
    try:
        truncating = subprocess.run(["ps", "-o", "args=", "-p", str(leader)],
                                    capture_output=True, text=True)
        assert truncating.returncode == 0
        if len(truncating.stdout.strip()) > 80:
            pytest.skip("this host's ps ignores COLUMNS, so the truncation cannot be staged")
        assert db not in truncating.stdout, (
            "test setup: the truncated form must have lost the corroborating tokens, "
            "otherwise this test proves nothing"
        )
        argv, how = alloc._pid_argv(leader)
        assert argv, "the argv must still be readable when ps would truncate it"
        assert alloc._argv_names_lease(argv, db), (
            f"the command-line rung must survive an 80-column ps (read via {how}); the "
            f"argv it saw was {argv!r}"
        )
        # The `ps` FALLBACK must itself be truncation-proof, or this whole class of
        # failure just moves to macOS/BSD where /proc does not exist and no Linux CI
        # would ever see it again.
        assert alloc._argv_names_lease(alloc._ps_argv(leader), db), (
            "the ps fallback must pass -ww (unlimited width); without it the same "
            "80-column truncation returns on every host that has no /proc"
        )
        harness.seed_lease(alloc_home, leader, db_name=db)
        assert alloc.cmd_gc({}) == 0
        survivors = _wait_dead(harness, leader, child)
        assert survivors == [], (
            f"a runaway must still be reclaimed under an 80-column ps; {survivors} survived"
        )
        assert "ownership PROVEN by cmdline" in capfd.readouterr().err
    finally:
        os.environ.pop("COLUMNS", None)


def test_the_port_rung_needs_no_external_binary(harness, monkeypatch):
    """REGRESSION - the second gap CI's environment exposed: a minimal container
    has NO lsof, ss or fuser (observed: all three absent on ubuntu:24.04), so a
    binary-only port rung means a containerised runtime can never prove ownership
    and therefore never reclaims a runaway. `/proc/net/tcp` + `/proc/<pid>/fd`
    answer the same question with no binary at all."""
    alloc = _import_allocator()
    if alloc._proc_listening_inodes(0) is None:
        pytest.skip("no readable /proc/net/tcp on this host")
    port = _free_port()
    leader, _ = harness.spawn(listen_port=port, argv_tail=["opaque-server-name"])
    monkeypatch.setattr(alloc, "_which", lambda binary: None)  # no lsof/ss/fuser at all
    monkeypatch.setattr(alloc, "_port_listener_pids", lambda port: None)

    holder, how = alloc._port_holder_in_group(leader, port)
    assert holder is not None, (
        "with /proc available the port rung must still attribute the listening socket "
        "to the lease's process group, with no external binary on PATH"
    )
    assert "/proc" in (how or ""), f"the answer must have come from /proc; got {how!r}"

    other_holder, other_how = alloc._port_holder_in_group(leader, _free_port())
    assert other_holder is None and other_how is not None, (
        "a port the group does NOT hold must be a definite MEASURED 'no' (holder None, "
        "how named), not an unmeasured (None, None) - only an unanswerable question may "
        f"report unmeasured; got {(other_holder, other_how)!r}"
    )


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
    """A port-holder question that could not be ASKED - neither `/proc/net/tcp`
    nor lsof/ss/fuser available - is "could not look", never "it is ours". The
    process survives, and the refusal must NAME the rung it could not evaluate,
    because "could not look" and "looked, no match" have different fixes."""
    alloc = _import_allocator()
    port = _free_port()
    leader, child = harness.spawn(listen_port=port, argv_tail=["bystander"])
    # Blind BOTH halves of the rung: /proc is the primary and the binaries are
    # the fallback, so removing only one leaves the question answerable.
    monkeypatch.setattr(alloc, "_which", lambda binary: None)
    monkeypatch.setattr(alloc, "_proc_listening_inodes", lambda port: None)
    assert alloc._port_holder_in_group(leader, port) == (None, None), (
        "with nothing able to answer, the rung must report UNMEASURED (None, None) - "
        "never an empty measurement, which would read as a definite 'not held'"
    )
    harness.seed_lease(alloc_home, leader, ports=[port])

    assert alloc.cmd_gc({}) == 0
    time.sleep(1.0)
    assert harness.alive(leader) and harness.alive(child)
    err = capfd.readouterr().err
    assert f"REFUSING to signal pid {leader}" in err
    assert "UNEVALUATED" in err, (
        f"the refusal must name the rung that went unevaluated; got: {err!r}"
    )


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


def test_gc_still_stops_a_runaway_whose_group_has_exactly_one_member(
        harness, alloc_home, tmp_path, capfd):
    """The single-process group - the shape a dev instance really runs as.

    Every other reclaim test here spawns a leader WITH a forked child, so a group
    stop is observable as two deaths. But Odoo forks HTTP workers only when
    `workers` is configured, and 50-instance-spinup.sh launches `setsid <py>
    <odoo-bin> -c <conf> -d <db>` with no such default - so on a developer machine
    the leased server's process GROUP has exactly ONE member. That is the boundary
    case for `_stop_group`, which signals the NEGATIVE pgid: a group of one is
    where "signal the group" and "signal the pid" coincide, and where an
    implementation that quietly resolved the wrong pgid (or fell back to the
    single-pid path) would still look green everywhere else.

    It went unprotected because the harness branch that stages it could not be
    entered: `spawn(fork_child=False)` reports child 0, and the interlock asserted
    that sentinel against `_FORBIDDEN_PIDS`, which contains 0.
    """
    alloc = _import_allocator()
    db = "odoo_17_t_solorunaway"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    leader, child = harness.spawn(
        fork_child=False,
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    assert child == 0, "test setup: this test is about a group with NO second member"
    assert os.getpgid(leader) == leader
    harness.seed_lease(alloc_home, leader, db_name=db)

    assert alloc.cmd_gc({}) == 0
    survivors = _wait_dead(harness, leader)
    assert survivors == [], (
        f"a runaway whose group has exactly one member must still be reclaimed; "
        f"{survivors} survived - a group stop that only works when the group has "
        "children never reclaims a plain `workers = 0` instance"
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
    # Skip ONLY where the rung is unavailable in BOTH forms (no readable
    # /proc/net/tcp and no lsof/ss/fuser) - i.e. never on Linux. It used to skip
    # whenever the binaries were missing, which silently excused a container from
    # proving the reclaim path at all.
    if alloc._port_holder_in_group(leader, port)[1] is None:
        pytest.skip("no /proc/net/tcp and no lsof/ss/fuser: port ownership is unobservable")
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
    # `.get`, not `[...]`: when corroboration fails the key is simply absent, and a
    # KeyError would report the symptom while hiding the cause. Assert the cause.
    recorded = _leases(alloc_home)[0]["owner"].get("pid_started")
    assert recorded is not None, (
        "no fingerprint was backfilled at all, which means ownership was not "
        "corroborated for a process that IS an odoo-bin invocation for this lease's "
        "database - the corroboration rungs could not read this environment (see the "
        "refusal on stderr for which rung went unevaluated)"
    )
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

    for name in ("_pid_alive", "_pid_argv", "_proc_argv", "_ps_argv",
                 "_port_holder_in_group", "_port_listener_pids", "_stop_group"):
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
# G4 - PARK and RESUME: the suspended state, and the transition back out of it
#
# `park` is the THIRD process-signalling call site in allocator.py (after
# `release` and `_gc`), which is why these live in this module rather than beside
# the plain gc tests: it stops the owner's process GROUP through the very gate
# every test above protects, and only then clears the pid. Its whole promise -
# "park holds DISK, never MEMORY" - is that stop; without it park would be a
# teardown loophole that reopens the RAM leak the SubagentStop gate exists to
# close, while LOOKING like a safe suspension.
#
# `resume` is the transition back. The assertion these tests exist for is
# assertion 3 below: a RESUMED lease must be judged by the PID arms again. A
# resume that left `parked_at` behind would leave a live, healthy server governed
# by a park budget alone - `_gc` would drop its database out from under it when
# that budget lapsed, and the teardown gate's parked exemption would exempt that
# live lease forever. One missing key, both harms.
#
# HARNESS SAFETY (the same two interlocks, re-stated because these tests are the
# ones that hand a pid to a WRITE path): a parked lease has no pid BY
# CONSTRUCTION, and every live pid named below comes from `harness.spawn` and is
# seeded through `harness.seed_lease`, which REFUSES any pid this module did not
# spawn. `resume --pid` is never given a raw pid, and never `os.getpid()`.
# --------------------------------------------------------------------------- #
def _parked_lease(alloc, home, harness, *, db="odoo_17_t_parked", age_s=0,
                  ttl_s=100, boot_id="__current__", drop=False, ports=(),
                  run_id="run-A", host=None):
    """A PARKED registry row: no pid, `parked_at` `age_s` seconds in the past.

    Written through `harness.seed_lease` (pid None) so the module's own interlock
    still vets it, then stamped with the park keys the way `cmd_park` stamps them.
    """
    harness.seed_lease(home, None, db_name=db, drop_on_release=drop,
                       ports=list(ports), run_id=run_id,
                       **({"host": host} if host is not None else {}))
    path = Path(home) / "runtime" / "leases.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    lease = reg["leases"][0]
    lease["owner"]["run_id"] = run_id
    lease["parked_at"] = alloc._now() - age_s
    lease["park_ttl_s"] = ttl_s
    if boot_id == "__current__":
        current = alloc._boot_id()
        if current:
            lease["parked_boot_id"] = current
    elif boot_id is not None:
        lease["parked_boot_id"] = boot_id
    path.write_text(json.dumps(reg), encoding="utf-8")
    return lease


def test_a_parked_lease_survives_gc_until_its_own_budget_lapses(harness, alloc_home):
    """G4.1 - a parked lease (fresh `parked_at`, NO pid) survives `gc`: the row is
    kept, no drop is attempted, and no reclaim record is emitted.

    The pre-park allocator had no way to express this at all: a pid-less row with
    an elapsed TTL is exactly what every parked lease looks like, so `gc` would
    condemn it and drop the database the caller deliberately preserved. The
    seeded row's ttl_s/heartbeat_at are DELIBERATELY expired (that is what
    `seed_lease` writes) - proving the park arm, not a fresh heartbeat, is what
    protects it."""
    alloc = _import_allocator()
    lease = _parked_lease(alloc, alloc_home, harness, age_s=0, ttl_s=100)
    assert alloc._now() - lease["heartbeat_at"] > lease["ttl_s"], (
        "test setup: the ordinary TTL must already be expired, or this proves nothing"
    )
    dropped = []
    alloc._drop_through_odoo = lambda lz, path=None: dropped.append(lz.get("db_name")) or True

    reg = {"leases": [dict(lease)]}
    records = alloc._gc(reg, "gc")

    assert records == [], "a parked lease within its budget must produce NO reclaim record"
    assert dropped == [], "a parked lease's database must never be dropped while it is parked"
    assert len(reg["leases"]) == 1, "the parked row must survive gc"


def test_an_expired_park_is_condemned_as_park_expired_and_drops_the_db(harness, alloc_home):
    """G4.2 - past `park_ttl_s`, gc reports EXACTLY `park-budget-expired` (not a
    TTL or pid reason - the arm that judged it is the one fact no later reader can
    re-derive) and the drop happens for a `drop_on_release` lease."""
    alloc = _import_allocator()
    db = "odoo_17_t_parkgone"
    lease = _parked_lease(alloc, alloc_home, harness, db=db, age_s=500, ttl_s=100, drop=True)
    dropped = []
    alloc._drop_through_odoo = lambda lz, path=None: dropped.append(lz.get("db_name")) or True

    reg = {"leases": [dict(lease)]}
    records = alloc._gc(reg, "gc")

    assert [r["reason"] for r in records] == [alloc.CONDEMN_PARK_EXPIRED], (
        f"an elapsed park budget must be reported as its own arm, got {records}"
    )
    assert dropped == [db], "an expired park must actually drop the database it was holding"
    assert reg["leases"] == [], "the expired parked row must be reclaimed"


def test_a_park_budget_that_only_elapsed_across_a_reboot_is_not_condemned(
        harness, alloc_home):
    """G4 edge case 1 - the host rebooted under the park. Wall-clock says the
    budget lapsed; the boot id says nobody was there to consume it. Protect the
    row: a reboot must not destroy a perfectly resumable database."""
    alloc = _import_allocator()
    lease = _parked_lease(alloc, alloc_home, harness, age_s=10_000, ttl_s=100,
                          boot_id="a-boot-that-is-not-this-one")
    if alloc._boot_id() is None:
        pytest.skip("no readable kernel boot id on this host: the arm degrades to plain TTL")
    assert alloc._condemn_reason(lease) is None, (
        "a park budget that elapsed only across a reboot must NOT be condemned - the "
        "park was never consumed"
    )


def test_an_unreadable_boot_id_degrades_to_the_plain_budget_never_to_a_reprieve(
        harness, alloc_home, monkeypatch):
    """The other half of edge case 1, and the one that would rot silently: where
    the boot id cannot be read at all (not Linux, or a container reporting the
    HOST's id), the arm must fall back to the plain budget comparison - not to a
    permanent reprieve that leaks the database forever, and not to a condemn on
    ambiguity."""
    alloc = _import_allocator()
    lease = _parked_lease(alloc, alloc_home, harness, age_s=500, ttl_s=100, boot_id=None)
    monkeypatch.setattr(alloc, "_boot_id", lambda: None)
    assert alloc._condemn_reason(lease) == alloc.CONDEMN_PARK_EXPIRED, (
        "with no boot id available on either side, an elapsed park budget must still expire"
    )


def test_park_stops_the_owner_group_before_it_clears_the_pid(
        harness, alloc_home, tmp_path, capfd):
    """Park holds DISK, never MEMORY. The stop is the whole reason park may
    satisfy the teardown gate at all: if park merely cleared the pid, the server
    would keep running with nothing left in the ledger able to name it, and park
    would be a hole in the RAM-leak fix wearing the face of a feature."""
    alloc = _import_allocator()
    db = "odoo_17_t_parkstop"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    leader, child = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    harness.seed_lease(alloc_home, leader, db_name=db, ports=[])
    token = _leases(alloc_home)[0]["token"]

    assert alloc.cmd_park({"token": token}) == 0

    survivors = _wait_dead(harness, leader, child)
    assert survivors == [], (
        f"park must stop the whole owner process GROUP; {survivors} survived - a park "
        "that leaves the server running frees no RAM and is a teardown loophole"
    )
    assert "ownership PROVEN by cmdline" in capfd.readouterr().err
    row = _leases(alloc_home)[0]
    assert row["owner"]["pid"] is None and row["owner"]["pid_started"] is None
    assert row["parked_at"] is not None and row["db_name"] == db, (
        "park keeps the database and stamps the park keys"
    )


def test_park_refuses_a_shared_lease_and_a_lease_with_no_server(harness, alloc_home):
    """The two refusals, each with its OWN exit code, because the remedies differ:
    a shared render target must be released when the server is finished with (3),
    and a lease with no bound pid has no server to stop and nothing to resume
    into (4) - which is also what makes a SECOND park on an already-parked lease
    a refusal instead of a silently re-stamped budget."""
    alloc = _import_allocator()
    harness.seed_lease(alloc_home, None, db_name="odoo_17_0", mode="shared")
    token = _leases(alloc_home)[0]["token"]
    assert alloc.cmd_park({"token": token}) == 3, "a shared lease is never parkable"

    harness.seed_lease(alloc_home, None, db_name="odoo_17_t_nopid")
    token = _leases(alloc_home)[0]["token"]
    assert alloc.cmd_park({"token": token}) == 4, "a lease with no owner pid is not RUNNING"

    lease = _parked_lease(alloc, alloc_home, harness)
    assert alloc.cmd_park({"token": lease["token"]}) == 4, (
        "an already-parked lease must be refused, not given a fresh budget"
    )


def test_a_resumed_lease_is_judged_by_the_pid_arms_again(
        harness, alloc_home, tmp_path, monkeypatch):
    """G4.3 - THE assertion this whole feature turns on (the review's C3).

    Seed a fresh park, resume it onto a live server, then advance the clock past
    `park_ttl_s`: the row must NOT be condemned while that pid is alive. Then kill
    the pid: it must be condemned as `owner-pid-dead`, NOT `park-budget-expired`.
    A resume that failed to DELETE the park keys passes neither half - it would
    drop a live server's database on budget expiry, and the SubagentStop teardown
    gate would exempt that live lease forever."""
    alloc = _import_allocator()
    db = "odoo_17_t_resumed"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    _parked_lease(alloc, alloc_home, harness, db=db, age_s=0, ttl_s=100)
    token = _leases(alloc_home)[0]["token"]
    leader, child = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: True)

    assert alloc.cmd_resume({"token": token, "pid": leader}) == 0

    row = _leases(alloc_home)[0]
    for key in ("parked_at", "park_ttl_s", "parked_boot_id"):
        assert key not in row, (
            f"resume must DELETE {key!r}; a survivor re-governs a LIVE lease by a park "
            "budget, which is exactly the harm park exists to prevent"
        )
    assert row["owner"]["pid"] == leader and row["owner"]["pid_started"], (
        "resume must record the new owner pid AND its recycling-resistant fingerprint"
    )

    # Past what WOULD have been the park budget, and past the ordinary TTL too.
    row["heartbeat_at"] = alloc._now() - 100_000
    row["ttl_s"] = 1
    assert alloc._condemn_reason(row) is None, (
        "a resumed, verified-alive owner must be protected by the PID arms - not "
        "condemned by a park budget that no longer applies"
    )

    for pid in (child, leader):
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, signal.SIGKILL)
    assert _wait_dead(harness, leader) == []
    assert alloc._condemn_reason(row) == alloc.CONDEMN_PID_DEAD, (
        "once the resumed server dies the lease is condemned by the PID arm, and the "
        "reason must name that arm - never the park arm it left behind"
    )


def test_two_agents_racing_to_resume_the_same_lease_cannot_both_win(
        harness, alloc_home, tmp_path, monkeypatch):
    """G4 edge case 4 - resolved BY CONSTRUCTION, not by timing. `resume` requires
    `parked_at` to be present; the first caller clears it, so the second is
    refused.

    What the refusal can and cannot promise is stated exactly, because the
    comfortable version of this claim is false: BOTH racers already launched a
    server before either could call `resume` (the call needs a live pid to
    corroborate), so "neither reaches a launch on the other's port" was never
    true. What IS true is that the loser is refused with a code that means STOP
    THE SERVER YOU LAUNCHED - never the `bind` fallback code - and that the
    winner's pid survives untouched."""
    alloc = _import_allocator()
    db = "odoo_17_t_race"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    _parked_lease(alloc, alloc_home, harness, db=db)
    token = _leases(alloc_home)[0]["token"]
    leader, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    second, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: True)

    assert alloc.cmd_resume({"token": token, "pid": leader}) == 0
    assert alloc.cmd_resume({"token": token, "pid": second}) == 6, (
        "the loser of a resume race must be refused with the code that means `another "
        "live server already holds this lease` - never 3, which its caller reads as `this "
        "was never parked, bind my pid instead` and would use to take the lease off the "
        "winner"
    )
    assert _leases(alloc_home)[0]["owner"]["pid"] == leader, (
        "the winner's pid must survive the loser's attempt"
    )


def test_resume_refuses_when_the_database_was_dropped_while_parked(
        harness, alloc_home, tmp_path, monkeypatch, capfd):
    """G4 edge case 2 - the database went away under the park. Refuse with its own
    exit code and NAME `release` as the next step; never launch a server against a
    database that no longer exists. An UNDETERMINABLE probe is deliberately not a
    refusal (tested by the sibling above, which resumes on a True probe): failing
    to look is not the same as looking and finding nothing."""
    alloc = _import_allocator()
    db = "odoo_17_t_gonedb"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    _parked_lease(alloc, alloc_home, harness, db=db)
    token = _leases(alloc_home)[0]["token"]
    leader, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: False)

    assert alloc.cmd_resume({"token": token, "pid": leader}) == 5
    assert "release" in capfd.readouterr().err, (
        "the refusal must name the verb that cleans this lease up, or the caller is stuck"
    )
    assert _leases(alloc_home)[0]["parked_at"] is not None, (
        "a refused resume must leave the lease PARKED - a half-transitioned row is the "
        "state the compare-and-set exists to make impossible"
    )


def test_resume_refuses_a_pid_whose_ownership_it_cannot_corroborate(
        harness, alloc_home, monkeypatch, capfd):
    """Park cleared `owner.pid_started`, so resume's proof can only come from an
    independent observation - in practice the `/proc/<pid>/cmdline` rung. A pid
    that corroborates nothing must be refused: resume WRITES that pid onto the
    lease, so release/gc would later group-signal it, and naming a pid the lease
    did not spawn is how an unrelated session gets killed."""
    alloc = _import_allocator()
    _parked_lease(alloc, alloc_home, harness, db="odoo_17_t_stranger")
    token = _leases(alloc_home)[0]["token"]
    stranger, _ = harness.spawn(argv_tail=["not-an-odoo-server-at-all"])
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: True)

    assert alloc.cmd_resume({"token": token, "pid": stranger}) == 4
    assert "ownership is NOT proven" in capfd.readouterr().err
    assert _leases(alloc_home)[0]["parked_at"] is not None, (
        "a refused resume must leave the lease parked and pid-less"
    )


def test_query_state_parked_finds_the_lease_and_reports_a_cross_run_attach(
        harness, alloc_home, capfd):
    """The DISCOVERY half. A mechanism nothing can reach is this plugin's
    signature defect, so the rung a returning agent actually calls is asserted
    here: `query --state parked` must find this run's own parked lease silently,
    and must REPORT (never silently swallow) an attach to another run's parked
    lease on this host."""
    alloc = _import_allocator()
    db = "odoo_17_t_discover"
    _parked_lease(alloc, alloc_home, harness, db=db, ports=[8170], run_id="run-A")

    assert alloc.cmd_query({"series": "17.0", "state": "parked", "run_id": "run-A"}) == 0
    out = capfd.readouterr().out
    assert "ALLOC_DB_NAME=" in out and db in out and "ALLOC_PARKED_AT=" in out
    assert "ALLOC_ATTACHED_FROM_RUN" not in out, (
        "resuming your OWN parked lease inherits nothing - there is nothing to report"
    )

    assert alloc.cmd_query({"series": "17.0", "state": "parked", "run_id": "run-B"}) == 0
    out = capfd.readouterr().out
    assert "ALLOC_ATTACHED_FROM_RUN=run-A" in out, (
        "inheriting another run's parked instance carries its data state - report the "
        "attach rather than gate it"
    )

    assert alloc.cmd_query({"series": "18.0", "state": "parked", "run_id": "run-A"}) == 1
    assert alloc.cmd_query({"series": "17.0"}) == 1, (
        "the DEFAULT query is shared-only and must be unchanged by any of this"
    )


def test_a_parked_lease_on_another_host_stays_gated_behind_force_attach(
        harness, alloc_home):
    """The one case that stays a gate rather than a report: off-host, the lease's
    database may live on a cluster this host cannot reach at all."""
    alloc = _import_allocator()
    _parked_lease(alloc, alloc_home, harness, db="odoo_17_t_offhost", host=FOREIGN_HOST)
    assert alloc.cmd_query({"series": "17.0", "state": "parked", "run_id": "run-A"}) == 1
    assert alloc.cmd_query({"series": "17.0", "state": "parked", "force_attach": True}) == 0


def test_an_expired_park_is_never_offered_as_resumable(harness, alloc_home):
    """Discovery must not hand a caller a database that gc is about to destroy."""
    alloc = _import_allocator()
    _parked_lease(alloc, alloc_home, harness, db="odoo_17_t_expired",
                  age_s=500, ttl_s=100)
    assert alloc.cmd_query({"series": "17.0", "state": "parked", "run_id": "run-A"}) == 1


def test_query_state_parked_never_offers_a_lease_whose_database_is_gone(
        harness, alloc_home, capfd, monkeypatch):
    """The PRE-LAUNCH half of "no server is ever started against a database that
    is gone", and the only rung that can carry it.

    `resume` corroborates a pid, so it can only run AFTER a server exists - by
    then a process is already up against the missing database. This command runs
    BEFORE the caller has coordinates to launch anything with, so a lease whose
    database is provably gone must be SKIPPED here, with `release` named, rather
    than handed over as resumable."""
    alloc = _import_allocator()
    db = "odoo_17_t_droppedunderpark"
    _parked_lease(alloc, alloc_home, harness, db=db, ports=[8171], run_id="run-A")
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: False)

    assert alloc.cmd_query({"series": "17.0", "state": "parked", "run_id": "run-A"}) == 1, (
        "a parked lease with no database left is not resumable, so discovery must report "
        "nothing to resume - not offer coordinates to launch against"
    )
    err = capfd.readouterr().err
    assert db in err and "release" in err, (
        f"the skip must NAME the lease and the verb that cleans it up, or the caller is left "
        f"with a row nothing tells it to remove; got {err!r}"
    )
    assert alloc.cmd_query(
        {"series": "17.0", "state": "parked", "run_id": "run-A", "force_attach": True}) == 1, (
        "--force-attach widens the HOST scope; it may not overrule a database that is not there"
    )


@pytest.mark.parametrize("probe,expected", [(True, 0), (None, 0)])
def test_only_a_PROVEN_absent_database_withholds_a_parked_lease(
        harness, alloc_home, monkeypatch, probe, expected):
    """The falsification of the test above, and the rule that keeps the skip from
    becoming a new way to strand a resumable instance: PRESENT is offered, and so
    is COULD-NOT-LOOK. `dropdb --if-exists` exits 0 for a database that never
    existed, which is exactly why "we failed to look" may never be read as "it is
    not there" - and a wrong guess here costs a rebuild that was not needed,
    while `resume`'s own probe is still the second net under it."""
    alloc = _import_allocator()
    _parked_lease(alloc, alloc_home, harness, db="odoo_17_t_probe", run_id="run-A")
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: probe)
    assert alloc.cmd_query(
        {"series": "17.0", "state": "parked", "run_id": "run-A"}) == expected


def test_resume_tells_a_first_launch_apart_from_a_lost_resume_race(
        harness, alloc_home, tmp_path, monkeypatch, capfd):
    """Two OPPOSITE remedies used to share exit 3, and the caller took the wrong
    one for both.

    `50-instance-spinup.sh::_bind_exclusive` treats exit 3 as "ordinary first
    launch, fall back to `bind`". That is right when the lease was simply never
    parked. It is catastrophic when the lease is not parked because ANOTHER agent
    already resumed it and its server is running: binding there takes the lease
    off the process that actually holds the database and port, so `release`/`gc`
    would later stop the wrong group. The two cases are decidable - a live,
    same-host owner pid - so they get their own codes."""
    alloc = _import_allocator()
    db = "odoo_17_t_racecodes"
    conf = f"{tmp_path}/conf/{db}-8069.conf"
    harness.seed_lease(alloc_home, None, db_name=db)
    token = _leases(alloc_home)[0]["token"]
    mine, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])
    monkeypatch.setattr(alloc, "_db_present", lambda lz, path=None: True)

    assert alloc.cmd_resume({"token": token, "pid": mine}) == 3, (
        "a lease that was never parked and holds no live server is the ordinary first "
        "launch - the one case whose caller-side fallback to `bind` is correct"
    )
    assert "bind" in capfd.readouterr().err, (
        "and the refusal must name that fallback, or the caller cannot take it"
    )

    # The winner of the race: its pid is now the lease's live owner.
    assert alloc.cmd_bind({"token": token, "pid": mine}) == 0
    loser, _ = harness.spawn(
        argv_tail=[str(_fake_odoo_bin(tmp_path)), "-c", conf, "-d", db])

    assert alloc.cmd_resume({"token": token, "pid": loser}) == 6, (
        "a lease already held by a LIVE same-host server is the lost resume race, not a "
        "first launch - it must NOT return the code that means `bind`"
    )
    err = capfd.readouterr().err
    assert str(mine) in err and "STOP" in err, (
        f"the refusal must name the pid that actually holds the lease and tell the loser to "
        f"stop the server it just launched; got {err!r}"
    )
    assert _leases(alloc_home)[0]["owner"]["pid"] == mine, (
        "the winner's pid must survive the loser's attempt"
    )

    for pid in (mine, loser):
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, signal.SIGKILL)
    assert _wait_dead(harness, mine, loser) == []


def test_reap_orphans_can_never_list_a_parked_leases_database(harness, alloc_home):
    """The SECOND destructive reclaimer, verified rather than assumed. It skips
    any db_name referenced by ANY lease - live or stale - so a parked lease is
    already safe by a predicate that predates park. Asserted here because
    'somebody checked' is not evidence."""
    alloc = _import_allocator()
    db = "odoo_17_t_deadbeef"
    _parked_lease(alloc, alloc_home, harness, db=db, age_s=10_000, ttl_s=1)
    leased = {lz.get("db_name") for lz in alloc._read_registry()["leases"]}
    assert db in leased
    candidates, skipped = alloc._reap_candidates(
        [{"name": db, "age_s": 10_000.0}], leased, ["odoo_17"], 0)
    assert candidates == [] and skipped == [], (
        "a parked lease's database must never even be LISTED as an orphan candidate - "
        "not as a candidate, and not as a skip: it is simply not this command's business"
    )
    # Falsification: the SAME database with no lease reference IS a candidate, so
    # the assertion above is proving the lease reference, not an inert predicate.
    unleased, _ = alloc._reap_candidates(
        [{"name": db, "age_s": 10_000.0}], set(), ["odoo_17"], 0)
    assert [c["name"] for c in unleased] == [db]


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
