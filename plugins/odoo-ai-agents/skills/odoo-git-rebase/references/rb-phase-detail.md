<!-- Reference for `odoo-git-rebase` § The pipeline: per-phase git-ops requests (outcome + result), dispatch-brief templates, artifact formats. -->

# Git-Rebase Pipeline - per-phase execution detail

**Contents:** Principal-checkout-lock (MUST - enforced at P0 and P7) - P0 - Intake / resolve - P1 - Recon (range enumerate) - P2 - Intent extract (parallel, rebase MODE) - P3 - Cluster behavior comparison - P4 - Classify (orchestrator records only) - P5 - Design (conditional route-out) - P6 - Plan gate (Plan Mode) - Summary - The single rebase invocation (delegated to git-ops at P7) - Per-commit plan - Conflict-resolution policy - Instance verify (B3 decision) - Installable guard - Bucket-(c) upgrade-scale decisions - P7 - Create integration worktree + start rebase - P8 - Conflict-resolution loop - P8b - Symbol-survival + collection gate - P9 - Adapt + test forward (per touched module) - P9b - Code-review loop (in-pipeline; fix-until-clean before verify) - P10 - Verify - P11 - Gate (human-confirm) - P12 - Final review + PR - rebase-log.md format - P8-resolved modules - Test-leg reports - intake.md format

All paths are under the integration worktree unless noted. `<slug> = <feature-ref>-onto-<new-base>`
(sanitized). Artifacts live under `<ISOLATE_DIR>/git-rebase/<slug>/` (gitignored; resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit). Every Odoo Semantic call passes a concrete `odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).

---

## Principal-checkout-lock (MUST - enforced at P0 and P7)

NEVER move the principal (main) working tree off its current branch or reset it.
Any branch needed locally (`<new-base>`, the
feature branch, or a PR HEAD) is materialized by asking git-ops for a new worktree on it -
never by switching the principal.

---

## P0 - Intake / resolve

**FIRST: check for an in-progress or partially-completed run before dispatching intake.**

Resolve the ISOLATE state dir once for this run: call `mcp__plugin_odoo-ai-agents_odoo-local__project_dir` with axis `isolate` and
`cwd` = the repo root, and substitute the returned absolute path for `<ISOLATE_DIR>` below.

1. Check for an existing checkpoint from a prior session: read
   `<ISOLATE_DIR>/git-rebase/<slug>/checkpoint.json`. Present -> a prior run exists; resume from
   its last completed phase.
2. Check whether a rebase is already in progress in an existing integration worktree: when the
   integration worktree path is known from checkpoint.json, call `repo_facts` on it.
   `operation_in_progress` = `rebase` -> RESUME the P8 conflict loop; do NOT restart or abort
   the rebase.

If a rebase is in progress: skip P1-P7 entirely; resume the P8 loop from the stopped
commit (skip `status=resolved` commits in checkpoint.json; resume a `status=designed`
commit at P6 design_doc ingestion). Do NOT blindly recreate the integration worktree.

Dispatch a haiku subagent. Brief (run-specific inputs only):

```
DISPATCH MODEL: haiku
TASK: Resolve the following natural-language rebase request into structured inputs.
NL REQUEST: <verbatim user prompt>
STEPS:
  1. Identify the feature ref (local branch name OR a PR number/URL).
     If a PR URL/number is given: report it in pr_resolved_from; the orchestrator will
     resolve the branch details via git-ops after you return.
  2. Identify the new-base ref (branch of the SAME Odoo series as the feature).
  3. Verify same_series_ok: both refs must share the same Odoo major version (both `<series>`).
  4. Determine local presence:
     - If the feature branch is NOT present locally as a branch or worktree:
         add it to branches_to_materialize (format: <remote>/<branch>).
         Do NOT create any worktree or switch any branch yourself.
     - If new-base is NOT present locally as a branch or worktree:
         add it to branches_to_materialize (format: <remote>/<new-base>).
         Do NOT create any worktree or switch any branch yourself.
     The orchestrator delegates worktree creation to git-ops after you return.
  5. Emit open_questions[] for anything ambiguous - do NOT guess. One item per ambiguity.
EMIT: intake.md at <ISOLATE_DIR>/git-rebase/<slug>/intake.md
FORMAT:
  feature_ref: <local branch name or PR URL>
  feature_worktree_path: <absolute path if already present locally, else "pending-materialize">
  new_base: <branch name>
  same_series_ok: true|false
  pr_resolved_from: <PR URL if applicable, else null>
  branches_to_materialize: [<remote>/<branch>, ...]
  open_questions:
    - "<question 1>"
