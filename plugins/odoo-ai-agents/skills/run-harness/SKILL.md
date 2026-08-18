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

Conductor of a multi-step run. Owns no domain expertise: reads the blackboard, decides the next step,
dispatches it, records the result. Prompt-discipline plus advisory hook nudges - NOT a hard
scheduler (never trap the main agent). SSOT for the mechanism: `docs/reference/workflow-harness.md`
§8 - this file is the operating procedure, that is the contract.

## Out of Scope

- **Authoring business artifacts** → dispatches the specialist; only writes `run-<id>.json`.
- **Planning / serializing the DAG** → intake's Phase P. The driver only *walks* an EXISTING
  `run-<id>.json`; it never ingests a plan `.md`. A skill that produces a plan (e.g. `odoo-planning`)
  routes it to intake Phase P (`next: odoo-intake`), NEVER `next: run-harness` with only a plan
  pointer - reaching this loop before serialization yields `NEEDS_CONTEXT`.
- **Coercing the main agent** → advisory nudges only (Hard rule #2).
- **Crossing the Odoo↔general boundary** → intake's routing decision.

## Hard rules

1. **Owns the blackboard.** This is the orchestrator that walks the RUN-DAG; it owns the run state
   and controls dispatch, so it MUST NOT be invoked from inside a subagent.
2. **Never hard-block the main agent - but that is not an open license to pause.** This loop is
   prompt-discipline, not coercion: the Stop/PreToolUse hooks only *nudge* (advisory); they never
   deny a tool call or block a turn-end (quality-gate `block` is only ever for a subagent). That does
   NOT make "a node just finished" a reason to stop. **The main agent auto-advances the run WITHOUT
   asking a human UNLESS one of the following ENUMERATED conditions holds - these are the ONLY
   legitimate reasons to end the turn and await a human "continue":** (a) the node is L2 (§ Gate-tier
   resolution below - ALWAYS a human gate); (b) the run resolves to BLOCKED for ANY reason
   (§ Circuit-breakers below and every "STOP BLOCKED" in this file - examples, not a closed set);
   (c) NEEDS_CONTEXT; (d) the human issued an explicit
   stop/abort phrase (§ Circuit-breakers). Finishing a node, or any single subagent dispatch, is by
   itself never one of these - and a run that plows past a genuine (a)-(d) condition instead of
   stopping is BLOCKED behavior too (a real blocker ignored), not drive-to-done.
3. **Writes to `run-<id>.json` after creation are run-harness's alone.** Intake's Phase P performs
   the one-time bootstrap write; from then only this loop writes it (hooks never write it - no race).
4. **You dispatch; subagents do not.** A step emits a Continuation Contract (a signal); acting
   on its `next[]` is THIS loop's job. Respect the worker-brief contract (`snippets/worker-brief.md`).
5. **L2 is always a human gate.** The autonomy dial can lower L1→auto-pass but can NEVER lower
   L2 (irreversible/outward: shared instance, git MERGE to the principal branch, send to a third
   party). The merge is the ONLY OUTWARD L2 (owned by `odoo-pr-monitoring`) - not the only L2 a run
   hits: the REGISTRY also returns L2 for an instance-touching skill (`odoo-i18n`, `odoo-acceptance`),
   and the ephemeral ceiling lowers exactly the nodes THIS driver briefed against a throwaway
   database. No local merge into the principal checkout; no auto-merge. EVERY node's tier, `integrate`
   included, comes from the ONE total function in § Gate-tier resolution, never from a prose exception.
6. **Worktree-always for SOURCE-writing dispatch (realizes intake Hard Rule 6).** Before dispatching
   a node that writes the SOURCE tree (not the `$ODOO_AI_HOME` state root; same test as Gate-tier
   resolution), if it has no `WORKTREE_PATH`/`TARGET: worktree:<path>` and its approach is not a
   self-provisioning specialist (SSOT list: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`
   § Self-provisioning specialists), INVOKE `git-toolkit:git-ops` to create a dedicated
   worktree/branch, inject its path into the node's `inputs`, and `write(RUN)`. NEVER dispatch a
   source-writing node against the principal checkout. A node writing only under the
   `$ODOO_AI_HOME` state root (e.g. `odoo-code-review` at `TARGET=local`) is NOT provisioned.

## Inputs

- An active `<ISOLATE_DIR>/run-<id>.json` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
  `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
  never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit; schema: harness §8.3).
- `autonomy` ∈ {auto (default), step, plan} read from that file.
- `repos[]` from that file: one entry per repository the run touches, each carrying that repo's Repo
  Capability Card (`id`, `base`, `verify`, `commit`, `confidential`, `worktree_root`). A single-repo
  run is a ONE-ENTRY list. **N repos = N `integrate` nodes = N PRs.** `id` is ORIGIN-DERIVED, so one
  repository always yields ONE id (resolution + collision: run-integration.md § Repo Capability Card
  Template; § Run start step 2 re-derives it).
- Each node's `repo` names one of those `id`s. **`repo: null` is legal ONLY for a node that writes
  into no repository tree and gates no repo's delivery** - the chat-only `inline` synthesis / routing
  / report node (rule owner: harness §8.3 § `repo: null` legality). Every source-writing, `integrate`
  and lifecycle node (verify, review, i18n, acceptance, doc, monitor, merge) MUST name a declared
  `id`; § Plan agreement check 2 proves it before every dispatch - never let an illegal one pass as
  "outside every repo's scope".

## Run start

Runs ONCE, before the first node, in this order. Nothing else creates the integration branch every
node's worktree forks from, and nothing else calls the sweep. Recipe:
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Run start procedure.

1. **Sweep FIRST**, before this run writes anything under its own
   `<ISOLATE_DIR>/integration/<slug>/`: call the stale-integration-dir sweep - fail-closed and
   run-status-correlated, never a bare mtime check (`run-integration.md`
   § Stale integration-dir sweep).
2. **Then fork, ONE branch + worktree pair PER ENTRY in `RUN.repos[]`** (a one-entry `repos[]` = one
   pair): invoke `git-toolkit:git-ops` to add worktree
   `<that entry's worktree_root>/run-integration` on branch `run-integration-<slug>`, based on that
   entry's `base`/principal. Re-derive each entry's `id` from the live `origin` and collapse two
   entries resolving to one id into ONE card before forking anything (§ Inputs).
   **Existence precheck, MANDATORY before the fork** - a crash-resume re-enters here looking exactly
   like a first start (`budget.nodes_run == 0`, no `RUNNING` node), so DERIVE this entry's
   branch/worktree state through `git-toolkit:git-ops` and ADOPT what is already there instead of
   forking a second (Invariant 1). Same shape as the land tail's, read locally:
   `run-integration.md` § Run start procedure > Existence precheck.

**The three lineage invariants - hold them, never re-derive them per node.**

1. ONE run-integration branch per repo, forked ONCE at step 2 - no per-node or per-stage integration
   branch, and never re-forked mid-run.
2. Every source-writing node's worktree forks THAT branch, of the node's OWN `repo` - never
   `base`/principal, never another repo's. It already carries every prior node's commit, so a
   dependent node's worktree CONTAINS its dependencies' source; getting that source onto a
   verification instance's addons-path still needs `WORKTREE_PATH` +
   `SELF_PROVISION: worktree-addons` on the brief.
3. Every commit a node returns cherry-picks back onto that same branch, as a saga with per-node
   verify + checkpoint. That branch is what the repo's terminal `integrate` node squashes and pushes
   - a commit that never reaches it never ships.

**Single-unit collapse.** COUNT the source-writing nodes whose `repo == R`; never infer it from an
absent field. At exactly ONE, dispatch straight into that repo's `run-integration` worktree and let
it commit there - no child worktree, no cherry-pick, no per-node checkpoint. Rule + why `n >= 2`
keeps the child worktree: `run-integration.md` § Single-unit collapse (ONE owner).

All git here runs through the `git-toolkit:git-ops` skill - never a raw git mutation inline.

## The loop

```
RUN_FILE = <ISOLATE_DIR>/run-<id>.json   # resolve WHICH run ONCE, out here: the active run; if
                        # several, the one intake just wrote / the user named

loop:
    RUN = read(RUN_FILE)    # RE-READ the run file from disk at the TOP of EVERY iteration - the file
                        # on disk wins over anything you remember from earlier in this run.
    if RUN.schema_version != "run/2.0":
                        # `run/2.0` is the CURRENT stamp and the ONE value this loop drives.
                        # `run/1.0` and older = the retired pre-5.0.0 schema (it carried
                        # `nodes[].gate_tier`/`topology`/`cumulative_modules`); an unknown NEWER
                        # stamp is refused the same way.
        set RUN.status = "NEEDS_CONTEXT"    # Do NOT drive it; do NOT guess a translation.
        blocked_reason = "run file is not schema run/2.0 - re-plan via odoo-planning to re-serialize"
        write(RUN); break   # report NEEDS_CONTEXT, ask the human for a re-plan.
    if RUN.status != "NEEDS_NEXT": break

    if RUN.budget.nodes_run >= RUN.budget.max_nodes:        # runaway guard
        set RUN.status = "BLOCKED"; blocked_reason = "node budget exhausted - human review"; write(RUN); break

    node = pick_ready(RUN)  # READY = every depends_on is DONE; topo-order; tie -> lowest node id
                        # (lexicographic on the id string - deterministic across resumes;
                        # `confidence` is a dynamic-next[] field, NOT a static-node field)
                        # `integrate@R` carries an EXTRA readiness predicate - evaluate it HERE,
                        # scoped by node.repo (§ integrate readiness)
    if node is None:        # nothing ready but not all done -> cycle / deadlock
        set RUN.status = "BLOCKED"; blocked_reason = "no ready node (dependency cycle?)"; write(RUN); break

    verify_plan_agreement(node)     # FIVE checks (§ Plan agreement below): each AGREES, or STOPS
                        # the run BLOCKED and routes back to odoo-planning.

    tier = gate_tier(node)  # TOTAL FUNCTION - § Gate-tier resolution. There is no stored tier.
    if RUN.autonomy == "step": tier = max(tier, "L1")   # --step gates everything >= L1
    if tier == "L2":        # ALWAYS human - emit gate, end turn, resume after approve/skip/cancel
        emit_human_gate(node); wait     # on cancel -> mark SKIPPED/stop per user
    elif tier == "L1" and RUN.autonomy != "auto":
        emit_human_gate(node); wait
    # else (L0, or L1 under --auto within budget) -> auto-pass; append to gate_log

    node.status = "RUNNING"; write(RUN)
    provision_worktree_if_needed(node)  # Hard rule 6 + Run start invariant 2: SOURCE-writing, no
                        # worktree, not self-provisioning -> git-ops forks one FROM this repo's
                        # run-integration branch; inject into node.inputs; write(RUN)
    dispatch(node):         # ONE node per iteration; this loop NEVER has two dispatches in flight.
                        # Every branch below is a synchronous call in THIS context; nothing here
                        # batches, groups, or advances nodes together - concurrency exists only
                        # INSIDE a dispatched spawner skill. Compose EVERY brief from the caller-side
                        # skeleton in ${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md (read it by
                        # path) plus the target agent's family delta - never inline it verbatim.
        - skill (leaf)      -> Skill tool inline; NL-dispatch is the fallback
        - skill (spawner)   -> invoke the SKILL via Skill tool; the skill fans out its
                               own agent (e.g. odoo-code-reviewer) via launch subagent
        - skill, approach == "odoo-instance"
                            -> § Verification dispatch below
        - workflow          -> hand the YAML name to workflow-chaining
        - integrate         -> the land tail, ONCE PER REPO: § `integrate` node dispatch (the land tail)
                               below - lint gate, THEN Existence precheck, THEN squash/push/open ONE PR
        - inline            -> do the small synth step yourself
    # turn typically ends here for any subagent/agent dispatch; SubagentStop hook nudges resume

    contract = read_continuation_contract(node)
                        # SPAWNER node (skill invoked in `main`, owns its own workers you do not
                        # track): read its in-context AGGREGATE result inline. LEAF agent: read the
                        # contract from your own launch call's returned result, NEVER the `.output`
                        # transcript (snippets/spawner-completion-contract.md R3).
    node.contract = contract
    node.produced = contract.produced
    node.status   = map(contract.status)
                        # DONE | NEEDS_NEXT->DONE (next[] already materialized into dynamic_nodes
                        # above) | FAILED->retry<3 else BLOCKED | BLOCKED | NEEDS_CONTEXT. NO
                        # parseable contract -> FAILED (counts toward the 3-strike cap); never mine
                        # the transcript for a status.
    if node wrote source and returned a commit SHA:
        cherry_pick(sha, into = repos[node.repo].run_integration)
                        # Run start invariant 3 - saga + verify + checkpoint per
                        # references/run-integration.md § Run start procedure
    for nx in contract.next:    # SUGGEST -> CHAIN ; cross-workflow on_complete lands here too
        if (nx.confidence or 0) >= 0.5 and not duplicate(nx) and within_budget:
            RUN.dynamic_nodes.append(materialize(nx))
                        # new READY node, depends_on = node; the tier function returns L2 for ANY
                        # dynamic node - human-gated, never auto-approved (GATE E-4)
        else:
            note_as_suggestion(nx)  # low-confidence / dup -> surface to human, do not auto-run
    RUN.budget.nodes_run += 1
    RUN.status = rollup(RUN)    # NEEDS_NEXT while any reachable node is not DONE
    write(RUN)

# Completion Contract (#8): terminal report with evidence
finalize: RUN.completion = {status, evidence: flatten(all produced), summary}; write(RUN)
emit terminal report (DONE | BLOCKED | NEEDS_CONTEXT), one evidence pointer per claim
```

## Plan agreement (`verify_plan_agreement`)

Five checks, before every dispatch: 1-4 are PURE FUNCTIONS of plan fields - no tool, no lookup; 5
compares a plan field against a runtime observable. Each either AGREES, or STOPS the run BLOCKED
naming the offending plan field. Never substitute, re-partition, re-order or re-plan.

1. **File-scope disjointness.** No two nodes' `files-in-scope` globs may overlap. Overlap -> STOP
   BLOCKED naming both node ids and the shared path and **route back to `odoo-planning`**; never
   guess an owner, never create a worktree first.
2. **`repo: null` legality.** A `repo: null` node MUST be chat-only `inline` with no file outputs
   (§ Inputs). Illegal -> STOP BLOCKED naming the node and **route back to `odoo-planning`**; never
   silently exclude it from a repo's scope.
3. **Module presence.** Every node whose `approach` touches source MUST carry a non-empty
   `node.modules`; never resolve those names yourself - the planner did, and the dispatched skill
   does again where the grounding is. Missing, or a dispatch returning BLOCKED on an unresolvable
   module -> STOP BLOCKED naming node + module and **route back to `odoo-planning`**; do not retry,
   do not substitute.
4. **Verification floor.** `node.approach == "odoo-instance"` -> `node.modules` MUST cover the union
   of `modules` over that node's transitive `depends_on` closure. BELOW -> STOP BLOCKED naming the
   missing modules and **route back to `odoo-planning`** to re-scope. ABOVE is the planner's
   deliberate widening (`skills/_shared/regression-scope.md`) - run it.
5. **Plan staleness.** Before ANY worktree is created: STALE = repo `R`'s `base` tip is no longer the
   commit Run start forked `run-integration-<slug>` from (a bounded `git-toolkit:git-ops` read of
   both). STALE -> STOP BLOCKED naming `base`, both commits and the pending nodes, record both in
   `produced`, and **route back to `odoo-planning`** to re-plan against the current tree; never
   re-derive the plan against the moved tree and never proceed on the stale one. An unresolvable fork
   point is an open finding, never agreement.

Per `${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`, run-harness keeps a live task
list of the RUN-DAG nodes it dispatches (one item per node, title = node id), mirroring
`RUN.nodes[].status` for human visibility, never redefining it; update both together on every status
change. Fires whenever a task-list tool is available in run-harness's own toolset; use whatever
primitive the runtime exposes.

Every gate this loop emits (`emit_human_gate`, the dynamic-node preview, the pre-PR lint gate, the
terminal report) is chat-facing: write it in the USER'S language (translate the prose; keep node ids,
module names, paths, skill names, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

## Gate-tier resolution

**The tier is a TOTAL FUNCTION - nobody authors it.** A node carries NO `gate_tier` field. Resolve
every node, of every `approach_kind`, here:

```
gate_tier(node):
    if node.approach_kind == "inline":     return L0     # chat-only synthesis, writes nothing
    if node.approach_kind == "integrate":  return L1     # the land tail: opens a PR, rewrites
                                                         # nothing; drive-to-done under --auto
    if node.approach_kind == "skill":    t = registry default_gate_tier(node.approach)  # skill_tool_deps.json
    if node.approach_kind == "agent":    t = that registry's `agents.<node.approach>` default_gate_tier
    if node.approach_kind == "workflow": t = HIGHEST `gate_tier` over the `phases[]` of
                                             `workflows/<node.approach>.workflow.yaml`
    if t is UNDEFINED (no such entry): t = L2   # unknown risk is NEVER auto-passed
    if node is DYNAMIC (not in the approved plan): t = L2
    else if THIS driver composed the dispatch brief itself AND that brief names a database this run
            creates and destroys (MODE: fresh + PERSIST: ephemeral + SELF_PROVISION: worktree-addons):
            t = min(t, L1)                               # the EPHEMERAL CEILING
    return t
then: --step raises the floor to L1; --auto lets L0 and L1 auto-pass within budget. L2 NEVER lowers.
```

**The ephemeral ceiling.** The registry marks a skill L2 when its instance touch could be on a
SHARED database - shared is what makes a touch irreversible. You know this touch is NOT shared
**because you wrote the brief**: `MODE: fresh` + `PERSIST: ephemeral` means the database is one this
run creates and destroys and nothing outside the run can observe it. That is the ONLY condition that
lowers a tier. A node dispatched to a skill owning its own instance policy (`odoo-i18n`,
`odoo-acceptance`) keeps its registry L2 - you did not write its brief. The ceiling reaches exactly
one node kind today: `approach: odoo-instance`, via § Verification dispatch, the only place this
driver composes an instance brief.

**Where the gate sits, by node class** (the exact preview block: `run-integration.md` § Gate-tier
node classes):

- **Source-writing node** (source tree, not the `$ODOO_AI_HOME` state root): the BINDING gate is
  HERE, at the driver, before dispatch - a worker subagent cannot pause for a human, so a skill's
  internal Phase-0 gate is only a safety-net. A spawner writing solely under `$ODOO_AI_HOME`
  (`odoo-code-review`, `odoo-ui-review`) needs no gate beyond its registry tier.
- **Static node** (in the Plan-Mode-approved DAG): Plan-Mode approval IS the human gate → auto-pass
  under `--auto` at L0/L1.
- **Dynamic node** (from `next[]` / `on_complete` at runtime, never in the approved plan): the
  function returns **L2**, so `--auto` cannot auto-pass it (GATE E-4 all-dynamic-L2). Emit that
  preview block and **END YOUR TURN** before dispatching.

## Verification dispatch

For a node whose `approach` is `odoo-instance`, compose the brief YOURSELF - never delegate it - from
the `dispatch-brief.md` skeleton named in § The loop, filling every field of
`run-integration.md` § Verification Brief Template. `node.modules` IS the suite scope; `MODE: fresh`
+ `PERSIST: ephemeral` + `SELF_PROVISION: worktree-addons` are mandatory, and writing them yourself
is what makes the touch EPHEMERAL - the basis of the ceiling in § Gate-tier resolution. DONE only on
a GREEN verdict from the returned `instance-ops` block; `failed > 0` or `tests-inconclusive` is
FAILED, never DONE. Record the `run-integration` tip it verified in `produced` - clause (iii)
compares against it.

## integrate readiness

A PREDICATE evaluated at `pick_ready`. **`R` is the node's own `repo` field** (harness §8.3; one
`integrate` node per `RUN.repos[]` entry).

