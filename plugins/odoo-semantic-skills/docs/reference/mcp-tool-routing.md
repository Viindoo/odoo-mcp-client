# MCP Tool × Persona × Adapter Routing Matrix

> **Generated:** 2026-05-28T00:00:00Z  
> **Server version:** 0.11.1  
> **Source:** `generator/server-surface.json` — edit that file and run `make gen` to update.
> **v0.6 change:** 10 legacy tools (`resolve_model`, `resolve_field`, `resolve_method`, `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`, `list_qweb_templates`, `list_js_patches`) were removed. Use the superset tools (`model_inspect`, `module_inspect`, `entity_lookup`) instead.

## Purpose

Single-source documentation answering:
- Which MCP tool maps to which persona?
- Which trigger phrases route a user prompt to which tool?
- Where does each adapter (Cursor, Gemini Gem, Custom GPT, Claude plugin) duplicate this routing logic?
- How are skill keyword conflicts resolved?

When adding a new MCP tool or persona, update **`generator/server-surface.json`** first, then run `make gen` to propagate.

---

## 1. Tool × Persona Matrix

| MCP Tool | CEO | dev | consultant | marketer | sales |
|----------|:---:|:---:|:----------:|:--------:|:-----:|
| **model_inspect** ★ | ● | ● | ● |  |  |
| **module_inspect** ★ | ● | ● | ● | ● | ● |
| **entity_lookup** ★ |  | ● |  |  |  |
| find_examples |  | ● | ● | ● | ● |
| impact_analysis | ● | ● |  |  |  |
| lookup_core_api |  | ● | ● |  |  |
| api_version_diff |  | ● |  | ● | ● |
| find_deprecated_usage | ● | ● |  |  |  |
| lint_check |  | ● |  |  |  |
| cli_help |  | ● |  |  |  |
| suggest_pattern |  | ● | ● |  |  |
| check_module_exists | ● | ● | ● | ● | ● |
| find_override_point |  | ● |  |  |  |
| describe_module | ● | ● | ● | ● | ● |
| **set_active_version** ☆ | ● | ● | ● | ● | ● |
| **set_active_profile** ☆ | ● | ● | ● | ● | ● |
| **list_available_versions** ☆ | ● | ● | ● | ● | ● |
| **list_available_profiles** ☆ | ● | ● | ● | ● | ● |
| **resolve_stylesheet** ✦ |  | ● |  |  |  |
| **find_style_override** ✦ |  | ● | ● |  |  |
| **resolve_orm_chain** ⊕ |  | ● |  |  |  |
| **validate_domain** ⊕ |  | ● |  |  |  |
| **validate_depends** ⊕ |  | ● |  |  |  |
| **validate_relation** ⊕ |  | ● |  |  |  |

**Legend:** ● = primary persona for this tool.  
★ = superset tool (supersedes removed v0.6 tools).  
☆ = session-context tool (sticky 24h TTL per API key).  
✦ = stylesheet tools (CSS/SCSS/LESS indexing, v0.7+).  
⊕ = ORM-validation tools (static domain / @api.depends / relation / dotted-path checks, v0.8+).

### MCP Resources

Read-only bookmark-stable handles addressable via the `odoo://` URI scheme:

| URI template | Returns |
|---|---|
| `odoo://{version}/model/{name}` | Model record: inheritance chain, field count, defining modules. |
| `odoo://{version}/field/{model}/{field}` | Field record: type, compute method, definition module, is_related. |
| `odoo://{version}/method/{model}/{method}` | Method record: override chain, super_ratio, convention, source file. |
| `odoo://{version}/view/{xmlid}` | View record: xpath chain, inherit_id, language, arch. |
| `odoo://{version}/module/{name}` | Module record: manifest, defines/extends counts, license notice if restricted. |
| `odoo://{version}/pattern/{name}` | Pattern catalogue entry: code snippet, gotchas, language, min version. |
| `odoo://{version}/stylesheet/{module}/{file_path*}` | Stylesheet record: selectors, imports, variables, language (CSS/SCSS/LESS). |

---

## 2. Tool Trigger Phrases

