<!-- SSOT snippet. The single source for the completion-status split between a skill whose
     PRIMARY deliverable is complete WITHOUT a live Odoo instance (static analysis/review) and
     a skill whose deliverable REQUIRES a live render/execution. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md instead of re-explaining
     the split in each SKILL.md. -->

# Instance-optional vs instance-required completion

When a live Odoo instance/browser is unreachable, which terminal status a skill emits depends
on whether the instance is OPTIONAL or REQUIRED for its PRIMARY deliverable - not on a
per-skill judgment call:

- **Instance-OPTIONAL** (the PRIMARY deliverable is complete WITHOUT an instance - static
  source/code review). Finish the static deliverable, mark the instance-gated dimension
  `DONE_WITH_CONCERNS`, and emit an OPT-IN `next: odoo-acceptance` (L2, human-gated)
  recommending a live verification pass rather than blocking. Example: `odoo-code-review` -
  Python/XML/OWL source review completes fully from static analysis; only the rendered-UI
  dimension needs a live render, so that one dimension is flagged while the overall review
  still ships (`odoo-code-review/SKILL.md` § Phase A.5).
- **Instance-REQUIRED** (the deliverable REQUIRES a live render/execution to exist at all).
  Emit `status: NEEDS_NEXT` with `next: odoo-instance` - there is nothing to ship without the
  instance, so the run stops and hands off provisioning instead of shipping a partial
  artifact. Examples: `odoo-ui-review` (a rated screenshot IS the deliverable),
  `odoo-test-writing` (Round 5 suite execution), `odoo-doc-illustration` (screen captures),
  `odoo-acceptance` (live oracle execution).

Rule of thumb: if the skill can finish with a caveat, it is instance-optional
(`DONE_WITH_CONCERNS` + opt-in `next: odoo-acceptance`); if there is nothing to finish without
the instance, it is instance-required (`NEEDS_NEXT: odoo-instance`).
