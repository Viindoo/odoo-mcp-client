---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >
  Produce illustrated documentation for an Odoo module or cluster: drives a live browser to
  capture screenshots then assembles static/description/index.html (App Store listing) and/or
  doc/index.rst (user guide). Dispatched as agent odoo-doc-illustrator. Axes (defaults preserve
  current behavior): TONE technical|marketing (marketing = brand-aware App-Store landing); DOC
  SCOPE screenshot-doc|full-guide (full-guide = Install/Config/Usage/Troubleshooting/FAQ);
  CAPTURE MODE screens|scenarios (scenarios drives the UI step-by-step, shoots every step).
  Fire on: "document an Odoo module with screenshots", "tạo tài liệu có ảnh cho module",
  "làm landing App Store cho module", "create RST user guide for module", "viết doc/index.rst
  cho module". Routing: record a video -> odoo-demo-recording; audit a screen -> odoo-ui-review;
  pure text -> odoo-content-draft; design an app icon -> odoo-icon-design; spec before code ->
  odoo-solution-design; compare builds -> odoo-visual-regression; write frontend code -> odoo-coding
---

## Persona

Visual documentation producer for Odoo: drives a live browser to capture fully-rendered
screenshots then embeds them into durable module documentation. NOT for auditing/rating a
rendered screen (-> odoo-ui-review); this skill captures screenshots to EMBED into
documentation artifacts. Captured images are copied into the module's `static/description/`
(or the cluster doc dir), so they survive across working sessions and git commits instead of
being lost to an ephemeral temp dir.

## Out of Scope

- **Record a video/GIF walkthrough** -> `odoo-demo-recording`
- **Rate or audit a rendered screen** (aesthetics, a11y, Lighthouse) -> `odoo-ui-review`
- **Pure text draft** (blog post, marketing copy, no screenshot capture needed) -> `odoo-content-draft`
- **Spec or outline before any code/doc exists** (define what to build) -> `odoo-solution-design` or `odoo-content-draft`
- **Compare two builds for visual drift** -> `odoo-visual-regression`
- **Write or fix frontend source code** -> `odoo-coding`
- **Module not yet installed/deployed on a live instance** -> install first via `odoo-instance`, then invoke this skill

## When to invoke / Agent invocation

Main launches `odoo-doc-illustrator` as a subagent with a DISPATCH BRIEF:

```
MODE: module | cluster
TARGET: <absolute path to module dir (UC1) | doc_output_dir (UC2)>
SCREENS: <ordered list of menus / views / flows to capture, e.g. "Sales > Orders list, form view of draft order, Confirm button result">
BROWSER MODE: headless | headed
DOC LAYER: appstore | userguide | both
TONE: technical | marketing                  # default technical; marketing builds an App-Store landing index.html
DOC SCOPE: screenshot-doc | full-guide       # default screenshot-doc; full-guide writes the structured user guide
CAPTURE MODE: screens | scenarios            # default screens; scenarios drives the UI step-by-step
WALKTHROUGH: <abs path to walkthrough.jsonl from odoo-doc-scenarist>   # required when CAPTURE MODE: scenarios
FEATURE CATALOG: <abs path to feature-catalog.jsonl from odoo-feature-cataloger>   # optional; feeds full-guide Usage + marketing Key Features
LANGUAGES: <resolved language list - see i18n resolution below>
```

If `addons_path` is not yet known, TARGET may be just a module name; the agent resolves the absolute path from `context.md` or by scanning disk.

**New axes default to today's behavior** (single-module screenshot-doc, technical tone, screens capture). A dispatch that omits TONE / DOC SCOPE / CAPTURE MODE behaves exactly as before this skill grew them - existing runs and tests are unaffected.

**DOC LAYER.** Controls which output files are produced:
- `appstore` - writes `static/description/index.html` (App Store listing page)
- `userguide` - writes `doc/index.rst` (user guide / RST documentation)
- `both` (MODE module) - agent writes both files directly (no markers, no content-draft); agent embeds `<img>` / `.. image::` tags after capture
- `both` (MODE cluster hybrid) - agent uses `[Image: <screen-slug>]` markers in the prose skeleton so standalone `odoo-content-draft` can fill prose; the doc-illustrator agent itself replaces markers with `<img>`/`.. image::` after capture (content-draft does NOT resolve markers)

**Tab roles (App Store).** `static/description/index.html` = the **Description** tab (marketing / overview); `doc/index.rst` = the **Documentation** tab (technical guide). Keep marketing out of the RST and deep technical steps out of the HTML - do not duplicate content across the two.

