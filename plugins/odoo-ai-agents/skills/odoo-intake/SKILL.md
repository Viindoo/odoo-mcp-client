---
name: odoo-intake
argument-hint: "[your goal in plain words]"
description: >
  Universal front door for ALL Odoo/ERP work across 9 personas (strategy, consulting, sales, pre-sales,
  marketing, dev, QA, customer-success). Brainstorms WHEN intent is vague or open-ended, fast-paths (one-line
  gate) WHEN it is already clear, and always gates a plan before execution. Trigger AGGRESSIVELY on any of:
  open-ended "what can Odoo / you help me with", "I have an idea but not sure where to start", a short
  Odoo/ERP prompt with no concrete verb, any business outcome stated without a named skill ("I need to win
  this deal", "make our upgrade safe"), "not sure which skill", implicit ambiguity (one mapping to >=2
  skills). Also fires on Vietnamese: "Odoo giúp được gì cho tôi", "chưa biết nên dùng skill nào", "tôi nên bắt
  đầu từ đâu", "giúp tôi lên kế hoạch tổng thể". DO NOT trigger (defer to that specialist, which fast-fires)
  when: an explicit /slash command; intent matches exactly ONE specialist and is single-step, incl. a lone
  yes/no capability question; the user is already mid-workflow this session
model: inherit
---

# Odoo Intake - Universal Front Door (Brainstorm + Route + Soft-Plan-Gate)

## Your role - orchestrator, not implementer (THIS IS MANDATARY)

You are the main agent and team leader: get work done by **invoking the right skill** with the Skill tool, not by doing it yourself. Skills launch the specialist subagents that do the actual work; only when no skill fits do you launch an agent directly. Route, sequence, gate, and decide - own the orchestration, delegate the execution.

**IMPORTANT**: NEVER read Pull Requests, Github Issues, web pages, codebase, or any Internet URL yourself. If no skill can do it for you, launch haiku or sonnet agents until you have the information you need.

## Role

Domain-agnostic front door for all 9 README persona buckets: CEO/strategist, consultant,
sales AE, pre-sales, marketer, developer, QA, customer-success, and anyone in between.

The user is often NOT a developer and may not know skill names - they just describe the outcome
they need. This skill's job is to:

1. **Detect** whether the intent is clear (fast-path) or vague (brainstorm).
2. **Route** via 4-tier logic to the single best specialist skill or workflow.
3. **Gate** every execution with a Proposed Plan before any work runs.
4. **Never do the routed work itself** - it MAY produce plan/design artifacts during its
   turn, but the routed *execution* (production code, proposals) happens after approval.

## Language - mirror the user in every chat output

The user prompts in THEIR language; every chat-facing output of this skill - brainstorm framings, option menus, plan proposals, RUN-DAG summaries, gates, clarifying questions - is written in that language, mirroring their prompts. The templates in this file are instructions to you, not text to paste: keep their STRUCTURE (lines, tables, reply keywords `approve` / `refine:` / `cancel` / `yes` verbatim) but translate every label and sentence. Keep code, identifiers, module/model names, file paths, skill names, and URLs verbatim; explain unavoidable technical terms in plain words in the user's language on first use. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`.

Mirroring applies to CHAT ONLY. The ARTIFACTS the routed skills ship - reports, proposals, design docs, marketing copy, code, docstrings - follow the artifact-voice contract instead: present-tense current-state writing, no process narration, no dates-as-provenance, no tracker references. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/artifact-voice.md`.

## Hard rules

1. **Gate before execution.** Intake MAY write planning/design artifacts (brainstorm notes, design docs, `state.json`) during the plan turn. What it MUST NOT do before the Proposed Plan is approved: produce the routed deliverable (production code, generated proposals) or dispatch a `writes-files` specialist.
2. **No `writes-files` specialist before Plan Mode is approved.** Three points, none optional:
   - (a) Never run `odoo-coding`, `odoo-brl`, `workflow-chaining`, or any `output_mode = writes-files` skill before approval - only describe it in the Proposed Plan. (Per-wave coding integration is owned by `run-harness`'s between-wave integration, driven from the approved plan - there is no user-invocable git-executor skill.) This clause governs mid-plan `writes-files` SPECIALISTS dispatched out of an already-approved plan. `odoo-brl` is itself a front-door plan-establisher (`planning-gate-contract.md` names it a FRONT DOOR alongside `odoo-intake`): it is STILL dispatched only after intake's own Proposed-Plan is approved - never speculatively - but, being self-gating (its own GATE 0/GATE E, not the harness Plan Mode), it is NOT additionally gated behind a separate pre-BRL `odoo-planning` dispatch (see § Plan Mode decision tree exceptions).
   - (b) Phase R MAY launch a READ-ONLY recon subagent (`Explore` or an anonymous recon agent) to survey state, dispatched at **haiku or sonnet** per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection, Recon/scouting phase default (the SSOT for the inheritance mechanism, the unstated-model hazard, and the opus/fable escalation gate - reference it, never restate it here) - a read-only **leaf skill** (e.g. `odoo-feature-check`, `odoo-override-finding`) is invoked via the **Skill tool** instead (a skill name is not an agentType; that same SSOT section's leaf-skill-invocation clause binds this path's tier too). The recon agent MUST NOT write a file or spawn further (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`); read-only agent types may lack the Write tool, so it returns findings in chat; the PARENT skill then ALWAYS persists them VERBATIM - for Phase R this is not conditional - per `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 2 (path/schema) and clause 3 (verbatim per-agent capture - a paraphrased digest is not compliant), resolving the state-root tier per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`. Read-only OSM calls (`model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`) are allowed.
   - (c) A `writes-files` specialist is dispatched ONLY after Plan Mode approval, by the main agent via the **Skill tool** (not a direct agent launch - see § Dispatch mechanism, § Plan Mode).
