"""Behavior tests for the RECORD every allocator reclamation must leave behind.

`allocator.py`'s `_gc` is destructive: for each lease `_is_stale` condemns it
SIGTERMs the owner's process group and DROPS the database, then removes the
registry row - and the registry was the only place those coordinates existed.
`gc` (the verb a human deliberately types) reported what it took; `acquire` (the
verb every build, test run and subagent dispatch calls constantly) ran the same
destruction as a silent side effect. That asymmetry is what these tests close.

The contract, stated as behavior: **after any command that reclaimed N leases, an
operator can determine FROM THAT COMMAND'S OWN OUTPUT which leases were
reclaimed and why** - without consulting the registry, which by then no longer
contains them. "Why" means the ARM of `_is_stale` that condemned the lease (dead
pid / recycled pid / TTL after unprovable liveness): the coordinates can be
recovered from an earlier `ALLOC_*` block, but the reason cannot be reconstructed
afterwards at all.

Two channels are asserted, both observable:
  - the command's own STDERR, one line per reclaimed lease. Never stdout:
    `cmd_acquire`'s stdout is a PROTOCOL (`eval $(allocator.py acquire ...)`),
    so a prose notice interleaved there is executed by the caller's shell -
    covered by `test_the_notice_stays_off_the_acquire_protocol_stream` and by an
    actual `eval` in `test_an_eval_of_the_acquire_output_survives_a_reclaim`.
  - an append-only evidence log under `$ODOO_AI_HOME/logs/`, because a
    subagent's stderr is frequently not what the human ends up reading. Its
    reclaim policy is asserted, not assumed, by
    `test_the_evidence_log_survives_the_state_root_sweep`.

HARNESS SAFETY - read before editing. This module drives code that SIGTERMs
process GROUPS and DROPS DATABASES. It builds no harness of its own: it reuses
`test_allocator_signal_ownership.Harness`, which already owns the two interlocks
that make naming a foreign process impossible (`spawn` is the only source of a
live pid and puts it in its OWN session/group; `seed_lease` REFUSES any pid this
module did not spawn, and refuses this process, its group and every ancestor).
A THIRD interlock is added here, for the database half: `_seed_many` asserts
`drop_on_release is False` on every seeded row BEFORE writing the registry, so
`_gc`'s `_drop_through_odoo` branch is unreachable from this module - no
database, real or imagined, can be dropped by these tests. Every acquire runs
with `--no-create` for the same reason.
"""

import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The interlocked harness (and the two sentinels its interlock 2 permits) plus
# the allocator loader - reused, never re-implemented. See this module's
# docstring.
from test_allocator_signal_ownership import (  # noqa: E402
    DEAD_PID,
    FOREIGN_HOST,
    Harness,
    _import_allocator,
)

# The instance catalog + subprocess env every other allocator test already uses.
from test_allocator import INSTANCES_TOML, _env, _run  # noqa: E402

STATE_RECLAIM = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "state_reclaim.sh"

# Every allocator command promises a verdict, so a hang is a FAILURE, not a wait.
TIMEOUT = 60

# The condemn-reason vocabulary is the allocator's own SSOT; the tests read the
# strings from there rather than re-spelling them, so the notice and the
# assertions can never drift apart.
_REASON_CONSTANTS = ("CONDEMN_PID_DEAD", "CONDEMN_PID_RECYCLED", "CONDEMN_TTL_UNPROVABLE")

# acquire's stdout is a shell protocol: shlex-quoted NAME=value lines, plus `#`
# comments. Anything else in that stream is executed by an eval-ing caller.
_PROTOCOL_LINE_RE = re.compile(r"^(?:#.*|[A-Z_][A-Z0-9_]*=.*)$")


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    try:
        yield h
    finally:
        h.reap()


