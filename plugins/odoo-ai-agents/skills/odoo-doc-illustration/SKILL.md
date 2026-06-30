---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >
  Produce illustrated documentation for an Odoo module or cluster: drives a live browser to
  capture screenshots of rendered screens then embeds them into static/description/ (UC1) or
  a doc-repo/marketing output dir (UC2). Dispatched as agent odoo-doc-illustrator.
  Pushy trigger - fire on: "document an Odoo module with screenshots", "tạo tài liệu có ảnh
  cho module", "screenshot doc Odoo", "làm static/description với hình", "viết tài liệu cụm
  module kèm ảnh", "illustrate module README with captured screens", "add screenshots to addon
  docs", "thêm ảnh chụp màn hình vào tài liệu module", "create RST user guide for module",
  "viết doc/index.rst cho module", "userguide có ảnh cho module".
  Routing: record a video -> odoo-demo-recording; audit a screen -> odoo-ui-review; pure text
  (no screenshots) -> odoo-content-draft; spec/outline before code -> odoo-solution-design or
  odoo-content-draft; compare builds -> odoo-visual-regression; write frontend code -> odoo-coding
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
LANGUAGES: <resolved language list - see i18n resolution below>
```

If `addons_path` is not yet known, TARGET may be just a module name; the agent resolves the absolute path from `context.md` or by scanning disk.

**DOC LAYER.** Controls which output files are produced:
- `appstore` - writes `static/description/index.html` (App Store listing page)
- `userguide` - writes `doc/index.rst` (user guide / RST documentation)
- `both` (MODE module) - agent writes both files directly (no markers, no content-draft); agent embeds `<img>` / `.. image::` tags after capture
- `both` (MODE cluster hybrid) - agent uses `[Image: <screen-slug>]` markers in the prose skeleton so standalone `odoo-content-draft` can fill prose; the doc-illustrator agent itself replaces markers with `<img>`/`.. image::` after capture (content-draft does NOT resolve markers)

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
  so the run-harness provisions one; fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots)` only if provisioning is itself impossible.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
