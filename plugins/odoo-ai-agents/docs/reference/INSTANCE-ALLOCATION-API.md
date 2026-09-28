# Odoo instance allocation - MCP tools, allocator CLI, database lifecycle and error codes

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index + parts map). This file owns the
`odoo-local` MCP tools (primary), the `allocator.py` CLI (fallback), the database lifecycle behind
a lease, and the error codes. Source of truth: the tool
definitions in `scripts/mcp/odoo_local/tools_*.py` and the docstring + `ERROR_CODES` of
`scripts/lib/allocator.py` (`allocator.py --help`); when they disagree with this page, they win.

## 6. Allocator surfaces

### MCP tools - `odoo-local` (primary)

`odoo-local` (`.mcp.json`, `scripts/mcp/odoo_local_server.py`) wraps the allocator and the instance
scripts as `mcp__plugin_odoo-ai-agents_odoo-local__<tool>`; Claude Code only (Codex and Gemini use the
CLI). Schemas are served by `tools/list`; this table maps each tool to what it wraps.

| Tool | Wraps | Notes |
|------|-------|-------|
| `lease_acquire` | `allocator.py acquire --format json`, then `list` to read the row back | `series` required; `ports` > 0 refused for `shared` / `readonly`; returns `lease` + `instance_handle` (`snippets/instance-handle-contract.md`) + `venv_missing` / `warnings` (the row has no venv python: builds and serves will raise `VENV_MISSING`) |
| `lease_release` | stops every still-running `instance_build` job of the lease, then `allocator.py release <token> --run-id <id>` | inputs `lease_token` + `run_id`; refuses `NOT_OWNER` / `RECLAIM_IN_PROGRESS` BEFORE stopping a job; `released` = `ALLOC_RELEASED` (this call deleted the row), `absent` = `ALLOC_ALREADY_ABSENT` |
| `lease_park` | `allocator.py park <token> --run-id <id> [--park-ttl <s>]` | inputs `lease_token` + `run_id`; a shared lease is `SHARED_NOT_PARKABLE` |
| `lease_list` | `allocator.py list --show-tokens --with-verdict` (`--session mine` / `--run-id`) | full token + `run_id` only for this session's leases, else null + 8-char prefix; `session_alive` |
| `lease_find` | `allocator.py query --series <X.Y> [--state parked] [--run-id <id>]` | `NOT_FOUND` becomes `found: false`; full `token` + `run_id` (`yours: true`) only for the caller's run AND this session or an ended one, else both null + `token_prefix`; every lease carries `served` / `http_port` / `url` |
| `lease_gc` | `allocator.py gc --scope dead-sessions\|all [--dry-run]` | `dry_run` defaults to true; an apply (`dry_run: false`) is never auto-approved (`hooks/auto-approve-local.sh`); each row's `action` is `reclaim` or `park`, re-parked prefixes in `parked` |
| `lease_adopt` | `allocator.py adopt <token> --run-id <id>` | inputs `lease_token` + `run_id` |
| `db_preflight` | `allocator.py db-preflight --series <X.Y> [--profile <P>]` | a refusal code becomes `ok: false` + `code` + `remedy` |
| `instance_build` | `scripts/setup-steps/55-instance-ops.sh <init\|update\|test>`, started DETACHED as a job | returns a `job_id` at once; connection facts come from the lease row; an `extra_args` token setting a tool-controlled flag (db/connection, addons path, config/save, data dir, `-i`/`-u`, stop-after-init, test switches, ports, log destination; short clusters read as optparse does) is `INVALID_ARGUMENTS` |
| `job_wait` | the job's process state, then `55-instance-ops.sh wait-log --timeout 0` for the log verdict | bounded wait (default 300s, max 540s); result `timeout` means call again |
| `instance_serve` | `scripts/setup-steps/50-instance-spinup.sh apply` | `lease_token` XOR `series`; a lease is served with its own venv, `profile` (another is `PROFILE_MISMATCH`) and series-derived port keys; success = a live server verified bound to the lease, else `SERVE_FAILED`; `state: launched` returns the shared lease's token, `attached` only when it is your run's in this session; nobody releases the shared lease as teardown (MODES §5); a parked lease of another session is `LEASE_NOT_ADOPTED` |
| `instance_status` | `50-instance-spinup.sh check`, plus `query` for the shared and the parked lease of the series | optional `run_id` (full token only for your run's leases, as `lease_find`); `http_port` / `url` when up |
| `catalog_read` | `scripts/lib/resolve_instances.sh --path`, then `instances_io.load_instances` | |
| `catalog_locate` | `instances_io.find_covering_instance` | |
| `series_detect` | `scripts/lib/odoo_series.py` `detect` | |
| `project_dir` | `scripts/lib/paths.py` `share_dir` / `isolate_dir` | |
| `server_info` | the server itself: version, Python, plugin root, session anchor | |

No tool: a server thread runs `allocator.py heartbeat --session mine` every 600s
(`ODOO_LOCAL_MCP_HEARTBEAT_S`), refreshing `seen_at` on this session's leases; no caller
heartbeats (`INSTANCE-ALLOCATION-RECLAIM.md` §7). Children get `ODOO_AI_VIA=mcp` and the
server's `ODOO_AI_SESSION_ANCHOR`, so a tool-acquired lease records `owner.via = "mcp"`.

Tool errors carry `{code, message, remedy, diagnostics}`. Allocator codes keep the code and meaning
of the table below; `scripts/mcp/odoo_local/errors.py` (SSOT for tool-side remedies) re-words their
remedy and adds the server's own codes (`SERVER_CODES`: e.g. `VENV_MISSING`, `PROFILE_MISMATCH`,
`LEASE_HAS_NO_PORT`, `SERVE_FAILED`, `INVALID_ARGUMENTS`).

