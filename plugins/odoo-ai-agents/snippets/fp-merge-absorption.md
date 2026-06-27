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
2a. **Manifest version (C1) - never invent a bump.** `--no-ff` already carries whatever the source
    commit did to `__manifest__.py`. Do NOT add, derive, or increment a `version` bump on the target
    side. On a `__manifest__.py` `version` CONFLICT, keep the **TARGET** file's `version` field as-is -
    never merge-pick the higher number, never bump "to be safe". (The only bump permitted anywhere in
    forward-port is the C2 case below, and it is a migration-threshold bump, not a conflict decision.)
3. Forward tests - translate API to target, strip implementation-coupled assertions
   (see [[test-behavior-contract]]).
4. Fix any lint/eslint/prettier errors introduced by the merge.
5. Delegate the commit to git-operator - the merge commit encapsulates the entire
   translation cost.

Do NOT ask git-operator to commit until verify is green (P9, below). Do NOT open a second
no-commit merge while one is in progress (git index is shared; git-operator enforces this).

## Migration dir retarget (C2) - distinct from C1

C1 ("keep target / no manual bump") does NOT license leaving a migration dir on the source series.
A v17 commit adds `migrations/17.0.a.b.c/`. Let `S` = `a.b.c` (source). Let `M` = the target module's
manifest `version` BEFORE this forward-port (the version deployed target DBs have already reached).
A migration runs only on UPGRADE and only when `installed < dir_version <= manifest`.

Decision criterion: **does the fix need to apply to native-target-series data?**

1. **Default (yes - applies on the target series):** RETARGET the prefix to the target series and pick
   `V` so the dir fires on a deployed target DB sitting at `M`:
   - `S > M`: `V = S` (the merge already bumped the manifest M->S; just name the dir `<tgt>.S`, no extra bump).
     (Exception: if C1 fired on this commit - the merge had a `version` conflict and TARGET's value was kept,
     leaving manifest at M not S - treat as the `S <= M` case below; bump manifest to S so `dir <= manifest` holds.)
   - `S <= M`: `V` = `M`'s last component +1 (next patch); **bump the manifest to V** - keeping `a.b.c=S`
     would leave `dir <= installed` and it would NEVER run. Set **manifest version == dir version == V**.
   - Dir named FULL `<tgt-series>.V`. Invariant: the retargeted dir version MUST be `<= the final manifest version` (guarantees `M < V <= manifest`; if this would be violated, use the `S <= M` bump path).
2. **Exception (legacy source-origin-only data fix, irrelevant to native-target data):** KEEP the dir as
   `<src-series>.a.b.c`, do NOT bump. It still fires for src->tgt jumpers below `a.b.c`; it can never fire
   on a native-target DB (17 < 18), which is correct.
3. **C1 vs C2 de-confliction:** a manifest bump is FORBIDDEN for ordinary code commits and for conflict
   resolution (keep target). It is REQUIRED **only** in case 1 when `S <= M`; the bump target is the
   **current target manifest's next patch**, not `S`.
4. Dir name is always FULL `<tgt-series>.x.y.z` (Viindoo convention; FULL compare lets a target-series dir
   exceed a native-target DB's installed version). Migrations must be idempotent: a fully-updated source DB
   jumping the major re-runs a retargeted tip migration.
5. Module that is `installable:False` at target = lint-only lane ([[fp-installable-false]]) - do NOT
   retarget; its migrations are never run.

### WHY (verified against Odoo source - module.py + migration.py, byte-identical v17/v18)

`adapt_version()` at `odoo/modules/module.py` - the series-prefixing role of `adapt_version` (the same
function also enforces the v17 version-string regex - see [[odoo-version-pivots]]) prefixes a short
manifest `a.b.c` to `<series>.a.b.c` and stores it as the module's `installed_version`.
`MigrationManager.migrate_module` (`odoo/modules/migration.py`) runs a dir only when
`installed_version < dir <= <series>.<manifest>`. So a dir left at `<src-series>.a.b.c` SILENTLY SKIPS
every DB already at the source-series state when it upgrades to the target series. Migrations run on
UPGRADE only (never fresh install).

Worked: M=0.1.2, S=0.1.2 (M==S) -> bump to 0.1.3, dir `18.0.0.1.3` (keeping 0.1.2: `18.0.0.1.2 <
18.0.0.1.2` false -> never runs). M=0.1.1, S=0.1.2 (M<S) -> dir `18.0.0.1.2`, no extra bump.
M=0.1.4, S=0.1.2 (M>S) -> S<=M applies -> bump to 0.1.5, dir `18.0.0.1.5`, manifest bumped to 0.1.5
(naming dir `18.0.0.1.2` would never run: 0.1.4 < 0.1.2 is false).
Legacy-only `17.0.a.b.c` -> kept, fires for v17 jumpers, inert on native v18 (correct).

After the rename, sweep the body for source-series literals (log strings, version constants) - they
survive the rename and mislead operators.

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

### C3 - fix old version first (provenance)

The same FP-delta / pre-existing discriminator above governs WHERE a bug is fixed - reactively at P9
(a red test) AND proactively at P8 (a coder who SPOTS a defect while adapting, before tests run):

- **Pre-existing** (also red on the clean target tip / pre-dates the port): carry it FAITHFULLY forward -
  do NOT inline-fix on the destination. Surface it to the SOURCE series so the source is fixed too and the
  fix forward-ports up naturally. The orchestrator delegates to **github-operator** to open a source-series
  issue, **conditional on a resolvable source remote** (mirror P11's `git remote get-url origin`); if none,
  record the deferred bug in `merge-log.md` and the Continuation Contract instead of opening an issue.
- **FP-delta** (green on source, red after adapt): fix it here, now (already the rule above).
- **Security/safety EXCEPTION:** fix on the destination IMMEDIATELY, then still open a source-series issue.

Canonical merge-log record: `<sha> | C3 | source issue <ref|DEFERRED> | <evidence one-liner>`.
Reviewer backstop (P11): flag any FP-delta diff that inline-fixes a pre-existing source bug (not
security/safety); an inherited bug carried faithfully + routed upstream is correct.

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
