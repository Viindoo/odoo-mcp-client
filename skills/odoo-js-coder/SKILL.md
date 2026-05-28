---
name: odoo-js-coder
description: >
  Write complete JavaScript/QWeb code for the Odoo v8–v14 legacy widget system — full
  `odoo.define(…)` module, `web.Widget`/`AbstractField` subclasses or `.include()` patches,
  QWeb XML template, and the `__manifest__.py` registration block (`assets` dict for v10+,
  `qweb` list for v8/v9). Use this skill ANY time someone needs frontend JS for Odoo
  versions 8 through 14, even when they describe the behavior in plain language. Pushy
  trigger: fire on "tạo widget tùy chỉnh", "viết field widget cho Odoo 8/10/11/12/13/14",
  "override ListView controller", "tạo client action bằng web.Widget", "QWeb template",
  "AbstractField subclass for selection field", "customize a field in Odoo 10", "write a
  widget for Odoo 12", "odoo.define() pattern", "Widget.include({…})", "field_registry
  add", "deferred chain replace with Promise?", "RPC call this._rpc(model, method, args)",
  "JS action manager", "viết JS cho Odoo 8 đến 14", "giao diện Odoo cũ", "legacy widget",
  "QWeb2 template", "JavaScript Odoo không dùng OWL", "color picker widget cho field
  selection trong Odoo 12", "add total row at bottom of list view in v11", "dashboard
  client action with chart for Odoo 13". Trigger even when the user does NOT say "legacy"
  — if the target version is v8–v14 OR they mention `odoo.define()`/`require()`/`web.Widget`
  without saying OWL, this is the skill. When the user asks for v15+ JS, redirect to
  **odoo-owl-coder** because `web.Widget` was removed in v16.
---

## Persona
Developer

## MCP tools (odoo-semantic)

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.

**Ollama-delegate tools** (local model, cost-free):
- `mcp__ollama-delegate__explain_code`
- `mcp__ollama-delegate__generate_code`
<!-- END GENERATED TOOLS -->

## Context

Odoo's JavaScript stack went through three distinct eras with **incompatible patterns**. Using the
wrong pattern for the target version produces code that silently fails or conflicts with existing
widgets. Always confirm the exact Odoo version before writing a single line.

### Era map

| Version | Pattern | Key classes | RPC style | ES level |
|---------|---------|------------|-----------|----------|
| v8–v9 (OpenERP) | `openerp.define(…)` AMD | `web.Widget`, `web.View` | `this.rpc('/web/dataset/call_kw', {…})` raw JSON-RPC | ES5, `var`, `$.Deferred` |
| v10–v12 (transition) | `odoo.define(…)` | `AbstractField`, `field_registry`, `Widget.include({…})` | `this._rpc({model, method, args})` | ES5+, still `var`/function |
| v13–v14 (OWL intro) | `odoo.define(…)` + optional `patch()` | `web.Widget` still primary; OWL exists but not default | `this._rpc(…)` | ES6 allowed but not required; `patch()` utility v13+ |

v14 is the **crossover**: OWL is the recommended choice for *new* components, but `web.Widget` still
works. Use `legacyFieldWidget` bridge only when mixing both. In v15+, `web.Widget` is removed — the
user needs the `odoo-owl-coder` skill.

### Why indexed codebase data beats training knowledge

Internal hook names and registration APIs shift between minor releases. Results from
`find_examples` and `find_override_point` reflect the *actual* code indexed for the user's repo —
always prefer these over what you know from training when there is a conflict.

## Instructions

Work in five sequential rounds. Rounds 2 and 3 each contain parallel calls — fire them in the
same message to save round-trips.

### Round 0 — Pin version + discover existing JS patches (before writing anything)

`set_active_version(odoo_version=<version>)` once.

When patching or extending an existing widget, JS module, or client action, call
`module_inspect(module=…, method='js')` to see the patch chain that already exists. This
prevents writing a conflicting or duplicate patch. Two calling patterns:

