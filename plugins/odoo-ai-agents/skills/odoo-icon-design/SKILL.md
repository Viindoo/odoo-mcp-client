---
name: odoo-icon-design
argument-hint: "[module] [version]"
description: >-
  Designs a module's icon and store cover
---

## Role

Designer of a module's image assets for Odoo, through `odoo-icon-designer`:

- **The app icon**: measured against the target series' own core app icons (size, mode, tile or
  flat style), composed as a brand-aware SVG with a purpose-drawn glyph, rasterized to
  `static/description/icon.png` and gated against that family.
- **The store cover**: the one image a store shows for the module, a product cover in the
  vendor's brand at 2:1, written to `static/description/main_screenshot.png` as the only entry of
  the manifest `images` list.

Works from static source; a live instance is used only when the caller hands one, to see the icon
among the installed apps. OSM is the primary source for the module's category, the version
grounding and the icon mechanism; the on-disk descriptor (`__manifest__.py`, or `__openerp__.py`
where the module has it) and the checkout are the fallback. Both assets are image files, not
rendered Odoo screens: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md` does not govern them.

## Out of Scope

- **Rating a rendered screen** -> `odoo-ui-review`
- **A screenshot of a live screen**, for a guide or a store page -> `odoo-doc-illustration`
- **An in-UI Font Awesome glyph class in a view or button** -> `odoo-coding` or
  `odoo-frontend-design`
- **A website favicon** -> `odoo-coding`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

## Agent invocation

Fill the caller-side skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read it by path) plus the icon designer's family delta. The files are git-tracked
writes: resolve `WORKTREE_PATH` first - the worktree already in scope, else one provisioned
through `git-toolkit:git-ops`, never the principal checkout. Resolve the vendor's colours, logo
and font once per `${CLAUDE_PLUGIN_ROOT}/snippets/vendor-facts.md` and pass what it yields.
Launch `odoo-icon-designer` at the `model` of
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection (designing an
image asset) with:

```
MODE: <icon | cover>
MODULE: <module name>
MODULE_PATH: <absolute path of the module directory>
WORKTREE_PATH: <abs path resolved above>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
VERSION: <Odoo series, or omit to let the agent resolve it>
BRIEF: <icon: palette or glyph hints; omit for the agent's own resolution>
BRAND: <cover: the vendor's palette by role and its logo, in the form of vendor-facts.md; omit when none resolved>
FONT_FILE: <cover: the author profile's font_file; omit when none>
INSTANCE_HANDLE: <icon: a live instance with the module installed, when the run holds one; the agent never releases it>
```

## Standalone-first fallback

OSM unreachable: the agent works from the descriptor on disk and says so. No SVG rasterizer on
the machine: the SVG ships alone with the install guidance and the agent returns `NEEDS_CONTEXT`.

## Verify then commit

Every file the agent reports exists under `WORKTREE_PATH`. Re-run the gate yourself:

- icon: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/icon_gate.py check <icon.png> --facts <the
  facts file the agent reported>` prints `ICON_GATE=PASS` and `CONSISTENCY=ok`; Read the
  `CONTACT_SHEET` and the `PREVIEW_ZOOM` images - an icon that stands out among the core icons, or
  a last cold read that does not name the module's purpose, goes back to the agent;
- cover: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/icon_gate.py cover <main_screenshot.png>`
  prints `COVER_GATE=PASS`; Read its `PREVIEW` - a product name that does not read at that width
  goes back to the agent.

`FAIL` or `outlier` goes back to the agent; `CANNOT-VERIFY` is reported as unverified, never as a
pass. Then commit the files and the manifest edit through `git-toolkit:git-ops`
(`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next).
