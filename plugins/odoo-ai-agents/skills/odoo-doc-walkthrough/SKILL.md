---
name: odoo-doc-walkthrough
argument-hint: "[module] [slug]"
description: >
  Author happy-path usage walkthroughs for an Odoo module: structured scenarios
  (name, role, precondition, steps {action/target/value}, expected outcome)
  grounded in the module's ACTUAL behavior via OSM. Dispatches odoo-doc-scenarist.
  Fire on: "write walkthrough for module", "document how to use this feature",
  "step-by-step user guide", "lập kịch bản sử dụng cho tính năng",
  "user workflow cho module", "hướng dẫn từng bước cho luồng",
  "walkthrough for module", "viết kịch bản dùng chức năng".
  Standalone-first; OSM PRIMARY; no browser or instance needed.
  route executable tests (tours/HttpCase) -> odoo-test-writing;
  route live UI QA + PASS/FAIL verdict -> odoo-acceptance;
  route marketing copy -> odoo-content-draft;
  route pre-code architecture -> odoo-solution-design.
  DO NOT trigger for: executable test code -> odoo-test-writing;
  live acceptance + verdict -> odoo-acceptance;
  marketing/landing copy -> odoo-content-draft;
  architecture before implementation -> odoo-solution-design
---

## Persona

Documentation author producing user-facing walkthroughs for an Odoo module. You map the
module's positive usage flows into readable, structured scenarios a new user can follow -
grounded in what the module ACTUALLY does, not in requirements or test oracles.

You are a STANDALONE-FIRST authoring tool: OSM is your primary grounding source; you do
not need a browser, a live instance, or test execution to produce the walkthrough.

## Out of Scope

- **Executable test code** (tours, HttpCase, pytest) -> `odoo-test-writing`
- **Live UI acceptance testing with a PASS/FAIL verdict** -> `odoo-acceptance`
- **Marketing copy** (landing page, email, social, App Store description) -> `odoo-content-draft`
- **Technical architecture or solution design before code is written** -> `odoo-solution-design`
- **Negative / boundary / permission-violation test scenarios** - those belong in `odoo-qa-suite` or `odoo-acceptance`; this skill covers POSITIVE happy-path flows only
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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
<!-- END GENERATED TOOLS -->

## Dispatch brief

Main dispatches `odoo-doc-scenarist` with:

```
MODULE: <module technical name>
MODULE_PATH: <absolute path to module dir, if known>
ODOO_VERSION: <concrete series, e.g. 17.0>
SLUG: <short identifier for output paths, e.g. sale_order>
CATALOG_PATH: .odoo-ai/documentation/<slug>/<module>/feature-catalog.jsonl (written by odoo-doc-feature-map; omit if not run)
OUTPUT_DIR: .odoo-ai/documentation/<slug>/<module>/
USER LANGUAGE: <language for human-facing prose; identifiers stay English>
```

`OUTPUT_DIR` and `CATALOG_PATH` share the per-module subdir (`<slug>` = run id, `<module>` = module
technical name) so a multi-module run never collides on a flat `walkthrough.jsonl`/`feature-catalog.jsonl`,
and the scenarist reads the catalog from the exact path the feature-map phase wrote it (producer == consumer).

If `MODULE_PATH` is unknown, the scenarist resolves it from `.odoo-ai/context.md` or disk.
If `ODOO_VERSION` is not stated, the scenarist infers it from the module manifest `version`
field major digit or from the addons directory name pattern; if still unresolved it returns
`NEEDS_CONTEXT(odoo_version)` before proceeding.

Collect `walkthrough.md` (and optional `walkthrough.jsonl`) from the agent output path, then
emit a Continuation Contract per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`.

## Standalone-first fallback

When Odoo Semantic (the odoo-semantic-mcp server) is unreachable:
- Fall back to reading `__manifest__.py`, model `.py` files, and view XML on disk to enumerate
  menus, models, and key fields.
- Label the grounding in the output: `grounding: local-source`.
- Emit `WARNING: OSM unreachable - scenario steps inferred from disk source; verify labels
  against a live instance before publishing`.

When `CATALOG_PATH` is absent or the file does not exist:
- The scenarist derives the feature set directly from OSM `describe_module` / `module_inspect`
  (or disk fallback); the output is labeled `catalog: none`.
