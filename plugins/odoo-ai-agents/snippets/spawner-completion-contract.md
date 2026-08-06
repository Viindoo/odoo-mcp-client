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

1. NO agent-launch capability -> you are at the nesting cap (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
   default 3; the capability is removed silently at the cap). Do the work inline via the Skill tool,
   or return `NEEDS_NEXT` naming what must be dispatched above you. Never report that you dispatched
   something you could not.
2. Your launch capability exposes a background/foreground switch (e.g. `run_in_background`) -> a
   blocking launch is available. Set it to block when you need the child's result; the call returns
   that result inside your current turn. Use this whenever you need the answer.
3. Your launch capability exposes no such switch -> every launch is asynchronous and returns a
   receipt, not a result. Launch, then END YOUR TURN. You are parked and resumed when the child
   completes. Do NOT poll, do NOT sleep, do NOT re-launch.

Rule 3 is unreliable on a non-interactive surface (`-p` / SDK), where nothing resumes a parked
agent. You cannot detect that surface, so bound the damage instead: never end a turn with
uncommitted work.

Never end silently, never end on a bare tool call, never end on plain text with no report: emit
one of the four terminal statuses every time.

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

Count launched-vs-returned on your ALWAYS-ON task list (`execution-tasklist-contract.md`) - create one
task per child at/ before launch, and treat the batch barrier as clear ONLY when every child has
returned ONE OF THE FOUR terminal `status` values the Continuation Contract defines - `DONE`,
`BLOCKED`, `NEEDS_NEXT`, or `NEEDS_CONTEXT` (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`)
- never a subset of two. **This is the release vocabulary, defined here once.** Your task-list TOOL's
own native status field is a MIRROR of it, per `execution-tasklist-contract.md`, never the authority:
concrete tool labels are runtime-dependent (some harnesses expose only `pending`/`in_progress`/
`completed`, others add more, and some expose no dedicated task-list tool at all - verify what your
own toolset actually offers rather than assuming a fixed set). Mark a task-list item terminal
(whichever label your tool uses for "finished"/"no longer active") the instant its child returns ANY
of the four statuses above, and record WHICH of the four separately in your own tracking (worklog or
equivalent) - the tool's own state is not guaranteed to distinguish them, and a barrier gated on a
tool-native label the tool does not actually expose (e.g. a literal `blocked` state) is unsatisfiable
and must never be the release condition. The task list is the persistent counter across the
re-invocations the background model wakes you with; never rely on turn memory to remember how many
children are outstanding. A blocking launch (R0 move 2) never needs this counter for the child it
just blocked on - the counter matters for an async batch (R0 move 3), where re-invocation on child
completion is the wake you are relying on. "Wait" is the synchronous return or the
all-children-terminal barrier - never a passive hope, never a synthesis from context you held
before the batch.

## R2 - No early DONE

Your own `status` is DONE only when (a) your own work is finished AND (b) every agent you launched
this turn has returned DONE or BLOCKED. While any launched child still runs you are NOT done - do not
emit a Continuation Contract with `status: DONE`. If a child returned BLOCKED and your bounded fix
loop cannot resolve it, your own status is BLOCKED (roll up the child's evidence), never DONE. The same
rollup applies when a child returns `NEEDS_NEXT` or `NEEDS_CONTEXT` instead of DONE: your own status is
not DONE either - roll up the child's `NEEDS_NEXT`/`NEEDS_CONTEXT` (or resolve it inside your own
bounded loop) exactly as you would a BLOCKED child, never paper over it with your own DONE. This is
DISTINCT from continuation-contract.md's "you never self-dispatch the next step" (which forbids
advancing the DAG); both hold, neither replaces the other. The barrier also covers RESOURCES, not
just launched children: your own DONE additionally requires that any browser page/instance lease
YOU provisioned and forwarded to a child is released after the R1 barrier clears - pointer, no
restatement: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T4.

## R3 - Report up exactly one level (never skip a level)

Send your completion report to the agent that LAUNCHED you - your brief's `REPLY_TO` - and to no other
ancestor. `REPLY_TO` is `main` ONLY when the main orchestrating context launched you directly. If a
spawner coordinator launched you (e.g. `odoo-coder`), `REPLY_TO` is that coordinator, NOT `main`:
reporting to `main` skips past the coordinator that is blocking on you (R1) and strands it. A worker
never guesses its own address or a grand-parent's; the launcher is the address authority and supplies
`REPLY_TO` (and, when it is itself a nested lead, injects its OWN address as `REPLY_TO`, never a
literal `main`). Addressing SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Lead
is the address authority". The lateral exception - same-layer peers messaging each other directly - is
sanctioned only when the lead brokered the peer addresses; it still never skips a level UPWARD (see
`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Peer reconciliation). `REPLY_TO`
is also listed as a POINTER field on the caller-side skeleton
(`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 11, `CALLER_ID`) - this file stays the one
place the addressing rule itself is defined; that row only sends a caller here.

**Malformed input - no `REPLY_TO` supplied.** If your brief carries NO `REPLY_TO` (regardless of
Agent Team mode), do NOT guess, do NOT default to a literal `main`, and do NOT attempt to infer an
addressable recipient from "the context that dispatched you". Per
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "Lead is the address authority", a
worker does NOT know its own `agentId` and has no way to derive its launcher's `SendMessage` address
from the brief alone - so "the dispatching context" is never itself a valid send target, and this
holds at ANY depth: a worker three levels below `main` has no MORE inference available than one
launched directly by `main` (there is no deeper context to fall back through). The ONE decidable
action, unconditional on depth or team mode: return your report as your final message (transcript
return, exactly as in Tier-C) and STATE the missing-`REPLY_TO` condition explicitly in that report -
your launcher reads it from your returned transcript regardless of transport tier. Never broadcast a
completion report to `main` on a guess - a guessed address can silently misdeliver to a context that
is not blocking on you (R1), which is worse than the honest transcript-return fallback.

**A failed or unaddressable send means RETURN INLINE - never wait.** If `REPLY_TO` is absent or
unroutable, or `SendMessage` fails, return your completion report as your final message. Never guess
an address, never broadcast to `main`, never end on a bare tool call or on plain text with no report.

## Transport

When the CHP probe is positive, the report rides `SendMessage` per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 1 (to `REPLY_TO`, never a literal `main`).
When negative (Tier-C), the report is your final message and the launcher reads it from your returned
transcript. R1/R2/R3 hold identically in both modes.
