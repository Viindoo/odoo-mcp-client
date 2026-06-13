---
name: odoo-solution-design
description: >
  Design the technical solution for a non-trivial Odoo change BEFORE code is written — the
  analysis-and-design step between requirement analysis (odoo-brl / odoo-gap-analysis) and code
  generation (odoo-coding). Dispatches the odoo-solution-architect
  agent to produce a gate-able Technical Design Document (approach, data model, override strategy,
  module structure, risks) grounded in OSM. Use it to decide HOW to build (inheritance axis,
  stored vs computed, new module vs extend) — not just WHAT to build or to immediately WRITE code.
  Fire on: "how should I architect/structure this", "design the solution / data model", "which
  approach", "plan the refactor", "technical design".
  Vietnamese: "thiết kế giải pháp", "phân tích thiết kế", "chọn cách tiếp cận nào", "lên kế hoạch
  refactor". For ONE method's hook use odoo-override-finding; to WRITE code use odoo-coding;
  to REVIEW use odoo-code-review; to classify a requirement LIST use
  odoo-brl / odoo-gap-analysis
---

## Where this sits in the flow (design precedes the code Plan Mode)

This is the **planning/analysis** step, not a code step. Its only output is an internal planning
artifact (`.odoo-ai/designs/…`, gitignored, L1) — never production source — so it runs and is
**approved BEFORE** the harness Plan Mode for the code. The correct order is:

```
design (architect writes the TDD)  →  HUMAN approves the design  →  Plan Mode for the code  →  code → review
```

The approved TDD *is* the plan the code Plan Mode then executes. Do not flip this: writing code
before the design is approved is exactly what this step exists to prevent. (The design step is
the planning-artifact exception to "writes-files runs only after Plan Mode" — its file is a
planning doc, the same class intake is allowed to write while planning, not the routed deliverable.)

## Phase 0 — Design intent gate (1-turn gate)

Before invoking the agent, emit a concise **design scope preview**, then **stop** for
confirmation. The preview names what the design will decide and which artifact it produces — it
does NOT write production code (this is a read-only design step):

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

Wait for the user's reply before proceeding. This gate is the single mandatory checkpoint and
applies even on a direct (intake-bypass) entry. It is a **preview, not a write-block** — on
confirmation the architect writes ONLY the design doc under `.odoo-ai/`, never source files.

---

## Persona

Developer — Odoo solution architect. Sits one step before the coders: turns a classified
requirement (or an upgrade/migration/refactor goal) into a reviewable design the user can
approve before a single line of production code is generated. Pairs with `odoo-coding`
(which consumes the design — backend then frontend) and with `odoo-code-review` (which can
check the implementation back against the design).

## When to invoke — and the non-trivial threshold

Invoke the `odoo-solution-architect` agent (via Agent tool) when the change is **non-trivial**
and benefits from a designed-and-approved-before-coding step. Fire it for ANY of:

- **Extension-L / Custom-XL** tier (from `odoo-brl` / `odoo-gap-analysis`) — significant or
  net-new logic.
- **A new module**, or a new model, or restructuring an existing module.
- **Overriding a core ORM hook** (`create` / `write` / `unlink`) or a method whose override
  chain already has ≥3 entries (conflict risk).
- **A schema / data migration** that has more than one viable strategy (pre vs post,
  openupgradelib vs raw SQL, ID-match vs value-match mapping).
- **A cross-model computed chain**, multi-company / multi-currency / multi-branch (v17+) logic,
  or a full-stack feature spanning backend + frontend.
- **A localization touch** that needs a generic-before-localization decision (does this belong in
  a shared module with per-country seed data, or is it truly country-specific?), or a new
  `application=True` module that needs the standard app-menu shape (root + Reports +
  Configuration) - both are architectural choices, not coding details.
- **A refactor** (extract a mixin, split/merge modules, change an inheritance axis) — refactor
  is design-heavy by nature; design it before touching code.

The architect surveys **bidirectional impact** (upstream depends-closure + downstream dependents,
direct and indirect) and designs **dynamic demo data** for any new end-user behavior - see
`agents/odoo-solution-architect.md` for the template; this skill only gates the entry.

**Skip the design step for trivial work** (Keep It Simple — do not impose design ceremony on a
one-liner): a single Standard/Config field, boilerplate (one computed field, a view shell, a
security CSV row), or a localized fix with exactly one obvious approach. For those, route
straight to `odoo-coding`. If unsure, ask one question: "this
looks like a one-approach change — design it first, or code it directly?"

## Out of Scope

- **Writing production code** → `odoo-coding` (backend Python/XML + frontend JS/OWL/SCSS)
- **Reviewing existing code** → `odoo-code-review`
- **Finding ONE method's hook location** → `odoo-override-finding` (this skill designs the whole
  solution; override-finding answers a single "where do I hook" question)
- **Classifying / costing a requirement list** → `odoo-brl` (large) or `odoo-gap-analysis` (short)
- **Version-to-version API delta** → `odoo-version-diff`; **deprecation scan** → `odoo-deprecation-audit`

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
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `resolve_orm_chain` ⊕ — Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `validate_depends` ⊕ — Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `validate_domain` ⊕ — Validate search domain terms: field-path resolution and operator version-awareness.
- `validate_relation` ⊕ — Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Brief context

