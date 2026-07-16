<!-- SSOT snippet. Owned by odoo-planning. The single source of truth for the mandatory-planning
     gate, enforced at ADMISSION: the FRONT DOOR (odoo-intake / odoo-brl / the odoo-implement-feature
     workflow) establishes an approved plan artifact before it dispatches any executor; executors
     TRUST that upstream governance happened and never self-block for "no plan". Referenced (not
     copy-pasted) by odoo-intake, odoo-coding, run-harness, odoo-solution-design, and the workflow
     YAML. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md. -->

# Planning Gate Contract

Planning is MANDATORY for ALL work that writes code, and it is enforced ONCE at the ADMISSION point
(the front door), never re-checked inside executors. There is NO trivial/size/module-count bypass
that lets the front door admit code-writing work without a plan. A single-module change is not an
exception - the front door flows it through `odoo-planning`, which emits the minimal
`[code, review, integrate]` plan for it. The SOLE lone-design exception is the gated migration
carve-out below (§ Migration carve-out).

## Mandatory-planning rule

Planning is enforced at ADMISSION: the FRONT DOOR (`odoo-intake`, `odoo-brl`, or the
`odoo-implement-feature` workflow) MUST establish an **approved plan artifact in scope** before it
dispatches any executor (`odoo-coding`, its `odoo-coder` per-module coordinator (every module) - and
that coordinator's `odoo-backend-coder`/`odoo-frontend-coder` hard-leaf workers) for any code-writing work (trivial included - a trivial change still gets the minimal
plan; only DESIGN, via `odoo-solution-design`, is reserved for non-trivial work). Checked ONCE, at the door. "Approved plan
artifact in scope" is TRUE when ANY of the three signals in § Approved-plan-artifact detection is
present. The resulting invariant - no executor ever writes code without an approved plan artifact in
scope - is GUARANTEED by the front door's admission decision, NOT re-checked by each executor:
executors TRUST that upstream governance happened, which keeps them composable and removes the
runtime contradiction of a per-stage self-gate.

- **Front door routes non-trivial work through `odoo-planning` first** - it does not dispatch a raw
  coder. A design-required change goes `odoo-solution-design` -> `odoo-planning` first; a
  one-approach change still flows through `odoo-planning` (which emits the minimal
  `[code, review, integrate]` plan). Admission would otherwise let code be written with no plan, so
  the front door HARD BLOCKS that path and routes to `odoo-planning`. The ONLY lone-design bypass is
  the § Migration carve-out.
- **The executor consumes the established signal** - once the front door has established a signal
  the plan already stands, and the executor proceeds on the plan-provided fast-path. The fast-path
  is NOT re-gated (re-gating a signalled invocation would stall `run-harness`'s between-wave
  sequential per-module loop); an executor invoked standalone (no signal) self-derives and proceeds - it never self-blocks
  for "no plan".

This is the SAME three-signal set `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` (its
plan-provided fast-path) keys on - intake, `odoo-coding`, and `run-harness` all cite THIS one
definition; they do not restate it.