### model_inspect ★ (added v0.5.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call. Supersedes removed resolve_model, list_fields, list_methods, list_views (v0.6). |
| **Personas** | dev, CEO, consultant |
| **Required params** | `model`, `method`, `odoo_version` |
| **Optional params** | `profile_name`, `field`, `method_name`, `start_index`, `limit`, `from_module`, `kind`, `view_type` |
| **Example call** | `model_inspect(model='sale.order', method='fields', odoo_version='17.0')` |
| **Routing keywords** | inspect model, fields of model, methods of model, views of model, model summary, full structure of model, everything about model, model schema, list fields, model_inspect |

### module_inspect ★ (added v0.5.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call. method ∈ {summary, views, owl, qweb, js, dependencies}. Supersedes removed list_views (module-scoped), list_owl_components, list_qweb_templates, list_js_patches (v0.6). method='dependencies' added v0.10.0. method='summary' shares describe_module's output and may include a 'License notice:' line for license-restricted modules (server v0.9.1+) — surface it to the user; do not retry or fabricate omitted content. |
| **Personas** | dev, CEO, consultant, marketer, sales |
| **Required params** | `name`, `method`, `odoo_version` |
| **Optional params** | `profile_name`, `start_index`, `limit`, `view_type`, `bound_model`, `era`, `target` |
| **Example call** | `module_inspect(name='sale_management', method='summary', odoo_version='17.0')` |
| **Routing keywords** | inspect module, module architecture, module UI artefacts, OWL components in module, QWeb templates in module, JS patches in module, module views, module overview, module_inspect |

### entity_lookup ★ (added v0.5.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module. Supersedes removed resolve_field, resolve_method, resolve_view (v0.6). |
| **Personas** | dev |
| **Required params** | `kind`, `odoo_version` |
| **Optional params** | `profile_name`, `model`, `field`, `method_name`, `xmlid`, `name`, `from_module` |
| **Example call** | `entity_lookup(kind='field', model='sale.order', field='amount_total', odoo_version='17.0')` |
| **Routing keywords** | lookup field, lookup method, lookup view, drill down on entity, find method on model, find field on model, override chain, entity_lookup |

### find_examples (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Semantic code search returning real indexed code snippets from the Odoo codebase. |
| **Personas** | dev, consultant, marketer, sales |
| **Required params** | `query`, `odoo_version` |
| **Optional params** | `limit`, `context_module`, `profile_name` |
| **Example call** | `find_examples(query='wizard with transient model', odoo_version='17.0')` |
| **Routing keywords** | show me examples, code example for, how is X used in codebase, real examples of, implementation example, find_examples |

### impact_analysis (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields. |
| **Personas** | CEO, dev |
| **Required params** | `entity_type`, `entity_name`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `impact_analysis(entity_type='field', entity_name='sale.order.amount_total', odoo_version='17.0')` |
| **Routing keywords** | what breaks if I change, impact of modifying, blast radius, dependencies of field, dependencies of method, safe to remove, risk of changing, impact_analysis |

### lookup_core_api (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement. |
| **Personas** | dev, consultant |
| **Required params** | `name`, `odoo_version` |
| **Optional params** | _(none)_ |
| **Example call** | `lookup_core_api(name='api.depends', odoo_version='17.0')` |
| **Routing keywords** | is API deprecated, signature of, how to use decorator, when was API added, status of API, Odoo core symbol, lookup_core_api |

### api_version_diff (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items. |
| **Personas** | dev, marketer, sales |
| **Required params** | `symbol`, `from_version`, `to_version` |
| **Optional params** | _(none)_ |
| **Example call** | `api_version_diff(symbol='name_get', from_version='16.0', to_version='17.0')` |
| **Routing keywords** | what changed between versions, breaking changes, API diff, new in Odoo version, deprecation between versions, api_version_diff |

### find_deprecated_usage (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Scan the indexed codebase for usages of deprecated API patterns. |
| **Personas** | CEO, dev |
| **Required params** | `odoo_version` |
| **Optional params** | `kind`, `profile_name` |
| **Example call** | `find_deprecated_usage(odoo_version='17.0')` |
| **Routing keywords** | deprecated API in code, pre-upgrade audit, deprecated patterns, upgrade risk scan, code using old API, find_deprecated_usage |

