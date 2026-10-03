---
name: odoo-deploy-checklist
argument-hint: "[module/release scope]"
description: >-
  Go-live readiness checklist for an Odoo upgrade or new module
---

## Role

Engineer / DevOps - Odoo developer or sysadmin on a one-man-company team or small team
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

<!-- BEGIN MANUAL TOOLS - odoo-deploy-checklist -->

**Session bootstrap** (optional - call once if version not already pinned):
- `set_active_version(odoo_version='<version>')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify that each module in the deploy scope actually exists in the target Odoo version. Use in Round 2 to auto-fill module existence items.
- `module_inspect` - Get module manifest summary, model list, view count, and OWL component presence for deploy notes. Use to confirm module health and spot unexpected dependencies.
- `find_deprecated_usage` - Sanity scan for deprecated API usage in deploy scope. Supplements `odoo-deprecation-audit` when a full pre-flight audit was not run separately.
- `cli_help` - Ground the deploy/test CLI flags (`--test-enable`, `--test-tags`, `-u`, `-i`, `--stop-after-init`) for the TARGET version in Domain 5, instead of assuming one version's flags apply to another.

**The module-scan calls are independent - fire in parallel to minimize round trips.**
<!-- END MANUAL TOOLS - odoo-deploy-checklist -->

---

## Checklist domains

Eight standard domains - every deploy checklist covers all eight. Items are auto-filled where context is available; remaining items flagged for manual verification.

Full item list and output template: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deploy-checklist/references/checklist-template.md`

Domain purposes (for autofill logic):
- **1 Pre-flight** - code-level readiness checks before touching production.
- **2 Backup** - data safe and recovery tested (not just assumed).
- **3 Data migration** - scripts present, correct, and tested at scale.
- **4 Downtime** - business continuity planned and communicated.
- **5 Deploy mechanics** - deploy is deterministic and repeatable. CLI flags grounded for TARGET version via OSM `cli_help` (`set_active_version` first); install/upgrade/reinstall classified per `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md` § Decision tree; tests per `ODOO-TESTING.md`. Never reuse one version's command line for another.
- **6 Smoke tests** - system functional after deploy. Code-quality CI gate reproduced: the lint-class modules (${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md) included in the `--test-tags` run - per `docs/reference/ODOO-TESTING.md`.
- **7 Monitoring** - observability ready before production traffic.
- **8 Rollback** - can undo the deploy quickly.

---

## Workflow

### Round 0 - Resolve project facts

**Round 0 - resolve project facts.** Resolve series, profile, and module scope per
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` and pre-fill Domain 1 with them.
Previous audit output is a request or brief input. Then proceed to Round 1 for whatever is left.

### Round 1 - Confirm scope (single message)

Ask all three in one message: (1) Target Odoo version, (2) Environment (staging/prod), (3) Module list. Also ask: "Have you already run `odoo-deprecation-audit` and `odoo-version-diff`?" - if yes, ask user to paste/link output to auto-fill Domain 1.

### Round 2 - Auto-fill checklist via MCP (parallel)

If OSM reachable, fire simultaneously:
```
check_module_exists(name=<each_module>, odoo_version=<target>)   # one call per module
module_inspect(name=<each_module>, method='summary', odoo_version='<version>')      # one call per module
find_deprecated_usage(odoo_version='<version>')                   # one call per version
```

Use results to fill: Domain 1 module existence (✓/✗ per module), Domain 3 migration script presence, Domain 1 deprecated usage. All other domains (2, 4, 5, 6, 7, 8) require user-supplied information - mark `⚠ Manual check` until confirmed.

### Round 3 - Rate every item

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✓ | PASSED | Confirmed done - evidence available |
| ⚠ | MANUAL CHECK | Not auto-verified - user must confirm |
| ✗ | BLOCKER | Known gap - must resolve before deploy |
| N/A | NOT APPLICABLE | Item does not apply to this scope |

Default to `⚠ Manual check`, not ✓. Err on the side of caution.

### Round 4 - Produce output with verdict

**Verdict logic:**
- `READY ✓` - zero ✗ items, all critical domains have at least one ✓
- `NEEDS WORK ⚠` - no ✗ items, but ≥3 `⚠ Manual check` in Domains 2/4/8
- `NOT READY ✗` - one or more ✗ items present

Output template: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deploy-checklist/references/checklist-template.md`

---

## Standalone-first fallback

When OSM is unreachable:
1. Skip all MCP calls.
2. Mark all OSM-dependent Domain 1 rows `⚠ Manual check` with note: `(OSM offline - verify module existence manually via: [ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true ; odoo-bin --addons-path ... -d <db> --update <module> --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296} - memory-cap policy: ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md)`
3. Fill all other domains from user-supplied information.
4. Add notice: `> Note: Module existence checks skipped (OSM unreachable). All OSM-dependent items marked ⚠ Manual check.`

The checklist remains fully usable - 7 of 8 domains require no OSM access.

---

## Notes

- **Project facts:** Round 0 pre-fills the series and module scope per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`. Whatever no rung resolves stays a mandatory Round 1 question.
- **Pre-flight code audit:** Run `odoo-deprecation-audit` first - its output directly fills Domain 1.
- **Full upgrade orchestration:** `/odoo-plan-upgrade` chains `odoo-deprecation-audit` → `odoo-version-diff` → `odoo-deploy-checklist`. Use when a complete plan is needed, not just a deploy gate.
- **Risk overview for stakeholders:** Route to `odoo-risk-overview` when the audience is a manager or client.

Examples: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deploy-checklist/references/examples.md`

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
