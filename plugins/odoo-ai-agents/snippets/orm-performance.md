<!-- SSOT snippet. "Stored compute aggregating over a high-volume relation MUST use _read_group."
     Consumers: odoo-coder.md (Round 4), odoo-code-reviewer.md (failure modes), odoo-solution-architect.md (§8 Risks).
     Version-stable (applies v8+). Edit here only; consumers cross-ref, never restate. -->

# ORM Performance - Stored Aggregate on High-Volume Relations

## Rule

A stored compute that **aggregates over a high-volume parent-child relation** (`hr.attendance`,
`stock.move`, `account.move.line`, `account.analytic.line`, or any model expected to grow beyond
~10 k rows) **MUST use one `_read_group` grouped query keyed by parent id**, never a per-record
loop.

**Why:** `for r in self: r.x = sum(r.line_ids.mapped('f'))` executes one SELECT per parent record
(O(n) round-trips). At install-init recompute or any bulk write, n = all records - catastrophic
at scale.

## Correct pattern

```python
result = self.env['account.move.line']._read_group(
    domain=[('move_id', 'in', self.ids)],
    groupby=['move_id'],
    aggregates=['debit:sum'],
)
mapped_vals = {move.id: debit_sum for move, debit_sum in result}
for r in self:
    r.total_debit = mapped_vals.get(r.id, 0.0)
```

## Anti-pattern (HIGH finding in review)

```python
# BAD: O(n) queries - one SELECT per record
for r in self:
    r.total_debit = sum(r.line_ids.mapped('debit'))
```

Severity in review: **HIGH**.
