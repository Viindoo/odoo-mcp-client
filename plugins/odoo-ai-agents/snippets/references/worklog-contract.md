<!-- Reference material for snippets/worklog-contract.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Worklog Contract - rationale and worked examples

## Why the worklog exists (moved from the file's opening paragraph)

A multi-phase Odoo run spans several agents (architect -> test-author -> coder -> reviewer ->
debugger) and several rounds of parallel workers. Each makes decisions the *next* one needs:
approach chosen vs rejected, scope added or dropped, model tier picked, cross-module impacts found
and mitigated. The worklog is how that knowledge survives the handoff instead of being re-derived
by every downstream phase.

## Worked example - a single entry

```
- Round 2 | architect | DECIDED | extend sale.order via _inherit (not a new model) | WHY: the margin field belongs on the existing order | EVIDENCE: model_inspect(model='sale.order', method='summary', odoo_version='<version>')
```

The `<when>` prefix plus the per-writer filename already order writers, so a coarse label (`Phase
0`, `Round 2`) is fine when no clock is available - the ordering is best-effort, not a correctness
invariant.

## Why `<run-or-slug>` reuses the run id

So the worklog sits beside the work it explains: a run resuming into an existing worklog dir (the
common case - most runs are not the first writer) finds the same directory a sibling phase already
wrote to, without needing to be told the path explicitly.
