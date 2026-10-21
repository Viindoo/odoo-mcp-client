---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >-
  Module docs with live screenshots: in-module user guide and App Store page
---

## Role

Front door for the documentation that ships inside Odoo modules (`doc/index.rst`, the App Store
page `static/description/index.html`), illustrated with live screenshots. A product documentation
site kept in its own repository is `odoo-doc-site`. It settles the tree the docs land
in, plans the instances a multi-module package needs, provisions each instance, launches ONE
`odoo-doc-writer` per module (`MODE: full` for the user guide, resumed with `MODE: landing` for
the App Store page), verifies the references, commits per module and releases what it leased.

## Out of Scope

- **Record a video or GIF walkthrough** -> `odoo-demo-recording`
- **Rate or audit a rendered screen** (aesthetics, a11y, Lighthouse) -> `odoo-ui-review`
- **Pure text draft** (blog post, marketing copy, no capture) -> `odoo-content-draft`
- **Spec or outline before any code or doc exists** -> `odoo-solution-design`
- **Compare two builds for visual drift** -> `odoo-visual-regression`
- **Write or fix frontend source** -> `odoo-coding`
- **The catalog, role map or walkthrough text alone, no browser** -> `odoo-doc-feature-map`
- **A product documentation site** (its own repository, a branch per series) -> `odoo-doc-site`

## Inputs

`TARGET`: one module (name or path), or `local`, `worktree:<abs-path>`, `repo:<abs-path>` for a
multi-module package. Optional axes, per module or for the run: `DOC LAYER` (`userguide`,
`appstore`, `both`; default `both`), `DOC SCOPE` (`screenshot-doc` default, `full-guide`),
`CAPTURE MODE` (`screens` default, `scenarios`), `BROWSER MODE` (`headless` default), `LANGUAGES`,
`TARGET MARKET`, and `CHANGE`: the path of a change file (`<ISOLATE_DIR>/docs/change-<slug>.md`, one
line per added, changed or removed user-visible feature with its module and UI label) or `whole`; a
module's feature list is the lines of that file that name the module. `CHANGE` is the one update input: with a feature list
the writer rewrites only the affected sections and recaptures only the affected screens; `whole`
documents the module again from scratch; absent, a module that already ships docs is left alone
(`doc:false`, step 3). A caller may supply per-module `FEATURE CATALOG`, `ROLE MAP`, `WALKTHROUGH`,
`MARKETING COPY`, `BUYER PROFILE`; each is forwarded and never rebuilt.

## Steps

1. **The tree** (read-only until the plan of step 3 is decided). `doc_root` = the worktree the caller names
   (`WORKTREE_PATH`, `worktree:`), else the `repo_root` of a `repo_facts` call on the module path. One
   `repo_facts` call on `doc_root` tells the kinds apart, with `status_paths` = each module path and
   its in-repo dependencies: `is_linked_worktree` true is a linked worktree, used as is; false is a
   principal checkout, which never takes a write - when `dirty` lists anything, ask once as a text question (commit first, or document
   HEAD without it) before the plan is presented. `is_repo` false: use it as is, nothing to commit.
   Capture `SHARE_DIR` once with `project_dir` (`cwd` = `doc_root`, axis `share`).
2. **Scope and plan (inline, no launch).** Per module: `abs_path`, `version`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`), `languages` (§ Language
   resolution), `doc_layer`, `has_demo`, `depends_in_scope`, `has_ondisk_doc`, `change`, `target_market`
   proposed from the descriptor (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/buyer-profile.md`
   § Target market) - field rules in `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-cluster-plan.md`
   § Input. One module: one instance, one step. Several: compute `doc-plan.yaml` per that file's
   algorithm (clusters, branch-aware instances, leaf-first order, dedup, `W`) and write it to
   `<SHARE_DIR>/documentation/<slug>-<date>/doc-plan.yaml`. Per module also list the sections of
   its guide and App Store page the run will write or recapture and the screens it will capture:
   with `change`, the ones the change file's lines name; otherwise every section and screen of the
   module (`module_inspect`).
