---
name: odoo-instance
argument-hint: "[create|drop|park|resume|init|update|test|load-language] [version|db]"
description: >-
  Create, update, test, stop or drop a live local Odoo instance
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

**Active-wait on long builds (relay).** `instance_build` returns a `job_id` at once; the executor's
VERY NEXT call MUST be `job_wait(job_id)`, called again with the same `job_id` for as long as its
`result` is `timeout`, and every response before a terminal `result` MUST carry a tool call - a
text-only "waiting for the build" reply that ends the turn is forbidden. `timeout` is the ONLY
result that means keep waiting; the executor compares the `progress` reading between waits and
reports `BLOCKED` with `log_path` preserved only once a whole window leaves a NON-EMPTY `progress`
unchanged. `success` is the only pass. `inconclusive` means the run FINISHED and refused to certify
a pass (its tag filter matched no test, or every matched test was skipped): never wait again on it
and never relay it as green - handle it as `tests-inconclusive`, surface `findings_path` and
`log_path`, and hold the caller back from merge or the next phase. `lost` is never a pass either.
For `run-tests` the verdict is the run's own `test_result`; `Modules loaded.` is only PROGRESS.
Full contract: `odoo-instance-ops`'s own "Active-wait on long builds".

**Readiness/completion signal is DETERMINISTIC, never a log tail.** An install/update/test job is DONE
when `job_wait` returns a terminal `result` for it; a LISTENING instance is READY when
`instance_serve` returns its URL. Full contract: `odoo-instance-ops`'s own "Deterministic completion
contract" and `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md` item 14.