### lint_check (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Validate code against Odoo-specific lint rules (Python/JavaScript), or return corpus-level XML RelaxNG violation nodes (language='xml', server v0.9.1+). Inline # noqa: RULE_ID suppresses findings on that line. |
| **Personas** | dev |
| **Required params** | `odoo_version` |
| **Optional params** | `code`, `language` |
| **Example call** | `lint_check(code='...', language='python', odoo_version='17.0')` |
| **Routing keywords** | lint check, coding standards, OCA style violations, Odoo conventions check, code quality, lint_check |

### cli_help (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags. |
| **Personas** | dev |
| **Required params** | `odoo_version` |
| **Optional params** | `command`, `flag` |
| **Example call** | `cli_help(command='server', flag='--http-port', odoo_version='17.0')` |
| **Routing keywords** | odoo-bin options, CLI flag, odoo server command, deprecated CLI option, odoo-bin scaffold, cli_help |

### suggest_pattern (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns. |
| **Personas** | dev, consultant |
| **Required params** | `intent`, `odoo_version` |
| **Optional params** | `language`, `limit` |
| **Example call** | `suggest_pattern(intent='wizard with multi-step form', odoo_version='17.0')` |
| **Routing keywords** | best pattern for, design pattern Odoo, how to implement, pattern for wizard, recommended approach, suggest_pattern |

### check_module_exists (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Verify module availability, edition (CE/EE/Viindoo), and cross-version presence. |
| **Personas** | CEO, dev, consultant, marketer, sales |
| **Required params** | `name`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `check_module_exists(name='sale_management', odoo_version='17.0')` |
| **Routing keywords** | does module exist, is module in CE or EE, check if feature is in standard Odoo, module available in version, is feature standard, CE vs EE check, check_module_exists |

### find_override_point (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior. |
| **Personas** | dev |
| **Required params** | `model`, `method`, `odoo_version` |
| **Optional params** | `to_version` |
| **Example call** | `find_override_point(model='sale.order', method='action_confirm', odoo_version='17.0')` |
| **Routing keywords** | where to override, override point for method, safest place to extend, inject custom logic, extend method without breaking, find_override_point |

### describe_module (added v0.1.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Module manifest + defined/extended model counts + view/JS inventory in one call. Note: module_inspect with method='summary' returns the same data plus extras. Output may include a 'License notice:' line for license-restricted modules (server v0.9.1+). OEEL-1 modules are skipped by default — the notice is the intentional non-silent marker that content is withheld; surface it to the user, do not retry or fabricate the omitted content. |
| **Personas** | CEO, dev, consultant, marketer, sales |
| **Required params** | `name`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `describe_module(name='sale_management', odoo_version='17.0')` |
| **Routing keywords** | what does module do, describe module, module overview, manifest of module, what is inside module, describe_module |

### set_active_version ☆ (added v0.6.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Pin Odoo version for the session (24h TTL per API key); subsequent calls pass odoo_version='auto' to reuse it instead of repeating the version (it can no longer be omitted). |
| **Personas** | dev, CEO, consultant, marketer, sales |
| **Required params** | `odoo_version` |
| **Optional params** | _(none)_ |
| **Example call** | `set_active_version(odoo_version='17.0')` |
| **Routing keywords** | set version, use Odoo version, pin session to version, set active version, set_active_version |

### set_active_profile ☆ (added v0.6.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Pin tenant profile for the session so subsequent calls scope to one customer profile. |
| **Personas** | dev, CEO, consultant, marketer, sales |
| **Required params** | `profile_name` |
| **Optional params** | _(none)_ |
| **Example call** | `set_active_profile(profile_name='viindoo-internal')` |
| **Routing keywords** | set profile, use profile, switch to profile, pin profile, set active profile, set_active_profile |

### list_available_versions ☆ (added v0.6.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Enumerate which Odoo versions the server has indexed. Run before set_active_version when unsure what is available. |
| **Personas** | dev, CEO, consultant, marketer, sales |
| **Required params** | _(none)_ |
| **Optional params** | _(none)_ |
| **Example call** | `list_available_versions()` |
| **Routing keywords** | what versions are indexed, list Odoo versions, available versions in MCP, list_available_versions |

