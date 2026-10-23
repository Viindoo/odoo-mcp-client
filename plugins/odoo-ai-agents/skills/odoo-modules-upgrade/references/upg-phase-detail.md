# upg-phase-detail - per-phase requests + dispatch briefs

git-ops requests, subagent dispatch briefs, and artifact formats for the
`odoo-modules-upgrade` skill.

---

## Symbols (resolve once, reuse everywhere)

- `<cluster>` = `cluster_slug` resolved in P0 intake (the scope slug).
- `<path>` = the upgrade-worktree base: a `.upg-worktrees/` directory SIBLING to the principal
  checkout (NEVER inside it - keeps the principal checkout clean). All worktrees below live under it.
- `<work-base>` = the base ref the integration branch forks from, resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch resolution.

## Artifact paths

Base: `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured
absolute path)
Integration worktree: `<path>/upg-integration` (JOB tier, created at P4 post-gate)
Child worktrees: `<path>/upg-<module>` per module (WORK tier, created + removed in P4)
Progress ledger: `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
  Schema: `{"<module>": "pending|absorbed|designed|adapted|reviewed|installed|done"}`
  Written after each module completes a phase. Per-phase skip rules on resume:
  P2 skips {absorbed, designed, adapted, reviewed, installed, done};
  P4 skips {adapted, reviewed, installed, done};
  P4b skips {reviewed, installed, done};
  P5 skips {installed, done} at the dependency-level granularity.

---

## P0 - Intake subagent dispatch brief

Model: haiku. Read-only. Output file: `intake.md`.

```
TASK: Resolve the upgrade request into structured inputs.

(1) Read the current branch name (the `branch` of a `repo_facts` call on the repo). Infer the Odoo SERIES
    `<S>` from it: a branch named `<S>`, `<S>-feat-x`, or `release-<S>` -> series `<S>`.
    If the branch name is ambiguous, mark as open_question.
    Cross-check: read a sample of module descriptors (BOTH names, as in (3a)) and find the MAX `version` series
    present on disk. If the branch-inferred series and the manifest-max series disagree
    (e.g. branch says `<S>` but manifests say `<S-1>.x.y.z`), raise as open_question
    rather than silently trusting the branch name.
    EXCEPTION - the manifests carry a SHORT `version` (2-3 numeric parts, no series prefix; the
    normal form, see `references/upg-classification-table.md` § Manifest breaks): there is no series
    in the manifest to compare, so SKIP the branch-vs-manifest-series cross-check entirely and
    resolve the source series from branch + profile. Do NOT raise a false "disagree" open_question.
    The current-branch read is ONLY for the SOURCE series; never use it to resolve `<work-base>`
    (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch resolution).

(2) Map that series to the OSM profile:
    - set_active_version(odoo_version='<inferred_series>')
    - list_available_profiles()
    - For each profile that looks relevant (name contains the series or is the default),
      profile_inspect(name='<profile>', method='summary', odoo_version='<inferred_series>') to confirm repos + module set.
    Report the matched_profile and its repos.

(3) Auto-detect CANDIDATE MODULES using a manifest-version-series scan:
    a. Find all module descriptors - glob BOTH names:
       find . \( -name "__manifest__.py" -o -name "__openerp__.py" \) 2>/dev/null
    b. For each manifest, extract the `version` field. A module is a CANDIDATE if its
       manifest `version` major series is LESS THAN the target series
       (e.g. version `<S-1>.1.2.3` when target is `<S>`).
    c. Also include any module that depends on a stale-versioned candidate (depends-on-stale
       scan: read each manifest's `depends` list and include modules whose direct dep is
       already in the candidate set).
    d. `installable: False` is a WEAK HINT only - log it alongside the candidate, never use it
       as the primary detector.
    e. Step (b) keys on a series prefix, so a manifest carrying the short form (`1.0.0`) yields
       NOTHING from it; never read that silence as "no candidates". Whenever (b) returns nothing, detect candidates by PROFILE
       MEMBERSHIP (`profile_inspect` module set) intersected with branch series + repo path instead;
       candidacy_reason = `profile-membership`.
    Emit the candidate list with paths and the reason for candidacy (version-series|depends-on-stale|profile-membership|installable-hint).

(4) Determine:
    - source_version: from the matched profile's Odoo version or the manifest `version`
      field (e.g. `<S-1>.1.0.0` -> series `<S-1>`).
    - target_version: from the NL ask (an explicit target in the ask; "next major" -> the
      major after source_version). If not determinable, mark as open_question.

(5) Dependency hints: for each candidate module, read its descriptor's `depends`
    field and emit {module: [dep1, dep2, ...]} pairs.

(6) If the user's MODULE SCOPE is not explicit in the NL ask, do NOT guess. Return
    candidate_modules + proposed_cluster (seeded from the dependency closure of the
    confirmed candidate modules - read each candidate's `depends` recursively to include
    all in-repo transitive deps; do NOT use naming/path proximity as the primary
    scoping heuristic) + an open_question asking the user to confirm or narrow.

OUTPUT FORMAT (write to intake.md):
```yaml
resolved_series: "<S>"
matched_profile: "<profile>"
cluster_slug: "l10n_vn"   # scope slug; becomes <cluster> in every artifact path + worktree/branch name
source_version: "<S-1>"
target_version: "<S>"
series_cross_check: "branch=<S>, manifest_max=<S-1> -> DISAGREE -> open_question raised"
  # when the manifests already carry the short form: "skipped (short-form manifest, no series prefix)"
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
  - "Confirm: upgrade l10n_vn_custom + l10n_vn_custom_report to <S>? (detected via manifest version-series scan)"
