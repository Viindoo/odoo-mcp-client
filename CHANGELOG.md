# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-05-21

### Added (v0.7 server surface)
- **2 new stylesheet tools** (`resolve_stylesheet`, `find_style_override`) added to all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT), routing matrix §1 & §2,
  Appendix table, and dev persona. `resolve_stylesheet` enumerates a module's CSS/SCSS
  files; `find_style_override` does pgvector + `:IMPORTS`-chain semantic search for
  selector/variable origin and overrides.
- **`from_module` filter** on `model_inspect` (method=`summary`/`fields`/`field`) and
  `entity_lookup` (kind=`model`/`field`) — restrict results to declarations from a
  specific module.
- **`kind` filter** on `model_inspect` (method=`fields`) — filter fields by type
  (e.g. `'many2one'`).
- **`view_type` filter** on `model_inspect` (method=`views`) and `module_inspect`
  (method=`views`) — filter by view type (e.g. `'form'`/`'tree'`).
- **`bound_model` filter** on `module_inspect` (method=`owl`) — restrict OWL components
  to those bound to a specific model.
- **`era` filter** on `module_inspect` (method=`js`) — filter JS patches by era
  (`era1`/`era2`/`era3`).
- **`noqa` support in `lint_check`** — inline `# noqa: RULE_ID` (or bare `# noqa`) in
  the `code` argument suppresses findings on that line. Documented in routing matrix,
  all three adapter snippets, and both affected skills (`odoo-coder`,
  `odoo-code-reviewer`).

### Changed (v0.6 migration — also part of this release)
- **Target server v0.6 tool surface.** The upstream server removed the 10
  deprecated flat tools (`resolve_model`, `resolve_field`, `resolve_method`,
  `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`,
  `list_qweb_templates`, `list_js_patches`) per server ADR-0028. All client adapter
  snippets (Cursor, Gemini Gem, OpenAI Custom GPT), persona docs, and the routing
  matrix have been migrated to reference the 3 superset discriminator tools
  (`model_inspect`, `module_inspect`, `entity_lookup`) that replace them.
- **Removed `odoo-router` classifier agent.** The agent was redundant: Claude Code
  discovers available tools at runtime via the MCP `tools/list` call, and the 3
  superset discriminator tools (`model_inspect`, `module_inspect`, `entity_lookup`)
  handle entity-type routing server-side without a dedicated client-side classifier.
- **Replaced hardcoded tool counts with capability phrasing** across README, snippets,
  and persona docs so the count never drifts out of sync with the server again.
- **Fixed `module_inspect` arg name drift**: routing matrix and adapter snippets now
  consistently use `name` (required) instead of `module` for the module name parameter.

## [0.5.0] - 2026-05-21

### Added
- `BLOCKED_VERSIONS.md` kill-switch registry: add a short SHA to block automatic
  marketplace pin for known-bad commits; `pin-sha.yml` reads the table and skips
  the pin step (fail-soft — CI stays green) when the HEAD SHA matches.
- `commands/connect.md`: added missing `name: connect` frontmatter field to match
  agent/skill convention (`name:` before `description:`).
- Initial **public** release of the Odoo MCP Client as a standalone MIT-licensed
  repository, split out of the `odoo-semantic` monolith.
- 15 persona-specific skills (CEO, Developer, Consultant, Marketer, Sales).
- 2 orchestration agents (`odoo-router`, `odoo-upgrade-planner`).
- `/odoo-semantic:connect` command for one-step MCP server setup.
- Multi-client MCP config snippets (Cursor, ChatGPT Custom GPT, Gemini Gem).
- Per-persona quick-start guides under `docs/personas/`.

### Notes
- This client targeted the v0.5.0 server tool surface (28 tools + 7 MCP Resources).
  The 10 legacy `resolve_*` / `list_*` tools were deprecated and have since been
  removed in the server's v0.6 (see [0.6.0] above).

## [0.4.x] - 2026-04-15

- Pre-split history. The plugin shipped as `dist/odoo-semantic-plugin/` inside the
  monolith repository. Full server-side changes for this period are recorded in the
  [server CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md).

## [0.3.x] - 2026-03-01

- M7.5 persona-skill batch: the original 15-skill set and routing agents were
  introduced. See the
  [server CHANGELOG](https://github.com/Viindoo/odoo-semantic-server/blob/master/CHANGELOG.md)
  for the detailed history.
