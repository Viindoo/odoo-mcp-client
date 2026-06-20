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

Odoo implementation architect / BRL analyst - responsible for turning a raw list of customer
business requirements into a classified, costed, phased implementation plan with full
traceability from requirement to evidence to budget line.

## Out of Scope

- Single feature availability check -> use `odoo-feature-check`
- Short ad-hoc gap matrix (no cost/DAG/scale) -> use `odoo-gap-analysis`
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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.

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

The BRL engine is the core consulting deliverable for Odoo project scoping. Classification errors are costly:
- Under-classifying (Custom -> Standard) = bloated budget, lost deal
- Over-classifying (Standard -> Custom) = budget overrun, unhappy client

**4-way classification:**
- `Available-in-Odoo-CE` - exists in odoo profile, edition=CE, zero custom dev
- `Available-in-Odoo-EE` - exists in odoo profile, edition=EE (license cost applies)
- `Available-in-Viindoo` - NOT in odoo profile, IS in `standard_viindoo_<version>` (or OEEL-1 license notice)
- `Custom` - not in either profile; effort_tier sub-tiers: Extension-M/L (inherit point exists) or Custom-XL (new build)

**OEEL-1 license notice (load-bearing):** When `check_module_exists` returns a license notice
for OEEL-1-restricted modules, treat as `Available-in-Viindoo`, set `notes="OEEL-1 restricted detail"`,
`evidence_field=null`. Do NOT retry, do NOT fabricate field detail.

**Cost is deterministic:** All cost numbers come from `cost-config.json` lookup - no LLM-generated figures.
This is essential for auditability when defending quotes to clients.

**Public-repo safety:** Use abstract customer labels (Customer-A, etc.). Never write real company names,
VND figures, or internal pricing into any committed file. `.odoo-ai/brl/` is gitignored.

## Instructions

### Phase 0 - INGEST + BOOTSTRAP

1. **Parse input:** Accept BRL in any format (CSV, XLSX-exported CSV, JSONL, pasted list, free text).
   Assign stable `req_id` values: `REQ-0001` ... `REQ-N` (zero-padded to 4 digits min; extend if N>9999).

2. **Write internal state** (before GATE 0):
   - `.odoo-ai/brl/<job-id>/manifest.json` - job metadata (see `reference/schema.md` §manifest)
   - `.odoo-ai/brl/<job-id>/input.jsonl` - 1 line per requirement
   - `.odoo-ai/brl/<job-id>/chunkplan.json` - chunk split (default 50/chunk, user can override)

   `<job-id>` format: `<CUSTOMER_LABEL>-<YYYYMMDD>-<4hex>` (e.g. `Customer-A-20260531-9f3a`).
   Use abstract label for CUSTOMER_LABEL. Never use real company name.

3. **MCP bootstrap** (once per session):
   - `list_available_versions` -> present options to user
   - `set_active_version(odoo_version=<chosen>)` -> pin for session
   - `set_active_profile(profile_name='odoo_<version>')` -> base profile. Resolve the concrete name
     from `list_available_profiles` / `.odoo-ai/context.md` - never hard-code a hyphenated or
     unversioned name (the server registers `odoo_8..odoo_19`, `standard_viindoo_17/18`, etc.).
   - `profile_inspect(method='summary', name='standard_viindoo_<version>', odoo_version='<version>')`
     -> confirm the Viindoo profile's composition before GATE 0.

4. **Load context:** Check `.odoo-ai/context.md`. If found, use its version/profile settings as defaults.
   If absent, suggest `/odoo-onboarding` but allow manual continuation.

