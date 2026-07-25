<!-- SSOT snippet. Everyday all-stack currency-check companion to
     `fp-symbol-survival-check.md` (forward-port-scoped: P6 of /odoo-forward-port, one merge
     window). This file is for EVERY code/test/review generation, forward-port or not. The
     currency PRINCIPLE ("existence is not currency") lives in `osm-first-contract.md` §1 - this
     file does NOT restate it, only the per-phase combo + tiering + blind-spot fallbacks. Edit
     here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/symbol-currency-check.md. -->

# Symbol Currency Check - per-phase combo + tiering

Param-safe per `generator/server-surface.json`: `lookup_core_api` requires `name,odoo_version`;
`api_version_diff` requires `symbol,from_version,to_version`; `lint_check` requires
`code,odoo_version` and takes an optional `language`; `impact_analysis` requires
`entity_type,entity_name,odoo_version`; `find_deprecated_usage` requires `odoo_version`.

## Cheap floor

**Mechanical, 1 call.** Any Python hunk you author or review that reuses a core idiom or
overrides a method: `lint_check(code=<python hunk>, odoo_version='<version>', language='python')`.
Trust `[pattern]` findings (deterministic - catches removed decorators like `@api.multi`); verify
`[fuzzy]` findings yourself. This is a pre-write hint, NOT the gate - the gate is `/test_lint`
(`osm-first-contract.md` §3).

## Per touched core symbol

For a decorator, mixin/ORM helper, base class, or core method you call DIRECTLY - never your own
custom field/model - call `lookup_core_api(name='<symbol>', odoo_version='<version>')`.
`stable` -> use it as-is; `deprecated`/`removed` -> use the returned `replacement`. For a plain
custom field/model add this is N=0 calls.

## Blind spots

**`lookup_core_api` blind spots - do NOT over-trust a miss.** It indexes PYTHON core symbols
only. It returns `not found` for a decorator-as-token (`api.multi`) and for JS/OWL (Hoot,
registries). A `not found` is NOT proof of currency - the core-symbol table is partial. Do NOT
hard-STOP on `not found`; cross-check instead:

