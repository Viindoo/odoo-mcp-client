# Orchestration Map (GENERATED - do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning agent which skills launch subagents (so it never forbids a legitimate launch).

| Skill | spawn_class | handoff | stack | instance | spawns |
|-------|-------------|---------|-------|----------|--------|
| `odoo-acceptance` | spawner-agent | fresh | none | yes | odoo-qa-planner (P1 independent-oracle author), odoo-qa-tester (P2b live execute + adjudicate; browser-serial, one at a time), odoo-ui-reviewer (optional per-screen quality verdict in the P2b serial slot), odoo-test-writer (P2a durable tour/HttpCase authoring - agent launched for context isolation; invokes the odoo-test-writing skill inline), odoo-instance (P2 provision the co-installed cluster + run durable tests, via Skill tool), odoo-debug / odoo-coding (P3 fix-loop on FAIL, via Skill tool) |
| `odoo-addon-diff` | leaf | fresh | none | - | - |
| `odoo-brl` | spawner-agent | fork | none | - | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | fresh | none | - | - |
| `odoo-capability-proof` | leaf | fresh | none | - | - |
| `odoo-code-review` | spawner-agent | send-message | fullstack | - | odoo-code-reviewer, odoo-review-scoper, odoo-ui-reviewer (conditional Phase A.5 - rendered-UI review when module.needs_ui_review is true or candidate and an instance is reachable), odoo-test-writer (coverage gate - authors the missing/adapt-mode protecting test when a CRITICAL/HIGH behavior change ships uncovered; agent launched for context isolation, invokes the odoo-test-writing skill inline), git-ops (PR worktree checkout + diff/branch read + inline-comment posting on the PR - via git-ops skill - git-toolkit) |
| `odoo-coding` | spawner-agent | send-message | fullstack | - | odoo-coder (per-module COORDINATOR - launched for EVERY module; the sanctioned nested spawner that owns the module's INTERNAL work-item split, launches odoo-backend-coder / odoo-frontend-coder per WI, sequences backend-before-frontend, tests the integrated module via odoo-instance INLINE, and returns files for odoo-coding to commit - a nested spawner-coordinator one level below odoo-coding), odoo-test-writer (hard leaf - launched FIRST by the odoo-coder coordinator per WI to author the RED test, before the coder makes it green; authors by invoking the odoo-test-writing skill inline), odoo-backend-coder (hard leaf - launched by the odoo-coder coordinator for a backend work-item), odoo-frontend-coder (hard leaf - launched by the odoo-coder coordinator for a frontend work-item), (dispatch: ONE odoo-coder per module; model-weighted subagent batches, explicit model per module per tier table haiku/sonnet/opus/fable - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-competitive-brief` | leaf | fresh | none | - | - |
| `odoo-content-draft` | leaf | fresh | none | - | - |
| `odoo-customer-health` | leaf | fresh | none | - | - |
| `odoo-customization-inventory` | leaf | fresh | none | - | - |
| `odoo-data-migration` | leaf | fresh | backend | - | - |
| `odoo-deal-followup` | leaf | fresh | none | - | - |
| `odoo-debug` | spawner-agent | fresh | fullstack | - | odoo-backend-debugger, odoo-ui-debugger |
| `odoo-deep-survey` | spawner-agent | fork | none | - | (anonymous read-only fan-out subagents, explicit model per phase haiku/sonnet/opus; read-only on Odoo source, write only findings under <SHARE_DIR>/survey/, no further spawn - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-demo-recording` | leaf | fresh | none | - | - |
| `odoo-deploy-checklist` | leaf | fresh | none | - | - |
| `odoo-deprecation-audit` | leaf | fresh | backend | - | - |
| `odoo-discovery-summary` | leaf | fresh | none | - | - |
| `odoo-doc-feature-map` | spawner-agent | fresh | backend | - | odoo-feature-cataloger |
| `odoo-doc-illustration` | spawner-agent | fresh | frontend | - | odoo-doc-scoper (pre-flight multi-module scope mapper; dispatched first on multi-module TARGET), odoo-doc-planner (dependency-aware doc scheduler; dispatched after scoper; emits doc-plan.yaml; one whole-plan gate; branch-aware per-instance incremental loop), odoo-user-doc-writer (browser-exclusive leaf; end-user guide doc/index.rst; dispatched per module per DOC LAYER userguide|both), odoo-marketing-writer (browser-exclusive leaf; App-Store landing static/description/index.html; dispatched per module per DOC LAYER appstore|both), odoo-content-draft (Skill tool - marketing copy pre-fetch on marketing path when copy not supplied) |
| `odoo-doc-walkthrough` | spawner-agent | fresh | backend | - | odoo-doc-scenarist |
| `odoo-feature-check` | leaf | fresh | none | - | - |
| `odoo-feature-highlights` | leaf | fresh | none | - | - |
| `odoo-forward-port` | spawner-agent | send-message | fullstack | yes | odoo-intent-extractor (read-only, one instance PER MODULE covering that module's full ordered commit list - never per commit; model per module-bundle complexity, opus gated on human confirm), odoo-installable-prober (read-only per-module category-3 disambiguation in P2: reads the orchestrator-written target clean-tip manifest + the source manifest history dump; model per complexity / sonnet), odoo-test-writer (P8a test-forward adapt mode, RED-first - agent launched for context isolation; invokes the odoo-test-writing skill inline; SendMessage-resumable, one instance PER MODULE across the whole run, reused across every commit touching that module), odoo-coding (P8 adapt via the Skill tool; owns the coder fan-out (odoo-coder coordinator / odoo-backend-coder / odoo-frontend-coder) + model; FP-enriched brief carries C1 no-manifest-bump, C2 migration-dir series-retarget, C3 fix-old-version-first, WORKER NAME Tier-A resume field (same shape as the P8a odoo-test-writer name, never an agentId); serial per commit via work-tier worktrees; the coordinator is named once per module (fp-adapt-<slug>-<module>-coder) and resumed via SendMessage on every later commit touching that module - odoo-coding now honors WORKER NAME, so R2b (at most one agent per module) is closed at this leg), git-ops (cherry-pick, merge, branch/worktree ops - all local git mutations - plus read-only diff/range map + P5 verify and PR create/review - via git-ops skill - git-toolkit), odoo-acceptance (P11 end-to-end acceptance via the Skill tool; MANDATORY, cluster-wide, narrow-escape only; ONE dispatch for the whole batch, runs BEFORE the P12 PR opens or its review runs, verdict carried into the human-merge decision), odoo-instance (P9 per-batch provision + test-run via the Skill tool; owns the odoo-instance-ops fan-out; the handle is forwarded so later batches reuse it), odoo-i18n (P9.5 catalog reconcile via the Skill tool; MANDATORY per module whose 8e record says i18n_due: yes, narrow-escape only; reuses the P9 instance, folds its result into the P10 gate) |
| `odoo-frontend-design` | leaf | fresh | frontend | - | - |
| `odoo-gap-analysis` | spawner-agent | fork | none | - | odoo-gap-analyzer (one per requirement cluster; model per complexity per concurrency-guard Model-tier selection) |
| `odoo-git-rebase` | spawner-agent | fresh | fullstack | yes | intake subagent (sonnet: NL -> structured refs/base, PR-resolve, worktree-not-switch), Explore (read-only range enumerate + diff read), odoo-intent-extractor (rebase MODE, per-commit, base-head grounding), odoo-diff-comparator (cluster behavior comparison + range-diff/dup-guard verify), odoo-coding skill (via Skill tool: P8 conflict resolution + adapt; owns the coder fan-out (odoo-coder coordinator / odoo-backend-coder / odoo-frontend-coder) and synthesis - the rebase does NOT dispatch raw coders for conflicts), odoo-code-review skill (via Skill tool: P9b in-pipeline review + P12 final PR review), odoo-test-writer (adapt mode, RED-first - agent launched for context isolation; invokes the odoo-test-writing skill inline), odoo-instance skill (CONDITIONAL at P10: provisions ONE instance when range touches DB-stateful behavior; its INSTANCE_HANDLE is forwarded to every downstream verify/coder brief - downstream never self-provisions), git-ops (all local git mutations - cherry-pick, branch, squash, force-with-lease - plus read-only diff/range analysis + tree-identity verify and PR create/review - via git-ops skill - git-toolkit) |
| `odoo-i18n` | spawner-agent | fresh | backend | yes | odoo-translator |
| `odoo-icon-design` | spawner-agent | fresh | frontend | - | odoo-icon-designer |
| `odoo-instance` | spawner-agent | fresh | backend | yes | odoo-instance-ops |
| `odoo-intake` | spawner-agent | fresh | none | - | (Phase R: ≤2 read-only recon agents - Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-modules-upgrade` | spawner-agent | fresh | fullstack | yes | intake subagent (sonnet: branch->series->profile, installable:False candidate detection, scope clarify), Explore (dependency-graph build + diff read), odoo-deprecation-audit + odoo-version-diff (P1 recon, NL/Skill dispatch), odoo-diff-comparator (per-module core-absorption comparison), odoo-gap-analysis (core-feature coverage), odoo-solution-architect (conditional hard-call design), odoo-coding (P4 adapt via the Skill tool; owns the coder fan-out (odoo-coder coordinator / odoo-backend-coder / odoo-frontend-coder) + model; dep order, per-module worktrees), odoo-instance skill (P5 install/test via the Skill tool; owns the odoo-instance-ops fan-out) + odoo-backend-debugger / odoo-ui-debugger (failure diagnose), git-ops (branch, worktree, cherry-pick, squash - all git mutations - plus read-only diff scope + verify and P7 PR review/creation - via git-ops skill - git-toolkit), odoo-acceptance (P5.8 acceptance via the Skill tool; MANDATORY, cluster-wide, narrow-escape only; ONE dispatch for the whole cluster, gates alongside the P6 sign-off), odoo-i18n (P5.7 catalog reconcile via the Skill tool; MANDATORY for every surviving module, narrow-escape only; reuses the P5 instance, folds its result into the P6 sign-off) |
| `odoo-objection-handling` | leaf | fresh | none | - | - |
| `odoo-override-finding` | leaf | fresh | backend | - | - |
| `odoo-perf-audit` | leaf | fresh | backend | - | - |
| `odoo-planning` | spawner-agent | fresh | none | - | odoo-planner, odoo-doc-planner, (dispatch: single planner by default; for very large scope fan out one planner per module cluster following concurrency-guard.md Mode B, then reconcile - handoff fresh) |
| `odoo-pr-monitoring` | spawner-agent | fresh | none | - | git-ops (read PR CI status + review state, MERGE at the L2-merge-gate, re-push of an approved D3 fix + post-merge cleanup of worktrees/branches/tag - via git-ops skill - git-toolkit), odoo-debug (D3: route ANY CI warning/error/fail for root-cause first, via Skill tool), odoo-coding (author the fix odoo-debug located, via Skill tool; the re-push stays human-gated X2) |
| `odoo-pricing-proposal` | leaf | fresh | none | - | - |
| `odoo-qa-suite` | orchestrator-nl | fresh | none | - | - |
| `odoo-rfp-response` | leaf | fresh | none | - | - |
| `odoo-risk-overview` | leaf | fresh | none | - | - |
| `odoo-security-audit` | leaf | fresh | backend | - | - |
| `odoo-solution-design` | spawner-agent | fresh | fullstack | - | odoo-solution-architect, (dispatch: single mode -> 1 architect call; master-child mode -> 1 master architect + N child architects in dag_layer order - see snippets/master-child-design-contract.md) + optional MODE: review (independent design review, human-opt-in gate keyword) |
| `odoo-support-triage` | orchestrator-nl | fresh | none | - | - |
| `odoo-test-writing` | leaf | fresh | backend | - | - |
| `odoo-ui-review` | spawner-agent | fresh | frontend | - | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | fresh | backend | - | - |
| `odoo-visual-regression` | leaf | fresh | frontend | - | - |
| `run-harness` | orchestrator-nl | fresh | none | - | odoo-coding (INVOKED per MODULE via the Skill tool during between-wave integration; odoo-coding owns coder count + model; the odoo-coder coordinator COMMITS its module and returns the SHA - the work-item is odoo-coder's INTERNAL unit, never a wave input), git-ops (worktree add per Block 2W lineage; per wave, cherry-picks each module's commit onto the single run-integration branch as a saga/checkpoint - verified after each pick, no per-wave PR, no force-push; ONCE, after the final wave closes green, the terminal integrate land-tail squashes run-integration + a fresh non-force FIRST push, then opens ONE PR run-integration->principal; no L2-squash-gate - the only L2 is the downstream outward merge, owned by odoo-pr-monitoring; no auto-merge - via git-ops skill - git-toolkit), (anonymous Sonnet conflict-resolver subagent - dispatched ONLY when a between-wave cherry-pick reports a semantic conflict: handed the conflict diff + both module briefs via worker-brief.md, it edits the conflicting files (markers removed), then git-ops runs cherry-pick --continue; NOT a registered/named teammate agent - see skills/run-harness/references/wave-integration.md § Conflict Resolver), (anonymous fable close-the-wave review subagent - escalated ONLY for a large integrated wave (>~1500 changed lines OR N>=8 modules), human-gated at ~2x opus cost; the small-wave close-the-wave review is opus INLINE in this context, NOT a spawn - see skills/run-harness/references/wave-integration.md § Review Escalation) |
| `workflow-chaining` | orchestrator-nl | fresh | none | - | (fan-out only: <=3 concurrent anonymous leaf workers, each carrying the mandatory worker-brief preamble, per skills/_shared/concurrency-guard.md Mode A - see SKILL.md Hard rule 2/§ Fan-out/Fan-in; NOT a named-teammate spawn, so spawn_class stays orchestrator-nl) |

## Legend

- **spawn_class** - `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch; no NAMED-teammate subagent spawn - see a skill's own spawns
  cell for any anonymous review/resolver subagent) · `spawner-agent` (dispatches a named
  subagent).
- **handoff** - Context-Handoff Protocol (CHP) tier for resuming subagents across turns.
  `send-message` (Tier-A: lead resumes a named worker via SendMessage, avoiding
  cold-spawn overhead) · `fork` (Tier-B: subagent_type=fork fan-out inheriting parent
  context + prompt cache) · `fresh` (Tier-C default: cold-spawn every turn via agent
  launch + worklog blackboard - always-correct baseline; implicit when field is absent).
- **stack** - drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

## Skills that may spawn

Derived from a non-empty `spawns` entry, NOT from `spawn_class` - the same predicate `orchestration-digest.txt` uses ([NEW]-2), so the two artifacts cannot disagree. Two spawn_classes legitimately appear here: (1) a `spawner-agent` (launches a named subagent directly); (2) an `orchestrator-nl` whose `spawns` are SKILL invocations it drives transitively via the Skill tool (e.g. `run-harness` chaining `odoo-coding` / `git-ops`) - it launches no agent itself, but the skills it dispatches may, so surfacing it here is correct, not a defect. Only a `leaf` listed here is a genuine drift to fix at the SSOT (a leaf must never carry a `spawns` entry - either its class or the `spawns` entry is wrong).

`odoo-acceptance`, `odoo-brl`, `odoo-code-review`, `odoo-coding`, `odoo-debug`, `odoo-deep-survey`, `odoo-doc-feature-map`, `odoo-doc-illustration`, `odoo-doc-walkthrough`, `odoo-forward-port`, `odoo-gap-analysis`, `odoo-git-rebase`, `odoo-i18n`, `odoo-icon-design`, `odoo-instance`, `odoo-intake`, `odoo-modules-upgrade`, `odoo-planning`, `odoo-pr-monitoring`, `odoo-solution-design`, `odoo-ui-review`, `run-harness`, `workflow-chaining`

## Skill Conflict Resolution

Full skill-collision policy with worked examples lives in `skills/odoo-intake/references/collision-zones.md`. The one case below is specific to a single skill and kept here:

### `odoo-coding`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill - `odoo-coding` - owns all Odoo coding (backend Python/XML and front-end JS/OWL) and, for the front end, handles both paradigms internally via the `odoo-frontend-coder` agent.
- **Resolution (internal):** the `odoo-frontend-coder` agent selects the paradigm by version. Legacy JS widget system on older Odoo; OWL components on newer Odoo. Odoo v14 is the grey zone (pre-OWL but post-legacy peak) - prefer the legacy widget system there since it is still dominant.
- **Heuristic (paradigm signals):** `odoo.define()`, `web.Widget`, `field_registry` → legacy JS widget path. `useService`, `t-component`, `patch()`, `useState` → OWL path. Both resolve to `odoo-coding` (frontend leg).

