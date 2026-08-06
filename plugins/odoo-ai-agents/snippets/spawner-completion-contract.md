<!-- SSOT snippet. The single home for the SPAWNER completion discipline every agent that launches
     another agent obeys: completion barrier, no-early-DONE, report-up-one-level. Always-on: holds in
     Tier-C cold-spawn (no SendMessage) exactly as in Agent Team mode. Sits ABOVE
     agent-team-protocol.md (which owns only the SendMessage/task-board TRANSPORT when the CHP probe
     is positive). Distinct from continuation-contract.md's "never self-dispatch the next DAG step"
     (that forbids advancing the DAG; THIS forbids claiming DONE before your children finish - do not
     conflate). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md. -->

# Spawner Completion Contract (barrier + no-early-DONE + report-up-one-level)

## R0 - Dispatch physics: observe your own toolset, then act

Before launching any agent, look at the launch capability you actually have:

1. NO agent-launch capability -> the nesting cap (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3;
   removed silently at the cap). Do the work inline via the Skill tool, or return `NEEDS_NEXT`
   naming what must be dispatched above you - never report a dispatch you could not make.
2. A background/foreground switch is exposed (e.g. `run_in_background`) -> a blocking launch is
   available: set it to block when you need the child's result, which then returns inside your
   current turn. Use this whenever you need the answer.
3. No such switch -> every launch is asynchronous, returning a receipt, not a result: launch, then
   END YOUR TURN. You are parked and resumed when the child completes. Do NOT poll, sleep, or
   re-launch.

Rule 3 is unreliable on a non-interactive surface (`-p` / SDK), where nothing resumes a parked
agent - bound the damage instead: never end a turn with uncommitted work.

Never end silently, on a bare tool call, or on plain text with no report: emit one of the four
terminal statuses every time.

You are a SPAWNER this turn iff you launched at least one agent (a direct dispatch call) or invoked a
spawner skill that fans out agents below you. A HARD LEAF that launched nothing is vacuously compliant
on R1/R2; only R3 addresses it.

## R1 - Completion barrier (block until every launched child returns)

Launching a child dispatches it in the BACKGROUND by default (you are notified on completion);
`run_in_background: false` launches it synchronously (the launch call does not return until the child
finishes). You MUST NOT compose your own result while any child you launched this turn is still
running. Pick the blocking shape by topology:

- DEPENDENT children (a later child needs an earlier one's output): with a blocking launch
  available (R0 move 2), launch each with `run_in_background: false` so the launch itself blocks;
  consume its result, then launch the next. Without one (R0 move 3), launch the first child, end
  your turn, consume its result on resume, then launch the next the same way.
- INDEPENDENT children (a parallel sibling batch): with a blocking launch available, launch the
  whole batch in one message, then hold until EVERY child has returned before you read results or
  synthesize. Without one, launch the whole batch in one message, end your turn, and track each
  child's arrival on your task list until every one is terminal before you synthesize.

Count launched-vs-returned on your ALWAYS-ON task list (`execution-tasklist-contract.md`) - one
task per child at/before launch; the batch barrier clears ONLY when every child has returned ONE OF
THE FOUR terminal `status` values the Continuation Contract defines - `DONE`, `BLOCKED`,
`NEEDS_NEXT`, or `NEEDS_CONTEXT` (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`) - never
a subset of two. **This is the release vocabulary, defined here once.** Your task-list TOOL's own status
field MIRRORS it, per `execution-tasklist-contract.md`, never the authority. Mark a task-list item
terminal the instant its child returns ANY of the four, and record WHICH of the four separately in
your own tracking (worklog or equivalent) - the tool's own state is not guaranteed to distinguish
them, and a barrier gated on a
tool-native label the tool does not actually expose (e.g. a literal `blocked` state) is unsatisfiable
and must never be the release condition. The task list persists across the re-invocations the
background model wakes you with; a blocking launch (R0 move 2) never needs it for the child it just
blocked on - only an async batch (R0 move 3) does. "Wait" is the synchronous return or the
all-children-terminal barrier - never a passive hope.

## R2 - No early DONE

Your own `status` is DONE only when (a) your own work is finished AND (b) every agent you launched
this turn has returned DONE or BLOCKED. While any launched child still runs you are NOT done - do not
emit a Continuation Contract with `status: DONE`. If a child returned BLOCKED (or `NEEDS_NEXT`/
`NEEDS_CONTEXT`) and your bounded fix loop cannot resolve it, roll up the child's evidence into your
own BLOCKED (or the same non-DONE status) - never paper over it with your own DONE. Distinct from
continuation-contract.md's "you never self-dispatch the next step" (forbids advancing the DAG); both
hold. The barrier also covers RESOURCES, not just children: your own DONE additionally requires any
browser page/instance lease YOU provisioned and forwarded to a child is released after the R1 barrier
clears - `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T4.

## R3 - Report up exactly one level (never skip a level)

Send your completion report to the agent that LAUNCHED you - your brief's `REPLY_TO` - and to no other
ancestor. `REPLY_TO` is `main` ONLY when the main orchestrating context launched you directly; if a
spawner coordinator launched you (e.g. `odoo-coder`), `REPLY_TO` is that coordinator, NOT `main` -
reporting to `main` strands the coordinator that is blocking on you (R1). A worker never guesses its
own address or a grand-parent's; the launcher is the address authority and supplies `REPLY_TO` (and,
when itself a nested lead, injects its OWN address, never a literal `main`). Addressing SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Lead is the address authority". Lateral
exception - same-layer peers messaging each other - is sanctioned only when the lead brokered the
peer addresses; it still never skips a level UPWARD (`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md`
§ Peer reconciliation). `REPLY_TO` is also a POINTER field on the caller-side skeleton
(`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 11, `CALLER_ID`); this file stays the one
place the addressing rule itself is defined.

**No `REPLY_TO`, or it is unroutable, or `SendMessage` fails: RETURN INLINE, unconditional on depth
or team mode.** Do NOT guess, do NOT default to a literal `main`, and do NOT attempt to infer an
addressable recipient - a worker does not know its own `agentId` and cannot derive its launcher's
`SendMessage` address from the brief alone, at ANY depth (a worker three levels below `main` has no
more inference available than one launched directly by `main`). The ONE decidable action: return your report as your final
message (transcript return, exactly as in Tier-C) and, when `REPLY_TO` itself was the problem, STATE
that missing/unroutable condition explicitly in the report - your launcher reads it from your
returned transcript regardless of transport tier. Never broadcast a completion report to `main` on a
guess - a guessed address can silently misdeliver to a context that is not blocking on you (R1),
which is worse than the honest transcript-return fallback. Never end on a bare tool call or on plain
text with no report.

## Transport

When the CHP probe is positive, the report rides `SendMessage` per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 1 (to `REPLY_TO`, never a literal `main`).
When negative (Tier-C), the report is your final message and the launcher reads it from your returned
transcript. R1/R2/R3 hold identically in both modes.
