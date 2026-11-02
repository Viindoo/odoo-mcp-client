<!-- Reference for `odoo-forward-port` § The pipeline. -->

# Forward-Port Pipeline - dispatch briefs, checkpoint/resume and caveats

**Contents:** Dispatch-brief skeleton - P1 one extractor per module (R2b retry, Tier-C) - P6 TEST-survival - P8 coder registry - P9.5 i18n reconcile - P11 acceptance - Checkpoint, resume - Frontend/i18n/data-XML caveats

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete
`odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).


---

## Orchestrator text moved from SKILL.md

Phase wording that is not in the phase files `references/fp-phase-p0-p4.md`, `fp-phase-p5-p8.md` and `fp-phase-p9-p12.md`.

### Dispatch-brief skeleton

**Dispatch-brief skeleton.** For every specialist agent dispatched below (`odoo-intent-extractor`,
`odoo-installable-prober`), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the
target agent's family delta; never inline that file verbatim into a hard-leaf brief. Resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once and pass the captured literals
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Cross-worktree dispatch).

### P1 - one extractor per module (R2b), retry and Tier-C

**BAN (R2b): at most ONE `odoo-intent-extractor` instance per module across the ENTIRE run.**
Dispatch by walking the P0 `module -> [ordered sha list]` map, ONE agent launch per module, never
one launch per commit. Each extractor brief MUST include `commit_dump_paths: { <sha>: <path>, ... }`
(the module's full ordered map from the P0 pre-step, oldest first; `commit_dump_path` only for the
narrow re-check/audit uses documented on the agent itself; the extractor never runs git). A second
instance for a module ALREADY dispatched this run, while the first is live or has completed
successfully, is a pipeline defect; retry a failed or incomplete module pass by resuming the SAME
instance by the id its launch returned.
**Tier-C retry (no recorded id, or it no longer resolves -
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A):** confirm the failed
instance's turn has fully ended, then launch exactly ONE replacement `general-purpose` worker
carrying the module's FULL, UNCHANGED `commit_dump_paths` plus `PRIOR ATTEMPT: <what the failed
pass returned or omitted>`. The replacement is authoritative for the whole module bundle.
Dispatch each module's single instance using CHP Tier-B `subagent_type: "fork"`
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B), with the module's triaged
`model` override (`references/fp-triage-table.md` Table 1, resolved per module bundle), up to the Mode B budget
(rolling window beyond it; the budget counts MODULES in flight, not commits). Extraction is
read-only, so no worktree children. Fallback (Tier C): if `subagent_type: "fork"` is unavailable,
dispatch a fresh `general-purpose` spawn with an explicit brief; the worklog is always written.

Commit dumps, the per-module `SLUG` and the brief: `references/fp-phase-p0-p4.md` § P1.

### P6 TEST-survival sub-check

**P6 TEST-survival sub-check [MUST - after the production symbol check].**
Detect test code referencing a field/model symbol removed at target. **Dispatched to `Explore`
(read-only, `model: haiku` passed on the launch)** per `[[fp-symbol-survival-check]]` § Who runs
this check. Every call named below is CONTENT OF THAT DELEGATE'S BRIEF, never a call you issue in
this context. Brief it to: for each model/field touched, call
`tests_covering(model='<model>', odoo_version='<target_version>')`
(optional `field='<field>'` narrows); for a whole-module commit, supplement with
`test_coverage_audit(module='<module>', odoo_version='<target_version>')` (field-level only; for
per-method coverage use `tests_covering(model='<model>', method='<method>', odoo_version='<version>')`,
which is sparse); and, because `tests_covering` does not compare cross-version, before concluding a
test is broken CONFIRM the symbol is absent at target via
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')`. Test methods
referencing a symbol absent at target MUST be triaged into the same bucket (not forwarded
verbatim). Record every broken test-symbol reference in the `merge-log.md` per-commit row; the
P8 adapt brief MUST carry this list as `BROKEN TEST-SYMBOLS`.

