# Odoo Frontend Fidelity - era-aware OWL/JS/SCSS ground truth (SSOT)

> Shared, version-structured grounding doc for the frontend skills (`odoo-coding`,
> `odoo-code-review`, `odoo-ui-review`, and referenced by `odoo-ui-debugger` /
> `odoo-visual-regression`). It exists so frontend output is **correct and lint-compliant by
> construction** across every supported Odoo era, and so review-time diagnosis cites real
> ground truth rather than memory.
>
> **Two-tier SSOT.** The authoritative, queryable home for version-tagged rules and patterns
> is the Odoo Semantic server (queried via OSM: `lint_check`, `suggest_pattern`,
> `find_style_override`, `resolve_stylesheet`). This document is the **client-side grounding
> and standalone fallback** - it stays usable when the server is unreachable. Skills
> cross-reference this doc; they do not duplicate it.
>
> **Ground truth = OSM + the running instance, not memory.** The rules below are stable; any
> concrete *token name*, *signature*, or *bundle path* is version-specific - confirm it for the
> target version before relying on it.

This doc is organised by the three frontend eras, then a design-system-fidelity section, then
the corrected OWL pitfall catalogue.

---

## Era 3 - OWL 2 / ES modules (v16 onward) - FULL

Most live work targets this era. Module system is native `import` / `export` (with the
`/** @odoo-module */` pragma still accepted); components are OWL 2 imported from `@odoo/owl`
(OWL 2.8.x). Resolve the exact OWL minor and any token/signature via OSM per target version.

### Baseline (v16 onward, identical unless a sub-row says otherwise)

> Sub-rows below capture the known era breaks through v19. Odoo ships a new major roughly
> yearly; for a target newer than the last sub-row, verify the OWL minor, `patch()` arity,
> and service reactivity for that version via OSM before relying on these defaults.

- **Imports:** `import { Component, useState, useService, onWillStart } from "@odoo/owl";`
  (registry, hooks and core utilities from their own modules, e.g.
  `import { registry } from "@web/core/registry";`). Never use the global `owl.*` namespace
  (that is Era 2).
- **Component shape:** `class Foo extends Component { static template = "addon.Foo"; static props = {...}; setup() {...} }`. State via `useState({...})`; services via `useService("name")`.
- **Registry:** extend via `registry.category("...").add("key", value)` - fields, views,
  actions, services, systray, etc.
- **Templates:** QWeb in a separate `.xml` asset; `t-on-<event>="handler"` and
  `t-att`/`t-attf` bindings. Event handlers may be a method name (`t-on-click="onClick"`,
  auto-bound to the component) or an arrow (`t-on-click="() => this.onClick(ev)"`).

### Sub-row - v16

- **`useService` reactivity:** wrapping a service in `useState(...)` to make its values
  reactive in templates is **required at v16** for services that are not themselves reactive
  (e.g. `this.ui = useState(useService("ui"))`).
- **`patch()`:** 3-argument form `patch(target, "patchName", overrides)` is still accepted.

### Sub-row - v17+ (hard break)

- **`patch()` is 2-argument and throws on the old 3-arg form.** Use
  `patch(Target.prototype, { method() { ... super.method(...) ... } })`. The patch-name argument
  was removed; passing it raises. (`web/.../core/utils/patch.js` enforces this at v17.)
- **`useService` reactivity:** `useState(useService("..."))` remains the canonical idiom at
  v17/v18 for non-reactive services.

### Sub-row - v18+ (hard break)

- **`Dialog` declares props as static class fields, not external prop objects.** A `Dialog`
  subclass/usage sets `static props = {...}` / `static defaultProps = {...}` on the class
  (`web/.../core/dialog/dialog.js:34`, `:59`). The earlier pattern of passing an external
  props descriptor object no longer applies. v18 and v19 also reorder body/footer markup -
  but the *slot names* are unchanged (see catalogue Class 6).
- **`useService` reactivity (v19):** many core services became `reactive()` at v19, so the
  `useState(useService(...))` wrapper is **dropped** for those - a plain `useService("...")` is
  reactive on its own. Confirm per service via OSM before adding/removing the wrapper.

---

## Era 2 - OWL 1 / dual system (v15 only)

v15 is a transition release: `@odoo-module` ES modules and legacy `odoo.define()` AMD coexist
roughly half-and-half, and OWL is **version 1.4.11**.

