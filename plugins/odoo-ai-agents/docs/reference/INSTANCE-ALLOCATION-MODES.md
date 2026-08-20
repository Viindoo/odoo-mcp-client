# Odoo instance allocation - access modes and port gates

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns what a caller may ASK for: the four access modes,
the `persist:` vocabulary SSOT, and the gates that decide which ports a lease gets.

## 5. Access modes

| Mode | Use case | DB | Port | Lease |
|------|----------|----|----|-------|
| `readonly` | query a running instance (OSM-style live reads, UI review against an up server) | the declared `db_name` | the declared `http_port` | none (shared) |
| `ephemeral` | **default for tests / throwaway `-i` verification** | NEW `<prefix>_t_<uuid8>`, created then dropped | none with `--ports 0` (tests, `--stop-after-init`); else N pooled ports | yes, until release |
| `exclusive` | a persistent dev server, or `-u`/migration against a REAL database that must not be touched concurrently | the declared (or a named) `db_name` | N pooled ports (`--ports`) | yes, exclusive on (db_name) |
| `shared` | the visual stack's live render server (UI review / debug / visual-regression / demo against an up server), shared by many readers across sessions | the declared `db_name` | the ACTUAL bound port, recorded verbatim via `--port` (not pooled) | yes, NON-exclusive + `drop_on_release=false` (gc reclaims a dead-server row but NEVER drops the declared DB) |

