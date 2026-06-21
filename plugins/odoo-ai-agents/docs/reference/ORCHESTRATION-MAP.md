# Orchestration Map (GENERATED - do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning agent which skills launch subagents (so it never forbids a legitimate launch).

| Skill | spawn_class | stack | instance | spawns |
|-------|-------------|-------|----------|--------|
| `odoo-addon-diff` | leaf | none | - | - |
| `odoo-brl` | spawner-agent | none | - | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | none | - | - |
| `odoo-capability-proof` | leaf | none | - | - |
| `odoo-code-review` | spawner-agent | fullstack | - | odoo-code-reviewer |
| `odoo-coding` | spawner-agent | fullstack | - | odoo-coder, odoo-frontend-coder, (dispatch: model-weighted subagent batches, explicit model per work-item per tier table haiku/sonnet/opus/fable - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-competitive-brief` | leaf | none | - | - |
| `odoo-content-draft` | leaf | none | - | - |
| `odoo-customer-health` | leaf | none | - | - |
| `odoo-customization-inventory` | leaf | none | - | - |
| `odoo-data-migration` | leaf | backend | - | - |
| `odoo-deal-followup` | leaf | none | - | - |
| `odoo-debug` | spawner-agent | fullstack | - | odoo-backend-debugger, odoo-ui-debugger |
| `odoo-deep-survey` | spawner-agent | none | - | (anonymous read-only fan-out subagents, explicit model per phase haiku/sonnet/opus; read-only on Odoo source, write only findings under .odoo-ai/survey/, no further spawn - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-demo-recording` | leaf | none | - | - |
| `odoo-deploy-checklist` | leaf | none | yes | - |
| `odoo-deprecation-audit` | leaf | backend | - | - |
| `odoo-discovery-summary` | leaf | none | - | - |
| `odoo-doc-illustration` | spawner-agent | frontend | - | odoo-doc-illustrator |
| `odoo-feature-check` | leaf | none | - | - |
| `odoo-feature-highlights` | leaf | none | - | - |
| `odoo-forward-port` | spawner-agent | fullstack | yes | odoo-intent-extractor (read-only per-commit; model per complexity), odoo-installable-prober (read-only per-module installable-state probe in P2; model per complexity / sonnet), odoo-coder / odoo-frontend-coder (FP-enriched adapter prompt; serial per commit via work-tier worktrees) |
| `odoo-frontend-design` | leaf | frontend | - | - |
| `odoo-gap-analysis` | leaf | none | - | - |
| `odoo-i18n` | spawner-agent | backend | yes | odoo-translator |
| `odoo-instance` | spawner-agent | backend | yes | odoo-instance-ops |
| `odoo-intake` | spawner-agent | none | - | (Phase R: ≤2 read-only recon agents - Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-objection-handling` | leaf | none | - | - |
| `odoo-onboarding` | leaf | none | - | - |
| `odoo-override-finding` | leaf | backend | - | - |
| `odoo-perf-audit` | leaf | backend | - | - |
| `odoo-pricing-proposal` | leaf | none | - | - |
| `odoo-qa-suite` | orchestrator-nl | none | yes | - |
| `odoo-rfp-response` | leaf | none | - | - |
| `odoo-risk-overview` | leaf | none | - | - |
| `odoo-security-audit` | leaf | backend | - | - |
| `odoo-solution-design` | spawner-agent | fullstack | - | odoo-solution-architect |
| `odoo-support-triage` | orchestrator-nl | none | - | - |
| `odoo-test-writing` | leaf | backend | - | - |
| `odoo-ui-review` | spawner-agent | frontend | - | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | backend | - | - |
| `odoo-visual-regression` | leaf | frontend | - | - |
| `run-driver` | orchestrator-nl | none | - | - |
| `wave` | spawner-wave | none | yes | (per-WI leaf workers over worktrees) |
| `workflow-chaining` | orchestrator-nl | none | - | - |

## Legend

- **spawn_class** - `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch, no subagent spawn) · `spawner-agent` (dispatches a named
  subagent) · `spawner-wave` (worktree fan-out with parallel subagents).
- **stack** - drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

## Skill Conflict Resolution

Full skill-collision policy with worked examples lives in `skills/odoo-intake/references/collision-zones.md`. The one case below is specific to a single skill and kept here:

### `odoo-coding`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill - `odoo-coding` - owns all Odoo coding (backend Python/XML and front-end JS/OWL) and, for the front end, handles both paradigms internally via the `odoo-frontend-coder` agent.
- **Resolution (internal):** the `odoo-frontend-coder` agent selects the paradigm by version. Legacy JS widget system on older Odoo; OWL components on newer Odoo. Odoo v14 is the grey zone (pre-OWL but post-legacy peak) - prefer the legacy widget system there since it is still dominant.
- **Heuristic (paradigm signals):** `odoo.define()`, `web.Widget`, `field_registry` → legacy JS widget path. `useService`, `t-component`, `patch()`, `useState` → OWL path. Both resolve to `odoo-coding` (frontend leg).

