---
name: intake
description: |
  Universal front door for ALL work across 9 personas (CEO/strategist, consultant,
  sales AE, pre-sales, marketer, developer, QA, customer-success) — brainstorms WHEN intent
  is vague or open-ended, fast-paths WHEN intent is already clear, and always proposes a plan
  + gate before execution.

  Trigger AGGRESSIVELY on any of: open-ended "what can Odoo / you help me with", "I have an
  idea but not sure where to start", a short Odoo/ERP prompt with no concrete verb, any
  business outcome stated without a named skill ("I need to win this deal", "make our v17
  upgrade safe"), "not sure which skill", implicit
  ambiguity (short Odoo prompt, no intent keyword, or one mapping to >=2 skills). Also fires
  on Vietnamese: "Odoo giúp được gì cho tôi", "chưa biết nên dùng skill nào".

  DO NOT trigger when: the user types an explicit /slash command; intent matches exactly ONE
  specialist clearly AND is single-step (let that skill fire directly); user is already
  mid-workflow inside another skill (already routed this session)
model: inherit
---

# Intake — Universal Front Door (Brainstorm + Route + Soft-Plan-Gate)

## Persona

Domain-agnostic front door for all 9 README persona buckets: CEO/strategist, consultant,
sales AE, pre-sales, marketer, developer, QA, customer-success, and anyone in between.

The user is often NOT a developer and may not know any skill names — they just describe
what they want or what outcome they need. This skill's job is to:

1. **Detect** whether the intent is clear (fast-path) or vague (brainstorm).
2. **Route** via 4-tier logic to the single best specialist skill or workflow.
3. **Gate** every execution with a Proposed Plan before any work runs.
4. **Never do the routed work itself** — it MAY produce plan/design artifacts during its
   turn, but the routed *execution* (production code, proposals) happens after approval.

## Hard rules

1. **Intake MAY write planning/design artifacts (brainstorm notes, design docs, `state.json`)
   during the plan turn — Write/Edit are available.** What it MUST NOT do before the Proposed
   Plan is approved is produce the *routed deliverable itself* (production code, generated
   proposals) or dispatch a writes-files specialist. The gate is behavioral (this rule + Plan
   Mode), not a blanket file-write block — producing a design doc on the plan turn is encouraged.
2. **No routed-deliverable production, and no writes-files specialist dispatch, before Plan
   Mode is approved — but read-only Recon and planning-artifact writes ARE allowed.** Four
   sub-rules, none optional:
   - (1) **Intake MAY write planning/design artifacts (design docs, brainstorm notes,
     `state.json`) on the plan turn**, but MUST NOT write the routed deliverable's files
     (production code, generated proposals) before Plan-Mode approval. The constraint is
     behavioral, not a `disallowed-tools` block.
   - (2) **NEVER invoke a writes-files execute-skill (a `writes-files` specialist) — nor the
     Skill tool running such a specialist — BEFORE Plan Mode is approved.** That includes
     `odoo-coding`, `wave`, `odoo-brl`, `workflow-chaining`, or any skill
     whose output mode is `writes-files`. Yield to it via a NL-dispatch description; the actual
     dispatch happens on a LATER turn, AFTER Plan-Mode approval (see § Plan Mode).
   - (3) **Phase R (Recon) MAY dispatch a READ-ONLY agent via the Agent tool** — `Explore`, or
     a specialist in read-only mode (e.g. `odoo-feature-check`, `odoo-override-finding`) — to
     survey current state. That agent **MUST NOT write any file and MUST NOT spawn a further
     sub-agent** (nesting guard — see § Phase R and `${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md`).
     Read-only OSM calls (`model_inspect`, `check_module_exists`, `find_override_point`,
     `impact_analysis`) are likewise allowed in Phase R.
   - (4) **Dispatch of a writes-files specialist happens ONLY after Plan Mode is approved**, and
     it is the **main agent — not intake during the plan turn —** that calls the Agent tool.
   This skill is depth-0 — intake lives in the main context only.
3. **Phase 0 — Context, Detect & Clarify (mandatory).** Runs at the start of every
   invocation. It does three things — read context, detect what kind of place we are in, and
   close the **intent gate** — before anything else proceeds.

   **3a. Read existing context / resume.**
   - Read `.odoo-ai/context.md` if it exists (version, edition, module list, instance URL).
   - Check `.odoo-ai/brainstorm/state.json` — if an in-progress brainstorm session exists,
     resume it (Tier 2).
   - **Check for an active run** — glob `.odoo-ai/run-*.json` for any with `status:
     NEEDS_NEXT`. If one exists, do NOT silently open a second RUN-DAG (that orphans the first
     and the Stop nudge goes silent when >1 run is active). Instead, surface it and ask: resume
     it (hand to `run-driver`), or start fresh (and what to do with the old run)? Only proceed to
     open a new run once the user chooses. This implements the resume contract `run-driver`
     § Resume assumes.

   **3b. Detect the working directory (4 branches).** Locate Odoo manifests with the same
   probe `odoo-onboarding` uses (its SKILL.md Step 1, ~lines 38–43):
   ```bash
   find . -maxdepth 3 -name "__manifest__.py" 2>/dev/null | head -20
   ```
   Branch on the result:
   - **(i) Odoo addon dir (≥1 manifest, no usable context file)** → dig deeper: ask for
     Odoo **version / edition (CE|EE|custom) / target module(s) / instance URL**. Note that
     `odoo-onboarding` can bootstrap a full `.odoo-ai/context.md` (its schema — environment,
     modules, conventions, session pins — is documented in `odoo-onboarding` SKILL.md
     ~lines 125–162; do **not** copy it here, point to it).
   - **(ii) Project root (manifests under nested dirs / mono-repo)** → infer the common parent
     as project root; confirm version/edition once, then continue.
   - **(iii) Non-Odoo dir (0 manifests)** → discriminate by intent (0 manifests alone never
     blocks an Odoo question):
     - **(iii-a) general Odoo Q&A**, no local code needed (e.g. "Odoo 17 vs 16 for devs",
       "does Odoo have feature X", capability/marketing about Odoo) → **proceed standalone**;
       record `Project: non-Odoo workspace (general Odoo Q&A)` + `OSM: standalone`.
     - **(iii-b) touches local code/instance** ("edit my module", "write a field", "debug this
       UI") but 0 manifests found → the addon is likely outside maxdepth-3: **ask for the addon
       path / instance URL and re-probe** there; if still 0, proceed standalone with a caveat
       ("no manifest found — working from the context you provide").
     - **(iii-c) purely non-Odoo** (HR/finance/legal/PR/general writing) → § Multi-plugin routing
       (do not invent an Odoo skill).
   - **(iv) `.odoo-ai/context.md` already present and usable** → use it as-is; **skip** re-asking
     version/edition/module.

   **3c. OSM probe.** Call `mcp__odoo-semantic__list_available_versions`. If it returns AND
   `.odoo-ai/context.md` carries an `odoo_version` → mark the path `backed` (specialist calls
   `set_active_version` automatically). If OSM tools are absent/unreachable → mark `standalone`
   (no OSM enforcement; specialist relies on user-provided context). Record `OSM: backed |
   standalone` in the Proposed Plan.

   **3d. GATE — Intent / Purpose / Expected outcomes (MANDATORY).** Before Phase R may run,
   all three MUST be clear: **what** the user wants, **why**, and **what done looks like**.
   If any is missing, resolve it with **pre-structured options** (ETHOS #2 / #9 — e.g. "Is the
   goal (a) ship a code change, (b) scope a proposal, (c) produce marketing copy?"), never an
   open-ended "what do you want?". **If intent / purpose / expected outcomes are not all clear,
   you MUST NOT proceed to Phase R (Recon).**
4. **Confidentiality (public repo — 8 banned groups).** Do not surface, quote, or
   transmit: CEO personal info, customer PII/contracts, internal pricing, competitor
   intelligence beyond public sources, product roadmap details, marketing-in-draft,
   OKR/targets, vault paths. If a user prompt contains such data, acknowledge intent
   only — do not echo it.
5. **Depth-0 only.** This skill MUST NOT be called from inside another skill or subagent.
   If you detect you are running at depth > 0, decline and inform the caller.

## Iron Law — anti-rationalize gate

> **No execution skill fires until the user has approved a Proposed Plan.**

The gate has two enforcement layers — both are required; neither is optional:

1. **Text gate (Proposed Plan block)** — brainstorm / route / soft-plan-gate. Always
   present; user types `approve / refine / cancel`.
2. **Plan Mode (harness-level guarantee)** — applies on top of the text gate whenever the
   approved next step is an execute-skill that **touches files** (see "Plan Mode" section
   below). Plan Mode is the stronger, machine-level enforcement; the text gate alone is
   insufficient when file writes are about to occur.

**Red Flags — phrases that trigger STOP + re-gate:**
- "This is simple, I'll just start coding" → STOP. Still propose + gate.
- "The user clearly wants X, skip the questions" → only valid via Tier-1 fast-path, NOT
  a rationalization to skip the gate.
- "I'll plan, then build the deliverable in the same turn" → STILL GATED. Writing a design/plan
  artifact is fine; producing the routed deliverable (production code, proposal) or dispatching a
  writes-files specialist before approval is not. (Memory: `started-editing-during-plan-request`.)
- "The gate is unnecessary friction here" → wrong. The gate IS the contract.
- "The text gate was enough, I can skip Plan Mode" → WRONG. Plan Mode is mandatory when
  an execute-skill will write files. The text gate and Plan Mode are independent layers.

## Phase R — Recon (read-only current-state + inventory discovery)

**When**: AFTER Phase 0 closes the intent gate (intent / purpose / expected outcomes all
clear), and BEFORE the Proposed Plan is written. Recon turns a generic plan into a
context-aware one — it confirms what already exists rather than guessing.

**What it does** — survey, never mutate:
- Dispatch **≤1–2 READ-ONLY agents** via the Agent tool — `Explore`, or a specialist in
  read-only mode (e.g. `odoo-feature-check`, `odoo-override-finding`) — to map the code /
  modules relevant to the stated intent. These agents do not write files and do not spawn.
- Call read-only OSM tools as needed: `model_inspect`, `check_module_exists`,
  `find_override_point`, `impact_analysis`.

**Inventory discovery (hybrid).** When the plan needs to know which skills/agents/commands
exist and their attributes, pull each fact from its SSOT — do NOT duplicate model/effort into
any registry:

| Need | Source | How to fetch |
|---|---|---|
| skill / agent / command exists + its description | runtime context (harness-injected) | already available — do NOT read files for this |
| `model_tier` (Haiku/Sonnet/Opus/inherit) | the `model:` frontmatter of the candidate's `SKILL.md` / `agents/*.md` (SSOT) | read the frontmatter of the CHOSEN candidate only; **if the field is absent (most `SKILL.md` omit it), treat it as `inherit`** |
| `output_mode` (`chat-only` ⇄ `writes-files`) | the explicit `orchestration.<skill>.output_mode` field in `skill_tool_deps.json` (NOT a `spawn_class`/`stack` derivation) | read that field directly |
| `effort` (S / M / L / XL) | NOT registered — it is a skill×task property | reason per the `odoo-gap-analysis` legend: **S = <1d · M = 1–3d · L = 3–10d · XL = >10d** |

**SSOT note**: `model_tier` lives in frontmatter and `effort` is per-task — NEVER copy either
into a registry. Read `model:` from the candidate's own frontmatter at plan time.

**Hard limits**: read-only, **depth-1** (one hop from main; the Recon agent is a leaf and must
not spawn further — full text `${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md`), and **no file
writes**. If OSM is unreachable, say so and proceed on user-provided context (standalone).

## Plan Mode — harness-level pre-execute gate

**Decision tree (run first)**: intake reads the chosen Approach's `output_mode` (Phase R
discovery — the explicit `orchestration.<skill>.output_mode` field in `skill_tool_deps.json`).
- `output_mode = writes-files` → **Plan Mode is REQUIRED** before dispatch (proceed through the
  full procedure + content schema below).
- `output_mode = chat-only` → **SKIP Plan Mode** (unchanged behaviour); intake ends its turn and
  the specialist fires via the Agent tool on the next turn. The chat-only set is listed under
  "Does NOT apply" below.

**When it applies**: after the user approves the Proposed Plan AND the chosen next step is
an execute-skill that will **write or modify files** — specifically any of: `odoo-coding`,
`wave`, `odoo-brl`, `workflow-chaining`, or any skill whose output
column is NOT "chat only".

**Why intake can do this**: intake runs at depth-0 (main context). `EnterPlanMode` /
`ExitPlanMode` are only callable from the main context — subagents cannot invoke them.
Intake MUST be the one to initiate Plan Mode; specialist skills running later do not have
this capability.

**Does NOT apply** for chat-only / read-only skills: `odoo-feature-check`,
`odoo-version-diff`, `odoo-risk-overview`, `odoo-deprecation-audit`, `odoo-gap-analysis`,
`odoo-discovery-summary`, `odoo-capability-proof`, `odoo-objection-handling`,
`odoo-content-draft`, `odoo-competitive-brief`, any skill whose Output field is "chat only".

**Procedure** (execute-skill that touches files):
1. User sends `approve` on the Proposed Plan.
2. Main agent calls **`EnterPlanMode`** tool.
3. Main agent writes an implementation plan (files to be changed, approach, acceptance
   criteria) inside Plan Mode.
4. Main agent calls **`ExitPlanMode`** tool → Plan Mode UI is shown to the user.
5. User reviews and approves the plan in the Plan Mode UI.
6. ONLY after Plan Mode approval: main agent invokes the execute-skill or workflow via the
   **Agent tool**.

**Red flags for Plan Mode**:
- "The user already said approve, I can skip EnterPlanMode" → NO. Text-gate approval and
  Plan Mode approval are two separate steps.
- "I'll enter Plan Mode after I've already started editing" → BANNED. EnterPlanMode must
  come before any file touch.

### Plan Mode Content Schema

The implementation plan written inside Plan Mode (step 3 above) MUST contain three blocks, none
optional for a `writes-files` Approach: **Block 1 — Workitem list** (each WI: `id`, one-line
description, disjoint `files-in-scope`); **Block 2 — Dependency graph** (DAG with typed edges +
topological order, or one of the four wave topologies for a few WIs); **Block 3 — Assignment**
(`WI → skill|command|agent` + model-from-frontmatter + effort + per-WI acceptance criteria +
verify command). A workflow-command is ONE WI (its `output_dir/`), never expanded into its
internal phases. **When writing a writes-files plan, read
`${CLAUDE_PLUGIN_ROOT}/skills/intake/references/plan-mode-schema.md`** for the full block schemas
(which shapes to borrow + line refs), worked examples, and the rejection flow.

**Rejection flow (summary):** if the user refines/rejects in the Plan Mode UI, loop back to the
soft-plan-gate (not execution); re-enter Plan Mode only after the revised plan is re-approved at
the text gate; never dispatch a writes-files specialist off a rejected plan. Full detail in the
reference above.

## Phase P — RUN-DAG persistence + drive-to-done (optional, additive)

This phase turns an approved plan into a self-advancing run. It is **purely additive**: a
single-step plan still dispatches exactly as before — Phase P only matters for multi-step work or
hands-off execution.

**Engage Phase P** (after the plan is approved) if ANY holds: (1) `node_count >= 2`; (2) a single
`output_mode == writes-files` node; or (3) a single workflow node whose YAML declares
`on_complete`. Otherwise SKIP it and dispatch directly (single chat-only, non-`on_complete` node).
When engaged, serialize the approved 3-block plan into `.odoo-ai/run-<id>.json`, tag gate-tiers,
and NL-dispatch `run-driver` (which keeps everything depth-0). Parse the autonomy dial from the
prompt (`--auto` default / `--step` / `--plan`).

**When engaging Phase P, read
`${CLAUDE_PLUGIN_ROOT}/skills/intake/references/phase-p-run-dag.md`** for the full engage/skip
rule, the `run-<id>.json` serialization procedure, the autonomy-dial semantics, depth safety, and
the workflow-as-node routing. Full schema + loop: `docs/reference/workflow-harness.md` §8.

## Multi-plugin routing — stay Odoo-centric

When Phase 0 detection finds the intent is **outside the Odoo domain** (general company work —
HR/recruiting, finance/budget, legal/compliance, internal ops, PR, broad market research with
no Odoo hook), do NOT force-fit it onto an Odoo skill. Instead:
- Route to the appropriate other surface (e.g. the vault research/capture skills for
  CEO/strategy/memory; another installed plugin), OR
- If nothing fits, say so plainly and flag it as out-of-plugin — let the main agent decide.

This plugin owns the **Odoo** domain; `/intake` is the front door that *also* recognises when a
request belongs elsewhere. Do not invent an Odoo skill to cover a non-Odoo need.

## 4-tier routing

Run tiers in order; first hit wins; cost rises per tier.

| Tier | Mechanism | Token cost | Action |
|---|---|---|---|
| **1 — regex/intent** | Explicit verb+noun pattern: "write computed field", "diff v16 v17", "review this PR", "/..." | 0 | Exact specialist → **pro fast-path** (see § Pro fast-path) |
| **2 — session state** | `.odoo-ai/brainstorm/state.json` exists and contains in-progress brainstorm | 0 | Resume that brainstorm thread |
| **3 — keyword table** | 40-row routing table (see § Routing Table) covering all 9 persona domains | 0 | Map to single skill or workflow → soft-plan-gate |
| **4 — LLM classify** | Only on Tier 1-3 miss: classify the ambiguous prompt (~500 tok) | ~500 tok | Single clear target → gate; vague/multi-domain → **enter brainstorm** |

Brainstorm fires ONLY when Tier 1-3 all miss AND Tier-4 returns either (a) no confident
single target, or (b) a large/multi-domain job ("hundreds of requirements", "win this deal
end-to-end", "plan + build + ship an upgrade").

## Pro fast-path

When Tier 1 or Tier 3 yields exactly ONE specialist AND the prompt contains a concrete
action verb + object, skip brainstorm entirely. Emit a **one-line soft plan gate**:

```
Plan: run `<skill-name>` to <one-line outcome>. Proceed? (yes / brainstorm instead / cancel)
```

A pro user types "yes" once. A novice can opt into brainstorm. This is the explicit
guarantee that brainstorm-first never blocks an expert.

## Brainstorm (6-step)

Only runs in the **vague branch** (Tier-4 miss or explicit "I'm not sure").

1. **Explore context (STATIC only)** — read `.odoo-ai/context.md`, list existing `.odoo-ai/`
   artifacts, infer domain and persona from environment. STATIC = filesystem/file reads only
   (no Agent-tool dispatch, no OSM calls); the dynamic recon that dispatches agents + calls OSM
   is Phase R (see the "Where Phase R fits" note below), not this step.
2. **Clarifying options** — present 2-3 **pre-structured options** (not open-ended
   questions), e.g. "Is this (a) sales/proposal, (b) engineering upgrade, (c) strategy?".
   Build for the audience (ETHOS #9).
   **Multi-turn boundary:** if the prompt already makes intent/purpose/outcomes clear, continue
   in the same turn; if not, emit the options and **END THE TURN** to wait for the user — the
   next turn resumes here via Tier-2 (`.odoo-ai/brainstorm/state.json`). Do not run Phase R
   until the intent gate is closed (Hard rule 3d).
3. **Propose 2-3 approaches** — each with: one-line outcome + key trade-off + a
   recommendation. Make concrete. (Informed by Phase R findings — see note below.)
4. **Present Proposed Plan** (soft-plan-gate — see § Soft plan gate). This IS the gate;
   do not write anything before approval.
5. **Write design doc** — intake MAY write this during the plan turn (no need to wait):
   `.odoo-ai/brainstorm/<slug>-<date>.md`. The approval gate covers the *routed deliverable*,
   not the planning artifact.
6. **Transition** — emit the NL-dispatch prompt for the chosen skill/workflow; update
   `.odoo-ai/brainstorm/state.json`.

**Where Phase R fits (applies to ALL paths, not just brainstorm):** Phase R (the read-only
*dynamic* recon that dispatches ≤1-2 agents — see § Phase R) is a flow-stage that runs AFTER
the intent gate closes and BEFORE the Proposed Plan, on both fast-path and brainstorm. It is
deliberately NOT a numbered brainstorm step (numbering it here would skip it on fast-path). In
the brainstorm flow it sits between step 2 (intent closed) and step 4 (Proposed Plan), so its
findings inform the step-3 approaches and fill the `Findings (Recon)` field.

## Soft plan gate

Universal gate emitted by intake at the end of every brainstorm or fast-path turn:

```
## Proposed Plan
Project:        <repo / project root, or "non-Odoo workspace">
Odoo version/edition: <e.g. 17.0 / EE | CE | custom | "n/a">
Intent / Purpose / Expected outcomes: <what / why / what done looks like — from the Phase 0 gate>
Domain:         <one of 9 persona buckets>
Approach:       <skill name | workflow name | command>
Chain:          <skill> → <skill> ...   (for multi-step; "single turn" for atomic asks)
Findings (Recon): <1-3 bullets from Phase R: what already exists / hook points / impact>
Workitems (preview): <WI-A …, WI-B … — disjoint files; "single WI" for atomic asks>
Assignment (skill/agent + model + effort): <WI → skill|agent (model from frontmatter, effort S/M/L/XL)>
Output:         .odoo-ai/<subdir>/<slug>-<date>.<ext>   (or "chat only")
Est. effort:    <S / M / L / XL / "single turn">
OSM:            backed | standalone   (backed if OSM (`mcp__odoo-semantic__*`) tools are available; standalone if not)
Plan Mode:      required | not   (required when Approach output_mode = writes-files)
Next turn:      invoke `<skill/workflow>` via the **Agent tool** (you will see the tool call)

Gate: approve / refine: [your feedback] / cancel
```

Enforcement stack:
1. Behavioral rule (Hard rule 1) → intake may write planning/design artifacts, but NOT the
   routed deliverable, before approval. (No `disallowed-tools` block — Write/Edit are available.)
2. Iron Law + Red Flags above → behavioral enforcement (text gate layer).
3. Plan Mode (EnterPlanMode / ExitPlanMode) → harness-level guarantee before any
   execute-skill that writes files (see § Plan Mode). This is the stronger layer.
4. On `approve` → if the next step writes files, main agent MUST call EnterPlanMode before
   invoking the specialist. If the next step is chat-only/read-only, intake ends its turn
   and the specialist fires via the Agent tool on the next turn.
5. On `refine: [feedback]` → loop back within brainstorm. On `cancel` → stop + brief report.

## Routing Table

Use this as Tier-3 keyword routing. Pick the **single best match** based on intent signals.
The **Discriminator** column resolves close ties.

| # | Intent signal | Target skill | Discriminator (when ambiguous vs neighbour) |
|---|---|---|---|
| 1 | "risk", "safe to upgrade", "blast radius", executive 1-page summary | `odoo-risk-overview` | Executive audience + risk score output (vs `odoo-deprecation-audit` which is code-level audit) |
| 2 | "inventory", "list all customizations", "what have we built" | `odoo-customization-inventory` | Module-list deliverable for CEO/PM (vs `odoo-risk-overview` which scores risk) |
| 3 | "where to hook", "override method", "best place to extend", "which method should I override" | `odoo-override-finding` | Hook location question for ONE method (vs `odoo-coding` which writes the override) |
| 4 | "deprecated", "what will break", "audit before upgrade", "old API", "leftover OpenERP code" | `odoo-deprecation-audit` | Code-level audit (vs `odoo-version-diff` which is pure API diff, vs `odoo-risk-overview` which is executive) |
| 5 | "what changed between", "diff v16 v17", "API changes", "new features in Odoo X" (dev framing) | `odoo-version-diff` | Version-to-version comparison (vs `odoo-feature-highlights` which is marketing framing for the same data) |
| 6 | "does Odoo have X", "is X available", "is module Y in CE" | `odoo-feature-check` | SINGLE feature lookup (vs `odoo-gap-analysis` which handles a LIST of requirements) |
| 7 | "gap analysis", "scope", "effort estimate", "proposal", "customer needs A,B,C - does Odoo have them" | `odoo-gap-analysis` | Multi-requirement -> effort matrix (vs `odoo-feature-check` for single feature) |
| 8 | "feature highlights", "slide", "blog post", "marketing", "release notes for non-developers", "newsletter" | `odoo-feature-highlights` | Marketing/business audience (vs `odoo-version-diff` which is dev-track diff) |
| 9 | "CE vs EE", "edition comparison", "what does Enterprise add" | `odoo-addon-diff` | Three-way edition comparison (vs `odoo-feature-check` which is single-feature) |
| 10 | "prove Odoo can", "evidence for demo", "RFP evidence", "before the demo", "competitor said Odoo can't" | `odoo-capability-proof` | Evidence PACKAGE (modules + code + demo steps) (vs `odoo-objection-handling` which produces a verbatim response paragraph) |
| 11 | "respond to objection", "counter 'Odoo can't'", "write a response", "rep is on the call", "customer says Odoo can't do X" | `odoo-objection-handling` | Verbatim ACA response paragraph (vs `odoo-capability-proof` which is technical evidence) |
| 12 | "write code", "create field", "implement feature", "write computed field", "add onchange", "add SQL constraint" | `odoo-coding` | The single coding front door — backend Python/XML AND frontend (see row 14). It works out per-module whether the change is backend-only / frontend-only / full-stack and dispatches the right agents (vs `odoo-override-finding` for finding a hook location, vs `odoo-code-review` which reviews existing code) |
| 13 | "review code", "check my PR", "audit this", "smell test before merge" | `odoo-code-review` | Reviewing EXISTING code (vs `odoo-coding` which writes NEW code, vs `odoo-deprecation-audit` which is module-level audit) |
| 14 | "JS", "widget", "OWL", "frontend", "any Odoo version", "odoo.define()", "useService", "patch component" | `odoo-coding` | Same unified coding skill (frontend leg) — legacy v8-14 or OWL v15+; auto-detects framework + which stacks a change needs via the Odoo version in `.odoo-ai/context.md` or the user statement |
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
| 32 | "setup môi trường / wire MCP / cấu hình instance URL cho visual / lần đầu setup visual" | `/odoo-semantic-skills:odoo-setup` (command) | One-time environment bootstrap for the visual stack — wires browser MCP + writes instance URL/visual config to `.odoo-ai/context.md` (vs `odoo-onboarding` which bootstraps project CODE context, vs `/odoo-semantic-mcp:connect` which only sets the OSM server URL/key) |
| 33 | "BRL", "business requirement list", "hàng trăm/nghìn requirement", "classify + cost", "dependency graph", "scope toàn bộ RFP", "1200 requirements", "RTM", "costed plan from requirements", "turn RFP into effort plan" | `odoo-brl` | FLAGSHIP large-scale pipeline: hundreds-to-thousands of items + cost estimate + dependency DAG (vs `odoo-gap-analysis` = short ad-hoc list, no cost/DAG; vs `odoo-feature-check` = single feature). Discriminator: item count scale + explicit cost/RTM/DAG signals |
| 34 | "QA suite", "test plan", "test cases for module", "acceptance tests", "deploy safety checklist", "qa this module before release", "generate tests and triage bugs", "full QA pipeline" | `qa-suite` (workflow) | End-to-end QA pipeline: generate test cases + deploy checklist + bug triage (vs `odoo-code-review` which reviews static source only, vs `odoo-deploy-checklist` which is the checklist phase alone) |
| 35 | "triage ticket", "support ticket", "customer reports Odoo issue", "classify this bug", "draft resolution for support case", "root cause for customer complaint", "escalate this issue", "bug report from client" | `support-triage` (workflow) | Full ticket triage: classify → root-cause → draft resolution/escalation (vs `odoo-debug` which is a dev debug session, vs `odoo-deal-followup` which is sales follow-up) |
| 36 | "multi-scene demo video", "storyboard and record", "assemble scenes into one video", "multi-take product demo", "quay nhiều scene ghép thành một video demo", "record and stitch demo clips" | `video-produce` (workflow) | Multi-scene video production: storyboard → record each scene → assemble (vs `odoo-demo-recording` which records a SINGLE scene/flow, vs `odoo-content-draft` which writes the script only) |
| 37 | "deal close cycle", "full sales closing cycle", "multi-step deal closing", "sales follow-up sequence end-to-end", "close this deal from discovery to signature" | `sales-closing-cycle` (workflow) | End-to-end deal-closing pipeline (vs `odoo-deal-followup` which is a single email draft, vs `/odoo-respond-bid` which produces an RFP response document) |
| 38 | "long debug session", "investigate phiên dài", "multi-turn UI debug", "ui-debug-session", "sustained troubleshooting session for Odoo UI" | `ui-debug-session` (workflow) | Sustained multi-turn UI debug session with state tracking (vs `odoo-debug` which is a single-turn root-cause investigation) |
| 39 | "content brief to publish", "full content production", "content from brief to done", "multi-step content workflow", "brief → draft → review → publish" | `content-production` (workflow) | End-to-end content pipeline: brief → draft → review → publish (vs `odoo-content-draft` which is single-piece draft only, vs `odoo-campaign-plan` which plans the campaign, not produces the pieces) |
| 40 | "do this as a wave", "parallelize these changes", "multi-WI PR with review and squash", "land N related changes safely without touching main", "git-wave orchestration", "split this work into parallel worktrees" | `wave` | Depth-0 git-wave orchestration: integration branch + parallel WI worktrees + cherry-pick + end-of-wave review + 1 PR + squash + human-confirm merge (vs `odoo-coding` which handles a SINGLE change with no git orchestration; vs `odoo-brl` which classifies/costs requirements but writes NO code) |
| 41 | "design the solution", "thiết kế giải pháp / phân tích thiết kế", "how should I architect / structure this", "which approach", "design the data model", "plan the refactor", "design before we code", "technical design", "architecture decision" | `odoo-solution-design` | Designs HOW to build a non-trivial change (approach / data model / override strategy / module structure) into a gate-able design doc BEFORE coding (vs `odoo-coding` which WRITES code, vs `odoo-override-finding` which answers ONE method's hook location, vs `odoo-brl`/`odoo-gap-analysis` which classify WHAT to build + cost). Discriminator: the user wants a designed/approved approach, not yet the code |
| 42 | "implement this feature end-to-end", "from requirement to working code", "design then build then review", "scope → design → code → review" | `odoo-implement-feature` (workflow) | End-to-end feature pipeline: gap/brl → solution-design → odoo-coding → code-review (vs `odoo-solution-design` which produces ONLY the design, vs `odoo-coding` which writes ONE change with no design/review phases) |
| 43 | "make this Odoo UI look good", "design the form/kanban/list", "this screen looks cluttered/off", "thiết kế giao diện Odoo đẹp đúng chuẩn", "đúng design-system Odoo", "design a clean portal page" | `odoo-frontend-design` | Knowledge-only DESIGN-QUALITY expertise for Odoo UI/UX (view-type choice, form hierarchy, semantic tokens, website/portal) - loaded by solution-design/odoo-coding and the bar ui-review rates against (vs `odoo-coding` which WRITES the JS/OWL/SCSS, vs `odoo-ui-review` which RATES a rendered screen in a browser) |

## Full-stack tasks — `odoo-coding` handles both stacks in one skill

Some requests span backend **and** frontend: e.g. "add a `priority` field to sale order **and
show it as a star widget on the form**", "thêm field rồi hiển thị bằng widget tùy biến", "new
dashboard: a computed KPI on the model **plus** an OWL component to render it". You do **not**
pre-split these — route to `odoo-coding`, the single coding front door. It scopes the change,
works out per-module whether the work is backend-only / frontend-only / full-stack, and sequences
the two stacks itself (backend first so the field/method exists, then frontend to render it). If
the styling must match the Odoo theme, the frontend leg follows the design-system fidelity
contract. For ≥4 independent work items or a git-orchestrated delivery, escalate to `wave`.

## Design-first rule — route non-trivial coding through `odoo-solution-design`

A coding request (`odoo-coding`) is NOT automatically the first step. When the change is
**non-trivial** (the set `odoo-solution-design` defines — Extension-L/Custom-XL, new
module/model, a core ORM-hook override or ≥3-override-chain method, a multi-strategy migration, a
cross-model/multi-company computed chain, a full-stack feature, or any refactor), plan
`odoo-solution-design` BEFORE the coder, so the chain is `odoo-solution-design → odoo-coding →
odoo-code-review` (exactly the `odoo-implement-feature` workflow — prefer it for the full chain,
driven by Phase P). **Order matters:** design is a planning step (writes only `.odoo-ai/designs/`)
and is **human-approved FIRST**; only then does Plan Mode wrap the code step and the coder build
to the approved doc — design → approve → Plan Mode (code) → execute → review. **Trivial** work
(a single field, boilerplate, a one-approach localized fix) skips design and routes straight to
`odoo-coding`. The `odoo-coding` Phase 0 gate is a safety net (re-checks "non-trivial and lacking
a design doc?"), not the design step.

## Collision zones — when the Routing Table tie is close

The Routing Table's **Discriminator** column resolves most ties inline. A handful of pairs
collide hard enough to warrant a worked example with prompts and counter-cases. **When the
candidate is one of the pairs below and the inline discriminator is not decisive, read
`${CLAUDE_PLUGIN_ROOT}/skills/intake/references/collision-zones.md`** for the canonical
resolution logic — do not guess.

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
| 9 | `wave` vs `odoo-brl` vs `odoo-coding` | parallelize+PR+squash → wave; classify/cost reqs → brl; single change → coding |

## Command-vs-skill discriminator

Slash commands (`/odoo-*`) are user-explicit kickoffs that chain multiple skills with
approval gates. Skills (`odoo-*`) auto-fire on natural-language intent match.

**Routing rule**: if the user's input begins with a `/` (e.g., `/odoo-respond-bid`), the
harness invokes the command directly — intake does NOT see this turn. If the user's input
is natural language describing intent, intake fires on description match.

Intake behaviour when ambiguous between command and skill:
- Intent is **multi-step** (e.g., "draft a bid response that includes discovery, gap analysis,
  and proposal") -> recommend the COMMAND.
- Intent is **single-step** (e.g., "synthesize these discovery notes") -> recommend the
  underlying SKILL.
- User wants to **save output to file** explicitly -> recommend the COMMAND (commands write
  to `.odoo-ai/<subdir>/`).

## Out of Scope

- **NEVER execute work yourself.** No code generation, no proposal drafting, no file writes.
  MCP / agent calls are limited to **read-only** context: Phase 0 context reads and Phase R
  read-only Recon (read-only OSM + read-only survey agents that do not write or spawn). No
  writes-files specialist runs before Plan Mode is approved.
- **NEVER recommend more than one skill _per work-item_.** If 2 skills are close *for the same
  work-item*, use the Discriminator column to pick the winner; if you truly cannot decide,
  escalate to the user with both names + the 1-line difference. **Note:** a full-stack change is a
  single `odoo-coding` work-item — that skill sequences the backend and frontend agents itself, so
  you do not split it into separate backend/frontend WIs (see § Full-stack tasks). Genuinely
  disjoint changes are still separate WIs handed to `wave`.
- **NEVER trigger on already-routed work.** If the user is mid-workflow (e.g., they just
  confirmed `odoo-coding` 2 turns ago and are now describing the code they want), let
  `odoo-coding` continue — do not re-route.
- **Decline politely for non-Odoo/ERP intents.** Say "This doesn't seem to be an Odoo/ERP
  task — could you clarify?" and stop.

## Standalone-first fallback

Intake is routing + brainstorm + read-only Recon — no file writes, and no MCP calls beyond
Phase 0 context reads and Phase R read-only OSM probes.
OSM is optional, not required:
- **backed path**: `.odoo-ai/context.md` has `odoo_version` AND `mcp__odoo-semantic__*` tools
  are reachable → specialist skills receive `set_active_version` automatically; intake records
  `OSM: backed` in the Proposed Plan.
- **standalone path**: `.odoo-ai/context.md` is absent, lacks `odoo_version`, or OSM tools
  are not reachable → intake operates on user-provided context alone; intake records
  `OSM: standalone` and notes that `odoo-onboarding` can bootstrap the context file. OSM is
  NOT forced on the specialist in this path.

## Output Format

**Fast-path gate** (Tier 1 or Tier 3 hit with clear verb):
```
Plan: run `<skill-name>` to <one-line outcome>.

Proceed? (yes / brainstorm instead / cancel)
```

**Brainstorm Proposed Plan** (Tier 4 vague branch — full gate block): use the canonical
`## Proposed Plan` block defined under § Soft plan gate (SSOT — do not restate the fields here;
they must not drift between the two sites).

**Collision / ambiguous — ask user**:
```
Your intent could map to 2 skills:
- `<skill-a>` — <1-line outcome>
- `<skill-b>` — <1-line outcome>

Which would you like to run? Or give me a bit more context and I'll pick.
```

**Non-Odoo/ERP intent**:
```
This doesn't seem to be an Odoo/ERP question. Could you share more context, or let me
know if I'm the wrong skill for this one.
```

Mirror the user's language (English or the language they wrote in).

## Notes for future maintainers

Design rationale, the 5-phase flow, inventory-discovery SSOT rules, the routing-table layout, and
the trigger-eval plan live in `${CLAUDE_PLUGIN_ROOT}/skills/intake/references/maintainers.md` —
read it when changing intake's structure, the routing table, or the harness wiring. Keep the
routing table and `references/collision-zones.md` in sync when adding entries.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
