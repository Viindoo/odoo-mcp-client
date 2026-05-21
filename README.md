# Odoo MCP Client

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://github.com/Viindoo/odoo-semantic-server)

> MIT-licensed client layer for **[odoo-semantic-server](https://github.com/Viindoo/odoo-semantic-server)** (AGPL-3.0).
> A Claude Code plugin — plus IDE snippets — that brings Odoo codebase intelligence
> (inheritance chains, field impact, pattern catalogue, upgrade paths) into your AI coding workflow.

This repository ships **no semantic logic**. It is a thin integration surface: 15
persona-specific skills, 2 orchestration agents, a `connect` command, and ready-to-paste
MCP config for several AI tools. All knowledge and computation live in the Odoo Semantic
MCP server — query it at the hosted instance
[`odoo-semantic.viindoo.com`](https://odoo-semantic.viindoo.com) or
[self-host the server](https://github.com/Viindoo/odoo-semantic-server).

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
| `odoo-risk-overview` | CEO | Executive risk overview of customizations before upgrade |
| `odoo-customization-inventory` | CEO | Structured inventory of all custom modules and their business purpose |
| `odoo-override-finder` | Developer | Find the correct override point and pattern for a method |
| `odoo-deprecation-audit` | Developer | Audit deprecated API usage for upgrade readiness |
| `odoo-version-diff` | Developer + Marketer | Categorized diff of API and feature changes between versions |
| `odoo-feature-check` | Consultant | Check if a feature exists in standard CE or EE |
| `odoo-gap-analysis` | Consultant | Gap matrix of client requirements vs. standard Odoo |
| `odoo-feature-highlights` | Marketer | Marketing-friendly feature highlights for a version |
| `odoo-addon-diff` | Marketer | Side-by-side CE vs EE feature comparison |
| `odoo-capability-proof` | Sales | Evidence-based proof that Odoo supports a client requirement |
| `odoo-objection-handler` | Sales | ACA-structured responses to capability objections |
| `odoo-coder` | Developer | Python/XML backend coder with Odoo conventions baked in |
| `odoo-code-reviewer` | Developer | Review Odoo patches for ORM/inheritance/security pitfalls |
| `odoo-js-coder` | Developer | Legacy web client (v8–v14) JavaScript coder |
| `odoo-owl-coder` | Developer | OWL framework (v15+) component coder |

Per-persona quick-start guides live in [`docs/personas/`](docs/personas/).

## Available agents

| Agent | Model | Role |
|-------|-------|------|
| `odoo-router` | Haiku | Classify a user query into the correct MCP tool (classify-only, no tool calls) |
| `odoo-upgrade-planner` | Sonnet | Orchestrate a full upgrade plan from source to target version |

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
| Zed | [`snippets/zed-mcp-config.md`](snippets/zed-mcp-config.md) (setup guide) + [`snippets/zed-mcp.json`](snippets/zed-mcp.json) (config) |

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
