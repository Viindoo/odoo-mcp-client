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
                 (create-on-init) and dropped through Odoo on release. A raw client
                 drop is the FALLBACK, and it is reached only on the three exits
                 that prove the Odoo route never touched the database (8 denied,
                 9 unreachable, 10 venv unavailable) and only when
                 `_client_drop_allowed` permits it. Ports only when --ports N>0.
                 Default for tests / -i verification.
                 REFUSES (exit 6 no CREATEDB / exit 7 undeterminable / exit 8
                 authentication denied / exit 9 cluster unreachable) instead of
                 degrading: an ephemeral request either gets an isolated
                 throwaway DB or fails, never an `exclusive` lease on the
                 declared database the caller did not ask for.
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
    allocator.py query --series <X.Y> [--state parked] [--run-id <id>] [--force-attach]
                 # DEFAULT (no --state): the live shared render server for a
                 # series, if any - unchanged, so no existing caller moves.
                 # --state parked: the resumable PARKED lease for that series
                 # (ALLOC_TOKEN/ALLOC_MODE/ALLOC_DB_NAME/ALLOC_PORTS/
                 # ALLOC_PARKED_AT), so a returning agent finds the instance it
                 # (or an earlier run on this host) suspended instead of building
                 # a new one. A parked lease has NO live owner by construction, so
                 # it is HOST-and-SERIES scoped, not run-scoped: this run's own
                 # parked lease is returned silently; another run's parked lease
                 # on THIS host is returned WITH ALLOC_ATTACHED_FROM_RUN so the
                 # attach is reported rather than gated; a parked lease on a
                 # DIFFERENT host needs --force-attach (its database may live on
                 # another cluster entirely). A same-host row whose database is
                 # PROVABLY gone is SKIPPED, not offered, and `release <token>` is
                 # named - this is the PRE-LAUNCH probe, and the only one that can
                 # be pre-launch (resume needs a live pid, so it necessarily runs
                 # after the launch). "Could not look" is not "absent" and is
                 # still offered.
    allocator.py can-createdb --series <X.Y> [--profile <P>] [--instances <path>]
                 # read-only: print CREATEDB=true|false|undeterminable (+ CREATEDB_WHY
                 # when undeterminable) and exit 0|6|7 - the SAME ladder and the SAME
                 # codes `acquire --mode ephemeral` gates on, so a reporting caller
                 # never re-implements the question. Exits 8/9 when the connection
                 # Odoo itself opens is provably refused / the cluster is absent:
                 # the capability was then never answered, and no client surface may
                 # overrule a fact about that connection. Writes NO lease.
    allocator.py db-preflight --series <X.Y> [--profile <P>] [--instances <path>]
                 # read-only: print DB_AUTH=ok|denied|unreachable|unknown +
                 # DB_AUTH_WHY, then CREATEDB + CREATEDB_WHY, and exit 0|6|7|8|9.
                 # DB_AUTH is evaluated FIRST: a capability answer describes a role,
                 # while DB_AUTH describes the connection every build opens, so
                 # CREATEDB=true is never emitted beside a proven refusal. This is
                 # the ONE question every reporting caller asks (05-prereq-check.sh,
                 # 45-venv.sh) instead of re-deriving half of it. Writes NO lease.
    allocator.py release <token> --run-id <id> [--force] [--force-forget]
                 [--instances <path>]
                 # a lease that records an owner run is released ONLY by that run:
                 # any other --run-id, AND an absent one, is refused (an absent
                 # caller run is not ownership unproven-but-assumed, it is
                 # ownership not established - same shape as assert-droppable).
                 # An UNOWNED lease (no owner run recorded) still releases on
                 # token-possession; --force overrides loudly.
                 # A drop that FAILS keeps the lease (so gc / a later retry can
                 # finish it) - and the drop surface is re-resolved from the
                 # CURRENT catalog on every attempt, so `45-venv.sh record-env`
                 # repairs an EXISTING lease, not just future ones.
                 # A drop that did not happen is CLASSIFIED before anything is
                 # named: a database PROVABLY absent releases the lease cleanly
                 # (ALLOC_FORGOTTEN_DB, exit 0 - the drop had nothing to do in
                 # Postgres, and its FILESTORE is removed on that path because
                 # neither reaper could find it once the lease is gone), one
                 # observed PRESENT keeps it, and one whose existence cannot be
                 # determined keeps it too.
                 # --force-forget is the documented escape when nothing on this
                 # host can ever drop the DB: it removes the lease and NAMES what
                 # was left behind - ALLOC_ABANDONED_DB when the database was
                 # observed present, ALLOC_FORGOTTEN_DB when it provably does not
                 # exist, ALLOC_UNVERIFIED_DB when that could not be confirmed. It
                 # never reports a teardown that did not happen, and never claims a
                 # cluster fact it did not observe.
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
    allocator.py park <token> [--park-ttl <s>]
                 # SUSPEND a RUNNING lease without destroying anything it holds.
                 # Stops the owner's process GROUP first (park holds DISK, never
                 # MEMORY), clears owner.pid/owner.pid_started, and stamps
                 # parked_at + park_ttl_s + parked_boot_id. db_name, ports and
                 # drop_on_release are left untouched, so the database, the
                 # filestore and the port reservation all survive and the lease
                 # can be resumed. EMITS that untouched drop_on_release
                 # (ALLOC_DROP_ON_RELEASE) and, when it is true, says on STDERR
                 # that the final `release` still drops that database: park
                 # DEFERS a throwaway, it never makes one durable, and the silent
                 # version of that gap is how a caller parks to SAVE a database
                 # and loses it later anyway. Refuses a `shared` lease (exit 3 - the shared
                 # row is already immune to the pid arms and is the ONE answer
                 # `query --series` gives for a series; a parked twin would make
                 # that rung two-valued) and a lease that is not RUNNING (exit 4 -
                 # no owner pid recorded: nothing to stop, nothing to resume).
    allocator.py resume <token> --pid <server_pid>
                 # The atomic PARKED -> RUNNING compare-and-set, under ONE
                 # registry hold: the lease must BE parked - NOT parked with no
                 # live same-host owner is the ordinary first launch (exit 3, the
                 # branch back to `bind`), while NOT parked because a LIVE
                 # same-host server already holds it is the resume RACE the first
                 # caller won (exit 6, never a bind: stop the server you just
                 # launched) - its database must not have been dropped underneath
                 # it (exit 5, naming `release` as the next step), and the named
                 # pid must be alive on this host AND corroborated as this
                 # lease's own server by _ownership_proof (exit 4). Only then does it
                 # DELETE parked_at/park_ttl_s/parked_boot_id and write
                 # owner.pid/owner.pid_started + a fresh heartbeat. Deleting the
                 # park keys is what puts the resumed lease back under the pid
                 # arms (and back under the SubagentStop teardown gate) instead
                 # of leaving it governed by a park budget forever.
    allocator.py heartbeat <token>
                 # refresh the lease's heartbeat, and BACKFILL owner.pid_started
                 # on an older row when - and only when - ownership of its pid is
                 # corroborated right then (_backfill_pid_fingerprint).
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

Every process signal release/gc/acquire/park can send goes through ONE gate
(`_stop_owner_group_if_local`): the pid must be on THIS host, alive, AND PROVEN
to belong to the lease - by a matching `owner.pid_started` fingerprint, or by an
independent corroborating observation (an Odoo command line naming this lease's
own database, or the process group listening on a port this lease reserved). An
unproven pid is NEVER signalled and the refusal is reported with its evidence:
pids are recycled, so "alive" alone is equally true of an unrelated shell whose
whole group a GROUP signal would take down. Refusing to signal never blocks
reclamation - the lease row and its database are reclaimed exactly as before, so
the worst case is a REPORTED process leak, never a lost lease.

