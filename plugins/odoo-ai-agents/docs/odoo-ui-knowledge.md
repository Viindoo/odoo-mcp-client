# Odoo UI Knowledge (SSOT for visual skills)

Portable, version-aware reference shared by the visual skills (`odoo-ui-review`,
`odoo-visual-regression`, `odoo-demo-recording`) and the `odoo-ui-reviewer` / `odoo-ui-debugger`
agents. Contains no instance-specific or confidential values - concrete URLs, logins, and
baseline directories live in each project's `.odoo-ai/context.md`.

## URLs and entry points

| Purpose | Path | Notes |
|---------|------|-------|
| Login | `/web/login` | Same across all supported versions. Submit credentials, then store the session. |
| Backend (web client) | `/odoo` (v17+) · `/web` (≤ v16) | v17 renamed the backend mount point. Use the version to pick the right path. |
| Website frontend | `/` and module routes (e.g. `/shop`, `/my`, `/my/invoices`) | Public/portal pages rendered by the `website` stack, not the backend client. |
| Portal | `/my` | Authenticated customer-facing pages. |

Always log in via `/web/login` first; navigating a backend URL while unauthenticated redirects to
the login page and produces misleading screenshots.

## Backend selectors (web client)

| Region | Selector | Notes |
|--------|----------|-------|
| Form view | `.o_form_view` | Active record form. |
| List view | `.o_list_view` | Editable/non-editable list. |
| Kanban view | `.o_kanban_view` | Card layout. |
| Main content area | `.o_content` | Wraps the active view; useful as a screenshot crop region. |
| Action manager root | `.o_action_manager` | Container for the current action. |
| Control panel | `.o_control_panel` | Breadcrumb + view switcher + search. |

These class names are stable across recent versions; the *mount path* (`/odoo` vs `/web`) is the
version-dependent part. The view-type and form-internal selectors below were confirmed against the
indexed Odoo source; the web client occasionally renames a class across a major, so confirm the
live class names with a DOM snapshot for the version under review before relying on one.

## Grounding a screen's structure before checking its render

OSM is the PRIMARY source for what a screen *should* contain: `set_active_version(odoo_version=<concrete>)`
to pin the version, then `module_inspect(name=<module>, method='views', odoo_version=<version>)` for the view arch a module ships and
**which view types its action exposes**, `find_examples` for how a given view type is typically structured, and
`model_inspect(model=<model>, method='summary', odoo_version=<version>)` for the backing model - whether it inherits `mail.thread` /
`mail.activity.mixin` (so a chatter / activity view is expected) and whether it declares date fields (so a
calendar is viable). OSM is indexed, cross-version, inheritance-resolved, and checkout-free; reading the view
XML or SCSS on disk is the FALLBACK, used only when OSM is missing the entity. OSM is STATIC (no live records) -
it tells you what to *expect*, never what actually rendered, so always confirm the real render in the browser
(`take_snapshot` for the live DOM/a11y tree).

## Break-signal taxonomy (what a render defect looks like)

Map every render failure to one of these classes so a finding is precise and locatable. The per-view tables
below cite these tags.

| Tag | Break class | What it looks like on the rendered screen |
|-----|-------------|-------------------------------------------|
| G1 | xpath-inherit broken | the view fails to load (ParseError) or an inherited field / button / page is silently absent |
| G2 | duplicate / hidden field | a field renders twice, or a `required`/`readonly` modifier stops firing because a duplicate node overrode it |
| G3 | modifier wrong | a field that should be editable is frozen `readonly`, or an element that should toggle is always-invisible / always-visible |
| G4 | menu / action mis-point | a menu, smart button, or action opens an empty / wrong list, a 404, or the wrong domain / context |
| G5 | OWL white-screen | a blank content area with NO Python traceback - only a browser-console JS error reveals it |
| G6 | view load-fail (kanban / search / pivot / graph / calendar) | the view does not render because its template or a search / group-by / measure / date field references a removed field |
| G7 | ACL block | an AccessError, an empty list, or a hidden field / button for the logged-in role (invisible when the screen is reviewed as admin) |

Scope note: G7 (role-dependent) and any CRUD / state-transition coverage need MULTIPLE roles and write
operations - that is the acceptance tester's scope (`odoo-qa-tester`). A rendered-UI review observes G1-G6
plus whatever G7 effect is visible for the single role it is logged in as, on one screen, without mutating data.

## View-type render checks

Switch to each view the action exposes via the control-panel view switcher (read-only navigation) and confirm
it mounts. The selector proves the view rendered; the success signal proves it is functional; the break column
points at the likely class above.

### Search view (control panel)

