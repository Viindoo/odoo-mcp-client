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
# HARD CONTRACT: this hook NEVER denies a tool call. The main agent (and any subagent) is a
#   decision-maker; hard-blocking is dangerous (can trap the agent / deadlock). So:
#   - permissionDecision is ALWAYS "allow"; we only attach `additionalContext` as a reminder.
#   - Self-gates: (1) requires an active run (no ISOLATE run-*.json with status NEEDS_NEXT;
#     resolved per ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md) → silent pass
#     otherwise. (2) requires a resolvable role=leaf match → silent pass otherwise (no
#     agent-role SSOT, no jq, unresolved agent_type = stay silent, never guess).
#   - (1) is best-effort MAIN-agent-only (skip when we can tell we are in a subagent - V-52:
#     ANY populated agent_id/agent_type means "in a subagent", no `!= general-purpose`
#     special-case, honoring this hook's own "stay silent when unsure" contract). (2) is the
#     mirror: it fires ONLY when we can tell we ARE in a subagent.
#   - Degrades to exit 0 on any uncertainty (no jq, parse error, no run file, no SSOT file).

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

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
      jq -cn --arg agent "$AGENT_NAME" \
        --arg ctx "You are running as \"$AGENT_NAME\", declared role=leaf in the agent-role SSOT (generator/skill_tool_deps.json). A HARD LEAF never launches another agent and never runs a git mutation or Skill(git-ops) itself - that is the coordinator/orchestrator's job (see snippets/worker-brief.md, snippets/git-delegation.md). This is only a reminder - proceed if you judge this classification does not actually apply to your current dispatch." \
        '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"allow", additionalContext:$ctx}}'
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

# Active-run self-gate: only nudge when a run is mid-flight (status NEEDS_NEXT). ISOLATE
# state dir (Problem 3 - snippets/state-root-resolution.md), resolved FROM the hook's own
# project cwd. CRITICAL RESILIENCE: this hook must NEVER hard-fail or block a tool call - a
# resolver refusal (non-git, no marker) or any error (missing script, no CLAUDE_PLUGIN_ROOT)
# silently falls back to the legacy project-relative path (previously this was ALWAYS
# CWD-relative, a bug: it ignored the resolver entirely). This fallback is the SANCTIONED
# "Advisory-glob exception" (V-50, state-root-resolution.md) - a read-only glob that only ever
# degrades to silence, never a write; do not copy this pattern into a call site that writes.
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
PROJ_DIR="${CWD:-${CLAUDE_PROJECT_DIR:-.}}"
RUN_DIR="$(cd "$PROJ_DIR" 2>/dev/null && bash "${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/resolve_project_dir.sh" isolate 2>/dev/null || true)"
[[ -n "$RUN_DIR" ]] || RUN_DIR="${PROJ_DIR}/.odoo-ai"
active_run=""
shopt -s nullglob
for rf in "$RUN_DIR"/run-*.json; do
  st="$(jq -r '.status // empty' "$rf" 2>/dev/null || true)"
  if [[ "$st" == "NEEDS_NEXT" ]]; then active_run="$rf"; break; fi
done
shopt -u nullglob
[[ -n "$active_run" ]] || _pass    # no active run → not in drive-to-done mode → silent

jq -cn --arg ctx "You are mid-run (active drive-to-done run under the namespaced state root - see snippets/state-root-resolution.md). As the orchestrator, prefer delegating this $TOOL to a subagent/specialist so your context stays clean for decisions. This is only a reminder - proceed if you judge it right." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"allow", additionalContext:$ctx}}'
exit 0
