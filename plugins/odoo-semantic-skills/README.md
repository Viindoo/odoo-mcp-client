# odoo-semantic-skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://odoo-semantic.viindoo.com/)

> The Odoo AI workforce toolkit: **39 skills + 4 agents + 9 commands**, grouped into **9 persona
> buckets**, plus **11 declarative workflows** - covering engineering, coding, code review, visual
> UI testing, pre-sales, sales, marketing, strategy, and onboarding. Installing this plugin pulls
> in the companion [`odoo-semantic-mcp`](../odoo-semantic-mcp/) plugin automatically (declared
> dependency), so all knowledge is grounded through the OSM MCP server. This repo is a thin
> routing and orchestration layer; computation lives on the server.

## What you get

Nine virtual specialists that self-activate from plain-language intent - no slash
commands to memorize. Describe what you need; the right persona fires automatically.
You do not need to know skill names.

`intake` is the universal front door. Say what you want in plain language and it plans the
whole job once, then drives it to done:
- **Vague intent** -> it brainstorms with you (clarifying options, no open-ended "what do you want?").
- **Clear single-step intent** -> it fast-paths straight to the matching specialist.
- **Multi-step intent** -> it lays out a plan (the work-items, their order, who does each), you
  approve once, and then it **advances step-to-step on its own** - dispatching each specialist,
  reading the result, and moving to the next - stopping only when a step is irreversible/outward
  (e.g. a git push or an email to a customer) or when it is blocked and needs you.

