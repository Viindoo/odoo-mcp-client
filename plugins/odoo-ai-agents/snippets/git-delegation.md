<!-- SSOT snippet. Single home for git delegation rules in odoo-ai-agents: hard rule,
     bounded-read allowlist, git-ops invocation contract, what git-ops resolves to, nesting,
     confirm pass-through, and conflict stateless-resume recipe. Referenced (not copy-pasted)
     by every git-touching odoo-ai-agents skill/agent/command. Edit here only. -->

# Git Delegation Contract

## Universal rule

**Universal rule (EVERY actor - the main/orchestrating agent included, not only dispatched
skills/agents/commands).** No actor may directly execute git mutations (rebase, cherry-pick, merge,
reset, amend, push, branch force-delete, filter-repo), gh CLI calls, GitHub-MCP tools, or unbounded
git reads. If you CREATE or EDIT any git-tracked file - even a one-line change, even repo
self-maintenance - you MUST commit it by invoking the `git-toolkit:git-ops` skill; never hand-run
stage / commit / push yourself. git-ops detects the repo's commit convention and applies the DCO
sign-off itself (convention + sign-off SSOT: `git-toolkit/snippets/commit-convention.md` C1-C4), so
routing through git-ops SATISFIES DCO. The main agent is bound by the equivalent statement in the
repo `CLAUDE.md`; keep the two in lockstep.

To perform a git/GitHub operation, INVOKE the `git-toolkit:git-ops` skill via the Skill
tool, describing the op (e.g. create a worktree, cherry-pick a range onto integration +
squash, open/merge a PR, read a diff range) + the scope + the worktree path + whether an
L2 destructive op is human-confirmed. git-ops resolves the op to the right git agent
(git-surveyor read / git-operator local mutation / github-operator GitHub / git-pipeline-lead
for >500 files / >10k LOC / thousand-file jobs) and runs it under the safety contract.
Consumers NO LONGER name or directly cold-spawn the git leaf agents by launching them.

## Bounded-read allowlist (inline OK)

These bounded, low-risk reads MAY run inline without routing through git-ops:
`git status`, `git rev-parse`, `git branch --show-current`, `git remote get-url`,
`git merge-base`, `git worktree list`,
`git diff --stat/--name-only/--shortstat/--quiet/--check`,
`git log -n<N>/--oneline`, `git show --stat`

Anything beyond this list (full diff content, unbounded log range, blame, large range) -> route through git-ops.

## No LEAF-worker git - the orchestrator (or a spawner coordinator) commits via git-ops

A dispatched HARD-LEAF worker (`odoo-backend-coder`, `odoo-frontend-coder`, `odoo-test-writer`, or
ANY leaf domain subagent) does NOT run git - not even git add / git commit / git stash in its own
worktree. Leaf workers do not own the project's git/commit conventions, so git is never their job. A
leaf finishing work in a `WORKTREE_PATH` WRITES its files there and RETURNS the list of files it
touched; it never stages, commits, or stashes.

The actor that COMMITS is the orchestrator OR a SPAWNER coordinator that owns the worktree, by
INVOKING `git-toolkit:git-ops`. In particular the `odoo-coder` per-module COORDINATOR (a spawner -
it can launch agents and launches the leaf coders, so it is NOT a leaf) COMMITS its module by
invoking `git-toolkit:git-ops` via the Skill tool once its integrated test is green, and returns the
SHA to `odoo-coding` (which collects it, no longer re-committing). The coordinator only REQUESTS the
commit (files + business outcome); it never runs raw git and never dispatches a git leaf agent
itself. Every git verb - `add`,
`commit`, `stash`, `branch`, `checkout`, `switch`, `cherry-pick`, `merge`, `rebase`, `reset`, `tag`,
`push`, `force-push`, `fetch`, `pull`, `worktree add/remove`, and all GitHub-API ops - is routed
through git-ops. The ONLY git a worker may run inline is the bounded-read allowlist above.

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

## Self-provisioning specialists

These skills create their own worktree/branch internally, so an orchestrator/driver MUST NOT
provision one for them: `odoo-forward-port`, `odoo-git-rebase`,
`odoo-modules-upgrade`, and `odoo-code-review` at `TARGET=pr`. (The per-wave coding worktrees are
provisioned by `run-harness`'s own between-wave integration per Block 2W, not by a dispatched
specialist - see `run-harness` SKILL.md § Between-wave integration.)

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

Invoking a SKILL via the Skill tool runs IN the caller's own context - unlike launching an
agent, which runs in a separate context. This makes it safe for any SKILL/orchestrator caller
(main context, a wave work-item, a workflow pipeline) to invoke git-ops inline: git-ops then
cold-spawns exactly ONE git leaf agent to run the op, and that leaf cannot launch anything
further - it holds no agent-launch capability. This does not extend to an agent-launched leaf
(see below), which never invokes git-ops itself. (Ref: git-toolkit `git-nesting-protocol` N1.)

A HARD-LEAF worker (`odoo-backend-coder`, `odoo-frontend-coder`, `odoo-test-writer`,
`odoo-icon-designer`, ANY leaf domain subagent) NEVER invokes git-ops, not even via the Skill tool:
it cannot launch agents and returns files for its orchestrator/coordinator to commit (SSOT:
`worker-brief.md`). A SPAWNER coordinator that can launch agents - notably the `odoo-coder`
per-module coordinator, and any SKILL/orchestrator context (main, a workflow phase, `run-harness`'s
between-wave integration loop) - MAY invoke git-ops via the Skill tool, which runs INLINE in its
own context; git-ops then cold-spawns exactly ONE git leaf below it, and that leaf cannot launch
anything further either. The discriminator is agent-launch capability, not "was I launched by an agent":
`odoo-coder` was launched by an agent yet is itself a spawner, so it commits. Two-line test: "Can
launch agents (orchestrator / spawner coordinator incl. `odoo-coder`) -> may invoke git-ops inline.
Hard leaf (cannot launch agents) -> return files, never git."

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
