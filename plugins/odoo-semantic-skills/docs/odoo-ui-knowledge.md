# Odoo UI Knowledge (SSOT for visual skills)

Portable, version-aware reference shared by the visual skills (`odoo-ui-reviewer`,
`odoo-ui-debug`, `odoo-visual-regression`, `odoo-demo-recorder`) and the `odoo-ui-reviewer`
agent. Contains no instance-specific or confidential values — concrete URLs, logins, and
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
version-dependent part.

## OWL vs legacy by version

| Odoo version | Web client framework | Implication for debugging |
|--------------|----------------------|---------------------------|
| v8–v14 | Legacy `web.Widget` / `odoo.define()` (QWeb2) | Render failures show as missing DOM nodes; check `field_registry` and template names. |
| v15 | OWL 1.x (`patch(Class.prototype, …)`) | Reactivity via `useState`; prototype-level patches. |
| v16+ | OWL 2.x (`patch(Class, …)`, ES modules) | `odoo.define` removed; registries via `registry.category(...)`; class-level patches. Confirmed through v19; verify new majors via OSM. |

A render-then-error symptom and an empty-render symptom have different root causes — confirm which
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
   e.g. `storageState-admin.json`, `storageState-portal.json` — one per role under the project's
   baseline directory.
2. Re-use the stored state on subsequent navigations instead of logging in each time; this keeps
   screenshots deterministic and avoids login-page noise in diffs.
3. Keep one storage-state file per role (admin, internal user, portal user) so role-specific UI can
   be reviewed without re-authenticating mid-session.

Credential values themselves come from the agreed credential source referenced in
`.odoo-ai/context.md` (`instance_login`) — never hard-code them here.

## Context file keys consumed by the visual skills

All four skills read `.odoo-ai/context.md` (Markdown bullets `- **key**: value`, not YAML):

- `odoo_version` — selects `/odoo` vs `/web` and the framework era above.
- `instance_base_url` — root of the running instance to navigate.
- `instance_login` — login identifier + agreed credential source.
- `screenshot_baseline_dir` — where baselines/evidence screenshots are written; videos default to
  `.odoo-ai/visual/videos/`.

If any key is missing, the skill asks the user rather than guessing.
