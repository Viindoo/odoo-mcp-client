---
name: odoo-instance
argument-hint: "[create|drop|park|resume|init|update|test|load-language] [version|db]"
description: >-
  Creates, updates, tests, stops or drops a live local Odoo instance
---

## Role

Odoo instance lifecycle front door for ALL instance lifecycle operations (create,
drop, park, resume, init, update, run-tests, ensure-up, status, load-language) for every Odoo
series the index carries - resolve that set with `list_available_versions()`, never from a
remembered floor. Use this skill when the caller already knows the operation parameters; it hands
them over and relays a structured `instance-ops` block. The interactive human wizard that writes
`instances.toml` is `/odoo-setup`.

**Single owner of instance provisioning.** Route every live-instance need here via the Skill tool;
never drive the lifecycle yourself. The instance-allocation rules and the HARD
RULES (demo by build purpose, the GATE_ROLE-conditioned lint-module install, per-version `cli_help`
grounding) apply on every path. A provided `INSTANCE_HANDLE` ALWAYS wins over self-provisioning
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`). A bare `lease_acquire` +
`instance_build` is never how a caller PROVISIONS an instance. Tearing your OWN lease down at your
terminal status - `lease_release` or `lease_park` - is not provisioning and is run directly
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).

**Launch by default.** A caller that can launch an agent (skill, spawner, node-owner) has this skill
LAUNCH `odoo-instance-ops` with `model: haiku` for every build, test run, serve and export, per "Brief
shape", and keeps the returned `INSTANCE_HANDLE` as the run-level owner of its lease. Run INLINE
(see "Inline mode") only when:

- (a) the caller is a declared HARD LEAF (`agents.<name>.role == leaf` in
  `generator/skill_tool_deps.json`): it cannot launch;
- (b) `MODE_HINT: path-incremental`;
- (c) the operation is read-only and quick: `status`, or an `ensure-up` that finds the instance
  already serving;
- (d) `park`, `drop` or release of a lease the caller itself holds (obtained or handed back up).

## Dispatch

When invoked, gather the following from the caller's request:

| Parameter | Values / notes |
|-----------|----------------|
| `operation` | `create` / `drop` / `park` / `resume` / `init` / `update` / `run-tests` / `ensure-up` / `status` / `load-language` |
| `series` | the Odoo series - required for create/init/update/run-tests/resume; optional for status |
| `lease_token` | required for `park` - the `lease_token` field of the `INSTANCE_HANDLE` being finished with. Not used by any other operation. `park` and `drop` of a lease the CALLER holds run inline (exception (d)), never via `odoo-instance-ops` |
| `park_ttl_s` | optional for `park` - how long the suspended database is kept before a gc may reclaim it. Omitted keeps the tool's default; state the default in the relay when the caller named none |
| `persist` | What a CALLER may request: `ephemeral` (default) / `exclusive-running` / `shared-running`. Meanings, and the `exclusive-parked` state a suspended instance sits in: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5. An `exclusive-running` instance never converges on `8069` (its port comes from the allocator pool); a `shared-running` one is shared by every reader on that series |
| `run_id` | the caller's run id - threaded into every brief and passed to every lease tool as the lease owner. A lease tool called with no `run_id` is refused (`RUN_ID_REQUIRED`). Never invent one: a caller that gave none gets `NEEDS_CONTEXT(RUN_ID)` |
| `PROFILE` | Tenant profile name (the exact name a profile listing returns). Resolve it per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` (rung 2 returns the exact declared `profile` for the `[[instance]]` covering this repo - use it verbatim) and thread it through, unless the caller passes it (`odoo-doc-site` does: the profile part of the site row's `instance` key). A profile reaches `lease_acquire` as its `profile` ONLY when `catalog_read` (that `series`, that profile) returns a row; the acquire refuses a name no row declares (`NO_INSTANCE`), and an omitted profile takes the series' first row. An EMPTY `INST_PROFILE` from rung 2 means rung 2 did not answer this fact: fall through to the rungs below, and if none names one, OMIT the field rather than send `PROFILE: ''`; an empty `INST_PROFILE` never discards `INST_SERIES`. REQUIRED input for the agent's lint-module HARD RULE below - when omitted, the agent resolves the series' vanilla profile itself or BLOCKs rather than probe unprofiled |
| `modules` | comma-separated or list; required for `init` / `update` / `run-tests`. A caller driving a plan node passes that node's `modules` list here. For the stand-alone proof and for acceptance the install set is the node's modules ONLY; a dependent or a sibling is added only in the second, explicitly requested build (`${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`) |
| `demo` | `on` / `off` - whether an `init` / `create` build must carry demo data; it reaches `instance_build` as its `demo` argument. Set it from the build's PURPOSE per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE. **There is no flat default** - omitted, the agent derives the value from the purpose and BLOCKs where the purpose does not resolve and the output depends on demo. `run-tests` takes NO `demo`: a test build runs the series default - never set it for a test dispatch |
| `test_tags` | `run-tests` scope selector (`modules` builds the registry, `test_tags` decides whose tests run). Pass the caller's resolved blast radius, normally `/<m>` per module in `modules` (e.g. `/sale,/account`), narrowable to a class or method (`/module:ClassName.method_name` - the CLASS separator is a COLON) for a focused re-run. `full` = run untagged ON PURPOSE (release sweep, CI/Runbot parity, no-code-change smoke). OMITTED / `none` = not supplied: the agent DERIVES `/<m>` per module and never runs untagged. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`; which modules belong in the set: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md` |
| `GATE_ROLE` | `pre-pr-lint-gate` / `node-verify` - REQUIRED for `run-tests`, and any `init`/`update` dispatch whose purpose is running automated tests via `--test-enable`; decides whether the agent unions the lint-class modules into the install list + `--test-tags` (see "Agent-side union" below). `pre-pr-lint-gate` is reserved for the ONE run-level pre-PR lint-class gate (the plan's `integrate` node states it explicitly); every OTHER test-run caller (a node verification run, a leaf's own break-check run, an ad-hoc human "run the tests" request) is `node-verify`. This skill resolves it before dispatch (rule below) |
| `mode` | `fresh` / `reuse` (`run-tests` only) - decided on the DATABASE: `reuse` whenever the target database already has the modules installed, `fresh` only for the FIRST install onto a brand-new database; `fresh` -> `-i` (init+test), `reuse` -> `-u` (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an existing database) |
| `hand_on` | `yes` / `no` (default `no`; `run-tests` with `mode=fresh` only) - `yes` keeps the lease and forwards its `INSTANCE_HANDLE` to the caller, who owns it from then on; `no` releases it when the run ends |
| `log_mode` | `info` / `debug` / `sql` (optional; `run-tests` only) - overrides the odoo log verbosity for this run; omitted keeps the default below. `warn` is REFUSED - it hides the pass summary |
| `fresh_venv` | `true` / `false` (default `false` - build on the venv the catalog declares for the series). `true` makes the executor rebuild the series' venv before it acquires a lease; a catalog row with no venv at all gets one built the same way without asking. Never combine `true` with a forwarded `INSTANCE_HANDLE`: that lease fixes the interpreter |
| `languages` | csv locale codes (e.g. `vi_VN,fr_FR`); required for `load-language`; optional for `create` / `init` / `run-tests`. It reaches `instance_build` as its `languages` argument; the tool adds `en_US` to every build, so neither the caller nor this skill adds it; omit / pass `none` for `en_US` alone |
| `skip_auto_install` | `true` / `false` (default `false`; forced `true` when `context=doc`) - the executor adds the skip-auto-install flag to every build of the dispatch, where the series' `cli_help` lists it |
| `context` | `doc` / `default` (default `default`; `doc` auto-sets `demo=on` + `skip_auto_install=true` for a clean documentation instance) |
| `mode_hint` | `path-incremental` / `default` (default `default`). `path-incremental` = ONE lease held across a sequential delta-install loop on ONE DB (dependency-cluster documentation). It ALWAYS runs INLINE in the driving skill's context per § Inline mode `MODE_HINT: path-incremental` below and is NEVER dispatched to `odoo-instance-ops` |
| `WORKTREE_PATH` | (optional) absolute path to the worktree whose code this instance must load. When set, the executor re-roots the addons list passed to `lease_acquire` onto it per § WORKTREE_PATH substitution below. Omit for a catalog-tree instance |

Anything the caller omits that is strictly required for the operation: ask ONE clarifying
question covering all missing required parameters before dispatching.

**`park` vs `drop` - decide on a fact about the DATABASE.** `park` KEEPS the database, filestore and
ports so a later `resume` picks the instance up where it was; `drop` destroys the database. A caller
finished with the instance FOR NOW but still wanting its data gets `park` - never a `drop` dispatch
in the hope it will be declined. `resume` brings a parked instance back on its own coordinates and
never rebuilds or installs modules.

**`GATE_ROLE` resolution (mandatory, resolved by THIS skill before dispatch).** For any `run-tests`
(or test-enable `init`/`update`) request: an explicit value already present in the caller's context
(the plan's pre-PR lint gate, or `odoo-coder`'s own node test) wins - forward it verbatim. For a
direct/human-initiated invocation with no stated role, use `GATE_ROLE: node-verify` and state the
assumption. Forward `GATE_ROLE: pre-pr-lint-gate` only when the caller explicitly identifies itself
as that ONE gate - never inferred from module count, phrasing, or any other proxy. The dispatched
`odoo-instance-ops` agent always receives a resolved `GATE_ROLE`.

**Log verbosity default.** Every build (`create` / `init` / `update` / `run-tests`) runs at
`--log-level=info`. Override per dispatch: `run-tests` via `log_mode`; the rest via a `--log-level`
in the brief's extra flags, which is placed after the default and wins. Ground `--log-level` via
`cli_help` like any other flag.

**Active-wait and completion (relay).** `instance_build` returns a `job_id`; the executor's very next call is `job_wait(job_id)`, repeated while `result` is `timeout`, every response carrying a tool call. Only `success` passes; `inconclusive` (no test matched or all skipped) and `lost` are never green and hold the caller back; a job is DONE when `job_wait` returns a terminal result and an instance READY when `instance_serve` returns its URL - never a log tail. Full contract: `references/dispatch-detail.md` § Active-wait and completion; `odoo-instance-ops`'s own sections.

**Build facts and the agent-side union.** `instance_build` applies the series' server-wide modules, `languages` (with `en_US`) and the demo flag itself; pass `languages` and (init/create only) `demo` as fields, a different server-wide set as `SERVER_WIDE`, never as extra flags (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Build facts the odoo-local tools apply). This skill resolves `PROFILE` and threads it in; the dispatched agent pins it, unions the framework-validation classes into every tagged run, and installs and tags the lint-class modules ONLY under `GATE_ROLE: pre-pr-lint-gate` (`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`). Detail: `references/dispatch-detail.md` § Build facts and the agent-side union.

**Confirmation.** `create`, `init`, `update` and `run-tests` run without asking. Ask the human in
text (`approve / skip / cancel`) only before a `drop` of a database this run did not create; a
`drop` of a database created in this run proceeds. `park` and `resume` never ask.

**Brief shape:** Launch the `odoo-instance-ops` agent with a worker brief per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. When composing the dispatch prompt for any
specialist agent you dispatch, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief. The brief must include:

```
OPERATION: <operation>
SERIES: <series or 'unspecified'>
PROFILE: <the NON-EMPTY profile name this skill already resolved before composing this brief;
  omit the field entirely when the resolved value is empty or no rung named one -
  never emit PROFILE: '' and never forward a pointer for the agent to go re-resolve>
MODULES: <comma-separated list or 'none'>
DEMO: <on|off>                # init/create only; omitted on run-tests - the series default applies
TEST_TAGS: <the resolved scope tags (normally `/<m>` per module in MODULES), or 'full' to run
  untagged on purpose; 'none'/omitted means NOT SUPPLIED and the agent derives `/<m>` per module -
  it never means "run every installed module's suite">
GATE_ROLE: <pre-pr-lint-gate|node-verify>   # REQUIRED for run-tests / test-enable init/update; resolved above - never omitted, never left for the agent to guess
MODE: <fresh|reuse>           # run-tests only; reuse whenever the target DB already has the modules, fresh only for a first install on a new DB
LOG_MODE: <info|debug|sql or 'default'>   # run-tests only; 'default' keeps the build default
FRESH_VENV: <true|false>
PERSIST: <ephemeral|exclusive-running|shared-running>   # create only; default ephemeral - see the dispatch table above
HAND_ON: <yes|no>             # run-tests fresh only; yes = keep the lease and forward its INSTANCE_HANDLE; default no = release it
LEASE_TOKEN: <token of the lease to suspend>            # park only - REQUIRED there, omitted everywhere else
PARK_TTL_S: <seconds or 'default'>                      # park only; 'default' keeps the tool's own budget
INSTANCE_HANDLE: <the caller's forwarded handle, verbatim>    # omit when none; every operation then runs on that lease/database (ensure-up serves it)
RUN_ID: <the caller's run id>                           # ALWAYS set - the lease-ownership identity; never invent one
LANGUAGES: <csv target locales, or 'none'; the tool adds en_US to every build>
SERVER_WIDE: <{exclude: [...], include: [...]} from the caller's brief, verbatim>   # omit unless the caller names one; the catalog row's set applies
SKIP_AUTO_INSTALL: <true|false>
CONTEXT: <doc|default>
WORKTREE_PATH: <absolute worktree path, or 'none'>   # when set, the agent re-roots its lease's addons list onto it
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve; the agent appends the run worklog and must not key it on WORKTREE_PATH's own toplevel>
```

`INSTANCE_RESOLUTION`, `ALLOCATOR`, and `OSM_GROUNDING` are NOT brief fields: the dispatched agent's
own "Common preamble" (Steps A-D) and port-flag tie-break own that procedure. Never add a field whose
value is a procedure to follow rather than a value this skill already resolved.

### Resolving `modules` + `test_tags` for a `run-tests` with no plan node

A plan node passes its own `modules` and tags. For an ad-hoc run resolve ONE module set `M` first: the modules the working tree's changed files belong to (descriptor by both filenames; the file list from `git-toolkit:git-ops`), plus the in-repo blast radius of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md` § Run-set; then pass `MODULES: <M>` and `TEST_TAGS: /<m>` per module - never modules with blank tags. A deliberate full sweep passes `TEST_TAGS: full` with its exemption (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Steps: `references/dispatch-detail.md` § Resolving modules and test_tags.

### WORKTREE_PATH substitution

A build that must load a worktree's code leases the catalog addons list re-rooted onto that
worktree: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/references/worktree-addons-path.md`. The
executor runs it - the dispatched agent from the brief's `WORKTREE_PATH`, inline mode before
its own `lease_acquire`.

**Relay the result.** Relay the agent's `instance-ops` block verbatim: it IS the run's `INSTANCE_HANDLE` (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`), forwarded into every downstream brief instead of self-provisioning. A `NEEDS_CONTEXT` from the agent is surfaced with its `blocked_reason`, never retried blind. Every `run-tests` relay carries the scope it was decided on (tags used and their provenance, modules loaded, tests run, any verdict from outside the module under verification) - never a dropped module, never an unrequested `skip_auto_install` (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Block schema: `references/dispatch-detail.md` § Relay the result.

### Inline mode (exceptions (a)-(d) only)

The ops steps run in the caller's own context under the same HARD RULES as the agent: with an `INSTANCE_HANDLE`, never provision, release, park or adopt its lease (a test run takes one small lease of its own on that database, `test_mode` `reuse`, released before return); without one, (1) interpreter then an isolated ephemeral `lease_acquire` under the caller's `run_id` with the worktree addons path, (2) `set_active_version` + `cli_help`, (3) the build facts and the gated lint union, (4) `instance_build` then `job_wait` to a terminal result, `instance_serve` only after success, (5) one of the three lease exits (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T4), emitting the same `instance-ops` block. `MODE_HINT: path-incremental` (`CONTEXT: doc`) is the ONE definition of the held-lease delta-install loop (A provision once, B init-delta, C ensure-up, D convergence-fill, E release at path end), always inline. Step detail and the loop: `references/dispatch-detail.md` § Inline mode.

### Multi-instance parallel provisioning

Each concurrent `lease_acquire` caller gets an independent ephemeral lease. Keep at most ~3
simultaneous ephemeral instances; the orchestrator manages the budget. Use `CONTEXT: doc` for clean
documentation instances. For browser-bound capture workers, cap W per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity (full rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2); browser-free phases (feature-map,
icon, copy) fan out wider. Never `createdb`/`dropdb` raw - always through Odoo and the lease tools.
Callers that share ONE database follow `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`
§ One build or export per database.

## Out of Scope

- **Writing or reviewing application code** - route to `odoo-coding` or `odoo-code-review`
- **Debugging application logic or runtime errors** - route to `odoo-debug`
- **Designing a technical solution** - route to `odoo-solution-design`
- **Translating a module** - route to `odoo-i18n`
- **Interactive declare-and-spinup of `instances.toml`** - that is `/odoo-setup` (human wizard);
  this skill is for programmatic dispatch where the caller already knows the parameters

## Standalone-first fallback

When OSM (the `odoo-semantic-mcp` server) is unreachable, the executor grounds per-version CLI
flags from the local Odoo source instead of `cli_help`, labelled `grounded: local-source`
(`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`). Provisioning never degrades - only
OSM-grounded CLI discovery falls back locally.

When the series' catalog row declares no venv (no `python`, a `lease_acquire` result with
`venv_missing: true`, or a build refused with `VENV_MISSING`), the executor builds it with `45-venv.sh create-venv`
(per `${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md`) and acquires afterwards. When the catalog
declares no instance for the series at all (`catalog_read` returns no row), nothing is built from
scratch: surface ONE `NEEDS_CONTEXT` naming exactly what is missing and route the human to
`/odoo-ai-agents:odoo-setup`, which declares the instance. Never guess an addons path, a DB host or
an interpreter.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='<profile from the resolved instance entry>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `list_available_versions` ☆ - Enumerate which Odoo versions the server has indexed.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->
