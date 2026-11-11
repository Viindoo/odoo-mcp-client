# State-root resolution (`$ODOO_AI_HOME`)

All persistent agent state lives under one machine-global root, `$ODOO_AI_HOME` (default
`$HOME/.odoo-ai`), never a project-relative `./.odoo-ai/`. Every artifact belongs to one tier.

## The tiers

| Tier | Root | Scope | Resolver |
|---|---|---|---|
| **Tier-1 - flat** | `$ODOO_AI_HOME/` | every project on this host | none - use `$ODOO_AI_HOME` directly |
| **Tier-2 - SHARE** | `$ODOO_AI_HOME/projects/<repo-key>/` | one repo; every linked worktree sees the same dir | `project_dir` axis `share` |
| **Tier-2 - ISOLATE** | `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/` | one worktree | `project_dir` axis `isolate` |
| **Tier-2 - WORKTREE** | `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<name>/src` | where an agent-created worktree is checked out; its ISOLATE dir is the parent of `src` | `project_dir` axis `worktree` + `name` |

The resolver computes the keys; never derive them by hand. Every worktree an agent creates lives
at the WORKTREE path: resolve it (`name` = the branch slug, `[A-Za-z0-9][A-Za-z0-9._-]{0,79}`) and
pass the returned path as the `worktree` of the `git-toolkit:git-ops` request - never a sibling
of the repo, a temp dir or a path the git worker picks.

`$ODOO_AI_PROJECT_DIR` (SHARE) and `$ODOO_AI_WORKTREE_DIR` (ISOLATE) override the resolver when
set. Outside a git repo the resolver walks up from the cwd to an `.odoo-ai-root` sentinel, else to
the nearest `__manifest__.py` directory, else it refuses.

## Tier-1 (flat, never namespaced)

`instances.toml` (the instance catalog, read only through `catalog_read` / `catalog_locate`),
`runtime/` (the lease registry), `logs/`, `conf/` (generated per-instance `odoo.conf`),
`i18n.json` (the cross-project translation glossary), `venvs/`, `tools/pylint-<series>/`,
`.gitignore`.

## Tier-2 SHARE list

Reusable across the worktrees and runs of a repo:

| Subpath | Holds |
|---|---|
| `coordination/modules/` | the module-coordination ledger |
| `designs/`, `plans/`, `gap-analysis/` | designs, plans, gap matrices |
| `documentation/<slug>/<module>/`, `documentation/<slug>-<date>/` | the documentation cache |
| `survey/<slug>-<date>/` | deep-survey findings |
| `brl/<job-id>/` | requirement-list job artifacts |
| `visual/baselines/`, `visual/doc/` | visual-regression baselines, the doc-illustration screenshot cache |
| `brand-tokens.json`, `mockups/`, `glossary.yml`, `cost-config.json` | project-declared inputs: brand tokens, mockups, the curated glossary, the cost override of `odoo-brl` |

## Tier-2 ISOLATE list

State of one run or one worktree:

| Subpath | Holds |
|---|---|
| `run-<id>.json` | the active run |
| `worklog/<run-or-slug>/`, `integration/<slug>/` | the run's worklog and integration log |
| `brainstorm/state.json`, `pr-monitoring/` | session state |
| `git-rebase/<slug>/`, `forward-port/<slug>/`, `modules-upgrade/<slug>/` | the working state of a rebase, a port, an upgrade |
| `coding/<slug>-<date>/`, `recon/<slug>-<date>/`, `reviews/<slug>-<date>/` | a coding run's plan and impact map, scouting findings, review reports |
| `followups/<slug>.md` | a deal follow-up |
| `i18n/<slug>-<date>/` | one translation run's export, memory and reports |
| `visual/<run_id>/<module>_staging/` | doc capture staging |
| `visual/screenshots/<slug>/` | UI-review evidence (`odoo-ui-reviewer`) |
| `visual/current/<slug>/` | the comparison set of one visual-regression run |
| `visual/qa/<slug>/<module>/` | acceptance evidence (`odoo-qa-tester`) |
| `visual/debug/<slug>/` | diagnosis evidence (`odoo-ui-debugger`) |
| `visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` | a demo recording |
| `visual/adhoc/<slug>/` | a capture no skill owns; kept 30 days |
| a workflow's `output_dir` (`bids/`, `content/`, `debug/`, `discovery/`, `implement/`, `packaging/`, `positioning/`, `qa/`, `research/`, `sales/`, `support/`, `upgrade-plans/`, `video/`) | that workflow run's output |

