# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [3.32.0] - 2026-06-28

### Added

- New agent `odoo-gap-analyzer`: the leaf worker that runs heavy gap analysis for one requirement cluster in its own context (keeping the main / team-leader context clean). OSM-first -> local-checkout 2-tier grounding (training-only grounding banned; rows that cannot be grounded are marked `grounded:unknown` / `BLOCKED`), and it writes a machine-readable findings file per cluster.
- SSOT for complexity -> model-tier selection added to `skills/_shared/concurrency-guard.md` (the haiku / sonnet / opus / fable principle); the gap-analysis agent, skill, and callers reference it instead of hardcoding a model.

### Changed

- `odoo-gap-analysis` upgraded from an inline leaf into a spawner-agent orchestrator: it clusters requirements by functional area, fans out `odoo-gap-analyzer` workers (rolling-window, model chosen per cluster complexity), synthesizes and de-duplicates findings from disk, and emits a locked file-handoff artifact set under `.odoo-ai/gap-analysis/<slug>-<date>/` (`gap-report.md`, `gap-matrix.jsonl`, `gap-continuation-contract.json`).
- Wired the gap-analysis file-handoff into its downstream consumers: `odoo-solution-design` and `odoo-solution-architect` (new `GAP_MATRIX` input port), `odoo-pricing-proposal` and `odoo-rfp-response` (effort read from `gap-matrix.jsonl`), the `odoo-respond-bid` and `odoo-implement-feature` workflows (explicit file-path chaining), `odoo-brl` (seed / cross-check from `gap-matrix`), and `odoo-intake` (scope-first routing: gap before design).

## [3.31.2] - 2026-06-28

### Changed

