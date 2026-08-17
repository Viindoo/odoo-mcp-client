<!-- SSOT snippet. The single home for the integration-loop + saga/rollback contract shared by
     every integration-loop owner in odoo-ai-agents. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md.
     Dependency direction: git-mutation SAFETY mechanics (backup-before, tree-identity-verify-after,
     human-confirm gate, worktree-lock) live in git-toolkit's provider contract
     (plugins/git-toolkit/snippets/git-safety-contract.md), NOT restated here. odoo-ai-agents
     (consumer) may point at git-toolkit (provider); never the reverse. -->

# Integration-loop + saga/rollback contract (SSOT)

An integration loop builds ONE integration branch from N independently-produced work-items (WIs):
for each WI, in node-DAG dependency order, cherry-pick its commit(s) onto the integration branch and
re-run the repo verify command. The branch must never be left half-built: a failure mid-loop is
rolled back or resumed deterministically, never left ambiguous.

## Who owns an integration loop (consumers of this file)

These owners run an integration loop and reference THIS file instead of restating it:

- `run-harness` - the **canonical per-node integration consumer** and SOLE owner (no separate
  git-executor skill exists): it forks ONE `run-integration` branch from base at run start
  (`run-harness/SKILL.md` § Run start); every source-writing node's worktree forks from it, and
  this saga cherry-picks each node's returned commit, in node-DAG order, onto run-integration
  before moving to the next ready node. Review and regression verification are ordinary PLAN
  nodes (dispatched to `odoo-code-review` / `odoo-instance`), not a driver-owned close step.
  There is NO per-node PR: the terminal `integrate` node squashes run-integration + opens the ONE
  per-repo PR once every non-land-tail node in that repo is terminal AND a DONE `odoo-instance`
  node covers the repo's coding nodes (`run-harness/SKILL.md` § integrate readiness + §
  `integrate` node dispatch).
- The PEER orchestrators, each owning its own loop plus a main-context human-confirm gate:
  `odoo-forward-port`, `odoo-modules-upgrade`, `odoo-git-rebase`.
- `odoo-planning` - references this contract so the plan it emits reserves the rollback/resume
  behavior the executor will run; planning does not run the loop itself.

## Saga / rollback (the load-bearing contract)

The executor runs the loop as a saga - every applied step is individually reversible, and an
unrecoverable failure unwinds to a known-clean point:

1. **Record the pre-node SHA.** Before cherry-picking a node's commit, record the integration
   branch's tip SHA (the pre-node SHA). This is the clean-abort anchor for that node's cherry-pick.
2. **Checkpoint after each success.** After each cherry-pick whose post-pick verify PASSES, write
   a checkpoint manifest entry: the WI id, the resulting integration SHA, and the verify result.
   The most recent entry is the resume anchor.
3. **On an unrecoverable failure** - a cherry-pick that cannot be resolved to intent, or a
   post-pick verify that cannot be made to pass within the loop's bound - do EXACTLY ONE of:
   - **Clean abort:** abandon the run-integration WORKTREE (git-ops `worktree remove`) and
     re-provision a fresh one, re-forking at the pre-node SHA (step 1). The node made no net
     change; report the failing WI and why.
   - **Resume from checkpoint:** abandon and re-provision, re-forking at the last PASSING
     checkpoint SHA (step 2), keeping work that already integrated cleanly; report the failing WI
     and stop before it.

   This is a worktree ABANDON + RE-FORK, never a git reset --hard against a live worktree (§
   Git-mutation safety below - this distinction keeps the per-node advance genuinely autonomous).
   Never leave a half-built integration branch (a cherry-pick applied but unverified, or conflict
   markers in the tree). Always report which WI failed and which outcome (abort | resume) was
   taken.

When a repo has exactly one source-writing node (enum owner:
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Single-unit collapse)
the saga reduces to the integration branch's own history: record the pre-node SHA (step 1), write
NO per-node checkpoint (step 2), and clean-abort (worktree abandon + re-fork) to that SHA on
failure.

**Verification is its own plan node, not a driver-owned close step.** The regression suite that
must be GREEN before `integrate` opens runs as an ordinary `odoo-instance` plan node, scoped by
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`; a red verdict fails that node -
`run-harness` never opens a repo's PR without a DONE verification node on `integrate`'s dependency
path (`run-harness/SKILL.md` § integrate readiness).

## Git-mutation safety - POINT, do not restate (dependency direction)

The worktree abandon+re-fork, the cherry-pick, the branch moves, and the closing squash/push are
GIT MUTATIONS whose safety mechanics are owned by git-toolkit's provider contract - not restated
here. The executor (or the git-toolkit operator it delegates to) MUST honor
`plugins/git-toolkit/snippets/git-safety-contract.md`:

- **S1 - backup before any destructive op.** The terminal squash records its S1 backup ref before
  rewriting (`run-integration.md` § Squash Tree-Identity Recipe). The saga rollback needs no S1
  backup - it is not a destructive op (see below).
- **S6 - tree-identity verify after a rewrite.** The terminal squash that closes the RUN is
  proven byte-identical to the integrated tree before the fresh first push.
- **S9 - worktree-lock / principal-checkout-lock.** Every mutation runs in a dedicated worktree;
  the primary checkout never leaves its principal branch. The saga rollback's re-provisioned
  worktree honors this the same as any other mutation.

**Saga rollback fires no destructive-confirm gate.** The saga unwind (clean-abort |
resume-from-checkpoint) is a `worktree remove` + a fresh `worktree add` re-forking run-integration
at the anchor SHA (the pre-node SHA, or the last passing checkpoint SHA) - never a `git reset
--hard` against a live worktree, and nothing unique is discarded: run-integration is disposable
and never-pushed, and every commit up to the anchor stays reachable on its own source branch.
`worktree add`/`worktree remove` is an ordinary, ungated mutation verb
(`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § No LEAF-worker git), distinct from the
8-item destructive gate list. So a mid-node failure does NOT stop for human confirmation -
drive-to-done continues autonomously (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` §
Gate-tier resolution). The terminal closing push is a fresh FIRST push of the never-pushed
run-integration branch (non-force, no history rewrite on any remote branch) - also NOT a
destructive op, also firing no confirm gate; it runs as part of drive-to-done. The only
human-gated LANDING is the downstream outward MERGE (odoo-pr-monitoring's merge approval gate).
odoo-ai-agents (consumer) pointing at git-toolkit (provider) is the legal direction; git-toolkit
never names a consumer.

## Recording

Record the pre-node SHA, every checkpoint entry, and the abort/resume decision in the run's worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) so a later phase or a resumed session can
see why the integration branch sits where it does.
