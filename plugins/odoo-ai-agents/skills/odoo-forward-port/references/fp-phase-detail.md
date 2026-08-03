<!-- Reference for odoo-forward-port/SKILL.md § The pipeline. Loaded as needed.
     Per-phase git commands, dispatch-brief templates, and worklog formats. The SKILL.md body
     carries the contract; this file carries the verbatim commands and brief text. -->

# Forward-Port Pipeline - per-phase execution detail

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit). Every Odoo Semantic call passes a concrete
`odoo_version=` (never a default; the pin is session-scoped state any other actor sharing this
session can overwrite - SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` §
OSM session-pin race).

---

## P0 - Recon & triage (read-only, NO stop)

```bash
# 0 - resolve the ISOLATE state dir once for this run
DIR="$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh" isolate)"

# 1 - resume: read prior state, skip done commits
cat "$DIR/forward-port/<slug>/checkpoint.json" 2>/dev/null   # {<sha>: status}

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
(chronological, oldest first); a commit touching 3 modules appears in each of the 3 modules' lists
(shared reference, never duplicated). This map is what P1 dispatches over.

For each MODULE's commit bundle, triage the EXTRACT tier INLINE (`git show --stat <sha>` for every
commit in the bundle; for an override-depth question, one `find_override_point` probe) per
`references/fp-triage-table.md` Table 1 - the tier is the HIGHEST-priority row any commit in the
bundle matches; the orchestrator triages the tier itself; never dispatch an agent to decide a
dispatch.

This is recon only. There is NO approval gate here, NO `plan.md` written, NO branch, NO worktree -
the plan gate is P4 (Plan Mode), after intent + classify + design. Write the per-commit EXTRACT tier
and the range facts to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md` per
`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` (each commit's row carries the
tier its module's bundle resolved to, per the module-bundle grouping above), then READ that file back at the
start of P1 rather than relying on this phase's text still being in context - a resumed
run must not re-triage the range.

---

## P1 - Intent extract (PARALLEL, READ-ONLY, MODULE-SCOPED)

**BAN (R2b): dispatch ONE `odoo-intent-extractor` per MODULE, never per commit.** Walk the P0
`module -> [ordered sha list]` map; for each module, launch exactly one subagent - real tool calls,
never narrated - carrying that module's FULL ordered commit list. Set BOTH the `model` parameter
(the module bundle's triaged EXTRACT tier, per `references/fp-triage-table.md` Table 1) and the
brief. Concurrency: Mode B budget (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
- the budget counts MODULES in flight, not commits); rolling-window beyond the budget. No child
worktree - extraction is read-only on git history + OSM. A second instance for a module already
dispatched this run is a defect; resume the SAME instance (CHP Tier-A `SendMessage`) instead.

Pre-step (once before the parallel dispatch): invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a batch pass to write per-commit dump files. For each commit SHA in the range:

- op: full-patch commit show (full message + diff) for the sha
- `output: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`
- `repo: <main-checkout-root>` (cross-repo ports only; source commits live only in the main
  checkout after the P0 source-remote add+fetch)

Collect the `{ <sha>: <abs-path> }` map before dispatching any extractor, then group it BY MODULE
using the P0 `module -> [ordered sha list]` map to build each module's `commit_dump_paths`. Every
extractor brief MUST include `commit_dump_paths` (the module's ordered map) from this grouping;
the extractor mandates this field for its P1 bulk-sweep use and never runs git itself.

Brief (run-specific inputs only - the agent's system prompt owns every procedure):

```
DISPATCH MODEL: <extract-tier>            # the MODULE bundle's tier, per Table 1
MODULE: <module-name>
commit_dump_paths:
  <sha1>: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha1>.dump
  <sha2>: <ISOLATE_DIR>/forward-port/<slug>/commits/<sha2>.dump
  # ... every sha touching this module, oldest first
