---
name: run-harness
argument-hint: "[run-id]"
user-invocable: false
description: >
  Runs an approved multi-step plan through to the end so the user does not have to push it along
  step by step: takes the next step whose prerequisites are met, stops for the human's approval
  where the plan says a human must approve, hands the step to the skill that owns it, records what
  came back, and keeps going until the work is finished, blocked, or missing something it needs.
  Also picks a paused or interrupted run back up where it left off, checking what actually
  happened before repeating anything. Started by odoo-intake once a plan is approved; never
  invoked directly by the user
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
  `run-<id>.json`; it never ingests a plan `.md`. A skill that produces a plan (e.g. `odoo-planning`)
  routes it to intake Phase P (`next: odoo-intake`), NEVER `next: run-harness` with only a plan
  pointer - reaching this loop before serialization just yields `NEEDS_CONTEXT`.
- **Coercing the main agent** → advisory nudges only (Hard rule #2).
- **Crossing the Odoo↔general boundary** → intake's routing decision.

## Hard rules

1. **Owns the blackboard.** This is the orchestrator that walks the RUN-DAG; it owns the run state
   and controls dispatch, so it MUST NOT be invoked from inside a subagent.
2. **Never hard-block the main agent - but that is not an open license to pause.** This loop is
   prompt-discipline, not coercion: the Stop/PreToolUse hooks only *nudge* (advisory); they never
   deny a tool call or block a turn-end. (Quality-gate `block` is only ever for a subagent, e.g.
   `enforce-grounding`.) That mechanism fact does NOT make "a wave/node just finished" a reason to
   stop. **The main agent auto-advances the run WITHOUT asking a human UNLESS one of the following
   ENUMERATED conditions holds - these are the ONLY legitimate reasons to end the turn and await a
   human "continue":** (a) the node is L2 (§ Gate-tier resolution below - ALWAYS a human gate); (b)
   the run resolves to BLOCKED (§ Circuit-breakers below: `budget.max_nodes` exhausted, a dependency
   cycle, a node FAILED 3x); (c) the run resolves to NEEDS_CONTEXT; (d) the human issued an explicit
   stop/abort phrase (§ Circuit-breakers below). Finishing a wave, a module, or any single subagent
   dispatch is, by itself, never one of these - and a run that plows past a genuine (a)-(d)
   condition instead of stopping is BLOCKED behavior too (a real blocker ignored), not
   drive-to-done.
3. **Writes to `run-<id>.json` after creation are run-harness's alone.** Intake's Phase P performs
   the one-time bootstrap write that creates the file; from then only this loop writes it (hooks
   never write it - no write race).
4. **You dispatch; subagents do not.** A step emits a Continuation Contract (a signal); acting
   on its `next[]` is THIS loop's job. Respect the worker-brief contract (`snippets/worker-brief.md`).
5. **L2 is always a human gate.** The autonomy dial can lower L1→auto-pass but can NEVER lower
   L2 (irreversible/outward: shared instance, git MERGE to the principal branch, send to a third
   party). Opening a repo's ONE PR is NOT L2 - nothing is rewritten, so the terminal `integrate`
   land-tail runs as part of drive-to-done under `--auto`. The ONLY coding-run L2 is the outward MERGE (owned by
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
  intake Phase P from the approved plan, schema in harness §8.3).
- `autonomy` ∈ {auto (default), step, plan} read from that file.
- `repos[]` from that file: one entry per repository the run touches, each carrying that repo's
  Repo Capability Card (`id`, `base`, `verify`, `commit`, `confidential`, `worktree_root`). A
  single-repo run is a ONE-ENTRY list. **N repos = N `integrate` nodes = N PRs.** `id` is
  ORIGIN-DERIVED, so one repository always yields ONE id (resolution rule + collision behaviour:
  wave-integration.md § Repo Capability Card Template); re-derive it at Run start and collapse two
  entries that resolve to one id into ONE card before forking anything.
- Each node's `repo` names one of those `id`s. **`repo: null` is legal ONLY for a node that writes
  into no repository tree and gates no repo's delivery** - the chat-only `inline` synthesis /
  routing / report node (rule owner: harness §8.3 § `repo: null` legality). Every `wave`,
  `integrate`, and lifecycle node (review, i18n, acceptance, doc, lint, monitor, merge) MUST name a
  declared `id`. The driver RE-DERIVES this rather than trust it: a `repo: null` node that is not
  chat-only `inline`, or that declares file outputs, is a serialization bug -> STOP BLOCKED naming
  the node; never let it pass as merely "outside every repo's scope".

## The loop

```
RUN_FILE = <ISOLATE_DIR>/run-<id>.json             # resolve WHICH run ONCE, out here: the active run; if
                                                   # several, the one intake just wrote / the user named

loop:
    RUN = read(RUN_FILE)          # RE-READ the run file from disk at the TOP of EVERY iteration - the file
                                  # on disk wins over anything you remember from earlier in this run.
    if RUN.status != "NEEDS_NEXT": break

    if RUN.budget.nodes_run >= RUN.budget.max_nodes:        # runaway guard
        set RUN.status = "BLOCKED"; blocked_reason = "node budget exhausted - human review"; write(RUN); break

    node = pick_ready(RUN)        # READY = every depends_on is DONE; topo-order; tie → lowest node id
                                  # (plan authoring order; `confidence` is a dynamic-next[] field, NOT a static-node field)
                                  # `integrate@R`: RE-DERIVE its extra precondition here, scoped by
                                  # node.repo, never trust depends_on alone (§ Gate-tier resolution
                                  # → `integrate` readiness precondition)
    if node is None:              # nothing ready but not all done → cycle / deadlock
        set RUN.status = "BLOCKED"; blocked_reason = "no ready node (dependency cycle?)"; write(RUN); break

    tier = rederive_floor(node)   # NOT raw node.gate_tier - re-assert the floor (see §Gate-tier
                                  # resolution): an `outward` MERGE | a non-wave instance_touching
                                  # node | ANY DYNAMIC (unplanned) node ⇒ L2; a STATIC between-wave
                                  # integration (wave) advance ⇒ L1 (ephemeral instance; auto-advance to
                                  # the next wave, NO per-wave PR); the terminal `integrate` land-tail
                                  # is drive-to-done, not L2; else node.gate_tier / registry default.
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
                              run-integration branch; INVOKE odoo-coding; cherry-pick the returned SHA
                              onto run-integration + saga; integrated review + cumulative close-gate;
                              then AUTO-ADVANCE - NO per-wave PR, NO per-wave stop)
        - integrate         → the terminal land-tail, ONCE PER REPO after the FINAL wave closes green:
                              run § Existence precheck, then invoke git-toolkit:git-ops (squash
                              node.repo's run-integration branch + push + open ONE PR against principal)
                              from main context, then materialize next -> odoo-pr-monitoring @ gate_tier
                              L2 (single outward merge gate)
        - inline            → do the small synth step yourself
    # turn typically ends here for any subagent/agent dispatch; SubagentStop hook nudges resume

    contract = read_continuation_contract(node)              # SPAWNER node (skill invoked in `main`): read its in-context
                                                             # AGGREGATE result inline. LEAF agent: read the contract from your
                                                             # own launch call's returned result, NOT the `.output` transcript.
    node.contract = contract
    node.produced = contract.produced
    node.status   = map(contract.status)                     # DONE | NEEDS_NEXT→DONE (next[] already
                                                             # materialized into dynamic_nodes above) |
                                                             # FAILED→retry<3 else BLOCKED | BLOCKED |
                                                             # NEEDS_CONTEXT
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
finalize: RUN.completion = {status, evidence: flatten(all produced), summary}; write(RUN)
emit terminal report (DONE | BLOCKED | NEEDS_CONTEXT), one evidence pointer per claim
```

Per `${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`, run-harness creates and keeps
current a live task list of the RUN-DAG nodes it dispatches (one item per node, title = node id) -
mirroring `RUN.nodes[].status` for human visibility, never redefining it; update both together on
every status change. This fires whenever a task-list tool is available in run-harness's own toolset;
use whatever task-list primitive the runtime exposes.

run-harness dispatches each node via Skill-tool inline, a spawner skill (Skill tool), or
workflow-chaining. A spawner-skill node (e.g. odoo-coding) runs in the same `main` context and owns
its own workers; run-harness reads that spawner's in-context aggregate result and does not track its
workers. For a LEAF agent dispatched directly, read the result from your own launch call's returned
result, NEVER the `.output` transcript
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3).

