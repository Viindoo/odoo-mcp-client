# Plan schema and run rules (writes-files Approach)

**SSOT owned by `odoo-planning`** (authored by its `odoo-planner` agent, or filled by the main
agent from the default tail for a one-node change).

Load this when the approved Approach has `output_mode = writes-files`. The plan has three blocks
and a run header; the main agent runs it by § Running the plan. `nodes` and `edges` are the ONLY
ordering statement a plan makes: no field, header, annotation or grouping construct batches nodes
together.

**Run header** (above Block 1): `odoo_version: <concrete series>`; optional
`osm_profile: <name|none>`, `grounded: osm | hybrid | local-source | ungrounded`. Resolve
`odoo_version` by the rungs of `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`,
never a silent default.

## Block 1 - Node list

The plan's unit is the **node**: one piece of work with one owner. A node is NOT a module; one
node MAY span several modules, and one module MAY be covered by several nodes when the changes
must land separately. Each node carries:

| Field | Value |
|---|---|
| `id` | short, stable, kebab-case, unique; named for the WORK, never for a module |
| `objective` | the BUSINESS result in one line: who is helped and which job gets done; never a technical end-state ("add field X" names HOW, which belongs to the design and the coder). A tail node states the outcome it protects |
| `modules` | technical names the node touches, in dependency order (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`); omitted for a node that touches no module. On an `odoo-instance` node this IS the suite scope |
| `approach`, `approach_kind` | the skill, agent or workflow; `skill | agent | workflow | inline | integrate` |
| `agent`, `mode` | the agent the node launches and its `MODE` (e.g. `odoo-code-reviewer` `R1`), when the node launches one directly |
| `model` | `haiku`, `sonnet`, `opus`, `fable` - the launch tier of an agent node, from `build_tier_hint` for a build node, else the default tail. A skill node is invoked inline and carries none: it runs in the runner's context, and the skill's own frontmatter `model:` applies for that turn |
| `build_tier_hint` | a build node: the design's hint plus its six-item checklist (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § 5.1); the plan copies, the runner checks presence |
| `business_function`, `audience` | the unit's Domain line (`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`); `audience: n/a` for a unit with no user-facing screen |
| `when` | a condition the runner evaluates with a tool before launching (§ Default tail); absent = always |
| `depends_on` | node ids; the only ordering statement |
| `files_in_scope` | file globs the node writes; two nodes that may run in parallel must have DISJOINT sets, else they are ordered by `depends_on` |
| `inputs` | `objective`, `acceptance` (verbatim, with their SRS or design pointer), `survey` (`none` when none), optional `recon_findings`, `needs_worktree` |

**A node's module set is closed under "same landing moment":** two modules belong in ONE node
when no other node depends on one without the other, neither needs independent revert, and
neither needs deeper reasoning than the other. Any of the three fails -> two nodes ordered by
`depends_on`.

For a multi-repo delivery, one Repo Capability Card per repo (`repos[]` below).

## Block 2 - Dependency graph

`nodes` + `edges` (`type`: `technical | business-logic | data-flow`, with a `reason`), a
`topological_order`, a `critical_path`, `cycles` (`[]` for a valid DAG). Edges you MUST emit: a
module-dependency edge whenever node Y touches a module that `depends` on a module node X touches
(auto-inferred per `odoo-module-graph.md`); a verification edge from every `odoo-instance` node to
each node it proves; the tail edges of § Default tail.

Render Block 2 as a fenced ```text ASCII graph (never mermaid; only `-`, `|`, `+`, `>`, `[`, `]`):
one box per node with `[repo: <repo>] [agent: <agent> <mode> @ <model>]` or `[skill: <skill>]`,
each module `(NEW)` or `(existing)` (evaluated once, the same tag everywhere), a `depends-on:` line
and a `when:` line, listed in topological order, then a flat edge list (`X --> Y` = Y depends on X).
Template:

````
## Block 2 - Dependency graph

```text
  [billing-core] [repo: fleet-addons] [agent: odoo-coder @ sonnet]
      modules: fleet_billing (NEW)
      depends-on: (none)

  [billing-accounting-bridge] [repo: fleet-addons] [agent: odoo-coder @ haiku]
      modules: fleet_billing_account (NEW), fleet_billing (NEW)
      depends-on: billing-core

  [verify] [repo: fleet-addons] [skill: odoo-instance]
      modules: fleet_billing, fleet_billing_account
      depends-on: billing-accounting-bridge

  [review-r1] [repo: fleet-addons] [agent: odoo-code-reviewer R1 @ haiku]
      depends-on: verify
  [review-r2] [repo: fleet-addons] [agent: odoo-code-reviewer R2 @ sonnet]
      depends-on: review-r1
  [acceptance] [repo: fleet-addons] [agent: odoo-qa-tester A1A2 @ haiku]
      depends-on: verify
      when: the diff touches a view, menu, report, controller, JS file, or a state change of a model with a workflow
  [fix-round] [repo: fleet-addons] [inline: merge findings, SendMessage the node's coder]
      depends-on: review-r2, acceptance
  [i18n] [repo: fleet-addons] [agent: odoo-translator @ sonnet]
      depends-on: fix-round
      when: the .pot exported on the stable tip has a msgid the committed .pot lacks
  [migration] [repo: fleet-addons] [skill: odoo-data-migration]
      depends-on: i18n
      when: a changed module was installable before this change, the change alters data existing databases hold, and a fresh install of it passed
  [docs-module] [repo: fleet-addons] [skill: odoo-doc-illustration]
      depends-on: i18n
      when: the change is user-visible and a changed module ships doc/ or static/description/, or the user asked for module docs
  [integrate] [repo: fleet-addons] [skill: git-toolkit:git-ops]
      depends-on: docs-module, migration
  [monitor] [repo: fleet-addons] [skill: odoo-pr-monitoring]
      depends-on: integrate
  [merge] [repo: fleet-addons] [skill: odoo-pr-monitoring]   human gate, always
      depends-on: monitor

  Edges:
    billing-core --> billing-accounting-bridge
    billing-accounting-bridge --> verify
    verify --> review-r1
    review-r1 --> review-r2
    verify --> acceptance
    review-r2 --> fix-round
    acceptance --> fix-round
    fix-round --> i18n
    i18n --> docs-module
    i18n --> migration
    docs-module --> integrate
    migration --> integrate
    integrate --> monitor
    monitor --> merge
```
````

A second repo adds a sibling tail in the same order, every node tagged `[repo: <repo-2>]`, and
its own `integrate`: N repos = N PRs.

A skill node that lands its own PR (`odoo-doc-site`) is the exception. Its repo is the docs repo,
tagged on the node, and only `monitor` and `merge` on that PR follow it: that repo has no
`integrate`, no `run-integration` branch and no verification node, and Loop step 4's cherry-pick
does not apply to the node. The docs repo's `repos[]` entry: `id` = the site row's `key`, `base` =
the series branch; `odoo-doc-site` creates the worktree itself.

**Design is an INPUT to this plan, never a node of it.** No node's `approach` is
`odoo-solution-design` and no node launches `odoo-solution-architect`; the design is read by
pointer and approved before the plan exists. A design is optional at every complexity level
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule); its absence
is carried as `none`, never a node.

