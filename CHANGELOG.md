# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.5.0] - 2026-06-03

### Added

- **Frontend fidelity (#37)** — make AI-authored Odoo OWL/JS + SCSS correct and lint-compliant
  by construction: an era-sectioned SSOT pitfall catalogue
  (`skills/_shared/odoo-frontend-fidelity.md`, v8–v19+), a write-time OWL grounding checklist
  plus a post-write verify gate (`scripts/verify-frontend.sh`, `scripts/rules/owl-pitfalls.txt`,
  `scripts/odoo-prettierrc.json`), and passing/broken `odoo-frontend-coder` examples.
- **Agent-facing guidance guard** (`tests/test_agent_facing_guidance.py`) — four checks keeping
  skills/snippets/agents/docs in sync with the server tool surface: no "omit/optional
  odoo_version" prose, no drifted parameter names, every named argument is a real parameter of
  its tool, and every example call to a version-required tool supplies `odoo_version`.

### Fixed

- Corrected AI-agent-facing tool guidance for the now-required `odoo_version`: removed
  "can omit / optional, default auto" prose, added `odoo_version='auto'` to ~166 example calls,
  and fixed drifted parameter names (`check_module_exists(module=)`→`name`,
  `find_deprecated_usage(scope=)` dropped, `lint_check(code_snippet=)`→`code`,
  `suggest_pattern(query=)`→`intent`, `lookup_core_api(symbol=)`→`name`,
  `api_version_diff(scope)`→`symbol`) across skills, the cursor/gemini/openai snippets, and
  agent definitions.
- **Tool-permission grants for file-authoring skills** — removed the `disallowed-tools: Write Edit`
  frontmatter block from the four skills whose own contract is to write deliverables to disk
  (`odoo-brl` → `.odoo-ai/brl/` rtm.csv/cost.json/dag/report.md, `odoo-qa-suite` →
  `.odoo-ai/qa/*.md`, `workflow-runner` → `output_dir` artifacts + checkpoints, `wave` →
  `.odoo-ai/wave/<slug>/plan.md`), which were previously blocked from delivering their output.
- Restored `odoo-coder` / `odoo-frontend-coder` to write/apply code directly (with a patch
  preview before applying), per the README's coder intent ("Coder — Write Odoo backend or
  frontend code", "fix writer … writes the override and shows a patch preview before
  applying") — undoing the v2.4.0 `disallowed-tools: Write Edit` drift that had reduced them
  to copy-paste-only. Removed the block from both skills, added `Write`/`Edit` to the
  `odoo-coder` agent's tool list, and reframed Phase 0 as a patch preview (not a write-block).
  The OSM-unreachable Standalone-first fallback stays paste-only.
- **AI-agent-consumer review follow-ups:**
  - Workflow-harness doc sync — `docs/reference/workflow-harness.md` no longer claims a
    platform-enforced `disallowed-tools: Write Edit` write-block (the gate is now behavioral
    Iron Law + Plan Mode; coders preview a patch then write). Updated the layer diagram,
    enforcement-stack table, and the mechanisms prose.
  - `set_active_version` 'auto'-needs-pin warning — clarified in `generator/server-surface.json`
    (the regeneration SSOT) that the tool needs a CONCRETE version (sentinels rejected), other
    calls reuse the pin via `odoo_version='auto'`, and `'auto'` is only safe AFTER a pin —
    without a pinned session it silently falls back to the latest indexed version. Regenerated
    all derived blocks.
  - Frontend gate hardening (`scripts/verify-frontend.sh` + `scripts/rules/owl-pitfalls.txt`):
    class-3 (`contenteditable`) now anchors on a quoted template attribute and only scans
    `.xml`/`.html`, so a JS CSS-selector string like `querySelector("[contenteditable=true]")`
    no longer hard-blocks; class-1 now also catches params-before-arrow (`(ev) => onSave(ev)`),
    PascalCase, and leading-underscore handlers while still ignoring `this.`/`props.` forms;
    portability fixes for macOS bash 3.2 (`mapfile`→read-loop, guarded empty-array expansion).
    Added a `class1_handlers.xml` fixture and a JS-selector case to the good fixture.
  - Agent-facing guard (`tests/test_agent_facing_guidance.py`) now matches the fully-qualified
    `mcp__<server>__tool(...)` call form (not just the bare name) and credits a positional
    toward `odoo_version` only when positionals reach its slot in the tool's canonical
    signature order — catching `suggest_pattern(...)`, `lint_check(code_chunk)`, and bare
    `cli_help(...)`/`lint_check(...)` calls that omitted the now-required version; fixed all
    the calls it newly caught.
  - Corrected the class-4 SCSS literal in `skills/_shared/odoo-frontend-fidelity.md` to the
    real Odoo source line `calc(#{map-get($spacers, 1 )} / 2)`
    (`calendar_renderer.scss:2`), replacing a fabricated `calc(#{map-get($spacers, 2)} * 2)`.

## [2.4.2] - 2026-06-02

### Build / CI

#### Added

- **`requirements.txt`** — single source of truth for test dependencies (`pytest` + `PyYAML`);
  previously undeclared, causing contributors to install deps ad-hoc and PyYAML-gated
  workflow tests to silently skip (~99 parametrized cases masked by the missing import).
- **`make setup`** — bootstraps `.venv` by probing for Python >= 3.12 (`python3.12` through
  `python`). All Makefile targets (`make test`, `make validate`, etc.) now run through
  `$(VENV)/bin/python` and auto-bootstrap the venv on first use if `make setup` was skipped.
- **Python 3.12+ prerequisite** documented in `README.md` (contributor section) and
  `CONTRIBUTING.md` (local development prerequisite).

#### Changed

- **CI `validate.yml` `schema` job** now runs `pip install -r requirements.txt` (was
  `pip install pytest`), ensuring PyYAML is present and the workflow-format test suite
  runs its full parametrized case set.

### odoo-semantic-skills

#### Changed

- Disambiguated the `odoo-semantic` name left over from the pre-split single
  plugin. Skill trigger phrases in `odoo-onboard` and `intake` now say
  `Odoo` (the onboarding skill bootstraps Odoo project context and installs no
  plugin), and standalone-fallback prose in `odoo-coder`, `odoo-code-reviewer`,
  `odoo-ui-reviewer`, `odoo-frontend-coder`, `odoo-onboard`, `upgrade-plan-full`,
  and `setup` now names `the odoo-semantic-mcp server` explicitly. Runtime
  identifiers (the MCP server id `odoo-semantic`, the `mcp__odoo-semantic__*`
  tool prefix, the brand `Odoo Semantic`, and the product URL) are unchanged.
- Compacted every specialist skill `description` under the 1024-character per-entry
  cap (28 skills; ~40,071 → ~27,051 chars, −32%). This eliminates skill-listing
  truncation — previously 28 descriptions exceeded the cap, forcing Claude to drop
  descriptions and degrade triggering. All `route to …` / `DO NOT trigger → …`
  disambiguation clauses, bilingual (EN+VN) triggers, version-resolution, and
  OSM-grounding signals are preserved; skill bodies, generated `## MCP tools` blocks,
  and output contracts are untouched. Validated against an isolated real-skill
  triggering eval (NEW vs OLD descriptions, flat aggregate). `intake` collision-zone
  guidance re-synced (`description matches` → `handles`).

#### Added

- `tests/test_skill_description_budget.py` (every skill description ≤ 1024 chars) and
  `tests/test_intake_quote_sync.py` (every skill/workflow the `intake` router names must
  exist) guardrails, locking in the description compaction above.
- `tests/test_naming_consistency.py` guardrail: fails if a bare `odoo-semantic`
  token reappears in the skill / command / trigger-phrase surface, allowlisting
  the server id, tool prefix, suffixed plugin names, and product URL.
- A naming-policy table in `CONTRIBUTING.md` documenting which form to use.
- A "First-time setup flow" table in `README.md` and `docs/setup.md` that
  distinguishes the three easily-confused setup steps: `/odoo-semantic-mcp:connect`
  (required, per machine), `/odoo-semantic-skills:setup` (optional visual stack,
  per machine), and the `odoo-onboard` skill (optional, per repo).

## [2.3.0] - 2026-05-31

### odoo-semantic-skills

#### Added

- **`wave` skill** — depth-0 multi-subagent git-wave orchestration: integration branch +
  WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate
  + human-confirm merge. Self-spawning, principal-branch-locked, auto-merge never allowed.
  Covers 1-WI minimal through ≥4-WI full plan-artifact (`.odoo-ai/wave/<slug>/plan.md`)
  with topology diagram and disjoint ownership map.
- **`/odoo-semantic-skills:wave-run` command** — thin dispatcher to the `wave` skill;
  accepts optional work-item description, emits plan gate before any branch is created.

## [2.2.0] - 2026-05-31

### odoo-semantic-skills

#### Added

- **`intake` skill** — universal front door for all 9 persona buckets (CEO/strategist,
  consultant, sales AE, pre-sales, marketer, developer, QA, customer-success). Handles
  vague prompts via a 4-tier brainstorm-or-fast-path routing flow, proposes a plan gate
  before any execution skill fires, and is depth-0 only (never spawns subagents).
- **`odoo-brl` skill** — BRL engine for classifying and costing tens-to-thousands of
  business requirements: 4-way classification (CE/EE/Viindoo/Custom), deterministic cost
  lookup, dependency DAG with Kahn topological sort, and checkpoint/resume support for
  large jobs.
- **3 domain workflow YAMLs** — `bid-respond.workflow.yaml`, `discovery-pipeline.workflow.yaml`,
  and `feature-positioning.workflow.yaml` added as composition-runnable workflows using
  the `workflow-runner` skill as the execution harness.
- **Security hardening** — confidentiality guard expanded to cover 8 banned content groups
  across all skill/agent/command surface; intake hard-rule enforces depth-0 constraint.

#### Changed

- **Plugin command count corrected**: `commands` array now has 8 entries (added
  `odoo-brl-run.md` and `odoo-video-produce.md`); plugin.json description updated from
  "7 workflow commands" to "8 workflow commands".
- **Renamed `odoo-router` → `intake`**: the universal front-door skill was renamed for
  clarity; all cross-references updated.
- **VERSION bumped** from `2.1.0` to `2.2.0`, kept in sync with `plugin.json.version`.

## [2.1.0] - 2026-05-29

### Added
- **Visual UI testing stack** for the `odoo-semantic-skills` plugin — review, debug,
  regression-test, and record a *rendered* Odoo UI in a live browser (complementing the
  existing source-level skills). Four new skills:
  - `odoo-ui-reviewer` — five-lens verdict (aesthetics, functional correctness, runtime
    stability, accessibility, performance) on a rendered screen (slim; paired with the new
    `odoo-ui-reviewer` agent bundle).
  - `odoo-ui-debug` — root-cause a broken/misbehaving UI at runtime (console errors, failed
    requests, blank OWL renders, CSS that renders wrong) and point at the exact override point.
  - `odoo-visual-regression` — screenshot-baseline + diff between two Odoo states (before/after
    an upgrade, module install, theme change, or code edit) with blast-radius assessment.
  - `odoo-demo-recorder` — record an MP4/GIF screen-capture of a scripted Odoo click-path for a
    demo, sales walkthrough, or marketing clip.
- **`odoo-ui-reviewer` agent bundle** (`agents/odoo-ui-reviewer.md`, Sonnet) — drives the
  multi-step browser review with screenshot/console/Lighthouse evidence plus OSM source pointers.
- **Bundled browser MCP servers** (`.mcp.json`) — `chrome-devtools`, `playwright`, and
  `pagecast` (local stdio `npx` servers) load automatically when the plugin is installed,
  powering the visual stack.
- **`/odoo-semantic-skills:setup` command** — one-shot, idempotent, extensible setup for the
  visual workflow. Drives a registry of numbered step scripts (`scripts/setup-steps/`), each
  with a `describe | check | apply` contract: wires the 3 browser MCP servers across Claude
  Code / Codex CLI / Gemini CLI, installs browser dependencies (Node >= 20, Playwright
  Chromium, ffmpeg), auto-allows the browser tool permissions, discovers local Odoo repos into
  `.odoo-ai/instances.toml`, and optionally spins up a declared instance.
- **SessionStart hook** (`hooks/hooks.json` + `hooks/check-setup-deps.sh`) — read-only
  readiness probe that hints `/odoo-semantic-skills:setup` when visual-stack deps are missing;
  silent when everything is ready, never installs or blocks.
- **Shared setup utilities** (`scripts/lib/`) — `config_merge.py` (idempotent cross-runtime MCP
  config merge) and `discover_odoo.sh` (local Odoo instance discovery), reused by the
  setup-step scripts.

### Changed
- Plugin description + keywords bumped to reflect the visual stack — now **26 skill personas +
  3 specialist agents + 6 workflow commands** across engineering, sales, marketing, strategy,
  onboarding, and visual UI testing.
- Documentation counts corrected from `22 skills / 2 agents / 5 commands` to
  `26 skills / 3 agents / 6 commands` across `README.md` and `docs/setup.md`.
- **VERSION bumped** from `2.0.1` to `2.1.0`, kept in sync with the skills plugin's
  `plugin.json.version`.

## [2.0.1] - 2026-05-29

### Fixed
- **Broken docs anchor in `README.md`** — the MCP-resources link pointed at the stale
  `docs/setup.md#mcp-resources-7-uri-templates` fragment; corrected to the actual
  `plugins/odoo-semantic-skills/docs/setup.md#mcp-resources-odoo-uri-scheme-v05` heading.
- **Stylesheet resource URI template** corrected to
  `odoo://{version}/stylesheet/{module}/{file_path*}` (was missing the `{module}` segment
  and `*` wildcard), matching the server surface.
- **Module resource description** now notes the `license notice if restricted` line,
  aligning the README with the server surface.

### Changed
- **Server-surface reference bumped to v0.11.1** (from the v0.8 surface the changelog
  previously implied as current). The v0.11.1 surface keeps the 24-tool / 7-resource
  count and folds in the v0.9.1 `license_notice` output marker and the v0.10.0
  `module_inspect(method='dependencies')` capability, so the changelog no longer reads
  v0.8 as the live target.
- **README tested-build note** updated to Claude Code v2.1.156.

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
- Confidentiality scan marker convention: PR #14 wave-2 removed the file-name allowlist entirely by moving the refinement plan to an internal planning document. v1.1.0 may adopt an opt-in HTML marker convention (e.g., `<!-- confidentiality-exempt: reason -->`) if any future public doc must legitimately reference an internal-only path — currently no such file exists, so defense-in-depth is restored without an allowlist.

## [0.8.0] - 2026-05-21

### Changed (server v0.9.1 surface alignment)
- **`license_notice` output marker** — `describe_module` and `module_inspect(method='summary')` (and the `odoo://{version}/module/{name}` resource) may now emit a `License notice:` line for license-restricted modules. OEEL-1 modules are skipped by default, so the notice is the intentional, non-silent marker that content is withheld — documented as such in the routing matrix so an AI client treats it as expected, not a missing-data bug to retry around.
- **`lint_check(language='xml')` clarified as corpus-level** — the server lints indexed views against the version-exact grammar at index time, exposing server-indexed XML lint findings. The `xml` mode returns those findings for a version and **ignores the `code` argument** (it is not a snippet check). Documented in the `lint_check` routing-matrix entry. No new tools — server tool surface remains 24.

### Changed (server v0.9.0 surface alignment)
- **`view_type` gains `'list'` value** (v18+ alias for `'tree'`) — documented in `view_type`
  arg descriptions for `model_inspect` and `module_inspect` across the routing matrix and all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT).
