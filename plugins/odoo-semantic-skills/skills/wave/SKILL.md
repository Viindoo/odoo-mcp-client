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

1. **Principal-branch-lock** — NEVER run `git checkout`, `git switch`, `git commit`,
   `git rebase`, `git merge`, `git pull`, or `git reset --hard` on the principal branch
   (the branch active at skill invocation). All WI branches and the integration branch
   live in separate worktrees. Read-only ops (`git log`, `git diff`, `git status`) on
   the principal are allowed.

2. **Depth-0 / self-spawn legality** — This skill (wave) runs at depth 0 (main context)
   only. It spawns WI subagents at depth 1 (integration/coordination layer), which are
   themselves leaf workers at depth-2 ceiling. Leaf workers MUST NOT spawn further
   subagents or invoke any depth0-only skill (the spawner bundles `odoo-coding`,
   `odoo-code-review`, `odoo-ui-review`, plus `/code-review`,
   `skill-creator`, `wave`, `intake`, `odoo-brl`, `workflow-chaining` — see the
   Skill-Delegation Matrix below and `docs/reference/ORCHESTRATION-MAP.md`).
   Depth ceiling: wave (depth 0) → WI subagent (depth 1) → leaf worker (depth-2 max);
   no further spawning allowed. Concurrency: model-weighted budget (BUDGET=8) per
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) - up to 8 haiku,
   4 sonnet, 2 opus, or exactly 1 fable WI subagent in flight at once; never exceed the
   budget (OOM guard). The cherry-pick step is NOT part of this budget - it is a depth-0
   critical section serialized to one at a time (Phase 2/3), never pushed down to a leaf.

