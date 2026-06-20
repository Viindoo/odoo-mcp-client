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
    ephemeral  - unique throwaway DB (<prefix>_t_<uuid8>), created + dropped;
                 ports only when --ports N>0. Default for tests / -i verification.
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
                 [--ports N] [--port P] [--ttl <s>] [--session <id>] [--db-name <name>]
                 [--pid <pid>] [--no-create] [--instances <path>]
    allocator.py query --series <X.Y>     # the live shared render server for a series, if any
    allocator.py release <token> [--instances <path>]
    allocator.py heartbeat <token>
    allocator.py gc [--instances <path>]
    allocator.py list

All commands emit shell-eval-able KEY=VALUE lines (shlex.quote'd), mirroring
instances_io.py's INST_* convention. acquire prints ALLOC_*.
"""

import contextlib
import fcntl
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances_io  # noqa: E402  (sibling lib; resolves via the path insert above)

DEFAULT_POOL_SIZE = 10
DEFAULT_TTL_S = 7200  # 2h; long runs call `heartbeat` to extend


# --------------------------------------------------------------------------- #
# Paths (mirror resolve_instances.sh precedence)
# --------------------------------------------------------------------------- #
def _home():
    return os.environ.get("ODOO_AI_HOME") or os.path.join(
        os.path.expanduser("~"), ".odoo-ai"
    )


def _runtime_dir():
    d = os.path.join(_home(), "runtime")
    os.makedirs(d, exist_ok=True)
    return d


def _registry_path():
    return os.path.join(_runtime_dir(), "leases.json")


def _lock_path():
    return os.path.join(_runtime_dir(), "registry.lock")


def resolve_instances_path(explicit=None):
    """instances.toml location: --instances > $ODOO_AI_INSTANCES > global > project."""
    if explicit:
        return explicit
    env = os.environ.get("ODOO_AI_INSTANCES")
    if env:
        return env
    global_path = os.path.join(_home(), "instances.toml")
    if os.path.isfile(global_path):
        return global_path
    return os.path.join(os.getcwd(), ".odoo-ai", "instances.toml")


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


def _pick_ports(reg, base, size, n):
    """Pick n free ports from [base, base+size): not in the registry AND bindable."""
    if n <= 0:
        return []
    used = _ports_in_use(reg)
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
        f"found {len(chosen)} (in-use or bound)."
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


def _probe_createdb(host, user):
    """True iff the connecting role has CREATEDB. False on any error (-> degrade)."""
    rc, out, _ = _run(
        ["psql", "-h", host, "-U", user, "-d", "postgres", "-tAc",
         "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"],
        env=_pg_env(),
    )
    return rc == 0 and out.strip() == "t"


# _createdb removed: the allocator no longer creates the ephemeral DB.
# The caller's `odoo-bin -d <db> -i <modules> --stop-after-init` performs
# create-on-init instead (B2 model: caller-side create, through-Odoo drop).
# _probe_createdb is still needed: Odoo create-on-init also requires CREATEDB,
# so if the role lacks it we degrade ephemeral -> exclusive (same invariant).


def _dropdb(host, user, db):
    """Terminate backends then drop, with retry (portable to PG10+)."""
    env = _pg_env()
    for _ in range(3):
        _run(
            ["psql", "-h", host, "-U", user, "-d", "postgres", "-tAc",
             "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
             f"WHERE datname = '{db}' AND pid <> pg_backend_pid()"],
            env=env,
        )
        rc, _, err = _run(["dropdb", "-h", host, "-U", user, "--if-exists", db], env=env)
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
    venv_python = lease.get("python", "")

    if venv_python and os.path.isfile(_ODOO_DB_PY):
        cmd = [venv_python, _ODOO_DB_PY, "drop", db, "--db-host", host, "--db-user", user]
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
            _dropdb(host, user, db)
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
    _dropdb(host, user, db)
    _drop_filestore(db)
    return True


# --------------------------------------------------------------------------- #
# GC
# --------------------------------------------------------------------------- #
def _is_stale(lease):
    owner = lease.get("owner", {})
    if owner.get("host") == _host():
        pid = owner.get("pid")
        if pid is not None and not _pid_alive(int(pid)):
            return True
    ttl = lease.get("ttl_s", DEFAULT_TTL_S)
    if _now() - lease.get("heartbeat_at", lease.get("owner", {}).get("started_at", 0)) > ttl:
        return True
    return False


def _gc(reg):
    """Reclaim stale leases (drop their ephemeral DB via through-Odoo path). Mutates reg."""
    kept, reclaimed = [], []
    for lease in reg["leases"]:
        if _is_stale(lease):
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
def _resolve_instance(path, series):
    items = instances_io.load_instances(path)
    inst, _ = instances_io.select_instance(items, series or None)
    return inst


def _emit_instance_common(inst):
    _emit("ALLOC_PYTHON", inst.get("python", ""))
    _emit("ALLOC_ADDONS_PATH", ":".join(str(x) for x in inst.get("addons_path", [])))
    _emit("ALLOC_DB_HOST", inst.get("db_host", "localhost"))
    _emit("ALLOC_DB_USER", inst.get("db_user", "odoo"))
    _emit("ALLOC_SERIES", instances_io.series_of(inst))


def cmd_acquire(opts):
    path = resolve_instances_path(opts.get("instances"))
    series = opts.get("series", "")
    inst = _resolve_instance(path, series)
    if inst is None:
        sys.stderr.write(
            f"allocator: no instance for series {series!r} in {path}. "
            "Declare one via /odoo-setup or pass --instances.\n"
        )
        return 1

    mode = opts.get("mode", "ephemeral")
    host = inst.get("db_host", "localhost")
    user = inst.get("db_user", "odoo")

    # readonly: lease-free; just surface the running instance's coordinates.
    if mode == "readonly":
        _emit("ALLOC_TOKEN", "")
        _emit("ALLOC_MODE", "readonly")
        _emit("ALLOC_DB_NAME", inst.get("db_name", "odoo"))
        _emit("ALLOC_PORTS", [inst.get("http_port", 8069)])
        _emit_instance_common(inst)
        return 0

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
                    existing.setdefault("owner", {})["pid"] = int(opts["pid"])
                if ports:
                    existing["ports"] = ports
                else:
                    ports = existing.get("ports", [])
                existing["heartbeat_at"] = now
            else:
                token = uuid.uuid4().hex
                reg["leases"].append({
                    "token": token,
                    "mode": "shared",
                    "series": series_c,
                    "db_name": db_name,
                    # drop_on_release is ALWAYS False for shared leases:
                    # the declared DB must never be dropped by gc/release.
                    "drop_on_release": False,
                    "ports": ports,
                    "owner": {
                        "host": _host(),
                        "pid": int(opts["pid"]) if opts.get("pid") else None,
                        "session_id": opts.get("session", ""),
                        "started_at": now,
                    },
                    "ttl_s": int(opts.get("ttl", DEFAULT_TTL_S)),
                    "heartbeat_at": now,
                    "_pg": {"host": host, "user": user},
                })
            _write_registry(reg)
        _emit("ALLOC_TOKEN", token)
        _emit("ALLOC_MODE", "shared")
        _emit("ALLOC_DB_NAME", db_name)
        _emit("ALLOC_PORTS", ports)
        _emit("ALLOC_ATTACHED", attached)
        _emit_instance_common(inst)
        return 0

    if mode not in ("ephemeral", "exclusive"):
        sys.stderr.write(f"allocator: unknown --mode {mode!r}\n")
        return 2

    n_ports = int(opts.get("ports", 0))
    base = int(inst.get("http_port_base", inst.get("http_port", 8069)))
    size = int(inst.get("port_pool_size", DEFAULT_POOL_SIZE))
    prefix = inst.get("db_name_prefix", inst.get("db_name", "odoo"))

    # B2 model: the allocator NO LONGER calls createdb.  The ephemeral DB is
    # created by the caller's `odoo-bin -d <db> -i <mods> --stop-after-init`
    # (Odoo create-on-init).  We still probe CREATEDB because Odoo create-on-init
    # also requires the role to have that privilege; if it is absent, degrading to
    # the declared exclusive DB (which already exists) is still the right move.
    if mode == "ephemeral":
        if not opts.get("no_create") and not _probe_createdb(host, user):
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
            ports = _pick_ports(reg, base, size, n_ports)
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
            "addons_path": ":".join(str(x) for x in inst.get("addons_path", [])),
            "db_host": host,
            "db_user": user,
            "ports": ports,
            "owner": {
                "host": _host(),
                # pid is a FAST-PATH reclaim signal only - recorded solely when the
                # caller passes a stable, long-lived --pid. We never default to the
                # transient bash pid (it dies right after this call returns, which
                # would let the next gc reclaim a lease whose DB is still in use).
                # With no --pid, reclamation falls back to ttl_s + heartbeat.
                "pid": int(opts["pid"]) if opts.get("pid") else None,
                "session_id": opts.get("session", ""),
                "started_at": now,
            },
            "ttl_s": ttl,
            "heartbeat_at": now,
            "_pg": {"host": host, "user": user},
        })
        _write_registry(reg)

    _emit("ALLOC_TOKEN", token)
    _emit("ALLOC_MODE", mode)
    _emit("ALLOC_DB_NAME", db_name)
    _emit("ALLOC_PORTS", ports)
    _emit_instance_common(inst)
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


def cmd_gc(opts):
    with _locked():
        reg = _read_registry()
        reclaimed = _gc(reg)
        _write_registry(reg)
    for lease in reclaimed:
        _emit("ALLOC_RECLAIMED", lease.get("token", ""))
    print(f"# reclaimed {len(reclaimed)} stale lease(s)")
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
    print(json.dumps(reg, indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- #
# Arg parsing (tiny; stdlib only, matches instances_io.py minimalism)
# --------------------------------------------------------------------------- #
_FLAG_KEYS = {
    "--series": "series", "--mode": "mode", "--ports": "ports", "--port": "port",
    "--ttl": "ttl", "--session": "session", "--db-name": "db_name",
    "--instances": "instances", "--pid": "pid",
}
_BOOL_KEYS = {"--no-create": "no_create"}


def _parse(argv):
    opts, pos = {}, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _BOOL_KEYS:
            opts[_BOOL_KEYS[a]] = True
            i += 1
        elif a in _FLAG_KEYS:
            opts[_FLAG_KEYS[a]] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            pos.append(a)
            i += 1
    return opts, pos


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    opts, pos = _parse(rest)
    if cmd == "acquire":
        return cmd_acquire(opts)
    if cmd == "release":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_release(opts)
    if cmd == "heartbeat":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_heartbeat(opts)
    if cmd == "gc":
        return cmd_gc(opts)
    if cmd == "list":
        return cmd_list(opts)
    if cmd == "query":
        return cmd_query(opts)
    sys.stderr.write(
        f"Unknown subcommand: {cmd!r}. Use acquire|release|heartbeat|gc|list|query.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
