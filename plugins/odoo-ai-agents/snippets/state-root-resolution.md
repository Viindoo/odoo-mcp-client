<!-- SSOT snippet. The single source of truth for the namespaced ~/.odoo-ai/ state root:
     the two-axis Tier model, the exact subpath classification tables, and the
     MANDATORY resolve-capture-substitute prose protocol every skill/agent follows before it
     touches ANY project-scoped .odoo-ai/ path. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md. -->

# State-Root Resolution (`~/.odoo-ai/` two-axis convention)

All persistent agent state lives under one machine-global root, `$ODOO_AI_HOME` (default
`$HOME/.odoo-ai`) - never a project-relative `./.odoo-ai/` (an execute-agent has no guaranteed
working directory across dispatches, and a project-relative dir collides the moment two sessions
work the same repo from different cwd). Every artifact belongs to exactly ONE of three tiers.
Getting the tier wrong is not cosmetic: a Tier-1 path re-rooted onto a project dir silently forks
the machine's lease registry, and a Tier-2 path that should ISOLATE but gets SHARE'd breaks a hook
that assumes exactly one active thing per scope (see § The rule, case `run-<id>.json`).

## The three tiers

| Tier | Root | Scope | Resolver |
|---|---|---|---|
| **Tier-1 - flat** | `$ODOO_AI_HOME/` | machine-global; every project on this host shares it | none needed - use `$ODOO_AI_HOME` directly |
| **Tier-2 - SHARE** | `$ODOO_AI_HOME/projects/<repo-key>/` | one repo; every linked worktree SEES the same dir | `project_dir` axis `share` |
| **Tier-2 - ISOLATE** | `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/` | one worktree; concurrent worktrees do NOT see each other's copy | `project_dir` axis `isolate` |

Keys (both sha256, first 12 hex chars, computed by the resolver - never hand-derived):

```
repo-key = sha256(realpath(git rev-parse --git-common-dir))[:12]   # same for every linked worktree
wt-key   = sha256(realpath(git rev-parse --show-toplevel))[:12]    # distinct per worktree
```

Explicit overrides `$ODOO_AI_PROJECT_DIR` (SHARE) /
`$ODOO_AI_WORKTREE_DIR` (ISOLATE) win when set. Outside any git repo, the resolver walks UP from
the cwd to the nearest project marker: an explicit `.odoo-ai-root` sentinel has GLOBAL priority
(scanned up to `/` first); only when none exists does it fall back to the NEAREST
`__manifest__.py` dir (a bare "nearest marker of either kind" would mis-root from inside a module,
since real Odoo layouts nest `__manifest__.py` under EVERY module dir). If NEITHER marker is
found, the resolver REFUSES rather than hashing the cwd-unstable working directory.

**Tier-1 is NEVER namespaced.** The lease registry MUST stay machine-global flat - namespacing it
under a project/worktree dir would let two sessions in different worktrees allocate the same port
or database, exactly the collision Tier-1 exists to prevent.

## Tier-1 allowlist (flat under `$ODOO_AI_HOME`, MUST NEVER map to a project/worktree dir)

This is the codemod's FIRST check, before any SHARE/ISOLATE rule below - a subpath on this list
stays flat under `$ODOO_AI_HOME` regardless of what project or worktree the agent is in:

| Subpath | Why |
|---|---|
| `instances.toml` | the instance catalog; read only via `catalog_read` / `catalog_locate` |
| `runtime/` (`leases.json`, `registry.lock`) | the lease registry - namespacing it lets two worktrees allocate the same port/DB |
| `logs/` | host-level operational logs |
| `conf/` | generated per-instance `odoo.conf` for a listening server; keyed `<db>-<port>`, host-level for the same reason `runtime/` is |
| `i18n.json` | cross-project translation glossary (distinct from the per-project `i18n/<slug>-<date>/` ISOLATE tree below) |
| `.gitignore` | the defensive `*` gitignore at `$ODOO_AI_HOME` root (setup step `40-instance-profile.sh`) |

`venvs/` and `tools/pylint-<series>/` are Tier-1 today (`45-venv.sh`) but explicitly **not**
reclassified by this convention - a future reclass must key by a requirements-hash (not bare
series+profile) to avoid cross-project contamination. Treat them as Tier-1 until then.

