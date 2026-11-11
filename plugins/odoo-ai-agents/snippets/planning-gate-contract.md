# Planning gate contract

## Gate reply keywords (two sets, no others)

- PLAN gate - a whole plan or design is on the table and the user may iterate:
  `approve / refine: [feedback] / cancel`
- STEP gate - one node, phase or dispatch is on the table, to do or to skip:
  `approve / skip / cancel`

Every gate prompt uses one of the two sets verbatim; `yes` is not a gate keyword.

## Mandatory-planning rule

The front door (`odoo-intake`, `odoo-brl`, the `odoo-implement-feature` workflow) establishes an
approved plan before it dispatches any executor (`odoo-coding`, its coder, their leaves) for
code-writing work, however small. Design (`odoo-solution-design`) is recommended for non-trivial
work and may be skipped; a plan may not: work whose design was skipped still goes through
`odoo-planning`, which emits the minimal `[code, verify, review, integrate, monitor, merge]` plan.
The check happens once, at the door. An executor proceeds on the signal it was handed and never
re-checks it; invoked standalone with no signal, it derives a single-step change itself, and work
that turns out to need several steps follows rule 6 below.

New modules across runs and worktrees are coordinated through
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`, written only by `odoo-coding`.

## Approved-plan-artifact detection

Any one of these means an approved plan is in scope:

1. an active `run-<id>` blackboard (the serialization of the approved plan);
2. a `WORKTREE_PATH` handed down by the plan runner;
3. plan-provided `inputs` in the Continuation Contract: the module set, the node DAG and the
   design pointers (`design_index`, `design_doc`, `design_docs`).

## Migration carve-out

The one case where a lone `design_doc` satisfies the rule: `odoo-solution-design` may route
straight to `next: odoo-data-migration` when the design is a migration script for a module that
was `installable` before the change, touches exactly one module, and has a single `dag_layers`
layer. Any richer design goes to `odoo-planning`. The executor does not re-validate this.

## One Plan-Mode gate per request

A user request gets exactly one Plan-Mode approval, owned by whatever produces its concrete
execution plan: `odoo-planning`; a self-planning skill invoked for the request itself
(`odoo-forward-port`, `odoo-git-rebase`, `odoo-modules-upgrade`, `odoo-doc-site`,
`odoo-doc-illustration`), over its own plan; `workflow-chaining`, over a workflow that owns the
request. A skill that runs as a plan node, a workflow phase, a step of another skill's run, or
with `return_to` is under its caller's gate.

1. Before the plan exists, every human question - intent, scope, approach, the SRS and design
   reviews - is a text question with the reply words above; `odoo-intake` never enters Plan Mode.
   Before any gate the owner reads the artifact and its review in full, settles every question a
   rule already answers, and asks only those with two materially different readings, each with a
   recommendation and a default. An agent's questions are never forwarded unread. A gate presents
   the current state with its evidence (file and symbol), each option's consequence per role (who
   does, sees and pays what) and a reasoned recommendation.
2. The owner authors its plan first (a plan written only under the state root needs no open Plan
   Mode, and no agent that writes there is launched while Plan Mode is open), then calls
   `EnterPlanMode`, presents it, and calls `ExitPlanMode` on approval - before any branch,
   worktree, git-tracked write or deletion. A rejected `ExitPlanMode` leaves Plan Mode open: fold
   the `refine` into the harness plan file and present again. The plan names the documentation target
   when the run documents, and every outward or irreversible action it will take.
3. Under an approved plan nothing enters Plan Mode again and no node or phase stops for approval;
   a skill that owns a gate when standalone writes its plan into its report instead.
4. A confirmation before an outward or irreversible action - send, publish, merge, push, delete -
   is a text question with the reply words above.
5. `EnterPlanMode` and `ExitPlanMode` are main-context tools; a subagent never calls them.
6. No approved plan and the work needs several steps: stop and invoke `odoo-planning`; its gate
   is the request's one approval.
7. Under an approved plan, decide everything inside its scope yourself and never ask (rule 4
   excepted). A regression or defect the run's own change caused is inside the scope, in whatever
   module it surfaces: fix it without asking. Other work outside the plan is re-planned through
   `odoo-planning`, whose approval then covers only the added scope.

A design is an input to a plan, never a node of one: when a design exists, `odoo-planning` runs
after `odoo-solution-design` and consumes its approved output.

## Execution adherence

An executor handed an approved plan follows its `depends_on` order, its module set and its
per-node skill exactly. A drift from it - a dependency the plan's DAG did not declare, a module
the plan lacks, a node whose real work needs another skill - stops the executor and goes back to
`odoo-planning` (rule 7), which re-renders the DAG. The executor never improvises an edge, a
module or a skill assignment.