### list_available_profiles ☆ (added v0.6.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Enumerate which tenant profiles exist in the server index. Run before set_active_profile. |
| **Personas** | dev, CEO, consultant, marketer, sales |
| **Required params** | _(none)_ |
| **Optional params** | _(none)_ |
| **Example call** | `list_available_profiles()` |
| **Routing keywords** | what profiles exist, list indexed profiles, available tenant profiles, list_available_profiles |

### resolve_stylesheet ✦ (added v0.7.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain. LESS covers legacy v8-v11. |
| **Personas** | dev |
| **Required params** | `module`, `odoo_version` |
| **Optional params** | _(none)_ |
| **Example call** | `resolve_stylesheet(module='website_sale', odoo_version='17.0')` |
| **Routing keywords** | stylesheets in module, CSS files in module, SCSS files in module, LESS files in module, import chain for module, stylesheet inventory, resolve_stylesheet |

### find_style_override ✦ (added v0.7.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain. Covers CSS, SCSS, and LESS (LESS for the legacy pre-SCSS era, ~v8-v12). |
| **Personas** | dev, consultant |
| **Required params** | `selector_or_variable`, `odoo_version` |
| **Optional params** | `limit` |
| **Example call** | `find_style_override(selector_or_variable='.o_kanban_record', odoo_version='17.0')` |
| **Routing keywords** | where is CSS selector defined, find SCSS variable, find LESS variable, which module overrides style, branding override, selector origin, find_style_override |

### resolve_orm_chain ⊕ (added v0.8.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks. Preferred over entity_lookup for multi-hop paths. |
| **Personas** | dev |
| **Required params** | `model`, `dotted_path`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `resolve_orm_chain(model='sale.order', dotted_path='partner_id.country_id.code', odoo_version='17.0')` |
| **Routing keywords** | trace field path, dotted path resolve, multi-hop field chain, where does path end, field chain validation, resolve_orm_chain |

### validate_domain ⊕ (added v0.8.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Validate search domain terms: field-path resolution and operator version-awareness. Operator validity is version-aware (parent_of v9+, any/not any v17+). Logical connectors are skipped. |
| **Personas** | dev |
| **Required params** | `model`, `domain`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `validate_domain(model='sale.order', domain="[('partner_id.country_id', '=', 'VN')]", odoo_version='17.0')` |
| **Routing keywords** | is this domain valid, check domain, validate search domain, domain operators valid, validate_domain |

### validate_depends ⊕ (added v0.8.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos. Catches stale compute declarations before runtime failure. |
| **Personas** | dev |
| **Required params** | `model`, `method`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `validate_depends(model='sale.order', method='_compute_amount_total', odoo_version='17.0')` |
| **Routing keywords** | validate compute depends, check @api.depends, stale depends paths, validate_depends |

### validate_relation ⊕ (added v0.8.0+)

| Attribute | Value |
|-----------|-------|
| **Description** | Assert a relational field points at the expected comodel (many2one/one2many/many2many). Reports the actual comodel on mismatch. |
| **Personas** | dev |
| **Required params** | `model`, `field`, `target_model`, `odoo_version` |
| **Optional params** | `profile_name` |
| **Example call** | `validate_relation(model='sale.order', field='partner_id', target_model='res.partner', odoo_version='17.0')` |
| **Routing keywords** | does field point to model, check relation target, is field many2one to, comodel of field, validate_relation |

---

## 3. Adapter Sync Map

When updating the tool surface, run `make gen` to propagate to all adapters.

| Adapter | File path | Format |
|---------|-----------|--------|
| Cursor IDE rules | `snippets/cursor-rules.md` | Markdown list + code snippets |
| Gemini Gem | `snippets/gemini-gem-instructions.md` | Instruction prose + tables |
| Custom GPT | `snippets/openai-gpt-instructions.md` | System instruction prose |
| Plugin skills | `skills/*/SKILL.md` | Between `<!-- BEGIN GENERATED TOOLS -->` markers |

---

## 4. Skill Conflict Resolution

Plugin skills can claim overlapping trigger keywords. Standard resolution policy:

### 4.1 `odoo-risk-overview` vs `odoo-deprecation-audit`

