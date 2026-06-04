---
name: odoo-feature-check
description: >
  Answer "does standard Odoo already do this?" with evidence — module name, edition (CE / EE),
  key fields/models, and a one-line verdict ready for a client email. Version-aware: uses MCP
  check_module_exists/find_examples; confirm version when unspecified. Fire before answering
  from memory — training data about Odoo modules drifts fast.
  Trigger on: "does Odoo have…", "is X available out of the box?", "do we need to build this
  or is it already there?", "what edition do I need for Z?".
  Also fires on Vietnamese: "Odoo có sẵn tính năng này không", "cần code thêm hay đã có sẵn",
  "cần bản CE hay EE cho Z".
  Use this when the user is asking about ONE feature/module; when they list MANY requirements
  at once route to odoo-gap-analysis instead. When they want to see real source-code examples
  of X being used, route to odoo-feature-highlights or odoo-capability-proof
---

## Persona
Consultant / Developer

## Out of Scope

- Multi-requirement effort matrix → use `odoo-gap-analysis`
- CE vs EE three-way comparison → use `odoo-addon-diff`
- Customer-facing objection response → use `odoo-objection-handler`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Standard Odoo coverage exists at three levels:
1. **CE native** — free, zero customization needed
2. **Odoo EE only** — requires paid Odoo Enterprise subscription
3. **Community App Store** — third-party OCA modules (note: not officially supported)

Version matters — a feature in v17 may not exist in v12. Always ask or infer the target version.

For v8/v9 (OpenERP era): module names and features differ significantly. The `sale` module in v8
has a very different field set than v16. When checking features for legacy versions, note that
many "new" features in v12+ didn't exist at all in v8/v9.

**Data priority:** When `check_module_exists` result conflicts with training knowledge about
whether a feature exists, trust the MCP result. MCP reflects the indexed codebase; training
data about specific Odoo module names and versions is frequently outdated.

## Instructions

**Round 0 — Pin the version (once):** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` simultaneously.
`find_examples` takes a semantic query from the requirement text and does not need the
module check result. Both are independent — fire together.

**Round 2 — Parallel (after Round 1):** Call `model_inspect(model=…, method='fields')` (needs
module/model name from Round 1) + `suggest_pattern` simultaneously. `suggest_pattern` can
be formulated from the requirement even if Round 1 shows partial coverage — they are
independent of each other.

**Round 3 — Deep dive (when `check_module_exists` confirms presence):** Call
`module_inspect(name=<name>, method='summary', odoo_version='auto')` to surface the module's full
architecture: manifest summary, which models it defines vs extends, view count, and JS patch
count. This gives the consultant a confident, evidence-backed answer about what the module
actually covers — beyond the bare "exists / does not exist" signal. If the module is confirmed
to exist, also consider drilling into specifics with `module_inspect(method='fields', odoo_version='auto')` or
`module_inspect(method='views', odoo_version='auto')` in a subsequent call if the client asks about exact field
or view coverage.

**Verdict levels:**
- `Available in CE` — standard, zero cost
- `Available in Odoo EE only` — requires Enterprise subscription
- `Partial — standard covers X, custom needed for Y` — specify the gap precisely
- `Not available — custom development required` — honest assessment with effort note

Always cite the exact module name so clients can verify independently.

## Standalone-first fallback

When OSM is unreachable (server down or network), ask the user to paste the module manifest content and 1-2 model file snippets from the module in question. The skill will still produce a verdict (available / unavailable, edition CE/EE) based on text analysis of the paste, with a caveat that verification via the semantic index is pending once the server is back online.

## Output format

```
## Feature Availability Check

**Feature requested:** <feature description>
**Odoo version:** <version>

| Feature aspect | CE | Odoo EE | Module | Notes |
|---------------|:--:|:-------:|--------|-------|
| ...           | ✓/✗ | ✓/✗ | ...  | ...   |

### Verdict
**<Available in CE / Available in EE only / Partial / Not available>**

### Evidence
- **Module:** `<module_name>`
- **Primary model:** `<model_name>`
- **Module scope:** <N> models defined, <N> models extended, <N> views, <N> JS patches (from module_inspect describe)
- **Key fields:** `<field1>`, `<field2>` — <what they implement>
- **Example:** <brief description from find_examples>

### Custom development needed (if partial)
- **Gap:** <what standard doesn't cover>
- **Extension pattern:** <from suggest_pattern>
- **Estimated effort:** <S/M/L>

### Recommendation
<1–2 sentences for the client>
```

## Examples

**Example 1:**
Prompt: "does Odoo have a subscription billing module built in?"
Output: Feature table showing `sale_subscription` exists in EE only (not CE), key model
`sale.order` with `subscription_id` field, verdict "Available in Odoo EE only".

**Example 2:**
Prompt: "Does Odoo have a fixed asset management module?"
Output: `account_asset` exists in EE, not CE.
`model_inspect(model='account.asset', method='fields', odoo_version='auto')` shows key fields. Recommendation
provided.
