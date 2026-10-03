# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`odoo-mcp-client` is the **MIT-licensed client layer** for the Odoo Semantic MCP server
(`odoo-semantic.viindoo.com`, AGPL, separate repo). It is a **monorepo of three Claude Code
plugins** under `plugins/`:

- **`odoo-ai-agents`** - the workforce toolkit: skills + specialist agents + workflow commands,
  the SSOT generator, declarative workflows, hooks, setup steps, and IDE snippets. Declares
  `odoo-semantic-mcp` as a dependency.
- **`odoo-semantic-mcp`** - the thin MCP connection plugin: registers the `odoo-semantic` server
  and ships `/odoo-semantic-mcp:connect`.
- **`git-toolkit`** - a domain-agnostic, Apache-2.0 git + GitHub toolkit for AI agents: one
  front-door skill (`git-ops`) + 4 agents that run git/github work safely in a delegated context.
  Declares `github` as a dependency; not under the SSOT generator.

Most of the repo is a **routing + orchestration layer made of Markdown** (skills/agents/commands
are prose with YAML frontmatter), and all Odoo source knowledge lives on the OSM server. The
exception is a small **local runtime** that `odoo-ai-agents` ships and runs at user time: the
instance allocator (`plugins/odoo-ai-agents/scripts/lib/allocator.py` + siblings, which leases
databases/ports and anchors each lease to the owning session) and the `odoo-local` stdio MCP server
that wraps it (`scripts/mcp/odoo_local_server.py`). The Python under `generator/` and `tests/`
exists to *validate and generate* the Markdown, not to run at user time.

## Commands

`make` targets auto-bootstrap `.venv` (Python >= 3.12 required) on first use.

```bash
make setup              # create .venv + install requirements.txt (one-time)
make test               # full pytest suite (tests/)
make validate           # claude plugin validate (if CLI present) + schema/format pytest + workflow + orchestration check, both STRICT/enforced
make gen                # regenerate SSOT-derived artifacts (see "SSOT generator" below)
make gen-check          # run gen, then fail if it produced any diff (CI idempotency gate)
make deps-check         # assert every skill->tool reference points at a live tool
make workflows-check    # validate workflows/*.workflow.yaml against the schema (warn-first standalone; WORKFLOWS_STRICT=1 to enforce locally - `make validate` always runs it strict)
make orchestration-check # capability/contract lint (warn-first standalone; ORCH_STRICT=1 to enforce locally - `make validate` always runs it strict)
```

Run a single test (use the venv directly):

```bash
.venv/bin/python -m pytest tests/test_skill_format.py -q
.venv/bin/python -m pytest tests/test_naming_consistency.py::<test_name> -q
```

Load a plugin from this checkout without the marketplace:

```bash
claude --plugin-dir ./plugins/odoo-ai-agents      # skills + agents + commands + MCP
claude --plugin-dir ./plugins/odoo-semantic-mcp   # MCP connection + connect command
```

CI (`.github/workflows/validate.yml`) runs `pytest tests/`, `check_deps.py`, the gen-idempotency
check, and the orchestration + workflow-schema lints (both STRICT/enforced) on every PR. Match
these locally with `make validate` before pushing.

## Architecture you must understand before editing

### SSOT generator - never hand-edit generated regions

`generator/server-surface.json` (+ `skill_tool_deps.json`, and the `.mcp.json` files) are the
**single source of truth** for the MCP tool surface. `generator/gen_surface.py` and
`gen_mcp_manifests.py` emit:

- the `## MCP tools` section of each `skills/*/SKILL.md`,
- the IDE snippets (`snippets/cursor-rules.md`, `openai-gpt-instructions.md`, `gemini-gem-instructions.md`),
- the Codex/Gemini MCP manifests, the orchestration map, and digest.

