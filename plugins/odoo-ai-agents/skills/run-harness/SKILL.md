---
name: run-harness
argument-hint: "[run-id]"
user-invocable: false
description: >
  Drive-to-done loop. Walks the RUN-DAG in the worktree's isolated run-state file that intake's
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
   L2 (irreversible/outward: shared instance, git MERGE to the principal branch, send to a third
   party). Opening the run's ONE PR - the terminal `integrate` land-tail's fresh FIRST-push of the
   run-integration branch to the fork + PR-open - is NOT L2: it is a non-destructive first push (no
   history rewrite, no force, so no git-toolkit destructive-op gate fires) and runs as part of
   drive-to-done under `--auto`. The ONLY coding-run L2 is the outward MERGE (owned by
   `odoo-pr-monitoring`). No local merge into the principal checkout; no auto-merge.
6. **Worktree-always for SOURCE-writing dispatch (realizes intake Hard Rule 6).** Before
   dispatching a node that writes the SOURCE tree (not the `$ODOO_AI_HOME` state root; same test as
   Gate-tier resolution), if it has no `WORKTREE_PATH`/`TARGET: worktree:<path>` and its approach is not a
   self-provisioning specialist (SSOT list:
   `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists), INVOKE
   `git-toolkit:git-ops` to create a dedicated worktree/branch, inject its path into the node's
   `inputs`, and `write(RUN)`. NEVER dispatch a source-writing node against the principal checkout.
   A node that writes only under the `$ODOO_AI_HOME` state root (e.g. `odoo-code-review` at
   `TARGET=local`) is NOT provisioned.

## Inputs

- An active `<ISOLATE_DIR>/run-<id>.json` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
  `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute
  path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit; serialized by
  intake Phase P from the approved plan, schema in harness §8.3) - run-harness is dispatched only
  after this file exists; it never receives a raw plan `.md`.
- `autonomy` ∈ {auto (default), step, plan} read from that file.

## The loop

```
load RUN = read(<ISOLATE_DIR>/run-<id>.json)        # the active run; if several, the one intake just wrote / the user named

while RUN.status == "NEEDS_NEXT":
    if RUN.budget.nodes_run >= RUN.budget.max_nodes:        # runaway guard
        set RUN.status = "BLOCKED"; blocked_reason = "node budget exhausted - human review"; break

    node = pick_ready(RUN)        # READY = every depends_on is DONE; topo-order; tie → lowest node id
                                  # (plan authoring order; `confidence` is a dynamic-next[] field, NOT a static-node field)
    if node is None:              # nothing ready but not all done → cycle / deadlock
        set RUN.status = "BLOCKED"; blocked_reason = "no ready node (dependency cycle?)"; break

    tier = rederive_floor(node)   # NOT raw node.gate_tier - re-assert the floor (see §Gate-tier
                                  # resolution): an `outward` MERGE | a non-wave instance_touching
                                  # node | ANY DYNAMIC (unplanned) node ⇒ L2; a STATIC between-wave
                                  # integration (wave) advance ⇒ L1 (ephemeral instance; auto-advance to
                                  # the next wave, NO per-wave PR); the terminal `integrate` land-tail's
                                  # branch-push + PR-open is drive-to-done (fresh first push, not L2);
                                  # else node.gate_tier / registry default.
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
                              node (consume Block 2W lineage; per module fork a worktree FROM the ONE
                              run-integration branch; INVOKE odoo-coding; the odoo-coder coordinator
                              commits + returns the SHA; cherry-pick onto run-integration + saga;
                              integrated review + cumulative close-gate; then AUTO-ADVANCE to the next
                              wave - NO per-wave PR, NO per-wave stop). run-harness owns this directly -
                              there is no git-executor skill.
        - integrate         → the terminal land-tail, dispatched ONCE after the FINAL wave closes green:
                              invoke git-toolkit:git-ops (squash the run-integration branch + fresh
                              FIRST-push to the fork + open ONE PR against principal) from main context,
                              then materialize next -> odoo-pr-monitoring @ gate_tier L2 (single outward
                              merge gate). The push is a non-force first push - no destructive-op gate fires.
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
                                                             # ALWAYS stamp gate_tier=L2 - ANY dynamic
                                                             # (unplanned) node is human-gated (preview + L2),
                                                             # never auto-approved (GATE E-4 all-dynamic-L2)
        else:
            note_as_suggestion(nx)                           # low-confidence / dup → surface to human, do not auto-run
    RUN.budget.nodes_run += 1
    RUN.status = rollup(RUN)                                 # NEEDS_NEXT while any reachable node ≠ DONE
    write(RUN)

# Completion Contract (#8): terminal report with evidence
finalize: RUN.completion = {status, evidence: flatten(all produced), summary}
emit terminal report (DONE | BLOCKED | NEEDS_CONTEXT), one evidence pointer per claim
```

