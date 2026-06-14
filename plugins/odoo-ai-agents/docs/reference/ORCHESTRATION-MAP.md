# Orchestration Map (GENERATED — do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning/main agent which skills spawn subagents (so it never forbids a
> legitimate spawn) and which are depth0-only (so a subagent never illegally invokes them).

| Skill | spawn_class | depth_policy | stack | instance | spawns |
|-------|-------------|--------------|-------|----------|--------|
| `odoo-addon-diff` | leaf | any-depth | none | — | — |
| `odoo-brl` | spawner-agent | depth0-only | none | — | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | any-depth | none | — | — |
| `odoo-capability-proof` | leaf | any-depth | none | — | — |
| `odoo-code-review` | spawner-agent | depth0-only | fullstack | — | odoo-code-reviewer |
| `odoo-coding` | spawner-agent | depth0-only | fullstack | — | odoo-coder, odoo-frontend-coder, (dispatch: Agent-tool model-weighted batches, explicit model per work-item per tier table haiku/sonnet/opus/fable - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-competitive-brief` | leaf | any-depth | none | — | — |
| `odoo-content-draft` | leaf | any-depth | none | — | — |
| `odoo-customer-health` | leaf | any-depth | none | — | — |
| `odoo-customization-inventory` | leaf | any-depth | none | — | — |
| `odoo-data-migration` | leaf | any-depth | backend | — | — |
| `odoo-deal-followup` | leaf | any-depth | none | — | — |
| `odoo-debug` | spawner-agent | depth0-only | fullstack | — | odoo-backend-debugger, odoo-ui-debugger |
| `odoo-deep-survey` | spawner-agent | depth0-only | none | — | (anonymous read-only fan-out workers via Agent tool, explicit model per phase haiku/sonnet/opus; read-only on Odoo source, write only findings under .odoo-ai/survey/, no further spawn — see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-demo-recording` | leaf | any-depth | none | — | — |
| `odoo-deploy-checklist` | leaf | any-depth | none | yes | — |
| `odoo-deprecation-audit` | leaf | any-depth | backend | — | — |
| `odoo-discovery-summary` | leaf | any-depth | none | — | — |
| `odoo-feature-check` | leaf | any-depth | none | — | — |
| `odoo-feature-highlights` | leaf | any-depth | none | — | — |
| `odoo-frontend-design` | leaf | any-depth | frontend | — | — |
| `odoo-gap-analysis` | leaf | any-depth | none | — | — |
| `odoo-intake` | spawner-agent | depth0-only | none | — | (Phase R: ≤2 read-only recon agents — Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-objection-handling` | leaf | any-depth | none | — | — |
| `odoo-onboarding` | leaf | any-depth | none | — | — |
| `odoo-override-finding` | leaf | any-depth | backend | — | — |
| `odoo-perf-audit` | leaf | any-depth | backend | — | — |
| `odoo-pricing-proposal` | leaf | any-depth | none | — | — |
| `odoo-qa-suite` | orchestrator-nl | any-depth | none | yes | — |
| `odoo-rfp-response` | leaf | any-depth | none | — | — |
| `odoo-risk-overview` | leaf | any-depth | none | — | — |
| `odoo-security-audit` | leaf | any-depth | backend | — | — |
| `odoo-solution-design` | spawner-agent | depth0-only | fullstack | — | odoo-solution-architect |
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

## Skill Conflict Resolution

Full skill-collision policy with worked examples lives in `skills/odoo-intake/references/collision-zones.md`. The one case below is specific to a single skill and kept here:

### `odoo-coding`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill — `odoo-coding` — owns all Odoo coding (backend Python/XML and front-end JS/OWL) and, for the front end, handles both paradigms internally via the `odoo-frontend-coder` agent.
- **Resolution (internal):** the `odoo-frontend-coder` agent selects the paradigm by version. Legacy JS widget system on older Odoo; OWL components on newer Odoo. Odoo v14 is the grey zone (pre-OWL but post-legacy peak) — prefer the legacy widget system there since it is still dominant.
- **Heuristic (paradigm signals):** `odoo.define()`, `web.Widget`, `field_registry` → legacy JS widget path. `useService`, `t-component`, `patch()`, `useState` → OWL path. Both resolve to `odoo-coding` (frontend leg).

