# Odoo Frontend Fidelity - era-aware OWL/JS/SCSS ground truth (SSOT)

> **Ground truth = OSM + the running instance, not memory.** The rules below are stable; any
> concrete *token name*, *signature* or *bundle path* is version-specific - confirm it for the
> target version before relying on it.

---

## Era 3 - OWL 2 / ES modules (v16 onward) - FULL

Module system is native `import` / `export` (the `/** @odoo-module */` pragma still accepted);
components are OWL 2 (2.8.x) imported from `@odoo/owl`. Resolve the exact OWL minor and any
token/signature via OSM per target version.

### Baseline (v16 onward, identical unless a sub-row says otherwise)

> For a target newer than the last sub-row, verify the OWL minor, `patch()` arity and service
> reactivity for that version via OSM before relying on these defaults.

- **Imports:** `import { Component, useState, useService, onWillStart } from "@odoo/owl";`
  (registry, hooks and core utilities from their own modules, e.g.
  `import { registry } from "@web/core/registry";`). Never the global `owl.*` namespace (Era 2).
- **Component shape:** `class Foo extends Component { static template = "addon.Foo"; static props = {...}; setup() {...} }`. State via `useState({...})`; services via `useService("name")`.
- **Registry:** extend via `registry.category("...").add("key", value)` - fields, views,
  actions, services, systray, etc.
- **Templates:** QWeb in a separate `.xml` asset; `t-on-<event>="handler"` and
  `t-att`/`t-attf` bindings. Event handlers may be a method name (`t-on-click="onClick"`,
  auto-bound to the component) or an arrow (`t-on-click="() => this.onClick(ev)"`).

### Sub-row - v16

- **`useService` reactivity:** wrapping a non-reactive service in `useState(...)` is required at
  v16 to make its values reactive in templates (e.g. `this.ui = useState(useService("ui"))`).
- **`patch()`:** the 3-argument form `patch(target, "patchName", overrides)` is still accepted.

### Sub-row - v17+ (hard break)

- **`patch()` is 2-argument and throws on the old 3-arg form.** Use
  `patch(Target.prototype, { method() { ... super.method(...) ... } })`; the patch-name
  argument was removed and passing it raises (`web/.../core/utils/patch.js` enforces this at v17).
- **`useService` reactivity:** `useState(useService("..."))` remains the canonical idiom at
  v17/v18 for non-reactive services.

### Sub-row - v18+ (hard break)

- **`Dialog` declares props as static class fields**: `static props = {...}` /
  `static defaultProps = {...}` on the class (`web/.../core/dialog/dialog.js:34`, `:59`), never an
  external props descriptor object. v18 and v19 reorder body/footer markup; the *slot names* are
  unchanged (catalogue Class 6).
- **`useService` reactivity (v19):** many core services became `reactive()`, so the
  `useState(useService(...))` wrapper is dropped for those. Confirm per service via OSM before
  adding or removing the wrapper.

---

## Era 2 - OWL 1 / dual system (v15 only)

`@odoo-module` ES modules and legacy `odoo.define()` AMD coexist; OWL is **1.4.11**.

- **Global namespace:** OWL 1 is reached through the global `owl.*` - `owl.Component`,
  `owl.hooks` (e.g. `owl.hooks.useState`), `owl.tags.xml` for inline templates. No
  `import ... from "@odoo/owl"` at v15.
- **Dual views:** legacy widget-based views ship alongside the new OWL components; both
  registration paths are live.
- Treat the OWL-1 global API as ground truth; never apply Era 3 idioms (`@odoo/owl`, static
  `template`/`props`, 2-arg `patch`) at v15.

---

## Era 1 - Legacy AMD / Widget (v8-v14) - pointer only

`odoo.define("addon.module", function (require) { ... })` AMD (`openerp.*` at v8); UI is
`Widget.extend({...})` / `AbstractField.extend({...})` with `web.Widget`, `require`/`return`, and
`include()` for monkey-patching. OWL is absent as the default (OWL 1.4.11 ships as a library at
v14 but is not the default rendering path). For v8-v14 work use the **`odoo-coding` legacy
gate**, which selects the `web.Widget` / `AbstractField` / `odoo.define()` path.

---

## Token reality

What a module may paint with is ruled by `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md`.
Which SCSS variables and runtime custom properties exist differs per series: find where a variable
or selector is defined and overridden in the index for the target series, and on a running
instance read the computed value on `:root` and on the element itself.

A custom property that computes empty takes every rule that reads it down with it, which shows as
a flat screen: panes without background or border, invisible muted text, badges without fill. It
has two causes: a chain into a property the series does not emit (Class 5), and a property defined
from itself (`--x: var(--x, <fallback>)` is a dependency cycle, so the fallback is never reached).
Fix the property once where it is defined, not on each component that reads it.

A stylesheet edit shows only after the bundle is rebuilt: an update of the module on the same
lease, or `?debug=assets` and a refresh for a file already in the bundle. Read the computed value
again after that.

---

## OWL pitfall catalogue (corrected, version-tagged)

Each class has its symptom, root cause, correct pattern and the series it applies to.

### Class 1 - `t-on` arrow `this` binding

- **Symptom (claimed):** an arrow handler in a template loses `this`. Flagging every arrow
  handler is a false positive.