Per `${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`, run-harness creates and keeps
current a live task list of the RUN-DAG nodes it dispatches (one item per node, title = node id) -
mirroring `RUN.nodes[].status` for human visibility, never redefining it; update both together on
every status change. This fires whenever a task-list tool is available in run-harness's own
toolset, INDEPENDENT of Agent Team mode / the CHP capability probe / `SendMessage` - it does not
require the experimental `TaskCreate`/`TaskList`/`TaskGet` surface specifically; use whatever
task-list primitive the runtime actually exposes.

Separately, when the CHP capability probe is positive (Agent Team mode on), run-harness ALSO
tracks OTHER named teammate agents via `TaskCreate`/`TaskList`/`TaskGet` per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 2 - this teammate-status layer is
distinct from the always-on node checklist above and stays CHP-gated. run-harness itself does NOT
spawn named teammate agents - it dispatches each node via Skill-tool inline, a spawner skill (Skill
tool), or workflow-chaining. A spawner-skill node (e.g. odoo-coding) runs in the same `main` context
and is team lead for its OWN teammates (injects their briefs TASK_ID + REPLY_TO: <that spawner
skill's current orchestrating context> (`main` when the main-context driver invoked run-harness; do
NOT hardcode a literal `main` if run-harness itself is running nested inside a non-lead agent) +
NOTIFY, consumes their pushes); run-harness reads the spawner's in-context aggregate result and does NOT
track the spawner's teammate tasks (single main context - no double-tracking). For a LEAF teammate
dispatched directly, inject its brief and read the result from its SendMessage push (NEVER the
`.output` transcript). When the CHP probe is off, teammate tracking is skipped - the always-on node
checklist above still applies regardless.

## Gate-tier resolution

Per node: `node.gate_tier` (run.json override) → else registry `default_gate_tier`
(`skill_tool_deps.json`). Apply the dial: `--step` raises floor to L1; `--auto` lets L0+L1
auto-pass within budget. **L2 never lowers.** See harness §8.4.

**Source-writing nodes** (targets source tree, not the `$ODOO_AI_HOME` state root) - **human gate
MUST be at the driver, before dispatch.** Spawner skills fan out their worker via launch subagent
and that subagent cannot pause for human input; the skill's internal Phase-0 gate is only a
safety-net, not the binding gate. Spawner skills writing only under the `$ODOO_AI_HOME` state root
(`odoo-code-review`, `odoo-ui-review`) need no extra driver gate beyond registry tier.

A coding wave node's `approach_kind` is `wave`: the node groups one wave's MODULES (with their
module-DAG + topology + `cumulative_modules` + the Block-2W lineage slice) - the outer unit is the
MODULE, not a work-item (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier
decomposition axis). run-harness drives it via § Between-wave integration - it iterates the wave's
modules and invokes `odoo-coding` per module; the work-item is `odoo-coder`'s INTERNAL intra-module
unit and never appears in a run node.

- **Static node** (in the Plan-Mode-approved DAG): Plan-Mode approval IS the human gate →
  auto-pass under `--auto`. A STATIC `wave` (between-wave integration) advance is L1 and DRIVES to
  done: each wave closes on a GREEN cumulative close-gate and AUTO-ADVANCES to the next wave (NO
  per-wave PR, NO per-wave stop). The single run-level PR is opened ONCE by the terminal `integrate`
  land-tail after the FINAL wave (a fresh, non-force first push - drive-to-done, not a gate), and the
  only irreversible landing is the downstream `outward` L2-merge-gate (odoo-pr-monitoring). `--step`
  re-inserts a between-wave stop: it raises the floor to L1, and an L1 node under non-`auto` autonomy
  emits a human gate.
