<!-- Reference for `odoo-forward-port` § The pipeline: per-phase git commands, dispatch-brief templates, worklog formats. -->

# Forward-Port Pipeline - per-phase execution detail

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete
`odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).

---

## P0 - Recon & triage (read-only, NO stop)

Resolve the ISOLATE state dir once for this run: call `mcp__plugin_odoo-ai-agents_odoo-local__project_dir` with axis `isolate` and
`cwd` = the target repo root, and substitute the returned absolute path for `<ISOLATE_DIR>` below.

```bash
# 1 - resume: read prior state, skip done commits
cat "<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json" 2>/dev/null   # {<sha>: status}

# 2 - enumerate the commits to forward (read-only; no worktree, no branch yet)
# Same-repo (both refs on origin): compute merge-base locally
MB=$(git merge-base <target-branch> <source-ref>)
# Cross-repo: invoke git-ops (add source remote + fetch), then compute:
#   MB=$(git merge-base <target-branch> source/<branch>)
# Invoke git-ops: enumerate commits (--no-merges, range MB..<source-ref>,
#   apply --scope <paths> / --since <date>); git-ops writes the commit list.
```

Map each `--scope` module name to its directory path before requesting git-ops to filter
by path (module `l10n_vn` -> `l10n_vn/`; resolve via manifest location - may be at repo root
or under an addons subdir, e.g. `addons/l10n_vn/`).

**Group by module first (R2a).** Invoke `git-toolkit:git-ops` (read-only) to list touched files
per commit (`--name-only`) for every commit in the range, then map each touched path to its owning
module (same resolution rule as `--scope` above). Build `module -> [ordered sha list]`
(chronological, oldest first); a commit touching 3 modules appears in each of the 3 modules' lists.
This map is what P1 dispatches over.

For each MODULE's commit bundle, triage the EXTRACT tier INLINE (`git show --stat <sha>` for every
commit in the bundle; for an override-depth question, one `find_override_point` probe) per
`references/fp-triage-table.md` Table 1 - the tier is the HIGHEST-priority row any commit in the
bundle matches; triage inline, never dispatch an agent to decide a dispatch.

Recon only: NO gate, NO `plan.md`, NO branch, NO worktree. Write the per-commit EXTRACT tier
and the range facts to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md` per
`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` (each commit's row carries the
tier its module's bundle resolved to), then READ that file back at the start of P1; a resumed run
must not re-triage the range.

---

## P1 - Intent extract (PARALLEL, READ-ONLY, MODULE-SCOPED)

**BAN (R2b): dispatch ONE `odoo-intent-extractor` per MODULE, never per commit.** Walk the P0
`module -> [ordered sha list]` map; for each module, launch exactly one subagent (real tool calls,
never narrated) carrying that module's FULL ordered commit list. Set BOTH the `model` parameter
(the module bundle's triaged EXTRACT tier, `references/fp-triage-table.md` Table 1) and the brief.
Concurrency: Mode B budget (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`; the budget
counts MODULES in flight, not commits). No child worktree. Retry rules (resume the SAME instance;
Tier-C superseding replacement): `SKILL.md` § P1.

Pre-step (once before the parallel dispatch): invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a batch pass to write per-commit dump files. For each commit SHA in the range:

- op: full-patch commit show (full message + diff) for the sha
- `output: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`
- `repo: <main-checkout-root>`   (cross-repo ports only)

Collect the `{ <sha>: <abs-path> }` map before dispatching any extractor, then group it BY MODULE
using the P0 `module -> [ordered sha list]` map to build each module's `commit_dump_paths`. Every
extractor brief MUST include `commit_dump_paths` (the module's ordered map).

**SLUG is PER-MODULE here, never the bare run slug.** A commit shared between modules A and B is
dispatched to BOTH modules' extractor instances. Set the brief's `SLUG` field to `<slug>/<module>`.
`commit_dump_paths` stays keyed by the run-level `<slug>`.

Brief (run-specific inputs only):

```
DISPATCH MODEL: <extract-tier>            # the MODULE bundle's tier, per Table 1
MODULE: <module-name>
commit_dump_paths:
  <sha1>: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha1>.dump
  <sha2>: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha2>.dump
  # ... every sha touching this module, oldest first
SOURCE SERIES: <source series>
SLUG: <slug>/<module>              # PER-MODULE namespace for this extractor's intents/ writes
TASK: Extract business intent + behavioral contract for every commit in commit_dump_paths
USER LANGUAGE: <lang | omit when English>
```

Aggregate every returned summary (`sha / intent_file / intent_one_liner / symbols /
4_outcome_hint / grounded` - one per commit; P2/P3/8b read the returned `intent_file` path) into
the P2 classify queue. Mark each commit `status=extracted` in `checkpoint.json`.

---

## P2 - Classify + installable-probe (module-first order, per-commit bucket, OSM)

Walk modules in the SAME order the P0/P1 map established, and within each module walk its commits
in that module's own order (R2a); the bucket decision stays per-commit.

```python
set_active_version(odoo_version='<target_version>')              # pin target; reachability probe
api_version_diff(symbol='account.move._post', from_version='<source_version>', to_version='<target_version>')
model_inspect(model='account.move', method='summary', odoo_version='<target_version>')
```

Assign exactly one bucket a/b/c/d per `[[fp-intent-4outcome]]`. Append one row per commit to `merge-log.md` (intent / bucket / reason / evidence -
no blank Reason or Evidence cell). C3 escalations use the canonical row
`<sha> | C3 | source issue <ref|DEFERRED> | <evidence one-liner>`. `odoo-version-diff` forward-port mode supplies the per-symbol
bucket suggestion when the diff is large. Refine the commit's ADAPT tier now that the bucket is
known (bucket a/d -> haiku, test-only).

**Installable-probe (TARGET CLEAN-TIP rule).** For each touched module, resolve its `installable` flag
at the target clean-tip (BEFORE merge) by reading `<module>/<tgt-descriptor>` at `target_ref` - written
by git-ops (read-only) to `manifest_path` in the pre-step below, which runs for EVERY touched
module. `<tgt-descriptor>` and `<src-descriptor>` are the per-side descriptor filenames SKILL.md
Hard rule 11 resolved once. An absent `installable` key means installable; an absent FILE means the
module is not on the clean tip.

DISPATCH the read-only haiku leaf `odoo-installable-prober` only when the SOURCE HISTORY is also
needed to disambiguate category 3 (manifest NOT touched by the forwarded commit range and target
state unclear). Record `installable_false=yes|no` in `merge-log.md` for the module - the ONE field
any later phase reads for its installable state.

Pre-step (for EVERY touched module): invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files. For
cross-repo ports include `repo: <main-checkout-root>`:

- `manifest_path`: read `<module>/<tgt-descriptor>` at `target_ref` and write to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/manifest.py`
- `history_dump_path`: run a log-with-patch of manifest modifications (--follow --diff-filter=M
  on `<module>/<src-descriptor>` - the SOURCE side's name) against `source_ref` and write to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/history.diff`

Assign the resulting absolute paths before launching the prober (both fields mandatory).

Dispatcher inputs (CANONICAL CONTRACT - pass exactly these keys):

```
{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }
```

- `repo_root` is the MAIN checkout root where git runs (the integration worktree does not exist at
  P2); populate it from the P0-recorded checkout root. For a cross-repo port it is the main clone
  that has the source remote added + fetched in the P0 bootstrap.
- `source_ref` / `target_ref` are the refs P0 enumerated.
- `target_version` is the concrete target series for OSM grounding.
- `manifest_path` / `history_dump_path` are absolute paths to the pre-step files.

The prober consumes those and returns BOTH:

- `merge_log_line:` - a single-line verdict logged VERBATIM to `merge-log.md`.
- a structured verdict block - `{ module, installable_false: yes|no, evidence }`. A probe that
  cannot resolve returns `status: BLOCKED`, never a degraded verdict.

**merge-log row placement.** Place the prober verdict under a dedicated `## Installable probes`
heading (one row per probed module), distinct from the per-commit rows.

**Routing the verdict.** `installable_false: yes` means the module lands `installable: False` ->
lint-only lane, SKIPping the extract/adapt logic tiers; `no` means it takes the normal lane. SSOT:
`[[fp-installable-false]]`. A `BLOCKED` probe is not
a verdict: resolve the missing input (`manifest_path`) and re-probe, or carry the module to the P4
plan gate as a FLAGGED row needing explicit human confirmation before its merge - never coerce it
to yes or no.

---

## P3 - Design (conditional route-out)

A bucket-(c) "do now" commit that touches a NON-TRIVIAL module routes OUT to
`odoo-solution-design` instead of being adapted blind (the non-trivial criterion
`odoo-solution-design` applies). A deferred or `installable:False` module needs no design.

Emit the Continuation Contract and YIELD (the plan runner advances the hop). This block is the
SSOT for the P3 payload:

```
next: odoo-solution-design
inputs:
  return_to: odoo-forward-port
  design_slug_hint: <slug>-fp-<sha>
  target_version: <target>
  modules: [<module-name>, ...]
  intent_records: [<ISOLATE_DIR>/forward-port/<slug>/<module>/intents/<sha>.md, ...]
    # one entry per module in `modules` above (§ P1 write path), never the bare run-slug intents/<sha>.md
  classification: <bucket-(c) summary>
  design_proposals: [<verbatim finding line>, ...]
    # structural changes this pipeline PROPOSES but never decides, carried verbatim: the P7
    # view-topology `VIEW-TOPOLOGY | ... | action: merge-into-base | ...` finding line.
    # `[]` when there is none - the key is ALWAYS present. A `NEEDS-HUMAN` view-topology line
    # NEVER travels here: it is presented at the P12 human gate.
```

**Routing a proposal when no commit routes to P3.** A `merge-into-base` line raised on a bucket-(b)
commit is never applied unapproved: when this batch emits no P3 hop, raise one whose `classification` reads
`view-topology proposal only (no bucket-(c) design)` and whose `modules` is the proposing module -
`design_proposals` is never dropped for want of a carrier.

`<slug>` is the run slug (`<source-series>-to-<target-series>`); `<sha>` the short SHA of the
routed commit.

`odoo-solution-design` under `return_to` emits `next: odoo-forward-port` with `design_doc: <path>`.
On re-entry, read `design_doc` from the returned contract's `inputs`, record it against the commit,
set checkpoint `status=designed`, and proceed to the P4 plan gate with the design linked - do not
re-run design. If `design_doc` is ABSENT, set the commit back to `status=extracted` and re-enter P3
next run.

---

## P4 - Plan gate (Plan Mode)

The request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request):
`EnterPlanMode`, present the plan, `ExitPlanMode` on approve. The plan CONTENT authored here (not
routed through `odoo-planning`) is MODULE-FIRST: module topology (each module's own ordered commit list from the P0 map);
per-module EXTRACT tier (the real triaged tier, `references/fp-triage-table.md` Table 1);
per-commit bucket (the real classification) and
ADAPT tier within that module; installable routing per module; design-doc link for any commit P3
designed; merge batches; the `Docs:` line (the documentation target of the closing step).

`EnterPlanMode` MUST come before any branch, worktree, or file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched FROM B (Hard rule 1 - no branch before this point). Describe the op:

```
op: create integration worktree
scope: branch fp/<slug>, base <target-branch>
worktree: <path>/fp-integration
```

THEN write `<ISOLATE_DIR>/forward-port/<slug>/plan.md` as the resume RECORD. MODULE-FIRST: one
block per touched module, that module's commits nested inside it in the module's own order:

```markdown
# Forward-port plan: <source-series> -> <target-series> (<slug>)
Absorption: <M> batch(es) -> <M> merge commit(s). Batch 1 = <src-first-SHA>..<src-tip-SHA> (<K> commits).
  (Default is ONE batch for the whole range; the commit count NEVER sets the merge count.)
Integration worktree: <path>  (branched from <target-branch>, B untouched)
Docs: <module | site | both | none> - <the facts that decided it>
Modules (<N>, after --scope/--since filter):

Outcome at target: (a) already in the target · (b) still needed, APIs compatible ·
(c) still needed, the old API is gone (re-implement) · (d) no longer relevant.

## Module: account_reports  (intent read at EXTRACT tier: sonnet)

| SHA | what it does | outcome at target | model that writes the port | ships on target? | design doc |
|-----|--------------|-------------------|----------------------------|------------------|------------|
| abc1234 | double-post guard | (b) APIs compatible | sonnet | yes | - |

## Module: report_engine_custom  (intent read at EXTRACT tier: sonnet)

| SHA | what it does | outcome at target | model that writes the port | ships on target? | design doc |
|-----|--------------|-------------------|----------------------------|------------------|------------|
| def5678 | new report engine | (c) old API gone - re-implement, do now | opus | yes | <SHARE_DIR>/designs/...md |

Deepest-reasoning rows (if any, ADAPT tier only - the EXTRACT table has no fable band): <module>: <sha> -
<why> (about 2x the cost of the tier below). (confirmed in Plan Mode)
Fable-declined / gate-suppressed downgrades (if any, ADAPT tier): <m>: opus (fable declined
| fable auto-downgraded - gate suppressed)
```

---

## P5 - Merge --no-commit (critical section) - ABSORB-ALL, runs ONCE per batch

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE for the batch's ENTIRE commit
range. Dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
For semantic conflicts use the stateless-resume recipe in that snippet.

`<src-tip-SHA>` = the batch's LAST (newest) source commit after the `--since`/scope filter;
`<src-first-SHA>` = its first. Resolve both from the P0 range map before dispatching.

```
# one merge of the range TIP
op: merge --no-ff --no-commit <src-tip-SHA>
worktree: <path>/fp-integration
```

To land only PART of a source branch, pass that sub-range's TIP as `<src-tip-SHA>`. A cherry-pick is
never the answer here (`SKILL.md` Hard rule 2).

**Never iterate this phase per source commit** (`SKILL.md` Hard rule 2). Only one merge in flight.
Do NOT commit - the working tree is the absorption zone for the whole range through P9. Full protocol incl. absorption window order:
`[[fp-merge-absorption]]`.

---

## P6 - Symbol-survival check (MUST, before adapt)

**Dispatched, never run inline** (`[[fp-symbol-survival-check]]` § Who runs this check). Sequence
the dispatches and record what comes back; do NOT run the conflict scan, the file enumeration, or
the OSM grounding in this context.

1. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for the conflict-marker scan AND the
   `<merge-base>..<src-SHA>` file list in ONE dispatch (--name-only; git-ops writes both to a
   findings file, filtered to non-empty entries, and returns the path). For cross-repo ports include
   `repo: <main-checkout-root>`.
2. Dispatch `Explore` (read-only, `model: haiku` on the launch) over that returned file list to ground every Odoo symbol it
   references (field / method / model / view ref / external-id / manifest depend / ORM chain)
   against the TARGET version, per `[[fp-symbol-survival-check]]` sections 1-2.5. Never issue the OSM
   calls here.
3. Record only what the delegate returns: any absent/changed symbol FORCES bucket b/c/d and bans
   leaving the auto-merged line unchanged; the `SYMBOL-BROKEN | <symbol> | <file>:<line> | bucket |
   evidence` finding list (an empty list `SYMBOL-SURVIVAL: clean` is a valid, desirable result); and
   the PASS/FAIL verdict. A non-empty list BLOCKS P8 on those files. Full contract:
   `[[fp-symbol-survival-check]]`.

**Run on `tests/` files too.** Apply the seven auto-merge-silent symbol classes from
`[[fp-symbol-survival-check]]` section 2.5; feed test files from the enumeration above through the
same grounding, do not filter them out.

---

## P7 - Pre-adapt drift scan (MUST, before the behavioral loop)

P7 is distinct from the P6 TEST-survival sub-check (OSM `tests_covering` / `test_coverage_audit`).
P7 uses the seven static symbol classes from `[[fp-symbol-survival-check]]` section 2.5 over two
lanes: (d) python-import + (e) AST-pyflakes + (g) ORM create/write dict-key run over ALL
merged-touched `.py` (production AND `tests/`); the remaining classes (a)(b)(c)(f) and the
collection ACCEPTANCE GATE apply to the `tests/` lane only. P7 blocks entry to P8 when test
collection itself would fail.

**Enumerate scope - two lanes. Dispatched, never run inline** (`[[fp-symbol-survival-check]]`
§ Who runs this check):

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to list files changed in range `<merge-base>..<src-SHA>` (--name-only;
git-ops writes the file list). Include `repo: <main-checkout-root>` in the dispatch for
cross-repo ports. From the returned list the delegate derives:

- **Lane 1** - ALL merged-touched `.py` (production AND `tests/`): the `*.py` entries.
- **Lane 2** - `tests/` only: the Lane-1 entries whose path contains `tests/`.

Dispatch the gates as read-only delegates and record only their verdict (delegate per class:
`[[fp-symbol-survival-check]]` § Who runs this check): the git-ops dispatch above enumerates the
files, and `Explore` (`model: haiku` on the launch) runs every static lane below. Lane 1
gets classes (d) + (e) (`py_compile` + `pyflakes`) AND (g) (ORM create/write
dict-key scan) over ALL .py - production AND tests; Lane 2 additionally gets (a) (b) (c) (f). Treat
F821 on a production file, and a (g) dead key on a production call site, as blockers.

Record findings as `SYMBOL-BROKEN | <symbol/path> | <file>:<line> | <class> | evidence` and
append to `merge-log.md`. These become the `BROKEN TEST-SYMBOLS` input to the P8 adapt brief.

**ACCEPTANCE GATE (collection clean) - mandatory before P8 starts:**

The gate is a `pytest --collect-only` run over the merged test files (no DB). Dispatch it to `Explore` (read-only, `model: haiku` on the launch), the delegate
`[[fp-symbol-survival-check]]` § Who runs this check assigns to this class. Brief it with: the
integration worktree path, the merged test file list Lane 2 produced, the exact command
`python -m pytest --collect-only <those files>`, and the instruction to return ONLY `PASS`, or
`FAIL` plus one line per collection error (`<file>::<node> | <error class> | <message>`) - never the
raw log. Record that verdict; never run the command, or read its log, in the orchestrating context.

**No ad hoc provisioning, in any phase.** When a `setUpClass` performs DB-dependent work that
`--collect-only` cannot exercise, do NOT acquire an ad hoc DB here - the ONLY provisioning path is
P9's `odoo-instance` dispatch. Record the residual as an open ACCEPTANCE GATE item on that test
file's `merge-log.md` row; P9's own run-tests result for that file is its true confirmation. The
`--collect-only` verdict still blocks P8 for every OTHER file it covers.

A collection failure means the tests NEVER RAN - `0 failed, N error(s)` is NOT a passing result.
Resolve every drift finding (P7 SYMBOL-BROKEN entries) before entering the P8 adapt loop.

**View-topology sub-check (bucket-(b)/(c) same-module inherit stacks).** Runs once a bucket-(b) OR
bucket-(c) commit's own adapt step lands or modifies an `ir.ui.view` record (INCLUDING a clean
auto-merge with no conflict marker), at the 8b adapt point; a finding line is triaged into
`merge-log.md` and confirmed before P10 commits. Buckets (a)/(d) are out of scope. A HIT is a
PROPOSAL only: the merge-and-delete outcome routes out through the P3 design gate to
`odoo-solution-design` and is applied solely when the returned `design_doc` adopts it. Full
predicate, the two non-defect exceptions, and the merge-unsafe escape: `references/fp-triage-table.md`
§ Bucket-(c) same-module inherit-view check.

---

## P8 - Adapt (code first, then tests; serial per-module; ALWAYS directly in the integration worktree)

Adapt the MERGED RESULT module by module, driven by the per-commit intent records; never re-open,
re-merge, or re-stage per source commit. Dispatch the adapt unit DIRECTLY in the integration
worktree (`<path>/fp-integration`) and process modules serially; a module touched by several commits
is adapted ONCE, against the combined merged result. Never create a per-module child worktree.

**Open-merge window.** From P5 (`--no-commit`) through P10 (`commit`), `MERGE_HEAD` is live in the
integration worktree: ONE window per batch, opened by P5 and closed only by P10. SSOT:
`[[fp-merge-absorption]]` § Absorption window (inside the ONE no-commit merge).

**One `odoo-coding` invocation per module.** Code is adapted FIRST, then the node's single test leg
forwards and adapts the module's source tests, proves each FP-delta test by breaking its rule, and
confirms absorption for each bucket-(a) commit
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). Launch no test author of your own.

**8a - ground the adapt brief.** Resolve the test-leg enrichment lines BEFORE the invocation:

```python
test_base_classes(odoo_version='<target_version>')                           # BASE CLASS (target)
find_test_examples(query='double-post guard on account.move', odoo_version='<target_version>')  # TARGET TEST EXAMPLES
```

`BROKEN TEST-SYMBOLS` is the subset of the P6 symbol-survival findings (plus any P7 drift finding) whose
`<file>` is one of this module's test files - copy those rows in verbatim; omit the line when empty.

**Bucket-(a) hunk map.** P5's merge keeps every cleanly-merged hunk of a bucket-(a) commit in the working
tree (`[[fp-merge-absorption]]` § Skip-code-but-still-absorb rule); the test leg takes those hunks
out of play first. For each bucket-(a) commit touching this module, dispatch `Explore` (read-only, `model: haiku` on the launch) with its commit dump
(`<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`) and `<path>/fp-integration`; it returns each hunk
as `<file>:<start>-<end>` in the merged tree, `conflicted` when the hunk sits inside conflict markers, or
`absent` when the merge left no trace of it (the target already carried the identical change). Carry the
result and the dump path on that commit's `BUCKET` line.

**8b - adapt the module** per bucket. Invoke the `odoo-coding` skill (via the Skill tool) with the
FP-ENRICHED brief (never raw `odoo-coder` or `odoo-frontend-coder`). **R2b at this leg: at most one
coder per module across the WHOLE run.** On the module's FIRST invocation omit the field and record
the coder's agent id `odoo-coding` reports in `plan.md`; on every LATER one carry it as
`WORKER_AGENT_ID: <id>` - never a string anyone invented; `odoo-coding` resumes that id
(`SKILL.md` § P8). The brief is identical on a fresh launch or a resume, and the Worktree path
never changes:

```
DISPATCH MODEL: <adapt-tier>
REQUEST: Adapt the forwarded intent to the target platform - code first, then the node's test leg
      forwards the SOURCE TESTS below. On a re-adapt, append the P9 failure output.
MODE: adapt
INTENT: <ISOLATE_DIR>/forward-port/<slug>/<module>/intents/<sha>.md   (one path per source
      commit in this batch touching the module; build to this, not the source diff)
BUCKET: <per sha: a (hunks <file>:<start>-<end>[ conflicted][, ...] | absent; dump <path>) - no
      adapt code: leave the clean hunks as merged, resolve a `conflicted` one to the TARGET side; the
      test leg runs the source test with the clean hunks out of play | b 3-way+adapt | c re-implement
      on target idiom | d skip-code>
SOURCE TESTS (READ/WRITE, in the integration worktree): <path>/fp-integration/<module>/tests/<test_file>[, ...]
      (merged working-tree content; for bucket (b) it may still carry conflict markers - the test leg
       resolves IN PLACE and writes the adapted result back to the SAME path. A bucket-(a) sha's source
       test is its absorption check; a re-bucket it reports goes on that sha's `merge-log.md` row)
BROKEN TEST-SYMBOLS: <the P6 / P7 SYMBOL-BROKEN entries that land in this module's test files -
      repair each, never forward them verbatim>
BASE CLASS (target): <signature from test_base_classes(odoo_version='<target>') for each source
      test's base class - the kwargs the target setUpClass/setUp actually accepts>
TARGET TEST EXAMPLES: <1-2 paths from find_test_examples(query='<feature>', odoo_version='<target>')
      that already test this behavior the target-idiomatic way>
COMMIT: caller   (make NO commit - the batch's merge window stays open; return the file list and
      the test leg's report; P10 commits the batch)
NEW MODULE: <yes | no>
DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>   (P3's route-out result)
MODULE SCOPE: <name>
  READ/WRITE (in the integration worktree, no separate child worktree): <path>/fp-integration/<module>/
    (merged content; for bucket (b) 3-way+adapt start from these files - they hold the
     auto-merged or conflict-marked state - and write ALL output back here, in place)
ODOO VERSION: <target>
WORKTREE_PATH: <path>/fp-integration   (the ONE root this dispatch works in; pass no
  INSTANCE_HANDLE)
RUN_ID: <this run's id>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - the SAME literal INTENT above was
  built from; never re-resolve>
WORKLOG: <slug> - read, then append.
CONSTRAINTS: C1 set the target version to max(M + 1, S) when the source bumped it; C2 retarget or
  forward a migrations dir by whether the target has the problem the script solves; C3 carry pre-existing source bugs faithfully, never inline-fix -
  ${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md
  [+ NEW MODULE yes: apply the installable:False checklist - ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md]
  [+ LINT-ONLY: the module is installable:False at the target - fix syntax/lint breakage only,
     adapt no business logic (8c-bis) - ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md]
WORKER_AGENT_ID: <id recorded for this module on its first invocation this run>   (omit on the
      module's FIRST invocation)
USER LANGUAGE: <lang | omit when English>
```

Store the return on the module's own `merge-log.md` row: the file list as `files: <path>, ...` (P10 stages
exactly this union), the test leg's brief per-test report (what it broke, how the test failed - one short
line each, free form), and any re-bucket the node reports as the new bucket + reason on that sha's row.
P9 adjudicates the report.

