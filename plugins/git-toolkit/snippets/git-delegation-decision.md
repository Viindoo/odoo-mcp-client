<!-- SSOT snippet. The single home for the 3-mode execution-routing decision (INLINE /
     SINGLE-DELEGATE / PHASED-PIPELINE) and the compact-return contract. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation-decision.md by skills/git-ops/SKILL.md.
     Edit here only. -->

# Git Delegation Decision (SSOT)

When git/github work arrives, route it to exactly ONE of three execution modes, by OUTPUT SIZE and
RISK, never step count. Goal: keep the caller's context clean by delegating anything heavy, without
over-spawning for one-liners.

## The three modes

### 1. INLINE - bounded-output, low-risk, single op

Run the safe command directly in the current context. No spawn. Use ONLY when the output is bounded
AND the op is low-risk:

- `git status`, `git log -n <small>`, `git show --stat`, branch/ref existence checks,
  `git rev-parse`, `git diff --stat`/`--name-only` (summaries, not content).

NEVER inline unbounded output: a full PR body, file contents, or a full diff. "Read one PR" returns
an unbounded body -> that is DELEGATE, not inline.

### 2. SINGLE-DELEGATE - one medium op

Cold-spawn ONE leaf at the right model with a self-contained brief; it works in its own context,
writes a findings file, and returns a 5-line summary + path. Use for one medium op:

- a rebase, a cherry-pick range, resolving one diff/conflict, ANALYZING a diff, a PR review, a PR
  create, issue triage, a release.
- pick the leaf: read-only cognition -> `git-surveyor`; local mutation (reversible or destructive,
  with the safety contract) -> `git-operator`; GitHub API -> `github-operator`.

### 3. PHASED-PIPELINE - complex / large

Cold-spawn `git-pipeline-lead` (opus); it runs P1-P5 below the caller. Use when the change is LARGE
per `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md` M2 (>500 files OR >10k LOC OR a
multi-commit rewrite OR a thousand-file backport). The lead maps -> evaluates -> strategizes ->
human-confirms (if destructive) -> executes -> verifies, and returns only the final compact result.

## Classify first

1. CLASSIFY the op: read / reversible-write / destructive-rewrite / github.
2. SIZE+RISK check: bounded output? destructive? multi-commit? large per M2?
3. Route: bounded+low-risk -> INLINE; one medium op -> SINGLE-DELEGATE; large/complex ->
   PHASED-PIPELINE.
4. DESTRUCTIVE ops ALWAYS carry the human-confirm gate from
   `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`, regardless of mode.

## Compact-return contract

Every delegated worker returns ONLY a 5-line summary + the absolute findings-file path - never diff
hunks, file contents, or stack traces. The caller ingests the conclusion, not the churn. See the
Agent-unavailable fallback in `${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N4 for when
the spawn tool is missing.
