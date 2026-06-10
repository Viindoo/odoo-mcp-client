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

Senior Odoo frontend designer. This skill is the **design-quality brain** - the body of taste
and judgement that decides what "good" looks like inside Odoo, before a line of JS/QWeb/SCSS is
written and while it is being reviewed. It carries expertise, not actions: it never spawns
subagents, never calls the Skill tool, never writes production code.

## Out of Scope

- **Writing the JS / OWL / QWeb / SCSS** → `odoo-coding` (its frontend leg; this skill supplies the taste, that bundle owns the mechanics)
- **Rating a rendered screen in a live browser** → `odoo-ui-review` (six-lens runtime audit; this skill defines the bar it rates against)
- **Backend Python/XML / data model** → `odoo-coding`; whole-solution design → `odoo-solution-design`
- **Token-reality verification mechanics** (resolve_stylesheet / computed-style checks) → these live in `skills/_shared/odoo-frontend-fidelity.md` (SSOT); this skill points there, it does not restate them

## The core principle: distinctiveness WITHIN constraints

Odoo UI fails in two opposite ways, and good design is the ridge between them.

**Cliff 1 - generic, characterless output:** timid palette, default font, no hierarchy, no point
of view. The fix is the usual one - bold direction, deliberate typography, real hierarchy.

**Cliff 2 - off-theme clashing (the more common one here):** a bespoke "designed" look bolted
onto the web client (custom fonts, custom shadows, hand-picked hex, a grid that ignores Odoo's
spacing) reads as broken, not bold. It fights the surrounding ERP chrome, breaks on the next Odoo
upgrade, and throws away years of usability work baked into Odoo's own components.

So the Odoo design quality bar is a narrow ridge between two cliffs:

| Cliff (left) | The ridge | Cliff (right) |
|---|---|---|
| Generic, characterless, "AI default" | **Distinctive WITHIN Odoo's design system** | Off-theme custom look that clashes with the web client |

Great Odoo UI feels like Odoo shipped it - and is still unmistakably well-made. Distinctiveness
comes from **hierarchy, density, clarity, and restraint executed unusually well**, not from
inventing a parallel visual language. The freedom you have is much wider on the website/portal
side (Context B) than inside the backend web client (Context A) - so the two contexts have
different rules, treated separately below.

> **Why constraints raise quality, not lower it.** Odoo's design system already solves spacing,
> color semantics, focus states, density and responsive behavior consistently across thousands
> of screens. Reusing it means a custom screen inherits all of that for free and a user's
> learned muscle memory keeps working. Inventing your own throws that away and you re-solve
> (usually worse) what the platform already solved.

---

## Context A - Backend / web client (the ERP UI)

This is the high-constraint context: forms, list/tree, kanban, pivot/graph/calendar/activity/
gantt, search/filter, OWL components, QWeb, field widgets. The user is a knowledge worker doing
repetitive data work, often all day. **Speed, scannability and predictability beat novelty.**
The single most valuable thing you can do is get information hierarchy right.

### Pick the right view type first (the biggest design decision)

The view type IS the design. Choosing wrong is the most expensive mistake because no amount of
styling rescues the wrong container.

| Use | When the user's job is | Anti-pattern |
|---|---|---|
| **list/tree** | scan/compare many records, edit a column fast | a kanban of 500 records (unscannable) |
| **kanban** | triage by stage/status, visual pipeline, card-at-a-glance | a kanban with 15 fields per card (it is a cramped form) |
| **form** | read/edit one record deeply | cramming a dashboard into a form |
| **pivot/graph** | aggregate, find trends, slice by dimension | hand-built chart widget when pivot/graph already does it |
| **calendar/gantt** | time is the primary axis (scheduling, planning) | a date column in a list when the job is scheduling |
| **activity** | "what do I need to do on these records" | a custom to-do widget |

If the user describes an *action over many records*, lead with list or kanban and let the form
be the drill-in. Reserve the form for depth.

### Information hierarchy on a form

A form is a reading order, not a field dump. Odoo gives you specific structural slots - use each
for its intended rank:

- **Statusbar (top)** - the record's lifecycle and the primary forward action. The user's eye
  lands here first; keep the workflow buttons few and ordered by likelihood. Demote rare actions
  into a cog/`action` menu rather than lining up ten buttons.
- **Button box / smart buttons (top right)** - navigation to *related* records with a live
  count ("3 Invoices", "12 Tasks"). They are signposts, not actions; use them to expose related
  data instead of burying it in a tab. Give each a meaningful icon and a count - a smart button
  with no number is a wasted slot.
- **Title / headline fields** - the one or two fields that identify the record (name, partner),
  visually largest, above the columns.
- **Group columns** - related fields in two balanced `<group>` columns. Group by *meaning*
  (billing vs delivery, dates vs amounts), not by accident of field order. Uneven columns and
  twelve fields in one ungrouped block are the classic "looks like a database table" smell.
