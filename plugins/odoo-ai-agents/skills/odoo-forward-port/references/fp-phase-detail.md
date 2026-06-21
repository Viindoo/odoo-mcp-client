<!-- Reference for odoo-forward-port/SKILL.md § The 8-phase pipeline. Loaded as needed.
     Per-phase git commands, dispatch-brief templates, and worklog formats. The SKILL.md body
     carries the contract; this file carries the verbatim commands and brief text. -->

# Forward-Port Pipeline - per-phase execution detail

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`.odoo-ai/forward-port/<slug>/` (gitignored). Every Odoo Semantic call passes a concrete
`odoo_version=` - never omit it, never rely on a default; the version pin is per-API-key state
that any concurrent agent can overwrite.

---

## P0 - Plan gate (STOP)

```bash
# 1 - resume: read prior state, skip done commits
cat .odoo-ai/forward-port/<slug>/checkpoint.json 2>/dev/null   # {<sha>: status}

# 2 - enumerate the commits to forward (read-only; no worktree, no branch yet)
# Same-repo (both refs on origin): compute merge-base locally
MB=$(git merge-base <target-branch> <source-ref>)
# Cross-repo: git remote add source <source-repo-clone-url> then fetch, then:
#   MB=$(git merge-base <target-branch> source/<branch>)
git fetch source   # cross-repo only; omit for same-origin refs
git log --no-merges ${MB}..<source-ref>   # apply --scope <paths> / --since <date>
```

Map each `--scope` module name to its directory path before passing to `git log -- <paths>`
(module `l10n_vn` -> `l10n_vn/`; resolve via manifest location - may be at repo root or
under an addons subdir, e.g. `addons/l10n_vn/`).

For each commit, triage the EXTRACT tier INLINE (`git show --stat <sha>`; for an override-depth
question, one `find_override_point` probe) per `references/fp-triage-table.md` Table 1. Emit
`plan.md`:

```markdown
# Forward-port plan: <source-series> -> <target-series> (<slug>)
Mode: continuous | one-shot
Integration worktree: <path>  (branched from <target-branch>, B untouched - created after approval)
Commits (<N>, after --scope/--since filter, minus checkpoint done):

| SHA | summary | EXTRACT tier | bucket-guess | scope |
|-----|---------|--------------|--------------|-------|
| abc1234 | double-post guard | sonnet | (b) | account/ |

Fable rows (if any): <m> - <why> (~2x opus). Confirm fable?
```

Then STOP. Do NOT create any branch or worktree, run no extraction, until the user approves
(`approve` / `go` / `yes`).

On approval: create the JOB-tier integration worktree branched FROM B (Hard rule 1 - no branch
before this point):

```bash
git worktree add -b fp/<slug> <path>/fp-integration <target-branch>
```

On `cancel`: stop (no worktree was created, nothing to remove).

---

## P1 - Intent extract (PARALLEL, READ-ONLY)

