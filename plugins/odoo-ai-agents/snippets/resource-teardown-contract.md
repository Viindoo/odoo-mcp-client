# Resource teardown contract (close and release before a terminal status)

Two resource classes, two verb sets, never mixed: you CLOSE a browser page, tab or context and
STOP a recording or trace; you RELEASE, PARK or hand off an Odoo instance lease. Closing a page
never touches a lease, and a "never release the lease" instruction never excuses an open page.

## T0 - The gate

You do not emit a terminal status - `DONE`, `BLOCKED`, `NEEDS_CONTEXT`, `NEEDS_NEXT` alike - while:

(a) a page, tab, context, recording or trace you drove this dispatch is still open or running; or
(b) a lease you obtained this dispatch (`lease_acquire`, `lease_adopt`, or an `instance_serve` by
    series that leased it for you), or one a child you launched handed back up to you, is still
    live: neither released, nor parked, nor handed off by name (T1 § The three exits).

(b) is enforced: a hook refuses your turn end, whatever its status, while such a lease is live
and not forwarded. A turn end that only waits for a teammate you launched
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R0 move 3) keeps the lease; your final report
stays gated. (a) is reminded, not enforced; it binds you the same.

## T1 - Ownership: who tears down what

Teardown belongs to whoever acquired the resource, never to whoever merely used it. A named
handoff (T4) moves that ownership to the catcher; forwarding a handle down to a consumer does not.

| How you hold it | Who tears it down | When |
|---|---|---|
| A page, context or recording you drove this dispatch - opened, or reused by navigating it | you (T2) | as you go, and before your terminal status |
| A lease you obtained yourself, a test-build lease on a forwarded handle's database included | you, by one of the three exits | before your terminal status |
| An `INSTANCE_HANDLE` forwarded down to you in your brief | never you | its acquirer |
| A lease acquired for your run and handed back up to you, or one you acquired and forwarded to children | you, the run-level owner | after every child returned and the run's verdict is final |
| A `MODE_HINT: path-incremental` lease | the skill that drives the path, inline | at the end of the path, never between steps |
| A `shared` lease (a multi-reader render server) | no single consumer; its launcher only on the user's explicit request | `lease_gc` once its server is dead |
| A lease you parked | you, or whoever resumes it by `lease_adopt` + `instance_serve` | the park is your teardown; then the adopter owns it |

Release or park only what you own, with the `run_id` you were given. A handle that reached you
down is never yours to release or park, although its token would let the call succeed: leave it
and name it in your report.

### The three exits

- **`release`** (`lease_release`): stops the server and drops the database of an `ephemeral` lease.
  For a database you are finished with.
- **`park`** (`lease_park`): stops the server and keeps the database, filestore and ports for a
  later resume. For a database still wanted.
- **`handoff`**: forward the `INSTANCE_HANDLE` to a named catcher in `next.inputs` (T4). The only
  exit that leaves the server running.

Choose on a fact about the database, not on convenience. A build that never listened still holds
a lease: release it.

## T2 - Browser: close what you drove

- **Close pages, never the server.** You never kill or restart a browser MCP server.
- **By family, at the end:** chrome-devtools - `close_page` each page you drove; the last open
  page is navigated to `about:blank` instead. playwright - `browser_close` (and stop a video or
  trace you started). pagecast - `stop_recording` for every session you started.
- **As you go:** reuse one page across a sweep instead of one per screen, breakpoint or role.
- **One driver per family at a time.** Each family (chrome-devtools, playwright, pagecast; headed
  and headless variants each count) carries at most one browser-driving agent; distinct families
  may run in parallel up to the cap of
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity, and at most two
  state-changing drives run at once.
- **A page the human asked to watch** may stay open: say so, and name the human as the owner who
  closes it.

## T3 - Instance: release what you provisioned

- Teardown goes through the lease tools: never signal a process, kill an `odoo-bin` or drop a
  database yourself. Tools unavailable: the allocator CLI of
  `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md`.
- A refused release is not done: follow the remedy of its error code; until it succeeds, T4
  applies.
- Resume a parked lease, never rebuild beside it: its token (from the handle, else `lease_find`
  with your `run_id`), `lease_adopt`, then `instance_serve`.

## T4 - Failure and handoff

- A failure does not waive teardown: after an error, a failed oracle or a rejected verdict, close
  your pages and release or park your leases before the terminal status.
- The one exception rides any status: a lease you own may stay running only when your
  continuation forwards its `INSTANCE_HANDLE` (with `lease_token` and `run_id`) in `next.inputs`
  to a named catcher that needs the live state. "Forwarded for later release" names nobody and is
  not a handoff. Pages get no such exception, except the watched page of T2.
- When teardown itself fails - the release errors, a process will not die, or the harness denies
  the call - you are `BLOCKED`: quote the refusal and take the named handoff with your caller as
  catcher. Never re-issue or reword a refused give-back.
