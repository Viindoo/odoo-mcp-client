"""Behavior tests: `release` and acquire's capacity reclaim never hold the
machine-wide registry lock while a server is stopped or a database is dropped.

The contract, stated as behavior:
  - while a release's drop is in flight, another session's `list` and an acquire
    of ANOTHER series complete promptly; the row being released shows as
    `reclaiming`, keeps its ports reserved (a full-pool acquire is refused), and
    no concurrent gc / park / second release touches it;
  - a release that dies between phases leaves a row whose marker names a DEAD
    pid, so the next release or gc takes it over and finishes the teardown;
  - a failed drop keeps the row (DROP_FAILED_KEPT) WITHOUT leaving it stuck as
    `reclaiming`, and --force-forget still names what was abandoned;
  - acquire's capacity reclaim stops a slow (SIGTERM-ignoring) server of an
    ended session OUTSIDE the lock: a parallel list and acquire do not wait on it,
    and the freed port still goes to the acquire that reclaimed it.

Every database interaction goes through a stub interpreter whose `drop` waits
on a GATE file the test opens - no Postgres, no Odoo, no real drop.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_allocator import _import_allocator  # noqa: E402
from test_allocator_liveness_v3 import ALLOC, DROP_GATE_MAX_S, POOL, World, _kv  # noqa: E402

# No wall-clock bounds: "did not wait on the lock" is proven by the concurrent
# calls RETURNING while the slow operation is provably still blocked (the drop
# gate is closed / the SIGTERM-ignoring server is still alive). A call that did
# wait could only return after that operation ended.

SECOND_SERIES = """
[[instance]]
series = "16.0"
addons_path = ["/srv/odoo16/addons"]
run_mode = "source"
http_port = 8068
http_port_base = 8190
port_pool_size = 5
db_name = "odoo_16_0"
db_name_prefix = "odoo_16_0"
db_host = "localhost"
db_user = "odoo"
python = "{py}"
"""


class GatedWorld(World):
    """World whose stub `drop` blocks until the test opens a gate file, fails
    while a `drop-fails` file exists, and whose `exists` answers from a file."""

    def __init__(self, tmp_path):
        self.gate = tmp_path / "drop-gate"
        self.drop_fails = tmp_path / "drop-fails"
        self.exists_answer = tmp_path / "exists-answer"
        super().__init__(tmp_path)
        self.toml.write_text(self.toml.read_text(encoding="utf-8")
                             + SECOND_SERIES.format(py=self.py), encoding="utf-8")

    def _stub_python(self, drop_sleep_s):
        py = self.tmp / "fakebin" / "python"
        py.parent.mkdir()
        py.write_text(
            "#!/bin/sh\n"
            'if [ "$(basename "$1")" = "odoo_db.py" ]; then\n'
            f'  echo "$2 $3" >> "{self.calls}"\n'
            '  case "$2" in\n'
            "    can-createdb) echo true; exit 0 ;;\n"
            '    preflight) echo "DB_AUTH_WHY=stub"; exit 0 ;;\n'
            f'    drop) : > "{self.drop_started}"\n'
            "          i=0\n"
            f'          while [ ! -e "{self.gate}" ] && [ $i -lt {int(DROP_GATE_MAX_S * 20)} ]; do '
            "sleep 0.05; i=$((i+1)); done\n"
            f'          if [ -e "{self.drop_fails}" ]; then exit 1; fi\n'
            "          exit 0 ;;\n"
            f'    exists) if [ -e "{self.exists_answer}" ]; then cat "{self.exists_answer}"; '
            "else echo false; fi; exit 0 ;;\n"
            "  esac\n"
            "  exit 0\n"
            "fi\n"
            f'exec {sys.executable} "$@"\n', encoding="utf-8")
        py.chmod(0o755)
        return py

    def open_gate(self):
        self.gate.touch()

    def wait_drop_started(self, timeout=20):
        deadline = time.time() + timeout
        while not self.drop_started.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert self.drop_started.exists(), "test setup: the drop never started"

    def popen(self, env, *args):
        return subprocess.Popen([sys.executable, str(ALLOC), *args], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def close(self):
        self.open_gate()  # never leave a stub drop polling behind
        super().close()


@pytest.fixture
def gw(tmp_path):
    w = GatedWorld(tmp_path)
    try:
        yield w
    finally:
        w.close()


def _row(listed, token):
    doc = json.loads(listed.stdout)
    leases = doc["fields"]["leases"] if "fields" in doc else doc["leases"]
    return next((lz for lz in leases if lz["token"] == token), None)


def _wait_until(pred, timeout=20, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError(f"test setup: {what} never happened")


# --------------------------------------------------------------------------- #
# 1 - release does not stall the machine while it drops
# --------------------------------------------------------------------------- #
def test_a_release_in_flight_blocks_neither_list_nor_another_series_acquire(gw):
    a, b = gw.session("sess-A"), gw.session("sess-B")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    ports = gw.lease(token)["ports"]

    rel = gw.popen(gw.env(a), "release", token, "--run-id", "run-A")
    try:
        gw.wait_drop_started()

        listed = gw.run(gw.env(b), "list", "--with-verdict", "--show-tokens",
                        "--format", "json")
        other, got = gw.acquire(gw.env(b), "--no-create", "--series", "16.0",
                                run_id="run-B")
        assert not gw.gate.exists() and rel.poll() is None, (
            "list + acquire must complete while the release's drop is still blocked")
        assert listed.returncode == 0 and other.returncode == 0, (listed.stderr, other.stderr)
        assert got["ALLOC_DB_NAME"].startswith("odoo_16_0_t_")
        row = _row(listed, token)
        assert row["verdict"]["state"] == "reclaiming", row["verdict"]
    finally:
        gw.open_gate()
        _out, err = rel.communicate(timeout=60)
    assert rel.returncode == 0, err
    assert gw.lease(token) is None and len(gw.drops()) == 1
    assert ports and all(p in POOL for p in ports)


def test_a_row_being_released_keeps_its_ports_and_is_touched_by_nothing_else(gw):
    """While the release is in phase B: its port is not handed out, a gc does not
    reclaim (or re-drop) it even though its session has ended, the owner cannot
    park it, and a second release is refused - all promptly. Once the release
    settles, the whole pool is free again."""
    a, b = gw.session("sess-A"), gw.session("sess-B")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]

    rel = gw.popen(gw.env(a), "release", token, "--run-id", "run-A")
    try:
        gw.wait_drop_started()
        a.end()  # condemnable by gc from here on - only the marker protects it

        full = gw.run(gw.env(b), "acquire", "--series", "17.0", "--mode", "ephemeral",
                      "--no-create", "--ports", str(len(POOL)), "--run-id", "run-B",
                      "--format", "json")
        gc = gw.run(gw.env(b), "gc", "--format", "json")
        again = gw.run(gw.env(a), "release", token, "--run-id", "run-A", "--format", "json")
        assert not gw.gate.exists() and rel.poll() is None, (
            "the concurrent calls must complete while the release's drop is still blocked")

        assert full.returncode == 4, "a port of a row being released must stay reserved"
        assert json.loads(full.stdout)["error"]["code"] == "PORT_POOL_EXHAUSTED"
        assert gc.returncode == 0 and json.loads(gc.stdout)["fields"]["reclaimed"] == []
        assert again.returncode == 11
        assert json.loads(again.stdout)["error"]["code"] == "RECLAIM_IN_PROGRESS"
        assert "(release)" in again.stderr, again.stderr
        assert len(gw.drops()) == 1, "nothing may start a second drop of the same row"
    finally:
        gw.open_gate()
        _out, err = rel.communicate(timeout=60)
    assert rel.returncode == 0, err
    assert gw.lease(token) is None
    p = gw.run(gw.env(b), "acquire", "--series", "17.0", "--mode", "ephemeral",
               "--no-create", "--ports", str(len(POOL)), "--run-id", "run-B")
    assert p.returncode == 0, "the settled release must give its ports back:\n" + p.stderr


# --------------------------------------------------------------------------- #
# 2 - a release that dies between phases is taken over, not stuck
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("taker", ["release", "gc"])
def test_a_release_killed_mid_drop_is_finished_by_the_next_release_or_gc(gw, taker):
    a, b = gw.session("sess-A"), gw.session("sess-B")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    ports = gw.lease(token)["ports"]

    rel = gw.popen(gw.env(a), "release", token, "--run-id", "run-A")
    gw.wait_drop_started()
    rel.send_signal(signal.SIGKILL)
    rel.communicate(timeout=30)

    row = gw.lease(token)
    assert row is not None, "a release killed before phase C must not lose the row"
    mark = row["reclaiming"]
    assert mark["by_pid"] == rel.pid and mark["by_verb"] == "release"
    assert row["ports"] == ports, "the ports stay reserved until the row is settled"
    listed = gw.run(gw.env(b), "list", "--with-verdict", "--show-tokens", "--format", "json")
    assert _row(listed, token)["verdict"]["state"] != "reclaiming", (
        "a marker whose process is dead must not keep the row `reclaiming`")

    gw.open_gate()  # the retaking drop completes at once
    if taker == "release":
        p = gw.run(gw.env(a), "release", token, "--run-id", "run-A")
        assert p.returncode == 0, p.stderr
    else:
        a.end()
        p = gw.run(gw.env(b), "gc", "--format", "json")
        assert p.returncode == 0, p.stderr
        assert [r["token"] for r in json.loads(p.stdout)["fields"]["reclaimed"]] == [token]
    assert gw.lease(token) is None
    assert len(gw.drops()) == 2, "the take-over re-runs the (idempotent) drop"


# --------------------------------------------------------------------------- #
# 3 - every release outcome survives the split
# --------------------------------------------------------------------------- #
def test_a_failed_drop_keeps_the_row_unmarked_and_force_forget_names_it(gw):
    a = gw.session("sess-A")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    gw.open_gate()
    gw.drop_fails.touch()
    gw.exists_answer.write_text("true\n", encoding="utf-8")

    p = gw.run(gw.env(a), "release", token, "--run-id", "run-A", "--format", "json")
    assert p.returncode == 1 and json.loads(p.stdout)["error"]["code"] == "DROP_FAILED_KEPT"
    row = gw.lease(token)
    assert row is not None and "reclaiming" not in row, (
        "a kept row must be handed back, not left marked")
    assert row["ports"], "a kept row keeps its ports"

    p = gw.run(gw.env(a), "release", token, "--run-id", "run-A", "--force-forget")
    assert p.returncode == 0, p.stderr
    assert _kv(p.stdout).get("ALLOC_ABANDONED_DB") == row["db_name"]
    assert gw.lease(token) is None


def test_a_provably_absent_database_releases_cleanly(gw):
    a = gw.session("sess-A")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    token = out["ALLOC_TOKEN"]
    db = gw.lease(token)["db_name"]
    gw.open_gate()
    gw.drop_fails.touch()  # exists answers false by default

    p = gw.run(gw.env(a), "release", token, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr
    assert _kv(p.stdout).get("ALLOC_FORGOTTEN_DB") == db
    assert gw.lease(token) is None


def test_a_refused_release_marks_nothing(gw):
    """NOT_OWNER is decided in phase A: the row is untouched, never `reclaiming`,
    and no stop or drop was attempted; an unknown token still exits 0."""
    a = gw.session("sess-A")
    p, out = gw.acquire(gw.env(a), "--ports", "1")
    token = out["ALLOC_TOKEN"]
    before = gw.lease(token)

    p = gw.run(gw.env(a), "release", token, "--run-id", "run-X", "--format", "json")
    assert p.returncode == 1 and json.loads(p.stdout)["error"]["code"] == "NOT_OWNER"
    assert gw.lease(token) == before and gw.drops() == []

    p = gw.run(gw.env(a), "release", "0" * 32, "--run-id", "run-A")
    assert p.returncode == 0, p.stderr


# --------------------------------------------------------------------------- #
# 4 - acquire's capacity reclaim stops a slow server outside the lock
# --------------------------------------------------------------------------- #
def test_a_capacity_reclaim_of_a_slow_server_blocks_neither_list_nor_acquire(gw):
    """The pool is held by an ended session's lease whose (proven) server ignores
    SIGTERM, so stopping it takes the full bounded wait before the SIGKILL. The
    acquire that reclaims it must not hold the registry lock meanwhile - and it,
    not a racer, still gets the freed port."""
    alloc = _import_allocator()
    server = subprocess.Popen(
        [sys.executable, "-c",
         "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
         "time.sleep(600)"],
        start_new_session=True)
    try:
        a, b, c = gw.session("sess-A"), gw.session("sess-B"), gw.session("sess-C")
        p, out = gw.acquire(gw.env(a), "--no-create", "--ports", str(len(POOL)),
                            "--pid", str(server.pid))
        assert p.returncode == 0, p.stderr
        token = out["ALLOC_TOKEN"]
        a.end()
        gw.age(token, alloc.ANCHOR_GRACE_S + 60)

        acq = gw.popen(gw.env(b), "acquire", "--series", "17.0", "--mode", "ephemeral",
                       "--no-create", "--ports", "1", "--run-id", "run-B")
        _wait_until(lambda: (gw.lease(token) or {}).get("reclaiming"),
                    what="the capacity reclaim marking the victim")

        listed = gw.run(gw.env(c), "list", "--with-verdict", "--show-tokens",
                        "--format", "json")
        other, _got = gw.acquire(gw.env(c), "--no-create", "--series", "16.0",
                                 run_id="run-C")
        racer = gw.run(gw.env(c), "acquire", "--series", "17.0", "--mode", "ephemeral",
                       "--no-create", "--ports", "1", "--run-id", "run-C")
        # The server ignores SIGTERM, so it is alive until the bounded stop's
        # SIGKILL: a call that had waited on the stop could only return after it.
        assert server.poll() is None and acq.poll() is None, (
            "the concurrent calls must complete while the slow server is still stopping")
        assert listed.returncode == 0 and other.returncode == 0, (listed.stderr, other.stderr)
        assert _row(listed, token)["verdict"]["state"] == "reclaiming"
        assert racer.returncode == 4, (
            "the ports of a row whose server is still stopping must not be handed out")

        stdout, err = acq.communicate(timeout=60)
        assert acq.returncode == 0, err
        assert int(_kv(stdout)["ALLOC_PORTS"]) in POOL
        server.wait(timeout=10)  # SIGKILLed by the bounded stop
        victim = gw.lease(token)
        assert victim is not None and "reclaiming" not in victim
        assert victim["ports"] == [] and victim["orphaned"]["reason"] == "owner-session-ended"
        assert victim["orphaned"]["by_verb"] == "acquire-capacity"
        assert gw.drops() == [], "the capacity path must never drop a database"
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGKILL)
            server.wait(timeout=10)
