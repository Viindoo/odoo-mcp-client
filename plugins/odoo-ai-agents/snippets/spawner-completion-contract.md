<!-- SSOT snippet. The single home for the SPAWNER completion discipline every agent that launches
     another agent obeys: completion barrier, no-early-DONE, report-up-one-level. Always-on: holds in
     Tier-C cold-spawn (no SendMessage) exactly as in Agent Team mode. Sits ABOVE
     agent-team-protocol.md (which owns only the SendMessage/task-board TRANSPORT when the CHP probe
     is positive). Distinct from continuation-contract.md's "never self-dispatch the next DAG step"
     (that forbids advancing the DAG; THIS forbids claiming DONE before your children finish - do not
     conflate). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md. -->

# Spawner Completion Contract (barrier + no-early-DONE + report-up-one-level)

You are a SPAWNER this turn iff you launched at least one agent (a direct dispatch call) or invoked a
spawner skill that fans out agents below you. A HARD LEAF that launched nothing is vacuously compliant
on R1/R2; only R3 addresses it.

## R1 - Completion barrier (block until every launched child returns)

Launching a child dispatches it in the BACKGROUND by default (you are notified on completion);
`run_in_background: false` launches it synchronously (the launch call does not return until the child
finishes). You MUST NOT compose your own result while any child you launched this turn is still
running. Pick the blocking shape by topology:

- DEPENDENT children (a later child needs an earlier one's output): launch each with
  `run_in_background: false` so the launch itself blocks; consume its result, then launch the next.
- INDEPENDENT children (a parallel sibling batch): launch the whole batch in one message, then hold
  until EVERY child has returned before you read results or synthesize.

Count launched-vs-returned on your ALWAYS-ON task list (`execution-tasklist-contract.md`) - create one
task per child at/ before launch, and treat the batch barrier as clear ONLY when every task on that
list is `completed` or `blocked`. The task list is the persistent counter across the re-invocations
the background model wakes you with; never rely on turn memory to remember how many children are
outstanding. "Wait" is the synchronous return or the all-tasks-terminal barrier - never a passive
hope, never a synthesis from context you held before the batch.

## R2 - No early DONE

Your own `status` is DONE only when (a) your own work is finished AND (b) every agent you launched
this turn has returned DONE or BLOCKED. While any launched child still runs you are NOT done - do not
emit a Continuation Contract with `status: DONE`. If a child returned BLOCKED and your bounded fix
loop cannot resolve it, your own status is BLOCKED (roll up the child's evidence), never DONE. The same
rollup applies when a child returns `NEEDS_NEXT` or `NEEDS_CONTEXT` instead of DONE: your own status is
not DONE either - roll up the child's `NEEDS_NEXT`/`NEEDS_CONTEXT` (or resolve it inside your own
bounded loop) exactly as you would a BLOCKED child, never paper over it with your own DONE. This is
DISTINCT from continuation-contract.md's "you never self-dispatch the next step" (which forbids
advancing the DAG); both hold, neither replaces the other.

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
`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` § Peer reconciliation).

**Malformed input - no `REPLY_TO` supplied.** If you are in Agent Team mode (`SendMessage` available
in your own toolset) but your brief carries NO `REPLY_TO`, do NOT guess and do NOT default to a
literal `main`. Instead treat the context that dispatched you (the agent/skill invocation that
produced your brief) as the recipient; if that context cannot be determined either, return your
report as your final message (transcript return, exactly as in Tier-C) and STATE the missing-
`REPLY_TO` condition explicitly in that report. Never broadcast a completion report to `main` on a
guess - a guessed address can silently misdeliver to a context that is not blocking on you (R1),
which is worse than the honest transcript-return fallback.

## Transport

When the CHP probe is positive, the report rides `SendMessage` per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 1 (to `REPLY_TO`, never a literal `main`).
When negative (Tier-C), the report is your final message and the launcher reads it from your returned
transcript. R1/R2/R3 hold identically in both modes.
