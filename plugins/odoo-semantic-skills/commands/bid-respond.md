---
name: odoo-bid-respond
description: |
  Generate a complete Odoo bid response package from raw prospect input. Chains discovery synthesis → gap analysis → capability proof → objection pre-empt → proposal draft. Invoke when responding to an RFP, proposal request, or post-discovery synthesis needs
---
# /odoo-bid-respond

<!-- execution SSOT: workflows/bid-respond.workflow.yaml -->

This command is a thin dispatcher. All phase logic, gates, skill invocations, output
paths, and fallback rules are defined in the declarative workflow SSOT:

```
plugins/odoo-semantic-skills/workflows/bid-respond.workflow.yaml
```

## How to run

The `workflow-runner` skill auto-discovers `bid-respond.workflow.yaml` and executes it
when this command fires. Dispatch happens via natural-language routing - the runner reads
the workflow YAML and drives each phase in sequence.

To invoke: type `/odoo-bid-respond` (optionally followed by a customer label, e.g.
`/odoo-bid-respond Customer-A`). The runner collects remaining inputs interactively at
Phase 0.

## What the workflow produces

Six gated phases (Pipeline pattern):

| Phase | Skill dispatched | Gate |
|-------|-----------------|------|
| 0 - Parse + context check | inline | implicit |
| 1 - Discovery synthesis | `odoo-discovery-summarize` | yes / edit / cancel |
| 2 - Gap analysis | `odoo-gap-analysis` | yes / edit / cancel |
| 3 - Capability proof | `odoo-capability-proof` | yes / iterate / cancel |
| 4 - Objection pre-empt | `odoo-objection-handler` | yes / edit / cancel |
| 5 - Assemble proposal | inline | yes - save / iterate / cancel |
| 6 - Output | inline (write file) | - |

Output lands in `.odoo-ai/bids/<customer_label>-<YYYY-MM-DD>.md`.

For full phase specifications, gate behavior, standalone fallback rules, hard rules
(abstract labels, no external writes before Gate 5, no email sending), and examples -
read `workflows/bid-respond.workflow.yaml` directly.
