<!-- SSOT snippet. The four canonical Odoo era boundaries (frontend framework, test framework,
     SavepointCase absorb/adapt boundary, OSM test_base_classes static-annotation bug). Every file
     that states one of these boundaries MUST cross-ref here, NOT restate a divergent value - this
     is the single source these facts drift from (drift already happened once: it produced the V-08
     and V-43 defects this snippet fixes).
     Consumers (files that actually cite this snippet): skills/odoo-forward-port/SKILL.md,
     skills/odoo-deprecation-audit/SKILL.md, skills/odoo-test-writing/SKILL.md,
     agents/odoo-intent-extractor.md, docs/odoo-ui-knowledge.md, agents/odoo-ui-reviewer.md,
     agents/odoo-ui-debugger.md, skills/odoo-risk-overview/SKILL.md.
     (The coder/architect files - read-before-write-contract.md, odoo-backend-coder,
     odoo-frontend-coder, odoo-solution-architect - use the coding_guidelines/14.0 fallback for a
     DIFFERENT fact and do NOT cite this snippet; they are intentionally not listed here.)
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
| 3 | `SavepointCase` absorb/adapt boundary | Does not exist v8-v11. **Distinct, non-deprecated class on v12-v14** (introduced ~v12; runs `setUpClass` inside a savepoint). **At v15, `TransactionCase` absorbed the class-level savepoint/`setUpClass` behavior and `SavepointCase` became a deprecated alias of it** - Odoo core migrated its own test classes off `SavepointCase` in that release. Adapt call sites to `TransactionCase` on target series **>= v15**; keep `SavepointCase` only on v12-v14 targets. | OSM usage graph: `test_class_inspect(SavepointCase, odoo_version=<target>, method='summary')` "Subclassed by" collapses **209 (v14) -> 2 (v15)** and stays flat thereafter, with the mirror-image `TransactionCase` jump **352 -> 616**; `AccountTestInvoicingCommon` / `MailCommon` / `TestSaleProject` all switch base `SavepointCase` -> `TransactionCase` exactly at v14->v15 (`test_class_inspect(..., method='hierarchy')`). `api_version_diff('SavepointCase', ...)` returns "not found" (it is a test base class, not a `CoreSymbol`) - resolve this boundary from the usage graph, NOT from `api_version_diff` or the static `test_base_classes` tag (row 4). |
| 4 | OSM `test_base_classes` static-annotation bug (version-invariant per-class tags) | `test_base_classes` emits per-class version tags that are STATIC / version-invariant - the SAME string at every queried version, so they are NOT a reliable source for any version-sensitive claim. For `SavepointCase` it returns `(deprecated alias, v8-v15)` on every call (v12, v15, v16, v17, v18 alike); that string is WRONG - `SavepointCase` did not exist v8-v11, and on v12-v14 it was a distinct non-deprecated class, so the real absorb/adapt boundary is **v15** (row 3), not the `v15` upper-bound the string implies. This is NOT unique to `SavepointCase`: every class's tag is emitted the same way (e.g. `TreeCase (v14+)`, `BaseCase (v10+)` appear even when queried at v8). So: treat any `test_base_classes` per-class version tag as advisory, and verify any version-sensitive class claim against the OSM usage graph (`test_class_inspect(..., method='hierarchy')`) before trusting it. This is a known server-side bug in the SEPARATE OSM-server repo (this client repo cannot fix it); it does NOT invert OSM-first precedence generally - OSM stays PRIMARY for every other structural fact. | `test_base_classes(SavepointCase, v12/v15/v16/v17/v18)` -> identical `(deprecated alias, v8-v15)` on every call; `test_base_classes` queried at v8 also emits `TreeCase (v14+)` / `BaseCase (v10+)` verbatim - the tag never varies with the queried version. |

## How to apply

- A same-era version bump (e.g. v16->v17) is a smaller migration/risk event than a cross-boundary
  bump (e.g. v14->v15 frontend shift, or v17->v18 test-framework shift) - weight risk/effort
  estimates and defect classification accordingly.
- Rate or diagnose a legacy-era (v8-v14) screen against LEGACY break signals, not OWL-specific
  ones - do not force-fit a legacy failure into an OWL defect class.
- Row 4 covers a known OSM-server bug in `test_base_classes`' per-class version tags (they never
  vary with the queried version, so they cannot resolve any version boundary). It does NOT invert
  OSM-first precedence: every other OSM call and every structural fact keeps OSM as PRIMARY - only
  these static per-class tags need the usage-graph cross-check
  (`test_class_inspect(..., method='hierarchy')`) before a version-sensitive claim is trusted.
