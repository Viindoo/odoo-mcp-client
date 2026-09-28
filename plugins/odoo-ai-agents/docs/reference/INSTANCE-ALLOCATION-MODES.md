# Odoo instance allocation - access modes and port gates

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns what a caller may ASK for: the four access modes,
the `persist:` vocabulary SSOT, and the gates that decide which ports a lease gets.

## 5. Access modes

| Mode | Use case | DB | Port | Lease |
|------|----------|----|----|-------|
| `readonly` | query a running instance (OSM-style live reads, UI review against an up server) | the declared `db_name` | the declared `http_port` | none (shared) |
| `ephemeral` | **default for tests / throwaway `-i` verification** | NEW `<prefix>_t_<uuid8>`, created then dropped | none with `--ports 0` (a plain `-i`/`-u`/`--load-language` pass with `--stop-after-init`, which binds nothing); one pooled port for ANY `--test-enable` build; else N pooled ports | yes, until release |
| `exclusive` | a persistent dev server, or `-u`/migration against a REAL database that must not be touched concurrently. NEVER the mode for `persist: exclusive-running`, which acquires `ephemeral` (HARD RULE: `agents/odoo-instance-ops.md` operation 1, "the three invariants") | the declared (or a named) `db_name` | N pooled ports (`--ports`) | yes, exclusive on (db_name) |
| `shared` | the visual stack's live render server (UI review / debug / visual-regression / demo against an up server), shared by many readers across sessions | the declared `db_name` | the ACTUAL bound port, recorded verbatim via `--port` (not pooled) | yes, NON-exclusive + `drop_on_release=false` (gc reclaims a dead-server row but NEVER drops the declared DB) |

Key nuance: a plain `-i`/`-u`/`--load-language` pass with `--stop-after-init` binds **no HTTP
port** - so it needs only a unique DB (`ports: 0` on `lease_acquire`). **A `--test-enable`
build is NOT such a pass:** on every indexed series Odoo forces `http_spawn()` when test mode is on, whatever
`--no-http` and `--stop-after-init` say, so it binds a port and needs `ports: 1`. Port leasing
follows what the build ACTUALLY binds, not what its flags appear to ask for. The caller decides only
HOW MANY ports it needs; the tools put each leased port on the right flag or odoo.conf key for the
series (`instance_build` refuses a port flag in `extra_args`, `instance_serve` derives the conf keys).

**`persist:` - THE SSOT for this vocabulary.** This block is the ONE place the `persist` values are
spelled out; every skill, agent and snippet that needs them points HERE instead of restating them
(a second list is how one of them silently loses a value). `persist` is the SKILL/AGENT-level
lifecycle/isolation vocabulary, NOT a fifth allocator mode: it maps onto the four allocator modes
above. Four values:

- `persist: ephemeral` -> allocator `ephemeral`, `ports: 0` (a throwaway `--stop-after-init` build).
- `persist: exclusive-running` -> allocator `ephemeral` - the mode the acquire MUST request;
  `exclusive-running` is not a mode at all and is refused with no lease written - plus `ports: 1`
  (`2` only under prefork; see "Gevent/longpolling port stays OPT-IN" below) and the caller's
  `run_id`. It is the SAME unique-db/pooled-port lease as `ephemeral`, run as a LIVE, listening
  process: TWO LEGS under ONE lease - `instance_build` installs the module set, then
  `instance_serve` with that lease's token listens on the SAME database. The sequence and its
  invariants are owned by `agents/odoo-instance-ops.md` operation 1 and are NOT restated here.
  The lease stays `mode: ephemeral` with `drop_on_release: true`, so `lease_release` DROPS this
  database (and so does gc). That is this value's contract, not a downgrade: the database is a
  throwaway that happens to stay listening. Parking keeps its database, filestore and ports but does
  not change that fate - it REPORTS it (`drop_on_release` in the result). The only listening value
  whose database survives release is `shared-running`, and that is the DECLARED shared database. This
  lease NEVER falls back to the declared/`8069` port.
- `persist: exclusive-parked` -> the SAME lease as `exclusive-running` (or one built and never
  served) after `lease_park`: its server, if any, is stopped (no RAM held) while the database, filestore and pooled ports stay reserved under a park
  budget. A parked lease survives the end of the session that parked it. This is a STATE a lease is
  put into and taken out of (park / resume), never a value a caller requests at create time.
  `lease_find` (state `parked`, your `run_id`) finds it - the full token only when your run owns it -
  then `lease_adopt` and `instance_serve` on that token resume it back to `exclusive-running`.
- `persist: shared-running` -> allocator `shared`, owner-stamped with the caller's run id so a
  foreign run cannot release it. Cross-session and multi-reader by design: judged by its server
  alone, never parkable, and never released as anyone's teardown - not even the launcher's (which
  releases it only on an explicit user request to stop that server); `gc` reclaims it once its
  server is gone.

**Gevent/longpolling port stays OPT-IN.** The default THREADED mode (`workers=0`, what `odoo-instance`
provisions unless told otherwise) multiplexes the longpolling/realtime bus over the single
`http_port` - no second port is needed, and none is allocated by default. A second port is needed
only under prefork (`--workers>0`), which MUST also request `--ports 2` at acquire time; full
contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Prefork needs a second port.

### For maintainers - allocator internals (not agent-facing)

Agents need only the table and the vocabulary above. The rest of § 5 is how the allocator implements
them.

