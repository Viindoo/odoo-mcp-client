<!-- Reference material for snippets/module-coordination-ledger.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Module Coordination Ledger - rationale

## Why SHARE and not ISOLATE, and not a bare cross-project `$ODOO_AI_HOME/coordination/`

`--git-common-dir` always points back to the ONE shared common git dir, so keying the SHARE path
off `sha256(realpath(git rev-parse --git-common-dir))` resolves to the SAME path for every linked
worktree and every concurrent invocation of THIS repo. A per-worktree ISOLATE dir is private - two
concurrent runs in two worktrees would each write their own copy and never see each other, exactly
the cross-run blindness this ledger removes.

The SHARE dir lives under `$ODOO_AI_HOME` (machine-global, outside any git working tree), so it
needs no gitignore entry and is never committed - it is live cross-run state, not source. Collapsing
it to a bare `$ODOO_AI_HOME/coordination/` (dropping the repo-key namespace) would regress
cross-repo isolation: two UNRELATED repos on the same host would then see each other's module
claims. The SHARE dir already gives exactly what this ledger needs: repo-scoped, worktree-converged
coordination - no more, no less.
