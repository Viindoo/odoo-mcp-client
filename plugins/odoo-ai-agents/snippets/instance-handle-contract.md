<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Referenced by odoo-git-rebase, odoo-coding,
     odoo-instance, and odoo-instance-ops. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md. -->

# Instance Handle Contract

`INSTANCE_HANDLE` is the canonical, run-scoped descriptor of the ONE live Odoo instance a
multi-agent run shares. It carries exactly:

- `db_name` - the database the run operates against
- `http_port` - the bound HTTP port (null for `--stop-after-init` runs)
- `db_port` - the Postgres port the instance's cluster is bound to (empty when the catalog/lease
  omits it - never assume `5432`)
- `addons_path` - the colon-separated addons path
- `venv` - the Python interpreter / venv for the target series
- `lease_token` - the allocator lease that owns the instance lifecycle
- `run_id` - the run/session id that owns the lease, forwarded back at release as `--run-id`
- `server_pid` (optional) - the server's process-group id under setsid, when forwarded; null for
  `--stop-after-init` builds, which self-terminate

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, which owns port allocation
and leasing (the `ALLOC_*` outputs, including `ALLOC_DB_PORT` and `ALLOC_RUN_ID`; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`). It captures that skill's canonical
`instance-ops` output block ONCE and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent that receives an `INSTANCE_HANDLE` MUST use it for every odoo-bin operation
(confirm-by-toggle, `-i` / `-u`, `--test-enable`) and MUST NOT build its own `db_name`, port, or
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
never re-provision).

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
