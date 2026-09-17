# odoo-solution-design - the TDD deliverable (reference)

What the architect hands back, so this skill can gate it. The design doc is a **contract for the
coders**, not prose. Its fixed eight sections - Intent & Business Value (solution-level intent /
purpose / expected outcomes / business value / user impact, plus a per-module table covering
BOTH new modules and existing modules being refactored, modified, or optimized), Approach
(inheritance axis + new-vs-extend, ADR-style with rejected alternatives), Data model, Override
strategy, Module structure, Sequencing, Test strategy outline (behavior-first, feeds
`odoo-test-writing` / `odoo-qa-suite`), and Risks - are specified in
`agents/odoo-solution-architect.md` (Round 4 is the SSOT for the doc template). The Intent &
Business Value section exists for the HUMAN approver: a design whose purpose and value cannot be
stated per module is not ready to gate.

How the architect grounds and validates each section (per-round OSM calls, the frontend
knowledge-source routing, and the per-mode master/child/consistency/reconcile dispatch shape) is
owned by `agents/odoo-solution-architect.md` - not restated here: § Round 0-3 (grounding + override
+ validation), § Round 2 (Tool routing per design facet - frontend), § Dispatch modes, § Reconcile
mode.
