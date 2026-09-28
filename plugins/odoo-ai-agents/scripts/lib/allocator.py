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
    leases.json      - the single registry (atomic read-modify-write under flock),
                       schema_version 3; older rows are read leniently
    registry.lock    - the fcntl.flock file guarding the critical section

CROSS-VERSION: the registry is machine-global, and a session keeps running the
allocator of the plugin version it started with - an OLDER allocator reads, and
on every acquire SWEEPS, the rows this one writes. So every row stays safe under
the pre-anchor (schema 2) reader: `owner.pid_started` keeps that reader's exact
shape (bare `ps -o lstart=` in the ambient TZ, compared with `==`) while the
TZ-free fingerprint lives in `owner.pid_fp` (+ `owner.pid_fp_pid`, the pid it was
measured on - see PID_OWNER_KEYS); `ttl_s` is at least 24h on a row without an
explicit --ttl; and `heartbeat` refreshes `heartbeat_at`, the only stamp that
reader's TTL arm looks at. That reader also knows nothing of the session anchor:
a bound server pid that died (or was recycled) under a still-live session is
`owner-pid-dead` to it, and its acquire sweep would drop the database. So every
locked write (`heartbeat` - including `heartbeat --session mine`, which the
odoo-local MCP server runs every 10 minutes - `acquire`, `bind`, `gc`, `adopt`)
SHEDS such a pid from every row of the machine (`_shed_gone_server`): the pid
keys are cleared and `heartbeat_at` refreshed, so the older reader's TTL arm
protects the row while this allocator still protects it by its anchor. RESIDUAL
WINDOW: between the server dying and the next such write (at most one heartbeat
interval while any session on the machine runs the MCP server; unbounded on a
machine where only the CLI is used and nothing new-version writes) the dead pid
is still on the row, and an older allocator's acquire in that window reclaims
it. Only a long-lived server pid is ever recorded (`acquire --pid` / `bind`
from the serve path, after `kill -0`; build pids never are), so the window opens
only when a served instance dies unexpectedly. A row with an explicit --ttl
shorter than the heartbeat interval can still lapse under the older reader's
TTL arm once shed. Guard: tests/test_allocator_cross_version.py.

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
                 drop_on_release is ALWAYS False (a reclaim removes a dead-server
                 row but NEVER drops the declared DB), and the actual bound --port
                 + the long-lived server --pid are recorded so `query` can find it.
                 A shared row is judged by its SERVER pid only - it is
                 cross-session by design, so no session anchor protects it.

LIVENESS - what protects a lease, and what condemns it (`_judge`, in order):
    1. PARKED: its own park budget (default 48h, `park --park-ttl`); a reboot
       while parked does not consume it.
    2. SESSION ANCHOR (not `shared`): every lease records the acquiring agent
       session's long-lived process (`owner.session`, see session_anchor.py:
       ODOO_AI_SESSION_ANCHOR, else CLAUDE_PID, else a claude/codex/gemini
       ancestor). While that process lives the lease is PROTECTED - whatever
       its server pid and TTL say. Once it is provably dead the lease is
       `owner-session-ended`, unless the caller is the same session resumed
       (same CLAUDE_CODE_SESSION_ID), which re-anchors it. The automatic paths
       wait ANCHOR_GRACE_S (30 min) after the session's last touch.
    3. LEGACY / UNANCHORED: a dead server pid on this host condemns
       (`owner-pid-dead`), a fingerprint proving pid recycling condemns
       (`owner-pid-recycled`), a matching fingerprint protects; otherwise
       liveness is unprovable and only an EXPLICIT `gc` (scope all) may apply
       the TTL arm (`ttl-expired-liveness-unprovable`): the lease's explicit
       --ttl, or at least 24h. The automatic paths never do.
    Pid fingerprints are timezone- and locale-independent
    (`proc:<boot_id>:<starttime>` / `ps:<UTC lstart>`, `owner.pid_fp`, trusted
    while `owner.pid_fp_pid` equals `owner.pid`); otherwise `owner.pid_started`
    is used - a LEGACY bare-lstart fingerprint is compared in the local zone and
    UTC and never counts as a mismatch.