**8c - installable:False modules** - two sub-cases, same manifest action. (i) **New module** (absent
at target): `installable: False`, comment `auto_install`/`application`, lint-fix only.
(ii) **Upgraded-then-forwarded** (target clean-tip = `installable:False` but merge carries `True`):
re-set to False + re-comment `auto_install`/`application` with `# TODO: Uncomment when upgrading
module to production-ready status` breadcrumb - then lint-fix only. SSOT: `[[fp-installable-false]]`.

**8c-bis - installable:False at target = LINT-ONLY lane.** BEFORE dispatching the coder/reviewer
for any module, confirm its target installable flag. Re-read
`<module>/<tgt-descriptor>` at `target_ref` (via git-ops, read-only) only if the manifest was touched
by the merge; otherwise reuse the value P2 already resolved from `manifest_path`. If
`installable: False` at the target, brief
the coder in **lint-only mode**: run flake8 / eslint / prettier / ruff and fix ONLY syntax/lint
breakage to keep CI green - do NOT adapt business logic, do NOT upgrade content. Add the
`LINT-ONLY` clause to the 8b brief's `CONSTRAINTS` field, with the pointer
`[[fp-installable-false]]`. The single exception to "no logic change" is a syntax/lint error that
itself blocks the file from parsing.
When the merged `<tgt-descriptor>` now shows `installable:True` (upgrade-commit carried in)
but the target clean-tip was `installable:False`, re-set to False + re-comment
`auto_install`/`application` with the `# TODO: Uncomment when upgrading` breadcrumb before
dispatching the coder. SSOT: `[[fp-installable-false]]`.