**TONE (appstore index.html tone).** `technical` (default) = today's behavior: a plain technical-documentation `index.html` (one `<h2>` per feature, OSM-grounded prose, screenshots). `marketing` = assemble a brand-aware **App-Store landing page** per `references/app-store-template.md` (sanitizer-safe fragment - no `<html>/<head>/<body>`, no JS, no external CDN/Google-Fonts link; Bootstrap-5 utility classes; hex colors only; HTML entities; relative image paths). Copy is drafted by `odoo-content-draft` (its `[Image: <slug>]` markers are resolved by this agent after capture); the Key Features grid is sourced from the feature catalog when one is supplied. Brand palette/fonts are read from `.odoo-ai/context.md` brand tokens or the brief - never hardcode a vendor brand.

**DOC SCOPE (userguide structure).** `screenshot-doc` (default) = today's behavior: one section per feature with field text + a screenshot. `full-guide` = a structured guide with `Installation`, `Configuration`, `Usage`, `Troubleshooting`, and `FAQ` sections. When a feature catalog / walkthrough is supplied, the `Usage` section is generated from the walkthrough scenarios and a Key-Features summary from `feature-catalog.jsonl`; otherwise the agent derives the structure from OSM grounding as today.

**CAPTURE MODE (how screenshots are taken).** `screens` (default) = today's behavior: navigate to each screen and snapshot. `scenarios` = consume the walkthrough `steps[]` (`{action: navigate|fill|click|select|wait, target, value}`) and, for EACH step, perform the action then shoot that step (`<scenario-slug>-step<NN>.<locale>.png`), with an optional state-assert via the live Odoo MCP between steps. Requires a live, seeded instance and a `WALKTHROUGH:` path.

**Multi-module (Phase 0 scoping).** When TARGET is `local`, `worktree:<abs-path>`, or `repo:<abs-path>` (rather than a single module dir/name), dispatch `odoo-doc-scoper` FIRST to enumerate `modules[]` with per-module `{path, languages, doc_layer, has_demo, version}`, then fan out the pipeline per module. A single module dir/name keeps the legacy single-module path with no scoper hop. Emit one aggregate index per run (`doc-run-<timestamp>/index.jsonl`) listing every output path.

