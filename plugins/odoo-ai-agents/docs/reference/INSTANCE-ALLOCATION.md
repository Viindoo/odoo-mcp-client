# Technical Design - concurrent Odoo instance allocation (user/global, cross-session)

Status: IMPLEMENTED
Audience: plugin maintainers + global contributors. This is a design contract, not code.
Related: `snippets/instance-resolution.md`, `snippets/venv-resolution.md`,
`snippets/instance-handle-contract.md`, `snippets/state-root-resolution.md`,
`snippets/odoo-bin-resource-limits.md`, `docs/reference/INSTANCE-LIFECYCLE.md`,
`skills/_shared/concurrency-guard.md`, `scripts/lib/instances_io.py`, `scripts/lib/odoo_db.py`,
`scripts/setup-steps/40-instance-profile.sh`, `scripts/setup-steps/50-instance-spinup.sh`.

> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for instance lifecycle operations (build, drop, init, update, test). The
> allocator is the low-level coordination primitive they use internally. Persistent operation logs
> are written to `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## 1. Problem & intent

Multiple subagents in one Claude Code session - and multiple sessions on one host - run Odoo
operations concurrently. Some agents only READ a running instance (share is fine); some need an
ISOLATED database (tests, `-i`/`-u`, a throwaway dev server). Today there is no coordination.

What exists is **declaration + resolution only**: `$ODOO_AI_HOME/instances.toml` is a machine-global
catalog (`series`, one `http_port`, one `db_name`, `db_host`/`db_user`, `addons_path`, venv
`python`) and `instances_io.py` picks the first instance matching a series. There is **no
in-use/owner/lease field, no per-run database or port, no PID/runtime registry, and no
mutual-exclusion primitive** (`flock`/`fcntl`/`.lock`/pidfile = 0 occurrences in the repo).
`concurrency-guard.md` governs only agent fan-out (OOM / model-weighted budget) - it says nothing
about DB or port ownership.

**Concurrency gap (verified):** OSM reads are safe (the session-pin race was neutralised by passing
the concrete version every call). But every live-instance mutation is unsafe under concurrency:
two agents/sessions resolve the SAME single `db_name`+`http_port`, so concurrent `--test-enable`,
`-i`/`-u`, or spin-up collide on the port or corrupt each other's database. Nothing serialises them.

**Intent:** a portable, user/global allocator that hands each concurrent caller either a shared
read-only handle or an isolated (db [+ port]) lease, reclaims leases when an agent/session dies, and
assumes nothing about this one machine.

## 2. Constraints (non-negotiable)

- **Portable / public / global.** No hardcoded paths (`/home/<user>/...`), no assumption about this
  host's Postgres, ports, or layout. All runtime state under `$ODOO_AI_HOME` (default `~/.odoo-ai`).
  The user declares their Postgres + venv via `instances.toml` (written by `/odoo-setup`).
- **No live Odoo MCP.** The `mcp__odoo__*` server is out of scope by existing design; the
  allocator coordinates only locally-declared instances.
- **Backward compatible.** Existing `instances.toml` files keep parsing; the read-only resolution
  path (`instance-resolution.md`) is unchanged for callers that only need a URL.
- **POSIX (Linux + macOS).** Concurrency primitive is `fcntl.flock` in Python (present on both),
  never the `flock(1)` CLI (absent on stock macOS). Windows is explicitly out of scope for v1.

## 3. Goals / non-goals

Goals: (1) distinct concurrent callers never share a mutable DB unless they ask to; (2) port
collisions impossible; (3) a dead agent/session never holds a resource forever; (4) zero new
machine assumptions; (5) one small Python helper + a documented protocol, wired into existing
consumers.

Non-goals: a daemon/service; cross-HOST coordination (each host has its own registry); managing the
external `mcp__odoo__*` instances; replacing `instances.toml` (it stays the catalog).

## 4. Architecture - two layers

| Layer | Where | Nature | Owner |
|-------|-------|--------|-------|
| **Catalog** | `$ODOO_AI_HOME/instances.toml` (existing) | static capability: where Postgres is, which venv, base port, addons | the user (via `/odoo-setup`) |
| **Runtime Lease Registry** | `$ODOO_AI_HOME/runtime/leases.json` (NEW) | dynamic: who currently holds which db/port | the allocator |

The catalog answers "what CAN run here"; the registry answers "what IS running/held right now".
Keeping them separate means the catalog stays a clean, hand-editable, commit-free declaration while
all volatile state lives in one machine-global file the allocator owns.

**Both layers are Tier-1 - flat under `$ODOO_AI_HOME`, NEVER namespaced per project/worktree.** This
is a hard invariant of the namespaced state-root convention
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Tier-1 allowlist): namespacing the lease
registry under a project- or worktree-scoped dir would let two worktrees of the same repo (or two
different repos) allocate the same port/DB independently, exactly the collision this whole design
exists to prevent. Every other `.odoo-ai/`-rooted artifact in this plugin (design docs, worklogs,
survey findings, ...) is project- or worktree-scoped; `instances.toml` and `runtime/` are the
deliberate exceptions.

### 4.1 Catalog additions (optional, backward-compatible)

Per `[[instance]]`, add OPTIONAL fields (absent = derive a default; old files still valid):

| Field | Default | Purpose |
|-------|---------|---------|
| `profile` | `""` | short name for this instance within its series (e.g. `"community"`, `"enterprise"`); allows multiple profiles on the same series to coexist |
| `instance_key` | `<series>:<profile>` (colon) | stable key for addressing this instance; computed at read time from `series`+`profile` when not explicit. Note: the venv DIRECTORY is `venvs/<series>-<profile>` (dash/slug) - a separate concept. |
| `http_port_base` | `http_port` | low end of this instance's port pool |
| `port_pool_size` | `10` | how many ports the allocator may hand out from `http_port_base` (version-agnostic numbers; the consumer maps each to a CLI flag via `cli_help`) |
| `db_name_prefix` | `db_name` | prefix for ephemeral DBs: `<prefix>_t_<uuid8>` |
| `ephemeral_ok` | auto-probe | whether `db_user` may `CREATEDB` (probed once, cached) |
| `db_port` | absent | optional Postgres port when the cluster is not on the libpq/`PGPORT` default; ABSENT is valid and MUST NOT be fabricated as `5432` - an emitted default would silently override `PGPORT` |

`instances_io.py` must tolerate unknown/old keys (it already defaults missing fields).

The venv for each instance is built per-profile via `45-venv.sh create-venv --series <X.Y>
--profile <name>` and lives under `venvs/<series>-<profile>`. The gate for recording the
`python` field is `odoo-bin --version` (not `import odoo`) - see AI-4 in `commands/odoo-setup.md`.

### 4.2 Lease registry format

`$ODOO_AI_HOME/runtime/leases.json` - a single JSON object, atomic-written (temp + `os.replace`),
read-modify-written only while holding `fcntl.flock` on `$ODOO_AI_HOME/runtime/registry.lock`:

```
{ "leases": [
  { "token": "<uuid>", "mode": "exclusive|ephemeral|shared",
    "series": "17.0", "db_name": "odoo_17_t_ab12cd34", "drop_on_release": true,
    "python": "<venv-interpreter>", "db_host": "localhost", "db_user": "odoo", "db_port": "<port|absent>",
    "ports": [8170, 8172],                            // [] when the caller passes --ports 0 (e.g. tests with --stop-after-init); N pooled ports otherwise
    "owner": { "host": "<hostname>", "pid": 41234, "pid_started": "<ps-lstart-fingerprint|absent>",
               "run_id": "<run-id>", "started_at": <epoch> },
    "ttl_s": 3600, "heartbeat_at": <epoch> } ] }   // ttl_s default == DEFAULT_TTL_S in scripts/lib/allocator.py (SSOT)

