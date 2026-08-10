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
- `argument-hint` is **required here** (repo convention, `tests/test_skill_format.py`) - a short,
  **double-quoted** string shown in `/skill-name` autocomplete to advertise the arguments a user
  passes, e.g. `argument-hint: "[PR#|local|worktree:<path>]"`. Derive it from the skill's real
  input contract (read the `description` triggers and any `$ARGUMENTS` use in the body); use the
  `[token]` form, a single space between multiple args, `|` for alternatives, ASCII only. **Always
  double-quote the value** - an unquoted `argument-hint: [foo]` parses as a YAML *list* at runtime,
  not a string. The same field applies to commands (`plugins/*/commands/*.md`).

**Required body sections** (`tests/test_skill_format.py` asserts all three exist):

- `## Role`
- `## Out of Scope`
- `## Standalone-first fallback` (or `## Standalone fallback`)

**`## Role` vs persona - identity lives in the agent, not the skill.** A skill's `## Role`
states the executor's **operating role, target audience, and scope** (what this capability does
and for whom) - e.g. "Module-upgrade conductor: delegate every diff read, decide dep-order, gate
on human" or "Developer / Tech Lead". It must **not** declare an identity, voice, or character:
no `You are a ...`, no first-person persona, no tone/personality adjectives. That is a deliberate
layering choice grounded in Anthropic, OpenAI, and Google guidance, which all place
persona/identity/voice in the **agent's system prompt** (a subagent body / SDK `systemPrompt` /
ADK `instruction` / a Gem) and keep skills/tools as portable, composable, identity-free
capabilities. Baking a persona into a skill breaks that portability and duplicates the identity a
dispatched agent already carries (`agents/*.md` open with `You are a senior Odoo ...`) - an SSOT
violation. Put the *identity* in the agent; put the *role/audience* (and any output tone as a
requirement of the **artifact**, e.g. "the pricing doc reads for a CFO first") in the skill.
Enforced by `test_skill_format.py::test_skill_role_declares_no_identity`.

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

**No `tools:` allowlist (scoped to `plugins/odoo-ai-agents/agents/`).** Repo convention there:
agents omit the frontmatter `tools:` key so they inherit the full (drift-proof) tool surface; the
harness depth cap is the only nesting net. Enforced by `tests/test_skill_format.py`
(`test_agent_frontmatter`, scoped to that plugin). This is intentionally stricter than the generic
Anthropic option to allowlist tools. (Generic background: Anthropic lets you omit `Agent` from
`tools`/`disallowedTools` to stop an agent spawning subagents; here you state that as a body
constraint instead.) `git-toolkit`'s three execution agents - `git-operator`, `git-surveyor`,
`github-operator` - are DELIBERATE exceptions: each declares an explicit `tools:` array
(least-privilege over git/GitHub operations) and sits outside the odoo-ai-agents-scoped
convention above.

