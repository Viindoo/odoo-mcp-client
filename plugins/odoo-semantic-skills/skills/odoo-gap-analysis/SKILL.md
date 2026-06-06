---
name: odoo-gap-analysis
description: >
  Produce a gap analysis comparing client requirements against Odoo standard
  functionality, ending in a concrete effort matrix (Standard / Configuration / Extension /
  Custom + S/M/L/XL day estimates), ready for a proposal or downstream skills. Use this skill ANY time
  someone is about to quote, scope, or estimate an Odoo project — even if they don't say
  "gap". Fire when the conversation contains a list of customer requirements + any hint of
  "what does Odoo do natively?" / "what needs to be built?" / "how many days?" / "what
  should we charge?" — catch phrases like "is this standard Odoo or do we need to build it?",
  "list of features → effort matrix", "RFP mentions 23 requirements — classify them".
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
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Gap analysis is the most important consulting deliverable — it sets client expectations and
determines project budget. Errors in either direction are costly:
- Under-estimating gaps → budget overruns, unhappy clients
- Over-estimating gaps → losing deals, recommending custom dev for standard features

**Effort classification:**
- **Standard** — exists in CE or EE, zero development needed. Mention if EE license required.
- **Configuration** — standard module exists but requires setup (multi-company, tax config,
  workflow rules). < 1 day effort.
- **Extension** — existing model/method can be extended with `_inherit`. Standard ORM extension
  patterns apply. 1–5 days per requirement.
- **Custom** — no standard module; requires new model, complex logic, or integration.
  5+ days per requirement.


**Version matters:** A feature classified "Custom" on v12 may be "Standard" on v16. Always note
the target version. For v8/v9 migrations, effort is higher — Python 2 syntax, `_columns` dict,
`osv.osv` all need full rewrites.

**Data priority:** MCP tool results are ground truth for Standard vs Custom classification.
If `check_module_exists` says a module doesn't exist but training knowledge says it should,
trust the MCP result. Use training knowledge only for effort estimation and business context.

## Instructions

Use parallel MCP calls to minimize latency — a gap analysis covering 10+ requirements can
complete in 3 rounds instead of 30+ sequential calls.

**Round 0 - Context bootstrap + pin:** Before asking the caller for any project fact,
follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`: read `.odoo-ai/context.md`
if present and extract `odoo_version` and `viindoo_profile` (never hard-code
`viindoo_internal_17`). Use those values for `set_active_version(odoo_version=…)` and
`set_active_profile(profile_name=…)`. If `.odoo-ai/context.md` is absent, derive version
from manifests on disk per the context-bootstrap snippet before asking.

The requirement list is already present in the invocation context - proceed with
classification directly; do not ask the user to re-provide requirements that were stated
in the original request.

**Round 1 — Parallel:** Call `check_module_exists` for ALL requirements simultaneously.
Each call is independent; there is no reason to wait for one before firing the next.

**Round 2 — Parallel:** For all requirements where coverage is partial (module exists but
incomplete), call `model_inspect(model=…, method='fields')` on each relevant model
simultaneously. One call returns fields + methods + views + inheritance chain. Pair it with
`module_inspect(name=<module>, method='summary', odoo_version='auto')` for the same modules: the
module-level view/OWL/JS inventory is what separates **Configuration** (the module already ships the
needed view/flow) from **Extension** (the view/field is absent and must be added) — a distinction the
field list alone cannot make.

**Round 3 — Parallel:** For all Extension/Custom gap items, call `find_examples` +
`lookup_core_api` + `suggest_pattern` simultaneously — one batch for all remaining gaps at
once.

Decision logic per requirement (applied after Round 1 results arrive):
- Full module match → mark Standard or Config; no further calls needed
- Partial coverage → escalate to Round 2 model_inspect
- No match → mark Custom; queue for Round 3 suggest_pattern + lookup_core_api

**Be conservative**: if in doubt, upgrade the effort tier. It's easier to reduce scope than
explain overruns.

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding protocol defined in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. The requirement list is
already in the invocation context - proceed immediately without asking the user to
re-provide it. Classify each requirement as Standard/Config/Extension/Custom based on
Odoo training knowledge (Tier 3) and include a caveat: "Classification not yet verified
against code examples; double-check effort estimates once OSM is online."

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

**Effort legend:** S = <1d · M = 1–3d · L = 3–10d · XL = >10d

### Effort summary
- **Standard** (no dev): <N> requirements — <list>
- **Configuration only**: <N> requirements — <list>
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
