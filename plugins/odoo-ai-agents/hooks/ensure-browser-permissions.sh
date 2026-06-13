#!/usr/bin/env bash
# ensure-browser-permissions.sh — SessionStart self-apply of the browser MCP tool
# permissions into ~/.claude/settings.json so the visual-UI agents
# (odoo-ui-reviewer / odoo-ui-debugger) run without a per-tool approval prompt.
#
# WHY a hook (not just docs): Claude Code has no post-install hook and a plugin
# cannot declare tool permissions in its manifest. settings.json is the durable
# layer (survives plugin updates), so a SessionStart check->apply makes the
# permission self-apply on the first session after any install/update and then
# no-op forever after. This is the ONE machine-level bit that cannot ship in the
# repo; everything else (server args, agent tool grants) is SSOT-in-repo and
# already self-applies via the bundled .mcp.json + agent frontmatter.
#
# Contract: idempotent, never blocks the session, always exits 0.
#   - Escape hatch: export ODOO_AI_NO_AUTO_PERMS=1 to disable (no-op). Honours a
#     user who deliberately removed the prefixes.
#   - Delegates the actual check/write to scripts/setup-steps/30-permissions.sh
#     (the SSOT for the prefix list + idempotent, backed-up writes). That script
#     auto-proceeds when stdin is not a TTY, so `apply </dev/null` is
#     non-interactive here.
#   - Honours CLAUDE_SETTINGS (the step script reads it) for tests / non-default
#     homes — never hard-codes the path.
set -uo pipefail

# Opt-out: respect a user who turned auto-permissioning off.
if [ "${ODOO_AI_NO_AUTO_PERMS:-0}" = "1" ]; then
  exit 0
fi

_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
_perms="${_plugin_root}/scripts/setup-steps/30-permissions.sh"

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
  _msg="odoo-ai-agents: NEW browser MCP tool permissions were just added to Claude settings - because permissions are finalized BEFORE SessionStart hooks run, RESTART Claude Code once (or start a new session) for them to take effect this session; meanwhile the PermissionRequest hook auto-approves these browser tools."
else
  _msg="odoo-ai-agents: could not auto-allow browser MCP permissions (rc=${_rc}). Run /odoo-ai-agents:odoo-setup permissions. Detail: ${_out}"
fi

# Visible console nudge (stderr) + structured SessionStart context (stdout, jq only).
echo "i  ${_msg}" >&2
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ctx "${_msg}" \
    '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
fi

exit 0
