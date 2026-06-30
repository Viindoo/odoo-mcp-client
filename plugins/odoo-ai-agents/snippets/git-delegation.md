<!-- SSOT snippet. Single home for git delegation rules in odoo-ai-agents: hard rule,
     bounded-read allowlist, git-ops invocation contract, what git-ops resolves to, nesting,
     confirm pass-through, and conflict stateless-resume recipe. Referenced (not copy-pasted)
     by every git-touching odoo-ai-agents skill/agent/command. Edit here only. -->

# Git Delegation Contract

## Hard rule

Business skills, agents, and commands in odoo-ai-agents MUST NOT directly execute git
mutations (rebase, cherry-pick, merge, reset, amend, push, branch force-delete, filter-repo),
gh CLI calls, mcp__plugin_github_github__* tools, or unbounded git reads.

To perform a git/GitHub operation, INVOKE the `git-toolkit:git-ops` skill via the Skill
tool, describing the op (e.g. create a worktree, cherry-pick a range onto integration +
squash, open/merge a PR, read a diff range) + the scope + the worktree path + whether an
L2 destructive op is human-confirmed. git-ops resolves the op to the right git agent
(git-surveyor read / git-operator local mutation / github-operator GitHub / git-pipeline-lead
for >500 files / >10k LOC / thousand-file jobs) and runs it under the safety contract.
Consumers NO LONGER name or directly cold-spawn the git leaf agents via the Agent tool.

## Bounded-read allowlist (inline OK)

These bounded, low-risk reads MAY run inline without routing through git-ops:
`git status`, `git rev-parse`, `git branch --show-current`, `git remote get-url`,
`git merge-base`, `git worktree list`,
`git diff --stat/--name-only/--shortstat/--quiet/--check`,
`git log -n<N>/--oneline`, `git show --stat`

Anything beyond this list (full diff content, unbounded log range, blame, large range) -> route through git-ops.

## Benign local writes (own worktree only)

A subagent MAY run `git add`, `git commit`, and `git stash` of ITS OWN work in ITS OWN
dedicated worktree inline - these are NOT "mutations" under the hard rule (S9 is satisfied
by construction: the worker is already isolated). A dispatched worker stages and commits its
own changes and returns the resulting SHA to the orchestrator. DANGEROUS ops that still
require routing through git-ops: branch, checkout, switch, cherry-pick, merge, rebase,
reset, tag, push, force-push, fetch, pull, worktree add/remove, and all GitHub-API ops.

## What git-ops resolves the op to (informational)

You do NOT pick or name these - you describe the op to git-ops and it classifies + routes.
This table is reference only, so a brief author knows what is happening under the front door.

| The op | git-ops resolves it to |
|---|---|
| Read-only git cognition - diff/log/range-diff analysis, map, verify | git-surveyor |
| Local mutation - rebase, cherry-pick, merge, commit, push, reset, tag, forward/back-port | git-operator |
| GitHub API - PR/issue lifecycle, CI, releases, fork->PR | github-operator |
| LARGE/COMPLEX - >500 files OR >10k LOC OR multi-commit history rewrite OR thousand-file port | git-pipeline-lead |

## Worktree isolation - mandatory for every mutation

When requesting ANY mutation (rebase, cherry-pick, commit, merge, reset, push, etc.) from
git-ops, you MUST require worktree isolation: either supply a `worktree` path in the request
or instruct git-ops to create a dedicated one. NEVER request a mutation against the main/shared
checkout. The primary/shared checkout must stay on its principal branch at all times.

This is the S9 invariant (Worktree-always / principal-checkout-lock) defined as SSOT in
git-toolkit's `snippets/git-safety-contract.md`. Violating it is an ERROR, not an option.

## Invocation contract

Invoke `git-toolkit:git-ops` via the Skill tool. In the request, describe AT MINIMUM:
- `op`: one-line description of the operation (create a worktree; cherry-pick a range onto
  integration + squash; open a PR; read a diff range; ...)
- `scope`: refs / range / paths
- `worktree`: absolute path of the dedicated worktree (or ask git-ops to create one)
- For destructive (L2) ops: `confirmed: <yes + quoted human approval | no>`
- `USER LANGUAGE: <language>`

git-ops classifies the op, routes it to the right git agent, and returns a compact result
block. Do NOT inline unbounded output (full diffs, PR bodies, file contents) - that is why
you route through git-ops instead of running git yourself.

## Nesting

Invoking a SKILL via the Skill tool runs IN the caller's own context - it adds NO subagent
depth. git-ops then cold-spawns exactly ONE git leaf agent to run the op - the same single
leaf depth as the previous direct-dispatch design. So this is safe at ANY caller depth (main
context, a wave work-item, a workflow pipeline): the git-ops invocation is inline, and only
one leaf is ever spawned beneath it. The git leaf agents cannot spawn further, so depth stays
bounded. (Ref: git-toolkit `git-nesting-protocol` N1.)

## Human-confirm pass-through

For destructive ops, obtain explicit human confirmation BEFORE invoking git-ops. Present the
op WITH Odoo context (module, branch, what is irreversible), then pass it as
`confirmed: yes - <quote>` in the git-ops request. git-ops (and the git agent beneath it)
enforces its own gate as backstop and returns BLOCKED if confirmation is absent. After a
BLOCKED return, obtain confirmation and invoke git-ops again.
(Ref: git-toolkit `git-safety-contract`.)

## Conflict stateless-resume (rebase / merge / cherry-pick)

Ask git-ops to resolve ALL mechanical conflicts (.po / .pot / binary / generated) and advance
to the next Odoo-semantic conflict. When it stops on an unresolved semantic conflict it returns
`BLOCKED-CONFLICT` (distinct from plain `BLOCKED`) with two additional fields in its result
block:
- `conflicted_files: [<relative-paths>]` - files carrying unresolved conflict markers
- `stopped_commit: <sha>` - the commit at which the rebase / cherry-pick stopped

**Status mapping for callers:**
- `DONE` => operation completed cleanly
- `BLOCKED` => safety gate triggered; present to human, obtain approval, invoke git-ops again with `confirmed:`
- `BLOCKED-CONFLICT` => semantic conflict stopped the op; run the stateless-resume loop below

**Resume loop** (rebase / merge / cherry-pick state persists ON DISK across separate git-ops invocations):
1. Read `conflicted_files` and `stopped_commit` from the git-ops result.
2. Dispatch a semantic resolver (e.g. odoo-coder) into the worktree to edit the conflicted
   files - a file edit, NOT a git op; the resolver does NOT run cherry-pick or merge itself.
3. Invoke git-ops again: ask it to stage the resolved files and continue the in-progress
   operation (the `--continue` flag of the original op type).
4. Repeat until git-ops returns `DONE` or a non-conflict `BLOCKED`.

(Ref: git-toolkit `git-safety-contract`.)
(S9 SSOT: git-toolkit `snippets/git-safety-contract.md`.)
