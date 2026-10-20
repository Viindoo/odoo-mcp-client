# Major Breaking Points in Odoo History (v8 onward)

| Version jump | Key breaking changes |
|-------------|---------------------|
| v16 → v17 | Python 3.10+ required; performance improvements; several `tools.*` cleanup |
| v17 → v18+ | ORM enhancements; module restructuring (ongoing) |

Frontend breaks (module system, OWL library major, legacy `web.Widget` and legacy-view lifetime) are
owned by `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` rows 1/1b; the `@api.multi` removal
by `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Python ORM - model API; the core package
and descriptor filename by `odoo-era-boundaries.md`; the old-API model style (`osv.osv`, `_columns`,
`pool.get()`) by `odoo-version-pivots.md`; the supported Python range by the series' own checkout.
None is restated here.

> Not exhaustive. Odoo ships a new major roughly yearly; this table captures the historical
> breaking points only. For any target newer than the last row, resolve the real diff via OSM
> (`api_version_diff`) and the release notes rather than assuming.

**Era boundary multipliers for upgrade complexity:**
- Within-era (e.g. v16→v17): Low
- Cross-era (a jump that crosses the `@api.multi` removal or a frontend era change): Medium
- OpenERP to modern (v8/v9→v12+): Very High (Python 2→3, full rewrite required)
