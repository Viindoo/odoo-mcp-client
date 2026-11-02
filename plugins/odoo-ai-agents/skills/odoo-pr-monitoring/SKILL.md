---
name: odoo-pr-monitoring
argument-hint: "[PR# / branch]"
description: >-
  Watches an open PR until merge: CI, reviews, merge gate
user-invocable: true
model: inherit
---

# odoo-pr-monitoring - the post-PR lifecycle owner (poller)

## Role

Post-PR lifecycle owner. The plan's `integrate` node stops at "PR opened, link reported" (ONE PR
per repo per run). `monitor` runs only when the user asked for the PR to be watched: a CI build
runs for hours and every tick costs tokens; without that ask no loop, cron or wakeup reads the
PR, and a later "how is the PR" is ONE read. `monitor` and
`merge` are ordinary plan nodes (`monitor depends_on integrate`, `merge depends_on
monitor`); this skill runs each time either is dispatched. Each poll tick reads once, classifies,
and PARKS: emit a `NEEDS_NEXT` Continuation Contract naming this skill in `next[]`; a later `/loop`
tick or `/schedule` cron re-invocation re-attaches via `run-<id>.json`. Once the watch classifies
green + approved + mergeable, the `monitor` node reaches DONE; it never performs the merge.

```
monitor node:  poll (/loop | /schedule)
   -> any CI warning/error/fail -> odoo-debug (D3: root-cause) -> odoo-coding (fix)
        -> proposed re-push is human-gated (X2); max_review_rounds cap; exhaustion -> BLOCKED
   -> green + approved + mergeable -> `monitor` DONE
merge node:    present merge approval gate -> merge (git-ops) -> post-merge cleanup (git-ops)
```

Make no domain/code decision and run no git/GitHub op yourself: read PR state, merge and clean up
via the `git-toolkit:git-ops` skill, route diagnosis to `odoo-debug` and fixes to `odoo-coding`.
Every git mutation stays human-gated + worktree-only, including from an unattended cron poll.

## Inputs - the PR handle (re-attachable across sessions)

On start, locate the PR by pointer (do NOT re-open or re-derive it):

- **PR URL + branches** - from the active `run-<id>.json`, which lives under the Tier-2 ISOLATE
  dir; resolve it via the resolve-capture-substitute protocol in
  `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (captured path shown as `<ISOLATE_DIR>`
  below) - `<ISOLATE_DIR>/run-<id>.json` (the `integrate` node's `produced` carries the PR URL,
  the run-integration branch, the squashed SHA). A fresh session re-attaches by reading
  `run-<id>.json`. Surface the PR URL + poll state in the Continuation Contract `produced`, and
  write poll-state notes under `<ISOLATE_DIR>/pr-monitoring/<id>.md`.
- **Direct user invocation** - "watch PR #N" supplies the PR number/URL directly; no run file
  required.

If no PR handle can be resolved (no run file, no PR named), STOP and report `NEEDS_CONTEXT` - never
guess a PR or open a new one.

**Two dispatch roles, one skill.** Dispatched as the `monitor` node: run Phase 1 through Phase 3
until the watch classifies green + approved + mergeable, then stop at that node's own DONE (never
enter Phase 4). Dispatched as the `merge` node (never ready until `monitor` is DONE): run Phase 1's
attach step only to re-confirm the recorded state, then go straight to Phase 4 - do not re-poll or
re-run the cadence choice below.

## Phase 1 - Attach + choose the poll cadence

**Orphan sweep (every run, BEFORE step 1 below).**

`find <ISOLATE_DIR>/pr-monitoring/ -maxdepth 1 -type f -name '*.md' -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

1. Resolve the PR handle (above). Read any existing poll-state note
   (`<ISOLATE_DIR>/pr-monitoring/<id>.md`) and the run worklog
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`, oldest-first).
2. Choose the cadence and state it:
   - **ONE read (default)** - read the PR once, classify, report and stop; no interval unless the
     user asked for one.
   - **`/loop` (in-session)** - only when the user asked to watch now. The poll re-runs on an
     interval in the live session.
   - **`/schedule` (cron)** - only when the user asked for an unattended, long-running watch that
     must survive across sessions (CI that takes hours, review that takes days). The scheduled run
     re-attaches via `run-<id>.json`.
3. Initialize `review_round = 0` and read `max_review_rounds` (default a small cap, e.g. 3) from the
   run-node `inputs` when present; this bounds the D3 fix loop (below).

## Phase 2 - Poll PR CI + review state (read-only)

Each poll tick, invoke the `git-toolkit:git-ops` skill (via the Skill tool, per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`) to READ - never to mutate - the PR's:

- CI / checks conclusion (success / failure / error / pending / neutral / cancelled), per check run;
- review decision (approved / changes-requested / review-required) and unresolved review threads;
- mergeable state (clean / blocked / behind / conflicting).

Read PR/CI/review state through `git-ops` only (no `gh`, no GitHub MCP call, no inline git). Classify the returned state into exactly
one of three branches:

- **pending** -> record the tick, keep polling (no action).
- **any warning / error / fail** -> Phase 3 (D3).
- **green + approved + mergeable** -> the `monitor` node's watch is complete; report `DONE`. Do
  NOT proceed to Phase 4 from here - that is the separate `merge` node's job, launched by the
  runner only once this `monitor` node is DONE.

Record each tick's classification in the poll-state note so the next tick (or a resumed session)
sees the history.

## Phase 3 - D3: CI warning/error/fail -> odoo-debug (root-cause first), fix human-gated

Root-cause comes before any fix, and the fix is NEVER pushed autonomously.

1. **Bound the loop.** `review_round += 1`. If `review_round > max_review_rounds`, STOP and report
   `BLOCKED` ("max_review_rounds exhausted - human review") - do not keep re-trying.