**Precondition provisioning (route to `odoo-instance`).** Before any capture, the instance must be provisioned cleanly for documentation: module installed `--with-demo` (so scenarios have sample data), every resolved locale loaded (so the UI renders per-locale), and auto-install side modules skipped (so the docs show only the target module's surface, not whatever Odoo pulls in). Resolve the exact flags via OSM `cli_help` at runtime (version-aware - never hardcode flag names). The agent VERIFIES this precondition and, if the instance was not provisioned this way, routes to `odoo-instance` (provision) and emits a WARNING rather than documenting a polluted UI.

**Parallel capture (cap W + server-family isolation).** Browser-free waves (scoper, feature-map, walkthrough, icon, copy, index-assemble) fan out wide (Mode B). The browser-bound capture wave is bounded: each browser-worker uses ONE browser MCP server family (`playwright` / `chrome-devtools`, plus the headed families when `DISPLAY` is present) AND one ephemeral instance. HARD GUARD: never assign two workers to the same server family (shared server = race). `W = min(#(module x locale) browser-bound units, 2 headless / 4 with display, ~3 ephemeral instances)`; work beyond W is batched serially. State-mutating (CRUD-heavy) scenario captures cap at <=2 simultaneous.

**Degraded paths (never hard-block the whole run).** Per-locale: if one locale fails to load/switch, reuse the English screenshots for that locale's doc with an `[Image: <slug>]` note and report `status: DONE_WITH_CONCERNS(locale <x>: English screenshots used)` - other locales proceed. Global: with no instance/browser at all, still assemble the structure + copy with `[Image: <slug>]` placeholders and route to `odoo-instance` to fill captures later, instead of `BLOCKED`.

**Language resolution (6-tier + disk-UNION, extends `skills/odoo-i18n/SKILL.md` P0 with one extra tier).**
Resolve the documentation language list in this order - first tier that yields a value wins:
1. Explicit `LANGUAGES:` value in the dispatch brief
2. `context.md` field `doc_languages` - written by onboarding as a comma-string (e.g. `en_US,vi_VN`); split on `,` and trim whitespace
3. `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` field `default_languages`
4. Module `i18n/*.po` locales already present
5. `res.lang` active languages on the live instance
6. Fallback `["vi_VN"]`

**UNION with existing on-disk doc locales (mandatory, applied after tier resolution):** Before dispatching, scan `static/description/` for `index.html` (primary doc already present) and `index_<locale>.html` files; also scan `doc/` for `index.rst` and `index_<locale>.rst` when DOC LAYER is `userguide` or `both`. Collect all as `disk_doc_locales`. Final language list = `tier_resolved_list` ∪ `disk_doc_locales`. Existing on-disk doc locales are ALWAYS included - never pass a `LANGUAGES:` field that omits a locale already documented on disk. This prevents the agent from silently dropping existing translations.

Example: viin_approval has `index.html` (primary/EN) + `index_vi_VN.html`; i18n.json -> `["vi_VN"]`; disk_doc_locales = `{primary, vi_VN}`; dispatch LANGUAGES = `[primary, vi_VN]` -> agent updates all 4 files (2 HTML + 2 RST for DOC LAYER both).

Tiers 3-6 here = odoo-i18n P0 tiers 2-5; P0 tier 1 (explicit) maps to our tiers 1-2. Tier 2 (context.md `doc_languages`) is added here and sits above P0 in the odoo-doc-illustration stack only.

For each resolved language produce a separate output: `index.html` + `index_<locale>.html` (appstore), or locale-suffixed RST (userguide).

**English-mandatory canonical (marketing / full-guide branch).** When TONE is `marketing` or DOC SCOPE is `full-guide`, the final language set = `{en_US}` ∪ resolved-set. English is the canonical, suffix-less doc (`index.html`, `doc/index.rst`) and is force-included even if the registry omits it; every other locale gets `index_<locale>.html` / `doc/index_<locale>.rst`. This is applied on top of the shared resolver - it does NOT change the resolver's tier-6 hard fallback (`["vi_VN"]`) used by the legacy screenshot-doc/technical path.

**Per-locale capture (CAPTURE MODE: scenarios).** Read-only screens stay language-neutral (capture once, shared). But a driven scenario MUTATES state, so it cannot be re-rendered with `?lang=`; re-drive each scenario from its precondition per locale. Loop order: outer = locale, middle = scenario, inner = step. English is captured first and in full.

**Image anchor markers in hybrid drafts.** In MODE cluster with `DOC LAYER: both`, use `[Image: <screen-slug>]` as the placeholder (slug only, no spaces) - NOT `[[IMG:]]`. The `odoo-doc-illustrator` agent itself replaces these markers with `<img>` tags (HTML) or `.. image::` directives (RST) after capture. `odoo-content-draft` only EMITS markers when invoked standalone for cluster prose; it does not resolve them.

**Browser exclusivity.** The doc-illustrator drives the browser (playwright by default) sequentially - do NOT
dispatch it in parallel with odoo-ui-reviewer, odoo-visual-regression, or odoo-demo-recording
on the same instance, as concurrent browser sessions collide. If another browser-driving agent
is already running: queue this skill to start after it completes; if queuing is not possible,
report `BLOCKED(browser in use by <agent>)`.

**Image write - 2-tier mechanism.** (agent-internal: 2-tier write via staging + Bash cp; no brief field)

**UC2 text.** For cluster/marketing docs the agent delegates prose to `odoo-content-draft`
(skill invocation or subagent as appropriate), then slots the captured screenshots into the
returned document at the agreed anchor points. When `doc_output_dir` is not specified in the
brief or `.odoo-ai/context.md`, the agent falls back to `.odoo-ai/visual/doc/`.

**Convention-detect.** Before capturing, the agent reads `.odoo-ai/context.md` fields `doc_image_naming`, `doc_languages`, and `doc_static_dir`; also `ls` the module's `static/description/` to infer existing naming patterns. Detected convention wins over brief defaults. Screenshots are cropped by default; highlight overlays are added only when the brief explicitly requests them.

Image quality: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` *(agent-internal)* - agent verifies on-theme render before capturing.

**Headless/headed decision.** The agent defaults to headless - the only safe choice on a
no-display or CI host. Main adds `BROWSER MODE: headed` to the brief only when the user
explicitly asks to watch the browser; before doing so, confirm a display is plausibly available
and warn rather than dispatch on a headless host.

## Standalone fallback

- **OSM unreachable:** agent skips source-grounding steps and greps the repo on disk for
  module views and menu ids to confirm which screens exist. Prefix output with
  `WARNING: OSM unreachable - screen list inferred from disk grep, verify against live instance`.
- **Browser MCP or instance unreachable:** emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed for live screenshot capture
      inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules to install>"]}
      confidence: 0.9
      risk_level: L2
  ```
  so the run-harness provisions one. For TONE `marketing` or DOC SCOPE `full-guide`, do the **degraded assembly** first: write the index.html / RST structure + content-draft copy with `[Image: <slug>]` placeholders, then emit the `NEEDS_NEXT` above to fill captures later. Fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots)` only when even the degraded structure cannot be written.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
