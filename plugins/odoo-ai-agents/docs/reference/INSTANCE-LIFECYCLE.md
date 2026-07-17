# Odoo Instance Lifecycle - install vs upgrade vs reinstall (method, not hardcoded facts)

> **Read this as a decision *framework*, not a version fact-sheet.** Odoo CLI flags,
> subcommands and module semantics differ across supported Odoo versions. The version-specific
> details below are **illustrative snapshots** - before you act on any of them for a given
> target version, **confirm against OSM**: `set_active_version(<target>)` then
> `cli_help(command, flag, odoo_version='<version>')` for CLI facts, and `api_version_diff` / `find_deprecated_usage`
> / `module_inspect` for API/era facts. OSM + the running instance are the ground truth.
>
> Consumed by: `odoo-deploy-checklist`, `odoo-qa-suite`, `run-harness`'s between-wave integration
> (when building/refreshing an instance), the upgrade command chain, and the `setup` scripts.
>
> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for build/drop/init/update/test operations on a local instance. Persistent
> operation logs live under `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`. This
> reference doc covers the underlying semantics those operations rely on - including, since the
> lifecycle does not end at "server answers", the teardown half covered in the new section below.

## Decision tree - what did you change?

| Change | Action | Why / trap |
|--------|--------|------------|
| First time loading a module into a DB | `-i` / `--init <module>` | registers in `ir_module_module`; loads all data incl. `noupdate`, runs demo data |
| Python only (method, compute, onchange, business logic) | **restart server** (no `-i`/`-u` needed) | code is re-imported on boot; `--dev=reload` for autoreload. #1 agent confusion - editing a method does NOT need `-u` |
| New/changed **field** (column add/drop/type) | `-u` / `--update <module>` | runs ORM schema sync |
| Changed `__manifest__.py` `depends` / `data` | `-u <module>` | a brand-new dependency is auto-installed by `-u`; or `-i` the new dep explicitly |
| XML / view / data record changed | `-u <module>` | **TRAP:** records in `<data noupdate="1">` (or a noupdate file) are written once at `-i` and **never** rewritten by `-u`. Editing them has no effect - flip noupdate, migrate, or delete the `ir_model_data` row |
| `store=True` computed field added / formula changed | `-u <module>` | `-u` should recompute the stored column; if recompute is skipped, force it (shell `env … recompute`, or null the column + `-u`). Verify the column, don't assume |
| Removed a model / field / changed an XML id | `-u <module>` + watch for orphans | may leave stale columns / `ir_model_data` orphans; hard cleanup → reinstall |
| Renamed module, changed a model `_name`, data corruption, demo mismatch | **REINSTALL**: drop DB + create fresh + `-i` | a leased (allocator-managed) DB is dropped by releasing its lease, never by bare name - see the ownership guard in `INSTANCE-ALLOCATION.md` §6.3 |
| Cross-version bump (e.g. 16 → 17) | OpenUpgrade / the upgrade path - **NOT a plain `-u`** | a version bump is a migration job, not a module update |

## `-i` vs `-u` semantics (confirm exact flags via `cli_help` for the target version)

- `-i <module>` = install: load manifest, create tables, load **all** data files (incl.
  noupdate), run demo data, run `tagged at_install` tests if `--test-enable`.
- `-u <module>` = update: re-run schema sync, reload **non-noupdate** data, run scripts in
  `migrations/`, recompute stored fields. `-u all` updates every installed module (slow).
- Neither is needed for pure-Python logic changes - a **server restart** picks those up.
- `-i` on an already-installed module is a no-op; to truly reset, uninstall or drop the DB. To
  RE-RUN tests on a DB that already has the module installed, use `-u <module> --test-enable` (see
  `ODOO-TESTING.md` § Core test invocation).

## Traps to always check

