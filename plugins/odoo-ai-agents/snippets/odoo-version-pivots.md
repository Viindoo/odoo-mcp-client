<!-- SSOT snippet. Ground-truth version-pivot table v8-v19, verified against on-disk codebase (D9).
     Every file that states a version-specific API fact MUST cross-ref here, NOT restate.
     Edit this file to correct a pivot; do not patch consumers.
     Consumers are DERIVED, never listed here - re-derive with `grep -rl "odoo-version-pivots.md" plugins/odoo-ai-agents/`. -->

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
| Optional list column | `optional="hide"` / `optional="show"` on a list/tree `<field>` | v13 | Attribute not honoured before v13 - the column is always rendered |
| Chatter element | `<chatter/>` | v18 | `<div class="oe_chatter">` deprecated; `<chatter/>` preferred from v18 |

## Manifest

| Change | Detail | From | Notes |
|---|---|---|---|
| Asset bundles | `assets` key in manifest | v15 | Pre-v15: `qweb` key + bundle XML in views |
| Version string | Strict `adapt_version` regex enforcement | v17 | Pre-v17: lenient; malformed version strings are rejected at install from v17 |
| Manifest version - code upgrade | Keep short form `x.y.z`; series-prefixed value CONVERTED, never bumped | CORE | `upg-conventions.md` Convention 1 |
| Forward-port version conflict | Keep TARGET's value, never bump | CORE | `[[fp-merge-absorption]]` C1 |

> `adapt_version` above refers to the install-gate version-string validation (v17+ regex enforcement). The same function also series-prefixes the manifest for migration-runner comparison (its second role) - see C2 in `[[fp-merge-absorption]]`.

## Build facts the odoo-local tools apply

`instance_build` and `instance_serve` apply three build facts themselves, on every series: the
server-wide modules (`--load`), the languages (`--load-language`) and the series' demo flag. Never
put any of them in `extra_args` and never compose them by hand. The judgement left to you is which
`demo` and which `languages` to ask for, and what to do with the warnings `job_wait` reports.

- **Server-wide modules.** The tools load the series' core default (read from the lease's Odoo
  checkout) plus the catalog row's `server_wide_modules`, fixed on the lease when it is acquired:
  the default for every build. Another set for one task: `server_wide` exclude/include on each
  build and serve of that DB. A `job_wait` server-wide warning: `server_wide.include` it for
  the task, or follow its catalog remedy (`/odoo-ai-agents:odoo-setup refresh`), then release the
  lease and acquire a new one before trusting it. Never answer it by installing the module with `-i`.
- **Languages.** Pass the target codes as `languages`; the tool adds `en_US` to every build.
  `job_wait` reports `languages_loaded` and `languages_failed`, proven from the build log; a code in
  `languages_failed` is not loaded, whatever you asked for.
- **Demo.** Pass `demo` (`on` | `off`) on every `init` build by its PURPOSE, per the table below,
  and never on a test build (the tool applies the series default; `job_wait` reports it). Demo data
  never leaves a database; `INSTANCE_HANDLE.demo` is the DATABASE's, from any lease.

| Series default | Series |
|---|---|
| Demo data loaded by default | v8-v18 |
| NO demo data by default | v19+ |

### Demo data by build PURPOSE

Resolve the purpose from the dispatch brief's own signals, never from the operation name alone.

| Build purpose - the signal that decides it | `demo` on a series whose default loads demo | `demo` on a series whose default loads none |
|---|---|---|
| Automation test run that gates code - ANY `--test-enable` build, at BOTH `GATE_ROLE: node-verify` and `GATE_ROLE: pre-pr-lint-gate` | series default (omit `demo`): demo, as its own CI runs; an `init` a test build reuses passes `on` | series default (omit `demo`): none; an `init` a test build reuses passes `off`; `on` and a demo database (`TEST_DB_HAS_DEMO`) are refused |
| Translation export / `.pot` / `.po` work | `on` | `on` |
| Documentation capture (`CONTEXT: doc`), demo recording, UI review | `on` | `on` |
| Acceptance live-UI sweep | `on` | `on` |
| Demo-load verification - proving a module's own `demo/` data still loads. INSTALL ONLY: this build NEVER carries `--test-enable` | `on` | `on` |
| Anything whose OUTPUT does not depend on demo records - a debug reproduction, an ensure-up, a language activation, a bare create, a no-code-change smoke run | `on` - the series default | `off` - the series default |