3. **Plan decision - always, also for one module with every input resolved.** When this skill
   owns the request, present the whole plan through Plan Mode
   (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request):
   `EnterPlanMode`, show modules, instances and order, the sections and screens per module,
   `doc:false` modules with their reason (a module with docs on disk and no `change` is listed;
   `refine: redo <module>` sets its `change` to `whole`), `W`, one `TARGET MARKET` row per appstore
   module for the user to correct, then `ExitPlanMode` on approve. `refine: [feedback]` recomputes
   the plan; `cancel` leaves nothing behind. Under an approved plan - a plan node, a workflow
   phase, the closing documentation of another run - present no gate: write the plan into the
   return and continue with the proposed target markets. Once the plan is decided, a principal
   checkout gets its docs worktree: invoke `git-toolkit:git-ops` to create a worktree and branch at
   HEAD under `worktree_root` = `project_dir` (axis `worktree`, `name` = `docs-<slug>`) and re-root
   every module path into it. Then capture `ISOLATE_DIR` with `project_dir` (`cwd` = `doc_root`,
   axis `isolate`) and pass the same literals to every launch and to step 7.
4. **Orphan sweep**, before any launch: remove abandoned staging of earlier runs -

   ```
   find <ISOLATE_DIR>/visual/ -mindepth 1 -maxdepth 1 -type d ! -name baselines ! -name doc ! -name current ! -name qa ! -name debug ! -name screenshots ! -name videos ! -name adhoc -mmin +1440 -exec rm -rf {} +
   ```
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3).
5. **Per instance path** (sequential within a path; paths in parallel up to `W`, each on its own
   browser family and instance - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
   § Browser exclusivity):
   1. Invoke `Skill(odoo-instance)` inline with `CONTEXT: doc`, `MODE_HINT: path-incremental`,
      `LANGUAGES`, `RUN_ID`, `WORKTREE_PATH: <doc_root>` for the first delta; keep the returned
      block verbatim as `INSTANCE_HANDLE` and its `addons_path` as `ADDONS_PATH`.
   2. For each module `M` of the path, leaf first. `doc:false`: install only (step 5.5).
      Otherwise run the gate of `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`
      § Reference gate (`--series` = M's resolved series) on `M` with no file arguments and keep
      its findings as the baseline, then launch
      `odoo-doc-writer` (brief in `references/writer-brief.md`; `model` per
      `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection: composing
      new text is sonnet, a `change` made only of relabels and recaptures is haiku) with
      `MODE: full` when the layer includes `userguide`, else `MODE: landing`.
   3. Layer `both`: when the `full` round returns, send the same writer `MODE: landing` with
      `SendMessage` - never a second launch; it holds the catalog and the captures.
   4. **Verify.** Every reported file exists. Run the reference gate on `M` with no file
      arguments; exit 2 stops the run `NEEDS_CONTEXT`. Compare each exit-1 finding with the
      baseline (same file, rule and reference): `IMG_ORPHAN` -> delete the file yourself and
      include it in the commit; a finding not in the baseline, or a baseline finding in a file of
      this run's layer -> send it to the writer as `FINDINGS` and re-run the gate; a baseline
      finding in a file left untouched -> `concerns`, not a block. Then commit `M`'s docs in
      `doc_root` through `git-toolkit:git-ops`, one commit per module.
   5. Advance: `Skill(odoo-instance)` inline with the held `lease_token` for the next delta
      (init-delta on the same database), then ensure-up; a convergence fill reuses the branch
      instance per `doc-plan.yaml`. One lease per path; never a second.
6. **Release** every lease this run took (`odoo-instance` step E, or
   `mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with the token and `RUN_ID`), then
   delete this run's staging only: `rm -rf <ISOLATE_DIR>/visual/<run_id>/` (never a bare
   `visual/`).
7. **Return.** The plan of step 3; `doc-run-<run_id>/index.jsonl` listing every output path; the worktree and branch
   when step 3 created them (this skill never merges or pushes); the `concerns` collected.

## Language resolution

The locale list passed as `LANGUAGES` to every launch, first tier that yields a value: the
brief's `LANGUAGES`; `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` `default_languages`; the module's
`i18n/*.po` locales; `res.lang` active languages on the live instance. All four empty:
`NEEDS_CONTEXT(documentation language)` - no built-in default.
Then union with the locales already documented on disk (`index_<locale>.html`,
`doc/index_<locale>.rst`) so no translation is dropped, and add `en_US`, the canonical suffix-less
file.

## Standalone-first fallback

OSM unreachable: the writer grounds labels from the module tree and prefixes its report
`WARNING: OSM unreachable - labels from disk source`. No browser or no instance: the writer
writes the structure with `[Image: <slug>]` placeholders and returns `NEEDS_NEXT` ->
`odoo-instance`; `BLOCKED` only when even the structure cannot be written.

## Agent-managed tools

`odoo-doc-writer` (modes `full`, `landing`); `odoo-instance` inline for every lease.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
index path and every doc file; `status: DONE` with `concerns`.
