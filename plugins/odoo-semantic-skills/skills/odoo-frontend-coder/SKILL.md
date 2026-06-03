---
name: odoo-frontend-coder
description: >
  Write complete, production-ready Odoo frontend JS for ANY version (v8–v19) — auto-gates
  to legacy `web.Widget`/`AbstractField`/`odoo.define()` (v8–v14) or OWL 2.x
  `patch()`/`useState`/`useService` (v15+) so callers never choose between frameworks.
  Trigger on: "AbstractField subclass", "Widget.include / odoo.define()", "patch
  FormController / extend ListController", "OWL lifecycle hook / useService", "dashboard
  client action", "register field widget via registry.category", "QWeb template override".
  Also fires on Vietnamese requests: "viết widget OWL", "sửa giao diện form", "thêm field
  widget", "override JS", "viết / sửa SCSS theme đúng design-system Odoo".
  Infer framework from version or API keywords even without "legacy"/"OWL". After code
  generation, suggest verifying via odoo-ui-debug (runtime render errors), odoo-ui-reviewer
  (layout), or odoo-visual-regression (before/after diff) — do not auto-invoke (depth rule).
  Backend Python/XML → odoo-coder. Code review → odoo-code-reviewer
---

## Persona

Developer (Odoo frontend, all versions v8–v19)

## Out of Scope

- **Backend Python / XML** (models, views, wizards, security, ORM) → use `odoo-coder`
- **Code review / audit of existing frontend code** → use `odoo-code-reviewer`
- **Deprecation analysis or upgrade planning** → use `odoo-deprecation-audit` or `odoo-version-diff`
- **Verifying the rendered UI / debugging a runtime render error / image regression** → use `odoo-ui-reviewer` / `odoo-ui-debug` / `odoo-visual-regression`

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
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key); subsequent calls pass `odoo_version='auto'` to reuse it (it can no longer be omitted).

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

## Phase 0 — Scope preview (1-turn gate)

You are the **fix writer**: you write the override/component to the correct file and show a
**patch preview before applying**. Before writing, emit the following preview block and
**stop** for confirmation — this is a preview, not a write-block:

```
Proposed: <brief description of the component / view / asset to be created or modified>.
Files: <module>/static/src/js/<file>.js, <module>/static/src/xml/<file>.xml, __manifest__.py (assets)
OSM: backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

- **Proposed** — one sentence: what JS/OWL/XML artifact will be created or changed, and in which module (located via `module_inspect` / Read / Grep — you find the right file yourself).
- **Files** — the files you will write/edit, plus the `__manifest__.py` assets entry.
- **OSM** — set to `backed` when the OSM MCP server is reachable and its tools (`find_examples`, `module_inspect`, etc.) will be used in subsequent rounds; after confirmation you **write/apply** the code to those files. Set to `standalone` when OSM is unreachable and the skill will fall back to pasted code only (no file writes). OSM tools improve accuracy for all frontend work and are **required for any styling/theme work** to ground design tokens (see Design-system fidelity below); when OSM is unreachable, say so and lower confidence rather than inventing token names.
- Wait for the user to reply `yes` before proceeding to Round 0 below. On `yes`, write the files to their correct locations. If they reply `refine: …`, update the scope and re-emit the block. If they reply `cancel`, stop.

## Design-system fidelity (mandatory whenever you touch SCSS / theme / component styling)

Off-theme UI is generated when colors are hardcoded, or when surface tokens are chained into
Bootstrap `--bs-*` custom properties that the target Odoo version does not actually emit at
runtime. The classic failure is a "shim" custom property whose value references itself — a CSS
dependency cycle that resolves to the empty value (the fallback is never reached), flattening
every downstream surface/border/text/badge token. Build theme-correct from the first line:

**Pre-write grounding** — before emitting any SCSS or styled OWL:
1. Read `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (era-aware SSOT: build-rules +
   token-reality method, the `--bs-*` self-reference worked example, AND the OWL pitfall catalogue).
2. Resolve which design tokens the **target version** really emits — `resolve_stylesheet(<module>, odoo_version='auto')`
   + `find_style_override(<selector_or_variable>, odoo_version='auto')`, then confirm at runtime with
   `getComputedStyle(document.documentElement)`. Never assume a token (e.g. any `--bs-*`) exists
   across versions — re-derive per version; the token reality differs by Bootstrap/Odoo version.
3. Consult the project mockup / UI spec for intent (mockup-first).

**Output self-check (gate — do not emit code until every box is checked):**
- [ ] No hardcoded `hex` / `rgb()` / `rgba()` for themeable colors — reuse runtime design
      tokens; use `color-mix()` for tints/shades.
- [ ] No self-referential custom property (a CSS variable whose value references itself) — to
      backfill a missing variable, anchor it to a token the target version actually emits, with
      a literal fallback, never to itself.
- [ ] Every referenced token verified to resolve at runtime for the target version (read the
      computed value — do not trust that an edit "took").
- [ ] Output matches the mockup / Odoo design system; fix the token **foundation**, not
      per-component patches (right altitude).

## Instructions

