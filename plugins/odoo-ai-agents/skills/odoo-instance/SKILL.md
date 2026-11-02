---
name: odoo-instance
argument-hint: "[create|drop|park|resume|init|update|test|load-language] [version|db]"
description: >-
  Creates, updates, tests, stops or drops a live local Odoo instance
---

## Role

Odoo instance lifecycle front door for ALL instance lifecycle operations (create, drop, park, resume, init, update, run-tests, ensure-up, status, load-language) for every Odoo series the index carries - resolve that set with `list_available_versions()`, never from a remembered floor. Use it when the caller already knows the operation parameters; it hands them over and relays a structured `instance-ops` block. The interactive human wizard that writes `instances.toml` is `/odoo-setup`.

**Single owner of instance provisioning.** Route every live-instance need here via the Skill tool; never drive the lifecycle yourself. The instance-allocation rules and the HARD RULES (demo by build purpose, the GATE_ROLE-conditioned lint-module install, per-version `cli_help` grounding) apply on every path. A provided `INSTANCE_HANDLE` ALWAYS wins over self-provisioning (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`). A bare `lease_acquire` + `instance_build` is never how a caller PROVISIONS an instance. Tearing your OWN lease down at your terminal status - `lease_release` or `lease_park` - is not provisioning and is run directly (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).

**Launch by default.** A caller that can launch an agent (skill, spawner, node-owner) has this skill LAUNCH `odoo-instance-ops` with `model: haiku` for every build, test run, serve and export, per "Brief shape", and keeps the returned `INSTANCE_HANDLE` as the run-level owner of its lease. Run INLINE (see "Inline mode") only when: (a) the caller is a declared HARD LEAF (`agents.<name>.role == leaf` in `generator/skill_tool_deps.json`): it cannot launch; (b) `MODE_HINT: path-incremental`; (c) the operation is read-only and quick: `status`, or an `ensure-up` that finds the instance already serving; (d) `park`, `drop` or release of a lease the caller itself holds (obtained or handed back up).

## Out of Scope

- **Writing or reviewing application code** - route to `odoo-coding` or `odoo-code-review`
- **Debugging application logic or runtime errors** - route to `odoo-debug`
- **Designing a technical solution** - route to `odoo-solution-design`
- **Translating a module** - route to `odoo-i18n`
- **Interactive declare-and-spinup of `instances.toml`** - that is `/odoo-setup` (human wizard); this skill is for programmatic dispatch where the caller already knows the parameters

## Dispatch

Gather the parameters from the caller's request; anything strictly required that the caller omits: ask ONE clarifying question covering all of it before dispatching. Full semantics of every parameter, the brief block, and the rules below: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/references/dispatch-parameters.md` (§ Parameters, § Brief shape).

- `operation`: `create` / `drop` / `park` / `resume` / `init` / `update` / `run-tests` / `ensure-up` / `status` / `load-language`. `series`: required for create/init/update/run-tests/resume.
- `lease_token` (park only, the `INSTANCE_HANDLE`'s field), `park_ttl_s` (park, optional). `park` and `drop` of a lease the CALLER holds run inline (exception (d)), never via `odoo-instance-ops`.
- `persist`: `ephemeral` (default) / `exclusive-running` / `shared-running` (`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5).
- `run_id`: the caller's run id, passed into every brief and every lease tool as lease owner (`RUN_ID_REQUIRED` otherwise). Never invent one: none given -> `NEEDS_CONTEXT(RUN_ID)`.
- `PROFILE`: resolve per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` (rung 2, verbatim) unless the caller passes it. EMPTY: fall through the rungs, else OMIT the field, never `PROFILE: ''`.
- `modules`: required for `init` / `update` / `run-tests`; a plan node's `modules` list; stand-alone proof and acceptance install the node's modules ONLY (`${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`).
- `demo` (`on` / `off`; init/create only): from the build's PURPOSE per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE; NO flat default; `run-tests` takes NO `demo`.
- `test_tags`: `run-tests` scope selector: normally `/<m>` per module, a class or method as `/module:ClassName.method_name` (the CLASS separator is a COLON); `full` = untagged ON PURPOSE; omitted / `none` = the agent DERIVES `/<m>` per module, never untagged (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`, `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`).
- `GATE_ROLE`: `pre-pr-lint-gate` / `node-verify`, REQUIRED for `run-tests` and any test-enabling `init` / `update`.
- `mode` (`run-tests`): `reuse` whenever the target DB already has the modules (`-u`), `fresh` only for the first install on a new DB (`-i`). `hand_on` (`run-tests` fresh; default `no`): `yes` keeps the lease and forwards its `INSTANCE_HANDLE`. `log_mode`: `info` / `debug` / `sql` (`warn` REFUSED).
- `fresh_venv` (default `false`; never `true` with a forwarded `INSTANCE_HANDLE`), `languages` (csv; required for `load-language`; the tool adds `en_US`), `skip_auto_install` (forced `true` when `context=doc`), `context` (`doc` sets `demo=on` + `skip_auto_install=true`), `mode_hint` (`path-incremental` ALWAYS runs INLINE, never via `odoo-instance-ops`), `WORKTREE_PATH` (re-roots the addons list, see below).

**`park` vs `drop`.** `park` KEEPS database, filestore and ports for a later `resume`; `drop` destroys the database. A caller finished FOR NOW but wanting its data gets `park`.

**`GATE_ROLE` resolution (by THIS skill before dispatch).** The caller's explicit value wins, forwarded verbatim; none stated: `node-verify`, assumption stated. `pre-pr-lint-gate` only when the caller explicitly identifies itself as that ONE run-level gate, never inferred.

**Log verbosity.** Every build runs `--log-level=info`; override via `log_mode` (`run-tests`) or a `--log-level` in the brief's extra flags.

**Active-wait and completion.** After `instance_build` the next call is `job_wait(job_id)`, repeated while `result` is `timeout`; only `success` passes (`inconclusive` and `lost` never green); DONE on a terminal `job_wait` result, READY when `instance_serve` returns its URL, never a log tail. `references/dispatch-detail.md` § Active-wait on long builds (relay) and the deterministic completion signal.

**Build facts and the agent-side union.** Pass `languages` and (init/create only) `demo` as fields, a different server-wide set as `SERVER_WIDE`, never as extra flags. The agent installs and tags the lint-class modules ONLY under `GATE_ROLE: pre-pr-lint-gate`. `references/dispatch-detail.md` § Build facts the tools apply and the agent-side union.

**Confirmation.** `create`, `init`, `update` and `run-tests` run without asking. Ask in text (`approve / skip / cancel`) only before a `drop` of a database this run did not create; `park` and `resume` never ask.

**Brief shape.** Launch `odoo-instance-ops` with a worker brief per `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`, filled from `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton plus the agent's family delta (never inline that file into a hard-leaf brief). The full block: `references/dispatch-parameters.md` § Brief shape. Fields:

```
OPERATION: SERIES: PROFILE: (omit when empty) MODULES: DEMO: (init/create) TEST_TAGS: MODE: LOG_MODE:
FRESH_VENV: PERSIST: HAND_ON: LEASE_TOKEN: PARK_TTL_S: (park) LANGUAGES: SERVER_WIDE: (only when named)
SKIP_AUTO_INSTALL: CONTEXT: WORKTREE_PATH:
GATE_ROLE: <pre-pr-lint-gate|node-verify>   # REQUIRED for run-tests / test-enable init/update
INSTANCE_HANDLE: <the caller's handle, verbatim; omit when none>
RUN_ID: <the caller's run id, ALWAYS>
SHARE_DIR: / ISOLATE_DIR: <the run's captured absolute paths, never re-resolved>
```

Never add a field whose value is a procedure rather than a value already resolved (no `INSTANCE_RESOLUTION`, `ALLOCATOR` or `OSM_GROUNDING` field).

### Resolving `modules` + `test_tags` for a `run-tests` with no plan node

A plan node passes its own `modules` and tags. For an ad-hoc run resolve ONE module set `M` first: the modules the working tree's changed files belong to (descriptor by both filenames; file list from `git-toolkit:git-ops`), plus the in-repo blast radius of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md` § Run-set; pass `MODULES: <M>` and `TEST_TAGS: /<m>` per module - never modules with blank tags. A deliberate full sweep passes `TEST_TAGS: full` with its exemption (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Steps: `references/dispatch-detail.md` § Resolving modules and test_tags.

### WORKTREE_PATH substitution

A build that must load a worktree's code leases the catalog addons list re-rooted onto that worktree: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/references/worktree-addons-path.md`. The dispatched agent runs it from the brief's `WORKTREE_PATH`; inline mode, before its own `lease_acquire`.

**Relay the result.** Relay the agent's `instance-ops` block verbatim: it IS the run's `INSTANCE_HANDLE` (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`), forwarded into every downstream brief instead of self-provisioning. A `NEEDS_CONTEXT` is surfaced with its `blocked_reason`, never retried blind. Every `run-tests` relay carries the scope it was decided on (tags used and their provenance, modules loaded, tests run, any verdict from outside the module under verification) - never a dropped module, never an unrequested `skip_auto_install` (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Block schema: `references/dispatch-detail.md` § Relay the result.

### Inline mode (exceptions (a)-(d) only)

The ops steps run in the caller's own context under the same HARD RULES as the agent: with an `INSTANCE_HANDLE`, never provision, release, park or adopt its lease (a test run takes one small lease of its own on that database, `test_mode` `reuse`, released before return); without one, (1) interpreter then an isolated ephemeral `lease_acquire` under the caller's `run_id` with the worktree addons path, (2) `set_active_version` + `cli_help`, (3) the build facts and the gated lint union, (4) `instance_build` then `job_wait` to a terminal result, `instance_serve` only after success, (5) one of the three lease exits (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T4), emitting the same `instance-ops` block. `MODE_HINT: path-incremental` (`CONTEXT: doc`) is the ONE definition of the held-lease delta-install loop (A provision once, B init-delta, C ensure-up, D convergence-fill, E release at path end), always inline. Step detail: `references/dispatch-detail.md` § Inline mode.

### Multi-instance parallel provisioning

Each concurrent `lease_acquire` caller gets an independent ephemeral lease. Keep at most ~3 simultaneous ephemeral instances; the orchestrator manages the budget. Use `CONTEXT: doc` for clean documentation instances. Browser-bound capture workers: cap W per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity (rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2); browser-free phases fan out wider. Never `createdb`/`dropdb` raw - always through Odoo and the lease tools. Callers sharing ONE database follow `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or export per database.

## Standalone-first fallback

When OSM is unreachable, the executor grounds per-version CLI flags from local Odoo source instead of `cli_help`, labelled `grounded: local-source` (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`); provisioning never degrades. When the series' catalog row declares no venv (no `python`, `lease_acquire` with `venv_missing: true`, or a build refused with `VENV_MISSING`), the executor builds it with `45-venv.sh create-venv` (`${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md`) and acquires afterwards. When the catalog declares no instance for the series (`catalog_read` returns no row), build nothing: surface ONE `NEEDS_CONTEXT` naming what is missing and route the human to `/odoo-ai-agents:odoo-setup`. Never guess an addons path, a DB host or an interpreter.

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