Classify by the full subpath: under `visual/`, only `baselines/` and `doc/` are SHARE. A new
artifact that is the active state of a run, or that two concurrent runs would interleave on, is
ISOLATE; one whose value is being seen by other worktrees and later runs is SHARE; when unsure,
ISOLATE.

## The resolve-capture-substitute protocol

`Read`, `Write` and `Edit` take a literal absolute path, so every Tier-2 path is resolved first:

1. **Resolve once and capture.** Call `project_dir` with the axis of the artifact's row and `cwd`
   = your working tree. It returns one absolute path (creating the directory; for `worktree` only
   its parent) or `PROJECT_DIR_UNRESOLVED`. Need both SHARE and ISOLATE: resolve both up front.
2. **Substitute the captured string literally** into every later path of that artifact - no
   variable, no second resolution.
3. **Never put `$ODOO_AI_PROJECT_DIR/...`, `$ODOO_AI_WORKTREE_DIR/...`, a bare `.odoo-ai/...` or
   the placeholder itself into a Read, Write or Edit call.** `<SHARE_DIR>` and `<ISOLATE_DIR>` in
   this plugin's prose stand for the captured paths. A `Bash` call may use the environment
   variable inside its own invocation.

A hook or a script resolves with `scripts/lib/resolve_project_dir.sh share|isolate`.

## Cross-worktree dispatch

`<SHARE_DIR>` is the same from any worktree of a repo; `<ISOLATE_DIR>` is not. When a brief names
a root other than your own cwd (`review_root`, `doc_root`, an integration worktree, "the target"),
the dispatcher resolves both dirs once with `cwd` set to that root and passes the captured
absolute strings to every agent it launches (`SHARE_DIR:`, `ISOLATE_DIR:`). An agent that receives
them substitutes them and never resolves again from its own cwd; one that receives none follows
the protocol above from its own cwd.

## Where a captured artifact goes

Every capture (screenshot, DOM or heap snapshot, trace, Lighthouse report, video, GIF) names an
absolute path under the resolved `<ISOLATE_DIR>` or `<SHARE_DIR>` - never a relative path, a path
inside a repo or working tree, or no destination.

1. **Reusable across runs** (visual-regression baselines, the doc-illustration cache):
   `<SHARE_DIR>/visual/...`.
2. **Run-scoped** (everything else, and the default): `<ISOLATE_DIR>/...` per the ISOLATE list; a
   capture no skill owns goes to `<ISOLATE_DIR>/visual/adhoc/<slug>/`.
3. **A committed module deliverable** (`<module>/static/description/...`, `<module>/doc/...`) is
   never a capture destination: the image is moved from ISOLATE to where the target document
   resolves it (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` § Place finals
   where the target doc resolves them), then committed through `git-toolkit:git-ops`.

The session scratchpad is for throwaway output read in the same turn; anything a later step, agent
or session needs goes under the state root.

**Per browser family.** chrome-devtools: `filePath` (`take_screenshot`, `take_snapshot`,
`take_heapsnapshot`, `performance_stop_trace`) or `outputDirPath` (`lighthouse_audit`).
playwright: `filename` = the absolute path (`browser_take_screenshot`, `browser_start_video`). A
playwright trace (`browser_stop_tracing`) and a pagecast `.webm` (`stop_recording`) have no
destination parameter: move the path they return into `<ISOLATE_DIR>` at once. Console and network
listings come back inline: write what you keep under `<ISOLATE_DIR>` so the report cites a path.

**A refused path** is never retried with a relative one.
- A hook deny: re-issue the call once with an absolute path under the directory it names (or as
  it says); denied again, stop `BLOCKED` quoting the deny.
- A server refusal ("Access denied", "outside allowed roots") of an absolute path under your
  resolved dirs: stop `BLOCKED(browser MCP flags outdated)` with the remedy "run
  /odoo-ai-agents:odoo-setup browser, then restart the session".

**The state root cannot be resolved:** chrome-devtools captures without `filePath` (the image
attaches to the response) and the report's evidence field says `inline (state root unresolvable)`;
playwright and pagecast, which always write a file, do not capture and return
`BLOCKED(state root unresolvable - cannot place evidence)`. An observation that was made is not
downgraded to UNVERIFIED for this reason alone.
