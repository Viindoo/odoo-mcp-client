# Intake - Notes for future maintainers

Background and design rationale for the intake router. Not needed at routing time - read it
when changing intake's structure, the routing table, or the harness wiring.

- **5-phase flow**: Phase 0 (Context, Detect & Clarify - closes the intent/purpose/outcomes
  gate + 4 detect branches) → **Phase R (Recon, read-only)** → Proposed Plan
  (context-rich) → Plan Mode (workitem + DAG + assignment) → Execute. Phase R dispatches
  ≤1-2 read-only agents (depth-1, no writes, no spawn) to survey current state before the plan
  is written.
- **Inventory discovery is hybrid, SSOT-respecting**: skill/agent/command existence + description
  come from runtime context; `output_mode` from the explicit `orchestration.<skill>.output_mode`
  field in `skill_tool_deps.json` (NOT a `spawn_class`/`stack` derivation - §4.7/§8.4); **`model_tier`
  is read from each candidate's own frontmatter (`model:`, absent ⇒ `inherit`) - NEVER copied into a registry**; and
  `effort` (S/M/L/XL) is a per-task property reasoned via the gap-analysis legend, also not
  registered.
- **Plan Mode Content Schema**: a `writes-files` Approach requires 3 blocks in the Plan-Mode
  plan - Workitem list (disjoint files), Dependency graph (DAG edge-types + topology, or one of
  the 4 wave topologies for few WIs), and Assignment (WI → skill/agent + model + effort + verify).
  A chat-only Approach skips Plan Mode (decision tree at the top of § Plan Mode). Full schema:
  `references/plan-mode-schema.md`.
- See `docs/reference/workflow-harness.md` for the full design rationale of the harness and the
  schemas borrowed here (wave WI brief, BRL DAG, wave topologies, gap-analysis effort legend).
- **Dispatch mechanism rationale** (why the Skill tool, not the Agent tool - § Dispatch mechanism
  keeps only the rule + table): a skill is not an agentType, so Agent-tool'ing a skill *name* fails
  outright; Agent-tool'ing the bare underlying agent instead would launch it but **bypass the
  skill's own orchestration** (topology decision, agent fan-out, synthesis - e.g.
  `odoo-code-review`'s module-count topology + fan-out + synthesis), forcing the read-and-imitate
  anti-pattern. A `spawner-agent` skill is `depth0-only` and must run in the depth-0 main context so
  the Skill tool can load it there and let it spawn its own agents (`odoo-code-reviewer`,
  `odoo-coder`, …) at depth-1. The depth-0 main agent IS allowed to call the Skill tool; the
  plugin's "never the Skill tool" rule binds depth≥1 subagents/fork-workers only (a subagent calling
  the Skill tool on a spawner skill would nest past the depth-2 ceiling).
- Routing table currently lists 43 entries (rows 1-13 = Phase A/B core; rows 14-21 = Phase B
  sales+marketing+engineering; rows 22-27 = Phase D commands; rows 28-32 = Phase E visual;
  rows 33-40 = Phase E+ BRL flagship + workflow domains + wave; rows 41-43 = solution-design,
  implement-feature, frontend-design). Update both the table AND `references/collision-zones.md`
  when adding entries.
- **Deep survey gate (opt-in)**: after the Proposed Plan, the gate offers `deep-survey` on
  *large* jobs. It is the heavy alternative to the light Phase R recon - `odoo-deep-survey` (a
  `depth0-only spawner-agent`, invoked via the Skill tool) fans out broad-haiku → narrow-sonnet →
  optional-opus workers and returns a `synthesis.md` that intake folds into the `Survey:` field and
  a re-proposed plan. It is the ONE `writes-files` skill intake dispatches WITHOUT Plan Mode: it
  writes only `.odoo-ai/survey/` analysis (not the routed deliverable) and the `deep-survey` keyword
  is itself the human gate (same rationale as Hard rule 1 letting intake write planning artifacts).
  It is deliberately NOT a routing-table row - it is never intent-routed, only opt-in. The
  re-proposed gate drops `deep-survey` so the survey runs at most once.
- Trigger description optimization is via `/skill-creator` Mode 5 (`run_loop.py`) with a
  20-query trigger eval set.
- Eval set (`evals/evals.json`) is descriptive - not graded. Use `/skill-creator` Mode 5 +
  `run_loop.py` for a graded trigger accuracy score.
- This skill carries the standard `odoo-` prefix as `odoo-intake`, consistent with all other skills in this plugin. The unprefixed `intake` namespace is intentionally reserved for a future domain-agnostic front door (general ERP, strategic planning, etc.) that may route to `odoo-intake` when it detects Odoo intent - keeping the Odoo-specific and domain-agnostic responsibilities cleanly separated.
