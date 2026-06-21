# Technical Design - concurrent Odoo instance allocation (user/global, cross-session)

Status: IMPLEMENTED
Audience: plugin maintainers + global contributors. This is a design contract, not code.
Related: `snippets/instance-resolution.md`, `snippets/venv-resolution.md`,
`docs/reference/INSTANCE-LIFECYCLE.md`, `skills/_shared/concurrency-guard.md`,
`scripts/lib/instances_io.py`, `scripts/lib/odoo_db.py`, `scripts/setup-steps/50-instance-spinup.sh`.

> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for instance lifecycle operations (build, drop, init, update, test). The
> allocator is the low-level coordination primitive they use internally. Persistent operation logs
> are written to `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## 1. Problem & intent

Multiple subagents in one Claude Code session - and multiple sessions on one host - run Odoo
operations concurrently. Some agents only READ a running instance (share is fine); some need an
ISOLATED database (tests, `-i`/`-u`, a throwaway dev server). Today there is no coordination.

What exists is **declaration + resolution only**: `~/.odoo-ai/instances.toml` is a machine-global
catalog (`series`, one `http_port`, one `db_name`, `db_host`/`db_user`, `addons_path`, venv
`python`) and `instances_io.py` picks the first instance matching a series. There is **no
in-use/owner/lease field, no per-run database or port, no PID/runtime registry, and no
mutual-exclusion primitive** (`flock`/`fcntl`/`.lock`/pidfile = 0 occurrences in the repo).
`concurrency-guard.md` governs only agent fan-out (OOM / model-weighted budget) - it says nothing
about DB or port ownership.

**Concurrency gap (verified):** OSM reads are safe (the version-pin race was neutralised by passing
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
- **No live Odoo MCP.** The `mcp__odoo__*` server is out of scope by existing design (PR #42); the
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
| **Catalog** | `~/.odoo-ai/instances.toml` (existing) | static capability: where Postgres is, which venv, base port, addons | the user (via `/odoo-setup`) |
| **Runtime Lease Registry** | `$ODOO_AI_HOME/runtime/leases.json` (NEW) | dynamic: who currently holds which db/port | the allocator |

The catalog answers "what CAN run here"; the registry answers "what IS running/held right now".
Keeping them separate means the catalog stays a clean, hand-editable, commit-free declaration while
all volatile state lives in one machine-global file the allocator owns.

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
    "python": "<venv-interpreter>", "db_host": "localhost", "db_user": "odoo",
    "ports": [8170, 8172],                            // [] when the caller passes --ports 0 (e.g. tests with --stop-after-init); N pooled ports otherwise
    "owner": { "host": "<hostname>", "pid": 41234, "session_id": "<cc-session>", "started_at": <epoch> },
    "ttl_s": 3600, "heartbeat_at": <epoch> } ] }

`drop_on_release` replaces the old `created_db` flag (B2): True for ephemeral leases where the
caller builds the DB via Odoo create-on-init and the allocator must drop it at release/gc via
`scripts/lib/odoo_db.py` (through-Odoo path); raw `dropdb` is the logged fallback when the venv
is unavailable. False when `--no-create` is passed, and always False for shared/exclusive (those
DBs survive beyond the lease). The `python`/`db_host`/`db_user` fields are stored so the drop
can invoke `odoo_db.py` under the right venv at release/gc time, even after the caller process
has exited.
```

`readonly` callers take NO lease (they only read a running server) - nothing to serialise.
A `shared` lease IS recorded but is NON-exclusive and always `drop_on_release=false`: it is the
visual stack's live render server (the actual bound port via `--port`, the long-lived server
pid via `--pid`). Many readers attach to the one row; gc reclaims it when the recorded pid
dies (or on TTL), but - because `drop_on_release` is false - it NEVER drops the declared database.

## 5. Access modes

