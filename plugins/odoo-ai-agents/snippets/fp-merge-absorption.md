<!-- SSOT snippet. Referenced by odoo-forward-port and every agent that runs a merge or verify
     step of a forward-port. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md. -->

# FP Merge Absorption (merge protocol + per-batch verify)

## Git operation - ONE merge for the whole range, ONE merge commit

**The unit of the git operation is the RANGE, never the commit.** A forward-port run absorbs
every commit after the merge base of the target and `<source-ref>` with a SINGLE merge of the
range's TIP commit, and closes it with a SINGLE merge commit - the shape an ordinary branch-level
merge has. Every commit in the range becomes an ancestor of that merge commit, so every source
SHA is preserved and the merge-base advances to the tip in one step.

Invoke the **`git-toolkit:git-ops`** skill (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
- `op: merge the range ending at <src-tip-SHA> as ONE true merge and stop before committing it`
  (request worktree isolation), where `<src-tip-SHA>` is the LAST (newest) commit of the range
  this run forwards - after any `--since` filter.

On return, the working tree is the absorption zone for the WHOLE range; all adapt work (§
Absorption window) happens there, inside this one open merge window. When adapt is complete,
invoke `git-toolkit:git-ops` again, ONCE:
- `op: conclude the merge with one commit`, `message: "fp: absorb <src-first-SHA>..<src-tip-SHA> - <one-line summary>"`

A true merge commit, never a fast-forward: the source history enters the DAG of the target
branch and the next run's range listing no longer sees any commit of the range.

### Two banned shapes

1. **One merge per commit.** It mints N merge commits for ONE logical forward-port and resolves
   every hunk touched by several source commits once per commit instead of once per run.
2. **Cherry-pick, at ANY granularity.** Each cherry-pick mints a FRESH SHA on the target: the
   merge-base does not move, so every later run re-encounters every commit and re-resolves every
   conflict. No mode, flag or special case licenses it.

**Batching does NOT reinstate either shape.** A batch is a VERIFY unit, not a git unit: when the
human splits the run at the plan gate, each batch boundary is a source SHA, and batch *k* merges
the LAST SHA of batch *k* - `N` batches produce at most `N` merge commits; the default (one batch)
produces exactly ONE; a batch is never "one commit each". **Landing only PART of a source branch is a `<src-tip-SHA>` choice:** merge
the sub-range's TIP; the commits after it stay out, every SHA that lands is preserved, and the
merge-base advances to exactly that point. A frozen source merges like any other.

## Absorption window (inside the ONE uncommitted merge)

Between the uncommitted merge git-ops opened and the commit step, the working tree is the
absorption zone for the whole range: ONE window per run (or per batch), opened once, open across
every module's adapt work, closed once. In this order:

1. Symbol-survival check - [[fp-symbol-survival-check]] BEFORE touching any file, ONCE over the
   merged result of the whole range.
2. Resolve conflict markers in source-touched files (3-way merge, platform-adapt per bucket,
   [[fp-intent-4outcome]]). A file touched by several commits in the range is resolved ONCE,
   against the range's combined result.
2a. **Manifest version (C1) - set by rule, only when the range changed the module's `version` on
    the source.** The true merge already carries whatever the source commit did to the module
    descriptor (the filename per series: `odoo-era-boundaries.md` row 6). `M` = the target module's
    version BEFORE this forward-port, `S` = its version at the source tip, both read on the module
    part after the series prefix and compared as dotted integer tuples; `+ 1` adds one to the last
    component. For a module that exists on the target, whether or not the merge conflicted on
    that field:
    - installable on both series (`installable_false=no` on its `merge-log.md` row; an absent
      `installable` key counts as installable - `[[fp-installable-false]]` § Discriminator):
      `version` = `max(M + 1, S)`;
    - `installable: False` at the target (`installable_false=yes`): `version` = `S`, the source
      version - the module is a dormant copy of the source code and its version matches the code
      it carries.
    A range that does not change the module's `version` on the source leaves the target's value
    as it is, in both cases; a module new on the target keeps the version the merge carries. Write
    the result in the form the target descriptor already uses. Never merge-pick one side's value
    and never bump for any other reason.
3. Adapt per module, code first: ONE `odoo-coding` node adapts the code, then its test leg forwards
   and adapts the tests and proves each
   (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Code first, then the test leg).
4. Fix any lint/eslint/prettier errors introduced by the merge.
5. Invoke `git-toolkit:git-ops` to commit - the merge commit encapsulates the entire
   translation cost.

Do NOT ask git-ops to commit until verify is green (§ Verify protocol). Do NOT open a second
uncommitted merge while one is in progress (the index is shared; git-toolkit enforces this).

## Migration dir retarget (C2) - distinct from C1

A source-series commit adds `migrations/<src-series>.a.b.c/`. `M` and `S` are as in C1. A migration
runs only on UPGRADE and only when `installed < dir_version <= manifest`. Decide each dir at P9.6,
after P9 is green and before P10 concludes the merge - never inside P8's adapt loop - in this order:

1. **Precondition - installability.** Every module the script acts on (the owner of the dir and
   each module whose tables, fields or records the script reads or writes) is `installable` at the
   target tip (the clean-tip read of `[[fp-installable-false]]`; an absent `installable` key counts
   as installable). Otherwise FORWARD the dir unchanged under its source-series name and record
   why on the commit's `merge-log.md` row (`<sha> | C2 forwarded | <module> not installable at
   target tip`). A module `installable:False` at the target is the lint-only lane, so its own
   migrations are always forwarded unchanged.
2. **Decision - does the TARGET have the problem the script solves?** Read the script and the
   target's code and data model for that module: the field, model or data shape the script repairs
   exists on the target and is affected the way the source was. YES -> RETARGET. NO -> FORWARD the
   dir unchanged under `<src-series>.a.b.c` and record why on the `merge-log.md` row
   (`<sha> | C2 forwarded | target has no <problem the script solves>`). A dir forwarded under its
   source-series name still fires for source-to-target jumpers below `a.b.c` and never on a
   native-target database.
3. **Retarget.** Name the dir FULL `<tgt-series>.V`, where `V` is the version C1 sets for the
   module - step 1 admits only modules installable at the target, so `V = max(M + 1, S)`, always
   above `M`, and the dir fires on a deployed target database sitting at `M`. When the range
   carries no other `version` change for the module, a retarget still sets the manifest to that
   `V`. Invariant: the dir version is `<=` the final manifest version.

A retargeted dir name is always FULL `<tgt-series>.x.y.z`. Migrations must be idempotent: a
fully-updated source DB jumping the major re-runs a retargeted tip migration. After the rename,
sweep the body for source-series literals (log strings, version constants).

Why (Odoo source): `adapt_version()` in `odoo/modules/module.py` prefixes a short manifest
`a.b.c` to `<series>.a.b.c` and stores it as `installed_version` (from a later series it also
validates the version string - [[odoo-version-pivots]]); `MigrationManager.migrate_module`
(`odoo/modules/migration.py`) runs a dir only when `installed_version < dir <= <series>.<manifest>`.
A dir left at `<src-series>.a.b.c` therefore silently skips every DB already at the source-series
state when it upgrades to the target series.

Worked (`V = max(M + 1, S)`): M=0.1.2, S=0.1.2 -> V=0.1.3, dir `<tgt>.0.1.3` (`<tgt>.0.1.2` never
runs: `<tgt>.0.1.2 < <tgt>.0.1.2` is false). M=0.1.1, S=0.1.5 -> V=0.1.5. M=0.1.4, S=0.1.2 ->
V=0.1.5. A source migration repairing a shape the target never had -> no retarget, dir stays
`<src-series>.a.b.c`, reason on the `merge-log.md` row; the manifest still follows C1.

## Skip-code-but-still-absorb rule

Outcome buckets (a) and (d) of [[fp-intent-4outcome]] require NO adapt diff: **(a) already
satisfied** - the target platform already provides the behavior; forward its tests only, the
node's absorption probe confirms or re-buckets it. **(d) no longer relevant** - the source commit
worked around a platform limitation the target has removed.

A CONFLICTED hunk of an (a)/(d) commit resolves to the TARGET side. A CLEANLY-merged hunk stays as
the merge left it, so an (a)/(d) commit's source code can be in the tree - which is why the
absorption probe takes that code out of play first
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Absorption probe).

**In both cases the commit is still ABSORBED - never excluded from the merge range.** A bucket is
a statement about ADAPT WORK, never about git topology: narrowing or splitting the merged range
leaves the merge-base behind the commit and the next forward-port encounters it again. Record each
(a)/(d) bucket and its reason on that commit's `merge-log.md` row and name them in the merge
commit's message body.

## Verify protocol - per-batch, not per-commit

Verify the WHOLE batch on ONE ephemeral instance. The DEFAULT batch is the whole run; splitting
into batches is a human decision at the plan gate, and each batch still merges its own range TIP
once.

**Delegate the instance - never a bare lease tool or `odoo-bin` invocation.** Provisioning,
install and test-run go through the `odoo-instance` skill via the Skill tool, which enforces the
instance HARD RULES (demo by build purpose, lint-module install, per-version `cli_help`
grounding) and the forward-port `WORKTREE_PATH` re-root that keeps verification pointed at the
adapted worktree.

1. Collect the batch (module set = every module touched by the batch's commits).
2. Dispatch `odoo-instance` ONCE for the batch: `operation: run-tests`, `GATE_ROLE: node-verify`,
   `persist: ephemeral`, `modules: <the batch's affected modules>`, `test_tags: <`/<m>` per module
   in that list - `${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`>`, `mode: fresh`
   (install + test in one pass; the lease only reserves the DB name/ports). Memory-cap is applied
   inside `odoo-instance-ops` (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`). The
   concrete dispatch brief with the `WORKTREE_PATH` re-root:
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-forward-port/references/fp-phase-detail.md` P9.
3. For a re-verify after a fix inside the SAME batch, or a SUBSEQUENT batch touching only a
   subset, re-dispatch `odoo-instance` with the SAME returned `INSTANCE_HANDLE`, `mode: reuse`
   (`-u` semantics) and `GATE_ROLE: node-verify` on the changed modules only.
4. Release the instance once no later step of this run needs it - after P10 has concluded the LAST
   batch's merge, never between batches. P11 acceptance never reuses this handle (its database
   carries the series' test-build demo shape; acceptance provisions its own demo-carrying cluster).
   Call `lease_release` with the cached `lease_token`/`run_id` - you are its run-level owner
   (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1); it stops the bound process
   group first, then drops the DB - never a raw `dropdb` or a `pkill`.

Cache the returned `lease_token`/`run_id` in the batch's worklog entry ([[worklog-contract]]) so a
crash during the batch can release the DB.

## Green suite + break-check records

- **Green suite (all tests):** the full suite for the target module must be green. A pre-existing
  red test is triaged (below), never fixed as part of this forward-port.
- **Break-checks (FP-delta tests only):** every test NEWLY forwarded or adapted in this batch was
  break-checked - or, for a bucket-(a) commit, absorption-probed - by the node's test leg at P8
  (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Break-check record). A test the
  report does not cover is unverified - send it back to the module's P8 adapt node; the verify run
  never breaks code itself.

## Triage: FP-delta vs pre-existing failure

A `--test-enable` build runs a Python suite AND one or more browser (Hoot/QUnit) suites; the
`instance-ops` block reports them in separate fields (`failed`/`errors` for Python,
`js_failed_reported`/`js_failed_tests` for the browser suites). **Triage each JS RUN separately** -
a run is one browser-suite logger scope (desktop, mobile, a module's own JS suite); one run can be
a pre-existing failure while another is an FP-delta. Never fold the runs together, and never treat
one run's green as the build's. A `js_failed_reported` that outruns `failed` by orders of
magnitude is the normal shape of a broken browser suite.

When a test is red after the batch install:

1. Run the same test against the target branch WITHOUT any absorption commits applied (a clean
   checkout of the target tip). ALSO red there -> **pre-existing failure**: record it in the
   worklog, do not touch it, do not block the batch on it.
2. Green on the clean target but red after absorption -> **FP-delta failure**: root-cause and fix
   before committing the batch.

Never widen or relax an assertion to make a pre-existing failure green ([[test-behavior-contract]]).

### C3 - fix old version first (provenance)

The same discriminator governs WHERE a bug is fixed - reactively at P9 (a red test) AND
proactively at P8 (a coder who SPOTS a defect while adapting):

- **Pre-existing** (also red on the clean target tip / pre-dates the port): carry it FAITHFULLY
  forward - do NOT inline-fix on the destination. Surface it to the SOURCE series so the fix
  forward-ports up naturally: the orchestrator invokes `git-toolkit:git-ops` to open a
  source-series issue, conditional on a resolvable source remote (the `origin_url` of
  `repo_facts`); if none, record the deferred bug in `merge-log.md` and the Continuation Contract.
- **FP-delta** (green on source, red after adapt): fix it here, now.
- **Security/safety EXCEPTION:** fix on the destination IMMEDIATELY, then still open a
  source-series issue.

Canonical merge-log record: `<sha> | C3 | source issue <ref|DEFERRED> | <evidence one-liner>`.
Reviewer backstop (P12): flag any FP-delta diff that inline-fixes a pre-existing source bug (not
security/safety); an inherited bug carried faithfully + routed upstream is correct.

## Ephemeral isolation - CREATEDB required

An `ephemeral` acquire either returns an ISOLATED throwaway DB or FAILS - it never silently shares
the declared database. On any `lease_acquire` refusal, STOP and act on the named error code's
remedy (`db_preflight` diagnoses it). When the role cannot create databases, either have a human
grant `CREATEDB`, or re-dispatch with mode `exclusive` and run the remaining batches ONE AT A
TIME, stating in your report that isolation was not provided. When Odoo cannot authenticate or
the cluster does not answer, every mode is refused - fix the cluster first. Allocation protocol:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` § Allocate.

## Git topology - two-tier worktrees (summary)

The integration worktree branches from the TARGET branch; no direct commit lands on the target
branch during forward-port and integration never fast-forwards into it (target-branch-lock,
`odoo-forward-port` Hard rule 1). Adapt work happens DIRECTLY in that integration worktree - the single
open merge window spans the whole range, so no per-module child worktree exists (derivation:
`odoo-forward-port` § Git topology). Only after P10 concludes the merge and P11 acceptance and
P12 PR review clear does the human merge the PR; the only thing that lands on the target branch
is that human-confirmed PR merge.

**git-toolkit owns the worktree lifecycle** (S9 invariant - git-toolkit
`snippets/git-safety-contract.md`): every worktree creation, removal and topology change goes
through the `git-ops` skill; this skill may ask git-ops for the worktree list but never mutates it.
