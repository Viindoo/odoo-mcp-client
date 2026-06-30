# Roadmap

This roadmap covers the **client** layer (this repository). The semantic backend has
its own roadmap, accessible after registration at
[odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/).
Items are directional, not commitments, and reflect publicly announced milestones only.

## Now

- **Tool-surface parity with server v0.13.1 (25 tools)** - skills and snippets
  reference the full surface: 25 tools incl. the superset trio (`model_inspect`,
  `module_inspect`, `entity_lookup`) + `profile_inspect` plus the 7 `odoo://` MCP Resources
  (ADR-0028 / ADR-0029 / ADR-0030).
- **Marketplace publishing pipeline** - automatic SHA pinning into
  `Viindoo/claude-plugins` on each release.

## Recently shipped

- **4-tier orchestration: planning split from execution** (v4.0.0) - a dedicated
  `odoo-planning` skill (with the `odoo-planner` agent) now authors the full-lifecycle
  EXECUTION plan after solution-design: a wave-batched module-DAG, the integration cadence,
  each module/stage wired to a skill, and the lifecycle code -> review -> doc -> PR -> monitor ->
  merge. `run-harness` (the sequencer, renamed from `run-driver`) walks it; the internal
  `odoo-wave` git-executor lands each coding wave-layer; and the new `odoo-pr-monitoring` skill
  watches the opened PR to merge (CI/review poller, CI failures route to `odoo-debug`, the
  L2-merge-gate). The standalone `/odoo-run-wave` slash command was removed in this major.
- **Git-wave execution** (v2.3.0; re-architected v4.0.0) - the git-executor that lands multiple
  work-items as one reviewed, squashed PR without touching the principal branch: integration
  branch + per-WI worktrees + cherry-pick + end-of-wave review + 1 PR + squash + tree-identity
  gate. In v4.0.0 it became the internal, consume-only `odoo-wave` skill driven by `run-harness`;
  it invokes `odoo-coding` per work-item and stops at the L2-squash-gate, with merge owned by
  `odoo-pr-monitoring`. Principal-branch-locked; auto-merge never allowed.
- **Workflow harness + `odoo-intake` front door** (v2.2.0) - three-layer architecture (Entry/Intake,
  Workflow, Execution). `odoo-intake` replaces `odoo-router` as the universal front door: brainstorms
  when vague, fast-paths when clear, always gates with a Proposed Plan before dispatching. The
  generic `workflow-chaining` executes `*.workflow.yaml` declarative workflows - adding a new
  workflow is one YAML file, no orchestration code. 10 workflows shipped at launch.
- **BRL engine** (v2.2.0) - `odoo-brl` skill + `/odoo-run-brl` command for classifying and
  costing tens-to-thousands of business requirements: 4-way classification, deterministic cost
  lookup, dependency DAG with Kahn topological sort, and checkpoint/resume for large jobs.
- **Support triage + QA suite skills** (v2.2.0) - `odoo-support-triage` (ticket classification,
  root-cause hint, customer-ready resolution draft) and `odoo-qa-suite` (test cases, pre-deploy
  checklist, bug triage pipeline) expand the specialist coverage to 30 skills.
- **Visual UI testing stack** (v2.1.0) - review, debug, regression-test, and record a
  *rendered* Odoo screen in a live browser: skills `odoo-ui-review`, `odoo-ui-debugging`,
  `odoo-visual-regression`, `odoo-demo-recording`, the `odoo-ui-reviewer` agent, and three
  bundled browser MCP servers (`chrome-devtools`, `playwright`, `pagecast`).
- **Unified `/odoo-ai-agents:odoo-setup`** (v2.1.0) - one-shot, idempotent, extensible
  setup that wires the browser MCP servers across Claude / Codex / Gemini, installs browser
  deps, auto-allows tool permissions, and discovers + optionally spins up a local Odoo
  instance; plus a SessionStart readiness hint.
- **Continue.dev + JetBrains snippets** - `snippets/continue-dev-mcp.yaml` and
  `snippets/jetbrains-mcp-config.md` now join the existing Cursor / ChatGPT / Gemini
  snippets.

## Next

- **Audit residual legacy-tool mentions** - the server already removed the 10 legacy
  `resolve_*` / `list_*` tools at v0.6 (done); sweep skills and snippets for any
  remaining references beyond the intentional "Supersedes removed …" notes in the
  superset tool descriptions.

## Later / exploring

- **OS-level screen recording** for `odoo-demo-recording` - capture beyond the browser
  viewport (native windows, OS chrome) for richer demo clips.
- **Pin browser MCP versions** - replace the `@latest` tags in the bundled `.mcp.json`
  with pinned versions for reproducible visual runs.
- **Marketplace entry for the visual stack** - surface the visual skills/setup as a
  discoverable capability in `Viindoo/claude-plugins`.
- **JetBrains plugin wrapper** - a thin native wrapper once demand is clear.
- **PyPI distribution** - `pip install`-able client for non-Claude IDEs.
- **Decouple client from server tool surface** - intent-only skill descriptions +
  build-time generator that reads the server's `tools/list` response and routing
  matrix to emit adapter snippets (Cursor/Gemini/OpenAI) automatically. Eliminates
  manual routing duplication; the server-side MCP Prompt becomes the SSOT for routing
  logic, and the client never needs a hand-rolled classifier agent again.

## Out of scope for this repo

- Indexer, graph/vector storage, MCP server logic, billing, and the web UI all live
  in the AGPL server repository.

Have an idea? Open a [feature request](https://github.com/Viindoo/odoo-mcp-client/issues).