@pytest.fixture
def env_home(tmp_path):
    """(env, home): a subprocess env whose ODOO_AI_HOME/HOME are isolated to
    tmp_path and whose catalog is the shared INSTANCES_TOML."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(INSTANCES_TOML, encoding="utf-8")
    return _env(home, toml), home


def _reasons(alloc):
    """The declared vocabulary, or a RED failure naming exactly what is missing."""
    missing = [name for name in _REASON_CONSTANTS if not hasattr(alloc, name)]
    assert not missing, (
        "allocator.py must declare a condemn-reason vocabulary - one string per arm of "
        "`_is_stale` - so a reclaim notice can say WHY a lease was condemned and every "
        f"consumer reads the same spelling. Missing: {missing}"
    )
    values = {name: getattr(alloc, name) for name in _REASON_CONSTANTS}
    assert len(set(values.values())) == len(values), (
        f"each condemn arm needs its OWN reason string; got {values}"
    )
    return values


def _seed_many(harness, home, specs):
    """Write a MULTI-row registry, every row first vetted by the harness's own
    pid interlock.

    INTERLOCK 3 (this module's addition): a seeded row may never carry
    `drop_on_release: True`. `_gc` only reaches `_drop_through_odoo` for such a
    row, so this assertion - made BEFORE anything is written - is what makes
    these tests structurally incapable of dropping a database.
    """
    leases = [harness.seed_lease(home, pid, **fields) for pid, fields in specs]
    for lease in leases:
        assert lease["drop_on_release"] is False, (
            "harness safety: a seeded lease must never arm the DB-drop branch of _gc"
        )
    path = Path(home) / "runtime" / "leases.json"
    path.write_text(json.dumps({"schema_version": 2, "leases": leases}), encoding="utf-8")
    return leases


def _leases(home):
    path = Path(home) / "runtime" / "leases.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["leases"]


def _lines_naming(stream, needle):
    return [line for line in stream.splitlines() if needle in line]


def _notice_for(stream, token, where):
    """The ONE line of `stream` that reports `token` as reclaimed."""
    hits = _lines_naming(stream, token)
    assert len(hits) == 1, (
        f"exactly one line of {where} must report the reclaimed lease {token} - an "
        f"operator whose database vanished has nothing else left to read (the registry "
        f"row is gone). Found {len(hits)} such line(s). Full {where}:\n{stream}"
    )
    return hits[0]


def _dead_same_host_pid(harness):
    """A pid this module spawned and then PROVED dead - the `_is_stale` dead-pid
    arm needs a SAME-HOST pid, and the harness interlock only ever lets this
    module name a pid it created itself. The harness's double-fork orphans the
    leader to init, so its death is real (no zombie keeping `os.kill(pid, 0)`
    alive) and "the pid is gone" is observable rather than assumed."""
    leader, child = harness.spawn()
    for pid in (leader, child):
        if pid:
            os.kill(pid, signal.SIGKILL)
    deadline = time.time() + 15
    while time.time() < deadline and harness.alive(leader):
        time.sleep(0.02)
    assert not harness.alive(leader), f"the spawned stand-in {leader} refused to die"
    return leader


def _acquire(env, mode, *extra, run_id="run-B"):
    return _run(env, "acquire", "--series", "17.0", "--mode", mode, "--no-create",
                "--run-id", run_id, *extra, timeout=TIMEOUT)


# --------------------------------------------------------------------------- #
# 1 + 2 - the two implicit passes: every acquire path must report what it took
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", ["shared", "ephemeral"])
def test_an_acquire_that_reclaims_reports_what_it_reclaimed(harness, env_home, mode):
    """THE INCIDENT, as a test. An ephemeral database disappeared out from under
    running work; the command that destroyed it printed nothing, and the registry
    row naming it was gone in the same write. The failure then presents as a test
    suite that cannot connect, and the debugging goes somewhere else entirely.

    Cross-tenant on purpose: run-B's acquire reclaims run-A's lease (`_gc` walks
    the whole shared registry), so the notice must name the VICTIM's run_id, not
    the acquiring one.
    """
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    lease, = _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "1a" * 16,
                    "db_name": "odoo_17_0_t_deadbeef"}),
    ])

    proc = _acquire(env, mode, run_id="run-B")
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"
    assert lease["token"] not in [lz["token"] for lz in _leases(home)], (
        "test setup: the seeded lease must actually have been reclaimed, otherwise "
        "this test proves nothing about reporting a reclamation"
    )

    line = _notice_for(proc.stderr, lease["token"], "the acquire's stderr")
    assert "run-A" in line, (
        f"the notice must name the reclaimed lease's OWN run_id (the run that lost the "
        f"database), not the reclaiming one: {line!r}"
    )
    assert lease["db_name"] in line, f"the notice must name the destroyed database: {line!r}"
    assert str(DEAD_PID) in line, f"the notice must name the recorded owner pid: {line!r}"
    assert any(reason in line for reason in reasons.values()), (
        "the notice must carry the condemn REASON - the coordinates can be recovered "
        "from an earlier ALLOC_* block, the reason cannot be reconstructed at all. "
        f"Expected one of {sorted(reasons.values())} in: {line!r}"
    )


# --------------------------------------------------------------------------- #
# 3 - the reason must be the ARM, not a constant
# --------------------------------------------------------------------------- #
def test_each_condemn_arm_names_itself_in_the_notice(harness, env_home):
    """Three leases, three DIFFERENT arms of `_is_stale`, one command. Each
    notice must carry that lease's OWN arm: a single hardcoded reason string
    would satisfy a one-lease test while telling the operator nothing about
    which of the three destroyed their work."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home

    dead_pid = _dead_same_host_pid(harness)
    recycled_leader, _ = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    if alloc._pid_fingerprint(recycled_leader) is None:
        pytest.skip("no re-measurable pid fingerprint on this host - the recycled arm "
                    "cannot be staged")

    dead, recycled, unprovable = _seed_many(harness, home, [
        (dead_pid, {"token": "2a" * 16, "db_name": "odoo_17_0_t_aaaaaaaa"}),
        (recycled_leader, {"token": "2b" * 16, "db_name": "odoo_17_0_t_bbbbbbbb",
                           "owner": {"pid_started": "0"}}),
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "2c" * 16,
                    "db_name": "odoo_17_0_t_cccccccc"}),
    ])

    proc = _acquire(env, "shared")
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"
    survivors = [lz["token"] for lz in _leases(home)]
    for lease in (dead, recycled, unprovable):
        assert lease["token"] not in survivors, (
            f"test setup: {lease['token']} must have been condemned for this test to "
            f"say anything; surviving rows: {survivors}"
        )

    observed = {}
    for label, lease in (("dead", dead), ("recycled", recycled), ("unprovable", unprovable)):
        line = _notice_for(proc.stderr, lease["token"], "the acquire's stderr")
        hits = [r for r in reasons.values() if r in line]
        assert len(hits) == 1, (
            f"the {label} lease's notice must carry exactly one reason from the declared "
            f"vocabulary {sorted(reasons.values())}; got {hits} in {line!r}"
        )
        observed[label] = hits[0]

    assert len(set(observed.values())) == 3, (
        "a dead pid, a positively RECYCLED pid and a TTL expiry after unprovable "
        f"liveness are three different findings and must report three different "
        f"reasons; got {observed}"
    )
    assert observed["dead"] == reasons["CONDEMN_PID_DEAD"], observed
    assert observed["recycled"] == reasons["CONDEMN_PID_RECYCLED"], observed
    assert observed["unprovable"] == reasons["CONDEMN_TTL_UNPROVABLE"], observed


