# Wave Orchestration - Reference Templates

On-demand reference for `skills/wave/SKILL.md`. Load this file when you need the full
template text for any of the structures below. Do not load it on every invocation.

---

## Repo Capability Card Template

Fill this once at Phase 0 and embed it verbatim in every WI subagent brief.

```
Repo Capability Card
  base          : <principal branch name>
  verify        : <command that must pass after every cherry-pick, e.g. "make test" or "make gen-check && make deps-check && make test">
  commit        : <conventional commit style, e.g. "conventional: feat(scope): ..., fix(scope): ...">
  confidential  : <public | restricted | internal>
  worktree_root : <parent path for wave worktrees, outside the repo tree>
```

Notes:
- Discover `verify` from Makefile targets, CI config, or README. If multiple commands
  are required, chain them with `&&`.
- `confidential: restricted` triggers the 8-group ban check on every artifact.
- `worktree_root` should be outside the repo tree to avoid accidental `git add .` inclusion.

---

## Four Topology Patterns

Choose at Phase 0 based on file-ownership and dependency analysis.

### Independent (most common)

All WIs modify disjoint files with no ordering dependency.
Cherry-pick in any order. Maximum parallelism.

```
principal ──────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► PR
                     │
                 WI-A ──► commit-A
                 WI-B ──► commit-B    (all parallel)
                 WI-C ──► commit-C
```

### Linear

