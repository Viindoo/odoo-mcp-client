#!/usr/bin/env bash
# session-end-gc.sh - SessionEnd crash backstop for the resource-teardown mechanism (L1.3).
#
# WHY: a -9 / OOM / abort runs no teardown prose and emits no DONE claim, so the
# DONE-gated SubagentStop teardown gate self-passes and never fires. An orphaned
# `odoo-bin` master + its Postgres backend then survive the WHOLE Claude session
# (unlike browser pages, which die with the session's MCP server process). This
# hook is the crash-time trigger for the allocator's gc: after L1.2, gc group-stops
# AND reclaims any orphan lease whose owner died with the session (TTL-expired-but-
# process-alive), freeing the leaked RAM.
#
# CONTRACT (Claude Code SessionEnd):
#   - Best-effort, SILENT, bounded (`timeout 25`). SessionEnd CANNOT block, so this
#     hook NEVER emits a decision - it only runs the reaper and exits 0.
#   - The 25s bound MUST stay above the allocator's own internal teardown wait
#     (_stop_group: up to 10s SIGTERM grace before SIGKILL, PER orphan) so a slow
#     orphan is actually reaped on this pass rather than killed mid-flight. The
#     hooks.json SessionEnd `timeout` must match (25). Keep all three in lockstep.
#   - Self-gates to exit 0 when python3 or allocator.py is missing (no way to gc).
#   - Any gc failure is swallowed: a crash backstop must never itself error out.
#
# This is one link in the teardown chain: prose release (graceful) -> SubagentStop
# block (a lying DONE) -> SessionEnd gc (session death) -> next-acquire gc / ttl.

set -uo pipefail

# Read + discard stdin so the caller's write never sees EPIPE (SessionEnd sends JSON).
cat >/dev/null 2>&1 || true

command -v python3 >/dev/null 2>&1 || exit 0

ALLOC="${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/allocator.py"
[[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$ALLOC" ]] || exit 0

# Bounded so a wedged Postgres/drop can never hang session teardown, but ABOVE the
# allocator's internal 10s-per-orphan SIGTERM grace so a slow orphan is reaped, not
# killed mid-teardown. Silent by contract - stdout/stderr discarded, exit always 0.
timeout 25 python3 "$ALLOC" gc >/dev/null 2>&1 || true
exit 0
