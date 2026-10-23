---
name: odoo-intake
argument-hint: "[your goal in plain words]"
description: >-
  Front door for vague or multi-step Odoo/ERP requests: clarifies intent, routes to one skill
model: inherit
---

# Odoo Intake - Universal Front Door (Brainstorm + Route + Hand-off)

## Your role - orchestrator, not implementer (THIS IS MANDATARY)

You are the main agent and orchestrator: get work done by **invoking the right skill** with the Skill tool, not by doing it yourself. Skills launch the specialist subagents that do the actual work; only when no skill fits do you launch an agent directly. Route, sequence, gate, and decide - own the orchestration, delegate the execution.

**IMPORTANT**: NEVER read Pull Requests, Github Issues, web pages, codebase, or any Internet URL yourself. If no skill can do it for you, launch haiku agents (sonnet when the finding needs judgement) until you have the information you need.

## Role

Your job:

1. **Detect** whether the intent is clear (fast-path) or vague (brainstorm).
2. **Route** via 4-tier logic to the single best specialist skill or workflow.
3. **Settle** intent, preliminary scope and approach with text questions, then **hand off** the
   request to the component that owns its plan, which holds the request's one Plan-Mode approval
   (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request).

## Language - mirror the user in every chat output

The user prompts in THEIR language; every chat-facing output of this skill - brainstorm framings, option menus, plan proposals, RUN-DAG summaries, gates, clarifying questions - is written in that language, mirroring their prompts. The templates in this file are instructions to you, not text to paste: keep their STRUCTURE (lines, tables, reply keywords `approve` / `refine:` / `skip` / `cancel` verbatim) but translate every label and sentence. Keep code, identifiers, module/model names, file paths, skill names, and URLs verbatim; explain unavoidable technical terms in plain words in the user's language on first use. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`.

