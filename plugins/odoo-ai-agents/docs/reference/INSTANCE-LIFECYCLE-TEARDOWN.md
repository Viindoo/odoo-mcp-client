# Odoo instance lifecycle - teardown

Part of `docs/reference/INSTANCE-LIFECYCLE.md` (index: the change-classification decision tree,
`-i` vs `-u` semantics, and the traps). This file owns the teardown half of the lifecycle. The
build half is `INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`.

## Teardown - the lifecycle does not end at "server answers"

An instance you provisioned is not finished with until it is torn down. **The normative rule lives
in one place - `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` - this section only
summarizes the instance-specific mechanics and points at where each piece is owned; it does not
restate the contract's ownership matrix or DONE-gate wording.**

- **T0 DONE-gate.** An agent may not claim `status: DONE` while an instance it self-provisioned
  this dispatch is still leased or listening. Take one of T1's three exits first. Full wording:
  `resource-teardown-contract.md` T0.
- **T1 ownership (who clears it).** Ownership is the lease's `run_id`. A self-provisioned instance
  (any `persist:` value the agent acquired for itself - `INSTANCE-ALLOCATION-MODES.md` §5) -> that
  agent clears it before its own terminal status by one of three exits: release it
  (`lease_release`), park it (`lease_park` - server stopped, database and ports kept for a later
  resume), or hand it off by name (forward its `INSTANCE_HANDLE` to a named catcher). A forwarded
  `INSTANCE_HANDLE` -> the receiving agent NEVER releases it; only the provisioning owner does. The
  shared render target -> multi-reader, so nobody releases or parks it as teardown, not even the
  run whose serve launched it (which releases it only when the user explicitly asks); `gc` reclaims
  it once its server is gone
  (`INSTANCE-ALLOCATION-RECLAIM.md` §7.2). Full matrix:
  `resource-teardown-contract.md` T1.
- **Mechanism: stop the process group, THEN drop the database.** `release` is teardown-complete for
  a listening instance, not just a drop: it marks the row `reclaiming`, stops the server's process
  GROUP (SIGTERM, a bounded wait, then a group SIGKILL - the HTTP master, workers, cron, the
  longpolling/gevent process, any `--dev=reload` watchdog), and only THEN drops a `drop_on_release`
  database through Odoo; stopping first frees the connections that would block `DROP DATABASE`.
  `lease_release` additionally stops any still-running `instance_build` job of that lease first.
  The same stop-then-drop order applies inside `gc`. **An unproven pid is never signalled:** only a
  pid PROVEN to be the lease's own server (`_stop_owner_group_if_local` + `_ownership_proof` in
  `scripts/lib/allocator.py` - read the ladder there) is stopped; a pid whose fingerprint proves
  recycling belongs to a bystander and is left alone while the lease is still reclaimed. Verb
  reference: `INSTANCE-ALLOCATION-API.md` §6.
- **`server_pid` on the handle.** The instance handle a listening instance returns carries
  `server_pid` - the server's process-group id under `setsid`, bound onto the lease inside
  `instance_serve` (`50-instance-spinup.sh`); null for a build, which exits on its own and is
  deliberately not bound. Field definition: `snippets/instance-handle-contract.md`.

## Enforcement chain

Four layers, each catching what the one before it missed. Acquire is not a link: it reclaims no
database (`INSTANCE-ALLOCATION-RECLAIM.md` §7.2).

1. **The agent's own exit** - the graceful path: release, park or forward by name
   (`INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`'s checklist + `resource-teardown-contract.md` T1/T3).
2. **Report-time hard gates** - one check at two moments, shared through `hooks/teardown-check.sh`.
   A report handed back through `SubagentHandback` reaches the caller the moment the call runs,
   before the subagent stops, so the check runs there first: the PreToolUse deny
   `hooks/block-handback-with-live-lease.sh` refuses the handback, and a refused one delivers
   nothing - the agent takes an exit and calls it again. The `SubagentStop` block
   (`hooks/enforce-teardown.sh`) is the backstop for a lease obtained after the handback and for a
   report delivered as final text. Both read the report the caller actually receives - the
   handback message, else the final message (`hooks/final-report.sh`). They
   check only the LIVE, non-shared lease TOKENS this subagent itself obtained, read from its own
   transcript: the results of its own `lease_acquire` and `lease_adopt` calls, a series-mode
   `instance_serve` that reported `state: launched` (an `attached` serve joined another run's server
   and is not obtaining; the shared lease a launch registers is exempt as multi-reader), and
   the Bash receipt line `allocator: acquired|adopted lease <token>` (correlation shared with the
   ownership gate: `hooks/lease-correlation.sh`). Serving or resuming a FORWARDED token is
   consumption, not obtaining - that lease stays its provider's. It never correlates by `run_id` or
   a time window; `run_id` is shared by the parent and every sibling. Whether such a lease is still live comes from the allocator's own verdict
   (`list --with-verdict`); a released or parked lease passes. They refuse until each such lease is
   released, parked, or handed off by a named `INSTANCE_HANDLE` forward that carries THAT lease's
   token in the report's `continuation` fence (per lease: one forwarded handle never clears a second
   live lease) - status-blind, including `BLOCKED` / `NEEDS_CONTEXT`. After a delivered handback
   the report is final, so the `SubagentStop` block then offers release or park only. Browser findings are ADVISORY only on both `SubagentStop`
   and `Stop` - see `resource-teardown-contract.md` "Why browsers and instances are enforced
   differently".
3. **`SessionEnd` backstop** (`hooks/session-end-gc.sh`) - scoped to the ENDING session plus
   provably dead owners, never other sessions' live work. The hook captures this session's anchor,
   spawns a detached worker and returns at once (a SessionEnd hook is aborted about a second after
   its batch siblings finish; the hook header records the measurement). The worker runs
   `gc --scope dead-sessions` (ended sessions past `ANCHOR_GRACE_S`, dead or recycled server pids,
   expired parks - never the TTL arm), waits for this session's anchor process to exit, then runs
   `gc --scope anchor` for this session's running and reserved leases; a parked lease survives the
   session by design, and a lease resumed or adopted out of a park is parked again rather than
   dropped (`owner.return_to_park`). Finally it runs `reap-orphans` in list-only mode. Flow diagram:
   `INSTANCE-ALLOCATION-RECLAIM.md` §7.2.
4. **Explicit human sweep** - `lease_gc` / `allocator.py gc` (dry run first) and
   `allocator.py reap-orphans --yes` against the persisted candidate list. Each `lease_gc` row
   carries `action: reclaim` (server stopped, throwaway database dropped, lease deleted) or
   `action: park` (a lease resumed out of a park goes back to it, database and ports kept); a real
   run lists the re-parked token prefixes in `parked`. Only an explicit
   `gc --scope all` applies the legacy TTL arm to a lease whose liveness cannot be proven.

A crashed session (`-9`, OOM) runs neither layer 2 nor layer 3 for itself: its leases stay
protected for the grace window after their last touch (so `claude --resume` can re-anchor them) and
are then reclaimed by the next session to end on this host.

Wiring for the hooks (`PreToolUse` / `SubagentStop` / `Stop` / `SessionEnd` registration) lives in
`hooks/hooks.json`; this section is a map, not a copy of their internals.