Generated content lives **between `<!-- BEGIN GENERATED TOOLS -->` / `<!-- END GENERATED TOOLS -->`
markers**. Editing inside the markers is wasted work - `make gen-check` (and CI) will revert it.
To change tool descriptions, edit the JSON SSOT and run `make gen`, then commit the regenerated
output. The generator is idempotent: a clean tree must produce zero diff.

### The `odoo-local` MCP server (local runtime)

`plugins/odoo-ai-agents/.mcp.json` registers `odoo-local`, a stdio MCP server
(`scripts/mcp/odoo_local_server.py` + `scripts/mcp/odoo_local/`) exposing the lease, instance,
translation-export and catalog tools agents call as `mcp__plugin_odoo-ai-agents_odoo-local__<tool>`. Rules:

- **Claude Code only.** Its command resolves `${CLAUDE_PLUGIN_ROOT}`, so `gen_mcp_manifests.py`
  excludes it from the Codex/Gemini manifests; those runtimes use the allocator CLI.
- **stdlib only**, and the entry point stays parseable by old Python 3 (it reports
  `PYTHON_TOO_OLD` instead of failing to start).
- **Tool names, descriptions and schemas live in the server** (`tools_*.py` `registry.add(...)`) -
  they are the SSOT and are NOT generated from `generator/server-surface.json` (that file is the
  OSM surface only). The allocator owns every rule; the server only translates.
- **`LOCAL_SERVERS` in `scripts/lib/plugin_mcp_servers.py` is the SSOT** for which bundled servers
  are local; the browser permission prefixes, the manifest generator and
  `hooks/auto-approve-local.sh` all read it. Add a local server there and in `.mcp.json` together.
- **Threading.** A tool registered `long_running=True` (it can block on a build, a probe, a server
  stop or a database drop) runs on a thread of its own, so it never queues behind another call;
  every other tool runs on a small bounded pool. Register any tool that can block as long-running,
  and make a tool that only waits poll `protocol.cancel_event()` so a cancelled call stops early.
- **Several plugin versions share one machine-global lease registry** (each session keeps the
  allocator it started with): rows must stay safe for older readers (`INSTANCE-ALLOCATION-RECLAIM.md`
  §7.4, `tests/test_allocator_cross_version.py`), and users restart sessions after updating.
- **Odoo facts come from the checkout, deployment facts from the catalog.** Every series-dependent
  fact (option spellings, the demo default, the core `--load` default, the supported Python range,
  the translation-export command line) is read from the Odoo checkout's source TEXT by
  `scripts/lib/odoo_source_facts.py` (never imported, never executed) - never keyed on a series
  number or kept in a hand-written table, so a new Odoo series needs no plugin edit. A fact the
  checkout does not state is refused (`ODOO_SOURCE_FACT_UNKNOWN`), never guessed. Which addons a
  site loads server-wide is a deployment fact: the catalog row's `server_wide_modules`, proposed and
  operator-confirmed by `/odoo-ai-agents:odoo-setup` (step `46-server-wide`, or `refresh`).
- **The tools apply the build facts; agents never compose them.** `instance_build`,
  `instance_serve` and `instance_i18n_export` pass `--load` (core default + the row's list; an agent
  adjusts it per call only through `server_wide` {exclude, include}, never through `extra_args`, and
  the lease and catalog stay unchanged); `instance_build` / `instance_serve` also pass
  `--load-language` (`en_US` + `languages`) and the series' demo flag (from `demo`, on `init` only),
  and `extra_args` refuses those flags. `instance_i18n_export` runs Odoo's own exporter (`.pot`
  first, then one `.po` per language, from one database). One build or export runs on a database at a time (`DATABASE_BUSY`).
- **Tool-launched Odoo never reads `~/.odoorc`.** Every `odoo-bin` the scripts launch reads a
  generated config file, named by `-c` and by `$ODOO_RC` (`scripts/lib/odoo_cli_facts.sh`
  `odoo_isolated_rc_env` - where Odoo loads its default rc file at import time, `-c` alone does not
  keep it out). The Postgres password comes only from `ODOO_PG_PASSWORD` or `~/.pgpass`; the plugin
  never writes one.
