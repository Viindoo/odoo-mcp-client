#!/usr/bin/env bash
# report-terminal-status.sh - SubagentStop OBSERVABILITY hook (strand telemetry).
#
# WHY: a stranded subagent (one that ends its turn expecting an unwakeable background
# child, or that stops mid tool-call) produces NO output and NO error - every OTHER
# guard in this plugin proves the PROSE changed; nothing proves BEHAVIOR changed. This
# hook is a runtime detector, not a lint: it appends ONE line to a rolling counter file
# under the machine-global state root whenever the subagent's own transcript carries
# either strand signature below, so the RATE is measurable before/after a fix. It
# proves a rate, not a cause - it never inspects WHY a stop happened, only THAT it
# matches a documented signature.
#
# Additive sibling of enforce-grounding.sh in the SubagentStop array - it does NOT modify or
# depend on that hook.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON has agent_transcript_path (the subagent's own
# transcript - the one read here), transcript_path (the whole session's) + stop_hook_active.
#   - HARD CONTRACT: never blocks, and never emits stdout JSON at all (no
#     {continue:...}, no {decision:...}) - this hook is a pure side-effecting observer.
#   - Judges only a stop no hook continued (stop_hook_active=false): the agent's OWN turn end,
#     before any hook text reached it - one verdict per dispatch round, the rate this counter
#     compares before and after a prompt fix. A turn a sibling's note or block bought is the hooks'
#     doing and is judged by the gates themselves (a lease left there is still blocked by the
#     teardown gate); counting it here would log one round twice whenever its extra turn strands
#     again. Residual: a strand first introduced in a hook-bought turn is not counted.
#   - Degrades to a silent no-write (exit 0) on ANY uncertainty: no jq, no transcript,
#     an unparseable transcript, or an unresolvable state root. A write call site never
#     falls back to a guessed location (unlike the read-only advisory-glob exception of
#     snippets/state-root-resolution.md, which is sanctioned ONLY for read-only globs,
#     never for a hook that writes state).
#
# Two signatures, either one triggers ONE appended line:
#   S1 (strand)   - the REPORT the caller received (a delivered SubagentHandback message,
#                   else the FINAL assistant turn's text) carries no `status:` from
#                   DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT inside a closed fenced
#                   ```continuation block (hooks/final-report.sh).
#   S2 (unexecuted tool_use) - a `tool_use` id in that same final assistant turn that
#                   never appears as a `tool_use_id` in any tool_result anywhere in the
#                   transcript.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass

# Shared helper: hooks/final-report.sh (which transcript, the report, the final turn).
_FR_LIB="${BASH_SOURCE[0]%/*}/final-report.sh"
[[ -r "$_FR_LIB" ]] || _pass
# shellcheck source=/dev/null
. "$_FR_LIB"

# The subagent's OWN transcript (agent_transcript_path on SubagentStop - never the session-wide
# transcript_path, which carries the parent's and every sibling's turns).
TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass

# The FINAL TURN is every assistant record after the last non-meta user record - not the last
# assistant RECORD: the harness writes each content block of a turn as its own record, so the last
# one can be a thinking-only record with no text at all. S2 reads that turn's tool_use ids; nothing
# parseable (no assistant turn at all) -> degrade silently, never assume a strand.
UNRESOLVED_COUNT="$(_final_turn_unresolved_count "$TRANSCRIPT")"
[[ "$UNRESOLVED_COUNT" =~ ^[0-9]+$ ]] || _pass

# S1 - the LAST closed ```continuation block of the REPORT the caller received (a delivered
# SubagentHandback message, else the final turn's text) must carry a terminal status. Absent
# block, or a status outside the four terminal values, both count as S1. The status is compared by
# its key (final-report.sh _continuation_status_key), so `NEEDS_CONTEXT(<field>)` or a backticked
# value is the terminal status it spells, as the teardown gates read it.
FINAL_TEXT="$(_final_report_text "$TRANSCRIPT" "$(_hook_last_message "$INPUT")")"
STATUS="$(_continuation_status_key "$(_continuation_status "$(_continuation_block "$FINAL_TEXT")")")"

S1=0
case "$STATUS" in
  DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT) ;;
  *) S1=1 ;;
esac

# S2 - a tool_use id in the final assistant turn with no matching tool_result anywhere
# in the transcript.
S2=0
[[ "${UNRESOLVED_COUNT:-0}" =~ ^[0-9]+$ ]] && [[ "$UNRESOLVED_COUNT" -gt 0 ]] && S2=1

# Neither signature fired -> a clean stop -> nothing to count.
[[ "$S1" == "1" || "$S2" == "1" ]] || _pass

SIG=""
[[ "$S1" == "1" ]] && SIG="S1"
[[ "$S2" == "1" ]] && SIG="${SIG:+$SIG,}S2"

# --- Resolve the machine-global Tier-1 state root ($ODOO_AI_HOME) the SAME way every
# other Tier-1 consumer does (session-end-gc.sh's runtime dir / resolve_instances.sh's
# instances.toml) - source the EXISTING resolver rather than re-deriving the
# HOME/ODOO_AI_HOME/trailing-slash fallback logic here. Tier-1 (flat, machine-global),
# not a per-worktree ISOLATE dir - this counter measures a RATE across the owner's
# whole workload, not one repo (snippets/state-root-resolution.md section The three tiers).
# WRITE call site: on any resolution failure this degrades to skipping the write
# entirely - never a guessed/wrong-location path.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
LIB_DIR="${PLUGIN_ROOT}/scripts/lib"
[[ -n "$PLUGIN_ROOT" && -f "$LIB_DIR/resolve_instances.sh" ]] || _pass
# shellcheck source=../scripts/lib/resolve_instances.sh
source "$LIB_DIR/resolve_instances.sh" 2>/dev/null || _pass
command -v _odoo_ai_runtime_dir >/dev/null 2>&1 || _pass
RUNTIME_DIR="$(_odoo_ai_runtime_dir 2>/dev/null || true)"
[[ -n "$RUNTIME_DIR" ]] || _pass

TELEMETRY_DIR="${RUNTIME_DIR%/runtime}/telemetry"
mkdir -p "$TELEMETRY_DIR" 2>/dev/null || _pass
COUNTER_FILE="$TELEMETRY_DIR/strand-events.log"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
[[ -n "$TS" ]] || TS="unknown"

printf '%s signature=%s\n' "$TS" "$SIG" >>"$COUNTER_FILE" 2>/dev/null || true

exit 0
