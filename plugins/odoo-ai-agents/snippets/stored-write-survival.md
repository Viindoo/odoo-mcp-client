<!-- SSOT snippet. "readonly=False does not guarantee value survival on stored computes."
     Consumers: odoo-solution-architect.md, odoo-code-reviewer.md (WS3). Edit here only. -->

# Stored Write Survival Contract

## The trap: `readonly=False` is not a survival guarantee

Declaring a stored computed field as `store=True, readonly=False` means the ORM will ACCEPT a
direct write to it - but it does NOT guarantee the written value persists. If the field's
`@api.depends` dependency set is triggered by any subsequent ORM operation in the same
transaction (e.g. another field on the same record is written and it appears in `depends`),
the ORM re-queues and re-runs the compute method, **overwriting** the value you just wrote.

## When the clobber happens

```python
class MyModel(models.Model):
    _inherit = 'some.model'

    validated_hours = fields.Float(store=True, readonly=False,
                                   compute='_compute_validated_hours',
                                   depends=['overtime_status', 'attendance_ids'])

    def _compute_validated_hours(self):
        for r in self:
            r.validated_hours = sum(r.attendance_ids.mapped('overtime'))
```

If you call:

```python
record.write({'overtime_status': 'validated', 'validated_hours': 8.0})
```

The ORM sees `overtime_status` in `depends` of `_compute_validated_hours`. It schedules a
recompute. The recompute runs AFTER the write and replaces `8.0` with whatever the compute
method derives. **Your explicit `8.0` is lost.**

## When it does NOT happen (safe paths)

- Writing ONLY `validated_hours` with no field in its `depends` also changing in the same
  call → no recompute triggered → value survives.
- The compute method is called only when the ORM is NOT already in a `with_context(no_recompute=True)`
  scope (rare, framework-internal).

## How to prove survival (required before claiming "value survives")

1. Reproduce on the **default company config** (no demo-data DB customization): write the field
   alongside every field in its `depends` that your feature also sets, in a single `write()` call.
2. Read the field back in a new transaction (flush + invalidate first):
   ```python
   record.flush_recordset()
   record.invalidate_recordset()
   assert record.validated_hours == expected  # only green if no clobber
   ```
3. If the assertion fails → value is clobbered.

## Correct fix: single writer via compute extension

When clobber is confirmed, the only safe fix is to make the compute method the **single writer**:
extend `_compute_validated_hours` in your module to incorporate the conditional override logic,
rather than writing the field from outside:

```python
def _compute_validated_hours(self):
    for r in self:
        if r.overtime_status == 'validated' and r.manual_override:
            r.validated_hours = r.manual_validated_hours  # your business rule
        else:
            super()._compute_validated_hours()  # or call self.browse(r.id)
```

Do **not** solve clobber by removing the field from `depends` unless that is semantically correct -
dropping a dependency silently breaks recompute triggers for other paths.

## Reviewer checklist

When reviewing code that calls `.write({'stored_compute_field': value, 'dep_field': other_value})`:

1. Is `dep_field` in the `@api.depends` of `stored_compute_field`? If yes → CLOBBER RISK → HIGH finding.
2. Is there a unit test that writes both fields and reads the compute field back in a separate
   flush+invalidate pass? If not → test is missing or tests only the happy-path order.
3. Does the review claim "value survives" based on static inspection alone? That is NOT verification
   - lower confidence or demand a runtime test on the bare `write()` RPC path.
