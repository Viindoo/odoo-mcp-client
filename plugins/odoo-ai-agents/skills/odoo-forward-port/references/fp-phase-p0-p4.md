# Forward-Port Pipeline - P0 to P4 (recon, intent, classify, design, plan gate)

**Contents:** P0 - P1 - P2 (incl. upgrade-scale gate) - P3 - P4 (plan.md template)

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete
`odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).


---


## P0 - Recon & triage (read-only, NO stop)

**Target clone.** The checkout the target series builds from hosts every git step of the run and
the integration worktree. Call `catalog_read` with the target series, and `repo_facts` on the
repository the request names and on each `addons_path` entry of that series' rows: the row with an
entry inside a checkout whose `origin_url` equals this repository's names `TARGET_CLONE` (that
checkout's `principal_root`). The catalog declares the target series but no row covers a checkout
of this repository: `NEEDS_CONTEXT(target clone)` - the build steps could not load the port. No
row of the target series at all: `TARGET_CLONE` is the repository the request names; say so in
the plan. Every git-ops request of this run carries `repo: <TARGET_CLONE>`.

Resolve the ISOLATE state dir once for this run: call `mcp__plugin_odoo-ai-agents_odoo-local__project_dir` with axis `isolate` and
`cwd` = `TARGET_CLONE`, and substitute the returned absolute path for `<ISOLATE_DIR>` below.

1. Resume: read any existing worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) and
   `<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json` (`{<sha>: status}`) when they exist. Skip ONLY
   `status=done`; a `designed` commit resumes at the P4 plan gate with its recorded `design_doc` (no
   re-design); `extracted` resumes at P2; `adapted` resumes at P9.
   "one-shot" / "one-time" in a request means ONE RUN, not a different git shape: never a licence to
   cherry-pick; to land only part of the branch, pass that sub-range's TIP SHA (Hard rule 2).
2. Enumerate the commits to forward (read-only; no worktree, no branch yet) with ONE git-ops request.
   A source ref `TARGET_CLONE` cannot reach is brought in first: the request asks for the source
   branch to be fetched, from the source repository added as a remote when the source is another
   repository. Results, all written to
   `<ISOLATE_DIR>/forward-port/<slug>/range.md`:
   - `merge_base:` - the merge base of `<target-branch>` and the source ref (the fetched source
     branch on a cross-repo port); later phases read it from this file.
   - the non-merge commits after it up to the source ref, oldest first, narrowed by the `--scope`
     paths and the `--since` SHA when the user gave them (`--scope` default = all modified modules in
     the range; `--since` = only commits after this SHA, an incremental or resumed run);
   - `unnamed:` - the commits the request did not name (colleagues' included): the merge of the
     source TIP lands every commit above the merge base, so the real scope is the merge base plus
     these commits;
   - per commit, the files it touches with their change statistics (the input of the EXTRACT-tier
     triage below);
   - `modules:` - per touched module (the directory holding the descriptor above each touched
     path), `installable`, `auto_install`, `application` and `version` as its descriptor states
     them at the target ref and at the source ref (`<tgt-descriptor>` / `<src-descriptor>`, Hard
     rule 11); `absent` where the descriptor is not on that ref;
   - `conflicts:` - the files a merge of the source ref into `<target-branch>` would conflict on,
     forecast without changing a branch, an index or a working tree.

   Nothing else of P0-P4 needs git: the triage gate, the P2 installable state and the P4 plan
   read these rows.

Map each `--scope` module name to its directory path before requesting git-ops to filter
by path (module `l10n_vn` -> `l10n_vn/`; resolve via manifest location - may be at repo root
or under an addons subdir, e.g. `addons/l10n_vn/`).

**Group by module first (R2a).** `range.md` lists the touched files per commit for every commit in
the range; map each touched path to its owning
module (same resolution rule as `--scope` above). Build `module -> [ordered sha list]`
(chronological, oldest first); a commit touching 3 modules appears in each of the 3 modules' lists.
This map is what P1 dispatches over.

For each MODULE's commit bundle, triage the EXTRACT tier INLINE (the change statistics in `range.md` for every
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
never narrated) carrying that module's FULL ordered commit list, at `model` = the module
bundle's triaged EXTRACT tier (`references/fp-triage-table.md` Table 1) and `effort` per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.
Concurrency: Mode B budget (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`; the budget
counts MODULES in flight, not commits). No child worktree. Retry rules (resume the SAME instance;
Tier-C superseding replacement): `references/fp-phase-briefs.md` § P1 - one extractor per module (R2b).

