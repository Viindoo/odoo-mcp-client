---
name: odoo-plan-upgrade
argument-hint: "[version-range]"
description: >-
  Upgrade plan only, no code: risks, deprecations, effort
---
# /odoo-plan-upgrade

Thin dispatcher for the declarative odoo-plan-upgrade workflow.

**SSOT**: `plugins/odoo-ai-agents/workflows/odoo-plan-upgrade.workflow.yaml` holds the phase
definitions, model tiers, skills, fallback policy and resume logic, and the output directory
`<ISOLATE_DIR>/upgrade-plans/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit). Do not duplicate them
here.

## Dispatch

<!-- engages-run: routes via /odoo-intake Phase P so the workflow's on_complete chain auto-advances -->

Yield to the `odoo-intake` skill with the intent already resolved: run the `odoo-plan-upgrade`
workflow over this command's `$ARGUMENTS` (an optional version range, `<from>-to-<to>` or
`<from>-<to>`). Intake MUST engage Phase P (trigger 3: a single workflow node whose YAML declares
`on_complete`), serializing a 1-node RUN-DAG and running it (`plan-mode-schema.md` § Running the
plan). The runner dispatches `workflow-chaining`, which reads the workflow YAML, collects missing
inputs (source version, target version, scope, deadline), decides the workflow plan, and executes:

```
risk-overview -> deprecation-audit -> version-diff -> synthesis
```

Do NOT dispatch `workflow-chaining` directly: without a run above it, the `on_complete` design
handoff (`needs_design == true` chains to `odoo-solution-design`) degrades to a human suggestion.

**Execute handoff.** For the code-level upgrade once this plan is approved, invoke
`odoo-modules-upgrade` (skill) manually; it is not auto-dispatched and this plan writes no code.

## When to use

- A client asks for a **full upgrade plan** covering risk, deprecation, and API diff in one deliverable.
- You need an **executive-readable risk overview** and **dev-readable action items** in one artifact.

Do **not** use when only a deprecation check is needed (`odoo-deprecation-audit`) or only an API
diff is needed (`odoo-version-diff`).
