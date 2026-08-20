# Odoo instance lifecycle - build/update/test contract

Part of `docs/reference/INSTANCE-LIFECYCLE.md` (index: the change-classification decision tree,
`-i` vs `-u` semantics, and the traps). This file owns the numbered checklist every build, update
or test run must satisfy. Teardown is a separate half: `INSTANCE-LIFECYCLE-TEARDOWN.md`.

## Instance lifecycle contract (checklist for any build/update/test)

1. **Resolve the target version explicitly** - confirm it is indexed (`list_available_versions`)
   and pin it (`set_active_version`). When multiple profiles exist for the same series,
   also resolve the `profile` field from the matching `[[instance]]` in `instances.toml`
   (via `instances_io.py read <toml> <series> [profile]`, emitting `INST_PROFILE`/`INST_KEY`).
2. **Query the CLI for that version - never assume.** `cli_help(command, flag, odoo_version='<version>')` for every
   non-trivial subcommand/flag (entry script, DB management, module management, port flags).
   Do not hardcode one version's CLI for another.
   **Venv probe gate:** verify the venv by RUNNING Odoo (`odoo-bin --version`), never by a bare
   `import odoo`. The probe shapes and the checkout layouts on which a bare import misreports a
   healthy venv are owned by `commands/odoo-setup.md` § AI-4 - read them there, never restate
   them here. Step 45 records `python` on `[[instance]]` only after this gate passes, alongside
   `odoo_root` (the checkout root that makes `import odoo` resolve) and the Postgres client
   surface `db_run_mode` (+ `db_container` in docker mode).
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
    listening process (never `--stop-after-init`) declares a listening `persist:` value - an
    isolated, owner-stamped instance on an allocator-issued pooled port (never the declared/`8069`
    port), or the shared render target, now ALSO owner-stamped via `run_id` so a foreign session
    cannot bare-drop it - never a bare port/db reuse with no owner. The values themselves, and the
    parked state a suspended instance sits in, are spelled out in ONE place and are NOT restated
    here: `INSTANCE-ALLOCATION-MODES.md` §5 (+ `INSTANCE-ALLOCATION-GUARDS.md` §6.3 for the
    ownership guard). Owned by
    `skills/odoo-instance/SKILL.md` (the `persist:`/`run_id:` dispatch fields) and
    `agents/odoo-instance-ops.md` (operation 1, create-instance). Whichever value you declare here
    also decides who tears it down and when - see `INSTANCE-LIFECYCLE-TEARDOWN.md`, not a
    restatement of it.
