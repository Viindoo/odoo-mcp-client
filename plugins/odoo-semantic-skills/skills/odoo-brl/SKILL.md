---
name: odoo-brl
description: >
  Process a business requirement list (BRL) of any size - tens to thousands of items -
  into a classified, costed, dependency-ordered implementation plan. For each requirement:
  4-way classification (Available-in-Odoo-CE / Available-in-Odoo-EE / Available-in-Viindoo / Custom)
  via double-profile odoo-semantic-mcp tool calls, a deterministic cost estimate (lookup
  table, no fabrication), and a requirements traceability matrix (RTM) for consultant
  export. Runs as a sequential-outer / parallel-inner chunked pipeline with
  checkpoint/resume so an interrupted session can restart without losing work. Fire ANY
  time someone pastes or points to a multi-item requirement list to scope end-to-end:
  "classify these 400 requirements", "turn this RFP spreadsheet into an effort + cost plan".
  For a SINGLE feature use odoo-feature-check; for a short ad-hoc gap matrix with no cost,
  no chunked pipeline, and no scale requirement use odoo-gap-analysis
model: opus
---

## Persona

Odoo implementation architect / BRL analyst — responsible for turning a raw list of customer
business requirements into a classified, costed, phased implementation plan with full
traceability from requirement to evidence to budget line.

## Out of Scope

