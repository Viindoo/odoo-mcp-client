# Migration Script Rules

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
