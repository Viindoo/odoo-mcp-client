# Conflict-resolution recipes - merge / rebase / cherry-pick

Resolve conflicts to the INTENT of the change on the target's idiom - never leave a marker, and
never leave an auto-merged line that references a renamed or moved symbol (a clean merge can still
be a runtime break). Always have the abort path ready. Every command is one plain call in the shape
of S12 in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`.

## Preconditions

```bash
git status --porcelain     # S4: any output -> BLOCKED, never stash
```

## Merge

```bash
git merge --no-ff --no-edit --rerere-autoupdate <branch>    # preserve history (preferred)
git merge --ff-only <branch>                                # fail if not fast-forward
git merge --squash  <branch>                                # one commit (loses per-commit attribution)
git merge --abort                                           # bail on bad conflict
```

## Rebase / pull-rebase

```bash
git rebase --rerere-autoupdate <base>
git rebase --rerere-autoupdate --onto <new-base> <old-base>    # graft onto a new parent
git pull --rebase origin <branch>
git rebase --continue
git rebase --skip
git rebase --abort
```

Drive the `--continue` vs `--skip` decision by the S10 conflict continue-driver (canonical) in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`: NEVER `--skip` on "no unmerged files"; only
`--skip` when `--continue` reports an empty patch.

## Cherry-pick (single + range)

```bash
git cherry-pick --rerere-autoupdate <sha>
git cherry-pick --rerere-autoupdate <sha>^..<sha2>     # inclusive range (note the ^)
git cherry-pick -x <sha>                               # add "cherry picked from" line (backports)
git cherry-pick --no-commit <sha>                      # stage only - review before committing
git cherry-pick --continue --no-edit
git cherry-pick --skip
git cherry-pick --abort
```

## Resolving a conflicted file

```bash
git checkout --ours   <path>    # keep our whole version
git checkout --theirs <path>    # keep their whole version
git add <path>                  # after either checkout, or after editing the file by hand
git rebase --continue
git cherry-pick --continue --no-edit
git commit --no-edit            # concludes a merge
```

For MECHANICAL conflicts in a rebase/cherry-pick, `-X ours` / `-X theirs` biases the auto-merge;
for SEMANTIC conflicts, edit by hand. After resolution, commit per
`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` (sign-off only when C4 requires it). After resolving,
confirm no conflict markers remain - exit status 1 with no output means no markers:

```bash
git grep -nE '^(<<<<<<<|=======|>>>>>>>)'
```

## Conflict-class policy

The mechanical classes (deletions, binary/static add/add, import-only package `__init__.py`), the
marker rule and the content scope are S10 step 2 in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`. In addition:

- `.po`/`.pot` (translations): re-merge msgids, never blindly take one side - merge memory matters.
- generated/lockfiles: regenerate from source rather than hand-merging.
- other binary conflicts: pick a side explicitly (`--ours`/`--theirs`); there is no line merge.

## Abort + recover

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git reset --hard ORIG_HEAD     # if the op already finished and must be undone
```

On 3 consecutive failed `--continue`, abort, restore from the S1 backup, and escalate BLOCKED per
the safety contract rather than forcing a bad resolution.

## Verify

```bash
git diff <expected-base>...HEAD     # only the intended changes present
git log --oneline -10               # expected topology
```