SOURCE SERIES: <e.g. 16.0>
SLUG: <slug>
TASK: For EACH commit in commit_dump_paths (in order), extract the business intent + behavioral
      contract. Read commit message -> PR/issue -> test changes -> code comments (in that
      priority). OSM-ground the touched symbols at the SOURCE version. Write ONE
      <ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md per commit. Note any overlap or revert
      between commits in this SAME module bundle. Do NOT copy diff hunks as intent. Do NOT
      classify the 4-outcome bucket (caller's job).
CALLER_ID (REPLY_TO): <this skill's current orchestrating context - literal `main` only when the
      main-context driver invoked this skill, else the dispatching skill/agent's own name -
      universal skeleton field 11, `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`>
USER LANGUAGE: <lang | omit when English>
```

Aggregate every returned summary (`sha / intent_file / intent_one_liner / symbols /
4_outcome_hint / grounding` - one per commit, all returned from the module's single dispatch) into
the P2 classify queue. Mark each commit `status=extracted` in `checkpoint.json`.

---

## P2 - Classify + installable-probe (module-first order, per-commit bucket, OSM)

Walk modules in the SAME order the P0/P1 map established, and within each module walk its commits
in that module's own order (R2a) - the bucket decision below stays per-commit.

```python
set_active_version(odoo_version='17.0')                          # pin target; reachability probe
api_version_diff(symbol='account.move._post', from_version='16.0', to_version='17.0')
model_inspect(model='account.move', method='summary', odoo_version='17.0')
```

Assign exactly one bucket a/b/c/d per `[[fp-intent-4outcome]]` (read it - do not re-derive the
definitions). Append one row per commit to `merge-log.md` (intent / bucket / reason / evidence -
no blank Reason or Evidence cell). C3 escalations use the canonical row
`<sha> | C3 | source issue <ref|DEFERRED> | <evidence one-liner>`. `odoo-version-diff` forward-port mode supplies the per-symbol
bucket suggestion when the diff is large. Refine the commit's ADAPT tier now that the bucket is
known (bucket a/d -> haiku, test-only).

**Installable-probe (TARGET CLEAN-TIP rule).** For each touched module, resolve its `installable` flag
at the target clean-tip (BEFORE merge) by reading `<module>/__manifest__.py` at `target_ref` - written
by git-ops (read-only) to `manifest_path` in the pre-step below, which now runs for EVERY touched
module, not only before a dispatch. An absent `installable` key means installable (Odoo convention);
an absent FILE means the module is not on the clean tip.

DISPATCH the read-only sonnet leaf `odoo-installable-prober` only when the SOURCE HISTORY is also
needed to disambiguate category 3 - the module's manifest was NOT touched by the cherry-pick range and
its target state is unclear. The prober reads the manifest you wrote plus the history dump; it never
runs git and never calls OSM for this fact. Whether resolved directly (categories 1-2) or via the
prober (category 3), record `installable_false=yes|no` in `merge-log.md` for the module - the ONE
field any later phase reads for its installable state.

Pre-step (unconditional - runs for EVERY touched module, not only before a dispatch): invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files. For
cross-repo ports include `repo: <main-checkout-root>` (source commits live only in the main
checkout after P0 bootstrap):

- `manifest_path`: read `<module>/__manifest__.py` at `target_ref` and write to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/manifest.py`
- `history_dump_path`: run a log-with-patch of manifest modifications (--follow --diff-filter=M
  on `<module>/__manifest__.py`) against `source_ref` and write to
  `<ISOLATE_DIR>/forward-port/<slug>/installable/<module>/history.diff`

Assign the resulting absolute paths before launching the prober; the prober mandates both fields
and never runs git itself.

Dispatcher inputs (CANONICAL CONTRACT - pass exactly these keys):

```
{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }
```

- `repo_root` is the MAIN checkout root where git runs. The integration worktree does NOT exist
  at P2 (it is created at P4) - never reference it here. For a same-repo forward-port `repo_root`
  is the main clone of the repo holding both refs; for a cross-repo port it is the main clone that
  has the source remote added + fetched in the P0 bootstrap step (git-ops adds the source remote
  + fetches). The dispatcher populates `repo_root` deterministically from the P0-recorded checkout
  root before launching the prober.
- `source_ref` / `target_ref` are the source / target git refs (the same refs P0 enumerated).
- `target_version` is the concrete target series for OSM grounding.
- `manifest_path` / `history_dump_path` are absolute paths to the surveyor-written files (see
  pre-step above).

The prober consumes those and returns BOTH:

- `merge_log_line:` - a single-line verdict logged VERBATIM to `merge-log.md`.
- a structured verdict block - `{ module, verdict: yes|no|tentative, evidence }`.

**merge-log row placement.** The prober verdict is its OWN row keyed by module, kept DISTINCT
from the per-commit rows (intent / bucket / reason / evidence). Place it under a dedicated
`## Installable probes` heading (one row per probed module) so a module-keyed verdict is never
confused with a commit-keyed classification row.

**TENTATIVE handling.** A `tentative` verdict is NEVER silently coerced to yes/no: carry it to
the P4 plan gate as a FLAGGED row requiring explicit human confirmation before that module's
merge. A `no` verdict means `installable:False` -> the module enters the lint-only lane and SKIPs
extract/adapt logic tiers. Do not restate the rule - SSOT: `[[fp-installable-false]]`.

---

## P3 - Design (conditional route-out)

A bucket-(c) "do now" commit that touches a NON-TRIVIAL module routes OUT to
`odoo-solution-design` instead of being adapted blind. Reuse the non-trivial criterion from
`skills/odoo-solution-design/SKILL.md` § When to invoke - do NOT invent a third definition. A
deferred or `installable:False` module needs no design - skip it.

Emit the Continuation Contract and YIELD (forward-port only EMITS the next hop; the run-harness
advances it):

```
next: odoo-solution-design
inputs:
  return_to: odoo-forward-port
  design_slug_hint: <slug>-fp-<sha>
  target_version: <target>
  modules: [<module-name>, ...]
  intent_records: [<ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md]
  classification: <bucket-(c) summary>
```

`<slug>` is the run slug (`<source-series>-to-<target-series>`); `<sha>` the short SHA of the
routed commit. Together `design_slug_hint` gives the design agent a deterministic output path
(`<slug>-fp-<sha>`), so forward-port re-entry locates it without scanning.

`odoo-solution-design` under `return_to` runs its own design + design-approval gate, then emits
`next: odoo-forward-port` with `design_doc: <path>`; it does NOT enter a code Plan Mode and does
NOT dispatch a coder (SSOT: `skills/odoo-solution-design/SKILL.md` § Design-approval gate). On
re-entry, read `design_doc` from the returned contract's `inputs`, record it against the commit,
set checkpoint `status=designed`, and proceed to the P4 plan gate with the design linked - do
not re-run design. If `design_doc` is ABSENT from the returned inputs (design crashed before
producing it), set the commit back to `status=extracted` and re-enter P3 next run rather than
advancing to P4 with no design.

---

## P4 - Plan gate (Plan Mode)

The user approves here - AFTER intent + classify + design, so the plan carries the REAL triaged
tiers and REAL buckets, never guesses. Forward-port runs from the MAIN context, so it MAY drive
Plan Mode (a subagent cannot).

Plan-Mode enter/exit is the SHARED SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit + plan_mode_active
- forward-port REUSES it for this gate rather than defining its own: `EnterPlanMode` iff
`plan_mode_active` is absent/false (skip iff a caller already opened Plan Mode), present the plan,
`ExitPlanMode` on approve, user approves in the Plan Mode UI. The plan CONTENT authored here (NOT
routed through `odoo-planning`) is MODULE-FIRST (R2a - this is the whole-picture gate a flat commit
list cannot give): module topology (each module's own ordered commit list from the P0 map);
per-module EXTRACT tier (the real triaged tier, called out on its own line when it is opus - R2d
gate, `references/fp-triage-table.md` Table 1); per-commit bucket (the real classification) and
ADAPT tier within that module; installable routing per module; design-doc link for any commit P3
designed; merge batches.

Red flags: a text-gate "approve" is NOT Plan Mode approval (two separate steps); `EnterPlanMode`
MUST come before any branch, worktree, or file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched FROM B (Hard rule 1 - no branch before this point). Describe the op:

```
op: create integration worktree
scope: branch fp/<slug>, base <target-branch>
worktree: <path>/fp-integration
```

THEN write `<ISOLATE_DIR>/forward-port/<slug>/plan.md` as the resume RECORD (not the gate - the gate
is Plan Mode above). MODULE-FIRST: one block per touched module, that module's commits nested
inside it in the module's own order (R2a - the whole-picture record). Later phases and the
checkpoint/continuation read it:

```markdown
# Forward-port plan: <source-series> -> <target-series> (<slug>)
Mode: continuous | one-shot
Integration worktree: <path>  (branched from <target-branch>, B untouched)
Modules (<N>, after --scope/--since filter):

## Module: account_reports  (EXTRACT tier: sonnet)

| SHA | summary | bucket | ADAPT tier | installable routing | design_doc |
|-----|---------|--------|------------|----------------------|------------|
| abc1234 | double-post guard | (b) | sonnet | normal | - |

## Module: report_engine_custom  (EXTRACT tier: opus - CONFIRMED at Plan Mode: cross-module report
engine rewrite)

| SHA | summary | bucket | ADAPT tier | installable routing | design_doc |
|-----|---------|--------|------------|----------------------|------------|
| def5678 | new report engine | (c) do-now | opus | normal | <SHARE_DIR>/designs/...md |

Fable rows (if any, ADAPT tier only - Table 1 has no fable band): <module>: <sha> - <why> (~2x
opus). (confirmed in Plan Mode)
Opus-declined / gate-suppressed downgrades (if any, EXTRACT tier): <module>: sonnet (opus declined
| opus auto-downgraded - gate suppressed)
```

---

## P5 - Merge --no-commit (critical section)

Invoke the `git-toolkit:git-ops` skill (via the Skill tool). Dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
For semantic conflicts use the stateless-resume recipe in that snippet.

```
# continuous - keep the source SHA
op: merge --no-ff --no-commit <src-SHA>
worktree: <path>/fp-integration

# one-shot only (source frozen)
op: cherry-pick -n <src-SHA>
worktree: <path>/fp-integration
```

Only one merge in flight (shared git index). Do NOT commit - the working tree is the absorption
zone through P9. Full protocol incl. absorption window order: `[[fp-merge-absorption]]`.

---

## P6 - Symbol-survival check (MUST, before adapt)

```bash
# files with conflict markers
git diff --check ; grep -rn '^<<<<<<<' .
```

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to list files changed in range `<merge-base>..<src-SHA>` (--name-only;
git-ops writes the file list, filtered to non-empty entries - these are the
merge-clean-but-source-touched autosilent-break candidates). For cross-repo ports include
`repo: <main-checkout-root>` (source commits live only in the main checkout after the P0
source-remote add+fetch).

For every Odoo symbol in those files (field / method / model / view ref / external-id /
manifest depend / ORM chain), confirm existence + type at the TARGET version:

```python
model_inspect(model='account.account', method='fields', odoo_version='18.0')
entity_lookup(kind='field', model='account.account', field='company_ids', odoo_version='18.0')
api_version_diff(symbol='account.account.company_id', from_version='17.0', to_version='18.0')
```

Any absent/changed symbol FORCES bucket b/c/d and bans leaving the auto-merged line unchanged.
Produce the `SYMBOL-BROKEN | <symbol> | <file>:<line> | bucket | evidence` finding list (an
empty list `SYMBOL-SURVIVAL: clean` is a valid, desirable result). A non-empty list BLOCKS
P8 on those files. Full contract: `[[fp-symbol-survival-check]]`.

**Run on `tests/` files too** - test files auto-merge silently exactly like production code and
crash at collection (base-class kwarg drift, broken import, dynamic `ref()`), never reaching
P9 if collection itself fails. Do NOT re-derive the test-survival logic here - apply the
seven auto-merge-silent symbol classes from `[[fp-symbol-survival-check]]` section 2.5 (it already
states production AND `tests/` scope). The merge-clean-but-source-touched enumeration above
already lists test files; feed them through the same section-2.5 grounding, do not filter them
out.

---

## P7 - Pre-adapt drift scan (MUST, before the behavioral loop)

This gate is DISTINCT from the P6 TEST-survival sub-check:
- **P6 TEST-survival** uses `tests_covering` / `test_coverage_audit` (OSM cross-version
  symbol lookup) to detect test methods that REFERENCE a field/model removed at the target.
  It operates at the OSM symbol-graph level and covers both production and test code.
- **P7** uses the seven static symbol classes from `[[fp-symbol-survival-check]]` section 2.5
  over two lanes: (d) python-import + (e) AST-pyflakes + (g) ORM create/write dict-key run over
  ALL merged-touched `.py` (production AND `tests/`) - (d)(e) catch runtime NameError and (g)
  catches an Invalid-field key (autosilent: pyflakes does NOT flag it) before P9; the remaining
  classes (a)(b)(c)(f) and the collection ACCEPTANCE GATE apply to the `tests/` lane only.

The two checks are COMPLEMENTARY: P6 catches symbol-graph breaks via OSM; P7 catches
static grep / import / AST breaks and blocks entry to P8 when test collection itself would
fail.

**Enumerate scope - two lanes:**

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to list files changed in range `<merge-base>..<src-SHA>` (--name-only;
git-ops writes the file list). Include `repo: <main-checkout-root>` in the dispatch for
cross-repo ports. From that list:

```bash
# Lane 1 (from git-ops result): ALL merged-touched .py (production AND tests/)
#   - filter the file list to *.py entries

# Lane 2 (from git-ops result): tests/ only
#   - from Lane 1, filter entries whose path contains tests/
```

For Lane 1 files apply classes (d) + (e) (`py_compile` + `pyflakes`) AND (g) (ORM create/write
dict-key scan) over ALL .py - production AND tests. Treat F821 on a production file as a runtime
NameError that would crash module load, not a nit; treat a (g) dead key on a production call site
the same way - it raises `Invalid field` at load/run yet pyflakes stays silent. For Lane 2 files
additionally apply (a) (b) (c) (f).

Record findings as `SYMBOL-BROKEN | <symbol/path> | <file>:<line> | <class> | evidence` and
append to `merge-log.md`. These become the `BROKEN TEST-SYMBOLS` input to the 8a brief.

**ACCEPTANCE GATE (collection clean) - mandatory before P8 starts:**

At P7 no instance DB has been acquired yet (allocator runs at P9) - use the `pytest --collect-only` path; the odoo-bin collection option requires first acquiring a temp DB.

```bash
# pytest collection smoke-test
python -m pytest <test_files> --collect-only -q 2>&1 | tail -20
# OR Odoo collection (for TestCase subclasses with setUpClass) - requires a DB acquired via allocator
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d $ALLOC_DB_NAME --test-enable --test-tags <tag> --stop-after-init \
  --skip-auto-install --http-port=$ALLOC_HTTP_PORT \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296} 2>&1 | grep -E 'ERROR|setUpClass'
```

Memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

A collection failure (ImportError, setUpClass crash, missing fixture) means the tests NEVER
RAN in P9 - a count of `0 failed, N error(s)` is NOT a passing result (the setUpClass
crashed before any test method ran). Resolve every drift finding (P7 SYMBOL-BROKEN entries)
before entering the P8 adapt loop.

**View-topology sub-check (bucket-(c) same-module inherit stacks).** Different in TIMING from the
checks above (P6/P7 run over the git-merged tree before any commit is re-implemented; this
sub-check runs once a bucket-(c) re-implement itself lands or modifies an `ir.ui.view` record, at
the same converge-back point the 8b bucket-(c) leg already passes through) but IDENTICAL in SHAPE
(a finding line triaged into `merge-log.md`, confirmed before the gate). Full predicate, the two
non-defect exceptions, and the merge-unsafe escape: `references/fp-triage-table.md` § Bucket-(c)
same-module inherit-view check.

---

## P8 - Adapt (test-first; serial per-module within a commit; ALWAYS directly in the integration worktree)

For each touched module/WI, dispatch the adapt unit DIRECTLY in the integration worktree
(`<path>/fp-integration`, the JOB-tier worktree already created at P4 - `## P4` above) and process
modules serially - complete one module before starting the next within the same commit. P8 NEVER
creates a per-module child worktree (full derivation: `SKILL.md` § Git topology "WORK tier - NOT
used by P8 adapt"): P8 is serial (no concurrent writer to filesystem-isolate) AND the open-merge
window below never clears before P8 runs (no committed tip for a child to fork from, and no way to
converge one back in time even if created).

**Open-merge window (CRITICAL constraint - unconditional, not a special case).** For the ENTIRE
span from P5 (`--no-commit`) through P10 (`commit`) - i.e. every commit's own P6/P7/P8/P9 -
`MERGE_HEAD` (continuous mode) or `CHERRY_PICK_HEAD` (one-shot/absorb-all) is live in the
integration worktree. Git rejects any second merge in that worktree until the first is committed
or aborted (error: `MERGE_HEAD exists`), so a child worktree could never converge back during P8
on ANY commit, in EITHER mode. This is NOT a carve-out for "a subsequent commit after the previous
P10 closed the prior merge": that gap sits BETWEEN commits, never DURING one - by the time P8 for
the next commit runs, that commit's OWN P5 has already reopened `MERGE_HEAD` (P5 always precedes
P6/P7/P8/P9; P10 is the only step that commits it, and P10 runs AFTER P8/P9 finish - `## P10`
below). Adapt all modules SERIALLY, DIRECTLY in the integration worktree, on every commit, in
either mode - continuous keeps `MERGE_HEAD` live for each commit's own P6-P9 span with no
exception; one-shot/absorb-all keeps `CHERRY_PICK_HEAD` live for the WHOLE run's single P6-P9 span
with no exception. SSOT: `[[fp-merge-absorption]]` §Absorption-window.

**8a - forward the test FIRST** (the test is the oracle; independence keeps it honest).
**R2b - at most one `odoo-test-writer` instance per module across the WHOLE run:** on the module's
FIRST commit in this run, launch a NEW `odoo-test-writer` agent named `fp-adapt-<slug>-<module>`
in adapt mode (it authors by invoking the `odoo-test-writing` skill inline, in its own context); on
any LATER commit touching the SAME module, RESUME that same named instance via `SendMessage`
(CHP Tier-A) instead of launching a new one - full rule and the cd-on-resume requirement:
`SKILL.md` § P8. The brief below is identical on a fresh launch or a resume; only the SOURCE TEST
content and the per-commit fields (INTENT/BUCKET/BROKEN TEST-SYMBOLS) change per commit - the
Worktree path field never changes (P8 always adapts directly in the SAME integration worktree for
the whole run, `SKILL.md` § Git topology).

```
TEST ADAPT MODE: forward this source test to the target platform.
WORKER NAME: fp-adapt-<slug>-<module>   (stable for the WHOLE run - launch once, resume for every
      later commit touching this module; never re-launch fresh under this name)
SOURCE TEST (READ/WRITE, in the integration worktree): <path>/fp-integration/<module>/tests/<test_file>
  (merged working-tree content; for bucket (b) it may still carry conflict markers or auto-merged
   text - resolve IN PLACE and write the adapted result back to this SAME path. P8 never uses a
   separate child worktree, so there is no WRITE-TO location distinct from where this is read.)
INTENT: <one-liner from intents/<sha>.md>   BUCKET: <a|b|c|d>
ODOO VERSION: <target>
BASE CLASS (target): <signature from test_base_classes(odoo_version='<target>') for the source
      test's base class - the kwargs the target setUpClass/setUp actually accepts, so the author
      does not re-introduce a dropped kwarg>
TARGET TEST EXAMPLES: <1-2 paths from find_test_examples(query='<feature>', odoo_version='<target>')
      that already test this behavior the target-idiomatic way - imitate their structure>
BROKEN TEST-SYMBOLS: <the P6 / P7 SYMBOL-BROKEN entries that land in THIS test file - the
      author must repair each (do not forward them verbatim)>
CALLER_ID (REPLY_TO): <this skill's current orchestrating context - literal `main` only when the
      main-context driver invoked this skill, else the dispatching skill/agent's own name -
      universal skeleton field 11, `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`>
RULE: translate to target API; STRIP implementation-coupled assertions (private method asserts,
      call counts, internal ordering); re-create the BEHAVIOR on target; confirm RED on target.
      Never relax/rewrite an assertion to pass unless the target platform legitimately redefines
      the behavior AND you cite the OSM/platform reason.
```

Resolve the three enrichment lines BEFORE dispatch:

```python
test_base_classes(odoo_version='18.0')                                      # BASE CLASS (target)
find_test_examples(query='double-post guard on account.move', odoo_version='18.0')  # TARGET TEST EXAMPLES
```

`BROKEN TEST-SYMBOLS` is the subset of the P6 symbol-survival finding list (plus any P7 drift
finding) whose `<file>` is this test file - copy those rows in verbatim; omit the line when the
list is empty for this file.

**8b - adapt the code** per bucket. Invoke the `odoo-coding` skill (via the Skill tool) with the
FP-ENRICHED brief - `odoo-coding` owns the backend/frontend split, coder fan-out (via its
`odoo-coder` per-module coordinator), model, and synthesis (do NOT dispatch raw `odoo-coder`,
`odoo-backend-coder`, or `odoo-frontend-coder`). **R2b at this leg is CLOSED: name the coordinator
once, resume it across commits - the SAME field shape as 8a, a NAME, never an agentId.**
`agents/odoo-coder.md` § Cross-round resume confirms the coordinator is round-scoped, not
single-shot-forever - a caller may resume the SAME named coordinator for a LATER commit instead of
cold-spawning a fresh one, the same mechanism already used for the 8a `odoo-test-writer` above.
On the module's FIRST commit, and on every LATER commit touching the same module, carry
`WORKER NAME: fp-adapt-<slug>-<module>-coder` in the brief below (distinct from the 8a
test-writer's `fp-adapt-<slug>-<module>` name; the SAME field label 8a already uses, never a
second differently-shaped field) - resume addresses a worker BY NAME (it keeps resolving after a
worker completes and is resumed from its transcript); a raw agentId is only the fallback for an
unnamed worker, and this worker is always named, so an agentId would carry no information the name
does not already carry. **R2b IS closed at 8b: `odoo-coding`'s brief-consumption contract now
recognizes `WORKER NAME` and resumes the already-addressable worker via `SendMessage` instead of
cold-spawning a fresh one under a self-generated name** (full reasoning:
`SKILL.md` § P8). Hard rule 2 is unaffected either way: one resumed coordinator making N commits'
worth of adapt work still produces N separate target merge commits, one per source SHA. The extra
context a generic
coder brief lacks:

```
DISPATCH MODEL: <adapt-tier>
REQUEST: Adapt the forwarded intent to the target platform.
INTENT RECORD: <ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md   (the why - build to this, not the source diff)
BUCKET: <a skip-code | b 3-way+adapt | c re-implement on target idiom | d skip-code>
FAILING TEST (RED, written by the odoo-test-writer above): <paths> - implement until GREEN; do NOT edit them.
NEW MODULE: <yes - apply installable:False checklist [[fp-installable-false]] | no>
DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>   (P3's route-out
      result, `references/fp-phase-detail.md` P3 - so 8b never adapts blind; `none` when P3 never
      routed this commit to design; same sentinel shape `odoo-coding`'s own resolution already
      uses, `skills/odoo-coding/SKILL.md` "DESIGN_DOC: <child TDD path | none>")
MODULE SCOPE: <name>
  READ/WRITE (in the integration worktree, no separate child worktree): <path>/fp-integration/<module>/
    (merged content; for bucket (b) 3-way+adapt start from these files - they hold the
     auto-merged or conflict-marked state - and write ALL output back here, in place)
ODOO VERSION: <target>
WORKLOG: <slug> - read, then append.
MANIFEST/MIGRATION/PROVENANCE: apply C1 (keep TARGET version on conflict, never bump), C2 (migration-dir
  retarget), C3 (carry pre-existing source bugs faithfully, do not inline-fix) - [[fp-merge-absorption]]
WORKER NAME: fp-adapt-<slug>-<module>-coder   (stable for the WHOLE run - launch once, resume for
      every later commit touching this module - see above)
CALLER_ID (REPLY_TO): <this skill's current orchestrating context - literal `main` only when the
      main-context driver invoked this skill, else the dispatching skill/agent's own name -
      universal skeleton field 11, `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`>
USER LANGUAGE: <lang | omit when English>
```

**8c - installable:False modules** - two sub-cases, same manifest action. (i) **New module** (absent
at target): `installable: False`, comment `auto_install`/`application`, lint-fix only.
(ii) **Upgraded-then-forwarded** (target clean-tip = `installable:False` but merge carries `True`):
re-set to False + re-comment `auto_install`/`application` with `# TODO: Uncomment when upgrading
module to production-ready status` breadcrumb - then lint-fix only. SSOT: `[[fp-installable-false]]`.

**8c-bis - installable:False at target = LINT-ONLY lane.** BEFORE dispatching the coder/reviewer
for any module (new or pre-existing), confirm its target installable flag. Re-read
`<module>/__manifest__.py` at `target_ref` (via git-ops, read-only) only if the manifest was touched
by the merge; otherwise reuse the value P2 already resolved from `manifest_path`. If
`installable: False` at the target, brief
the coder in **lint-only mode**: run flake8 / eslint / prettier / ruff and fix ONLY syntax/lint
breakage to keep CI green - do NOT adapt business logic, do NOT upgrade content. Pass
`LINT-ONLY: yes` in the 8b brief and the pointer `[[fp-installable-false]]`. The single exception
to "no logic change" is a syntax/lint error that itself blocks the file from parsing.
When the merged `__manifest__.py` now shows `installable:True` (upgrade-commit carried in)
but the target clean-tip was `installable:False`, re-set to False + re-comment
`auto_install`/`application` with the `# TODO: Uncomment when upgrading` breadcrumb before
dispatching the coder. SSOT: `[[fp-installable-false]]`.

**8d - migration script:** RETARGET a forwarded `migrations/<src-series>.a.b.c/` dir per C2:
default = rename to FULL `<tgt-series>.V` where `V` is chosen so the dir fires on a deployed target
DB at manifest `M` (if `S > M`: `V=S`, merge already bumped; if `S <= M`: bump manifest to
`V = M`'s last component +1, name dir `<tgt-series>.V`). Exception: a legacy source-origin-only
data fix keeps `<src-series>.a.b.c` untouched. Lint-only lane (`installable:False` at target) = do
NOT retarget. This is a migration-threshold action, NOT a "diff-touched-a-file" bump (C1). Full
rule + `adapt_version` silent-skip WHY: `[[fp-merge-absorption]]`. After the rename, sweep the
migration body for source-series literals still in log strings or version constants:

```bash
grep -rn '<src-series>' migrations/<tgt-series>/   # e.g. grep -rn '17\.0' migrations/18.0/
```

**8e - i18n: COMPUTE and RECORD; the dispatch happens at P9.5.** Do NOT dispatch `odoo-i18n` here -
this phase has no instance, and `odoo-i18n` hard-BLOCKs without one. Evaluate both mandate conditions
now, from artifacts that already exist, and record them on the module's `merge-log.md` row:

1. **Condition 1 - translatable delta.** Run the 8-signal trigger table over this batch's
   `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump` files. Record
   `i18n_signals: [<fired ids>]` or `i18n_signals: none`.
2. **Condition 2 - already live at the target.** Read `installable_false` from this module's
   `merge-log.md` row. Record `i18n_due: yes|no|escape:<E-id>`.

Both conditions and the escape table: `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`.
Carry `i18n_due` forward to P9.5. Recording it here and dispatching there is deliberate: the decision
needs the diff (available now), the dispatch needs the instance (available at P9).

No convergence or worktree removal step here: 8a/8b already wrote directly into the integration
worktree (no per-module child worktree exists to converge back or remove - `SKILL.md` § Git
topology). Mark `status=adapted`.

---

## P9 - Verify by behavior (PER-BATCH, in integration)

Resolve odoo-bin flags for the TARGET series via `cli_help` before dispatching - the allocator
returns version-agnostic ports; flags and bootstrap behavior differ per series (e.g. v19
namespace package changes bootstrap; always pass `odoo_version=<target>` to `cli_help`).
Instance lifecycle protocol: `docs/reference/INSTANCE-LIFECYCLE.md`. Test invocation
conventions: `docs/reference/ODOO-TESTING.md`.

**DELEGATE - never a raw `allocator.py`/`odoo-bin` recipe.** SKILL.md P9's rule is binding here
too: this orchestrator dispatches the `odoo-instance` skill (via the Skill tool) for every step
below. Only `odoo-instance-ops` and the instance-touching HARD LEAVES enumerated in
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` may call `scripts/lib/allocator.py`
or `odoo-bin` directly (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md` § Carve-out) - a bare
allocator/odoo-bin call from this orchestration layer would both bypass the instance HARD RULES
and skip the `WORKTREE_PATH` re-root below. Everything from here to the P10 gate is CONTENT for
that dispatch brief and the adjudication this orchestrator performs on the RETURNED `instance-ops`
block, never a shell recipe run inline.

**Env-bootstrap (informational, before the first dispatch).** Read `<SHARE_DIR>/context.md`
`## Verify environment` for the CATALOG (principal-checkout) baseline `odoo-instance` resolves
against internally - venv/interpreter discovery and addons-path assembly are `odoo-instance-ops`'s
own job (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md`), never hand-built or hand-verified
here. A multi-repo stack (e.g. Viindoo Standard spans 4 repos) needs EVERY repo on disk - a missing
repo makes a module invisible (silent ImportError / "module not found") to the dispatched instance.
Confirm each stack repo listed in `context.md` exists on disk before dispatching; a missing repo is
`BLOCKED` (NEEDS_CONTEXT), not a test red.

**Worktree re-root (MANDATORY, after the CATALOG baseline above, before it is treated as final).**
The block above resolves the CATALOG (principal-checkout) baseline only - it is NEVER the addons_path
this phase actually verifies against. This batch adapted `<path>/fp-integration` (the P4 JOB-tier
integration worktree), so re-root the baseline onto it via the SAME mechanism every other consumer
uses - `odoo-instance`'s `WORKTREE_PATH` field (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md`
§ WORKTREE_PATH substitution) plus the allocator's `--addons-path-override`: dispatch `odoo-instance`
(SKILL.md P9) with `WORKTREE_PATH: <path>/fp-integration`, which drops every catalog entry under the
principal checkout and prepends the equivalent under `<path>/fp-integration` before `acquire`. Do NOT
hand-build the override yourself and do NOT verify against the catalog `ADDONS_PATH` built above
directly - that is exactly the un-adapted-code false-green this re-root exists to prevent. Before trusting any
result below, assert the resolved addons list contains `<path>/fp-integration/<module>/__manifest__.py`
for every module in this batch (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` §
Addons coverage assertion) - on a miss, `BLOCKED`, never a silent run against the wrong tree.

**Install/verify the FULL transitive `depends` closure, not just the module you edited.**
A forwarded change can break a downstream depender that you never touched. Resolve the closure
per module, then install/verify its breadth:

```python
module_inspect(name='account_accountant', method='dependencies', odoo_version='18.0')
```

Union the closures of every directly-touched module and pass that whole set as `modules` in the
dispatch below.

**Lint toolchain present BEFORE the lint gate.** The verify venv must have flake8 / ruff
(and eslint / prettier for frontend) installed, or the P12 lint gate silently no-ops. Confirm
`flake8 --version` and `ruff --version` resolve in the verify env before relying on a green lint.

**Dispatch `odoo-instance` (via the Skill tool) - ONE ephemeral instance per BATCH, not per
commit.** First commit in the batch (fresh DB; install + test in one pass - Odoo create-on-init
builds the DB, the allocator only reserves the name/ports):

```
operation: run-tests
series: <target>
persist: ephemeral
RUN_ID: <this run's id>
WORKTREE_PATH: <path>/fp-integration   # re-root per the Worktree re-root note above
modules: <union of the touched modules' full transitive depends closure, comma-separated>
mode: fresh
skip_auto_install: true   # ISOLATES auto_install modules that would otherwise be pulled in
                          # silently and mask (or fabricate) a break
CONFIRM: "confirm each module in this closure emits a Loading line before reading any test count -
          Odoo silent-skips an installable:False or skip_auto_install-excluded module with NO
          error line, so a green run alone is not proof it installed; report per-module install
          status in modules_installed and the test result in findings_path"
```

Capture the returned `instance-ops` block as this batch's `INSTANCE_HANDLE` (`dbname`,
`lease_token`, `run_id`, `addons_path`) - memory-cap is applied automatically inside
`odoo-instance-ops`, no separate field to pass
(`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`). The closure suite can be very
large. MAY narrow with `test_tags` to the touched modules + direct dependers, but NEVER narrow to
only the edited module - a forwarded change can break tests in a downstream depender, and a
module-only tag would hide that. Default: no narrowing (run the full closure); narrow only when
the untagged run is prohibitively large, and record the tag used in `merge-log.md`.

For a SUBSEQUENT commit in the SAME batch touching only a subset, re-dispatch `odoo-instance` with
the SAME `INSTANCE_HANDLE` forwarded and `mode: reuse` (`-u` semantics) on the changed modules only
- skip re-running the full closure. Behavior rule: once a module is installed in this DB,
re-running its tests MUST use `reuse`; `fresh`/`-i` on an already-installed module is a no-op
(confirm flags via `cli_help`). Full rule: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

Relay the returned `instance-ops` block (`log_path`, `findings_path`, `modules_installed`,
`failed`/`errors`/`warnings`/`skipped`) into `merge-log.md` verbatim - never trust a bare "tests
passed" summary in its place (Hard rule 8: verify the result yourself). Reconcile
`modules_installed` against the installable scan (`[[fp-symbol-survival-check]]` section 2.5f): a
module that is `installable: False` at the target is EXPECTED to be absent from
`modules_installed` - route it to the 8c-bis lint-only lane and do NOT count its absence as a
break. A module that IS installable and absent from `modules_installed` is a real failure -
investigate via `log_path` before reading any test count.

**Recover a batch stuck mid-run.** Do NOT `pkill` an `odoo-bin` process or call
`allocator.py release` directly. Dispatch `odoo-instance` with `operation: drop`, passing the
batch's cached `lease_token`/`run_id` - it stops the bound process group FIRST, then drops the DB
through Odoo (`${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` § drop-instance); a bare `pkill`
risks matching the wrong process or a sibling batch's server. Re-dispatch the Step above for a
clean retry.

- **RED-then-GREEN (whole module):** target suite must be green.
- **Confirm-by-toggle (FP-delta tests only):** disable each newly-forwarded adapt -> that test
  must go RED -> restore. Proves the test exercises the adapted behavior. Do NOT toggle the whole
  suite.
- **Triage red:** Triage EVERY red against a clean-tip baseline before calling it a
  regression - whether the red is in the edited module or in a co-installed dependency pulled
  in by the closure. Re-dispatch `odoo-instance` (same shape as above) against a clean checkout of
  the target tip - no `WORKTREE_PATH` override, no absorption - running the SAME closure. Red
  there too = pre-existing (record in merge-log.md, do not fix, do not block). Green on clean /
  red only after absorption = FP-delta (fix before committing). A red in a co-installed dep you
  never touched is almost always pre-existing - prove it with the clean-tip dispatch, do not
  assume. Never widen an assertion to hide a pre-existing failure. For source-series
  follow-through on a pre-existing red, apply C3 - carry faithfully + open a source issue
  (resolvable remote) or record it; see `[[fp-merge-absorption]]` § Triage / C3.
- **Baseline a failed INSTALL the same way.** If a module fails to install, re-dispatch
  `odoo-instance` against clean `origin/<target-branch>` (no `WORKTREE_PATH`, no absorption).
  Fails there too = a PRE-EXISTING break in the target series, NOT FP-introduced - record it in
  `merge-log.md` and do NOT block the forward-port on it. Only an install that is green on clean
  origin/target and red after absorption is an FP-delta to fix.
- **CREATEDB-role footgun:** the allocator probes this automatically inside every `odoo-instance`
  dispatch and degrades `ephemeral` -> `exclusive` when the role lacks it - a degrade means two
  parallel batches can collide on the same DB. If the returned `instance-ops` notes flag a
  degrade, serialize remaining batches rather than run them concurrently. Full mechanism:
  `[[fp-merge-absorption]]` § Allocator footgun.

Full per-batch protocol: `[[fp-merge-absorption]]`. Mark `status=verified`.

---

## P10 - Gate merge (STOP, per batch)

Present `merge-log.md` and wait for human-confirm. On confirm, invoke the `git-toolkit:git-ops` skill (via the Skill tool):

```
op: commit
message: "fp: absorb <src-SHA> - <one-line summary> [bucket <x>]"
worktree: <path>/fp-integration
confirmed: yes - human approved at P10 gate
```

Buckets (a)/(d) STILL commit (keeps SHA, advances merge-base - Hard rule 7); the message records
the bucket + reason so the empty diff is not flagged. Update `checkpoint.json` `{<sha>: done}`.
More commits/batches remain -> LOOP to P5 (each subsequent commit re-runs the full per-commit
cycle P5 merge -> P6 symbol-survival -> P7 drift -> P8 adapt; P9 then verifies the batch of
adapted commits and P10 gates that batch - never skip P5/P6/P7 for a later commit by looping
straight to P8, which would absorb it without a merge or a symbol/drift check).

---

## P12 - PR + review

Runs AFTER P11 (end-to-end acceptance, `SKILL.md` § P11) has already cleared for this batch -
acceptance, then this review gate, THEN the PR opens; never the reverse (`SKILL.md` Hard rule 9;
SSOT for the ordering rationale: `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
§ Pre-PR tail).

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push (resolve origin URL via `git remote get-url origin`):

```
op: push fp/<slug> to origin (NOT B)
scope: branch fp/<slug>
worktree: <path>/fp-integration
remote: resolve via `git remote get-url origin`
```

Run `odoo-code-review` inline (via the Skill tool, from the orchestrating context) for the
forward-port pitfall (a forwarded test still coupled to the source API) - this review runs on the
pushed branch BEFORE the PR is created (the diff-based checks below need only the push above, not
an open PR).

**Attribute every finding to the FP diff before rating it.** A reviewer rating the whole
file blames the forward-port for code it never touched. Before rating any finding, confirm the
line is actually in the forward-port delta. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for a three-dot diff
(`origin/<target-branch>...fp/<slug> -- <file>`, only what the FP added to `<file>`).

A finding on a line NOT in this diff is pre-existing - note it separately, do not block the PR on
it (flag it, do not gate the forward-port on it).

**Per finding, apply C3 (fix old version first).** Check whether the same defect exists at the source
series. If it does, it is a **pre-existing source bug** (inherited - forwarded faithfully, not introduced
by this port): route the fix UPSTREAM via a source-series issue (invoke git-ops when a source
remote resolves via `git remote get-url`, else record it in `merge-log.md` + the Continuation Contract);
do NOT patch it inside the FP. Record `<sha> | C3 | source issue <ref|DEFERRED> | <evidence>` in
`merge-log.md` and carry it faithfully forward. EXCEPTION: a serious security/safety bug is fixed on the
destination immediately (still open a source issue). SSOT: `[[fp-merge-absorption]]` § Triage / C3.

**Narrow a field-existence question with a direct lookup, not a model_inspect retry.** When
a finding hinges on whether one field still exists / changed type at the target, query that field
directly instead of re-dumping the whole model:

```python
entity_lookup(kind='field', model='account.move', field='payment_state', odoo_version='18.0')
```

**installable:False modules get a LINT-ONLY review.** For any module that is
`installable: False` at the target (8c-bis lane), the reviewer rates ONLY syntax / lint findings -
do NOT raise business-logic / behavior findings against a module that does not even install at the
target. Mark such findings out-of-scope for this forward-port.

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

**Cross-check every static-review bot comment on the PR (post-PR, the ONE sub-step here that
genuinely needs an open PR).** Once the PR above is open and CI has had a chance to run, read the
bot (CI linter / review bot) comments and resolve or consciously waive each - a bot comment on a
forward-ported line is signal that an auto-merged construct did not survive the target. This runs
after PR creation, never before, and never gates PR creation itself.

NEVER squash (squash mints a new SHA, defeats merge-base advance). B stays LOCKED - the PR adds
only the merge commits. Present the PR URL, the review findings, and the P11 acceptance verdict
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

Leave `<ISOLATE_DIR>/forward-port/<slug>/` for the next continuous run's resume (it is gitignored and
the checkpoint lets tomorrow's run skip done commits).
