---
name: odoo-solution-design
argument-hint: "[feature/requirement to design]"
description: >-
  Design how to build a non-trivial Odoo change before coding. Build order -> odoo-planning
---

## Where this sits in the flow

```
SRS (architect)  ->  human gate  ->  recon (haiku)  ->  design (architect)  ->  human gate
   ->  odoo-planning (two or more nodes)  |  odoo-coding (one node)  ->  review and acceptance
```

One architect session carries the whole left half; this skill resolves its inputs, launches it,
relays each gate to the human and resumes the SAME session with the answer. Output lives under
`<SHARE_DIR>/designs/` (resolve `<SHARE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`, substitute the captured absolute path),
never production source.

## Role

Front door for designing an Odoo change. Turns a requirement into an approved SRS and design that
`odoo-planning` or `odoo-coding` consumes, with a build-tier hint per node.

## Before dispatch

1. Resolve `<SHARE_DIR>` and `<ISOLATE_DIR>` once. Read the worklog if one exists.
2. Read the gap artifact when one exists (`<SHARE_DIR>/gap-analysis/*/gap-matrix.jsonl` or
   `<SHARE_DIR>/brl/<job-id>/`): it is the effort source; never paste a tier into the request.
3. Decide `SRS_REQUIRED`. `yes` when the request has at least one of: a new module; a new model;
   two or more business functions (`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`); an
   override of `create`, `write`, `unlink` or an `action_*` method of a core model; a new menu,
   report or screen for an end user. Otherwise `no`.
4. Enumerate the modules in scope from the first artifact available: deep-survey `synthesis.md`,
   BRL `dag.json`, modules-upgrade `graph.md`, else the module descriptors on disk. Master-child
   mode is proposed only when more than one module is in scope AND the gap artifact grades at
   least two of them `Extension-L` or `Custom-XL`; then ask once, in the user's language:
   `approve-single` (default) / `approve-master-child` / `cancel`. Nothing else is asked before
   dispatch.

## Dispatch (P1)

Launch `odoo-solution-architect` with `model: opus` and the fields below; fill the universal
skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton read by path.

```
DISPATCH MODEL: opus
MODE: design-session | master | child | consistency | reconcile | review
REQUEST: <the requirement, target models when known>
ODOO VERSION: <version>        PROFILE: <profile | none>
WORKTREE_PATH: <the checkout the change will be built in | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
SRS_REQUIRED: yes | no
DOMAIN: <Domain line | omit>
GAP_MATRIX: <abs path | omit>
RETURN_TO: <caller skill | omit>     DESIGN_SLUG_HINT: <slug | omit>
USER LANGUAGE: <language>
```

`fable` is never the launch tier. When the architect's design return carries
`fable_proposed: yes`, ask the human in plain words - "<node> changes an inheritance axis across
several modules: run the design on the deepest-reasoning setting? About 2x the cost
(approve / skip / cancel)" - and on `approve` relaunch the design step at `model: fable`; on
`skip` keep the opus design and record `fable declined` in the design header.

## Gates (the human decides; the same session continues)

The architect stops with `status: NEEDS_CONTEXT` and `gate: srs` or `gate: design`. Present its
`summary` and `artifact` in the user's language (paths, module and model names verbatim), then
ask `approve / refine: <feedback> / cancel`. Send the answer to the SAME architect with
`SendMessage` - never a new launch; the session holds the SRS, the recon and the grounding. On
`cancel` the artifacts stay on disk.

Optional at `gate: design`: `review` launches a fresh `odoo-solution-architect` in `MODE: review`
(`model: opus`) over the design; present its findings and re-ask the same gate.

## Master-child branch (after `approve-master-child`)

Contract SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` (layout,
`index.yaml`, §10, contested symbols, handoff fields). The orchestration:
a. `MODE: master` -> gate `approve-master` / `review-master` / `refine:` / `cancel`.
b. Children per `dag_layers`, layer by layer, same-layer children in one batch under Mode B of
   the guard; each child brief carries `CHILD_MODULE`, `MASTER_DESIGN_DOC`, and the lower-layer
   child designs it depends on. After a layer returns, read `contested-symbols.md`; when it has
   rows, launch `MODE: reconcile`, write its verdicts into the master verbatim, resume only the
   children whose proposal lost. One reconcile round per layer; an `UNRESOLVED` row blocks for
   the human. Write `status: designed` per module into `index.yaml` as each child returns.
c. `MODE: consistency` once every child is `designed`; it is the sole `index.yaml` and §10
   applier and emits `conflict-list.md` (lead-resolved and escalated seams).
d. One batch gate: every escalated seam for the human, every lead-resolved seam listed with its
   evidence, one summary per child. `approve-all` / `review-children` / `refine:<module>:` /
   `cancel`. On `approve-all`, write `status: approved` per module.
e. Continuation Contract with `design_index`, `master_design_doc`, `design_docs` under `inputs`
   (the contract's canonical form); never a bare `design_doc`.

## Payload mapping when `return_to` is set

A caller such as `odoo-forward-port` supplies `return_to` and a payload; map it field by field per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/references/return-to-payload.md`. Every
`design_proposals` entry comes back `adopted` or `rejected`.

## Out of Scope

- **Writing production code** -> `odoo-coding`
- **Reviewing existing code** -> `odoo-code-review`
- **Finding ONE method's hook location** -> `odoo-override-finding`
- **Classifying or costing a requirement list** -> `odoo-brl` (large) or `odoo-gap-analysis` (short)
- **Version-to-version API delta** -> `odoo-version-diff`; **deprecation scan** -> `odoo-deprecation-audit`
- **User-facing walkthrough or scenario text** -> `odoo-doc-feature-map`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
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

## Deliverable shape

Three documents under `<SHARE_DIR>/designs/`: the SRS (`<slug>-<date>-srs.md`: roles, scope,
interactions, non-functional, demo data, acceptance criteria with expected values, effort, the
Domain line), the recon (`<SHARE_DIR>/recon/<slug>-<date>/recon.md`, written by
`odoo-impact-recon`), and the design (`<slug>-<date>.md`, light or full, with one `## Nodes`
block carrying `build_tier_hint` per node). The architect's own body owns every template.

## Standalone-first fallback

When OSM is unreachable the architect grounds from the checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` and the design header says
`grounded: local-source`; nothing here changes.

## Agent-managed tools

The architect inherits the full tool surface and launches only `odoo-impact-recon` by default;
the grounding skills it may invoke are listed in its own body. It launches no coder, reviewer or
executor.

## Continuation Contract

After the human approves the design, emit the block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`:
- `return_to` SET: `next: <return_to>`, `inputs: {design_doc: <path>}` (master-child: the
  contract's canonical `inputs`).
- `return_to` UNSET: `next: odoo-planning` when the design has two or more nodes;
  `next: odoo-coding` when it has one (the main agent fills the single-node plan from the default
  template of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md`); a
  single-module migration script meeting
  `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Migration carve-out goes to
  `next: odoo-data-migration`. `inputs` always carries `srs`, `recon` and `design_doc`.
