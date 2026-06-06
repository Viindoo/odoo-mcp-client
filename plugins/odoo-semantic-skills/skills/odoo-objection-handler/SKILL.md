---
name: odoo-objection-handler
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

- Full evidence package (modules + code + demo steps) → use `odoo-capability-proof`
- Simple feature availability lookup → use `odoo-feature-check`
- Effort estimate & scope for proposal → use `odoo-gap-analysis`

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
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Client objections about Odoo capabilities fall into four categories:
1. **False** — the feature exists and works well. Counter with evidence.
2. **Partially true** — standard coverage is limited; custom development closes the gap easily.
   Frame as "standard practice, not a gap."
3. **True but mitigated** — Odoo doesn't support it natively, but an OCA module, custom extension,
   or well-established integration pattern exists.
4. **True and significant** — honestly acknowledge and propose the workaround or alternative.

**Never fabricate capabilities.** Intellectual honesty builds more long-term trust than overselling.
If the objection is valid, say so clearly and pivot to how the gap is handled in practice.

**Distribution-specific advantages:** Many objections about capability gaps can be countered by
distribution-specific modules (custom extensions, partner modules, or third-party add-ons) that
cover specialized functionality — things Odoo CE/EE base doesn't have. Identify the appropriate
solution for your customer's platform.

**Data priority:** MCP tool results determine whether the objection is True, False, or Partially
true. If `check_module_exists` or `find_examples` confirms a feature exists but training knowledge
was uncertain, use the MCP result to counter the objection with confidence.

**Framework — ACA:**
- **A**cknowledge: validate the concern as a legitimate question, not a attack
- **C**ounter: present evidence-backed response
- **A**ffirm: close with confident capability statement or honest workaround

## Instructions

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` +
`model_inspect(model=…, method='fields')` + `module_inspect(name=<module>, method='summary', odoo_version='auto')`
simultaneously. All are independent — `find_examples` uses the objection text as its semantic query and doesn't
need the module check result; `model_inspect` uses the known model name; `module_inspect` adds module-scope
numbers (N models/views) that make the ACA "Counter" table concrete ("Odoo ships this across 4 models and 9
views") rather than a bare field name.

**Round 2 (conditional):** Call `suggest_pattern` only if Round 1 confirms the feature requires
customization. If the feature exists natively (`check_module_exists` returns CE or EE hit),
skip `suggest_pattern` entirely.

The "Suggested response (verbatim)" section should be ready to use in a client meeting without
editing. Keep it professional but conversational.

## Standalone-first fallback

The objection text is already in the invocation - do not ask the caller to re-provide it.
Resolve customer context without asking:

1. `Read .odoo-ai/context.md` (per `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`)
   for `odoo_version`, `viindoo_profile`, and industry hints.
2. If a customer name is known, `Read` the vault dossier at
   `Resources/Competitors/<name>.md` or `Sales/Customers/<name>.md` if present.

When OSM is unreachable, follow the three-tier grounding order from
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2 - self-serve first:** `WebFetch` relevant Odoo source or docs to ground
   capability claims; use local `Read`/`Grep` when a source tree is available.
   Label artifacts `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 - only if all Tier-2 fetches fail:** generate the ACA response from
   training knowledge and prepend `OSM unavailable - ungrounded`; add caveat "not yet
   verified against the codebase; fact-check evidence when OSM is back online". Ask the
   caller (`NEEDS_CONTEXT`) only for inputs that no tier above can resolve (e.g.,
   undisclosed customer context that is not on disk).

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

## Examples

**Example 1:**
Prompt: "handle the objection that Odoo doesn't support complex approval workflows"
Output: Counter-evidence citing `approval` module (EE) or `mail.activity.mixin` pattern (CE
extension); code example of multi-level approval; talking points; verbatim response.

**Example 2:**
Prompt: "customer says Odoo doesn't have accounting standards compliance for their region"
Output: Counter: specialized localization modules or custom extensions exist;
`model_inspect(model='account.move', method='fields', odoo_version='auto')` shows compliance-specific fields; verbatim
response with region-appropriate solution.
