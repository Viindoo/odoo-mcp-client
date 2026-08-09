<!-- SSOT snippet. Authoring-owned by odoo-planning; WRITTEN at runtime only by odoo-coding. The
     single source of truth for the cross-run / worktree
     module-coordination ledger (Q3): the on-disk claim/status registry that lets concurrent runs
     and linked worktrees see which NEW modules are being built where, so a `BLOCKED: manifest
     dependency <D> unresolved` can be classified honestly instead of guessed. WRITTEN ONLY by
     odoo-coding; the hard-leaf odoo-backend-coder/odoo-frontend-coder workers (and the odoo-coder
     lead that relays a worker's raw BLOCKED) stay ledger-unaware. Referenced (not
     copy-pasted) by odoo-coding and run-harness's between-wave integration. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md. -->

# Module Coordination Ledger (cross-run / worktree)

The per-run dependency pre-flight (`agents/odoo-backend-coder.md § Dependency pre-flight`) already converts
EVERY unresolved `depends` into a graceful `BLOCKED: manifest dependency <D> unresolved on
addons-path` - the raw Odoo manifest crash is fixed independent of this ledger. This ledger adds the
ONE thing a single run cannot see on its own: whether `<D>` is being built RIGHT NOW by a different
run or worktree, was already built elsewhere, or is genuinely absent. It exists so `odoo-coding` can
turn that raw BLOCKED into a specific, evidence-backed decision.

**Scope note (Block 2W).** Every wave's worktrees fork from the ONE `run-integration` branch, so a
dependent wave's worktree always CONTAINS its dependencies' committed source by construction - but
containing the source is NOT the same as that source being on the verification instance's
addons-path (the allocator emits the CATALOG addons list, pointing at the principal checkout, by
default). Reaching the addons-path is a POLICY step: the per-module brief must carry
`WORKTREE_PATH` + `SELF_PROVISION: worktree-addons`
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out), which
`odoo-coding` sets on EVERY per-module dispatch naming a `WORKTREE_PATH`. With that policy step
taken, this ledger and the `odoo-backend-coder` dependency pre-flight now backstop ONLY concurrent
INDEPENDENT runs (cross-run) + the manifest-crash safety net; the intra-run false BLOCKED no
longer fires.

## Location and why the SHARE dir

