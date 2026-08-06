<!-- Reference material for snippets/module-coordination-ledger.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Module Coordination Ledger - rationale

## Why SHARE and not a bare cross-project `$ODOO_AI_HOME/coordination/`

The SHARE dir lives under `$ODOO_AI_HOME` (machine-global, outside any git working tree), so it
needs no gitignore entry and is never committed - it is live cross-run state, not source. Collapsing
it to a bare `$ODOO_AI_HOME/coordination/` (dropping the repo-key namespace) would regress
cross-repo isolation: two UNRELATED repos on the same host would then see each other's module
claims. The SHARE dir already gives exactly what this ledger needs: repo-scoped, worktree-converged
coordination - no more, no less.
