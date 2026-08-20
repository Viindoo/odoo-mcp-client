# Odoo instance allocation - catalog and lease registry

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns the two-layer architecture and the on-disk format
of both layers: the `instances.toml` catalog and the `runtime/leases.json` lease registry.

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
| `db_port` | absent | optional Postgres port when the cluster is not on the libpq/`PGPORT` default; ABSENT is valid and MUST NOT be fabricated as `5432` - an emitted default would silently override `PGPORT` |
| `odoo_root` | absent | the core checkout root that makes `import odoo` resolve for a SOURCE instance (a venv alone does not: `odoo-bin` works only because it puts the repo root on `sys.path[0]`). Recorded by `45-venv.sh` from the repo whose `odoo-bin --version` passed |
| `db_run_mode` | absent | how POSTGRES is reached: `native` \| `docker` \| `tcp-only`. Vocabulary SSOT: `scripts/lib/pg_mode.sh` header. Distinct from `run_mode`, which describes ODOO. Consulted by every client-binary consumer (the raw-drop fallback, the spin-up preflight) AND, as the SECOND route only, by the CREATEDB check when the instance declares no `python` of its own (`INSTANCE-ALLOCATION-API.md` §6.6) - the answer is then a POSITIVE query put to the cluster, never an inference from which binaries happen to be installed |
| `db_container` | absent | `docker` mode only: the `docker exec` handle, derived ONCE at registration from `db_port` (`docker ps --filter publish=<db_port>`), never guessed - an ambiguous match, a `docker ps` that could not be asked, or a matching container that exists but is not RUNNING all refuse and record nothing |

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
    "ttl_s": 3600, "heartbeat_at": <epoch>,
    "parked_at": <epoch|absent>, "park_ttl_s": 86400, "parked_boot_id": "<kernel boot id|absent>" } ] }
                                                   // ttl_s default == DEFAULT_TTL_S in scripts/lib/allocator.py (SSOT)

The three `parked_*` keys are present TOGETHER or not at all, and their presence IS the PARKED
state - there is no separate status field to drift from them. `park` writes them (and clears
`owner.pid`/`owner.pid_started`); `resume` DELETES all three in the same locked write that records
the new owner pid. `park_ttl_s` defaults to `DEFAULT_PARK_TTL_S` (24h) in `scripts/lib/allocator.py`
(SSOT) - an order of magnitude looser than `ttl_s` because it budgets DISK, not RAM: park stopped
the server's process group before it cleared the pid. `parked_boot_id` is this boot's kernel
identity (`/proc/sys/kernel/random/boot_id`), compared at reclaim time so a budget that elapsed
only because the host was OFF is not read as one that was consumed; it is absent wherever that file
cannot be read (not Linux), and the comparison then degrades to the plain budget check.
`INSTANCE-ALLOCATION-RECLAIM.md` §7 states the arm.

`owner.pid_started` is a recycling-resistant fingerprint of the process that occupied `pid` at
the moment it was recorded (`ps -o lstart=` - the process's wall-clock start time; portable across
Linux/macOS/BSD, unlike `/proc`). A bare pid integer is reused by the OS over a machine's lifetime,
so `_is_stale` (`INSTANCE-ALLOCATION-RECLAIM.md` §7) needs this to tell "the SAME process is still running" apart from "a DIFFERENT,
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
on leases minted before `run_id` existed (see `INSTANCE-ALLOCATION-GUARDS.md` §6.3 for the
release/drop ownership guard this key enforces).
```

`readonly` callers take NO lease (they only read a running server) - nothing to serialise.
A `shared` lease IS recorded but is NON-exclusive and always `drop_on_release=false`: it is the
visual stack's live render server (the actual bound port via `--port`, the long-lived server
pid via `--pid`). Many readers attach to the one row; gc reclaims it when the recorded pid dies, or
- only when that pid's liveness cannot be verified at all
(`INSTANCE-ALLOCATION-RECLAIM.md` §7) - on TTL. A verified-alive
server pid is NEVER TTL-reclaimed. Because `drop_on_release` is false, gc never drops the declared
database either way.
