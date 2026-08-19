<!-- Reference for odoo-git-rebase/SKILL.md § The pipeline. Loaded as needed.
     Per-phase git commands, dispatch-brief templates, artifact formats, and git/PR conventions.
     The SKILL.md body carries the contract; this file carries the verbatim execution detail. -->

# Git-Rebase Pipeline - per-phase execution detail

All paths are under the integration worktree unless noted. `<slug> = <feature-ref>-onto-<new-base>`
(sanitized). Artifacts live under `<ISOLATE_DIR>/git-rebase/<slug>/` (gitignored; resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit). Every Odoo Semantic call passes a concrete `odoo_version=` (never a default; the
pin is session-scoped state any other actor sharing this session can overwrite - SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).

---

## Principal-checkout-lock (MUST - enforced at P0 and P7)

NEVER checkout, switch, or hard-reset the principal (main) working-tree off its current branch -
it must stay on its branch for the entire run. Any branch needed locally (`<new-base>`, the
feature branch, or a PR HEAD) is materialized by delegating a worktree-add to git-ops -
never by switching the principal.

---

## P0 - Intake / resolve

**FIRST: check for an in-progress or partially-completed run before dispatching intake.**

```bash
# 0. Resolve the ISOLATE state dir once for this run.
DIR="$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh" isolate)"

# 1. Check for an existing checkpoint from a prior session.
CHECKPOINT="$DIR/git-rebase/<slug>/checkpoint.json"
if [ -f "$CHECKPOINT" ]; then
  echo "Prior run detected - read checkpoint.json and resume from last completed phase."
fi

# 2. Check whether a rebase is already in progress in an existing integration worktree.
#    If the integration worktree path is known from checkpoint.json:
test -d "$(git -C <integration_worktree_path> rev-parse --git-path rebase-merge 2>/dev/null)" \
  && echo "Rebase in progress - RESUME P8 conflict loop; do NOT restart or abort the rebase."
```

If a rebase is in progress: skip P1-P7 entirely; resume the P8 loop from the stopped
commit (skip `status=resolved` commits in checkpoint.json; resume a `status=designed`
commit at P6 design_doc ingestion). Do NOT blindly recreate the integration worktree.

Dispatch a sonnet subagent. Brief (run-specific inputs only):

```
DISPATCH MODEL: sonnet
TASK: Resolve the following natural-language rebase request into structured inputs.
NL REQUEST: <verbatim user prompt>
STEPS:
  1. Identify the feature ref (local branch name OR a PR number/URL).
     If a PR URL/number is given: report it in pr_resolved_from; the orchestrator will
     resolve the branch details via git-ops after you return.
  2. Identify the new-base ref (branch of the SAME Odoo series as the feature).
  3. Verify same_series_ok: both refs must share the same Odoo major version (e.g. both 17.0).
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

Orchestrator asks the user only the `open_questions` in one message, then re-dispatches P0
with the answers. After P0 returns: if `pr_resolved_from` is set, invoke git-ops to
get the headRefName and headRepository; for each `branches_to_materialize` entry, invoke
git-ops to create a dedicated worktree (principal-checkout-lock enforced by git-toolkit).

---

## P1 - Recon (range enumerate)

Read `<ISOLATE_DIR>/git-rebase/<slug>/intake.md` back before enumerating - P0 wrote it and a resumed
run must take `feature_ref` / `new_base` / `feature_worktree_path` from that file, not from context.
Absent -> re-dispatch P0. Contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 1.

```bash
# Compute old-base (bounded read - git merge-base is in the allowlist; orchestrator runs this inline)
OLD_BASE=$(git merge-base <new-base> <feature-ref>)

# Guard: multiple merge-bases (criss-cross history) make the range boundary ambiguous.
# If >1 line, STOP and surface as open_question before continuing.
if [ "$(git merge-base --all <new-base> <feature-ref> | wc -l)" -gt 1 ]; then
  echo "AMBIGUOUS merge-base - STOP, surface as open_question: multiple merge-bases found; human must confirm range boundary before P7"; fi

# Enumerate commits in range (include merge commits to detect topology issues)
git log --no-merges --oneline ${OLD_BASE}..<feature-ref>

# Guard: detect merge commits in range -> rebase --onto linearizes, may re-replay absorbed commits
git log --oneline --graph ${OLD_BASE}..<feature-ref>
# If merge commits present: either pass --rebase-merges at P7 or flag to user that history
# will be linearized (topology lost) and confirm intent. Add a row to plan.md.

# Patch-id pre-filter: commits NOT yet on new-base (KEEP these).
# --right-only = feature commits with no patch-equivalent on base are listed;
# commits that DROP from this list relative to the full range = outcome-(a) candidates.
# This is a PRE-FILTER ONLY - fragile under context drift (see note below).
git log --cherry-pick --no-merges --right-only --oneline ${new-base}...<feature-ref>

# Cross-check (patch-id is fragile under context drift - use cherry -v as a second signal):
# Invoke git-ops to run cherry -v <new-base> <feature-ref>
# minus prefix = unique to feature (kept); plus or absent = absorbed candidate.

# NOTE: patch-id pre-filter is a CHEAP HINT ONLY. A commit absorbed by base with shifted
# context gets a different patch-id and will NOT be detected as absorbed here.
# Outcome-(a) is authoritatively decided at P3 (comparison) and P10 (dup-guard).
# NEVER skip on patch-id signal alone without P3 confirmation.