**`integrate@R` is READY only when ALL THREE clauses hold.**

**(i)** EVERY node whose `repo == R` and which is NOT in the land-tail set
`{integrate, monitor, merge}` is **DONE or SKIPPED**. Dynamic nodes materialized at runtime COUNT -
evaluate over the live node set, never over what the plan happened to name. The land-tail carve-out
is MANDATORY - never "simplify" it away: `monitor` depends on `integrate`, so a rule phrased "every
OTHER node in the repo must be DONE" deadlocks EVERY run. Another repo's nodes are outside this scope
(a slow second repo never holds this PR hostage), and so is a legal `repo: null` node (§ Plan
agreement check 2 proved that legality).

**(ii)** At least one node with `approach: odoo-instance`, `repo == R`, on `integrate@R`'s transitive
dependency path, is **DONE** - and the union of the `modules` it ran covers every module named in any
`modules` list among R's coding nodes, including any dynamic coding node that landed source in R.

**`SKIPPED` never satisfies clause (ii).** A cancelled or skipped verification is an ABSENT
verification. When clause (i) holds and clause (ii) does not, STOP BLOCKED with
`blocked_reason: "no green verification covers <modules> in <R> - the PR will not open on an
unverified tree"` and route back to `odoo-planning` to add or re-scope the node.