All commands emit shell-eval-able KEY=VALUE lines (shlex.quote'd), mirroring
instances_io.py's INST_* convention. acquire prints ALLOC_*.

RECLAMATION IS ALWAYS ON THE RECORD. `acquire` runs the same destructive sweep
`gc` does (`_gc`: stop the owner's process group, drop the database, delete the
row), so every command that reclaims a lease reports each one - which lease,
whose run, which database, which owner pid, and WHICH ARM condemned it (see
CONDEMN_REASONS) - on STDERR, plus an append-only JSONL record under
`$ODOO_AI_HOME/logs/` (RECLAIM_LOG_BASENAME) that outlives the process. Never on
stdout: that stream is a protocol for `eval $(allocator.py acquire ...)`. Read
the GC section header for why the silent version of this was worse than the data
loss it caused.

acquire exit codes:
    0 acquired as requested (a lease is written)
    1 no instance for that series in the catalog
    2 usage / unknown --mode
    3 exclusive conflict - the db is already exclusively held
    4 port pool exhausted
    5 addons_path worktree mismatch (pass --addons-path-override)
    6 `ephemeral` REFUSED: the role positively LACKS CREATEDB
    7 `ephemeral` REFUSED: CREATEDB capability UNDETERMINABLE
    8 REFUSED: Odoo cannot AUTHENTICATE to the cluster (`ephemeral`+`exclusive`)
    9 REFUSED: the cluster did not answer at all (`ephemeral`+`exclusive`)
Every non-zero exit writes NO lease.
`--mode` accepts ONLY the four values in "Modes" above. `exclusive-running` is a
`persist:` value - the skill/agent lifecycle vocabulary, NOT a fifth mode - and
it maps onto `--mode ephemeral` (docs/reference/INSTANCE-ALLOCATION-MODES.md
section 5), so `--mode exclusive-running` exits 2 and writes nothing. The
consequence is not cosmetic and must not be read as a downgrade: an `ephemeral`
lease carries `drop_on_release: True`, so `release` (and `gc`) DROP its database
by contract. `50-instance-spinup.sh --exclusive` is a SPIN-UP flag naming which
instance to launch; it never sets, changes or upgrades the lease's mode or its
`drop_on_release`. A database that must OUTLIVE its lease has to be acquired
that way in the first place (`--mode exclusive` / `shared`, both
`drop_on_release: False`) - no later command converts a throwaway into a durable
one.
6 and 7 stay distinct because the remedy
differs: 6 is fixed by granting the role CREATEDB, 7 by declaring a working
`python` + `odoo_root` (45-venv.sh record-env), by declaring a `db_run_mode`
client surface (the route a compose-run instance takes - it declares no
`python` of its own), or by starting the cluster.
8 and 9 are checked BEFORE 6/7 and for every mode that will build: Odoo's CLI
opens the maintenance-database connection for every `-d <name>` run before any
module loads, so a cluster that refuses Odoo kills the build whatever the role's
privileges are. 8 is fixed by `/odoo-ai-agents:odoo-setup` (or by exporting
ODOO_PG_PASSWORD for a cluster that cannot be reconfigured), 9 by starting the
cluster. Both are skipped for `--no-create`, `readonly` and `shared`, and an
UNDETERMINABLE authentication state never blocks - only a PROVEN 8 or 9 does.

Every call that talks to Postgres is BOUNDED (see `_probe_timeout_s`): psycopg2
opens the connection with no libpq connect timeout, so an unreachable cluster
never replies at all, and an unbounded probe would make `acquire` hang with no
lease, no refusal and no verdict - strictly worse than a wrong answer, because
the caller learns nothing. A bound that elapses is UNDETERMINED, never a "no".
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
DEFAULT_TTL_S = 7200
# reap-orphans default minimum PROVABLE age (seconds) before a lease-free
# ephemeral-shaped DB is even proposed as a candidate. Conservative on purpose:
# a DB that appeared moments ago (a narrow acquire-then-crash race, or a lease
# write still in flight) must never be mistaken for an abandoned orphan just
# because a reap-orphans sweep happened to run at the wrong instant.
DEFAULT_REAP_MIN_AGE_S = 24 * DEFAULT_TTL_S
# How long a PARKED lease keeps its database, filestore and ports with no owner
# process at all. This is a DISK budget, not a RAM one, and that is why it is an
# order of magnitude looser than DEFAULT_TTL_S: `park` stops the owner's process
# group BEFORE it clears the pid, so a parked lease costs no memory - only the
# database and the port reservation. It is deliberately the same 24h figure as
# DEFAULT_REAP_MIN_AGE_S above, the file's other disk-scoped budget, so the two
# "how long may abandoned disk survive" answers do not drift apart. Overridable
# per lease with `park --park-ttl <s>`.
DEFAULT_PARK_TTL_S = 24 * DEFAULT_TTL_S
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


_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"


def _boot_id():
    """This boot's kernel-issued identity, or None when it cannot be read.

    Same idea as the `pid_started` fingerprint one rung down: a value that is
    fixed for the whole life of a boot, so comparing it later answers "is this
    still the same machine-uptime the fact was recorded under?". `park` stamps
    it so `_condemn_reason` can tell a park budget that genuinely elapsed apart
    from one whose wall-clock elapsed only because the host was OFF - nobody
    consumed a park across a reboot, and a perfectly resumable database must not
    be dropped because the machine restarted.

    None is "could not look", NEVER a value: the file is Linux-only, so on
    macOS/BSD there is nothing to read, and inside a container this file may
    report the HOST's boot id and therefore NOT change when the container
    restarts. Both cases degrade the same way and on purpose - the caller
    compares only when BOTH sides have a value, so an unreadable (or
    container-shared) boot id leaves the plain TTL comparison in charge instead
    of manufacturing either a condemn or a permanent reprieve.
    """
    try:
        with open(_BOOT_ID_PATH, "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


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


# --------------------------------------------------------------------------- #
# Ownership corroboration - PROVING a recorded pid is this lease's server
#
# The signal path (`_stop_owner_group_if_local` -> `_stop_group`) SIGTERMs a
# whole process GROUP. A lease's `owner.pid` is only an integer, and the OS
# hands the same integers out again: by the time `gc` or `release` reads one,
# the process that recorded it may be long gone and something entirely
# unrelated - a shell, a test runner, an editor - may hold that number. Signal
# it then and nothing gets "cleaned up": a bystander is killed, and because the
# signal goes to the GROUP it takes that bystander's whole session with it.
#
# `owner.pid_started` (see `_pid_owner_fields`) settles the question whenever it
# is present AND re-measurable. Two populations are left over:
#   (a) rows written before that field existed - `leases.json` is at
#       schema_version 2 and readers stay deliberately lenient, so a row
#       carrying `pid` and no `pid_started` is a legal, expected shape, not a
#       corrupt one;
#   (b) rows whose fingerprint cannot be re-measured this second (a `ps` that is
#       missing, slow, or refused).
# Neither may be signalled on the strength of "the pid is alive": that is the
# one fact which is equally true of every bystander. Both used to reach an
# unverified `_stop_group` - population (a) because the guard was written as
# opt-in (`if expected_fp is not None`), population (b) because an unmeasurable
# fingerprint was explicitly allowed to proceed "best effort".
#
# Refusing outright would only trade a rare wrong kill for a guaranteed leak: a
# genuinely runaway Odoo server recorded on an old row would then never be
# reclaimed, and reclaiming exactly that is why this allocator exists. So the
# question is turned around and asked about the OBSERVED PROCESS instead of the
# number: a recycled bystander is merely alive, whereas the leased server still
# carries the lease's own coordinates. Two such coordinates are observable here
# with no new dependency and no second registry:
#   - CMDLINE: the process runs an Odoo launcher AND names THIS lease's
#     database. `50-instance-spinup.sh` launches
#     `setsid <py> <...>/odoo-bin -c <conf> -d <db_name>`, and its conf file is
#     itself keyed `<db_name>-<http_port>.conf`, so the database name appears on
#     the command line twice over. (The lease records no conf PATH of its own -
#     hence the conf is corroborated through the same db-name token test, not
#     through a field that does not exist.)
#   - PORT: the process, or the process group it leads, is LISTENING on a port
#     THIS lease reserved. `_port_bindable` can only say a port is taken;
#     attributing it to a pid needs `/proc` (or lsof/ss/fuser off-Linux).
# Either one is something a recycled bystander cannot accidentally satisfy,
# because both are keyed to values only this lease knows.
#
# BOTH rungs read `/proc` FIRST and fall back to an external binary, and that
# order is load-bearing rather than a preference - each fallback was observed
# failing where `/proc` cannot:
#   - `ps -o args=` prints `args` as a DISPLAY COLUMN and procps TRUNCATES it to
#     the screen width - 80 characters in any environment where it cannot
#     determine one, which includes a CI runner and a plain container. The tokens
#     that corroborate a lease (`odoo-bin`, `-d <db>`, the conf basename) sit at
#     the END of a long command line, so they were the exact bytes cut off: the
#     rung reported "not proven" for a genuine runaway server and the allocator
#     refused to reclaim it. `-ww` (unlimited width) is now MANDATORY on that
#     fallback, and `/proc/<pid>/cmdline` - the kernel's own NUL-separated copy,
#     never formatted, never truncated, and split on NUL so a path containing a
#     space cannot fake a token boundary - is preferred over it outright.
#   - lsof/ss/fuser are absent in a minimal container (observed: all three), so
#     an external-tool-only port rung means a containerised runtime can NEVER
#     prove ownership and therefore NEVER reclaims a runaway. `/proc/net/tcp{,6}`
#     plus `/proc/<pid>/fd` answer the same question with no binary at all.
# `/proc` is Linux-only, which is why the binaries remain as the macOS/BSD path;
# on Linux they are now only reached if `/proc` itself is unreadable.
# --------------------------------------------------------------------------- #

# argv[0]-style basenames Odoo has ever been launched under across the supported
# series (`odoo.py`/`openerp-server` on the oldest, `odoo-bin` from 10.0, and the
# `odoo` console script a pip install provides). Matched on the BASENAME of a
# non-flag token so `/x/y/odoo-bin` counts and `--addons-path=/opt/odoo` does not.
_ODOO_LAUNCHER_BASENAMES = ("odoo-bin", "odoo.py", "openerp-server", "odoo")
# Flags whose VALUE is a database name (Odoo's own `-d`/`--database`, plus the
# spelling this plugin's own tooling uses). A bare token that merely equals the
# db name is NOT accepted: the value has to be attached to a database flag, or a
# lease on a database called `odoo` would be corroborated by any command line
# that happens to mention a directory of that name.
_DB_NAME_FLAGS = ("-d", "--database", "--db-name", "--db_name")


def _proc_argv(pid):
    """The EXACT argument vector of `pid` from `/proc/<pid>/cmdline`, or None
    when `/proc` cannot answer (not Linux, pid gone, permission).

    The kernel stores argv NUL-separated, so this is the real vector: no display
    width, no truncation, and no whitespace guessing - a path containing a space
    stays ONE token instead of splitting into two that could fake a `-d <db>`
    pair. An EMPTY read is also None: a kernel thread or a zombie has no argv,
    which is "nothing to read", not "an argv that names nothing"."""
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as fh:
            raw = fh.read()
    except (OSError, ValueError, TypeError):
        return None
    tokens = [tok.decode("utf-8", "replace") for tok in raw.split(b"\0") if tok]
    return tokens or None


def _ps_argv(pid):
    """`pid`'s argv via `ps`, for hosts with no `/proc` (macOS/BSD). None when
    `ps` cannot answer (missing, refused, timed out, pid gone).

    `-ww` is REQUIRED, not tidiness: `args` is a display column and procps
    truncates it to the screen width - 80 characters wherever it cannot
    determine one (a CI runner, a container) - which silently cut the
    corroborating tokens off the end of a long command line and made a real
    runaway server look unprovable. Splitting on whitespace is APPROXIMATE (a
    path containing a space over-splits); that is acceptable only because this is
    the fallback and both halves of `_argv_names_lease` must still match."""
    rc, out, _ = _run(["ps", "-ww", "-o", "args=", "-p", str(pid)], timeout=_probe_timeout_s())
    if rc != 0:
        return None
    return out.split() or None


def _pid_argv(pid):
    """(argv, source) for the process CURRENTLY at `pid` - `/proc` first, `ps`
    second - or (None, None) when neither could read it. None means "could not
    look", never "nothing there": callers MUST NOT read it as evidence either
    way."""
    argv = _proc_argv(pid)
    if argv:
        return argv, "/proc/<pid>/cmdline"
    argv = _ps_argv(pid)
    if argv:
        return argv, "ps -ww -o args="
    return None, None


def _argv_names_lease(argv, db_name):
    """True when `argv` is an Odoo server invocation FOR `db_name` - both halves
    required, because either alone is weak evidence: plenty of processes mention a
    database name (`psql -d <db>`, a backup script), and plenty of Odoo
    invocations serve a different database.

    The database is accepted as: the value of a database flag (`-d <db>`,
    `--database=<db>`), or a `<db_name>-*.conf` basename - the conf file
    `50-instance-spinup.sh` generates per (database, port) and passes with `-c`.
    """
    if not argv or not db_name:
        return False
    tokens = list(argv)
    launcher = names_db = False
    for idx, tok in enumerate(tokens):
        if not tok.startswith("-") and os.path.basename(tok.rstrip("/")) in _ODOO_LAUNCHER_BASENAMES:
            launcher = True
        if tok == db_name and idx and tokens[idx - 1] in _DB_NAME_FLAGS:
            names_db = True
        elif "=" in tok and tok.split("=", 1)[0] in _DB_NAME_FLAGS \
                and tok.split("=", 1)[1] == db_name:
            names_db = True
        else:
            base = os.path.basename(tok.rstrip("/"))
            if base.startswith(f"{db_name}-") and base.endswith(".conf"):
                names_db = True
    return launcher and names_db


def _pids_from_plain(text):
    """Pids out of a pid-only listing (`lsof -t`, `fuser`)."""
    return {int(tok) for tok in text.split() if tok.isdigit()}


def _pids_from_ss(text):
    """Pids out of `ss -p` output: ONLY the `pid=<n>` fields of
    `users:(("odoo-bin",pid=41234,fd=7))`. Deliberately not a scan for any
    integer - ss also prints Recv-Q/Send-Q columns, and reading those as pids
    would let a small unrelated number corroborate a lease on a kill path."""
    pids = set()
    for raw in text.replace("(", " ").replace(")", " ").replace(",", " ").split():
        if raw.startswith("pid=") and raw[4:].isdigit():
            pids.add(int(raw[4:]))
    return pids


def _port_listener_pids(port):
    """The pids LISTENING on TCP `port` on this host: a set (EMPTY when a tool
    answered and nobody is listening), or None when no tool on this host could
    answer at all.

    The three-way return matters on a kill path: an empty set is the observation
    "the port this lease reserved is NOT held by anyone", while None is "this
    host cannot tell me" - and only a POSITIVE pid may ever corroborate
    ownership. Ladder order is portability-first: `lsof` exists on
    Linux/macOS/BSD, `ss` is Linux (iproute2), `fuser` is the last resort;
    whichever is installed first and names a holder wins. Every call is bounded
    (`lsof` in particular can block on a wedged mount), and a timeout or a
    missing binary is "could not look", not "nobody".
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    answered = False
    for binary, argv, parse in (
        ("lsof", ["lsof", "-t", "-i", f"TCP:{port}", "-sTCP:LISTEN"], _pids_from_plain),
        ("ss", ["ss", "-Hltnp", f"sport = :{port}"], _pids_from_ss),
        ("fuser", ["fuser", "-n", "tcp", str(port)], _pids_from_plain),
    ):
        if not _which(binary):
            continue
        rc, out, _ = _run(argv, timeout=_probe_timeout_s())
        if rc in (127, EXIT_PROBE_TIMEOUT):
            continue
        answered = True
        pids = parse(out)
        if pids:
            return pids
    return set() if answered else None


def _pgid_of(pid):
    """The process-group id of `pid`, or None when it cannot be read."""
    try:
        return os.getpgid(int(pid))
    except (OSError, TypeError, ValueError):
        return None


# TCP state 0A == TCP_LISTEN in /proc/net/tcp's hex state column. Only a
# LISTENING socket corroborates a server; an outbound connection to the same
# port number proves nothing about who serves it.
_PROC_TCP_LISTEN = "0A"


def _proc_listening_inodes(port):
    """Socket INODES listening on TCP `port`, read from `/proc/net/tcp{,6}`: a
    set (EMPTY when /proc answered and nothing listens), or None when `/proc/net`
    is not readable at all (not Linux).

    Inodes rather than pids because `/proc/net/tcp` does not carry a pid - it
    carries the socket inode, which `/proc/<pid>/fd` then attributes to a
    process. That two-step is what makes the port rung work with NO external
    binary, which matters because a minimal container has none of lsof/ss/fuser
    and would otherwise be unable to prove ownership of anything, ever."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    inodes = set()
    answered = False
    for table in ("tcp", "tcp6"):
        try:
            with open(f"/proc/net/{table}", encoding="utf-8") as fh:
                rows = fh.read().splitlines()[1:]  # drop the header row
        except OSError:
            continue
        answered = True
        for row in rows:
            cols = row.split()
            if len(cols) < 10 or cols[3] != _PROC_TCP_LISTEN:
                continue
            local = cols[1].rsplit(":", 1)
            if len(local) != 2:
                continue
            try:
                if int(local[1], 16) != port:
                    continue
            except ValueError:
                continue
            inodes.add(cols[9])
    return inodes if answered else None


def _proc_group_member_pids(pid):
    """Every pid in the process group LED by `pid` (including `pid` itself), as
    far as `/proc` can enumerate. Only group members are ever inspected - never
    every process on the host - so this never reads an unrelated user's fds."""
    members = {pid}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        candidate = int(entry)
        if candidate != pid and _pgid_of(candidate) == pid:
            members.add(candidate)
    return members


def _proc_group_socket_holder(pid, inodes):
    """The pid in `pid`'s process group that holds one of `inodes` as an open
    socket, or None. Reads only `/proc/<member>/fd` symlinks (`socket:[<inode>]`);
    an unreadable fd dir is skipped, never guessed at."""
    for member in sorted(_proc_group_member_pids(pid)):
        fd_dir = f"/proc/{member}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target[len("socket:["):-1] in inodes:
                return member
    return None


def _port_holder_in_group(pid, port):
    """(holder_pid, how) - is `port` held by the process group led by `pid`?

    Tri-state, and the third state is the point on a kill path:
      (int, how)   - a group member is LISTENING on it: ownership corroborated.
      (None, how)  - measured, and the group does NOT hold it.
      (None, None) - could NOT be measured on this host: not corroboration, and
                     the refusal must say which rung went unevaluated.
    `/proc` first (always present on Linux, needs no binary), then the external
    tools for hosts without it."""
    inodes = _proc_listening_inodes(port)
    if inodes is not None:
        how = "/proc/net/tcp + /proc/<pid>/fd"
        if not inodes:
            return None, how
        holder = _proc_group_socket_holder(pid, inodes)
        return holder, how
    holders = _port_listener_pids(port)
    if holders is None:
        return None, None
    for holder in sorted(holders):
        if holder == pid or _pgid_of(holder) == pid:
            return holder, "lsof/ss/fuser"
    return None, "lsof/ss/fuser"


def _clip(text, limit=160):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "..."


def _ownership_proof(lease, pid):
    """(proof, detail) - whether `pid` is PROVABLY this lease's server process,
    and the human-readable evidence either way.

    `proof` is the name of the signal that proved it ("fingerprint", "cmdline"
    or "port") or None when nothing did. `detail` is always populated: it is
    what the caller prints, so that both a signal and a refusal say WHY.

    Order is cheapest-and-strongest first. A fingerprint MISMATCH is a proof of
    NON-ownership (the recorded owner exited - that is precisely how its pid
    became free to reuse), so it stops the ladder instead of falling through to
    corroboration: there is nothing of ours left at that pid to find.
    """
    owner = lease.get("owner", {}) or {}
    db_name = lease.get("db_name", "") or ""
    expected_fp = owner.get("pid_started")
    if expected_fp is not None:
        current_fp = _pid_fingerprint(pid)
        if current_fp is not None:
            if current_fp == expected_fp:
                return "fingerprint", (
                    "the process holding that pid still reports the start time recorded "
                    "on the lease (owner.pid_started), so it is the very process the "
                    "lease named"
                )
            return None, (
                "the process holding that pid reports a DIFFERENT start time than the "
                "lease recorded (owner.pid_started), which proves the pid was recycled "
                "onto an unrelated process - this lease's own server already exited"
            )
        unprovable = (
            "the lease's owner.pid_started fingerprint could not be re-measured just "
            "now (`ps` gave no answer), so the pid cannot be matched to the recorded "
            "process"
        )
    else:
        unprovable = (
            "the lease row carries no owner.pid_started fingerprint at all (it was "
            "written before that field existed), so 'the pid is alive' says nothing "
            "about WHOSE process holds it"
        )

    argv, argv_how = _pid_argv(pid)
    if _argv_names_lease(argv, db_name):
        return "cmdline", (
            f"the process holding that pid is an Odoo server invocation for this "
            f"lease's own database {db_name!r}, read via {argv_how} "
            f"[{_clip(' '.join(argv))}]"
        )
    if argv:
        cmdline_status = (
            f"its command line (read via {argv_how}) is not an Odoo server invocation for "
            f"database {db_name!r} [it is: {_clip(' '.join(argv))}]"
        )
    else:
        # NAME the unevaluated rung: "could not look" and "looked, no match" lead
        # to different fixes, and a refusal that blurs them tells an operator
        # nothing about whether this host can ever reclaim anything.
        cmdline_status = (
            "its command line could NOT be read at all (no /proc/<pid>/cmdline entry and "
            "`ps -ww` gave no answer), so the command-line rung went UNEVALUATED"
        )

    ports = list(lease.get("ports") or [])
    unmeasured_ports, measured_ports = [], []
    for port in ports:
        holder, how = _port_holder_in_group(pid, port)
        if holder is not None:
            return "port", (
                f"pid {holder} is LISTENING on port {port}, which this lease reserved, "
                f"and it belongs to the process group led by pid {pid} (observed via {how})"
            )
        (measured_ports if how else unmeasured_ports).append(port)

    if not ports:
        port_status = "this lease reserved no port, so there was no port rung to evaluate"
    elif measured_ports and not unmeasured_ports:
        port_status = (
            f"none of this lease's reserved ports {measured_ports} is held by that pid's "
            "process group"
        )
    elif unmeasured_ports and not measured_ports:
        port_status = (
            f"whether this lease's reserved ports {unmeasured_ports} are held could NOT be "
            "measured on this host (no readable /proc/net/tcp and no lsof/ss/fuser), so the "
            "port rung went UNEVALUATED"
        )
    else:
        port_status = (
            f"ports {measured_ports} are not held by that pid's process group, and ports "
            f"{unmeasured_ports} could NOT be measured on this host, so the port rung went "
            "PARTLY UNEVALUATED"
        )

    return None, f"{unprovable}; {cmdline_status}; and {port_status}"


def _backfill_pid_fingerprint(lease):
    """Stamp the missing `owner.pid_started` onto an OLD lease row - but ONLY
    when ownership has just been corroborated independently. Mutates `lease`
    in place and returns True when it did; the caller owns the registry write.

    Why gated on corroboration rather than done unconditionally: a naive
    backfill is the same bug wearing a helpful face. Fingerprinting whatever
    process happens to hold the pid would stamp a RECYCLED bystander's start
    time onto the lease, turning an honestly-unprovable row into a wrongly-
    PROVEN one - and every later check, including `_is_stale`'s protect arm and
    the signal path, would then trust it. Stamping only a corroborated pid means
    the value recorded is the leased server's own, which is what makes the cheap
    fingerprint check usable on that row from then on and shrinks the unprovable
    population instead of letting it persist forever.

    Consequence worth naming: a row that gains a fingerprint also gains
    `_is_stale`'s TTL immunity while that process lives - which is correct, and
    exactly the protection an `acquire --pid`/`bind` row has had all along.
    """
    owner = lease.get("owner") or {}
    if owner.get("pid_started") is not None or owner.get("host") != _host():
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
    proof, detail = _ownership_proof(lease, pid)
    if proof is None:
        return False
    fingerprint = _pid_fingerprint(pid)
    if not fingerprint:
        return False
    owner["pid_started"] = fingerprint
    lease["owner"] = owner
    sys.stderr.write(
        "allocator: recorded the missing owner.pid_started fingerprint for pid {pid} on "
        "the lease for database {db!r} - ownership was corroborated by {proof} ({detail}), "
        "so this row no longer has to be judged on the pid number alone.\n".format(
            pid=pid, db=lease.get("db_name"), proof=proof, detail=detail)
    )
    return True


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
    host whose ownership by this lease is PROVEN. Returns True when a stop was
    attempted, False when none was.

    Three gates, in order, each of them a fact about the pid rather than a
    default:
      1. SAME HOST - mirrors `_is_stale`'s `owner.host` check. A pid integer
         recorded on another host names an unrelated LOCAL process here.
      2. ALIVE - a dead pid has nothing to stop (silent: it is the trivially
         safe no-op, not a decision anyone needs to audit).
      3. PROVEN OURS - `_ownership_proof`: a matching `pid_started`
         fingerprint, or an independent corroborating observation (the process is
         an Odoo invocation for THIS lease's database, or it leads the group
         listening on a port THIS lease reserved). Nothing proven -> nothing
         signalled.

    NEITHER outcome is silent. Group-signalling on an unproven pid is how an
    unrelated shell session gets killed with no trace at all, and "no trace" was
    the worst property of that failure, worse than the kill: the run simply
    stopped. A refusal names the pid, the lease and the evidence on stderr - the
    same channel every other refusal in this file uses - so an un-reclaimed
    process is a REPORTED leak rather than a mystery, and it can be finished by
    hand. Reclamation of the lease ROW is the caller's business and is
    deliberately unaffected: `_gc` still reclaims and still drops, so refusing
    to signal leaks at most a process, never a lease or a database.
    """
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
    proof, detail = _ownership_proof(lease, pid)
    if proof is None:
        sys.stderr.write(
            "allocator: REFUSING to signal pid {pid} for the lease on database {db!r} - "
            "ownership is NOT proven: {detail}. NOTHING was signalled. A process-GROUP "
            "SIGTERM on an unproven pid kills whatever session now holds that number "
            "(its shell, its children, its test run), which is never the cheaper "
            "mistake. If that pid really is a runaway server for this lease, stop it "
            "by hand after checking it (`ps -ww -o args= -p {pid}` - the `-ww` matters, "
            "plain `ps` truncates the command line to 80 columns).\n".format(
                pid=pid, db=lease.get("db_name"), detail=detail)
        )
        return False
    sys.stderr.write(
        "allocator: stopping the process GROUP of pid {pid} for the lease on database "
        "{db!r} - ownership PROVEN by {proof}: {detail}.\n".format(
            pid=pid, db=lease.get("db_name"), proof=proof, detail=detail)
    )
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


# ONE timeout policy for the whole plugin: the SAME env var pg_mode.sh's
# PG_MODE_PROBE_TIMEOUT reads, with the same default, so a host that tunes the
# bound gets it applied to every probe rather than to half of them.
PROBE_TIMEOUT_ENV = "ODOO_AI_PG_PROBE_TIMEOUT"
DEFAULT_PROBE_TIMEOUT_S = 10
# A MUTATING Postgres call is not a probe: dropping a large database legitimately
# takes minutes, so it gets a far longer bound - DERIVED from the same knob rather
# than introduced as a second one. It is still bounded: an unreachable cluster
# blocks inside libpq with no connect timeout, and an unbounded drop hangs
# `release` exactly as an unbounded probe hangs `acquire`.
PG_OP_TIMEOUT_MULTIPLE = 30
# `timeout`'s own "bound elapsed" code, reused here so the shell and python halves
# report an unanswered probe identically. Callers MUST read it as UNDETERMINED.
EXIT_PROBE_TIMEOUT = 124
# odoo_db.py's "venv unavailable" sentinel (its EXIT_NO_VENV).
EXIT_NO_VENV = 10
# odoo_db.py's CONNECTION verdicts, mirrored here so this script never re-derives
# them: 8 = Odoo was refused authentication, 9 = the cluster did not answer.
# Both are facts about the connection every build opens, so no other surface may
# overrule them and neither is ever read as a capability answer.
EXIT_AUTH_DENIED = 8
EXIT_UNREACHABLE = 9


def _probe_timeout_s():
    """Wall-clock bound (seconds) for a read-only PROBE. A non-numeric or
    non-positive value falls back to the default rather than disabling the bound:
    "no bound" is never a safe reading of a malformed knob."""
    raw = os.environ.get(PROBE_TIMEOUT_ENV, "")
    try:
        secs = int(str(raw).strip() or DEFAULT_PROBE_TIMEOUT_S)
    except ValueError:
        return DEFAULT_PROBE_TIMEOUT_S
    return secs if secs > 0 else DEFAULT_PROBE_TIMEOUT_S


def _pg_op_timeout_s():
    """Wall-clock bound (seconds) for a MUTATING Postgres call - see
    PG_OP_TIMEOUT_MULTIPLE."""
    return _probe_timeout_s() * PG_OP_TIMEOUT_MULTIPLE


def _run(cmd, env=None, timeout=None):
    """(rc, stdout, stderr). `timeout` bounds the call in wall-clock seconds and
    reports EXIT_PROBE_TIMEOUT when it elapses - "could not answer", never a
    factual answer. Every call that talks to Postgres passes one."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return EXIT_PROBE_TIMEOUT, "", (
            f"{cmd[0]}: probe timed out after {timeout}s (no answer - not an answer of 'no')"
        )


def _which(binary):
    from shutil import which

    return which(binary)


# _createdb removed: the allocator no longer creates the ephemeral DB.
# The caller's `odoo-bin -d <db> -i <modules> --stop-after-init` performs
# create-on-init instead (B2 model: caller-side create, through-Odoo drop).
# The CREATEDB CAPABILITY is still required (Odoo create-on-init needs it too),
# but it is asked as a LIVE privilege query through the instance's own
# interpreter - see _can_createdb. A client binary is never consulted: its
# absence is not evidence about a role's privileges.


def _pg_client_argv(mode, container, binary, host, user, port, args):
    """argv running libpq client `binary` against this cluster in the DECLARED
    mode, or None when the mode offers no client surface.

    The CONNECTION flags differ per mode and must not be passed through blindly:
      native - reach the cluster the way every other consumer does: -h <host>,
               -U <user>, and -p <port> only when declared (empty-omit).
      docker - the command runs INSIDE the container, where the declared host and
               the PUBLISHED port do not exist: the mapping is a host-side fact
               and <host> resolves to the container's own loopback. Connect over
               the container's local socket (-U only). Passing the published port
               here would target a port nothing listens on inside the container.
    PARITY: mirrors pg_mode.sh `pg_run_client` - keep the two in lockstep.
    """
    if mode == "native":
        conn = ["-h", host, "-U", user]
        if port:
            conn += ["-p", str(port)]
        return [binary] + conn + list(args)
    if mode == "docker":
        if not container:
            return None
        pre = ["docker", "exec"]
        if os.environ.get("ODOO_PG_PASSWORD"):
            pre += ["-e", "PGPASSWORD"]
        return pre + ["-i", container, binary, "-U", user] + list(args)
    return None


# The ONE live privilege query behind every CREATEDB answer, whichever route
# asks it. odoo_db.py's cmd_can_createdb issues this same statement, so the two
# routes below can never disagree about WHAT is being asked.
_CREATEDB_SQL = "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"
_RECORD_ENV_HINT = (
    "run `45-venv.sh record-env --series <X.Y> [--profile <P>]` to declare "
    "`python` + `odoo_root` (and the `db_run_mode` client surface) for this instance"
)


class _ConnBlocked(object):
    """Route 1's answer when the CONNECTION itself failed, provably.

    Not a capability verdict and not "the route could not be asked": the route
    that PREDICTS the build outcome reached the cluster and was refused, or found
    no cluster at all. Returned as its own type so the ladder can STOP instead of
    consulting a surface that answers about a different connection - which is how
    a probe came to report `true` on a host whose builds could not authenticate.
    """

    __slots__ = ("state",)

    def __init__(self, state):
        self.state = state  # "denied" | "unreachable"

    @property
    def exit_code(self):
        return EXIT_AUTH_DENIED if self.state == "denied" else EXIT_UNREACHABLE


def _can_createdb_via_python(inst, host, user, port):
    """(verdict, reason) asked THROUGH the instance's own declared interpreter.

    THIS script runs under the ambient python3, which is not guaranteed to have
    psycopg2 - an Odoo venv is, since it cannot run odoo-bin without it. Same
    interpreter, same odoo_db.py, same connection resolution as the drop path.
    """
    venv_python = inst.get("python", "")
    if not venv_python:
        return None, ("this instance declares no `python` (a compose-run instance never "
                      "does), so no interpreter could ask")
    if not os.path.isfile(_ODOO_DB_PY):
        return None, "odoo_db.py not found at {p}".format(p=_ODOO_DB_PY)
    cmd = [venv_python, _ODOO_DB_PY, "can-createdb", "--db-host", host, "--db-user", user]
    odoo_root = inst.get("odoo_root", "")
    if odoo_root:
        cmd += ["--odoo-root", odoo_root]
    if port:
        cmd += ["--db-port", str(port)]
    # The password is NOT passed on argv (it would be world-readable in `ps`):
    # odoo_db.py reads ODOO_PG_PASSWORD from its environment, which this child
    # inherits - the same by-name discipline the docker client arm already applies.
    rc, out, err = _run(cmd, timeout=_probe_timeout_s())
    out = out.strip()
    if rc == 0 and out == "true":
        return True, ""
    if rc == 0 and out == "false":
        return False, ""
    if rc == EXIT_PROBE_TIMEOUT:
        return None, ("the interpreter probe timed out after {s}s - the cluster did not "
                      "answer (psycopg2 opens the connection with no libpq connect "
                      "timeout, so an unreachable cluster simply never replies); start "
                      "the cluster, or raise ${env}".format(
                          s=_probe_timeout_s(), env=PROBE_TIMEOUT_ENV))
    if rc == EXIT_NO_VENV:
        # odoo_db.py's own wording here is "cannot import odoo (no venv?)", which
        # MISDIAGNOSES the usual cause: a source checkout is never pip-installed,
        # so `import odoo` resolves only via `odoo_root` - the venv is fine and the
        # missing thing is a DECLARED key.
        return None, ("the declared `python` cannot import odoo: for a source checkout "
                      "that means `odoo_root` is not declared (the venv itself is fine) - "
                      + _RECORD_ENV_HINT)
    if rc in (EXIT_AUTH_DENIED, EXIT_UNREACHABLE):
        # The route WORKED and the connection did not. Mapping this to "could not
        # answer" is what let the ladder fall through and ask a client surface
        # about a connection Odoo never makes.
        state = "denied" if rc == EXIT_AUTH_DENIED else "unreachable"
        return _ConnBlocked(state), (
            "the connection Odoo itself opens reported {state}: {msg}".format(
                state=state, msg=err.strip() or out or "no output"))
    return None, "odoo_db.py can-createdb exited {rc}: {msg}".format(
        rc=rc, msg=err.strip() or out or "no output")


def _can_createdb_via_client(inst, host, user, port):
    """(verdict, reason) asked over the DECLARED libpq client surface.

    The route for an instance that declares no interpreter of its own - a
    `run_mode = "docker"` instance is launched by compose and never declares
    `python`, so without this route `--mode ephemeral` could NEVER succeed for a
    first-class supported run mode: it would always exit 7, no matter what the
    role's privileges actually are.

    This is a POSITIVE query put to the cluster, not an inference from which
    binaries exist: a client that is ABSENT still says nothing about a role's
    privileges (that conflation is the original defect), which is why a mode with
    no client surface returns None here rather than False.
    """
    mode = inst.get("db_run_mode", "")
    container = inst.get("db_container", "")
    argv = _pg_client_argv(mode, container, "psql", host, user, port,
                           ["-d", "postgres", "-tAc", _CREATEDB_SQL])
    if argv is None:
        return None, ("db_run_mode={m} offers no libpq client surface either, so no "
                      "client could ask".format(m=mode or "<absent>"))
    rc, out, err = _run(argv, env=_pg_env(), timeout=_probe_timeout_s())
    ans = out.strip().lower()
    if rc == 0 and ans in ("t", "true"):
        return True, ""
    if rc == 0 and ans in ("f", "false"):
        return False, ""
    if rc == EXIT_PROBE_TIMEOUT:
        return None, ("the psql probe over db_run_mode={m} timed out after {s}s".format(
            m=mode, s=_probe_timeout_s()))
    return None, "psql CREATEDB probe over db_run_mode={m} exited {rc}: {msg}".format(
        m=mode, rc=rc, msg=err.strip() or ans or "no output")


def _can_createdb(inst, host, user, port):
    """(verdict, reason): may the connecting role CREATE DATABASE?

    Two routes, tried in order, each asking the CLUSTER the same live privilege
    question: the instance's own interpreter first (the SSOT resolution path,
    shared with drop), then the declared libpq client surface. The first route
    that ANSWERS wins; `None` only when every route failed, and the reason then
    names each exhausted route so the user can see what to declare.

    verdict:
      True         - the role positively HAS CREATEDB.
      False        - the role positively LACKS it.
      _ConnBlocked - route 1 proved the CONNECTION is refused or the cluster is
                     absent. The ladder STOPS here: a client surface can only
                     answer about a different connection, so letting it overrule
                     this is answering the wrong question confidently.
      None         - UNDETERMINABLE (no route could answer).
    NEVER collapse None into False: cmd_acquire gives them different, both-loud
    exits, and neither is read as the other.
    """
    reasons = []
    for route in (_can_createdb_via_python, _can_createdb_via_client):
        verdict, why = route(inst, host, user, port)
        if isinstance(verdict, _ConnBlocked):
            return verdict, why
        if verdict is not None:
            return verdict, ""
        reasons.append(why)
    return None, "; ".join(reasons)


_DB_AUTH_STATES = {
    0: "ok",
    EXIT_AUTH_DENIED: "denied",
    EXIT_UNREACHABLE: "unreachable",
}


def _db_auth(inst, host, user, port):
    """(state, why): can Odoo AUTHENTICATE to this cluster?

    Runs `odoo_db.py preflight` under the instance's DECLARED interpreter, which
    opens the maintenance-database connection through Odoo's own resolution - the
    exact route every build verb takes. The child OWNS the refusal text; this
    function forwards its stderr rather than composing a second copy.

    state is "ok" | "denied" | "unreachable" | "unknown". Only the two PROVEN
    negatives ever block a caller: "unknown" means the question could not be
    asked, and a caller that refused on it would refuse on every host that has not
    finished declaring its environment yet.
    """
    venv_python = inst.get("python", "")
    if not venv_python:
        return "unknown", ("this instance declares no `python` (a compose-run instance "
                           "never does), so the connection Odoo itself opens could not "
                           "be tried")
    if not os.path.isfile(_ODOO_DB_PY):
        return "unknown", "odoo_db.py not found at {p}".format(p=_ODOO_DB_PY)
    cmd = [venv_python, _ODOO_DB_PY, "preflight", "--db-host", host, "--db-user", user]
    odoo_root = inst.get("odoo_root", "")
    if odoo_root:
        cmd += ["--odoo-root", odoo_root]
    if port:
        cmd += ["--db-port", str(port)]
    # The password travels in the ENVIRONMENT (odoo_db.py reads ODOO_PG_PASSWORD),
    # never on argv where `ps` exposes it.
    rc, out, err = _run(cmd, timeout=_probe_timeout_s())
    why = ""
    for line in out.splitlines():
        if line.startswith("DB_AUTH_WHY="):
            why = line.partition("=")[2].strip()
    if rc != 0 and err:
        # Forward the primitive's bytes verbatim - one message, one place.
        sys.stderr.write(err if err.endswith("\n") else err + "\n")
    if rc in _DB_AUTH_STATES:
        return _DB_AUTH_STATES[rc], why
    if rc == EXIT_PROBE_TIMEOUT:
        return "unknown", ("the connection probe timed out after {s}s - the cluster did "
                           "not answer at all (psycopg2 opens the connection with no "
                           "libpq connect timeout)".format(s=_probe_timeout_s()))
    if rc == EXIT_NO_VENV:
        return "unknown", ("the declared `python` cannot import odoo: for a source "
                           "checkout that means `odoo_root` is not declared - "
                           + _RECORD_ENV_HINT)
    return "unknown", (why or "odoo_db.py preflight exited {rc}: {msg}".format(
        rc=rc, msg=err.strip() or "no output"))


def _dropdb(host, user, db, port="", mode="", container=""):
    """Terminate backends then drop, via the DECLARED client surface.

    Returns False - having dropped NOTHING - when the declared mode offers no
    client surface. A missing client is NOT a completed drop: the caller must
    keep the lease and report, never remove a lease whose database is still on
    disk (that is how an unreferenced orphan is minted).
    """
    if not mode:
        # LEGACY-ONLY shim, and only in this fallback-of-a-fallback: a lease
        # minted before db_run_mode existed carries no mode. Accept `native`
        # when both binaries are genuinely present, so a pre-change lease on a
        # native host still drops exactly as it did before. This is not an
        # ad-hoc re-probe of the FACT (absent != tcp-only): it can only ever
        # succeed where the pre-fix code also succeeded, and it never fires for
        # an explicitly declared mode.
        if _which("psql") and _which("dropdb"):
            mode = "native"
    term_sql = ("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = '{db}' AND pid <> pg_backend_pid()".format(db=db))
    psql_argv = _pg_client_argv(mode, container, "psql", host, user, port,
                                ["-d", "postgres", "-tAc", term_sql])
    drop_argv = _pg_client_argv(mode, container, "dropdb", host, user, port,
                                ["--if-exists", db])
    if psql_argv is None or drop_argv is None:
        sys.stderr.write(
            "allocator: ERROR - cannot raw-drop {db}: db_run_mode={mode!r} offers no libpq "
            "client surface on this host. NOTHING was dropped and the lease is kept. Fix the "
            "through-Odoo path (declare a working `python` + `odoo_root` via 45-venv.sh) or "
            "declare db_run_mode=native|docker.\n".format(db=db, mode=mode or "<absent>")
        )
        return False
    env = _pg_env()
    err = ""
    for _ in range(3):
        _run(psql_argv, env=env, timeout=_pg_op_timeout_s())
        rc, _, err = _run(drop_argv, env=env, timeout=_pg_op_timeout_s())
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


_DROP_SURFACE_KEYS = ("python", "odoo_root", "db_run_mode", "db_container")


def _catalog_drop_surface(lease, instances_path=None):
    """The drop-surface facts the CURRENT catalog declares for `lease`, as a dict
    limited to _DROP_SURFACE_KEYS.

    A lease minted before a key existed carries nothing for it, and nothing ever
    back-fills a written lease - so on a host with no libpq client, such a lease
    is PERMANENTLY un-droppable: odoo_db.py exits 10 (no odoo_root), the raw
    fallback finds no mode, `_dropdb` refuses, release re-appends the lease, gc
    repeats it, and reap-orphans excludes any DB a lease references. Re-reading
    the catalog is what makes `45-venv.sh record-env` able to fix an EXISTING
    lease and not just future ones.

    Matched by series first (the lease's own series), then by cluster identity
    (db_host/db_user/db_port) - never by guesswork. Every adopted value is
    VALIDATED first (an interpreter that exists, a root that exists): a catalog
    can name a python that has since been deleted, and adopting that would turn a
    working raw fallback into a 127 the drop path reads as a real failure.
    Returns {} when nothing matches or the catalog cannot be read: a gap stays a
    gap, never a fabrication.
    """
    try:
        items = instances_io.load_instances(resolve_instances_path(instances_path))
    except (OSError, ValueError):
        return {}
    series = lease.get("series", "")
    host = lease.get("db_host") or lease.get("_pg", {}).get("host", "")
    user = lease.get("db_user") or lease.get("_pg", {}).get("user", "")
    port = str(lease.get("db_port") or lease.get("_pg", {}).get("port", "") or "")
    by_series = [it for it in items if series and instances_io.series_of(it) == series]
    by_cluster = [
        it for it in items
        if (it.get("db_host", "localhost") == (host or "localhost")
            and it.get("db_user", "odoo") == (user or "odoo")
            and str(it.get("db_port", "") or "") == port)
    ]
    for item in by_series + by_cluster:
        facts = {}
        if item.get("python") and os.path.isfile(item["python"]):
            facts["python"] = item["python"]
        if item.get("odoo_root") and os.path.isdir(item["odoo_root"]):
            facts["odoo_root"] = item["odoo_root"]
        if item.get("db_run_mode"):
            facts["db_run_mode"] = item["db_run_mode"]
            if item.get("db_container"):
                facts["db_container"] = item["db_container"]
        if facts:
            return facts
    return {}


def _drop_surface(lease, instances_path=None):
    """(python, odoo_root, db_run_mode, db_container) for this lease.

    The LEASE is authoritative for every fact it actually carries - it names the
    surface the database was created against. Only the GAPS are filled from the
    current catalog (see `_catalog_drop_surface`), so re-resolution can never
    redirect a drop at a cluster the lease never used.
    """
    values = {k: lease.get(k, "") for k in _DROP_SURFACE_KEYS}
    if all(values.values()):
        return values
    fallback = _catalog_drop_surface(lease, instances_path)
    filled = []
    for key in _DROP_SURFACE_KEYS:
        if not values[key] and fallback.get(key):
            values[key] = fallback[key]
            filled.append(key)
    if filled:
        sys.stderr.write(
            "allocator: lease for {db} predates {keys}; re-resolved from the current "
            "catalog so the drop surface is the one declared TODAY.\n".format(
                db=lease.get("db_name", "<unnamed>"), keys=", ".join(filled))
        )
    return values


_EXISTS_SQL = "SELECT 1 FROM pg_database WHERE datname = '{db}'"


def _declared_db_prefixes(instances_path=None):
    """Every db_name_prefix (or db_name) the CURRENT catalog declares.

    The same set `reap-orphans` derives, so the ephemeral-shape predicate answers
    identically wherever it is asked. An unreadable catalog yields an empty set:
    a gap stays a gap, and the caller then refuses rather than assuming a shape.
    """
    try:
        items = instances_io.load_instances(resolve_instances_path(instances_path))
    except (OSError, ValueError):
        return set()
    return {str(it.get("db_name_prefix") or it.get("db_name", "odoo")) for it in items}


def _db_present(lease, instances_path=None):
    """True / False / None: does this lease's database exist on its cluster?

    Two routes with the SAME shape as the CREATEDB ladder - the lease's own
    interpreter first (Odoo's connection resolution), then the DECLARED client
    surface - because a host whose Postgres is containerised has no interpreter of
    its own and a host with no client has no surface, and both must be answerable.

    None means "we could not look", which is NEVER the same as "it is not there":
    `dropdb --if-exists` exits 0 for a database that never existed, so an
    unverified success is exactly how a teardown that did not happen gets reported
    as one.
    """
    db = lease.get("db_name", "")
    if not db:
        return None
    pg = lease.get("_pg", {})
    host = lease.get("db_host") or pg.get("host", "localhost")
    user = lease.get("db_user") or pg.get("user", "odoo")
    port = lease.get("db_port") or pg.get("port", "")
    surface = _drop_surface(lease, instances_path)

    if surface["python"] and os.path.isfile(_ODOO_DB_PY):
        cmd = [surface["python"], _ODOO_DB_PY, "exists", db,
               "--db-host", host, "--db-user", user]
        if surface["odoo_root"]:
            cmd += ["--odoo-root", surface["odoo_root"]]
        if port:
            cmd += ["--db-port", str(port)]
        rc, out, _err = _run(cmd, timeout=_probe_timeout_s())
        answer = out.strip().lower()
        if rc == 0 and answer == "true":
            return True
        if rc == 0 and answer == "false":
            return False

    argv = _pg_client_argv(
        surface["db_run_mode"], surface["db_container"], "psql", host, user, port,
        ["-d", "postgres", "-tAc", _EXISTS_SQL.format(db=db.replace("'", "''"))])
    if argv is not None:
        rc, out, _err = _run(argv, env=_pg_env(), timeout=_probe_timeout_s())
        if rc == 0:
            return bool(out.strip())
    return None


def _client_drop_allowed(lease, instances_path=None):
    """(allowed, reason): may this lease's database be dropped over the CLIENT
    surface instead of through Odoo?

    Two gates, and they make the equivalence argument a PRECONDITION rather than a
    hope. `exp_drop` closes a connection pool, issues DROP DATABASE and removes a
    filestore; the client route matches that only for a throwaway database whose
    owning process group the caller has already stopped:

      1. `drop_on_release` must be set - true for a throwaway lease only, so a
         declared long-lived database is out of scope by construction.
      2. the name must carry the throwaway SHAPE for a prefix the CURRENT catalog
         declares, reusing `reap-orphans`' predicate. A hand-edited or corrupted
         lease naming a declared database can then never reach a client drop.

    Consulted by EVERY client-drop arm, so a future arm cannot bypass it.
    """
    db = lease.get("db_name", "")
    if not db:
        return False, "the lease names no database"
    if not lease.get("drop_on_release"):
        return False, ("this lease does not set drop_on_release, so its database is not "
                       "a throwaway this script may destroy over a client surface")
    prefixes = _declared_db_prefixes(instances_path)
    if not _is_ephemeral_shaped(db, prefixes):
        return False, (
            "{db} does not carry the throwaway <prefix>_t_<hex8> shape for any prefix "
            "the current catalog declares ({p}), so a client-side drop is refused - "
            "only the through-Odoo path may touch it".format(
                db=db, p=", ".join(sorted(prefixes)) or "<none declared>"))
    return True, ""


def _client_drop(lease, host, user, db, port, mode, container, instances_path=None):
    """Drop `db` over the DECLARED client surface, GATED and VERIFIED.

    Returns True only when the gates passed, the surface reported success, AND the
    database was not observed still present afterwards. Absence that cannot be
    confirmed is reported out loud and accepted (the surface said it dropped it);
    absence CONTRADICTED is a failure, because `dropdb --if-exists` exits 0 for a
    database that was never there.
    """
    allowed, reason = _client_drop_allowed(lease, instances_path)
    if not allowed:
        sys.stderr.write(
            "allocator: ERROR - refusing the client-side drop of {db}: {reason}. "
            "NOTHING was dropped and the lease is kept.\n".format(db=db, reason=reason))
        return False
    if not _dropdb(host, user, db, port, mode, container):
        return False
    still_there = _db_present(lease, instances_path)
    if still_there is True:
        sys.stderr.write(
            "allocator: ERROR - the client surface reported dropping {db}, but the "
            "database is STILL on the cluster. DB retained, lease kept for retry.\n".format(
                db=db))
        return False
    if still_there is None:
        sys.stderr.write(
            "allocator: WARNING - the client surface dropped {db} but its absence could "
            "not be confirmed on this host.\n".format(db=db))
    return True


def _drop_through_odoo(lease, instances_path=None):
    """Drop the ephemeral DB via odoo_db.py (through-Odoo path, B2 mandate).

    Consults the DECLARED client surface ONLY when the through-Odoo route did not
    reach the database at all:
      - the lease carries no `python` interpreter path, OR
      - odoo_db.py is missing on disk, OR
      - odoo_db.py exits 10 (venv-unavailable sentinel), OR
      - odoo_db.py exits 8 / 9 - authentication refused / cluster unreachable. A
        connection failure necessarily precedes any DROP DATABASE, so those two
        codes are a POSITIVE statement that nothing was attempted.

    Any OTHER non-zero exit is a genuine exp_drop failure: the drop WAS attempted
    and failed. The allocator then consults no client surface, does NOT drop the
    filestore, and does NOT remove the lease (so gc can retry / a human can
    investigate) - papering a real failure over with a client-side drop would
    destroy the one signal that says the database is still in use.
    Returns True on success, False when the drop failed and the lease must be kept.

    A client-side drop that FAILS returns False too: its return value is honoured,
    never discarded. Reporting a drop that did not happen as success is what
    mints a database with no lease referencing it - an orphan nothing can find.

    Every consultation of the client surface is logged loudly to stderr and gated
    by `_client_drop_allowed`. The filestore is cleaned up ONLY after a success.
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
    # The DECLARED drop surface, carried on the lease for the same reason
    # python/db_host/db_user are: release/gc must reconstruct the invocation after
    # the caller process is gone. Any key ABSENT on a pre-change lease is
    # re-resolved from the CURRENT catalog (see `_drop_surface`), so a lease
    # written before a key existed is repairable by `45-venv.sh record-env`
    # instead of permanently stuck; only a gap the catalog cannot fill falls
    # through to the narrowly-scoped legacy shim inside _dropdb.
    surface = _drop_surface(lease, instances_path)
    venv_python = surface["python"]
    mode = surface["db_run_mode"]
    container = surface["db_container"]
    odoo_root = surface["odoo_root"]

    if venv_python and os.path.isfile(_ODOO_DB_PY):
        cmd = [venv_python, _ODOO_DB_PY, "drop", db, "--db-host", host, "--db-user", user]
        if odoo_root:
            cmd += ["--odoo-root", odoo_root]
        if port:
            cmd += ["--db-port", str(port)]
        # The password travels in the ENVIRONMENT (odoo_db.py reads
        # ODOO_PG_PASSWORD), never on argv where `ps` exposes it.
        rc, _, err = _run(cmd, timeout=_pg_op_timeout_s())
        if rc == 0:
            _drop_filestore(db)
            return True
        elif rc == 10:
            # venv-unavailable sentinel: the through-Odoo route never ran at all.
            sys.stderr.write(
                "allocator: WARNING - venv unavailable ({python}), consulting the declared "
                "client surface to drop {db}\n".format(python=venv_python, db=db)
            )
            if not _client_drop(lease, host, user, db, port, mode, container,
                                instances_path):
                sys.stderr.write(
                    "allocator: ERROR - the client-surface drop of {db} FAILED; DB "
                    "retained, lease kept for retry.\n".format(db=db)
                )
                return False
            _drop_filestore(db)
            return True
        elif rc in (EXIT_AUTH_DENIED, EXIT_UNREACHABLE):
            # The connection failed, so DROP DATABASE was never issued: this is a
            # POSITIVE statement that nothing was attempted, which is what makes
            # consulting another surface honest here and dishonest below.
            sys.stderr.write(
                "allocator: WARNING - the through-Odoo drop of {db} never reached the "
                "database (rc={rc}: {what}); consulting the declared client surface. "
                "stderr: {err}\n".format(
                    db=db, rc=rc,
                    what=("authentication refused" if rc == EXIT_AUTH_DENIED
                          else "cluster unreachable"),
                    err=err.strip())
            )
            if not _client_drop(lease, host, user, db, port, mode, container,
                                instances_path):
                sys.stderr.write(
                    "allocator: ERROR - the client-surface drop of {db} FAILED; DB "
                    "retained, lease kept for retry.\n".format(db=db)
                )
                return False
            _drop_filestore(db)
            return True
        else:
            # Genuine exp_drop failure - the drop WAS attempted. Retain the DB and
            # the lease for retry; no client surface is consulted, because a real
            # failure must never be papered over with a second drop command.
            sys.stderr.write(
                "allocator: ERROR - through-Odoo drop of {db} failed (rc={rc}); "
                "DB retained, lease kept for retry. stderr: {err}\n".format(
                    db=db, rc=rc, err=err.strip())
            )
            return False

    # No venv python or odoo_db.py missing: the through-Odoo route cannot run.
    if not venv_python:
        sys.stderr.write(
            "allocator: WARNING - venv unavailable, consulting the declared client "
            "surface to drop {db}\n".format(db=db)
        )
    else:
        # odoo_db.py missing on disk (should not happen, but handle gracefully).
        sys.stderr.write(
            "allocator: WARNING - odoo_db.py not found at {path}, consulting the declared "
            "client surface to drop {db}\n".format(path=_ODOO_DB_PY, db=db)
        )
    if not _client_drop(lease, host, user, db, port, mode, container, instances_path):
        sys.stderr.write(
            "allocator: ERROR - the client-surface drop of {db} FAILED; DB retained, "
            "lease kept for retry.\n".format(db=db)
        )
        return False
    _drop_filestore(db)
    return True


# --------------------------------------------------------------------------- #
# GC
#
# Reclaiming is DESTRUCTIVE and mostly IMPLICIT. For every condemned lease `_gc`
# stops the owner's process GROUP and DROPS the database, then removes the row -
# and the registry was the only place those coordinates existed. `gc` (the verb a
# human deliberately types) reported what it took; the two `acquire` passes -
# called by every build, every test run, every subagent dispatch - ran the same
# destruction as a side effect and said NOTHING. That asymmetry is backwards, and
# it is worse than a plain data loss: the victim does not see "something reclaimed
# my lease", it sees a suite that suddenly cannot connect or a setUpClass failing
# on a database the previous command created successfully. The natural inference
# is a regression in the code under test, so an unattributable deletion does not
# merely lose data - it MANUFACTURES A FALSE HYPOTHESIS and sends the debugging
# somewhere else entirely. Reclamation is also cross-tenant by construction (`_gc`
# walks the whole shared registry), so one run's `acquire` destroys another run's
# state, and neither side could learn what happened.
#
# So every reclamation now leaves a RECORD, and `_gc` itself emits it (rather than
# each call site being trusted to) - a future fourth call site cannot reintroduce
# the silence, and `verb` is a REQUIRED argument so it cannot be added without
# saying whose output the record belongs to. Two channels, both outliving the
# registry row:
#   - one line per reclaimed lease on STDERR, the same channel every other
#     refusal in this file uses. NEVER stdout: `cmd_acquire`'s stdout is a
#     PROTOCOL (`eval $(allocator.py acquire ...)`), so a prose line interleaved
#     there would be executed by the caller's shell.
#   - the same record appended to the evidence log (see RECLAIM_LOG_BASENAME),
#     because a subagent's stderr is frequently not what the human ends up
#     reading.
# --------------------------------------------------------------------------- #

# Condemn-reason vocabulary - the SSOT for WHY a lease was condemned: exactly one
# string per condemn arm of `_condemn_reason` below, and the only values that ever
# reach a notice, the evidence log, or an operator's grep. The reason is the part
# of the record that CANNOT be reconstructed after the fact: a lease's token, db
# and ports can still be recovered from the caller's earlier ALLOC_* block, but
# once the row is gone nothing on the machine remembers which arm judged it.
CONDEMN_PID_DEAD = "owner-pid-dead"
CONDEMN_PID_RECYCLED = "owner-pid-recycled"
CONDEMN_TTL_UNPROVABLE = "ttl-expired-liveness-unprovable"
CONDEMN_PARK_EXPIRED = "park-budget-expired"
CONDEMN_REASONS = (
    CONDEMN_PID_DEAD, CONDEMN_PID_RECYCLED, CONDEMN_TTL_UNPROVABLE, CONDEMN_PARK_EXPIRED,
)

# The evidence log, appended under `$ODOO_AI_HOME/logs/` (Tier-1: machine-global
# flat, exactly like the registry it outlives - see snippets/state-root-resolution.md).
# JSONL so a consumer parses it without a format of its own, and append-only so
# concurrent allocators cannot lose each other's lines (one short line per O_APPEND
# write, and `_gc` holds the registry flock anyway).
#
# ITS NAME IS DELIBERATELY OUTSIDE the run-artifact globs `prune_stale_run_artifacts`
# (`scripts/lib/state_reclaim.sh`) sweeps - `*.log`, `*.findings.md`, `*.conf` - so
# it is NOT swept, and that is a decision, not an oversight. That sweeper's
# mtime-plus-lease-reachability policy is right for a per-run build log, and
# precisely wrong here: this file is the ONLY surviving evidence that a database
# was destroyed, so an mtime bound would delete exactly the record needed to
# explain a deletion older than the bound - an evidence log that deletes itself
# defeats its own purpose. Nothing else reclaims it either, which is affordable
# because it grows ONLY when something was actually destroyed (one line per
# reclaimed lease, a few hundred bytes), never per acquire.
RECLAIM_LOG_BASENAME = "allocator-reclaimed.jsonl"

# The record's fields, in the order the stderr notice prints them: identity first
# (which lease, whose run, which database, which pid), then the verdict, then who
# performed the reclamation - so a victim and a perpetrator can each recognise
# themselves in the same line.
_RECLAIM_NOTICE_FIELDS = (
    "token", "run_id", "db_name", "mode", "series", "owner_pid", "owner_host",
    "reason", "dropped_db", "by_verb", "by_pid", "by_run_id", "at_utc",
)


def _condemn_reason(lease):
    """The ARM that condemns `lease`, or None when the lease is protected.

    Liveness is AUTHORITATIVE, not merely a condemn-only signal.

    Direction matters (state it explicitly so a future edit does not invert
    it): for reaping, the safe default is to NOT reap when unsure - an
    un-reaped orphan only costs RAM, but a wrongly-reaped lease kills a live
    server and destroys the owner's in-progress work. So:
      - A PARKED lease (`parked_at` present) is judged FIRST, by its own
        budget, and by nothing else. Park CLEARS the owner pid on purpose after
        stopping that process group, so every pid arm below would read the row
        as "no pid recorded" and hand it straight to TTL - reclaiming a
        deliberately suspended instance, and dropping its database, for the
        very act of suspending it. `resume` DELETES `parked_at`, which is what
        returns a resumed lease to the pid arms below (and to the SubagentStop
        teardown gate) rather than leaving it governed by a park budget for the
        rest of its life.
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

    Each condemn arm returns its OWN reason from CONDEMN_REASONS rather than a
    bare True, because that verdict is the one fact about a reclaimed lease that
    no later reader can re-derive - the row, the process and the database are all
    gone by the time anyone asks. `_is_stale` is the boolean face of this
    function for the callers that only need the predicate.
    """
    parked_at = lease.get("parked_at")
    if parked_at is not None:
        # FIRST arm, before the host/pid block, and the position is load-bearing
        # twice over. (a) A parked lease is pid-less by construction, so without
        # this early return control would fall through to the TTL comparison and
        # condemn every parked lease the moment its ORDINARY ttl_s lapsed.
        # (b) Keeping it ahead of - rather than inside - the host/pid block is
        # what leaves that block's behavior untouched for every NON-parked
        # pid-less lease, which is the shape
        # `test_is_stale_unprovable_liveness_still_governed_by_ttl` pins.
        recorded_boot = lease.get("parked_boot_id")
        current_boot = _boot_id()
        if recorded_boot and current_boot and recorded_boot != current_boot:
            # The host rebooted while this lease was parked, so the park budget
            # was never CONSUMED - it only elapsed on a machine that was off.
            # Treat it as not started: protect the row and let `resume`
            # re-stamp the current boot id. Comparing only when BOTH sides have
            # a value is deliberate - an absent or unreadable boot id (not
            # Linux, or a container reporting the host's) degrades to the plain
            # budget comparison below, never to a condemn on ambiguity and
            # never to a permanent reprieve.
            return None
        if _now() - parked_at > int(lease.get("park_ttl_s", DEFAULT_PARK_TTL_S)):
            return CONDEMN_PARK_EXPIRED
        return None
    owner = lease.get("owner", {})
    if owner.get("host") == _host():
        pid = owner.get("pid")
        if pid is not None:
            pid = int(pid)
            if not _pid_alive(pid):
                # condemn arm: unambiguous, no fingerprint needed
                return CONDEMN_PID_DEAD
            expected_fp = owner.get("pid_started")
            if expected_fp is not None:
                current_fp = _pid_fingerprint(pid)
                if current_fp is not None:
                    if current_fp == expected_fp:
                        return None  # PROVEN alive: protected, TTL not consulted
                    # PROVEN recycled: owner is as gone as a dead pid
                    return CONDEMN_PID_RECYCLED
                # current_fp is None: could not re-measure right now - not a
                # proven mismatch, so do not condemn on ambiguity; fall through.
            # else: no fingerprint was ever recorded for this lease (an older
            # allocator, or `ps` was unavailable at record time) - liveness is
            # UNPROVABLE here; fall through to TTL, same as a different host.
    ttl = lease.get("ttl_s", DEFAULT_TTL_S)
    if _now() - lease.get("heartbeat_at", lease.get("owner", {}).get("started_at", 0)) > ttl:
        return CONDEMN_TTL_UNPROVABLE
    return None


def _is_stale(lease):
    """Boolean face of `_condemn_reason` - true when SOME arm condemns the lease.

    Kept as its own name because most callers (`cmd_query`, `cmd_assert_droppable`)
    only ask the yes/no question; only the reclaiming path needs to know WHICH arm
    answered. One predicate, one implementation: a second copy of this judgment is
    how the shell half and the python half drift apart.
    """
    return _condemn_reason(lease) is not None


def _reclaim_record(lease, reason, verb, run_id=""):
    """The full, self-contained account of ONE reclamation.

    Self-contained is the whole point: it is read AFTER the registry row it
    describes has been deleted, so every coordinate a reader might need - lease,
    run, database, ports, owner - is copied out here rather than referenced.
    `by_*` names the reclaimer, which is what makes a cross-tenant reclamation
    attributable in both directions: the victim learns who took its lease, and the
    caller learns it destroyed state it never asked about.
    """
    owner = lease.get("owner", {}) or {}
    at = _now()
    return {
        "at": at,
        "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)),
        "token": lease.get("token", ""),
        "run_id": owner.get("run_id", ""),
        "db_name": lease.get("db_name", ""),
        "mode": lease.get("mode", ""),
        "series": lease.get("series", ""),
        "owner_pid": owner.get("pid"),
        "owner_host": owner.get("host", ""),
        "ports": lease.get("ports", []),
        "reason": reason,
        "dropped_db": bool(lease.get("drop_on_release") and lease.get("db_name")),
        "by_verb": verb,
        "by_pid": os.getpid(),
        "by_run_id": run_id,
    }


def _notice_value(value):
    """Render one field for the stderr notice. An absent value is the empty
    string (never the word "None"), and a boolean is spelled as JSON spells it so
    the line and the evidence log read identically."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _reclaim_notice(rec):
    """One line, `key=value` with shell-quoted values: greppable by a human who
    only has a scrollback, and parseable by anything else. The full token is
    printed (not the 8-char fingerprint `cmd_list` redacts to) because a reclaimed
    token is DEAD - it can no longer be handed to `release` - and matching it
    against the caller's own earlier `ALLOC_TOKEN=` is how an operator identifies
    which of their runs just lost its database. `cmd_gc`'s long-standing
    `ALLOC_RECLAIMED=` emission already prints it in full for the same reason."""
    fields = " ".join(
        "{k}={v}".format(k=key, v=shlex.quote(_notice_value(rec.get(key))))
        for key in _RECLAIM_NOTICE_FIELDS
    )
    return "allocator: RECLAIMED lease {fields}\n".format(fields=fields)


def _reclaim_log_path():
    return os.path.join(_home(), "logs", RECLAIM_LOG_BASENAME)


def _append_reclaim_log(rec):
    """Append one JSON record to the evidence log. Best-effort but never SILENT:
    a record that cannot be persisted is itself reported on stderr, because the
    one thing this whole path exists to prevent is a destruction nobody can
    attribute. Never fatal - failing to write the account of a reclamation must
    not fail the acquire that already performed it."""
    path = _reclaim_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    except OSError as exc:
        sys.stderr.write(
            "allocator: WARNING - could not append the reclaim record for lease "
            "{token} to {path} ({exc}); the stderr line above is now the ONLY "
            "record of that reclamation.\n".format(
                token=rec.get("token", ""), path=path, exc=exc)
        )


def _report_reclaimed(rec):
    """Both channels, one call - so neither can be added without the other."""
    sys.stderr.write(_reclaim_notice(rec))
    _append_reclaim_log(rec)


def _gc(reg, verb, instances_path=None, run_id=""):
    """Reclaim stale leases (drop their ephemeral DB via through-Odoo path),
    REPORTING each one. Mutates reg; returns the reclaim records.

    `verb` is required, and is the command whose output must carry the record
    (`acquire`, `gc`, ...). It has no default on purpose: a new call site cannot
    reintroduce the silent-destruction bug this reporting exists to close, because
    it cannot call this function at all without naming itself.
    """
    kept, reclaimed = [], []
    for lease in reg["leases"]:
        reason = _condemn_reason(lease)
        if reason is not None:
            # Reap the ORPHAN before reclaiming: a lease can be stale by ttl while
            # its server process is STILL alive (the box did not crash, the owner
            # just went away). Stop that process group first so we free RAM AND so
            # the drop below is not blocked by a live backend. A dead pid here is a
            # no-op (the same-host + liveness guard short-circuits).
            _stop_owner_group_if_local(lease)
            if lease.get("drop_on_release") and lease.get("db_name"):
                drop_ok = _drop_through_odoo(lease, instances_path)
                if not drop_ok:
                    # Genuine drop failure: retain the lease so a human / next gc
                    # can retry.  Do not count it as reclaimed, and do not report
                    # it as reclaimed either - the row and the database both still
                    # exist, so a record here would be a false account.
                    kept.append(lease)
                    continue
            record = _reclaim_record(lease, reason, verb, run_id)
            reclaimed.append(record)
            # Per lease, as it is reclaimed, NOT after the loop: if this process
            # dies part-way through a sweep, every lease it already destroyed has
            # already been accounted for, and the ones it has not reached are
            # still in the registry (which is only written after this returns).
            _report_reclaimed(record)
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

    This is the ONE place that reads the catalog's declared addons_path, so
    there is a single spelling of that read to keep correct.

    With no override the catalog value is flattened as declared, through the
    SSOT pair `instances_io.addons_path_list` (which knows BOTH declared shapes
    - a TOML array and a bare flattened string) and `join_addons_path`. Reading
    the raw `inst["addons_path"]` here instead would join a STRING-shaped
    declaration character by character, so `"/a,/b"` became `/,a,/,b` - a wrong
    value, not a crash, written onto the lease row that `50-instance-spinup.sh
    apply` now reads to pick which tree it serves.
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
        return instances_io.join_addons_path(instances_io.addons_path_list(inst)), None
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


def _emit_instance_common(inst, addons_csv):
    """Emit the fields every acquire mode shares.

    `addons_csv` is REQUIRED, not merely conventionally always passed. Every
    call site lives in `cmd_acquire`, which resolves it via
    `_resolve_addons_csv` up front and returns early on error - so by the time
    any of the three call sites below is reached, a real value already exists.
    A `None` default here was therefore unreachable: no live path could ever
    exercise the fallback that used to re-derive the value through a second
    copy of `_resolve_addons_csv`'s expression (the SAME copy that once joined
    a STRING-shaped catalog addons_path character by character - see
    `_resolve_addons_csv`, the ONE place that reads the catalog's declared
    addons_path). Dropping the default turns a future omission into a loud
    `TypeError` instead of silently taking a path nobody tested.
    """
    _emit("ALLOC_PYTHON", inst.get("python", ""))
    _emit("ALLOC_ADDONS_PATH", addons_csv)
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
            # Reports every lease it reclaims on stderr + the evidence log (see the
            # GC section header); the return value is unused HERE only because this
            # path writes the registry unconditionally below.
            _gc(reg, "acquire", path, run_id)
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
    # (Odoo create-on-init), which also requires the role to have CREATEDB.
    #
    # NEVER DEGRADE. An `ephemeral` request either gets an ISOLATED throwaway DB
    # or fails loudly. Silently handing back an `exclusive` lease on the DECLARED,
    # long-lived database (the pre-fix behavior) destroyed the only guarantee this
    # mode exists to provide: two concurrent callers wrote the same durable DB and
    # neither was told. The caller - not this script - owns any trade of isolation
    # for serialisation, and must state it by re-dispatching with an explicit
    # --mode exclusive. --no-create still skips the check entirely (the caller
    # declared it creates no database, so CREATEDB is irrelevant to it).
    # AUTHENTICATION IS EVALUATED FIRST, and for every mode that will build.
    # Odoo's CLI opens the maintenance-database connection for every `-d <name>`
    # run before any module loads, so a cluster that refuses Odoo kills the build
    # whatever the role's privileges are - and a capability answer emitted beside a
    # proven refusal is a contradiction, not extra information. Only the two PROVEN
    # negatives refuse: "unknown" never blocks, because a host that has not
    # finished declaring its environment must still be able to allocate.
    # --no-create skips this entirely (that caller opens no database at all).
    if mode in ("ephemeral", "exclusive") and not opts.get("no_create"):
        auth_state, auth_why = _db_auth(inst, host, user, db_port)
        if auth_state in ("denied", "unreachable"):
            sys.stderr.write(
                "allocator: REFUSING the {m} acquire for series {series} - Odoo cannot "
                "open its own connection to the database ({state}). NO lease was "
                "written and NOTHING was created. See the message above; {why}\n".format(
                    m=mode, series=instances_io.series_of(inst), state=auth_state,
                    why=auth_why or "no detail reported")
            )
            return EXIT_AUTH_DENIED if auth_state == "denied" else EXIT_UNREACHABLE

    if mode == "ephemeral" and not opts.get("no_create"):
        verdict, why = _can_createdb(inst, host, user, db_port)
        if isinstance(verdict, _ConnBlocked):
            sys.stderr.write(
                "allocator: REFUSING the ephemeral acquire for series {series} - the "
                "CREATEDB question could not be put to the cluster because the "
                "connection Odoo itself opens reported {state}. NO lease was written. "
                "{why}\n".format(series=instances_io.series_of(inst),
                                 state=verdict.state, why=why)
            )
            return verdict.exit_code
        if verdict is False:
            sys.stderr.write(
                "allocator: REFUSING ephemeral acquire - role {user!r} on {host}:{port} may not "
                "CREATE DATABASE, so an isolated throwaway database is impossible.\n"
                "  Choose ONE, explicitly:\n"
                "    - grant the role CREATEDB, then retry --mode ephemeral; or\n"
                "    - re-dispatch with --mode exclusive to accept a SERIALISED hold on the\n"
                "      declared database - isolation is then NOT provided, say so in your report; or\n"
                "    - pass --no-create if this run creates no database at all.\n".format(
                    user=user, host=host, port=db_port or "libpq-default")
            )
            return 6
        if verdict is None:
            sys.stderr.write(
                "allocator: REFUSING ephemeral acquire - CREATEDB capability is UNDETERMINABLE "
                "for series {series}: {why}.\n"
                "  Undeterminable is NEVER read as 'no': the acquire fails so that no caller can "
                "receive a non-isolated lease it did not ask for.\n"
                "  Choose ONE, explicitly:\n"
                "    - {hint}, then retry; or\n"
                "    - declare db_run_mode=docker + db_container (or native) so the capability "
                "can be asked over a libpq client surface instead; or\n"
                "    - start the cluster, if it is simply not running; or\n"
                "    - re-dispatch with an explicit --mode (exclusive provides NO isolation - "
                "say so in your report).\n".format(
                    series=instances_io.series_of(inst), why=why, hint=_RECORD_ENV_HINT)
            )
            return 7

    if mode == "ephemeral":
        db_name = f"{prefix}_t_{uuid.uuid4().hex[:8]}"
    else:
        db_name = opts.get("db_name") or inst.get("db_name", "odoo")

    with _locked():
        reg = _read_registry()
        # Each reclaimed lease is reported (stderr + evidence log) by `_gc` itself;
        # the records are truth-tested here only to decide the immediate persist.
        if _gc(reg, "acquire", path, run_id):
            # PERSIST THE GC OUTCOME IMMEDIATELY. `_gc` has already DROPPED the
            # reclaimed leases' databases, and the paths below can still return
            # 3 (exclusive conflict) or 4 (port pool exhausted) before the single
            # registry write at the end - which would leave the registry
            # advertising a lease whose database no longer exists.
            _write_registry(reg)

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
            # odoo_root makes `import odoo` resolve for a source checkout (the
            # through-Odoo drop's precondition); db_run_mode/db_container decide
            # how a client binary is reached if the raw fallback is ever taken.
            # All three are empty on a catalog that predates them - handled, and
            # never a reason to invent a value.
            "odoo_root": inst.get("odoo_root", ""),
            "db_run_mode": inst.get("db_run_mode", ""),
            "db_container": inst.get("db_container", ""),
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
        sys.stderr.write("Usage: allocator.py release <token> --run-id <id>\n")
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

        # Ownership guard - it asks the ONE question a release site must answer:
        # did this caller ACQUIRE this lease? `owner.run_id` is the answer, so a
        # lease that records one is released only by the run it names.
        # An EMPTY caller run is refused WITH the mismatches, not exempted from
        # them. It does not mean "the rightful owner forgot a flag"; it means
        # ownership cannot be established at all - and a call that is about to
        # stop a server and DROP a database is the last place to guess. The
        # rightful owner is never stuck by this: it already holds the run id
        # (`ALLOC_RUN_ID` from its own acquire, `INSTANCE_HANDLE.run_id`
        # downstream) and threads it; a caller that cannot produce one did not
        # acquire this lease and has nothing here to release.
        # This is the shape `cmd_assert_droppable` has used from the start.
        # `cmd_release` was the outlier: its extra `and caller_run` conjunct read
        # as leniency towards the owner while actually licensing a stranger - an
        # un-threaded release short-circuited the whole comparison, and one such
        # call destroyed a live acceptance database (113 modules + demo data) that
        # a peer session had built minutes earlier.
        # An UNOWNED lease (no run_id recorded at all) still releases on
        # token-possession. That is a deliberate NON-import of
        # `assert_droppable`'s P5.8 arm: P5.8 guards a BARE-NAME drop, which
        # carries no evidence of ownership whatsoever, while `release` requires
        # the token; refusing unowned leases here would leave every pre-run_id
        # and never-threaded lease with no exit but `--force`, and `release` is
        # the only correct teardown path there is.
        # `--force` overrides loudly - it is the human's override, never a
        # dispatched agent's way around a refusal.
        caller_run = opts.get("run_id") or opts.get("session", "")
        owner = found.get("owner", {})
        owner_run = owner.get("run_id") or owner.get("session_id", "")
        force = opts.get("force")
        if owner_run and owner_run != caller_run:
            caller_desc = repr(caller_run) if caller_run else "NOT NAMED (no --run-id passed)"
            if not force:
                sys.stderr.write(
                    "allocator: REFUSING to release the lease for db "
                    f"{found.get('db_name')!r}: it is owned by run {owner_run!r} and "
                    f"this caller's run is {caller_desc}. A release must name the run "
                    "that ACQUIRED the lease - thread the --run-id your own acquire "
                    "echoed as ALLOC_RUN_ID (INSTANCE_HANDLE.run_id downstream). If you "
                    "did not acquire this lease, leave it alone: holding the token is not "
                    "ownership, and this lease may be about to drop a live database. "
                    "--force overrides. The DB is NOT dropped and the lease is KEPT.\n"
                )
                return 1
            sys.stderr.write(
                f"allocator: force-releasing run {owner_run!r}'s lease "
                f"(caller run {caller_desc}).\n"
            )

        # Teardown ORDER is mandatory (L1.2): stop the server's process group
        # FIRST, THEN drop the DB. A listening Odoo master + workers hold open DB
        # connections, and an active backend blocks `DROP DATABASE`; stopping the
        # group closes those connections (odoo_db.py's pg_terminate_backend stays
        # as a second belt). No-op for a lease with no live local pid (legacy
        # pre-setsid / shared / already-dead), so this is always safe to call.
        _stop_owner_group_if_local(found)

        if found.get("drop_on_release") and found.get("db_name"):
            drop_ok = _drop_through_odoo(found, opts.get("instances"))
            if not drop_ok:
                # The drop did not happen. Before NAMING anything, ask whether the
                # database is even there: "abandoned" is a claim about the cluster,
                # and a build that crashed before creating anything leaves a lease
                # whose drop can only ever "fail" - un-releasable from both ends.
                db_name = found.get("db_name", "")
                present = _db_present(found, opts.get("instances"))
                cluster = "{user}@{host}:{port}".format(
                    user=found.get("db_user", "odoo"),
                    host=found.get("db_host", "localhost"),
                    port=found.get("db_port") or "libpq-default")
                if present is False:
                    # PROVABLY absent: the drop had nothing to do IN POSTGRES, so
                    # this is a clean release, not a failure. The other half of the
                    # leak.
                    # The FILESTORE is a separate object with its own lifetime, and
                    # this path is reached exactly when the database went away
                    # without Odoo dropping it - a deleted container volume takes
                    # every ephemeral database with it and leaves every filestore
                    # directory behind. Releasing the lease here puts that
                    # directory beyond BOTH reapers at once: `gc` is lease-driven
                    # and the lease is about to be gone, `reap-orphans` is
                    # pg_database-driven and there is no row. So it is removed
                    # here, before the lease is dropped, or "NOTHING was left
                    # behind" would be false by one directory per run, forever.
                    _drop_filestore(db_name)
                    sys.stderr.write(
                        "allocator: {db} does not exist on {cluster}, so there was "
                        "nothing to drop in PostgreSQL - its filestore directory was "
                        "removed here (no lease and no pg_database row would be left "
                        "for either reaper to find it by), the lease is released and "
                        "NOTHING was left behind.\n".format(db=db_name, cluster=cluster))
                    _emit("ALLOC_FORGOTTEN_DB", db_name)
                elif not opts.get("force_forget"):
                    # Present, or unverifiable: retain the lease so gc can retry.
                    if present is None:
                        sys.stderr.write(
                            "allocator: whether {db} exists on {cluster} could NOT be "
                            "determined, so its lease is treated as live.\n".format(
                                db=db_name, cluster=cluster))
                    sys.stderr.write(
                        "allocator: the lease for {db} is KEPT because the database is still "
                        "there. Fix the drop surface (see the message above; `45-venv.sh "
                        "record-env` re-declares it and is re-read on every retry), or - when "
                        "nothing on this host can ever drop it - pass --force-forget to give "
                        "up the lease and have the abandoned database named for manual "
                        "cleanup.\n".format(db=db_name)
                    )
                    reg["leases"] = kept + [found]
                    _write_registry(reg)
                    return 1
                elif present is True:
                    # --force-forget: the DOCUMENTED escape from an un-droppable
                    # lease. It never pretends the teardown happened - the database,
                    # its cluster, and the manual step are all named, and the name is
                    # also emitted machine-readably for a caller's report. The word
                    # ABANDONED is now EARNED: the database was observed present.
                    sys.stderr.write(
                        "allocator: FORCE-FORGETTING the lease for {db} - the database was "
                        "NOT dropped and is now ABANDONED on {cluster}. Drop it by "
                        "hand once a client surface exists; nothing will retry it.\n".format(
                            db=db_name, cluster=cluster)
                    )
                    _emit("ALLOC_ABANDONED_DB", db_name)
                else:
                    # --force-forget with existence UNVERIFIABLE. The lease is gone
                    # either way, so say exactly that and no more: claiming the
                    # database was abandoned would assert a cluster fact nothing
                    # here observed.
                    sys.stderr.write(
                        "allocator: FORCE-FORGETTING the lease for {db} - the lease is "
                        "gone, and whether the database still exists on {cluster} could "
                        "NOT be confirmed from this host. Check by hand; nothing will "
                        "retry it.\n".format(db=db_name, cluster=cluster)
                    )
                    _emit("ALLOC_UNVERIFIED_DB", db_name)
        reg["leases"] = kept
        _write_registry(reg)
    return 0


def cmd_heartbeat(opts):
    """Refresh a lease's heartbeat - and, while the row is open under the lock,
    BACKFILL the `owner.pid_started` fingerprint it may be missing.

    Heartbeat is the right (and only) home for the backfill: it is the periodic
    touch by the owner itself, it already writes the registry, and it is the one
    place where recording proof does not race a decision that is being taken
    right now. `acquire --pid` and `bind` already capture the fingerprint at
    record time; `gc`/`release` are deciding the lease's fate as they read it, so
    stamping a row that is about to be removed would buy nothing. The backfill is
    corroboration-gated - see `_backfill_pid_fingerprint` for why an ungated one
    would manufacture false proof."""
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
                _backfill_pid_fingerprint(lease)
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


def cmd_park(opts):
    """SUSPEND a RUNNING lease: stop its server, keep everything it reserved.

    The state this file was missing. Before `park` existed a caller that was
    finished with an instance for NOW - but not finished with the DATABASE it
    had just spent minutes building - had exactly two exits: `release` (which
    stops the server AND drops the database) or leave the lease held (which
    leaks RAM and is what the SubagentStop teardown gate hard-blocks). Both
    answers destroy work: one destroys the database, the other is refused.

    `park` is the third exit. Order inside the single lock, and it is the whole
    safety argument:
      1. REFUSE a `shared` lease (exit 3). The shared row is the ONE answer
         `query --series` gives for a series; a parked twin would make that rung
         two-valued, and the shared row is already immune to the pid arms
         anyway, so parking it would buy nothing and cost the invariant.
      2. REFUSE a lease that is not RUNNING (exit 4) - no `owner.pid` recorded.
         That covers a still-RESERVED lease, an already-parked one (park cleared
         its pid, so a second park is refused rather than silently re-stamping a
         fresh budget onto an old park), and the `--stop-after-init` build shape
         that never binds a pid at all: none of them has a process to stop or a
         listening state worth preserving.
      3. STOP THE OWNER'S PROCESS GROUP FIRST, through the same
         `_stop_owner_group_if_local` gate `release` and `_gc` use - so an
         unproven pid is still never signalled. Park holds DISK, never MEMORY.
         Doing this before the pid is cleared is not an ordering nicety: the pid
         IS the only handle on that process group, so clearing it first would
         strand the server as an unreclaimable orphan and turn `park` into the
         RAM leak this plugin already paid to close.
      4. Only then clear `owner.pid`/`owner.pid_started` and stamp
         `parked_at` + `park_ttl_s` + `parked_boot_id`.
    `db_name`, `ports` and `drop_on_release` are deliberately untouched: the
    database, the filestore and the port reservation are exactly what park
    exists to keep, and the eventual fate of the database at final `release` is
    not park's business to change.

    But it IS park's business to REPORT that fate, which is why the emissions
    below carry `ALLOC_DROP_ON_RELEASE` and a `drop_on_release=true` lease also
    gets an explicit stderr line. Park DEFERS a throwaway database, it does not
    make it durable: the drop still fires at the final `release` (and in `_gc`),
    so a caller that parked in order to SAVE a database it spent minutes
    building gets exactly what it asked for now and loses it later - with no
    signal in between unless park emits one. `drop_on_release` is written ONCE,
    by `cmd_acquire`, and no command mutates it afterwards, so there is no
    "convert it to durable" step to point at either; naming the surviving value
    here is the whole intervention. Do NOT trade this report for a mutation, and
    do NOT turn it into a mode-gated refusal: the isolated running lease park
    exists to suspend IS the `ephemeral` one (`persist: exclusive-running` maps
    onto allocator `ephemeral` - docs/reference/INSTANCE-ALLOCATION-MODES.md
    §5), so refusing that mode would refuse park's only intended client.
    """
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py park <token> [--park-ttl <s>]\n")
        return 2
    try:
        park_ttl = int(opts.get("park_ttl") or DEFAULT_PARK_TTL_S)
    except (TypeError, ValueError):
        sys.stderr.write("allocator: --park-ttl must be an integer number of seconds.\n")
        return 2
    with _locked():
        reg = _read_registry()
        target = None
        for lease in reg["leases"]:
            if lease.get("token") == token:
                target = lease
                break
        if target is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} to park.\n")
            return 1
        if target.get("mode") == "shared":
            sys.stderr.write(
                "allocator: REFUSING to park the `shared` lease on database {db!r}. The shared "
                "render target is the single answer `query --series {series}` gives for a series, "
                "and it is already immune to the owner-pid arms - a parked twin would make that "
                "lookup two-valued and protect nothing. Release it when the render server is "
                "genuinely finished with.\n".format(
                    db=target.get("db_name"), series=target.get("series"))
            )
            return 3
        if (target.get("owner") or {}).get("pid") is None:
            sys.stderr.write(
                "allocator: REFUSING to park the lease on database {db!r} - it records no owner "
                "pid, so it is not RUNNING: there is no server process to stop and nothing to "
                "resume into. (An already-parked lease lands here too, because park cleared its "
                "pid; use `resume <token> --pid <server_pid>` to bring it back, or `release` to "
                "finish with it.)\n".format(db=target.get("db_name"))
            )
            return 4
        # Park holds DISK, never MEMORY - stop the group BEFORE the pid that
        # names it is cleared.
        _stop_owner_group_if_local(target)
        owner = target.setdefault("owner", {})
        owner["pid"] = None
        owner["pid_started"] = None
        target["parked_at"] = _now()
        target["park_ttl_s"] = park_ttl
        boot = _boot_id()
        if boot:
            target["parked_boot_id"] = boot
        else:
            # Absent, not empty: `_condemn_reason` compares only when BOTH sides
            # carry a value, so an absent key degrades to the plain budget
            # comparison instead of reading as a mismatch.
            target.pop("parked_boot_id", None)
        _write_registry(reg)
    _emit("ALLOC_TOKEN", token)
    _emit("ALLOC_PARKED_AT", target["parked_at"])
    _emit("ALLOC_PARK_TTL_S", park_ttl)
    _emit("ALLOC_DB_NAME", target.get("db_name", ""))
    _emit("ALLOC_PORTS", target.get("ports", []))
    # The fate park deliberately did NOT change, reported at the one moment a
    # caller forms a belief about it (see the docstring).
    parked_drops = bool(target.get("drop_on_release"))
    _emit("ALLOC_DROP_ON_RELEASE", "true" if parked_drops else "false")
    if parked_drops:
        sys.stderr.write(
            "allocator: PARKED, and this lease still carries drop_on_release=true - so "
            "`release {token}` WILL DROP database {db!r}, and so will `gc` once the park "
            "budget lapses. Park DEFERS that drop, it does not cancel it: the database, "
            "the filestore and the ports survive the park itself. Nothing mutates "
            "drop_on_release after acquire, so if this database must outlive its lease it "
            "is the ACQUIRE that has to change (`--mode` decides the fate - see "
            "docs/reference/INSTANCE-ALLOCATION-MODES.md section 5), not this park.\n".format(
                token=token, db=target.get("db_name", ""))
        )
    return 0


def _live_owner_pid(lease):
    """The lease's own server pid when one is recorded, on THIS host, and alive.

    None otherwise - which covers every shape that leaves the lease FREE for a
    fresh pid: no pid recorded, a dead pid, a non-integer, or a pid recorded on
    another host (an integer means nothing off-host, so it can never be read as
    "somebody is running this lease here"). That asymmetry is the point: this
    answers only the question "is a live server already holding this lease on
    this host", and it must answer NO whenever it cannot answer YES with proof.
    """
    owner = lease.get("owner") or {}
    host = owner.get("host", "")
    if host and host != _host():
        return None
    try:
        pid = int(owner.get("pid"))
    except (TypeError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def cmd_resume(opts):
    """The atomic PARKED -> RUNNING compare-and-set. One lock, one decision.

    Every step below runs inside ONE `_locked()` registry hold, which is what
    makes two agents racing to resume the same parked lease safe BY
    CONSTRUCTION rather than by timing: the first caller finds `parked_at`
    present and clears it; the second finds the lease already RUNNING under the
    winner's live pid and is refused with exit 6, which tells its caller to STOP
    the server it just launched rather than bind over the winner.

      1. The lease must exist (exit 1) and must BE parked. A lease that is not
         parked splits into two OPPOSITE remedies, and one exit code for both is
         how a racing loser silently stole the winner's lease: NOT parked and no
         live same-host owner pid is the ordinary first launch (exit 3, and
         `50-instance-spinup.sh`'s `_bind_exclusive` branches on exactly that
         code to fall back to `bind`); NOT parked because a LIVE same-host server
         already holds it is the race case (exit 6, never a `bind`).
      2. The database must not have been dropped underneath the park (exit 5),
         probed with the same `_db_present` helper `release` uses. PROVABLY
         absent refuses and names `release` as the correct next step - resuming
         would launch a server against a database that no longer exists. "Could
         not look" (None) is NOT "absent" and does not refuse: stranding a
         resumable instance on an unanswered probe would be the worse mistake,
         and a wrong guess here is recoverable while a refusal is not.
      3. The named pid must be alive on THIS host and CORROBORATED as this
         lease's own server by `_ownership_proof` (exit 4). Park cleared
         `owner.pid_started`, so that ladder's fingerprint rung has nothing to
         match and the proof necessarily comes from an independent observation -
         in practice the command-line rung, read from `/proc/<pid>/cmdline`
         (never `ps -o args=`, which procps truncates to 80 columns wherever it
         cannot determine a width - a CI runner, a container - silently cutting
         the corroborating tokens off a long command line). This is what stops a
         caller binding a pid it did not spawn onto a lease it does not own.
      4. DELETE `parked_at`, `park_ttl_s` and `parked_boot_id`, then write
         `owner.pid`/`owner.pid_started` and a fresh heartbeat.

    Step 4's DELETE is the non-negotiable half. A resume that left `parked_at`
    behind would hand a live, healthy server a park budget as its only
    governor: `_condemn_reason`'s park arm would return CONDEMN_PARK_EXPIRED the
    moment that budget lapsed, `_gc` would stop the group and drop the database
    under a running instance, and the SubagentStop teardown gate's parked
    exemption would go on exempting that live lease forever - reopening the RAM
    leak. Both harms, from one missing `del`.
    """
    token = opts.get("token")
    pid = opts.get("pid")
    if not token or not pid:
        sys.stderr.write("Usage: allocator.py resume <token> --pid <server_pid>\n")
        return 2
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        sys.stderr.write("allocator: --pid must be an integer process id.\n")
        return 2
    with _locked():
        reg = _read_registry()
        target = None
        for lease in reg["leases"]:
            if lease.get("token") == token:
                target = lease
                break
        if target is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} to resume.\n")
            return 1
        if target.get("parked_at") is None:
            holder = _live_owner_pid(target)
            if holder is not None and holder != pid:
                sys.stderr.write(
                    "allocator: REFUSING to resume the lease on database {db!r} with pid {pid} - "
                    "it is NOT parked and pid {holder} is ALREADY running as its server on this "
                    "host. Another caller resumed it first; binding your pid here would take the "
                    "lease off the server that actually holds this database and port. STOP the "
                    "server you just launched - it is a second process on this lease's port - and "
                    "attach to the running one instead.\n".format(
                        db=target.get("db_name"), pid=pid, holder=holder)
                )
                return 6
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - it is NOT parked, "
                "and no live server holds it either. This is the ordinary first launch: bind the "
                "pid with `bind <token> --pid <server_pid>` instead.\n".format(
                    db=target.get("db_name"))
            )
            return 3
        present = _db_present(target, opts.get("instances"))
        if present is False:
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - that database is "
                "provably GONE from its cluster (dropped outside the allocator while the lease "
                "was parked). There is nothing left to resume into; `release {token}` cleans the "
                "lease and its filestore up correctly.\n".format(
                    db=target.get("db_name"), token=token)
            )
            return 5
        owner_host = (target.get("owner") or {}).get("host", "")
        if owner_host and owner_host != _host():
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - it was parked on "
                "host {owner_host!r} and this is {here!r}. A pid integer means nothing off-host, "
                "and that lease's database may live on another cluster entirely.\n".format(
                    db=target.get("db_name"), owner_host=owner_host, here=_host())
            )
            return 4
        if not _pid_alive(pid):
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} with pid {pid} - that "
                "pid is not a live process on this host, so it cannot be the server this lease is "
                "resuming into.\n".format(db=target.get("db_name"), pid=pid)
            )
            return 4
        proof, detail = _ownership_proof(target, pid)
        if proof is None:
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} with pid {pid} - "
                "ownership is NOT proven: {detail}. A resume writes that pid onto the lease, so "
                "release/gc would later signal its whole process GROUP; naming a pid this lease "
                "did not spawn is how an unrelated session gets killed.\n".format(
                    db=target.get("db_name"), pid=pid, detail=detail)
            )
            return 4
        # The set half of the compare-and-set. The three park keys go together:
        # a survivor of any one of them re-governs a live lease by a park budget.
        target.pop("parked_at", None)
        target.pop("park_ttl_s", None)
        target.pop("parked_boot_id", None)
        target.setdefault("owner", {}).update(_pid_owner_fields(pid))
        target["heartbeat_at"] = _now()
        _write_registry(reg)
    sys.stderr.write(
        "allocator: resumed the lease on database {db!r} onto pid {pid} - ownership PROVEN by "
        "{proof}: {detail}. The park budget is cleared; this lease is judged by the owner-pid "
        "arms again.\n".format(db=target.get("db_name"), pid=pid, proof=proof, detail=detail)
    )
    _emit("ALLOC_TOKEN", token)
    _emit("ALLOC_DB_NAME", target.get("db_name", ""))
    _emit("ALLOC_PORTS", target.get("ports", []))
    return 0


