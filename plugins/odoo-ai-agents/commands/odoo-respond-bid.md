---
name: odoo-respond-bid
argument-hint: "[customer-label]"
description: >-
  Full bid package: discovery to proposal
---
# /odoo-respond-bid

<!-- execution SSOT: workflows/odoo-respond-bid.workflow.yaml -->

Thin dispatcher. Invoke the `workflow-chaining` skill with
`plugins/odoo-ai-agents/workflows/odoo-respond-bid.workflow.yaml`; the workflow YAML holds all phase
logic, skill invocations, output paths, fallback rules and hard rules (abstract labels, no external
writes, no email sending). `$ARGUMENTS` is an optional customer label (e.g.
`/odoo-respond-bid Customer-A`); the runner collects the remaining inputs before the workflow plan,
then runs the phases without stopping once the plan is approved.

Output lands in `<ISOLATE_DIR>/bids/<customer_label>-<YYYY-MM-DD>.md` (resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit).
