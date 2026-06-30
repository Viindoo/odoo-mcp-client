# Authoring skills and agents in this repo

How to author or modify skills and agents in `odoo-mcp-client` the right way - grounded
in Anthropic's official docs AND this repo's own (stricter, test-enforced) conventions.
Where the two disagree, **the repo rule wins**; the generic guidance is noted as background.

This repo is **public** and almost entirely Markdown (skills/agents/commands are prose with
YAML frontmatter; the Python under `generator/` and `tests/` only validates and generates that
Markdown). Treat every file you touch as shipped product copy: ASCII hyphens only, no
machine/instance/internal data.

---

## 1. Use the official tooling first

Before hand-writing a skill or agent, reach for the maintained authoring tools - they encode
the latest Anthropic structure and run evals for you:

- **Skills** - the `plugin-dev` plugin's **`skill-development`** skill (structure, progressive
  disclosure, description-writing) and the **`skill-creator`** plugin (scaffold, eval, iterate,
  optimise a description for triggering). Review a finished skill with the `skill-reviewer` agent.
- **Agents** - the `plugin-dev` plugin's **`agent-development`** skill and the **`agent-creator`**
  agent (scaffold frontmatter + system prompt + triggering examples). Validate with the
  `plugin-validator` agent.

These produce a generic, Anthropic-shaped artifact. You then conform it to the repo rules in
sections 3-7 below and run the gates in section 8. The tooling does not know this repo's stricter
caps (1024-char description, required body sections, naming morphology, the generated tools block),
so the gates are non-optional.

## 2. Official Anthropic references

- Skills: https://code.claude.com/docs/en/skills
- Skills best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Subagents (Claude Code): https://code.claude.com/docs/en/sub-agents
- Subagents (Agent SDK): https://docs.claude.com/en/api/agent-sdk/subagents
- Plugins: https://code.claude.com/docs/en/plugins

## 3. Skill authoring

A skill is one directory `plugins/odoo-ai-agents/skills/<name>/SKILL.md` = YAML frontmatter +
Markdown body. Generic Anthropic guidance: keep `SKILL.md` concise (suggested < 500 lines) and
push detail into supporting files (`references/`, `scripts/`) that load on demand (progressive
disclosure).

**Frontmatter (repo-enforced):**

- `name` is **required here** (generic docs make it optional/defaulted) and **must equal the
  directory name** - `tests/test_skill_format.py`.
- `description` is required and is what drives auto-triggering - write it trigger-rich ("what it
  does + when to use", best use case first), with explicit `route to ...` / `DO NOT trigger`
  disambiguation clauses.
- **Description cap = 1024 chars** (`tests/test_skill_description_budget.py`, skills only). This is
  Anthropic's documented maximum length for a skill `description` field (Agent Skills best-practices)
  - a real authoring limit, not an arbitrary buffer. A SEPARATE, larger mechanism also exists: Claude
  Code truncates the skill-listing text - the combined `description` + `when_to_use` - at 1536 chars
  (`skillListingMaxDescChars`, see the skills doc below); keeping the field under 1024 clears that too.
  The CLI does not hard-reject at 1024 (the field-max is enforced at skill upload), so the test is
  what guarantees it here. When trimming, cut duplicate trigger phrases and examples first; preserve
  the routing/disambiguation clauses.
- The description must **not end in `.`, `!`, or `?`** (`tests/test_skill_format.py`,
  marketplace style).

**Required body sections** (`tests/test_skill_format.py` asserts all three exist):

- `## Persona`
- `## Out of Scope`
- `## Standalone-first fallback` (or `## Standalone fallback`)

**The generated `## MCP tools` block - never hand-edit.** Tool listings live between
`<!-- BEGIN GENERATED TOOLS -->` and `<!-- END GENERATED TOOLS -->` markers and are emitted by
the SSOT generator. Edits inside the markers are reverted by `make gen-check` and CI. To change a
skill's tool surface, edit `generator/skill_tool_deps.json` (and `server-surface.json` for tool
descriptions), then `make gen` and commit the regenerated output. See section 6 and CLAUDE.md
"SSOT generator".

