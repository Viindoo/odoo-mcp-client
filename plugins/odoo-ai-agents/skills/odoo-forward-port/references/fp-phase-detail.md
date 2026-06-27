<!-- Reference for odoo-forward-port/SKILL.md § The pipeline. Loaded as needed.
     Per-phase git commands, dispatch-brief templates, and worklog formats. The SKILL.md body
     carries the contract; this file carries the verbatim commands and brief text. -->

# Forward-Port Pipeline - per-phase execution detail

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`.odoo-ai/forward-port/<slug>/` (gitignored). Every Odoo Semantic call passes a concrete
`odoo_version=` - never omit it, never rely on a default; the version pin is per-API-key state
that any concurrent agent can overwrite.

---

## P0 - Recon & triage (read-only, NO stop)

```bash
# 1 - resume: read prior state, skip done commits
cat .odoo-ai/forward-port/<slug>/checkpoint.json 2>/dev/null   # {<sha>: status}

# 2 - enumerate the commits to forward (read-only; no worktree, no branch yet)
# Same-repo (both refs on origin): compute merge-base locally
MB=$(git merge-base <target-branch> <source-ref>)
# Cross-repo: delegate to git-operator (add source remote + fetch), then compute:
#   MB=$(git merge-base <target-branch> source/<branch>)
# Delegate to git-surveyor: enumerate commits (--no-merges, range MB..<source-ref>,
#   apply --scope <paths> / --since <date>); git-surveyor writes the commit list.
```

Map each `--scope` module name to its directory path before requesting git-surveyor to filter
by path (module `l10n_vn` -> `l10n_vn/`; resolve via manifest location - may be at repo root
or under an addons subdir, e.g. `addons/l10n_vn/`).

For each commit, triage the EXTRACT tier INLINE (`git show --stat <sha>`; for an override-depth
question, one `find_override_point` probe) per `references/fp-triage-table.md` Table 1 - the
orchestrator triages the tier itself; never dispatch an agent to decide a dispatch.

This is recon only. There is NO approval gate here, NO `plan.md` written, NO branch, NO worktree -
the plan gate is P4 (Plan Mode), after intent + classify + design. Carry the per-commit EXTRACT
tier forward to P1.

---

## P1 - Intent extract (PARALLEL, READ-ONLY)

