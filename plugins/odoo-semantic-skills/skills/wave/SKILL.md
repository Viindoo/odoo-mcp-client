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
  Do NOT use for a single-file change (use odoo-coder), requirement scoping (use odoo-brl),
  or in-context skill chaining (use workflow-runner).
  Never auto-merge - HUMAN-CONFIRM is the terminal gate
model: opus
disallowed-tools: Write Edit
---

## Persona

Release-train conductor. This skill owns the git topology and subagent lifecycle for a
multi-WI change. It makes zero domain decisions (code style, business logic, architecture
choices all belong to the leaf subagents). Its only job is to get N independent work items
from "idea" to "one green PR ready for human merge" safely, without ever touching the
principal branch.

## Out of Scope

- Single-file or single-WI change -> use `odoo-coder` directly
- Requirement scoping, BRL classification -> use `odoo-brl`
- In-context NL skill chaining without git branches -> use `workflow-runner`
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
   subagents or call self-spawning skills (`/code-review`, `skill-creator`, `wave`).
   Depth ceiling: wave (depth 0) → WI subagent (depth 1) → leaf worker (depth-2 max);
   no further spawning allowed. Maximum concurrent WI subagents: 3.

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
WIs         : <N>  (capped at 3 concurrent)
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

2. For each WI, create a worktree from the integration branch:
   `git worktree add -b wave/wi-<slug>-<id> <path>/wi-<id> wave/integration-<slug>`

3. Record all worktree paths in the plan artifact (or inline for 1-3 WIs).

4. Confirm all worktrees are clean with `git status --short` before dispatching.

## Phase 2 - Dispatch WI Subagents

Dispatch up to 3 concurrent WI subagents using the **Agent tool** — one Agent tool call per
WI. Make all Agent tool calls in a **single turn (same message, parallel)** so they run
concurrently. Pass the WI brief as the `prompt` parameter of each Agent call.

**MANDATORY**: You MUST make real Agent tool calls. Do NOT describe dispatch in prose
instead of calling the tool — the user must see actual Agent tool invocations. If you
narrate dispatch without calling the Agent tool, that is a hard violation of this phase.

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
  - You are a leaf worker (depth-2). You MAY NL-dispatch a non-spawning specialist skill
    (e.g. odoo-coder, odoo-code-reviewer) if it helps. Do NOT invoke the Skill tool
    directly. Do NOT spawn a sub-agent. Do NOT call self-spawning skills (/code-review,
    skill-creator, wave). Do NOT git branch/cherry-pick/merge/push; stay in your assigned
    worktree. Only Read/Grep/Glob/Edit/Write/Bash.
  - Only edit files listed in your "Files in scope". Do not touch files owned by other WIs.
  - Commit your work to branch wave/wi-<slug>-<id> using the repo commit convention.
  - Run the verify command and confirm it passes before declaring done.
  - Return your result using EXACTLY this template (no prose substitution):

## WI-<ID> Result
Status:  DONE | FAILED
SHA:     <commit sha or "no-commit (orchestrator commits)">
Verify:  PASS | FAIL — <command + result>
Changes: <1-3 bullets: file + what changed>

Confidentiality: <8-group restriction if restricted; otherwise "public repo - standard caution">

Acceptance criteria:
  <specific testable criteria for this WI>
```

Wait for all dispatched subagents to complete before proceeding to Phase 3.
If a subagent exceeds 15 minutes without output, check its status; do not assume success.

## Skill-Delegation Matrix

| Task | Leaf subagent MAY use (NL-dispatch) | Leaf subagent MUST NOT |
|---|---|---|
| Backend Python/XML code | odoo-coder (non-spawning) | Spawn subagent |
| Code review of own output | odoo-code-reviewer (non-spawning) | Call /code-review |
| Frontend JS/OWL | odoo-frontend-coder (non-spawning) | Call wave recursively |
| Any skill that auto-spawns | N/A - not allowed | Call skill-creator, /code-review, wave |

**Nesting rule**: Leaf subagents (depth 2) are allowed to NL-dispatch specialist skills
that do NOT themselves spawn subagents. Skills that auto-spawn (/code-review, skill-creator,
wave) are depth-0-only and must NEVER be called from a leaf subagent.

## Phase 3 - Cherry-pick + Conflict Resolution

For each WI (in topology order):

1. Cherry-pick the WI commit(s) onto the integration branch:
   `git cherry-pick <sha>` (from within the integration worktree)

2. Run the verify command immediately after each cherry-pick.

3. **On conflict**: dispatch a brief Sonnet resolver subagent with:
   - The conflicting diff
   - The two WI briefs whose files overlap (for context)
   - Instruction: resolve conflict, verify, commit.
   - Nesting line (verbatim, mandatory): "You are a leaf worker (depth-2). You MAY
     NL-dispatch a non-spawning specialist skill (e.g. odoo-coder, odoo-code-reviewer)
     if it helps. Do NOT invoke the Skill tool directly. Do NOT spawn a sub-agent. Do NOT
     call self-spawning skills (/code-review, skill-creator, wave). Do NOT git
     branch/cherry-pick/merge/push; stay in your assigned worktree. Only
     Read/Grep/Glob/Edit/Write/Bash."

4. Record the cherry-pick SHA and verify result in the plan artifact.

After all WIs are cherry-picked, run the verify command one final time on the full
integration branch state.

## Phase 4 - End-of-Wave Review

**4.1 - Opus inline review** (in this skill's context, not a subagent):

Review the full diff on the integration branch (`git diff <principal>...HEAD`) for:
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

If the user chooses direct: dispatch the appropriate specialist skill (odoo-coder,
odoo-frontend-coder, etc.) via NL-dispatch and stop.

## Examples

**Example 1 - Standard 3-WI wave:**
Prompt: "Parallelize these 3 changes: add computed field to sale.order, add OWL widget, update unit tests. Land them safely without touching main."
Action: Phase 0 discovers disjoint files, selects independent topology. Gate shows ownership
map. On approve: integration branch + 3 worktrees. Dispatch 3 concurrent Sonnet subagents.
Cherry-pick all 3. Opus review + /code-review. 1 PR. Squash + tree-identity. Wait for human-confirm.

**Example 2 - 1-WI edge case:**
Prompt: "Do this as a wave: fix the typo in account.move description."
Action: Phase 0 sees 1 WI. Standalone-first fallback: "This is a single-file fix -
wave overhead is not needed. Run odoo-coder directly? Or confirm you want a wave."

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
