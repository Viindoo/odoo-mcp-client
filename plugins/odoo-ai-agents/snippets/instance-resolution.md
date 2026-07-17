# Instance profile resolution (where `instances.toml` lives)

`instances.toml` declares the local Odoo instances on THIS host - series,
`http_port`, `db_port`, `db_host`/`db_user`/`db_name`, `addons_path`, and the venv `python`.
It is **Tier-1 - flat under `$ODOO_AI_HOME`**, not project-scoped: an execute-agent has no
guaranteed working directory, so the instance profile must be findable from any cwd, and
namespacing it per project/worktree would fragment one host's instance catalog into copies.
Every OTHER `.odoo-ai/`-rooted artifact - `context.md`, `survey/`, `worklog/`, ... - is
project- or worktree-scoped under the two-axis `$ODOO_AI_HOME/projects/<repo-key>/[worktrees/<wt-key>/]`
convention, **never** a project-relative `./.odoo-ai/`. Full Tier-1/SHARE/ISOLATE
classification tables + the resolve-capture-substitute protocol every consumer follows:
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (SSOT - do not restate the tables
here).

## Resolution order (stop at the first that yields a usable instance)

1. **`instance_base_url` in `<SHARE_DIR>/context.md`** - a project may pin a
   specific running instance for its own work; this project override wins when present.
   (Resolve `<SHARE_DIR>` per the resolve-capture-substitute protocol in
   `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` before reading it.)
2. **A live SHARED server in the allocator registry** - before deriving a URL from the
   static catalog, ask whether a render server is already running for the series. Its
   ACTUAL bound port may differ from the declared `http_port`, and it is visible across
   sessions:
   ```
   python3 <plugin>/scripts/lib/allocator.py query --series <X.Y>
   # emits ALLOC_PORTS (the actual bound port) + ALLOC_DB_NAME when a live shared server exists; rc=1 when none
   ```
   When present, use `instance_base_url = http://localhost:<ALLOC_PORTS>`.
3. **`instances.toml`, resolved via `scripts/lib/resolve_instances.sh`** - the helper
   already applies the machine-global SSOT with its internal override/fallback order
   (`$ODOO_AI_INSTANCES` explicit override -> machine-global `$ODOO_AI_HOME/instances.toml`
   written by `/odoo-ai-agents:odoo-setup` -> a transitional project-local copy only when no
   global file exists yet); consumers reference the resolver, not the individual paths.

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

**Agents: self-provision via `Skill(odoo-instance)`, not this recipe directly.** This section
documents the low-level allocator mechanism `odoo-instance` (and any other in-plugin caller) uses
INTERNALLY for the deterministic, concurrency-safe DB/port reservation. An agent that needs a live
instance and was handed no `INSTANCE_HANDLE` should invoke `Skill(odoo-instance)` - which performs
the acquire below AND applies the instance HARD RULES (`en_US` union, Viindoo `to_base` union,
lint-module install union, per-version `cli_help` grounding) - rather than calling
`scripts/lib/allocator.py acquire` directly, which would skip those rules. The recipe below stays
here for `odoo-instance` (and any other genuinely low-level caller) that still needs the raw
mechanism.

The resolution above is correct for a **read-only** need (a URL to open / query a
running server - many agents may share it). But the moment you MUTATE - run tests
(`--test-enable`), `-i`/`-u`/a migration, or spin a throwaway server - reusing the
single declared `db_name`/`http_port` is unsafe under concurrency: another agent or
another Claude Code session may be using the same database/port right now.

For a mutation, acquire an isolated lease instead of reading the catalog directly:

```
python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral [--profile <P>] [--ports N] [--run-id <id>]
# emits ALLOC_SERIES / ALLOC_PROFILE / ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_PYTHON /
# ALLOC_ADDONS_PATH / ALLOC_DB_HOST / ALLOC_DB_USER / ALLOC_DB_PORT / ALLOC_RUN_ID / ALLOC_TOKEN
# ALLOC_RUN_ID echoes the --run-id you passed (the lease's ownership key).
# release with `allocator.py release <ALLOC_TOKEN> [--run-id <id>]` when done.
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
