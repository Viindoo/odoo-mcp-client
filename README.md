# Odoo Semantic Plugin for Claude Code

A Claude Code plugin that brings Odoo codebase intelligence into your AI coding workflow. Adds 15 persona-specific skills, 2 orchestration agents, and a connect command powered by the Odoo Semantic MCP server.

## Quick install (3 steps — all required)

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
5. **Adds `mcp__odoo-semantic` to `permissions.allow` in `~/.claude/settings.json`** so every tool of this server (current 14 + future ones) is pre-approved — no more "Do you want to proceed?" prompts on every call. Idempotent, backs up the file before writing, refuses to overwrite invalid JSON, preserves every other key. Answer `n` at the prompt to skip (you can paste the snippet from [`docs/client-setup.md#claude-code-auto-trust`](../../docs/client-setup.md#claude-code-auto-trust) manually instead).
6. Tells you to restart Claude Code (required to load MCP tools)

## Requirements

- **Odoo Semantic MCP server URL** — `https://odoo-semantic.viindoo.com:9999/mcp` (provided by your admin)
- **API key** — format `osm_<alphanumeric>`, obtain from your server admin or via the `/install/` endpoint
- Claude Code with MCP support (tested on v2.1.140)


## For contributors — local dev install

Test changes from a checkout without going through the marketplace:

```bash
claude --plugin-dir ./
```
