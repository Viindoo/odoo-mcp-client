# Git delegation contract

## Universal rule

No actor of this plugin runs git - not a mutation, not a read, not inside a wrapper or a script
you write. How to operate git lives only in git-toolkit. Two doors:

1. **A repo fact -> the odoo-local `repo_facts` tool:** the repository root and the main checkout
   behind a linked worktree, the current branch or ref, the short HEAD SHA, the origin URL,
   whether given paths are clean or dirty (`status_paths`), whether a merge, rebase or cherry-pick
   is in progress. `is_repo=false` means the directory is outside any repository.
2. **Everything else -> a request to the `git-toolkit:git-ops` skill:** history, diffs, file
   lists, ancestry, branch lists, a worktree, every change to the repository, every GitHub
   operation (`gh` and the GitHub MCP tools are git-ops's too).

Whoever creates or edits a git-tracked file commits it through git-ops, which detects the repo's
commit convention and signs off where the repo requires it. A call the permission classifier
refuses: `${CLAUDE_PLUGIN_ROOT}/snippets/permission-denial.md`.

## Asking git-ops

Invoke `git-toolkit:git-ops` with the Skill tool. A request states what is wanted and what must
come back; git-ops picks the specialist, the commands and the safety steps.

- **Say the outcome**, never a command, a flag or a verb list: "the merge base of the feature
  branch and the new base, and the non-merge commits after it".
- **Say the shape of the result.** A single value comes back in the reply. A list, diff, log or
  per-file listing is written by git-ops to a path you name under the run's `ISOLATE_DIR`, and
  you read that file - never unbounded output inline.
- **Say how to tell it worked:** "return the new tip SHA and whether the tree is identical to the
  one before".

## Invocation contract

A request carries at least:

- `op`: one line describing the operation;
- `scope`: the refs, range or paths;
- `worktree`: the absolute path of the dedicated worktree - an existing one, or the path
  `project_dir` (axis `worktree`) returned for a new one
  (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`). A mutation never targets the
  principal checkout, which stays on its principal branch;
- `commit`: the files and the business outcome, never a finished message. A proposed Odoo `[TAG]`
  comes only from the TAG table of git-toolkit's Odoo commit convention. git-ops returns
  `commit_subject:` and `message_rewritten:`; relay a rewrite, never re-commit it;
- `confirmed: yes - <quoted human approval>` for the one gated op (below);
- `USER LANGUAGE: <language>`.

## Who commits

A leaf worker (`odoo-frontend-coder`, `odoo-test-writer`, `odoo-impact-recon`,
`odoo-icon-designer`, any agent that cannot launch agents) runs no git and never invokes git-ops:
it writes its files in `WORKTREE_PATH` and returns the list
(`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`). The actor that can launch agents commits by
invoking git-ops inline: the main agent, a skill or workflow phase, and a node owner -
`odoo-coder` commits its own node once its whole-node test is green and returns the range.

## Fresh base first

Before any work on a repository - code, module docs, a docs site - the ref the work starts from is
brought up to date with its upstream through ONE git-ops request that names the ref. This holds
for a worktree or branch created from a base, a range or merge base computed against a branch, a
review of a branch, a docs-site series branch, and the source and target of a port or a rebase. A
base that cannot be refreshed (no network, no upstream, a diverged local tip) is a `BLOCKED` or an
`open_question`, never a silent build on the stale tip. `repo_facts` describes the tree as it is;
it does not replace the refresh.

## Base-branch resolution

A worktree or branch created to receive work starts from the series' main branch, resolved here -
never from whatever the invoking checkout has checked out. The `branch` and `ref` of `repo_facts`
serve diagnosis and the inference of a source series; they are never assigned to a `base`. One
exception: the docs worktree of `odoo-doc-illustration` starts at the principal checkout's HEAD
commit, named explicitly, because docs describe the code the user pointed at.

Input: the run's resolved `odoo_version`
(`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`). A candidate is a local or
remote-tracking branch whose name EXACTLY equals `<odoo_version>`, `saas-<odoo_version>`, or a
vendor-prefixed form that the brief or the repo's history carries - never a name that merely
contains the series. One git-ops request enumerates the candidates, compares their tips and
fetches when needed.

| Case | Action |
|---|---|
| No candidate | `NEEDS_CONTEXT(base_branch)`: ask which branch is the series' main branch; never invent one, never fall back to HEAD |
| One candidate, no remote-tracking ref | use the local tip and state that assumption in the plan or report |
| One candidate, local and remote tips equal | use the remote-tracking ref |
| One candidate, tips still diverged after a fetch | `open_question`: the human chooses the remote or the local tip |
| Several distinct candidates | `open_question` listing each |

A detached HEAD or a dirty tree on the invoking checkout does not affect the resolution.

## Self-provisioning specialists

`odoo-forward-port`, `odoo-git-rebase`, `odoo-modules-upgrade` and `odoo-code-review` at
`TARGET=pr` create their own worktree and branch: a caller provisions none for them. The worktree
of every other source-writing node is provisioned by the plan runner, forked from the repo's
`run-integration` branch (`plan-mode-schema.md` § Running the plan, step 2).

`odoo-doc-illustration` provisions only when its target is a principal checkout: it moves the run
into a new docs worktree and branch at that checkout's HEAD commit, after a `repo_facts` call
(`status_paths` = the module paths) whose uncommitted changes it puts to the user once (commit
them first, or document HEAD without them). On a run it receives the run's worktree like any
source-writing node, and a linked worktree it receives is used as is.

## The one gated op

A push that moves or deletes a protected branch without a pull request, and merging a pull request
into one, need explicit human confirmation first: present the module, the branch and what changes
on the remote, then pass `confirmed: yes - <quote>`. Without it git-ops returns `BLOCKED`. Every
other op (a rewrite, a squash, a force-with-lease push to a feature or fork branch) git-ops
decides itself; never ask the human for it.

## Results and the conflict resume

| git-ops returns | The caller |
|---|---|
| `DONE` | continues |
| `BLOCKED`, `gate_hit: protected branch ...` | obtains the confirmation above and invokes again |
| `BLOCKED`, `gate_hit: S4 dirty tree` | settles the uncommitted changes (they are never stashed), then invokes again |
| `BLOCKED-CONFLICT` with `conflicted_files` and `stopped_commit` | runs the resume loop |

Ask git-ops to resolve every mechanical conflict itself (`.po`, `.pot`, binary and generated
files, a package `__init__.py` whose conflicting hunks are import lines only) and to stop at the
first conflict that needs Odoo judgement. The interrupted operation stays on disk between
invocations, so the resume loop is: launch a resolver (the node's coder) into the worktree to edit
the conflicted files - a file edit, never a git operation; invoke git-ops again to stage them and
continue the operation in progress; repeat until `DONE` or a `BLOCKED` that is not a conflict.
