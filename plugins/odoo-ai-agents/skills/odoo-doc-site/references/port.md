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

## What the writer does with a ported page

Plan rows get `work: port` and `source_series` (`writer-brief.md`). Per row:

- **Text.** Keep and adapt. Re-verify every fact against the TARGET series: `api_version_diff` from
  source to target for each module on the page, `check_module_exists` on the target, and every
  menu, button and field name against the target's live UI. The target UI wins over the source
  text; a difference that matters is a finding.
- **Shape.** Follow the target series' nearest sibling pages (`repo_facts.py` on the target
  worktree), not the source page.
- **Images.** Ship no source-series screenshot. Recapture every image on the target series' branded
  capture instance, keeping the file names; where an image already exists on the target, keep its
  size.
- **Translation.** Regenerate the target template with `po_sync.py`. The source `msgstr` values are
  translation memory only; every UI term must match the target-language UI of the target series
  (`ui_terms.py`).
- **Links.** Marketplace links move to the target series by the policy pattern; follow module
  renames found by `api_version_diff`.

## Dedupe

The page plan search (`page-plan.md`) runs on the target base branch (the target series' upstream
branch of `remote`), never on the port worktree. The open-pull-request skip rule excludes the
source pull request and a bot forward-port pull request for the same source and target. When the
target already has an equivalent page, the row is `update`: merge the ported content into that
page and keep its URL; no second page is added.

## Landing a taken-over branch

- The user can push to the bot branch (it is not a protected branch): push the fixes to that branch
  through `git-toolkit:git-ops`, one commit per the row's `commit` policy, with a lease. The bot's
  pull request updates; open no other.
- Otherwise: push to `fork_remote`, open one pull request whose body names the bot pull request it
  supersedes, and ask the user whether to close the bot pull request.
- Never open a second pull request silently.

## Then

Gates, browser acceptance and CI run as for any run; landing as § Landing a taken-over branch on a
taken-over branch, as for any run otherwise. The pull request body names the
source pull request or commits, the source series and, for a later target, the previous target's
branch it was ported from.
