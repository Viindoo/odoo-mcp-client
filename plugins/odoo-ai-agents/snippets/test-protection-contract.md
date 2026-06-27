<!-- SSOT for "what tests guard what" methodology.
     Consumers: odoo-coder (Round 2 test-protection pre-flight),
                odoo-frontend-coder (Round 0 step 8 test-protection pre-flight),
                odoo-deep-survey (Phase 2 L9 lens + synthesis tests_protecting section).
     Never restate the tier definitions or tool names in consuming files - cross-ref this file. -->

# Test-Protection Contract

For every model/field/method/view/component you **touch**, identify which tests already guard it
**before writing code**. A change that silently breaks a protecting test is worse than a feature gap.

## Three tiers

**(i) Own-module tests.** Discover the module's own `TestCase` classes via
`module_inspect(name='<module>', method='tests', odoo_version='<version>')`. Per model/field/method:
`tests_covering(model='<model>', odoo_version='<version>')` is the primary probe. COVERS_METHOD
edges are sparse - 0 results do NOT mean untested; fall through to
`find_test_examples(query='<method_or_field_name>', odoo_version='<version>')`. Field-level gap
audit: `test_coverage_audit(module='<module>', odoo_version='<version>')`.

Frontend targets (JS/OWL/template): `find_test_examples(query='<component_or_template_id>', kind='js', odoo_version='<version>')` + `js_test_inspect(module='<module>', odoo_version='<version>')` (framework-aware per module - do not map version to framework from memory; the mix varies by module).

OSM MISS (empty result for a symbol the repo says exists): label `grounded: local-source`, read
`<module>/tests/` on disk before concluding zero coverage.

**(ii) Base/dependency tests.** Tests in `base` or depended-on modules that exercise the SAME
model/view - a custom field on `res.partner` is also walked by core partner tests. Ground with
`tests_covering` on the CORE model + `impact_analysis(entity_type='model', entity_name='<model>', odoo_version='<version>')`
to find which dependent-module tests reach it.

**(iii) Framework-validation + lint gates.** Always-on; OSM does NOT index these. Cross-ref
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md` for the
full gate list + reproduction steps; mark each "verify against live test class":
- `base.TestInvisibleField` - v18+ always-invisible view fields need an explanatory XML comment.
- `hr.TestSelfAccessProfile` - custom `hr.employee` fields need `groups=`.
- `test_lint` - Odoo CE static lint gate (v14+); the authoritative backend code-quality CI gate.
- `test_pylint` (flake8 + extended static analysis) - Viindoo tvtmaaddons only (v16+); run alongside `test_lint` on v16+ Viindoo profiles.

## MUST-NOT-BREAK

Tier (i) + (ii) = MUST-NOT-BREAK. Record the assembled list in the worklog under `PROTECTION_SCOPE`
before writing code. Every test on the list must still pass after your change.

Tier (iii) = framework requirements - check the parity checklist unconditionally, independent of
whether the touched models/views appear in the feature-test list.

## Protocol rules

- Pass the **concrete** `odoo_version` on every OSM call - never `'auto'`.
- Apply per entity you TOUCH, not just the primary target.
- Run unconditionally - do not skip because a deep-survey artifact does or does not exist.