**OSM-first prose contract.** Any tool-routing prose must assert that **Odoo Semantic MCP (OSM)
is the PRIMARY** source for Odoo source/structure (indexed, cross-version, inheritance-resolved,
checkout-free) and that reading the codebase with Read/Grep is the **FALLBACK**, only when OSM is
incomplete or unreachable. Never invert this. OSM is STATIC (no live records). Keep prose
**version-agnostic** (no hardcoded version range/count) and **capability-described** (refer to a
"live Odoo MCP exposing `read_record`/`search_records`" by capability, not a product name). Guard:
`tests/test_disambiguation.py`. Full rules: CONTRIBUTING.md "Agent-facing prose".

**Fan-out / model tier.** If a skill dispatches subagents, it must reference
`skills/_shared/concurrency-guard.md` for the concurrency envelope (Mode A / Mode B) and the
"Model-tier selection" SSOT rather than restating the numbers. A skill whose orchestration
`handoff` is `fork` or `send-message` must document a Tier-C (fresh-spawn) fallback - reference
`snippets/context-handoff-protocol.md` (`tests/test_chp_hardening.py`).

## 4. Agent authoring

An agent is one file `plugins/*/agents/<name>.md` = YAML frontmatter + Markdown body, and the two
halves have **different readers** - keep their content separate (this mirrors Anthropic's subagent
contract):

- **Frontmatter `description` = routing metadata.** Read by the orchestrator at routing time to
  decide *whether to delegate*. Put triggers, "use this agent when ...", and worked `<example>`
  scenarios here. Required fields: `name`, `description`, `model` (all three enforced by
  `tests/test_skill_format.py`). Description must not end in `.`/`!`/`?`.
- **Body = the agent's system prompt.** Read by the running agent at startup; write it in the
  **second person** ("You are ..."). It contains only what the agent needs to *do the work* -
  role, operating procedure, runtime constraints, output contract.

**Do NOT put a `## When to invoke` heading (or any "when to use me" routing section) in the
body** - routing belongs in `description`; a routing heading in the body pollutes the system
prompt with text the running agent cannot act on. Banned by `tests/test_agent_body_convention.py`.
Genuine runtime constraints (read-only, one SHA per instance, never spawn subagents) belong in the
role intro or a constraints section of the body, not under a routing heading.

**No `tools:` allowlist.** Repo convention: agents omit the frontmatter `tools:` key so they
inherit the full (drift-proof) tool surface; the harness depth cap is the only nesting net.
Enforced by `tests/test_skill_format.py` (`test_agent_frontmatter`). This is intentionally
stricter than the generic Anthropic option to allowlist tools. (Generic background: Anthropic lets
you omit `Agent` from `tools`/`disallowedTools` to stop an agent spawning subagents; here you
state that as a body constraint instead.)

**Model is a default, overridden per dispatch.** Frontmatter `model:` (an alias) is only the
default tier. The dispatcher sets the launch `model` from the dispatched work's complexity - see
`skills/_shared/concurrency-guard.md` "Model-tier selection" (haiku = mechanical, sonnet =
default/medium, opus = heavy/wide blast radius, fable = ultra-complex + human-confirm). Do not
hardcode a tier in prose; reference that SSOT.

**Handoff = fork requires a Tier-C note.** If an agent or its skill uses `handoff: fork` /
`send-message`, the consuming skill must document the Tier-C fresh-spawn fallback (see section 3
and `tests/test_chp_hardening.py`).

CONTRIBUTING.md "Agent format" is the prose SSOT for this section.

## 5. Naming morphology (skill vs agent vs command)

Names encode role so a router can tell the layers apart even when a name appears bare
(`tests/test_naming_consistency.py`; CONTRIBUTING.md "Naming convention"):

- **Skill = capability noun** - a noun phrase (`-review`, `-analysis`, `-audit`, `-diff`,
  `-overview`) or gerund (`-coding`, `-handling`). Never an actor suffix; never a bare imperative.
- **Agent = actor noun** - typically with an `-er` / `-or` / `-ist` suffix (`odoo-coder`,
  `odoo-code-reviewer`), or an actor noun without one (e.g. `odoo-instance-ops`,
  `odoo-solution-architect`).
- **Command = imperative verb-object** (`odoo-run-brl`, `odoo-plan-upgrade`); frontmatter `name`
  **must equal the filename**.
- **Prefix `odoo-`** on every Odoo-specific skill/agent/command. The only unprefixed
  (domain-agnostic) names are `run-harness` and `workflow-chaining`.
