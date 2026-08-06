<!-- Reference material for snippets/resource-teardown-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Resource Teardown Contract - rationale and worked examples

## T2 close-call detail

Closing the current/last page is safe by design - a subsequent navigate re-creates a page. This
has not been smoke-verified across every headed variant; if a family ever wedges on last-page
close, close all other pages and hand the last one to a named catcher per T4.

## Why the RAM guardrail is the `W` pool cap and nothing else

No machinery enforces a browser RAM budget directly: `scripts/lib/resource_limits.sh` /
`ODOO_AI_LIMIT_MEMORY_HARD` cap the odoo-bin process's VIRTUAL memory only, and the allocator
counts Postgres/ports, not Chromium - neither caps aggregate browser RAM. The `W` pool cap in
concurrency-guard.md is therefore the only real guardrail; raise it only after the operator has
verified host RAM headroom for that many concurrent Chromium processes.
