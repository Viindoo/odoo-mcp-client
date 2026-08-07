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
L2 destructive op is human-confirmed. git-ops classifies the op INTERNALLY by op-type
(read-only cognition, local mutation, GitHub API, or large/complex at scale) and routes it
to the specialist that owns that class, then runs it under the safety contract. Consumers
never name or pick the specialist themselves.

## Bounded-read allowlist (inline OK)

Canonical SSOT: `git-toolkit`'s `snippets/git-delegation-decision.md` (INLINE mode) defines the
base bounded-read allowlist - `git status`, `git rev-parse`, `git log -n<N>`, `git show --stat`,
branch/ref existence checks, `git diff --stat`/`--name-only`. git-toolkit is the LOWER layer (it
never names or depends on odoo-ai-agents); this file cross-references that list rather than
forking it, and adds only the Odoo-specific reads below.

odoo-ai-agents-specific additions, also bounded-output and inline-OK: `git branch --show-current`
(current-branch read), `git remote get-url` (remote URL read), `git merge-base` (common-ancestor
read), `git worktree list` (listing only, not add/remove), `git diff --shortstat/--quiet/--check`
(extra bounded diff flags beyond `--stat`/`--name-only`), `git log --oneline` (extra bounded log
format).

The full inline-OK set for odoo-ai-agents is the UNION of both lists above:
`git status`, `git rev-parse`, `git branch --show-current`, `git remote get-url`,
`git merge-base`, `git worktree list`,
`git diff --stat/--name-only/--shortstat/--quiet/--check`,
`git log -n<N>/--oneline`, `git show --stat`

Anything beyond this union (full diff content, unbounded log range, blame, large range) -> route through git-ops.

## Base-branch resolution (the version-named main branch)

Per `git-toolkit`'s explicit-start-point rule (`git-safety-contract.md` S9 addendum), every
worktree/branch created to receive new coding-wave, upgrade, or self-provisioned work resolves its
start point by RESOLVING the branch below - never by inheriting whatever the invoking checkout's
HEAD/current branch happens to be. `git branch --show-current` (allowlisted above) stays legitimate
for diagnostic reads and source-series INFERENCE (e.g. cross-checking what a human is currently on
against a manifest-derived series) - it MUST NEVER be the value assigned to a `base` / `work-base` /
Repo Capability Card `base` field. A `base` resolved from the invoking checkout's ambient branch
reproduces the exact defect this section exists to close.

**Input.** The run's already-resolved `odoo_version` (the Run-header field required on every
`writes-files` plan - SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` - resolved
BEFORE this algorithm runs; never re-derived from a branch name here).

**Candidate enumeration.** Listing branches by name pattern is NOT on the bounded-read allowlist
above (only `branch --show-current` is), so ask `git-toolkit:git-ops` to report the local and
remote-tracking branches matching the candidates below, in the SAME request that also compares
tips and fetches if needed (enumerate + compare + fetch-if-needed is one op request, detailed in
the table below). A candidate branch name must EXACTLY equal `<odoo_version>` (e.g. `17.0`),
`saas-<odoo_version>` (when `odoo_version` is itself a SaaS series), or a vendor-prefixed form ONLY
IF the brief or the repo's branch history carries it (never invented at resolution time).
**EXACT branch-name match only - never a substring/contains match.** A substring match
(e.g. matching `17.0-feat-x` because it contains `17.0`) reintroduces the exact confusion this
rule exists to prevent: a human's feature branch would qualify as a "candidate" purely for
containing the series number.

**Resolution table - a decidable action, and a terminal status where one applies:**

| Case | Decidable action | Terminal status |
|---|---|---|
| Zero candidate names | Never invent one, never fall back to HEAD | `NEEDS_CONTEXT(base_branch)` - ask which branch is this series' main branch |
| Exactly one candidate name, no remote-tracking ref for it | Use the local branch's tip; STATE the assumption ("no remote-tracking ref found; using local `<name>` as-is") in the plan/report | none - proceeds with a stated assumption |
| Exactly one candidate name, remote-tracking ref exists, tips equal (`git rev-parse <name>` == `git rev-parse origin/<name>`, both bounded reads on the allowlist above once the name is known) | Use `origin/<name>` (prefer the remote-tracking ref on principle even when already in sync) | none - proceeds |
| Exactly one candidate name, remote-tracking ref exists, tips diverge (local behind OR ahead) | Ask `git-toolkit:git-ops` to `fetch` and re-compare (fetch is not a bounded read - see the Universal rule above); still diverged after fetch | `open_question` - a human decides whether to build on `origin/<name>` or the local tip; never silently pick either side |
| More than one distinct candidate name (e.g. both `17.0` and `viindoo-17.0` exist) | Never silently prefer one | `open_question` listing every candidate |
| Detached HEAD on the invoking checkout | No effect - this algorithm never reads the invoking checkout's HEAD/branch as an input, only `odoo_version` and the repo's branch list | none - irrelevant by construction |
| Dirty tree on the invoking checkout | No effect on base resolution - dirty-tree preconditions for the MUTATION itself are S4's job (`git-safety-contract.md`), not this rule's | none - irrelevant by construction |

Enumerating candidates and fetching are both routed through `git-toolkit:git-ops` - neither is on
the bounded-read allowlist above; only the tip comparison (`git rev-parse`) is a bounded inline
read once the candidate name is known. No actor resolves a stale `base` by fetching inline.

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

## How git-ops resolves a request (informational)

You do NOT pick or name a specialist - you describe the op and git-ops classifies + routes
internally, never you, among four op classes: read-only git cognition, local mutation, GitHub API,
and large/complex jobs (>500 files OR >10k LOC OR a multi-commit history rewrite OR a
thousand-file port).

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
provisioned by `run-harness`'s own between-wave integration - each forked FROM the ONE
`run-integration` branch per Block 2W, not by a dispatched specialist - see `run-harness` SKILL.md
§ Between-wave integration.)

## Invocation contract

Invoke `git-toolkit:git-ops` via the Skill tool. In the request, describe AT MINIMUM:
- `op`: one-line description of the operation (create a worktree; cherry-pick a range onto
  integration + squash; open a PR; read a diff range; ...)
- `scope`: refs / range / paths
- `worktree`: absolute path of the dedicated worktree (or ask git-ops to create one)
- For destructive (L2) ops: `confirmed: <yes + quoted human approval | no>`
- `USER LANGUAGE: <language>`

git-ops classifies the op, routes it, and returns a compact result block. Do NOT inline unbounded
output (full diffs, PR bodies, file contents) - that is why you route through git-ops instead of
running git yourself.

## Nesting

Invoking a SKILL via the Skill tool runs IN the caller's own context - unlike launching an agent,
which runs in a separate context. This makes it safe for any SKILL/orchestrator caller to invoke
git-ops inline: git-ops then cold-spawns exactly ONE git leaf agent to run the op, and that leaf
cannot launch anything further - it holds no agent-launch capability. This does not extend to an
agent-launched leaf (see below), which never invokes git-ops itself. (Ref: git-toolkit
`git-nesting-protocol` N1.)

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
`BLOCKED-CONFLICT` (distinct from plain `BLOCKED`) with two extra result-block fields:
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
