# Odoo instance allocation - reclaim, staleness and failure modes

Part of `docs/reference/INSTANCE-ALLOCATION.md` (index: status, audience, problem, constraints,
goals, and the full parts map). This file owns how a held resource is given back when nobody
released it: the registry-independent orphan sweep, the staleness verdict, the failure-mode
matrix, and the TTL that governs the liveness-unprovable bucket.

### 6.5 `reap-orphans` - DB-side sweep independent of the lease registry

`gc` (`INSTANCE-ALLOCATION-API.md` §6, §7) only ever reclaims a DB that a LEASE still references - it drops the DB attached to
a stale lease. It has no path for a DB that exists with ZERO lease reference at all: a lease-write
that never reached disk (a registry quarantine after corruption - §7's "torn/corrupt registry"
case, an ancient pre-B2 allocator that created the DB directly, or a crash in the single narrow
window between reserving a db_name and the lease write landing). Such a DB was, before this
command existed, permanently untraceable and unreapable by any registry-driven path.
`allocator.py reap-orphans` closes that gap with an explicit, auditable ownership predicate (see
the API table in `INSTANCE-ALLOCATION-API.md` §6) rather than an automatic/background sweep: every axis fails CLOSED (an
unreachable cluster is skipped, not assumed empty; an unmeasurable age is skipped, not assumed old
enough; any leased db_name, even stale, is left to `gc`/`release`), and the default is list-only -
`--yes` is required to actually drop anything, so a sweep is always a visible read before it is
ever destructive.

That second axis - "any leased db_name, live OR stale" - is also what keeps this second destructive
reclaimer away from a PARKED lease, with no park-specific branch of its own: a parked lease is
still a row in the registry naming its `db_name`, so its database can never even be LISTED as an
orphan candidate.

