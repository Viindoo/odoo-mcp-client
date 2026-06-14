# Deploy Checklist Output Template

```
# Deploy Checklist — <env> <version>

## Scope
- Target version: <X.Y>
- Environment: <staging | prod>
- Modules: <comma-separated list or "all">
- Window: <user-supplied downtime window, or "TBD">
- Pre-flight audits: <odoo-deprecation-audit: run/not run> | <odoo-version-diff: run/not run>

## Verdict
<READY ✓ | NEEDS WORK ⚠ | NOT READY ✗>

<One-sentence summary of the verdict reason.>

## Checklist by domain

### 1. Pre-flight
- [✓/⚠/✗/N/A] Deprecation audit run — <link or "not run">
- [✓/⚠/✗/N/A] Version diff reviewed — <link or "not run">
- [✓/⚠/✗/N/A] All BREAKING issues resolved
- [✓/⚠/✗/N/A] Module existence verified: <module_a> ✓ / <module_b> ✗
- [✓/⚠/✗/N/A] Third-party modules compatibility confirmed

### 2. Backup
- [✓/⚠/✗/N/A] Full database backup taken and stored off-server
- [✓/⚠/✗/N/A] Backup restore tested on separate environment
- [✓/⚠/✗/N/A] Filestore / attachments backup included
- [✓/⚠/✗/N/A] Backup age ≤ 24h before deploy window

### 3. Data migration
- [✓/⚠/✗/N/A] Migration scripts present for all upgrading modules
- [✓/⚠/✗/N/A] Migration tested on prod-size data
- [✓/⚠/✗/N/A] Custom SQL constraints checked for data conflicts
- [✓/⚠/✗/N/A] Post-migration data integrity assertions pass
- [✓/⚠/✗/N/A] Record count spot-check before/after migration

### 4. Downtime
- [✓/⚠/✗/N/A] Downtime window scheduled and confirmed
- [✓/⚠/✗/N/A] User communication sent
- [✓/⚠/✗/N/A] Maintenance page ready
- [✓/⚠/✗/N/A] Estimated duration communicated
- [✓/⚠/✗/N/A] Escalation contact available during window

### 5. Deploy mechanics
- [✓/⚠/✗/N/A] CI pipeline green on deploy commit
- [✓/⚠/✗/N/A] Branch pinned to specific SHA
- [✓/⚠/✗/N/A] Assets compiled and verified
- [✓/⚠/✗/N/A] Deploy runbook rehearsed on staging
- [✓/⚠/✗/N/A] Feature flags configured if partial rollout

### 6. Smoke tests
- [✓/⚠/✗/N/A] Smoke test suite passes on staging
- [✓/⚠/✗/N/A] Critical flows verified: login / sale order / invoice
- [✓/⚠/✗/N/A] Custom module happy-path tests pass
- [✓/⚠/✗/N/A] External integrations spot-checked
- [✓/⚠/✗/N/A] No ERROR lines in server log during smoke test

### 7. Monitoring
- [✓/⚠/✗/N/A] Log streaming active
- [✓/⚠/✗/N/A] Metrics dashboard ready and reviewed
- [✓/⚠/✗/N/A] Alerting rules active for new modules
- [✓/⚠/✗/N/A] Scheduled actions verified post-migration
- [✓/⚠/✗/N/A] Email / SMTP connectivity checked

### 8. Rollback
- [✓/⚠/✗/N/A] Rollback path documented
- [✓/⚠/✗/N/A] Database restore tested and timed
- [✓/⚠/✗/N/A] Previous version tagged and accessible
- [✓/⚠/✗/N/A] Rollback decision criteria defined
- [✓/⚠/✗/N/A] Human escalation contacts listed

## Blockers
<List of ✗ items — each with one-line action required. Empty = no blockers.>

## Suggested next skills
- `odoo-deprecation-audit` — if Domain 1 pre-flight items are unchecked
- `odoo-version-diff` — if API diff for target version was not reviewed
- `/odoo-plan-upgrade` — if no full upgrade plan exists (Phase C command)
```
