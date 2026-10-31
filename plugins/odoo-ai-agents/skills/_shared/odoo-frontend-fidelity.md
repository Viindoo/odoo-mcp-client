# Odoo Frontend Fidelity - era-aware OWL/JS/SCSS ground truth (SSOT)

> Grounding for the frontend skills (`odoo-coding`, `odoo-code-review`, `odoo-ui-review`,
> `odoo-ui-debugger`, `odoo-visual-regression`). The queryable home of version-tagged rules is the
> Odoo Semantic server (`lint_check`, `suggest_pattern`, `find_style_override`,
> `resolve_stylesheet`); this document is the client-side grounding and the standalone fallback.
> Skills cross-reference it; they do not duplicate it.
>
> **Ground truth = OSM + the running instance, not memory.** The rules below are stable; any
> concrete *token name*, *signature* or *bundle path* is version-specific - confirm it for the
> target version before relying on it.

Organised by the three frontend eras, then design-system fidelity, then the OWL pitfall catalogue.

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

## Design-system fidelity - build theme-correct first, remediate second

> Prevent off-theme output at write-time; diagnose and fix it at review-time. The build-right
> *rules* are generic and apply verbatim; any *token name* is version-specific - resolve it for the
> target version via OSM (`resolve_stylesheet`, `find_style_override`) and confirm it at runtime
> with `getComputedStyle`.

### A. Build-right rules (generic - apply verbatim)

1. **Reuse Odoo runtime design tokens; pick tokens, not raw hex.** Anchor surfaces, borders,
   text and status colors to the design tokens the target version actually emits at runtime
   (resolve them via OSM + `getComputedStyle`).
2. **Never hardcode `hex` / `rgb()` / `rgba()` for themeable colors.** For tints/shades use
   `color-mix(in srgb, <token> X%, white|black|transparent)` so the result tracks the theme.
3. **Never self-reference a custom property:** `--x: var(--x, <fallback>)` is a CSS dependency
   cycle - it computes to the guaranteed-invalid (empty) value and the fallback is never reached,
   so the whole downstream chain resolves to empty. To backfill a missing variable, redefine it
   **non-self-referentially**, anchored to a variable the version *does* emit, each with a literal
   fallback.
4. **Fix the token foundation, not per-component patches (right altitude).** When many
   components look wrong, suspect the token layer first; one foundation fix usually resolves
   every downstream surface/border/text/badge token.
5. **Scope overrides appropriately** and respect the mockup's spec dimensions.
6. **A business module paints only with core levers**: the core SCSS variables, the runtime
   custom properties core and Bootstrap emit, and core classes that carry a theme meaning. No
   custom property of its own (`--<vendor>-*`), no class of its own that holds a color, no
   Bootstrap class that fixes a color regardless of theme (`bg-white`, `text-dark`,
   `border-light`). The test: a theme that changes a core token changes the module with it, with
   no edit in the module.

### B. Token reality - OSM-grounded, never hardcoded

For the **target version**:

1. `set_active_version(<target>)`.
2. `resolve_stylesheet(<module>, odoo_version='<version>')` + `find_style_override(<selector_or_variable>, odoo_version='<version>')` to discover
   which tokens/selectors actually exist and where they are defined/overridden.
3. On the running instance, read `getComputedStyle(document.documentElement)` (and key
   elements) to list which tokens **RESOLVE** vs are **EMPTY**, and to detect self-ref cycles
   and transparent surfaces.

#### Illustrative snapshot - Odoo 17 (VERIFY before relying on it; do NOT extrapolate)

- Odoo 17 ships **Bootstrap 5.1.3**, which emits at `:root` runtime custom properties such as
  `--primary`, `--secondary`, `--gray-100..900`, `--light`, `--dark`, `--body-bg`,
  `--body-color`, `--success/-warning/-danger/-info`, `--o-color-1..N`.
- It does **NOT** emit the `--bs-*` runtime custom properties (e.g. `--bs-body-bg`,
  `--bs-white`, `--bs-secondary-bg`, `--bs-border-color`, `--bs-*-subtle`). Chaining brand/
  surface tokens into `--bs-*` therefore resolves to empty on Odoo 17.

Add rows for other series only after verifying each via OSM + runtime.

### C. Verify-don't-trust loop

Never trust that an edit "took" - read the computed value:

1. Read computed styles on `:root` + representative elements -> list RESOLVE vs EMPTY; detect
   self-ref cycles and transparent surfaces.
2. Edit SCSS -> recompile the asset bundle (`--dev=assets` or restart) -> screenshot (destination:
   state-root-resolution.md § Where a captured artifact goes) + re-read computed styles.
