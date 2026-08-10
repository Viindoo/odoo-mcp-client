<!-- SSOT snippet. The single home for the completion discipline every dispatched agent obeys:
     completion barrier, no-early-DONE, and the return path (R3 - your report IS your final
     message). Always-on and unconditional: it holds identically for a Tier-C cold-spawn, for a
     resumed child, and at any nesting depth. R3 is the ONE place the message-direction rule is
     defined; every other file points here and never restates it. Distinct from
     continuation-contract.md's "never self-dispatch the next DAG step" (that forbids advancing the
     DAG; THIS forbids claiming DONE before your children finish - do not conflate). Edit here only;
     consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md. -->

# Spawner Completion Contract (barrier + no-early-DONE + return path)

## R0 - Dispatch physics: observe your own toolset, then act

Before launching any agent, look at the launch capability you actually have:

1. NO agent-launch capability -> the nesting cap (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3;
   removed silently at the cap). Do the work inline via the Skill tool, or return `NEEDS_NEXT`
   naming what must be dispatched above you - never report a dispatch you could not make.
2. A background/foreground switch is exposed (e.g. `run_in_background`) -> a blocking launch is
   available: set it to block when you need the child's result, which then returns inside your
   current turn. Use this whenever you need the answer. On this path the child's result IS your own
   launch call's return value - no `REPLY_TO`, no `SendMessage`, no reply field needed; this is the
   DEFAULT, preferred shape, including when you yourself are a subagent.
3. No such switch -> every launch is asynchronous, returning a receipt, not a result: launch, then
   END YOUR TURN. You are parked and resumed when the child completes. Do NOT poll, sleep, or
   re-launch. Scoped to a launched CHILD: a blocking call that RETURNS a verdict inside the one
   tool call is not a poll.

Rule 3 is unreliable on a non-interactive surface (`-p` / SDK), where nothing resumes a parked
agent - bound the damage instead: never end a turn with uncommitted work.

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

**Boundary - a background child outlives a non-`main` launcher.** If you are a subagent (not `main`)
and you launch a child in the background (R0 move 3) but your OWN turn later completes/returns
before that child finishes, the child's eventual completion is re-addressed to `main`, never resumed
on you. Do not rely on a background grandchild's result coming back to you.

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

## R3 - Your report is your final message (there is no upward channel)

Your completion report is the FINAL TEXT of your turn. Emit it and stop. That text IS what your
launcher receives: a blocking launch returns it as that launch call's own return value (R0 move 2); a
background launch delivers it to the launcher on completion; a resume send delivers it the same way,
to whoever resumed you (Tier A). THE ONE DECIDABLE ACTION, unconditional
on depth, toolset, or mode: emit the report as your final message.

**Never send your report to anyone.** Do not look for a reply address, do not wait to be told one, do
not fall back to the literal `main`, and never read the presence of a messaging tool in your toolset
as a signal that you should. A worker does not know its own id and cannot learn its launcher's, at
ANY depth - a worker three levels below `main` has no more inference available than one launched
directly by `main`. A brief that carries a reply-address field, or asks you to push a report, is
malformed: ignore that instruction and report as above. This is why no dispatch brief has a
reply-address field - `REPLY_TO` and `CALLER_ID` are retired, not renamed. Never end on a bare tool
call or on plain text with no report.

**The only message you may ever send is DOWN, to a child you launched yourself**, addressed by the id
that child's own launch call returned to you - the sole address any agent ever holds. Any other target
(a name you invented, a skill name, an agent type, a sibling, `main` when `main` did not launch you)
does not resolve and the send fails. Resume semantics:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A. In-session sibling messaging
does not exist; cross-session messaging is out of scope for this plugin
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Contested-symbol reconciliation).

Sole legal use of the literal `main`: an agent `main` itself launched in the BACKGROUND may message
`main` mid-run. It still never sends its completion report - that is delivered for it.

Rolling a child's non-DONE status up into your own is R2, not this rule; both hold.
