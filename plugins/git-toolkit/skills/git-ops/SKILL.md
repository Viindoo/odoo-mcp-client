---
name: git-ops
description: >-
  Universal front door for ALL git and GitHub work, run in a delegated context. Fires on:
  status/log/diff/blame/bisect, branch/tag/worktree, fetch/pull/merge/cherry-pick, rebase,
  forward-port/backport, conflict resolution, history rewrite
  (rebase -i/squash/split/amend/reset/filter-repo), force-push, recovery (reflog/ORIG_HEAD/stash),
  large-diff analysis at scale, AND GitHub PR/issue/review/release/CI/fork, OR a pasted GitHub
  PR/issue URL (diff/CI/metadata, merge, compare). Vietnamese: "rebase nhánh", "gộp commit",
  "sửa lịch sử git", "giải quyết xung đột", "xóa commit", "khôi phục", "mở/review/merge PR",
  "tạo release", "dán link PR/issue". For a domain-specific flow (a framework's
  rebase/forward-port/cluster-upgrade orchestrator) a domain front-door may wrap this toolkit ->
  defer to it when installed
---

# git-ops - the universal git/github front door

Any git or GitHub need routes through here. The contract: git churn happens in a delegated or
inline-bounded context so the CALLER'S context stays clean, code is NEVER lost, and the work scales
from a few lines to thousands of files. GitHub work prefers the GitHub MCP, falling back to `gh`.

## Step 1 - classify the op

Bucket the request into one of: READ (status/log/diff/blame/bisect-read), REVERSIBLE-WRITE
(fetch/pull-rebase/merge/cherry-pick/branch/tag/worktree/non-force push/forward-port/backport),
DESTRUCTIVE-REWRITE (rebase -i/squash/split/amend/reset/filter-repo/force-with-lease), or GITHUB
(PR/issue/review/release/CI/fork).

## Step 2 - route by the delegation decision

Apply `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation-decision.md`. Pick ONE of three modes by
OUTPUT SIZE and RISK (never step count):

1. **INLINE** - bounded-output, low-risk single op (`git status`, `git log -n`, `git show --stat`,
   ref/branch existence, `git diff --stat`/`--name-only`): run the safe command directly. NEVER
   inline unbounded output (full PR body, file contents, a full diff) - "read one PR" is DELEGATE.
2. **SINGLE-DELEGATE** - one medium op (rebase, cherry-pick range, analyze one diff, PR
   review/create, issue triage): cold-spawn ONE leaf - READ cognition ->
   `git-surveyor` (read-only); local mutation (reversible OR destructive) -> `git-operator` (carries
   the safety contract); GitHub API -> `github-operator` (MCP-first / gh-fallback). Resolve the
   model tier from `${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md` (single-delegate op-class
   table, first-match-wins); pass it as the Agent-tool `model` param AND put
   `DISPATCH MODEL: <tier>` as the first line of the brief.
3. **PHASED-PIPELINE** - large/complex (>500 files OR >10k LOC OR multi-commit rewrite OR
   thousand-file backport, per `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md` M2):
   cold-spawn `git-pipeline-lead` (opus). It runs P1 map -> P2 evaluate -> P3 strategy +
   HUMAN-CONFIRM -> P4 execute -> P5 verify below the caller, and returns only the final result.
   P3 strategy and the human-confirm gate are the LEAD's job, not the surveyor's.

Fallback: if THIS context cannot cold-spawn (no Agent tool), degrade SINGLE-DELEGATE ->
INLINE-with-contract per `${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N4 - never fail
silently.

## Step 3 - apply the safety contract to anything destructive

Every destructive op carries the full safety contract in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md` (S1-S8 + 8-item human-confirm gate),
regardless of mode. A destructive op reaches a worker only WITH the human confirmation in its
brief; otherwise STOP at the gate.

## Step 4 - scale discipline

For any large change, obey `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`: read
`--name-only`/`--numstat` summaries first, cluster by module, delegate per cluster, never read a
huge diff whole. Use sparse-checkout / partial-clone / LFS for huge repos.

## Step 5 - GitHub interface

GitHub ops use `${CLAUDE_PLUGIN_ROOT}/snippets/github-mcp-first.md`: the
`mcp__plugin_github_github__*` tools are PRIMARY; `gh` is the fallback; never both for one op; note
`DONE_WITH_CONCERNS` if `gh` was used.

## Step 6 - commits

Any commit this skill's workers create follows
`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`: detect the repo's convention, state the
BUSINESS outcome in the subject (WHAT/WHY not HOW), keep 50/72 limits, sign off (`-s`) when DCO is
required.

## Out of scope - route elsewhere

| Situation | Route to |
|---|---|
| A domain-specific same-series rebase pipeline | that domain's rebase front-door |
| Porting code ACROSS major versions as a domain pipeline | that domain's forward-port front-door |
| Upgrading a module cluster to a new major series | that domain's upgrade front-door |

## Detailed recipes (references)

Load the matching reference only when the op calls for it - they are deterministic prose recipes,
not separately-triggered skills:

- `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/large-change-pipeline.md` - the P1-P5 phased
  recipe with per-phase model + dispatch briefs.
- `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/history-rewrite.md` - rebase-i/squash/split/
  amend/reset/filter-repo recipes with backup + verify + human-confirm.
- `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/conflict-resolution.md` - merge/rebase/
  cherry-pick conflict strategy, rerere, abort flows.
- `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/github-pipeline.md` - PR review / issue triage /
  release recipes, MCP-first.
- `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/commit-convention-general.md` and
  `commit-convention-odoo.md` - the two commit standards loaded by the detection protocol.
