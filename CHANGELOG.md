# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-05-19

### Added
- Initial **public** release of the Odoo MCP Client as a standalone MIT-licensed
  repository, split out of the `odoo-semantic` monolith.
- 15 persona-specific skills (CEO, Developer, Consultant, Marketer, Sales).
- 2 orchestration agents (`odoo-router`, `odoo-upgrade-planner`).
- `/odoo-semantic:connect` command for one-step MCP server setup.
- Multi-client MCP config snippets (Cursor, ChatGPT Custom GPT, Gemini Gem).
- Per-persona quick-start guides under `docs/personas/`.

### Notes
- This client targets the v0.5.0 server tool surface (28 tools + 7 MCP Resources).
  The 10 legacy `resolve_*` / `list_*` tools are deprecated and slated for removal
  in the server's v0.6.

## [0.4.x] - 2026-04-15

- Pre-split history. The plugin shipped as `dist/odoo-semantic-plugin/` inside the
  monolith repository. Full server-side changes for this period are recorded in the
  [server CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md).

## [0.3.x] - 2026-03-01

- M7.5 persona-skill batch: the original 15-skill set and routing agents were
  introduced. See the
  [server CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md)
  for the detailed history.