Verbs no tool exposes, reachable only through the CLI: `bind`, `resume` (both called by
`50-instance-spinup.sh`), `heartbeat` (the server thread above), `gc --scope anchor` (the SessionEnd
hook), `reap-orphans`, `assert-droppable`, `can-createdb`, `anchor`.

### Allocator CLI (fallback)

For when the `odoo-local` tools are unavailable (another runtime, a failed server start,
`PYTHON_TOO_OLD`), and for scripts and hooks.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" <verb> [flags] [--format shell|json]
```

It never builds an `odoo-bin` command. An unknown `--flag` is exit 2; `--help` prints the docstring.
Mutating verbs read-modify-write the registry inside one `fcntl.flock`, never held while a server
is stopped or a database dropped (RECLAIM §7.3).

**Output.** `--format shell` (default): `KEY=VALUE` lines on stdout (`shlex.quote`d, lists
space-joined), `# ...` comments, prose on stderr. `--format json`: ONE object on stdout:

```json
{"ok": true, "rc": 0, "error": null, "fields": {"ALLOC_TOKEN": "...", "ALLOC_PORTS": [8170]}}
```

`fields` holds the same keys typed (lists for ports and repeatable keys), JSON-only payloads
(`leases`, `schema_version`, `candidates`, `holders`, `touched`...) and `notes` (the `#` lines). A
non-zero exit carries `error: {code, message}` (code table below); `rc` is the exit code.

#### Verbs

