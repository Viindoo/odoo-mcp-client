---
name: odoo-solution-design
argument-hint: "[feature/requirement to design]"
description: >
  Design the technical solution for a non-trivial Odoo change BEFORE code is written - the
  analysis-and-design step between requirement analysis (odoo-brl / odoo-gap-analysis) and code
  generation (odoo-coding). Dispatches the odoo-solution-architect
  agent to produce a gate-able Technical Design Document (approach, data model, override strategy,
  module structure, risks) grounded in OSM. Use it to decide HOW to build (inheritance axis,
  stored vs computed, new module vs extend) - not just WHAT to build or to immediately WRITE code.
  Fire on: "how should I architect/structure this", "design the solution / data model", "which
  approach", "plan the refactor", "technical design".
  Vietnamese: "thiết kế giải pháp", "phân tích thiết kế", "chọn cách tiếp cận nào", "lên kế hoạch
  refactor". For ONE method's hook use odoo-override-finding; to WRITE code use odoo-coding;
  to REVIEW use odoo-code-review; to classify a requirement LIST use
  odoo-brl / odoo-gap-analysis
---

## Where this sits in the flow (design precedes the code Plan Mode)

Planning/analysis step only. Output: `.odoo-ai/designs/…` (gitignored, L1) - never production
source. Correct order:

```
design (architect writes the TDD)  →  HUMAN approves the design  →  Plan Mode for the code  →  code → review
```

The approved TDD is the plan the code Plan Mode executes. Do not flip this order. (The design
step is the planning-artifact exception to "writes-files runs only after Plan Mode".)

## Input port - gap-analysis artifact (read before designing)

Before the Phase 0 preview, look for a gap-analysis artifact on disk - the per-requirement
classification/effort is the design PRECONDITION, read it; do NOT re-derive the tier from
conversational text:

- **Glob** `.odoo-ai/gap-analysis/*/gap-matrix.jsonl` (newest dir wins); the consultant path
  may instead carry BRL output under `.odoo-ai/brl/*/` - accept either source.
- **Found:** READ it. Each `gap-matrix.jsonl` line is one requirement with keys `req_id` ·
  `requirement` · `coverage` (full|partial|none) · `classification`
  (standard|config|extension|custom) · `effort_tier` (S|M|L|XL) · `module` · `grounded` ·
  `notes`. Use `classification` + `effort_tier` per requirement to decide WHICH requirements
  need a TDD and at what depth (extension/custom + L/XL drive the design; standard/config with
  a single obvious approach route straight to `odoo-coding`). Cite the artifact path in the
  Phase 0 preview and pass it to the architect (`GAP_MATRIX:` line in the P1 template). When
  the artifact exists it is authoritative - do NOT re-derive tiers from memory.
- **Not found AND the change is non-trivial:** recommend running `odoo-gap-analysis` first to
  classify/cost the requirements rather than guessing the tier. (Trivial single-approach
  change: proceed without it.)

## Phase 0 - Design intent gate (1-turn gate)

**Exception: when `return_to` is set**, SKIP this Phase 0 scope-preview gate entirely. The
caller (e.g. `odoo-forward-port`) has already classified scope and approved entering the design
step. Go straight to the architect dispatch (Agent invocation - prompt template below) and
then the single design-approval gate after the architect returns.

**Default (no `return_to`):** Before invoking the agent, emit a concise **design scope
preview**, then **stop** for confirmation. The preview names what the design will decide and
which artifact it produces - it does NOT write production code (this is a read-only design step):

```
Design scope: <one-line of the change to be designed>
Will decide:  approach (inherit axis / new vs extend) · data model · override strategy ·
              module structure · sequencing · test outline · risks · platform-principles
              (multi-company/branch, localization strategy, app-menu) · bidirectional
              (upstream+downstream) impact · dynamic demo-data plan
Artifact:     .odoo-ai/designs/<slug>-<YYYY-MM-DD>.md (design doc, no production code)
OSM:          backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

Wait for the user's reply before proceeding. This gate is the single mandatory checkpoint for
the default (no `return_to`) path and applies even on a direct (intake-bypass) entry. It is a
**preview, not a write-block** - on confirmation the architect writes ONLY the design doc under
`.odoo-ai/`, never source files.

**Multi-module scope heuristic.** Before emitting the preview, check for these qualitative
signals - a cluster of them suggests master-child decomposition is worth offering:
- Multiple independent modules each needing a new model or new inheritance axis.
- Independent business domains where sub-designs are mostly orthogonal.
- Several Custom-XL / Extension-L items (from `odoo-brl` / `odoo-gap-analysis`) referencing
  different module entry points and sharing a non-trivial cross-module contract.

Module enumeration priority (first available): deep-survey `synthesis.md` → brl `dag.json`
→ modules-upgrade `graph.md` → fallback: scan `__manifest__.py` + topo-sort `depends`
(pattern: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/SKILL.md` § P1(a)).

