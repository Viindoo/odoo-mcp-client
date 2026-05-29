# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-05-29

### Changed
- **BREAKING:** Split the single `odoo-semantic` plugin into two: `odoo-semantic-skills`
  (22 skills + 2 agents + 5 workflow commands) and `odoo-semantic-mcp` (MCP server
  connection + `/odoo-semantic-mcp:connect`). Install either independently, or install
  `odoo-semantic-skills` to auto-pull `odoo-semantic-mcp` via the plugin dependency.
- Renamed the setup command `/odoo-semantic:connect` -> `/odoo-semantic-mcp:connect`.
- Relocated plugin content under `plugins/` (`plugins/odoo-semantic-skills/` and
  `plugins/odoo-semantic-mcp/`); updated `README.md` and `CONTRIBUTING.md` paths and
  per-client snippet/doc links accordingly.

### Migration
- Existing users: uninstall `odoo-semantic@viindoo-plugins`, then install
  `odoo-semantic-skills@viindoo-plugins` (pulls the MCP plugin), and re-run
  `/odoo-semantic-mcp:connect`. The MCP server name (`odoo-semantic`, tools
  `mcp__odoo-semantic__*`) is unchanged, and the marketplace name remains `viindoo-plugins`.

## [1.1.0] - 2026-05-28

### Changed
- **Full English rewrite of all top-level documentation** (`README.md`, `CHANGELOG.md`,
  `CONTRIBUTING.md`, `ROADMAP.md`, `BLOCKED_VERSIONS.md`, `CODE_OF_CONDUCT.md`,
  `NOTICE`, `VERSION`). No Vietnamese-language content remains in any public doc.
- **Neutralized Viindoo-specific framing** in `README.md`: "Viindoo CEO use case" ->
  "small-team founder use case"; "vs Viindoo" -> "vs your Odoo distribution"; Viindoo
  as legitimate project sponsor and trademark holder is retained throughout.
- **Replaced private server repository links** — all references to
  `github.com/Viindoo/odoo-semantic-server` replaced with the public hosted endpoint
  `https://odoo-semantic.viindoo.com/` or the sign-up page; self-host instructions
  redirect to post-registration server docs.
- **Fixed count claims** in `README.md`: "3 agents (2 + 1 deprecated)" corrected to
  "2 specialist agents" (deprecated agent removed from tree); "6 workflow commands"
  corrected to "5 workflow commands + 1 setup command (`/odoo-semantic:connect`)".
- **Added MCP resource URI templates section** to `README.md` documenting all 7
  `odoo://` resource templates and the 12 supported Odoo versions (v8.0 - v19.0).
- **VERSION bumped** from `1.0.0` to `1.1.0`.

No functional changes to skills, agents, or commands in this release.

## [1.0.0] - 2026-05-28

### Added
- 8 specialist personas: Engineer, Coder (agent+skill bundle), Code-Reviewer (agent+skill bundle), Pre-Sales Consultant, Sales AE, Marketer, Strategist, Onboarding/Concierge.
- 7 new skills: `odoo-frontend-coder` (merges legacy `odoo-js-coder` + `odoo-owl-coder` with v8-v19 internal version gate), `odoo-deal-followup`, `odoo-discovery-summarize`, `odoo-content-draft`, `odoo-campaign-plan`, `odoo-competitive-brief`, `odoo-deploy-checklist`.
- 2 new agent bundles in `agents/`: `odoo-coder` + `odoo-code-reviewer` (restricted-tool autonomy for code-write work).
- 5 slash command-recipes in `commands/`: `/odoo-bid-respond`, `/odoo-customer-followup-draft`, `/odoo-discovery-quick`, `/odoo-feature-positioning`, `/odoo-upgrade-plan-full` (replaces legacy `odoo-upgrade-planner` agent).
- `odoo-router` skill — silent disambiguation concierge with 21-row routing table + 4 collision-test cases.
- `odoo-onboard` skill — bootstrap Odoo project context to `.odoo-ai/context.md` (gitignored, portable markdown-bullet schema).
- SSOT generator (`generator/gen_surface.py`) — emits routing matrix + per-skill `## MCP tools` blocks + IDE snippets from `generator/server-surface.json`. Idempotent.
- Skill↔tool dependency map (`generator/skill_tool_deps.json`) + CI assertion (`generator/check_deps.py`) — fails if a skill/agent references a removed server tool.
- Confidentiality pre-commit hook + CI workflow — blocks vault paths and absolute `~/.` references in committed files.
- Multi-runtime smoke test checklist (`tests/smoke/runtime_parity.md`).
- README section "For the small-team Odoo founder" with use cases covering all 8 personas.
- `## Out of Scope` + `## Standalone-first fallback` sections in all 22 skills + 5 of 5 new commands (CI-enforced by `tests/test_skill_format.py`).
- Agent format tests (`test_agent_frontmatter`, `test_agent_depth_rule_guard`, `test_agent_skill_invocation_guard`) covering the 2 active specialist agents.

