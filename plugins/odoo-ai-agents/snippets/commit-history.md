# Commit history of a pull request

The commits a pull request shows are complete changes: each one is a business outcome with
everything it needs, and none exists only to correct another commit of the same pull request.
git-ops states the general rule in its commit convention and applies it on every commit request;
this card adds what an Odoo run needs.

| Case | Shape |
|---|---|
| A fix for a defect a commit of the PR introduced - a review, CI or acceptance finding, a fix of a fix | folded into that commit: the commit request carries `corrects: <what>`; git-ops folds it, pushes the branch again and returns `folded_into:` |
| A module added or removed, with the changes this forces in other modules | ONE commit |
| A plan run with an `integrate` node | node commits and `run-integration` are working history: every commit is requested plainly, a fix round included, and `integrate` rewrites them into the PR's commits |
| A forward-port PR | `${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md` § C3 |

A launcher never asks a worker for a separate fix commit, and takes a folded commit on a
re-pushed branch as the expected result.
