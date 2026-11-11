# Module Coordination Ledger (cross-run / worktree)

One run cannot see whether a module it depends on is being built right now by another run or
worktree, was built elsewhere, or is absent. The ledger records that, so `odoo-coding` can turn a
coder's raw `BLOCKED: manifest dependency <D> unresolved on addons-path` into a specific decision.
Inside one run every node's worktree forks from the `run-integration` branch and its coder
provisions on its own tree (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`
§ Worktree-addons carve-out), so the ledger matters across runs only.

## Location

Resolve the root once per run with `project_dir` (axis `share`, `cwd` = your worktree;
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) and substitute the captured path
literally: `<SHARE_DIR>/coordination/modules/<module>/entry.json`. The share axis is the same for
every linked worktree of one repository and different for unrelated repositories. When
`project_dir` returns `PROJECT_DIR_UNRESOLVED`, run with no ledger and log that; never invent a
location.

## Entry

```json
{
  "module": "<technical name>",
  "status": "claimed|building|done|failed",
  "run_id": "<the worklog run-or-slug, reused - never a new id>",
  "worktree": "<absolute path of the worktree building this module>",
  "claimed_at": "<UTC timestamp>",
  "heartbeat_at": "<UTC timestamp>"
}
```

Timestamps: `date -u +%Y-%m-%dT%H:%M:%SZ`.

## Ownership

`odoo-coding` alone writes the ledger, reads it for decisions and drives the wait below.
`odoo-coder` never reads or writes it: it runs its dependency pre-flight and returns the raw
`BLOCKED`. The plan runner receives `odoo-coding`'s classified result and never runs a wait or the
decision table itself.

## Claim = atomic `mkdir`

The node claims; the key is the module's technical name. `odoo-coding` claims EVERY module of the
node's `modules` list before dispatching the node's coder, in ascending technical-name order -
never dependency order, which leaves independent modules unordered and lets two runs deadlock.

```bash
# once per run, so the per-module mkdir below can only fail on an existing directory
mkdir -p "$LEDGER_ROOT"

MODULE="<technical name>"
# the claim: a BARE mkdir, never `mkdir -p`
if err="$(mkdir "$LEDGER_ROOT/$MODULE" 2>&1)"; then
    date_now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"module":"%s","status":"claimed","run_id":"%s","worktree":"%s","claimed_at":"%s","heartbeat_at":"%s"}\n' \
        "$MODULE" "$RUN_ID" "$WORKTREE" "$date_now" "$date_now" > "$LEDGER_ROOT/$MODULE/entry.json"
elif [ -d "$LEDGER_ROOT/$MODULE" ]; then
    cat "$LEDGER_ROOT/$MODULE/entry.json"        # lost: another run owns it - § Decision table
else
    printf 'ledger claim error for %s: %s\n' "$MODULE" "$err" >&2    # any other error: BLOCK
fi
```

The directory's existence is the lock: exactly one caller's `mkdir` succeeds. A lost claim on one
module of the list keeps every claim the node already won and re-queues the whole node behind the
wait of case 3. There is no release: removing a directory would destroy the lock, and marking a
held claim `failed` would block every run watching it. The states are `claimed -> building ->
done | failed` and nothing else.

## State transitions

`odoo-coding` sets `claimed` on winning the claim; `building` when the module's coder is
dispatched; `done` on the module's DONE (built, reviewed, committed); `failed` on a terminal
BLOCK. It refreshes `heartbeat_at` on every dispatch-loop tick for each module it is building, and
at run end leaves none of its entries `claimed` or `building`.

A coder dispatch that ends without a parseable Continuation Contract (a harness error, an empty
return, a status outside the four terminal values) flips its modules to `failed` at once, with no
staleness wait: the dispatch provably ended. On doubt whether a real report came back, `failed`;
a module whose coder did return a valid report is never failed on suspicion.

## Decision table - `BLOCKED: manifest dependency <D> unresolved`

`odoo-coding` evaluates in order; the first match wins:

1. `D` is on the effective addons path: a false alarm - re-run the pre-flight and proceed.
2. `D` is a module of THIS run still `claimed` or `building`: a dispatch-ordering error - re-queue
   the dependent after `D` is done.
3. Another `run_id` holds `D` `claimed` or `building` with a fresh heartbeat: wait and re-queue,
   bounded by the staleness count; then case 6.
4. `D` is `done` but not on this worktree's addons path: `BLOCKED: dependency <D> was built in
   run <X> - integrate/rebase it onto this worktree before continuing`.
5. `D` is `failed`, in this run or another: `BLOCKED: prerequisite module <D> failed in run <X>`.
6. `D` is absent from the ledger, or its heartbeat is stale: `BLOCKED: missing prerequisite
   module <D>`.

## Staleness

An entry is stale when its `heartbeat_at` has not advanced across 3 dispatch-loop ticks - ticks,
not wall-clock: a slow build advances its heartbeat every tick, a dead one never does. Absence is
the honest fallback: the ledger only upgrades case 6 to a more specific case when a fresh entry
proves it, and on any doubt the answer is case 6.