You control how hands-off this is with one optional flag (`--auto` is the default; see
[Drive to done](#drive-to-done---how-to-use-it)). No execution ever fires before you approve the
plan, and the main agent is never forced or trapped - the stops are real human checkpoints, the
nudges are advisory.

> **Counts at a glance:** this plugin ships **39 skills + 4 agents + 9 commands**, grouped into
> **9 persona buckets** for navigation, plus **11 declarative workflows** driven by
> `workflows/*.workflow.yaml`. A further slash command, `/odoo-semantic-mcp:connect`, belongs to
> the companion `odoo-semantic-mcp` plugin and is pulled in automatically when you install this one.

## Who is it for

```mermaid
flowchart LR
    subgraph concierge["Onboarding / Concierge (serves every persona)"]
        intake_skill["intake<br/>(universal front door)"]
        onboard["odoo-onboarding"]
    end

    eng["Engineer"] --> override["odoo-override-finding"]
    eng --> deprecation["odoo-deprecation-audit"]
    eng --> deploy["odoo-deploy-checklist"]

    coder["Coder"] --> coderpy["odoo-backend-coding (Python/XML)"]
    coder --> coderfe["odoo-frontend-coding (JS/OWL)"]

    rev["Code-Reviewer"] --> reviewer["odoo-code-review"]

    qa["Visual / UI QA"] --> uirev["odoo-ui-review"]
    qa --> uidbg["odoo-ui-debugging"]
    qa --> visreg["odoo-visual-regression"]
    qa --> demo["odoo-demo-recording"]
    qa --> qasuite["odoo-qa-suite"]

    presales["Pre-Sales Consultant"] --> featchk["odoo-feature-check"]
    presales --> gap["odoo-gap-analysis"]
    presales --> cap["odoo-capability-proof"]
    presales --> addon["odoo-addon-diff"]
    presales --> brl["odoo-brl (BRL engine)"]

    sales["Sales AE"] --> obj["odoo-objection-handling"]
    sales --> followup["odoo-deal-followup"]
    sales --> disc["odoo-discovery-summary"]
    sales --> support["odoo-support-triage"]

    mkt["Marketer"] --> highlights["odoo-feature-highlights"]
    mkt --> content["odoo-content-draft"]
    mkt --> campaign["odoo-campaign-plan"]

    strat["Strategist / CEO"] --> risk["odoo-risk-overview"]
    strat --> inv["odoo-customization-inventory"]
    strat --> comp["odoo-competitive-brief"]

    vdiff["odoo-version-diff<br/>(Engineer + Marketer)"]
    eng --> vdiff
    mkt --> vdiff
```

- **Engineer** - Find the correct override point, audit deprecated API usage before an upgrade, or validate a deployment is safe.
- **Coder** - Write Odoo backend (Python/XML) or frontend (JS/OWL) code that is idiomatic and convention-correct, without looking up every framework rule.
- **Code-Reviewer** - Review pull requests or audit patches for ORM misuse, inheritance anti-patterns, security holes, or N+1 query issues.
- **Visual / UI QA** - Review a live Odoo screen through five lenses (aesthetics, function, stability, accessibility, performance), debug a broken render, catch visual regressions, record a demo clip, or run a full QA pipeline (test cases + checklist + bug triage).
- **Pre-Sales Consultant** - Verify feature availability, build a gap matrix, produce evidence for a proposal, compare CE vs EE side-by-side, or classify and cost hundreds of business requirements at scale with the BRL engine.
- **Sales AE** - Get ACA-structured responses to objections, risk-scored follow-up emails for stalled deals, a synthesized prospect profile from discovery notes, or triage an inbound support ticket into a customer-ready resolution draft.
- **Marketer** - Create content around Odoo features - blog posts, slide decks, social copy, multi-channel campaign plans - in marketing-ready language.
- **Strategist / CEO** - Get an executive risk overview of customizations, a structured customization inventory, or a competitor capability snapshot ready for a board or sales response.
- **Onboarding / Concierge** - Cross-cutting for every persona: `odoo-onboarding` bootstraps project context on a new engagement; `intake` takes ambiguous intent, brainstorms when vague, fast-paths when clear, routes to the right workflow or specialist, and always proposes a plan before any execution skill fires.

### How it works

Everything runs at the **main (depth-0) agent**, which acts as an **orchestrator + decision-maker
only** - it routes, decides at gates, and delegates the heavy work to specialists so its own
context stays clean across a long session. The depth ceiling is strict: `main (0) -> a
skill/workflow (1) -> a fan-out/worktree worker (2)`, never deeper.

`intake` is the front door for any plain-language intent. It (1) closes an intent gate (what /
why / what-done), (2) runs a quick read-only **recon** to make the plan context-aware, then (3)
emits a **Proposed Plan** and waits for your approval. From there:

- **Single clear step** -> the one specialist fires; chat-only answers skip Plan Mode entirely.
- **Multi-step** -> `intake` writes the approved plan to a run file (`.odoo-ai/run-<id>.json`) and
  hands it to **`run-driver`**, which walks the work-items to `DONE` / `BLOCKED` / `NEEDS_CONTEXT`:
  pick the next ready node -> check its gate tier -> dispatch it (a leaf skill inline, a coding/
  review/UI **agent bundle**, or a declarative **workflow** via `workflow-chaining`) -> read the
  step's **Continuation Contract** -> advance. A step can chain the next one (including across
  workflows via `on_complete`), so the run keeps moving without re-prompting.

Each step carries a **gate tier** that decides what stops for you (see
[Drive to done](#drive-to-done---how-to-use-it)). On a new Odoo project, `odoo-onboarding`
bootstraps `.odoo-ai/context.md` so later skills skip setup. Every skill grounds its answers
through the OSM MCP server; output is a direct answer or a file under `.odoo-ai/`.

```mermaid
flowchart TD
    A([Plain-language intent]) --> D{"intake - front door (depth 0)"}
    D -->|"Vague"| E["Brainstorm: clarifying options"]
    E -->|approve| D
    D -->|"Non-Odoo intent"| X["Route elsewhere / flag<br/>(stay Odoo-centric)"]
    D -->|"Recon + Proposed Plan"| G{"Approved. How many steps?"}

    G -->|"Single chat-only"| F1["Specialist fires<br/>(skip Plan Mode)"]
    G -->|"Single writes-files"| F2["Specialist + Plan-Mode approval"]
    G -->|"Multi-step"| RUN["run-driver loop (depth 0)<br/>walk run-&lt;id&gt;.json"]

    RUN --> PK{"next ready node<br/>+ gate tier"}
    PK -->|"L0/L1 under --auto"| DISP["dispatch:<br/>leaf skill | agent bundle | workflow-chaining"]
    PK -->|"L2 (irreversible/outward)"| STOP["STOP - human gate"]
    STOP -->|approve| DISP
    DISP --> CC["read Continuation Contract<br/>(status + produced + next[])"]
    CC -->|"next[] / on_complete"| PK
    CC -->|"all done"| DONE([DONE / BLOCKED / NEEDS_CONTEXT])

    F1 --> I[("OSM MCP grounding")]
    F2 --> I
    DISP --> I
    I --> Z([Answer or .odoo-ai/ file])
```

### Drive to done - how to use it

Two dials decide how much the run does on its own and where it stops for you.

**1. Autonomy dial** (optional flag on your `/intake` request; default `--auto`):

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

**Best practice.** Start with a plain-language `/intake "<what you want>"`. Approve the plan once.
Let `--auto` carry the routine steps; you will be stopped exactly at the moments that matter
(anything leaving your machine or touching a customer/instance). Use `--step` when you want to
watch every edit, `--plan` when you only want the map. You never type a skill name.

> **For contributors / AI agents extending this plugin:** the authoritative, diagram-backed
> spec of this whole mechanism - the Continuation Contract, the `run-<id>.json` blackboard, the
> gate-tier derivation, the depth rules, and the command/skill/agent taxonomy - lives in
> [`docs/reference/workflow-harness.md` §8](docs/reference/workflow-harness.md).
> The per-skill orchestration registry (spawn class, depth policy, output mode, gate tier) is
> [`docs/reference/ORCHESTRATION-MAP.md`](docs/reference/ORCHESTRATION-MAP.md),
> generated from `generator/skill_tool_deps.json`. Read those before changing routing or gates.

## Workflows

The plugin ships 11 declarative workflows in `workflows/*.workflow.yaml`. Each workflow is
executed by the generic `workflow-chaining` skill, which reads the YAML and runs the declared
phase sequence with approval gates between phases. Adding a new workflow is a single YAML
file drop - no orchestration code required. A workflow may also declare an `on_complete`
transition (e.g. `qa-suite` -> `odoo-backend-coding` when bugs are found); `run-driver` picks
that up and chains the next step across workflows automatically.

| Workflow | Trigger | Output dir |
|----------|---------|------------|
| `odoo-respond-bid` | Full bid / RFP response chain | `.odoo-ai/bids/` |
| `odoo-plan-upgrade` | Comprehensive upgrade plan | `.odoo-ai/upgrade-plans/` |
| `odoo-position-feature` | Positioning copy for marketing and sales | `.odoo-ai/positioning/` |
| `discovery-pipeline` | Synthesize and structure discovery notes | `.odoo-ai/discovery/` |
| `qa-suite` | Generate test cases, QA checklist, bug triage | `.odoo-ai/qa/` |
| `support-triage` | Classify + root-cause + draft resolution for a support ticket | `.odoo-ai/support/` |
| `video-produce` | Multi-scene Odoo demo video (storyboard -> record -> assemble) | `.odoo-ai/video/` |
| `sales-closing-cycle` | Late-stage sales cycle: objection handling + closing steps | `.odoo-ai/sales/` |
| `ui-debug-session` | Resumable multi-turn UI debug with browser evidence | `.odoo-ai/debug/` |
| `content-production` | Multi-asset content from a positioning brief | `.odoo-ai/content/` |
| `research-multiphase` | Flexible-phase research: broad survey -> deep dives -> synthesis, a different model tier per phase | `.odoo-ai/research/` |

Commands come in two shapes: multi-phase orchestrators that chain several skills in a
gated sequence, and single-step wrappers that run one skill and offer a save step. The
diagrams below show both, plus the visual UI testing pipeline that `setup` provisions.

```mermaid
flowchart TB
    subgraph BID["/odoo-respond-bid -> .odoo-ai/bids/"]
        direction LR
        B1[discovery-summary] -->|Gate 1| B2[gap-analysis] -->|Gate 2| B3[capability-proof] -->|Gate 3| B4[objection-handling] -->|Gate 4| B5[(assemble + save)]
    end

    subgraph POS["/odoo-position-feature -> .odoo-ai/positioning/"]
        direction LR
        P1[feature-check] -->|Gate 1| P2[addon-diff] -->|"Gate 2 (2+ editions)"| P3[competitive-brief] -->|"Gate 3 (competitor named)"| P4[(positioning copy + save)]
    end

    subgraph UPG["/odoo-plan-upgrade -> .odoo-ai/upgrade-plans/"]
        direction LR
        U1[risk-overview] -->|Gate 1| U2[deprecation-audit] -->|Gate 2| U3[version-diff] -->|Gate 3| U4[order + estimate] --> U5[(assemble + save)]
    end

    subgraph BRL_CMD["/odoo-run-brl -> .odoo-ai/brl/"]
        direction LR
        R1["Gate 0: chunk plan"] --> R2[classify + cost] --> R3[dependency DAG] -->|Gate E| R4[(RTM + report)]
    end

    subgraph WRAP["Single-step wrappers (one skill + save)"]
        direction LR
        W1["/odoo-draft-followup<br/>-> deal-followup"]
        W2["/odoo-summarize-discovery<br/>-> discovery-summary"]
        W3["/odoo-produce-video<br/>-> demo-recording per scene"]
    end

    BID ~~~ POS ~~~ UPG ~~~ BRL_CMD ~~~ WRAP
```

The visual UI testing stack is a sibling cluster, not a linear chain: one `setup` step
provisions the browser environment, then four skills run independently and converge on
`odoo-frontend-coding` as the fix writer.

```mermaid
flowchart TD
    SETUP["/odoo-semantic-skills:odoo-setup"]
    SETUP --> MCPW["Wires 3 browser MCP servers<br/>chrome-devtools + playwright + pagecast"]
    SETUP --> CTX[".odoo-ai/context.md<br/>.odoo-ai/instances.toml"]

    MCPW --> SK["Visual skills available"]
    CTX --> SK

    SK --> UID["odoo-ui-debugging<br/>root-cause diagnosis"]
    SK --> UIR["odoo-ui-review<br/>5-lens review + agent"]
    SK --> VR["odoo-visual-regression<br/>before/after diff"]
    SK --> DR["odoo-demo-recording<br/>MP4 / GIF output"]

    UID --> FC["odoo-frontend-coding<br/>fix writer"]
    UIR --> FC
    VR --> FC

    DR --> MEDIA["Recording artifact<br/>(no code fix needed)"]
```

### Available commands

> `/odoo-semantic-mcp:connect` ships in the `odoo-semantic-mcp` plugin and is not counted among the 9 commands of this plugin.

| Command | Purpose | Chained skills |
|---------|---------|----------------|
| `/odoo-respond-bid` | Full bid response chain for RFP/requirements documents, saves to `.odoo-ai/bids/` | `odoo-discovery-summary` -> `odoo-gap-analysis` -> `odoo-capability-proof` -> `odoo-objection-handling` |
| `/odoo-draft-followup` | Sales follow-up email saved to `.odoo-ai/followups/` | `odoo-deal-followup` |
| `/odoo-summarize-discovery` | Synthesize discovery notes into a structured profile, saves to `.odoo-ai/discovery/` | `odoo-discovery-summary` |
| `/odoo-position-feature` | Positioning copy for marketing and sales use, saves to `.odoo-ai/positioning/` | `odoo-feature-check` -> `odoo-addon-diff` -> `odoo-competitive-brief` -> positioning copy |
| `/odoo-plan-upgrade` | Comprehensive upgrade plan (replaces legacy `odoo-upgrade-planner` agent), saves to `.odoo-ai/upgrade-plans/` | `odoo-risk-overview` -> `odoo-deprecation-audit` -> `odoo-version-diff` -> synthesis |
| `/odoo-run-brl` | Bulk requirement-list classification at scale (chunked, resumable), saves to `.odoo-ai/brl/<job-id>/` | `odoo-brl` (sequential-outer-parallel-inner) |
| `/odoo-produce-video` | Multi-scene Odoo demo video (storyboard -> record -> assemble), saves to `.odoo-ai/video/` | `odoo-demo-recording` (per scene) |
| `/odoo-semantic-skills:odoo-setup` | One-shot idempotent setup for the visual workflow - wires 3 browser MCP servers across Claude/Codex/Gemini, installs browser deps, auto-allows tool permissions, discovers + optionally spins up a local Odoo instance | - |
| `/odoo-semantic-skills:odoo-run-wave` | Depth-0 git-wave orchestration: integration branch + WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate + human-confirm merge (auto-merge never allowed) | `wave` |

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

Chains `odoo-risk-overview` -> `odoo-deprecation-audit` -> `odoo-version-diff` -> synthesis. Output: executive risk overview, code-level deprecation findings, API/feature diff, action ordering, S/M/L/XL effort estimate, and rollback plan. Saves to `.odoo-ai/upgrade-plans/customer-d-v15-v17-2026-MM-DD.md`. When you need actual code written, invoke the `odoo-coder` agent bundle (depth-1 safe, restricted-tool autonomy, OSM access).

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

Run `/odoo-semantic-skills:odoo-setup` once to provision the browser automation stack. Then skill `odoo-visual-regression` fires: it captures before/after screenshots of targeted views, diffs them, and flags regressions with severity labels. Where a defect is confirmed, `odoo-ui-review` follows up with a 5-lens audit (aesthetics / function / stability / accessibility / performance) and surfaces the exact CSS or XML path to fix. Fixes are handed to `odoo-frontend-coding`, which writes the override and shows a patch preview before applying.

### Use case 8 - Support: triage an inbound customer ticket

A customer reports that their invoice approval workflow is broken after a recent module update. You need to classify, root-cause, and draft a resolution note in one pass.

```
You: "Customer F reports: invoice approval button disappeared after installing
account_invoice_approval v14. Users are blocked."
```

Skill `odoo-support-triage` fires. It classifies the ticket (bug - UI regression), generates a root-cause hint using OSM to inspect the `account` module's approval flow and the installed module's view overrides, and drafts a resolution note ready to send to the customer. If a live browser is available, it NL-dispatches to `odoo-ui-debugging` to capture the console error and pinpoint the broken view. Output saved to `.odoo-ai/support/customer-f-2026-MM-DD.md`.

### Frequently asked questions

**I only need one skill - do I have to know all 39?** No. Skills auto-fire by intent match. Describe what you need; the right skill triggers. `intake` acts as a brainstorm partner when you are not sure which skill to use.

**What if the OSM server is offline?** Each skill has a `## Standalone-first fallback` section - it degrades gracefully by reading your local codebase and `.odoo-ai/context.md` directly (Read/Grep/WebFetch, three-tier grounding) instead of asking you to paste data; if a browser is genuinely unreachable a visual skill returns BLOCKED rather than requesting screenshots. The plugin does not break when OSM is offline.

**What about confidentiality?** Plugin code is public (MIT). Skills contain no customer-specific data or pricing. A pre-commit hook and CI scan block several categories of sensitive content. Examples use abstract labels (Customer A through Customer F).

**Multi-runtime?** Skills and commands are written for Claude Code. Codex/Gemini parity is smoke-tested in `tests/smoke/runtime_parity.md` - 10 representative skills verified across all three runtimes.

**How do I add a new workflow?** Drop a `*.workflow.yaml` file in `workflows/` following the schema in `workflows/_schema.md`. The `workflow-chaining` auto-discovers it. No `plugin.json` edit needed.

## Quick install (Claude Code - 3 steps, all required)

Inside Claude Code, run:

```
/plugin marketplace add Viindoo/claude-plugins   # one-time, if not already registered
/plugin install odoo-semantic-skills@viindoo-plugins   # auto-pulls odoo-semantic-mcp
/odoo-semantic-mcp:connect
```

Installing `odoo-semantic-skills` **automatically pulls in `odoo-semantic-mcp`** via the plugin dependency, so you get the skills, agents, commands, and the MCP connection in one step. Then **restart Claude Code**.

You will need an **API key** (format `osm_...`) from the [install page](https://odoo-semantic.viindoo.com/install/), and the **MCP server URL** (default `https://odoo-semantic.viindoo.com/mcp`). For MCP-only setup and the `connect` command details, see the companion [`odoo-semantic-mcp`](../odoo-semantic-mcp/) plugin.

### Browser MCP servers / cross-CLI install

The four Visual skills (`odoo-ui-review`, `odoo-ui-debugging`, `odoo-visual-regression`,
`odoo-demo-recording`) need three browser MCP servers: `chrome-devtools`, `playwright`,
and `pagecast`. Each runtime bundles them natively:

| Runtime | How it ships | What to run |
|---------|-------------|-------------|
| **Claude Code** | Bundled `.mcp.json` (auto-loaded on plugin install). Claude deduplicates by command - a same-command server already in your config wins silently. No manual step. | Nothing extra after `claude plugin install`. |
| **Gemini CLI** | `gemini-extension.json` in the plugin directory. **Gemini requires a repo root**, so install via local path: `gemini extensions install <your-clone>/plugins/odoo-semantic-skills` (or `...link ...` for live dev). Dedup is by server name. The `trust` field is not allowed in the extension manifest. | `gemini extensions install <your-clone>/plugins/odoo-semantic-skills` |
| **Codex CLI** | `.codex-plugin/plugin.json`. Installed from a marketplace snapshot: `codex plugin marketplace add <marketplace>` then `codex plugin add odoo-semantic-skills@<marketplace>` (marketplace.json to be published separately). | `codex plugin add odoo-semantic-skills@<marketplace>` |

**Fallback (Codex/Gemini without native install):** run `/odoo-semantic-skills:odoo-setup runtime`
inside Claude Code - it writes the correct browser server config for Codex and Gemini
idempotently. It does **not** write to `~/.claude.json` for Claude Code (served by the
bundled `.mcp.json`).

Full details and manual snippets: [`docs/setup.md` - Visual stack / browser MCP setup](docs/setup.md#visual-stack--browser-mcp-setup).

> **Upgrading from the old single `odoo-semantic` plugin (v1.x)?** It was split into
> `odoo-semantic-skills` + `odoo-semantic-mcp`. See [Migration in the repo
> README](../../README.md#migration--upgrading-from-v1x).

## Reference

### Skills (39)

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
| `odoo-test-writer` | Engineer | Write executable `test_*.py` (or JS Hoot/QUnit) that protect business behavior, not current code |
| `odoo-security-audit` | Engineer | Audit code for SQLi / XSS / access-control / CSRF / unsafe deserialization, graded findings |
| `odoo-data-migration` | Engineer | Write pre/post migration scripts + a verification plan (does not execute against an instance) |
| `odoo-perf-audit` | Engineer | Audit for N+1 queries, missing prefetch, unindexed domains, compute thrash, with fixes |
| `odoo-backend-coding` | Coder | Python/XML backend coder with Odoo conventions baked in (slim, paired with agent bundle) |
| `odoo-frontend-coding` | Coder | JS/OWL coder merging legacy web client (v8-14) and OWL component framework (v15+) (slim, paired with agent bundle) |
| `odoo-code-review` | Code-Reviewer | Review Odoo patches for ORM/inheritance/security pitfalls (slim, paired with agent bundle) |
| `odoo-feature-check` | Pre-Sales Consultant | Check if a feature exists in standard CE or EE |
| `odoo-gap-analysis` | Pre-Sales Consultant | Gap matrix of client requirements vs. standard Odoo |
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
| `intake` | Onboarding / Concierge | Universal front door - brainstorms when vague, fast-paths a single clear step, and for multi-step work plans once then hands a `run-<id>.json` to `run-driver` to drive to done; always gates with a Proposed Plan before execution |
| `odoo-ui-review` | Coder / Visual | Five-lens review of a rendered Odoo screen in a live browser (aesthetics, function, stability, accessibility, performance); slim, paired with agent bundle |
| `odoo-ui-debugging` | Coder / Visual | Root-cause a broken Odoo UI at runtime (console errors, failed requests, blank OWL renders, wrong CSS) and pinpoint the override point |
| `odoo-visual-regression` | Coder / Visual | Screenshot baseline + diff between two Odoo states (before/after upgrade, module install, theme change) with blast-radius assessment |
| `odoo-demo-recording` | Coder / Visual | Record an MP4/GIF screen-capture of a scripted Odoo click-path for a demo, sales walkthrough, or marketing clip |
| `odoo-qa-suite` | Coder / Visual | Full QA pipeline - generate structured test cases, produce a pre-deploy checklist, and triage bugs with severity classification and reproduction steps |
| `workflow-chaining` | Internal (harness) | Generic declarative workflow executor - reads `*.workflow.yaml` and runs gated phase sequences; invoked by intake via NL-dispatch, not directly by users |
| `run-driver` | Internal (harness) | Depth-0 drive-to-done loop - walks the `run-<id>.json` plan, dispatches each work-item, reads its Continuation Contract, and advances to DONE/BLOCKED/NEEDS_CONTEXT; gates L2 always, never traps the main agent |
| `wave` | Internal (orchestration) | Depth-0 git-wave orchestration - integration branch + WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate + human-confirm merge; self-spawning, principal-branch-locked |

### Agents (4)

| Agent | Model | Role |
|-------|-------|------|
| `odoo-coder` | Sonnet | Agent bundle for code writing - invoked by main agent and commands; depth-1 safe with restricted-tool autonomy |
| `odoo-code-reviewer` | Sonnet | Agent bundle for code review - runs full PR-scope analysis with OSM grounding |
| `odoo-ui-reviewer` | Sonnet | Agent bundle for visual UI review - drives a live browser through a five-lens audit with screenshot, console, and Lighthouse evidence plus OSM source pointers |
| `odoo-frontend-coder` | Sonnet | Agent bundle for frontend code writing - JS/OWL/QWeb/SCSS across legacy and OWL eras with OSM grounding and design-system fidelity (companion to the `odoo-frontend-coding` skill) |

## Requirements

- **Odoo Semantic MCP server URL** - `https://odoo-semantic.viindoo.com/mcp` (or your self-hosted instance)
- **API key** - format `osm_<alphanumeric>`, obtain from the [install page](https://odoo-semantic.viindoo.com/install/)
- Claude Code with MCP support (v2.1.x or newer)

## For contributors - local dev install

**Prerequisite:** Python 3.12+ (needed by `make setup` / `make test`).

Test changes from a checkout without going through the marketplace:

```bash
claude --plugin-dir ./plugins/odoo-semantic-skills   # skills + agents + commands
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