5. **GATE 0:** Present plan before any classification work:

   ```
   ## BRL Analysis Plan
   Customer label : <CUSTOMER_LABEL>
   Odoo version   : <version>
   Profiles       : odoo_<version> (CE/EE) + standard_viindoo_<version>
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
> A0 below uses training knowledge only to *propose* candidate modules - the final
> classification of every requirement MUST be confirmed against OSM (`check_module_exists`
> per profile/version, `find_examples` for the unmapped), never asserted from memory. If
> OSM is unreachable, mark the item ungrounded (`classification_source="osm-error"`) rather
> than guessing a CE/EE/Viindoo verdict. Any optional Phase D subagent inherits this contract.

**A0 - LLM module mapping (no MCP):**
Use training knowledge to generate <=3 candidate module names per requirement. Heuristics:
- "hoa don / invoice / AP / AR" -> account
- "kho / warehouse / inventory / stock" -> stock
- "ban hang / sales order" -> sale
- "mua hang / purchase" -> purchase
- "nhan su / HR / payroll" -> hr, hr_payroll
- "san xuat / manufacturing / MRP" -> mrp
- "du an / project / tasks" -> project
- "khach hang / CRM / leads" -> crm

0 confident candidates -> mark "unmapped", set `classify=Custom tentative`, queue for `find_examples`.

**A1 - Cache lookup:** Check `cache.json` for each `(candidate_module, odoo_version)` pair.
Keys: `"odoo:<module>:<version>"` and `"viin:<module>:<version>"`. HIT -> use stored verdict.
This eliminates 60-80% of calls when requirements share modules.

**A2 - Double-profile MCP (parallel within item, <=3 concurrent total across chunk):**
For each candidate NOT in cache, call in parallel:
- `check_module_exists(name=<candidate>, odoo_version='<version>')` with active profile = `odoo_<version>`
- `check_module_exists(name=<candidate>, profile_name='standard_viindoo_<version>', odoo_version='<version>')`
- `find_examples(query=<req_text>, odoo_version='<version>')` ONLY if A0 produced 0 candidates OR all missed

Write each result to `cache.json`.

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

`solution` is 1-2 sentences describing HOW to implement. Written at A3 for Standard/Config/Viindoo;
filled at Phase C for Custom items.

Write `chunks/chunk-NNN.A.jsonl` (1 line per requirement, A-phase fields only).

**Session TTL check:** At the start of each chunk, check `checkpoint.json.session_pinned_at`.
If `now - session_pinned_at > 23h` OR previous call returned "no active version" error,
re-run bootstrap and update `session_pinned_at`.

**Retry policy:** Exponential backoff: 1s, 2s, 4s (max 3 attempts). On persistent failure:
mark item `classification_source="osm-error"`, `risk_flag="mcp-fail"`, continue.
Inner concurrency already capped at 3 - this is the primary rate-limit guard.

### Phase B - COST (pure lookup, 0 MCP calls)

For each requirement, compute cost from `cost-config.json`:

```
days_min = effort_lookup[effort_tier].min_days
days_max = effort_lookup[effort_tier].max_days
rate     = rate_card.blended_vn          # default; use role-specific rate if requested
cost_usd_min = days_min * rate
cost_usd_max = days_max * rate
```

`effort_tier` is a SEPARATE axis from `classification` - a CE/EE/Viindoo item can still be
`Standard` (pure activation) or `Config` (needs setup work). Determine tier from the work implied:
- Module exists AND requirement satisfied by activating with zero setup -> `Standard` (0 days)
- Module exists but needs configuration only (tax rules, multi-company, IoT enrolment) -> `Config`
- `Custom` with `_inherit` extension point -> `Extension-M` (simple) or `Extension-L` (complex, multi-model)
- `Custom` with no module/model match -> `Custom-XL`

> The class never *forces* a tier. Default `Standard` for module-exists items only when req text implies
> no setup; otherwise `Config`.

Tier refinement: Phase C evidence may upgrade/downgrade Extension items before CHECKPOINT merges final values.

Write `chunks/chunk-NNN.B.jsonl`.

### Phase C - EVIDENCE (inner <=3 parallel, Extension/Custom items only)

Skip for Standard and Config items (module + edition already = proof).

For Extension and Custom items, call in parallel (<=3 concurrent):
- `model_inspect(model=<candidate_model>, method='fields', odoo_version='<version>')` - confirm extension point
- `suggest_pattern(intent=<req_text>, odoo_version='<version>')` - find pattern; guides tier refinement
- `lookup_core_api(name=<method_name>, odoo_version='<version>')` - if Extension needs method-level confirmation
- `impact_analysis(entity_type='model', entity_name=<candidate_model>, odoo_version='<version>')` - blast radius grounds Extension-M vs Extension-L decision

From results:
- Model exists with relevant field/method -> `extension_point_confirmed = true`; keep Extension tier
- Model exists but field/method missing -> may upgrade to Extension-L
- Large blast radius (many dependent modules/downstream fields) -> upgrade to Extension-L; isolated -> keep Extension-M
- No model match -> confirm Custom-XL
- Set `evidence_module`, `evidence_field`, `evidence_snippet_ref`

Synthesize `solution` (1-2 sentences):
- Extension-M/L: `"Inherit model `{evidence_module}.{model}` via `_inherit`; add {field/method} to satisfy {brief req}."`
- Custom-XL: `"New module: build {brief description} with no existing Odoo base model to extend."`

Write `chunks/chunk-NNN.C.jsonl`.

### CHECKPOINT (after each chunk)

Merge A + B + C results into `chunks/chunk-NNN.merged.jsonl` (one obj/line, OVERWRITE - never append).
Rebuild `results.jsonl` by concatenating `chunk-*.merged.jsonl` files in chunk order.
**Do NOT append directly to `results.jsonl`** - append is not idempotent and would duplicate rows on re-run.

Then update `checkpoint.json` (LAST write of the chunk so a crash leaves the chunk re-runnable):
- Increment `processed` by chunk size
- Append chunk idx to `chunks_done`
- Update `last_completed_chunk`
- Mark per-req status as "done"

**Resume protocol:** On restart, read `checkpoint.json`. Jump to outer loop at `last_completed_chunk + 1`.
Items already "done" in `per_req` skip all phases. Re-running a chunk is idempotent.

### Phase D - DAG (post-all-chunks; main + optional per-cluster Opus subagent)

Runs ONCE after every chunk completes A+B+C. Reads finished `results.jsonl`, writes `dag.json` +
`dag.mermaid`, back-fills `dependencies` and `impl_phase`. Never re-runs classification or cost.

Full reasoning algorithm in `reference/dag-prompt.md`. Summary:

**D1 - Technical bootstrap (deterministic, parallel MCP <=3):**
For each unique module in `results.jsonl`:
```
module_inspect(name=<module>, method='dependencies', odoo_version='<version>')
```
Build module-adjacency map `{module -> [depends_on_modules]}`. Cache under `deps:<module>:<version>`.

**D2 - Cluster-cut:**
Assign each requirement `cluster_key = (module_family, business_domain)`. Target 8-20 clusters.
`module_family` = root module from classification (Custom items -> `"custom"`).
`business_domain` = LLM tag from `req_category`/`req_text`.

> **HEURISTIC BOUND (acceptance I6) - cluster size cap = 120 requirements/cluster.**
> Opus reasons over at most 120 items per cluster so the cluster req-list fits comfortably in
> one context window. If any cluster exceeds 120 items, SPLIT it deterministically before D3:
> sub-partition by secondary key (priority bucket Must/Should/Nice, then req_id range) into
> sub-clusters of <=120 items each, suffixing the cluster id (`account-Finance#1`, `account-Finance#2`, ...).
> Record the split in `dag.json.meta.cluster_caps`.
> This cap is the load-bearing reason Phase D stays tractable at thousands of items; it is
> documented identically in `reference/dag-prompt.md` and `reference/schema.md`.

