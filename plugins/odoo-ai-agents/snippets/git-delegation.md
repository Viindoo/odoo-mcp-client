<!-- SSOT snippet. Single home for git delegation rules in odoo-ai-agents: hard rule,
     bounded-read allowlist, agent routing, dispatch contract, nesting, confirm pass-through,
     and conflict stateless-resume recipe. Referenced (not copy-pasted) by every
     git-touching odoo-ai-agents skill/agent/command. Edit here only. -->

# Git Delegation Contract

## Hard rule

Business skills, agents, and commands in odoo-ai-agents MUST NOT directly execute git
mutations (rebase, cherry-pick, merge, reset, amend, push, branch force-delete, filter-repo),
gh CLI calls, mcp__plugin_github_github__* tools, or unbounded git reads. Delegate every
such op to git-toolkit by cold-spawning its agents via the Agent tool `subagent_type`.

## Bounded-read allowlist (inline OK)

These bounded, low-risk reads MAY run inline without delegation:
`git status`, `git rev-parse`, `git branch --show-current`, `git remote get-url`,
`git merge-base`, `git worktree list`,
`git diff --stat/--name-only/--shortstat/--quiet/--check`,
`git log -n<N>/--oneline`, `git show --stat`

Anything beyond this list (full diff content, unbounded log range, blame, large range) -> delegate.

## Benign local writes (own worktree only)

A subagent MAY run `git add`, `git commit`, and `git stash` of ITS OWN work in ITS OWN
dedicated worktree inline - these are NOT "mutations" under the hard rule (S9 is satisfied
by construction: the worker is already isolated). A dispatched worker stages and commits its
own changes and returns the resulting SHA to the orchestrator. DANGEROUS ops that still
require delegation to git-operator: branch, checkout, switch, cherry-pick, merge, rebase,
reset, tag, push, force-push, fetch, pull, worktree add/remove, and all GitHub-API ops.

## Agent routing

| Need | Agent |
|---|---|
| Read-only git cognition - diff/log/range-diff analysis, map, verify | `git-surveyor` |
| Local mutation - rebase, cherry-pick, merge, commit, push, reset, tag, forward/back-port | `git-operator` |
| GitHub API - PR/issue lifecycle, CI, releases, fork->PR | `github-operator` |
| LARGE/COMPLEX - >500 files OR >10k LOC OR multi-commit history rewrite OR thousand-file port | `git-pipeline-lead` |

## Worktree isolation - mandatory for every mutation

When delegating ANY mutation (rebase, cherry-pick, commit, merge, reset, push, etc.) to
git-operator, you MUST request worktree isolation: either supply a `worktree` path in the brief
or instruct git-operator to create a dedicated one. NEVER ask git-operator to switch or operate
directly on the main checkout. The primary/shared checkout must stay on its principal branch at
all times.

This is the S9 invariant (Worktree-always / principal-checkout-lock) defined as SSOT in
git-toolkit's `snippets/git-safety-contract.md`. Violating it is an ERROR, not an option.

## Dispatch contract

Cold-spawn the chosen agent. Supply AT MINIMUM in the brief:
- `op`: one-line description of the operation
- `scope`: refs / range / paths
- `worktree`: absolute path of the dedicated worktree (or `create` to let git-operator make one)
- For destructive ops: `confirmed: <yes + quoted human approval | no>`
- `USER LANGUAGE: <language>`

The agent body documents its full brief schema and result block. Do NOT inline unbounded
output (full diffs, PR bodies, file contents) - that is why you delegate.

## Nesting

You MAY cold-spawn git-toolkit agents even when you are yourself a subagent (inside a wave
or workflow pipeline). Leaf agents (git-surveyor, git-operator, github-operator) cannot
spawn further, so depth is bounded at two levels. (Ref: git-toolkit `git-nesting-protocol` N1.)

## Human-confirm pass-through

For destructive ops, obtain explicit human confirmation BEFORE dispatching. Present the op
WITH Odoo context (module, branch, what is irreversible), then pass it as
`confirmed: yes - <quote>` in git-operator's brief. git-operator enforces its own gate as
backstop and returns BLOCKED if confirmation is absent. After a BLOCKED return, obtain
confirmation and re-dispatch a fresh git-operator.
(Ref: git-toolkit `git-safety-contract`.)

## Conflict stateless-resume (rebase / merge / cherry-pick)

Brief git-operator to resolve ALL mechanical conflicts (.po / .pot / binary / generated)
and advance to the next Odoo-semantic conflict. When it stops on an unresolved semantic
conflict it returns `BLOCKED-CONFLICT` (distinct from plain `BLOCKED`) with two additional
fields in its result block:
- `conflicted_files: [<relative-paths>]` - files carrying unresolved conflict markers
- `stopped_commit: <sha>` - the commit at which the rebase / cherry-pick stopped

**Status mapping for callers:**
- `DONE` => operation completed cleanly
- `BLOCKED` => safety gate triggered; present to human, obtain approval, re-dispatch with `confirmed:`
- `BLOCKED-CONFLICT` => semantic conflict stopped the op; run the stateless-resume loop below

**Resume loop** (rebase / merge / cherry-pick state persists ON DISK across cold-spawns):
1. Read `conflicted_files` and `stopped_commit` from the git-operator result.
2. Dispatch a semantic resolver (e.g. odoo-coder) into the worktree to edit the conflicted
   files - a file edit, NOT a git op; the resolver does NOT run cherry-pick or merge itself.
3. Cold-spawn a FRESH git-operator: brief it to stage the resolved files and continue the
   in-progress operation (the `--continue` flag of the original op type).
4. Repeat until git-operator returns `DONE` or a non-conflict `BLOCKED`.

(Ref: git-toolkit `git-safety-contract`.)
(S9 SSOT: git-toolkit `snippets/git-safety-contract.md`.)
