# odoo-doc-site - port pages to higher series

`PORT FROM <series>` names the source series and a source: a docs pull request number, a commit
range, or an area of pages. The targets are one or more higher `SERIES`. The run repeats steps 0-9
of `SKILL.md` per target, with the changes below.

## Order and chaining

One target at a time, lowest first. The first target ports from the source series; every later
target ports from the previous target's ported result, its pushed branch, not from the original
source. One worktree, one branch and one pull request per target. Never start a target before the
previous one has passed its gates.

## Starting point

Per target:

1. The site row's `policy.forward_port_branch_pattern` (placeholders `{pr}` and `{series}`) names the
   branch an automatic forward port would use. A key that is absent means the site has no such
   automation. When the pattern is set and `remote` holds a branch matching it for this source
   pull request and target, read it through `git-toolkit:git-ops`: take that branch over, check it
   out into the target worktree, and fix it. It lands as § Landing a taken-over branch says.
2. Otherwise create the worktree and a new branch from the target series' upstream branch, and
   invoke `git-toolkit:git-ops` to cherry-pick the source commits onto it. A conflict is resolved
   keeping the structure of the target branch: its file layout, its toctree and its page shape win
   over the source's.
3. An area of pages has no commit set: have `git-ops` copy the pages, their images and their
   translation entries from the source branch into the target worktree.

## Plan rows

Plan rows get `work: port` and `source_series` (`writer-brief.md`). When the target already has an
equivalent page, the row is `update`: merge the ported content into that page and keep its URL; no
second page is added.

## Landing a taken-over branch

- The user can push to the bot branch (it is not a protected branch): push the fixes to that branch
  through `git-toolkit:git-ops`, one commit per the row's `commit` policy, with a lease. The bot's
  pull request updates; open no other.
- Otherwise: push to `fork_remote`, open one pull request whose body names the bot pull request it
  supersedes, and ask the user whether to close the bot pull request.
- Never open a second pull request silently.

## Then

Gates, browser acceptance, landing and CI run as for any run; a taken-over branch lands per
§ Landing a taken-over branch. The pull request body names the source pull request or commits, the
source series and, for a later target, the previous target's branch it was ported from.
