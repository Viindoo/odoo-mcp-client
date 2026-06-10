# Odoo Semantic — Cursor Rules

## Overview

These rules configure Cursor IDE to automatically route Odoo-related questions through the Odoo Semantic MCP server. Add them to `.cursorrules` in your project root, or paste into **Cursor Settings → Rules for AI** (applies globally).

---

## Add to `.cursorrules`

```
# Odoo Semantic MCP — Developer Rules (v0.13.1 tool surface)
# Auto-triggers for Odoo codebase intelligence via MCP

## Session bootstrap (run once per chat session)
- At session start, call list_available_versions() to discover indexed versions
- Pin the version with set_active_version("17.0") — the pin is per-API-key server state (24h idle TTL); racy under concurrency
- Pass the concrete version on every call - the pin is per-API-key and racy under concurrency (omitting odoo_version raises a validation error)
- Pin tenant with set_active_profile("<name>") if multi-tenant MCP

## When to call Odoo Semantic tools

### Working with Python model files (models/*.py, *.py with `models.Model`)
- User asks about model structure / fields / methods / views in one go
  → call model_inspect(model=<name>, method="summary", odoo_version='<version>')
- User asks for a specific model's fields → call model_inspect(model=<name>, method="fields", odoo_version='<version>')
- User asks for a specific model's methods → call model_inspect(model=<name>, method="methods", odoo_version='<version>')
- User asks for a specific model's views → call model_inspect(model=<name>, method="views", odoo_version='<version>')
- User asks about ONE field → call entity_lookup(kind="field", model=<name>, field=<name>, odoo_version='<version>')
- User asks about ONE method → call entity_lookup(kind="method", model=<name>, method_name=<name>, odoo_version='<version>')
- User wants to add new behavior → call find_override_point(model=<name>, method=<name>, odoo_version='<version>')
- User wants code examples → call find_examples(natural_language_query, odoo_version='<version>')

### Working with XML view files (views/*.xml, *.xml with inherit_id)
- User asks about view structure → call entity_lookup(kind="view", xmlid=<id>, odoo_version='<version>')
- User wants every view for a model → call model_inspect(model=<name>, method="views", odoo_version='<version>')
- User wants to override a view → entity_lookup first, then suggest XPath from the chain

### Exploring module architecture
- User asks "what is module X" or "what does module X do"
  → call module_inspect(name=<name>, method="summary", odoo_version='<version>')
- User wants OWL components of a module → call module_inspect(name=<name>, method="owl", odoo_version='<version>')
- User wants QWeb templates of a module → call module_inspect(name=<name>, method="qweb", odoo_version='<version>')
- User wants JS patches of a module → call module_inspect(name=<name>, method="js", odoo_version='<version>')
- User wants views of a module → call module_inspect(name=<name>, method="views", odoo_version='<version>')

### Working with CSS/SCSS/LESS stylesheets
- User wants to know what stylesheets a module ships (CSS, SCSS, or LESS — LESS covers legacy v8-v11)
  → call resolve_stylesheet(module=<name>, odoo_version='<version>')
- User asks where a CSS selector or SCSS/LESS variable is defined or overridden
  → call find_style_override(selector_or_variable=<selector_or_var>, odoo_version='<version>')
- User wants to trace @import chains or find branding/theme overrides
  → call find_style_override(selector_or_variable=<var>, odoo_version='<version>')

### Validating ORM constructs before writing them (catch hallucinated fields/operators)
- Before pasting a search domain → call validate_domain(model=<name>, domain="<literal>", odoo_version='<version>')
  (operator validity is version-aware: `any`/`not any` v17+, `parent_of` v9+)
- Before trusting a compute method's @api.depends → call validate_depends(model=<name>, method=<_compute_x>, odoo_version='<version>')
- Before writing a multi-hop related= or domain path → call resolve_orm_chain(model=<name>, dotted_path="a.b.c", odoo_version='<version>')
- Before writing a related= that hops a relation → call validate_relation(model=<name>, field=<rel_field>, target_model=<expected_comodel>, odoo_version='<version>')

### Before writing any new code
- Check for existing patterns → call suggest_pattern(intent=<description>, odoo_version='<version>')
- Check module availability → call check_module_exists(name=<module>, odoo_version='<version>')

### Before using any Odoo core API
- Verify API status → call lookup_core_api(name=<symbol>, odoo_version='<version>')
- If writing upgrade code → call api_version_diff(symbol=<name>, from_version=<v>, to_version=<v>)

### Code review / pre-commit
- Scan for deprecated usage → call find_deprecated_usage(odoo_version)
- Check coding standards → call lint_check(code=<snippet>, odoo_version='<version>')
  (inline `# noqa: RULE_ID` in the code suppresses findings on that line)

