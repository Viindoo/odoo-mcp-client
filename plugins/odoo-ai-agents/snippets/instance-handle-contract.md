<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Referenced by odoo-git-rebase, odoo-coding,
     odoo-instance, and odoo-instance-ops. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md. -->

# Instance Handle Contract

`INSTANCE_HANDLE` is the canonical, run-scoped descriptor of the ONE live Odoo instance a
multi-agent run shares. It carries exactly:

- `db_name` - the database the run operates against
- `http_port` - the bound HTTP port (null for `--stop-after-init` runs)
- `addons_path` - the colon-separated addons path
- `venv` - the Python interpreter / venv for the target series
- `lease_token` - the allocator lease that owns the instance lifecycle

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, which owns port allocation
and leasing (the `ALLOC_*` outputs; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md`). It captures that skill's canonical
`instance-ops` output block ONCE and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream
brief that touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent that receives an `INSTANCE_HANDLE` MUST use it for every odoo-bin operation
(confirm-by-toggle, `-i` / `-u`, `--test-enable`) and MUST NOT build its own `db_name`, port, or
`addons_path`. Self-provisioning when a handle was already passed causes port `8069` / DB-name
collisions when multiple agents run concurrently. When NO handle is passed (a run that never
provisioned one), the agent falls back to acquiring its own isolated ephemeral instance per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance allocation. A provided
handle always wins.

## Lifecycle

One instance per run. The orchestrator releases / drops it via `lease_token` at the end of the run;
downstream agents never release a handle they did not provision.
