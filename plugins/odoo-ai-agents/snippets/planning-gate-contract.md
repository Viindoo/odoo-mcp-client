<!-- SSOT snippet. Owned by odoo-planning. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md; edit here only. -->

# Planning Gate Contract

## Gate reply keywords (two sets, no others)

- PLAN gate (a whole plan or design is on the table; the user may iterate on it):
  `approve / refine: [feedback] / cancel`
- STEP gate (one node, phase or dispatch is on the table; the choices are do or skip):
  `approve / skip / cancel`

Never invent a third set; `yes` is not a gate keyword. Every gate prompt (a text question before a
plan, the plan gate, a confirmation before an outward action) uses one of these two sets verbatim.

## Mandatory-planning rule

Planning is enforced at ADMISSION: the FRONT DOOR (`odoo-intake`, `odoo-brl`, or the
`odoo-implement-feature` workflow) MUST establish an **approved plan artifact in scope** before it
dispatches any executor (`odoo-coding`, its `odoo-coder` and the leaves it launches) for any
code-writing work, trivial included. Only DESIGN, via `odoo-solution-design`, may
be skipped: it is RECOMMENDED for non-trivial work, never required. Checked ONCE, at the door; executors never re-check it. It is TRUE
when any signal of § Approved-plan-artifact detection is present.

- **Front door routes non-trivial work through `odoo-planning` first** - it does not dispatch a raw
  coder. Non-trivial work SHOULD go `odoo-solution-design` -> `odoo-planning` - a front-door
  PREFERENCE, not a precondition; a one-approach change, or any change whose design was skipped,
  still flows through `odoo-planning` (which emits the minimal
  `[code, verify, review, integrate, monitor, merge]` plan). The front door HARD BLOCKS code with no
  PLAN. The ONLY lone-design bypass is the § Migration carve-out.
- **The executor consumes the established signal** - once the front door has established a signal
  the plan already stands, and the executor proceeds on the plan-provided fast-path. The fast-path
  is NOT re-gated. An executor invoked standalone (no signal) self-derives a single-step change and
  proceeds; work that needs a multi-step plan follows § One Plan-Mode gate per request, rule 6.

For cross-run/worktree NEW-module coordination, the same three defer to the single ledger SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` (written only by `odoo-coding`).

## Approved-plan-artifact detection

The front door ESTABLISHES one of these three signals before it dispatches an executor; the executor
merely CONSUMES the signal it is handed. Any of the three means an approved plan artifact is in scope:

1. **Active `run-<id>` blackboard** - dispatched under a named `run-<id>` (the `odoo-intake` Phase P
   serialization). The `odoo-planning` ExitPlanMode approval already stands.
2. **`WORKTREE_PATH`** - a pre-approved worktree path handed down by the plan runner when it
   provisions a node's worktree. The plan gate already stands.
3. **Plan-provided inter-module `inputs`** - the Continuation-Contract `inputs` carry the plan's
   already-computed inter-module results: the target module set + the node DAG +
   the design pointers (`design_index`/`design_doc`/`design_docs`).

## Migration carve-out

A FRONT-DOOR routing decision, owned by `odoo-solution-design`. It is the ONLY case a lone
`design_doc` (no `run-<id>`, no `WORKTREE_PATH`, no plan-provided `inputs`) satisfies the
mandatory-planning rule. When choosing its Continuation-Contract `next`, `odoo-solution-design` MAY
route directly to `next: odoo-data-migration` (or `next: odoo-coding` for the migration script),
bypassing `odoo-planning`, IFF ALL THREE conditions hold:

1. the design is a data/schema **migration script** for a module that was `installable` before the change; AND
2. it touches **exactly ONE module** (no new sibling module, no in-set `depends` edge added); AND
3. it has **no multi-layer `dag_layers`** (a single layer).

Any richer design (multi-module OR multi-layer) FAILS the carve-out: `odoo-solution-design` routes
it to `next: odoo-planning` instead. The executor that later receives the lone `design_doc` does NOT
re-validate the carve-out.

## One Plan-Mode gate per request

A user request gets exactly ONE Plan-Mode approval. The component that produces the request's
concrete execution plan owns it:

- `odoo-planning`, over the execution plan of work routed through it;
- a self-planning skill that owns the request, over its own plan: `odoo-forward-port` (P4),
  `odoo-git-rebase` (P6), `odoo-modules-upgrade` (P3), `odoo-doc-site` (page plan),
  `odoo-doc-illustration` (section plan);
- `workflow-chaining`, over the workflow plan of a workflow that owns the request.

A skill owns the request when it is invoked for the user's request itself, by the user or by
`odoo-intake`. A skill runs under an approved plan when it is a plan node, a workflow phase, a step
of another skill's run, or invoked with `return_to` (the caller owns the gate).

1. Before the plan exists, ask every human question - intent, scope, approach, the SRS review, the
   design review - as a text question with the reply words above. `odoo-intake` never enters Plan
   Mode. Before any gate the owner reads the artifact and its review in full, settles every
   question a rule already answers, and asks only those with two materially different readings,
   each with a recommendation and a default; an agent's questions are never forwarded unread. A
   gate presents the current state with its evidence (file and symbol), each option's consequence
   per role (who does, sees and pays what), and a reasoned recommendation.
2. The owner authors its plan first: a plan written only under the `$ODOO_AI_HOME` state root needs
   no open Plan Mode, and no state-root-writing subagent is launched while Plan Mode is open. Then
   it calls `EnterPlanMode`, presents the plan, and calls `ExitPlanMode` when the user approves -
   before any branch, worktree, git-tracked write or deletion. A rejected `ExitPlanMode` leaves
   Plan Mode open: fold a `refine` into the harness plan file yourself and present again; no
   writing subagent until the approval. The plan names the documentation target when the run
   documents, and every outward or irreversible action it will take.
3. Under an approved plan nothing enters Plan Mode again and no node or phase stops for approval.
   A skill that owns a plan gate when standalone writes its plan into its report instead.
4. A confirmation before an outward or irreversible action - send, publish, merge, push, delete - is
   a text question with the reply words above.
5. `EnterPlanMode`/`ExitPlanMode` are main-context tools; a subagent never calls them.
6. No approved plan yet and the work turns out to need a multi-step plan: stop the work and invoke
   `odoo-planning`; its gate is the request's one Plan-Mode approval.
7. Under an approved plan, decide everything inside its scope yourself and never ask (rule 4
   confirmations excepted). Work outside it: re-plan through `odoo-planning`; that approval
   covers only the added scope.

The self-planning skills author their plan in-skill; they neither route it through
`odoo-planning` nor are plan nodes of it.

**Design before planning.** When a design exists, run `odoo-planning` after
`odoo-solution-design` and consume its approved output. A design is an input to a plan, never a
node of one.

## Execution adherence

An executor (`odoo-coding`, or the plan runner) that was handed an approved plan follows its
**`depends_on` order**, **module set**, and **per-node skill** EXACTLY. On ANY drift from that plan -
a dependency the plan's module-DAG did not declare, a module missing from the plan, or a node whose
real work needs a different skill - the executor STOPS and re-plans through `odoo-planning`
(§ One Plan-Mode gate per request, rule 7), which re-renders the module-DAG from the corrected
`dag_layers`. It NEVER improvises a new edge, module, or skill assignment.
