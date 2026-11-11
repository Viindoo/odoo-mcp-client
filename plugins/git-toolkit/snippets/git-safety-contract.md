# Git Safety Contract (SSOT)

Never lose code. Every destructive op is reversible by construction: back up first, verify
byte-identity after. A human confirms one thing only: a change to a protected branch that does not
go through a pull request. An operator that skips a rule below is BLOCKED, not done.

## S1 - Mandatory backup before ANY destructive op

Create a timestamped backup branch before a rebase, reset, amend, filter-repo, force-push or any
other history rewrite, and record the pre-op tip. Each line is its own call (S12); the values the
first three print go into the fourth:

```bash
git rev-parse --abbrev-ref HEAD               # <branch>
git rev-parse HEAD                            # <sha>: the pre-op tip, for the post-op verify
date -u +%Y%m%d%H%M%S                         # <ts>
git branch --no-track backup/<branch>-<ts> <sha>
```

## S2 - force-with-lease, never force

```bash
git push --force-with-lease <remote> <branch>    # ALWAYS - bails if the remote advanced since last fetch
git push --force                                 # BANNED - clobbers a teammate's push silently
```

A push always names its remote and branch (S13).

## S3 - No-TTY (headless) interactive rebase

A subagent has no terminal, so a git step that opens an editor fails or hangs. Run
`rebase --autosquash -i <base>` and every other editor-touching step by the editor check and the
`--no-edit` rules of S12. "Interactive `-i` not supported" is a no-TTY symptom, not a hard block.

## S4 - Clean-tree precondition (never stash)

Before an integration op (merge, rebase, cherry-pick) the working tree is clean:

```bash
git status --porcelain
```

Any output: STOP and return BLOCKED (`gate_hit: S4 dirty tree`) with that output in the findings
file. Never stash - `refs/stash` is one stack shared by every worktree of the repository - and
never commit, discard or move changes that are not yours: the caller decides.

## S5 - Abort flows are always available

