# Git-Rebase Pipeline - per-phase execution detail

**Contents:** Checkpoint writers and shape - Principal-checkout-lock (MUST - enforced at P0 and P7) - P0 - Intake / resolve - P1 - Recon (range enumerate) - P2 - Intent extract (parallel, rebase MODE) - P3 - Cluster behavior comparison - P4 - Classify (orchestrator records only) - P5 - Design (conditional route-out) - P6 - Plan gate (Plan Mode) - Summary - The single rebase invocation (delegated to git-ops at P7) - Per-commit plan - Conflict-resolution policy - Instance verify (B3 decision) - Installable guard - Bucket-(c) upgrade-scale decisions - P7 - Create integration worktree + start rebase

P8-P12 and the artifact formats: `references/rb-phase-detail-p8-p12.md`. Resume rules: `SKILL.md` § Checkpoint / resume.

All paths are under the integration worktree unless noted. `<slug> = <feature-ref>-onto-<new-base>`
(sanitized). Artifacts live under `<ISOLATE_DIR>/git-rebase/<slug>/` (gitignored; resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit). Every Odoo Semantic call passes a concrete `odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).

---

## Checkpoint writers and shape

`<ISOLATE_DIR>/git-rebase/<slug>/checkpoint.json` (contract: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` - record the pre-loop SHA, checkpoint each applied commit, clean-abort or resume):

```json
{
  "phase": "P8",
  "<sha>": "extracted-pending-consolidation|extracted|designed|resolved|reviewed|done",
  "rebase_in_progress": true,
  "integration_worktree": "<absolute path to rb-integration worktree>"
}
```

Writers:
- P2 default per-commit dispatch: writes the canonical `intents/<sha>.md` directly and marks `<sha>: extracted`. Module-batched dispatch: `<sha>: extracted-pending-consolidation` after each intent file (the canonical copy is not yet confirmed, § P2 consolidation); the consolidation fan-in promotes it to `<sha>: extracted` only after git-ops confirms the canonical record exists and is non-empty.
- P5: `<sha>: designed`.
- P8: `<sha>: resolved` after git-ops continues the stopped rebase past that commit.
- P8b: `phase: P8b_done` after the collection gate passes.
- P9b: `<sha>: reviewed` after the code-review loop returns no CRITICAL/HIGH for that commit.

`rebase_in_progress: false` is a clean checkpoint: skip `done` phases and resume from the last incomplete one. A crash-left integration worktree is found through `integration_worktree` and resumed, never recreated.

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

Launch parameters, not brief lines: `model` = haiku; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
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

Launch parameters, not brief lines: `model` = extract_tier; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
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

Launch parameters, not brief lines: `model` = extract-tier; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
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

Launch parameters, not brief lines: `model` = sonnet; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
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
an override point, is a refactor in the sense `odoo-solution-design` § Before dispatch (step 3, `SRS_REQUIRED`) defines
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
  po_policy: three-way-merge  # header from the feature side; an entry the feature branch added or changed wins, every other entry keeps the base's wording
  pot_policy: three-way-merge
  binary_policy: prefer-feature-per-project-convention  # flag the choice in rebase-log.md for human review
  generated_policy: do-not-merge; regenerate from source after rebase completes
confirmed: yes (Plan Mode approval obtained at P6)
```

git-ops returns `DONE` (proceed to P8b) or `BLOCKED-CONFLICT` with
`conflicted_files: [<paths>]` and `stopped_commit: <sha>` (proceed to P8).

---

The rebase targets the base BRANCH as fetched right before it, never a commit id recorded at an
earlier assessment: when the fetched tip differs from the one assessed, re-assess the overlap and
any version-bump collision; fetch again right before the push and repeat when the base moved.