| Mode | Use case | DB | Port | Lease |
|------|----------|----|----|-------|
| `readonly` | query a running instance (OSM-style live reads, UI review against an up server) | the declared `db_name` | the declared `http_port` | none (shared) |
| `ephemeral` | **default for tests / throwaway `-i` verification** | NEW `<prefix>_t_<uuid8>`, created then dropped | none with `--ports 0` (tests, `--stop-after-init`); else N pooled ports | yes, until release |
| `exclusive` | a persistent dev server, or `-u`/migration against a REAL database that must not be touched concurrently | the declared (or a named) `db_name` | N pooled ports (`--ports`) | yes, exclusive on (db_name) |
| `shared` | the visual stack's live render server (UI review / debug / visual-regression / demo against an up server), shared by many readers across sessions | the declared `db_name` | the ACTUAL bound port, recorded verbatim via `--port` (not pooled) | yes, NON-exclusive + `drop_on_release=false` (gc reclaims a dead-server row but NEVER drops the declared DB) |

Key nuance: a CI-style test (`odoo-bin -d <db> -i <mod> --test-enable --stop-after-init`) binds **no
HTTP port** - so `ephemeral` tests need only a unique DB, not a port (pass `--ports 0`). Port leasing
applies only when a server actually listens. The CONSUMER decides HOW MANY ports it needs and which
CLI flag carries each (an HTTP port, plus a longpoll/gevent port on series that need one) by querying
`cli_help` for the `<series>` at runtime - the allocator just hands out N version-agnostic free port numbers.
This removes most port contention outright.

## 6. Allocator API (`scripts/lib/allocator.py`)

A thin Python CLI/lib next to `instances_io.py`. Emits shell-eval-able `ALLOC_*` lines like the
existing reader, so shell consumers stay simple.