- **Root cause / ground truth:** OWL injects `this` = the component into the template render
  context (`owl.js:2438`), so `() => this.foo()` is valid and used in core
  (`web/.../core/dialog/dialog.xml:24`), and the bare method form `t-on-click="foo"` auto-binds
  to the component. The real bug is a bare *free identifier* call - `() => onFoo()` where `onFoo`
  is neither on the component, on `props`, nor a slot-scope variable - which resolves to nothing
  at render time.
- **Correct pattern:** `t-on-click="onFoo"` (method) or `t-on-click="() => this.onFoo(ev)"`;
  for slot scope use the slot variable. Never `() => onFoo()` against a free identifier.
- **Version applicability:** v16+ (verify new majors via OSM).

### Class 2 - non-reactive `useService` in templates

- **Symptom:** values read from a service do not update the template when the service changes.
- **Root cause / ground truth:** whether a `useService` result is reactive depends on the series
  and the service. `useState(useService("ui"))` was required at v16, canonical at v17/v18
  (`web/.../core/emoji_picker/emoji_picker.js:138`), and dropped at v19 for services that became
  `reactive()` (`emoji_picker.js:110`).
- **Correct pattern:** resolve per target version + per service. v16-v18: wrap non-reactive
  services in `useState(useService("..."))`. v19: plain `useService("...")` for services that
  are `reactive()`; confirm which via OSM.
- **Version applicability:** required v16; canonical v17/v18; dropped v19 (per-service).

### Class 3 - raw `contenteditable` instead of the editor

- **Symptom:** rich-text/HTML editing is hand-rolled with a raw `contenteditable` element,
  losing toolbar/sanitisation/collaboration.
- **Root cause / ground truth:** the HTML field lazy-loads the editor bundle in `onWillStart`
  via `loadBundle('web_editor.backend_assets_wysiwyg')`, keeps props stable, and tracks
  `onWillUpdateProps` (`web_editor/.../static/src/.../backend/html_field.js:450`).
- **Correct pattern:** in `onWillStart`, `await loadBundle('web_editor.backend_assets_wysiwyg')`
  then instantiate the Wysiwyg with stable props; never author a raw `contenteditable`.
- **Version applicability:** v17+ (OWL form view).

### Class 4 - Sass function inside `calc()`

- **Symptom:** a Sass map/function call placed directly inside `calc()` produces wrong or
  literal CSS.
- **Root cause / ground truth:** all supported versions compile with **LibSass**; the fix is `#{}`
  interpolation so the Sass value is resolved before it reaches the CSS `calc()` - not a compiler
  swap. Core: `calc(#{map-get($spacers, 1 )} / 2)` (`web/.../views/calendar/calendar_renderer.scss:2`).
- **Correct pattern:** interpolate - `calc(#{map-get($spacers, 1 )} / 2)`, `calc(#{$gutter} / 2)`.
- **Version applicability:** all versions.

### Class 5 - `--bs-*` reference + self-referential custom property

- **Rule:** Odoo emits un-prefixed runtime tokens (`--primary`, `--o-color-*`, `--gray-*`),
  **not** `--bs-*`; never chain themeable tokens into `--bs-*` and never self-reference a var.
- **Symptom:** brand/surface tokens chained into `--bs-*` resolve to empty; "shim" custom
  properties resolve to empty.
- **Root cause / ground truth:** Odoo sets `$variable-prefix: ''` in
  `web/.../scss/bootstrap_overridden.scss:51`, so the runtime custom properties are
  `--primary`, `--o-color-*`, `--gray-*`, etc. (all v16+; re-verify the emitted token set per
  new major via OSM). Core contains no self-referential variable (§ Token reality).
- **Correct pattern:** reference the un-prefixed runtime tokens Odoo actually emits; a variable
  that must be backfilled is redefined non-self-referentially, anchored to an emitted token with
  a literal fallback.
- **Version applicability:** all v16+ (verify new majors via OSM).

### Class 6 - `Dialog` body slot

- **Rule:** `Dialog`'s body is the **default** slot; only `header` and `footer` are named.
  `t-set-slot="body"` does not exist - never use it.
- **Symptom:** a `<Dialog>` usage sets `t-set-slot="body"`, so the intended body content is dropped.
- **Root cause / ground truth:** the default slot of `Dialog` is the body; only `header` and
  `footer` are named (`web/.../core/dialog/dialog.xml`, body is `<t t-slot="default">` inside
  `modal-body`). v18/v19 reorder the body/footer markup; the slot names are unchanged.
- **Correct pattern:** body content in the default slot (no `t-set-slot`);
  `t-set-slot="header"` / `t-set-slot="footer"` only for those.
- **Version applicability:** all v16+ (verify new majors via OSM).

### Class 7 - props are validated only in dev mode

- **Rule:** a test of a view compiler or renderer that inserts component nodes mounts the result
  with prop validation on; the UI acceptance of such a change runs once with debug enabled.
- **Root cause / ground truth:** OWL checks component props only when the app runs in dev mode,
  so reading the compiled XML, a manual check or a screenshot in normal mode cannot catch a wrong
  prop.
- **Version applicability:** all v16+ (verify new majors via OSM).