Work in rounds (Round 0 -> 0.5 grounding -> framework rounds -> Round 6 verify). Within each round, fire independent MCP calls in the same message.

### Round 0 — Read context file + pin version

1. If `.odoo-ai/context.md` exists, read it to obtain `odoo_version` and `profile` (Phase B
   forward-wiring — see Notes). Skip if missing; fall back to user-stated version.
2. Call `set_active_version(odoo_version=<version>)` once.
3. Apply the version gate table above: if version is **v8–v14**, follow the
   [Legacy v8–v14 workflow](#legacy-v8v14-workflow) below; if **v15+**, follow the
   [OWL v15+ workflow](#owl-v15-workflow).
4. If patching or extending an existing widget/component (not greenfield), call
   `module_inspect(name=<module>, method='js', odoo_version='auto')` to see the existing patch chain
   and avoid duplicates. If the chain already has 3+ entries, warn the user before proceeding.

---

### Legacy v8–v14 workflow {#legacy-v8v14-workflow}

#### Round 1 — Version check + real examples (parallel)

Fire both calls simultaneously:

- `api_version_diff(symbol=<symbol>, from_version="8.0", to_version="<N>.0")` — surfaces breaking JS API
  changes relative to v8 baseline (skip if version is 8 or 9).
- `find_examples(query="<user feature> widget pattern Odoo <N>", odoo_version='auto')` — retrieves real indexed code
  using the closest matching pattern.

#### Round 2 — Find override point (only when patching an existing widget)

```
find_override_point(model="<WidgetClass>", method="<method>", odoo_version='auto')
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

#### Round 5 — Suggest visual verification (forward-wiring)

This code touches the DOM / QWeb render, so after presenting the output, suggest (TEXT only —
do NOT invoke any skill, to respect the depth rule) that the user verify the change on a live
instance:

- `odoo-ui-reviewer` — to check layout / spacing / responsive once the widget renders.
- `odoo-ui-debug` — if the widget does not appear or the console shows a runtime error.
- `odoo-visual-regression` — if this patches an existing view and they want a before/after diff.

These run via `/odoo-semantic-skills:setup` (browser MCP + instance URL). Mention them as an
optional next step; never auto-run them.

---

### OWL v15+ workflow {#owl-v15-workflow}

#### Round 0.5 — OWL pitfall grounding checklist (gate)

Before emitting any OWL/JS, assert each class in the catalogue at
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (section "OWL pitfall catalogue")
is satisfied for the target version. Do not duplicate the catalogue here - ground each item against it:

- [ ] **t-on handlers** - no bare free-identifier arrow call (`() => onFoo()`); use `() => this.onFoo()`, the auto-bound `t-on-click="onFoo"`, or `onChange.bind="onFoo"` for props (all valid).
- [ ] **useService reactivity** - a service that drives the template is reactivity-preserved per version (v16: wrap in `useState`; v17-18: canonical `useState(useService(...))`; v19: plain `useService` ok, the service is already `reactive()`).
- [ ] **No raw `contenteditable`** - delegate to `web_editor` Wysiwyg, lazy-loaded in `onWillStart`, with stable props built once.
- [ ] **SCSS in `calc()`** - interpolate Sass functions: `calc(#{map-get(...)} * 2)`, never bare `map-get(`/`min(` inside `calc(`.
- [ ] **No `--bs-*` assumptions** - Odoo sets `$variable-prefix:''`; reference `--primary`/`--o-color-*`, never a self-referential shim.
- [ ] **`Dialog` body** - body content goes in the default slot; only `header`/`footer` are named slots.

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

1. `module_inspect(name=<module>, method='owl', odoo_version='auto')` — enumerates OWL components in the module;
   checks for naming collisions.
2. `module_inspect(name=<module>, method='qweb', odoo_version='auto')` — enumerates QWeb template IDs; verifies
   exact template name before writing XPath overrides.
3. `find_examples(query="OWL component <feature> Odoo v<N>", odoo_version='auto')` — real import paths and hook
   names from indexed codebase (trust this over training memory for syntax).
4. `find_override_point(model=<Component>, method=<method>, odoo_version='auto')` — only when patching an existing Odoo component.
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

#### Round 5 — Suggest visual verification (forward-wiring)

This component touches OWL render, so after presenting the output, suggest (TEXT only — do NOT
invoke any skill, to respect the depth rule) that the user verify it on a live instance:

- `odoo-ui-reviewer` — to check layout / spacing / responsive once the component renders.
- `odoo-ui-debug` — if the component does not mount or the console shows a runtime error.
- `odoo-visual-regression` — if this patches an existing view and they want a before/after diff.

These run via `/odoo-semantic-skills:setup` (browser MCP + instance URL). Mention them as an
optional next step; never auto-run them.

---

### Round 6 — Post-write verify gate (both workflows)

Mirror the `odoo-coder` Round-4 self-verify discipline: do not declare the change done until the
static gate is green. Run the shared gate on the files you wrote:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/verify-frontend.sh <changed-files>
```

- Tier-2 static OWL/SCSS pitfall checks always run (no toolchain needed) - a BLOCK (classes 1/3/6)
  is a hard stop: fix and re-run. A WARN (classes 2/4/5) must be justified or fixed.
- Tier-1 format/lint runs `ruff check` (Python) and prettier (JS) when available, and **degrades
  gracefully** to a soft warning when the JS toolchain or config is absent - never a false hard-fail.
- If OSM is reachable, cross-check with `lint_check(language='javascript', odoo_version='<N>.0', code=...)`
  (note: `odoo_version` is a required argument for these tools).

---

## Standalone-first fallback

When OSM (the `odoo-semantic-mcp` server) is unreachable or returns errors:

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

When OSM is reachable, write these files to their correct locations (creating new files,
editing existing ones — append the assets entries to `__manifest__.py` rather than
overwriting) and report a patch-preview summary of what you wrote. In the Standalone-first
fallback, emit the same blocks as copy-pasteable code for the user to place manually. If
imports differ by version, show both with a comment.

## Examples

**Example 1 — v12 legacy: color picker field widget**

Prompt: "Create a color picker field widget for selection field in Odoo 12"

- Round 0: read `.odoo-ai/context.md` → `odoo_version: 12.0`. Version gate → Legacy workflow.
  `set_active_version("12.0")`.
- Round 1 (parallel): `api_version_diff("8.0", "12.0")` → confirms `AbstractField` stable since v10.
  `find_examples("color picker widget AbstractField Odoo 12", odoo_version='auto')` → real examples from index.
- Round 2: greenfield widget — skip `find_override_point`.
- Round 3: `generate_code(task="AbstractField subclass ColorPickerWidget for selection field, Odoo 12", context=<findings>)`.
- Round 4: Output — full JS subclassing `AbstractField` + jQuery color picker init in `start()` +
  QWeb2 XML template + manifest entry under `web.assets_backend`.

**Example 2 — v11 legacy: override list view to add total row**

Prompt: "override list view to add a total row at the bottom in Odoo 11"

- Round 0: `odoo_version: 11.0`. Version gate → Legacy. `set_active_version("11.0")`.
  `module_inspect(name=<module>, method='js', odoo_version='auto')` → existing patch chain (check conflicts).
- Round 1: `find_examples("ListController renderView total row Odoo 11", odoo_version='auto')`.
- Round 2: `find_override_point("ListController", "renderView", odoo_version='auto')` → exact class path + chain.
- Round 3: `generate_code(task="ListController.include patch to append total row, Odoo 11", context=<findings>)`.
- Round 4: `odoo.define` with `Widget.include({renderView: …})` + QWeb2 partial for row + manifest.

**Example 3 — v17 OWL: dashboard client action**

Prompt: "Create an OWL component to display a sales order summary dashboard in Odoo 17"

- Round 0: `odoo_version: 17.0`. Version gate → OWL. `set_active_version("17.0")`.
- Round 1: v17 → OWL 2.x, `patch(Class, {…})`, lifecycle hooks from `@odoo/owl`.
- Round 2 (parallel): `module_inspect(method='owl', odoo_version='auto')` + `module_inspect(method='qweb', odoo_version='auto')` +
  `find_examples("dashboard OWL component Odoo 17", odoo_version='auto')`. No override point — new component.
- Round 3: `generate_code(task="OWL 2.x dashboard component fetching sale.order stats via useService('orm') with useState + onWillStart", context=<examples>)`.
- Round 4: Output — JS with `/** @odoo-module **/`, `SaleOrderDashboard` class with `setup()`,
  template XML with KPI cards, action registration under `registry.category('actions')`, manifest entry.

**Example 4 — v16 OWL: patch form controller to add custom button**

Prompt: "patch the sale order form to add a custom button using OWL in Odoo 16"

- Round 0: `odoo_version: 16.0`. Version gate → OWL 2.x.
- Round 2 (parallel): `find_examples("patch FormController OWL Odoo 16", odoo_version='auto')` +
  `find_override_point("SaleOrderForm", "actionConfirm", odoo_version='auto')`.
- Round 3: `generate_code(task="OWL 2.x patch FormController adding confirmWithComment button", context=<findings>)`.
- Round 4: JS `patch(FormController, { confirmWithComment() {…} })` + XPath template override +
  manifest. OWL version note: "In v15 use `patch(FormController.prototype, 'sale_custom.patch', {…})`
  — prototype and name arguments were removed in v16."

## Notes

- **`.odoo-ai/context.md` integration (Phase B forward-wiring):** If the project has been
  initialized with `odoo-onboard`, `.odoo-ai/context.md` contains `odoo_version`, `profile`,
  and `custom_modules`. Round 0 reads this file first so the skill auto-selects the correct
  framework without asking the user for the version each time. If the file is absent, the skill
  asks the user to state the Odoo version.
- **Why indexed examples beat training memory:** Internal hook names and registration APIs
  shift between minor releases. `find_examples` and `find_override_point` reflect the actual
  indexed code for the user's repo — always prefer these over training knowledge when there is
  a conflict, especially for lifecycle hooks and import paths.
- **v14 crossover:** OWL is available in v14 but `web.Widget` is still the safe choice for
  extensions. Only use OWL in v14 for brand-new components where you do not need to extend an
  existing legacy widget.