```

Ask the user only the `open_questions` in one message, then re-dispatch P0
with the answers. After P0 returns: if `pr_resolved_from` is set, invoke git-ops to
get the headRefName and headRepository; for each `branches_to_materialize` entry, invoke
git-ops to create a dedicated worktree (principal-checkout-lock enforced by git-toolkit).

---

## P1 - Recon (range enumerate)

Read `<ISOLATE_DIR>/git-rebase/<slug>/intake.md` back before enumerating and take `feature_ref` /
`new_base` / `feature_worktree_path` from that file. Absent -> re-dispatch P0. Contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 1.

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) once for the recon enumerate-triage
(read-only). The request states the outcomes and where they are written, never the commands:

```
TASK: Enumerate and triage the commit range for the rebase pipeline.
FEATURE_REF: <branch>
NEW_BASE: <branch>
TRIAGE_TABLE: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-triage-table.md Table 1
RESULTS (write each to recon.md; the data flows on to P3, P7 and P10):
  1. old_base - the merge base of NEW_BASE and FEATURE_REF (the range boundary). When the two refs
     have MORE than one merge base (criss-cross history), return all of them and stop: emit an
     open_question "Ambiguous merge-base (criss-cross history); human must confirm the correct
     range boundary before P7 proceeds."
  2. The commits of the range - every non-merge commit after old_base up to FEATURE_REF, oldest
     first (sha, subject).
  3. Topology - whether the range holds merge commits. If it does, note them in recon.md and flag
     to the user that the replay must preserve merges or the topology is lost (a plan.md row).
  4. Absorbed candidates - which of those commits' changes are already on NEW_BASE (patch-equivalence
     pre-filter, cross-checked by a second independent listing). CANDIDATES only: P3 is
     authoritative, outcome (a) is decided at P3 and P10, and a commit is never skipped on this
     signal alone.
  5. Per non-(a) commit - the files it touches with their change statistics, for the EXTRACT
     tier per Table 1.
EMIT: <ISOLATE_DIR>/git-rebase/<slug>/recon.md
FORMAT (header line `old_base: <sha>`, then one row per commit):
  sha: <sha>
  subject: <one-line message>
  modules: [<list of touched Odoo module dirs>]
  already_on_base: true|false  # patch-equivalence candidate only; P3 is authoritative
  extract_tier: haiku|sonnet
  merge_commits_in_range: true|false
  merge_base_ambiguous: true|false
```

---

## P2 - Intent extract (parallel, rebase MODE)

### P2 pre-step: git-ops commit dump

Before dispatching intent-extractors, invoke git-ops to write the full commit content
for each non-(a) commit:

```
TASK: write per-commit dump files for intent extraction
commits: [<sha1>, <sha2>, ...]  # all non-(a) SHAs from recon.md
output_dir: <ISOLATE_DIR>/git-rebase/<slug>/commits/
output_format: full commit content (message + diff) for each SHA written to <output_dir>/<sha>.dump
worktree: <any local worktree where the commits are accessible (e.g. feature worktree or principal)>
```

git-ops returns a `{ <sha>: <abs-path> }` map. Pass the appropriate `commit_dump_path`
in each extractor brief below.

### P2 dispatch: odoo-intent-extractor

Dispatch one `odoo-intent-extractor` per non-(a) commit from `recon.md`. Model = `extract_tier`
from recon. Brief (rebase MODE - different from forward-port MODE):

```
DISPATCH MODEL: <extract_tier>
GROUNDING MODE: rebase-base-head
NEW BASE REF: <new-base>
SHA: <sha>
commit_dump_path: <ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump
SERIES: <series>
SLUG: <slug>
TASK: Extract this commit's business intent and behavioral contract.
OUTPUT FIELDS: sha, intent_one_liner, symbols[], outcome_hint, grounded
USER LANGUAGE: <lang | omit when English>
```

The dispatch above is the DEFAULT (per-commit) shape - use it while the range stays at or
below ~30 non-(a) commits, with `SLUG: <slug>` (the bare run slug).

### P2 dispatch (module-batched, above ~30 non-(a) commits)

**BAN: at most one `odoo-intent-extractor` instance per module for this run, once the
threshold trips.** Above the threshold, walk a `module -> [ordered sha list]` map built from
`recon.md`'s per-commit `modules[]` rows; for each module, launch exactly ONE
`odoo-intent-extractor` carrying that module's full ordered commit list - never a fresh
dispatch per individual commit once this threshold trips. Model = the module bundle's triaged
EXTRACT tier (worst-case commit in the bundle, per Table 1).

**`SLUG` is PER-MODULE here, never the bare run slug.** A commit that touches two modules is
dispatched to BOTH modules' extractor instances. Set `SLUG` to `<slug>/<module>` for EVERY
module's dispatch: module A's instance writes
`<ISOLATE_DIR>/git-rebase/<run-slug>/A/intents/<sha>.md`; module B's writes `.../B/intents/<sha>.md`
for the SAME sha.

Brief (run-specific inputs only):

```
DISPATCH MODEL: <extract-tier>            # the MODULE bundle's tier, per Table 1
GROUNDING MODE: rebase-base-head
NEW BASE REF: <new-base>
MODULE: <module-name>
commit_dump_paths:
  <sha1>: <ISOLATE_DIR>/git-rebase/<slug>/commits/<sha1>.dump
  <sha2>: <ISOLATE_DIR>/git-rebase/<slug>/commits/<sha2>.dump
  # ... every non-(a) sha touching this module, oldest first
SERIES: <series>
SLUG: <slug>/<module>              # PER-MODULE namespace for THIS extractor's own intents/ writes only
TASK: For EACH commit in commit_dump_paths (in order), extract its business intent and
      behavioral contract.
