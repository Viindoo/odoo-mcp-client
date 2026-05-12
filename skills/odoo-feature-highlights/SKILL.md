# odoo-feature-highlights

**Persona:** Marketer
**Triggers:** highlight new features in Odoo 17, what's exciting in this version, feature comparison for sales deck, tính năng nổi bật Odoo 17, nêu điểm mạnh so với phiên bản trước
**Tools used:** `api_version_diff`, `find_examples`, `resolve_model`

## Instructions

This skill generates marketing-friendly feature highlights for a specific Odoo version, suitable for inclusion in sales decks, blog posts, email campaigns, or product announcements. It translates technical API changes into compelling business-value narratives.

Call `api_version_diff` to retrieve the list of new APIs and capabilities in the target version. For the most impactful additions (prioritize user-facing models and core business flows), call `find_examples` to find real usage examples that can be cited as evidence. Use `resolve_model` on the key models involved in headline features to extract field-level details that make the narrative concrete.

Write in a positive, benefits-first tone. Lead with business outcomes, not technical mechanisms. Use concrete numbers where available (e.g., "the new `amount_by_group` field enables automatic tax grouping across 5 tax brackets"). Avoid acronyms, file paths, and developer jargon in the main highlights. Provide a separate "Technical notes" section for those who need it.

## Output format

## Feature Highlights: Odoo <version>

### Headline features
1. **<Feature name>** — <1–2 sentence business value description>
2. **<Feature name>** — <1–2 sentence business value description>
3. **<Feature name>** — <1–2 sentence business value description>

### Feature comparison: <prev version> vs <version>
| Capability | <prev> | <version> | Business impact |
|------------|--------|-----------|-----------------|
| ...        | ...    | ...       | ...             |

### Technical notes (for developers)
- <API change 1>
- <API change 2>

### Use in sales deck
<Suggested slide title + 3-bullet talking points>

## Example invocation

User: "create feature highlights for Odoo 17 for our sales deck"
Expected output: 3–5 headline features with business-value descriptions, a comparison table vs Odoo 16, and suggested sales deck talking points.