Every gate this loop emits (`emit_human_gate`, the dynamic-node preview, the close-the-wave
confirmation, the terminal report) is chat-facing: write it in the USER'S language (translate the
prose; keep node ids, module names, paths, skill names, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

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
  per-wave PR, NO per-wave stop). `--step` re-inserts a between-wave stop: it raises the floor to
  L1, and an L1 node under non-`auto` autonomy emits a human gate.
- **Dynamic node** (materialized at runtime from `next[]` / `on_complete` - never in the
  approved plan): driver MUST emit a preview (`Proposed / Files / OSM: backed | standalone` -
  spelling OSM out on first use: Odoo Semantic, the indexed Odoo source; backed = facts checked
  against it, standalone = not reachable, local files only - then
  `Gate: approve / refine: [feedback] / cancel`, the PLAN gate set,
  `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`)
  and **END ITS TURN** before dispatching. Treat ANY dynamic (unplanned) node as **L2**:
  `--auto` cannot auto-pass (GATE E-4 all-dynamic-L2). A DYNAMIC (unplanned) wave is one such node,
  so it stays L2 (unchanged), and a dynamic source-writing node is provisioned by Hard rule 6 at its
  human-gated dispatch like any other.

**Defense-in-depth (M3):** re-derive each node's floor from registry truth before gating (the
`rederive_floor` rules above), so a hand-edited `run.json` cannot lower a mandatory gate. The only
irreversible landing is the downstream `outward` merge (odoo-pr-monitoring's L2-merge-gate) of the
single run-level PR; a wave node that mutated a SHARED (non-ephemeral) instance would need explicit
L2 re-classification, and none exists today. The wave L1 is a run-harness NODE tier applied here by
the driver - NOT a registry `default_gate_tier` value (`_derive_gate_tier` has no wave branch).

**`integrate` readiness precondition (RE-DERIVE it; `depends_on` alone is NOT trusted).** This is the
same defense-in-depth move as `rederive_floor` above: the driver re-derives the rule at `pick_ready`
instead of believing what the plan serialized. **`R` is the node's own `repo` field** (harness §8.3;
one `integrate` node per entry in `RUN.repos[]`). **`integrate@R` is READY only when EVERY node whose
`repo == R` and which is NOT in the land-tail set is DONE or SKIPPED. land-tail set =
{`integrate`, `monitor`, `merge`}.** The land-tail carve-out is MANDATORY - never "simplify" it away:
`monitor` depends on `integrate`, so a rule phrased "every OTHER node in the repo must be DONE"
deadlocks EVERY run (`integrate` waits for `monitor`, `monitor` waits for `integrate`, run ends
BLOCKED). Nodes of ANOTHER repo are OUTSIDE this scope - each repo's PR waits only on ITS OWN nodes,
so a slow second repo never holds the first repo's PR hostage. A `repo: null` node is outside it too,
but ONLY because a LEGAL `repo: null` node writes into no repository and gates no delivery (§ Inputs):
re-derive that legality before excluding any such node - an illegal one STOPS the run BLOCKED, it is
never skipped past. A one-entry `repos[]` collapses this to "every non-land-tail node in the run", with
no special case. This is what keeps the PR from opening ahead of the doc / review / acceptance nodes
when the plan under-specified `integrate.depends_on` (tie-break by lowest node id would otherwise
decide that by accident).