**Data source.** The node graph derives from the design's `dag_layers`
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md`) plus the Block 3 assignment;
`(NEW)` vs `(existing)` from `odoo-module-graph.md`. Every repo that has a coding node carries at least ONE
`odoo-instance` node on `integrate`'s path whose `modules` cover every module a coding node of that
repo names (never a PR on a red suite); its `modules` grow monotonically down the graph
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`). A cross-module acceptance criterion
is owned by the verification node whose `modules` cover every module it spans, named on that
node's Block 3 line.

## Block 3 - Assignment

One line per node: `node -> agent <mode> @ <model> | skill | workflow (effort S/M/L/XL)`, the
node's **acceptance criteria** (business-observable outcomes that make the `objective` true,
each with its SRS or design pointer - never "field X exists") and the repo's **verify command**.
For a criterion that spans several modules, name on the owning verification node which
assertions cross a module boundary. A workflow is ONE node (`files_in_scope` = its `output_dir/`);
its phases stay in the `.workflow.yaml`. The plan for a single-node change is the node plus the
default tail.

## Default tail

The planner copies this tail after the last verification node and adapts it with a reason
written in the plan (an SRS with a language criterion puts `i18n` before `acceptance`). A position the run does not have is skipped in
place; the rest keep their order.

```yaml
- id: review-r1
  approach: odoo-code-reviewer
  approach_kind: agent
  agent: odoo-code-reviewer
  mode: R1
  model: haiku
  depends_on: [<last verify>]
- id: review-r2
  approach: odoo-code-reviewer
  approach_kind: agent
  agent: odoo-code-reviewer
  mode: R2
  model: sonnet
  depends_on: [review-r1]
  # R3 (mode R3, model opus) is launched in the same message as R2 and R2 waits for its report
  # when the unit's business_function is on the specialist list of business-taxonomy.md or
  # recon.md meets the thresholds of concurrency-guard.md section 5.2
- id: acceptance
  approach: odoo-qa-tester
  approach_kind: agent
  agent: odoo-qa-tester
  mode: A1A2
  model: haiku
  # model sonnet when a Given needs a fixture built (concurrency-guard.md, Model-tier selection)
  depends_on: [<last verify>]
  when: the diff touches a view, menu, report, controller, JS file, or a state change of a model with a workflow
  # A4 (mode A4, model sonnet) follows when audience is not n/a and the diff adds or changes a screen
- id: fix-round
  approach_kind: inline
  approach: >-
    merge the findings of review-r2 and acceptance, deduplicated by symbol and line and
    classified per acceptance-oracle-contract.md; SendMessage the node's coder once; then
    SendMessage review-r2 (FIX_DIFF) and acceptance (the failed and the touched scenarios);
    at most 3 rounds; two consecutive rounds with a new HIGH in the same area stop the run
    and return to the design
  depends_on: [review-r2, acceptance]
- id: i18n
  approach: odoo-translator
  approach_kind: agent
  agent: odoo-translator   # one launch per language of the deployment catalog
  model: sonnet
  depends_on: [fix-round]
  when: instance_i18n_export on the stable tip yields a msgid the committed .pot lacks or changed
- id: migration   # decided last: the loops are over and a fresh install is proven
  approach: odoo-data-migration   # owns the module's one version bump; never a node of a code upgrade
  approach_kind: skill
  depends_on: [i18n]
  when: a changed module was installable before this change, the change alters data existing databases hold, and a fresh install of it passed
- id: docs-module
  approach: odoo-doc-illustration   # invoked inline with CHANGE = the change file (Loop step 3); never the bare odoo-doc-writer
  approach_kind: skill
  depends_on: [i18n]
  when: the change is user-visible and a changed module ships doc/ or static/description/, or the user asked for module docs
- id: docs-site   # tagged with the docs repo; lands its own PR; only monitor-site and merge-site follow it
  approach: odoo-doc-site   # invoked inline with FROM CHANGE = the change file (Loop step 3)
  approach_kind: skill
  depends_on: [docs-module]
  when: a docs site is declared for the product and the change is user-visible, or the user asked for site docs
- id: integrate
  approach: git-toolkit:git-ops   # pre-PR lint over the aggregate diff, squash, push, ONE PR per repo
  approach_kind: integrate
  depends_on: [docs-module, migration]
- id: monitor
  approach: odoo-pr-monitoring
  approach_kind: skill
  depends_on: [integrate]
- id: merge
  approach: odoo-pr-monitoring   # the human gate, always
  approach_kind: skill
  depends_on: [monitor]
- id: monitor-site   # tagged with the docs repo; watches the PR odoo-doc-site opened
  approach: odoo-pr-monitoring
  approach_kind: skill
  depends_on: [docs-site]
- id: merge-site   # the human gate, always; the docs PR never merges before the code it documents
  approach: odoo-pr-monitoring
  approach_kind: skill
  depends_on: [monitor-site, merge]   # merge only where the plan has a code repo's merge
```