Dispatch one `odoo-intent-extractor` per commit as a subagent launch - real tool calls, never
narrated. Set BOTH the `model` parameter (the triaged EXTRACT tier) and the brief. Concurrency:
Mode B budget (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`); rolling-window
beyond the budget. No child worktree - extraction is read-only on git history + OSM.

Brief (run-specific inputs only - the agent's system prompt owns every procedure):

```
DISPATCH MODEL: <extract-tier>
SHA: <sha>
SOURCE SERIES: <e.g. 16.0>
SLUG: <slug>
TASK: Extract the business intent + behavioral contract of this one commit. Read commit
      message -> PR/issue -> test changes -> code comments (in that priority). OSM-ground the
      touched symbols at the SOURCE version. Write .odoo-ai/forward-port/<slug>/intents/<sha>.md.
      Do NOT copy diff hunks as intent. Do NOT classify the 4-outcome bucket (caller's job).
USER LANGUAGE: <lang | omit when English>
```

Aggregate each returned summary (`sha / intent_file / intent_one_liner / symbols /
4_outcome_hint / grounding`) into the Phase 2 classify queue. Mark each commit
`status=extracted` in `checkpoint.json`.

---

## P2 - 4-outcome classify (per-commit, OSM)

```python
set_active_version(odoo_version='17.0')                          # pin target; reachability probe
api_version_diff(symbol='account.move._post', from_version='16.0', to_version='17.0')
model_inspect(model='account.move', method='summary', odoo_version='17.0')
```

Assign exactly one bucket a/b/c/d per `[[fp-intent-4outcome]]` (read it - do not re-derive the
definitions). Append one row per commit to `merge-log.md` (intent / bucket / reason / evidence -
no blank Reason or Evidence cell). `odoo-version-diff` forward-port mode supplies the per-symbol
bucket suggestion when the diff is large. Refine the commit's ADAPT tier now that the bucket is
known (bucket a/d -> haiku, test-only).

---

## P3 - Git merge --no-commit (critical section)

```bash
# continuous - keep the source SHA
git merge --no-ff --no-commit <src-SHA>

# one-shot only (source frozen)
git cherry-pick -n <src-SHA>
```

Only one merge in flight (shared git index). Do NOT commit - the working tree is the absorption
zone through Phase 5. Full protocol incl. absorption window order: `[[fp-merge-absorption]]`.

---

## P3.5 - Symbol-survival check (MUST, before adapt)

```bash
# files with conflict markers
git diff --check ; grep -rn '^<<<<<<<' .

# merge-clean-but-source-touched files (autosilent-break candidates)
git log --name-only --format="" <merge-base>..<src-SHA> | sort -u | grep -v '^$'
```

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
Phase 4 on those files. Full contract: `[[fp-symbol-survival-check]]`.

**Run on `tests/` files too** - test files auto-merge silently exactly like production code and
crash at collection (base-class kwarg drift, broken import, dynamic `ref()`), never reaching
Phase 5 if collection itself fails. Do NOT re-derive the test-survival logic here - apply the
seven auto-merge-silent symbol classes from `[[fp-symbol-survival-check]]` section 2.5 (it already
states production AND `tests/` scope). The merge-clean-but-source-touched enumeration above
already lists test files; feed them through the same section-2.5 grounding, do not filter them
out.

---

## P4.5 - Pre-adapt drift scan (MUST, before the behavioral loop)

This gate is DISTINCT from the P3.5 TEST-survival sub-check:
- **P3.5 TEST-survival** uses `tests_covering` / `test_coverage_audit` (OSM cross-version
  symbol lookup) to detect test methods that REFERENCE a field/model removed at the target.
  It operates at the OSM symbol-graph level and covers both production and test code.
- **P4.5** uses the seven static symbol classes from `[[fp-symbol-survival-check]]` section 2.5
  over two lanes: (d) python-import + (e) AST-pyflakes + (g) ORM create/write dict-key run over
  ALL merged-touched `.py` (production AND `tests/`) - (d)(e) catch runtime NameError and (g)
  catches an Invalid-field key (autosilent: pyflakes does NOT flag it) before P5; the remaining
  classes (a)(b)(c)(f) and the collection ACCEPTANCE GATE apply to the `tests/` lane only.

The two checks are COMPLEMENTARY: P3.5 catches symbol-graph breaks via OSM; P4.5 catches
static grep / import / AST breaks and blocks entry to P4 when test collection itself would
fail.

**Enumerate scope - two lanes:**

```bash
# Lane 1: ALL merged-touched .py (production AND tests/) - for compile + pyflakes + ORM dict-key
git log --name-only --format="" <merge-base>..<src-SHA> | sort -u | grep '\.py$'

# Lane 2: tests/ only - for collection ACCEPTANCE GATE and the test-specific classes (a)(b)(c)(f)
git log --name-only --format="" <merge-base>..<src-SHA> | sort -u | grep '\.py$' \
  | grep 'tests/'
```

For Lane 1 files apply classes (d) + (e) (`py_compile` + `pyflakes`) AND (g) (ORM create/write
dict-key scan) over ALL .py - production AND tests. Treat F821 on a production file as a runtime
NameError that would crash module load, not a nit; treat a (g) dead key on a production call site
the same way - it raises `Invalid field` at load/run yet pyflakes stays silent. For Lane 2 files
additionally apply (a) (b) (c) (f).

Record findings as `SYMBOL-BROKEN | <symbol/path> | <file>:<line> | <class> | evidence` and
append to `merge-log.md`. These become the `BROKEN TEST-SYMBOLS` input to the 4a brief.

**ACCEPTANCE GATE (collection clean) - mandatory before Phase 4 starts:**

At P4.5 no instance DB has been acquired yet (allocator runs at P5) - use the `pytest --collect-only` path; the odoo-bin collection option requires first acquiring a temp DB.

```bash
# pytest collection smoke-test
python -m pytest <test_files> --collect-only -q 2>&1 | tail -20
# OR Odoo collection (for TestCase subclasses with setUpClass) - requires a DB acquired via allocator
odoo-bin -d $ALLOC_DB_NAME --test-enable --test-tags <tag> --stop-after-init \
  --skip-auto-install --http-port=$ALLOC_HTTP_PORT 2>&1 | grep -E 'ERROR|setUpClass'
```

A collection failure (ImportError, setUpClass crash, missing fixture) means the tests NEVER
RAN in Phase 5 - a count of `0 failed, N error(s)` is NOT a passing result (the setUpClass
crashed before any test method ran). Resolve every drift finding (P4.5 SYMBOL-BROKEN entries)
before entering the Phase 4 adapt loop.

---

## P4 - Adapt (test-first; serial per-module within a commit; WORK-tier worktree per module for filesystem isolation)

For each touched module/WI, create a child worktree off integration and dispatch the adapt unit
(serially - complete one module before starting the next within the same commit):

```bash
git worktree add -b fp/<slug>-<module> <path>/wt-<module> fp/<slug>
```

**Per-commit vs absorb-all worktree.** The child-worktree-per-module command above applies
when each source commit is committed on integration before the next is merged (one-shot
`cherry-pick -n`, or continuous merging one SHA at a time) - the child forks from a committed tree
and sees no in-flight conflicts. For an absorb-all run that merges every commit in ONE
`git merge --no-commit`, the conflicts live in the integration worktree's WORKING TREE
(uncommitted); a child worktree forked off the uncommitted integration HEAD CANNOT see them. In
that case do NOT run `git worktree add` for conflict resolution - resolve conflicts serially, per
module, directly in the integration worktree, and only resume child-worktree isolation once the
absorbed merge is committed. Picking the wrong mode here yields child worktrees with a clean tree
and an unresolved (invisible) conflict still sitting in integration.

**4a - forward the test FIRST** (the test is the oracle; independence keeps it honest). Dispatch
`odoo-test-writing` in mode `adapt`:

```
TEST ADAPT MODE: forward this source test to the target platform.
SOURCE TEST: <path(s) in the merged tree>
INTENT: <one-liner from intents/<sha>.md>   BUCKET: <a|b|c|d>
ODOO VERSION: <target>
BASE CLASS (target): <signature from test_base_classes(odoo_version='<target>') for the source
      test's base class - the kwargs the target setUpClass/setUp actually accepts, so the author
      does not re-introduce a dropped kwarg>
TARGET TEST EXAMPLES: <1-2 paths from find_test_examples(query='<feature>', odoo_version='<target>')
      that already test this behavior the target-idiomatic way - imitate their structure>
BROKEN TEST-SYMBOLS: <the P3.5 / P4.5 SYMBOL-BROKEN entries that land in THIS test file - the
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

`BROKEN TEST-SYMBOLS` is the subset of the P3.5 symbol-survival finding list (plus any P4.5 drift
finding) whose `<file>` is this test file - copy those rows in verbatim; omit the line when the
list is empty for this file.

**4b - adapt the code** per bucket. Dispatch `odoo-coder` (backend) / `odoo-frontend-coder`
(frontend) with the FP-ENRICHED brief - the extra context a generic coder brief lacks:

```
DISPATCH MODEL: <adapt-tier>
REQUEST: Adapt the forwarded intent to the target platform.
INTENT RECORD: .odoo-ai/forward-port/<slug>/intents/<sha>.md   (the why - build to this, not the source diff)
BUCKET: <a skip-code | b 3-way+adapt | c re-implement on target idiom | d skip-code>
FAILING TEST (RED, written by the test-author above): <paths> - implement until GREEN; do NOT edit them.
NEW MODULE: <yes - apply installable:False checklist [[fp-installable-false]] | no>
MODULE SCOPE: <name> @ <child-worktree path> - write ONLY within this module.
ODOO VERSION: <target>
WORKLOG: <slug> - read, then append.
USER LANGUAGE: <lang | omit when English>
```

**4c - new module:** apply `[[fp-installable-false]]` - `installable: False`, comment
`auto_install`/`application`, lint-fix only, no content upgrade.

**4c-bis - installable:False at target = LINT-ONLY lane.** BEFORE dispatching the coder/reviewer
for any module (new or pre-existing), confirm its target installable flag:

```python
module_inspect(name='l10n_vn_edi', method='summary', odoo_version='18.0')   # read installable
```

(or read the target manifest's `installable` key). If `installable: False` at the target, brief
the coder in **lint-only mode**: run flake8 / eslint / prettier / ruff and fix ONLY syntax/lint
breakage to keep CI green - do NOT adapt business logic, do NOT upgrade content. Pass
`LINT-ONLY: yes` in the 4b brief and the pointer `[[fp-installable-false]]`. The single exception
to "no logic change" is a syntax/lint error that itself blocks the file from parsing.

**4d - migration script:** rename the `migrations/<src-series>.x.y.z` dir to `<tgt-series>` ONLY
when the gate `installed < parse(dir) <= current` holds (else the script lands inert - silent).
The rename is idempotent (re-run safe). See `odoo-data-migration` for the script body. After the
rename, sweep the migration body for log strings / hardcoded series literals still naming the
SOURCE series (a `_logger.info("... 17.0 ...")` or a version string left from the source) - they
survive `git mv` unchanged and mislead the operator:

```bash
grep -rn '<src-series>' migrations/<tgt-series>/   # e.g. grep -rn '17\.0' migrations/18.0/
```

**4e - i18n: DISPATCH the `odoo-i18n` cluster, never inline.** When a forwarded commit adds or
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

Converge each child worktree back to integration (serialized, keep SHA), then
`git worktree remove <path>`. Mark `status=adapted`.

---

## P5 - Verify by behavior (PER-BATCH, in integration)

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
(and eslint / prettier for frontend) installed, or the P7 lint gate silently no-ops. Confirm
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
route it to the 4c-bis lint-only lane and do NOT count its absence as a break. A module that is
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
- **Baseline a failed INSTALL the same way.** If a module fails to install, re-run its `-i`
  on clean `origin/<target-branch>` (no absorption, no merge). Fails there too = a PRE-EXISTING
  break in the target series, NOT FP-introduced - record it in `merge-log.md` and do NOT block
  the forward-port on it. Only an install that is green on clean origin/target and red after
  absorption is an FP-delta to fix.
- **CREATEDB-role footgun:** verify `SELECT rolcreatedb FROM pg_roles WHERE rolname =
  current_user;` returns `t` before a parallel batch; if `f`, serialize the batch.

Full per-batch + allocator protocol: `[[fp-merge-absorption]]`. Mark `status=verified`.

---

## P6 - Gate merge (STOP, per batch)

Present `merge-log.md` and wait for human-confirm. On confirm:

```bash
git commit -m "fp: absorb <src-SHA> - <one-line summary> [bucket <x>]"
```

Buckets (a)/(d) STILL commit (keeps SHA, advances merge-base - Hard rule 7); the message records
the bucket + reason so the empty diff is not flagged. Update `checkpoint.json` `{<sha>: done}`.
More commits/batches remain -> LOOP to P4 (recreate WORK-tier worktrees from the updated
integration).

---

## P7 - PR + review

```bash
git push origin fp/<slug>                          # push integration, NOT B
gh pr create --base <target-branch> --head fp/<slug> --title "..." --body "..."
```

Run `odoo-code-review` inline (via the Skill tool, from the orchestrating context) for the
forward-port pitfall (a forwarded test still coupled to the source API). NEVER squash (squash
mints a new SHA, defeats merge-base advance). B stays LOCKED -
the PR adds only the merge commits. Present the PR URL and wait for the human to merge.

**Attribute every finding to the FP diff before rating it.** A reviewer rating the whole
file blames the forward-port for code it never touched. Before rating any finding, confirm the
line is actually in the forward-port delta:

```bash
git diff origin/<target-branch>...fp/<slug> -- <file>   # three-dot: only what the FP added
```

A finding on a line NOT in this diff is pre-existing - note it separately, do not block the PR on
it (flag it, do not gate the forward-port on it).

**Per finding, check whether the bug already exists in the SOURCE series.** For each finding,
open the source-series PR / branch and check if the same defect is present there. If it is, the
bug is INHERITED (forwarded faithfully, not introduced here) - route a fix UPSTREAM to the source
series; do NOT patch it silently inside the forward-port (that would diverge source and target and
hide the real fix location). Record `inherited -> upstream` in `merge-log.md` and carry the
faithful forward.

**Narrow a field-existence question with a direct lookup, not a model_inspect retry.** When
a finding hinges on whether one field still exists / changed type at the target, query that field
directly instead of re-dumping the whole model:

```python
entity_lookup(kind='field', model='account.move', field='payment_state', odoo_version='18.0')
```

**installable:False modules get a LINT-ONLY review.** For any module that is
`installable: False` at the target (4c-bis lane), the reviewer rates ONLY syntax / lint findings -
do NOT raise business-logic / behavior findings against a module that does not even install at the
target. Mark such findings out-of-scope for this forward-port.

---

## Cleanup (after human merge)

```bash
git worktree remove <path>/fp-integration
git worktree list          # confirm no dangling fp/<slug>-* child worktrees
git branch -d fp/<slug>
```

Leave `.odoo-ai/forward-port/<slug>/` for the next continuous run's resume (it is gitignored and
the checkpoint lets tomorrow's run skip done commits).
