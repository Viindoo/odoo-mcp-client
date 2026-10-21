<!-- SSOT snippet. The single home for the execution-routing decision (which git-toolkit agent
     takes an op, at which tier) and the compact-return contract. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation-decision.md by skills/git-ops/SKILL.md.
     Edit here only. -->

# Git Delegation Decision (SSOT)

Every git/github op goes to an agent. No mode runs a command in the dispatcher's context: the
agent owns the know-how (commands, flags, safety steps), the dispatcher owns the request and the
expected result. The decision is WHICH agent and WHICH tier, by the kind of op and its size and
risk, never by step count. Goal: keep the caller's context clean, including for a one-line read.

## Which agent

| Op | Agent | Notes |
|---|---|---|
| Read: state, history, a diff to analyze, a proof of no loss | `git-surveyor` | read-only; bounded or not, a read goes here |
| Local mutation, reversible or destructive: commit, integrate, branch/tag/worktree, rebase, squash, reset, push | `git-operator` | carries the safety contract |
| GitHub API: PR, issue, review, release, CI, fork | `github-operator` | MCP-first, the GitHub CLI as fallback |
| Large or complex change per `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md` M2 | `git-pipeline-lead` | runs P1-P5 below the caller |

Each is a cold spawn with a self-contained brief that states the request and the expected result
(`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N1, N5): it works in its own context,
writes a findings file, and returns a 5-line summary + path.

## Which tier

Resolve the tier from `${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md` (single-delegate
op-class table, first-match-wins) and pass it as the launch's `model` param AND as the
`DISPATCH MODEL:` first line of the brief. For `git-pipeline-lead` the CALLER resolves the tier
before launch (row 1 of that table); the lead runs P1-P5 below the caller, maps -> evaluates ->
strategizes -> human-confirms (only before changing a protected branch without a pull request) ->
executes -> verifies, and returns only the final compact result.

## Classify first

1. CLASSIFY the op: read / local mutation / github.
2. SIZE+RISK check: destructive? multi-commit? large per M2?
3. Route to the agent above, then resolve the tier.
4. DESTRUCTIVE ops ALWAYS carry the safety contract (S1 backup, S6 verify) from
   `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`; the agent applies it. Only a change to
   a protected branch without a pull request also needs the human-confirm gate.

## Compact-return contract

Every delegated worker returns ONLY a 5-line summary + the absolute findings-file path - never diff
hunks, file contents, or stack traces. The caller ingests the conclusion, not the churn. A context
that cannot launch agents returns `NEEDS_CONTEXT` instead (N4 in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md`).
