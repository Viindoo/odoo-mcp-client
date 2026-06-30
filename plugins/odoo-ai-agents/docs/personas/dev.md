# Odoo Semantic - Developer Guide

<!-- This persona intentionally enumerates the full 25-tool arsenal (server v0.13.1) instead of the "Most Useful Tools" template variant - devs need the full surface area, including the 4 superset tools, 4 session-context tools, 11 base tools, 2 stylesheet tools, and 4 ORM-validation tools. -->

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (auto-pulls `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. For other AI tools, see [client setup](../setup.md).

The full **25-tool arsenal (server v0.13.1)**, optimized for development workflows - understanding inheritance, safely extending core methods, enumerating fields/methods/views and UI-layer artefacts (OWL, QWeb, JS patches), CSS/SCSS/LESS stylesheet analysis, and static ORM validation. The 25 break into five groups, each enumerated with its version era in the sections below: four discriminator-routed **supersets** (`model_inspect`, `module_inspect`, `entity_lookup`, plus profile-level `profile_inspect`, v0.13+), four **session-context** tools (pin a version once, pass `odoo_version='auto'`), eleven **base tools**, two **stylesheet tools** (theme/branding), and four **ORM-validation tools** (catch hallucinated field-paths, operators, dependencies, relation targets before you ship a domain / `@api.depends` / relational field).

---

## All Tools Available to Developers (server v0.13.1)

### Supersets (v0.5+ - preferred over legacy siblings)

| Tool | Use case |
|------|----------|
| `model_inspect(model, method='summary'\|'fields'\|'methods'\|'views'\|'extenders'\|'field'\|'method', ...)` | One call returns the model's summary, field list, method list, view inventory, paginated extender list, or a single entity drill-down. **Replaces** `resolve_model` + `list_fields` + `list_methods` + `list_views`. |
| `module_inspect(module, method='summary'\|'views'\|'owl'\|'qweb'\|'js'\|'dependencies', ...)` | Module-level inventory across manifest, models, views, OWL, QWeb, JS patches, dependencies. **Replaces** `describe_module` + `list_views` (module-scoped) + `list_owl_components` + `list_qweb_templates` + `list_js_patches`. |
| `entity_lookup(kind='field'\|'method'\|'view', ...)` | One entity drill-down by ID. **Replaces** `resolve_field` + `resolve_method` + `resolve_view`. |
| `profile_inspect(profile, method='summary'\|'repos'\|'modules', ...)` | Profile-level introspection: inheritance chain + repos + module inventory (method=summary\|repos\|modules). |

### Session context (per-API-key pin, 24h idle TTL - racy under concurrency)

| Tool | Use case |
|------|----------|
| `set_active_version(odoo_version)` | Pin the Odoo version for this session. Subsequent calls without `odoo_version=` fall back to this value. **Use once per debugging/exploration session** to drop ~10 chars of boilerplate from every call. |
| `set_active_profile(profile_name)` | Pin the tenant profile for cross-profile MCP deployments. |
| `list_available_versions()` | Discover which Odoo versions the server has indexed. |
| `list_available_profiles()` | Discover which profiles exist. |

### Existing tools (v0.1-v0.4, unchanged)

| Tool | Use case |
|------|----------|
| `find_examples` | Semantic code search across indexed repos |
| `impact_analysis` | Risk assessment before changing a field or method |
| `lookup_core_api` | Verify an API symbol exists and is not deprecated |
| `api_version_diff` | Identify breaking changes between Odoo versions |
| `find_deprecated_usage` | Audit your module for deprecated API usage |
| `lint_check` | Check module against Odoo coding standards; inline `# noqa: RULE_ID` in code suppresses findings on that line |
| `suggest_pattern` | Find the canonical implementation pattern |
| `check_module_exists` | Verify module availability + CE/EE flag |
| `find_override_point` | Locate the safest method to override |
| `cli_help` | Look up `odoo-bin` flags and options |
| `describe_module` | Module architecture overview - manifest + defines/extends models + view/JS counts |

### Stylesheet tools (v0.7+)

| Tool | Use case |
|------|----------|
| `resolve_stylesheet(module, odoo_version="auto")` | Enumerate a module's CSS/SCSS/LESS stylesheet files - language, selector/variable/mixin/import counts, `@import` chain. Use to audit what a module ships before writing theme overrides. LESS covers the legacy pre-SCSS era (~v8-v12). |
| `find_style_override(selector_or_variable, odoo_version="auto", limit=5)` | Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain. Essential for theming/branding work. Covers CSS, SCSS, and LESS (LESS for the legacy pre-SCSS era, ~v8-v12). |

### ORM-validation tools (server v0.8.0+)

Static checks against the indexed graph. Run them **before** emitting a domain, `@api.depends`, or relational field - they catch hallucinated field-paths, invalid operators, and wrong comodels that would otherwise surface only at runtime.

| Tool | Use case |
|------|----------|
| `resolve_orm_chain(model, dotted_path, odoo_version="auto")` | Walk a dotted field path (`partner_id.country_id.code`) hop by hop; returns the terminal field type or a `BROKEN` line naming the first unresolved hop. Use to verify a multi-hop `related=` chain or domain path resolves. |
| `validate_domain(model, domain, odoo_version="auto")` | Validate every `(field_path, operator, value)` term of a search domain. Operator validity is **version-aware** (`parent_of` v9+, `any`/`not any` v17+). Run before pasting a domain into a view, `ir.rule`, or `search()`. |
| `validate_depends(model, method, odoo_version="auto")` | Validate an indexed compute method's `@api.depends('a.b', ...)` paths; flags depends on `id` (forbidden) and suggests the closest field for typos - directly catches the "stale compute" failure mode. |
| `validate_relation(model, field, target_model, odoo_version="auto")` | Assert a field is a many2one/one2many/many2many whose comodel is `target_model` (or a subtype via inheritance). Use before writing a `related=` that hops through a relation. |

> Prefer these over `entity_lookup(kind='field', ...)` when you have a *path* (`resolve_orm_chain`), a *full domain* (`validate_domain`), a *declared depends* (`validate_depends`), or a *comodel assertion* (`validate_relation`) - they reason about the whole construct, not one field.

### Removed in v0.6

The 10 flat tools (`resolve_model`, `resolve_field`, `resolve_method`, `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`, `list_qweb_templates`, `list_js_patches`) were deprecated in v0.5 and **removed in v0.6**. They no longer exist on the server. Use the supersets above.

See the server [CHANGELOG](https://odoo-semantic.viindoo.com/changelog) for side-by-side migration examples.

### MCP Resources (`odoo://` URI scheme, v0.5+)

Read-only handles for bookmark-stable access. Use these when you already know the entity ID and want the canonical record without a tool call: `odoo://{version}/{kind}/{id}` where `kind` is one of `model`, `field`, `method`, `view`, `module`, `pattern`, `stylesheet`. See the [MCP resources URI scheme docs](https://odoo-semantic.viindoo.com/docs/adr/0030-mcp-resources-uri-scheme).

---

## Standard Development Workflow

### 0. Pin the version once

Before any exploration session, set the version so you can drop `odoo_version=` from every subsequent call:

```
set_active_version("<version>")
```

TTL is 24h idle and the pin is per-API-key server state - any concurrent agent or session sharing the key can overwrite it, so pass the concrete version on every call under concurrency. Run `list_available_versions()` first if you are not sure which versions are indexed.

### 1. Understand before touching

Before adding logic to a model:

```
model_inspect(model="sale.order", method="summary", odoo_version='<version>')
```

Get the full inheritance chain, field count, method list, view inventory, and which modules have already extended this model - all in one call. Know what you are stepping into before writing a single line.

> Need one specific entity? Drill down with `entity_lookup(kind="field", model="sale.order", field="amount_total", odoo_version='<version>')` (or `kind="method"` / `kind="view"`).

### 2. Find the right extension point

Before writing an `@api.onchange`, `_compute_*`, or `super()` call:

```
find_override_point("sale.order", "action_confirm", "<version>")
```

Returns `super_safety` score and which modules are already overriding this method. If `super_ratio` is low, your override is at higher risk of being called out-of-order.

### 3. Get the pattern right

Before implementing a new pattern (computed cross-model field, wizard, report):

```
suggest_pattern("computed field that aggregates from child records with currency conversion", odoo_version='<version>')
```

Returns curated pattern entries with code snippets, gotchas, and anti-pattern warnings from the indexed codebase.

### 4. Verify the API

Before calling any `@api.*` decorator, `name_get`, `_name_search`, or ORM method:

```
lookup_core_api("name_get", "<version>")
```

If the result shows `status: deprecated` or `removed_in: <version>` - find the replacement before building on it.

### 5. Check your work

After writing the module:

```
lint_check(code=<module source>, odoo_version='<version>')
find_deprecated_usage(odoo_version='<version>')
```

---

## Sample Developer Questions

Example invocations (an AI agent can run these directly as NL dispatch; a human reader can copy them into their AI tool):

1. **Model exploration (superset):**
   > "Using odoo-semantic, inspect account.move with method=summary in Odoo 17.0. Show the inheritance chain and group fields by module."

2. **Safe extension:**
   > "Using odoo-semantic, find_override_point for account.move action_post in Odoo 17.0. Is it safe to override? What is the super_ratio?"

3. **Pattern lookup:**
   > "Using odoo-semantic, suggest_pattern for implementing an onchange that updates a computed monetary field across multiple models in Odoo 17."

4. **Pre-upgrade audit:**
   > "Using odoo-semantic, find_deprecated_usage for Odoo 17.0 in our codebase. List all HIGH risk items with file locations."

5. **View override (superset):**
   > "Using odoo-semantic, entity_lookup kind=view xmlid=sale.view_order_form in Odoo 17.0. Show the full XPath chain so I know exactly where to inject my override."

6. **Session pin:**
   > "Using odoo-semantic, set_active_version 17.0 for this session. Then inspect sale.order method=summary - no need to repeat the version on follow-up calls."

7. **ORM validation (before shipping a domain / depends):**
   > "Using odoo-semantic, validate_domain on sale.order for `[('partner_id.country_id.code', '=', 'US'), ('state', 'any', ...)]` in Odoo 16 - are the field-paths and operators valid for that version?" (and: "validate_depends for _compute_amount_total on sale.order - are all @api.depends paths real?")

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo AI Agent Team plugin:

| Skill | What it does |
|-------|-------------|
| `odoo-solution-design` | Design the technical solution (approach / data model / override strategy / module structure / sequencing / test outline / risks) into a gate-able design doc BEFORE coding - the analysis-and-design step for non-trivial work; chains to `odoo-coding` |
| `/odoo-override-finding` | Given a model + method, returns safe override point + existing overrides + suggest_pattern |
| `/odoo-deprecation-audit` | Full deprecated API scan with replacement suggestions |
| `/odoo-version-diff` | Side-by-side API diff between two Odoo versions for a given symbol |
| `odoo-test-writing` | Write executable `test_*.py` (or JS Hoot/QUnit) that assert business behavior, not current code |
| `odoo-security-audit` | Audit code for SQLi / XSS / access-control / CSRF / unsafe deserialization, graded findings |
| `odoo-perf-audit` | Audit for N+1, missing prefetch, unindexed domains, compute thrash, with concrete fixes |
| `odoo-data-migration` | Write pre/post migration scripts + a verification plan (does not execute against an instance) |
| `odoo-git-rebase` | Rebase a feature branch onto another branch of the same Odoo series, absorbing intent (not code text) via whole-range `git rebase --onto` |
| `odoo-modules-upgrade` | Upgrade a custom module cluster from a lower Odoo major to a higher one (code-level): drop what core now provides, adapt the rest, 1 PR per cluster |
| `odoo-planning` | Turn an approved design into the EXECUTION plan that ships it - a wave-batched module-DAG wiring each module/stage to a skill across the full lifecycle (code -> review -> doc -> PR -> monitor -> merge). The sequencer `run-harness` then drives it, landing each coding wave-layer through the internal `odoo-wave` git-executor (one squashed PR per wave) and the async `odoo-pr-monitoring` poller to merge. |

---

## Tips

- Always pass the `odoo_version` parameter - results differ significantly between versions.
- `find_override_point` returns `anti_patterns` - read them before writing.
- If `model_inspect` shows more than 10 modules extending a model, consider whether your extension logic could conflict with others.
- `suggest_pattern` queries are semantic, not keyword - describe what you want to achieve, not what method to use.