# --------------------------------------------------------------------------- #
# 4 + 5 - stdout is a protocol, not a log
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", ["shared", "ephemeral"])
def test_the_notice_stays_off_the_acquire_protocol_stream(harness, env_home, mode):
    """`eval $(allocator.py acquire ...)` is the documented call shape, so every
    stdout line is EXECUTED by the caller's shell. The reclaim record must
    therefore be on stderr and NOWHERE on stdout - reporting it correctly and
    reporting it on the wrong stream are two different fixes."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    lease, = _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "3a" * 16,
                    "db_name": "odoo_17_0_t_eeeeeeee"}),
    ])

    proc = _acquire(env, mode)
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"

    offenders = [ln for ln in proc.stdout.splitlines()
                 if ln.strip() and not _PROTOCOL_LINE_RE.match(ln)]
    assert offenders == [], (
        "every acquire stdout line must stay shell-eval-able (NAME=value or a # "
        f"comment); these would be executed as commands: {offenders}"
    )
    assert lease["token"] not in proc.stdout, (
        "the reclaim record must not reach the protocol stream - an eval-ing caller "
        f"would execute it. stdout:\n{proc.stdout}"
    )
    for reason in reasons.values():
        assert reason not in proc.stdout, f"{reason!r} must not appear on stdout"
    assert lease["token"] in proc.stderr, (
        "the record belongs on stderr - the same channel every other allocator refusal "
        f"uses. stderr:\n{proc.stderr}"
    )


def test_an_eval_of_the_acquire_output_survives_a_reclaim(harness, env_home):
    """The protocol assertion above, made literally: a real shell evals the real
    stdout of an acquire that reclaimed a lease. A prose notice on stdout shows up
    here as a non-zero rc and a `not found` diagnostic."""
    harness_env, home = env_home
    _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "4a" * 16,
                    "db_name": "odoo_17_0_t_ffffffff"}),
    ])
    alloc_py = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"
    script = (
        f'eval "$({shlex.quote(sys.executable)} {shlex.quote(str(alloc_py))} acquire '
        '--series 17.0 --mode ephemeral --no-create --run-id run-B 2>/dev/null)"\n'
        'printf "rc=%s token=%s\\n" "$?" "$ALLOC_TOKEN"\n'
    )
    proc = subprocess.run(["sh", "-c", script], capture_output=True, text=True,
                          env=harness_env, timeout=TIMEOUT)
    assert "not found" not in proc.stderr, (
        "the caller's shell tried to EXECUTE part of the acquire's stdout - that is a "
        f"reclaim notice on the protocol stream:\n{proc.stderr}"
    )
    assert re.search(r"rc=0 token=\w{32}", proc.stdout), (
        f"eval of the acquire output must set ALLOC_TOKEN and return 0; got "
        f"{proc.stdout!r} / {proc.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# 6 - MUST-NOT-CATCH: no reclamation, no noise
# --------------------------------------------------------------------------- #
def test_an_acquire_that_reclaims_nothing_stays_silent(harness, env_home):
    """A protected lease (live same-host pid whose fingerprint still matches) is
    NOT reclaimed even with an expired TTL, so nothing may be reported. A notice
    printed unconditionally would train every reader to ignore the channel."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    leader, _ = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    fingerprint = alloc._pid_fingerprint(leader)
    if fingerprint is None:
        pytest.skip("no re-measurable pid fingerprint on this host - a PROTECTED lease "
                    "cannot be staged")
    lease, = _seed_many(harness, home, [
        (leader, {"token": "5a" * 16, "db_name": "odoo_17_0_t_11111111",
                  "owner": {"pid_started": fingerprint}}),
    ])

    proc = _acquire(env, "ephemeral")
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"
    assert lease["token"] in [lz["token"] for lz in _leases(home)], (
        "test setup: a verified-alive owner must PROTECT its lease regardless of TTL"
    )
    assert lease["token"] not in proc.stderr, (
        f"nothing was reclaimed, so nothing may be reported:\n{proc.stderr}"
    )
    for reason in reasons.values():
        assert reason not in proc.stderr, (
            f"a reclaim reason was reported for a lease that survived:\n{proc.stderr}"
        )


