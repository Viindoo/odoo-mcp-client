# upg-phase-detail - per-phase commands + dispatch briefs

SSOT for verbatim git commands, subagent dispatch briefs, and artifact formats for the
`odoo-modules-upgrade` skill. The SKILL.md body states WHAT each phase achieves; this
file specifies HOW. Cross-references reused skills' SSOTs; copies none.

---

## Symbols (resolve once, reuse everywhere)

- `<cluster>` = `cluster_slug` resolved in P0 intake (the scope slug).
- `<path>` = the upgrade-worktree base: a `.upg-worktrees/` directory SIBLING to the principal
  checkout (NEVER inside it - keeps the principal `git status` clean). All worktrees below live under it.
- `<work-base>` = the base ref the integration branch forks from: HEAD of the target-series branch
  when one exists, else the merge-base of the cluster against the target series.

## Artifact paths

Base: `.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/`
Integration worktree: `<path>/upg-integration` (JOB tier, created at P4 post-gate)
Child worktrees: `<path>/upg-<module>` per module (WORK tier, created + removed in P4)
Progress ledger: `.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
  Schema: `{"<module>": "pending|absorbed|designed|adapted|reviewed|installed|done"}`
  Written after each module completes a phase. Per-phase skip rules on resume:
  P2 skips {absorbed, designed, adapted, reviewed, installed, done};
  P4 skips {adapted, reviewed, installed, done};
  P4b skips {reviewed, installed, done};
  P5 skips {installed, done} at the wave level.

---

## P0 - Intake subagent dispatch brief

Model: sonnet. Read-only. Output file: `intake.md`.

```
TASK: Resolve the upgrade request into structured inputs.

(1) Read the current branch name (`git branch --show-current`). Infer the Odoo SERIES
    from it: a branch named `17.0`, `17.0-feat-x`, or `viindoo-17.0` -> series `17.0`.
    If the branch name is ambiguous, mark as open_question.
    Cross-check: read a sample of `__manifest__.py` files and find the MAX `version` series
    present on disk. If the branch-inferred series and the manifest-max series disagree
    (e.g. branch says `17.0` but manifests say `16.0.x.y.z`), raise as open_question
    rather than silently trusting the branch name.
    EXCEPTION - Viindoo Standard/Internal profile (manifests carry a SHORT `version` with NO
    series prefix, per ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md): there is no series
    in the manifest to compare, so SKIP the branch-vs-manifest-series cross-check entirely and
    resolve the source series from branch + profile. Do NOT raise a false "disagree" open_question.

(2) Map that series to the OSM profile:
    - set_active_version(odoo_version='<inferred_series>')
    - list_available_profiles()
    - For each profile that looks relevant (name contains the series or is the default),
      profile_inspect(name='<profile>', method='summary', odoo_version='auto') to confirm repos + module set.
    Report the matched_profile and its repos.

(3) Auto-detect CANDIDATE MODULES using a manifest-version-series scan:
    a. Find all __manifest__.py files:
       find . -name "__manifest__.py" 2>/dev/null
    b. For each manifest, extract the `version` field. A module is a CANDIDATE if its
       manifest `version` major series is LESS THAN the target series
       (e.g. version `16.0.1.2.3` when target is `17.0`).
    c. Also include any module that depends on a stale-versioned candidate (depends-on-stale
       scan: read each manifest's `depends` list and include modules whose direct dep is
       already in the candidate set).
    d. `installable: False` is a WEAK HINT only - log it alongside the candidate but do
       NOT use it as the primary detector. A module can be `installable: True` and still
       be a valid upgrade target; a `installable: False` module that is a helper/dev/demo
       module may NOT be an upgrade target.
    e. SHORT-FORM blind spot: for Viindoo Standard/Internal manifests the `version` carries NO
       series prefix (e.g. `1.0.0`), so the version-series scan in (b) yields NOTHING. When the
       matched profile is Viindoo Standard/Internal, detect candidates by PROFILE MEMBERSHIP
       (`profile_inspect` module set) intersected with branch series + repo path instead;
       candidacy_reason = `profile-membership`.
    Emit the candidate list with paths and the reason for candidacy (version-series|depends-on-stale|profile-membership|installable-hint).

(4) Determine:
    - source_version: from the matched profile's Odoo version or the manifest `version`
      field (e.g. `16.0.1.0.0` -> series `16.0`).
    - target_version: from the NL ask ("upgrade to v17" -> `17.0`; "next major" -> the
      major after source_version). If not determinable, mark as open_question.

(5) Dependency hints: for each candidate module, read its `__manifest__.py` `depends`
    field and emit {module: [dep1, dep2, ...]} pairs.

(6) If the user's MODULE SCOPE is not explicit in the NL ask, do NOT guess. Return
    candidate_modules + proposed_cluster (seeded from the dependency closure of the
    confirmed candidate modules - read each candidate's `depends` recursively to include
    all in-repo transitive deps; do NOT use naming/path proximity as the primary
    scoping heuristic) + an open_question asking the user to confirm or narrow.

