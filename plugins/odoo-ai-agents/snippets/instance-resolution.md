# Instance profile resolution (where `instances.toml` lives)

`instances.toml` declares the local Odoo instances on THIS host - series,
`http_port`, `db_host`/`db_user`/`db_name`, `addons_path`, and the venv `python`.
It is **machine-global**, not project-scoped: an execute-agent has no guaranteed
working directory, so the instance profile must be findable from any cwd. (Every
other `.odoo-ai/` artifact - `context.md`, `survey/`, `worklog/`, ... - stays
project-scoped under `./.odoo-ai/`.)

## Resolution order (stop at the first that yields a usable instance)

1. **`instance_base_url` in `./.odoo-ai/context.md`** - a project may pin a
   specific running instance for its own work; this project override wins when present.
2. **A live SHARED server in the allocator registry** - before deriving a URL from the
   static catalog, ask whether a render server is already running for the series. Its
   ACTUAL bound port may differ from the declared `http_port`, and it is visible across
   sessions:
   ```
   python3 <plugin>/scripts/lib/allocator.py query --series <X.Y>
   # emits ALLOC_PORTS (the actual bound port) + ALLOC_DB_NAME when a live shared server exists; rc=1 when none
   ```
   When present, use `instance_base_url = http://localhost:<ALLOC_PORTS>`.
3. **`$ODOO_AI_INSTANCES`** - an explicit full path to an `instances.toml`
   (set in the environment; used by tests / non-standard layouts).
4. **`$HOME/.odoo-ai/instances.toml`** - the machine-global profile written by
   `/odoo-ai-agents:odoo-setup`. This is the canonical source; prefer it.
5. **`./.odoo-ai/instances.toml`** - a project-local profile, only as a
   transitional fallback when no machine-global file exists yet.

Each `[[instance]]` entry may include an optional `profile` field (a short name
like `"community"` or `"enterprise"`) and an `instance_key` (a stable key
`<series>:<profile>` with a colon, computed at read time from `series`+`profile`
when not explicit). These allow multiple profiles on the same series to coexist
without ambiguity. Note: the venv DIRECTORY uses a dash: `venvs/<series>-<profile>`.

Read a profile with the shipped reader (it emits shell-eval-able `INST_*` lines):

```
python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> [series] [profile]
# emits INST_PYTHON / INST_PROFILE / INST_KEY / INST_HTTP_PORT / ... for the matched instance
```

The first `[[instance]]` whose `series` matches (and, when supplied, whose `profile`
also matches) is the active instance; its `http_port` gives
`instance_base_url = http://localhost:<http_port>`. Omit `profile` to get the
highest-priority match for the series. If none of the sources above yields an
instance, surface a single clarifying request for the instance URL rather than
guessing.

## Allocate, don't just resolve (concurrent mutation)

The resolution above is correct for a **read-only** need (a URL to open / query a
running server - many agents may share it). But the moment you MUTATE - run tests
(`--test-enable`), `-i`/`-u`/a migration, or spin a throwaway server - reusing the
single declared `db_name`/`http_port` is unsafe under concurrency: another agent or
another Claude Code session may be using the same database/port right now.

For a mutation, acquire an isolated lease instead of reading the catalog directly:

```
python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral [--profile <P>] [--ports N]
# emits ALLOC_SERIES / ALLOC_PROFILE / ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_PYTHON /
# ALLOC_ADDONS_PATH / ALLOC_DB_HOST / ALLOC_DB_USER / ALLOC_TOKEN
# release with `allocator.py release <ALLOC_TOKEN>` when done.
```

`ephemeral` reserves a unique DB name and ports; the DB is created through Odoo by your
`-i` run (Odoo create-on-init) and dropped through Odoo on release via
`scripts/lib/odoo_db.py` (raw `dropdb` only as a logged fallback for the venv-unavailable
case); `exclusive` holds the declared DB under a single-holder lease; `shared` registers a
long-lived,
NON-exclusive render server (the visual stack's live target) with its actual `--port`
so other sessions discover it via `query` and gc reclaims it when its server pid dies -
it never drops the declared DB; `readonly` is lease-free (use plain resolution above).
The allocator returns version-agnostic port NUMBERS only -
map each to the right CLI flag (`--http-port`, longpoll/gevent, ...) by querying
`cli_help` for the target series at runtime. Full contract + GC/stale rules:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`.