## Tier-2 SHARE list (`<repo-key>/`, converges across a repo's worktrees)

This table enumerates every `.odoo-ai/`-rooted SHARE subpath used in this repo's prose today.
Because most consumers reference these paths through the `<SHARE_DIR>`/`<ISOLATE_DIR>` placeholder
(never a literal `.odoo-ai/...` string), no single grep can mechanically re-verify this table's
completeness - a NEW subpath is a maintainer responsibility to add here (§ The rule below), not a
lint finding.

| Subpath | Why |
|---|---|
| `coordination/` (`coordination/modules/`) | the module-coordination ledger's whole purpose is cross-worktree visibility |
| `designs/`, `plans/`, `gap-analysis/` | reusable design/plan cache across worktrees |
| `documentation/<slug>/<module>/`, `documentation/<slug>-<date>/` | doc-planner dedup wants repo-wide visibility |
| `survey/<slug>-<date>/` | deep-survey findings later phases cite - reusable knowledge |
| `brl/<job-id>/` (+ `chunkplan.json`, `input.jsonl`, `manifest.json`) | job-id-keyed deliverable cache |
| `visual/baselines/`, `visual/doc/` | reusable cross-run visual-regression baselines / doc-illustration cache |
| `brand-tokens.json` | consumer-DECLARED brand token map - one project-wide value every worktree sees identically |
| `mockups/` | consumer-DECLARED mockups - never agent-written, no run owns it |
| `glossary.yml` | human-curated glossary, consulted by EVERY i18n run - distinct from `i18n.json` Tier-1 |
| `cost-config.json` | project-level override for `odoo-brl` - per-PROJECT, not per-job |

## Tier-2 ISOLATE list (`<repo-key>/worktrees/<wt-key>/`, distinct per worktree)

Also EXHAUSTIVE. Two groups: explicit non-workflow subpaths, then the 13 workflow `output_dir`
trees named individually (never "...").

| Subpath | Why |
|---|---|
| `run-<id>.json` | the continuation hook needs exactly ONE active run per scope - two worktrees sharing this dir break the "one active thing" invariant |
| `worklog/<run-or-slug>/` | per-run execution log; parallel runs must not interleave |
| `integration/<slug>/` | run-harness's integration log, per active run |
| `brainstorm/state.json` | per-run/session active state |
| `git-rebase/<slug>/` | branch-slug rebase working state; one-worktree-one-branch |
| `forward-port/<slug>/` | branch/run-scoped, same reasoning as `git-rebase/` |
| `modules-upgrade/<slug>/` (incl. `modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`) | branch/run-scoped, same reasoning as `git-rebase/` |
| `pr-monitoring/` | active-session state (run-scoped) |
| `coding/<slug>-<date>/` (`plan.md`) | per-coding-run state a resume step reads - run-scoped, NOT the reusable `plans/` cache |
| `recon/<slug>-<date>/` (`findings.md`) | one run's scouting findings - run-scoped; contract: `scouting-persistence-contract.md` |
| `reviews/<slug>-<date>/` | tied to one diff/branch/PR - not cross-worktree reusable |
| `followups/<slug>.md` | terminal per-deal deliverable, no downstream reader |
| `visual/<run_id>/<module>_staging/` | run-scoped transient staging (on-disk form is module-prefixed `_staging`) |
| `visual/screenshots/<slug>/` | UI-review evidence for ONE review run (P9) - transient; owned by `odoo-ui-reviewer` |
| `visual/current/<slug>/` | state-B comparison set for ONE visual-regression run - transient, per-run suffix; owned by `odoo-visual-regression`, deleted before any terminal status, 24h-TTL swept |
| `visual/qa/<slug>/<module>/` | acceptance evidence, per-module (parallel browser families); cited by each PASS/FAIL/UNVERIFIED verdict; owned by `odoo-qa-tester` |
| `visual/debug/<slug>/` | symptom evidence for ONE debug/upgrade-P5 diagnosis, cited by the Output Contract's Observation field; owned by `odoo-ui-debugger` |
| `visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` | terminal demo-recording deliverable - a FILENAME with the same collision-proof suffix mechanism as the sibling `visual/*/<slug>/` dirs |
| `visual/adhoc/<slug>/` | a capture no skill owns (`<slug>` per `visual-evidence-lifecycle-contract.md` Clause 1); 30-day retention |
| `i18n/<slug>-<date>/` (`glossary-tm-<lang>.json`, `<module>.pot`, `translation-report-<lang>.json`, `consistency-audit-<lang>.md`) | i18n MANDATES a fresh `.pot`/TM re-export every invocation, forbidding artifact reuse - ephemeral, not reusable (contrast `glossary.yml` above) |

