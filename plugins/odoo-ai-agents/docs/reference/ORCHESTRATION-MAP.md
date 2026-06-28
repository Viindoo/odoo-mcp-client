# Orchestration Map (GENERATED - do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning agent which skills launch subagents (so it never forbids a legitimate launch).

| Skill | spawn_class | handoff | stack | instance | spawns |
|-------|-------------|---------|-------|----------|--------|
| `odoo-addon-diff` | leaf | fresh | none | - | - |
| `odoo-brl` | spawner-agent | fork | none | - | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | fresh | none | - | - |
| `odoo-capability-proof` | leaf | fresh | none | - | - |
| `odoo-code-review` | spawner-agent | send-message | fullstack | - | odoo-code-reviewer, odoo-review-scoper, github-operator (PR read + inline comment via GitHub MCP - delegated to git-toolkit), git-operator (local diff/branch read before review - delegated to git-toolkit) |
| `odoo-coding` | spawner-agent | send-message | fullstack | - | odoo-coder, odoo-frontend-coder, (dispatch: model-weighted subagent batches, explicit model per work-item per tier table haiku/sonnet/opus/fable - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-competitive-brief` | leaf | fresh | none | - | - |
| `odoo-content-draft` | leaf | fresh | none | - | - |
| `odoo-customer-health` | leaf | fresh | none | - | - |
| `odoo-customization-inventory` | leaf | fresh | none | - | - |
| `odoo-data-migration` | leaf | fresh | backend | - | - |
| `odoo-deal-followup` | leaf | fresh | none | - | - |
| `odoo-debug` | spawner-agent | fresh | fullstack | - | odoo-backend-debugger, odoo-ui-debugger |
| `odoo-deep-survey` | spawner-agent | fork | none | - | (anonymous read-only fan-out subagents, explicit model per phase haiku/sonnet/opus; read-only on Odoo source, write only findings under .odoo-ai/survey/, no further spawn - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-demo-recording` | leaf | fresh | none | - | - |
| `odoo-deploy-checklist` | leaf | fresh | none | yes | - |
| `odoo-deprecation-audit` | leaf | fresh | backend | - | - |
| `odoo-diff-comparator` | leaf | fresh | none | - | - |
| `odoo-discovery-summary` | leaf | fresh | none | - | - |
| `odoo-doc-illustration` | spawner-agent | fresh | frontend | - | odoo-doc-illustrator |
| `odoo-feature-check` | leaf | fresh | none | - | - |
| `odoo-feature-highlights` | leaf | fresh | none | - | - |
| `odoo-forward-port` | spawner-agent | send-message | fullstack | yes | odoo-intent-extractor (read-only per-commit; model per complexity), odoo-installable-prober (read-only per-module installable-state probe in P2; model per complexity / sonnet), odoo-coder / odoo-frontend-coder (FP-enriched adapter prompt carries C1 no-manifest-bump, C2 migration-dir series-retarget, C3 fix-old-version-first; serial per commit via work-tier worktrees), git-operator (cherry-pick, merge, branch/worktree ops - all local git mutations delegated to git-toolkit), git-surveyor (read-only diff/range map + P5 verify - delegated to git-toolkit), github-operator (PR create + review - delegated to git-toolkit) |
| `odoo-frontend-design` | leaf | fresh | frontend | - | - |
| `odoo-gap-analysis` | spawner-agent | fork | none | - | odoo-gap-analyzer (one per requirement cluster; model per complexity per concurrency-guard Model-tier selection) |
| `odoo-git-rebase` | spawner-agent | fresh | fullstack | yes | intake subagent (sonnet: NL -> structured refs/base, PR-resolve, worktree-not-switch), Explore (read-only range enumerate + diff read), odoo-intent-extractor (rebase MODE, per-commit, base-head grounding), odoo-diff-comparator (cluster behavior comparison + range-diff/dup-guard verify), odoo-coding skill (via Skill tool: P8 conflict resolution + adapt; owns odoo-coder/odoo-frontend-coder fan-out and synthesis - the rebase does NOT dispatch raw coders for conflicts), odoo-code-review skill (via Skill tool: P9b in-pipeline review + P12 final PR review), odoo-test-writing (mode adapt, RED-first), odoo-instance skill (CONDITIONAL at P10: provisions ONE instance when range touches DB-stateful behavior; its INSTANCE_HANDLE is forwarded to every downstream verify/coder brief - downstream never self-provisions), git-operator (all local git mutations: cherry-pick, branch, squash, force-with-lease - delegated to git-toolkit), git-surveyor (read-only diff/range analysis + tree-identity verify - delegated to git-toolkit), github-operator (PR create + review - delegated to git-toolkit) |
| `odoo-i18n` | spawner-agent | fresh | backend | yes | odoo-translator |
| `odoo-instance` | spawner-agent | fresh | backend | yes | odoo-instance-ops |
| `odoo-intake` | spawner-agent | fresh | none | - | (Phase R: ≤2 read-only recon agents - Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-modules-upgrade` | spawner-agent | fresh | fullstack | yes | intake subagent (sonnet: branch->series->profile, installable:False candidate detection, scope clarify), Explore (dependency-graph build + diff read), odoo-deprecation-audit + odoo-version-diff (P1 recon, NL/Skill dispatch), odoo-diff-comparator (per-module core-absorption comparison), odoo-gap-analysis (core-feature coverage), odoo-solution-architect (conditional hard-call design), odoo-coder / odoo-frontend-coder (P4 adapt, dep order, per-module worktrees), odoo-instance-ops (P5 install/test) + odoo-backend-debugger / odoo-ui-debugger (failure diagnose), git-operator (branch, worktree, cherry-pick, squash - all git mutations delegated to git-toolkit), git-surveyor (read-only diff scope + verify - delegated to git-toolkit), github-operator (P7 PR review + creation - delegated to git-toolkit) |
| `odoo-objection-handling` | leaf | fresh | none | - | - |
| `odoo-onboarding` | leaf | fresh | none | - | - |
| `odoo-override-finding` | leaf | fresh | backend | - | - |
| `odoo-perf-audit` | leaf | fresh | backend | - | - |
| `odoo-pricing-proposal` | leaf | fresh | none | - | - |
| `odoo-qa-suite` | orchestrator-nl | fresh | none | yes | - |
| `odoo-review-scoper` | leaf | fresh | none | - | - |
| `odoo-rfp-response` | leaf | fresh | none | - | - |
| `odoo-risk-overview` | leaf | fresh | none | - | - |
| `odoo-security-audit` | leaf | fresh | backend | - | - |
| `odoo-solution-design` | spawner-agent | fresh | fullstack | - | odoo-solution-architect, (dispatch: single mode -> 1 architect call; master-child mode -> 1 master architect + N child architects in dag_layer order - see snippets/master-child-design-contract.md) |
| `odoo-support-triage` | orchestrator-nl | fresh | none | - | - |
| `odoo-test-writing` | leaf | fresh | backend | - | - |
| `odoo-ui-review` | spawner-agent | fresh | frontend | - | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | fresh | backend | - | - |
| `odoo-visual-regression` | leaf | fresh | frontend | - | - |
| `run-driver` | orchestrator-nl | fresh | none | - | - |
| `wave` | spawner-wave | send-message | none | yes | (per-WI leaf workers over worktrees), git-operator (worktree add, cherry-pick A->B->C onto integration, squash, force-with-lease - all git ops delegated to git-toolkit), git-surveyor (read-only diff + tree-identity verify - delegated to git-toolkit), github-operator (PR integration->principal + review - delegated to git-toolkit) |
| `workflow-chaining` | orchestrator-nl | fresh | none | - | - |

## Legend

- **spawn_class** - `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch, no subagent spawn) · `spawner-agent` (dispatches a named
  subagent) · `spawner-wave` (worktree fan-out with parallel subagents).
- **handoff** - Context-Handoff Protocol (CHP) tier for resuming subagents across turns.
  `send-message` (Tier-A: lead resumes a named worker via SendMessage, avoiding
  cold-spawn overhead) · `fork` (Tier-B: subagent_type=fork fan-out inheriting parent
  context + prompt cache) · `fresh` (Tier-C default: cold-spawn every turn via Agent
  tool + worklog blackboard - always-correct baseline; implicit when field is absent).
- **stack** - drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

## Skill Conflict Resolution

Full skill-collision policy with worked examples lives in `skills/odoo-intake/references/collision-zones.md`. The one case below is specific to a single skill and kept here:

### `odoo-coding`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill - `odoo-coding` - owns all Odoo coding (backend Python/XML and front-end JS/OWL) and, for the front end, handles both paradigms internally via the `odoo-frontend-coder` agent.
- **Resolution (internal):** the `odoo-frontend-coder` agent selects the paradigm by version. Legacy JS widget system on older Odoo; OWL components on newer Odoo. Odoo v14 is the grey zone (pre-OWL but post-legacy peak) - prefer the legacy widget system there since it is still dominant.
- **Heuristic (paradigm signals):** `odoo.define()`, `web.Widget`, `field_registry` → legacy JS widget path. `useService`, `t-component`, `patch()`, `useState` → OWL path. Both resolve to `odoo-coding` (frontend leg).

