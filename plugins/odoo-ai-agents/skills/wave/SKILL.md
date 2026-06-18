---
name: wave
description: >
  Orchestrate a multi-work-item (multi-WI) change as a git wave without touching the
  principal branch: create one integration branch, spin up one isolated worktree per WI,
  dispatch a leaf subagent into each worktree, cherry-pick results back onto integration,
  run an end-of-wave Opus review plus /code-review inline, produce one PR, verify squash
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

2. **Depth-0 / self-spawn legality** - This skill (wave) runs at depth 0 (main context)
   only. It spawns WI subagents at depth 1 (integration/coordination layer), which are
   themselves leaf workers at depth-2 ceiling. Leaf workers MUST NOT spawn further
   subagents or invoke any depth0-only skill (the spawner bundles `odoo-coding`,
   `odoo-code-review`, `odoo-ui-review`, plus `/code-review`,
   `skill-creator`, `wave`, `odoo-intake`, `odoo-brl`, `workflow-chaining` - see the
   Skill-Delegation Matrix below and `docs/reference/ORCHESTRATION-MAP.md`).
   Depth ceiling: wave (depth 0) → WI subagent (depth 1) → leaf worker (depth-2 max);
   no further spawning allowed. Concurrency: model-weighted budget (BUDGET=8) per
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) - up to 8 haiku,
   4 sonnet, 2 opus, or exactly 1 fable WI subagent in flight at once; never exceed the
   budget (OOM guard). The cherry-pick step is NOT part of this budget - it is a depth-0
   critical section serialized to one at a time (Phase 2/3), never pushed down to a leaf.

3. **/code-review inline-only** - The `/code-review` skill auto-spawns and is therefore
   only legal at depth 0 (this skill's context). Invoke it here in Phase 4, never inside
   a WI subagent. Findings are fixed either inline or via a brief targeted subagent.

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

Dispatch WI subagents with the **Agent tool** - one Agent tool call per WI, each passing the
WI brief as its `prompt`. Scheduling is **Mode B model-weighted rolling-window**: as each worker
returns and its weight is freed, the next eligible WI (deps cherry-picked) is dispatched.
SSOT for weights and budget: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B).
Full pseudocode: `reference/wave-templates.md` §Mode B Dispatch Loop.

**Key invariants of the loop:**
- A leaf WI worker runs in its OWN isolated worktree. It writes + **commits + returns its SHA(s)**.
  It does **NOT** cherry-pick. Cherry-pick is forbidden to leaves (Hard Rules 1 + 2).
- **Cherry-pick is a depth-0 CRITICAL SECTION, serialized to one in-flight at a time**, run in
  this (main) context in topology/DAG order. No race on the shared integration branch.
- Dependent-gating promise is `cherry_picked[dep]`, **NOT** `completed[dep]`. A dependent WI
  starts only after every dep is **cherry-picked onto integration** (not merely committed in
  its own worktree), because the dependent's worktree forks from integration.
- Dependent worktrees are created **lazily** immediately before dispatch (after `cherry_picked[dep]`
  gate passes) so they fork from an up-to-date integration.

**MANDATORY**: Make real Agent tool calls for each worker dispatch. Do NOT narrate dispatch in
prose instead of calling the tool.

Dispatch rule (Agent-tool only - this plugin does not use the Claude Code Workflow JS tool): fire
every WI whose deps are already cherry-picked, up to the weighted budget; serialize each cherry-pick
at depth-0 as workers return. Never gate on a fixed-size batch; never let a leaf cherry-pick.

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
  - Nesting guard (full text: ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md): you are a
    leaf worker (depth-2). You ARE the specialist - write/review the code yourself, grounding
    every Odoo claim with the OSM MCP tools (an MCP tool call is never a spawn, so it is always
    allowed); follow the odoo-coding / odoo-code-review conventions but
    do NOT invoke those bundles. Do NOT invoke any depth0-only skill (odoo-coding,
    odoo-code-review, odoo-ui-review, wave, odoo-intake, odoo-brl,
    workflow-chaining, /code-review, skill-creator) - they dispatch a fresh agent and are
    main-agent-only. You MAY NL-dispatch a genuinely non-spawning (leaf) skill (e.g.
    odoo-feature-check, odoo-override-finding) for a read-only lookup. Do NOT invoke the Skill
    tool to trigger a spawner. Do NOT spawn a sub-agent. Do NOT git branch/cherry-pick/merge/push;
    stay in your assigned worktree. Only Read/Grep/Glob/Edit/Write/Bash.
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

In Mode B there is no whole-batch barrier: each worker's cherry-pick is serialized inline at
depth-0 as that worker returns, and a dependent WI is dispatched as soon as its deps are
cherry-picked. If a subagent exceeds 15 minutes without output, check its status; do not assume success.

