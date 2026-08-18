"""The allocator's stderr must SURVIVE its two highest-traffic callers.

`allocator.py` reports a reclamation on two channels - a `RECLAIMED lease ...`
line on stderr, and the same record appended to `logs/allocator-reclaimed.jsonl`.
Only the RECLAIMED notice is on both. Three classes of message reach stderr
ONLY, and each is the sole surviving account of something the command left
behind:

  - `REFUSING to signal pid N ...` - ownership was not proven, so NOTHING was
    signalled: a server process was knowingly LEAKED while its lease row was
    reclaimed anyway. No JSONL line records that.
  - `ERROR - ... drop of <db> FAILED; DB retained, lease kept for retry` - the
    database survived. `_gc` deliberately does not report such a lease as
    reclaimed, so there is no JSONL line for it AT ALL.
  - `WARNING - could not append the reclaim record ... the stderr line above is
    now the ONLY record of that reclamation` - the JSONL write itself failed.

Both of the plugin's implicit reclaimers used to send that stream to
`/dev/null`:

  - `hooks/session-end-gc.sh` - runs `gc` at the end of EVERY session, from a
    DETACHED worker whose own stdout/stderr are already `/dev/null`, so it is
    both the largest single reclaimer and the one with no terminal to speak to.
  - `scripts/setup-steps/50-instance-spinup.sh::_register_shared` - its
    `acquire` runs the same destructive `_gc` sweep over the whole shared
    registry as a side effect of registering a shared lease.

So the rule this module protects is: a reclaiming allocator call may never be
the reason its own account disappeared - AND making it speak may never become a
reason the reclamation itself fails to happen. Both halves are asserted
behaviorally, by running the REAL callers against the REAL allocator with a
registry seeded so a lease is reclaimed.

HARNESS SAFETY. `_gc` signals process GROUPS. Every lease seeded here goes
through `test_allocator_signal_ownership.Harness.seed_lease`, which REFUSES any
pid this suite did not spawn, and every seeded row uses the proven-dead pid on a
FOREIGN host (`_stop_owner_group_if_local` returns before it looks at a foreign
row) with `drop_on_release` False (the only arm that reaches a database drop).
Nothing here spawns, signals or drops anything.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
GC_HOOK = PLUGIN / "hooks" / "session-end-gc.sh"
STEP50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
LIB = PLUGIN / "scripts" / "lib"

# The interlocked harness - reused, never re-implemented (see this module's
# docstring), along with the two sentinels its pid interlock permits.
from test_allocator_signal_ownership import (  # noqa: E402
    DEAD_PID,
    FOREIGN_HOST,
    Harness,
)

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)

STALE_TOKEN = "cc" * 16
STALE_DB = "odoo_17_t_stalelease"
SPINUP_DB = "odoo_17_t_spinup"


# --------------------------------------------------------------------------- #
# The log's identity is read from the code under test, never re-spelled here
# --------------------------------------------------------------------------- #
def _diag_basename():
    """The durable log's basename, read from the hook's declared constant.

    Re-spelling it in the test would let the test and the code drift in lockstep
    and still pass; reading it means a rename has to be a deliberate, visible
    change to the SSOT the other caller is checked against below.
    """
    text = GC_HOOK.read_text(encoding="utf-8")
    match = re.search(r'^ALLOC_DIAG_BASENAME="([^"]+)"$', text, re.M)
    assert match, (
        "hooks/session-end-gc.sh must declare the durable stderr log's basename as "
        "ALLOC_DIAG_BASENAME=\"...\" - it is the name the other reclaiming caller "
        "(50-instance-spinup.sh) is held to, and the one an operator greps for"
    )
    return match.group(1)


def _diag_log(home: Path) -> Path:
    return Path(home) / "logs" / _diag_basename()


# --------------------------------------------------------------------------- #
# Sandbox builders
# --------------------------------------------------------------------------- #
def _fake_plugin_root(tmp_path: Path) -> Path:
    """A plugin root carrying the REAL allocator and the REAL shell libs.

    Copied rather than symlinked: `allocator.py` resolves its sibling helpers
    from `os.path.abspath(__file__)`, which does not follow a symlink, so a
    symlinked tree would quietly exercise a different resolution than production.
    """
    root = tmp_path / "plugin"
    libdir = root / "scripts" / "lib"
    libdir.mkdir(parents=True)
    for name in ("allocator.py", "state_reclaim.sh", "resolve_instances.sh",
                 "instances_io.py", "odoo_db.py", "pg_mode.sh"):
        src = LIB / name
        if src.is_file():
            shutil.copy2(src, libdir / name)
    return root


def _empty_catalog(tmp_path: Path) -> Path:
    """A catalog file that RESOLVES but declares no instance: gc needs none (the
    seeded rows never reach a drop), and `reap-orphans` stops at "nothing to
    reap" instead of reaching for a real cluster from a unit test."""
    toml = tmp_path / "instances.toml"
    toml.write_text("# no [[instance]] declared\n", encoding="utf-8")
    return toml