**8d - migration script:** decide each forwarded `migrations/<src-series>.a.b.c/` dir per C2. First
the precondition: every module the script acts on is installable at the target tip; otherwise forward
the dir unchanged under its source-series name and record why on the sha's `merge-log.md` row. Then
read the script and the target's code and data model for that module: when the target has the
problem the script solves, retarget - rename to FULL `<tgt-series>.V`, `V` being the version C1 sets
for the module; when it does not, forward the dir unchanged and record why on the same row. Full
rule: `[[fp-merge-absorption]]`. After the rename, sweep the
migration body for source-series literals still in log strings or version constants:

```bash
grep -rn '<src-series>' migrations/<tgt-series>/
```

**8e - i18n: COMPUTE and RECORD; the dispatch happens at P9.5.** Do NOT dispatch `odoo-i18n` here.
Evaluate both mandate conditions now and record them on the module's `merge-log.md` row:

1. **Condition 1 - translatable delta.** Run the 8-signal trigger table over this batch's
   `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump` files. Record
   `i18n_signals: [<fired ids>]` or `i18n_signals: none`.
2. **Condition 2 - already live at the target.** Read `installable_false` from this module's
   `merge-log.md` row. Record `i18n_due: yes|no|escape:<E-id>`.

Both conditions and the escape table: `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`.
Carry `i18n_due` forward to P9.5. No convergence or worktree removal step here. Mark `status=adapted`.

