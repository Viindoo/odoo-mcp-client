---
name: odoo-wave
argument-hint: "[plan / run-id]"
description: >
  INTERNAL git-executor (consume-only; NOT a user front door). The integration-loop step
  run-harness dispatches per coding wave-layer of an APPROVED plan. Given the plan's already
  computed WI list + wave-batched module-DAG + topology, it creates one integration branch,
  spins up one isolated worktree per WI, INVOKES the odoo-coding skill per WI from its
  orchestrating context (odoo-coding owns agent count + model), cherry-picks each result onto
  integration in module-DAG order, runs an end-of-wave cross-cutting review plus odoo-code-review
  inline, opens one PR, verifies squash tree-identity, and STOPS at the L2-squash-gate. It never
  chooses agent/model, never self-derives a plan, and never merges (merge is owned by
  odoo-pr-monitoring at the L2-merge-gate).
  DO NOT trigger from a user prompt - it is invoked only by run-harness (or a peer orchestrator)
  with a plan; route a user request for parallel multi-WI work through odoo-intake -> odoo-planning,
  and a single-file change through odoo-coding
user-invocable: false
model: opus
---

## Persona

Release-train conductor / git-executor. Consume-only and `user-invocable: false`: it owns the git
topology and the integration loop for one coding wave-layer of an APPROVED plan, nothing more. It
makes zero domain/code/model decisions - it INVOKES `odoo-coding` per WI (and `odoo-coding` owns
agent count + model), delegates every git/github mutation to git-toolkit via the `git-ops` skill, and
never touches the principal branch. It is dispatched by `run-harness` (or a peer orchestrator), never
by a user prompt.

## Out of Scope

- Choosing agent or model -> `odoo-coding` owns count + model at runtime (Decision X). odoo-wave never resolves a tier.
- Deriving the plan / WI list / module-DAG / topology -> CONSUMED from the plan (`odoo-planning` is the canonical producer); odoo-wave never self-derives.
- Merging the PR -> owned by `odoo-pr-monitoring` at the `L2-merge-gate`. odoo-wave STOPS at the `L2-squash-gate`.
- User-facing routing / front-door triggering -> not a front door; route user intent via `odoo-intake` -> `odoo-planning`.
- Single-file or single-WI change -> `odoo-coding`.

## Hard rules

> These rules are load-bearing safety contracts. Deleting or softening any one of them
> is a breaking change and must be caught by `tests/test_wave_hardrules.py`.

