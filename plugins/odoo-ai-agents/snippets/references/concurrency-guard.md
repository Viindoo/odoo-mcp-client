<!-- Reference material for skills/_shared/concurrency-guard.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Concurrency Guard - rationale and worked examples

## Mode A / Mode B - example skills (non-normative)

The main file's own text is explicit that these are examples of skills that already resolve to one
side of the Mode A/B decision rule, not the definition:

- Mode A (subagent batching): `odoo-debug`, `workflow-chaining`, `odoo-brl` (inner MCP
  parallelism), the YAML workflow fan-out ceiling (`workflows/_schema.md`) - none fans out more
  than one worker writing a shared
  module/worktree.
- Mode B (model-weighted budget): `odoo-coding` (one `odoo-coder` per node; two nodes in
  flight write disjoint file sets, coordinated via the module-coordination-ledger).
