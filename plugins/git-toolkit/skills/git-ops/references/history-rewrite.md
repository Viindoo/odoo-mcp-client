# History-rewrite recipes - deterministic, with backup + verify + confirm

All recipes here are DESTRUCTIVE. Every one runs under
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`: S1 backup + pre-op SHA FIRST, the 8-item
human-confirm gate BEFORE execution, S6 tree-identity verify AFTER. Drive interactive rebases
headlessly (S3) - a subagent has no TTY.

## Pre-op (every recipe)

```bash
git status --porcelain                                   # S4 clean tree (stash if not)
git branch backup/$(git rev-parse --abbrev-ref HEAD)-$(date +%Y%m%d%H%M%S)
git rev-parse HEAD                                        # record pre-op SHA
```

## Interactive rebase - autosquash (preferred)

Make fixups while committing, then collapse them non-interactively:

```bash
git commit --fixup=<target-sha>                          # "fixup! <target subject>"
GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>
EDITOR=true GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>   # if exec/amend involved
```

## Squash a range

```bash
GIT_SEQUENCE_EDITOR='awk "NR==1{print} NR>1{sub(/^pick/,\"squash\")} {print}"' \
  git rebase -i HEAD~<N>
```

## Split one commit into focused commits

```bash
GIT_SEQUENCE_EDITOR='sed -i "s/^pick <sha>/edit <sha>/"' git rebase -i <sha>^
git reset HEAD^                  # unstage that commit's changes
git add <first set>;  git commit -s -m "<first focused subject>"    # use -s + format per commit-convention.md
git add <second set>; git commit -s -m "<second focused subject>"   # use -s + format per commit-convention.md
git rebase --continue
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
git clone --no-local repo/ repo-rewrite/ && cd repo-rewrite/
git filter-repo --analyze                                # rename/size report first
git filter-repo --path-glob '*.secret' --invert-paths    # remove secrets
git filter-repo --path-rename old/:new/                   # rename a path (give BOTH paths)
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
git revert <sha>
git revert <sha1>..<sha2>     # range, reverse order
```
