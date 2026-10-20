# Version Diff Examples

**Example 1:**
Prompt: "what changed between Odoo <from> and <to> for module developers?"
Output: Categorized diff with Added/Removed/Deprecated/Changed sections, modernisation notes for
each breaking change, feature highlights, developer sprint plan.

**Example 2:**
Prompt: "compare API changes between Odoo <from> and <to>, we need to modernise our code"
Output: Cross-era diff (one entry per era jump listed in `references/breaking-points-history.md`,
`snippets/odoo-version-pivots.md` and `snippets/odoo-era-boundaries.md`, e.g. the `@api.multi`
removal, a frontend era change, the OWL library major). Era modernisation
section prominent. Complexity: Very High. Sprint plan with phased modernisation approach.
