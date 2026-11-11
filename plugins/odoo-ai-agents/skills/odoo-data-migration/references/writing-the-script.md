# Writing the module migration script (read by `odoo-coder` in `MODE: migration`)

Rules: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 5. Script rules and
code templates: `script-rules.md`; output and verification checklist: `output-templates.md`.

## What to cover

Per module: the migration type (field rename, type change, model split or merge, backfill of a new
stored or required field, data transform of XML records, parameters or tags, column drop with
preservation), the source and target fields or models, the stage (pre-migrate before the ORM
loads, post-migrate after), and every data note the run's nodes left in the worklog for that
module. One script per stage covers them all.

## The version, read and computed, never chosen

Read the module's `version` at the PR base and in the worktree. Unchanged -> the new version is
the smallest step of § 5 (`1.0.3` -> `1.0.4`, `0.3` -> `0.3.1`). Already bumped in this PR by the
smallest step -> reuse it and extend its existing `migrations/<series>.<version>/` folder instead
of adding a second one. Bumped any other way -> `BLOCKED` naming the module and both versions.
Write the descriptor's `version` in the same pass (the module's one bump), in the short form the
descriptor already uses (the filename per series: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`
row 6; read the path the module has, never a re-guessed filename).

## Path

`<WORKTREE_PATH>/<module>/migrations/<series>.<new short version>/pre-migrate.py` and/or
`post-migrate.py` (or `end-migrate.py`). The full series-prefixed folder runs on that series
only; a short-form folder runs on every series the module ships on and is written only when the
SRS asks for it (`migration_gate.py check --allow-short <module>`).

## Ground before writing (OSM first, parallel)

`model_inspect(method='fields')` on the source and target models; `entity_lookup(kind='field')`
on the moved field; `validate_relation` on each relational field; `lookup_core_api` on every
core helper the script calls. Confirm the real column names (stored fields only) and types.

OSM unreachable (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`): read the models on
disk (both descriptor filenames), read existing `migrations/` folders for prior patterns, mark an
unconfirmed column with `# VERIFY: confirm column name against live schema` and label the output
`grounded: local-source - not OSM-indexed`.

## Prove it

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/migration_gate.py check` (base tree = the PR's merge
base; `--help` states every rule): `MIGRATION_GATE=FAIL` is fixed before you return. Then a real
upgrade within the series through `Skill(odoo-instance)`: a database built from the PR base with
records the script moves, the module updated from `WORKTREE_PATH`, and the moved data read back
against the expected values. The verification checklist of `output-templates.md` goes in your
return. A `-u` that fails partway leaves the modules it had loaded at their new version without
their end-migrate, and a re-run skips them (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-failure-modes.md`,
Install / Upgrade / Migration): on a database you keep, reset their recorded version before
running again.
