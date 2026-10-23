# odoo-instance - dispatch detail

The full wording of the dispatch steps `SKILL.md` § Dispatch summarises; `SKILL.md` names the section it needs.

### Active-wait on long builds (relay) and the deterministic completion signal

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

### Build facts the tools apply and the agent-side union

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

### Resolving modules and test_tags for an ad-hoc run-tests

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

### Relay the result - the instance-ops block and scope transparency

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

### Inline mode (exceptions (a)-(d) only) and the path-incremental loop

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
