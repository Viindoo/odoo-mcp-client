"""allocator.py - concurrent Odoo instance allocator (user/global, cross-session).

Hands a caller an ISOLATED or shared Odoo resource lease so concurrent subagents
(across concurrent Claude Code sessions) never collide on a database or port.
This is the *runtime* layer; the static *catalog* stays in instances.toml
(read via instances_io.py). Full design: docs/reference/INSTANCE-ALLOCATION.md.

Deliberately DETERMINISTIC and VERSION-AGNOSTIC: it only does Postgres +
filesystem + a file lock. It NEVER builds an odoo-bin command - the consumer
maps the returned port numbers to the right CLI flags by querying cli_help for
the target series at runtime, so future Odoo CLI changes never touch this script.
Because it is a plain script run via Bash, ANY agent at ANY depth can call it
(no subagent spawn, no Skill tool).

Runtime state lives under  ${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime/ :
    leases.json      - the single registry (atomic read-modify-write under flock)
    registry.lock    - the fcntl.flock file guarding the critical section

Modes:
    readonly   - attach a running instance; NO lease (shared, lease-free)
    ephemeral  - unique throwaway DB (<prefix>_t_<uuid8>); reserves a unique DB name
                 + ports - the DB is created through Odoo by the caller's `-i` run
                 (create-on-init) and dropped through Odoo on release (raw dropdb only
                 as a venv-unavailable fallback). Ports only when --ports N>0.
                 Default for tests / -i verification.
                 Auto-degrades to `exclusive` when the role lacks CREATEDB.
    exclusive  - the declared (or named) DB held under an exclusive lease.
    shared     - a long-lived, NON-exclusive lease for the visual stack's live
                 render server: many readers attach to ONE lease (never blocked),
                 created_db is ALWAYS False (gc reclaims a dead-server row but
                 NEVER drops the declared DB), and the actual bound --port + the
                 long-lived server --pid are recorded so `query` can find it and
                 `gc` can reclaim it. The port is recorded verbatim (not pooled).

CLI:
    allocator.py acquire --series <X.Y> --mode <readonly|ephemeral|exclusive|shared>
                 [--ports N] [--port P] [--ttl <s>] [--run-id <id>] [--db-name <name>]
                 [--pid <pid>] [--no-create] [--instances <path>]
                 [--addons-path-override <csv-or-colon-paths>]
                 # --run-id is the canonical ownership key; --session is a back-compat
                 # alias. acquire echoes ALLOC_RUN_ID + ALLOC_DB_PORT.
                 # With NO --addons-path-override, acquire refuses (non-zero) instead
                 # of silently defaulting ALLOC_ADDONS_PATH when the caller's cwd is a
                 # git worktree of the SAME repo as a catalog addons_path entry but at
                 # a DIFFERENT checkout - the false-green shape where a fix living in a
                 # worktree gets silently verified against the principal checkout's
                 # (pre-fix) code instead. Pass --addons-path-override to state the
                 # tree explicitly (see _addons_path_worktree_mismatch).
    allocator.py query --series <X.Y>     # the live shared render server for a series, if any
    allocator.py release <token> [--run-id <id>] [--force] [--instances <path>]
                 # refuses only when the caller's run differs from a non-empty
                 # owner run (token-possession otherwise); --force overrides loudly.
    allocator.py assert-droppable --db-name <db> [--run-id <id>] [--force]
                 # read-only: non-zero if a FRESH lease on <db> is owned by a
                 # DIFFERENT run, OR is UNOWNED (no run_id recorded at all -
                 # P5.8: unowned is no longer a synonym for "safe to drop");
                 # 0 otherwise (own lease, stale lease, no lease, or --force).
    allocator.py bind <token> --pid <server_pid>
                 # upsert the live server pid onto an EXISTING lease (the
                 # exclusive-running path: acquire reserves the lease, the
                 # spin-up binds the launched pid) so release/gc can stop the
                 # whole process GROUP before dropping the DB.
    allocator.py heartbeat <token>
    allocator.py gc [--instances <path>]
    allocator.py reap-orphans [--min-age-s <s>] [--yes] [--instances <path>]
                 # lists (default) or drops (--yes) ephemeral-shaped databases
                 # (<prefix>_t_<hex8>, never a named/declared instance) that carry
                 # NO lease reference at all - live or stale - across every
                 # declared cluster. Ownership predicate (see _reap_candidates):
                 # naming shape + zero lease reference + a POSITIVELY PROVEN age
                 # >= --min-age-s (default 24h; an unmeasurable age is treated as
                 # NOT old enough, fail-closed). A DB referenced by any lease -
                 # even stale - is release/gc's job, never this one's. Emits
                 # REAP_CANDIDATE / REAP_SKIPPED / REAP_DROPPED lines.
    allocator.py list [--show-tokens]     # tokens are fingerprinted unless --show-tokens

All commands emit shell-eval-able KEY=VALUE lines (shlex.quote'd), mirroring
instances_io.py's INST_* convention. acquire prints ALLOC_*.
"""

import contextlib
import fcntl
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances_io  # noqa: E402  (sibling lib; resolves via the path insert above)

DEFAULT_POOL_SIZE = 10
# TTL now governs ONLY the "liveness unprovable" residual - a lease on a
# DIFFERENT host, one that never recorded an owner pid, or one whose recorded
# pid fingerprint could not be re-verified (see `_is_stale`). A same-host lease
# with a VERIFIED-alive owner pid is protected forever regardless of this
# value; it no longer needs `heartbeat` to survive at all. Reconsidered down
# from the pre-fix 7200s (2h) to 3600s (1h): that longer number was calibrated
# for a risk this constant no longer carries (killing a live, verified,
# same-host process - that path is now immune to TTL by construction), so
# holding it at the old value would only widen the orphan-leak window for
# exactly the leases this constant still governs - the very ones we CANNOT
# verify at all. 1h stays generous relative to every documented heartbeat
# cadence (agents heartbeat between phases/scenarios, not between seconds), so
# a caller that follows that convention is never caught out; it is not pushed
# lower still because the "do not reap when unsure" bias (see `_is_stale`)
# argues against being aggressive on the one bucket that is already the
# hardest to get right.
DEFAULT_TTL_S = 3600
# reap-orphans default minimum PROVABLE age (seconds) before a lease-free
# ephemeral-shaped DB is even proposed as a candidate. Conservative on purpose:
# a DB that appeared moments ago (a narrow acquire-then-crash race, or a lease
# write still in flight) must never be mistaken for an abandoned orphan just
# because a reap-orphans sweep happened to run at the wrong instant.
DEFAULT_REAP_MIN_AGE_S = 24 * 3600
# SSOT for the "no declared port" fallback (Odoo's own stock default). Also
# referenced by instances_io.py's INST_HTTP_PORT fallback so both Python
# consumers converge on one literal (P5.9 8069-fallback consolidation).
DEFAULT_HTTP_PORT = instances_io.DEFAULT_HTTP_PORT


# --------------------------------------------------------------------------- #
# Paths (mirror resolve_instances.sh precedence)
# --------------------------------------------------------------------------- #
def _home():
    """${ODOO_AI_HOME:-$HOME/.odoo-ai}, trailing slashes fully normalised -
    mirrors scripts/lib/paths.py's `_home()` exactly (parity invariant: all of
    paths.py, resolve_project_dir.sh's `_project_dir_home`, and
    resolve_instances.sh's `_odoo_ai_global_instances`/`_odoo_ai_runtime_dir`
    converge on the same root). A doubled/tripled trailing slash denotes the
    SAME directory as a single one, so it is collapsed here rather than left
    for a downstream os.path.join to preserve inconsistently with the shell
    half. An all-slashes $ODOO_AI_HOME (e.g. "/", "///") falls back to "/"."""
    override = os.environ.get("ODOO_AI_HOME")
    if override:
        return override.rstrip("/") or "/"
    return os.path.join(os.path.expanduser("~"), ".odoo-ai")


def _runtime_dir():
    d = os.path.join(_home(), "runtime")
    os.makedirs(d, exist_ok=True)
    return d