RECLAMATION - who may destroy what:
    acquire  reclaims NOTHING implicitly. Only when it cannot otherwise be
             served (port pool exhausted, or an exclusive conflict) does it
             take CAPACITY from leases whose owner is PROVABLY gone
             (owner-session-ended past the grace window, owner-pid-dead,
             owner-pid-recycled; never TTL, parked or shared): it stops their
             server group and frees their ports, marking the row `orphaned`
             (an exclusive holder's row is deleted - it never drops anything).
             It NEVER drops a database. Recorded as by_verb=acquire-capacity,
             dropped_db=false. When that reclaim stopped a server, the freed
             ports are re-picked for up to PORT_FREE_WAIT_S before giving up.
             Still exhausted -> exit 4 naming the holders; with NO holder at all
             it carries fields.reason `ports-busy-outside-registry` and that
             reason's own remedy (ERROR_CODES). Ports are probed the way Odoo
             binds them (SO_REUSEADDR + bind + listen), so a port in TIME_WAIT
             is usable and a LISTENING one is not.
    gc       the only verb that drops a lease it does not own: stop group ->
             drop through Odoo -> delete row. EXCEPT a lease that was resumed or
             adopted out of a deliberate park (`owner.return_to_park`): when its
             new owner is provably gone (session ended, server dead/recycled) gc
             PARKS it again - stops the group, keeps the database, the filestore
             and the ports, restores the park budget it had
             (`owner.return_park_ttl_s`) - instead of dropping it.
    release  the owner's teardown: the same stop -> drop -> delete.
    All three are TWO-PHASE on one primitive: the rows are marked `reclaiming`
    under the registry lock, the servers are stopped (and, for gc/release, the
    databases dropped) OUTSIDE it, and the rows are settled under the lock
    again - so no stop or drop ever stalls another session's acquire/list. A
    marked row keeps its ports until settled; a marker whose process died is
    ignored, so the next gc/release/acquire retakes the row.
    Every reclamation is reported per lease on STDERR (never stdout, which is
    the eval protocol) and appended to $ODOO_AI_HOME/logs/allocator-reclaimed.jsonl.

CLI (every verb also takes --format json, see OUTPUT):
    allocator.py acquire --series <X.Y> --mode <readonly|ephemeral|exclusive|shared>
                 [--run-id <id> | --allow-unowned]
                 [--ports N] [--port P] [--ttl <s>] [--db-name <name>] [--pid <pid>]
                 [--profile <P>] [--no-create] [--instances <path>]
                 [--addons-path-override <csv-or-colon-paths>]
                 # --series is REQUIRED (exit 2 SERIES_REQUIRED; nothing is picked
                 # for you). --run-id is the canonical ownership key (--session is
                 # a back-compat alias); without it acquire exits 10 unless
                 # --allow-unowned states deliberately that the lease has no owner
                 # OR --mode is readonly, which is lease-free and exempt from both.
                 # Echoes ALLOC_TOKEN, ALLOC_MODE, ALLOC_DB_NAME, ALLOC_PORTS,
                 # ALLOC_RUN_ID, ALLOC_PYTHON, ALLOC_ADDONS_PATH, ALLOC_DB_HOST,
                 # ALLOC_DB_USER, ALLOC_DB_PORT, ALLOC_SERIES, ALLOC_PROFILE
                 # (+ ALLOC_ATTACHED for shared). Records `profile` (the RESOLVED
                 # catalog profile, "" when unprofiled - `list` returns it),
                 # owner.session (the caller's anchor), owner.via ("mcp" when
                 # ODOO_AI_VIA=mcp, else "cli") and owner.acquired_by
                 # (ODOO_AI_CALLER_AGENT_ID/_TYPE). Every acquire that writes a
                 # lease (not readonly) also writes ONE line to STDERR:
                 #   allocator: acquired lease <full-token> run_id=<id>
                 # - it reaches the caller's transcript even when stdout is
                 # consumed by `eval "$(...)"`; stdout is unchanged.
                 # With NO --addons-path-override, acquire refuses (exit 5) instead
                 # of silently defaulting ALLOC_ADDONS_PATH when the caller's cwd is
                 # a git worktree of the SAME repo as a catalog addons_path entry
                 # but at a DIFFERENT checkout - the false-green shape where a fix
                 # living in a worktree gets verified against the principal
                 # checkout's (pre-fix) code instead.
    allocator.py query --series <X.Y> [--state parked] [--run-id <id>] [--force-attach]
                 # DEFAULT (no --state): the live shared render server for a
                 # series, if any (exit 1 NOT_FOUND otherwise).
                 # --state parked: the resumable PARKED lease for that series
                 # (ALLOC_TOKEN/ALLOC_MODE/ALLOC_DB_NAME/ALLOC_PORTS/
                 # ALLOC_PARKED_AT). A parked lease has NO live owner by
                 # construction, so it is HOST-and-SERIES scoped: this run's own
                 # parked lease is returned silently; another run's parked lease
                 # on THIS host is returned WITH ALLOC_ATTACHED_FROM_RUN; a parked
                 # lease on a DIFFERENT host needs --force-attach. A same-host row
                 # whose database is PROVABLY gone is SKIPPED, not offered, and
                 # `release <token>` is named. "Could not look" is not "absent"
                 # and is still offered.
    allocator.py can-createdb --series <X.Y> [--profile <P>] [--instances <path>]
                 # read-only: print CREATEDB=true|false|undeterminable (+ CREATEDB_WHY
                 # when undeterminable) and exit 0|6|7 - the SAME ladder and codes
                 # `acquire --mode ephemeral` gates on. Exits 8/9 when the
                 # connection Odoo itself opens is provably refused / the cluster is
                 # absent. Writes NO lease.
    allocator.py db-preflight --series <X.Y> [--profile <P>] [--instances <path>]
                 # read-only: print DB_AUTH=ok|denied|unreachable|unknown +
                 # DB_AUTH_WHY, then CREATEDB + CREATEDB_WHY, and exit 0|6|7|8|9.
                 # DB_AUTH is evaluated FIRST, so CREATEDB=true is never emitted
                 # beside a proven refusal. Writes NO lease.
    allocator.py release <token> --run-id <id> [--force] [--force-forget]
                 [--instances <path>]
                 # a lease that records an owner run is released ONLY by that run
                 # (any other --run-id, AND an absent one, is refused: exit 1
                 # NOT_OWNER); an UNOWNED lease releases on token-possession;
                 # --force overrides loudly (`_ownership_refusal`, shared with
                 # park). Stops the server group, then drops a
                 # throwaway DB through Odoo. A drop that FAILS keeps the lease
                 # (exit 1 DROP_FAILED_KEPT) - the drop surface is re-resolved from
                 # the CURRENT catalog on every attempt, so `45-venv.sh record-env`
                 # repairs an EXISTING lease. A database PROVABLY absent releases
                 # cleanly (ALLOC_FORGOTTEN_DB, exit 0, filestore removed).
                 # --force-forget removes an un-droppable lease and NAMES what was
                 # left behind: ALLOC_ABANDONED_DB (observed present),
                 # ALLOC_FORGOTTEN_DB (provably absent), ALLOC_UNVERIFIED_DB (could
                 # not be confirmed). An unknown token exits 0 (already released)
                 # and emits ALLOC_ALREADY_ABSENT=1; a release that deleted the
                 # row ITSELF emits ALLOC_RELEASED=<token> (both also in JSON
                 # `fields`), so a racing release is told apart from its winner.
                 # A row another gc/release is reclaiming right now: exit 11.
                 # The stop + drop run OUTSIDE the registry lock (the row is
                 # marked `reclaiming` meanwhile and keeps its ports).
    allocator.py assert-droppable --db-name <db> [--run-id <id>] [--force]
                 # read-only: exit 1 if a FRESH lease on <db> is owned by a
                 # DIFFERENT run (DB_HELD_BY_OTHER_RUN) or is UNOWNED
                 # (DB_HELD_UNOWNED); 0 otherwise (own lease, stale lease, no lease,
                 # or --force).
    allocator.py bind <token> --pid <server_pid>
                 # upsert the live server pid (+ its fingerprint, + the caller's
                 # session anchor) onto an EXISTING lease, so release/gc can stop
                 # the whole process GROUP before dropping the DB.
    allocator.py park <token> --run-id <id> [--park-ttl <s>] [--force]
                 # SUSPEND a RUNNING lease without destroying anything it holds.
                 # Ownership is release's rule, checked FIRST under the lock
                 # (`_ownership_refusal`): a lease that records an owner run is
                 # parked ONLY by that run (any other --run-id, AND an absent one,
                 # is refused: exit 1 NOT_OWNER, nothing stopped); an UNOWNED
                 # lease parks on token-possession; --force overrides loudly.
                 # Stops the owner's process GROUP first (park holds DISK, never
                 # MEMORY), clears the recorded server (PID_OWNER_KEYS), and stamps
                 # parked_at + park_ttl_s (default 48h) + parked_boot_id. db_name,
                 # ports and drop_on_release are left untouched. EMITS that
                 # drop_on_release (ALLOC_DROP_ON_RELEASE) and, when true, says on
                 # STDERR that the final `release` still drops that database: park
                 # DEFERS a throwaway, it never makes one durable. Refuses a
                 # `shared` lease (exit 3) and a lease that is not RUNNING (exit 4 -
                 # no owner pid recorded).
    allocator.py resume <token> --pid <server_pid>
                 # The atomic PARKED -> RUNNING compare-and-set, under ONE registry
                 # hold: NOT parked with no live same-host owner is the ordinary
                 # first launch (exit 3 NOT_PARKED - the branch back to `bind`);
                 # NOT parked because a LIVE same-host server already holds it is
                 # the resume RACE (exit 6 - stop the server you just launched);
                 # a database dropped under the park is exit 5 DB_GONE; the named
                 # pid must be alive on this host AND corroborated as this lease's
                 # own server (exit 4 WRONG_HOST / PID_NOT_ALIVE /
                 # OWNERSHIP_UNPROVEN). Then it DELETES parked_at/park_ttl_s/
                 # parked_boot_id and writes the pid, its fingerprints, the
                 # caller's anchor, a fresh heartbeat, and owner.return_to_park +
                 # owner.return_park_ttl_s (the budget it had), so the resuming
                 # session's end parks it again (see RECLAMATION / gc).
    allocator.py heartbeat <token> | heartbeat --session mine
                 # refresh heartbeat_at (and the anchor's seen_at when the caller
                 # is the lease's session); BACKFILL the fingerprints of an older
                 # row when - and only when - ownership of its pid is corroborated
                 # right then (and move a TZ-free value an earlier build wrote into
                 # pid_started over to pid_fp once it is proven to match).
                 # `--session mine` touches every lease of the caller's session in
                 # one registry hold - heartbeat_at included, because an older
                 # allocator judges a pid-less row by that stamp alone.
    allocator.py adopt <token> --run-id <id>
                 # re-anchor a lease onto the CALLER's session (a hand-over inside
                 # one run). Requires the recorded owner run (exit 1 NOT_OWNER),
                 # the same host (exit 4 WRONG_HOST) and an anchored caller (exit 5
                 # NO_ANCHOR). Changes who vouches for liveness, nothing else
                 # (adopting a PARKED lease also sets owner.return_to_park).
                 # Writes `allocator: adopted lease <token> run_id=<id>` to STDERR.
    allocator.py anchor [--print]
                 # print the caller's session anchor, shell-eval-able:
                 # ODOO_AI_SESSION_ANCHOR=<pid>:<fingerprint>, ODOO_AI_SESSION_ID,
                 # ODOO_AI_ANCHOR_SOURCE, ODOO_AI_ANCHOR_STATE. Exit 5 NO_ANCHOR
                 # outside an agent session.
    allocator.py gc [--scope all|dead-sessions|anchor] [--anchor <pid:fingerprint>]
                 [--dry-run] [--force] [--run-id <id>] [--instances <path>]
                 # all (default): every condemn arm, including the TTL arm.
                 # dead-sessions: the automatic semantics - ended sessions past the
                 # grace window, dead/recycled server pids, expired parks; never TTL.
                 # anchor: the running/reserved leases (never parked, never shared)
                 # of ONE session anchor (--anchor, default the caller's own); the
                 # anchor must no longer be alive (exit 3 ANCHOR_ALIVE; --force
                 # overrides; exit 2 ANCHOR_REQUIRED when there is none).
                 # --dry-run: emit ALLOC_WOULD_RECLAIM=<token> per candidate (JSON
                 # candidates carry `action`: reclaim|park) and change nothing.
                 # Otherwise ALLOC_RECLAIMED=<token> per lease plus a `# reclaimed N
                 # stale lease(s)` line, and ALLOC_PARKED=<token> (JSON `parked`)
                 # per lease returned to its park.
    allocator.py reap-orphans [--min-age-s <s>] [--yes] [--instances <path>]
                 # lists (default) or drops (--yes) ephemeral-shaped databases
                 # (<prefix>_t_<hex8>, never a named/declared instance) that carry
                 # NO lease reference at all - live or stale - across every declared
                 # cluster: naming shape + zero lease reference + a POSITIVELY
                 # PROVEN age >= --min-age-s (default 48h; an unmeasurable age is
                 # NOT old enough, fail-closed). Emits REAP_CANDIDATE / REAP_SKIPPED
                 # / REAP_DROPPED lines; exit 1 REAP_DROP_FAILED when a drop failed.
    allocator.py list [--show-tokens] [--run-id <id>] [--older-than <s>]
                 [--tokens <t1,t2>] [--session <pid:fingerprint|mine>] [--with-verdict]
                 # the registry as JSON. Tokens are fingerprinted to 8 chars unless
                 # --show-tokens. --tokens matches full tokens or >=8-char prefixes.
                 # --session filters by anchor (`mine` also matches the caller's
                 # session id; any other value is the legacy --run-id alias).
                 # --with-verdict adds `verdict` {state: running|reserved|parked|
                 # orphaned|reclaiming, protected_by: session|server-pid|park|ttl|
                 # none, condemn, condemn_auto, return_to_park, anchor_state,
                 # anchor_alive} - the SSOT a consumer reads instead of re-deriving
                 # liveness. Every row carries `profile`.

Every process signal release/gc/park/acquire-capacity can send goes through ONE
gate (`_stop_owner_group_if_local`): the pid must be on THIS host, alive, AND
PROVEN to belong to the lease - by a matching recorded fingerprint, or
by an independent corroborating observation (an Odoo command line naming this
lease's own database, or the process group listening on a port this lease
reserved). An unproven pid is NEVER signalled and the refusal is reported with
its evidence: pids are recycled, so "alive" alone is equally true of an unrelated
shell whose whole group a GROUP signal would take down.

OUTPUT:
    Default (--format shell): shell-eval-able KEY=VALUE lines (shlex.quote'd) on
    stdout, mirroring instances_io.py's INST_* convention; prose goes to stderr.
    --format json: exactly ONE JSON object on stdout,
        {"ok": bool, "rc": int, "error": {"code": str, "message": str} | null,
         "fields": {...}}
    where `fields` carries the same KEY names with typed values (ALLOC_PORTS is a
    list), repeatable keys as lists (ALLOC_RECLAIMED, ALLOC_WOULD_RECLAIM,
    REAP_*), and structured payloads: `leases` (list), `candidates` /
    `reclaimed` (gc), `holders` (a refused acquire), `touched` (heartbeat),
    `notes` (the `#` comment lines). Every non-zero exit carries a named
    `error.code` from ERROR_CODES (each code always pairs with one exit code);
    a code with a narrower cause adds `fields.reason` + `fields.remedy` (the
    code's `reasons` table). A missing or unreadable instance catalog is
    NO_INSTANCE_CATALOG (exit 1) on every verb that reads it.

acquire exit codes:
    0 acquired as requested (a lease is written)
    1 no instance for that series in the catalog                      NO_INSTANCE
      / no readable catalog at all                                    NO_INSTANCE_CATALOG
    2 usage: unknown --mode / non-integer flag / missing --series     USAGE,
      / invalid --addons-path-override        SERIES_REQUIRED, ADDONS_PATH_OVERRIDE_INVALID
    3 exclusive conflict - the db is already exclusively held         EXCLUSIVE_CONFLICT
    4 port pool exhausted                                             PORT_POOL_EXHAUSTED
    5 addons_path worktree mismatch (pass --addons-path-override)     ADDONS_PATH_WORKTREE_MISMATCH
    6 `ephemeral` REFUSED: the role positively LACKS CREATEDB         NO_CREATEDB
    7 `ephemeral` REFUSED: CREATEDB capability UNDETERMINABLE         CREATEDB_UNDETERMINABLE
    8 REFUSED: Odoo cannot AUTHENTICATE to the cluster                DB_AUTH_DENIED
    9 REFUSED: the cluster did not answer at all                      DB_UNREACHABLE
   10 REFUSED: no --run-id and no --allow-unowned                     RUN_ID_REQUIRED
Every non-zero exit writes NO lease (a capacity reclaim that ran before an exit
3/4 is persisted and reported - it never drops anything).
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
6 and 7 stay distinct because the remedy differs: 6 is fixed by granting the role
CREATEDB, 7 by declaring a working `python` + `odoo_root` (45-venv.sh
record-env), by declaring a `db_run_mode` client surface (the route a
compose-run instance takes - it declares no `python` of its own), or by starting
the cluster.
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
import session_anchor  # noqa: E402  (sibling lib; process identity + session anchor)

DEFAULT_POOL_SIZE = 10
# After acquire's capacity reclaim STOPPED a server holding this pool, the freed
# ports are re-picked every PORT_RETRY_INTERVAL_S for up to PORT_FREE_WAIT_S
# before the pool is reported exhausted: a server that was just SIGTERMed/KILLed
# can still hold its listening socket for a moment.
PORT_FREE_WAIT_S = 5
PORT_RETRY_INTERVAL_S = 0.25
# PORT_POOL_EXHAUSTED's `reason` when NO lease holds a port of the pool (see
# ERROR_CODES): the ports are busy outside the registry.
PORTS_BUSY_OUTSIDE_REGISTRY = "ports-busy-outside-registry"
# The registry's current schema. v3 adds `owner.session` (the session anchor),
# `owner.via`, `owner.acquired_by`, `ttl_explicit`, and the `orphaned` /
# `reclaiming` row markers. Readers stay lenient: a v1/v2 row simply lacks those
# keys and is judged by the legacy arms. There is no bulk migration.
SCHEMA_VERSION = 3
# The TTL arm now governs ONLY a lease whose liveness cannot be proven at all -
# UNANCHORED (no live session on record: CI, a human shell, a row written before
# anchoring existed) AND with no verifiable owner pid - and it is consulted ONLY
# by an explicit `gc` (scope `all`). The automatic paths (`gc --scope
# dead-sessions`, acquire's capacity reclaim) never take it: 44 real reclaims of
# live instances came from exactly this arm, because the runners that hold
# pid-less build leases never heartbeat.
# A row whose ttl_s was not set EXPLICITLY (`acquire --ttl`) is judged against
# at least this floor, so every pre-v3 row that merely carries the old 7200
# default gets the 24h window too; an explicit --ttl is honoured as given.
LEGACY_UNPROVABLE_TTL_S = 24 * 3600
DEFAULT_TTL_S = LEGACY_UNPROVABLE_TTL_S
# How long an anchored lease whose session is PROVABLY dead is still spared by the
# automatic paths, measured from the later of its heartbeat and its anchor's
# `seen_at`. A session that crashed may be resumed (`claude --resume` keeps the
# session id, which re-anchors the lease on its next touch); an explicit `gc`
# (scope `all`) does not wait.
ANCHOR_GRACE_S = 1800
# reap-orphans default minimum PROVABLE age (seconds) before a lease-free
# ephemeral-shaped DB is even proposed as a candidate: 48h. Conservative on
# purpose: a DB that appeared moments ago (a narrow acquire-then-crash race, or a
# lease write still in flight) must never be mistaken for an abandoned orphan just
# because a reap-orphans sweep happened to run at the wrong instant.
DEFAULT_REAP_MIN_AGE_S = 48 * 3600
# How long a PARKED lease keeps its database, filestore and ports with no owner
# process at all: 48h. This is a DISK budget, not a RAM one: `park` stops the
# owner's process group BEFORE it clears the pid, so a parked lease costs no
# memory - only the database and the port reservation. It is deliberately the
# same figure as DEFAULT_REAP_MIN_AGE_S above, the file's other disk-scoped
# budget, so the two "how long may abandoned disk survive" answers do not drift
# apart. Overridable per lease with `park --park-ttl <s>`.
DEFAULT_PARK_TTL_S = DEFAULT_REAP_MIN_AGE_S
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
    reg["schema_version"] = SCHEMA_VERSION
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

    The read itself lives in `session_anchor.boot_id` (the SSOT the pid
    fingerprint scheme shares); this name stays as the park arm's seam.
    """
    return session_anchor.boot_id()


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
    detect pid recycling - delegated to `session_anchor.fingerprint` (the SSOT):
    `proc:<boot_id>:<starttime>` on Linux, else `ps:<lstart>` measured with
    TZ=UTC LC_ALL=C. Both are independent of the caller's timezone and locale;
    the old bare `ps -o lstart=` string was not, so a live server fingerprinted
    under one TZ and re-measured under another read as "recycled" and was
    killed.

    Returns None when the pid is not currently running or nothing could measure
    it - callers MUST treat None as "cannot verify", never as a match or a
    mismatch. Comparisons go through `_fp_verdict`, never `==`: a recorded value
    may be a LEGACY bare lstart, which only `session_anchor.fp_verdict` knows how
    to compare safely. Recorded as `owner.pid_fp`; `owner.pid_started` keeps the
    legacy shape for older allocators (see PID_OWNER_KEYS).
    """
    return session_anchor.fingerprint(pid)


def _fp_verdict(expected, pid):
    """"match" | "mismatch" | "unknown" - the ONE comparison of a recorded
    `pid_started` against the live process (see `session_anchor.fp_verdict`)."""
    return session_anchor.fp_verdict(expected, pid)


def _pid_legacy_fingerprint(pid):
    """The LEGACY bare `ps -o lstart=` of `pid` in the ambient TZ/locale
    (`session_anchor.legacy_lstart`) - the exact shape an OLDER allocator reads
    from `owner.pid_started` and compares with `==`."""
    return session_anchor.legacy_lstart(pid)


# The owner keys that describe the recorded server process. They are written and
# cleared TOGETHER (`_pid_owner_fields`), never one at a time.
#   pid          the server pid
#   pid_started  LEGACY bare `ps -o lstart=` (ambient TZ) - kept in exactly the
#                shape an older allocator sharing this registry compares with
#                `==`; writing anything else there makes that allocator read a
#                live server as "recycled" and reap it (it drops the database of
#                a drop_on_release lease).
#   pid_fp       the TZ- and locale-free fingerprint (`_pid_fingerprint`) this
#                allocator prefers
#   pid_fp_pid   the pid `pid_fp` was measured on. An older allocator's `bind` /
#                `resume` rewrites pid + pid_started and knows nothing of pid_fp,
#                so a pid_fp is trusted only while pid_fp_pid == pid; otherwise
#                the reader falls back to pid_started.
PID_OWNER_KEYS = ("pid", "pid_started", "pid_fp", "pid_fp_pid")


def _pid_owner_fields(pid):
    """{pid, pid_started, pid_fp, pid_fp_pid} (see PID_OWNER_KEYS) for recording
    onto a lease's `owner` at the moment a stable pid is learned (acquire's
    shared/exclusive/ephemeral paths, `bind`, `resume`, the heartbeat backfill).
    Capturing the fingerprints HERE - immediately after the pid is learned, while
    it still names the process we intend to remember - is what makes the later
    liveness check in `_judge` resistant to pid recycling. Every key is None when
    `pid` is falsy (0/""/None): the "no stable pid supplied" case, and what
    `park` writes to clear the recorded server."""
    if not pid:
        return {key: None for key in PID_OWNER_KEYS}
    pid = int(pid)
    fingerprint = _pid_fingerprint(pid)
    return {
        "pid": pid,
        # None (never "") when unmeasurable: an older allocator compares a
        # non-None value with `==`, so an empty string would read as "recycled".
        "pid_started": _pid_legacy_fingerprint(pid) or None,
        "pid_fp": fingerprint,
        "pid_fp_pid": pid if fingerprint else None,
    }


def _recorded_fingerprint(owner, pid):
    """(fingerprint, key) - the fingerprint recorded for the process at `pid`,
    and the owner key it was read from; (None, None) when none is recorded.

    `owner.pid_fp` wins while it was measured on this same pid (`pid_fp_pid`);
    otherwise `owner.pid_started` (legacy bare lstart, or a scheme-prefixed value
    an earlier build of this allocator wrote there) - `_fp_verdict` compares
    either shape safely."""
    owner = owner or {}
    fp = owner.get("pid_fp")
    if fp:
        try:
            same_pid = int(owner.get("pid_fp_pid")) == int(pid)
        except (TypeError, ValueError):
            same_pid = False
        if same_pid:
            return fp, "owner.pid_fp"
    legacy = owner.get("pid_started")
    if legacy:
        return legacy, "owner.pid_started"
    return None, None


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
# A recorded fingerprint (`owner.pid_fp`, else `owner.pid_started` - see
# `_recorded_fingerprint`) settles the question whenever it is present AND
# re-measurable. Two populations are left over:
#   (a) rows written before any fingerprint existed - readers of `leases.json`
#       stay deliberately lenient across SCHEMA_VERSION bumps (there is no bulk
#       migration), so a row carrying `pid` and no fingerprint is a legal,
#       expected shape, not a corrupt one;
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
    expected_fp, fp_key = _recorded_fingerprint(owner, pid)
    if expected_fp is not None:
        verdict = _fp_verdict(expected_fp, pid)
        if verdict == session_anchor.VERDICT_MATCH:
            return "fingerprint", (
                "the process holding that pid still reports the start time recorded "
                f"on the lease ({fp_key}), so it is the very process the "
                "lease named"
            )
        if verdict == session_anchor.VERDICT_MISMATCH:
            return None, (
                "the process holding that pid reports a DIFFERENT start time than the "
                f"lease recorded ({fp_key}), which proves the pid was recycled "
                "onto an unrelated process - this lease's own server already exited"
            )
        unprovable = (
            f"the lease's {fp_key} fingerprint could not be matched just now "
            "(not re-measurable, or a legacy timezone-dependent value that matches "
            "neither the local timezone nor UTC), so the pid cannot be tied to the "
            "recorded process"
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
    PROVEN one - and every later check, including `_judge`'s protect arm and
    the signal path, would then trust it. Stamping only a corroborated pid means
    the value recorded is the leased server's own, which is what makes the cheap
    fingerprint check usable on that row from then on and shrinks the unprovable
    population instead of letting it persist forever.

    Consequence worth naming: a row that gains a fingerprint also gains
    `_judge`'s TTL immunity while that process lives - which is correct, and
    exactly the protection an `acquire --pid`/`bind` row has had all along.
    """
    owner = lease.get("owner") or {}
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
    recorded, _key = _recorded_fingerprint(owner, pid)
    if recorded is not None:
        # A present fingerprint is judged by `_fp_verdict` where it is used and is
        # never overwritten on corroboration alone. The one rewrite: a
        # scheme-prefixed value an earlier build wrote into `pid_started`, which an
        # older allocator compares with `==` and reads as "recycled". A MATCH is
        # the proof that it names this very process, so it moves to `pid_fp` and
        # `pid_started` gets the legacy shape back.
        if (not owner.get("pid_fp") and str(recorded).startswith(
                (session_anchor.SCHEME_PROC, session_anchor.SCHEME_PS))
                and _fp_verdict(recorded, pid) == session_anchor.VERDICT_MATCH):
            owner["pid_fp"], owner["pid_fp_pid"] = recorded, pid
            owner["pid_started"] = _pid_legacy_fingerprint(pid) or None
            lease["owner"] = owner
            return True
        return False
    proof, detail = _ownership_proof(lease, pid)
    if proof is None:
        return False
    fields = _pid_owner_fields(pid)
    if not (fields["pid_fp"] or fields["pid_started"]):
        return False
    owner.update(fields)
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
      1. SAME HOST - mirrors `_judge`'s `owner.host` check. A pid integer
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
    deliberately unaffected: `gc` still reclaims and still drops, so refusing
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
    """True if an Odoo server could bind `port` right now.

    Probed the way Odoo's own HTTP server binds (SO_REUSEADDR, bind, listen), not
    with a plain bind(): a port whose last connection is in TIME_WAIT - every port
    that just served HTTP, for ~60s after its server stopped - refuses a plain
    bind() but is perfectly usable by Odoo, so a plain probe made a freshly
    reclaimed pool look exhausted. A port some process is LISTENING on still
    refuses (SO_REUSEADDR does not allow two listeners)."""
    for family, addr in ((socket.AF_INET, ("", port)),):
        s = socket.socket(family, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(addr)
            s.listen(1)
        except OSError:
            return False
        finally:
            s.close()
    return True


def _ports_in_use(reg):
    """Every port any registry row reserves - INCLUDING a row marked
    `reclaiming`, whose server may still be stopping while gc/release/acquire
    works on it outside the lock (an orphaned row has already given its ports
    back)."""
    used = set()
    for lease in reg["leases"]:
        for p in lease.get("ports", []) or []:
            try:
                used.add(int(p))
            except (TypeError, ValueError):
                continue
    return used


def _port_in_pool(port, base, size):
    try:
        return base <= int(port) < base + size
    except (TypeError, ValueError):
        return False


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


def _conn_blocked_code(blocked):
    """The named failure code (ERROR_CODES) of a `_ConnBlocked` verdict."""
    return "DB_AUTH_DENIED" if blocked.state == "denied" else "DB_UNREACHABLE"


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
# Session anchor + the owner block every lease row carries
#
# A lease is ANCHORED to the long-lived agent process of the session that
# acquired it (see scripts/lib/session_anchor.py for how the anchor is found and
# fingerprinted). While that process lives, the lease is protected - whatever
# its server pid and whatever its TTL - because a session that is still running
# is, by definition, a session whose work is still in progress. That single
# fact replaces the heartbeat discipline no runner ever followed: pid-less build
# leases (`--stop-after-init`), docker-run instances and servers restarted
# without a re-bind all used to live on a TTL nobody refreshed.
# --------------------------------------------------------------------------- #
VIA_ENV = "ODOO_AI_VIA"
CALLER_AGENT_ID_ENV = "ODOO_AI_CALLER_AGENT_ID"
CALLER_AGENT_TYPE_ENV = "ODOO_AI_CALLER_AGENT_TYPE"

_ANCHOR_CACHE = {}


def _caller_anchor():
    """This process's session anchor (`session_anchor.discover_anchor`), memoised
    per value of the three env vars that decide it, so one command resolves it
    once while an in-process caller that changes its env still gets a fresh
    answer."""
    key = tuple(os.environ.get(name, "") for name in (
        session_anchor.ANCHOR_ENV, session_anchor.CLAUDE_PID_ENV,
        session_anchor.SESSION_ID_ENV))
    if key not in _ANCHOR_CACHE:
        _ANCHOR_CACHE[key] = session_anchor.discover_anchor()
    return _ANCHOR_CACHE[key]


def _caller_session_id():
    return os.environ.get(session_anchor.SESSION_ID_ENV, "") or ""


def _session_block(anchor, now):
    return {
        "pid": anchor.get("pid"),
        "started": anchor.get("started"),
        "session_id": anchor.get("session_id", "") or "",
        "source": anchor.get("source", "") or "",
        "seen_at": now,
    }


def _owner_block(run_id="", pid=None, base=None, now=None):
    """The `owner` object of a lease row - the ONE constructor, shared by acquire
    (every mode), bind and resume, so no path writes a differently-shaped owner.

    With no `base` it mints a fresh owner: host, run_id, started_at, the server
    pid + its fingerprint, `via` ("mcp" when ODOO_AI_VIA=mcp, else "cli"),
    `acquired_by` {agent_id, agent_type} when ODOO_AI_CALLER_AGENT_ID/_TYPE are
    set, and `session` (the caller's anchor + seen_at) when the caller has one.
    With a `base` (bind/resume) it keeps the acquisition identity - host, run_id,
    started_at, acquired_by - and refreshes the pid, `via` and, when the caller
    is anchored, `session`: the process that launched the server is the one whose
    liveness now matters. An unanchored caller never ERASES a recorded anchor."""
    now = _now() if now is None else now
    if base is None:
        owner = {"host": _host(), "run_id": run_id, "started_at": now}
        agent_id = os.environ.get(CALLER_AGENT_ID_ENV, "")
        agent_type = os.environ.get(CALLER_AGENT_TYPE_ENV, "")
        if agent_id or agent_type:
            owner["acquired_by"] = {"agent_id": agent_id, "agent_type": agent_type}
    else:
        owner = dict(base)
    if pid or base is None:
        owner.update(_pid_owner_fields(pid))
    if pid:
        owner.pop(SERVER_GONE_KEY, None)
    owner["via"] = "mcp" if os.environ.get(VIA_ENV, "") == "mcp" else "cli"
    anchor = _caller_anchor()
    if anchor:
        owner["session"] = _session_block(anchor, now)
    return owner


def _is_callers_session(session):
    """True when the recorded anchor belongs to the CALLER's session: the same
    anchor process, or - after `claude --resume`, which starts a new process
    under the same session id - the same non-empty session id."""
    if not session:
        return False
    if session_anchor.same_anchor(session, _caller_anchor()):
        return True
    sid = _caller_session_id()
    return bool(sid) and session.get("session_id") == sid


def _touch_session(lease, now=None):
    """Re-anchor `lease` onto the caller's anchor when the lease belongs to the
    caller's session (see `_is_callers_session`) and the caller has an anchor;
    mutates in place and returns True when it did. The caller owns the write."""
    owner = lease.get("owner") or {}
    session = owner.get("session")
    anchor = _caller_anchor()
    if not anchor or not _is_callers_session(session):
        return False
    owner["session"] = _session_block(anchor, _now() if now is None else now)
    lease["owner"] = owner
    return True


# --------------------------------------------------------------------------- #
# GC
#
# Reclaiming is DESTRUCTIVE: for every condemned lease `gc` stops the owner's
# process GROUP and DROPS the database, then removes the row - and the registry
# was the only place those coordinates existed. It used to be IMPLICIT too:
# `acquire` ran the same sweep over the whole machine-global registry as a side
# effect, so one run's acquire destroyed another run's live instance (113 of 134
# real reclaims happened inside an acquire). `acquire` no longer sweeps. The only
# destruction an acquire can perform is the narrow CAPACITY reclaim (see
# `_capacity_reclaim`): when it cannot otherwise be served, it stops the servers
# of leases whose owner is PROVABLY gone and frees their ports - it never drops a
# database and never deletes an ephemeral row.
#
# Every reclamation still leaves a RECORD, emitted by the reclaiming code itself
# (never trusted to each call site), on two channels that outlive the row:
#   - one line per reclaimed lease on STDERR. NEVER stdout: `cmd_acquire`'s
#     stdout is a PROTOCOL (`eval $(allocator.py acquire ...)`), so a prose line
#     interleaved there would be executed by the caller's shell.
#   - the same record appended to the evidence log (RECLAIM_LOG_BASENAME),
#     because a subagent's stderr is frequently not what the human ends up
#     reading.
#
# `gc`, `release` and acquire's capacity reclaim are TWO-PHASE so the registry
# lock is never held while a server is stopped (up to ~10s per group) or a
# database is dropped (minutes) - every acquire/release/park/list on the machine
# waits on that lock: phase A marks the targets `reclaiming` under the lock
# (`_mark_reclaiming`), phase B stops (+ drops) outside it (`_stop_and_drop`,
# `_capacity_reclaim`), phase C deletes the finished rows, clears the marker of
# a failed one, or frees an orphan's ports, under the lock again
# (`_settle_marked`). A `reclaiming` row keeps its ports reserved until phase C,
# so no acquire can be handed a port a server that is still being stopped is
# listening on; park/resume/adopt/release refuse it (RECLAIM_IN_PROGRESS) and
# gc skips it while its marker's process lives.
# --------------------------------------------------------------------------- #

# Condemn-reason vocabulary - the SSOT for WHY a lease was condemned: exactly one
# string per condemn arm of `_judge` below, and the only values that ever reach a
# notice, the evidence log, or an operator's grep. The reason is the part of the
# record that CANNOT be reconstructed after the fact.
CONDEMN_SESSION_ENDED = "owner-session-ended"
CONDEMN_PID_DEAD = "owner-pid-dead"
CONDEMN_PID_RECYCLED = "owner-pid-recycled"
CONDEMN_TTL_UNPROVABLE = "ttl-expired-liveness-unprovable"
CONDEMN_PARK_EXPIRED = "park-budget-expired"
CONDEMN_REASONS = (
    CONDEMN_SESSION_ENDED, CONDEMN_PID_DEAD, CONDEMN_PID_RECYCLED,
    CONDEMN_TTL_UNPROVABLE, CONDEMN_PARK_EXPIRED,
)
# The only reasons the automatic CAPACITY reclaim may act on: the owner is
# PROVABLY gone (its session ended, or its server pid is dead / recycled). A TTL
# expiry is an absence of evidence, and a park budget is not acquire's business.
CAPACITY_REASONS = (CONDEMN_SESSION_ENDED, CONDEMN_PID_DEAD, CONDEMN_PID_RECYCLED)

# `protected_by` vocabulary of `_verdict` (what, if anything, keeps a lease).
PROTECTED_BY_SESSION = "session"
PROTECTED_BY_SERVER_PID = "server-pid"
PROTECTED_BY_PARK = "park"
PROTECTED_BY_TTL = "ttl"
PROTECTED_BY_NONE = "none"

# `state` vocabulary of `_verdict`.
STATE_RUNNING = "running"
STATE_RESERVED = "reserved"
STATE_PARKED = "parked"
STATE_ORPHANED = "orphaned"
STATE_RECLAIMING = "reclaiming"

# `gc --scope` vocabulary.
GC_SCOPE_ALL = "all"
GC_SCOPE_DEAD_SESSIONS = "dead-sessions"
GC_SCOPE_ANCHOR = "anchor"
GC_SCOPES = (GC_SCOPE_ALL, GC_SCOPE_DEAD_SESSIONS, GC_SCOPE_ANCHOR)

# What gc does to a target (`_gc_action`): reclaim it (stop, drop, delete), or
# return a lease resumed out of a deliberate park to that park.
GC_ACTION_RECLAIM = "reclaim"
GC_ACTION_PARK = "park"

# `by_verb` of a capacity reclaim's record - distinct from "acquire" on purpose:
# a record with by_verb=acquire would mean the old implicit sweep came back.
CAPACITY_VERB = "acquire-capacity"

# A `reclaiming` marker whose owner cannot be probed (another host) is honoured
# for this long, then treated as abandoned.
RECLAIM_MARKER_OFFHOST_S = 3600

# The evidence log, appended under `$ODOO_AI_HOME/logs/` (Tier-1: machine-global
# flat, exactly like the registry it outlives - see snippets/state-root-resolution.md).
# JSONL so a consumer parses it without a format of its own, and append-only so
# concurrent allocators cannot lose each other's lines (one short line per O_APPEND
# write).
#
# ITS NAME IS DELIBERATELY OUTSIDE the run-artifact globs `prune_stale_run_artifacts`
# (`scripts/lib/state_reclaim.sh`) sweeps - `*.log`, `*.findings.md`, `*.conf` - so
# it is NOT swept, and that is a decision, not an oversight. That sweeper's
# mtime-plus-lease-reachability policy is right for a per-run build log, and
# precisely wrong here: this file is the ONLY surviving evidence that a database
# was destroyed, so an mtime bound would delete exactly the record needed to
# explain a deletion older than the bound. Nothing else reclaims it either, which
# is affordable because it grows ONLY when something was actually reclaimed.
RECLAIM_LOG_BASENAME = "allocator-reclaimed.jsonl"

# The record's fields, in the order the stderr notice prints them: identity first
# (which lease, whose run, which database, which pid), then the verdict, then who
# performed the reclamation - so a victim and a perpetrator can each recognise
# themselves in the same line.
_RECLAIM_NOTICE_FIELDS = (
    "token", "run_id", "db_name", "mode", "series", "owner_pid", "owner_host",
    "reason", "action", "dropped_db", "by_verb", "by_pid", "by_run_id", "at_utc",
)


def _ttl_threshold(lease):
    """The TTL arm's bound for `lease`: its own ttl_s when that was set
    EXPLICITLY (`acquire --ttl`), else at least LEGACY_UNPROVABLE_TTL_S."""
    try:
        ttl = int(lease.get("ttl_s", DEFAULT_TTL_S))
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL_S
    if lease.get("ttl_explicit"):
        return ttl
    return max(ttl, LEGACY_UNPROVABLE_TTL_S)


def _last_touch(lease):
    """The latest moment anything vouched for this lease: its heartbeat or its
    anchor's `seen_at` (falling back to when it was acquired)."""
    owner = lease.get("owner") or {}
    session = owner.get("session") or {}
    stamps = [lease.get("heartbeat_at"), session.get("seen_at"), owner.get("started_at")]
    values = []
    for stamp in stamps:
        try:
            values.append(int(stamp))
        except (TypeError, ValueError):
            continue
    return max(values) if values else 0


def _judge(lease, auto=False):
    """(reason, protected_by, anchor_state) - the ONE liveness judgment.

    `reason` is the ARM that condemns `lease` (a CONDEMN_REASONS value) or None
    when it is protected. `auto` selects the AUTOMATIC semantics (`gc --scope
    dead-sessions`, acquire's capacity reclaim): no TTL arm, and a grace window
    after a session ends. `anchor_state` is "alive" | "dead" | "unknown", or None
    for an unanchored row.

    Order, and why each rung sits where it does - for reaping, the safe default
    is to NOT reap when unsure: an un-reaped orphan costs RAM, a wrongly-reaped
    lease kills a live server and destroys work in progress.
      1. PARKED (`parked_at` present): judged by its own budget and nothing else.
         Park clears the owner pid on purpose, so every pid arm below would read
         it as "no pid" and hand it to the TTL arm - reclaiming a deliberately
         suspended instance for the act of suspending it. A reboot while parked
         does not consume the budget (`parked_boot_id`).
      2. ANCHORED on this host (not `shared` - a shared render server is
         cross-session by design and is judged by its server pid alone):
           alive -> PROTECTED, whatever the server pid and the TTL say.
           dead  -> the caller's own session (a resumed session: same session id)
                    re-anchors it and protects it; otherwise
                    CONDEMN_SESSION_ENDED - under `auto` only once
                    ANCHOR_GRACE_S has passed since its last touch.
           unknown -> fall through: the anchor could not be proven either way.
      3. LEGACY / UNANCHORED:
           a dead server pid on this host   -> CONDEMN_PID_DEAD
           its fingerprint proves recycling -> CONDEMN_PID_RECYCLED
           its fingerprint matches          -> PROTECTED
           otherwise liveness is UNPROVABLE -> the TTL arm, bounded by
           `_ttl_threshold`, and NEVER under `auto`.
    """
    parked_at = lease.get("parked_at")
    if parked_at is not None:
        recorded_boot = lease.get("parked_boot_id")
        current_boot = _boot_id()
        if recorded_boot and current_boot and recorded_boot != current_boot:
            # The host rebooted while parked, so the budget was never CONSUMED -
            # it only elapsed on a machine that was off. Comparing only when BOTH
            # sides have a value is deliberate: an unreadable boot id degrades to
            # the plain budget comparison, never to a condemn on ambiguity.
            return None, PROTECTED_BY_PARK, None
        try:
            budget = int(lease.get("park_ttl_s", DEFAULT_PARK_TTL_S))
        except (TypeError, ValueError):
            budget = DEFAULT_PARK_TTL_S
        if _now() - int(parked_at) > budget:
            return CONDEMN_PARK_EXPIRED, PROTECTED_BY_NONE, None
        return None, PROTECTED_BY_PARK, None

    owner = lease.get("owner") or {}
    here = _host()
    anchor_state = None
    session = owner.get("session")
    if session and lease.get("mode") != "shared":
        anchor_state = session_anchor.anchor_state(session, owner.get("host"), here)
        if anchor_state == session_anchor.STATE_ALIVE:
            return None, PROTECTED_BY_SESSION, anchor_state
        if anchor_state == session_anchor.STATE_DEAD:
            if _is_callers_session(session):
                # A resumed session (new process, same session id) or this very
                # session: re-anchor in memory; a caller holding the lock persists it.
                _touch_session(lease)
                return None, PROTECTED_BY_SESSION, anchor_state
            if auto and _now() - _last_touch(lease) <= ANCHOR_GRACE_S:
                return None, PROTECTED_BY_SESSION, anchor_state
            return CONDEMN_SESSION_ENDED, PROTECTED_BY_NONE, anchor_state

    if owner.get("host") == here and owner.get("pid") is not None:
        try:
            pid = int(owner.get("pid"))
        except (TypeError, ValueError):
            pid = None
        if pid is not None:
            if not _pid_alive(pid):
                return CONDEMN_PID_DEAD, PROTECTED_BY_NONE, anchor_state
            expected, _key = _recorded_fingerprint(owner, pid)
            verdict = _fp_verdict(expected, pid) if expected is not None \
                else session_anchor.VERDICT_UNKNOWN
            if verdict == session_anchor.VERDICT_MATCH:
                return None, PROTECTED_BY_SERVER_PID, anchor_state
            if verdict == session_anchor.VERDICT_MISMATCH:
                return CONDEMN_PID_RECYCLED, PROTECTED_BY_NONE, anchor_state
            # unknown: not a proven mismatch - never condemn on ambiguity.

    if auto:
        return None, PROTECTED_BY_NONE, anchor_state
    if _now() - _last_touch(lease) > _ttl_threshold(lease):
        return CONDEMN_TTL_UNPROVABLE, PROTECTED_BY_NONE, anchor_state
    return None, PROTECTED_BY_TTL, anchor_state


def _condemn_reason(lease, *, auto=False):
    """The ARM that condemns `lease` (a CONDEMN_REASONS value), or None when it
    is protected. See `_judge` for the order of the arms and what `auto` means."""
    return _judge(lease, auto=auto)[0]


def _is_stale(lease):
    """Boolean face of `_condemn_reason` (manual semantics) - true when SOME arm
    condemns the lease. Kept as its own name because most callers (`cmd_query`,
    `cmd_assert_droppable`) only ask the yes/no question. One predicate, one
    implementation."""
    return _condemn_reason(lease) is not None


def _reclaim_in_progress(lease):
    """True while another live process holds this row's `reclaiming` marker. A
    marker left by a process that died mid-reclaim (gc, release or an acquire's
    capacity reclaim) is ignored, so the row is retaken by the next gc/release
    instead of being stuck forever."""
    mark = lease.get("reclaiming")
    if not isinstance(mark, dict):
        return False
    if mark.get("host") and mark.get("host") != _host():
        try:
            return _now() - int(mark.get("at", 0)) < RECLAIM_MARKER_OFFHOST_S
        except (TypeError, ValueError):
            return False
    try:
        return _pid_alive(int(mark.get("by_pid")))
    except (TypeError, ValueError):
        return False


def _lease_state(lease):
    if _reclaim_in_progress(lease):
        return STATE_RECLAIMING
    if lease.get("parked_at") is not None:
        return STATE_PARKED
    if lease.get("orphaned"):
        return STATE_ORPHANED
    if (lease.get("owner") or {}).get("pid") is not None:
        return STATE_RUNNING
    return STATE_RESERVED


def _verdict(lease):
    """The SSOT answer to "what is this lease, and would anything reclaim it?" -
    consumed by `list --with-verdict` (the teardown hook, the MCP server) so no
    consumer re-derives liveness.

    {state, protected_by, condemn, condemn_auto, anchor_state, anchor_alive}:
    `condemn` is the explicit-`gc` verdict, `condemn_auto` the automatic one
    (dead-sessions / capacity), `anchor_alive` None for an unanchored row."""
    reason, protected_by, anchor_state = _judge(lease, auto=False)
    auto_reason = _judge(lease, auto=True)[0]
    return {
        "state": _lease_state(lease),
        "protected_by": protected_by,
        "condemn": reason,
        "condemn_auto": auto_reason,
        # True when a gc that condemns this lease for its owner being gone would
        # PARK it again instead of reclaiming it (see `_gc_action`).
        "return_to_park": bool((lease.get("owner") or {}).get("return_to_park")),
        "anchor_state": anchor_state or "none",
        "anchor_alive": (None if anchor_state is None
                         else anchor_state == session_anchor.STATE_ALIVE),
    }


# `owner.server_gone` - left on a row whose bound server exited while its session
# still lives (`_shed_gone_server`): {pid, reason, at}. Evidence only; nothing
# judges liveness from it. `park` reads it as "this lease was RUNNING", and any
# write of a fresh server pid (`_owner_block`) or a park (`_stamp_park`) clears it.
SERVER_GONE_KEY = "server_gone"


def _shed_gone_server(lease, now=None):
    """Clear the recorded server of a SESSION-PROTECTED lease whose server is
    provably gone, so an OLDER allocator protects the row too. Mutates `lease`
    in place and returns True when it did; the caller holds the lock and owns
    the write.

    Why: this allocator protects such a row by its live session anchor (`_judge`
    rung 2) and ignores the dead pid. A pre-anchor allocator knows nothing of the
    anchor: it reads `owner.pid` dead (or its fingerprint mismatched) as
    `owner-pid-dead` / `owner-pid-recycled`, and its acquire sweep reclaims the
    row - dropping a drop_on_release database under a session that is still
    using it. A row with NO pid is judged by that reader's TTL arm alone
    (`ttl_s` against `heartbeat_at`), which the session's heartbeat keeps fresh.
    So the pid keys (PID_OWNER_KEYS) are cleared, `heartbeat_at` is refreshed
    (the live anchor vouches for the row right now), and `owner.server_gone`
    records what was shed. Nothing is lost: a dead or recycled pid is never
    signalled (`_stop_owner_group_if_local`), and this allocator's own verdict
    for the row is unchanged (still `session`-protected; state `reserved`).

    Only when ALL hold: not parked (already pid-less), not shared (judged by its
    server pid alone, in every version), not being reclaimed, recorded on THIS
    host, its anchor PROVABLY alive, and its pid dead or proven recycled. An
    unknown anchor or an unmeasurable fingerprint sheds nothing."""
    if lease.get("parked_at") is not None or lease.get("mode") == "shared":
        return False
    if _reclaim_in_progress(lease):
        return False
    owner = lease.get("owner") or {}
    here = _host()
    if owner.get("host") != here or owner.get("pid") is None:
        return False
    try:
        pid = int(owner.get("pid"))
    except (TypeError, ValueError):
        return False
    session = owner.get("session")
    if not session or session_anchor.anchor_state(
            session, owner.get("host"), here) != session_anchor.STATE_ALIVE:
        return False
    if not _pid_alive(pid):
        reason = CONDEMN_PID_DEAD
    else:
        expected, _key = _recorded_fingerprint(owner, pid)
        if expected is None or _fp_verdict(expected, pid) != session_anchor.VERDICT_MISMATCH:
            return False
        reason = CONDEMN_PID_RECYCLED
    now = _now() if now is None else now
    owner.update(_pid_owner_fields(None))
    owner[SERVER_GONE_KEY] = {"pid": pid, "reason": reason, "at": now}
    lease["owner"] = owner
    lease["heartbeat_at"] = now
    sys.stderr.write(
        "allocator: the server (pid {pid}) of the lease on database {db!r} is gone "
        "({reason}) while its session is alive - cleared the server pid so the lease "
        "stays protected under every allocator version; the database and ports are "
        "kept.\n".format(pid=pid, db=lease.get("db_name"), reason=reason))
    return True


def _shed_gone_servers(reg, now=None):
    """`_shed_gone_server` over every row of `reg`; the number of rows changed.
    Called under the lock by the paths that already write the registry."""
    return sum(1 for lease in reg.get("leases", []) if _shed_gone_server(lease, now))


def _reclaim_record(lease, reason, verb, run_id="", action="deleted", dropped_db=None):
    """The full, self-contained account of ONE reclamation.

    Self-contained is the whole point: it is read AFTER the registry row it
    describes has been deleted (or its ports freed), so every coordinate a reader
    might need - lease, run, database, ports, owner - is copied out here rather
    than referenced. `by_*` names the reclaimer, which is what makes a
    cross-tenant reclamation attributable in both directions. `action` says what
    happened to the row ("deleted", or "orphaned" = server stopped + ports freed,
    row and database KEPT); `dropped_db` defaults to "a drop_on_release lease
    whose row was deleted"."""
    owner = lease.get("owner", {}) or {}
    at = _now()
    if dropped_db is None:
        dropped_db = bool(lease.get("drop_on_release") and lease.get("db_name")
                          and action == "deleted")
    session = owner.get("session") or {}
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
        "owner_session_id": session.get("session_id", ""),
        "ports": lease.get("ports", []),
        "reason": reason,
        "action": action,
        "dropped_db": bool(dropped_db),
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
    printed (not the 8-char fingerprint `cmd_list` redacts to) because matching
    it against the caller's own earlier `ALLOC_TOKEN=` is how an operator
    identifies which of their runs just lost its instance."""
    fields = " ".join(
        "{k}={v}".format(k=key, v=shlex.quote(_notice_value(rec.get(key))))
        for key in _RECLAIM_NOTICE_FIELDS
    )
    return "allocator: RECLAIMED lease {fields}\n".format(fields=fields)


def _reclaim_log_path():
    return os.path.join(_home(), "logs", RECLAIM_LOG_BASENAME)


def _append_reclaim_log(rec):
    """Append one JSON record to the evidence log. Best-effort but never SILENT:
    a record that cannot be persisted is itself reported on stderr. Never fatal -
    failing to write the account of a reclamation must not fail the command that
    already performed it."""
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


def _capacity_reason(lease):
    """The reason `lease` may be touched by acquire's CAPACITY reclaim, or None.

    Only a lease whose owner is PROVABLY gone under the automatic semantics
    (CAPACITY_REASONS); never a `shared` row, a parked row, a row another
    process is already reclaiming, or one already orphaned."""
    if (lease.get("mode") == "shared" or lease.get("parked_at") is not None
            or lease.get("orphaned") or _reclaim_in_progress(lease)):
        return None
    reason = _condemn_reason(lease, auto=True)
    return reason if reason in CAPACITY_REASONS else None


# ---- the ONE two-phase reclaim primitive (gc, release, acquire-capacity) ----
# Phase A (`_mark_reclaiming`, under the lock) claims a row for this process;
# phase B (`_stop_and_drop` / `_capacity_reclaim`, OUTSIDE the lock) does the
# slow part on a detached snapshot; phase C (`_settle_marked`, under the lock
# again) applies each outcome - but only to a row that still carries THIS
# process's marker. A marked row keeps its ports reserved throughout
# (`_ports_in_use`), and a marker whose process died is ignored by
# `_reclaim_in_progress`, so a crash between phases leaves a row the next
# gc/release/acquire simply retakes.
SETTLE_DELETE = "delete"   # the row goes
SETTLE_KEEP = "keep"       # the marker is cleared, the row stays as it was
SETTLE_ORPHAN = "orphan"   # the marker is cleared, the ports are freed, the row stays
SETTLE_PARK = "park"       # the marker is cleared, the row is PARKED again (db + ports kept)


def _mark_reclaiming(lease, reason, verb, now=None):
    """Phase A: mark `lease` as being reclaimed by this process (`verb` says
    which: gc, release, acquire-capacity). The caller holds the registry lock and
    owns the write. Returns a DETACHED snapshot for phase B to work from, so
    nothing outside the lock ever touches a registry object."""
    lease["reclaiming"] = {"by_pid": os.getpid(), "host": _host(),
                           "at": _now() if now is None else now,
                           "reason": reason, "by_verb": verb}
    return json.loads(json.dumps(lease))


def _reclaimer_desc(lease):
    """Who holds a row's `reclaiming` marker, for a RECLAIM_IN_PROGRESS refusal."""
    mark = lease.get("reclaiming") or {}
    return "pid {p} ({v})".format(p=mark.get("by_pid"), v=mark.get("by_verb") or "gc")


def _stop_and_drop(lease, instances_path=None):
    """Phase B of gc and release, OUTSIDE the lock: stop the owner's process group
    FIRST, then drop a throwaway database through Odoo. The order is mandatory: a
    listening Odoo master + workers hold open DB connections, and an active
    backend blocks `DROP DATABASE` (odoo_db.py's pg_terminate_backend stays as a
    second belt). The stop is a no-op for a lease with no live, proven-owned
    local pid. Returns False ONLY for a genuine drop failure - the database is
    then still there - and True otherwise (dropped, or nothing to drop)."""
    _stop_owner_group_if_local(lease)
    if lease.get("drop_on_release") and lease.get("db_name"):
        return _drop_through_odoo(lease, instances_path)
    return True


def _stamp_park(lease, park_ttl_s):
    """Write the PARKED state onto `lease`: clear the recorded server
    (PID_OWNER_KEYS) and stamp parked_at + park_ttl_s + parked_boot_id. The one
    writer of those keys, shared by `park` and gc's return-to-park."""
    owner = lease.setdefault("owner", {})
    owner.update(_pid_owner_fields(None))
    owner.pop(SERVER_GONE_KEY, None)
    lease["parked_at"] = _now()
    lease["park_ttl_s"] = park_ttl_s
    boot = _boot_id()
    if boot:
        lease["parked_boot_id"] = boot
    else:
        # Absent, not empty: `_judge` compares only when BOTH sides carry a
        # value, so an absent key degrades to the plain budget comparison
        # instead of reading as a mismatch.
        lease.pop("parked_boot_id", None)


def _mark_return_to_park(lease, park_ttl_s):
    """Record on `lease` that it was taken out of a deliberate park: the owner
    keys `return_to_park` (True) and `return_park_ttl_s` (the budget it had).
    `_gc_action` then parks it again when its new owner goes away."""
    owner = lease.setdefault("owner", {})
    owner["return_to_park"] = True
    try:
        owner["return_park_ttl_s"] = int(park_ttl_s)
    except (TypeError, ValueError):
        owner["return_park_ttl_s"] = DEFAULT_PARK_TTL_S


def _repark(lease):
    """Put a resumed lease back in the park with its original budget, measured
    from now; its db_name, ports and drop_on_release are untouched."""
    owner = lease.setdefault("owner", {})
    budget = owner.pop("return_park_ttl_s", None) or DEFAULT_PARK_TTL_S
    owner.pop("return_to_park", None)
    # A capacity reclaim may have orphaned it first (server stopped, ports given
    # back); it is parked now, whatever ports it still holds.
    lease.pop("orphaned", None)
    _stamp_park(lease, budget)


def _settle_marked(reg, outcomes):
    """Phase C: apply `outcomes` {token: SETTLE_*} to the rows THIS process
    marked. The caller holds the lock and owns the write. A row whose marker is
    no longer ours (or that is gone) is left exactly as it is. Returns the set of
    tokens settled."""
    me, here = os.getpid(), _host()
    settled, kept = set(), []
    for lease in reg["leases"]:
        token = lease.get("token", "")
        mark = lease.get("reclaiming") or {}
        if (token not in outcomes or mark.get("by_pid") != me
                or mark.get("host", here) != here):
            kept.append(lease)
            continue
        settled.add(token)
        outcome = outcomes[token]
        if outcome == SETTLE_DELETE:
            continue
        lease.pop("reclaiming", None)
        if outcome == SETTLE_ORPHAN:
            lease["orphaned"] = {"at": _now(), "reason": mark.get("reason"),
                                 "by_verb": mark.get("by_verb"),
                                 "ports": list(lease.get("ports") or [])}
            lease["ports"] = []
        elif outcome == SETTLE_PARK:
            _repark(lease)
        kept.append(lease)
    reg["leases"] = kept
    return settled


def _capacity_mark(reg, candidates):
    """Phase A of acquire's CAPACITY reclaim, under the lock: mark every candidate
    whose owner is provably gone (`_capacity_reason`). Returns [(snapshot,
    reason)]; empty when nothing may be taken. The caller owns the write."""
    now = _now()
    work = []
    for lease in list(candidates):
        reason = _capacity_reason(lease)
        if reason is not None:
            work.append((_mark_reclaiming(lease, reason, CAPACITY_VERB, now), reason))
    return work


def _capacity_reclaim(work, run_id="", delete=False):
    """Phase B of acquire's CAPACITY reclaim, OUTSIDE the lock: stop each marked
    owner's process group (through the same ownership-proof gate every signal
    uses) and report the reclamation. Returns the phase-C outcomes the acquire
    settles at the top of its next critical section.

    NON-DESTRUCTIVE by construction: the outcome is either SETTLE_ORPHAN - the
    row's ports are freed and it is marked `orphaned` {at, reason, by_verb,
    ports}; the row AND its database are KEPT, so the owner (or an explicit
    `gc`) still finishes it properly - or, with `delete` (an exclusive conflict:
    that row reserves a DECLARED database and never drops it, so removing the
    row loses nothing), SETTLE_DELETE. It NEVER drops a database. The stop is
    bounded (`_stop_group`) and, being outside the lock, stalls no other
    session; the marked rows keep their ports until phase C, so no other acquire
    can be handed a port a server that is still stopping listens on.

    Returns (outcomes, stopped): `stopped` counts the server groups actually
    signalled - what opens acquire's short port-free retry window."""
    outcomes, stopped = {}, 0
    for lease, reason in work:
        if _stop_owner_group_if_local(lease):
            stopped += 1
        _report_reclaimed(_reclaim_record(
            lease, reason, CAPACITY_VERB, run_id,
            action="deleted" if delete else "orphaned", dropped_db=False))
        outcomes[lease.get("token", "")] = SETTLE_DELETE if delete else SETTLE_ORPHAN
    return outcomes, stopped


def _holder_summary(lease):
    """What a refused acquire says about a lease standing in its way."""
    owner = lease.get("owner") or {}
    verdict = _verdict(lease)
    try:
        age = max(0, _now() - int(owner.get("started_at") or 0))
    except (TypeError, ValueError):
        age = None
    return {
        "token8": (lease.get("token") or "")[:8],
        "mode": lease.get("mode", ""),
        "db_name": lease.get("db_name", ""),
        "run_id": owner.get("run_id", ""),
        "state": verdict["state"],
        "session_alive": verdict["anchor_alive"],
        "age_s": age,
        "ports": list(lease.get("ports") or []),
    }


def _report_holders(holders):
    """Name the leases a refused acquire could not reclaim: stderr in shell mode
    (stdout is the eval protocol and a refusal writes nothing there), a
    structured `holders` field in JSON mode."""
    rows = [_holder_summary(lz) for lz in holders]
    _payload("holders", rows)
    for row in rows:
        sys.stderr.write(
            "allocator:   held by lease {t} mode={m} db={d} run={r} state={s} "
            "session_alive={a} age_s={g}\n".format(
                t=row["token8"], m=row["mode"], d=row["db_name"], r=row["run_id"] or "-",
                s=row["state"], a=_notice_value(row["session_alive"]) or "unanchored",
                g=_notice_value(row["age_s"]))
        )


# --------------------------------------------------------------------------- #
# Output: the shell-eval protocol, or one JSON object (`--format json`)
#
# Every command speaks through `_emit` / `_note` / `_payload` / `_fail` and never
# prints directly, so `--format json` can collect the SAME facts into
# {"ok", "rc", "error": {"code", "message"} | null, "fields": {...}} without a
# second implementation of any command. Without --format json the shell protocol
# is byte-identical to what it always was.
# --------------------------------------------------------------------------- #
_OUT = {"json": False, "fields": {}, "error": None}

# Named failure codes - the SSOT. Every non-zero exit of every verb carries
# exactly one of these (`_fail`), each code always pairs with the same exit
# code, and `--format json` reports it as `error.code`. The stdio MCP server
# imports this table rather than re-declaring it.
ERROR_CODES = {
    "USAGE": {"rc": 2, "summary": "invalid arguments",
              "remedy": "fix the flags named in the message (see `allocator.py --help`)"},
    "SERIES_REQUIRED": {"rc": 2, "summary": "acquire needs --series <X.Y>",
                        "remedy": "pass the series you mean; nothing is picked for you"},
    "ADDONS_PATH_OVERRIDE_INVALID": {"rc": 2,
                                     "summary": "--addons-path-override is empty or names "
                                                "missing directories",
                                     "remedy": "pass existing directories"},
    "NO_INSTANCE": {"rc": 1, "summary": "no instance for that series/profile in the catalog",
                    "remedy": "declare one with /odoo-ai-agents:odoo-setup or pass --instances"},
    "NO_INSTANCE_CATALOG": {"rc": 1, "summary": "the instance catalog (instances.toml) is "
                                                "missing or unreadable",
                            "remedy": "run /odoo-ai-agents:odoo-setup to declare an instance, "
                                      "or pass --instances <path to instances.toml>"},
    "EXCLUSIVE_CONFLICT": {"rc": 3, "summary": "the database is already held exclusively",
                           "remedy": "retry later, use --mode ephemeral, or ask its owner to "
                                     "release it"},
    "PORT_POOL_EXHAUSTED": {"rc": 4, "summary": "no free port in the instance's pool",
                            "remedy": "release or park a lease you own; see `holders`",
                            # A refinement `_fail(..., reason=)` reports as
                            # fields.reason + fields.remedy: same code and exit,
                            # different cause and fix.
                            "reasons": {
                                PORTS_BUSY_OUTSIDE_REGISTRY: {
                                    "summary": "no lease holds a port of this pool, yet no "
                                               "port in it can be bound",
                                    "remedy": "the ports are bound by processes outside the "
                                              "lease registry (or are still being released "
                                              "by a server that was just stopped): retry "
                                              "shortly; if it persists, find the listener "
                                              "(`ss -ltnp`) or widen the pool "
                                              "(port_pool_size / http_port_base)"}}},
    "ADDONS_PATH_WORKTREE_MISMATCH": {"rc": 5, "summary": "cwd is a different worktree of a "
                                                          "catalog addons_path repo",
                                      "remedy": "pass --addons-path-override <the tree to "
                                                "build>"},
    "NO_CREATEDB": {"rc": 6, "summary": "the role lacks CREATEDB",
                    "remedy": "grant CREATEDB, or use --mode exclusive, or --no-create"},
    "CREATEDB_UNDETERMINABLE": {"rc": 7, "summary": "CREATEDB could not be determined",
                                "remedy": "45-venv.sh record-env, declare db_run_mode, or "
                                          "start the cluster"},
    "DB_AUTH_DENIED": {"rc": 8, "summary": "Odoo cannot authenticate to the cluster",
                       "remedy": "run /odoo-ai-agents:odoo-setup or export ODOO_PG_PASSWORD"},
    "DB_UNREACHABLE": {"rc": 9, "summary": "the database cluster did not answer",
                       "remedy": "start the cluster"},
    "RUN_ID_REQUIRED": {"rc": 10, "summary": "no --run-id (ownership not established)",
                        "remedy": "pass the run id you were given; never invent one"},
    "RECLAIM_IN_PROGRESS": {"rc": 11, "summary": "another process is reclaiming this lease",
                            "remedy": "wait for that gc/release to finish, then re-check"},
    "LEASE_NOT_FOUND": {"rc": 1, "summary": "no lease with that token",
                        "remedy": "check the token (`list --tokens`)"},
    "NOT_OWNER": {"rc": 1, "summary": "the lease is owned by a different run",
                  "remedy": "only the run that acquired a lease may release, park, or adopt it"},
    "DROP_FAILED_KEPT": {"rc": 1, "summary": "the drop failed; the lease is kept",
                         "remedy": "fix the drop surface (45-venv.sh record-env) and retry, or "
                                   "--force-forget"},
    "SHARED_NOT_PARKABLE": {"rc": 3, "summary": "a shared lease cannot be parked",
                            "remedy": "leave it for its readers; gc reclaims it once its "
                                      "server is gone"},
    "NOT_RUNNING": {"rc": 4, "summary": "the lease records no server pid",
                    "remedy": "bind a pid first, or release the lease"},
    "NOT_PARKED": {"rc": 3, "summary": "the lease is not parked and no live server holds it",
                   "remedy": "bind the pid instead"},
    "RESUME_RACE": {"rc": 6, "summary": "another caller already resumed this lease",
                    "remedy": "stop the server you launched and attach to the running one"},
    "DB_GONE": {"rc": 5, "summary": "the parked lease's database no longer exists",
                "remedy": "release the lease, then build a fresh instance"},
    "WRONG_HOST": {"rc": 4, "summary": "the lease was recorded on another host",
                   "remedy": "operate on it from the host that holds it"},
    "PID_NOT_ALIVE": {"rc": 4, "summary": "the named pid is not a live process here",
                      "remedy": "pass the pid of the server you launched"},
    "OWNERSHIP_UNPROVEN": {"rc": 4, "summary": "the pid is not proven to be this lease's server",
                           "remedy": "launch the server for this lease's database/port"},
    "NOT_FOUND": {"rc": 1, "summary": "no matching lease",
                  "remedy": "acquire one"},
    "DB_HELD_BY_OTHER_RUN": {"rc": 1, "summary": "a fresh lease owned by another run holds "
                                                 "the database",
                             "remedy": "route the drop through `release <token>`"},
    "DB_HELD_UNOWNED": {"rc": 1, "summary": "a fresh unowned lease holds the database",
                        "remedy": "pass --force deliberately, or leave it"},
    "REAP_DROP_FAILED": {"rc": 1, "summary": "at least one orphan drop failed",
                         "remedy": "see the stderr account"},
    "ANCHOR_REQUIRED": {"rc": 2, "summary": "--scope anchor needs an anchor",
                        "remedy": "pass --anchor <pid:fingerprint> (see `anchor --print`)"},
    "ANCHOR_ALIVE": {"rc": 3, "summary": "that session anchor is still alive",
                     "remedy": "wait for the session to end, or pass --force deliberately"},
    "NO_ANCHOR": {"rc": 5, "summary": "the caller has no session anchor",
                  "remedy": "run inside an agent session or export ODOO_AI_SESSION_ANCHOR"},
    "UNSPECIFIED": {"rc": 1, "summary": "the command failed", "remedy": "see stderr"},
}


class _UsageError(Exception):
    """A malformed argument - reported as USAGE (exit 2), never a traceback."""


def _reset_output(json_mode=False):
    _OUT["json"] = bool(json_mode)
    _OUT["fields"] = {}
    _OUT["error"] = None


def _emit(name, value, multi=False):
    """One protocol fact. Shell mode: a `NAME=<shlex-quoted>` line on stdout (a
    list is space-joined). JSON mode: `fields[NAME]` keeps the typed value;
    `multi` names a key that may repeat and is always a list in JSON."""
    if _OUT["json"]:
        if multi:
            _OUT["fields"].setdefault(name, []).append(value)
        else:
            _OUT["fields"][name] = value
        return
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    print(f"{name}={shlex.quote(str(value))}")


def _payload(name, value):
    """A structured fact that exists only in JSON mode (lists of leases,
    candidates, holders) - the shell protocol has no spelling for it."""
    if _OUT["json"]:
        _OUT["fields"][name] = value


def _note(text):
    """A `# ...` comment line of the shell protocol; JSON mode keeps it in
    `fields.notes` instead of printing it."""
    if _OUT["json"]:
        _OUT["fields"].setdefault("notes", []).append(text)
        return
    print(text)


def _fail(code, rc=None, msg=None, reason=None):
    """Record the named failure `code` and return its exit code. `msg`, when
    given, is written to stderr as `allocator: <msg>`; call sites that already
    wrote their own (longer) refusal pass none, so stderr stays byte-identical.

    `reason` names one of the code's `reasons` in ERROR_CODES (a narrower cause
    with its own remedy): it is reported as `fields.reason` + `fields.remedy`
    (JSON) and as one stderr line, and its summary becomes the message."""
    spec = ERROR_CODES.get(code) or ERROR_CODES["UNSPECIFIED"]
    rc = spec["rc"] if rc is None else rc
    sub = (spec.get("reasons") or {}).get(reason) if reason else None
    if msg:
        sys.stderr.write("allocator: {m}\n".format(m=msg))
    if sub:
        _payload("reason", reason)
        _payload("remedy", sub["remedy"])
        sys.stderr.write("allocator: {c} ({r}): {s} - {rem}\n".format(
            c=code, r=reason, s=sub["summary"], rem=sub["remedy"]))
    _OUT["error"] = {"code": code,
                     "message": msg or (sub or {}).get("summary") or spec["summary"]}
    return rc


# The one success line a teardown hook keys on. STDERR, never stdout: under
# `eval "$(allocator.py acquire ...)"` the shell consumes stdout, while stderr
# still reaches the caller's transcript (a Bash tool result).
def _announce_lease(verb, token, run_id):
    """`allocator: <verb> lease <full-token> run_id=<id>` on stderr."""
    sys.stderr.write("allocator: {v} lease {t} run_id={r}\n".format(
        v=verb, t=token, r=run_id or ""))


def _int_opt(opts, key, flag, default=None):
    """opts[key] as an int, `default` when absent/empty, _UsageError otherwise."""
    raw = opts.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        raise _UsageError("{f} must be an integer, got {v!r}".format(f=flag, v=raw))


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
class _CatalogUnavailable(Exception):
    """The instance catalog could not be read (missing file, bad TOML) - reported
    as NO_INSTANCE_CATALOG by `_run_command`, never a traceback."""


def _load_catalog(path):
    """instances_io.load_instances(path), with an unreadable catalog raised as
    `_CatalogUnavailable` (the ONE place a verb that needs the catalog reads it)."""
    try:
        return instances_io.load_instances(path)
    except (OSError, ValueError) as exc:
        raise _CatalogUnavailable("cannot read the instance catalog {p}: {e}".format(
            p=path, e=exc))


def _resolve_instance(path, series, profile=None):
    items = _load_catalog(path)
    inst, _ = instances_io.select_instance(items, series or None, profile=profile or None)
    # Return the FULL catalog alongside the selected instance: cmd_acquire needs
    # every declared http_port (not just the selected one) to close the
    # pool-boundary off-by-one - this is the same load_instances() call
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
    series = (opts.get("series") or "").strip()
    profile = opts.get("profile", "")
    # --series is REQUIRED. Without it `select_instance` silently picks the
    # catalog's HIGHEST series - an instance the caller never named - and every
    # later build, test and drop runs against it.
    if not series:
        try:
            declared = sorted({instances_io.series_of(it)
                               for it in instances_io.load_instances(path)} - {""})
        except (OSError, ValueError):
            declared = []
        return _fail("SERIES_REQUIRED", 2, (
            "acquire requires --series <X.Y> - nothing is picked for you (the old "
            "default silently took the highest declared series). Declared: {d}.".format(
                d=", ".join(declared) or "<none>")))
    # Integer flags are validated up front: a malformed value is a usage error,
    # never a traceback half-way through an allocation.
    n_ports = _int_opt(opts, "ports", "--ports", 0)
    ttl_opt = _int_opt(opts, "ttl", "--ttl", None)
    port_opt = _int_opt(opts, "port", "--port", None)
    pid_opt = _int_opt(opts, "pid", "--pid", None)
    inst, catalog_items = _resolve_instance(path, series, profile=profile or None)
    if inst is None:
        sys.stderr.write(
            f"allocator: no instance for series {series!r} in {path}. "
            "Declare one via /odoo-setup or pass --instances.\n"
        )
        return _fail("NO_INSTANCE", 1)

    addons_csv, addons_err = _resolve_addons_csv(inst, opts.get("addons_path_override"))
    if addons_err:
        sys.stderr.write(f"allocator: {addons_err}\n")
        return _fail("ADDONS_PATH_OVERRIDE_INVALID", 2)

    mode = opts.get("mode", "ephemeral")
    host = inst.get("db_host", "localhost")
    user = inst.get("db_user", "odoo")
    # Postgres port (empty when undeclared -> omit everywhere).
    db_port = inst.get("db_port", "")
    # Canonical ownership key: --run-id (or the --session back-compat alias).
    # Empty ONLY when the caller passed --allow-unowned, which is a deliberate
    # statement that this lease has no owner; ownership then degrades to
    # token-possession. Every other path is refused below (exit 10).
    run_id = opts.get("run_id") or opts.get("session", "")

    # OWNERSHIP IS NOT OPTIONAL. A lease acquired with no run id is UNOWNED, and an unowned lease
    # is the leak shape nothing can clean up on its own behalf: `assert-droppable` refuses to drop
    # it (it cannot prove whose it is), the SubagentStop teardown gate cannot correlate it to any
    # subagent, and a run auditing its own leases will not find it because it belongs to no run.
    # Observed: a grandchild agent that was never handed the run's id MINTED ONE, and the audit
    # caught it only because the invented string happened to share a prefix with the real one.
    # Refusing here is what turns "nobody threaded the id down" from a silent leak into a message
    # at the moment the chain broke. `--allow-unowned` is the deliberate opt-out for a human or a
    # fixture that genuinely wants an unowned lease; a dispatched agent may not pass it
    # (hooks/block-unowned-lease-mutation.sh refuses it the same way it refuses --force).
    if not run_id and not opts.get("allow_unowned") and mode != "readonly":
        sys.stderr.write(
            "allocator: REFUSING to acquire without --run-id.\n"
            "  A lease with no owner cannot be released by ownership, cannot be correlated to the\n"
            "  subagent that holds it, and does not appear in its own run's audit - it can only be\n"
            "  reaped by hand, once someone notices.\n"
            "  Choose ONE:\n"
            "    - pass --run-id <the run id you were given> (INSTANCE_HANDLE.run_id when a handle\n"
            "      was forwarded to you; ALLOC_RUN_ID from your own earlier acquire). If you were\n"
            "      given none and you are a dispatched agent, that is the bug - report it as\n"
            "      NEEDS_CONTEXT(RUN_ID) rather than inventing a value, because an invented id is\n"
            "      invisible to the run that would have to clean up after you; or\n"
            "    - pass --allow-unowned to state deliberately that this lease has no owner.\n"
        )
        return _fail("RUN_ID_REQUIRED", 10)

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
            return _fail("ADDONS_PATH_WORKTREE_MISMATCH", 5)

    # shared: a long-lived, NON-exclusive render-server lease (the visual stack's
    # live target). Attach to the existing lease for (series, db_name) when one is
    # live, else mint one. drop_on_release is ALWAYS False, so gc reclaims a dead
    # row but NEVER drops the declared DB. Idempotent: a later call carrying the
    # real server --pid (or the actual bound --port) refreshes the row in place.
    if mode == "shared":
        db_name = opts.get("db_name") or inst.get("db_name", "odoo")
        series_c = instances_io.series_of(inst)
        ports = [port_opt] if port_opt else []
        attached = 0
        with _locked():
            reg = _read_registry()
            # NO sweep here (see the GC section header): registering a shared
            # render target must never reclaim another run's lease.
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
                if pid_opt:
                    existing.setdefault("owner", {}).update(_pid_owner_fields(pid_opt))
                if ports:
                    existing["ports"] = ports
                else:
                    ports = existing.get("ports", [])
                existing["heartbeat_at"] = now
                # Refresh profile when caller supplies it (idempotent re-register);
                # a row written before profiles were recorded gets the resolved one.
                if profile or "profile" not in existing:
                    existing["profile"] = instances_io.profile_of(inst)
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
                    # run_id is the CANONICAL ownership key; pid + pid_started
                    # ({None, None} without --pid) and the session anchor come
                    # from the ONE owner constructor. A shared row is judged by
                    # its server pid only - the anchor is recorded, not trusted.
                    "owner": _owner_block(run_id, pid_opt, now=now),
                    "ttl_s": ttl_opt if ttl_opt is not None else DEFAULT_TTL_S,
                    "heartbeat_at": now,
                    "_pg": {"host": host, "user": user, "port": db_port},
                }
                if ttl_opt is not None:
                    new_lease["ttl_explicit"] = True
                new_lease["profile"] = instances_io.profile_of(inst)
                reg["leases"].append(new_lease)
            _shed_gone_servers(reg, now)
            _write_registry(reg)
        _announce_lease("acquired", token, run_id)
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
        return _fail("USAGE", 2)
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

    # Pool-boundary off-by-one fix: reserve EVERY catalog-declared http_port,
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
            return (_fail("DB_AUTH_DENIED", EXIT_AUTH_DENIED) if auth_state == "denied"
                    else _fail("DB_UNREACHABLE", EXIT_UNREACHABLE))

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
            return _fail(_conn_blocked_code(verdict), verdict.exit_code)
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
            return _fail("NO_CREATEDB", 6)
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
            return _fail("CREATEDB_UNDETERMINABLE", 7)

    if mode == "ephemeral":
        db_name = f"{prefix}_t_{uuid.uuid4().hex[:8]}"
    else:
        db_name = opts.get("db_name") or inst.get("db_name", "odoo")

    # NO sweep here (see the GC section header). The only thing an acquire may
    # reclaim is CAPACITY it cannot otherwise get, and only from leases whose
    # owner is PROVABLY gone (`_capacity_mark`): a conflicting exclusive holder,
    # or the holders of this instance's port pool. It is the same two-phase shape
    # as gc/release: the candidates are MARKED under the lock, their servers are
    # stopped OUTSIDE it (`_capacity_reclaim` - up to 10s per lease, which would
    # otherwise stall every session's acquire/list on the machine), and the next
    # pass of this loop settles them and retries in ONE critical section, so the
    # freed ports go to this acquire and never to a racer. Each kind of capacity
    # (the exclusive hold, the port pool) is reclaimed at most once: the loop is
    # bounded at three passes.
    pending, delete, reclaimed = {}, False, set()
    # Set once a PORT capacity reclaim has stopped a server: the freed ports can
    # stay unbindable for a moment while the stopped process's sockets close, so
    # the pick is retried until this deadline before the pool is called exhausted.
    port_wait_until = None
    while True:
        work = []
        wait_for_ports = False
        with _locked():
            reg = _read_registry()
            if pending:
                _settle_marked(reg, pending)
                pending = {}
                # Persisted at once: the servers are already stopped, whatever the
                # retry below decides.
                _write_registry(reg)
            if mode == "exclusive":
                holders = [lz for lz in reg["leases"]
                           if lz.get("mode") == "exclusive" and lz.get("db_name") == db_name]
                if holders and "exclusive" not in reclaimed:
                    reclaimed.add("exclusive")
                    work, delete = _capacity_mark(reg, holders), True
                if holders and not work:
                    sys.stderr.write(
                        f"allocator: database {db_name!r} is already held by an "
                        f"exclusive lease (token {holders[0].get('token')}). Retry later "
                        "or use --mode ephemeral.\n"
                    )
                    _report_holders(holders)
                    return _fail("EXCLUSIVE_CONFLICT", 3)

            if not work:
                try:
                    ports = _pick_ports(reg, base, size, n_ports, reserved=reserved_ports)
                except RuntimeError as exc:
                    in_pool = [lz for lz in reg["leases"]
                               if any(_port_in_pool(p, base, size)
                                      for p in (lz.get("ports") or []))]
                    if "ports" not in reclaimed:
                        reclaimed.add("ports")
                        work, delete = _capacity_mark(reg, in_pool), False
                    if not work and port_wait_until is not None \
                            and time.time() < port_wait_until:
                        wait_for_ports = True
                    elif not work:
                        sys.stderr.write(f"allocator: {exc}\n")
                        _report_holders(in_pool)
                        if not in_pool:
                            # Nothing in the registry holds a port of this pool:
                            # the ports are bound by processes the allocator does
                            # not know about (or are still being released). No
                            # lease to release or park would help.
                            return _fail("PORT_POOL_EXHAUSTED", 4,
                                         reason=PORTS_BUSY_OUTSIDE_REGISTRY)
                        return _fail("PORT_POOL_EXHAUSTED", 4)

            if wait_for_ports:
                pass  # nothing to write: sleep outside the lock, then re-pick
            elif work:
                _write_registry(reg)  # the marks - phase A
            else:
                # drop_on_release: True for ephemeral leases where the caller will create
                # the DB via Odoo create-on-init and we must drop it at release/gc.
                # False when --no-create is passed (caller declared they won't create the
                # DB, so there is nothing to drop), and always False for shared/exclusive
                # (those DBs must survive beyond the lease lifetime).
                drop_on_release = (mode == "ephemeral" and not opts.get("no_create"))

                token = uuid.uuid4().hex
                ttl = ttl_opt if ttl_opt is not None else DEFAULT_TTL_S
                now = _now()
                series_val = instances_io.series_of(inst)
                new_lease = {
                    "token": token,
                    "mode": mode,
                    "series": series_val,
                    # The RESOLVED catalog profile ("" when unprofiled), so every
                    # later consumer re-selects the same catalog row (python,
                    # addons) instead of the series' first one.
                    "profile": instances_io.profile_of(inst),
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
                    # The ONE owner constructor (`_owner_block`): run_id (the CANONICAL
                    # ownership key), started_at, and pid + pid_started only when the
                    # caller passes a stable, long-lived --pid - never the transient bash
                    # pid, which dies right after this call and would read as a dead
                    # owner. What protects a pid-less lease now is `owner.session`: the
                    # caller's session anchor, alive for as long as the session is.
                    "owner": _owner_block(run_id, pid_opt, now=now),
                    "ttl_s": ttl,
                    "heartbeat_at": now,
                    "_pg": {"host": host, "user": user, "port": db_port},
                }
                if ttl_opt is not None:
                    new_lease["ttl_explicit"] = True
                reg["leases"].append(new_lease)
                _shed_gone_servers(reg, now)
                _write_registry(reg)
        if wait_for_ports:
            time.sleep(PORT_RETRY_INTERVAL_S)
            continue
        if not work:
            break
        pending, stopped = _capacity_reclaim(work, run_id, delete=delete)  # phase B, unlocked
        if stopped and "ports" in reclaimed and port_wait_until is None:
            port_wait_until = time.time() + PORT_FREE_WAIT_S

    _announce_lease("acquired", token, run_id)
    _emit("ALLOC_TOKEN", token)
    _emit("ALLOC_MODE", mode)
    _emit("ALLOC_DB_NAME", db_name)
    _emit("ALLOC_PORTS", ports)
    _emit("ALLOC_RUN_ID", run_id)
    _emit_instance_common(inst, addons_csv)
    return 0


def _ownership_refusal(lease, opts, verb, consequence):
    """The ownership rule of every verb that STOPS a lease's server - `release`
    and `park` - in ONE place. Returns None when the caller may proceed, else
    the `_fail("NOT_OWNER", 1)` exit code to return. Call it UNDER the registry
    lock, before anything is signalled: a check made outside the lock (or by a
    wrapper before it invokes the verb) is a race window, and the Bash fallback
    path has no wrapper at all.

    It asks the ONE question such a site must answer: did this caller ACQUIRE
    this lease? `owner.run_id` is the answer, so a lease that records one is
    stopped only by the run it names.
    An EMPTY caller run is refused WITH the mismatches, not exempted from them.
    It does not mean "the rightful owner forgot a flag"; it means ownership
    cannot be established at all - and a call that is about to stop a server
    (and, for release, DROP a database) is the last place to guess. The rightful
    owner is never stuck by this: it already holds the run id (`ALLOC_RUN_ID`
    from its own acquire, `INSTANCE_HANDLE.run_id` downstream) and threads it; a
    caller that cannot produce one did not acquire this lease.
    This is the shape `cmd_assert_droppable` has used from the start.
    `cmd_release` was once the outlier: its extra `and caller_run` conjunct read
    as leniency towards the owner while actually licensing a stranger - an
    un-threaded release short-circuited the whole comparison, and one such call
    destroyed a live acceptance database (113 modules + demo data) that a peer
    session had built minutes earlier. `cmd_park` had no check at all, so any
    token holder could stop a peer's live server through it.
    An UNOWNED lease (no run_id recorded at all) proceeds on token-possession.
    That is a deliberate NON-import of `assert_droppable`'s P5.8 arm: P5.8
    guards a BARE-NAME drop, which carries no evidence of ownership whatsoever,
    while these verbs require the token; refusing unowned leases here would
    leave every pre-run_id and never-threaded lease with no exit but `--force`.
    `--force` overrides loudly - it is the human's override, never a dispatched
    agent's way around a refusal.
    `cmd_adopt` deliberately does NOT use this: it re-anchors WHO vouches for a
    lease rather than stopping anything, and it refuses an unowned lease too."""
    caller_run = opts.get("run_id") or opts.get("session", "")
    owner = lease.get("owner") or {}
    owner_run = owner.get("run_id") or owner.get("session_id", "")
    if not owner_run or owner_run == caller_run:
        return None
    caller_desc = repr(caller_run) if caller_run else "NOT NAMED (no --run-id passed)"
    if not opts.get("force"):
        sys.stderr.write(
            "allocator: REFUSING to {verb} the lease for db {db!r}: it is owned by run "
            "{owner!r} and this caller's run is {caller}. A {verb} must name the run that "
            "ACQUIRED the lease - thread the --run-id your own acquire echoed as "
            "ALLOC_RUN_ID (INSTANCE_HANDLE.run_id downstream). If you did not acquire this "
            "lease, leave it alone: holding the token is not ownership, and {consequence}\n"
            .format(verb=verb, db=lease.get("db_name"), owner=owner_run, caller=caller_desc,
                    consequence=consequence))
        return _fail("NOT_OWNER", 1)
    sys.stderr.write(
        f"allocator: force-{verb}ing run {owner_run!r}'s lease (caller run {caller_desc}).\n")
    return None


def cmd_release(opts):
    """Release a lease: validate ownership, stop the server, drop a throwaway
    database through Odoo, delete the row.

    TWO-PHASE, on the same primitive as `gc` (see the GC section header): phase A
    validates ownership and marks the row `reclaiming` under the registry lock;
    phase B stops the server group and drops the database OUTSIDE it (a stop can
    take ~10s and a drop minutes - every acquire/list on the machine waits on
    that lock); phase C deletes the row, or clears the marker of a kept one,
    under the lock again. While marked, the row keeps its ports reserved and
    park/resume/adopt/gc refuse or skip it; a release that dies mid-way leaves a
    marker whose dead pid lets the next release or gc take over."""
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py release <token> --run-id <id>\n")
        return _fail("USAGE", 2)
    instances_path = opts.get("instances")
    # ---- phase A: validate + mark, under the lock -----------------------------
    with _locked():
        reg = _read_registry()
        found = next((lz for lz in reg["leases"] if lz.get("token") == token), None)
        if found is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} (already released?).\n")
            _emit("ALLOC_ALREADY_ABSENT", 1)
            return 0
        if _reclaim_in_progress(found):
            return _fail("RECLAIM_IN_PROGRESS", 11, (
                "lease {t} is being reclaimed right now by {who}; NOTHING was "
                "stopped or dropped by this release.".format(
                    t=token, who=_reclaimer_desc(found))))

        # Ownership guard: `_ownership_refusal` owns the rule (and why it is
        # the rule); release and park share that ONE implementation.
        refused = _ownership_refusal(found, opts, "release", (
            "this lease may be about to drop a live database. --force overrides. "
            "The DB is NOT dropped and the lease is KEPT."))
        if refused is not None:
            return refused

        lease = _mark_reclaiming(found, "released", "release")
        _write_registry(reg)

    # ---- phase B: stop + drop, OUTSIDE the lock -------------------------------
    # Teardown ORDER (L1.2) - stop the group FIRST, then drop - lives in
    # `_stop_and_drop`, the one implementation gc uses too. Every probe and
    # filestore removal below also runs unlocked.
    outcome, rc = SETTLE_DELETE, 0
    if not _stop_and_drop(lease, instances_path):
        # The drop did not happen. Before NAMING anything, ask whether the
        # database is even there: "abandoned" is a claim about the cluster,
        # and a build that crashed before creating anything leaves a lease
        # whose drop can only ever "fail" - un-releasable from both ends.
        db_name = lease.get("db_name", "")
        present = _db_present(lease, instances_path)
        cluster = "{user}@{host}:{port}".format(
            user=lease.get("db_user", "odoo"),
            host=lease.get("db_host", "localhost"),
            port=lease.get("db_port") or "libpq-default")
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
            outcome, rc = SETTLE_KEEP, _fail("DROP_FAILED_KEPT", 1)
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

    # ---- phase C: settle the row, under the lock ------------------------------
    with _locked():
        reg = _read_registry()
        settled = _settle_marked(reg, {token: outcome})
        _write_registry(reg)
    if outcome == SETTLE_DELETE and token in settled:
        # THIS call deleted the row (a racing gc/release that took the row over
        # settles it itself, and this call then says nothing).
        _emit("ALLOC_RELEASED", token)
    return rc


def cmd_heartbeat(opts):
    """Refresh a lease's heartbeat - and, while the row is open under the lock,
    BACKFILL the `owner.pid_started` fingerprint it may be missing and refresh
    its anchor's `seen_at` when the caller belongs to the lease's session.

    Heartbeat is the right (and only) home for the backfill: it is the periodic
    touch by the owner itself, it already writes the registry, and it is the one
    place where recording proof does not race a decision that is being taken
    right now. The backfill is corroboration-gated - see
    `_backfill_pid_fingerprint` for why an ungated one would manufacture false
    proof.

    `heartbeat --session mine` (no token) touches EVERY lease of the caller's
    session in one registry hold - the call a long-lived session process (the
    stdio MCP server) makes periodically so `seen_at` stays fresh."""
    token = opts.get("token")
    session_filter = _session_filter(opts)
    if not token and session_filter is None:
        sys.stderr.write("Usage: allocator.py heartbeat <token> | heartbeat --session mine\n")
        return _fail("USAGE", 2)
    now = _now()
    with _locked():
        reg = _read_registry()
        hits = []
        for lease in reg["leases"]:
            if token and lease.get("token") != token:
                continue
            if session_filter is not None and not session_filter(lease):
                continue
            lease["heartbeat_at"] = now
            _backfill_pid_fingerprint(lease)
            _touch_session(lease, now)
            hits.append(lease.get("token", ""))
        # Every row of the machine, not only the caller's: the MCP server runs
        # this every HEARTBEAT interval, which bounds how long a gone server's
        # pid stays on a live session's row for an older allocator to condemn.
        shed = _shed_gone_servers(reg, now)
        if hits or shed:
            _write_registry(reg)
        elif token:
            sys.stderr.write(f"allocator: no lease with token {token!r}.\n")
            return _fail("LEASE_NOT_FOUND", 1)
    _payload("touched", [t[:8] for t in hits])
    return 0


def cmd_bind(opts):
    """Bind a live server pid onto an EXISTING lease (under flock).

    The exclusive-running spin-up acquires its lease FIRST (reserving the db +
    ports) and only later learns the launched server's pid; `bind` upserts that
    pid (plus its recycling-resistant `pid_started` fingerprint, see
    `_pid_owner_fields`) onto the SAME `owner.pid`/`owner.pid_started` slots the
    shared-acquire path already writes, so release/gc can stop the whole
    process group before the drop (L1.1), and so `_judge` can PROTECT this
    lease once it is verified alive. Refuses an unknown token and a missing
    --pid; reuses the token-scan + write helpers (no second ledger path)."""
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py bind <token> --pid <server_pid>\n")
        return _fail("USAGE", 2)
    pid = _int_opt(opts, "pid", "--pid", None)
    if not pid:
        sys.stderr.write("Usage: allocator.py bind <token> --pid <server_pid>\n")
        return _fail("USAGE", 2)
    with _locked():
        reg = _read_registry()
        hit = False
        for lease in reg["leases"]:
            if lease.get("token") == token:
                # The ONE owner constructor: refreshes pid + fingerprint, `via`,
                # and the anchor of the caller that launched the server.
                lease["owner"] = _owner_block(pid=pid, base=lease.get("owner") or {})
                hit = True
        if hit:
            _shed_gone_servers(reg)
            _write_registry(reg)
        else:
            sys.stderr.write(f"allocator: no lease with token {token!r} to bind.\n")
            return _fail("LEASE_NOT_FOUND", 1)
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
      0. REFUSE a caller that did not acquire the lease (exit 1 NOT_OWNER) -
         release's rule, from the same `_ownership_refusal`. Park stops a live
         server, so it is as destructive to a peer's session as release is; the
         check runs HERE, under the lock, because a pre-check by a wrapper is a
         race window and the Bash fallback path has no wrapper at all.
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
         `_stop_owner_group_if_local` gate `release` and `gc` use - so an
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
    make it durable: the drop still fires at the final `release` (and in `gc`),
    so a caller that parked in order to SAVE a database it spent minutes
    building gets exactly what it asked for now and loses it later - with no
    signal in between unless park emits one. `drop_on_release` is written ONCE,
    by `cmd_acquire`, and no command mutates it afterwards, so there is no
    "convert it to durable" step to point at either; naming the surviving value
    here is the whole intervention. Do NOT trade this report for a mutation, and
    do NOT turn it into a mode-gated refusal: the isolated running lease park
    exists to suspend IS the `ephemeral` one (`persist: exclusive-running` maps
    onto allocator `ephemeral` - docs/reference/INSTANCE-ALLOCATION-MODES.md
    section 5), so refusing that mode would refuse park's only intended client.
    """
    token = opts.get("token")
    if not token:
        sys.stderr.write("Usage: allocator.py park <token> --run-id <id> [--park-ttl <s>] "
                         "[--force]\n")
        return _fail("USAGE", 2)
    try:
        park_ttl = int(opts.get("park_ttl") or DEFAULT_PARK_TTL_S)
    except (TypeError, ValueError):
        sys.stderr.write("allocator: --park-ttl must be an integer number of seconds.\n")
        return _fail("USAGE", 2)
    with _locked():
        reg = _read_registry()
        target = None
        for lease in reg["leases"]:
            if lease.get("token") == token:
                target = lease
                break
        if target is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} to park.\n")
            return _fail("LEASE_NOT_FOUND", 1)
        if _reclaim_in_progress(target):
            return _fail("RECLAIM_IN_PROGRESS", 11,
                         "lease {t} is being reclaimed right now by {who}; it was NOT "
                         "parked.".format(t=token, who=_reclaimer_desc(target)))
        # Park STOPS the owner's process group, so it answers release's
        # ownership question - decided here, under the lock, before any other
        # refusal can leak the lease's state to a stranger and before any signal.
        refused = _ownership_refusal(target, opts, "park", (
            "parking it would stop a server a peer session is using. --force overrides. "
            "NOTHING was stopped and the lease is unchanged."))
        if refused is not None:
            return refused
        if target.get("mode") == "shared":
            sys.stderr.write(
                "allocator: REFUSING to park the `shared` lease on database {db!r}. The shared "
                "render target is the single answer `query --series {series}` gives for a series, "
                "and it is already immune to the owner-pid arms - a parked twin would make that "
                "lookup two-valued and protect nothing. Leave it for its readers: it needs no "
                "teardown, and gc reclaims it once its server is gone.\n".format(
                    db=target.get("db_name"), series=target.get("series"))
            )
            return _fail("SHARED_NOT_PARKABLE", 3)
        # A row whose server exited under a live session had its pid shed
        # (`_shed_gone_server`); it was RUNNING, and parking it (keep the
        # database past the session) is still meaningful.
        target_owner = target.get("owner") or {}
        if target_owner.get("pid") is None and not target_owner.get(SERVER_GONE_KEY):
            sys.stderr.write(
                "allocator: REFUSING to park the lease on database {db!r} - it records no owner "
                "pid, so it is not RUNNING: there is no server process to stop and nothing to "
                "resume into. (An already-parked lease lands here too, because park cleared its "
                "pid; use `resume <token> --pid <server_pid>` to bring it back, or `release` to "
                "finish with it.)\n".format(db=target.get("db_name"))
            )
            return _fail("NOT_RUNNING", 4)
        # Park holds DISK, never MEMORY - stop the group BEFORE the pid that
        # names it is cleared.
        _stop_owner_group_if_local(target)
        _stamp_park(target, park_ttl)
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
    moment that budget lapsed, `gc` would stop the group and drop the database
    under a running instance, and the SubagentStop teardown gate's parked
    exemption would go on exempting that live lease forever - reopening the RAM
    leak. Both harms, from one missing `del`.
    """
    token = opts.get("token")
    pid = opts.get("pid")
    if not token or not pid:
        sys.stderr.write("Usage: allocator.py resume <token> --pid <server_pid>\n")
        return _fail("USAGE", 2)
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        sys.stderr.write("allocator: --pid must be an integer process id.\n")
        return _fail("USAGE", 2)
    with _locked():
        reg = _read_registry()
        target = None
        for lease in reg["leases"]:
            if lease.get("token") == token:
                target = lease
                break
        if target is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} to resume.\n")
            return _fail("LEASE_NOT_FOUND", 1)
        if _reclaim_in_progress(target):
            return _fail("RECLAIM_IN_PROGRESS", 11,
                         "lease {t} is being reclaimed right now by {who}; it was NOT "
                         "resumed - stop the server you launched.".format(
                             t=token, who=_reclaimer_desc(target)))
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
                return _fail("RESUME_RACE", 6)
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - it is NOT parked, "
                "and no live server holds it either. This is the ordinary first launch: bind the "
                "pid with `bind <token> --pid <server_pid>` instead.\n".format(
                    db=target.get("db_name"))
            )
            return _fail("NOT_PARKED", 3)
        present = _db_present(target, opts.get("instances"))
        if present is False:
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - that database is "
                "provably GONE from its cluster (dropped outside the allocator while the lease "
                "was parked). There is nothing left to resume into; `release {token}` cleans the "
                "lease and its filestore up correctly.\n".format(
                    db=target.get("db_name"), token=token)
            )
            return _fail("DB_GONE", 5)
        owner_host = (target.get("owner") or {}).get("host", "")
        if owner_host and owner_host != _host():
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} - it was parked on "
                "host {owner_host!r} and this is {here!r}. A pid integer means nothing off-host, "
                "and that lease's database may live on another cluster entirely.\n".format(
                    db=target.get("db_name"), owner_host=owner_host, here=_host())
            )
            return _fail("WRONG_HOST", 4)
        if not _pid_alive(pid):
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} with pid {pid} - that "
                "pid is not a live process on this host, so it cannot be the server this lease is "
                "resuming into.\n".format(db=target.get("db_name"), pid=pid)
            )
            return _fail("PID_NOT_ALIVE", 4)
        proof, detail = _ownership_proof(target, pid)
        if proof is None:
            sys.stderr.write(
                "allocator: REFUSING to resume the lease on database {db!r} with pid {pid} - "
                "ownership is NOT proven: {detail}. A resume writes that pid onto the lease, so "
                "release/gc would later signal its whole process GROUP; naming a pid this lease "
                "did not spawn is how an unrelated session gets killed.\n".format(
                    db=target.get("db_name"), pid=pid, detail=detail)
            )
            return _fail("OWNERSHIP_UNPROVEN", 4)
        # The set half of the compare-and-set. The three park keys go together:
        # a survivor of any one of them re-governs a live lease by a park budget.
        park_budget = target.get("park_ttl_s")
        target.pop("parked_at", None)
        target.pop("park_ttl_s", None)
        target.pop("parked_boot_id", None)
        # The ONE owner constructor: the resuming caller's anchor now vouches for
        # the lease (a parked lease may be resumed by a later session).
        target["owner"] = _owner_block(pid=pid, base=target.get("owner") or {})
        # Someone parked this lease ON PURPOSE. The resuming session's end
        # (`gc --scope anchor`, or the automatic session-ended arm) must put it
        # back in the park, not drop the database its owner chose to keep.
        _mark_return_to_park(target, park_budget)
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


