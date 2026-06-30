# Intake - Notes for future maintainers

Background and design rationale for the intake router. Not needed at routing time - read it
when changing intake's structure, the routing table, or the harness wiring.

- **5-phase flow**: Phase 0 (Context, Detect & Clarify - closes the intent/purpose/outcomes
  gate + 4 detect branches) → **Phase R (Recon, read-only)** → Proposed Plan
  (context-rich) → Plan Mode (workitem + DAG + assignment) → Execute. Phase R dispatches
  ≤1-2 read-only agents (leaf subagents, no writes, no spawn) to survey current state before the plan
  is written.
- **Inventory discovery is hybrid, SSOT-respecting**: skill/agent/command existence + description
  come from runtime context; `output_mode` from the explicit `orchestration.<skill>.output_mode`
  field in `skill_tool_deps.json` (NOT a `spawn_class`/`stack` derivation - §4.7/§8.4); **`model_tier`
  is read from each candidate's own frontmatter (`model:`, absent ⇒ `inherit`) - NEVER copied into a registry**; and
  `effort` (S/M/L/XL) is a per-task property reasoned via the gap-analysis legend, also not
  registered.
- **Plan Mode Content Schema**: a `writes-files` Approach requires 3 blocks in the Plan-Mode
  plan - Workitem list (disjoint files), Dependency graph (DAG edge-types + topology, or one of
  the 4 wave-batch topologies for few WIs), and Assignment (WI → skill/agent + effort + est_agents
  (advisory) + verify - model/count owned by the dispatched skill at runtime, never bound by the plan).
  A chat-only Approach skips Plan Mode (decision tree at the top of § Plan Mode). Full schema:
  `references/plan-mode-schema.md`.
- See `docs/reference/workflow-harness.md` for the full design rationale of the harness and the
  schemas borrowed here (odoo-wave WI brief, BRL DAG, wave-batch topologies, gap-analysis effort legend).
- **Dispatch mechanism rationale** (why the Skill tool, not the Agent tool - § Dispatch mechanism
  keeps only the rule + table): a skill is not an agentType, so Agent-tool'ing a skill *name* fails;
  Agent-tool'ing the bare underlying agent launches it but **bypasses the skill's own orchestration**
  (topology, fan-out, synthesis - e.g. `odoo-code-review`'s module-count topology + fan-out +
  synthesis), forcing the read-and-imitate anti-pattern. A `spawner-agent` skill must run in the main
  context so the Skill tool loads it there and lets it launch subagents (`odoo-code-reviewer`,
  `odoo-coder`, …). The main agent MAY call the Skill tool; the "never the Skill tool" rule binds
  subagents/fork-workers only (a subagent calling it on a spawner skill creates uncontrolled nesting).
- Routing table currently lists 49 entries (rows 1-13 = Phase A/B core; rows 14-21 = Phase B
  sales+marketing+engineering; rows 22-27 = Phase D commands; rows 28-32 = Phase E visual;
  rows 33-40 = Phase E+ BRL flagship + workflow domains + parallel-WI delivery (row 40 -> `odoo-planning`;
  the `odoo-wave` executor it plans for is internal, `user-invocable: false`); rows 41-49 =
  solution-design, implement-feature, frontend-design, doc-illustration, git-rebase, modules-upgrade,
  acceptance, planning, pr-monitoring). Update both the table AND `references/collision-zones.md`
  when adding entries.
- **Deep survey gate (opt-in)**: after the Proposed Plan, the gate offers `deep-survey` on
  *large* jobs - the heavy alternative to light Phase R recon. `odoo-deep-survey` (a `spawner-agent`,
  invoked via the Skill tool from the main context) fans out broad-haiku → narrow-sonnet →
  optional-opus workers and returns a `synthesis.md` that intake folds into the `Survey:` field and
  a re-proposed plan. It is the ONE `writes-files` skill intake dispatches WITHOUT Plan Mode: it
  writes only `.odoo-ai/survey/` analysis (not the routed deliverable), and the `deep-survey` keyword
  is itself the human gate (same rationale as Hard rule 1 letting intake write planning artifacts).
  Deliberately NOT a routing-table row - never intent-routed, only opt-in. The re-proposed gate
  drops `deep-survey` so the survey runs at most once.
- This skill carries the standard `odoo-` prefix as `odoo-intake`. The unprefixed `intake` namespace is reserved for a future domain-agnostic front door (general ERP, strategy, etc.) that may route to `odoo-intake` on detecting Odoo intent - keeping Odoo-specific and domain-agnostic responsibilities separate.