`owner.pid_started` is a recycling-resistant fingerprint of the process that occupied `pid` at
the moment it was recorded (`ps -o lstart=` - the process's wall-clock start time; portable across
Linux/macOS/BSD, unlike `/proc`). A bare pid integer is reused by the OS over a machine's lifetime,
so `_is_stale` (§7) needs this to tell "the SAME process is still running" apart from "a DIFFERENT,
unrelated process now happens to hold this pid" before it can let liveness PROTECT a lease. Written
by `acquire` (shared/exclusive/ephemeral, whenever `--pid` is supplied) and by `bind`; absent on a
lease that never recorded a pid, or on a legacy lease from before this field existed - `_is_stale`
treats an absent/unverifiable fingerprint as "cannot prove liveness", never as "proven dead" or
"proven alive".

`drop_on_release`: True for ephemeral leases where the
caller builds the DB via Odoo create-on-init and the allocator must drop it at release/gc via
`scripts/lib/odoo_db.py` (through-Odoo path); raw `dropdb` is the logged fallback when the venv
is unavailable. False when `--no-create` is passed, and always False for shared/exclusive (those
DBs survive beyond the lease). The `python`/`db_host`/`db_user`/`db_port` fields are stored so the
drop can invoke `odoo_db.py` under the right venv (and the right cluster, when `db_port` is set)
at release/gc time, even after the caller process has exited. `db_port` absent means the ambient
`PGPORT`/libpq default resolves the connection - never fabricate `5432`.