- `git-toolkit` single-delegate model assignment: the three leaf agents (`git-surveyor`, `git-operator`, `github-operator`) now default to `model: sonnet` instead of `inherit`, so a single-delegate spawn no longer inherits the caller's model (often opus) for trivial git/github ops. New SSOT `snippets/git-model-tiers.md` maps each single-delegate op-class to a tier (haiku for mechanical reads, sonnet default, opus for destructive rewrites); the `git-ops` SINGLE-DELEGATE route now passes the Agent-tool `model` param + a `DISPATCH MODEL:` brief line and no longer relies on `inherit`. Inert inline model tokens stripped from `git-surveyor`'s phase descriptions (an agent's own model is fixed at spawn; body prose cannot set it). (`git-toolkit` 0.1.2 -> 0.2.0.)
- `git-toolkit` `op=squash-push`: the squash-to-one + tree-identity + force-with-lease recipe is promoted into `snippets/git-squash-push.md` (composing the `git-safety-contract` S1/S6/S2 primitives), and `wave` now delegates to that named op instead of re-spelling the primitives in `wave/reference/wave-templates.md` - removing an SSOT duplication.

## [3.31.1] - 2026-06-28

### Fixed

- `odoo-git-rebase` orchestration gaps (#115): P8 conflict resolution and review now dispatch the `odoo-coding` / `odoo-code-review` skills via the Skill tool instead of raw agents; reference the new `git-toolkit` S10 `rebase --continue` continue-driver; slug sanitization pinned; `rerere.autoupdate` set; a conflict-type taxonomy added; P8b symbol-survival + collection gate delegated (Explore / git-surveyor) with an explicit PASS/FAIL verdict; explicit pyflakes import-resolvability gate; `installable=False` guard; a shared `INSTANCE_HANDLE` (new `snippets/instance-handle-contract.md`) provisioned once via `odoo-instance` and forwarded downstream; run-tests verdict contract.
- `git-toolkit` conflict continue-driver (#115): new S10 step in `git-safety-contract` - never `--skip` on "no unmerged files" (only on an empty `--continue` patch); per-path resolution (UD/DD -> `git rm`, static add/add -> non-empty side, marker -> coder, rerere-resolved -> `git add`); `rerere.autoupdate` enabled. `git-operator` and the `conflict-resolution` reference cite S10 inline. (`git-toolkit` 0.1.1 -> 0.1.2.)
- Capability/gap pipeline guardrails (#121, client-side only): module-slug -> provider inference forbidden; per-claim provenance tags `[OSM-index]` / `[inferred]` with wording downgrade; absence-in-index transparency; new `snippets/ssot-extraction-contract.md` (verbatim extraction for SSOT source docs); recon-no-file-write guard in `odoo-intake`. Live-MCP cross-check intentionally out of scope (kept per PR #42).

## [3.31.0] - 2026-06-28

### Added

- `odoo-solution-design`: master-child design decomposition for large multi-module scope. `odoo-solution-architect` now supports four modes (`single` / `master` / `child` / `consistency`); `master` mode produces one master TDD (cross-module contracts, shared-symbol ownership, DAG layer order) then N child TDDs in `dag_layer` order under `.odoo-ai/designs/<master-slug>/`; machine-readable `index.yaml` is the routing SSOT for downstream consumers. Two-level design handoff (`DESIGN_DOC` = child spec, `MASTER_DESIGN_DOC` = hard-constraint master TDD) wired through `odoo-coding`, `odoo-code-review`, `odoo-debug`, and `wave`. Contract SSOT: `snippets/master-child-design-contract.md`.
- `odoo-frontend-coder`: TDD-conformance gap fixed - agent now reads and enforces `MASTER_DESIGN_DOC` constraints in addition to the child `DESIGN_DOC` spec.

## [3.30.2] - 2026-06-28

### Changed

- Semantic-preserving compression of plugin runtime docs (agents / skills / commands / references /
  snippets / docs) across `odoo-ai-agents` and `git-toolkit` - terse prose, within-file dedup, and
  inline-copy -> existing-pointer trims. No `name`/`description` frontmatter and no behavior changed
  (verified: `make validate` + `make test` 946 passed, frontmatter byte-diff vs `master` empty,
  `make gen` idempotent). Per-plugin `COMPRESSION-REPORT.md` added. Realized ~2.6k token / ~0.76%
  reduction - the repo was already heavily SSOT-factored, so the safe headroom was small.

## [3.30.1] - 2026-06-27

### Added

- Forward-port conventions C1/C2/C3, folded into the existing merge-window SSOT `snippets/fp-merge-absorption.md` (no new snippet) (issue #126). **C1** - a forward-port never invents a `__manifest__.py` `version` bump; on conflict the target file's version wins. **C2** - a forwarded `migrations/<src-series>.a.b.c/` dir is retargeted to the target series (FULL form); the manifest is bumped only when the source version `<=` the target's current manifest (so the migration fires on already-deployed target DBs), grounded in Odoo `adapt_version`/`migration.py` (verified v17+v18); a legacy source-origin-only data fix keeps the source-series dir. **C3** - a bug pre-existing at the source series is carried faithfully forward and surfaced upstream (source-series issue), not inline-fixed; security/safety fixes go on the destination immediately. C1 and C2 are explicitly de-conflated, and a module made `installable` by a prior-series upgrade then forward-ported is re-set to `installable:False` when the target clean-tip was not yet upgraded. Same-series manifest-conflict analogue added to `odoo-git-rebase`. RED-before-green invariants in `tests/test_forward_port_hardening.py`.

### Changed

- `odoo-modules-upgrade` Rule A is now unconditional: a code-level upgrade never bumps the manifest `version`, never writes migration scripts (a genuine data-bearing case routes to `odoo-data-migration`), and restores `auto_install`/`application` only when an explicit `# TODO: Uncomment when upgrading` manifest breadcrumb (left by forward-port) directs - wiring forward-port and upgrade together.
- The backend code-quality gate is now Odoo's own lint test module - `test_lint` (v14+, renamed from `test_pylint` at v13) plus `test_pylint` on v16+ Viindoo profiles - run via `--test-tags` on an instance, instead of the OCA `pylint-odoo` package. `docs/reference/ODOO-TESTING.md` is the lint SSOT. Note: this requires a running instance (matching what Runbot runs); the previous fast no-DB static gate is removed.
- Consolidated `snippets/module-rename.md` into `snippets/upg-conventions.md` (net -1 snippet, no new files); its consumers repointed.

### Removed

- OCA support entirely, across skills/agents/snippets/scripts/docs - including `scripts/verify-backend.sh`, `scripts/odoo-pylintrc`, the per-series `lint` pins in `scripts/lib/odoo-python-matrix.json`, the OCA addons-path role in `scripts/lib/discover_odoo.sh`, and the `"OCA style violations"` `lint_check` routing keyword. Upgrade/manifest rules collapse to single Viindoo/Odoo conventions.

### Fixed

- The forward-port manifest version-bump gate no longer fires merely because a diff touches `migrations/` - the root-cause conflation of C1 (no bump) with C2 (migration-dir retarget) is removed from both `snippets/fp-installable-false.md` and `skills/odoo-forward-port/SKILL.md` (issue #126).

## [3.30.0] - 2026-06-27

### Added

- `git-toolkit` delegation: all git/GitHub operations in `odoo-ai-agents` now delegate to `git-toolkit` agents (`git-surveyor`, `git-operator`, `github-operator`, `git-pipeline-lead`) instead of running inline. New caller SSOT `plugins/odoo-ai-agents/snippets/git-delegation.md` documents the boundary and carve-outs; `git-toolkit` declared as an `odoo-ai-agents` dependency in `plugin.json`; boundary enforced by the new `tests/test_git_delegation_boundary.py`.

### Changed

- The four heavy pipelines (`odoo-git-rebase`, `odoo-forward-port`, `odoo-modules-upgrade`, `wave`), `odoo-code-review`, and the read-only leaf agents (`odoo-diff-comparator`, `odoo-intent-extractor`, `odoo-installable-prober`, `odoo-review-scoper`) no longer execute git or `gh` CLI calls inline; they cold-spawn the appropriate `git-toolkit` agent. Bounded reads (e.g. `git log`, `git diff`) and a subagent's own-worktree `git add`/`commit`/`stash` are explicitly permitted to stay inline.

### Fixed

- `odoo-modules-upgrade` upgrade robustness (review R3 findings M2/M3/L1/L2/L3): RECONCILE new-mechanism detection now runs `suggest_pattern`/`find_examples` unconditionally for every KEEP feature so a new parallel core mechanism (new model/mixin/action on the same domain) is caught even when the feature's own API endpoint shows no `new` items; crash-safe checkpoint resume now uses explicit per-phase skip thresholds (P2 skips {absorbed..done}, P4 skips {adapted..done}, P4b skips {reviewed..done}, P5 skips {installed,done}) preventing a resume from overwriting already-adapted integration worktree work; commit consolidation base is now recorded from the git-operator converge step SHA instead of being re-discovered from an interleaved log; design-trigger condition list removed from `upg-phase-detail.md` P2b (SKILL.md § P2b is the SSOT; duplicate no longer drifts); DCO sign-off (`git commit -s`) made mandatory in the P4 coder brief for KEEP/REWRITE paths.
- `git-toolkit` safety contract gains S9 (worktree-always / principal-checkout-lock, mandatory for all delegated ops); `git-operator` now emits a `BLOCKED-CONFLICT` status with `conflicted_files` and `stopped_commit` fields to support the stateless conflict-resume loop at the orchestrator level.
- Hardcoded fork and upstream identifiers removed from `odoo-git-rebase`, `odoo-forward-port`, and `odoo-modules-upgrade` agent prose; these are now resolved at runtime via `git remote get-url origin`.

## [3.29.0] - 2026-06-26

### Added

- Context-Handoff Protocol (CHP), an opt-in 3-tier agent-dispatch optimization (issue #98). New SSOT `snippets/context-handoff-protocol.md`: Tier A `SendMessage`-resume of a previously-spawned worker (gated on a runtime capability probe: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `SendMessage` tool present, target addressable, orchestrator is the team lead), Tier B `subagent_type: "fork"` for read-heavy fan-outs, and Tier C fresh-spawn + worklog as the always-correct SSOT fallback. The snippet codifies the fallback trigger matrix (silent/automatic/degraded-but-correct), async park-and-be-resumed semantics, the lead-is-address-authority contract, "no nested teams = roster only", a confidentiality guard (never frame a handoff payload as a "secret"), the worklog-as-SSOT invariant, and an invariant/cross-check-at-aggregation rule. Wired into `odoo-coding` + `odoo-code-review` (coder<->reviewer loop, Tier A), `wave` (per-WI Tier A with a cd-on-resume hard rule), `odoo-forward-port` (P1 intent-extract fork + P8/P9 adapt Tier A), `odoo-deep-survey` and `odoo-brl` (read fan-out fork). New generator field `handoff: send-message | fork | fresh` in `generator/skill_tool_deps.json` (absent = `fresh`), a `[chp-tier-c-fallback]` lint in `generator/check_orchestration.py`, a `handoff` column in the generated `docs/reference/ORCHESTRATION-MAP.md`, and `tests/test_chp_hardening.py` (#98).

### Changed

- Removed obsolete "no Skill tool / no subagent / NL-dispatch only" prohibitions now that Claude Code supports multi-level agent nesting (depth cap 5; interior agents can spawn subagents; "no nested teams" = roster only) and self-manages resources (concurrency cap, rolling windows, queueing). Skills, agents, and commands may now dispatch via the Skill tool: `odoo-qa-suite`, `odoo-debug` (relabeled Orchestrator), `odoo-support-triage`, `workflow-chaining` (phase dispatch incl. spawner skills), the `odoo-coder` / `odoo-frontend-coder` / `odoo-solution-architect` agents (blanket Skill-tool bans dropped; execution-pipeline carve-outs kept as scope correctness, not nesting fear), the `odoo-run-brl` / `odoo-run-wave` / `odoo-summarize-discovery` commands, and `docs/reference/workflow-harness.md` (fork-worker hard-rule narrowed to spawner-skills-only, internal inconsistency resolved). Genuine non-nesting/non-resource carve-outs preserved: `wave` cherry-pick critical-section + principal-branch lock + human-confirm-merge, `odoo-brl` sequential-outer ordering for checkpoint/resume correctness, `odoo-intake` fresh-context run-driver dispatch, and browser-main-context constraints. `README.md` and `workflow-harness.md` updated to document the CHP model and the corrected nesting reality (#98).

## [3.28.0] - 2026-06-26

### Added

- `odoo-modules-upgrade` v8-v19 hardening (issue #117). New SSOT `snippets/odoo-version-pivots.md` - a version-pivot table for ORM/view/manifest/CLI/JS facts across v8-v19, verified against the on-disk codebase, that every version-specific statement cross-references instead of hardcoding a single source->target pair. New `snippets/upg-conventions.md` (profile-gated Viindoo conventions: no manifest `version` bump on code-level upgrade, no-data rename via `old_technical_name`, always-invisible view field XML comment from v18, `hr.employee` groups guard), `snippets/stored-write-survival.md` (`readonly=False` is not proof a written value survives a `@api.depends` recompute), and `references/runbot-parity-checklist.md` (version-keyed reproduction of the Runbot lint/test gates). New pipeline phase **P1d Transitive Symbol Survey** (grounds external-dependency symbols down to base/ORM/tools at the target version, emitting `blockers[]` consumed by the coder); new **RECONCILE** verdict (target-core data-divergence OR new-feature wire-in, routed to design); gated-on **P5.7** i18n reconcile phase; per-module commit consolidation as a supported capability. Pipeline-robustness gaps closed (worktree/base/`cluster_slug` definitions, MIXED routing, `installable:False->True` in the coder brief, demo version-range). Wired into `odoo-diff-comparator`, `odoo-solution-architect`, `odoo-code-reviewer`, `odoo-coder`, `odoo-instance-ops`, `odoo-ui-reviewer`, `odoo-doc-illustrator`, and `odoo-deprecation-audit` (#117).
- `snippets/python-naming-conventions.md` (issue #120): Rule A (no `l`/`O`/`i` single-letter variable names - pylint `C0104` blocks CI) applies to all distributions; Rule B (no arbitrary abbreviations) and Rule C (iterate `self` as `for r in self`, not `rec`) are Viindoo-profile-gated. Routed via the per-version INDEX "By task" Naming row + the snippets catalog, and wired with thin pointers into the coder/frontend-coder/reviewer/backend-debugger/ui-debugger agents and the `odoo-qa-suite` / `odoo-test-writing` skills (#120).
- `snippets/test-protection-contract.md` (issue #117 follow-on): a single source of truth for "what tests guard what" - for every model/view/method a change touches, use OSM to enumerate the protecting tests in three tiers (own-module, base/dependency, framework/lint gates `base.TestInvisibleField` / `hr.TestSelfAccessProfile` / `test_pylint` / `test_lint`); tiers (i)+(ii) are MUST-NOT-BREAK. `odoo-coder` and `odoo-frontend-coder` now run this pre-flight UNCONDITIONALLY (not dependent on a survey having run), and `odoo-deep-survey` cross-references the same snippet so survey and coder share one methodology (#117).

### Changed

- SSOT consolidation of the coding guidelines (issue #117 follow-on). New `snippets/orm-performance.md` (a stored compute aggregating a high-volume relation MUST use one grouped `_read_group`, never per-record `mapped()`), now loaded by the general `odoo-coder` together with `snippets/stored-write-survival.md` and the `odoo-version-pivots.md` pivot table - the general coder previously loaded none of them; `odoo-code-reviewer` and `odoo-solution-architect` now cross-reference the perf SSOT instead of restating it. The CORE always-invisible-field XML-comment rule (v18+) is surfaced for all distributions in the coding-guidelines catalog (previously reachable only via the Viindoo-profile-gated path), and `odoo-i18n` documents the `.po`/`.pot` `#. module:` comment requirement. Per-version coding-guidelines topic files (verbatim upstream RST mirrors) are left untouched (#117).
- Coding-guidelines reorganised so the INDEX is a true router (issue #117 follow-on). The root `coding_guidelines/INDEX.md` is now a pure catalog/router (rule content evicted to snippets); each per-version `<v>/INDEX.md` "By task" table maps a task to its topic file(s) + the relevant snippets + the `odoo-version-pivots.md` section, and the code/debug/review agents (`odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, `odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-solution-architect`) plus their skills now MUST read the version INDEX first and read ONLY the By-task-mapped files (token-aware; `read-before-write-contract.md` is the SSOT for the mandate). Two rules previously mis-gated as Viindoo - the always-invisible-field XML comment (v18+) and the `hr.employee` field-groups requirement (v16+) - are reclassified as Odoo CORE (test-enforced) and made reachable for all profiles; only the short-form/no-bump version policy and `old_technical_name` remain Viindoo-gated. New `snippets/xml-view-conventions.md` (#117).
- `odoo-deep-survey` digs to the root instead of stopping at the directly-touched modules (issue #117 follow-on): it walks the dependency closure from the nearest modules down to `base` (phased, one layer per wave), maps the tests that protect the surveyed scope (own-module + base/dependency tests + the framework-validation/lint gates `base.TestInvisibleField` / `hr.TestSelfAccessProfile` / `test_pylint` / `test_lint`, flagged as not-OSM-indexed), and surfaces prior art (`find_examples` / `suggest_pattern`) so downstream design/code agents reuse instead of reinventing. Adds entry-point, data-flow, layer, side-effect and tech-debt lenses, reinforces OSM-first grounding, and keeps `SKILL.md` lean (detail in `references/survey-lenses.md` + `references/synthesis-schema.md`) (#117).
- `odoo-code-review` now auto-runs UI review for view changes and partitions large reviews (issue #117 follow-on). `odoo-review-scoper` classifies each module's changed files and returns a per-module `needs_ui_review` flag (any view-layer change, or a Python field/method the OSM confirms is view-bound) plus the affected screens; the per-module reviewer runs `UI_REVIEW=delegated` (non-rendered + view-source correctness only) and a new Phase A.5 dispatches `odoo-ui-reviewer` on the affected screens when an instance is reachable (else DONE_WITH_CONCERNS, never a hard block) - on both the single- and multi-module paths. When the change is too large for one opus, synthesis partitions by business domain (one opus per domain -> `domain-<d>.md`, then a final cross-domain opus -> `_synthesis.md`). Every phase persists its artifact under `.odoo-ai/reviews/<slug>-<date>/` (#117).

### Fixed

- `scripts/verify-backend.sh` lint gate parity: prepend `--disable=all` so only the derived Viindoo whitelist runs (no OCA-default broad enables), strip `#`-commented lines before deriving enabled codes, downgrade `unknown-option-value` (W0012) version drift to a non-blocking WARN, and fail-closed (loud WARN, never a silent green) when the whitelist cannot be derived; per-series `pylint_odoo` pins in `scripts/lib/odoo-python-matrix.json`; protected by `tests/test_verify_backend_gate.py` (red-before-green). The P5 install gate now runs framework validation with demo data ON (Runbot parity), and `odoo-deprecation-audit` scans at the TARGET version against the module's own source (with `era-reference.md` rewritten as a v8-v19 range). A performance lens (a stored compute aggregating a relation on a high-volume model must use a grouped `_read_group`) and verification discipline (no APPROVE-via-simulation; pre-write value / recompute claims require runtime evidence) were added to `odoo-code-reviewer` and `odoo-solution-architect`; `odoo-instance-ops` demo-flag guidance corrected to the v8-v18 vs v19 split (#117).
- Coder model-tier no longer leaves large work on sonnet: the `odoo-coding` §5 tier table now escalates a single-stack work-item to opus on size/scope (net-new-or-changed >=~200 LOC, >=~5 files, or a large / high-blast-radius target module), the sonnet catch-all is capped below those thresholds, and `wave` resolves each work-item's model tier via that table instead of letting the leaf agent fall back to its default sonnet (#117).
- Mandatory guideline-read enforcement, to stop agents shipping stale version constructs (e.g. `<tree>` on v18 where the guideline says `<list>`) when they skip the guidelines or lose them to context compaction. `read-before-write-contract.md` (SSOT) and every code/debug/review/architect agent now carry a unified `MANDATORY HARD RULE` (no line of a file type written before its By-task-mapped guideline + pivot section is read), a just-in-time pivot-row re-read immediately before writing each file type, and a `VERSION RULES APPLIED` sticky-note the coder emits before code and the reviewer verifies (mismatch = HIGH) so the rules survive compaction; coder/frontend-coder/reviewer gain a hard `MANDATORY READ GATE` checklist item (locked in by `tests/test_execute_agent_hardening.py`). Stale duplicated version-facts in agent/reference prose (`@odoo-module` "v16-v17", `@api.multi` "v13/v14", the tree/list history note, frozen era tables) are purged in favour of `odoo-version-pivots.md` pointers (#117).

## [3.27.0] - 2026-06-25

### Added

- Added `snippets/test-expected-log-contract.md` (SSOT): the expected-log contract for tests that legitimately emit a server/console WARNING/ERROR - an `assertLogs`-vs-`mute_logger` decision rule plus a 3-layer matrix (Python log / SQL constraint / JS-OWL), with the JS framework era split (v17 QUnit vs v18+ Hoot) resolved at runtime via `js_test_inspect` rather than hardcoded. Wired as a pointer (rule body stays in the snippet) into the coder/reviewer/debugger triad with distinct duties - coder wraps, reviewer flags a missing wrapper as HIGH, debugger treats a matching WARNING as expected noise: `odoo-test-writing`, `odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, `odoo-debug`, `odoo-backend-debugger`, and `docs/reference/ODOO-TESTING.md` (#114).

### Fixed

- Fixed `scripts/verify-frontend.sh` reporting a false-green `PASS` for the JS lint gate. It now resolves `eslint`/`prettier` from the repo-pinned `node_modules/.bin` (git-worktree aware, with an `npx --no-install` last resort; global `command -v` resolution removed), runs the real Runbot oracle `eslint --no-eslintrc -c _eslintrc.json --resolve-plugins-relative-to MAIN_ROOT` (replacing standalone `prettier --check`) with a prettier version-pin pre-check, and emits a tri-state result - `PASS` (exit 0) / `FAIL` (exit 1) / `CANNOT-VERIFY` (exit 2). An unresolved toolchain or a v14 no-gate layout now emits `CANNOT-VERIFY` (a soft-stop the agent must not treat as a pass), never `PASS`. Consumer agents/skills/docs updated to honor `CANNOT-VERIFY` = not-clean (#112).

## [3.26.0] - 2026-06-25

### Added

- Added greenfield `__manifest__.py` authoring guidance (scaffold-first, preserve scaffold commented placeholders, short non-series-prefixed `version`) as a dedicated snippet (`new-module-manifest.md`) wired into `odoo-coder` (directive + checklist) and `odoo-code-reviewer` (MED convention finding); `odoo-frontend-coder` references it at the manifest-wiring step; `odoo-coding` skill brief updated.
- Added profile-gated module-rename guidance (`snippets/module-rename.md`): under a Viindoo Standard/Internal profile (OSM-detected), a renamed module's manifest must carry `old_technical_name` (Viindoo-internal tooling key, ignored by Odoo core loader, additive to OpenUpgrade DB-level rename); wired into `odoo-coder` (directive + checklist item) and `odoo-code-reviewer` (MED finding, explicitly non-applicable outside Viindoo distributions).

## [3.24.0] - 2026-06-22

## [3.23.0] - 2026-06-22

### Added

- **Universal Work Ethos auto-loaded into every agent.** A new `ODOO-AI-ETHOS.md` at the plugin
  root holds 11 cross-cutting work principles (completeness, root-cause analysis, SSOT,
  behavior-protecting tests, ASCII-hyphen output, and so on). A SessionStart hook
  (`ensure-ethos-import.sh`) idempotently writes a sentinel-bounded absolute `@import` of it into
  the user's global `~/.claude/CLAUDE.md`, so the principles load into the main agent and every
  custom sub-agent (built-in Plan/Explore agents skip CLAUDE.md by design). The hook is
  corruption-safe and self-healing, creates CLAUDE.md if missing, and preserves a symlinked
  CLAUDE.md. Opt out with `ODOO_AI_NO_ETHOS_IMPORT=1`; the principles then apply across all your
  Claude Code projects, not only Odoo work.

## [3.22.0] - 2026-06-22

### Fixed

- **`/odoo-setup` verifies Odoo by running `odoo-bin --version`, not `python -c "import odoo"`.**
  A source-only Odoo checkout is never pip-installed, so the old bare-import gate
  (`45-venv.sh`, `50-instance-spinup.sh`) false-negatived a healthy venv and refused to record
  the instance's `python` field; it also misread Odoo 19's namespace package as broken. The gate
  now runs the real entrypoint - which self-inserts its repo on `sys.path` - and fails loud when
  the core repo is absent, instead of editable-installing Odoo. (#104)
- **`/odoo-setup` AI-4 venv probe is v8-v19 safe and principle-based.** Series detection now runs
  `odoo-bin --version` / `import odoo.release` instead of inspecting `import odoo` /
  `site-packages/odoo` (a false-negative on namespace-package Odoo 19), and escalates an
  `unknown` result to the user instead of guessing. (#104)

### Added

- **Per-profile venv and instance recording.** `[[instance]]` blocks gain optional `profile` /
  `instance_key`; `45-venv.sh create-venv --profile <name>` builds an isolated
  `venvs/<series>-<profile>` venv and verifies every repo in the profile is present before
  recording the interpreter. `40-instance-profile.sh`, `50-instance-spinup.sh`,
  `instances_io.py`, and `allocator.py` (`--profile`) carry the profile through, so two profiles
  of the same series no longer collide on venv path, DB name, or instance identity. (#104)

## [3.21.0] - 2026-06-21

### Changed

- feat(odoo-ai-agents): forward-port pipeline reorder - intent-extract + 4-outcome classify + a conditional design step now run BEFORE the plan gate, so the plan is built from understood intent (not bucket guesses). New order: P0 recon (no stop) -> P1 intent extract -> P2 classify + installable-probe -> P3 design (conditional route-out) -> P4 plan gate -> P5 merge -> P6 symbol-survival -> P7 drift -> P8 adapt -> P9 verify -> P10 gate-merge -> P11 PR
- feat(odoo-ai-agents): forward-port plan gate moved into harness Plan Mode (EnterPlanMode / ExitPlanMode); plan.md is now a resume record, not the approval gate
- feat(odoo-ai-agents): odoo-intake skips its own Plan Mode when routing to odoo-forward-port (forward-port owns its P4 gate - no double Plan Mode)

### Added

- feat(odoo-ai-agents): installable:False category-3 - a module first made-installable at the source series but not yet upgraded for the target lands installable:False, decided by a TARGET CLEAN-TIP (pre-merge) discriminator
- feat(odoo-ai-agents): new read-only agent odoo-installable-prober - reads target clean-tip manifest + source git-history to drive the category-3 installable decision (delegated heavy git-history read)
- feat(odoo-ai-agents): conditional design route-out to odoo-solution-design for complex (bucket-(c)) modules via a return_to round-trip (design-only; returns to forward-port without dispatching a coder)

## [3.20.1] - 2026-06-21

- fix(odoo-ai-agents): odoo-doc-illustrator real-module smoke fixes - never drop existing on-disk doc locales (language list = tier-resolved UNION disk-detected locales, so a module already shipping bilingual docs keeps all of them); derive odoo_version from the parent dir series when the manifest version does not encode an Odoo series (Viindoo-style `0.2.2`); convention-detect now also scans `doc/` for bilingual RST

## [3.20.0] - 2026-06-21

- feat(odoo-ai-agents): new odoo-doc-illustrator agent - browser-driven visual documentation (capture screenshots into module static/description or cluster docs)
- feat(odoo-ai-agents): new odoo-doc-illustration thin skill dispatching odoo-doc-illustrator
- feat(odoo-ai-agents): wire odoo-doc-illustration into odoo-intake routing + collision-zones, and into odoo-content-draft / odoo-onboarding / odoo-capability-proof / odoo-feature-highlights continuation contracts
- feat(odoo-ai-agents): odoo-doc-illustrator real-module workflow - DOC LAYER appstore|userguide|both (App Store index.html + doc/index.rst), multilingual docs resolved from i18n.json default_languages, convention-detect from the target module, crop-default capture, [Hinh anh:] marker shared with odoo-content-draft

## [3.19.1] - 2026-06-21

### Fixed

- **Dropped non-portable `/code-review` and `/skill-creator` references.** These slash commands
  exist only on the maintainer's machine, so the `wave` / `odoo-forward-port` pipelines that called
  them would fail for any other user of this public plugin. Odoo code review now routes to the
  bundled `odoo-code-review` skill (OSM-grounded, always available, auto-spawns its reviewer from the
  orchestrating context); both commands are removed from the WI-worker spawner-ban enumerations and
  the maintainer notes.
- **`odoo-intake` Phase R no longer mislabels read-only leaf skills as Agent-tool targets.**
  `odoo-feature-check` / `odoo-override-finding` are skills (not agentTypes), so they are invoked via
  the Skill tool; only `Explore` / anonymous recon agents are launched directly - resolving the
  contradiction with the skill's own dispatch-mechanism rule.

### Changed

- **Neutral subagent-launch language.** Now that nested subagents are supported, skills describe
  dispatching a specialist agent as "launch ... as a subagent" rather than prescribing "the Agent
  tool", letting the execute-agent choose the mechanism. Load-bearing technical facts (a skill name
  is not an agentType, so it must go through the Skill tool) are kept.

## [3.19.0] - 2026-06-21

### Fixed

- **forward-port P4.5 now scans production code, not only `tests/`.** The python-import and
  AST-pyflakes survival classes run over ALL merged-touched `.py` (production AND `tests/`), so a
  runtime `NameError` left in production code by a clean merge is caught statically before the slow
  P5 behavioral run instead of slipping through to a chance test path. (Closes #101)
- **forward-port P5 triages every red against a clean-tip baseline.** A red test - whether in an
  edited module or in a co-installed dependency pulled in by the install closure - must be proven
  against a clean target tip before it is called a regression; co-installed-dependency reds are
  almost always pre-existing.
- **odoo-code-review surfaces the lint gate in the verdict.** The `### Lint gate (pylint-odoo)` slot
  reports PASS / FAILED / SKIPPED; a soft-degraded (toolchain-absent) run reads SKIPPED and must not
  be reported as a clean Python pass - an unrun gate is not a green gate.
- **odoo-code-review Phase 0 detects a sibling git worktree.** When `WORKTREE_PATH` is supplied it
  diffs there (`git -C <path> diff`) instead of cwd, so changes living in a `wave` / `odoo-forward-port`
  worktree are no longer silently reviewed as clean. `verify-backend.sh` gains `VERIFY_BACKEND_GIT_DIR`.
- **odoo-intake no longer double-gates a skill that owns a stronger gate.** When a routed skill opens
  with its own STOP plan gate (e.g. `odoo-forward-port` P0 per-commit plan), intake launches it
  directly instead of emitting a redundant soft-plan-gate.

### Added

- **forward-port symbol-survival class (g): ORM `create`/`write` dict-key field-literal scan.** Over
  all merged-touched `.py` (production call sites + test helpers), each dict key is cross-checked per
  field via `entity_lookup(kind='field')` to catch a renamed/removed field or a Many2one->Many2many
  type flip that pyflakes cannot see.
- **forward-port P5 optional `--test-tags` narrowing.** When the untagged closure suite is
  impractically large, the run may narrow to touched modules + their direct dependers - never to the
  edited module alone, which would hide a broken downstream-depender test.
- **odoo-onboarding persists a verify-environment cache** (`verify_python`, `addons_path`) into
  `.odoo-ai/context.md` so P5 / run / verify steps read it instead of re-discovering the interpreter
  and addons-path each time; the SSOT remains `~/.odoo-ai/instances.toml`.

## [3.18.0] - 2026-06-20

### Added

- **New `odoo-instance-ops` agent + `odoo-instance` skill** for end-to-end Odoo instance lifecycle
  (create, drop, init-modules, update-modules, run-tests, ensure-up, status) across all series v8+.
  Allocator B2 model: reserve-only acquire, Odoo create-on-init, through-Odoo drop via `odoo_db.py`
  and `55-instance-ops.sh`. Per-version CLI grounding via OSM `cli_help` with local-source fallback.
  Persistent logs at `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/`; parseable output lines `LOG_PATH=`, `STATUS=`,
  `TEST_RESULT=` forwarded in the canonical `instance-ops` handoff block.

## [3.17.1] - 2026-06-20

### Added

- odoo-i18n: translate into a LIST of target languages in one run (default vi_VN) instead of a single hard-coded language. P0 resolves the language list by precedence (explicit args > ~/.odoo-ai/i18n.json default_languages > existing <lang>.po filenames > res.lang active=True > default vi_VN) and echoes the source before the approval STOP.
- odoo-i18n: add a machine-global language registry ~/.odoo-ai/i18n.json ({"default_languages":[...]}), seeded idempotently by the odoo-setup instance-profile step; documented in commands/odoo-setup.md and docs/setup.md.
- odoo-i18n: document a per-language loop order in the recipe (.pot exported once per module, language-agnostic; .po / glossary / validation per language) plus per-language artifact naming (glossary-tm-<lang>.json, translation-report-<lang>.json, consistency-audit-<lang>.md).
- odoo-i18n: fix the v19 i18n example filenames in the recipe so the export and import lines agree (-o and -w now both use <lang>.po).

## [3.17.0] - 2026-06-20

### Added

- **New `odoo-i18n` skill + `odoo-translator` agent (closes #76).** A dedicated spawner skill for
  Odoo translation work (`.pot`/`.po`) usable by any workflow - forward-port, new-module/feature
  development, bug-fix. Non-destructive recipe (SSOT `skills/odoo-i18n/references/i18n-recipe.md`):
  `polib` translation-memory merge (`po.merge(pot)`) that preserves existing `msgstr`, isolated-DB
  per-module export with `-i <module> --skip-auto-install` (Odoo >=17; isolated-DB-per-dependency-order
  for <17) to avoid auto-install noise, non-empty-`msgstr` regression via `polib` (not `grep`),
  placeholder-integrity check, and validation by Odoo `-u` reload (not `msgfmt`). Instance-mandatory
  (no no-DB workaround); consistency audit is advisory (safe for independent VN circular regimes).
- **`Terminology consistency` guidance** added to `coding_guidelines/{14..19}.0/python.md` - look up
  the canonical term (core+deps TM / `.odoo-ai/glossary.yml` / OSM `entity_lookup` field.string)
  before coining a new label.
- Invariant test gates `tests/test_forward_port_hardening.py` and `tests/test_odoo_i18n.py`.

### Changed

- **`odoo-forward-port` hardening (closes #90).** P3.5 symbol-survival now covers 6 auto-merge-silent
  blind-spots (test base-class signature drift, file-existence refs, dynamic `ref()`/xml_id, Python
  import survival, AST `pyflakes` scan, `installable`-flag transitions) and includes `tests/` files.
  New P4.5 pre-adapt drift scan with a "test files collect cleanly" acceptance gate. P5 verify adds
  `--skip-auto-install` + `--http-port`, per-module `Loading module` parse, transitive-deps breadth,
  and baseline-fail attribution. P7 review made mandatory for grafted engines (enumerate every code
  path, cross-check static-review bot, attribution diff vs `origin/<target>`). The destructive i18n
  re-export caveat is replaced by a dispatch to the new `odoo-i18n` skill. New `installable:False`
  lint-only lane (dormant modules get lint/syntax fixes only, no logic review). `odoo-coding` emits
  `SUGGESTED_NEXT: odoo-i18n` after new-module or translatable-string work.

### Fixed

- `odoo-backend-debugger` / `_shared/debug-method.md`: a `0 failed, N error(s)` test result (setUpClass
  crash) is no longer read as a pass - tests did not run; never conclude "transient" without a
  deterministic red->green toggle.

## [3.16.2] - 2026-06-20

### Fixed

- `/odoo-plan-upgrade` now routes through `/odoo-intake` Phase P so the workflow's `on_complete`
  design handoff (`needs_design == true` -> `odoo-solution-design`) auto-advances under the run-driver
  instead of degrading to a human suggestion when the command is run directly. Closes #93.
- `check_workflows.py` driver-required warning is now sentinel-aware: a command declaring the
  `engages-run-driver` marker clears the warning, while a command that dispatches a driver-required
  (`on_complete`) workflow directly still trips it. Added `tests/test_check_workflows_driver.py`
  (red-green: sentinel-less command warns, sentinel command clears, plus a real-repo regression guard).

## [3.16.1] - 2026-06-20

### Changed

- Merged the forward-port pipeline into a single skill: `odoo-run-forward-port` is renamed
  to `odoo-forward-port` and absorbs the former command shim (argument schema, when-to-use,
  examples). `/odoo-forward-port` now invokes the skill directly.

### Removed

- The `odoo-forward-port` command shim (`commands/odoo-forward-port.md`); its `/odoo-forward-port`
  entry point is preserved by the renamed skill of the same name.

## [3.16.0] - 2026-06-20

### Changed

- **Relax the subagent-orchestration model to match Claude Code's multi-level nesting**
  (subagents may now spawn subagents, hard cap depth 5). The plugin no longer enforces a
  self-imposed "flat depth-1" model: removed every depth label (`depth0-only`,
  `depth-2 ceiling`, "never invoke from inside a subagent", "main-agent-only") across
  skills, agents, commands, docs, hooks and the generated orchestration map/digest.
- Subagent launching is now described generically as "launch subagent" instead of
  prescribing the `Agent tool` by name; the architectural `Skill tool` vs `Agent tool`
  dispatch distinction (skills are loaded via the Skill tool, raw agents via the Agent
  tool) is kept as accurate documentation.
- Repurpose `snippets/nesting-guard.md` -> `snippets/worker-brief.md`: drop the depth/
  nesting guard, keep the non-depth worker rails (OSM grounding + worktree git-isolation).

### Removed

- The `depth_policy` orchestration field (plus its `check_orchestration.py` validator,
  the generated `ORCHESTRATION-MAP.md` column and the digest line) - it was a duplicate
  of `spawn_class`.
- The `disallowedTools` spawn/skill locks (`Agent`, `Task`, `Skill`) on all 8 agent
  bundles - agents inherit the full tool surface and the harness depth cap is the only net.
- The flat-depth test guards that protected the retired model (`test_agent_frontmatter`
  Agent-in-disallowed assert, `test_agent_depth_rule_guard`, `test_agent_skill_invocation_guard`,
  `test_wi_brief_nesting_rule_present`); the principal-branch-lock and human-confirm-merge
  wave guards are kept.

### Fixed

- Ground the forward-port frontend adapt leg against `odoo-frontend-fidelity.md`
  (closes a pre-existing `orchestration-check` design-system gap).

## [3.15.0] - 2026-06-19

### Added

- **OSM test surface in the tool generator** - register the 6 test-writing tools from
  odoo-semantic-server PR #323 (`find_test_examples`, `tests_covering`,
  `test_class_inspect`, `test_base_classes`, `test_coverage_audit`, `js_test_inspect`)
  and the 2 test resources (`odoo://{version}/test/{module}/{class_name}`,
  `odoo://{version}/testcoverage/{model}`) into `generator/server-surface.json`
  (`server_version` 0.13.1 -> 0.15.0, 25 -> 31 tools, 7 -> 9 resources).
- Declare the test tools in `generator/skill_tool_deps.json` for the auto-gen skills
  `odoo-solution-design`, `odoo-run-forward-port`, `odoo-debug` and
  `odoo-deprecation-audit`, bumping their `min_server_version` to 0.15.0; regenerate the
  `## MCP tools` blocks, snippets and orchestration map via `make gen`.

### Changed

- `suggest_pattern` gains an optional `category` parameter and `module_inspect` documents
  the `method='tests'` discriminator (metadata refresh from PR #323). The
  `module_inspect` description refresh propagates to every skill block that lists it.
- **Ground the test surface across the code/test skills and agents** - wire the OSM PR #323
  test tools into the existing grounding points so agents stop reinventing tests, picking
  the wrong base class, or emitting `cr.commit()` inside `TransactionCase`:
  - `odoo-test-writing`, `odoo-coding`, `odoo-qa-suite` - base-class selection via
    `test_base_classes` (carries the `cr.commit()` FORBIDDEN contract), coverage baseline
    via `tests_covering`/`test_coverage_audit`, test-only search via `find_test_examples`,
    helper inspection via `test_class_inspect`.
  - `odoo-coder`, `odoo-frontend-coder` - coverage pre-check before dispatching the
    test-author; a JS Test Grounding mini-protocol (`js_test_inspect` framework detection
    plus `find_test_examples` with `kind='js'`).
  - `odoo-code-review`, `odoo-debug`, `odoo-code-reviewer`, `odoo-backend-debugger` -
    evidence-ground the "missing test" finding and the regression-test spec instead of
    guessing; flag `cr.commit()` inside test code.
  - `odoo-solution-design`, `odoo-solution-architect` - §7 test strategy grounded in OSM.
  - `odoo-run-forward-port` - P3.5 test-survival check so a test referencing a symbol
    deleted on the target version is caught instead of silently auto-merged.
  - `wave` injects test grounding into each WI brief; `odoo-deep-survey` maps test
    blast-radius; `odoo-intent-extractor` grounds test-class base chains;
    `odoo-deprecation-audit` detects deprecated test APIs (`SavepointCase`, QUnit -> Hoot).
- Wiring corrected against live OSM behavior: `find_test_examples` kind enum is
  `transaction|http|form|js` (no `python`); `SavepointCase` is a deprecated alias still
  present in v16+ (not a removal); `test_class_inspect` returns base chain + cursor
  contract, not setUpClass fixture contents; `test_coverage_audit` reports field-level gaps
  only; JS is QUnit on v17 and Hoot on v18+.
- `suggest_pattern(category='test')` is intentionally NOT wired: the server returns empty
  (test patterns not yet seeded) - tracked as a follow-up issue against odoo-semantic-server.

## [3.14.2] - 2026-06-19

### Added

- **Example-tool-call required-param gate** (`tests/test_agent_facing_guidance.py`) - new
  `test_example_tool_calls_pass_all_required_params` asserts every concrete example tool call in
  `skills/`, `agents/`, `snippets/`, `docs/` supplies ALL required params per
  `generator/server-surface.json` (not just valid param names). Uses slot-based positional coverage
  (a param is satisfied when named or when a positional fills its slot in the tool's canonical
  `example_call`), so tools that interleave an optional positional between required ones
  (`entity_lookup`, `profile_inspect`, `lint_check`, `cli_help`) are handled correctly. Ellipsis
  sketches (`...`/`…`) stay exempt. Closes the gap where an example missing a required param
  (e.g. `model_inspect` without `method=`) passed CI but was rejected by the OSM server at runtime.
- **Kind-conditional required-param gate** (`tests/test_agent_facing_guidance.py`) - new
  `test_example_tool_calls_pass_conditional_required_params` enforces `entity_lookup`'s kind-dispatched
  discriminators (ADR-0028): `kind='field'` needs `model=`+`field=`, `kind='method'` needs
  `model=`+`method_name=`, `kind='view'` needs `xmlid=`, `kind='module'`/`'pattern'` needs `name=`. Rules
  are data-driven from a new `conditional_required` map in `generator/server-surface.json`. Catches the
  class where an example is gate-clean on universal required params but uses the wrong/absent kind
  discriminator (e.g. `entity_lookup(kind='field', name=...)`), which the OSM server rejects at runtime.
  Pipe-alternation (`kind='a'|'b'`), placeholders, and `...` sketches are skipped/exempt.

### Fixed

- **21 example tool calls missing a required param** across 13 files - added the missing discriminator
  (`module_inspect` -> `name=`, `model_inspect` -> `model=`/`method=`) so copied examples are
  runtime-valid. Doc-only (examples in skills/agents/snippets/docs prose); no runtime behavior change.
- **`entity_lookup` kind-conditional discriminator examples** - fixed `entity_lookup(kind='field', ...,
  name=...)` -> `field=...` (OSM rejects `name=` for `kind='field'`) and converted illustrative/
  comparison-prose `entity_lookup(kind='method'/'field'/'view', ...)` shorthands to `...` sketches.
- **`lint_check` surface drift** (`generator/server-surface.json`) - moved `code` from `optional_params`
  to `required_params` to match the live OSM schema (`code` is required); regenerated the Cursor/OpenAI/
  Gemini tool-surface snippets accordingly. Strengthens the required-param gate for `lint_check`.

## [3.14.1] - 2026-06-19

### Added

- **Security Pitfalls coding-guideline doc** (`skills/_shared/coding_guidelines/<ver>/security.md`)
  for every supported series 14.0-19.0 - the secure-coding companion to `python.md`, extracted
  from the official Odoo `security.rst#security-pitfalls` (v14 from `reference/addons/`, v15-19
  from `reference/backend/`). Covers Unsafe Public Methods, Bypassing the ORM / SQL injection,
  domain injection (`Domain`, v19), Unescaped field content / `t-raw` XSS, `markupsafe.Markup`
  (v17+), Escaping vs Sanitizing, Evaluating content / `safe_eval`, and Accessing object
  attributes / `getattr`. Each file is self-contained per the per-version convention.

### Changed

- The six per-version `python.md` warnings that pointed at a non-existent "Security Pitfalls
  (reference/security/pitfalls)" section now resolve to the local `security.md` in the same
  directory - closing a 6-way dangling reference.
- `security.md` is wired into the mandatory read-before-write set: the Round-1 topic-file
  enumeration of `odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, and
  `odoo-solution-architect`, the backend list in `snippets/read-before-write-contract.md`, and
  the "Table of contents" + "By task" rows of every `coding_guidelines/<ver>/INDEX.md`.

### Fixed

- Replaced the dangling `scripts/verify-guidelines.sh` reference (a script that never existed)
  in `coding_guidelines/INDEX.md` and `snippets/read-before-write-contract.md` with the real
  pre-push gates `scripts/verify-backend.sh` and `scripts/verify-frontend.sh`.
- Corrected upstream bugs in the v19 "Bypassing the ORM" code example (`x[x]` -> `x[0]`, added
  the missing closing bracket) carried into `19.0/security.md`, annotated inline.

### Tests

- `tests/test_execute_agent_hardening.py` gains a "B4" section asserting each `security.md`
  exists with a `# Security Pitfalls` heading, each `python.md` warning resolves locally (no
  `reference/security/pitfalls`), the four code agents + the contract snippet name `security.md`,
  the new docs are ASCII-hyphen-only, and `verify-guidelines.sh` is gone.

## [3.14.0] - 2026-06-18

### Added

- **`/odoo-forward-port` command** (`commands/odoo-forward-port.md`) - thin shim for
  continuous and one-shot forward-port workflows; accepts `<source-ref> <target-branch>
  [--scope] [--since] [--one-shot]` and resume-checks `checkpoint.json` before dispatching
  to the `odoo-run-forward-port` skill orchestrator.
- **`odoo-intent-extractor` agent** (`agents/odoo-intent-extractor.md`) - read-only
  per-commit intent extraction used in Phase 1 of the forward-port pipeline; model is
  `sonnet` by default with caller-level override at dispatch; `disallowedTools` blocks
  `Agent`, `Task`, and `Skill` to enforce the read-only contract.
- **`odoo-run-forward-port` skill** (`skills/odoo-run-forward-port/SKILL.md`) - 8-phase
  forward-port orchestrator (SSOT): P0 plan-gate, P1 parallel intent-extract, P2
  4-outcome classify, P3 merge --no-commit, P3.5 symbol-survival-check (autosilent-break
  gate), P4 test-first adapt (serial per commit), P5 per-batch verify, P6 merge-gate,
  P7 PR + review. Merge-keep-SHA protocol: outcome (a)/(d) commits merge without adapt
  diff; worktree isolation throughout.
- **Snippet `fp-intent-4outcome`** (`snippets/fp-intent-4outcome.md`) - SSOT 4-outcome
  classification table for forward-port commits (skip / 3-way+adapt / re-implement /
  skip-new-module).
- **Snippet `fp-symbol-survival-check`** (`snippets/fp-symbol-survival-check.md`) - SSOT
  Phase 3.5 autosilent-break gate: OSM-ground every symbol on the source side of
  conflicted + merge-clean-but-source-touched files; symbol absent in target forces bucket
  b/c/d, blocking silent field-break absorption.
- **Snippet `fp-merge-absorption`** (`snippets/fp-merge-absorption.md`) - merge-keep-SHA
  protocol and per-batch verify toggle; codifies the skip-code-still-merges rule (outcome
  a/d) and the RED-then-GREEN confirm-by-toggle gate for FP-delta tests.
- **Snippet `fp-installable-false`** (`snippets/fp-installable-false.md`) - new-module
  forward-port handling: set `installable: False`, comment out `auto_install` and
  `application`, run only lint; tracks the migration-rename gate
  (`installed < parse(dir)`).

### Changed

- **`odoo-test-writing`** gains a new `adapt` mode for forward-port test forwarding:
  translates API calls to the target version, strips source-snapshot assertions, and
  confirms RED-on-target before handing back to the adapt phase. Reference detail in
  `skills/odoo-test-writing/references/fp-adapt-mode.md`.
- **`odoo-version-diff`** gains a reference to the FP 4-outcome mapping
  (`snippets/fp-intent-4outcome.md`) so version-diff callers can bucket findings
  consistently with the forward-port pipeline.
- **`odoo-code-review`** gains pitfall #11 (test-coupled-to-src-API): flag tests that
  hard-code source-version field names or method signatures as HIGH when reviewing
  forward-ported code.
- **`snippets/test-first-contract`** gains a forward-port RED-on-target paragraph:
  a test that passes without modification on the target branch is not a forwarded test,
  it is a tautology - confirm RED before adapting.

## [3.13.0] - 2026-06-18

### Added

- **Concurrent Odoo instance allocator** (`plugins/odoo-ai-agents/scripts/lib/allocator.py`) - a
  deterministic, version-agnostic lease allocator so many subagents across many concurrent Claude
  Code sessions stop colliding on the single declared `db_name`/`http_port`. Each caller gets either
  an isolated **ephemeral** database (auto `createdb` on acquire, `dropdb` + filestore cleanup on
  release/GC; degrades to exclusive when the DB role lacks `CREATEDB`), an **exclusive** lease on the
  declared instance (single holder + pooled ports), or a lease-free **readonly** handle.
  Coordination is an atomic RMW under an `fcntl.flock`-guarded registry at
  `${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime/`; stale leases are reclaimed opportunistically at each
  acquire (dead-pid same-host + TTL). The allocator returns resource facts only (db, ports, token);
  consumers build the `odoo-bin` command and map ports to CLI flags via `cli_help` at runtime, so
  future Odoo CLI changes never touch the script. Subcommands `acquire`/`release`/`heartbeat`/`gc`/
  `list` emit shell-eval `ALLOC_*` lines. Design: `docs/reference/INSTANCE-ALLOCATION.md`; 12
  behavior tests in `tests/test_allocator.py` (the Postgres `createdb`/`dropdb` path skips when no
  local PG). Wired into the backend/frontend coders (DB-touching `odoo-bin` runs acquire an ephemeral
  DB, then release), the resolution snippets (`instance-resolution.md` "Allocate, don't just
  resolve"; `resolve_instances.sh` `_odoo_ai_runtime_dir` SSOT; `venv-resolution.md`),
  `skills/_shared/concurrency-guard.md`, `skills/odoo-coding/SKILL.md`, and
  `docs/reference/ODOO-TESTING.md`.
- **Shared live-render target wired into the allocator** - a new non-exclusive `shared` mode plus a
  `query --series` discovery subcommand let `scripts/setup-steps/50-instance-spinup.sh` register the
  spun-up server (its actual bound port + the live server pid; `created_db=false` so gc never drops
  the declared DB) and let `snippets/instance-resolution.md` discover that live port across sessions
  before falling back to the static `http_port`. The four visual consumers (`odoo-ui-reviewer` /
  `odoo-ui-debugger` / `odoo-visual-regression` / `odoo-demo-recording`) inherit it through the
  resolution snippet with no per-consumer edits; registration is best-effort and degrades to plain
  spin-up when the allocator is absent. A concurrent same-series start is benign (the loser loses the
  OS port bind and both sessions attach to the one live server).

### Changed

- **Engineering agents hardened and compacted** (`odoo-coder`, `odoo-solution-architect`,
  `odoo-frontend-coder`, `odoo-code-reviewer`). New normative guidance - Domain Knowledge
  Activation, Module Ownership / dependency-direction integrity (incl. the CE/EE bug-fixes-only
  policy), Code Quality Standards (flake8 / ESLint as functional requirements), solution/module
  Acceptance Criteria, and a per-module-vs-synthesis review mode - while the preloaded
  system-prompt token cost was reduced by tightening prose (agent bodies are rewrite-only, so no
  relocation). `odoo-coder`'s `disallowedTools` was narrowed to block only `Agent`, so it can invoke
  the `odoo-test-writing` skill for the test-first loop. `odoo-ui-debugger` / `odoo-ui-reviewer`
  gained a "headless by default, headed only on request" browser-mode section.
- **`odoo-code-reviewer` now reviews intent + domain + TDD conformance, and is compacted 299 -> 183
  lines.** It gained a Domain Knowledge Activation section, an intent / business-value lens, and a
  TDD-conformance step: when the dispatch brief carries `DESIGN_DOC: <path>` (wired through
  `skills/odoo-code-review`), the reviewer verifies the code against the design's Intent & Business
  Value (section 1) and Acceptance Criteria (section 9, solution + per-module) and emits a
  `### TDD Conformance` block - an unmet criterion or a code-vs-intent divergence is a HIGH/CRITICAL
  finding.
- **No more hardcoded `17.0` version default.** Across agents, personas, skills and snippets the
  example tool-calls now use a `<version>` placeholder, and the agents STOP and ask when the target
  Odoo version is ambiguous instead of silently assuming v17.
- **`odoo-coding` dispatch brief slimmed to run-specific params only** - the per-module procedure is
  stated once in the agent system prompt (SSOT). `tests/test_execute_agent_hardening.py` was
  repurposed from a brief-snapshot assert to a behavior assert.
- **Repo-wide ASCII-hyphen normalization** (em-/en-dash -> `-`) across docs, skills, agents,
  snippets, workflows and tests.

### Fixed

- **Profile-name correction** `viindoo_internal_17` -> `standard_viindoo_17` in
  `generator/server-surface.json`, `hooks/detect-intent.sh`, `docs/reference/workflow-harness.md`
  and several skills/snippets.
- **Skill-name consistency** `odoo-test-writer` -> `odoo-test-writing` (skill directory rename plus
  all references in docs, agents, skills, snippets and tests).

## [3.12.0] - 2026-06-16

### Added

- **`/odoo-setup` runs an interactive checkbox menu when given no arguments** -
  `plugins/odoo-ai-agents/commands/odoo-setup.md`. You no longer need to remember any flag: type
  `/odoo-setup` and pick what to do from an `AskUserQuestion` multi-select (browser automation stack /
  declare + spin up a local instance / reset `instances.toml`). The filter arguments
  (`all`/`browser`/`runtime`/`permissions`/`instance`/`--reset`) remain as optional shortcuts.
- **New setup step `47-instance-reset.sh`** - backs up `instances.toml` then writes a clean file,
  dropping dead/legacy entries; `--hard` wipes all instances. Reset-only (`--reset` filter); its
  `check` is always-satisfied so the `all` loop never triggers it.
- **New library `scripts/lib/osm_repo_map.py`** - normalizes any git remote URL (SCP/SSH/HTTPS) to a
  single match key and builds SSH clone commands (`-b <branch> --no-single-branch`, `odoo<major>` dir).

### Changed

- **The `/odoo-setup` instance cluster is now OSM-grounded and propose-then-confirm** instead of
  auto-deciding. It asks the Odoo Semantic index for versions -> profiles -> repos, spawns a read-only
  scan to map each repo/venv to a local path, and confirms every mapping with the user before any file
  is written (5 confirm gates). When the index is unavailable it degrades to a user-declared mode.
  `addons_path` ordering is own-repos-first -> ancestor -> core-last (Odoo resolves modules
  first-wins), reorderable at the confirm gate. The hard rule "do not spawn a subagent" is replaced by
  "spawn a read-only scan only; all file mutations go through the deterministic step scripts".
- **Setup step `40-instance-profile.sh` no longer auto-discovers-and-writes.** `apply` requires a
  confirmed `ODOO_AI_PROFILE_SPEC` (validated upfront - no partial writes) and refuses to write
  without it.
- **Setup steps `45-venv.sh` / `50-instance-spinup.sh` hardened.** `45` records the `python` field only
  after `import odoo` succeeds and accepts multiple `--requirements`; `50` validates the interpreter
  and database reachability before launch and fails loudly instead of polling a doomed start.

## [3.11.5] - 2026-06-16

### Changed

- **`instances.toml` is now machine-global, resolvable from any working directory**
  (`plugins/odoo-ai-agents/scripts/lib/resolve_instances.sh`). Previously the setup steps wrote and
  read `<cwd>/.odoo-ai/instances.toml`, so an execute-agent running in a different repo could not
  discover an Odoo instance declared elsewhere - yet the declared instances are a property of the
  HOST, not the project. The instance profile now lives at the machine-global
  `~/.odoo-ai/instances.toml` (override with `ODOO_AI_HOME`, or an explicit full-path
  `ODOO_AI_INSTANCES`). Resolution is global-wins: `$ODOO_AI_INSTANCES` ->
  `${ODOO_AI_HOME:-$HOME/.odoo-ai}/instances.toml` -> a project-local `./.odoo-ai/instances.toml`
  (transitional fallback). Steps `40`/`45`/`50` share the new resolver; `40 apply` migrates an
  existing project-local file to the global path once (idempotent copy, never clobbers) and writes a
  defensive `~/.odoo-ai/.gitignore`. Every other `.odoo-ai/` artifact (`context.md`, `survey/`,
  `worklog/`, ...) stays project-scoped. The resolver is bash 3.2-safe (macOS) and covered by new
  tests in `tests/test_setup_instances.py`. Agent/skill/doc guidance updated; see the new
  `plugins/odoo-ai-agents/snippets/instance-resolution.md`.
- **Agents that RUN Odoo now have an interpreter-discovery pointer** - new
  `plugins/odoo-ai-agents/snippets/venv-resolution.md` documents how to resolve the venv `python`
  to run `odoo-bin` (scaffold / `--test-enable`) / tests / migrations: the matching instance's
  `python` field (via `instances_io.py read`) -> `$ODOO_PYTHON` -> system `python3` (last resort),
  the same chain `50-instance-spinup.sh` uses. Wired into `odoo-coding` (the `odoo-bin scaffold`
  step), `odoo-test-writing`, and `odoo-data-migration`. Also finishes the instance-resolution wiring
  in `odoo-demo-recording` (it now falls back to the machine-global `instances.toml` instead of
  immediately asking the human).

## [3.11.4] - 2026-06-16

### Fixed

- **Playwright browser deps now install correctly across the supported Ubuntu LTS line
  (22.04 / 24.04 / 26.04) and macOS 13+** (`plugins/odoo-ai-agents/scripts/setup-steps/20-browser-deps.sh`).
  Playwright is now pinned via `PLAYWRIGHT_PIN` (default `1.61.0`, the first release that supports
  Ubuntu 26.04 per microsoft/playwright#40117, and still valid on 22.04/24.04 and macOS). The
  previous unpinned `npx -y playwright install` resolved to whatever the local npx cache held (e.g.
  1.60.0), which cannot install Chromium on Ubuntu 26.04. The pinned Chromium build is shared by the
  `pagecast` server, so this covers pagecast too. A new CI matrix
  (`.github/workflows/validate.yml` -> `browser-deps`) runs the real install plus a headless
  Chromium launch on ubuntu-22.04, ubuntu-24.04, ubuntu-26.04 (public preview), and every macOS
  version GitHub still hosts a runner for - macos-14 / macos-15 / macos-26 (arm64) plus
  macos-15-intel (x86_64). (macos-13 is not used: GitHub retired that runner image on 2025-12-08,
  so any job pinned to it queues forever; the binary-only macOS path still works on macOS 13+.)

### Changed

- `20-browser-deps.sh apply` now also installs Chromium's shared system libraries on apt-based
  Linux: automatically via `playwright install-deps` when passwordless `sudo` is available,
  otherwise it prints the exact command to run (it never runs sudo silently). `check` now probes
  those libraries by real soname, so a host that has the browser binary cached but the libraries
  missing is correctly reported as not-ready instead of being skipped. macOS, Windows, and non-apt
  Linux keep the binary-only path unchanged.

## [3.11.3] - 2026-06-14

### Fixed

- **Killed the recurring `undefined is not an object (evaluating 'modules')` crash** that hit the main
  agent whenever it dispatched `odoo-coding` (and, by imitation, other tasks) through the Claude Code
  Workflow (JS) tool. Root cause: `odoo-coding/SKILL.md` shipped a JS Workflow script that destructured
  the `args` global with no guard, no invocation example, and a resume example that omitted `args` -
  so `args` arrived `undefined` (passed as a JSON string, omitted, or dropped on resume) and the script
  crashed on the first `args` access. The Workflow tool always needs a JS script and `args` is
  `undefined` when not provided, so the fragile path was removed rather than patched.

### Changed

- **`odoo-coding` now dispatches the coder agents via the Agent tool exclusively, in model-weighted
  batches** (SSOT `skills/_shared/concurrency-guard.md` Mode B), instead of a JS Workflow pipeline.
  `wave` already proved model-weighted dispatch works on the Agent tool alone. Test-author isolation is
  preserved (two sequential Agent calls - no JS needed). Trade-off accepted: true rolling-window becomes
  a model-weighted batch barrier per round, and `resumeFromRunId` is gone (resume = re-dispatch the
  BLOCKED modules as fresh Agent calls).
- `docs/reference/workflow-harness.md`: added an invariant - this plugin does NOT use the Claude Code
  Workflow (JS) tool; all fan-out is Agent-tool / Skill-tool / `run-driver`. README, ORCHESTRATION-MAP
  (regenerated from `generator/skill_tool_deps.json`), `concurrency-guard.md`, and `wave/SKILL.md`
  updated to match.

### Removed

- The inline JS Workflow script and all "Workflow tool / rolling-window pipeline" dispatch guidance from
  `odoo-coding/SKILL.md` (~376 net lines). `tests/test_concurrency_guard_ssot.py`:
  `test_odoo_coding_passes_model_explicitly_on_both_paths` -> `test_odoo_coding_passes_model_explicitly`
  (a single dispatch path now).

## [3.11.2] - 2026-06-14

### Changed

- **Agents now get the FULL odoo-semantic surface, drift-proof.** Every `agents/*.md` drops its
  enumerated `mcp__odoo-semantic__*` `tools:` allowlist and instead omits `tools:` (inherit the full
  tool surface dynamically) + a minimal `disallowedTools` denylist. When the OSM server adds/renames a
  tool, agents pick it up automatically - no `server-surface.json` snapshot edit, no PR, no drift. The
  enumerated allowlist could never track the live server (the snapshot is hand-maintained), so this
  replaces it with dynamic inheritance. `disallowedTools` blocks only spawn (`Agent`/`Task`) on every
  agent, plus `Skill` on the 5 agents that must not invoke skills (kept for `odoo-frontend-coder` /
  `odoo-solution-architect`, which invoke `odoo-frontend-design`). Write/Edit are NOT blocked - every
  agent writes artifacts (worklog/report/design-doc/source).
- **Fixed a latent bug:** `odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-ui-reviewer` instructed
  "APPEND your worklog" but lacked `Write` in their allowlist (could not actually write). Inheriting the
  full surface restores `Write`, so the worklog contract now works.
- **`odoo-code-reviewer`:** replaced the hard-coded 11-tool step-by-step OSM usage list with a general
  directive ("you have the full surface - pick whatever fits, no fixed tool list"); review logic,
  severity rules, and snippet wiring unchanged. Stale "tool allowlist above" guard prose in all agents
  updated (there is no allowlist anymore).
- `generator/skill_tool_deps.json`: dropped the vestigial `agents:` section (agents inherit, not
  enumerated). Tests updated to the new agent contract (`disallowedTools` carries the no-spawn guard;
  OSM is inherited).

## [3.11.1] - 2026-06-14

### Changed

- **Compressed all 41 SKILL.md bodies + 7 agent system-prompts to cut token-per-invoke.** Structure
  refactor (no behavior change): reference-only blocks (worked examples, output-format templates,
  lookup tables, the brl Phase-E deliverable templates, the wave Mode-B dispatch loop) were relocated
  to per-skill `references/` files behind a one-line `${CLAUDE_PLUGIN_ROOT}/...` pointer (progressive
  disclosure - loaded on demand, not every invocation), and verbose prose was tightened. Agents are
  rewrite-only (their body is a preloaded system prompt, so no relocation). Skill bodies -25.0%
  (645,872 -> 484,526 B), agent bodies -16.6% (160,026 -> 133,507 B); ~188 KB removed from the
  on-invoke load. Frontmatter/descriptions byte-identical (triggering unchanged); all generated tool
  blocks untouched; full `pytest tests/` green.
- **`odoo-intake`: added a "Your role - orchestrator, not implementer" section** at the top of the
  body - frames the main agent as the team leader that gets work done by invoking the right skill
  (Skill tool), launching an agent directly only when no skill fits, and owning orchestration +
  decisions rather than hand-implementing.

## [3.11.0] - 2026-06-13

### Added

- **`hooks/auto-approve-browser.sh` (PermissionRequest hook).** Auto-approves the plugin's own
  browser MCP tools in-session, closing the window where SessionStart-applied permissions only take
  effect after a restart (Claude Code finalizes permissions before SessionStart fires). Stays silent
  (pass-through) for any non-plugin tool; opt out with `ODOO_AI_NO_AUTO_PERMS=1`.
- **`scripts/bump-version.sh auto` + `make bump` / `make bump-dry`.** Deterministic version-bump
  classifier that makes the existing policy operational: a `feat:` commit or a newly added
  command/skill/agent file -> minor; fix/refactor/docs/chore -> patch; `type!:` or `BREAKING CHANGE:`
  footer -> major. A human may still name an explicit `X.Y.Z` (natural-language override). The commit
  range anchors on the last `VERSION` change, not the (stale) `v*` tags.

### Fixed

- **Browser MCP `-headed` tools no longer prompt on every call.** The permission allow-list is now
  DERIVED from `.mcp.json` (the single source of truth) and lists every server - all three `-headed`
  variants included - fixing a drift where only the 3 base servers were allow-listed. A permission
  rule `mcp__<server>` matches at the `mcp__<server>__` boundary, so it never covered the distinct
  `-headed` servers; each needs its own entry.

## [3.10.0] - 2026-06-13

### Added

- **Two-variant browser MCP servers (headless default + headed on request).** Each browser backend
  (chrome-devtools, playwright, pagecast) now ships TWO servers: a headless default (`<name>`, passes
  `--headless`) and a visible `<name>-headed` variant - 6 servers total. The AI agent selects the
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
  `odoo-coding` / `odoo-test-writing`.
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

- **`odoo-backend-coding`** and **`odoo-frontend-coding`** skills - subsumed by the unified
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
- **7 new domain skills:** `odoo-test-writing`, `odoo-security-audit`, `odoo-data-migration`,
  `odoo-perf-audit`, `odoo-pricing-proposal`, `odoo-rfp-response`, `odoo-customer-health`.
- **`research-multiphase` workflow** - flexible-phase, multi-model-tier research dogfood.

### Changed

- **Per-plugin READMEs.** Split the shared root README into self-contained
  `odoo-semantic-skills` and `odoo-semantic-mcp` READMEs; the root README is now a monorepo
  landing page that links to both. Reworked the overview/commands mermaid diagrams for
  readability (vertical layout, fewer crossing edges).

## [3.0.0] - 2026-06-06

### Changed (BREAKING) - naming normalization across skills, agents, and commands

Names now encode **role** so an AI router (and a human) can tell the three layers apart even
when a name appears bare, without its `odoo-semantic-skills:` namespace: **skill** = a
capability noun (`-review`, `-analysis`, `-coding`), **agent** = an actor noun (`-er/-or`),
**command** = an imperative verb-object (`odoo-run-brl`). This removes three skill↔agent
name collisions and the agent-suffixed skills that were masquerading as executors. The full
convention is documented in `CONTRIBUTING.md` → "Naming convention: skill vs agent vs command".

**Migration (clean break, no aliases).** There is **no backward-compatibility shim** - invoking
an old name after updating to 3.0.0 fails with "not found"; use the new name (table below). To
defer migration, pin the plugin to `2.x`. The four **agent** names are unchanged. Skill
descriptions/trigger phrases are unchanged, so natural-language routing behaves identically -
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

**Commands renamed (9)** - `name:` now equals the filename (the invoked name); old `name:`
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

- **Local reproduction of the Odoo code-quality CI gate (issue #46) - multi-version aware, baked
  into the verify/test flow.** New `scripts/verify-backend.sh` is the backend sibling of
  `verify-frontend.sh`: it runs `pylint --load-plugins=pylint_odoo` on changed Python from an
  **isolated tools venv** (`$ODOO_AI_DIR/tools/pylint-<series>/`, never the instance venv), with
  pylint/astroid/pylint-odoo pinned per Odoo series in the extended
  `scripts/lib/odoo-python-matrix.json` (`lint` block; 16/17 → the verified-faithful
  pylint-odoo 8.0.22 · pylint 2.15.10 · astroid 2.13.5 combo, 18 → 9.x (pylint 3), 19 → 10.x
  (pylint 4, which pylint-odoo 10 hard-requires) - each pylint era-matched to its pylint-odoo major
  to avoid checker-plugin crashes). Always loads `pylint_odoo` so the
  `consider-merging-classes-inherited` pragma never reads as the `W0012` vanilla false signal, and
  **derives the enabled-code set from the deployment's own quality module** (`test_pylint`/`test_lint`)
  when present - no deployment-internal config is vendored. Graceful degradation (soft-warn, exit 0)
  when the toolchain/series/files are absent, with an opt-in `--provision` to build the pinned venv.
  Shipped fallback `scripts/odoo-pylintrc` (OCA defaults).
- **`/test_lint` mandate in the test-run SSOT.** `docs/reference/ODOO-TESTING.md` now documents the
  two-part gate (core `test_lint` + `pylint-odoo`) once; `odoo-qa-suite`, `odoo-deploy-checklist`,
  `wave`, `INSTANCE-LIFECYCLE.md` and `osm-first-contract.md` inherit it via their existing pointers.
  `odoo-coder` (Round 4) and `odoo-code-reviewer` now run `verify-backend.sh`; `odoo-deploy-checklist`
  gains a Domain-6 pre-push parity item. New reference: `docs/reference/odoo-code-quality.md`.
- **Enforcement substrate - `SubagentStop` grounding hook (`hooks/enforce-grounding.sh`).** Turns the
  previously advisory OSM-first contract into a checkable invariant: it reads the worker's own
  transcript (assistant-authored content only) and **blocks once** (loop-safe via `stop_hook_active`)
  when an artifact claims `grounded: osm` but made zero `mcp__odoo-semantic__*` calls, asking the
  agent to actually verify or relabel honestly. Self-gates to Odoo-shaped subagents. Two softer
  gaps raise a **non-blocking note** (never a block - a block there only manufactures unverifiable
  `grounded: local-source` labels and false-blocks legit pure-Python/standalone work): backend
  code written with OSM reachable but the ORM validators skipped; and the **silent-skipper** -
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

- **`detect-intent.sh` routed structure-lookup questions to the vault instead of the OSM index** -
  the UserPromptSubmit hook only surfaced the index hint for code-gen intents (domain
  `engineering|upgrade|visual-UI`) and worded it as "before generating or editing Odoo code", so a
  composition/lookup question ("which modules / repos does profile X contain") got no pointer to the
  index and the agent fell back to the vault - even though `profile_inspect` answers it directly.
  Added an `_is_lookup` intent probe (EN `module/repo/profile/version/inventory/composition` + VI
  `gồm / có gì / module nào / repo nào / những gì / có bao nhiêu`) that emits an `[OSM-lookup]` hint
  naming `profile_inspect` / `describe_module` / `model_inspect`, fired on Odoo/Viindoo anchor +
  lookup intent **independent of `_domain`** (so a general-domain Viindoo question still routes to
  the index). The hint is an in-context pointer that survives ToolSearch deferral of those tools.

## [2.7.0] - 2026-06-05

### Added

- **OSM server 0.13.1 surface sync (24 → 25 tools)** - mirror the new `profile_inspect` tool
  (`method=summary|repos|modules`: profile inheritance chain + repos + module inventory/count,
  ADR-0028) into `generator/server-surface.json` and wire it into the skills that answer
  "what's in this profile" questions: `odoo-onboard` (records module inventory into
  `.odoo-ai/context.md`), `odoo-customization-inventory`, `odoo-addon-diff`, `odoo-brl`,
  `odoo-risk-overview`, `odoo-competitive-brief`, `odoo-discovery-summarize`, `odoo-campaign-plan`.
- **Live version-gate (closes #40 Finding 2)** - `check_deps.py` now enforces the previously-dead
  `server_version_required` / per-skill `min_server_version` fields: each floor must cover the
  newest tool the skill/agent uses and stay ≤ the mirrored server version (semver compare).
- **OSM-maximization pass across skills + agents** - wired, at each phase, the OSM tool/resource
  that removes a concrete guessing step: `impact_analysis` (BRL Extension-M/L blast radius);
  `set_active_version` pins (ui-debug / visual-regression / demo-recorder / ui-reviewer - stop
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

- **#41 - skill examples pinned non-existent profile names** - replaced `viindoo-internal` (hyphen)
  and bare `odoo` with versioned names (`standard_viindoo_17`, `odoo_17`) across odoo-brl,
  odoo-gap-analysis, odoo-onboard, odoo-customization-inventory, odoo-addon-diff, evals, schema,
  workflow-harness, context-bootstrap; preserved the "read from `.odoo-ai/context.md` /
  `list_available_profiles`, never hard-code" guidance.
- **Tool descriptions resynced to 0.13.x behaviour** - `find_examples` documents the lexical
  fallback when the embedder is down (#264); `model_inspect` documents the `extenders` method +
  the real page caps (#262).

### Changed

- **Provenance stamp 0.11.1 → 0.13.1 (closes #40)** - `server_version` in the surface SSOT plus
  every hand-maintained "24 tools / v0.11.1" label (README, ROADMAP, setup.md, dev.md, snippet
  intros, MANUAL skill footers); generated surfaces regenerated via `make gen`.

## [2.6.0] - 2026-06-05

### Added

- **Agent-first grounding SSOT (PR #42)** - two new snippets the skills/agents reference by
  path: `snippets/disk-fallback-protocol.md` (three-tier grounding: OSM index → disk self-serve
  via Read/Grep/Bash/WebFetch → training-memory flagged `ungrounded`) and
  `snippets/context-bootstrap.md` (a mandatory Round 0 that reads `.odoo-ai/context.md` before
  asking the caller for version/profile/module list).
- **`odoo-frontend-coder` agent (PR #43)** - frontend coding is now an agent+skill bundle
  (mirrors `odoo-coder` / `odoo-code-reviewer`): a slim routing skill plus an isolated executor
  agent with a restricted tool allowlist (incl. `resolve_stylesheet` / `find_style_override`),
  so version-gating + multi-round MCP runs out of the main agent's context.

### Changed

- **Standalone-first fallback: paste-only → disk-grounded (PR #42)** - when OSM is unreachable
  a skill now reads the source itself (`find`/`grep`/`Read`, `WebFetch` upstream) instead of
  asking a human to paste code/fields/manifests; copy-pasteable output is the last resort
  (repo genuinely inaccessible). **This reverses the [2.5.0] decision to keep the fallback
  paste-only.** Visual skills return `BLOCKED(...)` when a browser/instance is unreachable
  rather than soliciting screenshots. `hooks/detect-intent.sh` recommends disk-grounded
  fallback accordingly.
- **Portability (PR #42)** - sales/visual flows no longer depend on the non-official live Odoo
  ERP MCP (`mcp__odoo__*`) or the claude.ai Gmail MCP; deal/CRM/email data comes from the
  invocation context and `.odoo-ai/context.md`, instance URL from `.odoo-ai/instances.toml`.
  Any live ERP/email integration is an optional bonus, never assumed.
- **Code skills self-author (PR #42)** - `odoo-coder` / `odoo-code-reviewer` /
  `odoo-frontend-coder` write and review code natively (boilerplate from `find_examples`
  templates, complex logic reasoned step by step, inline self-review) instead of delegating.
- **Model-tier (PR #42)** - `feature-positioning.workflow.yaml` feature-check / addon-diff
  `haiku` → `sonnet` (OSM synthesis, not simple lookup); `haiku` definition tightened in
  `_schema.md` / `workflow-harness.md` (never for write/synthesis phases). The
  `set_active_profile` example reads `viindoo_profile` from `.odoo-ai/context.md` instead of
  hard-coding `viindoo-internal`.
- **Frontend bundle + version portability (PR #43)** - the `odoo-frontend-coder` skill is
  renamed `odoo-frontend-coding` (the agent keeps the `odoo-frontend-coder` name); the
  wave / nesting-guard guidance is corrected so a depth-2 leaf worker never invokes a
  depth0-only bundle (it writes/reviews directly via OSM tools); hard-pinned `v8-v19` version
  ranges that only meant "all supported" are replaced with open phrasing ("any/all supported
  version", "v8+") while real era boundaries are kept; the README no longer tracks the plugin
  version.

### Removed

- **ollama-delegate (PR #42)** - removed all `mcp__ollama-delegate__*` delegation from the
  plugin and the `ollama_tools` field from every `generator/skill_tool_deps.json` entry (plus
  the `SKILL_OLLAMA_TOOLS` load and the "Ollama-delegate tools" render block in
  `generator/gen_surface.py`). The running agent generates/reviews code itself.

### Fixed

- **Session-pin scope wording (#253, follow-up to server #251/#252)** - corrected the
  `set_active_version` / `set_active_profile` sticky-context description from "per API key"
  to **per live MCP session** (single api-key/`_nosession` fallback for stdio/header-less,
  24h idle TTL, resets on server restart). Fixed at the SSOT
  (`generator/server-surface.json` tool description + `generator/gen_surface.py` legend) and
  regenerated via `make gen` (propagates to `mcp-tool-routing.md`, 12 SKILL.md, 3 snippets),
  plus the manual prose outside the generator (`docs/setup.md`, `docs/personas/dev.md`,
  `odoo-deploy-checklist`/`odoo-frontend-coder` SKILL.md, snippet intros, and the
  `odoo-brl` state-file `schema.md` re-bootstrap note). Prose-only - no tool-surface change
  (tool count stays 24), no client code change.

## [2.5.0] - 2026-06-03

### Added

- **Frontend fidelity (#37)** - make AI-authored Odoo OWL/JS + SCSS correct and lint-compliant
  by construction: an era-sectioned SSOT pitfall catalogue
  (`skills/_shared/odoo-frontend-fidelity.md`, v8-v19+), a write-time OWL grounding checklist
  plus a post-write verify gate (`scripts/verify-frontend.sh`, `scripts/rules/owl-pitfalls.txt`,
  `scripts/odoo-prettierrc.json`), and passing/broken `odoo-frontend-coder` examples.
- **Agent-facing guidance guard** (`tests/test_agent_facing_guidance.py`) - four checks keeping
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
- **Tool-permission grants for file-authoring skills** - removed the `disallowed-tools: Write Edit`
  frontmatter block from the four skills whose own contract is to write deliverables to disk
  (`odoo-brl` → `.odoo-ai/brl/` rtm.csv/cost.json/dag/report.md, `odoo-qa-suite` →
  `.odoo-ai/qa/*.md`, `workflow-runner` → `output_dir` artifacts + checkpoints, `wave` →
  `.odoo-ai/wave/<slug>/plan.md`), which were previously blocked from delivering their output.
- Restored `odoo-coder` / `odoo-frontend-coder` to write/apply code directly (with a patch
  preview before applying), per the README's coder intent ("Coder - Write Odoo backend or
  frontend code", "fix writer … writes the override and shows a patch preview before
  applying") - undoing the v2.4.0 `disallowed-tools: Write Edit` drift that had reduced them
  to copy-paste-only. Removed the block from both skills, added `Write`/`Edit` to the
  `odoo-coder` agent's tool list, and reframed Phase 0 as a patch preview (not a write-block).
  The OSM-unreachable Standalone-first fallback stays paste-only.
- **AI-agent-consumer review follow-ups:**
  - Workflow-harness doc sync - `docs/reference/workflow-harness.md` no longer claims a
    platform-enforced `disallowed-tools: Write Edit` write-block (the gate is now behavioral
    Iron Law + Plan Mode; coders preview a patch then write). Updated the layer diagram,
    enforcement-stack table, and the mechanisms prose.
  - `set_active_version` 'auto'-needs-pin warning - clarified in `generator/server-surface.json`
    (the regeneration SSOT) that the tool needs a CONCRETE version (sentinels rejected), other
    calls reuse the pin via `odoo_version='auto'`, and `'auto'` is only safe AFTER a pin -
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
    signature order - catching `suggest_pattern(...)`, `lint_check(code_chunk)`, and bare
    `cli_help(...)`/`lint_check(...)` calls that omitted the now-required version; fixed all
    the calls it newly caught.
  - Corrected the class-4 SCSS literal in `skills/_shared/odoo-frontend-fidelity.md` to the
    real Odoo source line `calc(#{map-get($spacers, 1 )} / 2)`
    (`calendar_renderer.scss:2`), replacing a fabricated `calc(#{map-get($spacers, 2)} * 2)`.

## [2.4.2] - 2026-06-02

### Build / CI

#### Added

- **`requirements.txt`** - single source of truth for test dependencies (`pytest` + `PyYAML`);
  previously undeclared, causing contributors to install deps ad-hoc and PyYAML-gated
  workflow tests to silently skip (~99 parametrized cases masked by the missing import).
- **`make setup`** - bootstraps `.venv` by probing for Python >= 3.12 (`python3.12` through
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
  truncation - previously 28 descriptions exceeded the cap, forcing Claude to drop
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

- **`wave` skill** - depth-0 multi-subagent git-wave orchestration: integration branch +
  WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate
  + human-confirm merge. Self-spawning, principal-branch-locked, auto-merge never allowed.
  Covers 1-WI minimal through ≥4-WI full plan-artifact (`.odoo-ai/wave/<slug>/plan.md`)
  with topology diagram and disjoint ownership map.
- **`/odoo-semantic-skills:wave-run` command** - thin dispatcher to the `wave` skill;
  accepts optional work-item description, emits plan gate before any branch is created.

## [2.2.0] - 2026-05-31

### odoo-semantic-skills

#### Added

- **`intake` skill** - universal front door for all 9 persona buckets (CEO/strategist,
  consultant, sales AE, pre-sales, marketer, developer, QA, customer-success). Handles
  vague prompts via a 4-tier brainstorm-or-fast-path routing flow, proposes a plan gate
  before any execution skill fires, and is depth-0 only (never spawns subagents).
- **`odoo-brl` skill** - BRL engine for classifying and costing tens-to-thousands of
  business requirements: 4-way classification (CE/EE/Viindoo/Custom), deterministic cost
  lookup, dependency DAG with Kahn topological sort, and checkpoint/resume support for
  large jobs.
- **3 domain workflow YAMLs** - `bid-respond.workflow.yaml`, `discovery-pipeline.workflow.yaml`,
  and `feature-positioning.workflow.yaml` added as composition-runnable workflows using
  the `workflow-runner` skill as the execution harness.
- **Security hardening** - confidentiality guard expanded to cover 8 banned content groups
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
- **Visual UI testing stack** for the `odoo-semantic-skills` plugin - review, debug,
  regression-test, and record a *rendered* Odoo UI in a live browser (complementing the
  existing source-level skills). Four new skills:
  - `odoo-ui-reviewer` - five-lens verdict (aesthetics, functional correctness, runtime
    stability, accessibility, performance) on a rendered screen (slim; paired with the new
    `odoo-ui-reviewer` agent bundle).
  - `odoo-ui-debug` - root-cause a broken/misbehaving UI at runtime (console errors, failed
    requests, blank OWL renders, CSS that renders wrong) and point at the exact override point.
  - `odoo-visual-regression` - screenshot-baseline + diff between two Odoo states (before/after
    an upgrade, module install, theme change, or code edit) with blast-radius assessment.
  - `odoo-demo-recorder` - record an MP4/GIF screen-capture of a scripted Odoo click-path for a
    demo, sales walkthrough, or marketing clip.
- **`odoo-ui-reviewer` agent bundle** (`agents/odoo-ui-reviewer.md`, Sonnet) - drives the
  multi-step browser review with screenshot/console/Lighthouse evidence plus OSM source pointers.
- **Bundled browser MCP servers** (`.mcp.json`) - `chrome-devtools`, `playwright`, and
  `pagecast` (local stdio `npx` servers) load automatically when the plugin is installed,
  powering the visual stack.
- **`/odoo-semantic-skills:setup` command** - one-shot, idempotent, extensible setup for the
  visual workflow. Drives a registry of numbered step scripts (`scripts/setup-steps/`), each
  with a `describe | check | apply` contract: wires the 3 browser MCP servers across Claude
  Code / Codex CLI / Gemini CLI, installs browser dependencies (Node >= 20, Playwright
  Chromium, ffmpeg), auto-allows the browser tool permissions, discovers local Odoo repos into
  `.odoo-ai/instances.toml`, and optionally spins up a declared instance.
- **SessionStart hook** (`hooks/hooks.json` + `hooks/check-setup-deps.sh`) - read-only
  readiness probe that hints `/odoo-semantic-skills:setup` when visual-stack deps are missing;
  silent when everything is ready, never installs or blocks.
- **Shared setup utilities** (`scripts/lib/`) - `config_merge.py` (idempotent cross-runtime MCP
  config merge) and `discover_odoo.sh` (local Odoo instance discovery), reused by the
  setup-step scripts.

### Changed
- Plugin description + keywords bumped to reflect the visual stack - now **26 skill personas +
  3 specialist agents + 6 workflow commands** across engineering, sales, marketing, strategy,
  onboarding, and visual UI testing.
- Documentation counts corrected from `22 skills / 2 agents / 5 commands` to
  `26 skills / 3 agents / 6 commands` across `README.md` and `docs/setup.md`.
- **VERSION bumped** from `2.0.1` to `2.1.0`, kept in sync with the skills plugin's
  `plugin.json.version`.

## [2.0.1] - 2026-05-29

### Fixed
- **Broken docs anchor in `README.md`** - the MCP-resources link pointed at the stale
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
- **Replaced private server repository links** - all references to
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
- `odoo-router` skill - silent disambiguation concierge with 21-row routing table + 4 collision-test cases.
- `odoo-onboard` skill - bootstrap Odoo project context to `.odoo-ai/context.md` (gitignored, portable markdown-bullet schema).
- SSOT generator (`generator/gen_surface.py`) - emits routing matrix + per-skill `## MCP tools` blocks + IDE snippets from `generator/server-surface.json`. Idempotent.
- Skill↔tool dependency map (`generator/skill_tool_deps.json`) + CI assertion (`generator/check_deps.py`) - fails if a skill/agent references a removed server tool.
- Confidentiality pre-commit hook + CI workflow - blocks vault paths and absolute `~/.` references in committed files.
- Multi-runtime smoke test checklist (`tests/smoke/runtime_parity.md`).
- README section "For the small-team Odoo founder" with use cases covering all 8 personas.
- `## Out of Scope` + `## Standalone-first fallback` sections in all 22 skills + 5 of 5 new commands (CI-enforced by `tests/test_skill_format.py`).
- Agent format tests (`test_agent_frontmatter`, `test_agent_depth_rule_guard`, `test_agent_skill_invocation_guard`) covering the 2 active specialist agents.

### Changed
- Plugin description + keywords updated to reflect post-refinement scope.
- 11 existing skills (`odoo-addon-diff`, `odoo-capability-proof`, `odoo-customization-inventory`, `odoo-deprecation-audit`, `odoo-feature-check`, `odoo-feature-highlights`, `odoo-gap-analysis`, `odoo-objection-handler`, `odoo-override-finder`, `odoo-risk-overview`, `odoo-version-diff`) gained `## Out of Scope` + `## Standalone-first fallback` sections.
- `odoo-coder` + `odoo-code-reviewer` skills slimmed (≤100 lines each) into agent+skill bundle pattern; execution detail moved to `agents/<name>.md`.
- `docs/reference/mcp-tool-routing.md` (442 lines) - fully generator-managed, no longer hand-maintained.

### Removed
- `skills/odoo-js-coder/` + `skills/odoo-owl-coder/` (merged into `odoo-frontend-coder`).
- Hardcoded `SKILL_TO_TOOLS` Python dict in generator - replaced by JSON SSOT in `skill_tool_deps.json`.

### Deprecated
- `agents/odoo-upgrade-planner.md` - kept in tree for git history but marked DEPRECATED; users should invoke `/odoo-upgrade-plan-full` slash command instead.

### Fixed
- Generator `description.split(".")[0]` clipping bug (truncated descriptions at inline periods like `@api.depends`, decimal version numbers).
- Confidentiality leak: 3 files referenced an absolute `~/.claude/plans/...` path - replaced with in-repo `docs/refinement-plan-2026-05-28.md`.
- 4 skills had redundant handwritten `## Additional tools (ollama-delegate)` section duplicating generator-managed content - removed.
- Agent bundle tools allowlist missing `set_active_version` - both `odoo-coder` and `odoo-code-reviewer` agents had this fixed (would have caused runtime denial of the first MCP call).
- Marker labels in 5 new B.2 skills renamed from `BEGIN GENERATED TOOLS` to honest `BEGIN MANUAL TOOLS - <name>` (since these skills are in `SKIP_SKILL_DIRS`).

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
- `commands/discovery-summarize.md` was renamed to `commands/discovery-quick.md` (slash command is now `/odoo-discovery-quick` - the skill `odoo-discovery-summarize` retains its name for natural-language invocation).
- Custom modules using `odoo-js-coder` / `odoo-owl-coder` skill names should switch to `odoo-frontend-coder` (handles both legacy and OWL based on detected version).

### Deferred to v1.1.0
- AC-D6: router trigger optimization via `/skill-creator` Mode 5 + `run_loop.py`. The 20-query eval set is authored in `skills/odoo-router/evals/evals.json` (15 cases) + the 5 collision-test cases in `skills/odoo-router/SKILL.md`. Mode 5 requires the Claude Code subprocess API, which is CC-only; multi-runtime parity is verified manually via `tests/smoke/runtime_parity.md` for v1.0.0. Re-runnable in v1.1.0 after multi-runtime smoke is fully executed.
- AC-D8 CI version-sync test: VERSION ↔ plugin.json sync is currently manual. Add a CI assertion in v1.1.0 (e.g., `test_version_sync` in `tests/test_plugin_schema.py`).
- Confidentiality scan marker convention: PR #14 wave-2 removed the file-name allowlist entirely by moving the refinement plan to an internal planning document. v1.1.0 may adopt an opt-in HTML marker convention (e.g., `<!-- confidentiality-exempt: reason -->`) if any future public doc must legitimately reference an internal-only path - currently no such file exists, so defense-in-depth is restored without an allowlist.

## [0.8.0] - 2026-05-21

### Changed (server v0.9.1 surface alignment)
- **`license_notice` output marker** - `describe_module` and `module_inspect(method='summary')` (and the `odoo://{version}/module/{name}` resource) may now emit a `License notice:` line for license-restricted modules. OEEL-1 modules are skipped by default, so the notice is the intentional, non-silent marker that content is withheld - documented as such in the routing matrix so an AI client treats it as expected, not a missing-data bug to retry around.
- **`lint_check(language='xml')` clarified as corpus-level** - the server lints indexed views against the version-exact grammar at index time, exposing server-indexed XML lint findings. The `xml` mode returns those findings for a version and **ignores the `code` argument** (it is not a snippet check). Documented in the `lint_check` routing-matrix entry. No new tools - server tool surface remains 24.

### Changed (server v0.9.0 surface alignment)
- **`view_type` gains `'list'` value** (v18+ alias for `'tree'`) - documented in `view_type`
  arg descriptions for `model_inspect` and `module_inspect` across the routing matrix and all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT).
- **`.less` stylesheet coverage** - `resolve_stylesheet` and `find_style_override` now cover
  CSS, SCSS, and LESS files (LESS targets legacy v8-v11 modules). Updated routing matrix §2
  tool entries, legend, dev persona, and all adapter snippets to read "CSS/SCSS/LESS".

### Added (v0.8 server surface)
- **4 new ORM-validation tools** documented across all adapter snippets (Cursor, Gemini
  Gem, OpenAI Custom GPT), routing matrix §1 & §2, Appendix table, dev persona, and the
  `odoo-coder` / `odoo-code-reviewer` skills. Static checks against the indexed graph that
  let an AI client catch hallucinated field-paths, operators, dependencies, and relation
  targets *before* it emits a domain / `@api.depends` / relational field:
  - **`resolve_orm_chain(model, dotted_path, odoo_version)`** - walks a dotted field path
    (e.g. `partner_id.country_id.code`) hop by hop, returning the terminal field type or a
    `BROKEN` line naming the first unresolved hop.
  - **`validate_domain(model, domain, odoo_version)`** - validates each `(field_path,
    operator, value)` term of a search domain. Operator validity is **version-aware**:
    `parent_of` from v9, `any`/`not any` only from v17, v19 access-rights variants.
  - **`validate_depends(model, method, odoo_version)`** - validates a compute method's
    indexed `@api.depends('a.b', ...)` paths; flags depends on `id` and suggests the closest
    field name for typos. Era1 (v8/v9) surfaces a clear "no @api.depends" note.
  - **`validate_relation(model, field, target_model, odoo_version)`** - asserts a field is a
    many2one/one2many/many2many whose comodel is `target_model` (or a subtype via
    inheritance); reports the actual comodel on mismatch.

### Changed
- **Target server v0.8 tool surface (20 → 24 tools).** Mirrors server v0.8.0. `tools/list` now reports 24 tools. Version references across README,
  routing matrix, dev persona, snippets, and setup docs bumped v0.7 → v0.8.

### Dependencies
- The 4 ORM-validation tools require server **v0.8.0**. `validate_depends`
  additionally requires a server-side backfill operation (see server docs) - until it runs,
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
  `entity_lookup` (kind=`model`/`field`) - restrict results to declarations from a
  specific module.
- **`kind` filter** on `model_inspect` (method=`fields`) - filter fields by type
  (e.g. `'many2one'`).
- **`view_type` filter** on `model_inspect` (method=`views`) and `module_inspect`
  (method=`views`) - filter by view type (e.g. `'form'`/`'tree'`).
- **`bound_model` filter** on `module_inspect` (method=`owl`) - restrict OWL components
  to those bound to a specific model.
- **`era` filter** on `module_inspect` (method=`js`) - filter JS patches by era
  (`era1`/`era2`/`era3`).
- **`noqa` support in `lint_check`** - inline `# noqa: RULE_ID` (or bare `# noqa`) in
  the `code` argument suppresses findings on that line. Documented in routing matrix,
  all three adapter snippets, and both affected skills (`odoo-coder`,
  `odoo-code-reviewer`).

### Changed (v0.6 migration - also part of this release)
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
  the pin step (fail-soft - CI stays green) when the HEAD SHA matches.
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
