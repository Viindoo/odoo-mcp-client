# Risk Overview Examples

**Example 1:**
Prompt: "give me a risk overview of our Odoo customization before we upgrade to v17"
Output: Table of custom modules with deprecated API counts, blast radius for critical fields,
migration complexity note (e.g. from v16 = Low multiplier), recommended action.

**Example 2:**
Prompt: "risk overview before we upgrade our system from version 14 to 17"
Output: Risk analysis for distribution-maintained vs custom modules, identify modules needing
deep migration work (v13 `@api.multi` removal + v14 OWL-becomes-primary + v15 OWL 2.0),
estimate timeline and recommended action in business language.