**`integrate` node dispatch (the land tail).** Dispatched ONCE PER REPO (`integrate@R`), after the
FINAL coding wave closes green. Invoke `git-toolkit:git-ops` from the main context to squash repo
`R`'s run-integration branch, push it to the fork, and open ONE PR against `R`'s `base` branch, then
materialize `next -> odoo-pr-monitoring` at `gate_tier: L2` - the single outward merge gate (L2
never auto-passes, so the human approves the merge even under `--auto`). `odoo-coding` never pushes
or opens a PR. No local merge into the principal checkout, and no auto-merge.

**Existence precheck (MANDATORY, BEFORE any push or PR-open - the land tail must be safe to run
twice).** Read `R`'s remote state through `git-toolkit:git-ops` FIRST (is `run-integration-<slug>`
already on the fork? is a PR for that branch against `base` already OPEN?) and DERIVE `first-push`
from it instead of asserting it. **An already-open PR IS this repo's ONE PR: UPDATE it - push the
missing commits to the SAME branch, which updates an open PR by itself - record its URL in
`produced`, and never open a second one.** Case matrix + the rewrite-history gate:
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Squash Tree-Identity Recipe.

## Between-wave integration (consumes Block 2W)

run-harness owns the between-wave INTEGRATION DIRECTLY as it walks the coding waves (there is no
separate git-executor skill - it is the sole owner). It CONSUMES the plan's
wave-batched **module-DAG** (with `depends_on` edges as the cherry-pick order) + topology +
`cumulative_modules` + the **Block 2W** worktree dependency graph (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 2W) and never
self-derives them. Full templates (every topology value, the saga pseudocode, the cleanup
checklist, the execution-log + squash recipe):
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`.

**Run start (ONCE, before wave 1).** FIRST, before touching anything under this run's own
`wave/<slug>/`: sweep stale `wave/<slug>/` siblings left by past, abandoned runs - a fail-closed,
run-status-correlated 24h crash-backstop, never a bare mtime check -
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
§ Stale wave-dir sweep (full recipe there, not restated here). THEN create the JOB-tier
integration worktree: invoke the `git-toolkit:git-ops` skill (via the Skill tool) to add a
worktree (branch `run-integration-<slug>`, worktree `<worktree_root>/run-integration`, base
`base`/principal) - **one such pair PER ENTRY in `RUN.repos[]`**, each resolved from THAT entry's own
card (`base`, `worktree_root`); a one-entry `repos[]` makes this exactly one pair, as before. A
repo's branch+worktree pair is the cherry-pick target for EVERY wave node whose `repo` is that repo,
and is what that repo's terminal `integrate` land-tail squashes + pushes. There is NO per-wave
integration branch or worktree.

Then, per wave N, in module-DAG order:

0. **Safety audit (trust-but-verify).** Run the disjoint file-ownership audit over the consumed
   module-DAG + a plan-staleness check before creating any worktree. A source file owned by two
   module scopes ⇒ STOP BLOCKED and route back to `odoo-planning` to re-partition.
0b. **Topology collapse (read, never re-derive).** `topology: single` on this wave node -> SKIP steps
   1-2 entirely: dispatch the one module DIRECTLY into the run-integration worktree, let it commit
   there, and go to step 3. No child worktree, no cherry-pick, no per-module checkpoint. Semantics +
   the `n <= 1` predicate:
   `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Topology values.
   Field ABSENT -> steps 1-2 as written.
