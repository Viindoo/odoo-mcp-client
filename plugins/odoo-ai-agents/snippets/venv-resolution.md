# Odoo interpreter / venv resolution (which `python` runs odoo-bin, tests, migrations)

When you must actually RUN something against Odoo - `odoo-bin` (`scaffold`, `-i <module>`, `-u <module>`,
`--test-enable`, `--test-tags`, `--stop-after-init`, `--skip-auto-install` - since Odoo 17.0, to avoid noise from
auto installed modules when testing, reviewing, debugging, developing, maintaining, etc), a unit-test suite,
or a migration script - you need a Python interpreter whose virtualenv has that Odoo series' dependencies.
Do NOT assume the system `python3`: it usually lacks `psycopg2` / `lxml` / `babel`, so the import crashes before
Odoo even loads.

## Resolution order (stop at the first that yields a usable interpreter)

1. The **`python` field of the matching `[[instance]]`** in the resolved `instances.toml`.
   Resolve the file per `snippets/instance-resolution.md` (machine-global
   `~/.odoo-ai/instances.toml`), then read the interpreter:

   ```
   python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> <series> [profile]
   # emits INST_PYTHON / INST_PROFILE / INST_KEY among the other INST_* fields
   ```

2. **`$ODOO_PYTHON`** - an interpreter path set in the environment.

3. system **`python3`** - last resort only; it likely lacks Odoo deps, so a clean run is not
   guaranteed.

> If you acquired the instance through the allocator (concurrent mutation - see
> `snippets/instance-resolution.md` § Allocate), the same interpreter is already returned to you
> as `ALLOC_PYTHON`; use it directly instead of a second `instances_io.py read` lookup.

This is exactly the chain `scripts/setup-steps/50-instance-spinup.sh` uses to launch an
instance, so spinning up via that step already picks the right interpreter for you.

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
