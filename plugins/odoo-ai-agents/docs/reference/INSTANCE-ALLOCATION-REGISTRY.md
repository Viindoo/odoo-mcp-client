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
read-modify-written only while holding `fcntl.flock` on `$ODOO_AI_HOME/runtime/registry.lock`.
`schema_version` is 3 (`SCHEMA_VERSION` in `scripts/lib/allocator.py`). Readers are lenient: a v1 or
v2 row simply lacks the v3 keys and is judged by the legacy liveness rungs
(`INSTANCE-ALLOCATION-RECLAIM.md` §7.1); there is no bulk migration.

```
{ "schema_version": 3,
  "leases": [
  { "token": "<uuid>", "mode": "exclusive|ephemeral|shared",
    "series": "17.0", "profile": "<profile|empty>", "db_name": "odoo_17_t_ab12cd34",
    "drop_on_release": true,
    "python": "<venv-interpreter>", "odoo_root": "<core checkout|empty>",
    "db_run_mode": "native|docker|tcp-only|empty", "db_container": "<docker handle|empty>",
    "db_host": "localhost", "db_user": "odoo", "db_port": "<port|absent>",
    "_pg": { "host": "...", "user": "...", "port": "..." },   // cluster coordinates (every mode, shared included)
    "addons_path": "<comma-joined dirs>",
    "ports": [8170, 8172],        // [] with --ports 0; N pooled ports otherwise
    "owner": { "host": "<hostname>", "run_id": "<run-id>", "started_at": <epoch>,
               "pid": <server pid|absent>, "pid_started": "<legacy lstart|absent>",
               "pid_fp": "<fingerprint|absent>", "pid_fp_pid": <pid pid_fp was measured on|absent>,
               "server_gone": { "pid": <pid>, "reason": "owner-pid-dead|owner-pid-recycled", "at": <epoch> },
                                                     // only after a shed (below)
               "return_to_park": true, "return_park_ttl_s": 172800,   // only after a resume/adopt out of a park
               "via": "mcp|cli",
               "acquired_by": { "agent_id": "...", "agent_type": "..." },   // when the caller set them
               "session": { "pid": <anchor pid>, "started": "<fingerprint>",
                            "session_id": "<CLAUDE_CODE_SESSION_ID|empty>",
                            "source": "env|claude-pid|ancestor", "seen_at": <epoch> } },
    "ttl_s": 86400, "ttl_explicit": true,            // ttl_explicit only when acquire --ttl was passed
    "heartbeat_at": <epoch>,
    "parked_at": <epoch|absent>, "park_ttl_s": 172800, "parked_boot_id": "<kernel boot id|absent>",
    "orphaned": { "at": <epoch>, "reason": "...", "by_verb": "acquire-capacity", "ports": [...] },
                                                     // capacity reclaim: server stopped, ports freed
    "reclaiming": { "by_pid": <pid>, "host": "<hostname>", "at": <epoch>,
                    "reason": "...", "by_verb": "gc|release|acquire-capacity" } } ] }
                                                     // present only while a reclaimer owns the row
```

**`owner.session`** is the session anchor that protects the lease (`INSTANCE-ALLOCATION-RECLAIM.md`
§7.1). It is written at `acquire` whenever the caller has an anchor, refreshed by `bind`, `resume`,
`adopt` and a same-session `heartbeat`, and never erased by an unanchored caller. `seen_at` is the
last time the owning session vouched for the lease; it measures only the grace window after that
session ends. A `shared` row records an anchor too, but is judged by its server pid alone.

**`owner.server_gone`** is written by `_shed_gone_server` inside every locked `heartbeat`, `acquire`,
`bind`, `gc` and `adopt` write, across the whole registry: when a non-shared, non-parked lease on this host has a PROVABLY alive session anchor but its
recorded server pid is dead or proven recycled, the pid keys (`pid`, `pid_started`, `pid_fp`,
`pid_fp_pid`) are cleared, `heartbeat_at` is refreshed, and `server_gone` records the shed pid, the
reason and when. This keeps an older allocator, which ignores the anchor and reads a dead pid as
condemning, from reclaiming a lease its session still uses; this allocator's own verdict is
unchanged (session-protected, state `reserved`). `park` reads it as "this lease was running" and
accepts it; any later write of a server pid (`bind`, `resume`, `acquire --pid`) and `park` itself
remove it.

