---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >
  Produce and orchestrate illustrated documentation for an Odoo module or cluster - the SOLE
  orchestrator that dispatches odoo-doc-scoper then odoo-doc-planner, gates the whole plan ONCE,
  then runs a branch-aware per-instance incremental loop that launches odoo-user-doc-writer
  (end-user doc/index.rst) and/or odoo-marketing-writer (App-Store static/description/index.html)
  per DOC LAYER and commits per module via git-ops. Axes: DOC LAYER appstore(default)|userguide|both;
  TONE technical|marketing; DOC SCOPE screenshot-doc|full-guide; CAPTURE MODE screens|scenarios. Fire
  on: "document an Odoo module with screenshots", "tạo tài liệu có ảnh cho module", "làm landing App
  Store cho module", "create RST user guide for module", "viết doc/index.rst cho module". Routing:
  record a video -> odoo-demo-recording; audit a screen -> odoo-ui-review; pure marketing copy only
  -> odoo-content-draft; module icon -> odoo-icon-design; write frontend code -> odoo-coding
---

## Persona

Documentation-run orchestrator for Odoo modules. This skill is the SOLE orchestrator of a
documentation run: it scopes and plans the modules, gates the plan once, provisions the live
instance(s), then per module launches two INTERNAL browser-driving writer agents that capture
fully-rendered screenshots and embed them into durable module documentation -
`odoo-user-doc-writer` (end-user `doc/index.rst`) and `odoo-marketing-writer` (App-Store
`static/description/index.html`). Captured images land in the module's `static/description/` so
they survive across sessions and git commits. NOT for auditing/rating a rendered screen
(-> `odoo-ui-review`) - this skill captures screenshots to EMBED into documentation.

## Out of Scope

- **Record a video/GIF walkthrough** -> `odoo-demo-recording`
- **Rate or audit a rendered screen** (aesthetics, a11y, Lighthouse) -> `odoo-ui-review`
- **Pure text draft** (blog post, marketing copy, no screenshot capture needed) -> `odoo-content-draft`
- **Spec or outline before any code/doc exists** (define what to build) -> `odoo-solution-design` or `odoo-content-draft`
- **Compare two builds for visual drift** -> `odoo-visual-regression`
- **Write or fix frontend source code** -> `odoo-coding`
- **Module not yet installed/deployed on a live instance** -> install first via `odoo-instance`, then invoke this skill

## Sole orchestrator (scoper -> planner -> ONE gate -> per-instance loop)

This skill owns the ENTIRE run: scoping, planning, the plan gate, instance-provisioning authority,
the per-instance loop, verify, per-module commit, and model selection for the writers. The two
writer agents are INTERNAL leaf executors - only this skill launches them; no consumer reaches past
the skill into a writer. The writers NEVER spawn, call the Skill tool, call
`odoo-content-draft`/`-scoper`/`-planner`, or run a loop - ALL orchestration lives here.

**Single module.** A single module dir/name keeps the legacy single-module path with no
scoper/planner hop: provision (or receive an `INSTANCE_HANDLE`), then run the loop body ONCE
against that module - behavior unchanged.

**Multi-module** (TARGET is `local`, `worktree:<abs-path>`, or `repo:<abs-path>` with >1 module):
1. **Scope** - dispatch `odoo-doc-scoper` FIRST to enumerate `modules[]` with per-module
   `{path, languages, doc_layer, has_demo, version, depends_in_scope, has_ondisk_doc}`.
2. **Plan** - dispatch `odoo-doc-planner` (`plan_source: scope`) to emit `doc-plan.yaml` -
   dependency clusters + branch-aware instance allocation + per-instance topological
   `install_doc_sequence` + dedup + parallelism schedule. Algorithm SSOT:
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-cluster-plan.md` - do not re-derive it here.
3. **Gate (ONE whole-plan).** Present the ENTIRE plan (clusters + instance allocation + install/doc
   order + dedup + schedule) for a SINGLE `approve / refine: [feedback] / cancel` - NOT a gate per
   cluster. `refine` re-runs the planner with the feedback; `cancel` aborts before any instance is
   provisioned.
4. **Loop** - run the per-instance incremental loop below over `doc-plan.yaml`.

**Per-instance incremental loop (the loop body).** Per instance-path (SEQUENTIAL within a path;
PARALLEL across independent instance-paths up to
`W = min(#paths, browser-family pool 2 headless / 4 headed, ephemeral-instance cap ~3)`; HARD
GUARD: never run two paths on the same browser family or the same instance):