1. **noupdate data never reloads on `-u`** (see table).
2. **Asset cache:** changing JS/CSS/SCSS regenerates the bundle on `-u`, but the browser may
   serve a cached `/web/assets/...`. Use `--dev=assets` in dev or hard-refresh; in prod the
   bundle hash changes on `-u`. **Where assets are declared differs by era** - confirm for
   the target version (manifest `assets` dict vs an XML `<template>`); do not assume.
3. **`-u` without `-d <DB>`** does nothing useful - always target a database.
4. **Demo data** loads only at `-i`; `--without-demo=all` at first install is not reversible by `-u`.
5. **API-compat gate:** a module using a removed decorator/API (e.g. `@api.multi`) only runs on
   older versions - confirm the removal version via `api_version_diff` / `find_deprecated_usage`
   for the target before assuming it installs.

## Instance lifecycle contract (checklist for any build/update/test)

1. **Resolve the target version explicitly** - confirm it is indexed (`list_available_versions`)
   and pin it (`set_active_version`). When multiple profiles exist for the same series,
   also resolve the `profile` field from the matching `[[instance]]` in `instances.toml`
   (via `instances_io.py read <toml> <series> [profile]`, emitting `INST_PROFILE`/`INST_KEY`).
2. **Query the CLI for that version - never assume.** `cli_help(command, flag, odoo_version='<version>')` for every
   non-trivial subcommand/flag (entry script, DB management, module management, port flags).
   Do not hardcode one version's CLI for another.
   **Venv probe gate:** verify the venv by running `odoo-bin --version` (not `import odoo`);
   a bare `import odoo` fails on source-only checkouts and is unreliable on Odoo 19 namespace
   packages. The `python` field is only recorded on `[[instance]]` after this gate passes.
3. **Classify the change** (decision tree above) → choose `-i` / `-u` / restart-only /
   drop+recreate, and state the classification before acting.
4. **Generalize the environment** - read addons-path, port, DB name, data dir from the
   project/config, not from any one machine's setup. Artifacts must be portable.
5. **noupdate / asset awareness** - if the change touches noupdate data or JS/CSS assets,
   flag that `-u` may not reload it and point at the era-correct asset location (verify).
6. **`store=True` recompute** - ensure recompute happened; verify the column.
7. **Tests** - see `ODOO-TESTING.md`; pick the test invocation supported by the target version.
8. **Version bump ≠ `-u`** - migrations go through the upgrade path.
9. **Read-only verification** - confirm `-d` target and addons-path; never run Odoo just to
   "test a guess" - query OSM/source instead.
10. **`en_US` always active on any first `-i` (create / init / fresh test-DB).** Odoo's base/source
    language must be loaded in every DB this contract builds, regardless of whether translation is
    in scope for the run - union `en_US` into any `--load-language` / `i18n loadlang` call and never
    issue one that omits it. Owned by the `odoo-instance` skill / `odoo-instance-ops` agent (SSOT:
    `skills/odoo-instance/SKILL.md`); `odoo-i18n` enforces the same invariant independently for the
    raw `odoo-bin` calls it issues outside this dispatch (recipe KT3:
    `skills/odoo-i18n/references/i18n-recipe.md`).
11. **Viindoo `to_base` unioned into `--load` when the active profile carries it.** Server-wide
    modules are resolved from a DATA-DRIVEN profile probe, never hardcoded, and `to_base` is
    appended to the era default (never replacing it). Owned by `odoo-instance-ops` (SSOT:
    `agents/odoo-instance-ops.md` § Server-wide modules (`--load`) - Viindoo `to_base` (HARD RULE));
    the `odoo-instance` skill threads the resolved `PROFILE` through its dispatch brief.
12. **Lint modules (`test_lint`/`test_pylint`) installed, not just tagged, on any test-run build.**
    A `--test-enable` build must UNION the present lint module(s) into the `-i`/`-u` install list
    from the same probe that appends their tag to `--test-tags`. Owned by `odoo-instance-ops`
    (SSOT: `agents/odoo-instance-ops.md` § Lint modules - installed for test-run builds (HARD
    RULE)); test-invocation detail in `ODOO-TESTING.md` § Install the lint modules (not just tag
    them).