---

## P9 - Verify by behavior (PER-BATCH, in integration)

Resolve odoo-bin flags for the TARGET series via `cli_help` (`odoo_version=<target>`) before
dispatching. Conventions: `docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`,
`docs/reference/ODOO-TESTING.md`.

**DELEGATE - never a bare lease tool or `odoo-bin` recipe.** Dispatch the `odoo-instance` skill
(via the Skill tool) for every step below; never a bare `lease_acquire` / `instance_build` /
`odoo-bin` call. Everything from here to P10 is CONTENT for that dispatch brief and the
adjudication you perform on the RETURNED `instance-ops` block.

**Env-bootstrap (before the first dispatch).** Resolve the CATALOG (principal-checkout) baseline
from the declared catalog row covering this repo (`addons_path` and `python` from `catalog_locate`
per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2) as a baseline only;
interpreter discovery and addons-path assembly are `odoo-instance-ops`'s job. A multi-repo stack
needs EVERY repo on disk: confirm every root in that entry's `addons_path` exists before
dispatching; a missing repo is `BLOCKED` (NEEDS_CONTEXT), not a test red.

**Worktree re-root (MANDATORY).** The catalog baseline is NEVER the addons_path this phase verifies
against. Dispatch `odoo-instance` with `WORKTREE_PATH: <path>/fp-integration`, which re-roots the
baseline onto that tree before acquiring. Do NOT hand-build the override and do NOT verify against
the catalog `ADDONS_PATH` directly. Before trusting any result below, assert the resolved addons
list contains `<path>/fp-integration/<module>/<tgt-descriptor>` for every module in this batch
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion) - on a
miss, `BLOCKED`.

