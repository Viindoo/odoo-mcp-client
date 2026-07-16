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

```
.odoo-ai/designs/
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

**Locating the index**: consumers search all `.odoo-ai/designs/*/index.yaml` files under the repo
root. A single match is used directly. When multiple index files match the current scope:

**Tie-break order** (apply in sequence until unique):
1. Intersection size - choose the index whose `modules` list has the largest intersection with the
   set of changed modules. Larger intersection wins.
2. Recency - if tied on intersection size, choose the index with the most recent `created:` date.
3. Alphabet - if still tied, choose the index whose slug comes first alphabetically.
4. Ambiguity flag - when more than one index.yaml matches after tie-break, ALWAYS emit
   `design_doc_ambiguity: true` plus a list of all candidate index paths before proceeding.

**Path resolution**: `master` and `child_path` values in `index.yaml` are RELATIVE to the
directory containing that `index.yaml` (i.e. `.odoo-ai/designs/<master-slug>/`). Consumers MUST
resolve them to absolute paths (join the index directory + the relative value) BEFORE reading the
files or inserting paths into `DESIGN_DOC` / `MASTER_DESIGN_DOC` fields.

Example: `index.yaml` at `.odoo-ai/designs/fleet-billing/index.yaml` with
`child_path: viin_fleet_billing-2026-06-28.md` resolves to
`.odoo-ai/designs/fleet-billing/viin_fleet_billing-2026-06-28.md` (repo-root-relative).

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

A single-owner or dependency-direction dispute peers cannot resolve within the bounded loop is a
deadlock - escalate per § Peer reconciliation, never silently pick a winner.

Cross-cluster sequencing (which `dag_layer` builds first) must match `dag_layers` in `index.yaml`.

## Peer reconciliation (bounded, same-layer siblings)

Applies to child architects in the SAME `dag_layer` running concurrently (Mode B). It is the
sanctioned lateral use of report-up-one-level
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3): peers may message peers
DIRECTLY, but escalation still only ever goes UP exactly one level (to the lead - your `REPLY_TO`;
`main` only when main is the actual lead, never a hardcoded literal), never past it.

**Addressing.** The lead is the address authority. When it fans out a same-layer batch it injects into
each child brief a `PEERS:` field listing the SendMessage-addressable names of the OTHER children in
that same batch (`none` when the layer has one child). A child uses only the names the lead supplied,
never a guessed address. Lower-layer children have already terminated by fan-out time, so a
higher-layer child does NOT debate a lower-layer decision live - it reads the lower-layer child's
finished TDD (its `UPSTREAM_CHILD_DESIGNS` artifact) and escalates a disagreement to the lead. The
master has also terminated; a child never debates a live master - it honors the master §10 artifact
and escalates a §10 disagreement to the lead.

**Bounded loop.** When child A's design needs a shared symbol a same-layer peer B owns or touches and
they disagree on the contract, A opens a direct exchange:
`SendMessage({to: <B in PEERS>, text: <the specific §10 symbol + A's proposed contract + why>})`.
B replies AGREE or COUNTER (its contract + why). Cap at TWO round-trips per peer pair (A->B->A->B).
Frame every message as shared design context, never "secret"/"private" (CHP confidentiality guard).

**Termination (agreement) - single-writer discipline.** The loop terminates the moment both sides
state agreement in writing. NEITHER peer edits `index.yaml`/§10 directly: the orchestrating skill and
the `MODE: consistency` pass are the ONLY §10/`index.yaml` writers (a child never re-declares a §10
symbol - see § single-owner). Instead EACH peer records the agreed contract in its OWN child TDD (the
symbol owner marks itself owner; the consumer marks itself consumer-only) and in its worklog. The
MANDATORY consistency pass then CONSUMES these recorded agreements and APPLIES them to §10, verifying
single-owner / dep-direction / no-circular-dep still hold before emitting `conflict-list.md`.

**Escalation (deadlock).** Escalate to the lead (your `REPLY_TO` - `main` only when main is the
actual lead, never a hardcoded literal; see `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`
R3) - one SendMessage with a structured
disagreement summary (the symbol, each side's contract, why neither yields) - IFF either: (a) the
two-round cap is exhausted with no written agreement, OR (b) no proposal on the table can satisfy a
§10 HARD rule (single-owner, dependency-direction, no-circular-dep). A child NEVER changes a master
§10 constraint by debate; a disagreement with a master decision is an escalation, not a child edit.
Escalation is the ONLY path a seam reaches the human gate; a peer-reconciled seam does not.

## Optional independent review (MODE: review)

Both master-child gates (master gate, batch gate) offer an OPT-IN independent review via
`odoo-solution-architect MODE: review` - gate keywords `review-master` / `review-children`,
default `approve`, so review is NEVER a mandatory stop (preserves drive-to-done). Review is a
single adversarial pass by a fresh context that did NOT author the design under review
(context-independence is the anti-bias axis, not agent-type independence); it reads the master
and/or child TDD(s) READ-ONLY, names the single weakest assumption plus a concrete alternative,
and writes `_review-<date>.md` under `.odoo-ai/designs/<master-slug>/` as a FINDINGS list
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
  design_index: .odoo-ai/designs/<master-slug>/index.yaml
  master_design_doc: .odoo-ai/designs/<master-slug>/_master-<date>.md
  design_docs:
    - module: <module-name>
      child_path: .odoo-ai/designs/<master-slug>/<module-name>-<date>.md
```

All paths are repo-root-relative. `child_path` values in `design_docs` are ABSOLUTE (repo-root
path, not relative to subdir) - consumers use them directly without additional joining. This is the
canonical form; single-mode uses `inputs: {design_doc: .odoo-ai/designs/<slug>-<date>.md}` (no
`design_index`). Top-level `design_doc:` (singular) is NOT emitted in master-child mode - it is
valid only in single mode. Downstream consumers resolve per-module paths from `design_docs` +
`design_index`.

**Non-drift rule**: child TDD = the coder's primary spec. Master TDD = hard constraints on data
model, dep direction, shared-symbol ownership, and cross-module sequencing. A child design or
implementation that violates a master-TDD constraint is a CRITICAL finding at review. A child
cannot overturn a master §10 constraint via peer debate - a disagreement with a master decision
escalates to the lead.

## Conflict list

The master-phase consistency pass CONSUMES the peer-reconciled child TDDs (each peer having
recorded its agreed contract in its own TDD per § Peer reconciliation) and is the SOLE §10/
`index.yaml` applier - children never write §10 themselves. It emits `conflict-list.md` at the
artifact root - the same subdir as `index.yaml` (i.e.
`.odoo-ai/designs/<master-slug>/conflict-list.md`). `conflict-list.md` splits into RESOLVED-BY-PEERS
seams (peers already agreed; informational, no decision needed) and ESCALATED seams (peers hit the
bounded-loop cap or a §10 HARD-rule conflict; need a human decision). This file is a MANDATORY
INPUT to the batch coding gate: the gate reads it and resolves every listed ESCALATED conflict
before dispatching child coders. The consistency agent and the batch-gate skill both reference
this fixed path - do not move or rename it.

## Semantic-shift note (safe degradation)

In master-child mode there is no single flat "full-solution" TDD. A consumer that reads
`inputs.design_doc` without the master-child wire receives a child-scoped doc only - this is a
MISS for the overall solution, but NOT a regression: the child doc is valid for its own module,
behavior is not incorrect, and no wrong document is substituted. The degradation is silent and
safe by construction (missing key, not wrong value).

A caller that uses `return_to` to skip Phase 0 of the solution-design skill bypasses the
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
