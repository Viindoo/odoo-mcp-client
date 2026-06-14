# Visual Regression Examples

## Example 1 — upgrade regression v16 → v17

Prompt: "We upgraded from Odoo 16 to 17 — did any backend screens change visually?"

- Round 0: context → `odoo_version: 17.0`; ask source = 16.0; base URLs for both; `screenshot_baseline_dir`.
- Round 1: `api_version_diff(symbol='web', from_version='16.0', to_version='17.0')` + `module_inspect(name=<module>, method='views', odoo_version='<version>')` → scope to affected screens.
- Round 2: capture baseline on the v16 instance.
- Round 3: capture current on the v17 instance; diff pairs.
- Round 4: report DRIFTED form header + UNCHANGED list view, with both screenshots.

## Example 2 — SCSS change drift

Prompt: "I changed our brand SCSS variable — what screens drifted?"

- Round 1: `find_style_override(selector_or_variable='$o-brand-primary', odoo_version='<version>')` → modules/screens touched.
- Rounds 2-3: capture before/after for those screens at 375/768/1280.
- Round 4: report drift; flag any drifted screen outside the predicted set as a surprise.
