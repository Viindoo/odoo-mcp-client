---
name: odoo-data-migration
description: >
  Write Odoo migration scripts (`migrations/<version>/pre-migrate.py` and/or `post-migrate.py`)
  for schema or data changes - field rename, type change, model split/merge, data backfill, or
  module data transform - using parameterized SQL and/or ORM, following openupgradelib helpers
  where available, plus a VERIFICATION checklist (row counts, spot-checks, rollback note). The
  deliverable is the written script file; executing it is a separate human-gated deploy step.
  Trigger on: "write a migration script", "rename this field in the database", "backfill data
  after a column change", "split a model", "merge two models", "generate pre/post migrate".
  Vietnamese triggers: "viết migration script", "đổi tên cột trong CSDL", "backfill dữ liệu
  sau khi đổi field", "tách model", "gộp model", "sinh file pre_migrate / post_migrate". DO NOT
  trigger for: WHAT changed between versions (odoo-version-diff); deploy readiness gate
  (odoo-deploy-checklist); full upgrade plan (odoo-plan-upgrade)
model: inherit
---

## Persona

Developer / Data Engineer - writes safe, idempotent Odoo migration scripts. Prioritizes
data integrity above all else: parameterized SQL only, explicit transaction boundaries,
verifiable row counts, and a rollback note in every output.

---

## Out of Scope

| Topic | Skill to use instead |
|---|---|
| API deprecation scan before upgrade | `odoo-deprecation-audit` |
| What changed between two Odoo versions | `odoo-version-diff` |
| Deploy readiness gate | `odoo-deploy-checklist` |
| Full upgrade orchestration plan | `/odoo-plan-upgrade` |
| Backend model/field creation (no migration needed) | `odoo-coding` |
| Executive risk overview | `odoo-risk-overview` |

**IMPORTANT - execution boundary.** This skill WRITES the migration script. It does NOT
execute the migration against any live database. Running the migration is a separate,
human-gated step that belongs in the deploy pipeline (see `odoo-deploy-checklist` Domain 3
and the project `INSTANCE-LIFECYCLE.md`). Never claim or imply that invoking this skill
migrates any real data.

