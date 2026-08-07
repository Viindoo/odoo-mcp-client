# upg-classification-table - module action taxonomy + breaking-change catalog

Used by: P2 `odoo-diff-comparator` brief, P4 `odoo-coding` brief, and the P3 Plan Mode
gate. NO data-migration content.

---

## 1. Module action taxonomy

### Action definitions

| Action | When to apply | Key signal |
|--------|---------------|------------|
| **DELETE-absorbed** | Target-version core fully provides EVERY feature this module adds | OSM `check_module_exists` + `module_inspect` confirms the core module at target; `api_version_diff` or `model_inspect` confirms the relevant models/fields exist in core |
| **KEEP** | Custom logic the module provides is not in core at target; all APIs it calls are stable | `api_version_diff` shows no Removed/Changed entries for the symbols this module uses |
| **REWRITE(api)** | Custom logic still needed; the APIs it calls changed or were removed at target | `api_version_diff` shows Removed/Changed for >=1 symbol this module calls; custom nghiệp vụ (business logic) is intact |
| **REWRITE(model)** | A model the module extends has structural changes (field renamed, type changed, removed) at target | `model_inspect` on the extended model at target shows field absent or type-changed |
| **MERGE** | Two or more modules in the cluster address the same business domain and can be consolidated into one at target | Shared model extension + shared views + no external dependers outside the cluster |
| **SPLIT** | A single module has grown to cover multiple unrelated domains; splitting improves maintainability + target installability | Module has >1 unrelated model domains with separate dependency trees |
| **RECONCILE** | EITHER (a) target-core newly writes/computes the SAME business quantity on the SAME records as the custom code (data-divergence: two SSOTs), OR (b) target-core gained a NEW mechanism/API that can replace or materially simplify the custom implementation (new-feature wire-in). The custom intent survives, but the SSOT/wire-in choice is architectural -> MUST route to P2b design (odoo-solution-design); never silently KEEP/coexist | `api_version_diff` shows a NEW core compute/field on the same model+records the custom code writes (a), or a `new` API entry covering the custom feature's acceptance criteria (b); triangulate with `model_inspect` / `suggest_pattern` / `find_examples` |
| **OBSOLETE** | The module's entire purpose is moot at target because core changed the underlying workflow or replaced the mechanism, but there is NO named core module/feature that directly absorbs it (it is deprecated because the need evaporated, not because a feature absorbed it) | OSM shows the workflow or mechanism the module customized no longer exists or is irrelevant at target; no single `absorbing_core_feature` can be honestly named |

### "Core absorbed it" signals (positive)

Use ALL of the following to confirm DELETE-absorbed. A single signal is insufficient.

1. `check_module_exists(name='<candidate_core_module>', odoo_version='<target_version>')` returns
   `exists: true, edition: CE|EE` - the core module exists at target.
2. `module_inspect(name='<candidate_core_module>', method='models', odoo_version='<target_version>')`
   lists a model that covers the custom module's primary domain.
3. `model_inspect(model='<custom_model>', method='fields', odoo_version='<target_version>')` -
   if the custom model is now an extension of a core model that provides the same fields,
   the custom extension adds zero net behavior.
4. `api_version_diff` for the custom module's key methods shows them present and unchanged
   in core at target (the functionality is there natively).
5. **Behavioral equivalence (MANDATORY - no DELETE without it).** Enumerate every override
   the custom module adds (`create`/`write`/`unlink`/`_compute_*`/`_constrains`/
   `@api.onchange`/action methods/SQL constraints) via
   `model_inspect(model='<model>', method='methods', odoo_version='<target_version>')` + grep of the module source. For EACH override,
   prove that the target-version core produces the SAME observable effect, OR that the
   override is now a no-op against core behavior. If ANY override has no core equivalent
   with the same effect, the module is NOT DELETE-absorbed - it is at most REWRITE/MERGE.
   Record this proof in `absorption/<module>.md` under a `behavioral_equivalence` section.
   **"Core defines the model" is necessary, never sufficient.**

