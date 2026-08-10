<!-- SSOT snippet. Contract for master-child design decomposition in odoo-solution-architect /
     odoo-solution-design. Referenced (not copy-pasted) by the architect agent, the solution-design
     skill, and every downstream consumer that reads a design handoff (odoo-coding,
     odoo-forward-port, odoo-modules-upgrade P2b). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md. -->

# Master-Child Design Contract

## When to use

**Master-child mode**: scope spans multiple modules or multiple independent business domains each
requiring substantial new or modified modules - decompose into one master TDD + one child TDD per
module.
**Single mode**: single module, or a straightforward change where one flat TDD captures the full
design. Existing layout unchanged; this contract adds nothing for that case.

## Artifact layout

Artifacts live under the Tier-2 SHARE dir (`<SHARE_DIR>` - resolve once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit):

```
<SHARE_DIR>/designs/
  <slug>-<date>.md                 # SINGLE mode - unchanged
  <master-slug>/                   # MASTER-CHILD mode
    index.yaml                     # manifest machine-readable (routing SSOT)
    _master-<date>.md              # master TDD (constraints + cross-module contracts)
    <module>-<date>.md             # child TDD per module; header line 1: `Master TDD: _master-<date>.md`
```

## index.yaml schema (machine-readable routing SSOT)

`index.yaml` is the authoritative file-location registry. Downstream consumers resolve child paths
from it - never by guessing filenames. Paths in `master` and `child_path` are RELATIVE to the
subdir.

```yaml
slug: fleet-billing
created: 2026-06-28
master: _master-2026-06-28.md
modules:
  - name: viin_fleet_billing
    child_path: viin_fleet_billing-2026-06-28.md
    depends_on: []
    dag_layer: 0            # 0 = no intra-design dep; higher = depends on lower-layer modules
    status: pending         # pending | designed | approved | skipped
  - name: viin_fleet_billing_account
    child_path: viin_fleet_billing_account-2026-06-28.md
    depends_on: [viin_fleet_billing]
    dag_layer: 1
    status: pending
dag_layers:
  - [viin_fleet_billing]
  - [viin_fleet_billing_account]
```

`dag_layers` and each entry's `depends_on` + `dag_layer` must be kept in sync - they are the
design's LOGICAL layering (the design's truth). `odoo-planning` is the FIRST consumer of
`dag_layers`: it turns this logical layering into the executable wave-batched module-DAG (the
PLAN). When a plan exists, the coding phase and the git-executor consume that PLAN - not
`dag_layers` directly; `odoo-coding` reads `dag_layers` itself only when running STANDALONE (no
plan). Build order then follows the plan's wave order (standalone: it follows `dag_layers`
top-to-bottom).

**Child-design dispatch is base-first (distinct from `odoo-planning`'s later wave-batching
above).** `odoo-solution-design` dispatches child architects using `dag_layer` as the ordering
axis for the DESIGN step itself: same layer = parallel (Mode B budget), different layer = strict
order - ALL layer-`k` children reach `status: designed` before ANY layer-`k+1` child is
dispatched. A layer-`k+1` child brief carries `UPSTREAM_CHILD_DESIGNS: [...]` (the already-authored
lower-layer child TDDs it `depends_on`) alongside `MASTER_DESIGN_DOC`. This changes DISPATCH ORDER
only - the §10 registry below still front-loads the cross-module CONTRACT so no child blocks on a
sibling for interface discovery; base-first instead reduces `MODE: consistency` rework by letting
a higher-layer child design against an already-concrete lower-layer sibling instead of a
still-shifting one.

## Index selection and path resolution

**Locating the index**: consumers search all `<SHARE_DIR>/designs/*/index.yaml` files. A single
match is used directly. When multiple index files match the current scope:

**Tie-break order** (apply in sequence until unique):
1. Intersection size - choose the index whose `modules` list has the largest intersection with the
   set of changed modules. Larger intersection wins.
2. Recency - if tied on intersection size, choose the index with the most recent `created:` date.
3. Alphabet - if still tied, choose the index whose slug comes first alphabetically.
4. Ambiguity flag - when more than one index.yaml matches after tie-break, ALWAYS emit
   `design_doc_ambiguity: true` plus a list of all candidate index paths before proceeding.

**Path resolution**: `master` and `child_path` values in `index.yaml` are RELATIVE to the
directory containing that `index.yaml` (i.e. `<SHARE_DIR>/designs/<master-slug>/`). Consumers MUST
resolve them to absolute paths (join the index directory + the relative value) BEFORE reading the
files or inserting paths into `DESIGN_DOC` / `MASTER_DESIGN_DOC` fields.

