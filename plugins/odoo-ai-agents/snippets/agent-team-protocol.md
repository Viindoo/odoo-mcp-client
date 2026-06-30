<!-- SSOT snippet. The single home for the Agent Team mode COMPLETION-REPORT push (teammate->lead)
     and the low-context TASK BOARD (TaskCreate/TaskUpdate/TaskList/TaskGet). Builds on
     context-handoff-protocol.md (reuses its capability probe + confidentiality guard) and
     continuation-contract.md (the report payload shape). CHP owns dispatch/resume (lead->worker);
     THIS owns completion-report + tracking (worker->lead) - the two are non-overlapping.
     Referenced (not copy-pasted) by the spawner/orchestrator skills (run-harness, odoo-intake,
     odoo-coding, odoo-debug, odoo-code-review, wave, odoo-modules-upgrade, odoo-forward-port, ...)
     and by every named teammate brief. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md. -->

# Agent Team Protocol - completion-report push + low-context task board

When the runtime is in **Agent Team mode**, a subagent spawned with a `name` is a TEAMMATE running
in the background, addressable via `SendMessage({to: "<name>"})`; the orchestrating context is the
team LEAD, addressed as `main`. In that mode a teammate's plain-text output AND any file it writes
are INVISIBLE to the lead - only an explicit `SendMessage` delivers content. A finished teammate
that ends its turn on a tool call or on plain text emits only a content-less `idle_notification`,
which strands the lead (it cannot tell *finished-without-reporting* from *still-working*).

This protocol fixes that with two contracts: **Ask 1** - the teammate pushes a completion report to
the lead; **Ask 2** - the lead tracks teammates on a cheap task board. Agent Team mode is OPTIONAL:
it is gated entirely by the CHP capability probe, and when off the whole protocol degrades silently
to today's behavior (final message + Continuation Contract).

This snippet is the worker->lead half. The lead->worker dispatch/resume half (Tier-A SendMessage
resume, Tier-B fork, Tier-C fresh spawn, the capability probe itself, and the confidentiality guard)
lives in `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` (CHP). The two are
non-overlapping SSOTs - do not restate CHP here; point at it.

## Detection - reuse the CHP probe, do not reinvent it

The run is in Agent Team mode exactly when the **CHP capability probe is positive** (env
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `SendMessage` present + addressable worker + you are the
team lead). Run the probe ONCE per run and cache it as CHP specifies - do NOT re-probe here. See
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Capability probe".

- **A worker** knows it is a TEAMMATE (not a cold-spawned Tier-C subagent) when `SendMessage` is
  present in its OWN active toolset for this turn. Present -> apply Ask 1. Absent -> it was
  cold-spawned; behave exactly as today (return the report as your final message + the Continuation
  Contract; never attempt `SendMessage`).
- **The lead** knows team mode is on from the same cached probe result; a positive probe is the
  trigger for Ask 2.

## Ask 1 - teammate completion-report contract (HARD RULE)

> On completing your assigned work, your turn's TERMINAL action MUST be
> `SendMessage({to: "main", text: <report>})`, plus one `SendMessage` to each named teammate listed
> in your brief's `NOTIFY:` field. NEVER end the turn on a bare tool call or on plain-text-only
> output.

NOTIFY peer-push is best-effort - it reaches only already-running dependents; a not-yet-spawned
dependent receives the result via the lead's `main` report (the lead routes it), not a direct peer
push. So `main` is the authoritative delivery channel; the peer push is an early-wakeup optimization
for dependents already in flight.

The report `text` is, in order:

