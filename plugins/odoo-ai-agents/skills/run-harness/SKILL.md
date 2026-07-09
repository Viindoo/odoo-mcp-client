---
name: run-harness
argument-hint: "[run-id]"
user-invocable: false
description: >
  Drive-to-done loop. Walks the RUN-DAG in `.odoo-ai/run-<id>.json` that intake's
  Phase P produced: picks the next ready node, resolves its gate tier (L0/L1/L2), dispatches
  it (Skill-tool a leaf skill | Skill-tool a spawner skill (it fans out its own agent) | hand a
  workflow to workflow-chaining), reads the step's Continuation Contract, updates the blackboard, and
  advances until the run reaches DONE / BLOCKED / NEEDS_CONTEXT. Invoked by intake after a
  RUN-DAG is approved, or to RESUME an existing active run. Never called directly by the user.
  Full schema + diagram: docs/reference/workflow-harness.md §8
model: inherit
---

# run-harness - Drive-to-done loop

## Role

Conductor of a multi-step run. Owns no domain expertise; only reads the blackboard, decides
the next step, dispatches it, and records the result. Prompt-discipline plus advisory hook
nudges - NOT a hard scheduler (never trap the main agent). SSOT for the mechanism:
`docs/reference/workflow-harness.md` §8 - this file is the operating procedure, that is the
contract.

## Out of Scope

- **Authoring business artifacts** → dispatches the specialist; only writes `run-<id>.json`.
- **Planning / serializing the DAG** → intake's Phase P. The driver only *walks* an EXISTING
  `run-<id>.json`; it does NOT ingest a plan `.md` and expand it into nodes. A skill that produces a
  plan (e.g. `odoo-planning`) must route its approved plan to intake Phase P (`next: odoo-intake`),
  NEVER emit `next: run-harness` with only a plan pointer - run-harness is dispatched BY Phase P
  after the run file exists; reaching it before serialization just yields `NEEDS_CONTEXT`.