- Single feature availability check -> use `odoo-feature-check`
- Short ad-hoc gap matrix (no cost/DAG/scale) -> use `odoo-gap-analysis`
- Code generation or module scaffolding -> use `odoo-backend-coding`
- Source-level API diff between versions -> use `odoo-version-diff`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `list_available_versions` ☆ — Enumerate which Odoo versions the server has indexed.
- `list_available_profiles` ☆ — Enumerate which tenant profiles exist in the server index.
- `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
<!-- END GENERATED TOOLS -->

## Context

The BRL engine is the core consulting deliverable for Odoo project scoping. Errors are costly:
- Under-classifying (marking Custom what is Standard) -> bloated budget, lost deal
- Over-classifying (marking Standard what is Custom) -> budget overrun, unhappy client

**4-way classification target:**
- `Available-in-Odoo-CE` — module exists in odoo profile, edition=CE, zero custom dev needed
- `Available-in-Odoo-EE` — module exists in odoo profile, edition=EE (license cost applies)
- `Available-in-Viindoo` — NOT in odoo profile, IS in `viindoo_internal_<version>` (or OEEL-1 license notice)
- `Custom` — not in either profile; effort_tier sub-tiers: Extension-M/L (inherit point exists) or Custom-XL (new build)

**OEEL-1 license notice (load-bearing):** When `check_module_exists` returns a license notice
for OEEL-1-restricted modules, treat as `Available-in-Viindoo`, set `notes="OEEL-1 restricted detail"`,
`evidence_field=null`. Do NOT retry, do NOT fabricate field detail.

**Cost is deterministic:** All cost numbers come from `cost-config.json` lookup. No LLM
generates cost figures. This is essential for auditability when defending quotes to clients.

**Public-repo safety:** Customer labels must be abstract (Customer-A, Customer-B, etc.).
Never write real company names, VND figures, or internal pricing into any committed file.
`.odoo-ai/brl/` is gitignored and is the only location for job artifacts.

## Instructions

### Phase 0 - INGEST + BOOTSTRAP

1. **Parse input:** Accept BRL in any format (CSV, XLSX-exported CSV, JSONL, pasted list, free text).
   Assign stable `req_id` values: `REQ-0001` ... `REQ-N` (zero-padded to 4 digits min; extend if N>9999).
   Each requirement gets: `{req_id, req_text, req_category (if provided), priority (if provided)}`.

2. **Write internal state** (before GATE 0 - these are not deliverables):
   - `.odoo-ai/brl/<job-id>/manifest.json` - job metadata (see `reference/schema.md` §manifest)
   - `.odoo-ai/brl/<job-id>/input.jsonl` - 1 line per requirement
   - `.odoo-ai/brl/<job-id>/chunkplan.json` - chunk split (default 50/chunk, user can override)

   `<job-id>` format: `<CUSTOMER_LABEL>-<YYYYMMDD>-<4hex>` (e.g. `Customer-A-20260531-9f3a`).
   Use abstract label for CUSTOMER_LABEL. Never use real company name.

3. **MCP bootstrap** (once per session):
   - `list_available_versions` -> present options to user
   - `set_active_version(odoo_version=<chosen>)` -> pin for session
   - `set_active_profile(profile_name='odoo_<version>')` -> base profile (e.g. `odoo_17`; overridden per check_module_exists call). Resolve the concrete name from `list_available_profiles` / `.odoo-ai/context.md` — never hard-code a hyphenated or unversioned name (the server registers `odoo_8..odoo_19`, `viindoo_internal_17/18`, etc.; a bogus name pins to nothing and every scoped call returns empty).
   - `profile_inspect(method='summary', name='viindoo_internal_<version>', odoo_version='auto')` -> confirm the Viindoo profile's composition (inheritance chain + repos + indexed module count) before GATE 0, so you scope on real coverage instead of assuming the profile exists.

4. **Load context:** Check `.odoo-ai/context.md`. If found, use its version/profile settings as defaults.
   If absent, suggest `/odoo-onboarding` but allow continuing with manually supplied context.

5. **GATE 0:** Present plan to user before any classification work:

   ```
   ## BRL Analysis Plan
   Customer label : <CUSTOMER_LABEL>
   Odoo version   : <version>
   Profiles       : odoo_<version> (CE/EE) + viindoo_internal_<version>
   Requirements   : <N> items
   Chunks         : <M> chunks x <chunk_size> items/chunk
   Est. MCP calls : ~<estimate> (with cache de-duplication)
   Est. cost band : classification only - no charge; cost estimate computed from config
   Artifacts      : .odoo-ai/brl/<job-id>/

   Options:
     approve          - start classification pipeline
     refine: <param>  - adjust chunk_size / version / rate_region / risk_profile
     cancel           - abort
   ```

   Do NOT proceed to Phase A until the user sends `approve` (or equivalent positive confirmation).

### Phase A - CLASSIFY (outer sequential per chunk, inner <=3 parallel MCP)

> **OSM-First Grounding Contract** (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md):
> A0 below uses training knowledge only to *propose* candidate modules — the final
> classification of every requirement MUST be confirmed against OSM (`check_module_exists`
> per profile/version, `find_examples` for the unmapped), never asserted from memory. If
> OSM is unreachable, mark the item ungrounded (`classification_source="osm-error"`) rather
> than guessing a CE/EE/Viindoo verdict. Any optional Phase D subagent inherits this contract.

For each chunk (outer loop, sequential):

**A0 - LLM module mapping (no MCP, fastest):**
For each requirement in the chunk, use training knowledge to generate <=3 candidate Odoo
module names. Apply naming heuristics:
- "hoa don / invoice / AP / AR" -> account
- "kho / warehouse / inventory / stock" -> stock
- "ban hang / sales order" -> sale
- "mua hang / purchase" -> purchase
- "nhan su / HR / payroll" -> hr, hr_payroll
- "san xuat / manufacturing / MRP" -> mrp
- "du an / project / tasks" -> project
- "khach hang / CRM / leads" -> crm

If 0 confident candidates -> mark "unmapped", set `classify=Custom tentative`, queue for `find_examples`.

**A1 - Cache lookup:** Check `cache.json` for each `(candidate_module, odoo_version)` pair.
Cache keys: `"odoo:<module>:<version>"` and `"viin:<module>:<version>"`.
Cache HIT -> use stored verdict, skip MCP call. This eliminates 60-80% of calls when many
requirements share modules.

**A2 - Double-profile MCP (parallel within item, <=3 concurrent total across chunk):**
For each candidate NOT in cache, call in parallel:
- `check_module_exists(name=<candidate>, odoo_version='auto')` with active profile = `odoo_<version>`
- `check_module_exists(name=<candidate>, profile_name='viindoo_internal_<version>', odoo_version='auto')`
- `find_examples(query=<req_text>, odoo_version='auto')` ONLY if A0 produced 0 candidates OR all candidates missed

After each call, write result to `cache.json`.

**A3 - Decision tree + solution synthesis:**
```
if r_odoo.exists:
    classification = Available-in-Odoo-{r_odoo.edition}   # CE or EE
    module = r_odoo.module_name
    edition = r_odoo.edition
    solution = "Activate module `{module}` + {brief config note}."
elif r_viin.exists OR r_viin.license_notice:
    classification = Available-in-Viindoo
    module = r_viin.module_name
    if r_viin.license_notice:
        notes = "OEEL-1 restricted detail"
        evidence_field = null
        solution = "Activate Viindoo module `{module}` (OEEL-1 license required)."
        # write 1 line to errors.jsonl type=license_restricted (informational, non-blocking)
    else:
        solution = "Activate Viindoo module `{module}` + {brief config note}."
