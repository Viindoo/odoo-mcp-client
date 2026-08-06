<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Referenced by odoo-git-rebase, odoo-coding,
     odoo-instance, and odoo-instance-ops. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md. -->

# Instance Handle Contract

`INSTANCE_HANDLE` is the canonical, run-scoped descriptor of the ONE live Odoo instance a
multi-agent run shares. It carries exactly:

- `dbname` - the database the run operates against
- `http_port` - the bound HTTP port (null for `--stop-after-init` runs)
- `gevent_port` - the second (longpolling/gevent) port, when a prefork/`--workers>0` build
  requested one via `--ports 2`; null when only one port was bound
- `db_port` - the Postgres port the instance's cluster is bound to (empty when the catalog/lease
  omits it - never assume `5432`)
- `addons_path` - the comma-separated addons path (Odoo's own `--addons-path`/`addons_path` format)
- `venv_python` - the Python interpreter / venv for the target series
- `demo` - whether demo data is loaded (`true`/`false`)
- `languages_loaded` - the locales confirmed active in `res.lang` (always includes `en_US`)
- `log_path` - the persistent build/test log path, captured verbatim from the script's `LOG_PATH=`
  line
- `lease_token` - the allocator lease that owns the instance lifecycle
- `run_id` - the run/session id that owns the lease, forwarded back at release as `--run-id`
- `server_pid` (optional) - the server's process-group id under setsid, when forwarded; null for
  `--stop-after-init` builds, which self-terminate

Field names are the producer's SSOT: `agents/odoo-instance-ops.md`'s canonical `instance-ops`
output block. `skills/odoo-instance/SKILL.md` relays that block verbatim - do not rename a field
here without updating both.

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, which owns port allocation
and leasing (the `ALLOC_*` outputs, including `ALLOC_DB_PORT` and `ALLOC_RUN_ID`; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`). It captures that skill's canonical
`instance-ops` output block ONCE and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent that receives an `INSTANCE_HANDLE` MUST use it for every odoo-bin operation
(confirm-by-toggle, `-i` / `-u`, `--test-enable`) and MUST NOT build its own `dbname`, port, or
`addons_path`. Collision is NOT solved merely by going through `odoo-instance`: the shared/spinup
path collides on the same declared/`8069` numbers even when every caller carries a handle -
`persist: shared-running` is DELIBERATELY one shared db+port for many readers, by design. Only
`persist: exclusive-running` (unique db + an allocator-issued pooled port + an owned lease, keyed on
`run_id`) prevents a collision outright; a `shared-running` instance stays shared on purpose but
MUST be owner-stamped (`run_id`) so a foreign session cannot bare-drop it (see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md` §5 + §6.3). When NO handle is passed (a
run that never provisioned one), the agent self-provisions by invoking `Skill(odoo-instance)` in its
own context - passing `persist: ephemeral` (default) or `persist: exclusive-running` when the
process must stay listening - which acquires its own isolated instance UNDER the instance HARD RULES
(`en_US` union, Viindoo `to_base`, lint-module install, per-version `cli_help` grounding) per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance allocation - rather than
a bare `allocator.py` call, which would bypass those rules. A provided handle always wins (consume,
never re-provision) - with exactly ONE exception, § Worktree-addons carve-out below.

**Isolation, not exclusivity.** Never instruct a worker to wait for a resource another session
owns. Give it a distinct port, database, config and log, and let it run.

### Worktree-addons carve-out (the ONE sanctioned self-provision under a handle)

A verification instance must load the tree the work was written in. One lease carries ONE
`addons_path`, so N module worktrees cannot share one handle. Exactly one rule releases the paragraph
above, and it is DISPATCHER-declared, never receiver-inferred:

- **Dispatcher, per-module coding fan-out.** When you dispatch a per-module coordinator against its
  own worktree, do NOT forward an `INSTANCE_HANDLE`; instead set the brief field
  `SELF_PROVISION: worktree-addons`. Never send both - a brief carrying a handle AND the token is
  malformed, and the receiver treats it as the handle case and returns `NEEDS_CONTEXT`.
- **Dispatcher, every other receiver.** Acquire the shared lease with `--addons-path-override`
  covering the ONE target worktree and state the resulting value in the brief as
  `ADDONS_PATH: <comma-joined dirs>`.
- **Receiver.** `SELF_PROVISION: worktree-addons` present (and no handle) -> self-provision as
  authorized. `INSTANCE_HANDLE` present -> use it, after the coverage assertion below.
  Never self-provision on your own judgment.
- **The authorized self-provision runs `odoo-instance` INLINE, in your own context** - never by
  launching the `odoo-instance-ops` agent. This is a MUST, not a preference: the SubagentStop
  teardown gate correlates a live lease to YOUR dispatch by finding the `allocator.py acquire`
  call in YOUR transcript, so provisioning through a sub-agent makes your own leak invisible to it
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1). What you acquire here you
  release before your terminal status.

