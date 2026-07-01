# Odoo AI Agent Team

> Plugin slug: `odoo-ai-agents`

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://odoo-semantic.viindoo.com/)

> The Odoo AI workforce toolkit: **53 skills + 23 agents + 8 commands**, grouped into **9 persona
> buckets**, plus **13 declarative workflows** - covering engineering, coding, code review, visual
> UI testing, instance provisioning, pre-sales, sales, marketing, strategy, onboarding, and cross-version forward-porting. Installing this plugin pulls
> in the companion [`odoo-semantic-mcp`](../odoo-semantic-mcp/) plugin automatically (declared
> dependency), so all knowledge is grounded through the OSM MCP server. This repo is a thin
> routing and orchestration layer; computation lives on the server.

## What you get

Nine virtual specialists that self-activate from plain-language intent - no slash
commands to memorize. Describe what you need; the right persona fires automatically.
You do not need to know skill names.

`odoo-intake` is the universal front door. Say what you want in plain language and it plans the
whole job once, then drives it to done:
- **Vague intent** -> it brainstorms with you (clarifying options, no open-ended "what do you want?").
- **Clear single-step intent** -> it fast-paths straight to the matching specialist. A **review,
  PR-review, or debug** intent fast-paths to `odoo-code-review` / `odoo-debug` with no Plan Mode at
  all - and on a CRITICAL/HIGH finding that specialist **autonomously drives the fix** through
  `odoo-coding` and re-reviews to verify (review -> code -> review, bounded to 3 rounds then escalates).
- **Large / open-ended job** -> it can offer an opt-in **`deep-survey`**: a read-only, multi-phase
  pass (broad haiku sweep -> narrow sonnet dives -> optional opus) that writes a synthesis under
  `.odoo-ai/survey/` and re-informs a sharper plan before any code is written.
- **Multi-step intent** -> it lays out a plan (the work-items, their order, who does each), you
  approve once, and then it **advances step-to-step on its own** - dispatching each specialist,
  reading the result, and moving to the next - stopping only when a step is irreversible/outward
  (e.g. a git push or an email to a customer) or when it is blocked and needs you.