1. **Fork module worktrees from run-integration.** Each module's worktree forks from the
   run-integration branch OF THE WAVE NODE'S OWN `repo` (NOT from `base`/principal, NOT from a
   per-wave branch, NOT from another repo's run-integration) per the planned
   Block-2W lineage. run-integration already carries every PRIOR wave's cherry-picked code, so a
   dependent wave's worktree already CONTAINS its dependencies' committed source
   (fork-from-integrated-parent, on ONE branch). That source reaches the verification instance's
   addons-path only when the per-module brief
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
   worktree - SCALE-BASED, never a flat inline review regardless of wave size: measure the wave and
   escalate a large one to a **fable** review subagent, asking the human as a TRADEOFF and never by
   tier name; otherwise run an **opus inline** review in this context. Thresholds, the trade-off
   wording and reply set, and the coverage / blast-radius review lenses:
   `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
   § Review Escalation. Then the **cumulative regression close-gate** - the growing
   `cumulative_modules` suite run GREEN (never open a PR on red). On green the wave is CLOSED and the
   driver AUTO-ADVANCES to the next wave: **NO per-wave PR, NO per-wave human stop**. The next wave's
   worktrees fork from the same run-integration branch, which now carries this wave's code too.

When composing the dispatch prompt for any specialist agent you dispatch (e.g. the fable/opus
review subagent above), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief.

4. **After the FINAL wave: the pre-PR tail, THEN the single land-tail PR.** There is NO per-wave PR.
   After the LAST wave closes green, run-harness drives the pre-PR tail IN THE ORDER FIXED BY the
   Terminal stage order constant (cited below), and ONLY THEN dispatches the
   terminal `integrate` land-tail ONCE PER REPO (§ `integrate` node dispatch, whose existence
   precheck runs first): squash that repo's run-integration branch, push it, open ONE PR against
   principal. The outward MERGE stays `odoo-pr-monitoring`'s (the single L2-merge-gate).
   Drive-to-done STOPS at "PR opened". Full sequence + the acceptance hand-off's `next` block:
   `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
   § Pre-PR tail (mandatory sequence, after the final wave closes green) > Terminal stage order -
   not restated here.

