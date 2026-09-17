---
name: odoo-icon-design
argument-hint: "[module] [version]"
description: >
  Design and generate the module identity icon (static/description/icon.png, plus the icon.svg
  source) - a version-correct SVG composed and rasterized to PNG 256x256. Dispatches
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
OSM is the primary source for module category and version grounding; the on-disk descriptor
(`__manifest__.py`, or `__openerp__.py` on v8-v9) is the fallback.

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

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

## Agent invocation

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief.

`icon.png`/`icon.svg` and the `__manifest__.py` edit are git-tracked writes, so per
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton field 5 resolve `WORKTREE_PATH` BEFORE this
dispatch: reuse the worktree already in scope, else provision one via `git-toolkit:git-ops` - never
the principal checkout (S9, see § Verify then commit below) - then dispatch `odoo-icon-designer`
with a brief:

```
MODULE: <module name>
MODULE_PATH: <absolute path to module dir, or omit to let agent resolve under WORKTREE_PATH>
WORKTREE_PATH: <abs path resolved above>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve; the agent roots itself at WORKTREE_PATH, so its own resolve would key on that worktree>
VERSION: <Odoo series, e.g. 17.0 - or omit to let agent resolve from manifest/context>
BRIEF: <palette hints, symbol hint, or additional context; omit for brand-agnostic defaults>
```

Agent resolves `odoo_version` and palette from context when the brief omits them (Step 0 of the
agent). Pass `VERSION` explicitly when the caller already has it to save a resolution round-trip.

MCP tool surface for the dispatched agent is the same as `## MCP tools` above - not repeated here.

## Design-system contract

The icon deliverable is a rasterized PNG (`static/description/icon.png`, 256x256), not a
live-rendered Odoo UI component - the CSS design-token checks in
`skills/_shared/odoo-frontend-fidelity.md` (which govern RENDERED Odoo screens) do NOT apply to
it. Palette resolution (brief -> `brand-tokens.json` -> category hue -> Odoo default) and the
brand-agnostic, no-vendor-palette rule are owned by `agents/odoo-icon-designer.md` § Step 1 and
§ Hard constraints - not restated here.

## Standalone-first fallback

- **OSM unreachable:** agent proceeds disk-only from the manifest descriptor; exact fields read
  and warning text owned by `agents/odoo-icon-designer.md` § Step 0.
- **Rasterizer absent:** not a hard fail - `icon.svg` ships alone with install guidance; full
  fallback behavior owned by `agents/odoo-icon-designer.md` § Step 4.

## Verify then commit (git-delegation)

**Verify then commit.** Verify the `odoo-icon-designer` agent's returned artifacts against its
Output block (files exist at the reported paths under the `WORKTREE_PATH` resolved above -
`icon.png`, plus `icon.svg` and the `__manifest__.py` `icon` key whenever the run wrote them;
which asset formats the target series accepts is resolved by the agent against OSM, never
assumed from a series here), then COMMIT
`icon.png`/`icon.svg`/the manifest `icon` key via git-toolkit `git-ops` (one-way git; the skill
never runs raw git mutations) - never the principal checkout (S9). Full contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