# Per-commit stat for EXTRACT tier triage
git show --stat <sha>
```

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for the recon enumerate-triage (read-only); brief:

```
TASK: Enumerate and triage the commit range for the rebase pipeline.
OLD_BASE: <sha>
FEATURE_REF: <branch>
NEW_BASE: <branch>
TRIAGE_TABLE: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-triage-table.md Table 1
STEPS:
  1. Run git log --no-merges --oneline <OLD_BASE>..<FEATURE_REF>
  2. Run `git merge-base --all <new-base> <feature-ref>`: if >1 line, emit an open_question
     "Ambiguous merge-base (criss-cross history); human must confirm the correct range
     boundary before P7 proceeds." Stop here if ambiguous.
  3. Run `git log --oneline --graph <OLD_BASE>..<FEATURE_REF>`: note any merge commits
     in recon.md; flag to user that --rebase-merges will be needed or topology will be lost.
  4. Run the patch-id pre-filter (--right-only) to identify outcome-(a) candidates on new-base.
     Cross-check with the cherry -v signal (minus prefix = unique to feature, plus = absorbed).
     These are CANDIDATES only - P3 is authoritative.
  5. For each non-(a) commit: git show --stat <sha> -> assign EXTRACT tier per Table 1.
  6. Emit recon.md (below).
