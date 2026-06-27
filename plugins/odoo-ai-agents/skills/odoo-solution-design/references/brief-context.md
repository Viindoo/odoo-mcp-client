# odoo-solution-design - Brief Context (reference)

The design doc is a **contract for the coders**, not prose: the architect grounds every
model/field/method/edition claim via OSM and reuses indexed patterns before proposing any
hand-written structure. Its fixed eight sections - Intent & Business Value (solution-level intent /
purpose / expected outcomes / business value / user impact, plus a per-module table covering
BOTH new modules and existing modules being refactored, modified, or optimized), Approach
(inheritance axis + new-vs-extend, ADR-style with rejected alternatives), Data model, Override
strategy, Module structure, Sequencing, Test strategy outline (behavior-first, feeds
`odoo-test-writing` / `odoo-qa-suite`), and Risks - are specified in
`agents/odoo-solution-architect.md` (Round 4 is the SSOT for the doc template). The Intent &
Business Value section exists for the HUMAN approver: a design whose purpose and value cannot be
stated per module is not ready to gate.

Key failure modes the design prevents (each surfaces only at review/runtime if skipped): wrong
inheritance axis, override at the wrong level / wrong `super()` position, stored-vs-computed
mistakes, conflicts with existing overrides, ad-hoc `depends` causing circular module deps.

**Full-stack designs (frontend portion).** When the change spans the frontend (a widget, OWL
component, QWeb override, or SCSS/theme work), the architect pulls in two knowledge sources: the
**design-quality** skill - **invoke skill `odoo-frontend-design` using skill tool** (it is a leaf
knowledge skill; loading injects expertise and spawns nothing) - for what a *good* Odoo UI is
(view-type choice, form hierarchy, density, semantic tokens, website/portal rules); and the
**fidelity** contract `skills/_shared/odoo-frontend-fidelity.md` (a `_shared` doc it Reads) so the
design names real design tokens / style origins for the target version via `resolve_stylesheet` /
`find_style_override` rather than inventing selectors or colors. The frontend half of the design
is then consumed by `odoo-coding` (its frontend leg), which loads the same two sources when it
writes the JS/OWL/SCSS.

**Master vs child architect brief (master-child mode only).** The same architect agent is
dispatched at different altitudes:
- `MODE: master` - cross-module altitude. Produces §10 shared-symbol registry + dep direction
  decisions. Does NOT design module internals. Master = hard constraint layer.
- `MODE: child` - single-module altitude. Standard 8-section TDD for one module. Must cite
  master §10 for every cross-module symbol. Child = coder's primary spec (`DESIGN_DOC`).
- `MODE: consistency` - reads CONTRACT SUBSET of each child (§1, §9, cross-module symbols)
  + master §10; reconciles seams; emits conflict-list. Full brief template:
  `agents/odoo-solution-architect.md`.
