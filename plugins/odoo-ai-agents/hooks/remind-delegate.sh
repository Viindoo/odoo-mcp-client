#!/usr/bin/env bash
# remind-delegate.sh - PreToolUse ADVISORY nudge for the drive-to-done loop.
#
# WHY: during an active run the main agent should stay an orchestrator - delegate heavy work
# (Write/Edit/wide reads/builds) to subagents so its context does not grow with run length.
# This hook NUDGES that, it never enforces it.
#
# HARD CONTRACT: this hook NEVER denies a tool call. The main agent is the top decision-maker
#   alongside the human; hard-blocking it is dangerous (can trap the agent / deadlock). So:
#   - permissionDecision is ALWAYS "allow"; we only attach `additionalContext` as a reminder.
#   - Self-gates: no active run (no .odoo-ai/run-*.json with status NEEDS_NEXT) → silent pass.
#   - Best-effort targets the MAIN agent only (skip when we can tell we are in a subagent), so a
#     subagent doing the delegated work is not nagged. When unsure, stay silent (no nudge).
#   - Degrades to exit 0 on any uncertainty (no jq, parse error, no run file).

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Write|Edit|MultiEdit|Bash) ;;          # only the heavy/mutating tools are worth a nudge
  *) _pass ;;
esac

# Skip when we can tell this is a subagent (so we nudge the main agent only). Claude Code
# surfaces an agent id/type for subagent tool calls; when present and non-default, stay silent.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
if [[ -n "$AGENT_ID" || ( -n "$AGENT_TYPE" && "$AGENT_TYPE" != "general-purpose" ) ]]; then
  _pass    # inside a subagent - it is supposed to do the work; do not nag
fi

# Active-run self-gate: only nudge when a run is mid-flight (status NEEDS_NEXT).
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
RUN_DIR="${CWD:-${CLAUDE_PROJECT_DIR:-.}}/.odoo-ai"
active_run=""
shopt -s nullglob
for rf in "$RUN_DIR"/run-*.json; do
  st="$(jq -r '.status // empty' "$rf" 2>/dev/null || true)"
  if [[ "$st" == "NEEDS_NEXT" ]]; then active_run="$rf"; break; fi
done
shopt -u nullglob
[[ -n "$active_run" ]] || _pass    # no active run → not in drive-to-done mode → silent

jq -cn --arg ctx "You are mid-run (active drive-to-done run in .odoo-ai/). As the orchestrator, prefer delegating this $TOOL to a subagent/specialist so your context stays clean for decisions. This is only a reminder - proceed if you judge it right." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"allow", additionalContext:$ctx}}'
exit 0
