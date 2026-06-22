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
| **OBSOLETE** | The module's entire purpose is moot at target because core changed the underlying workflow or replaced the mechanism, but there is NO named core module/feature that directly absorbs it (it is deprecated because the need evaporated, not because a feature absorbed it) | OSM shows the workflow or mechanism the module customized no longer exists or is irrelevant at target; no single `absorbing_core_feature` can be honestly named |

### "Core absorbed it" signals (positive)

Use ALL of the following to confirm DELETE-absorbed. A single signal is insufficient.

1. `check_module_exists(name='<candidate_core_module>', odoo_version='auto')` returns
   `exists: true, edition: CE|EE` - the core module exists at target.
2. `module_inspect(name='<candidate_core_module>', method='models', odoo_version='auto')`
   lists a model that covers the custom module's primary domain.
3. `model_inspect(model='<custom_model>', method='fields', odoo_version='auto')` -
   if the custom model is now an extension of a core model that provides the same fields,
   the custom extension adds zero net behavior.
4. `api_version_diff` for the custom module's key methods shows them present and unchanged
   in core at target (the functionality is there natively).
5. **Behavioral equivalence (MANDATORY - no DELETE without it).** Enumerate every override
   the custom module adds (`create`/`write`/`unlink`/`_compute_*`/`_constrains`/
   `@api.onchange`/action methods/SQL constraints) via
   `model_inspect(model='<model>', method='methods', odoo_version='auto')` + grep of the module source. For EACH override,
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

Apply to all KEEP / REWRITE / MERGE / SPLIT modules in P4. The `odoo-coder` brief cites
this catalog; the coder applies every relevant item.

### Python / ORM API breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `@api.multi` decorator removed | v14+ | Remove decorator; methods now implicitly multi-record |
| `@api.one` decorator removed | v14+ | Remove decorator; return a scalar, not a list |
| `_columns` dict removed | v13+ | Use `fields.*` class attributes |
| `osv.osv` / `orm.TransientModel` (old-style) | v13+ | Inherit from `models.Model` / `models.TransientModel` |
| `ir.values` model removed | v13+ | Use `ir.default` for user defaults |
| `name_get()` overrides | v17+ | Replace with `_compute_display_name()` compute field |
| `fields_view_get()` override | v17+ | Replace with `get_views()` (new signature) |
| `_sql_constraints` list of tuples | v17+ | Use `models.Constraint` objects (new API) |
| `attrs` / `states` view attribute (Python-eval) | v17+ | Replace with `invisible` / `required` / `readonly` domain-style attributes |
| `cr.commit()` in tests | all | FORBIDDEN inside `TransactionCase` / `SavepointCase`; remove or restructure test |
| `SavepointCase` alias | v16+ WARN, v18+ BREAKING | Migrate to `TransactionCase` |

### View / QWeb breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `<tree>` tag renamed to `<list>` | v17+ | Replace `<tree>` with `<list>` in all XML views |
| `<form>` `string=` attribute on groups | check per version | Validate against `model_inspect(model='<model>', method='views', odoo_version='auto')` at target |
| `<field widget="...">` legacy widgets | v14-v17+ | Check widget availability at target; OWL widgets may need replacing |
| `attrs` / `states` on form/tree fields | v17+ | Migrate to domain-based `invisible` / `required` / `readonly` attributes |
| `domain=` referencing removed fields | any | Update domains when fields renamed/removed at target |

### JavaScript / OWL / SCSS breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `odoo.define()` / `web.Widget` / `AbstractField` | v14 (deprecated) -> v16 (removed) | Rewrite as OWL component with `patch()` / `useState` / `useService` |
| `FieldWidget` / `AbstractField` from web module | v16+ removed | Route to `odoo-frontend-coder` for OWL rewrite |
| Legacy asset bundle keys (`web.assets_backend` manifest shape) | v15+ | Update `__manifest__.py` `assets` dict to new bundle format |
| SCSS `@import "variables"` | v16+ | Replace with `@use "variables" as *` + `math.div()` for division |
| `@import` for SCSS files that moved | any | Verify import paths against `module_inspect(name='<module>', method='assets', odoo_version='auto')` at target |
| QUnit tests | v18+ | Migrate to Hoot (`describe/test/expect`) - route to `odoo-frontend-coder` |

### Manifest breaks

| Break | Affected versions | Fix |
|-------|------------------|-----|
| `version` field still at source series | any | Bump to `<target_series>.X.Y.Z` (e.g. `16.0.1.0.0` -> `17.0.1.0.0`) |
| `depends` listing a module removed at target | any | Remove or replace with the new core module; flag in plan.md |
| `installable: False` carried from source | any | Set to `True` in the P4 manifest bump (after all other P4 fixes are applied), BEFORE P5 is run; P5 confirms the module installs - do NOT leave `installable: False` going into P5 |
| `auto_install: True` with condition that no longer holds | any | Review trigger condition against target module list |

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
- [ ] Manifest `version` field uses the target series prefix

### Test verification

- [ ] Per-module test result is `passed` (not `0 tests, 0 errors` - that means tests didn't run)
- [ ] No `setUpClass` errors (would give false-green `0 failed, N error(s)`)
- [ ] No `cr.commit()` in test files
- [ ] No test referencing a model/field removed at target (from deprecation.md)
- [ ] Confirmed RED-then-GREEN for any test adapted in P4 (confirm-by-toggle available)

### Commit structure verification

- [ ] Adapted modules: commit message format `upg: <module> <src>-><tgt> - <ACTION> <summary>`
- [ ] Absorbed-deleted modules: commit message format `upg: delete <module> - absorbed by core <core> in <tgt> (no custom delta remains)`
- [ ] Obsolete-deleted modules: commit message format `upg: delete <module> - obsolete at <tgt> (<one-line reason why the need evaporated>)` (do NOT invent a fake `absorbing_core_feature`)
- [ ] No squash commits
- [ ] Each deleted module's name removed from all dependers' `depends` in the cluster