For cross-run/worktree NEW-module coordination, the same three defer to the single ledger SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` (written only by `odoo-coding`).

## Approved-plan-artifact detection

The front door ESTABLISHES one of these three signals before it dispatches an executor; the executor
merely CONSUMES the signal it is handed - it does NOT detect whether it was handed a plan and then
block on its absence. The three signals - naming each ONCE - any of which means an approved plan
artifact is in scope:

1. **Active `run-<id>` blackboard** - dispatched under a named `run-<id>` (the `odoo-intake` Phase P
   -> `run-harness` chain). The `odoo-planning` ExitPlanMode approval already stands.
2. **`WORKTREE_PATH`** - a pre-approved worktree path handed down by `run-harness` (the between-wave
   integration path). The driver L2 gate already stands.
3. **Plan-provided inter-module `inputs`** - the Continuation-Contract `inputs` carry the plan's
   already-computed inter-module results: the target module set + the wave-batched module-DAG +
   the design pointers (`design_index`/`design_doc`/`design_docs`).

## Migration carve-out

A FRONT-DOOR routing decision, owned by `odoo-solution-design`. It is the ONLY case a lone
`design_doc` (no `run-<id>`, no `WORKTREE_PATH`, no plan-provided `inputs`) satisfies the
mandatory-planning rule. When choosing its Continuation-Contract `next`, `odoo-solution-design` MAY
route directly to `next: odoo-data-migration` (or `next: odoo-coding` for the migration script),
bypassing `odoo-planning`, IFF ALL THREE conditions hold:

1. the design is a data/schema **migration script**; AND
2. it touches **exactly ONE module** (no new sibling module, no in-set `depends` edge added); AND
3. it has **no multi-layer `dag_layers`** (a single layer).

Any richer design (multi-module OR multi-layer) FAILS the carve-out: `odoo-solution-design` routes
it to `next: odoo-planning` instead - the bypass is denied at the door. The executor that later
receives the lone `design_doc` does NOT re-validate the carve-out on arrival; admission was decided
once, by `odoo-solution-design`.

## Plan-Mode enter/exit + `plan_mode_active`

`EnterPlanMode`/`ExitPlanMode` are main-context harness tools - the orchestrating agent (e.g.
`odoo-intake`, `odoo-planning` running in the main context) can call them; a subagent cannot.

`plan_mode_active` is a boolean dispatch-brief flag (SSOT for its meaning is HERE). A caller sets it
to `true` ONLY when it holds Plan Mode open across the dispatch to the callee; otherwise it is
omitted (treated as `false`).

- **Enter iff `plan_mode_active` absent/false** - Plan Mode is not yet open; call `EnterPlanMode`
  before presenting the plan.
- **Skip iff `plan_mode_active: true`** - a caller already opened Plan Mode for its OWN reason
  (genuinely holds it open across the dispatch, not to pre-open on behalf of the callee - see the
  WHEN bullet below). Do NOT call `EnterPlanMode` again here - not because the harness call itself
  would fail (a redundant call is a harmless no-op, see § Enter is conditional and defensive below),
  but because calling it would violate the single-actor enter/exit ownership this contract pins: the
  caller that set `plan_mode_active: true` is the enterer of record, not the callee.
- **Exit** - on `approve`, the enterer calls `ExitPlanMode` to surface the plan for human approval.
- **WHEN - enter BEFORE authoring, not only before presenting.** `EnterPlanMode` MUST be called
  BEFORE ANY plan-content authoring or any dispatch that produces the plan being reviewed - never
  after the plan artifact already exists on disk. Exactly ONE actor calls it for a given plan: the
  plan-authoring skill running in the MAIN context (the lifecycle plan -> `odoo-planning`; a
  specialized git/upgrade plan -> the self-gating orchestrator that authors it). A caller MUST NOT
  pre-open Plan Mode on behalf of the plan author and then dispatch it - the author owns its own
  enter/exit, so the enter cannot be misordered by an upstream caller. `plan_mode_active: true` is
  passed ONLY by a caller that genuinely already holds Plan Mode open for its OWN reason (not to
  wrap the plan author); the callee then skips its own enter to avoid a double-enter harness error.
- **Enter is conditional and defensive.** The plan-authoring skill enters Plan Mode IFF
  `plan_mode_active` is absent/false AND `return_to` is unset (when a caller requested return
  routing the caller owns the gate) - the two brief-observable conditions; Plan Mode's native
  session state (whether a human already opened it via Shift+Tab / `/plan`) is NOT exposed to
  skills, so it is never a third condition to check. The author calls `EnterPlanMode` to ENSURE Plan
  Mode is open, not to detect whether it already is: if the session is already in Plan Mode, the
  call is treated as a harmless no-op by the harness. Skills cannot and need not detect Plan Mode
  state themselves - defaulting to skip the call on an unsure state would defeat the
  enter-before-authoring guarantee above, so the call is unconditional whenever the two brief fields
  say to make it.

**Reused by the self-driving front doors.** The dispatched-once orchestrators `odoo-forward-port`
(P4), `odoo-git-rebase` (P6), and `odoo-modules-upgrade` (P3) reuse THESE same
`EnterPlanMode`/`ExitPlanMode` mechanics - including the enter-iff-`plan_mode_active`-absent/false
guard above - to run their OWN human-approval gate. They author their SPECIALIZED plan content
(git-history / cluster-upgrade plans) in-skill; they do NOT route that content through
`odoo-planning`, and they are not plan nodes of it.

**Design-then-planning ordering.** `odoo-planning` is DOWNSTREAM of `odoo-solution-design`: when a
change is design-required it runs AFTER design and CONSUMES the approved design output - it is a
downstream consumer, NOT a peer or alternative to design. See § Mandatory-planning rule above for
the design-required (`odoo-solution-design` -> `odoo-planning`) vs trivial (skip design, still flow
through `odoo-planning`) routing.

## Execution adherence

An executor (`odoo-coding`, or `run-harness`'s between-wave integration) that was handed an approved plan follows its **wave order**,
**module set**, and **per-node skill** EXACTLY. On ANY drift FROM THAT APPROVED PLAN - a dependency
discovered that the plan's module-DAG did not declare, a module missing from the plan, or a node
whose real work needs a different skill - the executor STOPS and routes back to `odoo-planning` to
AMEND the plan (re-render the module-DAG dependency-graph from the corrected `dag_layers`). It NEVER
improvises a new edge, module, or skill assignment. This is a plan-adherence property (drift from a
plan you WERE given), NOT a readmission self-gate: an executor with no plan does not stop here - it
self-derives (§ Mandatory-planning rule). The picture the human approved is the picture that gets
built, or the plan is re-approved.
