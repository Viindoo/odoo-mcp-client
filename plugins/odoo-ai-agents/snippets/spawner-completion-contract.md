# Spawner completion contract

How a launcher collects its children, when it may report, and how a report travels. The same at
every nesting depth.

## R0 - Your agent-launch tool decides how results reach you

Look at the launch tool you hold before you launch.

- **Move 1 - you hold no agent-launch tool.** You are at the nesting cap
  (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3: the main conversation is depth 0, each
  launched agent is one deeper than its launcher, an inline skill adds none). The tool is removed
  silently, so your toolset, not the number, is the truth. Take the fallback of § Which fallback
  is yours; never report a dispatch you could not make.
- **Move 2 - the tool has a `run_in_background` parameter.** Launch every teammate whose result
  you need with `run_in_background: false` (the default is asynchronous); the call returns the
  result inside your turn. Independent teammates go in one message as several calls (batch size:
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Fan-out caps). Do not
  end your turn while a teammate you launched runs: nothing wakes a subagent that stopped, and its
  result goes to the main conversation instead.
- **Move 3 - the tool has no `run_in_background` parameter.** Every launch returns a receipt.
  Launch, then end your turn (below). You are woken once per teammate as each completes, at any
  depth; re-check R1 on every wake.

**An async receipt under move 2.** A launch, or a resume send to a child
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A), that hands back
`Async agent launched successfully`: stay in your turn. Wait with `Monitor` (load it first) or a short
`until` loop (a bare `sleep` is refused) until the completion notification arrives at a tool
round, then read the result. Every response before that carries a tool call.

**The main conversation on an unattended surface** (print mode) takes move 2 and waits in-turn
after a resume send, because its turn end ends the run. When a nested launcher's teammate reports
to it instead, it does not act on that result: it resumes the launcher by id so the launcher
collects it.

Under every move, you never do a child's work while it runs.

### Move 3: end your turn after dispatching

Stopping is the delivery point: you are woken with the child's report when it completes; keep
working in the launching turn and no delivery point exists. Commit what you have written, issue
every launch this turn needs in one message, write one line saying what you wait for, and end the
turn. Work you must not commit yet stays uncommitted: a node's code before its test leg
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Code first, then the test leg) and
any work under `COMMIT: caller`.

### A background shell command is a same-turn result

`Bash` says you will be notified when a backgrounded command completes. That holds for the main
conversation only. A dispatched agent's turn end is the end of its dispatch, so the result is
reachable only inside the turn that started the command: start it, wait in the same turn with
foreground calls (`Monitor` or an `until` loop), read its output file, and repeat until
it is done. Every response before the result carries a tool call. When the result cannot be had in
this turn, kill the command or report `BLOCKED` naming its output path - never a completion claim
over output you did not read. `Bash`'s `run_in_background` is a different parameter from the
launch tool's and is governed by this section only. A `SubagentStop` gate refuses a turn end that
still holds a background command you started or, on an unattended surface, a teammate still
running.

### Which fallback is yours

Move 1 only. Your declared role decides:

- Your definition assigns the artifact to another actor (you coordinate, review, plan, survey or
  orchestrate): end your turn with `NEEDS_NEXT` naming the dispatch and its full brief. You do not
  produce the artifact yourself.
- Your definition lets you produce the artifact (you are its specialist): produce it here, through
  the owning skill with the Skill tool when one owns it (a skill runs inline; it is not a launch).
  If you cannot, return `BLOCKED`.

## R1 - Completion barrier

Do not compose your own result while a child you launched is still running.

- Dependent children: launch one, collect its result, launch the next.
- Independent children: launch the batch in one message, then collect every result. The barrier
  gates what consumes the batch as a whole (your own result, an integrated test, a commit, a
  synthesis). It does not gate reading each arrival, nor launching a child whose own prerequisites
  already returned.

Track one task per child on your task list
(`${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`). The barrier clears when every
child returned one of the four statuses of
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `DONE`, `BLOCKED`, `NEEDS_NEXT`,
`NEEDS_CONTEXT`. Mark the task terminal on any of the four and record which one in your worklog;
the task tool's own states mirror the status and are never the release condition.