1. **Provision once at the leaf.** Dispatch `odoo-instance` (`odoo-instance-ops`,
   `CONTEXT: doc, MODE: path-incremental`, `--skip-auto-install --with-demo --load-language=<csv>`,
   EXCLUSIVE lease, `--ports 1`). THIS SKILL (not instance-ops) reads back
   `INSTANCE_HANDLE = <db>:<port>` from the returned instance-ops block.
2. **Walk `install_doc_sequence[]`** (each module M, leaf-dependency-first). For `M.doc == true`:
   1. **Marketing copy pre-fetch (TONE: marketing only).** If copy is not already supplied (the
      `module-packaging` workflow Phase 4 supplies it; a standalone run does not): first GUARANTEE
      `feature-catalog.jsonl` exists - use the caller/plan catalog, else dispatch
      `odoo-doc-feature-map` (which runs `odoo-feature-cataloger`) - then dispatch
      `odoo-content-draft` (landing-page-copy channel, grounded in that catalog) to produce the
      sectioned `<!-- HERO -->` ... copy with `[Image: <slug>]` markers. The writers NEVER call
      content-draft; the skill owns this pre-fetch.
   2. **Launch the writer(s) per DOC LAYER, SERIAL on this instance** (browser-exclusive - NEVER two
      writers concurrent on ONE instance): `userguide` -> `odoo-user-doc-writer`; `appstore` ->
      `odoo-marketing-writer`; `both` -> BOTH, one after the other on the same `INSTANCE_HANDLE`
      (two audience-pure capture passes - the marketing hero/feature-grid shots and the userguide
      per-step shots are DIFFERENT sets). Fan-out is free across MODULES/INSTANCES (each on its own
      family/instance), never within one instance.
      **Model selection (skill-owned).** The skill picks EACH writer's model at dispatch - default
      `sonnet`, override up/down per job complexity, scope, and module count (spawn-time resolution:
      env > Agent-param > frontmatter > inherit). The writer frontmatter carries only the default;
      no consumer sets a writer's model - model authority stays with this orchestrator.
   3. **Verify then commit.** Verify each writer's returned artifacts against its path-incremental
      completion block (files exist at the reported paths), then COMMIT M's docs via git-toolkit
      `git-ops` (per-module commit, one-way git; the skill never runs raw git mutations).
   For `M.doc == false` (dedup dependency): SKIP capture, still let instance-ops install it.
3. **Advance.** Tell `odoo-instance` to install the next delta (`init-delta` on the SAME DB) +
   `ensure-up`, then repeat step 2 for M+1. Convergence reuse+fill per `doc-plan.yaml`. THE SKILL
   decides WHEN to advance and WHEN to release the lease; instance-ops only executes each atomic op
   and returns its block.

Order per module: **install -> pre-fetch copy (marketing) -> capture + assemble (writer(s), serial)
-> verify -> commit -> next-delta.** Emit one aggregate index per run
(`doc-run-<timestamp>/index.jsonl`) listing every output path.

## Writer dispatch briefs

The skill launches each writer with a self-contained brief. `MODULE PATH` may be a bare module name
when `addons_path` is unknown - the writer resolves the absolute path from `context.md` or by
scanning disk. Omitting an axis field preserves today's behavior (see Documentation axes). The
shared browser-capture mechanics (2-tier write, headless/headed, on-theme check, per-locale loop,
`CAPTURE MODE` step-drive) live in `references/capture-mechanics.md` - the skill does not restate them.

**`odoo-user-doc-writer`** (DOC LAYER `userguide`, or the userguide half of `both`):
```
MODULE PATH: <abs path to module dir | module name>
INSTANCE_HANDLE: <db>:<port>          # from provision-once; absent = writer self-checks install
WALKTHROUGH: <abs path to walkthrough.jsonl from odoo-doc-scenarist>   # required for CAPTURE MODE: scenarios
FEATURE CATALOG: <abs path to feature-catalog.jsonl>                   # optional; feeds Usage + feature list
LANGUAGES: <resolved locale list, English-first>
DOC SCOPE: screenshot-doc | full-guide
CAPTURE MODE: screens | scenarios
extends_in_scope: [<base_module>, ...]
BROWSER MODE: headless | headed
```

**`odoo-marketing-writer`** (DOC LAYER `appstore`, or the appstore half of `both`):
```
MODULE PATH: <abs path to module dir | module name>
INSTANCE_HANDLE: <db>:<port>
MARKETING COPY: <abs path or inline sectioned copy from odoo-content-draft>   # REQUIRED - skill pre-fetches it
FEATURE CATALOG: <abs path to feature-catalog.jsonl>                          # REQUIRED - absent -> writer BLOCKS
LANGUAGES: <resolved locale list, English-first>
CAPTURE MODE: screens | scenarios
extends_in_scope: [<base_module>, ...]
BROWSER MODE: headless | headed
```