**The documentation target is decided once, from facts, by the Documentation routing rule of
`odoo-intake`** (module, site, both or none). The plan gate shows ONE line, `Docs: <module | site |
both | none> - <the facts that decided it>`, so the user can change it; `none` drops `docs-module`
and `docs-site` with the user's reason written in the plan. A docs-only request (target `both`)
is a plan with the nodes `docs-module` then `docs-site`, the code repo's `integrate`, `monitor`
and `merge`, the docs repo's `monitor-site` and `merge-site`, and no build or verification node:
no coding node exists, so there is no module set for `odoo-instance` to cover.

## Running the plan (the main agent, inline)

**Inputs.** The approved plan; `SHARE_DIR` and `ISOLATE_DIR` captured once; the run file
`<ISOLATE_DIR>/run-<id>.json` intake Phase P wrote; each repo's Capability Card.

**Invariants, checked before the first launch.** Two nodes with no path between them share no
module and no file glob; `depends_on` has no cycle; every node that can change code precedes
`integrate`; `merge` follows `integrate` (`merge-site` follows `docs-site` and, where the plan has one, `merge`) and is a human gate; every repo that has a coding node has a verification node
on `integrate`'s path covering its coding nodes' modules (a docs repo and a docs-only plan have none). A failed invariant is a plan error:
return it to `odoo-planning` with the finding; never patch the plan yourself.