You control how hands-off this is with one optional flag (`--auto` is the default; see
[Drive to done](#drive-to-done-how-to-use-it)). No execution ever fires before you approve the
plan, and the main agent is never forced or trapped - the stops are real human checkpoints, the
nudges are advisory.

A first-class **forward-port pipeline** (`/odoo-forward-port`) is also included: a 12-phase
orchestration that ports commits across Odoo series using intent-first extraction (not raw
code carry-over), merge-keep-SHA strategy, symbol-survival checking, pre-adapt drift scan,
adaptive test forwarding, and verify-by-behavior per batch. It runs alongside coding, code
review, and upgrade planning as a core engineering capability.

> **Counts at a glance:** this plugin ships **53 skills + 23 agents + 8 commands**, grouped into
> **9 persona buckets** for navigation, plus **13 declarative workflows** driven by
> `workflows/*.workflow.yaml`. A further slash command, `/odoo-semantic-mcp:connect`, belongs to
> the companion `odoo-semantic-mcp` plugin and is pulled in automatically when you install this one.

## Who is it for

| Persona | Key skills |
|---------|-----------|
| Onboarding / Concierge | `odoo-intake` - `odoo-onboarding` |
| Engineer | override-finding - deprecation-audit - forward-port / version-diff - git-rebase - modules-upgrade |
| Coder | odoo-coding - odoo-debug - solution-design |
| Code-Reviewer | odoo-code-review |
| Visual / UI QA | ui-review - visual-regression - demo-recording - doc-illustration |
| Pre-Sales | feature-check - gap-analysis - brl |
| Sales AE | objection-handling - deal-followup - discovery-summary |
| Marketer | feature-highlights - content-draft - campaign-plan - icon-design - doc-feature-map - doc-walkthrough |
| Strategist / CEO | risk-overview - competitive-brief - customization-inventory |

- **Engineer** - Find the correct override point, audit deprecated API usage before an upgrade, or validate a deployment is safe.
- **Coder** - Write Odoo backend (Python/XML) or frontend (JS/OWL) code that is idiomatic and convention-correct, without looking up every framework rule.
- **Code-Reviewer** - Review pull requests or audit patches for ORM misuse, inheritance anti-patterns, security holes, or N+1 query issues.
- **Visual / UI QA** - Review a live Odoo screen through five lenses (aesthetics, function, stability, accessibility, performance), debug a broken render, catch visual regressions, record a demo clip, or run a full QA pipeline (test cases + checklist + bug triage).
- **Pre-Sales Consultant** - Verify feature availability, build a gap matrix, produce evidence for a proposal, compare CE vs EE side-by-side, or classify and cost hundreds of business requirements at scale with the BRL engine.
- **Sales AE** - Get ACA-structured responses to objections, risk-scored follow-up emails for stalled deals, a synthesized prospect profile from discovery notes, or triage an inbound support ticket into a customer-ready resolution draft.
- **Marketer** - Create content around Odoo features - blog posts, slide decks, social copy, multi-channel campaign plans - in marketing-ready language, and package a complete module for the Apps Store (icon, feature catalog, usage walkthroughs, illustrated landing) via `module-packaging`; individual skills: `odoo-doc-illustration`, `odoo-icon-design`, `odoo-doc-feature-map`, `odoo-doc-walkthrough`.
- **Strategist / CEO** - Get an executive risk overview of customizations, a structured customization inventory, or a competitor capability snapshot ready for a board or sales response.
- **Onboarding / Concierge** - Cross-cutting for every persona: `odoo-onboarding` bootstraps project context on a new engagement; `odoo-intake` takes ambiguous intent, brainstorms when vague, fast-paths when clear, routes to the right workflow or specialist, and always proposes a plan before any execution skill fires.

### How it works

Every agent - the main agent and every custom sub-agent - carries a shared universal **Work Ethos** (11 principles: completeness, root-cause, SSOT, and so on) loaded from `ODOO-AI-ETHOS.md` via a managed `@import` in your global `~/.claude/CLAUDE.md`.

Everything runs through the **main agent**, which acts as an **orchestrator + decision-maker
only** - it routes, decides at gates, and delegates the heavy work to specialists so its own
context stays clean across a long session. Roles: orchestrating context (main agent) ->
dispatched specialist (skill/workflow) -> named-agent interior worker (e.g. `odoo-coder`) or
fan-out leaf-worker. Multi-level nesting is supported (platform depth cap 5); `context: fork`
fan-out workers carry a hard-rules line that prevents them from dispatching further spawner
skills. Orchestrator skills that dispatch worker agents use the **Context-Handoff Protocol
(CHP)** - a 3-tier dispatch optimization (Tier A `SendMessage`-resume / Tier B fork /
Tier C fresh spawn + worklog) whose SSOT is `snippets/context-handoff-protocol.md`. Resources
are platform-managed.

`odoo-intake` is the front door for any plain-language intent. It (1) closes an intent gate (what /
why / what-done), (2) resolves the Odoo version - escalating to `odoo-onboarding` to pick
version/profile when it is unknown and OSM is reachable (inline-menu fallback), or asking you for
the version + repo path when OSM is down - (3) runs a quick read-only **recon** to make the plan
context-aware, then (4) emits a **Proposed Plan** and waits for your approval. From there:

- **Review / PR-review or debug intent** -> **fast-paths** straight to `odoo-code-review` /
  `odoo-debug`, skipping the planning ceremony (no Proposed-Plan block, no Plan Mode).
- **Single clear step** -> the one specialist fires; chat-only answers skip Plan Mode entirely.
- **Opt-in deep-survey** (offered on large jobs) -> if you approve `deep-survey`, `odoo-deep-survey`
  fans out a broad haiku sweep -> narrow sonnet dives -> an optional opus pass and writes a synthesis
  under `.odoo-ai/survey/` that re-informs a sharper Proposed Plan before any execution.
- **Multi-step** -> for non-trivial multi-module work the approved plan is authored by
  **`odoo-planning`** (via the `odoo-planner` agent) after `odoo-solution-design`: a wave-batched
  module-DAG that wires each module/stage to a SKILL and spans the full lifecycle (code -> review ->
  doc -> PR -> monitor -> merge). `odoo-intake` serializes it to a run file (`.odoo-ai/run-<id>.json`)
  and hands it to **`run-harness`** (the sequencer), which walks the
  work-items to `DONE` / `BLOCKED` / `NEEDS_CONTEXT`: pick the next ready node -> check its gate tier
  -> dispatch it (a leaf skill inline, a coding/review/UI **agent bundle**, a declarative **workflow**
  via `workflow-chaining`, or - for a coding wave-layer - the internal git-executor **`odoo-wave`**,
  which invokes `odoo-coding` per work-item, opens one squashed PR, and STOPS at the L2-squash-gate)
  -> read the step's **Continuation Contract** -> advance. Once a PR is open the async poller
  **`odoo-pr-monitoring`** drives it to merge (watches CI + review; any failure routes to
  `odoo-debug` with the re-push human-gated; the L2-merge-gate). A step can chain the next one
  (including across workflows via `on_complete`), so the run keeps moving without re-prompting.

Each step carries a **gate tier** that decides what stops for you (see
[Drive to done](#drive-to-done-how-to-use-it)). On a new Odoo project, `odoo-onboarding`
bootstraps `.odoo-ai/context.md` so later skills skip setup. Every skill grounds its answers
through the OSM MCP server; output is a direct answer or a file under `.odoo-ai/`.

```mermaid
flowchart TD
    A([Plain-language intent]) --> D{"odoo-intake<br/>router - owns Plan Mode"}
    D -->|"Vague"| E["Brainstorm options"]
    E -->|"approve"| D
    D -->|"Non-Odoo"| X["Route elsewhere"]
    D -->|"Review / debug"| SPEC["odoo-code-review<br/>/ odoo-debug"]
    D -->|"Forward-port / rebase / upgrade"| FP["Peer orchestrator pipeline<br/>(forward-port / git-rebase /<br/>modules-upgrade) - see detail below"]
    D -->|"Recon + Plan"| G{"Approved?"}

    G -->|"deep-survey opt-in"| DS["odoo-deep-survey<br/>haiku -> sonnet -> opus"]
    DS -->|"re-informs plan"| G
    G -->|"Single chat"| F1["Specialist fires"]
    G -->|"Single writes-files"| F2["Specialist + Plan"]
    G -->|"Multi-step"| GA["odoo-gap-analysis<br/>(optional)"]

    GA --> SD["odoo-solution-design<br/>(odoo-solution-architect)"]
    SD --> PLN["TIER 2 - odoo-planning<br/>-> odoo-planner (code) + odoo-doc-planner (doc)<br/>1 gate: ONE lifecycle code -> QA -> doc -> PR -> merge"]
    PLN -->|"approve -> ExitPlanMode<br/>-> serialize the run file"| RUN["TIER 3 - run-harness<br/>(sequencer)"]

    SPEC -->|"CRITICAL/HIGH"| FIX["Fix loop:<br/>review -> coding -> review (max 3)"]

    RUN --> PK{"next node + gate tier"}
    PK -->|"L2 irreversible"| STOP["STOP - human gate"]
    STOP -->|"approve"| PK
    PK -->|"leaf / agent bundle / workflow"| DISP["dispatch node"]
    PK -->|"coding wave-layer"| WAVE["TIER 4 - odoo-wave (git-executor, internal)<br/>per WI: worktree -> INVOKE odoo-coding<br/>-> cherry-pick -> end-of-wave review<br/>-> 1 PR + squash -> STOP at L2-squash-gate"]
    PK -->|"after coding waves"| DOCPREP["doc content prep (parallel, browser-free)<br/>odoo-doc-feature-map + odoo-doc-walkthrough<br/>+ odoo-icon-design"]
    DOCPREP --> DOC["odoo-doc-illustration (browser-serial)<br/>+ i18n (odoo-i18n)"]

    DISP -->|"UI/behavior blast-radius (opt-in L2)"| ACC["odoo-acceptance<br/>oracle -> live execute -> adjudicate"]
    ACC -->|"FAIL: debug -> coding"| FIX
    DISP --> CC["Continuation Contract"]
    ACC -->|"ACCEPTED + evidence"| CC
    DOC --> CC
    CC -->|"next / on_complete"| PK
    CC -->|"all done"| DONE([DONE / BLOCKED])

    WAVE -. "ASYNC boundary - not a blocking node" .-> MON["odoo-pr-monitoring<br/>/loop | /schedule poller"]
    MON -->|"CI warn/error/fail = D3"| DBG["odoo-debug -> odoo-coding<br/>re-push human-gated (X2)"]
    DBG --> MON
    MON -->|"green + approved"| MG["L2-merge-gate -><br/>merge + post-merge cleanup"]
    MG --> DONE

    F1 --> I[("OSM MCP")]
    F2 --> I
    DISP --> I
    WAVE --> I
    FIX --> I
    MON --> I
    I --> Z([Answer or .odoo-ai/])
```

_All agents (main + custom sub-agents) share a universal Work Ethos loaded from `ODOO-AI-ETHOS.md`; built-in Plan/Explore agents skip it by design._

### Drive to done - how to use it

Two dials decide how much the run does on its own and where it stops for you.

**1. Autonomy dial** (optional flag on your `/odoo-intake` request; default `--auto`):

| Flag | Behavior | Use when |
|------|----------|----------|
| `--auto` *(default)* | Drives the whole plan to done; stops only at irreversible/outward steps (**L2**) and when blocked | You want hands-off; you trust the approved plan |
| `--step` | Stops at **every** writes-files step for confirmation | High-stakes work; you want to inspect each change |
| `--plan` | Produces the plan (work-items + order) and stops - runs nothing | You just want the plan/estimate |

**2. Gate tiers** - every step is tagged, and the tier (not the dial) is what ultimately decides
a human stop. **L2 always stops for a human; the dial can never lower it.**

| Tier | What it is | Under `--auto` |
|------|-----------|----------------|
| **L0** | Read-only / chat answers | Auto-passes |
| **L1** | Writes internal files under `.odoo-ai/` (reversible, gitignored) | Auto-passes |
| **L2** | Irreversible / outward: git push or merge, sending to a customer, touching a live instance - **and any source-code write that was not in the approved plan** | **Always stops for you** |

**Best practice.** Start with a plain-language `/odoo-intake "<what you want>"`. Approve the plan once.
Let `--auto` carry the routine steps; you will be stopped exactly at the moments that matter
(anything leaving your machine or touching a customer/instance). Use `--step` when you want to
watch every edit, `--plan` when you only want the map. You never type a skill name.

> **For contributors / AI agents extending this plugin:** the authoritative, diagram-backed
> spec of this whole mechanism - the Continuation Contract, the `run-<id>.json` blackboard, the
> gate-tier derivation, and the command/skill/agent taxonomy - lives in
> [`docs/reference/workflow-harness.md` §8](docs/reference/workflow-harness.md).
> The per-skill orchestration registry (spawn class, output mode, gate tier) is
> [`docs/reference/ORCHESTRATION-MAP.md`](docs/reference/ORCHESTRATION-MAP.md),
> generated from `generator/skill_tool_deps.json`. Read those before changing routing or gates.

### Coding dispatch and model tiers

When a coding job spans several modules, `odoo-coding` assigns each module a **deterministic model
tier** at its Phase 0 gate - `haiku` (trivial boilerplate), `sonnet` (default), `opus` (core
override / cross-model / migration), or `fable` (rare Custom-XL, ~2x opus price, design-doc-first) -
recorded in the gate table and `plan.md`. It then dispatches the `odoo-coder` (backend) and
`odoo-frontend-coder` (frontend) agents as **subagents** in **model-weighted batches**: per
module the backend leg runs before the frontend leg, modules are ordered so each runs after its
in-set dependencies, and each round packs work up to a single model-weighted budget (the OOM
envelope), whose SSOT is [`skills/_shared/concurrency-guard.md`](skills/_shared/concurrency-guard.md):
WEIGHT `haiku=1 / sonnet=2 / opus=4 / fable=8`, at most **8 weight-units in flight** (so opus
throttles to 2 concurrent and fable runs exclusive). The plugin does NOT use the Claude Code
Workflow tool (JS) for codegen - all fan-out is real subagent launches.

The agent frontmatter `model:` is only a default - the dispatch `model` parameter overrides it per
work-item in either direction (same convention as `odoo-debug` and `odoo-solution-design`).

```mermaid
flowchart TD
    GATE["Phase 0 gate<br/>scope + module graph + tier"]
    GATE --> BATCH["model-weighted batches"]

    subgraph BUDGET["Budget: 8 weight-units"]
        W["haiku=1 / sonnet=2<br/>opus=4 / fable=8"]
    end

    BATCH --> BUDGET

    subgraph PERMOD["Per module"]
        BE["odoo-coder<br/>(backend)"] --> FE["odoo-frontend-coder<br/>(frontend)"]
    end

    BUDGET --> PERMOD
    PERMOD --> DEP["Dependency order<br/>+ batch barrier"]
    DEP --> PLAN["plan.md - tier + status"]
```

### Solution design decomposition

`odoo-solution-design` produces a flat single TDD (one module or simple scope) or a
master + N child TDDs (multi-module or large scope). Consumers resolve artifact paths from
the Continuation Contract - see
[`snippets/master-child-design-contract.md`](snippets/master-child-design-contract.md) for
the full schema and handoff fields.

```mermaid
flowchart TD
    SD["odoo-solution-design<br/>(odoo-solution-architect)"]
    SD -->|"single module / simple scope"| S["single TDD<br/>.odoo-ai/designs/slug-date.md<br/>DESIGN_DOC=path"]
    SD -->|"multi-module / large scope"| M["master + N child TDDs<br/>.odoo-ai/designs/master-slug/"]
    M --> IDX["index.yaml - routing SSOT<br/>_master-date.md - cross-module constraints<br/>module-date.md per module (DAG order)<br/>design_docs[] in Continuation Contract"]
```

## Workflows

The plugin ships 13 declarative workflows in `workflows/*.workflow.yaml`. Each workflow is
executed by the generic `workflow-chaining` skill, which reads the YAML and runs the declared
phase sequence with approval gates between phases. Adding a new workflow is a single YAML
file drop - no orchestration code required. A workflow may also declare an `on_complete`
transition (e.g. `qa-suite` -> `odoo-coding` when bugs are found); `run-harness` picks
that up and chains the next step across workflows automatically.

| Workflow | Trigger | Output dir |
|----------|---------|------------|
| `odoo-respond-bid` | Full bid / RFP response chain | `.odoo-ai/bids/` |
| `odoo-implement-feature` | Requirement to shipped code with a design step (scope -> design -> code -> review) | `.odoo-ai/implement/` |
| `odoo-plan-upgrade` | Comprehensive upgrade plan | `.odoo-ai/upgrade-plans/` |
| `odoo-position-feature` | Positioning copy for marketing and sales | `.odoo-ai/positioning/` |
| `discovery-pipeline` | Synthesize and structure discovery notes | `.odoo-ai/discovery/` |
| `qa-suite` | Static release test-plan + QA checklist + bug triage (non-executing; live acceptance/oracle -> `odoo-acceptance`) | `.odoo-ai/qa/` |
| `support-triage` | Classify + root-cause + draft resolution for a support ticket | `.odoo-ai/support/` |
| `video-produce` | Multi-scene Odoo demo video (storyboard -> record -> assemble) | `.odoo-ai/video/` |
| `sales-closing-cycle` | Late-stage sales cycle: objection handling + closing steps | `.odoo-ai/sales/` |
| `ui-debug-session` | Resumable multi-turn UI debug with browser evidence | `.odoo-ai/debug/` |
| `content-production` | Multi-asset content from a positioning brief | `.odoo-ai/content/` |
| `research-multiphase` | Flexible-phase research: broad survey -> deep dives -> synthesis, a different model tier per phase | `.odoo-ai/research/` |
| `module-packaging` | End-to-end: scope -> doc-plan (branch-aware, 1 gate) -> feature-map/walkthrough/icon/copy fan-out (browser-free, parallel) -> provision-capture per instance-path (incremental, branch-aware) -> manifest-audit; output `.odoo-ai/packaging/` | `.odoo-ai/packaging/` |

Commands come in two shapes: multi-phase orchestrators that chain several skills in a
gated sequence, and single-step wrappers that run one skill and offer a save step.

| Command | Skill chain | Output |
|---------|------------|--------|
| `/odoo-respond-bid` | discovery-summary -> gap-analysis -> capability-proof -> objection-handling -> assemble | `.odoo-ai/bids/` |
| `/odoo-position-feature` | feature-check -> addon-diff -> competitive-brief -> positioning | `.odoo-ai/positioning/` |
| `/odoo-plan-upgrade` | risk-overview -> deprecation-audit -> version-diff -> synthesis | `.odoo-ai/upgrade-plans/` |
| `/odoo-run-brl` | Gate 0 chunk plan -> classify + cost -> dependency DAG -> RTM + report | `.odoo-ai/brl/` |
| `/odoo-draft-followup` | odoo-deal-followup (single step) | `.odoo-ai/followups/` |
| `/odoo-summarize-discovery` | odoo-discovery-summary (single step) | `.odoo-ai/discovery/` |
| `/odoo-produce-video` | odoo-demo-recording per scene | `.odoo-ai/video/` |

The visual UI testing stack is a sibling cluster, not a linear chain: one `setup` step
provisions the browser environment, then four skills run independently and converge on
`odoo-coding` as the fix writer. When no reachable instance is detected, the visual
skills emit `NEEDS_NEXT -> odoo-instance` so a live instance can be provisioned
programmatically before the visual workflow resumes.

```mermaid
flowchart TD
    SETUP["/odoo-setup (one-time, interactive)"]
    SETUP --> MCPW["3 browser MCP servers<br/>chrome-devtools / playwright / pagecast"]
    SETUP --> CTX["context.md + instances.toml"]

    INST["odoo-instance skill<br/>(programmatic path)"]
    INST --> IOPS["odoo-instance-ops agent<br/>create / init / ensure-up<br/>odoo_db.py + 55-instance-ops.sh"]
    IOPS --> CTX

    MCPW --> SK["Visual skills ready"]
    CTX --> SK

    subgraph FIX_SKILLS["Diagnosis -> fix"]
        UID["odoo-debug"] --> FC["odoo-coding<br/>(fix writer)"]
        UIR["odoo-ui-review<br/>6-lens"] --> FC
        VR["odoo-visual-regression"] --> FC
    end

    SK --> FIX_SKILLS
    SK --> DR["odoo-demo-recording"]
    DR --> MEDIA["MP4 / GIF artifact"]

    subgraph DOC_PREP["Doc content prep (browser-free, parallel)"]
        FMP["odoo-doc-feature-map<br/>(feature-catalog.jsonl)"]
        WLK["odoo-doc-walkthrough<br/>(happy-path walkthroughs)"]
        ICN["odoo-icon-design<br/>(icon.png + icon.svg)"]
    end

    SK --> DOC_PREP
    DOC_PREP --> DOCSCOPER["odoo-doc-scoper<br/>(multi-module: resolves TARGET to modules[])"]
    DOCSCOPER --> DOCILL["odoo-doc-illustration<br/>(browser-serial; odoo-doc-illustrator)"]
    DOCILL --> DOCOUT["static/description/index.html<br/>+ index_&lt;locale&gt; per locale<br/>+ doc/index.rst"]

    FIX_SKILLS -. "no instance reachable" .-> INST
    SK -. "no instance reachable" .-> INST
```

### Forward-port pipeline (`/odoo-forward-port`)

A 12-phase orchestration that ports commits across Odoo series using intent-first extraction
(not raw code carry-over), merge-keep-SHA strategy, symbol-survival checking, pre-adapt drift
scan, adaptive test forwarding, and verify-by-behavior per batch. Two human STOP-gates bound the automation.

```mermaid
flowchart TD
    START(["/odoo-forward-port"])
    START --> P0["P0 - Recon + triage<br/>(read-only: enumerate commits,<br/>inline-triage model tier)"]

    subgraph P1_grp["P1 - Intent extract (parallel, read-only)"]
        P0 --> IE1["odoo-intent-extractor<br/>commit A"]
        P0 --> IE2["odoo-intent-extractor<br/>commit B...N"]
    end

    IE1 --> P2["P2 - Classify + installable-probe<br/>(4-outcome bucket via OSM;<br/>odoo-installable-prober for ambiguous cat-3)"]
    IE2 --> P2

    P2 -->|"bucket (c) complex"| P3["P3 - Design<br/>(route-out to odoo-solution-design;<br/>returns to forward-port)"]
    P3 --> P4_gate
    P2 -->|"bucket (a/b/d)"| P4_gate["P4 - Plan gate<br/>(EnterPlanMode / ExitPlanMode;<br/>plan.md written as resume record)"]
    P4_gate -->|"STOP - human approve"| P5["P5 - Git merge --no-commit<br/>(keep SHA)"]

    P5 --> P6["P6 - Symbol-survival check<br/>(7 classes: field/method/model/<br/>test-base/import/installable/orm-field-key)<br/>+ test-survival sub-check"]
    P6 --> P7["P7 - Pre-adapt drift scan<br/>(Lane 1: ALL .py - import+pyflakes+orm-field-key<br/>Lane 2: tests-only collect gate)"]

    subgraph P8_grp["P8 - Adapt (serial per commit, test-first)"]
        P7 --> PA["forward tests RED-on-target"]
        PA --> PB["adapt by bucket<br/>a=skip / b=3-way / c=reimplement / d=skip"]
        PB --> PC["migration rename gate + i18n dispatch"]
    end

    PC --> P9["P9 - Verify by behavior<br/>(ephemeral instance, RED then GREEN,<br/>confirm-by-toggle per batch)"]
    P9 -->|"STOP - human confirm"| P10["P10 - Gate merge<br/>(commit + checkpoint;<br/>loop to P5 for next commit)"]
    P10 --> P11["P11 - PR + code-review<br/>(mandatory for new engines)"]
    P11 --> DONE(["Done - .odoo-ai/forward-port/"])
```

| Phase | Description | Parallel? | Human gate? |
|-------|-------------|-----------|-------------|
| P0 Recon + triage | Enumerate commits; inline-triage model tier; read-only | - | - |
| P1 Intent extract | Dispatch odoo-intent-extractor per commit | Yes (N commits) | - |
| P2 Classify + installable-probe | 4-outcome bucket via OSM; odoo-installable-prober for ambiguous cat-3 | Serial per commit | - |
| P3 Design | CONDITIONAL: route-out to odoo-solution-design for complex bucket-(c) modules; returns to forward-port | Serial per commit | - |
| P4 Plan gate | EnterPlanMode / ExitPlanMode; plan.md written as resume record after approval | - | STOP - human approve |
| P5 Git merge --no-commit | Merge source commit onto target branch, keep SHA | Serial per commit | - |
| P6 Symbol-survival check | 7 classes (field/method/model/test-base/import/installable/orm-field-key) + test-survival sub-check | Serial per commit | - |
| P7 Pre-adapt drift scan | Lane 1: ALL .py (import+pyflakes+orm-field-key); Lane 2: tests-only collect gate | Serial per commit | - |
| P8 Adapt | Test-first per module; adapt by bucket (a=skip/b=3-way/c=reimplement/d=skip); migration dir retarget (C2) + i18n dispatch; C1 no-bump / C3 source-bug gate | Serial per commit | - |
| P9 Verify by behavior | Ephemeral instance, RED then GREEN, confirm-by-toggle per batch | Per-batch | - |
| P10 Gate merge | STOP then commit + checkpoint; loop to P5 for next commit | - | STOP - human confirm |
| P11 PR + code-review | Open PR; mandatory code-review for new engines | - | - |

### Git-rebase pipeline (`/odoo-git-rebase`)

A 13-phase orchestration (P0-P12, with P8b and P9b sub-phases) that replays commits across Odoo
series using intent-aware conflict resolution, scale-conditional design before Plan Mode, an
in-pipeline code-review-and-fix loop after adapt, and a final pre-merge PR review. Two human
STOP-gates bound the automation; a third automated review gate (P9b) catches defects before verify.

```mermaid
flowchart TD
    START(["/odoo-git-rebase"])
    START --> P0["P0 - Intake / resolve<br/>(sonnet; clarify gate if open_questions)"]
    P0 --> P1["P1 - Recon<br/>(enumerate range, patch-id pre-filter,<br/>EXTRACT-tier triage)"]

    subgraph P2_grp["P2 - Intent extract (parallel, read-only)"]
        P1 --> IE1["odoo-intent-extractor<br/>commit A (rebase MODE)"]
        P1 --> IE2["odoo-intent-extractor<br/>commit B...N"]
    end

    IE1 --> P3["P3 - Cluster behavior comparison<br/>(opus; 4-outcome a/b/c/d + failure mode)"]
    IE2 --> P3
    P3 --> P4["P4 - Classify (record only)<br/>(assign one outcome a/b/c/d per commit)"]

    P4 -->|"(c) do-now non-trivial,<br/>OR (b) field/sig/override-point change,<br/>OR (b) > 3 files / >= 2 modules,<br/>OR full-stack"| P5["P5 - Design (route-out to<br/>odoo-solution-design; returns)"]
    P5 --> P6_gate
    P4 -->|"(a)/(d), OR trivial single-symbol (b)"| P6_gate["P6 - Plan Mode gate<br/>(EnterPlanMode / ExitPlanMode;<br/>decides adapt strategy BEFORE rebase)"]
    P6_gate -->|"STOP - human approve"| P7["P7 - Create integration worktree<br/>+ git rebase --onto (rebase starts)"]

    subgraph P8_grp["P8 - Conflict-resolution loop (per stopped commit)"]
        P7 --> CR1["Explore reads conflict + intent"]
        CR1 --> CR2["odoo-coder / odoo-frontend-coder<br/>resolve hunks to INTENT (ADAPT tier)"]
        CR2 --> CR3["git rebase --continue / --skip"]
        CR3 -.->|"more stopped commits"| CR1
    end

    CR3 --> P8b["P8b - Symbol-survival + collection gate<br/>(MUST; autosilent symbol-break catch)"]
    P8b --> P9["P9 - Test forward<br/>(adapt branch tests RED then GREEN)"]

    subgraph P9b_grp["P9b - In-pipeline code-review loop (fix-until-clean)"]
        P9 --> RV["odoo-code-review -> odoo-code-reviewer<br/>(scoped to adapt diff)"]
        RV -->|"CRITICAL/HIGH findings<br/>(cap 3, else escalate BLOCKED)"| FX["odoo-coding<br/>(fix to root cause)"]
        FX --> RV
    end

    RV -->|"clean: no CRITICAL/HIGH"| P10["P10 - Verify<br/>(range-diff + dup-guard + conditional instance)"]
    P10 -->|"STOP - human confirm"| P11["P11 - Gate (human-confirm)"]
    P11 --> P12["P12 - PR + FINAL review (human merge; never squash)"]
    P12 --> DONE(["Done - .odoo-ai/git-rebase/"])
```

Two review points are visible: the **P9b in-pipeline code-review loop** (fix-until-clean, right
after the adapt, before verify) AND the **P12 final PR review** (pre-merge). This is intentionally
more rigorous than forward-port (PR review only).

| Phase | Description | Parallel? | Human gate? |
|-------|-------------|-----------|-------------|
| P0 Intake / resolve | Clarify gate if open questions; read-only | - | - |
| P1 Recon | Enumerate range; patch-id pre-filter; EXTRACT-tier triage | - | - |
| P2 Intent extract | Dispatch odoo-intent-extractor per commit in rebase MODE | Yes (N commits) | - |
| P3 Cluster behavior comparison | Opus; 4-outcome a/b/c/d + failure mode per commit | - | - |
| P4 Classify | Assign one outcome a/b/c/d per commit (record only) | Serial per commit | - |
| P5 Design | CONDITIONAL: route-out to odoo-solution-design when non-trivial (see design-trigger table); returns | Serial per commit | - |
| P6 Plan Mode gate | EnterPlanMode / ExitPlanMode; decides adapt strategy BEFORE rebase starts | - | STOP - human approve |
| P7 Create integration worktree + rebase | Create worktree; git rebase --onto (rebase starts here) | - | - |
| P8 Conflict-resolution loop | Per stopped commit: explore conflict + intent; odoo-coder / odoo-frontend-coder resolve hunks to INTENT; git rebase --continue / --skip | Serial per commit | - |
| P8b Symbol-survival + collection gate | MUST run; autosilent symbol-break catch before test forward | - | - |
| P9 Test forward | Adapt branch tests RED then GREEN | - | - |
| P9b Code-review loop | In-pipeline: odoo-code-review -> odoo-code-reviewer scoped to adapt diff; fix via odoo-coding on CRITICAL/HIGH; cap 3 iterations; automated fix-until-clean | - | - |
| P10 Verify | Range-diff + dup-guard + conditional instance | - | STOP - human confirm |
| P11 Gate | Human-confirm gate | - | STOP - human confirm |
| P12 PR + FINAL review | Open PR; mandatory final code-review before human merge; never squash | - | - |

### Modules-upgrade pipeline (`/odoo-modules-upgrade`)

An 8-phase orchestration (P0-P7, with P1d, P2b, P4b, and P5.7 sub-phases) that upgrades custom
Odoo modules (v8-v19) across a major version jump using dependency-ordered absorption,
scale-conditional design before Plan Mode, an in-pipeline per-module code-review-and-fix loop
after adapt, and a final pre-merge dep-order PR review. Two human STOP-gates bound the
automation; a third automated review gate (P4b) catches defects before the install/test wave.

```mermaid
flowchart TD
    START(["/odoo-modules-upgrade"])
    START --> P0["P0 - Intake / resolve<br/>(sonnet; clarify scope if open_questions)"]

    subgraph P1_grp["P1 - Recon (parallel, 4 lanes)"]
        P0 --> R1["Explore: dependency DAG<br/>(topo-sort, leaves first)"]
        P0 --> R2["odoo-deprecation-audit"]
        P0 --> R3["odoo-version-diff"]
        P0 --> R4["P1d - Transitive Symbol Survey<br/>(Explore, read-only; emits blockers[] at target)"]
    end

    subgraph P2_grp["P2 - Core-absorption comparison (per module, dep order)"]
        R1 --> CMP["odoo-diff-comparator + odoo-gap-analysis<br/>verdict: DELETE / KEEP / REWRITE(api) /<br/>REWRITE(model) / MERGE / SPLIT / RECONCILE / OBSOLETE"]
    end
    R2 --> CMP
    R3 --> CMP
    R4 --> CMP

    CMP -->|"MERGE / SPLIT / RECONCILE /<br/>REWRITE(model field-type) / DELETE-with-risk,<br/>OR non-trivial REWRITE(api)/KEEP"| P2b["P2b - Hard-call design<br/>(route-out to odoo-solution-design; returns)"]
    P2b --> P3_gate
    CMP -->|"DELETE-no-risk / OBSOLETE, OR trivial<br/>REWRITE(api)/KEEP (<= 5 call sites, 1 module)"| P3_gate["P3 - Plan Mode gate<br/>(EnterPlanMode / ExitPlanMode;<br/>per-DELETE confirms)"]
    P3_gate -->|"STOP - human approve + per-DELETE confirm"| P4["P4 - Adapt (per module, dep order,<br/>child worktrees: odoo-coding)"]

    subgraph P4b_grp["P4b - In-pipeline code-review loop (per module, dep order, fix-until-clean)"]
        P4 --> RV["odoo-code-review -> odoo-code-reviewer<br/>(scoped to each module's adapt diff)"]
        RV -->|"CRITICAL/HIGH findings<br/>(cap 3, else escalate BLOCKED)"| FX["odoo-coding<br/>(fix to root cause)"]
        FX --> RV
    end

    RV -->|"clean: no CRITICAL/HIGH (all modules)"| P5["P5 - Install + test gate<br/>(ephemeral instance, wave-by-wave, demo=on)"]
    P5 -->|"red wave -> debugger -> back to P4"| P4
    P5 -->|"all waves green"| P57["P5.7 - i18n reconcile<br/>(gated-on; auto-SKIP if no translatable surface change)"]
    P57 --> P6["P6 - Gate (STOP, human sign-off)"]
    P6 -->|"STOP - human confirm"| P7["P7 - PR + FINAL dep-order review (human merge; no cluster-squash)"]
    P7 --> DONE(["Done - .odoo-ai/modules-upgrade/"])
```

Two review points are visible: the **P4b in-pipeline code-review loop** (per module, dep order,
fix-until-clean, right after the adapt, before the install/test gate) AND the **P7 final dep-order
PR review** (pre-merge). This is intentionally more rigorous than forward-port (PR review only).

| Phase | Description | Parallel? | Human gate? |
|-------|-------------|-----------|-------------|
| P0 Intake / resolve | Clarify scope if open questions; read-only | - | - |
| P1 Recon | Parallel (4 lanes): dependency DAG (topo-sort); odoo-deprecation-audit; odoo-version-diff; P1d transitive-symbol survey | Yes (4 lanes) | - |
| P1d Transitive Symbol Survey | (sub-phase of P1, parallel) Scans cluster for every symbol referencing external/core deps; grounds each at target; emits blockers[] used as preemptive fix list in P4 | Part of P1 | - |
| P2 Core-absorption comparison | odoo-diff-comparator + odoo-gap-analysis per module in dep order; emits verdict per module | Serial per module | - |
| P2b Hard-call design | CONDITIONAL: route-out to odoo-solution-design for MERGE / SPLIT / RECONCILE / REWRITE(model field-type) / DELETE-with-risk and non-trivial REWRITE(api)/KEEP; returns | Serial per module | - |
| P3 Plan Mode gate | EnterPlanMode / ExitPlanMode; per-DELETE confirmation before any file deletion | - | STOP - human approve |
| P4 Adapt | Per module in dep order; child worktrees; odoo-coding; P1d blockers[] prepended as preemptive fix list; manifest bump profile-gated | Serial per module | - |
| P4b Code-review loop | In-pipeline per module dep order: odoo-code-review -> odoo-code-reviewer scoped to each module's adapt diff; fix via odoo-coding on CRITICAL/HIGH; cap 3 iterations per module; automated fix-until-clean | Serial per module | - |
| P5 Install + test gate | Ephemeral instance; wave-by-wave green with demo=on (no separate framework-validation phase); red wave loops back to P4 via debugger | Per wave | - |
| P5.7 i18n reconcile | GATED-ON; auto-SKIP when no translatable surface changed; when active: polib-merge existing .po into P5 instance (never regenerate) | - | - |
| P6 Gate | Human sign-off after all waves green | - | STOP - human confirm |
| P7 PR + FINAL dep-order review | Open PR; Runbot parity gates + convention-compliance pass; mandatory final dep-order code-review; no cluster-squash (per-module consolidation to 1 clean commit per module allowed) | - | - |

### Module-packaging workflow (`module-packaging`)

End-to-end pipeline that packages a module for the Odoo Apps Store: scope inline, doc-plan (branch-aware, single whole-plan gate), browser-free content prep in parallel, then branch-aware per-instance-path provision-capture (incremental install -> doc -> commit), and a final manifest audit. P0.5 (`odoo-doc-planner`) clusters modules and allocates instances; after the gate, P1-P4 run fully in parallel; P3 (icon) writes directly to `static/description/` without waiting for P5; P5 (`provision-capture`, fused) runs per instance-path - parallel across paths, sequential within - incremental install leaf-first then doc then git commit; P6 audits inline; P7 aggregates output under `.odoo-ai/packaging/`.

```mermaid
flowchart TD
    PKG_START(["module-packaging"])
    PKG_START --> PKG_P0["P0 - Scope inline<br/>resolve module, read manifest,<br/>detect existing assets"]

    PKG_P0 --> PKG_P05["P0.5 - doc-plan (odoo-doc-planner)<br/>cluster modules, allocate instances branch-aware<br/>emit doc-plan.yaml + ONE whole-plan gate"]

    subgraph PKG_FANOUT["P1-P4: browser-free Mode B (parallel)"]
        PKG_P1["P1 - odoo-doc-feature-map<br/>(feature-catalog.jsonl)"]
        PKG_P2["P2 - odoo-doc-walkthrough<br/>(happy-path walkthroughs)"]
        PKG_P3["P3 - odoo-icon-design<br/>(icon.png + icon.svg)<br/>writes static/description/ directly"]
        PKG_P4["P4 - odoo-content-draft<br/>(Apps Store copy + description)"]
    end

    PKG_P05 --> PKG_P1
    PKG_P05 --> PKG_P2
    PKG_P05 --> PKG_P3
    PKG_P05 --> PKG_P4

    PKG_P1 --> PKG_P5["P5 - provision-capture (per instance-path)<br/>odoo-instance + odoo-doc-illustration + git-ops<br/>parallel ACROSS paths (<=W); sequential WITHIN<br/>incremental: install leaf-first -> doc -> commit"]
    PKG_P2 --> PKG_P5
    PKG_P4 --> PKG_P5
    PKG_P3 -. "icon written directly; no P5 dep" .-> PKG_ICON["icon.png + icon.svg<br/>in static/description/"]

    PKG_P5 --> PKG_P6["P6 - Manifest audit inline<br/>check __manifest__.py summary/website/<br/>category vs catalog; flag drift"]

    PKG_P6 --> PKG_P7["P7 - Aggregate<br/>.odoo-ai/packaging/ index<br/>asset manifest + diff summary"]

    PKG_P7 --> PKG_DONE(["DONE - .odoo-ai/packaging/"])
    PKG_ICON --> PKG_DONE
```

| Phase | Description | Parallel? | Browser? |
|-------|-------------|-----------|----------|
| P0 Scope | Resolve module, read manifest, detect existing assets | - | - |
| P0.5 doc-plan | `odoo-doc-planner` -> cluster modules, allocate instances branch-aware, emit doc-plan.yaml; ONE whole-plan gate | - | - |
| P1 Feature-map | `odoo-doc-feature-map` -> feature-catalog.jsonl | Part of P1-P4 fanout | - |
| P2 Walkthrough | `odoo-doc-walkthrough` -> happy-path walkthroughs | Part of P1-P4 fanout | optional |
| P3 Icon | `odoo-icon-design` -> icon.png 256x256 + icon.svg, written directly to static/description/ | Part of P1-P4 fanout (independent) | - |
| P4 Copy | `odoo-content-draft` -> Apps Store copy + description | Part of P1-P4 fanout | - |
| P5 provision-capture (FUSED) | `odoo-instance` + `odoo-doc-illustration` + `git-ops` per instance-path; incremental install leaf-first -> doc -> commit per module | Parallel ACROSS paths (<=W); sequential WITHIN | YES (per-path serial) |
| P6 Manifest audit | Inline: audit __manifest__.py summary/website/category vs catalog; flag drift | - | - |
| P7 Aggregate | Write .odoo-ai/packaging/ index, asset manifest, diff summary | - | - |

### Available commands

> `/odoo-semantic-mcp:connect` ships in the `odoo-semantic-mcp` plugin and is not counted among the 8 commands of this plugin.

| Command | Purpose | Chained skills |
|---------|---------|----------------|
| `/odoo-respond-bid` | Full bid response chain for RFP/requirements documents, saves to `.odoo-ai/bids/` | `odoo-discovery-summary` -> `odoo-gap-analysis` -> `odoo-capability-proof` -> `odoo-objection-handling` |
| `/odoo-draft-followup` | Sales follow-up email saved to `.odoo-ai/followups/` | `odoo-deal-followup` |
| `/odoo-summarize-discovery` | Synthesize discovery notes into a structured profile, saves to `.odoo-ai/discovery/` | `odoo-discovery-summary` |
| `/odoo-position-feature` | Positioning copy for marketing and sales use, saves to `.odoo-ai/positioning/` | `odoo-feature-check` -> `odoo-addon-diff` -> `odoo-competitive-brief` -> positioning copy |
| `/odoo-plan-upgrade` | Comprehensive upgrade plan (replaces legacy `odoo-upgrade-planner` agent), saves to `.odoo-ai/upgrade-plans/` | `odoo-risk-overview` -> `odoo-deprecation-audit` -> `odoo-version-diff` -> synthesis |
| `/odoo-run-brl` | Bulk requirement-list classification at scale (chunked, resumable), saves to `.odoo-ai/brl/<job-id>/` | `odoo-brl` (sequential-outer-parallel-inner) |
| `/odoo-produce-video` | Multi-scene Odoo demo video (storyboard -> record -> assemble), saves to `.odoo-ai/video/` | `odoo-demo-recording` (per scene) |
| `/odoo-ai-agents:odoo-setup` | One-shot idempotent setup for the visual workflow - wires 3 browser MCP servers across Claude/Codex/Gemini, installs browser deps, auto-allows tool permissions, discovers + optionally spins up a local Odoo instance | - |

## Use cases - day in the life

### Use case 1 - Sales AE: stalled deal, draft a follow-up email in 30 seconds

A manufacturing SME prospect has not replied in 21 days after the demo. Pipeline stage is "evaluation." You need a follow-up email tonight to send tomorrow morning.

```
You: "Deal with Customer A stalled 21 days after demo, manufacturing SME evaluating
Odoo vs SAP. At the last meeting they promised technical feedback within the week.
Write a follow-up email."
```

Skill `odoo-deal-followup` fires. Output: risk score (red - warm lead, >14 days no reply), next-best-action ("re-engage with concrete value proof"), and a 4-paragraph follow-up email. To save it: `/odoo-draft-followup` chains the skill and writes to `.odoo-ai/followups/customer-a-2026-MM-DD.md`.

### Use case 2 - Pre-Sales: RFP with 15 requirements

A prospect sends an RFP with 15 functional requirements: lot tracking, multi-level approval, reporting, multi-warehouse, customer portal, and more. You need a complete response within 24 hours.

```
You: "/odoo-respond-bid - Customer B (F&B chain, 50 locations), 15 requirements listed below"
```

The command runs a gated workflow: `odoo-discovery-summary` (prospect profile) -> `odoo-gap-analysis` (effort matrix: Standard / Config / Extension / Custom + S/M/L/XL days) -> `odoo-capability-proof` (evidence for covered items) -> `odoo-objection-handling` (2-3 anticipated objections) -> assemble proposal -> save to `.odoo-ai/bids/customer-b-2026-MM-DD.md`. You approve each phase before the next fires.

### Use case 3 - Pre-Sales: BRL scoping for a large implementation

A prospect hands you a spreadsheet with 800 business requirements. You need a full implementation cost estimate, dependency ordering, and a requirement traceability matrix (RTM) before the proposal meeting.

```
You: "/odoo-run-brl - Customer C (retail chain), 800 requirements, Odoo 17, VN rates"
```

The BRL engine runs in a chunked pipeline (50 requirements per chunk): 4-way classification (CE / EE / Viindoo / Custom) with OSM evidence per item, deterministic cost lookup (no fabricated numbers), dependency DAG with Kahn topological sort, and phase-by-phase implementation sequencing. Two gates keep you in control - Gate 0 (approve chunk plan and cost config) and Gate E (approve deliverables before any file is written). Output: `rtm.csv` (Excel-ready RTM), `dag.mermaid` (implementation phases), `cost.json` (project budget roll-up with phase breakdown), and `report.md` (executive summary). The session is fully resumable: if interrupted, re-run the command and it picks up from the last completed chunk.

### Use case 4 - Strategist / founder: monthly board brief

You need a board status brief covering product progress, pipeline health, competitive landscape, and top risks before next week's investor meeting.

```
You: "Summarize competitive landscape - Competitor A vs your Odoo distribution -
for next week's board meeting."
```

Skill `odoo-competitive-brief` fires. It pulls competitor signals from context, the vault, or a web search (you can also supply them inline); the skill structures them into a market snapshot, capability matrix, GTM moves, threat assessment, and recommended product response - ready for a board deck. Combine with `odoo-risk-overview` (founder-level engineering risk dashboard) and `odoo-customization-inventory` (all custom modules with business purpose, M&A due-diligence ready).

### Use case 5 - Engineer + Coder: upgrade v15 to v17

Customer D is running Odoo 15 with 12 custom modules and wants to move to v17 in Q3.

```
You: "/odoo-plan-upgrade - Customer D, v15 to v17, 12 custom modules, deadline Q3"
```

Chains `odoo-risk-overview` -> `odoo-deprecation-audit` -> `odoo-version-diff` -> synthesis. Output: executive risk overview, code-level deprecation findings, API/feature diff, action ordering, S/M/L/XL effort estimate, and rollback plan. Saves to `.odoo-ai/upgrade-plans/customer-d-v15-v17-2026-MM-DD.md`. When you need actual code written, invoke the `odoo-coder` agent bundle (restricted-tool autonomy, OSM access).

### Use case 6 - Marketer: launch a new feature campaign

You just shipped a new inventory forecasting feature and need launch positioning plus ready-to-publish copy for blog, LinkedIn, and email.

```
You: "/odoo-position-feature - inventory forecasting module, target SME manufacturers,
launch window 2 weeks, main competitor SAP Business One"
```

The command chains `odoo-feature-check` (verifies the feature and reads its scope from OSM) -> `odoo-addon-diff` (CE vs EE edition framing) -> `odoo-competitive-brief` (how it lands against SAP B1) -> positioning synthesis. Output: a one-line value proposition, three proof points, objection rebuttals, and channel-by-channel copy. Saves to `.odoo-ai/positioning/inventory-forecasting-2026-MM-DD.md`. For a full multi-week campaign blueprint, follow up with `odoo-campaign-plan`; for per-asset drafts (blog, email sequence, social), call `odoo-content-draft`.

### Use case 7 - QA / Visual: catch visual regressions after installing a module

Your team just installed a third-party module and you need to confirm no existing screens broke before handing off to the client.

```
You: "Run visual regression on the invoicing list and form views after installing
module account_followup on Customer E's staging instance."
```

Run `/odoo-ai-agents:odoo-setup` once to provision the browser automation stack. Then skill `odoo-visual-regression` fires: it captures before/after screenshots of targeted views, diffs them, and flags regressions with severity labels. Where a defect is confirmed, `odoo-ui-review` follows up with a 6-lens audit (aesthetics / function / stability / accessibility / performance / design-system + theme fidelity) and surfaces the exact CSS or XML path to fix. Fixes are handed to `odoo-coding`, which writes the override and shows a patch preview before applying.

### Use case 8 - Support: triage an inbound customer ticket

A customer reports that their invoice approval workflow is broken after a recent module update. You need to classify, root-cause, and draft a resolution note in one pass.

```
You: "Customer F reports: invoice approval button disappeared after installing
account_invoice_approval v14. Users are blocked."
```

Skill `odoo-support-triage` fires. It classifies the ticket (bug - UI regression), generates a root-cause hint using OSM to inspect the `account` module's approval flow and the installed module's view overrides, and drafts a resolution note ready to send to the customer. If a live browser is available, it NL-dispatches to `odoo-debug` to capture the console error and pinpoint the broken view. Output saved to `.odoo-ai/support/customer-f-2026-MM-DD.md`.

### Frequently asked questions

**I only need one skill - do I have to know all 53?** No. Skills auto-fire by intent match. Describe what you need; the right skill triggers. `odoo-intake` acts as a brainstorm partner when you are not sure which skill to use.

**What if the OSM server is offline?** Each skill has a `## Standalone-first fallback` section - it degrades gracefully by reading your local codebase and `.odoo-ai/context.md` directly (Read/Grep/WebFetch, three-tier grounding) instead of asking you to paste data; if a browser is genuinely unreachable a visual skill returns BLOCKED rather than requesting screenshots. The plugin does not break when OSM is offline.

**What about confidentiality?** Plugin code is public (MIT). Skills contain no customer-specific data or pricing. A pre-commit hook and CI scan block several categories of sensitive content. Examples use abstract labels (Customer A through Customer F).

**Multi-runtime?** Skills and commands are written for Claude Code. Codex/Gemini parity is smoke-tested in `tests/smoke/runtime_parity.md` - 10 representative skills verified across all three runtimes.

**Why did a coding task run on a bigger (or smaller) model?** `odoo-coding` assigns each module a model tier deterministically at its Phase 0 gate (haiku/sonnet/opus/fable, sonnet default) from the design-doc effort tier or file/LOC/override heuristics, and you approve it before any agent fires. The tier is recorded in `plan.md`; a fable (top-tier, ~2x opus) row only appears for Custom-XL work and is itself the cost gate you sign off.

**How do I add a new workflow?** Drop a `*.workflow.yaml` file in `workflows/` following the schema in `workflows/_schema.md`. The `workflow-chaining` auto-discovers it. No `plugin.json` edit needed.

## Quick install (Claude Code - 3 steps, all required)

Inside Claude Code, run:

```
/plugin marketplace add Viindoo/claude-plugins   # one-time, if not already registered
/plugin install odoo-ai-agents@viindoo-plugins   # auto-pulls odoo-semantic-mcp
/odoo-semantic-mcp:connect
```

Installing `odoo-ai-agents` **automatically pulls in `odoo-semantic-mcp`** via the plugin dependency, so you get the skills, agents, commands, and the MCP connection in one step. Then **restart Claude Code**.

**On first session after install**, a SessionStart hook adds a managed `@import` block of `ODOO-AI-ETHOS.md` to your **global `~/.claude/CLAUDE.md`**. Because CLAUDE.md is loaded by every Claude Code session (and `@import` is resolved recursively), these principles apply to **all your Claude Code projects**, not only Odoo work. The current session gets coverage immediately via `additionalContext`; subsequent sessions load the file through the `@import`.

- **Opt out:** set `ODOO_AI_NO_ETHOS_IMPORT=1` before starting Claude Code (dedicated var - independent of `ODOO_AI_NO_AUTO_PERMS`).
- **Uninstall cleanup:** removing the plugin leaves an orphan `@import` block in `~/.claude/CLAUDE.md`. To fully remove it, delete the sentinel-marked block between `<!-- BEGIN odoo-ai-agents ETHOS import ... -->` and `<!-- END odoo-ai-agents ETHOS import -->` from `~/.claude/CLAUDE.md` manually.

You will need an **API key** (format `osm_...`) from the [install page](https://odoo-semantic.viindoo.com/install/), and the **MCP server URL** (default `https://odoo-semantic.viindoo.com/mcp`). For MCP-only setup and the `connect` command details, see the companion [`odoo-semantic-mcp`](../odoo-semantic-mcp/) plugin.

### Browser MCP servers / cross-CLI install

The four Visual skills (`odoo-ui-review`, `odoo-visual-regression`,
`odoo-demo-recording`, `odoo-doc-illustration`) need three browser MCP servers: `chrome-devtools`, `playwright`,
and `pagecast`. Each runtime bundles them natively:

| Runtime | How it ships | What to run |
|---------|-------------|-------------|
| **Claude Code** | Bundled `.mcp.json` (auto-loaded on plugin install). Claude deduplicates by command - a same-command server already in your config wins silently. No manual step. | Nothing extra after `claude plugin install`. |
| **Gemini CLI** | `gemini-extension.json` in the plugin directory. **Gemini requires a repo root**, so install via local path: `gemini extensions install <your-clone>/plugins/odoo-ai-agents` (or `...link ...` for live dev). Dedup is by server name. The `trust` field is not allowed in the extension manifest. | `gemini extensions install <your-clone>/plugins/odoo-ai-agents` |
| **Codex CLI** | `.codex-plugin/plugin.json`. Installed from a marketplace snapshot: `codex plugin marketplace add <marketplace>` then `codex plugin add odoo-ai-agents@<marketplace>` (marketplace.json to be published separately). | `codex plugin add odoo-ai-agents@<marketplace>` |

**Fallback (Codex/Gemini without native install):** run `/odoo-ai-agents:odoo-setup runtime`
inside Claude Code - it writes the correct browser server config for Codex and Gemini
idempotently. It does **not** write to `~/.claude.json` for Claude Code (served by the
bundled `.mcp.json`).

Full details and manual snippets: [`docs/setup.md` - Visual stack / browser MCP setup](docs/setup.md#visual-stack--browser-mcp-setup).

## Renaming - migrating from `odoo-semantic-skills`

This plugin was renamed `odoo-semantic-skills` -> `odoo-ai-agents` (Odoo AI Agent Team).
If you have the old plugin installed, switch over:

    /plugin uninstall odoo-semantic-skills@viindoo-plugins
    /plugin marketplace update viindoo-plugins
    /plugin install odoo-ai-agents@viindoo-plugins     # auto-pulls odoo-semantic-mcp
    /odoo-semantic-mcp:connect

Then restart Claude Code. Your OSM API key + MCP URL are unchanged; the MCP server
(`odoo-semantic`) and sibling plugin (`odoo-semantic-mcp`) are NOT renamed, so anything using
`mcp__odoo-semantic__*` keeps working. After reinstalling, re-run
`/odoo-ai-agents:odoo-setup permissions` to re-allow the bundled browser MCP tools under the
new `mcp__plugin_odoo-ai-agents_*` prefix.

## Reference

### Grounding contracts (SSOT snippets)

There are two distinct loading mechanisms for shared context:

**Global universal principles** (`ODOO-AI-ETHOS.md`) - a single SSOT file containing 11 work-ethic principles (completeness, root-cause analysis, SSOT, ASCII hyphens, and so on) that apply across all agents and all of your Claude Code projects. A SessionStart hook writes a managed `@import` block to your global `~/.claude/CLAUDE.md`; because `@import` is resolved recursively, the main agent and every custom sub-agent in any project inherit these principles automatically. Built-in Plan/Explore agents skip CLAUDE.md by design and are NOT covered. Edit `ODOO-AI-ETHOS.md` once and all agents pick it up on the next session restart.

**Per-agent snippet contracts** - agents reference `${CLAUDE_PLUGIN_ROOT}/snippets/...` directly in their bodies (edit the snippet once, not each of the agents that consume it):

| Contract | What it enforces |
|----------|------------------|
| `snippets/odoo-platform-design-principles.md` | Multi-company (+ branch v17+), generic-before-localization (lift shared behavior out of `l10n_*`), and the standard app-menu shape (root + Reports + Configuration) |
| `snippets/bidirectional-impact.md` | Survey upstream (the `depends` closure) AND downstream (`impact_analysis` dependents), direct + indirect, before touching a module - at design, code, review, and debug time |
| `snippets/demo-data-dynamic.md` | Demo data is time-relative (`relativedelta`) and lives in `demo/`, kept distinct from test fixtures |
| `snippets/read-before-write-contract.md` | Read the target version's coding guidelines (`skills/_shared/coding_guidelines/<version>/`) BEFORE writing code and conform on the first pass - not patched against a checklist afterward |
| `snippets/test-first-contract.md` | Red-before-green: the behavior test is authored and fails BEFORE the code, and is never weakened to pass (drives the `code -> review+test -> code` loop, bounded to 3 rounds) |
| `snippets/test-behavior-contract.md` | Tests drive the REAL workflow (call `action_confirm`/`action_validate`/`button_validate`, build via `Form()` for onchange, `with_user()` not `sudo()` for access) and assert observable outcomes - never seed the terminal state with `create({'state': ...})`, which hides transition/constraint/onchange bugs |
| `snippets/worklog-contract.md` | Append-only cross-agent decision journal (`.odoo-ai/worklog/<run>/<NNN>-<agent>.md`) read at start, appended at end, so a later phase can look up why an earlier one decided what it did |
| `snippets/context-handoff-protocol.md` | 3-tier agent dispatch optimization (Tier A `SendMessage`-resume / Tier B `subagent_type: "fork"` / Tier C fresh spawn + worklog); Tier C is the always-correct SSOT fallback; consumed by `odoo-coding`, `odoo-code-review`, `odoo-wave`, `odoo-forward-port`, `odoo-deep-survey`, `odoo-brl`. The `handoff` metadata field (`send-message \| fork \| fresh`) is surfaced per-skill in `docs/reference/ORCHESTRATION-MAP.md` |
| `snippets/new-module-manifest.md` | Greenfield `__manifest__.py` authoring: scaffold-first, preserve commented placeholder keys, and use the short version form (`0.1` / `1.0.0`) - never the series-prefixed `17.0.1.0.0` form on a new module (enforced by `odoo-coder`, `odoo-frontend-coder`, and `odoo-code-reviewer`) |
| `snippets/upg-conventions.md` | Viindoo upgrade + module-rename conventions (Viindoo Standard/Internal profile, OSM-gated): keeping the manifest `version` unchanged on a code-level upgrade; a renamed module's `__manifest__.py` must carry `old_technical_name` so Viindoo tooling can map the old name to the new one; does not replace OpenUpgrade DB-level rename (consumed by `odoo-coder`, `odoo-code-reviewer`) |
| `skills/_shared/odoo-module-graph.md` | The Odoo module DAG (from each `__manifest__.py` `depends`); `odoo-planning` is the canonical producer of the wave-batched result, which `odoo-coding` and `odoo-wave` consume so all dispatch in dependency order and respect module boundaries |

### Skills (53)

Per-persona quick-start guides live in [`docs/personas/`](docs/personas/).

| Skill | Persona | Description |
|-------|---------|-------------|
| `odoo-risk-overview` | Strategist / CEO | Executive risk overview of customizations before upgrade |
| `odoo-customization-inventory` | Strategist / CEO | Structured inventory of all custom modules and their business purpose |
| `odoo-competitive-brief` | Strategist | Competitor capability snapshot structured for board or sales response |
| `odoo-override-finding` | Engineer | Find the correct override point and pattern for a method |
| `odoo-deprecation-audit` | Engineer | Audit deprecated API usage for upgrade readiness |
| `odoo-deploy-checklist` | Engineer | Pre-deployment safety checklist covering config, migration, and rollback |
| `odoo-version-diff` | Engineer + Marketer | Categorized diff of API and feature changes between versions |
| `odoo-test-writing` | Engineer | Write executable `test_*.py` (or JS Hoot/QUnit) that protect business behavior, not current code; authors the RED-first failing test before the code in the `odoo-coding` loop, and backfills coverage when review flags an unprotected behavior |
| `odoo-security-audit` | Engineer | Audit code for SQLi / XSS / access-control / CSRF / unsafe deserialization, graded findings |
| `odoo-data-migration` | Engineer | Write pre/post migration scripts + a verification plan (does not execute against an instance) |
| `odoo-i18n` | Engineer / Coder | Dedicated i18n cluster - export .pot templates, non-destructively merge into maintained .po translations, dispatch leaf translation for one or more target languages in a single run (default vi_VN; reads machine-global `~/.odoo-ai/i18n.json`), and audit cross-module term consistency; the i18n step forward-port and new-module workflows dispatch into |
| `odoo-perf-audit` | Engineer | Audit for N+1 queries, missing prefetch, unindexed domains, compute thrash, with fixes |
| `odoo-git-rebase` | Engineer | Rebase a feature branch onto another branch of the SAME Odoo series, absorbing intent (not code text) via whole-range `git rebase --onto`. |
| `odoo-modules-upgrade` | Engineer | Upgrade a custom module cluster from a lower Odoo major to a higher one (code-level): drop what core now provides, adapt the rest, 1 PR per cluster. |
| `odoo-forward-port` | Engineer | Forward-port fixes/features from a lower Odoo series up to a higher one as an intent-first pipeline (parallel intent sweep -> 4-outcome classify -> installable probe -> SHA-preserving merge -> symbol-survival check -> test-first adapt -> verify-by-behavior -> PR); two human STOP-gates bound the automation |
| `odoo-solution-design` | Architect / Coder | Design the technical solution (approach / data model / override strategy / module structure) into a gate-able design doc BEFORE coding - the analysis-and-design step between requirement scoping and code; supports master-child decomposition for large multi-module scope (slim, paired with agent bundle) |
| `odoo-planning` | Architect / Coder | Turn an APPROVED design into the EXECUTION plan that ships it - a gate-able ONE-lifecycle plan (wave-batched module-DAG + integration cadence + each module/stage wired to a SKILL + full lifecycle: code -> review -> QA -> doc -> PR -> monitor -> merge); dispatches BOTH `odoo-planner` (code plan, reuses design DAG) AND `odoo-doc-planner` (doc plan, branch-aware instance allocation) and stitches them into ONE plan with a single approval gate; emits estimates only (effort + `est_agents`, ADVISORY). Runs after `odoo-solution-design`, before `odoo-coding` (slim, paired with agent bundle) |
| `odoo-coding` | Coder | The single coding front door - writes backend (Python/XML) AND frontend (JS/OWL/QWeb/SCSS); scopes the change, assigns a deterministic model tier per module (haiku/sonnet/opus/fable, sonnet default), and dispatches the `odoo-coder` + `odoo-frontend-coder` agents as subagents in model-weighted batches (per-module backend->frontend, model-weighted concurrency budget); orders modules by the shared module DAG, orchestrates red-first test authorship before each non-trivial module's code, and feeds the `code -> review+test -> code` loop (slim, paired with agent bundle) |
| `odoo-frontend-design` | Architect / Coder / Visual | Knowledge-only design-quality expertise for Odoo UI/UX (view-type choice, form hierarchy, density, semantic tokens, website/portal theming); loaded by `odoo-solution-design` and `odoo-coding`, and the bar `odoo-ui-review` rates against (no agent spawn) |
| `odoo-code-review` | Code-Reviewer | Review Odoo patches for ORM/inheritance/security pitfalls plus bidirectional module impact, platform-design-principle violations, and missing behavior tests; accepts `TARGET: local \| worktree:<path> \| pr:<number-or-url>` - Phase 0 dispatches `odoo-review-scoper` to resolve diffs and map modules, then `odoo-code-reviewer` agents for analysis; emits a VERDICT (APPROVE/REQUEST_CHANGES) with SCORE 0-100 and findings grouped by severity; on a CRITICAL/HIGH finding drives the fix autonomously through `odoo-coding` and re-reviews to verify (bounded to 3 iterations, then escalates), and loops uncovered behavior back to `odoo-test-writing` (slim, paired with agent bundle) |
| `odoo-feature-check` | Pre-Sales Consultant | Check if a feature exists in standard CE or EE |
| `odoo-gap-analysis` | Pre-Sales Consultant | Gap matrix of client requirements vs. standard Odoo |
| `odoo-instance` | Engineer / Coder | Front door for all Odoo instance lifecycle operations (create, drop, init, update, run-tests, ensure-up, load-language, status) for any series v8+; dispatches the `odoo-instance-ops` agent and relays back structured metadata including db name, log path, ports, and lease token |
| `odoo-capability-proof` | Pre-Sales Consultant | Evidence-based proof that Odoo supports a client requirement |
| `odoo-addon-diff` | Pre-Sales Consultant | Side-by-side CE vs EE feature comparison |
| `odoo-brl` | Pre-Sales Consultant | BRL engine - classify and cost tens-to-thousands of business requirements into a phased RTM with dependency DAG and checkpoint/resume |
| `odoo-rfp-response` | Pre-Sales Consultant | Per-requirement compliance matrix (Yes / Partial / Roadmap / No + evidence) with an executive fit summary |
| `odoo-pricing-proposal` | Sales AE / Pre-Sales | Customer-facing pricing proposal - tier + implementation bands + SLA + terms (rate numbers are AE-filled placeholders) |
| `odoo-customer-health` | Customer Success | Health score + churn-risk signals + upsell opportunities + recommended next-touch for an existing customer |
| `odoo-objection-handling` | Sales AE | ACA-structured responses to capability objections |
| `odoo-deal-followup` | Sales AE | Risk-scored follow-up email for stalled deals with next-best-action |
| `odoo-discovery-summary` | Sales AE | Synthesize discovery session notes into a structured prospect profile |
| `odoo-support-triage` | Sales AE / Support | Parse an inbound support ticket into classification, root-cause hint, and a customer-ready resolution draft |
| `odoo-feature-highlights` | Marketer | Marketing-friendly feature highlights for a version |
| `odoo-content-draft` | Marketer | Draft blog posts, slide decks, or social content around Odoo features |
| `odoo-campaign-plan` | Marketer | Multi-channel campaign plan from a positioning brief |
| `odoo-onboarding` | Onboarding / Concierge | Bootstrap project context into `.odoo-ai/context.md` for new engagements |
| `odoo-intake` | Onboarding / Concierge | Universal front door - brainstorms when vague, fast-paths a single clear step, resolves the Odoo version (escalates to `odoo-onboarding` when unknown and OSM is reachable, asks for version + repo path otherwise), offers an opt-in `deep-survey` on large jobs, and fast-paths review / PR-review and debug intents straight to the specialist (skipping Plan Mode); for multi-step work plans once then hands a `run-<id>.json` to `run-harness` to drive to done; always gates with a Proposed Plan before execution |
| `odoo-deep-survey` | Onboarding / Concierge (opt-in) | Multi-phase opt-in deep survey - invoked by `odoo-intake` after the user approves `deep-survey`; fans out a broad haiku sweep -> narrow sonnet dives -> optional opus, then writes a synthesis under `.odoo-ai/survey/` that re-informs the plan (read-only; spawner-agent, requires orchestrating context) |
| `odoo-ui-review` | Coder / Visual | Six-lens review of a rendered Odoo screen in a live browser (aesthetics, function, stability, accessibility, performance, design-system + theme fidelity); slim, paired with agent bundle |
| `odoo-debug` | Coder | Front-door orchestrator for all Odoo debugging - scientific method; dispatches specialist debug agents (backend/UI). On a CRITICAL/HIGH root cause it drives the fix autonomously - hands the proven cause to `odoo-coding`, which loops back through `odoo-code-review` to verify (bounded to 3 iterations, then escalates) |
| `odoo-visual-regression` | Coder / Visual | Screenshot baseline + diff between two Odoo states (before/after upgrade, module install, theme change) with blast-radius assessment |
| `odoo-demo-recording` | Coder / Visual | Record an MP4/GIF screen-capture of a scripted Odoo click-path for a demo, sales walkthrough, or marketing clip |
| `odoo-doc-illustration` | Marketer / Visual | Thin spawner - captures live Odoo screenshots into `static/description/` or a cluster docs dir; MODE module|cluster, DOC LAYER appstore|userguide|both, multi-locale, convention-detect; dispatches `odoo-doc-scoper` (scope, multi-module) + `odoo-doc-illustrator` (capture) |
| `odoo-icon-design` | Marketer / Visual | Generates icon.png (256x256) and icon.svg for Odoo v19 modules; reads module manifest, picks fitting symbols, produces static/description/icon.png + icon.svg; dispatches `odoo-icon-designer`; standalone-first, no browser. |
| `odoo-doc-feature-map` | Marketer | Builds feature-catalog.jsonl SSOT from module source; catalogues technical features into user-facing capability rows; dispatches `odoo-feature-cataloger`; standalone-first. |
| `odoo-doc-walkthrough` | Marketer | Produces happy-path usage walkthroughs for a module's key flows; dispatches `odoo-doc-scenarist`; standalone-first, browser capture optional. |
| `odoo-qa-suite` | Coder / Visual | Static release QA - produce a non-executing release test-plan, a pre-deploy checklist, and bug triage with severity + reproduction steps; the independent acceptance oracle and live execution/adjudication route to `odoo-acceptance` |
| `odoo-acceptance` | Coder / QA | End-to-end acceptance on a change AND its blast-radius - map the affected cluster, plan an INDEPENDENT oracle, then EXECUTE it on a real running instance/UI and adjudicate PASS/FAIL with evidence; dispatches `odoo-qa-planner` (oracle) + `odoo-qa-tester` (live execute) and chains tours/HttpCase via `odoo-instance` (needs a live instance + browser MCP) |
| `odoo-pr-monitoring` | Coder / Engineer | Owns the PR lifecycle AFTER `odoo-wave` opens the PR and stops at the L2-squash-gate - a poller (via `/loop` or `/schedule` + git-toolkit's github-operator), not a blocking node: routes any CI warning/error/fail to `odoo-debug` (root-cause first; fix re-push always human-gated, X2), caps review ping-pong, and on green + approved presents the L2-merge-gate, merges, and runs post-merge cleanup |
| `workflow-chaining` | Internal (harness) | Generic declarative workflow executor - reads `*.workflow.yaml` and runs gated phase sequences; invoked by odoo-intake via NL-dispatch, not directly by users |
| `run-harness` | Internal (harness) | Orchestrating drive-to-done loop - walks the `run-<id>.json` plan, dispatches each work-item, reads its Continuation Contract, and advances to DONE/BLOCKED/NEEDS_CONTEXT; gates L2 always, never traps the main agent |
| `odoo-wave` | Internal (orchestration) | INTERNAL git-executor (`user-invocable: false`, consume-only) that `run-harness` dispatches per coding wave-layer of an APPROVED plan - integration branch + per-WI worktrees + cherry-pick in module-DAG order + end-of-wave cross-cutting review + `odoo-code-review` inline + 1 PR + squash + tree-identity verify, then STOPS at the L2-squash-gate. INVOKES `odoo-coding` per WI (which owns agent count + model); never chooses agent/model, never self-derives a plan, and never merges (merge is owned by `odoo-pr-monitoring` at the L2-merge-gate) |

### Agents (23)

| Agent | Model (default) | Role |
|-------|-----------------|------|
| `odoo-review-scoper` | Sonnet | Phase 0 specialist dispatched by `odoo-code-review` - resolves the review TARGET (local diff, worktree path, or GitHub PR), maps touched modules, fetches PR metadata and diff when TARGET is a PR, and returns a structured scope record so downstream `odoo-code-reviewer` agents receive a clean, consistent input regardless of target type |
| `odoo-coder` | Sonnet *(default; per-work-item tier overrides - haiku/sonnet/opus/fable)* | Agent bundle for backend code writing - invoked by main agent and commands; restricted-tool autonomy. Reads the target version's coding guidelines BEFORE writing (conform on the first pass), runs an impact pre-flight (bidirectional), respects the platform design principles, implements to a red-first behavior test that drives the real workflow (`test-behavior-contract`), and ships dynamic demo data for new behavior. The dispatcher (`odoo-coding`) passes an explicit `model` per module from its tier table; frontmatter is only the default. |
| `odoo-solution-architect` | Opus *(default; fable for Custom-XL designs)* | Agent bundle for solution design (companion to `odoo-solution-design`) - produces a grounded Technical Design Document (approach / data model / override strategy / module structure / risks) before code; checks the three platform design principles, surveys bidirectional (upstream + downstream) impact, and designs dynamic demo data; full odoo-semantic tool surface, read-only, writes only the design doc |
| `odoo-planner` | Opus | Execution-plan author dispatched by `odoo-planning` - turns an APPROVED design (design DAG / `dag_layers` + dependency direction), the gap matrix, and the independent QA oracle into a gate-able 3-block plan: a wave-batched module-DAG, the integration cadence, each module/stage wired to a SKILL (never an agent), and the full lifecycle (code -> review -> doc -> PR -> monitor -> merge); emits estimates only (effort + `est_agents`, ADVISORY - the dispatched skill owns the runtime model + count); read-only on source, writes only the plan, serializes no `run-<id>.json` (intake Phase P owns that), spawns nothing |
| `odoo-code-reviewer` | Sonnet | Agent bundle for code review - runs full PR-scope analysis with OSM grounding; per-module and cross-module bidirectional impact, platform-principle checks, and a test-coverage gate that loops an uncovered behavior back to `odoo-test-writing` and CRITICAL/HIGH fixes back to `odoo-coding` |
| `odoo-ui-reviewer` | Sonnet | Agent bundle for visual UI review - drives a live browser through a six-lens audit with screenshot, console, and Lighthouse evidence plus OSM source pointers |
| `odoo-frontend-coder` | Sonnet *(default; per-work-item tier overrides - haiku/sonnet/opus/fable)* | Agent bundle for frontend code writing - JS/OWL/QWeb/SCSS across legacy and OWL eras with OSM grounding and design-system fidelity (companion to the `odoo-coding` skill). Reads the target version's coding guidelines BEFORE writing (conform on the first pass), runs an impact pre-flight along the asset-bundle / template-inheritance axis, and implements to a red-first JS behavior test that drives the real workflow (`test-behavior-contract`). Dispatched at the module's tier (or a lower `frontendModel` when the design splits effort). |
| `odoo-backend-debugger` | Sonnet | Debug specialist dispatched by `odoo-debug` - root-causes Python/ORM/server runtime failures via the scientific method, OSM-only (no browser); assesses bidirectional impact (could the bug originate upstream? what downstream does the fix touch?) |
| `odoo-ui-debugger` | Sonnet | Debug specialist dispatched by `odoo-debug` - root-causes OWL/JS/QWeb/SCSS runtime failures from live browser evidence + OSM grounding (serial-exclusive browser use); assesses impact along the template / asset-inheritance axis |
| `odoo-intent-extractor` | Sonnet | Read-only pre-analysis specialist dispatched by `odoo-forward-port` (P1, parallel) - extracts the business intent and behavioral contract from a single source commit, separating purpose from implementation details; suitable for parallel dispatch over many commits before any git merge or adapt work begins |
| `odoo-installable-prober` | Sonnet | Read-only forward-port P2 leaf - probes target clean-tip + source git-history to decide installable:False category-3 outcome for modules where static classify is ambiguous; returns a binary verdict (keep-installable-False / promote-to-True) with evidence; dispatched by `odoo-forward-port` at P2 for ambiguous cat-3 decisions |
| `odoo-translator` | Sonnet | Leaf translation worker dispatched by `odoo-i18n` (Phase 3) - translates one module (or module-cluster) for one language by polib merge (forwards translation MEMORY, never regenerates), hand-translates only the new/changed residual, and self-validates with an Odoo `-u` reload; never destroys existing human translation |
| `odoo-instance-ops` | Sonnet | Instance lifecycle specialist dispatched by the `odoo-instance` skill - provisions, drives, and tears down Odoo instances for any series (v8+); learns each version's CLI at runtime via OSM `cli_help`; prefers creating and dropping databases through Odoo (`odoo_db.py` / `odoo-bin db drop`) over raw `createdb`/`dropdb`; returns structured metadata (db name, log path, ports, lease token) so callers keep clean context |
| `odoo-doc-illustrator` | Sonnet | Browser-driven visual documentation specialist dispatched by `odoo-doc-illustration` - navigates live Odoo, captures screenshots, writes illustrated module docs (`static/description/` or cluster docs dir); multi-locale; reads `doc_image_naming`/`doc_languages`/`doc_static_dir` from context.md |
| `odoo-icon-designer` | Sonnet | Dispatched by `odoo-icon-design`; reads module manifest and picks fitting symbols, generates icon.png 256x256 + icon.svg into static/description/; standalone-first, no browser. |
| `odoo-feature-cataloger` | Sonnet | Dispatched by `odoo-doc-feature-map`; reads module source, emits feature-catalog.jsonl mapping technical features to user-facing capability rows; standalone-first. |
| `odoo-doc-scenarist` | Sonnet | Dispatched by `odoo-doc-walkthrough`; authors happy-path usage walkthroughs for a module's key flows; standalone-first, browser capture optional. |
| `odoo-doc-scoper` | Sonnet | Dispatched by `odoo-doc-illustration` for multi-module MODE; read-only, resolves TARGET to modules[]; standalone-first, no browser. |
| `odoo-diff-comparator` | Sonnet | Read-only: reads a git-diff range and emits a structured business-intent / expected-outcome / acceptance-criteria comparison (rebase: branch vs base; upgrade: custom vs core). |
| `odoo-gap-analyzer` | Sonnet | Gap-analysis leaf dispatched by `odoo-gap-analysis` (one per requirement cluster) - classifies each requirement against standard Odoo (coverage full/partial/none, classification standard/config/extension/custom, effort tier S/M/L/XL) grounded in OSM first and the local checkout as fallback, then writes a machine-readable findings file; read-only on source, does not design or write code |
| `odoo-qa-planner` | Sonnet | Independent acceptance-oracle author dispatched by `odoo-acceptance` (P1) and `odoo-coding` (P0 pre-code TDD) - turns a requirement/intent into an immutable `scenarios.md` (GWT, equivalence/boundary, negative paths, role/CRUD/state/search matrices, risk tier per scenario) WITHOUT reading the implementation to decide expected values; read-only, does not run or adjudicate |
| `odoo-qa-tester` | Sonnet | Live acceptance executor dispatched by `odoo-acceptance` (P2b) - drives the real Odoo UI across the affected cluster (CRUD, two-plus roles, state transitions, search) and rules each scenario PASS/FAIL/UNVERIFIED with screenshot/console/network evidence; browser-exclusive (serial), reads the oracle read-only, does not modify it or fix code |
| `odoo-doc-planner` | Sonnet | Dependency-aware doc-package planner dispatched by `odoo-planning` (full-lifecycle, plan_source design-dag) or `module-packaging`/`odoo-doc-illustration` (standalone, plan_source scope) - clusters modules, branch-aware instance allocation, leaf-first install order, dedup; writes doc-plan.yaml; read-only, no subagents |

## Requirements

- **Odoo Semantic MCP server URL** - `https://odoo-semantic.viindoo.com/mcp` (or your self-hosted instance)
- **API key** - format `osm_<alphanumeric>`, obtain from the [install page](https://odoo-semantic.viindoo.com/install/)
- Claude Code with MCP support (v2.1.x or newer)

## For contributors - local dev install

**Prerequisite:** Python 3.12+ (needed by `make setup` / `make test`).

Test changes from a checkout without going through the marketplace:

```bash
claude --plugin-dir ./plugins/odoo-ai-agents   # skills + agents + commands
```

See [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the full plugin-dev workflow, the release /
SHA-pinning pipeline, and the DCO sign-off requirement.

## Other AI tools

The plugin is Claude Code only. For other tools, paste the matching MCP config - see
[`docs/setup.md`](docs/setup.md) for full per-client walkthroughs (Codex, Gemini, VS Code,
Antigravity, Windsurf, Zed, JetBrains Junie) and `snippets/` for copy-ready configs:

| Tool | Snippet |
|------|---------|
| Cursor | [`snippets/cursor-mcp.json`](snippets/cursor-mcp.json) (server config) + [`snippets/cursor-rules.md`](snippets/cursor-rules.md) (routing rules) |
| ChatGPT Custom GPT | [`snippets/openai-gpt-instructions.md`](snippets/openai-gpt-instructions.md) |
| Google Gemini Gem | [`snippets/gemini-gem-instructions.md`](snippets/gemini-gem-instructions.md) |
| Continue.dev | [`snippets/continue-dev-mcp.yaml`](snippets/continue-dev-mcp.yaml) (MCP server config) |
| JetBrains AI Assistant | [`snippets/jetbrains-mcp-config.md`](snippets/jetbrains-mcp-config.md) (setup guide) |
| VS Code (v1.99+) | [`snippets/vscode-mcp.json`](snippets/vscode-mcp.json) (top-level key is `servers`, not `mcpServers`) |
| Google Antigravity | [`snippets/antigravity-mcp.json`](snippets/antigravity-mcp.json) (uses `serverUrl`, not `url`) |
| Zed | [`snippets/zed-mcp.json`](snippets/zed-mcp.json) (`context_servers` key, native HTTP - older Zed needs the `mcp-remote` proxy) |
| Windsurf | [`snippets/windsurf-mcp.json`](snippets/windsurf-mcp.json) (uses `serverUrl`, not `url`) |
| JetBrains Junie | [`snippets/junie-mcp.json`](snippets/junie-mcp.json) (place in `.junie/mcp/mcp.json` in your project) |

## License

MIT - see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Brand assets are trademarks of
Viindoo Technology JSC and are not covered by the MIT grant. This plugin is part of the
[`odoo-mcp-client`](../../README.md) monorepo.
