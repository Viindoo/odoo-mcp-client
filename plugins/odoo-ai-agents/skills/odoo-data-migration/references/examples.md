# Migration Examples

## Example 1 - Field rename

**User:** "Rename `x_legacy_ref` to `external_ref` on `sale.order` in our v17 module."

**Skill action:**
- Round 1: `model_inspect(model='sale.order', method='fields', odoo_version='<version>')` to confirm `x_legacy_ref` is a stored
  field with column `x_legacy_ref`.
- Round 2: `lookup_core_api(name='openupgradelib.rename_field', odoo_version='<version>')` to confirm helper signature.
- Round 3: Write `pre-migrate.py` using `openupgrade.rename_field` with idempotent guard.
- Round 4: Emit verification checklist with the before/after SQL spot-checks.

## Example 2 - Data backfill for a new stored computed field

**User:** "We added a stored `amount_total_signed` field to `account.move` - backfill it for historical records."

**Skill action:**
- Round 1: `model_inspect(model='account.move', method='fields', odoo_version='<version>')` to confirm `amount_total`, `move_type`,
  and `currency_id` exist as stored columns (needed for the backfill formula).
- Round 2: `entity_lookup` on `amount_total_signed` to confirm the compute logic.
- Round 3: Write `post-migrate.py` with a parameterized UPDATE, row-count logging, and
  a NULL-check assertion comment.
- Round 4: Emit checklist with `SELECT COUNT(*) FROM account_move WHERE amount_total_signed IS NULL` post-check.

## Example 3 - Selection field to Many2one (type change)

**User:** "We changed `stage` from a Selection to a Many2one on `project.task` - write the migration."

**Skill action:**
- Round 1: `model_inspect(model='project.task', method='fields', odoo_version='<version>')` to confirm the old `stage` column
  type. `api_version_diff` to check if `stage_id` already exists in the target version.
- Round 2: `validate_relation` to confirm the target Many2one model exists.
- Round 3: Write both `pre-migrate.py` (add `stage_id` column before ORM load) and
  `post-migrate.py` (populate `stage_id` by joining to the stage records, then drop or
  leave `stage` for cleanup). Use parameterized SQL, idempotent guards, and row-count logs.
- Round 4: Checklist includes a spot-check query confirming `stage_id IS NOT NULL` count.