- **Dynamic node** (materialized at runtime from `next[]` / `on_complete` - never in the
  approved plan): driver MUST emit a preview (`Proposed / Files / OSM / Proceed? (yes / refine /
  cancel)`) and **END ITS TURN** before dispatching. Treat ANY dynamic (unplanned) node as **L2**:
  `--auto` cannot auto-pass (GATE E-4 all-dynamic-L2). A DYNAMIC (unplanned) wave is one such node,
  so it stays L2 (unchanged). A dynamic source-writing node is additionally provisioned by Hard
  rule 6 at its human-gated dispatch, so the coder never authors on the principal checkout on the
  unplanned path either.

**Defense-in-depth (M3):** re-derive each node's floor from registry truth before gating - an
`outward` git MERGE ⇒ L2; a non-wave `instance_touching` node ⇒ L2; ANY DYNAMIC (unplanned) node
(including an unplanned wave) ⇒ L2. A STATIC `approach_kind == wave` (between-wave integration)
advance ⇒ L1: its instance touches are ephemeral test DBs, it auto-advances to the next wave on a
GREEN cumulative close-gate (NO per-wave PR), and the only irreversible landing is the downstream
`outward` merge (odoo-pr-monitoring's L2-merge-gate) of the single run-level PR. The terminal
`integrate` land-tail's branch-push + PR-open is a fresh, non-force first push - drive-to-done under
`--auto`, not a gate (no destructive-op gate fires). A hand-edited `run.json` cannot lower a
mandatory gate; a wave node that mutated a SHARED (non-ephemeral) instance would need explicit L2
re-classification, and none exists today. This L1 is a run-harness NODE tier applied here by the
driver - NOT a registry `default_gate_tier` value (`_derive_gate_tier` has no wave branch).

**`integrate` node dispatch (the land tail).** Dispatched ONCE, after the FINAL coding wave closes
green. Invoke `git-toolkit:git-ops` from the main context to squash the run-integration branch, do a
fresh FIRST push of it to the fork (a non-force push - no history rewrite, so no git-toolkit
destructive-op gate fires), and open ONE PR against the principal branch, then materialize
`next -> odoo-pr-monitoring` at `gate_tier: L2` - the single outward merge gate (L2 never
auto-passes, so the human approves the merge even under `--auto`). `odoo-coding` never pushes or opens
a PR; per module it returns the SHA on its branch, which run-harness cherry-picks onto the ONE
run-integration branch during the between-wave integration. This is the ONE land mechanism for the
whole run - one PR, not one per wave (git-ops open-PR -> `odoo-pr-monitoring` merge); no local merge
into the principal checkout, and no auto-merge.

## Between-wave integration (consumes Block 2W)

This is the between-wave INTEGRATION responsibility run-harness owns DIRECTLY as it walks the coding
waves (there is no separate git-executor skill - run-harness is the sole owner). It CONSUMES the plan's
wave-batched **module-DAG** (with `depends_on` edges as the cherry-pick order) + topology +
`cumulative_modules` + the **Block 2W** worktree dependency graph (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 2W). It is
consume-only: it never self-derives the module-DAG. Full templates (all five topology values: the
four multi-module topologies plus the `single` collapse case; also the saga pseudocode, the cleanup
checklist, the execution-log + squash recipe):
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`.

**Run start (ONCE, before wave 1).** Create the JOB-tier integration worktree: invoke the
`git-toolkit:git-ops` skill (via the Skill tool) to add a worktree (branch
`run-integration-<slug>`, worktree `<worktree_root>/run-integration`, base `base`/principal). This
single branch+worktree pair is the cherry-pick target for EVERY wave and is the branch the terminal
`integrate` land-tail eventually squashes + pushes as the run's ONE PR. There is NO per-wave
integration branch or worktree.

Then, per wave N, in module-DAG order:

0. **Safety audit (trust-but-verify).** Run the disjoint file-ownership audit over the consumed
   module-DAG (no source file owned by two module scopes) + a plan-staleness check before creating
   any worktree. A file in two scopes ⇒ STOP BLOCKED and route back to `odoo-planning` to re-partition.
0b. **Topology collapse (read, never re-derive).** `topology: single` on this wave node -> SKIP steps
   1-2 entirely: dispatch the one module DIRECTLY into the run-integration worktree, let it commit
   there, and go to step 3. No child worktree, no cherry-pick, no per-module checkpoint. Semantics +
   the `n <= 1` predicate:
   `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Topology values.
   Field ABSENT -> steps 1-2 as written.
1. **Fork module worktrees from run-integration.** Each module's worktree forks from the ONE
   run-integration branch (NOT from `base`/principal, NOT from a per-wave branch) per the planned
   Block-2W lineage. Because run-integration already carries every PRIOR wave's cherry-picked code, a
   dependent wave's worktree already CONTAINS its dependencies' committed source - the
   fork-from-integrated-parent property, now realized on ONE branch instead of a chain of per-wave
   forks. That source reaches the verification instance's addons-path only when the per-module brief
   carries `WORKTREE_PATH` + `SELF_PROVISION: worktree-addons`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out), which
   `odoo-coding` sets on every such dispatch - a POLICY step, not a structural guarantee of the fork
   itself. Skipping it reopens the intra-run cross-wave "dependency absent" BLOCKED path even though
   the source already sits in the tree.
