<!-- SSOT snippet. Single home for git delegation rules in odoo-ai-agents: the no-git rule, the
     repo_facts tool, how to word a request to git-ops, base-branch resolution, leaf-worker git, what
     git-ops resolves to, nesting, confirm pass-through, and the conflict stateless-resume recipe.
     Referenced (not copy-pasted) by every git-touching odoo-ai-agents skill/agent/command. Edit here only. -->

# Git Delegation Contract

## Universal rule

**No actor runs git** - the main/orchestrating agent, every dispatched skill, agent and command, and
every leaf worker alike. Not a mutation, not a read, not a "harmless" status; not inside a wrapper
(`bash -c`, `$(...)`, a heredoc) or a script you write. How to operate git - which commands, which
flags - is the git agents' job and lives only in git-toolkit. A call the permission classifier
refuses: `${CLAUDE_PLUGIN_ROOT}/snippets/permission-denial.md`. Two doors only:

1. **A repo fact -> the odoo-local `repo_facts` tool.** The repository root and the main checkout
   behind a linked worktree, the current branch or ref, the short HEAD SHA, the origin URL, whether
   given paths are clean or dirty, and whether a merge / rebase / cherry-pick is in progress. One call
   with the directory (and `status_paths` for the dirtiness question); an `is_repo=false` answer means
   the directory is outside any repository.
