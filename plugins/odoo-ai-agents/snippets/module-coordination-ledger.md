<!-- SSOT snippet. Authoring-owned by odoo-planning; WRITTEN at runtime only by odoo-coding.
     On-disk claim/status registry so concurrent runs/worktrees see which NEW modules are being
     built where, letting `BLOCKED: manifest dependency <D> unresolved` be classified instead of
     guessed. WRITTEN ONLY by odoo-coding; the hard-leaf odoo-backend-coder/odoo-frontend-coder
     workers (and the odoo-coder lead relaying a raw BLOCKED) stay ledger-unaware. Referenced
     (not copy-pasted) by odoo-coding and run-harness. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md. -->

# Module Coordination Ledger (cross-run / worktree)

The per-run dependency pre-flight (`agents/odoo-backend-coder.md § Dependency pre-flight`)
already converts every unresolved `depends` into a graceful `BLOCKED: manifest dependency <D>
unresolved on addons-path`. This ledger adds the one thing a single run cannot see: whether `<D>`
is being built right now by a different run/worktree, was already built elsewhere, or is
genuinely absent - so `odoo-coding` can turn that raw BLOCKED into a specific, evidence-backed
decision.

**Scope note.** Every source-writing node's worktree forks from the ONE `run-integration` branch
(lineage: `run-harness/SKILL.md` § Run start), so it always CONTAINS its dependencies' committed
source - but that is not the same as the source being on the verification instance's addons-path
(the allocator's catalog list points at the principal checkout by default). Reaching it is a
POLICY step: the node's brief carries `WORKTREE_PATH` + `SELF_PROVISION: worktree-addons`
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out), set by
`odoo-coding` on every source-writing dispatch naming a `WORKTREE_PATH`. With that step taken,
this ledger backstops ONLY cross-run coordination + the manifest-crash safety net; the intra-run
false BLOCKED no longer fires.

## Location and why the SHARE dir

Resolve the ledger root ONCE per run via the Tier-2 SHARE resolver (policy + tables:
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), following its
resolve-capture-substitute protocol:

```bash
SHARE_DIR="$(bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share)"
LEDGER_ROOT="$SHARE_DIR/coordination/modules"
```

Each module's entry lives at `$LEDGER_ROOT/<module>/entry.json`.