else:
    classification = Custom
    solution = null   # placeholder; filled in Phase C after evidence
    # effort_tier sub-tier determined in Phase C:
    #   if model exists but missing field/method -> Extension-M or Extension-L
    #   if no model match at all -> Custom-XL
```

`solution` is 1-2 sentences describing HOW to implement (what to activate / configure / extend / build).
It is written at A3 for Standard/Config/Viindoo items and filled at Phase C for Custom items.

Write `chunks/chunk-NNN.A.jsonl` (1 line per requirement, A-phase fields only).

**Session TTL check:** At the start of each chunk, check `checkpoint.json.session_pinned_at`.
If `now - session_pinned_at > 23h` OR previous call returned "no active version" error,
re-run bootstrap (`set_active_version` + `set_active_profile`), update `session_pinned_at`.

**Retry policy:** Per-call exponential backoff: 1s, 2s, 4s (max 3 attempts). On persistent
failure: mark item `classification_source="osm-error"`, `risk_flag="mcp-fail"`, continue.
Rate-limit: inner concurrency already capped at 3 - this is the primary rate-limit guard.

### Phase B - COST (pure lookup, 0 MCP calls)

For each requirement in the chunk, compute cost from `cost-config.json`:

```
days_min = effort_lookup[effort_tier].min_days
days_max = effort_lookup[effort_tier].max_days
rate     = rate_card.blended_vn          # default; use role-specific rate if requested
cost_usd_min = days_min * rate
cost_usd_max = days_max * rate
```

`effort_tier` is a SEPARATE axis from `classification` — a CE/EE/Viindoo item can still be
`Standard` (pure activation) or `Config` (needs setup work). Determine the tier from the work
the requirement implies, not from the class alone:
- Module exists (CE/EE/Viindoo) AND the requirement is satisfied by activating the module with
  zero setup -> `Standard` (0 days)
- Module exists but the requirement needs configuration only, no code (tax rules, multi-company
  setup, device/IoT enrolment, workflow rule) -> `Config`
- `Custom` class with an `_inherit` extension point -> `Extension-M` (simple) or `Extension-L`
  (complex, multi-model) — resolved in Phase C from model_inspect evidence
- `Custom` class with no module/model match at all -> `Custom-XL`

> The class never *forces* a tier. Eval golden cases reflect this: a CE `sale` activation is
> `Standard` (0 cost) while an EE `iot` requirement is `Config` (device setup). Default to
> `Standard` for a module-exists item only when the req text implies no setup; otherwise `Config`.

Tier refinement: after Phase C evidence, Extension items may be upgraded/downgraded based
on field/method findings. Phase B runs with A-phase tier as initial estimate; Phase C may
update the tier before chunk CHECKPOINT merges final values.

Write `chunks/chunk-NNN.B.jsonl`.

### Phase C - EVIDENCE (inner <=3 parallel, Extension/Custom items only)

For Standard and Config items: SKIP (module + edition already = proof).
For Extension and Custom items only:

Call in parallel (<=3 concurrent):
- `model_inspect(model=<candidate_model>, method='fields', odoo_version='auto')` - confirm extension point exists
- `suggest_pattern(intent=<req_text>, odoo_version='auto')` - find pattern; guides effort-tier refinement
- `lookup_core_api(name=<method_name>, odoo_version='auto')` - if Extension needs method-level confirmation
- `impact_analysis(entity_type='model', entity_name=<candidate_model>, odoo_version='auto')` - blast radius of the extension point; ground the Extension-M vs Extension-L decision in the real count of dependent modules/downstream fields instead of estimating it

From results:
- If model exists with relevant field/method -> `extension_point_confirmed = true`; keep Extension tier
- If model exists but field/method missing -> may upgrade to Extension-L
- If the impact_analysis blast radius is large (many dependent modules / downstream fields) -> upgrade to Extension-L; if isolated -> keep Extension-M
- If no model match at all -> confirm Custom-XL
- Set `evidence_module`, `evidence_field`, `evidence_snippet_ref`

After evidence, synthesize `solution` (1-2 sentences) using the class-specific pattern:
- Extension-M/L: `"Inherit model `{evidence_module}.{model}` via `_inherit`; add {field/method name} to satisfy {brief req description}."`
- Custom-XL: `"New module: build {brief description of what to create} with no existing Odoo base model to extend."`

Write `chunks/chunk-NNN.C.jsonl`.

### CHECKPOINT (after each chunk)

Merge A + B + C results for this chunk into a per-chunk merged file
`chunks/chunk-NNN.merged.jsonl` (one obj/line, OVERWRITE — never append). Then rebuild
`results.jsonl` by concatenating the `chunk-*.merged.jsonl` files in chunk order.
**Do NOT append directly to `results.jsonl`** — append is not idempotent and would duplicate
rows if a chunk is re-run. Rebuilding from the per-chunk merged files is deterministic: one
row per req_id regardless of how many times a chunk is re-processed.

Then update `checkpoint.json` (this is the LAST write of the chunk so a crash before it leaves
the chunk re-runnable, not half-committed):
- Increment `processed` by chunk size
- Append chunk idx to `chunks_done`
- Update `last_completed_chunk`
- Mark per-req status as "done" (only in-flight items in `per_req` sparse dict)

**Resume protocol:** On restart, read `checkpoint.json`. Jump to outer loop at
`last_completed_chunk + 1`. Items already "done" in `per_req` skip all phases.
Re-running a chunk is idempotent: it OVERWRITES that chunk's `chunk-NNN.*.jsonl` +
`chunk-NNN.merged.jsonl` files, and `results.jsonl` is rebuilt by concatenation — so a chunk
that was processed but not checkpointed (crash window) produces no duplicate rows on re-run.

### Phase D - DAG (post-all-chunks; main + optional per-cluster Opus subagent)

Phase D runs ONCE after every chunk has completed Phase A+B+C (all requirements classified
and costed in `results.jsonl`). It is a bolt-on layer: it reads the finished `results.jsonl`
and writes two new artifacts (`dag.json`, `dag.mermaid`) plus back-fills `dependencies` and
`impl_phase` on each `results.jsonl` row. It NEVER re-runs classification or cost.

The hard problem is scale: pairwise dependency reasoning is O(n^2) (1000 items ~= 500k pairs),
which blows the context window and cost. Phase D cuts this with a **cluster-cut heuristic** so
Opus only reasons inside a cluster. The full reasoning prompt lives in `reference/dag-prompt.md`.

**D1 - Technical bootstrap (deterministic, parallel MCP):**
Collect the set of UNIQUE module names across `results.jsonl` (dedup; null/Custom-only items
contribute no module). For each unique module call, with inner concurrency <=3:
```
module_inspect(name=<module>, method='dependencies', odoo_version='auto')   # -> {"depends": ["base","mail",...]}
```
Build a technical module-adjacency map `{module -> [depends_on_modules]}`. Cache results in
`cache.json` under key `deps:<module>:<version>` so a resumed Phase D does not re-call.
These become **technical** edges between requirements (resolved at D4).

**D2 - Cluster-cut:**
Assign every requirement a `cluster_key = (module_family, business_domain)`:
- `module_family` = the root module from its classification (account, sale, stock, mrp, hr,
  purchase, project, crm, ...). Custom items with no module take `module_family = "custom"`.
- `business_domain` = an LLM tag derived from `req_category` / `req_text`
  (Finance, Sales, Inventory, Manufacturing, HR, Procurement, Project, CRM, Cross-cutting).

Group requirements by `cluster_key`. Target **8-20 clusters**.

> **HEURISTIC BOUND (acceptance I6) — cluster size cap = 120 requirements/cluster.**
> Opus reasons over at most 120 items per cluster so the cluster req-list fits comfortably in
> one context window. If any cluster exceeds 120 items, SPLIT it deterministically before D3:
> sub-partition that cluster by a secondary key (priority bucket Must/Should/Nice, then
> req_id range) into sub-clusters of <=120 items each, suffixing the cluster id
> (`account-Finance#1`, `account-Finance#2`, ...). Record the split in `dag.json.meta.cluster_caps`.
> This cap is the load-bearing reason Phase D stays tractable at thousands of items; it is
> documented identically in `reference/dag-prompt.md` and `reference/schema.md`.

