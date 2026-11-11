# Instance Handle Contract

`INSTANCE_HANDLE` describes the ONE live Odoo instance a multi-agent run shares. Copy every field
from the latest `instance_handle` a tool returned (after a build, the final `job_wait`'s):

- `db_name`; `http_port` (null for a build that does not listen); `gevent_port` (the second port
  of a prefork build, else null); `db_port` (the Postgres port; empty when the lease omits it,
  never assumed)
- `addons_path` (comma-separated, Odoo's own format); `venv_python` (the interpreter of the
  target series)
- `demo` (whether the DATABASE holds demo data; `null` = not known); `languages_loaded`;
  `facts_source` - `database` when those two were read from it, `leases` when only the builds
  its leases recorded could answer
- `log_path`; `lease_token` (the lease that owns the instance); `run_id` (the run that owns the
  lease)
- optional: `server_pid` (the server's process group; null when nothing listens); `ui_user` (the
  account a browser consumer acts as on a demo build; never asked for, never sought on disk)

## Provision once, forward everywhere

The orchestrator provisions one instance through the `odoo-instance` skill and forwards its handle
as `INSTANCE_HANDLE:` in every downstream brief that touches code or tests.

## Downstream agents consume, never self-provision

A receiver uses the handle for every Odoo operation: `init`, `update` and serve by passing its
`lease_token` to `instance_build` / `instance_serve`; a test run per § Test build on a forwarded
handle. It never invents a `db_name` or a port and never re-derives `addons_path`. With no handle
it provisions through `Skill(odoo-instance)` in its own context (an `ephemeral` lease by default,
a listening one when the process must stay up;
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance allocation);
`odoo-test-writer` never does (no handle -> `NEEDS_NEXT`). A worker never waits for a resource
another session owns: it gets its own port, database, config and log.

### Worktree-addons carve-out

A verification instance loads the tree the work was written in. One exception lets a receiver
provision although its launcher could have forwarded a handle; the DISPATCHER declares it, a
receiver never infers it:

- **A node's coder** gets `SELF_PROVISION: worktree-addons` instead of a handle, never both: one
  instance for the node's whole module set, provisioned through `Skill(odoo-instance)` with
  `WORKTREE_PATH`, released by the coder before its terminal status.
- **Every other receiver** gets a handle whose lease the dispatcher acquired with `cwd` = the one
  target worktree and an `addons_path` covering it, stated in the brief as
  `ADDONS_PATH: <comma-joined dirs>`.

The exception covers the provenance of the addons and nothing else: no invented `db_name` or
port, no `addons_path` re-derived from the catalog, no provisioning to change the series, to add
a module or because a handle looks stale.

### Addons coverage assertion

Before an Odoo run that decides a verdict (a test, an i18n export, a doc capture), assert that the
resolved addons list holds a directory `D` with `D/<module>/__manifest__.py` AND `D` inside the
tree you were told to work in (`WORKTREE_PATH` when named, else the catalog tree; compare
`pwd -P`-normalized absolute paths, a prefix match suffices). A miss:
`BLOCKED(verification addons-path does not cover <module> under <WORKTREE_PATH>)`. For a served
instance assert it against `instance_serve`'s `served_addons_path`.

## Test build on a forwarded handle

A consumer that runs tests on a forwarded handle (`odoo-test-writer`'s break-checks, a verify
run) judges by the handle's port. No server listens on it: build on the handle's own
`lease_token`. A server listens: take ONE small lease of your own on the handle's database
(`lease_acquire` mode `exclusive`, `no_create` true, `ports` 1, the handle's `db_name`,
`addons_path`, series and `run_id`, `cwd` = your `WORKTREE_PATH`), run your test builds on it and
`lease_release` it before you return, on every exit. Never release, park or adopt the handle's
lease.

A database a browser has driven (an acceptance, a capture, a debug session) carries no test
verdict: the UI moved records out of the state the tests expect. A suite or a break-check that
decides a verdict there runs on an `ephemeral` lease of its own; a red seen on a driven database
is re-run on a clean one before any code or data is touched.

Evidence comes from the installed build: a capture, an acceptance, a review or a recording never
asks `instance_serve` for a developer server, and one whose serve result says
`developer_server: true` (it restarts on a saved file and reads views from files) is parked and
served again by its owner before anything is captured or ruled on it.

## One build or export per database

Workers sharing one database never build or export on it at the same time. When a tool reports
the database busy, `job_wait` the job it names, then retry. Never release or park a lease you do
not own to free the database.

A job you started (`instance_build`, `instance_i18n_export`) is collected in the turn that
started it: `job_wait` until its result is not `timeout`. A finished job notifies no one, the
main conversation included. A turn that must end first says the job is still running and that
nothing will wake the session; a dispatched agent reports `BLOCKED` with the `job_id`. A gate
stops such a turn end once.

## Prefork (`--workers>0`) needs a second port

Threaded mode needs one port; prefork acquires with `ports` 2 and stays opt-in.

## Lifecycle

One instance per run, released per `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
T1; `lease_release` and `lease_park` take the handle's `lease_token` and `run_id`.

**Hand-on between consumers.** A caller that sequences several consumers of one build names the
next one to the current one as `HAND_ON: <skill>`: that consumer keeps the lease running and
returns the handle in its Continuation `next.inputs`; the caller forwards it when the build covers
the next consumer (series, demo, languages, addons path, auto-install shape), else provisions
anew, and releases the handle after the last consumer. No consumer releases a handle it was
forwarded or asked to hand on.
