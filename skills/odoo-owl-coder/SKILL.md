---
name: odoo-owl-coder
description: >
  Write complete, production-ready OWL (Owl Web Library) component code for Odoo v15+ —
  fully assembled with `/** @odoo-module **/` header, correct `patch()` syntax for the
  target OWL era, registry registration, separate template XML when appropriate, and
  `__manifest__.py` assets entry. Use this skill ANY time the user needs Odoo frontend JS
  for v15 or newer — even when they describe it in plain language without saying "OWL".
  Pushy trigger: fire on "tạo OWL component", "viết patch() cho Odoo 15/16/17/18/19",
  "client action OWL", "useService useState useRef", "t-component t-if", "field widget
  customization in Odoo 17", "patch the sale order form", "custom button on form view",
  "Odoo v17 frontend JS", "JavaScript Odoo v15 v16 v17 v18 v19", "viết giao diện Odoo
  modern", "register a new field widget", "tôi muốn thêm nút trên form sale order trong
  Odoo 17", "show partner avatar inside Many2one widget", "patch FormController", "extend
  ListController", "create dashboard view for sale.order stats", "OWL 2.x lifecycle hook
  example", "use registry.category to register…", "client action that fetches data via
  useService('orm')", "Odoo 17 reaction to state change in component". When the user is
  asking about Odoo v8–v14 JavaScript (`odoo.define()`, `Widget`, `AbstractField`,
  `FieldChar`), redirect to **odoo-js-coder** because OWL didn't exist before v15. When
  they ask about backend Python/XML rather than frontend, route to odoo-coder.
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

OWL (Odoo Web Library) replaced the legacy widget system starting in Odoo 15. The key failure
modes when writing OWL code are:

- **Wrong patch() syntax** — OWL 1.x (v15) uses `patch(SomeClass.prototype, 'name', {...})`;
  OWL 2.x (v16+) drops the prototype and name arguments: `patch(SomeClass, {...})`. Mixing
  these causes silent breakage or runtime errors.
- **Wrong import paths** — lifecycle hooks (`onMounted`, `onWillStart`, `onWillUnmount`) moved
  from `@web/core/utils/hooks` to `@odoo/owl` in v16. Always verify via `find_examples` on the
  target version — training knowledge can be stale.
- **Missing `/** @odoo-module **/`** — required as the very first line of every ES module file
  for v16 and v17. In v18+ it's optional but harmless to include.
- **`odoo.define()` still used** — the old AMD system is gone from v16+. Every new file must
  use ES `import`/`export`.
- **Asset bundle format** — v15 registers JS and XML separately under `web.assets_backend`;
  v16+ can use `import` within JS for templates (inline `xml` tagged literal), but a separate
  XML file under the same bundle is still the most readable pattern.
- **Registry category names** — `fields`, `actions`, `views`, `services` are stable across
  v15–v19. `component` is not a standard category; always use the correct one for the use case.

### Data priority

`find_examples` querying your indexed Odoo repos shows real import paths and hook names as they
appear in the codebase. Prefer that evidence over training memory when there is any doubt about
syntax, especially for lifecycle hooks and registry APIs.

### Version gate

If the user asks about Odoo v8–v14 JavaScript (`.js` files with `odoo.define(…)`, `Widget`,
`AbstractField`, `FieldChar`), redirect them to the **odoo-js-coder** skill instead — OWL did
not exist in those versions.

---

## Instructions

Work in four steps. Fire parallel MCP calls within the same step when the calls are independent.

### Step 1 — Detect OWL version

Infer the Odoo version from user context (stated version, repo name, config file, imports seen
in existing code). Map it:

| Odoo version | OWL era | patch() form | Lifecycle hooks source |
|---|---|---|---|
| v15 | OWL 1.x | `patch(Class.prototype, 'mod.name', {…})` | `@odoo/owl` |
| v16–v19+ | OWL 2.x | `patch(Class, {…})` | `@odoo/owl` |

If the user is porting code from one version to another, call `api_version_diff` to surface
breaking changes between the two versions before generating anything.

When the version is ambiguous, default to **v17** (OWL 2.x) and state the assumption.

### Step 2 — Discover existing components/templates + gather examples (parallel)

Before writing any code, discover what already exists in the target module to avoid naming
collisions or duplicating a component that's already there. Run all of the following
simultaneously — they are all independent:

1. `module_inspect(module=<module>, method='owl')` — enumerates OWL components defined in the
   module (v15+ only; returns empty with a warning for v8–v13). Use this to check whether the
   component you intend to write or patch already exists under a slightly different name.
2. `module_inspect(module=<module>, method='qweb')` — enumerates QWeb template IDs registered
   in the module. Use this to verify the exact template name before writing an XPath override
   and to avoid duplicate `t-name` definitions.
3. `find_examples(query="OWL component <feature> Odoo v<N>")` — finds real code using the same
   hook, registry, or patch pattern from the indexed codebase. Trust this output for import
   paths.