13. **`persist` + `run_id` on any build that must stay running.** A build that must remain a live,
    listening process (never `--stop-after-init`) declares `persist: exclusive-running` (an isolated,
    owner-stamped instance - unique db + an allocator-issued pooled port, never the declared/`8069`
    port) or `persist: shared-running` (the shared render target, now ALSO owner-stamped via
    `run_id` so a foreign session cannot bare-drop it) - never a bare port/db reuse with no owner.
    Owned by `skills/odoo-instance/SKILL.md` (the `persist:`/`run_id:` dispatch fields) and
    `agents/odoo-instance-ops.md` (operation 1, create-instance). Full contract:
    `INSTANCE-ALLOCATION.md` §5 + §6.3. Whichever mode you declare here also decides who tears it
    down and when - see the Teardown section below, not a restatement of it.
14. **Readiness/completion detection is DETERMINISTIC - never a log tail.** Under the
    `--log-level=warn` build baseline, EVERY completion line Odoo would otherwise log
    (`Modules loaded.`, `HTTP service (werkzeug) running on ...`, `Registry loaded ...`) is
    INFO-level and gets SUPPRESSED - a clean, successful run produces an EMPTY log. A completion
    check that waits to SEE a line in that log therefore stalls to its timeout even on success;
    this was the historical hang. Two DIFFERENT signals replace it, one per job shape:
    - **Install/update job** (`-i`/`-u` with `--stop-after-init` - the ephemeral build AND the
      build leg of `persist: exclusive-running`): the job ALWAYS exits (that is what
      `--stop-after-init` is for), so completion is **PROCESS EXIT**, never a log read. The build
      additionally forces `--log-handler=<ns>.modules.loading:INFO` onto the invocation so the
      `"Modules loaded."` completion line survives the `warn` baseline regardless (a per-logger
      `setLevel` wins over the inherited level) - `<ns>` is version-resolved: `openerp` for series
      < 10 (v8-v9), `odoo` for v10+ (the namespace renamed at the v9->v10 boundary). **Exit code 0
      alone is NOT proof of install** - three source-confirmed silent-skip paths stay exit 0: a
      misspelled/nonexistent module name (logged, ignored), an unresolved dependency, and a
      demo-data failure downgraded to a warning. SUCCESS therefore requires exit 0 AND the
      `"Modules loaded."` marker present AND none of these failure markers present: `CRITICAL`,
      `Traceback (most recent call last)`, `invalid module names, ignored`, `Some modules are not
      loaded`, `Unmet dependenc(y|ies)`, `cannot be installed`. Any of those -> FAILURE, reported
      with the log path preserved for diagnosis, never a hang.
    - **Listening instance** (`persist: exclusive-running`/`shared-running`, no `--stop-after-init`
      - the process serves after load instead of exiting): READY is a BOUNDED-timeout HTTP poll of
      the port - primary `GET /web/database/selector` (auth=none, no DB required, reliable
      v8-v19), fallback `/web/login` for a series/build where the selector route is unavailable.
      On timeout -> BLOCKED with the last probe error; it never waits forever and never falls back
      to a log tail.
    Owned by `scripts/setup-steps/55-instance-ops.sh` (install/update job) and
    `scripts/setup-steps/50-instance-spinup.sh` (listening readiness); the runtime contract for an
    executing agent is `agents/odoo-instance-ops.md`'s "Active-wait on long builds" section, relayed
    at dispatch level by `skills/odoo-instance/SKILL.md`.

## Teardown - the lifecycle does not end at "server answers"

