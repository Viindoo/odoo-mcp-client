---
name: odoo-deploy-checklist
description: >
  Generate a pre-deployment safety checklist for an Odoo upgrade or new-module go-live —
  auto-fills 8 domains (pre-flight, backup, data migration, downtime, deploy mechanics,
  smoke tests, monitoring, rollback), marks each item READY / NEEDS WORK / NOT READY, and
  surfaces blockers before you push to prod. Use ANY time someone is about to deploy Odoo to
  staging or production. Pushy trigger: "deploy checklist", "go-live checklist", "before
  pushing to prod", "ready to deploy this Odoo upgrade?", "deployment readiness". Also fires
  on Vietnamese: "checklist trước khi lên prod", "sẵn sàng deploy chưa", "kiểm tra trước
  go-live". Trigger
  even when the user says only "deploy" in the context of Odoo. DO NOT trigger for: ongoing
  code work not about to be deployed; debugging unrelated to a release; questions about what
  changed between versions (route to odoo-version-diff); requests to audit deprecated API
  usage in code (route to odoo-deprecation-audit); executive risk overview (route to
  odoo-risk-overview)
---

## Persona

Engineer / DevOps — Odoo developer or sysadmin on a one-man-company team or small team
preparing a production or staging release. Audience may range from solo Odoo consultant
to a 3-5 person dev shop. Output is operational and actionable, not executive-level.

---

## Out of Scope

| Topic | Skill to use instead |
|---|---|
| Deprecated API code audit (pre-upgrade code scan) | `odoo-deprecation-audit` |
| API + feature diff between two Odoo versions | `odoo-version-diff` |
| Full upgrade orchestration plan (multi-tool) | `/odoo-plan-upgrade` (Phase C command) |
| Executive risk dashboard for stakeholders | `odoo-risk-overview` |
| Backend coding fixes found during checklist | `odoo-coding` bundle |

---

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-deploy-checklist -->

