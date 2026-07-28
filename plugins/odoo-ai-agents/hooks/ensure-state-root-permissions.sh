#!/usr/bin/env bash
# ensure-state-root-permissions.sh - SessionStart self-apply of the narrow
# state-root Bash/Read/Edit permission rules into ~/.claude/settings.json
# so the planning pipeline (odoo-planner / odoo-doc-planner / intake Phase P)
# runs without a per-call approval prompt for its routine $ODOO_AI_HOME reads
# and writes.
#
# WHY a hook (not just docs): same rationale as ensure-browser-permissions.sh -
# a plugin cannot declare tool/path permissions in its manifest, so settings.json
# self-apply on SessionStart is the only durable, automatic path.
#
# Contract: idempotent, never blocks the session, always exits 0.
#   - Escape hatch: export ODOO_AI_NO_AUTO_PERMS=1 to disable (no-op) - the SAME
#     variable ensure-browser-permissions.sh honours, so one opt-out covers both.
#   - Delegates the actual check/write to
#     scripts/setup-steps/32-permissions-state-root.sh (the SSOT for the rule
#     list + idempotent, backed-up writes; it also honours the opt-out itself,
#     so this hook's own check is a defensive, redundant-by-design belt-and-
#     braces guard, not the only enforcement point).
#   - Honours CLAUDE_SETTINGS (the step script reads it) for tests / non-default
#     homes - never hard-codes the path.
set -uo pipefail

# Opt-out: respect a user who turned auto-permissioning off.
if [ "${ODOO_AI_NO_AUTO_PERMS:-0}" = "1" ]; then
  exit 0
fi

_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
_perms="${_plugin_root}/scripts/setup-steps/32-permissions-state-root.sh"

# Plugin not fully installed (step script absent) -> stay silent, do nothing.
[ -f "${_perms}" ] || exit 0

# Already satisfied -> silent no-op (the steady state after the first apply).
if bash "${_perms}" check >/dev/null 2>&1; then
  exit 0
fi

# Missing -> apply non-interactively (idempotent, backs up before writing).
_out="$(bash "${_perms}" apply </dev/null 2>&1)"
_rc=$?

if [ "${_rc}" -eq 0 ]; then
  _msg="odoo-ai-agents: NEW state-root planning permissions were just added to Claude settings - because permissions are finalized BEFORE SessionStart hooks run, RESTART Claude Code once (or start a new session) for them to take effect this session."
else
  _msg="odoo-ai-agents: could not auto-allow state-root planning permissions (rc=${_rc}). Run /odoo-ai-agents:odoo-setup permissions. Detail: ${_out}"
fi

# Visible console nudge (stderr) + structured SessionStart context (stdout, jq only).
echo "i  ${_msg}" >&2
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "${_msg}" \
    '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
fi

exit 0
