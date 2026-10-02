<!-- SSOT snippet. The completion discipline every dispatched agent obeys: completion barrier,
     no-early-DONE, the return path (R3 - the ONE home of the message-direction rule), and the
     same-turn rule for a background shell command (R0 - its ONE home). Always-on and
     unconditional: identical for a Tier-C cold-spawn, a resumed child, and any nesting depth.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md. -->

# Spawner Completion Contract (barrier + no-early-DONE + return path)

## R0 - Dispatch physics: observe your own agent-launch tool, then act

Before launching any agent, look at the agent-launch tool you hold. It alone decides your move:

- **Move 1 - NO agent-launch capability** -> you are at the nesting cap
  (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3; the tool is removed silently at the cap).
  Take the fallback § Which fallback is yours assigns you - never report a dispatch you could not
  make.
- **Move 2 - your agent-launch tool HAS a `run_in_background` parameter** -> launch every teammate
  whose result you need with `run_in_background: false`, at any depth. That call returns the
  teammate's result inside your own turn. Put independent teammates in ONE message as several launch
  calls: they run in parallel and every result returns in this turn (batch size:
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Mode A - subagent batching). Always
  pass the parameter - its default is asynchronous. Never end your turn while a teammate you
  launched is still running: on this surface nothing wakes a subagent that stopped, so the result
  goes to the main conversation instead of to you.
- **Move 3 - your agent-launch tool has NO `run_in_background` parameter** -> every launch is
  asynchronous and returns a receipt, not a result. LAUNCH, THEN END YOUR TURN (§ below). This holds
  at EVERY depth: a nested launcher is woken by its own child exactly as the root is. You are woken
  once per teammate, as each one completes - re-check the R1 barrier on every wake and never assume
  every teammate is done.