**D3 - Intra-cluster reasoning (Opus, per cluster, <=120 items each):**
For each cluster, reason about business-logic + data-flow edges INSIDE that cluster only.
The exact prompt is in `reference/dag-prompt.md` (cluster-scoped, input = that cluster's
req-list, output = `{edges:[{from,to,type,reason}]}` JSON).

- Default: reason **inline** in the main context, one cluster at a time (sequential).
- Optimization: when there are **>10 large clusters** (each near the 120 cap), launch **one
  Opus subagent per cluster** with `context: fork` (or the Agent tool) — depth-2 is allowed
  here (main -> skill -> DAG subagent). The subagent prompt MUST contain the hard-rules line:
  `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
  Each subagent returns ONLY its cluster's edges JSON (<=2k); the main context merges them.

Only intra-cluster pairs are ever considered, so the work is `O(Σ k_c^2)` not `O(n^2)`.

**D4 - Inter-cluster edges (rule-based + business-affinity for Custom):**
Derive cross-cluster edges from two complementary sources — do NOT fan out pairwise:

*Part A — Technical module deps (deterministic):*
```
for each (cluster_A, cluster_B):
    if module_family(cluster_A) depends_on module_family(cluster_B)   # from D1 map
        add ONE representative technical edge:
            from = earliest req (by topo-eligible / lowest req_id) in cluster_B
            to   = earliest req in cluster_A
        type = "technical", reason = "module <A> depends on module <B> (manifest)"