| Verb | Synopsis | Output keys | Exits |
|------|----------|-------------|-------|
| `acquire` | `--series <X.Y> --mode <readonly\|ephemeral\|exclusive\|shared> (--run-id <id> \| --allow-unowned) [--ports N] [--port P] [--ttl <s>] [--db-name <name>] [--pid <pid>] [--profile <P>] [--no-create] [--instances <path>] [--addons-path-override <csv-or-colon-paths>]` | `ALLOC_{TOKEN,MODE,DB_NAME,PORTS,RUN_ID,PYTHON,ADDONS_PATH,DB_HOST,DB_USER,DB_PORT,SERIES,PROFILE}`; `ALLOC_ATTACHED` for `shared`; `holders` (JSON) on exit 3/4 | 0-10 (error codes below, §6.6) |
| `query` | `--series <X.Y> [--state parked] [--run-id <id>] [--force-attach] [--instances <path>]` | `ALLOC_TOKEN`, `ALLOC_MODE`, `ALLOC_DB_NAME`, `ALLOC_PORTS`; with `--state parked` also `ALLOC_PARKED_AT`, `ALLOC_ATTACHED_FROM_RUN` | 0, 1 `NOT_FOUND` |
| `release` | `<token> --run-id <id> [--force] [--force-forget] [--instances <path>]` | `ALLOC_RELEASED` (this call deleted the row) or `ALLOC_ALREADY_ABSENT=1`; `ALLOC_FORGOTTEN_DB`, `ALLOC_ABANDONED_DB`, `ALLOC_UNVERIFIED_DB` (GUARDS §6.7) | 0 (also for an unknown token), 1 `NOT_OWNER` / `DROP_FAILED_KEPT`, 11 `RECLAIM_IN_PROGRESS` |
| `park` | `<token> --run-id <id> [--park-ttl <s>] [--force]` | `ALLOC_TOKEN`, `ALLOC_DB_NAME`, `ALLOC_PORTS`, `ALLOC_PARKED_AT`, `ALLOC_PARK_TTL_S`, `ALLOC_DROP_ON_RELEASE` | 0, 1 `LEASE_NOT_FOUND` / `NOT_OWNER`, 2 `USAGE`, 3 `SHARED_NOT_PARKABLE`, 4 `NOT_RUNNING`, 11 |
| `resume` | `<token> --pid <server_pid> [--instances <path>]` | `ALLOC_TOKEN`, `ALLOC_DB_NAME`, `ALLOC_PORTS` | 0, 3 `NOT_PARKED`, 4 `WRONG_HOST` / `PID_NOT_ALIVE` / `OWNERSHIP_UNPROVEN`, 5 `DB_GONE`, 6 `RESUME_RACE`, 11 |
| `bind` | `<token> --pid <server_pid>` | none | 0, 1 `LEASE_NOT_FOUND`, 2 `USAGE` |
| `adopt` | `<token> --run-id <id>` | `ALLOC_TOKEN`, `ODOO_AI_SESSION_ANCHOR` | 0, 1 `NOT_OWNER`, 4 `WRONG_HOST`, 5 `NO_ANCHOR`, 11 |
| `heartbeat` | `<token>` \| `--session mine` | `touched` (JSON, 8-char token prefixes) | 0, 1 `LEASE_NOT_FOUND`, 2 |
| `gc` | `[--scope all\|dead-sessions\|anchor] [--anchor <pid:fingerprint>\|mine] [--dry-run] [--force] [--run-id <id>] [--instances <path>]` | `ALLOC_WOULD_RECLAIM` per candidate (`--dry-run`; JSON `action` reclaim\|park) or `ALLOC_RECLAIMED` / `ALLOC_PARKED` per lease; `candidates` / `reclaimed` / `parked` / `scope` (JSON) | 0, 2 `ANCHOR_REQUIRED`, 3 `ANCHOR_ALIVE` |
| `list` | `[--show-tokens] [--run-id <id>] [--older-than <s>] [--tokens <t1,t2>] [--session <pid:fingerprint\|mine>] [--with-verdict]` | the registry as JSON; `leases` + `schema_version` (JSON mode) | 0 |
| `db-preflight` | `--series <X.Y> [--profile <P>] [--instances <path>]` | `DB_AUTH=ok\|denied\|unreachable\|unknown`, `DB_AUTH_WHY`, `CREATEDB`, `CREATEDB_WHY` | 0, 6, 7, 8, 9 |
| `can-createdb` | `--series <X.Y> [--profile <P>] [--instances <path>]` | `CREATEDB=true\|false\|undeterminable`, `CREATEDB_WHY` | 0, 6, 7, 8, 9 |
| `assert-droppable` | `--db-name <db> [--run-id <id>] [--force]` | `ALLOC_OWNER_RUN` on a refusal | 0, 1 `DB_HELD_BY_OTHER_RUN` / `DB_HELD_UNOWNED` |
| `reap-orphans` | `[--min-age-s <s>] [--yes] [--instances <path>]` | `REAP_CANDIDATE`, `REAP_SKIPPED`, `REAP_DROPPED` | 0, 1 `REAP_DROP_FAILED` |
| `anchor` | `[--print]` | `ODOO_AI_SESSION_ANCHOR=<pid>:<fingerprint>`, `ODOO_AI_SESSION_ID`, `ODOO_AI_ANCHOR_SOURCE=env\|claude-pid\|ancestor`, `ODOO_AI_ANCHOR_STATE=alive\|dead\|unknown` | 0, 5 `NO_ANCHOR` |

