---
name: odoo-icon-design
argument-hint: "[module] [version]"
description: >
  Design and generate the module identity icon (static/description/icon.png, plus icon.svg on
  v19) - a version-correct SVG composed and rasterized to PNG 256x256. Dispatches
  odoo-icon-designer. Standalone-first; no browser or instance required; OSM optional for
  module category and version grounding. Trigger on: 'design an app icon', 'make an icon for
  this module', 'create icon for addon', 'tạo icon module', 'thiết kế biểu tượng module',
  'icon.png cho module', 'vẽ icon cho addon', 'thiết kế icon cho module'. route a 128px
  live-screen CROP -> odoo-doc-illustration; in-UI FA glyphs in views or buttons -> odoo-coding
  or odoo-frontend-design; website favicon -> odoo-coding; rendered icon review -> odoo-ui-review.
  DO NOT trigger for editing existing screenshots, rating live screens, or authoring in-app
  widget glyphs
---

## Role

Module identity icon designer for Odoo: composes a version-correct, brand-aware SVG vector icon
(era-matched style, FA-category glyph, solid background) then rasterizes it to a 256x256 PNG at
`static/description/icon.png`. Works entirely from static source - no browser, no live instance.
OSM is the primary source for module category and version grounding; the on-disk `__manifest__.py`
is the fallback.

NOT for auditing or rating a rendered screen (-> `odoo-ui-review`); NOT for capturing a live
screenshot of a module as its icon (-> `odoo-doc-illustration`). Produces a designed vector asset,
not a viewport crop.

## Out of Scope

- **128px viewport CROP of a live screen used as icon** -> `odoo-doc-illustration` (screenshot
  capture, not design)
- **In-UI Font Awesome glyph class in a view or button** (not an asset file, no `icon.png`
  created) -> `odoo-coding` or `odoo-frontend-design`
- **Website favicon** (`favicon.ico` / `favicon.svg` served at root) -> `odoo-coding`
- **Aesthetic or a11y review of an icon already in production** -> `odoo-ui-review`

## Agent invocation

Dispatch `odoo-icon-designer` with a brief:

```
MODULE: <module name>
MODULE_PATH: <absolute path to module dir, or omit to let agent resolve>
VERSION: <Odoo series, e.g. 17.0 - or omit to let agent resolve from manifest/context>
BRIEF: <palette hints, symbol hint, or additional context; omit for brand-agnostic defaults>
```

Agent resolves `odoo_version` and palette from context when the brief omits them (Step 0 of the
agent). Pass `VERSION` explicitly when the caller already has it to save a resolution round-trip.

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

## Design-system contract

The icon deliverable is a rasterized PNG (`static/description/icon.png`, 256x256) - raster pixels,
not a live-rendered Odoo UI component - so the CSS design-token checks in
`skills/_shared/odoo-frontend-fidelity.md` (the in-repo frontend fidelity contract, which governs
RENDERED Odoo screens) do NOT apply to the icon asset itself. Palette is brand-agnostic and
resolved to CONCRETE hex values via Step 1 of the `odoo-icon-designer` agent (dispatch `BRIEF:`
-> `.odoo-ai/context.md` brand tokens -> module-category hue -> Odoo default `#714B67`). Never
invent CSS custom-property names (e.g. `var(--primary)`) and never hardcode a vendor brand
(Viindoo) palette in the source SVG or this skill - the SVG is composed with the same resolved hex
fills, not with design-system token references.

## Standalone-first fallback

- **OSM unreachable:** agent reads `category`, `name`, and `summary` from `__manifest__.py` on
  disk for glyph and palette selection; proceeds without OSM grounding; prefixes output with
  `WARNING: OSM unreachable - glyph/palette inferred from manifest fields only`.
- **Rasterizer absent (no rsvg-convert, inkscape, magick/convert, cairosvg, or Pillow):**
  agent writes `icon.svg` only, emits platform-specific install guidance, and sets
  `status: NEEDS_CONTEXT(no SVG rasterizer; icon.svg written, icon.png pending)`. Not a hard fail.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