OUTPUT FORMAT (write to intake.md):
```yaml
resolved_series: "17.0"
matched_profile: "viindoo_standard_17"
cluster_slug: "l10n_vn"   # scope slug; becomes <cluster> in every artifact path + worktree/branch name
source_version: "16.0"
target_version: "17.0"
series_cross_check: "branch=17.0, manifest_max=16.0 -> DISAGREE -> open_question raised"
  # for a Viindoo short-form profile: "skipped (short-form manifest, no series prefix)"
candidate_modules:
  - path: "l10n_vn_custom/"
    module: "l10n_vn_custom"
    candidacy_reason: "version-series"  # version-series | depends-on-stale | profile-membership | installable-hint
    installable: false
proposed_cluster:
  - "l10n_vn_custom"
dependency_hints:
  l10n_vn_custom: ["l10n_vn", "account"]
open_questions:
  - "Confirm: upgrade l10n_vn_custom + l10n_vn_viin_accounting to 17.0? (detected via manifest version-series scan)"
```
```

---

## P1 - Recon parallel dispatch

Four dispatches fire simultaneously (Mode B concurrency, independent): P1a DAG, P1b deprecation
audit, P1c version delta, P1d transitive symbol survey.

### P1a - DAG build (Explore, sonnet)

```
TASK: Emit the dependency graph for the confirmed cluster, including the FULL transitive
external/core dependency closure and any dependency identity changes at target.

For each module in: <confirmed_cluster>
  Read the module's __manifest__.py; extract the `depends` list.
  Emit {module: str, path: str, depends: [str]}.

FULL TRANSITIVE CLOSURE (incl. external/core deps):
  Recursively collect ALL deps, including deps of in-cluster modules' deps that are
  external (not in-cluster) or core modules. For each dep at any level:
    check_module_exists(name='<dep>', odoo_version='auto')
  Flag:
  - dep where exists=false at target as 'dep_missing_at_target: true'
  - dep where the module was RENAMED, MOVED, or SPLIT at target (e.g. a community module
    absorbed into core, or an account_* reorg): use api_version_diff + module_inspect to
    detect identity changes. Flag as 'dep_identity_changed: true' with the new identity.
  A dep that was renamed/moved is as dangerous as a missing dep - both cause install
  failures that only surface at P5 without this check.

Output: graph.md (YAML block listing each module + deps + missing flag + identity_changed flag)
```

After receiving graph.md, the orchestrator topo-sorts to produce `topo_order: []`
(leaves first). Append topo_order to graph.md.

### P1b - Deprecation audit (Skill tool: odoo-deprecation-audit)

Dispatch via Skill tool. Brief:
```
Source version: <source_version>
Target version: <target_version>
Modules: <confirmed_cluster as comma-separated list>
REPO_ROOT: <absolute path to the repository root>
MODULE_PATHS: <comma-separated absolute paths from intake.md candidate_modules[].path>
matched_profile: <matched_profile from intake.md>
Run the TARGET-version survival pass (symbols stable at <source> but deprecated/removed at
<target> - the upgrade-critical class find_deprecated_usage misses when pinned to source).
Output to: .odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/deprecation.md
```

`odoo-deprecation-audit` has its own protocol (find_deprecated_usage + api_version_diff +
lookup_core_api rounds + TARGET-version survival pass). Do NOT replicate it here; it owns its own SSOT.
The upgrade orchestrator consumes its output as a per-module fix list in P4.

### P1c - Version delta (Skill tool: odoo-version-diff)

Dispatch via Skill tool. Brief:
```
From version: <source_version>
To version: <target_version>
Focus: developer track (API breaking changes, removed symbols, migration notes).
Output to: .odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/version-delta.md
```

`odoo-version-diff` owns its own protocol. The upgrade orchestrator consumes its
Removed APIs + Changed signatures tables in P4 via the breaking-change catalog.

### P1d - Transitive Symbol Survey (Explore, sonnet, read-only)

P1a confirms a dep MODULE exists at target; it does NOT ground the SYMBOLS the cluster pulls
from that dep down to base/ORM/tools. P1d closes that gap: it grounds every external/core
symbol the cluster references AT THE TARGET, so a renamed/removed symbol surfaces in P1 instead
of crashing at P5.

```
TASK: Transitive symbol-survival survey for cluster '<cluster>' upgrading <src> -> <tgt>.
MODULE PATHS: <comma-separated absolute paths from intake.md candidate_modules[].path>

1. set_active_version(odoo_version='<target_version>').
2. Scan the cluster source for every symbol that references an EXTERNAL/core dependency
   (a dep NOT in the cluster): model `_inherit` / `env['<model>']` targets, fields read/written
   on those models, ORM chains 3+ levels deep, method calls/overrides, `env.ref` / template
   xml_ids, and manifest `depends` entries.
