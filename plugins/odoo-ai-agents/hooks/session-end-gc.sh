#!/usr/bin/env bash
# session-end-gc.sh - SessionEnd crash backstop for the resource-teardown mechanism (L1.3).
#
# WHAT IT RECLAIMS - the ENDING session's own leases, provably-dead owners, and stale browser-server
# byproducts; nothing else:
#   1. `gc --scope dead-sessions` - the allocator's AUTOMATIC semantics over the machine-global
#      registry: a lease whose recorded session anchor has been dead past the allocator's grace
#      window, a dead or recycled server pid on this host, an expired park. NEVER the TTL arm, so a
#      lease whose liveness merely cannot be proven (another host, no pid, no anchor) is never
#      taken here - that is an explicit `gc` for a human.
#   2. `gc --scope anchor --anchor <this session's anchor>` - the running/reserved leases (never
#      parked, never shared) that THIS session acquired, once the session's anchor process is
#      provably gone. The anchor is captured by the HOOK role (`allocator.py anchor`, which finds
#      the session through CLAUDE_PID or the claude ancestor this hook runs under) and handed to
#      the worker, which waits up to ANCHOR_WAIT_S for that process to exit - a SessionEnd fires
#      while `claude` is still shutting down. No `--force`: the allocator re-checks the anchor
#      itself and refuses a live one (ANCHOR_ALIVE), so a session that did not actually end -
#      `/clear` (skipped outright: the process carries on), or a wait that ran out - loses
#      nothing. A lease the session PARKED survives its end by design: park is how a session
#      keeps a database for a later one.
#   3. `reap-orphans` in its DEFAULT list-only mode - see "Discovery half" below.
#   4. Files the browser MCP servers wrote on their own under the state root, past their age
#      limit (`browser_mcp_servers.py prune`; never a per-repo state dir).
# Every other session's live lease is untouched: the registry is MACHINE-GLOBAL (every concurrent
# session on this host writes the same leases.json), so a sweep that is not scoped by session
# anchor is a sweep over other people's work in progress.
#
# WHY IT EXISTS AT ALL: a -9 / OOM / abort kills the run without executing SubagentStop or Stop,
# so the teardown gate never fires, and an `odoo-bin` master + its Postgres backend survive the
# session. Step 2 is the normal-exit path for a session's own leases; step 1 is what eventually
# reclaims a CRASHED session's leases (its anchor dies with it), from the next session to end on
# this host.
#
# The worker runs with the session identity SCRUBBED (no CLAUDE_PID, no CLAUDE_CODE_SESSION_ID,
# ODOO_AI_SESSION_ANCHOR=none): the allocator treats a caller that shares a lease's session id as
# that session RESUMED and re-anchors the lease onto it, which would make the ending session's own
# leases look alive to the very sweep meant to reclaim them.
#
# ALSO: gc and reap-orphans are deliberately DIFFERENT, non-overlapping mechanisms (allocator.py's
# own header comment plus the "reap-orphans: DB-side sweep INDEPENDENT of the lease registry"
# banner in scripts/lib/allocator.py): gc only ever reclaims a DB a LEASE still references;
# reap-orphans finds the class gc structurally cannot reach - an ephemeral-shaped DB with ZERO
# lease reference at all (a registry quarantine after corruption, a crash in the narrow
# acquire-write window, ...). This hook is its path for the DISCOVERY half only; see "Discovery
# half, never the destructive half" below for why the drop half deliberately stays elsewhere.
#
# WHY THE WORK IS DETACHED (the shape of this file - measured, not assumed):
#   A SessionEnd hook does NOT get the `timeout` its registration declares. On
#   Claude Code 2.1.233 this script (declared 25s, real runtime ~2.2s) was
#   ABORTED ~1s after the only other SessionEnd hook in the batch finished -
#   3 runs out of 3 - surfacing as `SessionEnd hook [...] failed: Hook cancelled`
#   (the CLI's rendering of ABORT_ERR on the spawn, never a non-zero exit from
#   here: the hook role below cannot return anything but 0). The budget is
#   RELATIVE, not absolute: adding a slower sibling hook to the same batch let
#   the identical 2.2s run complete cleanly, so "how long do I get" is decided by
#   hooks this plugin does not own and cannot see.
#   That abort KILLS the child, it does not merely stop awaiting it: the
#   candidate log below was left 0 bytes (truncated open by the redirect, then
#   killed mid-write), and an aborted probe never reached its own last line. So
#   the pre-detach shape did not just print an ugly error - it silently truncated
#   the reaper, and a REAL orphan (gc spends up to 10s of SIGTERM grace PER
#   orphan) had no chance of being reclaimed in the ~1s actually granted, i.e.
#   the backstop failed in exactly the crash case it exists for.
#   Hence: this file has TWO roles. The hook role validates, spawns the worker in
#   its OWN session (start_new_session=True == setsid, so it is not in the CLI's
#   process group and survives the CLI's death - verified: the worker still
#   completed 8s after `claude` had exited), and returns in milliseconds. The
#   worker role does the real, slow work with its own generous bounds. Do NOT
#   "simplify" this back into a straight-line synchronous script; that is the
#   defect, not the cleanup.
#
# CONTRACT (Claude Code SessionEnd):
#   - Best-effort, SILENT, bounded. SessionEnd CANNOT block, so this hook NEVER
#     emits a decision - it only spawns the reaper and exits 0. SILENT means
#     silent on the CALLER'S channels (this hook's own stdout/stderr, and the
#     detached worker's, which the spawning Popen hands /dev/null). It has never
#     meant "produce no record": the reap-orphans candidate list below is
#     persisted for exactly that reason, and so, now, is the allocator's stderr
#     (see ALLOC_DIAG_BASENAME).
#   - The HOOK role must stay ~instant (one python3 spawn). Its hooks.json
#     `timeout` now bounds only that spawn; it is NOT, and never was, a real
#     budget for the reaping itself (see above) - so do not raise it hoping to
#     buy the worker more time, and do not move work back under it.
#   - The WORKER's own `timeout N` values below are the ONLY real bound on the
#     reaping, which is why they are sized for the work (several orphans x 10s
#     SIGTERM grace) instead of being squeezed under a hook budget. Before the
#     detach they could not be: 25 (gc) + 15 (reap) already exceeded the 25s the
#     registration granted the whole script, so a gc that actually used its bound
#     guaranteed the rest was cut off.
#   - Self-gates to exit 0 when python3 or allocator.py is missing (no way to gc).
#   - Any gc/reap-orphans failure is swallowed: a crash backstop must never
#     itself error out.
#
# Discovery half, never the destructive half (justification for the trigger
# choice - which automatic checkpoint should reach reap-orphans, and how far):
#   SessionEnd IS the right trigger for the LIST-ONLY discovery half: it is the
#   one automatic checkpoint that already runs at the end of EVERY session, so
#   wiring the default (list-only, non-mutating) `reap-orphans` call here is what
#   makes the mechanism reachable at all, with zero new caller surface and zero
#   new destructive risk - the default emits REAP_CANDIDATE/REAP_SKIPPED lines
#   and touches nothing.
#   SessionEnd is the WRONG trigger for the DESTRUCTIVE half (`--yes`), so this
#   hook NEVER passes it: (1) SessionEnd is silent/unattended by contract above -
#   there is no human to see WHY a database is about to be dropped, which is
#   exactly the "always a visible, auditable read before it is ever destructive"
#   invariant `reap-orphans` was designed around (scripts/lib/allocator.py
#   cmd_reap_orphans header); (2) `reap-orphans` scans the WHOLE declared
#   cluster, not just leases this session touched, so an automatic `--yes` here
#   would let any session's end silently drop a database some OTHER, unrelated
#   session's tooling created outside the lease registry - a strictly larger
#   blast radius than this hook's `gc` calls, which act only on leases whose owner is
#   provably gone (step 1) or on THIS session's own leases (step 2). The
#   candidate list this hook persists (below) is the hand-off point: a human
#   reviews it and runs `allocator.py reap-orphans --yes` explicitly, elsewhere.
#
# This is one link in the teardown chain: prose release (graceful) -> SubagentStop
# block (an unforwarded live lease) -> SessionEnd gc of the ending session + dead sessions +
# reap-orphans-list -> a human's explicit `gc` / `reap-orphans --yes`. `acquire` reclaims no
# database at all (only capacity from provably-dead owners), so it is no longer a link.

