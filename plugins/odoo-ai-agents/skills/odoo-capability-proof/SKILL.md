---
name: odoo-capability-proof
description: >
  Assemble an evidence-backed proof package that Odoo can fulfill a specific client
  requirement - citing real module names, model fields, and code snippets from the indexed
  codebase, not marketing claims. Use this skill ANY time a sales engineer, consultant, or
  account manager needs to convince a skeptical client/prospect that "yes, Odoo really does
  this - here's the proof". Fire on "prove Odoo can do X", "feature evidence for customer
  requirement Y", "customer asks does Odoo support X - I need to show the code", "client
  doesn't believe Odoo handles Z - build the evidence", "RFP response - back up every yes
  with module + code". Trigger especially on deadline signals ("for the demo", "before
  Friday", "in the RFP") - user needs real artifacts fast. Also fires on Vietnamese:
  "chứng minh Odoo làm được X cho khách". When the user only wants a yes/no
  answer on availability (no proof package needed), route to odoo-feature-check. When they're
  scoping MANY requirements at once for a quote, route to odoo-gap-analysis
---

## Persona
Sales Engineer / Pre-sales Consultant

## Out of Scope

- Single feature availability (no proof needed) → `odoo-feature-check`
- Multi-requirement scope + effort quote → `odoo-gap-analysis`
- Customer-facing objection response paragraph → `odoo-objection-handling`
- Real recorded video/screencast → `odoo-demo-recording`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

## Context

Clients are skeptical of ERP vendor marketing claims. The most effective counter is real code from the indexed codebase - specific module names, model fields, and code snippets that demonstrate the capability exists and is used in production.

Support any supported Odoo version. For old versions (v8/v9): modules were under `addons/` of the OpenERP repository; field declarations used `_columns` dict; model API was `osv.osv`. Mention version if the client is on an older release.

**Capability verdicts:**
- **Supported natively** - standard module, zero customization
- **Supported with configuration** - standard module, requires setup
- **Supported with light customization** - standard extension point exists, <3 days dev
- **Requires custom development** - no standard module; state honestly with effort estimate

## Instructions

Use parallel MCP calls to build the evidence package quickly.

**Round 0 - Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 - Parallel:** Call `check_module_exists` + `find_examples` simultaneously. `find_examples` takes a semantic query derived directly from the requirement text - it does not need the module name from `check_module_exists`. Both can fire at the same time.

**Round 2 - Parallel (if module found):** Call `model_inspect(model=…, method='fields')` + `entity_lookup(kind='method', model=…, method_name=…)` + `module_inspect(name=<module>, method='summary', odoo_version='<version>')` simultaneously. `model_inspect` shows exact fields; `entity_lookup` shows the override chain for method-level requirements; `module_inspect` adds module-architecture scope (N models/views) - a proof package saying "this module ships 6 models and 12 views" is far more compelling to a skeptical client than a single field name. If model name is already known from training knowledge, include these in Round 1.

**Never fabricate capabilities.** If the feature doesn't exist, say so and propose the most credible workaround. When MCP results conflict with training knowledge, trust the MCP result.

## Standalone-first fallback

The requirement is already in the invocation - do not ask the caller to re-provide it. If the caller mentioned a document path, `Read` it directly.

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:
- **Tier 2:** `WebFetch` the relevant GitHub source for the target version (e.g. `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/<file>.py`) to pull real field lists and method signatures. Use local `Read`/`Grep` on a local source tree when present. Label artifacts `grounded: local-source (not OSM-indexed)`.
- **Tier 3:** Produce the evidence package from training knowledge, prepend `OSM unavailable - ungrounded`, add caveat "not yet verified against the codebase index; double-check code details when OSM is back online".

## Output format

```
## Capability Proof: <requirement>

**Verdict:** Supported natively / Supported with configuration / Supported with light customization / Requires custom development
**Odoo version:** <version>
**Edition:** CE / EE / Custom distribution

### Summary
<2-3 sentences confirming capability and how it's implemented>

### Evidence
| Module | Model | Key fields/methods | Code reference |
|--------|-------|--------------------|----------------|
| ...    | ...   | ...                | ...            |

### Demo steps
1. <step>
2. <step>
3. <step>

### Evidence details (for technical review)
```python
<code snippet from find_examples>
```

### Honest limitations
<Only if applicable: what this implementation does NOT cover>
```

**Worked examples:** `${CLAUDE_PLUGIN_ROOT}/skills/odoo-capability-proof/references/examples.md`

## Notes / Integration

This skill produces TEXT/code evidence and written demo steps - not a video. To turn the written demo steps into a real screencast on a live instance, hand them to `odoo-demo-recording`. Mention this as an optional next step; do not invoke it from here (depth rule).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
