# BRL Deliverable Templates

> On-demand reference for `odoo-brl` Phase E. Load when writing Phase E deliverables.

---

## report.md template

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

---

## rtm.csv header

```
req_id,req_text,req_category,priority,classification,module,edition,effort_tier,effort_days_min,effort_days_max,cost_usd_min,cost_usd_max,solution,dependencies,impl_phase,evidence_module,evidence_field,risk_flag,status,notes
```

`dependencies` column: pipe-joined (`REQ-0010|REQ-0015`) to remain CSV-safe.

## dag.mermaid style

`flowchart TD`, requirements grouped by `subgraph` by `impl_phase`.
Node label: `REQ-ID\n<short req_text>\n<effort_tier> | <days>`.
Fill by classification:
- CE = green (`fill:#d8f0d8,stroke:#2a2`)
- EE = yellow (`fill:#ffe,stroke:#cc0`)
- Viindoo = purple (`fill:#e8d,stroke:#808`)
- Custom = red (`fill:#f88,stroke:#c00`)

See also `dag-prompt.md` §Mermaid format for the full style block.
