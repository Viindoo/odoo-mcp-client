# Technical Design - concurrent Odoo instance allocation (user/global, cross-session)

Status: IMPLEMENTED
Audience: plugin maintainers + global contributors, and an agent whose `odoo-local` tools are
unavailable. This is a design contract, not code.
Related: `snippets/instance-resolution.md`, `snippets/venv-resolution.md`,
`snippets/instance-handle-contract.md`, `snippets/state-root-resolution.md`,
`snippets/odoo-bin-resource-limits.md`, `docs/reference/INSTANCE-LIFECYCLE.md`,
`skills/_shared/concurrency-guard.md`, `scripts/lib/allocator.py`, `scripts/lib/session_anchor.py`,
`scripts/lib/instances_io.py`, `scripts/lib/odoo_db.py`, `scripts/mcp/odoo_local_server.py`,
`scripts/setup-steps/40-instance-profile.sh`, `scripts/setup-steps/50-instance-spinup.sh`,
`scripts/setup-steps/55-instance-ops.sh`.

> **Front doors.** The `odoo-instance` skill and the `odoo-instance-ops` agent are the high-level
> interface for instance lifecycle operations (build, drop, init, update, test). Agents reach the
> allocator through the `odoo-local` MCP tools (`lease_*`, `instance_*`, `job_wait`, `catalog_*`);
> the `allocator.py` CLI is the fallback when those tools are unavailable. Both surfaces:
> `INSTANCE-ALLOCATION-API.md` §6. Persistent operation logs are written to
> `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## Parts - what each file owns

Every section below §3 lives in a part file. Cite the PART that owns the fact you need, never
this index.

| File | Sections | Owns |
|------|----------|------|
| `INSTANCE-ALLOCATION-REGISTRY.md` | §4, §4.1, §4.2 | the two-layer catalog/registry architecture, the optional `instances.toml` catalog fields, and the `leases.json` lease-registry format (schema v3) |
| `INSTANCE-ALLOCATION-MODES.md` | §5 | the four access modes, the `persist:` vocabulary SSOT, the P5/P5b/P6 port-uniqueness and bootstrap-race gates, and the opt-in gevent/longpolling port |
| `INSTANCE-ALLOCATION-API.md` | §6, §6.1, §6.6 | the `odoo-local` MCP tool index, the complete `allocator.py` CLI reference (verbs, flags, output keys, the `--format json` envelope, the `ERROR_CODES` table), DB lifecycle ownership (caller-side create, through-Odoo drop), and the acquire refusals 6/7/8/9 |
| `INSTANCE-ALLOCATION-GUARDS.md` | §6.2, §6.3, §6.4, §6.7 | what a build or a lease is REFUSED: config-file isolation, the run_id ownership guard, the addons-path worktree-mismatch guard, and the undroppable-database classification |
| `INSTANCE-ALLOCATION-RECLAIM.md` | §6.5, §7, §8, §9 | liveness and reclamation: the session anchor and the liveness rungs, who may reclaim what (acquire capacity, gc scopes, release, session end), two-phase reclamation and the `reclaiming` marker, the `reap-orphans` DB-side sweep, the failure-mode matrix, and the timing constants |

## 1. Problem & intent

Multiple subagents in one Claude Code session - and multiple sessions on one host - run Odoo
operations concurrently. Some agents only READ a running instance (share is fine); some need an
ISOLATED database (tests, `-i`/`-u`, a throwaway dev server).

The declaration layer alone (`$ODOO_AI_HOME/instances.toml`, one `http_port` and one `db_name` per
instance, read by `instances_io.py`) gives every caller the SAME database and port, so concurrent
`--test-enable`, `-i`/`-u` or spin-up would collide on the port or corrupt each other's database.
OSM reads are safe (the concrete version is passed on every call).

**Intent:** a portable, user/global allocator that hands each concurrent caller either a shared
read-only handle or an isolated (db [+ port]) lease, keeps that lease for exactly as long as the
session that took it is alive, reclaims it once that session is provably gone, and assumes nothing
about this one machine.

## 2. Constraints (non-negotiable)

- **Portable / public / global.** No hardcoded paths, no assumption about this host's Postgres,
  ports, or layout. All runtime state under `$ODOO_AI_HOME` (default `~/.odoo-ai`). The user
  declares their Postgres + venv via `instances.toml` (written by `/odoo-setup`).
- **No live Odoo MCP.** The `mcp__odoo__*` server is out of scope by existing design; the
  allocator coordinates only locally-declared instances. (`odoo-local` is this plugin's own server
  over the allocator, not a live-data server.)
- **Backward compatible.** Existing `instances.toml` files keep parsing; older registry rows are
  read leniently; the read-only resolution path (`instance-resolution.md`) is unchanged for callers
  that only need a URL.
- **POSIX (Linux + macOS).** Concurrency primitive is `fcntl.flock` in Python (present on both),
  never the `flock(1)` CLI (absent on stock macOS). Windows is out of scope.

## 3. Goals / non-goals

Goals: (1) distinct concurrent callers never share a mutable DB unless they ask to; (2) port
collisions impossible; (3) a live session never loses a lease it holds, and a dead session never
holds one forever; (4) zero new machine assumptions; (5) one small stdlib Python helper + a thin MCP
server over it, wired into existing consumers.

Non-goals: a daemon or keep-alive service; heartbeats as a caller obligation; cross-HOST
coordination (each host has its own registry); managing the external `mcp__odoo__*` instances;
replacing `instances.toml` (it stays the catalog).