- **Coercing the main agent** → advisory nudges only (Hard rule #2).
- **Crossing the Odoo↔general boundary** → intake's routing decision.

## Hard rules

1. **Owns the blackboard.** This is the orchestrator that walks the RUN-DAG. It MUST NOT be
   invoked from inside a subagent (it owns the run state and controls dispatch).
2. **Never hard-block the main agent.** This loop is prompt-discipline, not coercion. The
   human + main agent may stop at any time. The Stop/PreToolUse hooks only *nudge* (advisory);
   they never deny a tool call or block a turn-end. (Quality-gate `block` is only ever for a
   subagent, e.g. `enforce-grounding`.)
3. **Only run-harness writes `run-<id>.json`.** Hooks never write it (no write race).
4. **You dispatch; subagents do not.** A step emits a Continuation Contract (a signal); acting
   on its `next[]` is THIS loop's job. Respect the worker-brief contract (`snippets/worker-brief.md`).
5. **L2 is always a human gate.** The autonomy dial can lower L1→auto-pass but can NEVER lower
   L2 (irreversible/outward: instance, git push/merge, send to a third party).
6. **Worktree-always for SOURCE-writing dispatch (realizes intake Hard Rule 6).** Before
   dispatching a node that writes the SOURCE tree (not `.odoo-ai/`; same test as Gate-tier
   resolution), if it has no `WORKTREE_PATH`/`TARGET: worktree:<path>` and its approach is not a
   self-provisioning specialist (SSOT list:
   `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists), INVOKE
   `git-toolkit:git-ops` to create a dedicated worktree/branch, inject its path into the node's
   `inputs`, and `write(RUN)`. NEVER dispatch a source-writing node against the principal checkout.
   A `.odoo-ai/`-only node (e.g. `odoo-code-review` at `TARGET=local`) is NOT provisioned.

## Inputs

- An active `.odoo-ai/run-<id>.json` (serialized by intake Phase P from the approved plan, schema in
  harness §8.3) - run-harness is dispatched only after this file exists; it never receives a raw plan `.md`.
- `autonomy` ∈ {auto (default), step, plan} read from that file.

## The loop

```
load RUN = read(.odoo-ai/run-<id>.json)        # the active run; if several, the one intake just wrote / the user named

while RUN.status == "NEEDS_NEXT":
    if RUN.budget.nodes_run >= RUN.budget.max_nodes:        # runaway guard
        set RUN.status = "BLOCKED"; blocked_reason = "node budget exhausted - human review"; break

    node = pick_ready(RUN)        # READY = every depends_on is DONE; topo-order; tie → highest confidence
    if node is None:              # nothing ready but not all done → cycle / deadlock
        set RUN.status = "BLOCKED"; blocked_reason = "no ready node (dependency cycle?)"; break

    tier = rederive_floor(node)   # NOT raw node.gate_tier - re-assert the floor (see §Gate-tier
                                  # resolution): an `outward` merge | a non-wave instance_touching
                                  # node | a DYNAMIC source-writing node ⇒ L2; a STATIC between-wave
                                  # integration (wave) advance ⇒ L1 (ephemeral instance; the in-context
                                  # L2-squash-gate + downstream merge); else node.gate_tier / registry default.
    if RUN.autonomy == "step": tier = max(tier, "L1")       # --step gates everything ≥ L1
    if tier == "L2":              # ALWAYS human - emit gate, end turn, resume after approve/skip/cancel
        emit_human_gate(node); wait                          # on cancel → mark SKIPPED/stop per user
    elif tier == "L1" and RUN.autonomy != "auto":
        emit_human_gate(node); wait
    # else (L0, or L1 under --auto within budget) → auto-pass; append to gate_log

    node.status = "RUNNING"; write(RUN)
    provision_worktree_if_needed(node)   # Hard rule 6: SOURCE-writing + no worktree + not self-provisioning -> git-ops creates one; inject into node.inputs; write(RUN)
    dispatch(node):                                          # pick by approach_kind
        - skill (leaf)      → Skill tool inline; NL-dispatch is the fallback
        - skill (spawner)   → invoke the SKILL via Skill tool; the skill fans out its
                              own agent (e.g. odoo-code-reviewer) via launch subagent
        - workflow          → hand the YAML name to workflow-chaining
        - wave              → drive the § Between-wave integration procedure for this coding wave
                              node (consume Block 2W lineage; per module INVOKE odoo-coding; the
                              odoo-coder coordinator commits + returns the SHA; cherry-pick + saga;
                              integrated review + cumulative close-gate; ONE squashed PR; STOP at the
                              L2-squash-gate). run-harness owns this directly - there is no git-executor skill.
        - integrate         → invoke git-toolkit:git-ops (push the change's branch + open PR against
                              principal) from main context, then materialize next ->
                              odoo-pr-monitoring @ gate_tier L2 (single outward merge gate)
        - inline            → do the small synth step yourself
    # turn typically ends here for any subagent/agent dispatch; SubagentStop hook nudges resume

    contract = read_continuation_contract(node)              # SPAWNER node (skill invoked in `main`): read its in-context
                                                             # AGGREGATE result inline. LEAF teammate + Agent Team mode: read the
                                                             # contract from the teammate's SendMessage push, NOT the `.output`
                                                             # transcript (Tier-C fallback only). See prose below + agent-team-protocol.md.
    node.contract = contract
    node.produced = contract.produced
    node.status   = map(contract.status)                     # DONE | (FAILED→retry<3 else BLOCKED) | BLOCKED | NEEDS_CONTEXT
    for nx in contract.next:                                 # SUGGEST → CHAIN ; cross-workflow on_complete lands here too
        if nx.confidence >= 0.5 and not duplicate(nx) and within_budget:
            RUN.dynamic_nodes.append(materialize(nx))        # new READY node, depends_on = node;
                                                             # if it is writes-files to source, stamp gate_tier=L2
                                                             # (dynamic source write → always human; never approved)
        else:
            note_as_suggestion(nx)                           # low-confidence / dup → surface to human, do not auto-run
    RUN.budget.nodes_run += 1
    RUN.status = rollup(RUN)                                 # NEEDS_NEXT while any reachable node ≠ DONE
    write(RUN)

# Completion Contract (#8): terminal report with evidence
finalize: RUN.completion = {status, evidence: flatten(all produced), summary}
emit terminal report (DONE | BLOCKED | NEEDS_CONTEXT), one evidence pointer per claim
```

When the CHP capability probe is positive (Agent Team mode on), run-harness `TaskCreate`s one task
per DAG NODE it dispatches (title = node id) and tracks status via `TaskList`/`TaskGet`. It does NOT
spawn named teammate agents - it dispatches each node via Skill-tool inline, a spawner skill (Skill
tool), or workflow-chaining. A spawner-skill node (e.g. odoo-coding) runs in the same `main` context
and is team lead for its OWN teammates (injects their briefs TASK_ID + REPLY_TO: main + NOTIFY,
consumes their pushes); run-harness reads the spawner's in-context aggregate result and does NOT
track the spawner's teammate tasks (single main context - no double-tracking). For a LEAF teammate
dispatched directly, inject its brief and read the result from its SendMessage push (NEVER the
`.output` transcript). Per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When off,
dispatch + collect as today.

## Gate-tier resolution

Per node: `node.gate_tier` (run.json override) → else registry `default_gate_tier`
(`skill_tool_deps.json`). Apply the dial: `--step` raises floor to L1; `--auto` lets L0+L1
auto-pass within budget. **L2 never lowers.** See harness §8.4.

**Source-writing nodes** (targets source tree, not `.odoo-ai/`) - **human gate MUST be at the
driver, before dispatch.** Spawner skills fan out their worker via launch subagent and that subagent
cannot pause for human input; the skill's internal Phase-0 gate is only a safety-net, not the
binding gate. Spawner skills writing only `.odoo-ai/` (`odoo-code-review`, `odoo-ui-review`) need
no extra driver gate beyond registry tier.

A coding wave node's `approach_kind` is `wave`: the node groups one wave's MODULES (with their
module-DAG + topology + `cumulative_modules` + the Block-2W lineage slice) - the outer unit is the
MODULE, not a work-item (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier
decomposition axis). run-harness drives it via § Between-wave integration - it iterates the wave's
modules and invokes `odoo-coding` per module; the work-item is `odoo-coder`'s INTERNAL intra-module
unit and never appears in a run node.

- **Static node** (in the Plan-Mode-approved DAG): Plan-Mode approval IS the human gate →
  auto-pass under `--auto`. A STATIC `wave` (between-wave integration) advance is L1 and DRIVES to
  done: the squash/force-push is the in-context L2-squash-gate (human-confirmed as the wave closes)
  and the only irreversible landing is the downstream `outward` L2-merge-gate, so the driver does not
  re-stop between waves. `--step` re-inserts the between-wave stop: it raises the floor to L1, and an
  L1 node under non-`auto` autonomy emits a human gate.
- **Dynamic node** (materialized at runtime from `next[]` / `on_complete` - never in the
  approved plan): driver MUST emit a preview (`Proposed / Files / OSM / Proceed? (yes / refine /
  cancel)`) and **END ITS TURN** before dispatching. Treat as **L2**: `--auto` cannot auto-pass.
  A DYNAMIC (unplanned) wave is a dynamic source-writing node, so it stays L2 (unchanged). A
  dynamic source-writing node is provisioned by Hard rule 6 at its human-gated dispatch, so the
  coder never authors on the principal checkout on the unplanned path either.

**Defense-in-depth (M3):** re-derive each node's floor from registry truth before gating - an
`outward` git merge/push ⇒ L2; a non-wave `instance_touching` node ⇒ L2; a DYNAMIC source-writing
node (including an unplanned wave) ⇒ L2. A STATIC `approach_kind == wave` (between-wave integration)
advance ⇒ L1: its instance touches are ephemeral test DBs, its squash/force-push is the in-context
L2-squash-gate presented as the wave closes, and the only irreversible landing is the downstream
`outward` merge (odoo-pr-monitoring's L2-merge-gate). A hand-edited `run.json` cannot lower a
mandatory gate; a wave node that mutated a SHARED (non-ephemeral) instance would need explicit L2
re-classification, and none exists today. This L1 is a run-harness NODE tier applied here by the
driver - NOT a registry `default_gate_tier` value (`_derive_gate_tier` has no wave branch).

**`integrate` node dispatch (the land tail).** Invoke `git-toolkit:git-ops` from the main context to
push the change's branch and open a PR against the principal branch, then materialize
`next -> odoo-pr-monitoring` at `gate_tier: L2` - the single outward merge gate (L2 never
auto-passes, so the human approves the merge even under `--auto`). `odoo-coding` never pushes or opens
a PR; it returns the SHA on the change's branch exactly as in the between-wave integration. This is the ONE land
mechanism (git-ops open-PR -> `odoo-pr-monitoring` merge); no local merge into the principal checkout.

## Between-wave integration (consumes Block 2W)

This is the per-wave INTEGRATION responsibility run-harness owns DIRECTLY as it walks the coding waves
(there is no separate git-executor skill - run-harness is the sole owner). It CONSUMES the plan's
wave-batched **module-DAG** (with `depends_on` edges as the cherry-pick order) + topology +
`cumulative_modules` + the **Block 2W** worktree dependency graph (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 2W). It is
consume-only: it never self-derives the module-DAG. Full templates (the four topologies, the saga
pseudocode, the cleanup checklist, the execution-log + squash recipe):
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`. Per wave N, in module-DAG
order:

0. **Safety audit (trust-but-verify).** Run the disjoint file-ownership audit over the consumed
   module-DAG (no source file owned by two module scopes) + a plan-staleness check before creating
   any worktree. A file in two scopes ⇒ STOP BLOCKED and route back to `odoo-planning` to re-partition.
1. **Fork-from-prior-integration.** Fork `integration@wave-(N+1)` from `integration@wave-N` (NOT
   from `base`/principal) per the planned Block-2W lineage. Wave-1 integration forks `base`. This
   threads each wave's integrated state forward so a dependent wave's worktrees already carry their
   dependencies' committed code - the fork-from-integrated-parent loop that structurally removes the
   intra-run cross-wave "dependency absent" BLOCKED path.
2. **Cherry-pick + saga.** Cherry-pick each module's returned commit (the `odoo-coder` coordinator
   committed it via `git-toolkit:git-ops`) into the wave integration, in module-DAG topo order, with
   saga rollback / resume-from-checkpoint on failure (SSOT:
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`). All git is invoked via
   `git-toolkit:git-ops`.
3. **Close the wave.** Run the integrated-tree cross-cutting review over the whole integration
   worktree - SCALE-BASED, never a flat inline review regardless of wave size: a large wave
   (`git diff <principal>...HEAD --shortstat` > ~1500 changed lines OR module count N >= 8)
   escalates to a **fable** review subagent (cost ~2x opus - state tier + cost + a one-line why,
   wait for an explicit human `yes`; on decline/unavailable fall back to opus inline and note the
   downgrade); otherwise run an **opus inline** review in this context (full rule + coverage/
   blast-radius review lenses: `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
   § Review Escalation). Then the **cumulative regression close-gate** - the growing
   `cumulative_modules` suite run GREEN (never open a PR on red).
4. **One squashed PR, then STOP.** Open ONE squashed PR for the wave and STOP at the L2-squash-gate;
   the outward MERGE stays `odoo-pr-monitoring`'s (the single L2 merge gate). Then
   `integration@wave-(N+1)` forks from this closed integration and the loop continues.
5. **Acceptance hand-off (opt-in, L2).** If step 3's blast-radius render-check reached BEYOND the
   wave's own modules (the `render_check_set` binds dependents), materialize an `odoo-acceptance`
   node in the RUN-DAG at `gate_tier: L2` depending on the wave's PR, so the affected cluster is
   verified before merge (never auto-run, never auto-block) - the SAME condition + shape
   `odoo-code-review` emits its acceptance hand-off under (full `next` block + shared render_check_set
   SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Review
   Escalation).

The invoked `odoo-coding` DRIVES its own per-module `odoo-code-review` inline and returns a SHA;
run-harness does NOT advance a per-module `next` for that in-wave invocation (the review loop
lives inside `odoo-coding`; run-harness just cherry-picks the returned SHA). The between-wave advance
is L1 (autonomous drive-to-done); the squash/force-push + PR is the in-context L2-squash-gate; the
downstream merge is `odoo-pr-monitoring`'s L2-merge-gate. This is the drive-to-done invariant: the
wave may auto-advance between waves ONLY because each wave proves a GREEN cumulative close-gate before
it opens a PR.

## Circuit-breakers (anti-runaway, anti-trap)

- `budget.max_nodes` hard cap → BLOCKED.
- Dedup `dynamic_nodes` by (skill + inputs) - re-suggested already-run nodes dropped.
- `confidence < 0.5` next[] → surface as suggestion, do not auto-materialize.
- Node FAILED 3× → BLOCKED (escalate, don't retry forever).
- Cycle detection in `pick_ready`.
- User abort phrase ("stop", "dừng", "abort the run") → BLOCKED with reason="user abort".

## Resume

Re-entry reads `run-<id>.json`, skips `DONE` nodes, and continues at the first `READY` node in
topo-order (same contract as BRL checkpoint, harness §3.3 / §8.3).

## Standalone-first fallback

No OSM dependency - pure orchestration over `run-<id>.json`. Works whether or not OSM is
reachable; grounding is the concern of each dispatched specialist. If the blackboard file is
missing or unreadable, the driver reports `NEEDS_CONTEXT` (never fabricates a DAG).

## Continuation Contract

When this loop yields control (run reaches a terminal state, or a gate awaits the human),
append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` reflecting `RUN.status`.
