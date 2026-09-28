#!/usr/bin/env bash
# parse-continuation.sh - SubagentStop ADVISORY nudge: when a subagent ends having emitted a
# Continuation Contract with status NEEDS_NEXT, remind the run-harness to advance.
#
# Additive sibling of enforce-grounding.sh in the SubagentStop array - it does NOT modify or
# depend on that hook (the grounding invariants stay exactly as they were). This one only reads
# the subagent's own transcript for the ```continuation block of the report it delivered (a
# SubagentHandback message or its final text - hooks/final-report.sh) and emits a non-blocking nudge.
#
# HARD CONTRACT: never blocks. Emits {continue:true, systemMessage:...} or stays silent.
#   Loop-safe via stop_hook_active. Degrades to exit 0 on any uncertainty.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass

# Shared helper: hooks/final-report.sh (which transcript, and the report the caller received).
_FR_LIB="${BASH_SOURCE[0]%/*}/final-report.sh"
[[ -r "$_FR_LIB" ]] || _pass
# shellcheck source=/dev/null
. "$_FR_LIB"

# The subagent's OWN transcript (agent_transcript_path on SubagentStop - never the session-wide
# transcript_path, which carries the parent's and every sibling's text).
TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass

# The REPORT the caller received - a delivered SubagentHandback message, else the final message
# text - so a continuation block quoted in a tool_result/instruction, or left in an earlier turn,
# is not mistaken for the real one.
NORM="$(_final_report_text "$TRANSCRIPT" "$(_hook_last_message "$INPUT")")"
[[ -n "$NORM" ]] || _pass

# The status of the LAST closed ```continuation fenced block in the report.
STATUS="$(_continuation_status "$(_continuation_block "$NORM")")"

# Back-compat: a legacy `SUGGESTED_NEXT:` line (no fenced block) is read as an implicit
# NEEDS_NEXT. Some agents still emit only this (agents/odoo-backend-coder.md,
# agents/odoo-frontend-coder.md etc.) - honour the back-compat promised in
# snippets/continuation-contract.md so the chain is not silently dropped.
if [[ -z "$STATUS" ]] && printf '%s\n' "$NORM" | grep -qiE '^[[:space:]]*SUGGESTED_NEXT:'; then
  STATUS="NEEDS_NEXT"
fi

[[ "$STATUS" == "NEEDS_NEXT" ]] || _pass    # only nudge when more work is signalled

# ISOLATE state dir (Problem 3 - snippets/state-root-resolution.md), resolved FROM the
# hook's own project cwd so the nudge names the correct per-worktree run-*.json instead
# of the legacy project-relative convention. CRITICAL RESILIENCE: this hook must NEVER
# hard-fail or block - a resolver refusal (non-git, no marker) or any error (missing
# script, no CLAUDE_PLUGIN_ROOT) silently falls back to the legacy project-relative path.
# This fallback is the SANCTIONED "Advisory-glob exception" (V-50, state-root-resolution.md) -
# a read-only glob that only ever degrades to silence, never a write; do not copy this
# pattern into a call site that writes.
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
PROJ_DIR="${CWD:-${CLAUDE_PROJECT_DIR:-.}}"
RUN_DIR="$(cd "$PROJ_DIR" 2>/dev/null && bash "${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/resolve_project_dir.sh" isolate 2>/dev/null || true)"
[[ -n "$RUN_DIR" ]] || RUN_DIR="${PROJ_DIR}/.odoo-ai"

jq -cn --arg m "A subagent emitted a Continuation Contract with status=NEEDS_NEXT. run-harness: read the active $RUN_DIR/run-*.json, record this result, and advance the next[] node(s). (Advisory - you decide; not a block.)" \
  '{continue:true, systemMessage:$m}'
exit 0
