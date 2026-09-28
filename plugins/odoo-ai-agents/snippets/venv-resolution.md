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

`instance_build` reads the interpreter from the lease, so a build or test through the odoo-local
tools needs no resolution at all. Resolve an interpreter only for a run outside those tools (a
migration script, a probe, a standalone unit-test run).

1. **The `venv_python` of the lease you hold or the `INSTANCE_HANDLE` you were given** - the venv
   `lease_acquire` reports for the series. Use it directly; it was verified at acquire time.

2. **The `python` field of the matching catalog row** - `catalog_read` with the series (and
   profile) per `snippets/instance-resolution.md`. Verify it with the `--version` probe above
   before use.

3. **`$ODOO_PYTHON`** - an interpreter path set in the environment. Verify it with the `--version`
   probe above before use; an unverified env var is a candidate, not yet a usable interpreter.

4. **STOP - build or ask, never guess.** If steps 1-3 produced no candidate, or the candidate FAILS
   the `--version` probe, do NOT fall through to system `python3` for the run. Either:
   - build (or record) a venv for the series with `45-venv.sh` (see below), then re-resolve; or
   - surface a single clarifying request naming the missing/broken interpreter rather than guessing
     at one.

   System `python3` is never a valid stopping point in this resolution order - its only legitimate
   use anywhere in this document is as the tool that RUNS a `--version` probe, never as a stand-in
   interpreter for the actual run.

## If no suitable venv exists yet

Build (or record an existing) venv for the series with the optional setup step:

```
<plugin>/scripts/setup-steps/45-venv.sh create-venv --series <X.Y> --profile <name> --tool uv|pip
```

When multiple profiles share the same series, pass `--profile` to select the right instance
and venv. The venv is created under `venvs/<series>-<profile>` and its path is recorded as
the `python` field on the matching catalog row; `catalog_read` returns it afterwards. The script
verifies all the profile's repos are present and that `odoo-bin --version` runs (not a bare
`import odoo`) before recording the `python` field.

The supported Python range of a series is read from the instance's own Odoo checkout
(`45-venv.sh suggest <series> [--profile <name>]` prints it and the recommended version);
`scripts/lib/odoo-python-matrix.json` is only the fallback when no checkout is readable.

## Note: the backend lint gate uses the instance interpreter

The backend code-quality gate (module set: `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`) runs INSIDE an
Odoo instance (`instance_build` op `test` with `test_tags` `/<lint module>,...`), so the lease supplies
the interpreter - you do not need a separate toolchain for linting.
