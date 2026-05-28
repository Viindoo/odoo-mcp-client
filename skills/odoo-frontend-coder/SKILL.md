---
name: odoo-frontend-coder
description: >
  Write complete, production-ready Odoo frontend JS code for ANY Odoo version (v8–v19) —
  legacy `web.Widget`/`AbstractField`/`odoo.define()` system for v8–v14, or OWL 2.x
  components with `patch()`/`useState`/`useService` for v15+. Internally gates to the
  correct framework based on the target version so callers never need to choose between
  legacy and OWL skills. Use this skill ANY time someone needs Odoo frontend JS,
  regardless of version. Pushy trigger (EN+VI): fire on "tạo widget tùy chỉnh",
  "viết field widget cho Odoo", "customize a field in Odoo", "color picker widget",
  "AbstractField subclass", "odoo.define() pattern", "Widget.include", "field_registry add",
  "QWeb template", "QWeb2 template", "giao diện Odoo cũ", "legacy widget",
  "JavaScript Odoo không dùng OWL", "add total row list view", "dashboard client action",
  "tạo OWL component", "viết patch() cho Odoo 15/16/17/18/19", "client action OWL",
  "useService useState useRef", "t-component t-if", "field widget customization Odoo 17",
  "patch the sale order form", "custom button on form view", "Odoo v17 frontend JS",
  "JavaScript Odoo v15 v16 v17 v18 v19", "viết giao diện Odoo modern",
  "register a new field widget", "thêm nút trên form sale order", "patch FormController",
  "extend ListController", "create dashboard view", "OWL lifecycle hook",
  "use registry.category", "client action that fetches data via useService",
  "viết JS cho Odoo 8 đến 14", "viết JS cho Odoo 15 đến 19", "override ListView controller",
  "tạo client action bằng web.Widget", "RPC call this._rpc", "JS action manager",
  "QWeb3 template OWL", "show partner avatar Many2one widget". Trigger even when the user
  does NOT say "legacy" or "OWL" — infer from the stated Odoo version or API keywords.
  When the user asks about backend Python/XML rather than frontend JS, route to odoo-coder.
  When they want a code review rather than code generation, route to odoo-code-reviewer
---

## Persona

Developer (Odoo frontend, all versions v8–v19)

## Out of Scope

- **Backend Python / XML** (models, views, wizards, security, ORM) → use `odoo-coder`
- **Code review / audit of existing frontend code** → use `odoo-code-reviewer`
- **Deprecation analysis or upgrade planning** → use `odoo-deprecation-audit` or `odoo-version-diff`

## Version gate

This skill covers both frontend eras. The workflow diverges at Round 1 based on the detected version:

| Odoo version | JS framework | Key patterns | Template engine |
|---|---|---|---|
| v8–v9 | AMD `openerp.define()` | `web.Widget`, `web.View`, `$.Deferred` | QWeb2 XML (`<templates>`) |
| v10–v12 | `odoo.define()` | `AbstractField`, `field_registry`, `Widget.include({})` | QWeb2 XML |
| v13–v14 | `odoo.define()` + optional `patch()` | `web.Widget` primary; OWL available but not default | QWeb2 XML |
| v15 | OWL 1.x + `/** @odoo-module **/` | `patch(Class.prototype, 'name', {})`, hooks from `@odoo/owl` | QWeb3 (OWL templates) |
| v16–v19 | OWL 2.x + ES modules | `patch(Class, {})`, `import`/`export`, no `odoo.define()` | QWeb3 inline or separate XML |

**Critical v14 note:** v14 is the crossover — `web.Widget` still works and is the safest choice for extensions. OWL is available for *new* components only. If the user is unsure, ask.

**Critical v16 note:** `web.Widget` and `odoo.define()` are fully removed in v16+.

## MCP tools

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

## Instructions

Work in four rounds. Within each round, fire independent MCP calls in the same message.

### Round 0 — Read context file + pin version

1. If `.odoo-ai/context.md` exists, read it to obtain `odoo_version` and `viindoo_profile`
   (Phase B forward-wiring — see Notes). Skip if missing; fall back to user-stated version.