**Session bootstrap** (optional — call once if version not already pinned):
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` — Verify that each module in the deploy scope actually exists in the target Odoo version. Use in Round 2 to auto-fill module existence items.
- `module_inspect` — Get module manifest summary, model list, view count, and OWL component presence for deploy notes. Use to confirm module health and spot unexpected dependencies.
- `find_deprecated_usage` — Sanity scan for deprecated API usage in deploy scope. Supplements `odoo-deprecation-audit` when a full pre-flight audit was not run separately.
- `cli_help` — Ground the deploy/test CLI flags (`--test-enable`, `--test-tags`, `-u`, `-i`, `--stop-after-init`) for the TARGET version in Domain 5, instead of assuming one version's flags apply to another.

**The module-scan calls are independent — fire in parallel to minimize round trips.**
<!-- END MANUAL TOOLS — odoo-deploy-checklist -->

---

## Checklist domains

Eight standard domains — every deploy checklist covers all eight. Items are auto-filled
where context is available; remaining items are flagged for manual verification.

### Domain 1 — Pre-flight
_Goal: confirm that code-level readiness checks were done before touching production._

- [ ] Deprecation audit run for all modules in scope (`odoo-deprecation-audit`)
- [ ] Version diff reviewed for target version (`odoo-version-diff`)
- [ ] All BREAKING deprecation issues resolved (zero open BREAKING items)
- [ ] Module existence verified in target version (`check_module_exists`)
- [ ] Third-party modules confirmed compatible with target Odoo version

### Domain 2 — Backup
_Goal: confirm data is safe and recovery is tested — not assumed._

- [ ] Full database backup taken and stored off-server
- [ ] Backup restore tested on a separate environment (not just "backup exists")
- [ ] Filestore / attachments backup included
- [ ] Backup age confirmed (taken within 24h of deploy window)

### Domain 3 — Data migration
_Goal: confirm migration scripts are present, correct, and tested at scale._

- [ ] `pre_migrate.py` / `post_migrate.py` scripts present for all upgrading modules
- [ ] Migration scripts tested against a copy of the production database (not just demo)
- [ ] Tested on prod-size data (row count within 20% of production)
- [ ] Custom `_sql_constraints` checked for conflicts with existing data
- [ ] Data integrity assertions pass after migration (record counts, field spot-checks)

### Domain 4 — Downtime
_Goal: confirm business continuity is planned and communicated._

- [ ] Downtime window scheduled and confirmed with stakeholders
- [ ] User communication sent (email / Zalo / internal announcement)
- [ ] Maintenance page / "system under maintenance" message ready
- [ ] Estimated downtime duration calculated and communicated
- [ ] Escalation contact (DBA, vendor) available during window

### Domain 5 — Deploy mechanics
_Goal: confirm the deploy itself will be deterministic and repeatable._

- [ ] CI pipeline green on the commit to be deployed
- [ ] Deploy branch / tag pinned to a specific commit SHA (not a floating branch head)
- [ ] Assets compiled and committed (`odoo-bin --addons-path ... --stop-after-init` verified)
- [ ] CLI flags grounded for the TARGET version, not assumed — resolve via OSM `cli_help`
      (`set_active_version` first); install/upgrade/reinstall classified per
      ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md; tests invoked per
      ODOO-TESTING.md. Odoo CLI/test flags differ across versions — never reuse one
      version's command line for another.
- [ ] Deploy script / runbook documented and rehearsed on staging
- [ ] Feature flags in place if partial rollout is intended

### Domain 6 — Smoke tests
_Goal: confirm the system is functional immediately after deploy._

- [ ] Smoke test suite passes on staging after migration
- [ ] Code-quality CI gate reproduced locally (pre-push parity): `/test_lint` included in the
      `--test-tags` run AND `scripts/verify-backend.sh` (pylint-odoo) clean on changed Python —
      per `docs/reference/ODOO-TESTING.md`. Catches lint failures that otherwise only surface in
      CI; include the deployment's `/test_pylint` (or equivalent) tag when that module is present.
- [ ] Critical user flows verified manually: login, create sale order, confirm invoice
- [ ] Custom module smoke tests pass (at least happy path per module)
- [ ] External integrations (payment, shipping, API connectors) spot-checked
- [ ] No ERROR-level lines in Odoo server log during smoke test

### Domain 7 — Monitoring
_Goal: confirm observability is ready before production traffic hits the new code._

- [ ] Server logs / Odoo log streaming confirmed active
- [ ] Metrics dashboard (CPU, RAM, DB query time) ready and reviewed
- [ ] Alerting rules active for new modules (error rate, job queue depth)
- [ ] Scheduled actions (cron jobs) verified present and enabled post-migration
- [ ] Email / SMTP connectivity checked after migration

### Domain 8 — Rollback
_Goal: confirm you can undo the deploy quickly if something goes wrong._

- [ ] Rollback path documented (exact steps to restore previous version)
- [ ] Database restore tested and timed (know how long it takes)
- [ ] Previous code version tagged and accessible (git tag or artifact store)
- [ ] Rollback decision criteria defined (who decides, at what threshold)
- [ ] Human escalation contacts listed (DBA, Odoo partner, ops lead)

---

## Workflow

### Round 0 — Load context

Read `.odoo-ai/context.md` if present in the project root. Extract:
- `odoo_version` — default target version for MCP calls
- `modules` — default module scope
- Any previously run `odoo-deprecation-audit` or `odoo-version-diff` output references

If `.odoo-ai/context.md` is absent, proceed to Round 1 and ask the user directly.

### Round 1 — Confirm scope (ask user)

Confirm three parameters — ask for all three in a single message (do not multi-turn):

1. **Target Odoo version** — e.g. `17.0`, `16.0`
2. **Environment** — `staging` or `prod`
3. **Module list** — comma-separated list OR `"all"` (meaning every custom module in scope)

Also ask: "Have you already run `odoo-deprecation-audit` and `odoo-version-diff`?" (Y/N).
If yes, ask user to paste or link the output; use it to auto-fill Domain 1 items.

### Round 2 — Auto-fill checklist via MCP (parallel)

If OSM is reachable, fire these calls in parallel:

```
check_module_exists(name=<each_module>, odoo_version=<target>)     # one call per module
module_inspect(name=<each_module>, odoo_version='<version>')                                # one call per module
find_deprecated_usage(odoo_version='<version>')                                             # one call per version (kind= to filter)
```

Use results to fill:
- Domain 1: module existence check (✓ / ✗ per module from `check_module_exists`)
- Domain 3: flag modules with migration scripts missing (from `module_inspect` manifest scan)
- Domain 1 pre-flight: note any deprecated usage still present (from `find_deprecated_usage`)

All other domains (2, 4, 5, 6, 7, 8) require user-supplied or CI-supplied information —
mark as `⚠ Manual check` until user confirms.

### Round 3 — Rate every item

For each checklist item, assign one of four statuses:

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✓ | PASSED | Confirmed done — evidence available |
| ⚠ | MANUAL CHECK | Not auto-verified — user must confirm |
| ✗ | BLOCKER | Known gap — must resolve before deploy |
| N/A | NOT APPLICABLE | Item does not apply to this scope |

Default: items not auto-filled default to `⚠ Manual check`, not to ✓.
Err on the side of caution — a missed blocker costs more than an extra manual check.

### Round 4 — Produce output with verdict

Emit the full checklist in the output format below.

**Verdict logic:**
- `READY ✓` — zero ✗ items, all critical domains have at least one ✓
- `NEEDS WORK ⚠` — no ✗ items, but ≥3 `⚠ Manual check` items in Domains 2/4/8 (backup / downtime / rollback)
- `NOT READY ✗` — one or more ✗ items present

---

## Output format

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

---

## Standalone-first fallback

When OSM is unreachable or the user has not configured an API key:

1. Skip all MCP calls (`check_module_exists`, `module_inspect`, `find_deprecated_usage`).
2. Mark all OSM-dependent rows in Domain 1 as `⚠ Manual check` with note:
   `(OSM offline — verify module existence manually via: odoo-bin --addons-path ... -d <db> --update <module>)`
3. Continue filling all other domains (Domains 2-8) from user-supplied information.
4. Add a notice at the top of the output:
   `> Note: Module existence checks skipped (OSM unreachable). All OSM-dependent items marked ⚠ Manual check.`

The checklist remains fully usable — 7 of 8 domains require no OSM access.

---

## Examples

### Example 1 — Single module upgrade, staging

**User prompt:** "I'm about to deploy module `custom_loyalty_program` from Odoo 16 to 17 on staging. What do I need to check?"

**Skill action:**
- Round 1: Confirm scope — version 17.0, environment staging, module `custom_loyalty_program`.
- Round 2: Call `check_module_exists(name='loyalty', odoo_version='17.0')` to verify the base `loyalty` module (which `custom_loyalty_program` inherits) exists in v17; call `module_inspect` for manifest and migration script presence; call `find_deprecated_usage` for the module scope.
- Round 3-4: Auto-fill Domain 1 from MCP results; mark Domains 2-8 as `⚠ Manual check` (staging environment — backup and rollback still required for staging too).
- Output: checklist with verdict `NEEDS WORK ⚠` (backup and rollback items manual), blockers section empty or with module-specific gaps.

### Example 2 — Multi-module Q3 release, production go-live

**User prompt:** "Next week we're going live with our Q3 release to production — about 5 custom modules on Odoo 17. Full checklist."

**Skill action:**
- Round 1: Confirm the 5 module names, environment = prod, version 17.0, downtime window (ask explicitly).
- Round 2: Parallel `check_module_exists` × 5, `module_inspect` × 5, one `find_deprecated_usage` across all 5 modules.
- Round 3-4: Domains 2 (backup), 4 (downtime), 8 (rollback) are the highest-risk for prod — any `⚠ Manual check` in these domains triggers `NEEDS WORK ⚠` verdict at minimum. Blockers section lists any module not found in v17 or any deprecated usage not yet resolved.
- Output: full 8-domain checklist, verdict `READY ✓` only if all backup/rollback items are confirmed by user.

---

## Notes

### `.odoo-ai/context.md` integration

If the project has a `.odoo-ai/context.md` file (populated by `odoo-onboarding`), read it in
Round 0 to pre-fill:
- `odoo_version` — skip the version question in Round 1
- `modules` — offer the module list as default (user can override)
- Any links to previous `odoo-deprecation-audit` or `odoo-version-diff` runs — auto-fill Domain 1 items

Without `.odoo-ai/context.md`, all three Round 1 questions are mandatory.

### Cross-links

- **Pre-flight code audit** (before generating this checklist): run `odoo-deprecation-audit` first.
  Its output directly fills Domain 1 items.
- **Full upgrade orchestration**: `/odoo-plan-upgrade` (Phase C command) chains
  `odoo-deprecation-audit` → `odoo-version-diff` → `odoo-deploy-checklist` into a single
  end-to-end upgrade plan. Use the command when the user needs a complete plan, not just
  a deploy gate.
- **Risk overview for stakeholders**: `odoo-risk-overview` produces an executive-language
  risk dashboard — route to it when the audience is a manager or client, not the engineer.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