**Platform fact - `permissionMode`/`hooks`/`mcpServers` are ignored for plugin agents.** A plugin
agent's frontmatter `permissionMode`, `hooks`, and `mcpServers` keys are read by the build ONLY to
emit a warning ("Plugin agent file `<path>` sets `<key>`, which is ignored for plugin agents. Use
`.claude/agents/` for this level of control.") and are then discarded - they never reach the
running agent. These fields take effect only for agents under user/project `.claude/agents/`, not
under any plugin's `agents/` directory. Do not add `permissionMode` to an agent under
`plugins/*/agents/` expecting it to change enforcement - it is a dead field there; the only
platform lever for this level of control is `.claude/agents/`, outside any plugin. Enforced by
`tests/test_plugin_agent_ignored_fields.py`.

**Leaf/spawner status is SSOT'd, not just prose.** Every agent's `role` (`leaf` | `spawner` |
`coordinator`) is declared in `generator/skill_tool_deps.json` `agents.<name>.role` and
lint-enforced (`check_orchestration.py`'s agent-role pass) - a `role: leaf` agent's body is
checked for the never-git/never-spawn clause and for any contradicting spawn/git language. The
body-prose declaration ("You are a HARD LEAF...") stays required regardless; the SSOT does not
replace it, it guarantees it is present and non-contradictory. This does NOT change the
`tools:`-free convention above - still no allowlist, still no hard-deny hook.

**Model is a default, overridden per dispatch.** Frontmatter `model:` (an alias) is only the
default tier. The dispatcher sets the launch `model` from the dispatched work's complexity - see
`skills/_shared/concurrency-guard.md` "Model-tier selection" (haiku = mechanical, sonnet =
default/medium, opus = heavy/wide blast radius, fable = ultra-complex + human-confirm). Do not
hardcode a tier in prose; reference that SSOT.

**Handoff = fork requires a Tier-C note.** If an agent or its skill uses `handoff: fork` /
`send-message`, the consuming skill must document the Tier-C fresh-spawn fallback (see section 3
and `tests/test_chp_hardening.py`).

**Dispatch-brief snippet - the caller-side counterpart to the worker brief.**
`snippets/dispatch-brief.md` is the SSOT for how a spawner (main agent, a dispatching skill, or a
nested coordinator) fills the dispatch prompt when it dispatches a specialist agent -
the universal 10-field skeleton (`OBJECTIVE`, `WHY`, `SCOPE`, ..., `RETURN_BUDGET`) plus a per-family delta
(Designer/planner, Coder, Reviewer/auditor, Tester/QA, Doc-writer, Instance/ops, Survey/analyst).
Every spawner skill/agent **reads it BY PATH** while composing a dispatch prompt; it is **NEVER
inlined verbatim into a hard-leaf brief** - a leaf has no one to re-brief, so it self-checks
against only its own family-delta field list instead of the full caller schema. This is the
opposite direction from `worker-brief.md`, which IS inlined into every leaf because it is
worker-side behavior the leaf must execute. Every non-git agent body carries a `## Brief
self-check` section (the LEAF or SPAWNER variant from `dispatch-brief.md`, family-delta based);
`git-toolkit` agents carry the equivalent contract via that plugin's own
`git-nesting-protocol.md` (a cross-plugin boundary - `git-toolkit` cannot depend on
`odoo-ai-agents`, so its git-specific delta lives there, not in `dispatch-brief.md`).

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

## 6.5. Shared contracts: decidable rule vs. explanation (`snippets/references/`)

Every `snippets/*.md` (and `skills/_shared/*.md`) file cited by 3+ distinct skills+agents is a
HOT file, loaded into many cold agent contexts per run - its byte size is a per-invocation cost.
When authoring or editing one, keep it to DECIDABLE RULES ONLY (thresholds, exceptions, schemas,
procedures a reader can act on without further judgment). Move rationale, worked examples, and
historical "why" prose to a sibling `snippets/references/<name>.md` - a file for humans and future
authors doing repo archaeology, not for a runtime agent.

**The read-both hazard - the one hard rule.** The main file must NEVER name its `references/`
sibling's path, in any form (no "see snippets/references/X.md for more"). If an executing agent is
shown that path, it may read both files and the byte-cost saving is lost. `snippets/references/`
is discoverable only from this section and from `[ref-scope]`'s lint (`check_orchestration.py`),
which also asserts no consumer-facing file contains the literal substring `snippets/references/`.

`[card-budget]` (same lint) asserts every hot file stays under its declared budget - grow one
deliberately, never silently. A file becomes subject to it two ways:

- **Declared** - it has an entry in `tests/fixtures/card_budget_grandfather.json`. The entry is
  both the qualification and the budget, and the file is measured wherever it lives. This is the
  only door for a hot contract that is not a shared snippet - notably a top-level
  `skills/<name>/SKILL.md` runtime contract such as `run-harness`, whose basename is shared by
  every skill and so is invisible to the citer heuristic below.
- **Discovered** - it is a `snippets/*.md` or `skills/_shared/*.md` file cited by >=3 distinct
  skills+agents, and its budget is the default 4,096 B cap.

When you trim a budgeted file, lower its entry to the new actual size in the same change. A budget
left above the real size quietly hands the reclaimed bytes back.

## 7. Confidentiality and style (public repo)

- ASCII hyphen `-` (U+002D) only - no en/em/figure dashes (enforced for several snippets, e.g.
  `tests/test_chp_hardening.py`).
- No vault paths, personal emails, absolute `~/.` paths, instance hosts/dbs/keys, or hardcoded
  Odoo version ranges/counts in agent-facing prose. Install the guard once:
  `git config --local core.hooksPath .githooks/`.

## 8. Gates before commit

Run the full local gate (same as CI) before pushing:

```bash
make validate          # plugin schema + skill frontmatter + description cap + workflow + orchestration check, both STRICT/enforced
make test              # full pytest suite (naming, format, body convention, CHP, disambiguation, ...)
make gen-check         # regenerate SSOT artifacts, fail on any diff (idempotency)
make deps-check        # every skill->tool reference points at a live tool
make workflows-check   # workflows/*.workflow.yaml vs schema (warn-first standalone; WORKFLOWS_STRICT=1 to enforce locally - `make validate` always runs it strict)
make orchestration-check  # capability/contract lint (warn-first standalone; ORCH_STRICT=1 to enforce locally - `make validate` always runs it strict)
```

Then commit via the `git-toolkit:git-ops` skill (it detects the convention and applies the DCO
sign-off - never hand-run git; Universal rule: `plugins/odoo-ai-agents/snippets/git-delegation.md`)
and keep the PR to one logical change. Bump policy (CONTRIBUTING.md "Versioning"): a new
skill/agent/command is a **minor**;
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
7. Commit the CHANGELOG `[Unreleased]` entry + your changes via `git-toolkit:git-ops` (DCO sign-off
   applied for you).

## 10. Checklist: adding or editing a skill

1. Scaffold/iterate with the `skill-creator` plugin / `skill-development` skill.
2. `name` = directory name; `description` trigger-rich and **<= 1024 chars**, no trailing
   `.`/`!`/`?`, with `route to ...` / `DO NOT trigger` clauses; `argument-hint` = a double-quoted
   `[token]` hint of the args (e.g. `"[module] [target-series]"`).
3. Body has `## Role` (operating role/audience/scope, **no** identity/persona - see above),
   `## Out of Scope`, and `## Standalone-first fallback`. Keep `SKILL.md`
   concise; push detail to `references/`.
4. Tool surface: edit `generator/skill_tool_deps.json` (+ `server-surface.json`), then `make gen`.
   **Never hand-edit between the GENERATED TOOLS markers.**
5. OSM-first, version-agnostic, capability-described prose. Fan-out references
   `skills/_shared/concurrency-guard.md`; `fork`/`send-message` handoff references
   `snippets/context-handoff-protocol.md`.
6. Capability-noun name (`odoo-` prefix), different from any agent it dispatches.
7. Run the section-8 gates; commit the CHANGELOG `[Unreleased]` entry + your changes via
   `git-toolkit:git-ops` (DCO sign-off applied for you).