4. `find_override_point(component, hook)` — only when patching or extending an existing Odoo
   component (e.g. `SaleOrderForm`, `FormController`, a field widget). Skip when creating a
   brand-new component from scratch.

If you need authoritative hook or registry API details that `find_examples` does not cover, also
call `lookup_core_api` in this step.

### Step 3 — Generate component boilerplate

Pass the gathered examples and API details as context:

```
mcp__ollama-delegate__generate_code(
    task="OWL <1.x|2.x> component: <precise description of the component, hooks needed, and data sources>",
    context="<paste the most relevant example snippets + registry category + import paths confirmed in Step 2>"
)
```

Prefer `generate_code` over writing raw boilerplate yourself for:
- New Component class with `setup()`, lifecycle hooks, and template
- `patch()` block with one or two method overrides
- `registry.category('…').add(…)` registration line

Write the logic yourself (without delegating) when:
- The logic crosses multiple OWL components via `useChildSubEnv` / `useBus`
- Custom service with state that must survive component unmount
- The patch must call `this._super(…)` at a specific position relative to side effects (v15
  only — OWL 2.x uses `super` in classes)

### Step 4 — Assemble complete output

Combine the generated boilerplate with:

1. **JS file** — `/** @odoo-module **/` first line (v16–v17), then `import` statements from
   verified paths, then the component class, then the registry `.add()` call.
2. **XML template file** — unless the component uses the inline `xml` tagged literal. A
   separate file is clearer for templates over ~10 lines.
3. **`__manifest__.py` assets block** — list both the `.js` and `.xml` paths under
   `web.assets_backend`.
4. **OWL version notes** — briefly note any 1.x→2.x differences relevant to the code so the
   user knows what to change if they ever port the module.

---

## Output format

```
## OWL Component: `<ComponentName>` (Odoo v<N>, OWL <1.x|2.x>)

### File: `<module>/static/src/js/<component_name>.js`
```javascript
/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
// ... rest of imports

class <ComponentName> extends Component {
    setup() {
        // hooks and services here
    }
}

<ComponentName>.template = "<module>.<ComponentName>";

registry.category("<category>").add("<key>", <ComponentName>);
```

### File: `<module>/static/src/xml/<component_name>.xml` (if separate template)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="<module>.<ComponentName>">
        <!-- complete OWL template with t-if, t-foreach, t-on-click, etc. -->
    </t>
</templates>
```

### `__manifest__.py` registration
```python
'assets': {
    'web.assets_backend': [
        '<module>/static/src/js/<component_name>.js',
        '<module>/static/src/xml/<component_name>.xml',
    ],
},
```

### OWL version notes
<note any 1.x vs 2.x differences that affect this specific code>
```

---

## Examples

**Example 1 — new dashboard client action (Odoo 17, OWL 2.x):**

Prompt: "tạo OWL component hiển thị dashboard tổng quan đơn hàng trong Odoo 17"

- Step 1: v17 → OWL 2.x, `patch(Class, {…})`, import hooks from `@odoo/owl`.
- Step 2 (parallel): `find_examples("dashboard OWL component Odoo 17")` + (no override point —
  new component).
- Step 3: `generate_code(task="OWL 2.x dashboard component fetching sale.order stats via useService('orm') with useState + onWillStart", context="<examples from step 2>")`.
- Step 4: Output — JS with `/** @odoo-module **/`, imports, `SaleOrderDashboard` class with
  `setup()` calling `useService('orm')` and `useState`, template XML with KPI cards, action
  registration under `registry.category('actions')`, manifest assets entry.

**Example 2 — patch existing form controller (Odoo 16, OWL 2.x):**

Prompt: "patch the sale order form to add a custom button using OWL in Odoo 16"

- Step 1: v16 → OWL 2.x, direct class patch.
- Step 2 (parallel): `find_examples("patch FormController OWL Odoo 16")` + `find_override_point("SaleOrderForm", "actionConfirm")`.
- Step 3: `generate_code(task="OWL 2.x patch FormController adding confirmWithComment button method", context="<override point details + examples>")`.
- Step 4: Output — JS `patch(FormController, { confirmWithComment() {…} })`, XPath template
  override adding `<button>` next to existing save button, manifest assets entry. OWL version
  note: "In v15 this would be `patch(FormController.prototype, 'sale_custom.patch', {…})` — the
  prototype and name arguments were removed in v16."

**Example 3 — custom field widget (Odoo 17, OWL 2.x):**

Prompt: "customize the Many2one field widget on sale.order to show partner avatar"

- Step 1: v17 → OWL 2.x.
- Step 2 (parallel): `find_examples("Many2one field widget override OWL 17")` + `find_override_point("Many2OneField", "setup")`.
- Step 3: Direct Claude (logic extends existing field class with `setup()` calling `super.setup()` then adding computed avatar URL — position of super call matters).
- Step 4: Output — JS extending `Many2OneField`, template XPath override, `registry.category('fields').add('many2one_with_avatar', …)` with `supportedTypes` override, manifest entry.
