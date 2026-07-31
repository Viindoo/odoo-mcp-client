---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >
  Produce and orchestrate illustrated documentation for an Odoo module or cluster - SOLE orchestrator:
  dispatches odoo-doc-scoper + odoo-doc-planner, gates the plan ONCE, then a branch-aware per-instance loop
  launching odoo-user-doc-writer (end-user doc/index.rst) and/or odoo-marketing-writer (App-Store
  index.html) per DOC LAYER. Axes: DOC LAYER appstore(default)|userguide|both; TONE technical|marketing; DOC
  SCOPE screenshot-doc|full-guide; CAPTURE MODE screens|scenarios. Fire on: "document an Odoo module with
  screenshots", "tạo tài liệu có ảnh cho module", "hướng dẫn sử dụng có ảnh cho module", "làm landing App
  Store cho module", "create RST user guide for module", "viết doc/index.rst cho module". Routing: text
  usage scenarios only, no screenshots -> odoo-doc-walkthrough; feature inventory/catalog ->
  odoo-doc-feature-map; record a video -> odoo-demo-recording; audit a screen -> odoo-ui-review; pure
  marketing copy only -> odoo-content-draft; module icon -> odoo-icon-design; write frontend code ->
  odoo-coding
---

## Role

Documentation-run orchestrator for Odoo modules and the SOLE orchestrator of a documentation run:
scope and plan the modules, gate the plan once, provision the live instance(s), then per module
launch two INTERNAL browser-driving writer agents that capture fully-rendered screenshots and embed
them into durable module documentation - `odoo-user-doc-writer` (end-user `doc/index.rst`) and
`odoo-marketing-writer` (App-Store `static/description/index.html`). Captured images land in the
module's `static/description/` so they survive across sessions and git commits. NOT for
auditing/rating a rendered screen (-> `odoo-ui-review`) - this skill captures to EMBED into docs.

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
the per-instance loop, verify, per-module commit, and writer model selection. The two writer agents
are INTERNAL leaf executors - only this skill launches them; no consumer reaches past the skill into
a writer. The writers NEVER spawn, call the Skill tool, call `odoo-content-draft`/`-scoper`/
`-planner`, or run a loop - ALL orchestration lives here.

