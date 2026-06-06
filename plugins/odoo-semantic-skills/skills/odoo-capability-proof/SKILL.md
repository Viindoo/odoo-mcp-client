---
name: odoo-capability-proof
description: >
  Assemble an evidence-backed proof package that Odoo can fulfill a specific client
  requirement — citing real module names, model fields, and code snippets from the indexed
  codebase, not marketing claims. Use this skill ANY time a sales engineer, consultant, or
  account manager needs to convince a skeptical client/prospect that "yes, Odoo really does
  this — here's the proof". Fire on "prove Odoo can do X", "feature evidence for customer
  requirement Y", "customer asks does Odoo support X — I need to show the code", "client
  doesn't believe Odoo handles Z — build the evidence", "RFP response — back up every yes
  with module + code". Trigger especially on deadline signals ("for the demo", "before
  Friday", "in the RFP") — user needs real artifacts fast. Also fires on Vietnamese:
  "chứng minh Odoo làm được X cho khách". When the user only wants a yes/no
  answer on availability (no proof package needed), route to odoo-feature-check. When they're
  scoping MANY requirements at once for a quote, route to odoo-gap-analysis
---

## Persona
Sales Engineer / Pre-sales Consultant

## Out of Scope

- Single feature availability (no proof needed) → use `odoo-feature-check`
- Multi-requirement scope + effort quote → use `odoo-gap-analysis`
- Customer-facing objection response paragraph → use `odoo-objection-handler`
- A REAL recorded video/screencast of the flow (not text/code evidence) → use `odoo-demo-recorder`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across many versions (v8-v19) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, WITHOUT a local checkout or a running instance. Unique signature: cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
> - Files already in your own working tree - if the exact version is checked out locally and you want one file, your own file-read/grep tools are faster and authoritative for that checkout; use Odoo Semantic for cross-version / inheritance-resolved / whole-graph questions or when the code is not checked out.
> - Free-text or web documentation - Odoo Semantic returns structured graph facts, not prose; use a docs or web-search tool.
>
> Name the kind of truth you need: CODE/STRUCTURE that is cross-version + inheritance-resolved + needs no checkout -> use Odoo Semantic. LIVE DATA from a running instance -> use a live Odoo MCP server. One file from a checkout you already have -> use your own file tools.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
<!-- END GENERATED TOOLS -->

## Context

Clients are skeptical of ERP vendors' marketing claims. The most effective counter is showing real
code from the indexed codebase — specific module names, model fields, and code snippets that
demonstrate the capability exists and is used in production.

Support any supported Odoo version. When referencing old versions (v8/v9):
- Modules were under `addons/` of the OpenERP repository
- Field declarations used `_columns` dict, not class-level attributes
- The model API was `osv.osv`, not `models.Model`
Mention version if the client is on an older release.

Capability verdicts:
- **Supported natively** — standard module, zero customization
- **Supported with configuration** — standard module, requires setup (e.g. enable feature flag)
- **Supported with light customization** — standard extension point exists, <3 days dev
- **Requires custom development** — no standard module; state honestly with effort estimate

## Instructions

Use parallel MCP calls to build the evidence package quickly.

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` simultaneously.
`find_examples` takes a semantic query derived directly from the requirement text — it does not
need the module name from `check_module_exists`. Both can fire at the same time.

**Round 2 — Parallel (if module found):** Call `model_inspect(model=…, method='fields')` +
`entity_lookup(kind='method', model=…, method_name=…)` +
`module_inspect(name=<module>, method='summary', odoo_version='auto')` simultaneously. `model_inspect` shows
exact fields; `entity_lookup` shows the override chain for method-level requirements; `module_inspect` adds
module-architecture scope (N models defined/extended, N views) — a proof package that says "this module ships
6 models and 12 views around the capability" is far more compelling to a skeptical client than a single field.
If the model name is already known from training knowledge, include these in Round 1.

Never fabricate capabilities. If the feature doesn't exist, say so and propose the most credible
workaround. When MCP results conflict with training knowledge (e.g. a module that training data
says should exist but `check_module_exists` doesn't find), trust the MCP result — it reflects
the actual indexed codebase.

## Standalone-first fallback

The requirement is already in the invocation - do not ask the caller to re-provide it.
If the caller mentioned a document path (proposal, RFP excerpt), `Read` it directly.

When OSM is unreachable, follow the three-tier grounding order from
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2 - self-serve first:**
   - `WebFetch` the relevant GitHub source for the target version, e.g.
     `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/<file>.py`,
     to pull real field lists and method signatures as code evidence.
   - Use local `Read`/`Grep` on a local source tree when present.
   - Label any artifact built this way `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 - only if all Tier-2 fetches fail:** produce the evidence package from
   training knowledge and prepend `OSM unavailable - ungrounded` with caveat "not yet
   verified against the codebase index; double-check code details when OSM is back
   online". Do not ask the caller for any input that can be fetched from public sources.

## Output format

```
## Capability Proof: <requirement>

**Verdict:** Supported natively / Supported with configuration / Supported with light customization / Requires custom development
**Odoo version:** <version>
**Edition:** CE / EE / Custom distribution

### Summary
<2–3 sentences confirming capability and how it's implemented>

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

## Examples

**Example 1:**
Prompt: "prove Odoo can handle multi-currency invoicing for our prospect"
Output: Verdict "Supported natively", evidence table citing `account.move` fields (`currency_id`,
`amount_currency`, `currency_rate`) from `model_inspect(model='account.move', method='fields', odoo_version='auto')`, a
real code example, and demo steps.

**Example 2:**
Prompt: "prove Odoo 17 supports multi-level approval for purchase orders"
Output: Verdict with `purchase_stock` + `purchase` module evidence,
`entity_lookup(kind='method', model='purchase.order', method_name='button_approve', odoo_version='auto')` override
chain, and demo steps.

## Notes / Integration

- This skill produces TEXT/code evidence and written demo steps — not a video. To turn the
  written demo steps above into a REAL screencast running on a live instance, hand them to
  `odoo-demo-recorder` (which drives the instance through the same steps and saves an MP4/GIF).
  Mention this as an optional next step; do not invoke it from here (depth rule).