14. **Readiness/completion detection is DETERMINISTIC - never a log tail.** Two DIFFERENT
    signals apply, one per job shape:
    - **Install/update job** (`-i`/`-u` with `--stop-after-init`, NO `--test-enable` - the
      throwaway build AND the build leg of an isolated listening instance): the job ALWAYS exits
      (that is what `--stop-after-init` is for), so completion is **PROCESS EXIT**, never a log
      read. The build
      additionally forces `--log-handler=<ns>.modules.loading:INFO` onto the invocation as a
      FLOOR, so the `"Modules loaded."` completion line survives ANY caller-supplied level - `<ns>`
      is the core package name for the target series, and the row that owns that flip is
      `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` § Core package directory; read it
      there rather than from a copy here. **Exit code 0
      alone is NOT proof of install** - three source-confirmed silent-skip paths stay exit 0: a
      misspelled/nonexistent module name (logged, ignored), an unresolved dependency, and a
      demo-data failure downgraded to a warning. SUCCESS therefore requires exit 0 AND the
      `"Modules loaded."` marker present AND none of these failure markers present: `CRITICAL`,
      `Traceback (most recent call last)`, `invalid module names, ignored`, `Some modules are not
      loaded`, `Unmet dependenc(y|ies)`, `cannot be installed`. Any of those -> FAILURE, reported
      with the log path preserved for diagnosis, never a hang. A traceback rules here because
      under `-i`/`-u` no test runs, so nothing but the build itself can raise.
    - **Test job** (`--test-enable`, also `--stop-after-init`): shares the install job's shape -
      the process exits, and that exit is completion - but NOT its verdict rules, and the two must
      never be merged. `"Modules loaded."` is only PROGRESS here: Odoo logs it BEFORE the
      post-install suite starts, so it can never certify a tested build. SUCCESS is the run's OWN
      `TEST_RESULT=` line, which the harness appends once odoo-bin exits. A lone `Traceback (most
      recent call last)` is NOT a failure marker here either: on a test run tracebacks come from
      logged exceptions the run recovers from, routing errors, and every HttpCase 500 a test
      asserts on, as well as from failing tests - so per-test `FAIL:`/`ERROR:` markers and the
      per-module aggregate are the failure evidence for the PYTHON suite, the Hoot/QUnit markers
      are it for the browser suite (a JS failure writes no Python traceback at all), and all of
      them are MID-RUN, never completion. The
      only markers terminal BEFORE the run publishes its own verdict are the hard aborts that
      prove odoo-bin died and never will: `CRITICAL`, `Failed to load registry`, `psycopg2.`,
      `ParseError`, plus the silent-skip markers above.
    - **Listening instance** (any listening `persist:` value - `INSTANCE-ALLOCATION-MODES.md` §5 - with
      no `--stop-after-init`, so the process serves after load instead of exiting): READY is a
      BOUNDED-timeout HTTP poll of the port - primary `GET /web/database/selector` (auth=none, no
      DB required, reliable v8-v19), fallback `/web/login` for a series/build where the selector
      route is unavailable. On timeout -> BLOCKED with the last probe error; it never waits forever
      and never falls back to a log tail. A RESUMED instance takes this same path and nothing
      extra: the spin-up's launch line carries no `-i` and no `-u`, so re-launching against the
      database a park preserved re-installs nothing and READY means what it always meant.
    Owned by `scripts/setup-steps/55-instance-ops.sh` (install/update job) and
    `scripts/setup-steps/50-instance-spinup.sh` (listening readiness); the runtime contract for an
    executing agent is `agents/odoo-instance-ops.md`'s "Active-wait on long builds" section, relayed
    at dispatch level by `skills/odoo-instance/SKILL.md`.
15. **Memory/time resource limits apply on every launch - a version-general cap, not a version-branch.**
    Every install/update/test build (`--stop-after-init`, driven by `55-instance-ops.sh`) wraps the
    odoo-bin invocation in a shell `ulimit -Sv` PLUS a `--limit-memory-hard` flag, both derived from
    ONE resolved value. Each mechanism is load-bearing on exactly the series range the other does
    not cover, and the enforcement boundary that decides which is which is spelled out in ONE place
    and NOT restated here: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md` § The v12.0
    enforcement boundary. Both fire unconditionally on every build - each is a no-op wherever the
    other already covers the range - so no prose version-branch is needed at this site. The resolved default is `floor(MemTotal * 0.5)` floored at
    4 GiB, overridable via `ODOO_AI_LIMIT_MEMORY_HARD` (set to `""`/`0` for the deliberate uncapped
    escape hatch). A long-running listener (any listening `persist:` value -
    `INSTANCE-ALLOCATION-MODES.md` §5 - through the generated conf in `50-instance-spinup.sh`)
    additionally carries `limit_memory_soft` and `limit_time_real` conf keys - both are structurally
    unreachable on the `--stop-after-init` build path (they live in
    `ThreadedServer.process_limit()`, past the `if stop: return rc` short-circuit that
    `--stop-after-init` always takes), so the build path correctly omits them rather than passing a
    flag that looks like protection but is silently never evaluated. A PARKED lease is the third
    state and carries no resource limit at all: park stopped the owner's process group, so there is
    no listening process left for any cap to bind - parking a lease holds DISK (database, filestore,
    port reservation), never memory (`INSTANCE-ALLOCATION-MODES.md` §5). The caps re-arm the moment `resume`
    re-launches through that same generated conf from the same resolved value, so a resumed instance
    runs under the identical cap, never a weaker one. Full policy - the
    v12.0 enforcement boundary, the exact resolution formula, the uncapped escape hatch, and the
    `RLIMIT_AS`-is-virtual-not-physical caveat - lives in ONE place, not restated here:
    `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md` (SSOT). Owned by
    `scripts/setup-steps/55-instance-ops.sh` (build path) and `scripts/setup-steps/50-instance-spinup.sh`
    (listener conf); the resolution logic itself lives only in `scripts/lib/resource_limits.sh`.
