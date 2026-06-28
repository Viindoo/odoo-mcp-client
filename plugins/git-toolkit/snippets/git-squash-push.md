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
checkout).

## Inputs

| Parameter | Meaning |
|---|---|
| `worktree` | Absolute path to the dedicated integration worktree (S9: never the primary checkout) |
| `principal` | Branch name tracked at `origin/<principal>` (e.g. `master`, `main`) |
| `backup-ref` | Tag name for the S1 backup (e.g. `backup/squash-YYYYMMDDHHMMSS`) |
| `commit-msg` | Full commit message for the squashed commit |
| `integration-branch` | Local and remote branch name to push (e.g. `integration/wave-42`) |
| `confirmed` | Verbatim human approval text (required before step 5; see S2 gate) |

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

### 3 - Commit with provided message

```bash
git commit -m "<commit-msg>"
# add -s for DCO sign-off when the repo requires it
# (follow ${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md)
```

### 4 - S6 tree-identity gate

```bash
git diff --quiet <backup-ref>
```

Exit 0 (no diff) -> tree-identity confirmed; proceed.
Non-zero -> content diverged. ABORT: restore from `<backup-ref>`, report the diff to the caller,
do NOT push. See S6 in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`.

### 5 - S2 force-with-lease push (requires confirmed)

Gated by destructive human-confirm gate item 1 in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`. The brief MUST supply `confirmed:
<verbatim human approval text>`; if absent, STOP and return BLOCKED naming this gate.

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