### Receiving a result

A result is yours to judge before it is anyone else's.

- **Stalled is not complete.** A result that announces work still in flight (it dispatched
  something, it will wait, it will report later) carries no terminal status: re-dispatch the work,
  or roll it up as your own `BLOCKED` naming the child. It never counts toward the barrier.
- **Check the artifact.** A `DONE` is judged by what it owes: the file, commit or tree state exists
  and has size. A build is done on the loaded-modules marker in its log with no error marker, not
  on an exit code; a child that says it waits on a build has nothing running unless a process or a
  growing log proves it.
- **Check the pivotal claims** against the code and against the decisions the owner already made,
  before you act on the report or present it; drop a suggestion that contradicts one.
- **Decide what you own.** A `BLOCKED`, a `NEEDS_CONTEXT`, a question or a doubtful result is
  investigated by you first: read the evidence it cites, measure the state, settle everything your
  role owns, and resume or re-dispatch with what was missing. What remains for your caller or the
  human goes up in the shape of ODOO-AI-ETHOS #2 "How to ask".
- **Judge a wider or narrower delivery on its merits**, never on "it was not asked": extra work
  that is correct, serves the goal and adds no complexity for the end user stays; a narrower one
  with a sound reason is accepted and the remainder is yours. Reject only for a defect or a risk
  you name.
- **Before re-dispatching mutating work**, measure the state the child was to change (HEAD, an
  operation in progress, running processes) and read its whole report. A child that ended without
  handing back may have finished: measure the tree, then resume that child and ask for its report.
  A completion notice that says the report was delivered, with no report from that child in your
  context since your last send to it, is that case: the notice following a send is that send's
  completion, never an echo of an earlier turn, so do not wait for another.
  Never a second writer on a tree the first may still be writing; a replacement brief states the
  HEAD it expects and stops when it differs. Two empty returns from the same kind of child change
  the approach; a third nudge is not one.

## R2 - No early DONE

Your `status` is `DONE` only when your own work is finished, every child you launched returned a
terminal status, and every browser page or instance lease you provisioned and forwarded is
released (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1, T4). A child's
non-`DONE` that your bounded fix loop cannot resolve is rolled up, with its evidence, into your
own non-`DONE` status.

## R3 - Your report reaches your launcher once, after teardown

Your report is the summary, `produced` and the closed `continuation` block, delivered once as the
last act of your dispatch.

- **`SubagentHandback` is in your toolset:** call it with the full report as `message` (the
  continuation block and any `INSTANCE_HANDLE` in `next.inputs` included), alone in a message of
  its own, after teardown and after every other result is read. Only that message reaches your
  launcher. While a lease you obtained is live and not forwarded in the message, the call is
  refused: release, park or forward the lease
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1 § The three exits), then call
  again.
- **Otherwise:** your report is the final text of your turn.

**One report per dispatch.** Your launch is a dispatch, and so is every request your launcher
(the main conversation, or the agent that launched you) sends you after a report of yours was
delivered: its answer is a new report, delivered the same way. Plain text that ends such a turn
reaches nobody - your launcher is told a report arrived and receives none - and a gate stops that
turn end once. A notice of your own background work, a child's report or a hook's note is not a
request and needs no new report. Inside one dispatch a second `SubagentHandback` is refused, so
nothing amends a delivered report. When the call that answers a NEW request is refused as already
delivered, send that answer once with the messaging tool - to the id the request shows as its
sender, to `main` when it shows none - and stop.

Apart from that one case you send your report to no one and look for no reply address: a worker
knows neither its own id nor its launcher's, and a messaging tool in your toolset is not a signal
to use it. The only message you send goes down, to a child you launched, by the id its launch
returned. From a nested position a send to `main` reaches the main conversation, which is not
waiting for you - a send that succeeds is not a return path. An agent the main conversation
launched in the background may message `main` mid-run; its completion report is still delivered
for it.
