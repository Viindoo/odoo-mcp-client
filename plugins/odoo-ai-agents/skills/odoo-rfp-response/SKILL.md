---
name: odoo-rfp-response
description: >
  Rate Odoo compliance per RFP requirement and produce a response matrix - columns: Requirement |
  Odoo path (module/model/feature) | Compliance (Yes / Partial / Roadmap / No / via-Extension) |
  Evidence | Notes/effort - plus an executive summary (overall fit %, key strengths, gaps needing
  custom work). Use ANY time someone hands you a list of RFP requirements and needs a formal
  compliance response. Fire on: "respond to this RFP", "compliance matrix for these requirements",
  "rate these requirements against Odoo", "fill in this RFP response table", "score this tender
  spec against Odoo". Vietnamese triggers: "ma tran dap ung RFP", "danh gia yeu cau RFP voi
  Odoo", "lap bang compliance cho ho so thau". Route to odoo-gap-analysis for effort/quote matrix;
  odoo-capability-proof for deep code evidence on a single requirement; odoo-feature-check for a
  single yes/no availability question outside RFP context
model: inherit
---

## Persona
Pre-sales Consultant / Bid Manager

## When to use

- Prospect / public-sector client issues an RFP / RFQ / ITT expecting a formal compliance verdict per line
- You need a written compliance matrix before submitting a full proposal
- Sales engineering needs a quick score card to decide whether to bid
- Project manager needs to flag which requirements need custom dev before committing to a timeline

Difference from siblings: `odoo-gap-analysis` outputs effort tiers (days) for quoting; this skill outputs compliance verdicts. `odoo-capability-proof` gives deep code evidence for ONE requirement; this skill covers ALL requirements at once. `odoo-feature-check` handles a single feature; this skill handles a numbered list.

## Out of Scope

- Effort estimation / day-count → `odoo-gap-analysis`
- Deep code-level proof for a single requirement → `odoo-capability-proof`
- Single feature availability outside RFP context → `odoo-feature-check`
- Narrative sections of the full proposal → `odoo-content-draft`
- Objection handling after RFP submission → `odoo-objection-handling`

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

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
<!-- END GENERATED TOOLS -->

## Context

### Compliance labels (strict definitions - do not overclaim)

| Label | Meaning | When to use |
|-------|---------|-------------|
| **Yes** | Covered by a standard CE or EE module, zero development needed. State edition. | `check_module_exists` confirms presence; `model_inspect` shows the relevant fields/views |
| **Partial** | Standard module exists but covers only part; a gap remains that config alone cannot fill | Module found; coverage verified incomplete after `model_inspect` |
| **Roadmap** | Not in target version but confirmed in a later release or official roadmap | Evidence from OSM cross-version check or public roadmap - never training memory alone |
| **via-Extension** | Gap fillable with standard ORM extension (`_inherit`, computed field, wizard) | `suggest_pattern` returns a matching pattern; effort typically 1-5 days |
| **No** | Cannot be addressed by standard Odoo or light extension; requires custom dev or 3rd-party integration | Honest last resort |

**Absolute rule:** Do NOT assign `Yes` when evidence says `Partial`. Do NOT assign `Partial` when evidence says `No`. Overclaiming in an RFP creates legal and commercial risk. When OSM conflicts with training knowledge, trust OSM.

**Fit %:** `(Yes * 1.0 + Partial * 0.5 + via-Extension * 0.7 + Roadmap * 0.3 + No * 0.0) / total * 100` - round to nearest integer. Rough indicator only, not a contractual commitment.

**Version discipline:** A `No` on v14 may be `Yes` on v17. Always note the target version. For each `No` or `Partial`, optionally note the earliest version where it becomes `Yes` if OSM cross-version data is available.

## Method

Follow `${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md` for all claims.