def _anchor_arg(value):
    """(anchor, is_anchor_spelling) for a `--session` / `--anchor` value.

    `mine` is the caller's own anchor (an empty dict when the caller has none,
    which then matches only by session id); `<pid>:<fingerprint>` is an explicit
    anchor. Anything else is NOT an anchor spelling - for `list`/`release` the
    `--session` flag is also the historical alias of `--run-id`, and a value
    that is not an anchor keeps that meaning."""
    value = (value or "").strip()
    if value == "mine":
        return dict(_caller_anchor() or {}), True
    if ":" in value:
        parsed = session_anchor.parse_anchor(value)
        if parsed is not None:
            return {"pid": parsed[0], "started": parsed[1]}, True
    return None, False


def _lease_of_anchor(lease, anchor, by_session_id=""):
    """True when `lease` is anchored to `anchor` (same pid AND fingerprint; pid
    alone when the anchor names no fingerprint), or - with `by_session_id` - to
    that session id."""
    session = (lease.get("owner") or {}).get("session")
    if not session:
        return False
    if anchor and anchor.get("pid") is not None:
        if anchor.get("started"):
            if session_anchor.same_anchor(session, anchor):
                return True
        else:
            try:
                if int(session.get("pid")) == int(anchor.get("pid")):
                    return True
            except (TypeError, ValueError):
                pass
    return bool(by_session_id) and session.get("session_id") == by_session_id