- For a Python hunk: the `lint_check` floor above.
- For the known-rename family OSM cannot resolve: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`
  (its own OSM-caveat header lists the symbols it covers as fallback).
- Conclude `absent` only after a disk-fallback read also misses (per
  `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`).

**Base-class + JS-framework currency are NOT `lookup_core_api`'s job.** Test base-class
currency -> `test_base_classes(odoo_version='<version>')`; JS-framework currency ->
`js_test_inspect(module='<module>', odoo_version='<version>')`. Both are already wired in the
test/frontend paths - do not route base classes or JS frameworks through `lookup_core_api` (it
returns not-found for them).

## Tiering

**Tier-0 (ALWAYS).** Version-anchored (concrete `odoo_version` on every call, never `auto` on a
fresh pin) existence (`model_inspect`/`entity_lookup`) + the cheap floor above + per-touched-
core-symbol currency + ORM-path validation (`validate_domain`/`resolve_orm_chain`/
`validate_relation`). Cheap - mostly calls you already make.

**Tier-1 (heavy, ONLY on removal-risk).** Fires when the work is (a) a rename/removal of a
field/method/model, (b) cross-major (forward-port/upgrade, or a pattern remembered from an older
series), or (c) touches a widely-inherited core symbol (`find_override_point` chain >= 3, OR
`impact_analysis` shows wide downstream). Then add `impact_analysis` (blast radius),
`api_version_diff(symbol='<symbol>', from_version='<lo>', to_version='<hi>')`, and - for
existing ON-DISK code only, never a fresh in-session snippet -
`find_deprecated_usage(odoo_version='<version>')` or the 7-class sweep in
`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` §2.5. Reuse the Round-2
bidirectional-impact result you already computed (`${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md`)
as the escalation signal - do NOT add a new probe.

## Backend

Backend Python/XML (pre-write, Tier-0):

| # | Tool call (example) | Assert |
|---|---|---|
| 0 | `set_active_version(odoo_version='18.0')` | reachability probe + pin (once); pass concrete version on every later call |
| 1 | `model_inspect(model='sale.order', method='fields', odoo_version='18.0')` / `entity_lookup(kind='field', model='sale.order', field='amount_total', odoo_version='18.0')` | EXISTENCE + type + declaring module |
| 2 | `lookup_core_api(name='name_get', odoo_version='18.0')` per DIRECTLY-called core symbol | CURRENCY: `stable`; else replacement (`name_get -> _compute_display_name`). N=0 for pure custom |
| 3 | `lint_check(code=<python hunk>, odoo_version='18.0', language='python')` when overriding / reusing a remembered idiom | FLOOR: removed decorators/sigs (`@api.multi`) that `lookup_core_api` misses; trust `[pattern]` |
| 4 | `validate_domain(model='sale.order', domain="[('state','=','draft')]", odoo_version='18.0')` / `resolve_orm_chain(model='sale.order', dotted_path='partner_id.country_id.code', odoo_version='18.0')` / `validate_relation(model='sale.order', field='partner_id', target_model='res.partner', odoo_version='18.0')` | ORM-path correctness pre-write |
| - | POST-write: `validate_depends(model='sale.order', method='_compute_x', odoo_version='18.0')` | depends paths - method not indexed until it exists |

XML has NO snippet-level validator: `lint_check` with `language='xml'` IGNORES its `code` arg.
XML currency = `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` §XML views +
`entity_lookup(kind='view', xmlid='account.view_move_form', odoo_version='18.0')` for referenced
xml_ids + `model_inspect` for surfaced fields.

## Frontend

Frontend JS/OWL/SCSS (pre-write, Tier-0) - `lookup_core_api` is NOT the JS authority:

| # | Tool call (example) | Assert |
|---|---|---|
| 0 | `set_active_version(odoo_version='18.0')` | pin |
| 1 | `module_inspect(name='web', method='owl', odoo_version='18.0')` (or `'qweb'`/`'js'`) | existing component/patch-chain existence |
| 2 | `api_version_diff(symbol='web.Widget', from_version='16.0', to_version='18.0')` + `find_examples(query='OWL patch FormController', odoo_version='18.0')` | JS currency (the Python-only `lookup_core_api` returns not-found here); pivots §JavaScript/OWL for module header / `patch()` arity |
| 3 | `resolve_stylesheet(module='web', odoo_version='18.0')` + `find_style_override(selector_or_variable='--primary', odoo_version='18.0')` | token currency (no invented `--bs-*`) |
| 4 | `bash scripts/verify-frontend.sh <files>` (post-write) | eslint + OWL pitfall gate (already wired) |

## Test

Test (pre-write, Tier-0) - split by symbol class:

| # | Tool call (example) | Assert |
|---|---|---|
| 0 | `set_active_version(odoo_version='18.0')` | pin |
| 1 | `test_base_classes(odoo_version='18.0')` | base-class currency (the tool states each class's window/deprecation/removal for the queried version - see `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3; `cr.commit()` forbidden) - already wired; NOT `lookup_core_api` |
| 2 | `js_test_inspect(module='account', odoo_version='18.0')` | JS-framework currency (Hoot v18+ vs QUnit) - already wired; NOT `lookup_core_api` |
| 3 | `lookup_core_api(name='<core ORM/action method>', odoo_version='18.0')` for setUp/factory/assert symbols | CURRENCY of core ORM/action symbols the test calls only |
| 4 | `model_inspect(model='account.move', method='fields', odoo_version='18.0')` + `resolve_orm_chain(model='account.move', dotted_path='partner_id.country_id.code', odoo_version='18.0')` | create()/assert field names + relational paths |
| - | adapt mode only: `api_version_diff(symbol='name_get', from_version='17.0', to_version='18.0')` | cross-version rename mapping (already wired) |

## Review

Review (per touched symbol):

| # | Tool call (example) | Assert |
|---|---|---|
| 0 | `set_active_version(odoo_version='18.0')` | pin (already) |
| 1 | `entity_lookup(kind='field', model='sale.order', field='amount_total', odoo_version='18.0')` / `model_inspect(model='sale.order', method='fields', odoo_version='18.0')` | EXISTENCE - a miss is CRITICAL (already) |
| 2 | `lookup_core_api(name='<symbol>', odoo_version='18.0')` + `lint_check(code=<hunk>, odoo_version='18.0', language='python')` per touched core symbol | CURRENCY - present-but-deprecated = HIGH; removed-decorator = HIGH |
| 3 | Tier-1 (fp/ diff, or rename/removal in the diff): `api_version_diff(symbol='sale.order.x', from_version='17.0', to_version='18.0')` + `impact_analysis(entity_type='field', entity_name='sale.order.x', odoo_version='18.0')` | cross-version status + blast radius |
| - | `find_deprecated_usage(odoo_version='18.0')` ONLY if the diff is already indexed/merged (corpus) - else `lint_check` is the pre-merge substitute | corpus deprecations (post-merge only) |