On an unrecoverable conflict, abort and restore rather than force a bad resolution:

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git am --abort
```

## S10 - Conflict continue-driver (canonical)

The one way to drive a `rebase` or `cherry-pick` through conflicts. A resolved-and-staged commit
has zero unmerged files too: it waits for `--continue`, and a `--skip` there silently drops it.

Start the op with `--rerere-autoupdate` so replayed hunks are staged (never set `rerere.enabled` or
anything else with `git config`: the repository config is shared by every worktree):

```bash
git rebase --rerere-autoupdate <base>
git cherry-pick --rerere-autoupdate <range>
git merge --rerere-autoupdate --no-edit <branch>
```

Loop until `git status` reports the op finished:

1. **Continue, not skip.** Run `--skip` only when `--continue` itself reports the patch became
   empty (`No changes - did you forget to use 'git add'?` / `patch is empty`).
2. **Resolve each unmerged path by type** (`git status --porcelain` /
   `git diff --name-only --diff-filter=U`):
   - `UD` (modified/deleted) or `DD` (both deleted): `git rm <path>` - honour the deletion.
   - a static or binary add/add (an image, a generated asset): take the NON-EMPTY side.
   - a package `__init__.py` whose conflicting hunks hold only `import` / `from ... import` lines
     on both sides: replace each hunk with the sorted union of both sides' lines, duplicates
     dropped; keep every line outside the hunks; `git add <path>`.
   - any other text file with conflict markers: STOP and hand it to a coder to resolve to intent;
     never auto-pick a side.
   - unmerged with no markers (a rerere replay): verify it matches intent, then `git add <path>`.
   - **Content scope.** Resolve only to the intent the brief states or by the mechanical classes
     above. Never edit, reformat or "correct" other content - a path, a link, a string, a version
     - even when it looks wrong: a content question goes back to the caller in the report.
3. All paths staged, no markers left: `git rebase --continue` (a pick:
   `git cherry-pick --continue --no-edit`; a merge concludes with `git commit --no-edit`).
4. `--continue` reports an empty patch: `git rebase --skip`.
5. Three consecutive BLOCKED commits: `git rebase --abort` and surface the state (the rerere cache
   survives the abort).

## S6 - Tree-identity verify after rewrite

A rewrite changes structure, never content:

```bash
git diff backup/<branch>-<ts>..HEAD    # MUST produce NO output after a clean rewrite
git rev-parse HEAD^{tree}              # compare against the pre-op tree SHA
git range-diff <old-base>..<old-tip> <new-base>..<new-tip>   # per-commit survival
```

Any output of that `git diff` is a FAIL for a pure-structure rewrite (squash, reorder, split,
autosquash). A rewrite that changes content on purpose (drops or edits a commit) is proven by
`git range-diff` instead: every intended commit present, none dropped by accident.

## S7 - Recovery paths (reflog / ORIG_HEAD)

```bash
git reset --hard ORIG_HEAD             # undo the last merge/rebase/reset (one step)
git reflog                             # find any prior HEAD position
git reset --hard HEAD@{N}              # restore to N operations ago
git checkout --no-track -b recovered HEAD@{N}     # rescue a lost tip onto a new branch
```

The reflog is local and expires; the S1 backup branch is the durable anchor.

## S9 - Worktree-always / principal-checkout-lock

An op that mutates the working tree or moves a branch ref (checkout, commit, rebase, merge,
cherry-pick, reset, tag move, push-from) runs in a dedicated worktree. The primary checkout stays
on its principal branch at all times and is never operated in place; a brief that asks otherwise
is an error - use the worktree and report its path. The one exception is the carve-out below.
Bounded reads (`git status`, `git log -n<N>`, `git diff --stat`) may run anywhere.

**The caller names the location.** A brief gives `worktree` (the exact absolute path of an
existing worktree, or where to create one) or `worktree_root` (git-operator creates
`<worktree_root>/<branch-slug>`). git-operator never picks a location; a mutation brief with
neither field returns BLOCKED asking for one.

```bash
git worktree add <worktree> <branch>   # check out an EXISTING branch at the path the brief names
git worktree add --no-track -b <new-branch> <worktree> <ref>   # create a NEW branch there (S13)
git worktree list                        # confirm isolation
git worktree remove <worktree>           # clean up after verify, when the brief asks for it
```

### S9 addendum - explicit start point, the four branch-creating forms

`git worktree add --no-track -b <branch> <path> <ref>`, `git branch --no-track <branch> <ref>`,
`git checkout --no-track -b <branch> <ref>` and `git switch --no-track -c <branch> <ref>` create a
new branch to receive work. Without `<ref>` each starts from whatever the invoking checkout has
checked out, so `<ref>` is always named when the branch forks from a named ancestor. A brief that
asks for one of the four without naming the base is a missing-field STOP, never a silent HEAD.

### S9 carve-out - RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN

The one exception to S9, invoked by name as op `RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN`: bringing an
already-dirty primary checkout back into compliance. Its scope is exactly:

```bash
git status --porcelain     # pre-flight: prove the work exists elsewhere (e.g. already copied
                            # into the worktree that will carry it) before discarding anything