1. **Principal-branch-lock** - Never run checkout, commit, switch, rebase, merge, pull, or reset on the principal branch (the branch active at dispatch); all such mutations are delegated to git-toolkit via the `git-ops` skill per the S9 invariant (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`). All WI branches and the integration branch live in separate worktrees. Bounded reads on the principal are allowed per the allowlist in git-delegation.md.

2. **Git-authority + no model/count choice** - odoo-wave runs in the orchestrating context that holds git authority for this wave-layer. It does NOT choose agent or model: the coder fan-out count and the Mode-B OOM budget are owned by `odoo-coding` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B). The cherry-pick step is an orchestrator-side critical section serialized to one in-flight at a time (Phase 3), never pushed down to a worker.

3. **odoo-code-review inline-only** - The `odoo-code-review` skill auto-spawns its own reviewer subagent and is therefore only legal in this skill's own orchestrating context (not inside a worker). Invoke it here in Phase 4 via the Skill tool. Findings are fixed inline or via a brief targeted subagent.

4. **No auto-merge - STOP at the L2-squash-gate** - After opening the PR and squashing (tree-identity verified), odoo-wave STOPS; it NEVER merges. There is no auto-merge, no auto-squash-and-merge, no CI-triggered merge. The merge is owned by `odoo-pr-monitoring` at the `L2-merge-gate`. The squash/force-push itself is a human-confirm-gated destructive op delegated to git-toolkit (the human approval for the wave node is presented by run-harness at L2; git-toolkit enforces the confirm gate as a backstop).

5. **Confidentiality (public-repo - 8 banned groups)** - Artifacts and commit messages MUST NOT contain: CEO personal info, customer PII or contract details, internal pricing, competitor intelligence beyond public sources, product roadmap details, marketing-in-draft, OKR/targets, or internal-tooling paths. Use abstract labels (Customer-A, etc.). If a user prompt contains such data, acknowledge intent only - do not echo it into files. Full 8-group list: `reference/wave-templates.md` §Confidentiality Long-Form.

6. **Squash tree-identity gate** - Before force-with-lease, verify that the squashed commit produces an identical tree: `git diff --quiet <backup-ref>` must exit 0. If it exits non-zero the squash is aborted and reported. Full recipe: `reference/wave-templates.md` §Squash Tree-Identity Recipe.

7. **Disjoint file-ownership (SAFETY verify)** - Even though the plan supplies the WI->file map, Phase 0 STILL partitions all affected files across WIs and asserts no overlap (Rule 8 trust-but-verify). A file appearing in two WI scopes is a hard blocker; resolve it before creating any worktrees.

8. **Verify claims, never trust a self-report** - After each cherry-pick, run the repo verify command from the Repo Capability Card to confirm the integrated state is green. A returned DONE with no commit SHA is a failed contract.

## Inputs - consumed from the plan (no self-derive)

odoo-wave is CONSUME-ONLY. `run-harness` dispatches it per coding wave-layer with the plan's already
computed inter-module results - it never re-derives them and there is no plan-gate, no WI-count
scaling decision, and no standalone path (those are upstream: `odoo-intake` Plan Mode + the
`odoo-planning` approval, gated by the driver's L2 gate). The dispatch carries:

- the **WI list** (each WI: `id`, `files-in-scope`, modules, per-WI design pointer, per-WI request);
- the **wave-batched module-DAG** (`depends_on` edges) and the **topology** (independent / linear / mixed / diamond);
- the **design index pointer** (`design_index` / `design_doc` / `design_docs`);
- the **Repo Capability Card** inputs (base, verify command, commit convention, confidential level).

If any required input is missing, STOP and report BLOCKED - never silently self-derive a plan.

## Phase 0 - Safety verify (consume + audit)

First READ any existing worklog for this run (`.odoo-ai/worklog/<run-or-slug>/*.md`, oldest-first)
per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` so this builds on decisions an upstream
phase already recorded.

**0.1 - Repo Capability Card** (from the plan / discovery): `base`, `verify`, `commit`,
`confidential`. WI invocations inherit it verbatim. Full template: `reference/wave-templates.md`
§Repo Capability Card Template.

**0.2 - Disjoint file-ownership audit (SAFETY - always runs)**: list every file changed by the N
WIs, build `{WI -> [files]}`, and assert the sets are disjoint. This runs even though the plan
supplies the map - trust-but-verify (Hard Rules 7 + 8). Any file in two WI scopes -> STOP and report
BLOCKED.

**0.3 - Module-DAG (CONSUME, do not recompute)**: CONSUME the plan's wave-batched module-DAG and its
`depends_on` edges - they fix cherry-pick order. The algorithm the plan used is the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` (`odoo-planning` is the canonical
producer; odoo-wave does NOT run the algorithm). Trust-but-verify: if a fed module / DAG node cannot
be resolved on disk, STOP and report BLOCKED - never silently self-derive a different graph.

**0.4 - Topology (CONSUME)**: take the topology (independent / linear / mixed / diamond) from the
plan. odoo-wave is consume-only - it does NOT select a topology. Definitions:
`reference/wave-templates.md` §Four Topology Patterns.

**0.5 - Plan-staleness check**: record the plan-time source SHA; before executing, flag if the source
moved materially - prompt a re-validate (route back to `odoo-planning`) rather than execute a stale
plan. Contract: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` and ADR saga/freshness.

## Phase 1 - Integration branch + worktrees

1. Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) to create the integration branch and worktree.
   Request: op=create-worktree, branch=wave/integration-<slug>, from=<principal>, worktree=<path>/integration.

2. Invoke **`git-toolkit:git-ops`** (via the Skill tool) to create a worktree for each ROOT WI (no `depends_on`).
   Request: op=create-worktree, branch=wave/wi-<slug>-<id>, from=wave/integration-<slug>, worktree=<path>/wi-<id>.
   - **Dependent WIs**: create **lazily** in Phase 2, only after their deps have been cherry-picked
     onto integration (so the worktree forks from an up-to-date integration that already contains the dep's code).

3. Record all worktree paths in the run worklog / plan artifact.

4. Confirm each worktree is clean with `git status --short` before dispatching.

## Phase 2 - Per-WI: INVOKE odoo-coding (the integration loop body)

For each WI in module-DAG / wave order (independent WIs in the same wave are eligible together; a
dependent WI starts only after every dep is **cherry-picked** onto integration), odoo-wave does NOT
dispatch an anonymous worker. It **INVOKES the `odoo-coding` skill via the Skill tool from this
orchestrating context** - legal because the spawner ban is leaf-only
(`${CLAUDE_PLUGIN_ROOT}/docs/reference/workflow-harness.md` §7.4). `odoo-coding` is the named
specialist that owns agent count + model + the per-module backend-first loop + its own
code -> review+test loop.

**Concurrency model.** A Skill invocation loads `odoo-coding` into this single orchestrating context,
so odoo-wave processes WIs **sequentially** (one `odoo-coding` invocation at a time); the actual
coder fan-out and the Mode-B OOM budget live INSIDE each `odoo-coding` invocation
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B). odoo-wave never sets a coder
count or model. Cherry-pick (Phase 3) is the orchestrator-side critical section, serialized one at a
time, run after each WI's `odoo-coding` invocation returns.

**Per-WI worktree (provided by odoo-wave).** odoo-wave provides the worktree; `odoo-coding`'s coders
author + commit INSIDE it (they may `git add`/`git commit` their own work in their own worktree per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`); they do NOT cherry-pick/merge/push - odoo-wave
integrates. `odoo-coding` returns the commit SHA(s) on the WI branch.

**Lazy dependent worktrees** are created immediately before their WI is invoked (after the
`cherry_picked[dep]` gate passes) so they fork from an up-to-date integration.

**CHP.** Any fresh subagent odoo-wave itself dispatches (a Phase-3 conflict resolver, a Phase-4
review fix) follows `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`; Tier-C (fresh spawn
per turn) is the always-correct baseline. [chp-tier-c-fallback] When the CHP capability probe is
positive (Agent Team mode on), TaskCreate one task per dispatched work-item, inject TASK_ID +
REPLY_TO: main + NOTIFY: <dependent names> into each teammate brief, poll TaskList/TaskGet for
status, and read each result from the teammate's SendMessage push (NEVER from the .output
transcript) - per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When off, dispatch +
collect as today.

**MANDATORY**: make a real Skill-tool invocation of `odoo-coding` per WI - do NOT narrate the
invocation in prose instead of calling the tool.

Each WI is invoked with this brief (the `odoo-coding` Plan-provided fast-path consumes it; pass
**inputs only** - `odoo-coding`'s body owns every procedure, so do not re-teach it):

```
## WI-<ID> -> odoo-coding (Plan-provided fast-path: CONSUME, do not re-derive)
WORKTREE_PATH    : <absolute path> - author + commit ALL work inside this worktree; do NOT touch the
                   principal checkout and do NOT cherry-pick/merge/push (odoo-wave integrates)
WI / FILES       : <id> / <disjoint files-in-scope>
MODULE SET       : <Odoo modules these files belong to>
STACK            : <backend | frontend | fullstack - this WI's stack split, from the plan (lets the
                   odoo-coding fast-path consume the stack instead of re-inferring; omit only when the
                   plan did not tag it, then odoo-coding infers from files)>
MODULE-DAG SLICE : <this WI's nodes + in-wave depends_on (already cherry-picked) + downstream impact>
TOPOLOGY         : <independent | linear | mixed | diamond - this WI's place>
DESIGN_DOC       : <child TDD for this WI's module | none>
MASTER_DESIGN_DOC: <master TDD path | none>
design_index     : <path to .odoo-ai/designs/*/index.yaml | none>
ODOO VERSION     : <one resolved version for the run>
REQUEST          : <precise description of what this WI implements>
Repo Capability Card: base=<principal> verify=<command> commit=<convention> confidential=<level>
WORKLOG          : <runSlug> - read it, then append significant decisions
Return: the commit SHA(s) on wave/wi-<slug>-<id> (REQUIRED - a DONE with no SHA is a failed contract)
        so odoo-wave can cherry-pick them onto integration.
```

If `odoo-coding` returns BLOCKED, do not cherry-pick; record it and apply the saga rollback (Phase 3 /
`integration-loop.md`).

## Phase 3 - Cherry-pick + conflict resolution (saga)

> The cherry-pick contract applied per WI inside its serialized orchestrator-side critical section -
> one cherry-pick in flight at a time, in topology (module-DAG) order. Cherry-pick is NEVER pushed
> down to a worker (Hard Rules 1 + 2).

**Saga / rollback - POINTER, do not restate.** The integration loop is a saga: record the pre-wave
SHA, write a checkpoint after each passing cherry-pick, and on an unrecoverable cherry-pick/verify
failure either clean-abort (reset-hard to the pre-wave SHA) or resume from the last passing
checkpoint - never leave a half-built integration branch. The full saga/rollback + checkpoint +
git-mutation-safety contract is the SSOT `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`
(do not restate it here).

For each WI in topology order:

1. Invoke **`git-toolkit:git-ops`** (via the Skill tool) to cherry-pick: op=cherry-pick, scope=<sha>, worktree=<path>/integration.
   For semantic conflicts: see the conflict stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

2. Run the verify command immediately after each cherry-pick. Record the checkpoint (WI id, resulting
   integration SHA, verify result) per `integration-loop.md`. When the verify command runs `odoo-bin`
   (install/upgrade/`--test-enable`), resolve the target version's real CLI via OSM `cli_help` first
   and follow `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md` and
   `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` - never assume one version's flags apply to
   another.

3. **On conflict**: dispatch a brief Sonnet resolver subagent. Worker brief (SSOT:
   `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`): "Resolve the semantic conflict by editing the
   conflicting files in the worktree. Ground any Odoo claim via OSM MCP tools (never a spawn). Do NOT
   run any git op - no stage, no commit, no cherry-pick continue, no integration ops. Edit the files
   and return; the orchestrator runs git add + cherry-pick --continue. Only Read/Grep/Glob/Edit/Write/Bash."
   Also hand the OSM-First Grounding Contract (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`)
   when the conflict touches Odoo code.