- **Hooks gate what a subagent does with a lease.** `hooks/hooks.json` registers exactly FOUR
  PreToolUse hard denies - coordinator source writes, an unowned lease mutation, a
  `SubagentHandback` while a lease the subagent obtained is still live and not forwarded
  (`block-handback-with-live-lease.sh`: a handback delivers the report before SubagentStop, so the
  SubagentStop teardown gate alone came too late; both share `hooks/teardown-check.sh`), and a
  browser capture whose destination is relative or outside the capture area - `<state root>/projects`
  plus the override dirs, never the rest of the state root (`block-capture-outside-state-root.sh`,
  decided by `scripts/lib/capture_paths.py`). Its
  `description` states that count and tests pin it - a new deny updates both. Every hook that reads
  a subagent's report reads it through `hooks/final-report.sh` (the `SubagentHandback` message, else
  the final message).
- Agent-facing prose names the tool and states the rule; it never restates a tool's schema, flags
  or error codes. Human reference (tool -> allocator verb index, CLI, error codes, liveness model):
  `plugins/odoo-ai-agents/docs/reference/INSTANCE-ALLOCATION-API.md` and
  `INSTANCE-ALLOCATION-RECLAIM.md`.

### Three layers, distinguished by name morphology

Names encode role so a router can tell the layers apart even when a name appears bare:

- **Skill** = capability noun (`-review`, `-analysis`, `-coding`, `-handling`). Front doors that
  fire on user intent (see the `description` frontmatter). Live in `skills/<name>/SKILL.md`.
- **Agent** = an actor noun, typically with an `-er/-or/-ist` suffix (or an actor noun without
  one, e.g. `odoo-instance-ops`, `odoo-solution-architect`). The executor a skill dispatches.
  Listed in `plugin.json` `agents`.
- **Command** = imperative verb-object (`odoo-run-brl`, `odoo-plan-upgrade`). Frontmatter `name`
  **must equal the filename**. Listed in `plugin.json` `commands`.

A skill and the agent it dispatches must have **different** names (capability vs actor). All
Odoo-specific names carry the `odoo-` prefix; `run-harness` and `workflow-chaining` are the only
unprefixed (domain-agnostic) names. Enforced by `tests/test_naming_consistency.py`.

**Before creating or modifying any skill or agent, read `docs/authoring-skills-and-agents.md`** -
the in-repo authoring guide (frontmatter, required body sections, naming morphology, the generated
tools block, model-tier selection, and the pre-commit gates), grounded in Anthropic's official
docs and this repo's stricter, test-enforced conventions.

### Skill descriptions drive routing - and share one listing budget

A skill's or command's `description` frontmatter is what makes it trigger, and every
model-invocable one is shown to the model on every turn in ONE skill listing that Claude Code caps
at 1% of the context window (as it counts it: 4 chars per token, so 8000 chars on a 200k window).
Over the cap the harness keeps the names but drops descriptions - of this plugin's skills, other
plugins' and the user's own - so the binding limit is the plugin's AGGREGATE, not any one entry.
Rules (full guidance: `docs/authoring-skills-and-agents.md`):

- **English only, ASCII.** No trigger lists in other languages; the model maps a user's language
  to an English description.
- **Meaning first, length follows.** State what the skill does, its core trigger intent, and a
  route-out only where a neighbour is genuinely confusable. No paraphrase lists, examples, process
  detail or marketing wording - those belong in the body.
- **The aggregate stays inside the budget.** A new skill pays for itself by tightening others, never
  by raising the budget. A command that is purely a user shortcut for a still-visible skill may set
  `disable-model-invocation: true` (it leaves the listing), unless an orchestrator skill or workflow
  names it.

Enforced by `test_skill_description_budget.py` (aggregate budget, English-only, the 1024-char field
maximum, hidden entries never routed to) and `test_skill_format.py`. Every skill/workflow the
`odoo-intake` router references must exist (`test_odoo_intake_quote_sync.py`).