**D3 - Intra-cluster reasoning (Opus, per cluster, <=120 items each):**
Reason about business-logic + data-flow edges INSIDE each cluster only.
Exact prompt in `reference/dag-prompt.md` (output: `{edges:[{from,to,type,reason}]}` JSON).

- Default: reason **inline** in main context, one cluster at a time.
- Optimization: when there are **>10 large clusters** (large = >=60 requirements, >=50% of the 120 cap),
  launch **one Opus subagent per cluster**. Subagent prompt MUST contain:
  `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
  Each subagent returns only its cluster's edges JSON (<=2k); main context merges them.

Work is `O(Σ k_c^2)` not `O(n^2)` - only intra-cluster pairs considered.

**D4 - Inter-cluster edges (rule-based + business-affinity for Custom):**

*Part A - Technical module deps (deterministic):*
```
for each (cluster_A, cluster_B):
    if module_family(cluster_A) depends_on module_family(cluster_B)   # from D1 map
        add ONE representative technical edge:
            from = earliest req (lowest req_id) in cluster_B
            to   = earliest req in cluster_A
        type = "technical", reason = "module <A> depends on module <B> (manifest)"
```

*Part B - Business-domain affinity for Custom clusters (LLM-reasoned, bounded):*
Custom items (no module in D1 map) produce zero technical inter-cluster edges. To fill these:
```
for each custom_cluster C:
    dependent_on_clusters = LLM_reason_business_affinity(C, all_non_custom_clusters)
    # Bound: emit at most ONE representative edge per (custom_cluster, source_cluster) pair.
    for each source_cluster S in dependent_on_clusters:
        add ONE representative business-affinity edge:
            from = earliest req in S
            to   = earliest req in C
        type = "business-logic"
        reason = "custom cluster '<C.id>' requires '<S.id>' domain established first: {reason}"
