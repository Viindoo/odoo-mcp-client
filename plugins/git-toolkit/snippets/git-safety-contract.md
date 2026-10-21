<!-- SSOT snippet. The single home for the git safety contract: backup, force-with-lease,
     no-TTY rebase, clean-tree precondition (never stash), abort flows, reflog/ORIG_HEAD
     recovery, filter-repo fresh-clone rule, tree-identity verify, conflict driver, command
     shape, no inherited upstream on a new branch, and the one human-confirm gate (protected
     branch). Referenced (never copy-pasted) by
     skills/git-ops/SKILL.md and every operator agent via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md. Edit here only. -->

# Git Safety Contract (SSOT)

Never lose code. Every destructive op is reversible by construction: back up first, verify
byte-identity after. A human confirms only one thing: a change to a protected branch that does not
go through a pull request. The rules below are non-negotiable - a leaf operator that skips any one
is BLOCKED, not done.

## S1 - Mandatory backup before ANY destructive op

Create a timestamped backup branch BEFORE rebase, reset, amend, filter-repo, force-push, or any
history rewrite. Record the pre-op tip. Each line is its own call (S12); write the values the
first three print into the fourth:

```bash
git rev-parse --abbrev-ref HEAD               # <branch>
git rev-parse HEAD                            # <sha>: the pre-op tip, for the post-op verify
date -u +%Y%m%d%H%M%S                         # <ts>
git branch --no-track backup/<branch>-<ts> <sha>
```

Never skip. The backup branch is the recovery anchor if the op goes wrong.

## S2 - force-with-lease, never force

```bash
git push --force-with-lease <remote> <branch>    # ALWAYS - bails if the remote advanced since last fetch
git push --force                                 # BANNED - clobbers a teammate's push silently
```

A push always names its remote and branch (S13); it never relies on an upstream.

## S3 - No-TTY (headless) interactive rebase

A subagent has no terminal, so any git step that opens an editor fails or hangs. Run
`rebase --autosquash -i <base>` and every other editor-touching step by the editor check and the
`--no-edit` rules in S12. "Interactive `-i` not supported" is a no-TTY symptom, NOT a hard block.

## S4 - Clean-tree precondition (never stash)

Before any integration op (merge / rebase / cherry-pick), the working tree MUST be clean:

```bash
git status --porcelain
```

Empty output = clean; proceed. Any output -> STOP and return BLOCKED (`gate_hit: S4 dirty tree`)
with that output in the findings file. Never stash: `refs/stash` is one stack shared by every
worktree of the repository, so another session can pop or drop the entry. Never commit, discard or
move the changes either - they belong to someone else; the caller decides.

## S5 - Abort flows are always available