2. **Diagnose.** Route the failure to `odoo-debug` via the Skill tool, passing the failing
   check log/summary and the PR/branch context. `odoo-debug` does not author the fix.
3. **Fix.** When the root cause is known, route the fix to `odoo-coding` via the Skill tool. Per the
   integration-loop contract (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`), the fix
   is authored + committed INSIDE a dedicated worktree on the PR's integration branch - never on the
   principal checkout (S9). Choose neither coder count nor model.
4. **Re-push is HUMAN-GATED (X2).** The poller PREPARES the fix in the worktree and SURFACES it -
   it NEVER pushes from the unattended poll. Present the proposed change (what failed, the proven
   root cause, the fix diff summary, the target branch) and WAIT for explicit human approval. Only
   after approval is the push delegated to `git-ops`. An unattended `/schedule` poll that hits a
   failure does NOT push - it parks the proposal and waits for a human at the next attended turn.
5. **Out-of-plan fix -> re-plan (CG-2).** A fix that needs a node NOT in the approved plan
   re-plans per `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate
   per request, rule 7, still bounded by `max_review_rounds`.
6. After an approved re-push, return to Phase 2 (poll the re-triggered CI).

## Phase 4 - Dispatched as `merge`: the merge approval gate -> merge -> cleanup

1. **Present the merge approval gate (always human).** The autonomy dial can NEVER lower this gate
   (`plan-mode-schema.md` § Running the plan, step 7). Present a tight summary - PR URL, CI green,
   review approved, squashed SHA + tree-identity result from the `integrate` node - and WAIT for
   human approval. Write the gate in the USER'S LANGUAGE
   (translate labels/prose; keep PR URL, branch, SHA, and module names verbatim).
2. **Merge.** On approval, invoke `git-ops` to merge (pass the human approval through
   as `confirmed: yes - <quote>`). There is no auto-merge and no CI-triggered merge.
3. **Post-merge cleanup.** After the merge is confirmed on the remote, invoke `git-ops` to run the
   cleanup in one brief (`op=integration-cleanup`): remove every node worktree and the
   run-integration worktree, delete the per-node branches and the run-integration branch, delete
   the run-integration-backup tag, and prune stale worktree refs:

   ```
   [ ] remove worktree <worktree_root>/<node-id>   (every node worktree of this run)
   [ ] remove worktree <worktree_root>/run-integration
   [ ] delete branch node/<slug>-<node-id>         (every node branch of this run)
   [ ] delete branch run-integration-<slug>        (after the merge is confirmed on the remote)
   [ ] delete tag run-integration-backup-<slug>
   [ ] worktree-prune
   ```

   A docs-site series worktree whose PR merged or closed is removed through `git-toolkit:git-ops`
   in the same brief.

   `<ISOLATE_DIR>/integration/<slug>/` (outside any git working tree) and this skill's own
   `<ISOLATE_DIR>/pr-monitoring/<id>.md` are removed inline. Optionally surface a
   version-bump/changelog follow-up (wrapping `make bump`) as a `next` entry for the runner to
   gate - do not run it autonomously.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
<!-- END GENERATED TOOLS -->

## Concurrency + handoff

Dispatch strictly SERIALLY - one poll, then at most one route (`odoo-debug` then `odoo-coding`) or
one merge per tick, no fan-out. Invoke every delegate fresh each turn; resume across a session
boundary by re-reading `run-<id>.json` + the poll-state note. When composing the dispatch prompt for any
specialist agent you dispatch, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief.

## Out of Scope

- **Opening or squashing the PR** -> the plan's `integrate` node.
- **Writing a fix** -> `odoo-coding` (backend + frontend); **diagnosing a failure** -> `odoo-debug`
  (root-cause first). This skill only ROUTES to them and gates the re-push.
- **Any inline git / GitHub-API op** -> `git-toolkit:git-ops` (PR read, merge, re-push, cleanup).
- **Re-planning scope** -> `odoo-planning` (a fix needing a node outside the approved plan, CG-2).
- **Autonomous merge or autonomous re-push** -> never from an unattended poll.

## Standalone-first fallback

Two start modes: (a) inside a run - re-attach via the PR URL in `run-<id>.json`; (b) standalone -
a user names "watch PR #N" directly and the watch runs on that PR with no run file. When OSM is unreachable the watch still runs, and any D3 hand-off degrades to `odoo-debug`'s own
disk fallback (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`). If the PR handle itself
cannot be resolved, STOP and report `NEEDS_CONTEXT` - never fabricate a PR.

## Continuation Contract

When the watch yields control (a tick with no action, a gate awaiting the human, or a terminal
state), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`:

- **Still watching / pending CI** -> `status: NEEDS_NEXT`, `produced: [<ISOLATE_DIR>/pr-monitoring/<id>.md]`,
  `next: [{skill: odoo-pr-monitoring, reason: "CI still pending - keep polling", inputs: {pr: <url>}}]`
  so the run re-attaches on the next tick.
- **Failure routed (D3)** -> `status: NEEDS_NEXT` with `next` to `odoo-debug` then `odoo-coding`; the
  re-push stays human-gated (X2).
- **Green + approved + mergeable, dispatched as `monitor`** -> `status: DONE`. Never emit a `next[]`
  entry for the merge here.
- **Dispatched as `merge`, gate awaiting the human** -> `status: NEEDS_NEXT` with the merge approval
  gate as the next step; after a confirmed merge + cleanup -> `status: DONE` with the merged PR URL
  and the cleanup result in `produced`.
- **Bounded out / blocked** -> `status: BLOCKED` with `blocked_reason` (e.g. "max_review_rounds
  exhausted - human review") or `NEEDS_CONTEXT` when the PR handle is missing.