def cmd_gc(opts):
    with _locked():
        reg = _read_registry()
        reclaimed = _gc(reg, "gc", opts.get("instances"),
                        opts.get("run_id") or opts.get("session", ""))
        _write_registry(reg)
    # The explicit verb keeps its long-standing PROTOCOL output byte-for-byte (a
    # consumer evals it): one ALLOC_RECLAIMED= line per lease plus the count. The
    # per-lease account of WHY each one was condemned went to stderr + the evidence
    # log as it happened, exactly as it now does for the implicit acquire passes.
    for rec in reclaimed:
        _emit("ALLOC_RECLAIMED", rec.get("token", ""))
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


def _odoo_db_query(cluster, subcommand, *extra):
    """(rc, stdout): run one read-only odoo_db.py query under the cluster's own
    declared interpreter. rc != 0 means "could not answer" - the caller decides
    what that means for ITS question, and must never read it as a factual answer.

    Every question this command asks Postgres is a plain SELECT, so it goes
    through the interpreter the catalog already declares (psycopg2 via Odoo's own
    connection layer) rather than a client binary. A host with the cluster in a
    container and no libpq client installed is therefore fully served - the shape
    that used to make reap-orphans a silent no-op exactly where its orphans were.
    """
    venv_python = cluster.get("python", "")
    if not venv_python or not os.path.isfile(_ODOO_DB_PY):
        return 1, ""
    cmd = [venv_python, _ODOO_DB_PY, subcommand, *extra,
           "--db-host", cluster.get("host", "localhost"),
           "--db-user", cluster.get("user", "odoo")]
    if cluster.get("odoo_root"):
        cmd += ["--odoo-root", cluster["odoo_root"]]
    if cluster.get("port"):
        cmd += ["--db-port", str(cluster["port"])]
    # The password travels in the ENVIRONMENT (odoo_db.py reads ODOO_PG_PASSWORD),
    # never on argv where `ps` exposes it.
    # BOUNDED: these are read-only PROBES, and an unreachable cluster blocks
    # inside libpq with no connect timeout - an unbounded sweep would hang.
    rc, out, _ = _run(cmd, timeout=_probe_timeout_s())
    return rc, out


