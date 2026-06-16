# Odoo interpreter / venv resolution (which `python` runs odoo-bin, tests, migrations)

When you must actually RUN something against Odoo - `odoo-bin` (`scaffold`, `-i <module>`,
`--test-enable`, `--stop-after-init`), a unit-test suite, or a migration script - you need a
Python interpreter whose virtualenv has that Odoo series' dependencies. Do NOT assume the
system `python3`: it usually lacks `psycopg2` / `lxml` / `babel`, so the import crashes before
Odoo even loads.

## Resolution order (stop at the first that yields a usable interpreter)

1. The **`python` field of the matching `[[instance]]`** in the resolved `instances.toml`.
   Resolve the file per `snippets/instance-resolution.md` (machine-global
   `~/.odoo-ai/instances.toml`), then read the interpreter:

   ```
   python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> <series>
   # emits INST_PYTHON=<path-to-venv-python> among the other INST_* fields
   ```

2. **`$ODOO_PYTHON`** - an interpreter path set in the environment.

3. system **`python3`** - last resort only; it likely lacks Odoo deps, so a clean run is not
   guaranteed.

This is exactly the chain `scripts/setup-steps/50-instance-spinup.sh` uses to launch an
instance, so spinning up via that step already picks the right interpreter for you.

## If no suitable venv exists yet

Build (or record an existing) venv for the series with the optional setup step:

```
<plugin>/scripts/setup-steps/45-venv.sh create-venv --series <X.Y> --tool uv|pip
```

It installs the series' requirements and records the interpreter back onto the instance's
`python` field. The recommended Python per Odoo series lives in
`scripts/lib/odoo-python-matrix.json`.

## Note: the lint gate resolves its own toolchain

`scripts/verify-backend.sh` (the pylint-odoo gate) manages its OWN isolated tools venv per
series from the matrix - you do not pick an interpreter for it. The chain above is for RUNNING
Odoo (odoo-bin / tests / migrations), not for linting.
