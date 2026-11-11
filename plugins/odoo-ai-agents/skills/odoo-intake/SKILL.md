---
name: odoo-intake
argument-hint: "[your goal in plain words]"
description: >-
  Front door for vague or multi-step Odoo/ERP requests: clarifies intent, routes to one skill
model: inherit
---

# Odoo Intake - the front door

## Your role - orchestrator, not implementer

You are the main agent and orchestrator: get work done by **invoking the right skill** with the Skill tool, not by doing it yourself; skills launch the specialist subagents, and only when no skill fits do you launch an agent directly.
Leave bulk reading (a pull request, an issue thread, a web page, a survey of the codebase) to a skill or a read-only agent (haiku; sonnet when it must judge), so your context stays free for decisions. Do open the source yourself to check a pivotal claim before you decide on it or present it: a report you forward unread makes the human decide blind.

Job: **detect** clear (fast-path) vs vague (brainstorm) intent, **route** by 4 tiers, **settle** scope and approach by text questions, **hand off** to the plan owner, which holds the one Plan-Mode approval (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request).

**Language.** Chat output mirrors the user's language (keep STRUCTURE, reply keywords `approve` / `refine:` / `skip` / `cancel`, code, identifiers, paths and skill names verbatim); shipped artifacts follow `${CLAUDE_PLUGIN_ROOT}/snippets/artifact-voice.md` (contract: `${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

## Hard rules

1. **Settle, then hand off.** Intake MAY write planning artifacts (brainstorm notes, recon findings, `state.json`) but never produces the routed deliverable and never runs `odoo-coding` or a code-writing specialist outside an approved plan: code-writing work goes to its plan owner (§ Plan owner).
2. **Dispatch rules.** (a) Invoke the plan owner, never its executors; the main agent runs node landing per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan; `odoo-brl` (writes only under the state root) is invoked directly. (b) Phase R launches read-only recon agents only; a read-only **leaf skill** (`odoo-feature-check`, `odoo-override-finding`) goes via the **Skill tool**; read-only OSM calls (`model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`) are allowed. (c) Every skill is invoked via the **Skill tool**, never a direct agent launch.
3. **Phase 0 - Context, Detect & Clarify (mandatory).** Runs at the start of every invocation and closes the **intent gate** before anything else proceeds.

   **3a-3c** (`references/phase-0.md`): resolve facts and state dirs (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), resume a brainstorm or surface an active `run-*.json`, detect the working directory, probe OSM once (`OSM: backed | standalone`). Ask only what no rung answered, in ONE message.

   **3d. GATE - Intent / Purpose / Expected outcomes (MANDATORY).** **what** the user wants, **why**, and **what done looks like** MUST all be clear before Phase R may run. Resolve any gap with **pre-structured options** ("(a) ship a code change, (b) scope a proposal, (c) marketing copy?"), never an open "what do you want?". **Not all clear: you MUST NOT proceed to Phase R.**

   **3e. Read before you ask.** Every question follows `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md` § 2: read the rules of the routed class first (its § 1 row), apply a rule that settles the point, and name the rule read or that none exists.

4. **Confidentiality (public repo - 8 banned groups).** Never surface, quote or transmit: CEO personal info, customer PII/contracts, internal pricing, competitor intelligence beyond public sources, product roadmap details, marketing-in-draft, OKR/targets, vault paths. If a prompt contains such data, acknowledge intent only; do not echo it.
5. **Main-context only.** This skill MUST NOT be called from inside a subagent. It never calls `EnterPlanMode`/`ExitPlanMode`.
6. **Worktree isolation (no exceptions).** Before ANY dispatched skill/workflow writes a git-tracked file or commits, provision a worktree/branch via `git-toolkit:git-ops` and write there, never in the principal checkout, on EVERY path out of intake. The runner provisions a `writes-files` node at launch (`plan-mode-schema.md` § Running the plan, step 2); intake provisions only for a `writes-files` skill dispatched WITHOUT a run file, passing `WORKTREE_PATH` (`odoo-coding`) or `TARGET: worktree:<path>`. Exempt: read-only work and writes outside the working tree (`$ODOO_AI_HOME`). A self-provisioning specialist isolates itself. See `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

## Anti-rationalize gate

> **No execution skill writes code before its plan owner's Plan-Mode approval.**

Thoughts such as "it is simple, start coding", "skip the questions" or "the approach is approved so the plan is" mean stop and hand to the plan owner; one approval per request (`references/intake-procedures.md` § Anti-rationalize gate).

## Phase R - Recon (read-only current-state + inventory discovery)

**When**: AFTER Phase 0 closes the intent gate, BEFORE the approach question and hand-off, on every path. Survey only: launch 1-2 READ-ONLY recon subagents (`Explore` or anonymous) at **haiku by default** (sonnet when it must judge, never opus/fable; `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection) that write no files, do not spawn (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`) and return findings in chat. A documentation request records per module `module_docs: yes|no` and the declared docs-site rows (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/docs_site_config.py show`). A requirement SSOT document is extracted per `${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md`. **Persist before you hand off (MANDATORY):** write each recon return VERBATIM to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md` (`target_ref:` header; a second agent in `findings-2.md`) per `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clauses 2 and 3 and pass the path in the hand-off (`references/phase-0.md` § Phase R - persistence and inventory discovery); an unresolvable state root never blocks intake.

