# Orchestration Map (GENERATED - do not edit by hand)

> SSOT: `generator/skill_tool_deps.json` → `orchestration`. Regenerate with `make gen`.
> Tells any planning agent which skills launch subagents (so it never forbids a legitimate launch).

| Skill | spawn_class | handoff | stack | instance | spawns |
|-------|-------------|---------|-------|----------|--------|
| `odoo-acceptance` | spawner-agent | fresh | none | yes | odoo-qa-tester (MODE A1A2 at haiku, or sonnet when a Given needs a fixture built per concurrency-guard.md Model-tier selection: the stand-alone and with-dependents databases, scenario execution, evidence, PASS/FAIL/UNVERIFIED; MODE A4 at sonnet: the audience walk-through when the node adds a user-facing screen), odoo-qa-planner (only for SRS criteria without a comparable expected value), odoo-test-writer (durable tour/HttpCase for High-tier PASS scenarios when the plan asks), odoo-instance (the testers build their databases through the skill, on leases the run owns) |
| `odoo-addon-diff` | leaf | fresh | none | - | - |
| `odoo-brl` | spawner-agent | fork | none | - | (conditional DAG workers when >10 large clusters) |
| `odoo-campaign-plan` | leaf | fresh | none | - | - |
| `odoo-capability-proof` | leaf | fresh | none | - | - |
| `odoo-code-review` | spawner-agent | send-message | fullstack | - | odoo-code-reviewer (MODE R1 at haiku, then MODE R2 at sonnet and MODE R3 at opus when the unit is specialist or the override chain is deep; later rounds resume the same reviewers with SendMessage), odoo-ui-reviewer (when an instance exists and views changed), git-ops (PR worktree checkout, bounded diff reads, inline-comment posting on the keyword post - via git-ops skill - git-toolkit) |
| `odoo-coding` | spawner-agent | send-message | fullstack | - | odoo-coder, (ONE per plan node, at the design's build_tier_hint; the coder writes code and tests, runs the instance through the odoo-instance skill, commits through git-ops, and is resumed with SendMessage for review and acceptance findings; it launches odoo-impact-recon when it has no recon, a second odoo-coder only past one agent's output budget, and odoo-frontend-coder only for a disjoint frontend part with new JS or OWL files) |
| `odoo-competitive-brief` | leaf | fresh | none | - | - |
| `odoo-content-draft` | spawner-agent | fresh | none | - | odoo-marketer (MODE copy: one piece for one channel; sonnet to compose, haiku to re-cut an existing draft) |
| `odoo-customer-health` | leaf | fresh | none | - | - |
| `odoo-customization-inventory` | leaf | fresh | none | - | - |
| `odoo-data-migration` | leaf | fresh | backend | - | - |
| `odoo-deal-followup` | leaf | fresh | none | - | - |
| `odoo-debug` | spawner-agent | fresh | fullstack | - | odoo-backend-debugger (one per incident; resumed at a higher tier with PRIOR_FINDINGS), odoo-ui-debugger (browser-exclusive; one per incident), odoo-perf-audit / odoo-security-audit (Skill tool, inline, reactive mode), odoo-coding (Skill tool, inline, standalone fix hand-off) |
| `odoo-deep-survey` | spawner-agent | fork | none | - | (anonymous read-only fan-out subagents, explicit model per phase per the capability map: haiku gathers, sonnet dives and synthesizes, opus only on an evidenced trigger or a specialist domain; read-only on Odoo source, write only findings under <SHARE_DIR>/survey/, no further spawn - see skills/_shared/concurrency-guard.md Mode B) |
| `odoo-demo-recording` | leaf | fresh | none | - | - |
| `odoo-deploy-checklist` | leaf | fresh | none | - | - |
| `odoo-deprecation-audit` | leaf | fresh | backend | - | - |
| `odoo-discovery-summary` | leaf | fresh | none | - | - |
| `odoo-doc-feature-map` | spawner-agent | fresh | backend | - | odoo-doc-writer (MODE catalog-only; writes the catalog, the role map and the usage walkthrough) |
| `odoo-doc-illustration` | spawner-agent | fresh | frontend | - | odoo-doc-writer (MODE full per module - the user guide; sonnet, haiku for a change made only of relabels and recaptures; CHANGE feature list = update only the affected sections and screens), odoo-marketer (MODE landing per module whose layer includes appstore - the App Store page from the writer's catalog, facts and staged captures; same model rule), odoo-instance (Skill tool, inline - one lease per instance path), git-toolkit:git-ops (Skill tool - the docs worktree and one commit per module) |
| `odoo-doc-site` | spawner-agent | fresh | none | yes | odoo-doc-site-writer (one per disjoint page group; sonnet for new pages, haiku for recapture, relabel, toctree wiring and filling existing translations), odoo-qa-tester (MODE DOCS: browser acceptance of the locally served docs build before the PR; sonnet), odoo-instance (Skill tool, inline - one lease per series), odoo-doc-feature-map (Skill tool - the catalog of a module the plan shows when none exists), git-toolkit:git-ops (Skill tool - worktrees, commits, push and the PR per series) |
| `odoo-feature-check` | leaf | fresh | none | - | - |
| `odoo-feature-highlights` | leaf | fresh | none | - | - |
| `odoo-forward-port` | spawner-agent | send-message | fullstack | yes | odoo-intent-extractor (read-only, one instance PER MODULE covering that module's full ordered commit list - never per commit; model per the capability map in skills/_shared/concurrency-guard.md), odoo-installable-prober (read-only per-module category-3 disambiguation in P2: reads the orchestrator-written target clean-tip manifest + the source manifest history dump; haiku), odoo-coding (P8 adapt via the Skill tool; one invocation per module, MODE: adapt, COMMIT: caller; owns the node's coder (odoo-coder, with odoo-frontend-coder for a disjoint JS/OWL part; the coder writes the node's tests test leg that adapts the forwarded tests and break-checks them) + model; FP-enriched brief carries C1 manifest version by formula (installable modules only), C3 fix-old-version-first; the C2 migration-dir decision is a later resumed invocation at P9.6, WORKER_AGENT_ID Tier-A resume field (an id the caller captured from its own earlier launch, never a string anyone invented); modules adapted serially in the one integration worktree; the coder is launched ONCE per module and its returned id recorded, then resumed by that id on every later invocation for that module - odoo-coding honors WORKER_AGENT_ID, so R2b (at most one agent per module) is closed at this leg), git-ops (P5 absorb-all - ONE no-ff no-commit merge of the batch's range TIP, the pipeline's only git shape - plus branch/worktree ops, the single self-decided P10 merge commit (no human gate; human gates are P4 and the P12 PR merge), and all other local git mutations, plus read-only diff/range map and PR create/review - via git-ops skill - git-toolkit; never a per-commit merge, and never a cherry-pick at any granularity), odoo-acceptance (P11 end-to-end acceptance via the Skill tool; MANDATORY, cluster-wide, narrow-escape only; ONE dispatch for the whole batch, runs BEFORE the P12 PR opens or its review runs, verdict carried into the human-merge decision), odoo-instance (P9 per-batch provision + test-run via the Skill tool; owns the odoo-instance-ops fan-out; the handle is forwarded so later batches reuse it), odoo-i18n (P9.5 catalog reconcile via the Skill tool; MANDATORY per module whose 8e record says i18n_due: yes, narrow-escape only; SELF_PROVISIONS its own demo-loaded export instance - the P9 verify instance is built without demo and cannot serve an export - its result is presented at the P12 PR gate), odoo-doc-illustration / odoo-doc-site (Skill tool; after the PR is presented, per snippets/docs-after-change.md, for the modules installable at the target; module docs commit onto the same PR's branch), odoo-doc-site (Skill tool; the docs-site lane - references/fp-docs-site-lane.md - with WORKTREE = the integration worktree and LAND: caller: it re-verifies the ported pages, runs the build gates and the browser acceptance and returns its files for the one merge commit) |
| `odoo-frontend-design` | leaf | fresh | frontend | - | - |
| `odoo-gap-analysis` | spawner-agent | fork | none | - | odoo-gap-analyzer (one per requirement cluster; model per complexity per concurrency-guard Model-tier selection) |
| `odoo-git-rebase` | spawner-agent | fresh | fullstack | yes | intake subagent (haiku: NL -> structured refs/base, PR-resolve, worktree-not-switch), Explore (read-only range enumerate + diff read), odoo-intent-extractor (rebase MODE, per-commit, base-head grounding), odoo-diff-comparator (cluster behavior comparison + range-diff/dup-guard verify), odoo-coding skill (via Skill tool: P8 conflict resolution + adapt; owns the node's coder (odoo-coder, with odoo-frontend-coder for a disjoint JS/OWL part) and synthesis - the rebase does NOT dispatch raw coders for conflicts), odoo-code-review skill (via Skill tool: P9b in-pipeline review + P12 final PR review), odoo-instance skill (CONDITIONAL at P10: provisions ONE instance when range touches DB-stateful behavior; its INSTANCE_HANDLE is forwarded to every downstream verify/coder brief - downstream never self-provisions), git-ops (all local git mutations - cherry-pick, branch, squash, force-with-lease - plus read-only diff/range analysis + tree-identity verify and PR create/review - via git-ops skill - git-toolkit) |
| `odoo-i18n` | spawner-agent | fresh | backend | yes | odoo-translator |
| `odoo-icon-design` | spawner-agent | fresh | frontend | - | odoo-icon-designer |
| `odoo-instance` | spawner-agent | fresh | backend | yes | odoo-instance-ops |
| `odoo-intake` | spawner-agent | fresh | none | - | (Phase R: ≤2 read-only recon agents - Explore or specialist in read-only mode; no writes, no further spawn) |
| `odoo-modules-upgrade` | spawner-agent | fresh | fullstack | yes | intake subagent (haiku: branch->series->profile, installable:False candidate detection, scope clarify), Explore (dependency-graph build + diff read), odoo-deprecation-audit + odoo-version-diff (P1 recon, NL/Skill dispatch), odoo-diff-comparator (per-module core-absorption comparison), odoo-gap-analysis (core-feature coverage), odoo-solution-architect (conditional hard-call design), odoo-coding (P4 adapt via the Skill tool; owns the node's coder (odoo-coder, with odoo-frontend-coder for a disjoint JS/OWL part) + model; dep order, per-module worktrees), odoo-instance skill (P5 install/test via the Skill tool; owns the odoo-instance-ops fan-out) + odoo-backend-debugger / odoo-ui-debugger (failure diagnose), git-ops (branch, worktree, cherry-pick, squash - all git mutations - plus read-only diff scope + verify and P7 PR review/creation - via git-ops skill - git-toolkit), odoo-acceptance (P5.8 acceptance via the Skill tool; MANDATORY, cluster-wide, narrow-escape only; ONE dispatch for the whole cluster, gates alongside the P6 sign-off), odoo-i18n (P5.7 catalog reconcile via the Skill tool; MANDATORY for every surviving module, narrow-escape only; reuses the P5 instance, folds its result into the P6 sign-off), odoo-doc-illustration / odoo-doc-site (Skill tool; after the PR is presented, per snippets/docs-after-change.md, for the modules installable at the target; module docs commit onto the same PR's branch) |
| `odoo-objection-handling` | leaf | fresh | none | - | - |
| `odoo-override-finding` | leaf | fresh | backend | - | - |
| `odoo-perf-audit` | leaf | fresh | backend | - | - |
| `odoo-planning` | spawner-agent | fresh | none | - | odoo-planner, (dispatch: single planner by default; for very large scope fan out one planner per module cluster following concurrency-guard.md Mode B, then reconcile - handoff fresh) |
| `odoo-pr-monitoring` | spawner-agent | fresh | none | - | git-ops (read PR CI status + review state, MERGE at the L2-merge-gate, re-push of an approved D3 fix + post-merge cleanup of worktrees/branches/tag - via git-ops skill - git-toolkit), odoo-debug (D3: route ANY CI warning/error/fail for root-cause first, via Skill tool), odoo-coding (author the fix odoo-debug located, via Skill tool; the re-push to the PR branch is self-decided, only the merge into the protected branch waits for the human) |
| `odoo-pricing-proposal` | leaf | fresh | none | - | - |
| `odoo-qa-suite` | orchestrator-nl | fresh | none | - | - |
| `odoo-rfp-response` | leaf | fresh | none | - | - |
| `odoo-risk-overview` | leaf | fresh | none | - | - |
| `odoo-security-audit` | leaf | fresh | backend | - | - |
| `odoo-solution-design` | spawner-agent | fresh | fullstack | - | odoo-solution-architect, (one design session per change: SRS -> gate -> recon by odoo-impact-recon -> design -> gate; the skill resumes the same architect with SendMessage at each gate; master-child mode adds MODE: master, child, consistency and reconcile passes per snippets/master-child-design-contract.md and an optional MODE: review on a human opt-in keyword) |
| `odoo-support-triage` | orchestrator-nl | fresh | none | - | - |
| `odoo-test-writing` | leaf | fresh | backend | - | - |
| `odoo-ui-review` | spawner-agent | fresh | frontend | - | odoo-ui-reviewer |
| `odoo-version-diff` | leaf | fresh | backend | - | - |
| `odoo-visual-regression` | leaf | fresh | frontend | - | - |
| `workflow-chaining` | orchestrator-nl | fresh | none | - | (fan-out only: <=3 concurrent anonymous leaf workers, each carrying the mandatory worker-brief preamble, per skills/_shared/concurrency-guard.md Mode A - see SKILL.md Hard rule 2/§ Fan-out/Fan-in; leaf workers only, so spawn_class stays orchestrator-nl) |

## Legend

- **spawn_class** - `leaf` (runs inline) · `orchestrator-nl` (chains other skills via
  natural-language dispatch; no subagent spawn of its own - see a skill's own spawns
  cell for any anonymous review/resolver subagent) · `spawner-agent` (dispatches a
  subagent).
- **handoff** - Context-Handoff Protocol (CHP) tier for resuming subagents across turns.
  `send-message` (Tier-A: a launcher resumes a child it launched, by the id its own
  launch returned, avoiding cold-spawn overhead) · `fork` (Tier-B: subagent_type=fork fan-out inheriting parent
  context + prompt cache) · `fresh` (Tier-C default: cold-spawn every turn via agent
  launch + worklog blackboard - always-correct baseline; implicit when field is absent).
- **stack** - drives backend↔frontend routing; `fullstack` work must engage both a
  backend and a frontend specialist.

## Skills that may spawn

Derived from a non-empty `spawns` entry, NOT from `spawn_class` - the same predicate `orchestration-digest.txt` uses ([NEW]-2), so the two artifacts cannot disagree. Two spawn_classes legitimately appear here: (1) a `spawner-agent` (launches a named subagent directly); (2) an `orchestrator-nl` whose `spawns` are SKILL invocations it drives transitively via the Skill tool (e.g. `odoo-forward-port` chaining `odoo-coding` / `git-ops`) - it launches no agent itself, but the skills it dispatches may, so surfacing it here is correct, not a defect. Only a `leaf` listed here is a genuine drift to fix at the SSOT (a leaf must never carry a `spawns` entry - either its class or the `spawns` entry is wrong).

`odoo-acceptance`, `odoo-brl`, `odoo-code-review`, `odoo-coding`, `odoo-content-draft`, `odoo-debug`, `odoo-deep-survey`, `odoo-doc-feature-map`, `odoo-doc-illustration`, `odoo-doc-site`, `odoo-forward-port`, `odoo-gap-analysis`, `odoo-git-rebase`, `odoo-i18n`, `odoo-icon-design`, `odoo-instance`, `odoo-intake`, `odoo-modules-upgrade`, `odoo-planning`, `odoo-pr-monitoring`, `odoo-solution-design`, `odoo-ui-review`, `workflow-chaining`

## Skill Conflict Resolution

Full skill-collision policy with worked examples lives in `skills/odoo-intake/references/collision-zones.md`. The one case below is specific to a single skill and kept here:

### `odoo-coding`: legacy JS widgets vs OWL (version-aware)

- **No skill conflict:** A single skill - `odoo-coding` - owns all Odoo coding (backend Python/XML and front-end JS/OWL) and, for the front end, handles both paradigms internally via the `odoo-frontend-coder` agent.
- **Resolution (internal):** the `odoo-frontend-coder` agent selects the paradigm, and the paradigm boundary itself is owned by `snippets/odoo-era-boundaries.md` rows 1 and 1b - resolve it there. This map states no Odoo version fact of its own.