def _session_filter(opts):
    """A predicate for `--session <pid:fingerprint|mine>`, or None when the flag
    is absent or carries a (legacy) run id instead."""
    anchor, is_anchor = _anchor_arg(opts.get("session"))
    if not is_anchor:
        return None
    sid = _caller_session_id() if (opts.get("session") or "").strip() == "mine" else ""
    return lambda lease: _lease_of_anchor(lease, anchor, sid)


def _gc_targets(reg, scope, anchor):
    """[(lease, reason)] this gc pass will reclaim, in registry order."""
    targets = []
    for lease in reg["leases"]:
        if _reclaim_in_progress(lease):
            continue  # another live gc owns it
        if scope == GC_SCOPE_ANCHOR:
            if not _lease_of_anchor(lease, anchor):
                continue
            # Only what the ended session was RUNNING or holding in reserve: a
            # parked lease was deliberately preserved past the session, and a
            # shared render server is cross-session by design.
            if lease.get("parked_at") is not None or lease.get("mode") == "shared":
                continue
            targets.append((lease, CONDEMN_SESSION_ENDED))
            continue
        reason = _condemn_reason(lease, auto=(scope == GC_SCOPE_DEAD_SESSIONS))
        if reason is not None:
            targets.append((lease, reason))
    return targets