- **`.less` stylesheet coverage** — `resolve_stylesheet` and `find_style_override` now cover
  CSS, SCSS, and LESS files (LESS targets legacy v8-v11 modules). Updated routing matrix §2
  tool entries, legend, dev persona, and all adapter snippets to read "CSS/SCSS/LESS".

### Added (v0.8 server surface)
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
- **Target server v0.8 tool surface (20 → 24 tools).** Mirrors server v0.8.0. `tools/list` now reports 24 tools. Version references across README,
  routing matrix, dev persona, snippets, and setup docs bumped v0.7 → v0.8.

### Dependencies
- The 4 ORM-validation tools require server **v0.8.0**. `validate_depends`
  additionally requires a server-side backfill operation (see server docs) — until it runs,
  `validate_depends` returns the "no @api.depends" note for methods indexed before the
  reindex. The backfill introduces no new MCP tools (surface stays 24), so this client
  release needs no tool changes for it; recommend landing this release alongside that
  reindex so `validate_depends` is fully functional on the live surface.

## [0.7.0] - 2026-05-21

### Added (v0.7 server surface)
- **2 new stylesheet tools** (`resolve_stylesheet`, `find_style_override`) added to all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT), routing matrix §1 & §2,
  Appendix table, and dev persona. `resolve_stylesheet` enumerates a module's CSS/SCSS
  files; `find_style_override` does pgvector semantic search (with import-chain traversal) for
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
