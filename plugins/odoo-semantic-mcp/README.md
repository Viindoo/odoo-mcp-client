# odoo-semantic-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Backend: AGPL-3.0](https://img.shields.io/badge/backend-AGPL--3.0-blue.svg)](https://odoo-semantic.viindoo.com/)

> The **connection layer** that wires the [Odoo Semantic MCP server](https://odoo-semantic.viindoo.com/)
> into your AI agent. Install this alone if you only want the raw MCP tools - no persona skills,
> agents, or commands. For the full Odoo workforce toolkit, install the companion
> [`odoo-ai-agents`](../odoo-ai-agents/) plugin instead (it pulls this one in automatically).

## What this plugin provides

- An HTTP MCP server registration (`odoo-semantic`) exposing **25 tools** and **7 resource URI
  templates** for semantic Odoo code intelligence - inheritance chains, field impact, model
  inspection, ORM validation, and more - over indexed Odoo source (**v8.0 onward**).
- A single slash command, `/odoo-semantic-mcp:connect`, to configure and verify the connection.

All knowledge and computation live on the OSM server; this plugin is a thin connection shim.

## Quick install (Claude Code)

```
/plugin marketplace add Viindoo/claude-plugins   # one-time, if not already registered
/plugin install odoo-semantic-mcp@viindoo-plugins
/odoo-semantic-mcp:connect
```

Then **restart Claude Code** so the MCP tools load (see [known bugs](#known-claude-code-bugs)).

You will need an **API key** (format `osm_...`) from the
[install page](https://odoo-semantic.viindoo.com/install/), and the **MCP server URL**
(default `https://odoo-semantic.viindoo.com/mcp`).

> **Want the persona skills too?** Install [`odoo-ai-agents`](../odoo-ai-agents/)
> instead - it declares `odoo-semantic-mcp` as a dependency, so the skills, agents, commands,
> and this MCP connection all arrive in one step.

## The `connect` command

`/odoo-semantic-mcp:connect`:

1. Prompts for your MCP server URL and API key.
2. Validates the key format (`osm_...`).
3. Registers the server via `claude mcp add --scope user`.
4. Probes the server health endpoint.
5. Pre-approves all `mcp__odoo-semantic__*` tools in `~/.claude/settings.json` (idempotent).

Full parameter details and the manual snippet for `permissions.allow` are in
[`docs/setup.md#claude-code-auto-trust`](../odoo-ai-agents/docs/setup.md#claude-code-auto-trust).

## MCP tools and resources

The server exposes **25 tools** and **7 resource URI templates** (`odoo://{version}/{kind}/{id}`,
where `kind` is one of `model`, `field`, `method`, `view`, `module`, `pattern`, `stylesheet`).
Full URI descriptions, parameter reference, and usage examples are in
[`docs/setup.md`](../odoo-ai-agents/docs/setup.md#mcp-resources-odoo-uri-scheme-v05).

Supported Odoo versions: **v8.0 onward** - every major the OSM server has indexed (query
`list_available_versions` for the live set).

## Configuration

This plugin declares a `userConfig` block (API key + MCP URL) consumed by `.mcp.json`:

| Key | Description | Default |
|-----|-------------|---------|
| `api_key` | Odoo Semantic API key (`osm_...`), marked sensitive | *(required)* |
| `mcp_url` | Base URL of your MCP server | `https://odoo-semantic.viindoo.com/mcp` |

If Claude Code does not prompt for these at install time (a known v2.1.x bug), run
`/odoo-semantic-mcp:connect` afterward to set them.

<a name="known-claude-code-bugs"></a>
<details>
<summary>Known Claude Code bugs affecting this install (v2.1.x)</summary>

**Bug 1 - `userConfig` not prompted at install time**
([#39455](https://github.com/anthropics/claude-code/issues/39455), [#39827](https://github.com/anthropics/claude-code/issues/39827))
The CLI does not prompt for `userConfig` values at install time, so the MCP server silently
fails until you run `/odoo-semantic-mcp:connect` (`claude mcp list` will not show
`odoo-semantic`). This is why the connect step is **mandatory**.

**Bug 2 - MCP servers not hot-reloaded within a session**
([#46426](https://github.com/anthropics/claude-code/issues/46426) - "not planned")
After running `/odoo-semantic-mcp:connect`, **restart Claude Code** for the MCP tools to load.
The connect command verifies the server via `curl` and tells you when to restart.

</details>

## Other AI tools

This plugin packages the connection for Claude Code. For other clients (Cursor, ChatGPT,
Gemini, Continue.dev, VS Code, Zed, Windsurf, JetBrains), paste the matching MCP config -
copy-ready snippets and per-client walkthroughs live in the companion plugin under
[`odoo-ai-agents/snippets/`](../odoo-ai-agents/snippets/) and
[`docs/setup.md`](../odoo-ai-agents/docs/setup.md).

## Requirements

- **Odoo Semantic MCP server URL** - `https://odoo-semantic.viindoo.com/mcp` (or your self-hosted instance)
- **API key** - format `osm_<alphanumeric>`, obtain from the [install page](https://odoo-semantic.viindoo.com/install/)
- Claude Code with MCP support (v2.1.x or newer)

## Relationship to the server

| Layer | Repository | License |
|-------|------------|---------|
| Client (this plugin) - MCP connection + `connect` command | `Viindoo/odoo-mcp-client` | MIT |
| Server - indexer, Neo4j graph, pgvector, MCP server, web UI | [odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/) | AGPL-3.0-or-later |

## License

MIT - see [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). This plugin is part of the
[`odoo-mcp-client`](../../README.md) monorepo.