- **Global namespace:** OWL 1 is reached through the global `owl.*` - `owl.Component`,
  `owl.hooks` (e.g. `owl.hooks.useState`), `owl.tags.xml` for inline templates. There is **no**
  `import ... from "@odoo/owl"` at v15.
- **Dual views:** legacy widget-based views still ship alongside the new OWL components; both
  registration paths are live.
- When writing or reviewing v15 frontend code, treat the OWL-1 global API as ground truth -
  do **not** apply Era 3 (`@odoo/owl`, static `template`/`props`, 2-arg `patch`) idioms.

---

## Era 1 - Legacy AMD / Widget (v8-v14) - pointer only

Module system is `odoo.define("addon.module", function (require) { ... })` AMD (`openerp.*` at
v8); UI is `Widget.extend({...})` / `AbstractField.extend({...})` with `web.Widget`,
`require`/`return`, and `include()` for monkey-patching. OWL is absent as the default (OWL
1.4.11 appears as a library at v14 but is not the default rendering path).

> Do not over-document legacy here. For v8-v14 frontend work, use the
> **`odoo-coding` legacy gate**, which auto-selects the `web.Widget` /
> `AbstractField` / `odoo.define()` path.

---

## Design-system fidelity - build theme-correct first, remediate second

> Make UI work **design-system-aware**: prevent off-theme output at write-time, and
> diagnose/fix it at review-time. **Prevention is the priority - reactive-only fixing is
> wasteful.** Ground truth = OSM + the running instance, not memory. The build-right *rules*
> are generic (version-independent) and may be applied verbatim; any *token name* is
> version-specific - resolve it for the target version via OSM (`resolve_stylesheet`,
> `find_style_override`) and confirm it at runtime with `getComputedStyle`. (Maps to catalogue
> Class 5 + the hardcoded-hex rule.)

### A. Build-right rules (generic - apply verbatim)

1. **Reuse Odoo runtime design tokens; pick tokens, not raw hex.** Anchor surfaces, borders,
   text and status colors to the design tokens the target version actually emits at runtime
   (resolve them via OSM + `getComputedStyle`).
2. **Never hardcode `hex` / `rgb()` / `rgba()` for themeable colors.** For tints/shades use
   `color-mix(in srgb, <token> X%, white|black|transparent)` so the result tracks the theme.
3. **Never self-reference a custom property:** `--x: var(--x, <fallback>)` is a CSS dependency
   cycle - it computes to the guaranteed-invalid (empty) value and the fallback is **never**
   reached, so the whole downstream chain resolves to empty. To backfill a missing variable,
   redefine it **non-self-referentially**, anchored to a variable the version *does* emit,
   each with a literal fallback.
4. **Fix the token foundation, not per-component patches (right altitude).** When many
   components look wrong, suspect the token layer first; one foundation fix usually resolves
   every downstream surface/border/text/badge token.
5. **Scope overrides appropriately** and respect the mockup's spec dimensions.

### B. Token reality - OSM-grounded, never hardcoded

For the **target version**:

1. `set_active_version(<target>)`.
2. `resolve_stylesheet(<module>, odoo_version='auto')` + `find_style_override(<selector_or_variable>, odoo_version='auto')` to discover
   which tokens/selectors actually exist and where they are defined/overridden.
3. On the running instance, read `getComputedStyle(document.documentElement)` (and key
   elements) to list which tokens **RESOLVE** vs are **EMPTY**, and to detect self-ref cycles
   and transparent surfaces.

#### Illustrative snapshot - Odoo 17 (VERIFY before relying on it; do NOT extrapolate)

> Labeled example only. Confirm via OSM (`resolve_stylesheet` for v17) + runtime
> `getComputedStyle`. **Do not assume these hold for v16 / v18 / v19** - re-derive per version.

- Odoo 17 ships **Bootstrap 5.1.3**, which emits at `:root` runtime custom properties such as
  `--primary`, `--secondary`, `--gray-100..900`, `--light`, `--dark`, `--body-bg`,
  `--body-color`, `--success/-warning/-danger/-info`, `--o-color-1..N`.
- It does **NOT** emit the `--bs-*` runtime custom properties (e.g. `--bs-body-bg`,
  `--bs-white`, `--bs-secondary-bg`, `--bs-border-color`, `--bs-*-subtle`). Chaining brand/
  surface tokens into `--bs-*` therefore resolves to empty on Odoo 17.

