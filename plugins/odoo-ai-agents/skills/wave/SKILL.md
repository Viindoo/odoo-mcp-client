---
name: wave
description: >
  Orchestrate a multi-work-item (multi-WI) change as a git wave without touching the
  principal branch: create one integration branch, spin up one isolated worktree per WI,
  dispatch a leaf subagent into each worktree, cherry-pick results back onto integration,
  run an end-of-wave Opus review plus odoo-code-review inline, produce one PR, verify squash
  tree-identity, then stop and wait for human-confirm before merging.
  Fire this skill when asked to: "do this as a wave", "parallelize these changes",
  "multi-WI PR with review and squash", "land N changes safely without touching main",
  or any multi-file change that needs parallel workers + safe git integration.
  Do NOT use for a single-file change (use odoo-coding), requirement scoping (use odoo-brl),
  or in-context skill chaining (use workflow-chaining).
  Never auto-merge - HUMAN-CONFIRM is the terminal gate
model: opus
---

## Persona

Release-train conductor. This skill owns the git topology and subagent lifecycle for a
multi-WI change. It makes zero domain decisions (code style, business logic, architecture
choices all belong to the leaf subagents). Its only job is to get N independent work items
from "idea" to "one green PR ready for human merge" safely, without ever touching the
principal branch.

## Out of Scope

- Single-file or single-WI change -> use `odoo-coding` directly
- Requirement scoping, BRL classification -> use `odoo-brl`
- In-context NL skill chaining without git branches -> use `workflow-chaining`
- Auto-merge -> NEVER. Human-confirm is the terminal gate, non-negotiable

## Hard rules

> These rules are load-bearing safety contracts. Deleting or softening any one of them
> is a breaking change and must be caught by `tests/test_wave_hardrules.py`.

1. **Principal-branch-lock** - NEVER run `git checkout`, `git switch`, `git commit`,
   `git rebase`, `git merge`, `git pull`, or `git reset --hard` on the principal branch
   (the branch active at skill invocation). All WI branches and the integration branch
   live in separate worktrees. Read-only ops (`git log`, `git diff`, `git status`) on
   the principal are allowed.

2. **Git-authority stays with the orchestrator** - This skill (wave) runs in the
   orchestrating context that holds git authority for the run. It dispatches WI subagents
   that are themselves the specialists for their scope. Concurrency: model-weighted budget
   (BUDGET=8) per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) -
   up to 8 haiku, 4 sonnet, 2 opus, or exactly 1 fable WI subagent in flight at once;
   never exceed the budget (OOM guard). The cherry-pick step is NOT part of this budget -
   it is an orchestrator-side critical section serialized to one at a time (Phase 2/3),
   never pushed down to a WI worker.

3. **odoo-code-review inline-only** - The `odoo-code-review` skill auto-spawns its own
   reviewer subagent and is therefore only legal in this skill's own orchestrating context
   (not inside a WI subagent). Invoke it here in Phase 4 via the Skill tool, never inside a
   WI subagent. Findings are fixed either inline or via a brief targeted subagent.

4. **Human-confirm merge** - The skill MUST stop at Phase 6 and wait for explicit user
   confirmation before merging the integration branch. No automated merge, no auto-squash-
   and-merge, no CI-triggered merge. The skill presents the PR URL and waits.

5. **Confidentiality (public-repo - 8 banned groups)** - Artifacts and commit messages
   MUST NOT contain: CEO personal info, customer PII or contract details, internal pricing,
   competitor intelligence beyond public sources, product roadmap details, marketing-in-draft,
   OKR/targets, or internal-tooling paths. Use abstract labels (Customer-A, etc.).
   If a user prompt contains such data, acknowledge intent only - do not echo it into files.
   Full 8-group list: `reference/wave-templates.md` §Confidentiality Long-Form.

6. **Squash tree-identity gate** - Before force-with-lease, verify that the squashed commit
   produces an identical tree: `git diff --quiet <backup-ref>` must exit 0. If it exits
   non-zero the squash is aborted and reported. Full recipe: `reference/wave-templates.md`
   §Squash Tree-Identity Recipe.

7. **Disjoint file-ownership** - The Phase 0 ownership map must partition all affected
   files across WIs with no overlap. A file appearing in two WI scopes is a hard blocker;
   resolve it before creating any worktrees.