### Workflows are declarative YAML

`workflows/*.workflow.yaml` are SSOT definitions executed at runtime by the `workflow-chaining`
skill (a runner, not codegen). Schema is in `workflows/_schema.md`; validate with
`make workflows-check`. They chain skills/agents into phases (Pipeline, Producer-Reviewer, etc.).

### OSM-first precedence (agent-facing prose contract)

Agent/skill prose must assert: **Odoo Semantic MCP is the PRIMARY source** for Odoo
source/structure (indexed, cross-version, inheritance-resolved, checkout-free); reading the Odoo
codebase with Read/Grep is the **FALLBACK**, only when OSM is incomplete or unavailable. Never
invert this. OSM is STATIC (no live records) - live-data requests need a separate live Odoo MCP.
Keep this in sync with the server's `INSTRUCTIONS` SSOT. Guard: `tests/test_disambiguation.py`.

### `odoo-semantic` naming policy

`odoo-semantic` appears in many forms with strict meanings - see the table in `CONTRIBUTING.md`
("Naming policy"). Briefly: `odoo-semantic-mcp` = the MCP plugin; `odoo-ai-agents` = the skills
plugin; `Odoo Semantic`/`OSM` = the brand; `` `odoo-semantic` `` in backticks = the runtime server
id (config only); `mcp__odoo-semantic__*` = the tool-call prefix. A bare `odoo-semantic` token
outside those contexts is a bug. Enforced by `tests/test_naming_consistency.py`.

### Versioning - VERSION is SSOT, kept in lockstep

`VERSION` is the single source of truth and must equal `plugins/odoo-ai-agents/.claude-plugin/plugin.json`
`version` (`test_version_consistency.py` fails CI otherwise). The `odoo-semantic-mcp` plugin versions
independently. Prefer `make bump` (auto-classifies patch/minor/major from commits since VERSION last
changed and cuts the CHANGELOG); `make bump-dry` previews. If a human names a specific
version/level, run `scripts/bump-version.sh <that>` instead. Level policy: fix/refactor/docs ->
**patch** (the default, do not skip); new feature/skill/agent/command or `feat:` -> **minor**;
breaking change -> **major**.

## This repo is public - confidentiality

No environment-specific, machine-specific, or Viindoo-internal data in committed files: no vault
paths, personal emails, absolute `~/.` paths, instance hosts/dbs/keys. Install the pre-commit guard
once: `git config --local core.hooksPath .githooks/`. It scans staged blobs against generic
structural patterns plus untracked `.githooks/patterns.local`. A confidentiality-scan CI job also
runs.

Separately - a DIFFERENT guard, often confused with the one above: **no hardcoded Odoo version
ranges/counts in agent-facing prose.** The pre-commit hook does NOT check this; it is enforced by
`generator/check_orchestration.py` rules 17 (`[gen-prose]`) and 18 (`[version-claim]`), which gate
`make validate` and CI. Only the boundary-SSOT files listed in that script may spell a version;
everywhere else points at them.

## Contributions

Branch from `master`, keep PRs to one logical change, run `make validate && make test && make
gen-check`. **Never hand-run git in this repo**: route EVERY git operation - staging, commit, push,
branch, merge - including your own one-line edits and repo self-maintenance, through the
`git-toolkit:git-ops` skill, which detects the commit convention and applies the required DCO
sign-off for you. This binds the main agent and every skill/agent alike. Bounded reads on the
`git-delegation.md` "Bounded-read allowlist" MAY run inline; every git MUTATION - staging, commit,
push, branch, merge, and everything else in this paragraph - routes through `git-toolkit:git-ops`.
The equivalent rule for
dispatched skills/agents lives in `plugins/odoo-ai-agents/snippets/git-delegation.md` (Universal
rule); keep the two in lockstep. Human contributor / release / marketplace-pinning details:
`CONTRIBUTING.md`.
