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

**Scope note (Block 2W).** The planned worktree dependency graph's fork-from-integrated-parent
lineage (every wave's worktrees fork from the ONE `run-integration` branch, which already carries
all prior waves' cherry-picked code) makes INTRA-run cross-wave dependency-blindness
**structurally solved** - a dependent wave's worktrees always carry their dependencies' committed
code by construction. So this ledger and the `odoo-backend-coder` dependency pre-flight now backstop ONLY
concurrent INDEPENDENT runs (cross-run) + the manifest-crash safety net; the intra-run false BLOCKED
no longer fires.

## Location and why the SHARE dir

Resolve the ledger root ONCE per run via the Tier-2 SHARE resolver (Problem 3 - full policy +
classification tables: `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), following its
mandatory resolve-capture-substitute protocol:

```bash
SHARE_DIR="$(bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share)"
LEDGER_ROOT="$SHARE_DIR/coordination/modules"
```

Each module's entry lives at `$LEDGER_ROOT/<module>/entry.json`.

WHY SHARE (not ISOLATE, and not a per-worktree `./.odoo-ai/`): the SHARE dir is keyed off
`sha256(realpath(git rev-parse --git-common-dir))` - a linked worktree has its own `.git` file, but
it points back to the ONE shared common git dir of the principal checkout, so `--git-common-dir`
(and therefore the resolved SHARE dir) is the SAME path for every linked worktree and every
concurrent invocation of THIS repo. A per-worktree ISOLATE dir is private to that worktree - two
concurrent runs in two worktrees would each write their own copy and never see each other, which is
exactly the cross-run blindness this ledger removes. The SHARE dir lives under `$ODOO_AI_HOME`
(machine-global, outside any git working tree), so it needs no gitignore entry and is never
committed - it is live cross-run state, not source. Do NOT collapse this to a bare
`$ODOO_AI_HOME/coordination/` (cross-project-global) - that would regress cross-repo isolation:
two UNRELATED repos on the same host would then see each other's module claims. The SHARE dir
already gives exactly what this ledger needs: repo-scoped, worktree-converged coordination.

**No git repo and no project marker (resolver refuses).** If `resolve_project_dir.sh share` fails
(the run is outside any git repo AND no `.odoo-ai-root`/`__manifest__.py` marker exists up the
chain), there is no shared ledger: degrade to per-run behavior with NO ledger (the per-run
pre-flight still produces graceful BLOCKEDs), and LOG that the ledger was unavailable. Never fabricate
a ledger location outside the repo.

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

## Ownership - `odoo-coding` is the sole writer

ONLY `odoo-coding` writes the ledger: it owns the NEW-module build boundary and the DONE barrier, so
it is the only actor that knows when a module transitions state. The one consistent statement of who
reads and who writes:

- **WRITE - `odoo-coding` alone.** No other actor ever writes an entry or a status.
- **READ for coordination decisions - `odoo-coding` alone.** It reads its own ledger to run the
  § Decision table and to drive the bounded N-barrier WAIT INTERNALLY (§ N-barrier WAIT ownership).
- **The hard-leaf `odoo-backend-coder`/`odoo-frontend-coder` workers stay LEDGER-UNAWARE** (as does
  the `odoo-coder` coordinator) - they never read or write `$LEDGER_ROOT`; only the `odoo-backend-coder`
  runs the § Dependency pre-flight and emits a RAW `BLOCKED: manifest dependency <D> unresolved on
  addons-path` (the coordinator relays it up unchanged).
- **`run-harness`'s between-wave integration neither writes the ledger nor drives any ledger
  decision.** It receives `odoo-coding`'s already-classified BLOCKED and runs its saga path; it may
  read the ledger read-only for its own execution-log, but it never runs the WAIT or the decision table.

The ledger write is NOT a worklog entry (`snippets/worklog-contract.md`) and NOT a
Continuation-Contract dispatch (`snippets/continuation-contract.md`) - it is per-module shared
cross-run coordination state with a single writer (`odoo-coding`).

## N-barrier WAIT ownership - `odoo-coding` owns it internally

`odoo-coding` owns the ENTIRE decision-table case-3 WAIT/re-queue loop internally and transparently
to its caller: it waits, bounded by N dispatch-loop barriers (§ Staleness), for a concurrent build to
land. When the bounded wait is EXHAUSTED with no progress it returns a normal clean `BLOCKED`
(case 6) - the caller (`run-harness`'s between-wave integration) treats that like any other BLOCKED
and never re-implements a barrier wait of its own.

## Claim = atomic `mkdir` (no flock, no lock file)

To claim a NEW module before dispatching its coder:

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
   fires ONLY cross-run: intra-run it is structurally impossible under the Block 2W
   fork-from-integrated-parent lineage (a dependent wave already carries prior waves' committed code).
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
