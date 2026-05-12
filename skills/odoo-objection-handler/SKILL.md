# odoo-objection-handler

**Persona:** Sales
**Triggers:** handle objection that Odoo can't do X, counter argument for limitation concern, respond to 'Odoo doesn't support Y', phản bác lo ngại về tính năng X, xử lý phản đối từ khách hàng
**Tools used:** `check_module_exists`, `find_examples`, `suggest_pattern`

## Instructions

This skill helps sales engineers craft evidence-based responses to client objections about Odoo's capabilities. It transforms "Odoo can't do X" objections into opportunities by finding real evidence that X is supported — or providing a credible, honest workaround when partial support is the truth.

Call `check_module_exists` with the feature being objected to, to get ground-truth availability data. Use `find_examples` to retrieve concrete code examples that refute the objection — specific examples are far more persuasive than general claims. Call `suggest_pattern` to identify established extension patterns when the feature requires customization, so the response can honestly frame customization as "standard practice, not a gap."

Structure the response using the ACA framework: Acknowledge the concern, provide Counter-evidence, and close with an Affirmation of capability or workaround. Never fabricate capabilities — if Odoo genuinely doesn't support something, say so clearly and propose the best available workaround. Intellectual honesty builds more trust than overselling.

## Output format

## Objection Response: "<objection>"

### Acknowledge
<1 sentence acknowledging the concern as valid>

### Counter-evidence
| Evidence type | Detail | Source |
|--------------|--------|--------|
| Module exists | `<module_name>` | `check_module_exists` |
| Code example | <description> | `find_examples` result |
| Pattern | <pattern name> | `suggest_pattern` result |

### Talking points
1. <talking point 1>
2. <talking point 2>
3. <talking point 3>

### If partial support (workaround)
<honest description of what's needed to close the gap — hours/days estimate>

### Suggested response (verbatim)
"<ready-to-use client-facing response paragraph>"

## Example invocation

User: "handle the objection that Odoo doesn't support complex approval workflows"
Expected output: ACA-structured response citing the `approval` module, a code example of multi-level approval, talking points, and a verbatim response the salesperson can use in the meeting.