**Round 0 - Context bootstrap + pin:** Follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`: read `.odoo-ai/context.md` if present and extract `odoo_version` and `viindoo_profile`. Call `set_active_version(odoo_version=…)` and `set_active_profile(profile_name=…)` with those values (never hard-code `standard_viindoo_17`). If `.odoo-ai/context.md` is absent, derive version from manifests on disk per the context-bootstrap snippet before asking.

The requirement list is already in the invocation context - proceed directly without asking the user to re-provide it.

**Round 1 - Parallel:** Call `check_module_exists` for EVERY requirement simultaneously. Map each requirement to its most likely module/feature keyword before firing.

**Round 2 - Parallel (after Round 1):** For requirements with partial match or unclear module scope, call `model_inspect(model=…, method='fields')` + `module_inspect(name=<module>, method='summary', odoo_version='<version>')` in parallel - one per ambiguous module/model. These reveal whether the standard view/flow already covers the requirement (no gap) or whether a field/view is absent (gap confirmed).

**Round 3 - Parallel (for Partial/No items):** Call `find_examples` + `suggest_pattern` simultaneously. A matching `suggest_pattern` result upgrades a tentative `No` to `via-Extension` if the extension is bounded and standard ORM patterns apply.

**Decision logic:**
```
check_module_exists → full match, fields confirmed → Yes (CE) or Yes (EE)
check_module_exists → module found, model_inspect shows gap → Partial
module found, suggest_pattern covers the gap, effort bounded → via-Extension
check_module_exists → not found, suggest_pattern → no match → No
cross-version check shows it exists in a later release → Roadmap
```

**Parallelism discipline:** 20 requirements must not make 20 sequential calls. Batch all Round 1 calls together, all Round 2 together, all Round 3 together. Target 3 rounds regardless of requirement count.

**Honesty discipline:** If OSM returns `not found` for a module that training knowledge says exists, report the OSM result and note the discrepancy. Do not silently override OSM with training memory.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`.

The requirement list is already in the invocation context - proceed immediately without asking the user to re-provide it.

- **Tier 2 - disk / WebFetch:** If a local Odoo source tree is present, use `find . -maxdepth 4 -name "__manifest__.py"` then `Read` relevant manifests and model files. Alternatively, `WebFetch` raw manifests from `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py`. Label artifacts `grounded: local-source (not OSM-indexed)`.
- **Tier 3 - training memory only:** Classify from training knowledge, prepend each verdict with `(OSM unavailable - unverified)`. Include caveat in executive summary: "Compliance verdicts are unverified against the code index; double-check once OSM is back online."

## Output format

```
## RFP Compliance Matrix

**Client / RFP reference:** <client name or RFP ID>
**Target Odoo version:** <version> (<CE / EE / Viindoo>)
**Requirements analyzed:** <N>
**Analysis date:** <date>

| # | Requirement | Odoo path (module / model / feature) | Compliance | Evidence | Notes / effort |
|---|-------------|--------------------------------------|:----------:|----------|----------------|
| 1 | <req text>  | `<module_name>` / `<model.name>`     | Yes        | <source> | <note>         |
| 2 | ...         | ...                                  | Partial    | ...      | Gap: <what is missing> |
| 3 | ...         | ...                                  | via-Extension | ...   | Pattern: `<suggest_pattern result>`; est. <S/M/L> |
| 4 | ...         | -                                    | No         | Not found in OSM | Custom dev required; est. <L/XL> |

**Compliance key:**
- Yes - standard CE or EE, zero development
- Partial - standard module covers part; a gap remains
- via-Extension - standard extension point exists; bounded dev (1-5 days)
- Roadmap - available in a later version or official roadmap
- No - requires custom development or third-party integration

---

### Executive Summary

**Overall fit: <N>%**

**Distribution:** Yes <N> | Partial <N> | via-Extension <N> | Roadmap <N> | No <N>

**Key strengths (top 3-5 requirements Odoo covers out of the box):**
- <req summary> - <module / brief reason>

**Gaps requiring custom work:**
- <req summary> - <why No or Partial, effort hint>

**Recommended bid position:**
<1-2 sentences: whether to bid, what to note in the covering letter about gaps, whether
EE license is required>
```

**Effort legend (for via-Extension and No rows):** S = <1d - M = 1-3d - L = 3-10d - XL = >10d

**Worked examples:** `${CLAUDE_PLUGIN_ROOT}/skills/odoo-rfp-response/references/examples.md`

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
