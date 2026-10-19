# History-rewrite recipes - deterministic, with backup + verify + confirm

All recipes here are DESTRUCTIVE. Every one runs under
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`: S1 backup + pre-op SHA FIRST, the 8-item
human-confirm gate BEFORE execution, S6 tree-identity verify AFTER. Every command is one plain call
in the shape of S12, which also settles every step that would open an editor.

## Pre-op (every recipe)

```bash
git status --porcelain                                   # S4: any output -> BLOCKED, never stash
```

Then the S1 backup: branch name, pre-op SHA, timestamp, backup branch - one call each.

## Interactive rebase - autosquash (preferred)

Make fixups while committing, then collapse them:

```bash
git commit --fixup=<target-sha>                          # "fixup! <target subject>"
git rebase -i --autosquash <base>
```

## Squash a range

Write the squashed commit's message with the file tool beside the findings file (C5), then:

```bash
git reset --soft <base>
git commit -F <message-file>
```

## Split one commit into focused commits

Rebuild the commit on a detached HEAD, then replay the commits above it onto the result. Commit
messages per `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` (sign-off per C4):

```bash
git switch --detach <sha>
git reset HEAD^                  # unstage that commit's changes
git add <first set>
git commit -F <first-message-file>
git add <second set>
git commit -F <second-message-file>
git rebase --onto HEAD <sha> <branch>
```

## Amend the last commit

```bash
git commit --amend --no-edit          # fold staged changes in
git commit --amend -m "Better subject"
```

Safe only on un-pushed commits (rewrites the SHA).

## Reset

```bash
git reset --soft  HEAD~<N>    # keep changes staged
git reset --mixed HEAD~<N>    # keep changes unstaged (default)
git reset --hard  <sha>       # DISCARD all changes - gated; backup first
```

## filter-repo (bulk rewrite - fresh clone only)

```bash
git clone --no-local <repo> <fresh clone>
git -C <fresh clone> filter-repo --analyze                                # rename/size report first
git -C <fresh clone> filter-repo --path-glob '*.secret' --invert-paths    # remove secrets
git -C <fresh clone> filter-repo --path-rename old/:new/                  # rename a path (give BOTH paths)
```

Refuses to run in-place; rewrites EVERY SHA; coordinate with all fork owners. `--path` does NOT
follow renames.

## Force-push the rewritten branch

```bash
git push --force-with-lease    # NEVER --force (S2)
```

## Post-op verify (S6 - mandatory)

```bash
git diff backup/<branch>-<ts>..HEAD     # MUST be empty (content preserved)
git range-diff <old-base>..backup/<branch>-<ts> <old-base>..HEAD
git rev-parse HEAD^{tree}               # compare to recorded pre-op tree SHA
```

Non-empty diff against the backup = FAIL: code changed when only structure should have. Restore:

```bash
git reset --hard ORIG_HEAD              # last op only
git reset --hard backup/<branch>-<ts>   # durable anchor
git reflog                              # older recovery
```

## Revert - the non-destructive alternative (shared branches)

When the branch is shared/public, prefer revert over rewrite - it adds a new inverse commit, no SHA
churn, no force-push:

```bash
git revert --no-edit <sha>
git revert --no-edit <sha1>..<sha2>     # range, reverse order
```