**Run start.** Fork ONE `run-integration` branch per repo that has an `integrate` node from its base through `git-ops`
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`), and before creating this run's own
`<ISOLATE_DIR>/integration/<slug>/`, reap abandoned ones - age alone never decides, the
correlating run's own top-level status must prove terminal
(`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` § 3.6):

```bash
command -v jq >/dev/null 2>&1 && find <ISOLATE_DIR>/integration/ -mindepth 1 -maxdepth 1 -type d -mmin +1440 -print0 |
  while IFS= read -r -d '' d; do
    case "$(jq -r '.status // empty' "<ISOLATE_DIR>/run-$(basename "$d").json" 2>/dev/null)" in
      DONE|BLOCKED|NEEDS_CONTEXT) rm -rf "$d" ;;   # proven terminal
      *) : ;;                                       # absent, unreadable or NEEDS_NEXT: never delete
    esac
  done
```

**Loop.** A node is ready when every `depends_on` is `DONE` or `SKIPPED`.
1. Evaluate `when:` with a tool (a bounded `git-ops` diff read, `instance_i18n_export`, the SRS
   file) and write the evidence to the worklog; false -> `SKIPPED`.
2. A node that writes source gets a worktree from `git-toolkit:git-ops` under `worktree_root`
   (`project_dir` axis `worktree`, `name` = the node id) starting at the repo's `run-integration`
   branch; `inputs.worktree_path` records it.
3. Launch the node's agent at its `model` with the brief of § Node brief (every launch in one
   message when several nodes are ready and their file sets are disjoint; the in-flight weight
   stays inside `concurrency-guard.md` Mode B; the reason letter of launch economics goes to the
   worklog). A skill node is invoked inline; a workflow node through `workflow-chaining`.
   Before a docs node, compose the change's feature list from the SRS acceptance criteria and the
   node objectives - one line per added, changed or removed user-visible feature, with its UI
   label - write it to `<ISOLATE_DIR>/docs/change-<slug>.md` and pass that path as `CHANGE`
   (`docs-module`) or `FROM CHANGE` (`docs-site`).
4. On return, record `status`, `produced`, the commit range and the evidence paths in the run
   file; cherry-pick a source node's range onto `run-integration` through `git-ops`
   (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`; a node that lands its own PR is
   exempt); a continuation `next[]` entry
   with confidence >= 0.5 becomes a dynamic node, below 0.5 a suggestion in the summary.
5. A worker that returns `BLOCKED` or `NEEDS_CONTEXT` without a `gate:` is launched once more one
   tier higher with its own artifacts as `PRIOR_FINDINGS`; a second failure stops the run at that
   node and asks the human. A resumed round (a fix, a verification of a fix) goes to the SAME
   agent with `SendMessage`, never to a new launch.
6. **Verdict currency.** Before `integrate`, compare the `run-integration` tip the last green
   verification recorded with the live tip (a bounded `git-ops` read); they differ -> re-run that
   verification node on the new tip. A `.po`, `.pot` or `migration` change alone does not change behaviour and
   does not trigger it.
7. **Human gates** under the approved plan are exactly `merge` and any other outward or
   irreversible operation (send, publish, push, delete), each a text question. At a gate: write
   the state to the run file, ask (`approve / skip / cancel`), end the turn; on the reply read the
   run file and continue. Nothing under the plan enters Plan Mode, and a node's skill presents no
   plan of its own (it writes its plan into its report). A finished node is never a reason to stop.
