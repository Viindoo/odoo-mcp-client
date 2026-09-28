# Instance profile resolution (which local instance serves a series)

`instances.toml` declares the local Odoo instances on THIS host - series, profile, ports, database
coordinates, `addons_path`, and the venv `python`. It is **Tier-1 - flat under `$ODOO_AI_HOME`**,
not project-scoped (every other `.odoo-ai/` artifact is Tier-2, project/worktree-scoped). Full
Tier-1/SHARE/ISOLATE classification tables:
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (SSOT - do not restate the tables here).
Read the catalog only through `catalog_read` (rows by series/profile) and `catalog_locate` (the
row whose `addons_path` covers a repo or worktree path); never parse the file yourself.

## Resolution order (stop at the first that yields a usable instance)

1. **A live shared server** - before deriving a URL from the catalog, call `lease_find` (state
   `shared`) or `instance_status` for the series. Its base URL is `lease.url` (when
   `lease.served`) or `instance_status.url` - never one derived from a lease token. A reader needs
   no token (another run's is withheld). Nobody releases or parks the shared server as teardown,
   not even the run that launched it: it is multi-reader, and `lease_gc` reclaims it once its
   server is gone.
1b. **A parked lease for the series** - before concluding an instance must be BUILT, call
   `lease_find` (state `parked`, your `run_id`). A parked lease still owns its database, filestore
   and ports: resuming costs a launch, rebuilding costs a full install and strands the parked one.
   `yours: true` -> `lease_adopt(lease_token, run_id)`, then `instance_serve(lease_token)` - never
   build again. Always adopt first: a token you only found may not be released or parked, and the
   adopt makes the resumed server yours to tear down. `yours: false` (token withheld) is another
   run's, or held by another live session: never resume, release or park it. When a resume is refused,
   follow the error code's remedy; never retry the same call blind.
2. **The catalog** - `catalog_read` with the series (and profile when several are declared). With
   no profile, several rows on one series are an ambiguity to resolve from the task, never a pick.
   To select by WORKING REPO instead - the direction a Round 0 needs - use `catalog_locate` per
   `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2. The venv DIRECTORY uses a
   dash: `venvs/<series>-<profile>`.

With no live server, `instance_base_url = http://localhost:<http_port>` from the matched row is the
ONLY derivation of that URL - never invent a host or assume a port. If no source
yields an instance, surface a single clarifying request for the instance URL rather than guessing.

## Allocate, don't just resolve (concurrent mutation)

**Agents: self-provision via `Skill(odoo-instance)`, not the lease tools directly** (this binds
every agent except `odoo-instance-ops`, the executor that skill dispatches). The
`odoo-instance` skill calls `lease_acquire` INTERNALLY and applies the instance HARD RULES (demo
by build purpose, lint-module install union, per-version `cli_help` grounding) that a bare
`lease_acquire` + `instance_build` skips.

The resolution above is for a **read-only** need (a URL to open / query a running server - many
agents may share it). For any MUTATION - tests, `init` / `update`, a migration, a throwaway server -
the single declared database and port are unsafe under concurrency: hold an isolated lease
(`lease_acquire` mode `ephemeral`) instead of using the catalog row.

- A refused `lease_acquire` writes no lease; follow the named error code's remedy (`db_preflight`
  diagnoses a Postgres refusal). Never fall back to mode `exclusive` silently: choosing it after a
  refusal gives up isolation, and your report must say so.
- Release or park what you acquired per `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`.

If the odoo-local tools are unavailable, use the allocator CLI documented in
${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md.