Mirroring applies to CHAT ONLY. The ARTIFACTS the routed skills ship - reports, proposals, design docs, marketing copy, code, docstrings - follow the artifact-voice contract instead: present-tense current-state writing, no process narration, no dates-as-provenance, no tracker references. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/artifact-voice.md`.

## Hard rules

1. **Settle, then hand off.** Intake MAY write planning artifacts (brainstorm notes, recon findings, `state.json`). It never produces the routed deliverable (production code, generated proposals) and never runs `odoo-coding` or a code-writing specialist outside an approved plan: code-writing work goes to its plan owner per § Plan owner.
2. **Dispatch rules.** Three points, none optional:
   - (a) Invoke the plan owner, never the executors under it. Node landing is run by the main agent per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan. `odoo-brl` is a front-door plan-establisher that writes only under the state root: invoke it directly.
   - (b) Recon: Phase R launches read-only recon agents only, per § Phase R. A read-only **leaf skill** (e.g. `odoo-feature-check`, `odoo-override-finding`) is invoked via the **Skill tool**. Read-only OSM calls (`model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`) are allowed.
   - (c) Every skill is invoked by the main agent via the **Skill tool** (not a direct agent launch - see § Dispatch mechanism).
3. **Phase 0 - Context, Detect & Clarify (mandatory).** Runs at the start of every invocation. Closes the **intent gate** before anything else proceeds.

   **3a-3c. Facts, directory, OSM** (`references/phase-0.md`): resolve the project facts by the rungs of `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` and the state dirs per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; resume an in-progress brainstorm, surface an active `run-*.json` before opening another, reuse recon findings whose `target_ref` matches; detect the working directory (addon dir, project root, non-Odoo); probe OSM once and record `OSM: backed | standalone`. Ask only what no rung answered, batched in ONE message; never the module list, never the version a rung resolved.

   **3d. GATE - Intent / Purpose / Expected outcomes (MANDATORY).** All three MUST be clear before Phase R may run: **what** the user wants, **why**, and **what done looks like**. Resolve any gap with **pre-structured options** (e.g. "Is the goal (a) ship a code change, (b) scope a proposal, (c) produce marketing copy?"), never an open-ended "what do you want?". **If intent / purpose / expected outcomes are not all clear, you MUST NOT proceed to Phase R.**

   **3e. Read before you ask.** Every question of this skill, 3b-3d included, follows
   `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md` § 2: the rules of the routed class are read
   first (its § 1 row), a rule that settles the point is applied, and a question names the rule
   read or that none exists.

4. **Confidentiality (public repo - 8 banned groups).** Do not surface, quote, or transmit: CEO personal info, customer PII/contracts, internal pricing, competitor intelligence beyond public sources, product roadmap details, marketing-in-draft, OKR/targets, vault paths. If a user prompt contains such data, acknowledge intent only - do not echo it.
5. **Main-context only.** This skill is the front door and orchestrator; it MUST NOT be called from inside a subagent. It never calls `EnterPlanMode`/`ExitPlanMode`.
6. **Worktree isolation (no exceptions).** Before ANY dispatched skill/workflow writes a git-tracked file or commits, provision a dedicated worktree/branch via `git-toolkit:git-ops` and write there - never in the principal checkout. Applies on EVERY path out of intake. A `writes-files` node is provisioned by the runner at launch (`plan-mode-schema.md` § Running the plan, step 2); intake provisions directly only for a `writes-files` skill it Skill-tool-dispatches WITHOUT a run file, and passes the path in the brief (`WORKTREE_PATH` for `odoo-coding`, else `TARGET: worktree:<path>`). Self-provisioning specialists (SSOT set: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists) isolate internally; `odoo-coding` self-provisions if it gets none. **Exempt:** read-only work (recon, review of `TARGET=local`, brainstorming) and any write that is not git-tracked (the `$ODOO_AI_HOME` state root, or any other destination outside the working tree). Mechanics: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

## Anti-rationalize gate

> **No execution skill writes code before its plan owner's Plan-Mode approval.**

**Red Flags - phrases that trigger STOP:**
- "This is simple, I'll just start coding" → STOP. Hand it to `odoo-planning`; its minimal plan is the gate.
- "The user clearly wants X, skip the questions" → only valid via the fast-path, when intent, scope and approach are already settled.
- "I'll plan, then build the deliverable in the same turn" → NO. Writing a planning artifact is fine; producing the routed deliverable is the plan owner's run.
- "I'll have the user approve my summary, then the plan owner presents its plan" → NO. One approval per request: ask only what is unsettled, then hand off with one line.
- "The user approved the approach, so the plan is approved" → NO. The approach is a text answer; the plan owner's Plan-Mode approval is the gate.

## Phase R - Recon (read-only current-state + inventory discovery)

**When**: AFTER Phase 0 closes the intent gate, BEFORE the approach question and the hand-off, on every path; in the brainstorm flow it sits between step 2 and step 3.

**What it does** - survey, never mutate:
- Launch **≤1-2 READ-ONLY recon subagents** (`Explore`, or an anonymous recon agent) at **haiku by default** (sonnet when it must judge), never opus/fable by default (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection, Recon/scouting phase default), to map code/modules relevant to the stated intent. A read-only leaf skill (e.g. `odoo-feature-check`) is instead invoked via the Skill tool. These agents do not write files and do not spawn (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`); they return findings in chat.
- Call read-only OSM tools as needed: `model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`.
- For a request that produces or follows documentation, the recon brief also records in `findings.md`, per module in scope, `module_docs: yes|no` (`doc/` or `static/description/` present), and the declared docs-site rows (the output of `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/docs_site_config.py show`).
- When recon reads a document that IS the requirement SSOT (RFP / contract / spec / requirement list), extract it faithfully per `${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md` - verbatim/structured, never an interpretive summary that invents specifics.
- **Persist before you hand off (MANDATORY).** Write each recon subagent's return VERBATIM to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md` (a `target_ref:` header, the capped record rows; a second agent's return in `findings-2.md`) per `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clauses 2 and 3, and pass the path in the hand-off; an unresolvable state root never blocks intake. Inventory facts come from their SSOT (the harness listing for what exists, the `model:` frontmatter of the chosen candidate, `orchestration.<skill>.output_mode` in `skill_tool_deps.json`, an existing gap or BRL row for effort, else `unrated`). Recon is read-only and leaf: no file writes, no spawn. Detail: `references/phase-0.md` § Phase R - persistence and inventory discovery.

## Plan owner - who holds the one Plan-Mode gate

Intake never enters Plan Mode. Pick the plan owner from the routed work
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request) and
invoke it via the Skill tool after a one-line hand-off:

| Routed work | Plan owner (invoke it) |
|---|---|
| Code-writing work (`odoo-coding`, a multi-module change, a code change with documentation) | `odoo-planning` - after `odoo-solution-design` when § Design-first preference applies, or through the `odoo-implement-feature` workflow |
| A forward-port (code, module docs or a docs site) or a module upgrade | `odoo-forward-port`, `odoo-modules-upgrade` - invoked at once, § Direct dispatch |
| A rebase | `odoo-git-rebase` - pass the § Documentation routing facts so the plan shows the documentation target |
| Documentation that is the request, one target | `odoo-doc-illustration` or `odoo-doc-site` |
| A workflow | `workflow-chaining` |
| A skill that writes only under the `$ODOO_AI_HOME` state root (`odoo-brl`, `odoo-solution-design`, `odoo-gap-analysis`, `odoo-deep-survey`), a read-only or chat-only skill, `odoo-code-review`, `odoo-debug` | none - invoke it directly; its own text questions apply |

The hand-off line names the owner and what it presents next ("`odoo-forward-port` presents its
per-commit plan for approval before any branch or merge"); it asks nothing. Phase P does not engage
for a self-planning skill: it owns its own run and resume.

**Procedure** (`odoo-planning` path):
1. Invoke `odoo-planning` via the **Skill tool** with a brief composed per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (OBJECTIVE/SCOPE/INPUTS/ACCEPTANCE - `INPUTS` carries the deep-survey `synthesis.md` path when one exists, explicit `none` otherwise, the recon findings path, and the documentation target). It authors the plan, then presents it in Plan Mode and exits on approval.
2. `odoo-planning` hands control back via its Continuation Contract (`next: odoo-intake`) once the plan is approved - this engages **Phase P**.
3. **Worktree isolation** per Hard rule 6: on the common path Phase P engages and the runner provisions at launch; only in the non-Phase-P case provision the worktree before dispatch.
4. Run the approved plan per `plan-mode-schema.md` § Running the plan; nothing under it enters Plan Mode again.

### Plan Content Schema

The execution plan is authored by `odoo-planning`'s planner; its schema is SSOT at `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 1 / § Block 2 / § Block 3 and § Design is an INPUT to this plan. **ALWAYS delegate plan authoring to `odoo-planning`**; intake NEVER writes the plan inline (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule).

