# upg-phase-detail - per-phase commands + dispatch briefs

SSOT for verbatim git commands, subagent dispatch briefs, and artifact formats for the
`odoo-modules-upgrade` skill. The SKILL.md body states WHAT each phase achieves; this
file specifies HOW. Cross-references reused skills' SSOTs; copies none.

---

## Artifact paths

Base: `.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/`
Integration worktree: `<path>/upg-integration` (JOB tier, created at P4 post-gate)
Child worktrees: `<path>/upg-<module>` per module (WORK tier, created + removed in P4)
Progress ledger: `.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
  Schema: `{"<module>": "pending|absorbed|designed|adapted|reviewed|installed|done"}`
  Written after each module completes a phase. On resume, P2-P5 skip `done` modules.

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
    Emit the candidate list with paths and the reason for candidacy (version-series|depends-on-stale|installable-hint).

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
source_version: "16.0"
target_version: "17.0"
series_cross_check: "branch=17.0, manifest_max=16.0 -> DISAGREE -> open_question raised"
candidate_modules:
  - path: "l10n_vn_custom/"
    module: "l10n_vn_custom"
    candidacy_reason: "version-series"  # version-series | depends-on-stale | installable-hint
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

Three dispatches fire simultaneously (Mode B concurrency, independent).

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
Output to: .odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/deprecation.md
```

`odoo-deprecation-audit` has its own protocol (find_deprecated_usage + api_version_diff +
lookup_core_api rounds). Do NOT replicate it here; it owns its own SSOT.
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

### P1 gate

Assert: DAG is acyclic. On cycle: surface the cycle edges as `DONE_WITH_CONCERNS` +
list the cycle + ask the user to break it before P2 proceeds (do NOT hard-fail).
Assert: no dep_missing_at_target or dep_identity_changed (if any flagged, surface as
`DONE_WITH_CONCERNS` + list affected deps with their new identity or missing status +
ask user to confirm the resolution before P2).

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
      - MERGE: this module + another cluster module are now best combined
      - SPLIT: this module has grown to warrant splitting
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
  verdict: DELETE-absorbed | OBSOLETE | KEEP | REWRITE(api) | REWRITE(model) | MERGE | SPLIT | MIXED
  features:
    - name: <feature_description>
      classification: <class>
      evidence: <OSM citation>
      proposed_action: <action>
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

Fires when a module's P2 verdict matches the design-trigger table in SKILL.md § P2b -
ALWAYS for MERGE / SPLIT / REWRITE(model with a field-type change) / DELETE-absorbed (with
risk); AND for REWRITE(api) or KEEP when the adaptation is NON-TRIVIAL (changes the module's
public model surface, OR touches > 5 call sites, OR spans >= 2 modules, OR meets the
solution-design non-trivial criterion). A trivial localized fix (<= 5 call sites, 1 module, no
public-surface change) skips design. DELETE-absorbed (no risk) and OBSOLETE never route - the
module is removed, not adapted.

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

### Manifest version bumps required
- <m2>: 16.0.1.0.0 -> 17.0.1.0.0
- <m3>: 16.0.2.0.0 -> 17.0.2.0.0

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

```bash
git worktree add -b upg/<src>-<tgt>-<cluster> <path>/upg-integration <work-base>
```

### Child worktree per module (WORK tier)

```bash
git worktree add -b upg/<src>-<tgt>-<cluster>-<module> <path>/upg-<module> upg/<src>-<tgt>-<cluster>
# ... dispatch coder to <path>/upg-<module> ...
# converge back:
cd <path>/upg-integration && git merge --no-ff upg/<src>-<tgt>-<cluster>-<module>
git worktree remove <path>/upg-<module>
git branch -d upg/<src>-<tgt>-<cluster>-<module>
```

### odoo-coding dispatch brief (via Skill tool, per module)