## Documentation axes

**Axis defaults** (omitting any field preserves today's behavior): DOC LAYER `appstore` (writes
`static/description/index.html`); TONE `technical`; DOC SCOPE `screenshot-doc`; CAPTURE MODE
`screens`. A dispatch that omits these fields behaves exactly as before - existing runs and tests
are unaffected.

**DOC LAYER** - which output files are produced and which writer runs:
- `appstore` -> `odoo-marketing-writer` writes `static/description/index.html` (App Store listing).
- `userguide` -> `odoo-user-doc-writer` writes `doc/index.rst` (user guide / RST documentation).
- `both` -> the skill launches BOTH writers serially on the same instance; each captures the shots
  it needs and writes its own file. No single agent writes both.

**Tab roles (App Store).** `static/description/index.html` = the **Description** tab (marketing /
overview); `doc/index.rst` = the **Documentation** tab (technical guide). Keep marketing out of the
RST and deep technical steps out of the HTML - do not duplicate content across the two.

**TONE (appstore index.html tone).** `technical` (default) = a plain technical-documentation
`index.html` (one `<h2>` per feature, OSM-grounded prose, screenshots). `marketing` =
`odoo-marketing-writer` assembles a brand-aware **App-Store landing page** per
`references/app-store-template.md` (sanitizer-safe fragment - no `<html>/<head>/<body>`, no JS, no
external CDN/Google-Fonts link; Bootstrap-5 utility classes; hex colors only; HTML entities;
relative image paths). The skill pre-fetches the copy from `odoo-content-draft`; the writer resolves
its `[Image: <slug>]` markers after capture and sources the Key Features grid from the feature
catalog. Brand palette/fonts come from `.odoo-ai/context.md` brand tokens or the brief - never
hardcode a vendor brand.

**DOC SCOPE (userguide structure).** `screenshot-doc` (default) = one section per feature with field
text + a screenshot. `full-guide` = `odoo-user-doc-writer` writes a structured guide with
`Installation`, `Configuration`, `Usage`, `Troubleshooting`, and `FAQ` sections. When a feature
catalog / walkthrough is supplied, the `Usage` section is generated from the walkthrough scenarios
and a Key-Features summary from `feature-catalog.jsonl`; otherwise the writer derives the structure
from OSM grounding.

**CAPTURE MODE (how screenshots are taken).** `screens` (default) = navigate to each screen and
snapshot. `scenarios` = consume the walkthrough `steps[]` (`{action: navigate|fill|click|select|wait,
target, value}`) and, for EACH step, perform the action then shoot that step
(`<scenario-slug>-step<NN>.<locale>.png`), with an optional state-assert via the live Odoo MCP
between steps. Requires a live, seeded instance and a `WALKTHROUGH:` path. Both writers honour it via
`references/capture-mechanics.md`.

**Image anchor markers.** `[Image: <slug>]` (slug only, no spaces - NOT `[[IMG:]]`) is the
placeholder that `odoo-content-draft` EMITS in the marketing copy; `odoo-marketing-writer` RESOLVES
each marker to a captured file after capture. `odoo-user-doc-writer` writes RST directly (no markers,
no content-draft). A marker that survives into a shipped artifact means the capture was degraded (see
Degraded paths).

## Provisioning, parallel cap, degraded paths