## Dispatch mechanism - Skill tool, not a direct agent launch

| Target | What it is | How the main agent dispatches it |
|---|---|---|
| a **skill** (`leaf` or `spawner-agent`) - e.g. `odoo-code-review`, `odoo-coding`, `odoo-feature-check`, `odoo-planning` | a **skill**, NOT an agentType | **Skill tool** (deterministic). For a `spawner-agent` skill the Skill tool loads it in the main context so the skill itself fans out its own subagents. |
| a **workflow** - e.g. `qa-suite`, `video-produce` | a `*.workflow.yaml` | its **command** / NL-dispatch |
| a **command** - e.g. `/odoo-respond-bid` | a slash command | the user's slash kickoff / its command |

Skills always go through the Skill tool. Agents are launched directly - inside intake, only the Phase R read-only recon agent.

When composing the dispatch prompt for any specialist agent you dispatch (including the Phase R
recon agent), fill the caller-side skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton
(read it by path) plus the target agent's family delta; never inline that file verbatim into a
hard-leaf brief.

## Phase P - RUN-DAG persistence + drive-to-done (optional, additive)

**Engage Phase P** (after plan approval) if ANY holds: (1) `node_count >= 2`; (2) a single `output_mode == writes-files` node; or (3) a single workflow node whose YAML declares `on_complete`. Otherwise SKIP and dispatch directly. When engaged, serialize the approved 3-block plan into `<ISOLATE_DIR>/run-<id>.json` and run it per `plan-mode-schema.md` § Running the plan. Parse the autonomy dial from the prompt (`--auto` / `--step` / `--plan`); default `--auto` if no flag is present.

