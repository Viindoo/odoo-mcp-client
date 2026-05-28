# Odoo MCP Client

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://github.com/Viindoo/odoo-semantic-server)

> MIT-licensed client layer for **[odoo-semantic-server](https://github.com/Viindoo/odoo-semantic-server)** (AGPL-3.0).
> Odoo / Viindoo AI workforce toolkit — **22 skill personas** across 8 work domains
> (engineering, sales, marketing, strategy, onboarding) + **6 workflow commands** that
> chain skills into multi-step recipes. Pairs with the OSM (odoo-semantic) MCP server
> for indexed-codebase grounding.

This repository ships **no semantic logic**. It is a thin integration surface: 22
persona-specific skills (across 8 personas), 3 agents (2 specialist bundle + 1 deprecated),
6 commands, and ready-to-paste MCP config for several AI tools. All knowledge and computation
live in the Odoo Semantic MCP server — query it at the hosted instance
[`odoo-semantic.viindoo.com`](https://odoo-semantic.viindoo.com) or
[self-host the server](https://github.com/Viindoo/odoo-semantic-server).

## Một-người-công-ty: cách dùng AI specialist

Bạn là CEO/Founder của một công ty làm Odoo/Viindoo? Một mình lo cả engineering, sales, marketing, strategy? Plugin này biến AI agent thành **8 chuyên gia ảo (AI specialist)** - mỗi specialist là một skill hoặc agent bundle chuyên trách 1 mảng nghiệp vụ. Bạn không cần thuê thêm người để start.

### Cách hoạt động

Mỗi specialist tự kích hoạt khi bạn mô tả intent bằng tiếng Việt hoặc English tự nhiên (không cần biết tên skill). Một số workflow phức tạp được gọi thành slash command `/odoo-*` để gọi tường minh.

### 8 chuyên gia

| Persona | Skill / Agent | Khi nào dùng |
|---|---|---|
| Engineer | `odoo-override-finder`, `odoo-deprecation-audit`, `odoo-deploy-checklist` | Custom code, audit pre-upgrade, deploy safety |
| Coder | `odoo-coder` (Python/XML, agent+skill bundle), `odoo-frontend-coder` (JS/OWL legacy v8-14 + OWL v15+) | Viết code production-ready |
| Code-Reviewer | `odoo-code-reviewer` (agent+skill bundle) | Review PR, audit code lý do bugs/security/N+1 |
| Pre-Sales Consultant | `odoo-feature-check`, `odoo-gap-analysis`, `odoo-capability-proof`, `odoo-addon-diff` | Verify Odoo có tính năng X, scope effort, evidence cho proposal |
| Sales AE | `odoo-objection-handler`, `odoo-deal-followup`, `odoo-discovery-summarize` | Phản hồi objection, follow-up deal stalled, synthesize discovery |
| Marketer | `odoo-feature-highlights`, `odoo-content-draft`, `odoo-campaign-plan` | Slide/blog content, multi-channel campaign |
| Strategist | `odoo-risk-overview`, `odoo-customization-inventory`, `odoo-competitive-brief` | Board brief, customization inventory, competitor brief |
| Onboarding/Concierge | `odoo-onboard`, `odoo-router` | Bootstrap context cho project mới, route ambiguous intent |

Plus 5 slash commands chain các skill thành workflow đa bước: `/odoo-bid-respond`, `/odoo-customer-followup-draft`, `/odoo-discovery-quick`, `/odoo-feature-positioning`, `/odoo-upgrade-plan-full`.

### Use case 1 - Sales AE: deal stalled, viết follow-up email trong 30 giây

Bạn có 1 khách prospect (gọi là Khách A - manufacturing SME) đã 21 ngày không trả lời sau buổi demo. Pipeline stage "evaluation". Bạn cần email follow-up tonight để gửi sáng mai.

```
Bạn: "deal Khách A stalled 21 ngày sau demo, manufacturing SME đang đánh giá Odoo vs SAP. Cuối lần gặp họ promise sẽ feedback technical questions trong tuần. Viết follow-up email."
```

Skill `odoo-deal-followup` tự fire. Output: risk score (red, >14d no reply on warm lead), next-best-action ("re-engage with concrete value proof"), 4-paragraph VI follow-up email template ready to paste.

Nếu muốn save vào file: `/odoo-customer-followup-draft` (chains skill + save step to `.odoo-ai/followups/khach-a-2026-MM-DD.md`).

### Use case 2 - Pre-Sales: khách hỏi RFP với 15 yêu cầu

Khách gửi RFP với 15 yêu cầu functional: lot tracking, multi-level approval, VAS reporting, multi-warehouse, customer portal, v.v. Bạn cần phản hồi đầy đủ trong 24h.

```
Bạn: "/odoo-bid-respond - Khách B (F&B chain, 50-store), 15 yêu cầu paste sau"
```

Command chạy 7-phase workflow:

1. Parse args + read `.odoo-ai/context.md` (nếu chưa có, gợi ý `odoo-onboard`).
2. Trigger `odoo-discovery-summarize` - structured profile.
3. Trigger `odoo-gap-analysis` - effort matrix (Standard / Config / Extension / Custom + S/M/L/XL days).
4. Trigger `odoo-capability-proof` cho Standard/Config items - evidence package.
5. Trigger `odoo-objection-handler` cho 2-3 anticipated objections.
6. Assemble proposal draft (VI default).
7. Save to `.odoo-ai/bids/khach-b-2026-MM-DD.md` (gated - bạn duyệt từng phase).

### Use case 3 - Strategist/CEO: viết board brief tháng

Bạn cần brief board status tháng: product progress, pipeline health, competitive landscape, top risks.

```
Bạn: "tóm tắt cạnh tranh từ Competitor A vs Viindoo cho board meeting tuần sau"
```

Skill `odoo-competitive-brief` fires. Bạn paste signals đã thu thập, skill structure thành: snapshot, capability matrix, GTM moves, threat assessment, recommended Viindoo response. Format ready for board deck.

Combine với:
- `odoo-risk-overview` cho engineering risk overview (CEO-level dashboard, không phải dev audit).
- `odoo-customization-inventory` để liệt kê tất cả custom module với business purpose (M&A due-diligence ready).

### Use case 4 - Engineer + Coder: upgrade v15 lên v17

Khách Khách C đang chạy Odoo 15 với 12 custom modules, muốn lên v17 trong Q3.

```
Bạn: "/odoo-upgrade-plan-full - Khách C v15 to v17, 12 custom modules, deadline Q3"
```

Chain 4 skill: `odoo-risk-overview` - `odoo-deprecation-audit` - `odoo-version-diff` - synthesis. Output: executive risk overview + code-level deprecation findings + API/feature diff + action ordering + S/M/L/XL effort estimate + rollback plan. Save to `.odoo-ai/upgrade-plans/khach-c-v15-v17-2026-MM-DD.md`.

Nếu cần code thực: invoke `odoo-coder` agent bundle (depth-1 safe, restricted-tool autonomy, có access OSM + ollama-delegate cost-free model).

### Câu thường gặp

**Tao chỉ cần 1 skill, không cần all 22?** OK - skills auto-fire by intent match. Bạn không phải biết hết. Cứ describe what you need; skill phù hợp sẽ trigger.

**OSM server down thì sao?** Mỗi skill có `## Standalone-first fallback` - degrade gracefully bằng cách prompt bạn paste data manually. Plugin không bị broken khi OSM offline.

**Lo confidentiality?** Plugin code public (MIT). Skills KHÔNG chứa customer-specific data hay pricing. Pre-commit hook + CI scan block 8 nhóm leak (vault path, customer name, pricing, OKR, v.v.). Examples dùng abstract labels (Khách A, Customer-A).

**Multi-runtime?** Skills + commands chuẩn Claude Code. Codex/Gemini parity smoke test ở `tests/smoke/runtime_parity.md` - 10 skill đại diện được verify chạy trên cả 3 runtime.

## Quick install (Claude Code — 3 steps, all required)

Inside Claude Code, run:

```
/plugin marketplace add Viindoo/claude-plugins   # one-time, if not already registered
/plugin install odoo-semantic@viindoo-plugins
/odoo-semantic:connect
```

> ⚠️ **`/odoo-semantic:connect` is mandatory on Claude Code v2.1.x.** Plugin manifests use a
> `userConfig` block to collect the API key + MCP URL, but the CLI currently
> does not prompt for those values at install time
> ([anthropics/claude-code#39455](https://github.com/anthropics/claude-code/issues/39455),
> [#39827](https://github.com/anthropics/claude-code/issues/39827)). Without it
> the plugin loads its skills but the MCP server silently fails — `claude mcp list`
> will not show `odoo-semantic`.
>
> ⚠️ **Restart Claude Code after `/odoo-semantic:connect`** to actually load the
> MCP tools. Claude Code v2.x does not hot-reload MCP servers within a session
> ([#46426](https://github.com/anthropics/claude-code/issues/46426) — "not
> planned"). The connect command verifies the server via `curl` and tells you
> when to restart.

You will need an **API key** (format `osm_…`) from your server admin or the
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
| `odoo-upgrade-planner` | Sonnet | DEPRECATED → use `/odoo-upgrade-plan-full` command |

## Available commands

| Command | Purpose | Chained skills |
|---------|---------|----------------|
| `/odoo-semantic:connect` | Interactive MCP server setup — prompts for URL + API key, registers server, pre-approves tools | — |
| `/odoo-bid-respond` | Full bid response chain for RFP/requirements documents | `odoo-discovery-summarize` → `odoo-gap-analysis` → `odoo-capability-proof` → `odoo-objection-handler` |
| `/odoo-customer-followup-draft` | Sales follow-up email saved to `.odoo-ai/followups/` | `odoo-deal-followup` |
| `/odoo-discovery-quick` | Slash wrapper — synthesize discovery notes into a structured profile | `odoo-discovery-summarize` |
| `/odoo-feature-positioning` | Positioning copy for marketing and sales use | `odoo-feature-highlights` → `odoo-content-draft` |
| `/odoo-upgrade-plan-full` | Comprehensive upgrade plan — replaces legacy `odoo-upgrade-planner` agent | `odoo-risk-overview` → `odoo-deprecation-audit` → `odoo-version-diff` → synthesis |

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

- **Odoo Semantic MCP server URL** — `https://odoo-semantic.viindoo.com/mcp` (or your self-hosted server)
- **API key** — format `osm_<alphanumeric>`, obtain from your server admin or the [install page](https://odoo-semantic.viindoo.com/install/)
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
| Server — indexer, Neo4j graph, pgvector, MCP server, web UI | [`Viindoo/odoo-semantic-server`](https://github.com/Viindoo/odoo-semantic-server) | AGPL-3.0-or-later |

Deploy/operate the backend: see the
[server deploy guide](https://github.com/Viindoo/odoo-semantic-server/blob/master/docs/deploy.md).

## License

MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Brand assets in `branding/` are
trademarks of Viindoo Technology JSC and are not covered by the MIT grant — see
[`branding/TRADEMARK.md`](branding/TRADEMARK.md).