3. Iterate until tokens resolve and the UI matches the mockup.

### D. Mockup-first

Before writing, consult the project's mockups + UI design spec for intent. Theme-correct means
matching both the Odoo design system **and** the project's mockup.

### E. The bug class this prevents

An OWL backend app renders "flat" (panes without background or border, muted text invisible,
badges without fill) when its SCSS chains surface tokens into custom properties the series does
not emit at runtime and a "shim" backfills them self-referentially (rule A3): every downstream
token resolves to empty. Detection: `getComputedStyle(document.documentElement)` shows the chain
EMPTY. Fix: one high-altitude change - redefine the missing variables non-self-referentially,
anchored to tokens the series does emit, each with a literal fallback - then verify per § C. A
design-system-aware skill never generates this (A2/A3 + token reuse) and flags it on review.

### F. How the skills use this

- **`odoo-coding` (prevention):** before emitting SCSS/OWL, resolve which tokens to reuse
  (OSM + § B); run the output self-check gate - no hardcoded hex/rgba, no self-ref custom
  property, referenced tokens exist at runtime for the target version, output matches the mockup.
- **`odoo-ui-review` (detection + remediation):** the design-system/theme lens runs the
  token-reality check (§ C) and flags empty/transparent surfaces, self-ref cycles, hardcoded
  palette and mockup divergence - emitting token+file remediation pointers.
- **`odoo-ui-debugger` / `odoo-visual-regression`:** cross-reference this SSOT when a root cause
  or a diff is theme/token related.

### G. Brand-token fidelity (optional, brand-agnostic, consumer-driven)

Sections A-F enforce fidelity to **Odoo's own design system** (the `--primary` / `--o-color-*`
runtime tokens). Brand fidelity - "does this match *our* brand?" - is a separate, optional layer:
the plugin ships a mechanism, never a brand. The consumer declares their brand; the skills
discover and assert against it.