set -uo pipefail

# The real bound on the reaping, now that no hook budget truncates it. gc gets
# room for several orphans at up to 10s of SIGTERM grace each (_stop_group);
# reap-orphans is a read-only sweep, so a shorter cap is enough and an incomplete
# LIST is harmless (no mutation is in flight to interrupt, unlike a drop).
GC_TIMEOUT_S=300
REAP_TIMEOUT_S=120
# How long the worker waits for the ending session's anchor process to exit before it asks the
# allocator to reclaim that session's leases. SessionEnd fires while `claude` is still shutting
# down, so an immediate check would find it alive and (correctly) be refused. Past this bound the
# allocator's own ANCHOR_ALIVE refusal is what keeps a still-running session's work safe.
# ODOO_AI_SESSION_END_ANCHOR_WAIT_S overrides it (a whole non-negative number of seconds) so a
# test can prove the "still alive after the wait" branch without sleeping a minute.
ANCHOR_WAIT_S="${ODOO_AI_SESSION_END_ANCHOR_WAIT_S:-60}"
[[ "$ANCHOR_WAIT_S" =~ ^[0-9]+$ ]] || ANCHOR_WAIT_S=60

# The durable target for the ALLOCATOR's stderr, appended under the Tier-1
# `logs/` root (`odoo_ai_state_root`/logs - the same root allocator.py's own
# evidence log uses; see RECLAIM_LOG_BASENAME there).
#
# WHY a file and not /dev/null, and why the JSONL evidence log does NOT already
# cover it: allocator.py reports a reclamation on TWO channels (stderr notice +
# `allocator-reclaimed.jsonl`), but only the RECLAIMED notice is on both. Three
# classes of message reach stderr ONLY, and each is the sole record of something
# that outlives the command:
#   - `REFUSING to signal pid N ...` - ownership was not proven, so NOTHING was
#     signalled and a live server process was LEAKED. The lease row is reclaimed
#     regardless, so after this line the process is the only thing left, and
#     nothing else on the machine records that it was knowingly left running.
#   - `ERROR - ... drop of <db> FAILED; DB retained, lease kept for retry` - the
#     database survived. `_gc` deliberately does NOT report such a lease as
#     reclaimed, so there is no JSONL line for it at all.
#   - `WARNING - could not append the reclaim record ... the stderr line above is
#     now the ONLY record of that reclamation` - the JSONL write itself failed.
#     Discarding stderr here is precisely the case that warning is about.
# On this hook that is not a hypothetical: SessionEnd runs at the end of EVERY
# session, so it is the plugin's largest single reclaimer, and its worker is
# detached with stdout/stderr on /dev/null - there is no terminal for any of the
# above to reach even in principle.
#
# Appended (never truncated): concurrent sessions and later sessions each add to
# one machine-global account, and every write is a whole line to an O_APPEND fd
# (python line-buffers stderr), so lines interleave but never tear. It grows ONLY
# when the allocator had something to say - a quiet gc writes zero bytes - and,
# unlike the JSONL, it is deliberately INSIDE `prune_stale_run_artifacts`' `*.log`
# family (scripts/lib/state_reclaim.sh), so an idle machine reclaims it after the
# retention window. That is the right policy HERE and the wrong one there: the
# JSONL is the only surviving evidence of a DESTROYED database, while everything
# in this file describes state that still exists and is re-observable (`ps`,
# `allocator.py list`, the cluster itself) for as long as it matters.
#
# SSOT: this basename and the resolve-or-fall-back-to-/dev/null block in
# `_run_worker` are mirrored by `scripts/setup-steps/50-instance-spinup.sh`
# (`_register_shared`), the other caller that used to discard this stream. The
# two are kept identical by tests/test_allocator_stderr_survives.py; fold both
# into scripts/lib/state_reclaim.sh (which owns `odoo_ai_state_root` and the
# `logs/` family) when that file is next open for change.
ALLOC_DIAG_BASENAME="allocator-stderr.log"

