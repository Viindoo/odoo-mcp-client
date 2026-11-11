# odoo-diff-comparator - upgrade absorption findings file

## Upgrade absorption -> `<ISOLATE_DIR>/modules-upgrade/<slug>/absorption/<module>.md`

Propose one class per behaviour (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`):

| Class | Meaning |
|---|---|
| `DELETE-absorbed` | target core provides the behaviour; the custom code goes |
| `OBSOLETE` | the purpose is moot at the target and no named core feature replaces it |
| `KEEP` | genuinely custom, no core equivalent |
| `REWRITE(api)` / `REWRITE(model)` | the logic holds, but the API it uses or the model it touches changed |
| `MERGE` | partly overlaps a new core feature; keep the delta |
| `SPLIT` | bundles several concerns; separate them for the target |
| `RECONCILE` | core writes the same business quantity on the same records, or offers a mechanism that can replace the implementation (step 4); an architectural choice, routed to design |

The module `verdict` is the class every behaviour shares, else `MIXED`; any `RECONCILE` makes it
`RECONCILE` or `MIXED`. `whole_module_absorbed` is true only when every behaviour is
`DELETE-absorbed` by the same core feature, named in `absorbing_core_feature`; never invent one
for `OBSOLETE`. The file header and the return block carry the same three values.

```markdown
# Absorption analysis - <module> (v<source> -> v<target>)

**Mode:** upgrade
**Module:** <module>
**Verdict:** <class | MIXED>
**Whole module absorbed:** true | false
**Absorbing core feature:** <core_module>/<feature> | null
**grounded:** <osm | local-source | ungrounded>

## Feature comparison

| Feature | Custom impl (symbol + path) | Core equivalent at target | Proposed class | Evidence |
|---|---|---|---|---|

## Behavioral equivalence
<required before any DELETE-absorbed or OBSOLETE: per override of the module (create, write, unlink, computes, constraints, onchanges, actions, SQL constraints), whether target core produces the same observable effect. One override with no equivalent means the module is not absorbed>

| Override (symbol @ path) | Core equivalent at target | Same effect? | Notes |
|---|---|---|---|

## Reuse candidates
<RECONCILE behaviours only>

| Feature | Custom impl (symbol @ path) | Target-core mechanism to wire into | Why it replaces or simplifies | Evidence |
|---|---|---|---|---|

## Breaking-change flags
<each symbol the module uses that was removed or renamed between the two series>

## Deferred work
<empty table when the module has no marker>

| File | Line | Marker | Anchored version | Classification | Work item (DUE only) |
|---|---|---|---|---|---|

**due_count:** <n> **unanchored_count:** <n>

## Grounding notes
```
