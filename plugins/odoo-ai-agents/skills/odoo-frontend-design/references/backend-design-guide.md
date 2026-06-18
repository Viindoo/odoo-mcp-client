# Backend Design Guide - Context A (Web Client)

## Pick the right view type first

The view type IS the design. Choosing wrong is the most expensive mistake - no styling rescues the wrong container.

| Use | When the user's job is | Anti-pattern |
|---|---|---|
| **list/tree** | scan/compare many records, edit a column fast | kanban of 500 records (unscannable) |
| **kanban** | triage by stage/status, visual pipeline, card-at-a-glance | kanban with 15 fields per card (cramped form) |
| **form** | read/edit one record deeply | cramming a dashboard into a form |
| **pivot/graph** | aggregate, find trends, slice by dimension | hand-built chart when pivot/graph already does it |
| **calendar/gantt** | time is the primary axis (scheduling, planning) | date column in list when job is scheduling |
| **activity** | "what do I need to do on these records" | custom to-do widget |

If the user describes an action over many records, lead with list or kanban; reserve form for depth.

## Information hierarchy on a form

A form is a reading order, not a field dump. Use each structural slot for its intended rank:

- **Statusbar (top)** - lifecycle + primary forward action. Keep workflow buttons few and ordered by likelihood; demote rare actions into a cog/action menu.
- **Button box / smart buttons (top right)** - navigation to related records with a live count. Signposts, not actions; give each a meaningful icon and count (a button with no number is a wasted slot).
- **Title / headline fields** - the one or two fields identifying the record (name, partner), visually largest, above columns.
- **Group columns** - related fields in two balanced `<group>` columns. Group by meaning (billing vs delivery, dates vs amounts), not field order. Uneven columns + twelve ungrouped fields = database-table smell.
- **Notebook / tabs** - secondary and bulky detail (lines, notes, technical settings). Order by frequency of use. Do not hide primary fields behind a tab to make the top "look clean" - that trades tidiness for clicks.
- **Chatter (right or bottom)** - messaging, activities, followers, audit log. Keep it where users expect it.

The discipline: what must the user see in the first second? First scroll? Only when going looking? Rank, then place into the matching slot.

## Density vs readability

ERP users value density but density past scannability becomes noise. Respect Odoo's existing row height, padding, and font scale - defaults are tuned for all-day use. Add air through grouping and alignment, not one-off margins that desync from every other screen.

## Decorations, badges, empty states

- **`decoration-*` and widget badges** carry semantic color (success/warning/danger/info/muted) to make state scannable. Use the semantic mapping, never a raw color. Color must reinforce a state also conveyed textually (for color-blind users) - never be the only signal.
- **Empty states** are a design surface: a short line plus the primary create action orients new users instead of leaving a void.

## Responsive behavior

The backend collapses groups, stacks columns, and adapts the action bar automatically. Design with that reflow - no pinned fixed pixel widths. Verify hierarchy still reads when columns stack (top-ranked fields come first when linearised).

## Standard widget before bespoke widget

Odoo ships a deep field-widget library (many2one, many2many_tags, badge, priority, handle, progressbar, monetary, image, statusbar, etc.). A standard widget brings keyboard support, accessibility, i18n, and theme fidelity for free. Reach for a custom OWL widget only when no standard one expresses the need - a bespoke widget is a maintenance and a11y liability you own forever.
