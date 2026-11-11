# upg-phase-detail (P4 to P7) - adapt, review, install, PR

**Contents:** P4 - Adapt dispatch briefs - P4b - Code-review loop - P5 - Install + test gate format - P5.7 - i18n reconcile - Commit consolidation (P6/P7 capability) - P7 - Final review, then PR creation command - Cluster upgrade - Cross-references - Checkpoint / resume. Symbols, artifact paths and phases P0 to P3: `upg-phase-detail.md` (the `Symbols` and `Artifact paths` sections there apply here).

---

## P4 - Adapt dispatch briefs

Decisions (verdict handling, brief contents, no version bump, migrations deletion): the SKILL.md pipeline bullet P4. Procedure detail:
- Child worktree per module when `n >= 2` modules need a P4 dispatch; a single module dispatches directly into the integration worktree (§ Child worktree per module). Never dispatch a raw `odoo-coder` or `odoo-frontend-coder`.
- DELETE-absorbed / OBSOLETE: the brief's block "If ACTION=DELETE-absorbed or ACTION=OBSOLETE" (sweep, git-ops removal in the child worktree, dependers' `depends` cleanup); the commit message follows `SKILL.md` § Git / PR conventions.
- Other verdicts: the brief's block "If ACTION=KEEP/REWRITE(api)/REWRITE(model)/MERGE/SPLIT" (steps 0 to 5). `auto_install`/`application` change only when a manifest-comment breadcrumb directs; never auto-detect a "bridge".
- The adapt fields (`INTENT` from `absorption/<module>.md`, `SOURCE TESTS`, `BROKEN TEST-SYMBOLS`, `RUN_ID`) let the node's test leg adapt the module's own tests after the code (template: § odoo-coding dispatch brief).
- Converge each child worktree back to integration serially; remove the child.

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
SHARE_DIR: <the SAME literal resolved at P0 intake, per `upg-phase-detail.md` § Artifact paths - substitute it>
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
  sourced from `module_inspect(name='<module>', method='summary', odoo_version='<source_version>')`
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
  0b. DUE VERSION-ANCHORED DEFERRED WORK (DUE / DEFERRED / UNANCHORED defined in `upg-phase-detail.md` § P2): for every item in this module's absorption/<module>.md
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
  4. Manifest `version` and `migrations/` per `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0 and § Convention 1 (short form kept, a series prefix converted and never bumped, `migrations/` deleted, no migration script); remedy + form: upg-classification-table.md § Manifest breaks, the Rule A row.
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

Decisions (scope, cap 3, BLOCKED, fix loop, no inline review, gate to P5): the SKILL.md pipeline bullet P4b. `TARGET: worktree:<path>/upg-integration`, module-scoped; DELETE-absorbed / OBSOLETE modules have no adapt diff and are skipped. MED/LOW are recorded for the P7 review and do not block; the final dep-order review stays at P7.

**P4b acceptance hand-off (consumption clause).** Each dispatched `odoo-code-review`'s
Continuation Contract MAY carry a `next: odoo-acceptance` entry - its Phase A.5 emits this
whenever a module's `render_check_set` reaches beyond that module (dependents bind a changed
symbol). Do NOT act on it per module here; ONE cluster-wide dispatch at P5.8 covers it.

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

The fix dispatch to `odoo-coding` carries the `AUTONOMOUS FIX` sentinel plus the findings; a BLOCKED escalation names the module, the finding and what was tried.

---

## P5 - Install + test gate format

Decisions (levels, `GATE_ROLE: node-verify`, demo shape, acceptance): the SKILL.md pipeline bullets P5, P5.7, P5.8. Procedure detail:
- Install bottom-up one dependency level at a time (leaves first); record per-level green in `checkpoint.json` (status `installed`) and `install-test.md`. The P4b review MUST cover ACL / `.sudo()` for every create/write/compute override on a widely-used core model. Cross-ref `references/runbot-parity-checklist.md`.
- This is an AUTOMATION-TEST build: demo shape from `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-build-facts.md` § Demo data by build PURPOSE, never overridden for this gate; request no `demo` for it. The framework-validation classes the target series ships run here (§ Framework-validation test classes of that file): the `base` view-arch check (every always-invisible view field needs an explanatory XML comment) and the `hr` self-access check (custom `hr.employee` fields need `groups='hr.group_hr_user'`) run in the UNTAGGED suite; name them only in a tag-scoped run elsewhere, resolving each class name for the target series first.
- Flip gates (a module whose `installable` flipped) and the red-level debugger routing: the paragraphs after Step 3 below. Instance release: the flip-gate paragraph.
- **P5.8 brief.** Invoke `odoo-acceptance` (Skill tool) ONCE for the whole cluster, never per module. Compute the verify scope with `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (do NOT re-derive the reverse closure; it comes from `graph.md`); `changed_set` = every surviving module in `plan.md`; fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton: `INPUTS` = the changed set, `scope_hint` = `graph.md` + `absorption/*.md`, `odoo_version` = the target; `INSTANCE_HANDLE: none provisioned`, NEVER the P5 test handle; `ACCEPTANCE` is the module behaviour in `absorption/<module>.md` and any P2b design doc's section 9, NEVER a pre-built oracle; do not hand it the implementation. The skip proof (true leaf) is recorded explicitly in `install-test.md`, never silently. Present the verdict with the P6 sign-off; the artifact `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` is referenced from `install-test.md`.

