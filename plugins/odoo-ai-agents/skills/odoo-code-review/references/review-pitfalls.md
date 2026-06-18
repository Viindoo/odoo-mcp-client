# Odoo Code Review - Pitfall Reference

Key failure modes the reviewer checks for:

1. **ORM / N+1** - `search()`, `browse()`, `.read()`, `.mapped()` inside `for rec in self` loops; use `mapped()` or prefetch outside loop.
2. **Inheritance breaks** - missing `super()` in `create`/`write`/`unlink` breaks tracking, compute triggers, and downstream overrides (always CRITICAL).
3. **`@api.depends` errors** - stale or wrong dotted paths; `id` in depends list; constraint on relational field (silently skipped).
4. **Deprecated API** - `@api.multi`, `@api.one` removed in v13/v14; raise at call time, not import.
5. **OWL reactivity** - direct `this.state.items.push()` bypasses OWL reactivity; `position="replace"` in XML views breaks other override chains. Confirm visually on live instance with `odoo-debug`.
6. **Design-system fidelity (SCSS/OWL styling)** - hardcoded `hex`/`rgba` for themeable colors, or surface tokens chained into Bootstrap `--bs-*` custom properties the target version does not emit at runtime (self-referential CSS var cycle). Flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`; confirm at runtime with `odoo-debug`/`odoo-ui-review`, route fix to `odoo-coding`.
7. **Coding-guideline conventions** - after pinning the version, reviewer grounds convention findings against `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/` (naming prefixes, model attribute order, import order, `_()` form) and cites the violated file + section - see `agents/odoo-code-reviewer.md`.
8. **Runtime presence probing** - `hasattr`/`getattr`-default/`try-except AttributeError` to detect a field/method is a smell masking a lookup-gap, wrong ORM path, or missing `depends`; resolve via OSM, classify (3-way), do not defer - see `agents/odoo-code-reviewer.md` and `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`.
9. **Platform design principles** - check against `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md`: company/branch-scoped data missing `company_id` (or `res.branch` on v17+) isolation, country-specific feature built where generic+seed split belongs, `application=True` module lacking standard root/Reports/Configuration menu. Silent deviation = finding; justified = recorded in worklog.
10. **Behavior left unprotected by a test** - CRITICAL/HIGH change to business behavior with no test that would go red if the behavior regressed is itself a HIGH finding. Per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`, route to `odoo-test-writing` rather than waving through.
