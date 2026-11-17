---
name: odoo-visual-regression
argument-hint: "[baseline] [candidate]"
description: >-
  Screenshot-diffs an Odoo screen between two states
---

## Role

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
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `find_style_override` ✦ - Find where a CSS selector or SCSS/LESS variable is first defined and which modules override it, with the full override chain.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `resolve_stylesheet` ✦ - Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `list_available_versions` ☆ - Enumerate which Odoo versions the server has indexed.
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

### Round 0 - Resolve the run's inputs

Resolve each input from its own SSOT - never from a stored snapshot, and never by guessing:

- **Odoo series** - per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
- **`instance_base_url`** (state A) - per `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`
  (live shared server first, then the declared `[[instance]]` in `$ODOO_AI_HOME/instances.toml`).
- **`instance_base_url_b`** (state B) - a per-run BRIEF/request input, set ONLY for a genuine
  two-instance comparison (two separate builds/hosts). Absent -> state B is the SAME
  `instance_base_url` re-navigated after the change under test (module install/uninstall, theme
  toggle, in-place upgrade) is applied. That same-instance before/after is the default.
- **Baseline dir** - always `<SHARE_DIR>/visual/baselines/`; there is no per-project override.

Ask the user (plus the two states to compare) in a single message only for what no SSOT above
supplies. Do not guess.

Then resolve `<SHARE_DIR>` and `<ISOLATE_DIR>` - both needed before Round 3 writes any comparison
screenshot, and before the orphan sweep below. Resolve each once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write a placeholder or a bare `.odoo-ai/` into a Read/Write/Edit.

**Orphan sweep, every run, BEFORE minting your own slug below:** a run that crashed or was
abandoned leaves its `<slug>/` directory behind, so remove the ones untouched for 24 hours:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/state_sweep.py <ISOLATE_DIR>/visual/current --older-than-minutes 1440`
(`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 2).

Now mint this run's `<slug>` once (Clause 1 of that contract: the brief's `SLUG:`, else
`<intent-slug>-<YYYYMMDD>-<4 random chars>`) and use that same value in every path of this run.

Once `odoo_version` is resolved, **pin it** with `set_active_version(odoo_version=<concrete>)`
and pass that concrete version on every Round 1 OSM call - the pin is session-scoped and racy
when actors share a session (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
§ OSM session-pin race), so passing it explicitly avoids scoping against the wrong version.

### Round 1 - Scope the comparison set (parallel, OSM)

- **Upgrade:** `api_version_diff(symbol=<scope>, from_version=<old>, to_version=<new>)`.
- **Code change:** `impact_analysis(entity_type=<field|method|model>, entity_name=<dotted>, odoo_version='<version>')`.
- **Styling change:** `find_style_override(selector_or_variable=<selector>, odoo_version='<version>')` + `resolve_stylesheet(module=<changed_module>, odoo_version='<version>')` - a stylesheet change ripples to every screen that transitively imports it, so override origin alone under-scopes the set.
- **Theme/token change:** when a screen goes "flat" (empty surfaces, washed-out text, badges without fill), treat as a design-token regression - check `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` § Token reality and `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md` §§ 1-2, not just a pixel diff.
- Map results to screens: `module_inspect(name=<module>, method='views', odoo_version='<version>')` and `model_inspect(model=<model>, method='summary', odoo_version='<version>')`.

> Resource shortcut: when a view xmlid is already known, read `odoo://{version}/view/{xmlid}` directly - returns view arch + inherit chain without a `module_inspect` round-trip.

### Round 2 - Capture baseline (browser)

**Single-page discipline.** Reuse ONE page for the whole sweep - `navigate_page` + `resize_page` in
place across every screen/breakpoint - instead of opening a new page per screen. Never call
`new_page` per screen; navigating the reused page IS the correct reuse pattern.

For each in-scope screen at each agreed breakpoint:
1. `navigate_page` to the screen (state A).
2. `resize_page` to the breakpoint.
3. `take_screenshot` → `<SHARE_DIR>/visual/baselines/<screen>-<breakpoint>.png` (pass this
   absolute path as `filePath`, never `path` - the chrome-devtools schema accepts unknown keys
   silently and writes nothing).

### Round 3 - Capture current + diff (browser)

Switch to state B's instance URL - `instance_base_url_b` when this is a two-instance comparison,
otherwise re-navigate the SAME `instance_base_url` after applying the change under test (module
install/uninstall, theme toggle, in-place upgrade) - then for each screen:
1. `resize_page` to same breakpoint; `take_screenshot` → `<ISOLATE_DIR>/visual/current/<slug>/<screen>-<breakpoint>.png` (`filePath`, never `path`).
2. Compare pairs. Where pixel diff is ambiguous, use `evaluate_script` to compare DOM structure/text of the region.

### Round 4 - Report drift + scope

List each screen as UNCHANGED / DRIFTED, attach both screenshots for drifted screens, and tie drift
back to the Round 1 blast radius. Flag any drifted screen NOT predicted by the impact analysis as a
higher-priority surprise.

**Close before reporting, every run:** the pages you drove, per
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2.

## Standalone-first fallback

- **OSM unreachable:** skip Round 1; ask the user which screens to compare, or grep the repo for changed views/stylesheets (`grep -rln "<selector>" --include=*.scss`). Prefix with `⚠ OSM unreachable - comparison set chosen without blast-radius analysis, may miss affected screens`.
- **Browser MCP or instance unreachable:** if the orchestrator has provided pre-captured before/after screenshot paths in context, use those pairs directly. If no pre-captured pairs are available, emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed for screenshot baseline capture
      inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules to compare>"]}
      confidence: 0.9
  ```
  so the caller provisions one; fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots for regression diff)` only if provisioning is itself impossible. Do NOT ask the user to paste screenshots or URLs. Prefix (if pre-captured pairs used) with `⚠ Instance unreachable - diff limited to pre-captured screenshots`.

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
- Baselines (SHARE, reusable): <SHARE_DIR>/visual/baselines/
- This run's comparison set (ISOLATE, deleted after this verdict): <ISOLATE_DIR>/visual/current/<slug>/
```

Examples (two worked scenarios - upgrade regression + SCSS change drift):
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-visual-regression/references/examples.md`

## Notes / Integration

- Determinism matters: same user, data, breakpoint, scroll position for both captures or the diff is noise.
- This skill detects drift only; hand fixes to `odoo-coding`.
- **Retention.** Before ANY terminal status (`DONE`, `BLOCKED`, `NEEDS_CONTEXT`, `NEEDS_NEXT`)
  delete this run's comparison set, `<ISOLATE_DIR>/visual/current/<slug>/` and nothing above it;
  the baselines stay in SHARE.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the plan runner - it does not change anything produced above.