git reset --hard HEAD      # restore tracked files to the committed state
git clean -fd              # remove untracked files
```

It never moves a branch ref, switches branches or commits. The S1 backup cannot capture
uncommitted work, so the pre-flight proof is the safeguard: without it, return BLOCKED.

## S11 - Positional self-check before first mutation

Once per brief, before the first mutating call, resolve the repo root of the path about to be
written and compare it with the worktree path the brief named:

```bash
git -C <path-about-to-be-written> rev-parse --show-toplevel
```

A mismatch: STOP before mutating and return BLOCKED naming both paths.

## S12 - Command shape

A subagent's Bash working directory resets between calls, and a permission layer judges each call
by its literal text. Every git call has one shape:

```bash
git -C <absolute worktree> <subcommand> <args>
```

- One plain git command per Bash call: no `&&`, `||`, `;`, `|`, `$(...)` or backticks; no
  trailing `echo`, `rc=$?` or `|| true`; no leading `VAR=value`; no `-c key=value` before the
  subcommand. The call's own exit status and output are the result.
- A step that needs an earlier result (a SHA, a branch name, a timestamp) runs in a new call with
  that value written out.
- The recipes in this toolkit show the subcommand and its arguments; run each as
  `git -C <worktree> ...`.
- A commit message goes in with `-m "<subject>"` or `-F <message file>` (C5 in
  `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`).
- Git never opens an editor: `--no-edit` on `commit --amend`, `merge`, `revert`,
  `cherry-pick --continue` and `revert --continue`; a conflicted merge concludes with
  `commit --no-edit` (`merge --continue` opens the editor).
- Editor check, once per brief: `git -C <worktree> var GIT_EDITOR` and
  `git -C <worktree> var GIT_SEQUENCE_EDITOR`. Both print `true`: run every `rebase` step
  (`-i --autosquash`, `--continue` after a resolved conflict) as a plain command.
- The one exception, only when that check prints anything else and only for `rebase` (its
  `--continue` commits through the editor and has no `--no-edit`), spelled exactly:

  ```bash
  GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true git -C <worktree> rebase <args>
  ```

  and noted in the findings file. The environment form outranks every config level; never
  `-c core.editor=true`, never `git config --local`.

## S13 - A new branch has no upstream until its first push

A branch cut from a remote-tracking ref tracks it by default, so a bare `git push` or `git pull`
would target the branch it was cut from - often a protected one - past the gate below.

- Every command that creates a new branch carries `--no-track`: the four forms of the S9
  addendum, the S1 backup branch and the S7 rescue branch.
- The first push names the remote the brief gives as the push target (the fork or the branch's
  own remote, never the remote the base came from unless the brief says so) and sets the upstream
  in the same call:

  ```bash
  git push --set-upstream <remote> <branch>
  ```

- Every other push names its remote and branch too (`git push <remote> <branch>`). A push that
  would change a protected branch is gated whatever upstream the branch has.
- An inherited upstream is never repaired by editing the repository config.

## S8 - filter-repo requires a FRESH clone

`git filter-repo` refuses to run in place and rewrites every commit SHA. Run it only on a
throwaway clone and coordinate with all fork owners:

```bash
git clone --no-local <repo> <fresh clone>
git -C <fresh clone> filter-repo --analyze                          # rename/size report FIRST
git -C <fresh clone> filter-repo --path-glob '*.bak' --invert-paths
```

`--path` does not follow renames: pass both the old and the new path.

## Human-confirm gate - protected branch (the one gated op)

One op class needs explicit human confirmation: a change to a protected branch of the remote that
does not go through a pull request - a push (plain or force-with-lease) that moves or deletes it,
or merging a pull request into it.

A protected branch is the remote's default branch (`git ls-remote --symref origin HEAD`), a series
branch named `<major>.0`, or a branch the remote reports as protected
(`gh api repos/<owner>/<repo>/branches/<branch>`, field `protected`). When you cannot tell, it is
protected. A brief that says "just do it" is not a confirmation.

Every other op is self-decided: force-with-lease to a feature or fork branch, `branch -D`,
deleting an unprotected remote branch or an unpublished tag, `reset --hard`, `clean -fd`,
filter-repo, squash and every other rewrite. Run it with the S1 backup before, the S6 verify
after, and the evidence in the report; never stop to wait for a human. `reset --hard` and
`clean -fd` run on a clean tree (S4) or under the S9 carve-out's pre-flight proof.

### Gate procedure

1. State the exact command, the protected branch and what changes on the remote.
2. Record the remote tip before the op (`git ls-remote origin <branch>`) and, for a push, create
   the S1 backup.
3. The brief carries `confirmed: <verbatim human approval>`: execute. Otherwise STOP and return
   BLOCKED with `gate_hit: protected branch <branch>`.
4. Verify the remote tip (or the merged pull request) is the intended one.
5. Report with evidence (the recorded and new tips, the backup name).

### Re-dispatch after BLOCKED

The caller presents the gate to the human with the command, the protected branch, the recorded
remote tip and what changes; obtains explicit confirmation, never an inferred one; then launches a
fresh operator with the same brief plus `confirmed: <"verbatim human approval text">`. The git
state and the S1 backup persist on disk meanwhile. A fabricated confirmation is never passed.