# --------------------------------------------------------------------------- #
# Worker role - the actual reaping, running detached from the dying session.
# --------------------------------------------------------------------------- #
_run_worker() {
    local lib_dir="$1" alloc="$2" anchor="${3:-}" reason="${4:-}"

    # Resolve the durable stderr target (see ALLOC_DIAG_BASENAME above). Every
    # rung falls back to /dev/null - today's behavior - rather than failing:
    # a missing lib, an unresolvable root, an uncreatable dir and an unwritable
    # file are all "no record", never "no gc". The writability probe is not
    # optional: `mkdir -p` succeeds on an EXISTING but unwritable dir, and a
    # redirect that cannot open its target makes bash skip the command entirely,
    # which would turn a lost log line into a lost reclamation.
    local diag=/dev/null diag_log
    if [[ -f "$lib_dir/state_reclaim.sh" ]]; then
        # shellcheck source=../scripts/lib/state_reclaim.sh
        source "$lib_dir/state_reclaim.sh" 2>/dev/null || true
    fi
    if command -v odoo_ai_state_root >/dev/null 2>&1; then
        diag_log="$(odoo_ai_state_root)/logs/$ALLOC_DIAG_BASENAME"
        if mkdir -p "${diag_log%/*}" 2>/dev/null && ( : >>"$diag_log" ) 2>/dev/null; then
            diag="$diag_log"
        fi
    fi

    # Silent on this worker's own channels, exit always 0 - but the allocator's
    # stderr is APPENDED to the durable log, not discarded: it carries the
    # RECLAIMED notice for every lease a sweep destroys plus the three
    # stderr-only classes above. STDOUT stays /dev/null: `cmd_gc`'s stdout is a
    # PROTOCOL (`ALLOC_RECLAIMED=<token>` lines + a count) whose every fact is a
    # strict subset of the stderr record, so persisting it would duplicate, not
    # add.
    #
    # Step 1 (header): provably-dead owners, automatic semantics, never the TTL arm. It runs
    # FIRST because it does not depend on the ending session at all, so the anchor wait below
    # never delays it.
    timeout "$GC_TIMEOUT_S" python3 "$alloc" gc --scope dead-sessions >/dev/null 2>>"$diag" || true

    # Step 2 (header): the ending session's own running/reserved leases, once its anchor is gone.
    # `/clear` ends a session inside a process that keeps running - nothing to reclaim for it.
    if [[ -n "$anchor" && "$reason" != "clear" ]]; then
        local anchor_pid="${anchor%%:*}" waited=0
        if [[ "$anchor_pid" =~ ^[0-9]+$ ]]; then
            while (( waited < ANCHOR_WAIT_S )) && kill -0 "$anchor_pid" 2>/dev/null; do
                sleep 1
                waited=$(( waited + 1 ))
            done
            # No --force: the allocator re-checks the anchor (pid AND fingerprint) and refuses a
            # live one with ANCHOR_ALIVE, which is the answer we want if the wait ran out.
            timeout "$GC_TIMEOUT_S" python3 "$alloc" gc --scope anchor --anchor "$anchor" >/dev/null 2>>"$diag" || true
        fi
    fi

    # Stale files the browser MCP servers wrote on their own under the state root (playwright's
    # auto-named files in projects/, pagecast's scratch recordings). Same rule the browser
    # launcher applies at every start: scripts/lib/browser_mcp_servers.py prune.
    if [[ -f "$lib_dir/browser_mcp_servers.py" ]]; then
        python3 "$lib_dir/browser_mcp_servers.py" prune >/dev/null 2>&1 || true
    fi

    # Discovery half: default (list-only) reap-orphans, persisted so a human can
    # review it later - NEVER /dev/null'd, because an unreachable result defeats
    # the whole point of wiring this in (see header). Its own file, not the gc log
    # above: this is a full LIST that is rewritten every session and read as a
    # snapshot ("what is reapable right now"), while the gc log is an append-only
    # incident record - truncating one into the other would destroy whichever
    # semantics it did not get. Best-effort: a resolution failure or a write
    # failure here must never fail this worker.
    if [[ -f "$lib_dir/resolve_instances.sh" ]]; then
        # shellcheck source=../scripts/lib/resolve_instances.sh
        source "$lib_dir/resolve_instances.sh" 2>/dev/null || true
        if command -v _odoo_ai_runtime_dir >/dev/null 2>&1; then
            local runtime_dir
            runtime_dir="$(_odoo_ai_runtime_dir 2>/dev/null || true)"
            if [[ -n "$runtime_dir" ]] && mkdir -p "$runtime_dir" 2>/dev/null; then
                timeout "$REAP_TIMEOUT_S" python3 "$alloc" reap-orphans \
                    >"$runtime_dir/reap-orphans-candidates.log" 2>&1 || true
            fi
        fi
    fi
}

