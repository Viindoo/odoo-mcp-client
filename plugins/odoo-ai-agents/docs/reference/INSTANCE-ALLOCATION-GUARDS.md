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

- **`55-instance-ops.sh`-backed operations** (create/init/update/run-tests - what
  `instance_build` runs) pass ALL parameters as explicit CLI flags and read NO shared config
  file at all: no `-c`/`--config` flag, no reliance on `$ODOO_RC`.
- **`50-instance-spinup.sh`-backed operations** (the "stay-running" apply path that
  `instance_serve` runs, and `ensure-up`) DO
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

### 6.3 Ownership guard (run_id)

`owner.run_id` is the ownership key stamped at `acquire` (`INSTANCE-ALLOCATION-REGISTRY.md` §4.2);
the legacy `owner.session_id` field is read only as a fallback on rows minted before `run_id`
existed. Ownership (who may destroy a lease) and liveness (what keeps it from being reclaimed - the
session anchor, `INSTANCE-ALLOCATION-RECLAIM.md` §7.1) are separate facts: sharing a session does
not confer ownership, and owning a run does not keep a lease alive.

**Release and park belong to the run that ACQUIRED the lease.** `release <token> --run-id <id>`
(`lease_release`) is refused whenever the lease's `owner.run_id` (or its legacy `session_id`
fallback) is non-empty and the caller's run id does not equal it - and an ABSENT run id is one of
those cases: ownership NOT ESTABLISHED, never ownership assumed. The rightful owner is never blocked:
it passes the run id its own acquire returned (`INSTANCE_HANDLE.run_id` downstream). Holding the
token is not ownership. `--force` proceeds anyway and logs the foreign run id it overrode; it is a
human's override, never a dispatched agent's way around a refusal. The check runs inside the same
`flock` critical section as the release itself. `park <token> --run-id <id>` (`lease_park`) applies
the same rule, through the same helper, under the lock and before any signal (an unowned lease parks
on the token alone), and `adopt` (`lease_adopt`) requires the recorded owner run too.

The PreToolUse hook `hooks/block-unowned-lease-mutation.sh` (matcher: `Bash` and the MCP
`lease_release` / `lease_park` / `lease_adopt` tools) enforces this for SUBAGENT callers only - the
main context is never denied:

- **A1** - a Bash `allocator.py release|park|adopt` naming no `--run-id` (nor `--session`). A
  python interpreter's own options before the script (`python3 -u`, `-X dev`, `-W error`, a cluster
  like `-uB`) are skipped, so they never hide an invocation from any arm; `-c` / `-m` run something
  else and are left alone.
- **A2** - `--force` / `--force-forget` on release or park, `reap-orphans --yes`, `acquire
  --allow-unowned`.
- **A3** - `allocator.py gc` without `--dry-run`.
- **A4** - a release, park or adopt (Bash or MCP) of a token the caller does not hold: the token must
  appear in the caller's OWN transcript as OBTAINED (a `lease_acquire` or `lease_adopt` result, a
  series-mode `instance_serve` result reporting `state: launched`, or the Bash receipt line
  `allocator: acquired|adopted lease <token>`) or HANDED UP in the report of a child it dispatched.
  NOT obtainment: an `attached` series-mode serve (it joined a server another run started), a serve
  or resume of a token passed in, and a `lease_find` / `lease_list` result. An adopt may also use a
  token its own `lease_find` returned, which is the only resume path from a new session:
  `lease_find` (parked, run_id) -> `lease_adopt` -> `instance_serve`; a found token is never
  released or parked before that adopt. A token that only arrived in the brief is refused as
  forwarded. The
  correlation is `hooks/lease-correlation.sh`, shared with `enforce-teardown.sh`. The arm fails open
  (a stderr line) when the transcript is unreadable or a Bash token is not a literal; command
  substitutions (`eval "$(...)"`) are checked like direct calls.

An agent that CONSUMES a forwarded `INSTANCE_HANDLE` never releases or parks it - only its owner
does (`snippets/resource-teardown-contract.md` T1). A launched series-mode serve makes the SHARED
lease it registered pass A4 for its launcher, but that lease is multi-reader and never anyone's
teardown (`INSTANCE-ALLOCATION-MODES.md` §5 `shared-running`); `park` refuses it outright.

An UNOWNED lease - no owner run recorded at all - still releases on token possession: `release`
requires the token, and it is the only correct teardown path for a row minted before `run_id`
existed. Acquire with a run id and a lease is never in that class (`acquire` without `--run-id`
exits 10 unless `--allow-unowned` states the lack deliberately).

**A leased (managed) database MUST be dropped via `release`, never by bare name.** Bare
`odoo_db.py drop` / `55-instance-ops.sh drop` are for UNMANAGED databases only. Before a bare drop,
confirm the database is unmanaged with `assert-droppable --db-name <db> [--run-id <id>]`; it exits
non-zero when a FRESH lease on that database is owned by another run (naming the owning run) OR is
unowned - unowned does not mean "safe to drop". An own lease, a condemned lease or no lease is
droppable; `--force` is the explicit override. This is an accident-prevention layer, not a security
boundary: `run_id` is a semi-discoverable slug, and `assert-droppable` and the drop are two separate
processes, so a lease minted in the gap between them is not covered; managed databases never take
the bare-drop path, so this window does not apply to them.

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