Resolve the ledger root ONCE per run via the Tier-2 SHARE resolver (full policy + classification
tables: `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), following its mandatory
resolve-capture-substitute protocol:

```bash
SHARE_DIR="$(bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share)"
LEDGER_ROOT="$SHARE_DIR/coordination/modules"
```

Each module's entry lives at `$LEDGER_ROOT/<module>/entry.json`.

WHY SHARE (not ISOLATE): the SHARE dir is keyed off `sha256(realpath(git rev-parse --git-common-dir))`
- the SAME resolved path for every linked worktree and every concurrent invocation of THIS repo, so
a per-worktree ISOLATE dir (which would go blind to a claim made in a sibling worktree) is never a
fit here. Do NOT collapse this to a bare `$ODOO_AI_HOME/coordination/` (cross-project-global) - two
UNRELATED repos on the same host would then see each other's module claims.

**No git repo and no project marker (resolver refuses).** If `resolve_project_dir.sh share` fails,
there is no shared ledger: degrade to per-run behavior with NO ledger (the per-run pre-flight
still produces graceful BLOCKEDs), and LOG that the ledger was unavailable outside the repo. Never
fabricate a ledger location.

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

- `run_id` REUSES the worklog run-or-slug (`snippets/worklog-contract.md`) - one id per run, never a
  freshly-minted ledger id, so a ledger entry is traceable back to the run that owns it.
- Timestamps are UTC and portable: `date -u +%Y-%m-%dT%H:%M:%SZ`.

## What gets claimed - every module a coordinator will WRITE

An `odoo-coder` coordinator's `MODULE SCOPE` is 1..N modules and it writes across all of them
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier decomposition axis), so
`odoo-coding` CLAIMS **every module in a scope before dispatching it** - not only NEW ones. NEW
modules still drive the § Decision table (a `BLOCKED: manifest dependency <D> unresolved` is only
classifiable against build state); an EXISTING module's claim has no decision-table role and exists
solely to make "exactly ONE coordinator writes a module at a time" enforced rather than hoped, now
that a coordinator is not implicitly limited to one module. Without it two scopes in different runs
could both list the same existing module and silently collide.

**Scope EXPANSION.** A coordinator needing a module its scope omits returns
`NEEDS_CONTEXT(module <m> required but not in MODULE SCOPE)`; it never claims or writes `<m>`.
`odoo-coding` attempts the claim: on a WIN it re-dispatches that coordinator with `<m>` added (and
drops `<m>` from any not-yet-dispatched scope, preserving disjointness); on a LOSS it classifies
`<m>` via the § Decision table like any contested module. Record the expansion in plan.md - a later
fix/resume step re-dispatches from that scope map, so an unrecorded expansion makes it lie.

## Ownership - `odoo-coding` is the sole writer

ONLY `odoo-coding` writes the ledger: it owns the module build boundary and the DONE barrier, so
it is the only actor that knows when a module transitions state.

- **WRITE - `odoo-coding` alone.** No other actor ever writes an entry or a status.
- **READ for coordination decisions - `odoo-coding` alone.** It reads its own ledger to run the
  § Decision table and to drive the bounded N-barrier WAIT INTERNALLY (§ N-barrier WAIT ownership).
- **The hard-leaf `odoo-backend-coder`/`odoo-frontend-coder` workers stay LEDGER-UNAWARE** (as does
  the `odoo-coder` coordinator, INCLUDING for a scope expansion - it reports the needed module up
  and `odoo-coding` does the claiming) - they never read or write `$LEDGER_ROOT`; only `odoo-backend-coder`
  runs the § Dependency pre-flight and emits a RAW `BLOCKED: manifest dependency <D> unresolved on
  addons-path` (the coordinator relays it up unchanged).
- **`run-harness`'s between-wave integration neither writes the ledger nor drives any ledger
  decision.** It receives `odoo-coding`'s already-classified BLOCKED and runs its saga path; it may
  read the ledger read-only for its own execution-log, but never runs the WAIT or the decision table.

The ledger write is NOT a worklog entry (`snippets/worklog-contract.md`) and NOT a
Continuation-Contract dispatch (`snippets/continuation-contract.md`) - per-module shared cross-run
coordination state with a single writer (`odoo-coding`).

## N-barrier WAIT ownership - `odoo-coding` owns it internally

`odoo-coding` owns the ENTIRE decision-table case-3 WAIT/re-queue loop internally and transparently
to its caller: it waits, bounded by N dispatch-loop barriers (§ Staleness), for a concurrent build to
land. When the bounded wait is EXHAUSTED with no progress it returns a normal clean `BLOCKED`
(case 6) - the caller (`run-harness`'s between-wave integration) treats that like any other BLOCKED
and never re-implements a barrier wait of its own.

## Claim = atomic `mkdir` (no flock, no lock file)

To claim a module before dispatching the coordinator whose scope contains it (every module in the scope, not only NEW ones - see § What gets claimed):

```bash
# BOOTSTRAP - run ONCE per run, before ANY per-module claim. Pre-create the shared parent tree.
# `mkdir -p` here is REQUIRED and safe (idempotent): on the very first use $LEDGER_ROOT does not
# exist yet, so the BARE per-module `mkdir` below would fail with ENOENT (missing parent), which
# with `2>/dev/null` would be silently misread as a lost claim (EEXIST) and then `cat` a
# nonexistent entry. Creating the parent up front makes the per-module mkdir fail ONLY for EEXIST.
mkdir -p "$LEDGER_ROOT"

MODULE="<technical name>"
# Per-module claim: the BARE atomic mkdir (NEVER `mkdir -p` on the per-module dir - `-p` succeeds on
# an already-existing dir and would defeat the mutual exclusion). Capture stderr so an EEXIST lost
# claim is distinguished from any OTHER error rather than swallowed.
if err="$(mkdir "$LEDGER_ROOT/$MODULE" 2>&1)"; then
    # WON the claim: this run created the dir. Write entry.json status:claimed.
    date_now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"module":"%s","status":"claimed","run_id":"%s","worktree":"%s","claimed_at":"%s","heartbeat_at":"%s"}\n' \
        "$MODULE" "$RUN_ID" "$WORKTREE" "$date_now" "$date_now" > "$LEDGER_ROOT/$MODULE/entry.json"
elif [ -d "$LEDGER_ROOT/$MODULE" ]; then
    # LOST the claim (EEXIST): the dir already exists -> another run/worktree owns it. Read its
    # entry.json and classify via the § Decision table.
    cat "$LEDGER_ROOT/$MODULE/entry.json"
else
    # ANY OTHER error (permission, ENOSPC, a parent that vanished, ...): the claim did NOT fail
    # because of a competing owner. Do NOT misread it as a lost claim - SURFACE it and BLOCK.
    printf 'ledger claim error for %s: %s\n' "$MODULE" "$err" >&2
    # -> BLOCKED: ledger claim failed - see stderr; never proceed as if the module were claimed.
