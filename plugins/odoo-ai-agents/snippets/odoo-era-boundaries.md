<!-- SSOT snippet. The four canonical Odoo era boundaries (frontend framework, test framework,
     SavepointCase alias window, known OSM-annotation carve-out). Every file that states one of
     these boundaries MUST cross-ref here, NOT restate a divergent value - this is the single
     source these facts drift from (drift already happened once: it produced the V-08 and V-43
     defects this snippet fixes).
     Consumers: snippets/read-before-write-contract.md, agents/odoo-backend-coder.md,
     agents/odoo-frontend-coder.md, agents/odoo-solution-architect.md,
     skills/odoo-forward-port/SKILL.md, skills/odoo-deprecation-audit/SKILL.md,
     skills/odoo-test-writing/SKILL.md, agents/odoo-intent-extractor.md,
     docs/odoo-ui-knowledge.md, agents/odoo-ui-reviewer.md, agents/odoo-ui-debugger.md,
     skills/odoo-risk-overview/SKILL.md.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md. -->

# Odoo Era Boundaries - SSOT

Four version boundaries every version-aware Odoo skill/agent must apply. Determine the target
version FIRST (`set_active_version` / the resolved target series), THEN look up the row below -
never infer an era from a version range restated elsewhere.

| # | Boundary | Rule | OSM evidence (re-verified) |
|---|---|---|---|
| 1 | Frontend framework (module/import system) | **Legacy AMD/Widget/OWL-1 = v8-v14.** **Modern ES6 module system = v15+.** v15 is a compat-shim bridge - the `/** @odoo-module **/` + ES6 import/export system is canonical there, and the legacy `odoo.define()` AMD module system still loads via a compat shim (deprecated). The legacy module system is REMOVED at v16. Rate/diagnose a screen as "Legacy era" (module system absent OWL-as-default-path) for v8-v14, "OWL era" (some OWL version is the default component path) for v15+. | `suggest_pattern('OWL component field widget', v14, js)` -> `owl-abstract-field-v14` / `legacy-widget-extend-v14` (`odoo.define(...)` + OWL 1 + `Widget.extend` + `_super`; gotcha: "in v15+ use `/** @odoo-module **/` + ES6"). `suggest_pattern(..., v15, js)` -> `odoo-module-owl2-component-v15` (`/** @odoo-module **/` + component-based OWL; "legacy module system works in v15 via compat shim but is deprecated ... removed in v16"). |
| 1b | Frontend framework (OWL library major version - finer axis, do NOT conflate with #1) | The OWL **library** itself is 1.x (global `owl.*` namespace, `owl.hooks`, no `@odoo/owl` import) through v15 (v15 is a transition release: ES6 modules per #1, but still OWL 1.4.11); OWL **2.x** (`@odoo/owl` import, class-level `patch()`, static `template`/`props`) lands at **v16**. When diagnosing an OWL COMPONENT bug (not just a module-loading bug), use THIS row, not row 1 - applying an OWL-2 idiom (2-arg `patch`, `@odoo/owl` import) to a v15 target is wrong. Full catalogue: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (Era 1/2/3). |
| 2 | Test framework | **QUnit through v17.0.** **Hoot replaces QUnit at v18.0.** | `js_test_inspect(web, v17)` -> qunit 248 files, 0 hoot. `js_test_inspect(web, v18)` -> hoot 262 files (dominant) + qunit 16 residual + tour 1. |
| 3 | `SavepointCase` alias window | Does not exist v8-v11. **Distinct, non-deprecated class on v12-v15** (introduced ~v12; runs `setUpClass` inside a savepoint). **Deprecated alias of `TransactionCase` from v16+** (v16 absorbed the class-level savepoint/`setUpClass` behavior into `TransactionCase`). Adapt call sites to `TransactionCase` ONLY when the target series is v16+; keep `SavepointCase` on v12-v15 targets. | Odoo `odoo/tests/common.py` history (first-principles derivation; `api_version_diff(symbol='SavepointCase', from_version='15.0', to_version='16.0')` and the v16->v17 equivalent both return "not found in either" - it is a test base class, not a `CoreSymbol`, so `api_version_diff` cannot resolve this boundary directly). |
| 4 | Known OSM-annotation bug (single-symbol carve-out) | OSM `test_base_classes(SavepointCase)` returns the STATIC, version-invariant string `(deprecated alias, v8-v15)` for every version queried, including v17/v18. This string is WRONG two ways: SavepointCase did not exist v8-v11, and on v12-v15 it was a distinct non-deprecated class, not an alias. Treat this annotation string as advisory FOR THIS SYMBOL ONLY and apply boundary #3 above instead. Do NOT force a `TransactionCase` rewrite on a v12-v15 target on the strength of this string. This is a documented, single-symbol carve-out on a known server-side bug in the SEPARATE OSM-server repo (this client repo cannot fix it) - it does NOT invert OSM-first precedence generally; OSM stays PRIMARY for every other structural fact. | `test_base_classes(SavepointCase, v12/v15/v16/v17/v18)` -> identical `(deprecated alias, v8-v15)` string on every call, even where SavepointCase should not be listed as deprecated (v12-v15) or should not exist at all (pre-v12, absent from the range). |

## How to apply

- A same-era version bump (e.g. v16->v17) is a smaller migration/risk event than a cross-boundary
  bump (e.g. v14->v15 frontend shift, or v17->v18 test-framework shift) - weight risk/effort
  estimates and defect classification accordingly.
- Rate or diagnose a legacy-era (v8-v14) screen against LEGACY break signals, not OWL-specific
  ones - do not force-fit a legacy failure into an OWL defect class.
- Row 4 is a narrow, documented exception. It applies ONLY to the `SavepointCase` annotation
  string returned by `test_base_classes`; every other OSM call and every other symbol keeps
  standard OSM-first precedence.