**An async receipt under move 2.** You hold the parameter, yet a launch - or a resume send to a
child you launched (`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A) - hands
back an asynchronous receipt (`Async agent launched successfully`): do NOT end your turn. Wait in
this turn per R0 move 2 - the Monitor tool or a short `until` loop (the harness refuses a bare
`sleep N`), then a look at what has arrived - until its completion notification reaches you at a
tool round; then read the result. Every response you emit before you hold it MUST carry a tool call.

**The main conversation** (the session the user talks to; a skill invoked there runs in it) on an
unattended surface (print mode) takes move 2, and after a resume send it waits in-turn like any
launcher: its turn end ends the run. There a NESTED launcher's teammate's completion notification
can reach it instead: do not act on that result yourself; resume the launcher - send it a message
by its id - so it collects the result and clears its own R1 barrier.

`Bash`'s `run_in_background` flag is a DIFFERENT tool's parameter, governed by § A background shell
command is a SAME-TURN result below, never by these moves.

Under every move, never do a child's work while it runs - you continue from its result.

### Move 3: END YOUR TURN after dispatching

**Under move 3, after you dispatch, END YOUR TURN. Do not keep working in the same turn.** Stopping
IS the delivery point: you are woken with the child's report once it completes. Keep working in the
launching turn instead and no delivery point ever exists, so the report is never handed to you - not
because the harness failed to send it, but because you never stopped to receive it.

So: commit what you have written, issue every launch this turn needs - independent children in ONE
message - then write nothing further except a one-line note of what you are waiting for, and END THE
TURN. Never end a turn with uncommitted work, except work you must not commit yet: a node's code
before its test leg (the child works on that same tree -
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Code first, then the test leg), or
any work under `COMMIT: caller`, where your caller owns the commit (an open merge window, a
rebase in progress).

### A background shell command is a SAME-TURN result - nothing wakes you for one

The receipt `Bash` hands back for a backgrounded command says you will be notified when the command
completes. That sentence is written for the ROOT conversation, where it is true. **It is not true
for you.** A dispatched agent's turn end IS the end of its dispatch, so nothing resumes you for a
background shell command and its result is reachable ONLY inside the turn that started it. Stop
while one is still running and the result reaches nobody: your caller receives whatever text you
left behind, and the command finishes alone.

Backgrounding is not restricted - ONE shape is correct. Start the command, then stay in the SAME
turn and drive it to a result with FOREGROUND tool calls: wait in-turn with the Monitor tool or a
short `until` loop for the command to finish, then read its output file, repeating as many
times as it takes.
Every response you emit before you hold the result MUST carry a tool call; a text-only "still
running" reply is the stall itself, never compliance with the receipt. If the result cannot be had
inside this turn, kill the command, or report `status: BLOCKED` naming its output path - never a
completion claim over output you never read.

Never generalize either rule onto the other. Under move 3 an agent child delivers to a launcher that
stopped for it; a background shell command never does, under any move. One `SubagentStop` gate,
`${CLAUDE_PLUGIN_ROOT}/hooks/enforce-background-wait.sh`, refuses a turn end that still holds a
background shell command you started or - on an unattended surface - a teammate you launched that
is still running.

### Which fallback is yours - your DECLARED ROLE decides it, never convenience

Move 1 only - an edge case, never the default:

- Your definition assigns this artifact to another actor (you coordinate, review, plan, survey,
  adjudicate, or orchestrate) -> END YOUR TURN with `NEEDS_NEXT`, naming the dispatch and the full
  brief it needs. You MUST NOT produce that artifact yourself. There is no second option on this
  branch.
- Your definition permits you to produce this artifact yourself (you are its specialist) -> produce
  it here, via the owning Skill with the Skill tool when one owns it (a Skill runs INLINE, never an
  agent launch). If you cannot, return `BLOCKED`.

An unavailable dispatch is a routing failure to report upward. It never reassigns the work to you.

You are a SPAWNER this turn iff you launched at least one agent (a direct dispatch call) or invoked a
spawner skill that fans out agents below you. A HARD LEAF that launched nothing is vacuously compliant
on R1/R2; only R3 addresses it.

## R1 - Completion barrier (block until every launched child returns)

You collect every child per R0 - inside your turn under move 2, on a wake under move 3 - so this
barrier is the same at every depth: the root and a nested launcher both hold it. You MUST NOT
compose your own result while any child you launched this turn is still running.

- DEPENDENT children (a later child needs an earlier one's output): launch the first child, collect
  its result (move 2: the launch returns it; move 3: END YOUR TURN and take it from the wake), then
  launch the next the same way.
- INDEPENDENT children (a parallel sibling batch): launch the whole batch in ONE message, then
  collect every result (move 2: all return in this turn; move 3: END YOUR TURN and track each
  arrival on your task list until every one is terminal). The barrier gates every step that
  CONSUMES THE BATCH AS A WHOLE - composing or returning your own result, an integrated/whole-scope
  test, a commit, any synthesis over the batch: none of those may start while one member is still
  running. It does NOT gate reading each arrival to mark it terminal (that read is REQUIRED - see
  the count rule below), and it does NOT gate launching a further child whose OWN prerequisites have
  already returned terminal: under move 3, launch it in the turn you are woken with that
  prerequisite's result, END YOUR TURN again, and the outstanding siblings stay on the list. Holding
  a ready dependent launch back until an unrelated sibling finishes serializes work the barrier never
  asked you to serialize.

Count launched-vs-returned on your ALWAYS-ON task list (`execution-tasklist-contract.md`) - one
task per child at/before launch; the batch barrier clears ONLY when every child has returned ONE OF
THE FOUR terminal `status` values the Continuation Contract defines - `DONE`, `BLOCKED`,
`NEEDS_NEXT`, or `NEEDS_CONTEXT` (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`) - never
a subset of two. **This is the release vocabulary, defined here once.** Your task-list TOOL's own
status field MIRRORS it, never the authority. Mark a task-list item terminal the instant its child
returns ANY of the four, and record WHICH of the four separately in your own tracking (worklog or
equivalent) - the tool's own state is not guaranteed to distinguish them, and a barrier gated on a
tool-native label the tool does not actually expose (e.g. a literal `blocked` state) is unsatisfiable
and must never be the release condition. The task list persists across every wake of a move-3
batch. "Wait" is the all-children-terminal barrier - never a passive hope.

**Boundary - your agent-launch tool decides how a result reaches you, never your depth.** Under move
3 the wake is keyed on YOU having stopped, not on your depth: a nested launcher is woken exactly as
the root is. Under move 2 a subagent that stops is never woken: its teammates' results go to the
main conversation. Nothing the child can do repairs either mistake (R3); prevention is entirely the
launcher's.