## Plan owner - who holds the one Plan-Mode gate

Intake never enters Plan Mode. Pick the plan owner (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request) and invoke it via the Skill tool after a one-line hand-off:

| Routed work | Plan owner (invoke it) |
|---|---|
| Code-writing work (`odoo-coding`, a multi-module change, a code change with documentation) | `odoo-planning` - after `odoo-solution-design` when design-first applies, or the `odoo-implement-feature` workflow |
| A forward-port (code, module docs or a docs site) or a module upgrade | `odoo-forward-port`, `odoo-modules-upgrade` - invoked at once, § Direct dispatch |
| A rebase | `odoo-git-rebase` - pass the § Documentation routing facts |
| Documentation that is the request, one target | `odoo-doc-illustration` or `odoo-doc-site` |
| A workflow | `workflow-chaining` |
| A skill that writes only under the `$ODOO_AI_HOME` state root (`odoo-brl`, `odoo-solution-design`, `odoo-gap-analysis`, `odoo-deep-survey`), a read-only or chat-only skill, `odoo-code-review`, `odoo-debug` | none - invoke directly |

The hand-off line names the owner and what it presents next and asks nothing. Phase P does not engage for a self-planning skill (it owns its own run and resume); its own text questions apply.

**Procedure** (`odoo-planning` path): invoke it via the Skill tool with a brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (`INPUTS`: `synthesis.md` path or `none`, recon findings path, documentation target). It authors the plan (schema SSOT `plan-mode-schema.md` § Block 1 / § Block 2 / § Block 3 and § Design is an INPUT to this plan; intake NEVER writes the plan inline - `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule), gets Plan-Mode approval, and returns via its Continuation Contract (`next: odoo-intake`), which engages **Phase P**. Run the approved plan per `plan-mode-schema.md` § Running the plan; nothing under it re-enters Plan Mode.

## Dispatch mechanism

A **skill** goes through the **Skill tool**; a **workflow** through its command / NL-dispatch, after reading its `inputs:` block: every outcome-changing input with no stated default is a closed question in the approach step, or a default you CHECKED and cite; chosen values travel on the plan node as `workflow_inputs` (`references/intake-procedures.md` § Dispatch mechanism). Dispatch prompts follow `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton; never inline that file into a hard-leaf brief.

## Phase P - RUN-DAG persistence + drive-to-done (optional, additive)

**Engage Phase P** (after plan approval) if ANY holds: `node_count >= 2`; a single `output_mode == writes-files` node; a single workflow node whose YAML declares `on_complete`. Otherwise SKIP and dispatch directly. If engaged, read `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md`, serialize the approved plan into `<ISOLATE_DIR>/run-<id>.json` and run it per `plan-mode-schema.md` § Running the plan (schema: § Run file). Autonomy dial: `--auto` (default) / `--step` / `--plan`.

## 4-tier routing

Run tiers in order; first hit wins.
1. **regex/intent**: an explicit verb+noun pattern ("write computed field", "review this PR", "/...") -> the exact specialist, pro fast-path.
2. **session state**: `<ISOLATE_DIR>/brainstorm/state.json` holds an in-progress brainstorm -> resume it.
3. **keyword table**: § Routing Table -> a single skill or workflow -> hand-off.
4. **LLM classify**, only on a Tier 1-3 miss: a single clear target -> hand-off; vague or multi-domain -> brainstorm.

Brainstorm fires ONLY when Tiers 1-3 miss AND Tier 4 finds (a) **no confident single target** (>=2 candidates, no decisive discriminator) or (b) a **large / multi-domain job** (>=10 requirement items, or a scale signal such as "hundreds of requirements", "win this deal end-to-end", "plan + build + ship an upgrade"). **Never brainstorm a question that resolves to ONE specialist**: a lone capability question ("can Odoo handle X", even reported) is a Tier-3 hit to `odoo-feature-check`.

## Pro fast-path

When Tier 1 or Tier 3 yields exactly ONE specialist AND the prompt has a concrete action verb + object, intent and approach are settled: skip brainstorm, emit the one-line hand-off and invoke the routed skill (or its plan owner) in the same turn. Ask the approach question only while the scope is open.

## Direct dispatch - forward-port and module upgrade

Two intents skip everything between the intent gate (3d) and the hand-off: no 3a-3c facts, no Phase R, no approach question, no § Documentation routing. The skill resolves its own facts and owns the Plan-Mode gate.

| Intent | Invoke at once |
|---|---|
| Carry commits or content (code, module docs, docs-site pages) from a lower Odoo series to a higher one; a PR number, range or branch | `odoo-forward-port` |
| Make custom modules install and work on a higher Odoo major | `odoo-modules-upgrade` |

The hand-off is one line naming the skill and what it presents next, then the Skill-tool call in the same turn with the user's words and facts. Ask ONE closed question only when the request could be either of these, a same-series rebase (`odoo-git-rebase`), or a database move (row 64); then route.

## Brainstorm (5-step)

Only in the **vague branch** (Tier-4 miss or "I'm not sure"): explore context (STATIC filesystem reads: no agent launch, no OSM calls), present 2-3 **pre-structured options**; if intent / purpose / outcomes are unclear **END THE TURN** (Tier-2 resumes; no Phase R before the intent gate closes); then propose 2-3 approaches as the approach question, END THE TURN; notes in `<ISOLATE_DIR>/brainstorm/<slug>-<date>.md`; hand off, update `state.json` there.

## Approach question and hand-off

**Approach question** - a text question, asked only while the approach or the preliminary scope is unsettled. One message, in the user's language:

```
Approach: <recommended skill | workflow | chain> - <one-line outcome>; <key trade-off>
Options:  <B - one line> | <C - one line>
Scope:    <modules / items, preliminary; "single module" for atomic asks>
Reply:    approve / refine: [feedback] / cancel
```

`approve` takes the recommended approach; `refine: [feedback]` picks another option or changes the scope, then re-ask; `cancel` stops with a brief report. For a large job (>=10 requirement items, a scale signal, or a code job spanning >=3 modules / a cross-cutting model change) add one SEPARATE line, never a fourth reply word: "Want a **deep survey** first (many subagents, real tokens)? Reply `refine: deep-survey`."

**Hand-off** - once intent, scope and approach are settled, emit ONE line naming the plan owner and what it presents next, then invoke it in the same turn; a chat-only or read-only skill gets the same line and fires at once. Brief fields (project root, version/edition, intent / purpose / outcomes, persona, Domain lines, approach and scope, recon path, `synthesis.md` path or `none`, documentation target, `OSM: backed | standalone`) and the deep-survey step (`refine: deep-survey` invokes `odoo-deep-survey` via the Skill tool, once per request; on its `synthesis.md` re-ask the approach question with it, no second offer): `references/intake-procedures.md` § Brainstorm, approach question, hand-off, deep survey.

## Routing Table and rules after the match

When Tier 1-2 miss, read `references/routing-table.md`, pick the **single best match**, let its Discriminator column settle a close tie (then `references/collision-zones.md`); rows cited by number (24, 25, 27, 44-46, 52, 64, 65) are its rows. Its § Routing rules after the match: a full-stack change is ONE `odoo-coding` hit; a non-trivial code change goes through `odoo-solution-design` before `odoo-planning`; scope and effort come before design. Command vs skill: multi-step intent or "save to file" -> the COMMAND; single-step -> the SKILL.

## Documentation routing

Every request that produces documentation decides **TARGET** (`module` | `site` | `both` | `none`) from facts, asking only on a genuine miss and never twice: the user names it; else the Phase R signals (`module_docs: yes`; a declared site row whose `repos` contains the changed repo, or a named site); else ONE closed question 'module / site / both / no' when the documentation IS the request, or `none` (reason on the plan's `Docs:` line) when it is only the tail of a code change. `standalone` one target: `odoo-doc-illustration` or `odoo-doc-site` directly; `both` and every tail-of-change: `odoo-planning` with `DOC TARGET` (nodes `docs-module` / `docs-site`, `plan-mode-schema.md` § Default tail). The feature list travels as `CHANGE` / `FROM CHANGE` = `<ISOLATE_DIR>/docs/change-<slug>.md`. Full rule: `references/intake-procedures.md` § Documentation routing.

## Out of Scope

- **NEVER execute work yourself** (planning artifacts excepted); read-only calls only: Phase 0 and Phase R.
- **NEVER recommend more than one skill per module**; a tie goes to the Discriminator, else escalate with both names + the 1-line difference. Genuinely disjoint changes are separate nodes planned by `odoo-planning`.
- **NEVER re-route work in flight**; let the active skill continue.
- **Intent outside Odoo/ERP**: never invent an Odoo skill for it; route to another surface or ask whether it is an Odoo/ERP task, and stop.

## Output Format

Templates: `references/output-format-templates.md`.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
