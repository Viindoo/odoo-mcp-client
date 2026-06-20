---
name: odoo-gap-analysis
description: >
  Produce a gap analysis comparing client requirements against Odoo standard
  functionality, ending in a concrete effort matrix (Standard / Configuration / Extension /
  Custom + S/M/L/XL day estimates), ready for a proposal or downstream skills. Use this skill ANY time
  someone is about to quote, scope, or estimate an Odoo project - even if they don't say
  "gap". Fire when the conversation contains a list of customer requirements + any hint of
  "what does Odoo do natively?" / "what needs to be built?" / "how many days?" / "what
  should we charge?" - catch phrases like "is this standard Odoo or do we need to build it?",
  "list of features → effort matrix", "RFP mentions 23 requirements - classify them".
  Also fires on Vietnamese: "phân tích gap", "cái này Odoo có sẵn hay phải build thêm",
  "ước lượng bao nhiêu ngày công", "ma trận effort cho báo giá". When
  the user asks about ONE specific feature route to odoo-feature-check instead. When they
  want highlights for marketing copy route to odoo-feature-highlights
---

## Persona
Consultant / Project Manager

## Out of Scope

- Single feature availability check → use `odoo-feature-check`
- Marketing highlights for version release → use `odoo-feature-highlights`
- Source-level API diff between versions → use `odoo-version-diff`

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
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Gap analysis sets client expectations and determines budget. Errors in either direction are costly (under = overruns; over = lost deals).

**Effort classification:**
| Type | Definition | Effort |
|---|---|---|
| Standard | Exists in CE or EE; zero dev | 0 (note if EE license needed) |
| Configuration | Module exists; needs setup | <1 day |
| Extension | `_inherit` extension pattern | 1-5 days/req |
| Custom | New model, complex logic, or integration | 5+ days/req |

Version matters: "Custom" on v12 may be "Standard" on v16. v8/v9 migrations cost more (Python 2, `_columns`, `osv.osv`). **Data priority:** MCP over training knowledge - trust `check_module_exists` results.

## Instructions

Use parallel MCP calls - 10+ requirements can complete in 3 rounds vs 30+ sequential.

**Round 0 - Bootstrap + pin:** Follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`. Read `.odoo-ai/context.md`; extract `odoo_version` and `viindoo_profile` (never hard-code `standard_viindoo_17`). Derive version from manifests on disk if file absent. Requirement list is already in context - do not ask the user to re-provide it.

**Round 1 - Parallel:** `check_module_exists` for ALL requirements simultaneously.

**Round 2 - Parallel (partial matches):** `model_inspect(model=…, method='fields')` + `module_inspect(name=<module>, method='summary', odoo_version='<version>')` for all partial-coverage modules simultaneously. The module-level view/OWL/JS inventory is what distinguishes **Configuration** (module ships the needed view/flow) from **Extension** (view/field absent).

**Round 3 - Parallel (Extension/Custom gaps):** `find_examples` + `lookup_core_api` + `suggest_pattern` in one batch for all remaining gaps.

Decision logic per requirement:
- Full match → Standard/Config; no further calls
- Partial → Round 2
- No match → Custom; queue for Round 3

**Be conservative**: upgrade effort tier when in doubt.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Proceed immediately - requirement list is in context. Classify from training knowledge (Tier 3) and note: "Classification not yet verified against code examples; double-check estimates once OSM is online."

## Output format

```
## Gap Analysis Report

**Client:** <client name or "Client">
**Target Odoo version:** <version>
**Requirements analyzed:** <N>
**Analysis date:** <date>

| # | Requirement | Standard coverage | Module | Effort type | Effort | Notes |
|---|-------------|------------------|--------|-------------|--------|-------|
| 1 | ...         | Full/Partial/None | ...   | Standard/Config/Extension/Custom | S/M/L/XL | ... |

**Effort legend:** S = <1d · M = 1-3d · L = 3-10d · XL = >10d

### Effort summary
- **Standard** (no dev): <N> requirements - <list>
- **Configuration only**: <N> requirements - <list>
- **Extension** (custom field/method): <N> requirements
- **Full custom development**: <N> requirements

### Total estimated effort
**<Low/Medium/High/Very High>**

<Rationale paragraph: what drives the total, which items have highest uncertainty>

### Risk flags
- <Item at risk of scope creep or hidden complexity>

### Recommended phasing
Phase 1 (must-have): ...
Phase 2 (nice-to-have): ...
```

## Examples

**Example 1:**
Prompt: "gap analysis for a client who needs multi-company invoicing, approval workflows, and a
custom loyalty program"
Output: Multi-company invoicing → Standard (CE) S; Approval workflows → Extension M (using
`mail.activity.mixin`); Custom loyalty → Custom XL. Total effort: Medium. Suggested phasing.

**Example 2:**
Prompt: "Gap analysis for a manufacturing client: needs MRP, batch production planning, and CNC
machine integration via IoT"
Output: MRP → Standard CE; Batch production planning → Standard CE (lot/serial tracking); CNC
IoT integration → Custom XL (EE IoT module exists but custom adapter required). Total effort:
High.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