When the heuristic fires, replace `Proceed? (yes / refine: [feedback] / cancel)` with:

```
Proceed?
  approve-master-child  - one master TDD + one child TDD per module (see Decompose branch)
  approve-single / yes  - flat TDD covering full scope (default; use when in doubt)
  refine: [feedback]    - clarify scope first
  cancel
```

Default is `approve-single` / plain `yes`. Show `approve-master-child` only when the heuristic
fires - never for a single-module or narrowly-scoped design.

**`approve-single` / plain `yes`:** MUST set `MODE: single` in the architect dispatch brief (P1
template). Without this explicit field, the architect's decompose-bounce heuristic may re-evaluate
scope as multi-module, return `NEEDS_NEXT`, and loop instead of writing the TDD.

---

## Decompose branch (master-child mode)

Only entered when the user replied `approve-master-child` at Phase 0.
Contract SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md`.
Artifact root: `.odoo-ai/designs/<master-slug>/`.

**a. Master TDD dispatch.** Dispatch `odoo-solution-architect` with `MODE: master`. Architect
produces `_master-<date>.md` (cross-module altitude: §10 shared-symbol registry, dep directions,
integration-module decisions - NOT module internals) and `index.yaml` (per contract schema).
Use same prompt template as P1 below; add `MODE: master`.

**b. Master gate (human, MANDATORY).** Present master TDD summary: §10 symbol count, dep order,
top cross-module risks. Gate: `approve-master / refine: [feedback] / cancel`. No child dispatch
before this clears. The approved master §10 is the hard constraint for all children.

**c. DAG fan-out (child TDDs).** After master gate:
- Read `dag_layers` from `index.yaml` (topo order is encoded in list order).
- Dispatch `odoo-solution-architect` `MODE: child` per module, following **Mode B**
  (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`). Same-`dag_layer` modules
  run in parallel. Dep-wait only when a child consumes an interface PROPOSED (not yet in master
  §10) by a sibling; if already in §10, no wait needed.
- **Model floor: opus.** Scale toward fable for modules with a new inheritance axis (same
  fable-confirmation rule as single mode).
- Child brief includes `MODE: child`, `CHILD_MODULE: <name>`, `MASTER_DESIGN_DOC: <abs path>`,
  `ODOO_VERSION: <version>`. Child cites master §10 for every cross-module symbol it references.
- After each child subagent returns, YOU (the orchestrating main agent) write `status: designed`
  for that module to `index.yaml` (checkpoint for resume on interruption).

**d. Consistency pass (MANDATORY after all children `designed`).** Dispatch
`odoo-solution-architect` `MODE: consistency`. Reads CONTRACT SUBSET of each child (§1 Intent,
§9 Acceptance Criteria, cross-module fields/models/deps - NOT full body) + master §10. Reconciles seams,
updates §10 where needed, emits `conflict-list.md` at the artifact root.

**e. Batch gate (human, single gate for all children).** Present conflict-list (MANDATORY - state
explicitly if empty; do not skip) + per-child TDD summaries (approach, top risk, data-model delta).
Gate: `approve-all / refine:<module>: [feedback] / cancel`. A `refine:<module>` re-dispatches that
child only, re-runs consistency pass, then re-presents this gate. One batch gate total.
On `approve-all`, write `status: approved` for all modules in `index.yaml`.

**f. Continuation Contract (master-child).** Emit per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. All paths are repo-root-relative;
`child_path` under `design_docs` MUST be the full repo-root path (not relative to subdir):

```yaml
status: NEEDS_NEXT
next: <return_to or odoo-planning>
inputs:
  design_index: .odoo-ai/designs/<master-slug>/index.yaml
  master_design_doc: .odoo-ai/designs/<master-slug>/_master-<date>.md
  design_docs:
    - module: <name>
      child_path: .odoo-ai/designs/<master-slug>/<name>-<date>.md
```

