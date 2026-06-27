<!-- SSOT snippet. The single home for the git safety contract: backup, force-with-lease,
     no-TTY rebase, clean-tree precondition, abort flows, reflog/ORIG_HEAD recovery,
     filter-repo fresh-clone rule, tree-identity verify, and the destructive human-confirm
     gate. Referenced (never copy-pasted) by skills/git-ops/SKILL.md and every operator agent
     via ${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md. Edit here only. -->

# Git Safety Contract (SSOT)

Never lose code. Every destructive op is reversible by construction: back up first, verify
byte-identity after, gate on human confirm before. The rules below are non-negotiable - a leaf
operator that skips any one is BLOCKED, not done.

## S1 - Mandatory backup before ANY destructive op

Create a timestamped backup branch BEFORE rebase, reset, amend, filter-repo, force-push, or any
history rewrite. Record the pre-op tip.

```bash
git branch backup/$(git rev-parse --abbrev-ref HEAD)-$(date +%Y%m%d%H%M%S)
git rev-parse HEAD   # record pre-op SHA for the post-op verify
```

Never skip. The backup branch is the recovery anchor if the op goes wrong.

## S2 - force-with-lease, never force

```bash
git push --force-with-lease    # ALWAYS - bails if the remote advanced since last fetch
git push --force               # BANNED - clobbers a teammate's push silently
```

## S3 - No-TTY (headless) interactive rebase

A subagent has no terminal, so a bare `git rebase -i` hangs. Drive the sequence non-interactively:

```bash
GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>
EDITOR=true GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>   # when exec/amend is involved
```

For scripted todo edits, set `GIT_SEQUENCE_EDITOR` to a `sed`/`awk` one-liner (see
`${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/history-rewrite.md`). "Interactive `-i` not
supported" is a no-TTY symptom, NOT a hard block - the env-var form is the fix.

## S4 - Clean-tree precondition

Before any integration op (merge / rebase / cherry-pick), the working tree MUST be clean:

```bash
git status --porcelain   # empty = clean; if not, stash first
git stash push -m "pre-<op>"
```

## S5 - Abort flows are always available

On an unrecoverable conflict, abort and restore rather than force a bad resolution:

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git am --abort
```

## S6 - Tree-identity verify after rewrite

A history rewrite must change STRUCTURE, never CONTENT. Prove content survived:

```bash
git diff backup/<branch>-<ts>..HEAD    # MUST produce NO output after a clean rewrite
git rev-parse HEAD^{tree}              # compare against the pre-op tree SHA
git range-diff <old-base>..<old-tip> <new-base>..<new-tip>   # per-commit survival
```

Any non-empty `git diff` against the backup is a FAIL: code changed when it should not have. For
rewrites that INTENTIONALLY change content (drop/edit a commit), the survival check is
`git range-diff` (every intended commit present, none unintentionally dropped), NOT the empty-diff
invariant; empty `git diff backup..HEAD` applies to pure-structure rewrites
(squash/reorder/split/autosquash).

## S7 - Recovery paths (reflog / ORIG_HEAD / stash)

```bash
git reset --hard ORIG_HEAD             # undo the last merge/rebase/reset (one step)
git reflog                             # find any prior HEAD position
git reset --hard HEAD@{N}              # restore to N operations ago
git checkout -b recovered HEAD@{N}     # rescue a lost tip onto a new branch
git fsck --unreachable | grep commit   # find an orphaned (dropped-stash) commit
```

Reflog is LOCAL only and expires (90d reachable / 30d unreachable). The S1 backup branch is the
durable anchor; reflog is the safety net for ops where a backup was somehow missed.

## S8 - filter-repo requires a FRESH clone

`git filter-repo` refuses to run in-place and rewrites EVERY commit SHA permanently. Run it only on
a throwaway clone and coordinate with all fork owners:

```bash
git clone --no-local repo/ repo-rewrite/
cd repo-rewrite/
git filter-repo --analyze                          # rename/size report FIRST
git filter-repo --path-glob '*.secret' --invert-paths
```

`--path` does NOT follow renames - pass both old and new paths explicitly.

## Destructive human-confirm gate (the 8-item list)

These ops are IRREVERSIBLE-IN-EFFECT or PUBLIC-FACING. Each requires explicit human confirmation
BEFORE execution - never auto-run, even when asked to "just do it":

1. `git push --force-with-lease` to a shared/public branch
2. `git branch -D` (force-delete an unmerged branch)
3. `git push origin --delete <branch>` (delete a remote branch)
4. `git reset --hard` (discard uncommitted work)
5. `git clean -fd` (delete untracked files/dirs)
6. `git filter-repo` (rewrite entire history)
7. any tag deletion on a published release
8. merge to `main`/`master` without CI green

### Gate procedure

1. State the exact command + what it will change + what is irreversible.
2. Create the S1 backup branch and record the pre-op SHA.
3. Get explicit human confirmation (present, STOP, wait).
4. Execute.
5. Run the S6 tree-identity verify.
6. Report with evidence (the verify output, the backup branch name).

A leaf operator that reaches a gated op WITHOUT human confirmation in its brief STOPS and returns
BLOCKED with the gate list - it does not self-authorize.