WI-B depends on WI-A output (e.g., WI-B's code calls a function WI-A introduces).
Dispatch sequentially; cherry-pick A before dispatching B.

```
principal ────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ──► PR
                     │
                 WI-A ──► commit-A
                              └─► (WI-B dispatched after WI-A commits)
                                  WI-B ──► commit-B
```

### Mixed

Some WIs are independent, some sequential. Cherry-pick independent WIs first,
then the sequential group.

```
principal ──────────────────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick C ─── cherry-pick B ──► PR
                     │
                 WI-A ──► commit-A   (independent)
                 WI-C ──► commit-C   (independent, parallel with A)
                              └─► (WI-B depends on A+C; dispatched after both commit)
                                  WI-B ──► commit-B
```

### Diamond

WI-B and WI-C both depend on WI-A but are independent of each other.
Cherry-pick A first, then dispatch B and C in parallel.

```
principal ────────────────────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► PR
                     │
                 WI-A ──► commit-A
                              ├─► WI-B ──► commit-B   (parallel after A)
                              └─► WI-C ──► commit-C   (parallel after A)
```

---

## Plan Artifact Full Template (>=4 WI)

Write to `.odoo-ai/wave/<slug>/plan.md` (gitignored). This is the SSOT for the wave.

```markdown
# Wave Plan: <slug>

Generated: <ISO datetime>
Principal branch: <name>
Integration branch: wave/integration-<slug>

## Repo Capability Card

  base          : <principal>
  verify        : <command>
  commit        : <convention>
  confidential  : <level>
  worktree_root : <path>

## Topology

<independent | linear | mixed | diamond>

<Paste the relevant ASCII diagram from above, filled in with WI IDs>

## Work Items

| ID | Branch | Worktree path | Files in scope | Status |
|---|---|---|---|---|
| WI-A | wave/wi-<slug>-a | <path> | <file list> | pending |
| WI-B | wave/wi-<slug>-b | <path> | <file list> | pending |
| ... | | | | |

## Ownership Map

```
WI-A owns: [file1, file2, ...]
WI-B owns: [file3, file4, ...]
WI-C owns: [file5, ...]
```
(Sets must be disjoint. File appearing in two WIs = blocker.)

## Cherry-pick Log

| WI | Commit SHA | Verify result | Notes |
|---|---|---|---|
| WI-A | pending | - | |
| WI-B | pending | - | |
| ... | | | |

## Review Log

| Phase | Reviewer | Findings | Fixed |
|---|---|---|---|
| 4.1 Opus review | Opus | <summary> | <yes/no + detail> |
| 4.2 /code-review | /code-review skill | <findings> | <yes/no + detail> |

## PR

URL     : <to be filled>
Squash  : <backup ref> -> tree-identity <confirmed | FAILED>
Status  : <open | merged | closed>

## Cleanup

- [ ] WI worktrees removed
- [ ] WI branches deleted
- [ ] Integration branch deleted (after merge)
- [ ] Backup tag deleted
- [ ] .odoo-ai/wave/<slug>/ removed
```

---

## Cleanup Checklist

Run after Phase 6 human-confirm merge:

```
[ ] git worktree remove <path>/wi-a    (and all other WI worktrees)
[ ] git worktree remove <path>/integration
[ ] git branch -d wave/wi-<slug>-a     (and all other WI branches)
[ ] git branch -d wave/integration-<slug>   (after merge confirmed on remote)
[ ] git tag -d wave-backup-<slug>
[ ] rm -rf .odoo-ai/wave/<slug>/        (gitignored; safe to delete)
[ ] git worktree prune                  (clean stale worktree refs)
```

Verify after cleanup:
`git worktree list` should show only the principal worktree.
`git branch --list "wave/*"` should be empty.

---

## Squash Tree-Identity Recipe

This is the load-bearing safe-squash procedure. Follow it exactly.

```bash
# Step 0: Stale-base guard — MUST run before squashing
# Fetch the latest principal branch tip from the remote.
git fetch origin <principal-branch-name>

# Check whether the principal has moved since integration was cut.
# If this check fails (exit non-zero), the principal received new commits
# AFTER the integration branch was branched off.  Squashing onto the local
# <principal-branch-name> would silently revert those intervening commits
# because git reset --soft moves HEAD to that (now-stale) tip.
# ABORT: rebase integration onto origin/<principal-branch-name> first,
# re-run the full verify command, then return to Step 1.
git merge-base --is-ancestor origin/<principal-branch-name> HEAD \
  || { echo "ABORT: principal has moved — rebase integration first"; exit 1; }

# Step 1: Create a backup ref BEFORE squashing
git tag wave-backup-<slug> HEAD

# Step 2: Squash all integration commits into one
# (from the integration worktree, not the principal)
# Use origin/<principal-branch-name> — guaranteed fresh after Step 0 fetch.
git reset --soft origin/<principal-branch-name>
git commit -m "<conventional commit message>"

# Step 3: Verify tree identity
# Exit 0 = trees are identical (safe to push)
# Exit non-zero = mismatch (ABORT, do not push)
git diff --quiet wave-backup-<slug>

# Step 4a: On success - force-with-lease push
git push --force-with-lease origin wave/integration-<slug>

# Step 4b: On failure - abort and restore
# DO NOT push. Report the mismatch to the user.
# To restore: git reset --hard wave-backup-<slug>
# Investigate with: git diff wave-backup-<slug>
```

**Stale-base hazard**: `git reset --soft <principal>` silently squashes onto wherever
the local ref points. If commits landed on the principal AFTER integration was branched,
the local ref is stale and those commits are reverted even though the tree-identity check
passes (tree matches backup but commit graph is wrong). The Step 0 fetch + ancestry check
is the only guard against this failure mode.

**Empty-tree SHA note**: When checking if a tree is completely empty (rare edge case),
the empty tree SHA is `da39a3ee5e6b4b0d3255bfef95601890afd80709`. This is only relevant
if debugging a squash that produces an unexpected empty commit.

**Why `git diff --quiet` not `--exit-code`**: Both work for tree comparison but `--quiet`
suppresses all output, which is what we want in the gate check. The exit code is the signal.

---

## Confidentiality Long-Form - 8 Banned Groups

When `confidential: restricted` or `confidential: internal` in the Repo Capability Card,
enforce these 8 groups in ALL artifacts, commit messages, and subagent outputs:

1. **CEO personal info** - salary, personal decisions, personal health, personal comms
2. **Customer PII / contracts** - names (use Customer-A), deal sizes, contract terms, SLAs
3. **Internal pricing** - VND rates, discount structures, partner margins, cost basis
4. **Competitor intelligence** - non-public analysis, win/loss data, internal benchmarks
5. **Product roadmap** - unannounced features, internal milestones, R&D directions
6. **Marketing in-draft** - unreleased campaigns, launch dates, messaging that is not public
7. **OKR / targets** - revenue targets, growth metrics, internal KPIs
8. **Internal-tooling paths** - any absolute machine path (user home dirs, temp dirs) or
   note-store reference that reveals internal infrastructure

For each group: if the user prompt contains such data, acknowledge the intent but do not
echo the data into any committed file. Use abstract placeholders instead.

For public repos (confidential: public): standard open-source caution applies. No machine
paths, no personal info. Groups 1-3 and 5-8 still apply to avoid accidental leakage.
