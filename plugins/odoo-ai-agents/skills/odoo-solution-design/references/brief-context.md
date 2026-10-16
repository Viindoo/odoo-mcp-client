# odoo-solution-design - the three deliverables (reference)

What the architect hands back, so this skill can gate it.

- **SRS** (`<SHARE_DIR>/designs/<slug>-<date>-srs.md`): the WHAT, for the human approver and for
  every later step - the Domain line, the roles and their jobs, scope, cross-function
  interactions, non-functional requirements, demo data, and the acceptance criteria with expected
  values (the acceptance oracle). Written only when `SRS_REQUIRED: yes`; otherwise its content is
  the header of the design.
- **Recon** (`<SHARE_DIR>/recon/<slug>-<date>/recon.md`, by `odoo-impact-recon`): the dependency,
  dependent, sibling, existing-feature and existing-test facts, one row each with its source.
- **Design** (`<SHARE_DIR>/designs/<slug>-<date>.md`): the HOW. Light (one `## Nodes` block) when
  the effort is Standard or Config and recon raised no flag; full (approach, data model,
  override strategy, module structure, sequencing, test outline, risks, grounding evidence)
  otherwise. Every node carries `build_tier_hint` with the 5.1 checklist and the 5.2 answer.

The architect's own body owns the templates and the grounding steps; this file only names what
crosses the gate.