| Element | Selector | Render-success signal | Typical break |
|---------|----------|-----------------------|---------------|
| Search box | `.o_searchview`, input `.o_searchview_input` | the bar is visible in the control panel; typing offers an autocomplete dropdown | G6 (a search field references a removed field) |
| Applied facets | `.o_searchview_facet` (`.o_facet_values`) | each active filter / group-by shows as a removable chip | G4 (a default filter targets a wrong / removed field -> empty result) |
| Filters menu | `.o_filter_menu` | "Filters" opens; lists predefined filters + "Add Custom Filter" | G1 (an inherited filter entry is missing) |
| Group By menu | `.o_group_by_menu` | "Group By" opens; choosing a field regroups the records with no console error | G6 (group-by on a removed field) |
| Favorites menu | `.o_favorite_menu` | "Favorites" opens; "Save current search" is present | - |
| Search panel (sidebar) | `.o_search_panel` (`.o_search_panel_category` / `.o_search_panel_filter`) | the left category / filter sidebar renders for views that declare it | G6 / G1 (a panel field was removed) |

Opening these dropdowns and applying a filter is read-only (it only re-queries) - a reviewer may do it to confirm
the controls mount and populate; exhaustive filter / group-by combinations and result-correctness assertions are
the tester's matrix.

### Pivot view

| Element | Selector | Render-success signal | Typical break |
|---------|----------|-----------------------|---------------|
| Container | `.o_pivot` | a table of measure cells renders | G5 (blank), G6 (a measure / group field was removed) |
| Header cells | `.o_pivot_header_cell_closed` / `.o_pivot_header_cell_opened` | clicking +/- expands / collapses a dimension | G5 |
| Measure values | `.o_pivot_cell_value` | numeric values populate; row / column totals reconcile | G6 |

### Graph view

| Element | Selector | Render-success signal | Typical break |
|---------|----------|-----------------------|---------------|
| Renderer | `.o_graph_renderer` containing a `<canvas>` | a chart paints (bar / line / pie) | G5 (empty canvas / JS error) |
| Mode switch | control-panel chart-type buttons | switching bar / line / pie re-renders the canvas | G5 |
| Series | legend / axis labels | the legend reflects the group-by; axes are labelled | G6 (a measure field was removed) |

### Calendar view

| Element | Selector | Render-success signal | Typical break |
|---------|----------|-----------------------|---------------|
| Container | `.o_calendar_view` / `.o_calendar_renderer` (FullCalendar `.fc`) | a day / week / month grid renders with scale toggles | G5 (FullCalendar JS error -> blank) |
| Events | `.fc-event` | records appear as event blocks on their dates | G6 (a `date_start` / `date_stop`-style field was removed -> view fails) |
| Sidebar | `.o_calendar_sidebar` | the mini-calendar + filters render | G1 |

### Activity view

| Element | Selector | Render-success signal | Typical break |
|---------|----------|-----------------------|---------------|
| Container | `.o_activity_view` (table `.o_activity_view_table`) | a grid of records (rows) x activity types (columns) renders | G5, G6 (the model has no `mail.activity` support) |
| Type columns | `.o_activity_type_cell` | one column per activity type, with counters / badges | G6 |
| Schedule cells | `.o_activity_summary_cell` (`.o-mail-ActivityCell-counter`) | per-record activity cells render | G7 (record ACL hides rows) |

## Form internals

On a form view (`.o_form_view`), confirm each internal region mounts. Opening a notebook tab, clicking a smart
button to follow its action, and reading the chatter are read-only navigation; creating / editing / saving
records and firing state-changing statusbar action buttons are NOT - leave those to `odoo-qa-tester`.

| Region | Selector | Render-success signal | Typical break |
|--------|----------|-----------------------|---------------|
| Notebook (tabs) | `.o_notebook`; headers `.o_notebook_headers .nav-link`; pages `.tab-pane` / `.o_notebook_page` | tabs render; clicking a tab switches the active page and its fields render | G1 (an inherited page xpath broke -> page absent / ParseError), G3 (a page `invisible` modifier is wrong), G5 |
| Button-box / smart buttons | `.oe_button_box`; each `.oe_stat_button` with `.o_stat_value` / `.o_stat_info` (count) + `.o_stat_text` (label) | each smart button shows an icon, a non-placeholder count, and opens an action when clicked | G4 (the action was removed -> opens empty / wrong), G2 (a duplicate compute -> wrong count), G5 |
| Chatter | OWL `.o-mail-Chatter` (`.o-mail-ChatterContainer`); legacy `.o_mail_thread` / `.o_chatter`; messages `.o-mail-Message`; composer `.o-mail-Composer`; followers `.o-mail-Followers` | the chatter panel mounts beside / below the form; Send message / Log note / Activities / Followers controls present; existing messages render | G5 (an OWL mail render error -> blank chatter, common after an upgrade), G1 (`mail.thread` inherit / `<chatter/>` not injected), G7 (follower / message ACL) |
| Statusbar | `.o_statusbar_status` (the clickable stage / state pipeline) + `.o_statusbar_buttons` (header action buttons) | the current state is highlighted; reachable states are shown; header buttons render for the current state | G3 (a modifier is wrong -> a button is always / never visible), G4 (a button calls a removed method) |

