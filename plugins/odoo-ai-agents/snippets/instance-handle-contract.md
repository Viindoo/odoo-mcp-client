<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md. -->

# Instance Handle Contract

`INSTANCE_HANDLE` is the canonical, run-scoped descriptor of the ONE live Odoo instance a
multi-agent run shares. It carries exactly:

- `db_name` - the database the run operates against
- `http_port` - the bound HTTP port (null for a build that does not listen)
- `gevent_port` - the second (longpolling/gevent) port of a prefork build; null otherwise
- `db_port` - the Postgres port the instance's cluster is bound to (empty when the lease omits
  it - never assume `5432`)
- `addons_path` - the comma-separated addons path (Odoo's own `--addons-path` format)
- `venv_python` - the Python interpreter of the target series
- `demo` - whether the DATABASE holds demo data (`null` = not known)
- `languages_loaded` - the languages active in the DATABASE (every tool build loads `en_US`)
- `facts_source` - who answered `demo` / `languages_loaded`: `database` (read from it) or
  `leases` (it could not be read, so the builds its leases recorded)
- `log_path` - the persistent build/test log path
- `lease_token` - the lease that owns the instance lifecycle
- `run_id` - the run that owns the lease
- `server_pid` (optional) - the server's process-group id; null for a build that does not listen

Field names are the producer's SSOT: `odoo-instance-ops`'s `instance-ops` output block, relayed
verbatim by `odoo-instance` - rename in both or neither. Copy every field from the latest
`instance_handle` a tool returned (after a build, the final `job_wait`'s). `demo` and
`languages_loaded` are facts of the database, whichever lease built it; the tools enforce them
from the database too.

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, captures its canonical
`instance-ops` output block ONCE, and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent receiving an `INSTANCE_HANDLE` MUST use it for every Odoo operation: `init` / `update` /
serve by passing its `lease_token` to `instance_build` / `instance_serve`; a test run per § Test
build on a forwarded handle. It never invents a `db_name` or port and never re-derives
`addons_path`.
When NO handle is passed, the agent self-provisions by invoking `Skill(odoo-instance)` in its own
context (an `ephemeral` lease by default; a listening one when the process must stay up), applying
the instance HARD RULES per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo
instance allocation; `odoo-test-writer` never self-provisions (no handle -> `NEEDS_NEXT`,
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § The break-check). A provided
handle always wins (consume, never re-provision) - with exactly ONE exception, § Worktree-addons
carve-out below.

**Isolation, not exclusivity.** Never instruct a worker to wait for a resource another session
owns; give it its own port, database, config and log.

### Worktree-addons carve-out (the ONE sanctioned self-provision under a handle)

A verification instance must load the tree the work was written in. A catalog-default lease carries
the catalog's `addons_path`, which points at the principal checkout, so it does not cover a node's
own worktree. Exactly one rule releases the paragraph above, DISPATCHER-declared, never
receiver-inferred:

- **Dispatcher, node coding fan-out.** When dispatching a node's coordinator against its own
  worktree, do NOT forward an `INSTANCE_HANDLE`; instead set the brief field
  `SELF_PROVISION: worktree-addons`. A node gets ONE instance for its whole module set - never one
  instance per module. Never send both: a brief carrying a handle AND the token is malformed, and
  the receiver treats it as the handle case, returning `NEEDS_CONTEXT`.
- **Dispatcher, every other receiver.** Acquire the lease with `cwd` = the ONE target worktree and
  `addons_path` covering it, and state the resulting value in the brief as
  `ADDONS_PATH: <comma-joined dirs>`.
- **Receiver.** `SELF_PROVISION: worktree-addons` present (and no handle) -> self-provision as
  authorized. `INSTANCE_HANDLE` present -> use it, after the coverage assertion below.
  Never self-provision on your own judgment.
- **The authorized self-provision runs `odoo-instance` INLINE, in your own context** - never via
  the `odoo-instance-ops` agent. The SubagentStop teardown gate checks only the leases YOUR own
  tool calls obtained, so provisioning through a sub-agent makes your own leak invisible to it
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1). Pass `cwd` = your worktree
  and `addons_path` naming it; `lease_acquire` refuses a worktree `cwd` without one
  (`ADDONS_PATH_WORKTREE_MISMATCH`). What you acquire here you release before your terminal status.

### Addons coverage assertion (ONE rule, every consumer points here)

Before any Odoo run that decides a verdict (`test`, an i18n export, a doc capture), assert the
resolved addons list contains a directory `D` such that `D/<module>/__manifest__.py` exists AND `D`
is inside the tree you were told to work in (`WORKTREE_PATH` when named, else the catalog tree;
compare `pwd -P`-normalized absolute paths, a prefix match is sufficient). On a miss, STOP with
`BLOCKED(verification addons-path does not cover <module> under <WORKTREE_PATH> - a green result
here would prove nothing)` - never run the operation "to see what happens". For a served instance,
assert it against `instance_serve`'s `served_addons_path`.

This section authorizes worktree-addons provenance and NOTHING else. A receiver still MUST NOT invent
a `db_name` or a port (`lease_acquire` mints both), MUST NOT re-derive `addons_path` from the
catalog, and MUST NOT self-provision to change the series, add a module, or because a handle looks
stale.

## Test build on a forwarded handle (ONE rule, every consumer points here)

A test build binds an HTTP port on every series, and the handle's port may belong to its running
server. A consumer that RUNS tests on a forwarded `INSTANCE_HANDLE` (`odoo-test-writer`'s baseline
and break-check runs, any verify run on a forwarded handle) therefore takes ONE lease of its own on
the handle's database and holds it across its runs:

1. `lease_acquire` - mode `exclusive`, `no_create` true, `ports` 1, with the handle's `db_name`,
   `addons_path`, series and `run_id`, `cwd` = your `WORKTREE_PATH`.
2. Every `instance_build` op `test` (`test_mode` `reuse`) runs on THAT lease's token, never the
   handle's, then `job_wait`. `DATABASE_BUSY` -> `job_wait` the job it names, then retry.
3. `lease_release` that token before you return, on every exit.

Never release, park or adopt the handle's own lease - it stays its owner's - and never provision a
new database. A lease you hold yourself that reserved a port is built on directly.

## One build or export per database (ONE rule, every parallel fan-out points here)

Workers sharing ONE database (one forwarded handle) never build or export on it at the same time.
When a tool reports the database busy, `job_wait` the job it names, then retry the call. Never
release or park a lease you do not own to free the database.

## Prefork (`--workers>0`) needs a second port

The default threaded mode (`workers=0`) needs one port. Prefork (`--workers>0`) MUST acquire with
`ports` 2; `instance_serve` derives both conf keys from the series. Prefork stays OPT-IN.

## Lifecycle

One instance per run. Who releases it, when, and what "released" means is owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1 - edit the lifecycle rule there,
not here. `lease_release` / `lease_park` take the handle's `lease_token` + `run_id`.