**Install/verify the FULL transitive `depends` closure, not just the module you edited.**
Resolve the closure per module, then install/verify its breadth:

```python
module_inspect(name='account_accountant', method='dependencies', odoo_version='<target_version>')
```

Union the closures of every directly-touched module and pass that whole set as `modules` in the
dispatch below.

**Lint toolchain present BEFORE the lint gate.** Confirm `flake8 --version` and `ruff --version`
(and eslint / prettier for frontend) resolve in the verify env before relying on a green lint.

**Dispatch `odoo-instance` (via the Skill tool) - ONE ephemeral instance per BATCH, not per
commit.** First commit in the batch (fresh DB; install + test in one pass):

```
operation: run-tests
series: <target>
persist: ephemeral
RUN_ID: <this run's id>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
WORKTREE_PATH: <path>/fp-integration   # re-root per the Worktree re-root note above
modules: <union of the touched modules' full transitive depends closure, comma-separated>
test_tags: <`/<m>` for every module in that closure, comma-joined (narrowing rule below)>
mode: fresh
GATE_ROLE: node-verify    # a per-batch verify, never the run's pre-PR lint gate
skip_auto_install: true
CONFIRM: "confirm each module in this closure emits a Loading line before reading any test count;
          report per-module install status in modules_installed and the test result in findings_path"
```

