# odoo-solution-design - `return_to` payload mapping (caller-return flow)

Load this only when a caller (e.g. `odoo-forward-port`) invokes `odoo-solution-design` with
`return_to` set - it maps the caller's payload onto the P1 architect dispatch template. The
default (no `return_to`) path never needs this.

When this skill is invoked by a caller that supplied `return_to` in its inputs (e.g.
`odoo-forward-port` routing a bucket-(c) module here), map the caller's payload onto the
dispatch template as follows - do NOT improvise or drop any field:

| Caller input | Architect template field | How to compose |
|---|---|---|
| `target_version` | `REQUEST` preamble + `set_active_version` | Write "Target Odoo version: <target_version>" as the first line of `REQUEST` |
| `modules` | `REQUEST` preamble | Write "Modules: <names>" as the second line of `REQUEST` |
| `classification` | `REQUEST` body | Paste the bucket-(c) summary verbatim as the core requirement description in `REQUEST` |
| `intent_records` | `REQUEST` body | Write "Intent records (read these FIRST for the OSM-grounded behavioral contract): <paths>" as a dedicated line in `REQUEST`; the architect MUST Read each path before designing - this is the behavioral contract the forward-port must preserve |
| `design_slug_hint` | `DESIGN_SLUG_HINT` line | Copy verbatim; the architect uses it as `<slug>` when naming `<SHARE_DIR>/designs/<slug>-<date>.md` (resolve `<SHARE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit) |
| `return_to` | `RETURN_TO` line | Copy verbatim; routes the architect's Continuation Contract back to the caller |

The assembled `REQUEST` therefore reads:
```
REQUEST: Target Odoo version: <target_version>
Modules: <module names>
Intent records (read these FIRST for the OSM-grounded behavioral contract): <intent_records paths>
<classification - bucket-(c) summary>
```

Never flatten `intent_records` into the classification summary or omit it - it carries the
behavioral contract the design must honour, distinct from the structural classification.
