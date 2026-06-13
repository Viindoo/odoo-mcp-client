---
name: odoo-risk-overview
description: >
  Produce an executive-level Odoo risk dashboard — quantifying upgrade risk (deprecated API
  counts), change blast radius (how widely a field/method is depended on), and dependency
  health — into a one-page summary a CEO or CTO can act on, scoped to the active tenant
  profile + target version (confirm both if unstated). Use ANY time a manager, sponsor, or
  executive asks about Odoo system health, upgrade readiness, or "how risky is it to change
  X?". Pushy trigger: "give me a risk overview", "what's the upgrade risk", "is it safe to
  upgrade", "blast radius if we deprecate field X", "technical debt — give me numbers".
  Also fires on Vietnamese: "rủi ro nâng cấp", "nâng cấp có an toàn không".
  Trigger especially on a deadline or decision context ("board meeting", "before we commit
  budget", "RFP due"). When the user wants a per-line technical audit of deprecated APIs (not
  an executive summary), route to odoo-deprecation-audit. When they want module-by-module
  business inventory, route to odoo-customization-inventory
---

## Persona
CEO / CTO / Project Sponsor

## Out of Scope

- Per-line deprecated API technical audit → use `odoo-deprecation-audit`
- Module-by-module business inventory → use `odoo-customization-inventory`
- Tactical override/extension guidance → use `odoo-override-finding`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_deprecated_usage` — Scan the indexed codebase for usages of deprecated API patterns.
- `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Context

Executives need a high-signal risk picture without reading code. The risk picture has three
dimensions:
1. **Upgrade risk** — how many deprecated APIs will break when upgrading to a newer version
2. **Change blast radius** — how many places in the system are affected when a key field/model
   is modified
3. **Dependency health** — whether custom modules depend on third-party or platform-specific
   features that may disappear

**Risk levels:**
- **Low** — 0–2 deprecated APIs, no high-impact fields, all dependencies stable
- **Medium** — 3–10 deprecated APIs, or 1–2 high-impact fields, manageable migration
- **High** — 10+ deprecated APIs, or critical business field with wide blast radius, requires
  dedicated migration project

**Version era multiplier:** Migrating across era boundaries amplifies risk:
- Within same era (e.g. v16→v17): Low multiplier
- Cross-era (e.g. v12→v16, crosses v13 `@api.multi` removal + v14 OWL-becomes-primary migration): Medium multiplier
- OpenERP to modern (v8/v9→v12+): Very High multiplier (Python 2→3, full rewrite required)

Distribution note: Modules with consistent naming patterns (e.g., `viin_*` prefix or similar)
indicate distribution-maintained code. Risk for distribution-maintained modules is generally
lower than truly custom modules — flag them separately.

**Data priority:** MCP tool results are ground truth for deprecated API counts and blast radius.
Use training knowledge for interpreting business impact and recommending remediation approaches.

## Instructions

Use parallel MCP calls — steps 1, 2, and 3 are fully independent. Fire them simultaneously.

**Round 0 — Pin version + profile + enumerate scope:** `set_active_version(...)` + `set_active_profile(...)`,
then `profile_inspect(method='modules', name=<profile>, odoo_version='<version>')` to auto-enumerate the in-scope
modules from the index instead of relying on the user to list which modules are in scope.

**Round 1 — Parallel:** Call `find_deprecated_usage` + `impact_analysis` (on highest-usage
custom fields known from context) + `check_module_exists` (for all custom module dependencies)
all at once. None of these depend on each other's results.

**Round 2 — Parallel:** Call `model_inspect(model=…, method='fields')` on the most heavily
customized models identified from Round 1 results. Simultaneously call
`module_inspect(name=<name>, method='summary', odoo_version='<version>')` for each custom module in scope — this
surfaces JS patch counts, view counts, and models defined/extended, which the executive
table needs. Both calls are independent; fire them together. If hotspot models are already
known from context, include `model_inspect` calls in Round 1 as well to reduce to a single
round.

Focus `impact_analysis` on fields referenced by many other modules (high `used_by` count).
Count BREAKING vs WARN severity from `find_deprecated_usage` results.

Synthesize findings into a concise executive table. Keep prose minimal — let the table carry
the data. Always close with a one-sentence recommended action tied to the highest-risk item.

## Standalone-first fallback

When OSM unreachable, follow the three-tier grounding protocol defined in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Specifically:

- **Tier 2 (disk):** Run `find . -maxdepth 3 -name "__manifest__.py"` to discover
  modules, `Read` each manifest for classification clues, and `grep` for deprecated
  patterns (`@api.multi`, `_columns`, `osv.osv`, `web.Widget`) directly in source.
  Build the risk overview from those findings without asking the user to supply them.
- **Tier 3 (training):** If no readable source is available, produce a heuristic
  estimate of deprecated risk (based on module age and naming patterns) and label the
  artifact `OSM unavailable - ungrounded` with caveat "deprecated API + blast radius not
  yet scanned - verify with detailed audit when OSM is online".

## Output format

```
## Odoo Customization Risk Overview

**Assessment date:** <date>
**Current Odoo version:** <version>
**Target upgrade version:** <version or "Not specified">
**Modules assessed:** <N>

| Module | Type | Deprecated APIs | JS patches | Views | High-impact fields | Upgrade risk | Priority |
|--------|------|:---------------:|:----------:|:-----:|:------------------:|:------------:|:--------:|
| ...    | Custom/Distribution | ... | ... | ... | ... | Low/Med/High | 1/2/3 |

### Key findings
- <finding 1 — most important risk with module name>
- <finding 2>
- <finding 3>

### Risk summary by category
- **Upgrade risk (deprecated APIs):** <Low/Med/High> — <N> BREAKING issues across <N> modules
- **Change blast radius:** <Low/Med/High> — <field/method> affects <N> downstream points
- **Dependency health:** <Low/Med/High> — <N> dependencies unverified in target version

### Version migration complexity
<Low/Medium/High/Very High> — <rationale based on era and version gap>

### Recommended action
<One concrete, specific sentence: "Prioritize migration of `module_x` before the v17 upgrade window
because it has N breaking changes in core method Y.">
```

## Examples

**Example 1:**
Prompt: "give me a risk overview of our Odoo customization before we upgrade to v17"
Output: Table of custom modules with deprecated API counts, blast radius for critical fields,
migration complexity note (e.g. from v16 = Low multiplier), recommended action.

**Example 2:**
Prompt: "risk overview before we upgrade our system from version 14 to 17"
Output: Risk analysis for distribution-maintained vs custom modules, identify modules needing
deep migration work (v13 `@api.multi` removal + v14 OWL-becomes-primary + v15 OWL 2.0),
estimate timeline and recommended action in business language.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
