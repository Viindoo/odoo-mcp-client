# odoo-intake - Phase 0 detail (3a-3c)

Read from Hard rule 3 of `SKILL.md`.

### Phase 0 - 3a resume, 3b working directory, 3c OSM probe

   **3a. Read existing context / resume.**
   - **Resolve the project facts** - series, OSM profile, addons scope, and (live steps only) an instance target - per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`: work its rungs in order, stop at the first that answers, thread the resolved literals into the hand-off and every dispatch brief. Resolve `<SHARE_DIR>` (and `<ISOLATE_DIR>` where noted below) via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` before the first Read/Write/Edit of any state-root path in this skill.
   - Check `<ISOLATE_DIR>/brainstorm/state.json` - if an in-progress brainstorm session exists, resume it (Tier 2).
   - **Check for an active run** - glob `<ISOLATE_DIR>/run-*.json` for any with `status: NEEDS_NEXT`. If one exists, do NOT silently open a second RUN-DAG. Surface it and ask: resume it (continue per `plan-mode-schema.md` § Running the plan), or start fresh? Only proceed to open a new run once the user chooses.
   - **Check for existing recon** - glob `<ISOLATE_DIR>/recon/*/findings.md` for this intent's slug.
     A match whose `target_ref:` header line (schema: `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md`
     clause 2) equals the current ref (`ref` of a `repo_facts` call: the branch, or the short SHA when
     `HEAD` is detached) -> READ it and SKIP Phase R's dispatch entirely (resume rule: clause 1 of
     the same contract). A mismatch -> STALE - fall through to Phase R, which re-dispatches and
     overwrites the file per clause 1.

   **3b. Detect the working directory (3 branches).** Locate Odoo manifests with:
   ```bash
   find . -maxdepth 3 \( -name "__manifest__.py" -o -name "__openerp__.py" \) 2>/dev/null | head -20
   ```
   - **(i) Odoo addon dir (≥1 manifest)** → the facts 3a resolved stand as-is; **skip** re-asking anything a rung answered. Ask ONLY for what remained unresolved after every rung, batched into ONE message (rung 5). Never ask for the module list - rung 3 globs it. Edition (CE|EE|custom) is stored nowhere: when an answer genuinely depends on it, settle it per question via OSM (`list_available_profiles` / `check_module_exists`) against the resolved series.
   - **(ii) Project root (manifests under nested dirs / mono-repo)** → infer common parent as project root; confirm version/edition once, then continue.
   - **(iii) Non-Odoo dir (0 manifests)** → discriminate by intent:
     - **(iii-a) general Odoo Q&A**, no local code needed → **proceed standalone**; record `Project: non-Odoo workspace (general Odoo Q&A)` + `OSM: standalone`.
     - **(iii-b) touches local code/instance** but 0 manifests found → addon is likely outside maxdepth-3: **ask for the addon path / instance URL and re-probe**; if still 0, proceed standalone with a caveat.
     - **(iii-c) purely non-Odoo** (HR/finance/legal/PR/general writing) → § Multi-plugin routing.

   **3c. OSM probe + version confirmation.** Call `mcp__odoo-semantic__list_available_versions`, then branch:
   - **OSM reachable AND 3a resolved the series** → confirm the series is in the indexed list and mark `backed`. Do NOT re-ask the version.
   - **OSM reachable BUT the series is still unresolved after every rung** → present the indexed version menu from `list_available_versions` → `list_available_profiles` filtered to the chosen version → `profile_inspect(method='summary', …)` to confirm the profile name resolves. Record both as the values in force for this turn. Mark `backed`. When no `[[instance]]` in the catalog covers this repo, add ONE line offering `/odoo-ai-agents:odoo-setup` to declare one - an offer, never a precondition; the run proceeds on the resolved values either way.
   - **OSM absent/unreachable** → mark `standalone`. The series still comes from 3a's rungs; ask for it only when every rung missed. When no `[[instance]]` in the catalog covers this repo, add ONE line offering `/odoo-ai-agents:odoo-setup`.
   Record `OSM: backed | standalone` for the hand-off.

### Phase R - persistence and inventory discovery

- **Persist before you hand off (MANDATORY).** After the recon subagents return, YOU write their returns VERBATIM (never a paraphrase or digest) to `<ISOLATE_DIR>/recon/<slug>-<date>/findings.md`: a `target_ref:` header line (the current `ref` of a `repo_facts` call: the branch, or short SHA when detached) followed by the capped four-field record rows. When two subagents ran, the second's return goes to its own `findings-2.md`, never merged into `findings.md`, and `findings.md` names it in a closing `siblings:` line. Schema: `${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clauses 2 and 3; resolve the state-root tier per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`. Pass the path in the hand-off brief. Cannot resolve `<ISOLATE_DIR>` (resolver REFUSAL) -> proceed and pass `Findings (Recon): <bullets> (not persisted - state root unresolvable)`; never block intake on it.

**Inventory discovery (hybrid).** Pull each fact from its SSOT:

| Need | Source | How to fetch |
|---|---|---|
| skill / agent / command exists + its description | runtime context (harness-injected) | already available - do NOT read files for this |
| `model_tier` (Haiku/Sonnet/Opus/inherit) | the `model:` frontmatter of the candidate's `SKILL.md` / `agents/*.md` (SSOT) | read the frontmatter of the CHOSEN candidate only; **if absent, treat as `inherit`** |
| `output_mode` (`chat-only` ⇄ `writes-files`) | `orchestration.<skill>.output_mode` in `skill_tool_deps.json` | read that field directly |
| `effort` (S / M / L / XL / `unrated`) | `odoo-gap-analysis` owns the tier | COPY the tier from an existing gap-matrix / BRL RTM row for this item; with no such row write `unrated` and leave the tier to the gap run or the dispatched skill - never reason one out here |

**Hard limits**: read-only, leaf - must not spawn further (see `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`), no file writes. If OSM is unreachable, proceed on user-provided context (standalone).