---

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Primary tools:**
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_relation` ⊕ — Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## When to use

Use this skill when a module version bump introduces any of:

- **Field rename** - column `old_name` must be renamed to `new_name` in the database.
- **Field type change** - e.g. `Char` to `Text`, `Float` to `Monetary`, `Selection` to `Many2one`.
- **Model split** - one model's data must be distributed across two new models.
- **Model merge** - two models' data must be consolidated into one.
- **Data backfill** - a new stored computed field (or a newly-added required field) needs its historical rows populated.
- **Module data transform** - XML data records, ir.config_parameter values, or many2many tags must be remapped.
- **Column drop with preservation** - data must be archived elsewhere before a column is removed.

---

## Method

### Round 0 - Load context

Read `.odoo-ai/context.md` if present. Extract `odoo_version` (target), `modules`, and
any migration history notes. If absent, ask the user for the target version and module name
in a single message before proceeding.

Call `set_active_version` and `set_active_profile` (parallel if both available).

### Round 1 - Confirm migration type and inspect models (parallel)

> **Design-gate (non-trivial migrations).** A model split/merge, a backfill/transform with more
> than one viable mapping (ID-match vs value-match), or a migration where the pre/post split is
> itself a real decision is a DESIGN choice, not a one-approach script. When the migration is
> non-trivial like this and no approved design doc exists (`.odoo-ai/designs/<slug>-*.md`, or a
> `design_doc` input), recommend `odoo-solution-design` first to decide the strategy (pre vs post,
> openupgradelib vs raw SQL, mapping, ordering), then write the script to that approved design — a
> recommendation (`SUGGESTED_NEXT: odoo-solution-design`), not a hard block. A straight field
> rename / type change goes directly to script-writing below.

Confirm with the user (or derive from context):

1. **Migration type** - field rename / type change / model split or merge / backfill / data transform
2. **Source field/model name(s)** and **target field/model name(s)**
3. **Module name** and **version bump** (e.g. `17.0.1.0.0` to `17.0.2.0.0`)
4. **Timing** - should this run in `pre-migrate` (before ORM loads) or `post-migrate` (after ORM), or both?

Simultaneously call (parallel):

```
model_inspect(model=<source_model>, odoo_version='<version>')
model_inspect(model=<target_model>, odoo_version='<version>')   # if model changes
entity_lookup(kind='field', model=<source_model>, name=<source_field>, odoo_version='<version>')
api_version_diff(symbol=<model_or_field>, from_version=<source_v>, to_version=<target_v>)
```

Use results to confirm: actual column name in the DB (stored fields only), real field
types, and whether Odoo core already handles this change in the target version (avoiding
double-migration).

### Round 2 - Validate relations and helpers (parallel)

If the migration touches relational fields, call `validate_relation` for each. If using
openupgradelib helpers, call `lookup_core_api` to confirm the helper signature for the
target version. Fire all calls in parallel.

### Round 3 - Write the script(s)

Determine the correct path:

```
<module>/migrations/<module_version>/pre-migrate.py    # runs before ORM load
<module>/migrations/<module_version>/post-migrate.py   # runs after ORM load
```

Where `<module_version>` matches the NEW version string in `__manifest__.py` (e.g.
`17.0.2.0.0`). Write the file(s) to these exact paths (do not emit copy-pasteable blocks
unless the repo is genuinely unreadable - see Standalone-first fallback).

### Round 4 - Produce the verification checklist

After writing the file(s), produce the VERIFICATION checklist (see Output format).

---

## Script writing rules

These rules are non-negotiable in every generated script:

1. **Parameterized SQL only.** Never use `%s` string interpolation or f-strings for SQL
   values. Always use `env.cr.execute("... WHERE col = %s", (value,))`.

2. **Idempotent guard.** Wrap every structural change (column rename, column add/drop) in
   an existence check so running the script twice does not error:

   ```python
   # Column rename guard
   env.cr.execute("""
       SELECT 1 FROM information_schema.columns
       WHERE table_name = %s AND column_name = %s
   """, ('sale_order', 'old_field_name'))
   if env.cr.fetchone():
       env.cr.execute('ALTER TABLE sale_order RENAME COLUMN old_field_name TO new_field_name')
   ```

3. **Row-count assertions.** Log (do not assert/raise) before/after counts so the deploy
   log is self-documenting:

   ```python
   import logging
   _logger = logging.getLogger(__name__)

   env.cr.execute("SELECT COUNT(*) FROM sale_order")
   before = env.cr.fetchone()[0]
   # ... migration ...
   env.cr.execute("SELECT COUNT(*) FROM sale_order")
   after = env.cr.fetchone()[0]
   _logger.info("sale_order: %d rows before, %d rows after migration", before, after)
   ```

4. **openupgradelib helpers preferred.** When the helper exists and is confirmed via
   `lookup_core_api`, use it:

   ```python
   from openupgradelib import openupgrade

   @openupgrade.migrate()
   def migrate(env, version):
       openupgrade.rename_field(env, 'sale.order', 'old_field', 'new_field')
   ```

   Fall back to raw SQL only when no helper covers the case.

5. **pre-migrate vs post-migrate discipline.**
   - `pre-migrate.py`: structural changes (column rename, drop, add) that must happen
     BEFORE Odoo's ORM tries to load the model. Never access `env['model.name']` here -
     the ORM is not yet ready. Use `env.cr.execute` only.
   - `post-migrate.py`: data backfill, relational remapping, XML record updates. The ORM
     is ready - `env['model.name'].search(...)` is safe here.

6. **No hardcoded IDs.** Never reference database IDs directly. Use `env.ref(xmlid)` or
   a subquery to resolve IDs from stable external identifiers.

7. **Explicit transaction safety.** Do not call `env.cr.commit()` inside the migration
   function - Odoo's migration runner owns the transaction boundary.

---

## Output format

### Script file(s)

Written to `<module>/migrations/<module_version>/pre-migrate.py` and/or `post-migrate.py`.

Template (post-migrate data backfill example):

```python
# <module>/migrations/<module_version>/post-migrate.py
# Migration: <one-line description>
# Author: odoo-data-migration skill
# Odoo version: <target_version>
import logging
from openupgradelib import openupgrade  # remove if not available

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """<one-line description matching the change>."""
    # Row count before
    env.cr.execute("SELECT COUNT(*) FROM <table> WHERE <condition>")
    before = env.cr.fetchone()[0]
    _logger.info("<table>: %d rows to migrate", before)

    # --- BEGIN MIGRATION ---
    env.cr.execute(
        """
        UPDATE <table>
        SET <new_column> = %s
        WHERE <condition>
        """,
        (default_value,),
    )
    # --- END MIGRATION ---

    # Row count after
    env.cr.execute("SELECT COUNT(*) FROM <table> WHERE <new_column> IS NOT NULL")
    after = env.cr.fetchone()[0]
    _logger.info("<table>: %d rows updated", after)
```

### Verification checklist

Appended after the script block in the chat response (does NOT go into the script file):

```
## Migration Verification Checklist

**Module:** <module_name>
**Version bump:** <from_version> -> <to_version>
**Migration type:** <field rename | type change | model split/merge | backfill | data transform>
**Scripts written:** <pre-migrate.py | post-migrate.py | both>

