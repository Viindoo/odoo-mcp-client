# odoo-doc-site - browser acceptance

The tester is `odoo-qa-tester` with `MODE: DOCS`.

## Serve

Run `${CLAUDE_PLUGIN_ROOT}/scripts/lib/docs_site/build_compare.py serve --work-dir <D> [--port 0]`
in the background, `<D>` being the work directory of the gate build. It prints the base URL per
language. Read the URLs from its output; stop it at teardown. After a
rebuild, stop it and serve again.

## Launch (`odoo-qa-tester`)

`DISPATCH MODEL` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier
selection: items that compare an observed value with a stated one (1, 2, 4-11) are haiku; items
that judge what an image shows (3, 12) are sonnet. A launch that includes item 3 or 12 is sonnet.

```
DISPATCH MODEL: sonnet | haiku
MODE: DOCS
ORACLE_PATH: <abs path of the checklist file, written below>
MODULES: none
WORKTREE_PATH: <series worktree>   ODOO VERSION: <series>
SERVED URLS: <language: base URL, one line per site language>
PAGE PLAN: <abs path of page-plan.md>
IMAGES TO REVIEW: <the IMAGES_TO_REVIEW list of content_gates.py, repo-relative paths | none>
BANNED TERMS: <policy.banned_terms>
BROWSER_MODE: headless   SLUG: <site>-<series>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
REPORT_PATH: <abs>
USER LANGUAGE: <lang | omit>
```

Write the checklist to `<SHARE_DIR>/docs-site/<site>/<series>/acceptance-checklist.md` from the
table below, unchanged, under one header line:
`reference_viewport: <WxH> | content_width: <px> | density: 2 | mobile_viewport: 390x844`
(`reference_viewport` and `content_width` from the content-width record). The tester covers every
plan row whose action is not `skip`, in every language, at a desktop and a mobile viewport, and
opens every image of `IMAGES TO REVIEW` (item 12).

## Checklist

| # | Item | Pass when |
|---|---|---|
| 1 | Reachable | the page opens from the navigation or the toctree of its parent; title and breadcrumb are the planned ones |
| 2 | Images load | after each image is scrolled into view, its natural width is above zero |
| 3 | Language variant | each image shows the interface in the page's language |
| 4 | Placement | at the reference viewport each image spans the recorded content width and has no text beside it |
| 5 | Legibility | at the reference viewport, rendered width divided by intrinsic CSS width (natural width divided by the shot's density) is at least 0.75; judged on the desktop viewport only |
| 6 | No horizontal scroll | the mobile page does not scroll sideways; a wide table scrolls inside its own box |
| 7 | Internal links | every internal link and anchor answers on the local server; none is a 404 |
| 8 | External links | every marketplace link answers 200; `UNVERIFIED` when the network is unavailable |
| 9 | Presentation | admonitions and semantic classes render styled |
| 10 | Console | no console error on load or after scrolling |
| 11 | Language switch | the switch reaches the same page in the other language |
| 12 | Image content | an image of `IMAGES TO REVIEW`, opened as a file, shows no banned term and no off-brand UI |
| 13 | Embedded video | a video embedded on the page is narrated in the page's language (its id is the one the plan lists for that language); a page with no video in its language embeds none |

## Loop

A `FAIL` row goes to the writer as `FINDINGS` (`<file>:<line>: ACCEPTANCE: <item> <page>
<language> <viewport>`) with the evidence path. After the fix: rebuild, re-run the gates the change
touches, re-serve, and send the same tester the failed items with the new URLs by `SendMessage`; a
fix that changes layout or an image re-runs the whole checklist. After the third failed round return
`BLOCKED` with the failed items and their evidence. `UNVERIFIED` items go to the PR body, not to the writer.