The invoked `odoo-coding` DRIVES its own per-module `odoo-code-review` inline and returns a SHA;
run-harness does NOT advance a per-module `next` for that in-wave invocation (the review loop
lives inside `odoo-coding`; run-harness just cherry-picks the returned SHA onto run-integration). The
between-wave advance is L1 (autonomous drive-to-done, auto-advance with NO per-wave PR); the ONLY
coding-run L2 is the downstream MERGE of the single run PR (`odoo-pr-monitoring`'s L2-merge-gate).
This is the drive-to-done invariant: the run auto-advances between waves ONLY because each wave
proves a GREEN cumulative close-gate first, and the run opens exactly ONE PR per REPO after the
final wave.

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

**A `RUNNING` node on re-entry means DISPATCHED, OUTCOME UNKNOWN - never re-dispatch it blindly.**
`RUNNING` is persisted BEFORE dispatch, so the step may have fully run, half-run, or never started,
and its `depends_on` are all `DONE`, so `pick_ready` would otherwise dispatch it a SECOND time. Before
`pick_ready` may consider ANY node, RECONCILE every `RUNNING` node against OBSERVABLE reality - its
declared outputs on disk, and for a node carrying a `repo`, that repo's state through
`git-toolkit:git-ops` (bounded reads: branch present? its commits there? a PR already open?) - then
set exactly ONE status and `write(RUN)`: **DONE** when the work and its evidence are fully present
(record them in `produced`); **READY** when nothing landed, so re-dispatch is safe; **BLOCKED** when
the effect is PARTIAL - record what exists in `produced`, `blocked_reason` naming what is missing,
and report; a partial node is never re-dispatched on a guess. Reconcile from what is observable,
never from the transcript or from what you remember dispatching. An `integrate` node
reconciles through its own § Existence precheck, so a resumed land tail UPDATES this repo's already
open PR instead of opening a second one.

## Standalone-first fallback

No OSM dependency - pure orchestration over `run-<id>.json`, whether or not OSM is reachable;
grounding is each dispatched specialist's concern. If the blackboard file is missing or unreadable,
the driver reports `NEEDS_CONTEXT` (never fabricates a DAG).

## Continuation Contract

When this loop yields control (a terminal state, or a gate awaiting the human), append a
Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` reflecting `RUN.status`.
