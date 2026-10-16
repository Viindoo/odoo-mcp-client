---
name: odoo-doc-illustration
argument-hint: "[module] [doc target]"
description: >-
  Module docs with live screenshots: App Store page and/or RST user guide
---

## Role

Front door for documenting Odoo modules with live screenshots. It settles the tree the docs land
in, plans the instances a multi-module package needs, provisions each instance, launches ONE
`odoo-doc-writer` per module (`MODE: full` for the user guide, resumed with `MODE: landing` for
the App Store page), verifies the references, commits per module and releases what it leased.
The writer owns the documents; this skill owns the tree, the instances and the order.

## Out of Scope

- **Record a video or GIF walkthrough** -> `odoo-demo-recording`
- **Rate or audit a rendered screen** (aesthetics, a11y, Lighthouse) -> `odoo-ui-review`
- **Pure text draft** (blog post, marketing copy, no capture) -> `odoo-content-draft`
- **Spec or outline before any code or doc exists** -> `odoo-solution-design`
- **Compare two builds for visual drift** -> `odoo-visual-regression`
- **Write or fix frontend source** -> `odoo-coding`
- **The catalog, role map or walkthrough alone, no browser** -> `odoo-doc-feature-map` /
  `odoo-doc-walkthrough`

## Inputs

`TARGET`: one module (name or path), or `local`, `worktree:<abs-path>`, `repo:<abs-path>` for a
multi-module package. Optional axes, per module or for the run: `DOC LAYER` (`userguide`,
`appstore`, `both`; default `both`, else what the module already ships on disk), `DOC SCOPE`
(`screenshot-doc` default, `full-guide`), `CAPTURE MODE` (`screens` default, `scenarios`),
`BROWSER MODE` (`headless` default), `LANGUAGES`, `TARGET MARKET`, `REDOC`. A caller may supply
per-module `FEATURE CATALOG`, `ROLE MAP`, `WALKTHROUGH`, `MARKETING COPY`, `BUYER PROFILE`; each
is forwarded and never rebuilt.

## Steps

1. **The tree.** `doc_root` = the worktree the caller names (`WORKTREE_PATH`, `worktree:`), else
   the top level of the repo holding the module. One bounded read tells the kinds apart
   (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Bounded-read allowlist):
   `git -C <doc_root> rev-parse --path-format=absolute --git-dir --git-common-dir`. Two paths: a
   linked worktree, used as is. The same path twice: a principal checkout, which never takes a
   write - run `git -C <doc_root> status --porcelain -- <each module path and its in-repo
   dependencies>`; when it lists anything, ask once (commit first, or document HEAD without it)
   as part of the gate of step 3; then invoke `git-toolkit:git-ops` to create a docs worktree and
   branch at HEAD under `worktree_root` = `project_dir` (axis `worktree`, `name` = `docs-<slug>`),
   and re-root every module path into it. Not under git: use it as is, nothing to commit. Then
   capture `SHARE_DIR` and `ISOLATE_DIR` once with `project_dir` (`cwd` = `doc_root`, axes
   `share` and `isolate`) and pass the same literals to every launch and to step 7.
2. **Scope and plan (inline, no launch).** Per module: `abs_path`, `version`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`), `languages` (§ Language
   resolution), `doc_layer`, `has_demo`, `depends_in_scope`, `has_ondisk_doc`, `target_market`
   proposed from the descriptor (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/buyer-profile.md`
   § Target market) - field rules in `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-cluster-plan.md`
   § Input. One module: one instance, one step. Several: compute `doc-plan.yaml` per that file's
   algorithm (clusters, branch-aware instances, leaf-first order, dedup, `W`) and write it to
   `<SHARE_DIR>/documentation/<slug>-<date>/doc-plan.yaml`.
3. **One gate.** Present the whole plan - modules, instances and order, `doc:false` modules with
   their reason, `W`, one `TARGET MARKET` row per appstore module, the uncommitted-changes
   question of step 1 - for one `approve / refine: [feedback] / cancel`. `refine` recomputes the
   plan; `cancel` leaves nothing behind. A single module with every input resolved skips the gate
   except the target-market and uncommitted-changes questions, asked once.
4. **Orphan sweep**, before any launch: remove abandoned staging of earlier runs -

   ```
   find <ISOLATE_DIR>/visual/ -mindepth 1 -maxdepth 1 -type d ! -name baselines ! -name doc ! -name current ! -name qa ! -name debug ! -name screenshots ! -name videos ! -name adhoc -mmin +1440 -exec rm -rf {} +
   ```
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3; the eight
   named children are other owners' trees).
5. **Per instance path** (sequential within a path; paths in parallel up to `W`, each on its own
   browser family and instance - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
   § Browser exclusivity):
   1. Invoke `Skill(odoo-instance)` inline with `CONTEXT: doc`, `MODE_HINT: path-incremental`,
      `LANGUAGES`, `RUN_ID`, `WORKTREE_PATH: <doc_root>` for the first delta; keep the returned
      block verbatim as `INSTANCE_HANDLE` and its `addons_path` as `ADDONS_PATH`.
   2. For each module `M` of the path, leaf first. `doc:false`: install only (step 5.5).
      Otherwise run the reference gate of `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`
      on `M` with no file arguments and keep its findings as the baseline, then launch
      `odoo-doc-writer` (`model: sonnet`, brief in `references/writer-brief.md`) with `MODE: full`
      when the layer includes `userguide`, else `MODE: landing`.
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
7. **Return.** `doc-run-<run_id>/index.jsonl` listing every output path; the worktree and branch
   when step 1 created them (this skill never merges or pushes); the `concerns` collected.

## Language resolution

The locale list passed as `LANGUAGES` to every launch, first tier that yields a value: the
brief's `LANGUAGES`; `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` `default_languages`; the module's
`i18n/*.po` locales; `res.lang` active languages on the live instance. All four empty:
`NEEDS_CONTEXT(documentation language)` - no built-in default, the same rule as `odoo-i18n`.
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