3. **/code-review inline-only** — The `/code-review` skill auto-spawns and is therefore
   only legal at depth 0 (this skill's context). Invoke it here in Phase 4, never inside
   a WI subagent. Findings are fixed either inline or via a brief targeted subagent.

4. **Human-confirm merge** — The skill MUST stop at Phase 6 and wait for explicit user
   confirmation before merging the integration branch. No automated merge, no auto-squash-
   and-merge, no CI-triggered merge. The skill presents the PR URL and waits.

5. **Confidentiality (public-repo — 8 banned groups)** — Artifacts and commit messages
   MUST NOT contain: CEO personal info, customer PII or contract details, internal pricing,
   competitor intelligence beyond public sources, product roadmap details, marketing-in-draft,
   OKR/targets, or internal-tooling paths. Use abstract labels (Customer-A, etc.) in any example text.
   If a user prompt contains such data, acknowledge intent only - do not echo it into files.

6. **Squash tree-identity gate** — Before force-with-lease, verify that the squashed commit
   produces an identical tree: `git diff --quiet <backup-ref>` must exit 0. If it exits
   non-zero the squash is aborted and reported. See `reference/wave-templates.md` for the
   full recipe.

7. **Disjoint file-ownership** — The Phase 0 ownership map must partition all affected
   files across WIs with no overlap. A file appearing in two WI scopes is a hard blocker;
   resolve it before creating any worktrees. Disjoint ownership is what makes cherry-pick
   conflict-free by default.

8. **Verify subagent claims** — Do not trust a subagent's self-report of success. After
   each cherry-pick, run the repo verify command from the Repo Capability Card to confirm
   the integrated state is green. A subagent may report "done" while tests fail.

## Iron Law - pre-wave gate

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

**0.1 - Repo Capability Card** (always run first):

Discover the repo's topology and verification commands. Record:
- `base`: the principal branch name (`git rev-parse --abbrev-ref HEAD`)
- `verify`: the command that must pass after every cherry-pick (from Makefile/CI/README)
- `commit`: conventional commit format requirement (if any)
- `confidential`: public / restricted / internal

Store the card inline in the wave plan. WI subagents inherit it verbatim in their briefs.

**0.2 - File ownership audit**:

List every file that will be changed by the N WIs. Build an ownership map: `{WI -> [files]}`.
Assert the sets are disjoint. If any file appears in two WI scopes, STOP and ask the user to
resolve the overlap before proceeding.

**0.3 - Topology selection**:

Choose a topology from the four standard patterns (see `reference/wave-templates.md`):
- **Independent** - all WIs modify disjoint files; cherry-pick in any order
- **Linear** - WI-B depends on WI-A output; cherry-pick A then B
- **Mixed** - some independent, some sequential; pick independent first
- **Diamond** - WI-B and WI-C both depend on WI-A; pick A first, then B+C parallel

**0.4 - Plan artifact** (for >=4 WIs):

Write `.odoo-ai/wave/<slug>/plan.md` using the full template from
`reference/wave-templates.md`. For 1-3 WIs, the plan lives inline in the conversation.

**0.5 - Plan gate**:

Present the plan to the user before any branch or worktree is created:

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
Confidential: <public | restricted>
Scaling mode: <minimal | plan-gate | full-plan-artifact>

Approve (go / yes) | Refine | Cancel
```

Do NOT create any branch or worktree before the user approves.

## Phase 1 - Integration Branch + Worktrees

After plan approval:

1. Create the integration branch from the principal:
   `git worktree add -b wave/integration-<slug> <path>/integration <principal>`

2. Create a worktree from the integration branch for each WI, using the same command
   shape: `git worktree add -b wave/wi-<slug>-<id> <path>/wi-<id> wave/integration-<slug>`.
   - **Root WIs** (no `depends_on`) can be created up front here - integration already
     holds the base they fork from.
   - **Dependent WIs** are created **lazily** in Phase 2, only after their deps have been
     cherry-picked onto integration, so each dependent worktree forks from an up-to-date
     integration that already contains its deps' commits. Creating a dependent worktree
     here (before its deps land) would fork it from a stale integration and the worker
     would never see the code it builds on. Phase 2 owns this lazy creation.

3. Record all worktree paths (including the lazily-created dependents, as they are made)
   in the plan artifact (or inline for 1-3 WIs).

4. Confirm each worktree is clean with `git status --short` before dispatching into it.

## Phase 2 - Dispatch WI Subagents (Mode B rolling-window)

Dispatch WI subagents with the **Agent tool** - one Agent tool call per WI, each passing the
WI brief as its `prompt`. Scheduling is **Mode B model-weighted rolling-window**, NOT a
fixed-size batch barrier: there is no "dispatch a fixed group, wait for the whole group,
dispatch the next group". The moment a WI returns and its weight is freed, the next eligible WI
(whose deps are cherry-picked) is dispatched into the freed budget. SSOT for the weights and
budget is
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) - do NOT restate the
numbers here; read them from there (`BUDGET=8`; haiku=1, sonnet=2, opus=4, fable=8).

**What is fundamentally different from `odoo-coding`'s rolling-window (read carefully):**

- A leaf WI worker runs in its OWN isolated worktree. It writes + **commits + returns its
  SHA(s)** in the structured result. It does **NOT** cherry-pick. Cherry-pick is forbidden to
  leaves (Hard Rule 1 principal/integration ownership + Hard Rule 2 depth-0; enforced by
  `tests/test_wave_hardrules.py`).
- **Cherry-pick is a depth-0 CRITICAL SECTION, serialized to one in-flight at a time**, run in
  this (main) context in topology/DAG order. One cherry-pick at a time = no race on the shared
  integration branch. Verify runs immediately after each cherry-pick (Phase 3 contract). This
  serialization is independent of - and on top of - the weighted budget that bounds the
  parallel *workers*.
- The dependent-gating promise is `cherry_picked[dep]`, **NOT** `completed[dep]`. A dependent
  WI starts only after every dep it lists is **cherry-picked onto integration** (not merely
  committed in the dep's own worktree), because the dependent's worktree forks from integration
  and must contain the dep's code at fork time. This is the deliberate difference from
  `odoo-coding`, where `completed[dep]` (the dep's own commit) is enough.
- The dependent worktree is therefore created **lazily**, immediately before its worker is
  dispatched (after its `cherry_picked[dep]` gate passes), so it forks from an up-to-date
  integration (Phase 1, step 2).

**MANDATORY**: You MUST make real Agent tool calls for each worker dispatch. Do NOT describe
dispatch in prose instead of calling the tool - the user must see actual Agent tool
invocations. If you narrate dispatch without calling the Agent tool, that is a hard violation
of this phase.

**Mode B dispatch loop (orchestrator pseudocode, depth-0):**

```js
// Phase 2 - Mode B rolling-window dispatch + serialized depth-0 cherry-pick.
const WEIGHT = { haiku: 1, sonnet: 2, opus: 4, fable: 8 };
const BUDGET = 8; // SSOT: skills/_shared/concurrency-guard.md (Mode B) - do not restate

// validate tiers up front: a typo'd/missing tier must fail the whole run at t=0,
// before any worker or worktree exists, not silently book the wrong weight
for (const wi of wis) {
  if (!WEIGHT[wi.model]) throw new Error(`WI ${wi.id}: unknown model tier '${wi.model}'`);
}

// weighted semaphore (plain JS - no per-model runtime knob). release() admits
// strictly FIFO so a heavy (fable/opus) waiter is never starved by lighter waiters.
let used = 0; const waiters = [];
const acquire = (w) => new Promise((res) => {
  const attempt = () => (used + w <= BUDGET ? ((used += w), res(), true) : false);
  if (!attempt()) waiters.push(attempt);
});
const release = (w) => { used -= w; while (waiters.length && waiters[0]()) waiters.shift(); };

// CRITICAL SECTION for cherry-pick: one in-flight at a time, depth-0 only.
// The promise chain serializes every cherry-pick onto integration -> no branch race.
let cpChain = Promise.resolve();
const cherryPickSerial = (fn) => (cpChain = cpChain.then(fn, fn));

// per-WI CHERRY-PICKED promise (NOT merely committed). Dependents fork from
// integration, so a dependent must wait until its deps are ON integration.
const cpResolvers = {}; const cherry_picked = {};
for (const wi of wis) cherry_picked[wi.id] = new Promise((r) => { cpResolvers[wi.id] = r; });

const runWI = async (wi) => {
  // gate on deps being CHERRY-PICKED (not merely committed in their own worktree).
  // any dep that resolved false (blocked upstream) blocks this WI too.
  const depsOk = (await Promise.all(
    (wi.depends_on || []).map((d) => cherry_picked[d] ?? Promise.resolve(true))
  )).every(Boolean);
  if (!depsOk) { cpResolvers[wi.id](false); return { id: wi.id, upstreamBlocked: true }; }

  // lazy worktree: create the dependent's worktree NOW, after the gate, so it forks
  // from an up-to-date integration that already holds the dep commits (root WIs were
  // created in Phase 1). git worktree add -b wave/wi-<slug>-<id> <path> wave/integration-<slug>
  ensureWorktree(wi);

  const w = WEIGHT[wi.model];
  await acquire(w);                       // wait for weight budget (rolling window)
  let workerResult;
  try {
    // leaf worker: write + commit in its OWN worktree, return SHA(s). NO cherry-pick.
    workerResult = await agent(wiBrief(wi), {
      label: wi.id, phase: 'implement', model: wi.model, schema: WI_RESULT_SCHEMA,
    });
  } finally { release(w); }               // free weight as soon as the worker returns

  if (!ok(workerResult)) { cpResolvers[wi.id](false); return { id: wi.id, result: workerResult }; }

  // cherry-pick: serialized at depth-0, topology order enforced by the dep gate above.
  await cherryPickSerial(async () => {
    for (const sha of workerResult.committed_shas) {
      cherryPick(sha);                    // git cherry-pick <sha> in the INTEGRATION worktree
      runVerify();                        // Repo Capability Card verify after each pick (Phase 3)
      // on conflict -> dispatch the Phase 3 Sonnet resolver subagent (unchanged) and re-verify
    }
  });
  cpResolvers[wi.id](true);               // unblock dependents ONLY after cherry-picked + verified
  return { id: wi.id, result: workerResult };
};

await Promise.all(wis.map(runWI));        // rolling window; deps enforced per-WI, no batch barrier
```

If the Workflow tool is unavailable, run the same schedule with plain Agent-tool calls: fire
every WI whose deps are already cherry-picked, up to the weighted budget; as each worker
returns, serialize its cherry-pick at depth-0, then admit the next eligible WI. Never gate the
window on a fixed-size group; never let a leaf cherry-pick.

Each subagent receives a **Phase-4 WI brief** as its `prompt`:

```
## WI-<ID> Brief
Worktree path  : <absolute path>
Branch         : wave/wi-<slug>-<id>
Files in scope : <disjoint list>
Task           : <precise description of what to implement>

Repo Capability Card:
  base    : <principal>
  verify  : <command>
  commit  : <convention>
  confidential: <level>

Hard rules:
  - Ground in OSM first — follow the OSM-First Grounding Contract
    (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md): you are in an Odoo context, so
    verify every model/field/method/module/CLI/design-token claim via OSM
    (set_active_version + model_inspect / entity_lookup / find_examples /
    resolve_stylesheet) BEFORE writing, reuse indexed patterns before hand-writing, and if
    OSM is unreachable say so ("OSM unavailable — ungrounded"). Never code Odoo from memory.
  - Nesting guard (full text: ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md): you are a
    leaf worker (depth-2). You ARE the specialist — write/review the code yourself, grounding
    every Odoo claim with the OSM MCP tools (an MCP tool call is never a spawn, so it is always
    allowed); follow the odoo-coding / odoo-code-review conventions but
    do NOT invoke those bundles. Do NOT invoke any depth0-only skill (odoo-coding,
    odoo-code-review, odoo-ui-review, wave, intake, odoo-brl,
    workflow-chaining, /code-review, skill-creator) — they dispatch a fresh agent and are
    main-agent-only. You MAY NL-dispatch a genuinely non-spawning (leaf) skill (e.g.
    odoo-feature-check, odoo-override-finding) for a read-only lookup. Do NOT invoke the Skill
    tool to trigger a spawner. Do NOT spawn a sub-agent. Do NOT git branch/cherry-pick/merge/push;
    stay in your assigned worktree. Only Read/Grep/Glob/Edit/Write/Bash.
  - Only edit files listed in your "Files in scope". Do not touch files owned by other WIs.
  - Commit your work to branch wave/wi-<slug>-<id> using the repo commit convention.
  - Run the verify command and confirm it passes before declaring done. If verify involves
    `odoo-bin` (install/upgrade/test), resolve the target version's real CLI via OSM
    `cli_help` first and follow ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md
    and ODOO-TESTING.md — never assume one version's flags apply to another.
  - Return your result using EXACTLY this template (no prose substitution):

## WI-<ID> Result
Status:  DONE | FAILED
SHA:     <commit sha(s) on wave/wi-<slug>-<id> - REQUIRED on DONE; the orchestrator
         cherry-picks these onto integration. A DONE with no SHA is a failed contract.>
Verify:  PASS | FAIL — <command + result>
Changes: <1-3 bullets: file + what changed>

Confidentiality: <8-group restriction if restricted; otherwise "public repo - standard caution">

Acceptance criteria:
  <specific testable criteria for this WI>
```

In Mode B there is no whole-batch barrier: each worker's cherry-pick is serialized inline at
depth-0 as that worker returns (per the loop above), and a dependent WI is dispatched as soon
as its deps are cherry-picked. Phase 3 below documents the cherry-pick + conflict-resolution
contract that this loop applies per WI; the final full-integration verify (end of Phase 3) runs
once the rolling window has drained (`await Promise.all(...)` resolved). If a subagent exceeds
15 minutes without output, check its status; do not assume success.

## Skill-Delegation Matrix

| Task | Leaf worker does this | Leaf worker MUST NOT |
|---|---|---|
| Backend Python/XML | Write it directly, grounded via OSM tools (`model_inspect` / `find_examples` / `validate_*`), following `odoo-coding` conventions | Invoke the `odoo-coding` bundle (depth0-only) |
| Frontend JS/OWL/SCSS | Write it directly, grounded via OSM tools (`find_examples` / `resolve_stylesheet`), following `odoo-coding` conventions | Invoke the `odoo-coding` bundle (depth0-only) |
| Review of own output | Self-review inline against the `odoo-code-review` conventions | Invoke `odoo-code-review` or `/code-review` |
| Read-only lookup | NL-dispatch a `leaf` skill (`odoo-feature-check`, `odoo-override-finding`) | Spawn a sub-agent; call any depth0-only skill |

**Nesting rule**: depth0-only skills (`odoo-coding`, `odoo-code-review`, `odoo-ui-review`,
`wave`, `intake`, `odoo-brl`, `workflow-chaining`, `/code-review`,
`skill-creator`) each dispatch a fresh agent (depth0→1) and may ONLY be invoked from the main
agent — NEVER from a leaf worker. A leaf worker IS the specialist: it writes/reviews directly
with its own tools (OSM MCP calls are never spawns), and only ever NL-dispatches genuinely
non-spawning (`leaf`) skills for read-only lookups.

## Phase 3 - Cherry-pick + Conflict Resolution

> This is the cherry-pick contract that Phase 2's Mode B loop applies per WI inside its
> serialized depth-0 critical section (`cherryPickSerial`) - one cherry-pick in flight at a
> time, in topology order. It is documented here as a standalone contract; the steps below are
> exactly what runs at depth-0 each time a worker returns its SHA. Cherry-pick is NEVER pushed
> down to a leaf worker (Hard Rules 1 + 2).

For each WI (in topology order):

1. Cherry-pick the WI commit(s) onto the integration branch:
   `git cherry-pick <sha>` (from within the integration worktree)

2. Run the verify command immediately after each cherry-pick.

3. **On conflict**: dispatch a brief Sonnet resolver subagent with:
   - The conflicting diff
   - The two WI briefs whose files overlap (for context)
   - Instruction: resolve conflict, verify, commit.
   - Nesting guard (verbatim, mandatory — SSOT: ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md):
     "You are a leaf worker (depth-2). You ARE the specialist — resolve and verify directly,
     grounding any Odoo claim with the OSM MCP tools (an MCP tool call is never a spawn). Do NOT
     invoke any depth0-only skill (odoo-coding, odoo-code-review, odoo-ui-review,
     wave, intake, odoo-brl, workflow-chaining, /code-review, skill-creator)
     — they are main-agent-only. You MAY NL-dispatch a genuinely non-spawning (leaf) skill for a
     read-only lookup. Do NOT invoke the Skill tool to trigger a spawner. Do NOT spawn a
     sub-agent. Do NOT git branch/cherry-pick/merge/push; stay in your assigned worktree. Only
     Read/Grep/Glob/Edit/Write/Bash."
   - Also hand the resolver the OSM-First Grounding Contract
     (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md) when the conflict touches Odoo code.

4. Record the cherry-pick SHA and verify result in the plan artifact.

After all WIs are cherry-picked, run the verify command one final time on the full
integration branch state.

## Phase 4 - End-of-Wave Review

**4.1 - End-of-wave review** (in this skill's context by default, not a subagent):

Size the review tier first. Measure the integration diff and WI count:
`git diff <principal>...HEAD --shortstat` (changed lines) and the WI count N from the plan.

- **Large wave** (changed lines > ~1500 OR N >= 8 WIs): escalate to a **fable** review
  subagent, dispatched from THIS depth-0 context (legal, like `/code-review` in 4.2 - never
  pushed down to a leaf; the review subagent only READS the diff and reports, it does not
  cherry-pick or commit). fable costs ~2x opus, so it ALWAYS needs explicit human confirmation:
  state the tier, the cost, and a one-line why on its own line (e.g. `Fable review: <X> lines /
  <N> WIs exceeds the opus-inline threshold (~2x opus cost). Confirm fable?`) and wait for the
  user's yes. If the user declines, or the fable dispatch fails (insufficient usage credit,
  model unavailable, Agent-tool error), fall back to **opus inline review** automatically and
  note the downgrade (`review: opus (fable declined/unavailable)`).
- **Otherwise** (the common case): **opus inline review** in this context (current behavior).

Either way, review the full diff on the integration branch (`git diff <principal>...HEAD`) for:
- Plan adherence: does the code match what was specified in each WI brief?
- Correctness: obvious logic errors, missing cases, unhandled errors
- Simplicity: over-engineering, speculative abstraction, unused code
- Self-contain: no machine paths, no internal-tooling refs, no internal code leaked into public files
- Confidentiality: no banned-group content in committed artifacts

Fix any findings directly (inline edit) or via a targeted brief subagent if the fix is
non-trivial. Re-run verify after any fix.

**4.2 - /code-review inline** (invoke from this context, depth 0):

After the Opus review and fixes, invoke `/code-review` on the integration branch.
Address its findings before proceeding to Phase 5.

## Phase 5 - PR + Squash + Tree Identity

**5.1 - PR creation**:

Push the integration branch and open a PR against the principal branch.
PR title follows the repo commit convention. PR body includes:
- Summary of all WIs
- Verify command result
- Link to plan artifact (if >=4-WI wave)

**5.2 - Squash + tree-identity gate**:

Before squashing, run the stale-base guard:
```
git fetch origin <principal>
git merge-base --is-ancestor origin/<principal> HEAD
```
If the ancestry check fails, the principal has moved since integration was cut.
ABORT: rebase integration onto `origin/<principal>` first, re-run verify, then return here.
Skipping this guard can silently revert commits that landed on the principal after the
integration branch was created — the tree-identity check does NOT catch this (tree matches
backup but commit graph is wrong).

After the guard passes, create a backup ref:
`git tag wave-backup-<slug> HEAD`

Run the squash (against the freshly-fetched remote ref):
`git reset --soft origin/<principal>`
`git commit -m "<conventional message>"`

Verify tree identity:
`git diff --quiet wave-backup-<slug>` (exit 0 = trees match; exit non-zero = ABORT)

On abort: restore from backup ref, report the mismatch, do not force-push.

See `reference/wave-templates.md` for the full squash recipe with stale-base guard details.

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

1. Merge the PR (or note that the user merged it directly via the URL).

2. Cleanup:
   - Remove WI worktrees: `git worktree remove <path>`
   - Remove WI branches: `git branch -d wave/wi-<slug>-*`
   - Remove integration worktree and branch after merge
   - Remove backup tag: `git tag -d wave-backup-<slug>`
   - Remove `.odoo-ai/wave/<slug>/` if present (gitignored; safe to delete)

3. Report: final commit SHA on principal, files changed, verify result.

## Scaling Rule

| WI count | Mode | Plan artifact |
|---|---|---|
| 1 WI | Minimal - inline micro-plan (no plan-artifact file); integration branch + 1 worktree + squash + human-confirm still apply; consider standalone-first fallback first | Inline in conversation |
| 2-3 WI | Plan-gate mode - full Phase 0 gate, worktrees, review | Inline in conversation |
| >=4 WI | Full mode - plan-artifact at `.odoo-ai/wave/<slug>/plan.md` | Written file (gitignored) |

For 1 WI: the wave overhead (integration branch, cherry-pick, squash) is likely unnecessary.
Present the standalone-first fallback first and ask the user to confirm they want the full
wave process.

## Standalone-first fallback

When the wave process is unnecessary (1 WI, trivial change, or user preference):

1. Propose running the task directly in the current worktree.
2. State why the wave overhead is not warranted.
3. Offer: "Run directly (simpler) OR proceed as a wave (more isolation)?"

If the user chooses direct: dispatch the appropriate specialist skill (odoo-coding,
odoo-code-review, etc.) via NL-dispatch and stop.

## Examples

**Example 1 - Standard 3-WI wave:**
Prompt: "Parallelize these 3 changes: add computed field to sale.order, add OWL widget, update unit tests. Land them safely without touching main."
Action: Phase 0 discovers disjoint files, selects independent topology. Gate shows ownership
map. On approve: integration branch + 3 worktrees. Dispatch the 3 Sonnet WI subagents under the
Mode B rolling window (3 x sonnet = weight 6, within BUDGET=8, so all three run at once).
Serialize each cherry-pick at depth-0 as its worker returns. Opus review + /code-review. 1 PR.
Squash + tree-identity. Wait for human-confirm.

**Example 2 - 1-WI edge case:**
Prompt: "Do this as a wave: fix the typo in account.move description."
Action: Phase 0 sees 1 WI. Standalone-first fallback: "This is a single-file fix -
wave overhead is not needed. Run odoo-coding directly? Or confirm you want a wave."

**Example 3 - Ownership conflict detected:**
Prompt: "Parallelize WI-A (edits models.py + tests.py) and WI-B (edits models.py + views.py)."
Action: Phase 0 ownership audit finds models.py in both scopes. STOP: "models.py appears
in both WI-A and WI-B. Resolve the overlap before I can create worktrees. Options:
(a) move models.py changes to one WI, (b) split the models.py change into a WI-0 prerequisite."

**Example 4 - Squash mismatch abort:**
Prompt context: squash step on 4-WI integration branch.
Action: `git diff --quiet wave-backup-<slug>` exits 1 (tree mismatch). Abort:
"Squash tree-identity FAILED - the squashed commit does not match the pre-squash tree.
Restoring from wave-backup-<slug>. Do NOT force-push. Investigate the mismatch before
proceeding." Report the differing files.

**Example 5 - Conflict resolver path:**
WI-A and WI-B unexpectedly both touch `__init__.py` (missed in Phase 0 audit):
Cherry-pick of WI-B fails with conflict. Dispatch Sonnet resolver subagent with the conflict
diff + both WI briefs. Resolver commits the fix. Re-run verify. Continue.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
