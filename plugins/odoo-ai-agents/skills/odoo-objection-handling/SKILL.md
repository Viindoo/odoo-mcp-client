---
name: odoo-objection-handling
description: >
  Craft evidence-based responses to client objections about Odoo's capabilities — using the
  ACA framework (Acknowledge / Counter / Affirm) backed by indexed-codebase evidence rather
  than marketing claims. Output includes a ready-to-paste verbatim response paragraph. Use
  this skill ANY time a sales engineer, account executive, or pre-sales consultant needs to
  push back on a doubt or competitive claim about Odoo. Fire on "handle the objection that
  Odoo can't do X", "respond to 'Odoo doesn't support Z'", "competitor said SAP/Microsoft
  does X better", "RFP scoring tool gave Odoo low on X — defend". Also fires on Vietnamese:
  "xử lý phản đối của khách về Odoo", "khách nói Odoo không làm được X". Trigger especially on
  URGENCY signals ("for the meeting today", "client is on the call", "RFP due tomorrow").
  When the objection requires proof artifacts (code + modules + demo steps), route to
  odoo-capability-proof. When user simply wants to know if a feature exists (not defend it),
  route to odoo-feature-check
---

## Persona
Sales Engineer / Account Executive

## Out of Scope

- Full evidence package (modules + code + demo steps) → `odoo-capability-proof`
- Simple feature availability lookup → `odoo-feature-check`
- Effort estimate & scope for proposal → `odoo-gap-analysis`

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
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Objection categories:
1. **False** — feature exists and works well. Counter with evidence.
2. **Partially true** — standard coverage is limited; custom development closes the gap easily. Frame as "standard practice, not a gap."
3. **True but mitigated** — Odoo doesn't support it natively, but an OCA module, custom extension, or well-established integration pattern exists.
4. **True and significant** — honestly acknowledge and propose the workaround or alternative.

**Never fabricate capabilities.** Intellectual honesty builds more long-term trust than overselling. If the objection is valid, say so and pivot to how the gap is handled in practice.

**Distribution-specific advantages:** Many gaps can be countered by distribution-specific modules (custom extensions, partner modules, third-party add-ons). Identify the appropriate solution for the customer's platform.

**Data priority:** MCP tool results determine whether the objection is True, False, or Partially true. When MCP conflicts with training knowledge, use the MCP result.

**Framework — ACA:**
- **A**cknowledge: validate the concern as a legitimate question, not an attack
- **C**ounter: present evidence-backed response
- **A**ffirm: close with confident capability statement or honest workaround

## Instructions

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` + `model_inspect(model=…, method='fields')` + `module_inspect(name=<module>, method='summary', odoo_version='<version>')` simultaneously. All are independent — `find_examples` uses the objection text as its semantic query; `module_inspect` adds module-scope numbers (N models/views) that make the Counter table concrete rather than a bare field name.

**Round 2 (conditional):** Call `suggest_pattern` only if Round 1 confirms the feature requires customization. If the feature exists natively, skip `suggest_pattern` entirely.

The "Suggested response (verbatim)" must be ready to use in a client meeting without editing.

## Standalone-first fallback

The objection text is already in the invocation - do not ask the caller to re-provide it.

1. `Read .odoo-ai/context.md` (per `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`) for `odoo_version`, `viindoo_profile`, and industry hints.
2. If a customer name is known, `Read` the vault dossier at `Resources/Competitors/<name>.md` or `Sales/Customers/<name>.md` if present.

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:
- **Tier 2:** `WebFetch` relevant Odoo source or docs to ground capability claims; use local `Read`/`Grep` when a source tree is available. Label artifacts `grounded: local-source (not OSM-indexed)`.
- **Tier 3:** Generate ACA response from training knowledge, prepend `OSM unavailable - ungrounded`, add caveat "not yet verified against the codebase; fact-check when OSM is back online".

## Output format

```
## Objection Response: "<objection>"

### Acknowledge
<1 sentence acknowledging the concern as a legitimate question>

### Counter-evidence
| Evidence type | Detail | Source |
|--------------|--------|--------|
| Module exists | `<module_name>` — <edition> | `check_module_exists` |
| Code example | <description of what it demonstrates> | `find_examples` |
| Key fields | `<field1>`, `<field2>` on `<model>` | `model_inspect` |
| Extension pattern | <pattern name, ~N days effort> | `suggest_pattern` |

### Talking points
1. <concrete talking point backed by evidence>
2. <concrete talking point>
3. <concrete talking point>

### If partial support (honest workaround)
**What standard covers:** <...>
**What requires customization:** <...>
**Effort estimate:** <N days> using <pattern>
**Who has done it:** <reference to existing implementation if found>

### Suggested response (verbatim)
"<Ready-to-use client-facing paragraph. Professional, confident, honest.>"
```

**Worked examples:** `${CLAUDE_PLUGIN_ROOT}/skills/odoo-objection-handling/references/examples.md`

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
