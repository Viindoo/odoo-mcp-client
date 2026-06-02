# Odoo Design-System Fidelity — build theme-correct first, remediate second

> Shared SSOT for the UI/UX skills (`odoo-frontend-coder`, `odoo-ui-reviewer`, and
> referenced by `odoo-ui-debug`, `odoo-visual-regression`). It exists to make UI work
> **design-system-aware**: prevent off-theme output at write-time, and diagnose/fix it at
> review-time. **Prevention is the priority — reactive-only fixing is wasteful.**
>
> **Ground truth = OSM + the running instance, not memory.** The build-right *rules* below
> are generic (version-independent) and may be applied verbatim. Any *token name* is
> version-specific: resolve it for the target version via OSM (`resolve_stylesheet`,
> `find_style_override`) and confirm it at runtime with `getComputedStyle` — never assume a
> token exists across versions.

## A. Build-right rules (generic — apply verbatim)

1. **Reuse Odoo runtime design tokens; pick tokens, not raw hex.** Anchor surfaces, borders,
   text and status colors to the design tokens the target version actually emits at runtime
   (resolve them via OSM + `getComputedStyle`).
2. **Never hardcode `hex` / `rgb()` / `rgba()` for themeable colors.** For tints/shades use
   `color-mix(in srgb, <token> X%, white|black|transparent)` so the result tracks the theme.
3. **Never self-reference a custom property:** `--x: var(--x, <fallback>)` is a CSS dependency
   cycle — it computes to the guaranteed-invalid (empty) value and the fallback is **never**
   reached, so the whole downstream chain resolves to empty. To backfill a missing variable,
   redefine it **non-self-referentially**, anchored to a variable the version *does* emit,
   each with a literal fallback.
4. **Fix the token foundation, not per-component patches (right altitude).** When many
   components look wrong, suspect the token layer first; one foundation fix usually resolves
   every downstream surface/border/text/badge token.
5. **Scope overrides appropriately** and respect the mockup's spec dimensions.

## B. Token reality — OSM-grounded, never hardcoded

For the **target version**:

1. `set_active_version(<target>)`.
2. `resolve_stylesheet(<module>)` + `find_style_override(<selector_or_variable>)` to discover
   which tokens/selectors actually exist and where they are defined/overridden.
3. On the running instance, read `getComputedStyle(document.documentElement)` (and key
   elements) to list which tokens **RESOLVE** vs are **EMPTY**, and to detect self-ref cycles
   and transparent surfaces.

### Illustrative snapshot — Odoo 17 (VERIFY before relying on it; do NOT extrapolate)

> Labeled example only. Confirm via OSM (`resolve_stylesheet` for v17) + runtime
> `getComputedStyle`. **Do not assume these hold for v16 / v18 / v19** — re-derive per version.

- Odoo 17 ships **Bootstrap 5.1.3**, which emits at `:root` runtime custom properties such as
  `--primary`, `--secondary`, `--gray-100..900`, `--light`, `--dark`, `--body-bg`,
  `--body-color`, `--success/-warning/-danger/-info`, `--o-color-1..N`.
- It does **NOT** emit the `--bs-*` runtime custom properties (e.g. `--bs-body-bg`,
  `--bs-white`, `--bs-secondary-bg`, `--bs-border-color`, `--bs-*-subtle`). Chaining brand/
  surface tokens into `--bs-*` therefore resolves to empty on Odoo 17.

Add v16 / v18 / v19 rows only after verifying each via OSM + runtime.

## C. Verify-don't-trust loop

Never trust that an edit "took" — read the computed value:

1. Read computed styles on `:root` + representative elements → list RESOLVE vs EMPTY; detect
   self-ref cycles and transparent surfaces.
2. Edit SCSS → recompile the asset bundle (`--dev=assets` or restart) → screenshot + re-read
   computed styles.
3. Iterate until tokens resolve and the UI matches the mockup.

## D. Mockup-first

Before writing, consult the project's mockups + UI design spec for intent. Theme-correct
means matching both the Odoo design system **and** the project's mockup.

## E. Worked example (the bug class this prevents)

An Odoo 17 OWL backend app rendered "flat": panes had no background/border, muted text was
near-invisible, badges lost their fill.

- **Cause (systemic, not one-off):** the app's SCSS chained surface tokens into Bootstrap 5.3
  `--bs-*` custom properties, but Odoo 17 (Bootstrap 5.1.3) does not emit those at runtime
  (`getComputedStyle` shows them empty at `:root`). A "shim" meant to backfill them used the
  self-referential pattern `--bs-x: var(--bs-x, <fallback>)` → a CSS cycle → empty → the whole
  downstream chain resolved to empty.
- **Detection:** read `getComputedStyle(document.documentElement)` → `--bs-*` EMPTY; identify
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

## F. How the skills use this

- **`odoo-frontend-coder` (prevention):** before emitting SCSS/OWL, resolve which tokens to
  reuse (OSM + Section B); run the output self-check gate — no hardcoded hex/rgba, no self-ref
  custom property, referenced tokens exist at runtime for the target version, output matches
  the mockup.
- **`odoo-ui-reviewer` (detection + remediation):** add a design-system/theme lens that runs
  the token-reality check (Section C) and flags empty/transparent surfaces, self-ref cycles,
  hardcoded palette, and mockup divergence — emitting token+file remediation pointers.
- **`odoo-ui-debug` / `odoo-visual-regression`:** cross-reference this SSOT when a root cause
  or a diff is theme/token related.
