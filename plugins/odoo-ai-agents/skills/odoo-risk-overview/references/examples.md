# Risk Overview Examples

**Example 1:**
Prompt: "give me a risk overview of our Odoo customization before we upgrade to Odoo <target>"
Output: Table of custom modules with deprecated API counts, blast radius for critical fields,
upgrade complexity note (a same-era jump = Low multiplier), recommended action.

**Example 2:**
Prompt: "risk overview before we upgrade our system from version <from> to <to>"
Output: Risk analysis for distribution-maintained vs custom modules, identify modules needing
deep modernisation work (the `@api.multi` removal, a frontend era change and the OWL library major, per
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` and
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`),
estimate timeline and recommended action in business language.
