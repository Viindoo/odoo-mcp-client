<!-- SSOT snippet. The single home for the integration-loop + saga/rollback contract shared by
     every integration-loop owner in odoo-ai-agents. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md.
     Dependency direction: the underlying git-mutation SAFETY mechanics (backup-before,
     tree-identity-verify-after, human-confirm gate, worktree-lock) are NOT restated here - they
     live in git-toolkit's provider contract (plugins/git-toolkit/snippets/git-safety-contract.md).
     odoo-ai-agents (consumer) may point at git-toolkit (provider); never the reverse. -->

# Integration-loop + saga/rollback contract (SSOT)

An integration loop builds ONE integration branch from N independently-produced work-items (WIs):
for each WI in module-DAG / wave order, cherry-pick its commit(s) onto the integration branch and
re-run the repo verify command. The branch must never be left half-built - a failure mid-loop is
rolled back or resumed deterministically, never left in an ambiguous partial state.

## Who owns an integration loop (consumers of this file)

These owners run an integration loop and reference THIS file instead of restating it:

- `run-harness` - the **canonical between-wave integration consumer** and SOLE owner (there is no
  separate git-executor skill): it forks ONE `run-integration` branch from base at run start, then
  per wave forks the module worktrees from it (Block 2W lineage), cherry-picks each module's commit in
  module-DAG order under this saga onto run-integration, runs the integrated cross-cutting review +
  cumulative close-gate, and AUTO-ADVANCES to the next wave. There is NO per-wave PR: after the FINAL
  wave the terminal `integrate` land-tail squashes run-integration + opens the ONE run-level PR (see
  `run-harness/SKILL.md` § Between-wave integration + § `integrate` node dispatch).
- The PEER orchestrators, each owning its own loop plus a main-context human-confirm gate:
  `odoo-forward-port`, `odoo-modules-upgrade`, `odoo-git-rebase`.
- `odoo-planning` - references this contract so the plan it emits reserves the rollback/resume
  behavior the executor will run; planning does not run the loop itself.

## Saga / rollback (the load-bearing contract)

The executor runs the loop as a saga - every applied step is individually reversible, and an
unrecoverable failure unwinds to a known-clean point:

1. **Record the pre-wave SHA.** Before the first cherry-pick of a wave, record the integration
   branch's tip SHA (the pre-wave SHA). This is the clean-abort anchor for the whole wave.
2. **Checkpoint after each success.** After each cherry-pick whose post-pick verify PASSES, write
   a checkpoint manifest entry: the WI id, the resulting integration SHA, and the verify result.
   The most recent entry is the resume anchor.
3. **On an unrecoverable failure** - a cherry-pick that cannot be resolved to intent, or a
   post-pick verify that cannot be made to pass within the loop's bound - do EXACTLY ONE of:
   - **Clean abort:** abandon the run-integration WORKTREE (git-ops `worktree remove`) and
     re-provision a fresh one, re-forking the run-integration branch at the pre-wave SHA (step 1).
     The wave made no net change; report the failing WI and why.
   - **Resume from checkpoint:** abandon the run-integration worktree and re-provision a fresh one,
     re-forking the branch at the last PASSING checkpoint SHA (step 2), keeping the work that
     already integrated cleanly; report the failing WI and stop before it.

   This is a worktree ABANDON + RE-FORK, never a git reset --hard against a live worktree - see
   § Git-mutation safety below for why that distinction is load-bearing (it is what keeps the
   between-wave advance genuinely autonomous). Never leave a half-built integration branch (a
   cherry-pick applied but unverified, or conflict markers in the tree). Always report which WI
   failed and which outcome (abort | resume) was taken.

For a wave whose `topology` is `single` (enum owner: `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Topology values) the saga reduces to the integration branch's own history: record the pre-wave SHA (step 1), write NO per-module checkpoint (step 2), and clean-abort (worktree abandon + re-fork) to that SHA on failure.

**Wave-closing verify = the CUMULATIVE suite.** The FINAL verify that closes a wave (before the wave
AUTO-ADVANCES) runs the cumulative run-set (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/cumulative-test-scope.md`), not just the touched module; a red
cumulative suite is unrecoverable within the loop's bound -> clean-abort or resume-from-checkpoint,
and NEVER auto-advance (nor open the run's ONE PR) on red.

## Git-mutation safety - POINT, do not restate (dependency direction)

The worktree abandon+re-fork, the cherry-pick, the branch moves, and the closing squash/push are
GIT MUTATIONS. Their safety mechanics are owned by git-toolkit's provider contract - this file does
NOT restate them. The executor (or the git-toolkit operator it delegates to) MUST honor
`plugins/git-toolkit/snippets/git-safety-contract.md`:

- **S1 - backup before any destructive op.** The terminal squash (the one rewrite this loop performs)
  records its S1 backup ref before rewriting (`wave-integration.md` § Squash Tree-Identity Recipe).
  The saga rollback no longer needs an S1 backup - it is not a destructive op (see below).
- **S6 - tree-identity verify after a rewrite.** The single terminal squash that closes the RUN (once,
  after the final wave) is proven byte-identical to the integrated tree before the fresh first push
  (the executor's squash gate).
- **S9 - worktree-lock / principal-checkout-lock.** Every mutation runs in a dedicated worktree;
  the primary checkout never leaves its principal branch. The saga rollback's re-provisioned
  worktree honors this the same as every other mutation.

**Saga rollback fires no destructive-confirm gate, by construction - not by exemption.** The saga
unwind (clean-abort | resume-from-checkpoint) is a `worktree remove` + a fresh `worktree add` that
re-forks run-integration at the anchor SHA (the pre-wave SHA, or the last passing checkpoint SHA) -
it never invokes a git reset --hard against a live worktree. git-toolkit's destructive human-confirm
gate (`git-safety-contract.md` item 4) names git reset --hard specifically because it can discard
uncommitted work with no other copy; here there is nothing unique to discard: run-integration is a
disposable, never-pushed, run-scoped branch, the anchor SHA and every cherry-picked commit up to it
remain fully reachable (each module's own commits still live independently on that module's own
branch, untouched by this rollback), and `worktree add`/`worktree remove` is an ordinary, ungated
mutation verb (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § No LEAF-worker git lists it among
the routine git-ops verbs, distinct from the 8-item destructive gate list). This is WHY the
between-wave advance can stay a genuinely autonomous L1 drive-to-done
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution, "NO per-wave stop"): the
one operation that could have forced an unplanned human stop never reaches a gated op in the first
place, so there is exactly ONE decidable conclusion for an agent hitting a mid-wave failure - it does
NOT stop for human confirmation. The terminal closing push is, separately, a fresh FIRST push of the
never-pushed run-integration branch (non-force, no history rewrite on any remote branch) - also NOT a
destructive op, also firing no confirm gate; it runs as part of drive-to-done. The only human-gated
LANDING is the downstream outward MERGE (odoo-pr-monitoring's L2-merge-gate). odoo-ai-agents
(consumer) pointing at git-toolkit (provider) is the legal direction; git-toolkit never names a
consumer.

## Recording

Record the pre-wave SHA, every checkpoint entry, and the abort/resume decision in the run's worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) so a later phase or a resumed session can
see why the integration branch sits where it does.