Add v16 / v18 / v19 rows only after verifying each via OSM + runtime.

### C. Verify-don't-trust loop

Never trust that an edit "took" - read the computed value:

1. Read computed styles on `:root` + representative elements -> list RESOLVE vs EMPTY; detect
   self-ref cycles and transparent surfaces.
2. Edit SCSS -> recompile the asset bundle (`--dev=assets` or restart) -> screenshot + re-read
   computed styles.
3. Iterate until tokens resolve and the UI matches the mockup.

### D. Mockup-first

Before writing, consult the project's mockups + UI design spec for intent. Theme-correct
means matching both the Odoo design system **and** the project's mockup.

### E. Worked example (the bug class this prevents)

An Odoo 17 OWL backend app rendered "flat": panes had no background/border, muted text was
near-invisible, badges lost their fill.

- **Cause (systemic, not one-off):** the app's SCSS chained surface tokens into Bootstrap 5.3
  `--bs-*` custom properties, but Odoo 17 (Bootstrap 5.1.3) does not emit those at runtime
  (`getComputedStyle` shows them empty at `:root`). A "shim" meant to backfill them used the
  self-referential pattern `--bs-x: var(--bs-x, <fallback>)` -> a CSS cycle -> empty -> the
  whole downstream chain resolved to empty.
- **Detection:** read `getComputedStyle(document.documentElement)` -> `--bs-*` EMPTY; identify
  the self-ref cycle in the shim.
- **Fix (one high-altitude change):** redefine the missing `--bs-*` **non-self-referentially**,
  anchored to vars Odoo 17 *does* emit at runtime (`--gray-100..900`, `--primary`,
  `--secondary`, `--success/-warning/-danger/-info`, `--body-bg`, `--body-color`,
  `--o-color-*`), each with a literal fallback. That one change resolved every downstream
  surface/border/text/badge token.
- **Before/after verification:** computed styles + screenshots show tokens now RESOLVE and the
  UI matches the theme.

A design-system-aware skill should (a) **never generate** this (rule A2/A3 + token reuse), and
(b) **flag it immediately on review** (the design-system lens runs the token-reality check).

### F. How the skills use this

- **`odoo-coding` (prevention):** before emitting SCSS/OWL, resolve which tokens to
  reuse (OSM + Section B); run the output self-check gate - no hardcoded hex/rgba, no self-ref
  custom property, referenced tokens exist at runtime for the target version, output matches
  the mockup.
- **`odoo-ui-review` (detection + remediation):** add a design-system/theme lens that runs
  the token-reality check (Section C) and flags empty/transparent surfaces, self-ref cycles,
  hardcoded palette, and mockup divergence - emitting token+file remediation pointers.
- **`odoo-ui-debugger` / `odoo-visual-regression`:** cross-reference this SSOT when a root cause
  or a diff is theme/token related.

### G. Brand-token fidelity (optional, brand-agnostic, consumer-driven)

Sections A-F enforce fidelity to **Odoo's own design system** (the `--primary` / `--o-color-*`
runtime tokens). Brand fidelity - "does this match *our* brand?" - is a **separate, optional**
layer, and it is deliberately **not** baked into this plugin: the plugin serves many brands, so
it ships a **mechanism, never a brand**. The consumer declares their brand; the skills discover
and assert against it. This mirrors how `verify-backend.sh` derives lint ENABLED_CODES from the
deployment's own quality module - **single source of truth lives in the consumer environment,
not vendored here.**

**Declaration (consumer side).** A project opts in by setting `brand_tokens_source` in
`.odoo-ai/context.md` to a committed JSON map of token -> expected color, e.g.
`{ "--primary": "#1E88E5", "--o-brand-secondary": "#8E24AA" }`. No map declared -> brand checks
silently skip (pure-Odoo projects are unaffected). The map is the brand SSOT; never hardcode
brand values into a skill, agent, or rule file.

**Two enforcement halves, one helper.** Both consume `brand_tokens_source` and share
`scripts/lib/color_delta.py` (stdlib CIEDE2000 - so `rgb()` / shorthand / hex variants compare
perceptually, not by string):
- **Static (no browser) - `verify-frontend.sh` Tier 4:** scans changed SCSS for hardcoded hex
  that sits within ΔE `BRAND_NEAR_DELTA` of a declared brand token and WARNs "reference the
  token var, don't inline the brand color" (the A2/A3 rule, brand-aware). WARN-only.