```
ODOO VERSION: <target_version>
MODULE: <module>
MODULE PATH: <path>
ACTION: <DELETE-absorbed | OBSOLETE | KEEP | REWRITE(api) | REWRITE(model) | MERGE | SPLIT>
WORKTREE: <path>/upg-<module>

INPUTS:
- Absorption verdict: absorption/<module>.md
- Deprecation fix list (rows for this module only): deprecation.md
- Breaking-change catalog: ${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md
- Version delta (Removed + Changed for relevant symbols): version-delta.md
- Design doc (if P2b produced one): <path or "none">

ADAPT TIER: <haiku | sonnet | opus | fable> (from upg-triage-table.md)

INSTRUCTIONS:
If ACTION=DELETE-absorbed or ACTION=OBSOLETE:
  DANGLING-REFERENCE SWEEP (MANDATORY before git rm):
  Grep the entire repo for references to the module's models, XML IDs, security groups,
  and env.ref targets that will become dangling after deletion:
    grep -rn "<module_model_names>" . --include="*.py" --include="*.xml" --include="*.csv"
    grep -rn "env.ref('<module>\." . --include="*.py"
    grep -rn "group_<module>" . --include="*.xml" --include="*.py" --include="*.csv"
    grep -rn "<xmlid from the module>" . --include="*.xml"
  The orchestrator pre-populates the module's model names (from absorption/<module>.md)
  and known XML IDs (from module_inspect at source) in the brief. For EACH dangling
  reference found: either rehome it to the absorbing core module/feature OR remove it.
  Document the rehoming decisions in the commit message or a `# upg: rehomed` comment.

  After the sweep:
  git rm -r <path>
  dependers: <list of modules pre-populated by the orchestrator from graph.md that list
  '<module>' in their depends - the orchestrator resolves this BEFORE dispatching the
  brief so the coder does not need to re-discover them>
  For each module in dependers[], remove '<module>' from that module's
  __manifest__.py `depends` list.
  Commit message (absorbed): "upg: delete <module> - absorbed by core <absorbing_core_feature> in <target_version> (no custom delta remains)"
  Commit message (obsolete): "upg: delete <module> - obsolete at <target_version> (<one-line reason why the need evaporated>)"

If ACTION=KEEP/REWRITE(api)/REWRITE(model)/MERGE/SPLIT:
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
  4. Bump manifest version: replace the source series prefix with the target series prefix
     (e.g. 16.0.1.2.3 -> 17.0.1.2.3).
  5. If a migration script is genuinely needed (field type change with data to preserve,
     renaming with existing data), write it inline under migrations/<target_version>/
     as a standard Odoo migration script. This is the EXCEPTION, not the default.
  6. Write or adapt tests: test the adapted behavior, not the old source text. RED first.
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

Step 1 - create instance (once):
```
operation: create
series: <target_version>
demo: off
```

For each wave in topo_order (leaves first), run Steps 2-3 before moving to the next wave:

Step 2 - init (install) this wave's modules:
```
operation: init
series: <target_version>
modules: <transitive closure of THIS WAVE's modules + all previously installed modules,
          comma-separated - ensures deps are re-specified so Odoo's dep-order logic holds>
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

## P7 - PR creation command

```bash
# Artifact base dir (absolute)
ARTIFACT_DIR=".odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>"
INSTALL_TEST_MD="${ARTIFACT_DIR}/install-test.md"

# Pre-render PR body from structured artifacts (not free-text grep of plan.md).
# The orchestrator constructs these lists from the structured verdict data it holds
# at this point (not by grepping plan.md prose which may contain keyword false-positives).
PR_BODY_FILE="$(mktemp /tmp/pr-body-XXXXXX.md)"
cat > "${PR_BODY_FILE}" <<EOF
## Cluster upgrade: <src> -> <tgt>

### Modules adapted
<orchestrator inlines the list of REWRITE/KEEP/MERGE/SPLIT modules from the
 structured verdict list built during P2-P4 - one line per module with action>

### Modules deleted
<orchestrator inlines the list of DELETE-absorbed + OBSOLETE modules with their
 reasons - sourced from the structured verdict list, not grep of plan.md prose>

### Test result
See ${ARTIFACT_DIR}/install-test.md - all waves green, all modules passed.

### Review request
Please review modules in dependency order (leaves first):
<topo_order from graph.md>
EOF

git push davidtranhp upg/<src>-<tgt>-<cluster>
gh pr create \
  -R Viindoo/<repo> \
  --base <work-base> \
  --head davidtranhp:upg/<src>-<tgt>-<cluster> \
  --title "upg: <cluster> <src>-><tgt> - cluster upgrade" \
  --body-file "${PR_BODY_FILE}"
rm -f "${PR_BODY_FILE}"
```
Note: resolve `<repo>` from `git remote get-url origin` (parse the repository name from the URL).

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
- Concurrency guard (Mode B): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
- Worker brief format: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`
- Continuation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
- Disk fallback protocol: `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`
- Instance lifecycle: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md`
- Odoo testing: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`