```

*Part B — Business-domain affinity for Custom clusters (LLM-reasoned, bounded):*
Custom items (module_family="custom") have no module in the D1 map, so they produce ZERO
technical inter-cluster edges from Part A. To avoid dropping these cross-cluster dependencies,
derive inter-cluster edges via **business-domain affinity heuristic** (LLM-reasoned):

```
custom_clusters = clusters where module_family == "custom"
for each custom_cluster C:
    # Step 1: identify which non-custom clusters C's items depend on by reading
    #         their req_text / business_domain tag and reasoning about ordering need.
    #         Example: cluster "custom-Sales" (loyalty, discount engine) plausibly
    #         depends on cluster "sale-Sales" (base sales order) being set up first.
    #         Example: cluster "custom-Finance" (VN tax report builder) depends on
    #         cluster "account-Finance" (chart of accounts + tax config).
    dependent_on_clusters = LLM_reason_business_affinity(C, all_non_custom_clusters)
    #   Output: list of (source_cluster, reason_string) pairs.
    #   Bound: emit at most ONE representative edge per (custom_cluster, source_cluster) pair.

    for each source_cluster S in dependent_on_clusters:
        add ONE representative business-affinity edge:
            from = earliest req (lowest req_id) in S
            to   = earliest req in C
        type = "business-logic"
        reason = "custom cluster '<C.id>' requires '<S.id>' domain to be established first: {reason_string}"
```

**Heuristic bound:** Only representative edges (one per ordered cluster pair). LLM reasoning
is O(|custom_clusters| x |non_custom_clusters|) cluster-level prompts, NOT O(n^2) item pairs.
A custom cluster with no clear domain affinity emits zero edges (conservative, no fabrication).
Record all D4-B edges in `dag.json` with `type="business-logic"` so they are distinguishable
from D4-A technical edges. Document in `dag.json.meta.custom_affinity_edges` the count of
edges added via this heuristic.

One representative edge per ordered cluster pair keeps the DAG sparse (`O(C^2)` cluster pairs,
not `O(n^2)` requirement pairs).

**D5 - Kahn topological sort + cycle detection:**
Run Kahn's algorithm (BFS) over the union of edges `(intra-cluster ∪ inter-cluster ∪ technical)`:
```
in_degree[r] = number of incoming edges
queue = all r with in_degree 0
while queue: pop n -> append to order; for each successor m: in_degree[m]-=1; if 0 enqueue m
if len(order) != len(requirements): CYCLE detected
```
- On success, `topological_order` = the emitted order.
- Assign `phases`: phase 1 = all in-degree-0 nodes; remove them; repeat. Each peel = one phase.
  Write `impl_phase` back onto every `results.jsonl` row.
- **On cycle:** identify the cycle members (nodes never emitted) and DO NOT silently drop edges.
  Report them explicitly in `dag.json.cycles` AND in the GATE E summary, each with the three
  resolution options:
  1. **split** — break the requirement into a phase-A part and a later phase-B part;
  2. **manual** — mark the cycle members for manual implementor ordering;
  3. **shared-prereq** — introduce a new shared prerequisite (base setup) both depend on.
  Phase D still emits a partial `topological_order` for the acyclic remainder so the rest of
  the plan is usable.

**D6 - Critical path (EST/EFT over effort_days):**
Compute Earliest Start Time / Earliest Finish Time per node using `effort_days_max` as node
weight over the DAG, then trace the longest path:
```
EST[n] = max(EFT[p] for p in predecessors(n)), 0 if none
EFT[n] = EST[n] + effort_days_max[n]
critical_path = backtrace from the node with max EFT along predecessors that define it
critical_path_days = max EFT
```

**Output (write after GATE E approve, see Phase E):**
- `dag.json` — adjacency: `nodes`, `edges` (each `{from,to,type,reason}`), `topological_order`,
  `phases`, `cycles`, `critical_path`, `critical_path_days`, plus `meta` (cluster list + caps).
  Schema: `reference/schema.md` §dag.json. Edge `type` ∈ `technical | business-logic | data-flow`.
- `dag.mermaid` — `flowchart TD`, requirements grouped into `subgraph` by `impl_phase`. Node
  label = `REQ-ID\n<short req_text>\n<effort_tier> | <days>`. Style fill by classification class:
  CE = green (`fill:#d8f0d8,stroke:#2a2`), EE = yellow (`fill:#ffe,stroke:#cc0`),
  Viindoo = purple (`fill:#e8d,stroke:#808`), Custom = red (`fill:#f88,stroke:#c00`).

