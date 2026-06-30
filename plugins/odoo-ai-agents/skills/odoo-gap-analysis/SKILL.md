---
name: odoo-gap-analysis
argument-hint: "[requirement list / RFP scope]"
description: >
  Gap analysis turning a list of client requirements into a costed effort matrix (Standard /
  Configuration / Extension / Custom + S/M/L/XL). Now an ORCHESTRATOR - it clusters requirements
  by functional area, delegates each cluster to the odoo-gap-analyzer subagent (main context
  stays clean), then emits a reusable file artifact under .odoo-ai/gap-analysis/. Use ANY time
  someone is about to quote, scope, or estimate an Odoo project - even if they don't say "gap".
  Fire on a list of requirements + "is this standard Odoo or do we build it?", "how many days?",
  "RFP has 23 requirements - classify them". Vietnamese: "phân tích gap", "cái này Odoo có sẵn
  hay phải build thêm", "ước lượng bao nhiêu ngày công", "ma trận effort cho báo giá". For ONE
  specific feature route to odoo-feature-check; for marketing highlights route to
  odoo-feature-highlights; for a large costed + dependency-DAG pipeline at scale route to
  odoo-brl
---

## Persona
Consultant / Project Manager

## Out of Scope

- Single feature availability check -> use `odoo-feature-check`
- Marketing highlights for version release -> use `odoo-feature-highlights`
- Source-level API diff between versions -> use `odoo-version-diff`
- Large costed + dependency-DAG pipeline at scale -> use `odoo-brl`

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
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Gap analysis sets client expectations and determines budget. Errors in either direction are costly (under = overruns; over = lost deals).

**Effort classification** (the locked `classification` axis - one of `standard | config | extension | custom`):
| classification | Definition | typical effort_tier |
|---|---|---|
| standard | Exists in CE or EE; zero dev (flag EE license in `notes`) | S (activation only) |
| config | Module exists; needs setup | S - M |
| extension | `_inherit` extension pattern | M - L |
| custom | New model, complex logic, or integration | L - XL |

`effort_tier` is the separate day axis: **S** <1d - **M** 1-3d - **L** 3-10d - **XL** >10d. `coverage` is `full | partial | none`. These four enums (`classification`, `effort_tier`, `coverage`, and `grounded`) are the locked keys of `gap-matrix.jsonl` (see § Output).

Version matters: "custom" on v12 may be "standard" on v16. v8/v9 migrations cost more (Python 2, `_columns`, `osv.osv`). **Data priority:** OSM / local source over training knowledge - never assert a verdict from memory (see § Standalone-first fallback).

**Index coverage is not ground truth.** A module ABSENT from the OSM index is NOT proof the product lacks the feature - profile/index coverage is incomplete for commercial layers. Confirm coverage with `profile_inspect(method='repos', ...)` and fall back to a local checkout (§ Standalone-first fallback). A requirement that neither OSM nor a checkout can ground is `grounded: unknown` with `notes: "BLOCKED - needs OSM index or checkout"` - never a training guess.

## When to invoke the gap-analyzer subagent

This skill is an ORCHESTRATOR. It does NOT classify requirements inline - it dispatches the
`odoo-gap-analyzer` worker agent and synthesizes the workers' output from disk, keeping the
main / team-leader context clean.

**Cluster by functional area first.** Group the requirement list by cohesive functional area
(sales, inventory, accounting, HR, manufacturing, CRM, project, website, ...), then size the
fan-out:
- **Small scope** (one cohesive area, or a short list) -> **ONE** `odoo-gap-analyzer` worker
  (the fast path - see § Instructions). It still writes the full artifact set.
- **Larger scope** -> **one worker per cluster**, dispatched in a **rolling concurrency window**
  (fill the budget, drain, dispatch the next) - the same pattern `odoo-deep-survey` uses.

**Concurrency budget:** follow **Mode B (model-weighted budget)** in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` - do not restate the weights or the
in-flight cap here. Beyond the budget, use the rolling window.

**Model per cluster:** set each worker's launch `model` from THAT cluster's complexity per the
SSOT `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § "Model-tier selection" - e.g.
a small, well-indexed cluster -> haiku; a normal cluster -> sonnet; a large or poorly-indexed
cluster needing deep local-source fallback plus cross-module reasoning -> opus. Do not restate
the tier principle - read it from the SSOT.

**Synthesize from disk, do not re-classify.** After the workers finish:
1. Read every worker's `clusters/<NN>-<area>.jsonl` shard and concatenate the rows into the
   top-level `gap-matrix.jsonl` (one row per `req_id`, no duplicates).