**State dir resolution (once per run, before any writer dispatch).** This skill is the
cross-worktree dispatcher for its own pipeline (writers + end-of-run cleanup) - per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` §Cross-worktree dispatch, resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` ONCE, with cwd set to the run's target root (`doc_root` from the
scoper for multi-module; the module's own containing repo root for the single-module legacy path),
and CAPTURE both absolute paths for the rest of the run:
```
bash -c "cd <doc_root> && bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share"
bash -c "cd <doc_root> && bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh isolate"
```
Pass these captured literals as `SHARE_DIR:` / `ISOLATE_DIR:` fields in EVERY writer dispatch brief
(§Writer dispatch briefs below) and reuse the SAME captured `ISOLATE_DIR` value - never a fresh
resolve call - at the end-of-run staging cleanup step below, so the writers' staging path and the
cleanup's `rm -rf` target are guaranteed identical. `doc_root` is ALSO this run's `WORKTREE_PATH`
(`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 5 - each writer is a separate agent context
and does not inherit this skill's cwd) - pass it verbatim as `WORKTREE_PATH:` in every writer brief
alongside `SHARE_DIR:`/`ISOLATE_DIR:`; never let a writer re-derive its module root from its own cwd.

**Orphan sweep (crash backstop, do this every run, BEFORE any writer dispatch above and BEFORE
this run's own `<run_id>` exists below).** The end-of-run staging cleanup below only fires on a
clean finish - a run that crashed, was killed, or was abandoned mid-loop leaks its
`visual/<run_id>/` dir forever unless a later run reaps it. `visual/` itself is NOT a `<run_id>/`
directory - it is the shared parent of `baselines/`, `doc/` (SHARE, reusable - NEVER sweep) and
`current/`, `qa/`, `debug/`, `screenshots/`, `videos/` (other skills' OWN sibling ISOLATE trees -
NEVER sweep, they are not `<run_id>/` dirs and this skill does not own them), so the sweep MUST
exclude all seven by name rather than blindly sweeping every `visual/` child:

`find <ISOLATE_DIR>/visual/ -mindepth 1 -maxdepth 1 -type d ! -name baselines ! -name doc ! -name current ! -name qa ! -name debug ! -name screenshots ! -name videos -mmin +1440 -exec rm -rf {} +`

(any remaining child - by construction only a `<run_id>/` dir - untouched for over 24h is
presumed abandoned; a healthy doc run finishes well inside that window). Full rule + bound
rationale: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.
Enforcer: whoever executes `odoo-doc-illustration` next, unconditionally, every run.

**Single module.** A single module dir/name keeps the legacy single-module path with no
scoper/planner hop: provision (or receive an `INSTANCE_HANDLE`), then run the loop body ONCE
against that module - behavior unchanged.

**Multi-module** (TARGET is `local`, `worktree:<abs-path>`, or `repo:<abs-path>` with >1 module):
1. **Scope** - dispatch `odoo-doc-scoper` FIRST to enumerate `modules[]` with per-module
   `{abs_path, languages, doc_layer, has_demo, version, depends_in_scope, has_ondisk_doc}`.
   **Resume: read `_scope.md` back, do not re-scope.** The scoper writes `_scope.md` under
   `<SHARE_DIR>/documentation/<slug>-<date>/` (`${CLAUDE_PLUGIN_ROOT}/agents/odoo-doc-scoper.md`).
   Glob that dir for this slug first; a match is READ and used verbatim - skip the dispatch. The
   per-instance loop reads any scope field it needs from that file, never from a re-dispatch.
   Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 1.
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
`W = min(#paths, browser-family pool, ephemeral-instance cap ~3)` - browser-family pool size is per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity, the SSOT for
`W`; HARD GUARD: never run two paths on the same browser family or the same instance):

1. **Provision once at the leaf.** Dispatch `odoo-instance` (`odoo-instance-ops`,
   `CONTEXT: doc, MODE: path-incremental`, `--skip-auto-install --with-demo --load-language=<csv>`,
   EXCLUSIVE lease, `--ports 1`). THIS SKILL (not instance-ops) reads back
   `INSTANCE_HANDLE = <db>:<port>` PLUS `addons_path` from the returned instance-ops block (the full
   descriptor per `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`) and forwards
   `addons_path` as `ADDONS_PATH:` to every writer (§Writer dispatch briefs) so each can run the
   Addons coverage assertion against `WORKTREE_PATH` instead of trusting an unverified handle.
2. **Walk `install_doc_sequence[]`** (each module M, leaf-dependency-first). For `M.doc == true`:
   1. **Marketing copy pre-fetch (TONE: marketing only).** If copy is not already supplied (the
      `module-packaging` workflow Phase 4 supplies it; a standalone run does not): first GUARANTEE
      `feature-catalog.jsonl` exists - use the caller/plan catalog, else dispatch
      `odoo-doc-feature-map` (which runs `odoo-feature-cataloger`) - then dispatch
      `odoo-content-draft` (landing-page-copy channel, grounded in that catalog) to produce the
      sectioned `<!-- HERO -->` ... copy with `[Image: <slug>]` markers. The writers NEVER call
      content-draft; the skill owns this pre-fetch. `marketing` is the DOC LAYER `appstore` default
      (§ Documentation axes), so a bare appstore dispatch triggers this pre-fetch automatically.
   2. **Walkthrough pre-fetch (CAPTURE MODE: scenarios only).** If a `WALKTHROUGH:` path is not
      already supplied (a caller may pass one; a standalone `CAPTURE MODE: scenarios` run does
      not): dispatch `odoo-doc-walkthrough` (which fans out `odoo-doc-scenarist`) to produce
      `walkthrough.jsonl` for this module, then pass its path as `WALKTHROUGH:` to the writer(s)
      below. Conditional on `CAPTURE MODE: scenarios` only - the default `screens` mode does not
      need this pre-fetch (narrow blast radius). The writers NEVER call `odoo-doc-walkthrough`
      themselves; the skill owns this pre-fetch, mirroring the marketing-copy pre-fetch above.
   3. **Launch the writer(s) per DOC LAYER, SERIAL on this instance** (browser-exclusive PER FAMILY,
      per `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2 - NEVER two writers
      concurrent on ONE instance OR the SAME browser MCP family; distinct families/instances may run
      in parallel). Read `M.doc_layer` from THIS module's `install_doc_sequence`
      entry (SSOT: `skills/_shared/doc-cluster-plan.md` § schema); when `M.doc_layer` is absent (a
      `plan_source: design-dag` entry with no scoper pass), use the run-level DOC LAYER axis default
      (§ Documentation axes below) for that module only - never the other way round. Resolved value:
      `userguide` -> `odoo-user-doc-writer`; `appstore` -> `odoo-marketing-writer`; `both` -> BOTH, one
      after the other on the same `INSTANCE_HANDLE` (two audience-pure capture passes - the marketing
      hero/feature-grid shots and the userguide per-step shots are DIFFERENT sets). Fan-out is free
      across MODULES/INSTANCES (each on its own family/instance), never within one instance.
      **Model selection (skill-owned).** The skill picks EACH writer's model at dispatch - default
      `sonnet`, override up/down per job complexity, scope, and module count (spawn-time resolution:
      env > Agent-param > frontmatter > inherit). The writer frontmatter carries only the default;
      no consumer sets a writer's model - model authority stays with this orchestrator.
   4. **Verify then commit.** Verify each writer's returned artifacts against its path-incremental
      completion block (files exist at the reported paths), then COMMIT M's docs via git-toolkit
      `git-ops` (per-module commit, one-way git; the skill never runs raw git mutations).
   For `M.doc == false` (dedup dependency): SKIP capture, still let instance-ops install it.
3. **Advance.** Tell `odoo-instance` to install the next delta (`init-delta` on the SAME DB) +
   `ensure-up`, then repeat step 2 for M+1. Convergence reuse+fill per `doc-plan.yaml`. THE SKILL
   decides WHEN to advance and WHEN to release the lease; instance-ops only executes each atomic op
   and returns its block. Between advances, call `allocator.py heartbeat <token>` so the TTL
   backstop never reaps this long-lived path-incremental run - full rule:
   `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T3.

Order per module: **install -> pre-fetch copy (marketing) -> pre-fetch walkthrough (scenarios) ->
capture + assemble (writer(s), serial) -> verify -> commit -> next-delta.**

**End-of-run staging cleanup (skill-owned).** After the LAST module is verified + committed and
BEFORE emitting the aggregate index, delete this run's transient capture staging - scoped to
`<run_id>` ONLY. `visual/` is Tier-2 ISOLATE; reuse the SAME `<ISOLATE_DIR>` captured ONCE at
§State dir resolution above (the identical literal every writer this run staged under, per the
`SHARE_DIR:`/`ISOLATE_DIR:` fields in §Writer dispatch briefs) - do NOT re-resolve here, then:
```
rm -rf <ISOLATE_DIR>/visual/<run_id>/ .playwright-mcp/<run_id>/
```
HARD RULE: never `rm` another run's subtree (no bare `<ISOLATE_DIR>/visual/` or `.playwright-mcp/`); the
final committed images already live in each module's `static/description/` (or `doc/`), so removing
the run-scoped staging loses nothing.

**Files vs teardown (distinct steps - do all three, in order).** The staging `rm -rf` above handles
FILES only - it is NOT resource teardown; see
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2/T3 for pages and the lease. Before
emitting the aggregate index, also: (a) RELEASE the path-incremental instance lease via `odoo-instance`
(operation E / `allocator.py release <token> --run-id <id>`) - never leave the last module's instance
leased; (b) CLOSE every browser page a writer opened this run (`list_pages`, then `close_page` for
any stray this run created).

Then emit one aggregate index per run (`doc-run-<run_id>/index.jsonl`) listing every output path.

## Writer dispatch briefs

**Dispatch-brief skeleton.** When composing the dispatch prompt for `odoo-user-doc-writer`,
`odoo-marketing-writer`, or any other specialist agent dispatched below, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target
agent's Doc-writer family delta; never inline that file verbatim into a hard-leaf brief.

The skill launches each writer with a self-contained brief. `MODULE PATH` may be a bare module name
- the writer resolves the absolute path under `WORKTREE_PATH` (never its own cwd - a dispatched
agent does not inherit this skill's cwd, per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`
field 5) using `ADDONS_PATH`/`context.md` before falling back to a disk scan. Omitting an axis field
preserves today's behavior (see Documentation axes). Shared
browser-capture mechanics (2-tier write, headless/headed, on-theme check per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` - a screen with an empty or
self-referential token resolves off-theme and must be skipped, never embedded in shipped docs -
per-locale loop, `CAPTURE MODE` step-drive) live in `references/capture-mechanics.md`; the skill
does not restate them.

Both briefs carry `RUN_ID: <run-or-slug>` - REUSE the run's worklog run-or-slug (the id used for
`doc-run-<run_id>/index.jsonl`); do NOT mint a new id. Both briefs ALSO carry `WORKTREE_PATH:` /
`SHARE_DIR:` / `ISOLATE_DIR:` - the SAME absolute paths captured ONCE at §State dir resolution
above; writers use them literally per `references/capture-mechanics.md` section 3, never
re-resolving (WORKTREE_PATH is the cwd that section's Branch selection assumes - `cd` there first
if the agent's shell cwd differs). The writers
stage captures under `<ISOLATE_DIR>/visual/<run_id>/<module>_staging/...` (using the passed
`ISOLATE_DIR` literal), so two modules or concurrent runs never clobber each other, and the
end-of-run cleanup (which reuses the same literal) always finds the real staging tree.

**`odoo-user-doc-writer`** (DOC LAYER `userguide`, or the userguide half of `both`):
```
MODULE PATH: <abs path to module dir | module name>
RUN_ID: <run-or-slug>                 # reuse the worklog run-or-slug; scopes the staging dir
WORKTREE_PATH: <abs-path captured at State dir resolution (doc_root)>
SHARE_DIR: <abs-path captured at State dir resolution>
ISOLATE_DIR: <abs-path captured at State dir resolution>   # use directly - do NOT re-resolve
INSTANCE_HANDLE: <db>:<port>          # from provision-once; absent = writer self-checks install
ADDONS_PATH: <comma-joined dirs read back with INSTANCE_HANDLE>   # lets the writer run the Addons coverage assertion (snippets/instance-handle-contract.md) against WORKTREE_PATH
WALKTHROUGH: <abs path to walkthrough.jsonl from odoo-doc-scenarist>   # required for CAPTURE MODE: scenarios - skill pre-fetches via odoo-doc-walkthrough (§ per-instance loop step 2.2) when not already supplied
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
RUN_ID: <run-or-slug>                 # reuse the worklog run-or-slug; scopes the staging dir
WORKTREE_PATH: <abs-path captured at State dir resolution (doc_root)>
SHARE_DIR: <abs-path captured at State dir resolution>
ISOLATE_DIR: <abs-path captured at State dir resolution>   # use directly - do NOT re-resolve
INSTANCE_HANDLE: <db>:<port>
ADDONS_PATH: <comma-joined dirs read back with INSTANCE_HANDLE>   # lets the writer run the Addons coverage assertion (snippets/instance-handle-contract.md) against WORKTREE_PATH
MARKETING COPY: <abs path or inline sectioned copy from odoo-content-draft>   # REQUIRED - skill pre-fetches it
FEATURE CATALOG: <abs path to feature-catalog.jsonl>                          # REQUIRED - absent -> writer BLOCKS
LANGUAGES: <resolved locale list, English-first>
CAPTURE MODE: screens | scenarios
extends_in_scope: [<base_module>, ...]
BROWSER MODE: headless | headed
```

## Documentation axes

**Axis defaults.** DOC LAYER `appstore` (writes `static/description/index.html`); TONE
`marketing` when DOC LAYER resolves to `appstore` (an App-Store `index.html` is inherently
buyer-facing, so this default also makes the copy/catalog pre-fetch in step 2.1 below FIRE by
default, supplying `odoo-marketing-writer`'s REQUIRED `MARKETING COPY`/`FEATURE CATALOG` inputs -
see § TONE); the `userguide` layer is unaffected by TONE (TONE governs only the appstore
`index.html`, § TONE below). DOC SCOPE `screenshot-doc`; CAPTURE MODE `screens` - both unchanged
from before. A bare dispatch that omits every axis field now produces a marketing-toned App-Store
landing page by default: pass `TONE: technical` explicitly to keep the previous plain-technical
`index.html` (previously the default, which left the pre-fetch un-fired and could BLOCK
`odoo-marketing-writer` on its own REQUIRED inputs).

**DOC LAYER precedence (multi-module runs).** A per-module `doc_layer` on the `doc-plan.yaml`
`install_doc_sequence` entry (§ per-instance loop step 2 above) ALWAYS wins for that module; this
run-level DOC LAYER axis is the default applied only when a module's plan entry carries no
`doc_layer`. The single-module legacy path (no scoper/planner hop) has no plan entry, so the
run-level axis is authoritative there.

**DOC LAYER** - which output files are produced and which writer runs:
- `appstore` -> `odoo-marketing-writer` writes `static/description/index.html` (App Store listing).
- `userguide` -> `odoo-user-doc-writer` writes `doc/index.rst` (user guide / RST documentation).
- `both` -> the skill launches BOTH writers serially on the same instance; each captures the shots
  it needs and writes its own file. No single agent writes both.

**Tab roles (App Store).** `static/description/index.html` = the **Description** tab (marketing /
overview); `doc/index.rst` = the **Documentation** tab (technical guide). Keep marketing out of the
RST and deep technical steps out of the HTML - do not duplicate content across the two.

**TONE (appstore index.html tone).** `marketing` (default when DOC LAYER resolves to `appstore`) =
`odoo-marketing-writer` assembles a brand-aware **App-Store landing page** per
`references/app-store-template.md` (sanitizer-safe fragment - no `<html>/<head>/<body>`, no JS, no
external CDN/Google-Fonts link; Bootstrap-5 utility classes; hex colors only; HTML entities;
relative image paths). The skill pre-fetches the copy from `odoo-content-draft`; the writer resolves
`[Image: <slug>]` markers after capture and sources the Key Features grid from the feature catalog.
Brand palette/fonts come from `context.md` brand tokens (Tier-2 SHARE; resolve via the
resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`,
i.e. `<SHARE_DIR>/context.md`) or the brief - never hardcode a vendor brand. `technical` (opt-in via
`TONE: technical`) = a plain technical-documentation `index.html` intent (one `<h2>` per feature,
OSM-grounded prose, screenshots). `odoo-marketing-writer` is the sole `appstore` writer regardless
of TONE, and its `MARKETING COPY`/`FEATURE CATALOG` inputs are UNCONDITIONALLY REQUIRED (hard
BLOCK if absent, per `odoo-marketing-writer.md` § Required inputs) - the copy pre-fetch above is
gated on `TONE: marketing`, so an explicit `TONE: technical` dispatch does NOT trigger it and the
caller must supply `MARKETING COPY` some other way or the writer BLOCKs. Prefer the `marketing`
default unless a caller has its own copy-supply path for `technical`.

**DOC SCOPE (userguide structure).** `screenshot-doc` (default) = one section per feature with field
text + a screenshot. `full-guide` = `odoo-user-doc-writer` writes a structured guide with
`Installation`, `Configuration`, `Usage`, `Troubleshooting`, `FAQ`. With a feature catalog /
walkthrough supplied, `Usage` is generated from the walkthrough scenarios and a Key-Features summary
from `feature-catalog.jsonl`; otherwise the writer derives the structure from OSM grounding.

**CAPTURE MODE (how screenshots are taken).** `screens` (default) = navigate to each screen and
snapshot. `scenarios` = consume the walkthrough `steps[]` (`{action: navigate|fill|click|select|wait,
target, value}`) and, for EACH step, perform the action then shoot it
(`<scenario-slug>-step<NN>.<locale>.png`), with an optional state-assert via the live Odoo MCP
between steps. Requires a live, seeded instance and a `WALKTHROUGH:` path. Both writers honour it via
`references/capture-mechanics.md`.

**Image anchor markers.** `[Image: <slug>]` (slug only, no spaces - NOT `[[IMG:]]`) is the
placeholder `odoo-content-draft` EMITS in the marketing copy; `odoo-marketing-writer` RESOLVES each
to a captured file after capture. `odoo-user-doc-writer` writes RST directly (no markers, no
content-draft). A marker surviving into a shipped artifact means the capture was degraded (see
Degraded paths).

## Provisioning, parallel cap, degraded paths

**Precondition provisioning (route to `odoo-instance`).** Before any capture the instance must be
provisioned cleanly: module installed `--with-demo` (sample data for scenarios), every resolved
locale loaded (per-locale UI), and auto-install side modules skipped (docs show only the target
module's surface). Resolve the exact flags via OSM `cli_help` at runtime (version-aware - never
hardcode flag names). The skill VERIFIES this precondition; if not met, it routes to `odoo-instance`
(provision) and emits a WARNING rather than documenting a polluted UI.

**Parallel capture (cap W + server-family isolation).** Browser-free waves (scoper, feature-map,
walkthrough, icon, copy) fan out wide. The browser-bound wave is bounded: each writer uses ONE
browser MCP server family (`chrome-devtools` (default) / `playwright` (opt-in), plus headed families
when `DISPLAY` is present) AND one ephemeral instance. HARD GUARD: never assign two writers to the
same server family (shared server = race). `W = min(#(module x locale) browser-bound units,
browser-family pool, ~3 ephemeral instances)` - browser-family pool size is per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity, the SSOT for
`W`; work beyond W batches serially. State-mutating (CRUD-heavy) scenario captures cap at <=2
simultaneous.

**Degraded paths (never hard-block the whole run).** Per-locale: if a locale fails to load/switch,
the writer reuses the English screenshots for that locale's doc with an `[Image: <slug>]` note and
reports `status: DONE_WITH_CONCERNS(locale <x>: English screenshots used)` - other locales proceed.
Global: with no instance/browser, the writer still assembles the structure + supplied copy with
`[Image: <slug>]` placeholders and routes to `odoo-instance` to fill captures later, instead of
`BLOCKED`.

**Headless/headed.** The skill defaults `BROWSER MODE: headless` - the only safe choice on a
no-display / CI host. Pass `headed` only when the user explicitly asks to watch, and only after
confirming a display is plausibly available; warn rather than dispatch headed on a headless host.

## Language resolution (6-tier + disk-UNION)

**SSOT.** This section is the single source of truth for the 6-tier language resolver (+
disk-UNION). Any other file that describes this resolution order (e.g. `app-store-template.md`,
`doc-scoper.md`) or cites it (`user-doc-writer.md`, `marketing-writer.md`) MUST cross-reference this
section rather than restate the tiers - do not fork a second copy of this order elsewhere.

Resolve the documentation language list the skill passes as each writer's `LANGUAGES:` in this order
- first tier that yields a value wins (extends `skills/odoo-i18n/SKILL.md` P0 with one extra tier):
1. Explicit `LANGUAGES:` value already in the run / plan
2. `context.md` field `doc_languages` - a comma-string (e.g. `en_US,vi_VN`); split on `,` and trim
3. `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` field `default_languages`
4. Module `i18n/*.po` locales already present
5. `res.lang` active languages on the live instance
6. Fallback `["vi_VN"]`

**UNION with existing on-disk doc locales (mandatory, after tier resolution).** Scan
`static/description/` for `index.html` / `index_<locale>.html`; also scan `doc/` for `index.rst` /
`index_<locale>.rst` when DOC LAYER is `userguide` or `both`. Collect as `disk_doc_locales`. Final
list = `tier_resolved_list` ∪ `disk_doc_locales`. On-disk doc locales are ALWAYS included - never
pass a `LANGUAGES:` field that omits a locale already documented on disk (prevents silently dropping
translations). Tiers 3-6 here = odoo-i18n P0 tiers 2-5; tier 2 (`context.md doc_languages`) is added
in this stack only.

**English-mandatory canonical (marketing / full-guide branch).** When TONE is `marketing` or DOC
SCOPE is `full-guide`, the final set = `{en_US}` ∪ resolved-set. English is the canonical,
suffix-less doc (`index.html`, `doc/index.rst`), force-included even if the registry omits it; every
other locale gets `index_<locale>.html` / `doc/index_<locale>.rst`. Applied on top of the shared
resolver - it does NOT change the resolver's tier-6 hard fallback (`["vi_VN"]`) used by the legacy
screenshot-doc/technical path.

**Per-locale capture (CAPTURE MODE: scenarios).** Read-only screens stay language-neutral (capture
once, shared). A driven scenario MUTATES state so it cannot be re-rendered with `?lang=`; the writer
re-drives each scenario from its precondition per locale (outer = locale, middle = scenario, inner =
step; English first and in full) - see `references/capture-mechanics.md`.

## INSTANCE_HANDLE + cross-reference

**INSTANCE_HANDLE (path-incremental).** In the per-instance loop the skill provisions once, reads
back `INSTANCE_HANDLE = <db>:<port>` plus `addons_path` from the instance-ops block, and passes both
(the latter as `ADDONS_PATH:`) to each writer. A writer with `INSTANCE_HANDLE` uses that DB/port
directly and does NOT self-provision; after its
writes it emits a path-incremental completion block so the skill can verify, commit, and advance to
the next module delta on the same live DB. A writer with NO `INSTANCE_HANDLE` (standalone dispatch)
self-checks that the module is installed and behaves as today.

**extends_in_scope (cross-reference hint).** An optional list of in-scope base module names (from the
planner/scoper `depends_in_scope ∩ doc:true` set). When non-empty, the writer inserts one
cross-reference per base - "Extends `<base>` - see its documentation" (a relative link when the base
shares the addons path) - into `doc/index.rst` (`odoo-user-doc-writer`, any DOC SCOPE) and/or
`static/description/index.html` (`odoo-marketing-writer`, after the hero). Absent/empty -> nothing
added; default behavior preserved.

## Standalone fallback

- **OSM unreachable:** the writers skip source-grounding and grep the repo on disk for module views
  and menu ids to confirm which screens exist, prefixing output with
  `WARNING: OSM unreachable - screen list inferred from disk grep, verify against live instance`.
- **Browser MCP or instance unreachable:** for TONE `marketing` or DOC SCOPE `full-guide`, the writer
  does the **degraded assembly** first (structure + supplied copy with `[Image: <slug>]`
  placeholders) then emits `status: NEEDS_NEXT` routing to `odoo-instance` (`operation: ensure-up`)
  so the run-harness provisions one and a later pass fills the captures - screen captures are the
  instance-REQUIRED part of this deliverable (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md`).
  Fall back to
  `BLOCKED(Browser MCP unavailable - cannot capture screenshots)` only when even the degraded
  structure cannot be written.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