def _list_cluster_databases(cluster):
    """Non-template datnames on this cluster, or None on ANY failure (no declared
    `python`, a venv that cannot import odoo, connection refused, auth failure).
    None means "could not enumerate" - NEVER conflated with an empty list, so a
    cluster this process cannot currently reach is skipped, not silently treated
    as having zero orphans."""
    rc, out = _odoo_db_query(cluster, "list-databases")
    if rc != 0:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _db_age_s(cluster, db_name):
    """Best-effort DB age in seconds via pg_stat_file's mtime on PG_VERSION -
    the same proxy a human operator uses to eyeball this by hand, since
    Postgres itself records no database creation time. Returns None on ANY
    failure (pg_stat_file needs elevated privilege on many Postgres builds;
    a connection error; a db that vanished between enumeration and this call) -
    callers MUST treat None as unknown, never as "0 / just created"."""
    rc, out = _odoo_db_query(cluster, "db-age-s", db_name)
    out = out.strip()
    if rc != 0 or not out:
        return None
    try:
        return float(out)
    except ValueError:
        return None


def _db_size_bytes(cluster, db_name):
    """Best-effort size via pg_database_size; None on any failure. Reporting-
    only - it never gates the reap decision."""
    rc, out = _odoo_db_query(cluster, "db-size-bytes", db_name)
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
    # Postgres cluster is queried once, not once per declared instance. The
    # queries and the drop both run through the catalog ITEM's declared facts
    # (`python`, `odoo_root`, `db_run_mode`, `db_container`), so a lease-free DB
    # is reachable here even though no lease exists to carry them. The FIRST item
    # declaring a `python` for a cluster wins - two instances on one cluster are
    # two interpreters for the same questions, and either answers identically.
    clusters = {}
    for it in items:
        key = (it.get("db_host", "localhost"), it.get("db_user", "odoo"), it.get("db_port", ""))
        entry = clusters.setdefault(key, {
            "host": key[0], "user": key[1], "port": key[2],
            "python": "", "odoo_root": "", "db_run_mode": "", "db_container": "",
        })
        if not entry["python"] and it.get("python"):
            entry["python"] = it.get("python", "")
            entry["odoo_root"] = it.get("odoo_root", "")
        if not entry["db_run_mode"] and it.get("db_run_mode"):
            entry["db_run_mode"] = it.get("db_run_mode", "")
            entry["db_container"] = it.get("db_container", "")

    all_candidates, all_skipped, unreachable = [], [], []
    for cluster in clusters.values():
        host, user, port = cluster["host"], cluster["user"], cluster["port"]
        names = _list_cluster_databases(cluster)
        if names is None:
            unreachable.append(f"{user}@{host}:{port or 'default'}")
            continue
        dbs = []
        for name in names:
            if not _is_ephemeral_shaped(name, prefixes):
                continue  # cheap pre-filter before any per-db round-trip
            if name in leased_names:
                continue
            dbs.append({
                "name": name,
                "age_s": _db_age_s(cluster, name),
                "size_bytes": _db_size_bytes(cluster, name),
                "host": host, "user": user, "port": port,
                "db_run_mode": cluster["db_run_mode"],
                "db_container": cluster["db_container"],
            })
        cands, skipped = _reap_candidates(dbs, leased_names, prefixes, min_age_s)
        all_candidates.extend(cands)
        all_skipped.extend(skipped)

    for cluster_label in unreachable:
        sys.stderr.write(
            "allocator: reap-orphans could not reach {c}; skipped. The enumeration runs "
            "through the instance's declared `python` (+ `odoo_root`) - declare them via "
            "45-venv.sh, or start the cluster.\n".format(c=cluster_label)
        )

    for name, reason in all_skipped:
        _emit("REAP_SKIPPED", f"{name}: {reason}")

    dropped, failed = [], []
    for db in all_candidates:
        age_h = (db["age_s"] or 0) / 7200
        size_mb = (db["size_bytes"] or 0) / (1024 * 1024)
        _emit("REAP_CANDIDATE", f"{db['name']} age_h={age_h:.1f} size_mb={size_mb:.1f}")
        if yes:
            if _dropdb(db["host"], db["user"], db["name"], db["port"],
                       db.get("db_run_mode", ""), db.get("db_container", "")):
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


