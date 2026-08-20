# Odoo instance lifecycle - teardown

Part of `docs/reference/INSTANCE-LIFECYCLE.md` (index: the change-classification decision tree,
`-i` vs `-u` semantics, and the traps). This file owns the teardown half of the lifecycle. The
build half is `INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`.

## Teardown - the lifecycle does not end at "server answers"

The decision tree in `INSTANCE-LIFECYCLE.md` and the checklist in
`INSTANCE-LIFECYCLE-BUILD-CONTRACT.md` cover the BUILD half of the lifecycle (what to run to get a
correct, up-to-date instance). This section covers the other half: an instance you provisioned is
not finished with until it is torn down. **The full normative rule lives in one place -
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` - this section only summarizes the
instance-specific mechanics and points at where each piece is owned; it does not restate the
contract's ownership matrix or DONE-gate wording.**

- **T0 DONE-gate.** An agent may not claim `status: DONE` while an instance it self-provisioned
  this dispatch is still leased or listening. A finished report with a live leftover server is not
  done - take one of T1's three exits first, then claim DONE. Full wording:
  `resource-teardown-contract.md` T0.
- **T1 ownership (who clears it).** A self-provisioned instance (any `persist:` value the agent
  acquired for itself - `INSTANCE-ALLOCATION-MODES.md` §5) -> that agent clears it before its own
  terminal status, by one of T1's three exits: release it, park the lease (`allocator.py park` -
  server stopped, database and ports kept for a later `resume`), or hand it off by name. A forwarded `INSTANCE_HANDLE` -> the
  receiving agent NEVER releases it; only the provisioning orchestrator does, at run end.
  The shared render target -> no single consumer ever releases it; only allocator GC reclaims it -
  immediately on a dead owner pid, or (when that pid's liveness cannot be verified at all - a
  different host, or no pid recorded) on an expired TTL. A verified-alive owner pid is NEVER
  TTL-reclaimed (see `INSTANCE-ALLOCATION-RECLAIM.md` §7). Full matrix (incl. the run-level-owner and
  path-incremental rows): `resource-teardown-contract.md` T1.
- **Mechanism: stop the process group, THEN drop the DB.** `release` is teardown-complete for a
  listening instance, not just a DB drop: if the lease carries a live `server_pid` on this host,
  the allocator stops that PID's process GROUP first (SIGTERM, a bounded wait, then a group
  SIGKILL - reaping the HTTP master, workers, cron, the longpolling/gevent process, and any
  `--dev=reload` watchdog) and only THEN drops the DB for `drop_on_release` leases. Stopping the
  group first frees the DB connections that would otherwise block `DROP DATABASE`. The same order
  applies inside `gc` whenever it reclaims a lease whose still-live local pid it can PROVE is that
  lease's own server. **An unproven pid is never signalled.** A positive `pid_started` mismatch
  proves the OPPOSITE of ownership - the recorded owner already exited, which is exactly how its
  pid became free to be reused - so the live process now holding that number is an unrelated
  bystander and is NEVER signalled: the lease is still condemned and reclaimed, the process is
  left alone, and the refusal is reported. What counts as proof (the fingerprint / command-line /
  reserved-port rungs) is defined by `_stop_owner_group_if_local` + `_ownership_proof` in
  `scripts/lib/allocator.py` - read the ladder there rather than trusting a paraphrase of it. A
  same-host owner pid that is VERIFIED alive is never reached by this path at all (`_is_stale`
  never condemns it - see `INSTANCE-ALLOCATION-RECLAIM.md` §7). Full API rows (`bind`, `release`,
  `gc`): `INSTANCE-ALLOCATION-API.md` §6.
- **`server_pid` on the handle.** The instance handle a build hands back (and forwards downstream)
  now carries an optional `server_pid` - the server's process-group id under `setsid`, bound onto
  the lease via `allocator.py bind <token> --pid <pid>` at spin-up (`50-instance-spinup.sh`); null
  for a `--stop-after-init` build, which self-terminates. Field definition:
  `snippets/instance-handle-contract.md`.
- **Enforcement + crash-backstop chain.** Four layers, each catching what the one before it
  missed:
  1. **Prose release** - the agent releases its own lease as the normal, graceful path
     (`INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`'s checklist + `resource-teardown-contract.md` T1/T3).
  2. **`SubagentStop` hard block** (`hooks/enforce-teardown.sh`) - the one hard-blocking gate:
     it fires only on a live, non-shared lease that the SUBAGENT ITSELF provisioned (correlated
     from its own `acquire`/`bind`/`heartbeat` `--run-id`), at any turn end but a
     `BLOCKED`/`NEEDS_CONTEXT` report or a T4 named handoff, refusing it until the lease is
     released or handed off. Browser findings are ADVISORY only (never block) on both
     `SubagentStop` and `Stop` - see `resource-teardown-contract.md` "Why browsers and instances
     are enforced differently".
  3. **`SessionEnd` crash backstop** (`hooks/session-end-gc.sh`) - runs `allocator.py gc`
     unconditionally when the session ends, silent and bounded, so a killed/OOM'd session (no DONE
     claim, no hook 2 trigger) gets its ephemeral DB dropped WHEN `_is_stale` says the lease may be
     reclaimed (dead pid; or unprovable liveness past TTL). Its orphaned server group is stopped in
     that same pass only when the pid is provably that lease's own server; an unproven pid is never
     signalled (see the Mechanism bullet above). The hook itself only
     SPAWNS that reaping into a DETACHED session and returns at once - a SessionEnd hook is aborted
     (and its child killed mid-write) roughly a second after the batch's other hooks finish, no
     matter what `timeout` its registration declares, so anything slow left running under the hook
     is silently truncated instead of reaping; the measurement and the resulting two-role shape are
     in the hook's own header, not restated here. Note: if the
     `odoo-bin` child SURVIVED the session (a detached/setsid orphan that is still running), this
     layer deliberately does NOT reclaim it while its pid stays verified-alive on this host - see
     `hooks/session-end-gc.sh`'s header comment and `INSTANCE-ALLOCATION-RECLAIM.md` §7 for the
     tradeoff.
  4. **Next-acquire GC / TTL** - `gc` also runs opportunistically inside every `acquire`. Per
     `_is_stale` (`INSTANCE-ALLOCATION-RECLAIM.md` §7): a same-host owner pid that is DEAD is reclaimed
     immediately; a same-host owner pid that is VERIFIED ALIVE is NEVER reclaimed, no matter how
     long past `ttl_s` its heartbeat is; only the residual case liveness cannot be proven at all
     (a different-host lease, or one that never recorded a pid) falls back to the allocator's TTL
     (default `DEFAULT_TTL_S = 3600s` in `scripts/lib/allocator.py`, the SSOT for that number, sized
     for exactly this narrower residual case). Long-lived holders whose lease falls in that residual
     bucket call `heartbeat <token>` between phases so it is never reaped mid-flight; a holder with a
     verified-alive, same-host pid no longer needs to for this purpose.
  Wiring for both hooks (`SubagentStop`/`Stop`/`SessionEnd` registration) lives in `hooks/hooks.json`;
  do not restate their internals here - this bullet is a map, not a copy.