On an unrecoverable conflict, abort and restore rather than force a bad resolution:

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git am --abort
```

## S10 - Conflict continue-driver (canonical)

The ONE correct way to drive a `rebase`/`cherry-pick` through conflicts. The fatal bug this prevents:
treating "no unmerged files" as "empty patch" and running `--skip`, which SILENTLY DROPS a commit a
resolver just staged - a resolved-and-staged commit ALSO has zero unmerged files; it is waiting for
`--continue`, not `--skip`.

Start the op with `--rerere-autoupdate` so rerere-replayed hunks are staged (leave `rerere.enabled`
as-is; never set either with `git config` - the repository config is shared by every worktree):

```bash
git rebase --rerere-autoupdate <base>
git cherry-pick --rerere-autoupdate <range>
git merge --rerere-autoupdate --no-edit <branch>
```

Loop until `git status` reports the rebase/pick finished:

1. **continue-vs-skip rule (non-negotiable).** NEVER run `git rebase --skip` just because there are no
   unmerged files. Run `--skip` ONLY when `git rebase --continue` itself reports the patch became
   empty (`No changes - did you forget to use 'git add'?` / `patch is empty`).
2. **Resolve each unmerged path by type** (`git status --porcelain` / `git diff --name-only --diff-filter=U`):
   - `UD` (modified/deleted) or `DD` (both deleted) -> `git rm <path>` (honor the deletion the branch intends).
   - static/binary add/add (`static/description/*.gif`, images, generated assets) -> take the
     NON-EMPTY side; never leave a zero-byte file.
   - import-only package init: an add/add (`AA`) or both-modified (`UU`) conflict in a package
     `__init__.py` (such as `tests/__init__.py`) whose conflicting hunks on both sides consist only
     of `import` / `from ... import` lines is MECHANICAL -> replace each hunk with the union of both
     sides' import lines, sorted, one per line, duplicates dropped; keep every line outside the
     hunks; `git add <path>`; continue. Any other line inside a hunk -> the marker rule below.
   - text file still containing conflict markers (`<<<<<<<`), other than the import-only case
     above -> STOP, hand to a coder to resolve to intent; do NOT auto-pick a side.
   - unmerged but NO markers (a rerere-replayed resolution) -> verify it matches intent, then `git add <path>`.
   - **Content scope.** Resolve a conflict only to the intent the brief states or by the mechanical
     classes above. Beyond that, never edit, rewrite, reformat or "correct" file content - a path,
     a link, a string, a version - even when it looks wrong. A content question goes back to the
     caller in the report and findings file; the op proceeds or stops on git grounds only.
3. All paths staged and no markers remain -> `git rebase --continue` (a pick:
   `git cherry-pick --continue --no-edit`; a merge concludes with `git commit --no-edit`).
4. `--continue` reports an empty patch -> `git rebase --skip`.
5. **Escalation.** 3 consecutive BLOCKED commits -> `git rebase --abort` and surface state (the rerere
   cache survives the abort).

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

## S7 - Recovery paths (reflog / ORIG_HEAD)

```bash
git reset --hard ORIG_HEAD             # undo the last merge/rebase/reset (one step)
git reflog                             # find any prior HEAD position
git reset --hard HEAD@{N}              # restore to N operations ago
git checkout --no-track -b recovered HEAD@{N}     # rescue a lost tip onto a new branch
```

Reflog is LOCAL and expires (90d reachable / 30d unreachable); the S1 backup branch is the durable
anchor, reflog only the net for an op where a backup was missed.

## S9 - Worktree-always / principal-checkout-lock

Any op that mutates the working tree or moves a branch ref (checkout/switch, commit, rebase,
merge, cherry-pick, reset, tag-move, push-from, etc.) MUST run in a dedicated worktree - never
in the primary/shared checkout, and NEVER by switching the primary checkout off its principal
branch. The primary checkout stays on its principal branch at all times. The single narrow
exception is the S9 carve-out below.

Pure bounded reads (`git status`, `git log -n<N>`, `git diff --stat`) may run anywhere; they do
not mutate and cannot corrupt the shared checkout's branch state.

If a brief asks git-operator to operate in-place on the primary checkout or to switch it off its
principal branch, that is an ERROR: git-operator uses the dedicated worktree instead and reports
its path in the result block. Worktree isolation is ALWAYS required for mutations, never
optional. The sole exception is a brief whose op is exactly the S9 carve-out below, with its
pre-flight proof.

**The caller names the location.** A brief gives `worktree` (the exact absolute path of an
existing worktree, or where to create a new one) or `worktree_root` (a directory; git-operator
creates `<worktree_root>/<branch-slug>`). git-operator never picks a location itself: no sibling
of the repo, no temp dir. A mutation brief with neither field returns BLOCKED asking for one.

```bash
git worktree add <worktree> <branch>   # check out an EXISTING branch at the path the brief names
git worktree add --no-track -b <new-branch> <worktree> <ref>   # create a NEW branch there (S13)
git worktree list                        # confirm isolation
git worktree remove <worktree>           # clean up after verify, when the brief asks for it
```

### S9 addendum - explicit start point, the four branch-creating forms

`git worktree add --no-track -b <branch> <path> <ref>`, `git branch --no-track <branch> <ref>`,
`git checkout --no-track -b <branch> <ref>`, and `git switch --no-track -c <branch> <ref>` are the
four command forms that create a NEW branch to receive work (`--no-track` is S13). All four
SILENTLY resolve the new branch's start point to HEAD - whatever
the invoking checkout currently has checked out - when `<ref>` is omitted. Omitting `<ref>` is
forbidden for any of these four forms whenever the branch/worktree is meant to fork from a NAMED
ancestor: name the ancestor explicitly, every time, rather than relying on the invoking checkout's
ambient position. The S1 backup names the pre-op SHA and the S7 recovery form names a reflog
entry, so both already carry their start point.

A brief that requests one of the four forms without naming `<ref>` fails the Brief self-check's
BASE-ref requirement - a missing-field STOP, never a silent HEAD substitution.

### S9 carve-out - RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN

The one exception to S9, invoked by name as op `RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN`: bringing an
already-dirty primary checkout back into S9 compliance. Scope is exactly:

```bash
git status --porcelain     # pre-flight: prove the work exists elsewhere (e.g. already copied
                            # into the worktree that will carry it) before discarding anything
git reset --hard HEAD      # restore tracked files to the committed state
git clean -fd              # remove untracked files
```

Restores tracked files and removes untracked files - nothing else. Never moves a branch ref,
never switches branches, never commits. The S1 backup cannot capture uncommitted work, so the
pre-flight proof is the safeguard: without it, return BLOCKED.

## S11 - Positional self-check before first mutation

Before the FIRST mutating command in a brief, resolve the repo root of the path about to be
written and compare it against the worktree path the brief named:

```bash
git -C <path-about-to-be-written> rev-parse --show-toplevel
```

Mismatch against the brief's worktree path -> STOP before mutating; return BLOCKED naming both
paths. Run this once per brief, before the first `Edit`/`Write`/mutating `Bash` call - never
after, and never as a self-correction once files are already changed.

## S12 - Command shape

A subagent's Bash working directory resets between calls, and a permission layer judges each call
by its literal text. Every git call therefore has one shape:

```bash
git -C <absolute worktree> <subcommand> <args>
```

- One plain git command per Bash call. No `&&`, `||`, `;`, `|`, `$(...)` or backticks; no
  trailing `echo`, `rc=$?` or `|| true`; no leading `VAR=value`; no `-c key=value` before the
  subcommand. The call's own exit status and output are the result.
- A step that needs an earlier result (a SHA, a branch name, a timestamp) runs in a new call with
  that value written out.
- The recipes in this toolkit show the subcommand and its arguments; run each as
  `git -C <worktree> ...`.
- A commit message goes in with `-m "<subject>"` or `-F <message file>` (C5 in
  `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`).
- Never let git open an editor: `--no-edit` on `commit --amend`, `merge`, `revert`,
  `cherry-pick --continue` and `revert --continue`; conclude a conflicted merge with
  `commit --no-edit` (`merge --continue` opens the editor).
- Replay cached resolutions with `--rerere-autoupdate` on the op (S10).
- Editor check, once per brief: `git -C <worktree> var GIT_EDITOR` and
  `git -C <worktree> var GIT_SEQUENCE_EDITOR`. Both print `true` -> run every `rebase` step
  (`-i --autosquash`, `--continue` after a resolved conflict) as plain commands.
- The ONE exception, only when that check prints anything else and only for `rebase` (its
  `--continue` commits through the editor and has no `--no-edit`). Spell it exactly:

  ```bash
  GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true git -C <worktree> rebase <args>
  ```

  and note it in the findings file. The environment form, not `-c core.editor=true`: the
  environment variables outrank every config level, so a `-c` value loses to an editor already set
  in the environment. Never `git config --local` either: the repository config is shared by every
  worktree.

## S13 - A new branch has no upstream until its first push

When the start point of a new branch is a remote-tracking ref (`origin/<series>`, `origin/main`),
git makes the new branch track it by default. A bare `git push` or `git pull` on that branch then
targets the remote branch it was cut from - often a protected one - and the human-confirm gate
below is bypassed by a default instead of a decision. So:

- Every command that creates a NEW branch carries `--no-track`: the four forms in the S9 addendum,
  the S1 backup branch and the S7 rescue branch. The branch starts with no upstream, whatever its
  start point.
- The first push of that branch names the remote the brief gives as the push target (the fork or
  the branch's own remote, never the remote the base came from unless the brief says so) and sets
  the upstream in the same call:

  ```bash
  git push --set-upstream <remote> <branch>
  ```

- Every other push names its remote and branch too (`git push <remote> <branch>`); a push never
  falls back to whatever upstream a branch happens to carry. A push that would change a protected
  branch is still gated (below), whatever upstream the branch has.
- Never repair an inherited upstream by editing the repository config; it is shared by every
  worktree. Name the remote and branch in the push instead.

## S8 - filter-repo requires a FRESH clone

`git filter-repo` refuses to run in-place and rewrites EVERY commit SHA permanently. Run it only on
a throwaway clone and coordinate with all fork owners:

```bash
git clone --no-local <repo> <fresh clone>
git -C <fresh clone> filter-repo --analyze                          # rename/size report FIRST
git -C <fresh clone> filter-repo --path-glob '*.bak' --invert-paths
```

`--path` does NOT follow renames - pass both old and new paths explicitly.

## Human-confirm gate - protected branch (the one gated op)

Exactly one op class needs explicit human confirmation before it runs - a change to a protected
branch of the remote that does not go through a pull request:

1. A push (plain or force-with-lease) that moves or deletes a protected branch on the remote, or
   merging a pull request into a protected branch.

A protected branch is the remote's default branch (`git ls-remote --symref origin HEAD`), a series
branch named `<major>.0`, or a branch the remote reports as protected
(`gh api repos/<owner>/<repo>/branches/<branch>`, field `protected`). When you cannot tell, treat
the branch as protected. A brief that says "just do it" is not a confirmation.

Every other op is self-decided - force-with-lease to a feature or fork branch, `branch -D`,
deleting a remote branch that is not protected, `reset --hard`, `clean -fd`, filter-repo, deleting
an unpublished tag, squash and every other rewrite. Run it with the S1 backup first, the S6 verify
after, and the evidence (backup name, verify output) in the report; never STOP to wait for a
human. `reset --hard` and `clean -fd` run on a clean tree (S4) or under the S9 carve-out's
pre-flight proof - uncommitted work is never discarded without that proof.

### Gate procedure

1. State the exact command, the protected branch, and what changes on the remote.
2. Record the remote tip before the op (`git ls-remote origin <branch>`) and, for a push, create
   the S1 backup.
3. The brief carries `confirmed: <verbatim human approval>` -> execute. Otherwise STOP and return
   BLOCKED with `gate_hit: protected branch <branch>` - never self-authorize.
4. Verify the remote tip (or the merged pull request) is the intended one.
5. Report with evidence (the recorded and new tips, the backup name).

### Re-dispatch after BLOCKED

When an operator returns BLOCKED at this gate, the CALLER must:

1. Present it to the human with full context: the command, the protected branch, the remote tip
   recorded, and what changes on the remote.
2. Obtain explicit human confirmation - not implied, not inferred.
3. Cold-spawn a FRESH operator with the SAME op brief PLUS an explicit
   `confirmed: <"verbatim human approval text">` field. The new instance reads this field and
   proceeds past the gate.

The git state and any S1 backup persist on disk between dispatches - nothing is lost while the
caller waits. Never self-authorize or pass a fabricated confirmation.