```
A custom cluster with no clear domain affinity emits zero edges (conservative, no fabrication).
Record D4-B edges with `type="business-logic"` and count in `dag.json.meta.custom_affinity_edges`.

**D5 - Kahn topological sort + cycle detection:**
```
in_degree[r] = number of incoming edges
queue = all r with in_degree 0
while queue: pop n -> append to order; for each successor m: in_degree[m]-=1; if 0 enqueue m
if len(order) != len(requirements): CYCLE detected
```
- Success: assign `phases` (each in-degree-0 peel layer = one phase). Write `impl_phase` back to every `results.jsonl` row.
- Cycle: identify members never emitted. Report in `dag.json.cycles` AND GATE E summary with three resolution options:
  1. **split** - break requirement into phase-A + phase-B parts
  2. **manual** - mark cycle members for manual implementor ordering
  3. **shared-prereq** - introduce a new shared prerequisite both depend on
  Still emit partial `topological_order` for the acyclic remainder.

**D6 - Critical path (EST/EFT over effort_days):**
```
EST[n] = max(EFT[p] for p in predecessors(n)), 0 if none
EFT[n] = EST[n] + effort_days_max[n]
critical_path = backtrace from max-EFT node
critical_path_days = max EFT
```

**Output artifacts** (write after GATE E approve):
- `dag.json` - `nodes`, `edges` (`{from,to,type,reason}`), `topological_order`, `phases`, `cycles`,
  `critical_path`, `critical_path_days`, `meta`. Schema: `reference/schema.md` §dag.json.
  Edge `type` ∈ `technical | business-logic | data-flow`.
- `dag.mermaid` - template and style in `reference/deliverable-templates.md` §dag.mermaid style.

**Do NOT use `impact_analysis`** in Phase D (reverse direction, wrong for forward planning).

**Standalone (OSM down):** if D1 `module_inspect` is unreachable, skip technical edges (D1/D4),
still run D2/D3/D5/D6, and flag `dag.json.meta.technical_edges = "skipped-osm-unreachable"`.

### Phase E - DELIVERABLES (pure write, 0 MCP calls)

**GATE E:** Present summary before writing deliverables:

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

When `Cycles detected > 0`, list each cycle's members and its three resolution options inline - never hide a cycle.

On `approve`, write ALL deliverables atomically:

1. **`results.jsonl`** - rebuild by concatenating `chunks/chunk-*.merged.jsonl` in order (one row per req_id,
   no duplicates). Back-fill `dependencies` and `impl_phase` from Phase D. Schema: `reference/schema.md` §results.

2. **`rtm.csv`** - convert results.jsonl to CSV. Header and column notes: `reference/deliverable-templates.md` §rtm.csv.

3. **`cost.json`** - project-level roll-up:
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
   # - this matches the cost-config.json `_note`).  Default = 1.0 (no adjustment).
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
   Output MUST include `risk_multiplier_applied` field (1.0 when no risk flag) for auditability.

4. **`dag.json`** + **`dag.mermaid`** - from Phase D. Schemas in `reference/schema.md` §dag.json and
   `reference/deliverable-templates.md` §dag.mermaid style.

5. **`report.md`** - executive summary. Full template: `reference/deliverable-templates.md` §report.md template.

## Hard rules

1. **NL-dispatch only:** When delegating to another skill (not expected in normal BRL flow),
   use a natural-language prompt. Do NOT use the Skill tool. Subagent launch is allowed for EXACTLY
   ONE purpose: Phase D DAG per-cluster reasoning workers (only when >10 large clusters). Any such
   subagent prompt MUST contain: `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