Plus the 13 workflow `output_dir` trees, each ISOLATE for the same reason (a per-run deliverable +
optional `<slug>-state.json` resume state that two concurrent runs must never clobber) - verified
exactly 13, one per `output_dir:` line across `workflows/*.workflow.yaml`: `bids/`
(`odoo-respond-bid.workflow.yaml`), `content/` (`content-production.workflow.yaml`), `debug/`
(`ui-debug-session.workflow.yaml`), `discovery/` (`discovery-pipeline.workflow.yaml`),
`implement/` (`odoo-implement-feature.workflow.yaml`), `packaging/`
(`module-packaging.workflow.yaml`), `positioning/` (`odoo-position-feature.workflow.yaml`), `qa/`
(`qa-suite.workflow.yaml`), `research/` (`research-multiphase.workflow.yaml`), `sales/`
(`sales-closing-cycle.workflow.yaml`), `support/` (`support-triage.workflow.yaml`),
`upgrade-plans/` (`odoo-plan-upgrade.workflow.yaml`), `video/` (`video-produce.workflow.yaml`).

**Note the split inside `visual/`:** `visual/baselines/` and `visual/doc/` are SHARE (reusable
cross-run assets), while `visual/<run_id>/<module>_staging/`, `visual/screenshots/<slug>/`,
`visual/current/<slug>/`, `visual/qa/<slug>/<module>/`, `visual/debug/<slug>/`, `visual/adhoc/<slug>/` and
`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` are ISOLATE (transient or terminal,
run-scoped). FOUR sibling evidence subpaths, four owners, no shared directory: `visual/screenshots/<slug>/`
(`odoo-ui-reviewer`), `visual/current/<slug>/` (`odoo-visual-regression`),
`visual/qa/<slug>/<module>/` (`odoo-qa-tester`), `visual/debug/<slug>/` (`odoo-ui-debugger`).
The demo-recording video is a FILENAME (owned by odoo-demo-recording, same collision-proof
mechanism) and `visual/adhoc/<slug>/` has no owner, so neither counts among the FOUR. Classify by
the FULL subpath, never by the top-level directory name alone - `visual/` itself is not a Tier.

## Codemod guards

- **Workflow YAML `output_dir:` lines stay UNCHANGED** - relative `.odoo-ai/<name>` literals
  `workflow-chaining` resolves against the runtime-resolved ISOLATE dir at execution time. Only
  PROSE mentions of those 13 names in skill/agent/command Markdown get rewritten to the
  resolve-capture-substitute protocol.
- Several ISOLATE names are BOTH an explicit row above and a workflow `output_dir` (`qa/`, `debug/`,
  `support/`) - consistent, no conflict; both point at the same ISOLATE tree.
- `brl/` is SHARE and is NOT one of the 13 workflow `output_dir`s - no collision.
- The Tier-1 allowlist (top of this doc) is a hard override: a Tier-1 subpath is NEVER rewritten
  to a SHARE/ISOLATE literal even inside an otherwise Tier-2-only skill/agent - it stays exactly
  `$ODOO_AI_HOME/<subpath>`.

## Advisory-glob exception (read-only, never-block hooks)

The general rule above (never a project-relative `./.odoo-ai/`) has exactly ONE sanctioned
exception, and it is narrow: `hooks/parse-continuation.sh`, `hooks/drive-continuation.sh`, and
`hooks/remind-delegate.sh` each resolve `RUN_DIR` via the shared `hooks/run-ownership.sh`
(`resolve_project_dir.sh isolate`) and, only on the resolver's own documented REFUSAL case,
fall back to legacy `<project>/.odoo-ai` before globbing `run-*.json`. Tolerated for these three
call sites and no others, because all three hold simultaneously: (1) **read-only glob, never a
write** - `run-<id>.json` is written ONLY by `run-harness` (§8.3), which always resolves through
the real two-axis root, so a degraded glob at the wrong location cannot corrupt or fork the lease
registry; (2) **fail-closed** - only existing record files count, so a wrong-location
fallback matches no files - the hook emits NO nudge, never a false one; (3) **hard
resilience contract** -
all three hooks are documented NEVER to hard-fail or block a tool call / turn-end / subagent-stop
on ANY error, and re-deriving a real two-axis key is not possible in the refusal case anyway (the
key inputs are exactly what the resolver could not get).