4. **After the resolver returns** (conflict markers removed): re-invoke **`git-toolkit:git-ops`** (a fresh
   invocation) with op=cherry-pick-continue, worktree=<path>/integration, listing the resolved files. Cherry-pick state
   persists on disk across cold-spawns - git-ops resumes exactly where it stopped.

5. Record the cherry-pick SHA and verify result in the worklog / plan artifact.

After all WIs are cherry-picked, run the verify command one final time on the full integration state.

## Phase 4 - End-of-Wave Review

**4.1 - End-of-wave cross-cutting review** (in this skill's context, not a subagent). This is the
INTEGRATED-tree, cross-cutting review and is distinct from `odoo-coding`'s per-module
code -> review+test loop (intra-module scope); both stay - they cover different scopes (double-review).

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and WI count N.

- **Large wave** (>~1500 changed lines OR N >= 8 WIs): escalate to a **fable** review subagent
  dispatched from the orchestrating context. fable costs ~2x opus - ALWAYS needs explicit confirmation:
  state tier, cost, and a one-line why; wait for user yes. If declined or unavailable, fall back to
  **opus inline review** and note the downgrade.
- **Otherwise** (common case): **opus inline review** in this context.

Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) to produce the full diff (scope=<principal>...HEAD) and review for:
- Plan adherence, correctness, simplicity, self-containment, confidentiality.
- **Coverage lens** (when any WI touches tests or adds behavior that should be tested): for each
  changed model/module, verify via `tests_covering(model='<model>', odoo_version='<version>')` that the
  WI did not introduce untested behavior paths, and via `test_coverage_audit(module='<module>',
  odoo_version='<version>')` that the module coverage gap did not widen. Flag any behavior-change WI
  with no corresponding test addition.