Step 1 - create instance (once):
```
operation: create
series: <target_version>
demo: <the series default: the automation-test row of § Demo data by build PURPOSE - this database hosts every level's test run, which runs the series default; never `on` where demo defaults off>
SHARE_DIR: <the SAME literal resolved at P0 intake, per `upg-phase-detail.md` § Artifact paths - substitute it>
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
alongside the level result. A flipped module is scanned by the target's FULL test suite AND loads its own `demo/` data for the first time, hence two builds; where the level gate runs demo-less, Gate 7b carries the demo half. You are the run-level owner of each flip-gate instance
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once its verdict is recorded, call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with its `lease_token` and `run_id`. Keep the
Step 1 instance until the last level is green and the flip-gate verdicts are recorded, then release it the same way; `lease_park` instead only when a named later step still needs the database. Never release between levels.

After each level: write level result to `install-test.md` and update `checkpoint.json`
(set `installed` for each module in the level that passed). On FAILURE in a level:
dispatch `odoo-backend-debugger` or `odoo-ui-debugger` with the traceback + module source, plus
`ISOLATE_DIR:` (the SAME literal resolved at P0 intake, per `upg-phase-detail.md` § Artifact paths) and
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

Decision, `HAND_ON` and escapes: the SKILL.md pipeline bullet P5.7. Every surviving module (KEEP / REWRITE(api) / REWRITE(model) / MERGE / SPLIT / RECONCILE) runs it; a content diff is NOT the gate. Never blind-regenerate: load the existing `.po` into a fresh instance before re-export, then diff-review. Escapes are enumerated in `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` § Escape hatches and RECORDED in `install-test.md`; DELETE-absorbed and OBSOLETE modules skip via E1.

Dispatch:
```
SKILL: odoo-i18n
INSTANCE: SELF_PROVISION - odoo-i18n builds its own export instance (i18n caller obligation 5;
          `${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` KT4). Never inherit the
          P5 instance
MODULES: <cluster adapted modules>
TARGET_VERSION: <target_version>
MODE: reconcile (non-destructive)
WORKTREE_PATH: <the P4 integration worktree - .po/.pot are git-tracked>
SHARE_DIR: <the SAME literal resolved at P0 intake, per `upg-phase-detail.md` § Artifact paths - substitute it>
ISOLATE_DIR: <the SAME literal resolved at P0 intake - substitute it, and do NOT re-resolve or
  improvise one from a worktree cwd>
TARGET LANGUAGES: <explicit list when this run has one, else omit the field entirely>
RETURN: the result; present it at the P6 sign-off
STEPS (detail owned by odoo-i18n):
  1. fresh instance with en_US + each existing <lang>.po loaded, then re-export each <lang>.po
  2. git-ops diff-review each re-exported <lang>.po against its committed version; adjudicate every
     removed/changed msgid per `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` (its buckets,
     the ARTEFACT test BEFORE ruling WRONG) - preserve every existing msgstr except an adjudicated-CORRECT loss
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

Order, the two-class gate (a)(b)(c) and the push rule: the SKILL.md pipeline bullet P7.

**Pre-PR checklist.** Run the Runbot parity gates
(${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md) PLUS
these passes before opening the PR, each cross-referencing its owning snippet:
- Convention-compliance: manifest version-form is the short form with no series prefix and no bump
  (references/upg-classification-table.md § Manifest breaks, the Rule A row) and always-invisible
  view fields carry an explanatory XML comment - per ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md.
- Perf-lens: no per-record `mapped()` aggregate over a high-volume model (`hr.attendance`,
  `stock.move`, `account.move.line`, `account.analytic.line`) in a stored compute - use a grouped
  `_read_group`.
- i18n: P5.7 ran for every surviving module, or each skip is a RECORDED enumerated escape
  (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` § Escape hatches) - never a silent
  content-diff skip.

**Final dep-order review (BEFORE the push and the PR).**
Delegate the review of the integration worktree with the brief below, fix every CRITICAL/HIGH
finding on `<path>/upg-integration` (dispatch `odoo-coding` at the module's ADAPT tier, the SAME
loop as the SKILL.md pipeline bullet P4b), and review again until none remains; MED/LOW are recorded on the module rows
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

---

## Checkpoint / resume

The pipeline writes a progress ledger at `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
after each module completes a phase. Schema:

```json
{
  "<module_name>": "pending | absorbed | designed | adapted | reviewed | installed | done"
}
```

Status progression:
- `pending` - initial state for all modules at P0.
- `absorbed` - P2 comparison complete, verdict recorded in `absorption/<module>.md`.
- `designed` - P2b design doc received (only for modules routed to design).
- `adapted` - P4 code changes committed and merged to integration worktree.
- `reviewed` - P4b code-review loop returned no CRITICAL/HIGH for the module.
- `installed` - module's dependency level passed P5 install + test green.
- `done` - module fully processed (installed green + verified).

Resume behavior (per-phase skip rules):
- P2 skips modules with status in {absorbed, designed, adapted, reviewed, installed, done}.
- P4 skips modules with status in {adapted, reviewed, installed, done}.
- P4b skips modules with status in {reviewed, installed, done}.
- P5 skips modules at the dependency-level granularity with status in {installed, done}.
On restart, read `checkpoint.json` and resume from the first module that has not yet reached the
target phase's skip-threshold. P5 records green per level in the ledger.
