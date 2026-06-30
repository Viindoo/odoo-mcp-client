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

- `odoo-wave` - the git-executor (consume-only; renamed from `wave`): the canonical per-wave
  integration loop, run from its orchestrating context.
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
   - **Clean abort:** reset the integration branch HARD to the pre-wave SHA (step 1). The wave
     made no net change; report the failing WI and why.
   - **Resume from checkpoint:** reset the integration branch HARD to the last PASSING checkpoint
     SHA (step 2), keeping the work that already integrated cleanly; report the failing WI and stop
     before it.

   Never leave a half-built integration branch (a cherry-pick applied but unverified, or conflict
   markers in the tree). Always report which WI failed and which outcome (abort | resume) was taken.

## Git-mutation safety - POINT, do not restate (dependency direction)

The reset-hard, the cherry-pick, the branch moves, and the closing squash/push are GIT MUTATIONS.
Their safety mechanics are owned by git-toolkit's provider contract - this file does NOT restate
them. The executor (or the git-toolkit operator it delegates to) MUST honor
`plugins/git-toolkit/snippets/git-safety-contract.md`:

- **S1 - backup before any destructive op.** The pre-wave SHA above is recorded as / alongside the
  S1 backup branch, so a reset-hard is always recoverable.
- **S6 - tree-identity verify after a rewrite.** The squash that closes the loop is proven
  byte-identical to the integrated tree before any force-with-lease (the executor's squash gate).
- **S9 - worktree-lock / principal-checkout-lock.** Every mutation runs in a dedicated worktree;
  the primary checkout never leaves its principal branch.

The reset-hard and the closing push are among that contract's human-confirm-gated destructive ops:
the executor delegates them through git-toolkit
(`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`), which enforces the S1 backup and the
confirm gate as a backstop. odoo-ai-agents (consumer) pointing at git-toolkit (provider) is the
legal direction; git-toolkit never names a consumer.

## Recording

Record the pre-wave SHA, every checkpoint entry, and the abort/resume decision in the run's worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) so a later phase or a resumed session can
see why the integration branch sits where it does.
