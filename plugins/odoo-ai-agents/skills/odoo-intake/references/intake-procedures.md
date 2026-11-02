# odoo-intake - procedures moved out of SKILL.md

Contents: Anti-rationalize red flags | Documentation routing | Brainstorm, approach question, hand-off, deep survey | Phase R - Recon | Dispatch mechanism | Language and voice | Command-vs-skill

## Anti-rationalize gate

> **No execution skill writes code before its plan owner's Plan-Mode approval.**

**Red Flags - phrases that trigger STOP:**
- "This is simple, I'll just start coding" → STOP. Hand it to `odoo-planning`; its minimal plan is the gate.
- "The user clearly wants X, skip the questions" → only valid via the fast-path, when intent, scope and approach are already settled.
- "I'll plan, then build the deliverable in the same turn" → NO. Writing a planning artifact is fine; producing the routed deliverable is the plan owner's run.
- "I'll have the user approve my summary, then the plan owner presents its plan" → NO. One approval per request: ask only what is unsettled, then hand off with one line.
- "The user approved the approach, so the plan is approved" → NO. The approach is a text answer; the plan owner's Plan-Mode approval is the gate.

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


## Brainstorm, approach question, hand-off, deep survey

Only runs in the **vague branch** (Tier-4 miss or explicit "I'm not sure").

1. **Explore context (STATIC only)** - reuse the facts 3a resolved, list existing artifacts under the `$ODOO_AI_HOME` state root (SHARE/ISOLATE dirs per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), infer domain and persona. STATIC = filesystem reads only (no agent launch, no OSM calls).
2. **Clarifying options** - present 2-3 **pre-structured options** (not open-ended questions), e.g. "Is this (a) sales/proposal, (b) engineering upgrade, (c) strategy?". **Multi-turn boundary:** if intent/purpose/outcomes are already clear, continue in the same turn; if not, emit options and **END THE TURN** - next turn resumes via Tier-2. Do not run Phase R until the intent gate is closed (Hard rule 3d).
3. **Propose 2-3 approaches** - each with: one-line outcome + key trade-off + recommendation, informed by Phase R findings - as the approach question (§ Approach question and hand-off). END THE TURN.
4. **Write brainstorm notes** - intake MAY write `<ISOLATE_DIR>/brainstorm/<slug>-<date>.md`.
5. **Hand off** - on the chosen approach, emit the hand-off line, invoke the plan owner, and update `<ISOLATE_DIR>/brainstorm/state.json`.

## Approach question and hand-off

The approach question text and template are in `SKILL.md`; omit the deep-survey line for small asks.

**Hand-off** - once intent, scope and approach are settled, emit ONE line naming the plan owner and what it presents next, then invoke it in the same turn. Its brief carries: project root; Odoo version/edition; intent / purpose / expected outcomes; persona; Domain lines (`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`: `Domain: <business_function>; Audience: <roles | n/a>; Outcome: <result>` per unit, `UNKNOWN` when the category is not in the taxonomy; never assign a business function from a technical word); the chosen approach and preliminary scope; the recon findings path; the deep-survey `synthesis.md` path or `none`; the documentation target and its facts (§ Documentation routing); `OSM: backed | standalone`. A chat-only or read-only skill gets the same one line and fires at once.

### Deep survey (opt-in)

On `refine: deep-survey`:
1. Invoke **`odoo-deep-survey` via the Skill tool** (a `spawner-agent` skill - the Skill tool loads it in the main context so it fans out workers as subagents). Pass it the closed intent/purpose/outcomes, the resolved Odoo version + profile, the feature slug, and the recommended approach.
2. It writes only analysis artifacts under `<SHARE_DIR>/survey/`; the user's opt-in reply is the consent.
3. When it returns a `synthesis.md` path, re-ask the approach question sharpened by the synthesis and **drop the deep-survey offer line** (survey runs at most once).
4. Downstream skills read `synthesis.md` (carried in the hand-off brief and, for a RUN-DAG, in the `run-<id>.json` node inputs).


## Phase R - Recon (read-only current-state + inventory discovery)

**When**: AFTER Phase 0 closes the intent gate, BEFORE the approach question and the hand-off, on every path; in the brainstorm flow it sits between step 2 and step 3.

**What it does** - survey, never mutate:
- Launch **≤1-2 READ-ONLY recon subagents** (`Explore`, or an anonymous recon agent) at **haiku by default** (sonnet when it must judge), never opus/fable by default (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection, Recon/scouting phase default), to map code/modules relevant to the stated intent. A read-only leaf skill (e.g. `odoo-feature-check`) is instead invoked via the Skill tool. These agents do not write files and do not spawn (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`); they return findings in chat.
- Call read-only OSM tools as needed: `model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`.
- For a request that produces or follows documentation, the recon brief also records in `findings.md`, per module in scope, `module_docs: yes|no` (`doc/` or `static/description/` present), and the declared docs-site rows (the output of `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/docs_site_config.py show`).
- When recon reads a document that IS the requirement SSOT (RFP / contract / spec / requirement list), extract it faithfully per `${CLAUDE_PLUGIN_ROOT}/snippets/ssot-extraction-contract.md` - verbatim/structured, never an interpretive summary that invents specifics.
- **Persist before you hand off:** the rule is in `SKILL.md` § Phase R; `findings.md` holds the capped record rows. Persistence and inventory-fact sources: `references/phase-0.md` § Phase R - persistence and inventory discovery.


## Dispatch mechanism - Skill tool, not a direct agent launch

For a `spawner-agent` skill the Skill tool loads it in the main context, so the skill itself fans out its own subagents. A command is dispatched by the user's slash kickoff or its command.

Before proposing a workflow, read its `inputs:` block: every input that changes the outcome and has no default the YAML states (`video-produce`: `destination`, `languages`, `targets`) is a closed question in the approach step, or a default you CHECKED against the facts it depends on and cite (the odoo-media `youtube_check` for a destination, the embed targets' languages for `languages`) - never a default you assumed.

## Language - mirror the user in every chat output

The user prompts in THEIR language; every chat-facing output of this skill - brainstorm framings, option menus, plan proposals, RUN-DAG summaries, gates, clarifying questions - is written in that language, mirroring their prompts. The templates in this file are instructions to you, not text to paste: keep their STRUCTURE (lines, tables, reply keywords `approve` / `refine:` / `skip` / `cancel` verbatim) but translate every label and sentence. Keep code, identifiers, module/model names, file paths, skill names, and URLs verbatim; explain unavoidable technical terms in plain words in the user's language on first use. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`.

Mirroring applies to CHAT ONLY. The ARTIFACTS the routed skills ship - reports, proposals, design docs, marketing copy, code, docstrings - follow the artifact-voice contract instead: present-tense current-state writing, no process narration, no dates-as-provenance, no tracker references. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/artifact-voice.md`.


## Command-vs-skill discriminator

Save output to a file explicitly -> the COMMAND; commands write under the resolved `$ODOO_AI_HOME` SHARE/ISOLATE dir, tier per the command's actual subpath (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`).