**Do NOT use `impact_analysis`** for Phase D. That tool is REVERSE direction (who depends on
me / blast radius) and is wrong for forward implementation planning.

**Standalone (OSM down):** if D1 `module_inspect(dependencies, odoo_version='auto')` is unreachable, skip technical
edges (D1/D4), still run D2/D3 (LLM business/data-flow) + D5/D6, and flag in `dag.json.meta`:
`"technical_edges": "skipped-osm-unreachable"`.

### Phase E - DELIVERABLES (pure write, 0 MCP calls)

**GATE E:** Before writing final deliverables, present summary:

```
## BRL Analysis Summary - <job-id>
Requirements analyzed : <N>
Classification mix    :
  Available-in-Odoo-CE   : <N> (<pct>%)
  Available-in-Odoo-EE   : <N> (<pct>%)
  Available-in-Viindoo   : <N> (<pct>%)
  Custom                 : <N> (<pct>%)
Errors / flagged       : <N> (see errors.jsonl)
Base effort            : <min_days> - <max_days> man-days
Budget estimate (blended vn): $<min> - $<max>
Dependency DAG         :
  Implementation phases : <P> phases
  Critical path         : <K> requirements, <critical_path_days> days
  Cycles detected       : <C>  (<list cycle members + resolution options if C > 0>)

Options:
  approve  - write deliverables
  refine   - re-run Phase D (DAG) or Phase E roll-up (rate_region / risk_profile)
  cancel   - discard deliverables (internal state preserved for resume)
```

When `Cycles detected > 0`, list each cycle's members and its three resolution options
(split / manual / shared-prereq) inline in the GATE E summary — never hide a cycle.

On `approve`, write ALL deliverables atomically:

1. **`results.jsonl`** - rebuilt during the chunk loop by concatenating
   `chunks/chunk-*.merged.jsonl` in order (one row per req_id, no duplicates). Finalize by
   verifying all N requirements are present exactly once, then back-fill `dependencies` (per-req
   incoming edge sources from Phase D) and `impl_phase` (from the Kahn phase assignment) on every
   row. Schema: see `reference/schema.md` §results.

2. **`rtm.csv`** - convert results.jsonl to CSV with header:
   `req_id,req_text,req_category,priority,classification,module,edition,effort_tier,effort_days_min,effort_days_max,cost_usd_min,cost_usd_max,solution,dependencies,impl_phase,evidence_module,evidence_field,risk_flag,status,notes`
   `dependencies` = pipe-joined (`REQ-0010|REQ-0015`) to remain CSV-safe.
   `solution` = the 1-2 sentence implementation description (from Phase A/C).

3. **`cost.json`** - project-level roll-up (formula from `docs/reference/workflow-harness.md`):
   ```
   custom_pct = count(Custom) / N
   customization_coefficient:
     custom_pct < 0.20  -> 1.0
     custom_pct 0.20-0.40 -> 1.3
     custom_pct > 0.40  -> 1.5
   unique_modules = count(distinct module values, excluding null)
   cross_module_factor = 0.08 * max(0, unique_modules - 3)
   base_effort_min = sum(effort_days_min)
   base_effort_max = sum(effort_days_max)

   # OPTIONAL: job-level risk multiplier (from cost-config.json `risk_multipliers`).
   # If the manifest or job context sets a risk profile (e.g. manufacturing, first_erp,
   # multi_site), read the corresponding factor from risk_multipliers.  When multiple
   # risk factors apply, use the SINGLE highest factor (do NOT multiply factors together
   # — this matches the cost-config.json `_note`).  Default = 1.0 (no adjustment).
   risk_multiplier = max(risk_multipliers[f] for f in applicable_risk_flags) or 1.0

   project_effort_min = base_effort_min * customization_coefficient * (1 + cross_module_factor) * risk_multiplier
   project_effort_max = base_effort_max * customization_coefficient * (1 + cross_module_factor) * risk_multiplier
   budget_min = project_effort_min * blended_rate * (1 + contingency[risk_profile])
   budget_max = project_effort_max * blended_rate * (1 + contingency[risk_profile])
   # phase_breakdown partitions the FINAL budget (contingency already included).
   # phase_distribution sums to exactly 1.0 -> the 7 lines reconcile to budget_max.
   # Do NOT add a separate contingency line here: contingency is already inside budget
   # (the (1 + contingency) multiplier) - listing it again would double-count.
   phase_breakdown[phase] = budget_max * phase_distribution[phase]  (7 lines, sum == budget_max)
   annual_maintenance = budget_max * annual_maintenance_pct   # 0.10 from config
   ```

   `cost.json` output MUST include a `risk_multiplier_applied` field recording the factor
   used (1.0 when no risk flag applies) so the roll-up is fully auditable.