Example: `index.yaml` at `<SHARE_DIR>/designs/fleet-billing/index.yaml` with
`child_path: viin_fleet_billing-2026-06-28.md` resolves to
`<SHARE_DIR>/designs/fleet-billing/viin_fleet_billing-2026-06-28.md` (absolute, under the
resolved SHARE dir).

## §10 Cross-module contracts - shared-symbol ownership registry (in master TDD)

The master TDD contains a **§10 Cross-module contracts** section. Every shared symbol (field,
model, method) referenced by more than one module in this design is listed here. Children cite
this table and honor it; they do not re-own or redefine listed symbols.

Table header (diff-able):

```
| Shared symbol (field/model/method) | Type | Owning module | Consumers | Notes |
```

Three constraints enforced by this section:

1. **Single owner**: each symbol has exactly one owning module. Consumer modules only extend or
   read it - never re-declare it. If ownership is ambiguous, resolve it in §10 before any child
   is written.
2. **Dependency direction**: a consumer module must declare `depends` on (or transitively reach)
   the owning module. A symbol reference without a valid dep is a design defect.
3. **Integration-module rule**: if two sibling modules at the same `dag_layer` need to share a
   symbol, the symbol belongs in a dedicated integration module or a lower-layer shared dep -
   never in either sibling (that would create a circular dep). State the decision explicitly in
   the Notes column.

A single-owner or dependency-direction dispute a child cannot honor as written is contested, not a
child's to decide - record it per § Contested-symbol reconciliation, never silently pick a winner.

Cross-cluster sequencing (which `dag_layer` builds first) must match `dag_layers` in `index.yaml`.

## Contested-symbol reconciliation (same-layer siblings)

Same-layer child architects run concurrently and cannot message each other - no agent can address a
sibling (`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3). Reconciliation is the
LEAD's, after its R1 barrier clears:

- **Child.** When your design needs a shared symbol another module in this layer owns or touches and
  you cannot honor the master §10 contract as written, do NOT block and do NOT guess: record the
  symbol, your proposed contract, and why, in your own TDD AND append one row to
  `<SHARE_DIR>/designs/<master-slug>/contested-symbols.md`. Then finish your TDD on your own
  proposal and report DONE, naming the contested symbol in your report. Frame the row as shared
  design context, never "secret"/"private" (CHP confidentiality guard).
- **Lead.** After every child in the layer has returned, read `contested-symbols.md`. Decide each
  contested symbol against the master §10 contract, write the decision into the master TDD, and
  re-dispatch ONLY the children whose proposal lost, with the decision in their brief. Bound this to
  ONE reconciliation round per layer; unresolved after it -> the layer is BLOCKED for a human.

Lower-layer children and the master have already terminated by fan-out time: a child never debates a
live master or a lower layer - it honors the finished artifact (`MASTER_DESIGN_DOC`,
`UPSTREAM_CHILD_DESIGNS`) and records the disagreement for the lead the same way.

**Single-writer discipline.** NEITHER child edits `index.yaml`/§10 directly: the orchestrating skill
and the `MODE: consistency` pass are the ONLY §10/`index.yaml` writers (a child never re-declares a
§10 symbol - see § single-owner). The MANDATORY consistency pass CONSUMES the recorded proposals and
the lead's decisions and APPLIES them to §10, verifying single-owner / dep-direction /
no-circular-dep still hold before emitting `conflict-list.md`. A child NEVER changes a master §10
constraint; the lead's decision is the only path a seam reaches the human gate.

## Optional independent review (MODE: review)

Both master-child gates (master gate, batch gate) offer an OPT-IN independent review via
`odoo-solution-architect MODE: review` - gate keywords `review-master` / `review-children`,
default `approve`, so review is NEVER a mandatory stop (preserves drive-to-done). Review is a
single adversarial pass by a fresh context that did NOT author the design under review
(context-independence is the anti-bias axis, not agent-type independence); it reads the master
and/or child TDD(s) READ-ONLY, names the single weakest assumption plus a concrete alternative,
and writes `_review-<date>.md` under `<SHARE_DIR>/designs/<master-slug>/` as a FINDINGS list
(severity + alternative) - it never rewrites the TDD or `index.yaml`. Full contract:
`agents/odoo-solution-architect.md` § Review mode.

## Handoff fields (additive; backward-compat with single mode)

`DESIGN_DOC:` = path to the CHILD TDD - the spec the coder builds verbatim. Single mode: path to
the flat doc. Semantics unchanged from the existing contract.

`MASTER_DESIGN_DOC:` = path to the master TDD (hard constraints; see Non-drift rule). Single
mode: `none`.

Continuation Contract in master-child mode - in this mode the **skill** (`odoo-solution-design`,
Decompose branch step f), not the architect agent, owns and emits the CC. The pipeline is
design -> planning -> code, so the default `next:` is `odoo-planning` (the planner consumes
`index.yaml` `dag_layers` and wave-batches the modules before any code is written). When the skill
was invoked with `return_to` set, it emits `next: <return_to>` instead and hands back to the caller:

```yaml
status: NEEDS_NEXT
next: odoo-planning
inputs:
  design_index: <SHARE_DIR>/designs/<master-slug>/index.yaml
  master_design_doc: <SHARE_DIR>/designs/<master-slug>/_master-<date>.md
  design_docs:
    - module: <module-name>
      child_path: <SHARE_DIR>/designs/<master-slug>/<module-name>-<date>.md
```

All paths are absolute (rooted at the resolved `<SHARE_DIR>`, per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` - never repo-root-relative). `child_path`
values in `design_docs` are ABSOLUTE and already fully resolved (not relative to subdir) -
consumers use them directly without additional joining. This is the
canonical form; single-mode uses `inputs: {design_doc: <SHARE_DIR>/designs/<slug>-<date>.md}` (no
`design_index`). Top-level `design_doc:` (singular) is NOT emitted in master-child mode - it is
valid only in single mode. Downstream consumers resolve per-module paths from `design_docs` +
`design_index`.