def _gc_action(lease, reason):
    """GC_ACTION_PARK when `lease` goes back to the park instead of being
    reclaimed: it was resumed/adopted out of a deliberate park
    (`owner.return_to_park`) and what ended is its OWNER (session ended, server
    gone), not its park budget. Otherwise GC_ACTION_RECLAIM."""
    if ((lease.get("owner") or {}).get("return_to_park")
            and reason in CAPACITY_REASONS and lease.get("mode") != "shared"):
        return GC_ACTION_PARK
    return GC_ACTION_RECLAIM


def _gc_candidate(lease, reason):
    owner = lease.get("owner") or {}
    return {
        "token": lease.get("token", ""),
        "reason": reason,
        "db_name": lease.get("db_name", ""),
        "mode": lease.get("mode", ""),
        "run_id": owner.get("run_id", ""),
        "state": _lease_state(lease),
        "action": _gc_action(lease, reason),
        "drops_db": bool(lease.get("drop_on_release") and lease.get("db_name")
                         and _gc_action(lease, reason) == GC_ACTION_RECLAIM),
    }


def cmd_gc(opts):
    """Reclaim condemned leases: stop the owner's process group, drop a throwaway
    database through Odoo, delete the row - and report each one.

    --scope all (default)     every arm of `_judge`, including the TTL arm.
    --scope dead-sessions     the AUTOMATIC semantics: an ended session (after
                              ANCHOR_GRACE_S), a dead or recycled server pid, an
                              expired park; never the TTL arm.
    --scope anchor            the running/reserved (never parked, never shared)
                              leases of ONE session anchor - `--anchor
                              <pid:fingerprint>`, default the caller's own. The
                              anchor must no longer be alive (`--force` overrides).
    --dry-run                 list what would be reclaimed; change nothing.

    Two-phase (see the GC section header): the registry lock is NOT held while a
    server is stopped or a database is dropped."""
    scope = (opts.get("scope") or GC_SCOPE_ALL).strip()
    if scope not in GC_SCOPES:
        return _fail("USAGE", 2, "unknown --scope {s!r}; one of: {all}".format(
            s=scope, all=", ".join(GC_SCOPES)))
    dry_run = bool(opts.get("dry_run"))
    run_id = opts.get("run_id") or opts.get("session", "")
    instances_path = opts.get("instances")
    anchor = None
    if scope == GC_SCOPE_ANCHOR:
        if opts.get("anchor"):
            anchor, is_anchor = _anchor_arg(opts.get("anchor"))
            if not is_anchor:
                return _fail("USAGE", 2, "--anchor takes <pid>:<fingerprint> (see `anchor "
                                         "--print`) or `mine`")
        else:
            anchor = _caller_anchor()
        if not anchor or anchor.get("pid") is None:
            return _fail("ANCHOR_REQUIRED", 2, "--scope anchor needs --anchor "
                                               "<pid>:<fingerprint> (the caller has none)")
        if not dry_run and not opts.get("force") \
                and session_anchor.anchor_state(anchor) == session_anchor.STATE_ALIVE:
            return _fail("ANCHOR_ALIVE", 3, (
                "session anchor {a} is still ALIVE - reclaiming a live session's leases "
                "would destroy work in progress. NOTHING was reclaimed. Wait for the "
                "session to end, or pass --force deliberately.".format(
                    a=session_anchor.format_anchor(anchor["pid"], anchor.get("started")))))

    # ---- phase A: choose + mark, under the lock -------------------------------
    with _locked():
        reg = _read_registry()
        targets = _gc_targets(reg, scope, anchor)
        if dry_run:
            candidates = [_gc_candidate(lease, reason) for lease, reason in targets]
            for cand in candidates:
                _emit("ALLOC_WOULD_RECLAIM", cand["token"], multi=True)
            _payload("candidates", candidates)
            _payload("scope", scope)
            _note(f"# would reclaim {len(candidates)} lease(s) (dry-run, scope {scope}; "
                  "nothing was changed)")
            return 0
        now = _now()
        work = []
        for lease, reason in targets:
            work.append((_mark_reclaiming(lease, reason, "gc", now), reason))
        _shed_gone_servers(reg, now)
        # Also persists any re-anchoring `_judge` did for a resumed session.
        _write_registry(reg)

    # ---- phase B: stop + drop, OUTSIDE the lock -------------------------------
    outcomes, records, reparked = {}, {}, []
    for lease, reason in work:
        token = lease.get("token", "")
        if _gc_action(lease, reason) == GC_ACTION_PARK:
            # Back to the park: stop the server (park holds DISK, never MEMORY),
            # keep the database, the filestore and the ports.
            _stop_owner_group_if_local(lease)
            _report_reclaimed(_reclaim_record(lease, reason, "gc", run_id,
                                              action="parked", dropped_db=False))
            outcomes[token] = SETTLE_PARK
            reparked.append(token)
            continue
        # Reap the ORPHAN before reclaiming: a condemned lease's server may still
        # be alive. Stopping its group first frees the RAM and unblocks the drop
        # (a live backend blocks DROP DATABASE). Unproven ownership signals
        # nothing and is reported (`_stop_owner_group_if_local`).
        if not _stop_and_drop(lease, instances_path):
            # Genuine drop failure: the row and the database both still exist,
            # so it is NOT reported as reclaimed; phase C clears the marker so
            # a later gc (or the owner's release) can retry.
            outcomes[token] = SETTLE_KEEP
            continue
        record = _reclaim_record(lease, reason, "gc", run_id)
        # Reported as soon as the destruction happened, not after phase C: if this
        # process dies before C, the account already exists and the row (still
        # marked by a dead pid) is simply retaken by the next gc.
        _report_reclaimed(record)
        outcomes[token], records[token] = SETTLE_DELETE, record

    # ---- phase C: settle the rows, under the lock -----------------------------
    reclaimed, settled = [], set()
    if work:
        with _locked():
            reg = _read_registry()
            settled = _settle_marked(reg, outcomes)
            _write_registry(reg)
        reclaimed = [rec for token, rec in records.items() if token in settled]
    parked_back = [t for t in reparked if t in settled]
    for token in parked_back:
        _emit("ALLOC_PARKED", token, multi=True)
    _payload("parked", parked_back)
    # The long-standing PROTOCOL output, byte-for-byte (a consumer evals it): one
    # ALLOC_RECLAIMED= line per lease plus the count. The per-lease account of WHY
    # went to stderr + the evidence log as it happened.
    for rec in reclaimed:
        _emit("ALLOC_RECLAIMED", rec.get("token", ""), multi=True)
    _payload("reclaimed", reclaimed)
    _payload("scope", scope)
    _note(f"# reclaimed {len(reclaimed)} stale lease(s)")
    if parked_back:
        _note(f"# returned {len(parked_back)} resumed lease(s) to the park")
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
    items = _load_catalog(path)
    if not items:
        sys.stderr.write(f"allocator: no instances declared in {path}; nothing to reap.\n")
        return 0

    try:
        min_age_s = float(opts.get("min_age_s") or DEFAULT_REAP_MIN_AGE_S)
    except ValueError:
        raise _UsageError("--min-age-s must be a number of seconds, got {v!r}".format(
            v=opts.get("min_age_s")))
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
        _emit("REAP_SKIPPED", f"{name}: {reason}", multi=True)

    dropped, failed = [], []
    for db in all_candidates:
        age_h = (db["age_s"] or 0) / 3600
        size_mb = (db["size_bytes"] or 0) / (1024 * 1024)
        _emit("REAP_CANDIDATE", f"{db['name']} age_h={age_h:.1f} size_mb={size_mb:.1f}",
              multi=True)
        if yes:
            if _dropdb(db["host"], db["user"], db["name"], db["port"],
                       db.get("db_run_mode", ""), db.get("db_container", "")):
                _drop_filestore(db["name"])
                dropped.append(db["name"])
            else:
                failed.append(db["name"])

    if yes:
        for name in dropped:
            _emit("REAP_DROPPED", name, multi=True)
        _note(f"# reaped {len(dropped)} orphan(s), {len(failed)} failure(s)")
        return _fail("REAP_DROP_FAILED", 1) if failed else 0

    _note(f"# {len(all_candidates)} orphan candidate(s) found (list-only - pass --yes to drop)")
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
        return _fail("NO_INSTANCE", 1)
    host = inst.get("db_host", "localhost")
    user = inst.get("db_user", "odoo")
    port = inst.get("db_port", "")

    auth_state, auth_why = _db_auth(inst, host, user, port)
    _emit("DB_AUTH", auth_state)
    _emit("DB_AUTH_WHY", auth_why)
    if auth_state in ("denied", "unreachable"):
        return (_fail("DB_AUTH_DENIED", EXIT_AUTH_DENIED) if auth_state == "denied"
                else _fail("DB_UNREACHABLE", EXIT_UNREACHABLE))

    verdict, why = _can_createdb(inst, host, user, port)
    if isinstance(verdict, _ConnBlocked):
        # Route 1 saw the connection fail after the preflight said otherwise (a
        # cluster that went away in between, or a preflight that could not run).
        # The connection verdict still wins over any client surface.
        _emit("CREATEDB", "undeterminable")
        _emit("CREATEDB_WHY", why)
        return _fail(_conn_blocked_code(verdict), verdict.exit_code)
    if verdict is True:
        _emit("CREATEDB", "true")
        return 0
    if verdict is False:
        _emit("CREATEDB", "false")
        return _fail("NO_CREATEDB", 6)
    _emit("CREATEDB", "undeterminable")
    _emit("CREATEDB_WHY", why)
    return _fail("CREATEDB_UNDETERMINABLE", 7)


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
        return _fail("NO_INSTANCE", 1)
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
        return _fail(_conn_blocked_code(verdict), verdict.exit_code)
    if verdict is True:
        _emit("CREATEDB", "true")
        return 0
    if verdict is False:
        _emit("CREATEDB", "false")
        return _fail("NO_CREATEDB", 6)
    _emit("CREATEDB", "undeterminable")
    _emit("CREATEDB_WHY", why)
    return _fail("CREATEDB_UNDETERMINABLE", 7)


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
        and not _reclaim_in_progress(lz)
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
    return _fail("NOT_FOUND", 1)


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
        return _fail("USAGE", 2)
    for lease in reg["leases"]:
        if (lease.get("mode") == "shared"
                and lease.get("series") == series
                and not _reclaim_in_progress(lease)
                and not _is_stale(lease)):
            _emit("ALLOC_TOKEN", lease.get("token", ""))
            _emit("ALLOC_MODE", "shared")
            _emit("ALLOC_DB_NAME", lease.get("db_name", ""))
            _emit("ALLOC_PORTS", lease.get("ports", []))
            return 0
    return _fail("NOT_FOUND", 1)