# --------------------------------------------------------------------------- #
# 7 - MUST-NOT-CATCH: gc's existing protocol output is unchanged
# --------------------------------------------------------------------------- #
def test_gc_keeps_its_protocol_output_and_gains_the_record(harness, env_home):
    """`ALLOC_RECLAIMED=<token>` and the count line are `gc`'s existing, consumed
    stdout contract - the explicit verb keeps reporting exactly as before, and
    gains the same stderr record the implicit passes now emit."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    lease, = _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "6a" * 16,
                    "db_name": "odoo_17_0_t_22222222"}),
    ])

    proc = _run(env, "gc", timeout=TIMEOUT)
    assert proc.returncode == 0, f"gc failed:\n{proc.stdout}\n{proc.stderr}"
    assert f"ALLOC_RECLAIMED={lease['token']}" in proc.stdout, (
        f"gc's ALLOC_RECLAIMED= emission must stay byte-compatible:\n{proc.stdout}"
    )
    assert "# reclaimed 1 stale lease(s)" in proc.stdout, (
        f"gc's count line must stay unchanged:\n{proc.stdout}"
    )
    line = _notice_for(proc.stderr, lease["token"], "the gc's stderr")
    assert any(reason in line for reason in reasons.values()), (
        f"gc must also carry the condemn reason - the token alone does not say why: {line!r}"
    )


# --------------------------------------------------------------------------- #
# 8 - the evidence must outlive the process that emitted it
# --------------------------------------------------------------------------- #
def test_the_reclaim_record_outlives_the_process(harness, env_home):
    """A subagent's stderr is frequently not what the human ends up reading, and
    the registry row is gone. So the same record is appended under
    `$ODOO_AI_HOME/logs/`, machine-readable, one record per reclaimed lease."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    lease, = _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "7a" * 16,
                    "db_name": "odoo_17_0_t_33333333"}),
    ])

    proc = _acquire(env, "ephemeral")
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"

    logs = Path(home) / "logs"
    carriers = [p for p in sorted(logs.glob("*"))
                if p.is_file() and lease["token"] in p.read_text(encoding="utf-8")]
    assert len(carriers) == 1, (
        f"exactly one file under {logs} must carry the reclaim record for "
        f"{lease['token']}; found {[p.name for p in carriers]} "
        f"(dir listing: {[p.name for p in sorted(logs.glob('*'))] if logs.exists() else 'MISSING'})"
    )
    records = [json.loads(ln) for ln in carriers[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    mine = [r for r in records if r.get("token") == lease["token"]]
    assert len(mine) == 1, f"one record per reclaimed lease; got {records}"
    rec = mine[0]
    assert rec.get("db_name") == lease["db_name"]
    assert rec.get("run_id") == "run-A", f"the record must name the lease's own run: {rec}"
    assert str(rec.get("owner_pid")) == str(DEAD_PID), rec
    assert rec.get("reason") in reasons.values(), (
        f"the persisted record needs the same condemn reason as the notice: {rec}"
    )
    assert alloc.CONDEMN_REASONS, "the vocabulary must be enumerable for consumers"
    assert rec["reason"] in alloc.CONDEMN_REASONS, (
        f"the reason must come from the declared closed vocabulary: {rec}"
    )


# --------------------------------------------------------------------------- #
# 9 - the reclaim policy for the evidence log itself
# --------------------------------------------------------------------------- #
def test_the_evidence_log_survives_the_state_root_sweep(harness, env_home):
    """POLICY, asserted rather than inherited. `prune_stale_run_artifacts`
    (`state_reclaim.sh`) sweeps `$ODOO_AI_HOME/logs/` under an mtime bound plus a
    lease-registry guard - the right policy for a per-run build log, and exactly
    the WRONG one for this file: the reclaim log is the ONLY surviving evidence
    of a destroyed database, so a sweep would delete precisely the record needed
    to explain a deletion older than the bound. Its name is therefore outside the
    swept globs.

    The decoy proves the sweep really ran: same directory, same backdated mtime,
    an unleased db name - it must be gone while the evidence log stays.
    """
    env, home = env_home
    _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "8a" * 16,
                    "db_name": "odoo_17_0_t_44444444"}),
    ])
    proc = _acquire(env, "ephemeral")
    assert proc.returncode == 0, f"acquire failed:\n{proc.stdout}\n{proc.stderr}"

    logs = Path(home) / "logs"
    carriers = [p for p in sorted(logs.glob("*")) if p.is_file() and "8a" * 16 in
                p.read_text(encoding="utf-8")]
    assert len(carriers) == 1, f"no evidence log to test the policy on: {logs}"
    evidence = carriers[0]
    decoy = logs / "retired_db-20240101120000.log"
    decoy.write_text("a per-run build log whose lease is long gone\n", encoding="utf-8")

    ancient = time.time() - 400 * 24 * 7200
    for path in (evidence, decoy):
        os.utime(path, (ancient, ancient))

    script = (
        f'. {shlex.quote(str(STATE_RECLAIM))}\n'
        f'prune_stale_run_artifacts {shlex.quote(str(logs))} "*.log" "*.findings.md"\n'
    )
    swept = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           env=env, timeout=TIMEOUT)
    assert swept.returncode == 0, f"the sweep itself failed:\n{swept.stderr}"
    assert not decoy.exists(), (
        "test setup: the sweep must actually have run and reclaimed the decoy, or this "
        f"test proves nothing:\n{swept.stdout}\n{swept.stderr}"
    )
    assert evidence.exists(), (
        f"{evidence.name} is the only surviving record of a destroyed database - an "
        "evidence log that deletes itself defeats its own purpose. It must not be a "
        "candidate for the run-artifact sweep."
    )