- **Notebook / tabs** - secondary and bulky detail (lines, notes, technical settings) moved
  off the first screen. Order tabs by frequency of use; the first tab is the one most people
  open. Do not hide primary fields behind a tab to make the top "look clean" - that trades
  tidiness for clicks.
- **Chatter (right or bottom)** - messaging, activities, followers, audit log. It is a known,
  consistent region; keep it where users expect it rather than relocating it.

The discipline: **what must the user see in the first second, what in the first scroll, what
only when they go looking?** Rank, then place into the slot that matches the rank.

### Density vs readability

ERP users value density - more rows visible means less scrolling - but density past the point of
scannability becomes noise. Respect Odoo's existing row height, padding and font scale rather
than compressing them; the defaults are tuned for all-day use. Add air through *grouping and
alignment*, not by inventing larger margins that desync from every other screen.

### Decorations, badges and empty states

- **`decoration-*` and widget badges** carry semantic color (success/warning/danger/info/muted)
  to make state scannable in a list or kanban - a red overdue row, a green done badge. Use the
  semantic mapping, never a raw color, so it tracks the theme and means the same thing
  everywhere. Color should *reinforce* a state that is also conveyed textually (for color-blind
  users), not be the only signal.
- **Empty states** are a design surface, not an oversight. A blank list or kanban is a chance to
  orient a new user - a short line plus the primary create action - instead of a void. Odoo
  supports this; design the empty state deliberately.

### Responsive behavior of the web client

The backend is used on laptops primarily but must survive narrow widths. The web client already
collapses groups, stacks columns and adapts the action bar. Design *with* that reflow - do not
pin fixed pixel widths that break it, and check that your hierarchy still reads when columns
stack (the top-ranked fields should still come first when linearised).

### Standard widget before bespoke widget

Odoo ships a deep field-widget library (many2one, many2many_tags, badge, priority, handle,
progressbar, monetary, image, statusbar, etc.). A standard widget brings keyboard support,
accessibility, i18n and theme fidelity for free. **Reach for a custom OWL widget only when no
standard one expresses the need** - a bespoke widget is a maintenance and a11y liability you now
own forever. (The coder enforces this; the design judgement starts here.)

---

## Context B - Website / portal / eCommerce frontend

Lower-constraint, public-facing, brand-led. A bold, distinctive, memorable aesthetic applies far
more directly here, because the audience is a prospect/customer, not an all-day operator. But it
is still **the Odoo theme system, not a blank canvas**:

- **Theme + Bootstrap, version-grounded.** Odoo website builds on a theme layer over Bootstrap,
  and **the Bootstrap major differs per Odoo release** - do not assume a version. Ground the
  grid, utility classes and breakpoints in the *target version's* actual Bootstrap (resolve via
  OSM/fidelity doc) rather than writing from memory; a class that exists in one Bootstrap major
  may be renamed or gone in another.
- **Snippets and the website builder.** Website content is assembled from snippets that
  non-technical editors then rearrange in the builder. Design components that *survive editing* -
  options the editor expects (color, spacing presets, background), content that reflows when a
  block is moved or duplicated. A pixel-perfect block that breaks the moment an editor touches it
  is a design failure, not a coding one.
- **Brand/theme tokens.** Use the theme's color palette and typography variables so the page
  inherits the site's identity and a theme switch propagates. Brand fidelity (does it match *our*
  brand) is the optional consumer-declared layer described in the fidelity doc - design to the
  declared tokens, never hardcode brand hex.
- **Portal vs marketing.** The portal (customer self-service: invoices, orders, tickets) leans
  back toward Context A discipline - clarity and task-completion over flourish - even though it
  uses the website stack. Match the register to the job.

---

## Design-quality lenses (Odoo-aware)

Each lens is a dimension of quality; what follows is the **Odoo-specific way to satisfy it well**.

- **Typography.** In the backend, do NOT swap in characterful display fonts - the web client has
  one type system and consistency is the feature; "distinctiveness" comes from hierarchy (size,
  weight, label vs value) within Odoo's scale, not from new fonts. On website/portal you have
  real type freedom - pair a distinctive display font with a readable body font, set via theme
  variables, never inline.
- **Spacing and rhythm.** Reuse Odoo's spacing scale (the `$spacers` / `$o-*` SCSS variables);
  consistent rhythm is what makes a screen feel native. Create breathing room by *grouping*, not
  by inventing one-off margins that desync from neighbouring screens.
- **Color and semantic tokens.** Color in Odoo is semantic first: primary, secondary,
  success/warning/danger/info, muted, the surface/border/text tokens, and the `--o-color-*`
  palette. Map meaning to a token; never pick a raw hex for a themeable color. This is also what
  keeps a screen on-theme across versions and brand switches.
- **Visual hierarchy.** The strongest tool you have in Odoo. Statusbar > headline > grouped
  columns > notebook detail; in a list, the identifying column + a semantic decoration; in a
  kanban, one clear title + at most a few supporting facts + a status color. Make the most
  important thing the most prominent thing, and demote the rest honestly.