OUTPUT FIELDS: sha, intent_file, intent_one_liner, symbols[], outcome_hint, grounded
USER LANGUAGE: <lang | omit when English>
```

Aggregate every returned summary (`sha` / `intent_file` / `intent_one_liner` / `symbols` /
`outcome_hint` / `grounded` - one per commit, across every module's dispatch) - the input to the P2 consolidation fan-in.

### P2 consolidation (module-batched mode only, before P3)

Runs ONLY when the module-batched dispatch was used (the default per-commit dispatch needs no
consolidation).

The instant a module-batched extractor for a commit's module returns, mark that commit
`<sha>: extracted-pending-consolidation` in `checkpoint.json` - NEVER `<sha>: extracted` yet. Only
after the copy below is confirmed does a commit earn `<sha>: extracted`.

For each non-(a) commit `<sha>` still recorded at `extracted-pending-consolidation`, using the
`modules[]` list `recon.md` already recorded for that commit:

- `len(modules[sha]) == 1`: the sole module's returned `intent_file` IS the commit's only
  record - invoke git-ops to copy it to the canonical
  `<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md` (a plain file copy inside the gitignored
  ISOLATE scratch dir - not a git mutation).
- `len(modules[sha]) > 1` (the shared-commit case): invoke git-ops to copy the FIRST module's
  (by `modules[sha]` order as recorded at P1)
  `intent_file` to the canonical `<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md`; record
  `owner_module: <first-module>` for that sha in `checkpoint.json` so a resumed run does not
  re-derive a possibly-different owner. Leave the non-owning module's copy in place.

The copy is an idempotent overwrite: a resumed run re-attempts it for EVERY sha still at
`extracted-pending-consolidation` (never re-dispatch the extractor). After git-ops confirms the
destination file exists and is non-empty, promote that sha to `<sha>: extracted` in
`checkpoint.json`. Downstream phases (P3/P5/P8/P9) read
`<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md`.

**Default per-commit dispatch:** mark each commit `<sha>: extracted` directly after its intent
file is written.

---

## P3 - Cluster behavior comparison

### P3 gate: canonical intent record completeness (MUST pass before any P3 dispatch)

Fail CLOSED: an absent or empty record is never "nothing to compare".

Before the pre-step below (and before dispatching `odoo-diff-comparator`): for every non-(a)
commit in `recon.md`, delegate a read-only existence + non-empty check on
`<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md` (invoke git-ops or Explore - never read
inline). If ANY non-(a) commit's canonical record is missing or empty, STOP and return:

```continuation
status: BLOCKED
produced: []
next: []
blocked_reason: <N> non-(a) commit(s) missing a canonical intents/<sha>.md record: [<sha, ...>].
  Re-run the P2 consolidation fan-in for these commits (idempotent - safe to redo even if a
  prior partial copy already landed) before retrying P3.
```

On this `BLOCKED`: do not proceed, re-run the named remediation (the P2 consolidation copy for the
listed shas), confirm the gate passes, then retry P3 from the top.

### P3 pre-step: git-ops feature diff

Before dispatching odoo-diff-comparator, invoke git-ops to produce the feature diff:

```
TASK: produce the feature diff for rebase behavior comparison
result: the changes <feature-ref> introduced since it diverged from <new-base> (what the feature
  branch adds, with none of the changes <new-base> gained meanwhile)
output: <ISOLATE_DIR>/git-rebase/<slug>/feature-diff.txt
worktree: <any local worktree where both refs are accessible>
```

git-ops writes the diff to the output file and returns the path.

### P3 dispatch: odoo-diff-comparator

Dispatch `odoo-diff-comparator` (sonnet):

```
DISPATCH MODEL: sonnet
mode: rebase
TASK: Compare the feature branch versus the new base as a WHOLE - what intents the new base
      already satisfies, what symbols it renamed/moved, what override points it refactored.
REFS:
  FEATURE_REF: <branch>
  NEW_BASE: <branch>
  diff_scope: the feature branch's own changes since it diverged from <new-base>
  diff_path: <ISOLATE_DIR>/git-rebase/<slug>/feature-diff.txt
  intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/
