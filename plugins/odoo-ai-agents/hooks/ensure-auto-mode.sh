#!/usr/bin/env bash
# ensure-auto-mode.sh - SessionStart keeper of the auto-mode entries written by
# scripts/setup-steps/34-auto-mode.sh in the user's settings file.
#
# WHY a hook: a plugin cannot ship `autoMode` or `permissions`, and its entry text changes
# between plugin versions. After the owner approved the step once, this hook converges the
# settings to the installed version's entries (the step prunes its own tagged entries and
# writes the current set, never touching the user's own) and says so in one line.
#
# Contract: idempotent, never blocks the session, always exits 0.
#   - ODOO_AI_NO_AUTO_PERMS=1 (the opt-out the sibling ensure hooks honour) -> do nothing.
#   - Step script absent (partial install) -> silent.
#   - The settings carry NO tagged autoMode.environment entry (the owner never approved the
#     step on this machine) -> write nothing; one advice line to run
#     /odoo-ai-agents:odoo-setup auto-mode.
#   - Approved and current -> silent.
#   - Approved and drifted -> `apply` non-interactively, then one line naming the update.
#   - A settings file that is not valid JSON is never written (the step refuses it).
#   - CLAUDE_SETTINGS, ODOO_AI_HOME and ODOO_AI_INSTANCES are honoured by the step.
set -uo pipefail

if [ "${ODOO_AI_NO_AUTO_PERMS:-0}" = "1" ]; then
  exit 0
fi

_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
_step="${_plugin_root}/scripts/setup-steps/34-auto-mode.sh"
_facts="${_plugin_root}/scripts/lib/auto_mode_facts.py"
_settings="${CLAUDE_SETTINGS:-${HOME}/.claude/settings.json}"

if [ ! -f "${_step}" ] || [ ! -f "${_facts}" ]; then
  exit 0
fi

_emit() {
  echo "i  $1" >&2
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg ctx "$1" \
      '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
  fi
}

if ! python3 "${_facts}" marker "${_settings}" >/dev/null 2>&1; then
  _emit "odoo-ai-agents: auto mode is not configured for this machine yet - run /odoo-ai-agents:odoo-setup auto-mode once to review and approve the entries (routine development stays unblocked, protected branches keep a human gate)."
  exit 0
fi

if bash "${_step}" check >/dev/null 2>&1; then
  exit 0
fi

_out="$(bash "${_step}" apply </dev/null 2>&1)"
_rc=$?
if [ "${_rc}" -eq 0 ]; then
  _emit "odoo-ai-agents: the auto-mode entries in Claude settings were updated to this plugin version; start a new session for them to take effect."
else
  _emit "odoo-ai-agents: could not update the auto-mode entries (rc=${_rc}); run /odoo-ai-agents:odoo-setup auto-mode. Detail: ${_out}"
fi
exit 0
