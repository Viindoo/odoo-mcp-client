<!-- SSOT snippet. Turns a change's blast-radius into an actionable verify-scope manifest:
     reverse-closure -> risk rank -> dependent modules + screens -> install/test/render sets.
     Builds ON bidirectional-impact.md (closure mechanics live there - do NOT restate them);
     this snippet adds risk ranking, screen enumeration, and the manifest contract. Referenced
     (not copy-pasted) by odoo-acceptance Phase 0, odoo-code-review Phase A.5, and wave Phase 4.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md. -->

# Acceptance Scope Contract (blast-radius -> verify-scope manifest)

Most QA binds tests and render-checks to the module that was edited. A change in an Odoo
dependency DAG ripples beyond that module - the verify scope is the edited module PLUS its
dependents PLUS every screen that binds a changed symbol. This snippet derives that scope as a
single machine-usable manifest so acceptance covers what actually changed, ranked by risk.

## Step 1 - Compute the closure (mechanics: bidirectional-impact.md)

Run the bidirectional walk per `${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md` (do not
restate it): forward (`module_inspect(method='dependencies', ...)`) to know what the change relies
on, and - the one that grows the verify scope - the REVERSE closure on each changed
model/field/method via `impact_analysis(entity_type=..., entity_name=..., odoo_version=...)`,
walked transitively. The reverse closure is the set of dependent modules/views/reports/overrides
that inherit the changed behavior and can break. OSM is PRIMARY here; fall back to disk
(`__manifest__.py depends` + `grep -rl "_inherit"`) only when OSM is unreachable, and label the
manifest `closure approximate from disk`.

## Step 2 - Rank each node by risk (likelihood x impact)

Do NOT verify every node equally. Score each module/screen in the closure:

- **Likelihood** that the change breaks it - higher when the node directly `super()`s a changed
  method, `xpath`-es a changed view node, depends on a changed stored compute / field type, or
  sits on a changed ACL/`ir.rule`; lower when the link is incidental or far in the transitive ring.
- **Impact** if it breaks - higher for ledger/accounting integrity, tenant/company isolation, a
  state machine that gates downstream documents, money or tax computation, or a primary daily
  screen; lower for cosmetic or rarely-used surfaces.

Assign each node a tier: **High** (likelihood x impact large), **Med**, or **Low**. High = cover
DEEP (full role/CRUD/state/negative matrix, durable tour/HttpCase); Low = SMOKE only (does the
screen render without console/4xx-5xx error). The goal is depth where it matters, not uniform
coverage.

## Step 3 - Enumerate the affected screens

For each in-scope module, list the screens (views/actions/menus) that bind a changed symbol -
these are what a live tester must open:

- A changed field/method that surfaces on a view: `model_inspect(model=<m>, method='views',
  odoo_version=<v>)` and the `impact_analysis` view dependents -> collect the view xmlids.
- A directly changed `xml_view` / OWL / SCSS: the `inherit_id` and record ids it touches.
- Record each as `{module, view_xmlid, view_type (form|list|kanban|search|pivot|graph|calendar|
  activity), risk_tier}`. Empty only when the change is headless (no UI binding).

## Step 4 - Emit the verify-scope manifest

Write the manifest to `.odoo-ai/qa/<slug>-scope.md` (the run's slug). It is the contract the
planner and tester consume; structure it exactly so both can parse it:

```
## Verify scope: <slug>
- odoo_version: <concrete>
- changed_set: [<module|model.field|model.method>, ...]
- grounding: osm | closure approximate from disk

### Dependent modules (reverse closure, ranked)
| module | relation to change | risk_tier |
|--------|--------------------|-----------|
| <name> | super()/xpath/depends/acl/incidental | High|Med|Low |

### Affected screens
| module | view_xmlid | view_type | risk_tier |
|--------|-----------|-----------|-----------|

### Verify sets (derived from the tables above)
- install_set:     [<modules to install together so the cluster loads as deployed>]
- test_set:        [<High/Med modules whose suites + new tours/HttpCase must run>]
- render_check_set:[<every affected screen; High = deep, Low = smoke>]
```

`install_set` is the cluster installed together (co-install surfaces MRO/load-order breaks a
single-module install hides). `test_set` and `render_check_set` are what the durable channel and
the live channel respectively must cover. A manifest that names the dependent modules, the screens,
and the risk tier is gate-able; one that lists only the edited module is the blind spot this
contract closes.