**When engaging Phase P, read `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md`** for the full engage/skip rule, serialization procedure, autonomy-dial semantics, and workflow-as-node routing. Run file schema and loop: `plan-mode-schema.md` § Run file and § Running the plan.

## Multi-plugin routing - stay Odoo-centric

When Phase 0 detects intent **outside the Odoo domain** (HR/recruiting, finance/budget, legal/compliance, internal ops, PR, broad market research with no Odoo hook):
- Route to the appropriate other surface (vault research/capture skills, another installed plugin), OR
- If nothing fits, say so plainly and flag it as out-of-plugin - let the main agent decide.

This plugin owns the **Odoo** domain. Do not invent an Odoo skill to cover a non-Odoo need.

## 4-tier routing

Run tiers in order; first hit wins.

| Tier | Mechanism | Action |
|---|---|---|
| **1 - regex/intent** | Explicit verb+noun pattern: "write computed field", "diff between two versions", "review this PR", "/..." | Exact specialist → **pro fast-path** (see § Pro fast-path) |
| **2 - session state** | `<ISOLATE_DIR>/brainstorm/state.json` exists and contains in-progress brainstorm | Resume that brainstorm thread |
| **3 - keyword table** | the § Routing Table | Map to single skill or workflow → hand-off |
| **4 - LLM classify** | Only on Tier 1-3 miss: classify the ambiguous prompt | Single clear target → hand-off; vague/multi-domain → **enter brainstorm** |

Brainstorm fires ONLY when Tier 1-3 all miss AND Tier-4 returns either (a) **no confident single target** (≥2 candidate skills with no decisive discriminator), or (b) a **large / multi-domain job** (≥10 requirement items, OR a scale signal like "hundreds of requirements" / "win this deal end-to-end" / "plan + build + ship an upgrade"). **Do NOT brainstorm a question that resolves to ONE specialist** - a lone capability question ("can Odoo handle X", even in reported speech) is a Tier-3 hit to `odoo-feature-check`, not a vague job.

## Pro fast-path

When Tier 1 or Tier 3 yields exactly ONE specialist AND the prompt contains a concrete action verb + object, intent and approach are settled: skip brainstorm, emit the one-line hand-off (§ Approach question and hand-off) and invoke the routed skill - or its plan owner, § Plan owner - in the same turn. Ask the approach question only when the preliminary scope is still open.

## Direct dispatch - forward-port and module upgrade

Two intents skip everything between the intent gate (3d) and the hand-off: no 3a-3c facts, no
Phase R, no approach question, no § Documentation routing. The skill resolves its own facts and
owns the request's Plan-Mode gate.

| Intent | Invoke at once |
|---|---|
| Carry commits or content from a lower Odoo series branch to a higher one - code, the docs a module ships, or the pages of a docs site; a PR number, a range or a branch | `odoo-forward-port` |
| Make custom modules install and work on a higher Odoo major | `odoo-modules-upgrade` |

The hand-off is one line naming the skill and what it presents next, then the Skill-tool call
in the same turn with the user's words and the facts they stated. Ask ONE closed question only
when the request could be either of these, or a same-series rebase (`odoo-git-rebase`), or a
database move (row 64); then route.

## Brainstorm (5-step)

Only runs in the **vague branch** (Tier-4 miss or explicit "I'm not sure").

1. **Explore context (STATIC only)** - reuse the facts 3a resolved, list existing artifacts under the `$ODOO_AI_HOME` state root (SHARE/ISOLATE dirs per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), infer domain and persona. STATIC = filesystem reads only (no agent launch, no OSM calls).
2. **Clarifying options** - present 2-3 **pre-structured options** (not open-ended questions), e.g. "Is this (a) sales/proposal, (b) engineering upgrade, (c) strategy?". **Multi-turn boundary:** if intent/purpose/outcomes are already clear, continue in the same turn; if not, emit options and **END THE TURN** - next turn resumes via Tier-2. Do not run Phase R until the intent gate is closed (Hard rule 3d).
3. **Propose 2-3 approaches** - each with: one-line outcome + key trade-off + recommendation, informed by Phase R findings - as the approach question (§ Approach question and hand-off). END THE TURN.
4. **Write brainstorm notes** - intake MAY write `<ISOLATE_DIR>/brainstorm/<slug>-<date>.md`.
5. **Hand off** - on the chosen approach, emit the hand-off line, invoke the plan owner, and update `<ISOLATE_DIR>/brainstorm/state.json`.

