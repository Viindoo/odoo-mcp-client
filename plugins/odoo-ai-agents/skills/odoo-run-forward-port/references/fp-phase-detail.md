<!-- Reference for odoo-run-forward-port/SKILL.md § The 8-phase pipeline. Loaded as needed.
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

Dispatch one `odoo-intent-extractor` per commit with the **Agent tool** - real tool calls, never
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

---

## P4 - Adapt (test-first; serial per-module within a commit (v1); WORK-tier worktree per module for filesystem isolation)

For each touched module/WI, create a child worktree off integration and dispatch the adapt unit
(serially - complete one module before starting the next within the same commit):

```bash
git worktree add -b fp/<slug>-<module> <path>/wt-<module> fp/<slug>
```

**4a - forward the test FIRST** (the test is the oracle; independence keeps it honest). Dispatch
`odoo-test-writing` in mode `adapt`:

```
TEST ADAPT MODE: forward this source test to the target platform.
SOURCE TEST: <path(s) in the merged tree>
INTENT: <one-liner from intents/<sha>.md>   BUCKET: <a|b|c|d>
ODOO VERSION: <target>
RULE: translate to target API; STRIP implementation-coupled assertions (private method asserts,
      call counts, internal ordering); re-create the BEHAVIOR on target; confirm RED on target.
      Never relax/rewrite an assertion to pass unless the target platform legitimately redefines
      the behavior AND you cite the OSM/platform reason.
```

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

**4d - migration script:** rename the `migrations/<src-series>.x.y.z` dir to `<tgt-series>` ONLY
when the gate `installed < parse(dir) <= current` holds (else the script lands inert - silent).
The rename is idempotent (re-run safe). See `odoo-data-migration` for the script body.

Converge each child worktree back to integration (serialized, keep SHA), then
`git worktree remove <path>`. Mark `status=adapted`.

---

## P5 - Verify by behavior (PER-BATCH, in integration)

Resolve odoo-bin flags for the TARGET series via `cli_help` before invoking - the allocator
returns version-agnostic ports; flags and bootstrap behavior differ per series (e.g. v19
namespace package changes bootstrap; always pass `odoo_version=<target>` to `cli_help`).
Instance lifecycle protocol: `docs/reference/INSTANCE-LIFECYCLE.md`. Test invocation
conventions: `docs/reference/ODOO-TESTING.md`.

```bash
# one ephemeral DB per BATCH, not per commit
python3 <plugin>/scripts/lib/allocator.py acquire --series <X.Y> --mode ephemeral
#   -> ALLOC_DB_NAME / ALLOC_PORTS / ALLOC_TOKEN  (cache TOKEN in the batch worklog)

odoo-bin -d $ALLOC_DB_NAME -i mod_a,mod_b --test-enable --stop-after-init   # install N once
# subsequent same-batch commits touching a subset: -u <changed_mod> (skip full -i)

python3 <plugin>/scripts/lib/allocator.py release $ALLOC_TOKEN
```

- **RED-then-GREEN (whole module):** target suite must be green.
- **Confirm-by-toggle (FP-delta tests only):** disable each newly-forwarded adapt -> that test
  must go RED -> restore. Proves the test exercises the adapted behavior. Do NOT toggle the whole
  suite.
- **Triage red:** run the red test on a clean target tip (no absorption). Red there too =
  pre-existing (record, do not fix, do not block). Green on clean / red after = FP-delta (fix
  before committing). Never widen an assertion to hide a pre-existing failure.
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

## P7 - PR + review (depth-0)

```bash
git push origin fp/<slug>                          # push integration, NOT B
gh pr create --base <target-branch> --head fp/<slug> --title "..." --body "..."
```

Run `/code-review` inline (depth-0 only - it auto-spawns, illegal inside a leaf). Optionally
dispatch `odoo-code-review` for the forward-port pitfall (a forwarded test still coupled to the
source API). NEVER squash (squash mints a new SHA, defeats merge-base advance). B stays LOCKED -
the PR adds only the merge commits. Present the PR URL and wait for the human to merge.

---

## Cleanup (after human merge)

```bash
git worktree remove <path>/fp-integration
git worktree list          # confirm no dangling fp/<slug>-* child worktrees
git branch -d fp/<slug>
```

Leave `.odoo-ai/forward-port/<slug>/` for the next continuous run's resume (it is gitignored and
the checkpoint lets tomorrow's run skip done commits).
