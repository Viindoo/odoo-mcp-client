# odoo-feature-check

**Persona:** Consultant
**Triggers:** does Odoo have module X built-in, check if feature Y exists in standard, is this available out of the box, Odoo có sẵn tính năng X không, module X có trong Odoo CE không
**Tools used:** `check_module_exists`, `resolve_model`, `find_examples`

## Instructions

This skill helps consultants quickly determine whether a client requirement is covered by standard Odoo functionality — and at what edition level (Community Edition vs. Enterprise Edition). It prevents the expensive mistake of recommending custom development for features that already exist in Odoo.

Call `check_module_exists` with the feature or module name to determine if it exists in standard Odoo and which edition it belongs to. If the module exists, call `resolve_model` on the primary model it introduces to understand what fields and functionality are already provided out of the box. Use `find_examples` to locate code examples that demonstrate the feature in use, which can be shown to clients as evidence.

Present a clear availability verdict: "Available in CE", "Available in EE only", "Not available — custom development required", or "Partial — standard covers X, custom needed for Y". When only partially covered, specify exactly which part requires customization. Always cite the exact module name so clients can verify independently.

## Output format

## Feature Availability Check

**Feature requested:** <feature description>
**Odoo version:** <version>

| Feature aspect | CE | EE | Module | Notes |
|---------------|----|----|--------|-------|
| ...           | ✓/✗ | ✓/✗ | ...  | ...   |

### Verdict
**<Available in CE / Available in EE only / Partial / Not available>**

### Evidence
- Module: `<module_name>`
- Key model: `<model_name>`
- Example usage: <brief description>

### Recommendation
<1–2 sentences on what to tell the client>

## Example invocation

User: "does Odoo have a subscription billing module built in?"
Expected output: Feature availability table showing CE vs EE coverage, module name (`sale_subscription` in EE), key model fields, and a verdict with a client-facing recommendation.