fi
```

`mkdir` of a single directory is ONE POSIX syscall that atomically succeeds for exactly one caller
and returns `EEXIST` to every other - the winner creates the dir and writes `entry.json`; the losers
read the existing entry. No `flock`, no lock file, no race window: the directory's existence IS the
lock. The per-module claim MUST distinguish EEXIST (a lost claim - the dir already exists, so read
the entry and run the § Decision table) from any OTHER error (permission, ENOSPC, ENOENT) - the
`elif [ -d ... ]` / `else` split does exactly this: only EEXIST is a lost claim; every other error is
surfaced and BLOCKS. Two rules never bend: the parent `$LEDGER_ROOT` is pre-created ONCE with
`mkdir -p` (never per-module), and the per-module claim is the BARE atomic `mkdir` (never `mkdir -p`,
which would succeed on an existing dir and destroy the mutual exclusion).

## State transitions (`odoo-coding` performs each)

- **claimed** - on winning the `mkdir` claim, before the coder is dispatched.
- **building** - flip when the module's coder is actually dispatched.
- **done** - flip on the module's DONE (built + reviewed + committed).
- **failed** - flip on a terminal BLOCK for the module.
- **heartbeat_at** - refresh to the current UTC time on EVERY dispatch-loop tick for each module this
  run is currently `building`, so other runs can tell a live build from a dead one.
- **building -> failed (dead-dispatch, immediate, no staleness wait)** - the ONE transition that does
  NOT wait for the N-tick staleness bound (§ Honesty invariant below): flip a module straight from
  `building` to `failed` the instant its `odoo-coder` dispatch resolves WITHOUT a parseable
  Continuation Contract - a harness-level dispatch error, an empty/content-less return, or output
  that does not parse to one of the four terminal `status` values
  (`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`). This is DISTINCT from a stale
  heartbeat (an ABSENCE of fresh evidence, bounded by ticks): a dead-dispatch signal IS fresh, PROVABLE evidence the dispatch
  ended, so `odoo-coding` never leaves that module's entry sitting at `building` with a heartbeat that
  keeps looking recent to every OTHER run watching the ledger - a live-looking heartbeat on a module
  whose dispatch has already terminated would actively mislead a concurrent run into treating a dead
  build as in-progress (§ Reacting to a dead-dispatch signal in `skills/odoo-coding/SKILL.md`, in your
  own dispatch loop, defines exactly what counts as "resolves without a parseable Continuation
  Contract" - do not re-derive it here). Fail CLOSED: on any doubt whether the dispatch produced a
  real report, treat it as dead-dispatch (flip to `failed`) rather than leave the module `building` -
  never the reverse (never flip a module that DID return a valid report to `failed` on a mere
  suspicion).

On run completion, `odoo-coding` sets each of its own modules to `done` or `failed` - it never leaves
its own entries dangling in `claimed`/`building`.

## Decision table - classify `BLOCKED: manifest dependency <D> unresolved`

Evaluated by `odoo-coding` (it alone holds the batch map + DONE barrier + reads the ledger); NEVER by
the leaf coder. Evaluate the cases IN ORDER; the first match wins:

1. **`D` is on the effective `--addons-path`** (OSM/disk resolvable) -> false alarm; re-run the
   pre-flight and PROCEED.
2. **`D` is an in-set sibling of THIS run still `claimed`/`building`** (dispatched, not yet DONE and
   NOT `failed`) -> a dispatch-ordering error in THIS run; RE-QUEUE `D`'s dependent after the sibling
   reaches DONE (this run's own bug, not an environment problem). A same-run sibling ALREADY in
   `failed` does NOT match here - it will never complete, so a re-queue would loop forever; it falls
   through to case 5.
3. **Ledger shows `D` `claimed`/`building` by a DIFFERENT `run_id` with a FRESH heartbeat** ->
   WAIT / re-queue, bounded by N barriers (§ Staleness); after N barriers with no progress, demote to
   case 6.
4. **Ledger shows `D` `done` but `D` is NOT on this worktree's addons-path** -> `BLOCKED: dependency
   <D> was built in run <X> - integrate/rebase it onto this worktree before continuing`. This now
   fires ONLY cross-run: intra-run, the worktree already CONTAINS `D`'s committed source (Block 2W's
   fork-from-integrated-parent lineage), and `odoo-coding` sets `SELF_PROVISION: worktree-addons` on
   every per-module dispatch naming `WORKTREE_PATH`, so the verification instance is re-rooted onto
   that same worktree - a POLICY guarantee enforced at dispatch time (§ Scope note above), not a
   structural one.
5. **Ledger shows `D` `failed`** (THIS run's own sibling OR a different run - a terminally failed
   module never completes) -> `BLOCKED: prerequisite module <D> failed in run <X>`.
6. **`D` absent from the ledger OR its heartbeat is stale (dead run)** ->
   clean `BLOCKED: missing prerequisite module <D>`.

The cases are mutually exclusive and evaluated first-match-wins: a same-run `failed` sibling is
excluded from case 2, does not match 3 (same `run_id`) or 4 (not `done`), and lands cleanly on
case 5 - never on the case-2 re-queue that would loop.

## Honesty invariant - absence is always the honest fallback

A run that NEVER writes the ledger, or a dead/stale run, lands in case 6 as a clean BLOCKED - NEVER a
false "in progress". The ledger ONLY EVER UPGRADES a case-6 BLOCKED to a more specific, evidence-backed
status (cases 3/4/5) when a FRESH entry proves it; it never downgrades a real absence into a fake
"someone is building it". On ANY doubt, default to case 6.

**Staleness is measured in dispatch-loop ticks, not wall-clock.** A `claimed`/`building` entry is
STALE when its `heartbeat_at` has not advanced across a bounded number of `odoo-coding` dispatch-loop
ticks (default: 3 ticks - the same bound as the code -> review loop). A stale entry is treated as a
dead run and falls to case 6. Do NOT guess a wall-clock timeout: a slow build and a dead build look
identical on the clock, but a live build advances its heartbeat every tick while a dead one never
does.