WHY SHARE (not ISOLATE): keyed off `sha256(realpath(git rev-parse --git-common-dir))` - the same
path for every linked worktree, so a per-worktree ISOLATE dir (blind to a sibling's claim) does
not fit. Do NOT collapse this to a bare `$ODOO_AI_HOME/coordination/` - two unrelated repos on
one host would then see each other's claims.

**No git repo, no project marker (resolver refuses).** If `resolve_project_dir.sh share` fails,
degrade to per-run behavior with NO ledger (the per-run pre-flight still produces graceful
BLOCKEDs) and LOG that the ledger was unavailable. Never fabricate a ledger location.

## Entry schema

`entry.json` is a single JSON object:

```json
{
  "module": "<technical name>",
  "status": "claimed|building|done|failed",
  "run_id": "<the worklog run-or-slug - REUSE it, do NOT mint a new id>",
  "worktree": "<absolute path of the worktree building this module>",
  "claimed_at": "<UTC timestamp>",
  "heartbeat_at": "<UTC timestamp>"
}
```

- `run_id` REUSES the worklog run-or-slug (`snippets/worklog-contract.md`) - never a
  freshly-minted ledger id - so an entry traces back to its owning run.
- Timestamps are UTC, portable: `date -u +%Y-%m-%dT%H:%M:%SZ`.

## Ownership - `odoo-coding` is the sole writer

ONLY `odoo-coding` writes the ledger: it owns the NEW-module build boundary and the DONE barrier,
so it is the only actor that knows when a module transitions state.

- **WRITE - `odoo-coding` alone.** No other actor writes an entry or status.
- **READ for coordination decisions - `odoo-coding` alone.** It reads its own ledger to run
  § Decision table and drive the bounded N-barrier WAIT internally (§ N-barrier WAIT ownership).
- **The hard-leaf `odoo-backend-coder`/`odoo-frontend-coder` workers stay LEDGER-UNAWARE** (as
  does the `odoo-coder` coordinator) - they never read or write `$LEDGER_ROOT`; only
  `odoo-backend-coder` runs § Dependency pre-flight and emits a RAW `BLOCKED: manifest dependency
  <D> unresolved on addons-path` (the coordinator relays it up unchanged).
- **`run-harness` neither writes the ledger nor drives any ledger decision.** It receives
  `odoo-coding`'s already-classified BLOCKED and runs its saga path; it may read the ledger
  read-only for its own execution log, but never runs the WAIT or decision table.

The ledger write is neither a worklog entry (`snippets/worklog-contract.md`) nor a
Continuation-Contract dispatch (`snippets/continuation-contract.md`) - it is per-module shared
cross-run coordination state with a single writer (`odoo-coding`).

## N-barrier WAIT ownership - `odoo-coding` owns it internally

`odoo-coding` owns the ENTIRE WAIT/re-queue loop internally and transparently to its caller: it
waits, bounded by N dispatch-loop barriers (§ Staleness), for a concurrent build to land. This
bounded barrier covers TWO triggers: decision-table case 3 (a manifest dependency claimed by a
DIFFERENT run) is its documented trigger; a lost claim (EEXIST) on THIS run's OWN node - claiming
a module in this node's own `modules` list that another run already holds - EXTENDS the same
mechanism rather than inventing a second one (§ Claim = atomic `mkdir` below). Because a node can
claim several modules at once, the staleness window is WIDER than a single-module claim's: any
claimed-but-not-yet-`done` module going stale reopens the wait. When the wait is EXHAUSTED with no
progress it returns a clean `BLOCKED` (case 6) - `run-harness` treats that like any other BLOCKED,
never re-implementing a barrier wait of its own.

## Claim = atomic `mkdir` (no flock, no lock file)

**The claimant is the node; the claim key stays the module technical name.** A node's `modules`
list may name several modules (5.2/D4) - `odoo-coding` claims EVERY one before dispatching the
node's single `odoo-coder`, never a subset, never one at a time across separate dispatches. A
node id is run-local (never collides cross-run); the module technical name is the key that does.

**Claim order is ASCENDING TECHNICAL-NAME order, always - never dependency order.** Lock
acquisition needs a TOTAL order independent of the plan: dependency order leaves independent
modules unordered, so two runs claiming the same pair as `[m1, m2]` and `[m2, m1]` could deadlock
on each other. Dependency order governs the `-i` install list, not the lock sequence.

To claim ONE module in that ordered list, before dispatching the node's coder:

```bash
# BOOTSTRAP - run ONCE per run, before any per-module claim (idempotent; makes the per-module
# mkdir below fail ONLY for EEXIST, never ENOENT).
mkdir -p "$LEDGER_ROOT"

MODULE="<technical name>"
# Per-module claim: BARE atomic mkdir (never `mkdir -p`). Capture stderr to distinguish EEXIST
# (lost claim) from any other error.
if err="$(mkdir "$LEDGER_ROOT/$MODULE" 2>&1)"; then
    # WON: write entry.json status:claimed.
    date_now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"module":"%s","status":"claimed","run_id":"%s","worktree":"%s","claimed_at":"%s","heartbeat_at":"%s"}\n' \
        "$MODULE" "$RUN_ID" "$WORKTREE" "$date_now" "$date_now" > "$LEDGER_ROOT/$MODULE/entry.json"
elif [ -d "$LEDGER_ROOT/$MODULE" ]; then
    # LOST (EEXIST): another run/worktree owns it. Read its entry.json, classify via § Decision table.
    cat "$LEDGER_ROOT/$MODULE/entry.json"
else
    # ANY OTHER error: not a competing owner. Surface it and BLOCK - never proceed as claimed.
    printf 'ledger claim error for %s: %s\n' "$MODULE" "$err" >&2
fi
```

`mkdir` of a single directory is ONE POSIX syscall that atomically succeeds for exactly one caller
and returns `EEXIST` to every other - the winner creates the dir and writes `entry.json`; the
losers read the existing entry. No `flock`, no lock file, no race window: the directory's
existence IS the lock. The `elif [ -d ... ]` / `else` split distinguishes EEXIST (a lost claim -
read the entry, run § Decision table) from any OTHER error (permission, ENOSPC, ENOENT), which is
surfaced and BLOCKS instead. Two rules never bend: `$LEDGER_ROOT` is pre-created ONCE with
`mkdir -p` (never per-module), and the per-module claim is the BARE atomic `mkdir` (never
`mkdir -p`, which would succeed on an existing dir and destroy the mutual exclusion).

**On EEXIST for any module while claiming a node's list, do NOT release the claims this node's
loop already won.** Keep every already-claimed module `claimed` exactly as-is, and re-queue the
WHOLE node behind the existing bounded N-barrier (§ N-barrier WAIT ownership above) - the same
barrier, extended to a second trigger, not a new mechanism. **No release / un-claim / `rmdir`
primitive exists, and none is added:** `rmdir` would destroy the mutual-exclusion lock this
ledger IS, and flipping a held claim to `failed` would send every other run watching it to
decision-table case 5 (`BLOCKED: prerequisite module <D> failed in run <X>`) - a permanent false
BLOCKED for a module that did not fail. A node that wins some claims and loses one simply waits,
still holding the ones it won, until the barrier resolves or exhausts to a clean case-6
`BLOCKED`. The state machine stays exactly `claimed -> building -> done | failed` - no fifth
value, no release transition.

## State transitions (`odoo-coding` performs each)

- **claimed** - on winning the `mkdir` claim, before the coder is dispatched.
- **building** - flip when the module's coder is actually dispatched.
- **done** - flip on the module's DONE (built + reviewed + committed).
- **failed** - flip on a terminal BLOCK for the module.
- **heartbeat_at** - refresh to current UTC time on EVERY dispatch-loop tick for each module
  currently `building`, so other runs can tell live from dead.
- **building -> failed (dead-dispatch, immediate, no staleness wait)** - the ONE transition that
  skips the N-tick staleness bound (§ Honesty invariant below): flip a module from
  `building` to `failed` the instant its `odoo-coder` dispatch resolves WITHOUT a parseable
  Continuation Contract - a harness-level dispatch error, an empty return, or output
  that does not parse to one of the four terminal `status` values
  (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`). This is DISTINCT from a stale
  heartbeat (absence of evidence, bounded by ticks): a dead-dispatch signal is fresh, provable
  evidence the dispatch ended, so the module never sits at `building` with a live-looking
  heartbeat. (What counts as "resolves without a parseable Continuation Contract"
  is defined at `skills/odoo-coding/SKILL.md` § Reacting to a dead-dispatch signal.) Fail CLOSED:
  on any doubt whether the dispatch produced a real report, flip to `failed` rather than leave the
  module `building` - never the reverse (never flip a module that DID return a valid report to
  `failed` on a mere suspicion).

On run completion, `odoo-coding` sets each of its own modules to `done` or `failed` - it never
leaves its own entries dangling in `claimed`/`building`.

## Decision table - classify `BLOCKED: manifest dependency <D> unresolved`

Evaluated by `odoo-coding` only (it holds the batch map + DONE barrier + reads the ledger) - never
the leaf coder. Evaluate the cases IN ORDER; first match wins:

1. **`D` is on the effective `--addons-path`** (OSM/disk resolvable) -> false alarm; re-run the
   pre-flight and PROCEED.
2. **`D` is an in-set sibling of THIS run still `claimed`/`building`** (dispatched, not yet DONE,
   not `failed`) -> a dispatch-ordering error in this run; RE-QUEUE `D`'s dependent after the
   sibling reaches DONE. A same-run sibling already `failed` does NOT match here (it will never
   complete, so re-queuing would loop forever) - falls through to case 5.
3. **Ledger shows `D` `claimed`/`building` by a DIFFERENT `run_id` with a FRESH heartbeat** ->
   WAIT / re-queue, bounded by N barriers (§ Staleness); after N barriers with no progress, demote
   to case 6.
4. **Ledger shows `D` `done` but `D` is NOT on this worktree's addons-path** -> `BLOCKED:
   dependency <D> was built in run <X> - integrate/rebase it onto this worktree before
   continuing`. Fires ONLY cross-run: intra-run the worktree already contains `D`'s committed
   source (fork-from-integrated-parent lineage, `run-harness/SKILL.md` § Run start), and
   `SELF_PROVISION: worktree-addons` re-roots the verification instance onto it - a POLICY
   guarantee (§ Scope note above), not structural.
5. **Ledger shows `D` `failed`** (THIS run's own sibling OR a different run - a terminally failed
   module never completes) -> `BLOCKED: prerequisite module <D> failed in run <X>`.
6. **`D` absent from the ledger OR its heartbeat is stale (dead run)** -> clean `BLOCKED: missing
   prerequisite module <D>`.

The cases are mutually exclusive, evaluated first-match-wins: a same-run `failed` sibling is
excluded from case 2, misses 3 (same `run_id`) and 4 (not `done`), landing on case 5 - never the
case-2 re-queue that would loop.

## Honesty invariant - absence is always the honest fallback

A run that never writes the ledger, or a dead/stale run, lands in case 6 as a clean BLOCKED -
never a false "in progress". The ledger only ever UPGRADES a case-6 BLOCKED to a more specific
status (cases 3/4/5) when a FRESH entry proves it; it never downgrades a real absence into a fake
"someone is building it". On any doubt, default to case 6.

**Staleness is measured in dispatch-loop ticks, not wall-clock.** A `claimed`/`building` entry is
STALE when its `heartbeat_at` has not advanced across a bounded number of ticks (default: 3, same
bound as the code -> review loop) - treated as a dead run, falling to case 6. Do not use a
wall-clock timeout: a slow build and a dead build look identical on the clock, but a live build
advances its heartbeat every tick and a dead one never does.
