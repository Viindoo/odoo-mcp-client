# instance-ops operations - per-operation detail

Per-operation procedure of the `odoo-instance-ops` agent for operations 1-4 and 6-9, restart,
doc-context provisioning and multi-instance provisioning. The agent's HARD RULES, the common
preamble (Steps A-D), "Active-wait on long builds", the demo / language / server-wide rules, the
lint-gate rules, operation 5 (run-tests) and the output block stay in the agent file and bind every
operation here. "Active-wait" below means that section; "Step A-D" means the common preamble.

**Contents:** 1. create-instance - 2. drop-instance - 3. init-modules - 4. update-modules - 6. ensure-up / status - 7. load-language - 8. park-instance - 9. resume-instance - Restart on the same lease - Doc-context provision - `MODE_HINT: path-incremental` - Multi-instance parallel provisioning - Lint gate: probe and union - Run-tests adjudication - Step C detail - Warning handling - Run-tests counters - Step D detail

### 1. create-instance

Create a new Odoo database with a given module set for a target series.

**Inputs:** series, modules (list), demo (`on`/`off`; absent means DERIVE per "Demo, languages and server-wide modules"), languages (csv; `en_US` added by the tool), server_wide (optional), addons_path override (optional), `persist` (default `ephemeral`; values: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5), `run_id` (passed on every lease call; NEVER omitted).

