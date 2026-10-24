# odoo-doc-site - the check shot

One screen per site language, captured before any page work and judged by this skill, no question
asked. It must show the right language, the demo company of that language (`policy.demo_company`),
the site's theme, a content width inside the theme's column and no error banner.

## Instance

Provisioned with the parameters of `SKILL.md` step 3.

## When it runs

`check_shot` is `first-per-series`: when the site and series have no content-width record.
`always`: on every run. Otherwise skip the step and reuse the recorded `reference_viewport` and
`content_width`.

## Capture

Launch `odoo-doc-site-writer` with a PAGE PLAN holding the single row `work: check-shot` and the
screen to capture (the first app menu of the area), and the content page it measures: a published
page of the SAME KIND as the planned pages (a task page for task pages, an index for an index -
the nearest sibling of the first planned page; an index page and a page that hides its local
table of contents are wider than a task page with one), never a page of another kind. The writer captures it per language following
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` and returns the paths,
`reference_viewport` and `content_width`; it writes no page.

## Judge

Open every returned image and rule it against the list in the intro. A shot that fails is a defect
of the instance, never a shot to keep: fix it (a language not loaded, a missing module: through
`odoo-instance`; a wrong company name or an error banner: the cause on the instance), recapture the
failed languages and judge again. After 3 failed rounds return `BLOCKED` with the images and what
differs from the list.

## The content width

The check-shot launch gets `SERVED URLS` of the fresh build (`SKILL.md` step 0), opens the content
page at a desktop reference viewport and reads the CSS width of the main article element from the
DOM, the element named by its role in the page, not by a theme-specific selector. It returns
`reference_viewport` and `content_width`.

Store: `<SHARE_DIR>/docs-site/<site>/<series>/content-width.json` (`site`, `series`, the capture
instance key, `reference_viewport`, `content_width`, `measured_page` and its `page_kind`), written
by this skill after the shots are judged. Every later capture derives its viewport width from `content_width` (at most 1.25 times
it).
