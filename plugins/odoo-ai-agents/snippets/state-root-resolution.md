<!-- SSOT snippet. The single source of truth for the namespaced ~/.odoo-ai/ state root:
     the two-axis Tier model, the exact subpath classification tables, and the
     MANDATORY resolve-capture-substitute prose protocol every skill/agent follows before it
     touches ANY project-scoped .odoo-ai/ path. Referenced (not copy-pasted) by
     project-facts-resolution.md (Round 0) and every skill/agent/workflow that reads or writes a
     Tier-2 subpath. Edit here only; consumers point at
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
| **Tier-2 - SHARE** | `$ODOO_AI_HOME/projects/<repo-key>/` | one repo; every linked worktree SEES the same dir | `scripts/lib/resolve_project_dir.sh share` |
| **Tier-2 - ISOLATE** | `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/` | one worktree; concurrent worktrees do NOT see each other's copy | `scripts/lib/resolve_project_dir.sh isolate` |

Keys (both sha256, first 12 hex chars, computed by the resolver - never hand-derived):

```
repo-key = sha256(realpath(git rev-parse --git-common-dir))[:12]   # same for every linked worktree
wt-key   = sha256(realpath(git rev-parse --show-toplevel))[:12]    # distinct per worktree
```

`--git-common-dir` always resolves to the ONE shared `.git` dir regardless of which linked
worktree you are in, so the SHARE key converges; `--show-toplevel` diverges per worktree, so the
ISOLATE key diverges too. Explicit overrides `$ODOO_AI_PROJECT_DIR` (SHARE) /
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
| `instances.toml` | the instance catalog; resolved via `scripts/lib/resolve_instances.sh` |
| `runtime/` (`leases.json`, `registry.lock`) | the lease registry - namespacing it lets two worktrees allocate the same port/DB |
| `logs/` | host-level operational logs |
| `i18n.json` | cross-project translation glossary (distinct from the per-project `i18n/<slug>-<date>/` ISOLATE tree below) |
| `.gitignore` | the defensive `*` gitignore at `$ODOO_AI_HOME` root (setup step `40-instance-profile.sh`) |

`venvs/` and `tools/pylint-<series>/` are Tier-1 today (`45-venv.sh`) but explicitly **not**
reclassified by this convention - a future reclass must key by a requirements-hash (not bare
series+profile) to avoid cross-project contamination. Treat them as Tier-1 until then.

## Tier-2 SHARE list (`<repo-key>/`, converges across a repo's worktrees)