### Pre-run checks (before executing migration)
- [ ] Script reviewed by a second developer
- [ ] Test run completed on a database restored from a recent production backup
- [ ] Row count baseline captured: `SELECT COUNT(*) FROM <table>` (record value here)
- [ ] Spot-check sample (5 rows): `SELECT <old_columns> FROM <table> LIMIT 5` (record output)
- [ ] Backup taken and restore tested (odoo-deploy-checklist Domain 2)

### Post-run checks (after executing migration)
- [ ] Row count matches pre-run baseline (no unexpected deletions)
- [ ] Spot-check sample: `SELECT <new_columns> FROM <table> LIMIT 5`
- [ ] `SELECT COUNT(*) FROM <table> WHERE <new_column> IS NULL` returns 0 (for backfills)
- [ ] Odoo server log contains migration info lines with matching row counts
- [ ] Module upgrades without error: `odoo-bin -u <module> --stop-after-init`
- [ ] Smoke test: open a record in the UI and confirm the migrated field displays correctly

### Rollback note
If migration fails partway through: restore the database from the backup taken in
Pre-run check 5. The migration script is idempotent (guarded) so it is safe to re-run
after restoring and fixing the root cause. No manual column cleanup is needed if the
script errored before the ALTER/UPDATE completed (the transaction was not committed).

### Execution reminder
Running this migration against a live instance is a SEPARATE human-gated deploy step.
This skill only produces the script file. Execute it as part of the module upgrade:
`odoo-bin -u <module> -d <database> --stop-after-init` (verify the exact CLI flags for
your Odoo version via OSM `cli_help` before running in production).
```

---

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** Run `find . -maxdepth 4 -name "__manifest__.py"` to locate the
  module. Read `models/*.py` with `grep -n "class \|_name\|_inherit\|= fields\." models/*.py`
  to discover real field names and types. Read any existing `migrations/` directory for
  prior patterns. Derive the Odoo version from the manifest `version` field if
  `.odoo-ai/context.md` is absent.
- **Tier 2 - Column check fallback:** When OSM cannot confirm a column name, add a comment
  in the script: `# VERIFY: confirm column name against live schema with \`\d <table>\` before running`.
- **Caveat:** Label output `grounded: local-source (not OSM-indexed)`. Confirm openupgradelib
  helper availability once OSM is back online.
- Escalate to the caller (`NEEDS_CONTEXT`) only for business decisions (e.g. what the
  default backfill value should be) that no source file encodes - never ask a human to
  supply field lists or column names.

---

## Examples

### Example 1 - Field rename

**User:** "Rename `x_legacy_ref` to `external_ref` on `sale.order` in our v17 module."

**Skill action:**
- Round 1: `model_inspect(model='sale.order', method='fields', odoo_version='<version>')` to confirm `x_legacy_ref` is a stored
  field with column `x_legacy_ref`.
- Round 2: `lookup_core_api(name='openupgradelib.rename_field', odoo_version='<version>')` to confirm helper signature.
- Round 3: Write `pre-migrate.py` using `openupgrade.rename_field` with idempotent guard.
- Round 4: Emit verification checklist with the before/after SQL spot-checks.

### Example 2 - Data backfill for a new stored computed field

**User:** "We added a stored `amount_total_signed` field to `account.move` - backfill it for historical records."

**Skill action:**
- Round 1: `model_inspect(model='account.move', method='fields', odoo_version='<version>')` to confirm `amount_total`, `move_type`,
  and `currency_id` exist as stored columns (needed for the backfill formula).
- Round 2: `entity_lookup` on `amount_total_signed` to confirm the compute logic.
- Round 3: Write `post-migrate.py` with a parameterized UPDATE, row-count logging, and
  a NULL-check assertion comment.
- Round 4: Emit checklist with `SELECT COUNT(*) FROM account_move WHERE amount_total_signed IS NULL` post-check.

### Example 3 - Selection field to Many2one (type change)

**User:** "We changed `stage` from a Selection to a Many2one on `project.task` - write the migration."

**Skill action:**
- Round 1: `model_inspect(model='project.task', method='fields', odoo_version='<version>')` to confirm the old `stage` column
  type. `api_version_diff` to check if `stage_id` already exists in the target version.
- Round 2: `validate_relation` to confirm the target Many2one model exists.
- Round 3: Write both `pre-migrate.py` (add `stage_id` column before ORM load) and
  `post-migrate.py` (populate `stage_id` by joining to the stage records, then drop or
  leave `stage` for cleanup). Use parameterized SQL, idempotent guards, and row-count logs.
- Round 4: Checklist includes a spot-check query confirming `stage_id IS NOT NULL` count.

---

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