Verb semantics that a synopsis cannot carry (the full text is the docstring):

- **`acquire`** - `--run-id` is the ownership key (`--session` is an alias); every mode but
  `readonly` needs it or `--allow-unowned`. `readonly` writes no lease. `ephemeral` reserves a unique
  `<prefix>_t_<hex8>` name (+ N pooled ports) and creates nothing (§6.1). `shared` attaches to the
  live row (`ALLOC_ATTACHED=1`) or mints one with `drop_on_release=false`, recording `--port` and
  `--pid`. Every row records `profile` (the resolved catalog profile, `""` unprofiled). A written
  lease also prints `allocator: acquired lease <token> run_id=<id>` on stderr (the transcript
  receipt the teardown and ownership hooks read). Ports are probed as Odoo binds them
  (`SO_REUSEADDR` + bind + listen): TIME_WAIT is free, a listener is not. Acquire reclaims nothing
  implicitly; the capacity path (`INSTANCE-ALLOCATION-RECLAIM.md` §7.2) re-picks ports for up to
  `PORT_FREE_WAIT_S` after it stopped a server. Modes and `persist:`: `INSTANCE-ALLOCATION-MODES.md`
  §5; worktree refusal: `INSTANCE-ALLOCATION-GUARDS.md` §6.4.
- **`query`** - default: the live `shared` lease; `--state parked`: the resumable parked lease,
  host-and-series scoped (another run's carries `ALLOC_ATTACHED_FROM_RUN`, another host's needs
  `--force-attach`); one whose database is provably gone is skipped.
- **`release`** - ownership first (GUARDS §6.3), then two-phase: mark `reclaiming`, stop the proven
  server group, drop a `drop_on_release` database through Odoo, delete the row. A failed drop keeps
  the lease; `--force-forget` names what was left (§6.7 there).
- **`park`** - stops the proven group, clears the pid, stamps `parked_at` / `park_ttl_s` (48h) /
  `parked_boot_id`; database, ports and `drop_on_release` are untouched.
- **`resume`** - one locked compare-and-set AFTER the new server launched; every refusal obliges the
  caller to stop that server (RECLAIM §8). Exit 3: first launch, `bind` instead; exit 6: lost the race.
- **`bind`** - upserts the server pid + fingerprints (REGISTRY §4.2) + caller's anchor. **`adopt`** - moves the lease onto the caller's
  anchor, prints `allocator: adopted lease <token> run_id=<id>`; adopting (or resuming) a parked
  lease sets `owner.return_to_park`. **`heartbeat`** - refreshes `heartbeat_at` and, for the
  caller's own session, `seen_at`.
- **`gc`** - scopes: RECLAIM §7.2; a condemned `return_to_park` lease is parked again, not dropped.
  **`list --with-verdict`** - the liveness SSOT (RECLAIM §7.1). **`db-preflight`** evaluates
  `DB_AUTH` first; **`can-createdb`** is the ladder `acquire --mode ephemeral` gates on (§6.6).
  **`assert-droppable`** - GUARDS §6.3. **`reap-orphans`** - RECLAIM §6.5. **`anchor`** - its first
  line hands the same anchor to a detached worker or hook.

### Error codes (`ERROR_CODES`)

Every non-zero exit names one code, each paired with one exit code. The remedy column is the
allocator's (CLI vocabulary); the tool wording lives in `scripts/mcp/odoo_local/errors.py`.