EMIT: <ISOLATE_DIR>/git-rebase/<slug>/recon.md
FORMAT (one row per commit):
  sha: <sha>
  subject: <one-line message>
  modules: [<list of touched Odoo module dirs>]
  already_on_base: true|false  # patch-id candidate only; P3 is authoritative
  extract_tier: haiku|sonnet|opus
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
SERIES: <e.g. 17.0>
SLUG: <slug>
TASK: Extract the business intent and behavioral contract of this one commit. Read commit
      message -> PR/issue -> test changes -> code comments (priority order). Ground the
      touched symbols at <NEW BASE REF> HEAD (same-version grounding, NOT a cross-version diff).
      Do NOT call api_version_diff (same series; no version jump).
      Write <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md
      Do NOT copy diff hunks as intent. Do NOT classify the 4-outcome bucket (caller's job).
OUTPUT FIELDS: sha, intent_one_liner, symbols[], outcome_hint, grounding
USER LANGUAGE: <lang | omit when English>
```

The dispatch above is the DEFAULT (per-commit) shape - use it while the range stays at or
below ~30 non-(a) commits. `SLUG: <slug>` here is the bare run slug: exactly one dispatch ever
owns a given commit in this shape, so there is no path collision to guard against.

### P2 dispatch (module-batched, above ~30 non-(a) commits)

**BAN: at most one `odoo-intent-extractor` instance per module for this run, once the
threshold trips.** Above the threshold, walk a `module -> [ordered sha list]` map built from
`recon.md`'s per-commit `modules[]` rows; for each module, launch exactly ONE
`odoo-intent-extractor` carrying that module's full ordered commit list - never a fresh
dispatch per individual commit once this threshold trips. Model = the module bundle's triaged
EXTRACT tier (worst-case commit in the bundle, per Table 1).

**`SLUG` is PER-MODULE here, never the bare run slug (closes the shared-commit write race).**
A commit that touches two modules is intentionally dispatched to BOTH modules' single
extractor instances - two independent, concurrently-running instances legitimately process the
identical SHA. Without a namespace, both would target the SAME `intents/<sha>.md` path with no
owner or merge rule - a write race. Set this brief's `SLUG` field to `<slug>/<module>` (the run
`<slug>` plus this module's own name) for EVERY module's dispatch - the extractor's own
write-path template (`agents/odoo-intent-extractor.md` § Rebase mode,
`<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md`, substituted verbatim from this field) then
resolves per module with no change needed to that agent: module A's instance writes
`<ISOLATE_DIR>/git-rebase/<run-slug>/A/intents/<sha>.md`; module B's writes
`.../B/intents/<sha>.md` for the SAME sha - two distinct files, never a last-write-wins
collision.

Brief (run-specific inputs only):

```
DISPATCH MODEL: <extract-tier>            # the MODULE bundle's tier, per Table 1
GROUNDING MODE: rebase-base-head
NEW BASE REF: <new-base>
MODULE: <module-name>
commit_dump_paths:
  <sha1>: <ISOLATE_DIR>/git-rebase/<slug>/commits/<sha1>.dump
  <sha2>: <ISOLATE_DIR>/git-rebase/<slug>/commits/<sha2>.dump
  # ... every non-(a) sha touching this module, oldest first (run-level <slug> - shared,
  # read-only, single writer - unchanged regardless of dispatch shape)
SERIES: <e.g. 17.0>
SLUG: <slug>/<module>              # PER-MODULE namespace for THIS extractor's own intents/ writes only
TASK: For EACH commit in commit_dump_paths (in order), extract the business intent and
      behavioral contract. Ground the touched symbols at <NEW BASE REF> HEAD (same-version
      grounding, NOT a cross-version diff). Do NOT call api_version_diff (same series; no
      version jump). Write ONE <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md per commit
      (the module-scoped <slug> above, so this module's write path never collides with
      another module's for a shared sha). Note any overlap or revert between commits in this
      SAME module bundle. Do NOT copy diff hunks as intent. Do NOT classify the 4-outcome
      bucket (caller's job).
OUTPUT FIELDS: sha, intent_file, intent_one_liner, symbols[], outcome_hint, grounding
USER LANGUAGE: <lang | omit when English>
```

Aggregate every returned summary (`sha` / `intent_file` / `intent_one_liner` / `symbols` /
`outcome_hint` / `grounding` - one per commit, across every module's single dispatch;
`intent_file` is that module's own module-scoped path per the `SLUG` substitution above) - this
is the input to the P2 consolidation fan-in below.

### P2 consolidation (module-batched mode only, before P3)

Runs ONLY when the module-batched dispatch above was used; the default per-commit dispatch
already writes directly to the canonical bare-slug path and is marked `<sha>: extracted` in one
step (see "Default per-commit checkpoint marking" below) - it needs no consolidation and no
intermediate state.

**Checkpoint the two facts SEPARATELY - "the extractor returned" is not "the canonical record
exists".** The instant a module-batched extractor for a commit's module returns, mark that
commit `<sha>: extracted-pending-consolidation` in `checkpoint.json` - NEVER `<sha>: extracted`
yet. Conflating the two would let a crash between extraction and consolidation (or a resumed run
that reads a premature `extracted` and assumes the canonical file exists) leave P3/P5/P8/P9
reading a path that was never written - a green-looking run built on nothing. Only after the
copy below is confirmed does a commit earn `<sha>: extracted`.

For each non-(a) commit `<sha>` still recorded at `extracted-pending-consolidation`, using the
`modules[]` list `recon.md` already recorded for that commit:

- `len(modules[sha]) == 1`: the sole module's returned `intent_file` IS the commit's only
  record - invoke git-ops to copy it to the canonical
  `<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md` (a plain file copy inside the gitignored
  ISOLATE scratch dir - not a git mutation).
- `len(modules[sha]) > 1` (the shared-commit case): invoke git-ops to copy the FIRST module's
  (by `modules[sha]` order as recorded at P1 - deterministic, never last-write-wins)
  `intent_file` to the canonical `<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md`; record
  `owner_module: <first-module>` for that sha in `checkpoint.json` so a resumed run does not
  re-derive a possibly-different owner. The non-owning module's own copy is left in place
  under its per-module namespace (harmless scratch state, swept by the existing orphan-sweep
  rule) - it is simply not the one downstream phases read.

**Idempotent by construction, so resume is a blind re-attempt, not a diff.** The copy is a
plain file overwrite: re-running it against a sha whose canonical file is already correct
reproduces the same bytes - a no-op, never an error. A resumed run therefore does NOT need to
determine which copies already landed before the crash; it simply re-attempts the copy for
EVERY sha still at `extracted-pending-consolidation` (never re-dispatches the extractor itself -
its module-scoped source file at `<ISOLATE_DIR>/git-rebase/<slug>/<module>/intents/<sha>.md` is
untouched by a crash here). After git-ops confirms the destination file exists and is
non-empty, promote that sha to `<sha>: extracted` in `checkpoint.json`. A sha that never gets
promoted past `extracted-pending-consolidation` (a repeatedly-failing copy, a missing source) is
exactly what the P3 completeness gate below exists to catch - it must never reach P3 silently.

After consolidation, every downstream phase (P3/P5/P8/P9) reads the SAME unqualified
`<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md` it always has - no consumer needs to know
whether P2 ran per-commit or module-batched this run.

**Default per-commit checkpoint marking.** For the default (non-batched) dispatch shape, mark
each commit `<sha>: extracted` directly, in one step, immediately after its intent file is
written - it already IS the canonical record, so `extracted-pending-consolidation` never
applies to it.

---

## P3 - Cluster behavior comparison

### P3 gate: canonical intent record completeness (MUST pass before any P3 dispatch)

**Fail CLOSED, not silently through.** P2 consolidation (above) is a NEW moving part that can
be skipped without anyone noticing: a crash between extraction and consolidation, a resumed run
that misreads its own state, or simply a future edit to this pipeline that forgets consolidation
is conditional. If that happens, module-batched mode has written ONLY the per-module-namespaced
files - nothing lands at the canonical `intents/<sha>.md` path P3 reads. An absent or empty
record must never be read as "nothing to compare"; that produces a green-looking `comparison.md`
built on no evidence, the exact shape of the defect this whole fix closes.

Before the pre-step below (and before dispatching `odoo-diff-comparator`): for every non-(a)
commit in `recon.md`, delegate a read-only existence + non-empty check on
`<ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md` (invoke git-ops or Explore - never read
inline). If ANY non-(a) commit's canonical record is missing or empty, STOP and return:

```
status: BLOCKED - <N> non-(a) commit(s) missing a canonical intents/<sha>.md record: [<sha, ...>].
  Re-run the P2 consolidation fan-in for these commits (idempotent - safe to redo even if a
  prior partial copy already landed) before retrying P3.
```

This reuses the SAME `BLOCKED` vocabulary `agents/odoo-intent-extractor.md` (Step 1: "neither
commit_dump_path nor commit_dump_paths provided") and `agents/odoo-diff-comparator.md` (Step 1:
"diff_path not provided") already return for their own absent-required-input guards - never a
new status, never a silent pass-through. The orchestrator's response to this `BLOCKED` is
identical to any other `BLOCKED` return in this pipeline: do not proceed, re-run the named
remediation (here: the P2 consolidation copy for the listed shas), confirm the gate passes, then
retry P3 from the top.

Only once every non-(a) commit's canonical record is confirmed present and non-empty does P3
proceed to the pre-step below.

### P3 pre-step: git-ops three-dot diff

Before dispatching odoo-diff-comparator, invoke git-ops to produce the three-dot diff:

```
TASK: produce three-dot diff for rebase behavior comparison
scope: <new-base>...<feature-ref>  (three-dot form: base vs feature)
output: <ISOLATE_DIR>/git-rebase/<slug>/three-dot-diff.txt
worktree: <any local worktree where both refs are accessible>
```

git-ops writes the diff to the output file and returns the path.

### P3 dispatch: odoo-diff-comparator

Dispatch `odoo-diff-comparator` (opus for cluster-wide runs, sonnet for <=3 small modules):

```
DISPATCH MODEL: opus
mode: rebase
TASK: Compare the feature branch versus the new base as a WHOLE - what intents the new base
      already satisfies, what symbols it renamed/moved, what override points it refactored.
REFS:
  FEATURE_REF: <branch>
  NEW_BASE: <branch>
  diff_path: <ISOLATE_DIR>/git-rebase/<slug>/three-dot-diff.txt
  intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/
OUTCOME_CONTRACT: [[rb-intent-4outcome]] (${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md)
STEPS:
  1. Read diff_path and all intent files.
  2. For each commit's intent, decide which absorption failure mode applies:
       already-present | renamed | moved | override-refactored | depends-drift | test-symbol-removed
  3. Propose exactly one outcome (a/b/c/d) per commit with evidence (symbol + path).
  4. List a duplicate-behavior risk for any commit classified (a) - confirm the feature truly
     already exists at new-base and is not just a similar-looking construct.
EMIT: <ISOLATE_DIR>/git-rebase/<slug>/comparison.md
FORMAT per commit:
  sha: <sha>
  outcome: a|b|c|d
  failure_mode: <from list above | none>
  evidence: <symbol:path>
  proposed_adapt: <one-liner or null>
  dup_risk_note: <string or null>
```

---

## P4 - Classify (orchestrator records only)

Read `comparison.md`. For each commit, record exactly one row in `rebase-log.md`:

```
| sha | subject | outcome | failure_mode | evidence | adapt_tier (TBD) | status |
```

`adapt_tier` is filled in at P6 plan gate from `rb-triage-table.md` Table 2.
Flag upgrade-scale bucket-(c) commits now per `rb-triage-table.md` § Bucket-(c) upgrade-scale
defer-or-do gate - the defer-or-do choice is PRESENTED at the P6 plan gate, never
resolved silently.

**Late extraction (commit dump provisioning for reclassified commits):** if any commit has
`already_on_base: true` in `recon.md` but `comparison.md` assigns it a non-(a) outcome,
that commit was skipped by the P2 pre-step and has no dump file or intent file. Before
proceeding to P5/P6: invoke git-ops to write its dump to
`<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump` (same brief as P2 pre-step for a single SHA);
then dispatch a late `odoo-intent-extractor` (rebase MODE, same brief as P2 dispatch with
`commit_dump_path:` set). Record `<sha>: extracted` in `checkpoint.json`. The deep
reclassification routing logic is FLAG-ONLY - this step only provisions the input so the
git-free leaf never lacks it.

---

## P5 - Design (conditional route-out)

Fires when a commit matches the design-trigger table (`rb-triage-table.md` § Design-trigger
table): bucket-(c) "do now" always; bucket-(b) adapt when it changes a field/method signature,
an override point, is a refactor in the sense `odoo-solution-design` § When to invoke defines
one, or is full-stack / crosses the legacy<->OWL-2 boundary. Reuse the
`odoo-solution-design` § When to invoke non-trivial criterion. Bucket (a)/(d) and trivial
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

On re-entry (run-harness returns with `design_doc`): read `design_doc` path from returned
contract inputs; record it against the commit; set `checkpoint.json` `<sha>: designed`;
proceed to P6 with the design linked. If `design_doc` is absent, set commit back to
`status=extracted` and re-enter P5 next run.

---

## P6 - Plan gate (Plan Mode)

Plan-Mode enter/exit is the SHARED SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit + plan_mode_active
- rebase REUSES it here rather than defining its own: `EnterPlanMode` iff `plan_mode_active` is
absent/false, write the plan (template below), `ExitPlanMode` on approve. NO branch or worktree is
created before `ExitPlanMode` + user approval. plan.md template:

```markdown
# Rebase plan - <slug>

## Summary
- Feature: <feature-ref>
- New base: <new-base>
- Old base: <old-base sha>
- Series: <e.g. 17.0>
- Commit count: <N> (<M> non-(a))

## The single rebase invocation (delegated to git-ops at P7)
Integration worktree: <WT_ROOT>/rb-integration, branch rb/<slug>, start ref: <feature-ref> (feature tip).
Two-arg onto form: target <new-base>, upstream <old-base>. Avoids 'already used by worktree'.

## Per-commit plan
| sha | subject | outcome | EXTRACT tier | ADAPT tier | design_doc | notes |
|-----|---------|---------|-------------|-----------|------------|-------|
| <sha> | <subj> | (a) | haiku | haiku (skip) | - | already on base |
| <sha> | <subj> | (b) | sonnet | sonnet | - | symbol renamed |
| <sha> | <subj> | (c) | opus | fable (CONFIRM) | <path> | framework rewrite |

## Conflict-resolution policy
Resolve each stopped commit to INTENT on the new-base idiom via the `odoo-coding` skill
(dispatched through the Skill tool; it owns the backend/frontend coder fan-out and synthesis).
Review is the `odoo-code-review` skill (P9b in-pipeline + P12 final pre-PR review).
outcome-(a) stops -> git-ops skips that commit (--skip).
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
op: create integration worktree at feature tip and start the onto-rebase
worktree: create at <WT_ROOT>/rb-integration; branch rb/<slug>; start ref: <feature-ref>
  IMPORTANT: start ref is the FEATURE TIP, NOT new-base. This is the integration branch.
  CRITICAL: never pass <feature-ref> as a three-arg rebase target while that branch is
  checked out in another worktree - use the two-arg form on current HEAD instead to avoid
  the "already used by worktree" abort.
scope:
  - enable rerere in the integration worktree with `rerere.autoupdate=true` (local config)
    so rerere-replayed hunks are auto-staged
    (rr-cache is repo-global and shared across all worktrees; assume one rebase per repo at a time)
  - run two-arg onto form: target <new-base>, upstream <old-base>
conflict_resolution_policy:
  po_policy: take-feature-side  # --theirs in rebase context (rebase inverts ours/theirs: --ours=base, --theirs=feature)
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

The `conflict_resolution_policy` in the P7 brief instructs git-ops to resolve all
mechanical conflict classes autonomously before stopping on Odoo-semantic (text-hunk) conflicts.
The table below defines the policy rules (already encoded in the P7 brief) and coder routing
for text hunks:

| File type | Policy |
|---|---|
| `.po` / `.pot` | Take feature side (--theirs; note rebase inverts merge ours/theirs: --ours=base, --theirs=feature); git-ops resolves autonomously per `po_policy` in P7 brief; then re-run `odoo-i18n` after the full rebase completes; do NOT hand-merge gettext diffs |
| Binary (PNG, ODS, PDF, etc.) | Prefer feature per project convention per `binary_policy` in P7 brief; git-ops applies the chosen side; choice is flagged in `rebase-log.md` for human review |
| Generated assets (compiled JS, minified CSS, etc.) | Regenerate from source after the rebase completes per `generated_policy` in P7 brief; do NOT hand-merge generated content |
| Text hunk (Python/XML/JS/SCSS/CSV) | Route to the `odoo-coding` skill per ADAPT tier as described below |

### Conflict-TYPE taxonomy (rename-commit scenarios, Odoo rebases)

The table above is FILE-TYPE. Odoo same-series rebases also hit CONFLICT-TYPE cases born of
module/file renames on the new base - resolve these per type:

- **static/binary add/add from a renamed module** (e.g. `static/description/*.png`, generated
  assets duplicated under both the old and renamed module path) -> take the NON-EMPTY side; never
  leave a zero-byte file.
- **modify/delete of a renamed-away module** (the new base deleted/relocated a file the feature
  still edits) -> honor the base's removal of the path (the git-toolkit S10 continue-driver runs
  the deletion), then re-home the intent into the renamed module via the `odoo-coding` skill.
- **rename/rename** (both sides renamed the same file differently) -> keep the new-base name; the
  `odoo-coding` skill ports the feature hunk onto it.

For the generic per-path mechanics (UD/DD -> honor the deletion; text file with markers -> hand to the
`odoo-coding` skill; rerere-resolved-no-markers -> verify then stage via git-ops; continue-vs-skip), do NOT
restate them - follow git-toolkit S10, the canonical continue-driver in git-toolkit
`snippets/git-safety-contract.md` § "S10 - Conflict continue-driver (canonical)". INVARIANT: NEVER
`--skip` on "no unmerged files"; only `--skip` when `--continue` itself reports an empty patch.

### rerere hygiene

Rerere's `rr-cache` lives in the COMMON git dir and is **shared across ALL worktrees**
of the repo. Assume a single rebase run per repo at a time - concurrent runs will
cross-contaminate cached resolutions. After rerere auto-resolves a conflict, the adapt
subagent MUST still verify the auto-resolved hunk against the commit's intent file: rerere
replays TEXT, not INTENT - a past wrong resolution propagates silently to every identical
conflict marker. Never let git-ops invoke --continue on a rerere-autoresolved file without
a symbol check against `intents/<sha>.md`.

### Abort path (ETHOS #7 fail-3-times escalation)

If 3 consecutive --continue attempts fail (coder cannot resolve, or the resolution
reintroduces a conflict), do NOT keep retrying. Invoke git-ops to abort the rebase
(restores <WT_ROOT>/rb-integration to its pre-rebase state = feature tip). Restore state from
`checkpoint.json` (the `rb/<slug>` branch is at the feature tip again; all
`designed`/`extracted` intents are still on disk). Escalate per ETHOS #7 with a clear
description of which commit SHA blocked the loop and why.

### Per-conflict dispatch

For each `BLOCKED-CONFLICT` return from git-ops, consume the canonical output fields:
- `conflicted_files: [<paths>]` - the text-hunk files that need semantic resolution (mechanical
  types already resolved by git-ops per the P7 `conflict_resolution_policy`).
- `stopped_commit: <sha>` - the SHA the rebase stopped on; use for intent file lookup.

Verify inline if needed (allowlisted bounded reads):

```bash
# Inline verification (allowlisted; canonical fields from git-ops return are primary)
git diff --check
git status
```

**Fast-path fallback (missing intent file):** if no `intents/<sha>.md` exists for
`stopped_commit` (e.g., the small-scale fast-path was taken and P2 was skipped): invoke
git-ops to write the commit dump to `<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump`,
then dispatch `odoo-intent-extractor` (rebase MODE, P2 brief with `commit_dump_path:` set)
to create the intent file before proceeding to the coder.

Dispatch Explore first if context is needed, then the `odoo-coding` skill via the Skill tool
(mirroring P9b - do NOT dispatch raw `odoo-coder`, `odoo-backend-coder`, or `odoo-frontend-coder`
agents; `odoo-coding` owns the backend/frontend split, coder fan-out (via its `odoo-coder`
per-node coordinator), and synthesis):

```
SKILL: odoo-coding
DISPATCH MODEL: <adapt_tier from plan.md>
TASK: Resolve a rebase conflict for one commit in a same-series Odoo rebase.
SHA: <sha>
INTENT_FILE: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md
OUTCOME: <a|b|c|d>
FAILURE_MODE: <from comparison.md>
CONFLICTED_FILES: <list from git diff --check - text hunks only; .po/binary/generated handled above>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve; `<ISOLATE_DIR>` keys on the enclosing repository root, so a leaf that resolves it from inside rb-integration writes into that worktree's own tree>
RULE: Resolve to the INTENT expressed in INTENT_FILE, using the idiom of the new base.
      If OUTCOME=(a): do not resolve - caller will instruct git-ops to skip that commit.
      If OUTCOME=(d): do not resolve - caller will instruct git-ops to skip that commit.
      Never leave a line referencing a symbol that was renamed/moved at the new base.
      On a module-descriptor `version` conflict (`__manifest__.py`, or `__openerp__.py` on v8-v9),
      keep the new-base ref's `version` field unchanged -
      a same-series replay never bumps it. (Same-series analogue only; do NOT import the cross-series
      forward-port C1/C2 migration logic.)
      If rerere auto-resolved any file: verify each auto-resolved hunk against INTENT_FILE
      before staging - rerere replays text, not intent.
      After resolving: emit a "RESOLVED" status listing the resolved files.
      Caller will invoke git-ops to stage and continue per the stateless-resume recipe.
      `odoo-coding` routes OWL/QWeb/SCSS legs to `odoo-frontend-coder`, grounded against
      `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` so the adapted UI stays
      on-theme and design-system-correct for the target series.
```

After `odoo-coding` returns RESOLVED: invoke git-ops to drive continue/skip per the
canonical continue-driver (git-toolkit S10, cited in the Conflict-TYPE taxonomy above) and the
stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`:
- outcome=(a) or (d): instruct git-ops to skip that commit (--skip)
- outcome=(b)/(c): instruct git-ops to stage the resolved files and invoke --continue

Loop until git-ops returns `DONE` (rebase complete - proceed to P8b). `BLOCKED-CONFLICT`
continues the loop with the next stopped commit from `stopped_commit`; on 3 consecutive
`BLOCKED-CONFLICT` returns for the same `stopped_commit` without resolution progress, invoke
the abort path above. A plain `BLOCKED` return (non-conflict human-confirm gate) escalates
immediately per the stateless-resume recipe in git-delegation.md.

---

## P8b - Symbol-survival + collection gate

**MUST run before P9. No test-forward without this gate passing.**

After the rebase loop finishes (git-ops returns `DONE`), run symbol-survival analysis over
every file touched by the replayed range - both conflicted (already handled by P8) AND
merge-clean-but-feature-touched files (the silent-break risk: no conflict marker, but base
may have renamed/moved/removed the symbol).

### Identifying feature-touched files (delegated to Explore)

Dispatch `Explore` (read-only) to enumerate the files the replayed range touches; it runs the
bounded read below and returns the sorted file list. The orchestrator does NOT read the diff
inline:

```bash
# All files touched by the replayed range (relative to old-base)
git diff --name-only <old-base>..<feature-ref>
```

This list is the complete file set for the symbol-survival, import-resolvability, and collection
gates below.

### Symbol-survival check (delegated)

Dispatch Explore + OSM `entity_lookup` over the feature-touched files per
`[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`)
Sections 1-2.5 - adapted for rebase context (the orchestrator records the verdict only, never
reads diffs inline):

- Ground: the SHARED-SERIES base HEAD (`<new-base>`) - NOT a cross-version diff.
- For each symbol the replayed range imports, calls, or references: confirm it exists
  at `<new-base>` HEAD with the expected name, type, and module. Seven autosilent break
  classes from `[[fp-symbol-survival-check]]` apply unchanged (renamed, moved, retyped,
  split, merged, removed, now-internal).
- A symbol absent/renamed/retyped at base HEAD is a **BLOCKER**: it auto-merged with
  no conflict marker and will crash at runtime. Resolve each blocking symbol back into
  its 4-outcome bucket (outcome b/c/d typically) and re-stage the file before P9.
- Record all findings in `verify.md` § symbol_survival.

### Import-resolvability gate (pyflakes F821)

Run `pyflakes` over every feature-touched `.py` from the Explore list. Any `F821` (undefined name)
is a broken import that survived the clean merge and MUST be resolved (4-outcome bucket) before P9.
This is the same check as `[[fp-symbol-survival-check]]`
(`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`) Sections 2.5(d) and 2.5(e), and it
applies to SAME-SERIES rebases too: an import valid at the old base can have been removed within
the series at the new base (e.g. `from odoo.tools import relativedelta`, valid in 17.0, removed in
18.0 - the same class of within-series removal occurs between two same-series bases). Dispatch this
to `Explore` (read-only) - the delegate `[[fp-symbol-survival-check]]` § Who runs this check assigns
to a static lint lane; the orchestrator records the PASS/FAIL verdict only.

```bash
pyflakes <every-feature-touched-.py-from-the-Explore-list>   # any F821 = blocker
```

### Collection acceptance gate (delegated to `Explore`)

After all symbol-survival + import-resolvability blockers are resolved, dispatch `Explore`
(read-only) - the delegate `[[fp-symbol-survival-check]]` § Who runs this check assigns to this
class - to run the test-collection gate and return a compact PASS/FAIL plus one line per collection
error; the orchestrator records the verdict only and never reads the diff or log inline:

```bash
# Odoo test collection (replace with pytest --collect-only for non-Odoo test runners)
# Must show zero collection errors - a setUpClass crash means tests never ran.
python -m pytest --collect-only <feature-touched test files>
# OR via odoo-bin for TransactionCase/HttpCase tests. Pick the flag by DB freshness:
#   -i <modules> on a FRESH <db> (modules not yet installed - the usual collection-gate case);
#   -u <modules> on a REUSED/already-installed <db> (-i on an installed module is a no-op).
#   Confirm flags via cli_help; see ${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md
#   Memory-cap policy: ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d <db> --test-enable --stop-after-init -i <modules> \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296} 2>&1 | grep -E "ERROR|error"
```

**ACCEPTANCE GATE (HARD):** collection must complete with `0 failed, 0 error(s)`.
`0 failed, N error(s)` is **NOT a pass** - a `setUpClass` crash or import error means
the tests never ran and the collection gate has not been satisfied. Resolve all errors
before proceeding to P9. This gate is the same as forward-port P7 collection gate.

---

## P9 - Test forward (per touched module)

Launch the `odoo-test-writer` agent (adapt mode; it authors by invoking the `odoo-test-writing`
skill inline) for each module whose behavior changed, then invoke the `odoo-coding` skill (via the
Skill tool) until GREEN - `odoo-coding` owns the coder fan-out + model (do NOT dispatch raw
`odoo-coder`, `odoo-backend-coder`, or `odoo-frontend-coder`). Test-adapt brief:

```
DISPATCH MODEL: <adapt_tier>
TASK: Adapt the branch's own tests to the new-base idiom for module <module>.
MODE: adapt (RED first, then GREEN)
INTENT_FILE: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md
TARGET_SERIES: <series>
NEW_BASE: <new-base branch>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve; `<ISOLATE_DIR>` keys on the enclosing repository root, so a leaf that resolves it from inside rb-integration writes into that worktree's own tree>
RULE: Forward the source test as the behavioral oracle. Adapt API to target idiom
      (base class, imports, helper signatures). Confirm RED before writing the fix.
      Do NOT write a brand-new test if the source commit shipped one - adapt it.
```

---

## P9b - Code-review loop (in-pipeline; fix-until-clean before verify)

Goal: catch review-class defects in the just-adapted diff BEFORE the P10 verify, fixing in a loop
until no CRITICAL/HIGH remains. Two review points exist: this in-pipeline loop and the final P12
review of the whole integration worktree, which runs ahead of the PR - do NOT remove P12.

Dispatch (orchestrator -> Skill tool, full delegation):

```
SKILL: odoo-code-review
TARGET: worktree:<WT_ROOT>/rb-integration
SCOPE: the replayed/adapted commits only (the rebase has produced rb/<slug>); attribute every
       finding to a replayed/adapted line - a finding on a pre-existing base line is OUT of scope
       (do not re-rate base debt as a rebase regression).
SERIES: <series>
ASK: severity-graded findings (CRITICAL/HIGH/MED/LOW) + corrected version. Odoo-specific failure
     modes (ORM-hook order, singleton, super() safety, N+1, view/XPath) are in scope.
```

`odoo-code-review` runs its own scoper (Phase 0) over the git target + fans out reviewers.

Loop + escalate:
1. Read findings. No CRITICAL/HIGH -> gate PASS, write `<sha>: reviewed`, proceed to P10.
2. CRITICAL/HIGH present -> dispatch `odoo-coding` with the findings as the fix brief:
   ```
   ODOO VERSION: <series>
   WORKTREE_PATH: <WT_ROOT>/rb-integration
   SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
   ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
   ADAPT TIER: <same tier as the P8 adapt for these files>
   FIX BRIEF: <the CRITICAL/HIGH findings + reviewer's corrected version>
   RULE: fix to the finding's root cause only; do not expand scope; keep tests GREEN.
   ```
   Then RE-REVIEW (step 1). Record MED/LOW in `rebase-log.md` for P12, do not block on them.
3. Cap = 3 review->fix iterations. 3rd iteration still CRITICAL/HIGH -> STOP, escalate BLOCKED
   per ETHOS #7 with the failing finding + diff. Never relax the severity bar to pass the gate.

The gate is automated (fix-until-clean), not a human STOP - human STOP-gates stay at P11/P12.

---

## P10 - Verify

### range-diff + dup-guard (always)

#### P10 pre-step: git-ops range-diff

Invoke git-ops to produce the range-diff before odoo-diff-comparator:

```
TASK: produce range-diff for rebase outcome verification
scope: <old-base>..<feature-ref-tip> vs <new-base>..<rb-tip>
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
diff_path: <ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt
intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/
PLAN: <ISOLATE_DIR>/git-rebase/<slug>/plan.md
STEPS:
  1. Read the file at diff_path (the range-diff output produced by the git-ops pre-step above).
  2. For each P4 intent: confirm it is present and semantically unchanged in the rb branch.
  3. Duplicate-behavior guard - for each feature's key identifier (field name, model name,
     method name, xmlid):
     a. PRIMARY (hard fail): call OSM `entity_lookup` for the identifier and count
        definitions across the FULL INHERITANCE CHAIN (all modules). If count >1,
        this is a HARD duplicate failure - flag as dup_findings. A feature re-added by
        the rebase that base ALSO added in a DIFFERENT module (classic core-absorption)
        will have count >1; grep scoped to one module path misses this.
     b. SECONDARY (locator): grep the rb-integration worktree within the relevant module
        path to locate the definitions. This is a locator only, not the dup signal.
     Flag any identifier with OSM count >1 as a definitive duplicate; flag count=0
     (symbol removed at base) as a symbol-survival miss that should have been caught at P8b.
EMIT: <ISOLATE_DIR>/git-rebase/<slug>/verify.md
FORMAT:
  range_diff_verdict: pass|fail|warn
  intent_survival: [{sha, present: true|false, note}]
  duplicate_findings: [{identifier, osm_definition_count, paths[], note}]
  overall: pass|fail
```

### B3 - conditional instance verify

Provision ONE instance via the `odoo-instance` skill ONLY when the rebased range touches ANY of:
- A model field add, remove, rename, or type-change
- A stored compute or constraint
- An ORM `create` / `write` / `unlink` override
- A `migrations/` directory
- A test that subclasses `TransactionCase` or `HttpCase`

Skip for pure-frontend (JS/OWL/SCSS), docstring/label/comment-only, or non-DB-stateful ranges.
The orchestrator decides from `recon.md` commits[].modules[] + P3 comparison metadata.

The `odoo-instance` skill owns provisioning (port allocation + leasing). The orchestrator captures its
canonical output block ONCE as the run's `INSTANCE_HANDLE` and forwards that handle as an
`INSTANCE_HANDLE:` field in EVERY downstream verify / coder / test brief - downstream agents consume
the provided handle, never invent a DB or a port, and never re-derive `addons_path` from the catalog.
The DISPATCHER owns addons provenance: whenever a brief names a `WORKTREE_PATH`, acquire with
`--addons-path-override` so the instance loads THAT worktree, or authorize
`SELF_PROVISION: worktree-addons`. One instance per run; release it via its `lease_token` at the end.
Contract, including the carve-out and the coverage assertion:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

Instance lifecycle protocol: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md`.
Test invocation conventions: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.
Resolve odoo-bin flags for the target series via `cli_help` before invoking - flags differ
per series (e.g. v19 namespace bootstrap); always pass `odoo_version=<series>` to `cli_help`.

---

## P11 - Gate (human-confirm)

Present `rebase-log.md` + `verify.md` to the human. STOP. Do NOT push, do NOT open a PR
until the human explicitly confirms. Confirmation in Plan Mode UI or as a plain message both
count. If the human requests changes, re-enter the relevant phase (P8 for resolution fixes,
P9 for test failures) before re-presenting.

---

## P12 - Final review + PR

Stage order inside this phase is the **Terminal stage order** constant
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail, its ONE
owner): review -> push -> open PR. Do not reorder it locally.

**Step 1 (FIRST) - final code review of the integration worktree, BEFORE any push or PR.**
Delegate a code review passing `TARGET: worktree:<WT_ROOT>/rb-integration`. This review can force
CODE CHANGES, so it must clear first - fix CRITICAL/HIGH findings on that worktree (dispatch
`odoo-coding` at the P8 ADAPT tier, the SAME loop shape as § P9b) and review again until none
remains; MED/LOW are recorded in `rebase-log.md`. Only when the review returns no CRITICAL/HIGH do
steps 2-3 run.

**Step 2 - push.** Resolve the fork remote name and upstream org/repo from
`git remote get-url origin` (bounded read, inline). Never hardcode the fork remote or upstream repo.

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push rb/<slug> to the fork remote:

```
op: push rebase branch to fork (never to the upstream directly)
scope: rb/<slug>
worktree: <WT_ROOT>/rb-integration
remote: <fork-remote-name>  # resolved from git remote get-url origin
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

**After the PR opens, only PR-OBSERVING work remains** - CI-failure triage and the human merge (the
constant's post-PR band). Do NOT delegate another worktree code review here: step 1 above already
cleared it, and a code-changing review on an open PR is exactly what makes the PR churn.
Wait for human merge. NEVER squash commits. The `rb/<slug>` branch must merge as-is; the
orchestrator does not rewrite commit messages (an outcome-(a) skip records the reason in
`rebase-log.md`, not in a commit).

---

## rebase-log.md format

```markdown
# Rebase log - <slug>

| sha | subject | outcome | failure_mode | evidence | adapt_tier | status |
|-----|---------|---------|-------------|---------|-----------|--------|
| abc1234 | add double-post guard | (b) | renamed | `_post`->`action_post` at `account/models/account_move.py:123` | sonnet | resolved |
| def5678 | fix typo in docstring | (a) | already-present | patch-id match on new-base | haiku | skipped |
| ghi9012 | OWL widget refactor | (c) | override-refactored | `ListRenderer` replaced by `ListController` | fable | designed |
```

---

## intake.md format

```yaml
feature_ref: 17.0-feat-double-post-guard
feature_worktree_path: <WT_ROOT>/rb-feature-<slug>
new_base: 17.0
same_series_ok: true
pr_resolved_from: https://github.com/<org>/<repo>/pull/482
branches_to_materialize: []
open_questions: []
```
