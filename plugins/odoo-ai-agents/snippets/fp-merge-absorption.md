<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-forward-port (orchestrator),
     the future fp-intent-4outcome, fp-symbol-survival-check, and any agent that runs
     a git merge step or a verify step during continuous forward-port.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md. -->

# FP Merge Absorption (git merge protocol + per-batch verify)

## Git operation - keep the source SHA

**Continuous forward-port** (recurring, source repo keeps evolving):

Delegate to **git-operator** (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
- `op: merge --no-ff --no-commit <src-SHA>` (request worktree isolation)

On return from git-operator, the working tree is the absorption zone. All adapt work
(steps 1-4 in "Absorption window" below) happens there. When adapt is complete, delegate
to **git-operator** again:
- `op: commit`, `message: "fp: absorb <src-SHA> - <one-line summary>"`

`--no-ff` forces a true merge commit so the source SHA enters the DAG of the target branch.
The merge-base advances to `<src-SHA>` after the commit. Next run, the scoped log
(src..tgt) will no longer see this commit - no re-resolution ever.

**NEVER squash or cherry-pick for continuous forward-port.** Both create a fresh SHA on
the target: merge-base does not move, and tomorrow's run encounters the same conflict again,
permanently.

**One-shot mode** (port once, source is frozen): delegate to **git-operator** with
`op: cherry-pick -n <src-SHA>` (the -n / no-commit flag keeps the tree open for absorption;
request this explicitly in the brief) as a SHOULD fallback - the repeated-resolution footgun
does not apply when the source will never advance.

## Absorption window (inside the no-commit merge)

Between the no-commit merge opened by git-operator and the subsequent commit step, the
working tree is the absorption zone. All work happens here - in this order:

1. Symbol-survival check - see [[fp-symbol-survival-check]] BEFORE touching any file.
2. Resolve conflict markers in source-touched files (3-way merge, platform-adapt per bucket,
   see [[fp-intent-4outcome]]).
3. Forward tests - translate API to target, strip implementation-coupled assertions
   (see [[test-behavior-contract]]).
4. Fix any lint/eslint/prettier errors introduced by the merge.
5. Delegate the commit to git-operator - the merge commit encapsulates the entire
   translation cost.

Do NOT ask git-operator to commit until verify is green (P9, below). Do NOT open a second
no-commit merge while one is in progress (git index is shared; git-operator enforces this).

## Skip-code-but-still-merge rule

Outcome buckets (a) and (d) from [[fp-intent-4outcome]] require NO adapt diff:

- **(a) already satisfied** - target platform already provides the behavior; the source
  commit adds nothing. Forward the tests only (they will pass immediately against target).
- **(d) no longer relevant** - the source commit worked around a platform limitation that
  the target has removed.

**In both cases, still create the merge commit.** The merge commit is what advances the
merge-base. If you skip it, tomorrow's forward-port encounters the same commit again. The
commit message should record the bucket and reason so reviewers do not flag it as empty.

## Verify protocol - per-batch, not per-commit

Running a full `-i <module> --test-enable` install for every absorbed commit is prohibitive.
Instead, use the reserve-only model: the allocator reserves a unique DB name and ports;
the DB is created through Odoo by your `-i` run (Odoo create-on-init) and dropped through
Odoo on release (via `scripts/lib/odoo_db.py`). The CREATEDB role is still required because
Odoo create-on-init needs it; if the role lacks CREATEDB the allocator degrades ephemeral
to exclusive (see "Allocator footgun" below).

1. Collect a batch of merge commits for the same module set (e.g. all commits in one P10 gate window).
2. **Acquire one ephemeral lease for the batch** (see [[concurrency-guard]] § Odoo
   instance allocation) - this reserves the DB name and ports but does NOT create the DB:

   ```bash
   python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral
   # emits ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_TOKEN
   ```

3. Install the N affected modules ONCE on that DB (Odoo create-on-init creates the DB):

   ```
   odoo-bin -d $ALLOC_DB_NAME -i mod_a,mod_b --test-enable --stop-after-init
   ```

4. For subsequent commits in the same batch that touch only a subset, run `-u <changed_mod>`
   against the already-installed DB - skip the full `-i` reinstall.
5. Release the lease when the batch is done (release drops the DB through Odoo):

   ```bash
   python3 <plugin>/scripts/lib/allocator.py release $ALLOC_TOKEN
   ```

Cache the lease token in the batch's worklog entry (see [[worklog-contract]]) so a crash
during the batch can release the DB rather than leaving it orphaned.

## RED-then-GREEN + confirm-by-toggle

After install:

- **RED-then-GREEN (all tests):** the full suite for the target module must be green.
  A pre-existing red test is a pre-existing failure - triage it (see Triage below), do not
  fix it as part of this forward-port.
- **Confirm-by-toggle (FP-delta tests only):** for each test that was NEWLY forwarded
  in this batch, temporarily disable the corresponding adapt code (comment out the patch,
  revert the field rename, etc.) and re-run ONLY that test. It must go RED. Then restore.
  This proves the test actually exercises the adapted behavior and is not green-by-accident.
  Do NOT toggle the entire suite - it is expensive and already covered by RED-then-GREEN.

## Triage: FP-delta vs pre-existing failure

When a test is red after the batch install:

1. Run the same test against the target branch WITHOUT any absorption commits applied
   (a clean checkout of the target tip). If it is ALSO red there, it is a **pre-existing
   failure** - record it in the worklog, do not touch it, do not block the batch on it.
2. If it is green on the clean target but red after absorption, it is an **FP-delta
   failure** - root-cause and fix before committing the batch.

Never widen or relax an assertion to make a pre-existing failure green - that violates
[[test-behavior-contract]].

## Allocator footgun - CREATEDB role

`allocator.py acquire --mode ephemeral` reserves a unique DB name; the DB is then created
by the caller's `odoo-bin -i ... --stop-after-init` (Odoo create-on-init). Both the
allocator probe and Odoo create-on-init require the PostgreSQL `CREATEDB` role. If the OS
user lacks it, the allocator degrades to `--mode exclusive` silently - it borrows the
single declared `db_name` without holding a real isolated lease. Under concurrency (another
session or another agent running at the same time), both may write to the same DB and
produce undefined test results.

Verify the role before starting a parallel batch:

```bash
psql -c "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user;"
# must return 't'
```

If it returns `f`, serialize the batch (one agent at a time) or fix the role grant.
Full allocation protocol: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`
§ Allocate and `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`.

## Git topology - two-tier worktrees (summary)

The integration worktree branches from the TARGET branch (never the target branch directly -
no direct commits land there during forward-port). Work-item worktrees branch from
integration for per-module absorption and converge back into integration via merge
(keeping SHA). Only after a human-gated P10 + P11 PR review does the human merge
the PR; integration NEVER fast-forwards into B directly (target-branch-lock, Hard rule 1).
The only thing that lands on B is the human-confirmed PR merge. This isolation guarantees
the target branch stays consistent even if one WI worktree is abandoned mid-flight.

**git-operator owns the worktree lifecycle** (S9 invariant - SSOT in git-toolkit
`snippets/git-safety-contract.md`). All worktree creation, removal, and
topology changes must be delegated to git-operator. This skill may read topology state (e.g.
via `git worktree list`) but never mutates it directly.

Full topology: see the forward-port orchestrator skill (`skills/odoo-forward-port/SKILL.md`).