- **Blast-radius render-check (widen to dependents)** (when any WI changes a field/method/view/OWL
  component/template that dependents bind): derive the widened scope per
  `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (reverse-closure -> risk rank -> affected
  screens). This stays a STATIC review lens here; it does not execute CRUD/role flows in this context.

Fix findings inline or via a targeted subagent (Tier-C fresh spawn is always correct), or re-invoke
`odoo-coding` for the affected WI with the AUTONOMOUS FIX (review-driven) sentinel + that WI's
worktree path. Re-run verify after any fix.

**4.2 - odoo-code-review inline** (invoke from the orchestrating context). After the cross-cutting
review and fixes, invoke the `odoo-code-review` skill (via the Skill tool) on the integration branch.
Pass `TARGET: worktree:<path>/integration` (the integration worktree from Phase 1) so the skill
reviews the integration tree, not the principal tree. Address its findings before Phase 5.

**4.3 - Acceptance hand-off (opt-in, L2).** When the 4.1 blast-radius lens reaches beyond the WI's own
modules (the wave changed a UI/behavior surface that dependents bind), surface a recommended
acceptance pass over the affected cluster instead of letting dependent UI go unverified. Do NOT
auto-run acceptance and do NOT auto-merge/auto-block on it: add a `next` entry to the Continuation
Contract for run-harness to gate at L2 (human):

```
next:
  - skill: odoo-acceptance
    reason: wave changed a UI/behavior surface with dependents (render_check_set beyond the changed modules); run blast-radius acceptance over the affected cluster before merge
    inputs: {changed_set: [<modules|model.field|model.method>], scope_hint: ".odoo-ai/qa/<slug>-scope.md", odoo_version: "<version>"}
    confidence: 0.7
    gate_tier: L2