8. **Verify subagent claims** - Do not trust a subagent's self-report of success. After
   each cherry-pick, run the repo verify command from the Repo Capability Card to confirm
   the integrated state is green.

## Pre-wave gate

> **No branch is created until the user approves the wave plan.**

**Red Flags - phrases that trigger STOP + re-gate:**
- "This is a small change, just start the worktrees" -> STOP. Still produce + gate the plan.
- "Skip Phase 0, the files are obviously disjoint" -> NEVER skip the ownership audit.
- "I'll parallelize and review in the same turn" -> BANNED. Plan turn = plan only, no branches.
- "Auto-merge is fine for this one" -> Rule 4 is non-negotiable. Present the gate anyway.
- "The subagent said it passed" -> Rule 8: run the verify command yourself before continuing.

**Phase 0 gates the entire wave.** If the user says "cancel" at the plan gate, clean up and
stop. No worktree is created, no branch is cut, until the user sends a positive confirmation
("approve", "go", "yes", or equivalent).

## Phase 0 - Capability Discovery + Plan Gate

First READ any existing worklog for this run (`.odoo-ai/worklog/<run-or-slug>/*.md`, oldest-first)
per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` so the plan builds on decisions an
upstream phase already recorded.

**0.1 - Repo Capability Card** (always run first):

Discover the repo's topology and verification commands. Record:
- `base`: the principal branch name (`git rev-parse --abbrev-ref HEAD`)
- `verify`: the command that must pass after every cherry-pick (from Makefile/CI/README)
- `commit`: conventional commit format requirement (if any)
- `confidential`: public / restricted / internal

Store the card inline in the wave plan. WI subagents inherit it verbatim in their briefs.
Full template: `reference/wave-templates.md` §Repo Capability Card Template.

**0.2 - File ownership audit**:

List every file changed by the N WIs. Build `{WI -> [files]}`. Assert sets are disjoint.
If any file appears in two WI scopes, STOP and ask the user to resolve before proceeding.

**0.3 - Odoo module DAG (respect module boundaries)**:

Disjoint files alone are not enough - partition by **module**. Compute the module DAG per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`:
- Map each WI to its module(s): `{WI -> [modules]}`.
- **Auto-infer `depends_on`:** if a module owned by WI-B depends (directly or transitively)
  on a module owned by WI-A, add that edge - cherry-pick order follows the manifest graph.
- **Warn on boundary-crossing WIs:** if one WI spans multiple modules at different DAG depths,
  flag it and propose splitting along module lines. Soft gate - let the user decide.

**0.4 - Topology selection**:

Choose from the four standard patterns in `reference/wave-templates.md` §Four Topology Patterns,
using the module DAG from 0.3:
- **Independent** - disjoint files AND disjoint module sub-graphs; cherry-pick any order
- **Linear** - WI-B depends on WI-A output; cherry-pick A then B
- **Mixed** - some independent, some sequential; pick independent first
- **Diamond** - WI-B and WI-C both depend on WI-A; pick A first, then B+C parallel

**0.5 - Plan artifact** (for >=4 WIs):

Write `.odoo-ai/wave/<slug>/plan.md` using the full template from `reference/wave-templates.md`
§Plan Artifact Full Template. For 1-3 WIs, the plan lives inline in the conversation.

**0.6 - Plan gate**:

Present the plan before any branch or worktree is created:

```
## Wave Plan - <slug>
Base branch : <principal>
Integration : wave/integration-<slug>
WIs         : <N>  (model-weighted budget BUDGET=8)
Topology    : <independent | linear | mixed | diamond>
Verify cmd  : <command from Repo Capability Card>
Ownership map:
  WI-A: <file list>
  WI-B: <file list>
  ...
Module DAG (from 0.3):
  WI-A: [<modules>]            depends_on: []
  WI-B: [<modules>]            depends_on: [WI-A]   (module <m_b> depends on <m_a>)
  Warnings: <WI crossing >1 module boundary, with split suggestion - or "none">
Confidential: <public | restricted>
Scaling mode: <minimal | plan-gate | full-plan-artifact>

Approve (go / yes) | Refine | Cancel
```

Do NOT create any branch or worktree before the user approves.

## Phase 1 - Integration Branch + Worktrees

After plan approval:

1. Create the integration branch:
   `git worktree add -b wave/integration-<slug> <path>/integration <principal>`