`odoo_root`, `db_run_mode` and `db_container` are copied from the catalog row at acquire for every leased mode but `shared` (empty on
a catalog that predates them) and, with `python` and `_pg`, let the through-Odoo drop and the raw
fallback reach the right installation and cluster after the caller has exited (§4.1).

**`owner.via`** is `"mcp"` when the `odoo-local` server made the call (`ODOO_AI_VIA=mcp`), else
`"cli"`. **`owner.acquired_by`** comes from `ODOO_AI_CALLER_AGENT_ID` / `_TYPE` when set.

**`ttl_s` / `ttl_explicit`** feed only the legacy TTL arm. `ttl_s` defaults to `DEFAULT_TTL_S`
(24h); a row whose TTL was not set explicitly is judged against at least 24h whatever `ttl_s` it
carries.

The three `parked_*` keys are present TOGETHER or not at all, and their presence IS the PARKED
state - there is no separate status field to drift from them. `park` writes them (and clears
the recorded server - `owner.pid`, `pid_started`, `pid_fp`, `pid_fp_pid`); `resume` DELETES all three in the same locked write that records
the new owner pid. `park_ttl_s` defaults to `DEFAULT_PARK_TTL_S` (48h): it budgets DISK, not RAM,
because park stopped the server's process group before it cleared the pid. `parked_boot_id` is this
boot's kernel identity (`/proc/sys/kernel/random/boot_id`), compared at reclaim time so a budget
that elapsed only because the host was OFF is not read as consumed; it is absent wherever that file
cannot be read, and the comparison then degrades to the plain budget check.

**`orphaned`** marks a row whose owner was provably gone when an `acquire` needed its capacity: its
server group was stopped and its ports freed, but its database was kept - a later `gc` or `release`
drops it. **`reclaiming`** is the phase-A marker of the two-phase reclaim
(`INSTANCE-ALLOCATION-RECLAIM.md` §7.3); the row keeps its ports while it is present.

**Server-pid fingerprints.** A bare pid is reused by the OS, so liveness needs a fingerprint to tell
"the SAME process is still running" from "an unrelated process now holds this pid".
`owner.pid_fp` is the TZ- and locale-free fingerprint (`proc:<boot_id>:<starttime>` on Linux,
`ps:<UTC lstart>` elsewhere), trusted only while `owner.pid_fp_pid` equals `owner.pid` (an older
allocator's `bind` / `resume` rewrites `pid` and knows nothing of `pid_fp`). `owner.pid_started`
keeps the LEGACY bare `ps -o lstart=` shape (ambient TZ) that an older plugin version reads and
compares with `==` - it is written for them, and read here only as the fallback
(`INSTANCE-ALLOCATION-RECLAIM.md` § Cross-version). All four keys are written by `acquire` (with
`--pid`), `bind` and `resume`, and cleared together by `park`. An absent or unverifiable fingerprint
means "cannot prove liveness", never "proven dead" or "proven alive".

**`owner.return_to_park`** (+ `return_park_ttl_s`, the budget it had) marks a lease taken out of a
deliberate park by `resume` or `adopt`: a gc that condemns it because its new owner is gone parks it
again with that budget instead of dropping its database.

`drop_on_release` is true for an `ephemeral` lease whose database the caller builds through Odoo
create-on-init and the allocator drops at release / gc through `scripts/lib/odoo_db.py`
(`INSTANCE-ALLOCATION-API.md` §6.1). It is false with `--no-create`, and always false for `shared`
and `exclusive` (those databases outlive the lease). The `python` / `db_host` / `db_user` /
`db_port` fields let the drop reach the right venv and cluster after the caller has exited;
`db_port` absent means the ambient `PGPORT` / libpq default resolves the connection - never
fabricate `5432`.

`owner.run_id` is the ownership key, stamped from `--run-id` (or its `--session` alias) at acquire.
New leases do not write `owner.session_id`; it is read only as a fallback on rows minted before
`run_id` existed (`INSTANCE-ALLOCATION-GUARDS.md` §6.3).

`readonly` callers take NO lease (they only read a running server). A `shared` lease IS recorded but
is NON-exclusive and always `drop_on_release=false`: it is the visual stack's live render server
(the bound port via `--port`, the long-lived server pid via `--pid`). Many readers attach to the one
row. It is condemned only when its server pid is dead or recycled (or, under an explicit
`gc --scope all`, by the legacy TTL arm when that pid's liveness cannot be proven), and because
`drop_on_release` is false no reclaim ever drops the declared database.
