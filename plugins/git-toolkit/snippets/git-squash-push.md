<!-- SSOT snippet. Domain-agnostic recipe for op=squash-push: stale-base guard + squash-to-one
     commit + force-with-lease push. This is a COMPOSITION of S1 (backup), S6 (tree-identity),
     and S2 (force-with-lease) from git-safety-contract.md onto a stale-base guard - not a
     re-explanation of those primitives. Referenced by git-operator via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-squash-push.md. Edit here only. -->

# git-squash-push recipe (SSOT)

Squash every commit above `origin/<principal>` on the integration branch into a single commit,
verify tree identity, then force-with-lease push to the remote. This composes the S1, S6, and S2
primitives from `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`; see that file for the
primitive semantics. All commands run inside the dedicated `<worktree>` (S9 - never the primary
checkout). The recipe needs no human confirmation: the S1 backup and the S6 verify make it
reversible. Only an `integration-branch` that is a protected branch (the gate in the safety
contract) needs `confirmed:` before step 5.

## Inputs

| Parameter | Meaning |
|---|---|
| `worktree` | Absolute path to the dedicated integration worktree (S9: never the primary checkout) |
| `principal` | Branch name tracked at `origin/<principal>` (e.g. `master`, `main`) |
| `backup-ref` | Tag name for the S1 backup (e.g. `backup/squash-YYYYMMDDHHMMSS`) |
| `commit-msg` | Caller-proposed commit message for the squashed commit - a proposal, validated (and rewritten on mismatch) against C6 in step 3 before it reaches `git commit`, never passed through unchecked |
| `integration-branch` | Local and remote branch name to push (e.g. `integration/feature-batch`) |

## Steps

### 0a - Fetch (stale-base guard, MUST run first)

```bash
git fetch origin <principal>
```

A stale local `origin/<principal>` causes `reset --soft` to land on the wrong commit range.
Always fetch before computing the ancestry.

### 0b - Ancestry check

```bash
git merge-base --is-ancestor origin/<principal> HEAD
```

Exit 0 -> integration branch is ahead of `origin/<principal>`; proceed.
Non-zero -> principal has advanced past the integration branch. ABORT: rebase the integration
branch onto `origin/<principal>`, re-verify, then retry from step 0a.

### 1 - S1 backup (before squash)

Implemented as a tag rather than a branch so it survives worktree removal without a dangling
branch ref. See S1 in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`.

```bash
git tag <backup-ref> HEAD
git rev-parse HEAD   # record pre-op SHA
```

### 2 - Reset --soft to base

```bash
git reset --soft origin/<principal>
```

All commits above `origin/<principal>` collapse into the index. The working tree is unchanged.

### 3 - Validate, then commit

Run C6 (`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`) on `<commit-msg>` FIRST; commit
the validated-or-rewritten string, never the raw input, and report it in `commit_subject:` and
`message_rewritten:`. Write it to a message file (C5), then:

```bash
git commit -F <message-file>
```

When C4 requires sign-off, add `-s` and confirm the `Signed-off-by:` trailer landed.

### 4 - S6 tree-identity gate

```bash
git diff --quiet <backup-ref>
```

Exit 0 (no diff) -> tree-identity confirmed; proceed.
Non-zero -> content diverged. ABORT: restore from `<backup-ref>`, name the diverged paths in your report,
do NOT push. See S6 in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`.

### 5 - S2 force-with-lease push

```bash
git push --force-with-lease origin <integration-branch>
```

See S2 in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md` - `--force-with-lease` bails
if the remote advanced since the last fetch; bare `--force` is banned.

## Hazard notes

- **Stale-base reset-soft hazard.** `reset --soft` with a stale `origin/<principal>` lands on the
  wrong base, producing a squash that includes or excludes unintended commits. Step 0a (fetch
  first) is mandatory.
- **Empty-tree artifact.** The SHA `4b825dc642cb6eb9a060e54bf8d69288fbee4904` appears in diff
  output only when the squash accidentally produced a literally empty commit, indicating a
  misconfigured base ref. The authoritative check is the `git diff --quiet <backup-ref>` exit code
  in step 4; the empty-tree SHA is a diagnostic artifact for an unexpectedly empty squash, not
  part of the verification gate itself.
- **force-with-lease vs force.** `--force-with-lease` bails when the remote has advanced;
  bare `--force` silently clobbers a teammate's push. Always use the former (S2).