- A skill and the agent it dispatches **must have different names** (capability vs actor) - e.g.
  skill `odoo-code-review` dispatches agent `odoo-code-reviewer`.

## 6. Registration and regeneration

- **Register the file.** Add a new agent to the plugin's `.claude-plugin/plugin.json` `agents`
  array and a new command to `commands`. Skills are discovered by directory, but the
  `odoo-intake` router and workflows must be able to reach them.
- **Declare the tool surface.** A skill's MCP tools come from
  `generator/skill_tool_deps.json` (with descriptions in `generator/server-surface.json`); bumping
  a tool's `min_server_version` lives here too.
- **Regenerate.** Run `make gen` after any SSOT change. It rewrites the `## MCP tools` blocks, the
  IDE snippets, the Codex/Gemini MCP manifests, the digest, and the **ORCHESTRATION-MAP** (the map
  is 100% generated - never hand-edit it). `make gen` must be idempotent: a clean tree produces
  zero diff (`make gen-check` enforces this in CI).

## 7. Confidentiality and style (public repo)

- ASCII hyphen `-` (U+002D) only - no en/em/figure dashes (enforced for several snippets, e.g.
  `tests/test_chp_hardening.py`).
- No vault paths, personal emails, absolute `~/.` paths, instance hosts/dbs/keys, or hardcoded
  Odoo version ranges/counts in agent-facing prose. Install the guard once:
  `git config --local core.hooksPath .githooks/`.

## 8. Gates before commit

Run the full local gate (same as CI) before pushing:

```bash
make validate          # plugin schema + skill frontmatter + description cap + workflow schema
make test              # full pytest suite (naming, format, body convention, CHP, disambiguation, ...)
make gen-check         # regenerate SSOT artifacts, fail on any diff (idempotency)
make deps-check        # every skill->tool reference points at a live tool
make workflows-check   # workflows/*.workflow.yaml vs schema
make orchestration-check  # capability/contract lint (warn-first; ORCH_STRICT=1 to enforce)
```

Then: **sign off every commit** (`git commit -s` - DCO required) and keep the PR to one logical
change. Bump policy (CONTRIBUTING.md "Versioning"): a new skill/agent/command is a **minor**;
docs/fix/refactor is a **patch**. Prefer `make bump` (auto-classifies); never hand-edit version
fields.

## 9. Checklist: adding a new agent

1. Scaffold with the `agent-creator` agent / `agent-development` skill.
2. Frontmatter: `name`, `description` (routing metadata - triggers + `<example>`s, no trailing
   `.`/`!`/`?`), `model` (default tier). Omit `tools:`.
3. Body: second-person system prompt - role, procedure, runtime constraints, output contract.
   **No `## When to invoke`** and no routing section.
4. Name it as an actor noun (`-er`/`-or`/`-ist`, `odoo-` prefix), different from the dispatching
   skill.
5. Register it in the plugin's `plugin.json` `agents` array; if it dispatches via `fork`, wire the
   Tier-C fallback in the consuming skill.
6. `make gen` (if you touched any SSOT) then run the section-8 gates.
7. CHANGELOG `[Unreleased]` entry; `git commit -s`.

## 10. Checklist: adding or editing a skill

1. Scaffold/iterate with the `skill-creator` plugin / `skill-development` skill.
2. `name` = directory name; `description` trigger-rich and **<= 1024 chars**, no trailing
   `.`/`!`/`?`, with `route to ...` / `DO NOT trigger` clauses.
3. Body has `## Persona`, `## Out of Scope`, and `## Standalone-first fallback`. Keep `SKILL.md`
   concise; push detail to `references/`.
4. Tool surface: edit `generator/skill_tool_deps.json` (+ `server-surface.json`), then `make gen`.
   **Never hand-edit between the GENERATED TOOLS markers.**
5. OSM-first, version-agnostic, capability-described prose. Fan-out references
   `skills/_shared/concurrency-guard.md`; `fork`/`send-message` handoff references
   `snippets/context-handoff-protocol.md`.
6. Capability-noun name (`odoo-` prefix), different from any agent it dispatches.
7. Run the section-8 gates; CHANGELOG `[Unreleased]` entry; `git commit -s`.