### "Core absorbed it" risk signals (require human confirmation in plan)

Raise as a risk in `plan.md` when any of these hold:

- The custom module has a field that stores data not present in the core model at target
  (structural data loss risk if deleted without migration).
- The custom module has `ir.model.access` / `ir.rule` records beyond the core's grants.
- The custom module has a `noupdate="1"` data record not present in core.
- External dependers OUTSIDE the cluster depend on the custom module (check `validate_depends`
  or grep the rest of the repo for `depends` containing the module name).

In these cases, mark as `DELETE-absorbed (with risk)` in the absorption verdict, list the
risks in plan.md, and require explicit user confirmation at the P3 gate.

---

## 2. Cross-major breaking-change catalog

Apply to all KEEP / REWRITE / MERGE / SPLIT modules in P4. The `odoo-coding` brief cites
this catalog; its coder applies every relevant item. The "Affected versions" column is
indicative and frozen at v18; new pivots live ONLY in
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` (F0) - consult it for v19+. Verify there
(and via OSM `api_version_diff` at target) before applying.

### Python / ORM API breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `@api.multi` decorator removed | v13+ | Remove decorator; methods now implicitly multi-record |
| `@api.one` decorator removed | v13+ | Remove decorator; return a scalar, not a list |
| `_columns` dict removed | v13+ | Use `fields.*` class attributes |
| `osv.osv` / `orm.TransientModel` (old-style) | v13+ | Inherit from `models.Model` / `models.TransientModel` |
| `ir.values` model removed | v13+ | Use `ir.default` for user defaults |
| `name_get()` overrides | v17 deprecated (WARN); **v18+ REMOVED** | Replace with `_compute_display_name()` compute field |
| `fields_view_get()` override | v16 deprecated; **v17+ REMOVED** | Replace with `get_views()` (new signature) |
| `attrs` / `states` view attribute (Python-eval) | v17+ | Replace with `invisible` / `required` / `readonly` domain-style attributes |
| `cr.commit()` in tests | all | FORBIDDEN inside `TransactionCase` / `SavepointCase`; remove or restructure test |
| `SavepointCase` used in tests | **v15-v16** WARN (deprecated, still real); **v17+** BREAKING (removed - import failure) - see `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 | Migrate to `TransactionCase` (mandatory at v17+, cleanliness at v15-v16; keep on v8-v14) |

### View / QWeb breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `<tree>` tag renamed to `<list>` | **v18+** (at v17 `<tree>` is still canonical; `<list>` is unknown pre-v18) | Replace `<tree>` with `<list>` in all XML views |
| `<form>` `string=` attribute on groups | check per version | Validate against `model_inspect(model='<model>', method='views', odoo_version='<target_version>')` at target |
| `<field widget="...">` legacy widgets | v14-v17+ | Check widget availability at target; OWL widgets may need replacing |
| `attrs` / `states` on form/tree fields | v17+ | Migrate to domain-based `invisible` / `required` / `readonly` attributes |
| `domain=` referencing removed fields | any | Update domains when fields renamed/removed at target |

### JavaScript / OWL / SCSS breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `odoo.define()` / `web.Widget` / `AbstractField` | v14-v15 (deprecated) - NOT removed at v16; absent from the OSM index by v18 | Rewrite as OWL component with `patch()` / `useState` / `useService` |
| `FieldWidget` / `AbstractField` from web module | v14 (deprecated) - NOT removed at v16; absent from the OSM index by v18 | Route to `odoo-coding` (frontend leg) for OWL rewrite |
| Legacy asset bundle keys (`web.assets_backend` manifest shape) | v15+ | Update `__manifest__.py` `assets` dict to new bundle format |
| SCSS `@import "variables"` | v16+ | Replace with `@use "variables" as *` + `math.div()` for division |
| `@import` for SCSS files that moved | any | Verify import paths against `module_inspect(name='<module>', method='assets', odoo_version='<target_version>')` at target |
| QUnit tests | v18+ | Migrate to Hoot (`describe/test/expect`) - route to `odoo-coding` (frontend leg) |

