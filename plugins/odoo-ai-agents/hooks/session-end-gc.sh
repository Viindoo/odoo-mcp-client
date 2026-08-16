#!/usr/bin/env bash
# session-end-gc.sh - SessionEnd crash backstop for the resource-teardown mechanism (L1.3).
#
# WHY: a -9 / OOM / abort kills the run without executing SubagentStop or Stop at
# all, so the teardown gate never gets the chance to fire. An orphaned
# `odoo-bin` master + its Postgres backend then survive the WHOLE Claude session
# (unlike browser pages, which die with the session's MCP server process). This
# hook is the crash-time trigger for the allocator's gc: after L1.2, gc
# group-stops AND reclaims any orphan lease whose owner pid is DEAD on this host
# (immediate - no TTL wait needed), or - only when liveness cannot be proven at
# all (a different host, or no pid was ever recorded on the lease) - whose TTL
# has expired, freeing the leaked RAM in either case.
#
# Note (liveness is authoritative, not a mere condemn signal - see
# `scripts/lib/allocator.py::_is_stale`): a session that dies while its
# `odoo-bin` child SURVIVES as a detached (setsid) orphan - the process the
# session spawned did not die WITH it - is no longer reclaimed by this hook (or
# by any later TTL-driven gc) once its pid is verified alive on this host. That
# is a deliberate tradeoff, not a gap: reaping a lease we cannot prove is
# abandoned risks killing genuinely in-progress work, which costs the user far
# more than an un-reaped orphan costs in RAM (see `_is_stale`'s docstring for
# the full tradeoff writeup). Such a survivor is reclaimed only by an explicit
# `release`, a human's `allocator.py gc`/`list` triage, or the process dying on
# its own.
#
# ALSO: after gc, the worker runs `reap-orphans` in its DEFAULT list-only mode -
# see "Discovery half" below. gc and reap-orphans are deliberately DIFFERENT,
# non-overlapping mechanisms (allocator.py's own header comment plus the
# "reap-orphans: DB-side sweep INDEPENDENT of the lease registry" banner in
# scripts/lib/allocator.py): gc only ever reclaims a DB a LEASE still
# references; reap-orphans finds the class gc structurally cannot reach - an
# ephemeral-shaped DB with ZERO lease reference at all (a registry quarantine
# after corruption, a crash in the narrow acquire-write window, ...). Before this
# hook called it, `reap-orphans` had no caller anywhere in the plugin - the
# mechanism existed and was unreachable. This hook is now that path for the
# DISCOVERY half only; see "Discovery half, never the destructive half" below
# for why the drop half deliberately stays elsewhere.
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
#     emits a decision - it only spawns the reaper and exits 0.
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
#   blast radius than this hook's existing `gc` call, which only ever acts on
#   leases already in the (session-scoped-by-construction) registry. The
#   candidate list this hook persists (below) is the hand-off point: a human
#   reviews it and runs `allocator.py reap-orphans --yes` explicitly, elsewhere.
#
# This is one link in the teardown chain: prose release (graceful) -> SubagentStop
# block (an unforwarded live lease) -> SessionEnd gc + reap-orphans-list (session
# death) -> next-acquire gc / ttl / a human's explicit reap-orphans --yes.

set -uo pipefail

# The real bound on the reaping, now that no hook budget truncates it. gc gets
# room for several orphans at up to 10s of SIGTERM grace each (_stop_group);
# reap-orphans is a read-only sweep, so a shorter cap is enough and an incomplete
# LIST is harmless (no mutation is in flight to interrupt, unlike a drop).
GC_TIMEOUT_S=300
REAP_TIMEOUT_S=120

# --------------------------------------------------------------------------- #
# Worker role - the actual reaping, running detached from the dying session.
# --------------------------------------------------------------------------- #
_run_worker() {
    local lib_dir="$1" alloc="$2"

    # Silent by contract - stdout/stderr discarded, exit always 0.
    timeout "$GC_TIMEOUT_S" python3 "$alloc" gc >/dev/null 2>&1 || true

    # Discovery half: default (list-only) reap-orphans, persisted so a human can
    # review it later - NEVER /dev/null'd, unlike gc above, because an unreachable
    # result defeats the whole point of wiring this in (see header). Best-effort:
    # a resolution failure or a write failure here must never fail this worker.
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
    _run_worker "$LIB_DIR" "$ALLOC"
    exit 0
fi

# Read + discard stdin so the caller's write never sees EPIPE (SessionEnd sends JSON).
cat >/dev/null 2>&1 || true

# Spawn the worker into its OWN session. python3 (already a hard requirement
# above) is what makes this portable: setsid(1) is Linux-only, absent on macOS,
# while start_new_session=True is exactly setsid() on every POSIX host. The
# worker is deliberately orphaned - it must outlive both this hook and the CLI.
python3 - "$0" <<'PY' >/dev/null 2>&1 || true
import subprocess
import sys

subprocess.Popen(
    ["bash", sys.argv[1], "--detached-worker"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
PY

exit 0
