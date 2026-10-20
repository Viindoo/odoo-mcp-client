<!-- SSOT snippet. Contract for master-child design decomposition in odoo-solution-architect /
     odoo-solution-design. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md; edit here only. -->

# Master-Child Design Contract

## When to use

**Master-child mode**: scope spans multiple modules or multiple independent business domains each
requiring substantial new or modified modules - one master TDD + one child TDD per module.
**Single mode**: single module, or a straightforward change where one flat TDD captures the full
design.

## Artifact layout

Artifacts live under `<SHARE_DIR>` (resolve once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path
into every Read/Write/Edit):

```
<SHARE_DIR>/designs/
  <slug>-<date>.md                 # SINGLE mode
  <master-slug>/                   # MASTER-CHILD mode
    index.yaml                     # machine-readable manifest (routing SSOT)
    _master-<date>.md              # master TDD (constraints + cross-module contracts)
    <module>-<date>.md             # child TDD per module; header line 1: `Master TDD: _master-<date>.md`
```

## index.yaml schema

`index.yaml` is the authoritative file-location registry. Resolve child paths from it, never by
guessing filenames. `master` and `child_path` are RELATIVE to the directory containing `index.yaml`.

```yaml
slug: fleet-billing
created: 2026-06-28
master: _master-2026-06-28.md
modules:
  - name: fleet_billing
    child_path: fleet_billing-2026-06-28.md
    depends_on: []
    dag_layer: 0            # 0 = no intra-design dep; higher = depends on lower-layer modules
    status: pending         # pending | designed | approved | skipped
  - name: fleet_billing_account
    child_path: fleet_billing_account-2026-06-28.md
    depends_on: [fleet_billing]
    dag_layer: 1
    status: pending
dag_layers:
  - [fleet_billing]
  - [fleet_billing_account]
```

Keep `dag_layers` and each entry's `depends_on` + `dag_layer` in sync. `dag_layers` is the design's
LOGICAL layering; `odoo-planning` turns it into the executable node DAG. When a plan exists, the
coding phase follows the plan's `depends_on` order; `odoo-coding` reads `dag_layers` itself only
when running STANDALONE (top-to-bottom).

**Child-design dispatch is base-first.** `odoo-solution-design` dispatches child architects with
`dag_layer` as the ordering axis: same layer = parallel (Mode B budget), different layer = strict
order - ALL layer-`k` children reach `status: designed` before ANY layer-`k+1` child is dispatched. A
layer-`k+1` child brief carries `UPSTREAM_CHILD_DESIGNS: [...]` (the lower-layer child TDDs it
`depends_on`) alongside `MASTER_DESIGN_DOC`.

## Index selection and path resolution

Consumers search all `<SHARE_DIR>/designs/*/index.yaml`. A single match is used directly. When
several match the current scope, apply in sequence until unique:
1. Largest intersection between the index's `modules` list and the set of changed modules.
2. Most recent `created:` date.
3. Slug first alphabetically.
4. When more than one index.yaml still matches, ALWAYS emit `design_doc_ambiguity: true` plus the
   list of all candidate index paths before proceeding.

Resolve `master` and `child_path` to absolute paths (index directory + relative value) BEFORE reading
the files or inserting paths into `DESIGN_DOC` / `MASTER_DESIGN_DOC`.

## §10 Cross-module contracts - shared-symbol ownership registry (in master TDD)

The master TDD contains a **§10 Cross-module contracts** section listing every shared symbol (field,
model, method) referenced by more than one module. Children cite this table and honor it; they do
not re-own or redefine listed symbols.

```
| Shared symbol (field/model/method) | Type | Owning module | Consumers | Notes |
```

1. **Single owner**: each symbol has exactly one owning module; consumers only extend or read it. An
   ambiguous owner is resolved in §10 before any child is written.
2. **Dependency direction**: a consumer module must declare `depends` on (or transitively reach) the
   owning module. A symbol reference without a valid dep is a design defect.
3. **Integration-module rule**: a symbol two sibling modules at the same `dag_layer` need to share
   belongs in a dedicated integration module or a lower-layer shared dep, never in either sibling;
   state the decision in the Notes column.

A single-owner or dependency-direction dispute a child cannot honor as written is contested: record
it per § Contested-symbol reconciliation, never silently pick a winner. Cross-cluster sequencing must
match `dag_layers` in `index.yaml`.

## Contested-symbol reconciliation (same-layer siblings)

Same-layer child architects run concurrently and cannot message each other
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3).