| Code | rc | Meaning | Remedy |
|------|----|---------|--------|
| `USAGE` | 2 | invalid arguments | fix the flags named in the message (`allocator.py --help`) |
| `SERIES_REQUIRED` | 2 | acquire needs `--series <X.Y>` | pass the series you mean; nothing is picked for you |
| `ADDONS_PATH_OVERRIDE_INVALID` | 2 | `--addons-path-override` is empty or names missing directories | pass existing directories |
| `ANCHOR_REQUIRED` | 2 | `gc --scope anchor` has no anchor | pass `--anchor <pid:fingerprint>` (see `anchor --print`) |
| `NO_INSTANCE` | 1 | no instance for that series/profile in the catalog | declare one with `/odoo-ai-agents:odoo-setup`, or pass `--instances` |
| `NO_INSTANCE_CATALOG` | 1 | `instances.toml` missing or unreadable (every verb that reads it) | run `/odoo-ai-agents:odoo-setup`, or pass `--instances <path>` |
| `LEASE_NOT_FOUND` | 1 | no lease with that token | check the token (`list --tokens`) |
| `NOT_OWNER` | 1 | the lease is owned by a different run | only the run that acquired a lease may release or adopt it |
| `DROP_FAILED_KEPT` | 1 | the drop failed; the lease is kept | fix the drop surface (`45-venv.sh record-env`) and retry, or `--force-forget` |
| `NOT_FOUND` | 1 | no matching lease (`query`) | acquire one |
| `DB_HELD_BY_OTHER_RUN` | 1 | a fresh lease owned by another run holds the database | route the drop through `release <token>` |
| `DB_HELD_UNOWNED` | 1 | a fresh unowned lease holds the database | pass `--force` deliberately, or leave it |
| `REAP_DROP_FAILED` | 1 | at least one orphan drop failed | see the stderr account |
| `UNSPECIFIED` | 1 | the command failed | see stderr |
| `EXCLUSIVE_CONFLICT` | 3 | the database is already held exclusively | retry later, use `--mode ephemeral`, or ask its owner to release it |
| `SHARED_NOT_PARKABLE` | 3 | a shared lease cannot be parked | leave it for its readers; gc reclaims it once its server is gone |
| `NOT_PARKED` | 3 | the lease is not parked and no live server holds it | bind the pid instead |
| `ANCHOR_ALIVE` | 3 | that session anchor is still alive | wait for the session to end, or pass `--force` deliberately |
| `PORT_POOL_EXHAUSTED` | 4 | no free port in the instance's pool | release or park a lease you own; see `holders`. `fields.reason` `ports-busy-outside-registry` (no lease holds one): retry shortly, find the listener, or widen the pool |
| `NOT_RUNNING` | 4 | the lease records no server pid | bind a pid first, or release the lease |
| `WRONG_HOST` | 4 | the lease was recorded on another host | operate on it from the host that holds it |
| `PID_NOT_ALIVE` | 4 | the named pid is not a live process here | pass the pid of the server you launched |
| `OWNERSHIP_UNPROVEN` | 4 | the pid is not proven to be this lease's server | launch the server for this lease's database/port |
| `ADDONS_PATH_WORKTREE_MISMATCH` | 5 | cwd is a different worktree of a catalog addons_path repo | pass `--addons-path-override <the tree to build>` |
| `DB_GONE` | 5 | the parked lease's database is gone | release the lease, then build a fresh instance |
| `NO_ANCHOR` | 5 | the caller has no session anchor | run inside an agent session or export `ODOO_AI_SESSION_ANCHOR` |
| `NO_CREATEDB` | 6 | the role lacks CREATEDB | grant CREATEDB, or use `--mode exclusive`, or `--no-create` |
| `RESUME_RACE` | 6 | another caller already resumed this lease | stop the server you launched and attach to the running one |
| `CREATEDB_UNDETERMINABLE` | 7 | CREATEDB could not be determined | `45-venv.sh record-env`, declare `db_run_mode`, or start the cluster |
| `DB_AUTH_DENIED` | 8 | Odoo cannot authenticate to the cluster | run `/odoo-ai-agents:odoo-setup` or export `ODOO_PG_PASSWORD` |
| `DB_UNREACHABLE` | 9 | the database cluster did not answer | start the cluster |
| `RUN_ID_REQUIRED` | 10 | no `--run-id` (ownership not established) | pass the run id you were given; never invent one |
| `RECLAIM_IN_PROGRESS` | 11 | another process is reclaiming this lease | wait for that gc/release to finish, then re-check |