### P8 - the coder registry and the resumed coder (R2b)

**Per-module agent-id registry (this run's plan.md).** Record in `plan.md`, keyed by module, the id
each of your launches returns - one id per module for the WHOLE run, never one per commit
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` Tier A).

**R2b at the 8b leg: one coder per module, resumed.** P8's only launch per module is the
`odoo-coder` that `odoo-coding` starts (the node's test leg runs inside it). On the module's
FIRST P8 invocation this run, invoke `odoo-coding` without `WORKER_AGENT_ID` and record the coder's agent id
that launch returns; on every LATER one (a P9 re-adapt, a later batch) carry it as `WORKER_AGENT_ID: <id>`
in the FP-ENRICHED brief and `odoo-coding` resumes it. Send the P9 failure output (or the next batch's brief) and collect the result per CHP § Async
park-and-be-resumed semantics - R0 of `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`
decides whether you end your turn or wait inside it; never carry on with the next module before the result
is in hand. On resume the coder MUST `cd` to the integration worktree before any Bash command (CHP
snippet "Tier-A workers in a linked worktree - cd on resume").
Fallback (Tier C): when no id is recorded for the module, the recorded id no longer resolves, or no
messaging tool is present, re-invoke `odoo-coding` cold with the full FP-ENRICHED brief - the same
**Worktree path: `<path>/fp-integration`** field and, for a re-adapt, the P9 failure output.

### P9.5 - i18n reconcile

**P9.5 - i18n reconcile [MANDATORY, per batch, own export build].** For every module in this
batch whose 8e record says `i18n_due: yes`, invoke the `odoo-i18n` skill (via the Skill tool) ONCE.
Pass the five caller obligations from
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`: `WORKTREE_PATH` (this batch's integration
worktree), `SELF_PROVISION: worktree-addons` so `odoo-i18n` builds its OWN export instance whose
addons path covers that worktree
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion: on a
miss, BLOCK), and `TARGET LANGUAGES` (the codes inferred from the source-side `<lang>.po` filenames -
deliverable languages only, never `en_US` - when any exist; otherwise OMIT the field). An
`i18n_due: escape:<E-id>` module is skipped with its recorded reason. Present every result -
reconciled or escaped - at P12 with the PR.

