<!-- SSOT snippet. Ground-truth version-pivot table v8-v19, verified against on-disk codebase (D9).
     Every file that states a version-specific API fact MUST cross-ref here, NOT restate.
     Consumers: era-reference.md, upg-conventions.md, runbot-parity-checklist.md, upg-phase-detail.md.
     Last audited: 2026-06-26. Edit this file to correct a pivot; do not patch consumers. -->

# Odoo Version Pivots - v8-v19 SSOT

Compact canonical table. Row format: **change** | **new API / mechanism** | **from vMIN** | **old: removed or alias**.
"alias" = old name still works but emits DeprecationWarning. "REMOVED vN" = raises AttributeError / ImportError / ValidationError at that version.

> **OSM caveat (active until server bug fix):** OSM currently does NOT resolve underscore-renamed
> methods (`_has_cycle`, `_filtered_access`) or `res.users.has_group`/`has_groups` (server bugs
> #2/#3). This table is the authoritative fallback for those symbols. For all others, verify via
> OSM `api_version_diff(symbol, from_version, to_version)` at TARGET - do not read this table as
> a substitute for a live OSM check when OSM is available and the symbol is indexed.

---

## Python ORM - ACL / access

| Change | New API | From | Old |
|---|---|---|---|
| Unified access check | `check_access(operation)` / `has_access(operation)` | v18 | `check_access_rights(operation)` + `check_access_rule(operation)` = alias (DeprecationWarning v18+) |
| Filtered access | `_filtered_access(mode)` | v18 | `_filter_access_rules()` / `_filter_access_rules_python()` = alias |
| User group test - single xmlid | `user.has_group('mod.xmlid')` | v8 | -- (present since v8) |
| User group test - plural / env shorthand | `user.has_groups('a.x,b.y')` | v18 | `user_has_groups(xmlid)` **REMOVED v18** |

## Python ORM - model API

| Change | New API | From | Old |
|---|---|---|---|
| Cycle check | `_has_cycle(field)` | v18 | `_check_recursion(field)` = alias |
| Display name | `_compute_display_name` override | v12 | `name_get()` deprecated v17, **REMOVED v18** |
| Record-style API | `@api.model`, `@api.model_create_multi`, plain multi-record methods | v13 | `@api.one`, `@api.multi`, `_columns` dict, `fields.function`, `osv.osv` **REMOVED v13** |

## Python ORM - cache / flush / metadata

| Change | New API | From | Old |
|---|---|---|---|
| Targeted flush | `Model.flush_model()` / `records.flush_recordset()` | v16 | `self.flush()` **REMOVED v17** |
| Targeted invalidate | `Model.invalidate_model()` / `records.invalidate_recordset()` | v16 | `self.invalidate_cache()` **REMOVED v17** |
| External id lookup | `record.get_external_id()` | v16 | `record.get_xml_id()` **REMOVED v17** |
| View loading | `env['ir.ui.view'].get_views(...)` | v16 | `fields_view_get()` deprecated v16, **REMOVED v17**; `fields_get_keys()` gone v17 |
| Registry cache clear | `registry.clear_cache()` | v17 | `registry.clear_caches()` = alias |
| Field to SQL | `_field_to_sql(alias, fname, query)` | v17 | `_inherits_join_calc(...)` = alias |
| Order to SQL | `_order_to_sql(order, query, alias, reverse)` | v17 | `_generate_order_by(...)` = alias |

## XML views

| Change | New | From | Old |
|---|---|---|---|
| Inline Python modifiers | `readonly="record.state == 'done'"` | v17 | `attrs=`/`states=` → `ValidationError` **from v17** (not just a warning) |
| List view arch tag | `<list>` | v18 | `<tree>` still accepted but `<list>` is canonical; `<tree>` was canonical up to v17 |
| Always-invisible field | field + XML comment AFTER: `<!-- invisible: <reason> -->` | v18 | No comment → fails `base.TestInvisibleField` from v18+ |
| Chatter element | `<chatter/>` | v18 | `<div class="oe_chatter">` deprecated; `<chatter/>` preferred from v18 |

## Manifest

| Change | Detail | From | Notes |
|---|---|---|---|
| Asset bundles | `assets` key in manifest | v15 | Pre-v15: `qweb` key + bundle XML in views |
| Version string | Strict `adapt_version` regex enforcement | v17 | Pre-v17: lenient; malformed version strings are rejected at install from v17 |
| Manifest version - code upgrade | Keep short form `x.y.z`; series-prefixed value CONVERTED, never bumped | CORE | `upg-conventions.md` Convention 1 |
| Forward-port version conflict | Keep TARGET's value, never bump | CORE | `[[fp-merge-absorption]]` C1 |

> `adapt_version` above refers to the install-gate version-string validation (v17+ regex enforcement). The same function also series-prefixes the manifest for migration-runner comparison (its second role) - see C2 in `[[fp-merge-absorption]]`.

## CLI - demo flag

| Scenario | Flag / behavior | Version range |
|---|---|---|
| Disable demo data | `--without-demo` | v8-v19 (present in ALL versions) |
| Demo ON is the default; no extra flag needed to get demo | *(default)* | v8-v18 |
| Enable demo data | `--with-demo` | **v19+ only** - this flag does NOT exist in v8-v18 |
| Demo default | **ON** when `-i`/`-u` given | v8-v18 |
| Demo default | **OFF** | v19+ |

> `--without-demo=False` is **INVALID** in all versions. Never use it.

## JavaScript / OWL / tests

| Change | New API | From | Old |
|---|---|---|---|
| OWL experimental | OWL 1.x alongside `web.Widget` | v14 | pre-v14: `web.Widget` only |
| OWL becomes primary for views | OWL 2.x - `Component`, `useState`, `useService`, `registry.category('fields')` | v16 | from v16 form/list/kanban/fields use `Component`; `AbstractField`/`web.field_registry` → `registry.category('fields')`; legacy `web.Widget` no longer used in core views (class lingers, declining v16→v18) |
| JS module header | `/** @odoo-module **/` | v15 | Mandatory v15-v17; auto-detected (can omit) **from v18**; `/** @odoo-module ignore **/` to opt out |
| Legacy AMD define | `odoo.define(name, fn)` | v9 | Shim-only (compatibility layer) from v17; do NOT write new `odoo.define` code |
| Test framework | `@odoo/hoot` | v18 | QUnit → Hoot from v18 (Hoot primary; QUnit still present at v18, last 100%-QUnit is v17) |

> Detailed per-version JS/OWL authoring rules, pitfall catalogue, and per-version applicability: `skills/_shared/odoo-frontend-fidelity.md`.

## Core test-enforced authoring rules

These are CORE Odoo rules enforced by a core test. Applies to ALL distributions.

### `hr.employee` field absent from `hr.employee.public` - requires `groups=` (v16+)

When adding a field to `hr.employee` that has NO counterpart on `hr.employee.public`, declare
`groups='hr.group_hr_user'` on the field definition:

```python
class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    sensitive_field = fields.Char(groups='hr.group_hr_user')
```

- Place `groups=` on the `hr.employee` override, NOT on a shared mixin - the mixin is used by
  both models and would wrongly gate the field on the public model too.
- ACL requirement from v16+. Enforced by `hr.TestSelfAccessProfile.test_employee_fields_groups`
  (exact test name present from v18; sibling test `TestSelfAccessRights.testReadOtherEmployee`
  covers v16/v17).

---

## gettext placeholders (named required for multi-arg; E8505 lint failure v18+)

CORE Odoo rule enforced by a core test. Applies to ALL distributions.

In `_()` / `_lt()` translation calls that interpolate MORE THAN ONE variable, use NAMED
placeholders `%(name)s` with keyword arguments - never multiple positional `%s`. A single
positional `%s` is acceptable.

```python
# v14+ correct (named, lint-clean on v18+):
raise UserError(_("Answer to %(field)s is not valid, expected %(kind)s.", field=name, kind="int"))

# v18 E8505 FAILURE (two unnamed placeholders):
raise UserError(_("Answer to %s is not valid, expected %s.", name, "int"))
```

- **Capability:** the multi-arg `_()` signature exists from **v14+** (verified v14, v16, v17, v18).
  `GettextAlias.__call__` is `def __call__(self, source):` (single-arg, no `*args`/`**kwargs`) on
  v12 AND v13 - passing extra positional/keyword args on v13 or earlier raises `TypeError`, it does
  not lint-fail. Multi-var interpolation pre-v14 is done via `%` outside the call.
- **v14-v17:** named placeholders are supported and preferred, but a positional multi-`%s` call
  does NOT lint-fail.
- **v18+:** this is a hard `test_lint` FAILURE, not a style nit - `test_lint`'s gettext AST checker
  (`TestI18nChecks.test_gettext_placeholders`) rejects more than one unnamed placeholder: pylint
  symbol `gettext-placeholders`, message code **E8505**. Escaped `%%s` and a single `%s` are still
  OK. The check is NEW at v18 (absent at v16/v17).
- Treat an E8505 finding as a BUILD FAILURE - fix by switching to named placeholders, never by
  suppressing the lint check.

---

## Viindoo-distribution conventions (profile-gated - see `upg-conventions.md`)

Apply ONLY under `upg-conventions.md`'s gating. NOT Odoo core or other distributions.

| Convention | Rule | Cross-ref |
|---|---|---|
| No-data module rename | `old_technical_name` key only - no migration script | `upg-conventions.md` Convention 2 |
