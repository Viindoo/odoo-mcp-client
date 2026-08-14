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
   available: set it to block whenever you need the child's answer, which then returns inside your
   current turn. On this path the child's result IS your own launch call's return value - no
   `REPLY_TO`, no `SendMessage`, no reply field needed. OMITTING the switch does NOT block: absent
   means background, the tool's own default. This is the preferred shape, including when you
   yourself are a subagent. **For a subagent this is not a preference: a dispatch whose result you
   need MUST block - and it is now a mechanism, not an honour rule. Backgrounding is REFUSED at the
   call by `hooks/block-nested-background-spawn.sh` (PreToolUse deny, `true` and ABSENT alike), so
   expect a denial, not a stall; re-issue it as a blocking launch.** Backgrounding and ending your turn to wait is the one unrecoverable move -
   nothing wakes you (R1 § Boundary), so the run stops there with no error, no output, and no one
   aware it stopped. Concurrency survives: several blocking launches in ONE message still run
   concurrently.
3. No such switch -> every launch is asynchronous, returning a receipt, not a result. ONLY the root
   conversation is resumed when a background child finishes. If you ARE the root: launch, then END
   YOUR TURN; do NOT poll, sleep, or re-launch. If you are a SUBAGENT: nothing resumes you, so never
   launch-and-park - do the work inline via the Skill tool, or return `NEEDS_NEXT` naming the
   dispatch that must happen above you. Scoped to a launched CHILD: a blocking call that RETURNS a
   verdict inside the one tool call is not a poll.

Even at the root, rule 3 is unreliable on a non-interactive surface (`-p` / SDK), where nothing
resumes a parked agent - bound the damage: never end a turn with uncommitted work.

You are a SPAWNER this turn iff you launched at least one agent (a direct dispatch call) or invoked a
spawner skill that fans out agents below you. A HARD LEAF that launched nothing is vacuously compliant
on R1/R2; only R3 addresses it.

## R1 - Completion barrier (block until every launched child returns)

Background is the launch default (the root is notified on completion); `run_in_background: false`
launches it synchronously (R0 move 2). You MUST NOT compose your own result while any child you
launched this turn is still running. Pick the blocking shape by topology - both async variants below
are ROOT-ONLY (R0 move 3):

- DEPENDENT children (a later child needs an earlier one's output): with a blocking launch
  available (R0 move 2), launch each with `run_in_background: false` so the launch itself blocks;
  consume its result, then launch the next. Without one, at the root, launch the first child, end
  your turn, consume its result on resume, then launch the next the same way.
- INDEPENDENT children (a parallel sibling batch): with a blocking launch available, launch the
  whole batch in one message, then hold until EVERY child has returned before you read results or
  synthesize. Without one, at the root, launch the whole batch in one message, end your turn, and
  track each child's arrival on your task list until every one is terminal before you synthesize.

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
root-only async batch is woken with; a blocking launch (R0 move 2) never needs it for the child it
just blocked on. "Wait" is the synchronous return or the
all-children-terminal barrier - never a passive hope.

**Boundary - a background child outlives a non-`main` launcher.** If you are a subagent and a child
you launched in the background (R0 move 3) finishes after your OWN turn returns, its completion is
re-addressed to `main`, never resumed on you. Do not rely on a background grandchild's result coming
back to you: it lands on a context that was not waiting for it, while you - the one context that
was - are never woken. Nothing the child can do repairs this (R3); prevention is at launch time
only, which is why R0 move 2 is now enforced rather than advised.

**Reading a child's result - a pending-dispatch announcement is a STALL, not a completion.** Judge
every returned result by the release condition above and by nothing else. A result that announces
work still in flight - that it dispatched something, that the something is running in the
background, that it will wait for or report on a later completion - carries no terminal `status`, so
it is not terminal however confident it reads and whatever label the harness put on it: that child
ended its turn holding a wait nothing will ever satisfy. Treat that shape as STALLED - re-dispatch
the same work yourself as a BLOCKING launch (R0 move 2), or roll it up as your own `BLOCKED` naming
the stalled child. Never count it toward the barrier and never inherit it as your own `DONE`.

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
background launch, and a resume send, deliver it on completion to the root that is still live to take
it (R0 move 3, Tier A). THE ONE DECIDABLE ACTION, unconditional
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
not waiting for you, while the launcher that IS waiting stays parked forever. So a send that returns
success is never evidence you found the return path - below the root, that success IS the stall.
Resume semantics:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A. In-session sibling messaging
does not exist; cross-session messaging is out of scope for this plugin
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Contested-symbol reconciliation).

Sole legal use of the literal `main`: an agent `main` itself launched in the BACKGROUND may message
`main` mid-run. It still never sends its completion report - that is delivered for it.

Rolling a child's non-DONE status up into your own is R2, not this rule; both hold.
