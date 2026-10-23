# odoo-forward-port - the docs-site lane

A docs-site repository (Sphinx, one branch per series, declared as a site row - `SKILL.md` P0
`REPO KIND: docs-site`) is forwarded by the SAME pipeline and the SAME git shape as code: ONE
merge of the range tip into an integration branch from the target series, closed by ONE merge
commit; never a cherry-pick, never a squash (Hard rule 2). Only the content phases differ. Every
phase not named below runs as `SKILL.md` states.

## Several targets

One target series per run, lowest first. The next target's `<source-ref>` is the previous
target's pushed integration branch, never the original source. A target starts only after the
previous one's PR is open.

## P0 - recon

Read the site row (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-site/references/site-row.md`) and
record `series`, `languages`, `repos`, `policy.forward_port_branch_pattern` and `fork_remote`.
When the pattern is set and `remote` holds a bot branch for this source pull request and target
(a `repo_facts` call lists branches; the pattern's `{pr}` and `{series}` filled), record its
name: the run still merges the range tip; the PR body names the bot pull request it supersedes.

## P1-P2 - per page, not per module

The unit is the PAGE. From `range.md`, list every page the range touches with the images and
translation entries that belong to it, and the modules each page documents (the mapping of
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-site/references/page-plan.md` § 1, OSM at the TARGET
series). No `odoo-intent-extractor` and no `odoo-installable-prober` are dispatched. Each page
takes one bucket:

| Every module of the page at the target | Row | Meaning |
|---|---|---|
| installable | `port` | the page is re-verified on the target: facts, screenshots, version prose, marketplace links |
| at least one `installable: False` or absent | `skip` | forwarded as it is - text, images and translation entries unchanged |

A page whose modules are all absent at the target is listed at P4 with `skip` proposed; the human
may drop it (`refine:`).

## P4 - the plan

The plan gate shows the page table above, the series-specific files the merge must resolve to the
target (`conf.py` version and release, the `Makefile` build directory, the toctree of the target
branch), the bot branch found at P0, and the ONE merge commit. The `Docs:` line is absent: the
run IS the documentation.

## P5-P7 - merge and resolve

P5 merges the range tip. A conflict is resolved keeping the structure of the target branch: its
file layout, its toctree and its page shape win over the source's. The symbol-survival checks are
replaced by the build gates: before any adapt, run the gates of
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-site/references/gates-and-landing.md` § Gates on the
integration worktree with every `port` and `skip` page as the plan (the series-specific lines of
the paragraph above are fixed here, by you, inside the merge window).

## P8-P11 - adapt, verify, accept

Invoke `odoo-doc-site` ONCE (via the Skill tool) with `SITE`, `SERIES` = the target,
`WORKTREE` = `<path>/fp-integration`, `LAND: caller`, `PAGE PLAN` = the P4 page table (`port`
rows with `source_series` = the source series; `skip` rows as such), `RUN_ID`. It provisions the
capture instance, launches `odoo-doc-site-writer` per `port` group, runs the gates and the
browser acceptance (`odoo-qa-tester` `MODE: DOCS`), tears down and returns its file list. That
return is P9 and P11 of this lane; P9.5 and P9.6 do not exist here.

## P10 and P12 - one merge commit, the PR

P10 stages the returned files and concludes the merge with ONE commit (`SKILL.md` P10). P12
pushes `fp/<slug>` to `fork_remote` and opens the PR against the target series branch of
`remote`; the PR body states the source pull request or commits, the source series, that the
branch is a merge to be landed with a merge commit (no squash, no rebase), the bot pull request
it supersedes when one exists, the page table, and the gate and acceptance results. Then ask the
user whether to close the bot pull request. CI is read as `gates-and-landing.md` § CI says. No
`odoo-code-review` runs; the closing documentation step of `SKILL.md` does not run.