`owner.run_id` is the canonical ownership key, stamped from `--run-id` (or its `--session` alias)
at acquire. New leases no longer write `owner.session_id`; it is read only as a legacy fallback
on leases minted before `run_id` existed (see §6.3 for the release/drop ownership guard this key
enforces).
```

`readonly` callers take NO lease (they only read a running server) - nothing to serialise.
A `shared` lease IS recorded but is NON-exclusive and always `drop_on_release=false`: it is the
visual stack's live render server (the actual bound port via `--port`, the long-lived server
pid via `--pid`). Many readers attach to the one row; gc reclaims it when the recorded pid dies, or
- only when that pid's liveness cannot be verified at all (§7) - on TTL. A verified-alive
server pid is NEVER TTL-reclaimed. Because `drop_on_release` is false, gc never drops the declared
database either way.

## 5. Access modes

| Mode | Use case | DB | Port | Lease |
|------|----------|----|----|-------|
| `readonly` | query a running instance (OSM-style live reads, UI review against an up server) | the declared `db_name` | the declared `http_port` | none (shared) |
| `ephemeral` | **default for tests / throwaway `-i` verification** | NEW `<prefix>_t_<uuid8>`, created then dropped | none with `--ports 0` (tests, `--stop-after-init`); else N pooled ports | yes, until release |
| `exclusive` | a persistent dev server, or `-u`/migration against a REAL database that must not be touched concurrently | the declared (or a named) `db_name` | N pooled ports (`--ports`) | yes, exclusive on (db_name) |
| `shared` | the visual stack's live render server (UI review / debug / visual-regression / demo against an up server), shared by many readers across sessions | the declared `db_name` | the ACTUAL bound port, recorded verbatim via `--port` (not pooled) | yes, NON-exclusive + `drop_on_release=false` (gc reclaims a dead-server row but NEVER drops the declared DB) |

Key nuance: a CI-style test - memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`
(HARD RULE, never omit the `ulimit -Sv` guard):

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d <db> -i <mod> --test-enable --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

binds **no HTTP port** - so `ephemeral` tests need only a unique DB, not a port (pass `--ports 0`). Port leasing
applies only when a server actually listens. The CONSUMER decides HOW MANY ports it needs and which
CLI flag carries each (an HTTP port, plus a longpoll/gevent port on series that need one) by querying
`cli_help` for the `<series>` at runtime - the allocator just hands out N version-agnostic free port numbers.
This removes most port contention outright.

**`persist:` (caller-facing concept, NOT a fifth allocator mode).** `skills/odoo-instance/SKILL.md`'s
`persist` field (`ephemeral` | `exclusive-running` | `shared-running`) is the SKILL/AGENT-level
lifecycle/isolation choice a caller makes; it maps onto the four allocator modes above rather than
adding a fifth:

- `persist: ephemeral` -> allocator `ephemeral`, `--ports 0` (a throwaway `--stop-after-init` build).
- `persist: exclusive-running` -> allocator `ephemeral`, `--ports 1` (or `2`) + `--run-id <id>` - the
  SAME unique-db/pooled-port lease as `ephemeral` above, except the caller runs it as a LIVE,
  listening process (`50-instance-spinup.sh --exclusive`, `agents/odoo-instance-ops.md` operation 1)
  instead of `--stop-after-init`. This lease NEVER falls back to the declared/`8069` port - the port
  always comes from this acquire (P5 port-uniqueness gate, below).
- `persist: shared-running` -> allocator `shared`, now REQUIRED to be owner-stamped via `--run-id`
  (§6.3) so a foreign session can no longer bare-drop it.

**P5 port-uniqueness gate.** `_pick_ports` (§6 `acquire`) excludes the instance's declared `http_port`
from the pool outright - both by defaulting `http_port_base` to `declared_port + 1` when the catalog
declares no separate pool base, and by passing the declared port as an explicit `reserved` exclusion
so a misconfigured overlapping `http_port_base` still cannot collide. Without this, a catalog entry
with no separate `http_port_base` would let the pool hand out the declared/shared port itself to an
`exclusive-running` lease. Covered by `test_allocator.py::test_pooled_port_never_equals_the_declared_http_port`
and `::test_concurrent_pooled_acquires_never_collide_with_declared_port`.