def cmd_list(opts):
    """The registry as JSON, optionally filtered and annotated.

    Filters (all combine with AND): `--run-id <id>` (exact owner run; `--session
    <run>` is its historical alias), `--older-than <s>`, `--tokens a,b` (full
    tokens or >=8-char prefixes), `--session <pid:fingerprint|mine>` (leases
    anchored to that session; `mine` also matches the caller's session id).
    `--with-verdict` adds `verdict` (`_verdict`: state, protected_by, condemn,
    condemn_auto, anchor_state, anchor_alive) to every lease - the SSOT a
    consumer reads instead of re-deriving liveness. Read-only: no lock, no write."""
    reg = _read_registry()
    # Audit filters. A run auditing its own leaks used to grep this output for its run-id PREFIX,
    # which is not a thing this tool offers and not a thing prefix matching can do reliably: the
    # one leak it caught was caught because an INVENTED run id happened to share a prefix with the
    # real one. `--run-id` filters on the recorded owner exactly, and `--older-than` finds what an
    # id-based audit structurally cannot - a lease whose owner string matches nothing the run
    # knows about, which is precisely the shape a descendant that minted its own id produces.
    session_filter = _session_filter(opts)
    want_run = opts.get("run_id") or ("" if session_filter else opts.get("session")) or ""
    older_than = opts.get("older_than")
    try:
        cutoff = (_now() - float(older_than)) if older_than else None
    except ValueError:
        raise _UsageError("--older-than must be a number of seconds, got {v!r}".format(
            v=older_than))
    wanted_tokens = [t.strip() for t in (opts.get("tokens") or "").split(",") if t.strip()]
    kept = []
    for lease in reg.get("leases", []):
        owner = lease.get("owner") or {}
        if want_run and (owner.get("run_id") or owner.get("session_id") or "") != want_run:
            continue
        if cutoff is not None and float(owner.get("started_at") or 0) > cutoff:
            continue
        if wanted_tokens:
            token = lease.get("token") or ""
            if not any(token == t or (len(t) >= 8 and token.startswith(t))
                       for t in wanted_tokens):
                continue
        if session_filter is not None and not session_filter(lease):
            continue
        if opts.get("with_verdict"):
            # Judged on a COPY: `_judge` may re-anchor a resumed session's lease in
            # memory, and a read-only verb must print the row as it is on disk.
            lease["verdict"] = _verdict(json.loads(json.dumps(lease)))
        kept.append(lease)
    reg["leases"] = kept
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
    if _OUT["json"]:
        _payload("schema_version", reg.get("schema_version", 1))
        _payload("leases", reg["leases"])
        return 0
    print(json.dumps(reg, indent=2, sort_keys=True))
    return 0


