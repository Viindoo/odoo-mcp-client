# Orchestration Map (GENERATED — do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning/main agent which skills spawn subagents (so it never forbids a
> legitimate spawn) and which are depth0-only (so a subagent never illegally invokes them).

| Skill | spawn_class | depth_policy | stack | instance | spawns |
|-------|-------------|--------------|-------|----------|--------|
| `intake` | spawner-agent | depth0-only | none | — | (Phase R: ≤2 read-only recon agents — Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-addon-diff` | leaf | any-depth | none | — | — |
| `odoo-backend-coding` | spawner-agent | depth0-only | backend | — | odoo-coder |
| `odoo-brl` | spawner-agent | depth0-only | none | — | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | any-depth | none | — | — |
| `odoo-capability-proof` | leaf | any-depth | none | — | — |
| `odoo-code-review` | spawner-agent | depth0-only | fullstack | — | odoo-code-reviewer |
| `odoo-competitive-brief` | leaf | any-depth | none | — | — |
| `odoo-content-draft` | leaf | any-depth | none | — | — |
| `odoo-customer-health` | leaf | any-depth | none | — | — |
| `odoo-customization-inventory` | leaf | any-depth | none | — | — |
| `odoo-data-migration` | leaf | any-depth | backend | — | — |
| `odoo-deal-followup` | leaf | any-depth | none | — | — |
| `odoo-debug` | spawner-agent | depth0-only | fullstack | — | odoo-backend-debugger, odoo-ui-debugger |
| `odoo-demo-recording` | leaf | any-depth | none | — | — |
| `odoo-deploy-checklist` | leaf | any-depth | none | yes | — |
| `odoo-deprecation-audit` | leaf | any-depth | backend | — | — |
| `odoo-discovery-summary` | leaf | any-depth | none | — | — |
| `odoo-feature-check` | leaf | any-depth | none | — | — |
| `odoo-feature-highlights` | leaf | any-depth | none | — | — |
| `odoo-frontend-coding` | spawner-agent | depth0-only | frontend | — | odoo-frontend-coder |
| `odoo-gap-analysis` | leaf | any-depth | none | — | — |
| `odoo-objection-handling` | leaf | any-depth | none | — | — |
| `odoo-onboarding` | leaf | any-depth | none | — | — |
| `odoo-override-finding` | leaf | any-depth | backend | — | — |
| `odoo-perf-audit` | leaf | any-depth | backend | — | — |
| `odoo-pricing-proposal` | leaf | any-depth | none | — | — |
| `odoo-qa-suite` | orchestrator-nl | any-depth | none | yes | — |
| `odoo-rfp-response` | leaf | any-depth | none | — | — |
| `odoo-risk-overview` | leaf | any-depth | none | — | — |
| `odoo-security-audit` | leaf | any-depth | backend | — | — |
| `odoo-support-triage` | orchestrator-nl | any-depth | none | — | — |
| `odoo-test-writer` | leaf | any-depth | backend | — | — |
| `odoo-ui-review` | spawner-agent | depth0-only | frontend | — | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | any-depth | backend | — | — |
| `odoo-visual-regression` | leaf | any-depth | frontend | — | — |
| `run-driver` | orchestrator-nl | depth0-only | none | — | — |
| `wave` | spawner-wave | depth0-only | none | yes | (per-WI leaf workers over worktrees) |
| `workflow-chaining` | orchestrator-nl | depth0-only | none | — | — |

## Legend

- **spawn_class** — `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch, no Agent-tool spawn) · `spawner-agent` (dispatches a named
  agent, depth 0→1) · `spawner-wave` (worktree fan-out, depth 0→1→2).
- **depth_policy** — `depth0-only` skills must be invoked only from the main agent,
  never from inside a subagent (nesting-crash guard). `any-depth` is safe to NL-dispatch.
- **stack** — drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