2. Call `set_active_version(odoo_version=<version>)` once.
3. Apply the version gate table above: if version is **v8–v14**, follow the
   [Legacy v8–v14 workflow](#legacy-v8v14-workflow) below; if **v15+**, follow the
   [OWL v15+ workflow](#owl-v15-workflow).
4. If patching or extending an existing widget/component (not greenfield), call
   `module_inspect(module=<module>, method='js')` to see the existing patch chain
   and avoid duplicates. If the chain already has 3+ entries, warn the user before proceeding.

---

### Legacy v8–v14 workflow {#legacy-v8v14-workflow}

#### Round 1 — Version check + real examples (parallel)

Fire both calls simultaneously:

- `api_version_diff(scope, from_version="8.0", to_version="<N>.0")` — surfaces breaking JS API
  changes relative to v8 baseline (skip if version is 8 or 9).
- `find_examples(query="<user feature> widget pattern Odoo <N>")` — retrieves real indexed code
  using the closest matching pattern.

#### Round 2 — Find override point (only when patching an existing widget)

```
find_override_point(model="<WidgetClass>", method="<method>")
```

Reveals the exact class path and override chain. If `module_inspect` in Round 0 already
surfaced the override path, skip this call and use that data directly.
Skip entirely for greenfield widget creation.

#### Round 3 — Generate boilerplate

```
mcp__ollama-delegate__generate_code(
    task="<concise JS task description> for Odoo v<N> using <pattern: odoo.define / AbstractField / Widget.include>",
    context="<paste examples + API diff from rounds 1-2>"
)
```

#### Round 4 — Assemble complete output

Combine boilerplate with full scaffolding (see Output format below):
- JS file with full `odoo.define()` module
- QWeb2 XML template file
- `__manifest__.py` registration (`assets` dict for v10+; `qweb` list for v8/v9)
- For v14: note whether `ir.asset` records should be used instead of the assets dict

---

### OWL v15+ workflow {#owl-v15-workflow}

#### Round 1 — Detect OWL sub-version (parallel when porting)

Map the version to the OWL era:

| Odoo version | OWL era | `patch()` form | Lifecycle hooks source |
|---|---|---|---|
| v15 | OWL 1.x | `patch(Class.prototype, 'mod.name', {…})` | `@odoo/owl` |
| v16–v19 | OWL 2.x | `patch(Class, {…})` | `@odoo/owl` |

When the version is ambiguous, default to **v17 (OWL 2.x)** and state the assumption.

If porting between versions, call `api_version_diff` to surface breaking changes first.

#### Round 2 — Discover existing components + gather examples (parallel)

Run all of the following simultaneously — they are independent:

1. `module_inspect(module=<module>, method='owl')` — enumerates OWL components in the module;
   checks for naming collisions.
2. `module_inspect(module=<module>, method='qweb')` — enumerates QWeb template IDs; verifies
   exact template name before writing XPath overrides.
3. `find_examples(query="OWL component <feature> Odoo v<N>")` — real import paths and hook
   names from indexed codebase (trust this over training memory for syntax).
4. `find_override_point(component, hook)` — only when patching an existing Odoo component.
   Skip for brand-new components.

If authoritative hook/registry API details are still missing after step 3, also call
`lookup_core_api` in this round.

#### Round 3 — Generate component boilerplate

```
mcp__ollama-delegate__generate_code(
    task="OWL <1.x|2.x> component: <precise description, hooks needed, data sources>",
    context="<most relevant example snippets + registry category + verified import paths>"
)
```

Prefer `generate_code` for: new Component class with `setup()` + lifecycle hooks + template,
`patch()` block with method overrides, `registry.category('…').add(…)` registration.

Write logic directly (without delegating) when:
- Logic crosses multiple OWL components via `useChildSubEnv` / `useBus`
- Custom service with state surviving component unmount
- Patch must call `super` at a position-sensitive point relative to side effects

#### Round 4 — Assemble complete output

1. **JS file** — `/** @odoo-module **/` first line (v16–v17; optional but harmless in v18+),
   then `import` statements from verified paths, then component class, then registry `.add()`.
2. **XML template file** — separate file preferred for templates over ~10 lines.
3. **`__manifest__.py` assets block** — list both `.js` and `.xml` under `web.assets_backend`.
4. **OWL version notes** — briefly note any 1.x→2.x differences relevant to the generated code.

---

## Standalone-first fallback

When OSM (`odoo-semantic`) is unreachable or returns errors:

1. Ask the user to paste the relevant existing code (widget class, component, or manifest excerpt).
2. Ask the user to confirm the **exact Odoo version** (e.g., "12.0", "17.0").
3. Proceed with Rounds 3–4 using only the pasted code as context — skip MCP discovery calls.
4. Prefix output with: `⚠ OSM unreachable — generated from pasted code only. Verify import paths against your actual codebase.`

## Output format

**Legacy (v8–v14):**

```
## Widget: `<WidgetName>` (Odoo v<N>, <pattern>)

### File: `<module>/static/src/js/<widget_name>.js`
```javascript
odoo.define('<module>.<widget_name>', function (require) {
    'use strict';
    // complete, runnable widget code — not a skeleton
});
```

### File: `<module>/static/src/xml/<widget_name>.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <!-- complete QWeb2 template — include all t-att-*, t-if, event bindings -->
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
# v8/v9: use 'qweb' list key instead — no 'assets' dict.
```

### Version notes
<ES5 constraint, $.Deferred vs Promise, _super() vs super(), patch() availability, ir.asset vs assets dict>
```

**OWL v15+ :**

```
## OWL Component: `<ComponentName>` (Odoo v<N>, OWL <1.x|2.x>)

### File: `<module>/static/src/js/<component_name>.js`
```javascript
/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
// ... verified imports

class <ComponentName> extends Component {
    setup() { /* hooks and services */ }
}
<ComponentName>.template = "<module>.<ComponentName>";
registry.category("<category>").add("<key>", <ComponentName>);
```

### File: `<module>/static/src/xml/<component_name>.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="<module>.<ComponentName>">
        <!-- complete OWL template -->
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
<1.x vs 2.x differences affecting this specific code>
```

Output must be copy-pasteable. If imports differ by version, show both with a comment.

## Examples

**Example 1 — v12 legacy: color picker field widget**

Prompt: "tạo field widget color picker cho field selection trong Odoo 12"

- Round 0: read `.odoo-ai/context.md` → `odoo_version: 12.0`. Version gate → Legacy workflow.
  `set_active_version("12.0")`.
- Round 1 (parallel): `api_version_diff("8.0", "12.0")` → confirms `AbstractField` stable since v10.
  `find_examples("color picker widget AbstractField Odoo 12")` → real examples from index.
- Round 2: greenfield widget — skip `find_override_point`.
- Round 3: `generate_code(task="AbstractField subclass ColorPickerWidget for selection field, Odoo 12", context=<findings>)`.
- Round 4: Output — full JS subclassing `AbstractField` + jQuery color picker init in `start()` +
  QWeb2 XML template + manifest entry under `web.assets_backend`.

**Example 2 — v11 legacy: override list view to add total row**

Prompt: "override list view to add a total row at the bottom in Odoo 11"

- Round 0: `odoo_version: 11.0`. Version gate → Legacy. `set_active_version("11.0")`.
  `module_inspect(module=<module>, method='js')` → existing patch chain (check conflicts).
- Round 1: `find_examples("ListController renderView total row Odoo 11")`.
- Round 2: `find_override_point("ListController", "renderView")` → exact class path + chain.
- Round 3: `generate_code(task="ListController.include patch to append total row, Odoo 11", context=<findings>)`.
- Round 4: `odoo.define` with `Widget.include({renderView: …})` + QWeb2 partial for row + manifest.

**Example 3 — v17 OWL: dashboard client action**

Prompt: "tạo OWL component hiển thị dashboard tổng quan đơn hàng trong Odoo 17"

- Round 0: `odoo_version: 17.0`. Version gate → OWL. `set_active_version("17.0")`.
- Round 1: v17 → OWL 2.x, `patch(Class, {…})`, lifecycle hooks from `@odoo/owl`.
- Round 2 (parallel): `module_inspect(method='owl')` + `module_inspect(method='qweb')` +
  `find_examples("dashboard OWL component Odoo 17")`. No override point — new component.
- Round 3: `generate_code(task="OWL 2.x dashboard component fetching sale.order stats via useService('orm') with useState + onWillStart", context=<examples>)`.
- Round 4: Output — JS with `/** @odoo-module **/`, `SaleOrderDashboard` class with `setup()`,
  template XML with KPI cards, action registration under `registry.category('actions')`, manifest entry.

**Example 4 — v16 OWL: patch form controller to add custom button**

Prompt: "patch the sale order form to add a custom button using OWL in Odoo 16"

- Round 0: `odoo_version: 16.0`. Version gate → OWL 2.x.
- Round 2 (parallel): `find_examples("patch FormController OWL Odoo 16")` +
  `find_override_point("SaleOrderForm", "actionConfirm")`.
- Round 3: `generate_code(task="OWL 2.x patch FormController adding confirmWithComment button", context=<findings>)`.
- Round 4: JS `patch(FormController, { confirmWithComment() {…} })` + XPath template override +
  manifest. OWL version note: "In v15 use `patch(FormController.prototype, 'sale_custom.patch', {…})`
  — prototype and name arguments were removed in v16."

## Notes

- **`.odoo-ai/context.md` integration (Phase B forward-wiring):** If the project has been
  initialized with `odoo-onboard`, `.odoo-ai/context.md` contains `odoo_version`,
  `viindoo_profile`, and `custom_modules`. Round 0 reads this file first so the skill
  auto-selects the correct framework without asking the user for the version each time.
  If the file is absent, the skill asks the user to state the Odoo version.
- **Why indexed examples beat training memory:** Internal hook names and registration APIs
  shift between minor releases. `find_examples` and `find_override_point` reflect the actual
  indexed code for the user's repo — always prefer these over training knowledge when there is
  a conflict, especially for lifecycle hooks and import paths.
- **v14 crossover:** OWL is available in v14 but `web.Widget` is still the safe choice for
  extensions. Only use OWL in v14 for brand-new components where you do not need to extend an
  existing legacy widget.