**Non-drift rule**: child TDD = the coder's primary spec. Master TDD = hard constraints on data
model, dep direction, shared-symbol ownership, and cross-module sequencing. A child design or
implementation that violates a master-TDD constraint is a CRITICAL finding at review. A child
cannot overturn a master §10 constraint - a disagreement with a master decision is recorded for the
lead, never resolved by the child.

## Conflict list

The master-phase consistency pass CONSUMES the child TDDs plus `contested-symbols.md` and the lead's
decisions on it (§ Contested-symbol reconciliation) and is the SOLE §10/
`index.yaml` applier - children never write §10 themselves. It emits `conflict-list.md` at the
artifact root - the same subdir as `index.yaml` (i.e.
`<SHARE_DIR>/designs/<master-slug>/conflict-list.md`). `conflict-list.md` splits into
LEAD-RESOLVED seams (the lead decided; informational, no decision needed) and ESCALATED seams (the
one reconciliation round did not settle it, or a §10 HARD-rule conflict; need a human decision).
This file is a MANDATORY
INPUT to the batch coding gate: the gate reads it and resolves every listed ESCALATED conflict
before dispatching child coders. The consistency agent and the batch-gate skill both reference
this fixed path - do not move or rename it.

## Semantic-shift note (safe degradation)

In master-child mode there is no single flat "full-solution" TDD. A consumer that reads
`inputs.design_doc` without the master-child wire receives a child-scoped doc only - this is a
MISS for the overall solution, but NOT a regression: the child doc is valid for its own module,
behavior is not incorrect, and no wrong document is substituted. The degradation is silent and
safe by construction (missing key, not wrong value).

A `return_to` caller skips the scope question and bypasses the
decompose branch by construction - master-child output cannot reach `odoo-forward-port` or
`odoo-modules-upgrade` P2b via that route. Skills that consume master-child output must read
`design_index:` from the Continuation Contract, not `design_doc:` (singular).

**Documented seam (deliberately deferred, not silently dropped).** `return_to` callers enter
SINGLE mode (one flat TDD, no children), so base-first child ordering and the opt-in
`review-master` / `review-children` gate keywords above are N/A by construction - there is no
child batch to order or review. A shared design-review hook on the `return_to` path (letting
`odoo-forward-port` / `odoo-modules-upgrade` opt a single-mode design into `MODE: review`) COULD be
offered later; it is explicitly OUT OF SCOPE today because those callers already enforce their own
dependency order downstream through their own integration loops
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`). Flagged here so a future editor does
not need to re-derive this decision.

## Worklog per child

Each child architect writes its own worklog under `<run-or-slug>/<module>/NNN-architect.md`
(subpath per module) so N parallel children never collide. Full path convention:
`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`.
