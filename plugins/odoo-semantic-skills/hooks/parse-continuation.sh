#!/usr/bin/env bash
# parse-continuation.sh - SubagentStop ADVISORY nudge: when a subagent ends having emitted a
# Continuation Contract with status NEEDS_NEXT, remind the depth-0 run-driver to advance.
#
# Additive sibling of enforce-grounding.sh in the SubagentStop array - it does NOT modify or
# depend on that hook (the grounding invariants stay exactly as they were). This one only reads
# the subagent's own transcript for a ```continuation block and emits a non-blocking nudge.
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

TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
[[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]] || _pass

# Assistant-authored text only (same normalization approach as enforce-grounding.sh), so a
# continuation block quoted in a tool_result/instruction is not mistaken for the real one.
NORM="$(jq -rR 'fromjson? | (.message // .) as $m
  | (($m.role // .type) // "") as $role
  | select($role == "assistant")
  | ($m.content // [])
  | (if type == "array" then .[] else empty end)
  | if (.type == "text") then (.text // "") else empty end' "$TRANSCRIPT" 2>/dev/null || true)"
[[ -n "$NORM" ]] || _pass

# Extract the status of the LAST ```continuation fenced block in the assistant text.
STATUS="$(printf '%s\n' "$NORM" | awk '
  /```[ \t]*continuation/ { incont=1; next }
  incont && /```/        { incont=0; next }
  incont && /status:/    { line=$0; sub(/.*status:[ \t]*/,"",line); sub(/[ \t].*/,"",line); last=line }
  END { print last }' 2>/dev/null || true)"

# Back-compat: a legacy `SUGGESTED_NEXT:` line (no fenced block) is read as an implicit
# NEEDS_NEXT. Some agents still emit only this (agents/odoo-coder.md etc.) - honour the
# back-compat promised in snippets/continuation-contract.md so the chain is not silently dropped.
if [[ -z "$STATUS" ]] && printf '%s\n' "$NORM" | grep -qiE '^[[:space:]]*SUGGESTED_NEXT:'; then
  STATUS="NEEDS_NEXT"
fi

[[ "$STATUS" == "NEEDS_NEXT" ]] || _pass    # only nudge when more work is signalled

jq -cn '{continue:true, systemMessage:"A subagent emitted a Continuation Contract with status=NEEDS_NEXT. run-driver: read the active .odoo-ai/run-*.json, record this result, and advance the next[] node(s). (Advisory - you decide; not a block.)"}'
exit 0
