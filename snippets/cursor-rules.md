# Odoo Semantic — Cursor Rules

## Overview

These rules configure Cursor IDE to automatically route Odoo-related questions through the Odoo Semantic MCP server. Add them to `.cursorrules` in your project root, or paste into **Cursor Settings → Rules for AI** (applies globally).

---

## Add to `.cursorrules`

```
# Odoo Semantic MCP — Developer Rules (v0.6 — 18-tool surface)
# Auto-triggers for Odoo codebase intelligence via MCP

## Session bootstrap (run once per chat session)
- At session start, call list_available_versions() to discover indexed versions
- Pin the version with set_active_version("17.0") — TTL 24h per API key
- Subsequent tool calls can omit odoo_version (falls back to the pinned value)
- Pin tenant with set_active_profile("<name>") if multi-tenant MCP

## When to call Odoo Semantic tools

### Working with Python model files (models/*.py, *.py with `models.Model`)
- User asks about model structure / fields / methods / views in one go
  → call model_inspect(model=<name>, method="summary")
- User asks for a specific model's fields → call model_inspect(model=<name>, method="fields")
- User asks for a specific model's methods → call model_inspect(model=<name>, method="methods")
- User asks for a specific model's views → call model_inspect(model=<name>, method="views")
- User asks about ONE field → call entity_lookup(kind="field", model=<name>, field=<name>)
- User asks about ONE method → call entity_lookup(kind="method", model=<name>, method_name=<name>)
- User wants to add new behavior → call find_override_point(model_name, method_name)
- User wants code examples → call find_examples(natural_language_query)

### Working with XML view files (views/*.xml, *.xml with inherit_id)
- User asks about view structure → call entity_lookup(kind="view", xmlid=<id>)
- User wants every view for a model → call model_inspect(model=<name>, method="views")
- User wants to override a view → entity_lookup first, then suggest XPath from the chain

### Exploring module architecture
- User asks "what is module X" or "what does module X do"
  → call module_inspect(module=<name>, method="summary")
- User wants OWL components of a module → call module_inspect(module=<name>, method="owl")
- User wants QWeb templates of a module → call module_inspect(module=<name>, method="qweb")
- User wants JS patches of a module → call module_inspect(module=<name>, method="js")
- User wants views of a module → call module_inspect(module=<name>, method="views")

### Before writing any new code
- Check for existing patterns → call suggest_pattern(description)
- Check module availability → call check_module_exists(module_name)

### Before using any Odoo core API
- Verify API status → call lookup_core_api(symbol_name)
- If writing upgrade code → call api_version_diff(symbol_name, from_version, to_version)

### Code review / pre-commit
- Scan for deprecated usage → call find_deprecated_usage(odoo_version)
- Check coding standards → call lint_check(code_chunk)

### Risk assessment before major changes
- Impact of field change → call impact_analysis(entity_type="field", entity_name="model.field_name")
- Impact of method change → call impact_analysis(entity_type="method", entity_name="model.method_name")

## MCP Resources (read-only, bookmark-stable)
- odoo://{version}/model/{name}             # = model_inspect(method='summary') equivalent
- odoo://{version}/field/{model}/{field}    # = entity_lookup(kind='field')
- odoo://{version}/method/{model}/{method}  # = entity_lookup(kind='method')
- odoo://{version}/module/{name}            # = module_inspect(method='summary')
- odoo://{version}/view/{xmlid}             # = entity_lookup(kind='view')
- odoo://{version}/pattern/{name}           # canonical pattern catalogue entry
- odoo://{version}/stylesheet/{file_path}   # CSS/SCSS record

Use Resources when you already know the entity ID — no tool call overhead.

## Example: superset tools replace the old multi-call pattern

# Efficient (one call after set_active_version):
#   set_active_version("17.0")          # once per session
#   model_inspect(model="sale.order", method="summary")   # full model overview
#   model_inspect(model="sale.order", method="fields")    # just fields
#   module_inspect(module="sale_management", method="js") # JS patches in module

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
1. Open model file → model_inspect(method="summary") to understand inheritance
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
When working with Odoo Python or XML files, use the odoo-semantic MCP tools (v0.6, 18-tool surface):

Session bootstrap (once per chat):
- list_available_versions() / list_available_profiles()
- set_active_version("17.0") / set_active_profile("<name>")
Subsequent calls can omit odoo_version (sticky 24h TTL per API key).

Superset tools (use these for all model/module/entity queries):
- Model questions (structure / fields / methods / views) → model_inspect(model=<name>, method="summary"|"fields"|"methods"|"views")
- One specific field / method / view → entity_lookup(kind="field"|"method"|"view", ...)
- Module-level (describe / OWL / QWeb / JS patches / views) → module_inspect(module=<name>, method="summary"|"owl"|"qweb"|"js"|"views")
  NOTE: use method="js" for JS patches

Targeted tools:
- "Where to add X" → find_override_point
- "Best practice for X" → suggest_pattern
- "Does Odoo have X" → check_module_exists
- "Is [API] deprecated" → lookup_core_api
- "What changed in upgrade" → api_version_diff
- "What breaks if I change X" → impact_analysis
- "Lint this module" → lint_check
- "Deprecated APIs in my code" → find_deprecated_usage
- "Show me code for" → find_examples

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

## Key mappings (v0.6 — 18 tools)
- Session start → list_available_versions + set_active_version("17.0")
- "how does X work" → entity_lookup(kind="method") or model_inspect(method="summary")
- "where to override" → find_override_point
- "add functionality to" → find_override_point + suggest_pattern
- "impact of changing" → impact_analysis
- "deprecated / upgrade" → find_deprecated_usage + api_version_diff
- "show me code for" → find_examples
- "does Odoo have" → check_module_exists
- "what is module X" → module_inspect(method="summary")
- "list fields / methods / views of X" → model_inspect(method="fields"|"methods"|"views")
- "OWL / QWeb / JS patches in X" → module_inspect(method="owl"|"qweb"|"js")
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
