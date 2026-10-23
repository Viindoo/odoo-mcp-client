# odoo-brl - phase procedure

The full wording of the phases `SKILL.md` § Instructions summarises; `SKILL.md` names the section it needs.

### Seed + cross-check from a prior gap-analysis

### Seed + cross-check from a prior gap-analysis (optional)

At Phase 0, glob `<SHARE_DIR>/gap-analysis/*/gap-matrix.jsonl` (newest dir wins). If one
exists, BRL MAY consume it as a PRIOR - never ground truth - to seed and cross-check the fit-gap of
its RTM. BRL only reads the artifact; it never delegates to the gap-analyzer:

- **Seed:** match each BRL `req_id` / requirement text to a gap-matrix row; prefill
  the candidate `module` (warm `cache.json`) and map the gap row's `classification`
  (`standard|config|extension|custom`) onto BRL's `effort_tier` family
  (Standard / Config / Extension-M|L / Custom-XL). A gap row's `module` / `coverage` is a candidate,
  not a verdict.
- **Cross-check (OSM-first still wins):** Phase A re-grounds every seeded item per the § OSM-First
  Grounding Contract. The double-profile `check_module_exists` (A2) always resolves BRL's 4-way
  edition split (Available-in-Odoo-CE / -EE / -Viindoo / Custom) - the gap-matrix cannot carry it. On
  a divergence, BRL's OSM-grounded verdict wins; record it in `notes`
  (`gap-matrix said <x>; OSM confirms <y>`). A `grounded: unknown` gap row is treated as unseeded.

**Stay format-compatible with gap-analysis.** Keep BRL's per-req rows carrying the keys `req_id`,
`requirement`, `module`, an effort axis, `notes`, and keep the § Continuation Contract handoff to
`odoo-solution-design` in the shape of a gap-analysis handoff (`{<deliverable path>, items: [REQ-…]}`).

### Phase A - CLASSIFY

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

### Phase B - COST

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

### Phase C - EVIDENCE

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

### Phase D - DAG

### Phase D - DAG (post-all-chunks; main, optional per-cluster subagent)

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

Never cap or split a cluster by size.

**D3 - Intra-cluster reasoning (per cluster):**
Reason about business-logic + data-flow edges INSIDE each cluster only.
Exact prompt in `reference/dag-prompt.md` (output: `{edges:[{from,to,type,reason}]}` JSON).

- Default: reason **inline** in main context, one cluster at a time.
- Only under Hard rule 1's condition: launch **one subagent per cluster** using CHP Tier-B
  `subagent_type: "fork"` (`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B).
  The cluster JSON snapshot passed by prompt is the authoritative input for that worker. If
  `subagent_type: "fork"` is unavailable, dispatch a fresh `general-purpose` spawn with an explicit
  brief containing the cluster JSON (Tier C). Write the worklog regardless of tier.
  Model per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection.
  Fill the cluster subagent's prompt from the caller-side skeleton in
  `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the
  target agent's family delta; never inline that file verbatim into a hard-leaf brief.
  Subagent prompt MUST contain: `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write/Bash.`
  Each subagent returns only its cluster's edges JSON (<=2k); main context merges them.

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
- Cycle: identify members never emitted. Report in `dag.json.cycles` AND the report.md summary with three resolution options:
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

**Output artifacts** (written in Phase E):
- `dag.json` - `nodes`, `edges` (`{from,to,type,reason}`), `topological_order`, `phases`, `cycles`,
  `critical_path`, `critical_path_days`, `meta`. Schema: `reference/schema.md` §dag.json.
  Edge `type` ∈ `technical | business-logic | data-flow`.
- `dag.mermaid` - template and style in `reference/deliverable-templates.md` §dag.mermaid style.

**Do NOT use `impact_analysis`** in Phase D.

OSM down: § Standalone-first fallback item 3.

### Phase E - DELIVERABLES

### Phase E - DELIVERABLES (pure write, 0 MCP calls)

When the DAG has cycles, list each cycle's members and its three resolution options in `report.md` - never hide a cycle.

Write ALL deliverables atomically:

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
   # risk factors apply, use the SINGLE highest factor (never multiply factors together).
   # Default = 1.0 (no adjustment).
   risk_multiplier = max(risk_multipliers[f] for f in applicable_risk_flags) or 1.0

   project_effort_min = base_effort_min * customization_coefficient * (1 + cross_module_factor) * risk_multiplier
   project_effort_max = base_effort_max * customization_coefficient * (1 + cross_module_factor) * risk_multiplier
   budget_min = project_effort_min * blended_rate * (1 + contingency[risk_profile])
   budget_max = project_effort_max * blended_rate * (1 + contingency[risk_profile])
   # phase_breakdown partitions the FINAL budget (contingency already included).
   # phase_distribution sums to exactly 1.0 -> the 7 lines reconcile to budget_max.
   # Do NOT add a separate contingency line.
   phase_breakdown[phase] = budget_max * phase_distribution[phase]  (7 lines, sum == budget_max)
   annual_maintenance = budget_max * annual_maintenance_pct   # 0.10 from config
   ```
   Output MUST include `risk_multiplier_applied` field (1.0 when no risk flag) for auditability.

4. **`dag.json`** + **`dag.mermaid`** - from Phase D. Schemas in `reference/schema.md` §dag.json and
   `reference/deliverable-templates.md` §dag.mermaid style.

5. **`report.md`** - executive summary. Full template: `reference/deliverable-templates.md` §report.md template.