3. **Phase 0 - Context, Detect & Clarify (mandatory).** Runs at the start of every invocation. Closes the **intent gate** before anything else proceeds.

   **3a. Read existing context / resume.**
   - Read `<SHARE_DIR>/context.md` if it exists (version, edition, module list, instance URL) - resolve `<SHARE_DIR>` (and `<ISOLATE_DIR>` where noted below) via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` before the first Read/Write/Edit of any state-root path in this skill.
   - Check `<ISOLATE_DIR>/brainstorm/state.json` - if an in-progress brainstorm session exists, resume it (Tier 2).
   - **Check for an active run** - glob `<ISOLATE_DIR>/run-*.json` for any with `status: NEEDS_NEXT`. If one exists, do NOT silently open a second RUN-DAG. Surface it and ask: resume it (hand to `run-harness`), or start fresh? Only proceed to open a new run once the user chooses.
   - **Check for existing recon** - glob `<ISOLATE_DIR>/recon/*/findings.md` for this intent's slug.
     A match whose `target_ref:` header line (schema: `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md`
     clause 2) equals the current ref (`git rev-parse --abbrev-ref HEAD`, or the short SHA when
     `HEAD` is detached) -> READ it and SKIP Phase R's dispatch entirely (resume rule: clause 1 of
     the same contract). A mismatch -> STALE - fall through to Phase R, which re-dispatches and
     overwrites the file per clause 1.

   **3b. Detect the working directory (4 branches).** Locate Odoo manifests with:
   ```bash
   find . -maxdepth 3 -name "__manifest__.py" 2>/dev/null | head -20
   ```
   Branch on the result:
   - **(i) Odoo addon dir (≥1 manifest, no usable context file)** → ask for Odoo **version / edition (CE|EE|custom) / target module(s) / instance URL**. Note that `odoo-onboarding` can bootstrap a full `<SHARE_DIR>/context.md` (schema documented in `odoo-onboarding` § Context file schema - do not copy it here).
   - **(ii) Project root (manifests under nested dirs / mono-repo)** → infer common parent as project root; confirm version/edition once, then continue.
   - **(iii) Non-Odoo dir (0 manifests)** → discriminate by intent:
     - **(iii-a) general Odoo Q&A**, no local code needed → **proceed standalone**; record `Project: non-Odoo workspace (general Odoo Q&A)` + `OSM: standalone`.
     - **(iii-b) touches local code/instance** but 0 manifests found → addon is likely outside maxdepth-3: **ask for the addon path / instance URL and re-probe**; if still 0, proceed standalone with a caveat.
     - **(iii-c) purely non-Odoo** (HR/finance/legal/PR/general writing) → § Multi-plugin routing.
   - **(iv) `<SHARE_DIR>/context.md` already present and usable** → use it as-is; **skip** re-asking version/edition/module.

   **3c. OSM probe + version resolution.** Call `mcp__odoo-semantic__list_available_versions`, then branch:
   - **OSM reachable AND `<SHARE_DIR>/context.md` carries an `odoo_version`** → mark `backed`. Do NOT re-ask the version.
   - **OSM reachable BUT version unknown** → **default: escalate to `odoo-onboarding`** (it lists versions/profiles, lets the user pick, validates, and persists `<SHARE_DIR>/context.md`). **Inline fallback** (only when user declines onboarding): call `list_available_versions` → present version menu → `list_available_profiles` filtered to chosen version → pick profile using same logic as `odoo-onboarding` Step 3 → `profile_inspect(method='summary', …)` to confirm. Record version + profile in the Proposed Plan only, stating "used for this turn; run `odoo-onboarding` to persist it". Mark `backed`.
   - **OSM absent/unreachable** → mark `standalone`. If the intent needs a version, ask the user for it and proceed on that.
   Record `OSM: backed | standalone` in the Proposed Plan.

   **3d. GATE - Intent / Purpose / Expected outcomes (MANDATORY).** All three MUST be clear before Phase R may run: **what** the user wants, **why**, and **what done looks like**. Resolve any gap with **pre-structured options** (e.g. "Is the goal (a) ship a code change, (b) scope a proposal, (c) produce marketing copy?"), never an open-ended "what do you want?". **If intent / purpose / expected outcomes are not all clear, you MUST NOT proceed to Phase R.**

4. **Confidentiality (public repo - 8 banned groups).** Do not surface, quote, or transmit: CEO personal info, customer PII/contracts, internal pricing, competitor intelligence beyond public sources, product roadmap details, marketing-in-draft, OKR/targets, vault paths. If a user prompt contains such data, acknowledge intent only - do not echo it.
5. **Main-context only.** This skill is the front door and orchestrator; it MUST NOT be called from inside a subagent. It owns the ADMISSION gate (the text Proposed-Plan gate) and the initial routing decision. It does NOT call `EnterPlanMode`/`ExitPlanMode` on any path - Plan Mode is owned by the plan-authoring skill it dispatches (`odoo-planning`, or a self-gating orchestrator).
6. **Worktree isolation - universal git-safety default (no exceptions).** Before ANY dispatched skill/workflow writes a git-tracked file or commits, a dedicated worktree/branch MUST be provisioned via `git-toolkit:git-ops` and the write happens there - never in the principal checkout (a direct mutation corrupts any other session on that branch). Applies on EVERY path out of intake - Tier-1/3 fast-path, Tier-4 brainstorm, the trivial inline-micro-plan case, the Plan-Mode-exempt fast-paths. ENFORCEMENT: a `writes-files` node is provisioned by `run-harness` at dispatch (Phase P engage #2); intake provisions directly only for a `writes-files` skill it Skill-tool-dispatches WITHOUT a run file. Self-provisioning specialists (SSOT set: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists) isolate internally; `odoo-coding` self-provisions if it gets none. **Exempt:** read-only work (recon, review of `TARGET=local`, brainstorming) and deliverables confined to the `$ODOO_AI_HOME` state root (per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) or `/tmp`. Mechanics (SSOT - do not restate): `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

## Anti-rationalize gate

> **No execution skill fires until the user has approved a Proposed Plan.**

Two enforcement layers, both required: the **text gate** (Proposed Plan block; user types `approve / refine / cancel`) and, on top of it whenever the approved step **writes files**, **Plan Mode** (the harness-level guarantee). The text gate alone is insufficient when file writes are about to occur.

**Red Flags - phrases that trigger STOP + re-gate:**
- "This is simple, I'll just start coding" → STOP. Still propose + gate.
- "The user clearly wants X, skip the questions" → only valid via Tier-1 fast-path, NOT a rationalization to skip the gate.
- "I'll plan, then build the deliverable in the same turn" → STILL GATED. Writing a design/plan artifact is fine; producing the routed deliverable (production code, proposal) or dispatching a writes-files specialist before approval is not.
- "The gate is unnecessary friction here" → wrong. The gate IS the contract.
- "The text gate was enough, I can skip Plan Mode" → WRONG. Plan Mode is mandatory when an execute-skill will write files. The text gate and Plan Mode are independent layers.

## Phase R - Recon (read-only current-state + inventory discovery)

**When**: AFTER Phase 0 closes the intent gate, BEFORE the Proposed Plan. Recon turns a generic plan into a context-aware one.

**What it does** - survey, never mutate:
- Launch **≤1-2 READ-ONLY recon subagents** (`Explore`, or an anonymous recon agent) at **haiku or sonnet** - never opus/fable by default (mechanism, unstated-model hazard, and escalation gate: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection, Recon/scouting phase default - reference it, never restate it here) - to map code/modules relevant to the stated intent; a read-only leaf skill (e.g. `odoo-feature-check`) is instead invoked via the Skill tool. These agents do not write files and do not spawn. When the CHP capability probe is positive (Agent Team mode on), TaskCreate one task per dispatched work-item, inject TASK_ID + REPLY_TO: <this skill's current orchestrating context> (`main` when the main-context driver invoked this skill; do NOT hardcode a literal `main` if running nested inside a non-lead agent) + NOTIFY: <dependent names> into each teammate brief, poll TaskList/TaskGet for status, and read each result from the teammate's SendMessage push (NEVER from the .output transcript) - per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When off, dispatch + collect as today.
- Call read-only OSM tools as needed: `model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`.
- When recon reads a document that IS the requirement SSOT (RFP / contract / spec / requirement list), extract it faithfully per `${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md` - verbatim/structured, never an interpretive summary that invents specifics.
- **Persist before you propose (MANDATORY).** After the recon subagents return, YOU (not they) write
  their findings to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md`: a `target_ref:` header line
  (the current `git rev-parse --abbrev-ref HEAD`, or short SHA when detached) followed by the
  capped four-field record rows, then reference that path in the Proposed Plan. The `target_ref:`
  header is what Phase 0 3a's staleness read-back (above) checks on resume. Contract (full schema):
  `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 2. The subagents stay
  write-free, but YOUR write is never a paraphrase - transcribe each subagent's returned findings
  VERBATIM: when only one subagent ran, its return fills `findings.md` fact-for-fact; when two ran,
  the second's verbatim return goes to its OWN sibling `findings-2.md` (never merged into
  `findings.md`) and `findings.md` names it in a closing `siblings:` line - clause 3 (verbatim
  per-agent capture) of the same contract owns this schema; a summarized digest standing in for
  either subagent's actual return is not compliant. Cannot resolve `<ISOLATE_DIR>` (resolver REFUSAL) -> proceed with the plan and record
  `Findings (Recon): <bullets> (not persisted - state root unresolvable)`; never block intake on it.

**Inventory discovery (hybrid).** Pull each fact from its SSOT:

| Need | Source | How to fetch |
|---|---|---|
| skill / agent / command exists + its description | runtime context (harness-injected) | already available - do NOT read files for this |
| `model_tier` (Haiku/Sonnet/Opus/inherit) | the `model:` frontmatter of the candidate's `SKILL.md` / `agents/*.md` (SSOT) | read the frontmatter of the CHOSEN candidate only; **if absent, treat as `inherit`** |
| `output_mode` (`chat-only` ⇄ `writes-files`) | `orchestration.<skill>.output_mode` in `skill_tool_deps.json` | read that field directly |
| `effort` (S / M / L / XL) | NOT registered - skill×task property | reason per the `odoo-gap-analysis` effort legend (SSOT) |

`model_tier` lives in frontmatter and `effort` is per-task - NEVER copy either into a registry.

**Hard limits**: read-only, leaf - must not spawn further (see `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`), no file writes. If OSM is unreachable, proceed on user-provided context (standalone).

## Plan Mode - harness-level pre-execute gate

**Decision tree (run first)**: read the chosen Approach's `output_mode` from `skill_tool_deps.json`.
- `output_mode = writes-files` → **Plan Mode REQUIRED** before dispatch. **Exceptions that SKIP Plan Mode:**
  - `odoo-deep-survey` (dispatched via the `deep-survey` gate keyword) - the opt-in keyword is the human gate.
  - `odoo-code-review` and `odoo-debug` - a **review** intent (routing row 13) or **debug** intent (routing row 29) fast-paths straight to the skill once Phase 0 intent gate is closed: emit the one-line § Pro fast-path gate, on `yes` invoke via Skill tool - NO Proposed-Plan blocks, NO Plan Mode. These two then drive their own autonomous fix loop. Hard rule 6 (worktree isolation) still applies to any write these trigger - each owns it internally before touching a file (`git-delegation.md`); skipping intake's Plan Mode never means skipping worktree isolation.
  - `odoo-forward-port` (P4 gate), `odoo-git-rebase` (P6 gate), `odoo-modules-upgrade` (P3 gate) - each uses the shared Plan-Mode gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit) for its own approval (EnterPlanMode/ExitPlanMode called internally; plan presented before any branch/worktree/merge/adapt). Intake MUST NOT call EnterPlanMode for these; dispatch directly after the § Soft plan gate "stronger gate" one-liner is acknowledged. Each already satisfies Hard rule 6 internally (own worktree/branch per `git-delegation.md`) - intake does not double-provision.
  - `odoo-brl` - a self-gating FRONT-DOOR plan-establisher (`planning-gate-contract.md` names it a FRONT DOOR alongside `odoo-intake` and the `odoo-implement-feature` workflow): it presents its OWN text gates (GATE 0 before classification, GATE E before writing deliverables - `skills/odoo-brl/SKILL.md`), never the harness Plan Mode. It is dispatched directly once intake's own Proposed-Plan is approved (Hard rule 2(a)) - NOT additionally gated behind a separate pre-BRL `odoo-planning` dispatch.
  - `odoo-solution-design`, and any other `output_mode = writes-files` skill that persists ONLY under the `$ODOO_AI_HOME` state root (never a git-tracked path - e.g. a Technical Design Document at `<SHARE_DIR>/design/...`) - SKIPS Plan Mode: **Plan Mode gates git-TRACKED writes, not state-root writes.** Such a skill is likewise exempt from worktree isolation (Hard rule 6) for the same reason.
- `output_mode = chat-only` → **SKIP Plan Mode**; intake ends its turn and the specialist fires via the Skill tool on the next turn.

**When it applies**: after user approves the Proposed Plan AND the next step is an execute-skill that will **write or modify files** - specifically `odoo-coding`, `odoo-brl`, `workflow-chaining`, or any skill whose output column is NOT "chat only".

**Who enters Plan Mode**: the plan-authoring skill (`odoo-planning`) dispatches its two planners (`odoo-planner`, `odoo-doc-planner`) FIRST - they author the plan artifact under the `$ODOO_AI_HOME` state root, which does NOT require an open Plan Mode window - THEN `odoo-planning` enters Plan Mode itself, after both planners return and before presenting the plan for approval; intake never does. `EnterPlanMode`/`ExitPlanMode` are main-context tools and both intake and `odoo-planning` run in the main context, but exactly one enterer is pinned - the author - so the enter cannot be misordered. Semantics: `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit + plan_mode_active.

**Does NOT apply** for any `chat-only` skill (per the decision tree - e.g. `odoo-feature-check`, `odoo-version-diff`, `odoo-gap-analysis`, `odoo-discovery-summary`, `odoo-capability-proof`, `odoo-content-draft`), NOR for a `writes-files` skill covered by the state-root-only-writer exception above (`odoo-solution-design` and its class - see § Plan Mode decision tree: Plan Mode gates git-TRACKED writes, not state-root writes). `odoo-planning` owns its own Plan Mode: it dispatches both planners first (they author the plan under the state root, which needs no Plan Mode window), then enters Plan Mode itself AFTER both return and BEFORE presenting the plan for approval (SSOT: planning-gate-contract.md) - intake dispatches it WITHOUT pre-opening (never passes `plan_mode_active: true`), so there is exactly one enterer and it enters before the plan is presented. The SKIP-list skills above (`odoo-deep-survey`, `odoo-code-review`, `odoo-debug`, `odoo-forward-port`, `odoo-git-rebase`, `odoo-modules-upgrade`, `odoo-brl`) each drive their own gate the same way - self-entering (or, for `odoo-brl`, self-text-gating via its own GATE 0/GATE E) before their own authoring/branch/write.

**Procedure** (execute-skill that touches files):
1. User sends `approve` on the Proposed Plan.
2. Main agent dispatches the mandatory `odoo-planning` via the **Skill tool** - WITHOUT `plan_mode_active` - with a brief composed per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (OBJECTIVE/SCOPE/INPUTS/ACCEPTANCE - `INPUTS` carries the resolved Proposed Plan `Survey:` path when one exists, explicit `none` otherwise, so `odoo-planning` can pass it on to `odoo-planner`'s `SURVEY:` field). `odoo-planning` dispatches its two planners (`odoo-planner`, `odoo-doc-planner`) FIRST - they author the 3-block plan (module list, dependency graph, assignment) under the `$ODOO_AI_HOME` state root, which does NOT require an open Plan Mode window - THEN `odoo-planning` enters Plan Mode ITSELF, after both planners return and before presenting the plan (its own guard; SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit), presents it, and calls **`ExitPlanMode`** itself once the human approves in the Plan Mode UI. Intake calls NEITHER `EnterPlanMode` NOR `ExitPlanMode` on this path; intake does not draft plan content itself either (see § Plan Mode Content Schema below).
3. `odoo-planning` hands control back to intake via its Continuation Contract (`next: odoo-intake`) once the plan is approved - this then engages **Phase P**.
4. **Worktree isolation (Hard rule 6, no exceptions).** Self-provisioning specialists (SSOT set: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists) provision internally - skip this step. On the common path a `writes-files` Approach engages Phase P and `run-harness` provisions at dispatch. Only in the non-Phase-P case, BEFORE dispatch, invoke `git-toolkit:git-ops` via the Skill tool to create a worktree/branch and pass its path into the brief (`WORKTREE_PATH` for `odoo-coding`, else `TARGET: worktree:<path>`). The principal checkout is NEVER the target. Mechanics: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
5. ONLY after Plan Mode approval AND worktree provisioning, the dispatcher invokes the execute-skill via the **Skill tool** (`run-harness` in the common case, else the main agent directly; a skill is not an agentType, so launching an agent by a skill name fails - see § Dispatch mechanism).

The self-gating skip-list skills (`odoo-forward-port`, `odoo-git-rebase`, `odoo-modules-upgrade`, `odoo-deep-survey`, `odoo-code-review`, `odoo-debug`) each own their own gate exactly the same way - they call `EnterPlanMode`/`ExitPlanMode` internally, before their own authoring/branch/write; intake dispatches each directly (§ Plan Mode decision tree above) and calls neither tool for them either.

**Red flags for Plan Mode**:
- "The user already said approve, I can skip dispatching `odoo-planning`'s Plan Mode gate" → NO. Text-gate approval and Plan Mode approval are two separate steps.
- "I'll enter Plan Mode after I've already started editing" → BANNED. EnterPlanMode must come before any file touch.
- "I'll enter Plan Mode before dispatching the planners, to be safe" → UNNECESSARY and out of order for `odoo-planning`: the planners write ONLY under the `$ODOO_AI_HOME` state root (no Plan Mode window needed for that), so `odoo-planning` enters Plan Mode AFTER both planners return and BEFORE presenting the plan - never before dispatching them (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit, the amended WHEN clause).
- "`odoo-deep-survey` writes files, so it needs Plan Mode" → NO. It is the one `writes-files` exception (analysis-only under `<SHARE_DIR>/survey/`, gated by the `deep-survey` opt-in keyword).
- "This is a trivial single-WI fix / an ambiguous case I couldn't fully classify, worktree isolation can wait" → NO. Hard rule 6 is a catch-all default: trivial and ambiguous work that touches git-tracked files is provisioned into a worktree exactly like any other, before dispatch.

### Plan Mode Content Schema

The implementation plan (step 2 above) is a 3-block `writes-files` plan, authored by `odoo-planning`'s two planners under the state root and then presented inside Plan Mode; its schema is SSOT at `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` (block schemas incl. the REQUIRED module-DAG ASCII dep-graph, worked examples, rejection flow). **ALWAYS delegate 3-block authoring to `odoo-planning`** (its `odoo-planner` produces the wave-batched module-DAG + integration cadence + lifecycle wiring); intake NEVER writes the plan inline - planning is mandatory for all work (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule). **Intake dispatches it WITHOUT `plan_mode_active`** (never passes it as `true`) - `odoo-planning` dispatches both planners first (they author under the state root), then enters Plan Mode itself AFTER both return and BEFORE presenting the plan, per its own guard (`skills/odoo-planning/SKILL.md` § Plan Mode guard).

The minimal `writes-files` plan `odoo-planning` emits for a single-module change is `[code, review, integrate]`; the `integrate` land tail (git-ops open-PR -> `odoo-pr-monitoring` @ L2) is SSOT at `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Terminal integrate land node.

**Rejection flow (summary):** if the user refines/rejects in the Plan Mode UI, loop back to the soft-plan-gate (not execution); re-enter Plan Mode only after the revised plan is re-approved at the text gate. Full detail in the reference above.

## Dispatch mechanism - Skill tool, not a direct agent launch

| Target | What it is | How the main agent dispatches it |
|---|---|---|
| a **skill** (`leaf` or `spawner-agent`) - e.g. `odoo-code-review`, `odoo-coding`, `odoo-feature-check`, `odoo-planning` | a **skill**, NOT an agentType | **Skill tool** (deterministic). For a `spawner-agent` skill the Skill tool loads it in the main context so the skill itself fans out its own subagents. |
| a **workflow** - e.g. `qa-suite`, `video-produce` | a `*.workflow.yaml` | its **command** / NL-dispatch |
| a **command** - e.g. `/odoo-respond-bid` | a slash command | the user's slash kickoff / its command |

Skills always go through the Skill tool: a skill name is not an agentType, so passing one to an agent launch fails. A `spawner-agent` skill must run in the main context so the Skill tool can load it there and let it launch its own subagents. Agents are launched directly - inside intake, only the Phase R read-only recon agent. Full rationale: `references/maintainers.md`.

When composing the dispatch prompt for any specialist agent you dispatch (including the Phase R
recon agent), fill the caller-side skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`
(read it by path) plus the target agent's family delta; never inline that file verbatim into a
hard-leaf brief.

## Phase P - RUN-DAG persistence + drive-to-done (optional, additive)

This phase turns an approved plan into a self-advancing run. It is **purely additive**: single-step plans dispatch as before - Phase P only matters for multi-step work or hands-off execution.

**Engage Phase P** (after plan approval) if ANY holds: (1) `node_count >= 2`; (2) a single `output_mode == writes-files` node; or (3) a single workflow node whose YAML declares `on_complete`. Otherwise SKIP and dispatch directly. When engaged, serialize the approved 3-block plan into `<ISOLATE_DIR>/run-<id>.json`, tag gate-tiers, and NL-dispatch `run-harness`. Parse the autonomy dial from the prompt (`--auto` / `--step` / `--plan`); default `--auto` if no flag is present.

**When engaging Phase P, read `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md`** for the full engage/skip rule, serialization procedure, autonomy-dial semantics, and workflow-as-node routing. Full schema + loop: `docs/reference/workflow-harness.md` §8.

## Multi-plugin routing - stay Odoo-centric

When Phase 0 detects intent **outside the Odoo domain** (HR/recruiting, finance/budget, legal/compliance, internal ops, PR, broad market research with no Odoo hook):
- Route to the appropriate other surface (vault research/capture skills, another installed plugin), OR
- If nothing fits, say so plainly and flag it as out-of-plugin - let the main agent decide.

This plugin owns the **Odoo** domain. Do not invent an Odoo skill to cover a non-Odoo need.

## 4-tier routing

Run tiers in order; first hit wins; cost rises per tier.

| Tier | Mechanism | Token cost | Action |
|---|---|---|---|
| **1 - regex/intent** | Explicit verb+noun pattern: "write computed field", "diff v16 v17", "review this PR", "/..." | 0 | Exact specialist → **pro fast-path** (see § Pro fast-path) |
| **2 - session state** | `<ISOLATE_DIR>/brainstorm/state.json` exists and contains in-progress brainstorm | 0 | Resume that brainstorm thread |
| **3 - keyword table** | 63-row routing table (see § Routing Table) covering all 9 persona domains | 0 | Map to single skill or workflow → soft-plan-gate |
| **4 - LLM classify** | Only on Tier 1-3 miss: classify the ambiguous prompt (~500 tok) | ~500 tok | Single clear target → gate; vague/multi-domain → **enter brainstorm** |

Brainstorm fires ONLY when Tier 1-3 all miss AND Tier-4 returns either (a) **no confident single target** (≥2 candidate skills with no decisive discriminator), or (b) a **large / multi-domain job** (≥10 requirement items, OR a scale signal like "hundreds of requirements" / "win this deal end-to-end" / "plan + build + ship an upgrade"). **Do NOT brainstorm a question that resolves to ONE specialist** - a lone capability question ("can Odoo handle X", even in reported speech) is a Tier-3 hit to `odoo-feature-check`, not a vague job; brainstorm is for genuinely open-ended or multi-domain intent, never a hedge against a single clear answer.

## Pro fast-path

When Tier 1 or Tier 3 yields exactly ONE specialist AND the prompt contains a concrete action verb + object, skip brainstorm entirely and emit a **one-line soft plan gate**:

```
Plan: run `<skill-name>` to <one-line outcome>. Proceed? (yes / brainstorm instead / cancel)
```

A pro user types "yes" once. A novice can opt into brainstorm. This guarantees brainstorm-first never blocks an expert.

**Canonical behavior on a clear single-step match (removes the fire/no-fire ambiguity).** A clear match is NOT a reason to skip the gate - gate-before-execution (Hard rule 1) has no exception. So the outcome is always the one-line fast-path gate above (intake engages, states the target, and stops for `yes`); there is NO "silent passthrough that runs the specialist ungated". Two - and only two - outcomes are genuinely "intake never engages": (a) an explicit `/slash` command (the harness invokes it directly and intake never sees the turn), and (b) the user is already mid-workflow inside another skill. The description's `DO NOT trigger ... let it fire directly` clause is a *harness-triggering* hint (prefer surfacing the specific specialist over intake); it does NOT mean that, once consulted, intake executes without a gate. The read-only/chat-only fast-paths (`odoo-code-review`, `odoo-debug` - see § Plan Mode) still emit this one-line gate; they only skip the heavier Plan Mode.

## Brainstorm (6-step)

Only runs in the **vague branch** (Tier-4 miss or explicit "I'm not sure").

1. **Explore context (STATIC only)** - read `<SHARE_DIR>/context.md`, list existing artifacts under the `$ODOO_AI_HOME` state root (SHARE/ISOLATE dirs per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), infer domain and persona. STATIC = filesystem reads only (no agent launch, no OSM calls). Dynamic recon that dispatches agents + calls OSM is Phase R (not this step).
2. **Clarifying options** - present 2-3 **pre-structured options** (not open-ended questions), e.g. "Is this (a) sales/proposal, (b) engineering upgrade, (c) strategy?". **Multi-turn boundary:** if intent/purpose/outcomes are already clear, continue in the same turn; if not, emit options and **END THE TURN** - next turn resumes via Tier-2. Do not run Phase R until the intent gate is closed (Hard rule 3d).
3. **Propose 2-3 approaches** - each with: one-line outcome + key trade-off + recommendation. Informed by Phase R findings.
4. **Present Proposed Plan** (soft-plan-gate - see § Soft plan gate). This IS the gate.
5. **Write design doc** - intake MAY write `<ISOLATE_DIR>/brainstorm/<slug>-<date>.md` during the plan turn. The approval gate covers the routed deliverable, not the planning artifact.
6. **Transition** - emit the NL-dispatch prompt for the chosen skill/workflow; update `<ISOLATE_DIR>/brainstorm/state.json`.

**Where Phase R fits (ALL paths, not just brainstorm):** Phase R runs AFTER the intent gate closes and BEFORE the Proposed Plan, on both fast-path and brainstorm. In the brainstorm flow it sits between step 2 (intent closed) and step 4 (Proposed Plan), so its findings inform step-3 approaches and fill the `Findings (Recon)` field.

## Soft plan gate

Universal gate emitted by intake at the end of every brainstorm or fast-path turn:

**Exception - skills that own a stronger gate.** When the routed skill opens with its own richer STOP
plan gate (`odoo-forward-port` P4, `odoo-git-rebase` P6, `odoo-modules-upgrade` P3 - each in harness
Plan Mode after its own intent-extract/classify/design), do NOT emit the full `## Proposed Plan`
block; launch directly with a single acknowledgment one-liner: "Launching `odoo-forward-port` - it
will present its own per-commit plan and stop for your approval before any branch or merge."
(Substitute the actual skill name.) Two approval gates for one action is friction; the skill's own
gate is authoritative. Phase P does NOT engage for these skills either - a self-gating + self-resuming
skill (Plan Mode gate + checkpoint.json resume) owns its own run-DAG; intake dispatches it once and
the skill drives itself.

```
## Proposed Plan
Project:        <repo / project root, or "non-Odoo workspace">
Odoo version/edition: <e.g. 17.0 / EE | CE | custom | "n/a">
Intent / Purpose / Expected outcomes: <what / why / what done looks like - from the Phase 0 gate>
Domain:         <one of 9 persona buckets>
Approach:       <skill name | workflow name | command>
Chain:          <skill> → <skill> ...   (for multi-step; "single turn" for atomic asks)
Findings (Recon): <1-3 bullets from Phase R: what already exists / hook points / impact>
Findings file:  <ISOLATE_DIR>/recon/<slug>-<date>/findings.md   (or "not persisted - state root unresolvable")
Survey:         none | <SHARE_DIR>/survey/<slug>-<date>/synthesis.md   (deep-survey synthesis path, if a deep survey was run)
Modules (preview): <module-A …, module-B … - disjoint; "single module" for atomic asks>
Assignment (skill/agent + effort + est_agents): <module → skill|agent (effort S/M/L/XL, est_agents N - ADVISORY/du kien; model + count owned by the dispatched skill at runtime, never bound here)>
Output:         `$ODOO_AI_HOME` SHARE/ISOLATE path (tier per the routed skill's actual subdir - see `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), e.g. <SHARE_DIR>/<subdir>/<slug>-<date>.<ext>   (or "chat only")
Est. effort:    <S / M / L / XL / "single turn">
OSM:            backed | standalone   (backed if OSM (`mcp__odoo-semantic__*`) tools are available; standalone if not)
Plan Mode:      required | not | skill-owned   (skill-owned when the routed skill drives its own Plan Mode - e.g. odoo-forward-port at P4, odoo-git-rebase at P6, odoo-modules-upgrade at P3)
Next turn:      invoke the routed **skill** via the **Skill tool** (workflow/command: via its command) - you will see the tool call

Gate: approve / refine: [your feedback] / deep-survey / cancel
```

When the job is **large** (≥10 requirement items or a scale signal, OR a code job spanning ≥3 modules / a cross-cutting model change), add one offer line under the plan: "This plan is built on a light Phase R recon. Want me to run a **deep survey** (`deep-survey` - many subagents, real tokens) and re-propose a sharper plan?". Omit for small/atomic asks.

Enforcement stack:
1. Hard rule 1 → intake may write planning/design artifacts, but NOT the routed deliverable, before approval.
2. Anti-rationalize gate + Red Flags → behavioral enforcement (text gate layer).
3. Plan Mode (EnterPlanMode / ExitPlanMode) → harness-level guarantee before any execute-skill that writes files (the stronger layer).
4. On `approve` → if the next step writes files, main agent dispatches the mandatory `odoo-planning` (Skill tool, WITHOUT `plan_mode_active`) BEFORE invoking the specialist - `odoo-planning` dispatches its two planners first (they author the plan under the state root), then calls `EnterPlanMode` itself AFTER both return and BEFORE presenting the plan. If chat-only/read-only, intake ends its turn and the specialist fires via the **Skill tool** on the next turn.
5. On `refine: [feedback]` → loop back within brainstorm. On `cancel` → stop + brief report.
6. On `deep-survey` → run the opt-in deep survey, then re-propose (see § Deep survey).
7. Hard rule 6 (worktree isolation) → before any writes-files dispatch a dedicated worktree/branch MUST be provisioned (common case: Phase P → `run-harness`; rare non-Phase-P case: inline per § Plan Mode Procedure step 4); the principal checkout is never the target, on any path.

### Deep survey (opt-in)

On `deep-survey`:
1. Invoke **`odoo-deep-survey` via the Skill tool** (a `spawner-agent` skill - the Skill tool loads it in the main context so it fans out workers as subagents). Pass it the closed intent/purpose/outcomes, the resolved Odoo version + profile, the feature slug, and the first Proposed Plan.
2. **No Plan Mode.** `deep-survey` writes only analysis artifacts under `<SHARE_DIR>/survey/` (never the routed deliverable), and the `deep-survey` keyword IS the human gate.
3. When it returns a `synthesis.md` path, **re-propose** the Proposed Plan: fill the `Survey:` field with that path; update `Approach` / `Chain` / `Findings` / `Workitems` / `Est. effort` from the synthesis. Re-gate with `approve / refine / cancel` - **drop `deep-survey`** from the re-proposed gate (survey runs at most once).
4. Downstream execute-skills read `synthesis.md` (carried in `Survey:` and, for a RUN-DAG, in the `run-<id>.json` node inputs).

## Routing Table

Use this as Tier-3 keyword routing. Pick the **single best match** based on intent signals. The **Discriminator** column resolves close ties.

| # | Intent signal | Target skill | Discriminator (when ambiguous vs neighbour) |
|---|---|---|---|
| 1 | "risk", "safe to upgrade", "blast radius", executive 1-page summary | `odoo-risk-overview` | Executive audience + risk score output (vs `odoo-deprecation-audit` which is code-level audit) |
| 2 | "inventory", "list all customizations", "what have we built" | `odoo-customization-inventory` | Module-list deliverable for CEO/PM (vs `odoo-risk-overview` which scores risk) |
| 3 | "where to hook", "override method", "best place to extend", "which method should I override" | `odoo-override-finding` | Hook location question for ONE method (vs `odoo-coding` which writes the override) |
| 4 | "deprecated", "what will break", "audit before upgrade", "old API", "leftover OpenERP code" | `odoo-deprecation-audit` | Code-level audit (vs `odoo-version-diff` which is pure API diff, vs `odoo-risk-overview` which is executive) |
| 5 | "what changed between", "diff v16 v17", "API changes", "new features in Odoo X" (dev framing) | `odoo-version-diff` | Version-to-version comparison (vs `odoo-feature-highlights` which is marketing framing for the same data) |
| 6 | "does Odoo have X", "is X available", "is module Y in CE", "can Odoo handle/do/support X", "someone asked me if Odoo can X", "is it possible to X in Odoo" (reported-speech capability questions count) | `odoo-feature-check` | SINGLE feature/capability lookup - a lone yes/no question is NOT vague, do NOT brainstorm it (vs `odoo-gap-analysis` which handles a LIST of requirements; vs `odoo-capability-proof` which builds an evidence PACKAGE) |
| 7 | "gap analysis", "scope", "effort estimate", "proposal", "customer needs A,B,C - does Odoo have them" | `odoo-gap-analysis` | Multi-requirement -> effort matrix (vs `odoo-feature-check` for single feature) |
| 8 | "feature highlights", "slide", "blog post", "marketing", "release notes for non-developers", "newsletter" | `odoo-feature-highlights` | Marketing/business audience (vs `odoo-version-diff` which is dev-track diff) |
| 9 | "CE vs EE", "edition comparison", "what does Enterprise add" | `odoo-addon-diff` | Three-way edition comparison (vs `odoo-feature-check` which is single-feature) |
| 10 | "prove Odoo can", "evidence for demo", "RFP evidence", "before the demo", "competitor said Odoo can't" | `odoo-capability-proof` | Evidence PACKAGE (modules + code + demo steps) (vs `odoo-objection-handling` which produces a verbatim response paragraph) |
| 11 | "respond to objection", "counter 'Odoo can't'", "write a response", "rep is on the call", "customer says Odoo can't do X" | `odoo-objection-handling` | Verbatim ACA response paragraph (vs `odoo-capability-proof` which is technical evidence) |
| 12 | "write code", "create field", "implement feature", "write computed field", "add onchange", "add SQL constraint" | `odoo-coding` | The single coding front door - backend Python/XML AND frontend (see row 14). It works out per-module whether the change is backend-only / frontend-only / full-stack and dispatches the right agents (vs `odoo-override-finding` for finding a hook location, vs `odoo-code-review` which reviews existing code) |
| 13 | "review code", "check my PR", "audit this", "smell test before merge" | `odoo-code-review` | Reviewing EXISTING code (vs `odoo-coding` which writes NEW code, vs `odoo-deprecation-audit` which is module-level audit) |
| 14 | "JS", "widget", "OWL", "frontend", "any Odoo version", "odoo.define()", "useService", "patch component" | `odoo-coding` | Same unified coding skill (frontend leg) - legacy v8-14 or OWL v15+; auto-detects framework + which stacks a change needs via the Odoo version in `<SHARE_DIR>/context.md` or the user statement |
| 15 | "follow up with customer", "deal stalled", "draft follow-up email", "customer hasn't replied" | `odoo-deal-followup` | Sales AE follow-up email writer (vs `odoo-objection-handling` for objection response, vs `odoo-discovery-summary` for raw meeting notes) |
| 16 | "summarize the customer meeting", "synthesize discovery notes", "extract customer profile" | `odoo-discovery-summary` | Pre-proposal structured profile (vs `odoo-gap-analysis` for effort matrix, vs `odoo-deal-followup` for post-meeting follow-up email) |
| 17 | "write a blog post on Odoo", "draft a LinkedIn post", "YouTube script for Odoo", "email sequence about", "landing page copy" | `odoo-content-draft` | Single-piece content draft (vs `odoo-campaign-plan` which orchestrates multi-piece campaign, vs `odoo-feature-highlights` which is slide-format) |
| 18 | "plan a campaign", "plan campaign Q3", "multi-channel plan", "campaign brief" | `odoo-campaign-plan` | Multi-week orchestration (vs `odoo-content-draft` for single piece) |
| 19 | "competitor brief", "competitive analysis", "landscape brief", "threat assessment" | `odoo-competitive-brief` | Structured CEO/board briefing on a competitor (vs `odoo-objection-handling` for sales counter-talking-points) |
| 20 | "deploy checklist", "checklist before going live", "go-live checklist", "pre-deploy safety" | `odoo-deploy-checklist` | Pre-deployment safety items (vs `odoo-deprecation-audit` for code-level upgrade audit) |
| 21 | "I just cloned the Odoo repo", "set up Odoo for this project", "first time setup" | `odoo-onboarding` | Project-context bootstrap (vs `/odoo-semantic-mcp:connect` slash command for server URL/key setup) |
| 22 | "setup MCP server URL + API key" | `/odoo-semantic-mcp:connect` (command) | One-time infra setup, not work |
| 23 | "full bid response" / "write a complete RFP response" / "full proposal for prospect" | `/odoo-respond-bid` (command) | Multi-step proposal chain (vs `odoo-discovery-summary` or `odoo-capability-proof` alone) |
| 24 | "write follow-up email for customer" + explicit save-to-file ask | `/odoo-draft-followup` (command) | Wraps `odoo-deal-followup` with save step (skill alone for just draft text) |
| 25 | "synthesize discovery notes" + explicit slash kickoff | `/odoo-summarize-discovery` (command) | Quick slash for `odoo-discovery-summary` skill (bypass intake for explicit kickoff) |
| 26 | "position feature X for [slide/blog/email/proposal]" | `/odoo-position-feature` (command) | Multi-step chain (vs `odoo-feature-check` for existence-only) |
| 27 | "full upgrade plan from v<N> to v<M>" | `/odoo-plan-upgrade` (command) | Replaces legacy `odoo-upgrade-planner` agent; chains 4 skills + effort estimate |
| 28 | "kiểm tra giao diện / form hiển thị sai / UI review / responsive / layout vỡ" | `odoo-ui-review` | Rates a RENDERED screen in the browser (vs `odoo-coding` which WRITES the JS, vs `odoo-code-review` which reads source STATICALLY without a browser) |
| 29 | "console error / OWL render lỗi / trang trắng / widget không hiện / JS runtime error" | `odoo-debug` | Front-door for ALL debugging: reproduces, root-causes, dispatches specialist debug agents (vs `odoo-ui-review` which rates a working screen) |
| 30 | "visual regression / so ảnh trước-sau / UI có đổi sau khi sửa / baseline screenshot" | `odoo-visual-regression` | Diffs TWO states/builds for drift (vs `odoo-ui-review` which judges ONE screen once) |
| 31 | "quay video tính năng / demo video / screencast / video marketing" | `odoo-demo-recording` | Produces a REAL video/GIF of a live instance (vs `odoo-capability-proof` which produces TEXT/code evidence, vs `odoo-content-draft` which writes the SCRIPT only) |
| 32 | "setup môi trường / wire MCP / cấu hình instance URL cho visual / lần đầu setup visual" | `/odoo-ai-agents:odoo-setup` (command) | One-time environment bootstrap for the visual stack - wires browser MCP + writes instance URL/visual config to `<SHARE_DIR>/context.md` (vs `odoo-onboarding` which bootstraps project CODE context, vs `/odoo-semantic-mcp:connect` which only sets the OSM server URL/key) |
| 33 | "BRL", "business requirement list", "hàng trăm/nghìn requirement", "classify + cost", "dependency graph", "scope toàn bộ RFP", "1200 requirements", "RTM", "costed plan from requirements", "turn RFP into effort plan" | `odoo-brl` | FLAGSHIP large-scale pipeline: hundreds-to-thousands of items + cost estimate + dependency DAG (vs `odoo-gap-analysis` = short ad-hoc list, no cost/DAG; vs `odoo-feature-check` = single feature). Discriminator: item count scale + explicit cost/RTM/DAG signals |
| 34 | "QA suite", "release test plan", "test-plan doc for module", "deploy safety checklist", "generate tests and triage bugs", "static QA pipeline before release" | `qa-suite` (workflow) | STATIC release artifacts only - test-plan doc + deploy checklist + bug triage, NOTHING executed (vs `odoo-acceptance` which EXECUTES + adjudicates an oracle on a live instance/UI; vs `odoo-code-review` static source review; vs `odoo-deploy-checklist` the checklist phase alone) |
| 35 | "triage ticket", "support ticket", "customer reports Odoo issue", "classify this bug", "draft resolution for support case", "root cause for customer complaint", "escalate this issue", "bug report from client" | `support-triage` (workflow) | Full ticket triage: classify → root-cause → draft resolution/escalation (vs `odoo-debug` which is a dev debug session, vs `odoo-deal-followup` which is sales follow-up) |
| 36 | "multi-scene demo video", "storyboard and record", "assemble scenes into one video", "multi-take product demo", "quay nhiều scene ghép thành một video demo", "record and stitch demo clips" | `video-produce` (workflow) | Multi-scene video production: storyboard → record each scene → assemble (vs `odoo-demo-recording` which records a SINGLE scene/flow, vs `odoo-content-draft` which writes the script only) |
| 37 | "deal close cycle", "full sales closing cycle", "multi-step deal closing", "sales follow-up sequence end-to-end", "close this deal from discovery to signature" | `sales-closing-cycle` (workflow) | End-to-end deal-closing pipeline (vs `odoo-deal-followup` which is a single email draft, vs `/odoo-respond-bid` which produces an RFP response document) |
| 38 | "long debug session", "investigate phiên dài", "multi-turn UI debug", "ui-debug-session", "sustained troubleshooting session for Odoo UI" | `ui-debug-session` (workflow) | Sustained multi-turn UI debug session with state tracking (vs `odoo-debug` which is a single-turn root-cause investigation) |
| 39 | "content brief to publish", "full content production", "content from brief to done", "multi-step content workflow", "brief → draft → review → publish" | `content-production` (workflow) | End-to-end content pipeline: brief → draft → review → publish (vs `odoo-content-draft` which is single-piece draft only, vs `odoo-campaign-plan` which plans the campaign, not produces the pieces) |
| 40 | "do this as a wave", "parallelize these changes", "multi-WI PR with review and squash", "land N related changes safely without touching main", "split this work into parallel worktrees", VI: "chia viec song song", "chay nhu mot wave" | `odoo-planning` | User-facing parallel / multi-module delivery routes to the PLANNER, never to an executor: `odoo-planning` produces the wave-batched module plan (design-first chain `odoo-solution-design -> odoo-planning`); on approval `run-harness` drives the waves via its INTERNAL between-wave integration (ONE run-integration branch + per-module worktrees + cherry-pick + per-wave review + cumulative close-gate + AUTO-ADVANCE with NO per-wave PR, then ONE run-level PR + squash after the FINAL wave, STOP at "PR opened" - it never merges; the merge is owned by the subsequent `odoo-pr-monitoring` at the L2-merge-gate). The between-wave integration is internal to `run-harness` - NEVER route a user prompt to an executor. (vs `odoo-coding` = a SINGLE change, no git orchestration; vs `odoo-brl` = classify/cost requirements, writes NO code) |
| 41 | "design the solution", "thiết kế giải pháp / phân tích thiết kế", "how should I architect / structure this", "which approach", "design the data model", "plan the refactor", "design before we code", "technical design", "architecture decision" | `odoo-solution-design` | Designs HOW to build a non-trivial change into a gate-able design doc BEFORE coding (vs `odoo-coding` which WRITES code, vs `odoo-override-finding` which answers ONE method's hook location, vs `odoo-brl`/`odoo-gap-analysis` which classify WHAT to build + cost). Discriminator: user wants a designed/approved approach, not yet the code |
| 42 | "implement this feature end-to-end", "from requirement to working code", "design then build then review", "scope → design → code → review" | `odoo-implement-feature` (workflow) | End-to-end feature pipeline: gap/brl → solution-design → odoo-coding → code-review (vs `odoo-solution-design` which produces ONLY the design, vs `odoo-coding` which writes ONE change with no design/review phases) |
| 43 | "make this Odoo UI look good", "design the form/kanban/list", "this screen looks cluttered/off", "thiết kế giao diện Odoo đẹp đúng chuẩn", "đúng design-system Odoo", "design a clean portal page" | `odoo-frontend-design` | Knowledge-only DESIGN-QUALITY expertise for Odoo UI/UX (view-type choice, form hierarchy, semantic tokens, website/portal) - loaded by solution-design/odoo-coding and the bar ui-review rates against (vs `odoo-coding` which WRITES the JS/OWL/SCSS, vs `odoo-ui-review` which RATES a rendered screen in a browser) |
| 44 | "viết tài liệu module", "cập nhật tài liệu có ảnh chụp màn hình", "làm static/description cho module", "minh hoạ tài liệu module bằng screenshot", "write module docs with screenshots", "document this module", "screenshot-illustrated module guide", "static description with screenshots", "viết hướng dẫn sử dụng module", "create RST user guide for module", "viết doc/index.rst cho module" | `odoo-doc-illustration` | Produces STATIC screenshot-illustrated module docs (vs `odoo-demo-recording` REAL VIDEO/GIF; vs `odoo-content-draft` TEXT-only; vs `odoo-ui-review` RATES a screen; vs `odoo-visual-regression` DIFFS builds). DOC LAYER discriminator: "hướng dẫn sử dụng / user guide / RST / doc/index.rst" -> `DOC LAYER:userguide TONE:technical DOC SCOPE:full-guide`; "landing / App Store / marketing / static/description/index.html" (no guide) -> `DOC LAYER:appstore TONE:marketing`; omit DOC LAYER -> default `appstore` (writes index.html). Scope: single module = `MODE:module TARGET:<abs-path>`; cluster/multiple modules = `MODE:cluster TARGET:local|worktree:<abs-path>|repo:<abs-path>` (dispatches odoo-doc-scoper first). For BOTH files in one run -> row 54. For full App Store bundle with icon + manifest -> row 53 `module-packaging`. |
| 45 | "rebase onto", "rebase branch onto another branch same version", "absorb my branch onto an updated base", "rebase feature onto X", "rebase intent", VI: "rebase nhánh lên nhánh khác cùng phiên bản", "đưa nhánh feature lên base mới", "gộp ý đồ khi rebase nhánh" | `odoo-git-rebase` | SAME Odoo series; whole-range `rebase --onto` absorbing intent (vs `odoo-forward-port` = CROSS major; vs parallel N-disjoint-WI delivery = `odoo-planning`, which plans it for `run-harness`'s between-wave integration; vs `odoo-coding` = one change, nothing to replay) |
| 46 | "upgrade my module(s) to v<N>", "migrate custom module from v16 to v17", "upgrade this cluster across majors", "make this module installable on the new Odoo version", VI: "nâng cấp module lên phiên bản Odoo mới", "chuyển module custom từ v16 lên v17", "đưa cluster lên series cao hơn" | `odoo-modules-upgrade` | EXECUTE a cross-major cluster upgrade (CODE-LEVEL: installable+working; DELETE core-absorbed modules) (vs `/odoo-plan-upgrade` = PLAN only; vs `odoo-forward-port` = ONE commit same major; vs `odoo-deprecation-audit`/`odoo-version-diff` = detection only) |
| 47 | "acceptance test", "QA the affected cluster / blast-radius", "run it for real on the UI", "write scenarios then run them", "verify blast-radius", "works end-to-end before release", VI: "nghiệm thu cụm module", "chạy thật trên UI", "kịch bản test rồi chạy", "kiểm thử chấp nhận", "QA cụm bị ảnh hưởng" | `odoo-acceptance` | EXECUTE an independent oracle on a LIVE instance/UI across the affected cluster (CRUD + >=2 roles + state + search) and adjudicate PASS/FAIL/UNVERIFIED with evidence (vs `qa-suite` which only WRITES a static test-plan/checklist doc, nothing run; vs `odoo-ui-review` which rates ONE rendered screen; vs `odoo-code-review` which is static source review, no run). Needs a live instance + browser MCP |
| 48 | "plan the implementation / execution plan", "what order do we build the modules", "sequence this rollout / wire the lifecycle", VI: "lập kế hoạch thực hiện", "thứ tự build module", "lên kế hoạch triển khai" | `odoo-planning` | Turns an APPROVED design into the EXECUTION PLAN (wave-batched module order + integration cadence + module/stage->skill wiring + full lifecycle) BEFORE code; runs AFTER `odoo-solution-design`. Also the user front door for "parallelize / run as a wave" (row 40): it plans the wave-batched delivery; on approval `run-harness` drives each wave-layer via its INTERNAL between-wave integration (never user-invoked). Discriminator: `odoo-solution-design` = the technical DESIGN = HOW to build (data model / override strategy / approach); `odoo-planning` = the EXECUTION plan = build/integration order + lifecycle wiring. Pure design with no sequencing → solution-design; WRITE code → `odoo-coding`; classify/cost requirements → `odoo-gap-analysis` |
| 49 | "watch PR #N", "monitor PR #123", "babysit this PR", "drive the PR to merge", "poll CI until it goes green", VI: "theo dõi PR", "canh PR đến khi merge" | `odoo-pr-monitoring` | Owns the PR lifecycle AFTER a PR already exists and `run-harness`'s terminal `integrate` land-tail opened the ONE run-level PR (STOP at "PR opened"): polls CI + review state (via `/loop` in-session or `/schedule` cron, reading through git-toolkit), routes any CI warning/fail to `odoo-debug` (fix authored by `odoo-coding`, re-push HUMAN-gated), and on green + approved presents the L2-merge-gate and merges. Discriminator: opening + squashing the PR = `run-harness`'s terminal land-tail (internal, once after the final wave); writing a fix = `odoo-coding`; diagnosing = `odoo-debug`. DO NOT route here to OPEN a new PR, before any PR exists, or for a single-file change |
| 50 | "thiết kế icon module", "design module app icon", "tạo icon.png cho module", "generate icon.png", "module identity icon", "design icon for Odoo app" | `odoo-icon-design` | DESIGN/GENERATE the module's icon.png (256x256 SVG-to-PNG) via code-gen + rasterizer - brand-aware, version-gated (vs `odoo-doc-illustration` which captures a 128x128 live SCREENSHOT crop as fallback; vs in-UI glyph = a Font Awesome class name -> route to `odoo-coding`) |
| 51 | "liệt kê tính năng module cho tài liệu", "enumerate module capabilities", "feature inventory for docs", "what features does this module ship", "catalog all module features" | `odoo-doc-feature-map` | FULL enumeration of all features/capabilities a module ships FOR DOCUMENTATION (vs `odoo-feature-check` which answers ONE single yes/no feature question; vs `odoo-feature-highlights` which is marketing "what's new in version X") |
| 52 | "lập kịch bản hướng dẫn sử dụng", "walkthrough scenarios for docs", "write usage scenarios", "happy-path usage guide", "document how to use this module", "tạo kịch bản sử dụng cho tài liệu" | `odoo-doc-walkthrough` | Authors happy-path usage SCENARIO TEXT for documentation, browser-free, no execution (vs `odoo-acceptance` which DRIVES live UI + yields PASS/FAIL verdict; vs `odoo-content-draft` which is marketing copy with channel-specific formatting; vs `odoo-solution-design` which designs technical architecture) |
| 53 | "đăng module lên Apps Store", "đóng gói tài liệu module", "module packaging", "store listing", "App Store submission bundle", "chuẩn bị module lên marketplace", "đóng gói đăng Apps Store kèm icon và manifest" | `module-packaging` (workflow) | Full App Store submission bundle: icon-design + doc-illustration marketing landing + user-guide + manifest audit BEFORE submission (vs `odoo-doc-illustration` row 54 for docs-only RST+HTML no icon no manifest-audit; vs `odoo-icon-design` for icon only; vs `odoo-doc-feature-map` for feature inventory only). Discriminator: explicit icon.png needed OR manifest-audit OR "đăng store / submission" -> module-packaging; docs-only (RST + HTML, no icon, no manifest audit) -> row 54 odoo-doc-illustration DOC LAYER:both |
| 54 | "viết cả hướng dẫn và landing cho module", "guide + landing page kèm ảnh", "full doc cả 2 file", "both user-guide and store description", "cả RST lẫn index.html cho module", "doc cả 2 loại không cần đóng gói", "viết hướng dẫn sử dụng và mô tả App Store cho module" | `odoo-doc-illustration` | DOC LAYER:both TONE:marketing DOC SCOPE:full-guide - produces BOTH `static/description/index.html` AND `doc/index.rst` with shared screenshots in ONE run. DOCUMENTATION ONLY: no icon.png generated, no manifest-audit, no store submission. Discriminator: "cả 2 file tài liệu (RST + HTML), KHÔNG cần icon, KHÔNG đăng store" -> row 54 (odoo-doc-illustration DOC LAYER:both); "full store bundle kèm icon + manifest-audit + đăng marketplace" -> row 53 module-packaging |
| 55 | "why is Odoo slow", "N+1 query", "perf audit", "optimize this query", "list view takes forever", "computed field is slow", "should I add index=True", "t-foreach performance", VI: "code bị N+1 không", "audit hiệu năng", "tối ưu truy vấn", "field có nên index không" | `odoo-perf-audit` | Static PERFORMANCE audit -> findings report with file:line + impact, does NOT rewrite (vs `odoo-code-review` = holistic multi-lens review; vs `odoo-debug` = live "slow right now in production" runtime diagnosis; vs `odoo-coding` = writes the fix) |
| 56 | "audit security", "is this code safe", "SQL injection risk", "XSS in QWeb", "check access control", "sudo bypass", "hardcoded secret", "okay to ship?", VI: "kiểm tra bảo mật code", "có bị SQL injection không", "review bảo mật trước deploy", "t-raw có an toàn không" | `odoo-security-audit` | Static SECURITY vulnerability audit -> severity-graded findings + exploit path, no fixes (vs `odoo-code-review` = general bugs/convention; vs `odoo-debug` = runtime symptom; write the fix -> `odoo-coding`) |
| 57 | "write a migration script", "rename this field in the DB", "backfill data after a column change", "split/merge a model", "generate pre/post migrate", VI: "viết migration script", "đổi tên cột CSDL", "backfill dữ liệu", "tách/gộp model", "sinh file pre_migrate/post_migrate" | `odoo-data-migration` | Writes `migrations/<ver>/pre|post-migrate.py` + verification checklist (vs `odoo-version-diff` = WHAT changed between versions; vs `/odoo-plan-upgrade` = full upgrade plan; vs `odoo-modules-upgrade` = adapt module source to run on the new series) |
| 58 | "customer health check", "churn risk", "is this customer at risk", "upsell opportunities", "account review", "renewal coming up", "adoption is low", VI: "sức khỏe khách hàng", "nguy cơ rời bỏ", "cơ hội upsell cho khách" | `odoo-customer-health` | Green/Amber/Red health score + churn signals + upsell for an EXISTING customer (vs `odoo-discovery-summary` = NEW prospect profile; vs `support-triage` = one ticket; vs `odoo-deal-followup` = the follow-up email itself) |
| 59 | "translate this module", "export .pot/.po", "update the translation", "sync terminology", "audit term consistency", VI: "dịch module Odoo", "xuất .pot/.po", "cập nhật bản dịch", "đồng bộ thuật ngữ" | `odoo-i18n` | Front door for ALL Odoo translation; instance-backed, non-destructive .po MERGE (vs a one-line UI label fix -> `odoo-coding`; vs a rendered-UI language check -> `odoo-ui-review`). Needs a running instance |
| 60 | "draft a pricing proposal", "build a quote", "how much should we charge", "commercial offer", "price breakdown", VI: "báo giá", "đề xuất giá", "soạn báo giá cho khách", "bảng giá cho deal" | `odoo-pricing-proposal` | Customer-facing PRICING doc: license tier + impl cost + support tier + terms + total (vs `odoo-gap-analysis` = the effort/scope estimate that FEEDS the price; vs `odoo-deal-followup` = a follow-up email) |
| 61 | "respond to this RFP", "compliance matrix for these requirements", "rate these requirements against Odoo", "fill in this RFP response table", "score this tender spec", VI: "ma trận đáp ứng RFP", "đánh giá yêu cầu RFP", "bảng compliance hồ sơ thầu" | `odoo-rfp-response` | Formal RFP COMPLIANCE matrix (Yes/Partial/Roadmap/No/via-Extension + evidence + fit %) (vs `odoo-gap-analysis` = effort/quote matrix; vs `odoo-capability-proof` = deep code evidence for ONE requirement; vs `/odoo-respond-bid` = the full multi-step bid package). Discriminator: per-requirement compliance scoring, no cost |
| 62 | "write test cases", "write test_*.py", "cover this constraint with a test", "write a tour / HttpCase", "write a JS Hoot test", "translate tests to the new version", VI: "viết test cho model", "viết tour Odoo", "viết HttpCase", "dịch test sang version mới" | `odoo-test-writing` | Writes RUNNABLE test files (Python TransactionCase/Form/@tagged, JS Hoot/QUnit, tours) (vs `odoo-qa-suite` = a non-executing prose test-PLAN table; vs `odoo-acceptance` = run live + adjudicate PASS/FAIL; vs `odoo-code-review` = review existing code) |
| 63 | "create an Odoo instance", "spin up v17", "init these modules", "drop the test DB", "run tests on this instance", "is the instance up", "rebuild from scratch", "activate a language", VI: "dựng instance Odoo", "tạo DB Odoo mới", "xoá instance", "cài module chạy test" | `odoo-instance` | Front door for ALL live-instance lifecycle: create/drop DB, init/update modules, run tests, status (vs `odoo-coding` = write code; vs `odoo-debug` = diagnose a runtime failure; vs `odoo-acceptance` = drive a QA oracle on an instance) |

## Full-stack tasks - `odoo-coding` handles both stacks in one skill

A request spanning backend **and** frontend (e.g. "add a `priority` field **and** show it as a star widget") is a **single `odoo-coding` module** - do **not** pre-split it. `odoo-coding` (rows 12/14) scopes per-module and dispatches ONE `odoo-coder` coordinator that sequences backend-first then frontend internally, following the design-system fidelity contract when styling must match the theme. For ≥4 disjoint modules or git-orchestrated delivery, route to `odoo-planning` - it plans the wave-batched delivery and, on approval, `run-harness` drives it via its internal between-wave integration (never invoke an executor directly).

## Design-first rule - route non-trivial coding through `odoo-solution-design`

A coding request (`odoo-coding`) is NOT automatically the first step. When the change is **non-trivial** (Extension-L/Custom-XL, new module/model, a core ORM-hook override or ≥3-override-chain method, a multi-strategy migration, a cross-model/multi-company computed chain, a full-stack feature, or any refactor), plan `odoo-solution-design` BEFORE the coder, with `odoo-planning` between design and code: `odoo-solution-design → odoo-planning → odoo-coding → odoo-code-review` (exactly the `odoo-implement-feature` workflow - prefer it for the full chain, driven by Phase P). `odoo-planning` turns the approved design into the wave-batched execution plan. Design is a planning step (writes only `<SHARE_DIR>/designs/`), human-approved FIRST, then Plan Mode wraps the code step. DESIGN may be skipped for a one-approach localized fix (a single field, boilerplate), but **planning is mandatory for all work** - it still flows through `odoo-planning`, which emits the minimal `[code, review, integrate]` plan. Intake OWNS this admission gate: it establishes the approved plan (routing through `odoo-planning`) before dispatching any executor, so the executor never re-checks for a plan (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule).

## Scope-first rule - establish scope/effort before designing

`odoo-solution-design` designs HOW to build a KNOWN scope; it is NOT the first step when scope or
effort is unestablished. When the user asks to DESIGN / architect a solution but no scope exists yet
(no prior gap/BRL run, an open-ended or unclassified requirement set, "design a solution for these
requirements"), route `odoo-gap-analysis` FIRST - or `odoo-brl` at hundreds-of-items / cost+DAG scale -
then design: `odoo-gap-analysis → odoo-solution-design → odoo-planning → odoo-coding → odoo-code-review`. The gap run
classifies each requirement + effort tier and emits `gap-continuation-contract.json`
(`meta.has_nontrivial`), which decides whether a design step is even needed.

**Reuse a prior gap run.** In Phase 0 / Phase R, glob `<SHARE_DIR>/gap-analysis/*/gap-matrix.jsonl`. If a
run exists, surface it in the Proposed Plan (path + date) and offer to REUSE it: skip a fresh gap run
and feed that artifact straight to `odoo-solution-design` (it reads either a gap-matrix or a BRL RTM).
Re-run gap-analysis only if the requirements changed since.

## Collision zones - when the Routing Table tie is close

The Routing Table's **Discriminator** column resolves most ties inline. **When the candidate is one of the pairs below and the inline discriminator is not decisive, read `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/collision-zones.md`** for the canonical resolution logic.

| # | Collision pair | Quick discriminator |
|---|---|---|
| 1 | `odoo-objection-handling` vs `odoo-capability-proof` | "write a response" (paste-able paragraph) → objection; "technical evidence / proof package" → capability-proof |
| 2 | `odoo-version-diff` vs `odoo-feature-highlights` | "slide / newsletter / summarize for business" → highlights; "which APIs changed, dev needs" → version-diff |
| 3 | `odoo-deprecation-audit` vs `odoo-version-diff` | "audit OUR code / what will break" → deprecation-audit; "clean diff between versions" → version-diff |
| 4 | `odoo-deal-followup` vs `odoo-objection-handling` | "hasn't replied / re-engage" → deal-followup; "counter a stated objection" → objection |
| 5 | skill vs `/command` (same domain) | no slash + single-step → SKILL; explicit slash or "save to file" → COMMAND |
| 6 | `odoo-capability-proof` vs `odoo-demo-recording` | written/paste-able proof → capability-proof; real recorded video/GIF → demo-recording |
| 7 | `odoo-coding` vs `odoo-debug` | symptom + "why / not showing" → debug (cause first); "write / create from scratch" → coding |
| 8 | `odoo-feature-check` vs `odoo-gap-analysis` vs `odoo-brl` | 1 feature → feature-check; short list → gap-analysis; hundreds OR cost/DAG/RTM → brl |
| 9 | parallel multi-module vs `odoo-brl` vs `odoo-coding` | parallelize+PR+squash → `odoo-planning` (plans it; `run-harness` drives it via its between-wave integration); classify/cost reqs → brl; single change → coding |
| 10 | `odoo-doc-illustration` vs `odoo-demo-recording` | static doc/screenshots → doc-illustration; recorded video/GIF → demo-recording |
| 11 | `odoo-git-rebase` vs `odoo-forward-port` vs parallel multi-module | same series + one branch's whole range = git-rebase; cross-major single commit = forward-port; N disjoint modules squashed = `odoo-planning` (plans it; `run-harness` drives it via its between-wave integration) |
| 12 | `odoo-modules-upgrade` vs `odoo-forward-port` / `/odoo-plan-upgrade` / `odoo-deprecation-audit` / `odoo-version-diff` | execute + working code/PR for a cluster across majors = modules-upgrade; plan only = plan-upgrade; one commit same major = forward-port; detection only = deprecation-audit/version-diff |
| 13 | `odoo-acceptance` vs `qa-suite` vs `odoo-ui-review` vs `odoo-code-review` | execute + adjudicate an oracle on a live instance/UI across the cluster = acceptance; static test-plan/checklist/triage doc, nothing run = qa-suite; rate ONE rendered screen = ui-review; static source/PR review, no run = code-review |
| 14 | `odoo-feature-check` vs `odoo-doc-feature-map` vs `odoo-feature-highlights` | single yes/no feature question -> feature-check; enumerate ALL capabilities for docs -> doc-feature-map; marketing "what's new in version X" -> feature-highlights |
| 15 | `odoo-customization-inventory` vs `odoo-doc-feature-map` | CUSTOM code summary for a client engagement -> customization-inventory; STANDARD module capabilities from source for documentation -> doc-feature-map |
| 16 | `odoo-doc-walkthrough` vs `odoo-acceptance` vs `odoo-content-draft` vs `odoo-solution-design` | docs narrative no-execute -> doc-walkthrough; live drive + PASS/FAIL verdict -> acceptance; marketing copy with channels -> content-draft; technical architecture pre-code -> solution-design |
| 17 | `odoo-icon-design` vs `odoo-doc-illustration` (screenshot crop) vs in-UI glyph | DESIGN/GENERATE icon.png (256x256 SVG code-gen + rasterize) -> icon-design; crop live screenshot as fallback -> doc-illustration; Font Awesome class name in a view -> odoo-coding |
| 18 | `odoo-doc-illustration` DOC LAYER:userguide vs :appstore vs :both vs `module-packaging` | user guide RST only -> DOC LAYER:userguide; App Store HTML only -> DOC LAYER:appstore; both RST+HTML no icon/submission -> DOC LAYER:both (row 54); full bundle icon+manifest+submission -> module-packaging (row 53) |

## Command-vs-skill discriminator

Slash commands (`/odoo-*`) are user-explicit kickoffs that chain multiple skills with approval gates. Skills (`odoo-*`) auto-fire on natural-language intent match.

**Routing rule**: if the user's input begins with `/`, the harness invokes the command directly - intake does NOT see this turn. If input is natural language, intake fires on description match.

When ambiguous between command and skill:
- **Multi-step** intent → recommend the COMMAND.
- **Single-step** intent → recommend the underlying SKILL.
- **Save output to file** explicitly → recommend the COMMAND (commands write under the resolved `$ODOO_AI_HOME` SHARE/ISOLATE dir - tier per the command's actual subpath, see `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`).

## Out of Scope

- **NEVER execute work yourself.** No code generation, no proposal drafting, no file writes. MCP / agent calls limited to read-only context: Phase 0 context reads and Phase R read-only Recon. No writes-files specialist runs before Plan Mode is approved.
- **NEVER recommend more than one skill per module.** If 2 skills are close for the same module, use the Discriminator column to pick the winner; if truly undecidable, escalate to the user with both names + the 1-line difference. A full-stack change is a single `odoo-coding` module - that skill dispatches ONE `odoo-coder` coordinator which sequences backend and frontend internally (see § Full-stack tasks). Genuinely disjoint changes are separate modules planned by `odoo-planning`; its approved plan is what `run-harness` drives via its internal between-wave integration.
- **NEVER trigger on already-routed work.** If the user is mid-workflow, let the active skill continue - do not re-route.
- **Decline politely for non-Odoo/ERP intents.** Say "This doesn't seem to be an Odoo/ERP task - could you clarify?" and stop.

## Standalone-first fallback

Intake is routing + brainstorm + read-only Recon - no file writes, and no MCP calls beyond Phase 0 context reads and Phase R read-only OSM probes. OSM is optional:
- **backed path**: `<SHARE_DIR>/context.md` has `odoo_version` AND `mcp__odoo-semantic__*` tools are reachable → intake records `OSM: backed` in the Proposed Plan.
- **standalone path**: `<SHARE_DIR>/context.md` is absent, lacks `odoo_version`, or OSM tools are not reachable → intake operates on user-provided context alone; records `OSM: standalone` and notes that `odoo-onboarding` can bootstrap the context file.

## Output Format

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/output-format-templates.md` for the full collision / non-Odoo response templates.

**Fast-path gate** (Tier 1 or Tier 3 hit with clear verb): emit the one-line gate from § Pro fast-path.

**Brainstorm Proposed Plan** (Tier 4 vague branch): use the canonical `## Proposed Plan` block from § Soft plan gate (SSOT - do not restate the fields here).

## Notes for future maintainers

Design rationale, 5-phase flow, inventory-discovery rules, routing-table layout, and trigger-eval plan: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/maintainers.md`. Keep the routing table and `references/collision-zones.md` in sync when adding entries.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive output for the run-harness - it does not change anything produced above.
