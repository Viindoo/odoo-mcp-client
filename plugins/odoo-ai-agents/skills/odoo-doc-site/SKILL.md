---
name: odoo-doc-site
argument-hint: "[site] [series...] [area|modules] [pages] [FROM CHANGE]"
description: >-
  Writes docs-site pages (Sphinx, branch per series) with live screenshots
---

## Role

Front door for writing or updating the pages of a product documentation site kept in its own
repository: one branch, one worktree and one pull request per series. Audience: the site's readers
(roles and audience come from the site row). It launches `odoo-doc-site-writer` per disjoint page
group.

## Out of Scope

- **Docs that ship inside a module** (`doc/index.rst`, the App Store page) -> `odoo-doc-illustration`
- **Marketing copy, blog, landing text** -> `odoo-content-draft`
- **A video or GIF of a workflow** -> `odoo-demo-recording`
- **The catalog, role map or walkthrough alone** -> `odoo-doc-feature-map`
- **Rating a screen** -> `odoo-ui-review`; **fixing a branding gap in module source** -> `odoo-coding`
- **Merging the PR or watching it to merge** -> `odoo-pr-monitoring`
- **Porting pages from a lower series to a higher one** -> `odoo-forward-port` (its docs-site lane
  invokes this skill with `WORKTREE` and `LAND: caller`)

## Inputs

`SITE` (key or repo), `SERIES` (one or several; each is its own worktree, branch and PR), the
`AREA` (app cluster) or a module list, an optional page list, and these optional inputs:

- `FROM CHANGE` - the path of a change file (`<ISOLATE_DIR>/docs/change-<slug>.md`) when this skill
  is the tail of a code change: one line per changed user-visible feature with its module and UI
  label. Read it; the plan then holds only the pages and shots those features touch.
- `CODE_WORKTREE` - absolute path of the code being documented. As a plan tail node it is
  `<code repo>/run-integration`. Absent: the catalog row's addons path.
- `RUN_ID` - the caller's run id. Standalone: make one per series.
- `INSTANCE_HANDLE` - optional: a demo build the caller already holds. When its series is the target, `demo` is true, `languages_loaded`
  holds every site language, its build reported `auto_install: on` and its `addons_path` covers
  `CODE_WORKTREE` (else the catalog addons), step 3 installs the plan's missing modules on that
  lease by a delta `init` and provisions nothing; the caller releases it.
- `WORKTREE` with `LAND: caller` - a caller that owns the branch (`odoo-forward-port`) hands the
  series worktree in: step 0 creates no worktree and no branch, steps 7-8 run nothing, and the
  return carries the file list for the caller to commit. It may add `PAGE PLAN`, the rows it
  decided (`work: port` for a page to re-verify on this series, `skip` for one forwarded as it
  is): step 1 keeps those rows, adds only the `skip` rows of pages an open pull request already
  covers, and presents no gate.

A missing `SITE` or `SERIES` is asked once. This skill lands its own pull request (steps 7-8); a
plan that runs it follows it with monitor and merge only.

## Steps

`RUN_DIR` = `<ISOLATE_DIR>/docs-site/<RUN_ID>/`. Plugin scripts run with `python3`;
`build_compare.py`, `po_sync.py` and `images.py install` run with `DOCS PYTHON`.

