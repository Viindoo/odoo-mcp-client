# Odoo Semantic Plugin for Claude Code

A Claude Code plugin that brings Odoo codebase intelligence into your AI coding workflow. Adds 11 persona-specific skills, 2 orchestration agents, and a setup command powered by the Odoo Semantic MCP server.

## Quick install

```bash
claude plugin install dist/odoo-semantic-plugin/
```

After install, run the setup command:

```
/odoo-semantic:setup
```

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

## Available agents

| Agent | Model | Role |
|-------|-------|------|
| `odoo-router` | Haiku | Classify a user query into the correct MCP tool (classify-only, no tool calls) |
| `odoo-upgrade-planner` | Sonnet | Orchestrate a full upgrade plan from source to target version |

## Setup command

```
/odoo-semantic:setup
```

Interactive setup that:
1. Prompts for your MCP server URL and API key
2. Validates key format (`osm_...`)
3. Updates `~/.claude.json` with the MCP server config
4. Runs a connectivity check against `resolve_model`

## Requirements

- **Odoo Semantic MCP server URL** — self-hosted or use `https://odoo-semantic.viindoo.com:9999/mcp`
- **API key** — format `osm_<alphanumeric>`, obtain from your server admin or via `/install/` endpoint
- Claude Code with MCP support

## Environment variable

Set `ODOO_SEMANTIC_API_KEY` in your shell for automatic authentication via `.mcp.json`:

```bash
export ODOO_SEMANTIC_API_KEY=osm_yourkey
```