Capture the returned `instance-ops` block as this batch's `INSTANCE_HANDLE` (`db_name`,
`lease_token`, `run_id`, `addons_path`). **Pass `test_tags`** (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`):
`/<m>` for every module in the INSTALL CLOSURE this batch named, comma-joined. NEVER narrow below
that to only the edited module. Record the tag set used in `merge-log.md`.

For a SUBSEQUENT commit in the SAME batch touching only a subset, re-dispatch `odoo-instance` with
the SAME `INSTANCE_HANDLE` forwarded, `mode: reuse` (`-u` semantics) and `GATE_ROLE: node-verify`
on the changed modules only
- skip re-running the full closure. Once a module is installed in this DB, re-running its tests
MUST use `reuse` (`-u`; `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an
existing database; confirm flags via `cli_help`). Full rule: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

Relay the returned `instance-ops` block (`log_path`, `findings_path`, `modules_installed`,
`failed`/`errors`/`warnings`/`skipped`) into `merge-log.md` verbatim (Hard rule 8). Reconcile
`modules_installed` against the installable scan (`[[fp-symbol-survival-check]]` section 2.5f): a
module that is `installable: False` at the target is EXPECTED to be absent from
`modules_installed` - route it to the 8c-bis lint-only lane and do NOT count its absence as a
break. A module that IS installable and absent from `modules_installed` is a real failure -
investigate via `log_path` before reading any test count.

