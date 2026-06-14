# Version Diff Examples

**Example 1:**
Prompt: "what changed between Odoo 16 and 17 for module developers?"
Output: Categorized diff with Added/Removed/Deprecated/Changed sections, migration notes for
each breaking change, feature highlights, developer sprint plan.

**Example 2:**
Prompt: "compare API changes between Odoo 12 and 16, we need to migrate"
Output: Cross-era diff (v12→v13: `@api.multi` removal + OWL introduced; v13→v14: OWL becomes
primary + `web.Widget` deprecated; v14→v16: OWL 2.0 + `web.Widget` removed). Era migration
section prominent. Complexity: Very High. Sprint plan with phased migration approach.