# --------------------------------------------------------------------------- #
# 10 - the false-hypothesis case: a command that reclaimed AND THEN failed
# --------------------------------------------------------------------------- #
def test_an_acquire_that_fails_after_reclaiming_still_reports_it(harness, env_home):
    """The exact confusion the issue documents: a disappearance was blamed on a
    command that had in fact errored and done nothing. An acquire can reclaim
    (destroying another run's database) and THEN refuse for its own reasons - so
    a non-zero exit must not suppress the record."""
    alloc = _import_allocator()
    reasons = _reasons(alloc)
    env, home = env_home
    leader, _ = harness.spawn(argv_tail=["bystander-not-an-odoo-server"])
    fingerprint = alloc._pid_fingerprint(leader)
    if fingerprint is None:
        pytest.skip("no re-measurable pid fingerprint on this host - the live exclusive "
                    "holder cannot be staged")
    stale, _holder = _seed_many(harness, home, [
        (DEAD_PID, {"host": FOREIGN_HOST, "token": "9a" * 16,
                    "db_name": "odoo_17_0_t_55555555"}),
        (leader, {"token": "9b" * 16, "mode": "exclusive", "db_name": "odoo_17_0",
                  "owner": {"pid_started": fingerprint}}),
    ])

    proc = _acquire(env, "exclusive")
    assert proc.returncode == 3, (
        "test setup: the live exclusive holder must make this acquire conflict "
        f"(rc 3); got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    line = _notice_for(proc.stderr, stale["token"], "the failed acquire's stderr")
    assert any(reason in line for reason in reasons.values()), (
        f"a refusal must not suppress the record of what was already destroyed: {line!r}"
    )