**(iii) A MUTATED TREE INVALIDATES ITS VERDICT.** ANY commit landed on `R`'s `run-integration` after
the clause-(ii) node closed GREEN voids that verdict - clause (ii) stays UNSATISFIED until that node
is re-dispatched and closes GREEN over the CURRENT tip. DERIVE it, never assume: the tip in that
node's `produced` against `R`'s live tip. Evaluate HERE, and AGAIN in the land tail once the lint
gate cherry-picks a fix - `run-integration.md` § Pre-PR tail > Verdict currency.

**The plan's `integrate.depends_on` is a FLOOR, not the rule.** When the plan named fewer nodes than
clause (i) requires, record an ADVISORY finding naming the missing ids and proceed on the derived
set. Never STOP BLOCKED on a narrower `depends_on`, and never widen a plan-named dependency into a
land-tail node - that deadlocks. The floor is what keeps the PR from opening ahead of the doc /
review / acceptance nodes when the plan under-specified it.

## `integrate` node dispatch (the land tail)

Dispatched ONCE PER REPO (`integrate@R`), once § integrate readiness holds. In order:

1. **Pre-PR lint-class gate FIRST (MANDATORY, before the Existence precheck).** Dispatch NO terminal
   stage here: `review`, `i18n`, `acceptance`, `doc`, `monitor`, `merge` are ORDINARY PLAN NODES
   `pick_ready` dispatches like any other, and clause (i) already proved the pre-PR ones terminal -
   re-driving one doubles a human gate and re-runs a side-effecting stage. Run ONLY this driver's OWN
   pre-PR lint-class gate - the ONE tail step no node carries - over repo `R`'s integration-branch
   aggregate diff, with `GATE_ROLE: pre-pr-lint-gate`. Its fields, its containment loop, and the
   stage ORDER the PLAN copies: `run-integration.md` § Pre-PR tail (ONE owner). A fix that loop
   cherry-picks re-opens clause (iii): satisfy it before step 2.
