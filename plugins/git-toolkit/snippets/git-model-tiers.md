# Git model tiers

A tier is chosen by the kind of work and its reversibility, never by context size: haiku for what a
cheap model does reliably, sonnet where an error is costly or judgement is needed, opus only for
strategy synthesis. The toolkit authors no application code, so `fable` is not used. The safety
contract (backup, tree identity, the protected-branch gate) is the same at every tier.

## Single-delegate op class -> tier

First match wins.

| # | Op class | Agent | Tier |
|---|---|---|---|
| 1 | Launching `git-pipeline-lead` - the caller decides before launch, the lead never picks its own tier. A sonnet lead that returns BLOCKED at P3 is re-launched once at opus | `git-pipeline-lead` | opus for a port across major versions (its P3 strategy is the hard part), else sonnet |
| 2 | Destructive history rewrite (interactive rebase, squash, split, amend, reset, filter-repo, force-with-lease push), or any integration that is resolving conflicts | `git-operator` | sonnet |
| 3 | Bounded conflict-free integration (fetch, branch, tag, worktree, non-force push, clean cherry-pick or merge); a conflict mid-op means re-dispatch at sonnet | `git-operator` | haiku |
| 4 | Read-only no-loss verify (tree identity, range-diff) that gates an irreversible step | `git-surveyor` | sonnet |
| 5 | Other read-only git cognition: enumerate, map, analyze a diff, assess conflict, risk or intent | `git-surveyor` | haiku |
| 6 | GitHub API op that judges correctness (review a PR diff and post findings) | `github-operator` | sonnet |
| 7 | Other GitHub API op (read, list, issue triage, CI status, create PR, release or tag, fork) | `github-operator` | haiku |

The caller passes the tier as the launch's `model` parameter. It outranks the agent's frontmatter
`model:`, the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable and the calling context's model, so
never rely on a default or on inheritance.

The per-phase tiers of the phased pipeline (P1 to P5) are in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N3.