- **`exclusive-running` under the tools.** The listening leg is `50-instance-spinup.sh --exclusive
  --alloc-token <token>`; `--exclusive` names which instance to LAUNCH and never makes the LEASE
  exclusive. `allocator.py acquire --mode exclusive-running` exits 2 (`USAGE`).
- **Park / resume.** `lease_park` is `allocator.py park`: stops the proven process group if one runs, stamps
  `parked_at` / `park_ttl_s` / `parked_boot_id`, and the lease is judged by its park budget instead of
  the session and pid rungs (`INSTANCE-ALLOCATION-RECLAIM.md` §7.1). Resume is `allocator.py resume
  <token> --pid <new server pid>`, one locked compare-and-set; `lease_find` with state `parked` is
  `allocator.py query --series <X.Y> --state parked`. Resuming or adopting a parked lease sets
  `owner.return_to_park`, so a gc that finds its new owner gone parks it again instead of dropping it
  (`INSTANCE-ALLOCATION-RECLAIM.md` §7.2).
- **Shared ownership** - `INSTANCE-ALLOCATION-GUARDS.md` §6.3; `SHARED_NOT_PARKABLE`,
  `INSTANCE-ALLOCATION-API.md` §6.

**P5 port-uniqueness gate.** `_pick_ports` (`INSTANCE-ALLOCATION-API.md` §6 `acquire`) excludes the instance's declared `http_port`
from the pool outright - both by defaulting `http_port_base` to `declared_port + 1` when the catalog
declares no separate pool base, and by passing the declared port as an explicit `reserved` exclusion
so a misconfigured overlapping `http_port_base` still cannot collide. Without this, a catalog entry
with no separate `http_port_base` would let the pool hand out the declared/shared port itself to an
`exclusive-running` lease. Covered by `test_allocator.py::test_pooled_port_never_equals_the_declared_http_port`
and `::test_concurrent_pooled_acquires_never_collide_with_declared_port`.

**P5b - catalog-wide reservation (closes the boundary off-by-one).** The single-instance exclusion
above is not sufficient across a MULTI-instance catalog: declared ports may step by 10 (older
catalogs from `40-instance-profile.sh`) while a pool spans `DEFAULT_POOL_SIZE=10` ports starting at
`declared_port + 1`, so instance 0's pool ends exactly AT instance 1's declared port (e.g. 8069's
pool reaching 8079, a second catalog entry's declared port). `cmd_acquire` reserves EVERY
catalog-declared `http_port`, not only the acquiring instance's own: it reads the full catalog via
the same `load_instances()` call already made (before the `with _locked()` critical section, so this
adds no new lock and no deadlock risk) and passes the whole set as the `reserved` exclusion to
`_pick_ports`. This is what closes the boundary off-by-one on an EXISTING catalog; the port step of 11 for new
instances (`40-instance-profile.sh`) is a COSMETIC companion only - it does not touch
already-declared ports and does not by itself prevent the collision. Covered by
`test_allocator.py::test_maxed_out_pool_never_hands_out_a_sibling_instances_declared_port`.

**P6 - bootstrap-race safety (two same-series projects racing to spin up first).** A `db_name`
default derived from `series` alone (`odoo_<series>`, identical for every project on that series)
plus a declared port that also defaults identically at index 0 meant two never-migrated
same-series projects could resolve to the SAME db_name and port before either had a chance to
register distinctly - a bare `db_name` identity check could then pass against a foreign server.
Three-part fix, all in `40-instance-profile.sh`
/ `50-instance-spinup.sh` (outside `allocator.py` itself, but part of this design's concurrency
guarantee):
1. **PRIMARY - eager catalog migration.** `40-instance-profile.sh` migrates a project's local
   `instances.toml` into the machine-global catalog EAGERLY, at the top of every subcommand dispatch,
   so two projects that both migrate early land in ONE
   global catalog whose port stepper (P5b above) then sees every already-declared instance and
   assigns distinct ports before either spins up. Covered by
   `test_setup_instances.py::test_migration_runs_eagerly_at_session_start_not_gated_behind_apply` and
   `::test_eager_migration_two_same_series_projects_get_distinct_ports_and_db_names`.
2. **BACKSTOP - instance-identity attach guard.** `50-instance-spinup.sh` records an identity token
   (a hash of `addons_path` - unique per project checkout, unlike `db_name`/series alone) on the port
   at spin-up, and refuses to treat "the port answers HTTP 200" as "my instance is up" when a LATER
   invocation's expected token mismatches a recorded one - a fail-closed collision detector for the
   narrow race window the eager migration shrinks but cannot fully eliminate. A port with no recorded
   marker yet (nothing has spun up through this guard) is a pass-through. Covered by `test_setup_instances.py::test_attach_guard_rejects_a_live_port_with_mismatched_recorded_identity`,
   `::test_attach_guard_allows_a_live_port_with_no_recorded_identity_yet`, and
   `::test_attach_guard_allows_a_live_port_with_matching_recorded_identity`.
3. **db_name project-discriminator.** The default `db_name` is series- AND project-scoped
   (`odoo_<series>_<repo-key8>`, the first 8 hex chars of the same `sha256(realpath(git-common-dir))`
   key that `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` uses for the Tier-2 SHARE root -
   not a fresh hash), so two same-series projects sharing the now-global catalog never default to the
   SAME db name even outside the race window.
