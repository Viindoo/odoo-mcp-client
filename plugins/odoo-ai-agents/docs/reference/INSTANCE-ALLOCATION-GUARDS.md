# Odoo instance allocation - guards

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns the guards a build or a lease must clear that are
not acquire exit codes: config-file isolation, run/session ownership, addons-path provenance, and
a database the allocator cannot drop.

### 6.2 Config-file isolation (agent-facing contract)

Every concurrent instance build MUST be isolated. Isolation is guaranteed by the ALLOCATOR, not by
a shared environment config: the allocator reserves a UNIQUE database name (`<prefix>_t_<uuid8>`,
`INSTANCE-ALLOCATION-REGISTRY.md` §4.1) and a private port pool per caller
(`INSTANCE-ALLOCATION-API.md` §6), and the DB itself is created THROUGH Odoo by that build's own
`-i` run (`INSTANCE-ALLOCATION-API.md` §6.1) - never by a config file.

Two distinct paths exist in the current implementation, and BOTH satisfy the isolation contract by
construction:

- **`55-instance-ops.sh`-backed operations** (create/init/update/run-tests - the primary
  `odoo-instance-ops` path) pass ALL parameters as explicit CLI flags and read NO shared config
  file at all: no `-c`/`--config` flag, no reliance on `$ODOO_RC`.
- **`50-instance-spinup.sh`-backed operations** (the "stay-running" apply path, and `ensure-up`) DO
  materialise an `odoo.conf` for the launched server. That file MUST live at a DETERMINISTIC path
  keyed by the RESOURCE - `$ODOO_AI_HOME/conf/<db_name>-<port>.conf` - NEVER the environment's
  default `odoo.conf` / `$ODOO_RC`, and MUST NOT mutate any project file. `db_name` and `port` are
  the identical pair the allocator's own lease already guarantees is exclusive per LIVE instance
  (`INSTANCE-ALLOCATION-REGISTRY.md` §4.1, `INSTANCE-ALLOCATION-API.md` §6), so this key is unique per live instance without minting a separate per-invocation
  identity. Re-spinning the same instance overwrites its own conf file in place; a stale conf whose
  lease is gone is reclaimed by `prune_stale_run_artifacts` (`scripts/lib/state_reclaim.sh`) under
  the lease-registry reachability guard, the same mechanism that reclaims stale logs. `conf/` is a
  Tier-1 subpath - see `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`'s Tier-1 allowlist
  for where it is registered; that classification is not restated here.

  **Per-invocation uniqueness (`mktemp`) is FORBIDDEN for this file, going forward.** An
  invocation-keyed name has no owner on any exit path: `-c "$conf"` keeps the file open for the
  server's entire lifetime once launched, so it can never be deleted after that point, and a name
  that changes on every invocation therefore has nothing that ever reclaims it - one orphaned file
  accumulates per spin-up, forever. Keying the file by the resource instead of the invocation is
  what makes it both correct (still exclusive per live instance) and reclaimable (bounded by the
  set of declared instances rather than by the number of launches ever performed).

**Contract:** an agent MUST NOT introduce a build step that writes to a shared or default config
path (`$ODOO_RC`, a project-committed `odoo.conf`, or any config file reused across concurrently
LIVE instances). Every build either (a) passes flags with no config file at all, or (b) writes the
resource-keyed conf at its deterministic, per-live-instance path - there is no third path, and (b)
is NEVER a per-invocation temp file. This is a harness-level guarantee, not an Odoo-CLI fact, so it
applies identically across all versions (v8-v19).

Consumers point back here rather than restating the contract: `agents/odoo-instance-ops.md`
("Through-Odoo DB lifecycle") and `skills/odoo-instance/SKILL.md`.

### 6.3 Ownership guard (run/session)

`owner.run_id` is the canonical ownership key stamped at `acquire`
(`INSTANCE-ALLOCATION-REGISTRY.md` §4.2); the legacy
`owner.session_id` field is no longer written on new leases and is read only as a fallback on
leases minted before `run_id` existed.

**`release` belongs to the run that ACQUIRED the lease.** `release <token> --run-id <id>` refuses
the release whenever the lease's `owner.run_id` (or its legacy `session_id` fallback) is non-empty
and the caller's `--run-id` does not equal it - and an ABSENT `--run-id` is one of those cases, not
an exemption from them. "No run id forwarded" is not "the owner forgot a flag"; it is ownership NOT
ESTABLISHED, and a call that stops a server and drops a database may not proceed on a guess. The
rightful owner is never blocked by this: it threads the id its own `acquire` echoed as
`ALLOC_RUN_ID` (`INSTANCE_HANDLE.run_id` downstream). A caller that cannot produce one did not
acquire this lease - holding the token is not ownership. `--force` proceeds anyway and logs the
foreign run id it overrode; it is a human's override, never a dispatched agent's way around a
refusal. The check runs inside the same `flock` critical section as the release itself, so it is
race-free. This is the same predicate shape `assert-droppable` (below) has always used.

