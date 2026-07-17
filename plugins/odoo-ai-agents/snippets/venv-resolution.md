# Odoo interpreter / venv resolution (which `python` runs odoo-bin, tests, migrations)

When you must actually RUN something against Odoo - `odoo-bin` (`scaffold`, `-i <module>`, `-u <module>`,
`--test-enable`, `--test-tags`, `--stop-after-init`, `--skip-auto-install` - since Odoo 17.0, to avoid noise from
auto installed modules when testing, reviewing, debugging, developing, maintaining, etc), a unit-test suite,
or a migration script - you need a Python interpreter whose virtualenv has that Odoo series' dependencies.

**Never fall through to the system `python3` for a RUN.** It usually lacks `psycopg2` / `lxml` / `babel`, so
the import crashes before Odoo even loads - and even when it happens to import cleanly, it is not the
series-pinned interpreter, so package versions can silently drift from what the target series expects.
System `python3` is permitted for exactly ONE purpose: a `--version`-style read probe used to VERIFY a
candidate interpreter (see "Usable interpreter" below). It is NOT a valid stopping point for anything that
runs `odoo-bin`, a test, a migration, or anything that touches a database.

## Usable interpreter - definition

An interpreter is "usable" only once it is VERIFIED, not merely located. Verification means running:

```
<candidate-python> <odoo-bin-path> --version
```

and observing it succeed (exit 0, a version string printed). A path found on disk or read from a
config field is a CANDIDATE, not yet usable - confirm it with this probe before trusting it for any
run, test, or migration.

## Resolution order (stop at the first step that yields a VERIFIED, usable interpreter)

1. The **`python` field of the matching `[[instance]]`** in the resolved `instances.toml`.
   Resolve the file per `snippets/instance-resolution.md` (machine-global
   `$ODOO_AI_HOME/instances.toml`), then read the interpreter:

   ```
   python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> <series> [profile]
   # emits INST_PYTHON / INST_PROFILE / INST_KEY among the other INST_* fields
   ```

   Verify the returned `INST_PYTHON` with the `--version` probe above before use.

2. **`$ODOO_PYTHON`** - an interpreter path set in the environment. Verify it with the `--version`
   probe above before use; an unverified env var is a candidate, not yet a usable interpreter.

3. **STOP - build or ask, never guess.** If steps 1-2 produced no candidate, or the candidate FAILS
   the `--version` probe, do NOT fall through to system `python3` for the run. Either:
   - build (or record) a venv for the series with `45-venv.sh` (see below), then re-resolve; or
   - surface a single clarifying request naming the missing/broken interpreter rather than guessing
     at one.

   System `python3` is never a valid stopping point in this resolution order - its only legitimate
   use anywhere in this document is as the tool that RUNS a `--version` probe, never as a stand-in
   interpreter for the actual run.

> If you acquired the instance through the allocator (concurrent mutation - see
> `snippets/instance-resolution.md` § Allocate), the same interpreter is already returned to you
> as `ALLOC_PYTHON` (already verified at acquire time), alongside `ALLOC_DB_PORT` / `db_port` (the
> instance's Postgres port, empty when the catalog/lease omits it) and `ALLOC_RUN_ID` (the run that
> owns the lease); use `ALLOC_PYTHON` directly instead of a second `instances_io.py read` lookup.

This is exactly the chain `scripts/setup-steps/50-instance-spinup.sh` uses to launch an
instance, so spinning up via that step already picks the right, verified interpreter for you.

## If no suitable venv exists yet

Build (or record an existing) venv for the series with the optional setup step:

```
<plugin>/scripts/setup-steps/45-venv.sh create-venv --series <X.Y> --profile <name> --tool uv|pip
```

When multiple profiles share the same series, pass `--profile` to select the right instance
and venv. The venv is created under `venvs/<series>-<profile>` and its path is recorded as
the `python` field on the matching `[[instance]]` in `instances.toml`. The script verifies
all the profile's repos are present and that `odoo-bin --version` runs (not a bare
`import odoo`) before recording the `python` field.

Read the resulting path with:

```
python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> <series> [profile]
# emits INST_PYTHON / INST_PROFILE / INST_KEY among the INST_* fields
```

The recommended Python per Odoo series lives in
`scripts/lib/odoo-python-matrix.json`.

## Note: the backend lint gate uses the instance interpreter

The backend code-quality gate (`/test_lint` + `/test_pylint` on v16+ Viindoo) runs INSIDE an
Odoo instance (`odoo-bin --test-enable --test-tags /test_lint,...`). Use the same interpreter
resolved above for the instance run - you do not need a separate toolchain for linting.

## Precedence over the `verify_python` context cache

`<SHARE_DIR>/context.md`'s `verify_python` field (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit; see also
`snippets/context-bootstrap.md`) is a
non-authoritative HINT for READ-ONLY flows only - it can go stale once the venv it names moves,
breaks, or is rebuilt after the field was cached. For ANY odoo-bin run, test, migration, or
DB-mutating operation, re-resolve the interpreter per the resolution order above and confirm it
with the `--version` probe before use; never trust the `verify_python` cache alone for a mutation.
This file is the authority for interpreter selection; `verify_python` is only ever a shortcut hint
for a read-only flow, never a substitute for the resolution order above.