**Recover a batch stuck mid-run.** Do NOT `pkill` an `odoo-bin` process. The batch's lease was
provisioned for THIS run, so you are its run-level owner
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): call `lease_release` with the
batch's cached `lease_token`/`run_id` - it stops the bound process group FIRST, then drops the DB.
Re-dispatch the Step above for a clean retry.

- **Whole module green:** the target suite must be green.
- **Every FP-delta test proven:** each newly-forwarded or adapted test was proven by its node's test leg -
  the report recorded on the module's `merge-log.md` row says what it broke and how the test failed
  (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`); a bucket-(a) commit's source test is
  instead confirmed absorbed (green on the target with the commit's own code out of play). A test with
  neither is unverified - resume the module's coder through `odoo-coding` (8b, `WORKER_AGENT_ID`) to
  produce it; never run a break of your own here.
- **Database freshness.** Never hand this handle to a P8 invocation; if a break ever ran on it,
  rebuild fresh when the break touched data files or schema.
- **Triage red:** Triage EVERY red against a clean-tip baseline before calling it a
  regression. Re-dispatch `odoo-instance` (same shape as above) against a clean checkout of
  the target tip - no `WORKTREE_PATH` override, no absorption - running the SAME closure. Red
  there too = pre-existing (record in merge-log.md, do not fix, do not block). Green on clean /
  red only after absorption = FP-delta (fix before committing). Never widen an assertion to hide a pre-existing failure. For source-series
  follow-through on a pre-existing red, apply C3 - carry faithfully + open a source issue
  (resolvable remote) or record it; see `[[fp-merge-absorption]]` § Triage / C3.
- **Baseline a failed INSTALL the same way.** If a module fails to install, re-dispatch
  `odoo-instance` against clean `origin/<target-branch>` (no `WORKTREE_PATH`, no absorption).
  Fails there too = a PRE-EXISTING break in the target series, NOT FP-introduced - record it in
  `merge-log.md` and do NOT block the forward-port on it. Only an install that is green on clean
  origin/target and red after absorption is an FP-delta to fix.
- **CREATEDB role:** on any acquire refusal follow `[[fp-merge-absorption]]` § Ephemeral isolation.

Full per-batch protocol: `[[fp-merge-absorption]]`. Mark `status=verified`.

---

## P10 - Conclude the merge (self-decided, per batch) - ONE commit closes the whole range

No human confirmation (a local merge on `fp/<slug>`; P12 presents it). Before the commit, build the FULL file list:
the union of every module row's `files:` (8b) plus the files P9.5's `odoo-i18n` result names.
Compare it with `git -C <path>/fp-integration status --porcelain` (bounded read): a modified or
untracked path in neither the list nor the merge's own staged set is work no step accounted for -
attribute it to its module (or remove it) before you continue. Then invoke the
`git-toolkit:git-ops` skill (via the Skill tool) ONCE:

```
op: stage these files, then conclude the merge with one commit
files: <the FULL file list above>
message: |
  fp: absorb <src-first-SHA>..<src-tip-SHA> - <one-line summary>

  <sha> <bucket x> <one-line reason>      # one body line per absorbed commit
  ...
worktree: <path>/fp-integration
```

After it returns, confirm the tree is clean: `git -C <path>/fp-integration status --porcelain` is
empty and `git -C <path>/fp-integration rev-parse -q --verify MERGE_HEAD` finds nothing (bounded
reads). A leftover path is a file the list missed - record it with the path in `merge-log.md` for P12;
never amend the merge commit.

That single commit lands the whole range; every SHA in the range is marked `done` in
`checkpoint.json`. Buckets (a)/(d) are absorbed by it too (Hard rule 7); their body line records the
bucket + reason.

**There is no P5 loop.** A single-batch run reaches P10 once, then P11. Only a human-approved
multi-batch split at the P4 plan gate returns to P5, once PER BATCH, never per commit, with the NEXT
batch's range TIP, then P6 -> P7 -> P8 -> P9 -> P10 for that whole batch. Never skip P5/P6/P7 for a
later batch.

---

## P12 - PR + review

Runs AFTER P11 (`SKILL.md` § P11): acceptance, then this review gate, THEN the PR opens
(`SKILL.md` Hard rule 9; `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail).

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push (resolve origin URL via `git remote get-url origin`):

