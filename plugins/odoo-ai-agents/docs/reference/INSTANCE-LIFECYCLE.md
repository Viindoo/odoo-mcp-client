# Odoo Instance Lifecycle - install vs upgrade vs reinstall (method, not hardcoded facts)

> **Read this as a decision *framework*, not a version fact-sheet.** Odoo CLI flags,
> subcommands and module semantics differ across supported Odoo versions. The version-specific
> details below are **illustrative snapshots** - before you act on any of them for a given
> target version, **confirm against OSM**: `set_active_version(<target>)` then
> `cli_help(command, flag, odoo_version='<version>')` for CLI facts, and `api_version_diff` / `find_deprecated_usage`
> / `module_inspect` for API/era facts. OSM + the running instance are the ground truth.
>
> Consumed by: `odoo-deploy-checklist`, `odoo-qa-suite`, `run-harness`
> (when building/refreshing an instance), the upgrade command chain, and the `setup` scripts.
>
> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for build/drop/init/update/test operations on a local instance. Persistent
> operation logs live under `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`. This
> reference doc covers the underlying semantics those operations rely on - including, since the
> lifecycle does not end at "server answers", the teardown half owned by
> `INSTANCE-LIFECYCLE-TEARDOWN.md`.

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
| Renamed module, changed a model `_name`, data corruption, demo mismatch | **REINSTALL**: drop DB + create fresh + `-i` | a leased (allocator-managed) DB is dropped by releasing its lease, never by bare name - see the ownership guard in `INSTANCE-ALLOCATION-GUARDS.md` §6.3 |
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

## Parts - what each file owns

The decision tree, the `-i`/`-u` semantics and the traps above stay here. The two long halves
live in part files; cite the PART that owns the fact you need.

| File | Owns |
|------|------|
| `INSTANCE-LIFECYCLE-BUILD-CONTRACT.md` | the numbered build/update/test checklist (items 1-15), including item 14's deterministic readiness/completion contract and item 15's resource limits |
| `INSTANCE-LIFECYCLE-TEARDOWN.md` | the teardown half: the T0 DONE-gate, T1 ownership, the stop-group-then-drop mechanism, `server_pid` on the handle, and the four-layer enforcement chain |
