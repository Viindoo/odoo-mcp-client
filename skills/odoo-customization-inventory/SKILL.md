# odoo-customization-inventory

**Persona:** CEO
**Triggers:** list all our Odoo customizations, inventory of custom modules, what have we built on top of Odoo, liệt kê tất cả customization, bản kiểm kê module tùy chỉnh
**Tools used:** `resolve_model`, `check_module_exists`

## Instructions

This skill generates a structured inventory of all custom Odoo modules and the standard models they extend. It serves executives who need to understand the scope and business purpose of their Odoo investment before a strategic decision (upgrade, migration, vendor change, or audit).

For each custom module provided, call `check_module_exists` to confirm it is not a standard Odoo module (only custom/override modules are relevant). Then call `resolve_model` for the primary model each module extends to extract key fields added and inherited capabilities.

Present findings as a clean inventory table. For each module, identify: the standard Odoo model it extends, the most important custom fields (up to 5), and a plain-language business purpose inferred from field names and module name. Avoid technical jargon in the "Business purpose" column — write for a non-technical CEO audience.

## Output format

## Odoo Customization Inventory

**Total custom modules:** <N>
**Base modules extended:** <N distinct base models>

| Module | Base model extended | Key custom fields | Business purpose |
|--------|--------------------|--------------------|-----------------|
| ...    | ...                | ...                | ...             |

### Summary
<2–3 sentence narrative for the CEO>

## Example invocation

User: "list all our Odoo customizations and what they do"
Expected output: A table listing each custom module, the Odoo model it extends, up to 5 key custom fields, and a plain-language description of what business problem it solves.