**P5b - catalog-wide reservation (closes the boundary off-by-one).** The single-instance exclusion
above is not sufficient across a MULTI-instance catalog: declared ports historically stepped by 10
(`40-instance-profile.sh`) while a pool spans `DEFAULT_POOL_SIZE=10` ports starting at
`declared_port + 1`, so instance 0's pool ends exactly AT instance 1's declared port (e.g. 8069's
pool reaching 8079, a second catalog entry's declared port). `cmd_acquire` now reserves EVERY
catalog-declared `http_port`, not only the acquiring instance's own: it reads the full catalog via
the same `load_instances()` call already made (before the `with _locked()` critical section, so this
adds no new lock and no deadlock risk) and passes the whole set as the `reserved` exclusion to
`_pick_ports`. This is the fix that closes the boundary off-by-one on an EXISTING catalog; widening
new instances' port step to 11 (`40-instance-profile.sh`) is a COSMETIC companion only - it does not
touch already-declared ports and does not by itself prevent the collision. Covered by
`test_allocator.py::test_maxed_out_pool_never_hands_out_a_sibling_instances_declared_port`.

**P6 - bootstrap-race safety (two same-series projects racing to spin up first).** A `db_name`
default derived from `series` alone (`odoo_17_0` for every v17.0 project) plus a declared port that
also defaults identically at index 0 meant two never-migrated same-series projects could resolve to
the SAME db_name and port before either had a chance to register distinctly - a bare `db_name`
identity check could then pass against a foreign server. Three-part fix, all in `40-instance-profile.sh`
/ `50-instance-spinup.sh` (outside `allocator.py` itself, but part of this design's concurrency
guarantee):
1. **PRIMARY - eager catalog migration.** `40-instance-profile.sh` migrates a project's local
   `instances.toml` into the machine-global catalog EAGERLY, at the top of every subcommand dispatch
   - not lazily, only inside `apply` as before - so two projects that both migrate early land in ONE
   global catalog whose port stepper (P5b above) then sees every already-declared instance and
   assigns distinct ports before either spins up. Covered by
   `test_setup_instances.py::test_migration_runs_eagerly_at_session_start_not_gated_behind_apply` and
   `::test_eager_migration_two_same_series_projects_get_distinct_ports_and_db_names`.
2. **BACKSTOP - instance-identity attach guard.** `50-instance-spinup.sh` records an identity token
   (a hash of `addons_path` - unique per project checkout, unlike `db_name`/series alone) on the port
   at spin-up, and refuses to treat "the port answers HTTP 200" as "my instance is up" when a LATER
   invocation's expected token mismatches a recorded one - a fail-closed collision detector for the
   narrow race window the eager migration shrinks but cannot fully eliminate. A port with no recorded
   marker yet (nothing has spun up through this guard) is a pass-through, same as before the guard
   existed. Covered by `test_setup_instances.py::test_attach_guard_rejects_a_live_port_with_mismatched_recorded_identity`,
   `::test_attach_guard_allows_a_live_port_with_no_recorded_identity_yet`, and
   `::test_attach_guard_allows_a_live_port_with_matching_recorded_identity`.
3. **db_name project-discriminator.** The default `db_name` is now series- AND project-scoped
   (`odoo_<series>_<repo-key8>`, the first 8 hex chars of the same `sha256(realpath(git-common-dir))`
   key that `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` uses for the Tier-2 SHARE root -
   not a fresh hash), so two same-series projects sharing the now-global catalog never default to the
   SAME db name even outside the race window.

**Gevent/longpolling port stays OPT-IN.** The default THREADED mode (`workers=0`, what `odoo-instance`
provisions unless told otherwise) multiplexes the longpolling/realtime bus over the single
`http_port` - no second port is needed, and none is allocated by default. A second port is needed
only under prefork (`--workers>0`), which MUST also request `--ports 2` at acquire time; full
contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Prefork needs a second port.

## 6. Allocator API (`scripts/lib/allocator.py`)

A thin Python CLI/lib next to `instances_io.py`. Emits shell-eval-able `ALLOC_*` lines like the
existing reader, so shell consumers stay simple.

| Command | Behavior |
|---------|----------|
| `acquire --series <X.Y> --mode <readonly\|ephemeral\|exclusive\|shared> [--profile <P>] [--ports <N>] [--port <P>] [--pid <pid>] [--ttl <s>] [--run-id <id>] (alias --session)` | resolve catalog instance for series (and profile when supplied); under flock: GC stale leases, pick N free ports from the pool (registry-set ∪ live `bind()` probe) when `--ports N>0`, choose db_name (ephemeral: unique reserved name; else declared), write the lease atomically (B2: does NOT create the DB - the caller's `-i` run performs Odoo create-on-init); probe CREATEDB and degrade ephemeral -> exclusive when absent (Odoo create-on-init requires it too); print `ALLOC_TOKEN/ALLOC_SERIES/ALLOC_PROFILE/ALLOC_DB_NAME/ALLOC_PORTS (space-separated)/ALLOC_PYTHON/ALLOC_ADDONS_PATH/ALLOC_DB_HOST/ALLOC_DB_USER/ALLOC_DB_PORT/ALLOC_RUN_ID`. `--run-id` is the canonical ownership key (the intake Phase P run id); `--session` is kept only as a back-compat alias for the same slot. When `--profile <P>` is given and `db_name` is not set explicitly in the catalog, `db_name` defaults to `odoo_<series_slug>_<profile_slug>` (e.g. `odoo_17_0_minimal`). **`shared`**: attach to the live `(series, db_name)` lease if one exists (emit `ALLOC_ATTACHED=1`) else mint one with `drop_on_release=false`; record the KNOWN port verbatim via `--port` (not pooled) and the long-lived server pid via `--pid` (idempotent upsert when a later call supplies a newer pid) - never blocks a second holder |
| `query --series <X.Y>` | read-only cross-session discovery: print the live `shared` lease for the series (`ALLOC_TOKEN/ALLOC_MODE/ALLOC_DB_NAME/ALLOC_PORTS`), or exit 1 when none. Does not mutate the registry |
| `bind <token> --pid <server_pid>` | under flock: verify the token, then UPSERT the live server pid onto that lease's `owner.pid` (the same slot the `shared` acquire path writes). Refuses an unknown token or a missing `--pid`. Used by the `exclusive-running` spin-up: the caller acquires the lease first (reserving db + ports), then binds the launched server pid so `release`/`gc` can stop the whole process GROUP before the drop. Also upgrades gc for exclusive leases from ttl-only to fast-path pid-dead reclaim, for free |
| `release <token> [--run-id <id>] [--force]` | under flock: verify token match, then apply the ownership guard (§6.3) - refuses when the caller's run id conflicts with the lease owner's run id, unless `--force`. On success, ORDER IS MANDATORY: (1) if the lease carries a live `owner.pid` on THIS host, STOP the server's process GROUP first (`_stop_group`: SIGTERM -> bounded wait -> group SIGKILL - reaps master + HTTP workers + cron + gevent/longpolling + any `--dev=reload` watchdog); (2) THEN, if `drop_on_release`, drop the ephemeral DB through Odoo (`scripts/lib/odoo_db.py`; raw `dropdb` as logged fallback when venv unavailable). Stopping the group first releases the DB connections that would otherwise block `DROP DATABASE`; `odoo_db.py`'s `pg_terminate_backend` remains as a second belt. A lease with no live local pid (legacy pre-setsid / shared / already-dead) skips the stop - no-op, always safe |
| `heartbeat <token>` | bump `heartbeat_at` - matters ONLY for a lease whose liveness `_is_stale` cannot prove (a different host, or no `--pid` ever recorded); a same-host lease with a verified-alive pid is protected regardless of heartbeat freshness |
| `gc` | under flock: reclaim leases per `_is_stale` (§7): a same-host owner pid that is DEAD (`os.kill(pid,0)`) is reclaimed immediately, TTL-independent; a same-host owner pid that is VERIFIED ALIVE (its `pid_started` fingerprint still matches) is NEVER reclaimed, TTL-independent; every other case (different host, no pid recorded, or an unverifiable fingerprint) falls back to `now - heartbeat_at > ttl_s`. When reclaiming a lease whose `owner.pid` IS recorded and alive on this host but was condemned via the fingerprint-mismatch (recycled-pid) or TTL-fallback path, STOP its process group first (`_stop_group`) before reclaim + drop. For each reclaimed `drop_on_release` lease: drop through Odoo (`odoo_db.py`), raw `dropdb` fallback |
| `reap-orphans [--min-age-s <s>] [--yes] [--instances <path>]` | DB-side sweep INDEPENDENT of the lease registry, for a class `gc` cannot reach: an ephemeral-shaped DB (`<prefix>_t_<hex8>`) that carries NO lease reference at all, live or stale (a lease-write that never happened - registry quarantine after corruption, a pre-B2 allocator, or a crash in the single narrow window between reserving a db_name and the lease write reaching disk). Ownership predicate, ALL THREE required before a DB is even listed: (1) name matches the ephemeral shape for a KNOWN catalog prefix - a named/declared instance's DB can never match, full stop; (2) NO lease references the db_name, live or stale - a leased DB, even stale, is `gc`'s/`release`'s job exclusively, never this command's; (3) age is POSITIVELY PROVEN (via `pg_stat_file`'s mtime on `PG_VERSION` - Postgres records no creation time) and `>= --min-age-s` (default 24h) - an unmeasurable age is treated as NOT proven old enough, fail-closed. A cluster this process cannot reach is skipped, never assumed empty. Default is list-only (emits `REAP_CANDIDATE`/`REAP_SKIPPED`); `--yes` is required to actually drop (emits `REAP_DROPPED`), via raw `dropdb` (no lease means no stored venv path to go through Odoo) |
| `assert-droppable --db-name <db> [--run-id <id>] [--force]` | read-only, under flock: exits non-zero when a FRESH (non-stale) lease on `<db>` is owned by a DIFFERENT run (names the owning run id), OR when it is UNOWNED (no run_id recorded at all - unowned does not mean "safe to drop"); exits 0 when owned by the caller, the lease is stale, no lease exists, or `--force` is passed. Lets a bare-name drop confirm a DB is unmanaged before touching it (§6.3) |
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

On `release`/`gc` the allocator drops it through Odoo via
`scripts/lib/odoo_db.py` (which
invokes the Odoo `db` management API under the correct venv). Raw `dropdb` is the logged fallback
when the venv is unavailable (exit 10 from `odoo_db.py`). The `python`/`db_host`/`db_user`/`db_port`
fields stored in the lease allow drop-time to reconstruct the right invocation - against the right
Postgres cluster, when `db_port` is set - even after the caller process exits.

**Degrade path (unchanged):** if `db_user` lacks `CREATEDB` (probed at acquire time), `ephemeral`
automatically falls back to `exclusive` on the declared `db_name` (serialise instead of isolate)
and the allocator logs the downgrade. The CREATEDB requirement is identical under B2: Odoo
create-on-init also needs that privilege, so the degrade logic is the same invariant.

**Consumer contract under B2:** a caller that acquires an ephemeral lease then runs
`odoo-bin -d $ALLOC_DB_NAME` WITHOUT `-i` (bare launch or a `-u` update) fails - the DB does not
exist. Always: acquire -> `-i <modules>` (create-on-init) -> use DB -> release. For operations
needing a pre-existing populated DB (translation reload `-u`, a server-start against existing
data), use `--mode exclusive` on a declared DB instead.

### 6.2 Config-file isolation (agent-facing contract)

Every concurrent instance build MUST be isolated. Isolation is guaranteed by the ALLOCATOR, not by
a shared environment config: the allocator reserves a UNIQUE database name (`<prefix>_t_<uuid8>`,
§4.1) and a private port pool per caller (§6), and the DB itself is created THROUGH Odoo by that
build's own `-i` run (§6.1) - never by a config file.

Two distinct paths exist in the current implementation, and BOTH satisfy the isolation contract by
construction:

- **`55-instance-ops.sh`-backed operations** (create/init/update/run-tests - the primary
  `odoo-instance-ops` path) pass ALL parameters as explicit CLI flags and read NO shared config
  file at all: no `-c`/`--config` flag, no reliance on `$ODOO_RC`.
- **`50-instance-spinup.sh`-backed operations** (the "stay-running" apply path, and `ensure-up`) DO
  materialise an `odoo.conf` for the launched server. That file MUST be a fresh,
  unique-per-invocation temp file (`mktemp`) - NEVER the environment's default `odoo.conf` /
  `$ODOO_RC` - and MUST NOT mutate any project file.

**Contract:** an agent MUST NOT introduce a build step that writes to a shared or default config
path (`$ODOO_RC`, a project-committed `odoo.conf`, or any config file reused across concurrent
callers). Every build either (a) passes flags with no config file at all, or (b) generates a
unique-per-run temp file - there is no third path. This is a harness-level guarantee, not an
Odoo-CLI fact, so it applies identically across all versions (v8-v19).

Consumers point back here rather than restating the contract: `agents/odoo-instance-ops.md`
("Through-Odoo DB lifecycle") and `skills/odoo-instance/SKILL.md`.

### 6.3 Ownership guard (run/session)

`owner.run_id` is the canonical ownership key stamped at `acquire` (§4.2); the legacy
`owner.session_id` field is no longer written on new leases and is read only as a fallback on
leases minted before `run_id` existed.

**`release` refuses a foreign run.** `release <token> [--run-id <id>]` refuses the release IFF
the caller passes a non-empty `--run-id` AND the lease's `owner.run_id` (or its legacy
`session_id` fallback) is non-empty AND the two differ - unless `--force` is also passed. In
every other case (no run id forwarded, an unowned/legacy lease, or a matching run id) the
release proceeds on token possession alone, exactly as before: a caller that never forwards a
run id is NEVER blocked from releasing its own lease. `--force` proceeds anyway and logs the
foreign run id it overrode. The check runs inside the same `flock` critical section as the
release itself, so it is race-free.

**A leased (managed) DB MUST be dropped via `release`, never by bare name.** Bare
`odoo_db.py drop` / `55-instance-ops.sh drop` are for UNMANAGED databases only - one with no
lease has nothing to orphan. Before a bare drop, confirm the DB is unmanaged with
`assert-droppable --db-name <db> [--run-id <id>]`; it exits non-zero (and names the owning run)
when a fresh foreign lease exists, so the caller routes to `release` instead. `--force` on the
drop path is the explicit override for reaping a foreign or stale lease. This is an
accident-prevention layer, not a security boundary - `run_id` is a semi-discoverable slug
(worklog paths), and `assert-droppable` + the drop remain two separate processes, so a lease
minted in the gap between them is not covered; managed DBs never take the bare-drop path, so
this bounded TOCTOU window does not apply to them.

**P5.8: an UNOWNED-but-fresh lease is ALSO refused, not just a foreign one.** Before this fix,
`assert-droppable` treated an empty `owner.run_id` as `always droppable` - which is exactly what let
one session bare-drop another session's live instance whenever the OWNING acquire never threaded
`--run-id` (the `_register_shared` gap P5.5 closes). A fresh (non-stale) lease with NO recorded owner
at all now ALSO requires `--force` to drop, same as a fresh foreign-owned one; an own-lease or a
stale lease remains droppable with no `--force`, unchanged. Covered by
`test_allocator.py::test_assert_droppable_refuses_unowned_fresh_lease_without_force`.

### 6.4 Addons-path worktree-mismatch guard (false-green prevention)

A caller verifying a fix that lives in a linked git worktree, while the catalog's declared
`addons_path` still points at the PRINCIPAL checkout of that same repo, must never be silently
handed the principal path - that produces a false green (the pre-fix code, self-consistently
tested, reports success). `acquire` detects this shape via `_addons_path_worktree_mismatch`:
git-common-dir is IDENTICAL across every worktree of one repository while `--show-toplevel`
differs per checkout, so "same common-dir, different toplevel" between the caller's cwd and a
catalog `addons_path` entry is the fingerprint. When detected AND no `--addons-path-override` was
passed, `acquire` refuses (exit 5) with a message naming both paths and the exact
`--addons-path-override` value that would resolve it, instead of guessing. An explicit
`--addons-path-override` always bypasses the guard (that IS the caller stating the tree
explicitly - the whole point). The guard is scoped to modes that actually drive a build
(`ephemeral`/`exclusive`/`shared`); `readonly` is exempt (it builds nothing). A cwd that is not a
git repo, IS the catalog's own declared checkout, or shares no repository with any addons_path
entry never trips it - see `tests/test_lease_ownership_and_reaping.py` for the full behavior
matrix (mismatched worktree refused, override bypasses it, principal checkout unaffected,
unrelated repo unaffected, readonly exempt).

### 6.5 `reap-orphans` - DB-side sweep independent of the lease registry

`gc` (§6, §7) only ever reclaims a DB that a LEASE still references - it drops the DB attached to
a stale lease. It has no path for a DB that exists with ZERO lease reference at all: a lease-write
that never reached disk (a registry quarantine after corruption - §7's "torn/corrupt registry"
case, an ancient pre-B2 allocator that created the DB directly, or a crash in the single narrow
window between reserving a db_name and the lease write landing). Such a DB was, before this
command existed, permanently untraceable and unreapable by any registry-driven path.
`allocator.py reap-orphans` closes that gap with an explicit, auditable ownership predicate (see
the API table in §6) rather than an automatic/background sweep: every axis fails CLOSED (an
unreachable cluster is skipped, not assumed empty; an unmeasurable age is skipped, not assumed old
enough; any leased db_name, even stale, is left to `gc`/`release`), and the default is list-only -
`--yes` is required to actually drop anything, so a sweep is always a visible read before it is
ever destructive.

**Wired (discovery half only).** `hooks/session-end-gc.sh` - the SessionEnd crash backstop that
already ran `gc` on every session's end - now ALSO runs `reap-orphans` in its default list-only
mode immediately after `gc`, persisting the candidate list to
`${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime/reap-orphans-candidates.log` (never `/dev/null`, unlike
`gc`'s own output, so the list is actually reviewable). This is the DISCOVERY half only: the hook
NEVER passes `--yes`. SessionEnd is silent and unattended by its own contract (no decision is ever
emitted), so an automatic drop there would remove the one property `reap-orphans` was designed
around - a visible, auditable read before anything destructive happens - and would let one
session's end drop a database created entirely outside that session's own leases (`reap-orphans`
scans the WHOLE declared cluster, not a per-session scope). The destructive half stays a separate,
deliberate, human-run `allocator.py reap-orphans --yes` against the persisted candidate log -
never automatic. Before this wiring, `reap-orphans` had no caller anywhere in the plugin at all;
its mechanics (ownership predicate, fail-closed age proof) were correct and tested in isolation,
but unreachable in practice.

## 7. Crash / stale handling

- Owner records `host`+`pid`+`pid_started`+`run_id`+`started_at` (a legacy lease may carry
  `session_id` instead of `run_id` - read as a fallback). **Liveness is authoritative, not a
  mere condemn signal.** `_is_stale` (`scripts/lib/allocator.py`):
  - A DEAD owner pid on THIS host is an unambiguous, TTL-independent condemn - the recorded owner
    is provably gone.
  - A LIVE owner pid on THIS host PROTECTS the lease REGARDLESS OF `ttl_s` - but only when the
    `pid_started` fingerprint captured at record time still matches the process currently holding
    that pid, which is what rules out a pid-recycled impostor (a bare `os.kill(pid,0)` cannot tell
    the two apart - pids are reused by the OS over a machine's lifetime). A POSITIVE fingerprint
    mismatch (the pid was recycled onto a different process) condemns immediately, same as a dead
    pid - the recorded owner is exactly as gone.
  - Every case where liveness cannot be proven at all - a DIFFERENT host (the pid integer is
    meaningless off-host), no pid ever recorded, or a fingerprint that could not be re-measured
    (not a proven mismatch) - falls back to `now - heartbeat_at > ttl_s`, exactly as before this
    fix. This is the ONLY case `heartbeat` still matters for; call it on any long operation whose
    lease cannot carry a locally-verifiable pid.
  - **Direction, stated explicitly so a future edit does not invert it:** for reaping, the safe
    default is to NOT reap when unsure - an un-reaped orphan only costs RAM, but a wrongly-reaped
    lease kills a live server and destroys the owner's in-progress work. See `_is_stale`'s
    docstring in `scripts/lib/allocator.py` for the full writeup; §12 covers why `DEFAULT_TTL_S`
    was reconsidered under this narrower scope.
- GC runs opportunistically at the start of every `acquire` (no daemon needed); it can also be
  invoked directly via `allocator.py gc`.
- Registry write is atomic (temp + `os.replace`); a torn/corrupt registry is detected (JSON parse
  fail) and quarantined to `leases.json.bak` with a fresh empty registry, logged loudly.

## 8. Failure modes & edge cases

| Risk | Mitigation |
|------|------------|
| Two allocators pick the same port | flock serialises the RMW; only one writes the lease; the loser re-scans. Plus a live `bind()` probe rejects a port already taken by a non-allocator process. |
| Ephemeral db name collision | uuid8 suffix; Odoo create-on-init failure -> caller can retry with a new acquire. |
| Agent dies mid-run | GC reclaims immediately by dead pid (same host); a same-host process that SURVIVES the agent (a detached orphan) is deliberately NOT reclaimed while verified alive - only TTL, for the different-host/no-pid/unverifiable case, or an explicit release/reap eventually clears it. Drops through Odoo (`odoo_db.py`), raw `dropdb` fallback. |
| Postgres unreachable | `acquire` fails fast with a clear message; never silently shares a DB. |
| `$ODOO_AI_HOME` on a network FS without working flock | documented requirement: registry must live on a local FS; setup checks and warns. |
| Old `instances.toml` with no pool fields | derive pool from `http_port`; fully backward compatible. |

## 9. TTL default

`ttl_s` defaults to `DEFAULT_TTL_S = 3600` (1h) in `scripts/lib/allocator.py` (SSOT). It governs
only the liveness-unprovable bucket (different host, no pid recorded, unverifiable fingerprint) -
a same-host owner with a verified-alive pid is NEVER TTL-reclaimed. Call `heartbeat <token>` on
any long operation in that bucket.
