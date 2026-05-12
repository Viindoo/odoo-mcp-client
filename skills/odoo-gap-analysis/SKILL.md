# odoo-gap-analysis

**Persona:** Consultant
**Triggers:** gap analysis for client requirements, what needs to be customized, standard vs custom feature map, phân tích gap giữa yêu cầu và Odoo standard, tính năng nào cần custom
**Tools used:** `check_module_exists`, `find_examples`, `lookup_core_api`

## Instructions

This skill performs a structured gap analysis comparing a client's requirements against Odoo standard functionality. It is the core consulting deliverable for pre-sales, scoping, and project kickoff — translating a requirements list into a concrete custom development estimate.

For each client requirement, call `check_module_exists` to test if a standard module covers it. Where standard coverage is partial, call `find_examples` to locate the closest existing pattern in the codebase, which informs the custom development effort. Use `lookup_core_api` to confirm the extension points available for any gaps requiring customization.

Produce a gap matrix that a project manager can use directly for estimation. Classify each requirement as: "Standard" (zero effort), "Configuration" (low effort), "Extension" (medium effort — existing model), or "Custom" (high effort — new model/logic). Provide a total effort estimate at the bottom. Be conservative: if in doubt, upgrade the effort estimate.

## Output format

## Gap Analysis Report

**Client:** <client name or "Client">
**Requirements analyzed:** <N>
**Date:** <date>

| # | Requirement | Standard coverage | Effort type | Estimated effort | Recommended module |
|---|-------------|------------------|-------------|-----------------|-------------------|
| 1 | ...         | Partial/Full/None | Standard/Config/Extension/Custom | S/M/L/XL | ... |

### Effort summary
- Standard (no effort): <N> requirements
- Configuration only: <N> requirements
- Extension (custom field/method): <N> requirements
- Full custom development: <N> requirements

### Total estimated effort
<Low/Medium/High/Very High> — <rationale paragraph>

## Example invocation

User: "gap analysis for a client who needs multi-company invoicing, approval workflows, and a custom loyalty program"
Expected output: A gap matrix with all three requirements assessed, effort classifications, and module recommendations, plus a total effort summary.
