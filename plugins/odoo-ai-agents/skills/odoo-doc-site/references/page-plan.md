# odoo-doc-site - find existing content, then plan

Done per series, before any worktree or page is written. Never plan a page before the search below
ran.

## 1. Map the area to modules

The `AREA` or module list resolves to technical modules: the series' OSM profile (`set_active_version` with the series, then
`describe_module`, `module_inspect`), then the catalog instance's profile and addons. Keep per module: technical name,
user-facing app name, menu path, the roles that reach it (the role map of `odoo-doc-feature-map`
when it exists).

## 2. Search what already says it

On the series' upstream branch of `remote` as fetched (`content/` tree and target-language `.po`
files, read through `git-toolkit:git-ops`), never on a worktree that holds ported or edited pages,
search for each module:

- its technical name, its app name, its marketplace link (the row's pattern filled in);
- the menu paths and the headings of its screens, in the source language and in the target one;
- the titles of the candidate pages.

A hit on a menu path or a heading counts as coverage even when the module name is absent.

Then list the open pull requests of the docs repository that touch the area, read-only, through
`git-toolkit:git-ops`: title, branch, files, state. A page an open
pull request already adds is `skip` with that pull request as the reason, never a rival copy.
With `PORT FROM`, leave out of this rule the source pull request and a bot forward-port pull
request for the same source and target (`port.md`).

Module guides (`doc/*.rst` inside the modules, target-language variants included) are SOURCES for
the writer, not duplicates; list them per page as `sources`.

## 3. The page plan

Write `<SHARE_DIR>/docs-site/<site>/<series>/<area-slug>/page-plan.md`, one row per page:

| Field | Value |
|---|---|
| `page` | the docs path without extension |
| `action` | `update`, `new`, or `skip` with the covering URL or pull request |
| `url` | the published URL under `site_url_prefix`; for `update` it never changes |
| `toctree_parent` | the index page that lists it (a `new` page must have one) |
| `roles` | the audience role(s) the page addresses |
| `modules`, `sources` | the modules it documents; the module guides it draws from |
| `work` | `compose`, `port`, `recapture`, `relabel`, `wire` or `fill` (`writer-brief.md`) |
| `shots` | `all`, or the screens to recapture (`FROM CHANGE`: only those its features touch) |
| `group` | the disjoint page group: no two groups touch the same file |
| `source_series` | `work: port` rows only: the series the page is ported from |

A published page is never renamed or moved. A plan that needs one stops for a human decision.

With `FROM CHANGE`, read the change file and keep only the pages whose content its features change;
every other page is absent from the plan, not `skip`.

## 4. The gate

When this skill owns the request, present the plan with the open pull requests found through Plan
Mode (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request):
`EnterPlanMode`, present the plan, `ExitPlanMode` on approve. `refine: [feedback]` recomputes the
plan; `cancel` leaves nothing behind and stops.

Under an approved plan - a plan node, a workflow phase, the closing documentation of another run -
present no gate: write the page plan into the return and the PR body, and continue.