## Skill-Delegation Matrix

| Task | Leaf worker does this | Leaf worker MUST NOT |
|---|---|---|
| Backend Python/XML | Write directly, grounded via OSM (`model_inspect` / `find_examples` / `validate_*`), following `odoo-coding` conventions | Invoke the `odoo-coding` bundle (depth0-only) |
| Frontend JS/OWL/SCSS | Write directly, grounded via OSM (`find_examples` / `resolve_stylesheet`), following `odoo-coding` conventions | Invoke the `odoo-coding` bundle (depth0-only) |
| Review of own output | Self-review inline against `odoo-code-review` conventions | Invoke `odoo-code-review` or `/code-review` |
| Read-only lookup | NL-dispatch a `leaf` skill (`odoo-feature-check`, `odoo-override-finding`) | Spawn a sub-agent; call any depth0-only skill |

**Nesting rule**: depth0-only skills (`odoo-coding`, `odoo-code-review`, `odoo-ui-review`,
`wave`, `odoo-intake`, `odoo-brl`, `workflow-chaining`, `/code-review`,
`skill-creator`) each dispatch a fresh agent and may ONLY be invoked from the main
agent. A leaf worker IS the specialist: it writes/reviews directly, and leaf subagents MAY
NL-dispatch genuinely non-spawning (`leaf`) skills for read-only lookups. Leaf subagents
must NOT spawn further subagents - they are the depth-2 ceiling.

## Phase 3 - Cherry-pick + Conflict Resolution

> This is the cherry-pick contract that Phase 2's Mode B loop applies per WI inside its
> serialized depth-0 critical section - one cherry-pick in flight at a time, in topology
> (module-DAG) order. Cherry-pick is NEVER pushed down to a leaf worker (Hard Rules 1 + 2).

For each WI in topology order:

1. Cherry-pick onto the integration branch:
   `git cherry-pick <sha>` (from within the integration worktree)

2. Run the verify command immediately after each cherry-pick.

3. **On conflict**: dispatch a brief Sonnet resolver subagent with:
   - The conflicting diff and the two WI briefs whose files overlap
   - Nesting guard (verbatim, mandatory - SSOT: ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md):
     "You are a leaf worker (depth-2). You ARE the specialist - resolve and verify directly,
     grounding any Odoo claim with the OSM MCP tools (an MCP tool call is never a spawn). Do NOT
     invoke any depth0-only skill (odoo-coding, odoo-code-review, odoo-ui-review,
     wave, odoo-intake, odoo-brl, workflow-chaining, /code-review, skill-creator)
     - they are main-agent-only. You MAY NL-dispatch a genuinely non-spawning (leaf) skill for a
     read-only lookup. Do NOT invoke the Skill tool to trigger a spawner. Do NOT spawn a
     sub-agent. Do NOT git branch/cherry-pick/merge/push; stay in your assigned worktree. Only
     Read/Grep/Glob/Edit/Write/Bash."
   - Also hand the OSM-First Grounding Contract
     (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md) when the conflict touches Odoo code.

4. Record the cherry-pick SHA and verify result in the plan artifact.

After all WIs are cherry-picked, run the verify command one final time on the full integration state.

## Phase 4 - End-of-Wave Review

**4.1 - End-of-wave review** (in this skill's context, not a subagent):

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and WI count N.

- **Large wave** (>~1500 changed lines OR N >= 8 WIs): escalate to a **fable** review subagent
  dispatched from depth-0. fable costs ~2x opus - ALWAYS needs explicit confirmation: state tier,
  cost, and one-line why; wait for user yes. If user declines or fable is unavailable, fall back
  to **opus inline review** and note the downgrade.
- **Otherwise** (common case): **opus inline review** in this context.

Review the full diff (`git diff <principal>...HEAD`) for:
- Plan adherence, correctness, simplicity, self-containment, confidentiality

Fix findings inline or via a targeted brief subagent. Re-run verify after any fix.

**4.2 - /code-review inline** (invoke from depth 0):

After the Opus review and fixes, invoke `/code-review` on the integration branch.
Address its findings before Phase 5.

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
odoo-code-review, etc.) via NL-dispatch and stop.

## Examples

> Full worked examples with action detail: `reference/wave-templates.md` §Examples. Dispatches:

**Example 1 - Standard 3-WI wave:** 3 Sonnet workers (weight 6, within BUDGET=8) all in parallel.
Serialize cherry-picks at depth-0. Opus review + /code-review. 1 PR. Squash + tree-identity.
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
output for the depth-0 run-driver - it does not change anything produced above.