2. **Cherry-pick + saga.** Cherry-pick each module's returned commit (the `odoo-coder` coordinator
   committed it via `git-toolkit:git-ops`) onto the RUN-INTEGRATION branch, in module-DAG topo order,
   with saga rollback / resume-from-checkpoint on failure (SSOT:
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
   `cumulative_modules` suite run GREEN (never open a PR on red). On green the wave is CLOSED and the
   driver AUTO-ADVANCES to the next wave: **NO per-wave PR, NO per-wave human stop**. The next wave's
   worktrees fork from the same run-integration branch, which now carries this wave's code too.

When composing the dispatch prompt for any specialist agent you dispatch (e.g. the fable/opus
review subagent above), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief.

4. **After the FINAL wave: the single land-tail PR.** There is NO per-wave PR. After the LAST wave
   closes green, run-harness dispatches the terminal `integrate` land-tail ONCE (§ `integrate` node
   dispatch): squash the run-integration branch, fresh FIRST-push it to the fork (non-force - no
   history rewrite, so no git-toolkit destructive-op gate fires), and open ONE PR against principal.
   The outward MERGE stays `odoo-pr-monitoring`'s (the single L2-merge-gate). Drive-to-done STOPS at
   "PR opened".
5. **Acceptance hand-off (opt-in, L2).** If step 3's blast-radius render-check reached BEYOND a
   wave's own modules (the `render_check_set` binds dependents), materialize an `odoo-acceptance`
   node in the RUN-DAG at `gate_tier: L2` depending on the run's PR, so the affected cluster is
   verified before merge (never auto-run, never auto-block) - the SAME condition + shape
   `odoo-code-review` emits its acceptance hand-off under (full `next` block + shared render_check_set
   SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Review
   Escalation).

The invoked `odoo-coding` DRIVES its own per-module `odoo-code-review` inline and returns a SHA;
run-harness does NOT advance a per-module `next` for that in-wave invocation (the review loop
lives inside `odoo-coding`; run-harness just cherry-picks the returned SHA onto run-integration). The
between-wave advance is L1 (autonomous drive-to-done, auto-advance with NO per-wave PR); the ONLY
coding-run L2 is the downstream MERGE of the single run PR (`odoo-pr-monitoring`'s L2-merge-gate).
This is the drive-to-done invariant: the wave may auto-advance between waves ONLY because each wave
proves a GREEN cumulative close-gate before the next wave forks from run-integration - and the run
opens exactly ONE PR after the final wave.

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
