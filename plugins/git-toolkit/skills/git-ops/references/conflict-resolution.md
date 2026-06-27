# Conflict-resolution recipes - merge / rebase / cherry-pick

Resolve conflicts to the INTENT of the change on the target's idiom - never leave a marker, and
never leave an auto-merged line that references a renamed or moved symbol (a clean merge can still
be a runtime break). Always have the abort path ready.

## Preconditions

```bash
git status --porcelain     # S4 clean tree before starting (stash if not)
git config rerere.enabled true   # remember + replay conflict resolutions across retries
```

## Merge

```bash
git merge --no-ff   <branch>    # preserve history (preferred)
git merge --ff-only <branch>    # fail if not fast-forward
git merge --squash  <branch>    # one commit (loses per-commit attribution)
git merge --abort               # bail on bad conflict
```

## Rebase / pull-rebase

```bash
git rebase <base>
git rebase --onto <new-base> <old-base>    # graft onto a new parent
git pull --rebase origin <branch>
git rebase --continue | --skip | --abort
```

## Cherry-pick (single + range)

```bash
git cherry-pick <sha>
git cherry-pick <sha>^..<sha2>     # inclusive range (note the ^)
git cherry-pick -x <sha>           # add "cherry picked from" line (backports)
git cherry-pick --no-commit <sha>  # stage only - review before committing
git cherry-pick --continue | --skip | --abort
```

## Resolving a conflicted file

```bash
git checkout --ours   <path>    # keep our whole version
git checkout --theirs <path>    # keep their whole version
# OR edit the file by hand for a line-by-line/semantic merge, then:
git add <path>
git rebase --continue            # or: git cherry-pick --continue / git commit (merge)
```

For MECHANICAL conflicts in a rebase/cherry-pick, `-X ours` / `-X theirs` biases the auto-merge;
for SEMANTIC conflicts, edit by hand. After resolution, commit per
`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` (sign off with `-s`). After resolving,
confirm no conflict markers remain:

```bash
git grep -nE '^(<<<<<<<|=======|>>>>>>>)' || echo "no markers"
```

## Conflict-class policy

- `.po`/`.pot` (translations): re-merge msgids, never blindly take one side - merge memory matters.
- generated/lockfiles: regenerate from source rather than hand-merging.
- binary: pick a side explicitly (`--ours`/`--theirs`); there is no line merge.

## Abort + recover

```bash
git rebase --abort | git merge --abort | git cherry-pick --abort
git reset --hard ORIG_HEAD     # if the op already finished and must be undone
```

On 3 consecutive failed `--continue`, abort, restore from the S1 backup, and escalate BLOCKED per
the safety contract rather than forcing a bad resolution.

## Verify

```bash
git diff <expected-base>...HEAD     # only the intended changes present
git log --oneline -10               # expected topology
```