| Command | Behavior |
|---------|----------|
| `acquire --series <X.Y> --mode <readonly\|ephemeral\|exclusive\|shared> [--profile <P>] [--ports <N>] [--port <P>] [--pid <pid>] [--ttl <s>] [--session <id>]` | resolve catalog instance for series (and profile when supplied); under flock: GC stale leases, pick N free ports from the pool (registry-set ∪ live `bind()` probe) when `--ports N>0`, choose db_name (ephemeral: unique reserved name; else declared), write the lease atomically (B2: does NOT create the DB - the caller's `-i` run performs Odoo create-on-init); probe CREATEDB and degrade ephemeral -> exclusive when absent (Odoo create-on-init requires it too); print `ALLOC_TOKEN/ALLOC_SERIES/ALLOC_PROFILE/ALLOC_DB_NAME/ALLOC_PORTS (space-separated)/ALLOC_PYTHON/ALLOC_ADDONS_PATH/ALLOC_DB_HOST/ALLOC_DB_USER`. When `--profile <P>` is given and `db_name` is not set explicitly in the catalog, `db_name` defaults to `odoo_<series_slug>_<profile_slug>` (e.g. `odoo_17_0_minimal`). **`shared`**: attach to the live `(series, db_name)` lease if one exists (emit `ALLOC_ATTACHED=1`) else mint one with `drop_on_release=false`; record the KNOWN port verbatim via `--port` (not pooled) and the long-lived server pid via `--pid` (idempotent upsert when a later call supplies a newer pid) - never blocks a second holder |
| `query --series <X.Y>` | read-only cross-session discovery: print the live `shared` lease for the series (`ALLOC_TOKEN/ALLOC_MODE/ALLOC_DB_NAME/ALLOC_PORTS`), or exit 1 when none. Does not mutate the registry |
| `release <token>` | under flock: drop the lease; if `drop_on_release` -> drop the ephemeral DB through Odoo (`scripts/lib/odoo_db.py`); raw `dropdb` as logged fallback when venv unavailable |
| `heartbeat <token>` | bump `heartbeat_at` (long runs that outlive `ttl_s`) |
| `gc` | under flock: reclaim leases whose owner pid is dead (same host: `os.kill(pid,0)`) OR `now - heartbeat_at > ttl_s`; for each reclaimed `drop_on_release` lease: drop through Odoo (`odoo_db.py`), raw `dropdb` fallback |
| `list` | print current leases (debug / `odoo-doctor`) |

`acquire`/`release`/`gc` all do their read-modify-write **inside one `fcntl.flock`** so concurrent
allocators serialise on the registry; the lock is held only for the short critical section, not for
the duration of the Odoo run.

### 6.1 DB lifecycle ownership (B2 model: caller-side create, through-Odoo drop)

`ephemeral` acquire reserves a unique DB name + ports but does NOT create the DB. The caller's
`odoo-bin -d <db> -i <modules> --stop-after-init` performs Odoo create-on-init, which builds the
DB. On `release`/`gc` the allocator drops it through Odoo via `scripts/lib/odoo_db.py` (which
invokes the Odoo `db` management API under the correct venv). Raw `dropdb` is the logged fallback
when the venv is unavailable (exit 10 from `odoo_db.py`). The `python`/`db_host`/`db_user` fields
stored in the lease allow drop-time to reconstruct the right invocation even after the caller exits.

**Degrade path (unchanged):** if `db_user` lacks `CREATEDB` (probed at acquire time), `ephemeral`
automatically falls back to `exclusive` on the declared `db_name` (serialise instead of isolate)
and the allocator logs the downgrade. The CREATEDB requirement is identical under B2: Odoo
create-on-init also needs that privilege, so the degrade logic is the same invariant.

**Consumer contract under B2:** a caller that acquires an ephemeral lease and then runs
`odoo-bin -d $ALLOC_DB_NAME` WITHOUT `-i` (a bare server launch or a `-u` update) will fail
because the DB does not exist. Always follow the sequence: acquire -> `-i <modules>` (create-on-init)
-> use DB -> release. For operations that require a pre-existing populated DB (translation
reload `-u`, a server-start against existing data), use `--mode exclusive` on a declared DB instead.

## 7. Crash / stale handling

- Owner records `host`+`pid`+`session_id`+`started_at`. GC reclaims when, on the SAME host, the pid
  is gone, or when `now - heartbeat_at > ttl_s` (covers different-host leases where pid liveness is
  unknowable). Long operations call `heartbeat`.
- GC runs opportunistically at the start of every `acquire` (no daemon needed) and is also callable
  from `odoo-doctor` / a setup step.
- Registry write is atomic (temp + `os.replace`); a torn/corrupt registry is detected (JSON parse
  fail) and quarantined to `leases.json.bak` with a fresh empty registry, logged loudly.

## 8. Failure modes & edge cases

| Risk | Mitigation |
|------|------------|
| Two allocators pick the same port | flock serialises the RMW; only one writes the lease; the loser re-scans. Plus a live `bind()` probe rejects a port already taken by a non-allocator process. |
| Ephemeral db name collision | uuid8 suffix; Odoo create-on-init failure -> caller can retry with a new acquire. |
| Agent dies mid-run | GC reclaims by dead pid (same host) or TTL; drops through Odoo (`odoo_db.py`), raw `dropdb` fallback. |
| Postgres unreachable | `acquire` fails fast with a clear message; never silently shares a DB. |
| `$ODOO_AI_HOME` on a network FS without working flock | documented requirement: registry must live on a local FS; setup checks and warns. |
| Old `instances.toml` with no pool fields | derive pool from `http_port`; fully backward compatible. |

## 9. Consumers to wire (the change list when implemented)

- `snippets/instance-resolution.md` - add an "allocate, don't just resolve" section for mutation
  callers (resolution stays for read-only URL needs).
- `snippets/venv-resolution.md` - the venv `python` comes back in the `ALLOC_*` payload.
- `docs/reference/ODOO-TESTING.md` + `skills/odoo-coding` / `odoo-test-writing` / `odoo-qa-suite`
  test guidance - tests acquire an `ephemeral` DB, run `--stop-after-init`, release.
- `scripts/setup-steps/50-instance-spinup.sh` - the spun-up server is the SHARED read-only render
  target for the visual stack, so it registers a `shared` (non-exclusive) lease with its actual port
  + server pid AFTER the server answers, NOT an exclusive lease (that would defeat the sharing).
- `agents/odoo-coder.md` + `agents/odoo-frontend-coder.md` - the `odoo-bin` (scaffold / test) note
  points at the allocator; this is also where `venv-resolution` belongs long-term (see the open
  item the brief slim-down surfaced).
- `skills/_shared/concurrency-guard.md` - add an "Odoo instance allocation" section (sibling to the
  OSM version-pin race) so the rule is discoverable where the other concurrency rules live.
- `odoo-doctor` / setup - expose `allocator gc` + `allocator list`.

**Wired:** the coder agents, `concurrency-guard.md`, `odoo-coding`, and `ODOO-TESTING.md` route
DB-touching runs through `ephemeral`/`exclusive` leases; `50-instance-spinup.sh` registers the
shared render server as a `shared` lease (actual port + server pid) once it answers, and
`instance-resolution.md` consults `allocator.py query` so every visual consumer discovers that live
port across sessions with no per-consumer edits. A concurrent same-series start is benign: the
second spin-up loses the OS port bind and exits, then both sessions attach to the one live server
(only a live pid is recorded, so gc never reclaims a running server). Covered by `test_allocator.py`
(shared mint / attach / query / gc-keeps-declared-DB) and `test_step45_50_harden.py`
(register-after-up / attach-without-relaunch / no-lease-on-failure / degrade-without-allocator).

## 10. Test outline (behavior-first, red-before-green)

- Two concurrent `acquire(ephemeral)` calls return DISTINCT db_name (and distinct ports when
  `needs_http`) - never the same.
- A lease whose owner pid is dead is reclaimed by the next `gc`/`acquire`; its ephemeral DB is
  dropped.
- `release` drops exactly the ephemeral DB the caller built (via Odoo create-on-init) and leaves declared DBs untouched.
- Degrade: with `ephemeral_ok=false`, `acquire(ephemeral)` returns an `exclusive` lease on the
  declared DB and logs the downgrade.
- flock serialises RMW: N parallel acquires yield N unique ports with no duplicate in the registry.
- Path resolution honors `$ODOO_AI_HOME` / `$ODOO_AI_INSTANCES` and never reads a hardcoded home.
- Old `instances.toml` (no pool fields) still allocates (derives the pool).

## 11. Decisions taken (this pass)

1. **Deliverable = this design doc first**, implement after review.
2. **B2 model: caller-side create, through-Odoo drop.** `ephemeral` acquire reserves the DB name;
   the caller's `-i` run performs Odoo create-on-init; release/gc drops through `scripts/lib/odoo_db.py`
   (raw `dropdb` as logged fallback). Automatic degrade to `exclusive`-lease when `db_user` cannot
   `CREATEDB` (Odoo create-on-init requires the same privilege).
3. **Form = a deterministic SCRIPT (`scripts/lib/allocator.py`) run via `Bash` at any depth** - NOT an
   LLM agent. Subagent-nesting IS available (Claude Code 2.1.172+, depth cap 5) but an LLM agent for a
   deterministic allocation is slow, token-costly, non-deterministic on port choice, and would force
   opening the `Agent` tool on consumers (breaking the worker-brief + `test_skill_format` net).
   `Bash` is allowed at any nesting level, so even a leaf-worker calls the script directly.
4. **Version-specific stays OUT of the allocator.** It returns resource facts only (db_name, free port
   numbers, token); the CONSUMER builds the `odoo-bin` command - how many ports, and which flags
   (`--http-port`, longpoll/gevent, `--test-enable`, `--stop-after-init`) - from `cli_help` for the `<series>`
   at runtime, so future Odoo CLI changes never touch the script.
5. **`readonly` is lease-free (v1)**; the allocator governs only `ephemeral` + `exclusive`.
6. **On-demand / lazy** - runs only when a caller needs an instance; GC runs opportunistically inside
   each `acquire`. No SessionStart/eager hook.

## 12. Open questions for review

- RESOLVED: pool size default 10. Port-to-flag mapping (longpoll/gevent etc.) is NOT hardcoded - the
  consumer derives it from `cli_help` for the `<series>` at runtime; the allocator only hands out N
  version-agnostic free port numbers via `--ports N`.
- RESOLVED: `readonly` stays lease-free. The visual stack's shared render server is served by the
  `shared` mode rather than a refcount - the long-lived server pid IS the refcount (gc reclaims the
  row when the process dies), so no fragile manual increment/decrement is needed.
- RESOLVED: no SessionStart/eager hook - GC runs opportunistically inside `acquire` (on-demand).
- Still open: the `ttl_s` default and whether `heartbeat` is needed for the longest test runs -
  decide during implementation from real run durations.