OUTCOME_CONTRACT: [[rb-intent-4outcome]] (${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md)
```

Taxonomy, `comparison.md` shape and risk list: the agent's own § Step 3a (rebase mode P3).

---

## P4 - Classify (orchestrator records only)

Read `comparison.md`. For each commit, record exactly one row in `rebase-log.md`:

```
| sha | subject | outcome | failure_mode | evidence | adapt_tier (TBD) | status |
```

Fill `adapt_tier` at the P6 plan gate from `rb-triage-table.md` Table 2. Flag upgrade-scale
bucket-(c) commits now per `rb-triage-table.md` § Bucket-(c) upgrade-scale defer-or-do gate; present
the defer-or-do choice at the P6 plan gate.

**Late extraction:** if any commit has `already_on_base: true` in `recon.md` but `comparison.md`
assigns it a non-(a) outcome, before proceeding to P5/P6: invoke git-ops to write its dump to
`<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump` (same brief as P2 pre-step for a single SHA);
then dispatch a late `odoo-intent-extractor` (rebase MODE, same brief as P2 dispatch with
`commit_dump_path:` set). Record `<sha>: extracted` in `checkpoint.json`.

---

## P5 - Design (conditional route-out)

Fires when a commit matches the design-trigger table (`rb-triage-table.md` § Design-trigger
table): bucket-(c) "do now" always; bucket-(b) adapt when it changes a field/method signature,
an override point, is a refactor in the sense `odoo-solution-design` § When to invoke defines
one, or is full-stack / crosses the legacy<->OWL-2 boundary. Bucket (a)/(d) and trivial
single-symbol (b) skip design.
Continuation Contract payload (emit verbatim):

```yaml
status: paused-design
next: odoo-solution-design
inputs:
  return_to: odoo-git-rebase
  design_slug_hint: <slug>-rb-<sha>
  target_version: <series>
  modules: [<names>]
  intent_records: [<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md]
  classification: "<outcome bucket (c or b)> - <one-line reason>"
```

On re-entry (the plan runner returns with `design_doc`): read `design_doc` path from returned
contract inputs; record it against the commit; set `checkpoint.json` `<sha>: designed`;
proceed to P6 with the design linked. If `design_doc` is absent, set commit back to
`status=extracted` and re-enter P5 next run.

---

## P6 - Plan gate (Plan Mode)

The request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request):
`EnterPlanMode`, present the plan (template below), `ExitPlanMode` on approve. NO branch or worktree is
created before `ExitPlanMode` + user approval. plan.md template:

```markdown
# Rebase plan - <slug>

## Summary
- Feature: <feature-ref>
- New base: <new-base>
- Old base: <old-base sha>
- Series: <series>
- Commit count: <N> (<M> non-(a))

## The single rebase invocation (delegated to git-ops at P7)
Integration worktree: <WT_ROOT>/rb-integration, branch rb/<slug>, start ref: <feature-ref> (feature tip).
Replay: the commits after <old-base> go onto <new-base> (a rebase onto the new base, not a merge).

## Per-commit plan
| sha | subject | outcome | EXTRACT tier | ADAPT tier | design_doc | notes |
|-----|---------|---------|-------------|-----------|------------|-------|
| <sha> | <subj> | (a) | haiku | haiku (skip) | - | already on base |
| <sha> | <subj> | (b) | sonnet | sonnet | - | symbol renamed |
| <sha> | <subj> | (c) | sonnet | fable (CONFIRM) | <path> | framework rewrite |

## Conflict-resolution policy
Resolve each stopped commit to INTENT on the new-base idiom via the `odoo-coding` skill
(dispatched through the Skill tool; it owns the backend/frontend coder fan-out and synthesis).
Review is the `odoo-code-review` skill (P9b in-pipeline + P12 final pre-PR review).
outcome-(a) stops -> git-ops skips that commit.
Never leave a line referencing a renamed/moved symbol.

## Instance verify (B3 decision)
<"WILL provision ONE instance via odoo-instance at P10 because: <reason>" | "SKIP: pure-frontend / docstring range">

## Installable guard
A module shipped `installable: False` at the new base is intentionally deferred: keep it
`installable: False`, exclude it from the install/test set, and do NOT flip it True. Rules:
`${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md`.

## Bucket-(c) upgrade-scale decisions
<"<sha>: DEFER (installable:False, lint-only)" | "<sha>: DO NOW (est. <N> LOC, ADAPT tier: <tier>)">
```

After `ExitPlanMode` + user approval, write `plan.md` as the resume record.

---

## P7 - Create integration worktree + start rebase

Invoke the `git-toolkit:git-ops` skill (via the Skill tool), describing the op:

```
op: create integration worktree at feature tip and replay the feature range onto the new base
worktree: create at <WT_ROOT>/rb-integration; branch rb/<slug>; start ref: <feature-ref>
  start ref is the FEATURE TIP, NOT new-base. The feature branch may be checked out in another
  worktree: name the replay by its start (the tip) and its boundary (old_base), never by the branch.
scope:
  - turn on conflict-resolution reuse in the integration worktree, so previously resolved hunks
    are re-applied and staged automatically
  - replay the commits after <old-base> (from recon.md) onto <new-base>
conflict_resolution_policy:
  po_policy: take-feature-side  # the feature branch's version, not the base's
  pot_policy: take-feature-side
  binary_policy: prefer-feature-per-project-convention  # flag the choice in rebase-log.md for human review
  generated_policy: do-not-merge; regenerate from source after rebase completes
confirmed: yes (Plan Mode approval obtained at P6)
```

git-ops returns `DONE` (proceed to P8b) or `BLOCKED-CONFLICT` with
`conflicted_files: [<paths>]` and `stopped_commit: <sha>` (proceed to P8).

---

## P8 - Conflict-resolution loop

### Conflict-class handling (policy passed upfront in P7 dispatch brief)

The P7 `conflict_resolution_policy` makes git-ops resolve all mechanical conflict classes
before stopping on text-hunk conflicts. Rules:

| File type | Policy |
|---|---|
| `.po` / `.pot` | Take the feature side per `po_policy`; then re-run `odoo-i18n` after the full rebase completes; do NOT hand-merge gettext diffs |
| Binary (PNG, ODS, PDF, etc.) | Prefer feature per `binary_policy`; flag the choice in `rebase-log.md` |
| Generated assets (compiled JS, minified CSS, etc.) | Regenerate from source after the rebase completes per `generated_policy`; do NOT hand-merge generated content |
| Text hunk (Python/XML/JS/SCSS/CSV) | Route to the `odoo-coding` skill per ADAPT tier as described below |

### Conflict-TYPE taxonomy (rename-commit scenarios, Odoo rebases)

CONFLICT-TYPE cases born of module/file renames on the new base, resolved per type:

- **static/binary add/add from a renamed module** (e.g. `static/description/*.png`, generated
  assets duplicated under both the old and renamed module path) -> take the NON-EMPTY side; never
  leave a zero-byte file.
- **modify/delete of a renamed-away module** (the new base deleted/relocated a file the feature
  still edits) -> honor the base's removal of the path (the git-toolkit S10 continue-driver runs
  the deletion), then re-home the intent into the renamed module via the `odoo-coding` skill.
- **rename/rename** (both sides renamed the same file differently) -> keep the new-base name; the
  `odoo-coding` skill ports the feature hunk onto it.

Generic per-path mechanics (deleted-by-one-side, text markers, reuse-resolved, continue-vs-skip):
git-ops owns them (git-toolkit `snippets/git-safety-contract.md` § "S10 - Conflict continue-driver
(canonical)"). Never ask git-ops to skip a commit because no files remain unmerged; a commit is
skipped only when continuing reports that it became empty.

### Resolution-reuse hygiene

Run a single rebase per repo at a time. After the reuse step auto-resolves a conflict, the adapt subagent
MUST still verify the auto-resolved hunk against the commit's intent file. Never let git-ops
continue past a file the reuse step resolved without a symbol check against `intents/<sha>.md`.

### Abort path

If 3 consecutive attempts to continue the rebase fail (coder cannot resolve, or the resolution
reintroduces a conflict), do NOT keep retrying. Invoke git-ops to abort the rebase
(restores <WT_ROOT>/rb-integration to its pre-rebase state = feature tip). Restore state from
`checkpoint.json` (the `rb/<slug>` branch is at the feature tip again; all
`designed`/`extracted` intents are still on disk). Escalate, naming which commit SHA blocked the loop and why.

### Per-conflict dispatch

For each `BLOCKED-CONFLICT` return from git-ops, consume the canonical output fields:
- `conflicted_files: [<paths>]` - the text-hunk files that need semantic resolution.
- `stopped_commit: <sha>` - the SHA the rebase stopped on; use for intent file lookup.

Need to confirm the state? Ask git-ops for the files that still carry conflict markers (and the
tree status) in its reply; do not read it with git yourself.

**Fast-path fallback (missing intent file):** if no `intents/<sha>.md` exists for
`stopped_commit`: invoke
git-ops to write the commit dump to `<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump`,
then dispatch `odoo-intent-extractor` (rebase MODE, P2 brief with `commit_dump_path:` set)
to create the intent file before proceeding to the coder.

Read the stopped commit's P4 outcome first. Outcome (a) or (d): invoke git-ops to skip the commit
and dispatch nothing else - a bucket-(a)/(d) commit is never sent to `odoo-coding`.
Outcome (b)/(c): dispatch Explore first if context is needed, then the `odoo-coding` skill via the
Skill tool (never raw `odoo-coder` or `odoo-frontend-coder` agents):

```
SKILL: odoo-coding
DISPATCH MODEL: <adapt_tier from plan.md>
TASK: Resolve a rebase conflict for one commit in a same-series Odoo rebase.
SHA: <sha>
INTENT: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md
BUCKET: <b | c - the P4 outcome; an (a)/(d) commit is skipped, never sent>
COMMIT: caller   (make NO commit - the rebase is stopped on this commit; return the resolved file
      list, and the caller stages it and continues)
TEST LEG: deferred - P9   (write no test and run no integrated test here; P9 runs this module's
      test leg once the rebase is done)
RUN_ID: <this run's id>
FAILURE_MODE: <from comparison.md>
CONFLICTED_FILES: <the conflicted files git-ops reported - text hunks only; .po/binary/generated handled above>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
RULE: Resolve to the INTENT recorded at INTENT, using the idiom of the new base.
      Never leave a line referencing a symbol that was renamed/moved at the new base.
      On a module-descriptor `version` conflict (the descriptor filename
      ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md row 6 names for the series),
      keep the new-base ref's `version` field unchanged - a same-series replay never bumps it.
      If the reuse step auto-resolved any file: verify each auto-resolved hunk against INTENT
      before staging - a reused resolution replays text, not intent.
      After resolving: emit a "RESOLVED" status listing the resolved files.
      Caller will invoke git-ops to stage and continue per the stateless-resume recipe.
```

After `odoo-coding` returns RESOLVED: record each module its returned file list touches in
`rebase-log.md` § P8-resolved modules (one `<sha>: <module>, ...` line); P9 runs each module's test leg. Then invoke git-ops to stage the returned file list and continue the
stopped rebase, per the canonical continue-driver (git-toolkit S10, cited in the Conflict-TYPE taxonomy
above) and the stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

Loop until git-ops returns `DONE` (rebase complete - proceed to P8b). `BLOCKED-CONFLICT`
continues the loop with the next stopped commit from `stopped_commit`; on 3 consecutive
`BLOCKED-CONFLICT` returns for the same `stopped_commit` without resolution progress, invoke
the abort path above. A plain `BLOCKED` return (non-conflict human-confirm gate) escalates
immediately per the stateless-resume recipe in git-delegation.md.

---

## P8b - Symbol-survival + collection gate

**MUST run before P9.** After the rebase loop finishes (git-ops returns `DONE`), run
symbol-survival analysis over every file touched by the replayed range - conflicted AND
merge-clean-but-feature-touched files.

### Identifying feature-touched files (delegated to git-ops)

Ask git-ops for the sorted list of files the replayed range touches (every file changed after
`<old-base>` up to `<feature-ref>`), written to `<ISOLATE_DIR>/git-rebase/<slug>/touched-files.txt`.
Never read the diff inline.

This list is the file set for the gates below.

### Symbol-survival check (delegated)

Dispatch Explore + OSM `entity_lookup` over the feature-touched files per
`[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`)
Sections 1-2.5 - adapted for rebase context (record the verdict only):

- Ground: the SHARED-SERIES base HEAD (`<new-base>`) - NOT a cross-version diff.
- For each symbol the replayed range imports, calls, or references: confirm it exists
  at `<new-base>` HEAD with the expected name, type, and module. Seven autosilent break
  classes from `[[fp-symbol-survival-check]]` apply unchanged (renamed, moved, retyped,
  split, merged, removed, now-internal).
- A symbol absent/renamed/retyped at base HEAD is a **BLOCKER**. Resolve each blocking symbol back into
  its 4-outcome bucket (outcome b/c/d typically) and re-stage the file before P9.
- Record all findings in `verify.md` § symbol_survival.

### Import-resolvability gate (pyflakes F821)

Run `pyflakes` over every feature-touched `.py` from `touched-files.txt`. Any `F821` (undefined name)
is a broken import that survived the clean merge and MUST be resolved (4-outcome bucket) before P9.
Check: `[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`)
Sections 2.5(d) and 2.5(e). Dispatch to `Explore` (read-only) per § Who runs this check; record the
PASS/FAIL verdict only.

```bash
pyflakes <every-feature-touched-.py-from-the-Explore-list>   # any F821 = blocker
```

### Collection acceptance gate (two lanes, both delegated)

Two lanes; record each verdict and never read a diff or log inline.

**Lane 1 - static collection (always; no DB, no server).** After all symbol-survival +
import-resolvability blockers are resolved, dispatch `Explore` (read-only) - the delegate
`[[fp-symbol-survival-check]]` § Who runs this check assigns to this lane - with the
`rb-integration` worktree path, the feature-touched test files, and this command. It returns ONLY
`PASS`, or `FAIL` plus one line per collection error (`<file>::<node> | <error class> | <message>`):

```bash
python -m pytest --collect-only <feature-touched test files>   # zero collection errors
```

**Lane 2 - Odoo collection (only when a feature-touched test subclasses an Odoo database-backed
test class - `TransactionCase`, `HttpCase`, or another the series ships, per Odoo Semantic
`test_base_classes`).** Never run `odoo-bin` for this yourself and never have `Explore` run it: invoke the `odoo-instance` skill (via the Skill tool) with:

```
OPERATION: run-tests
GATE_ROLE: node-verify
SERIES: <series>
RUN_ID: <this run's id>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
MODULES: <the modules owning those test files, dependency order>
TEST_TAGS: </<m> per module in MODULES, comma-joined - never untagged>
MODE: fresh
```

`odoo-instance` returns the `instance-ops` block. Lane 2 PASSES only on `status: tests-passed` or `tests-passed-with-warnings`
with `failed` and `errors` both 0 and every module in `modules_installed`; `tests-failed`,
`tests-inconclusive` (no proof a suite ran) or any `errors > 0` is a FAIL. Warnings are findings for P9, not a collection failure. Capture the returned
`INSTANCE_HANDLE` as this run's ONE instance: forward it to the P9 briefs and reuse it at P10 B3
(`mode: reuse`) instead of provisioning a second one.

**ACCEPTANCE GATE (HARD):** both lanes that apply must PASS. `0 failed, N error(s)` is **NOT a
pass**. Resolve every error before proceeding to P9 (same gate as forward-port P7).

---

## P9 - Adapt + test forward (per touched module)

For each module whose behavior changed - and for every module listed in `rebase-log.md`
§ P8-resolved modules, whose test leg P8 deferred here - invoke the `odoo-coding` skill (via the Skill
tool) ONCE with the adapt fields below (never raw `odoo-coder` or `odoo-frontend-coder`). Record the node's per-test report
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`) in `rebase-log.md` § Test-leg reports,
one `<module>: <report>` per module. Adapt brief:

```
DISPATCH MODEL: <adapt_tier>
REQUEST: Adapt module <module> and the branch's own tests to the new-base (<new-base branch>) idiom.
MODE: adapt
MODULE SCOPE: <module> @ <WT_ROOT>/rb-integration/<module>
INTENT: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md - the behavioral oracle (one path per
      replayed sha touching the module)
BUCKET: <per replayed sha touching the module: b | c | d - [[rb-intent-4outcome]]; never a
      bucket-(a) sha: (a) commits are skipped or already on the base, with no code and no test
      to forward (rb-triage-table.md Table 2 short-circuit)>
SOURCE TESTS: <the branch's own test files for this module, in the integration worktree>
BROKEN TEST-SYMBOLS: <the P8b symbol-survival entries that land in those test files | omit when none>
ODOO VERSION: <series>
WORKTREE_PATH: <WT_ROOT>/rb-integration
RUN_ID: <this run's id>
INSTANCE_HANDLE: <the P8b Lane 2 instance-ops block, verbatim - or 'none' when P8b provisioned none>
ADDONS_PATH: <that handle's addons_path, comma-joined - the coder's addons coverage assertion
      reads it; omit with INSTANCE_HANDLE: none>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
RULE: The node's test leg forwards each source test as the behavioral oracle and adapts its API to
      the new-base idiom (base class, imports, helper signatures). Do NOT write a brand-new test if
      the source commit shipped one - adapt it.
```

Pass the same `INSTANCE_HANDLE` to every `odoo-coding` invocation of this phase and of P9b, and
reuse it at P10 B3 (`mode: reuse`); a consumer runs on it and never releases or parks it
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`).

---

## P9b - Code-review loop (in-pipeline; fix-until-clean before verify)

Fix in a loop until no CRITICAL/HIGH remains in the just-adapted diff, BEFORE P10. The final P12
review still runs.

Dispatch (Skill tool):

```
SKILL: odoo-code-review
TARGET: worktree:<WT_ROOT>/rb-integration
SCOPE: the replayed/adapted commits only (the rebase has produced rb/<slug>); attribute every
       finding to a replayed/adapted line - a finding on a pre-existing base line is OUT of scope.
SERIES: <series>
ASK: severity-graded findings (CRITICAL/HIGH/MED/LOW) + corrected version. Odoo-specific failure
     modes (ORM-hook order, singleton, super() safety, N+1, view/XPath) are in scope.
```

Loop + escalate:
1. Read findings. No CRITICAL/HIGH -> gate PASS, write `<sha>: reviewed`, proceed to P10.
2. CRITICAL/HIGH present -> dispatch `odoo-coding` with the findings as the fix brief:
   ```
   ODOO VERSION: <series>
   WORKTREE_PATH: <WT_ROOT>/rb-integration
   RUN_ID: <this run's id>
   SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
   ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
   ADAPT TIER: <same tier as the P8 adapt for these files>
   INSTANCE_HANDLE: <the P8b Lane 2 instance-ops block, verbatim - or 'none'>
   ADDONS_PATH: <that handle's addons_path, comma-joined - omit with INSTANCE_HANDLE: none>
   FIX BRIEF: <the CRITICAL/HIGH findings + reviewer's corrected version>
   RULE: fix to the finding's root cause only; do not expand scope; keep tests GREEN.
   ```
   Add the fix's test-leg report to `rebase-log.md` § Test-leg reports, then RE-REVIEW
   (step 1). Record MED/LOW in `rebase-log.md` for P12, do not block on them.
3. Cap = 3 review->fix iterations. 3rd iteration still CRITICAL/HIGH -> STOP, escalate BLOCKED
   with the failing finding + diff. Never relax the severity bar to pass the gate.

---

## P10 - Verify

### range-diff + dup-guard (always)

#### P10 pre-step: git-ops range-diff

Invoke git-ops to produce the range-diff before odoo-diff-comparator:

```
TASK: produce range-diff for rebase outcome verification
result: a commit-by-commit comparison of the original series (the commits after <old-base> up to
  <feature-ref-tip>) with the rebased series (the commits after <new-base> up to <rb-tip>)
output: <ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt
worktree: <WT_ROOT>/rb-integration (rb/<slug> and feature-ref-tip accessible from here)
```

git-ops writes the range-diff output to the file and returns the path.

#### P10 dispatch: odoo-diff-comparator

Dispatch `odoo-diff-comparator` (sonnet):

```
DISPATCH MODEL: sonnet
mode: rebase
verify_mode: true
TASK: Verify the rebase outcome via range-diff and duplicate-behavior guard.
diff_scope: original series (after <old-base> up to <feature-ref-tip>) vs rebased series (after <new-base> up to <rb-tip>)
diff_path: <ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt
intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/
PLAN: <ISOLATE_DIR>/git-rebase/<slug>/plan.md
```

Range-diff read, duplicate-behavior guard and `verify.md` format: the agent's own § Step 3b. Its
Step 4 `duplicate_blockers` field gates whether you may proceed.

### B3 - conditional instance verify

If P8b Lane 2 already provisioned the run's instance, reuse its `INSTANCE_HANDLE` here (`mode: reuse`)
and provision nothing; when a break the test leg ran on this database touched data files or schema,
release that lease and take the verdict from ONE fresh build via the `odoo-instance` skill (`mode: fresh`, same `WORKTREE_PATH`,
modules and test tags). Otherwise provision ONE instance via the `odoo-instance` skill ONLY when the
rebased range touches ANY of:
- A model field add, remove, rename, or type-change
- A stored compute or constraint
- An ORM `create` / `write` / `unlink` override
- A `migrations/` directory
- A test that subclasses `TransactionCase` or `HttpCase`

Skip for pure-frontend (JS/OWL/SCSS), docstring/label/comment-only, or non-DB-stateful ranges.
Decide from `recon.md` commits[].modules[] + P3 comparison metadata.

Capture the `odoo-instance` output block ONCE as the run's `INSTANCE_HANDLE` and forward it as an
`INSTANCE_HANDLE:` field in EVERY downstream verify / coder / test brief. Whenever a brief names a
`WORKTREE_PATH`, have the lease acquired
with `addons_path` naming THAT worktree so the instance loads it, or authorize
`SELF_PROVISION: worktree-addons`. One live instance per run at a time, and you are its run-level owner
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once every brief that carried the
handle has returned and the P10 verdict is final - BEFORE the P11 human gate, never while a leaf still
holds it - call `mcp__plugin_odoo-ai-agents_odoo-local__lease_release` on its `lease_token` and this
run's run_id. Call `lease_park` instead when the database is still wanted for a likely P11 re-entry
into P9/P10; a re-entry after a release provisions again.
If the odoo-local tools are unavailable, use the allocator CLI documented in ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md.
Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`. Lifecycle:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`. Test conventions:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`. Resolve odoo-bin flags via `cli_help` with
`odoo_version=<series>`.

---

## P11 - Gate (human-confirm)

Present `rebase-log.md` + `verify.md` to the human and ask, as a text question,
`approve / skip / cancel`. STOP. Do NOT push, do NOT open a PR until the human
replies `approve`; `skip` ends the run with the branch unpushed.

---

## P12 - Final review + PR

Order (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail): review -> push -> open PR.

**Step 1 (FIRST) - final code review of the integration worktree, BEFORE any push or PR.**
Delegate a code review passing `TARGET: worktree:<WT_ROOT>/rb-integration`. Fix CRITICAL/HIGH findings on that worktree (dispatch
`odoo-coding` at the P8 ADAPT tier, the SAME loop shape as § P9b) and review again until none
remains; MED/LOW are recorded in `rebase-log.md`. Only when the review returns no CRITICAL/HIGH do
steps 2-3 run.

**Step 2 - push.** Resolve the upstream org/repo from the `origin_url`, and the fork remote name from
the `remotes`, of a `repo_facts` call on `<WT_ROOT>/rb-integration` (the remote other than origin that
branches are pushed to; none or several -> ask the user once). Never hardcode the fork remote or upstream repo.

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push rb/<slug> to the fork remote:

```
op: push rebase branch to fork (never to the upstream directly)
scope: rb/<slug>
worktree: <WT_ROOT>/rb-integration
remote: <fork-remote-name>  # resolved from the repo_facts remotes
confirmed: yes - human approved at P11
```

**Step 3 - open the PR.** Invoke git-ops to open the PR:

```
op: create PR for rebase result
upstream_repo: <org>/<repo>  # resolved from origin URL
base: <new-base>
head: <fork-remote-name>:rb/<slug>
title: rb(<slug>): <one-line summary of the feature intent>
body:
  ## Summary
  Rebase of <feature-ref> onto updated <new-base> (same-series semantic translation).

  ## Outcome summary
  | sha | subject | outcome |
  |-----|---------|---------|
  <rows from rebase-log.md>

  ## Verify result
  range_diff_verdict: <pass|warn|fail>
  duplicate_findings: <none | list>

  ## Design docs
  <links if P5 fired, else "none">
```

**After the PR opens, only PR-OBSERVING work remains** (CI-failure triage, the human merge). Do NOT
delegate another worktree code review. Wait for human merge. NEVER squash commits; never rewrite
commit messages (an outcome-(a) skip records the reason in `rebase-log.md`).

---

## rebase-log.md format

```markdown
# Rebase log - <slug>

| sha | subject | outcome | failure_mode | evidence | adapt_tier | status |
|-----|---------|---------|-------------|---------|-----------|--------|
| abc1234 | add double-post guard | (b) | renamed | `_post`->`action_post` at `account/models/account_move.py:123` | sonnet | resolved |
| def5678 | fix typo in docstring | (a) | already-present | patch-id match on new-base | haiku | skipped |
| ghi9012 | OWL widget refactor | (c) | override-refactored | `ListRenderer` replaced by `ListController` | fable | designed |

## P8-resolved modules

<sha>: <module>, ...   (the modules a P8 conflict resolution touched; each gets a P9 test leg)

## Test-leg reports

<module>: <the P9 / P9b test leg's brief per-test report: what it broke, how the test failed>
```

---

## intake.md format

```yaml
feature_ref: <series>-feat-double-post-guard
feature_worktree_path: <WT_ROOT>/rb-feature-<slug>
new_base: <series>
same_series_ok: true
pr_resolved_from: https://github.com/<org>/<repo>/pull/482
branches_to_materialize: []
open_questions: []
```