- **Runtime (live screen) - `odoo-ui-review` Step 4b:** reads `getComputedStyle(:root)` and
  ΔE-diffs the *resolved* brand tokens against the declared map - the only place the real
  rendered value is knowable (OSM indexes SCSS but cannot resolve the cascade winner). WARN.

Keep brand checks WARN-tier: ΔE thresholds and `rgb()`-vs-hex rounding make false-blocks easy.
A `mockup_dir` key (also consumer-declared) feeds the existing mockup-first check (Section D).

---

## OWL pitfall catalogue (corrected, version-tagged)

Six classes. Each lists symptom, root cause, the correct pattern, a real source citation,
version applicability, and a tier tag. Tier semantics: **lint-block** = the gate should fail;
**lint-warn** = the gate should warn (false-positive-prone, human-confirm); **grounding** =
resolve the right shape via OSM before writing; **runtime** = only observable on the running
instance.

### Class 1 - `t-on` arrow `this` binding

- **Common misconception:** that any arrow handler in a template loses `this` and is
  "always broken". This is a false positive - flagging every arrow handler is wrong.
- **Symptom (claimed):** an arrow handler in a template loses `this`.
- **Root cause / ground truth:** OWL injects `this` = the component into the template render
  context (`owl.js:2438`). Therefore `() => this.foo()` **is valid and used in core**
  (`web/.../core/dialog/dialog.xml:24`, e.g. `t-on-click="() => this.data.close()"`), and the
  bare method form `t-on-click="foo"` auto-binds to the component (also safe). The **real** bug
  is a bare *free identifier* call - `() => onFoo()` where `onFoo` is neither on the component,
  on `props`, nor a slot-scope variable - which resolves to nothing at render time.
- **Correct pattern:** `t-on-click="onFoo"` (method) or `t-on-click="() => this.onFoo(ev)"`;
  for slot scope use the slot variable. Do not write `() => onFoo()` against a free identifier.
- **Citation:** `owl.js:2438` (ctx `this` injection); `web/.../core/dialog/dialog.xml:24`.
- **Version applicability:** identical v16+ (confirmed through v19; OWL 2 context injection is
  stable - verify for new majors via OSM).
- **Tier:** **lint-block (tightened)** - the rule must match only *arrow + bare lowercase
  identifier call without `this.` / `props.` / a slot variable*, so it does **not** flag
  `t-on="foo"` nor `() => this.foo()` (matches core usage; flagging those is a false positive).

### Class 2 - non-reactive `useService` in templates

- **Rule (version-dependent):** whether a `useService` result is reactive depends on the
  Odoo version and the specific service - resolve it per target, do not assume.
- **Symptom:** values read from a service do not update the template when the service changes.
- **Root cause / ground truth:** whether a `useService` result is reactive changed across
  versions. `useState(useService("ui"))` was **required at v16**, remained **canonical at
  v17/v18** (`web/.../core/emoji_picker/emoji_picker.js:138`), and was **dropped at v19** for
  services that became `reactive()` themselves - a plain `useService` is then already reactive
  (`web/.../core/emoji_picker/emoji_picker.js:110`).
- **Correct pattern:** resolve per target version + per service. v16-v18: wrap non-reactive
  services in `useState(useService("..."))`. v19: use plain `useService("...")` for services that
  are `reactive()`; confirm which via OSM.
- **Citation:** `emoji_picker.js:138` (v17/18 wrap), `emoji_picker.js:110` (v19 plain).
- **Version applicability:** required v16; canonical v17/v18; dropped v19 (per-service).
- **Tier:** **grounding + runtime; lint-warn only** (correct shape is version- and
  service-dependent, so a block rule would over-fire).

### Class 3 - raw `contenteditable` instead of the editor

- **Rule:** never hand-roll rich-text editing with a raw `contenteditable`; use Odoo's editor.
- **Symptom:** rich-text/HTML editing is hand-rolled with a raw `contenteditable` element
  instead of Odoo's editor component, losing toolbar/sanitisation/collaboration.
- **Root cause / ground truth:** the HTML field lazy-loads the editor bundle in
  **`onWillStart`** via `loadBundle('web_editor.backend_assets_wysiwyg')`, keeps props stable,
  and tracks `onWillUpdateProps`
  (`web_editor/.../static/src/.../backend/html_field.js:450`).