4. **`dag.json`** - dependency adjacency from Phase D: `nodes`, `edges` (`{from,to,type,reason}`),
   `topological_order`, `phases`, `cycles`, `critical_path`, `critical_path_days`, `meta`.
   Schema: see `reference/schema.md` §dag.json.

5. **`dag.mermaid`** - `flowchart TD` grouped into `subgraph` by `impl_phase`; node label
   `REQ-ID\n<short>\n<tier> | <days>`; fill by class (CE green / EE yellow / Viindoo purple /
   Custom red). Template + style block: `reference/dag-prompt.md` §Mermaid format.

6. **`report.md`** - executive summary in gap-analysis format:

   ```markdown
   ## BRL Analysis Report

   **Customer:** <CUSTOMER_LABEL>
   **Odoo version:** <version>
   **Requirements analyzed:** <N>
   **Analysis date:** <date>
   **Job ID:** <job-id>

   ### Classification summary

   | Classification | Count | % | Est. effort (days) | Est. cost (USD) |
   |---|---|---|---|---|
   | Available-in-Odoo-CE | N | pct% | min-max | $min-$max |
   | Available-in-Odoo-EE | N | pct% | min-max | $min-$max |
   | Available-in-Viindoo | N | pct% | min-max | $min-$max |
   | Custom | N | pct% | min-max | $min-$max |
   | **Total** | N | 100% | min-max | $min-$max |

   ### Project budget estimate

   | Item | Value |
   |---|---|
   | Base effort | <min> - <max> man-days |
   | Customization coefficient | <value> (<pct>% Custom items) |
   | Cross-module factor | <value> (<N> unique modules) |
   | Project effort | <min> - <max> man-days |
   | Blended rate (VN) | $300 / day |
   | Contingency (<risk_profile>) | <pct>% |
   | **Budget estimate** | **$<min> - $<max>** |
   | Annual maintenance (10%) | $<value> / year |

   ### Phase distribution

   | Phase | % of budget | Est. (USD) |
   |---|---|---|
   | Discovery & Blueprint | 12% | $... |
   | Config & Development | 35% | $... |
   | Data Migration | 20% | $... |
   | Testing & UAT | 12% | $... |
   | Training | 8% | $... |
   | Project Management | 5% | $... |
   | Go-Live & Hypercare | 8% | $... |
   | **Total** | **100%** | **$<budget_max>** |

   > Contingency (<pct>%) is already inside the budget figure above - it is NOT a
   > separate phase line (that would double-count). The 7 phase rows sum to 100% of budget.

   ### Risk flags
   - <Items with osm-error or license_restricted or module-mapping-uncertain>

   ### Effort tier breakdown

   **Effort legend:** Standard = 0d · Config = 0.25-1d · Extension-M = 1-3d · Extension-L = 3-10d · Custom-XL = 10-30d

   ### Top custom requirements (effort-descending)

   | req_id | req_text | effort_tier | effort_days_max | solution |
   |---|---|---|---|---|
   | ... | ... | ... | ... | ... |

   ### Implementation phasing (from dependency DAG)

   | Phase | # requirements | Est. effort (days) | Key items |
   |---|---|---|---|
   | 1 - Foundation | N | min-max | <req_ids> |
   | 2 - Core | N | min-max | <req_ids> |
   | ... | ... | ... | ... |

   **Critical path:** <K> requirements, <critical_path_days> days
   (`REQ-XXXX -> REQ-YYYY -> ...`). See `dag.mermaid` for the full diagram.

   **Cycles:** <none, OR list cycle members + chosen resolution (split / manual / shared-prereq)>

   ### Next steps

   - Review rtm.csv in Excel for full traceability matrix
   - Follow the implementation phasing above (rendered visually in dag.mermaid)
   - Resolve any flagged dependency cycles before scheduling
   - Validate Custom items with technical workshop before finalizing quote
   ```

## Hard rules