### Addons coverage assertion (ONE rule, every consumer points here)

Before any `odoo-bin` run that decides a verdict (`--test-enable`, an i18n export, a doc capture),
assert the resolved addons list contains a directory `D` such that `D/<module>/__manifest__.py`
exists AND `D` is inside the tree you were told to work in (`WORKTREE_PATH` when your brief names
one, else the catalog tree). Compare `pwd -P`-normalized absolute paths; a prefix match is
sufficient. On a miss, STOP with
`BLOCKED(verification addons-path does not cover <module> under <WORKTREE_PATH> - a green result here
would prove nothing)`. Never run the operation "to see what happens": a suite that loads a different
copy of the module is structurally biased toward green.

This section authorizes worktree-addons provenance and NOTHING else. A receiver still MUST NOT invent
a `dbname` or a port (the allocator mints both), MUST NOT re-derive `addons_path` from the catalog,
and MUST NOT self-provision to change the series, add a module, or because a handle looks stale.

**Structural backstop (belt-and-braces, not the sole protection for every case).**
`scripts/lib/allocator.py`'s `_addons_path_worktree_mismatch` guard (`cmd_acquire`) independently
REFUSES (exit 5) an acquire in `shared`/`ephemeral`/`exclusive` mode whenever the caller's cwd is a
linked git worktree of the SAME repository as a catalog `addons_path` entry at a DIFFERENT
checkout path AND no `--addons-path-override` was passed - the exact "silently defaults to the
principal checkout" shape this carve-out exists to prevent (`readonly` mode is exempt: it never
builds, so there is nothing to mis-verify). The guard's scope stops there: it never inspects an
override's CONTENT, so once ANY `--addons-path-override` is present the guard trusts it
unconditionally and never re-checks it against cwd. For that one residual shape - a dispatcher
that passes an override naming the WRONG worktree, or drops `SELF_PROVISION: worktree-addons` on
one dispatch branch while still forwarding some override - this POLICY step (the dispatcher
correctly computing the override value and setting the flag, per this section) remains the SOLE
protection; no structural guard can verify a caller's true intent from a value it was simply
handed. Do not restate the guard's mechanics elsewhere - point back here.

## Prefork (`--workers>0`) needs a second port

The default THREADED mode (`workers=0`, what `odoo-instance` provisions unless told otherwise)
multiplexes the longpolling/realtime bus over the single `http_port` - no second port is needed. Any
use of prefork (`--workers>0`) MUST also request `--ports 2` at acquire time and forward the resolved
gevent/longpolling port + its conf key (`gevent_port`/`longpolling_port`, per OSM `cli_help`) to the
spin-up step; gevent/prefork stays OPT-IN, never the default.

## Lifecycle

One instance per run. Who releases it, when, and what "released" means (stop the process group,
then drop the DB) is owned by `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
T1/T3 - edit the lifecycle rule there, not here. The handle fields forwarded at release are
`lease_token` + `run_id` (as `--run-id`), per the field list above.