**Precondition provisioning (route to `odoo-instance`).** Before any capture the instance must be
provisioned cleanly for documentation: module installed `--with-demo` (so scenarios have sample
data), every resolved locale loaded (so the UI renders per-locale), and auto-install side modules
skipped (so the docs show only the target module's surface, not whatever Odoo pulls in). Resolve the
exact flags via OSM `cli_help` at runtime (version-aware - never hardcode flag names). The skill
VERIFIES this precondition and, if the instance was not provisioned this way, routes to
`odoo-instance` (provision) and emits a WARNING rather than documenting a polluted UI.

**Parallel capture (cap W + server-family isolation).** Browser-free waves (scoper, feature-map,
walkthrough, icon, copy) fan out wide. The browser-bound capture wave is bounded: each writer uses
ONE browser MCP server family (`playwright` / `chrome-devtools`, plus the headed families when
`DISPLAY` is present) AND one ephemeral instance. HARD GUARD: never assign two writers to the same
server family (shared server = race). `W = min(#(module x locale) browser-bound units, 2 headless /
4 with display, ~3 ephemeral instances)`; work beyond W is batched serially. State-mutating
(CRUD-heavy) scenario captures cap at <=2 simultaneous.

**Degraded paths (never hard-block the whole run).** Per-locale: if one locale fails to load/switch,
the writer reuses the English screenshots for that locale's doc with an `[Image: <slug>]` note and
reports `status: DONE_WITH_CONCERNS(locale <x>: English screenshots used)` - other locales proceed.
Global: with no instance/browser at all, the writer still assembles the structure + supplied copy
with `[Image: <slug>]` placeholders and routes to `odoo-instance` to fill captures later, instead of
`BLOCKED`.

**Headless/headed.** The skill defaults `BROWSER MODE: headless` - the only safe choice on a
no-display or CI host. Pass `headed` only when the user explicitly asks to watch the browser, and
only after confirming a display is plausibly available; warn rather than dispatch headed on a
headless host.

## Language resolution (6-tier + disk-UNION)

Resolve the documentation language list the skill passes as each writer's `LANGUAGES:` in this order
- first tier that yields a value wins (extends `skills/odoo-i18n/SKILL.md` P0 with one extra tier):
1. Explicit `LANGUAGES:` value already in the run / plan
2. `context.md` field `doc_languages` - a comma-string (e.g. `en_US,vi_VN`); split on `,` and trim
3. `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` field `default_languages`
4. Module `i18n/*.po` locales already present
5. `res.lang` active languages on the live instance
6. Fallback `["vi_VN"]`

**UNION with existing on-disk doc locales (mandatory, after tier resolution).** Scan
`static/description/` for `index.html` and `index_<locale>.html`; also scan `doc/` for `index.rst`
and `index_<locale>.rst` when DOC LAYER is `userguide` or `both`. Collect these as
`disk_doc_locales`. Final list = `tier_resolved_list` ∪ `disk_doc_locales`. Existing on-disk doc
locales are ALWAYS included - never pass a `LANGUAGES:` field that omits a locale already documented
on disk. This prevents silently dropping existing translations. Tiers 3-6 here = odoo-i18n P0 tiers
2-5; tier 2 (`context.md doc_languages`) is added in this stack only.

**English-mandatory canonical (marketing / full-guide branch).** When TONE is `marketing` or DOC
SCOPE is `full-guide`, the final language set = `{en_US}` ∪ resolved-set. English is the canonical,
suffix-less doc (`index.html`, `doc/index.rst`) and is force-included even if the registry omits it;
every other locale gets `index_<locale>.html` / `doc/index_<locale>.rst`. This is applied on top of
the shared resolver - it does NOT change the resolver's tier-6 hard fallback (`["vi_VN"]`) used by
the legacy screenshot-doc/technical path.

**Per-locale capture (CAPTURE MODE: scenarios).** Read-only screens stay language-neutral (capture
once, shared). A driven scenario MUTATES state, so it cannot be re-rendered with `?lang=`; the writer
re-drives each scenario from its precondition per locale (outer = locale, middle = scenario, inner =
step; English first and in full) - see `references/capture-mechanics.md`.

## INSTANCE_HANDLE + cross-reference

**INSTANCE_HANDLE (path-incremental).** In the per-instance loop the skill provisions the instance
once, reads back `INSTANCE_HANDLE = <db>:<port>` from the instance-ops block, and passes it to each
writer. A writer with `INSTANCE_HANDLE` uses that DB/port directly and does NOT self-provision; after
its writes it emits a path-incremental completion block so the skill can verify, commit, and advance
to the next module delta on the same live DB. A writer with NO `INSTANCE_HANDLE` (standalone dispatch)
self-checks that the module is installed and behaves as today.

**extends_in_scope (cross-reference hint).** An optional list of in-scope base module names (from the
planner/scoper `depends_in_scope ∩ doc:true` set). When non-empty, the writer inserts one
cross-reference per base - "Extends `<base>` - see its documentation" (a relative link when the base
is in the same addons path) - into `doc/index.rst` (`odoo-user-doc-writer`, any DOC SCOPE) and/or
`static/description/index.html` (`odoo-marketing-writer`, after the hero). Absent/empty -> nothing is
added; default behavior preserved.

## Standalone fallback

- **OSM unreachable:** the writers skip source-grounding and grep the repo on disk for module views
  and menu ids to confirm which screens exist, prefixing output with
  `WARNING: OSM unreachable - screen list inferred from disk grep, verify against live instance`.
- **Browser MCP or instance unreachable:** for TONE `marketing` or DOC SCOPE `full-guide`, the writer
  does the **degraded assembly** first (structure + supplied copy with `[Image: <slug>]`
  placeholders) then emits `status: NEEDS_NEXT` routing to `odoo-instance` (`operation: ensure-up`)
  so the run-harness provisions one and a later pass fills the captures. Fall back to
  `BLOCKED(Browser MCP unavailable - cannot capture screenshots)` only when even the degraded
  structure cannot be written.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
