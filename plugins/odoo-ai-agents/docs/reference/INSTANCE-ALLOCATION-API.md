# Odoo instance allocation - MCP tools, allocator CLI, database lifecycle and error codes

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index). This file owns the
`odoo-local` MCP tools (primary), the `allocator.py` CLI (fallback), the database lifecycle behind
a lease, and the error codes. Source of truth: the tool
definitions in `scripts/mcp/odoo_local/tools_*.py` and the docstring + `ERROR_CODES` of
`scripts/lib/allocator.py` (`allocator.py --help`); when they disagree with this page, they win.

## 6. Allocator surfaces

### MCP tools - `odoo-local` (primary)

`odoo-local` (`.mcp.json`, `scripts/mcp/odoo_local_server.py`) wraps the allocator and the instance
scripts as `mcp__plugin_odoo-ai-agents_odoo-local__<tool>`; Claude Code only (Codex and Gemini use the
CLI). Schemas: `tools/list`.

| Tool | Wraps | Notes |
|------|-------|-------|
| `lease_acquire` | `allocator.py acquire --format json`, then `list` to read the row back | `series` required; `ports` > 0 refused for `shared` / `readonly`; returns `lease` + `instance_handle` (`snippets/instance-handle-contract.md`) + `venv_missing` / `warnings` (no venv python: builds and serves raise `VENV_MISSING`) |
| `lease_release` | stops every still-running `instance_build` job of the lease, then `allocator.py release <token> --run-id <id>` | inputs `lease_token` + `run_id`; refuses `NOT_OWNER` / `RECLAIM_IN_PROGRESS` BEFORE stopping a job; `released` = `ALLOC_RELEASED`, `absent` = `ALLOC_ALREADY_ABSENT` |
| `lease_park` | `allocator.py park <token> --run-id <id> [--park-ttl <s>]` | inputs `lease_token` + `run_id`; a shared lease is `SHARED_NOT_PARKABLE` |
| `lease_list` | `allocator.py list --show-tokens --with-verdict` (`--session mine` / `--run-id`) | full token + `run_id` only for this session's leases, else null + 8-char prefix; `session_alive` |
| `lease_find` | `allocator.py query --series <X.Y> [--state parked] [--run-id <id>]` | `NOT_FOUND` becomes `found: false`; full `token` + `run_id` (`yours: true`) only for the caller's run AND this session or an ended one, else both null + `token_prefix`; every lease carries `served` / `http_port` / `url` |
| `lease_gc` | `allocator.py gc --scope dead-sessions\|all [--dry-run]` | `dry_run` defaults to true; an apply is never auto-approved (`hooks/auto-approve-local.sh`); each row's `action` is `reclaim` or `park` |
| `lease_adopt` | `allocator.py adopt <token> --run-id <id>` | inputs `lease_token` + `run_id` |
| `db_preflight` | `allocator.py db-preflight --series <X.Y> [--profile <P>]` | a refusal code becomes `ok: false` + `code` + `remedy` |
| `instance_build` | `scripts/setup-steps/55-instance-ops.sh <init\|update\|test>`, started DETACHED as a job | returns a `job_id` at once and no `instance_handle` (`job_wait` returns it); one live build/export job per DATABASE (any lease) - another is `DATABASE_BUSY`. `--load` = checkout core default + the lease's `server_wide_modules` (`SERVER_WIDE_CORE_UNKNOWN`), adjusted for the call by `server_wide` `{exclude, include}` (`instances_io.effective_server_wide_modules`: core + (declared - exclude) + include, core first; a core / undeclared exclude or a module in both lists is `INVALID_ARGUMENTS`, an include not found on the lease's addons path + core addons is `SERVER_WIDE_MODULE_NOT_FOUND`; reported as `server_wide_adjustment`); `--load-language` = `en_US` + `languages`; `demo` required for `init`, refused for `update` / `test` (`test` runs the checkout's series default; where it loads no demo, a database holding demo is `TEST_DB_HAS_DEMO` - `odoo_db.py db-facts`, else the leases' build records, `facts_source`). Odoo reads a generated conf, never `~/.odoorc`. The launcher (`odoo-bin`) is located on the addons path being served first, and the lease's `odoo_root` only fills in when no entry leads to one (`--odoo-root` of `55-instance-ops.sh`; also for `instance_i18n_export`). An `extra_args` token setting a flag the tool owns (`TOOL_CONTROLLED_LONG` + build facts in `tools_instance.py`) is `INVALID_ARGUMENTS` |
| `job_wait` | the job's process state, then `55-instance-ops.sh wait-log --timeout 0` for the log verdict | bounded wait (default 300s, max 540s); `timeout` means call again. Finished: `languages_loaded` / `languages_failed` (`en_US` once modules loaded, others log-proven), `warnings` (server-wide module missing - names `server_wide.include` for the task and the catalog row + `odoo-setup refresh` call for every build; demo data failed), `instance_handle` (database facts, as above); an `instance_i18n_export` job adds `exports` (`.pot` first) |
| `instance_i18n_export` | `scripts/setup-steps/55-instance-ops.sh i18n-export`, started DETACHED as a job | per module the `.pot`, then one `.po` per language (the module's existing `<code>.po`, else Odoo's export name `<iso_code>.po`; both present fails the job, `I18N_PO_FILE_AMBIGUOUS`), into the module's `i18n/` (or `output_dir/<module>/`), by Odoo's exporter (`odoo_source_facts.i18n_export_cli`) run on the build's server-wide set (`--load` as for `instance_build`, `server_wide` included; the `i18n export` subcommand gets it as `server_wide_modules` in its conf); files never edited, replaced only by a finished export. Refused when an exported module lacks its own demo (`I18N_EXPORT_NEEDS_DEMO`), a language is not loaded (`I18N_LANGUAGE_NOT_LOADED`) - database facts, as above - or a module resolves in more than one addons dir (`MODULE_SHADOWED`); `odoo_db.py i18n-state` fails the job on a module not installed / a language not active |
| `instance_serve` | `scripts/setup-steps/50-instance-spinup.sh apply` | `lease_token` XOR `series`; a lease is served with its own venv, `profile` (another is `PROFILE_MISMATCH`) and series-derived port keys; success = a live server verified bound to the lease, else `SERVE_FAILED`; `launched` returns the shared lease's token, `attached` only when it is your run's in this session; `--load` as `instance_build`; `server_wide` only on your own non-shared lease (else `INVALID_ARGUMENTS`), passed to the spin-up as the complete `--load` set; an attach to the lease's running server whose conf carries another set (`RUNNING_SERVER_WIDE_MODULES`) is `SERVER_WIDE_NOT_APPLIED`; nobody releases the shared lease (MODES §5); a parked lease of another session is `LEASE_NOT_ADOPTED` |
| `instance_status` | `50-instance-spinup.sh check`, plus `query` for the shared and the parked lease of the series | optional `run_id` (full token only for your run's leases, as `lease_find`); `http_port` / `url` when up |
| `catalog_read` | `scripts/lib/resolve_instances.sh --path`, then `instances_io.load_instances` | |
| `catalog_locate` | `instances_io.find_covering_instance` | |
| `series_detect` | `scripts/lib/odoo_series.py` `detect` | |
| `project_dir` | `scripts/lib/paths.py` `share_dir` / `isolate_dir` | |
| `server_info` | the server itself: version, Python, plugin root, session anchor | |

No tool: a server thread runs `allocator.py heartbeat --session mine` every 600s
(`ODOO_LOCAL_MCP_HEARTBEAT_S`), refreshing `seen_at` on this session's leases; no caller
heartbeats (RECLAIM §7). Children get `ODOO_AI_VIA=mcp` and the
server's `ODOO_AI_SESSION_ANCHOR`, so a tool-acquired lease records `owner.via = "mcp"`.

Tool errors carry `{code, message, remedy, diagnostics}`. Allocator codes keep the code and meaning
of the table below; `scripts/mcp/odoo_local/errors.py` (SSOT for tool-side remedies) re-words their
remedy and adds its own codes (`SERVER_CODES`).

CLI-only verbs: `bind`, `resume` (both called by `50-instance-spinup.sh`), `record-build` (the
build tools), `heartbeat` (the server thread), `gc --scope anchor` (the SessionEnd hook),
`reap-orphans`, `assert-droppable`, `can-createdb`, `anchor`.

### Allocator CLI (fallback)

For when the `odoo-local` tools are unavailable (another runtime, a failed server start,
`PYTHON_TOO_OLD`), and for scripts and hooks.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" <verb> [flags] [--format shell|json]
```

It never builds an `odoo-bin` command. An unknown `--flag` is exit 2; `--help` prints the docstring.
Mutating verbs write the registry under one `fcntl.flock`, never held across a server stop or a
drop (RECLAIM §7.3).

**Output.** `--format shell` (default): `KEY=VALUE` lines on stdout (`shlex.quote`d, lists
space-joined), `# ...` comments, prose on stderr. `--format json`: ONE object on stdout:

```json
{"ok": true, "rc": 0, "error": null, "fields": {"ALLOC_TOKEN": "...", "ALLOC_PORTS": [8170]}}
```

`fields` holds the same keys typed, JSON-only payloads (`leases`, `candidates`, `holders`...) and
`notes` (the `#` lines). A non-zero exit carries `error: {code, message}`; `rc` is the exit code.

#### Verbs

| Verb | Synopsis | Output keys | Exits |
|------|----------|-------------|-------|
| `acquire` | `--series <X.Y> --mode <readonly\|ephemeral\|exclusive\|shared> (--run-id <id> \| --allow-unowned) [--ports N] [--port P] [--ttl <s>] [--db-name <name>] [--pid <pid>] [--profile <P>] [--no-create] [--instances <path>] [--addons-path-override <csv-or-colon-paths>]` | `ALLOC_{TOKEN,MODE,DB_NAME,PORTS,RUN_ID,PYTHON,ADDONS_PATH,DB_HOST,DB_USER,DB_PORT,SERIES,PROFILE,SERVER_WIDE_MODULES}`; `ALLOC_ATTACHED` for `shared`; `holders` (JSON) on exit 3/4; the `allocator: acquired lease` stderr receipt is written after stdout is flushed, so a merged `2>&1 \| tail` still ends on it; an `--addons-path-override` that drops the checkout's core addons is `ADDONS_PATH_OVERRIDE_INVALID` (below) | 0-10 (error codes below, §6.6) |
| `query` | `--series <X.Y> [--state parked] [--run-id <id>] [--force-attach] [--instances <path>]` | `ALLOC_TOKEN`, `ALLOC_MODE`, `ALLOC_DB_NAME`, `ALLOC_PORTS`; with `--state parked` also `ALLOC_PARKED_AT`, `ALLOC_ATTACHED_FROM_RUN` | 0, 1 `NOT_FOUND` |
| `release` | `<token> --run-id <id> [--force] [--force-forget] [--instances <path>]` | `ALLOC_RELEASED` (this call deleted the row) or `ALLOC_ALREADY_ABSENT=1`; `ALLOC_FORGOTTEN_DB`, `ALLOC_ABANDONED_DB`, `ALLOC_UNVERIFIED_DB` (GUARDS §6.7) | 0 (also for an unknown token), 1 `NOT_OWNER` / `DROP_FAILED_KEPT`, 11 `RECLAIM_IN_PROGRESS` |
| `park` | `<token> --run-id <id> [--park-ttl <s>] [--force]` | `ALLOC_TOKEN`, `ALLOC_DB_NAME`, `ALLOC_PORTS`, `ALLOC_PARKED_AT`, `ALLOC_PARK_TTL_S`, `ALLOC_DROP_ON_RELEASE` | 0, 1 `LEASE_NOT_FOUND` / `NOT_OWNER`, 2 `USAGE`, 3 `SHARED_NOT_PARKABLE`, 4 `NOT_RUNNING`, 11 |
| `resume` | `<token> --pid <server_pid> [--instances <path>]` | `ALLOC_TOKEN`, `ALLOC_DB_NAME`, `ALLOC_PORTS` | 0, 3 `NOT_PARKED`, 4 `WRONG_HOST` / `PID_NOT_ALIVE` / `OWNERSHIP_UNPROVEN`, 5 `DB_GONE`, 6 `RESUME_RACE`, 11 |
| `bind` | `<token> --pid <server_pid>` | none | 0, 1 `LEASE_NOT_FOUND`, 2 `USAGE` |
| `record-build` | `<token> [--demo on\|off] [--languages <a,b>]` | `ALLOC_BUILT_DEMO`, `ALLOC_BUILT_LANGUAGES` | 0, 1 `LEASE_NOT_FOUND`, 2 `USAGE` |
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
  live row (`ALLOC_ATTACHED=1`) or mints one with `drop_on_release=false`. A written lease prints
  `allocator: acquired lease <token> run_id=<id>` on stderr (the receipt the teardown and ownership
  hooks read). Acquire reclaims nothing implicitly; the capacity path (RECLAIM §7.2) re-picks ports
  for up to `PORT_FREE_WAIT_S` after it stopped a server. Modes and `persist:`: MODES §5; worktree
  refusal: GUARDS §6.4.
- **`query`** - default: the live `shared` lease; `--state parked`: the resumable parked lease,
  host-and-series scoped (another run's carries `ALLOC_ATTACHED_FROM_RUN`, another host's needs
  `--force-attach`); one whose database is provably gone is skipped.
- **`release`** - ownership first (GUARDS §6.3), then two-phase: mark `reclaiming`, stop the proven
  server group, drop a `drop_on_release` database through Odoo, delete the row. A failed drop keeps
  the lease; `--force-forget` names what was left (§6.7 there).
- **`park`** - stops the proven group if one runs (a reserved, never-served lease parks too),
  clears the pid, stamps `parked_at` / `park_ttl_s` (48h) / `parked_boot_id`;
  database, ports and `drop_on_release` are untouched.
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

Every non-zero exit names one code with one exit code. Remedies are the CLI's; the tools' are in
`scripts/mcp/odoo_local/errors.py`.

| Code | rc | Meaning | Remedy |
|------|----|---------|--------|
| `USAGE` | 2 | invalid arguments | fix the flags named in the message (`allocator.py --help`) |
| `SERIES_REQUIRED` | 2 | acquire needs `--series <X.Y>` | pass the series you mean; nothing is picked for you |
| `ADDONS_PATH_OVERRIDE_INVALID` | 2 | `--addons-path-override` is empty or names missing directories | pass existing directories. `fields.reason` `core-addons-missing` (the override drops the checkout's core addons the catalog row declares): keep the catalog row's addons_path and replace only the entry that covers this repo with your worktree path |
| `ANCHOR_REQUIRED` | 2 | `gc --scope anchor` has no anchor | pass `--anchor <pid:fingerprint>` (see `anchor --print`) |
| `NO_INSTANCE` | 1 | no instance for that series/profile in the catalog | declare one with `/odoo-ai-agents:odoo-setup`, or pass `--instances` |
| `NO_INSTANCE_CATALOG` | 1 | `instances.toml` missing or unreadable | run `/odoo-ai-agents:odoo-setup`, or pass `--instances <path>` |
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
| `NOT_RUNNING` | 4 | the lease is already parked, or orphaned with no server | resume it by serving it, or release the lease |
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
| `DB_UNREACHABLE` | 9 | the database cluster did not answer | start the cluster, or correct `db_host` / `db_port` |
| `RUN_ID_REQUIRED` | 10 | no `--run-id` (ownership not established) | pass the run id you were given; never invent one |
| `RECLAIM_IN_PROGRESS` | 11 | another process is reclaiming this lease | wait for that gc/release to finish, then re-check |

Every non-zero `acquire` exit writes NO lease (a capacity reclaim before an exit 3/4 persists and
drops nothing). `--mode exclusive-running` exits 2: that `persist:` value maps onto `ephemeral`
(MODES §5), whose database `release` and `gc` DROP; a database that must outlive its lease is
acquired `exclusive` or `shared`.

### 6.1 DB lifecycle ownership (caller-side create, through-Odoo drop)

An `ephemeral` acquire reserves a unique database name + ports but does NOT create the database.
The caller's first `-i <modules>` run creates it (`instance_build` op `init`, or op `test` with mode
`fresh`), under the memory cap owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

On `release` / `gc` the allocator drops it through Odoo (`scripts/lib/odoo_db.py`, the lease's
venv). The `db_run_mode` client surface is the logged last resort, ONLY when the Odoo route never
reached the database (`odoo_db.py` exit 8, 9, 10) AND the name is a throwaway `<prefix>_t_<hex8>`; an
attempted, failed drop keeps database and lease. The drop surface is re-resolved on every attempt
(GUARDS §6.7).

**Consumer contract.** Ephemeral: acquire -> `-i <modules>` -> use -> release. A populated
database (a `-u` reload, a server on existing data) is leased `exclusive`.

### 6.6 Acquire refusals - exits 6, 7, 8 and 9, never a degrade

An `ephemeral` acquire returns an ISOLATED throwaway database or fails - never an `exclusive` lease
on the declared database. Trading isolation for serialisation is the caller's explicit choice
(acquire `exclusive`, and say so in the report).

AUTHENTICATION is evaluated FIRST for every mode that will build (`ephemeral`, `exclusive`; skipped
for `--no-create`, `readonly`, `shared`): a cluster that refuses Odoo kills any build.

Exits 6 `NO_CREATEDB`, 7 `CREATEDB_UNDETERMINABLE`, 8 `DB_AUTH_DENIED`, 9 `DB_UNREACHABLE`: meaning
and remedy in the code table above.

An UNDETERMINABLE authentication state never blocks - only a proven 8 or 9 does. CREATEDB is asked
over two routes in order, and 7 means both failed: (1) the declared `python` (`odoo_db.py
can-createdb`; a proven 8 or 9 stops the ladder); (2) the `db_run_mode` client surface (`psql`, native
or in `db_container`).

Every Postgres call is BOUNDED by `$ODOO_AI_PG_PROBE_TIMEOUT` (default 10s; longer for mutating
calls). An elapsed bound is UNDETERMINED (exit 7), never a factual "no".