1. your **Continuation Contract** block (the fenced `continuation` block carrying
   `status` / `produced` / `next`, per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`),
2. a SHORT prose summary (a few lines - what you did, what to know), and
3. the `produced:` artifact **PATHS** - the file paths only.

Do NOT inline the full diff, file bodies, or artifact contents into the message - those STAY in the
files you wrote. You STILL write your artifacts AND your worklog to files (in addition to, never
instead of, the `SendMessage`); the report is a pointer-and-summary, not a transport for bulk
content.

**Rationale (state it; it is load-bearing, not narration):** in Agent Team mode your plain text and
your written files are invisible to the lead; only `SendMessage` delivers the report. Ending the
turn on a tool call or on plain text leaves the lead stuck on a content-less `idle_notification`,
forcing a wasted round-trip where it must poke you for the result.

Frame the report as **shared team context** (or "prior-phase findings" / "run worklog contents"),
NEVER as "secret" / "confidential" / "private" - a secret framing makes the substrate refuse
delivery and silently breaks the push. This is the CHP confidentiality guard; full rule in
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Confidentiality guard".

After sending, **END your turn** - the push is fire-and-forget; do not await a synchronous return,
just stop and wait to be resumed if the lead has more for you (CHP async park-and-be-resumed).

## Ask 2 - team-lead tracking contract (HARD RULE)

> When the CHP capability probe is positive, the lead - at or before dispatch - `TaskCreate`s
> exactly ONE task per work-item (title = the work-item id, status `pending`) and injects
> `TASK_ID: <id>`, `REPLY_TO: main`, and `NOTIFY: <dependent teammate names>` into each teammate's
> brief. The teammate `TaskUpdate`s its task `pending` -> `in_progress` at start and ->
> `completed` | `blocked` at end with a status line of at most ONE line. The lead reads STATUS only
> from `TaskList` / `TaskGet`, and report CONTENT only from the Ask-1 `SendMessage` push - NEVER
> from a teammate's `.output` JSONL transcript.

If `TaskCreate` is absent while `SendMessage` is present, skip the task board and rely on the
SendMessage push alone - never error (silent degradation).

Why never the transcript: a `local_agent`'s `.output` file is a symlink to the full JSONL
conversation and overflows the lead's context window; `TaskOutput` is deprecated. `TaskList` /
`TaskGet` return only the cheap status surface, so the lead can poll which teammates are
done / blocked without loading any transcript, and pair that status with the pushed report content.

## Real-time guarantee + the four-channel split

The lead never blocks on a content-less `idle_notification`, because:

- **status is live** - the task board reflects each teammate's `pending` / `in_progress` /
  `completed` / `blocked` the moment it `TaskUpdate`s;
- **content arrives the instant a teammate finishes** - Ask 1 forces the final action to be the
  `SendMessage` report;
- **the lead is never stranded** - Ask 1 forbids ending a turn on a bare tool call or plain text,
  so an `idle_notification` never stands in for a missing report.

Four non-overlapping channels, each with ONE job:

| Channel | Carries | Owner / SSOT |
|---|---|---|
| Task board (`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`) | STATUS (pending/in_progress/completed/blocked) | this snippet, Ask 2 |
| `SendMessage` push | CONTENT (the completion report) | this snippet, Ask 1 |
| Worklog | WHY (the decision journal) | `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` |
| Blackboard (`run-<id>.json`) | the driver RUN-DAG / machine state | run-harness (driver-only) |

## Addressing - main is the lead, the lead is the address authority

`main` is the single orchestrating context that is the team lead - whichever skill is driving in the
MAIN context: run-harness, or a spawner skill that the main context invoked via the Skill tool
(those run IN the main context, they are NOT nested subagents, so they too address as `main`). A
worker NEVER self-addresses or guesses its own id; the lead is the address authority and supplies
every reply-to (`REPLY_TO: main`) and peer name (`NOTIFY: ...`) explicitly in the brief. Full rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Lead is the address authority".

## Fallback - team mode off

When the capability probe is negative (any of: env unset, `SendMessage` absent, not addressable,
not the lead), Agent Team mode is OFF: no task board, no `SendMessage`. The worker returns its
completion report as its FINAL message together with its Continuation Contract, and the lead reads
that returned transcript + the worklog exactly as today. This is silent degradation, never an error
- the protocol is purely additive on top of the always-correct Tier-C behavior.
