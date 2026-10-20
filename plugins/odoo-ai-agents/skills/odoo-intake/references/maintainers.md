# Intake - Notes for future maintainers

Human reference for the intake router; read it when changing intake's structure, the routing
table, or the harness wiring. Not loaded at routing time.

- **Flow**: Phase 0 (Context, Detect & Clarify - closes the intent/purpose/outcomes gate, 3 detect
  branches) -> Phase R (Recon, read-only) -> approach question (text, only while unsettled) ->
  hand-off to the plan owner, whose Plan-Mode approval is the request's one gate -> execute.
- **Inventory discovery**: skill/agent/command existence and description come from runtime context;
  `output_mode` from `orchestration.<skill>.output_mode` in `skill_tool_deps.json`; `model_tier`
  from each candidate's own frontmatter (`model:`, absent = `inherit`), never copied into a
  registry; `effort` is a per-task property owned by `odoo-gap-analysis`, also not registered.
- **Plan schema, run rules, node brief, run file**: `references/plan-mode-schema.md`. The BRL DAG
  and the gap-analysis effort legend live in their own skills.
- **Dispatch mechanism**: a skill is not an agentType, so launching an agent by a skill name fails;
  launching the bare underlying agent bypasses the skill's own orchestration (topology, fan-out,
  synthesis). A `spawner-agent` skill must run in the main context so the Skill tool loads it
  there and it can launch subagents. The main agent MAY call the Skill tool; subagents never do.
- **Routing table**: 63 rows. Rows 1-13 core specialists; 14-21 sales, marketing and engineering;
  22-27 commands; 28-32 visual; 33-40 BRL, workflows and parallel delivery (row 40 routes to
  `odoo-planning`); 41-49 solution-design, implement-feature, frontend-design, doc-illustration,
  git-rebase, modules-upgrade, acceptance, planning, pr-monitoring; 50-54 icon-design,
  doc-feature-map, doc-site, module-packaging, docs-only plan (TARGET `both`); 55-63 perf-audit,
  security-audit, data-migration, customer-health, i18n, pricing-proposal, rfp-response,
  test-writing, instance. `odoo-deep-survey` is not a row (opt-in only) and `workflow-chaining` is
  internal machinery. Update the table AND `references/collision-zones.md` together.
- **Deep survey (opt-in)**: the approach question offers it on large jobs as a SEPARATE line, never a
  gate keyword; the user opts in with `refine: deep-survey` (the `refine:` feedback text).
  `odoo-deep-survey` (a `spawner-agent`, invoked via the Skill tool) returns a `synthesis.md` that
  intake carries in the hand-off brief; it writes only under `<SHARE_DIR>/survey/`. The sharpened
  approach question drops the offer so the survey runs at most once.
- **Naming**: the unprefixed `intake` namespace is reserved for a future domain-agnostic front door
  that may route to `odoo-intake` on detecting Odoo intent.