### Manifest breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `version` field at source series | any | **Do NOT bump** (Rule A). The manifest `version` uses the SHORT form - 2-3 numeric parts, NO series prefix. Value already short -> leave it byte-identical. Value in LONG form (series-prefixed, `<series>.x.y.z`) -> **CONVERT it to `x.y.z`** by dropping the series prefix and leaving the remaining numbers untouched; a conversion is not a bump. Never add a prefix, never raise a number. Form SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md` §3; upgrade context: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` |
| `depends` listing a module removed at target | any | Remove or replace with the new core module; flag in plan.md |
| `installable: False` carried from source | any | Set to `True` in the P4 manifest edit (after all other P4 fixes are applied), BEFORE P5 is run; P5 confirms the module installs - do NOT leave `installable: False` going into P5 |
| `auto_install: True` with condition that no longer holds | any | Restore only if a `# TODO: Uncomment when upgrading` breadcrumb (left by forward-port) explicitly directs it; do NOT auto-detect |
| `application: True` commented out by forward-port | any | Restore only if a `# TODO: Uncomment when upgrading` breadcrumb explicitly directs it; same guard as `auto_install` |

---

## 3. Install + test verification checklist

Run in P5 after `odoo-instance` completes, before P6 human sign-off.

### Install verification

- [ ] Every module in the cluster emits `Loading module <module>` in the log
- [ ] No `ImportError`, `AttributeError`, or `TypeError` at module load
- [ ] No `odoo.modules.module: Invalid type for _inherit: <str>` (old-style inherit)
- [ ] No `Field <field> is not valid for model <model>` (field reference to removed field)
- [ ] No `External ID not found in the system: <xmlid>` in data XML
- [ ] `installable: True` in every adapted module's manifest
- [ ] Scanned each module descriptor (`__manifest__.py`, or `__openerp__.py` on v8-v9) for the `# TODO: Uncomment when upgrading` breadcrumb and honored it (restored `auto_install`/`application` only when the breadcrumb directed)
- [ ] Manifest `version` uses the short form, no series prefix, and is NOT bumped from the source value - a value that arrived series-prefixed was CONVERTED to `x.y.z`, not bumped (remedy: § Manifest breaks, the Rule A row)
- [ ] Existing `migrations/` dirs belonging to lower series are untouched, and no NEW migration script was written (a data-at-risk case routes out to `odoo-data-migration`)

### Test verification

- [ ] Per-module test result is `passed` (not `0 tests, 0 errors` - that means tests didn't run)
- [ ] No `setUpClass` errors (would give false-green `0 failed, N error(s)`)
- [ ] No `cr.commit()` in test files
- [ ] No test referencing a model/field removed at target (from deprecation.md)
- [ ] Confirmed RED-then-GREEN for any test adapted in P4 (confirm-by-toggle available)

### Commit structure verification

- [ ] Adapted modules: commit requested via `git-toolkit:git-ops` with business outcome `<module> <src>-><tgt> - <ACTION> <summary>`; git-ops composed the message
- [ ] Absorbed-deleted modules: commit requested via `git-toolkit:git-ops` with business outcome `delete <module> - absorbed by core <core> in <tgt> (no custom delta remains)`; git-ops composed the message
- [ ] Obsolete-deleted modules: commit requested via `git-toolkit:git-ops` with business outcome `delete <module> - obsolete at <tgt> (<one-line reason why the need evaporated>)` (do NOT invent a fake `absorbing_core_feature`); git-ops composed the message
- [ ] No squash commits
- [ ] Each deleted module's name removed from all dependers' `depends` in the cluster
