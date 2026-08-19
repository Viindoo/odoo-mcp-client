<!-- SSOT snippet. The seven canonical Odoo era boundaries (frontend framework, test framework,
     SavepointCase absorb/adapt boundary, `test_base_classes` authority + corroboration rule, core
     package directory, module manifest filename, core stylesheet language) PLUS the ordered
     procedure for deriving a series from a checkout, which the core-package-directory and
     manifest-filename boundaries govern. Every
     file that states one of these boundaries MUST cross-ref here, NOT restate a divergent value -
     this is the single source these facts drift from (drift already happened once: it produced the
     V-08 and V-43 defects this snippet fixes).
     Consumers are DERIVED, never listed here - re-derive with
     `grep -rl "odoo-era-boundaries.md" plugins/odoo-ai-agents/`.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md. -->

# Odoo Era Boundaries - SSOT

Seven version boundaries every version-aware Odoo skill/agent must apply. Determine the target
version FIRST (`set_active_version` / the resolved target series), THEN look up the row below -
never infer an era from a version range restated elsewhere. Rows 5 and 6 run the other direction:
they are what makes the target series READABLE off a checkout when nothing has declared it - see
§ Series derivation from a checkout.

| # | Boundary | Rule | OSM evidence (re-verified) |
|---|---|---|---|
| 1 | Frontend framework (module/import system) | **Legacy AMD/Widget/OWL-1 = v8-v14.** **Modern ES6 module system = v15+.** v15 is a compat-shim bridge - the `/** @odoo-module **/` + ES6 import/export system is canonical there, and the legacy `odoo.define()` AMD module system still loads via a compat shim. `odoo.define()` AMD is DEPRECATED from v15, and stays loadable via that compat shim through at least v17 - it is NOT removed at v16; finer detail: `odoo-version-pivots.md`. Rate/diagnose a screen as "Legacy era" (module system absent OWL-as-default-path) for v8-v14, "OWL era" (some OWL version is the default component path) for v15+. | `suggest_pattern('OWL component field widget', v14, js)` -> `owl-abstract-field-v14` / `legacy-widget-extend-v14` (`odoo.define(...)` + OWL 1 + `Widget.extend` + `_super`; gotcha: "in v15+ use `/** @odoo-module **/` + ES6"). `suggest_pattern(..., v15, js)` -> `odoo-module-owl2-component-v15` (`/** @odoo-module **/` + component-based OWL). `find_examples('odoo.define module system boot loader', v16)` -> `web/static/src/boot.js` (the legacy AMD loader) plus live `odoo.define('web.core', ...)` / `odoo.define('web.view_registry', ...)` / `odoo.define('web.mvc', ...)` call sites still shipping at v16 - legacy module system present, NOT removed. `find_examples(..., v17)` -> `web/static/src/module_loader.js` exposes `odoo.define = loader.define.bind(loader)` (compat shim over the new `ModuleLoader.define(name, deps, factory)`), with a live call site still using it: `addons/spreadsheet/static/src/o_spreadsheet/odoo_module.js` -> `odoo.define("@odoo/o-spreadsheet", [...], function (require) {...})`. So `odoo.define()` is present and loadable at BOTH v16 and v17. |
| 1b | Frontend framework (OWL library major version - finer axis, do NOT conflate with #1) | The OWL **library** itself is 1.x (global `owl.*` namespace, `owl.hooks`, no `@odoo/owl` import) through v15 (v15 is a transition release: ES6 modules per #1, but still OWL 1.4.11); OWL **2.x** (`@odoo/owl` import, class-level components, static `template`/`props`) lands at **v16**. DECOUPLED axis - do NOT read patch arity off this boundary: the `@web/core/utils/patch` SIGNATURE is 3-arg `patch(proto, name, obj)` at **v15 AND v16** (unchanged from the legacy calling convention), changing to 2-arg `patch(proto, obj)` only at **v17** (the `name` parameter is dropped there). A 2-arg `patch()` call is a **v17** marker, NOT a v16 marker. When diagnosing an OWL COMPONENT bug (not just a module-loading bug), use THIS row, not row 1 - applying the v17 2-arg `patch` idiom to a v15/v16 target is wrong, and applying the v15/v16 3-arg idiom to a v17 target is equally wrong. Full catalogue: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (Era 1/2/3). | `find_examples('patch', v15)` -> real 3-arg call site `patch(routerService, "studio_action_path", {...})` (viin_studio router service; `name` param present). `find_examples('patch', v16)` -> `@web/core/utils/patch` internals still route through a 3-arg descriptor form (`patch(obj, patchDesc.name, patchDesc.patch, {...})`); no 2-arg call site found at v16. `find_examples('patch', v17)` -> real call sites are uniformly 2-arg: `patch(imStatusService, imStatusServicePatch)`, `patch(objToPatch, extension)`, `patch(Record.prototype, {...})`, `patch(CodeEditor, {...})` - the `name` parameter is gone. So `@odoo/owl` + class-level components = v16, but 2-arg `patch()` = v17. |
| 2 | Test framework (JS) | **Hoot becomes the DOMINANT JS test framework at v18.0 - it does NOT replace QUnit.** QUnit keeps shipping AND keeps running at v18.0 and v19.0, and a QUnit suite there can still FAIL. So NEVER series-gate a JS reader - a test author, a log parser, a failure counter - to one framework: read BOTH vocabularies on EVERY series, and resolve the actual per-module mix with `js_test_inspect(<module>, <series>)` before choosing one. A green marker from one framework is a verdict for that suite only, never for the run. | `js_test_inspect('web', '17.0', framework='hoot')` -> "No JS test suites indexed"; the same call with `framework='qunit'` -> `Framework mix: qunit (249 files)`. `js_test_inspect('web', '18.0')` -> hoot 263 files + qunit 16 files. `js_test_inspect('web', '19.0')` -> hoot 294 files + qunit 4 files. |
| 3 | Test base-class windows + `SavepointCase` adapt boundary | Windows are BRANCH-HEAD facts (what each series' current branch HEAD contains today), not GA-day snapshots. `TransactionCase` **v8-v19** (absorbs `SavepointCase`'s class-level-savepoint `setUpClass` at **v15**). `SingleTransactionCase` **v8-v19**, never deprecated. `BaseCase` **v8-v19** (abstract mixin). `HttpCase` **v8-v19** (absorbs `HttpSavepointCase`'s class-level savepoint at **v15**). `SavepointCase` **v8-v16**: a REAL, non-deprecated `TransactionCase` subclass v8-v14; still a real class but DEPRECATED at **v15**; **REMOVED at v17** - never a bare `SavepointCase = TransactionCase` alias at any version. `HttpSavepointCase` **v14-v16**, deprecated v15, REMOVED at v17. `TreeCase` **v11-v14 only**. `HttpCaseCommon` **v14 only**. `Form` and `O2MForm` **v12+**, both relocating `odoo/tests/common.py` -> `odoo/tests/form.py` at **v17** (API unchanged). ADAPT RULE: target **>= v15** -> write `TransactionCase` / `HttpCase`; target **>= v17** -> `SavepointCase`/`HttpSavepointCase` DO NOT EXIST, so a surviving import is **BREAKING** (import failure), never a WARN; target **v8-v14** -> `SavepointCase` is legitimate and MUST NOT be flagged as anachronistic. v12 has no significance for this class. TIE-BREAKER: OSM's pattern `test-savepointcase-v8-v15` carries a historical id and a gotcha phrased "use plain TransactionCase for v16+"; THIS row's boundary (deprecated at v15) WINS - the id encodes nothing, and that pattern's own gotcha already says "recommend this pattern for v8-v14". For any base class NOT named here, call `test_base_classes(odoo_version='<target>')`; this row enumerates only the classes whose window CHANGES across v8-v19. | `test_base_classes(name='SavepointCase', odoo_version='17.0')` -> "NOT AVAILABLE ... available 8.0-16.0; deprecated at 15.0 (merged into TransactionCase); removed at 17.0". `test_class_inspect('SavepointCase','8.0')` -> `openerp/tests/common.py:191`; at 15.0 -> `:869` + DEPRECATED; at 17.0 -> "Not found". `TreeCase` at 10.0/15.0 -> Not found; at 11.0 -> `common.py:94`. `HttpCaseCommon` at 13.0/15.0 -> Not found; at 14.0 -> `common.py:1385`. `HttpSavepointCase` at 13.0 -> Not found; at 16.0 -> `common.py:2124` DEPRECATED. `Form`/`O2MForm` at 11.0 -> Not found; at 17.0 -> `form.py:27` / `form.py:604`. Sweep covers all 12 indexed majors v8.0-v19.0. |
| 4 | `test_base_classes` per-class version tags | `test_base_classes` is VERSION-SCOPED: query it with the CONCRETE target version and use its stated window, deprecation point, and removal version directly. The old "treat every per-class tag as advisory / distrust the tool" directive is RETIRED - do not reinstate it, and do not re-derive a window by hand from subclass counts. SCOPE: the FRAMEWORK base menu is authoritative at every indexed major. At v8/v9 the tool additionally prints `era1 - addon-level class hierarchy is regex best-effort`; that caveat applies to ADDON-level subclass counts, NOT to the framework window - do not downgrade the window because of it, and do not quote a v8/v9 subclass count as proof of anything. Standing practice (not a bug workaround, not specific to this tool): before acting DESTRUCTIVELY on a version-sensitive class claim - deleting or rewriting a call site - corroborate with one `test_class_inspect(..., method='hierarchy')` or `find_test_examples(...)` call. OSM-first precedence is unchanged. | Live sweep, all 12 indexed majors: three DISTINCT output shapes for `SavepointCase` - plain entry v8-v14, "DEPRECATED ... merged into TransactionCase" v15-v16, "NOT AVAILABLE ... removed at 17.0" v17-v19. `TreeCase` absent from the v8 menu, present v11-v14; `HttpCaseCommon` only at v14. The tag tracks the queried version. |
| 5 | Core package directory | **`openerp/` = v8.0-v9.0.** **`odoo/` = v10.0+.** The flip lands at **10.0** and is total: in v10+ the `odoo` package replaces `openerp` everywhere, so `from openerp import ...` inside a v10+ addon raises `ImportError`. When locating core FROM a checkout, probe BOTH names - assuming one dir finds nothing at all on the other era, and the miss is silent. | `describe_module('base', <series>)` swept across all 12 indexed series: `Path: openerp/addons/base` at 8.0 and 9.0; `Path: odoo/addons/base` at 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0. `suggest_pattern(..., '10.0')` -> `api-depends-dotted-path-v10`, gotcha verbatim: "In v10 the `odoo` package replaces `openerp` everywhere ... using `from openerp import` in v10 addons raises ImportError". Corroborated by indexed `to_odoo_module` `git.branch._module_manifest_location_valid`, docstring verbatim: `/path/to/odoo/odoo/addons (Odoo source code branch for Odoo 10 or later)` and `/path/to/odoo/openerp/addons (Odoo source code branch for Odoo 9 or earlier)`. |
| 6 | Module manifest (descriptor) filename | **`__openerp__.py` = v8.0-v9.0.** **`__manifest__.py` = v10.0+, and required there.** The flip lands at **10.0**. With BOTH files present in one addon, Odoo loads `__manifest__.py` and silently ignores `__openerp__.py`. Any module-discovery glob MUST cover BOTH names: globbing `__manifest__.py` alone returns nothing on v8.0/v9.0 and hands the next step an empty path instead of an error. | OSM pattern `manifest-transition-v10`, span `v10.0-*`, cited at `addons/sale/__manifest__.py:1`, snippet line 1 verbatim `# v10+ uses __manifest__.py (replaces __openerp__.py)`; gotcha 1 verbatim: "In v9, the descriptor file is `__openerp__.py`; in v10+ it MUST be `__manifest__.py`"; the both-present precedence is that same pattern's gotcha. Core-test corroboration at 16.0/17.0/18.0/19.0: `test_class_inspect('TestModuleManifest', <series>)` -> `odoo/addons/base/tests/test_module.py`, whose `test_default_manifest` body opens `opj(self.module_root, '__manifest__.py')`. |
| 7 | Core stylesheet language | **Plain CSS only at v8.0.** **LESS at v9.0-v11.0** (introduced at 9.0 beside the CSS files; by 10.0 the whole of core `web` is LESS). **SCSS from v12.0 onward**, with a residual `css/reset.min.css` still shipping at v11.0 and v12.0. Stated for core `web` ONLY: an addon may ship any of the three on any series, so resolve the real language per module with `resolve_stylesheet(<module>, <series>)` - and `find_style_override(<selector or variable>, <series>)` for one token - BEFORE writing a theme override. Never infer a module's stylesheet language from the series alone, and never write a LESS override for a target the tool reports as `lang=scss`. | `resolve_stylesheet('web', '8.0')` -> 5 files, every one `lang=css`, zero `.less`. `('web', '9.0')` -> 13 files: 5 `css` + 8 `less`. `('web', '10.0')` -> 34 files, every one `lang=less`. `('web', '11.0')` -> 48 files: 47 `less` + `css/reset.min.css`. `('web', '12.0')` -> 64 files: 63 `scss` + `css/reset.min.css`, zero `.less`. `find_style_override('$o-brand-odoo', '13.0')` -> `web/static/src/scss/webclient_extra.scss`. |

## How to apply

- A same-era version bump (e.g. v16->v17) is a smaller migration/risk event than a cross-boundary
  bump (e.g. v14->v15 frontend shift, or v17->v18 test-framework shift) - weight risk/effort
  estimates and defect classification accordingly.
- Rate or diagnose a legacy-era (v8-v14) screen against LEGACY break signals, not OWL-specific
  ones - do not force-fit a legacy failure into an OWL defect class.
- Row 4: use `test_base_classes`' version-scoped answer directly - it is authoritative for the
  queried version. Corroborate with `test_class_inspect(..., method='hierarchy')` or
  `find_test_examples(...)` ONLY before a destructive rewrite (deleting or rewriting a call site).
  OSM-first precedence is unchanged - every other OSM call and structural fact keeps OSM as
  PRIMARY.

## Series derivation from a checkout

When no declared instance covers the repo (rung 2 of
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`), derive the series with the
detector, not a hand-rolled probe:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/odoo_series.py detect \
  "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

It prints shell-eval `KEY=VALUE` lines:

| Key | Meaning |
|---|---|
| `SERIES_STATUS` | `OK` or `NEEDS_CONTEXT` |
| `SERIES` | the resolved series, e.g. `17.0`; empty unless `SERIES_STATUS=OK` |
| `SERIES_STEP` | `1`-`5`: which ordered step produced the answer |
| `SERIES_ERA` | step 4 only - a RANGE, never one series, e.g. `8.0-9.0` / `10.0+` |
| `SERIES_EVIDENCE` | steps 1-3 - the citation: an absolute path or a branch name |
| `SERIES_HINT` | steps 3 + 5 - WEAK, never a series: step 3's unconfirmed candidate, step 5's filenames |

Exit codes: `0` = resolved (step 1 or 2 only); `3` = `NEEDS_CONTEXT`; `2` = usage error; `1` = root
is not a directory.

The ordered steps, strongest first. It STOPS at the first that yields anything, and a later step
NEVER overrides an earlier one; only steps 1-2 resolve a series:

1. **Core `release.py`** - authoritative, covers v8.0-v19.0. Probed under BOTH package dirs (row 5),
   deep enough for a nested checkout layout. Series = `major_version` when assigned as a
   plain string literal, else the first two elements of `version_info` joined with a dot
   (`(17, 0, 0, FINAL, 0, '')` -> `17.0`). A SaaS spelling (`'saas~17.2'`) yields the numeric major
   with the minor forced to `0`. A candidate contradicting its own package dir is discarded,
   never returned.
2. **A series-named git branch** - for an addons-only repo with no core package. Accepted ONLY when
   the name matches `^[0-9]{1,2}\.0$`, optionally after a remote prefix (`origin/17.0`); a
   feature-branch name is not evidence.
3. **The manifest `version` key - a HINT, never a series.** Only a series-PREFIXED `<major>.0.x.y`
   (>= 4 segments) whose major is at or above the v8 floor (row 5), with NO ceiling, is a
   candidate - `17.0.1.0.0` and a future `20.0.1.0.0` qualify. Every other value yields NOTHING:
   `1.0`, `1.3`, `1.0.9`, `1.0.0` are the ADDON's own version, the shape core `base` ships (`1.3` at
   ten of twelve indexed series, `1.4` at 17.0). Never take "the first two dotted components" of an
   unvalidated `version`. EVERY manifest in range is read (row 6 filenames, no cap) and all must
   agree; disagreement is inconclusive, and agreement alone proves nothing. A candidate arrives
   as `SERIES_HINT` with `NEEDS_CONTEXT` and exit 3, because a code-level upgrade leaves `version`
   unbumped: a prefix can name an earlier series than the checkout. Confirm it, or ask.
4. **Era only** - reports `SERIES_ERA` with `NEEDS_CONTEXT`, never a series.
5. **Last-resort hints** (`setup.py`, `debian/changelog`) - existence only, surfaced as
   `SERIES_HINT`, never parsed for a value.

`NEEDS_CONTEXT` means UNRESOLVED: carry it to the caller's own words, then to ONE batched ask.
Never substitute a default series.

Edition (Community vs Enterprise) is NOT derivable from a checkout on ANY series: no core constant
carries it, and a manifest with no `license` key parses as `LGPL-3` - a CE-looking license is a
default, not a statement. Settle it per question with OSM against the resolved series
(`list_available_profiles` / `check_module_exists`).