The page plan (step 1, `references/page-plan.md` § 4) is the one Plan-Mode gate of this skill. Nothing below asks again: a step
that cannot finish returns `BLOCKED` with its evidence. Only a push or a pull request is an outward
action that gets a text confirmation (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`).

0. **Resolve** (`references/site-row.md`). Read-only until the page plan of step 1 is decided: no
   worktree, branch or file in the repository before then.
   - Read the site row; none for the repo -> `NEEDS_CONTEXT`: run `/odoo-ai-agents:odoo-setup
     docs-site`.
   - Per series, the local repo to branch from is the series' `clone`, else any other `clone` of the
     row, else stop `NEEDS_CONTEXT`
     and print the command that clones `remote` into a directory beside the user's other clones, for
     the user to run; never clone.
   - Capture `SHARE_DIR` once with `project_dir` (axis `share`, `cwd` = that repo).
   - After step 1, per series: take the worktree path from `project_dir` (axis
     `worktree`, `cwd` = that repo, `name` = the branch slug) and invoke `git-toolkit:git-ops` to
     fetch and create the worktree plus a new branch from the series' upstream branch there; the
     clone path is never written. A given `WORKTREE` is that worktree: create nothing. Then capture `ISOLATE_DIR` per series worktree with
     `project_dir` and pass the same literals everywhere.
   - Docs venv: run `docs_python.py venv --worktree <worktree> --venv
     <SHARE_DIR>/docs-site/<site>/<series>/venv --json`. It builds the venv on the Python the docs
     repo states, else the newest interpreter that installs `requirements.txt`; record its `python`
     as `DOCS PYTHON`. Exit 3 (no interpreter installs them): `NEEDS_CONTEXT` with its `tried` list.
   - Write `<RUN_DIR>policy.json` from `docs_site_config.py show --key <site>` (the row's `policy`
     object); every gate and writer uses that path.
   - Run `repo_facts.py --worktree <worktree> --json` and save the result to
     `<RUN_DIR>repo-facts.json` (the writers' `REPO FACTS`). `NEEDS_CONTEXT` when `series_agree` is
     false or `series` differs from the row's series.
   - When the check shot runs (`references/check-shot.md` § When it runs), run `build_compare.py`
     on the fresh worktree (candidate equals base, before any edit) and `build_compare.py serve` it:
     step 3 measures the content widths on it, then the server is stopped.
1. **Find existing content before writing** (`references/page-plan.md`) - mandatory, per series.
   Map the area to modules, search the branch and the open pull requests, write the page plan
   (`update | new | skip` per page), then decide it per `references/page-plan.md` § 4.
2. **Facts.** Per module of the plan without a catalog: invoke `odoo-doc-feature-map`. Each page
   group has its own facts file `<SHARE_DIR>/docs-site/<site>/<series>/facts/<area>.<group>.md`,
   written by that group's writer (`file:symbol` citations); a live-UI difference is a finding.
3. **Capture instance, then the check shot** (`references/check-shot.md`).
   - The site documents the product as users run it, so its capture database is built with
     auto-install on. With a covering `INSTANCE_HANDLE` whose build reported `auto_install: on`:
     invoke `odoo-instance` with `operation: init` on that handle for the modules the plan needs
     that it lacks, then `ensure-up`; skip the create below. A handle built with auto-install
     skipped does not cover a site: leave it to its owner and create.
     Otherwise invoke `odoo-instance` with `operation: create`, `context: doc`,
     `skip_auto_install: false`, `series` and `PROFILE` = the
     series and profile of the row's `instance` key (`<series>:<profile>`; no profile part: omit
     `PROFILE`), `modules` = the
     documented modules plus the row's `extra_modules` plus the bridge modules matching
     `module_bridge_patterns` for every app the plan shows (one build, one instance, one lease per
     series; a module Odoo auto-installs only for a company of one country is not added by this
     build, whose main company has no country - the row's `extra_modules` names the localization
     modules the site documents), `demo: on`, `languages` = every site language, `persist: exclusive-running`,
     `WORKTREE_PATH` = `CODE_WORKTREE` when given, `run_id` = `RUN_ID`. Keep the
     returned block verbatim as `INSTANCE_HANDLE`. Build, update and reinstall decisions follow
     `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md` § Decision tree.
   - The check shot runs when `references/check-shot.md` § When it runs says so; its launch also
     measures the content widths on the served build. Stop the server once they are recorded.
     This skill writes the content-width record from the `reference_viewport` and `content_widths`
     the writer returns.
4. **Write.** Launch `odoo-doc-site-writer` per disjoint page group (`references/writer-brief.md`).
   Model tier per `references/writer-brief.md`. Groups run in parallel only up to `W` of
   § Browser exclusivity of that file, each on its own browser family, and only when the capture
   database shows one company name in every site language (`policy.demo_company` absent or equal
   per language): the company name is one value of the shared database, so otherwise one group at a
   time. A fix round goes to the same writer with `SendMessage`.
5. **Gates** (`references/gates-and-landing.md` § Gates). Fix and re-run until clean, at most 3
   rounds; then `BLOCKED` with the findings left. An `UNVERIFIED` item is reported, never hidden.
6. **Browser acceptance** (`references/acceptance.md`). Serve the candidate build of every language
   with `build_compare.py serve` and launch `odoo-qa-tester` with `MODE: DOCS`, independent of the
   writer: it gets the served URLs, the page plan, the checklist and the banned terms of the
   policy, nothing else. On `FAIL`, resume the writer with the findings, rebuild, re-run step 5 for
   what changed, re-serve and re-run acceptance, until `PASS` or `BLOCKED` (`references/acceptance.md` § Loop).
7. **Land** (`references/gates-and-landing.md` § Land). Commit per the row's `commit` policy through
   `git-toolkit:git-ops`, push to `fork_remote` with a lease, open the PR against the series branch.
   `LAND: caller`: nothing here; the file list goes back in the return.
8. **CI** (`references/gates-and-landing.md` § CI; not under `LAND: caller`). Read the result;
   classify docs failure versus infrastructure failure and report which. A docs failure goes back
   to the writer (step 4); an infrastructure failure never changes the PR.
9. **Teardown**, on every exit path, a cancel included:
   - `build_compare.py stop --work-dir <D>`, then `build_compare.py clean --work-dir <D>` and
     `po_sync.py clean --work-dir <W>` for every work dir this run created.
   - Release every lease this run took (`odoo-instance` step E, or
     `mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with the token and `RUN_ID`) - never
     a forwarded `INSTANCE_HANDLE`.
   - After the PR body is written, remove `<RUN_DIR>`, `<ISOLATE_DIR>/visual/<RUN_ID>/` and the
     tester's evidence directory `<ISOLATE_DIR>/visual/qa/<SLUG>/docs/` only.
   - A given `WORKTREE` is the caller's: never remove it.
   - Keep the series worktree of a pushed branch. The run that sees its PR merged or closed
     removes it through `git-toolkit:git-ops`: `odoo-pr-monitoring` (the plan's merge node), or
     this skill when step 8 reads the PR as merged or closed. Remove the worktrees of a cancelled
     run the same way.

## Return

Per series: worktree, branch, PR URL (under `LAND: caller`: the file list instead), the page plan, pages added / updated / removed with their site URLs, the
gate and acceptance results with their `UNVERIFIED` items, the CI verdict, findings (code versus description,
branding gaps for the branding owner), what is left. Never an absolute warning count.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

OSM unreachable: the writer traces the module tree on disk and prefixes its report
`WARNING: OSM unreachable - facts from disk source`. No browser or no instance: the writer writes
the structure with `[Image: <slug>]` placeholders and returns `NEEDS_NEXT` -> `odoo-instance`; the
PR is not opened while a placeholder remains. No `git-ops`: stop `BLOCKED`, write nothing.

## Agent-managed tools

`odoo-doc-site-writer`; `odoo-qa-tester` (`MODE: DOCS`); `odoo-instance` and `odoo-doc-feature-map`
inline; `git-toolkit:git-ops`
for every git and GitHub operation.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = each
page, image and `.po` path plus the PR URLs; `status: DONE` with `concerns`.