2. **Existence precheck (MANDATORY, BEFORE any push or PR-open).** The land tail must be safe to run
   twice: read `R`'s remote state through `git-toolkit:git-ops` and DERIVE `first-push` from it,
   never assert it. **An already-open PR IS this repo's ONE PR - UPDATE it, never open a second.**
   The two facts, the 3-case matrix and the rewrite-history gate: `run-integration.md` § Squash
   Tree-Identity Recipe.
3. **Land.** Invoke `git-toolkit:git-ops` from the main context to squash repo `R`'s run-integration
   branch, push it to the fork, and open ONE PR against `R`'s `base`. Do NOT materialize an
   `odoo-pr-monitoring` node here - the plan's own `monitor` and `merge` nodes depend on this one and
   `pick_ready` takes them next; `merge` is L2 from the registry, so the human approves it even under
   `--auto`. `odoo-coding` never pushes or opens a PR. No local merge into the principal, no
   auto-merge. Drive-to-done STOPS at "PR opened".
   **Exactly ONE PR per REPO per run**, and no intermediate PR is ever opened.

## Circuit-breakers (anti-runaway, anti-trap)

- `budget.max_nodes` hard cap → BLOCKED.
- Dedup `dynamic_nodes` by (skill + inputs) - re-suggested already-run nodes dropped.
- `confidence < 0.5` next[] → surface as suggestion, do not auto-materialize.
- Node FAILED 3× → BLOCKED (escalate, don't retry forever).
- Cycle detection in `pick_ready`.
- User abort phrase ("stop", "dừng", "abort the run") → BLOCKED with reason="user abort".

## Resume

Re-entry reads `run-<id>.json`, skips `DONE` nodes, and continues at the first `READY` node in
topo-order (same contract as BRL checkpoint, harness §3.3 / §8.3). Run start is re-entered too - its
own Existence precheck (§ Run start step 2) is what stops a resume forking a SECOND integration
branch.

**A `RUNNING` node on re-entry means DISPATCHED, OUTCOME UNKNOWN - never re-dispatch it blindly.**
`RUNNING` is persisted BEFORE dispatch, so the step may have fully run, half-run, or never started,
and its `depends_on` are all `DONE`, so `pick_ready` would otherwise dispatch it a SECOND time.
Before `pick_ready` may consider ANY node, RECONCILE every `RUNNING` node against OBSERVABLE reality
- its declared outputs on disk, and for a node carrying a `repo`, that repo's state through
`git-toolkit:git-ops` (bounded reads: branch present? its commits there? a PR already open?) - then
set exactly ONE status and `write(RUN)`: **DONE** when the work and its evidence are fully present
(record them in `produced`); **READY** when nothing landed, so re-dispatch is safe; **BLOCKED** when
the effect is PARTIAL - record what exists in `produced`, `blocked_reason` naming what is missing,
and report; a partial node is never re-dispatched on a guess. Reconcile from what is observable,
never from the transcript or from what you remember dispatching. An `integrate` node reconciles
through its own § Existence precheck, so a resumed land tail UPDATES this repo's already open PR
instead of opening a second one.

## Standalone-first fallback

No OSM dependency - pure orchestration over `run-<id>.json`, reachable OSM or not; grounding is each
dispatched specialist's concern. A missing or unreadable blackboard file -> report `NEEDS_CONTEXT`,
never fabricate a DAG.

## Continuation Contract

When this loop yields control (a terminal state, or a gate awaiting the human), append a Continuation
Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` reflecting `RUN.status`.
