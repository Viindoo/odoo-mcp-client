---
name: odoo-frontend-design
argument-hint: "[UI/screen to design]"
description: >-
  Native-looking Odoo UI design guidance for other skills; writes no code
---

## Role

Screen design for Odoo: what a screen holds, in which view type, in what order, for which role.
Serves a designer or coder who has a screen to decide. Carries judgement, not actions: launches no
agent, invokes no skill, writes no production code.

The binding rules are `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md`; this skill is how to
decide within them. Its bar is `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md`
§ 0: a screen a user with low IT skills reads at once, behaving as the same screen does in every
core app.

## Out of Scope

- **Writing views, templates, JS or SCSS** -> `odoo-coding`
- **Rating a rendered screen in a live browser** -> `odoo-ui-review`
- **Data model, overrides, whole-solution design** -> `odoo-solution-design`

## Native first

In the backend, consistency with core is the feature. A custom screen that looks and behaves like
core inherits its spacing, colour meaning, focus states, density and responsive behaviour, and a
theme restyles it with the rest. Quality shows in hierarchy, density and clarity, never in a look
of the module's own. Only the website and portal side is brand-led, and it still builds on the
theme of the site.

## Deciding a screen

1. **The job.** Name the role, what it does on this screen and how often. A screen that serves
   two jobs is two views.
2. **The view type.** It is the design; no styling rescues the wrong one. The table and the form
   slots are in `references/backend-design-guide.md`; a website or portal page follows
   `references/website-design-guide.md`.
3. **The rank.** List what the user must see in the first second, on the first scroll, and only
   when looking for it. Place each item in the slot of its rank, in the order the user enters
   data.
4. **The phone.** Read the arch top to bottom as one column: that is the phone screen. Its first
   screenful holds the first rank.
5. **Core first.** For every element name the core widget, component or class that provides it
   in the target series. An element with no core counterpart is a cost the module owns: keep it
   only when the job cannot be done without it.

## Mockup

The decisions above go into the design's `## Screens` section, one block per screen, and each
screen gets a mockup or a placement note the approver, the coder and the reviewer all look at:
`references/mockup.md` says which of the two, how to make it and where it is kept. A mockup the
project already keeps under `<SHARE_DIR>/mockups/` is input to it, never its output location.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `resolve_stylesheet` ✦ - Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- `find_style_override` ✦ - Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

The steps above hold without OSM. What needs grounding is which widgets, classes and variables
the target series has: OSM unreachable, read them in the series' `web` addon on disk and label
the design `grounded: local-source`. With neither, say so and name no class or variable as if it
were verified.
