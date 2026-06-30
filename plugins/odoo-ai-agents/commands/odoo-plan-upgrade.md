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

<!-- engages-run-harness: routes via /odoo-intake Phase P so the workflow's on_complete chain auto-advances -->

Yield to the `odoo-intake` skill with the intent already resolved: run the `odoo-plan-upgrade`
workflow over this command's `$ARGUMENTS` (optional version range such as `v16-to-v17` or
`16.0-17.0`). Because that workflow declares an `on_complete` cross-workflow chain, intake MUST engage
Phase P (trigger 3: a single workflow node whose YAML declares `on_complete`) - serializing a 1-node
RUN-DAG and dispatching the `run-harness` above it. The run-harness then dispatches `workflow-chaining`,
which reads the workflow YAML, collects missing inputs (source version, target version, scope,
deadline), emits the soft-plan-gate, and executes the four-phase pipeline:

```
risk-overview -> deprecation-audit -> version-diff -> synthesis
```

Output is written to `.odoo-ai/upgrade-plans/` on explicit user confirmation at the final gate. Do NOT
dispatch `workflow-chaining` directly - without the run-harness above it, the `on_complete` design
handoff degrades to a human suggestion (see below).

**Design handoff (`on_complete`).** When the plan contains migration/refactor items with more than one
viable approach (`needs_design == true`), `on_complete` chains to `odoo-solution-design` so those items
are designed before any code is written. Routing through `/odoo-intake` Phase P keeps the run-harness
present to read the emitted Continuation Contract and auto-advance - the chain fires automatically. A
bare `workflow-chaining` dispatch (no run-harness) degrades this to a visible human suggestion, which is
why this command routes via intake.

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