**Wired (discovery half only).** `hooks/session-end-gc.sh` - the SessionEnd crash backstop that
already ran `gc` on every session's end - now ALSO runs `reap-orphans` in its default list-only
mode immediately after `gc`, in the hook's DETACHED worker (the hook returns at once; work left
running under a SessionEnd hook is killed about a second after the batch's siblings finish, which
used to leave this very log truncated to 0 bytes - see the hook's header), persisting the candidate
list to
`${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime/reap-orphans-candidates.log` (never `/dev/null`, so the
list is actually reviewable). `gc`'s own stderr is persisted the same way, to
`${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/allocator-stderr.log` - the machine-global account both
implicit reclaimers (this hook and 50-instance-spinup.sh's shared-lease registration) append to,
carrying the RECLAIMED notice plus the refusal/failed-drop lines that have no JSONL counterpart. This is the DISCOVERY half only: the hook
NEVER passes `--yes`. SessionEnd is silent and unattended by its own contract (no decision is ever
emitted), so an automatic drop there would remove the one property `reap-orphans` was designed
around - a visible, auditable read before anything destructive happens - and would let one
session's end drop a database created entirely outside that session's own leases (`reap-orphans`
scans the WHOLE declared cluster, not a per-session scope). The destructive half stays a separate,
deliberate, human-run `allocator.py reap-orphans --yes` against the persisted candidate log -
never automatic. Before this wiring, `reap-orphans` had no caller anywhere in the plugin at all;
its mechanics (ownership predicate, fail-closed age proof) were correct and tested in isolation,
but unreachable in practice.

## 7. Crash / stale handling

- Owner records `host`+`pid`+`pid_started`+`run_id`+`started_at` (a legacy lease may carry
  `session_id` instead of `run_id` - read as a fallback). **Liveness is authoritative, not a
  mere condemn signal.** `_is_stale` (`scripts/lib/allocator.py`):
  - A PARKED lease (`parked_at` present) is judged FIRST, by its own budget and by nothing else,
    and the arm's position ahead of the host/pid block is load-bearing: park CLEARS the owner pid
    on purpose, so every arm below would read the row as "no pid recorded" and hand it to TTL -
    reclaiming a deliberately suspended instance, and dropping its database, for the act of
    suspending it. Past `park_ttl_s` the reason is `park-budget-expired`. If `parked_boot_id` and
    this boot's id BOTH exist and DIFFER, the host rebooted under the park, so the budget was
    never consumed: the row is protected and stays resumable. Either id absent (not Linux, or a
    container reporting the host's) degrades to the plain budget comparison - never to a condemn
    on ambiguity, and never to a permanent reprieve. `resume` deletes `parked_at`, which is what
    returns the lease to the arms below.
  - A DEAD owner pid on THIS host is an unambiguous, TTL-independent condemn - the recorded owner
    is provably gone.
  - A LIVE owner pid on THIS host PROTECTS the lease REGARDLESS OF `ttl_s` - but only when the
    `pid_started` fingerprint captured at record time still matches the process currently holding
    that pid, which is what rules out a pid-recycled impostor (a bare `os.kill(pid,0)` cannot tell
    the two apart - pids are reused by the OS over a machine's lifetime). A POSITIVE fingerprint
    mismatch (the pid was recycled onto a different process) condemns immediately, same as a dead
    pid - the recorded owner is exactly as gone.
  - Every case where liveness cannot be proven at all - a DIFFERENT host (the pid integer is
    meaningless off-host), no pid ever recorded, or a fingerprint that could not be re-measured
    (not a proven mismatch) - falls back to `now - heartbeat_at > ttl_s`, exactly as before this
    fix. This is the ONLY case `heartbeat` still matters for; call it on any long operation whose
    lease cannot carry a locally-verifiable pid.
  - **Direction, stated explicitly so a future edit does not invert it:** for reaping, the safe
    default is to NOT reap when unsure - an un-reaped orphan only costs RAM, but a wrongly-reaped
    lease kills a live server and destroys the owner's in-progress work. See `_is_stale`'s
    docstring in `scripts/lib/allocator.py` for the full writeup; §12 covers why `DEFAULT_TTL_S`
    was reconsidered under this narrower scope.
- GC runs opportunistically at the start of every `acquire` (no daemon needed); it can also be
  invoked directly via `allocator.py gc`.
- Registry write is atomic (temp + `os.replace`); a torn/corrupt registry is detected (JSON parse
  fail) and quarantined to `leases.json.bak` with a fresh empty registry, logged loudly.

## 8. Failure modes & edge cases

| Risk | Mitigation |
|------|------------|
| Two allocators pick the same port | flock serialises the RMW; only one writes the lease; the loser re-scans. Plus a live `bind()` probe rejects a port already taken by a non-allocator process. |
| Ephemeral db name collision | uuid8 suffix; Odoo create-on-init failure -> caller can retry with a new acquire. |
| Agent dies mid-run | GC reclaims immediately by dead pid (same host); a same-host process that SURVIVES the agent (a detached orphan) is deliberately NOT reclaimed while verified alive - only TTL, for the different-host/no-pid/unverifiable case, or an explicit release/reap eventually clears it. Drops through Odoo (`odoo_db.py`), raw `dropdb` fallback. |
| Postgres unreachable | `acquire` fails fast with a clear message; never silently shares a DB. |
| `$ODOO_AI_HOME` on a network FS without working flock | documented requirement: registry must live on a local FS; setup checks and warns. |
| Old `instances.toml` with no pool fields | derive pool from `http_port`; fully backward compatible. |
| Host reboots while a lease is parked | `parked_boot_id` (§7) differs from the current boot id, so the park budget is treated as NOT started: the row is protected and stays resumable. A reboot means nobody consumed the park, and a perfectly resumable database must not be dropped because the machine restarted. `resume` re-stamps the current boot id. |
| The parked lease's database was dropped externally | TWO probes, and only the FIRST one is pre-launch. (1) `query --state parked` probes `_db_present` and SKIPS a lease whose database is provably gone, naming `release <token>`: the caller never receives coordinates, so nothing is launched. (2) `resume` probes again and refuses with exit 5 for the window between the two. `release` then handles that lease on its own `present is False` branch (removes the filestore, reports `ALLOC_FORGOTTEN_DB`, `INSTANCE-ALLOCATION-GUARDS.md` §6.7). An UNDETERMINABLE probe refuses at neither rung - stranding a resumable instance on an unanswered question is the worse error. |
| Port collision on resume | The parked lease still holds its `ports` in the registry, so no allocator caller can take them; a non-allocator process still can. That case is caught by `50-instance-spinup.sh`'s identity-marker/attach guard (`_write_identity_marker`/`_identity_ok`, `INSTANCE-ALLOCATION-MODES.md` §5 P6.2), which runs BEFORE any launch and refuses to treat a foreign listener on that port as "my instance is up". `resume` is NOT that guard and cannot be: it corroborates a live pid, so it necessarily runs after the launch. |
| Two agents race to resume one parked lease | The lease can only be won once: `resume` is a locked compare-and-set REQUIRING `parked_at`. Both racers have already launched a server by then (resume needs a live pid to corroborate), so the guarantee is about what happens NEXT, not about preventing the second launch: the first caller clears `parked_at`; the second finds a LIVE same-host owner pid on the lease and is refused with exit 6 - a code distinct from exit 3 precisely so its caller stops the server it just launched instead of `bind`ing over the winner. `50-instance-spinup.sh` stops that process group and fails the apply. |
| A resume refused AFTER the launch (exits 1/4/5/6) | THE INVARIANT: no path may end with a live server the teardown gate cannot see. A refused resume leaves the lease PARKED, and `hooks/enforce-teardown.sh` skips a parked row as "not a leak" - so a server left running behind it would be invisible to the one gate that blocks RAM leaks. `50-instance-spinup.sh::_bind_exclusive` therefore STOPS the process group it just launched and FAILS the apply; the lease is left exactly as it was (parked, holding its database, filestore and ports), so the caller can still release or re-resume it. |

## 9. TTL default

`ttl_s` defaults to `DEFAULT_TTL_S = 7200` (2h) in `scripts/lib/allocator.py` (SSOT). It governs
only the liveness-unprovable bucket (different host, no pid recorded, unverifiable fingerprint) -
a same-host owner with a verified-alive pid is NEVER TTL-reclaimed. Call `heartbeat <token>` on
any long operation in that bucket.