This table enumerates every `.odoo-ai/`-rooted SHARE subpath used in this repo's prose today. A
codemod agent needs zero judgment on any of these - every row already carries its rationale. Note:
because most consumers reference these paths through the `<SHARE_DIR>`/`<ISOLATE_DIR>` placeholder
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
| `wave/<slug>/` | run-harness's between-wave log, per active run |
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
`visual/current/<slug>/`, `visual/qa/<slug>/<module>/`, `visual/debug/<slug>/`, and
`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` are ISOLATE (transient or terminal,
run-scoped). FOUR sibling evidence subpaths, four owners, no shared directory: `visual/screenshots/<slug>/`
(`odoo-ui-reviewer`), `visual/current/<slug>/` (`odoo-visual-regression`),
`visual/qa/<slug>/<module>/` (`odoo-qa-tester`), `visual/debug/<slug>/` (`odoo-ui-debugger`).
A fifth sibling evidence path lives in the same `visual/` root - the demo-recording video filename
`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}`, owned by odoo-demo-recording and
collision-proofed by the identical mechanism as the four above - a FILENAME rather than a
`<slug>/` directory, so it sits outside this note's FOUR-directory count while following the same
rule. Classify by the FULL subpath, never by the top-level directory name alone - `visual/` itself
is not a Tier.

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
`hooks/remind-delegate.sh` each resolve `RUN_DIR` via `resolve_project_dir.sh isolate` and, only
when that resolution itself fails (the resolver's own documented REFUSAL case), fall back to
`RUN_DIR="${PROJ_DIR}/.odoo-ai"` before globbing `run-*.json`. Tolerated for these three call
sites and no others, because all three hold simultaneously: (1) **read-only glob, never a
write** - `run-<id>.json` is written ONLY by `run-harness` (§8.3), which always resolves through
the real two-axis root, so a degraded glob at the wrong location cannot corrupt or fork the lease
registry; (2) **fail-closed** - `shopt -s nullglob` makes a wrong-location fallback match zero
files, so the hook silently emits NO nudge, never a false one; (3) **hard resilience contract** -
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

## Where a captured artifact goes (three buckets, keyed on the capture call)

A capture call (screenshot, DOM snapshot, heap snapshot, performance trace, console/network log,
video/GIF recording) NEVER writes into the target repo's working tree and NEVER runs with no
destination. Classify the DESTINATION OF THE CAPTURE CALL - not the artifact, and not where it ends
up later - into exactly one bucket:

1. **Reusable across runs** (visual-regression BASELINES, the cached login `storageState`, the
   doc-illustration screenshot cache) -> `<SHARE_DIR>/visual/...` per `## Tier-2 SHARE list` above.
2. **Run-scoped** (a visual-regression run's state-B comparison set, acceptance evidence, debug
   symptom evidence, UI-review evidence, demo-video output, staging LATER copied into a module
   tree) -> `<ISOLATE_DIR>/...` per `## Tier-2 ISOLATE list` above. The default when in doubt.
3. **A committed module deliverable** (`<module>/static/description/...`, `<module>/doc/...`) is
   NEVER a capture destination - reached only by an explicit Bash `cp`/`mv` of one named file out
   of bucket (1) or (2), then committed via `git-toolkit:git-ops`.

Bucket 3 keeps the committed-deliverable pipeline intact: `odoo-icon-designer.md`, `odoo-marketing-writer.md`,
`odoo-user-doc-writer.md` each reach it only by an explicit copy step - never a direct capture target.

**Family mechanics.** chrome-devtools (eager default): pass the absolute path as **`filePath`**
(never `path` - unknown keys are silently ignored); omitting it attaches the image inline instead
of writing a file. playwright (opt-in): absolute paths REJECTED - capture with a RELATIVE
`filename`, then Bash `cp`/`mv` the returned path into the tier dir; never omit `filename`
(defaults to `page-<timestamp>.png`). pagecast (opt-in): no destination parameter - record,
`stop_recording`, `cp`/`mv` the returned `.webm` path. `list_console_messages`/
`list_network_requests` return data inline - Write it verbatim to a file under the ISOLATE
evidence dir yourself so the report cites a real path.

**The refusal fallback (family-conditional, fail-closed).** On resolver REFUSAL:
- **chrome-devtools**: omit `filePath` entirely - attaches to the response, nothing written - and
  write the literal `inline (state root unresolvable)` into the report's evidence field.
- **playwright / pagecast**: emit `BLOCKED(state root unresolvable - cannot place evidence)`. Do
  NOT capture. Both families write by default and neither can be told where; scattering files is
  the defect this rule exists to prevent. A brief naming an opt-in family in a marker-less cwd is
  a misconfiguration worth blocking on.

A scenario is not downgraded to UNVERIFIED for this reason alone when the observation was made.

## The resolve-capture-substitute protocol (MANDATORY - read this before touching any Tier-2 path)

The resolver above is shell + Python, but most consumers are **prose** - an agent using
`Read`/`Write`/`Edit`, not `Bash`. Those tools take a **literal absolute path string** and run no
shell, so `$ODOO_AI_PROJECT_DIR` inside one neither expands nor persists across calls. Putting a
`$VAR` or a bare `.odoo-ai/...` literal into a Read/Write/Edit call is therefore always a bug.
Every skill/agent touching a Tier-2 subpath follows this THREE-STEP protocol:

1. **Resolve ONCE, via Bash, and CAPTURE the printed absolute path(s).** Run one or both, as
   needed:
   ```
   bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share
   bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh isolate
   ```
   Each prints exactly one absolute path on stdout (and creates the dir if it did not exist yet).
   Hold that output as a plain string for the rest of this turn/step.
2. **Substitute that captured ABSOLUTE STRING, literally, into every subsequent
   Read/Write/Edit/Bash path for this artifact.** No variable, no re-resolution, no shell involved.
3. **NEVER put `$ODOO_AI_PROJECT_DIR/...`, `$ODOO_AI_WORKTREE_DIR/...`, or a bare
   `.odoo-ai/...` literal into a Read/Write/Edit call.** It will not expand and will not persist.
   (A `Bash` call MAY reference the env var within that SAME `bash -c` invocation, but never
   across a Read/Write/Edit boundary.)

### Worked example

`bash resolve_project_dir.sh share` prints `/home/user/.odoo-ai/projects/ab12cd34ef56`; substitute
that literal into every later call (`Read /home/user/.odoo-ai/projects/ab12cd34ef56/glossary.yml`) -
never `Read $ODOO_AI_PROJECT_DIR/glossary.yml` (does not expand) or `Read .odoo-ai/glossary.yml`
(cwd-relative, wrong root). If you need BOTH the SHARE and ISOLATE dirs in the same step, resolve
both up front in one Bash call and capture both printed lines.

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
calls "the target"), the DISPATCHER resolves `<SHARE_DIR>`/`<ISOLATE_DIR>` ONCE with cwd set to
THAT root (`resolve_project_dir.sh --root <target-root> share|isolate`), and passes the CAPTURED
ABSOLUTE strings to EVERY leaf it dispatches (`SHARE_DIR: <abs-path>` / `ISOLATE_DIR: <abs-path>`).
A leaf receiving these fields MUST substitute them directly and MUST NOT re-run the resolver from
its own cwd - re-resolving independently is exactly what causes the divergence this rule exists to
prevent. A leaf invoked WITHOUT these fields falls back to the normal protocol, resolving from its
own cwd. Canonical worked example: `agents/odoo-review-scoper.md` (`review_root`) and the
`odoo-code-review` skill's Phase 0.
