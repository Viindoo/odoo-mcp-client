---
name: odoo-frontend-design
description: >
  Design-quality expertise for ANY Odoo UI/UX work - the senior-frontend-designer brain other
  skills and agents LOAD to make Odoo interfaces look and feel RIGHT. Knowledge-only: teaches
  HOW to design well in Odoo; does not write code or spawn agents. Apply whenever Odoo UI quality
  matters: form views, list/tree, kanban, pivot/graph/calendar/activity, search views, OWL
  components, QWeb, field widgets, statusbar/notebook/button-box/chatter layout, smart buttons,
  decorations, empty states, density, responsive web client, accessibility, SCSS/design tokens;
  plus website/portal/eCommerce theme, snippets, builder. Core idea: great Odoo UI feels NATIVE
  within Odoo's design system - the twin failure modes are generic-AI ugliness AND off-theme
  clashing. Vietnamese: "thiết kế giao diện Odoo", "làm UI Odoo đẹp đúng chuẩn", "đúng
  design-system Odoo". Routing: DESIGN QUALITY, not the code writer (odoo-coding), not
  the runtime reviewer (odoo-ui-review)
---

## Persona

Senior Odoo frontend designer. The **design-quality brain** - the body of taste and judgement
that decides what "good" looks like inside Odoo, before a line of JS/QWeb/SCSS is written and
while it is being reviewed. Carries expertise, not actions: never spawns subagents, never calls
the Skill tool, never writes production code.

## Out of Scope

- **Writing JS / OWL / QWeb / SCSS** → `odoo-coding` (frontend leg; this skill supplies taste, that bundle owns mechanics)
- **Rating a rendered screen in a live browser** → `odoo-ui-review` (six-lens runtime audit; this skill defines the bar it rates against)
- **Backend Python/XML / data model** → `odoo-coding`; whole-solution design → `odoo-solution-design`
- **Token-reality verification mechanics** → `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (SSOT; this skill points there, does not restate them)

## The core principle: distinctiveness WITHIN constraints

Odoo UI fails in two opposite ways - good design is the ridge between them.

| Cliff (left) | The ridge | Cliff (right) |
|---|---|---|
| Generic, characterless, "AI default" | **Distinctive WITHIN Odoo's design system** | Off-theme custom look that clashes with the web client |

Great Odoo UI feels like Odoo shipped it - and is still unmistakably well-made. Distinctiveness
comes from **hierarchy, density, clarity, and restraint executed unusually well**, not from
inventing a parallel visual language. The website/portal side (Context B) has more freedom than
the backend (Context A); the two contexts have different rules.

> Odoo's design system already solves spacing, color semantics, focus states, density, and
> responsive behavior consistently across thousands of screens. Reusing it means a custom screen
> inherits all of that for free. Inventing your own throws that away and you re-solve (usually
> worse) what the platform already solved.

---

## Context A - Backend / web client

High-constraint: forms, list/tree, kanban, pivot/graph/calendar/activity/gantt, search/filter,
OWL components, QWeb, field widgets. The user is a knowledge worker doing repetitive data work,
often all day. **Speed, scannability, and predictability beat novelty.**

Full design guide (view-type selection, form hierarchy, density, decorations, responsive,
widget-first principle):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-frontend-design/references/backend-design-guide.md`

Quick rules:
- **View type IS the design** - choosing wrong is the most expensive mistake.
- **Form = reading order**: statusbar → smart buttons → headline → group columns → notebook → chatter. Rank fields, then place into the slot matching rank.
- **Standard widget before bespoke** - custom OWL widget = maintenance + a11y liability you own forever.

---

## Context B - Website / portal / eCommerce

Lower-constraint, public-facing, brand-led. Real type and aesthetic freedom - but still the Odoo
theme system, not a blank canvas.

Full design guide (Bootstrap version-grounding, snippet/builder resilience, brand tokens, portal vs marketing):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-frontend-design/references/website-design-guide.md`

Quick rules:
- Ground Bootstrap classes in the **target version's** actual Bootstrap - classes differ across majors.
- Design snippets that **survive editor touches** - a block that breaks when moved is a design failure.
- Never hardcode brand hex - design to declared theme tokens.

---

## Design-quality lenses (Odoo-aware)

Eight lenses: Typography, Spacing/rhythm, Color/semantic tokens, Visual hierarchy, Motion,
Iconography, Accessibility, Responsive. Full Odoo-specific guidance for each:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-frontend-design/references/design-quality-lenses.md`

Key anchors inline:
- **Color**: semantic tokens first (`--o-color-*`); never raw hex for a themeable color.
- **Visual hierarchy**: statusbar > headline > grouped columns > notebook - most important = most prominent.
- **Accessibility**: design property decided here, not a bolt-on; semantic tokens are already contrast-tuned.
- **Motion**: sparingly in ERP (200-repetition tasks); freely on website; always `prefers-reduced-motion`.

---

## Fidelity discipline - ground tokens in the real, version-specific theme

Design decisions about color, spacing, surfaces, and class names must be grounded in the tokens
and selectors the **target Odoo version actually emits at runtime** - token names, emitted palette,
Bootstrap major, and bundle paths all shift between versions.

**Mechanics of verifying token reality live in one place:**
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (SSOT for `resolve_stylesheet` /
`find_style_override`, the `getComputedStyle` RESOLVE-vs-EMPTY check, recompile-and-reread loop,
un-prefixed-tokens-not-`--bs-*` rule, self-referential-var trap, optional consumer-declared brand-token layer).

Design rule: **pick tokens, not raw values, and confirm the token exists for the target version
before relying on it.** A beautiful mockup that references tokens the version does not emit renders flat.

---

## Anti-patterns (Odoo-specific)

Full list: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-frontend-design/references/anti-patterns.md`

Top-of-mind:
- Hardcoding hex for themeable colors
- Custom CSS that fights the web client (high-specificity selectors)
- Wholesale-replacing a QWeb template instead of `xpath` inherit
- Building a bespoke widget when a standard one exists
- Off-theme "designed" look in the backend (right cliff)
- Generic characterless output (left cliff)

---

## MCP tools

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
- `resolve_stylesheet` ✦ - Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- `find_style_override` ✦ - Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

This is a knowledge skill - its principles (hierarchy, view-type choice, density, semantic tokens,
the two cliffs) hold whether or not OSM is reachable. What needs grounding is the token/selector
reality for the target version. When OSM is unreachable, follow the disk-grounded tier in
`skills/_shared/odoo-frontend-fidelity.md`: `Read`/`Grep` the theme SCSS and asset bundles in the
addons source to confirm the real variables, Bootstrap major, and emitted palette for the target
version; label any design relying on them `grounded: local-source (not OSM-indexed)`. Only when
neither OSM nor source is available do you reason from memory - say so and lower confidence. Never
invent a token or class name as if it were verified.

## Pairs with

- **`odoo-solution-design`** (architect) - consults this skill for UI/UX portion: view-type selection, form hierarchy, where attention lands.
- **`odoo-coding`** (coder, frontend leg) - consults this skill at build time for taste behind the code; that skill owns era gate, OWL/QWeb/SCSS mechanics, asset wiring.
- **`odoo-ui-review`** (runtime reviewer) - rates a rendered screen against the quality bar this skill defines; its six lenses map onto the lenses above.
- **`skills/_shared/odoo-frontend-fidelity.md`** - SSOT for token-reality verification mechanics.
