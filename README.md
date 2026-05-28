# Odoo MCP Client

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://odoo-semantic.viindoo.com/)

> MIT-licensed client layer for the **[Odoo Semantic MCP server](https://odoo-semantic.viindoo.com/)** (AGPL-3.0).
> Odoo AI workforce toolkit — **22 skill personas** across 8 work domains
> (engineering, sales, marketing, strategy, onboarding) + **5 workflow commands + 1 setup command**
> that chain skills into multi-step recipes. Pairs with the OSM (odoo-semantic) MCP server
> for indexed-codebase grounding.

This repository ships **no semantic logic**. It is a thin integration surface: 22
persona-specific skills (across 8 personas), 2 specialist agents, 5 workflow commands
plus 1 setup command (`/odoo-semantic:connect`), and ready-to-paste MCP config for
several AI tools. All knowledge and computation live in the Odoo Semantic MCP server —
query it at the hosted instance [`odoo-semantic.viindoo.com`](https://odoo-semantic.viindoo.com)
or sign up for an API key at the [install page](https://odoo-semantic.viindoo.com/install/).

## For the small-team Odoo founder

Running a small Odoo consultancy or building go-to-market for Odoo — and wearing every
hat at once? This plugin turns your AI agent into **8 virtual specialists** (one per
work domain). Each specialist is a skill or agent bundle that owns a specific
function: engineering, sales, marketing, strategy, and more. You do not need to know
skill names — describe your intent in natural language and the right specialist fires
automatically.

### How it works

Each specialist self-activates when you describe your intent in plain English (or any
natural language). Complex multi-step workflows are exposed as explicit slash commands
(`/odoo-*`) for when you want to control the sequence.

### 8 specialist personas

| Persona | Skill / Agent | When to use |
|---|---|---|
| Engineer | `odoo-override-finder`, `odoo-deprecation-audit`, `odoo-deploy-checklist` | Custom code, pre-upgrade audit, deploy safety |
| Coder | `odoo-coder` (Python/XML, agent+skill bundle), `odoo-frontend-coder` (JS/OWL legacy v8-14 + OWL v15+) | Write production-ready code |
| Code-Reviewer | `odoo-code-reviewer` (agent+skill bundle) | Review PRs, audit for bugs, security, N+1 queries |
| Pre-Sales Consultant | `odoo-feature-check`, `odoo-gap-analysis`, `odoo-capability-proof`, `odoo-addon-diff` | Verify feature availability, scope effort, build evidence for proposals |
| Sales AE | `odoo-objection-handler`, `odoo-deal-followup`, `odoo-discovery-summarize` | Handle objections, follow up stalled deals, synthesize discovery |
| Marketer | `odoo-feature-highlights`, `odoo-content-draft`, `odoo-campaign-plan` | Slide and blog content, multi-channel campaigns |
| Strategist | `odoo-risk-overview`, `odoo-customization-inventory`, `odoo-competitive-brief` | Board briefs, customization inventory, competitor analysis |
| Onboarding / Concierge | `odoo-onboard`, `odoo-router` | Bootstrap context for a new project, route ambiguous intent |

Plus 5 slash commands that chain skills into multi-step workflows: `/odoo-bid-respond`,
`/odoo-customer-followup-draft`, `/odoo-discovery-quick`, `/odoo-feature-positioning`,
`/odoo-upgrade-plan-full`.

### Use case 1 - Sales AE: stalled deal, draft a follow-up email in 30 seconds

You have a prospect (manufacturing SME) that has not replied in 21 days after the demo.
Pipeline stage is "evaluation". You need a follow-up email tonight to send tomorrow
morning.

```
You: "Deal with Customer A stalled 21 days after demo, manufacturing SME evaluating
Odoo vs SAP. At the last meeting they promised technical feedback within the week.
Write a follow-up email."
```

Skill `odoo-deal-followup` fires. Output: risk score (red — warm lead, >14 days no
reply), next-best-action ("re-engage with concrete value proof"), 4-paragraph follow-up
email template ready to paste.

To save to a file: `/odoo-customer-followup-draft` (chains the skill and saves to
`.odoo-ai/followups/customer-a-2026-MM-DD.md`).

### Use case 2 - Pre-Sales: RFP with 15 requirements

A prospect sends an RFP with 15 functional requirements: lot tracking, multi-level
approval, reporting, multi-warehouse, customer portal, and more. You need a complete
response within 24 hours.

```
You: "/odoo-bid-respond - Customer B (F&B chain, 50 locations), 15 requirements
listed below"
```

The command runs a 7-phase workflow:

1. Parse args and read `.odoo-ai/context.md` (if missing, suggest `odoo-onboard`).
2. Trigger `odoo-discovery-summarize` — structured prospect profile.
3. Trigger `odoo-gap-analysis` — effort matrix (Standard / Config / Extension / Custom + S/M/L/XL days).
4. Trigger `odoo-capability-proof` for Standard/Config items — evidence package.
5. Trigger `odoo-objection-handler` for 2-3 anticipated objections.
6. Assemble proposal draft.
7. Save to `.odoo-ai/bids/customer-b-2026-MM-DD.md` (gated — you approve each phase).

### Use case 3 - Strategist / founder: monthly board brief

You need a board status brief covering product progress, pipeline health, competitive
landscape, and top risks.

```
You: "Summarize competitive landscape — Competitor A vs your Odoo distribution — for
next week's board meeting."
```

Skill `odoo-competitive-brief` fires. Paste your collected signals; the skill
structures them into: market snapshot, capability matrix, GTM moves, threat assessment,
and recommended product response. Format is ready for a board deck.

Combine with:
- `odoo-risk-overview` for engineering risk overview (founder-level dashboard, not a
  dev audit).
- `odoo-customization-inventory` to list all custom modules with their business purpose
  (M&A due-diligence ready).

### Use case 4 - Engineer + Coder: upgrade v15 to v17

Customer C is running Odoo 15 with 12 custom modules and wants to move to v17 in Q3.

```
You: "/odoo-upgrade-plan-full - Customer C, v15 to v17, 12 custom modules, deadline Q3"
```

Chains 4 skills: `odoo-risk-overview` - `odoo-deprecation-audit` - `odoo-version-diff`
- synthesis. Output: executive risk overview + code-level deprecation findings + API/
feature diff + action ordering + S/M/L/XL effort estimate + rollback plan. Saves to
`.odoo-ai/upgrade-plans/customer-c-v15-v17-2026-MM-DD.md`.

When you need actual code written: invoke the `odoo-coder` agent bundle (depth-1 safe,
restricted-tool autonomy, with OSM access and an optional cost-free local model).

### Frequently asked questions

**I only need one skill — do I have to know all 22?** No. Skills auto-fire by intent
match. Describe what you need; the right skill triggers.

**What if the OSM server is offline?** Each skill has a `## Standalone-first fallback`
section — it degrades gracefully by prompting you to paste data manually. The plugin
does not break when OSM is offline.

**What about confidentiality?** Plugin code is public (MIT). Skills contain no
customer-specific data or pricing. A pre-commit hook and CI scan block several
categories of sensitive content. Examples use abstract labels (Customer A, Customer B).

**Multi-runtime?** Skills and commands are written for Claude Code. Codex/Gemini
parity is smoke-tested in `tests/smoke/runtime_parity.md` — 10 representative skills
verified across all three runtimes.

## Quick install (Claude Code — 3 steps, all required)

Inside Claude Code, run:

```
/plugin marketplace add Viindoo/claude-plugins   # one-time, if not already registered
/plugin install odoo-semantic@viindoo-plugins
/odoo-semantic:connect
```

> **`/odoo-semantic:connect` is mandatory on Claude Code v2.1.x.** Plugin manifests use a
> `userConfig` block to collect the API key + MCP URL, but the CLI currently
> does not prompt for those values at install time
> ([anthropics/claude-code#39455](https://github.com/anthropics/claude-code/issues/39455),
> [#39827](https://github.com/anthropics/claude-code/issues/39827)). Without it
> the plugin loads its skills but the MCP server silently fails — `claude mcp list`
> will not show `odoo-semantic`.
>
> **Restart Claude Code after `/odoo-semantic:connect`** to actually load the
> MCP tools. Claude Code v2.x does not hot-reload MCP servers within a session
> ([#46426](https://github.com/anthropics/claude-code/issues/46426) — "not
> planned"). The connect command verifies the server via `curl` and tells you
> when to restart.

You will need an **API key** (format `osm_...`) from the
[install page](https://odoo-semantic.viindoo.com/install/), and the **MCP server URL**
(default `https://odoo-semantic.viindoo.com/mcp`).

## Available skills

| Skill | Persona | Description |
|-------|---------|-------------|
| `odoo-risk-overview` | Strategist / CEO | Executive risk overview of customizations before upgrade |
| `odoo-customization-inventory` | Strategist / CEO | Structured inventory of all custom modules and their business purpose |
| `odoo-competitive-brief` | Strategist | Competitor capability snapshot structured for board or sales response |
| `odoo-override-finder` | Engineer | Find the correct override point and pattern for a method |
| `odoo-deprecation-audit` | Engineer | Audit deprecated API usage for upgrade readiness |
| `odoo-deploy-checklist` | Engineer | Pre-deployment safety checklist covering config, migration, and rollback |
| `odoo-version-diff` | Engineer + Marketer | Categorized diff of API and feature changes between versions |
| `odoo-coder` | Coder | Python/XML backend coder with Odoo conventions baked in (slim, paired with agent bundle) |
| `odoo-frontend-coder` | Coder | JS/OWL coder merging legacy web client (v8-14) and OWL component framework (v15+) |
| `odoo-code-reviewer` | Code-Reviewer | Review Odoo patches for ORM/inheritance/security pitfalls (slim, paired with agent bundle) |
| `odoo-feature-check` | Pre-Sales Consultant | Check if a feature exists in standard CE or EE |
| `odoo-gap-analysis` | Pre-Sales Consultant | Gap matrix of client requirements vs. standard Odoo |
| `odoo-capability-proof` | Pre-Sales Consultant | Evidence-based proof that Odoo supports a client requirement |
| `odoo-addon-diff` | Pre-Sales Consultant | Side-by-side CE vs EE feature comparison |
| `odoo-objection-handler` | Sales AE | ACA-structured responses to capability objections |
| `odoo-deal-followup` | Sales AE | Risk-scored follow-up email for stalled deals with next-best-action |
| `odoo-discovery-summarize` | Sales AE | Synthesize discovery session notes into a structured prospect profile |
| `odoo-feature-highlights` | Marketer | Marketing-friendly feature highlights for a version |
| `odoo-content-draft` | Marketer | Draft blog posts, slide decks, or social content around Odoo features |
| `odoo-campaign-plan` | Marketer | Multi-channel campaign plan from a positioning brief |
| `odoo-onboard` | Onboarding / Concierge | Bootstrap project context into `.odoo-ai/context.md` for new engagements |
| `odoo-router` | Onboarding / Concierge | Concierge skill — routes ambiguous user intent to the right specialist |

Per-persona quick-start guides live in [`docs/personas/`](docs/personas/).

## Available agents

| Agent | Model | Role |
|-------|-------|------|
| `odoo-coder` | Sonnet | Agent bundle for code writing — invoked by main agent and commands; depth-1 safe with restricted-tool autonomy |
| `odoo-code-reviewer` | Sonnet | Agent bundle for code review — runs full PR-scope analysis with OSM grounding |

## Available commands

| Command | Purpose | Chained skills |
|---------|---------|----------------|
| `/odoo-semantic:connect` | Interactive MCP server setup — prompts for URL + API key, registers server, pre-approves tools | — |
| `/odoo-bid-respond` | Full bid response chain for RFP/requirements documents | `odoo-discovery-summarize` -> `odoo-gap-analysis` -> `odoo-capability-proof` -> `odoo-objection-handler` |
| `/odoo-customer-followup-draft` | Sales follow-up email saved to `.odoo-ai/followups/` | `odoo-deal-followup` |
| `/odoo-discovery-quick` | Slash wrapper — synthesize discovery notes into a structured profile | `odoo-discovery-summarize` |
| `/odoo-feature-positioning` | Positioning copy for marketing and sales use | `odoo-feature-highlights` -> `odoo-content-draft` |
| `/odoo-upgrade-plan-full` | Comprehensive upgrade plan — replaces legacy `odoo-upgrade-planner` agent | `odoo-risk-overview` -> `odoo-deprecation-audit` -> `odoo-version-diff` -> synthesis |

## MCP resources

The server exposes **7 MCP resource URI templates** (in addition to the 24 tools) for
direct structured data access:

- `odoo://{version}/model/{name}` — model summary
- `odoo://{version}/model/{name}/fields` — field list
- `odoo://{version}/model/{name}/field/{field}` — single field detail
- `odoo://{version}/module/{name}` — module summary
- `odoo://{version}/module/{name}/views` — module views
- `odoo://{version}/module/{name}/js` — module JS patches
- `odoo://{version}/module/{name}/owl` — module OWL components

Supported Odoo versions: **v8.0 through v19.0 (12 versions)**.

## Connect command

```
/odoo-semantic:connect
```

Interactive command that:
1. Prompts for your MCP server URL and API key
2. Validates key format (`osm_...`)
3. Registers the MCP server via `claude mcp add --scope user`
4. Probes `/health` + `/mcp` with `curl` to verify server + key
5. **Adds `mcp__odoo-semantic` to `permissions.allow` in `~/.claude/settings.json`** so every tool of this server is pre-approved — no more "Do you want to proceed?" prompts on every call. Idempotent, backs up the file before writing, refuses to overwrite invalid JSON, preserves every other key. Answer `n` at the prompt to skip (you can paste the snippet from [`docs/setup.md#claude-code-auto-trust`](docs/setup.md#claude-code-auto-trust) manually instead).
6. Tells you to restart Claude Code (required to load MCP tools)

## Other AI tools

The plugin is Claude Code only. For other tools, paste the matching MCP config — see
[`docs/setup.md`](docs/setup.md) for full per-client walkthroughs (Codex, Gemini, VS Code,
Antigravity) and `snippets/` for copy-ready configs:

| Tool | Snippet |
|------|---------|
| Cursor | [`snippets/cursor-mcp.json`](snippets/cursor-mcp.json) (server config) + [`snippets/cursor-rules.md`](snippets/cursor-rules.md) (routing rules) |
| ChatGPT Custom GPT | [`snippets/openai-gpt-instructions.md`](snippets/openai-gpt-instructions.md) |
| Google Gemini Gem | [`snippets/gemini-gem-instructions.md`](snippets/gemini-gem-instructions.md) |
| Continue.dev | [`snippets/continue-dev-mcp.yaml`](snippets/continue-dev-mcp.yaml) (MCP server config) |
| JetBrains AI Assistant | [`snippets/jetbrains-mcp-config.md`](snippets/jetbrains-mcp-config.md) (setup guide) |

## Requirements

- **Odoo Semantic MCP server URL** — `https://odoo-semantic.viindoo.com/mcp` (or your self-hosted instance)
- **API key** — format `osm_<alphanumeric>`, obtain from the [install page](https://odoo-semantic.viindoo.com/install/)
- Claude Code with MCP support (tested on v2.1.140)

## For contributors — local dev install

Test changes from a checkout without going through the marketplace:

```bash
claude --plugin-dir ./
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full plugin-dev workflow, the release /
SHA-pinning pipeline, and the DCO sign-off requirement.

## Relationship to the server

| Layer | Repository | License |
|-------|------------|---------|
| Client (this repo) — plugin, skills, agents, snippets | `Viindoo/odoo-mcp-client` | MIT |
| Server — indexer, Neo4j graph, pgvector, MCP server, web UI | [odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/) | AGPL-3.0-or-later |

To use the hosted instance, sign up for an API key at
[odoo-semantic.viindoo.com/install](https://odoo-semantic.viindoo.com/install/).
Self-hosting instructions are available in the server's own documentation,
accessible after registration.

## License

MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Brand assets in `branding/` are
trademarks of Viindoo Technology JSC and are not covered by the MIT grant — see
[`branding/TRADEMARK.md`](branding/TRADEMARK.md).
