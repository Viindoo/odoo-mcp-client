# Technical Design - concurrent Odoo instance allocation (user/global, cross-session)

Status: IMPLEMENTED
Audience: plugin maintainers + global contributors. This is a design contract, not code.
Related: `snippets/instance-resolution.md`, `snippets/venv-resolution.md`,
`snippets/instance-handle-contract.md`, `snippets/state-root-resolution.md`,
`snippets/odoo-bin-resource-limits.md`, `docs/reference/INSTANCE-LIFECYCLE.md`,
`skills/_shared/concurrency-guard.md`, `scripts/lib/instances_io.py`, `scripts/lib/odoo_db.py`,
`scripts/setup-steps/40-instance-profile.sh`, `scripts/setup-steps/50-instance-spinup.sh`.

> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for instance lifecycle operations (build, drop, init, update, test). The
> allocator is the low-level coordination primitive they use internally. Persistent operation logs
> are written to `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## Parts - what each file owns

Every section below §3 lives in a part file. Cite the PART that owns the fact you need, never
this index.

| File | Sections | Owns |
|------|----------|------|
| `INSTANCE-ALLOCATION-REGISTRY.md` | §4, §4.1, §4.2 | the two-layer catalog/registry architecture, the optional `instances.toml` catalog fields, and the `leases.json` lease-registry format |
| `INSTANCE-ALLOCATION-MODES.md` | §5 | the four access modes, the `persist:` vocabulary SSOT, the P5/P5b/P6 port-uniqueness and bootstrap-race gates, and the opt-in gevent/longpolling port |
| `INSTANCE-ALLOCATION-API.md` | §6, §6.1, §6.6 | the `allocator.py` command surface, B2 DB lifecycle ownership (caller-side create, through-Odoo drop), and the acquire exit codes 6/7/8/9 |
| `INSTANCE-ALLOCATION-GUARDS.md` | §6.2, §6.3, §6.4, §6.7 | what a build or a lease is REFUSED: config-file isolation, the run/session ownership guard, the addons-path worktree-mismatch guard, and the undroppable-database classification |
| `INSTANCE-ALLOCATION-RECLAIM.md` | §6.5, §7, §8, §9 | how a lease is reclaimed: the `reap-orphans` DB-side sweep, `_is_stale` crash/stale handling, the failure-mode matrix, and the TTL default |

## 1. Problem & intent

Multiple subagents in one Claude Code session - and multiple sessions on one host - run Odoo
operations concurrently. Some agents only READ a running instance (share is fine); some need an
ISOLATED database (tests, `-i`/`-u`, a throwaway dev server). Today there is no coordination.

What exists is **declaration + resolution only**: `$ODOO_AI_HOME/instances.toml` is a machine-global
catalog (`series`, one `http_port`, one `db_name`, `db_host`/`db_user`, `addons_path`, venv
`python`) and `instances_io.py` picks the first instance matching a series. There is **no
in-use/owner/lease field, no per-run database or port, no PID/runtime registry, and no
mutual-exclusion primitive** (`flock`/`fcntl`/`.lock`/pidfile = 0 occurrences in the repo).
`concurrency-guard.md` governs only agent fan-out (OOM / model-weighted budget) - it says nothing
about DB or port ownership.

**Concurrency gap (verified):** OSM reads are safe (the session-pin race was neutralised by passing
the concrete version every call). But every live-instance mutation is unsafe under concurrency:
two agents/sessions resolve the SAME single `db_name`+`http_port`, so concurrent `--test-enable`,
`-i`/`-u`, or spin-up collide on the port or corrupt each other's database. Nothing serialises them.

**Intent:** a portable, user/global allocator that hands each concurrent caller either a shared
read-only handle or an isolated (db [+ port]) lease, reclaims leases when an agent/session dies, and
assumes nothing about this one machine.

## 2. Constraints (non-negotiable)

- **Portable / public / global.** No hardcoded paths (`/home/<user>/...`), no assumption about this
  host's Postgres, ports, or layout. All runtime state under `$ODOO_AI_HOME` (default `~/.odoo-ai`).
  The user declares their Postgres + venv via `instances.toml` (written by `/odoo-setup`).
- **No live Odoo MCP.** The `mcp__odoo__*` server is out of scope by existing design; the
  allocator coordinates only locally-declared instances.
- **Backward compatible.** Existing `instances.toml` files keep parsing; the read-only resolution
  path (`instance-resolution.md`) is unchanged for callers that only need a URL.
- **POSIX (Linux + macOS).** Concurrency primitive is `fcntl.flock` in Python (present on both),
  never the `flock(1)` CLI (absent on stock macOS). Windows is explicitly out of scope for v1.

## 3. Goals / non-goals

Goals: (1) distinct concurrent callers never share a mutable DB unless they ask to; (2) port
collisions impossible; (3) a dead agent/session never holds a resource forever; (4) zero new
machine assumptions; (5) one small Python helper + a documented protocol, wired into existing
consumers.

Non-goals: a daemon/service; cross-HOST coordination (each host has its own registry); managing the
external `mcp__odoo__*` instances; replacing `instances.toml` (it stays the catalog).