2. **Everything else -> a request to `git-toolkit:git-ops`.** History, diffs, file lists, ancestry,
   branch lists, a worktree, every change to the repository, every GitHub operation (`gh` and the
   GitHub MCP tools are git-ops's too).

If you CREATE or EDIT any git-tracked file - even a one-line change, even repo self-maintenance - you
MUST commit it by invoking the `git-toolkit:git-ops` skill; never stage, commit or push yourself.
git-ops detects the repo's commit convention and applies the DCO sign-off where the repo requires it
(convention + sign-off SSOT: `git-toolkit/snippets/commit-convention.md` C1-C4).

## Asking git-ops - the request and the result, never the command

INVOKE the `git-toolkit:git-ops` skill via the Skill tool. A request states WHAT is wanted and WHAT it
must hand back; git-ops classifies the op INTERNALLY (read-only cognition, local mutation, GitHub API,
or large/complex at scale), routes it to the specialist that owns that class and runs it under the
safety contract. Consumers never name or pick the specialist, and never write a command, a flag or a
verb list.

- **Say the outcome.** "The merge base of the feature branch and the new base, and the non-merge
  commits after it" - not how to compute them. "Absorb the source range into the integration
  worktree and stop before the commit" - not the merge flags.
- **Say the shape of the result.** A single value comes back in the reply. A list, diff, log or
  per-file listing is written by git-ops to a path you name (under the run's `ISOLATE_DIR`) and you
  Read it; never ask for unbounded output inline.
- **Data a later step needs is a result like any other.** A merge base, a commit list, a file list
  the next phase reads: ask for it, with the path it is written to, and read that file later.
- **A finished request says how to tell it worked.** "Return the new tip SHA and whether the tree
  is identical to the one before" beats "run the checks".

## Base-branch resolution (the version-named main branch)

Per `git-toolkit`'s explicit-start-point rule (`git-safety-contract.md` S9 addendum), every
worktree/branch created to receive new coding-node, upgrade, or self-provisioned work resolves its
start point by RESOLVING the branch below - never by inheriting whatever the invoking checkout's
HEAD/current branch happens to be. The `branch` / `ref` that `repo_facts` returns stays legitimate
for diagnostic reads and source-series INFERENCE (e.g. cross-checking what a human is currently on
against a manifest-derived series) - it MUST NEVER be the value assigned to a `base` / `work-base` /
Repo Capability Card `base` field. A `base` resolved from the invoking checkout's ambient branch
reproduces the exact defect this section exists to close. One exception: the docs worktree of
`odoo-doc-illustration` (§ Self-provisioning specialists) starts at the principal checkout's HEAD
commit, named explicitly - docs describe the code the user pointed at.

**Input.** The run's already-resolved `odoo_version` (the Run-header field required on every
`writes-files` plan - SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` - resolved
BEFORE this algorithm runs; never re-derived from a branch name here).

**Candidate enumeration.** Ask `git-toolkit:git-ops` to report the local and remote-tracking
branches matching the candidates below, in the SAME request that also compares their tips and
fetches if needed (enumerate + compare + fetch-if-needed is one request, detailed in the table
below). A candidate branch name must EXACTLY equal `<odoo_version>`,
`saas-<odoo_version>` (when `odoo_version` is itself a SaaS series), or a vendor-prefixed form ONLY
IF the brief or the repo's branch history carries it (never invented at resolution time).
**EXACT branch-name match only - never a substring/contains match.** A substring match
(e.g. matching `<odoo_version>-feat-x` because it contains `<odoo_version>`) reintroduces the exact confusion this
rule exists to prevent: a human's feature branch would qualify as a "candidate" purely for
containing the series number.

**Resolution table - a decidable action, and a terminal status where one applies:**

| Case | Decidable action | Terminal status |
|---|---|---|
| Zero candidate names | Never invent one, never fall back to HEAD | `NEEDS_CONTEXT(base_branch)` - ask which branch is this series' main branch |
| Exactly one candidate name, no remote-tracking ref for it | Use the local branch's tip; STATE the assumption ("no remote-tracking ref found; using local `<name>` as-is") in the plan/report | none - proceeds with a stated assumption |
| Exactly one candidate name, remote-tracking ref exists, tips equal (git-ops reports the local and the remote-tracking tip of `<name>` as the same commit) | Use `origin/<name>` (prefer the remote-tracking ref on principle even when already in sync) | none - proceeds |
| Exactly one candidate name, remote-tracking ref exists, tips diverge (local behind OR ahead) | Ask `git-toolkit:git-ops` to fetch the remote and compare the two tips again; still diverged after the fetch | `open_question` - a human decides whether to build on `origin/<name>` or the local tip; never silently pick either side |
| More than one distinct candidate name (e.g. both `17.0` and `viindoo-17.0` exist) | Never silently prefer one | `open_question` listing every candidate |
| Detached HEAD on the invoking checkout | No effect - this algorithm never reads the invoking checkout's HEAD/branch as an input, only `odoo_version` and the repo's branch list | none - irrelevant by construction |
| Dirty tree on the invoking checkout | No effect on base resolution - dirty-tree preconditions for the MUTATION itself are S4's job (`git-safety-contract.md`), not this rule's | none - irrelevant by construction |

Enumerating candidates, comparing tips and fetching are all one request to `git-toolkit:git-ops`.
No actor resolves a stale `base` by fetching inline.

## No LEAF-worker git - the orchestrator (or the node owner) commits via git-ops

A dispatched HARD-LEAF worker (`odoo-frontend-coder`, `odoo-test-writer`, `odoo-impact-recon`, or
ANY leaf domain subagent) runs no git at all, not even in its own worktree and not even to read:
the Universal rule binds it first. Leaf workers do not own the project's git/commit conventions, so
git is never their job. A leaf takes a repo fact from `repo_facts`; for anything else, it WRITES its
files in its `WORKTREE_PATH` and RETURNS the list of files it touched. A leaf never invokes git-ops
either (see Nesting).

The actor that COMMITS is the orchestrator OR the node owner that owns the worktree, by
INVOKING `git-toolkit:git-ops`. In particular `odoo-coder` (`role: node-owner` - it writes the
node and may launch a leaf, so it is NOT a leaf) COMMITS its node by invoking
`git-toolkit:git-ops` via the Skill tool once its whole-node test is green, and returns the
range to `odoo-coding` (which collects it, never re-committing). The coder only REQUESTS the
commit (files + business outcome); it never runs raw git and never dispatches a git leaf agent
itself. A node owner or spawner asks `Skill(git-toolkit:git-ops)` for every change to the
repository and every GitHub-API op, and reads every repo fact from `repo_facts`.

## How git-ops resolves a request (informational)

You do NOT pick or name a specialist - you describe the op and git-ops classifies + routes
internally, never you, among four op classes: read-only git cognition, local mutation, GitHub API,
and large/complex jobs (>500 files OR >10k LOC OR a multi-commit history rewrite OR a
thousand-file port).

## Worktree isolation - mandatory for every mutation

When requesting ANY change to the repository (rebase, cherry-pick, commit, merge, reset, push,
etc.) from git-ops, you MUST require worktree isolation: supply the `worktree` path in the request. For a
NEW worktree that path comes from `project_dir` (axis `worktree`, `name` = the branch slug; SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), never from git-ops's own choice.
NEVER request a mutation against the main/shared checkout. The primary/shared checkout must stay
on its principal branch at all times.

This is the S9 invariant (Worktree-always / principal-checkout-lock) defined as SSOT in
git-toolkit's `snippets/git-safety-contract.md`. Violating it is an ERROR, not an option.

## Self-provisioning specialists

These skills create their own worktree/branch internally, so an orchestrator/driver MUST NOT
provision one for them: `odoo-forward-port`, `odoo-git-rebase`,
`odoo-modules-upgrade`, and `odoo-code-review` at `TARGET=pr`. (Each source-writing node's worktree
is provisioned by the plan runner, forked from that repo's `run-integration` branch - not by a
dispatched specialist - see `plan-mode-schema.md` § Running the plan, step 2.)

`odoo-doc-illustration` self-provisions only when its target is a principal checkout: it moves the
run into a new docs worktree and branch at that checkout's HEAD commit, after a `repo_facts` call
(`status_paths` = the module paths) whose uncommitted changes it puts to the user once (commit them
first, or document HEAD without them). So a dispatcher outside a run (`odoo-intake`
without Phase P, a direct invocation) provisions nothing for it. On a run, the runner hands it
the run's worktree like any source-writing node; a linked worktree it receives is used as is.

## Invocation contract

Invoke `git-toolkit:git-ops` via the Skill tool. In the request, describe AT MINIMUM:
- `op`: one-line description of the operation (create a worktree; cherry-pick a range onto
  integration + squash; open a PR; read a diff range; ...)
- `scope`: refs / range / paths
- `worktree`: absolute path of the dedicated worktree - an existing one, or the `project_dir`
  axis `worktree` path git-ops creates it at
- For the L2 op - a push to or deletion of a protected branch, or merging a PR into one:
  `confirmed: <yes + quoted human approval | no>`
- `commit`: the files and the business outcome, never a finished message. A proposed Odoo
  `[TAG]` comes only from the TAG table in git-toolkit's
  `skills/git-ops/references/commit-convention-odoo.md`. git-ops validates it and returns
  `commit_subject:` and `message_rewritten:`; relay a rewrite, never re-commit it.
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

A HARD-LEAF worker (`odoo-frontend-coder`, `odoo-test-writer`, `odoo-impact-recon`,
`odoo-icon-designer`, ANY leaf domain subagent) NEVER invokes git-ops, not even via the Skill tool:
it cannot launch agents and returns files for its orchestrator or node owner to commit (SSOT:
`worker-brief.md`). A node owner or spawner that can launch agents - notably `odoo-coder`, and
any SKILL/orchestrator context (main running a plan, a workflow phase) - MAY invoke git-ops via
the Skill tool, which runs INLINE in its
own context; git-ops then cold-spawns exactly ONE git leaf below it, and that leaf cannot launch
anything further either. The discriminator is agent-launch capability, not "was I launched by an agent":
`odoo-coder` was launched by an agent yet can launch one itself, so it commits. Two-line test: "Can
launch agents (orchestrator / node owner incl. `odoo-coder`) -> may invoke git-ops inline.
Hard leaf (cannot launch agents) -> return files, never git."

## Human-confirm pass-through

The L2 git gate is ONE op class: a push that moves or deletes a protected branch without a pull
request, and merging a PR into one (protected branch: git-toolkit `git-safety-contract`). Only
for it, obtain explicit human confirmation BEFORE invoking git-ops - present it WITH Odoo context
(module, branch, what changes on the remote) and pass `confirmed: yes - <quote>`. git-ops returns
BLOCKED without it; then obtain it and invoke again. Every other op (rewrite, squash,
force-with-lease to a feature or fork branch) git-ops decides itself; never ask the human.
(Ref: git-toolkit `git-safety-contract`.)

## Conflict stateless-resume (rebase / merge / cherry-pick)

Ask git-ops to resolve ALL mechanical conflicts (.po / .pot / binary / generated / a package
`__init__.py` whose conflicting hunks are import lines only) and advance
to the next Odoo-semantic conflict. When it stops on an unresolved semantic conflict it returns
`BLOCKED-CONFLICT` (distinct from plain `BLOCKED`) with two extra result-block fields:
- `conflicted_files: [<relative-paths>]` - files carrying unresolved conflict markers
- `stopped_commit: <sha>` - the commit at which the rebase / cherry-pick stopped

**Status mapping for callers:**
- `DONE` => operation completed cleanly
- `BLOCKED` with `gate_hit: protected branch ...` => present to human, obtain approval, invoke git-ops again with `confirmed:`
- `BLOCKED` with `gate_hit: S4 dirty tree` => uncommitted changes git-ops will not stash; settle them, then invoke again
- `BLOCKED-CONFLICT` => semantic conflict stopped the op; run the stateless-resume loop below

**Resume loop** (rebase / merge / cherry-pick state persists ON DISK across separate git-ops invocations):
1. Read `conflicted_files` and `stopped_commit` from the git-ops result.
2. Dispatch a semantic resolver (e.g. odoo-coder) into the worktree to edit the conflicted
   files - a file edit, NOT a git op; the resolver does NOT run cherry-pick or merge itself.
3. Invoke git-ops again: ask it to stage the resolved files and continue the in-progress
   operation of the original type.
4. Repeat until git-ops returns `DONE` or a non-conflict `BLOCKED`.

(Ref: git-toolkit `git-safety-contract`.)
(S9 SSOT: git-toolkit `snippets/git-safety-contract.md`.)