```
```

---

## P1 - Recon parallel dispatch

Fire four dispatches simultaneously (Mode B concurrency): P1a DAG, P1b deprecation audit, P1c
version delta, P1d transitive symbol survey.

### P1a - DAG build (Explore, haiku)

```
TASK: Emit the dependency graph for the confirmed cluster, including the FULL transitive
external/core dependency closure and any dependency identity changes at target.

For each module in: <confirmed_cluster>
  Read the module's descriptor (`__manifest__.py`, or `__openerp__.py` on the oldest series); extract the `depends` list.
  Emit {module: str, path: str, depends: [str]}.

FULL TRANSITIVE CLOSURE (incl. external/core deps):
  Recursively collect ALL deps, including deps of in-cluster modules' deps that are
  external (not in-cluster) or core modules. For each dep at any level:
    check_module_exists(name='<dep>', odoo_version='<target_version>')
  Flag:
  - dep where exists=false at target as 'dep_missing_at_target: true'
  - dep where the module was RENAMED, MOVED, or SPLIT at target (e.g. a community module
    absorbed into core, or an account_* reorg): use api_version_diff + module_inspect to
    detect identity changes. Flag as 'dep_identity_changed: true' with the new identity.

Output: graph.md (YAML block listing each module + deps + missing flag + identity_changed flag)
```