### Changed
- Plugin description + keywords updated to reflect post-refinement scope.
- 11 existing skills (`odoo-addon-diff`, `odoo-capability-proof`, `odoo-customization-inventory`, `odoo-deprecation-audit`, `odoo-feature-check`, `odoo-feature-highlights`, `odoo-gap-analysis`, `odoo-objection-handler`, `odoo-override-finder`, `odoo-risk-overview`, `odoo-version-diff`) gained `## Out of Scope` + `## Standalone-first fallback` sections.
- `odoo-coder` + `odoo-code-reviewer` skills slimmed (≤100 lines each) into agent+skill bundle pattern; execution detail moved to `agents/<name>.md`.
- `docs/reference/mcp-tool-routing.md` (442 lines) — fully generator-managed, no longer hand-maintained.

### Removed
- `skills/odoo-js-coder/` + `skills/odoo-owl-coder/` (merged into `odoo-frontend-coder`).
- Hardcoded `SKILL_TO_TOOLS` Python dict in generator — replaced by JSON SSOT in `skill_tool_deps.json`.

### Deprecated
- `agents/odoo-upgrade-planner.md` — kept in tree for git history but marked DEPRECATED; users should invoke `/odoo-upgrade-plan-full` slash command instead.

### Fixed
- Generator `description.split(".")[0]` clipping bug (truncated descriptions at inline periods like `@api.depends`, decimal version numbers).
- Confidentiality leak: 3 files referenced an absolute `~/.claude/plans/...` path — replaced with in-repo `docs/refinement-plan-2026-05-28.md`.
- 4 skills had redundant handwritten `## Additional tools (ollama-delegate)` section duplicating generator-managed content — removed.
- Agent bundle tools allowlist missing `set_active_version` — both `odoo-coder` and `odoo-code-reviewer` agents had this fixed (would have caused runtime denial of the first MCP call).
- Marker labels in 5 new B.2 skills renamed from `BEGIN GENERATED TOOLS` to honest `BEGIN MANUAL TOOLS — <name>` (since these skills are in `SKIP_SKILL_DIRS`).

### Refinement history (v0.8 → v1.0)

Plugin grew from a thin 24-tool OSM mirror into a 22-skill + 2-agent + 5-workflow-command
AI workforce toolkit organized around 8 specialist personas (Engineer, Coder,
Code-Reviewer, Pre-Sales, Sales AE, Marketer, Strategist, Onboarding-Concierge).

Delivered across 4 phases (Foundation → Specialists → Workflows → Polish) in
a multi-wave parallel orchestration using Sonnet subagents with disjoint file
ownership. Key engineering decisions: persona-as-skill-default with two
agent+skill bundles for restricted-tool autonomy; SSOT generator for tool surface;
skill-creator quality-gated router and onboard skills; depth-rule enforced at
every subagent prompt.

Detailed orchestration log retained internally.

### Migration notes
- Users invoking the legacy `odoo-upgrade-planner` agent should switch to `/odoo-upgrade-plan-full` slash command.
- `commands/discovery-summarize.md` was renamed to `commands/discovery-quick.md` (slash command is now `/odoo-discovery-quick` — the skill `odoo-discovery-summarize` retains its name for natural-language invocation).
- Custom modules using `odoo-js-coder` / `odoo-owl-coder` skill names should switch to `odoo-frontend-coder` (handles both legacy and OWL based on detected version).

### Deferred to v1.1.0
- AC-D6: router trigger optimization via `/skill-creator` Mode 5 + `run_loop.py`. The 20-query eval set is authored in `skills/odoo-router/evals/evals.json` (15 cases) + the 5 collision-test cases in `skills/odoo-router/SKILL.md`. Mode 5 requires the Claude Code subprocess API, which is CC-only; multi-runtime parity is verified manually via `tests/smoke/runtime_parity.md` for v1.0.0. Re-runnable in v1.1.0 after multi-runtime smoke is fully executed.
- AC-D8 CI version-sync test: VERSION ↔ plugin.json sync is currently manual. Add a CI assertion in v1.1.0 (e.g., `test_version_sync` in `tests/test_plugin_schema.py`).
- Confidentiality scan marker convention: PR #14 wave-2 removed the file-name allowlist entirely by moving the refinement plan to internal AI-Memory. v1.1.0 may adopt an opt-in HTML marker convention (e.g., `<!-- confidentiality-exempt: reason -->`) if any future public doc must legitimately reference a vault path — currently no such file exists, so defense-in-depth is restored without an allowlist.