**Build facts the tools apply.** `instance_build` applies the series' server-wide modules, the
requested `languages` (always with `en_US`) and the series' demo flag itself. Pass `languages` as a
dispatch field, `demo` only for an `init` / `create` build, and never put those flags (or `--load`)
in extra flags. When the caller's task needs a server-wide set different from the catalog row's
(exclude the deployment's branding modules; include a new module that must load server-wide),
forward it as `SERVER_WIDE`; it reaches every build and serve of that database as `server_wide`.
Rules, including what to do with a `job_wait` warning that a module must be loaded server-wide:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Build facts the odoo-local tools apply.

**Agent-side union this skill does not compute itself.** This skill resolves `PROFILE` and threads it
into the brief (omitted when empty, never sent empty). The dispatched `odoo-instance-ops` agent PINS
that profile (`set_active_profile` + explicit `profile_name=` on every probe; an absent `PROFILE`
field triggers the agent's own vanilla-profile resolution) before one DATA-DRIVEN union:
- **Lint modules for `run-tests` - GATED.** Only when this dispatch's `GATE_ROLE` is
  `pre-pr-lint-gate`: the agent resolves and probes the lint-class modules per
  `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md` and unions every present one into BOTH the
  `-i`/`-u` install list and `--test-tags`. For `GATE_ROLE: node-verify` the agent does NOT probe,
  install, or tag any of them. A `run-tests`/test-enable dispatch reaching the agent with
  `GATE_ROLE` unresolved runs as `node-verify` with the assumption stated, unless it names a
  lint-class module (then `NEEDS_CONTEXT`). Full contract: `odoo-instance-ops`'s own "Lint modules -
  installed ONLY for the designated pre-PR lint gate (HARD RULE)" and
  `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` "Install the lint modules (not just tag them)".
  A clean counter set on a `pre-pr-lint-gate` dispatch is NOT `tests-passed` until the agent's own
  coverage confirmation clears too (`odoo-instance-ops`'s own "Checker-load coverage confirmation").

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

A caller driving a plan node passes that node's `modules` list (authored by `odoo-planner` per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`) and the matching tags. For an AD-HOC run
- a human asking to test a change, a leaf confirming its own edit - resolve the same module set `M`
yourself before dispatching, in this order:

1. **Modules actually changed.** Map the working tree's changed files to their owning modules: the
   module is the nearest ancestor directory holding a module descriptor - glob for BOTH descriptor
   filenames, per the "Module manifest (descriptor) filename" row of
   `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`. Ask
   `git-toolkit:git-ops` for the paths of the files changed in the working tree (modified, added
   and untracked), as a list in the reply.
2. **In-repo blast radius.** Add the modules in THIS repo whose own suites exercise a model the
   change touched, keeping only owners that live in the repo under test. Coverage lookup, ceiling and
   the OSM-down degrade: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md` § Run-set.
3. **Both fields, from that one set.** Pass `MODULES: <M>` (dependency order) and `TEST_TAGS: /<m>`
   per module. Never pass modules and leave the tags blank.

When the request is explicitly a full sweep, or no code changed at all, pass `TEST_TAGS: full` and
say which exemption applies (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`).

### WORKTREE_PATH substitution

A build that must load a worktree's code leases the catalog addons list re-rooted onto that
worktree: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/references/worktree-addons-path.md`. The
executor runs it - the dispatched agent from the brief's `WORKTREE_PATH`, inline mode before
its own `lease_acquire`.

**Relay the result:** Relay the agent's structured output block verbatim to the caller:

```instance-ops
op: <create-instance|drop-instance|park-instance|resume-instance|init-modules|update-modules|run-tests|ensure-up|status>
series: <X.Y>
db_name: <db_name>
http_port: <port or null>
gevent_port: <port or null (omit if not bound)>
db_port: <resolved port or empty>
run_id: <owning run id or empty>
modules_installed: [<list or null>]
demo: <true|false|null>                 # whether the DATABASE holds demo data
languages_loaded: [<list or null>]      # the DATABASE's active languages
facts_source: <database|leases>         # who answered demo / languages_loaded
venv_python: <path>
addons_path: <comma-separated path>
log_path: <log file path>
failed: <n or null>            # run-tests only; from TEST_FAILED=
errors: <n or null>           # run-tests only; from TEST_ERROR=
warnings: <n or null>         # run-tests only; from TEST_WARNING=
skipped: <n or null>          # run-tests only; from TEST_SKIPPED=
js_runs: <n or null>          # run-tests only; from JS_RUNS= (browser-suite logger scopes this build drove)
js_scope: <scoped|unscoped or null>   # run-tests only; from JS_SCOPE=
js_failed_reported: <n or null>       # run-tests only; from JS_FAILED_REPORTED= - never added to `failed`, it counts other units
js_failed_tests: <n or null>          # run-tests only; from JS_FAILED_TESTS=
findings_path: <path or null> # run-tests only; from FINDINGS_PATH= (failures + warnings + skips file)
lease_token: <token or null>
status: <one value of the agent's own enum, relayed as-is - never a Continuation status>
notes: <short human-readable summary or error; run-tests: ALWAYS carries the scope figures + any out-of-scope verdict, see below>
```

This `instance-ops` block IS the canonical `INSTANCE_HANDLE` for the run: the orchestrator forwards
it (`db_name` / `http_port` / `db_port` / `addons_path` / `venv_python` / `lease_token` / `run_id`) as
an `INSTANCE_HANDLE:` field into every downstream code / test brief, and downstream agents consume
it instead of self-provisioning. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

On the agent's Continuation `status: NEEDS_CONTEXT` (its `instance-ops` block reads `status: error`
on a refusal before launch), surface its `blocked_reason` and the refusal it quoted, then stop - do
not retry without the missing requirement.

**Scope transparency on every `run-tests` relay.** The run is BOUNDED to the declared scope
(`test_tags` you passed, else the agent derives `/<m>` per module in `modules`) and the result is
REPORTED with the scope it was decided on. Never drop a module in `modules` from the tags, and never
add a `skip_auto_install` the caller did not ask for. Relay verbatim in `notes` the agent's
tags-used + provenance and its scope figures (modules actually loaded, tests actually run), plus its
statement of any verdict decided by tests OUTSIDE the module under verification; never report an
out-of-scope `tests-failed` as this module's own regression. Rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`; agent side: `odoo-instance-ops`'s own Scope
transparency section.

### Inline mode (exceptions (a)-(d) only)

Run the ops steps INLINE in the caller's own context, without launching `odoo-instance-ops`, and
still under the HARD RULES.

With an `INSTANCE_HANDLE` in the brief, run the steps as the HANDLE-CONSUMER branch below changes
them; with none, self-provision via the numbered steps as written.

**HANDLE-CONSUMER branch (an `INSTANCE_HANDLE` is in the brief).** Never provision a database (skip
step 1's acquire) and never release, park or adopt the handle's own lease; an `init` / `update` build or a serve (including `ensure-up`: `instance_serve` on the handle's `lease_token`, never by `series`) runs on the handle's token. For a test build: when no server listens on
the handle's port, run it on the handle's token; when one does, take one small lease of your own on
the handle's database - one port, creating and dropping nothing - and run every `op test` there with
`test_mode` `reuse` (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`). Release what you
took before you return, on every exit
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1), and report the forwarded handle
unchanged.

Every step runs through the odoo-local tools (`mcp__plugin_odoo-ai-agents_odoo-local__<tool>`).
If the odoo-local tools are unavailable, use the allocator CLI documented in ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md.

Run these steps in order, honoring the SAME HARD RULES as the agent (`odoo-instance-ops`'s own
cross-referenced sections):

1. **Interpreter, then an isolated lease.** When `fresh_venv` is `true` or `catalog_read` shows no
   `python` on the series' row, build the venv first with `45-venv.sh create-venv` per
   `${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md` § If no suitable venv exists yet - the lease
   copies the catalog's interpreter at acquire time, so acquire only after it exits 0. Then
   `lease_acquire` (`series`, `profile` = `PROFILE` when a catalog row declares it (see the `PROFILE` row), mode `ephemeral`, your `run_id`, `cwd` = the
   tree you build, `addons_path` from § WORKTREE_PATH substitution when you work in a worktree;
   `ports` 1 for a test build or a listening instance - a test build binds an HTTP port on every
   series - else 0). Never reuse the single declared db/port for a mutation. A refused acquire
   writes no lease: follow the error code's remedy, never retry blind. A result with
   `venv_missing: true` is a lease no build can use: release it, build the venv, acquire again.
2. **Pin series + ground CLI flags** - `set_active_version` then `cli_help` per the agent's "Common
   preamble" Steps A-B (every flag from this series' `cli_help`, never from memory).
3. **Apply the HARD RULES** as the agent does - `languages`, the caller's `server_wide` (when it
   names one, on every build AND serve) and (never on a test build) `demo` passed as build arguments
   and every `job_wait` warning acted on (`odoo-instance-ops`'s own "Demo, languages and
   server-wide modules (HARD RULE)"), and lint-module install for a test-run build ONLY when
   `GATE_ROLE: pre-pr-lint-gate` (its own "Lint modules - installed ONLY for the designated pre-PR
   lint gate (HARD RULE)"). A HARD LEAF running here (self-provisioning, or `odoo-test-writer` running its break-check on
   a forwarded handle) uses `GATE_ROLE: node-verify` and never installs or tags any lint-class
   module. Resolve + PIN the profile before any probe; never probe
   profile-less.
4. **Run the operation** - `instance_build` (op `init` / `update` / `test`, `demo` on `init` only, `languages`,
   only `cli_help`-grounded flags in `extra_args` and never a port flag - the build binds the
   lease's own port; a test build carries the resolved `test_tags`), then `job_wait(job_id)` as the VERY NEXT call, re-called
   while `result` is `timeout`, every response carrying a tool call until the result is terminal;
   only `success` passes. Serve a listening instance with `instance_serve(lease_token)` (no `profile`)
   only after its build succeeded. Report the same run-tests scope figures (`TEST_TAGS_USED`,
   `MODULES_LOADED`, `TESTS_RUN` from the final `job_wait` summary).
5. **Clear the lease** when done, by ONE of the three exits - `lease_release`, `lease_park` when
   the database is still wanted, or forward the handle to a NAMED catcher in `next.inputs`
   (`INSTANCE_HANDLE`, naming the skill that needs the live state). A lease left on none of the
   three at your terminal status is a leak. Full rule:
   `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T4. Whichever exit you take,
   emit the same `instance-ops` block the launched agent emits.

**`MODE_HINT: path-incremental` (with `CONTEXT: doc`) - the ONE definition of this loop.** The
driving skill holds ONE lease across a sequential delta-install walk on ONE database and calls this
branch once per step, always INLINE. NEVER dispatch `odoo-instance-ops` for any step. The driving
skill decides which module is next, when to capture and when to end; each step below does exactly
one thing and returns the `instance-ops` block.

- **A. Provision once** (the dependency-graph leaf module). Steps 1-4 above: `lease_acquire`
  (mode `ephemeral`, ports 1), `instance_build` op `init` with the doc-context flags
  (`odoo-instance-ops`'s own "Doc-context provision"), `job_wait`, then `instance_serve(lease_token)`.
  Do NOT run step 5: hold the `lease_token` and return the block as the path's `INSTANCE_HANDLE`.
- **B. Init-delta.** `instance_build` op `init` for the next module on the HELD `lease_token`, with
  the SAME demo as step A, and with the skip-auto-install flag AND the no-HTTP flag in `extra_args`
  on EVERY delta (the served process already holds the lease's port), then `job_wait`. Never
  acquire a second lease for the path.
- **C. Ensure-up.** `instance_serve(lease_token)` on the held token, when the driving skill asks.
- **D. Convergence-fill** (branching clusters only). ONE delta build installing exactly the
  still-missing modules the plan lists, same flags as B, then C.
- **E. Release.** `lease_release(lease_token, run_id)` at path completion only - never between
  steps. This is the path's step 5.

An independent branch is a separate path: its own A on a fresh lease, its own E.

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