def _registry_path():
    return os.path.join(_runtime_dir(), "leases.json")


def _lock_path():
    return os.path.join(_runtime_dir(), "registry.lock")


def _instances_nonempty(path):
    """True when `path` is a file declaring at least one [[instance]] table.

    Byte-parity with scripts/lib/resolve_instances.sh `_instances_nonempty`,
    which greps `^\\[\\[instance\\]\\]` - column-anchored, so a leading-whitespace
    line does NOT count here either.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return any(line.startswith("[[instance]]") for line in fh)
    except OSError:
        return False


def resolve_instances_path(explicit=None):
    """instances.toml location: --instances > $ODOO_AI_INSTANCES > global > project.

    The global path wins only when it DECLARES an instance - the same non-empty
    test resolve_instances.sh applies - so the shell and Python halves can never
    disagree about which file is authoritative. The project-local fallthrough is
    TRANSITIONAL: returned only when it is itself non-empty, and it names itself
    on stderr. A resolution that finds no catalog at all emits a named
    diagnostic and returns the global path, so the caller fails loud on a
    missing instance instead of silently reading a wrong file.
    """
    if explicit:
        return explicit
    env = os.environ.get("ODOO_AI_INSTANCES")
    if env:
        return env
    global_path = os.path.join(_home(), "instances.toml")
    if _instances_nonempty(global_path):
        return global_path
    project_path = os.path.join(os.getcwd(), ".odoo-ai", "instances.toml")
    if _instances_nonempty(project_path):
        sys.stderr.write(
            "allocator: NO_GLOBAL_INSTANCE_CATALOG - falling through to the "
            f"transitional project-local catalog {project_path}. Run /odoo-setup "
            "to declare instances in the machine-global catalog.\n"
        )
        return project_path
    sys.stderr.write(
        "allocator: NO_INSTANCE_CATALOG - no [[instance]] table in "
        f"{global_path} or {project_path}. Run /odoo-setup to declare an instance.\n"
    )
    return global_path


# --------------------------------------------------------------------------- #
# Registry (atomic, lock-guarded)
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def _locked():
    """Hold an exclusive fcntl.flock for the registry critical section."""
    _runtime_dir()
    fd = os.open(_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_registry():
    path = _registry_path()
    if not os.path.isfile(path):
        return {"leases": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("leases"), list):
            raise ValueError("registry shape")
        return data
    except (ValueError, OSError):
        # Corrupt registry: quarantine and start fresh, loudly.
        with contextlib.suppress(OSError):
            os.replace(path, path + ".bak")
        sys.stderr.write(
            f"allocator: registry was corrupt; quarantined to {path}.bak, "
            "starting a fresh registry.\n"
        )
        return {"leases": []}


def _write_registry(reg):
    # Stamp the current schema version on every write. Readers stay lenient (a
    # missing schema_version is treated as v1), so this is explicitness for
    # test anchoring, not a load-bearing gate.
    reg["schema_version"] = 2
    path = _registry_path()
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Liveness, ports, time
# --------------------------------------------------------------------------- #
def _now():
    return int(time.time())


def _host():
    return socket.gethostname()


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    except (OSError, TypeError):
        return False
    return True


def _pid_fingerprint(pid):
    """A fingerprint of the process CURRENTLY running at `pid`, good enough to
    detect pid recycling - `ps -o lstart=` (the process's wall-clock start
    time), portable across Linux/macOS/BSD (unlike `/proc`, which is
    Linux-only). A bare `os.kill(pid, 0)` only proves SOME process holds this
    pid right now; it cannot distinguish the process a lease originally
    recorded from an unrelated one the OS later handed the same (recycled)
    pid to. A process's start time is fixed for its whole lifetime, so
    comparing it at check-time against the value captured when the pid was
    first recorded is what actually proves "same process", not just "same
    pid number".

    Returns None when the pid is not currently running or `ps` cannot report
    it (missing binary, transient failure, permission) - callers MUST treat
    None as "cannot verify", never as a match or a mismatch.

    Second-granularity (not a cryptographic identity): two unrelated processes
    that happen to start within the same wall-clock second and later collide
    on a recycled pid would fool this check. That residual risk is accepted -
    it is astronomically narrower than the bare-pid check it replaces, and
    catching it would need a portable pid+start-time-plus-more source that
    does not exist across Linux/macOS/BSD without extra dependencies.
    """
    rc, out, _ = _run(["ps", "-o", "lstart=", "-p", str(pid)])
    if rc != 0:
        return None
    out = out.strip()
    return out or None


def _pid_owner_fields(pid):
    """{'pid': int, 'pid_started': fingerprint-or-None} for recording onto a
    lease's `owner` at the moment a stable pid is learned (acquire's
    shared/exclusive/ephemeral paths, and `bind`). Capturing the fingerprint
    HERE - immediately after the pid is learned, while it still names the
    process we intend to remember - is what makes the later liveness check in
    `_is_stale` resistant to pid recycling. {'pid': None, 'pid_started': None}
    when `pid` is falsy (0/""/None), matching the existing "no stable pid
    supplied" case exactly."""
    if not pid:
        return {"pid": None, "pid_started": None}
    pid = int(pid)
    return {"pid": pid, "pid_started": _pid_fingerprint(pid)}