def cmd_db_preflight(opts):
    """Read-only: can Odoo AUTHENTICATE, and may the role CREATE DATABASE?

    Both facts, in one call, with AUTHENTICATION evaluated FIRST - the ordering is
    the point. A capability answer describes a role; the authentication answer
    describes the connection every build opens. Emitting `CREATEDB=true` beside a
    proven refusal is the contradiction a probe over a client surface used to
    produce, so the capability ladder is never even reached once the connection is
    provably refused.

    Emits DB_AUTH / DB_AUTH_WHY / CREATEDB / CREATEDB_WHY. Exits 0 both fine,
    6 CREATEDB positively false, 7 CREATEDB undeterminable, 8 authentication
    refused, 9 cluster unreachable. Writes NO lease.
    """
    path = resolve_instances_path(opts.get("instances"))
    series = opts.get("series", "")
    profile = opts.get("profile", "")
    inst, _items = _resolve_instance(path, series, profile=profile or None)
    if inst is None:
        sys.stderr.write(f"allocator: no instance for series {series!r} in {path}.\n")
        return 1
    host = inst.get("db_host", "localhost")
    user = inst.get("db_user", "odoo")
    port = inst.get("db_port", "")

    auth_state, auth_why = _db_auth(inst, host, user, port)
    _emit("DB_AUTH", auth_state)
    _emit("DB_AUTH_WHY", auth_why)
    if auth_state in ("denied", "unreachable"):
        return EXIT_AUTH_DENIED if auth_state == "denied" else EXIT_UNREACHABLE

    verdict, why = _can_createdb(inst, host, user, port)
    if isinstance(verdict, _ConnBlocked):
        # Route 1 saw the connection fail after the preflight said otherwise (a
        # cluster that went away in between, or a preflight that could not run).
        # The connection verdict still wins over any client surface.
        _emit("CREATEDB", "undeterminable")
        _emit("CREATEDB_WHY", why)
        return verdict.exit_code
    if verdict is True:
        _emit("CREATEDB", "true")
        return 0
    if verdict is False:
        _emit("CREATEDB", "false")
        return 6
    _emit("CREATEDB", "undeterminable")
    _emit("CREATEDB_WHY", why)
    return 7