## [0.8.0] - 2026-05-21

### Changed (server PR #162 / v0.9.1 surface alignment — c9cf637)
- **`license_notice` output marker** (server ADR-0036) — `describe_module` and `module_inspect(method='summary')` (and the `odoo://{version}/module/{name}` resource) may now emit a `License notice:` line for license-restricted modules. OEEL-1 modules are skipped by default, so the notice is the intentional, non-silent marker that content is withheld — documented as such in the routing matrix so an AI client treats it as expected, not a missing-data bug to retry around.
- **`lint_check(language='xml')` clarified as corpus-level** — server's RelaxNG validation (WI-E) lints the indexed views against the version-exact grammar at index time, exposing `:LintViolation` nodes. The `xml` mode returns those nodes for a version and **ignores the `code` argument** (it is not a snippet check). Documented in the `lint_check` routing-matrix entry. No new tools — server tool surface remains 24.

### Changed (server PR #160 surface alignment — f82e1a3)
- **`view_type` gains `'list'` value** (v18+ alias for `'tree'`) — documented in `view_type`
  arg descriptions for `model_inspect` and `module_inspect` across the routing matrix and all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT).
- **`.less` stylesheet coverage** — `resolve_stylesheet` and `find_style_override` now cover
  CSS, SCSS, and LESS files (LESS targets legacy v8-v11 modules). Updated routing matrix §2
  tool entries, legend, dev persona, and all adapter snippets to read "CSS/SCSS/LESS".

### Added (v0.8 server surface — M10.5 Phase 2)
- **4 new ORM-validation tools** documented across all adapter snippets (Cursor, Gemini
  Gem, OpenAI Custom GPT), routing matrix §1 & §2, Appendix table, dev persona, and the
  `odoo-coder` / `odoo-code-reviewer` skills. Static checks against the indexed graph that
  let an AI client catch hallucinated field-paths, operators, dependencies, and relation
  targets *before* it emits a domain / `@api.depends` / relational field:
  - **`resolve_orm_chain(model, dotted_path, odoo_version)`** — walks a dotted field path
    (e.g. `partner_id.country_id.code`) hop by hop, returning the terminal field type or a
    `BROKEN` line naming the first unresolved hop.
  - **`validate_domain(model, domain, odoo_version)`** — validates each `(field_path,
    operator, value)` term of a search domain. Operator validity is **version-aware**:
    `parent_of` from v9, `any`/`not any` only from v17, v19 access-rights variants.
  - **`validate_depends(model, method, odoo_version)`** — validates a compute method's
    indexed `@api.depends('a.b', ...)` paths; flags depends on `id` and suggests the closest
    field name for typos. Era1 (v8/v9) surfaces a clear "no @api.depends" note.
  - **`validate_relation(model, field, target_model, odoo_version)`** — asserts a field is a
    many2one/one2many/many2many whose comodel is `target_model` (or a subtype via
    inheritance); reports the actual comodel on mismatch.

### Changed
- **Target server v0.8 tool surface (20 → 24 tools).** Mirrors server v0.8.0 (M10.5 Phase 2,
  server PR #158). `tools/list` now reports 24 tools. Version references across README,
  routing matrix, dev persona, snippets, and setup docs bumped v0.7 → v0.8.

### Dependencies
- The 4 ORM-validation tools require server **v0.8.0** (PR #158). `validate_depends`
  additionally requires the prod `mth.depends` backfill (`python -m src.indexer index-repo
  --all --full`) — until it runs, `validate_depends` returns the "no @api.depends" note for
  methods indexed before the reindex. That backfill is now scheduled as server **PR #159**
  (M10C polish wave) — the full reindex v8→v19, with the ordered runbook in
  `docs/deploy/m10-postmerge-ops.md` (in the server repository).
  PR #159 introduces no new MCP tools (surface stays 24), so this client release needs no
  tool changes for it; recommend landing this release alongside that reindex so
  `validate_depends` is fully functional on the live surface.

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
  server CHANGELOG (available after sign-up at https://odoo-semantic.viindoo.com/).

## [0.3.x] - 2026-03-01

- M7.5 persona-skill batch: the original 15-skill set and routing agents were
  introduced. See the
  server CHANGELOG (available after sign-up at https://odoo-semantic.viindoo.com/)
  for the detailed history.