def _seed_stale_lease(harness: Harness, home: Path, *, token=STALE_TOKEN, db=STALE_DB):
    """One lease that `_condemn_reason` must condemn, seeded through the pid
    interlock. Foreign host + proven-dead pid + an elapsed TTL is the
    `ttl-expired-liveness-unprovable` arm - the one arm that needs no live
    process at all, so nothing can be signalled by staging it."""
    home.mkdir(parents=True, exist_ok=True)
    return harness.seed_lease(
        home, DEAD_PID, host=FOREIGN_HOST, token=token, db_name=db,
        drop_on_release=False, mode="shared",
    )


def _read_log(path: Path, needle: str, timeout_s: float = 30.0) -> str:
    """Poll for `needle` in `path`. The hook's worker is DETACHED, so every
    assertion about what it wrote must wait for the worker, not for the hook."""
    deadline = time.monotonic() + timeout_s
    text = ""
    while time.monotonic() < deadline:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                return text
        time.sleep(0.05)
    return text


def _leases(home: Path):
    path = Path(home) / "runtime" / "leases.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["leases"]


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    try:
        yield h
    finally:
        h.reap()


# --------------------------------------------------------------------------- #
# 1 - the SessionEnd hook: the largest reclaimer, and the one with no terminal
# --------------------------------------------------------------------------- #
@requires_bash
def test_the_session_end_gc_persists_the_account_of_what_it_destroyed(harness, tmp_path):
    """END TO END. Seed a condemned lease, run the REAL hook against the REAL
    allocator, and require the reclamation to be discoverable afterwards.

    Before this, the account went to `/dev/null` on the one path that runs at the
    end of EVERY session - so the half of the reporting meant for a human was
    lost on exactly the path that destroys the most.
    """
    root = _fake_plugin_root(tmp_path)
    home = tmp_path / "home"
    _seed_stale_lease(harness, home)

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(root)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)  # isolate the ~/.odoo-ai fallback
    env["ODOO_AI_INSTANCES"] = str(_empty_catalog(tmp_path))
    proc = subprocess.run(["bash", str(GC_HOOK)], input="{}", capture_output=True,
                          text=True, timeout=30, env=env)

    assert proc.returncode == 0, f"the hook must still exit 0; stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "", "SessionEnd gc must stay silent on its own stdout"

    log = _diag_log(home)
    text = _read_log(log, STALE_TOKEN)
    assert log.is_file(), (
        f"the reclaiming gc's stderr must be PERSISTED under {log} - a SessionEnd "
        "worker is detached with no terminal, so /dev/null there means the notice "
        "reaches nobody, ever"
    )
    assert f"RECLAIMED lease token={STALE_TOKEN}" in text, (
        f"the persisted stream must carry the per-lease RECLAIMED notice; got {text!r}"
    )
    assert f"db_name={STALE_DB}" in text and "reason=ttl-expired" in text, (
        "the notice must still name the database and the condemning arm - the "
        f"reason is the one fact no later reader can re-derive; got {text!r}"
    )
    assert _leases(home) == [], "the lease itself must still have been reclaimed"

    # The JSONL evidence log is NOT what this test proves, but the two must agree:
    # a stderr record that contradicts the durable record would be worse than none.
    jsonl = home / "logs" / "allocator-reclaimed.jsonl"
    if jsonl.is_file():
        assert STALE_TOKEN in jsonl.read_text(encoding="utf-8")