The chatter DOM moved from the legacy thread widget to the OWL mail store in newer majors - confirm the live
class names with a DOM snapshot rather than assuming. On small screens in newer majors, form header buttons fold
into the gear / Cog menu, so an EMPTY mobile statusbar-button area is EXPECTED, not a defect - do not raise it as
a finding.

## OWL vs legacy by version

| Odoo version | Web client framework | Implication for debugging |
|--------------|----------------------|---------------------------|
| v8-v14 | Legacy `web.Widget` / `odoo.define()` (QWeb2) | Render failures show as missing DOM nodes; check `field_registry` and template names. |
| v15 | OWL 1.x (`patch(Class.prototype, …)`) | Reactivity via `useState`; prototype-level patches. |
| v16+ | OWL 2.x (`patch(Class, …)`, ES modules) | `odoo.define` removed; registries via `registry.category(...)`; class-level patches. Confirmed through v19; verify new majors via OSM. |

A render-then-error symptom and an empty-render symptom have different root causes - confirm which
via a DOM snapshot before attributing the cause to JS.

## Responsive breakpoints

Use a consistent set for review, regression, and recording so captures are comparable:

| Breakpoint | Width (px) | Device class |
|------------|-----------|--------------|
| Mobile | 375 | phone portrait |
| Tablet | 768 | tablet portrait |
| Desktop | 1280 | standard laptop/desktop |
| Wide | 1920 | large monitor (only when the brief asks for it) |

## Session / multi-role storage

For repeatable, deterministic captures and for exercising role-specific UI:

1. Log in once via `/web/login` and persist the browser session (storage state) to a named file,
   e.g. `storageState-admin.json`, `storageState-portal.json` - one per role under the project's
   baseline directory.
2. Re-use the stored state on subsequent navigations instead of logging in each time; this keeps
   screenshots deterministic and avoids login-page noise in diffs.
3. Keep one storage-state file per role (admin, internal user, portal user) so role-specific UI can
   be reviewed without re-authenticating mid-session.

Credential values themselves come from the agreed credential source referenced in
`.odoo-ai/context.md` (`instance_login`) - never hard-code them here.

## Context file keys consumed by the visual skills

All four skills read `.odoo-ai/context.md` (Markdown bullets `- **key**: value`, not YAML):

- `odoo_version` - selects `/odoo` vs `/web` and the framework era above.
- `instance_base_url` - root of the running instance to navigate.
- `instance_login` - login identifier + agreed credential source.
- `screenshot_baseline_dir` - where baselines/evidence screenshots are written; videos default to
  `.odoo-ai/visual/videos/`.
- `brand_tokens_source` - (optional) path to a consumer-declared JSON map `token -> expected color`
  (e.g. `{"--primary": "#1E88E5"}`). When present, `odoo-ui-review` Step 4b ΔE-diffs the resolved
  `getComputedStyle(:root)` brand tokens against it (runtime brand fidelity, `odoo-frontend-fidelity.md`
  Section G). Brand-agnostic - no brand is vendored in the plugin; omit for pure-Odoo projects.
- `mockup_dir` - (optional) directory of reference mockups/design specs for the mockup-first check.

If a *required* key (the first four) is missing, the skill asks the user rather than guessing; the
optional brand/mockup keys simply disable their checks when absent.

## Documentation screenshots (static/description)

Convention for `odoo-doc-illustrator` when writing module visual documentation into
`<module>/static/description/`. All paths below are relative to the module root.

### Layout

| Asset | Path | Spec |
|-------|------|------|
| App icon | `static/description/icon.png` | PNG 100x100 (legacy) or 128x128; match the module's existing icon size |
| Store listing HTML | `static/description/index.html` | Pure HTML; image refs use `<img src="./file">` (relative) |
| Banner screenshot | `static/description/main_screenshot.png` | 1280x600 |
| Localised banner GIF | `static/description/main_screenshot.<locale>.gif` | 1280x600; one file per locale |
| Feature screenshot | `static/description/<N>-<slug>.<locale>.jpg` | ~1800px target, >=1200x800 floor; `N` = two-digit ordering prefix |

Manifest key: `'images': ['static/description/main_screenshot.png']`.

### Writing screenshots from the agent

SSOT for the screenshot write mechanism (allowed-roots constraint + 2-tier relative-filename ->
`.playwright-mcp` -> Bash cp staging): see `agents/odoo-doc-illustrator.md` (Critical path
constraint section). Do not duplicate that mechanism here - follow the agent SSOT.

### UC2 - cluster / docs-repo output

When `doc_output_dir` is set in `.odoo-ai/context.md` (MODE cluster), images go to that
directory instead of `static/description/`. RST references use `.. image:: <filename>.png`
(no path prefix when the image is in the same docs dir as the `.rst` file).