**Declaration (consumer side).** A project opts in by placing `<SHARE_DIR>/brand-tokens.json`
(resolve `<SHARE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit) - a JSON map of token -> expected color, e.g.
`{ "--primary": "#1E88E5", "--o-brand-secondary": "#8E24AA" }`. The file's EXISTENCE is the opt-in;
absent -> brand checks silently skip. The map is the brand SSOT; never hardcode brand values into
a skill, agent, or rule file.

**Two enforcement halves, one helper.** Both read that map and share
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/color_delta.py" [--threshold T] <expected> <actual>`
(CIEDE2000, so hex/`rgb()` variants compare perceptually; prints ΔE; `--threshold`: exit 0 within,
1 over; exit 2 unparseable = skip):
- **Static (no browser) - `verify-frontend.sh` Tier 4:** scans changed SCSS for hardcoded hex
  that sits within ΔE `BRAND_NEAR_DELTA` of a declared brand token and WARNs "reference the
  token var, don't inline the brand color". WARN-only.
- **Runtime (live screen) - `odoo-ui-review` Step 4b:** reads `getComputedStyle(:root)` and
  ΔE-diffs the *resolved* brand tokens against the declared map - the only place the real
  rendered value is knowable. WARN.

Keep brand checks WARN-tier: ΔE thresholds and `rgb()`-vs-hex rounding make false-blocks easy.
A non-empty `<SHARE_DIR>/mockups/` (also consumer-declared) feeds the mockup-first check (§ D).

---

## OWL pitfall catalogue (corrected, version-tagged)

Six classes. Each lists symptom, root cause, the correct pattern, a source citation, version
applicability and a tier tag. Tier semantics: **lint-block** = the gate fails; **lint-warn** =
the gate warns (false-positive-prone, human-confirm); **grounding** = resolve the right shape via
OSM before writing; **runtime** = only observable on the running instance.

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
- **Citation:** `owl.js:2438`; `web/.../core/dialog/dialog.xml:24`.
- **Version applicability:** v16+ (verify new majors via OSM).
- **Tier:** **lint-block (tightened)** - match only *arrow + bare lowercase identifier call
  without `this.` / `props.` / a slot variable*; never flag `t-on="foo"` nor `() => this.foo()`.

### Class 2 - non-reactive `useService` in templates

- **Symptom:** values read from a service do not update the template when the service changes.
- **Root cause / ground truth:** whether a `useService` result is reactive depends on the series
  and the service. `useState(useService("ui"))` was required at v16, canonical at v17/v18
  (`web/.../core/emoji_picker/emoji_picker.js:138`), and dropped at v19 for services that became
  `reactive()` (`emoji_picker.js:110`).
- **Correct pattern:** resolve per target version + per service. v16-v18: wrap non-reactive
  services in `useState(useService("..."))`. v19: plain `useService("...")` for services that
  are `reactive()`; confirm which via OSM.
- **Citation:** `emoji_picker.js:138` (v17/18 wrap), `emoji_picker.js:110` (v19 plain).
- **Version applicability:** required v16; canonical v17/v18; dropped v19 (per-service).
- **Tier:** **grounding + runtime; lint-warn only** (the correct shape is version- and
  service-dependent).

### Class 3 - raw `contenteditable` instead of the editor

- **Symptom:** rich-text/HTML editing is hand-rolled with a raw `contenteditable` element,
  losing toolbar/sanitisation/collaboration.
- **Root cause / ground truth:** the HTML field lazy-loads the editor bundle in `onWillStart`
  via `loadBundle('web_editor.backend_assets_wysiwyg')`, keeps props stable, and tracks
  `onWillUpdateProps` (`web_editor/.../static/src/.../backend/html_field.js:450`).
- **Correct pattern:** in `onWillStart`, `await loadBundle('web_editor.backend_assets_wysiwyg')`
  then instantiate the Wysiwyg with stable props; never author a raw `contenteditable`.
- **Citation:** `web_editor/.../backend/html_field.js:450`.
- **Version applicability:** v17+ (OWL form view).
- **Tier:** **lint-block** (raw `contenteditable`) **+ grounding** (resolve the bundle name /
  lazy-load shape via OSM).

### Class 4 - Sass function inside `calc()`

- **Symptom:** a Sass map/function call placed directly inside `calc()` produces wrong or
  literal CSS.
- **Root cause / ground truth:** all supported versions compile with **LibSass**; the fix is `#{}`
  interpolation so the Sass value is resolved before it reaches the CSS `calc()` - not a compiler
  swap. Core: `calc(#{map-get($spacers, 1 )} / 2)` (`web/.../views/calendar/calendar_renderer.scss:2`).
- **Correct pattern:** interpolate - `calc(#{map-get($spacers, 1 )} / 2)`, `calc(#{$gutter} / 2)`.
- **Citation:** `web/.../views/calendar/calendar_renderer.scss:2`.
- **Version applicability:** all versions.
- **Tier:** **lint-warn** - flag `calc(` containing `map-get` / `min(` (etc.) without an
  enclosing `#{`.

### Class 5 - `--bs-*` reference + self-referential custom property

- **Rule:** Odoo emits un-prefixed runtime tokens (`--primary`, `--o-color-*`, `--gray-*`),
  **not** `--bs-*`; never chain themeable tokens into `--bs-*` and never self-reference a var.
- **Symptom:** brand/surface tokens chained into `--bs-*` resolve to empty; "shim" custom
  properties resolve to empty.
- **Root cause / ground truth:** Odoo sets `$variable-prefix: ''` in
  `web/.../scss/bootstrap_overridden.scss:51`, so the runtime custom properties are
  `--primary`, `--o-color-*`, `--gray-*`, etc. (all v16+; re-verify the emitted token set per
  new major via OSM). Core contains no self-referential variable; that pattern is a pure-CSS
  authoring mistake (§ A3, § E).
- **Correct pattern:** reference the un-prefixed runtime tokens Odoo actually emits; a variable
  that must be backfilled is redefined non-self-referentially, anchored to an emitted token with
  a literal fallback.
- **Citation:** `web/.../scss/bootstrap_overridden.scss:51` (`$variable-prefix: ''`).
- **Version applicability:** all v16+ (verify new majors via OSM).
- **Tier:** **lint-warn** - flag `var(--bs-` in addon SCSS (and the self-ref
  `--x: var(--x, ...)` pattern).

### Class 6 - `Dialog` body slot

- **Rule:** `Dialog`'s body is the **default** slot; only `header` and `footer` are named.
  `t-set-slot="body"` does not exist - never use it.
- **Symptom:** a `<Dialog>` usage sets `t-set-slot="body"`, so the intended body content is dropped.
- **Root cause / ground truth:** the default slot of `Dialog` is the body; only `header` and
  `footer` are named (`web/.../core/dialog/dialog.xml`, body is `<t t-slot="default">` inside
  `modal-body`). v18/v19 reorder the body/footer markup; the slot names are unchanged.
- **Correct pattern:** body content in the default slot (no `t-set-slot`);
  `t-set-slot="header"` / `t-set-slot="footer"` only for those.
- **Citation:** `web/.../core/dialog/dialog.xml`.
- **Version applicability:** all v16+ (verify new majors via OSM).
- **Tier:** **lint-block** - flag `t-set-slot="body"` under `<Dialog>`.