Dispatch one `odoo-intent-extractor` per commit as a subagent launch - real tool calls, never
narrated. Set BOTH the `model` parameter (the triaged EXTRACT tier) and the brief. Concurrency:
Mode B budget (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`); rolling-window
beyond the budget. No child worktree - extraction is read-only on git history + OSM.

Pre-step (once before the parallel dispatch): delegate to git-surveyor (read-only, no worktree)
in a batch pass to write per-commit dump files. For each commit SHA in the range:

- op: full-patch commit show (full message + diff) for the sha
- `output: .odoo-ai/forward-port/<slug>/commits/<sha>.dump`
- `repo: <main-checkout-root>` (include for cross-repo ports; the source commits exist only in
  the main checkout after git-operator added the source remote and fetched at P0)

Collect the `{ <sha>: <abs-path> }` map before dispatching any extractor. Every extractor brief
MUST include `commit_dump_path` from this map; the extractor mandates this field and never runs
git itself.

Brief (run-specific inputs only - the agent's system prompt owns every procedure):

```
DISPATCH MODEL: <extract-tier>
SHA: <sha>
commit_dump_path: .odoo-ai/forward-port/<slug>/commits/<sha>.dump
SOURCE SERIES: <e.g. 16.0>
SLUG: <slug>
TASK: Extract the business intent + behavioral contract of this one commit. Read commit
      message -> PR/issue -> test changes -> code comments (in that priority). OSM-ground the
      touched symbols at the SOURCE version. Write .odoo-ai/forward-port/<slug>/intents/<sha>.md.
      Do NOT copy diff hunks as intent. Do NOT classify the 4-outcome bucket (caller's job).
USER LANGUAGE: <lang | omit when English>
```

Aggregate each returned summary (`sha / intent_file / intent_one_liner / symbols /
4_outcome_hint / grounding`) into the P2 classify queue. Mark each commit
`status=extracted` in `checkpoint.json`.

---

## P2 - Classify + installable-probe (per-commit, OSM)

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

**Installable-probe (TARGET CLEAN-TIP rule).** For each touched module, read its `installable`
flag at the target clean-tip (BEFORE merge), via OSM or the target manifest:

```python
module_inspect(name='l10n_vn_edi', method='summary', odoo_version='18.0')   # read installable
```

DISPATCH the read-only sonnet leaf `odoo-installable-prober` ONLY when category-3 is AMBIGUOUS -
OSM returned `installable:True` at the target AND the module manifest was NOT touched by the
cherry-pick range, OR OSM was unreachable. Do NOT blanket-sweep every module: OSM already grounds
categories 1-2, so a probe there is wasted.

Pre-step before dispatch: delegate to git-surveyor (read-only) to write two files. Include
`repo: <main-checkout-root>` in the git-surveyor dispatch for cross-repo ports (the source
commits exist only in the main checkout after P0 bootstrap):

- `manifest_path`: read `<module>/__manifest__.py` at `target_ref` and write to
  `.odoo-ai/forward-port/<slug>/installable/<module>/manifest.py`
- `history_dump_path`: run a log-with-patch of manifest modifications (--follow --diff-filter=M
  on `<module>/__manifest__.py`) against `source_ref` and write to
  `.odoo-ai/forward-port/<slug>/installable/<module>/history.diff`

Assign the resulting absolute paths before launching the prober; the prober mandates both fields
and never runs git itself.

Dispatcher inputs (CANONICAL CONTRACT - pass exactly these keys):

```
{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }
```

- `repo_root` is the MAIN checkout root where git runs. The integration worktree does NOT exist
  at P2 (it is created at P4) - never reference it here. For a same-repo forward-port `repo_root`
  is the main clone of the repo holding both refs; for a cross-repo port it is the main clone that
  has the source remote added + fetched in the P0 bootstrap step (git-operator delegates: add
  source remote + fetch). The dispatcher populates `repo_root` deterministically from the P0-recorded checkout
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

Emit the Continuation Contract and YIELD (forward-port only EMITS the next hop; the run-driver
advances it):

```
next: odoo-solution-design
inputs:
  return_to: odoo-forward-port
  design_slug_hint: <slug>-fp-<sha>
  target_version: <target>
  modules: [<module-name>, ...]
  intent_records: [.odoo-ai/forward-port/<slug>/intents/<sha>.md]
  classification: <bucket-(c) summary>
```

`<slug>` is the forward-port run slug (`<source-series>-to-<target-series>`); `<sha>` is the
short SHA of the routed commit. Together `design_slug_hint` gives the design agent a
deterministic path for the output design doc (`<slug>-fp-<sha>`), ensuring the forward-port
re-entry can locate it without scanning.

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
tiers and REAL buckets, never guesses. Forward-port runs from the MAIN context, so it MAY call
`EnterPlanMode` / `ExitPlanMode` (a subagent cannot).

Procedure:
1. Main agent calls `EnterPlanMode`.
2. Main agent writes the implementation plan INSIDE Plan Mode: commit topology; per-commit model
   tier (the real triaged EXTRACT + ADAPT tiers); bucket (the real classification); installable
   routing per module; design-doc link for any commit P3 designed; merge batches.
3. Main agent calls `ExitPlanMode` -> Plan Mode UI shown.
4. User approves in the Plan Mode UI.

Red flags: a text-gate "approve" is NOT Plan Mode approval (two separate steps); `EnterPlanMode`
MUST come before any branch, worktree, or file touch.

After Plan Mode approval, delegate to git-operator: create the JOB-tier integration worktree
branched FROM B (Hard rule 1 - no branch before this point). Brief:

```
op: create integration worktree
scope: branch fp/<slug>, base <target-branch>
worktree: <path>/fp-integration
```

THEN write `.odoo-ai/forward-port/<slug>/plan.md` as the resume RECORD (not the gate - the gate
is Plan Mode above). Later phases and the checkpoint/continuation read it:

```markdown
# Forward-port plan: <source-series> -> <target-series> (<slug>)
Mode: continuous | one-shot
Integration worktree: <path>  (branched from <target-branch>, B untouched)
Commits (<N>, after --scope/--since filter, minus checkpoint done):

| SHA | summary | EXTRACT tier | ADAPT tier | bucket | installable routing | design_doc |
|-----|---------|--------------|------------|--------|---------------------|------------|
| abc1234 | double-post guard | sonnet | sonnet | (b) | normal | - |
| def5678 | new report engine | opus | opus | (c) do-now | normal | .odoo-ai/designs/...md |

Fable rows (if any): <m> - <why> (~2x opus). (confirmed in Plan Mode)
```

---

## P5 - Merge --no-commit (critical section)

Delegate to git-operator. Dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
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

Delegate to git-surveyor: list files changed in range `<merge-base>..<src-SHA>` (--name-only;
git-surveyor writes the file list, filtered to non-empty entries - these are the
merge-clean-but-source-touched autosilent-break candidates). Include `repo: <main-checkout-root>`
in the dispatch for cross-repo ports (the source commits exist only in the main checkout after
git-operator added the source remote and fetched at P0).

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

Delegate to git-surveyor: list files changed in range `<merge-base>..<src-SHA>` (--name-only;
git-surveyor writes the file list). Include `repo: <main-checkout-root>` in the dispatch for
cross-repo ports. From that list:

```bash
# Lane 1 (from git-surveyor result): ALL merged-touched .py (production AND tests/)
#   - filter the file list to *.py entries

# Lane 2 (from git-surveyor result): tests/ only
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
odoo-bin -d $ALLOC_DB_NAME --test-enable --test-tags <tag> --stop-after-init \
  --skip-auto-install --http-port=$ALLOC_HTTP_PORT 2>&1 | grep -E 'ERROR|setUpClass'
```

A collection failure (ImportError, setUpClass crash, missing fixture) means the tests NEVER
RAN in P9 - a count of `0 failed, N error(s)` is NOT a passing result (the setUpClass
crashed before any test method ran). Resolve every drift finding (P7 SYMBOL-BROKEN entries)
before entering the P8 adapt loop.

---

## P8 - Adapt (test-first; serial per-module within a commit; WORK-tier worktree per module for filesystem isolation)

For each touched module/WI, delegate to git-operator to create a child worktree off integration
and dispatch the adapt unit (serially - complete one module before starting the next within the
same commit):

```
op: create per-module child worktree from fp/<slug>
scope: branch fp/<slug>-<module>, path <path>/wt-<module>
worktree: <path>/wt-<module>
```

**Open-merge window (CRITICAL constraint).** During the open P5 merge window of the CURRENT
source commit - after git-operator ran `--no-commit` and before git-operator runs the P10
`commit` - `MERGE_HEAD` is live in the integration worktree. Git will reject any second merge
operation in that worktree until the first is committed or aborted (error: `MERGE_HEAD exists`).
Therefore: child worktrees CANNOT converge back into integration during this window. Adapt all
modules SERIALLY DIRECTLY in the integration worktree for the current commit's adapt pass - do
NOT fan out child worktrees. SSOT for the in-window adapt protocol: `[[fp-merge-absorption]]`
§Absorption-window.

**Per-commit vs absorb-all worktree.** Child-worktree fan-out is ONLY valid when the integration
HEAD is already committed - i.e. when processing a SUBSEQUENT source commit after the previous P10
commit has closed the prior merge. At that point `MERGE_HEAD` is gone, a child forks from a clean
committed tree, and converging back via merge works correctly. For an absorb-all run that merges
every commit in ONE no-commit merge, `MERGE_HEAD` is live throughout; do NOT fan out child
worktrees at all - resolve conflicts serially, per module, directly in the integration worktree,
and only resume child-worktree isolation once the absorbed merge is committed. Picking the wrong
mode yields child worktrees with a clean tree and an unresolved (invisible) conflict still sitting
in integration.

**8a - forward the test FIRST** (the test is the oracle; independence keeps it honest). Dispatch
`odoo-test-writing` in mode `adapt`:

```
TEST ADAPT MODE: forward this source test to the target platform.
SOURCE TEST (READ-FROM): <absolute-path-in-integration-worktree>/<module>/tests/<test_file>
  (merged working-tree content in the integration worktree; read the file from this path)
WRITE-TO: <absolute-child-worktree-path>/<module>/tests/<test_file>
  (write the adapted result here; for bucket (b) start from the READ-FROM content which
   may have conflict markers or auto-merged text - resolve it and write to WRITE-TO)
INTENT: <one-liner from intents/<sha>.md>   BUCKET: <a|b|c|d>
ODOO VERSION: <target>
BASE CLASS (target): <signature from test_base_classes(odoo_version='<target>') for the source
      test's base class - the kwargs the target setUpClass/setUp actually accepts, so the author
      does not re-introduce a dropped kwarg>
TARGET TEST EXAMPLES: <1-2 paths from find_test_examples(query='<feature>', odoo_version='<target>')
      that already test this behavior the target-idiomatic way - imitate their structure>
BROKEN TEST-SYMBOLS: <the P6 / P7 SYMBOL-BROKEN entries that land in THIS test file - the
      author must repair each (do not forward them verbatim)>
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

**8b - adapt the code** per bucket. Dispatch `odoo-coder` (backend) / `odoo-frontend-coder`
(frontend) with the FP-ENRICHED brief - the extra context a generic coder brief lacks:

```
DISPATCH MODEL: <adapt-tier>
REQUEST: Adapt the forwarded intent to the target platform.
INTENT RECORD: .odoo-ai/forward-port/<slug>/intents/<sha>.md   (the why - build to this, not the source diff)
BUCKET: <a skip-code | b 3-way+adapt | c re-implement on target idiom | d skip-code>
FAILING TEST (RED, written by the test-author above): <paths> - implement until GREEN; do NOT edit them.
NEW MODULE: <yes - apply installable:False checklist [[fp-installable-false]] | no>
MODULE SCOPE: <name>
  READ-FROM: <absolute-path-in-integration-worktree>/<module>/ (merged content; for bucket
    (b) 3-way+adapt start from these files - they hold the auto-merged or conflict-marked state)
  WRITE-TO: <absolute-child-worktree-path>/<module>/ (your child worktree; write ALL output here)
ODOO VERSION: <target>
WORKLOG: <slug> - read, then append.
MANIFEST/MIGRATION/PROVENANCE: apply C1 (keep TARGET version on conflict, never bump), C2 (migration-dir
  retarget), C3 (carry pre-existing source bugs faithfully, do not inline-fix) - [[fp-merge-absorption]]
USER LANGUAGE: <lang | omit when English>
```

**8c - installable:False modules** - two sub-cases, same manifest action. (i) **New module** (absent
at target): `installable: False`, comment `auto_install`/`application`, lint-fix only.
(ii) **Upgraded-then-forwarded** (target clean-tip = `installable:False` but merge carries `True`):
re-set to False + re-comment `auto_install`/`application` with `# TODO: Uncomment when upgrading
module to production-ready status` breadcrumb - then lint-fix only. SSOT: `[[fp-installable-false]]`.

**8c-bis - installable:False at target = LINT-ONLY lane.** BEFORE dispatching the coder/reviewer
for any module (new or pre-existing), confirm its target installable flag (already probed at P2 -
re-confirm here only if the manifest was touched by the merge):

```python
module_inspect(name='l10n_vn_edi', method='summary', odoo_version='18.0')   # read installable
```

(or read the target manifest's `installable` key). If `installable: False` at the target, brief
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

**8e - i18n: DISPATCH the `odoo-i18n` cluster, never inline.** When a forwarded commit adds or
changes translatable strings (new `.po`/`.pot`, new `string=`/labels/help, a new module), hand the
translation work to the dedicated cluster via a subagent dispatch (or `SUGGESTED_NEXT: odoo-i18n`
when the run is one-shot):

```
DISPATCH: odoo-i18n
SOURCE PO PATHS: <source-side .po/.pot files in the merged tree>
TARGET MODULES: <module name(s) whose translations need forwarding>
ODOO VERSION: <target>
SOURCE SERIES: <source-series>
TARGET LANGUAGES: <language codes inferred from the source .po filenames, e.g. vi_VN fr_FR;
    list one code per file (<lang>.po -> <lang>); if forwarding only a subset, list that
    subset explicitly>
```

`odoo-i18n` owns the non-destructive `.pot`/`.po` recipe and the isolated-DB export; this pipeline
forwards only the INTENT (which strings, which modules), never the export itself.

Converge each child worktree back to integration (serialized, keep SHA), then delegate to
git-operator to remove the child worktree at `<path>` (only after that module's P9 cycle
confirms GREEN - see SKILL.md P8 for the Tier-A worktree-persist rule). Mark `status=adapted`.

---

## P9 - Verify by behavior (PER-BATCH, in integration)

Resolve odoo-bin flags for the TARGET series via `cli_help` before invoking - the allocator
returns version-agnostic ports; flags and bootstrap behavior differ per series (e.g. v19
namespace package changes bootstrap; always pass `odoo_version=<target>` to `cli_help`).
Instance lifecycle protocol: `docs/reference/INSTANCE-LIFECYCLE.md`. Test invocation
conventions: `docs/reference/ODOO-TESTING.md`.

**Env-bootstrap (do this FIRST, before any odoo-bin call).** Read `.odoo-ai/context.md`
`## Verify environment` FIRST: if `verify_python` / `addons_path` are present, use them and
skip the instances.toml/venv archaeology below; fall back to the resolution chain
(`snippets/venv-resolution.md`) only when the section is absent or a listed repo path no
longer exists on disk. A multi-repo stack (e.g. Viindoo Standard spans 4 repos) needs EVERY
repo on disk and concatenated into `--addons-path` before verify - a module is invisible
(silent ImportError / "module not found") if its repo is absent. Build the addons-path from
all stack repos:

```bash
ADDONS_PATH=/path/repo-a/addons,/path/repo-b,/path/repo-c/addons,/path/repo-d
# verify each repo dir exists on disk; a missing repo = BLOCKED (NEEDS_CONTEXT), not a test red
```

**Install/verify the FULL transitive `depends` closure, not just the module you edited.**
A forwarded change can break a downstream depender that you never touched. Resolve the closure
per module, then install/verify its breadth:

```python
module_inspect(name='account_accountant', method='dependencies', odoo_version='18.0')
```

Union the closures of every directly-touched module and feed that whole set to `-i` below.

**Lint toolchain present BEFORE the lint gate.** The verify venv must have flake8 / ruff
(and eslint / prettier for frontend) installed, or the P11 lint gate silently no-ops. Confirm
`flake8 --version` and `ruff --version` resolve in the verify env before relying on a green lint.

```bash
# one ephemeral DB per BATCH, not per commit
python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral
#   -> ALLOC_DB_NAME (unique reserved name) / ALLOC_PORTS / ALLOC_TOKEN
#   (cache TOKEN in the batch worklog)
#   ALLOC_PORTS includes a free HTTP port -> export it as ALLOC_HTTP_PORT
#
#   The allocator reserves the DB name + ports but does NOT create the DB.
#   The -i run below performs Odoo create-on-init, which builds the DB.
#   On release/gc the allocator drops it through Odoo (raw dropdb only as fallback).
#   CREATEDB-role probe still degrades ephemeral -> exclusive when the role lacks it,
#   because Odoo create-on-init also requires CREATEDB (same invariant as before).

# install the full closure once. --skip-auto-install ISOLATES auto_install modules that
# would otherwise be pulled in silently and mask (or fabricate) a break. --http-port binds the
# allocator-issued free port: --no-http does NOT prevent the bind a running HttpCase performs,
# so two parallel batches collide on the default 8069 - always pin the allocated port.
odoo-bin -d $ALLOC_DB_NAME -i mod_a,mod_b --test-enable --stop-after-init \
  --skip-auto-install --http-port=$ALLOC_HTTP_PORT 2>&1 | tee install.log
# The closure suite can be very large. MAY narrow with --test-tags to touched modules +
# direct dependers (/mod_a,/mod_b), but NEVER narrow to only the edited module - a
# forwarded change can break tests in a downstream depender, and a module-only tag would
# hide that. Default: no --test-tags (run full closure); narrow only when the untagged
# run is prohibitively large, and record the tag used in merge-log.md.
# subsequent same-batch commits touching a subset: -u <changed_mod> (skip full -i),
# keep --skip-auto-install --http-port=$ALLOC_HTTP_PORT

python3 <plugin>/scripts/lib/allocator.py release $ALLOC_TOKEN
```

**Confirm EACH module actually loaded; Odoo silent-skips, it does not error.** An
`installable: False` module (or one excluded by `--skip-auto-install`) is skipped with NO error
line - a green run is NOT proof it installed. Parse the log for a `Loading module <X>` line per
module in the closure:

```bash
for m in mod_a mod_b mod_c; do
  grep -q "Loading module $m" install.log || echo "NOT LOADED: $m"   # absent = never installed
done
```

Reconcile the NOT-LOADED set against the installable scan (`[[fp-symbol-survival-check]]`
section 2.5f): a module that is `installable: False` at the target is EXPECTED not to load -
route it to the 8c-bis lint-only lane and do NOT count its absence as a break. A module that is
installable AND missing its Loading line is a real failure - investigate before reading any test
count.

**Recover an orphaned odoo-bin before re-running.** A crashed/killed batch can leave an
odoo-bin process holding the DB and port. Kill ONLY the process bound to this batch's DB (match
the unique `$ALLOC_DB_NAME`, never a bare `odoo-bin` that would self-match this very command or a
sibling batch), then release the lease so the allocator can reclaim the port:

```bash
pkill -f "odoo-bin.*$ALLOC_DB_NAME"   # narrow match - never `pkill -f odoo-bin`
python3 <plugin>/scripts/lib/allocator.py release $ALLOC_TOKEN
```

- **RED-then-GREEN (whole module):** target suite must be green.
- **Confirm-by-toggle (FP-delta tests only):** disable each newly-forwarded adapt -> that test
  must go RED -> restore. Proves the test exercises the adapted behavior. Do NOT toggle the whole
  suite.
- **Triage red:** Triage EVERY red against a clean-tip baseline before calling it a
  regression - whether the red is in the edited module or in a co-installed dependency pulled
  in by the closure. Run the red test on a clean target tip (no absorption, full closure
  installed the same way). Red there too = pre-existing (record in merge-log.md, do not fix,
  do not block). Green on clean / red only after absorption = FP-delta (fix before committing).
  A red in a co-installed dep you never touched is almost always pre-existing - prove it with
  the clean-tip baseline, do not assume. Never widen an assertion to hide a pre-existing failure.
  For source-series follow-through on a pre-existing red, apply C3 - carry faithfully + open a
  source issue (resolvable remote) or record it; see `[[fp-merge-absorption]]` § Triage / C3.
- **Baseline a failed INSTALL the same way.** If a module fails to install, re-run its `-i`
  on clean `origin/<target-branch>` (no absorption, no merge). Fails there too = a PRE-EXISTING
  break in the target series, NOT FP-introduced - record it in `merge-log.md` and do NOT block
  the forward-port on it. Only an install that is green on clean origin/target and red after
  absorption is an FP-delta to fix.
- **CREATEDB-role footgun:** verify `SELECT rolcreatedb FROM pg_roles WHERE rolname =
  current_user;` returns `t` before a parallel batch; if `f`, serialize the batch.

Full per-batch + allocator protocol: `[[fp-merge-absorption]]`. Mark `status=verified`.

---

## P10 - Gate merge (STOP, per batch)

Present `merge-log.md` and wait for human-confirm. On confirm, delegate to git-operator:

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

## P11 - PR + review

Delegate the push to git-operator (resolve origin URL via `git remote get-url origin`):

```
op: push fp/<slug> to origin (NOT B)
scope: branch fp/<slug>
worktree: <path>/fp-integration
remote: resolve via `git remote get-url origin`
```

Delegate PR creation to github-operator:

```
op: create PR
base: <target-branch>
head: fp/<slug>
title: "..."
body: "..."
remote: resolve from `git remote get-url origin`
```

Run `odoo-code-review` inline (via the Skill tool, from the orchestrating context) for the
forward-port pitfall (a forwarded test still coupled to the source API). NEVER squash (squash
mints a new SHA, defeats merge-base advance). B stays LOCKED -
the PR adds only the merge commits. Present the PR URL and wait for the human to merge.

**Attribute every finding to the FP diff before rating it.** A reviewer rating the whole
file blames the forward-port for code it never touched. Before rating any finding, confirm the
line is actually in the forward-port delta. Delegate to git-surveyor: three-dot diff
(`origin/<target-branch>...fp/<slug> -- <file>`, only what the FP added to `<file>`).

A finding on a line NOT in this diff is pre-existing - note it separately, do not block the PR on
it (flag it, do not gate the forward-port on it).

**Per finding, apply C3 (fix old version first).** Check whether the same defect exists at the source
series. If it does, it is a **pre-existing source bug** (inherited - forwarded faithfully, not introduced
by this port): route the fix UPSTREAM via a source-series issue (delegate to github-operator when a source
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

---

## Cleanup (after human merge)

Delegate to git-operator: remove integration worktree and delete the integration branch.

```bash
# Delegate to git-operator:
#   op: worktree remove <path>/fp-integration
#   confirmed: yes - forward-port is merged
git worktree list          # confirm no dangling fp/<slug>-* child worktrees
# Delegate to git-operator:
#   op: branch delete fp/<slug>
#   confirmed: yes - forward-port is merged
```

Leave `.odoo-ai/forward-port/<slug>/` for the next continuous run's resume (it is gitignored and
the checkpoint lets tomorrow's run skip done commits).