Transcribe the worker's returned YAML into `graph.md` VERBATIM
(`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 3), then topo-sort to
produce `topo_order: []` (leaves first) and append it to graph.md.

### P1b - Deprecation audit (Skill tool: odoo-deprecation-audit, haiku)

Dispatch via Skill tool at haiku. Brief:
```
Source version: <source_version>
Target version: <target_version>
Modules: <confirmed_cluster as comma-separated list>
REPO_ROOT: <absolute path to the repository root>
MODULE_PATHS: <comma-separated absolute paths from intake.md candidate_modules[].path>
matched_profile: <matched_profile from intake.md>
Run the TARGET-version survival pass (symbols stable at <source> but deprecated/removed at
<target> - the upgrade-critical class find_deprecated_usage misses when pinned to source).
Output to: <ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/deprecation.md
```

Consume its output as a per-module fix list in P4.

### P1c - Version delta (Skill tool: odoo-version-diff)

Dispatch via Skill tool. Brief:
```
From version: <source_version>
To version: <target_version>
Focus: developer track (API breaking changes, removed symbols, migration notes).
Output to: <ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/version-delta.md
```

Consume its Removed APIs + Changed signatures tables in P4 via the breaking-change catalog.

### P1d - Transitive Symbol Survey (Explore, haiku, read-only)

P1d grounds every external/core symbol the cluster references AT THE TARGET.

```
TASK: Transitive symbol-survival survey for cluster '<cluster>' upgrading <src> -> <tgt>.
MODULE PATHS: <comma-separated absolute paths from intake.md candidate_modules[].path>

1. set_active_version(odoo_version='<target_version>').
2. Scan the cluster source for every symbol that references an EXTERNAL/core dependency
   (a dep NOT in the cluster): model `_inherit` / `env['<model>']` targets, fields read/written
   on those models, ORM chains 3+ levels deep, method calls/overrides, `env.ref` / template
   xml_ids, and manifest `depends` entries.
3. Ground EACH symbol at the target using OSM per
   ${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md § 2 (per-symbol grounding) and
   § 2.5 (the seven autosilent symbol classes). Use
   `model_inspect` / `entity_lookup` / `api_version_diff` / `resolve_orm_chain` / `check_module_exists`.
4. Classify each symbol: SURVIVED | RENAMED | REMOVED | TYPE_CHANGED.
   Emit ONLY the non-SURVIVED ones as `blockers[]` (RENAMED/REMOVED/TYPE_CHANGED) - these gate P3/P4.
   For a CUSTOM `_inherit`/symbol OSM cannot resolve, that is an OSM MISS (custom code is not
   indexed), NOT absence at target: confirm against module source and label `grounded: hybrid`.

FALLBACK: if OSM is unreachable, run the grep-only enumeration from § 2/§ 2.5 and label the
whole survey `grounded: local-source - not OSM-indexed`; still emit best-effort blockers[].

OUTPUT: transitive-symbol-survey.md
FORMAT (return it as plain YAML lines, outside any code fence - its `grounded:` line is your
grounding claim, per ${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md §5):
  cluster: <cluster>
  grounded: "osm" | "hybrid" | "local-source"
  blockers:
    - module: <module>          # the cluster module that references the symbol
      symbol: <symbol>
      kind: model|field|method|orm-chain|xml_id|depends
      status: RENAMED|REMOVED|TYPE_CHANGED
      target_equivalent: <new symbol or null>
      fix_hint: "<one line: how to rewrite the call site at target>"
```

Transcribe the worker's returned YAML into `transitive-symbol-survey.md` VERBATIM
(`${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md` clause 3). Feed each module's
`blockers[]` into P4 as that module's PREEMPTIVE FIX LIST (before the deprecation + breaking-change fixes).

### P1 gate

Assert: DAG is acyclic. On cycle: surface the cycle edges as a `concerns:` entry +
list the cycle + ask the user to break it before P2 proceeds (do NOT hard-fail).
Assert: no dep_missing_at_target or dep_identity_changed (if any flagged, surface as a
`concerns:` entry + list affected deps with their new identity or missing status +
ask user to confirm the resolution before P2).
Record P1d `blockers[]` for P3/P4; a non-empty list is NOT a hard-fail; list it in the P3 plan.

---

## P2 - Core-absorption dispatch briefs

Per module in dep order (topo_order from graph.md), parallel within the same dependency level
(modules at the same depth in the DAG). Concurrency: Mode B, model-weighted budget 8
per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`.

### P2 - odoo-diff-comparator brief (per module)

Model: sonnet.

```
mode: upgrade
TASK: Core-absorption comparison for module '<module>' upgrading <src> -> <tgt>.

diff_scope: <path>
source_version: <source_version>
target_version: <target_version>
slug: <src>-<tgt>-<cluster>
repo_root: <absolute path to the repository root>
CLASSIFICATION TABLE: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md
```

The agent's own Step 1 (upgrade mode) and § 3c (Upgrade mode) define the feature inventory, the
deferred-work reconciliation, the classification-table walk, the
reuse-candidate sweep, the behavioral-equivalence check before any DELETE-absorbed verdict, and the
`absorption/<module>.md` format + Step 4 return block.

```
OUTPUT: write to absorption/<module>.md
FORMAT: module / grounded / verdict / features / reuse_candidates / whole_module_absorbed /
  absorbing_core_feature / deferred_work / behavioral_equivalence - per the
  agent's own § 3c template + Step 4 return block.
  vendor_api_checked: <pkg>@<found> -> adapted-to <newest> | <pkg>@<found> (newer <newest> deferred - <reason>) | <pkg>@<version-found> | over-cap (<n> packages) | not-triggered | unreachable
    # written at P4 step 0c (not at P2 comparator emission); one of the six forms in
    # ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md § Convention 0(c). P6 presents it.
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

Use its output as weak triangulation input only. The DELETE decision MUST rest on the
comparator's behavioral-equivalence proof (signal #5), not on a "Standard" gap-analysis tag.

---

## P2b - Hard-call design (conditional route-out)

Fires per the design-trigger table in SKILL.md § P2b.

Continuation Contract payload (emit verbatim, one route-out per module):

```yaml
status: paused-design
next: odoo-solution-design
inputs:
  return_to: odoo-modules-upgrade
  design_slug_hint: <src>-<tgt>-<cluster>-upg-<module>
  target_version: <target_version>
  modules: [<module>]
  intent_records: [<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/absorption/<module>.md]
  classification: "<verdict> - <one-line reason from absorption/<module>.md>"
```

`odoo-solution-design` under `return_to` runs its own design, then emits `next: odoo-modules-upgrade`
with `design_doc`; P3 Plan Mode + P4 coder are owned by THIS skill.

On re-entry (the plan runner returns with `design_doc`): read the `design_doc` path from the returned
contract `inputs`; record it against the module; set `checkpoint.json` `<module>: designed`;
proceed to P3 with the design linked - do NOT re-run design. If `design_doc` is ABSENT from the
returned inputs (design crashed before producing it), set the module back to `<module>: absorbed`
and re-enter P2b next run rather than advancing to P3 with no design.

Multiple modules may trigger P2b in one cluster. Route them one at a time (the plan runner advances
one design hop per yield); a module whose status is already `designed` is skipped on the next P2b
pass. P3 Plan Mode is entered only after EVERY P2b-triggered module in the cluster has a recorded
`design_doc`.

---

## P3 - Plan Mode content template

Present this between `EnterPlanMode` and `ExitPlanMode`
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request).

```markdown
## Upgrade Plan: <src> -> <tgt> for cluster <cluster>
Docs: <module | site | both | none> - <the facts that decided it>

### Per-module decision table
| Module | Class | Action | Absorbing core / Reason (if DELETE/OBSOLETE) | Behavioral-equiv proof (if DELETE) | ADAPT tier | Design doc |
|--------|-------|--------|----------------------------------------------|-------------------------------------|------------|------------|
| <m1>   | upgraded | DELETE-absorbed | account/reconcile_model | All 2 overrides (create, write) proven equivalent in core - see absorption/m1.md | n/a | n/a |
| <m4>   | upgraded | OBSOLETE | Workflow evaporated: <reason> | n/a (no absorption) | n/a | n/a |
| <m2>   | upgraded | REWRITE(api) | n/a | n/a | sonnet | n/a |
| <m5>   | already-installable (bump + migration when data moves, decided after P5) | KEEP + [FIX] | n/a | n/a | haiku | n/a |
| <m3>   | KEEP | n/a | n/a | haiku | n/a |

**DELETE confirmations required (one per row, separate from plan approval):**
- Delete m1 (absorbed by account/reconcile_model - behavioral equivalence verified)? (approve / skip / cancel)
- Delete m4 (OBSOLETE - <reason>)? (approve / skip / cancel)

### Adapt order (dependency-first, leaves first)
1. <m3> (no custom deps in cluster)
2. <m2> (depends on m3)
3. DELETE <m1> (depends on m2; will be removed after m2 adapted)

### Manifest version (Rule A - NOT bumped)
# Do NOT bump the manifest `version` for any module in this cluster. Short form already -> leave it
# byte-identical; series-prefixed -> convert to `x.y.z` (dropping a prefix is not a bump).
# Remedy + form: references/upg-classification-table.md § Manifest breaks, the Rule A row.
- <m2>: 1.0.0 (unchanged)
- <m3>: 2.0.0 (unchanged)
- <m4>: <series>.2.1.0 -> 2.1.0 (series prefix dropped, numbers untouched)

### Commit plan
Each row in the classification table above becomes one commit, requested via
`git-toolkit:git-ops`: the files touched, the business outcome (module, source series, target
series, action taken), and `WORKTREE_PATH`. Do not compose or prescribe the message.

### Risks
- <any dep_missing_at_target or dep_identity_changed flags from P1>
- <any ambiguous classification from P2>
```

After `ExitPlanMode` and user approval: write `plan.md` (SSOT for P4+).

---

## P4 - Adapt dispatch briefs

### Integration worktree creation

Invoke the `git-toolkit:git-ops` skill (via the Skill tool; see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`) to create a worktree:
- op: create a worktree on a new branch
- branch: `upg/<src>-<tgt>-<cluster>`
- worktree: `<path>/upg-integration`
- base: `<work-base>`

### Child worktree per module (WORK tier)

For each module, delegate all mutations to git-toolkit via the `git-ops` skill (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):

**Collapse first (`n <= 1`).** `n` = the number of modules requiring a P4 dispatch in THIS cluster,
read from `plan.md`'s P3 classification table (count the rows whose action is KEEP, REWRITE(api),
REWRITE(model), MERGE, SPLIT or RECONCILE; DELETE-absorbed and OBSOLETE rows need no coder and do not
count). `n <= 1` -> SKIP steps 1-3 below: dispatch the one module DIRECTLY into
`<path>/upg-integration`. `n >= 2` -> steps 1-3 as written; the child worktree is there for
poison-containment, whether or not two modules run at once; file-level disjointness does not
replace it. Semantics: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`.

1. Create child worktree - invoke `git-toolkit:git-ops` to add a worktree (branch
   `upg/<src>-<tgt>-<cluster>-<module>`, worktree `<path>/upg-<module>`,
   base `upg/<src>-<tgt>-<cluster>`).

2. Dispatch coder to `<path>/upg-<module>`.

3. Converge back - invoke `git-toolkit:git-ops` (single request): merge branch
   `upg/<src>-<tgt>-<cluster>-<module>` into `upg/<src>-<tgt>-<cluster>` no-ff in
   worktree `<path>/upg-integration`; then remove worktree `<path>/upg-<module>`;
   then delete branch `upg/<src>-<tgt>-<cluster>-<module>`.

### odoo-coding dispatch brief (via Skill tool, per module)

```
ODOO VERSION: <target_version>
MODULE: <module>
MODULE PATH: <path>
ACTION: <DELETE-absorbed | OBSOLETE | KEEP | REWRITE(api) | REWRITE(model) | MERGE | SPLIT>
WORKTREE_PATH: <path>/upg-<module>
RUN_ID: <this run's id>
SHARE_DIR: <the SAME literal resolved at P0 intake, per `## Base` above - substitute it>
ISOLATE_DIR: <the SAME literal resolved at P0 intake - substitute it, never re-resolve>

INPUTS:
- Absorption verdict: absorption/<module>.md
- Version-anchored deferred work DUE this upgrade (this module only): absorption/<module>.md
  `deferred_work` block, items with classification=DUE
- Preemptive fix list (this module's blockers[] - apply FIRST): transitive-symbol-survey.md
- Deprecation fix list (rows for this module only): deprecation.md
- Breaking-change catalog: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md
- Version delta (Removed + Changed for relevant symbols): version-delta.md
- Design doc (if P2b produced one): <path or "none">
- Conventions (apply on EVERY profile/distribution; this IS a modules-upgrade adapt):
  ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md § Convention 0 - code upgrade only, no
  old-series compatibility, no version bump, implement any `reuse_candidates[]` target-core mechanism
  instead of a shim; see INSTRUCTIONS step 0c below for the vendor-currency pass (clause (c)).

ADAPT TIER: <haiku | sonnet | opus | fable> (from upg-triage-table.md)

ADAPT FIELDS (ACTION=KEEP/REWRITE(api)/REWRITE(model)/MERGE/SPLIT only - omit all four for
DELETE-absorbed / OBSOLETE; the node's test leg reads them after the code is adapted):
MODE: adapt
INTENT: absorption/<module>.md `features` - the module's custom behavior, PRESERVED on the target
  (+ the P2b design doc's §9 when one exists). The test leg takes every expected value from here,
  never from the adapted code. A feature the module hands over to core is not listed - its old test
  goes to the coders' OBSOLETE TESTS report.
SOURCE TESTS: <the module's existing test files in WORKTREE_PATH (tests/, static/tests/,
  static/tours/) - adapted in place | none>
BROKEN TEST-SYMBOLS: <the P1d `blockers[]` and P1b deprecation.md rows for this module that its
  test files reference - symbol, status, target equivalent | omit when none>

INSTRUCTIONS:
If ACTION=DELETE-absorbed or ACTION=OBSOLETE:
  DANGLING-REFERENCE SWEEP (MANDATORY before directory removal):
  Grep the entire repo for references to the module's models, XML IDs, security groups,
  and env.ref targets that will become dangling after deletion:
    grep -rn "<module_model_names>" . --include="*.py" --include="*.xml" --include="*.csv"
    grep -rn "env.ref('<module>\." . --include="*.py"
    grep -rn "group_<module>" . --include="*.xml" --include="*.py" --include="*.csv"
    grep -rn "<xmlid from the module>" . --include="*.xml"
  The brief carries the module's model names (from absorption/<module>.md) and known XML IDs,
  sourced from `module_inspect(name='<module>', method='models', odoo_version='<source_version>')`
  + the module's data/security XML at SOURCE. For EACH dangling
  reference found: either rehome it to the absorbing core module/feature OR remove it.
  Document the rehoming decisions in the commit request's business-outcome description or an
  inline rehoming comment in the touched file.

  After the sweep, report findings to the orchestrating skill, which invokes
  the `git-toolkit:git-ops` skill (in this child worktree) to delete the module directory and commit
  the deletion (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
  git-ops request fields:
    - op: delete the module directory and commit the deletion
    - confirmed: yes - user confirmed DELETE <module> at P3 Plan Mode gate
    - business outcome (absorbed): delete <module> - absorbed by core <absorbing_core_feature> in <target_version> (no custom delta remains)
    - business outcome (obsolete): delete <module> - obsolete at <target_version> (<one-line reason why the need evaporated>)
  Do not compose or prescribe the commit message.
  dependers: <modules from graph.md that list '<module>' in their depends>
  For each module in dependers[], remove '<module>' from that module's
  descriptor (`__manifest__.py`, or `__openerp__.py` on the oldest series) `depends` list.

If ACTION=KEEP/REWRITE(api)/REWRITE(model)/MERGE/SPLIT:
  0. PREEMPTIVE FIX LIST (apply FIRST): for every blocker attributed to this module in
     transitive-symbol-survey.md (status RENAMED/REMOVED/TYPE_CHANGED), rewrite the call site
     to its `target_equivalent` per `fix_hint`, before the catalog passes below.
  0b. DUE VERSION-ANCHORED DEFERRED WORK: for every item in this module's absorption/<module>.md
     `deferred_work` block with classification=DUE, implement its `work_item` NOW, through the SAME implement -> P4b review -> P5 test
     path as every other change in this module. Leave DEFERRED items untouched in source; an UNANCHORED item is NEVER silently resolved here - it stays
     flagged for the P6 human gate.
  0c. VENDOR-CURRENCY BIAS (Convention 0(c), CORE - apply on every profile): decide the trigger,
     run the capped WebFetch/WebSearch pass, and ACT on the finding (adapt to the newest upstream
     API or record a deferral) for any third-party import this module's adapt touches
     (${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md § Convention 0(c)). Persist the outcome as the
     `vendor_api_checked:` field in THIS module's `absorption/<module>.md` (§ P2 output FORMAT above).
  1. Apply all deprecation fix-list items for this module (from deprecation.md).
  2. Apply all breaking-change items that affect this module (from upg-classification-table.md).
  3. For REWRITE(model): update field references, compute methods, search/domain expressions,
     and XML views that reference changed/removed fields. ALSO sweep:
     - `data/*.xml` - update record field values, domain attrs, and field refs
     - `demo/*.xml` - same as data/
     - `security/*.csv` (ir.model.access.csv) - update model names if model was renamed
     - `ir.rule` records - update domain expressions referencing renamed/removed fields
  4. Do NOT bump the manifest `version`: already short -> leave it byte-identical; series-prefixed
     -> CONVERT it to `x.y.z` by dropping the prefix (not a bump). Remedy + form:
     upg-classification-table.md § Manifest breaks, the Rule A row. Delete the module's `migrations/`
     directory (Convention 0) and write no migration script.
  4b. Set `installable: True` (flip from False) AFTER all other P4 fixes are applied, BEFORE P5
     runs - per the upg-classification-table.md manifest-break row. P5 confirms it installs.
  4c. Scan each module descriptor (BOTH names) for `# TODO: Uncomment when upgrading` markers left by the
     forward-port skill. Restore `auto_install`/`application` ONLY when the breadcrumb explicitly
     directs it - do NOT auto-detect from module name or depends structure.
  5. Tests: none here - the node's test leg adapts them after the code
     (${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § Code first, then the test leg).
  The coders run NO git; after they write their files the orchestrating skill (odoo-coding) commits
  via the git-toolkit:git-ops skill (sign-off only where the repo requires it - git-ops decides; per
  snippets/git-delegation.md).
  Commit request: files touched + business outcome (<module> <source_version>-><target_version> -
  <ACTION> <one-line summary>) + `WORKTREE_PATH`; git-ops composes the message.

AUTONOMOUS FIX: on a P5 failure for this module you are re-dispatched with the debugger's root
cause. Fix to that root cause only.
```

---

## P4b - Code-review loop (in-pipeline; per module, dep order; fix-until-clean before install)

Review each adapted module's diff BEFORE P5, fixing in a loop until no CRITICAL/HIGH remains. The
final P7 review still runs.

For each adapted module in topo_order (leaves first); skip DELETE-absorbed/OBSOLETE (no adapt diff):

```
SKILL: odoo-code-review
TARGET: worktree:<path>/upg-integration
SCOPE: module '<module>' adapt diff only (the module's adapt commit); attribute findings to
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
   (which module, which finding, what was tried).
Proceed to P5 ONLY when EVERY adapted module is `reviewed` clean.

---

## P5 - Install + test gate format

Install bottom-up one dependency level at a time (leaves first). Per-level green is recorded in `checkpoint.json` (status `installed` per module) and
`install-test.md`.

**Framework-validation gate is part of P5.** A module that flips `installable: False -> True` is
scanned by the target's FULL test suite for the first time AND loads its own `demo/` data for the
first time. Those are TWO builds: where this gate runs demo-less, the demo half is a separate
install-only build (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`
Gate 7b) with `DEMO: on` and NO `--test-enable`. The framework-validation checks (the `base`
view-arch one: every always-invisible view field needs an explanatory XML comment; the `hr`
self-access one: custom `hr.employee` fields need `groups='hr.group_hr_user'`) run in the UNTAGGED
suite; name them only in a tag-scoped run elsewhere, resolving each class name for the target series
first (${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md § Framework-validation test classes).
This gate is an automation-test build: take its demo shape from
${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md § Demo data by build PURPOSE and request no
`demo` for it. The P4b review for any flipped module MUST additionally cover ACL / `.sudo()` for
every create/write/compute override on a widely-used core model. Cross-ref
${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md.

Step 1 - create instance (once):
```
operation: create
series: <target_version>
demo: <the series default: the automation-test row of § Demo data by build PURPOSE - this database hosts every level's test run, which runs the series default; never `on` where demo defaults off>
SHARE_DIR: <the SAME literal resolved at P0 intake, per `## Base` above - substitute it>
ISOLATE_DIR: <the SAME literal resolved at P0 intake - substitute it, never re-resolve>
WORKTREE_PATH: <path>/upg-integration   # the P4 integration worktree, forwarded verbatim
```

For each dependency level in topo_order (leaves first), run Steps 2-3 before moving to the next level:

Step 2 - init (install) this level's modules:
```
operation: init
series: <target_version>
demo: <the SAME value as Step 1 - the level's test run reuses this database>
modules: <FULL transitive closure of THIS LEVEL's modules - including external/core deps from
          graph.md P1a's full closure - plus all previously installed modules, comma-separated>
CONFIRM: "confirm each module in this level emits a Loading line; report per-module install status"
```

Step 3 - run tests for this level:
```
operation: run-tests
series: <target_version>
modules: <THIS LEVEL's modules only, comma-separated>
flags: --test-enable
test_tags: <`/<m>` for every module in THIS LEVEL, comma-joined - never untagged
           (${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md)>
GATE_ROLE: node-verify   # REQUIRED on any test-enable dispatch; a per-level verification
CONFIRM: "report per-module test result for this level"
```

**After the level containing a module whose `installable` this run flipped, run the two
installable-flip gates as SEPARATE builds - they ADD to Step 3, never replace it:**

- **Gate 7** (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`) -
  the full UNTAGGED suite on a FRESH database.
- **Gate 7b** (same file) - the install-only demo-load build, `DEMO: on`, no `--test-enable`.

Run them in that order, each on its own instance, and record both verdicts in `install-test.md`
alongside the level result. You are the run-level owner of each flip-gate instance
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once its verdict is recorded, call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with its `lease_token` and `run_id`. Keep the
Step 1 instance until the last level is green, then release it the same way (the P5 instance release step).

After each level: write level result to `install-test.md` and update `checkpoint.json`
(set `installed` for each module in the level that passed). On FAILURE in a level:
dispatch `odoo-backend-debugger` or `odoo-ui-debugger` with the traceback + module source, plus
`ISOLATE_DIR:` (the SAME literal resolved at P0 intake, per `## Base` above) and
`SLUG: <cluster>-level<n>` - `odoo-ui-debugger` composes
`<ISOLATE_DIR>/visual/debug/<cluster>-level<n>/` from both literals and MUST NOT re-resolve one.
Receive proven root cause -> feed back to P4 for the affected module only (dispatch
`odoo-coding` with `AUTONOMOUS FIX` sentinel + root cause). Re-run P5 FROM THE FAILING
LEVEL (skip levels already recorded as `installed` in `checkpoint.json`).

Final `install-test.md` schema:

```yaml
# install-test.md
cluster: <cluster>
target_version: <target_version>
levels:
  - level: <n>
    modules: [<m1>, <m2>]
    install_ok: true | false
    test_result: passed | failed | error
    root_cause: null | "<proven root cause from debugger>"
per_module:
  - module: <m>
    level: <n>
    install_ok: true | false
    test_result: passed | failed | error
    root_cause: null | "<proven root cause from debugger>"
flip_gates:            # one entry per module whose `installable` THIS run flipped; omit the key
  - module: <m>        # entirely when no module flipped
    gate7: passed | failed | error          # full untagged suite on a fresh DB
    gate7b: passed | failed | error | n/a   # demo-load build; n/a where gate7 already carried demo
    notes: null | "<what failed>"
overall: green | red
```

`flip_gates` is a REQUIRED key whenever this run flipped any module's `installable`; record the
verdicts under this key, never as free text.

---

## P5.7 - i18n reconcile (MANDATORY; narrow escape only)

Run the `odoo-i18n` skill as a post-install phase. Never blind-regenerate: load the existing `.po`
into a fresh instance before re-export, then diff-review.

MANDATORY for every SURVIVING module of the cluster (KEEP, REWRITE(api), REWRITE(model), MERGE,
SPLIT, RECONCILE); a content diff is NOT the gate. The ONLY skips are the enumerated escapes in
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` § Escape hatches, and each one is RECORDED in
`install-test.md` - never silent. DELETE-absorbed and OBSOLETE modules skip via E1.

When it runs:
```
SKILL: odoo-i18n
INSTANCE: SELF_PROVISION - odoo-i18n builds its own export instance (i18n caller obligation 5;
          `${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` KT4). Never inherit the
          P5 instance
MODULES: <cluster adapted modules>
TARGET_VERSION: <target_version>
MODE: reconcile (non-destructive)
WORKTREE_PATH: <the P4 integration worktree - .po/.pot are git-tracked>
SHARE_DIR: <the SAME literal resolved at P0 intake, per `## Base` above - substitute it>
ISOLATE_DIR: <the SAME literal resolved at P0 intake - substitute it, and do NOT re-resolve or
  improvise one from a worktree cwd>
TARGET LANGUAGES: <explicit list when this run has one, else omit the field entirely>
RETURN: the result; present it at the P6 sign-off
STEPS (detail owned by odoo-i18n):
  1. fresh instance with en_US + each existing <lang>.po loaded, then re-export each <lang>.po
  2. git-ops diff-review each re-exported <lang>.po against its committed version; adjudicate every
     removed/changed msgid into the THREE buckets CORRECT / ARTEFACT / WRONG defined in
     `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` (apply the ARTEFACT test BEFORE ruling
     WRONG) - preserve every existing msgstr except an adjudicated-CORRECT loss
  3. translate every entry left with an empty `msgstr`; one whose correct translation equals its
     `msgid` stays EMPTY and is not residual - never write the `msgid` into it
     (`${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`)
  4. reload with `-u <module>` on the instance and confirm the catalog loads
```
Output: `i18n-reconcile.md` (per-module: residual count, translated count, skipped?).

---

## Commit consolidation (P6/P7 capability)

NEVER collapse the whole cluster into ONE commit. Consolidate a single module's WIP/fixup commits
into ONE clean commit per module when a module accumulated fixups during P4/P4b.

Delegate the entire consolidation sequence to git-toolkit via the `git-ops` skill for each module in dependency order
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
- op: consolidate module commits in integration worktree
- worktree: `<path>/upg-integration`
- scope: `<module>/` subtree only (do NOT stage other modules)
- base: the first commit SHA recorded for this module. Record each module's first commit SHA
  returned by the git-ops converge step and pass it as `base`; never re-discover it from the log.
  Fallback when no recorded SHA: `<work-base>`.
- business outcome: <module> <src>-><tgt> - <ACTION> <summary> (do not compose or prescribe the message)
- confirmed: yes - Plan Mode approved at P3 (consolidation listed in commit plan; backup ref created by git-ops)
- Result git-ops guarantees: ONE commit holding only `<module>/`, with a tree IDENTICAL to the
  tree before the consolidation (a safety backup is taken first and removed after the check).
- On S6 failure git-ops returns BLOCKED (gate_hit: S6 tree-identity mismatch). Recovery: invoke
  `git-toolkit:git-ops` to restore the tree from the backup and escalate
  BLOCKED listing the differing trees.

Squash alternative: ask `git-toolkit:git-ops` to fold the module's fixup commits into the
commits they fix; git-ops handles the non-TTY environment natively.
Keep exactly ONE commit per module; never one commit per cluster.

---

## P7 - Final review, then PR creation command

Order (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail): checklist -> final
dep-order review -> push -> open PR.

**Pre-PR checklist.** Run the Runbot parity gates
(${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md) PLUS
these passes before opening the PR, each cross-referencing its owning snippet:
- Convention-compliance: manifest version-form is the short form with no series prefix and no bump
  (references/upg-classification-table.md § Manifest breaks, the Rule A row) and always-invisible
  view fields carry an explanatory XML comment - per ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md.
  No upgraded module carries a `migrations/` directory (Convention 0); none is retargeted here.
- Migration notes: `migration-notes.md` is written in the run dir (SKILL.md § P7) from
  `transitive-symbol-survey.md` `blockers[]`, `absorption/*.md`, `version-delta.md` and the
  `migrations/` paths the P4 commits deleted; it lists renamed or removed models, fields, xmlids and
  selection values, changed field types, modules deleted as absorbed, changed `noupdate` data and
  each deleted `migrations/` directory. It is written without asking and never blocks the run.
- Perf-lens: no per-record `mapped()` aggregate over a high-volume model (`hr.attendance`,
  `stock.move`, `account.move.line`, `account.analytic.line`) in a stored compute - use a grouped
  `_read_group`.
- i18n: P5.7 ran for every surviving module, or each skip is a RECORDED enumerated escape
  (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` § Escape hatches) - never a silent
  content-diff skip.

**Final dep-order review (BEFORE the push and the PR).**
Delegate the review of the integration worktree with the brief below, fix every CRITICAL/HIGH
finding on `<path>/upg-integration` (dispatch `odoo-coding` at the module's ADAPT tier, the SAME
loop shape as § P4b), and review again until none remains; MED/LOW are recorded on the module rows
of `install-test.md`. Only when it returns no CRITICAL/HIGH do the push and PR steps below run.

Review delegation brief:
```
TARGET: worktree:<path>/upg-integration
REVIEW ORDER: <topo_order from graph.md> (leaves first)
CONTEXT: cross-major upgrade <src>-><tgt> for cluster <cluster>
         modules in scope: <cluster_list>
         breaking changes applied: see version-delta.md
         deleted modules: <delete_list> (absorbed by core or obsolete - do NOT raise business findings for these)
```

**PR body construction:** build the adapted-modules and deleted-modules lists from the structured
verdict data (never by grepping plan.md prose). PR body template:

```markdown
## Cluster upgrade: <src> -> <tgt>

### Modules adapted
<REWRITE/KEEP/MERGE/SPLIT modules from the structured verdict list - one line per module with action>

### Modules deleted
<DELETE-absorbed + OBSOLETE modules with their reasons, from the structured verdict list>

### Test result
See <ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/install-test.md - all levels green.

### Migration notes
See <ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/migration-notes.md.

### Review request
Please review modules in dependency order (leaves first):
<topo_order from graph.md>
```

**Push and open PR - invoke `git-toolkit:git-ops` in sequence (see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):**
1. Push branch - invoke `git-toolkit:git-ops` to push `upg/<src>-<tgt>-<cluster>` to the fork remote
   (resolve the fork remote from the `remotes` of a `repo_facts` call, or a dedicated fork remote).
2. Open PR - invoke `git-toolkit:git-ops` to create the PR: upstream org/repo resolved
   from the `origin_url` of a `repo_facts` call, base branch per the plan; head `upg/<src>-<tgt>-<cluster>`; title
   `<cluster> cluster upgrade <src>-><tgt>`; body from the PR body template above.

After the PR exists, only PR-OBSERVING work remains: CI-failure triage and the human merge. Do NOT
delegate another worktree review here - the final review above already cleared.

---

## Cross-references

- Model tiers and concurrency guard (Mode B): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
- Symbol grounding § 2 / § 2.5 (P1d): `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`
- Odoo upgrade conventions: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`
- F0 version-pivot SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`
- Runbot parity checklist (P5 gate + pre-PR): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`
- Worker brief format: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`
- Continuation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
- Disk fallback protocol: `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`
- Instance lifecycle: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`
- Odoo testing: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`