The decision tree and checklist above cover the BUILD half of the lifecycle (what to run to get a
correct, up-to-date instance). This section covers the other half: an instance you provisioned is
not finished with until it is torn down. **The full normative rule lives in one place -
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` - this section only summarizes the
instance-specific mechanics and points at where each piece is owned; it does not restate the
contract's ownership matrix or DONE-gate wording.**

- **T0 DONE-gate.** An agent may not claim `status: DONE` while an instance it self-provisioned
  this dispatch is still leased or listening. A finished report with a live leftover server is not
  done - release first, then claim DONE. Full wording: `resource-teardown-contract.md` T0.
- **T1 ownership (who releases).** Self-provisioned `ephemeral`/`exclusive-running` -> the agent
  that acquired it releases before its own terminal status. A forwarded `INSTANCE_HANDLE` -> the
  receiving agent NEVER releases it; only the provisioning orchestrator does, at run end.
  `persist: shared-running` -> no single consumer ever releases it; only allocator GC reclaims a
  dead pid or an expired TTL. Full matrix (incl. the run-level-owner and path-incremental rows):
  `resource-teardown-contract.md` T1.
- **Mechanism: stop the process group, THEN drop the DB.** `release` is teardown-complete for a
  listening instance, not just a DB drop: if the lease carries a live `server_pid` on this host,
  the allocator stops that PID's process GROUP first (SIGTERM, a bounded wait, then a group
  SIGKILL - reaping the HTTP master, workers, cron, the longpolling/gevent process, and any
  `--dev=reload` watchdog) and only THEN drops the DB for `drop_on_release` leases. Stopping the
  group first frees the DB connections that would otherwise block `DROP DATABASE`. The same order
  applies inside `gc` when it reclaims a TTL-expired-but-still-alive orphan. Full API rows
  (`bind`, `release`, `gc`): `INSTANCE-ALLOCATION.md` §6.
- **`server_pid` on the handle.** The instance handle a build hands back (and forwards downstream)
  now carries an optional `server_pid` - the server's process-group id under `setsid`, bound onto
  the lease via `allocator.py bind <token> --pid <pid>` at spin-up (`50-instance-spinup.sh`); null
  for a `--stop-after-init` build, which self-terminates. Field definition:
  `snippets/instance-handle-contract.md`.
- **Enforcement + crash-backstop chain.** Four layers, each catching what the one before it
  missed:
  1. **Prose release** - the agent releases its own lease as the normal, graceful path (this doc's
     checklists + `resource-teardown-contract.md` T1/T3).
  2. **`SubagentStop` hard block** (`hooks/enforce-teardown.sh`) - the one hard-blocking gate in
     the system: it fires only on a live, non-shared lease that the SUBAGENT ITSELF provisioned
     (correlated from its own `acquire`/`bind`/`heartbeat` `--run-id`) at a `status: DONE` claim,
     and refuses the DONE until it is released or explicitly handed off. Browser findings are
     ADVISORY only (never block) on both `SubagentStop` and `Stop` - the asymmetry is intentional,
     see `resource-teardown-contract.md` "Why browsers and instances are enforced differently".
  3. **`SessionEnd` crash backstop** (`hooks/session-end-gc.sh`) - runs `allocator.py gc`
     unconditionally when the session ends, silent and bounded, so a killed/OOM'd session (no DONE
     claim, no hook 2 trigger) still gets its orphaned server group-stopped and its ephemeral DB
     dropped.
  4. **Next-acquire GC / TTL** - `gc` also runs opportunistically inside every `acquire`, and the
     allocator's TTL (default `DEFAULT_TTL_S = 7200s` in `scripts/lib/allocator.py`, the SSOT for
     that number) reaps anything the first three layers still missed (e.g. a different-host lease
     whose pid liveness is unknowable). Long-lived holders call `heartbeat <token>` between phases
     so a healthy run is never reaped mid-flight.
  Wiring for both hooks (`SubagentStop`/`Stop`/`SessionEnd` registration) lives in `hooks/hooks.json`;
  do not restate their internals here - this bullet is a map, not a copy.
