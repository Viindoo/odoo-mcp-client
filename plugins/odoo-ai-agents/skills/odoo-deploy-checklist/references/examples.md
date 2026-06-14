# Deploy Checklist Examples

## Example 1 — Single module upgrade, staging

**User prompt:** "I'm about to deploy module `custom_loyalty_program` from Odoo 16 to 17 on staging. What do I need to check?"

**Skill action:**
- Round 1: Confirm scope — version 17.0, environment staging, module `custom_loyalty_program`.
- Round 2: Call `check_module_exists(name='loyalty', odoo_version='17.0')` to verify the base `loyalty` module (which `custom_loyalty_program` inherits) exists in v17; call `module_inspect` for manifest and migration script presence; call `find_deprecated_usage` for the module scope.
- Round 3-4: Auto-fill Domain 1 from MCP results; mark Domains 2-8 as `⚠ Manual check` (staging environment — backup and rollback still required for staging too).
- Output: checklist with verdict `NEEDS WORK ⚠` (backup and rollback items manual), blockers section empty or with module-specific gaps.

## Example 2 — Multi-module Q3 release, production go-live

**User prompt:** "Next week we're going live with our Q3 release to production — about 5 custom modules on Odoo 17. Full checklist."

**Skill action:**
- Round 1: Confirm the 5 module names, environment = prod, version 17.0, downtime window (ask explicitly).
- Round 2: Parallel `check_module_exists` × 5, `module_inspect` × 5, one `find_deprecated_usage` across all 5 modules.
- Round 3-4: Domains 2 (backup), 4 (downtime), 8 (rollback) are the highest-risk for prod — any `⚠ Manual check` in these domains triggers `NEEDS WORK ⚠` verdict at minimum. Blockers section lists any module not found in v17 or any deprecated usage not yet resolved.
- Output: full 8-domain checklist, verdict `READY ✓` only if all backup/rollback items are confirmed by user.