Every non-zero `acquire` exit writes NO lease (a capacity reclaim before an exit 3/4 is persisted,
and never drops anything). `--mode exclusive-running` exits 2: that `persist:` value maps onto
`ephemeral` (`INSTANCE-ALLOCATION-MODES.md` §5), whose database `release` and `gc` DROP. A database
that must outlive its lease is acquired `exclusive` or `shared` from the start.

### 6.1 DB lifecycle ownership (caller-side create, through-Odoo drop)

An `ephemeral` acquire reserves a unique database name + ports but does NOT create the database.
The caller's first `-i <modules>` run performs Odoo create-on-init (`instance_build` op `init`, or
op `test` with mode `fresh`), under the memory cap owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

On `release` / `gc` the allocator drops it through Odoo (`scripts/lib/odoo_db.py`, the lease's
venv). The `db_run_mode` client surface is the logged last resort, ONLY when the Odoo route never
reached the database (`odoo_db.py` exit 8, 9, 10) AND the name is a throwaway `<prefix>_t_<hex8>`; an
attempted, failed drop keeps database and lease. The drop surface is re-resolved on every attempt
(GUARDS §6.7).

`ephemeral` NEVER degrades: it returns a fresh throwaway database or refuses (§6.6).

**Consumer contract.** An ephemeral lease launched WITHOUT `-i` (a bare launch, or `-u`) fails: the
database does not exist. Always acquire -> `-i <modules>` -> use -> release. A pre-existing populated
database (a `-u` reload, a server on existing data) uses `exclusive` on a declared database.

### 6.6 Acquire refusals - exits 6, 7, 8 and 9, never a degrade

An `ephemeral` acquire returns an ISOLATED throwaway database or fails - never an `exclusive` lease
on the declared database. Trading isolation for serialisation is the caller's explicit choice
(acquire `exclusive`, and say so in the report).

AUTHENTICATION is evaluated FIRST, for every mode that will build (`ephemeral` and `exclusive`;
skipped for `--no-create`, `readonly` and `shared`): Odoo connects before any module loads, so a
cluster that refuses Odoo kills an update or a test exactly as it kills a create.

| Exit | Code | Meaning | Remedy |
|------|------|---------|--------|
| `6` | `NO_CREATEDB` | the role positively LACKS CREATEDB | grant that role CREATEDB, then retry |
| `7` | `CREATEDB_UNDETERMINABLE` | no route could answer the CREATEDB question | declare what is missing (below), or start the cluster |
| `8` | `DB_AUTH_DENIED` | Odoo cannot authenticate to the cluster | run `/odoo-ai-agents:odoo-setup`; or export `ODOO_PG_PASSWORD` for a cluster that cannot be reconfigured |
| `9` | `DB_UNREACHABLE` | the cluster did not answer at all | start the cluster, or correct `db_host` / `db_port` |

An UNDETERMINABLE authentication state never blocks - only a proven 8 or 9 does. CREATEDB is asked
over two routes in order, and 7 means both failed: (1) the declared `python` (`odoo_db.py
can-createdb`; a proven 8 or 9 stops the ladder); (2) the `db_run_mode` client surface (`psql`, native
or in `db_container`). Exit 7 resolves by `45-venv.sh record-env --series <X.Y>` (records `python`,
`odoo_root` - REGISTRY §4.1 - and `db_run_mode` / `db_container`), or by starting the cluster.

Every Postgres call is BOUNDED by `$ODOO_AI_PG_PROBE_TIMEOUT` (default 10s; longer for mutating
calls). An elapsed bound is UNDETERMINED (exit 7), never a factual "no".
