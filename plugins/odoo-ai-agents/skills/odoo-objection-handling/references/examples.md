# Objection Handling - Worked Examples

**Example 1:**
Prompt: "handle the objection that Odoo doesn't support complex approval workflows"
Output: Counter-evidence citing `approval` module (EE) or `mail.activity.mixin` pattern (CE
extension); code example of multi-level approval; talking points; verbatim response.

**Example 2:**
Prompt: "customer says Odoo doesn't have accounting standards compliance for their region"
Output: Counter: specialized localization modules or custom extensions exist;
`model_inspect(model='account.move', method='fields', odoo_version='<version>')` shows compliance-specific fields; verbatim
response with region-appropriate solution.