The design doc is a **contract for the coders**, not prose: the architect grounds every
model/field/method/edition claim via OSM and reuses indexed patterns before proposing any
hand-written structure. Its fixed eight sections — Intent & Business Value (solution-level intent /
purpose / expected outcomes / business value / user impact, plus a per-module table covering
BOTH new modules and existing modules being refactored, modified, or optimized), Approach
(inheritance axis + new-vs-extend, ADR-style with rejected alternatives), Data model, Override
strategy, Module structure, Sequencing, Test strategy outline (behavior-first, feeds
`odoo-test-writer` / `odoo-qa-suite`), and Risks — are specified in
`agents/odoo-solution-architect.md` (Round 4 is the SSOT for the doc template); this skill does
not restate them, so the contract stays in one place. The Intent & Business Value section exists
for the HUMAN approver: a design whose purpose and value cannot be stated per module is not ready
to gate.

Key failure modes the design prevents (each surfaces only at review/runtime if skipped): wrong
inheritance axis, override at the wrong level / wrong `super()` position, stored-vs-computed
mistakes, conflicts with existing overrides, ad-hoc `depends` causing circular module deps.

**Full-stack designs (frontend portion).** When the change spans the frontend (a widget, OWL
component, QWeb override, or SCSS/theme work), the architect pulls in two knowledge sources: the
**design-quality** skill — **invoke skill `odoo-frontend-design` using skill tool** (it is a leaf
knowledge skill; loading injects expertise and spawns nothing) — for what a *good* Odoo UI is
(view-type choice, form hierarchy, density, semantic tokens, website/portal rules); and the
**fidelity** contract `skills/_shared/odoo-frontend-fidelity.md` (a `_shared` doc it Reads) so the
design names real design tokens / style origins for the target version via `resolve_stylesheet` /
`find_style_override` rather than inventing selectors or colors. The frontend half of the design
is then consumed by `odoo-coding` (its frontend leg), which loads the same two sources when it
writes the JS/OWL/SCSS.

## Agent invocation — prompt template (P1)

When the user confirms intent (Phase 0 gate passed), the main agent invokes the
`odoo-solution-architect` agent via the Agent tool. Use the following template **verbatim** as
the agent prompt, filling in the bracketed placeholders:

**Model per dispatch.** The agent frontmatter pins `model: opus` only as a floor.
Pass the Agent-tool `model` parameter explicitly on every dispatch - the
`DISPATCH MODEL` line at the top of the template records the tier you chose;
set that same value as the Agent-tool `model` parameter on THIS dispatch:
- **opus** - default for every design.
- **fable** - ONLY when the requirement is graded Custom-XL (from odoo-brl /
  odoo-gap-analysis) or the design spans >=3 modules full-stack with a new
  inheritance axis. fable costs ~2x opus, so it ALWAYS needs explicit human
  confirmation: add a line to the proposal gate stating the tier, the cost, and
  WHY this design needs it, and wait for the user's yes. If the user declines,
  or the fable dispatch fails (insufficient usage credit, model unavailable,
  Agent-tool error), fall back to **opus** automatically and note the downgrade
  in the TDD header (`dispatch: opus (fable declined/unavailable)`).

```
DISPATCH MODEL: <opus|fable>
You are the odoo-solution-architect agent. Produce an Odoo Technical Design Document (NOT
production code) for the following change:

REQUEST: [full requirement/goal, with target model(s), Odoo version, any constraints, and the
classification/effort tier if it came from odoo-brl/odoo-gap-analysis]

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

The agent runs its rounds (version pin → context gather → approach selection → data-model &
override design → validation → write the doc) using its restricted read-only tool allowlist. It
does NOT spawn further subagents or invoke skills, and it does NOT write production code.

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`: the architect `Read`/`Grep`s the
module source itself (field lists, existing method signatures, manifest `depends`) and designs
against that, labelling the doc `grounded: local-source (not OSM-indexed)`. When OSM is
reachable but a specific module/model is not in the index (a customer-local addon), the
architect applies the Tier-1 MISS rule from the same protocol: OSM for what it covers, local
source for the missed entities, doc labelled `grounded: osm + local-source (hybrid)`. Only when the repo
itself is inaccessible does it fall back to memory, labelled `OSM unavailable — ungrounded`,
with lowered confidence. Escalate to the caller (`NEEDS_CONTEXT`) only for business decisions no
source encodes — never to ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-solution-architect.md` for the
full restricted (read-only) tool list and execution detail.

## Design-approval gate (who approves: the human)

When the architect returns the TDD, **the main agent does NOT auto-chain to coding.** Present the
design for approval and **stop**. The approver is the **human** — a design is a decision that
belongs to the user, not something a downstream agent should rubber-stamp. Surface a tight summary
(chosen approach + one-line rationale, the data-model/override headlines, top risk) with a pointer
to the full doc, then gate:

Write the gate message in the USER'S LANGUAGE (translate the labels and prose; keep
file paths, module names, and model identifiers verbatim):

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
- `approve` → ONLY NOW does the chain move on: enter Plan Mode for the code and dispatch the
  coder (`odoo-coding`) to build to the approved doc.
- `cancel` → stop; the design doc remains on disk for later.

Optional assist (does not replace human approval): for a high-risk design you MAY ask
`odoo-code-review` for a read-only second opinion on the doc before presenting it — but the
human still makes the call.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). The `next`
is **gated on the human design-approval above** — the driver dispatches the coder only after the
design is approved (the design doc is the plan the code Plan Mode then executes). For a backend,
frontend, or full-stack design, emit `next: odoo-coding` (it sequences the backend and frontend
legs itself per the design); for a migration design, emit `next: odoo-data-migration` (or
`odoo-coding` for the migration script) — each carrying the design-doc path as a
`design_doc` input so the coder builds to the approved design. Additive output for the depth-0
run-driver — it does not change anything produced above.
