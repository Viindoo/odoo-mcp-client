# BRL Artifact Schema

> SSOT for all artifacts written by the `odoo-brl` skill.
> Source of truth for artifact layout: `docs/reference/workflow-harness.md` §3 (BRL job schema).
> This file documents field-level detail and JSON schema for each artifact type.

---

## 1. Directory layout

All BRL artifacts live under `.odoo-ai/brl/<job-id>/`. The `.odoo-ai/` directory is gitignored
by the `odoo-onboard` skill so no artifact is ever committed to the project repo.

`<job-id>` format: `<CUSTOMER_LABEL>-<YYYYMMDD>-<4hex>`
Example: `Customer-A-20260531-9f3a`

CUSTOMER_LABEL MUST be abstract (Customer-A, Customer-B, etc.). Never use a real company name.

```
.odoo-ai/brl/<job-id>/
  manifest.json           # immutable job metadata (written at Phase 0, never mutated after Gate 0)
  input.jsonl             # 1 line per requirement: {req_id, req_text, req_category?, priority?}
  chunkplan.json          # chunk split plan
  checkpoint.json         # machine resume state (updated after each chunk)
  chunks/
    chunk-000.A.jsonl       # classify output for chunk 0 (Phase A)
    chunk-000.B.jsonl       # cost output for chunk 0 (Phase B)
    chunk-000.C.jsonl       # evidence output for chunk 0 (Phase C)
    chunk-000.merged.jsonl  # A+B+C merged for chunk 0 (overwrite per chunk; idempotent)
    chunk-001.A.jsonl
    ...
  cache.json              # module-verdict cache - avoids duplicate MCP calls
  results.jsonl           # RTM SSOT (1 obj/line) - REBUILT by concatenating chunk-*.merged.jsonl
                          # in order (never appended directly), finalized at Phase E
  rtm.csv                 # consultant export (Excel-ready)
  cost.json               # project-level cost roll-up
  report.md               # executive human-readable summary
  dag.json                # (Phase D) dependency adjacency + topo order + critical path
  dag.mermaid             # (Phase D) flowchart by implementation phase
  errors.jsonl            # per-item failures - informational, non-blocking
```

---

## 2. manifest.json

Written once at Phase 0 before Gate 0. Never mutated after gate approval.

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "created_at": "2026-05-31T10:00:00Z",
  "customer_label": "Customer-A",
  "odoo_version": "17.0",
  "profiles": {
    "odoo": "odoo_17",
    "viindoo": "viindoo-internal"
  },
  "total_reqs": 1000,
  "chunk_size": 50,
  "cost_config_ref": "cost-config.json@v1",
  "rate_region": "vn",
  "risk_profile": "medium",
  "schema_version": "brl/1.0"
}
```

| Field | Type | Description |
|---|---|---|
| `job_id` | string | Unique identifier for this BRL job |
| `created_at` | ISO 8601 | Job creation timestamp |
| `customer_label` | string | Abstract customer label (never real name) |
| `odoo_version` | string | Odoo version string (e.g. "17.0", "18.0") |
| `profiles.odoo` | string | OSM profile name for CE/EE classification |
| `profiles.viindoo` | string | OSM profile name for Viindoo classification |
| `total_reqs` | int | Total number of requirements in BRL |
| `chunk_size` | int | Items per chunk (default 50) |
| `cost_config_ref` | string | Cost config file + version used |
| `rate_region` | string | Rate card region key (e.g. "vn") |
| `risk_profile` | string | Risk level for contingency: low/medium/high/very_high |
| `schema_version` | string | BRL schema version for forward compatibility |

---

## 3. checkpoint.json

Updated after every completed chunk. Resume reads `last_completed_chunk` and enters
the outer loop at `last_completed_chunk + 1`. Re-running a chunk is idempotent
(overwrites `chunk-NNN.*.jsonl` files).

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "phase": "classify",
  "processed": 350,
  "total": 1000,
  "last_completed_chunk": 6,
  "chunks_done": [0, 1, 2, 3, 4, 5, 6],
  "session_pinned_at": "2026-05-31T10:00:00Z",
  "per_req": {
    "REQ-0351": "pending"
  }
}
```