def _stop_group(pid, timeout_s=10):
    """Stop the whole process GROUP led by `pid`: SIGTERM, a bounded wait, then a
    group SIGKILL escalation.

    Under `setsid` at launch the Odoo server is its own session/process-group
    leader (pgid == pid), so signalling the group reaps the master AND every
    child it spawned in one shot - HTTP workers, cron, the longpolling/gevent
    process, and any `--dev=reload` watchdog - which is exactly what release/gc
    must do before a `DROP DATABASE` (a still-connected backend blocks the drop).

    If `os.getpgid` raises (a legacy pre-setsid lease whose pid is not a clean
    group leader, or a pid that already exited) we fall back to single-pid
    signalling. `ProcessLookupError`/`PermissionError`/`OSError` are swallowed
    throughout: the process dying out from under us is success, not an error.
    Caller MUST apply the same-host guard - a pid integer is meaningless on
    another host (see `_stop_owner_group_if_local`).
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    # Resolve the group ONCE; fall back to the bare pid when getpgid can't.
    try:
        pgid = os.getpgid(pid)

        def _signal(sig):
            os.killpg(pgid, sig)
    except OSError:  # ProcessLookupError (gone) / legacy non-leader pid

        def _signal(sig):
            os.kill(pid, sig)

    with contextlib.suppress(OSError):
        _signal(signal.SIGTERM)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    with contextlib.suppress(OSError):
        _signal(signal.SIGKILL)


def _stop_owner_group_if_local(lease, timeout_s=10):
    """Stop the lease's recorded server process group IFF it is a live pid on THIS
    host. Same-host guard mirrors `_is_stale`'s `owner.host` check - we NEVER
    signal a pid recorded on another host (the integer would name an unrelated
    local process). No-op when there is no pid, it is on another host, or it is
    already dead. Returns True when a stop was attempted."""
    owner = lease.get("owner", {})
    if owner.get("host") != _host():
        return False
    pid = owner.get("pid")
    if pid is None:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if not _pid_alive(pid):
        return False
    # Recycled-pid guard: when a fingerprint was recorded for this pid and the
    # CURRENT process at that pid no longer matches it, the lease's real owner
    # already exited (that is exactly how the pid became free to reuse) - there
    # is nothing of OURS left to stop, and signalling this pid now would hit an
    # unrelated bystander process instead of a runaway server. A fingerprint we
    # cannot re-measure right now (`ps` hiccup) is NOT a mismatch - proceed as
    # before (best effort), same as a lease that never recorded one at all.
    expected_fp = owner.get("pid_started")
    if expected_fp is not None:
        current_fp = _pid_fingerprint(pid)
        if current_fp is not None and current_fp != expected_fp:
            return False
    _stop_group(pid, timeout_s=timeout_s)
    return True


def _port_bindable(port):
    """True if `port` can be bound right now (free on this host)."""
    for family, addr in ((socket.AF_INET, ("", port)),):
        s = socket.socket(family, socket.SOCK_STREAM)
        try:
            s.bind(addr)
        except OSError:
            return False
        finally:
            s.close()
    return True


def _ports_in_use(reg):
    used = set()
    for lease in reg["leases"]:
        for p in lease.get("ports", []):
            used.add(int(p))
    return used


def _pick_ports(reg, base, size, n, reserved=()):
    """Pick n free ports from [base, base+size): not in the registry, not in
    `reserved` (e.g. the instance's declared/shared HTTP port - P5 port-
    uniqueness gate: a pooled lease must never collide with that port even
    when it falls inside [base, base+size)), AND bindable."""
    if n <= 0:
        return []
    used = _ports_in_use(reg) | {int(p) for p in reserved}
    chosen = []
    for p in range(base, base + size):
        if p in used:
            continue
        if not _port_bindable(p):
            continue
        chosen.append(p)
        if len(chosen) == n:
            return chosen
    raise RuntimeError(
        f"port pool exhausted: need {n} free ports in [{base},{base + size}), "
        f"found {len(chosen)} (in-use, bound, or reserved)."
    )


# --------------------------------------------------------------------------- #
# Postgres (only touched for ephemeral DB lifecycle)
# --------------------------------------------------------------------------- #
def _pg_env():
    env = os.environ.copy()
    pw = os.environ.get("ODOO_PG_PASSWORD")
    if pw:
        env["PGPASSWORD"] = pw
    return env


def _run(cmd, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"


def _probe_createdb(host, user, port=""):
    """True iff the connecting role has CREATEDB. False on any error (-> degrade).

    Threads -p <port> ONLY when a port is declared (same empty-omit rule as the
    drop path) so the probe hits the SAME cluster create/drop will use.
    """
    cmd = ["psql", "-h", host, "-U", user]
    if port:
        cmd += ["-p", str(port)]
    cmd += ["-d", "postgres", "-tAc",
            "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"]
    rc, out, _ = _run(cmd, env=_pg_env())
    return rc == 0 and out.strip() == "t"


# _createdb removed: the allocator no longer creates the ephemeral DB.
# The caller's `odoo-bin -d <db> -i <modules> --stop-after-init` performs
# create-on-init instead (B2 model: caller-side create, through-Odoo drop).
# _probe_createdb is still needed: Odoo create-on-init also requires CREATEDB,
# so if the role lacks it we degrade ephemeral -> exclusive (same invariant).


def _dropdb(host, user, db, port=""):
    """Terminate backends then drop, with retry (portable to PG10+).

    Threads -p <port> into BOTH the psql terminate-backend call and dropdb ONLY
    when a port is declared (empty-omit) so the raw fallback hits the same cluster.
    """
    env = _pg_env()
    port_args = ["-p", str(port)] if port else []
    for _ in range(3):
        _run(
            ["psql", "-h", host, "-U", user] + port_args + ["-d", "postgres", "-tAc",
             "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
             f"WHERE datname = '{db}' AND pid <> pg_backend_pid()"],
            env=env,
        )
        rc, _, err = _run(
            ["dropdb", "-h", host, "-U", user] + port_args + ["--if-exists", db], env=env)
        if rc == 0:
            return True
        time.sleep(0.5)
    sys.stderr.write(f"allocator: dropdb {db} failed after retries: {err.strip()}\n")
    return False


def _filestore_dir(db):
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "Odoo", "filestore", db)


def _drop_filestore(db):
    import shutil

    path = _filestore_dir(db)
    with contextlib.suppress(OSError):
        shutil.rmtree(path, ignore_errors=True)


_ODOO_DB_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odoo_db.py")


def _drop_through_odoo(lease):
    """Drop the ephemeral DB via odoo_db.py (through-Odoo path, B2 mandate).

    Falls back to raw _dropdb ONLY when:
      - the lease carries no `python` interpreter path, OR
      - odoo_db.py is missing on disk, OR
      - odoo_db.py exits with code 10 (venv-unavailable sentinel).

    Any OTHER non-zero exit is a genuine exp_drop failure.  In that case the
    allocator does NOT fall back to raw dropdb, does NOT drop the filestore,
    and does NOT remove the lease (so gc can retry / a human can investigate).
    Returns True on success, False when the drop failed and the lease must be kept.

    Any fallback (rc=10 / no venv) is logged loudly to stderr.
    The filestore is cleaned up ONLY after a successful drop.
    """
    db = lease.get("db_name", "")
    if not db:
        return True
    # New leases store db_host/db_user at the top level; fall back to _pg for
    # leases written by an older allocator version (backward compat).
    pg = lease.get("_pg", {})
    host = lease.get("db_host") or pg.get("host", "localhost")
    user = lease.get("db_user") or pg.get("user", "odoo")
    # Postgres port travels top-level with a _pg mirror for backward compat.
    # Empty -> omit the flag (same empty-omit rule as the rest of the port surface).
    port = lease.get("db_port") or pg.get("port", "")
    venv_python = lease.get("python", "")

    if venv_python and os.path.isfile(_ODOO_DB_PY):
        cmd = [venv_python, _ODOO_DB_PY, "drop", db, "--db-host", host, "--db-user", user]
        if port:
            cmd += ["--db-port", str(port)]
        pw = os.environ.get("ODOO_PG_PASSWORD")
        if pw:
            cmd += ["--db-password", pw]
        rc, _, err = _run(cmd)
        if rc == 0:
            _drop_filestore(db)
            return True
        elif rc == 10:
            # venv-unavailable sentinel: fall back to raw dropdb (logged).
            sys.stderr.write(
                "allocator: WARNING - venv unavailable ({python}), "
                "dropped {db} via raw dropdb fallback\n".format(
                    python=venv_python, db=db)
            )
            _dropdb(host, user, db, port)
            _drop_filestore(db)
            return True
        else:
            # Genuine exp_drop failure - retain the DB and the lease for retry.
            sys.stderr.write(
                "allocator: ERROR - through-Odoo drop of {db} failed (rc={rc}); "
                "DB retained, lease kept for retry. stderr: {err}\n".format(
                    db=db, rc=rc, err=err.strip())
            )
            return False

    # No venv python or odoo_db.py missing: fall back to raw dropdb.
    if not venv_python:
        sys.stderr.write(
            "allocator: WARNING - venv unavailable, "
            "dropped {db} via raw dropdb fallback\n".format(db=db)
        )
    else:
        # odoo_db.py missing on disk (should not happen, but handle gracefully).
        sys.stderr.write(
            "allocator: WARNING - odoo_db.py not found at {path}, "
            "dropped {db} via raw dropdb fallback\n".format(
                path=_ODOO_DB_PY, db=db)
        )
    _dropdb(host, user, db, port)
    _drop_filestore(db)
    return True


# --------------------------------------------------------------------------- #
# GC
# --------------------------------------------------------------------------- #
def _is_stale(lease):
    """Liveness is AUTHORITATIVE, not merely a condemn-only signal.

    Direction matters (state it explicitly so a future edit does not invert
    it): for reaping, the safe default is to NOT reap when unsure - an
    un-reaped orphan only costs RAM, but a wrongly-reaped lease kills a live
    server and destroys the owner's in-progress work. So:
      - A DEAD pid on THIS host is an unambiguous, TTL-independent condemn:
        the recorded owner is provably gone: reclaim now (RAM matters, and
        there is nothing left to protect).
      - A LIVE pid on THIS host PROTECTS the lease - but only when we can
        prove it is the SAME process the lease recorded, not a pid-recycled
        impostor (pids are reused; a bare `os.kill(pid, 0)` cannot tell the
        two apart). Proof is the `pid_started` fingerprint captured at
        record time (see `_pid_owner_fields`/`_pid_fingerprint`): if it
        still matches, the lease is protected REGARDLESS of TTL - a
        long-running, healthy process is never reaped just because nobody
        called `heartbeat`. If it POSITIVELY mismatches (the pid was
        recycled onto a different process), the recorded owner is exactly as
        gone as a dead pid: condemn now, same as the dead-pid arm.
      - Every case where liveness cannot be proven - a DIFFERENT host (the
        pid integer is meaningless off-host), no pid ever recorded, or a
        fingerprint that could not be re-measured just now (a `ps` hiccup,
        not a proven mismatch) - falls through to the TTL/heartbeat check,
        exactly as before this fix. TTL is now scoped to precisely this
        residual "cannot verify" case; see DEFAULT_TTL_S for why its value
        was reconsidered under that narrower scope.
    """
    owner = lease.get("owner", {})
    if owner.get("host") == _host():
        pid = owner.get("pid")
        if pid is not None:
            pid = int(pid)
            if not _pid_alive(pid):
                return True  # condemn arm: unambiguous, no fingerprint needed
            expected_fp = owner.get("pid_started")
            if expected_fp is not None:
                current_fp = _pid_fingerprint(pid)
                if current_fp is not None:
                    if current_fp == expected_fp:
                        return False  # PROVEN alive: protected, TTL not consulted
                    return True  # PROVEN recycled: owner is as gone as a dead pid
                # current_fp is None: could not re-measure right now - not a
                # proven mismatch, so do not condemn on ambiguity; fall through.
            # else: no fingerprint was ever recorded for this lease (an older
            # allocator, or `ps` was unavailable at record time) - liveness is
            # UNPROVABLE here; fall through to TTL, same as a different host.
    ttl = lease.get("ttl_s", DEFAULT_TTL_S)
    if _now() - lease.get("heartbeat_at", lease.get("owner", {}).get("started_at", 0)) > ttl:
        return True
    return False


def _gc(reg):
    """Reclaim stale leases (drop their ephemeral DB via through-Odoo path). Mutates reg."""
    kept, reclaimed = [], []
    for lease in reg["leases"]:
        if _is_stale(lease):
            # Reap the ORPHAN before reclaiming: a lease can be stale by ttl while
            # its server process is STILL alive (the box did not crash, the owner
            # just went away). Stop that process group first so we free RAM AND so
            # the drop below is not blocked by a live backend. A dead pid here is a
            # no-op (the same-host + liveness guard short-circuits).
            _stop_owner_group_if_local(lease)
            if lease.get("drop_on_release") and lease.get("db_name"):
                drop_ok = _drop_through_odoo(lease)
                if not drop_ok:
                    # Genuine drop failure: retain the lease so a human / next gc
                    # can retry.  Do not count it as reclaimed.
                    kept.append(lease)
                    continue
            reclaimed.append(lease)
        else:
            kept.append(lease)
    reg["leases"] = kept
    return reclaimed


# --------------------------------------------------------------------------- #
# Emit
# --------------------------------------------------------------------------- #
def _emit(name, value):
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    print(f"{name}={shlex.quote(str(value))}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _resolve_instance(path, series, profile=None):
    items = instances_io.load_instances(path)
    inst, _ = instances_io.select_instance(items, series or None, profile=profile or None)
    # Return the FULL catalog alongside the selected instance: cmd_acquire needs
    # every declared http_port (not just the selected one) to close the
    # boundary off-by-one (P2 §2.3) - this is the same load_instances() call
    # (no second read), so callers get it for free.
    return inst, items


def _resolve_addons_csv(inst, override):
    """Return (comma_joined_addons_path, error_or_None) for this acquire.

    With no override the catalog value is returned unchanged (byte-identical to
    the pre-override behavior), via the SSOT `instances_io.join_addons_path`.
    An override REPLACES it: accepted comma- OR colon-separated (tolerated by
    the SSOT `instances_io.split_addons_path`), always re-emitted COMMA-
    separated via `join_addons_path`, because Odoo's --addons-path parser
    splits on comma only (see the lease comment below). Every entry must be an
    existing directory - a non-existent entry is refused loudly, so a mistyped
    worktree path can never produce a green run against the wrong tree. This
    function never hand-rolls the separator - both branches go through the
    instances_io SSOT, the same one every other producer/consumer uses.
    """
    if not override:
        return instances_io.join_addons_path(inst.get("addons_path", [])), None
    parts = instances_io.split_addons_path(override)
    if not parts:
        return None, "--addons-path-override is empty"
    missing = [p for p in parts if not os.path.isdir(p)]
    if missing:
        return None, (
            "--addons-path-override names non-existent directories: "
            + ", ".join(missing)
        )
    return instances_io.join_addons_path(parts), None


def _git_rc_out(argv):
    rc, out, _ = _run(argv)
    return rc, out.strip()


def _git_common_dir(path):
    """Absolute git-common-dir for `path`, or "" when `path` is not inside a
    git working tree (or `git` is unavailable).

    git-common-dir is IDENTICAL across every worktree of one repository (the
    principal checkout and every `git worktree add` linked off it all share
    ONE `.git` directory), while `--show-toplevel` differs per checkout - that
    pairing is the fingerprint `_addons_path_worktree_mismatch` uses below."""
    rc, out = _git_rc_out(["git", "-C", path, "rev-parse", "--git-common-dir"])
    if rc != 0 or not out:
        return ""
    return out if os.path.isabs(out) else os.path.realpath(os.path.join(path, out))


def _git_toplevel(path):
    """Absolute worktree root for `path`, or "" when not inside a git working
    tree (or `git` is unavailable)."""
    rc, out = _git_rc_out(["git", "-C", path, "rev-parse", "--show-toplevel"])
    if rc != 0 or not out:
        return ""
    return os.path.realpath(out)


def _addons_path_worktree_mismatch(addons_entries):
    """Detect the false-green shape: the caller's cwd is a git worktree of the
    SAME repository as one of the (unoverridden) catalog `addons_path` entries,
    but at a DIFFERENT checkout path than the one the catalog declares - e.g.
    the caller sits in a linked worktree carrying a fix while the catalog still
    points at the principal checkout (the pre-fix code), so a build driven by
    the catalog default would silently install and verify the wrong tree.

    Returns (mismatched_catalog_entry, cwd_toplevel) when detected, else
    (None, None) - which covers every benign case: cwd is not a git repo (or
    git is unavailable), the caller genuinely IS standing in the checkout the
    catalog declares (entry_top == cwd_top), or no addons_path entry shares
    cwd's repository at all (an unrelated project - never this check's
    business). A non-existent or non-directory entry is skipped outright."""
    cwd = os.getcwd()
    cwd_common = _git_common_dir(cwd)
    if not cwd_common:
        return None, None
    cwd_top = _git_toplevel(cwd)
    for entry in addons_entries:
        if not entry or not os.path.isdir(entry):
            continue
        entry_common = _git_common_dir(entry)
        if not entry_common or entry_common != cwd_common:
            continue
        entry_top = _git_toplevel(entry)
        if entry_top and entry_top != cwd_top:
            return entry, cwd_top
    return None, None


def _emit_instance_common(inst, addons_csv=None):
    _emit("ALLOC_PYTHON", inst.get("python", ""))
    _emit(
        "ALLOC_ADDONS_PATH",
        addons_csv if addons_csv is not None
        else instances_io.join_addons_path(inst.get("addons_path", [])),
    )
    _emit("ALLOC_DB_HOST", inst.get("db_host", "localhost"))
    _emit("ALLOC_DB_USER", inst.get("db_user", "odoo"))
    # db_port is EMPTY when undeclared (never 5432); the handle forwards it so
    # create and drop connect to the same resolved cluster port, so a drop against
    # the wrong port never silently no-ops.
    _emit("ALLOC_DB_PORT", inst.get("db_port", ""))
    _emit("ALLOC_SERIES", instances_io.series_of(inst))
    _emit("ALLOC_PROFILE", instances_io.profile_of(inst))


def cmd_acquire(opts):
    path = resolve_instances_path(opts.get("instances"))
    series = opts.get("series", "")
    profile = opts.get("profile", "")
    inst, catalog_items = _resolve_instance(path, series, profile=profile or None)
    if inst is None:
        sys.stderr.write(
            f"allocator: no instance for series {series!r} in {path}. "
            "Declare one via /odoo-setup or pass --instances.\n"
        )
        return 1

    addons_csv, addons_err = _resolve_addons_csv(inst, opts.get("addons_path_override"))
    if addons_err:
        sys.stderr.write(f"allocator: {addons_err}\n")
        return 2

    mode = opts.get("mode", "ephemeral")
    host = inst.get("db_host", "localhost")
    user = inst.get("db_user", "odoo")
    # Postgres port (empty when undeclared -> omit everywhere).
    db_port = inst.get("db_port", "")
    # Canonical ownership key: --run-id (or the --session back-compat alias).
    # Empty for a standalone one-off run -> the lease is unowned (ownership then
    # degrades to token-possession, today's behavior).
    run_id = opts.get("run_id") or opts.get("session", "")

    # readonly: lease-free; just surface the running instance's coordinates.
    if mode == "readonly":
        _emit("ALLOC_TOKEN", "")
        _emit("ALLOC_MODE", "readonly")
        _emit("ALLOC_DB_NAME", inst.get("db_name", "odoo"))
        _emit("ALLOC_PORTS", [inst.get("http_port", DEFAULT_HTTP_PORT)])
        _emit("ALLOC_RUN_ID", run_id)
        _emit_instance_common(inst, addons_csv)
        return 0

    # False-green guard (issue class: a wrong-tree default silently verified):
    # only engages when the caller did NOT pass --addons-path-override - an
    # explicit override already IS the caller stating the tree, which is the
    # whole fix, so this never re-litigates it. Skipped for readonly above
    # (nothing is built there); applies to shared/ephemeral/exclusive alike.
    if not opts.get("addons_path_override"):
        mismatched_entry, cwd_top = _addons_path_worktree_mismatch(
            instances_io.split_addons_path(addons_csv)
        )
        if mismatched_entry:
            sys.stderr.write(
                "allocator: refusing to default ALLOC_ADDONS_PATH - this "
                f"directory ({cwd_top}) is a git worktree of the SAME "
                f"repository as catalog entry {mismatched_entry!r}, but the "
                "catalog still points at THAT OTHER checkout. Building "
                "against the catalog default here would silently install "
                "and verify a different checkout of your own repo (a "
                "false-green generator). Pass --addons-path-override "
                f"{cwd_top!r} to build against THIS worktree, or pass "
                "--addons-path-override naming the checkout you actually "
                "intend, explicitly.\n"
            )
            return 5

    # shared: a long-lived, NON-exclusive render-server lease (the visual stack's
    # live target). Attach to the existing lease for (series, db_name) when one is
    # live, else mint one. drop_on_release is ALWAYS False, so gc reclaims a dead
    # row but NEVER drops the declared DB. Idempotent: a later call carrying the
    # real server --pid (or the actual bound --port) refreshes the row in place.
    if mode == "shared":
        db_name = opts.get("db_name") or inst.get("db_name", "odoo")
        series_c = instances_io.series_of(inst)
        port = opts.get("port")
        ports = [int(port)] if port else []
        attached = 0
        with _locked():
            reg = _read_registry()
            _gc(reg)
            existing = next(
                (lz for lz in reg["leases"]
                 if lz.get("mode") == "shared"
                 and lz.get("series") == series_c
                 and lz.get("db_name") == db_name),
                None,
            )
            now = _now()
            if existing is not None:
                attached = 1
                token = existing.get("token")
                if opts.get("pid"):
                    existing.setdefault("owner", {}).update(_pid_owner_fields(opts["pid"]))
                if ports:
                    existing["ports"] = ports
                else:
                    ports = existing.get("ports", [])
                existing["heartbeat_at"] = now
                # Refresh profile when caller supplies it (idempotent re-register).
                if profile:
                    existing["profile"] = profile
            else:
                token = uuid.uuid4().hex
                new_lease = {
                    "token": token,
                    "mode": "shared",
                    "series": series_c,
                    "db_name": db_name,
                    # drop_on_release is ALWAYS False for shared leases:
                    # the declared DB must never be dropped by gc/release.
                    "drop_on_release": False,
                    "ports": ports,
                    "db_port": db_port,
                    "owner": {
                        "host": _host(),
                        # run_id is the CANONICAL ownership key; the dead
                        # standalone session_id is no longer written on new leases.
                        "run_id": run_id,
                        "started_at": now,
                        # pid + pid_started (recycling-resistant fingerprint,
                        # see _pid_owner_fields/_is_stale) - {None, None} when
                        # the caller passes no --pid.
                        **_pid_owner_fields(opts.get("pid")),
                    },
                    "ttl_s": int(opts.get("ttl", DEFAULT_TTL_S)),
                    "heartbeat_at": now,
                    "_pg": {"host": host, "user": user, "port": db_port},
                }
                if profile:
                    new_lease["profile"] = profile
                reg["leases"].append(new_lease)
            _write_registry(reg)
        _emit("ALLOC_TOKEN", token)
        _emit("ALLOC_MODE", "shared")
        _emit("ALLOC_DB_NAME", db_name)
        _emit("ALLOC_PORTS", ports)
        _emit("ALLOC_ATTACHED", attached)
        _emit("ALLOC_RUN_ID", run_id)
        _emit_instance_common(inst, addons_csv)
        return 0

    if mode not in ("ephemeral", "exclusive"):
        sys.stderr.write(f"allocator: unknown --mode {mode!r}\n")
        return 2

    n_ports = int(opts.get("ports", 0))
    # P5 port-uniqueness gate: the declared HTTP port is reserved for the
    # shared/declared render target (readonly/shared modes above) and must
    # NEVER be handed out as a pooled ephemeral/exclusive port - not even when
    # the profile declares no separate http_port_base, which would otherwise
    # make the pool start counting AT the declared port itself. Default the
    # base to declared_port + 1 (skip it outright), and ALSO pass it as
    # `reserved` so a misconfigured http_port_base that overlaps the declared
    # port still can't collide.
    declared_port = int(inst.get("http_port", DEFAULT_HTTP_PORT))
    base = int(inst.get("http_port_base", declared_port + 1))
    size = int(inst.get("port_pool_size", DEFAULT_POOL_SIZE))
    prefix = inst.get("db_name_prefix", inst.get("db_name", "odoo"))

    # P2 §2.3 boundary off-by-one fix: reserve EVERY catalog-declared http_port,
    # not just the acquiring instance's own. Declared ports step by 10
    # (40-instance-profile.sh) while a pool spans DEFAULT_POOL_SIZE=10 ports
    # starting at declared+1, so instance-0's pool would otherwise end AT
    # instance-1's declared port (e.g. 8079) and could hand it out. catalog_items
    # was already loaded via load_instances() in _resolve_instance() ABOVE this
    # point - i.e. before the `with _locked()` critical section below - so this
    # reserves the whole catalog with no new lock and no deadlock risk.
    reserved_ports = {declared_port}
    for _item in catalog_items:
        try:
            reserved_ports.add(int(_item.get("http_port", DEFAULT_HTTP_PORT)))
        except (TypeError, ValueError):
            continue

    # B2 model: the allocator NO LONGER calls createdb.  The ephemeral DB is
    # created by the caller's `odoo-bin -d <db> -i <mods> --stop-after-init`
    # (Odoo create-on-init).  We still probe CREATEDB because Odoo create-on-init
    # also requires the role to have that privilege; if it is absent, degrading to
    # the declared exclusive DB (which already exists) is still the right move.
    if mode == "ephemeral":
        if not opts.get("no_create") and not _probe_createdb(host, user, db_port):
            sys.stderr.write(
                "allocator: role lacks CREATEDB - degrading ephemeral -> exclusive "
                "on the declared database.\n"
            )
            mode = "exclusive"

    if mode == "ephemeral":
        db_name = f"{prefix}_t_{uuid.uuid4().hex[:8]}"
    else:
        db_name = opts.get("db_name") or inst.get("db_name", "odoo")

    with _locked():
        reg = _read_registry()
        _gc(reg)

        if mode == "exclusive":
            for lease in reg["leases"]:
                if lease.get("mode") == "exclusive" and lease.get("db_name") == db_name:
                    sys.stderr.write(
                        f"allocator: database {db_name!r} is already held by an "
                        f"exclusive lease (token {lease.get('token')}). Retry later "
                        "or use --mode ephemeral.\n"
                    )
                    return 3

        try:
            ports = _pick_ports(reg, base, size, n_ports, reserved=reserved_ports)
        except RuntimeError as exc:
            sys.stderr.write(f"allocator: {exc}\n")
            return 4

        # drop_on_release: True for ephemeral leases where the caller will create
        # the DB via Odoo create-on-init and we must drop it at release/gc.
        # False when --no-create is passed (caller declared they won't create the
        # DB, so there is nothing to drop), and always False for shared/exclusive
        # (those DBs must survive beyond the lease lifetime).
        drop_on_release = (mode == "ephemeral" and not opts.get("no_create"))

        token = uuid.uuid4().hex
        ttl = int(opts.get("ttl", DEFAULT_TTL_S))
        now = _now()
        series_val = instances_io.series_of(inst)
        reg["leases"].append({
            "token": token,
            "mode": mode,
            "series": series_val,
            "db_name": db_name,
            # drop_on_release replaces the old created_db flag.  It marks whether
            # release/gc must drop the DB (ephemeral=True, shared/exclusive=False).
            "drop_on_release": drop_on_release,
            # Drop context: venv interpreter + connection params so _drop_through_odoo
            # can invoke odoo_db.py under the right Odoo installation at release/gc
            # time, even if the caller process is long gone.  Password is NOT stored
            # here - read from ODOO_PG_PASSWORD at drop time.
            "python": inst.get("python", ""),
            # addons_path is forward-context only (for future tooling that may want
            # to launch odoo-bin from the lease); the drop path never reads it.
            # Odoo's --addons-path/addons_path takes COMMA-separated directories
            # (never colon - that is PATH/PYTHONPATH style, not Odoo's addons-path
            # syntax), matching ALLOC_ADDONS_PATH above - so any future consumer can
            # forward this value to odoo-bin verbatim, with no extra conversion step.
            "addons_path": addons_csv,
            "db_host": host,
            "db_user": user,
            # db_port travels top-level beside db_host/db_user; empty when undeclared.
            "db_port": db_port,
            "ports": ports,
            "owner": {
                "host": _host(),
                # run_id is the CANONICAL ownership key; the dead standalone
                # session_id is no longer written on new leases (read as a
                # compat fallback only, on pre-existing leases).
                "run_id": run_id,
                "started_at": now,
                # pid + pid_started are a FAST-PATH reclaim/protect signal only -
                # recorded solely when the caller passes a stable, long-lived
                # --pid. We never default to the transient bash pid (it dies
                # right after this call returns, which would let the next gc
                # wrongly CONDEMN a lease whose DB is still in use - the dead-pid
                # arm of `_is_stale` would fire on that transient pid). With no
                # --pid, staleness falls back entirely to ttl_s + heartbeat
                # (liveness is unprovable without one). pid_started is the
                # recycling-resistant fingerprint `_is_stale` needs to PROTECT
                # (not just condemn) a verified-alive owner - see
                # `_pid_owner_fields`.
                **_pid_owner_fields(opts.get("pid")),
            },
            "ttl_s": ttl,
            "heartbeat_at": now,
            "_pg": {"host": host, "user": user, "port": db_port},
        })
        _write_registry(reg)

    _emit("ALLOC_TOKEN", token)
    _emit("ALLOC_MODE", mode)
    _emit("ALLOC_DB_NAME", db_name)
    _emit("ALLOC_PORTS", ports)
    _emit("ALLOC_RUN_ID", run_id)
    _emit_instance_common(inst, addons_csv)
    return 0


def cmd_release(opts):
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py release <token>\n")
        return 2
    with _locked():
        reg = _read_registry()
        kept, found = [], None
        for lease in reg["leases"]:
            if lease.get("token") == token:
                found = lease
            else:
                kept.append(lease)
        if found is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} (already released?).\n")
            return 0

        # Ownership guard - NOT self-blocking. REFUSE the release IFF
        # the caller identifies as a DIFFERENT non-empty run than the owner. Every
        # other case proceeds on token-possession:
        #   - caller_run == ""  -> release site forwarded no run id -> token-possession
        #   - owner_run  == ""  -> unowned / legacy lease            -> token-possession
        #   - caller_run == owner_run -> owner releasing its own lease
        # This never blocks the rightful owner just because the run id was not
        # threaded to the release call. --force overrides with a loud line.
        caller_run = opts.get("run_id") or opts.get("session", "")
        owner = found.get("owner", {})
        owner_run = owner.get("run_id") or owner.get("session_id", "")
        force = opts.get("force")
        if owner_run and caller_run and owner_run != caller_run:
            if not force:
                sys.stderr.write(
                    "allocator: refusing to release the lease for db "
                    f"{found.get('db_name')!r}: it is owned by run {owner_run!r}, "
                    f"but the caller's run is {caller_run!r}. Pass --force to override "
                    "(the DB is NOT dropped and the lease is kept).\n"
                )
                return 1
            sys.stderr.write(
                f"allocator: force-releasing run {owner_run!r}'s lease "
                f"(caller run {caller_run!r}).\n"
            )

        # Teardown ORDER is mandatory (L1.2): stop the server's process group
        # FIRST, THEN drop the DB. A listening Odoo master + workers hold open DB
        # connections, and an active backend blocks `DROP DATABASE`; stopping the
        # group closes those connections (odoo_db.py's pg_terminate_backend stays
        # as a second belt). No-op for a lease with no live local pid (legacy
        # pre-setsid / shared / already-dead), so this is always safe to call.
        _stop_owner_group_if_local(found)

        if found.get("drop_on_release") and found.get("db_name"):
            drop_ok = _drop_through_odoo(found)
            if not drop_ok:
                # Genuine drop failure: retain the lease, signal error to caller.
                # The lease stays in the registry so gc can retry.
                reg["leases"] = kept + [found]
                _write_registry(reg)
                return 1
        reg["leases"] = kept
        _write_registry(reg)
    return 0


def cmd_heartbeat(opts):
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py heartbeat <token>\n")
        return 2
    with _locked():
        reg = _read_registry()
        hit = False
        for lease in reg["leases"]:
            if lease.get("token") == token:
                lease["heartbeat_at"] = _now()
                hit = True
        if hit:
            _write_registry(reg)
        else:
            sys.stderr.write(f"allocator: no lease with token {token!r}.\n")
            return 1
    return 0


def cmd_bind(opts):
    """Bind a live server pid onto an EXISTING lease (under flock).

    The exclusive-running spin-up acquires its lease FIRST (reserving the db +
    ports) and only later learns the launched server's pid; `bind` upserts that
    pid (plus its recycling-resistant `pid_started` fingerprint, see
    `_pid_owner_fields`) onto the SAME `owner.pid`/`owner.pid_started` slots the
    shared-acquire path already writes, so release/gc can stop the whole
    process group before the drop (L1.1), and so `_is_stale` can PROTECT this
    lease once it is verified alive. Refuses an unknown token and a missing
    --pid; reuses the token-scan + write helpers (no second ledger path)."""
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py bind <token> --pid <server_pid>\n")
        return 2
    pid = opts.get("pid")
    if not pid:
        sys.stderr.write("Usage: allocator.py bind <token> --pid <server_pid>\n")
        return 2
    with _locked():
        reg = _read_registry()
        hit = False
        for lease in reg["leases"]:
            if lease.get("token") == token:
                lease.setdefault("owner", {}).update(_pid_owner_fields(pid))
                hit = True
        if hit:
            _write_registry(reg)
        else:
            sys.stderr.write(f"allocator: no lease with token {token!r} to bind.\n")
            return 1
    return 0


def cmd_gc(opts):
    with _locked():
        reg = _read_registry()
        reclaimed = _gc(reg)
        _write_registry(reg)
    for lease in reclaimed:
        _emit("ALLOC_RECLAIMED", lease.get("token", ""))
    print(f"# reclaimed {len(reclaimed)} stale lease(s)")
    return 0


# --------------------------------------------------------------------------- #
# reap-orphans: DB-side sweep INDEPENDENT of the lease registry.
#
# `gc` (above) only ever reclaims a DB that a LEASE still references (it drops
# the DB attached to a stale lease). It has no path for a DB that exists with
# ZERO lease reference at all - a lease-write that never happened (a registry
# quarantine after corruption, an ancient pre-B2 allocator, a process that
# died in the single narrow window between reserving a db_name and the lease
# write reaching disk). Such a DB is invisible to every registry-driven path
# and, before this command existed, had NO reaping path whatsoever.
#
# Ownership predicate a candidate must satisfy on ALL THREE axes before it is
# even LISTED (never mind dropped) - see _reap_candidates:
#   1. name matches the ephemeral shape for a KNOWN catalog prefix
#      (<prefix>_t_<8-hex>) - a named/declared instance's DB can NEVER match
#      this shape, so it can never be a candidate, full stop.
#   2. NO lease references the db_name at all - live OR stale. A leased DB,
#      even a stale one, is `gc`'s/`release`'s job exclusively; reap-orphans
#      never competes with the registry-driven path.
#   3. Age is POSITIVELY PROVEN (via pg_stat_file's mtime proxy - Postgres
#      records no creation time) and >= --min-age-s. An age this process
#      CANNOT measure (missing privilege, connection hiccup) is treated as
#      NOT proven old enough - fail-closed, never "assume it's fine".
#
# Any cluster this process cannot reach is SKIPPED (never assumed empty), and
# --yes is required to actually drop anything: the default is list-only, so a
# sweep is always a visible, auditable read before it is ever destructive.
# --------------------------------------------------------------------------- #
def _is_ephemeral_shaped(db_name, prefixes):
    """True iff `db_name` matches `<prefix>_t_<8-hex>` for ANY prefix in
    `prefixes` (every catalog instance's db_name_prefix/db_name) - the SAME
    shape `cmd_acquire` mints ephemeral DBs under. A named/declared instance's
    db_name can never satisfy this (it has no `_t_<hex8>` suffix), which is
    what keeps reap-orphans from ever touching one."""
    import re

    for prefix in prefixes:
        if not prefix:
            continue
        if re.fullmatch(re.escape(prefix) + r"_t_[0-9a-f]{8}", db_name):
            return True
    return False


def _reap_candidates(dbs, leased_names, prefixes, min_age_s):
    """Pure decision function (no I/O) implementing the ownership predicate
    above. `dbs` is an iterable of {"name", "age_s" (float|None), ...} dicts
    already filtered to ONE cluster's non-template databases. Returns
    (candidates, skipped) - `candidates` are the dicts eligible to reap;
    `skipped` is a list of (name, reason) for every ephemeral-shaped, unleased
    db this pass did NOT propose, so a caller sees what was excluded and why,
    never silently. A db that is not even ephemeral-shaped, or IS leased, is
    not our business at all and appears in neither list (this command has
    nothing to say about it)."""
    candidates, skipped = [], []
    for db in dbs:
        name = db["name"]
        if not _is_ephemeral_shaped(name, prefixes):
            continue
        if name in leased_names:
            continue
        age = db.get("age_s")
        if age is None:
            skipped.append((name, "age unknown (could not measure) - skipped, not reaped"))
            continue
        if age < min_age_s:
            skipped.append((name, f"age {age:.0f}s < min-age {min_age_s:.0f}s - too young to reap"))
            continue
        candidates.append(db)
    return candidates, skipped


def _list_cluster_databases(host, user, port):
    """Non-template datnames on this cluster, or None on ANY psql failure
    (connection refused, auth failure, missing psql binary). None means
    "could not enumerate" - NEVER conflated with an empty list, so a cluster
    this process cannot currently reach is skipped, not silently treated as
    having zero orphans."""
    cmd = ["psql", "-h", host, "-U", user]
    if port:
        cmd += ["-p", str(port)]
    cmd += ["-d", "postgres", "-tAc", "SELECT datname FROM pg_database WHERE datistemplate = false"]
    rc, out, _ = _run(cmd, env=_pg_env())
    if rc != 0:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _db_age_s(host, user, port, db_name):
    """Best-effort DB age in seconds via pg_stat_file's mtime on PG_VERSION -
    the same proxy a human operator uses to eyeball this by hand, since
    Postgres itself records no database creation time. Returns None on ANY
    failure (pg_stat_file needs elevated privilege on many Postgres builds;
    a connection error; a db that vanished between enumeration and this call) -
    callers MUST treat None as unknown, never as "0 / just created"."""
    cmd = ["psql", "-h", host, "-U", user]
    if port:
        cmd += ["-p", str(port)]
    cmd += ["-d", "postgres", "-tAc",
            "SELECT extract(epoch FROM (now() - "
            "(pg_stat_file('base/'||oid||'/PG_VERSION')).modification)) "
            f"FROM pg_database WHERE datname = '{db_name}'"]
    rc, out, _ = _run(cmd, env=_pg_env())
    out = out.strip()
    if rc != 0 or not out:
        return None
    try:
        return float(out)
    except ValueError:
        return None


def _db_size_bytes(host, user, port, db_name):
    """Best-effort size via pg_database_size; None on any failure. Reporting-
    only - it never gates the reap decision."""
    cmd = ["psql", "-h", host, "-U", user]
    if port:
        cmd += ["-p", str(port)]
    cmd += ["-d", "postgres", "-tAc", f"SELECT pg_database_size('{db_name}')"]
    rc, out, _ = _run(cmd, env=_pg_env())
    out = out.strip()
    if rc != 0 or not out:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def cmd_reap_orphans(opts):
    path = resolve_instances_path(opts.get("instances"))
    items = instances_io.load_instances(path)
    if not items:
        sys.stderr.write(f"allocator: no instances declared in {path}; nothing to reap.\n")
        return 0

    min_age_s = float(opts.get("min_age_s") or DEFAULT_REAP_MIN_AGE_S)
    yes = bool(opts.get("yes"))

    # Every prefix ANY declared instance could mint an ephemeral DB under - a
    # db from a series other than what a future caller happens to name here
    # must still be recognisable as an orphan of ITS OWN series' pool.
    prefixes = sorted({
        str(it.get("db_name_prefix") or it.get("db_name", "odoo")) for it in items
    })

    # Leased db_names, live OR stale: reap-orphans must NEVER compete with the
    # registry-driven gc/release path - a leased DB, even a stale one, is that
    # path's job exclusively (read-only peek; no lock needed since we never
    # write the registry from here).
    reg = _read_registry()
    leased_names = {lz.get("db_name") for lz in reg.get("leases", []) if lz.get("db_name")}

    # Dedup clusters by connection identity so a multi-series catalog on one
    # Postgres cluster is queried once, not once per declared instance.
    clusters = {}
    for it in items:
        key = (it.get("db_host", "localhost"), it.get("db_user", "odoo"), it.get("db_port", ""))
        clusters[key] = True

    all_candidates, all_skipped, unreachable = [], [], []
    for host, user, port in clusters:
        names = _list_cluster_databases(host, user, port)
        if names is None:
            unreachable.append(f"{user}@{host}:{port or 'default'}")
            continue
        dbs = []
        for name in names:
            if not _is_ephemeral_shaped(name, prefixes):
                continue  # cheap pre-filter before any per-db psql round-trip
            if name in leased_names:
                continue
            dbs.append({
                "name": name,
                "age_s": _db_age_s(host, user, port, name),
                "size_bytes": _db_size_bytes(host, user, port, name),
                "host": host, "user": user, "port": port,
            })
        cands, skipped = _reap_candidates(dbs, leased_names, prefixes, min_age_s)
        all_candidates.extend(cands)
        all_skipped.extend(skipped)

    for cluster in unreachable:
        sys.stderr.write(f"allocator: reap-orphans could not reach {cluster}; skipped.\n")

    for name, reason in all_skipped:
        _emit("REAP_SKIPPED", f"{name}: {reason}")

    dropped, failed = [], []
    for db in all_candidates:
        age_h = (db["age_s"] or 0) / 3600
        size_mb = (db["size_bytes"] or 0) / (1024 * 1024)
        _emit("REAP_CANDIDATE", f"{db['name']} age_h={age_h:.1f} size_mb={size_mb:.1f}")
        if yes:
            if _dropdb(db["host"], db["user"], db["name"], db["port"]):
                _drop_filestore(db["name"])
                dropped.append(db["name"])
            else:
                failed.append(db["name"])

    if yes:
        for name in dropped:
            _emit("REAP_DROPPED", name)
        print(f"# reaped {len(dropped)} orphan(s), {len(failed)} failure(s)")
        return 1 if failed else 0

    print(f"# {len(all_candidates)} orphan candidate(s) found (list-only - pass --yes to drop)")
    return 0


def cmd_query(opts):
    """Read-only cross-session discovery: emit the live `shared` lease for a
    series (the running render server's actual port + db), or exit 1 if none.
    Does not mutate the registry; a stale row is simply skipped (gc reclaims it).
    """
    series = opts.get("series", "")
    reg = _read_registry()
    for lease in reg["leases"]:
        if (lease.get("mode") == "shared"
                and lease.get("series") == series
                and not _is_stale(lease)):
            _emit("ALLOC_TOKEN", lease.get("token", ""))
            _emit("ALLOC_MODE", "shared")
            _emit("ALLOC_DB_NAME", lease.get("db_name", ""))
            _emit("ALLOC_PORTS", lease.get("ports", []))
            return 0
    return 1


def cmd_list(opts):
    reg = _read_registry()
    # Redact each token to an 8-char fingerprint by default so a `list` scrape
    # can no longer hand a full token to `release`. --show-tokens reveals them for
    # debugging. This is an ACCIDENT-PREVENTION layer, not a security boundary
    # (the possession model is unchanged), consistent with run_id being a
    # semi-discoverable slug.
    if not opts.get("show_tokens"):
        for lease in reg.get("leases", []):
            tok = lease.get("token")
            if tok:
                lease["token"] = tok[:8]
    print(json.dumps(reg, indent=2, sort_keys=True))
    return 0


def cmd_assert_droppable(opts):
    """Read-only ownership probe (under flock). Exit non-zero + print the owning
    run (when known) when a FRESH (non-stale) lease on --db-name is either (a)
    owned by a DIFFERENT non-empty run than --run-id, or (b) UNOWNED (no run_id
    recorded at all) - P5.8: an unowned lease is no longer assumed safe to drop,
    since that is exactly the gap that let one session bare-drop another
    session's live instance. Pass --force to reap either case. A stale lease,
    or one owned by the calling run itself, remains droppable with no --force.
    Bounded TOCTOU: this and the actual drop are two processes, so a lease
    minted in between is not covered - acceptable because MANAGED DBs are
    dropped through the race-free `release` path, never via bare name."""
    db = opts.get("db_name")
    if not db:
        sys.stderr.write(
            "Usage: allocator.py assert-droppable --db-name <db> [--run-id <id>] [--force]\n"
        )
        return 2
    caller_run = opts.get("run_id") or opts.get("session", "")
    force = opts.get("force")
    with _locked():
        reg = _read_registry()
        for lease in reg["leases"]:
            if lease.get("db_name") != db:
                continue
            if _is_stale(lease):
                continue
            owner = lease.get("owner", {})
            owner_run = owner.get("run_id") or owner.get("session_id", "")
            if owner_run:
                if owner_run == caller_run:
                    continue  # own lease: droppable, no --force needed.
                if not force:
                    sys.stderr.write(
                        f"allocator: database {db!r} is held by a FRESH lease owned by "
                        f"run {owner_run!r}; route the drop through `release <token>` "
                        "instead of a bare-name drop (or pass --force to reap it).\n"
                    )
                    _emit("ALLOC_OWNER_RUN", owner_run)
                    return 1
                sys.stderr.write(
                    f"allocator: --force reaping a lease owned by a different run "
                    f"{owner_run!r} (caller run {caller_run!r}).\n"
                )
                continue
            # Unowned (no run_id recorded at all): no longer a synonym for
            # "safe to drop" (P5.8) - refuse unless --force.
            if not force:
                sys.stderr.write(
                    f"allocator: database {db!r} is held by a FRESH lease with NO "
                    "recorded owner; an unowned lease is no longer assumed safe to "
                    "drop - pass --force to reap it, or thread --run-id at acquire "
                    "time so ownership is tracked.\n"
                )
                _emit("ALLOC_OWNER_RUN", "")
                return 1
            sys.stderr.write(
                f"allocator: --force reaping an unowned fresh lease on {db!r}.\n"
            )
    return 0


# --------------------------------------------------------------------------- #
# Arg parsing (tiny; stdlib only, matches instances_io.py minimalism)
# --------------------------------------------------------------------------- #
_FLAG_KEYS = {
    "--series": "series", "--mode": "mode", "--ports": "ports", "--port": "port",
    "--ttl": "ttl", "--run-id": "run_id", "--session": "session", "--db-name": "db_name",
    "--instances": "instances", "--pid": "pid", "--profile": "profile",
    "--addons-path-override": "addons_path_override", "--min-age-s": "min_age_s",
}
_BOOL_KEYS = {
    "--no-create": "no_create", "--force": "force", "--show-tokens": "show_tokens",
    "--yes": "yes",
}
# Every spelling `main()` recognises as "show usage, do nothing else" - the ONLY
# two conventional Unix forms. This is the SSOT the regression test derives its
# spelling list from (`from allocator import _HELP_TOKENS`), so a future third
# spelling (there is none today) gets covered by construction rather than by a
# second hand-typed list silently drifting from this one.
_HELP_TOKENS = ("-h", "--help")


def _parse(argv):
    """Split argv into (opts, positionals, unknown_flags).

    An unrecognised `--flag` is COLLECTED, never dropped into `pos`: the old
    behavior made a typo'd flag exit 0 having silently ignored it, which is the
    exact silent-swallow class this tool must not have.
    """
    opts, pos, unknown = {}, [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _BOOL_KEYS:
            opts[_BOOL_KEYS[a]] = True
            i += 1
        elif a in _FLAG_KEYS:
            opts[_FLAG_KEYS[a]] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif a.startswith("--"):
            unknown.append(a)
            i += 1
        else:
            pos.append(a)
            i += 1
    return opts, pos, unknown


def main(argv):
    if not argv or argv[0] in _HELP_TOKENS:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    # Full help-spelling class, not just one reported shape: a help request
    # ANYWHERE in a subcommand's own argv - `acquire --help`, `acquire -h`,
    # `release -h`, etc. - must short-circuit to usage text BEFORE `_parse()`
    # ever runs on `rest`, for every subcommand alike. Checking this here,
    # ahead of `_parse`, is what closes the single-dash sibling: `_parse`
    # itself routes any token not starting with "--" into `pos` (a positional),
    # never "unknown" - so `-h` previously reached `cmd_acquire` as a silently
    # swallowed positional and allocated a real lease before this fix existed.
    # Never allocates, never mutates the registry, exits 0 (showing usage is
    # success, not an error - consistent with the no-subcommand-at-all case
    # immediately above).
    if any(tok in _HELP_TOKENS for tok in rest):
        print(__doc__)
        return 0
    opts, pos, unknown = _parse(rest)
    if unknown:
        sys.stderr.write(
            f"allocator: unknown flag(s) {' '.join(unknown)}. "
            "Known flags: " + " ".join(sorted(set(_FLAG_KEYS) | set(_BOOL_KEYS))) + "\n"
        )
        return 2
    if cmd == "acquire":
        return cmd_acquire(opts)
    if cmd == "release":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_release(opts)
    if cmd == "heartbeat":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_heartbeat(opts)
    if cmd == "bind":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_bind(opts)
    if cmd == "gc":
        return cmd_gc(opts)
    if cmd == "reap-orphans":
        return cmd_reap_orphans(opts)
    if cmd == "list":
        return cmd_list(opts)
    if cmd == "query":
        return cmd_query(opts)
    if cmd == "assert-droppable":
        return cmd_assert_droppable(opts)
    sys.stderr.write(
        f"Unknown subcommand: {cmd!r}. "
        "Use acquire|release|bind|heartbeat|gc|reap-orphans|list|query|assert-droppable.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