@requires_bash
def test_the_session_end_gc_still_runs_when_its_log_cannot_be_written(tmp_path):
    """The non-fatal half. A redirect bash cannot open makes it SKIP the command
    outright, so a naive redirect turns "no log line" into "no gc" - the backstop
    silently stops reclaiming. An unwritable log directory must degrade to
    today's behavior (no record) and never to a missed sweep.
    """
    root = _fake_plugin_root(tmp_path)
    libdir = root / "scripts" / "lib"
    marker = libdir / "gc-called.txt"
    (libdir / "allocator.py").write_text(
        "import sys, pathlib\n"
        "pathlib.Path(pathlib.Path(__file__).parent / 'gc-called.txt')"
        ".write_text(' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    (home / "logs").mkdir(parents=True)
    os.chmod(home / "logs", 0o500)  # exists, but nothing can be created in it
    try:
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
        env["ODOO_AI_HOME"] = str(home)
        env["HOME"] = str(home)
        proc = subprocess.run(["bash", str(GC_HOOK)], input="{}", capture_output=True,
                              text=True, timeout=30, env=env)
        assert proc.returncode == 0, f"stderr={proc.stderr!r}"
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and not marker.is_file():
            time.sleep(0.05)
        assert marker.is_file(), (
            "gc must STILL be invoked when the durable log cannot be created - "
            "`mkdir -p` succeeds on an existing-but-unwritable dir, so without a "
            "writability probe bash would refuse the redirect and skip the sweep"
        )
        assert marker.read_text(encoding="utf-8").strip() == "gc"
        assert proc.stdout.strip() == "" and proc.stderr.strip() == "", (
            "and the failure to log must itself stay silent on the hook's own "
            f"channels; got stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    finally:
        os.chmod(home / "logs", 0o700)


# --------------------------------------------------------------------------- #
# 2 - the shared-lease registration: an acquire that reclaims as a side effect
# --------------------------------------------------------------------------- #
def _spinup_sandbox(tmp_path: Path):
    """(env, home, launch_log): the minimal stubbed world 50-instance-spinup.sh
    needs to reach `_register_shared` - a fake odoo-bin, a fake python that
    answers `--version` and then sleeps, a curl that reports 000 once and 200
    after, and a pg_isready that succeeds. No network, no Postgres, no Odoo."""
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "fake-core" / "odoo-bin"
    _stub(fake_bin, 'echo "Odoo Server 17.0"\n')

    launch_log = tmp_path / "odoo-launch.log"
    py_bin_dir = tmp_path / "fake-py-bin"
    py_bin_dir.mkdir(exist_ok=True)
    fake_py = py_bin_dir / "python"
    _stub(fake_py, (
        'if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi\n'
        f'echo "launched $*" >> "{launch_log}"\n'
        'exec sleep 15\n'
    ))

    toml = tmp_path / "instances.toml"
    toml.write_text(
        "[[instance]]\n"
        'series = "17.0"\n'
        f'python = "{fake_py}"\n'
        "http_port = 18171\n"
        f'db_name = "{SPINUP_DB}"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        'run_mode = "source"\n'
        f'addons_path = "{fake_addons}"\n',
        encoding="utf-8",
    )

    bind = tmp_path / "bin50"
    bind.mkdir(exist_ok=True)
    counter = tmp_path / "curl.count"
    _stub(bind / "curl", (
        f'n="$(cat "{counter}" 2>/dev/null || echo 0)"\n'
        f'echo $((n + 1)) > "{counter}"\n'
        'if [[ "$n" -ge 1 ]]; then echo "200"; else echo "000"; fi\n'
    ))
    _stub(bind / "pg_isready", "exit 0\n")

    home = tmp_path / "home"
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)
    env["SPINUP_TIMEOUT"] = "10"
    env["ODOO_BIN"] = str(fake_bin)
    env.pop("ODOO_PG_PASSWORD", None)
    return env, home, launch_log


def _stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _kill_spinup_server(home: Path):
    """Reap the stub `sleep` the spin-up backgrounded - and NOTHING else.

    Scoped to the lease this spin-up just wrote for its OWN sandbox database:
    the pid there is the `$!` of the process the test itself launched, seconds
    ago, in a sandboxed registry no other run can reach. The seeded stale row is
    deliberately excluded (it names the proven-dead sentinel pid, and a harness
    that signals pids it did not spawn is how a test kills its own shell).
    """
    for lease in _leases(home):
        if lease.get("db_name") != SPINUP_DB:
            continue
        pid = lease.get("owner", {}).get("pid")
        if pid and int(pid) not in (DEAD_PID, 0, 1):
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass


@requires_bash
def test_the_shared_lease_registration_persists_the_account_of_what_it_destroyed(
        harness, tmp_path):
    """END TO END on the other caller. `_register_shared` runs a real `acquire`,
    which runs the same destructive `_gc` sweep over the WHOLE shared registry -
    so a spin-up routinely reclaims some other run's lease. That account went to
    `/dev/null` too.

    Also asserts the two properties that must NOT change: the notice stays OFF
    this script's own stdout/stderr (its stdout is a KEY=VALUE protocol, and a
    warning printed one line before `ok Odoo ... is up` reads as a spin-up
    failure to the agent parsing it), and the registration still happens.
    """
    env, home, _launch = _spinup_sandbox(tmp_path)
    _seed_stale_lease(harness, home)

    proc = subprocess.run(["bash", str(STEP50), "apply", "--version", "17.0"],
                          capture_output=True, text=True, env=env, timeout=60)
    try:
        assert proc.returncode == 0, (
            f"test setup: the stubbed spin-up must succeed.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        leases = _leases(home)
        shared = [lz for lz in leases if lz.get("db_name") == SPINUP_DB]
        assert len(shared) == 1, (
            f"the shared lease must still be registered - persisting the stderr may "
            f"never cost the registration itself.\nLeases: {leases}"
        )
        assert not [lz for lz in leases if lz.get("token") == STALE_TOKEN], (
            "test setup: the acquire's gc must actually have reclaimed the seeded "
            f"stale lease, or this test proves nothing.\nLeases: {leases}"
        )

        log = _diag_log(home)
        assert log.is_file(), (
            f"the reclaiming acquire's stderr must be PERSISTED under {log}"
        )
        text = log.read_text(encoding="utf-8", errors="replace")
        assert f"RECLAIMED lease token={STALE_TOKEN}" in text, (
            f"a spin-up that destroys another run's lease must leave an account of "
            f"it; got {text!r}"
        )
        assert "by_verb=acquire" in text, (
            "and the account must name the verb that took it - the implicit acquire "
            f"pass is the one an operator does not expect; got {text!r}"
        )
        assert STALE_TOKEN not in proc.stdout, (
            "acquire's stdout is a shell PROTOCOL for `eval $(allocator.py acquire "
            "...)`; this script's stdout is a KEY=VALUE protocol too. The notice "
            "must never be interleaved into either"
        )
        assert STALE_TOKEN not in proc.stderr, (
            "nor into this script's own stderr: a best-effort registration's "
            "diagnostics printed one line before `ok Odoo ... is up` read as a "
            "spin-up failure to the agent parsing this output"
        )
    finally:
        _kill_spinup_server(home)


@requires_bash
def test_the_shared_lease_is_still_registered_when_the_log_cannot_be_written(tmp_path):
    """The non-fatal half, on the spin-up side: an unwritable log directory must
    cost the RECORD, never the lease. A redirect bash cannot open skips the
    command, which here would mean the shared render target is never registered
    and no other session can discover it."""
    env, home, _launch = _spinup_sandbox(tmp_path)
    (home / "logs").mkdir(parents=True)
    os.chmod(home / "logs", 0o500)
    try:
        proc = subprocess.run(["bash", str(STEP50), "apply", "--version", "17.0"],
                              capture_output=True, text=True, env=env, timeout=60)
        assert proc.returncode == 0, (
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        shared = [lz for lz in _leases(home) if lz.get("db_name") == SPINUP_DB]
        assert len(shared) == 1, (
            "the shared lease must be registered even when its diagnostics cannot "
            f"be persisted; leases were {_leases(home)}"
        )
    finally:
        _kill_spinup_server(home)
        os.chmod(home / "logs", 0o700)


# --------------------------------------------------------------------------- #
# 3 - the shape guard: no reclaiming call may discard its stderr again
# --------------------------------------------------------------------------- #
# Verbs that provably CANNOT destroy anything: they neither run `_gc` (only
# `acquire` and `gc` do) nor stop a group nor drop a database, so discarding
# their stderr loses no account of a destruction. Everything else - including an
# invocation whose verb is built at runtime (`"${args[@]}"`) - is treated as
# destructive, i.e. this guard fails CLOSED on anything it cannot read.
_NON_DESTRUCTIVE_VERBS = ("bind", "heartbeat", "list", "query", "assert-droppable")


def _statements(path: Path):
    """The file as STATEMENTS: backslash-continuations joined, whitespace runs
    collapsed. A guard that matched raw lines would be defeated by a reflow, and
    would miss the multi-line `reap-orphans` call entirely."""
    text = re.sub(r"\\\n\s*", " ", path.read_text(encoding="utf-8"))
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]


def _is_allocator_call(stmt: str) -> bool:
    return bool(re.search(r"\bpython3\b", stmt)
                and re.search(r'\$\{?(?:alloc|alloc_py|ALLOC)\b', stmt)
                and not stmt.lstrip().startswith("#"))


def _is_destructive_call(stmt: str) -> bool:
    if not _is_allocator_call(stmt):
        return False
    return not any(re.search(rf"\s{verb}(\s|$)", stmt) for verb in _NON_DESTRUCTIVE_VERBS)


def _stderr_is_discarded(stmt: str) -> bool:
    """True when this statement throws the command's stderr away.

    Deliberately conservative: an ABSENT `2>` counts as discarded, because both
    call sites run somewhere stderr does not reach a human (a detached worker
    whose stderr is already /dev/null; a script whose stderr an agent reads as
    the spin-up's own verdict).
    """
    if re.search(r"2>\s*/dev/null", stmt):
        return True
    if "2>&1" in stmt:
        # stderr follows stdout: discarded exactly when stdout is /dev/null.
        return bool(re.search(r"(?<![0-9&])>\s*/dev/null", stmt))
    return not re.search(r"2>", stmt)


_MUST_CATCH = (
    'python3 "$alloc" gc >/dev/null 2>&1 || true',
    'python3 "$alloc" gc >/dev/null 2>/dev/null || true',
    'python3 "$alloc" gc >/dev/null || true',
    'timeout 300 python3 "$alloc" gc >"$run_log" 2>/dev/null || true',
    'python3 "$alloc_py" "${args[@]}" >/dev/null 2>&1 || true',
)

_MUST_NOT_CATCH = (
    'python3 "$alloc" gc >/dev/null 2>>"$diag" || true',
    'python3 "$alloc_py" "${args[@]}" >/dev/null 2>>"$_diag" || true',
    'timeout 120 python3 "$alloc" reap-orphans >"$runtime_dir/x.log" 2>&1 || true',
    'python3 "$alloc" gc 2>"$diag" >/dev/null || true',
)


@pytest.mark.parametrize("stmt", _MUST_CATCH)
def test_the_discard_detector_catches_every_shape_of_the_defect(stmt):
    assert _stderr_is_discarded(stmt), (
        f"this statement throws the allocator's stderr away and the guard missed "
        f"it: {stmt!r}"
    )


@pytest.mark.parametrize("stmt", _MUST_NOT_CATCH)
def test_the_discard_detector_leaves_compliant_calls_alone(stmt):
    assert not _stderr_is_discarded(stmt), (
        f"this statement PERSISTS the allocator's stderr and the guard flagged it "
        f"anyway - a guard that cannot be satisfied gets deleted: {stmt!r}"
    )


@pytest.mark.parametrize("path", [GC_HOOK, STEP50], ids=lambda p: p.name)
def test_no_reclaiming_allocator_call_discards_its_stderr(path):
    """Every allocator invocation that can DESTROY must keep its stderr. The two
    files here are the plugin's implicit reclaimers; a third caller added later
    inherits the same rule by being in this list."""
    offenders = [stmt for stmt in _statements(path)
                 if _is_destructive_call(stmt) and _stderr_is_discarded(stmt)]
    assert not offenders, (
        f"{path.name} discards the stderr of a reclaiming allocator call, which is "
        "the ONLY record of a refused signal (a leaked process), a failed drop (a "
        "retained database) and a failed evidence-log write. Offending "
        f"statement(s): {offenders}"
    )


def test_both_reclaiming_call_sites_write_the_SAME_log(tmp_path):
    """SSOT. The two call sites resolve the durable log independently (the hook
    cannot source the setup step, and vice versa), so the one thing that can
    silently drift is the PATH - and two half-logs are worse than one, because an
    operator who finds one stops looking. Until this resolution can live in
    `scripts/lib/state_reclaim.sh` (which owns `odoo_ai_state_root` and the
    `logs/` family), this test is what keeps them identical."""
    basename = _diag_basename()
    # Either spelling of the same name: the hook declares it as a constant, the
    # setup step (which may not grow a top-level constant of its own) writes the
    # literal. What must not differ is the DIRECTORY and the NAME.
    ref = re.compile(r"logs/(?:\$\{?ALLOC_DIAG_BASENAME\}?|" + re.escape(basename) + r")")
    for path in (GC_HOOK, STEP50):
        text = path.read_text(encoding="utf-8")
        assert ref.search(text), (
            f"{path.name} must resolve the durable stderr log as "
            f"<state root>/logs/{basename}; it is the SAME machine-global file the "
            "other reclaiming caller appends to (both end-to-end tests above read "
            "that one path, which is where this is proven behaviorally)"
        )
        assert "odoo_ai_state_root" in text, (
            f"{path.name} must resolve the root through `odoo_ai_state_root` "
            "(scripts/lib/state_reclaim.sh) - the ONE spelling of the Tier-1 state "
            "root - rather than re-deriving it from $HOME or a runtime dir"
        )

    producers = sorted(
        p.name for p in PLUGIN.rglob("*.sh") if basename in p.read_text(
            encoding="utf-8", errors="replace")
    )
    assert producers == sorted([GC_HOOK.name, STEP50.name]), (
        f"exactly the two reclaiming call sites may name {basename}; found "
        f"{producers}. A third writer means the file has stopped being one account"
    )