def cmd_can_createdb(opts):
    """Read-only: may this instance's role CREATE DATABASE?

    The SAME ladder `acquire --mode ephemeral` gates on (`_can_createdb`), exposed
    so a reporting caller never has to re-implement it. The setup-time report used
    to invoke odoo_db.py directly, which duplicated route 1 in shell and could not
    reach route 2 at all - so a compose-run instance got no answer from the very
    command whose job is to say whether isolation is available.

    Exits mirror acquire's: 0 = true, 6 = positively false, 7 = undeterminable.
    Writes NO lease - it is a question, not an allocation.
    """
    path = resolve_instances_path(opts.get("instances"))
    series = opts.get("series", "")
    profile = opts.get("profile", "")
    inst, _items = _resolve_instance(path, series, profile=profile or None)
    if inst is None:
        sys.stderr.write(f"allocator: no instance for series {series!r} in {path}.\n")
        return 1
    verdict, why = _can_createdb(
        inst, inst.get("db_host", "localhost"), inst.get("db_user", "odoo"),
        inst.get("db_port", ""))
    if isinstance(verdict, _ConnBlocked):
        # The capability was never answered: the connection Odoo itself opens
        # reported a refusal, and no client surface may overrule that. Reported as
        # undeterminable with the connection exit, so this narrow question can
        # never contradict `db-preflight`.
        _emit("CREATEDB", "undeterminable")
        _emit("CREATEDB_WHY", why)
        return verdict.exit_code
    if verdict is True:
        _emit("CREATEDB", "true")
        return 0
    if verdict is False:
        _emit("CREATEDB", "false")
        return 6
    _emit("CREATEDB", "undeterminable")
    _emit("CREATEDB_WHY", why)
    return 7


