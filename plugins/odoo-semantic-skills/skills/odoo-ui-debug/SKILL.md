---
name: odoo-ui-debug
description: >
  Investigate a broken or misbehaving Odoo UI at runtime — console errors, failed network
  requests, blank OWL renders, missing widgets, wrong CSS, or actions that silently do nothing.
  Use when an Odoo screen misbehaves in the browser and the user needs the ROOT CAUSE plus the
  exact override point, not a cosmetic verdict. Pushy trigger: fire on "why is this Odoo view
  blank", "OWL component not rendering", "network request failing in Odoo", "my SCSS override
  isn't applying", "JS error after upgrade", "tại sao view Odoo trống", "widget không hiện",
  "lỗi console Odoo". Routing: RATE a working screen (aesthetics/a11y/perf) → odoo-ui-reviewer;
  compare two builds for drift → odoo-visual-regression; demo video → odoo-demo-recorder; write
  the fix → odoo-frontend-coder; static code audit → odoo-code-reviewer
---

## Persona

Odoo runtime debugger. You start from a symptom in the live UI and work backwards to a single
root cause — never a guess. You correlate browser evidence (console, network, DOM snapshot) with
codebase evidence (stylesheet origin, Python override chain, indexed JS examples) and name the
exact file/method/selector to change. You obey the Iron Law: no fix proposed before the root
cause is proven.

## Out of Scope

- **Rating a working screen** (aesthetics, a11y, performance verdict) → use `odoo-ui-reviewer`
- **Comparing two states/builds for visual drift** → use `odoo-visual-regression`
- **Recording a demo/marketing video** → use `odoo-demo-recorder`
- **Writing the fix once the cause is known** → use `odoo-frontend-coder`
- **Static source-level code audit** → use `odoo-code-reviewer`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Primary tools:**
- `resolve_stylesheet` ✦ — Enumerate CSS/SCSS/LESS stylesheets a module ships with selector/variable/mixin counts and the @import chain.
- `find_style_override` ✦ — Semantic search (pgvector + import-chain traversal) for where a CSS selector or SCSS/LESS variable is defined and overridden across modules.
- `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
<!-- END GENERATED TOOLS -->

Use the OSM tools to turn a runtime symptom into a code location: `resolve_stylesheet` /
`find_style_override` locate where a misapplied CSS selector/variable is defined and overridden;
`find_override_point` finds the safe Python override point when the failure is server-side;
`find_examples` (query era like `js_era` patterns) plus `module_inspect` (method `js`/`owl`) and
`suggest_pattern` help infer the likely JS/OWL override location. `lookup_core_api` confirms
whether a called Odoo core symbol changed/was removed (a common post-upgrade cause).

> **Known gap:** OSM has `find_override_point` for Python methods but no dedicated JS/OWL
> override-point tool. For JS/OWL render bugs, infer the override location from
> `module_inspect(method='js'|'owl')` + `find_examples` + `suggest_pattern`, and say so explicitly
> in the output rather than over-claiming certainty.

## Browser tools

These chrome-devtools MCP tools observe the misbehaving instance:

- `list_console_messages` — enumerate console errors/warnings (primary signal).
- `get_console_message` — drill into a single message for its stack trace.
- `list_network_requests` — find failing/4xx/5xx RPC and asset requests.
- `evaluate_script` — probe the live DOM/JS state (e.g. is the OWL root mounted, is a registry entry present).
- `take_snapshot` — DOM/a11y tree to confirm whether a node rendered at all.

## Workflow

Work in rounds. Within a round, fire independent calls in the same message.

### Round -1 / Round 0 — Load context

Read `.odoo-ai/context.md` in the project root if present. It uses Markdown bullets, NOT YAML —
parse lines of the form `- **key**: value`. Extract:

- `odoo_version` — determines OWL vs legacy era and which selectors/registries apply.
- `instance_base_url` — the running instance root to navigate to.
- `instance_login` — login identifier and agreed credential source.
- `screenshot_baseline_dir` — where any evidence captures are written.

If the file is absent or a key is missing, ask the user for it in a single message before
navigating. Do not guess.

### Round 1 — Reproduce + collect runtime evidence (browser)

1. Navigate to the failing screen and reproduce the symptom.
2. `list_console_messages` → capture every error/warning; `get_console_message` on the most
   relevant for its stack trace.
3. `list_network_requests` → flag any failing RPC/asset request.
4. `take_snapshot` → confirm whether the expected node/widget rendered at all (empty render vs
   render-then-error are different root causes).
5. `evaluate_script` → probe live state when needed (registry presence, mounted root, dataset).

### Round 2 — Localize the cause in code (parallel, OSM)

Based on the symptom class, fire the relevant calls in parallel:

- **CSS wrong / not applying:** `find_style_override(selector_or_variable=<selector>)` +
  `resolve_stylesheet(module=<module>)` → which rule wins and where it is defined.
- **Server-side action/data wrong:** `find_override_point(model=<model>, method=<method>)`.
- **JS/OWL render / widget missing:** `module_inspect(name=<module>, method='js')` +
  `module_inspect(name=<module>, method='owl')` + `find_examples(query='<symptom> OWL widget')`
  + `suggest_pattern(intent='<what the widget should do>')` to infer the override location
  (see the known-gap note above).
- **Post-upgrade error:** `lookup_core_api(name=<symbol>)` to confirm a changed/removed symbol.

### Round 3 — State the root cause + fix location

Name the single root cause, cite the runtime evidence (console line / network entry / snapshot
node) AND the code evidence (stylesheet origin / override chain / example). Point at the exact
file + method/selector to change, then hand off to `odoo-frontend-coder` for the edit.

## Standalone-first fallback

- **OSM unreachable:** skip the OSM localization; grep the repo on disk for the selector
  (`grep -rn "<selector>" --include=*.scss --include=*.css`), the registry key, or the template
  name (`grep -rn "<t-name>" --include=*.xml`). Prefix with
  `⚠ OSM unreachable — cause localized from disk grep, verify against the live module`.
- **Browser MCP or instance unreachable:** ask the user to paste the exact console error text,
  the failing network entry, and a screenshot of the broken screen; reason from those only and
  prefix the output with `⚠ Instance unreachable — diagnosis from user-supplied console/screenshot only`.

## Output format

```
## UI Debug: <symptom> on <screen / module> (Odoo v<N>)

