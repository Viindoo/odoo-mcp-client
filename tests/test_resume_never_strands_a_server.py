"""Guard: a REFUSED `resume` never leaves a live server the teardown gate cannot see.

THE INVARIANT (one sentence, and every test here is a direction of it): no path through
`50-instance-spinup.sh apply --exclusive --alloc-token <parked lease>` may end with an Odoo
server running while its lease still carries `parked_at`.

Why that exact shape is the dangerous one, and not merely untidy:

  - `resume <token> --pid <pid>` CORROBORATES the pid against the lease before it writes it, so
    it structurally cannot run before the server exists. The launch is therefore first, and the
    resume second - by construction, not by an ordering anyone chose.
  - A resume that REFUSES leaves the lease exactly as it found it: still parked. That is the
    compare-and-set doing its job.
  - `hooks/enforce-teardown.sh` filters the leases it blocks on with `select(has("parked_at") |
    not)` - a parked row is deliberately NOT a leak, because park already stopped its process
    group (asserted in `tests/test_enforce_teardown.py::
    test_a_parked_lease_never_blocks_the_subagent_that_parked_it`).

Put together, a spin-up that launched a server and then failed to resume would produce the one
combination the RAM-leak protection is blind to: a live, detached `odoo-bin` process group behind
a ledger row the gate skips. Nothing else in the system would ever name it - `gc`'s park arm
protects the row until `park_ttl_s` lapses, and `reap-orphans` excludes any database a lease
references. So `_bind_exclusive` STOPS the process group it was handed and FAILS the apply.

The pre-launch half of the same guarantee lives one rung earlier and is tested with the other
allocator behaviour: `query --state parked` SKIPS a lease whose database is provably gone, so the
caller never gets coordinates to launch against it at all (`tests/test_allocator_signal_ownership.py
::test_query_state_parked_never_offers_a_lease_whose_database_is_gone`).

Every assertion below is made after a REAL `50-instance-spinup.sh` run against the REAL allocator,
on the PROCESS TABLE and the REGISTRY FILE - never on prose - because the defect this file exists
to prevent was a live process that the script's own output described as a successful spin-up.

HARNESS SAFETY. The only pid this module ever signals or asserts on is the one the script itself
prints as `Odoo starting (pid: N ...)` - a process this test launched, seconds earlier, from a
stub interpreter inside its own tmp sandbox. No lease is ever seeded with a pid: the parked rows
here are written with `owner.pid = None`, which is exactly what `park` leaves behind.

Offline: no PostgreSQL, no real Odoo, no network. odoo-bin / python / curl / pg_isready / psql are
stubs (the Sandbox from `test_conf_lifecycle.py`, reused rather than re-implemented).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
ALLOCATOR = PLUGIN / "scripts" / "lib" / "allocator.py"

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_conf_lifecycle import Sandbox  # noqa: E402

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")

# The exclusive-running coordinates a real caller would have got back from `query --state parked`.
PARKED_DB = "odoo_test_parked"
PARKED_PORT = 18371
RUN_ID = "run-resume-guard"

_LAUNCH_PID_RE = re.compile(r"Odoo starting \(pid: (\d+)")


@pytest.fixture
def sandbox(tmp_path):
    sb = Sandbox(tmp_path)
    try:
        yield sb
    finally:
        sb.reap()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _declare_native_pg(sandbox: Sandbox) -> None:
    """Declare a `native` client surface so `_db_present` has a route it can take.

    Without it the probe answers None ("could not look") and the test would be measuring the
    undeterminable branch instead of the one it names.
    """
    sandbox.toml.write_text(
        sandbox.toml.read_text(encoding="utf-8") + 'db_run_mode = "native"\n', encoding="utf-8"
    )


def _psql_reports(sandbox: Sandbox, *, database_present: bool) -> None:
    """Stub `psql` so `_db_present` gets a DEFINITE answer, either way.

    `_db_present`'s client route reads one row from `pg_database`: a non-empty line means the
    database is there, an empty result means it provably is not.
    """
    body = 'echo "1"\n' if database_present else 'exit 0\n'
    path = sandbox.bindir / "psql"
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _long_lived_launcher(sandbox: Sandbox) -> None:
    """Make the stand-in server behave like a real one in the two ways these tests measure.

    1. It KEEPS the command line the launch gave it. The Sandbox's default stub `exec sleep`s,
       which REPLACES its argv - so the process the allocator inspects names no database and
       `_ownership_proof` can never corroborate it. A real odoo-bin keeps `-c <conf> -d <db>` on
       its command line, and the cmdline rung is the ONLY proof a resume can use (park cleared the
       `pid_started` fingerprint). Restoring that is what lets the SUCCESS direction be tested.
    2. It NEVER exits on its own. The default stub sleeps for a bounded 20s, which would let a
       "was the server stopped?" assertion pass on the stub's own mortality instead of on the
       teardown - measured, not assumed: with the stop removed and the bounded stub in place, the
       liveness assertion below still went green. A detached Odoo server does not time itself out,
       and neither may the stand-in that stands for it.
    """
    real_py3 = which("python3") or "/usr/bin/python3"
    sandbox.fake_py.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi\n'
        'if [[ "$2" == "preflight" ]]; then exit 0; fi\n'
        'case "$1" in\n'
        "    *odoo-bin*)\n"
        f'        echo "odoo-bin launched $*" >> "{sandbox.launch_log}"\n'
        '        if [[ "$*" == *--stop-after-init* ]]; then\n'
        '            echo "Modules loaded."\n'
        "            exit 0\n"
        "        fi\n"
        f'        : > "{sandbox.marker}"\n'
        "        while true; do sleep 1; done ;;\n"
        "esac\n"
        f'exec {real_py3} "$@"\n',
        encoding="utf-8",
    )
    sandbox.fake_py.chmod(0o755)


def _acquire_exclusive(sandbox: Sandbox) -> str:
    """A REAL exclusive lease on PARKED_DB, through the real allocator. Returns its token."""
    res = subprocess.run(
        [
            sys.executable, str(ALLOCATOR), "acquire",
            "--series", "17.0", "--mode", "exclusive",
            "--db-name", PARKED_DB, "--run-id", RUN_ID, "--no-create", "--ports", "0",
        ],
        capture_output=True, text=True, env=sandbox.env(), timeout=60,
    )
    assert res.returncode == 0, f"acquire failed:\n{res.stdout}\n{res.stderr}"
    token = next(
        (line.split("=", 1)[1].strip().strip("'")
         for line in res.stdout.splitlines() if line.startswith("ALLOC_TOKEN=")),
        "",
    )
    assert token, f"acquire must mint a token:\n{res.stdout}"
    return token


def _registry_path(sandbox: Sandbox) -> Path:
    return sandbox.home / "runtime" / "leases.json"


def _lease(sandbox: Sandbox, token: str) -> dict:
    rows = [
        row for row in json.loads(_registry_path(sandbox).read_text(encoding="utf-8"))["leases"]
        if row.get("token") == token
    ]
    assert rows, f"no lease row for {token!r}"
    return rows[0]


def _park_the_row(sandbox: Sandbox, token: str) -> None:
    """Stamp the park keys `cmd_park` writes, directly onto the registry row.

    `park` itself REFUSES a lease with no owner pid (there would be no process to stop), and this
    module deliberately never seeds a pid - so the row is written the way park leaves it: pid-less,
    `parked_at` fresh, budget generous.
    """
    path = _registry_path(sandbox)
    registry = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for row in registry["leases"] if row.get("token") == token]
    assert rows, f"no lease row for {token!r} to park"
    row = rows[0]
    assert not (row.get("owner") or {}).get("pid"), (
        "this lease unexpectedly records a pid; do not seed rows that name one"
    )
    row.setdefault("owner", {})["pid"] = None
    row["owner"]["pid_started"] = None
    row["parked_at"] = int(time.time())
    row["park_ttl_s"] = 86400
    path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _apply_exclusive(sandbox: Sandbox, token: str) -> subprocess.CompletedProcess:
    return sandbox.apply(
        "--exclusive", "--db-name", PARKED_DB,
        "--http-port", str(PARKED_PORT), "--port-key", "http_port",
        "--alloc-token", token,
    )


def _launched_pid(res: subprocess.CompletedProcess) -> int:
    match = _LAUNCH_PID_RE.search(res.stdout + res.stderr)
    assert match, (
        "test setup: the script must have reached the launch, or there is no server to reason "
        f"about.\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    return int(match.group(1))


def _still_alive(pid: int, *, within_s: float = 15.0) -> bool:
    """Whether `pid` is still a live process after a bounded wait.

    Bounded rather than instantaneous because the stop is SIGTERM -> grace -> group SIGKILL
    (SPINUP_STOP_GRACE), and because a just-exited child stays visible as a zombie until it is
    reaped. The stand-in server never exits on its own (see `_long_lived_launcher`), so a False
    here can only mean something stopped it.
    """
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return False
        time.sleep(0.1)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False
    return True


# ---------------------------------------------------------------------------
# The refusal direction - nothing may be left running
# ---------------------------------------------------------------------------


@requires_bash
def test_a_refused_resume_leaves_no_server_behind_a_still_parked_lease(sandbox):
    """The whole invariant, on the failure mode most likely to happen for real: the database was
    dropped from under a parked lease, so `resume` refuses (exit 5) after the launch.

    Three things must hold together, and any one of them alone would be satisfied by a broken
    implementation: the apply FAILS, the launched process group is STOPPED, and the lease is left
    untouched so the next caller can still release it cleanly."""
    _declare_native_pg(sandbox)
    _psql_reports(sandbox, database_present=False)
    _long_lived_launcher(sandbox)
    token = _acquire_exclusive(sandbox)
    _park_the_row(sandbox, token)

    res = _apply_exclusive(sandbox, token)
    pid = _launched_pid(res)

    assert res.returncode != 0, (
        "a spin-up whose resume was refused must FAIL - reporting success hands the caller a "
        f"handle to an instance nothing owns.\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    assert not _still_alive(pid), (
        f"the server launched at pid {pid} is STILL RUNNING behind a lease that still carries "
        "`parked_at` - the exact combination hooks/enforce-teardown.sh skips as 'not a leak'"
    )
    row = _lease(sandbox, token)
    assert row.get("parked_at") is not None, (
        "a refused resume must leave the lease PARKED - the database, filestore and ports it "
        "reserved are still wanted"
    )
    assert not (row.get("owner") or {}).get("pid"), (
        "no pid may be written onto a lease whose resume was refused"
    )


@requires_bash
def test_the_refusal_names_the_exit_code_and_what_to_do_about_it(sandbox):
    """A blocked caller has to be able to act. The refusal must say that nothing was left running
    (or the agent tears down an instance that is already gone) and name the remedy for the code it
    got - here exit 5, whose remedy is `release`, never a retry."""
    _declare_native_pg(sandbox)
    _psql_reports(sandbox, database_present=False)
    _long_lived_launcher(sandbox)
    token = _acquire_exclusive(sandbox)
    _park_the_row(sandbox, token)

    res = _apply_exclusive(sandbox, token)
    text = res.stdout + res.stderr

    assert "resume exit 5" in text, f"the refusal must name the allocator's exit code:\n{text}"
    assert "STOPPED" in text, (
        f"the refusal must state that the launched server was stopped:\n{text}"
    )
    assert "release" in text, (
        f"exit 5's remedy is `release`, and the refusal must name it:\n{text}"
    )


# ---------------------------------------------------------------------------
# The success direction - a legitimate resume must still work
# ---------------------------------------------------------------------------


@requires_bash
def test_a_legitimate_resume_still_brings_the_parked_instance_back(sandbox):
    """The other half, without which "make it fail closed" would pass: when the database IS there
    and the launched pid IS corroborated as this lease's own server, the apply succeeds and the
    lease transitions PARKED -> RUNNING - park keys deleted, pid recorded.

    A resumed lease that kept its park keys would be governed by `park_ttl_s` alone, so gc would
    drop the database under a live server and the teardown gate would exempt it forever."""
    _declare_native_pg(sandbox)
    _psql_reports(sandbox, database_present=True)
    _long_lived_launcher(sandbox)
    token = _acquire_exclusive(sandbox)
    _park_the_row(sandbox, token)

    res = _apply_exclusive(sandbox, token)
    pid = _launched_pid(res)

    assert res.returncode == 0, (
        f"a resumable parked lease must spin up.\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    row = _lease(sandbox, token)
    for key in ("parked_at", "park_ttl_s", "parked_boot_id"):
        assert key not in row, (
            f"resume must DELETE {key!r} - a survivor re-governs a LIVE lease by a park budget"
        )
    assert row["owner"]["pid"] == pid, (
        "the resumed lease must name the server that is actually running, so release/gc can stop "
        f"its process group; got {row['owner'].get('pid')!r}, launched {pid}"
    )
