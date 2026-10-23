---
name: odoo-brl
argument-hint: "[requirements list / RFP]"
description: >-
  Turns a requirement list into a costed, dependency-ordered plan with RTM export
model: sonnet
---

## Role

Odoo implementation architect / BRL analyst - responsible for turning a raw list of customer
business requirements into a classified, costed, phased implementation plan with full
traceability from requirement to evidence to budget line.

## Out of Scope

- Single feature availability check -> use `odoo-feature-check`
- Shorter coverage/classification matrix, no costing, no dependency DAG (fewer than ~tens of items) -> use `odoo-gap-analysis`
- Code generation or module scaffolding -> use `odoo-coding`
- Source-level API diff between versions -> use `odoo-version-diff`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile(profile_name='<profile from the resolved instance entry>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `list_available_versions` ☆ - Enumerate which Odoo versions the server has indexed.
- `list_available_profiles` ☆ - Enumerate which tenant profiles exist in the server index.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
<!-- END GENERATED TOOLS -->

## Context

**4-way classification:**
- `Available-in-Odoo-CE` - exists in odoo profile, edition=CE, zero custom dev
- `Available-in-Odoo-EE` - exists in odoo profile, edition=EE (license cost applies)
- `Available-in-Viindoo` - NOT in odoo profile, IS in `standard_viindoo_<version>` (or OEEL-1 license notice)
- `Custom` - not in either profile; effort_tier sub-tiers: Extension-M/L (inherit point exists) or Custom-XL (new build)

## Instructions

### Phase 0 - INGEST + BOOTSTRAP

1. **Parse input:** Accept BRL in any format (CSV, XLSX-exported CSV, JSONL, pasted list, free text).
   Assign stable `req_id` values: `REQ-0001` ... `REQ-N` (zero-padded to 4 digits min; extend if N>9999).
   If the input is a source requirement document (RFP / spec / list) rather than free-form, apply
   `${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md` - extract each requirement faithfully, not inferred.

2. **Write internal state:**
   - `<SHARE_DIR>/brl/<job-id>/manifest.json` - job metadata (see `reference/schema.md` §manifest)
   - `<SHARE_DIR>/brl/<job-id>/input.jsonl` - 1 line per requirement
   - `<SHARE_DIR>/brl/<job-id>/chunkplan.json` - chunk split (default 50/chunk, overridable by the request)

   `<job-id>` format: `<CUSTOMER_LABEL>-<YYYYMMDD>-<4hex>` (e.g. `Customer-A-20260531-9f3a`).
   Use abstract label for CUSTOMER_LABEL. Never use real company name.

3. **Resolve the project facts:** work the rungs of
   `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` in order and stop at the first that
   answers the series and the profile. Rung 2 returns the exact declared profile name; rung 3 derives
   the series from the checkout. Return `status: NEEDS_CONTEXT` naming the series when every rung left
   it unresolved.

4. **MCP bootstrap** (once per session, on the values step 3 resolved):
   - `set_active_version(odoo_version=<resolved series>)` -> pin for session
   - `set_active_profile(profile_name=<resolved profile>)` -> base profile. Use the resolved name
     verbatim, or confirm one against `list_available_profiles` when no rung supplied it - never
     hard-code a hyphenated or unversioned name.
   - `profile_inspect(method='summary', name=<resolved profile>, odoo_version=<resolved series>)`
     -> confirm the profile's composition. When no `[[instance]]` covers this repo,
     offer `/odoo-ai-agents:odoo-setup` to declare one - an offer, never a precondition; BRL proceeds
     on the resolved values regardless.

5. Proceed to Phase A.

### Seed + cross-check from a prior gap-analysis (optional)

A `<SHARE_DIR>/gap-analysis/*/gap-matrix.jsonl` (newest) is a PRIOR, never ground truth: it seeds the candidate `module` and the effort-tier family per `req_id`, and Phase A re-grounds every seeded item (the double-profile `check_module_exists` alone resolves the 4-way edition split); on a divergence the OSM verdict wins and `notes` records both. Rows stay format-compatible with gap-analysis (`req_id`, `requirement`, `module`, an effort axis, `notes`; the design hand-off shape). Rules: `reference/procedure.md` § Seed + cross-check.

### Phase A - CLASSIFY (outer sequential per chunk, inner <=3 parallel MCP)

OSM-first (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`): training knowledge only PROPOSES up to 3 candidate modules per requirement (A0); the verdict comes from `cache.json` (A1) or the double-profile `check_module_exists` on the odoo and the Viindoo profile, with `find_examples` only when A0 produced nothing (A2, <=3 concurrent across the chunk, results cached); A3's decision tree yields `Available-in-Odoo-CE|EE`, `Available-in-Viindoo` (an OEEL-1 notice is informational) or `Custom` (tier settled in Phase C) and a 1-2 sentence `solution`. OSM unreachable marks the item `classification_source="osm-error"`, never a guessed edition. Write `chunks/chunk-NNN.A.jsonl`. Re-pin the session after 23h or a "no active version" error; retries 1s/2s/4s then `risk_flag="mcp-fail"`. Heuristics, calls and the decision tree: `reference/procedure.md` § Phase A.

### Phase B - COST (pure lookup, 0 MCP calls)

`effort_tier` is an axis separate from `classification`: `Standard` (activation, 0 days) when the text implies no setup, else `Config`; a `Custom` item with an `_inherit` point is `Extension-M` or `Extension-L`, with no model match `Custom-XL` (Phase C may refine). Days and cost come only from `cost-config.json` (`days_min/max * blended rate`). Write `chunks/chunk-NNN.B.jsonl`. Formula: `reference/procedure.md` § Phase B.

### Phase C - EVIDENCE (inner <=3 parallel, Extension/Custom items only)

Standard and Config items need no evidence. For Extension and Custom items, `model_inspect`, `suggest_pattern`, `lookup_core_api` and `impact_analysis` (<=3 concurrent) confirm the extension point, refine Extension-M/L by blast radius or confirm Custom-XL, set `evidence_module` / `evidence_field` / `evidence_snippet_ref` and synthesize the `solution`. Write `chunks/chunk-NNN.C.jsonl`. Calls and outcomes: `reference/procedure.md` § Phase C.

### CHECKPOINT (after each chunk)

Merge A + B + C into `chunks/chunk-NNN.merged.jsonl` (overwrite, never append) and rebuild `results.jsonl` from the merged files in chunk order; update `checkpoint.json` LAST (processed count, `chunks_done`, `last_completed_chunk`, per-req `done`). Resume reads it and continues at `last_completed_chunk + 1`; a re-run is idempotent. Detail: `reference/procedure.md` § CHECKPOINT.

### Phase D - DAG (post-all-chunks; main, optional per-cluster subagent)

Runs ONCE over the finished `results.jsonl`; never re-classifies or re-costs. D1 builds the module adjacency with `module_inspect(method='dependencies')` (cached); D2 cuts clusters by `(module_family, business_domain)`, 8-20 of them, never by size; D3 reasons business-logic and data-flow edges inside each cluster, inline by default, one forked leaf per cluster only under Hard rule 1 (brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`, model per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection, no Skill tool, no spawn); D4 adds one representative technical edge per depending cluster pair and, for Custom clusters, at most one business-affinity edge per source cluster, none without a clear affinity; D5 Kahn sort gives `phases`, a cycle is reported with three resolution options (split, manual, shared-prereq) and a partial order; D6 computes the critical path over `effort_days_max`. No `impact_analysis` here. Outputs `dag.json` and `dag.mermaid` (schemas in `reference/schema.md`, style in `reference/deliverable-templates.md`). Algorithms and prompts: `reference/dag-prompt.md`, `reference/procedure.md` § Phase D.

### Phase E - DELIVERABLES (pure write, 0 MCP calls)

Write every deliverable atomically: `results.jsonl` (rebuilt from the merged chunks, `dependencies` and `impl_phase` back-filled), `rtm.csv`, `cost.json` (the project roll-up of `reference/procedure.md` § Phase E: customization coefficient, cross-module factor, the single highest applicable risk multiplier recorded as `risk_multiplier_applied`, contingency, a 7-line phase breakdown reconciling to `budget_max`, annual maintenance), `dag.json` + `dag.mermaid`, and `report.md` (template: `reference/deliverable-templates.md`); a DAG cycle is listed with its options, never hidden. Schemas: `reference/schema.md`.

## Hard rules

1. **NL-dispatch only:** When delegating to another skill (not expected in normal BRL flow),
   use a natural-language prompt. Do NOT use the Skill tool. Subagent launch is allowed for EXACTLY
   ONE purpose: Phase D DAG per-cluster reasoning workers (only when >10 large clusters). Any such
   subagent prompt MUST contain: `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
2. **Leaf subagents:** Phase D DAG cluster subagents must never spawn another subagent or invoke a skill.
3. **Public-repo safety:** Abstract customer labels only. Never write real company names, VND amounts,
   or internal pricing into any committable file. `<SHARE_DIR>/brl/` is gitignored.
4. **No cost fabrication:** All cost figures from `cost-config.json` lookup. No LLM-generated numbers.
   If missing: stop and report "cost-config.json not found - cannot compute deterministic cost."
5. **OEEL-1 no-retry:** When check_module_exists returns a license notice, classify as
   Available-in-Viindoo and stop. Do NOT retry, do NOT call model_inspect on OEEL-1 modules.
6. **Project facts:** Series and profile come from `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, worked in rung order. Return `status: NEEDS_CONTEXT` naming what every rung left unresolved.
7. **Principal-branch-lock:** Read-only on the project repo. Only write within the machine-global
   `$ODOO_AI_HOME` state root (two-axis convention: `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) - never a source file in the project repo.
8. **Sequential outer:** Never fan-out chunks to parallel subagents. Inner <=3 MCP parallel per chunk
   is the only concurrency (Mode A - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`).

## Standalone-first fallback

When OSM is unreachable (bootstrap fails or `check_module_exists` returns repeated errors):

1. **Phase A degrade:** Classify using LLM training knowledge only. Mark each item:
   `classification_source = "unverified-llm"`, `risk_flag = "osm-unreachable"`.
2. **Phase C skip:** `evidence_module = null`, `evidence_field = null`.
3. **Phase D degrade:** `module_inspect(name=<module>, method='dependencies', odoo_version='<version>')` is unreachable -> skip technical
   edges (D1/D4); still run D2/D3/D5/D6. Set `dag.json.meta.technical_edges = "skipped-osm-unreachable"`.
4. **Phase B/E:** Run normally (cost lookup and roll-up do not need MCP).
5. **report.md banner:** Add at top:
   `> WARNING: OSM unreachable - classifications unverified (unverified-llm). Re-run Phase A when server is available.`
6. **Resume-friendly:** When OSM returns, re-run only items with `classification_source = "unverified-llm"`.
   Re-classify and update `results.jsonl` + `rtm.csv` in place.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).

**Hand off to planning/design before coding.** Set `status: NEEDS_NEXT`:
- Any Extension-L or Custom-XL item → `next: odoo-solution-design` 
  inputs `{rtm: <path>, items: [REQ-…]}`.
- Standard/Config/Extension-M only (no L/XL) → route to `odoo-planning` instead of `odoo-coding`
  directly - `next: odoo-planning`, inputs `{rtm: <path>, items: [REQ-…]}`.

Never hand a requirement straight to an executor: establish the plan (`odoo-planning`, or
`odoo-solution-design` first for L/XL) before any code
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule). BRL is terminal
(`status: DONE`, `next: []`) ONLY when every item is fully covered with zero custom dev
(Available-in-Odoo-CE / -EE / -Viindoo, no Extension/Custom item).