`phase` values (lifecycle): `ingest | classify | dag | deliver | done`

`session_pinned_at`: Used for 24h idle-TTL detection. The pin is keyed per live MCP
session and also resets on a server restart, so if `now - session_pinned_at > 23h`
OR any MCP call returns "no active version" (TTL lapse or server restart), re-run
bootstrap and update this field.

`per_req`: Sparse dict - only in-flight or error items appear. Completed items are omitted
to keep the file small. Values: `"done" | "pending" | "error"`.

---

## 4. input.jsonl

One JSON object per line. Written at Phase 0. Never modified after Gate 0.

```json
{"req_id": "REQ-0001", "req_text": "Multi-level invoice approval workflow", "req_category": "Functional", "priority": "Must-have"}
{"req_id": "REQ-0002", "req_text": "Real-time inventory reporting by warehouse", "req_category": "Functional", "priority": "Should-have"}
```

| Field | Required | Description |
|---|---|---|
| `req_id` | yes | Stable ID: REQ-0001 ... REQ-N (zero-padded) |
| `req_text` | yes | Original requirement text (verbatim from BRL input) |
| `req_category` | no | Functional / Technical / Data / Integration / Non-functional |
| `priority` | no | Must-have / Should-have / Nice-to-have / MoSCoW labels |

---

## 5. chunk-NNN.A.jsonl (Phase A output)

```json
{
  "req_id": "REQ-0042",
  "candidate_modules": ["account"],
  "classification": "Available-in-Odoo-CE",
  "module": "account",
  "edition": "CE",
  "classification_source": "mcp-verified",
  "cache_hit": false,
  "risk_flag": null
}
```

`classification_source` values: `mcp-verified | cache-hit | unverified-llm | osm-error`

---

## 6. chunk-NNN.B.jsonl (Phase B output)

```json
{
  "req_id": "REQ-0042",
  "effort_tier": "Extension-M",
  "effort_days_min": 1,
  "effort_days_max": 3,
  "effort_phase": "Config & Development",
  "cost_usd_min": 300,
  "cost_usd_max": 900,
  "rate_used": "blended_vn",
  "rate_usd_per_day": 300
}
```

---

## 7. chunk-NNN.C.jsonl (Phase C output)

Only written for Extension and Custom items. Standard/Config items have no Phase C entry.

```json
{
  "req_id": "REQ-0042",
  "evidence_module": "account",
  "evidence_field": "account.move:invoice_line_ids",
  "evidence_snippet_ref": "chunks/chunk-000.C.jsonl#L3",
  "extension_point_confirmed": true,
  "effort_tier_revised": "Extension-M"
}
```

`effort_tier_revised`: If Phase C evidence changes the initial B-phase tier, this field
holds the revised value. The chunk CHECKPOINT merger uses this to update `results.jsonl`.

---

## 8. results.jsonl (RTM SSOT)

One object per requirement. Final merged output of A + B + C (+ D when implemented).
Rebuilt by concatenating `chunks/chunk-*.merged.jsonl` in chunk order after every chunk
(never appended directly — append would duplicate rows on a chunk re-run). Finalized at Phase E.

```json
{
  "req_id": "REQ-0042",
  "req_text": "Three-level invoice approval",
  "req_category": "Functional",
  "priority": "Must-have",
  "classification": "Available-in-Odoo-CE",
  "module": "account",
  "edition": "CE",
  "effort_tier": "Extension-M",
  "effort_days_min": 1,
  "effort_days_max": 3,
  "effort_phase": "Config & Development",
  "cost_usd_min": 300,
  "cost_usd_max": 900,
  "solution": "Inherit account.move, add approval_state field and multi-level approval logic via approval_ids Many2many.",
  "risk_flag": null,
  "evidence_module": "account",
  "evidence_field": "account.move:state",
  "evidence_snippet_ref": "chunks/chunk-000.C.jsonl#L12",
  "dependencies": [],
  "impl_phase": null,
  "status": "Not started",
  "notes": ""
}
```

