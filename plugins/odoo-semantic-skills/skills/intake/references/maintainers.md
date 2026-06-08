# Intake — Notes for future maintainers

Background and design rationale for the intake router. Not needed at routing time — read it
when changing intake's structure, the routing table, or the harness wiring.

- **5-phase flow**: Phase 0 (Context, Detect & Clarify — closes the intent/purpose/outcomes
  gate + 4 detect branches) → **Phase R (Recon, read-only)** → Proposed Plan
  (context-rich) → Plan Mode (workitem + DAG + assignment) → Execute. Phase R dispatches
  ≤1–2 read-only agents (depth-1, no writes, no spawn) to survey current state before the plan
  is written.
- **Inventory discovery is hybrid, SSOT-respecting**: skill/agent/command existence + description
  come from runtime context; `output_mode` from the explicit `orchestration.<skill>.output_mode`
  field in `skill_tool_deps.json` (NOT a `spawn_class`/`stack` derivation — §4.7/§8.4); **`model_tier`
  is read from each candidate's own frontmatter (`model:`, absent ⇒ `inherit`) — NEVER copied into a registry**; and
  `effort` (S/M/L/XL) is a per-task property reasoned via the gap-analysis legend, also not
  registered.
- **Plan Mode Content Schema**: a `writes-files` Approach requires 3 blocks in the Plan-Mode
  plan — Workitem list (disjoint files), Dependency graph (DAG edge-types + topology, or one of
  the 4 wave topologies for few WIs), and Assignment (WI → skill/agent + model + effort + verify).
  A chat-only Approach skips Plan Mode (decision tree at the top of § Plan Mode). Full schema:
  `references/plan-mode-schema.md`.
- See `docs/reference/workflow-harness.md` for the full design rationale of the harness and the
  schemas borrowed here (wave WI brief, BRL DAG, wave topologies, gap-analysis effort legend).
- Routing table currently lists 43 entries (rows 1-13 = Phase A/B core; rows 14-21 = Phase B
  sales+marketing+engineering; rows 22-27 = Phase D commands; rows 28-32 = Phase E visual;
  rows 33-40 = Phase E+ BRL flagship + workflow domains + wave; rows 41-43 = solution-design,
  implement-feature, frontend-design). Update both the table AND `references/collision-zones.md`
  when adding entries.
- Trigger description optimization is via `/skill-creator` Mode 5 (`run_loop.py`) with a
  20-query trigger eval set.
- Eval set (`evals/evals.json`) is descriptive — not graded. Use `/skill-creator` Mode 5 +
  `run_loop.py` for a graded trigger accuracy score.
- The `intake` name is intentionally non-Odoo-prefixed: this front door is future-proof for
  non-Odoo domains (general ERP, strategic planning, etc.) without renaming.