2. **Leaf subagents:** Phase D DAG cluster subagents must never spawn another subagent or invoke a skill.
3. **Public-repo safety:** Abstract customer labels only. Never write real company names, VND amounts,
   or internal pricing into any committable file. `.odoo-ai/brl/` is gitignored.
4. **No cost fabrication:** All cost figures from `cost-config.json` lookup. No LLM-generated numbers.
   If missing: stop and report "cost-config.json not found - cannot compute deterministic cost."
5. **OEEL-1 no-retry:** When check_module_exists returns a license notice, classify as
   Available-in-Viindoo and stop. Do NOT retry, do NOT call model_inspect on OEEL-1 modules.
6. **Context check:** Load `.odoo-ai/context.md` if present. Absent -> suggest `/odoo-onboarding`.
7. **Principal-branch-lock:** Read-only on the project repo. Only write to `.odoo-ai/`.
8. **Sequential outer:** Never fan-out chunks to parallel subagents. Inner <=3 MCP parallel per chunk
   is the only concurrency. Rationale: MCP-I/O-bound not CPU-bound; subagent fan-out risks OOM and
   rate-limit spikes (Mode A - see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`).

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

## Examples

> Full worked examples: `reference/deliverable-templates.md`. Summary dispatches below.

**Example 1 - Standard dispatch:**
Prompt: "800 requirements from a manufacturing client RFP - classify, cost, give us the RTM."
Action: Fire odoo-brl. GATE 0 plan: 800 items / 16 chunks / ~1600 MCP calls with cache. After approve,
runs Phase 0-A-B-C-D-E. Produces rtm.csv + cost.json + report.md in `.odoo-ai/brl/Customer-A-YYYYMMDD-<hex>/`.

**Example 2 - Resume after interruption:**
Prompt: "The BRL job from yesterday got interrupted at chunk 7 - resume?"
Action: Read checkpoint.json, find `last_completed_chunk=6`, resume at chunk 7. Report:
"Resuming from chunk 7/16. 350/800 requirements already classified."

**Example 3 - OSM down:**
Prompt: "Classify this 200-item BRL but the OSM server seems down."
Action: Degrade to unverified-llm. Mark all `risk_flag=osm-unreachable`. Complete cost.json + report.md.
Banner warning in report. Offer resume when server returns.

**Example 4 - Dependency sequencing + cycle:**
Prompt: "We have the classified BRL - now give us the implementation order and flag circular dependencies."
Action: Run Phase D. Module bootstrap, cluster-cut (~12 clusters, each <=120 items), intra-cluster Opus
reasoning, rule-based inter-cluster edges, Kahn topo-sort. If a cycle is found (e.g. REQ-0042 <-> REQ-0061),
report it explicitly in GATE E with three resolution options (split / manual / shared-prereq) and still
emit a partial order + dag.mermaid for the acyclic remainder.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.

**Hand off non-trivial items to design before coding.** If the classified set contains any
Extension-L or Custom-XL item, set `status: NEEDS_NEXT` and emit `next: odoo-solution-design`
so those items get a designed-and-approved solution before any code is written - pass the RTM/report
path and the L/XL `req_id` list as inputs (`{rtm: <path>, items: [REQ-…]}`, `risk_level: L1`).
Standard/Config/Extension-M items go straight to `odoo-coding`. All-small-items set -> BRL is terminal
(`status: DONE`, `next: []`).