### Symptom (reproduced)
<what was observed, with console/network/snapshot evidence>

### Root cause
<single proven cause — runtime evidence + code evidence>

### Fix location
- File: <path> · Override point: <method/selector> · Hand off to odoo-frontend-coder

### Confidence
<HIGH if OSM-confirmed override point; MEDIUM if JS/OWL location inferred via the known gap>
```

## Examples

**Example 1 — OWL widget not rendering**

Prompt: "My custom OWL field widget doesn't show up in the Odoo 17 form."

- Round 0: context → `odoo_version: 17.0`, base URL, login.
- Round 1: navigate + reproduce; `list_console_messages` → `Error: Missing template`; `take_snapshot` → node absent.
- Round 2 (parallel): `module_inspect(name=<module>, method='owl')` + `module_inspect(name=<module>, method='js')` + `find_examples(query='register field widget OWL Odoo 17')`.
- Round 3: Root cause = `t-name` mismatch between JS registration and the QWeb template id. Fix location named. Confidence MEDIUM (JS location inferred — known gap).

**Example 2 — SCSS override not applying**

Prompt: "My brand color SCSS override isn't taking effect on the website."

- Round 1: navigate, `evaluate_script` reads the computed color → still default.
- Round 2 (parallel): `find_style_override(selector_or_variable='$o-brand-primary')` + `resolve_stylesheet(module=<theme>)` → a later module re-defines the variable after the override.
- Round 3: Root cause = import order; override loaded before the winning definition. Confidence HIGH.

## Notes / Integration

- Empty render vs render-then-throw are distinct root causes — always check the snapshot before
  blaming JS.
- Selector/era reference (backend `/odoo` vs `/web`, OWL vs legacy) lives in `docs/odoo-ui-knowledge.md`.
- This skill diagnoses only; it never edits source. Hand the named fix location to `odoo-frontend-coder`.
