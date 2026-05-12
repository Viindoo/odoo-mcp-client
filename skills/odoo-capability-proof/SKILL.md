# odoo-capability-proof

**Persona:** Sales
**Triggers:** prove Odoo can do X for this client, show capability evidence for requirement Y, demo material for sale.order customization, chứng minh Odoo làm được X, bằng chứng tính năng cho khách hàng
**Tools used:** `find_examples`, `check_module_exists`, `resolve_model`

## Instructions

This skill assembles concrete evidence that Odoo can fulfill a specific client requirement. It is used by sales engineers during pre-sales to counter skepticism and build confidence, backed by real code and module references rather than marketing claims.

Call `find_examples` to retrieve real code examples from the indexed codebase that directly demonstrate the capability in question. Use `check_module_exists` to confirm the relevant module exists and cite it by name. Call `resolve_model` on the primary model involved to show the exact fields that implement the requirement — making the evidence tangible and verifiable.

Structure the output as a capability brief that a salesperson can walk through with the client. Start with a clear statement of capability ("Yes, Odoo supports X natively via the Y module"). Provide code evidence with module and file references. Include suggested demo steps that the sales team can perform live. Keep technical detail as a collapsible "Evidence details" section so the main narrative stays accessible.

## Output format

## Capability Proof: <requirement>

**Verdict:** Supported natively / Supported with configuration / Supported with light customization

### Summary
<2–3 sentences confirming capability and how it's implemented>

### Evidence
| Module | Model | Key fields | Code reference |
|--------|-------|-----------|----------------|
| ...    | ...   | ...       | ...            |

### Demo steps
1. <step>
2. <step>
3. <step>

### Evidence details (for technical review)
```python
<code snippet from find_examples>
```

## Example invocation

User: "prove Odoo can handle multi-currency invoicing for our prospect"
Expected output: Capability verdict with evidence table citing `account.move` fields (`currency_id`, `amount_currency`), a real code example, and demo steps for a live walkthrough.
