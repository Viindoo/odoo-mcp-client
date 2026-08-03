<!-- SSOT snippet. The single source of truth for the namespaced ~/.odoo-ai/ state root
     (Problem 3): the two-axis Tier model, the exact subpath classification tables, and the
     MANDATORY resolve-capture-substitute prose protocol every skill/agent follows before it
     touches ANY project-scoped .odoo-ai/ path. Referenced (not copy-pasted) by
     context-bootstrap.md (Round 0) and, going forward, by every skill/agent/workflow that reads
     or writes a Tier-2 subpath. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md. -->

# State-Root Resolution (`~/.odoo-ai/` two-axis convention)

All persistent agent state lives under one machine-global root, `$ODOO_AI_HOME` (default
`$HOME/.odoo-ai`) - never a project-relative `./.odoo-ai/` (an execute-agent has no guaranteed
working directory across dispatches, and a project-relative dir collides the moment two Claude
Code sessions work the same repo from different cwd). Inside that root, every artifact belongs to
exactly ONE of three tiers. Getting the tier wrong is not cosmetic: a Tier-1 path re-rooted onto a
project dir silently forks the machine's lease registry, and a Tier-2 path that should ISOLATE but
gets SHARE'd breaks a hook that assumes exactly one active thing per scope (see § The rule, case
`run-<id>.json`).

## The three tiers

| Tier | Root | Scope | Resolver |
|---|---|---|---|
| **Tier-1 - flat** | `$ODOO_AI_HOME/` | machine-global; every project on this host shares it | none needed - use `$ODOO_AI_HOME` directly (or `scripts/lib/resolve_instances.sh` for `instances.toml` specifically) |
| **Tier-2 - SHARE** | `$ODOO_AI_HOME/projects/<repo-key>/` | one repo; every linked worktree of that repo SEES the same dir | `scripts/lib/resolve_project_dir.sh share` / `paths.py` `share_dir()` |
| **Tier-2 - ISOLATE** | `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/` | one worktree; concurrent worktrees of the same repo do NOT see each other's copy | `scripts/lib/resolve_project_dir.sh isolate` / `paths.py` `isolate_dir()` |

Keys (both sha256, first 12 hex chars, computed by the resolver - never hand-derived):

```
repo-key = sha256(realpath(git rev-parse --git-common-dir))[:12]   # same for every linked worktree
wt-key   = sha256(realpath(git rev-parse --show-toplevel))[:12]    # distinct per worktree
```

`--git-common-dir` always resolves to the ONE shared `.git` dir regardless of which linked
worktree you are in, so the SHARE key converges; `--show-toplevel` is the worktree's own checkout
root, so the ISOLATE key diverges. Explicit overrides `$ODOO_AI_PROJECT_DIR` (SHARE) /
`$ODOO_AI_WORKTREE_DIR` (ISOLATE) win when set, and are honored verbatim. Outside any git repo,
the resolver walks UP from the cwd to the nearest project marker and hashes that. Two marker
kinds, STRICT priority: an explicit `.odoo-ai-root` sentinel file has GLOBAL priority - the walk
scans the WHOLE chain up to `/` for it first; only when no sentinel exists ANYWHERE does it fall
back to the NEAREST dir containing `__manifest__.py`. This matters because real Odoo addons
layouts nest a `__manifest__.py` under EVERY module dir - "nearest marker of either kind" would
mis-root from inside a module (two modules of one project would fork into two different keys, and
a root sentinel meant to fix that would be defeated by the nearer manifest). If NEITHER marker is
found anywhere in the chain, the resolver REFUSES with a clear error rather than ever hashing the
bare, cwd-unstable working directory.

**Tier-1 is NEVER namespaced.** The lease registry (`runtime/leases.json` + `registry.lock`) is
the one artifact that MUST stay machine-global flat - namespacing it under a project/worktree dir
would let two sessions in different worktrees allocate the same port or database, which is exactly
the collision Tier-1 exists to prevent.

## Tier-1 allowlist (flat under `$ODOO_AI_HOME`, MUST NEVER map to a project/worktree dir)

This is the codemod's FIRST check, before any SHARE/ISOLATE rule below - a subpath on this list
stays flat under `$ODOO_AI_HOME` regardless of what project or worktree the agent is in:

| Subpath | Why |
|---|---|
| `instances.toml` | the instance catalog; resolved via `scripts/lib/resolve_instances.sh` |
| `runtime/` (`leases.json`, `registry.lock`) | the allocator's lease registry - namespacing it lets two worktrees allocate the same port/DB, exactly the collision Tier-1 exists to prevent |
| `logs/` | host-level operational logs |
| `i18n.json` | cross-project translation glossary/memory (distinct from the per-project `i18n/<slug>-<date>/` ISOLATE tree below) |
| `.gitignore` | the defensive `*` gitignore dropped at the `$ODOO_AI_HOME` root (written idempotently by setup step `40-instance-profile.sh`) |

`venvs/` and `tools/pylint-<series>/` are Tier-1 today (`45-venv.sh`) but are explicitly **not**
reclassified by this convention - a future reclass, if it happens, must key by a requirements-hash
(not bare series+profile) to avoid cross-project dependency contamination. Treat them as Tier-1
until a dedicated follow-up says otherwise.

## Tier-2 SHARE list (`<repo-key>/`, converges across a repo's worktrees)

This table is EXHAUSTIVE for every `.odoo-ai/`-rooted subpath found in this repo today (verified by
`grep -rhoE '\.odoo-ai/[A-Za-z0-9_.-]+' plugins/ docs/ workflows/`). A codemod agent needs zero
judgment on any of these - every row already carries its rationale.