8. The run file is the truth for resuming after a broken session: a node left `RUNNING` is
   reconciled against the worktree and the worklog before any re-launch. Workers write detail to
   `ISOLATE_DIR` and return a short report (status, paths, numbers).
9. When the session runs at an expensive tier, the whole loop may be handed to one
   general-purpose `sonnet` agent with the plan and this section; it reports back at each gate
   (launch economics reason e).

**`integrate`.** When every non-tail node of the repo is `DONE` or `SKIPPED` and the verdict is
current: run the pre-PR lint-class gate over the aggregate diff (the module set of
`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`, through `odoo-instance`), then invoke
`git-toolkit:git-ops` to squash `run-integration`, push it and open ONE PR against the principal
branch (update it when a resumed run finds one open). `monitor` and `merge` are plan nodes, never
materialized twice.

## Node brief

A build node gets the fields of
`odoo-coder` § You receive, filled from the plan: `NODE`, `REQUEST` (= `inputs.objective`, then
"Done when:" and `inputs.acceptance` verbatim), `MODULES` (`name @ path`, dependency order),
`WORKTREE_PATH`, `ODOO VERSION`, `PROFILE`, `SHARE_DIR`, `ISOLATE_DIR`, `RUN_ID`, `WORKLOG`,
`DESIGN_DOC`, `MASTER_DESIGN_DOC`, `SRS`, `RECON`, `DOMAIN`, `SELF_PROVISION: worktree-addons` or
an `INSTANCE_HANDLE` with `ADDONS_PATH`, `SURVEY` (`none` when none), `CONSTRAINTS` (the Block 3
cross-module assertions). Return: the commit range `<base>..<head>` on the node's branch. A tail
node gets the brief of its skill's `references/` file (`odoo-code-review`, `odoo-acceptance`,
`odoo-i18n`, `odoo-doc-illustration`) with `WORKTREE_PATH: <repo>/run-integration` and
`SELF_PROVISION: worktree-addons` where the agent builds its own instance (i18n always: an export
build needs demo data and the target languages, which a test lease cannot provide). `migration`
(`odoo-data-migration`) gets `WORKTREE_PATH: <repo>/run-integration`, `ODOO VERSION`, `DESIGN_DOC` and the changed
modules that satisfy its `when:`. `odoo-doc-site`
gets `CODE_WORKTREE: <code repo>/run-integration`, `RUN_ID` and `FROM CHANGE` instead of
`WORKTREE_PATH`: the docs repo has no run-integration tree. A verification
node: `OPERATION: run-tests`, `SERIES`, `MODULES` (= `node.modules`), `MODE: fresh`,
`PERSIST: ephemeral`, `SELF_PROVISION: worktree-addons`, `WORKTREE_PATH`, `SHARE_DIR`,
`ISOLATE_DIR`, `WORKLOG`, `GATE_ROLE: node-verify`, `TEST_TAGS` per
`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`.

## Run file (`<ISOLATE_DIR>/run-<id>.json`, `schema_version: run/2.0`)

Written once by intake Phase P, then only by the runner. `run_id`, `intent`, `autonomy`
(`auto | step | plan`), `status`, `cursor`, `budget`, `repos[]` (one Capability Card per repo:
`id` origin-derived, `base`, `verify`, `commit`, `confidential`, `worktree_root` from
`project_dir` axis `worktree`; the docs repo's entry has no `worktree_root`), `nodes[]` (the Block 1 fields plus `status`
`PENDING|READY|RUNNING|DONE|FAILED|SKIPPED|BLOCKED|NEEDS_CONTEXT`, `produced`, `contract` = the last
continuation block), `dynamic_nodes[]`, `gate_log[]`, `completion`. `repo: null` only for a node
that writes into no repository and gates no delivery; every source-writing, verification,
`integrate` and tail node names a declared `repos[].id`. Resume: skip `DONE` nodes, continue at
the first ready node in topological order.

## Rejection flow

A `refine` at the plan gate loops back to the planner, never to execution: adjust the nodes
(objective, acceptance, scope, files, assignment, effort) and re-present in Plan Mode. `cancel`
stops. Never launch a writes-files node off a rejected plan.