Do NOT emit bare `design_doc:` (single-mode only). Do NOT put `design_index` /
`master_design_doc` / `design_docs` as bare top-level keys - they belong under `inputs:`.
`next:` same rule as single mode: `return_to` SET → `next: <return_to>`; UNSET →
`next: odoo-planning` (the planner consumes `index.yaml` `dag_layers` and batches the modules into
a wave-batched execution plan before any code is written - it is the first consumer of the design
DAG; the coders later follow the plan's module/wave order rather than `dag_layers` directly).

---

## Persona

Odoo solution architect. Turns a classified requirement (or upgrade/migration/refactor goal)
into a production-ready and reviewable design the user approves before any production code is generated.
Pairs with `odoo-coding` (consumes the design) and `odoo-code-review` (checks implementation vs design).

## When to invoke - and the non-trivial threshold

Launch `odoo-solution-architect` as a subagent for **non-trivial** changes. Fire for ANY of:

- **Extension-L / Custom-XL** tier (from `odoo-brl` / `odoo-gap-analysis`).
- **A new module**, new model, or module restructure.
- **Overriding a core ORM hook** (`create` / `write` / `unlink`) or a method with ≥3 entries
  in its override chain.
- **A schema / data migration** with more than one viable strategy.
- **A cross-model computed chain**, multi-company / multi-currency / multi-branch (v17+), or a
  full-stack feature spanning backend + frontend.
- **A localization touch** needing a generic-before-localization decision, or a new
  `application=True` module needing the standard app-menu shape (root + Reports + Configuration).
- **A refactor** (mixin extraction, module split/merge, inheritance axis change).

The architect surveys **bidirectional impact** and designs **dynamic demo data** for any new
end-user behavior - see `agents/odoo-solution-architect.md` for the template.

**Skip for trivial work:** a single Standard/Config field, boilerplate (one computed field, a
view shell, a security CSV row), or a localized fix with exactly one obvious approach → route
straight to `odoo-coding`. If unsure: "this looks like a one-approach change - design it first,
or code it directly?"

## Out of Scope

- **Writing production code** → `odoo-coding` (backend Python/XML + frontend JS/OWL/SCSS)
- **Reviewing existing code** → `odoo-code-review`
- **Finding ONE method's hook location** → `odoo-override-finding` (this skill designs the whole
  solution; override-finding answers a single "where do I hook" question)
- **Classifying / costing a requirement list** → `odoo-brl` (large) or `odoo-gap-analysis` (short)
- **Version-to-version API delta** → `odoo-version-diff`; **deprecation scan** → `odoo-deprecation-audit`
- **User workflow narrative or happy-path usage scenarios for documentation** -> `odoo-doc-walkthrough`. This skill designs technical architecture BEFORE code; it does NOT author user-facing walkthrough text or scenario docs

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `resolve_orm_chain` ⊕ - Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `validate_domain` ⊕ - Validate search domain terms: field-path resolution and operator version-awareness.
- `validate_relation` ⊕ - Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

## Brief context

The design doc is a **contract for the coders**. Eight fixed sections (Intent & Business Value,
Approach, Data model, Override strategy, Module structure, Sequencing, Test strategy outline, Risks)
are specified in `agents/odoo-solution-architect.md` (Round 4 is the SSOT for the doc template).

For full-stack design, ground the frontend approach in the **fidelity** contract
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`. Full reference (doc structure,
frontend-design sources, key failure modes prevented):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/references/brief-context.md`

### Test strategy grounding (§7) - when to use which test tool

Section §7 "Test strategy outline" is the highest-leverage output of the TDD: every downstream
agent (odoo-test-writing, odoo-qa-planner, odoo-coder) inherits the base classes and behavior list
it specifies (odoo-qa-planner turns it into the independent acceptance oracle under odoo-acceptance;
odoo-qa-suite reuses it only as a static release test-plan, never to execute or adjudicate). The architect uses four test tools - already visible in `## MCP tools` below - at
specific moments in the design rounds:

| Tool | When in the rounds | Why |
|---|---|---|
| `test_base_classes(odoo_version='<version>')` | Round 0 HARD RULE, before writing any test class name | Returns authoritative `TransactionCase` / `HttpCase` / `SavepointCase` / `Form` menu for the pinned version + always outputs **`cr.commit()` FORBIDDEN** contract. Never assert a base class from memory. |
| `find_test_examples(query='<feature>', odoo_version='<version>')` | Round 1, call #5, parallel with `find_examples` | Returns ONLY test chunks (no production code). Seeds the workflow-path shapes that populate §7 rows. Use instead of `find_examples` whenever the intent is to find test patterns. |
| `tests_covering(model='<model>', odoo_version='<version>')` | Round 2, immediately after `impact_analysis` | Lists test methods that already COVER the target model/field/method. Zero model-level edges = unguarded behavior that §7 must add. Non-zero = existing protection (no need to duplicate). Edge count goes in the Impact matrix and §7 "Already covered?" column. **Caveat:** method-narrow (`method=`) and field-narrow (`field=`) calls frequently return zero edges even for well-tested code because COVERS_METHOD / COVERS_FIELD edges are sparse; prefer the model-level call as the primary signal and treat method-narrow zero as supporting evidence only. |
| `test_coverage_audit(module='<module>', odoo_version='<version>')` | Round 4, first step before filling §7 rows | Audits the whole module for zero-coverage fields (field-level static-reference; method gaps are NOT reported - use `tests_covering` with `method=` to probe a specific method, but expect sparse results). Each field gap surfaced here that the design introduces or modifies MUST appear as a new test row in §7. |

