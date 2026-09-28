"""Behavior tests for scripts/lib/session_anchor.py - process identity and the
session liveness anchor the allocator protects leases with.

What is protected (behavior, not code):
  - a fingerprint identifies ONE process across time and is independent of the
    caller's timezone and locale (the old `ps -o lstart=` string was not, and a
    live server fingerprinted under one TZ was later condemned as "recycled"
    and killed by a caller in another);
  - a LEGACY timezone-dependent fingerprint is matched in the local zone OR UTC
    and is never reported as a mismatch;
  - `/proc/<pid>/stat` is parsed correctly even when the process name contains
    spaces and ')';
  - the anchor is discovered in the documented precedence, and its state is
    "dead" only on proof.

Every live pid named here is a `sleep` (or copy of one) THIS module started.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import session_anchor as sa  # noqa: E402

LINUX_PROC = Path("/proc/self/stat").exists()
needs_proc = pytest.mark.skipif(not LINUX_PROC, reason="needs Linux /proc")


@pytest.fixture
def sleeper():
    procs = []

    def _start(argv=None):
        proc = subprocess.Popen(argv or ["sleep", "300"], start_new_session=True)
        procs.append(proc)
        return proc

    yield _start
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _kill(proc):
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)


def _lstart(pid, tz=None):
    env = dict(os.environ)
    if tz is not None:
        env["TZ"] = tz
        env["LC_ALL"] = "C"
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                         text=True, env=env).stdout.strip()
    if not out:
        pytest.skip("`ps -o lstart=` gives no answer on this host")
    return out


# --------------------------------------------------------------------------- #
# fingerprints
# --------------------------------------------------------------------------- #
def test_a_fingerprint_is_stable_for_one_process_and_differs_for_another(sleeper):
    a = sleeper()
    # A recycled pid is necessarily held by a LATER process; stage "later" by
    # more than one clock tick (the proc scheme's granularity).
    time.sleep(0.1)
    b = sleeper()
    fa = sa.fingerprint(a.pid)
    assert fa, "a live process must be fingerprintable on this host"
    assert sa.fingerprint(a.pid) == fa, "the same process must fingerprint identically"
    assert sa.fp_verdict(fa, a.pid) == sa.VERDICT_MATCH
    # On a host whose clock granularity is a whole second (the ps scheme) two
    # processes may collide; the proc scheme (clock ticks) does not.
    if fa.startswith(sa.SCHEME_PROC):
        assert sa.fp_verdict(fa, b.pid) == sa.VERDICT_MISMATCH, (
            "a different process holding another pid must be a PROVEN mismatch"
        )


def test_a_fingerprint_does_not_depend_on_the_callers_timezone(sleeper):
    """Measured in two different zones, the SAME process must fingerprint the
    same - the property the legacy `ps -o lstart=` fingerprint lacked."""
    proc = sleeper()
    code = ("import sys; sys.path.insert(0, %r); import session_anchor as sa; "
            "print(sa.fingerprint(%d))" % (str(LIB), proc.pid))
    answers = set()
    for tz in ("UTC", "Asia/Tokyo", "America/Los_Angeles"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "TZ": tz, "LC_ALL": "C"}).stdout.strip()
        answers.add(out)
    assert len(answers) == 1 and "None" not in answers, answers


def test_a_process_recorded_in_another_boot_is_a_mismatch(sleeper):
    proc = sleeper()
    fp = sa.fingerprint(proc.pid)
    if not fp or not fp.startswith(sa.SCHEME_PROC):
        pytest.skip("no /proc boot id on this host")
    start = fp.rpartition(":")[2]
    assert sa.fp_verdict("proc:some-other-boot:" + start, proc.pid) == sa.VERDICT_MISMATCH


@pytest.mark.parametrize("zone", ["local", "UTC"])
def test_a_legacy_fingerprint_recorded_in_the_local_zone_or_utc_still_matches(sleeper, zone):
    """Rows written before the TZ-independent scheme carry a bare lstart taken in
    whatever TZ the recorder had. Both the local zone and UTC are tried."""
    proc = sleeper()
    legacy = _lstart(proc.pid, None if zone == "local" else "UTC")
    assert sa.fp_verdict(legacy, proc.pid) == sa.VERDICT_MATCH


def test_a_legacy_fingerprint_matching_neither_zone_is_unknown_never_a_mismatch(sleeper):
    """Recorded in a THIRD zone (UTC+14): the value is genuinely about this
    process, yet matches neither comparison. Calling that a mismatch is exactly
    how a live server got killed as "recycled"; it must be "unknown"."""
    proc = sleeper()
    third = _lstart(proc.pid, "Pacific/Kiritimati")
    if third in (_lstart(proc.pid), _lstart(proc.pid, "UTC")):
        pytest.skip("the host's local zone coincides with the probe zone")
    assert sa.fp_verdict(third, proc.pid) == sa.VERDICT_UNKNOWN
    assert sa.fp_verdict("Thu Jan  1 00:00:00 1970", proc.pid) == sa.VERDICT_UNKNOWN


def test_an_unmeasurable_or_absent_fingerprint_is_unknown():
    assert sa.fp_verdict(None, os.getpid()) == sa.VERDICT_UNKNOWN
    assert sa.fp_verdict("", os.getpid()) == sa.VERDICT_UNKNOWN
    assert sa.fingerprint("not-a-pid") is None


# --------------------------------------------------------------------------- #
# /proc/<pid>/stat parsing
# --------------------------------------------------------------------------- #
@needs_proc
def test_proc_stat_is_parsed_after_the_last_paren_even_with_a_hostile_name(sleeper, tmp_path):
    """The process name (field 2) is free text inside parentheses and may itself
    contain spaces and ')'. A naive split shifts every later field; the start
    time must still be field 22. Oracle, independent of the parser: the kernel's
    boot time (btime) plus starttime/CLK_TCK must equal now minus the process's
    elapsed time as `ps` reports it."""
    hostile = tmp_path / "a b) c (d"
    shutil.copy2(shutil.which("sleep"), hostile)
    proc = sleeper([str(hostile), "300"])
    time.sleep(0.2)
    comm, _fields = sa._proc_stat(proc.pid)
    assert comm == "a b) c (d"[:15], comm

    start = sa.proc_starttime(proc.pid)
    assert start and start.isdigit(), start
    btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                 if line.startswith("btime "))
    ticks = os.sysconf("SC_CLK_TCK")
    etimes = subprocess.run(["ps", "-o", "etimes=", "-p", str(proc.pid)], capture_output=True,
                            text=True).stdout.strip()
    if not etimes.isdigit():
        pytest.skip("`ps -o etimes=` unavailable")
    started_wall = btime + int(start) / ticks
    assert abs(started_wall - (time.time() - int(etimes))) <= 3, (
        f"starttime {start} does not describe when the process started; the stat line "
        "was mis-split around the hostile name"
    )


# --------------------------------------------------------------------------- #
# the anchor
# --------------------------------------------------------------------------- #
def test_an_explicit_anchor_wins_and_none_disables_anchoring(sleeper):
    proc = sleeper()
    fp = sa.fingerprint(proc.pid)
    env = {sa.ANCHOR_ENV: sa.format_anchor(proc.pid, fp), sa.SESSION_ID_ENV: "sess-1",
           sa.CLAUDE_PID_ENV: str(os.getpid())}
    anchor = sa.discover_anchor(env)
    assert anchor == {"pid": proc.pid, "started": fp, "session_id": "sess-1", "source": "env"}
    assert sa.discover_anchor({**env, sa.ANCHOR_ENV: "none"}) is None


def test_claude_pid_is_the_next_rung_and_a_malformed_explicit_value_is_ignored(sleeper):
    proc = sleeper()
    env = {sa.ANCHOR_ENV: "garbage", sa.CLAUDE_PID_ENV: str(proc.pid)}
    anchor = sa.discover_anchor(env)
    assert anchor["pid"] == proc.pid and anchor["source"] == "claude-pid"
    assert anchor["started"] == sa.fingerprint(proc.pid)


def test_an_agent_cli_ancestor_is_found_when_no_env_names_one(tmp_path):
    """The launch shape with no CLAUDE_PID (a stdio MCP server, a hook): walk up
    the process tree to the nearest `claude`. Staged with a python copy NAMED
    `claude` whose child asks for the anchor with an empty environment."""
    fake = tmp_path / "claude"
    real_python = os.path.realpath(sys.executable)
    try:
        os.symlink(real_python, fake)
    except OSError:
        pytest.skip("cannot stage a process named claude")
    child = ("import sys; sys.path.insert(0, %r); import session_anchor as sa, os; "
             "a = sa.discover_anchor({}); "
             "print(a['source'] if a else 'none', a['pid'] if a else 0, os.getppid())"
             % str(LIB))
    parent = "import subprocess, sys; sys.exit(subprocess.call([sys.argv[1], '-c', sys.argv[2]]))"
    out = subprocess.run([str(fake), "-c", parent, real_python, child],
                         capture_output=True, text=True, timeout=60)
    comm = Path("/proc/self/comm")
    if not comm.exists():
        pytest.skip("needs /proc to name the ancestor")
    source, pid, ppid = out.stdout.split()
    assert source == "ancestor" and pid == ppid, (
        f"the child's parent is the process named claude and must be the anchor: "
        f"{out.stdout!r} {out.stderr!r}"
    )


def test_anchor_state_is_dead_only_on_proof(sleeper):
    proc = sleeper()
    anchor = {"pid": proc.pid, "started": sa.fingerprint(proc.pid)}
    assert sa.anchor_state(anchor) == sa.STATE_ALIVE
    assert sa.anchor_state(anchor, host="another-host") == sa.STATE_UNKNOWN, (
        "a pid recorded on another host means nothing here"
    )
    assert sa.anchor_state({"pid": proc.pid, "started": None}) == sa.STATE_UNKNOWN, (
        "a live pid with no fingerprint is not PROVEN to be the anchor"
    )
    _kill(proc)
    assert sa.anchor_state(anchor) == sa.STATE_DEAD
