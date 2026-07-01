---
name: odoo-doc-feature-map
argument-hint: "[module-name]"
description: >
  Enumerate ALL features, menus, views, and models a module ships - output is a machine-readable
  `feature-catalog.jsonl` (one entry per capability: name, type, menu path, model, business purpose,
  key fields) as the shared SSOT for the landing Key Features grid, the Usage guide, and walkthrough
  scripts. Dispatches `odoo-feature-cataloger`. Trigger on: "liệt kê tính năng module cho tài liệu",
  "feature inventory for doc", "bản đồ tính năng module X", "list all features of module",
  "catalog module screens for documentation", "danh sách màn hình / menu của module",
  "module capability map". Standalone-first (OSM + disk; no browser or live instance needed).
  route a single feature yes/no -> odoo-feature-check; route marketing highlights for a version
  release -> odoo-feature-highlights; route an executive audit of CUSTOM code in a client instance
  -> odoo-customization-inventory. DO NOT trigger for a one-feature availability check, a version
  release marketing brief, or a custom-code engagement audit
---

## Role

Documentation analyst: enumerates every user-visible capability a module ships - menus, views,
models, actions, and key fields - and packages the result as a reusable machine-readable catalog.
This catalog is the shared SSOT consumed by the landing Key Features grid, the Usage guide
sections, and the walkthrough scenario author. NOT an auditor of custom code (->
`odoo-customization-inventory`) and NOT a feature availability checker (-> `odoo-feature-check`).

## Out of Scope

- **Single feature yes/no** (does module X have Y?) -> `odoo-feature-check`
- **Marketing highlights for a version release** (what is new in v18?) -> `odoo-feature-highlights`
- **Executive audit of CUSTOM code in a client instance** -> `odoo-customization-inventory`
- **Writing the user guide or landing copy** -> `odoo-doc-illustration` / `odoo-content-draft`
- **Live instance required** - this skill is read-only and browser-free; for live record queries use
  a live Odoo MCP server

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
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
<!-- END GENERATED TOOLS -->

## Context

The feature catalog is a MODULE-DRIVEN artifact: it enumerates what the module SOURCE defines, not
what a client's running instance has enabled. It is the canonical input for:

1. The landing **Key Features grid** (`value` field per entry feeds the grid copy)
2. The **Usage guide** "Features" section (each entry maps to a guide subsection)
3. The **walkthrough scenario author** (`odoo-doc-scenarist`): entry points, states, and key fields
   drive the authored happy-path step lists

Grounding is OSM-first (static indexed source), disk fallback (manifest + views + security on
disk). A live instance is NEVER required for catalog production.

## Agent invocation

Dispatch `odoo-feature-cataloger` with the following brief:

```
MODULE: <module technical name>
MODULE_PATH: <absolute path to the module dir on disk, if resolvable>
ODOO_VERSION: <concrete version from context.md or manifest, e.g. 17.0>
PROFILE: <viindoo_profile from .odoo-ai/context.md, or omit if absent>
OUTPUT_DIR: .odoo-ai/documentation/<slug>/<module>/
```

`OUTPUT_DIR` is the per-module subdir (`<slug>` = run id, `<module>` = module technical name) so a
multi-module run never collides on a flat `feature-catalog.jsonl`. Producer and consumer agree on
this path: the walkthrough/illustration phases read the catalog from the same `<slug>/<module>/`.

`MODULE_PATH` is optional but speeds up disk fallback. Derive `ODOO_VERSION` from `.odoo-ai/context.md`
-> `__manifest__.py` `version` field major prefix -> addons-dir regex -> ask if none found.

## Standalone-first fallback

Odoo Semantic MCP (OSM) is the PRIMARY source. If OSM is unreachable, the agent falls back to
reading `__manifest__.py`, grepping `views/` and `models/` on disk, and reading
`security/ir.model.access.csv` directly. Prefix any disk-only output with:
`WARNING: OSM unreachable - catalog grounded from disk only; verify completeness`.

No browser, no live Odoo instance, no screenshot capture is performed by this skill. If the caller
needs screenshots or a live UI pass, route to `odoo-doc-illustration` after the catalog is produced.

## Continuation Contract

After the agent completes, emit the Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. Typical next steps:
- `status: NEEDS_NEXT` with `next: odoo-doc-walkthrough` when the caller needs usage scenarios
  grounded in the catalog
- `status: DONE` when the catalog alone was requested