**Invariant:** §7 is only valid if all four tools were called during the design rounds. A §7
written from memory (no `test_base_classes` call) is a design defect - the wrong base class in the
TDD flows verbatim into test code.

## Agent invocation - prompt template (P1)

When the user confirms intent (Phase 0 gate passed), launch `odoo-solution-architect` as a subagent.
Use the template below **verbatim**, filling the bracketed placeholders.

**Model per dispatch** - set as the subagent `model` parameter (the `DISPATCH MODEL` line
records the tier chosen; both must match):
- **opus** - default for every design.
- **fable** - ONLY for Custom-XL tier or a design spanning >=3 modules full-stack with a new
  inheritance axis. Requires explicit human confirmation (state tier, cost, and why). If
  declined or unavailable, fall back to **opus** and note in the TDD header
  (`dispatch: opus (fable declined/unavailable)`).

```
DISPATCH MODEL: <opus|fable>
You are the odoo-solution-architect agent. Produce an Odoo Technical Design Document (NOT
production code) for the following change:

REQUEST: [full requirement/goal, with target model(s), Odoo version, any constraints. For the
classification/effort tier, prefer the GAP_MATRIX file below over a pasted tier string - the
architect reads it per requirement]

GAP_MATRIX: [omit this line entirely when absent; otherwise the gap artifact path found by the
Input port - .odoo-ai/gap-analysis/<slug>-<date>/gap-matrix.jsonl, or the BRL results dir
.odoo-ai/brl/<job-id>/. The architect READS this for the authoritative per-requirement
classification/effort_tier - do NOT also flatten the tier into REQUEST as free text]

RETURN_TO: [omit this line entirely when absent; set to the caller skill name (e.g.
odoo-forward-port) when the caller requests return routing after design approval]

DESIGN_SLUG_HINT: [omit when absent; short slug the caller wants used for the design doc
filename, e.g. account-move-fp-18 - the architect uses this as the <slug> when writing
.odoo-ai/designs/<slug>-<date>.md]

Step 0 (ONLY if mcp__odoo-semantic__* tools are available): call
set_active_version('<version>'), then proceed through your design rounds. If OSM is
unavailable, use the Standalone-first fallback (disk-grounded: Read/Grep the repo). If OSM
is reachable but a SPECIFIC module/model in this request is not in the index (a
customer-local custom module), that is a Tier-1 MISS, not proof of absence: keep OSM for
everything it covers and Read/Grep the local addons for just the missed entities, grounding
the design hybrid (grounded: osm + local-source (hybrid)). Do NOT
design from memory when OSM is reachable.

Follow your system-prompt rounds. Write the design doc to .odoo-ai/designs/<slug>-<date>.md.
Do NOT write any production source files. Do NOT spawn subagents or invoke skills.
```

The agent runs its rounds using its restricted read-only tool allowlist. It does NOT spawn
subagents, invoke skills, or write production code.

### Payload mapping when `return_to` is set (caller-return flow)

When this skill is invoked by a caller that supplied `return_to` in its inputs (e.g.
`odoo-forward-port` routing a bucket-(c) module here), map the caller's payload onto the
dispatch template as follows - do NOT improvise or drop any field:

| Caller input | Architect template field | How to compose |
|---|---|---|
| `target_version` | `REQUEST` preamble + `set_active_version` | Write "Target Odoo version: <target_version>" as the first line of `REQUEST` |
| `modules` | `REQUEST` preamble | Write "Modules: <names>" as the second line of `REQUEST` |
| `classification` | `REQUEST` body | Paste the bucket-(c) summary verbatim as the core requirement description in `REQUEST` |
| `intent_records` | `REQUEST` body | Write "Intent records (read these FIRST for the OSM-grounded behavioral contract): <paths>" as a dedicated line in `REQUEST`; the architect MUST Read each path before designing - this is the behavioral contract the forward-port must preserve |
| `design_slug_hint` | `DESIGN_SLUG_HINT` line | Copy verbatim; the architect uses it as `<slug>` when naming `.odoo-ai/designs/<slug>-<date>.md` |
| `return_to` | `RETURN_TO` line | Copy verbatim; routes the architect's Continuation Contract back to the caller |