**Resume before you build (listening `persist:` values only - FIRST).** `lease_find(series, state parked, run_id)`. `found=true` with `yours: true` -> operation 9, resume-instance, on that lease; do NOT acquire. `found=false` is an ordinary answer - build below. A run whose earlier session died finds here the built leases gc parked for it: resume the one this request needs and `lease_release` those it does not - a parked lease holds its ports until its budget lapses. Full ladder: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`.

**Mechanism - branch on `persist`:**

- **`persist: ephemeral`** (throwaway build, no listening server): `lease_acquire` (`series`, mode `ephemeral`, ports 0) -> `instance_build` (op `init`, the caller's FULL module set in one `modules` list, `demo`, `languages`) -> `job_wait` to a terminal `result`. `success` -> `status: created`; anything else -> `status: error` with `log_path` forwarded. The lease stays yours: forward its `INSTANCE_HANDLE` to the caller as the named catcher, or release it when the brief says the build was the whole job.

- **`persist: exclusive-running`** (a LIVE, listening instance that is MINE - its own database, an allocator-pooled port, my `run_id` as owner; NEVER converges on `8069`). **TWO LEGS, ONE lease**, build leg first, on the SAME lease token; serving alone yields an EMPTY database.
  1. `lease_acquire` - `series`, mode `ephemeral`, ports 1 (2 only under prefork per Step D; a browser-driven phase is never the reason).
  2. **Leg 1 - build.** `instance_build` (op `init`, FULL module set, `demo`, `languages`) -> `job_wait` to a terminal `result`. Anything but `success` ends this branch - never serve a failed build.
  3. **Leg 2 - listen.** `instance_serve(lease_token)`, no `profile`. It serves the lease's own database on its own port; `url` is the base URL. A lease with no port is refused (`LEASE_HAS_NO_PORT`) - BLOCK rather than fall back to the declared/`8069` port or a serve by `series`. Check that `served_addons_path` covers the modules you built.

  **HARD RULE - three invariants across the leg-1/leg-2 handoff** (a green HTTP probe proves none):
  1. **The lease mode is `ephemeral`** - never `exclusive` (holds the DECLARED database with no isolation). The lease carries `drop_on_release: true`: `lease_release` DROPS this database. Report the instance as a throwaway; across a gap you intend to return from, use operation 8 (park) then 9 (resume), never release.
  2. **One lease, both legs.** Build and serve on the byte-identical `lease_token` - never a second lease, never a serve by `series`.
  3. **The lease survives between the legs.** Do NOT release, park or gc it between leg 1 and leg 2.

- **`persist: shared-running`** (attach to, or start, the SHARED render target for this series). Do NOT call `lease_acquire`: call `instance_serve(series, run_id)`. `state: launched` = this call started the server and registered the shared lease under your `run_id`. `state: attached` = already running; `lease_token` is null unless the lease is your run's in this session. Never release or park it when you finish - release it only when the user explicitly asks to stop that render server. `shared_lease_error` set means the server is up but NOT leased - tell the user.

Every build above is driven to a terminal `result` per "Active-wait on long builds".

### 2. drop-instance

Drop an existing Odoo database through Odoo (never raw dropdb).

**Inputs:** the token of a lease THIS dispatch obtained, series. A token that only arrived in your brief is not yours: report that instead of calling. **Check first that a DROP is what the caller wants**: when the instance is finished with for now but its data still wanted, run operation 8, park-instance.

**Mechanism.** `lease_release(lease_token, run_id)`. It stops the server's whole process group and any build job still running on the lease, then drops the database of an ephemeral lease. `released` = clean teardown; `absent` = already released. `NOT_OWNER`: hand it back to the run that owns it, never work around it. `DROP_FAILED_KEPT`: follow its remedy and release again - never report it as a teardown; if it still fails, report it to the user. A database no lease tracks cannot be dropped through these tools: use the allocator CLI named in the agent's § The odoo-local tools (how every operation runs), never raw `dropdb`.

**If the HARNESS refuses the release before it runs:** the agent's § Teardown refused by the harness (operations 2 and 8).

### 3. init-modules

Install one or more modules into an existing Odoo database.

**Inputs:** series, db name or `INSTANCE_HANDLE`, modules (list), demo (derived as in create-instance when absent), languages (csv), addons_path override (optional).

**Mechanism.** With an `INSTANCE_HANDLE`, build on its `lease_token`. With only a db name, `lease_acquire` (`series`, mode `exclusive`, `db_name`, `no_create` true, ports 0) first. Then `instance_build` (op `init`, `modules`, `demo`, `languages`) -> `job_wait` to a terminal `result` (Active-wait). `success` is the only confirmed install; on anything else preserve `log_path` and surface it. Release a lease you acquired here when done (`no_create` drops nothing); never release the handle's.

### 4. update-modules

Update already-installed modules (-u). **Inputs:** series, db name or `INSTANCE_HANDLE`, modules (list).

**Mechanism.** Same lease handling as init-modules, then `instance_build` (op `update`, `modules`, `extra_args` carrying the version-correct no-HTTP flag so the run binds no port) -> `job_wait` to a terminal `result` (Active-wait).

### 6. ensure-up / status

Check whether an instance is running; start it if not. **Inputs:** series, db name (optional), `INSTANCE_HANDLE` (optional).

**Mechanism.** `instance_status(series[, profile], run_id)` reports whether the declared instance is up and its `url` (with the handle's `lease_token` instead: whether that lease is served, and its own `url`), plus the live `shared_lease` and the resumable `parked_lease` for the series (a parked lease carries its full token only when your run owns it and it is this session's or its session ended). `lease_list` (scope `mine`, or `run` with your `run_id`) reports what your run still holds; another session's row shows only its token prefix, and `session_alive: false` marks a lease whose session ended.

- **Status only:** `up` -> `status: up` with its `url` and the shared lease's coordinates. Not up but a `parked_lease` exists -> `status: parked` with its db and ports (and token when yours) - never `down`. Neither -> `status: down`.
- **Spin-up with an `INSTANCE_HANDLE`:** `instance_serve(lease_token=<the handle's lease_token>)` - serves the handle's own database on that lease (attaches when listening, resumes when parked, else launches; the database must have been built), creates no lease, never serves by `series`. Ask `instance_status(lease_token=...)` for the handle's state; `instance_status(series)` reports the declared instance, never the handle's.
- **Spin-up, no handle:** a `parked_lease` -> operation 9. Already `up` -> report it. Otherwise `instance_serve(series, run_id)`; it blocks until HTTP answers - do NOT call `lease_acquire` for an ensure-up. The shared-server rule of operation 1's `shared-running` applies.

### 7. load-language

Activate locales in an existing database. **Inputs:** series, db name or `INSTANCE_HANDLE`, languages (csv codes, e.g. `vi_VN,fr_FR`).

**Mechanism.** Steps A-D (an existing database: the handle's lease, else `lease_acquire` (`series`, mode `exclusive`, `db_name`, `no_create` true, ports 0)). Then `instance_build` (op `init`, `modules` `["base"]`, `languages` = the caller's codes, `demo` per the "anything whose output does not depend on demo" purpose row) -> `job_wait` to a terminal `result`. Re-installing `base` loads the languages without installing new modules. `languages_loaded` and `languages_failed` come from the final `job_wait`; a failed locale is a `concerns:` entry (`locale <x>: load failed - log: <log_path>`), the others still count (never abort for one). Put both lists in the output block (`languages_failed` when non-empty).

### 8. park-instance

SUSPEND an instance: stop its server if it has one, keep its database, filestore and ports for a later resume (third teardown exit, `resource-teardown-contract.md` T1 § The three exits). **Inputs:** the token of a lease THIS dispatch obtained, optional park budget in seconds; a token that only arrived in your brief is not yours - report that instead of calling.

**Mechanism.** No build runs: skip Steps B-D. `lease_park(lease_token, run_id[, park_ttl_s])`. Report `status: parked` with the token, db name and ports it returned; state the park budget in `notes` whenever the caller named none. `drop_on_release: true` means the final release still drops the database. A refusal leaves the instance as it was: report it and follow its remedy - never fall back to a drop the caller did not ask for.

### 9. resume-instance

Bring a PARKED instance back to running on its own database, filestore and ports - no rebuild, no `-i`/`-u`, no second lease. **Inputs:** the `lease_token` of the handle when the caller holds one, else series and `run_id`. Run Step A; do NOT call `lease_acquire`.

1. With a token: go to step 2 with it. Without one: `lease_find(series, state parked, run_id)` - it returns one lease, so a run that parked more than one instance of the series passes the token instead. `found=false` -> `status: down`; a caller that wanted an instance is routed to operation 1. A found lease with `yours: false` is another run's (token withheld): not yours to resume, release or park - report it in `notes` and treat the answer as `found=false`.
2. `yours: true` -> `lease_adopt(lease_token, run_id)` before serving, ALWAYS (every parked lease you did not obtain in this dispatch). A refused adopt (`LEASE_NOT_ADOPTED`): report it and do not serve.
3. `instance_serve(lease_token)`, no `profile` - resumes the parked lease (`resumed=true`) and returns its `url`. Report `status: up`. The running server is now yours to tear down like any lease you obtained: park, release or hand it off before your terminal status.

A refused resume leaves the lease unchanged and still parked: follow the error code's remedy (`DB_GONE` -> release it and build fresh via operation 1, reporting the rebuild in `notes`); never re-run the same serve hoping for a different answer.

### Restart on the same lease

A running instance on a lease THIS dispatch obtained keeps its database, filestore and ports across a restart. Python-only change: `lease_park(lease_token, run_id)`, then `instance_serve(lease_token)`. Manifest, data or field change: `instance_build` operation `update` on the same lease. Never kill or relaunch `odoo-bin` by hand - the lease tracks only the server its tools start. A handle that only arrived in your brief is not yours to park: ask its owner.

### Doc-context provision (demo + languages + the auto-install shape)

For documentation capture (`CONTEXT: doc`), one `instance_build` init carries `demo` `on` and `languages` = the capture locales. The auto-install shape follows `SKIP_AUTO_INSTALL`:

- `true` (the default under `CONTEXT: doc`) - a module's own documentation: the skip-auto-install flag goes in `extra_args` where `cli_help` lists it, so the instance renders the target module and its `depends` only. When the skip makes the target module fail to install, return `NEEDS_CONTEXT: auto-install bridge <name> required - install selectively?`; on the caller's yes, add only that bridge to `modules`, keep the flag, and name the bridge in `notes`.
- `false` - the product as users run it (a documentation site): no skip flag, so Odoo installs every auto-install module whose dependencies are met.

State the shape in `notes`: `auto_install: on`, `auto_install: skipped`, or `auto_install: on (the series has no skip flag)`.

### `MODE_HINT: path-incremental` - never yours

A brief carrying `MODE_HINT: path-incremental` gets `NEEDS_CONTEXT(MODE_HINT)` with the reason "run the path-incremental loop inline via the odoo-instance skill" - acquire nothing.

## Multi-instance parallel provisioning

Per instance: `lease_acquire` (`series`, mode `ephemeral`, `run_id`) -> the doc-context init for that lease -> emit the output block with its `INSTANCE_HANDLE` and `run_id`. `PORT_POOL_EXHAUSTED` is answered by releasing or parking a lease YOU hold, never someone else's. Cap: about 3 simultaneous ephemeral instances; browser pool cap `W`: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity. NEVER share a mutable DB across concurrent capture workers. Workers handed ONE database follow `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or export per database.

## Lint gate: probe and union

Applies only when `GATE_ROLE: pre-pr-lint-gate`. Resolve and PIN the profile BEFORE any probe - never call `check_module_exists` profile-less:

1. **Resolve.** Take the brief's `PROFILE:` (already resolved by the dispatching `odoo-instance` skill per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2). Absent: resolve the series' VANILLA profile - `list_available_profiles()`, filter to profiles reporting `<series>`, `profile_inspect(method='summary', name='<candidate>', odoo_version='<series>')` on each to find the one with an empty/root ancestor chain. Exactly one root candidate: pin it. Zero or several: STOP with `status: NEEDS_CONTEXT`, `blocked_reason: which profile to build against is unresolved for <series>`.
2. **Pin.** `set_active_profile(profile_name='<resolved profile>')` once, AND pass `profile_name='<resolved profile>'` explicitly on every `check_module_exists` call.

Then resolve WHICH modules the gate is made of and probe them exactly as `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md` specifies (it owns the candidate set read from the resolved addons path, the scoping and server-wide companion rules, and the stale-index rule that makes a bare probe insufficient). For every module it resolves as present:

1. UNION it into the build's `modules` list.
2. Append its tag to `test_tags` (one `/<module>` per resolved module).
3. Pass its own scoping options, set to the PR's modules, as the build's `conf_options` - option names read from that module's source, never assumed. A module whose source names none runs unscoped: say so in `notes`.

The install set and the tag set MUST derive from the SAME probe - never tag a module you did not install. The lint modules widen BOTH sides together and never license an untagged run (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`; `--test-tags` selection: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`).

## Run-tests adjudication

**"Fresh" is a claim until the log shows it.** A fresh install's base-load line carries seconds and thousands of queries, its "Loading module" count equals the module count, and the loaded-modules marker appears once per pid; a base load in zero queries is a reused database or a second process. Before a build, no other process may be on that database; after a detached launch, confirm ONE pid and never relaunch because the launcher looks idle. A red with many install-layer errors at once is suspected as two processes on one database before it is debugged.

**Scope adjudication (the agent's Scope transparency rule).** Adjudicate SCOPE from `findings_path`: a failing or erroring test whose module is NOT in `--modules` is OUT OF SCOPE. Whenever one exists, `notes` MUST state that the verdict was decided partly (or, when no in-scope test failed, ENTIRELY) by tests outside the module under verification, naming those modules. The verdict never softens: an out-of-scope failure is still `tests-failed` and BLOCKING. The one exception is a lint-class FINDING about code outside the PR's modules, decided by `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md` § Scope the gate to the PR's modules.

**Lint coverage (`GATE_ROLE: pre-pr-lint-gate` only - BEFORE trusting any branch above as a pass).** `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md` § Coverage evidence decides it; a shortfall escalates `status` to `tests-inconclusive` regardless of the counters.

## Step C detail

Run `45-venv.sh create-venv` exactly as `${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md` § If no suitable venv exists yet gives it, with `--series` and, when the brief names one, `--profile`; read the series' row with `catalog_read` (with `PROFILE` when the brief names one) before acquiring. `CREATEDB_UNDETERMINABLE` from `lease_acquire` (a row with neither `python` nor `db_run_mode`), a `lease_acquire` result with `venv_missing: true`, or `VENV_MISSING` from `instance_build` / `instance_serve`: release any such lease, build the venv, acquire again (follow the remedy).

## Warning handling

A module Odoo says must be loaded server-wide means the catalog row (or the brief's `SERVER_WIDE`) lacks it and the instance is not the deployment's. The `NEEDS_CONTEXT` `blocked_reason` carries the warning's remedy, both routes: a rebuild with `server_wide.include` for this task, or the catalog row fixed through `/odoo-ai-agents:odoo-setup refresh` or by the operator for every build (only a lease acquired AFTER that loads the module). A demo-data failure warning on a build that asked for `demo` `on` means demo records are missing: `status: error`, never `created`.

## Run-tests counters

Extra detail to the agent's Counters rule: JS suite classes to tag: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/tests.md` § JavaScript unit tests. With `JS_SCOPE=unscoped`, `JS_FAILED_TESTS` is unavailable - say so. An EMPTY count is reported as not measurable. `TEST_WARNING` / `TEST_SKIPPED` are always numeric.

## Step D detail

Extra detail to the agent's Step D. With a `WORKTREE_PATH` other than `none` (also the lease's `cwd`), compute the addons list yourself per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/references/worktree-addons-path.md` (its `BLOCKED` is yours to return) and pass it as `addons_path`; `lease_acquire` refuses a worktree `cwd` without one.

Ports: `instance_build` binds the lease's own port and refuses a port flag in `extra_args`; a plain `-i`/`-u`/`--load-language` run with `--stop-after-init` needs 0. A SECOND port only under prefork (`--workers>0`), never because a browser drives the instance: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Prefork (`--workers>0`) needs a second port.
