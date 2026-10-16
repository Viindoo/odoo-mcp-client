---
name: odoo-doc-walkthrough
argument-hint: "[module] [slug]"
description: >-
  Text-only step-by-step usage scenarios for an Odoo module
---

## Role

Front door for the text-only usage walkthrough of one module: one happy-path scenario per task
each business role performs, in process order, the administrator's setup first, grounded in what
the module does. It launches `odoo-doc-writer` in `MODE: catalog-only` (the walkthrough is one of
its three shared files; a catalog and role map the caller holds are forwarded, not rebuilt) and
returns the paths. No browser, no instance, no test execution.

## Out of Scope

- **Executable test code** (tours, HttpCase, pytest) -> `odoo-test-writing`
- **Live UI acceptance testing with a PASS/FAIL verdict** -> `odoo-acceptance`
- **Marketing copy** (landing page, email, social, App Store description) -> `odoo-content-draft`
- **Technical architecture or solution design before code is written** -> `odoo-solution-design`
- **Negative, boundary or permission-violation scenarios** -> `odoo-qa-suite` / `odoo-acceptance`
- **Video or GIF recording of a live walkthrough** -> `odoo-demo-recording`

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
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
<!-- END GENERATED TOOLS -->

## Steps

1. Resolve `MODULE`, `MODULE_PATH`, `ODOO VERSION` and `PROFILE`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`); capture `SHARE_DIR` and
   `ISOLATE_DIR` once with `project_dir`. An unresolved series is `NEEDS_CONTEXT(odoo_version)`.
2. Launch `odoo-doc-writer` (`model: sonnet`, `MODE: catalog-only`) with the brief in
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/writer-brief.md`
   § `catalog-only`, with `FEATURE CATALOG` and `ROLE MAP` when the caller holds them. The
   walkthrough lands in `<SHARE_DIR>/documentation/<RUN_ID>/<MODULE>/walkthrough.jsonl` and
   `walkthrough.md` (schema: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/doc-artifacts.md`).
3. Return the paths and the grounding.

## Standalone-first fallback

OSM unreachable: the writer grounds the scenario steps from the module tree, labels them
`local-source` and prefixes its report with a warning to verify labels on a live instance.

## Agent-managed tools

`odoo-doc-writer` (`MODE: catalog-only`).

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
two paths; `next: odoo-doc-illustration` with `CAPTURE MODE: scenarios` when the caller wants the
scenarios captured.
