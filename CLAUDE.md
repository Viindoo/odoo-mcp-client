# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`odoo-mcp-client` is the **MIT-licensed client layer** for the Odoo Semantic MCP server
(`odoo-semantic.viindoo.com`, AGPL, separate repo). It is a **monorepo of two Claude Code
plugins** under `plugins/`:

- **`odoo-ai-agents`** - the workforce toolkit: skills + specialist agents + workflow commands,
  the SSOT generator, declarative workflows, hooks, setup steps, and IDE snippets. Declares
  `odoo-semantic-mcp` as a dependency.
- **`odoo-semantic-mcp`** - the thin MCP connection plugin: registers the `odoo-semantic` server
  and ships `/odoo-semantic-mcp:connect`.

There is almost no application logic here. The repo is a **routing + orchestration layer made of
Markdown** (skills/agents/commands are prose with YAML frontmatter); all knowledge and computation
live on the OSM server. The Python under `generator/` and `tests/` exists to *validate and generate*
that Markdown, not to run at user time.

## Commands

`make` targets auto-bootstrap `.venv` (Python >= 3.12 required) on first use.

```bash
make setup              # create .venv + install requirements.txt (one-time)
make test               # full pytest suite (tests/)
make validate           # claude plugin validate (if CLI present) + schema/format pytest + workflow check
make gen                # regenerate SSOT-derived artifacts (see "SSOT generator" below)
make gen-check          # run gen, then fail if it produced any git diff (CI idempotency gate)
make deps-check         # assert every skill->tool reference points at a live tool
make workflows-check    # validate workflows/*.workflow.yaml against the schema
make orchestration-check # capability/contract lint (warn-first; ORCH_STRICT=1 to enforce)
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
check, and orchestration lint on every PR. Match these locally before pushing.

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

### Three layers, distinguished by name morphology

Names encode role so a router can tell the layers apart even when a name appears bare:

- **Skill** = capability noun (`-review`, `-analysis`, `-coding`, `-handling`). Front doors that
  fire on user intent (see the `description` frontmatter). Live in `skills/<name>/SKILL.md`.
- **Agent** = actor noun with `-er/-or/-ist` suffix (`odoo-coder`, `odoo-code-reviewer`). The
  executor a skill dispatches. Listed in `plugin.json` `agents`.
- **Command** = imperative verb-object (`odoo-run-brl`, `odoo-plan-upgrade`). Frontmatter `name`
  **must equal the filename**. Listed in `plugin.json` `commands`.

A skill and the agent it dispatches must have **different** names (capability vs actor). All
Odoo-specific names carry the `odoo-` prefix; `wave` and `workflow-chaining` are the only
unprefixed (domain-agnostic) names. Enforced by `tests/test_naming_consistency.py`.

### Skill descriptions drive routing - and are budget-capped

A skill's `description` frontmatter is what makes it trigger. Keep it **under 1024 characters**
(Claude truncates longer ones out of the listing, silently breaking routing). When trimming, cut
duplicate trigger phrases and examples first; preserve the `route to ...` / `DO NOT trigger` clauses.
Enforced by `test_skill_format.py` + `test_skill_description_budget.py`. Every skill/workflow the
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

No environment-specific, machine-specific, or Viindoo-internal data in committed files (no vault
paths, personal emails, absolute `~/.` paths, instance hosts/dbs/keys, or hardcoded version
ranges/counts in agent-facing prose). Install the pre-commit guard once:
`git config --local core.hooksPath .githooks/`. It scans staged blobs against generic structural
patterns plus untracked `.githooks/patterns.local`. A confidentiality-scan CI job also runs.

## Contributions

Branch from `master`, keep PRs to one logical change, run `make validate && make test && make gen-check`, and
**sign off every commit** (`git commit -s` - DCO is required). Full contributor and release/
marketplace-pinning details are in `CONTRIBUTING.md`.
