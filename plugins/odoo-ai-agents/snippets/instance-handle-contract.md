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

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, which owns port allocation
and leasing (the `ALLOC_*` outputs, including `ALLOC_DB_PORT` and `ALLOC_RUN_ID`; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`). It captures that skill's canonical
`instance-ops` output block ONCE and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent that receives an `INSTANCE_HANDLE` MUST use it for every odoo-bin operation
(confirm-by-toggle, `-i` / `-u`, `--test-enable`) and MUST NOT build its own `db_name`, port, or
`addons_path`. Self-provisioning when a handle was already passed causes port `8069` / DB-name
collisions when multiple agents run concurrently. When NO handle is passed (a run that never
provisioned one), the agent self-provisions by invoking `Skill(odoo-instance)` in its own context -
which acquires its own isolated ephemeral instance UNDER the instance HARD RULES (`en_US` union, Viindoo
`to_base`, lint-module install, per-version `cli_help` grounding) per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance allocation - rather than
a bare `allocator.py` call, which would bypass those rules. A provided handle always wins (consume,
never re-provision).

## Lifecycle

One instance per run. The orchestrator releases / drops it via `lease_token` (passing `run_id` as
`--run-id` alongside it) at the end of the run; downstream agents never release a handle they did
not provision.