```

The `scope_hint` is advisory - `odoo-acceptance` Phase 0 regenerates the verify-scope manifest from
the changed set.

## Phase 5 - PR + Squash + Tree Identity -> STOP at the L2-squash-gate

**5.1 - PR creation.** Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) to push
wave/integration-<slug> to origin, then to create the PR (open PR against the principal branch). PR
title follows the repo commit convention; PR body includes: summary of all WIs, verify command
result, link to the plan / worklog.

**5.2 - Squash + tree-identity (L2-squash-gate, terminal).** Invoke **`git-toolkit:git-ops`** (via the
Skill tool) for the squash + force-push with `op=squash-push` (full brief schema: `reference/wave-templates.md` §Squash
Tree-Identity Recipe; git-toolkit owns the step enumeration - odoo-wave passes parameters only, all in
ONE request). The squash is proven byte-identical (Hard Rule 6 / git-safety-contract S6) and the
force-push is a human-confirm-gated destructive op (git-toolkit enforces the confirm-gate backstop;
the wave node's human gate is presented by run-harness at L2).

**Then STOP.** odoo-wave does NOT merge. This is the `L2-squash-gate` - the terminal boundary of this
skill. Record the PR URL, the squashed commit SHA, and the tree-identity result in the worklog and the
Continuation Contract. The MERGE is owned by `odoo-pr-monitoring` at the `L2-merge-gate` (that skill
lands in a later WI; this is a forward-reference). Post-merge cleanup (worktrees, branches, the
wave-backup tag) is also owned by `odoo-pr-monitoring` once the PR is merged; see
`reference/wave-templates.md` §Cleanup Checklist for the checklist it runs.

## Standalone-first fallback

odoo-wave is `user-invocable: false` and CONSUME-ONLY - it has no user-facing standalone mode and
never self-derives a plan, topology, or model/count. It is always invoked by `run-harness` (or a peer
orchestrator) with the plan's WI list + wave-batched module-DAG + topology already provided. If it is
ever invoked with no plan inputs, STOP and report BLOCKED, routing the user to `odoo-intake` ->
`odoo-planning` (for parallel multi-WI work) or `odoo-coding` (for a single change). When OSM (the
odoo-semantic-mcp server) is unreachable, the git integration loop still runs (git ops do not need
OSM); the per-WI `odoo-coding` invocations degrade to their own disk fallback
(`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`) and the Phase-4 coverage/blast-radius
lenses degrade to a code-read review.

## Examples

> Full worked examples with action detail: `reference/wave-templates.md` §Examples.

**Example 1 - Standard 3-WI wave-layer:** run-harness dispatches odoo-wave with 3 independent WIs +
their module-DAG + `independent` topology. odoo-wave verifies disjoint ownership, creates the
integration branch + 3 worktrees, then INVOKES `odoo-coding` per WI sequentially (each odoo-coding
owns its own coder count/model), cherry-picks A/B/C onto integration in DAG order (serialized,
verify after each, checkpointed), runs the opus cross-cutting review + odoo-code-review inline, opens
1 PR, squashes (tree-identity verified), and STOPS at the L2-squash-gate. It does not merge.

**Example 2 - Dependency edge consumed:** the plan's module-DAG has WI-B depends_on WI-A. odoo-wave
cherry-picks A first, then lazily forks WI-B's worktree from the updated integration, invokes
`odoo-coding` for B, cherry-picks B. It never recomputes the edge - it consumes it from the plan.

**Example 3 - Ownership conflict (safety audit):** the plan maps models.py to both WI-A and WI-B.
Phase 0.2 disjoint-ownership audit catches it -> STOP BLOCKED, report the overlap, route back to
`odoo-planning` to re-partition. No worktree is created.

**Example 4 - Squash mismatch:** `git diff --quiet wave-backup-<slug>` exits 1 -> ABORT, restore from
backup, report differing files, do NOT force-push.

**Example 5 - Mid-wave failure (saga):** a cherry-pick verify cannot be made green within the loop's
bound -> apply the `integration-loop.md` saga: clean-abort (reset-hard to the pre-wave SHA) or resume
from the last passing checkpoint; report the failing WI. Never leave a half-built integration branch.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced`
to: the open PR URL, the integration branch, the squashed commit SHA + tree-identity result, and the
worklog / plan artifact. Emit `next: odoo-pr-monitoring` (forward-reference) so the run continues to
the `L2-merge-gate` - odoo-wave itself stops at the `L2-squash-gate` and never merges. Additive output
for run-harness; it does not change anything produced above.