- **Child.** When your design needs a shared symbol another module in this layer owns or touches and
  you cannot honor the master §10 contract as written, do NOT block and do NOT guess: record the
  symbol, your proposed contract, and why, in your own TDD AND append one row to
  `<SHARE_DIR>/designs/<master-slug>/contested-symbols.md`. Then finish your TDD on your own proposal
  and report DONE, naming the contested symbol. Frame the row as shared design context, never
  "secret"/"private".
- **Lead.** After every child in the layer has returned, read `contested-symbols.md` and DISPATCH the
  decision, never make it: `odoo-solution-architect` `MODE: reconcile` decides each contested symbol
  against the master §10 contract and returns one verdict per symbol (winner, loser, evidence). Write
  those verdicts into the master TDD verbatim and re-dispatch ONLY the children whose proposal lost,
  with the verdict in their brief; never pick a winner yourself. ONE reconciliation round per layer; a
  symbol returned `UNRESOLVED`, or a round that does not settle every symbol, BLOCKS the layer for a
  human.

Lower-layer children and the master have terminated by fan-out time: a child honors the finished
artifact (`MASTER_DESIGN_DOC`, `UPSTREAM_CHILD_DESIGNS`) and records any disagreement for the lead the
same way.

**Single-writer discipline.** A child NEVER edits `index.yaml` or §10. The orchestrating skill and
the `MODE: consistency` pass are the ONLY writers: the MANDATORY consistency pass APPLIES the recorded
proposals and the `MODE: reconcile` verdicts to §10, verifying single-owner / dep-direction /
no-circular-dep still hold, before emitting `conflict-list.md`.

## Optional independent review (MODE: review)

Both master-child gates (master gate, batch gate) offer an OPT-IN independent review via
`odoo-solution-architect` `MODE: review`, requested with `refine: review`; default `approve`, so
review is never a mandatory stop. It is one adversarial pass by a fresh context that did NOT author
the design; it reads the master and/or child TDD(s) READ-ONLY, names the single weakest assumption
plus a concrete alternative, and writes `_review-<date>.md` under
`<SHARE_DIR>/designs/<master-slug>/` as a FINDINGS list (severity + alternative) - it never rewrites
the TDD or `index.yaml`.

## Handoff fields

`DESIGN_DOC:` = path to the CHILD TDD (the spec the coder builds verbatim); single mode: the flat
doc. `MASTER_DESIGN_DOC:` = path to the master TDD (hard constraints); single mode: `none`.

In master-child mode the **skill** (`odoo-solution-design`), not the architect agent, emits the
Continuation Contract. Default `next:` is `odoo-planning`; with `return_to` set it emits
`next: <return_to>` instead:

```continuation
status: NEEDS_NEXT
next: odoo-planning
inputs:
  design_index: <SHARE_DIR>/designs/<master-slug>/index.yaml
  master_design_doc: <SHARE_DIR>/designs/<master-slug>/_master-<date>.md
  design_docs:
    - module: <module-name>
      child_path: <SHARE_DIR>/designs/<master-slug>/<module-name>-<date>.md
```

All paths are absolute (rooted at the resolved `<SHARE_DIR>`); `design_docs[].child_path` values are
already resolved - use them directly. Single mode uses
`inputs: {design_doc: <SHARE_DIR>/designs/<slug>-<date>.md}` (no `design_index`). Top-level
`design_doc:` (singular) is NOT emitted in master-child mode. Consumers of master-child output read
`design_index:` and `design_docs`, never `design_doc:`.

**Non-drift rule**: the child TDD is the coder's primary spec; the master TDD holds hard constraints
on data model, dep direction, shared-symbol ownership and cross-module sequencing. A child design or
implementation that violates a master-TDD constraint is a CRITICAL finding at review. A child never
overturns a master §10 constraint; a disagreement is recorded for the lead.

## Conflict list

The consistency pass CONSUMES the child TDDs plus `contested-symbols.md` and the `MODE: reconcile`
verdicts, is the SOLE §10/`index.yaml` applier, and emits
`<SHARE_DIR>/designs/<master-slug>/conflict-list.md` (fixed path - do not move or rename it). It splits
into LEAD-RESOLVED seams (a reconcile verdict settled it and the lead applied it; each listed at the
gate as symbol + winner + loser + evidence, never a bare count) and ESCALATED seams (the one round did
not settle it, or a §10 HARD-rule conflict; a human decides). The batch gate reads it and resolves
every ESCALATED conflict before dispatching child coders.

## Worklog per child

Each child architect writes its own worklog under `<run-or-slug>/<module>/NNN-architect.md` so
parallel children never collide (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).