3. Ground EACH symbol at the target using OSM, REUSING the procedure in
   ${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md § 2 (per-symbol grounding) and
   § 2.5 (the seven autosilent symbol classes) BY PATH - do NOT copy the steps here. Use
   `model_inspect` / `entity_lookup` / `api_version_diff` / `resolve_orm_chain` / `check_module_exists`.
4. Classify each symbol: SURVIVED | RENAMED | REMOVED | TYPE_CHANGED.
   Emit ONLY the non-SURVIVED ones as `blockers[]` (RENAMED/REMOVED/TYPE_CHANGED) - these gate P3/P4.
   For a CUSTOM `_inherit`/symbol OSM cannot resolve, that is an OSM MISS (custom code is not
   indexed), NOT absence at target: confirm against module source and label `grounded: osm + local-source (hybrid)`.

FALLBACK: if OSM is unreachable, run the grep-only enumeration from § 2/§ 2.5 and label the
whole survey `grounded: local-source (not OSM-indexed)`; still emit best-effort blockers[].

OUTPUT: transitive-symbol-survey.md
FORMAT:
  cluster: <cluster>
  grounded: "osm" | "osm + local-source (hybrid)" | "local-source (not OSM-indexed)"
  blockers:
    - module: <module>          # the cluster module that references the symbol
      symbol: <symbol>
      kind: model|field|method|orm-chain|xml_id|depends
      status: RENAMED|REMOVED|TYPE_CHANGED
      target_equivalent: <new symbol or null>
      fix_hint: "<one line: how to rewrite the call site at target>"
```

The orchestrator feeds each module's `blockers[]` into P4 as that module's PREEMPTIVE FIX LIST
(prepended before the deprecation + breaking-change fixes).

### P1 gate

Assert: DAG is acyclic. On cycle: surface the cycle edges as `DONE_WITH_CONCERNS` +
list the cycle + ask the user to break it before P2 proceeds (do NOT hard-fail).
Assert: no dep_missing_at_target or dep_identity_changed (if any flagged, surface as
`DONE_WITH_CONCERNS` + list affected deps with their new identity or missing status +
ask user to confirm the resolution before P2).
Record P1d `blockers[]` for P3/P4; a non-empty blockers list is NOT a hard-fail (it is the
preemptive fix list), but list it in the P3 plan so the human sees what P4 will fix up front.

---

## P2 - Core-absorption dispatch briefs

Per module in dep order (topo_order from graph.md), parallel within the same wave
(modules at the same depth in the DAG). Concurrency: Mode B, model-weighted budget 8
per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`.

### P2 - odoo-diff-comparator brief (per module)

Model: sonnet (opus for a cluster-wide comparison or when the module has >500 LOC).

```
TASK: Core-absorption comparison for module '<module>' upgrading <src> -> <tgt>.

MODULE PATH: <path>
SOURCE VERSION: <source_version>
TARGET VERSION: <target_version>
CLASSIFICATION TABLE: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md

STEPS:
1. set_active_version(odoo_version='<target_version>')
2. Read the module source (models/, views/, security/, static/src/) via Read/Grep to
   understand its nghiệp vụ (business purpose), ý đồ (intent), expected outcomes,
   and acceptance criteria.
2a. DATA-AT-RISK CHECK: check the module's manifest for `installable: True`. If True,
   check whether the module defines stored non-computed fields (fields without
   `compute=` or `related=`, and with `store=True` or default store behavior) OR has
   `noupdate="1"` records in its data XML. If both conditions hold (installable:True +
   stored fields or noupdate records), set `data_at_risk: true` in the output.
   If `data_at_risk: true` and the forthcoming verdict is REWRITE(model) or DELETE,
   report BLOCKED and escalate to the orchestrator for human decision - do NOT proceed
   to classify as code-only.
3. For each FEATURE the module provides:
   a. Use check_module_exists / module_inspect / model_inspect to determine whether
      the target-version core ALREADY provides this feature.
   b. Use api_version_diff to check if the relevant API changed.
   c. Classify the feature per the classification table:
      - DELETE-absorbed: target core fully provides this (cite the core module/feature)
      - OBSOLETE: the module's purpose is moot at target but NO named core feature absorbs it
      - KEEP: custom logic that core does not provide and API is stable
      - REWRITE(api): API changed at target; custom logic still needed; adapt call sites
      - REWRITE(model): model structure changed (field renamed/type-changed/removed)
      - RECONCILE: custom intent survives BUT target-core now writes/computes the SAME business
        quantity on the SAME records (data-divergence), OR a new core mechanism can replace/
        simplify the custom impl -> route to P2b design (never a silent KEEP)
      - MERGE: this module + another cluster module are now best combined
      - SPLIT: this module has grown to warrant splitting
3b. NEW-FEATURE SWEEP (RECONCILE detection) - run for EVERY feature classified KEEP or
   REWRITE(api)/REWRITE(model).
   (a) API-endpoint sweep: if the api_version_diff result from step 3.b above contains a `new`
   section, inspect those new items for mechanisms that replace or simplify the feature - REUSE
   that same result; do NOT call api_version_diff again for the same feature.
   (b) UNCONDITIONAL domain sweep: run `suggest_pattern` / `find_examples` for EVERY KEEP
   feature regardless of the api_version_diff result. This catches new parallel core mechanisms
   (new model on the same domain, new mixin, new action) that do NOT appear in an
   endpoint-scoped api_version_diff but can replace the custom logic. A new parallel core
   mechanism on the same domain forces RECONCILE even when the feature's own API is stable.
   For each surviving custom feature, judge whether a NEW target-core mechanism/API can replace
   or materially simplify it AND still cover the feature's acceptance criteria. Evidence: the
   api_version_diff `new` items + `suggest_pattern` / `find_examples` / `describe_module`.
   - New core mechanism can wire-in and covers the criteria -> reclassify RECONCILE (b);
     record it in `reuse_candidates[]`.
   - New core ALSO writes/computes the SAME business quantity on the SAME records the custom
     code writes -> reclassify RECONCILE (a) data-divergence (two SSOTs).
   A RECONCILE feature sets the module verdict to RECONCILE (or MIXED if other features stay
   KEEP/REWRITE); the orchestrator routes that verdict to P2b design (§ P2b) - never a silent KEEP.
4. If EVERY feature is DELETE-absorbed, return verdict=DELETE-absorbed with
   the SINGLE core module/feature that replaces the whole module.
4a. BEHAVIORAL-EQUIVALENCE CHECK (MANDATORY for DELETE-absorbed verdict):
   Enumerate every override the module defines: `create`/`write`/`unlink`/`_compute_*`/
   `_constrains`/`@api.onchange`/action methods/SQL constraints. Use
   `model_inspect(model='<model>', method='methods', odoo_version='auto')` + grep of models/ source. For EACH override:
   - confirm that target core produces the SAME observable effect, OR
   - confirm the override is a no-op against core behavior at target.
   If ANY override has no core equivalent with the same effect, change the verdict from
   DELETE-absorbed to REWRITE or MERGE - the module is NOT fully absorbed.
   Record the full enumeration in `behavioral_equivalence` in the output.
5. For each classification, provide:
   - evidence: OSM citation (module_inspect / model_inspect / api_version_diff result)
   - proposed_action: DELETE-absorbed / OBSOLETE / KEEP / REWRITE(api) / REWRITE(model) / MERGE / SPLIT

OUTPUT: write to absorption/<module>.md
FORMAT:
  module: <module>
  grounded: "osm" | "osm + local-source (hybrid)" | "local-source (not OSM-indexed)"
    # hybrid = OSM resolved core symbols but a CUSTOM _inherit/symbol was confirmed from module
    # source (OSM does not index custom code; an OSM MISS on a custom symbol is NOT absence).
  verdict: DELETE-absorbed | OBSOLETE | KEEP | REWRITE(api) | REWRITE(model) | RECONCILE | MERGE | SPLIT | MIXED
  features:
    - name: <feature_description>
      classification: <class>
      evidence: <OSM citation>
      proposed_action: <action>
  reuse_candidates:
    # NEW-FEATURE SWEEP output (RECONCILE-b). Omit when empty.
    - feature: <feature_description>
      new_core_mechanism: "<core module/API that can replace or simplify it>"
      covers_acceptance_criteria: true | false
      evidence: "<api_version_diff new item + suggest_pattern/find_examples citation>"
  whole_module_absorbed: true | false
  absorbing_core_feature: "<core_module>/<feature>" (only when whole_module_absorbed=true; omit for OBSOLETE)
  data_at_risk: true | false
    # true if: module is currently installable:True AND (defines stored non-computed fields
    # OR has noupdate="1" records). Flag before applying any REWRITE(model) or DELETE verdict.
  behavioral_equivalence:
    # MANDATORY for DELETE-absorbed verdict. Omit for other verdicts.
    overrides_enumerated:
      - method: <method_name>
        core_equivalent: <yes|no>
        proof: "<citation or explanation>"
    conclusion: "all overrides proved equivalent" | "FAIL: <method> has no core equivalent -> NOT DELETE-absorbed"
```

### P2 - odoo-gap-analysis dispatch (per module, parallel with comparator)

Dispatch via Skill tool. Brief:
```
Requirements: <list the module's features as requirements>
Target Odoo version: <target_version>
Context: This is for core-absorption analysis of module '<module>'.
         Determine for each requirement whether target-version core already provides it.
         Standard = core provides it natively -> DELETE candidate.
         Extension/Custom = still needs to be built -> KEEP/REWRITE candidate.
```

`odoo-gap-analysis` owns its own protocol. Its `Standard` verdict means "a customer could
get this requirement from core" - it is a SCOPING signal, NOT a delete-safety oracle.
Use its output as weak triangulation input only. The DELETE decision MUST rest on the
comparator's behavioral-equivalence proof (signal #5), not on a "Standard" gap-analysis tag.

---

## P2b - Hard-call design (conditional route-out)

Fires per the full design-trigger table in SKILL.md § P2b (SSOT; do not replicate the
condition list here).

Reuse the non-trivial criterion from `${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/SKILL.md`
§ "When to invoke - and the non-trivial threshold" - do NOT invent a third definition.

Continuation Contract payload (emit verbatim, one route-out per module):

```yaml
status: paused-design
next: odoo-solution-design
inputs:
  return_to: odoo-modules-upgrade
  design_slug_hint: <src>-<tgt>-<cluster>-upg-<module>
  target_version: <target_version>
  modules: [<module>]
  intent_records: [.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/absorption/<module>.md]
  classification: "<verdict> - <one-line reason from absorption/<module>.md>"
```

`odoo-solution-design` under `return_to` runs its own design + design-approval gate, then emits
`next: odoo-modules-upgrade` with `design_doc`; it does NOT enter a code Plan Mode and does NOT
dispatch a coder (P3 Plan Mode + P4 coder are owned by THIS skill).

On re-entry (run-driver returns with `design_doc`): read the `design_doc` path from the returned
contract `inputs`; record it against the module; set `checkpoint.json` `<module>: designed`;
proceed to P3 with the design linked - do NOT re-run design. If `design_doc` is ABSENT from the
returned inputs (design crashed before producing it), set the module back to `<module>: absorbed`
and re-enter P2b next run rather than advancing to P3 with no design.

Multiple modules may trigger P2b in one cluster. Route them one at a time (the run-driver advances
one design hop per yield); a module whose status is already `designed` is skipped on the next P2b
pass. P3 Plan Mode is entered only after EVERY P2b-triggered module in the cluster has a recorded
`design_doc`.

---

## P3 - Plan Mode content template

Write this inside Plan Mode (between `EnterPlanMode` and `ExitPlanMode`).

```markdown
## Upgrade Plan: <src> -> <tgt> for cluster <cluster>

### Per-module decision table
| Module | Action | Absorbing core / Reason (if DELETE/OBSOLETE) | Behavioral-equiv proof (if DELETE) | ADAPT tier | Design doc |
|--------|--------|----------------------------------------------|-------------------------------------|------------|------------|
| <m1>   | DELETE-absorbed | account/reconcile_model | All 2 overrides (create, write) proven equivalent in core - see absorption/m1.md | n/a | n/a |
| <m4>   | OBSOLETE | Workflow evaporated: <reason> | n/a (no absorption) | n/a | n/a |
| <m2>   | REWRITE(api) | n/a | n/a | sonnet | n/a |
| <m3>   | KEEP | n/a | n/a | haiku | n/a |

**DELETE confirmations required (one per row - separate from plan approval):**
- [ ] Confirm DELETE m1 (absorbed by account/reconcile_model - behavioral equivalence verified) [y/N]
- [ ] Confirm DELETE m4 (OBSOLETE - <reason>) [y/N]

### Adapt order (dependency-first, leaves first)
1. <m3> (no custom deps in cluster)
2. <m2> (depends on m3)
3. DELETE <m1> (depends on m2; will be removed after m2 adapted)

### Manifest version (Rule A - NOT bumped)
# Do NOT bump the manifest `version` for any module in this cluster.
# Code-level upgrade keeps the existing short form unchanged.
- <m2>: 1.0.0 (unchanged)
- <m3>: 2.0.0 (unchanged)

### Commit plan
- `upg: m3 16.0->17.0 - KEEP update API call sites`
- `upg: m2 16.0->17.0 - REWRITE(api) <summary>`
- `upg: delete m1 - absorbed by core account/reconcile_model in 17.0 (no custom delta remains)`
- `upg: delete m4 - obsolete at 17.0 (<reason>)`

### Risks
- <any dep_missing_at_target or dep_identity_changed flags from P1>
- <any data_at_risk: true modules from P2 - these BLOCK until human decision>
- <any ambiguous classification from P2>
```

After `ExitPlanMode` and user approval: write `plan.md` as the RECORD SSOT for P4+.

---

## P4 - Adapt dispatch briefs

### Integration worktree creation

Delegate to git-operator (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
- op: worktree add
- branch: `upg/<src>-<tgt>-<cluster>`
- worktree: `<path>/upg-integration`
- base: `<work-base>`

### Child worktree per module (WORK tier)

For each module, delegate all mutations to git-operator (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):

1. Create child worktree - dispatch git-operator: op worktree add, branch
   `upg/<src>-<tgt>-<cluster>-<module>`, worktree `<path>/upg-<module>`,
   base `upg/<src>-<tgt>-<cluster>`.

2. Dispatch coder to `<path>/upg-<module>`.

3. Converge back - dispatch git-operator (single brief): merge branch
   `upg/<src>-<tgt>-<cluster>-<module>` into `upg/<src>-<tgt>-<cluster>` no-ff in
   worktree `<path>/upg-integration`; then remove worktree `<path>/upg-<module>`;
   then delete branch `upg/<src>-<tgt>-<cluster>-<module>`.

### odoo-coding dispatch brief (via Skill tool, per module)

```
ODOO VERSION: <target_version>
MODULE: <module>
MODULE PATH: <path>
ACTION: <DELETE-absorbed | OBSOLETE | KEEP | REWRITE(api) | REWRITE(model) | MERGE | SPLIT>
WORKTREE: <path>/upg-<module>

INPUTS:
- Absorption verdict: absorption/<module>.md
- Preemptive fix list (this module's blockers[] - apply FIRST): transitive-symbol-survey.md
- Deprecation fix list (rows for this module only): deprecation.md
- Breaking-change catalog: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md
- Version delta (Removed + Changed for relevant symbols): version-delta.md
- Design doc (if P2b produced one): <path or "none">

ADAPT TIER: <haiku | sonnet | opus | fable> (from upg-triage-table.md)

INSTRUCTIONS:
If ACTION=DELETE-absorbed or ACTION=OBSOLETE:
  DANGLING-REFERENCE SWEEP (MANDATORY before directory removal):
  Grep the entire repo for references to the module's models, XML IDs, security groups,
  and env.ref targets that will become dangling after deletion:
    grep -rn "<module_model_names>" . --include="*.py" --include="*.xml" --include="*.csv"
    grep -rn "env.ref('<module>\." . --include="*.py"
    grep -rn "group_<module>" . --include="*.xml" --include="*.py" --include="*.csv"
    grep -rn "<xmlid from the module>" . --include="*.xml"
  The orchestrator pre-populates the module's model names (from absorption/<module>.md) and
  known XML IDs in the brief, sourced from `module_inspect(name='<module>', method='models',
  odoo_version='<source_version>')` + the module's data/security XML at SOURCE (the module is
  about to be deleted, so it is no longer at target - read it at source). For EACH dangling
  reference found: either rehome it to the absorbing core module/feature OR remove it.
  Document the rehoming decisions in the commit message or a `# upg: rehomed` comment.

  After the sweep, report findings to the orchestrator. The orchestrator then dispatches
  git-operator (in this child worktree) to remove the module directory, stage the
  deletion, and commit -s (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
  Git-operator brief fields:
    - op: rm -r module dir + stage deletion + commit -s
    - confirmed: yes - user confirmed DELETE <module> at P3 Plan Mode gate
    - commit_message (absorbed): `upg: delete <module> - absorbed by core <absorbing_core_feature> in <target_version> (no custom delta remains)`
    - commit_message (obsolete): `upg: delete <module> - obsolete at <target_version> (<one-line reason why the need evaporated>)`
  dependers: <list of modules pre-populated by the orchestrator from graph.md that list
  '<module>' in their depends - the orchestrator resolves this BEFORE dispatching the
  brief so the coder does not need to re-discover them>
  For each module in dependers[], remove '<module>' from that module's
  __manifest__.py `depends` list.

If ACTION=KEEP/REWRITE(api)/REWRITE(model)/MERGE/SPLIT:
  0. PREEMPTIVE FIX LIST (apply FIRST): for every blocker attributed to this module in
     transitive-symbol-survey.md (status RENAMED/REMOVED/TYPE_CHANGED), rewrite the call site
     to its `target_equivalent` per `fix_hint`. These are external/core symbols that auto-survive
     a clean port yet break at install/runtime - fix them before the catalog passes below.
  1. Apply all deprecation fix-list items for this module (from deprecation.md).
  2. Apply all breaking-change items that affect this module (from upg-classification-table.md).
  3. For REWRITE(model): update field references, compute methods, search/domain expressions,
     and XML views that reference changed/removed fields. ALSO sweep:
     - `data/*.xml` - update record field values, domain attrs, and field refs
     - `demo/*.xml` - same as data/
     - `security/*.csv` (ir.model.access.csv) - update model names if model was renamed
     - `ir.rule` records - update domain expressions referencing renamed/removed fields
     These files break installation just as hard as Python or view files when a field
     or model they reference no longer exists at target.
  4. Do NOT bump the manifest `version` - keep the existing short form unchanged.
  4b. Set `installable: True` (flip from False) AFTER all other P4 fixes are applied, BEFORE P5
     runs - per the upg-classification-table.md manifest-break row. P5 confirms it installs.
  4c. Scan each `__manifest__.py` for `# TODO: Uncomment when upgrading` markers left by the
     forward-port skill. Restore `auto_install`/`application` ONLY when the breadcrumb explicitly
     directs it - do NOT auto-detect from module name or depends structure.
  5. Write or adapt tests: test the adapted behavior, not the old source text. RED first.
  Always commit with `git commit -s` (DCO sign-off required by CONTRIBUTING.md).
  Commit message: "upg: <module> <source_version>-><target_version> - <ACTION> <one-line summary>"

AUTONOMOUS FIX: if the P5 install+test run returns a failure for this module, you will
be re-dispatched with the root cause from the debugger. Fix to that root cause only.
```

---

## P4b - Code-review loop (in-pipeline; per module, dep order; fix-until-clean before install)

Goal: review each adapted module's diff BEFORE the P5 ephemeral-instance install/test waves,
fixing in a loop until no CRITICAL/HIGH remains. Two review points exist: this in-pipeline loop
and the final P7 dep-order PR review - do NOT remove P7.

For each adapted module in topo_order (leaves first); skip DELETE-absorbed/OBSOLETE (no adapt diff):

```
SKILL: odoo-code-review
TARGET: worktree:<path>/upg-integration
SCOPE: module '<module>' adapt diff only (the upg: <module> ... commit); attribute findings to
       adapted lines only.
SERIES: <target_version>
CONTEXT: cross-major upgrade <src>-><tgt>; verdict <KEEP|REWRITE(api)|REWRITE(model)|MERGE|SPLIT>;
         design doc (if P2b produced one): <path or none>.
ASK: severity-graded findings (CRITICAL/HIGH/MED/LOW) + corrected version.
```

Loop + escalate (per module):
1. No CRITICAL/HIGH -> write `<module>: reviewed`, move to the next module.
2. CRITICAL/HIGH present -> dispatch `odoo-coding` (AUTONOMOUS FIX sentinel + the findings) at the
   module's ADAPT tier to fix to root cause; re-review that module. Record MED/LOW in the module's
   row for the P7 review, do not block.
3. Cap = 3 review->fix iterations per module. 3rd still CRITICAL/HIGH -> STOP, escalate BLOCKED
   per ETHOS #7 (which module, which finding, what was tried).
Proceed to P5 ONLY when EVERY adapted module is `reviewed` clean. The gate is automated; human
STOP-gates stay at P6/P7.

---

## P5 - Install + test gate format

Install bottom-up wave-by-wave (one wave = one DAG depth level, leaves first) so
failures localize to the wave that introduced them and resume skips proven waves.
Per-wave green is recorded in `checkpoint.json` (status `installed` per module) and
`install-test.md`.

**Framework-validation gate is MERGED into P5 (no separate phase) and runs demo=on.** A module
that flips `installable: False -> True` is scanned by the target's FULL test suite for the first
time; from v18 `base.TestInvisibleField` (every always-invisible view field needs an explanatory
XML comment) and `hr.TestSelfAccessProfile` (custom `hr.employee` fields need
`groups='hr.group_hr_user'`) run in that suite and require demo data. Demo default is
version-keyed - F0 ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md:
v8-v18 demo ON by default (`--without-demo` disables); v19 demo OFF by default (`--with-demo`
enables); `--without-demo=False` is INVALID. The gate stays demo=on regardless
(on v19 the instance must be created `--with-demo`). The P4b review for any flipped module MUST
additionally cover ACL / `.sudo()` for every create/write/compute override on a widely-used core
model. Cross-ref ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md.

Step 1 - create instance (once), demo=on:
```
operation: create
series: <target_version>
demo: on   # framework-validation gate REQUIRES demo data (see note above); on v19 -> --with-demo
```

For each wave in topo_order (leaves first), run Steps 2-3 before moving to the next wave:

Step 2 - init (install) this wave's modules:
```
operation: init
series: <target_version>
modules: <FULL transitive closure of THIS WAVE's modules - including external/core deps from
          graph.md P1a's full closure - plus all previously installed modules, comma-separated;
          re-specifying deps ensures Odoo's dep-order logic holds and no external dep is skipped>
CONFIRM: "confirm each module in this wave emits a Loading line; report per-module install status"
```

Step 3 - run tests for this wave:
```
operation: run-tests
series: <target_version>
modules: <THIS WAVE's modules only, comma-separated>
flags: --test-enable
test_tags: (none - run all module tests for this wave)
CONFIRM: "report per-module test result for this wave"
```

After each wave: write wave result to `install-test.md` and update `checkpoint.json`
(set `installed` for each module in the wave that passed). On FAILURE in a wave:
dispatch `odoo-backend-debugger` or `odoo-ui-debugger` with the traceback + module source.
Receive proven root cause -> feed back to P4 for the affected module only (dispatch
`odoo-coding` with `AUTONOMOUS FIX` sentinel + root cause). Re-run P5 FROM THE FAILING
WAVE (skip waves already recorded as `installed` in `checkpoint.json`).

Final `install-test.md` schema:

```yaml
# install-test.md
cluster: <cluster>
target_version: <target_version>
waves:
  - wave: <wave_number>
    modules: [<m1>, <m2>]
    install_ok: true | false
    test_result: passed | failed | error
    root_cause: null | "<proven root cause from debugger>"
per_module:
  - module: <m>
    wave: <wave_number>
    install_ok: true | false
    test_result: passed | failed | error
    root_cause: null | "<proven root cause from debugger>"
overall: green | red
```

---

## P5.7 - i18n reconcile (gated-on by default; auto-SKIP)

Wires the EXISTING `odoo-i18n` skill as a post-install phase - no new i18n logic. Non-destructive
is load-bearing: re-exporting a `.po` from a fresh DB destroys 40-90% of existing `msgstr`, so
translation MEMORY is always forwarded by MERGE, never regenerated.

SKIP gate (evaluate first): SKIP this phase when the cluster changed NO translatable surface -
no add/remove/rename of a translatable field, view label/string, selection value, help text, or
report label across the adapted modules (diff the P4 commits for translatable tokens). Record
`i18n: skipped (no translatable-surface change)` and proceed to P6.

When it runs (against the P5 instance, demo=on):
```
SKILL: odoo-i18n
INSTANCE: the P5 ephemeral instance (already up)
MODULES: <cluster adapted modules>
TARGET_VERSION: <target_version>
MODE: reconcile (non-destructive)
STEPS (odoo-i18n owns the detail; do NOT replicate its protocol):
  1. export .pot for each adapted module
  2. polib-MERGE the new .pot into each existing <lang>.po (preserve every existing msgstr)
  3. hand-translate ONLY the residual untranslated entries
  4. reload with `-u <module>` on the P5 instance and confirm the catalog loads
```
Output: `i18n-reconcile.md` (per-module: residual count, translated count, skipped?).

---

## Commit consolidation (P6/P7 capability)

"No cluster-squash" means: NEVER collapse the whole cluster into ONE opaque commit - the
per-module commit messages ARE the upgrade record. It does NOT forbid consolidating a single
module's WIP/fixup commits into ONE clean commit per module. Per-module consolidation is ALLOWED
and preferred when a module accumulated fixups during P4/P4b.

Delegate the entire consolidation sequence to git-operator for each module in dependency order
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
- op: consolidate module commits in integration worktree
- worktree: `<path>/upg-integration`
- scope: `<module>/` subtree only (do NOT stage other modules)
- base: the first commit SHA recorded by the orchestrator for this module (see note below)
  NOTE: The orchestrator MUST record each module's first commit SHA returned by the
  git-operator converge step and pass it as `base` in this brief. Do not re-discover
  the base from the log - when modules' commits interleave, log-based discovery is
  ambiguous. Fallback when no recorded SHA: `<work-base>`.
- commit_message: `upg: <module> <src>-><tgt> - <ACTION> <summary>` (signed)
- confirmed: yes - Plan Mode approved at P3 (consolidation listed in commit plan; backup ref created by git-operator)
- Steps git-operator performs: safety backup ref at HEAD -> reset-mixed to base ->
  stage `<module>/` only -> commit -s -> tree-identity verify (`git diff --quiet`
  backup vs HEAD; must be TREE-IDENTICAL) -> delete backup ref.
- tree-identity verify is git-operator S6; on S6 failure git-operator returns BLOCKED
  (gate_hit: S6 tree-identity mismatch). Recovery: dispatch git-operator to restore
  from the backup ref (hard-reset to backup-ref) and escalate BLOCKED per ETHOS #7
  listing the differing trees.

Autosquash alternative: delegate to git-operator with autosquash enabled;
git-operator handles the non-TTY environment natively.
Keep exactly ONE commit per module; never one commit per cluster.

---

## P7 - PR creation command

**Pre-PR checklist (extends P6 sign-off).** Run the Runbot parity gates
(${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md) PLUS
these three passes before opening the PR, each cross-referencing its owning snippet:
- Convention-compliance: manifest version-form per profile, always-invisible view fields carry an
  explanatory XML comment from v18, renames done via `old_technical_name` with no migration script
  for no-data modules - per ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md.
- Perf-lens: no per-record `mapped()` aggregate over a high-volume model (`hr.attendance`,
  `stock.move`, `account.move.line`, `account.analytic.line`) in a stored compute - use a grouped
  `_read_group`.
- i18n: P5.7 ran, or was correctly auto-SKIPPED with the recorded reason.

**PR body construction (pre-render from structured artifacts - not grep of plan.md prose):**
The orchestrator constructs adapted-modules and deleted-modules lists from the structured
verdict data it holds at this point (not by grepping plan.md prose, which risks false-positives).
PR body template:

```markdown
## Cluster upgrade: <src> -> <tgt>

### Modules adapted
<orchestrator inlines the list of REWRITE/KEEP/MERGE/SPLIT modules from the
 structured verdict list built during P2-P4 - one line per module with action>

### Modules deleted
<orchestrator inlines the list of DELETE-absorbed + OBSOLETE modules with their
 reasons - sourced from the structured verdict list, not grep of plan.md prose>

### Test result
See .odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/install-test.md - all waves green.

### Review request
Please review modules in dependency order (leaves first):
<topo_order from graph.md>
```

**Push and open PR - delegate in sequence (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):**
1. Push branch - dispatch git-operator: op push `upg/<src>-<tgt>-<cluster>` to the fork remote
   (resolve fork remote URL from `git remote get-url origin` or a dedicated fork remote).
2. Open PR - dispatch github-operator: op create PR; upstream org/repo and base branch resolved
   from `git remote get-url origin`; head `upg/<src>-<tgt>-<cluster>`; title
   `upg: <cluster> <src>-><tgt> - cluster upgrade`; body from the PR body template above.

Review delegation brief:
```
TARGET: worktree:<path>/upg-integration
REVIEW ORDER: <topo_order from graph.md> (leaves first)
CONTEXT: cross-major upgrade <src>-><tgt> for cluster <cluster>
         modules in scope: <cluster_list>
         breaking changes applied: see version-delta.md
         deleted modules: <delete_list> (absorbed by core or obsolete - do NOT raise business findings for these)
```

---

## Reused skill SSOTs (cross-reference only - do NOT copy)

- `odoo-deprecation-audit` protocol: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deprecation-audit/SKILL.md`
- `odoo-version-diff` output format: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-version-diff/SKILL.md`
- `odoo-gap-analysis` output format: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-gap-analysis/SKILL.md`
- `odoo-coding` ADAPT tier table: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` Phase 0 step 5
- `odoo-instance` dispatch: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md`
- `odoo-i18n` reconcile (P5.7): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/SKILL.md`
- Concurrency guard (Mode B): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
- Symbol grounding § 2 / § 2.5 (P1d): `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`
- Odoo upgrade conventions: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`
- F0 version-pivot SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`
- Runbot parity checklist (P5 gate + pre-PR): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`
- Worker brief format: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`
- Continuation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
- Disk fallback protocol: `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`
- Instance lifecycle: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md`
- Odoo testing: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`
