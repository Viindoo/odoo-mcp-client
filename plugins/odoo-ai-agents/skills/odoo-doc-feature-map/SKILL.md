---
name: odoo-doc-feature-map
argument-hint: "[module-name]"
description: >-
  Catalogs a module's features, roles and usage scenarios as text, no screenshots
---

## Role

Front door for the three shared documentation files of one module: the feature catalog (every
user-visible capability with the access right that reaches it), the role map (the business roles
of a company that work with the module and the process they hand records along) and the role
walkthrough (one happy-path scenario per task each role performs, the administrator's setup
first, as text). A request for the catalog, the role map, the usage scenarios or the walkthrough
alone is this skill: the writer always produces all three, and a file the caller already holds is
forwarded, never rebuilt. It launches `odoo-doc-writer` in `MODE: catalog-only` and returns the
paths. No browser, no instance, no test execution. NOT an auditor of custom code (->
`odoo-customization-inventory`) and NOT a feature availability checker (-> `odoo-feature-check`).

## Out of Scope

- **Single feature yes/no** (does module X have Y?) -> `odoo-feature-check`
- **Marketing highlights for a version release** (what is new in v18?) -> `odoo-feature-highlights`
- **Executive audit of CUSTOM code in a client instance** -> `odoo-customization-inventory`
- **The user guide or the App Store page** -> `odoo-doc-illustration`
- **Executable test code** (tours, HttpCase, pytest) -> `odoo-test-writing`
- **Live UI acceptance with a PASS/FAIL verdict**, or negative and permission-violation scenarios
  -> `odoo-acceptance` / `odoo-qa-suite`
- **Marketing copy** (landing page, email, social) -> `odoo-content-draft`
- **Technical architecture or design before code** -> `odoo-solution-design`
- **Video or GIF of a live walkthrough** -> `odoo-demo-recording`
- **Live record queries** -> a live Odoo MCP server; this skill reads source only

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
<!-- END GENERATED TOOLS -->

## Steps

1. Resolve `MODULE`, `MODULE_PATH`, `ODOO VERSION` and `PROFILE`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`; never a series from a manifest
   `version` prefix); capture `SHARE_DIR` and `ISOLATE_DIR` once with `project_dir`. An
   unresolved module or series is `NEEDS_CONTEXT(<field>)`.
2. Launch `odoo-doc-writer` (`model: sonnet`, `MODE: catalog-only`) with the brief in
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/writer-brief.md`
   § `catalog-only`, forwarding any of the three files the caller already holds. The files land
   in `<SHARE_DIR>/documentation/<RUN_ID>/<MODULE>/`, the path every later doc step reads
   (schemas: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/doc-artifacts.md`).
3. Return the three paths and the grounding (`osm`, `hybrid`, `local-source`).

## Standalone-first fallback

OSM unreachable: the writer grounds from the module tree, labels the files `local-source` and
says so in its report.

## Agent-managed tools

`odoo-doc-writer` (`MODE: catalog-only`).

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
three paths; `next: odoo-doc-illustration` when the caller wants screenshots (with `CAPTURE MODE:
scenarios` to capture the walkthrough steps).
