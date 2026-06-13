# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [3.10.0] - 2026-06-13

### Added

- **Two-variant browser MCP servers (headless default + headed on request).** Each browser backend
  (chrome-devtools, playwright, pagecast) now ships TWO servers: a headless default (`<name>`, passes
  `--headless`) and a visible `<name>-headed` variant — 6 servers total. The AI agent selects the
  `-headed` variant only when the human asks to watch the browser; the choice is which tool it calls
  (NL/AI-driven), NOT an env var or on-disk flag. chrome-devtools + playwright also pass `--isolated`
  so concurrent Claude/Codex/Gemini sessions get a private profile (fixes the "browser already
  running, use --isolated" collision); the headless default makes the visual stack work on
  no-display/CI hosts out of the box.
- **`hooks/ensure-browser-permissions.sh` (SessionStart).** Self-applies the browser MCP tool
  permission prefixes to `~/.claude/settings.json` on every session (idempotent; no-op once present),
  so the visual-UI agents run without a per-tool approval prompt after any install/update. Opt out
  with `ODOO_AI_NO_AUTO_PERMS=1`.

### Changed

- **`odoo-ui-reviewer` / `odoo-ui-debugger` are now self-contained**: they grant the plugin's OWN
  browser prefix (`mcp__plugin_odoo-ai-agents_chrome-devtools__*`) plus its `-headed` variant,
  dropping the implicit dependency on the standalone `chrome-devtools-mcp` plugin. Both default to the
  headless variant and switch to `-headed` only when the dispatch brief carries `BROWSER MODE: headed`.
- **`30-permissions.sh`** allow-lists the plugin-namespaced own prefixes
  (`mcp__plugin_odoo-ai-agents_{chrome-devtools,playwright,pagecast}`), which match both the headless
  and `-headed` variants.

## [3.9.0] - (unreleased)

### Added

- **New opt-in `odoo-deep-survey` skill**: a read-only, multi-phase survey (broad haiku sweep ->
  narrow sonnet dives -> optional opus pass) that `odoo-intake` offers on large / open-ended jobs.
  When the user approves `deep-survey`, it writes a synthesis under `.odoo-ai/survey/` that
  re-informs a sharper Proposed Plan before any code is written (read-only; spawner-agent,
  depth0-only). Skill count 40 -> 41.
- **Two new grounding-contract SSOT snippets** loaded by reference (edit once, not per agent):
  `snippets/read-before-write-contract.md` (read the target version's coding guidelines BEFORE
  writing code and conform on the first pass, not patched against a checklist afterward) and
  `snippets/test-behavior-contract.md` (tests drive the REAL workflow via
  `action_confirm`/`button_validate`/`Form()`/`with_user()` and assert observable outcomes, never
  seeding the terminal state with `create({'state': ...})`).

### Changed

- **`odoo-intake` resolves the Odoo version up front**: it escalates to `odoo-onboarding` to pick
  version/profile when the version is unknown and OSM is reachable (inline-menu fallback), or asks
  for the version + repo path when OSM is down - making the recon and plan context-aware.
- **`odoo-intake` fast-paths review / PR-review and debug intents**: these route straight to
  `odoo-code-review` / `odoo-debug` with no Proposed-Plan block and no Plan Mode.
- **Autonomous fix loop**: on a CRITICAL/HIGH finding, `odoo-code-review` / `odoo-debug` now drive
  the fix on their own through `odoo-coding` and re-review to verify (review -> code -> review),
  bounded to 3 rounds then escalates.
- **Agent identity priming**: each agent is primed with its own identity at the start of its run.
- **Plugin-wide removal of private-vault citations**: the ETHOS and Iron-Law references that named
  a private vault are renamed to in-plugin concept names - Anti-rationalize gate, Root-cause-first
  rule, and Pre-wave gate - so the public plugin is self-contained.
- **Skill-conflict resolution consolidated**: the `odoo-coding` legacy-JS-vs-OWL paradigm rule
  (previously §4.4 of the routing matrix) now lives in the generated
  `docs/reference/ORCHESTRATION-MAP.md`, which also points to
  `skills/odoo-intake/references/collision-zones.md` for the full collision policy.

### Removed

- **`docs/reference/mcp-tool-routing.md` deleted** (was 437 lines, generator-managed): the
  static-vs-live guidance it carried is already injected by the MCP server and duplicated in every
  skill's `## MCP tools` block + the IDE snippets, and its tool/persona/param tables duplicated the
  live `tools/list` schema and per-agent tool whitelists. `gen_surface.py` no longer emits it.
- **Execute-agent noise stripped from skill bodies**: the `_Tool surface: server vX._` version stamp
  (28 skill `## MCP tools` blocks, both generated and manual) and the `## Notes for future
  maintainers` roadmap subsection in `odoo-onboarding` carried no signal for an executing agent and
  were removed. The IDE-adapter snippets keep their stamp (they target non-Claude clients).

## [3.8.0] - 2026-06-12

### Added

- **Execute-agent hardening across the design -> code -> review -> debug chain** (#68): six SSOT
  contracts that the relevant agents now load by reference (edit once, not per agent) -
  `snippets/worklog-contract.md` (append-only cross-agent decision log under
  `.odoo-ai/worklog/<run>/`), `snippets/odoo-platform-design-principles.md` (multi-company + branch
  v17+, generic-before-localization, standard app-menu shape), `snippets/bidirectional-impact.md`
  (upstream + downstream impact, direct + indirect), `snippets/demo-data-dynamic.md` (time-relative
  `relativedelta` demo data), `snippets/test-first-contract.md` (red-before-green), and
  `skills/_shared/odoo-module-graph.md` (the shared Odoo module DAG). The five coder / reviewer /
  debugger agents that lacked it gain the `mcp__odoo-semantic__impact_analysis` tool.
- **Test-first loop in `odoo-coding`**: a separate test-author writes a failing test before the
  code for non-trivial modules (the coder self-tests for trivial ones), feeding a bounded
  `code -> review+test -> code` loop; `odoo-code-review` gates test coverage and loops fixes back to
  `odoo-coding` / `odoo-test-writer`.
- **Module-aware `wave`**: Phase 0 computes the Odoo module DAG, auto-infers work-item `depends_on`
  from module dependencies, and warns on work-items that cross module boundaries.

### Changed

- `odoo-solution-architect` now surveys bidirectional impact, designs dynamic demo data, and checks
  the three platform design principles. The README gains a "Grounding contracts" table, and the
  ChatGPT / Gemini / Cursor instruction ports gain a self-contained Odoo Design Principles block.

### Fixed

- **`odoo-solution-architect` could ship designs that violated coding conventions and named
  non-existent fields / methods**, which every downstream coder then built on. It now reads the
  target version's `coding_guidelines/` like the coders do, and a HARD RULE separates EXISTING
  entities (must be OSM- or disk-verified, never named from memory) from PROPOSED additions (may be
  new, but follow naming conventions and are marked in the data-model / override tables).

## [3.7.0] - 2026-06-11

### Changed

- **Plugin renamed `odoo-semantic-skills` -> `odoo-ai-agents`** (display name "Odoo AI Agent Team"):
  end users should uninstall the old plugin and install the new one -
  `/plugin uninstall odoo-semantic-skills@viindoo-plugins` then
  `/plugin install odoo-ai-agents@viindoo-plugins`. The `odoo-semantic` MCP server and the
  `odoo-semantic-mcp` sibling plugin are **unchanged** - `mcp__odoo-semantic__*` tool references
  continue to work without modification.
- **Skill renamed `intake` -> `odoo-intake`**: the Odoo-specific front door now carries the
  standard `odoo-` prefix, consistent with every other Odoo skill. The bare `intake` namespace is
  reserved for a future domain-agnostic front door that may invoke `odoo-intake` when it detects
  Odoo intent. Update any `/intake` references to `/odoo-intake`.

## [3.6.0] - 2026-06-11

### Changed

- **wave Phase 2 rolling-window (Mode B) + fable escalation** (`odoo-semantic-skills`, #61):
  `wave` Phase 2 migrates from cap-3 Agent-tool batching to the Mode B model-weighted budget
  (BUDGET=8, per `skills/_shared/concurrency-guard.md`); cherry-pick stays a serialized depth-0
  critical section and a dependent WI starts only after its dependency is cherry-picked
  (`cherry_picked[dep]` gate, dependent worktrees created lazily). `odoo-debug` Phase 2 and the
  wave end-of-wave review gain a **fable** escalation tier (human-confirm + automatic opus
  fallback) - fable fires only after an inconclusive opus pass, or for a large wave review
  (changed lines > ~1500 or N >= 8 WIs).
  - Deferred: the YAML `model_tier: fable` enum is intentionally NOT added (no consumer needs it;
    CI rejects it loudly). When the first consumer appears, change three places in one commit:
    `generator/check_workflows.py`, `tests/test_workflow_format.py`, `workflows/_schema.md`.

### Fixed

- **Docs/skills synced to server fixes** (`odoo-semantic-skills`, #62): `lint_check` guidance now
  describes the V0.5 hybrid matcher (deterministic `[pattern]` on security-rule classes like
  sql-injection, heuristic `[fuzzy]` elsewhere) instead of the old "fuzzy V0 / can miss SQL
  injection" framing - while keeping "hint, not the gate" (`verify-backend.sh` + `/test_lint`
  remain authoritative). ORM-tool timeout prose is softened to reflect the server-side query
  bound (the client `"timeout": 90000` is now a defensive backstop, not the sole protection).
  `resolve_orm_chain` documents depth-first inherited-field resolution.

## [3.5.0] - 2026-06-10

### Added

- **Rolling-window codegen dispatch + per-work-item model tiers** (`odoo-semantic-skills`,
  closes #59): `odoo-coding` replaces the fixed "fire 3, wait, fire 3" Agent-tool batching
  with a canonical **Workflow-tool pipeline** (per-module backend->frontend stages, dependency
  promises instead of wave barriers, plain-JS weighted semaphore) plus an Agent-tool
  weighted-batch fallback when the Workflow tool is unavailable. Phase 0 gains a deterministic
  4-tier model table (haiku / sonnet / opus / **fable**, sonnet default) sourced from the
  design-doc effort tier or file/LOC/override heuristics; the gate table and `plan.md` now
  record an explicit `model` per work-item, and every dispatch passes `model` explicitly
  (agent frontmatter is a floor only, mirroring `odoo-debug`).
- **Concurrency-guard SSOT** (`skills/_shared/concurrency-guard.md`): the OOM fan-out rule
  now lives in one place - Mode A (legacy cap-3 batching) and Mode B (model-weighted budget:
  haiku=1, sonnet=2, opus=4, fable=8; budget 8). The five fan-out skills (`odoo-coding`,
  `odoo-debug`, `odoo-code-review`, `wave`, `workflow-chaining`) reference it instead of
  restating the numbers. Guarded by `tests/test_concurrency_guard_ssot.py`.
- **Claude Fable 5 integration** (`claude-fable-5`, tier above opus, 2x opus price):
  row 1 of the `odoo-coding` tier table (Custom-XL / >=3-module full-stack work, never a
  default, design-doc-first), and `odoo-solution-design` now passes an explicit
  `model: opus|fable` per dispatch (fable only for Custom-XL designs).
- **Coder agents** (`odoo-coder`, `odoo-frontend-coder`): documented the model
  floor/override convention and the shared-version invariant for concurrent runs;
  frontend-coder gains a Read-the-SKILL fallback for `odoo-frontend-design` when the Skill
  tool is unavailable under the Workflow harness.

## [3.4.1] - 2026-06-09

## [3.4.0] - 2026-06-08

### Added

- **Solution-design phase** (`odoo-semantic-skills`): new skill `odoo-solution-design` + agent
  `odoo-solution-architect` (opus, full read-only OSM surface) that turn a classified
  requirement / upgrade / migration / refactor goal into a gate-able Technical Design Document
  under `.odoo-ai/designs/` before any code is written, with a **human design-approval gate** that
  runs before Plan Mode (`design → approve → Plan Mode → code → review`). Wired into intake
  routing + the design-first rule, the `odoo-brl` / `odoo-data-migration` handoffs, and the
  `odoo-implement-feature` + `odoo-plan-upgrade` workflows.
- **`odoo-frontend-design`** skill: leaf, knowledge-only (no agent spawn) design-quality
  expertise that `odoo-solution-design` and `odoo-coding` load via the Skill tool, and the bar
  `odoo-ui-review` rates against.
- **`odoo-coding`** skill: the single full-stack coding front door (see Changed/Removed). Scopes
  the target module set, computes dependency order via OSM, and dispatches the backend then
  frontend coder agents in waves (≤3 concurrent) via the Agent tool, building to an approved
  design doc when present.

### Changed

- **`odoo-code-review` scaled to multi-module**: one module → single sonnet reviewer; many →
  per-module fan-out (≤3 concurrent) + an opus integration pass over the full dependency closure
  (forward via `module_inspect`, reverse via `impact_analysis`). Output persisted under
  `.odoo-ai/reviews/`.
- **`intake` slimmed via progressive disclosure** (793 → 551 lines): collision zones, Plan Mode
  schema, Phase P RUN-DAG, and maintainer notes moved to `skills/intake/references/`, loaded on
  demand; routing table + gating hot path kept inline.
- **Skill-tool invocation phrasing locked** to `` invoke skill `<name>` using skill tool ``.

### Removed

- **`odoo-backend-coding`** and **`odoo-frontend-coding`** skills — subsumed by the unified
  `odoo-coding` front door (the `odoo-coder` / `odoo-frontend-coder` agents are retained as its
  companions). Net skill count 39 → 40; agents 6 → 7.

## [3.3.0] - 2026-06-08

### Added

- **Per-version Odoo coding-guidelines SSOT** under
  `skills/_shared/coding_guidelines/<version>/` (14.0 through 19.0). Each version directory is
  self-contained (no cross-version deltas) and split into topic files
  (`module-structure`, `python`, `naming`, `model-ordering`, `xml`, `javascript`, `scss`) with a
  per-version `INDEX.md` and a root index. Content is extracted faithfully from the official
  `coding_guidelines.rst` of each branch.
- **Read-before-write wiring** in the engineering agents (`odoo-coder`, `odoo-code-reviewer`,
  `odoo-frontend-coder`, `odoo-backend-debugger`, `odoo-ui-debugger`) plus the three engineering
  SKILL.md briefs: after the Odoo version is resolved, the agent MUST read the matching
  `coding_guidelines/<version>/` files BEFORE writing code (correct on the first pass, not a
  post-hoc checklist). The reviewer cites the violated guideline by version file + section.

### Changed

- `hooks/enforce-grounding.sh` adds a non-blocking note when a subagent writes backend Python
  without reading a `coding_guidelines/<version>/` file (read-before-write reminder). Consistent
  with the plugin's "notes, not blocks, for non-provable gaps" philosophy.
- `generator/check_orchestration.py` now verifies the coding-guidelines root + per-version index
  files exist on disk (ref-target integrity).

## [3.2.0] - 2026-06-08

### Added

- **`odoo-debug` front-door skill** + two specialist agents (`odoo-backend-debugger`,
  `odoo-ui-debugger`). Routes a debugging request to the right specialist instead of forcing
  the caller to pick. This release also bumps the version so marketplace clients holding a
  cached `3.1.0` re-pull and actually receive the new skill/agents (they were invisible while
  the version string stayed put).

### Fixed

- `odoo-semantic-skills` manifest `description` (and the Codex `longDescription` + generated
  Gemini extension) said "28 skill personas" - a stale count. Corrected to "39 skills" to match
  the actual skill set and the README canon (39 skills + 4 agents + 9 commands).

## [3.1.0] - 2026-06-07

### Added

- **Plan-once, Drive-to-done orchestration.** `/intake` plans a multi-step job once, then
  `run-driver` (a depth-0 loop) drives it to `DONE` / `BLOCKED` / `NEEDS_CONTEXT` via a
  machine-readable Continuation Contract and an `.odoo-ai/run-<id>.json` blackboard. Adds an
  autonomy dial (`--auto` default / `--step` / `--plan`) and gate tiers L0/L1/L2 (L2 always
  stops for a human; the dial can never lower it), plus cross-workflow `on_complete`
  transitions. Three advisory hooks (`remind-delegate`, `drive-continuation`,
  `parse-continuation`) nudge but never hard-block the main agent.
- **7 new domain skills:** `odoo-test-writer`, `odoo-security-audit`, `odoo-data-migration`,
  `odoo-perf-audit`, `odoo-pricing-proposal`, `odoo-rfp-response`, `odoo-customer-health`.
- **`research-multiphase` workflow** - flexible-phase, multi-model-tier research dogfood.

### Changed

- **Per-plugin READMEs.** Split the shared root README into self-contained
  `odoo-semantic-skills` and `odoo-semantic-mcp` READMEs; the root README is now a monorepo
  landing page that links to both. Reworked the overview/commands mermaid diagrams for
  readability (vertical layout, fewer crossing edges).

## [3.0.0] - 2026-06-06

### Changed (BREAKING) — naming normalization across skills, agents, and commands

Names now encode **role** so an AI router (and a human) can tell the three layers apart even
when a name appears bare, without its `odoo-semantic-skills:` namespace: **skill** = a
capability noun (`-review`, `-analysis`, `-coding`), **agent** = an actor noun (`-er/-or`),
**command** = an imperative verb-object (`odoo-run-brl`). This removes three skill↔agent
name collisions and the agent-suffixed skills that were masquerading as executors. The full
convention is documented in `CONTRIBUTING.md` → "Naming convention: skill vs agent vs command".

**Migration (clean break, no aliases).** There is **no backward-compatibility shim** — invoking
an old name after updating to 3.0.0 fails with "not found"; use the new name (table below). To
defer migration, pin the plugin to `2.x`. The four **agent** names are unchanged. Skill
descriptions/trigger phrases are unchanged, so natural-language routing behaves identically —
only explicit slash commands and bare name references changed.

**Skills renamed (10):**

| Old | New |
|-----|-----|
| `odoo-coder` | `odoo-backend-coding` |
| `odoo-code-reviewer` | `odoo-code-review` |
| `odoo-ui-reviewer` | `odoo-ui-review` |
| `odoo-demo-recorder` | `odoo-demo-recording` |
| `odoo-objection-handler` | `odoo-objection-handling` |
| `odoo-override-finder` | `odoo-override-finding` |
| `odoo-discovery-summarize` | `odoo-discovery-summary` |
| `odoo-onboard` | `odoo-onboarding` |
| `odoo-ui-debug` | `odoo-ui-debugging` |
| `workflow-runner` | `workflow-chaining` |

**Commands renamed (9)** — `name:` now equals the filename (the invoked name); old `name:`
fields that never matched their file are corrected:

| Old command | New command |
|-------------|-------------|
| `/odoo-bid-respond` | `/odoo-respond-bid` |
| `/odoo-customer-followup-draft` | `/odoo-draft-followup` |
| `/odoo-discovery-quick` | `/odoo-summarize-discovery` |
| `/odoo-feature-positioning` | `/odoo-position-feature` |
| `/odoo-upgrade-plan-full` | `/odoo-plan-upgrade` |
| `/odoo-brl-run` | `/odoo-run-brl` |
| `/wave-run` | `/odoo-run-wave` |
| `/odoo-video-produce` | `/odoo-produce-video` |
| `/setup` | `/odoo-setup` |

The 4 agents (`odoo-coder`, `odoo-code-reviewer`, `odoo-ui-reviewer`, `odoo-frontend-coder`)
keep their names. SSOT `generator/skill_tool_deps.json`, the orchestration map, workflow files,
manifests, and docs were updated in lockstep; `make gen` output is regenerated.

## [2.8.0] - 2026-06-06

### Added

- **Local reproduction of the Odoo code-quality CI gate (issue #46) — multi-version aware, baked
  into the verify/test flow.** New `scripts/verify-backend.sh` is the backend sibling of
  `verify-frontend.sh`: it runs `pylint --load-plugins=pylint_odoo` on changed Python from an
  **isolated tools venv** (`$ODOO_AI_DIR/tools/pylint-<series>/`, never the instance venv), with
  pylint/astroid/pylint-odoo pinned per Odoo series in the extended
  `scripts/lib/odoo-python-matrix.json` (`lint` block; 16/17 → the verified-faithful
  pylint-odoo 8.0.22 · pylint 2.15.10 · astroid 2.13.5 combo, 18 → 9.x (pylint 3), 19 → 10.x
  (pylint 4, which pylint-odoo 10 hard-requires) — each pylint era-matched to its pylint-odoo major
  to avoid checker-plugin crashes). Always loads `pylint_odoo` so the
  `consider-merging-classes-inherited` pragma never reads as the `W0012` vanilla false signal, and
  **derives the enabled-code set from the deployment's own quality module** (`test_pylint`/`test_lint`)
  when present — no deployment-internal config is vendored. Graceful degradation (soft-warn, exit 0)
  when the toolchain/series/files are absent, with an opt-in `--provision` to build the pinned venv.
  Shipped fallback `scripts/odoo-pylintrc` (OCA defaults).
- **`/test_lint` mandate in the test-run SSOT.** `docs/reference/ODOO-TESTING.md` now documents the
  two-part gate (core `test_lint` + `pylint-odoo`) once; `odoo-qa-suite`, `odoo-deploy-checklist`,
  `wave`, `INSTANCE-LIFECYCLE.md` and `osm-first-contract.md` inherit it via their existing pointers.
  `odoo-coder` (Round 4) and `odoo-code-reviewer` now run `verify-backend.sh`; `odoo-deploy-checklist`
  gains a Domain-6 pre-push parity item. New reference: `docs/reference/odoo-code-quality.md`.
- **Enforcement substrate — `SubagentStop` grounding hook (`hooks/enforce-grounding.sh`).** Turns the
  previously advisory OSM-first contract into a checkable invariant: it reads the worker's own
  transcript (assistant-authored content only) and **blocks once** (loop-safe via `stop_hook_active`)
  when an artifact claims `grounded: osm` but made zero `mcp__odoo-semantic__*` calls, asking the
  agent to actually verify or relabel honestly. Self-gates to Odoo-shaped subagents. Two softer
  gaps raise a **non-blocking note** (never a block — a block there only manufactures unverifiable
  `grounded: local-source` labels and false-blocks legit pure-Python/standalone work): backend
  code written with OSM reachable but the ORM validators skipped; and the **silent-skipper** —
  backend `.py` written with zero OSM calls and no grounding label at all (previously slipped
  through unnoticed). The `odoo-coder` Round-4 "skipped with reason noted" free bypass was
  tightened to require the standalone `grounded: local-source` label. Hook behavior is locked by
  `tests/test_enforce_grounding.py` (block / both notes / self-gate / honest-label / loop-guard).
- **Brand-agnostic brand-fidelity mechanism (no brand vendored).** Optional, consumer-driven via a
  new `brand_tokens_source` key in `.odoo-ai/context.md` (a JSON `token -> color` map). New
  `scripts/lib/color_delta.py` (stdlib CIEDE2000); `verify-frontend.sh` Tier 4 WARNs on hardcoded
  SCSS hex within ΔE of a declared brand token, and `odoo-ui-reviewer` Step 4b ΔE-diffs
  `getComputedStyle(:root)` against the map at runtime. Documented as Section G of
  `skills/_shared/odoo-frontend-fidelity.md`; mirrors the gate's "derive from the consumer
  environment, vendor nothing" principle so the public plugin stays brand-neutral.

## [2.7.1] - 2026-06-05

### Fixed

- **`detect-intent.sh` routed structure-lookup questions to the vault instead of the OSM index** —
  the UserPromptSubmit hook only surfaced the index hint for code-gen intents (domain
  `engineering|upgrade|visual-UI`) and worded it as "before generating or editing Odoo code", so a
  composition/lookup question ("which modules / repos does profile X contain") got no pointer to the
  index and the agent fell back to the vault — even though `profile_inspect` answers it directly.
  Added an `_is_lookup` intent probe (EN `module/repo/profile/version/inventory/composition` + VI
  `gồm / có gì / module nào / repo nào / những gì / có bao nhiêu`) that emits an `[OSM-lookup]` hint
  naming `profile_inspect` / `describe_module` / `model_inspect`, fired on Odoo/Viindoo anchor +
  lookup intent **independent of `_domain`** (so a general-domain Viindoo question still routes to
  the index). The hint is an in-context pointer that survives ToolSearch deferral of those tools.

## [2.7.0] - 2026-06-05

### Added

- **OSM server 0.13.1 surface sync (24 → 25 tools)** — mirror the new `profile_inspect` tool
  (`method=summary|repos|modules`: profile inheritance chain + repos + module inventory/count,
  ADR-0028) into `generator/server-surface.json` and wire it into the skills that answer
  "what's in this profile" questions: `odoo-onboard` (records module inventory into
  `.odoo-ai/context.md`), `odoo-customization-inventory`, `odoo-addon-diff`, `odoo-brl`,
  `odoo-risk-overview`, `odoo-competitive-brief`, `odoo-discovery-summarize`, `odoo-campaign-plan`.
- **Live version-gate (closes #40 Finding 2)** — `check_deps.py` now enforces the previously-dead
  `server_version_required` / per-skill `min_server_version` fields: each floor must cover the
  newest tool the skill/agent uses and stay ≤ the mirrored server version (semver compare).
- **OSM-maximization pass across skills + agents** — wired, at each phase, the OSM tool/resource
  that removes a concrete guessing step: `impact_analysis` (BRL Extension-M/L blast radius);
  `set_active_version` pins (ui-debug / visual-regression / demo-recorder / ui-reviewer — stop
  `odoo_version='auto'` resolving to latest-indexed); `module_inspect` scope numbers
  (feature-highlights / capability-proof / objection-handler / gap-analysis); `find_deprecated_usage`
  + `module_inspect(dependencies)` (customization-inventory upgrade-risk); `lookup_core_api` /
  `find_examples` / `api_version_diff` (override-finder); `set_active_profile` scoping
  (deprecation-audit); `cli_help` (deploy-checklist / qa-suite); `find_examples` (version-diff);
  agent tools `find_override_point` / `module_inspect` (coder), `entity_lookup` (frontend-coder),
  `find_examples` / `api_version_diff` / `find_style_override` / `resolve_stylesheet` (code-reviewer),
  `set_active_version` / `api_version_diff` (ui-reviewer). Added `odoo://` resource shortcuts where
  the entity id is already known.

### Fixed

- **#41 — skill examples pinned non-existent profile names** — replaced `viindoo-internal` (hyphen)
  and bare `odoo` with versioned names (`viindoo_internal_17`, `odoo_17`) across odoo-brl,
  odoo-gap-analysis, odoo-onboard, odoo-customization-inventory, odoo-addon-diff, evals, schema,
  workflow-harness, context-bootstrap; preserved the "read from `.odoo-ai/context.md` /
  `list_available_profiles`, never hard-code" guidance.
- **Tool descriptions resynced to 0.13.x behaviour** — `find_examples` documents the lexical
  fallback when the embedder is down (#264); `model_inspect` documents the `extenders` method +
  the real page caps (#262).

### Changed

- **Provenance stamp 0.11.1 → 0.13.1 (closes #40)** — `server_version` in the surface SSOT plus
  every hand-maintained "24 tools / v0.11.1" label (README, ROADMAP, setup.md, dev.md, snippet
  intros, MANUAL skill footers); generated surfaces regenerated via `make gen`.

## [2.6.0] - 2026-06-05

### Added

- **Agent-first grounding SSOT (PR #42)** — two new snippets the skills/agents reference by
  path: `snippets/disk-fallback-protocol.md` (three-tier grounding: OSM index → disk self-serve
  via Read/Grep/Bash/WebFetch → training-memory flagged `ungrounded`) and
  `snippets/context-bootstrap.md` (a mandatory Round 0 that reads `.odoo-ai/context.md` before
  asking the caller for version/profile/module list).
- **`odoo-frontend-coder` agent (PR #43)** — frontend coding is now an agent+skill bundle
  (mirrors `odoo-coder` / `odoo-code-reviewer`): a slim routing skill plus an isolated executor
  agent with a restricted tool allowlist (incl. `resolve_stylesheet` / `find_style_override`),
  so version-gating + multi-round MCP runs out of the main agent's context.

### Changed

- **Standalone-first fallback: paste-only → disk-grounded (PR #42)** — when OSM is unreachable
  a skill now reads the source itself (`find`/`grep`/`Read`, `WebFetch` upstream) instead of
  asking a human to paste code/fields/manifests; copy-pasteable output is the last resort
  (repo genuinely inaccessible). **This reverses the [2.5.0] decision to keep the fallback
  paste-only.** Visual skills return `BLOCKED(...)` when a browser/instance is unreachable
  rather than soliciting screenshots. `hooks/detect-intent.sh` recommends disk-grounded
  fallback accordingly.
- **Portability (PR #42)** — sales/visual flows no longer depend on the non-official live Odoo
  ERP MCP (`mcp__odoo__*`) or the claude.ai Gmail MCP; deal/CRM/email data comes from the
  invocation context and `.odoo-ai/context.md`, instance URL from `.odoo-ai/instances.toml`.
  Any live ERP/email integration is an optional bonus, never assumed.
- **Code skills self-author (PR #42)** — `odoo-coder` / `odoo-code-reviewer` /
  `odoo-frontend-coder` write and review code natively (boilerplate from `find_examples`
  templates, complex logic reasoned step by step, inline self-review) instead of delegating.
- **Model-tier (PR #42)** — `feature-positioning.workflow.yaml` feature-check / addon-diff
  `haiku` → `sonnet` (OSM synthesis, not simple lookup); `haiku` definition tightened in
  `_schema.md` / `workflow-harness.md` (never for write/synthesis phases). The
  `set_active_profile` example reads `viindoo_profile` from `.odoo-ai/context.md` instead of
  hard-coding `viindoo-internal`.
- **Frontend bundle + version portability (PR #43)** — the `odoo-frontend-coder` skill is
  renamed `odoo-frontend-coding` (the agent keeps the `odoo-frontend-coder` name); the
  wave / nesting-guard guidance is corrected so a depth-2 leaf worker never invokes a
  depth0-only bundle (it writes/reviews directly via OSM tools); hard-pinned `v8–v19` version
  ranges that only meant "all supported" are replaced with open phrasing ("any/all supported
  version", "v8+") while real era boundaries are kept; the README no longer tracks the plugin
  version.

### Removed

- **ollama-delegate (PR #42)** — removed all `mcp__ollama-delegate__*` delegation from the
  plugin and the `ollama_tools` field from every `generator/skill_tool_deps.json` entry (plus
  the `SKILL_OLLAMA_TOOLS` load and the "Ollama-delegate tools" render block in
  `generator/gen_surface.py`). The running agent generates/reviews code itself.

### Fixed

- **Session-pin scope wording (#253, follow-up to server #251/#252)** — corrected the
  `set_active_version` / `set_active_profile` sticky-context description from "per API key"
  to **per live MCP session** (single api-key/`_nosession` fallback for stdio/header-less,
  24h idle TTL, resets on server restart). Fixed at the SSOT
  (`generator/server-surface.json` tool description + `generator/gen_surface.py` legend) and
  regenerated via `make gen` (propagates to `mcp-tool-routing.md`, 12 SKILL.md, 3 snippets),
  plus the manual prose outside the generator (`docs/setup.md`, `docs/personas/dev.md`,
  `odoo-deploy-checklist`/`odoo-frontend-coder` SKILL.md, snippet intros, and the
  `odoo-brl` state-file `schema.md` re-bootstrap note). Prose-only — no tool-surface change
  (tool count stays 24), no client code change.

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
