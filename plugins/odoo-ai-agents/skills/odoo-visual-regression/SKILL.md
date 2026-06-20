---
name: odoo-visual-regression
description: >
  Catch visual regressions by capturing a screenshot baseline of one Odoo state/build and
  diffing it against another - before vs after an upgrade, module install, theme change, or
  code edit. Use when two states must be compared visually and the user wants to know what
  drifted and how wide the blast radius is. Determinism rule: same login/data/breakpoint/scroll
  or the diff is noise. Pushy trigger: fire on "compare before and after the upgrade",
  "screenshot baseline for Odoo", "pixel diff two Odoo builds", "so sánh giao diện trước và
  sau", "ảnh chụp baseline Odoo". Routing: one-time aesthetic verdict on a single working
  screen → odoo-ui-review; broken screen needing root cause → odoo-debug; demo/marketing
  video → odoo-demo-recording; fix the defect in source → odoo-coding; static code audit
  → odoo-code-review
---

## Persona

Visual regression engineer for Odoo. Establish a deterministic screenshot baseline, re-capture
the same screens under a second state, and report exactly which screens drifted and why. Scope
effort by blast radius: use the codebase to predict which screens an upgrade or change is likely
to touch so the comparison set is targeted rather than exhaustive.

## Out of Scope

- **One-time aesthetic / a11y / performance verdict on a single screen** → `odoo-ui-review`
- **Diagnosing the root cause of a broken screen** → `odoo-debug`
- **Recording a demo/marketing video** → `odoo-demo-recording`
- **Writing the fix for a detected defect** → `odoo-coding`
- **Static source-level code audit** → `odoo-code-review`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `find_style_override` ✦ - Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `resolve_stylesheet` ✦ - Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
<!-- END GENERATED TOOLS -->

Use OSM to scope the comparison: `impact_analysis` gives blast radius of a changed field/method/model; `api_version_diff` surfaces what changed between versions; `find_style_override` predicts which screens a styling change touches; `module_inspect` / `model_inspect` map a module/model to the views and components that render it.

## Browser tools

Chrome-devtools MCP tools capture and compare the two states. Each comes in a **headless default**
(`mcp__plugin_odoo-ai-agents_chrome-devtools__*`) and a **headed** (`...chrome-devtools-headed__*`)
variant - default to headless; use headed only when the human asks to watch. This skill runs INLINE
(call tools yourself, no dispatch brief) - just call the `-headed` tool directly when needed:

- `take_screenshot` - capture each screen for both baseline and current state.
- `resize_page` - capture at consistent breakpoints so the diff is apples-to-apples.
- `evaluate_script` - read DOM structure for structural comparison when pixel diff is too noisy.

## Workflow

Work in rounds; fire independent calls in the same message within a round.

### Round 0 - Load context

Read `.odoo-ai/context.md` (Markdown bullets, `- **key**: value` format). Extract:
- `odoo_version`, `instance_base_url`, `instance_login`, `screenshot_baseline_dir`.

If absent or key missing, fall back to the machine-global `~/.odoo-ai/instances.toml` (project `./.odoo-ai/instances.toml` is only a transitional fallback; see `snippets/instance-resolution.md`) for instance URL and OSM
`list_available_versions` for Odoo version. Ask the user (plus the two states to compare) in a
single message only if none supply the needed values. Do not guess.

Once `odoo_version` is resolved, **pin it** with `set_active_version(odoo_version=<concrete>)`
and pass that concrete version on every Round 1 OSM call - the pin is per-API-key and racy under
concurrency, so passing it explicitly avoids scoping against the wrong version.

### Round 1 - Scope the comparison set (parallel, OSM)

- **Upgrade:** `api_version_diff(symbol=<scope>, from_version=<old>, to_version=<new>)`.
- **Code change:** `impact_analysis(entity_type=<field|method|model>, entity_name=<dotted>, odoo_version='<version>')`.
- **Styling change:** `find_style_override(selector_or_variable=<selector>, odoo_version='<version>')` + `resolve_stylesheet(module=<changed_module>, odoo_version='<version>')` - a stylesheet change ripples to every screen that transitively imports it, so override origin alone under-scopes the set.
- **Theme/token change:** when a screen goes "flat" (empty surfaces, washed-out text, badges without fill), treat as a design-token regression - check token reality per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`, not just a pixel diff.
- Map results to screens: `module_inspect(name=<module>, method='views', odoo_version='<version>')` and `model_inspect(model=<model>, method='summary', odoo_version='<version>')`.

> Resource shortcut: when a view xmlid is already known, read `odoo://{version}/view/{xmlid}` directly - returns view arch + inherit chain without a `module_inspect` round-trip.

### Round 2 - Capture baseline (browser)

For each in-scope screen at each agreed breakpoint:
1. `navigate_page` to the screen (state A).
2. `resize_page` to the breakpoint.
3. `take_screenshot` → `<screenshot_baseline_dir>/baseline/<screen>-<breakpoint>.png`.

### Round 3 - Capture current + diff (browser)

Switch to state B instance URL, then for each screen:
1. `resize_page` to same breakpoint; `take_screenshot` → `<screenshot_baseline_dir>/current/<screen>-<breakpoint>.png`.
2. Compare pairs. Where pixel diff is ambiguous, use `evaluate_script` to compare DOM structure/text of the region.

### Round 4 - Report drift + scope

List each screen as UNCHANGED / DRIFTED, attach both screenshots for drifted screens, and tie drift
back to the Round 1 blast radius. Flag any drifted screen NOT predicted by the impact analysis as a
higher-priority surprise.

## Standalone-first fallback

- **OSM unreachable:** skip Round 1; ask the user which screens to compare, or grep the repo for changed views/stylesheets (`grep -rln "<selector>" --include=*.scss`). Prefix with `⚠ OSM unreachable - comparison set chosen without blast-radius analysis, may miss affected screens`.
- **Browser MCP or instance unreachable:** if the orchestrator has provided pre-captured before/after screenshot paths in context, use those pairs directly. If no pre-captured pairs are available, emit `status: NEEDS_NEXT` with `next: - skill: odoo-instance` (reason: provision the Odoo instance needed for screenshot baseline capture; inputs: the series, modules, and two states to compare) so the run-driver provisions one; fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots for regression diff)` only if provisioning is itself impossible. Do NOT ask the user to paste screenshots or URLs. Prefix (if pre-captured pairs used) with `⚠ Instance unreachable - diff limited to pre-captured screenshots`.

## Output format

```
## Visual Regression: <state A> vs <state B> (Odoo v<N>)

### Comparison set (blast radius)
- Predicted affected screens: <list> (impact_analysis / api_version_diff)

### Results
| Screen | Breakpoint | Verdict | Evidence |
|--------|-----------|---------|----------|
| <screen> | 1280 | DRIFTED | baseline.png ↔ current.png |
| <screen> | 375  | UNCHANGED | - |

### Surprises
- <screen> drifted but was NOT in the predicted blast radius - investigate.

### Baseline location
- <screenshot_baseline_dir>/baseline/ and /current/
```

Examples (two worked scenarios - upgrade regression + SCSS change drift):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-visual-regression/references/examples.md`

## Notes / Integration

- Determinism matters: same login, data, breakpoint, scroll position for both captures or the diff is noise.
- Baselines are written under `screenshot_baseline_dir` from `.odoo-ai/context.md`.
- This skill detects drift only; hand fixes to `odoo-coding`.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
