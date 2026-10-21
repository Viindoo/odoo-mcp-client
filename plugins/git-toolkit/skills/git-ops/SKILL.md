---
name: git-ops
argument-hint: "[git/github task]"
description: >-
  Front door for any git or GitHub task, however casually asked: commit, push, branch, rebase, merge, cherry-pick, conflicts, history rewrite, recovery, PRs, issues, CI, or a pasted PR/issue URL. Runs it in a delegated agent so no code is lost. Defer to a domain skill for code review, rebase or forward-port when one is installed
---

# git-ops - the universal git/github front door

Any git or GitHub need routes through here. The contract: every git or GitHub operation, a
one-line read included, runs in a delegated agent so the CALLER'S context stays clean, code is
NEVER lost, and the work scales from a few lines to thousands of files.

**Your job is to ROUTE and DISPATCH, not to execute.** You classify the op, pick the agent and its
tier, and hand over a brief. You run no git or GitHub command yourself and read no diff, PR body
or file the op touches: the agent that owns the op also owns the know-how (which commands, which
flags, which safety steps) and returns a compact result.

## The brief rule

The caller describes the REQUEST and the RESULT it expects - never the commands.

- **Request:** what is wanted, which repository, worktree and branch, the business outcome behind
  it, the constraints, and any human confirmation already given (`confirmed:`).
- **Result:** what the caller needs back - a state, a verdict, a commit subject, a link, a yes/no.
- **Never** write a git or GitHub-CLI command, a subcommand sequence or a flag in a brief, and
  never paste one from memory or from another document. The agents choose them; a command in a
  brief overrides the agent's know-how, confuses it and forks the source of truth.

## Step 1 - classify the op

Bucket the request as one of: READ (state, history, a diff to analyze, blame, a proof that nothing
was lost), LOCAL MUTATION (stage, commit, clone, branch, tag, worktree, fetch, pull, merge,
cherry-pick, forward-port, backport, push, or a destructive rewrite such as rebase, squash, split,
amend, reset, history filtering), or GITHUB (PR, issue, review, release, CI, fork). Reading the
result of a finished bisect is a READ; running a live bisect checks out commits again and again,
so it is a LOCAL MUTATION.

## Step 2 - route to the agent

Apply `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation-decision.md`. Every op goes to an agent:

| Op | Agent |
|---|---|
| READ, bounded or not | `git-surveyor` (read-only) |
| LOCAL MUTATION | `git-operator` (carries the safety contract) |
| GITHUB | `github-operator` (GitHub MCP first, the GitHub CLI as fallback) |
| LARGE or COMPLEX (past the M2 trigger in `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`) | `git-pipeline-lead` |

Resolve the tier from `${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md` (first-match-wins; a read
takes the cheapest tier the table allows; for the lead the CALLER decides, row 1). Pass it as the
launch's `model` param AND put `DISPATCH MODEL: <tier>` as the first line of the brief.

Collect the worker's result by the N0 rule in `${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md`.
This skill runs in whatever context invoked it - the main conversation or a dispatched agent - so
read the launch tool THIS context holds: whether it has a `run_in_background` parameter decides
whether the launch returns the result inside this turn or this turn ends and the result arrives on
a wake.

If THIS context cannot launch agents, return `NEEDS_CONTEXT` ("needs a context that can launch
git-ops agents") per N4 in the same file. Do not run the op yourself.

A mutation brief names its worktree: `worktree` (exact absolute path) or `worktree_root` (the
agent creates `<worktree_root>/<branch-slug>`). Neither given -> ask the caller before
dispatching; the agent never chooses a location.

## Step 3 - safety

Every destructive op runs under the safety contract in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`; the agent applies it, not you. The one
human gate is a change to a protected branch without a pull request (a direct push to or deletion
of it, or merging a PR into it): that op reaches an agent only WITH the human confirmation in its
brief; otherwise STOP at the gate and ask.

## Step 4 - commits

State the BUSINESS outcome of a commit in the request; the agent detects the repo's convention,
writes the subject and signs off only when the repo requires it
(`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`). A caller-supplied commit message is
input, never output to pass through unchanged. Relay the agent's `commit_subject:` and
`message_rewritten:` to the caller.

## Out of scope - route elsewhere

| Situation | Route to |
|---|---|
| A domain-specific same-series rebase pipeline | that domain's rebase front-door |
| Porting code ACROSS major versions as a domain pipeline | that domain's forward-port front-door |
| Upgrading a module cluster to a new major series | that domain's upgrade front-door |