def _emit_parked(lease, attached_from=""):
    _emit("ALLOC_TOKEN", lease.get("token", ""))
    _emit("ALLOC_MODE", lease.get("mode", ""))
    _emit("ALLOC_DB_NAME", lease.get("db_name", ""))
    _emit("ALLOC_PORTS", lease.get("ports", []))
    _emit("ALLOC_PARKED_AT", lease.get("parked_at", ""))
    if attached_from:
        _emit("ALLOC_ATTACHED_FROM_RUN", attached_from)


def _query_parked(reg, series, run_id, force_attach, instances_path=None):
    """Rung order for `query --state parked`, and the reasoning behind it.

    A parked lease has NO live owner BY CONSTRUCTION - park stopped the process
    group and cleared the pid - so the ownership objection that makes a RUNNING
    lease private does not apply to it. That is why a parked lease is HOST-and-
    SERIES scoped rather than run-scoped: gating the cross-session case behind a
    flag would leave the very complaint park exists to answer (instances get
    destroyed and rebuilt between sessions) half-answered.

      1. This run's OWN parked lease -> return it silently. Nothing was
         inherited; there is nothing to report.
      2. Another run's parked lease ON THIS HOST -> return it WITH the owning
         run named (ALLOC_ATTACHED_FROM_RUN), so the residual risk - inheriting
         another run's data state - is SURFACED rather than gated. Naming the
         owner in the output beats a flag a caller learns to pass reflexively.
      3. A parked lease on a DIFFERENT host -> only with --force-attach. This is
         the one genuinely unsafe case: the database may live on a cluster this
         host cannot reach at all, so it is a decision, not a default.
    A lease its own budget has already condemned is skipped - offering a row gc
    is about to reclaim would hand the caller a database that is about to vanish.

    THE PRE-LAUNCH DB PROBE lives here, on rungs 1 and 2, and this is the ONLY
    place it can live: `resume` needs a live pid to corroborate ownership, so it
    necessarily runs AFTER the server is launched, while THIS command runs before
    the caller has coordinates to launch anything with. A lease whose database is
    PROVABLY gone is therefore skipped here rather than offered - that is what
    makes "no server is ever started against a database that is gone" true for
    the discovery path. "Could not look" (None) is NOT "absent" and is offered:
    stranding a resumable instance on an unanswered probe is the worse error, and
    `resume`'s own probe is the second net under it. Rung 3 (--force-attach,
    off-host) is offered UNPROBED on purpose: that database lives on another
    host's cluster, so a probe run here would answer about the wrong cluster.
    """
    parked = [
        lz for lz in reg.get("leases", [])
        if lz.get("parked_at") is not None
        and lz.get("series") == series
        and _condemn_reason(lz) is None
    ]
    here = _host()
    # SAME HOST gates rungs 1 and 2 alike - `run_id` only decides SILENT vs
    # REPORTED, it never overrides the host check. A row recorded on another host
    # names a database on another cluster whatever run owns it, so an own-run
    # match off-host is still the --force-attach case below.
    local = [lz for lz in parked if (lz.get("owner") or {}).get("host") == here]
    gone = set()

    def _offer(lease, attached_from=""):
        """Emit this lease's coordinates unless its database is provably gone."""
        token = lease.get("token", "")
        if token in gone:
            return False
        if _db_present(lease, instances_path) is False:
            gone.add(token)
            sys.stderr.write(
                "allocator: SKIPPING the parked lease on database {db!r} - that database is "
                "provably GONE from its cluster (dropped outside the allocator while the lease "
                "was parked), so there is nothing to resume into and NOTHING was launched. "
                "`release {token}` cleans the lease and its filestore up correctly; then build a "
                "fresh instance.\n".format(db=lease.get("db_name"), token=token)
            )
            return False
        _emit_parked(lease, attached_from=attached_from)
        return True

    for lease in local:
        if run_id and (lease.get("owner") or {}).get("run_id") == run_id:
            if _offer(lease):
                return 0
    for lease in local:
        if _offer(lease, attached_from=(lease.get("owner") or {}).get("run_id", "")):
            return 0
    if force_attach:
        for lease in parked:
            # A local row already PROVEN gone stays skipped: --force-attach widens
            # the HOST scope, it does not overrule a database that is not there.
            if lease.get("token", "") in gone:
                continue
            _emit_parked(lease, attached_from=(lease.get("owner") or {}).get("run_id", ""))
            return 0
    return 1


