# Design-Quality Lenses (Odoo-Aware)

Each lens is a dimension of quality; what follows is the Odoo-specific way to satisfy it well.

## Typography
Backend: do NOT swap in characterful display fonts — the web client has one type system and consistency is the feature. Distinctiveness comes from hierarchy (size, weight, label vs value) within Odoo's scale, not new fonts. Website/portal: real type freedom — pair a distinctive display font with a readable body font, set via theme variables, never inline.

## Spacing and rhythm
Reuse Odoo's spacing scale (`$spacers` / `$o-*` SCSS variables). Consistent rhythm is what makes a screen feel native. Create breathing room by grouping, not by inventing one-off margins that desync from neighbouring screens.

## Color and semantic tokens
Color in Odoo is semantic first: primary, secondary, success/warning/danger/info, muted, surface/border/text tokens, `--o-color-*` palette. Map meaning to a token; never pick a raw hex for a themeable color. This keeps a screen on-theme across versions and brand switches.

## Visual hierarchy
The strongest tool in Odoo. Statusbar > headline > grouped columns > notebook detail; in a list, the identifying column + a semantic decoration; in a kanban, one clear title + at most a few supporting facts + a status color. Make the most important thing the most prominent thing, demote the rest honestly.

## Motion / transitions
Sparingly in the ERP — a worker repeating an action 200 times wants instant feedback, not a 400ms animation each time. Use motion only where it aids comprehension (panel sliding, subtle state transition). On website/portal, orchestrated reveals are welcome. Respect `prefers-reduced-motion` either way.

## Iconography
Use Odoo's bundled icon set (Font Awesome in current eras — confirm the set for the target version) so icons match weight and style across the app. Do not mix in a foreign icon library that looks alien beside native ones.

## Accessibility
Sufficient contrast (semantic tokens are tuned for it), full keyboard operability (standard widgets give this, hand-rolled often do not), correct ARIA roles/labels on custom OWL components, visible focus states, no color-only state signals. a11y is a design property, decided here, not a bolt-on at review.

## Responsive
Design for reflow, not fixed widths; verify hierarchy still reads when layout linearises. Backend: trust the web client's adaptive behavior. Website: use the target version's Bootstrap breakpoints, grounded not assumed.