### Risk assessment before major changes
- Impact of field change → call impact_analysis(entity_type="field", entity_name="model.field_name", odoo_version='<version>')
- Impact of method change → call impact_analysis(entity_type="method", entity_name="model.method_name", odoo_version='<version>')

## MCP Resources (read-only, bookmark-stable)
- odoo://{version}/model/{name}             # = model_inspect(method='summary', odoo_version='<version>') equivalent
- odoo://{version}/field/{model}/{field}    # = entity_lookup(kind='field', odoo_version='<version>')
- odoo://{version}/method/{model}/{method}  # = entity_lookup(kind='method', odoo_version='<version>')
- odoo://{version}/module/{name}            # = module_inspect(method='summary', odoo_version='<version>')
- odoo://{version}/view/{xmlid}             # = entity_lookup(kind='view', odoo_version='<version>')
- odoo://{version}/pattern/{name}           # canonical pattern catalogue entry
- odoo://{version}/stylesheet/{module}/{file_path*}   # CSS/SCSS/LESS record

Use Resources when you already know the entity ID — no tool call overhead.

## Example: superset tools replace the old multi-call pattern

# Efficient (one call after set_active_version):
#   set_active_version("17.0")          # once per session
#   model_inspect(model="sale.order", method="summary", odoo_version='<version>')   # full model overview
#   model_inspect(model="sale.order", method="fields", odoo_version='<version>')    # just fields
#   module_inspect(name="sale_management", method="js", odoo_version='<version>') # JS patches in module

## Auto-trigger on file open
When a Python file with `class .*(models\.Model)` is opened:
- Silently resolve the model to pre-cache its structure
- Surface inheritance chain in a comment if the user asks "what is this model?"

## Odoo version detection
- Check pyproject.toml, setup.cfg, or __manifest__.py for version hints
- Default to "17.0" if version not found in project
- Always pass detected version to MCP tool calls

## Response formatting
- Inheritance chains: use ├─ └─ tree notation
- Field info: type, required, compute/related, string label
- Method info: full override chain with module names
- Risk levels: always bold HIGH, MEDIUM, LOW
- Module names: always in `backticks`

## Developer workflow
1. Open model file → model_inspect(method="summary", odoo_version='<version>') to understand inheritance
2. Find extension point → find_override_point before writing override
3. Check pattern → suggest_pattern for the implementation approach
4. Verify API → lookup_core_api for any core methods used
5. After writing → lint_check to verify standards
6. Before PR → find_deprecated_usage + impact_analysis for risky changes
```

---

## Global Rules (Cursor Settings → Rules for AI)

For workspace-agnostic use, paste this shorter version into **Cursor → Settings → Rules for AI**:

```
When working with Odoo Python or XML files, use the odoo-semantic MCP tools (v0.13.1 tool surface):

Session bootstrap (once per chat):
- list_available_versions() / list_available_profiles()
- set_active_version("17.0") / set_active_profile("<name>")
Pass the concrete version on every call - the pin is per-API-key server state (24h idle TTL) and racy under concurrency.

Superset tools (use these for all model/module/entity queries):
- Model questions (structure / fields / methods / views) → model_inspect(model=<name>, method="summary"|"fields"|"methods"|"views", odoo_version='<version>')
- One specific field / method / view → entity_lookup(kind="field"|"method"|"view", ...)
- Module-level (describe / OWL / QWeb / JS patches / views) → module_inspect(name=<name>, method="summary"|"owl"|"qweb"|"js"|"views", odoo_version='<version>')
  NOTE: use method="js" for JS patches

