# upg-phase-detail - per-phase requests + dispatch briefs

**Contents:** Symbols (resolve once, reuse everywhere) - Artifact paths - P0 - Intake subagent dispatch brief - P1 - Recon parallel dispatch - P2 - Core-absorption dispatch briefs - P2b - Hard-call design (conditional route-out) - P3 - Plan Mode content template. Phases P4 to P7, Commit consolidation and Checkpoint / resume: `upg-phase-detail-p4-p7.md`.

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
Progress ledger: `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`; schema, writers and
  per-phase skip rules: `upg-phase-detail-p4-p7.md` § Checkpoint / resume.

---

## P0 - Intake subagent dispatch brief

Decision and gate: the SKILL.md pipeline bullet P0. Procedure is the brief below.

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

Four dispatches fire simultaneously (Mode B concurrency): P1a DAG, P1b deprecation audit, P1c version delta, P1d transitive symbol survey. The deprecation audit also runs the TARGET-version survival pass; the DAG read uses BOTH descriptor names (§ P0). Decision and outputs: the SKILL.md pipeline bullet P1.

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

### P1c - Version delta (Skill tool: odoo-version-diff, sonnet)

Dispatch via Skill tool at sonnet. Brief:
```
From version: <source_version>
To version: <target_version>
Focus: developer track (API breaking changes, removed symbols).
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

Decision, concurrency and verdict set: the SKILL.md pipeline bullet P2. The comparator brief below carries the rest.

**Deferred work [same per-module read].** The same `odoo-diff-comparator` dispatch additionally scans every in-scope file
(`.py` incl. `__manifest__.py`, tests, `.xml`, `.js`, `.csv`, `.po`, README/docs) for a
case-insensitive marker set - `TODO`/`todo`/`Todo`/`ToDo`/`@todo`, `FIXME`, `XXX`, `HACK` - and
classifies each hit against the target series X (`<target_version>`): anchored to X or to an
already-passed LOWER version -> **DUE** (execute NOW, in THIS upgrade); anchored to a HIGHER
future version -> **DEFERRED** (leave it untouched); no parseable version anchor ->
**UNANCHORED** - record it and flag it for the human, never silently absorbed into DUE nor
silently dropped. The comparator returns this as a compact `deferred_work` block inside
`absorption/<module>.md` (never raw grep output); never grep module source yourself for this. For a module that survives (KEEP/REWRITE/
MERGE/SPLIT), every DUE item becomes REAL upgrade work: P4 folds it into that module's SAME
implement -> P4b review -> P5 test path (`upg-phase-detail-p4-p7.md` § P4, brief step 0b).

Per module in dep order (topo_order from graph.md), parallel within the same dependency level
(modules at the same depth in the DAG); a module is NOT dispatched until its in-cluster
dependencies have finished P2. Concurrency: Mode B, model-weighted budget 8
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

The comparator owns the whole-module DELETE-absorbed derivation.

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

Dispatch via Skill tool at sonnet. Brief:
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

Decision list: the SKILL.md pipeline bullet P2b (route-out to `odoo-solution-design`, opus). Match directly on the return block's `verdict:` field, never on the `proposed_classification` count aggregate. Precision the list omits:
- `MERGE` and `SPLIT` route always; `RECONCILE` (data-divergence or new-feature wire-in) and `MIXED` (resolve the per-feature verdicts) route always, the whole module.
- `REWRITE(api)` changes the PUBLIC MODEL SURFACE when it adds/removes/retypes a stored field or changes a public method signature on an extended core model.
- A non-trivial `KEEP (with adaptation)` meets the `odoo-solution-design` § Before dispatch (step 3, `SRS_REQUIRED`) criterion (overrides `create`/`write`/`unlink`, a method with >=3 override-chain entries, a cross-model computed chain, a multi-company/branch change).
- A trivial REWRITE(api)/KEEP (localized fix, <= 5 call sites, 1 module, no public-surface change) skips design and goes to P3.

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
| <m5>   | already-installable | KEEP + [FIX] | n/a | n/a | haiku | n/a |
| <m3>   | upgraded | KEEP | n/a | n/a | haiku | n/a |

**DELETE confirmations required (one per row, separate from plan approval):**
- Delete m1 (absorbed by account/reconcile_model - behavioral equivalence verified)? (approve / skip / cancel)
- Delete m4 (OBSOLETE - <reason>)? (approve / skip / cancel)

### Deferred work (every surviving module: KEEP / REWRITE / MERGE / SPLIT)
- <m2>: <n> DUE version-anchored items (real P4 work)
- UNANCHORED markers, listed in full for the human (never silently absorbed or dropped; they stay flagged for the P6 gate): <module>: <marker, file:line>

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

The `Docs:` line follows the Documentation routing rule in `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` (taken from `odoo-intake`'s routing facts in the brief, else decided by that rule, ask only on a miss; `refine: no docs` drops it).

After `ExitPlanMode` and user approval: write `plan.md` (SSOT for P4+).

---