No other skill, agent, or hook may adopt this pattern - every other Tier-2 consumer follows the
resolve-capture-substitute protocol below with no silent fallback, because those call sites WRITE
state (a wrong-location write is the actual anti-pattern this doc exists to prevent).

## The rule (how to place a NEW subpath)

When you introduce a new `.odoo-ai/`-rooted artifact, ask ONE question and place it accordingly -
never guess, never default to SHARE "to be safe" (a wrongly-shared run-state file silently breaks
a continuation hook the same way `run-<id>.json` would):

> Is this RUN/SESSION-scoped active state that a hook or resume-logic treats as "the one active
> thing", or that two concurrent runs would interleave on if they wrote it at the same time?
> -> **ISOLATE.**
>
> Is this a reusable CACHE/KNOWLEDGE artifact whose value IS cross-run/worktree visibility (another
> worktree, or a later run in the same worktree, should see it)?
> -> **SHARE.**

If genuinely unsure, treat it as ISOLATE by default (safer: two copies, not a silent overwrite) and
flag it for a maintainer to add to the tables above.

## Where a captured artifact goes

Every capture call (screenshot, DOM or heap snapshot, trace, Lighthouse report, video/GIF) names an
ABSOLUTE path under the resolved `<ISOLATE_DIR>` or `<SHARE_DIR>` - never a relative path, never a
path inside the target repo or any working tree, never no destination. Pick the root by bucket:

1. **Reusable across runs** (visual-regression BASELINES, the cached login `storageState`, the
   doc-illustration screenshot cache) -> `<SHARE_DIR>/visual/...` per `## Tier-2 SHARE list` above.
2. **Run-scoped** (a visual-regression run's state-B comparison set, acceptance, debug and UI-review
   evidence, demo-video output, doc staging) -> `<ISOLATE_DIR>/...` per `## Tier-2 ISOLATE list`
   above. The default when in doubt; a capture no skill owns goes to `<ISOLATE_DIR>/visual/adhoc/<slug>/`.