Targeted tools:
- "Where to add X" → find_override_point
- "Best practice for X" → suggest_pattern
- "Does Odoo have X" → check_module_exists
- "Is [API] deprecated" → lookup_core_api
- "What changed in upgrade" → api_version_diff
- "What breaks if I change X" → impact_analysis
- "Lint this module" → lint_check (inline # noqa: RULE_ID suppresses findings on that line)
- "Deprecated APIs in my code" → find_deprecated_usage
- "Show me code for" → find_examples
- "What stylesheets does module X ship" → resolve_stylesheet
- "Where is selector / SCSS variable X defined or overridden" → find_style_override
- "Is this domain / are these operators valid" → validate_domain
- "Are this compute method's @api.depends correct" → validate_depends
- "What type does dotted path a.b.c resolve to" → resolve_orm_chain
- "Does field X point to model Y" → validate_relation

MCP Resources (read-only handles): odoo://{version}/<model|field|method|view|module|pattern|stylesheet>/...

Always call the tool before answering codebase-specific questions.
Default Odoo version: 17.0 (detect from project manifest if available, else use set_active_version).
```

---

## Example `.cursorrules` (Minimal)

For a project already configured for Odoo 17.0 development:

```
# .cursorrules — Odoo 17.0 project

## MCP tools (use odoo-semantic for all Odoo questions)

When user asks about Odoo models, fields, methods, views, or patterns:
- ALWAYS call the relevant odoo-semantic MCP tool first
- Default version: 17.0
- Never fabricate module names, field types, or method signatures
- After getting tool results, summarize clearly with tree notation for chains

## Key mappings (v0.8)
- Session start → list_available_versions + set_active_version("17.0")
- "how does X work" → entity_lookup(kind="method", odoo_version='<version>') or model_inspect(method="summary", odoo_version='<version>')
- "where to override" → find_override_point
- "add functionality to" → find_override_point + suggest_pattern
- "impact of changing" → impact_analysis
- "deprecated / upgrade" → find_deprecated_usage + api_version_diff
- "show me code for" → find_examples
- "does Odoo have" → check_module_exists
- "what is module X" → module_inspect(method="summary", odoo_version='<version>')
- "list fields / methods / views of X" → model_inspect(method="fields"|"methods"|"views", odoo_version='<version>')
- "OWL / QWeb / JS patches in X" → module_inspect(method="owl"|"qweb"|"js", odoo_version='<version>')
- "stylesheets in module X" → resolve_stylesheet(module=X, odoo_version='<version>')
- "where is selector/variable X defined" → find_style_override(selector_or_variable=X, odoo_version='<version>')
- "is this domain / these operators valid" → validate_domain(model=X, domain="...")
- "are the @api.depends on _compute_x correct" → validate_depends(model=X, method="_compute_x", odoo_version='<version>')
- "what type is path a.b.c" → resolve_orm_chain(model=X, dotted_path="a.b.c", odoo_version='<version>')
- "does field X point to model Y" → validate_relation(model=X, field="X", target_model="Y", odoo_version='<version>')
```

---

## Verify Setup

In Cursor chat, type:
```
Using odoo-semantic, what is the inheritance chain of sale.order in Odoo 17.0?
```

**Expected:** Structured tree output with module names from the index.
**If Cursor answers from training data:** Check that the MCP server is configured in Cursor settings under `mcp.json`.

### Add MCP server to Cursor

In `~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "odoo-semantic": {
      "type": "http",
      "url": "https://odoo-semantic.viindoo.com/mcp",
      "headers": {
        "X-API-Key": "<YOUR_API_KEY>"
      }
    }
  }
}
```

---

## Generated Tool Surface

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. Generated from `generator/server-surface.json`. Run `make gen` to update._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

## Key mappings (generated)
- "inspect model" → `model_inspect ★` — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- "inspect module" → `module_inspect ★` — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- "lookup field" → `entity_lookup ★` — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- "which repos make up profile" → `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- "show me examples" → `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- "what breaks if I change" → `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- "is API deprecated" → `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- "what changed between versions" → `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- "deprecated API in code" → `find_deprecated_usage` — Scan the indexed codebase for usages of deprecated API patterns.
- "lint check" → `lint_check` — Validate code against Odoo-specific lint rules (Python/JavaScript), or return corpus-level XML RelaxNG violation nodes (language='xml', server v0.9.1+).
- "odoo-bin options" → `cli_help` — Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- "best pattern for" → `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- "does module exist" → `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- "where to override" → `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- "what does module do" → `describe_module` — Module manifest + defined/extended model counts + view/JS inventory in one call.
- "set version" → `set_active_version ☆` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- "set profile" → `set_active_profile ☆` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- "what versions are indexed" → `list_available_versions ☆` — Enumerate which Odoo versions the server has indexed.
- "what profiles exist" → `list_available_profiles ☆` — Enumerate which tenant profiles exist in the server index.
- "stylesheets in module" → `resolve_stylesheet ✦` — Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- "where is CSS selector defined" → `find_style_override ✦` — Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- "trace field path" → `resolve_orm_chain ⊕` — Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- "is this domain valid" → `validate_domain ⊕` — Validate search domain terms: field-path resolution and operator version-awareness.
- "validate compute depends" → `validate_depends ⊕` — Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- "does field point to model" → `validate_relation ⊕` — Assert a relational field points at the expected comodel (many2one/one2many/many2many).
<!-- END GENERATED TOOLS -->
