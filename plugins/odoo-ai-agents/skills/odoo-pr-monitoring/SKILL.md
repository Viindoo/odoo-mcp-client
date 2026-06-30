---
name: odoo-pr-monitoring
description: >
  Owns the PR lifecycle AFTER odoo-wave opens the PR and stops at the L2-squash-gate. A POLLER,
  not a blocking DAG node: it watches the PR CI status + review state via /loop (in-session) or
  /schedule (cron), reading through git-toolkit's git-ops skill. On ANY CI warning/error/fail it
  routes to odoo-debug (root-cause first; fixes authored by odoo-coding) - the fix re-push is ALWAYS
  human-gated (X2), never an autonomous push from the unattended poller; a max_review_rounds cap
  stops review ping-pong (exhaustion -> BLOCKED for a human). On green + approved it presents the
  L2-merge-gate, merges via git-ops, then runs post-merge cleanup. Fire on: "watch PR #N",
  "babysit this PR", "drive the PR to merge", "poll CI until it goes green". Vietnamese:
  "theo doi PR", "canh PR den khi merge". Route opening + squashing the PR to odoo-wave; writing a
  fix to odoo-coding; diagnosing the failure to odoo-debug. DO NOT trigger
  to open a NEW PR, before any PR exists, or for a single-file code change (odoo-coding)
user-invocable: true
model: inherit
---

# odoo-pr-monitoring - the post-PR lifecycle owner (poller)

## Where this sits in the flow (the async PR boundary)

This skill begins exactly where `odoo-wave` ends. `odoo-wave` opens ONE PR (integration ->
principal), squashes with tree-identity verified, and STOPS at the `L2-squash-gate` - it never
merges. PR CI runs for minutes-to-hours and human review takes hours-to-days, so the watch CANNOT
be a synchronous blocking node in the `run-harness` DAG. `odoo-pr-monitoring` is the ASYNC boundary:
a poller that drives the open PR to a merged-and-cleaned state.

```
odoo-wave  ->  open PR + squash (tree-identity)  ->  STOP at L2-squash-gate
   --- ASYNC BOUNDARY (this skill; NOT a blocking DAG node) ---
odoo-pr-monitoring  (poll via /loop in-session | /schedule cron)
   -> any CI warning/error/fail  ->  odoo-debug (D3: root-cause)  ->  odoo-coding (fix)
        -> proposed re-push is HUMAN-GATED (X2); max_review_rounds cap; exhaustion -> BLOCKED
   -> green + approved  ->  present L2-merge-gate  ->  merge (git-ops)
        -> post-merge cleanup (worktrees/branches/tag via git-ops)
```

It makes no domain/code decision and performs no git/GitHub op itself: it reads PR state and merges
through the `git-toolkit:git-ops` skill (which it also uses for cleanup), and routes diagnosis to
`odoo-debug` and fixes to `odoo-coding` - each via its delegate. The repo is PUBLIC and every
git mutation is human-gated + worktree-only; this skill never relaxes that, least of all from an
unattended cron poll.

## Persona

PR release-watcher. After the executor opens the PR, this poller babysits it to merge: it samples
CI + review on an interval, surfaces failures to the right specialist, holds the irreversible merge
behind the human `L2-merge-gate`, and tidies up afterwards. It owns the WATCH and the MERGE; it owns
no code, no design, and no git authority of its own (all git/GitHub work is delegated).

## Inputs - the PR handle (re-attachable across sessions)

The watch is keyed on the PR produced upstream. On start, locate the PR by pointer (do NOT re-open
or re-derive it):

- **PR URL + branches** - from the active `.odoo-ai/run-<id>.json` (the run-DAG `odoo-wave` fed:
  the squashing node's `produced` carries the PR URL, the integration branch, and the squashed SHA).
  Recording the PR URL in `run-<id>.json` is what lets a FRESH session re-attach to an in-flight
  watch: re-attach = read `run-<id>.json`, find the PR URL, resume polling. (`run-harness` owns
  writing `run-<id>.json` - hard rule; this skill SURFACES the PR URL + poll state in its
  Continuation Contract `produced`, and `run-harness` persists it. This skill writes only its own
  poll-state notes under `.odoo-ai/pr-monitoring/<id>.md`.)
- **Direct user invocation** - a user asking "watch PR #N" supplies the PR number/URL directly; no
  run file is required for the standalone watch.

If no PR handle can be resolved (no run file, no PR named), STOP and report `NEEDS_CONTEXT` - never
guess a PR or open a new one.

## Phase 1 - Attach + choose the poll cadence

1. Resolve the PR handle (above). Read any existing poll-state note
   (`.odoo-ai/pr-monitoring/<id>.md`) and the run worklog
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`, oldest-first) so a resumed watch builds on
   what an earlier turn already saw (last CI conclusion, review round count).
2. Choose the cadence and state it:
   - **`/loop` (in-session)** - when the user is present and wants to watch now (default for a
     direct "watch this PR" ask). The poll re-runs on an interval in the live session.
   - **`/schedule` (cron)** - for an unattended, long-running watch that must survive across sessions
     (CI that takes hours, review that takes days). The scheduled run re-attaches via `run-<id>.json`.
3. Initialize `review_round = 0` and read `max_review_rounds` (default a small cap, e.g. 3) from the
   run-node `inputs` when present; this bounds the D3 fix loop (below).

## Phase 2 - Poll PR CI + review state (read-only)

Each poll tick, invoke the `git-toolkit:git-ops` skill (via the Skill tool, per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`) to READ - never to mutate - the PR's:

- CI / checks conclusion (success / failure / error / pending / neutral / cancelled), per check run;
- review decision (approved / changes-requested / review-required) and unresolved review threads;
- mergeable state (clean / blocked / behind / conflicting).

Reading PR/CI/review state is a GitHub-API read - it is delegated to `git-ops`, never run
inline (no `gh`, no GitHub MCP call, no inline git in this skill - the delegation boundary, guarded
by `tests/test_git_delegation_boundary.py`). The poller classifies the returned state into exactly
one of three branches:

- **pending** -> record the tick, keep polling (no action).
- **any warning / error / fail** -> Phase 3 (D3).
- **green + approved + mergeable** -> Phase 4 (the L2-merge-gate).

Record each tick's classification in the poll-state note so the next tick (or a resumed session)
sees the history.

## Phase 3 - D3: CI warning/error/fail -> odoo-debug (root-cause first), fix human-gated

D3 is LOCKED: a failing PR is NOT patched blindly. Root-cause comes before any fix, and the fix is
NEVER pushed autonomously.

1. **Bound the loop.** `review_round += 1`. If `review_round > max_review_rounds`, STOP and report
   `BLOCKED` ("max_review_rounds exhausted - human review") - do not keep re-trying. This prevents
   review/CI ping-pong.
2. **Diagnose.** Route the failure to `odoo-debug` via the Skill tool (front-door debug
   orchestrator: reproduce -> falsifiable hypothesis -> bisect -> confirm-by-toggle). Pass the
   failing check log/summary and the PR/branch context. `odoo-debug` proves the root cause; it does
   not author the fix.
3. **Fix.** When the root cause is known, route the fix to `odoo-coding` via the Skill tool. Per the
   integration-loop contract (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`), the fix
   is authored + committed INSIDE a dedicated worktree on the PR's integration branch - never on the
   principal checkout (S9). `odoo-coding` owns its own coder count + model (Decision X); this skill
   chooses neither.
4. **Re-push is HUMAN-GATED (X2).** The poller PREPARES the fix in the worktree and SURFACES it -
   it NEVER pushes from the unattended poll. Present the proposed change (what failed, the proven
   root cause, the fix diff summary, the target branch) and WAIT for explicit human approval. Only
   after approval is the push delegated to `git-ops` (a human-confirm-gated destructive op;
   git-toolkit enforces the confirm gate as a backstop). An unattended `/schedule` poll that hits a
   failure does NOT push - it parks the proposal and waits for a human at the next attended turn.
5. **Out-of-plan fix -> re-plan, do not silently expand scope (CG-2).** If the fix needs a
   module/wave NOT in the approved plan, do not widen scope (that would bypass the L2 source-writing
   gate). Emit a re-plan request back to `odoo-planning` (a new gated plan), still bounded by
   `max_review_rounds`.
6. After an approved re-push, return to Phase 2 (poll the re-triggered CI).

## Phase 4 - Green + approved -> the L2-merge-gate -> merge -> cleanup

1. **Present the L2-merge-gate (always human).** The merge is irreversible/outward (git merge to the
   principal branch), so it is L2 and the autonomy dial can NEVER lower it (`run-harness` hard rule
   #5). Present a tight summary - PR URL, CI green, review approved, squashed SHA + tree-identity
   result from `odoo-wave` - and WAIT for human approval. Write the gate in the USER'S LANGUAGE
   (translate labels/prose; keep PR URL, branch, SHA, and module names verbatim).
2. **Merge.** On approval, invoke `git-ops` to merge (pass the human approval through
   as `confirmed: yes - <quote>`). This is the only place this skill triggers the merge; there is no
   auto-merge and no CI-triggered merge.
3. **Post-merge cleanup.** After the merge is confirmed on the remote, invoke `git-ops` to run the
   cleanup in one brief (the checklist `odoo-wave` reserved for this owner:
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-wave/reference/wave-templates.md` Cleanup Checklist): remove
   the per-WI worktrees and the integration worktree, delete the WI + integration branches, delete
   the wave-backup tag, and prune stale worktree refs. The gitignored `.odoo-ai/wave/<slug>/` and
   this skill's own `.odoo-ai/pr-monitoring/<id>.md` may be removed inline. Optionally surface a
   version-bump/changelog follow-up (wrapping `make bump`) as a `next` entry for `run-harness` to
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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
<!-- END GENERATED TOOLS -->