- **Motion / transitions.** Sparingly in the ERP - a worker repeating an action 200 times wants
  instant feedback, not a 400ms animation each time. Use motion only where it aids comprehension
  (a panel sliding to show it came from somewhere, a subtle state transition). On website/portal,
  orchestrated reveals are welcome. Respect `prefers-reduced-motion` either way.
- **Iconography.** Use Odoo's bundled icon set (Font Awesome in current eras - confirm the set
  for the target version) so icons match weight and style across the app. A smart button, a tab,
  an action benefits from a meaningful icon; do not mix in a foreign icon library that looks
  alien beside the native ones.
- **Accessibility.** Sufficient contrast (the semantic tokens are tuned for it - another reason
  to use them), full keyboard operability (which standard widgets give you and a hand-rolled one
  often does not), correct ARIA roles/labels on custom OWL components, visible focus states, and
  not relying on color alone to convey state. a11y is a design property, decided here, not a
  bolt-on at review.
- **Responsive.** Design for reflow, not fixed widths; verify the hierarchy still reads when the
  layout linearises. Backend: trust the web client's adaptive behavior. Website: use the target
  version's Bootstrap breakpoints, grounded not assumed.

---

## Fidelity discipline - ground tokens in the real, version-specific theme

Design decisions about color, spacing, surfaces and class names must be grounded in the tokens
and selectors the **target Odoo version actually emits at runtime** - never invented from memory.
Token names, the emitted palette, the Bootstrap major and bundle paths all shift between
versions.

**The mechanics of verifying token reality live in one place - point there, do not restate them:**
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` is the SSOT for
`resolve_stylesheet` / `find_style_override`, the `getComputedStyle` RESOLVE-vs-EMPTY check, the
recompile-and-reread loop, the un-prefixed-tokens-not-`--bs-*` rule, the self-referential-var
trap, and the optional consumer-declared brand-token layer.

The design rule that flows from it: **pick tokens, not raw values, and confirm the token exists
for the target version before relying on it.** A beautiful mockup that references tokens the
version does not emit renders flat - the fidelity doc's worked example is exactly this bug class.

---

## Anti-patterns (Odoo-specific)

- **Hardcoding hex / rgb()** for a themeable color instead of a semantic SCSS/CSS variable -
  breaks theme and brand switches, drifts off-palette.
- **Custom CSS that fights the web client** - overriding core spacing/typography globally,
  high-specificity selectors that win battles against Odoo's own styles and lose the war on the
  next upgrade.
- **Wholesale-replacing a core QWeb template** instead of an `xpath` inherit - you fork the
  template and inherit none of its future fixes; surgical `xpath` position="..." keeps you on the
  upgrade path.
- **Non-responsive fixed widths** that break the web client's reflow or the website grid.
- **Ignoring RTL / i18n** - hardcoded left/right instead of logical start/end, layouts that
  assume Latin text width, untranslatable inline strings. Odoo is multilingual by default.
- **Building a bespoke widget when a standard one exists** - you lose keyboard, a11y, i18n and
  theme fidelity and inherit perpetual maintenance.
- **Off-theme "designed" look in the backend** - custom fonts/shadows/grid that read as broken
  beside the ERP chrome (the right-hand cliff).
- **Generic characterless output** - timid palette, default font, no hierarchy, no point of view
  (the left-hand cliff). Both cliffs are failures.
- **Form-as-database-dump** - twelve ungrouped fields, no notebook, no statusbar ranking; no
  reading order.
- **Kanban-as-cramped-form** - too many fields per card so nothing is scannable at a glance.

---

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `resolve_stylesheet` ✦ — Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- `find_style_override` ✦ — Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

This is a knowledge skill — its principles (hierarchy, view-type choice, density, semantic
tokens, the two cliffs) hold whether or not OSM is reachable. What needs grounding is the
*token/selector reality* for the target version. When OSM is unreachable, follow the disk-grounded
tier in `skills/_shared/odoo-frontend-fidelity.md`: `Read`/`Grep` the theme SCSS and asset bundles
in the addons source to confirm the real variables, the Bootstrap major, and the emitted palette
for the target version, and label any design that relies on them `grounded: local-source (not
OSM-indexed)`. Only when neither OSM nor the source is available do you reason from memory — say so
and lower confidence. Never invent a token or class name as if it were verified.

## Pairs with

- **`odoo-solution-design`** (architect) - consults this skill for the UI/UX portion of a
  solution: view-type selection, form hierarchy, where attention lands.
- **`odoo-coding`** (coder, frontend leg) - consults this skill at build time for the taste behind
  the code it writes; that skill owns the era gate, OWL/QWeb/SCSS mechanics and asset wiring.
- **`odoo-ui-review`** (runtime reviewer) - rates a rendered screen against the quality bar this
  skill defines; its six lenses map onto the lenses above.
- **`skills/_shared/odoo-frontend-fidelity.md`** - the SSOT for token-reality verification
  mechanics this skill points to for all grounding.