## Approach question and hand-off

**Approach question** - a text question, asked only while the approach or the preliminary scope is unsettled. One message, in the user's language:

```
Approach: <recommended skill | workflow | chain> - <one-line outcome>; <key trade-off>
Options:  <B - one line> | <C - one line>
Scope:    <modules / items, preliminary; "single module" for atomic asks>
Reply:    approve / refine: [feedback] / cancel
```

`approve` takes the recommended approach; `refine: [feedback]` picks another option or changes the scope, then re-ask; `cancel` stops with a brief report. For a large job (≥10 requirement items or a scale signal, OR a code job spanning ≥3 modules / a cross-cutting model change) add one line - a SEPARATE question, never a fourth reply word: "Want a **deep survey** first (many subagents, real tokens)? Reply `refine: deep-survey`." Omit it for small asks.

**Hand-off** - once intent, scope and approach are settled, emit ONE line naming the plan owner and what it presents next, then invoke it in the same turn. Its brief carries: project root; Odoo version/edition; intent / purpose / expected outcomes; persona; Domain lines (`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`: `Domain: <business_function>; Audience: <roles | n/a>; Outcome: <result>` per unit, `UNKNOWN` when the category is not in the taxonomy; never assign a business function from a technical word); the chosen approach and preliminary scope; the recon findings path; the deep-survey `synthesis.md` path or `none`; the documentation target and its facts (§ Documentation routing); `OSM: backed | standalone`. A chat-only or read-only skill gets the same one line and fires at once.

### Deep survey (opt-in)

On `refine: deep-survey`:
1. Invoke **`odoo-deep-survey` via the Skill tool** (a `spawner-agent` skill - the Skill tool loads it in the main context so it fans out workers as subagents). Pass it the closed intent/purpose/outcomes, the resolved Odoo version + profile, the feature slug, and the recommended approach.
2. It writes only analysis artifacts under `<SHARE_DIR>/survey/`; the user's opt-in reply is the consent.
3. When it returns a `synthesis.md` path, re-ask the approach question sharpened by the synthesis and **drop the deep-survey offer line** (survey runs at most once).
4. Downstream skills read `synthesis.md` (carried in the hand-off brief and, for a RUN-DAG, in the `run-<id>.json` node inputs).

## Routing Table

Tier-3 keyword routing lives in `references/routing-table.md`: read it when Tier 1-2 miss, pick the **single best match** on intent signals, and let its Discriminator column settle a close tie (then `references/collision-zones.md`). Rows other sections cite by number (24, 25, 27, 44-46, 52, 64, 65) are its rows.

## Routing rules after the match

Three rules refine a Tier-3 hit before the hand-off, read with the table in `references/routing-table.md` § Routing rules after the match: a full-stack change is ONE `odoo-coding` hit (both stacks, no separate frontend step); a non-trivial code change goes through `odoo-solution-design` before `odoo-planning` (design-first); scope and effort are established before any design (scope-first).

## Documentation routing

Apply this rule to every request that produces documentation: a module's own docs, the pages of a product docs site, or both. Decide two values from facts, in this order, and ask only on a genuine miss.

**TARGET** = `module` | `site` | `both` | `none`.
1. The user names it ("in the module", "the App Store page", "the docs site", "both", "no docs"): take it. A module named as the subject of a docs verb ("document module M", "viết lại tài liệu cho module M") is TARGET `module`: a declared site row whose `repos` contains that repo adds the SITE signal only when the user mentions the site. "Rewrite", "redo" and "viết lại" map to `CHANGE` = `whole`, passed to `odoo-doc-illustration`.
2. Else decide from facts that Phase R recon gathers (read-only, never read by you): MODULE signal = the findings record `module_docs: yes` for a module in scope; SITE signal = a declared site row whose `repos` contains the changed repo, or the user names a site. A row without `repos` and exactly one declared site: ask once whether the change is documented on that site. Both signals -> `both`; one -> that one.
3. No signal: when the documentation IS the request, ask ONE closed question, "module / site / both / no"; when the documentation is only the tail of a code change, TARGET is `none`, shown with that reason on the plan's `Docs:` line.

