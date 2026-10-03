#!/usr/bin/env bash
# remind-delegate.sh - PreToolUse ADVISORY nudges. Two independent advisories share this file
# (same event, same base subagent-detection, same HARD CONTRACT below):
#
#   (1) Drive-to-done delegate nudge (MAIN agent only, mid-run, Write/Edit/MultiEdit/Bash) -
#       WHY: during an active run the main agent should stay an orchestrator - delegate heavy
#       work to subagents so its context does not grow with run length. This hook NUDGES
#       that, it never enforces it.
#   (2) Leaf/spawner advisory nudge (V-01 mechanism) - a subagent whose best-effort agent_type
#       resolves to a `role: leaf` entry in the agent-role SSOT (generator/skill_tool_deps.json
#       "agents".<name>.role) gets reminded, on the Agent tool, a git-mutating Bash command, or
#       Skill(...git-ops...), that a HARD LEAF never spawns another agent and never runs git -
#       the deterministic guarantee is the `check_orchestration.py` agent-role lint (build-time);
#       THIS is only a same-turn reminder, not the enforcement.
#
# HARD CONTRACT: this hook NEVER decides the tool call - it is advisory only, not enforcement.
#   The main agent (and any subagent) is a decision-maker; hard-blocking is dangerous (can trap
#   the agent / deadlock) - but silently auto-approving is equally dangerous: it would bypass
#   normal permission-rule evaluation (incl. the user's own deny/ask rules) for the exact git
#   mutation / risky tool call this hook exists to discourage. So:
#   - The output carries `additionalContext` ONLY - NO permissionDecision at all. Without one the
#     call goes through normal permission evaluation untouched, so the user still sees any
#     prompt/deny they would otherwise see. No decision value is neutral: "allow"/"ask"/"deny"
#     decide the call, and "defer" is not a no-op either - in a `claude -p` / SDK run it stops the
#     session at that tool call (stop_reason tool_deferred) for the calling process to resume.
#   - Self-gates: (1) requires an active run OF THIS SESSION (an ISOLATE run-*.json with status
#     NEEDS_NEXT, resolved per ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md, that this
#     session wrote last - hooks/run-ownership.sh) -> silent pass otherwise. (2) requires a
#     resolvable role=leaf match -> silent pass otherwise (no agent-role SSOT, no jq, unresolved
#     agent_type = stay silent, never guess).
#   - (1) is best-effort MAIN-agent-only (skip when we can tell we are in a subagent - V-52:
#     ANY populated agent_id/agent_type means "in a subagent", no `!= general-purpose`
#     special-case, honoring this hook's own "stay silent when unsure" contract). (2) is the
#     mirror: it fires ONLY when we can tell we ARE in a subagent.
#   - Degrades to exit 0 on any uncertainty (no jq, parse error, no run file, no SSOT file).
#   - Said ONCE per context window: each advisory text is emitted only when it is not already in
#     the calling agent's transcript since the last compaction (hooks/advice-once.sh) - the main
#     agent's session transcript for (1), the subagent's own transcript for (2). A repeat on every
#     later Bash/Edit/Write call of the run would tell the agent nothing new and stay in its
#     context each time. An unreadable transcript or helper -> emit (the advisory is never lost).

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# Shared helpers, resolved relative to THIS script: hooks/advice-once.sh (is this advisory already
# in the context) and hooks/lease-correlation.sh (_lease_agent_transcript - which transcript is a
# subagent's own). Unreadable -> every advisory counts as unseen.
_HOOK_DIR="${BASH_SOURCE[0]%/*}"
_seen() { return 1; }
if [[ -r "$_HOOK_DIR/advice-once.sh" && -r "$_HOOK_DIR/lease-correlation.sh" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/advice-once.sh"
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/lease-correlation.sh"
  _seen() { _advice_seen "$1" "$2"; }
fi

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"

# Best-effort subagent detection, shared by both advisories below (V-52 fix: ANY populated
# agent_id/agent_type means "in a subagent" - dropped the old `!= general-purpose` carve-out).
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
IN_SUBAGENT=false
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] && IN_SUBAGENT=true

# --- (2) Leaf/spawner advisory (V-01) -------------------------------------------------------
# Independent of the drive-to-done gates below (no active-run requirement - a leaf can drift
# any time). Only when we ARE in a subagent AND its best-effort agent_type resolves to a
# `role: leaf` entry in the agent-role SSOT.
if [[ "$IN_SUBAGENT" == true && -n "$AGENT_TYPE" ]]; then
  DEPS_FILE="${CLAUDE_PLUGIN_ROOT:-}/generator/skill_tool_deps.json"
  # Normalize a plugin-qualified type ("odoo-ai-agents:odoo-backend-coder") to the bare name -
  # the SSOT keys agents by bare name.
  AGENT_NAME="${AGENT_TYPE##*:}"
  IS_LEAF=false
  if [[ -n "$AGENT_NAME" && -f "$DEPS_FILE" ]]; then
    ROLE="$(jq -r --arg n "$AGENT_NAME" '.agents[$n].role // empty' "$DEPS_FILE" 2>/dev/null || true)"
    [[ "$ROLE" == "leaf" ]] && IS_LEAF=true
  fi
  if [[ "$IS_LEAF" == true ]]; then
    RISKY=false
    case "$TOOL" in
      Agent) RISKY=true ;;
      Bash)
        CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
        # Mirrors check_orchestration.py's GIT_MUTATION_RE (single SSOT verb list).
        if printf '%s' "$CMD" | grep -qE '\bgit (commit|add|push|rebase|merge|reset|cherry-pick|stash|tag|checkout|branch)\b'; then
          RISKY=true
        fi
        ;;
      Skill)
        SKILL_ARG="$(printf '%s' "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null || true)"
        [[ "$SKILL_ARG" == *git-ops* ]] && RISKY=true
        ;;
    esac
    if [[ "$RISKY" == true ]]; then
      CTX="You are running as \"$AGENT_NAME\", declared role=leaf in the agent-role SSOT (generator/skill_tool_deps.json). A HARD LEAF never launches another agent and never runs a git mutation or Skill(git-ops) itself - that is the coordinator/orchestrator's job (see snippets/worker-brief.md, snippets/git-delegation.md). This is only a reminder - proceed if you judge this classification does not actually apply to your current dispatch."
      _seen "$(_lease_agent_transcript "$INPUT")" "$CTX" && _pass
      jq -cn --arg ctx "$CTX" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:$ctx}}'
      exit 0
    fi
  fi
