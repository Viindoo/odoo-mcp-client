---
name: odoo-position-feature
argument-hint: "[feature] [competitor/segment]"
description: >-
  Positioning copy for one Odoo feature
---
# /odoo-position-feature

Thin dispatcher. Invoke the `workflow-chaining` skill with the `odoo-position-feature` workflow:

```
plugins/odoo-ai-agents/workflows/odoo-position-feature.workflow.yaml
```

The workflow YAML (SSOT) holds the phases (feature-check, addon-diff, competitive-brief,
positioning-copy), model tiers, and resume logic.

## Inputs collected before the workflow plan

- **feature_name** - the Odoo feature or capability to position (required)
- **target_audience** - exec / sales / developer / marketer
- **competitor_name** - competitor to benchmark against (optional; answer "none" to skip the competitive-brief phase)
- **output_channel** - slide / blog / email / proposal

Output artifacts land under `<ISOLATE_DIR>/positioning/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once
per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute
path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit). To resume an
interrupted run, re-invoke with the same feature slug; the runner reads
`<ISOLATE_DIR>/positioning/<slug>-state.json`.