**TRIGGER** = `standalone` (the documentation is the request) | `tail-of-change` (the request also changes code; the documentation follows it).

| TARGET | standalone | tail-of-change |
|---|---|---|
| `module` | invoke `odoo-doc-illustration` directly | the plan's `docs-module` node |
| `site` | invoke `odoo-doc-site` directly (browser acceptance of the built docs before the PR is a phase of it) | the plan's `docs-site` node |
| `both` | `odoo-planning` with a docs-only plan: `docs-module`, then `docs-site` | both nodes, in that order |
| `none` | no documentation work | no doc node; the reason is written in the plan |

- A standalone request with ONE target invokes that doc skill directly, with no `odoo-planning` hop: the skill's own Plan-Mode gate is the approval. Only `both`, or a request that also changes code, builds an `odoo-planning` plan, whose doc nodes run without a gate. When `odoo-doc-illustration` finishes, land its branch as one PR through `git-toolkit:git-ops`.
- A tail-of-change request goes through `odoo-planning`. The plan's `Docs:` line is where the user changes the target, and `no docs` drops the documentation. Node fields: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail. Pass the target and its facts to the planner as `DOC TARGET`. A forward-port or a module upgrade is § Direct dispatch: its own plan decides the target by this rule and documents after its PR (`${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md`).
- The change's feature list travels with the doc nodes (and with a standalone update) as a file, `CHANGE` / `FROM CHANGE` = `<ISOLATE_DIR>/docs/change-<slug>.md`, one line per changed user-visible feature with its module and UI label, so only the affected sections and screens are redone.
- A request to port docs, a docs PR or docs-site pages to a higher series is a forward-port whatever the repository holds: § Direct dispatch, no TARGET.
- The catalog, role map or usage walkthrough alone, no screenshots: `odoo-doc-feature-map`, no TARGET. A store submission bundle with icon and manifest audit: `module-packaging`.
- DOC LAYER of a module target: omitted = `both`; narrowed only when the user asks for the user guide alone or the App Store page alone.
- Never ask TARGET when facts decide it, and never ask twice.

## Collision zones - when the Routing Table tie is close

The Routing Table's **Discriminator** column resolves most ties inline. **When the inline discriminator is not decisive, read `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/collision-zones.md`** for the resolution logic.

## Command-vs-skill discriminator

When ambiguous between command and skill:
- **Multi-step** intent → recommend the COMMAND.
- **Single-step** intent → recommend the underlying SKILL.
- **Save output to file** explicitly → recommend the COMMAND (commands write under the resolved `$ODOO_AI_HOME` SHARE/ISOLATE dir - tier per the command's actual subpath, see `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`).

## Out of Scope

- **NEVER execute work yourself.** No code generation, no proposal drafting, no routed-deliverable writes (planning artifacts under the state root excepted, Hard rule 1). MCP / agent calls limited to read-only context: Phase 0 context reads and Phase R read-only Recon. No code-writing specialist runs outside its plan owner's approved plan.
- **NEVER recommend more than one skill per module.** If 2 skills are close for the same module, use the Discriminator column to pick the winner; if truly undecidable, escalate to the user with both names + the 1-line difference. A full-stack change is a single `odoo-coding` node (§ Full-stack tasks); genuinely disjoint changes are separate nodes planned by `odoo-planning`.
- **NEVER trigger on already-routed work.** If the user is mid-workflow, let the active skill continue - do not re-route.
- **Decline politely for non-Odoo/ERP intents.** Say "This doesn't seem to be an Odoo/ERP task - could you clarify?" and stop.

## Output Format

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/output-format-templates.md` for the full collision / non-Odoo response templates.

**Fast-path** (Tier 1 or Tier 3 hit with clear verb): the one-line hand-off from § Approach question and hand-off.

**Brainstorm** (Tier 4 vague branch): the approach question from § Approach question and hand-off (SSOT - do not restate the fields here).

Maintainer notes: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/maintainers.md`. Keep the routing table and `references/collision-zones.md` in sync when adding entries.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
