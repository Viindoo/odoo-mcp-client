# odoo-perf-audit — Output Format

```
## Performance Audit Report

**Module / file scope:** <module or file list>
**Odoo version:** <version>
**Grounding:** osm-indexed | local-source (not OSM-indexed) | OSM unavailable - ungrounded
**Issues found:** <N total> (<N> HIGH / <N> MEDIUM / <N> LOW)

### Findings

| # | File | Line | Anti-pattern | Impact | Remediation |
|---|------|------|--------------|--------|-------------|
| 1 | ... | L42 | N+1: browse() inside for-loop | HIGH - O(n) queries | Collect IDs first, single browse(ids) outside loop |
| 2 | ... | L87 | Unindexed field in domain | MEDIUM - full table scan | Add index=True to field definition |
| 3 | ... | ... | ... | ... | ... |

### Finding details

#### #1 - N+1: browse() inside for-loop (HIGH)
**File:** `module/models/sale_order.py` L42
**Pattern:**
```python
for order in self:
    partner = self.env['res.partner'].browse(order.partner_id.id)  # N+1
```
**Why it matters:** Each loop iteration fires a separate SQL SELECT. For 500 records this is 500 queries vs 1.
**Remediation:** Pre-fetch all partner records outside the loop:
```python
partners = {p.id: p for p in self.mapped('partner_id')}
for order in self:
    partner = partners[order.partner_id.id]
```
**Estimated impact:** HIGH - eliminates O(n) queries; critical for list views and reports.

#### #2 - Unindexed field in domain (MEDIUM)
...

### Summary

- **Highest risk:** <describe the 1-2 findings most likely to cause production incidents>
- **Quick wins:** <findings fixable in < 1 hour>
- **Requires refactor:** <findings needing structural change>

### Estimated total query reduction
<Quantitative estimate where possible, e.g. "N+1 fix alone reduces queries by ~80% for
list view with 100+ records">
```

## Impact levels

- **HIGH** - O(n) query multiplication, mass recompute on every write, full-table scan on a large model, or QWeb loop with per-record RPC
- **MEDIUM** - unindexed field on medium-sized model, overly broad depends on frequently written model, stored compute without `store=True` stability check
- **LOW** - style-level (redundant `mapped` call, minor prefetch gap on small recordsets)

## Examples

**Example 1:**
Prompt: "This invoice list view takes 30 seconds to load - here is the model code"
Output: Findings table with N+1 browse in `_compute_payment_state`, missing `index=True` on `invoice_date` used in default domain, and overly broad `@api.depends('line_ids')` instead of `@api.depends('line_ids.price_subtotal')`. Each finding includes file:line, impact estimate, and concrete remediation snippet. Does NOT rewrite the file.

**Example 2:**
Prompt: "code này bị N+1 không?" (with a QWeb report template pasted)
Output: Detects `<t t-foreach="docs" t-as="doc">` with `doc.order_line` accessed in inner loop without prefetch; flags as HIGH impact for reports with > 50 lines. Suggests calling `docs.mapped('order_line')` before the foreach to warm the prefetch cache.

**Example 3:**
Prompt: "should I add index=True to this field used in search domain?"
Output: Calls `model_inspect` to check current index flag, checks model record volume estimate from OSM, and recommends index=True if the field is used in user-facing search domains on models expected to grow beyond ~10k records.
