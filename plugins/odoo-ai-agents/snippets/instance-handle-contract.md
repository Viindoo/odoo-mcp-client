<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Referenced by odoo-git-rebase, odoo-coding,
     odoo-instance, and odoo-instance-ops. Edit here only; consumers point at
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
- `demo` - whether demo data is loaded (`true`/`false`)
- `languages_loaded` - the locales confirmed active in `res.lang` (always includes `en_US`)
- `log_path` - the persistent build/test log path
- `lease_token` - the lease that owns the instance lifecycle
- `run_id` - the run that owns the lease
- `server_pid` (optional) - the server's process-group id; null for a build that does not listen

Field names are the producer's SSOT: `odoo-instance-ops`'s `instance-ops` output block, relayed
verbatim by `odoo-instance` - rename in both or neither. `lease_token` and `run_id` come
from `lease_acquire`'s `instance_handle`; `log_path` and `server_pid` from `instance_build` /
`instance_serve`.

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, captures its canonical
`instance-ops` output block ONCE, and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent receiving an `INSTANCE_HANDLE` MUST use it for every Odoo operation (confirm-by-toggle,
`init` / `update`, `test`) by passing its `lease_token` to `instance_build` / `instance_serve`, and
MUST NOT call `lease_acquire`, invent a `db_name` or port, or re-derive `addons_path`. Only an
isolated lease (`lease_acquire` mode `ephemeral`: its own database and pooled ports, owned by its
`run_id`) prevents a collision outright; a `shared` lease is deliberately one database and port for
many readers.
When NO handle is passed, the agent self-provisions by invoking `Skill(odoo-instance)` in its own
context (an `ephemeral` lease by default; a listening one when the process must stay up), applying
the instance HARD RULES (`en_US` union, Viindoo `--load`, lint-module install, per-version
`cli_help` grounding) per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance
allocation. A provided handle always wins (consume, never re-provision) - with exactly ONE
exception, § Worktree-addons carve-out below. (`odoo-instance` may lease a test port on the
handle's database; it never releases or parks the handle's lease.)

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
stale. `lease_acquire`'s worktree refusal never inspects the CONTENT of an `addons_path` you pass,
so a wrong-but-present `addons_path` is caught only by this assertion.

## Prefork (`--workers>0`) needs a second port

The default THREADED mode (`workers=0`) multiplexes the longpolling/realtime bus over the single
`http_port` - no second port needed. Any use of prefork (`--workers>0`) MUST acquire with `ports` 2;
`instance_serve` derives both conf keys from the series. Prefork stays OPT-IN, never default.

## Lifecycle

One instance per run. Who releases it, when, and what "released" means is owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1 - edit the lifecycle rule there,
not here. `lease_release` / `lease_park` take the handle's `lease_token` + `run_id`.
