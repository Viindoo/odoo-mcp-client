# odoo-doc-site - the check shot

One screen per site language, captured before any page work. It must show the right language, the
demo company of that language, the site's theme and no error banner.

## Instance

The instance behind the shot is provisioned by `odoo-instance` in `CONTEXT: doc`, default mode,
through its `odoo-instance-ops` agent at the flat haiku tier (launch reason (d) of
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Launch economics), with the
parameters of `SKILL.md` step 3. Keep the returned
`INSTANCE_HANDLE` verbatim for the writers and the teardown; releasing this run's own lease at the
end stays inline.

## Capture

Launch `odoo-doc-site-writer` with a PAGE PLAN holding the single row `work: check-shot` and the
screen to capture (the first app menu of the area), and the content page it measures: the area's
index page, else the first planned page. The writer captures it per language following
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` (§ Browser exclusivity + server family, § Run/module-scoped staging, § Auth, § On-theme check, § Capture step and § Per-locale capture loop) and returns the paths, `reference_viewport` and `content_width`; it writes no
page.

## Decide

Store: `<SHARE_DIR>/docs-site/<site>/<series>/check-shot/` holding the approved images and
`approval.json` (`site`, `series`, `languages`, the approval date, the capture instance key,
`reference_viewport` and `content_width`), which this skill writes from the writer's returned values.

- `check_shot` is `first-per-series` and an approval exists for this site and series: compare the new
  shots with the approved ones by looking at them. Continue unless a language, the company name,
  the theme or the layout differs.
- `check_shot` is `always`, no approval exists, or the comparison differs: show every shot to the
  user and wait. On approval, replace the stored shots and `approval.json`.

## The content width

The check-shot launch gets `SERVED URLS` of the fresh build (`SKILL.md` step 0), opens the content
page at a desktop reference viewport and reads the CSS width of the main article element from the
DOM, the element named by its role in the page, not by a theme-specific selector. It returns
`reference_viewport` and `content_width`; this skill records them in `approval.json`. Every later capture derives its viewport width
from `content_width` (at most 1.25 times it), and the acceptance legibility check uses the same value.
A record that already holds `content_width` is reused unless `check_shot` is `always`.

A rejected shot ends the step: fix the instance (language not loaded, wrong demo company, wrong
modules) through `odoo-instance`, then repeat; after 3 rejected rounds stop and ask the user.
