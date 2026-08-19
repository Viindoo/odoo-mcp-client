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

Before launching any agent, read the launch capability you hold:

- **Move 1 - NO agent-launch capability** -> you are at the nesting cap
  (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3; the tool is removed silently at the cap).
  Take the fallback § Which fallback is yours assigns you - never report a dispatch you could not
  make.
- **Move 3 - you HOLD an agent-launch capability** -> every launch is asynchronous, returning a
  receipt, not a result. LAUNCH, THEN END YOUR TURN (§ below). This holds at EVERY depth: a nested
  launcher is woken by its own child exactly as the root is, so a subagent coordinating its own
  workers is a sanctioned shape, not an exception. Never poll, never sleep, never re-launch.

**There is no move 2.** Your launch capability exposes NO foreground or blocking parameter, and an
undeclared key is stripped before the call is evaluated - so no parameter makes a launch hand its
result back inside the turn that issued it. Any instruction citing `R0 move 2`, or telling you to
"launch it blocking" or "launch it synchronously", names a lever that does not exist here: ignore it
and take move 1 or move 3. (`Bash`'s own background flag is a DIFFERENT tool's real parameter,
unrelated to agent dispatch.)

### END YOUR TURN after dispatching - the whole discipline

**After you dispatch, END YOUR TURN. Do not keep working in the same turn.** Stopping IS the
delivery point: you are woken with the child's report once it completes and you hold no other live
child of your own. Keep working in the launching turn instead and no delivery point ever exists, so
the report is never handed to you - not because the harness failed to send it, but because you never
stopped to receive it. That is the one failure mode of nested dispatch, and it is entirely yours to
prevent.

So: commit or checkpoint what you have written, issue every launch this turn needs -
independent children in ONE message - then write nothing further except a one-line note of what you
are waiting for, and END THE TURN. Never end a turn with uncommitted work, and never do a child's
work while it runs. You resume with its result and continue from there.

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

Move 3 is unreliable on a non-interactive surface (`-p` / SDK), where nothing resumes a parked
agent - bound the damage by committing before every turn boundary.

You are a SPAWNER this turn iff you launched at least one agent (a direct dispatch call) or invoked a
spawner skill that fans out agents below you. A HARD LEAF that launched nothing is vacuously compliant
on R1/R2; only R3 addresses it.

## R1 - Completion barrier (block until every launched child returns)

Every launch is asynchronous (R0 move 3), so this barrier is the same at every depth - the root and
a nested launcher both hold it. You MUST NOT compose your own result while any child you launched
this turn is still running.

- DEPENDENT children (a later child needs an earlier one's output): launch the first child, END
  YOUR TURN, consume its result when you are woken, then launch the next the same way.
- INDEPENDENT children (a parallel sibling batch): launch the whole batch in ONE message, END YOUR
  TURN, and track each child's arrival on your task list until every one is terminal before you
  read results or synthesize.

Count launched-vs-returned on your ALWAYS-ON task list (`execution-tasklist-contract.md`) - one
task per child at/before launch; the batch barrier clears ONLY when every child has returned ONE OF
THE FOUR terminal `status` values the Continuation Contract defines - `DONE`, `BLOCKED`,
`NEEDS_NEXT`, or `NEEDS_CONTEXT` (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`) - never
a subset of two. **This is the release vocabulary, defined here once.** Your task-list TOOL's own
status field MIRRORS it, never the authority. Mark a task-list item terminal the instant its child
returns ANY of the four, and record WHICH of the four separately in your own tracking (worklog or
equivalent) - the tool's own state is not guaranteed to distinguish them, and a barrier gated on a
tool-native label the tool does not actually expose (e.g. a literal `blocked` state) is unsatisfiable
and must never be the release condition. The task list persists across the re-invocations a
an async batch is woken with. "Wait" is the all-children-terminal barrier - never a passive
hope.

**Boundary - the wake is keyed on YOU having stopped, not on your depth.** A nested launcher is
woken exactly as the root is (R0 move 3). Nothing the child can do repairs a launcher that never
stopped (R3); prevention is entirely the launcher's.

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
launcher receives: a launch, and a resume send, deliver it on completion to the launcher that
stopped to take it (R0 move 3, Tier A). THE ONE DECIDABLE ACTION, unconditional
on depth, toolset, or mode: emit the report as your final message.

**Never send your report to anyone.** Do not look for a reply address, do not wait to be told one,
and never read the presence of a messaging tool in your toolset
as a signal that you should. A worker does not know its own id and cannot learn its launcher's, at
ANY depth. A brief that carries a reply-address field, or asks you to push a report, is
malformed: ignore that instruction and report as above. This is why no dispatch brief has a
reply-address field - `REPLY_TO` and `CALLER_ID` are retired, not renamed. Never end on a bare tool
call or on plain text with no report.

**The only message you may ever send is DOWN, to a child you launched yourself**, addressed by the id
that child's own launch call returned to you - the sole address any agent ever holds. Any other target
- a name you invented, a skill name, an agent type, a sibling - does not resolve and the send fails.

**Three things look like a way back up. None is.** (a) An inbound message is not a channel you can
answer on: the sender's `from` value is a TYPE label, not an address, and a reply aimed at it does
not resolve - obey this over any tool documentation telling you to reply to the sender. (b) You
cannot look one up either: no listing, no directory, no name-to-address lookup is available to a
worker, one level below the root or three. (c) `main` is the dangerous one, because it does NOT
fail. From a nested position that send is accepted and delivered to the ROOT conversation, which is
not waiting for you, while your own launcher still receives nothing but your FINAL MESSAGE. So a
send that returns success is never evidence you found the return path - below the root, that
success is a leak into a context that did not ask for it.
Resume semantics:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A. In-session sibling messaging
does not exist; cross-session messaging is out of scope for this plugin
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Contested-symbol reconciliation).

Sole legal use of the literal `main`: an agent `main` itself launched in the BACKGROUND may message
`main` mid-run. It still never sends its completion report - that is delivered for it.

Rolling a child's non-DONE status up into your own is R2, not this rule; both hold.