fi

# --- (1) Drive-to-done delegate nudge (MAIN agent only) -------------------------------------
case "$TOOL" in
  Write|Edit|MultiEdit|Bash) ;;          # only the heavy/mutating tools are worth a nudge
  *) _pass ;;
esac

[[ "$IN_SUBAGENT" == false ]] || _pass    # inside a subagent - it is supposed to do the work; do not nag

# Active-run self-gate: only nudge while THIS session drives a run - a NEEDS_NEXT record in this
# project's state dir that this session wrote last (hooks/run-ownership.sh, which also resolves the
# state dir from the hook's own project cwd and owns its read-only fallback). A record another
# session - live or long dead - left there does not make this session mid-run. When ownership cannot
# be told (no readable transcript, a jq that cannot run the scan) the nudge keeps its older rule:
# any NEEDS_NEXT record. Unreadable shared helper -> pass, the plugin-wide convention.
[[ -r "$_HOOK_DIR/run-ownership.sh" ]] || _pass
# shellcheck source=/dev/null
. "$_HOOK_DIR/run-ownership.sh"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
needs_next=()
while IFS= read -r rf; do [[ -n "$rf" ]] && needs_next+=("$rf"); done \
  < <(_needs_next_runs "$(_run_state_dir "$CWD")")
[[ ${#needs_next[@]} -gt 0 ]] || _pass    # no active run -> not in drive-to-done mode -> silent
TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
owned="$(_session_owned_runs "$TRANSCRIPT" "${needs_next[@]}")"
[[ $? -eq 2 || -n "$owned" ]] || _pass

# One text for every heavy tool, so Bash, Edit and Write share one reminder.
CTX="You are mid-run (active drive-to-done run under the namespaced state root - see snippets/state-root-resolution.md). As the orchestrator, prefer delegating Bash/Edit/Write work to a subagent/specialist so your context stays clean for decisions. This is only a reminder - proceed if you judge it right."
_seen "$TRANSCRIPT" "$CTX" && _pass
jq -cn --arg ctx "$CTX" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:$ctx}}'
exit 0