The assembled `REQUEST` therefore reads:
```
REQUEST: Target Odoo version: <target_version>
Modules: <module names>
Intent records (read these FIRST for the OSM-grounded behavioral contract): <intent_records paths>
<classification - bucket-(c) summary>
```

Never flatten `intent_records` into the classification summary or omit it - it carries the
behavioral contract the design must honour, distinct from the structural classification.

## Standalone-first fallback

When OSM is unreachable: architect `Read`/`Grep`s module source (field lists, method signatures,
manifest `depends`), labels doc `grounded: local-source (not OSM-indexed)`. When OSM is
reachable but a specific module is not in the index (customer-local addon): OSM for what it
covers, local source for missed entities, doc labeled `grounded: osm + local-source (hybrid)`.
Only when the repo itself is inaccessible: fall back to memory, label `OSM unavailable -
ungrounded`. Three-tier grounding SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`.
Escalate (`NEEDS_CONTEXT`) only for business decisions no source encodes - never to ask a human
to paste code or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-solution-architect.md` for the
full restricted (read-only) tool list and execution detail.

## Design-approval gate (who approves: the human)

When the architect returns the TDD, **do NOT auto-chain to coding.** Present a tight summary
(chosen approach + rationale, data-model/override headlines, top risk, pointer to the full doc),
then gate. Write the gate message in the USER'S LANGUAGE (translate labels and prose; keep file
paths, module names, and model identifiers verbatim):

```
Design ready: .odoo-ai/designs/<slug>-<YYYY-MM-DD>.md
Intent: <one line - what this solves and why>   ·   Business value: <one line>
Approach: <one line>   ·   Top risk: <one line>
Modules:
  | module | new/modified | intent | expected outcome | business value |
  | <m1>   | new          | <...>  | <observable>     | <...> |
  | <m2>   | modified     | <...>  | <observable>     | <...> |
Approve design? (approve / refine: [feedback] / cancel)
```

- `refine: [feedback]` → re-dispatch the architect with the feedback; rewrite the same doc.
- `approve` → ONLY NOW does the chain move on. Two branches:
  - **`return_to` is UNSET (default standalone flow):** hand off to `odoo-planning` to turn the
    approved design into the execution plan (module order + integration cadence + lifecycle
    wiring); `odoo-planning` owns the code Plan Mode and the plan wires `odoo-coding` / `odoo-wave`
    (the git-executor, dispatched by run-harness) per its plan. (A migration design routes straight to `odoo-data-migration` / `odoo-coding`.)
  - **`return_to` is SET (caller-return flow):** do NOT enter a code Plan Mode and do NOT
    dispatch any coder. Emit the Continuation Contract (see below) with `next: <return_to>`
    and hand control back to the caller. The caller (e.g. `odoo-forward-port`) owns the
    downstream Plan Mode and code dispatch.
- `cancel` → stop; the design doc remains on disk for later.

Optional assist (does not replace human approval): for a high-risk design you MAY ask
`odoo-code-review` for a read-only second opinion on the doc before presenting it - but the
human still makes the call.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). The `next`
is **gated on the human design-approval above** - the driver dispatches the next step only after
the design is approved. Choose `next` as follows:

- **`return_to` is SET:** emit `next: <return_to>` (e.g. `next: odoo-forward-port`). Include
  in `inputs`: `design_doc: <path>` only. Do NOT emit a coder target. The caller recovers
  everything else (module names, branches, versions) from its own checkpoint; only the design
  doc path needs to cross the boundary. The caller resumes with the approved design doc and
  runs its own Plan Mode.
- **`return_to` is UNSET (default):** for a backend, frontend, or full-stack design emit
  `next: odoo-planning` (the planner turns the approved design into the wave-batched execution
  plan before any code is written); for a migration design emit `next: odoo-data-migration` (or
  `odoo-coding` for the migration script). Each carries `design_doc: <path>` so the next step
  builds on the approved design.

- **Master-child mode (`approve-master-child` path):** see Decompose branch § f above. Emit
  `design_index` / `master_design_doc` / `design_docs` - NOT bare `design_doc:` (single-mode only).

Additive output for the run-harness - it does not change anything produced above.