2. Create a worktree for each WI:
   `git worktree add -b wave/wi-<slug>-<id> <path>/wi-<id> wave/integration-<slug>`
   - **Root WIs** (no `depends_on`): create up front here.
   - **Dependent WIs**: create **lazily** in Phase 2, only after their deps have been
     cherry-picked onto integration (so the worktree forks from an up-to-date integration
     that already contains the dep's code).

3. Record all worktree paths in the plan artifact (or inline for 1-3 WIs).

4. Confirm each worktree is clean with `git status --short` before dispatching.

## Phase 2 - Dispatch WI Subagents (Mode B rolling-window)

Dispatch WI subagents - one subagent launch per WI, each passing the
WI brief as its `prompt`. Scheduling is **Mode B model-weighted rolling-window**: as each worker
returns and its weight is freed, the next eligible WI (deps cherry-picked) is dispatched.
SSOT for weights and budget: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B).
Full pseudocode: `reference/wave-templates.md` §Mode B Dispatch Loop.

**CHP Tier-A wiring (follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`):**

Run the capability probe once before the first WI dispatch. When Tier-A is available (all four
probe conditions positive):

- Assign each WI worker a stable `name` at spawn time - use the pattern `wi-<slug>-<id>-coder`.
- Capture the returned `agentId` for each WI worker immediately after launch.
- Record `name` + `agentId` in the plan artifact (keyed by WI id) so the plan becomes the
  agentId registry for Phase 4.

When the probe is negative (any condition fails), dispatch exactly as below - Tier C (fresh
subagent per WI) is the always-correct baseline. [chp-tier-c-fallback]

**Key invariants of the loop:**
- A WI worker runs in its OWN isolated worktree. It writes + **commits + returns its SHA(s)**.
  It does **NOT** cherry-pick. Cherry-pick is forbidden to WI workers (Hard Rules 1 + 2).
- **Cherry-pick is an orchestrator-side CRITICAL SECTION, serialized to one in-flight at a time**,
  run in the orchestrating context in topology/DAG order. No race on the shared integration branch.
- Dependent-gating promise is `cherry_picked[dep]`, **NOT** `completed[dep]`. A dependent WI
  starts only after every dep is **cherry-picked onto integration** (not merely committed in
  its own worktree), because the dependent's worktree forks from integration.
- Dependent worktrees are created **lazily** immediately before dispatch (after `cherry_picked[dep]`
  gate passes) so they fork from an up-to-date integration.

**MANDATORY**: Make real subagent launches for each worker dispatch. Do NOT narrate dispatch in
prose instead of calling the tool.

Dispatch rule (subagent launches only - this plugin does not use the Claude Code Workflow JS tool):
fire every WI whose deps are already cherry-picked, up to the weighted budget; serialize each
cherry-pick in the orchestrating context as workers return. Never gate on a fixed-size batch; never
let a WI worker cherry-pick. Resolve each WI's model tier with the `odoo-coding` SKILL § "Assign a
model tier" table (size/scope-aware) and pass it as the subagent launch `model` - this is also the
WI's scheduling weight. A large or complex WI must NOT fall back to the leaf agent's default sonnet.

Each subagent receives a **WI brief** as its `prompt`:

```
## WI-<ID> Brief
Worktree path  : <absolute path>
Branch         : wave/wi-<slug>-<id>
Files in scope : <disjoint list>
Modules in scope        : <Odoo modules these files belong to>
Module depends-on (in-wave): <WIs whose modules this WI's modules depend on - already cherry-picked>
Upstream deps (out-of-scope): <modules this WI depends on that are NOT being changed - do not edit>
Downstream impact       : <modules that depend on this WI's modules - your change must not break them>
Task           : <precise description of what to implement>

Repo Capability Card:
  base    : <principal>
  verify  : <command>
  commit  : <convention>
  confidential: <level>

Hard rules:
  - Ground in OSM first - follow the OSM-First Grounding Contract
    (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md): verify every model/field/method/
    module/CLI/design-token claim via OSM (set_active_version + model_inspect / entity_lookup /
    find_examples / resolve_stylesheet) BEFORE writing. Never code Odoo from memory.
    If this WI involves writing or adapting tests, also ground the test surface via OSM
    before generating any test code:
      - `find_test_examples(query='<feature>', odoo_version='<version>')` - find real test
        chunks (100% test code, not production); use instead of find_examples when context is tests.
      - `test_base_classes(odoo_version='<version>')` - get the correct base class for the
        target version (TransactionCase/SavepointCase/HttpCase); note cr.commit() FORBIDDEN in
        TransactionCase (isolation is savepoint rollback, not manual commit).
      - `tests_covering(model='<model>', odoo_version='<version>')` - check existing test
        coverage for a model/field/method before writing new tests; only write what is missing.
      - `js_test_inspect(module='<module>', odoo_version='<version>')` - for frontend JS test
        WIs: identify the framework in use (QUnit v16-/v17, Hoot v18+) and mock_models
        convention before writing any JS test code; never assume framework from memory.
      - `test_coverage_audit(module='<module>', odoo_version='<version>')` - audit coverage
        gaps across a module before proposing a test plan.
  - Worker brief (full text: ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md): you ARE the
    specialist - write/review the code yourself, grounding every Odoo claim with the OSM MCP
    tools (an MCP tool call is never a spawn, so it is always allowed); follow the
    odoo-coder / odoo-frontend-coder / odoo-code-reviewer conventions. Do NOT git
    branch/cherry-pick/merge/push; stay in your assigned worktree. Only
    Read/Grep/Glob/Edit/Write/Bash.
  - **cd-on-resume (HARD RULE - Tier-A):** On resume via SendMessage, immediately `cd` to the
    Worktree path listed above before running any Bash command. Shell cwd is NOT guaranteed to be
    restored across a SendMessage-resume; the explicit `cd` makes Tier-A safe regardless of
    runtime behavior. Apply this on every resume, not only the first.
  - Only edit files listed in your "Files in scope". Do not touch files owned by other WIs.
  - Commit your work to branch wave/wi-<slug>-<id> using the repo commit convention.
  - Run the verify command and confirm it passes before declaring done. If verify involves
    `odoo-bin` (install/upgrade/test), resolve the target version's real CLI via OSM
    `cli_help` first and follow ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md
    and ODOO-TESTING.md - never assume one version's flags apply to another.
  - Append significant decisions to .odoo-ai/worklog/<slug>/<id>-wi.md per
    ${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md (one file per worker - no shared-file race).
  - Return your result using EXACTLY this template (no prose substitution):

## WI-<ID> Result
Status:  DONE | FAILED
SHA:     <commit sha(s) on wave/wi-<slug>-<id> - REQUIRED on DONE; the orchestrator
         cherry-picks these onto integration. A DONE with no SHA is a failed contract.>
Verify:  PASS | FAIL - <command + result>
Changes: <1-3 bullets: file + what changed>

Confidentiality: <8-group restriction if restricted; otherwise "public repo - standard caution">

Acceptance criteria:
  <specific testable criteria for this WI>
```

In Mode B there is no whole-batch barrier: each worker's cherry-pick is serialized inline in the
orchestrating context as that worker returns, and a dependent WI is dispatched as soon as its deps
are cherry-picked. If a subagent exceeds 15 minutes without output, check its status; do not assume success.

## Skill-Delegation Matrix

| Task | WI worker does this | WI worker MUST NOT |
|---|---|---|
| Backend Python/XML | Write directly, grounded via OSM (`model_inspect` / `find_examples` / `validate_*`), following `odoo-coder` conventions | Re-dispatch the `odoo-coding` bundle - you ARE the specialist |
| Frontend JS/OWL/SCSS | Write directly, grounded via OSM (`find_examples` / `resolve_stylesheet`), following `odoo-frontend-coder` conventions | Re-dispatch the `odoo-coding` bundle - you ARE the specialist |
| Test writing (Python) | Ground via `test_base_classes` (base class + cr.commit() contract) + `tests_covering` (coverage gap) + `find_test_examples` (real test patterns) BEFORE writing; only write uncovered paths | Assume base class or cr.commit() legality from memory; re-implement tests that already exist |
| Test writing (JS) | Ground via `js_test_inspect` (framework: QUnit v16-/v17, Hoot v18+) + `find_test_examples(query='<feature>', kind='js', odoo_version='<version>')` BEFORE writing any JS test | Write Hoot syntax for a QUnit module (or vice versa); assume framework from version heuristic |
| Review of own output | Self-review inline against `odoo-code-reviewer` conventions | Re-dispatch `odoo-code-review` from a worktree |
| Read-only lookup | Invoke a non-spawning skill via the Skill tool (`odoo-feature-check`, `odoo-override-finding`) | - |

**Specialist rule**: a WI worker IS the specialist for its scope - it writes and reviews
directly, grounded in OSM, following the `odoo-coder` / `odoo-frontend-coder` /
`odoo-code-reviewer` conventions, rather than re-dispatching the spawner bundle (`odoo-coding`,
`odoo-code-review`, `odoo-ui-review`, `wave`, `odoo-intake`, `odoo-brl`,
`workflow-chaining`) that would only fan back out to the same specialist. It MAY
invoke genuinely non-spawning (leaf) skills via the Skill tool for read-only lookups.

## Phase 3 - Cherry-pick + Conflict Resolution

> This is the cherry-pick contract that Phase 2's Mode B loop applies per WI inside its
> serialized orchestrator-side critical section - one cherry-pick in flight at a time, in topology
> (module-DAG) order. Cherry-pick is NEVER pushed down to a WI worker (Hard Rules 1 + 2).

For each WI in topology order:

1. Cherry-pick onto the integration branch:
   `git cherry-pick <sha>` (from within the integration worktree)

2. Run the verify command immediately after each cherry-pick.

3. **On conflict**: dispatch a brief Sonnet resolver subagent with:
   - The conflicting diff and the two WI briefs whose files overlap
   - Worker brief (verbatim, mandatory - SSOT: ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md):
     "You ARE the specialist - resolve and verify directly, grounding any Odoo claim with the OSM
     MCP tools (an MCP tool call is never a spawn). Do NOT git branch/cherry-pick/merge/push; stay
     in your assigned worktree. Only Read/Grep/Glob/Edit/Write/Bash."
   - Also hand the OSM-First Grounding Contract
     (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md) when the conflict touches Odoo code.

4. Record the cherry-pick SHA and verify result in the plan artifact.

After all WIs are cherry-picked, run the verify command one final time on the full integration state.

## Phase 4 - End-of-Wave Review

**4.1 - End-of-wave review** (in this skill's context, not a subagent):

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and WI count N.

- **Large wave** (>~1500 changed lines OR N >= 8 WIs): escalate to a **fable** review subagent
  dispatched from the orchestrating context. fable costs ~2x opus - ALWAYS needs explicit confirmation: state tier,
  cost, and one-line why; wait for user yes. If user declines or fable is unavailable, fall back
  to **opus inline review** and note the downgrade.
- **Otherwise** (common case): **opus inline review** in this context.

Review the full diff (`git diff <principal>...HEAD`) for:
- Plan adherence, correctness, simplicity, self-containment, confidentiality
- **Coverage lens** (apply when any WI touches test files or adds behavior that should be tested):
  for each changed model/module, verify via `tests_covering(model='<model>', odoo_version='<version>')`
  that the WI did not introduce untested behavior paths, and via `test_coverage_audit(module='<module>',
  odoo_version='<version>')` that the module coverage gap did not widen after the change.
  Flag any behavior-change WI that has no corresponding test addition as a finding.

Fix findings inline or via a targeted subagent. For each finding:

- If the finding maps to a specific WI's files AND that WI worker's `agentId` is recorded in the
  plan artifact AND the Tier-A probe passed for this run: attempt a Tier-A `SendMessage`-resume of
  that WI worker (park-and-be-resumed, async) with the finding details, end your turn, and wait to
  be resumed when the worker's fix reply arrives - then re-run verify. Do NOT emit further output
  in this turn after the SendMessage; the orchestrator is parked until the worker replies. The
  resumed worker keeps its full prior context - it is the mind that wrote the code, not a cold reader.
- Otherwise (finding is cross-WI, or agentId not recorded, or probe did not pass): fall back to the
  current behavior - spawn a fresh targeted brief subagent (Tier C). Tier C is always correct.

Re-run verify after any fix regardless of which tier was used.

**4.2 - odoo-code-review inline** (invoke from the orchestrating context):

After the Opus review and fixes, invoke the `odoo-code-review` skill (via the Skill tool)
on the integration branch. Pass `TARGET: worktree:<path>/integration` (the integration worktree
created in Phase 2 step 1 - `<path>` is the same base path used in `git worktree add`) so the
skill reviews the integration tree, not the principal tree. Address its findings before Phase 5.

## Phase 5 - PR + Squash + Tree Identity

**5.1 - PR creation**:

Push the integration branch and open a PR against the principal branch.
PR title follows the repo commit convention. PR body includes: summary of all WIs,
verify command result, link to plan artifact (if >=4-WI wave).

**5.2 - Squash + tree-identity gate**:

Before squashing, run the stale-base guard:
```
git fetch origin <principal>
git merge-base --is-ancestor origin/<principal> HEAD
```
If the ancestry check fails, the principal has moved since integration was cut.
ABORT: rebase integration onto `origin/<principal>` first, re-run verify, then return here.
Skipping this guard can silently revert commits that landed on the principal after the
integration branch was created - the tree-identity check does NOT catch this.

After the guard passes:
`git tag wave-backup-<slug> HEAD`
`git reset --soft origin/<principal>`
`git commit -m "<conventional message>"`
`git diff --quiet wave-backup-<slug>` (exit 0 = trees match; exit non-zero = ABORT)

On abort: restore from backup ref, report the mismatch, do not force-push.
Full recipe with comments: `reference/wave-templates.md` §Squash Tree-Identity Recipe.

**5.3 - Force-with-lease push**:

`git push --force-with-lease origin wave/integration-<slug>`

## Phase 6 - Human-Confirm Merge + Cleanup

**Stop here. Present the PR URL and wait for explicit user confirmation.**

```
Wave complete - integration branch is ready for merge.
PR URL : <url>
Verify : <last verify result - PASS>
Squash : tree-identity confirmed (wave-backup-<slug>)

To merge: confirm here (type "merge" or "yes") or merge directly via the PR URL.
Waiting for your confirmation before proceeding.
```

**Only after explicit confirmation:**

1. Merge the PR (or note the user merged it directly via the URL).

2. Cleanup (full checklist: `reference/wave-templates.md` §Cleanup Checklist):
   - `git worktree remove <path>` for all WI and integration worktrees
   - `git branch -d wave/wi-<slug>-*` and `wave/integration-<slug>`
   - `git tag -d wave-backup-<slug>`
   - `rm -rf .odoo-ai/wave/<slug>/`

3. Report: final commit SHA on principal, files changed, verify result.

## Scaling Rule

| WI count | Mode | Plan artifact |
|---|---|---|
| 1 WI | Minimal - inline micro-plan; integration branch + 1 worktree + squash + human-confirm still apply; consider standalone-first fallback first | Inline in conversation |
| 2-3 WI | Plan-gate mode - full Phase 0 gate, worktrees, review | Inline in conversation |
| >=4 WI | Full mode - plan-artifact at `.odoo-ai/wave/<slug>/plan.md` | Written file (gitignored) |

For 1 WI: wave overhead is likely unnecessary. Present the standalone-first fallback first.

## Standalone fallback

When the wave process is unnecessary (1 WI, trivial change, or user preference):

1. Propose running the task directly in the current worktree.
2. State why the wave overhead is not warranted.
3. Offer: "Run directly (simpler) OR proceed as a wave (more isolation)?"

If the user chooses direct: dispatch the appropriate specialist skill (odoo-coding,
odoo-code-review, etc.) via the Skill tool and stop.

## Examples

> Full worked examples with action detail: `reference/wave-templates.md` §Examples. Dispatches:

**Example 1 - Standard 3-WI wave:** 3 Sonnet workers (weight 6, within BUDGET=8) all in parallel.
Serialize cherry-picks in the orchestrating context. Opus review + odoo-code-review. 1 PR. Squash + tree-identity.
Wait for human-confirm before merging.

**Example 2 - 1-WI edge case:** Standalone-first fallback offered ("This is a single-file fix -
wave overhead is not needed"). User confirms before wave proceeds.

**Example 3 - Ownership conflict:** models.py in both WI-A and WI-B scopes -> STOP at Phase 0.
Options: (a) move changes to one WI, (b) split into a WI-0 prerequisite.

**Example 4 - Squash mismatch:** `git diff --quiet wave-backup-<slug>` exits 1 -> ABORT,
restore from backup, report differing files, do NOT force-push.

**Example 5 - Conflict resolver:** Cherry-pick of WI-B fails. Dispatch Sonnet resolver subagent
with diff + both WI briefs. Resolver commits fix. Re-run verify. Continue.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
