# Orchestration Map (GENERATED — do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning/main agent which skills spawn subagents (so it never forbids a
> legitimate spawn) and which are depth0-only (so a subagent never illegally invokes them).

| Skill | spawn_class | depth_policy | stack | instance | spawns |
|-------|-------------|--------------|-------|----------|--------|
| `intake` | orchestrator-nl | depth0-only | none | — | — |
| `odoo-addon-diff` | leaf | any-depth | none | — | — |
| `odoo-brl` | spawner-agent | depth0-only | none | — | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | any-depth | none | — | — |
| `odoo-capability-proof` | leaf | any-depth | none | — | — |
| `odoo-code-reviewer` | spawner-agent | depth0-only | fullstack | — | odoo-code-reviewer |
| `odoo-coder` | spawner-agent | depth0-only | backend | — | odoo-coder |
| `odoo-competitive-brief` | leaf | any-depth | none | — | — |
| `odoo-content-draft` | leaf | any-depth | none | — | — |
| `odoo-customization-inventory` | leaf | any-depth | none | — | — |
| `odoo-deal-followup` | leaf | any-depth | none | — | — |
| `odoo-demo-recorder` | leaf | any-depth | none | — | — |
| `odoo-deploy-checklist` | leaf | any-depth | none | yes | — |
| `odoo-deprecation-audit` | leaf | any-depth | backend | — | — |
| `odoo-discovery-summarize` | leaf | any-depth | none | — | — |
| `odoo-feature-check` | leaf | any-depth | none | — | — |
| `odoo-feature-highlights` | leaf | any-depth | none | — | — |
| `odoo-frontend-coder` | leaf | any-depth | frontend | — | — |
| `odoo-gap-analysis` | leaf | any-depth | none | — | — |
| `odoo-objection-handler` | leaf | any-depth | none | — | — |
| `odoo-onboard` | leaf | any-depth | none | — | — |
| `odoo-override-finder` | leaf | any-depth | backend | — | — |
| `odoo-qa-suite` | orchestrator-nl | any-depth | none | yes | — |
| `odoo-risk-overview` | leaf | any-depth | none | — | — |
| `odoo-support-triage` | orchestrator-nl | any-depth | none | — | — |
| `odoo-ui-debug` | leaf | any-depth | frontend | — | — |
| `odoo-ui-reviewer` | spawner-agent | depth0-only | frontend | — | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | any-depth | backend | — | — |
| `odoo-visual-regression` | leaf | any-depth | frontend | — | — |
| `wave` | spawner-wave | depth0-only | none | yes | (per-WI leaf workers over worktrees) |
| `workflow-runner` | orchestrator-nl | depth0-only | none | — | — |

## Legend

- **spawn_class** — `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch, no Agent-tool spawn) · `spawner-agent` (dispatches a named
  agent, depth 0→1) · `spawner-wave` (worktree fan-out, depth 0→1→2).
- **depth_policy** — `depth0-only` skills must be invoked only from the main agent,
  never from inside a subagent (nesting-crash guard). `any-depth` is safe to NL-dispatch.
- **stack** — drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

