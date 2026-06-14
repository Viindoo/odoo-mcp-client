# Output Templates

## Script file template (post-migrate data backfill example)

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

## Verification checklist template

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