# --------------------------------------------------------------------------- #
# Entry - worker re-entry first, then the hook role.
# --------------------------------------------------------------------------- #
command -v python3 >/dev/null 2>&1 || exit 0

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
LIB_DIR="$PLUGIN_ROOT/scripts/lib"
ALLOC="$LIB_DIR/allocator.py"
[[ -n "$PLUGIN_ROOT" && -f "$ALLOC" ]] || exit 0

if [[ "${1:-}" == "--detached-worker" ]]; then
    _run_worker "$LIB_DIR" "$ALLOC" "${2:-}" "${3:-}"
    exit 0
fi

# Read stdin in full (so the caller's write never sees EPIPE) - SessionEnd sends JSON carrying
# `session_id` and `reason`.
HOOK_INPUT="$(cat 2>/dev/null || true)"

# Hook role, in ONE python3 spawn: parse the payload, capture the ending session's anchor while
# this hook still runs under it (`allocator.py anchor`: ODOO_AI_SESSION_ANCHOR, else CLAUDE_PID,
# else the claude ancestor of this process), and spawn the worker into its OWN session.
#   - The anchor is discarded when it is provably NOT this session's: the allocator reports a
#     session id and the payload names a DIFFERENT one. Uncertainty drops step 2, never widens it.
#   - The worker's environment is scrubbed of the session identity (see the header).
# python3 (already a hard requirement above) is what makes the detach portable: setsid(1) is
# Linux-only, absent on macOS, while start_new_session=True is exactly setsid() on every POSIX
# host. The worker is deliberately orphaned - it must outlive both this hook and the CLI.
HOOK_INPUT="$HOOK_INPUT" python3 - "$0" "$LIB_DIR" <<'PY' >/dev/null 2>&1 || true
import json
import os
import subprocess
import sys