- **Overlap:** "upgrade risk", "is our code ready for v17", "what breaks in our system"
- **Resolution:** `odoo-risk-overview` → CEO/Manager persona (executive summary, LOW/MEDIUM/HIGH labels). `odoo-deprecation-audit` → Developer persona (file:line evidence, code-level fixes).
- **Heuristic:** User mentions "team", "budget", "timeline", "business risk" → `odoo-risk-overview`. User shows code or mentions specific module/file → `odoo-deprecation-audit`.

### 4.2 `odoo-version-diff` vs `odoo-feature-highlights`

- **Overlap:** "what's new in Odoo 17", "what's new in v17", "feature comparison"
- **Resolution:** `odoo-version-diff` → Developer persona (API changes, migration guide, breaking changes). `odoo-feature-highlights` → Marketer persona (sales-deck tone, business value, announcement copy).
- **Heuristic:** "migration", "breaking", "API", "deprecation" → `odoo-version-diff`. "highlight", "sales deck", "blog post", "announcement" → `odoo-feature-highlights`.

### 4.3 `odoo-feature-check` vs `odoo-addon-diff`

- **Overlap:** "is module X in CE or EE", "do we need Enterprise for feature Y"
- **Resolution:** `odoo-feature-check` → Consultant (requirement scoping, gap analysis). `odoo-addon-diff` → Marketer/Sales (edition comparison table for proposals).
- **Heuristic:** Embedded in scoping/gap context → `odoo-feature-check`. Standalone edition comparison → `odoo-addon-diff`.

### 4.4 `odoo-frontend-coder`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill — `odoo-frontend-coder` — owns all Odoo front-end work and handles both paradigms internally (merged from the former `odoo-js-coder` + `odoo-owl-coder`).
- **Resolution (internal):** `odoo-frontend-coder` selects the paradigm by version. Legacy JS widget system on older Odoo; OWL components on newer Odoo. Odoo v14 is the grey zone (pre-OWL but post-legacy peak) — prefer the legacy widget system there since it is still dominant.
- **Heuristic (paradigm signals):** `odoo.define()`, `web.Widget`, `field_registry` → legacy JS widget path. `useService`, `t-component`, `patch()`, `useState` → OWL path. Both resolve to `odoo-frontend-coder`.

---

## 5. Appendix: Tool × Adapter Quick Reference

| Tool | Cursor | Gemini | OpenAI |
|------|:------:|:------:|:------:|
| **model_inspect** ★ | ✓ | ✓ | ✓ |
| **module_inspect** ★ | ✓ | ✓ | ✓ |
| **entity_lookup** ★ | ✓ | ✓ | ✓ |
| **find_examples** | ✓ | ✓ | ✓ |
| **impact_analysis** | ✓ | ✓ | ✓ |
| **lookup_core_api** | ✓ | ✓ | ✓ |
| **api_version_diff** | ✓ | ✓ | ✓ |
| **find_deprecated_usage** | ✓ | ✓ | ✓ |
| **lint_check** | ✓ | ✓ | ✓ |
| **cli_help** | ✓ | ✓ | ✓ |
| **suggest_pattern** | ✓ | ✓ | ✓ |
| **check_module_exists** | ✓ | ✓ | ✓ |
| **find_override_point** | ✓ | ✓ | ✓ |
| **describe_module** | ✓ | ✓ | ✓ |
| **set_active_version** ☆ | ✓ | ✓ | ✓ |
| **set_active_profile** ☆ | ✓ | ✓ | ✓ |
| **list_available_versions** ☆ | ✓ | ✓ | ✓ |
| **list_available_profiles** ☆ | ✓ | ✓ | ✓ |
| **resolve_stylesheet** ✦ | ✓ | ✓ | ✓ |
| **find_style_override** ✦ | ✓ | ✓ | ✓ |
| **resolve_orm_chain** ⊕ | ✓ | ✓ | ✓ |
| **validate_domain** ⊕ | ✓ | ✓ | ✓ |
| **validate_depends** ⊕ | ✓ | ✓ | ✓ |
| **validate_relation** ⊕ | ✓ | ✓ | ✓ |

> **v0.11.1 tool surface (24 tools + 7 resources):** All tools are reached via HTTP MCP protocol to the Odoo Semantic MCP server. No logic is duplicated — only routing heuristics.