1. **NL-dispatch only:** When delegating to another skill (not expected in normal BRL flow),
   use a natural-language prompt that matches the target skill's description. Do NOT use the
   Skill tool. The Agent tool is allowed for EXACTLY ONE purpose: Phase D DAG per-cluster
   reasoning workers (only when >10 large clusters). Any such `context: fork` subagent prompt
   MUST contain: `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
2. **Depth-2 ceiling:** This skill runs inline in the main context (depth 1). Phase D DAG
   cluster subagents are depth 2 max. Never exceed depth 2 (a DAG subagent must never spawn
   another subagent or invoke a skill).
3. **Public-repo safety:** Customer label must be abstract. Never write real company names,
   VND amounts, or internal pricing into any file that could be committed to the repo.
   `.odoo-ai/brl/` is gitignored - all job artifacts stay there.
4. **No cost fabrication:** All cost figures come from `cost-config.json` lookup.
   No LLM-generated cost numbers. If the config file is missing,
   stop and report: "cost-config.json not found - cannot compute deterministic cost."
5. **OEEL-1 no-retry:** When check_module_exists returns a license notice, classify as
   Available-in-Viindoo and stop. Do NOT retry, do NOT call model_inspect on OEEL-1 modules.
6. **Context check:** Load `.odoo-ai/context.md` if present; use its version/profile.
   Absent -> suggest `/odoo-onboarding`, allow manual continuation.
7. **Principal-branch-lock:** Read-only on the project repo. Only write to `.odoo-ai/`.
8. **Sequential outer:** Never fan-out chunks to parallel subagents. Inner <=3 MCP parallel
   per chunk is the only concurrency. Rationale: MCP-I/O-bound not CPU-bound; subagent
   fan-out risks OOM and rate-limit spikes (see failure: unbounded-opus-fanout-oom).

## Standalone-first fallback

When OSM is unreachable (bootstrap fails or `check_module_exists` returns repeated errors):

1. **Phase A degrade:** Classify using LLM training knowledge only. Mark each item:
   `classification_source = "unverified-llm"`, `risk_flag = "osm-unreachable"`.
2. **Phase C skip:** `evidence_module = null`, `evidence_field = null`.
3. **Phase D degrade:** `module_inspect(dependencies, odoo_version='auto')` is unreachable -> skip technical edges
   (D1/D4); still run D2/D3 (LLM business/data-flow) + D5/D6. Set
   `dag.json.meta.technical_edges = "skipped-osm-unreachable"`.
4. **Phase B/E:** Run normally (cost lookup and roll-up do not need MCP).
5. **report.md banner:** Add at top:
   `> WARNING: OSM unreachable - classifications unverified (unverified-llm). Re-run Phase A when server is available.`
6. **Resume-friendly:** When OSM comes back online, re-run only items with
   `classification_source = "unverified-llm"` (checkpoint distinguishes them).
   Re-classify and update `results.jsonl` + `rtm.csv` in place.

## Examples

**Example 1 - Standard dispatch:**
Prompt: "We have 800 requirements from a manufacturing client RFP - classify them, cost them, give us the RTM."
Action: Fire odoo-brl. GATE 0 plan shows 800 items / 16 chunks / est. ~1600 MCP calls with cache. After approve, runs Phase 0-A-B-C-E. Produces rtm.csv + cost.json + report.md in .odoo-ai/brl/Customer-A-YYYYMMDD-<hex>/.

**Example 2 - Resume after interruption:**
Prompt: "The BRL job from yesterday got interrupted at chunk 7 - can we resume?"
Action: Read checkpoint.json, find last_completed_chunk=6, resume outer loop at chunk 7. Report: "Resuming from chunk 7/16. 350/800 requirements already classified."

**Example 3 - OSM down:**
Prompt: "Classify this 200-item BRL but the OSM server seems down."
Action: Degrade to unverified-llm classification. Mark all items risk_flag=osm-unreachable. Complete cost.json and report.md. Banner warning in report. Offer resume when server returns.

**Example 4 - Dependency sequencing + cycle:**
Prompt: "We have the classified BRL - now give us the implementation order and flag any circular dependencies."
Action: Run Phase D. Technical bootstrap (module_inspect dependencies), cluster-cut into ~12 clusters (each <=120 items), intra-cluster Opus reasoning, rule-based inter-cluster edges, Kahn topo-sort. If a cycle is found (e.g. REQ-0042 <-> REQ-0061), report it explicitly in GATE E with three resolution options (split / manual / shared-prereq) and still emit a partial order + dag.mermaid for the acyclic remainder. Critical path and per-phase grouping shown in report.md.