def cmd_anchor(opts):
    """Print the caller's session anchor, shell-eval-able:
        ODOO_AI_SESSION_ANCHOR=<pid>:<fingerprint>
        ODOO_AI_SESSION_ID=<CLAUDE_CODE_SESSION_ID or empty>
        ODOO_AI_ANCHOR_SOURCE=env|claude-pid|ancestor
        ODOO_AI_ANCHOR_STATE=alive|dead|unknown
    Exporting the first line hands the SAME anchor to a process that would not
    discover it itself (a detached worker, a hook). Exit 5 (NO_ANCHOR) when the
    caller is not inside an agent session. `--print` is accepted and implied."""
    anchor = _caller_anchor()
    if not anchor:
        return _fail("NO_ANCHOR", 5, "no session anchor: not inside an agent session "
                                     "(no ODOO_AI_SESSION_ANCHOR, no CLAUDE_PID, no agent "
                                     "CLI ancestor) - or anchoring is disabled")
    _emit(session_anchor.ANCHOR_ENV,
          session_anchor.format_anchor(anchor["pid"], anchor.get("started")))
    _emit("ODOO_AI_SESSION_ID", anchor.get("session_id", "") or "")
    _emit("ODOO_AI_ANCHOR_SOURCE", anchor.get("source", ""))
    _emit("ODOO_AI_ANCHOR_STATE", session_anchor.anchor_state(anchor))
    return 0