**Reading a child's result - a pending-dispatch announcement is a STALL, not a completion.** Judge
every returned result by the release condition above and by nothing else. A result that announces
work still in flight - that it dispatched something, that the something is running in the
background, that it will wait for or report on a later completion - carries no terminal `status`, so
it is not terminal however confident it reads and whatever label the harness put on it: that child
ended its turn holding a wait nothing will ever satisfy. Treat that shape as STALLED - re-dispatch
the same work yourself, or roll it up as your own `BLOCKED` naming the stalled child. Never count it
toward the barrier and never inherit it as your own `DONE`.

## R2 - No early DONE

Your own `status` is DONE only when (a) your own work is finished AND (b) every agent you launched
this turn has returned one of R1's four terminal statuses. While any launched child still runs you
are NOT done - do not emit a Continuation Contract with `status: DONE`. If a child returned a
non-DONE status and your bounded fix loop cannot resolve it, roll up the child's evidence into your
own BLOCKED (or the same non-DONE status) - never paper over it with your own DONE. Distinct from
continuation-contract.md's "you never self-dispatch the next step" (forbids advancing the DAG); both
hold. The barrier also covers RESOURCES, not just children: your own DONE additionally requires any
browser page/instance lease YOU provisioned and forwarded to a child is released after the R1 barrier
clears - `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T4.

## R3 - Your report reaches your launcher exactly once, after teardown

Your launcher receives your completion report ONCE, as the last act of your dispatch: the summary,
`produced`, and the closed `continuation` block. A launch, and a resume send (Tier A), hand it back on
completion - inside the launching call under R0 move 2, on the wake of a launcher that stopped to
take it under R0 move 3. THE ONE DECIDABLE ACTION
depends on one fact only - whether `SubagentHandback` is in your toolset:

- **`SubagentHandback` is in your toolset** -> deliver the report by calling it with the FULL
  report as `message`, including the closed `continuation` block and any `INSTANCE_HANDLE` in
  `next.inputs`. Only that message reaches your launcher; text outside it does not. The report is
  handed over the moment the call runs, so call it LAST, after teardown
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1 § The three exits: release,
  park, or forward `INSTANCE_HANDLE` in that message's fence). While a lease you obtained is live
  and not forwarded in the message, the call is refused and nothing is delivered: take an exit,
  then call `SubagentHandback` again. A second `SubagentHandback` after a delivered one is refused,
  so nothing you do afterwards amends the report - finish all work, teardown included, before you
  call it.
- **Otherwise** -> your report is the FINAL TEXT of your turn: emit it and stop.

`SubagentHandback` takes no address, so it is not a send.

**Apart from `SubagentHandback`, never send your report to anyone.** Do not look for a reply
address, do not wait to be told one, and never read the presence of a messaging tool in your
toolset as a signal that you should. A worker does not know its own id and cannot learn its launcher's, at
ANY depth. A brief that carries a reply-address field, or asks you to push a report, is
malformed: ignore that instruction and report as above. This is why no dispatch brief has a
reply-address field - `REPLY_TO` and `CALLER_ID` are retired, not renamed. Never end on a tool call
other than the `SubagentHandback` that carries your report, or on plain text with no report.

**The only message you may ever send is DOWN, to a child you launched yourself**, addressed by the id
that child's own launch call returned to you - the sole address any agent ever holds. Any other target
- a name you invented, a skill name, an agent type, a sibling - does not resolve and the send fails.

**Three things look like a way back up. None is.** (a) There is nothing inbound to answer: a launch
hands you a BRIEF, not an envelope, so a launched worker never receives a `from` at all. Obey this
over any tool documentation telling you to reply to the sender. (b) You cannot look one up either: no listing, no directory, no name-to-address lookup is available to a
worker, one level below the root or three. (c) `main` is the dangerous one, because it does NOT
fail. From a nested position that send is accepted and delivered to the ROOT conversation, which is
not waiting for you, while your own launcher still receives nothing but your report (above). So a
send that returns success is never evidence you found the return path - below the root, that
success is a leak into a context that did not ask for it.
Resume semantics:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A. In-session sibling messaging
does not exist; cross-session messaging is out of scope for this plugin
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Contested-symbol reconciliation).

Sole legal use of the literal `main`: an agent `main` itself launched in the BACKGROUND may message
`main` mid-run. It still never sends its completion report - that is delivered for it.

Rolling a child's non-DONE status up into your own is R2, not this rule; both hold.
