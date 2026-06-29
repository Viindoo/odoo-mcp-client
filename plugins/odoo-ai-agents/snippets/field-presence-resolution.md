# Field / Method Presence Resolution (don't probe - resolve)

Probing whether an Odoo **field or method exists on a recordset at runtime** -
`hasattr(record, 'field')`, `getattr(record, 'field', default)`, or
`try: record.field except AttributeError:` - is a code smell, not defensive coding. The ORM
schema is statically knowable from the module dependency graph; a runtime probe **masks one of
three real defects** instead of surfacing it. Resolve presence with OSM **before** writing or
accepting the access. (This is the runtime-code corollary of the OSM-First contract §1: you
already may not *assert* existence from memory - equally, you may not *re-probe* it at runtime.)

Scope: this targets **Odoo ORM field/method presence on a recordset**. It does NOT ban
`getattr`/`hasattr` on plain Python objects (optional kwargs, duck-typed non-ORM values).

## Resolve presence (the OSM walk)

1. `model_inspect(model='<m>', method='fields'|'methods', odoo_version='<v>')` - does the
   field/method exist on the model at all, and **which module declares it**?
2. `entity_lookup(kind='field'|'method', model='<m>', field='<f>', odoo_version='<v>')` /
   `resolve_orm_chain(model='<m>', dotted_path='<a.b.c>', odoo_version='<v>')` - if it is on a
   *related* model, pin the exact hop.
3. `module_inspect(name='<my_module>', method='dependencies', odoo_version='<v>')` - walk the
   target module's transitive `depends` closure: is the declaring module reachable?

## Three-way classification (name the masked defect)

| # | Class | What the probe was hiding | Correct fix |
|---|---|---|---|
| 1 | **Lookup-gap** | Field/method existence was never OSM-verified; the probe is a guess in code form. | Verify via OSM; the field is guaranteed by the dep closure -> **direct access** `record.field`. |
| 2 | **Hidden bug / wrong ORM path** | The field exists, but on a *related* model - the probe returns False and silently routes around the real bug. | Use the real path (`resolve_orm_chain` pins it), e.g. `order.partner_id.commercial_partner_id`. |
| 3 | **Dependency-architecture gap** | The field is real but its module is **not in your `depends`** closure; the probe papers over a missing manifest dependency. | Either add the module to `depends` (presence now guaranteed -> direct access), **or**, if optional *by design*, use `'field' in record._fields` **with a documented soft-dependency note** explaining why both module sets are supported. |

A probe is **never** acceptable as "defensive coding" - it is always one of the three above, and
all three have a static fix. `'field' in record._fields` is legitimate **only** for a genuine,
documented soft-dependency (class 3 optional-by-design); used anywhere else it is itself a class-1
or class-2 smell. Run the OSM walk first, classify, then choose the branch - do not assign severity
or pick a fix from the syntactic pattern alone.

Inversion case (class 3, base model): a **base** model must not sniff `self._fields` for a field a
**downstream** module injects - the base cannot hard-depend on the downstream, so the probe is the
wrong direction. Have the base expose an **overridable hook** (a method returning a default, e.g.
`def _get_<x>(self): return <default>`) and let the downstream module override it to read the
injected field. The base stays dependency-clean; the downstream owns the field it added.

## Worked example 1 - wrong ORM path (class 2)

```python
# BAD - masks a wrong-model access; returns False, silently drops the value
total = order.commercial_partner_id.name if hasattr(order, 'commercial_partner_id') else order.partner_id.name
# WHY: commercial_partner_id is declared on res.partner, NOT on sale.order.
#      entity_lookup(field, sale.order, commercial_partner_id, odoo_version='auto') -> NOT FOUND
#      entity_lookup(field, res.partner, commercial_partner_id, odoo_version='auto') -> FOUND (computed, module 'base')

# GOOD - use the real ORM path; presence is guaranteed by partner_id's comodel
total = order.partner_id.commercial_partner_id.name
```

## Worked example 2 - dependency-architecture gap (class 3)

```python
# BAD - getattr-default hides that sale_margin isn't in this module's depends
margin = getattr(order, 'margin', 0.0)
# WHY: 'margin'/'margin_percent' on sale.order are added by the module 'sale_margin'.
#      module_inspect(name='<my_module>', method='dependencies', odoo_version='auto') shows sale_margin NOT reachable.

# GOOD (preferred) - declare the dependency, then access directly
#   __manifest__.py: 'depends': [..., 'sale_margin'],
margin = order.margin

# GOOD (only if margin support is OPTIONAL by design - documented soft-dep)
# Soft-dependency: 'sale_margin' is not a hard depend; this module also runs without it.
margin = order.margin if 'margin' in order._fields else 0.0
```

## Tests - duck-typed fakes are the same smell

A test that builds a duck-typed fake record (e.g. `class FakeSaleOrder` with hand-set attributes)
to satisfy a `hasattr`/`getattr` branch tests the **code's shape, not Odoo behavior** - it locks in
the probe instead of the business rule it should protect. Flag both the production probe and the
test fake. Exercise the real recordset on the real model instead. The test passes only because the
fake was built to match the probe - it can never go red on a real defect.

## JavaScript / OWL analogue (frontend)

The same smell in JS/OWL is `record.data.field !== undefined`, optional chaining as an existence
guard `record.data?.field`, or `'field' in record.fields`. The fix mirrors the backend: the field a
widget binds to must be guaranteed by the **manifest `depends` closure of the module owning the JS
asset**. Confirm the bound field exists and is reachable (`module_inspect` / `entity_lookup`) before
binding; do not paper over a missing field with `record.data.field ?? default`. If it is genuinely
optional, gate it on a documented soft-dependency rather than a bare runtime probe.
