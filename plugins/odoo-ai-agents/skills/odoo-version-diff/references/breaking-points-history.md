# Major Breaking Points in Odoo History (v8 onward)

| Version jump | Key breaking changes |
|-------------|---------------------|
| v8 → v10 | Python 2→3, `__openerp__.py` → `__manifest__.py`, `osv.osv` → `models.Model`, `_columns` → class attributes, `pool.get()` removed |
| v12 → v13 | `@api.multi`, `@api.one` removed; OWL introduced as new JS framework (alongside old `web.Widget` — NOT yet primary) |
| v13 → v14 | OWL becomes primary frontend framework; `web.Widget` deprecated (still present) |
| v14 → v15 | OWL 2.0 migration; many widget APIs changed; `AbstractModel`, `AbstractRenderer` removed |
| v15 → v16 | `web.Widget` removed completely; `fields.Text` with `widget='html'` replaced by `fields.Html`; new `HtmlField` widget; `body_html` field type changes; accounting model restructure |
| v16 → v17 | Python 3.10+ required; performance improvements; several `tools.*` cleanup |
| v17 → v18+ | ORM enhancements; module restructuring (ongoing) |

> Not exhaustive. Odoo ships a new major roughly yearly; this table captures the historical
> breaking points only. For any target newer than the last row, resolve the real diff via OSM
> (`api_version_diff`) and the release notes rather than assuming.

**Era boundary multipliers for migration complexity:**
- Within-era (e.g. v16→v17): Low
- Cross-era (e.g. v12→v16, crosses `@api.multi` removal + OWL-becomes-primary): Medium
- OpenERP to modern (v8/v9→v12+): Very High (Python 2→3, full rewrite required)