`solution`: 1-2 sentence implementation description generated in Phase A/C. Pattern per class:
- `Available-in-Odoo-CE/EE`: "Activate module `<module>` + <specific config step>."
- `Available-in-Viindoo`: "Activate Viindoo module `<module>`; <OEEL-1 note if applicable>."
- `Extension-M/L`: "Inherit model `<model>`, add <field/method> via `_inherit`."
- `Custom-XL`: "New module: <short description of what to build>."

`classification` enum: `Available-in-Odoo-CE | Available-in-Odoo-EE | Available-in-Viindoo | Custom`

`effort_tier` enum: `Standard | Config | Extension-M | Extension-L | Custom-XL`

`dependencies`: list of req_ids this requirement directly depends on (incoming edge sources
from Phase D), e.g. `["REQ-0010", "REQ-0015"]`. Empty `[]` if the requirement has no
predecessors. Back-filled by Phase D before Phase E finalizes `results.jsonl`.

`impl_phase`: integer phase number from the Kahn phase assignment (1 = foundation). Set by
Phase D. `null` only if Phase D has not yet run (e.g. a mid-pipeline checkpoint inspection).

---

## 9. rtm.csv header

```
req_id,req_text,req_category,priority,classification,module,edition,effort_tier,effort_days_min,effort_days_max,cost_usd_min,cost_usd_max,solution,dependencies,impl_phase,evidence_module,evidence_field,risk_flag,status,notes
```

`dependencies` column: pipe-joined (`REQ-0010|REQ-0015`) to remain CSV-safe (no commas).
`solution` column: 1-2 sentence implementation description (see §results.jsonl for pattern per class).

---

## 10. cost.json

