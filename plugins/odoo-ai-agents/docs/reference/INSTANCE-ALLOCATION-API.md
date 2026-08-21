# Odoo instance allocation - allocator API, database lifecycle and acquire exit codes

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns the `allocator.py` command surface, who creates and
drops the database behind a lease, and the exit codes an `acquire` refuses with.

## 6. Allocator API (`scripts/lib/allocator.py`)

A thin Python CLI/lib next to `instances_io.py`. Emits shell-eval-able `ALLOC_*` lines like the
existing reader, so shell consumers stay simple.

| Command | Behavior |
|---------|----------|
| `acquire --series <X.Y> --mode <readonly\|ephemeral\|exclusive\|shared> [--profile <P>] [--ports <N>] [--port <P>] [--pid <pid>] [--ttl <s>] [--run-id <id>] (alias --session)` | resolve catalog instance for series (and profile when supplied); under flock: GC stale leases, pick N free ports from the pool (registry-set ∪ live `bind()` probe) when `--ports N>0`, choose db_name (ephemeral: unique reserved name; else declared), write the lease atomically (B2: does NOT create the DB - the caller's `-i` run performs Odoo create-on-init); for a mode that will build, gate on DB_AUTH then CREATEDB and REFUSE per §6.6 (exits 6/7/8/9, no lease written) - both asked of the CLUSTER as LIVE queries, never inferred from installed binaries, and BOUNDED by `$ODOO_AI_PG_PROBE_TIMEOUT`; print `ALLOC_TOKEN/ALLOC_SERIES/ALLOC_PROFILE/ALLOC_DB_NAME/ALLOC_PORTS (space-separated)/ALLOC_PYTHON/ALLOC_ADDONS_PATH/ALLOC_DB_HOST/ALLOC_DB_USER/ALLOC_DB_PORT/ALLOC_RUN_ID`. `--run-id` is the canonical ownership key (the intake Phase P run id); `--session` is kept only as a back-compat alias for the same slot. When `--profile <P>` is given and `db_name` is not set explicitly in the catalog, `db_name` defaults to `odoo_<series_slug>_<profile_slug>` (e.g. `odoo_17_0_minimal`). **`shared`**: attach to the live `(series, db_name)` lease if one exists (emit `ALLOC_ATTACHED=1`) else mint one with `drop_on_release=false`; record the KNOWN port verbatim via `--port` (not pooled) and the long-lived server pid via `--pid` (idempotent upsert when a later call supplies a newer pid) - never blocks a second holder |
| `query --series <X.Y> [--state parked] [--run-id <id>] [--force-attach]` | read-only cross-session discovery. Default (no `--state`): the live `shared` lease for the series (`ALLOC_TOKEN/ALLOC_MODE/ALLOC_DB_NAME/ALLOC_PORTS`), or exit 1 when none - unchanged, so no existing caller moves. `--state parked`: the resumable PARKED lease for the series instead (adds `ALLOC_PARKED_AT`), so a returning dispatch finds the instance an earlier one suspended rather than rebuilding it. A parked lease has no live owner by construction, so it is HOST-and-SERIES scoped: this run's own parked lease is returned silently; another run's parked lease ON THIS HOST is returned with `ALLOC_ATTACHED_FROM_RUN=<owning run>` so the attach is REPORTED rather than gated; a parked lease on a different host needs `--force-attach` (its database may live on another cluster). A lease its own budget has already condemned is skipped, and so is a same-host lease whose database is PROVABLY gone - that skip names `release <token>` and is the PRE-LAUNCH half of "no server is ever started against a database that is gone" (the only rung that can be pre-launch; `resume` needs a live pid). "Could not look" is not "absent" and is still offered. Does not mutate the registry |
| `bind <token> --pid <server_pid>` | under flock: verify the token, then UPSERT the live server pid onto that lease's `owner.pid` (the same slot the `shared` acquire path writes). Refuses an unknown token or a missing `--pid`. Used by the `exclusive-running` spin-up: the caller acquires the lease first (reserving db + ports), then binds the launched server pid so `release`/`gc` can stop the whole process GROUP before the drop. Also upgrades gc for exclusive leases from ttl-only to fast-path pid-dead reclaim, for free |
| `release <token> --run-id <id> [--force] [--force-forget]` | under flock: verify token match, then apply the ownership guard (`INSTANCE-ALLOCATION-GUARDS.md` §6.3) - a lease that records an owner run is released ONLY by that run: any other `--run-id`, and an ABSENT one, is refused unless `--force` (an absent caller run is ownership not established, never ownership assumed; an UNOWNED lease still releases on token possession). On success, ORDER IS MANDATORY: (1) if the lease carries an `owner.pid` on THIS host that is alive AND PROVEN to be this lease's own server (`_stop_owner_group_if_local` -> `_ownership_proof`; an unproven pid is reported and NEVER signalled), STOP the server's process GROUP first (`_stop_group`: SIGTERM -> bounded wait -> group SIGKILL - reaps master + HTTP workers + cron + gevent/longpolling + any `--dev=reload` watchdog); (2) THEN, if `drop_on_release`, drop the ephemeral DB through Odoo (`scripts/lib/odoo_db.py`; raw `dropdb` as logged fallback when venv unavailable). Stopping the group first releases the DB connections that would otherwise block `DROP DATABASE`; `odoo_db.py`'s `pg_terminate_backend` remains as a second belt. A lease with no live local pid (legacy pre-setsid / shared / already-dead) skips the stop - no-op, always safe. A drop that did not happen is CLASSIFIED by whether the database exists before anything is named or released (`INSTANCE-ALLOCATION-GUARDS.md` §6.7) |
| `park <token> [--park-ttl <s>]` | under flock: SUSPEND a RUNNING lease without destroying anything it reserved. Order is mandatory: (1) refuse a `shared` lease (exit 3 - the shared row is the single answer `query --series` gives, and a parked twin would make that lookup two-valued) and a lease with no `owner.pid` (exit 4 - not RUNNING: nothing to stop, and an already-parked lease lands here because park cleared its pid, so a second park cannot re-stamp a fresh budget onto an old one); (2) STOP the owner's process GROUP through the same `_stop_owner_group_if_local` gate `release`/`gc` use, so an unproven pid is still never signalled - park holds DISK, never MEMORY, and stopping BEFORE the pid is cleared is what keeps that group reachable; (3) clear `owner.pid`/`owner.pid_started` and stamp `parked_at`/`park_ttl_s`/`parked_boot_id`. `db_name`, `ports` and `drop_on_release` are untouched: the database, the filestore and the port reservation are exactly what parking a lease exists to keep |
| `resume <token> --pid <server_pid>` | under flock, as ONE compare-and-set: the lease must already be a PARKED lease, and a lease that is NOT parked splits by whether a LIVE same-host `owner.pid` already holds it - no (exit 3: the ordinary first launch, and the code `50-instance-spinup.sh`'s `_bind_exclusive` branches on to fall back to `bind`), yes (exit 6: another caller won the resume race, so its caller must STOP the server it just launched and never `bind` over the winner). Its database must not have been dropped while the lease was parked (exit 5, naming `release` as the next step; "could not look" is not "absent" and does not refuse), and the named pid must be alive on this host AND corroborated as this lease's own server by `_ownership_proof` (exit 4). Only then does it DELETE `parked_at`/`park_ttl_s`/`parked_boot_id`, write `owner.pid`/`owner.pid_started` and refresh `heartbeat_at`. The DELETE is load-bearing: a resumed lease that kept its park keys would be governed by `park_ttl_s` alone, so `gc` would drop the database under a live server, and the SubagentStop teardown gate would exempt that live lease forever. Because the pid must be live, resume runs AFTER the launch - so every refusal here obliges its caller to tear the launched server down (`INSTANCE-ALLOCATION-RECLAIM.md` §8, "A resume refused AFTER the launch") |
| `heartbeat <token>` | bump `heartbeat_at` - matters ONLY for a lease whose liveness `_is_stale` cannot prove (a different host, or no `--pid` ever recorded); a same-host lease with a verified-alive pid is protected regardless of heartbeat freshness |
| `gc` | under flock: reclaim leases per `_is_stale` (`INSTANCE-ALLOCATION-RECLAIM.md` §7 - liveness is AUTHORITATIVE, not a condemn-only signal), stopping a condemned lease's process group before the reclaim - but ONLY when that pid is PROVEN to be the lease's own server (`_ownership_proof`); a proven-recycled or unprovable pid is reported and NEVER signalled, and the row is reclaimed either way. For each reclaimed `drop_on_release` lease: drop through the same ladder §6.1 defines |
| `reap-orphans [--min-age-s <s>] [--yes] [--instances <path>]` | DB-side sweep INDEPENDENT of the lease registry, for the class `gc` cannot reach: an ephemeral-shaped DB carrying NO lease reference at all. Predicate, outputs and the fail-closed age rule: `INSTANCE-ALLOCATION-RECLAIM.md` §6.5. Default is list-only; `--yes` is required to drop |
| `assert-droppable --db-name <db> [--run-id <id>] [--force]` | read-only, under flock: exits non-zero when a FRESH (non-stale) lease on `<db>` is owned by a DIFFERENT run (names the owning run id), OR when it is UNOWNED (no run_id recorded at all - unowned does not mean "safe to drop"); exits 0 when owned by the caller, the lease is stale, no lease exists, or `--force` is passed. Lets a bare-name drop confirm a DB is unmanaged before touching it (`INSTANCE-ALLOCATION-GUARDS.md` §6.3) |
| `db-preflight --series <X.Y> [--profile <P>] [--instances <path>]` | read-only: print `DB_AUTH=ok\|denied\|unreachable\|unknown` + `DB_AUTH_WHY`, then `CREATEDB` + `CREATEDB_WHY`, exiting per §6.6. The ONE question every reporting caller asks (`05-prereq-check.sh`, `45-venv.sh`) instead of re-deriving half of it. Writes NO lease |
| `list` | print current leases (debug); tokens are redacted to an 8-char fingerprint by default - pass `--show-tokens` to print them in full |

`acquire`/`release`/`gc` all do their read-modify-write **inside one `fcntl.flock`** so concurrent
allocators serialise on the registry; the lock is held only for the short critical section, not for
the duration of the Odoo run.

### 6.1 DB lifecycle ownership (B2 model: caller-side create, through-Odoo drop)

`ephemeral` acquire reserves a unique DB name + ports but does NOT create the DB. The caller's
odoo-bin run performs Odoo create-on-init, which builds the DB - memory-cap policy (HARD RULE,
never omit the `ulimit -Sv` guard): `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`:

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d <db> -i <modules> --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

On `release`/`gc` the allocator drops it through Odoo via `scripts/lib/odoo_db.py` (which invokes
the Odoo `db` management API under the correct venv). The declared client surface is the allocator's
logged last-resort fallback, and ONLY when the through-Odoo route never reached the database at all
(exit 10 no venv, 8 authentication refused, 9 cluster unreachable) AND the lease names a throwaway
`<prefix>_t_<hex8>` database it is allowed to destroy; a drop that was ATTEMPTED and failed keeps
the DB and the lease, and absence is verified before any client-side drop reports success. The
`python`/`db_host`/`db_user`/`db_port` fields stored in the lease allow drop-time to reconstruct the
right invocation - against the right Postgres cluster, when `db_port` is set - even after the caller
process exits.

**`ephemeral` NEVER degrades** - it exits 0 with a fresh `<prefix>_t_<hex8>` DB or refuses, writing
no lease. The exit codes and their remedies live in §6.6; do not restate them here.

**Consumer contract under B2:** a caller that acquires an ephemeral lease then runs
`odoo-bin -d $ALLOC_DB_NAME` WITHOUT `-i` (bare launch or a `-u` update) fails - the DB does not
exist. Always: acquire -> `-i <modules>` (create-on-init) -> use DB -> release. For operations
needing a pre-existing populated DB (translation reload `-u`, a server-start against existing
data), use `--mode exclusive` on a declared DB instead.

### 6.6 Acquire exit codes - 6, 7, 8 and 9 are REFUSALS, never a degrade

An `ephemeral` acquire either returns an ISOLATED throwaway DB or fails. It never hands back an
`exclusive` lease on the declared, long-lived database: the caller - not the allocator - owns any
trade of isolation for serialisation, and must state it by re-dispatching with an explicit
`--mode exclusive` (and saying so in its report).

**AUTHENTICATION is evaluated FIRST, and for every mode that will build** (`ephemeral` plus
`exclusive`; skipped for `--no-create`, `readonly` and `shared`). Odoo opens its maintenance-database
connection for every `-d <name>` run before any module loads, so a cluster that refuses Odoo kills an
update or a test exactly as it kills a create - and a CREATEDB verdict is never emitted beside a
proven refusal.

| Exit | Meaning | Remedy |
|------|---------|--------|
| `6` | the role positively LACKS CREATEDB | grant that role CREATEDB, then retry |
| `7` | CREATEDB capability UNDETERMINABLE - no route could answer | declare what is missing (below) |
| `8` | `DB_AUTH=denied` - Odoo cannot authenticate to the cluster | run `/odoo-ai-agents:odoo-setup`; or export `ODOO_PG_PASSWORD` for a cluster that cannot be reconfigured |
| `9` | `DB_AUTH=unreachable` - the cluster did not answer at all | start the cluster, or correct `db_host`/`db_port` |

An UNDETERMINABLE authentication state NEVER blocks - only a PROVEN 8 or 9 does. The capability is
asked of the CLUSTER over two routes tried in order; the first that ANSWERS wins, and `7` means
every route failed:

| # | Route | Why it exists |
|---|-------|---------------|
| 1 | the instance's own declared `python` (`odoo_db.py can-createdb`) | the same connection resolution the drop path and every build use. A proven 8 or 9 here STOPS the ladder: another surface can only answer about a different connection |
| 2 | the declared `db_run_mode` client surface (`psql` natively or in `db_container`) | the route a `run_mode = "docker"` instance takes - compose launches it, so it declares no `python`, and without this route its `ephemeral` acquire could only ever exit 7 |

Exit 7 therefore resolves by declaring what is missing - `45-venv.sh record-env --series <X.Y>`
records `python` + `odoo_root` (`INSTANCE-ALLOCATION-REGISTRY.md` §4.1 - "cannot import odoo" means an undeclared `odoo_root`, NOT a
broken venv) and `db_run_mode`/`db_container` - or by starting a cluster that is not running.

Every Postgres call the allocator makes is BOUNDED by `$ODOO_AI_PG_PROBE_TIMEOUT` (default 10s; a
mutating call gets a longer bound derived from the same knob - ONE policy, shared with
`pg_mode.sh`). psycopg2 connects with no libpq connect timeout, so unbounded, an unreachable
cluster would leave `acquire` with no lease, no refusal and no verdict at all. A bound that elapses
is UNDETERMINED (exit 7), never a factual "no".
