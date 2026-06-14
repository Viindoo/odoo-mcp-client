# Odoo Frontend Anti-Patterns

- **Hardcoding hex / rgb()** for a themeable color instead of a semantic SCSS/CSS variable — breaks theme and brand switches, drifts off-palette.
- **Custom CSS that fights the web client** — overriding core spacing/typography globally, high-specificity selectors that win battles against Odoo's own styles and lose the war on the next upgrade.
- **Wholesale-replacing a core QWeb template** instead of an `xpath` inherit — you fork the template and inherit none of its future fixes; surgical `xpath position="..."` keeps you on the upgrade path.
- **Non-responsive fixed widths** that break the web client's reflow or the website grid.
- **Ignoring RTL / i18n** — hardcoded left/right instead of logical start/end, layouts that assume Latin text width, untranslatable inline strings. Odoo is multilingual by default.
- **Building a bespoke widget when a standard one exists** — you lose keyboard, a11y, i18n, and theme fidelity and inherit perpetual maintenance.
- **Off-theme "designed" look in the backend** — custom fonts/shadows/grid that read as broken beside the ERP chrome (right-hand cliff).
- **Generic characterless output** — timid palette, default font, no hierarchy, no point of view (left-hand cliff). Both cliffs are failures.
- **Form-as-database-dump** — twelve ungrouped fields, no notebook, no statusbar ranking; no reading order.
- **Kanban-as-cramped-form** — too many fields per card so nothing is scannable at a glance.