def cmd_adopt(opts):
    """Re-anchor a lease onto the CALLER's session: `adopt <token> --run-id <id>`.

    The hand-over verb for a lease that must outlive the session that acquired
    it inside the same run (a resumed session under a new id, a worker another
    process launched). It changes WHO vouches for the lease's liveness - never
    its owner run, its database, its ports or its mode - so it requires the
    ownership the release path requires (the run id recorded on the lease),
    the same host, and a caller that HAS an anchor."""
    token = opts.get("token")
    run_id = opts.get("run_id") or ""
    if not token or not run_id:
        sys.stderr.write("Usage: allocator.py adopt <token> --run-id <id>\n")
        return _fail("USAGE", 2)
    anchor = _caller_anchor()
    if not anchor:
        return _fail("NO_ANCHOR", 5, "adopt needs a caller with a session anchor; this "
                                     "process has none, so there is nothing to anchor to")
    with _locked():
        reg = _read_registry()
        target = next((lz for lz in reg["leases"] if lz.get("token") == token), None)
        if target is None:
            sys.stderr.write(f"allocator: no lease with token {token!r} to adopt.\n")
            return _fail("LEASE_NOT_FOUND", 1)
        owner = target.get("owner") or {}
        owner_run = owner.get("run_id") or owner.get("session_id", "")
        if owner_run != run_id:
            return _fail("NOT_OWNER", 1, (
                "REFUSING to adopt the lease for db {db!r}: it is owned by run {o!r} and "
                "this caller named {c!r}. Only the run that acquired a lease may re-anchor "
                "it.".format(db=target.get("db_name"), o=owner_run or "<none recorded>",
                             c=run_id)))
        if owner.get("host") and owner.get("host") != _host():
            return _fail("WRONG_HOST", 4, (
                "REFUSING to adopt the lease for db {db!r}: it was recorded on host {h!r} "
                "and this is {here!r}.".format(db=target.get("db_name"), h=owner.get("host"),
                                               here=_host())))
        if _reclaim_in_progress(target):
            return _fail("RECLAIM_IN_PROGRESS", 11,
                         "lease {t} is being reclaimed right now by {who}; it was NOT "
                         "adopted.".format(t=token, who=_reclaimer_desc(target)))
        now = _now()
        owner["session"] = _session_block(anchor, now)
        target["owner"] = owner
        if target.get("parked_at") is not None:
            # Adopting a parked lease: when the adopting session later resumes and
            # then ends, the lease goes back to the park (see `_mark_return_to_park`).
            _mark_return_to_park(target, target.get("park_ttl_s"))
        target["heartbeat_at"] = now
        _shed_gone_servers(reg, now)
        _write_registry(reg)
    _announce_lease("adopted", token, run_id)
    _emit("ALLOC_TOKEN", token)
    _emit(session_anchor.ANCHOR_ENV,
          session_anchor.format_anchor(anchor["pid"], anchor.get("started")))
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
        return _fail("USAGE", 2)
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
                    return _fail("DB_HELD_BY_OTHER_RUN", 1)
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
                return _fail("DB_HELD_UNOWNED", 1)
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
    "--park-ttl": "park_ttl", "--state": "state", "--older-than": "older_than",
    "--scope": "scope", "--anchor": "anchor", "--tokens": "tokens", "--format": "format",
}
_BOOL_KEYS = {
    "--no-create": "no_create", "--force": "force", "--show-tokens": "show_tokens",
    "--yes": "yes", "--force-forget": "force_forget", "--force-attach": "force_attach",
    "--allow-unowned": "allow_unowned", "--dry-run": "dry_run",
    "--with-verdict": "with_verdict", "--print": "print",
}
# `--format` values. `shell` (the default) is the KEY=VALUE eval protocol;
# `json` prints exactly ONE JSON object on stdout:
#   {"ok": bool, "rc": int, "error": {"code", "message"} | null, "fields": {...}}
OUTPUT_FORMATS = ("shell", "json")
# Every verb `main()` dispatches - the SSOT of the unknown-subcommand message.
VERBS = (
    "acquire", "release", "bind", "park", "resume", "heartbeat", "adopt", "gc",
    "reap-orphans", "list", "query", "assert-droppable", "can-createdb",
    "db-preflight", "anchor",
)
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


def _dispatch(cmd, opts, pos):
    token_verbs = ("release", "heartbeat", "bind", "park", "resume", "adopt")
    if cmd in token_verbs:
        opts.setdefault("token", pos[0] if pos else None)
    handlers = {
        "acquire": cmd_acquire, "release": cmd_release, "heartbeat": cmd_heartbeat,
        "bind": cmd_bind, "park": cmd_park, "resume": cmd_resume, "adopt": cmd_adopt,
        "gc": cmd_gc, "reap-orphans": cmd_reap_orphans, "list": cmd_list,
        "query": cmd_query, "can-createdb": cmd_can_createdb,
        "db-preflight": cmd_db_preflight, "assert-droppable": cmd_assert_droppable,
        "anchor": cmd_anchor,
    }
    handler = handlers.get(cmd)
    if handler is None:
        sys.stderr.write(
            f"Unknown subcommand: {cmd!r}. Use " + "|".join(VERBS) + ".\n"
        )
        return _fail("USAGE", 2)
    return handler(opts)


def _run_command(cmd, rest):
    opts, pos, unknown = _parse(rest)
    fmt = (opts.get("format") or "shell").strip().lower()
    _reset_output(json_mode=(fmt == "json"))
    if fmt not in OUTPUT_FORMATS:
        return _fail("USAGE", 2, "unknown --format {f!r}; one of: {a}".format(
            f=fmt, a=", ".join(OUTPUT_FORMATS)))
    if unknown:
        sys.stderr.write(
            f"allocator: unknown flag(s) {' '.join(unknown)}. "
            "Known flags: " + " ".join(sorted(set(_FLAG_KEYS) | set(_BOOL_KEYS))) + "\n"
        )
        return _fail("USAGE", 2)
    try:
        return _dispatch(cmd, opts, pos)
    except _UsageError as exc:
        return _fail("USAGE", 2, str(exc))
    except _CatalogUnavailable as exc:
        return _fail("NO_INSTANCE_CATALOG", None, str(exc))


def main(argv):
    _reset_output(json_mode=False)
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
    rc = _run_command(cmd, rest)
    if _OUT["json"]:
        error = _OUT["error"]
        if rc != 0 and error is None:
            error = {"code": "UNSPECIFIED", "message": ERROR_CODES["UNSPECIFIED"]["summary"]}
        print(json.dumps({"ok": rc == 0, "rc": rc, "error": error if rc != 0 else None,
                          "fields": _OUT["fields"]}, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