- **By target file** (when you know what you're patching): pass the target file path as part
  of the query; the tool filters patches whose target matches.
- **By module** (when auditing all patches in a module):
  ```
  module_inspect(module="sale_management", method="js")
  ```

**Era awareness** — JS patches divide into eras:
- `era1` — v8–v13: `openerp.define(…)` / `odoo.define(…)` AMD modules, `Widget.include({…})`
- `era2` — v14–v16: hybrid era, `odoo.define(…)` still dominant but `patch()` utility introduced
- `era3` — v17+: ES module `import`/`export` with OWL `patch()` (redirect to odoo-owl-coder)

If the existing patch chain has 3+ entries, warn the user about conflict risk before generating
more patches. Skip this round entirely for brand-new widget creation (no existing target).

### Round 1 — Version check + real examples (parallel)

Determine the Odoo version from the user's message or ask if ambiguous. Then fire both calls
simultaneously:

- `api_version_diff(scope, from_version="8.0", to_version="<N>.0")` — surfaces breaking JS API
  changes the user's version introduced relative to the baseline (skip if version is 8 or 9).
- `find_examples(query="<user feature> widget pattern Odoo <N>")` — retrieves real code from the
  indexed codebase that uses the pattern closest to what the user wants.

These two calls are independent; launch them together.

### Round 2 — Find override point (only if patching an existing widget)

If the user wants to **extend or patch** an existing Odoo widget (rather than write a brand-new
one), call:

```
find_override_point(model_or_component="<WidgetClass>", method_or_hook="<method>")
```

This reveals the exact class and hook to inherit/patch, including any existing override chain.
The patch chain discovered in Round 0 feeds into this — if `module_inspect(method='js')`
already showed the override path, you may skip `find_override_point` and use that data directly.
Skip this round entirely for greenfield widget creation.

### Round 3 — Generate boilerplate via ollama-delegate

With version + examples + override point in hand, call:

```
mcp__ollama-delegate__generate_code(
    task="<concise JS task description> for Odoo v<N> using <pattern>",
    context="<paste the examples and API diff findings from rounds 1-2>"
)
```

The context parameter matters: the model will match the pattern to what was found, not hallucinate
an incompatible one.

### Round 4 — Assemble and deliver complete output

Combine the generated code with the scaffolding the user needs to actually wire it in:
- JS file (full `odoo.define()` module)
- QWeb XML template file
- `__manifest__.py` registration (assets dict for v10+; `qweb` list for v8/v9)
- For v14: note whether `ir.asset` records should be used instead of the assets dict

Use the output format below — no shortcuts, no "you can fill in the rest".

### Version gate

If the user asks for v15 or later, respond:

> "Odoo v15+ uses OWL exclusively — `web.Widget` is removed. This request needs the
> **odoo-owl-coder** skill. Want me to switch?"

Do not attempt to generate legacy-style code for v15+.

## Output format

```
## Widget: `<WidgetName>` (Odoo v<N>, <pattern>)

### File: `<module>/static/src/js/<widget_name>.js`
```javascript
odoo.define('<module>.<widget_name>', function (require) {
    'use strict';

    // complete, runnable widget code here
    // (not a skeleton — fill in all methods)
});
```

### File: `<module>/static/src/xml/<widget_name>.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <!-- complete QWeb template — include all t-att-*, t-if, event bindings -->
</templates>
```

### `__manifest__.py` registration
```python
# v10+ assets dict:
'assets': {
    'web.assets_backend': [
        '<module>/static/src/js/<widget_name>.js',
        '<module>/static/src/xml/<widget_name>.xml',
    ],
},
# v8/v9: use 'qweb' list key instead (no 'assets' dict).
```

### Version notes
<Anything version-specific: ES5 constraint, $.Deferred vs Promise, super() vs _super(),
 patch() availability, legacyFieldWidget bridge, ir.asset vs assets dict>
```

The output must be copy-pasteable. If there are imports that differ by version (e.g.,
`require('web.AbstractField')` vs `require('web.field_registry')`), show both with a comment
explaining which to use when.

## Examples

**Example 1:** "tạo field widget color picker cho field selection trong Odoo 12"

Round 1: `api_version_diff("8.0","12.0")` → confirms `AbstractField` API stable since v10.
Parallel: `find_examples("color picker widget AbstractField Odoo 12")` → real examples from index.
Round 3: `generate_code(task="AbstractField subclass ColorPickerWidget for selection field, Odoo 12", context=<findings>)`
Output: full JS subclassing `AbstractField` + jQuery color picker init in `start()` + QWeb
template + manifest entry under `web.assets_backend`.

**Example 2:** "override list view to add a total row at bottom in Odoo 11"

Round 1: `find_examples("ListController renderView total row Odoo 11")`
Round 2: `find_override_point("ListController", "renderView")` → exact class path + override chain.
Round 3: `generate_code(task="ListController.include patch to append total row, Odoo 11", context=<findings>)`
Output: `odoo.define` with `Widget.include({renderView: …})` pattern + QWeb partial template for
the row + manifest entry.

**Example 3:** "create a client action that shows a dashboard with a chart, Odoo 13"

Round 1: `api_version_diff("8.0","13.0")` to surface any action_registry changes.
Parallel: `find_examples("client action dashboard web.Widget Odoo 13")`
Round 3: `generate_code` for `AbstractAction` subclass wired into `action_registry`.
Note in output: v13 introduced OWL but `AbstractAction`/`web.Widget` still valid — OWL not
required for this use case.