3. **A committed module deliverable** (`<module>/static/description/...`, `<module>/doc/...`) is
   NEVER a capture destination. An image the module ships is `mv`d from ISOLATE into the location the
   target doc resolves (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/capture-mechanics.md`
   § Place finals where the target doc resolves them), then committed via `git-toolkit:git-ops`.

Bucket 3 keeps the committed-deliverable pipeline intact: the doc writers reach a module tree
only by that explicit `mv`.

**Per family.** chrome-devtools: `filePath` (`take_screenshot`, `take_snapshot`,
`take_heapsnapshot`, `performance_stop_trace`; never `path` - unknown keys are silently ignored, and
omitting `filePath` attaches the output inline) or `outputDirPath` (`lighthouse_audit`).
playwright: `filename` = the absolute path (`browser_take_screenshot`, `browser_start_video`). A
trace (`browser_stop_tracing`) or a pagecast `.webm` (`stop_recording`) has no destination: `mv` the
path it returns into `<ISOLATE_DIR>` immediately. Console/network listings return inline - Write
what you keep under `<ISOLATE_DIR>` so the report cites a real path.

**Refused path.** Never retry with a relative path.
- A HOOK deny: re-issue the call ONCE with an absolute path under the directory it names (or
  omit `filePath`, or stop, as it says); denied again -> stop `BLOCKED` quoting the deny. Keep the
  file where it was written and cite that path; only bucket 3 moves a file.
- A SERVER refusal ("Access denied", "outside allowed roots") of an absolute path under your
  `<ISOLATE_DIR>`/`<SHARE_DIR>`: stop `BLOCKED(browser MCP flags outdated)`, remedy "run
  /odoo-ai-agents:odoo-setup browser, then restart the session".

**Resolver REFUSAL (state root unresolvable), fail-closed:**
- **chrome-devtools**: omit `filePath` entirely - attaches to the response, nothing written - and
  write the literal `inline (state root unresolvable)` into the report's evidence field.
- **playwright / pagecast**: emit `BLOCKED(state root unresolvable - cannot place evidence)`. Do
  NOT capture - both write a file by default.

A scenario is not downgraded to UNVERIFIED for this reason alone when the observation was made.

## The resolve-capture-substitute protocol (MANDATORY - read this before touching any Tier-2 path)

Agents resolve with the `project_dir` tool; hooks and scripts, which cannot call a tool, run
`scripts/lib/resolve_project_dir.sh share|isolate` (the same resolver). `Read`/`Write`/`Edit`
take a **literal absolute path string** and run no shell, so `$ODOO_AI_PROJECT_DIR` never expands
or persists inside one (step 3 names the exact ban). Every skill/agent touching a Tier-2 subpath
follows this THREE-STEP protocol:

1. **Resolve ONCE and CAPTURE the returned absolute path(s).** Call `project_dir` with the axis
   the artifact's row names (`share` / `isolate`) and `cwd` = your working tree. It returns one
   absolute path (creating the dir if absent) or `PROJECT_DIR_UNRESOLVED` (the refusal case).
   Hold that path as a plain string for the rest of this turn/step.
2. **Substitute that captured ABSOLUTE STRING, literally, into every subsequent
   Read/Write/Edit/Bash path for this artifact.** No variable, no re-resolution, no shell involved.
3. **NEVER put `$ODOO_AI_PROJECT_DIR/...`, `$ODOO_AI_WORKTREE_DIR/...`, or a bare
   `.odoo-ai/...` literal into a Read/Write/Edit call.** It will not expand and will not persist.
   (A `Bash` call MAY reference the env var within that SAME `bash -c` invocation, but never
   across a Read/Write/Edit boundary.)

### Worked example

`project_dir` (axis `share`) returns `/home/user/.odoo-ai/projects/ab12cd34ef56`; substitute that
literal into every later call (`Read /home/user/.odoo-ai/projects/ab12cd34ef56/glossary.yml`) -
never `Read $ODOO_AI_PROJECT_DIR/glossary.yml` (does not expand) or `Read .odoo-ai/glossary.yml`
(cwd-relative, wrong root). If you need BOTH the SHARE and ISOLATE dirs in the same step, resolve
both up front and capture both paths.

### Placeholder notation used in skill/agent prose

`<SHARE_DIR>` and `<ISOLATE_DIR>` are PLACEHOLDERS standing for the absolute path captured from the
resolver in step 1; `$ODOO_AI_HOME` denotes the Tier-1 flat root and may be used directly. Resolve
+ capture, then substitute the captured absolute string in place of the placeholder - NEVER write
the literal angle-bracket token into a Read/Write/Edit call.

## Cross-worktree dispatch (when a pipeline targets a root other than the dispatcher's own cwd)

Some pipelines operate on a TARGET worktree/repo different from the dispatching skill/agent's own
inherited cwd. `<SHARE_DIR>` is cwd-independent within one repo so this never applies to it;
`<ISOLATE_DIR>` is NOT (diverges via `--show-toplevel`) - a leaf that resolves it from its OWN cwd
instead of the pipeline's target root lands its artifact in the WRONG worktree's directory,
orphaned from every sibling leaf in the run.

**The rule:** when your dispatch brief names an external logical root distinct from your own
inherited cwd (`review_root`, `doc_root`, an integration worktree path, or any field the brief
calls "the target"), the DISPATCHER resolves `<SHARE_DIR>`/`<ISOLATE_DIR>` ONCE with `project_dir`'s `cwd` set to
THAT root, and passes the CAPTURED
ABSOLUTE strings to EVERY leaf it dispatches (`SHARE_DIR: <abs-path>` / `ISOLATE_DIR: <abs-path>`).
A leaf receiving these fields MUST substitute them directly and MUST NOT re-run the resolver from
its own cwd - re-resolving independently is exactly what causes the divergence this rule exists to
prevent. A leaf invoked WITHOUT these fields falls back to the normal protocol, resolving from its
own cwd. Canonical worked example: `odoo-review-scoper` (`review_root`) and the
`odoo-code-review` skill's Phase 0.