script, alloc = sys.argv[1], os.path.join(sys.argv[2], "allocator.py")
try:
    payload = json.loads(os.environ.get("HOOK_INPUT") or "{}")
    if not isinstance(payload, dict):
        payload = {}
except ValueError:
    payload = {}
reason = str(payload.get("reason") or "")
session_id = str(payload.get("session_id") or "")

anchor = ""
try:
    out = subprocess.run([sys.executable, alloc, "anchor", "--format", "json"],
                         capture_output=True, text=True, timeout=5)
    fields = (json.loads(out.stdout or "{}") or {}).get("fields") or {}
    anchor = str(fields.get("ODOO_AI_SESSION_ANCHOR") or "")
    anchor_sid = str(fields.get("ODOO_AI_SESSION_ID") or "")
    if anchor_sid and session_id and anchor_sid != session_id:
        anchor = ""
except Exception:
    anchor = ""

env = dict(os.environ)
env.pop("HOOK_INPUT", None)
for name in ("CLAUDE_PID", "CLAUDE_CODE_SESSION_ID"):
    env.pop(name, None)
env["ODOO_AI_SESSION_ANCHOR"] = "none"

subprocess.Popen(
    ["bash", script, "--detached-worker", anchor, reason],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    env=env,
)
PY

exit 0
