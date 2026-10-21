<!-- SSOT snippet: teardown before DONE - browser pages (T2), instance leases (T3), the DONE-gate
     (T0), ownership (T1), failure paths (T4), and browser single-flight. Edit here only; consumers
     point at ${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md. -->

# Resource Teardown Contract (close/release before DONE)

## Verb glossary - read this first

Two resource classes, two disjoint verb sets. Never mix them:

- **CLOSE** - browser verbs. You CLOSE a page/tab/context and STOP a recording/trace.
  These verbs never apply to an Odoo instance or its lease.
- **RELEASE / DROP** - Odoo instance verbs. You RELEASE a lease (which may DROP the DB and
  stop the server). These verbs never apply to a browser page.

Closing a browser page never touches the lease. Every "never drop or release the lease"
instruction refers to the INSTANCE only and never excuses skipping the browser CLOSE rules below.

## T0 - The DONE-gate

You may not emit `status: DONE` while:
(a) a browser page, tab, context, recording, or trace that YOU drove this dispatch (T1) is still
    open or running, or
(b) an Odoo instance lease that YOU obtained this dispatch (`lease_acquire`, `lease_adopt`, or
    an `instance_serve` by series that leased it for you; serving a forwarded token is consumption,
    not obtaining), or that a child you launched handed back UP to you, is still live - i.e. you neither released it, nor
    PARKED THE LEASE (T1 § The three exits - this is the instance-lease exit, not the same-spelled
    dispatch discipline in `context-handoff-protocol.md`), nor handed it off by name.

A finished report with a live leftover page or instance is NOT done - finish the teardown, then
emit the status. This gate binds every terminal status path (see T4 for BLOCKED / NEEDS_CONTEXT /
handoff).

**The two tiers behind this gate are enforced differently:**
- **(b) Instance teardown is HARD-blocked, and the gate is STATUS-BLIND.** The `SubagentStop`
  `enforce-teardown.sh` hook BLOCKS **any** turn end, whatever its status - a
  `BLOCKED`/`NEEDS_CONTEXT` stop report included, a missing status worst of all - while a live,
  non-shared lease that THIS agent's own tool calls obtained, or a child it launched handed back UP, remains and no T4 named handoff
  forwards it. A parked lease is not a live lease here. A turn end that WAITS for a still-running teammate you launched
  (`spawner-completion-contract.md` R0 move 3) keeps your lease through that stop; your final
  report (`SubagentHandback`) stays gated.
- **(a) Browser-page teardown is ADVISORY** (`enforce-teardown.sh` nudges, never blocks). You
  remain bound to close every page you drove before DONE.

## T1 - Ownership: who tears down what

Teardown belongs to whoever ACQUIRED the resource - never to whoever merely used it. A T4 named handoff moves that ownership to the named catcher; forwarding a handle DOWN to a consumer never does.

| How you hold it | Who tears it down | When |
|---|---|---|
| Browser page/context/recording you DROVE this dispatch - opened, or reused by navigating it (navigating acquires it) | YOU (T2) | as you go + before your terminal status |
| Lease you obtained yourself (any mode but `shared` - including a test-build port lease on a forwarded handle's database) | YOU (one of the three exits below) | before your terminal status |
| `INSTANCE_HANDLE` forwarded DOWN to you in your brief | NEVER you | the agent that acquired it |
| Lease acquired for YOUR run and handed back UP to you (you dispatched its provisioning), or one you acquired AND forwarded to children - you are the run-level owner | YOU | after every child returned (spawner barrier R1) and the run verdict is final - then before your own DONE |
| `MODE_HINT: path-incremental` lease | the skill that drives the path, inline (`odoo-instance` step E) | at path completion - never between steps |
| `shared` lease (multi-reader render server), even one you launched | NO single consumer, ever; its launcher only on an explicit user request to stop it | `lease_gc` once its server is dead |
| A lease you parked (`lease_park`) | YOU, or whoever resumes it by `lease_adopt` + `instance_serve` | at your terminal status the park is the teardown; then the adopter owns it, or `lease_gc` once its park budget lapses. |

**Release directly only what you own.** Call `lease_release` / `lease_park` yourself on a lease
YOU acquired, or on one handed back UP to you as the run-level owner (the rows above). A lease that
reached you DOWN, as a forwarded `INSTANCE_HANDLE`, is never yours to release or park - even though
its `lease_token` and `run_id` would let the call succeed; leave it and name it in your report.
Pass the `run_id` you were given, never one you made up.

### The three exits

A live, non-shared lease you own is cleared by exactly one of THREE exits.

- **`release`** - `lease_release`: stops the server's whole process group, then drops the DB of
  an `ephemeral` lease. Use it when a database you own is finished with.
- **`park`** - `lease_park`: stops the process group if any and KEEPS the database, filestore and ports for a later resume
  (T3); a lease built and never served parks too. Use it when the instance is done for now and the
  database is still wanted.
- **`handoff`** - forward `INSTANCE_HANDLE` to a NAMED catcher in your continuation `next.inputs`
  (T4). The only exit that leaves the server RUNNING, and the only one needing a named owner.

Choose on a fact about the DATABASE, not on convenience: still wanted -> park; finished with ->
release; wanted by a named next step, still running -> handoff.

A build that does not listen leaves the LEASE (db + ports) yours - release it so the DB is dropped.
Never keep a lease alive yourself; you still release.

## T2 - Browser: close what you drove

- **Close pages, never the server.** Your teardown scope is INSIDE the browser MCP server: pages, tabs,
  contexts, recordings, traces. NEVER kill, restart, or "clean up" the MCP server process itself.
- **End of dispatch, by family:** chrome-devtools -> `close_page` each page you drove; if it is
  the last open page, `navigate_page` it to `about:blank` instead (it cannot close its last page);
  playwright -> `browser_close` (plus `browser_stop_video` / `browser_stop_tracing` if you
  started either); pagecast -> `stop_recording` for every session you started.
- **Clean up as you go, not just at the end.** Reuse ONE page across a sweep instead of opening a
  page per screen/breakpoint/role; close an extra page/context when that step ends.
- **Single-flight (exclusivity) - PER FAMILY.** At most ONE browser-driving agent runs at a
  time **per MCP family** (chrome-devtools, playwright, pagecast; each headed/headless variant
  is its own family - 6 total). Dispatch same-family browser agents as exclusive, serial steps,
  never a parallel fan-out. Across DISTINCT families, parallel drivers ARE allowed up to the pool
  cap `W` in `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity;
  state-mutating (CRUD) drives stay at most 2 simultaneous regardless of family mix.
- **Headed exception (human-watch).** When the human explicitly asked to WATCH, you may leave the
  watched page open at the human's request - state that you did, and name the human as the owner
  who closes it (a T4 named-catcher handoff). Default (nobody asked to watch): close, headed or
  not.

## T3 - Instance: release what you provisioned

- **Route the teardown through the lease tools.** Never signal processes, `pkill` an `odoo-bin`,
  or run `dropdb` yourself, and never hardcode a series' flags - resolve per-version CLI via OSM `cli_help`.
- **A refused release is not done.** When `lease_release` returns an error code (e.g. the database
  survived and the lease was kept), follow its remedy; until it succeeds, T4's failure path
  applies.
- Per-mode rule: T1's matrix.
- **Resume a parked lease, never rebuild beside it:** `lease_find` (state `parked`, your
  `run_id`) -> `lease_adopt` its token -> `instance_serve` it.
- If the odoo-local tools are unavailable, use the allocator CLI documented in
  ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md.

## T4 - Failure and handoff paths

- **BLOCKED / NEEDS_CONTEXT do not waive teardown.** Before emitting any terminal status -
  including after an error, a failed oracle, or a REJECTED verdict - close your pages and
  release or park the leases you own.
- **The only exception is an EXPLICIT, NAMED handoff, and it rides ANY status** - T0(b) reads the
  forwarded handle, never the status word (`NEEDS_NEXT` is the usual carrier, not a requirement).
  You may leave a lease you own running ONLY when your continuation forwards
  `INSTANCE_HANDLE` (incl. `lease_token`, `run_id`) in `next.inputs`, naming the catcher that
  needs the live state. An unnamed "forward the token for later release" is not a handoff. Browser pages get no such exception, with one narrow
  carve-out: T2's headed human-watch case, which is itself a NAMED handoff - outside that one
  case, close pages even when handing off.
- **If teardown itself fails** (release errors, a process refuses to die, or the HARNESS REFUSES
  the give-back before it runs), you are BLOCKED, not DONE: quote the refusal AND take the named
  handoff above, with your **dispatching caller** as catcher. Never re-issue or reword a refused
  give-back.
