<!-- SSOT snippet. The single home for the resource-teardown-before-DONE invariant: browser
     pages/contexts/recordings (T2) and Odoo instance leases (T3) with one DONE-gate (T0),
     one ownership rule (T1), and one failure-path rule (T4). Also the SSOT for the browser
     single-flight (exclusivity) rule. Edit here only; consumers
     point at ${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md.
     This contract operationalizes ODOO-AI-ETHOS Principle #10 (DONE needs observable evidence)
     for tool-using agents: a resource you left running is evidence the task is NOT done. It does
     not restate #10; it makes it checkable for browsers and instances. -->

# Resource Teardown Contract (close/release before DONE)

## Verb glossary - read this first

Two resource classes, two disjoint verb sets. Never mix them:

- **CLOSE** - browser verbs. You CLOSE a page/tab/context and STOP a recording/trace.
  These verbs never apply to an Odoo instance or its lease.
- **RELEASE / DROP** - Odoo instance verbs. You RELEASE a lease (which may DROP the DB and
  stop the server). These verbs never apply to a browser page.

Closing a browser page is ORTHOGONAL to the instance lease: `close_page` / `browser_close`
touches only the browser; the Odoo server keeps running and the lease is untouched. Every
"never drop or release the lease" instruction you carry refers to the INSTANCE only - it does
not forbid, and never excuses skipping, the browser CLOSE rules below.

## T0 - The DONE-gate

You may not emit `status: DONE` while:
(a) a browser page, tab, context, recording, or trace that YOU opened this dispatch is still
    open or running, or
(b) an Odoo instance that YOU self-provisioned this dispatch is still running under your lease -
    i.e. you neither released it, nor PARKED THE LEASE (T1 § The three exits, which names the
    exact command - this is the instance-lease exit, not the same-spelled dispatch discipline in
    `context-handoff-protocol.md`), nor handed it off by name.

DONE claims two things at once: the goal is met AND the resources the work borrowed are
returned. A finished report with a live leftover page or instance is NOT done - finish the
teardown, then emit the status. This gate binds every terminal status path (see T4 for
BLOCKED / NEEDS_CONTEXT / handoff).

**The two tiers behind this gate are NOT enforced the same way** (full rationale: "Why browsers
and instances are enforced differently" below):
- **(b) Instance teardown is HARD-blocked, and the gate is STATUS-BLIND.** The `SubagentStop`
  `enforce-teardown.sh` hook reads the allocator ledger and BLOCKS **any** turn end, whatever its
  status - a `BLOCKED`/`NEEDS_CONTEXT` stop report included, a missing status worst of all - while
  a live, self-provisioned, non-shared lease remains open and no T4 named handoff forwards it. A
  parked lease is not a live lease here: its row carries `parked_at` and no owner pid because its
  server is already stopped, so parking clears the gate exactly as releasing does.
- **(a) Browser-page teardown is ADVISORY.** The same `enforce-teardown.sh` hook (also registered
  on `Stop`, not only `SubagentStop`) emits a `systemMessage` nudge - never `decision:block` -
  when it infers an apparently-open page from the transcript. You remain contract-bound to close
  every page you opened before DONE; only the ENFORCEMENT tier differs, not the obligation.

## T1 - Ownership: who tears down what

Teardown belongs to whoever ACQUIRED the resource - never to whoever merely used it.

| How you hold it | Who tears it down | When |
|---|---|---|
| Browser page/context/recording you opened | YOU (close/stop it) | as you go + before your terminal status |
| Instance you self-provisioned (no `INSTANCE_HANDLE` in your brief - whatever `persist:` value you asked for yourself; the values live in `docs/reference/INSTANCE-ALLOCATION-MODES.md` §5) | YOU (one of the three exits below) | before your terminal status |
| `INSTANCE_HANDLE` forwarded in your brief | NEVER you | the provisioning orchestrator, at end of run |
| Instance you provisioned AND forwarded to children (you are the run-level owner) | YOU | after every child returned (spawner barrier R1) and the run verdict is final - then before your own DONE |
| `mode_hint: path-incremental` EXCLUSIVE lease | the owning skill, via release-lease (operation E) | at path completion - never between steps |
| `persist: shared-running` | NO single consumer, ever | allocator GC only (dead-pid, immediately; TTL, only when liveness cannot be verified at all - see `docs/reference/INSTANCE-ALLOCATION-RECLAIM.md` §7) |
| A lease you parked (`allocator.py park`) | YOU, or whoever resumes it | at your terminal status the park itself is the teardown; the lease is then reclaimed by its own `park_ttl_s` budget, or released after a `resume` |

### The three exits

A live, self-provisioned, non-shared lease is cleared by exactly one of THREE exits.
This list is the SSOT for that set: the `SubagentStop` hook names the same three in the block it
emits, and a guard asserts the two sets are equal.

- **`release`** - stops the server's whole process group, then drops the DB for `drop_on_release`
  leases. Use it when a database YOU acquired is finished with: "finished with" is a fact about
  your own lease, never a licence over anyone else's.
- **`park`** - stops the SAME process group, so it frees the RAM exactly as `release` does, but
  KEEPS the database, filestore and ports under a park budget for a later `resume`. Use it when
  the instance is done for now and the database is still wanted. NOT an exemption: park holds
  DISK, never MEMORY, and a parked lease has no running process to leave behind.
- **`handoff`** - forward `INSTANCE_HANDLE` to a NAMED catcher in your continuation `next.inputs`
  (T4). The only exit that leaves the server RUNNING, and the only one needing a named owner.

Did YOU acquire this lease? If not, NONE of the three is yours to run - leave it and name it in
your report. If yes, choose on a fact about the DATABASE, not on convenience: still wanted ->
park; finished with -> release; wanted by a named next step, still running -> handoff.

An ephemeral `--stop-after-init` build self-terminates its process, but the LEASE (db + port
reservation) is still yours - release it so `drop_on_release` reclaims the DB.

A mechanical backstop below this contract reaps an owner that died before releasing: allocator
GC, SessionEnd gc, and gc-on-acquire - immediately when its pid is dead, or (only when liveness
cannot be verified at all) once the allocator's TTL (default 3600s) lapses with no `heartbeat`. A same-host
owner whose pid is verified alive is NEVER TTL-reaped, by design. The backstop is a safety net,
not an alternative - you still release; the net catches crashes, not laziness.

## T2 - Browser: close what you opened

- **Close pages, never the server.** The browser MCP servers (chrome-devtools, playwright,
  pagecast; headed and headless variants) are deliberately long-lived shared processes. Your
  teardown scope is INSIDE the server: pages, tabs, contexts, recordings, traces. NEVER kill,
  restart, or "clean up" the MCP server process itself. Closing the current/last page is safe by
  design - a subsequent navigate re-creates a page.
- **The close calls, by family:** chrome-devtools -> `close_page` (per page you opened; use
  `list_pages` to find strays you created); playwright -> `browser_close` (plus
  `browser_stop_video` / `browser_stop_tracing` if you started a video or trace); pagecast ->
  `stop_recording` (by its tool name, not just "stop the recorder" in prose).
- **Clean up as you go, not just at the end.** Reuse ONE page across a sweep instead of opening a
  page per screen/breakpoint/role; close an extra page/context when that step ends. Before your
  terminal status, close every page `list_pages` reports that YOU created.
- **Single-flight (exclusivity) - PER FAMILY.** At most ONE browser-driving agent runs at a
  time **per MCP family** (chrome-devtools, playwright, pagecast; each headed/headless variant
  is its own family - 6 total). Two drivers on the SAME family share one Chromium process
  (shared DOM/session) and corrupt each other's evidence - that is the hard exclusivity, and
  orchestrators dispatch same-family browser agents as exclusive, serial steps, never a
  parallel fan-out. Across DISTINCT families, parallel drivers ARE allowed - each family is a
  distinct stdio process with its own `--isolated` Chromium profile. The cross-family ceiling is
  the pool cap `W` defined in `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
  § Browser exclusivity (that file is the SSOT for the exact figure), subject to the operator's
  RAM budget (no machinery enforces it - `resource_limits.sh` caps only odoo-bin's memory, the
  allocator counts Postgres/ports, not Chromium; `W` IS the guardrail); state-mutating (CRUD)
  drives stay at most 2 simultaneous regardless of family mix.
- **Headed exception (human-watch).** When the human explicitly asked to WATCH, you may leave the
  watched page open at the human's request - state that you did, and name the human as the owner
  who closes it (a T4 named-catcher handoff). Default (nobody asked to watch): close, headed or
  not.
- **Disambiguations.** "Pick one server family per run and stay on it" governs FAMILY choice, not
  keeping pages open. Saved `storageState-<role>.json` files survive page close - reuse the FILE
  to skip re-login, never an open page.

## T3 - Instance: release what you provisioned

- **Route the teardown; never hand-roll it.** Release through the same path you acquired:
  `Skill(odoo-instance)` / `allocator.py release <token> --run-id <id>`. Release is now
  teardown-complete for a listening instance: the allocator stops the server's process group
  FIRST (SIGTERM, bounded wait, group SIGKILL), THEN drops the DB for `drop_on_release` leases.
  You never signal processes or run `dropdb` yourself, and you never hardcode a series' flags -
  `odoo-instance-ops` resolves the per-version CLI at runtime via OSM `cli_help`.
- **Long-lived holders heartbeat.** Long-lived holders (path-incremental, an acceptance run
  across phases): call `allocator.py heartbeat <token>` between phases - it is what protects you
  on the residual case the allocator cannot verify liveness for at all (a different host, or no
  pid recorded), governed by the TTL backstop (default 3600s).
- **Per-mode rule is T1's matrix** - read it there; it is deliberately not copied here.
- **Park is routed, never hand-rolled, exactly like release.** `allocator.py park <token>` (T1's
  second exit); to come back, `Skill(odoo-instance)` finds it via `allocator.py query --series
  <X.Y> --state parked` and resumes it. The shared render target is never parkable. Full rules:
  `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` §5 +
  `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-RECLAIM.md` §7.

## T4 - Failure and handoff paths

- **BLOCKED / NEEDS_CONTEXT do not waive teardown.** Before emitting any terminal status -
  including after an error, a failed oracle, or a REJECTED verdict - close your pages and
  release your self-provisioned instances. Your captured evidence is on disk; the open page or
  running server is not evidence, it is a leak.
- **The only exception is an EXPLICIT, NAMED handoff, and it rides ANY status** - T0(b) reads the
  forwarded handle, never the status word (`NEEDS_NEXT` is the usual carrier, not a requirement).
  You may leave a self-provisioned instance leased ONLY when your continuation forwards
  `INSTANCE_HANDLE` (incl. `lease_token`, `run_id`) in `next.inputs`, naming the catcher that
  needs the live state. An unnamed "forward the token for later release" is not a handoff - it is
  the leak this contract exists to close. Browser pages get no such exception, with one narrow
  carve-out: T2's headed human-watch case, which is itself a NAMED handoff - outside that one
  case, close pages even when handing off.
- **If teardown itself fails** (release errors, a process refuses to die, or the HARNESS REFUSES
  the give-back before it runs - not one of this plugin's exit codes, so do not translate it into
  one), you are BLOCKED, not DONE, and a bare BLOCKED is not enough: quote the refusal AND take
  the named handoff above, with your **dispatching caller** as catcher. It outlives you and can
  release what you cannot, and naming it needs no tool, no permission and no live process - so
  being unable to RELEASE never leaves you unable to hand over. Never re-issue or reword a refused
  give-back: the refusal is your answer, and an obfuscated retry is itself a blocked action.
  `permission-denied-teardown.sh` says this at refusal time.

## Why browsers and instances are enforced differently

- Browser sessions are session-bounded and advisory: pages die with the session's shared MCP
  server process, so a stray page cannot outlive your run - enforcement nudges, it does not
  block.
- Odoo instances are detached OS processes: a leased instance is a ledger entry that outlives
  your run if you crash, so enforcement blocks on the ledger's provable truth, never on a
  transcript guess.
- Do not equalize them in either direction - tightening browsers to a ledger-block or loosening
  instances to advisory-only breaks this design; the asymmetry is intentional, not an oversight.