| Subpath | Why |
|---|---|
| `context.md` | project identity (version/profile/modules) - identical across a repo's worktrees |
| `coordination/` (`coordination/modules/`) | the module-coordination ledger's entire purpose is cross-worktree visibility |
| `designs/`, `plans/`, `gap-analysis/` | reusable design/plan cache - authored in one worktree, reusable in another |
| `documentation/<slug>/<module>/`, `documentation/<slug>-<date>/` | the doc-planner dedups "already documented on disk" - wants repo-wide visibility (both the doc-planner run-root and the per-module feature-catalog/walkthrough naming are the same reusable cache) |
| `survey/<slug>-<date>/` | deep-survey findings that later phases cite - reusable knowledge |
| `brl/<job-id>/` (+ `chunkplan.json`, `input.jsonl`, `manifest.json`) | job-id-keyed deliverable cache (customer+date+hex) |
| `visual/baselines/`, `visual/doc/` | reusable cross-run visual-regression baselines / doc-illustration screenshot cache |
| `brand-tokens.json` | consumer-DECLARED (not agent-written) brand token map, referenced from `context.md` - same class as `context.md` itself: one project-wide value every worktree must see identically |
| `mockups/` | consumer-DECLARED reference mockups/design specs (`context.md`'s `mockup_dir`), consulted by the mockup-first fidelity check across any worktree doing frontend work - never agent-written, so no run ever "owns" or clobbers it |
| `glossary.yml` | project glossary of domain/regulatory terms - human/maintainer-curated (no agent writes it), consulted by EVERY i18n run (P1 TM build) and by coding guidelines; distinct from the cross-PROJECT `i18n.json` Tier-1 file above |
| `cost-config.json` | project-level day-rate-region / risk-profile OVERRIDE for `odoo-brl`'s shipped lookup table - "override-able at `.odoo-ai/`" per design, i.e. a per-PROJECT declared value every BRL job on this project should see the same way, not a per-job artifact |

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
| `modules-upgrade/<slug>/` (incl. `modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`) | branch/run-scoped upgrade working state, same reasoning as `git-rebase/` |
| `pr-monitoring/` | active-session state (run-scoped, even when it doesn't strictly collide) |
| `coding/<slug>-<date>/` (`plan.md`) | per-coding-run orchestration state a later review/fix/resume step reads to avoid recomputing the graph - run-scoped state, NOT the reusable `plans/` design cache |
| `recon/<slug>-<date>/` (`findings.md`) | a scouting pass's findings for ONE run: consumed by the SAME run's later phases and by a resume of that run, never by another worktree - run-scoped state, same class as `coding/<slug>-<date>/`; contract: `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` |
| `reviews/<slug>-<date>/` | a review is tied to one diff/branch/PR - not cross-worktree reusable (two worktrees reviewing different branches must never share this dir) |
| `followups/<slug>.md` | terminal per-deal deliverable, no downstream reader - one-off sales output, same class as `pr-monitoring/`/`support/` |
| `visual/<run_id>/<module>_staging/` | run-scoped transient staging (follows the run; note the actual on-disk form is module-prefixed `_staging`, not a bare `_staging/`) |
| `visual/screenshots/<slug>/` | UI-review evidence staged for ONE review run (P9) - transient, same reasoning as `visual/<run_id>/<module>_staging/`; owned by `odoo-ui-reviewer` |
| `visual/current/<slug>/` | the state-B comparison set for ONE visual-regression run (Round 3) - transient, superseded the moment the Round-4 verdict is recorded, and per-run by construction (`<slug>` carries a random suffix, same mechanism as `run-<id>.json`'s id, so two concurrent runs on the identical comparison intent never write the same screenshot path); owned by `odoo-visual-regression`, which deletes it before ANY terminal status (DONE/BLOCKED/NEEDS_CONTEXT alike), backstopped by a 24h-TTL orphan sweep the next run performs |
| `visual/qa/<slug>/<module>/` | acceptance evidence for ONE module of ONE acceptance run - `odoo-acceptance/SKILL.md:142` dispatches one `odoo-qa-tester` per High-tier module and `:135-140` allows distinct browser families to run in parallel, so the path is per-module, not per-run; RETAINED because it is the cited evidence behind each PASS/FAIL/UNVERIFIED verdict in `qa/<slug>-acceptance-report.md`; owned by `odoo-qa-tester` |
| `visual/debug/<slug>/` | symptom evidence for ONE `odoo-debug` (or `odoo-modules-upgrade` P5) diagnosis - RETAINED because the Output Contract's Observation field cites it; correlated to `debug/` notes and `worklog/<run-or-slug>/` by the same `<slug>`; owned by `odoo-ui-debugger` |
| `visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` | terminal demo-recording deliverable, no downstream reader in any other skill - run-scoped, same class as `followups/`; the filename carries the SAME collision-proof suffix mechanism as the four sibling `visual/*/<slug>/` directories below (SSOT + rationale: `visual-evidence-lifecycle-contract.md` Clause 1's fifth-consumer rule) - never a bare `<feature>-<timestamp>` |
| `i18n/<slug>-<date>/` (`glossary-tm-<lang>.json`, `<module>.pot`, `translation-report-<lang>.json`, `consistency-audit-<lang>.md`) | the i18n recipe MANDATES a fresh `.pot`/TM re-export on every invocation and forbids reusing a prior run's artifacts on disk - ephemeral per-run output tied to one worktree's current code state, not reusable knowledge (contrast with `glossary.yml` above, which IS meant to persist and be reused) |
| `bids/` | workflow `output_dir` (`odoo-respond-bid.workflow.yaml`) |
| `content/` | workflow `output_dir` (`content-production.workflow.yaml`) |
| `debug/` | workflow `output_dir` (`ui-debug-session.workflow.yaml`) |
| `discovery/` | workflow `output_dir` (`discovery-pipeline.workflow.yaml`) |
| `implement/` | workflow `output_dir` (`odoo-implement-feature.workflow.yaml`) |
| `packaging/` | workflow `output_dir` (`module-packaging.workflow.yaml`) |
| `positioning/` | workflow `output_dir` (`odoo-position-feature.workflow.yaml`) |
| `qa/` | workflow `output_dir` (`qa-suite.workflow.yaml`) |
| `research/` | workflow `output_dir` (`research-multiphase.workflow.yaml`) |
| `sales/` | workflow `output_dir` (`sales-closing-cycle.workflow.yaml`) |
| `support/` | workflow `output_dir` (`support-triage.workflow.yaml`) |
| `upgrade-plans/` | workflow `output_dir` (`odoo-plan-upgrade.workflow.yaml`) |
| `video/` | workflow `output_dir` (`video-produce.workflow.yaml`) |

All 13 rows above are per-run deliverables (+ a `<slug>-state.json` where the workflow persists
resume state) that two concurrent runs must never clobber - verified exactly 13, one per
`output_dir:` line across `workflows/*.workflow.yaml`.

**Note the split inside `visual/`:** `visual/baselines/` and `visual/doc/` are SHARE (reusable
cross-run assets), while `visual/<run_id>/<module>_staging/`, `visual/screenshots/<slug>/`,
`visual/current/<slug>/`, `visual/qa/<slug>/<module>/`, `visual/debug/<slug>/`, and
`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` are ISOLATE (transient or terminal,
run-scoped). FOUR sibling evidence subpaths, four owners, no shared directory: `visual/screenshots/<slug>/`
(`odoo-ui-reviewer`), `visual/current/<slug>/` (`odoo-visual-regression`),
`visual/qa/<slug>/<module>/` (`odoo-qa-tester`), `visual/debug/<slug>/` (`odoo-ui-debugger`).
A fifth sibling evidence path lives in the same `visual/` root - the demo-recording video filename
`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}`, owned by odoo-demo-recording and
collision-proofed by the identical Clause 1 mechanism as the four above - a FILENAME rather than a
`<slug>/` directory, so it sits outside this note's FOUR-directory count while following the same
rule. Classify by the FULL subpath, never by the top-level directory name alone - `visual/` itself
is not a Tier.

## Codemod guards

- **Workflow YAML `output_dir:` lines stay UNCHANGED.** They are relative `.odoo-ai/<name>` literals
  that `workflow-chaining` resolves against the runtime-resolved ISOLATE dir at execution time
  (design §3.5) - a codemod must NEVER rewrite the `output_dir:` value itself. Only PROSE mentions
  of those 13 names in skill/agent/command Markdown (outside workflow YAML) get rewritten to the
  resolve-capture-substitute protocol below.
- Several ISOLATE names are BOTH an explicit row above and a workflow `output_dir` (`qa/`, `debug/`,
  `support/`) - consistent, no conflict; both point at the same ISOLATE tree.
- `brl/` is SHARE and is NOT one of the 13 workflow `output_dir`s - no collision with the ISOLATE
  list above.
- The Tier-1 allowlist (top of this doc) is a hard override: even inside a skill/agent that
  otherwise deals only in Tier-2 paths, a Tier-1 subpath (`instances.toml`, `runtime/`, `logs/`,
  `i18n.json`) is NEVER rewritten to a SHARE/ISOLATE literal - it stays exactly `$ODOO_AI_HOME/<subpath>`.

## Advisory-glob exception (V-50 - read-only, never-block hooks)

The general rule above (never a project-relative `./.odoo-ai/`) has exactly ONE sanctioned
exception, and it is narrow: `hooks/parse-continuation.sh`, `hooks/drive-continuation.sh`, and
`hooks/remind-delegate.sh` each resolve `RUN_DIR` via `resolve_project_dir.sh isolate` and, only
when that resolution itself fails (script missing, `CLAUDE_PLUGIN_ROOT` unset, cwd outside any
git repo with no `.odoo-ai-root`/`__manifest__.py` marker anywhere in the chain - the resolver's
own documented REFUSAL case), fall back to `RUN_DIR="${PROJ_DIR}/.odoo-ai"` before globbing
`run-*.json`. This is INTENTIONALLY tolerated for these three call sites and no others, because
all three hold simultaneously:

1. **Read-only glob, never a write.** None of the three ever creates, writes, or deletes anything
   at the fallback path - `run-<id>.json` is written ONLY by `run-harness` (§8.3), which always
   resolves through the real two-axis root. A degraded glob at the wrong location cannot corrupt
   or fork the lease registry the way a Tier-1 mis-route (§ Tier-1 allowlist above) could.
2. **Fail-closed, not fail-open.** `shopt -s nullglob` makes a non-existent or wrong-location
   fallback dir match zero files, so the hook silently emits NO nudge - never a false one. The
   worst case is a missed advisory reminder, not an incorrect action.
3. **Hard resilience contract.** All three hooks are documented NEVER to hard-fail or block a
   tool call / turn-end / subagent-stop on ANY error (missing script, parse failure, no run
   file) - a resolver refusal is just one more input the hook must degrade through, not escalate.
   Re-deriving a real two-axis key here is not possible in the refusal case anyway (the key inputs
   - `git rev-parse --git-common-dir` / `--show-toplevel` - are exactly what the resolver could
   not get), so there is no strictly-better fallback root to substitute in.

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

If genuinely unsure, treat it as ISOLATE by default (the safer failure mode is two worktrees each
keeping their own copy, not two worktrees silently overwriting each other's run state) and flag it
for a maintainer to add to the tables above.

## Where a captured artifact goes (three buckets, keyed on the capture call)

A capture call (screenshot, DOM snapshot, heap snapshot, performance trace, console/network log,
video/GIF recording) NEVER writes into the target repo's working tree and NEVER runs with no
destination. Classify the DESTINATION OF THE CAPTURE CALL - not the artifact, and not where it ends
up later - into exactly one bucket:

1. **Reusable across runs** (visual-regression BASELINES, the cached login `storageState`, the
   doc-illustration screenshot cache) -> `<SHARE_DIR>/visual/...`
   per `## Tier-2 SHARE list` above.
2. **Run-scoped** (a visual-regression run's state-B comparison set, acceptance evidence, debug
   symptom evidence, UI-review evidence, demo-video output, and any staging that will LATER be copied
   into a module tree) -> `<ISOLATE_DIR>/...` per `## Tier-2 ISOLATE list` above. This is the default
   when in doubt.
3. **A committed module deliverable** (`<module>/static/description/...`, `<module>/doc/...`) is
   NEVER a capture destination. It is reached only by an explicit Bash `cp`/`mv` of one named file
   out of bucket (1) or (2), and committed via `git-toolkit:git-ops`.

Bucket 3 keeps the committed-deliverable pipeline intact: `odoo-icon-designer.md`
(`icon.png`), `odoo-marketing-writer.md` (`index.html`), `odoo-user-doc-writer.md` (`doc/index.rst`)
each reach it only by an explicit copy step - never as a direct capture target.

**Family mechanics.** **chrome-devtools** (the eager default): pass the absolute path as
**`filePath`** (`take_screenshot`, `take_snapshot`, `performance_start_trace`, `take_heapsnapshot`).
The schema accepts unknown keys silently, so a wrong key name writes NOTHING - the key is
`filePath`, never `path`. Omitting it attaches the image to the response and writes no file.
**playwright** (opt-in): absolute paths are REJECTED. Capture with a RELATIVE `filename` under the
tool's own output root, read the returned path, then Bash `cp`/`mv` into the tier dir. NEVER omit
`filename` - it defaults to `page-<timestamp>.png` under the cwd-rooted output dir. **pagecast**
(opt-in): exposes NO destination parameter. Record, `stop_recording`, read the returned `.webm`
path, then Bash `cp`/`mv` into the tier dir. Do not invent a destination argument for it.
`list_console_messages` / `list_network_requests` have NO destination parameter either - they
return data inline; when a scenario's required evidence includes console/network output, Write the
returned data verbatim to a file under the ISOLATE evidence dir yourself so the report cites a real
path, never an inline paraphrase.

**The refusal fallback (family-conditional, fail-closed).** On resolver REFUSAL (cwd outside any
git repo, no `.odoo-ai-root`, no `__manifest__.py` anywhere in the chain):
- **chrome-devtools**: omit `filePath` entirely - the image/snapshot attaches to the response,
  nothing is written - and write the literal `inline (state root unresolvable)` into the report's
  evidence field.
- **playwright / pagecast**: emit `BLOCKED(state root unresolvable - cannot place evidence)`. Do
  NOT capture. Both families write by default and neither can be told where; scattering files is
  the defect this rule exists to prevent. A brief that names an opt-in family in a marker-less cwd
  is a misconfiguration worth blocking on.

A scenario is not downgraded to UNVERIFIED for this reason alone when the observation itself was
made.

## The resolve-capture-substitute protocol (MANDATORY - read this before touching any Tier-2 path)

The resolver above is shell + Python, but most consumers are **prose** - an agent using
`Read`/`Write`/`Edit`, not `Bash`. Those tools take a **literal absolute path string**; they do
**not** run a shell, so `$ODOO_AI_PROJECT_DIR` inside a `Read`/`Write`/`Edit` call neither expands
(no shell to expand it) nor persists (the harness resets the shell environment between separate
`Bash` calls, so even an `export`ed variable from a prior Bash call is gone). Putting a `$VAR` or a
bare `.odoo-ai/...` literal into a Read/Write/Edit call is therefore always a bug. Every skill and
agent that touches a Tier-2 subpath (SHARE or ISOLATE) follows this THREE-STEP protocol:

1. **Resolve ONCE, via Bash, and CAPTURE the printed absolute path(s).** Run one or both, as
   needed for the artifact you're about to touch:
   ```
   bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share
   bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh isolate
   ```
   Each prints exactly one absolute path on stdout (and creates the dir if it did not exist yet).
   Read that output and hold it as a plain string for the rest of this turn/step.

2. **Substitute that captured ABSOLUTE STRING, literally, into every subsequent
   Read/Write/Edit/Bash path for this artifact.** The captured value is just text you copy in -
   there is no variable, no re-resolution, no shell involved in the substitution.

3. **NEVER put `$ODOO_AI_PROJECT_DIR/...`, `$ODOO_AI_WORKTREE_DIR/...`, or a bare
   `.odoo-ai/...` literal into a Read/Write/Edit call.** It will not expand and will not persist -
   the captured literal from step 1 is the only safe form. (A `Bash` call MAY reference the env var
   directly within that SAME `bash -c` invocation, since a shell is running there - but never across
   a Read/Write/Edit boundary.)

### Worked example

```
# Step 1 - resolve once, capture the printed path.
Bash: bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share
  -> stdout: /home/user/.odoo-ai/projects/ab12cd34ef56

# Step 2/3 - substitute the captured literal into every later call. WRONG vs RIGHT:
WRONG:  Read $ODOO_AI_PROJECT_DIR/context.md                 # does not expand, does not persist
WRONG:  Read .odoo-ai/context.md                              # cwd-relative, wrong root entirely
RIGHT:  Read /home/user/.odoo-ai/projects/ab12cd34ef56/context.md
```

If you need BOTH the SHARE and ISOLATE dirs in the same step (e.g. reading shared `context.md`
while writing an ISOLATE `run-<id>.json`), resolve both up front in one Bash call and capture both
printed lines - do not interleave a resolve call between every single Read/Write.

### Placeholder notation used in skill/agent prose

Throughout this plugin's prose, `<SHARE_DIR>` and `<ISOLATE_DIR>` are PLACEHOLDERS that stand for
the absolute path you captured from the resolver in step 1 (SHARE and ISOLATE respectively).
`$ODOO_AI_HOME` denotes the Tier-1 flat root (`~/.odoo-ai` by default) and may be used directly.
When you act on a path written as `<SHARE_DIR>/survey/<slug>/report.md`, you first resolve+capture
the SHARE dir, then substitute the captured absolute string in place of `<SHARE_DIR>` - NEVER write
the literal angle-bracket token (or a bare `.odoo-ai/...`) into a Read/Write/Edit call. A file that
uses these placeholders carries a one-line pointer back to this protocol at its first Tier-2 use;
it does not restate the three steps.

## Cross-worktree dispatch (when a pipeline targets a root other than the dispatcher's own cwd)

Some pipelines operate on a TARGET worktree/repo different from the dispatching skill/agent's own
inherited cwd - reviewing a PR checked out into a separate worktree, a doc run scoped to
`TARGET=worktree:<abs-path>`, a rebase/forward-port integration worktree. `<SHARE_DIR>` is
cwd-independent within one repo (its key converges via `--git-common-dir`, § The three tiers above)
so this never applies to it; `<ISOLATE_DIR>` is NOT (its key diverges via `--show-toplevel`) - a
leaf that resolves `<ISOLATE_DIR>` from its OWN dispatch-inherited cwd instead of the pipeline's
target root lands its artifact in the WRONG worktree's directory, orphaned from every sibling leaf
in the same run.

**The rule:** when your dispatch brief names an external logical root distinct from your own
inherited cwd - `review_root`, `doc_root`, an integration worktree path, or any absolute-path field
the brief calls out as "the target" - the DISPATCHER (the skill/agent that names that root and fans
out leaves against it) resolves `<SHARE_DIR>`/`<ISOLATE_DIR>` ONCE with cwd set to THAT root:

```
bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh --root <target-root> share
bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh --root <target-root> isolate
```

...and passes the CAPTURED ABSOLUTE strings to EVERY leaf it dispatches in that pipeline (as
explicit brief fields, e.g. `SHARE_DIR: <abs-path>` / `ISOLATE_DIR: <abs-path>`). A leaf that
receives these fields MUST substitute them directly wherever this snippet's placeholder notation
says `<SHARE_DIR>`/`<ISOLATE_DIR>` and MUST NOT re-run the resolver from its own cwd - re-resolving
independently is exactly what causes the divergence this rule exists to prevent. A leaf invoked
WITHOUT these fields (a standalone/direct invocation, not part of a cross-worktree pipeline) falls
back to the normal resolve-capture-substitute protocol above, resolving from its own cwd as usual.

Equivalently: every leaf in the pipeline resolves `<ISOLATE_DIR>` as if its cwd were the target root.
Prefer `--root <target-root>` (one process, no shell nesting) for every new call site; the older
equivalent `bash -c "cd <target-root> && bash ...resolve_project_dir.sh share"` remains correct for a
caller that already uses it, but neither form matches the state-root permission allowlist's exact,
wildcard-free rules (the target path varies per call) - an agent issuing either one directly still
prompts for approval today. Either way the DISPATCHER resolves ONCE and passes the captured literal -
one resolver invocation, not N, and no possibility of drift.
Canonical worked example: `agents/odoo-review-scoper.md` (`review_root`) and the `odoo-code-review`
skill's Phase 0, which resolves once and threads the captured `SHARE_DIR`/`ISOLATE_DIR` through the
scoper, every reviewer, the UI reviewer, and synthesis - point here instead of re-deriving this rule
per pipeline.
