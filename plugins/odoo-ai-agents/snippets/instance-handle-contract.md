<!-- SSOT snippet. The INSTANCE_HANDLE contract: one provisioned instance per run,
     forwarded to every downstream brief. Referenced by odoo-git-rebase, odoo-coding,
     odoo-instance, and odoo-instance-ops. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md. -->

# Instance Handle Contract

`INSTANCE_HANDLE` is the canonical, run-scoped descriptor of the ONE live Odoo instance a
multi-agent run shares. It carries exactly:

- `db_name` - the database the run operates against
- `http_port` - the bound HTTP port (null for `--stop-after-init` runs)
- `gevent_port` - the second (longpolling/gevent) port when a prefork/`--workers>0` build
  requested one via `--ports 2`; null otherwise
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
  `--stop-after-init` builds (self-terminate)

Field names are the producer's SSOT: `agents/odoo-instance-ops.md`'s canonical `instance-ops`
output block. `skills/odoo-instance/SKILL.md` relays that block verbatim - do not rename a field
here without updating both.

## Provision once, forward everywhere

The orchestrator provisions ONE instance via the `odoo-instance` skill, which owns port allocation
and leasing (the `ALLOC_*` outputs, incl. `ALLOC_DB_PORT`/`ALLOC_RUN_ID`; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md` § 6), captures its canonical `instance-ops`
output block ONCE, and forwards it as an `INSTANCE_HANDLE:` field in EVERY downstream brief that
touches code or tests (coder, test-author, verify, debug).

## Downstream agents consume, never self-provision

An agent receiving an `INSTANCE_HANDLE` MUST use it for every odoo-bin operation
(confirm-by-toggle, `-i` / `-u`, `--test-enable`) and MUST NOT build its own `db_name`, port, or
`addons_path`. Going through `odoo-instance` does NOT by itself solve collision: the SHARED render
target is DELIBERATELY one db+port for many readers, so only an ISOLATED lease (its own db + an
allocator-issued pooled port + an owned lease keyed on `run_id`) prevents a collision outright; a
shared instance MUST still be owner-stamped (`run_id`) so a foreign session cannot bare-drop it.
Which `persist:` value gives you which - and the parked state a suspended instance sits in - is
spelled out in ONE place, never restated here:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` §5
(+ `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-GUARDS.md` §6.3 for the ownership guard).
When NO handle is passed, the agent self-provisions by invoking `Skill(odoo-instance)` in its own
context, declaring the `persist:` value that matches its need per that SSOT (a throwaway build by
default; a listening one when the process must stay up), applying the instance HARD RULES (`en_US`
union, Viindoo `to_base`, lint-module install, per-version
`cli_help` grounding) per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Odoo instance
allocation - never a bare `allocator.py` call. A provided handle always wins (consume, never
re-provision) - with exactly ONE exception, § Worktree-addons carve-out below.

**Isolation, not exclusivity.** Never instruct a worker to wait for a resource another session
owns. Give it a distinct port, database, config and log, and let it run.

### Worktree-addons carve-out (the ONE sanctioned self-provision under a handle)

A verification instance must load the tree the work was written in. The shared catalog lease carries
ONE `addons_path`, pointed at the principal checkout by default, so it does not automatically cover a
node's own worktree. Exactly one rule releases the paragraph above, DISPATCHER-declared, never
receiver-inferred:

- **Dispatcher, node coding fan-out.** When dispatching a node's coordinator against its own
  worktree, do NOT forward an `INSTANCE_HANDLE`; instead set the brief field
  `SELF_PROVISION: worktree-addons`. A node gets ONE instance for its whole module set - never one
  instance per module. Never send both: a brief carrying a handle AND the token is malformed, and
  the receiver treats it as the handle case, returning `NEEDS_CONTEXT`.
- **Dispatcher, every other receiver.** Acquire the shared lease with `--addons-path-override`
  covering the ONE target worktree and state the resulting value in the brief as
  `ADDONS_PATH: <comma-joined dirs>`.
- **Receiver.** `SELF_PROVISION: worktree-addons` present (and no handle) -> self-provision as
  authorized. `INSTANCE_HANDLE` present -> use it, after the coverage assertion below.
  Never self-provision on your own judgment.
- **The authorized self-provision runs `odoo-instance` INLINE, in your own context** - never via
  the `odoo-instance-ops` agent. This is a MUST: the SubagentStop teardown gate correlates a live
  lease to YOUR dispatch by finding the `allocator.py acquire` call in YOUR transcript, so
  provisioning through a sub-agent makes your own leak invisible to it
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1). What you acquire here you
  release before your terminal status.

### Addons coverage assertion (ONE rule, every consumer points here)

Before any `odoo-bin` run that decides a verdict (`--test-enable`, an i18n export, a doc capture),
assert the resolved addons list contains a directory `D` such that `D/<module>/__manifest__.py`
exists AND `D` is inside the tree you were told to work in (`WORKTREE_PATH` when named, else the
catalog tree; compare `pwd -P`-normalized absolute paths, a prefix match is sufficient). On a miss,
STOP with `BLOCKED(verification addons-path does not cover <module> under <WORKTREE_PATH> - a green
result here would prove nothing)` - never run the operation "to see what happens".

This section authorizes worktree-addons provenance and NOTHING else. A receiver still MUST NOT invent
a `db_name` or a port (the allocator mints both), MUST NOT re-derive `addons_path` from the catalog,
and MUST NOT self-provision to change the series, add a module, or because a handle looks stale.

**Structural backstop (belt-and-braces, not the sole protection).** `scripts/lib/allocator.py`'s
`_addons_path_worktree_mismatch` guard (`cmd_acquire`) independently REFUSES (exit 5) the common
case - a linked-worktree cwd acquiring against a mismatched catalog `addons_path` entry with no
`--addons-path-override` (`readonly` mode is exempt). It never inspects an override's CONTENT, so
once ANY override is present it trusts it unconditionally. For that residual shape - a wrong
override, or a dropped `SELF_PROVISION: worktree-addons` while still forwarding some override -
this POLICY step is the SOLE protection. Do not restate the guard's mechanics elsewhere - point
back here.

## Prefork (`--workers>0`) needs a second port

The default THREADED mode (`workers=0`, what `odoo-instance` provisions unless told otherwise)
multiplexes the longpolling/realtime bus over the single `http_port` - no second port needed. Any
use of prefork (`--workers>0`) MUST also request `--ports 2` at acquire time and forward the resolved
gevent/longpolling port + its conf key (`gevent_port`/`longpolling_port`, per OSM `cli_help`) to the
spin-up step; gevent/prefork stays OPT-IN, never default.

## Lifecycle

One instance per run. Who releases it, when, and what "released" means (stop the process group,
then drop the DB) is owned by `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
T1/T3 - edit the lifecycle rule there, not here. The handle fields forwarded at release are
`lease_token` + `run_id` (as `--run-id`), per the field list above.
