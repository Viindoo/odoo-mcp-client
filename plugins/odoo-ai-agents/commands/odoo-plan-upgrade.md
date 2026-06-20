---
name: odoo-plan-upgrade
description: |
  Generate a comprehensive Odoo upgrade plan from source version to target version. Chains executive risk overview -> deprecation audit -> API/feature version diff -> synthesis with action ordering and effort estimate. Replaces the legacy odoo-upgrade-planner agent
---
# /odoo-plan-upgrade

Thin dispatcher for the declarative odoo-plan-upgrade workflow.

**SSOT**: `plugins/odoo-ai-agents/workflows/odoo-plan-upgrade.workflow.yaml`

All phase definitions, gates, model tiers, skills, output directory (`.odoo-ai/upgrade-plans/`),
fallback policy, and resume logic live in the workflow YAML. Do not duplicate them here.

## Dispatch

Yield to the `workflow-chaining` skill, passing this command's `$ARGUMENTS` (optional version
range such as `v16-to-v17` or `16.0-17.0`) as the initial input. The runner reads the
workflow YAML, collects missing inputs (source version, target version, scope, deadline),
emits the soft-plan-gate, and executes the four-phase pipeline:

```
risk-overview -> deprecation-audit -> version-diff -> synthesis
```

Output is written to `.odoo-ai/upgrade-plans/` on explicit user confirmation at the final gate.

**Design handoff (`on_complete`).** The workflow declares an `on_complete` that, when the plan
contains migration/refactor items with more than one viable approach (`needs_design == true`),
chains to `odoo-solution-design` so those items are designed before any code is written. For that
chain to fire automatically, this command must run under the run-driver - enter via
`/odoo-intake` Phase P (or a 1-node run) rather than a bare `workflow-chaining` dispatch. Without a
driver above it, `workflow-chaining` degrades the handoff to a visible human suggestion (it tells
you to run `/odoo-intake` or trigger `odoo-solution-design` manually) rather than auto-chaining.

## When to use

- A client asks for a **full upgrade plan** covering risk, deprecation, and API diff in one deliverable.
- You need **executive-readable risk overview** and **dev-readable action items** in the same artifact.
- Replacing a legacy `agents/odoo-upgrade-planner.md` invocation (removed; this command replaces it).

Do **not** use when:
- Only a deprecation check is needed: invoke `odoo-deprecation-audit` directly.
- Only an API diff is needed: invoke `odoo-version-diff` directly.

## See also

- `workflows/odoo-plan-upgrade.workflow.yaml` - phase contract (SSOT)
- `odoo-deploy-checklist` skill - use at actual deploy time
- `/odoo-respond-bid` - if this upgrade is part of a prospect proposal
