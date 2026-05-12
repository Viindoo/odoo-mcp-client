# odoo-risk-overview

**Persona:** CEO
**Triggers:** give me a risk overview of our Odoo customization, what's the upgrade risk for our system, business risk report for Odoo changes, tổng quan rủi ro customization Odoo, báo cáo rủi ro upgrade
**Tools used:** `impact_analysis`, `find_deprecated_usage`, `check_module_exists`

## Instructions

This skill produces an executive-level risk overview of an organization's Odoo customizations. It is designed for decision-makers who need a quick, high-signal picture of where technical debt or upgrade risk is concentrated — without needing to understand the underlying code.

Start by calling `find_deprecated_usage` across the custom module set to surface deprecated API calls that will break on upgrade. Then call `impact_analysis` on the highest-usage custom fields and methods to estimate blast radius. Use `check_module_exists` to verify that each custom module's base dependencies exist in the target Odoo version.

Synthesize findings into a concise executive summary. Group risk by module. Assign a risk level (Low / Med / High) based on deprecated API count and impact-analysis severity. Keep prose minimal — let the table carry the content. Always close with a one-sentence recommended action (e.g., "Prioritize migration of `viin_sale` before the v17 upgrade window").

## Output format

## Odoo Customization Risk Overview

**Assessment date:** <date>
**Odoo version assessed:** <version>

| Module | Deprecated APIs | High-impact fields | Upgrade risk |
|--------|----------------|--------------------|--------------|
| ...    | ...            | ...                | Low/Med/High |

### Key findings
- <bullet 1>
- <bullet 2>

### Recommended action
<one sentence>

## Example invocation

User: "give me a risk overview of our Odoo customization before we upgrade to v17"
Expected output: Executive summary table listing each custom module with deprecated API counts, high-impact field names, and a Low/Med/High risk rating, followed by a prioritized action recommendation.