def cmd_query(opts):
    """Read-only cross-session discovery.

    DEFAULT (no `--state`): the live `shared` lease for a series (the running
    render server's actual port + db), or exit 1 if none - byte-for-byte what it
    always emitted, so no existing caller moves.

    `--state parked`: the resumable PARKED lease for that series instead, so a
    returning agent can find the instance an earlier dispatch suspended rather
    than build a new one. See `_query_parked` for the rung order.

    Does not mutate the registry; a condemned row is simply skipped (gc reclaims
    it).
    """
    series = opts.get("series", "")
    reg = _read_registry()
    state = (opts.get("state") or "").strip().lower()
    if state == "parked":
        return _query_parked(
            reg, series, opts.get("run_id") or opts.get("session", ""),
            bool(opts.get("force_attach")), opts.get("instances"),
        )
    if state:
        sys.stderr.write(
            f"allocator: unknown --state {state!r}. The only value is `parked`; omit --state for "
            "the default live-shared lookup.\n"
        )
        return 2
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
    "--park-ttl": "park_ttl", "--state": "state",
}
_BOOL_KEYS = {
    "--no-create": "no_create", "--force": "force", "--show-tokens": "show_tokens",
    "--yes": "yes", "--force-forget": "force_forget", "--force-attach": "force_attach",
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
    if cmd == "park":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_park(opts)
    if cmd == "resume":
        opts.setdefault("token", pos[0] if pos else None)
        return cmd_resume(opts)
    if cmd == "gc":
        return cmd_gc(opts)
    if cmd == "reap-orphans":
        return cmd_reap_orphans(opts)
    if cmd == "list":
        return cmd_list(opts)
    if cmd == "query":
        return cmd_query(opts)
    if cmd == "can-createdb":
        return cmd_can_createdb(opts)
    if cmd == "db-preflight":
        return cmd_db_preflight(opts)
    if cmd == "assert-droppable":
        return cmd_assert_droppable(opts)
    sys.stderr.write(
        f"Unknown subcommand: {cmd!r}. "
        "Use acquire|release|bind|park|resume|heartbeat|gc|reap-orphans|list|query|"
        "assert-droppable|can-createdb|db-preflight.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
