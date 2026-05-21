# Odoo Semantic — Developer Guide

<!-- This persona intentionally enumerates the full tool arsenal (v0.6) instead of the "Most Useful Tools" template variant — devs need the full surface area, including the 3 M11 supersets and 4 session-context tools. -->

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` → `claude plugin install odoo-semantic@viindoo-plugins` → `/odoo-semantic:connect`. Chi tiết + AI tools khác: [client setup](../setup.md).

The full **tool arsenal (v0.6)**, optimized for development workflows. From understanding inheritance to safely extending core methods to enumerating fields/methods/views and UI-layer artefacts (OWL, QWeb, JS patches), this guide covers the daily patterns. v0.6 ships three discriminator-routed **supersets** (`model_inspect`, `module_inspect`, `entity_lookup`) plus four **session-context** tools that let you pin an Odoo version once and drop the `odoo_version=` arg from every subsequent call.

---

## All Tools Available to Developers (v0.6)

### Supersets (★ M11 Wave D — preferred over legacy siblings)

| Tool | Use case |
|------|----------|
| `model_inspect(model, method='summary'\|'fields'\|'methods'\|'views'\|'field'\|'method', ...)` | One call returns the model's summary, field list, method list, view inventory, or a single entity drill-down. **Replaces** `resolve_model` + `list_fields` + `list_methods` + `list_views`. |
| `module_inspect(module, method='summary'\|'views'\|'owl'\|'qweb'\|'js', ...)` | Module-level inventory across manifest, models, views, OWL, QWeb, JS patches. **Replaces** `describe_module` + `list_views` (module-scoped) + `list_owl_components` + `list_qweb_templates` + `list_js_patches`. |
| `entity_lookup(kind='field'\|'method'\|'view', ...)` | One entity drill-down by ID. **Replaces** `resolve_field` + `resolve_method` + `resolve_view`. |

### Session context (☆ M11 Wave E — sticky 24h TTL per API key)

| Tool | Use case |
|------|----------|
| `set_active_version(odoo_version)` | Pin the Odoo version for this session. Subsequent calls without `odoo_version=` fall back to this value. **Use once per debugging/exploration session** to drop ~10 chars of boilerplate from every call. |
| `set_active_profile(profile_name)` | Pin the tenant profile for cross-profile MCP deployments. |
| `list_available_versions()` | Discover which Odoo versions the server has indexed. |
| `list_available_profiles()` | Discover which profiles exist. |

### Existing tools (M1–M9, unchanged)

| Tool | Use case |
|------|----------|
| `find_examples` | Semantic code search across indexed repos |
| `impact_analysis` | Risk assessment before changing a field or method |
| `lookup_core_api` | Verify an API symbol exists and is not deprecated |
| `api_version_diff` | Identify breaking changes between Odoo versions |
| `find_deprecated_usage` | Audit your module for deprecated API usage |
| `lint_check` | Check module against Odoo coding standards |
| `suggest_pattern` | Find the canonical implementation pattern |
| `check_module_exists` | Verify module availability + CE/EE flag |
| `find_override_point` | Locate the safest method to override |
| `cli_help` | Look up `odoo-bin` flags and options |
| `describe_module` | Module architecture overview — manifest + defines/extends models + view/JS counts |

### Removed in v0.6

The 10 flat tools (`resolve_model`, `resolve_field`, `resolve_method`, `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`, `list_qweb_templates`, `list_js_patches`) were deprecated in v0.5 and **removed in v0.6**. They no longer exist on the server. Use the supersets above.

See the server [CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md) for side-by-side migration examples.

### MCP Resources (M11 Wave F — `odoo://` URI scheme)

Read-only handles for bookmark-stable access. Use these when you already know the entity ID and want the canonical record without a tool call: `odoo://{version}/{kind}/{id}` where `kind` is one of `model`, `field`, `method`, `view`, `module`, `pattern`, `stylesheet`. See [ADR-0030](https://github.com/Viindoo/odoo-semantic-server/blob/master/docs/adr/0030-mcp-resources-uri-scheme.md).

---

## Standard Development Workflow

### 0. Pin the version once

Before any exploration session, set the version so you can drop `odoo_version=` from every subsequent call:

```
set_active_version("17.0")
```

TTL is 24h per API key. Run `list_available_versions()` first if you're not sure which versions are indexed.

### 1. Understand before touching

Before adding logic to a model:

```
model_inspect(model="sale.order", method="summary")
```

Get the full inheritance chain, field count, method list, view inventory, and which modules have already extended this model — all in one call. Know what you're stepping into before writing a single line.

> Need one specific entity? Drill down with `entity_lookup(kind="field", model="sale.order", field="amount_total")` (or `kind="method"` / `kind="view"`).

### 2. Find the right extension point

Before writing an `@api.onchange`, `_compute_*`, or `super()` call:

```
find_override_point("sale.order", "action_confirm", "17.0")
```

Returns `super_safety` score and which modules are already overriding this method. If `super_ratio` is low, your override is at higher risk of being called out-of-order.

### 3. Get the pattern right

Before implementing a new pattern (computed cross-model field, wizard, report):

```
suggest_pattern("computed field that aggregates from child records with currency conversion")
```

Returns curated `PatternExample` nodes with code snippets, gotchas, and anti-pattern warnings from the indexed codebase.

### 4. Verify the API

Before calling any `@api.*` decorator, `name_get`, `_name_search`, or ORM method:

```
lookup_core_api("name_get", "17.0")
```

If the result shows `status: deprecated` or `removed_in: 17.0` — find the replacement before building on it.

### 5. Check your work

After writing the module:

```
lint_check("my_module", "17.0")
find_deprecated_usage("17.0")
```

---

## Sample Developer Questions

Copy these prompts into your AI tool:

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
   > "Using odoo-semantic, set_active_version 17.0 for this session. Then inspect sale.order method=summary — no need to repeat the version on follow-up calls."

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo Semantic plugin:

| Skill | What it does |
|-------|-------------|
| `/odoo-override-finder` | Given a model + method, returns safe override point + existing overrides + suggest_pattern |
| `/odoo-deprecation-audit` | Full deprecated API scan with replacement suggestions |
| `/odoo-version-diff` | Side-by-side API diff between two Odoo versions for a given symbol |

---

## Tips

- Always pass the `odoo_version` parameter — results differ significantly between versions.
- `find_override_point` returns `anti_patterns` — read them before writing.
- If `model_inspect` shows more than 10 modules extending a model, consider whether your extension logic could conflict with others.
- `suggest_pattern` queries are semantic, not keyword — describe what you want to achieve, not what method to use.
