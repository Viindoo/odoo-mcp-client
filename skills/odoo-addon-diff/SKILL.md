# odoo-addon-diff

**Persona:** Marketer
**Triggers:** compare Odoo CE vs EE features, what modules are in Enterprise edition, addon comparison for proposal, so sánh CE và EE, module nào chỉ có trong Enterprise
**Tools used:** `check_module_exists`, `resolve_model`

## Instructions

This skill produces a clear comparison between Odoo Community Edition (CE) and Enterprise Edition (EE) for a given business domain or feature set. It is designed for marketers and sales engineers who need accurate, evidence-based content for proposals, website pages, or competitive positioning.

For each module or feature in the comparison list, call `check_module_exists` to determine its edition availability. When a module exists in both editions but with different capabilities, call `resolve_model` on the relevant models to identify field-level differences (e.g., EE adds `forecast_date`, `analytic_account_id` etc.). Avoid stating features as EE-only without verification — incorrect claims damage trust.

Present the comparison as a clean side-by-side table that a non-technical decision-maker can evaluate. Group features by business domain (Sales, Accounting, Manufacturing, etc.). For each EE-only feature, include a brief business value note explaining why it matters. Avoid technical field names in the main table — translate to business language.

## Output format

## Odoo CE vs EE Comparison

**Domain:** <business domain>
**Version:** <Odoo version>

| Feature | CE | EE | Business value (EE advantage) |
|---------|----|----|-------------------------------|
| ...     | ✓/✗/Partial | ✓/✗ | ...                |

### EE-only highlights
- **<Feature>**: <why it matters for this type of business>
- **<Feature>**: <why it matters>

### CE strengths
- <what CE does well that EE also includes>

### Upgrade recommendation
<1 sentence: under what conditions should this client consider EE?>

## Example invocation

User: "compare CE vs EE for a manufacturing client considering Odoo"
Expected output: Side-by-side comparison table covering Manufacturing, Inventory, and MRP features, with EE-only highlights and a tailored upgrade recommendation.