Key nuance: a CI-style test - memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`
(HARD RULE, never omit the `ulimit -Sv` guard):

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d <db> -i <mod> --test-enable --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

binds **no HTTP port** - so `ephemeral` tests need only a unique DB, not a port (pass `--ports 0`). Port leasing
applies only when a server actually listens. The CONSUMER decides HOW MANY ports it needs and which
CLI flag carries each (an HTTP port, plus a longpoll/gevent port on series that need one) by querying
`cli_help` for the `<series>` at runtime - the allocator just hands out N version-agnostic free port numbers.
This removes most port contention outright.

**`persist:` - THE SSOT for this vocabulary.** This block is the ONE place the `persist` values are
spelled out; every skill, agent and snippet that needs them points HERE instead of restating them
(a second list is how one of them silently loses a value). `persist` is the SKILL/AGENT-level
lifecycle/isolation vocabulary, NOT a fifth allocator mode: it maps onto the four allocator modes
above. Four values:

- `persist: ephemeral` -> allocator `ephemeral`, `--ports 0` (a throwaway `--stop-after-init` build).
- `persist: exclusive-running` -> allocator `ephemeral`, `--ports 1` (or `2`) + `--run-id <id>` - the
  SAME unique-db/pooled-port lease as `ephemeral` above, except the caller runs it as a LIVE,
  listening process (`50-instance-spinup.sh --exclusive`, `agents/odoo-instance-ops.md` operation 1)
  instead of `--stop-after-init`. This lease NEVER falls back to the declared/`8069` port - the port
  always comes from this acquire (P5 port-uniqueness gate, below).
- `persist: exclusive-parked` -> the SAME lease as `exclusive-running` after `allocator.py park`:
  the server's process group is stopped (so it holds no RAM) while the database, the filestore and
  the pooled ports stay reserved, under `park_ttl_s` instead of the owner-pid arms. This is a STATE
  a lease is put into and taken out of (`park` / `resume`), never a value a caller requests at
  create time. `resume <token> --pid <new server pid>` returns it to `exclusive-running` in one
  locked compare-and-set; `query --series <X.Y> --state parked` is how a later dispatch finds it.
- `persist: shared-running` -> allocator `shared`, now REQUIRED to be owner-stamped via `--run-id`
  (`INSTANCE-ALLOCATION-GUARDS.md` §6.3) so a foreign session can no longer bare-drop it. Never
  parkable - see the `park` row in `INSTANCE-ALLOCATION-API.md` §6.

**P5 port-uniqueness gate.** `_pick_ports` (`INSTANCE-ALLOCATION-API.md` §6 `acquire`) excludes the instance's declared `http_port`
from the pool outright - both by defaulting `http_port_base` to `declared_port + 1` when the catalog
declares no separate pool base, and by passing the declared port as an explicit `reserved` exclusion
so a misconfigured overlapping `http_port_base` still cannot collide. Without this, a catalog entry
with no separate `http_port_base` would let the pool hand out the declared/shared port itself to an
`exclusive-running` lease. Covered by `test_allocator.py::test_pooled_port_never_equals_the_declared_http_port`
and `::test_concurrent_pooled_acquires_never_collide_with_declared_port`.

**P5b - catalog-wide reservation (closes the boundary off-by-one).** The single-instance exclusion
above is not sufficient across a MULTI-instance catalog: declared ports historically stepped by 10
(`40-instance-profile.sh`) while a pool spans `DEFAULT_POOL_SIZE=10` ports starting at
`declared_port + 1`, so instance 0's pool ends exactly AT instance 1's declared port (e.g. 8069's
pool reaching 8079, a second catalog entry's declared port). `cmd_acquire` now reserves EVERY
catalog-declared `http_port`, not only the acquiring instance's own: it reads the full catalog via
the same `load_instances()` call already made (before the `with _locked()` critical section, so this
adds no new lock and no deadlock risk) and passes the whole set as the `reserved` exclusion to
`_pick_ports`. This is the fix that closes the boundary off-by-one on an EXISTING catalog; widening
new instances' port step to 11 (`40-instance-profile.sh`) is a COSMETIC companion only - it does not
touch already-declared ports and does not by itself prevent the collision. Covered by
`test_allocator.py::test_maxed_out_pool_never_hands_out_a_sibling_instances_declared_port`.

**P6 - bootstrap-race safety (two same-series projects racing to spin up first).** A `db_name`
default derived from `series` alone (`odoo_17_0` for every v17.0 project) plus a declared port that
also defaults identically at index 0 meant two never-migrated same-series projects could resolve to
the SAME db_name and port before either had a chance to register distinctly - a bare `db_name`
identity check could then pass against a foreign server. Three-part fix, all in `40-instance-profile.sh`
/ `50-instance-spinup.sh` (outside `allocator.py` itself, but part of this design's concurrency
guarantee):
1. **PRIMARY - eager catalog migration.** `40-instance-profile.sh` migrates a project's local
   `instances.toml` into the machine-global catalog EAGERLY, at the top of every subcommand dispatch
   - not lazily, only inside `apply` as before - so two projects that both migrate early land in ONE
   global catalog whose port stepper (P5b above) then sees every already-declared instance and
   assigns distinct ports before either spins up. Covered by
   `test_setup_instances.py::test_migration_runs_eagerly_at_session_start_not_gated_behind_apply` and
   `::test_eager_migration_two_same_series_projects_get_distinct_ports_and_db_names`.
2. **BACKSTOP - instance-identity attach guard.** `50-instance-spinup.sh` records an identity token
   (a hash of `addons_path` - unique per project checkout, unlike `db_name`/series alone) on the port
   at spin-up, and refuses to treat "the port answers HTTP 200" as "my instance is up" when a LATER
   invocation's expected token mismatches a recorded one - a fail-closed collision detector for the
   narrow race window the eager migration shrinks but cannot fully eliminate. A port with no recorded
   marker yet (nothing has spun up through this guard) is a pass-through, same as before the guard
   existed. Covered by `test_setup_instances.py::test_attach_guard_rejects_a_live_port_with_mismatched_recorded_identity`,
   `::test_attach_guard_allows_a_live_port_with_no_recorded_identity_yet`, and
   `::test_attach_guard_allows_a_live_port_with_matching_recorded_identity`.
3. **db_name project-discriminator.** The default `db_name` is now series- AND project-scoped
   (`odoo_<series>_<repo-key8>`, the first 8 hex chars of the same `sha256(realpath(git-common-dir))`
   key that `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` uses for the Tier-2 SHARE root -
   not a fresh hash), so two same-series projects sharing the now-global catalog never default to the
   SAME db name even outside the race window.

**Gevent/longpolling port stays OPT-IN.** The default THREADED mode (`workers=0`, what `odoo-instance`
provisions unless told otherwise) multiplexes the longpolling/realtime bus over the single
`http_port` - no second port is needed, and none is allocated by default. A second port is needed
only under prefork (`--workers>0`), which MUST also request `--ports 2` at acquire time; full
contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Prefork needs a second port.
