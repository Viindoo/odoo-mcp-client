# Website / Portal / eCommerce Design Guide — Context B

Lower-constraint, public-facing, brand-led. A bold, distinctive aesthetic applies far more directly here because the audience is a prospect/customer, not an all-day operator. Still the Odoo theme system, not a blank canvas.

## Theme + Bootstrap, version-grounded

Odoo website builds on a theme layer over Bootstrap, and the Bootstrap major differs per Odoo release. Do not assume a version — ground the grid, utility classes, and breakpoints in the target version's actual Bootstrap (resolve via OSM/fidelity doc). A class that exists in one Bootstrap major may be renamed or gone in another.

## Snippets and the website builder

Website content is assembled from snippets that non-technical editors rearrange in the builder. Design components that survive editing: options the editor expects (color, spacing presets, background), content that reflows when a block is moved or duplicated. A pixel-perfect block that breaks the moment an editor touches it is a design failure, not a coding one.

## Brand/theme tokens

Use the theme's color palette and typography variables so the page inherits the site's identity and a theme switch propagates. Never hardcode brand hex — design to the declared tokens. Brand fidelity is the optional consumer-declared layer described in the fidelity doc.

## Portal vs marketing

The portal (customer self-service: invoices, orders, tickets) leans back toward Context A discipline — clarity and task-completion over flourish — even though it uses the website stack. Match the register to the job.
