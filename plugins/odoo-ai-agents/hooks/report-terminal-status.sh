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
# Additive sibling of enforce-grounding.sh / parse-continuation.sh in the SubagentStop
# array - it does NOT modify or depend on either hook.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON has transcript_path + stop_hook_active.
#   - HARD CONTRACT: never blocks, and never emits stdout JSON at all (no
#     {continue:...}, no {decision:...}) - this hook is a pure side-effecting observer.
#   - Loop-safe via stop_hook_active, for consistency with its siblings.
#   - Degrades to a silent no-write (exit 0) on ANY uncertainty: no jq, no transcript,
#     an unparseable transcript, or an unresolvable state root. A write call site never
#     falls back to a guessed location (unlike parse-continuation.sh's read-only
#     advisory-glob exception - snippets/state-root-resolution.md - which is
#     sanctioned ONLY for read-only globs, never for a hook that writes state).
#
# Two signatures, either one triggers ONE appended line:
#   S1 (strand)   - the transcript's FINAL assistant turn carries no `status:` from
#                   DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT inside a fenced
#                   ```continuation block (same fence-parsing approach as
#                   parse-continuation.sh, scoped to only the LAST assistant turn).
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

TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
[[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]] || _pass

# --- Isolate the FINAL assistant turn (ASSISTANT-authored only, same posture as
# enforce-grounding.sh / enforce-teardown.sh) and, separately, every tool_result id
# anywhere in the transcript. Both signatures below read ONLY this one final turn plus
# the transcript-wide tool_result id set - never an earlier assistant turn, so a
# subagent that emitted a correct terminal status several turns ago but then kept
# going (or fired one more tool call) after it is still caught.
RESULT="$(jq -nR '
  [inputs | fromjson?] as $all
  | ($all
      | map(
          (.message // .) as $m
          | (($m.role // .type) // "") as $role
          | (($m.content // []) ) as $content
          | {role: $role, content: $content}
        )
      | map(select(.role == "assistant" and (.content | type) == "array" and (.content | length) > 0))
    ) as $ass
  | ( [ $all[]
        | (.message // .) as $m
        | ($m.content // [])
        | (if type == "array" then .[] else empty end)
        | select(.type == "tool_result")
        | (.tool_use_id // "")
        | select(length > 0)
      ] ) as $resids
  | if ($ass | length) == 0 then
      {have_final: false, final_text: "", unresolved: []}
    else
      ($ass[-1].content) as $fc
      | ([$fc[] | select(.type == "text") | (.text // "")] | join("\n")) as $ftext
      | ([$fc[] | select(.type == "tool_use") | (.id // "")] | map(select(length > 0))) as $fids
      | {have_final: true, final_text: $ftext, unresolved: ($fids - $resids)}
    end
' "$TRANSCRIPT" 2>/dev/null || true)"
[[ -n "$RESULT" ]] || _pass

HAVE_FINAL="$(printf '%s' "$RESULT" | jq -r '.have_final // false' 2>/dev/null || echo false)"
[[ "$HAVE_FINAL" == "true" ]] || _pass   # nothing parseable to judge - degrade silently, never assume a strand

FINAL_TEXT="$(printf '%s' "$RESULT" | jq -r '.final_text // ""' 2>/dev/null || true)"
UNRESOLVED_COUNT="$(printf '%s' "$RESULT" | jq -r '.unresolved | length' 2>/dev/null || echo 0)"

# S1 - the LAST fenced ```continuation block in the final assistant turn (same
# fence-parsing awk as parse-continuation.sh) must carry a terminal status. Absent
# block, or a status outside the four terminal values, both count as S1.
STATUS="$(printf '%s\n' "$FINAL_TEXT" | awk '
  /```[ \t]*continuation/ { incont=1; next }
  incont && /```/        { incont=0; next }
  incont && /status:/    { line=$0; sub(/.*status:[ \t]*/,"",line); sub(/[ \t].*/,"",line); last=line }
  END { print last }' 2>/dev/null || true)"

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
# whole workload, not one repo (snippets/state-root-resolution.md § The three tiers).
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