```
op: push fp/<slug> to origin (NOT B)
scope: branch fp/<slug>
worktree: <path>/fp-integration
remote: resolve via `git remote get-url origin`
```

Run `odoo-code-review` inline (via the Skill tool) for the forward-port pitfall (a forwarded test
still coupled to the source API) on the pushed branch BEFORE the PR is created.

**Attribute every finding to the FP diff before rating it.** Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for a three-dot diff
(`origin/<target-branch>...fp/<slug> -- <file>`, only what the FP added to `<file>`).

A finding on a line NOT in this diff is pre-existing - note it separately, never block the PR on it.

**Per finding, apply C3 (fix old version first).** Check whether the same defect exists at the source
series. If it does, it is a **pre-existing source bug** (inherited - forwarded faithfully, not introduced
by this port): route the fix UPSTREAM via a source-series issue (invoke git-ops when a source
remote resolves via `git remote get-url`, else record it in `merge-log.md` + the Continuation Contract);
do NOT patch it inside the FP. Record `<sha> | C3 | source issue <ref|DEFERRED> | <evidence>` in
`merge-log.md` and carry it faithfully forward. EXCEPTION: a serious security/safety bug is fixed on the
destination immediately (still open a source issue). SSOT: `[[fp-merge-absorption]]` § Triage / C3.

**Field-existence question:** query that field directly instead of re-dumping the model:

```python
entity_lookup(kind='field', model='account.move', field='payment_state', odoo_version='<target_version>')
```

**installable:False modules get a LINT-ONLY review.** For any module that is
`installable: False` at the target (8c-bis lane), the reviewer rates ONLY syntax / lint findings - raise no business-logic findings against it; mark such findings out-of-scope.

Only once the review above is addressed, invoke the `git-toolkit:git-ops` skill (via the Skill
tool) to create the PR:

```
op: create PR
base: <target-branch>
head: fp/<slug>
title: "..."
body: "..."
remote: resolve from `git remote get-url origin`
```

**Cross-check every static-review bot comment on the PR (post-PR).** Once the PR is open and CI has
run, read the bot comments and resolve or consciously waive each; this never gates PR creation.

NEVER squash. B stays LOCKED - the PR adds only the merge commits. Present the PR URL, the review findings, and the P11 acceptance verdict
together, and wait for the human to merge.

---

## Cleanup (after human merge)

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to remove the integration worktree and delete the integration branch.

```bash
# Invoke git-ops:
#   op: worktree remove <path>/fp-integration
#   confirmed: yes - forward-port is merged
git worktree list          # confirm no dangling fp/<slug>-* child worktrees
# Invoke git-ops:
#   op: branch delete fp/<slug>
#   confirmed: yes - forward-port is merged
```

Confirm no instance of this run is still leased: call `mcp__plugin_odoo-ai-agents_odoo-local__lease_list`
with scope `run` and this run's `run_id`, and `lease_release` any lease the P9 instance release step left
behind - you are its run-level owner (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).

Leave `<ISOLATE_DIR>/forward-port/<slug>/` for the next run's resume.
