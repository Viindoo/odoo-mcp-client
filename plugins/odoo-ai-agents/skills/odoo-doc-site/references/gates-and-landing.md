# odoo-doc-site - gates, landing, CI

Scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/lib/docs_site/`. `build_compare.py`, `po_sync.py`
and `images.py install` run with `DOCS PYTHON` (`SKILL.md` step 0); every other script with the
plugin `python3`. Every gate that takes the policy reads `<RUN_DIR>policy.json`.

## Gates

Run in this order on each series worktree; fix and re-run until every gate is clean, at most 3
rounds, then `BLOCKED` with the findings left.

1. `build_compare.py` - builds the source language and every site language of the worktree and of
   its base commit in the same environment and compares them. The change must add no Sphinx
   WARNING or ERROR; report the difference against the base, never an absolute count.
2. `po_sync.py verify` - every message of the plan's pages has an entry in every non-source
   catalog, none empty or fuzzy.
3. `images.py check --source-lang <first site language>` - every image a planned page uses exists
   for every target language; the source language may use the plain image.
4. `content_gates.py --policy <RUN_DIR>policy.json --capture-text <RUN_DIR>capture-text.jsonl` with
   the built CSS: presentation rules, banned terms in text and in the capture-text log
   (`banned_terms_exempt_paths` excepted), version prose. It lists the images with no capture
   record as `IMAGES_TO_REVIEW`; pass that list to browser acceptance.

A gate that cannot run is `UNVERIFIED` with its reason; it is reported in the PR body and the
return. Browser acceptance (`acceptance.md`) follows the gates; a rebuild after an acceptance fix
re-runs the gates its change touches. A finding goes to the writer as `FINDINGS`.

## Land

- Commit through `git-toolkit:git-ops`. `commit` = `one-per-pr`: one commit for the PR;
  `per-area`: one per area. The subject follows the style of the `commit_subject_samples` that the docs-site tooling's `scripts/lib/docs_site/repo_facts.py --worktree <SITE WORKTREE> --page <first planned page>` returns (not the plugin's `scripts/lib/repo_facts.py`, which answers only the repository facts).
- Push to `fork_remote` with a lease; open the PR against the series branch of `remote`.
- `LAND: caller`: no commit, no push, no PR; the file list goes back to the caller, which lands
  it (`odoo-forward-port` lands one merge commit, never a squash: `commit` governs the pages a run
  writes, never a merge).
- PR body: the page plan; pages added, updated and removed with their site URLs; how it was built and against
  which base commit; the gates and the browser acceptance with their result; what is left (`UNVERIFIED` items, findings).
  Never an absolute warning count.

## CI

Read the docs repository's CI result for the PR through `git-toolkit:git-ops`. Pending: report
`PENDING` with the PR URL and stop.

| Verdict | Evidence |
|---|---|
| Docs failure | a Sphinx WARNING or ERROR before the build-finished line, or a failed build |
| Infrastructure failure | an error after both language builds succeeded, raised inside the system site-packages or a third-party checkout, and the same image is green on an unrelated PR |

Report which one with the log lines. A docs failure goes back to the writer. An infrastructure
failure never changes the PR: report it to the user.