> **OSM-first precedence.** Odoo Semantic MCP (OSM) is the PRIMARY source for Odoo source/structure
> (indexed, cross-version, inheritance-resolved, checkout-free); reading the codebase with Read/Grep
> is the FALLBACK, only when OSM is incomplete or unreachable. OSM is STATIC (no live records). This
> skill barely touches OSM: it pins the run's target Odoo series once at attach (which doubles as the
> OSM reachability probe) so the version-pinned context travels with any D3 hand-off to `odoo-debug`
> and into the merge report. All PR/CI/review reads are GitHub-API ops delegated to `git-ops`
> (not OSM), and any deep source grounding happens INSIDE `odoo-debug` / `odoo-coding`, not here.

## Concurrency + handoff

This skill dispatches strictly SERIALLY - one poll, then at most one route (`odoo-debug` then
`odoo-coding`) or one merge per tick. It runs no fan-out, so the Mode-A/Mode-B budgets in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` are never exercised; that SSOT still
governs any subagent it cold-spawns. Every delegate (the `git-ops` skill, `odoo-debug`,
`odoo-coding`) is invoked fresh each turn (Tier-C, the always-correct baseline),
so the watch resumes correctly after any session boundary by re-reading `run-<id>.json` and the
poll-state note.

## Out of Scope

- **Opening or squashing the PR** -> `odoo-wave` owns that and STOPS at the `L2-squash-gate`; this
  skill starts after.
- **Writing a fix** -> `odoo-coding` (backend + frontend); **diagnosing a failure** -> `odoo-debug`
  (root-cause first). This skill only ROUTES to them and gates the re-push.
- **Any inline git / GitHub-API op** -> delegated to git-toolkit via the `git-ops` skill (PR read +
  merge, the re-push, and post-merge cleanup; git-ops routes each to the right leaf). This skill
  never runs `gh`, a GitHub MCP call, or an inline git mutation.
- **Re-planning scope** -> `odoo-planning` (when a fix needs a module/wave outside the approved
  plan, CG-2). This skill never silently expands scope.
- **Autonomous merge or autonomous re-push** -> both are L2 and human-gated; an unattended poll
  never merges and never pushes.

## Standalone-first fallback

Two start modes: (a) inside a run - re-attach via the PR URL in `run-<id>.json`; (b) standalone -
a user names "watch PR #N" directly and the watch runs on that PR with no run file. OSM is optional:
when the odoo-semantic-mcp server is unreachable the watch still runs (PR/CI reads go through
`git-ops`, which needs no OSM), and any D3 hand-off degrades to `odoo-debug`'s own disk
fallback (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`). If the PR handle itself
cannot be resolved, STOP and report `NEEDS_CONTEXT` - never fabricate a PR.

## Continuation Contract

When the watch yields control (a tick with no action, a gate awaiting the human, or a terminal
state), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`:

- **Still watching / pending CI** -> `status: NEEDS_NEXT`, `produced: [.odoo-ai/pr-monitoring/<id>.md]`,
  `next: [{skill: odoo-pr-monitoring, reason: "CI still pending - keep polling", inputs: {pr: <url>}, risk_level: L0}]`
  so the run re-attaches on the next tick.
- **Failure routed (D3)** -> `status: NEEDS_NEXT` with `next` to `odoo-debug` then `odoo-coding`; the
  re-push stays `risk_level: L2` (human-gated).
- **Green + approved, merge pending the gate** -> `status: NEEDS_NEXT` with the `L2-merge-gate` as an
  `L2` next; after a confirmed merge + cleanup -> `status: DONE` with the merged PR URL and the
  cleanup result in `produced`.
- **Bounded out / blocked** -> `status: BLOCKED` with `blocked_reason` (e.g. "max_review_rounds
  exhausted - human review") or `NEEDS_CONTEXT` when the PR handle is missing.

The block is additive; advancing on `next[]` is `run-harness`'s job, never this skill's.