2. **Deduplicate by build signature** - requirements that resolve to the SAME module + pattern /
   override point / core API are ONE build. Count that build's `effort_tier` ONCE in the effort
   summary and total; tag the dependent rows `notes: "shares build with <req_id>"`. Every
   requirement still keeps its own row - dedup affects the effort roll-up, not the row count.
3. Assemble the aggregate outputs (`gap-report.md`, `gap-continuation-contract.json`).

**Cross-check at aggregation:** the merged row count MUST equal the number of requirements
dispatched, and `meta.total` MUST equal `standard + config + extension + custom`. If either
check fails, a shard is missing or malformed - re-dispatch that cluster before writing the report.

## Instructions

**Round 0 - Bootstrap + pin.** Follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`.
Read `.odoo-ai/context.md`; extract `odoo_version` and `viindoo_profile` (never hard-code
`standard_viindoo_17`); derive the version from on-disk manifests if the file is absent. The
requirement list is already in context - do not ask for it. Call `set_active_version` once as the
reachability probe (concrete version only - `'auto'` is unsafe under fan-out, per the
concurrency-guard OSM version-pin race). Pick the slug (reuse any feature slug already in play);
the artifact dir is `.odoo-ai/gap-analysis/<slug>-<date>/`.

**Cluster.** Partition the requirements by functional area (§ When to invoke). Assign each
cluster a 2-digit `<NN>` and a short `<area>` label.

**Dispatch.** Launch one `odoo-gap-analyzer` worker per cluster (or one worker total on the fast
path) at the `model` chosen for that cluster's complexity, honoring the Mode B budget with a
rolling window. Prefer CHP Tier-B `subagent_type: "fork"` (the fork inherits the orchestrator's
loaded context + version pin and shares its prompt cache; see
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`); if fork is unavailable, fall back
to a fresh `odoo-gap-analyzer` spawn (Tier-C) carrying the explicit brief - Tier-C is always
correct. Each worker brief carries:
1. **Leaf restrictions** - `Do NOT invoke the Skill tool. Do NOT spawn a sub-agent. Use
   Read/Grep/Glob/Bash + OSM MCP only; the ONLY file you Write is your own shard.`
2. **Scope, hard** - this cluster's requirements (each `req_id` + text) and the `<area>` label.
3. **Version + profile pin** - the concrete `odoo_version` and `viindoo_profile`; pass the
   concrete version on EVERY OSM call, never `'auto'`.
4. **Grounding rule** - OSM-first; on a Tier-1 MISS read the local checkout; an ungroundable
   requirement is `grounded: unknown` + `notes: "BLOCKED - needs OSM index or checkout"`. NEVER
   guess from training (§ Standalone-first fallback).
5. **Brand rule** - take module identity only from OSM `check_module_exists` / `describe_module`
   / `module_inspect` (`author`, `shortdesc`); a vendor-like token in a slug is NOT proof of a
   provider. If unprovable, leave `module` empty (`null`) and set `grounded: unknown`.
6. **Output contract** - write one JSON object PER requirement to
   `.odoo-ai/gap-analysis/<slug>-<date>/clusters/<NN>-<area>.jsonl` with the EXACT keys
   `{req_id, requirement, coverage, classification, effort_tier, module, grounded, notes}`
   (enums per § Context). Be conservative - upgrade `effort_tier` when in doubt.

The `odoo-gap-analyzer` agent owns the per-requirement OSM method (the `check_module_exists` ->
`model_inspect` / `module_inspect` -> `find_examples` / `suggest_pattern` rounds) and the
OSM-First Grounding Contract; the orchestrator does not run those calls itself.

**Synthesize + write artifacts.** Per § When to invoke: merge shards, dedup by build signature,
run the aggregation cross-check, then write the three artifacts in § Output. Finally print the
compact chat summary plus the artifact paths.

## Standalone-first fallback

OSM (the indexed Odoo source graph) is the PRIMARY source; the local checkout is the FALLBACK
(see the § MCP tools block and `${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`). Every
requirement is grounded in exactly two tiers, then `unknown` - there is NO training-memory
classification tier:

1. **`grounded: osm`** - confirmed in the OSM index (`check_module_exists` / `model_inspect` /
   `module_inspect` / `find_examples`). Use **`grounded: hybrid`** when an OSM hit is completed by
   a local-source read of a customer-local entity (a Tier-1 MISS).
2. **`grounded: local-source`** - OSM is unreachable (incl. timeout/hang) or returned a Tier-1
   MISS, and the fact was read from a local checkout (`Read`/`Grep` the addons, or `WebFetch`
   upstream for the pinned version).
3. **`grounded: unknown`** - neither OSM nor a checkout can ground the requirement. Mark the row
   `grounded: unknown` with `notes: "BLOCKED - needs OSM index or checkout"`.