- **Correct pattern:** in `onWillStart`, `await loadBundle('web_editor.backend_assets_wysiwyg')`
  then instantiate the Wysiwyg with stable props; do not author a raw `contenteditable`.
- **Citation:** `web_editor/.../backend/html_field.js:450`.
- **Version applicability:** v17+ (OWL form view).
- **Tier:** **lint-block** (raw `contenteditable`) **+ grounding** (resolve the correct bundle
  name / lazy-load shape via OSM).

### Class 4 - Sass function inside `calc()`

- **Common misconception:** that this is a "LibSass vs Dart Sass" compatibility issue. It is
  not - all supported versions use LibSass; the fix is `#{}` interpolation, not a compiler swap.
- **Symptom:** a Sass map/function call placed directly inside `calc()` produces wrong or
  literal CSS.
- **Root cause / ground truth:** all supported versions compile with **LibSass**
  (libsass-python); the real fix is `#{}` interpolation so the Sass value is resolved before it
  reaches the CSS `calc()`. Core does exactly this:
  `calc(#{map-get($spacers, 1 )} / 2)` (`web/.../views/calendar/calendar_renderer.scss:2`).
- **Correct pattern:** interpolate - `calc(#{map-get($spacers, 1 )} / 2)`,
  `calc(#{$gutter} / 2)` - rather than calling the Sass function bare inside `calc()`.
- **Citation:** `web/.../views/calendar/calendar_renderer.scss:2`.
- **Version applicability:** all versions (LibSass throughout).
- **Tier:** **lint-warn** - flag `calc(` containing `map-get` / `min(` (etc.) without an
  enclosing `#{`.

### Class 5 - `--bs-*` reference + self-referential custom property

- **Rule:** Odoo emits un-prefixed runtime tokens (`--primary`, `--o-color-*`, `--gray-*`),
  **not** `--bs-*`; never chain themeable tokens into `--bs-*` and never self-reference a var.
- **Symptom:** brand/surface tokens chained into `--bs-*` resolve to empty; "shim" custom
  properties resolve to empty.
- **Root cause / ground truth:** Odoo sets `$variable-prefix: ''` in
  `web/.../scss/bootstrap_overridden.scss:51`, so the runtime custom properties are
  `--primary`, `--o-color-*`, `--gray-*`, etc. - **not** `--bs-*`. This applies to **all
  v16+** (not just v17; confirmed through v19 - re-verify the emitted token set per new major
  via OSM). Core contains no real self-referential variable; that pattern is a
  pure-CSS authoring mistake (see Design-system fidelity Section A3 + worked example).
- **Correct pattern:** reference the un-prefixed runtime tokens Odoo actually emits; if a
  variable must be backfilled, redefine it non-self-referentially anchored to an emitted token
  with a literal fallback.
- **Citation:** `web/.../scss/bootstrap_overridden.scss:51` (`$variable-prefix: ''`).
- **Version applicability:** all v16+ (confirmed through v19; verify new majors via OSM).
- **Tier:** **lint-warn** - flag `var(--bs-` in addon SCSS (and the self-ref
  `--x: var(--x, ...)` pattern).

### Class 6 - `Dialog` body slot

- **Rule:** `Dialog`'s body is the **default** slot; only `header` and `footer` are named.
  `t-set-slot="body"` does not exist - never use it.
- **Symptom:** a `<Dialog>` usage sets `t-set-slot="body"`, which does not exist, so the
  intended body content is dropped.
- **Root cause / ground truth:** the **default** slot of `Dialog` is the body; only `header`
  and `footer` are named slots (`web/.../core/dialog/dialog.xml`, body is `<t t-slot="default">`
  inside `modal-body`). v18/v19 reorder the body/footer markup but the **slot names are
  unchanged**.
- **Correct pattern:** put body content in the default slot (no `t-set-slot`), and use
  `t-set-slot="header"` / `t-set-slot="footer"` only for those.
- **Citation:** `web/.../core/dialog/dialog.xml` (default = body; `header`/`footer` named).
- **Version applicability:** all v16+ (markup reorder at v18/v19, slot names stable; verify new
  majors via OSM).
- **Tier:** **lint-block** - flag `t-set-slot="body"` under `<Dialog>`.