A demo-carrying build and a code-gating test build are two SEPARATE builds on two leases: loading
demo proves the `demo/` XML installs; the suite proves the code works. Where the default loads no
demo, never test on a database holding demo (a handle whose `demo` is `true`, an acceptance or
documentation instance): test on a fresh lease.

> **A v19+ automation-test build carries NO demo data, and the test suite must not want any.** Demo
> records are absent there, so a test that reads one fails. Every durable test authored for a v19+
> target - Python `TransactionCase` / `HttpCase`, Python tour, JS tour - MUST create its own records
> in `setUpClass` / `setUp` and MUST NOT reference a demo record by xmlid or by name. This holds even
> when the test was authored while driving a demo-carrying acceptance instance: the file it leaves
> behind runs demo-less in the gate.

### Test run on an existing database - `-i` vs `-u`

| Database state | Test build (`instance_build` op `test`) | Series |
|---|---|---|
| Scope modules NOT installed yet (a new database) | `test_mode` `fresh` (`-i`) | every series |
| Scope modules ALREADY installed | `test_mode` `reuse` (`-u`) - right on every series | every series; from v19 `-i` skips an installed module and runs none of its tests |

## Framework-validation test classes (named in `--test-tags` beside module tags)

**Only two classes are listed here, and the list stays that size on purpose.** A class earns a row
ONLY if all three hold: it is a FRAMEWORK class (lives in `base`/`hr`, not in the module under
test), it enforces a convention THIS plugin teaches, and a module-scoped `--test-tags /<module>` run
SKIPS it so nothing else would catch the violation. Odoo and Viindoo ship hundreds of thousands of
tests; this is not a mirror of them, and a class that fails any of the three does not belong.

| Convention it enforces | Class, per series | Tag spec to pass |
|---|---|---|
| Always-invisible view field needs an explanatory XML comment | `TestInvisibleField` (in `base`), v18+ only - absent below | `/base:TestInvisibleField` |
| Custom `hr.employee` field needs `groups="hr.group_hr_user"` | in `hr`: `TestSelfAccessProfile` v13-v18, RENAMED to `TestSelfAccessPreferences` at v19 | `/hr:TestSelfAccessProfile` or `/hr:TestSelfAccessPreferences` per series |

> **The `hr` class was RENAMED, not removed.** Its file and its `test_employee_fields_groups` method
> both still exist at v19 under the new class name, so the enforcement is live there - dropping the
> tag because the old name no longer resolves silently stops the check. (That method itself only
> exists from v18; below that the class is present but enforces the convention through other tests.)

> **The class separator in a tag spec is a COLON.** The grammar is `[-][tag][/module][:class][.method]`
> (`odoo/tests/tag_selector.py`, `filter_spec_re`), so `base.TestInvisibleField` does NOT name a
> class - it parses as tag `base` plus METHOD `TestInvisibleField`, matches no test method that
> exists, and selects NOTHING. Copy the tag-spec column; never re-derive it from a dotted name.

> **A tag that matches nothing is a SILENT no-op, not an error** - whether the spec is misspelled or
> the series ships a different name. The run exits 0 having tested nothing. So CONFIRM the class name
> against the target build's own `addons/<module>/tests/` before tagging it: this table has been
> wrong twice, once on a bound and once by reading "the old name is absent" as "the thing is gone".
> An UNTAGGED run needs none of this - it already includes every framework class - so prefer it
> wherever the cost of running the full closure is acceptable.

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
  covers v16/v17). Those are METHOD bounds inside the class, narrower than the CLASS bound in
  § Framework-validation test classes - read that section for what to TAG, and this line only for
  which assertion actually fires. The class itself is gone at v19, so the convention stands on its
  own there with no test left to catch a violation.

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

### Backend lint-class gate - which modules exist per series

| Module | Source | Present at |
|---|---|---|
| `test_lint` | Odoo core (`odoo/addons/test_lint`) | v10+ ONLY - absent below that, where a `/test_lint` tag silently matches nothing |
| `test_pylint` | Viindoo `tvtmaaddons` | v16 ONLY - the gate does not exist below v16 |
| `test_viin_pylint` | Viindoo `tvtmaaddons` | v17+ ONLY - same gate as `test_pylint`, under the new name |

> `test_pylint` and `test_viin_pylint` are ONE gate under two names, split at v17 - never install or
> tag both in the same build. Selection procedure, and the false-green trap that makes this matter:
> `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`.