A requirement that cannot be grounded by OSM or a checkout is `unknown`, never a guessed verdict.
Downgrade customer-facing wording for any `unknown` row to "to be confirmed". An OSM hit proves
the source DEFINES the capability - it is NOT a live "verified available" guarantee, so never
phrase it that way.

## Output - locked file-handoff contract

All outputs live in `.odoo-ai/gap-analysis/<slug>-<date>/`. The skill is no longer chat-only: it
writes the three artifacts below, then prints a compact summary plus these paths to chat.

### `gap-matrix.jsonl` (machine SSOT - one JSON object per requirement)

Keys EXACTLY: `{"req_id","requirement","coverage","classification","effort_tier","module","grounded","notes"}`
- `coverage` is one of `full | partial | none`
- `classification` is one of `standard | config | extension | custom`
- `effort_tier` is one of `S | M | L | XL`
- `grounded` is one of `osm | hybrid | local-source | unknown`
- `module` - the OSM-confirmed technical module, or `null` when unknown.
- `notes` - EE-license flag, dedup pointer (`shares build with <req_id>`), or the
  `BLOCKED - needs OSM index or checkout` marker.

Built by concatenating the worker shards (`clusters/*.jsonl`), deduped per § When to invoke.

### `gap-report.md` (human deliverable)

The markdown table (existing columns, each mapping 1:1 to a `gap-matrix.jsonl` key):

| # | Requirement | Standard coverage | Module | Effort type | Effort | Source | Notes |
|---|-------------|-------------------|--------|-------------|--------|--------|-------|

(`Standard coverage` = `coverage`, `Effort type` = `classification`, `Effort` = `effort_tier`,
`Source` = `grounded`.) Below the table:
- **Effort summary by category** - counts of standard / config / extension / custom + the `req_id`s.
- **Total** - deduped `effort_days` min-max from the band table (S 0-1 - M 1-3 - L 3-10 -
  XL 10-20, summed over DISTINCT builds), plus a one-line rationale.
- **Risk flags** - scope-creep / hidden-complexity items, and every `grounded: unknown` row.
- **Recommended phasing** - Phase 1 (must-have) / Phase 2 (nice-to-have).

An OSM hit means the source DEFINES the capability, not that a shipped product is "verified
available"; word `unknown` rows as "to be confirmed" (§ Standalone-first fallback).

### `gap-continuation-contract.json` (locked machine handoff)

```json
{
  "status": "DONE | NEEDS_NEXT | BLOCKED",
  "produced": ["<paths written>"],
  "meta": {
    "total": 0, "standard": 0, "config": 0, "extension": 0, "custom": 0,
    "has_nontrivial": false,
    "effort_days": {"min": 0, "max": 0}
  },
  "next": null
}
```
- `has_nontrivial` is `true` iff any `extension` or `custom` row is present.
- `next` is `"odoo-solution-design"` when `has_nontrivial` is true, else `null`.
- `effort_days` is the deduped min/max from the band table above.

## Examples

**Example 1 - small scope, fast path:**
Prompt: "gap analysis for a client who needs multi-company invoicing, approval workflows, and a
custom loyalty program"
Action: One cohesive list -> ONE `odoo-gap-analyzer` worker (sonnet). It writes
`clusters/01-finance.jsonl`; the orchestrator emits the artifact set under
`.odoo-ai/gap-analysis/<slug>-<date>/`. Rows: multi-company invoicing -> standard/S; approval
workflows -> extension/M (`mail.activity.mixin`); custom loyalty -> custom/XL. `has_nontrivial:
true` -> `next: odoo-solution-design`.

**Example 2 - larger scope, clustered fan-out:**
Prompt: "Classify these 40 requirements across manufacturing, inventory, accounting and HR for a
v17 quote"
Action: Cluster into 4 functional areas; dispatch one worker per cluster in a rolling window (the
cross-module MRP cluster -> opus; the well-indexed HR cluster -> haiku). Synthesize: merge shards,
dedup shared builds (e.g. two HR reqs that both extend `hr.employee` are one build), then write
`gap-report.md` + `gap-matrix.jsonl` + `gap-continuation-contract.json`.

## Continuation Contract

Emit the chat continuation block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next); it MUST mirror `gap-continuation-contract.json`. `produced` lists the
three artifact paths. When `meta.has_nontrivial` is true: `status: NEEDS_NEXT`,
`next: odoo-solution-design` with inputs `{gap_report: <path>, gap_matrix: <path>, items: [<extension/custom req_id>]}`
and `risk_level: L1`. Otherwise `status: DONE`, `next: []`. Surface every `grounded: unknown` row
in the risk flags so the human can supply an OSM index or checkout before design proceeds.