An UNOWNED lease - no owner run recorded at all - still releases on token possession. That is a
deliberate NON-import of P5.8 below: P5.8 guards a BARE-NAME drop, which carries no ownership
evidence whatsoever, whereas `release` requires the token; and since `release` is the only correct
teardown path, refusing unowned leases here would leave every pre-`run_id` lease with no exit but
`--force`. Thread `--run-id` at `acquire` and the lease is never in that class.

**Superseded, and deleted from this section:** the earlier rule "in every other case (no run id
forwarded, ...) the release proceeds on token possession alone ... a caller that never forwards a
run id is NEVER blocked from releasing its own lease". It was written to protect the owner and
instead licensed a stranger: an `and caller_run` conjunct made an un-threaded release short-circuit
the whole ownership comparison, so a dispatch that had acquired nothing released a live acceptance
lease whose token it merely knew, and `drop_on_release: true` destroyed the database. Do not
reinstate it in any wording. If a legitimate caller is blocked, thread its run id - do not widen
the predicate.

**A leased (managed) DB MUST be dropped via `release`, never by bare name.** Bare
`odoo_db.py drop` / `55-instance-ops.sh drop` are for UNMANAGED databases only - one with no
lease has nothing to orphan. Before a bare drop, confirm the DB is unmanaged with
`assert-droppable --db-name <db> [--run-id <id>]`; it exits non-zero (and names the owning run)
when a fresh foreign lease exists, so the caller routes to `release` instead. `--force` on the
drop path is the explicit override for reaping a foreign or stale lease. This is an
accident-prevention layer, not a security boundary - `run_id` is a semi-discoverable slug
(worklog paths), and `assert-droppable` + the drop remain two separate processes, so a lease
minted in the gap between them is not covered; managed DBs never take the bare-drop path, so
this bounded TOCTOU window does not apply to them.

**P5.8: an UNOWNED-but-fresh lease is ALSO refused, not just a foreign one.** Before this fix,
`assert-droppable` treated an empty `owner.run_id` as `always droppable` - which is exactly what let
one session bare-drop another session's live instance whenever the OWNING acquire never threaded
`--run-id` (the `_register_shared` gap P5.5 closes). A fresh (non-stale) lease with NO recorded owner
at all now ALSO requires `--force` to drop, same as a fresh foreign-owned one; an own-lease or a
stale lease remains droppable with no `--force`, unchanged. Covered by
`test_allocator.py::test_assert_droppable_refuses_unowned_fresh_lease_without_force`.

### 6.4 Addons-path worktree-mismatch guard (false-green prevention)

A caller verifying a fix that lives in a linked git worktree, while the catalog's declared
`addons_path` still points at the PRINCIPAL checkout of that same repo, must never be silently
handed the principal path - that produces a false green (the pre-fix code, self-consistently
tested, reports success). `acquire` detects this shape via `_addons_path_worktree_mismatch`:
git-common-dir is IDENTICAL across every worktree of one repository while `--show-toplevel`
differs per checkout, so "same common-dir, different toplevel" between the caller's cwd and a
catalog `addons_path` entry is the fingerprint. When detected AND no `--addons-path-override` was
passed, `acquire` refuses (exit 5) with a message naming both paths and the exact
`--addons-path-override` value that would resolve it, instead of guessing. An explicit
`--addons-path-override` always bypasses the guard (that IS the caller stating the tree
explicitly - the whole point). The guard is scoped to modes that actually drive a build
(`ephemeral`/`exclusive`/`shared`); `readonly` is exempt (it builds nothing). A cwd that is not a
git repo, IS the catalog's own declared checkout, or shares no repository with any addons_path
entry never trips it - see `tests/test_lease_ownership_and_reaping.py` for the full behavior
matrix (mismatched worktree refused, override bypasses it, principal checkout unaffected,
unrelated repo unaffected, readonly exempt).

### 6.7 A lease whose database cannot be dropped

`release` keeps the lease whenever the drop FAILED - the database is still there, and removing the
lease would mint an orphan nothing can find (`reap-orphans` excludes any DB a lease references).
Two mechanisms keep that from becoming permanent:

- **The drop surface is re-resolved from the CURRENT catalog on every attempt.** Only the GAPS are
  filled, and only with values that VALIDATE, so re-resolution can never redirect a drop at a
  cluster the lease never used - which makes `45-venv.sh record-env` repair EXISTING leases, not
  just future ones.
- **`release <token> --force-forget`** is the documented escape when nothing on this host can ever
  drop the DB (no `python`, `db_run_mode = tcp-only`). It removes the lease and NAMES what was left
  behind, and never reports a teardown that did not happen.

Existence is CLASSIFIED before anything is named, so ABANDONED is EARNED, not assumed:

| Database exists? | `--force-forget` outcome | plain release after a failed drop |
|---|---|---|
| yes | `ALLOC_ABANDONED_DB=<db>` - observed present on its cluster | lease kept, exit 1 |
| no | `ALLOC_FORGOTTEN_DB=<db>` - nothing was left behind | **lease released, exit 0** - the drop had nothing to do |
| could not look | `ALLOC_UNVERIFIED_DB=<db>` - the lease is gone; existence unconfirmed. Check by hand | lease kept, exit 1, reason named |

The "no" row closes the leak from the other end: a build that crashed before creating anything left a
lease whose drop could only ever "fail", retried by gc forever.