**Do NOT hand over the P9 verify instance** to `odoo-i18n`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` KT4); let it provision.

P9 and P9.6: `references/fp-phase-p9-p12.md` § P9, § P9.6.

### Checkpoint, resume and the per-batch caveats

## Checkpoint / resume

`<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json` maps
`{<sha>: extracted | designed | adapted | verified | done}`, with `designed` carrying the
`design_doc` path for any commit P3 routed to `odoo-solution-design`. P0 reads it and skips
`status=done` commits (and resumes a `status=designed` commit at the P4 plan gate with its
recorded `design_doc`, so a crash between design-approval and re-entry resumes correctly). After a
crash mid-batch, re-read the checkpoint + the on-disk `<module>/intents/` per-module
subdirectories, `plan.md`, and `merge-log.md` (file existence is the source of truth).

**Resuming a crash INSIDE the absorption window.** A crash during P6-P9 leaves the merge
in progress and partial adapt on disk; that state IS the resume point: check for it
FIRST (`repo_facts` on `<path>/fp-integration`: `operation_in_progress` = `merge`), and when
it is, RESUME the existing window at the phase `checkpoint.json` last recorded - never re-run
P5 on top of it and never abort it in order to restart the range commit-by-commit. Abort and re-open the WHOLE range only when the window is already gone or
the working tree is unrecoverable, and record that decision in `merge-log.md`. Record the executor's
`INSTANCE_HANDLE` (and its instance log path) in the batch worklog so a resumed run reuses the same
instance or releases it instead of orphaning the DB. A resume in the SAME session reuses the recorded
handle as-is. A resume that spans a session boundary reuses it only through
`lease_find` (state `parked`, this run's `run_id`) -> `lease_adopt` the token that call returns ->
`instance_serve`; `found=false` means the recorded instance is gone - provision a fresh one via
`odoo-instance`, and never release or park the recorded token you did not adopt. You are the run-level owner of the P9 lease
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1); release it per `SKILL.md` § The pipeline, P9.

## Frontend / i18n / data-XML caveats

- **Frontend (JS/OWL/SCSS).** Route a frontend adapt commit to `odoo-coding` - never hand-translate
  OWL from memory.
- **i18n (.pot / .po).** Do NOT hand-port or re-export translation files in this pipeline. The i18n
  reconcile is MANDATORY, narrow-escape only, per `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`:
  8e COMPUTES the trigger + already-upgraded conditions per module, P9.5 DISPATCHES `odoo-i18n` once
  the P9 instance exists - it owns the non-destructive `.pot`/`.po` recipe and validates the result.
  Full wiring: `references/fp-phase-p5-p8.md` § 8e, `SKILL.md` § The pipeline, P9.5.
- **Data XML (`noupdate` records).** A source data record may reference an external-id that does
  not resolve at the target. After merge, verify every external-id in touched data XML resolves
  on the target (P6 covers `ref()` / `xml_id`); a `noupdate="1"` record will not be
  re-written.

Per-batch checks:

- **Multi-repo env bootstrap.** When source and target live in different repos/clones, bring
  the source ref into reach (invoke `git-toolkit:git-ops`: add source remote + fetch) BEFORE computing
  the merge base or merging. Detail: `references/fp-phase-p0-p4.md` § P0.
- **Manifest version & migration dir.** C1 sets the manifest version at the merge, C2 decides each
  forwarded `migrations/` dir at P9.6; they are distinct, apply both. SSOT: `[[fp-merge-absorption]]`.
- **Field-label grounding.** When the port renames or re-labels a field, confirm the
  target's canonical label before adapting -
  `entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<target>')` - so the
  forwarded string matches the target's own term. Detail: `references/fp-phase-p9-p12.md` § P12 (entity_lookup example).

### P11 - End-to-end acceptance

**P11 - End-to-end acceptance (odoo-acceptance) stage [MANDATORY, cluster-wide, narrow escape
only, BEFORE the P12 PR opens or reviews].** Runs after the P10 loop closes and BEFORE P12 pushes the
branch, opens the PR, or runs its review gate (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md`
§ Default tail). Compute the verify scope by invoking `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`
over every module touched across the batch (from `merge-log.md`), deriving the reverse-closure via
OSM `impact_analysis` per that snippet's Step 1.
Invoke the `odoo-acceptance` skill (via the Skill tool) ONCE for the whole batch (never per commit
or per module). Fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton
(read it by path): `INPUTS` = the touched module set from `merge-log.md`, `scope_hint` =
`merge-log.md` + each touched module's own `<module>/intents/<sha>.md` (§ P1 write path), `odoo_version`
= target series; `INSTANCE_HANDLE: none provisioned` - NEVER P9's verify handle. `ACCEPTANCE` (by
pointer) = each ported commit's behavioral contract recorded in the touched module's own
`<module>/intents/<sha>.md` and any P3 design doc's §9 - NEVER a pre-built oracle. Do NOT hand it
the implementation.
**MANDATORY - narrow escape only.** Skip it ONLY when the touched set is a true dependency leaf with
ZERO in-repo dependents AND no behavioral surface (no views, no models any other module consumes) -
record that proof explicitly in `merge-log.md`; never skip silently. **The forward-port is not DONE
until this stage returns ACCEPTED (PASS), or the narrow-escape condition above is explicitly met and
recorded.**
Carry the acceptance verdict (or the recorded narrow-escape) forward and present it ALONGSIDE the
P12 human-merge decision below.
Output: `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` (`odoo-acceptance`'s own artifact), referenced
from `merge-log.md`.
