# Instance profile resolution (where `instances.toml` lives)

`instances.toml` declares the local Odoo instances on THIS host - series, `http_port`, `db_port`,
`db_host`/`db_user`/`db_name`, `addons_path`, and the venv `python`. It is **Tier-1 - flat under
`$ODOO_AI_HOME`**, not project-scoped (every other `.odoo-ai/` artifact is Tier-2,
project/worktree-scoped). Full Tier-1/SHARE/ISOLATE classification tables + the
resolve-capture-substitute protocol every consumer follows:
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (SSOT - do not restate the tables here).

## Resolution order (stop at the first that yields a usable instance)

1. **A live SHARED server in the allocator registry** - before deriving a URL from the static
   catalog, ask whether a render server is already running for the series. Its ACTUAL bound port
   may differ from the declared `http_port`, and it is visible across sessions:
   ```
   python3 <plugin>/scripts/lib/allocator.py query --series <X.Y>
   # emits ALLOC_PORTS (the actual bound port) + ALLOC_DB_NAME when a live shared server exists; rc=1 when none
   ```
   When present, use `instance_base_url = http://localhost:<ALLOC_PORTS>`.
1b. **A PARKED lease for the series** - before concluding an instance must be BUILT, ask whether
   one was merely SUSPENDED. A parked lease still owns its database, filestore and ports:
   resuming costs a launch, rebuilding costs a full install AND strands the parked one until its
   budget lapses:
   ```
   python3 <plugin>/scripts/lib/allocator.py query --series <X.Y> --state parked --run-id <id>
   # emits ALLOC_TOKEN / ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_PARKED_AT; rc=1 when none
   ```
   It is also the PRE-LAUNCH DB check: a lease whose DB was dropped under the park is SKIPPED
   (stderr names it and `release <token>`), so nothing launches against a gone DB - treat a skip
   as rc=1, release that token, build fresh.
   Order, host-and-series scoped rather than run-scoped because a parked lease has NO live owner
   by construction: (a) one owned by YOUR `run_id` - resume silently; (b) else one on THIS host -
   resume and REPORT the attach (`ALLOC_ATTACHED_FROM_RUN=<owning run>`; its data state is that
   run's, a fact to relay, not a reason to refuse); (c) one on a DIFFERENT host needs
   `--force-attach` and stays gated - its database may live on an unreachable cluster.
   Resuming is not a separate launch path: hand the emitted `ALLOC_DB_NAME` / `ALLOC_PORTS` /
   `ALLOC_TOKEN` to the ordinary exclusive spin-up (`--db-name` / `--http-port` / `--alloc-token`,
   no `-i`/`-u`), which calls `allocator.py resume <token> --pid <new pid>` itself. A REFUSED
   resume BLOCKs that spin-up, which has already stopped the server it launched and left the
   lease parked: never re-run it - act on the exit code the refusal names
   (`<plugin>/agents/odoo-instance-ops.md` operation 9).
2. **`instances.toml`, resolved via `scripts/lib/resolve_instances.sh`** - the helper
   already applies the machine-global SSOT with its internal override/fallback order
   (`$ODOO_AI_INSTANCES` explicit override -> machine-global `$ODOO_AI_HOME/instances.toml`
   written by `/odoo-ai-agents:odoo-setup` -> a transitional project-local copy only when no
   global file exists yet); consumers reference the resolver, not the individual paths.

Each `[[instance]]` entry may include an optional `profile` field (a short name like
`"community"`) and an `instance_key` (a stable `<series>:<profile>` key with a colon, computed at
read time when not explicit), so several profiles on one series coexist without ambiguity. Note:
the venv DIRECTORY uses a dash: `venvs/<series>-<profile>`.

Read a profile with the shipped reader (it emits shell-eval-able `INST_*` lines):

```
python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> [series] [profile]
# emits INST_PYTHON / INST_PROFILE / INST_KEY / INST_HTTP_PORT / ... for the matched instance
```

The first `[[instance]]` whose `series` matches (and, when supplied, whose `profile` also
matches) is the active instance; omit `profile` for the highest-priority match on that series. To
select by WORKING REPO instead - the direction a Round 0 needs - use `instances_io.py locate` per
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2.

`instance_base_url = http://localhost:<http_port>` from the matched entry is the
ONLY derivation of that URL - never invent a host or assume a port.
If no source yields an instance, surface a single clarifying request for the
instance URL rather than guessing.

## Allocate, don't just resolve (concurrent mutation)

**Agents: self-provision via `Skill(odoo-instance)`, not this recipe directly.** This section
documents the low-level allocator mechanism `odoo-instance` (and any other in-plugin caller) uses
INTERNALLY. An agent needing a live instance and handed no `INSTANCE_HANDLE` invokes
`Skill(odoo-instance)` - which performs the acquire below AND applies the instance HARD RULES
(`en_US` union, Viindoo `to_base` union, lint-module install union, per-version `cli_help`
grounding) - never `scripts/lib/allocator.py acquire` directly, which skips those rules.

The resolution above is for a **read-only** need (a URL to open / query a running
server - many agents may share it). For any MUTATION - tests (`--test-enable`),
`-i`/`-u`, a migration, a throwaway server - the single declared `db_name`/`http_port`
is unsafe under concurrency (another agent or session may hold it): acquire
an isolated lease instead of reading the catalog directly:

```
python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral [--profile <P>] [--ports N] --run-id <id>
# emits ALLOC_SERIES / ALLOC_PROFILE / ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_PYTHON /
# ALLOC_ADDONS_PATH / ALLOC_DB_HOST / ALLOC_DB_USER / ALLOC_DB_PORT / ALLOC_RUN_ID / ALLOC_TOKEN
# ALLOC_RUN_ID echoes your --run-id - the ownership key release DEMANDS back.
# release with `allocator.py release <ALLOC_TOKEN> --run-id <ALLOC_RUN_ID>` - or
# `allocator.py park <ALLOC_TOKEN>` when you are done for NOW but the database must
# survive for a later resume (park stops the server, so it frees the same RAM).
```

An acquire REFUSES with exit `6`, `7`, `8` or `9` - each writes no lease and never
degrades to `exclusive`. `8`/`9` (Odoo cannot authenticate / the cluster did not answer)
gate `exclusive` too, so no mode gets past them; re-dispatching `--mode exclusive` after
`6`/`7` is the caller's own trade of isolation and must be stated in its report.
Remedies: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md` § 6.6.

`ephemeral` reserves a unique DB name and ports; the DB is created through Odoo by your
`-i` run (Odoo create-on-init) and dropped through Odoo on release via
`scripts/lib/odoo_db.py` (raw `dropdb` only as a fallback, refused when the declared
`db_run_mode` names no client surface); `exclusive` holds the declared DB under a
single-holder lease; `shared` registers a long-lived, NON-exclusive render server (the visual
stack's live target) with its actual `--port` so other sessions discover it via `query` and gc
reclaims it when its server pid dies - it never drops the declared DB; `readonly` is lease-free
(use plain resolution above). The allocator returns version-agnostic port NUMBERS only - map each
to the right CLI flag (`--http-port`, longpoll/gevent, ...) by querying
`cli_help` for the target series at runtime. Full mode contract:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5; GC/stale rules:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-RECLAIM.md` § 7.
