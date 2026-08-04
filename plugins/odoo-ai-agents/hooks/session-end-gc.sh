#!/usr/bin/env bash
# session-end-gc.sh - SessionEnd crash backstop for the resource-teardown mechanism (L1.3).
#
# WHY: a -9 / OOM / abort runs no teardown prose and emits no DONE claim, so the
# DONE-gated SubagentStop teardown gate self-passes and never fires. An orphaned
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
# ALSO: after gc, this hook runs `reap-orphans` in its DEFAULT list-only mode -
# see "Discovery half" below. gc and reap-orphans are deliberately DIFFERENT,
# non-overlapping mechanisms (allocator.py's own header comment,
# scripts/lib/allocator.py:1094-1120): gc only ever reclaims a DB a LEASE still
# references; reap-orphans finds the class gc structurally cannot reach - an
# ephemeral-shaped DB with ZERO lease reference at all (a registry quarantine
# after corruption, a crash in the narrow acquire-write window, ...). Before this
# hook called it, `reap-orphans` had no caller anywhere in the plugin - the
# mechanism existed and was unreachable. This hook is now that path for the
# DISCOVERY half only; see "Discovery half, never the destructive half" below
# for why the drop half deliberately stays elsewhere.
#
# CONTRACT (Claude Code SessionEnd):
#   - Best-effort, SILENT, bounded. SessionEnd CANNOT block, so this hook NEVER
#     emits a decision - it only runs the reaper(s) and exits 0.
#   - hooks.json caps this WHOLE script at 25s wall-clock (SessionEnd `timeout`) -
#     that outer bound, not either internal `timeout N` below, is what actually
#     protects session teardown from hanging. The `gc` internal timeout MUST stay
#     at 25 (matching hooks.json) so a slow orphan's SIGTERM grace (_stop_group:
#     up to 10s, PER orphan) is not truncated mid-teardown when gc alone is given
#     the full budget; the `reap-orphans` internal timeout is deliberately SHORTER
#     (15) purely as a defensive per-command cap - if `gc` already consumed most
#     of the outer 25s reclaiming several orphans, the outer hooks.json bound (not
#     this inner one) is what actually cuts `reap-orphans` off, and an incomplete
#     LIST-ONLY read is harmless (no mutation is in flight to interrupt, unlike a
#     drop). Keep the outer hooks.json value and the `gc` timeout in lockstep;
#     the `reap-orphans` timeout only needs to stay <= the `gc` one.
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
# block (a lying DONE) -> SessionEnd gc + reap-orphans-list (session death) ->
# next-acquire gc / ttl / a human's explicit reap-orphans --yes.

set -uo pipefail

# Read + discard stdin so the caller's write never sees EPIPE (SessionEnd sends JSON).
cat >/dev/null 2>&1 || true

command -v python3 >/dev/null 2>&1 || exit 0

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
LIB_DIR="$PLUGIN_ROOT/scripts/lib"
ALLOC="$LIB_DIR/allocator.py"
[[ -n "$PLUGIN_ROOT" && -f "$ALLOC" ]] || exit 0

# Bounded so a wedged Postgres/drop can never hang session teardown, but ABOVE the
# allocator's internal 10s-per-orphan SIGTERM grace so a slow orphan is reaped, not
# killed mid-teardown. Silent by contract - stdout/stderr discarded, exit always 0.
timeout 25 python3 "$ALLOC" gc >/dev/null 2>&1 || true

# Discovery half: default (list-only) reap-orphans, persisted so a human can
# review it later - NEVER /dev/null'd, unlike gc above, because an unreachable
# result defeats the whole point of wiring this in (see header). Best-effort:
# a resolution failure or a write failure here must never fail this hook.
if [[ -f "$LIB_DIR/resolve_instances.sh" ]]; then
    # shellcheck source=../scripts/lib/resolve_instances.sh
    source "$LIB_DIR/resolve_instances.sh" 2>/dev/null || true
    if command -v _odoo_ai_runtime_dir >/dev/null 2>&1; then
        RUNTIME_DIR="$(_odoo_ai_runtime_dir 2>/dev/null || true)"
        if [[ -n "$RUNTIME_DIR" ]] && mkdir -p "$RUNTIME_DIR" 2>/dev/null; then
            timeout 15 python3 "$ALLOC" reap-orphans \
                >"$RUNTIME_DIR/reap-orphans-candidates.log" 2>&1 || true
        fi
    fi
fi

exit 0
