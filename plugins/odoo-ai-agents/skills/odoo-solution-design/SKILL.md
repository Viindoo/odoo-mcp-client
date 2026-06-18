---
name: odoo-solution-design
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

## Phase 0 - Design intent gate (1-turn gate)

Before invoking the agent, emit a concise **design scope preview**, then **stop** for
confirmation. The preview names what the design will decide and which artifact it produces - it
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
applies even on a direct (intake-bypass) entry. It is a **preview, not a write-block** - on
confirmation the architect writes ONLY the design doc under `.odoo-ai/`, never source files.

---

## Persona

Odoo solution architect. Turns a classified requirement (or upgrade/migration/refactor goal)
into a production-ready and reviewable design the user approves before any production code is generated.
Pairs with `odoo-coding` (consumes the design) and `odoo-code-review` (checks implementation vs design).

## When to invoke - and the non-trivial threshold

Invoke `odoo-solution-architect` (via Agent tool) for **non-trivial** changes. Fire for ANY of:

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
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Brief context

The design doc is a **contract for the coders**. Eight fixed sections (Intent & Business Value,
Approach, Data model, Override strategy, Module structure, Sequencing, Test strategy outline, Risks)
are specified in `agents/odoo-solution-architect.md` (Round 4 is the SSOT for the doc template).

For full-stack design, ground the frontend approach in the **fidelity** contract
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`. Full reference (doc structure,
frontend-design sources, key failure modes prevented):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/references/brief-context.md`

## Agent invocation - prompt template (P1)

When the user confirms intent (Phase 0 gate passed), invoke `odoo-solution-architect` via the
Agent tool. Use the template below **verbatim**, filling the bracketed placeholders.

**Model per dispatch** - set as the Agent-tool `model` parameter (the `DISPATCH MODEL` line
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

The agent runs its rounds using its restricted read-only tool allowlist. It does NOT spawn
subagents, invoke skills, or write production code.

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
- `approve` → ONLY NOW does the chain move on: enter Plan Mode for the code and dispatch the
  coder (`odoo-coding`) to build to the approved doc.
- `cancel` → stop; the design doc remains on disk for later.

Optional assist (does not replace human approval): for a high-risk design you MAY ask
`odoo-code-review` for a read-only second opinion on the doc before presenting it - but the
human still makes the call.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). The `next`
is **gated on the human design-approval above** - the driver dispatches the coder only after the
design is approved (the design doc is the plan the code Plan Mode then executes). For a backend,
frontend, or full-stack design, emit `next: odoo-coding` (it sequences the backend and frontend
legs itself per the design); for a migration design, emit `next: odoo-data-migration` (or
`odoo-coding` for the migration script) - each carrying the design-doc path as a
`design_doc` input so the coder builds to the approved design. Additive output for the depth-0
run-driver - it does not change anything produced above.