Pre-step (once before the parallel dispatch): invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a batch pass to write per-commit dump files. For each commit SHA in the range:

- op: write the commit's full message and diff for the sha
- `output: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`

Group the resulting `{<sha>: <abs-path>}` map by module (the P0 map) into each brief's
`commit_dump_paths`. A commit shared between two modules goes to both extractors, so the brief's
`SLUG` is `<slug>/<module>`; the dump paths stay under the run-level `<slug>`.

Brief (run-specific inputs only):

```
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

Every Odoo Semantic call carries `odoo_version=` - never omit it. Assign exactly one bucket a/b/c/d per `[[fp-intent-4outcome]]`. Append one row per commit to `merge-log.md` (intent / bucket / reason / evidence -
no blank Reason or Evidence cell). A C3 row uses the canonical record of
`[[fp-merge-absorption]]` § C3. `odoo-version-diff` forward-port mode supplies the per-symbol
bucket suggestion when the diff is large. Refine the commit's ADAPT tier now that the bucket is
known (bucket a/d -> haiku, test-only).

**Bucket-(c) upgrade-scale gate.** Once buckets are known, estimate each bucket-(c) cluster; an
upgrade-scale re-implement (not a mechanical port) gets the `upgrade-scale` flag RECORDED now
(`references/fp-triage-table.md` § Bucket-(c) upgrade-scale defer-or-do gate). Do NOT STOP at P2:
the flag becomes a defer-or-do line in the P4 plan. A `(b) do now` cluster that ALSO meets the P3
non-trivial criterion proceeds to P3 design before P4.

**Installable state (TARGET CLEAN-TIP rule).** For each touched module, take its `installable` flag
at the target ref from the `modules:` rows of `range.md` and decide per
`[[fp-installable-false]]` § Discriminator. Record `installable_false=yes|no` as the module's OWN
row in `merge-log.md`, keyed by module and distinct from the per-commit rows - the ONE field any
later phase reads for its installable state.

DISPATCH the read-only haiku leaf `odoo-installable-prober` only when the SOURCE HISTORY is also
needed (the range does not touch the module's descriptor and the target state is unclear). The
prober is a `role: leaf` that cannot fetch its inputs: for each module it probes, invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files:

- `manifest_path`: read `<module>/<tgt-descriptor>` at `target_ref` and write to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/manifest.py`
- `history_dump_path`: the history, as patches and following renames, of the commits that modified
  `<module>/<src-descriptor>` (the SOURCE side's name) up to `source_ref`, written to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/history.diff`

Dispatcher inputs (CANONICAL CONTRACT - pass exactly these keys):

```
{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }
```

- `repo_root` is the MAIN checkout root where git runs (the `repo_root` of a `repo_facts` call; the
  integration worktree does not exist at P2); populate it from the P0-recorded checkout root. For a cross-repo port it is the main clone
  that has the source remote added + fetched in the P0 bootstrap.
- `source_ref` / `target_ref` are the refs P0 enumerated.
- `target_version` is the concrete target series for OSM grounding.
- `manifest_path` / `history_dump_path` are the absolute paths of the two files above; both are mandatory.

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
designed; the REAL SCOPE of the merge (the merge base and every commit the request did not name,
colleagues' included, that the tip merge lands); and the ABSORPTION topology: how many batches, each
batch's `<src-first-SHA>..<src-tip-SHA>` range and so how many merge commits the run produces. State
that number explicitly (the human's ONLY chance to choose a multi-batch split; the default is ONE
batch = ONE merge commit, never derived from the commit count). The plan also carries one
`Docs: <module | site | both | none> - <facts>` line: the documentation target of the closing step,
taken from `odoo-intake`'s Documentation routing facts in the brief, or decided here by that rule when
none came (ask only on a miss), with the finding count of
`${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md` for a target other than `none`;
`refine: no docs` drops it.

`EnterPlanMode` MUST come before any branch, worktree, or file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched FROM B (Hard rule 1 - no branch before this point). Describe the op (dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):

```
op: create integration worktree
repo: <TARGET_CLONE>
scope: branch fp/<slug>, base <target-branch>
worktree: <path>/fp-integration
```

THEN write `<ISOLATE_DIR>/forward-port/<slug>/plan.md` as the resume RECORD. MODULE-FIRST: one
block per touched module, that module's commits nested inside it in the module's own order:

```markdown
# Forward-port plan: <source-series> -> <target-series> (<slug>)
Real scope: merge base <sha>; unnamed commits landed by the tip merge: <shas | none>
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
