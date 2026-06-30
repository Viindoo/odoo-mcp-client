---
name: odoo-position-feature
argument-hint: "[feature] [competitor/segment]"
description: |
  Generate positioning copy for a specific Odoo feature or capability. Chains feature-check
  (does it exist?) -> addon-diff (which edition?) -> competitive-brief (vs competitor, optional)
  -> positioning copy block. Use for marketing assets, sales decks, or RFP positioning
---
# /odoo-position-feature

Thin dispatcher - execution is fully encoded in the declarative workflow SSOT:

```
plugins/odoo-ai-agents/workflows/odoo-position-feature.workflow.yaml
```

## How this command works

This command invokes the `workflow-chaining` skill with the `odoo-position-feature` workflow.
The runner reads the YAML, emits a soft-plan-gate, collects required inputs, and executes
four gated phases in sequence:

| Phase | Skill | Purpose |
|---|---|---|
| feature-check | `odoo-feature-check` | Verify the feature exists; identify editions and key modules |
| addon-diff | `odoo-addon-diff` | Edition capability table (CE / EE / Dist.) |
| competitive-brief | `odoo-competitive-brief` | Odoo vs competitor matrix (skipped if no competitor named) |
| positioning-copy | inline | Produce copy block adapted to audience + channel |

## Inputs collected at Phase 0

- **feature_name** - the Odoo feature or capability to position (required)
- **target_audience** - exec / sales / developer / marketer
- **competitor_name** - competitor to benchmark against (optional; answer "none" to skip Phase 3)
- **output_channel** - slide / blog / email / proposal

Output artifacts land under `.odoo-ai/positioning/`.

## To run

Invoke this command; `workflow-chaining` guides you through all phases with explicit
gates between each. To resume an interrupted run, re-invoke with the same feature slug -
the runner reads `.odoo-ai/positioning/<slug>-state.json` automatically.

## See also

- `plugins/odoo-ai-agents/workflows/odoo-position-feature.workflow.yaml` - SSOT for phases, gates, model tiers
- `/odoo-content-draft` - full marketing pieces (blog, whitepaper, case study)
- `/odoo-respond-bid` - RFP positioning with pricing and timelines
- `/odoo-objection-handling` - reactive objection responses