Project-level cost roll-up. All numbers trace to `cost-config.json` via the formula
via the formula in `docs/reference/workflow-harness.md`.

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "computed_at": "2026-05-31T12:00:00Z",
  "classification_mix": {
    "CE": 0.55,
    "EE": 0.08,
    "Viindoo": 0.10,
    "Custom": 0.27
  },
  "base_effort_days": {"min": 210.5, "max": 612.0},
  "customization_coefficient": 1.3,
  "custom_item_pct": 0.27,
  "unique_modules": 15,
  "cross_module_factor": 0.96,
  "project_effort_days": {"min": 536.4, "max": 1559.4},
  "blended_rate_usd": 300,
  "risk_profile": "medium",
  "contingency_pct": 0.15,
  "budget_usd": {"min": 185042, "max": 537985},
  "phase_breakdown_usd": {
    "discovery_blueprint": 64558,
    "config_development": 188295,
    "data_migration": 107597,
    "testing_uat": 64558,
    "training": 43039,
    "project_management": 26899,
    "golive_hypercare": 43039
  },
  "annual_maintenance_usd": 53798,
  "cost_config_ref": "cost-config.json@v1",
  "formula_trace": "project_effort = 612 * 1.3 * (1 + 0.96) = 1559.4 days; budget_max = 1559.4 * 300 * 1.15 = 537985; phase_breakdown[p] = budget_max * phase_distribution[p] (7 lines sum to 537985)"
}
```

**Invariant:** `sum(phase_breakdown_usd.values()) == budget_usd.max`. `phase_distribution`
in `cost-config.json` sums to exactly 1.0, so the breakdown reconciles to the final budget.
Contingency is applied ONCE (the `(1 + contingency_pct)` factor in `budget_usd`); it is NOT a
separate phase line — listing it twice would double-count. `annual_maintenance_usd` is a
separate forward-looking figure (`budget_max * annual_maintenance_pct`), not part of the budget.

---

## 11. errors.jsonl

Informational only - does not block the batch. Written throughout the pipeline.

```json
{"req_id": "REQ-0099", "type": "license_restricted", "module": "some_ee_module", "message": "OEEL-1 restricted detail - classified as Available-in-Viindoo without field-level evidence"}
{"req_id": "REQ-0150", "type": "mcp_error", "message": "check_module_exists failed after 3 retries - marked osm-error"}
{"req_id": "REQ-0201", "type": "module_mapping_uncertain", "message": "A0 LLM produced 0 confident candidates; find_examples also inconclusive - classified Custom tentative"}
```

`type` values: `license_restricted | mcp_error | module_mapping_uncertain | osm_unreachable`

---

## 12. dag.json (Phase D)

Dependency adjacency written by Phase D after all chunks finish. The reasoning algorithm
(cluster-cut + Kahn + EST/EFT) is in `dag-prompt.md`. See `docs/reference/workflow-harness.md` for the overall architecture.

```json
{
  "nodes": [
    {"id": "REQ-0001", "label": "Chart of Accounts", "module": "account",
     "classification": "Available-in-Odoo-CE", "effort_tier": "Config",
     "effort_days": 1, "impl_phase": 1},
    {"id": "REQ-0042", "label": "3-Level Approval", "module": "account",
     "classification": "Custom", "effort_tier": "Custom-XL",
     "effort_days": 17, "impl_phase": 2}
  ],
  "edges": [
    {
      "from": "REQ-0001",
      "to": "REQ-0042",
      "type": "data-flow",
      "reason": "approval flow requires chart-of-accounts setup first"
    }
  ],
  "topological_order": ["REQ-0001", "REQ-0042"],
  "phases": {"1": ["REQ-0001"], "2": ["REQ-0042"]},
  "cycles": [],
  "critical_path": ["REQ-0001", "REQ-0042"],
  "critical_path_days": 18,
  "meta": {
    "clusters": ["account-Finance", "sale-Sales", "stock-Inventory"],
    "cluster_caps": [
      {"cluster": "account-Finance", "size": 132, "split_into": ["account-Finance#1", "account-Finance#2"], "cap": 120}
    ],
    "technical_edges": "from-module-deps",
    "cluster_size_cap": 120
  }
}
```

| Field | Type | Description |
|---|---|---|
| `nodes[]` | array | One per requirement: `id`, `label` (short req_text), `module`, `classification`, `effort_tier`, `effort_days` (= effort_days_max, used as node weight), `impl_phase` |
| `edges[]` | array | Directed `from -> to` (from must complete before to). Each has `type` + `reason` |
| `edges[].type` | enum | `technical \| business-logic \| data-flow` |
| `topological_order` | array | Implementation sequence from Kahn's algorithm (acyclic remainder if a cycle exists) |
| `phases` | object | `{phase_number: [req_ids]}` — in-degree-0 peel layers; drives `impl_phase` |
| `cycles` | array | Cycle members when a circular dependency is detected (empty `[]` for a valid DAG). Each entry: `{members: [req_ids], resolution_options: ["split","manual","shared-prereq"]}` |
| `critical_path` | array | Longest EST/EFT path (req_ids) |
| `critical_path_days` | number | Sum of `effort_days` along the critical path (= max EFT) |
| `meta.clusters` | array | Cluster ids used in D2 |
| `meta.cluster_caps` | array | Records any cluster that exceeded the 120-item cap and was split |
| `meta.cluster_size_cap` | int | Heuristic bound (120) — documented identically in `dag-prompt.md` and SKILL.md Phase D |
| `meta.technical_edges` | string | `from-module-deps` normally; `skipped-osm-unreachable` in standalone fallback |
| `meta.custom_affinity_edges` | int | Count of inter-cluster edges added via D4-B business-domain affinity heuristic for Custom clusters (0 if no Custom items produced cross-cluster edges) |

**Cycle example** (`cycles` non-empty):
```json
{
  "cycles": [
    {"members": ["REQ-0042", "REQ-0061"],
     "resolution_options": ["split", "manual", "shared-prereq"]}
  ]
}
```
A cycle is a REPORTED outcome (surfaced in GATE E + report.md), never a silent edge-drop or
crash. `topological_order` still covers the acyclic remainder.

Edge `type` values: `technical | business-logic | data-flow`

---

## References

- `docs/reference/workflow-harness.md` §3 — BRL job schema SSOT
- `cost-config.json` — effort lookup + rate card SSOT
- `docs/reference/workflow-harness.md` — harness architecture and BRL schema SSOT
